"""Tests für TermineErfragenTask — TER-10, EC-8/EC-9 (Refs #143).

Prüft die Aufgabe als EC-8-Katalog-Aufgabe:
- ReadTask-Kind (EC-9, kein Bestätigungs-Gate)
- Korrekte Registrierung im Katalog (wenn plan_origin_url gesetzt)
- run() delegiert korrekt an termine_erfragen und gibt eine Quittung zurück
"""

from datetime import date

from fakes import FakeTelegram
from model import READ
from skills.plan_client import PlanClientError
from skills.termine_erfragen_task import TermineErfragenTask
from tasks import ReadTask, TurnContext, build_catalog

# ============================================================
#  Hilfs-Klassen
# ============================================================

MONTAG = date(2026, 6, 1)


class FakePlanClientForTask:
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


def _member(user_ids):
    ids = set(user_ids)
    return lambda uid: uid in ids


def _event(titel="Test", beginn="2026-06-01", ende="2026-06-02",
           ganztags=True, id="evt-1"):
    return {"id": id, "titel": titel, "beginn": beginn, "ende": ende,
            "ganztags": ganztags, "person": None}


def _task(events=None, error=None):
    tg = FakeTelegram()
    pc = FakePlanClientForTask(events=events, error=error)
    is_member_fn = _member([7])
    task = TermineErfragenTask(tg=tg, plan_client=pc, is_member_fn=is_member_fn)
    return task, tg, pc


# ============================================================
#  TER-10 — ReadTask-Kind, EC-9-Lesend
# ============================================================

def test_TER_10_ist_eine_read_task():
    """TER-10 EC-9: die Aufgabe ist lesend (ReadTask, kein Bestätigungs-Gate)."""
    task, _, _ = _task(events=[_event()])
    assert isinstance(task, ReadTask)
    assert task.kind == READ


def test_TER_10_name_ist_termine_erfragen():
    """TER-10: der Name der Aufgabe ist 'termine_erfragen'."""
    task, _, _ = _task()
    assert task.name == "termine_erfragen"


def test_TER_10_hat_parameter_schema():
    """TER-10: die Aufgabe hat ein JSON-Schema für ihre Parameter."""
    task, _, _ = _task()
    params = task.parameters
    assert params["type"] == "object"
    assert "anfrage_text" in params["properties"]


# ============================================================
#  AC4 — Registrierung im build_catalog wenn plan_origin_url gesetzt
# ============================================================

def test_AC4_catalog_registriert_task_wenn_plan_origin_url_gesetzt(tmp_path):
    """AC4: build_catalog() registriert TermineErfragenTask wenn plan_origin_url
    gesetzt ist."""
    # CA-Datei anlegen (für CaVerteilungTask notwendig)
    ca_path = str(tmp_path / "rootCA.pem")
    with open(ca_path, "wb") as f:
        f.write(b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n")
    tg = FakeTelegram(members={7: {"status": "member"}})
    catalog = build_catalog(
        tg=tg,
        ca_pem_path=ca_path,
        plan_origin_url="http://127.0.0.1:5020",
    )
    task = catalog.get("termine_erfragen")
    assert task is not None
    assert isinstance(task, ReadTask)


def test_AC4_catalog_registriert_task_nicht_ohne_plan_origin_url(tmp_path):
    """AC4: ohne plan_origin_url wird TermineErfragenTask nicht registriert."""
    ca_path = str(tmp_path / "rootCA.pem")
    with open(ca_path, "wb") as f:
        f.write(b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n")
    tg = FakeTelegram()
    catalog = build_catalog(
        tg=tg,
        ca_pem_path=ca_path,
        # plan_origin_url nicht gesetzt
    )
    task = catalog.get("termine_erfragen")
    assert task is None


# ============================================================
#  run() — Delegation an termine_erfragen
# ============================================================

def test_run_delegiert_und_gibt_quittung_zurueck():
    """run() ruft termine_erfragen auf und gibt eine Quittung als Text zurück."""
    task, tg, pc = _task(events=[_event()])
    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = task.run(arguments={"anfrage_text": "heute"}, turn_context=ctx)
    assert isinstance(result, str)
    assert len(result) > 0


def test_run_chat_id_aus_turn_context():
    """Der Zielchat kommt aus dem TurnContext, nicht aus den Modell-Argumenten."""
    task, tg, pc = _task(events=[_event()])
    ctx = TurnContext(chat_id=42, from_user_id=7)
    # Modell liefert eine abweichende chat_id — sie wird ignoriert
    task.run(arguments={"anfrage_text": "", "chat_id": 999}, turn_context=ctx)
    # Nachricht ging in Chat 42, nicht 999
    assert tg.sent[0]["chat_id"] == 42


def test_run_beantwortet_liefert_quittung_text():
    """Bei SIGNAL_BEANTWORTET liefert run() eine nicht-leere Quittung."""
    task, tg, pc = _task(events=[_event()])
    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = task.run(arguments={}, turn_context=ctx)
    assert "Termine" in result or "geschickt" in result


def test_run_leer_liefert_leer_quittung():
    """Bei SIGNAL_LEER liefert run() die 'leer'-Quittung."""
    task, tg, pc = _task(events=[])
    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = task.run(arguments={}, turn_context=ctx)
    assert "keine" in result.lower() or "Termine" in result


def test_run_nicht_erreichbar_liefert_fehler_quittung():
    """Bei SIGNAL_NICHT_ERREICHBAR liefert run() die Fehler-Quittung."""
    task, tg, pc = _task(error=PlanClientError("weg"))
    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = task.run(arguments={}, turn_context=ctx)
    assert "Wochenplan" in result or "nicht erreichbar" in result.lower()


def test_run_anfrage_text_wird_weitergegeben():
    """run() leitet den anfrage_text an die Funktion weiter (TER-4)."""
    task, tg, pc = _task(events=[_event("Arzt", beginn="2026-06-02",
                                         ende="2026-06-03")])
    ctx = TurnContext(chat_id=42, from_user_id=7)
    task.run(arguments={"anfrage_text": "morgen"}, turn_context=ctx)
    # Die Funktion hat den Zeitraum aus 'morgen' aufgelöst (nicht Default)
    assert pc.calls    # mindestens ein Aufruf
    # 'morgen' ab heute=date.today() → start=heute+1, tage=1
    # Wir prüfen nur, dass tage=1 ist (Uhrzeit-sensitiv → Heute dynamisch)
    assert pc.calls[0][1] == 1
