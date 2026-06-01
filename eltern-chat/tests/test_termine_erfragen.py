"""Tests für die Funktion termine_erfragen — TER-1 … TER-10 (Refs #143).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(TER-11, CLAUDE.md §6). Telegram und die Plan-Buddy-Schnittstelle werden durch
kontrollierte Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).
"""

import json
from datetime import date, timedelta

import pytest

from fakes import FakeTelegram
from skills.plan_client import PlanClientError
from skills.termine_erfragen import (
    SIGNAL_ABGELEHNT, SIGNAL_BEANTWORTET, SIGNAL_LEER, SIGNAL_NICHT_ERREICHBAR,
    formatiere_termine, parse_zeitraum, termine_erfragen,
)


# ============================================================
#  Hilfs-Klassen / Doppelungen
# ============================================================

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


def _member(user_ids):
    """Erstellt eine is_member_fn, die nur die angegebenen IDs akzeptiert."""
    ids = set(user_ids)
    return lambda uid: uid in ids


def _kein_mitglied():
    return lambda uid: False


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
#  TER-1 — Aufruf-Schnittstelle und Ergebnis-Signale
# ============================================================

def test_TER_1_minimaler_aufruf_mit_gueltigem_mitglied():
    """TER-1: ein Aufruf mit Chat-ID, User-ID und Mitglied postet eine
    Antwort und liefert 'beantwortet'."""
    tg = FakeTelegram(members={7: {"status": "member"}})
    pc = FakePlanClient(events=[_event()])
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_BEANTWORTET
    assert len(tg.sent) == 1


def test_TER_1_kein_chat_id_bricht_ohne_wirkung_ab():
    """TER-1: ein Aufruf ohne chat_id bricht ohne Wirkung ab."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    signal = termine_erfragen(
        tg=tg, chat_id=None, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_ABGELEHNT
    assert tg.sent == []


# ============================================================
#  TER-2 — Berechtigung live geprüft
# ============================================================

def test_TER_2_nicht_mitglied_wird_abgelehnt():
    """TER-2: ein Nicht-Familienmitglied bekommt das Signal 'abgelehnt';
    im Chat erscheint keine Antwort."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=99, anfrage_text="",
        plan_client=pc, is_member_fn=_kein_mitglied(),
        heute=MONTAG,
    )
    assert signal == SIGNAL_ABGELEHNT
    assert tg.sent == []   # keine Antwort im Chat


def test_TER_2_plan_client_wird_nicht_aufgerufen_bei_ablehnung():
    """TER-2: bei Ablehnung wird die Plan-Buddy-Schnittstelle nicht aufgerufen."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=99, anfrage_text="",
        plan_client=pc, is_member_fn=_kein_mitglied(),
        heute=MONTAG,
    )
    assert pc.calls == []


def test_TER_2_none_user_id_wird_abgelehnt():
    """TER-2: eine fehlende user_id (None) führt zur Ablehnung."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=None, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_ABGELEHNT


# ============================================================
#  TER-3 — Antwort im selben Chat
# ============================================================

def test_TER_3_antwort_landet_in_demselben_chat_gruppe():
    """TER-3: Gruppen-Anfrage → Antwort in der Gruppe, kein Privatchat."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    gruppen_chat_id = -100123
    termine_erfragen(
        tg=tg, chat_id=gruppen_chat_id, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert tg.sent[0]["chat_id"] == gruppen_chat_id


def test_TER_3_antwort_landet_in_demselben_chat_privat():
    """TER-3: Privatchat-Anfrage → Antwort im Privatchat."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    privat_chat_id = 7
    termine_erfragen(
        tg=tg, chat_id=privat_chat_id, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert tg.sent[0]["chat_id"] == privat_chat_id


def test_TER_3_kein_privatchat_bei_gruppen_anfrage():
    """TER-3: kein Privatchat-Eröffnung bei einer Gruppen-Frage (E-TER-3)."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    gruppen_chat_id = -100456
    privat_chat_id = 7
    termine_erfragen(
        tg=tg, chat_id=gruppen_chat_id, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    # Alle Nachrichten gehen in die Gruppe, nicht in den Privatchat
    for msg in tg.sent:
        assert msg["chat_id"] != privat_chat_id


# ============================================================
#  TER-5 — HTTP-Aufruf an PLAN-22
# ============================================================

def test_TER_5_http_aufruf_mit_richtigen_parametern():
    """TER-5: der HTTP-Aufruf nutzt ab=<iso>&tage=<n>."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="heute",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert len(pc.calls) == 1
    ab, tage = pc.calls[0]
    assert ab == MONTAG.isoformat()
    assert tage == 1


def test_TER_5_kein_cache_zweiter_aufruf_sieht_neue_dopplung():
    """TER-5: kein Cache — ein zweiter Aufruf geht frisch an den Server."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    termine_erfragen(tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
                     plan_client=pc, is_member_fn=_member([7]), heute=MONTAG)
    termine_erfragen(tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
                     plan_client=pc, is_member_fn=_member([7]), heute=MONTAG)
    assert len(pc.calls) == 2


def test_TER_5_datums_vokabular_loest_richtigen_aufruf_aus_morgen():
    """TER-4/TER-5: 'morgen' → start=heute+1, tage=1."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event("Zahnarzt", beginn="2026-06-02",
                                       ende="2026-06-03")])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="morgen",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert pc.calls[0] == (DIENSTAG.isoformat(), 1)


def test_TER_5_datums_vokabular_diese_woche():
    """TER-4/TER-5: 'diese Woche' (ab Montag) → start=heute, tage=7."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="diese Woche",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert pc.calls[0] == (MONTAG.isoformat(), 7)


def test_TER_5_datums_vokabular_naechste_woche():
    """TER-4/TER-5: 'nächste Woche' → start=nächster Montag, tage=7."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="nächste Woche",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    naechster_montag = MONTAG + timedelta(7)
    assert pc.calls[0] == (naechster_montag.isoformat(), 7)


def test_TER_5_datums_vokabular_naechsten_5_tage():
    """TER-4/TER-5: 'die nächsten 5 Tage' → start=heute, tage=5."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="die nächsten 5 Tage",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert pc.calls[0] == (MONTAG.isoformat(), 5)


def test_TER_5_datums_vokabular_default():
    """TER-4/TER-5: kein Datums-Ausdruck → start=heute, tage=7 (Default)."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="was steht an?",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert pc.calls[0] == (MONTAG.isoformat(), 7)


# ============================================================
#  TER-6 — Personen-Auflösung bleibt beim Plan-Buddy
# ============================================================

def test_TER_6_person_feld_wird_uebernommen():
    """TER-6: das person-Feld aus der PLAN-22-Antwort wird direkt übernommen."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[
        _event("Klettern", person="person-mia-01"),
    ])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert tg.sent
    assert "person-mia-01" in tg.sent[0]["text"]


def test_TER_6_leeres_person_feld_wird_nicht_fingiert():
    """TER-6: ein leeres person-Feld führt zu einem Termin ohne Personen-Bezug —
    keine fingierte Zuordnung."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[
        _event("Termin ohne Person", person=None),
    ])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert tg.sent
    # Kein "—" (Personen-Separator) in der Termin-Zeile
    termin_text = tg.sent[0]["text"]
    assert "Termin ohne Person" in termin_text
    # Person-Separator " — " darf nicht vorkommen (TER-6)
    lines = [l for l in termin_text.splitlines() if "Termin ohne Person" in l]
    assert lines
    assert " — " not in lines[0]


# ============================================================
#  TER-7 — Plan-Buddy nicht erreichbar
# ============================================================

def test_TER_7_verbindung_tot_liefert_nicht_erreichbar():
    """TER-7: ein Verbindungsfehler liefert 'nicht_erreichbar' und postet
    die hart-codierte Ehrlich-Antwort."""
    tg = FakeTelegram()
    pc = FakePlanClient(error=PlanClientError("Verbindung tot"))
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert len(tg.sent) == 1   # ehrliche Antwort gepostet
    assert "Wochenplan" in tg.sent[0]["text"]


def test_TER_7_http_fehler_liefert_nicht_erreichbar():
    """TER-7: HTTP 5xx wird als 'nicht_erreichbar' gemeldet."""
    tg = FakeTelegram()
    pc = FakePlanClient(error=PlanClientError("HTTP 503"))
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR
    # keine Halluzination: nur EINE Nachricht, die ehrliche Fehlermeldung
    assert len(tg.sent) == 1
    assert "nicht erreichbar" in tg.sent[0]["text"].lower() or \
           "Wochenplan" in tg.sent[0]["text"]


def test_TER_7_plan_buddy_nicht_installiert_selbes_verhalten():
    """TER-7 APP-2: ein nicht installierter Plan-Buddy verhält sich identisch
    zu einem Verbindungsfehler — PlanClientError ist die gemeinsame Klasse."""
    tg = FakeTelegram()
    # APP-2: Plan-Buddy nicht installiert → Verbindung schlägt fehl
    pc = FakePlanClient(error=PlanClientError("Plan-Buddy nicht installiert"))
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR


def test_TER_7_kein_stack_trace_keine_halluzination():
    """TER-7 EC-7: bei einem Fehler werden keine Termine erfunden — nur die
    hart-codierte Antwort, kein generierter Text."""
    tg = FakeTelegram()
    pc = FakePlanClient(error=PlanClientError("weg"))
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    # Die Antwort enthält kein LLM-generiertes Material — sie ist deterministisch.
    from skills.termine_erfragen import _ANTWORT_NICHT_ERREICHBAR
    assert tg.sent[0]["text"] == _ANTWORT_NICHT_ERREICHBAR


# ============================================================
#  TER-8 — Leerer Zeitraum
# ============================================================

def test_TER_8_leere_liste_liefert_leer():
    """TER-8: eine leere PLAN-22-Antwort liefert 'leer' und postet die
    hart-codierte 'keine Termine'-Antwort."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[])
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_LEER
    assert len(tg.sent) == 1
    from skills.termine_erfragen import _ANTWORT_LEER
    assert tg.sent[0]["text"] == _ANTWORT_LEER


def test_TER_8_leer_ist_kein_stiller_abbruch():
    """TER-8: ein leerer Kalender führt zu einer Antwort — kein Schweigen."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert len(tg.sent) == 1   # eine Antwort, kein Schweigen


# ============================================================
#  TER-9 — Tagesgruppierte Antwort
# ============================================================

def test_TER_9_tagesgruppierung_chronologisch():
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


def test_TER_9_mehrtages_spanne_erscheint_genau_einmal():
    """TER-9 PLAN-14: eine Mehrtages-Spanne (gleiche id) erscheint genau
    einmal — nicht je Tag wiederholt."""
    # Ein Event, das zwei Tage umfasst (id="evt-mehr")
    events = [
        _event("Urlaub", beginn="2026-06-01", ende="2026-06-04",
               ganztags=True, id="evt-mehr"),
    ]
    antwort = formatiere_termine(events, MONTAG, 7)
    # "Urlaub" darf nur einmal vorkommen
    assert antwort.count("Urlaub") == 1


def test_TER_9_mehrtages_spanne_mit_hinweis():
    """TER-9: eine Mehrtages-Spanne trägt einen Spannen-Hinweis."""
    events = [
        _event("Urlaub", beginn="2026-06-01", ende="2026-06-05",
               ganztags=True, id="evt-mehr"),
    ]
    antwort = formatiere_termine(events, MONTAG, 7)
    # Spannen-Hinweis im Format "(bis TT.MM.)"
    assert "bis" in antwort


def test_TER_9_ganztaegiger_termin_traegt_ganztaetig():
    """TER-9: ganztägige Termine tragen 'ganztägig' statt einer Uhrzeit."""
    events = [_event("Familientag", ganztags=True)]
    antwort = formatiere_termine(events, MONTAG, 7)
    assert "ganztägig" in antwort


def test_TER_9_timed_termin_traegt_uhrzeit():
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


def test_TER_9_antwort_ist_deterministisch(monkeypatch):
    """TER-9 EC-12: gleiche Eingabe liefert immer denselben Text — kein LLM."""
    events = [_event("Termin A", id="a")]
    r1 = formatiere_termine(events, MONTAG, 7)
    r2 = formatiere_termine(events, MONTAG, 7)
    assert r1 == r2


def test_TER_9_deutsche_wochentage():
    """TER-9 URL-7: Tages-Köpfe sind deutsche Wochentage."""
    events = [_event("Test", beginn="2026-06-01", id="e")]
    antwort = formatiere_termine(events, MONTAG, 7)
    assert "Montag" in antwort


def test_TER_9_person_feld_in_antwort():
    """TER-9: das person-Feld erscheint in der Termin-Zeile."""
    events = [_event("Sport", person="person-mia-01", id="e")]
    antwort = formatiere_termine(events, MONTAG, 7)
    assert "person-mia-01" in antwort


def test_TER_9_full_flow_antwort_im_chat():
    """TER-9 End-to-End: der vollständige Aufruf postet eine tagesgruppierte
    Antwort, die keine LLM-generierten Anteile enthält."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[
        _event("Zahnarzt", beginn="2026-06-01", ende="2026-06-02",
               ganztags=True, id="e1"),
        _event("Sport", beginn="2026-06-03T15:00:00",
               ende="2026-06-03T16:00:00",
               ganztags=False, id="e2"),
    ])
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7, anfrage_text="diese Woche",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_BEANTWORTET
    assert len(tg.sent) == 1
    text = tg.sent[0]["text"]
    assert "Montag" in text
    assert "Zahnarzt" in text
    assert "Mittwoch" in text
    assert "Sport" in text
    assert "15:00" in text


# ============================================================
#  TER-4 EC-22 — mehrdeutiger Ausdruck → Rückfrage
# ============================================================

def test_TER_4_mehrdeutig_loest_rueckfrage_aus():
    """TER-4 EC-22: ein mehrdeutiger Ausdruck ('nächsten Freitag') löst eine
    Rückfrage aus statt eines blinden Aufrufs."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7,
        anfrage_text="nächsten Freitag",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_BEANTWORTET
    assert len(tg.sent) == 1
    assert "?" in tg.sent[0]["text"]  # eine Rückfrage
    assert pc.calls == []   # kein blinder Plan-Buddy-Aufruf


# ============================================================
#  TER-4 — explizite Kalenderdaten (#309)
# ============================================================

# MITTWOCH ist 2026-06-03 → liegt nach MONTAG 2026-06-01
MITTWOCH_DATUM = date(2026, 6, 3)
# Ein Datum in der Vergangenheit (relativ zu MONTAG = 2026-06-01)
VERGANGEN = date(2026, 5, 15)


def test_TER_4_explizit_dd_mm_punkt_punkt():
    """TER-4 #309: '3.6.' → start=2026-06-03, tage=1."""
    assert parse_zeitraum("3.6.", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER_4_explizit_dd_mm_fuehrende_null():
    """TER-4 #309: '03.06.' → start=2026-06-03, tage=1."""
    assert parse_zeitraum("03.06.", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER_4_explizit_dd_mm_jjjj():
    """TER-4 #309: '03.06.2026' → start=2026-06-03, tage=1."""
    assert parse_zeitraum("03.06.2026", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER_4_explizit_den_dd_mm():
    """TER-4 #309: 'den 3.6.' → start=2026-06-03, tage=1."""
    assert parse_zeitraum("den 3.6.", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER_4_explizit_am_dd_monat():
    """TER-4 #309: 'am 3. Juni' → start=2026-06-03, tage=1."""
    assert parse_zeitraum("am 3. Juni", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER_4_explizit_am_dd_monat_kleinschreibung():
    """TER-4 #309: 'am 3. juni' → start=2026-06-03, tage=1 (Kleinschreibung)."""
    assert parse_zeitraum("am 3. juni", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER_4_explizit_im_satz():
    """TER-4 #309: Datum eingebettet in Satz → korrekt geparst."""
    assert parse_zeitraum("gib mir die Termine für den 3.6. bitte", MONTAG) == (MITTWOCH_DATUM, 1)


def test_TER_4_explizit_heute_ist_explizites_datum():
    """TER-4 #309: explizites Datum = heute → start=heute, tage=1."""
    assert parse_zeitraum("1.6.", MONTAG) == (MONTAG, 1)


def test_TER_4_explizit_vergangen_ohne_jahr_gibt_rueckfrage():
    """TER-4 #309 EC-22: jahrloses Datum in der Vergangenheit → Rückfrage-Signal,
    kein Default, kein Folgejahr."""
    result = parse_zeitraum("15.5.", MONTAG)
    # Ergebnis darf weder (MONTAG, 7) noch ein Tupel mit date sein
    assert result is not None
    assert not isinstance(result, tuple)


def test_TER_4_explizit_vergangen_sendet_naechstes_jahr_rueckfrage():
    """TER-4 #309 EC-22: vergangenes jahrloses Datum → gezielte 'nächstes Jahr'-
    Rückfrage im Chat, kein blinder Plan-Buddy-Aufruf."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[_event()])
    signal = termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7,
        anfrage_text="15.5.",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert signal == SIGNAL_BEANTWORTET
    assert len(tg.sent) == 1
    assert "nächstes Jahr" in tg.sent[0]["text"]
    assert pc.calls == []   # kein blinder Plan-Buddy-Aufruf


def test_TER_4_explizit_default_bleibt_default():
    """TER-4 #309: 'was steht an' ohne Datum → Default (heute, 7) unverändert."""
    assert parse_zeitraum("was steht an", MONTAG) == (MONTAG, 7)


def test_TER_4_explizit_heute_bleibt_heute():
    """TER-4 #309: 'heute' bleibt bei (heute, 1) — kein Kurzschluss zum Datum-Parser."""
    assert parse_zeitraum("heute", MONTAG) == (MONTAG, 1)


def test_TER_4_explizit_e2e_plan_client_erhaelt_korrekten_zeitraum():
    """TER-4 #309 AC3: Plan-Buddy wird mit dem tatsächlichen (start, tage=1) aufgerufen,
    nicht mit Default-7-Tage — ehrliche Grenze (EC-7)."""
    tg = FakeTelegram()
    pc = FakePlanClient(events=[
        _event("Geburtstag", beginn="2026-06-03", ende="2026-06-04", ganztags=True),
    ])
    termine_erfragen(
        tg=tg, chat_id=42, from_user_id=7,
        anfrage_text="3.6.",
        plan_client=pc, is_member_fn=_member([7]),
        heute=MONTAG,
    )
    assert len(pc.calls) == 1
    ab, tage = pc.calls[0]
    assert ab == "2026-06-03"
    assert tage == 1
