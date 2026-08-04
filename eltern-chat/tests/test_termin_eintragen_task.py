"""Tests für TermineEintragenTask und Catalog-Registrierung (TES-10, Refs #144).

Analog `test_kalender_verbinden_task.py`:
- WriteTask-Prüfung: is_async, propose(), Quittungstext.
- Catalog-Probe: TermineEintragenTask ist via build_catalog registrierbar.
- AND-Guard: task erscheint nur wenn plan_origin_url UND family_group_chat_id_getter.

Seit T144-IMPL-S2: handle_update-Routing-Test (AC2) prüft, dass eingehende
Privatchat-Nachrichten an eine laufende TES-Session geleitet werden —
analog FAA-12 (test_familie_anlegen_task.py Z.253-300).
"""

import time
from datetime import date

from confirm import PendingStore
from fakes import FakePlanClient, FakeProvider, FakeTelegram, make_message
from history import History
from main import Context, handle_update
from skills.termin_eintragen_task import (
    TermineEintragenTask,
    TesInput,
    TesSession,
    make_tes_input,
)
from tasks import Proposal, TurnContext, WriteTask, build_catalog

# ============================================================
#  Hilfs-Bausteine
# ============================================================

def _family_getter(fgcid=200):
    return lambda: fgcid


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def _make_task(sessions=None, plan_client=None, tg=None,
               family_group_chat_id_getter=None):
    if sessions is None:
        sessions = {}
    if plan_client is None:
        plan_client = FakePlanClient()
    if tg is None:
        tg = FakeTelegram(members=_members(42))
    if family_group_chat_id_getter is None:
        family_group_chat_id_getter = _family_getter()
    return TermineEintragenTask(
        tg=tg,
        plan_client=plan_client,
        sessions=sessions,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=lambda uid: True,  # für Task-Tests immer erlaubt
    )


# ============================================================
#  TES-10 — WriteTask-Klassifikation
# ============================================================

def test_TES10_ist_write_task():
    """TES-10: TermineEintragenTask ist ein WriteTask (EC-10)."""
    task = _make_task()
    assert isinstance(task, WriteTask)


def test_TES10_name():
    """TES-10: Task-Name ist 'termin_eintragen' (Catalog-Schlüssel)."""
    task = _make_task()
    assert task.name == "termin_eintragen"


def test_TES10_is_async():
    """TES-10: is_async=True — Worker-Thread läuft, Hooks nicht inline (Refs #159)."""
    task = _make_task()
    assert task.is_async is True


def test_TES10_keine_post_execute_hooks():
    """TES-10: TermineEintragenTask deklariert keine post_execute_hooks
    (Plan-Buddy hat keinen In-Memory-Cache für Einzel-Events)."""
    task = _make_task()
    assert task.post_execute_hooks == ()


# ============================================================
#  TES-10 — propose()
# ============================================================

def test_TES10_propose_liefert_proposal():
    """TES-10: propose() liefert ein Proposal-Objekt mit nicht-leerem summary."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    proposal = task.propose({}, ctx)
    assert isinstance(proposal, Proposal)
    assert proposal.summary


# ============================================================
#  TES-10 / EC-10 #266 — Vorschlag ist kontextabhängig
# ============================================================

def test_TES266_propose_from_group_nennt_privatchat():
    """EC-10 #266: aus der Familien-Gruppe gestartet → Vorschlag nennt
    den Privatchat als Ort der Klärung (chat_id != private_chat_id)."""
    task = _make_task()
    ctx = TurnContext(chat_id=200, from_user_id=42, private_chat_id=42)
    proposal = task.propose({}, ctx)
    assert isinstance(proposal, Proposal)
    assert "Privatchat" in proposal.summary


def test_TES266_propose_from_privatchat_kein_wechselhinweis():
    """EC-10 #266: schon im Privatchat gestartet → Vorschlag ohne
    Ortswechsel-Hinweis (chat_id == private_chat_id)."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    proposal = task.propose({}, ctx)
    assert isinstance(proposal, Proposal)
    assert "Privatchat" not in proposal.summary
    assert proposal.summary  # Nicht leer


# ============================================================
#  TES-10 — execute() Quittungstext
# ============================================================

def test_TES10_execute_aus_gruppe_quittung():
    """TES-10/EC-20: aus der Familien-Gruppe gestartet → Privatchat-Wechsel-Quittung."""
    sessions = {}
    task = _make_task(sessions=sessions)
    ctx = TurnContext(chat_id=200, from_user_id=42, private_chat_id=42)
    quittung = task.execute({"anstos_text": "Klettern Donnerstag"}, ctx)
    # Soll Privatchat erwähnen
    assert quittung
    assert isinstance(quittung, str)
    # Session wurde gestartet
    assert 42 in sessions
    # Cleanup: Session als beendet markieren
    sessions.pop(42, None)


def test_TES10_execute_aus_privatchat_quittung():
    """TES-10: aus dem Privatchat gestartet → direkte Einleitungs-Quittung."""
    sessions = {}
    task = _make_task(sessions=sessions)
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    quittung = task.execute({"anstos_text": "Klettern Donnerstag"}, ctx)
    assert quittung
    assert isinstance(quittung, str)
    sessions.pop(42, None)


def test_TES10_execute_kein_private_chat():
    """TES-10: kein Privatchat → keine Session, Hinweis-Quittung."""
    task = _make_task()
    ctx = TurnContext(chat_id=200, from_user_id=None, private_chat_id=None)
    quittung = task.execute({}, ctx)
    assert "Privatchat" in quittung or "privat" in quittung.lower()


def test_TES10_execute_session_laeuft_schon():
    """TES-10: läuft bereits eine Session in diesem Privatchat → Hinweis."""
    sessions = {42: object()}  # simulierter laufender Session-Eintrag
    task = _make_task(sessions=sessions)
    ctx = TurnContext(chat_id=200, from_user_id=42, private_chat_id=42)
    quittung = task.execute({}, ctx)
    assert quittung
    # Keine neue Session gestartet
    assert isinstance(sessions[42], object)  # alter Eintrag bleibt


# ============================================================
#  TES-10 — Catalog-Registrierung (AND-Guard)
# ============================================================

def test_TES10_registriert_wenn_plan_und_fgcid():
    """TES-10 AC4: TermineEintragenTask erscheint im Catalog, wenn plan_origin_url
    UND family_group_chat_id_getter gesetzt sind."""
    import os
    import tempfile
    ca_pem = tempfile.mktemp(suffix=".pem")
    # CA-PEM-Datei muss existieren für CaVerteilungTask.
    try:
        with open(ca_pem, "w") as f:
            f.write("fake-pem")
        tg = FakeTelegram()
        catalog = build_catalog(
            tg=tg,
            ca_pem_path=ca_pem,
            plan_origin_url="http://127.0.0.1:5020",
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("termin_eintragen")
        assert task is not None, "TermineEintragenTask sollte im Catalog sein"
        assert isinstance(task, WriteTask)
    finally:
        try:
            os.unlink(ca_pem)
        except OSError:
            pass


def test_TES10_nicht_registriert_ohne_plan_origin():
    """AC4: ohne plan_origin_url kein TermineEintragenTask im Catalog."""
    import os
    import tempfile
    ca_pem = tempfile.mktemp(suffix=".pem")
    try:
        with open(ca_pem, "w") as f:
            f.write("fake-pem")
        tg = FakeTelegram()
        catalog = build_catalog(
            tg=tg,
            ca_pem_path=ca_pem,
            # plan_origin_url fehlt
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("termin_eintragen")
        assert task is None, "Ohne plan_origin_url darf kein TermineEintragenTask registriert sein"
    finally:
        try:
            os.unlink(ca_pem)
        except OSError:
            pass


def test_TES10_nicht_registriert_ohne_fgcid():
    """AC4: ohne family_group_chat_id_getter kein TermineEintragenTask im Catalog."""
    import os
    import tempfile
    ca_pem = tempfile.mktemp(suffix=".pem")
    try:
        with open(ca_pem, "w") as f:
            f.write("fake-pem")
        tg = FakeTelegram()
        catalog = build_catalog(
            tg=tg,
            ca_pem_path=ca_pem,
            plan_origin_url="http://127.0.0.1:5020",
            # family_group_chat_id_getter fehlt
        )
        task = catalog.get("termin_eintragen")
        assert task is None, "Ohne family_group_chat_id_getter darf kein TermineEintragenTask registriert sein"
    finally:
        try:
            os.unlink(ca_pem)
        except OSError:
            pass


# ============================================================
#  make_tes_input
# ============================================================

def test_make_tes_input():
    """make_tes_input übersetzt IncomingMessage in TesInput (TES-3-Adapter)."""
    from telegram import IncomingMessage
    msg = IncomingMessage(
        update_id=1, chat_id=42, chat_type="private", message_id=10,
        from_user_id=7, from_user_name="test", text="Klettern Donnerstag",
        images=[], reply_to_message_id=None, reply_to_from_bot=False,
        mentions_bot=False)
    tes_input = make_tes_input(msg)
    assert tes_input.text == "Klettern Donnerstag"


# ============================================================
#  TesSession
# ============================================================

def test_TesSession_prefix():
    """TesSession hat den richtigen Thread-Namen-Präfix und Logging-Präfix."""
    session = TesSession(chat_id=42)
    assert TesSession.THREAD_NAME_PREFIX == "tes"
    assert TesSession.LOG_PREFIX == "TES"


# ============================================================
#  TES-3 / AC2 — handle_update routet Privatchat-Nachrichten an TES-Session
# ============================================================

def _ctx_with_tes_session(tmp_path, tg, tes_sessions,
                           family_group_chat_id="-100"):
    """Minimaler Context für den handle_update-Routing-Test (TES-3, AC2).

    Analog `_ctx` in `test_familie_anlegen_task.py` (Z.35-58): Context hat
    eine tes_sessions-Map, damit handle_update eingehende Privatchat-Updates
    an die laufende Session leiten kann.
    """
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        plan_origin_url="http://test-plan",
        family_group_chat_id_getter=lambda: family_group_chat_id,
        tes_sessions=tes_sessions,
    )
    return Context(
        tg=tg,
        bot_username="mybot",
        family_group_chat_id=family_group_chat_id,
        context_depth=20,
        provider=FakeProvider([]),
        catalog=catalog,
        history=History(str(tmp_path / "tes_routing.db")),
        pending=PendingStore(),
        tes_sessions=tes_sessions,
    )


def test_handle_update_routes_to_tes_session(tmp_path):
    """TES-3 / AC2: läuft eine TES-Session in einem Privatchat, gehen eingehende
    Privatchat-Updates dorthin (statt zum Agenten) — analog FAA-12.

    Prüft: handle_update ruft session.deliver() auf, wenn eine aktive TES-Session
    für den eingehenden chat_id existiert. Die Nachricht landet NICHT beim Agenten
    (FakeProvider bleibt ohne Aufruf).
    """
    user_id = 42
    tg = FakeTelegram(members={user_id: {"status": "member"}})
    tes_sessions = {}
    ctx = _ctx_with_tes_session(tmp_path, tg, tes_sessions)

    # Session manuell starten: eine TesSession in die Map eintragen.
    session = TesSession(chat_id=user_id)
    tes_sessions[user_id] = session

    # Eingabe aufzeichnen, die via deliver() ankommt.
    delivered = []

    def _run():
        msg = session.next_message()
        if msg is not None:
            delivered.append(msg)

    session.start(_run, ())
    # Warten, bis der Worker-Thread auf next_message() blockiert.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not session._queue is not None:
        time.sleep(0.01)
    time.sleep(0.05)  # Worker ist nun in next_message() blockiert.

    # handle_update aufrufen — Privatchat-Nachricht von user_id.
    msg = make_message("Klettern Donnerstag",
                       chat_id=user_id, from_user_id=user_id,
                       chat_type="private", message_id=200)
    handle_update(msg, ctx)

    # Warten, bis deliver() die Nachricht verarbeitet hat.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not delivered:
        time.sleep(0.01)

    assert delivered, (
        "handle_update hätte die Privatchat-Nachricht an tes_sessions[%s].deliver() "
        "leiten müssen — stattdessen wurde sie nicht an die Session zugestellt" % user_id)
    assert delivered[0].text == "Klettern Donnerstag"
    # Session wird nach _run() aus der Map entfernt — kein Agent-Aufruf.
    assert not tg.sent, "Der Agent hätte bei laufender TES-Session nicht antworten dürfen"


# ============================================================
#  T280-S1-W — Smoke-Test: run_tes baut typing_fn-Lambda korrekt
# ============================================================

# Festes Montag-Datum, damit "Klettern Donnerstag" sauber zu Datum 04.06.2026 auflöst.
_MONTAG = date(2026, 6, 1)

# Bekannte IDs für den Anti-Off-by-one-Beweis.
_PRIVATE_CHAT_ID  = 42
_FAMILY_GROUP_ID  = 200


def test_T280_S1W_run_tes_typing_fn_uses_private_chat_id(tmp_path):
    """T280-S1-W / AC1+AC2: run_tes() baut typing_fn-Lambda korrekt — sendet
    send_chat_action an private_chat_id (42), NICHT an family_group_chat_id (200).

    Smoke-Test für den Live-Pfad execute() → run_tes() → termin_eintragen():
    Die Closure in termin_eintragen_task.py (Z.195-196) bindet private_chat_id
    aus dem TurnContext — dieser Test prüft, dass die richtige ID durchgereicht
    wird, nicht versehentlich family_group_chat_id.

    Sequenz: Datum+Titel im Anstoß-Text bekannt → einzige next_message-Runde
    ist die TES-7-Bestätigungs-Frage → deliver("ok") → Session fertig.
    """
    sessions = {}
    tg = FakeTelegram(members={_PRIVATE_CHAT_ID: {"status": "member"}})
    plan_client = FakePlanClient(put_event_id="evt-smoke-t280")
    task = TermineEintragenTask(
        tg=tg,
        plan_client=plan_client,
        sessions=sessions,
        family_group_chat_id_getter=lambda: _FAMILY_GROUP_ID,
        is_member_fn=lambda uid: True,
    )

    # execute() aus der Familien-Gruppe aufgerufen: private_chat_id != chat_id.
    ctx = TurnContext(
        chat_id=_FAMILY_GROUP_ID,
        from_user_id=_PRIVATE_CHAT_ID,
        private_chat_id=_PRIVATE_CHAT_ID,
    )
    # Datum und Titel sind im Anstoß-Text eindeutig bekannt (TES-5/TES-4):
    # "Klettern Donnerstag" → Titel="Klettern", Tag=04.06.2026 (nächster Donnerstag ab Montag).
    # Daher braucht run_tes nur EINE User-Antwort: die TES-7-Bestätigung.
    quittung = task.execute({"anstos_text": "Klettern Donnerstag"}, ctx)
    assert quittung  # EC-20: Quittung nicht leer

    # Session muss in der Map sein (run_tes läuft im Worker-Thread).
    assert _PRIVATE_CHAT_ID in sessions, (
        "execute() hätte sessions[%s] anlegen müssen" % _PRIVATE_CHAT_ID)
    session = sessions[_PRIVATE_CHAT_ID]

    # Einen kleinen Moment warten, damit der Worker-Thread in next_message()
    # blockiert (er läuft asynchron im Daemon-Thread — kurze Settle-Zeit).
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not session._queue is not None:
        time.sleep(0.01)
    time.sleep(0.05)

    # TES-7-Bestätigung einliefern: "ok" bestätigt den Vorschlag.
    session.deliver(TesInput(text="ok"))

    # Warten, bis der Worker-Thread fertig ist (Session aus der Map entfernt).
    session._finished.wait(timeout=3.0)
    assert session.is_finished(), (
        "Worker-Thread von run_tes() hätte nach 'ok'-Bestätigung fertig sein müssen")

    # AC1: send_chat_action wurde mindestens einmal aufgerufen.
    assert tg.chat_actions, (
        "tg.send_chat_action wurde kein einziges Mal aufgerufen — "
        "typing_fn-Lambda in run_tes() scheint nicht zu feuern")

    typing_private = [
        a for a in tg.chat_actions
        if a["chat_id"] == _PRIVATE_CHAT_ID and a["action"] == "typing"
    ]
    typing_group = [
        a for a in tg.chat_actions
        if a["chat_id"] == _FAMILY_GROUP_ID
    ]

    # AC1: mindestens ein Typing-Aufruf an den Privatchat.
    assert typing_private, (
        "Kein send_chat_action(chat_id=%s, action='typing') gefunden. "
        "Alle aufgezeichneten Aufrufe: %r" % (_PRIVATE_CHAT_ID, tg.chat_actions))

    # AC2: KEIN Typing-Aufruf an die Familien-Gruppe (Anti-Off-by-one).
    assert not typing_group, (
        "send_chat_action wurde an family_group_chat_id=%s gesendet — "
        "typing_fn-Lambda schließt falsche ID ein. Aufrufe: %r"
        % (_FAMILY_GROUP_ID, tg.chat_actions))


# ============================================================
#  Unit-Tests: skills/typing_indicator.fire_typing (EC-25, T285a)
# ============================================================

from skills.typing_indicator import fire_typing  # noqa: E402 — nach Klassen-Defs


def test_fire_typing_ruft_callable_auf():
    """EC-25: fire_typing ruft den übergebenen Callable genau einmal auf."""
    calls = []
    fire_typing(lambda: calls.append(1))
    assert calls == [1]


def test_fire_typing_none_ist_noop():
    """EC-25: fire_typing mit None → kein Fehler, kein Aufruf."""
    fire_typing(None)  # kein Exception erwartet


def test_fire_typing_schluckt_exception():
    """EC-25: fire_typing schluckt jede Exception — kein Abbruch der aufrufenden Aufgabe."""
    def kaputt():
        raise RuntimeError("Telegram-Fehler simuliert")

    fire_typing(kaputt)  # darf nicht weitergeworfen werden
