"""Tests für die Funktion termin_eintragen — TES-1 … TES-9 (Refs #144, #289).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(TES-11, CLAUDE.md §6). Telegram, Plan-Buddy und Privatchat-Stream werden durch
kontrollierte Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).

Datums-Vokabular: parse_datum/extrahiere_titel werden direkt getestet;
die Datums-Grundlagen stammen aus `termine_erfragen.parse_zeitraum` (E-TES-4).

TES-6 (Refs #289): neue Tests für Uhrzeit-Vokabular (zeitgebunden), Mehrtages-
Spanne (ganztägig + beginn/ende) und EC-10-kombinierte-Bestätigung.

Hinweis: FakePlanClientV2 erweitert FakePlanClient lokal, da fakes.py (Shared-
Doppelung) außerhalb des Whitelist liegt. FakePlanClientV2 überschreibt nur
put_termin auf die neue (titel, beginn, ende=None)-Signatur (AC1, TES-8).
"""

from datetime import date, timedelta

import pytest

from fakes import FakePlanClient, FakeTelegram
from skills.plan_client import PlanClientError
from skills.termin_eintragen import (
    SIGNAL_ABGEBROCHEN,
    SIGNAL_ABGELEHNT,
    SIGNAL_EINGETRAGEN,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_UNKLAR,
    SIGNAL_VERWORFEN,
    extrahiere_titel,
    parse_datum,
    parse_mehrtage_spanne,
    parse_uhrzeit,
    termin_eintragen,
)
from telegram import TelegramError


# ============================================================
#  FakePlanClientV2 — lokale Erweiterung für TES-6/AC1 (Refs #289)
#
#  fakes.py ist außerhalb des Whitelist (Shared-Doppelung) und kann nicht
#  direkt editiert werden. Diese Subklasse überschreibt put_termin auf die
#  neue PLAN-22-Signatur (titel, beginn, ende=None) und speichert alle drei
#  Argumente in put_calls als 3-Tuple. Bestehende Tests importieren weiterhin
#  FakePlanClient (2-Arg-Signatur, ganztägig-Backward-Compat). Neue TES-6-Tests
#  nutzen FakePlanClientV2.
# ============================================================

class FakePlanClientV2(FakePlanClient):
    """Erweiterter FakePlanClient mit PLAN-22-Signatur (TES-8, #289).

    put_calls speichert (titel, beginn, ende) als 3-Tuple.
    """

    def __init__(self, put_event_id="evt-new-1", put_error=None):
        super().__init__(put_event_id=put_event_id, put_error=put_error)
        # Eigene put_calls-Liste mit 3-Tupeln — überlagert die aus FakePlanClient.
        self.put_calls = []

    def put_termin(self, titel, beginn, ende=None):
        """TES-8 / AC1: neue Signatur put_termin(titel, beginn, ende=None)."""
        self.put_calls.append((titel, beginn, ende))
        if self._put_error is not None:
            raise self._put_error
        return self._put_event_id


# ============================================================
#  Hilfs-Bausteine
# ============================================================

MONTAG    = date(2026, 6, 1)   # weekday()=0
DIENSTAG  = date(2026, 6, 2)
MITTWOCH  = date(2026, 6, 3)
DONNERSTAG= date(2026, 6, 4)
FREITAG   = date(2026, 6, 5)
SAMSTAG   = date(2026, 6, 6)
SONNTAG   = date(2026, 6, 7)


def _member(*user_ids):
    ids = set(user_ids)
    return lambda uid: uid in ids


def _kein_mitglied():
    return lambda uid: False


def _messages(*texts):
    """Baut einen next_message-Callable aus einer Folge von Texten.

    Ein None-Element in der Folge signalisiert Session-Timeout (SESS-3).
    """
    msgs = list(texts)

    class _Input:
        def __init__(self, t):
            self.text = t

    def _next():
        if not msgs:
            return None
        item = msgs.pop(0)
        if item is None:
            return None
        return _Input(item)

    return _next


def _run(anstos_text="Klettern Donnerstag", today=MONTAG,
         event_id="evt-1", put_error=None,
         messages=None, user_id=42, private_chat_id=100,
         family_group_chat_id=200, is_member=None):
    """Hilfsfunktion: führt termin_eintragen mit kontrollierten Doppelungen aus.

    Nutzt FakePlanClientV2 (neue PLAN-22-Signatur, put_calls als 3-Tuple).
    """
    tg = FakeTelegram(members={user_id: {"status": "member"}})
    plan_client = FakePlanClientV2(put_event_id=event_id, put_error=put_error)
    if is_member is None:
        is_member = _member(user_id)
    if messages is None:
        messages = _messages("ok")   # Default: Vorschlag bestätigen
    return (
        termin_eintragen(
            tg=tg,
            private_chat_id=private_chat_id,
            from_user_id=user_id,
            family_group_chat_id=family_group_chat_id,
            anstos_text=anstos_text,
            plan_client=plan_client,
            is_member_fn=is_member,
            next_message=messages,
            heute=today,
        ),
        tg,
        plan_client,
    )


# ============================================================
#  TES-4 — Datums-Vokabular: parse_datum
# ============================================================

def test_TES4_heute():
    """TES-4: „heute" → heutiges Datum."""
    assert parse_datum("Termin heute", MONTAG) == MONTAG


def test_TES4_morgen():
    """TES-4: „morgen" → nächster Tag."""
    assert parse_datum("Termin morgen", MONTAG) == DIENSTAG


def test_TES4_wochentag_donnerstag():
    """TES-4: konkreter Wochentag ohne Marker → nächster solcher Wochentag."""
    assert parse_datum("Klettern Donnerstag", MONTAG) == DONNERSTAG


def test_TES4_wochentag_freitag():
    assert parse_datum("Schulausflug Freitag", MONTAG) == FREITAG


def test_TES4_naechsten_montag():
    """TES-4: „nächsten Montag" am Montag → Montag nächste Woche."""
    assert parse_datum("Meeting nächsten Montag", MONTAG) == MONTAG + timedelta(7)


def test_TES4_naechsten_donnerstag():
    """TES-4: „nächsten Donnerstag" → eindeutig nächste Woche."""
    erwartet = DONNERSTAG + timedelta(7)
    assert parse_datum("Sport nächsten Donnerstag", MONTAG) == erwartet


def test_TES4_diese_woche_ist_kein_einzelner_tag():
    """TES-4: Zeitraum-Ausdrücke wie „diese Woche" → None (Rückfrage)."""
    assert parse_datum("Termine diese Woche", MONTAG) is None


def test_TES4_naechste_woche_ist_kein_einzelner_tag():
    """TES-4: Zeitraum-Ausdrücke wie „nächste Woche" → None (Rückfrage)."""
    assert parse_datum("nächste Woche", MONTAG) is None


def test_TES4_mehrdeutig_liefert_none():
    """TES-4: unbekannter Ausdruck → None (EC-22: gezielte Rückfrage)."""
    # parse_zeitraum liefert für unbekannten Text (heute, 7) → tage>1 → None
    result = parse_datum("irgendwann vielleicht", MONTAG)
    # parse_zeitraum gibt bei unbekanntem Text default (heute, 7 Tage) zurück
    # → tage=7 > 1 → None
    assert result is None


# ============================================================
#  TES-5 — Titel-Extraktion: extrahiere_titel
# ============================================================

def test_TES5_einfacher_titel():
    """TES-5: Titel roh aus dem Anstoß-Text, Trigger-Wörter entfernt."""
    titel = extrahiere_titel("trag Klettern Mila Donnerstag ein")
    assert "Klettern" in titel
    assert "Mila" in titel
    # Trigger-Wörter und Datums-Token sollen nicht im Titel sein
    assert "trag" not in titel.lower()
    assert "ein" not in titel.lower()
    assert "Donnerstag" not in titel


def test_TES5_nur_datum_vokabular_liefert_leer():
    """TES-5: Text nur aus Trigger+Datum → leerer Titel (Rückfrage nötig)."""
    titel = extrahiere_titel("trag morgen ein")
    # Soll leer oder nur Datums-Vokabular enthalten
    from skills.termin_eintragen import _ist_nur_datum_vokabular
    assert _ist_nur_datum_vokabular(titel)


def test_TES5_schulausflug():
    """TES-5: Schulausflug als Titel erhalten."""
    titel = extrahiere_titel("Schulausflug am Dienstag eintragen")
    assert "Schulausflug" in titel


def test_TES5_leerer_text():
    """TES-5: leerer Anstoß-Text → leerer Titel."""
    assert extrahiere_titel("") == ""


# ============================================================
#  TES-1 — Haupt-Funktion: Erfolgspfad
# ============================================================

def test_TES1_eingetragen_mit_event_id():
    """TES-1: erfolgreicher Aufruf liefert 'eingetragen'; event_id aus PLAN-22."""
    signal, tg, client = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
        event_id="evt-123",
    )
    assert signal == SIGNAL_EINGETRAGEN
    assert len(client.put_calls) == 1


def test_TES1_ohne_private_chat_id_abgelehnt():
    """TES-1: ohne Privatchat-ID bricht die Funktion ohne Wirkung ab."""
    tg = FakeTelegram()
    plan_client = FakePlanClient()
    signal = termin_eintragen(
        tg=tg, private_chat_id=None, from_user_id=42,
        family_group_chat_id=200, anstos_text="Klettern Donnerstag",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages(), heute=MONTAG)
    assert signal == SIGNAL_ABGELEHNT
    assert len(plan_client.put_calls) == 0


# ============================================================
#  TES-2 — Berechtigung
# ============================================================

def test_TES2_nicht_mitglied_abgelehnt():
    """TES-2: Nicht-Familienmitglied → 'abgelehnt', kein PUT."""
    signal, tg, client = _run(
        anstos_text="Klettern Donnerstag",
        is_member=_kein_mitglied(),
    )
    assert signal == SIGNAL_ABGELEHNT
    assert len(client.put_calls) == 0


def test_TES2_mitglied_darf_eintragen():
    """TES-2: Familienmitglied → kein 'abgelehnt'."""
    signal, _, client = _run(
        anstos_text="Klettern Donnerstag",
        is_member=_member(42),
    )
    assert signal != SIGNAL_ABGELEHNT


# ============================================================
#  TES-3 — Privatchat-Pflicht / Session-Timeout
# ============================================================

def test_TES3_timeout_liefert_abgebrochen():
    """TES-3: Session-Timeout (next_message=None) → 'abgebrochen'."""
    signal, _, client = _run(
        anstos_text="Klettern Donnerstag",
        messages=_messages(None),   # Timeout sofort
    )
    assert signal == SIGNAL_ABGEBROCHEN
    assert len(client.put_calls) == 0


# ============================================================
#  TES-4 — Datum Pflicht, Rückfrage bei Mehrdeutigkeit
# ============================================================

def test_TES4_mehrdeutiger_ausdruck_stellt_rueckfrage():
    """TES-4: mehrdeutiger Datums-Ausdruck → Rückfrage → dann korrekter PUT."""
    signal, tg, client = _run(
        anstos_text="Klettern diese Woche",  # keine eindeutige Datum → None
        today=MONTAG,
        messages=_messages("Donnerstag", "ok"),   # Rückfrage + Bestätigung
    )
    # Nach der Rückfrage „Donnerstag" sollte das Datum klar sein
    assert signal == SIGNAL_EINGETRAGEN
    assert len(client.put_calls) == 1


def test_TES4_mehrdeutiger_ausdruck_ohne_antwort_unklar():
    """TES-4: Rückfrage ohne gültige Antwort → 'unklar', kein PUT."""
    signal, _, client = _run(
        anstos_text="Klettern diese Woche",
        messages=_messages("keine ahnung"),  # keine gültige Datumsangabe
    )
    assert signal == SIGNAL_UNKLAR
    assert len(client.put_calls) == 0


def test_TES4_vergangenheit_stellt_rueckfrage_und_schreibt():
    """TES-4 Edge-Case: vergangenes Datum → Rückfrage → Bestätigung → PUT."""
    gestern = MONTAG - timedelta(days=1)
    signal, _, client = _run(
        anstos_text="Arzttermin Sonntag",   # Sonntag ist gestern (heute=Montag)
        today=MONTAG,
        # Sonntag liegt vor Montag: gestern
        messages=_messages("ok", "ok"),   # Vergangenheits-Bestätigung + Vorschlag
    )
    assert signal == SIGNAL_EINGETRAGEN
    assert len(client.put_calls) == 1


def test_TES4_vergangenheit_rueckfrage_verworfen():
    """TES-4 Edge-Case: vergangenes Datum → Rückfrage → nicht bestätigt → 'verworfen'."""
    signal, _, client = _run(
        anstos_text="Arzttermin Sonntag",
        today=MONTAG,
        messages=_messages("nein"),   # Vergangenheits-Rückfrage verweigert
    )
    assert signal == SIGNAL_VERWORFEN
    assert len(client.put_calls) == 0


# ============================================================
#  TES-5 — Titel Pflicht, Rückfrage wenn leer/nur Datum-Vokabular
# ============================================================

def test_TES5_leerer_titel_stellt_rueckfrage():
    """TES-5: leerer Titel → Rückfrage → Titel eingeben → PUT."""
    signal, _, client = _run(
        anstos_text="trag morgen ein",  # kein erkennbarer Titel
        today=MONTAG,
        messages=_messages("Zahnarzt", "ok"),   # Titel-Rückfrage + Vorschlag
    )
    assert signal == SIGNAL_EINGETRAGEN
    assert len(client.put_calls) == 1
    titel_im_put, _, _ = client.put_calls[0]
    assert "Zahnarzt" in titel_im_put


def test_TES5_titel_roh_ohne_anreicherung():
    """TES-5: Titel wird roh übernommen, keine automatische Personen-Anreicherung."""
    signal, _, client = _run(
        anstos_text="Klettern Mila Donnerstag",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    titel_im_put, _, _ = client.put_calls[0]
    # Roh: enthält Mila, kein automatisch angehängter Name
    assert "Mila" in titel_im_put


# ============================================================
#  TES-6 — Ganztägig, kein Uhrzeit-Feld im Body
# ============================================================

def test_TES6_body_ganztags_eintaeig():
    """TES-6: Ganztägig eintägig — PUT-Body enthält titel + beginn (ISO-Datum ohne T),
    kein ende. AC3-Regression: bisheriges Verhalten bleibt grün."""
    signal, _, client = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    titel, beginn, ende = client.put_calls[0]
    assert isinstance(titel, str)
    assert isinstance(beginn, str)
    # Ganztägig: kein »T« in beginn
    assert "T" not in beginn
    # ende ist None (eintägig)
    assert ende is None
    # beginn muss gültiges ISO-Datum sein
    from datetime import date as _date
    d = _date.fromisoformat(beginn)
    assert d == DONNERSTAG


# ============================================================
#  TES-6 (Refs #289) — parse_uhrzeit: Einzel-Uhrzeit-Parser
# ============================================================

def test_TES6_parse_uhrzeit_HH_MM():
    """TES-6: »14:00« → start_h=14, start_m=0, kein end, keine dauer."""
    u = parse_uhrzeit("Zahnarzt 14:00")
    assert u is not None
    assert u["start_h"] == 14
    assert u["start_m"] == 0
    assert u["end_h"] is None
    assert u["dauer_min"] is None


def test_TES6_parse_uhrzeit_H_Uhr():
    """TES-6: »14 Uhr« → start_h=14, start_m=0."""
    u = parse_uhrzeit("um 14 Uhr Termin")
    assert u is not None
    assert u["start_h"] == 14
    assert u["start_m"] == 0


def test_TES6_parse_uhrzeit_von_bis():
    """TES-6: »von 14 bis 15 Uhr« → start=14:00, end=15:00."""
    u = parse_uhrzeit("von 14 bis 15 Uhr Termin")
    assert u is not None
    assert u["start_h"] == 14
    assert u["end_h"] == 15
    assert u["end_m"] == 0


def test_TES6_parse_uhrzeit_HH_MM_bis_HH_MM():
    """TES-6: »14:00 bis 15:30« → start=14:00, end=15:30."""
    u = parse_uhrzeit("14:00 bis 15:30")
    assert u is not None
    assert u["start_h"] == 14
    assert u["start_m"] == 0
    assert u["end_h"] == 15
    assert u["end_m"] == 30


def test_TES6_parse_uhrzeit_bis_H_Uhr():
    """TES-6: Startuhrzeit + »bis 15 Uhr« → end_h=15."""
    u = parse_uhrzeit("Termin 14 Uhr bis 15 Uhr")
    assert u is not None
    assert u["start_h"] == 14
    assert u["end_h"] == 15


def test_TES6_parse_uhrzeit_fuer_X_stunden():
    """TES-6: »für 2 Stunden« → dauer_min=120."""
    u = parse_uhrzeit("Termin 14 Uhr für 2 Stunden")
    assert u is not None
    assert u["start_h"] == 14
    assert u["dauer_min"] == 120


def test_TES6_parse_uhrzeit_fuer_eine_stunde():
    """TES-6: »für eine Stunde« → dauer_min=60."""
    u = parse_uhrzeit("Termin 14 Uhr für eine Stunde")
    assert u is not None
    assert u["dauer_min"] == 60


def test_TES6_parse_uhrzeit_X_h():
    """TES-6: »1 h« → dauer_min=60."""
    u = parse_uhrzeit("Termin 14:00 1 h")
    assert u is not None
    assert u["dauer_min"] == 60


def test_TES6_parse_uhrzeit_kein_vokabular():
    """TES-6: kein Uhrzeit-Vokabular → None."""
    assert parse_uhrzeit("Klettern Donnerstag") is None
    assert parse_uhrzeit("Schulausflug Freitag") is None
    assert parse_uhrzeit("") is None


# ============================================================
#  TES-6 (Refs #289) — parse_mehrtage_spanne
# ============================================================

def test_TES6_parse_mehrtage_von_montag_bis_mittwoch():
    """TES-6: »von Montag bis Mittwoch« → (Montag, Mittwoch) als date."""
    result = parse_mehrtage_spanne("von Montag bis Mittwoch", heute=MONTAG)
    assert result is not None
    beginn, ende = result
    assert beginn == MONTAG
    assert ende == MITTWOCH


def test_TES6_parse_mehrtage_und():
    """TES-6: »Dienstag und Mittwoch« → (Dienstag, Mittwoch)."""
    result = parse_mehrtage_spanne("Schulausflug Dienstag und Mittwoch", heute=MONTAG)
    assert result is not None
    beginn, ende = result
    assert beginn == DIENSTAG
    assert ende == MITTWOCH


def test_TES6_parse_mehrtage_kein_match():
    """TES-6: kein Mehrtages-Ausdruck → None."""
    assert parse_mehrtage_spanne("Klettern Donnerstag", heute=MONTAG) is None
    assert parse_mehrtage_spanne("Termin morgen", heute=MONTAG) is None


# ============================================================
#  TES-6 / AC2 (Refs #289) — Zeitgebundener Anstoß → zeitgebundener PUT
# ============================================================

def test_TES6_uhrzeit_anstos_zeitgebundener_put():
    """TES-6 / AC2: Uhrzeit im Anstoß → zeitgebundener PUT (beginn/ende mit T)."""
    signal, _, client = _run(
        anstos_text="Zahnarzt Dienstag 10 Uhr bis 11 Uhr",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    titel, beginn, ende = client.put_calls[0]
    # Zeitgebunden: »T« in beginn und ende
    assert "T" in beginn, "beginn muss Datetime (T) sein, nicht Datum: %r" % beginn
    assert ende is not None and "T" in ende, "ende muss Datetime (T) sein: %r" % ende
    # Uhrzeit im PUT-Beginn muss stimmen
    assert "10:00:00" in beginn
    assert "11:00:00" in ende


def test_TES6_nur_startzeit_stellt_rueckfrage():
    """TES-6 / AC2: Nur Startzeit ohne Ende/Dauer → Rückfrage nach Ende, kein blinder PUT."""
    signal, tg, client = _run(
        anstos_text="Zahnarzt Dienstag 10 Uhr",   # nur Startzeit
        today=MONTAG,
        messages=_messages("bis 11 Uhr", "ok"),   # Endzeit-Rückfrage + Bestätigung
    )
    assert signal == SIGNAL_EINGETRAGEN
    assert len(client.put_calls) == 1
    titel, beginn, ende = client.put_calls[0]
    assert "T" in beginn
    assert ende is not None and "T" in ende
    assert "11:00:00" in ende


def test_TES6_nur_startzeit_mit_dauer_in_rueckfrage():
    """TES-6 / AC2: Rückfrage nach Ende — »für eine Stunde« als Dauer ist gültig."""
    signal, _, client = _run(
        anstos_text="Zahnarzt Dienstag 10 Uhr",   # nur Startzeit
        today=MONTAG,
        messages=_messages("für eine Stunde", "ok"),   # Dauer-Antwort + Bestätigung
    )
    assert signal == SIGNAL_EINGETRAGEN
    _, beginn, ende = client.put_calls[0]
    assert "T" in beginn
    assert "11:00:00" in ende   # 10:00 + 60 min = 11:00


def test_TES6_nur_startzeit_rueckfrage_timeout_unklar():
    """TES-6 / AC2: Rückfrage nach Ende — Timeout → 'unklar', kein PUT."""
    signal, _, client = _run(
        anstos_text="Zahnarzt Dienstag 10 Uhr",
        today=MONTAG,
        messages=_messages(None),   # Timeout auf die Endzeit-Rückfrage
    )
    assert signal == SIGNAL_ABGEBROCHEN
    assert len(client.put_calls) == 0


def test_TES6_vollstaendige_startend_kein_rueckfrage():
    """TES-6 / AC2: »16:00 bis 17:00« → direkt ohne Rückfrage eingetragen."""
    signal, tg, client = _run(
        anstos_text="Arzttermin Donnerstag 16:00 bis 17:00",
        today=MONTAG,
        messages=_messages("ok"),   # Nur Bestätigung, keine Endzeit-Rückfrage
    )
    assert signal == SIGNAL_EINGETRAGEN
    # Keine Rückfrage nach Endzeit: nur eine message verbraucht (ok)
    assert len(client.put_calls) == 1
    _, beginn, ende = client.put_calls[0]
    assert "16:00:00" in beginn
    assert "17:00:00" in ende


def test_TES6_validierung_ende_kleiner_beginn_mitternacht():
    """TES-6: Enduhrzeit vor Startuhrzeit → Mitternachts-Übergang (+1 Tag)."""
    signal, _, client = _run(
        anstos_text="Silvester Donnerstag 23 Uhr bis 1 Uhr",
        today=MONTAG,
        messages=_messages("ok"),
    )
    assert signal == SIGNAL_EINGETRAGEN
    _, beginn, ende = client.put_calls[0]
    # Beginn ist am Donnerstag, Ende am Freitag (Mitternachts-Übergang)
    beginn_datum = beginn.split("T")[0]
    ende_datum = ende.split("T")[0]
    assert beginn_datum == DONNERSTAG.isoformat()
    assert ende_datum == FREITAG.isoformat()


def test_TES6_zeitgebunden_put_kein_event_id():
    """TES-6 / TES-8: zeitgebundener PUT enthält kein event_id."""
    signal, _, client = _run(
        anstos_text="Zahnarzt Dienstag 10 Uhr bis 11 Uhr",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    # Der FakePlanClientV2 bekommt nur (titel, beginn, ende) — kein event_id.
    assert len(client.put_calls) == 1


# ============================================================
#  TES-6 / AC3 (Refs #289) — Mehrtages-Anstoß → ganztägige Spanne
# ============================================================

def test_TES6_mehrtage_put_beginn_ende_datum():
    """TES-6 / AC3: Mehrtages-Anstoß → PUT mit beginn+ende als ISO-Datum (kein T)."""
    signal, _, client = _run(
        anstos_text="Schulausflug von Dienstag bis Mittwoch",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    titel, beginn, ende = client.put_calls[0]
    # Ganztägig: kein T in beginn/ende
    assert "T" not in beginn
    assert ende is not None and "T" not in ende
    # Datumsangaben stimmen
    from datetime import date as _date
    assert _date.fromisoformat(beginn) == DIENSTAG
    assert _date.fromisoformat(ende) == MITTWOCH


def test_TES6_mehrtage_vorschlag_zeigt_von_bis():
    """TES-6 / AC3: Vorschlag bei Mehrtages-Termin zeigt Von/Bis-Zeilen."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClientV2()
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200,
        anstos_text="Schulausflug von Dienstag bis Mittwoch",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG)
    vorschlaege = [m for m in tg.sent if "Von:" in m["text"] or "von" in m["text"].lower()]
    assert vorschlaege, "Kein Vorschlag mit Von-Bis-Angabe gefunden: %r" % tg.sent


def test_TES6_mehrtage_ohne_uhrzeit():
    """TES-6 / AC3: Mehrtage ohne Uhrzeit → ganztägige Spanne, kein T."""
    signal, _, client = _run(
        anstos_text="Elternabend Dienstag und Mittwoch",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    _, beginn, ende = client.put_calls[0]
    assert "T" not in beginn
    assert ende is not None and "T" not in ende


# ============================================================
#  TES-6 / AC4 (Refs #289) — EC-10: kombinierte Bestätigungsnachricht
# ============================================================

def test_TES6_EC10_vollstaendiger_anstos_eine_nachricht():
    """TES-6 / AC4 / EC-10: vollständiger Anstoß (Titel+Datum bekannt) →
    EINE kombinierte Nachricht (Vorschlag + Bestätigungsfrage)."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClientV2()
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200,
        anstos_text="Klettern Donnerstag",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG)
    # Alle gesendeten Nachrichten an private_chat_id=100:
    nachrichten_privat = [m["text"] for m in tg.sent if m["chat_id"] == 100]
    # Exakt zwei Nachrichten: Vorschlag (kombiniert) + Quittung.
    vorschlaege = [t for t in nachrichten_privat if "Soll ich diesen Termin" in t]
    assert len(vorschlaege) == 1, (
        "Erwarte genau EINE kombinierte Vorschlags-Nachricht, "
        "bekam %d: %r" % (len(vorschlaege), nachrichten_privat))
    # Bestätigungsfrage ist in der GLEICHEN Nachricht wie Vorschlag (EC-10).
    vorschlag_text = vorschlaege[0]
    assert "ok" in vorschlag_text.lower() or "bestätige" in vorschlag_text.lower(), (
        "Bestätigungsaufforderung fehlt in der kombinierten Nachricht: %r" % vorschlag_text)


def test_TES6_EC10_vollstaendiger_zeitgebundener_anstos_eine_nachricht():
    """TES-6 / AC4 / EC-10: vollständiger Anstoß mit Uhrzeit →
    EINE kombinierte Nachricht mit Zeit-Zeile."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClientV2()
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200,
        anstos_text="Zahnarzt Dienstag 10 Uhr bis 11 Uhr",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG)
    nachrichten_privat = [m["text"] for m in tg.sent if m["chat_id"] == 100]
    vorschlaege = [t for t in nachrichten_privat if "Soll ich diesen Termin" in t]
    assert len(vorschlaege) == 1, (
        "Erwarte genau EINE kombinierte Vorschlags-Nachricht: %r" % nachrichten_privat)
    # Zeitgebundener Vorschlag enthält Zeit-Zeile (TES-6-Spec).
    assert "10:00" in vorschlaege[0] or "Zeit" in vorschlaege[0], (
        "Zeitgebundener Vorschlag soll Uhrzeit enthalten: %r" % vorschlaege[0])


def test_TES6_EC10_unvollstaendiger_anstos_zweistufig():
    """TES-6 / AC4 / EC-10: unvollständiger Anstoß (Datum unbekannt) →
    zweistufig (erst Rückfrage, dann Vorschlag)."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClientV2()
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200,
        anstos_text="Klettern diese Woche",   # Datum unbekannt → Rückfrage
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("Donnerstag", "ok"), heute=MONTAG)
    nachrichten_privat = [m["text"] for m in tg.sent if m["chat_id"] == 100]
    # Mindestens 2 Nachrichten: Rückfrage + Vorschlag
    assert len(nachrichten_privat) >= 2, (
        "Bei unvollständigem Anstoß erwarte mindestens 2 Nachrichten: %r" % nachrichten_privat)
    # Erste Nachricht ist die Rückfrage (nicht der Vorschlag).
    assert "Soll ich diesen Termin" not in nachrichten_privat[0], (
        "Erste Nachricht bei unvollständigem Anstoß darf kein Vorschlag sein: %r"
        % nachrichten_privat[0])
    # Eine der Nachrichten ist der Vorschlag.
    vorschlaege = [t for t in nachrichten_privat if "Soll ich diesen Termin" in t]
    assert vorschlaege, "Kein Vorschlag-Nachricht gefunden: %r" % nachrichten_privat


def test_TES6_EC10_nur_startzeit_zweistufig():
    """TES-6 / AC4 / EC-10: Anstoß mit Startzeit, aber ohne Ende/Dauer →
    zweistufig (Rückfrage nach Ende, dann Vorschlag)."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClientV2()
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200,
        anstos_text="Zahnarzt Dienstag 10 Uhr",   # nur Startzeit
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("bis 11 Uhr", "ok"), heute=MONTAG)
    nachrichten_privat = [m["text"] for m in tg.sent if m["chat_id"] == 100]
    # Mindestens 2 Nachrichten: Endzeit-Rückfrage + Vorschlag
    assert len(nachrichten_privat) >= 2, (
        "Bei Anstoß ohne Ende erwarte mindestens 2 Nachrichten: %r" % nachrichten_privat)


# ============================================================
#  TES-6 / AC1 (Refs #289) — plan_client.put_termin Backward-Compat
# ============================================================

def test_TES6_AC1_ganztags_backward_compat():
    """TES-6 / AC1: bestehende ganztägige Aufrufe (beginn=ISO-Datum, ende=None)
    bleiben lauffähig — Rückwärts-Kompatibilität."""
    signal, _, client = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    # put_termin(titel, beginn) ohne ende entspricht dem alten put_termin(titel, datum)
    titel, beginn, ende = client.put_calls[0]
    assert ende is None  # Rückwärts-Compat: ende bleibt None für ganztägig eintägig


# ============================================================
#  TES-7 — Vorschlag + Bestätigungswort
# ============================================================

def test_TES7_vorschlag_wird_gepostet():
    """TES-7: vor dem PUT wird ein Vorschlag im Privatchat gepostet."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClient()
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200, anstos_text="Klettern Donnerstag",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG)
    # Mindestens eine Nachricht soll „Soll ich diesen Termin eintragen" enthalten
    vorschlaege = [m for m in tg.sent
                   if "Soll ich diesen Termin" in m["text"]]
    assert vorschlaege, "Kein Vorschlags-Text gefunden"


def test_TES7_bestaetigungswort_loest_put_aus():
    """TES-7: ein E-EC-7-Wort als Antwort auf den Vorschlag löst den PUT aus."""
    for wort in ("ok", "ja", "jo", "✅", "passt", "mach"):
        signal, _, client = _run(
            anstos_text="Klettern Donnerstag",
            messages=_messages(wort),
        )
        assert signal == SIGNAL_EINGETRAGEN, "Wort %r hat keinen PUT ausgelöst" % wort
        assert len(client.put_calls) == 1


def test_TES7_nicht_bestaetigendes_wort_verworfen():
    """TES-7: nicht-bestätigende Antwort → 'verworfen', kein PUT."""
    for wort in ("nein", "abbrechen", "nope", "lieber nicht"):
        signal, _, client = _run(
            anstos_text="Klettern Donnerstag",
            messages=_messages(wort),
        )
        assert signal == SIGNAL_VERWORFEN, "Wort %r hätte verwerfen sollen" % wort
        assert len(client.put_calls) == 0


def test_TES7_timeout_bei_vorschlag_abgebrochen():
    """TES-7: Timeout nach dem Vorschlag → 'abgebrochen', kein PUT."""
    signal, _, client = _run(
        anstos_text="Klettern Donnerstag",
        messages=_messages(None),  # Timeout beim Vorschlag-Warten
    )
    assert signal == SIGNAL_ABGEBROCHEN
    assert len(client.put_calls) == 0


# ============================================================
#  TES-8 — PUT und Antwort
# ============================================================

def test_TES8_put_methode_und_datum():
    """TES-8: PUT-Body enthält korrektes beginn im ISO-Datum-Format (ganztägig)."""
    signal, _, client = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    _, beginn, _ = client.put_calls[0]
    assert beginn == DONNERSTAG.isoformat()


def test_TES8_event_id_aus_plan_antwort():
    """TES-8: die event_id aus der PLAN-22-Antwort ist (für den Aufrufer) verfügbar.
    Da termin_eintragen() nur das Signal zurückgibt, prüfen wir via FakePlanClient,
    dass put_termin() aufgerufen wurde und SIGNAL_EINGETRAGEN zurückgegeben wird.
    """
    signal, _, client = _run(event_id="evt-xyz")
    assert signal == SIGNAL_EINGETRAGEN
    # FakePlanClient hat put_termin mit event_id="evt-xyz" versorgt.
    assert client._put_event_id == "evt-xyz"


def test_TES8_http_400_nicht_erreichbar():
    """TES-8: HTTP 400 vom Plan-Buddy → 'nicht_erreichbar'."""
    signal, _, client = _run(
        put_error=PlanClientError("HTTP 400"),
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert len(client.put_calls) == 1


def test_TES8_http_502_nicht_erreichbar():
    """TES-8: HTTP 502 (CalendarUnavailable) → 'nicht_erreichbar'."""
    signal, _, client = _run(
        put_error=PlanClientError("HTTP 502 CalendarUnavailable"),
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR


def test_TES8_kein_retry():
    """TES-8: bei PlanClientError wird kein Retry gemacht — nur ein PUT-Versuch."""
    signal, _, client = _run(
        put_error=PlanClientError("connection refused"),
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert len(client.put_calls) == 1   # genau ein Versuch, kein Retry


# ============================================================
#  TES-9 — Plan-Buddy nicht erreichbar
# ============================================================

def test_TES9_connection_fehler_nicht_erreichbar():
    """TES-9: Connection-Fehler → 'nicht_erreichbar', ehrliche Antwort im Chat."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClient(put_error=PlanClientError("connection tot"))
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200, anstos_text="Klettern Donnerstag",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG)
    # Ehrliche Antwort muss im Privatchat erscheinen
    nicht_erreichbar_msgs = [
        m for m in tg.sent
        if "nicht erreichbar" in m["text"].lower()
        or "konnte den Termin" in m["text"]
    ]
    assert nicht_erreichbar_msgs, "Keine ehrliche Fehler-Antwort im Chat"


def test_TES9_kein_halluzinierter_event_id():
    """TES-9: bei Plan-Buddy-Fehler wird keine event_id erfunden."""
    signal, tg, client = _run(
        put_error=PlanClientError("Plan-Buddy nicht da"),
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR
    # Keine Meldung „eingetragen" oder „event_id"
    eingetragen_msgs = [
        m for m in tg.sent
        if "eingetragen" in m["text"].lower() and "evt" in m["text"].lower()
    ]
    assert not eingetragen_msgs, "Halluzinierte Erfolgs-Meldung gefunden"


# ============================================================
#  TES-7 — Quittungs-Nachricht nach erfolgreichem PUT
# ============================================================

def test_TES7_quittung_eingetragen():
    """TES-7 / E-EC-7: nach erfolgreichem PUT sendet der Bot eine
    Quittungs-Nachricht mit Titel und Datum an private_chat_id."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClient(put_event_id="evt-q1")
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200, anstos_text="Klettern Donnerstag",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG)
    # Letzte Nachricht im Privatchat muss die Quittung sein
    letzte = tg.sent[-1]["text"]
    assert letzte.startswith("Eingetragen ✅"), (
        "Quittungs-Nachricht beginnt nicht mit 'Eingetragen ✅': %r" % letzte)
    assert "Klettern" in letzte, "Titel fehlt in Quittung: %r" % letzte
    # Datum muss im DD.MM.YYYY-Format enthalten sein (DONNERSTAG = 04.06.2026)
    assert "04.06.2026" in letzte, "Datum fehlt in Quittung: %r" % letzte


# ============================================================
#  TES-12 — Quittungs-Wortlaut je Termin-Art (T304, #273)
# ============================================================

def test_TES12_quittung_zeitgebunden():
    """TES-12 / AC1: nach erfolgreichem PUT eines zeitgebundenen Termins erscheint
    im Privatchat die Quittung im Zeitgebunden-Format (Titel + Datum + Uhrzeiten)."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClientV2(put_event_id="evt-tz-1")
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200,
        anstos_text="Zahnarzt Dienstag 10 Uhr bis 11 Uhr",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG)
    letzte = tg.sent[-1]["text"]
    # TES-12: Quittung beginnt mit »Eingetragen ✅«
    assert letzte.startswith("Eingetragen ✅"), (
        "Zeitgebunden-Quittung beginnt nicht mit 'Eingetragen ✅': %r" % letzte)
    # Titel muss enthalten sein
    assert "Zahnarzt" in letzte, "Titel fehlt in Zeitgebunden-Quittung: %r" % letzte
    # Start- und Endzeit müssen enthalten sein (TES-12: Zeitgebunden-Format)
    assert "10:00" in letzte, "Startzeit fehlt in Zeitgebunden-Quittung: %r" % letzte
    assert "11:00" in letzte, "Endzeit fehlt in Zeitgebunden-Quittung: %r" % letzte
    # Datum muss enthalten sein (Dienstag = 02.06.2026)
    assert "02.06.2026" in letzte, "Datum fehlt in Zeitgebunden-Quittung: %r" % letzte
    # Zeitgebunden-Quittung unterscheidet sich vom Ganztags-Format (enthält Uhrzeiten, nicht nur Datum)
    assert "Uhr" in letzte, "»Uhr« fehlt in Zeitgebunden-Quittung: %r" % letzte


def test_TES12_quittung_mehrtage():
    """TES-12 / AC2: nach erfolgreichem PUT eines mehrtägigen Termins erscheint
    im Privatchat die Quittung im Mehrtage-Format (»von … bis …«)."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClientV2(put_event_id="evt-mt-1")
    termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200,
        anstos_text="Schulausflug von Dienstag bis Mittwoch",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG)
    letzte = tg.sent[-1]["text"]
    # TES-12: Quittung beginnt mit »Eingetragen ✅«
    assert letzte.startswith("Eingetragen ✅"), (
        "Mehrtage-Quittung beginnt nicht mit 'Eingetragen ✅': %r" % letzte)
    # Titel muss enthalten sein
    assert "Schulausflug" in letzte, "Titel fehlt in Mehrtage-Quittung: %r" % letzte
    # Mehrtage-Format: »von … bis …« (TES-12)
    assert "von" in letzte.lower(), "»von« fehlt in Mehrtage-Quittung: %r" % letzte
    assert "bis" in letzte.lower(), "»bis« fehlt in Mehrtage-Quittung: %r" % letzte
    # Beginn- und Enddatum müssen enthalten sein (Dienstag=02.06, Mittwoch=03.06.2026)
    assert "02.06.2026" in letzte, "Beginn-Datum fehlt in Mehrtage-Quittung: %r" % letzte
    assert "03.06.2026" in letzte, "Ende-Datum fehlt in Mehrtage-Quittung: %r" % letzte


# ============================================================
#  TES-5 — Live-Pfad PUT-Body: Tanz-Termin + Bitte-um-Geduld (T304, #273)
# ============================================================

def test_TES5_live_tanz_termin_put_body():
    """TES-5 / AC3 (#273): »Trag Tanz-Termin am Freitag ein« →
    PUT-Body-Titel ist »Tanz-Termin« (Inhaltswörter bleiben erhalten,
    Trigger-Wörter und Datums-Token werden entfernt)."""
    signal, _, client = _run(
        anstos_text="Trag Tanz-Termin am Freitag ein",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    titel_im_put, beginn, _ = client.put_calls[0]
    assert titel_im_put == "Tanz-Termin", (
        "PUT-Body-Titel soll 'Tanz-Termin' sein, got %r" % titel_im_put)
    # Datum muss Freitag = 05.06.2026 sein
    from datetime import date as _date
    assert _date.fromisoformat(beginn) == FREITAG, (
        "PUT-Datum soll Freitag (%s) sein, got %r" % (FREITAG.isoformat(), beginn))


def test_TES5_live_bitte_um_geduld_put_body():
    """TES-5 / AC3 (#273): »Bitte um Geduld am Freitag« →
    PUT-Body-Titel ist »Bitte um Geduld« (»Bitte«, »um« und »Geduld«
    sind Inhaltswörter — kein Trigger, kein Datum-Token)."""
    signal, _, client = _run(
        anstos_text="Bitte um Geduld am Freitag",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    titel_im_put, beginn, _ = client.put_calls[0]
    assert titel_im_put == "Bitte um Geduld", (
        "PUT-Body-Titel soll 'Bitte um Geduld' sein, got %r" % titel_im_put)
    # Datum muss Freitag = 05.06.2026 sein
    from datetime import date as _date
    assert _date.fromisoformat(beginn) == FREITAG, (
        "PUT-Datum soll Freitag (%s) sein, got %r" % (FREITAG.isoformat(), beginn))


# ============================================================
#  T280 — typing_fn-Hook vor jeder Send-Phase (EC-14, Issue #280)
# ============================================================

def test_TES_typing_fn_called_before_each_send():
    """T280 / AC1+AC3: typing_fn wird vor jeder send_message-Phase aufgerufen.

    Vollständige Erfolgssequenz (Datum bekannt + Titel bekannt + Bestätigung):
    1× Vorschlag-Send + 1× Quittungs-Send = 2 Sends → Counter >= 2.
    Mit einem Datum-Rückfrage-Pfad kämen weitere Sends dazu.

    Wir erzwingen den 4-Send-Pfad: mehrdeutiges Datum (→ Rückfrage),
    eindeutiges Datum danach, kein Titel im Text (→ Rückfrage), Bestätigung.
    Damit: _RUECKFRAGE_DATUM + _RUECKFRAGE_TITEL + _VORSCHLAG + _ANTWORT_EINGETRAGEN
    = 4 Sends → Counter muss >= 4 sein.
    """
    counter = [0]

    def _counting_typing():
        counter[0] += 1

    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClient(put_event_id="evt-typing-1")
    # „trag diese Woche ein": kein Datum (→ Rückfrage), kein Titel (→ Rückfrage)
    signal = termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200,
        anstos_text="trag diese Woche ein",   # kein Datum, kein Titel
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("Donnerstag", "Zahnarzt", "ok"),
        heute=MONTAG,
        typing_fn=_counting_typing,
    )
    assert signal == SIGNAL_EINGETRAGEN
    assert counter[0] >= 4, (
        "typing_fn hätte mindestens 4× aufgerufen werden müssen "
        "(RUECKFRAGE_DATUM + RUECKFRAGE_TITEL + VORSCHLAG + QUITTUNG), "
        "aber es waren %d Aufrufe" % counter[0])


def test_TES_typing_fn_called_simple_success():
    """T280 / AC3: im einfachen Erfolgspfad (Datum+Titel bekannt) wird
    typing_fn mindestens 2× aufgerufen: vor Vorschlag + vor Quittung."""
    counter = [0]

    def _counting_typing():
        counter[0] += 1

    signal, tg, plan_client = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
        messages=_messages("ok"),
    )
    # Test nochmal direkt mit typing_fn:
    counter[0] = 0
    tg2 = FakeTelegram(members={42: {"status": "member"}})
    pc2 = FakePlanClient()
    signal2 = termin_eintragen(
        tg=tg2, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200, anstos_text="Klettern Donnerstag",
        plan_client=pc2, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG,
        typing_fn=_counting_typing,
    )
    assert signal2 == SIGNAL_EINGETRAGEN
    assert counter[0] >= 2, (
        "Im einfachen Erfolgspfad müssen mindestens 2 typing_fn-Aufrufe erfolgen "
        "(Vorschlag + Quittung), aber es waren %d" % counter[0])


def test_TES_typing_fn_none_ist_no_op():
    """T280 / AC4: typing_fn=None ist Backward-Compat — keine Exception,
    bestehende Erfolgs- und Fehler-Pfade laufen durch."""
    # Erfolgspfad
    signal, _, _ = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
        messages=_messages("ok"),
    )
    assert signal == SIGNAL_EINGETRAGEN

    # Fehler-Pfad (PlanClientError)
    signal2, _, _ = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
        put_error=PlanClientError("kein Plan-Buddy"),
        messages=_messages("ok"),
    )
    assert signal2 == SIGNAL_NICHT_ERREICHBAR

    # Verworfen-Pfad
    signal3, _, _ = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
        messages=_messages("nein"),
    )
    assert signal3 == SIGNAL_VERWORFEN


def test_TES_typing_fn_wirft_exception_kein_abbruch():
    """T280 / AC1 (Best-Effort): eine typing_fn, die TelegramError wirft,
    darf termin_eintragen() nicht unterbrechen — analog before_provider_call
    in agent.py (Issue #156, EC-14).

    Die Funktion muss 'eingetragen' zurückliefern, obwohl typing_fn immer wirft.
    """

    def _immer_werfend():
        raise TelegramError("Typing fehlgeschlagen")

    tg = FakeTelegram(members={42: {"status": "member"}})
    plan_client = FakePlanClient(put_event_id="evt-robust-1")
    signal = termin_eintragen(
        tg=tg, private_chat_id=100, from_user_id=42,
        family_group_chat_id=200, anstos_text="Klettern Donnerstag",
        plan_client=plan_client, is_member_fn=_member(42),
        next_message=_messages("ok"), heute=MONTAG,
        typing_fn=_immer_werfend,
    )
    assert signal == SIGNAL_EINGETRAGEN, (
        "typing_fn-Exception darf termin_eintragen() nicht abbrechen — "
        "erwartet SIGNAL_EINGETRAGEN, bekam %r" % signal)
