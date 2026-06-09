"""Tests für TermineErfragenTask — TER-10, TER-11, EC-29, TASK-10 (Refs #143, #569).

Pflicht-Tests (Spec TER-11 + EC-29 + TASK-10):
- ReadTask-Kind (EC-9, kein Bestätigungs-Gate).
- Task-Name ist 'termine_erfragen'.
- Task delegiert korrekt an termine_erfragen und gibt
  Tool-Result-Text direkt zurück (EC-29 / TASK-10).
- TASK-10-Baseline: run() sendet in keinem Pfad selbst (EC-29).
- Katalog-Registrierung (AND-Guard, plan_origin_url).
"""

import contextlib
import os
import tempfile

import pytest
from fakes import FakeTelegram
from skills.plan_client import PlanClientError
from skills.termine_erfragen import BerechtigungError
from skills.termine_erfragen_task import TermineErfragenTask
from tasks import ReadTask, TurnContext, build_catalog

# ============================================================
#  Doppelungen
# ============================================================

class FakePlanClient:
    """Doppelung des PlanClients für Task-Tests."""

    def __init__(self, events=None, error=None):
        self._events = events if events is not None else []
        self._error = error
        self.calls = []

    def termine(self, ab, tage):
        self.calls.append((ab, tage))
        if self._error is not None:
            raise self._error
        return list(self._events)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _event(titel="Test", beginn="2026-06-01", ende="2026-06-02",
           ganztags=True, id="evt-1"):
    return {"id": id, "titel": titel, "beginn": beginn, "ende": ende,
            "ganztags": ganztags, "person": None}


def _make_task(events=None, error=None, is_member_fn=None):
    pc = FakePlanClient(events=events, error=error)
    return TermineErfragenTask(
        plan_client=pc,
        is_member_fn=is_member_fn or _immer_mitglied,
    ), pc


# ============================================================
#  Task-Klassifikation + Grundeigenschaften
# ============================================================

def test_TER10_ist_read_task():
    """TER-10 EC-9: TermineErfragenTask ist ein ReadTask (lesend)."""
    task, _ = _make_task(events=[_event()])
    assert isinstance(task, ReadTask)


def test_TER10_name():
    """TER-10: Task-Name ist 'termine_erfragen' (Catalog-Schlüssel)."""
    task, _ = _make_task()
    assert task.name == "termine_erfragen"


def test_TER10_hat_parameter_schema():
    """TER-10: die Aufgabe hat ein JSON-Schema für ihre Parameter."""
    task, _ = _make_task()
    params = task.parameters
    assert params["type"] == "object"
    assert "anfrage_text" in params["properties"]


# ============================================================
#  Task delegiert korrekt an Funktion — EC-29: Text direkt als Tool-Result
# ============================================================

def test_TER10_happy_path_gibt_text_zurueck():
    """TER-10 / EC-29: run() liefert tagesgruppierte Termin-Text."""
    task, pc = _make_task(events=[_event("Arzt")])
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert pc.calls
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Arzt" in result


def test_TER10_nicht_mitglied_wirft_exception():
    """TER-2 / EC-29: run() mit Nicht-Mitglied → BerechtigungError
    propagiert zum Agent-Loop (is_error-Pfad)."""
    task, pc = _make_task(is_member_fn=_kein_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=99)

    with pytest.raises(BerechtigungError):
        task.run({}, ctx)

    assert pc.calls == []


def test_TER10_leer_gibt_text_zurueck():
    """TER-8 / EC-29: leerer Zeitraum → Text-Meldung direkt als Tool-Result."""
    task, pc = _make_task(events=[])
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert pc.calls
    assert isinstance(result, str)
    assert len(result) > 0
    assert "keine" in result.lower() or "stehen" in result.lower()


def test_TER10_nicht_erreichbar_gibt_text_zurueck():
    """TER-7 / EC-29: Plan-Buddy nicht erreichbar → Text-Meldung direkt als Tool-Result."""
    task, pc = _make_task(error=PlanClientError("Connection refused"))
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "erreichbar" in result.lower() or "Wochenplan" in result


def test_TER10_zielchat_aus_turn_context():
    """TER-3/TER-10: Zielchat kommt aus TurnContext, nicht aus arguments.

    EC-29: Task sendet nichts — result ist direkt der Tool-Result-String.
    """
    task, pc = _make_task(events=[_event("X")])
    ctx = TurnContext(chat_id=55555, from_user_id=7)

    result = task.run({}, ctx)

    # Ergebnis ist der Termin-Text (enthält "X")
    assert "X" in result


def test_TER10_anfrage_text_wird_weitergegeben():
    """run() leitet den anfrage_text an die Funktion weiter (TER-4)."""
    task, pc = _make_task(events=[_event("Arzt", beginn="2026-06-02",
                                          ende="2026-06-03")])
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({"anfrage_text": "morgen"}, ctx)

    # 'morgen' → tage=1 (Uhrzeit-sensitiv, nur tage prüfen)
    assert pc.calls
    assert pc.calls[0][1] == 1


def test_TER10_rueckfrage_mehrdeutig_gibt_text_zurueck():
    """TER-4 EC-22 / EC-29: mehrdeutiger Zeitraum → Rückfrage-Text als Tool-Result."""
    task, pc = _make_task(events=[])
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"anfrage_text": "nächsten Freitag"}, ctx)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "?" in result
    assert pc.calls == [], "Kein Plan-Buddy-Aufruf bei Rückfrage (TER-4)"


# ============================================================
#  TASK-10-Baseline: run() sendet in keinem Pfad selbst
# ============================================================

def test_TASK10_baseline_run_sendet_nichts():
    """TASK-10 / EC-29 Baseline-Test: task.run() sendet in keinem der
    vier Haupt-Pfade selbst an Telegram.

    Happy + Leer + Transport-Fehler: returnter String ist nicht-leer
    (EC-29: Task gibt Tool-Result zurück, sendet nicht selbst).

    Rückfrage-mehrdeutig: returnter String ist nicht-leer.

    Berechtigungs-Pfad: BerechtigungError propagiert.
    """
    ctx = TurnContext(chat_id=42, from_user_id=7)

    # --- Happy-Path ---
    task_happy, _ = _make_task(events=[
        _event("Zahnarzt", beginn="2026-06-01", id="e1"),
        _event("Sport", beginn="2026-06-03T15:00:00", ganztags=False, id="e2"),
    ])

    result_happy = task_happy.run({}, ctx)

    assert isinstance(result_happy, str), "Happy: Tool-Result muss ein String sein"
    assert len(result_happy) > 0, "Happy: Tool-Result muss nicht-leer sein"

    # --- Leer-Pfad ---
    task_leer, _ = _make_task(events=[])

    result_leer = task_leer.run({}, ctx)

    assert isinstance(result_leer, str), "Leer: Tool-Result muss ein String sein"
    assert len(result_leer) > 0, "Leer: Tool-Result muss nicht-leer sein"

    # --- Transport-Fehler-Pfad ---
    task_err, _ = _make_task(error=PlanClientError("Timeout"))

    result_err = task_err.run({}, ctx)

    assert isinstance(result_err, str), "Fehler: Tool-Result muss ein String sein"
    assert len(result_err) > 0, "Fehler: Tool-Result muss nicht-leer sein"

    # --- Rückfrage-Pfad (mehrdeutig) ---
    task_rq, pc_rq = _make_task(events=[])

    result_rq = task_rq.run({"anfrage_text": "nächsten Dienstag"}, ctx)

    assert isinstance(result_rq, str), "Rückfrage: Tool-Result muss ein String sein"
    assert len(result_rq) > 0, "Rückfrage: Tool-Result muss nicht-leer sein"
    assert pc_rq.calls == [], "Rückfrage: kein Plan-Buddy-Aufruf"

    # --- Berechtigungs-Pfad ---
    task_auth, pc_auth = _make_task(events=[], is_member_fn=_kein_mitglied)

    with pytest.raises(BerechtigungError):
        task_auth.run({}, ctx)

    assert pc_auth.calls == [], \
        "Berechtigungs-Fehler: kein API-Aufruf (TER-2)"


# ============================================================
#  Catalog-Registrierung (AND-Guard, TER-10) — plan_origin_url
# ============================================================

def _ca_pem():
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_TER10_guard_plan_origin_registriert():
    """TER-10: Task erscheint im Katalog wenn plan_origin_url gesetzt ist."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            plan_origin_url="http://127.0.0.1:5020",
        )
        task = catalog.get("termine_erfragen")
        assert task is not None
        assert isinstance(task, ReadTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_TER10_guard_ohne_plan_origin_nicht_registriert():
    """TER-10 Guard: ohne plan_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
        )
        assert catalog.get("termine_erfragen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)
