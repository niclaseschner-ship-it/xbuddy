"""Tests für die Orchestrierung — EC-2/EC-3/EC-5/EC-10/EC-14 (Refs #27).
Enthält auch poll_loop-Tests (#294): Backoff bei leeren/fehlgeschlagenen
getUpdates-Aufrufen und Latenz-Instrumentierung (LOG-4).

Geprüft wird `handle_update` und `poll_loop`: das Zusammenspiel der
Sicherheits-Gates mit dem Agenten. Telegram-Kanal und KI-Anbieter sind
kontrollierte Doppelungen (EC-17).

SESS-5 (Ticket #264): Routing-Test für die Session-Sorten-Registry —
belegt, dass `handle_update` über `_SESSION_SORTS` an `session.deliver()`
liefert (Entry-Path-Probe).
"""

import logging
import time

import main as main_mod
from a2_receipt_store import A2ReceiptStore
from confirm import PendingStore
from fakes import (
    FakeProvider,
    FakeReadTask,
    FakeTelegram,
    FakeWriteTask,
    make_message,
    task_call_response,
    text_response,
)
from history import History
from main import _PROVIDER_DOWN, Context, handle_update, poll_loop
from model import ProviderError
from private_chat_session import PrivateChatSession
from tasks import Catalog
from telegram import TelegramError


def _ctx(tmp_path, tg, provider, catalog=None):
    return Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider,
        catalog=catalog if catalog is not None else Catalog(),
        history=History(str(tmp_path / "orch.db")), pending=PendingStore())


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


# -- EC-2: Berechtigung über Familien-Gruppe ---------------------

def test_EC_2_non_member_is_ignored(tmp_path):
    tg = FakeTelegram(members={})            # niemand ist Mitglied
    provider = FakeProvider([])              # darf nicht aufgerufen werden
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("hallo", from_user_id=7), ctx)
    assert tg.sent == []
    assert provider.requests == []


def test_EC_2_member_is_served(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Hallo!")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("hallo", from_user_id=7), ctx)
    assert len(tg.sent) == 1
    assert tg.sent[0]["text"] == "Hallo!"


# -- EC-3: Gruppe und Privatchat gleichwertig --------------------

def test_EC_3_private_chat_member_is_served(tmp_path):
    """Ein Gruppen-Mitglied erreicht den Bot auch im Privatchat."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Im Privatchat erreichbar.")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("hallo", chat_type="private", from_user_id=7), ctx)
    assert tg.sent[0]["text"] == "Im Privatchat erreichbar."


# -- EC-5: wann das System reagiert ------------------------------

def test_EC_5_group_message_without_addressing_is_ignored(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("essen ist fertig", chat_type="group",
                               from_user_id=7, mentions_bot=False,
                               reply_to_from_bot=False), ctx)
    assert tg.sent == []
    assert provider.requests == []


def test_EC_5_group_message_with_mention_is_served(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Ja, bitte?")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("@mybot was gibt es heute", chat_type="group",
                               from_user_id=7, mentions_bot=True), ctx)
    assert tg.sent[0]["text"] == "Ja, bitte?"


def test_EC_5_group_reply_to_bot_is_served(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Antwort verstanden.")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("und das auch", chat_type="group",
                               from_user_id=7, reply_to_from_bot=True), ctx)
    assert tg.sent[0]["text"] == "Antwort verstanden."


# -- EC-10: schreibende Aufgabe — Vorschlag, dann Bestätigung ----

def test_EC_10_write_proposal_then_confirmation_executes(tmp_path):
    write = FakeWriteTask(name="daten_setzen", summary="Termin eintragen",
                          result="Termin eingetragen.")
    catalog = Catalog()
    catalog.register(write)
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([task_call_response("daten_setzen", arguments={"tag": "Mo"})])
    ctx = _ctx(tmp_path, tg, provider, catalog)

    # Schritt 1: Anfrage → Vorschlag, noch keine Ausführung.
    handle_update(make_message("trag einen Termin ein", message_id=100,
                               from_user_id=7), ctx)
    assert write.execute_calls == []
    assert ctx.pending.open_count(42) == 1
    proposal_msg_id = tg.sent[0]["message_id"]

    # Schritt 2: 👍 als Antwort auf die Vorschlags-Nachricht → Ausführung.
    handle_update(make_message("👍", message_id=101, from_user_id=7,
                               reply_to_message_id=proposal_msg_id), ctx)
    assert write.execute_calls == [{"tag": "Mo"}]
    assert tg.sent[-1]["text"] == "Termin eingetragen."
    # Der Vorschlag ist verbraucht — keine doppelte Ausführung.
    assert ctx.pending.open_count(42) == 0


def test_EC_10_confirmation_word_without_pending_falls_through_to_agent(tmp_path):
    """Ein »ok« ohne offenen Vorschlag ist kein Gate-Auslöser, sondern Text."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Alles klar.")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("ok", from_user_id=7), ctx)
    assert tg.sent[0]["text"] == "Alles klar."
    assert len(provider.requests) == 1


# -- EC-14: Anbieter nicht erreichbar ----------------------------

def test_EC_14_provider_error_yields_clear_hint(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([ProviderError("Zeitüberschreitung")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("hallo", from_user_id=7), ctx)
    # klarer Hinweis, sauberer Abbruch — kein Absturz.
    assert tg.sent[0]["text"] == _PROVIDER_DOWN


# -- Issue #93: Typing-Indikator vor Provider-Aufruf -------------

def test_typing_action_sent_before_provider_call(tmp_path):
    """Vor jedem Provider-Aufruf wird `send_chat_action(chat_id, "typing")`
    abgesetzt — der Familien-Chat sieht „Bot tippt …", solange der Provider
    rechnet (Issue #93).

    EC-25 / AC2 (Ticket #287): Im Privatchat feuert ein zusätzlicher
    Typing-Aufruf VOR dem Auth-Check — damit der Nutzer auch während der
    getChatMember-Latenz „tippt gerade" sieht. Im Privatchat-Pfad sind das
    insgesamt zwei Aufrufe: einer vor Auth, einer vor dem Provider-Call.
    """
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Antwort.")])
    ctx = _ctx(tmp_path, tg, provider)

    handle_update(make_message("hallo", chat_id=42, from_user_id=7), ctx)

    # EC-25/AC2: Privatchat ⇒ ein Typing vor Auth + ein Typing vor Provider-Call.
    assert tg.chat_actions == [
        {"chat_id": 42, "action": "typing"},   # vor Auth (EC-25/AC2)
        {"chat_id": 42, "action": "typing"},   # vor Provider-Call (Issue #93)
    ]
    # Provider hat genau einen Aufruf bekommen.
    assert len(provider.requests) == 1


def test_typing_action_failure_does_not_block_turn(tmp_path):
    """Ein scheiternder Typing-Indikator (TelegramError) darf den Turn nicht
    abbrechen — er ist Komfort, kein Gate (Issue #93).

    EC-25/AC2 (Ticket #287): Im Privatchat werden zwei Typing-Aufrufe
    unternommen (vor Auth, vor Provider). Schlagen beide fehl, läuft der Turn
    trotzdem durch.
    """
    tg = FakeTelegram(members=_members(7),
                      send_chat_action_error=TelegramError("API down"))
    provider = FakeProvider([text_response("Trotzdem geantwortet.")])
    ctx = _ctx(tmp_path, tg, provider)

    handle_update(make_message("hallo", from_user_id=7), ctx)

    # Beide Aufrufe wurden versucht (beide fehlgeschlagen, aber kein Abbruch) …
    assert len(tg.chat_actions) == 2
    # … der Provider wurde trotzdem aufgerufen …
    assert len(provider.requests) == 1
    # … und der Bot hat geantwortet.
    assert tg.sent[0]["text"] == "Trotzdem geantwortet."


def test_typing_action_sent_for_each_provider_call_in_tool_loop(tmp_path):
    """Issue #156: in einem Tool-Use-Loop (Agent ruft Tool, bekommt Ergebnis,
    ruft Provider erneut) muss der Typing-Indikator VOR JEDEM Provider-Call
    abgesetzt werden — nicht nur vor dem ersten. Sonst löscht Telegram ihn
    nach ~5 s und der Bot wirkt eingefroren, obwohl er gerade die zweite
    Provider-Runde rechnet.
    """
    read = FakeReadTask(name="info_lesen", result="Es sind 22 Grad.")
    catalog = Catalog()
    catalog.register(read)
    tg = FakeTelegram(members=_members(7))
    # Zwei Provider-Runden: erst Tool-Aufruf, dann finale Antwort.
    provider = FakeProvider([
        task_call_response("info_lesen", arguments={"ort": "Berlin"}),
        text_response("In Berlin sind es 22 Grad."),
    ])
    ctx = _ctx(tmp_path, tg, provider, catalog)

    handle_update(make_message("wetter?", chat_id=42, from_user_id=7), ctx)

    # EC-25/AC2: Privatchat ⇒ Typing vor Auth + zwei mal vor Provider-Call (Tool-Loop).
    assert len(provider.requests) == 2
    assert tg.chat_actions == [
        {"chat_id": 42, "action": "typing"},   # vor Auth (EC-25/AC2)
        {"chat_id": 42, "action": "typing"},   # vor erstem Provider-Call (Issue #93)
        {"chat_id": 42, "action": "typing"},   # vor zweitem Provider-Call (Issue #156)
    ]
    # Antwort ist trotzdem korrekt durchgelaufen.
    assert tg.sent[-1]["text"] == "In Berlin sind es 22 Grad."


# ============================================================
#  #294 — poll_loop: Backoff + Pickup-Latenz-Logging
# ============================================================

def _poll_ctx(tmp_path, tg, provider=None):
    """Minimaler Context für poll_loop-Tests."""
    return Context(
        tg=tg,
        bot_username="testbot",
        family_group_chat_id="-100",
        context_depth=20,
        provider=provider or FakeProvider([]),
        catalog=Catalog(),
        history=History(str(tmp_path / "poll.db")),
        pending=PendingStore(),
    )


class _StopAfterN(Exception):
    """Wird nach N Iterationen geworfen, um den poll_loop zu beenden."""


class _FakeTelegramPoll:
    """Telegram-Doppelung, die eine skriptierte Folge von getUpdates-Ergebnissen
    liefert. Nach Erschöpfung wird ein TelegramError("Alle Antworten
    verbraucht") geworfen — der Reader-Thread (EC-37) faengt TelegramError
    und macht Backoff; im Test-Setup laeuft der Reader im selben Thread (via
    `_reader_loop` direkt), sodass die Exception nach oben gereicht werden
    kann, um den Test sauber zu beenden.

    `sleep_calls` zeichnet alle time.sleep-Aufrufe auf, die der poll_loop
    durch den monkeypatched time.sleep abgesetzt hat.
    """

    def __init__(self, responses):
        """responses: Liste von — [] (leer), [update-dict] oder Exception."""
        self._responses = list(responses)
        self.sleep_calls = []

    def get_updates(self, offset=None, timeout=30):
        if not self._responses:
            raise _StopAfterN("Alle Antworten verbraucht")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def extract_message(self, update, bot_username):
        return None

    def extract_migration(self, update):
        return None

    def extract_bot_added(self, update):
        return None

    def send_message(self, *a, **kw):
        return {"message_id": 1}

    def send_chat_action(self, *a, **kw):
        pass


def _drive_reader(tg, monkeypatch):
    """Treibt `main._reader_loop` einmal durch — bis ein _StopAfterN-Wurf
    aus der Telegram-Doppelung den Loop verlaesst. Hilfsfunktion fuer die
    Backoff- und Pickup-Latenz-Tests in der Reader/Processor-Topologie
    (EC-37, 2026-06-19).

    Im Test-Setup laeuft der Reader im aktuellen Thread (nicht als Daemon-
    Thread), damit Exceptions sichtbar sind und Backoff-Sleeps via
    monkeypatch erfasst werden koennen. Der Processor-Pfad wird durch eine
    Mini-Hand-off-Schleife im Test-Thread gespiegelt: pro Update sofort
    `ack.put(update_id)`, damit der Reader weiterlaeuft.
    """
    import queue
    import threading

    handoff = queue.Queue(maxsize=1)
    ack = queue.Queue(maxsize=1)
    open_chat_ids = set()
    lock = threading.RLock()
    stop_event = threading.Event()

    # Mini-Processor in einem Daemon-Thread: ACKt jedes Update sofort.
    def _mini_processor():
        while not stop_event.is_set():
            try:
                _t0, update_id, _update = handoff.get(timeout=0.1)
            except queue.Empty:
                continue
            ack.put(update_id)

    proc = threading.Thread(target=_mini_processor, daemon=True)
    proc.start()
    try:
        main_mod._reader_loop(
            None, tg, handoff, ack, open_chat_ids, lock, stop_event,
            get_updates_timeout=30)
    except _StopAfterN:
        pass
    finally:
        stop_event.set()
        proc.join(timeout=1.0)


def test_backoff_grows_on_empty_polls(tmp_path, monkeypatch):
    """AC3 (#294, E-EC-2-Verfeinerung): Aufeinanderfolgende leere getUpdates-
    Antworten führen zu exponentiell wachsenden sleep-Pausen.

    Erwarteter Ablauf (Start=1, Faktor=2):
      - Poll 1 → leer → sleep(1)
      - Poll 2 → leer → sleep(2)
      - Poll 3 → leer → sleep(4)
      - Poll 4 → _StopAfterN beendet den Reader

    Reader-Topologie (EC-37): Backoff liegt jetzt im `_reader_loop`. Der
    Long-Poll-timeout-Parameter (Sekunden, die Telegram wartet) ist davon
    unberührt — er bleibt auf dem Default (30 s in get_updates).
    """
    sleep_calls = []
    monkeypatch.setattr("main.time.sleep", lambda s: sleep_calls.append(s))

    # `Exception` (statt TelegramError) am Ende — der Reader-Loop faengt nur
    # TelegramError; `_StopAfterN` schluepft durch und verlaesst den Loop.
    responses = [[], [], [], TelegramError("dummy"), _StopAfterN("stop")]
    tg = _FakeTelegramPoll(responses)
    _drive_reader(tg, monkeypatch)

    # Drei leere Polls → Backoff-Pausen 1, 2, dann Fehler mit Backoff 4
    # (Fehler nach leerem Poll hat kumulierten Backoff, zählt weiter).
    assert len(sleep_calls) >= 2, (
        "Erwartet mindestens 2 Backoff-Pausen für 3 leere Polls, erhalten: %s"
        % sleep_calls)
    # Erste Pause ist die Startverzögerung (1 s).
    assert sleep_calls[0] == 1, (
        "Erste Backoff-Pause soll 1 s sein, erhalten: %s" % sleep_calls[0])
    # Zweite Pause ist das Doppelte (2 s).
    assert sleep_calls[1] == 2, (
        "Zweite Backoff-Pause soll 2 s sein, erhalten: %s" % sleep_calls[1])


def test_backoff_resets_after_update(tmp_path, monkeypatch):
    """AC3 (#294): Nach einem eintreffenden Update wird der Backoff auf 0 gesetzt —
    der nächste leere Poll startet wieder bei der Startverzögerung (1 s).

    Ablauf: leer → Update → leer → leer → stop
    Erwartete sleep-Folge: [1, (kein sleep nach Update), 1, 2, ...]
    """
    sleep_calls = []
    monkeypatch.setattr("main.time.sleep", lambda s: sleep_calls.append(s))

    update = {"update_id": 100}
    responses = [[], [update], [], [], _StopAfterN("stop")]
    tg = _FakeTelegramPoll(responses)
    _drive_reader(tg, monkeypatch)

    # Nach dem Update muss der Backoff zurückgesetzt sein — die nächste leere
    # Poll-Pause startet wieder bei 1 s, nicht bei 4 s (was sie wäre, wenn
    # kein Reset passiert).
    post_update_sleeps = sleep_calls[1:]   # die sleep nach dem ersten leeren Poll ausblenden
    if post_update_sleeps:
        assert post_update_sleeps[0] == 1, (
            "Backoff muss nach Update auf 1 s zurückgesetzt sein, "
            "erhalten: %s (alle sleeps: %s)" % (post_update_sleeps[0], sleep_calls))


def test_backoff_caps_at_5s(tmp_path, monkeypatch):
    """AC3 (#294): Der Backoff wird bei 5 s gedeckelt — kein unbegrenztes
    Wachstum. Nach genügend leeren Polls darf keine Pause über 5 s gehen.
    """
    sleep_calls = []
    monkeypatch.setattr("main.time.sleep", lambda s: sleep_calls.append(s))

    # 6 leere Polls reichen, damit der Backoff die Cap erreicht (1→2→4→5→5→5).
    responses = [[] for _ in range(6)] + [_StopAfterN("stop")]
    tg = _FakeTelegramPoll(responses)
    _drive_reader(tg, monkeypatch)

    assert sleep_calls, "Reader muss bei leeren Polls schlafen"
    assert max(sleep_calls) <= 5, (
        "Backoff-Cap ist 5 s — kein Sleep darf darüber liegen. "
        "Max: %s, alle sleeps: %s" % (max(sleep_calls), sleep_calls))


def test_pickup_latency_logged_on_updates(tmp_path, monkeypatch, caplog):
    """AC4 (#294, LOG-4): Wenn Updates eingetroffen sind, wird die familienseitige
    Pickup-Latenz als INFO-Eintrag geloggt (event=pickup_latency count=N latency_ms=X).

    Abgrenzung zu EC-23-Provider-Latenz: dieser Log-Eintrag misst die Zeit von
    getUpdates-Rückkehr (im Reader, t0) bis Ende der Verarbeitung (im
    Processor, t1), NICHT die LLM-Provider-Latenz innerhalb eines Turns.

    Reader/Processor-Topologie (EC-37, 2026-06-19): Der Log wird im
    Processor-Pfad gemacht. Wir treiben hier den vollen `poll_loop` in einem
    Daemon-Thread und beenden ihn nach kurzem Wait.
    """
    import threading
    import time as _time

    monkeypatch.setattr("main.time.sleep", lambda s: None)

    update = {"update_id": 200}
    responses = [[update], [], [], [], [], _StopAfterN("stop")]
    tg = _FakeTelegramPoll(responses)
    ctx = _poll_ctx(tmp_path, tg)

    def _runner():
        try:
            poll_loop(ctx, get_updates_timeout=30)
        except Exception:  # Test-Daemon, alle Fehler schlucken
            pass

    with caplog.at_level(logging.INFO, logger="root"):
        th = threading.Thread(target=_runner, daemon=True)
        th.start()
        # Warten, bis der Latenz-Log auftaucht.
        deadline = _time.monotonic() + 2.0
        while _time.monotonic() < deadline:
            info_messages = [r.message for r in caplog.records
                             if r.levelno == logging.INFO]
            if any("pickup_latency" in m for m in info_messages):
                break
            _time.sleep(0.02)

    info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert any(
        "pickup_latency" in m and "count=" in m and "latency_ms=" in m
        for m in info_messages
    ), (
        "AC4 (#294): Erwartet INFO-Log mit 'event=pickup_latency count=N latency_ms=X'. "
        "Gefunden: %s" % info_messages
    )


# ============================================================
#  SESS-5 (#264) — Session-Sorten-Registry: Entry-Path-Probe
# ============================================================


def test_SESS5_registry_routes_privatchat_to_session_deliver(tmp_path):
    """SESS-5 / AC1 (Ticket #264): Entry-Path-Probe — belegt, dass handle_update
    über die _SESSION_SORTS-Registry eingehende Privatnachrichten an die erste
    aktive Session-Sorte weiterleitet, statt sie an den Agenten zu schicken.

    Verwendet eine minimal-konkrete Session (PrivateChatSession-Subklasse) und
    eine echte ctx.*_sessions-Map, damit der getattr-Lookup in handle_update
    genau so läuft wie in der Produktion. Der FakeProvider bleibt ohne Aufruf —
    die Nachricht hat den Registry-Pfad genommen.
    """
    user_id = 99
    tg = FakeTelegram(members={user_id: {"status": "member"}})
    provider = FakeProvider([])

    # Wir nutzen faa_sessions als Stellvertreter für „irgendeine Session-Sorte".
    faa_sessions = {}
    ctx = Context(
        tg=tg,
        bot_username="mybot",
        family_group_chat_id="-100",
        context_depth=20,
        provider=provider,
        catalog=Catalog(),
        history=History(str(tmp_path / "sess5.db")),
        pending=PendingStore(),
        faa_sessions=faa_sessions,
    )

    # Minimalste Subklasse — nur thread-safe Queue+deliver, kein echter Skill.
    class _MinimalSession(PrivateChatSession):
        THREAD_NAME_PREFIX = "test"
        LOG_PREFIX = "TEST"

    session = _MinimalSession(chat_id=user_id)
    delivered = []

    def _worker():
        msg = session.next_message(timeout=1.0)
        if msg is not None:
            delivered.append(msg)

    session.start(_worker)
    # Worker wartet jetzt in next_message — kurz pausieren, damit er bereit ist.
    time.sleep(0.05)

    # Session in die Map eintragen — wie der echte Task-Worker es tut.
    faa_sessions[user_id] = session

    # handle_update mit einer Privatnachricht aufrufen.
    msg = make_message("Hallo Registry",
                       chat_id=user_id, from_user_id=user_id,
                       chat_type="private", message_id=300)
    handle_update(msg, ctx)

    # Warten, bis deliver() verarbeitet wurde.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not delivered:
        time.sleep(0.01)

    assert delivered, (
        "SESS-5: handle_update hätte die Privatnachricht über _SESSION_SORTS "
        "an session.deliver() weiterleiten müssen.")
    # Die Nachricht soll ankommen — make_faa_input übersetzt sie zu FaaInput;
    # wir prüfen nur, dass etwas in der Queue landete (kein Agent-Aufruf).
    assert not provider.requests, (
        "SESS-5: Bei aktiver Session darf der Agent nicht aufgerufen werden.")
    assert not tg.sent, (
        "SESS-5: Bei aktiver Session darf keine Bot-Antwort gesendet werden.")


# ============================================================
#  EC-36 Korrektur-Hook (#844) — Integrationstests handle_update
# ============================================================


class _StubHTTP:
    """Stubt main._http_delete für die Integrationstests."""

    def __init__(self, statuses=None):
        self._statuses = list(statuses or [])
        self.calls = []

    def __call__(self, origin_url, api_path, timeout=2.0):
        self.calls.append((origin_url, api_path))
        if self._statuses:
            return self._statuses.pop(0), b""
        return 200, b""


def _ec36_ctx(tmp_path, tg, provider, *, catalog=None, store=None,
              photo_origin="", essen_origin=""):
    """Context mit EC-36-Feldern."""
    return Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider,
        catalog=catalog if catalog is not None else Catalog(),
        history=History(str(tmp_path / "ec36.db")),
        pending=PendingStore(),
        a2_receipt_store=store,
        photo_origin_url=photo_origin,
        essen_origin_url=essen_origin,
    )


def test_EC_36_falsch_nach_a2_foto_loest_inverse_aus(tmp_path, monkeypatch):
    """AC1/AC2-Integration: handle_update verarbeitet »falsch« VOR dem Agenten;
    A2-Receipt löst HTTP DELETE aus, Quittung positiv, kein Provider-Call."""
    store = A2ReceiptStore(str(tmp_path / "rec.db"))
    chat_id = 42
    store.insert("foto_senden", chat_id, "med-7",
                 'photo DELETE /api/v1/photo/medien/med-7')

    tg = FakeTelegram(members=_members(7))
    # Provider darf NICHT gerufen werden — der Hook handelt allein.
    provider = FakeProvider([])
    ctx = _ec36_ctx(tmp_path, tg, provider, store=store,
                    photo_origin="http://127.0.0.1:5070")

    http = _StubHTTP(statuses=[200])
    monkeypatch.setattr(main_mod, "_http_delete", http)

    handle_update(make_message("falsch", chat_id=chat_id, from_user_id=7),
                  ctx)

    assert provider.requests == [], (
        "EC-36: »falsch« muss VOR dem Agenten greifen — kein Provider-Call.")
    assert http.calls == [
        ("http://127.0.0.1:5070", "/api/v1/photo/medien/med-7")]
    assert len(tg.sent) == 1
    assert "rückgängig" in tg.sent[0]["text"].lower()
    # Korrektur-State sichtbar für den Folge-Turn
    assert ctx.pending.get_correction(chat_id) is not None


def test_EC_36_falsch_nach_klasse_c_verwirft_pending(tmp_path):
    """AC1-Integration Klasse-C: »falsch« nach Pending verwirft den Vorschlag,
    Quittung „Vorschlag verworfen", kein Provider-Call."""
    write = FakeWriteTask(name="gericht_anlegen", summary="Pizza anlegen",
                          result="Pizza angelegt.")
    catalog = Catalog()
    catalog.register(write)

    tg = FakeTelegram(members=_members(7))
    # Schritt 1: ein Vorschlag entsteht (write_proposal-Flow).
    provider = FakeProvider([
        task_call_response("gericht_anlegen", arguments={"label": "Pizza"}),
        # Schritt 2 NICHT erwartet — »falsch« greift VOR dem Agenten.
    ])
    ctx = _ec36_ctx(tmp_path, tg, provider, catalog=catalog)

    handle_update(make_message("trag Pizza ein", message_id=100,
                               from_user_id=7), ctx)
    assert ctx.pending.open_count(42) == 1

    handle_update(make_message("falsch", message_id=101, from_user_id=7), ctx)

    # Pending verworfen
    assert ctx.pending.open_count(42) == 0
    # Quittung
    texts = [s["text"] for s in tg.sent]
    assert any("vorschlag verworfen" in t.lower() for t in texts)
    # Agent wurde nur EINMAL gerufen (für den ersten Vorschlag)
    assert len(provider.requests) == 1
    # Korrektur-State trägt Original-Skill + Args
    state = ctx.pending.get_correction(42)
    assert state is not None
    assert state.last_skill == "gericht_anlegen"
    assert state.last_args == {"label": "Pizza"}


def test_EC_36_re_propose_durchlaeuft_confirm_gate(tmp_path):
    """AC4 Re-Propose: nach »falsch« + Patch baut der Agent einen neuen
    Vorschlag, der IMMER durch das zweistufige Confirm-Gate geht — auch wenn
    der Original-Skill A2 war (spec Z. 1193-1201).

    Hier am Klasse-C-Beispiel: »falsch« → Patch → neuer Vorschlag → »ja«
    → Ausführung. Belegt damit, dass das System die Re-Propose-Form als
    normalen Pending-Pfad handhabt.
    """
    write = FakeWriteTask(name="gericht_anlegen", summary="Nudeln anlegen",
                          result="Nudeln angelegt.")
    catalog = Catalog()
    catalog.register(write)

    tg = FakeTelegram(members=_members(7))
    # Turn 1: erster Vorschlag (Pizza)
    # Turn 2 (nach »falsch« + Patch »Nudeln«): zweiter Vorschlag (Nudeln)
    provider = FakeProvider([
        task_call_response("gericht_anlegen", arguments={"label": "Pizza"},
                           call_id="c1"),
        task_call_response("gericht_anlegen", arguments={"label": "Nudeln"},
                           call_id="c2"),
    ])
    ctx = _ec36_ctx(tmp_path, tg, provider, catalog=catalog)

    # Schritt 1: »trag Pizza ein« → Vorschlag
    handle_update(make_message("trag Pizza ein", message_id=100,
                               from_user_id=7), ctx)
    assert ctx.pending.open_count(42) == 1
    assert write.execute_calls == []

    # Schritt 2: »falsch« → Vorschlag verworfen, Korrektur-State gesetzt
    handle_update(make_message("falsch", message_id=101, from_user_id=7), ctx)
    assert ctx.pending.open_count(42) == 0
    assert ctx.pending.get_correction(42) is not None

    # Schritt 3: Patch »Nudeln« → Agent baut neuen Vorschlag (Confirm-Gate)
    handle_update(make_message("Nudeln", message_id=102, from_user_id=7), ctx)
    # Korrektur-State nach dem Agent-Turn verbraucht
    assert ctx.pending.get_correction(42) is None
    # Neuer Vorschlag liegt vor
    assert ctx.pending.open_count(42) == 1
    proposal_msg_id = tg.sent[-1]["message_id"]
    # Noch nicht ausgeführt
    assert write.execute_calls == []

    # Schritt 4: »ja« als Antwort auf den neuen Vorschlag → Ausführung
    handle_update(make_message("ja", message_id=103, from_user_id=7,
                               reply_to_message_id=proposal_msg_id), ctx)
    # Re-Propose-Args wurden ausgeführt
    assert write.execute_calls == [{"label": "Nudeln"}]


def test_EC_36_falsch_nach_a2_provider_nicht_gerufen(tmp_path, monkeypatch):
    """Negativ-Probe: Der Hook fängt »falsch« VOR dem Agenten ab — also läuft
    der Provider auch dann nicht, wenn er skriptiert wäre."""
    store = A2ReceiptStore(str(tmp_path / "rec.db"))
    chat_id = 42
    store.insert("einkauf_hinzufuegen", chat_id, "item-1",
                 'essen DELETE /api/v1/essen/wuensche/item-1')

    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("DARF NICHT KOMMEN")])
    ctx = _ec36_ctx(tmp_path, tg, provider, store=store,
                    essen_origin="http://127.0.0.1:5052")

    monkeypatch.setattr(main_mod, "_http_delete", _StubHTTP(statuses=[200]))
    handle_update(make_message("falsch", chat_id=chat_id, from_user_id=7),
                  ctx)

    assert provider.requests == []
    assert "DARF NICHT KOMMEN" not in (tg.sent[0]["text"] if tg.sent else "")


def test_EC_36_falsch_ohne_vorgang_geht_an_agent(tmp_path):
    """»falsch« ohne A2-Receipt + ohne Pending → Hook gibt False, Agent läuft."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Was war falsch?")])
    # Kein store, kein pending — Hook ist no-op
    ctx = _ec36_ctx(tmp_path, tg, provider)

    handle_update(make_message("falsch", from_user_id=7), ctx)

    # Agent wurde gerufen
    assert len(provider.requests) == 1
    assert tg.sent[0]["text"] == "Was war falsch?"


# ============================================================
#  EC-36 Test-Implikationen 2/3/4 (spec Z. 1211-1224) +
#  Re-Propose-Gate-Pflicht für A2-Skills (FIX 1, Watchdog T844-S1-W)
# ============================================================


def test_EC_36_re_propose_auto_confirm_task_geht_durch_gate(tmp_path,
                                                             monkeypatch):
    """FIX 1 (Watchdog T844-S1-W, EC-36 spec Z. 1193-1201): Ein A2-Skill
    (auto_confirm=True) ruft im Korrektur-State NICHT direkt execute(),
    sondern läuft durch propose() — das Vertrauen aus der A2-Klausel ist
    nach »falsch« verbraucht.

    Reale Live-Drift, die der Patch schließt: einkauf_hinzufuegen
    (auto_confirm=True) hätte im Re-Propose nach »falsch + eigentlich
    Brötchen« sofort »Brötchen« geschrieben — der User hätte ihn ein
    zweites Mal mit »falsch« rückgängig machen müssen.
    """
    chat_id = 42
    # Auto-confirm-Schreibtask, der den »einkauf_hinzufuegen«-Charakter trägt.
    write = FakeWriteTask(name="einkauf_hinzufuegen",
                          summary="Brötchen auf die Liste",
                          result="Brötchen eingetragen.",
                          auto_confirm=True)
    catalog = Catalog()
    catalog.register(write)

    # A2-Receipt für den Ursprungs-Akt »Brot« — der »falsch«-Hook löst den
    # Inverse-Call aus und setzt den Korrektur-State.
    store = A2ReceiptStore(str(tmp_path / "rec.db"))
    store.insert("einkauf_hinzufuegen", chat_id, "item-brot",
                 'essen DELETE /api/v1/essen/wuensche/item-brot')

    tg = FakeTelegram(members=_members(7))
    # Provider antwortet im Korrektur-Folge-Turn mit dem Re-Aufruf des
    # auto_confirm-Skills (gepatchte Args »Brötchen«).
    provider = FakeProvider([
        task_call_response("einkauf_hinzufuegen",
                           arguments={"text": "Brötchen"}, call_id="c-re"),
    ])
    ctx = _ec36_ctx(tmp_path, tg, provider, catalog=catalog, store=store,
                    essen_origin="http://127.0.0.1:5052")

    monkeypatch.setattr(main_mod, "_http_delete", _StubHTTP(statuses=[200]))

    # Schritt 1: »falsch« nach A2-Akt → Korrektur-State gesetzt
    handle_update(make_message("falsch", message_id=200, from_user_id=7), ctx)
    assert ctx.pending.get_correction(chat_id) is not None
    # Provider wurde noch NICHT gerufen
    assert provider.requests == []

    # Schritt 2: Patch »eigentlich Brötchen« → Agent baut neuen Aufruf
    handle_update(make_message("eigentlich Brötchen", message_id=201,
                               from_user_id=7), ctx)

    # FIX 1 — execute() wurde NICHT direkt aufgerufen, obwohl auto_confirm=True
    assert write.execute_calls == [], (
        "EC-36 spec Z. 1193-1201: Re-Propose für A2-Skill (auto_confirm) "
        "muss durch das Confirm-Gate laufen — execute_calls darf leer sein.")
    # Stattdessen liegt ein propose-Vorschlag im Pending-Slot
    assert ctx.pending.open_count(chat_id) == 1
    assert write.propose_calls == [{"text": "Brötchen"}]
    # Korrektur-State nach dem Folge-Turn verbraucht
    assert ctx.pending.get_correction(chat_id) is None


def test_EC_36_impl2_re_propose_a2_durchlaeuft_gate(tmp_path, monkeypatch):
    """EC-36 spec Z. 1213-1217 Test-Implikation 2: A2-Pfad
    einkauf_hinzufuegen Sofort-Write von »Brot« → User »falsch« → Bot löscht
    und fragt »Was war falsch?« → User »eigentlich Brötchen« → Bot propose
    mit »Brötchen« (Confirm-Gate erzwungen) → User »ja« → Schreibakt grün.

    Subsumiert FIX 1, prüft aber auch den vollständigen ja-Pfad bis zum
    execute() nach der Bestätigung.
    """
    chat_id = 42
    write = FakeWriteTask(name="einkauf_hinzufuegen",
                          summary="Brötchen auf die Liste",
                          result="Brötchen eingetragen.",
                          auto_confirm=True)
    catalog = Catalog()
    catalog.register(write)

    store = A2ReceiptStore(str(tmp_path / "rec.db"))
    store.insert("einkauf_hinzufuegen", chat_id, "item-brot",
                 'essen DELETE /api/v1/essen/wuensche/item-brot')

    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([
        task_call_response("einkauf_hinzufuegen",
                           arguments={"text": "Brötchen"}, call_id="c-re"),
    ])
    ctx = _ec36_ctx(tmp_path, tg, provider, catalog=catalog, store=store,
                    essen_origin="http://127.0.0.1:5052")

    monkeypatch.setattr(main_mod, "_http_delete", _StubHTTP(statuses=[200]))

    # »falsch« → Korrektur-State
    handle_update(make_message("falsch", message_id=300, from_user_id=7), ctx)
    # Patch → propose statt sofort-execute
    handle_update(make_message("eigentlich Brötchen", message_id=301,
                               from_user_id=7), ctx)
    assert write.execute_calls == []
    assert ctx.pending.open_count(chat_id) == 1
    proposal_msg_id = tg.sent[-1]["message_id"]

    # »ja« als Reply auf den Vorschlag → execute() grün
    handle_update(make_message("ja", message_id=302, from_user_id=7,
                               reply_to_message_id=proposal_msg_id), ctx)
    assert write.execute_calls == [{"text": "Brötchen"}]


def test_EC_36_impl3_cross_skill_exit_versiegelt_correction(tmp_path):
    """EC-36 spec Z. 1219-1221 Test-Implikation 3 (Cross-Skill-Exit):
    termin_eintragen propose → »falsch« → User »lieber als Plan-Aktivität«
    → Bot startet plan_aktivitaeten_setzen, alter Korrektur-State versiegelt.

    Mechanisch: nach `_falsch_hook` ist der Korrektur-State gesetzt. Im
    Folge-Turn ruft der Agent einen ANDEREN Skill — main.py löscht den
    Korrektur-State NACH dem Agent-Lauf (genau-ein-Turn-Lebensdauer). Der
    neue Skill läuft durch seinen normalen Pfad.
    """
    chat_id = 42
    termin = FakeWriteTask(name="termin_eintragen",
                           summary="Sport Mo 17:00",
                           result="Termin eingetragen.")
    plan = FakeWriteTask(name="plan_aktivitaeten_setzen",
                         summary="Sport als Plan-Aktivität",
                         result="Plan-Aktivität gesetzt.")
    catalog = Catalog()
    catalog.register(termin)
    catalog.register(plan)

    tg = FakeTelegram(members=_members(7))
    # Turn 1: Termin-Vorschlag
    # Turn 2 (nach »falsch« + Cross-Skill): plan_aktivitaeten_setzen-Vorschlag
    provider = FakeProvider([
        task_call_response("termin_eintragen",
                           arguments={"titel": "Sport", "zeit": "Mo 17"},
                           call_id="t1"),
        task_call_response("plan_aktivitaeten_setzen",
                           arguments={"titel": "Sport"}, call_id="t2"),
    ])
    ctx = _ec36_ctx(tmp_path, tg, provider, catalog=catalog)

    # Schritt 1: Termin-Vorschlag entsteht
    handle_update(make_message("Sport Mo 17 eintragen", message_id=400,
                               from_user_id=7), ctx)
    assert ctx.pending.open_count(chat_id) == 1

    # Schritt 2: »falsch« → Pending verworfen, Korrektur-State zeigt auf termin_eintragen
    handle_update(make_message("falsch", message_id=401, from_user_id=7), ctx)
    state = ctx.pending.get_correction(chat_id)
    assert state is not None
    assert state.last_skill == "termin_eintragen"

    # Schritt 3: Cross-Skill — »lieber als Plan-Aktivität«
    handle_update(make_message("lieber als Plan-Aktivität", message_id=402,
                               from_user_id=7), ctx)
    # Alter Korrektur-State versiegelt (genau-ein-Turn-Lebensdauer)
    assert ctx.pending.get_correction(chat_id) is None
    # Neuer Skill lief durch seinen normalen Pfad — Vorschlag liegt vor,
    # NICHT mehr für termin_eintragen, sondern für plan_aktivitaeten_setzen
    assert ctx.pending.open_count(chat_id) == 1
    assert plan.propose_calls == [{"titel": "Sport"}]
    # Der alte Skill wurde im Cross-Skill-Turn nicht erneut aufgerufen
    assert termin.propose_calls == [{"titel": "Sport", "zeit": "Mo 17"}]


def test_EC_36_impl4_klasse_c_mehrere_iterationen(tmp_path):
    """EC-36 spec Z. 1223-1224 Test-Implikation 4: Klasse-C propose →
    »falsch« → Patch → propose → »falsch« → erneut Patch → propose → »ja«
    → grün.

    Geprüft wird, dass der Korrektur-Hook und der Confirm-Gate auch in
    mehreren Iterationen sauber zusammenspielen — jeder Iterations-Bon
    wird sauber verworfen, der Korrektur-State nach jedem Patch-Turn
    verbraucht, der finale »ja«-Pfad führt zum execute().
    """
    chat_id = 42
    write = FakeWriteTask(name="gericht_anlegen",
                          summary="Nudeln anlegen",
                          result="Nudeln angelegt.")
    catalog = Catalog()
    catalog.register(write)

    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([
        # Turn 1: erster Vorschlag (Pizza)
        task_call_response("gericht_anlegen", arguments={"label": "Pizza"},
                           call_id="c1"),
        # Turn 2 (nach »falsch« + Patch »Lasagne«): zweiter Vorschlag
        task_call_response("gericht_anlegen", arguments={"label": "Lasagne"},
                           call_id="c2"),
        # Turn 3 (nach erneutem »falsch« + Patch »Nudeln«): dritter Vorschlag
        task_call_response("gericht_anlegen", arguments={"label": "Nudeln"},
                           call_id="c3"),
    ])
    ctx = _ec36_ctx(tmp_path, tg, provider, catalog=catalog)

    # Iteration 1: Vorschlag → »falsch« → Patch → neuer Vorschlag
    handle_update(make_message("trag Pizza ein", message_id=500,
                               from_user_id=7), ctx)
    assert ctx.pending.open_count(chat_id) == 1
    handle_update(make_message("falsch", message_id=501, from_user_id=7), ctx)
    assert ctx.pending.get_correction(chat_id) is not None
    handle_update(make_message("Lasagne", message_id=502, from_user_id=7), ctx)
    assert ctx.pending.get_correction(chat_id) is None
    assert ctx.pending.open_count(chat_id) == 1
    assert write.execute_calls == []

    # Iteration 2: erneut »falsch« → Patch → dritter Vorschlag
    handle_update(make_message("falsch", message_id=503, from_user_id=7), ctx)
    assert ctx.pending.open_count(chat_id) == 0
    assert ctx.pending.get_correction(chat_id) is not None
    handle_update(make_message("Nudeln", message_id=504, from_user_id=7), ctx)
    assert ctx.pending.get_correction(chat_id) is None
    assert ctx.pending.open_count(chat_id) == 1
    proposal_msg_id = tg.sent[-1]["message_id"]
    assert write.execute_calls == []

    # Finale Bestätigung
    handle_update(make_message("ja", message_id=505, from_user_id=7,
                               reply_to_message_id=proposal_msg_id), ctx)
    assert write.execute_calls == [{"label": "Nudeln"}]


def test_EC_36_provider_error_clears_correction(tmp_path):
    """FIX 4 (Watchdog T844-S1-W, Befund 5): ProviderError im Korrektur-Folge-
    Turn versiegelt den Korrektur-State trotzdem (main.py Z. 506-509).

    Ohne diesen Cleanup würde der Korrektur-State doppelt zugespielt — der
    nächste User-Turn liefe mit altem Suffix in einen neuen Agent-Turn, der
    inhaltlich gar nicht zum Patch passt.
    """
    chat_id = 42
    write = FakeWriteTask(name="gericht_anlegen", summary="Pizza anlegen",
                          result="Pizza angelegt.")
    catalog = Catalog()
    catalog.register(write)

    tg = FakeTelegram(members=_members(7))
    # Turn 1: erster Vorschlag — sauber
    # Turn 2 (Patch nach »falsch«): Provider wirft
    provider = FakeProvider([
        task_call_response("gericht_anlegen", arguments={"label": "Pizza"},
                           call_id="c1"),
        ProviderError("Anbieter weg"),
    ])
    ctx = _ec36_ctx(tmp_path, tg, provider, catalog=catalog)

    # Schritt 1: Vorschlag → Pending
    handle_update(make_message("trag Pizza ein", message_id=600,
                               from_user_id=7), ctx)
    # Schritt 2: »falsch« → Korrektur-State gesetzt
    handle_update(make_message("falsch", message_id=601, from_user_id=7), ctx)
    assert ctx.pending.get_correction(chat_id) is not None

    # Schritt 3: Patch — Provider wirft, _PROVIDER_DOWN-Nachricht
    handle_update(make_message("Nudeln", message_id=602, from_user_id=7), ctx)

    # FIX 4 — Korrektur-State wurde im Provider-Down-Pfad versiegelt
    assert ctx.pending.get_correction(chat_id) is None
    # Der Provider-Down-Hinweis wurde gesendet
    assert any(_PROVIDER_DOWN in s["text"] for s in tg.sent)
