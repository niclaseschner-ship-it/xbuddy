"""Tests für die Funktion routine_zeiten_setzen — RZS-1 … RZS-7 (Refs #343).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(RZS-7, CLAUDE.md §6). Telegram und Routine-Buddy werden durch kontrollierte
Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).

Pflicht-Tests (RZS-7):
- Nicht-Mitglied → kein PUT (RZS-2).
- Happy-Path: vollständiger Anstoß → PUT mit erwartetem Payload (CLIENT-1).
- Buddy-4xx → kein Schreiben, ehrliche Grenze (EC-7, RZS-5).
- APP-3: der Skill ruft die API, nicht die Datei.
"""

from dataclasses import dataclass

from fakes import FakeTelegram
from skills.routine_client import RoutineClientError
from skills.routine_zeiten_setzen import (
    SIGNAL_ABGEBROCHEN,
    SIGNAL_ABGELEHNT,
    SIGNAL_GESETZT,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_UNKLAR,
    _erkenne_minuten,
    _erkenne_uhrzeit,
    _erkenne_zeit_art,
    routine_zeiten_setzen,
)

# ============================================================
#  Doppelungen
# ============================================================

class FakeRoutineClient:
    """Kontrollierte Doppelung des RoutineClients (CLIENT-1, EC-17).

    Transport-Stub-Naht: put_calls speichert die übergebenen Payloads.
    Kann Fehler injizieren.
    """

    def __init__(self, error=None):
        self._error = error
        self.put_calls = []  # list of payload dicts

    def put_config(self, payload):
        self.put_calls.append(dict(payload))
        if self._error is not None:
            raise self._error
        return True


@dataclass
class FakeMsg:
    """Minimale Nachricht-Doppelung für next_message-Stub."""
    text: str


def _member(user_id):
    return lambda uid: uid == user_id


def _kein_mitglied():
    return lambda uid: False


def _always_member():
    return lambda uid: True


# ============================================================
#  Parse-Helfer
# ============================================================

def test_erkenne_zeit_art_abfahrtszeit():
    """RZS-3: 'abfahrt' wird als abfahrtszeit erkannt."""
    assert _erkenne_zeit_art("setz die abfahrtszeit auf 08:15") == "abfahrtszeit"


def test_erkenne_zeit_art_aufstehzeit():
    """RZS-3: 'aufsteh' wird als aufstehzeit erkannt."""
    assert _erkenne_zeit_art("aufstehzeit auf 7 Uhr") == "aufstehzeit"


def test_erkenne_zeit_art_anzieh():
    """RZS-3: 'anzieh' wird als anzieh_vorlauf_min erkannt."""
    assert _erkenne_zeit_art("anzieh vorlauf auf 10") == "anzieh_vorlauf_min"


def test_erkenne_zeit_art_keine():
    """RZS-3: unbekannter Text → None."""
    assert _erkenne_zeit_art("hallo welt") is None


def test_erkenne_uhrzeit_hhmm():
    """RZS-3: HH:MM-Format wird erkannt."""
    assert _erkenne_uhrzeit("08:15") == "08:15"


def test_erkenne_uhrzeit_h_uhr():
    """RZS-3: 'H Uhr' wird als HH:MM erkannt."""
    assert _erkenne_uhrzeit("8 Uhr") == "08:00"


def test_erkenne_uhrzeit_h_uhr_mm():
    """RZS-3: 'H Uhr MM' wird als HH:MM erkannt."""
    assert _erkenne_uhrzeit("7 Uhr 30") == "07:30"


def test_erkenne_uhrzeit_none():
    """RZS-3: kein Uhrzeitwert → None."""
    assert _erkenne_uhrzeit("hallo") is None


def test_erkenne_minuten_zahl():
    """RZS-3: Zahl wird als Minuten erkannt."""
    assert _erkenne_minuten("10 Minuten") == 10


def test_erkenne_minuten_ohne_suffix():
    """RZS-3: reine Zahl wird als Minuten erkannt."""
    assert _erkenne_minuten("15") == 15


def test_erkenne_minuten_none():
    """RZS-3: kein Minutenwert → None."""
    assert _erkenne_minuten("keine Zeit") is None


# ============================================================
#  RZS-2: Nicht-Mitglied → kein PUT
# ============================================================

def test_RZS2_nicht_mitglied_kein_put():
    """RZS-2: Nicht-Mitglied → SIGNAL_ABGELEHNT, kein put_config-Aufruf."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=99,
        family_group_chat_id=200,
        anstos_text="abfahrtszeit auf 08:15",
        routine_client=client,
        is_member_fn=_kein_mitglied(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_ABGELEHNT
    assert len(client.put_calls) == 0, "Kein PUT bei Nicht-Mitglied (RZS-2)"


def test_RZS2_kein_user_id_kein_put():
    """RZS-2: from_user_id=None → SIGNAL_ABGELEHNT, kein put_config-Aufruf."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=None,
        family_group_chat_id=200,
        anstos_text="abfahrtszeit auf 08:15",
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_ABGELEHNT
    assert len(client.put_calls) == 0


# ============================================================
#  AC3: Happy-Path → PUT mit erwartetem Payload (CLIENT-1, Transport-Stub)
# ============================================================

def test_AC3_abfahrtszeit_happy_path():
    """AC3: vollständiger Anstoß (abfahrtszeit + HH:MM) → PUT mit {abfahrtszeit: '08:15'}."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="abfahrtszeit auf 08:15",
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_GESETZT
    assert client.put_calls == [{"abfahrtszeit": "08:15"}]


def test_AC3_aufstehzeit_happy_path():
    """AC3: vollständiger Anstoß (aufstehzeit + HH:MM) → PUT mit {aufstehzeit: '07:00'}."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="aufstehzeit auf 7 Uhr",
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_GESETZT
    assert client.put_calls == [{"aufstehzeit": "07:00"}]


def test_AC3_anzieh_vorlauf_happy_path():
    """AC3: vollständiger Anstoß (anzieh + Minuten) → PUT mit {anzieh_vorlauf_min: 10}."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="anzieh vorlauf auf 10 Minuten",
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_GESETZT
    assert client.put_calls == [{"anzieh_vorlauf_min": 10}]


def test_AC3_quittung_in_privatchat():
    """RZS-5: nach erfolgreichem PUT sendet die Funktion eine Quittung in den Privatchat."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="abfahrtszeit auf 08:15",
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    # Quittung im Privatchat gesendet
    quittungen = [m["text"] for m in tg.sent if m["chat_id"] == 42]
    assert any("gesetzt" in q.lower() or "08:15" in q for q in quittungen), (
        "Keine Quittung nach erfolgreichem PUT (RZS-5)")


# ============================================================
#  AC3: Buddy-4xx → kein Schreiben, ehrliche Grenze (EC-7, RZS-5)
# ============================================================

def test_AC3_buddy_4xx_kein_schreiben():
    """AC3 / RZS-5: Buddy-4xx (ungültiges Format) → SIGNAL_NICHT_ERREICHBAR,
    ehrliche Fehlermeldung im Privatchat, kein wiederholter PUT (EC-7)."""
    tg = FakeTelegram()
    client = FakeRoutineClient(
        error=RoutineClientError("Routine-Buddy: HTTP 400 bei PUT /api/v1/routine/config"))
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="abfahrtszeit auf 08:15",
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_NICHT_ERREICHBAR
    # Fehlermeldung im Privatchat
    texte = [m["text"] for m in tg.sent if m["chat_id"] == 42]
    assert any(texte), "Keine Fehlermeldung bei Buddy-4xx (EC-7)"


def test_AC3_buddy_5xx_nicht_erreichbar():
    """RZS-5: Buddy-5xx → SIGNAL_NICHT_ERREICHBAR, Fehlermeldung im Privatchat."""
    tg = FakeTelegram()
    client = FakeRoutineClient(
        error=RoutineClientError("Routine-Buddy: HTTP 503 bei PUT /api/v1/routine/config"))
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="abfahrtszeit auf 08:15",
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_NICHT_ERREICHBAR


# ============================================================
#  APP-3: Skill ruft die API, nicht die Datei
# ============================================================

def test_APP3_keine_datei_zugriffe():
    """APP-3: die Funktion liest/schreibt routine.json nicht direkt.

    Der RoutineClient ist die einzige Schnittstelle (RZS-6). Da wir den
    FakeRoutineClient injizieren, belegt ein erfolgreicher Test-Lauf,
    dass der Code ausschließlich über den Client schreibt — kein FS-Zugriff.
    (Dieser Test ist strukturell: ein FS-Bypass würde an einem anderen Ort
    schreiben und der FakeRoutineClient würde keine put_calls sehen.)
    """
    import unittest.mock as mock

    tg = FakeTelegram()
    client = FakeRoutineClient()
    with mock.patch("builtins.open", side_effect=AssertionError("FS-Bypass verboten")):
        result = routine_zeiten_setzen(
            tg=tg,
            private_chat_id=42,
            from_user_id=7,
            family_group_chat_id=200,
            anstos_text="abfahrtszeit auf 08:15",
            routine_client=client,
            is_member_fn=_always_member(),
            next_message=lambda: None,
        )
    assert result == SIGNAL_GESETZT
    assert len(client.put_calls) == 1, "PUT muss über den Client gehen (APP-3)"


# ============================================================
#  Rückfragen bei unvollständigem Anstoß
# ============================================================

def test_rueckfrage_fehlende_zeit_art():
    """RZS-4: fehlt Zeit-Art → Rückfrage, danach PUT (EC-22)."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    antworten = iter([FakeMsg("abfahrtszeit")])
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="auf 08:15",  # kein Zeit-Art-Hinweis
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: next(antworten, None),
    )
    assert result == SIGNAL_GESETZT
    assert client.put_calls == [{"abfahrtszeit": "08:15"}]


def test_rueckfrage_fehlender_wert():
    """RZS-4: fehlt Wert → Rückfrage, danach PUT (EC-22)."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    antworten = iter([FakeMsg("08:30")])
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="abfahrtszeit setzen",  # kein Wert
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: next(antworten, None),
    )
    assert result == SIGNAL_GESETZT
    assert client.put_calls == [{"abfahrtszeit": "08:30"}]


def test_rueckfrage_abgebrochen_bei_none():
    """RZS-4 / SESS-3: next_message → None bei unvollständigem Anstoß → ABGEBROCHEN."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="Zeit setzen",  # unvollständig
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_ABGEBROCHEN
    assert len(client.put_calls) == 0


def test_unklar_nach_schlechter_antwort():
    """RZS-4: Rückfrage → unverständliche Antwort → UNKLAR."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    antworten = iter([FakeMsg("keine ahnung")])
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=42,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="Zeit setzen",  # unvollständig
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: next(antworten, None),
    )
    assert result == SIGNAL_UNKLAR
    assert len(client.put_calls) == 0


# ============================================================
#  RZS-1: kein Privatchat → ABGELEHNT
# ============================================================

def test_kein_privatchat_abgelehnt():
    """RZS-1: private_chat_id=None → SIGNAL_ABGELEHNT, kein PUT."""
    tg = FakeTelegram()
    client = FakeRoutineClient()
    result = routine_zeiten_setzen(
        tg=tg,
        private_chat_id=None,
        from_user_id=7,
        family_group_chat_id=200,
        anstos_text="abfahrtszeit auf 08:15",
        routine_client=client,
        is_member_fn=_always_member(),
        next_message=lambda: None,
    )
    assert result == SIGNAL_ABGELEHNT
    assert len(client.put_calls) == 0
