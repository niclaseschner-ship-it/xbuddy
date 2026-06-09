"""Tests für die Funktion termine_erfragen — TER-1 … TER-11, EC-29 (Refs #143, #569).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(TER-11, CLAUDE.md §6). Plan-Buddy und Telegram werden durch kontrollierte
Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).

EC-29 / TASK-10: Die Funktion sendet selbst keine Telegram-Nachricht mehr.
Sie returnt in jedem Pfad einen User-tauglichen Antwort-Text als String.
Berechtigungs-Bruch (TER-2) wirft BerechtigungError.
"""

from datetime import date, timedelta

import pytest
from skills.plan_client import PlanClientError
from skills.termine_erfragen import (
    _ANTWORT_LEER,
    _ANTWORT_NICHT_ERREICHBAR,
    _RUECKFRAGE_NAECHSTES_JAHR,
    _RUECKFRAGE_ZEITRAUM,
    BerechtigungError,
    formatiere_termine,
    parse_zeitraum,
    termine_erfragen,
)

# ============================================================
#  Doppelungen — CLIENT-1 Transport-Stub-Naht
# ============================================================

class FakeTelegram:
    """Telegram-Doppelung: zeichnet send_message-Aufrufe auf.

    EC-29: In jedem Test-Pfad muss messages == [] bleiben — die Funktion
    sendet nicht mehr selbst.
    """

    def __init__(self):
        self.messages = []

    def send_message(self, chat_id, text):
        self.messages.append({"chat_id": chat_id, "text": text})

    def get_chat_member(self, group_id, user_id):
        return None


class FakePlanClient:
    """Kontrollierte Doppelung des PlanClients (TER-11, EC-17).

    Kann entweder eine feste Ereignis-Liste liefern oder einen Fehler werfen.
    Alle Aufrufe werden aufgezeichnet.
    """

    def __init__(self, events=None, error=None):
        self._events = events if events is not None else []
        self._error = error
        self.calls = []   # [(ab, tage), ...]

    def termine(self, ab, tage):
        self.calls.append((ab, tage))
        if self._error is not None:
            raise self._error
        return list(self._events)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _member(user_ids):
    """Erstellt eine is_member_fn, die nur die angegebenen IDs akzeptiert."""
    ids = set(user_ids)
    return lambda uid: uid in ids


def _event(titel="Arzttermin", beginn="2026-06-01", ende="2026-06-02",
           ganztags=True, person=None, id="evt-1"):
    return {"id": id, "titel": titel, "beginn": beginn, "ende": ende,
            "ganztags": ganztags, "person": person}


# ============================================================
#  TER-4 — Datums-Vokabular (parse_zeitraum)
# ============================================================

MONTAG    = date(2026, 6, 1)   # weekday()=0
DIENSTAG  = date(2026, 6, 2)
MITTWOCH  = date(2026, 6, 3)
DONNERSTAG= date(2026, 6, 4)
FREITAG   = date(2026, 6, 5)
SAMSTAG   = date(2026, 6, 6)
SONNTAG   = date(2026, 6, 7)


def test_TER_4_heute():
    assert parse_zeitraum("heute", MONTAG) == (MONTAG, 1)


def test_TER_4_morgen():
    assert parse_zeitraum("morgen", MONTAG) == (MONTAG + timedelta(1), 1)


def test_TER_4_naechste_woche_ab_montag():
    """Nächste Woche: nächster Montag, 7 Tage."""
    start, tage = parse_zeitraum("nächste Woche", MONTAG)
    assert start == MONTAG + timedelta(7)  # nächster Montag
    assert tage == 7


def test_TER_4_naechste_woche_ab_freitag():
    """Nächste Woche ab Freitag: übernächster Montag wäre falsch —
    es ist der nächste Montag (3 Tage)."""
    start, tage = parse_zeitraum("nächste Woche", FREITAG)
    # Freitag→Montag = 3 Tage weiter
    assert start == FREITAG + timedelta(3)
    assert tage == 7


def test_TER_4_naechste_woche_ab_sonntag():
    """Nächste Woche ab Sonntag: nächster Montag ist morgen."""
    start, tage = parse_zeitraum("nächste woche", SONNTAG)
    assert start == SONNTAG + timedelta(1)
    assert tage == 7


def test_TER_4_diese_woche_montag():
    """Diese Woche ab Montag: bis Sonntag = 7 Tage."""
    start, tage = parse_zeitraum("diese Woche", MONTAG)
    assert start == MONTAG
    assert tage == 7


def test_TER_4_diese_woche_freitag():
    """Diese Woche ab Freitag: bis Sonntag = 3 Tage."""
    start, tage = parse_zeitraum("diese Woche", FREITAG)
    assert start == FREITAG
    assert tage == 3


def test_TER_4_diese_woche_samstag():
    """Diese Woche ab Samstag: bis Sonntag = 2 Tage."""
    start, tage = parse_zeitraum("was steht diese Woche an?", SAMSTAG)
    assert start == SAMSTAG
    assert tage == 2


def test_TER_4_diese_woche_sonntag():
    """Diese Woche ab Sonntag: nur noch der heutige Sonntag = 1 Tag."""
    start, tage = parse_zeitraum("diese Woche", SONNTAG)
    assert start == SONNTAG
    assert tage == 1


def test_TER_4_naechsten_n_tage_3():
    start, tage = parse_zeitraum("die nächsten 3 Tage", MONTAG)
    assert start == MONTAG
    assert tage == 3


def test_TER_4_naechsten_n_tage_14():
    start, tage = parse_zeitraum("die nächsten 14 Tage", MONTAG)
    assert start == MONTAG
    assert tage == 14


def test_TER_4_naechsten_n_tage_31():
    start, tage = parse_zeitraum("die nächsten 31 Tage", MONTAG)
    assert start == MONTAG
    assert tage == 31


def test_TER_4_default_keine_zeitangabe():
    """Default: keine erkennbare Zeitangabe → heute, 7 Tage."""
    start, tage = parse_zeitraum("was steht an?", MONTAG)
    assert start == MONTAG
    assert tage == 7


def test_TER_4_default_welche_termine():
    start, tage = parse_zeitraum("welche Termine haben wir?", MONTAG)
    assert start == MONTAG
    assert tage == 7


def test_TER_4_default_leerer_text():
    start, tage = parse_zeitraum("", MONTAG)
    assert start == MONTAG
    assert tage == 7


def test_TER_4_mehrdeutig_naechsten_freitag_gibt_none():
    """TER-4 EC-22: mehrdeutiger Ausdruck wie 'nächsten Freitag' gibt None zurück."""
    result = parse_zeitraum("nächsten Freitag", MONTAG)
    assert result is None


def test_TER_4_mehrdeutig_naechsten_montag_gibt_none():
    result = parse_zeitraum("nächsten Montag", MONTAG)
    assert result is None


def test_TER_4_naechste_woche_hat_vorrang_vor_mehrdeutig():
    """'nächste Woche' ist klar (keine Mehrdeutigkeit)."""
    result = parse_zeitraum("nächste Woche", MONTAG)
    assert result is not None
    assert result[1] == 7


# ============================================================
#  TER-2: Berechtigung — Nicht-Mitglied → BerechtigungError, kein API-Aufruf
# ============================================================

def test_TER2_nicht_mitglied_wirft_berechtigung_error():
    """TER-2 / EC-29: Nicht-Mitglied → BerechtigungError, kein plan_client-Aufruf."""
    pc = FakePlanClient(events=[_event()])

    with pytest.raises(BerechtigungError):
        termine_erfragen(
            chat_id=42,
            from_user_id=99,
            anfrage_text="",
            plan_client=pc,
            is_member_fn=_kein_mitglied,
            heute=MONTAG,
        )

    assert pc.calls == [], "Kein API-Aufruf bei Nicht-Mitglied (TER-2)"


def test_TER2_kein_user_id_wirft_berechtigung_error():
    """TER-2 / EC-29: from_user_id=None → BerechtigungError."""
    pc = FakePlanClient()

    with pytest.raises(BerechtigungError):
        termine_erfragen(
            chat_id=42,
            from_user_id=None,
            anfrage_text="",
            plan_client=pc,
            is_member_fn=_immer_mitglied,
            heute=MONTAG,
        )

    assert pc.calls == []


def test_TER2_keine_telegram_nachricht_bei_ablehnung():
    """TER-2 / EC-29: Bei BerechtigungError wird kein tg.send_message aufgerufen.

    Die Funktion sendet nicht selbst — der Agent-Loop schreibt den
    Fehler-Tool-Result-Block (agent.py Fehlerpfad).
    """
    tg = FakeTelegram()
    pc = FakePlanClient()

    with pytest.raises(BerechtigungError):
        termine_erfragen(
            chat_id=42,
            from_user_id=99,
            anfrage_text="",
            plan_client=pc,
            is_member_fn=_kein_mitglied,
            heute=MONTAG,
        )

    assert tg.messages == [], "Keine Telegram-Nachricht bei Berechtigungs-Fehler (EC-29)"


# ============================================================
#  TER-7: Plan-Buddy nicht erreichbar — ehrliche Grenze als Tool-Result-String
# ============================================================

def test_TER7_verbindung_tot_returnt_meldung():
    """TER-7 / EC-29: Transport-Fehler → ehrliche Grenze als String,
    kein Cache, kein Retry. Kein tg.send_message (EC-29).
    """
    tg = FakeTelegram()
    pc = FakePlanClient(error=PlanClientError("Verbindung tot"))

    antwort = termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert isinstance(antwort, str)
    assert len(antwort) > 0
    assert pc.calls == [("2026-06-01", 7)], "Genau ein Aufruf, kein Retry (TER-7)"
    assert "Wochenplan" in antwort or "nicht erreichbar" in antwort.lower()
    assert antwort == _ANTWORT_NICHT_ERREICHBAR
    # EC-29: keine Telegram-Nachricht
    assert tg.messages == [], "Funktion darf kein tg.send_message aufrufen (EC-29)"


def test_TER7_kein_retry():
    """TER-7: bei Transport-Fehler KEIN zweiter Aufruf."""
    pc = FakePlanClient(error=PlanClientError("Timeout"))

    termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert len(pc.calls) == 1


# ============================================================
#  TER-8: Leerer Zeitraum — ehrliche Meldung als Tool-Result-String
# ============================================================

def test_TER8_leere_liste_returnt_meldung():
    """TER-8 / EC-29: Plan-Buddy liefert leere Liste → Skill returnt ehrliche
    Meldung als String. Kein tg.send_message (EC-29).
    """
    tg = FakeTelegram()
    pc = FakePlanClient(events=[])

    antwort = termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert isinstance(antwort, str)
    assert len(antwort) > 0
    assert antwort == _ANTWORT_LEER
    assert "keine" in antwort.lower() or "stehen" in antwort.lower()
    # EC-29: keine Telegram-Nachricht
    assert tg.messages == [], "Funktion darf kein tg.send_message aufrufen (EC-29)"


# ============================================================
#  TER-9: Happy-Path — tagesgruppierte Antwort als Tool-Result-String
# ============================================================

def test_TER9_happy_path_gibt_text_zurueck():
    """TER-9 / EC-29: Termine vorhanden → tagesgruppierte Antwort als String.
    Kein tg.send_message (EC-29).
    """
    tg = FakeTelegram()
    events = [
        _event("Zahnarzt", beginn="2026-06-01", ende="2026-06-02",
               ganztags=True, id="e1"),
        _event("Sport", beginn="2026-06-03T15:00:00",
               ende="2026-06-03T16:00:00",
               ganztags=False, id="e2"),
    ]
    pc = FakePlanClient(events=events)

    antwort = termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="diese Woche",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert isinstance(antwort, str)
    assert len(antwort) > 0
    assert "Montag" in antwort
    assert "Zahnarzt" in antwort
    assert "Mittwoch" in antwort
    assert "Sport" in antwort
    assert "15:00" in antwort
    # EC-29: keine Telegram-Nachricht
    assert tg.messages == [], "Funktion darf kein tg.send_message aufrufen (EC-29)"


def test_TER9_tagesgruppierung_chronologisch():
    """TER-9: Termine werden nach Tagen gruppiert, chronologisch."""
    events = [
        _event("Arzt Montag", beginn="2026-06-01", ende="2026-06-02",
               ganztags=True, id="e1"),
        _event("Schule Dienstag", beginn="2026-06-02", ende="2026-06-03",
               ganztags=True, id="e2"),
    ]
    antwort = formatiere_termine(events, MONTAG, 7)
    # Montag erscheint vor Dienstag
    pos_mo = antwort.index("Montag")
    pos_di = antwort.index("Dienstag")
    assert pos_mo < pos_di


def test_TER9_mehrtages_spanne_erscheint_genau_einmal():
    """TER-9 PLAN-14: eine Mehrtages-Spanne (gleiche id) erscheint genau
    einmal — nicht je Tag wiederholt."""
    events = [
        _event("Urlaub", beginn="2026-06-01", ende="2026-06-04",
               ganztags=True, id="evt-mehr"),
    ]
    antwort = formatiere_termine(events, MONTAG, 7)
    assert antwort.count("Urlaub") == 1


def test_TER9_ganztaegiger_termin_traegt_ganztaetig():
    """TER-9: ganztägige Termine tragen 'ganztägig' statt einer Uhrzeit."""
    events = [_event("Familientag", ganztags=True)]
    antwort = formatiere_termine(events, MONTAG, 7)
    assert "ganztägig" in antwort


def test_TER9_timed_termin_traegt_uhrzeit():
    """TER-9: Termine mit Uhrzeit zeigen HH:MM."""
    events = [{
        "id": "evt-t", "titel": "Meeting",
        "beginn": "2026-06-01T10:30:00",
        "ende": "2026-06-01T11:00:00",
        "ganztags": False, "person": None,
    }]
    antwort = formatiere_termine(events, MONTAG, 7)
    assert "10:30" in antwort
    assert "Meeting" in antwort


def test_TER9_deutsche_wochentage():
    """TER-9 URL-7: Tages-Köpfe sind deutsche Wochentage."""
    events = [_event("Test", beginn="2026-06-01", id="e")]
    antwort = formatiere_termine(events, MONTAG, 7)
    assert "Montag" in antwort


def test_TER9_person_feld_in_antwort():
    """TER-9: das person-Feld erscheint in der Termin-Zeile."""
    events = [_event("Sport", person="person-mia-01", id="e")]
    antwort = formatiere_termine(events, MONTAG, 7)
    assert "person-mia-01" in antwort


def test_TER9_antwort_ist_deterministisch():
    """TER-9 EC-12: gleiche Eingabe liefert immer denselben Text — kein LLM."""
    events = [_event("Termin A", id="a")]
    r1 = formatiere_termine(events, MONTAG, 7)
    r2 = formatiere_termine(events, MONTAG, 7)
    assert r1 == r2


# ============================================================
#  TER-4 EC-22: Rückfrage-Pfade returnen Text (kein Senden)
# ============================================================

def test_TER4_mehrdeutig_returnt_rueckfrage_text():
    """TER-4 EC-22 / EC-29: mehrdeutiger Ausdruck ('nächsten Freitag') →
    Rückfrage-Text als Tool-Result, kein tg.send_message, kein Plan-Buddy-Aufruf.
    """
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])

    antwort = termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="nächsten Freitag",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert isinstance(antwort, str)
    assert len(antwort) > 0
    assert antwort == _RUECKFRAGE_ZEITRAUM
    assert "?" in antwort  # eine Rückfrage
    assert pc.calls == [], "Kein blinder Plan-Buddy-Aufruf (TER-4, EC-22)"
    assert tg.messages == [], "Funktion darf kein tg.send_message aufrufen (EC-29)"


def test_TER4_vergangenes_datum_returnt_naechstes_jahr_rueckfrage():
    """TER-4 #309 EC-22 / EC-29: vergangenes jahrloses Datum → gezielte
    'nächstes Jahr'-Rückfrage als Tool-Result, kein tg.send_message,
    kein Plan-Buddy-Aufruf.
    """
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])

    antwort = termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="15.5.",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert isinstance(antwort, str)
    assert len(antwort) > 0
    assert antwort == _RUECKFRAGE_NAECHSTES_JAHR
    assert "nächstes Jahr" in antwort
    assert pc.calls == [], "Kein blinder Plan-Buddy-Aufruf (TER-4, #309)"
    assert tg.messages == [], "Funktion darf kein tg.send_message aufrufen (EC-29)"


# ============================================================
#  EC-29 / TASK-10: Kein tg.send in irgendeinem Pfad (Grundsatz-Test)
# ============================================================

def test_EC29_happy_path_sendet_nicht():
    """EC-29 / TASK-10: Happy-Path — FakeTelegram.messages == [].

    Belegt: die Funktion ruft in keinem Pfad tg.send_* auf.
    """
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])

    termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert tg.messages == []


def test_EC29_leer_sendet_nicht():
    """EC-29 / TASK-10: Leer-Pfad — FakeTelegram.messages == []."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[])

    termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert tg.messages == []


def test_EC29_fehler_sendet_nicht():
    """EC-29 / TASK-10: Transport-Fehler-Pfad — FakeTelegram.messages == []."""
    tg = FakeTelegram()
    pc = FakePlanClient(error=PlanClientError("Fehler"))

    termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert tg.messages == []


def test_EC29_rueckfrage_mehrdeutig_sendet_nicht():
    """EC-29 / TASK-10: Rückfrage-mehrdeutig-Pfad — FakeTelegram.messages == []."""
    tg = FakeTelegram()
    pc = FakePlanClient()

    termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="nächsten Montag",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert tg.messages == []


def test_EC29_rueckfrage_vergangen_sendet_nicht():
    """EC-29 / TASK-10: Rückfrage-vergangen-Pfad — FakeTelegram.messages == []."""
    tg = FakeTelegram()
    pc = FakePlanClient()

    termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="15.5.",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert tg.messages == []


# ============================================================
#  TER-3 — Zielchat-Routing via chat_id (kein Senden mehr, aber Parameter-Naht)
# ============================================================

def test_TER3_chat_id_wird_an_funktion_uebergeben():
    """TER-3: chat_id wird als Kontext übergeben — Funktion bricht nicht ab,
    wenn chat_id eine Gruppen-ID ist. EC-29: keine Sende-Prüfung nötig."""
    pc = FakePlanClient(events=[_event()])

    antwort = termine_erfragen(
        chat_id=-100123,
        from_user_id=7,
        anfrage_text="",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert isinstance(antwort, str)
    assert len(antwort) > 0


# ============================================================
#  TER-5 — HTTP-Aufruf an PLAN-22
# ============================================================

def test_TER5_http_aufruf_mit_richtigen_parametern():
    """TER-5: der HTTP-Aufruf nutzt ab=<iso>&tage=<n>."""
    pc = FakePlanClient(events=[_event()])

    termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="heute",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert len(pc.calls) == 1
    ab, tage = pc.calls[0]
    assert ab == MONTAG.isoformat()
    assert tage == 1


def test_TER5_datums_vokabular_morgen():
    """TER-4/TER-5: 'morgen' → start=heute+1, tage=1."""
    pc = FakePlanClient(events=[_event("Zahnarzt", beginn="2026-06-02",
                                       ende="2026-06-03")])

    termine_erfragen(
        chat_id=42,
        from_user_id=7,
        anfrage_text="morgen",
        plan_client=pc,
        is_member_fn=_immer_mitglied,
        heute=MONTAG,
    )

    assert pc.calls[0] == (DIENSTAG.isoformat(), 1)


# ============================================================
#  TER-4 — explizite Kalenderdaten (#309)
# ============================================================

MITTWOCH_DATUM = date(2026, 6, 3)


def test_TER4_explizit_dd_mm_punkt_punkt():
    """TER-4 #309: '3.6.' → start=2026-06-03, tage=1."""
    assert parse_zeitraum("3.6.", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER4_explizit_dd_mm_jjjj():
    """TER-4 #309: '03.06.2026' → start=2026-06-03, tage=1."""
    assert parse_zeitraum("03.06.2026", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER4_explizit_am_dd_monat():
    """TER-4 #309: 'am 3. Juni' → start=2026-06-03, tage=1."""
    assert parse_zeitraum("am 3. Juni", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER4_explizit_vergangen_ohne_jahr_gibt_rueckfrage():
    """TER-4 #309 EC-22: jahrloses Datum in der Vergangenheit → Rückfrage-Signal,
    kein Default, kein Folgejahr."""
    result = parse_zeitraum("15.5.", MONTAG)
    # Ergebnis darf weder (MONTAG, 7) noch ein Tupel mit date sein
    assert result is not None
    assert not isinstance(result, tuple)
