"""Tests für die Funktion routine_punkte_lesen — RPS-3 V1.2, EC-9.

Prüft die trigger-agnostische Lese-Funktion: Format, Signale, RPS-2-
Berechtigung, Fehlerbehandlung. Kein propose→confirm, kein Schreiben.
"""

from skills.routine_client import RoutineClientError
from skills.routine_punkte_lesen import (
    SIGNAL_ABGELEHNT,
    SIGNAL_GELESEN,
    SIGNAL_NICHT_ERREICHBAR,
    routine_punkte_lesen,
)


# ============================================================
#  Doppelungen — CLIENT-1 Transport-Stub-Naht
# ============================================================

class FakeRoutineClient:
    """Minimal-Doppelung des RoutineClients für Lese-Tests."""

    def __init__(self, get_items_response=None, get_items_error=None):
        self.get_items_calls = []
        self._get_items_response = get_items_response or {
            "default": [], "einmalig_heute": []}
        self._get_items_error = get_items_error

    def get_items(self):
        self.get_items_calls.append(True)
        if self._get_items_error is not None:
            raise self._get_items_error
        return dict(self._get_items_response)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


# ============================================================
#  RPS-2: Berechtigung
# ============================================================

def test_rps2_nicht_mitglied_abgelehnt():
    """RPS-2: Nicht-Mitglied → SIGNAL_ABGELEHNT, kein get_items()."""
    rc = FakeRoutineClient()
    signal, _ = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_kein_mitglied,
        from_user_id=99,
    )
    assert signal == SIGNAL_ABGELEHNT
    assert rc.get_items_calls == []


def test_rps2_kein_user_id_abgelehnt():
    """RPS-2: from_user_id=None → SIGNAL_ABGELEHNT."""
    rc = FakeRoutineClient()
    signal, _ = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=None,
    )
    assert signal == SIGNAL_ABGELEHNT
    assert rc.get_items_calls == []


# ============================================================
#  AC1 / RPS-3 V1.2: Signal und Rohdaten
# ============================================================

def test_lesen_signal_gelesen():
    """AC1: routine_punkte_lesen liefert SIGNAL_GELESEN (RPS-3 V1.2)."""
    rc = FakeRoutineClient(get_items_response={
        "default": [
            {"id": "anziehen", "label": "Anziehen", "piktogramm": "👕"},
        ],
        "einmalig_heute": [],
    })
    signal, daten = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert signal == SIGNAL_GELESEN
    assert len(daten["default"]) == 1
    assert daten["einmalig_heute"] == []


def test_lesen_ruft_get_items_auf():
    """AC1: routine_punkte_lesen ruft get_items() genau einmal auf."""
    rc = FakeRoutineClient()
    routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert len(rc.get_items_calls) == 1


# ============================================================
#  AC1 / RPS-3 V1.2: Format-Prüfung
# ============================================================

def test_format_dauerhaft_nummeriert():
    """AC1: Formatierter Text enthält 'Dauerhaft:' + nummerierte Items + Piktogramme."""
    rc = FakeRoutineClient(get_items_response={
        "default": [
            {"id": "anziehen", "label": "Anziehen", "piktogramm": "👕"},
            {"id": "fruehstueck", "label": "Frühstücken", "piktogramm": "🍞"},
            {"id": "zaehne-putzen", "label": "Zähne putzen", "piktogramm": "🪥"},
        ],
        "einmalig_heute": [],
    })
    _, daten = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    text = daten["text"]
    assert "Dauerhaft" in text
    assert "1. Anziehen" in text
    assert "2. Frühstücken" in text
    assert "3. Zähne putzen" in text
    assert "👕" in text
    assert "🍞" in text
    assert "🪥" in text


def test_format_mit_einmalig():
    """AC1: 'Heute zusätzlich' erscheint wenn einmalig_heute nicht leer."""
    rc = FakeRoutineClient(get_items_response={
        "default": [
            {"id": "anziehen", "label": "Anziehen", "piktogramm": "👕"},
        ],
        "einmalig_heute": [
            {"id": "einmalig:turnbeutel-mit", "label": "Turnbeutel", "piktogramm": "🎒"},
        ],
    })
    _, daten = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    text = daten["text"]
    assert "Heute zusätzlich" in text
    assert "1. Turnbeutel" in text
    assert "🎒" in text


def test_format_keine_einmalig_kein_heute_zusaetzlich():
    """AC1: 'Heute zusätzlich' erscheint NICHT wenn einmalig_heute leer."""
    rc = FakeRoutineClient(get_items_response={
        "default": [{"id": "a", "label": "A", "piktogramm": "1"}],
        "einmalig_heute": [],
    })
    _, daten = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert "Heute zusätzlich" not in daten["text"]


def test_format_leere_liste():
    """AC1: Leere default-Liste → '(keine Punkte)' im Text."""
    rc = FakeRoutineClient(get_items_response={
        "default": [],
        "einmalig_heute": [],
    })
    _, daten = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert "keine Punkte" in daten["text"]


# ============================================================
#  Fehlerbehandlung
# ============================================================

def test_buddy_nicht_erreichbar():
    """EC-7: get_items() wirft RoutineClientError → SIGNAL_NICHT_ERREICHBAR."""
    rc = FakeRoutineClient(
        get_items_error=RoutineClientError("Routine-Buddy nicht erreichbar"))
    signal, daten = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert "detail" in daten


# ============================================================
#  EC-9: Kein Schreiben
# ============================================================

def test_kein_schreiben():
    """EC-9: routine_punkte_lesen verändert KEINE Daten — nur get_items(),
    kein add/delete/replace."""
    class StrictFakeClient(FakeRoutineClient):
        def add_item(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

        def delete_item(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

        def replace_default_items(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

    rc = StrictFakeClient()
    signal, _ = routine_punkte_lesen(
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert signal == SIGNAL_GELESEN
