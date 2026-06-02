"""Tests für die Orchestrierung — EC-2/EC-3/EC-5/EC-10/EC-14 (Refs #27).
Enthält auch poll_loop-Tests (#294): Backoff bei leeren/fehlgeschlagenen
getUpdates-Aufrufen und Latenz-Instrumentierung (LOG-4).

Geprüft wird `handle_update` und `poll_loop`: das Zusammenspiel der
Sicherheits-Gates mit dem Agenten. Telegram-Kanal und KI-Anbieter sind
kontrollierte Doppelungen (EC-17).
"""

import logging

from confirm import PendingStore
from fakes import (FakeProvider, FakeReadTask, FakeTelegram, FakeWriteTask,
                   make_message, task_call_response, text_response)
from history import History
from main import Context, handle_update, poll_loop
from main import _PROVIDER_DOWN
from model import ProviderError
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
    liefert und nach Erschöpfung _StopAfterN wirft (zum kontrollierten Beenden
    von poll_loop in Tests).

    `sleep_calls` zeichnet alle time.sleep-Aufrufe auf, die der poll_loop
    durch den monkeypatched time.sleep abgesetzt hat.
    """

    def __init__(self, responses):
        """responses: Liste von — [] (leer), [update-dict] oder TelegramError."""
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


def test_backoff_grows_on_empty_polls(tmp_path, monkeypatch):
    """AC3 (#294, E-EC-2-Verfeinerung): Aufeinanderfolgende leere getUpdates-
    Antworten führen zu exponentiell wachsenden sleep-Pausen.

    Erwarteter Ablauf (Start=1, Faktor=2):
      - Poll 1 → leer → sleep(1)
      - Poll 2 → leer → sleep(2)
      - Poll 3 → leer → sleep(4)
      - Poll 4 → _StopAfterN beendet den Loop

    Der Long-Poll-timeout-Parameter (Sekunden, die Telegram wartet) ist davon
    unberührt — er bleibt auf dem Default (30 s in get_updates).
    """
    sleep_calls = []
    monkeypatch.setattr("main.time.sleep", lambda s: sleep_calls.append(s))

    responses = [[], [], [], TelegramError("stop")]
    tg = _FakeTelegramPoll(responses)
    ctx = _poll_ctx(tmp_path, tg)

    try:
        poll_loop(ctx, get_updates_timeout=30)
    except (TelegramError, _StopAfterN):
        pass

    # Drei leere Polls → Backoff-Pausen 1, 2, dann Fehler mit Backoff 1
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
    ctx = _poll_ctx(tmp_path, tg)

    try:
        poll_loop(ctx, get_updates_timeout=30)
    except (TelegramError, _StopAfterN, Exception):
        pass

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
    ctx = _poll_ctx(tmp_path, tg)

    try:
        poll_loop(ctx, get_updates_timeout=30)
    except (TelegramError, _StopAfterN, Exception):
        pass

    assert sleep_calls, "poll_loop muss bei leeren Polls schlafen"
    assert max(sleep_calls) <= 5, (
        "Backoff-Cap ist 5 s — kein Sleep darf darüber liegen. "
        "Max: %s, alle sleeps: %s" % (max(sleep_calls), sleep_calls))


def test_pickup_latency_logged_on_updates(tmp_path, monkeypatch, caplog):
    """AC4 (#294, LOG-4): Wenn Updates eingetroffen sind, wird die familienseitige
    Pickup-Latenz als INFO-Eintrag geloggt (event=pickup_latency count=N latency_ms=X).

    Abgrenzung zu EC-23-Provider-Latenz: dieser Log-Eintrag misst die Zeit von
    getUpdates-Rückkehr bis Ende der Verarbeitung des Batches, NICHT die
    LLM-Provider-Latenz innerhalb eines Turns.
    """
    monkeypatch.setattr("main.time.sleep", lambda s: None)

    update = {"update_id": 200}
    # Ein Update-Batch, dann stop.
    responses = [[update], _StopAfterN("stop")]
    tg = _FakeTelegramPoll(responses)
    ctx = _poll_ctx(tmp_path, tg)

    with caplog.at_level(logging.INFO, logger="root"):
        try:
            poll_loop(ctx, get_updates_timeout=30)
        except (TelegramError, _StopAfterN, Exception):
            pass

    info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert any(
        "pickup_latency" in m and "count=" in m and "latency_ms=" in m
        for m in info_messages
    ), (
        "AC4 (#294): Erwartet INFO-Log mit 'event=pickup_latency count=N latency_ms=X'. "
        "Gefunden: %s" % info_messages
    )
