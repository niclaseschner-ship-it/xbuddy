"""Tests für die Funktion termin_eintragen — TES-1 … TES-9 (Refs #144).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(TES-11, CLAUDE.md §6). Telegram, Plan-Buddy und Privatchat-Stream werden durch
kontrollierte Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).

Datums-Vokabular: parse_datum/extrahiere_titel werden direkt getestet;
die Datums-Grundlagen stammen aus `termine_erfragen.parse_zeitraum` (E-TES-4).
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
    termin_eintragen,
)
from telegram import TelegramError


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
    """Hilfsfunktion: führt termin_eintragen mit kontrollierten Doppelungen aus."""
    tg = FakeTelegram(members={user_id: {"status": "member"}})
    plan_client = FakePlanClient(put_event_id=event_id, put_error=put_error)
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
    titel_im_put, _ = client.put_calls[0]
    assert "Zahnarzt" in titel_im_put


def test_TES5_titel_roh_ohne_anreicherung():
    """TES-5: Titel wird roh übernommen, keine automatische Personen-Anreicherung."""
    signal, _, client = _run(
        anstos_text="Klettern Mila Donnerstag",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    titel_im_put, _ = client.put_calls[0]
    # Roh: enthält Mila, kein automatisch angehängter Name
    assert "Mila" in titel_im_put


# ============================================================
#  TES-6 — Ganztägig, kein Uhrzeit-Feld im Body
# ============================================================

def test_TES6_body_nur_titel_und_datum():
    """TES-6: PUT-Body enthält ausschließlich titel + datum (kein event_id, kein ganztags)."""
    # Wir testen via FakePlanClient — der PUT-Body wird in plan_client.py zusammengebaut.
    # Hier prüfen wir, dass die übergebenen Argumente nur Titel und Datum sind.
    signal, _, client = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    titel, datum = client.put_calls[0]
    assert isinstance(titel, str)
    assert isinstance(datum, str)
    # Datum muss ISO-Format sein
    from datetime import date as _date
    d = _date.fromisoformat(datum)
    assert d == DONNERSTAG


def test_TES6_uhrzeit_im_text_ignoriert():
    """TES-6: Uhrzeit im Anstoß-Text wird ignoriert, kein Uhrzeit-Feld im PUT."""
    signal, _, client = _run(
        anstos_text="Zahnarzt Dienstag 10 Uhr",
        today=MONTAG,
    )
    # Das Signal soll 'eingetragen' sein (Uhrzeit löst keine Rückfrage aus)
    assert signal == SIGNAL_EINGETRAGEN
    titel, datum = client.put_calls[0]
    # Kein Uhrzeit-Feld, nur Titel + Datum
    assert isinstance(datum, str)


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
    """TES-8: PUT-Body enthält korrektes datum im ISO-Format."""
    signal, _, client = _run(
        anstos_text="Klettern Donnerstag",
        today=MONTAG,
    )
    assert signal == SIGNAL_EINGETRAGEN
    _, datum = client.put_calls[0]
    assert datum == DONNERSTAG.isoformat()


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
