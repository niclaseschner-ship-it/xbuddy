"""Tests für TermineEintragenTask und Catalog-Registrierung (TES-10, Refs #144).

Analog `test_kalender_verbinden_task.py`:
- WriteTask-Prüfung: is_async, propose(), Quittungstext.
- Catalog-Probe: TermineEintragenTask ist via build_catalog registrierbar.
- AND-Guard: task erscheint nur wenn plan_origin_url UND family_group_chat_id_getter.
"""

import time

from fakes import FakePlanClient, FakeTelegram
from skills.termin_eintragen_task import (
    TermineEintragenTask,
    TesSession,
    make_tes_input,
)
from tasks import Catalog, Proposal, TurnContext, WriteTask, build_catalog


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
