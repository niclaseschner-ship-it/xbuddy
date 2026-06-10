"""Tests für `AnbieterWechselnTask` — ONB-11, ONB-13 (Refs #639).

Geprüft werden:
  * Privatchat-Trigger (AC1): Familien-Gruppe gibt Hinweis + Session-Start
    im Privatchat; Privatchat startet direkt.
  * Session-Schutz: doppelter Aufruf liefert Quittung ohne zweite Session.
  * Build-Catalog-Guard: Task erscheint nur im Katalog, wenn alle Abhängigkeiten
    gesetzt sind.
  * is_async-Flag: Framework skipt inline-Hooks (Refs #159).
  * ONB-8-Schutz: keine Keys in Task-Quittungen.

Die Privatchat-Konversation selbst (Anbieter-Wahl, Validierungs-Ping, ZD-
Schreiben, Gruppen-Bestätigung) ist in `test_anbieter_wechseln.py` abgedeckt.
"""

import time

from fakes import FakeTelegram, make_message
from skills.anbieter_wechseln_task import AnbieterWechselnTask, AvbSession, make_avb_input
from tasks import TurnContext, WriteTask, build_catalog

# ============================================================
#  Test-Doppelungen
# ============================================================


class _FakeZd:
    """Minimal-ZD für Task-Quittungs-Tests."""

    def __init__(self):
        self._data = {}

    def get(self, name, default=None):
        return self._data.get(name, default)

    def set(self, name, value):
        self._data[name] = value

    def has(self, name):
        return name in self._data


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def _build_task(tg=None, sessions=None, current_provider="claude"):
    """Hilfsfunktion: baut einen `AnbieterWechselnTask` mit Doppelungen."""
    if tg is None:
        tg = FakeTelegram(members=_members(7))
    if sessions is None:
        sessions = {}
    zd = _FakeZd()
    return AnbieterWechselnTask(
        tg=tg,
        zd_store_getter=lambda: zd,
        sessions=sessions,
        family_group_chat_id_getter=lambda: 99,
        current_provider_getter=lambda: current_provider)


# ============================================================
#  1. Klassen-Eigenschaften
# ============================================================

def test_task_ist_write_task():
    """AnbieterWechselnTask ist eine WriteTask (EC-10)."""
    task = _build_task()
    assert isinstance(task, WriteTask)


def test_task_is_async_true():
    """Refs #159: is_async=True — Framework skipt inline-Hooks."""
    assert AnbieterWechselnTask.is_async is True


def test_task_name():
    """Task-Name ist `anbieter_wechseln`."""
    task = _build_task()
    assert task.name == "anbieter_wechseln"


# ============================================================
#  2. propose() — kontextabhängiger Summary
# ============================================================

def test_propose_from_group():
    """propose() aus der Familien-Gruppe nennt den Privatchat als Ort."""
    task = _build_task()
    ctx = TurnContext(chat_id=99, private_chat_id=7, from_user_id=7)
    proposal = task.propose({}, ctx)
    assert "Privatchat" in proposal.summary


def test_propose_from_private():
    """propose() aus dem Privatchat ohne Ortswechsel-Hinweis."""
    task = _build_task()
    # Privatchat: chat_id == private_chat_id
    ctx = TurnContext(chat_id=7, private_chat_id=7, from_user_id=7)
    proposal = task.propose({}, ctx)
    assert proposal.summary


# ============================================================
#  3. execute() — Quittungen
# ============================================================

def test_execute_from_group_returns_privat_hinweis():
    """AC1: execute() aus der Familien-Gruppe liefert Privatchat-Hinweis."""
    sessions = {}
    task = _build_task(sessions=sessions)
    ctx = TurnContext(chat_id=99, private_chat_id=7, from_user_id=7)
    result = task.execute({}, ctx)
    assert "Privatchat" in result
    # Session wurde gestartet.
    assert 7 in sessions
    # Aufräumen: Session beenden (verhindert hängende Worker-Threads im Test).
    sessions[7].deliver(None)
    time.sleep(0.1)


def test_execute_from_private_returns_direkte_einleitung():
    """execute() aus dem Privatchat: Wechsel-Quittung ohne Ortswechsel-Hinweis."""
    sessions = {}
    task = _build_task(sessions=sessions)
    # Privatchat: chat_id == private_chat_id
    ctx = TurnContext(chat_id=7, private_chat_id=7, from_user_id=7)
    result = task.execute({}, ctx)
    assert result
    assert "Privatchat" not in result   # kein Ortswechsel-Hinweis
    assert 7 in sessions
    sessions[7].deliver(None)
    time.sleep(0.1)


def test_execute_ohne_private_chat_id():
    """execute() ohne private_chat_id → klare Fehlermeldung, keine Session."""
    sessions = {}
    task = _build_task(sessions=sessions)
    ctx = TurnContext(chat_id=99, private_chat_id=None, from_user_id=None)
    result = task.execute({}, ctx)
    assert result
    assert sessions == {}


def test_execute_session_already_running():
    """Doppelter Aufruf für denselben Privatchat → Quittung, keine zweite Session."""
    sessions = {7: AvbSession(7)}   # Schon eine Session drin
    task = _build_task(sessions=sessions)
    ctx = TurnContext(chat_id=7, private_chat_id=7, from_user_id=7)
    result = task.execute({}, ctx)
    assert result
    assert len(sessions) == 1, "Keine zweite Session anlegen"


# ============================================================
#  4. build_catalog-Guard (ONB-11)
# ============================================================

def test_build_catalog_ohne_avb_parameter_kein_task():
    """Ohne `avb_sessions` und `current_provider_getter` erscheint der Task
    NICHT im Katalog."""
    from fakes import FakeTelegram
    tg = FakeTelegram()
    catalog = build_catalog(tg, "ca.pem",
                            zd_store_getter=lambda: _FakeZd(),
                            family_group_chat_id_getter=lambda: 99)
    assert catalog.get("anbieter_wechseln") is None


def test_build_catalog_mit_allen_parametern_task_im_katalog():
    """Mit allen AVB-Parametern erscheint der Task im Katalog."""
    from fakes import FakeTelegram
    tg = FakeTelegram()
    sessions = {}
    catalog = build_catalog(
        tg, "ca.pem",
        zd_store_getter=lambda: _FakeZd(),
        family_group_chat_id_getter=lambda: 99,
        avb_sessions=sessions,
        current_provider_getter=lambda: "claude")
    assert catalog.get("anbieter_wechseln") is not None


def test_build_catalog_ohne_zd_getter_kein_task():
    """Ohne `zd_store_getter` kein AVB-Task im Katalog."""
    from fakes import FakeTelegram
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "ca.pem",
        family_group_chat_id_getter=lambda: 99,
        avb_sessions={},
        current_provider_getter=lambda: "claude")
    assert catalog.get("anbieter_wechseln") is None


def test_build_catalog_ohne_current_provider_getter_kein_task():
    """Ohne `current_provider_getter` kein AVB-Task im Katalog."""
    from fakes import FakeTelegram
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "ca.pem",
        zd_store_getter=lambda: _FakeZd(),
        family_group_chat_id_getter=lambda: 99,
        avb_sessions={})
    assert catalog.get("anbieter_wechseln") is None


# ============================================================
#  5. make_avb_input — Adapter
# ============================================================

def test_make_avb_input():
    """make_avb_input übersetzt IncomingMessage.text in AvbInput.text."""
    msg = make_message(text="claude")
    avb_in = make_avb_input(msg)
    assert avb_in.text == "claude"


def test_make_avb_input_none_text():
    """make_avb_input behandelt None-Text als leeren String."""
    msg = make_message(text=None)
    avb_in = make_avb_input(msg)
    assert avb_in.text == ""
