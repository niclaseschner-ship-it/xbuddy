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
from skills._errors import BerechtigungError
from skills.plan_client import PlanClientError
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


# ============================================================
#  TER-9 / TASK-10 — Wortwörtlich-Klausel (EC-29, EC-12 Trust-Sicherheit)
# ============================================================

def test_TER9_description_traegt_wortwoertlich_klausel():
    """TER-9 / TASK-10: Die description der TermineErfragenTask trägt die
    Wortwörtlich-Klausel — damit das LLM den Termin-Listen-Block 1:1
    übernimmt (keine Umsortierung, keine ausgelassenen Termine, EC-12).
    """
    task, _ = _make_task()
    desc = task.description
    assert "wortwörtlich" in desc.lower(), (
        "description enthält nicht 'wortwörtlich' (TER-9/TASK-10)")
    assert "tool-result" in desc.lower(), (
        "description enthält nicht 'aus dem Tool-Result' (TER-9/TASK-10)")


def test_TER9_e2e_listen_block_im_tool_result():
    """TER-9 E2E: task.run() liefert den tagesgruppiert-formatierten
    Listen-Block mit Wochentag-Köpfen und einer Zeile je Termin — 1:1
    aus formatiere_termine(), kein LLM (EC-12 Anbieter-Sicherheit).

    Die Ereignisse starten ab heute + 1 Tag, damit sie unabhängig vom
    Wochentag des Testtags ins Default-7-Tage-Fenster fallen. `expected`
    wird aus derselben `formatiere_termine`-Funktion berechnet, die auch
    `task.run()` intern nutzt — so ist der Test date-unabhängig.
    """
    from datetime import date, timedelta

    from skills.termine_erfragen import formatiere_termine

    heute = date.today()
    tag0 = heute                          # Default-Pfad: start = heute, tage = 7
    tag1 = heute + timedelta(days=1)      # zweiter Tag im Fenster
    tag2 = heute + timedelta(days=2)      # dritter Tag im Fenster

    events = [
        # Ganztägiger Termin am ersten Tag
        {"id": "e1", "titel": "Zahnarzt",
         "beginn": tag0.isoformat(), "ende": (tag0 + timedelta(days=1)).isoformat(),
         "ganztags": True, "person": None},
        # Termin mit Uhrzeit am zweiten Tag
        {"id": "e2", "titel": "Sport",
         "beginn": tag1.isoformat() + "T15:00:00",
         "ende": tag1.isoformat() + "T16:00:00",
         "ganztags": False, "person": None},
        # Mehrtages-Spanne ab drittem Tag (id="e3", darf nur einmal erscheinen)
        {"id": "e3", "titel": "Urlaub",
         "beginn": tag2.isoformat(), "ende": (tag2 + timedelta(days=2)).isoformat(),
         "ganztags": True, "person": None},
    ]

    pc = FakePlanClient(events=events)
    task = TermineErfragenTask(plan_client=pc, is_member_fn=_immer_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"anfrage_text": ""}, ctx)

    # Das Ergebnis muss exakt dem aus formatiere_termine entsprechen
    expected = formatiere_termine(events, tag0, 7)
    assert result == expected, (
        "Tool-Result weicht vom erwarteten Listen-Block ab — "
        "TER-9 verlangt 1:1-Übernahme (keine Umsortierung, EC-12)")

    # Wochentag-Köpfe im korrekten Format (*Wochentag, DD.MM.*)
    # Wochentagnamen sind deterministisch aus expected ableitbar (TER-9/URL-7)
    assert "*" in result, "Kein Tages-Kopf im Format *Wochentag, DD.MM.* gefunden"
    assert "," in result, "Kein Komma in Tages-Kopf (Format *Wochentag, DD.MM.*)"
    # Datum-Marker je Tag stehen im Kopf
    assert "%02d.%02d." % (tag0.day, tag0.month) in result
    assert "%02d.%02d." % (tag1.day, tag1.month) in result
    assert "%02d.%02d." % (tag2.day, tag2.month) in result

    # Termin-Titel stehen drin
    assert "Zahnarzt" in result
    assert "Sport" in result
    assert "Urlaub" in result

    # Mehrtages-Spanne erscheint genau einmal
    assert result.count("Urlaub") == 1, (
        "Mehrtages-Spanne darf nur einmal im Listen-Block erscheinen (TER-9/PLAN-14)")
