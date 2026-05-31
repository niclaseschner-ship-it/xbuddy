"""Termin eintragen — specs/platform/termin-eintragen.md (TES-1 … TES-10).

Aufrufbare, trigger-agnostische Funktion (TES-1, E-TES-1): klärt einen Termin
im Telegram-Privatchat des Aufrufers, legt ihn nach Bestätigung (TES-7) über
die Plan-Buddy-Termin-Schnittstelle an (PLAN-22, TES-8) und liefert ein
Ergebnis-Signal zurück.

Eingang: Telegram-Privatchat-ID, User-ID (Berechtigung TES-2), freier
Anstoß-Text (Datums-/Titel-Parsing TES-4/TES-5), next_message-Callable
(Privatchat-Stream, TES-3), PlanClient (TES-8), is_member_fn (TES-2).

Ausgang: Ergebnis-Signal als String (TES-1):
  „eingetragen"       — Termin angelegt, event_id aus PLAN-22-Antwort.
  „verworfen"         — Aufrufer hat Vorschlag nicht bestätigt (TES-7).
  „abgebrochen"       — Session-Timeout oder Prozess-Neustart (SESS-3).
  „abgelehnt"         — Berechtigung fehlt (TES-2).
  „nicht_erreichbar"  — Plan-Buddy nicht erreichbar oder PUT fehlgeschlagen (TES-9).
  „unklar"            — Titel/Datum nicht ermittelbar, Rückfrage ohne Antwort (TES-4/TES-5).

Datums-Vokabular: importiert aus `termine_erfragen.parse_zeitraum` (TES-4,
E-TES-4: geteilte Wahrheit, kein Kopieren).
"""

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable

import authz
import confirm
from skills.plan_client import PlanClient, PlanClientError
from skills.termine_erfragen import (parse_naechsten_wochentag, parse_wochentag,
                                      parse_zeitraum, wochentag_nr_dict)
from telegram import TelegramError


logger = logging.getLogger(__name__)


# TES-1: Ergebnis-Signale der Funktion.
SIGNAL_EINGETRAGEN     = "eingetragen"
SIGNAL_VERWORFEN       = "verworfen"
SIGNAL_ABGEBROCHEN     = "abgebrochen"
SIGNAL_ABGELEHNT       = "abgelehnt"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"
SIGNAL_UNKLAR          = "unklar"

# TES-9: Ehrliche Antwort bei nicht erreichbarem Plan-Buddy (EC-7).
# Wortlaut lebt im Code, Spec normiert Existenz + Inhalt (kein Stiller Abbruch).
_ANTWORT_NICHT_ERREICHBAR = (
    "Der Wochenplan ist gerade nicht erreichbar — ich konnte den Termin "
    "nicht eintragen, bitte gleich nochmal probieren.")

# TES-7: Vorschlags-Muster. Wortlaut lebt im Code, Spec normiert das Soll:
# Vorschlag enthält Titel + Tag(e) + ggf. Uhrzeit, Bestätigungswort erforderlich (E-EC-7).
# EC-10: vollständiger Anstoß → EINE kombinierte Nachricht (Vorschlag + Bestätigungsfrage).
_VORSCHLAG_TEMPLATE_GANZTAGS = (
    "Soll ich diesen Termin eintragen?\n"
    "• Titel: %s\n"
    "• Tag: %s\n\n"
    "Bestätige mit »ok« / »ja« oder einem anderen Bestätigungswort.")

_VORSCHLAG_TEMPLATE_ZEITGEBUNDEN = (
    "Soll ich diesen Termin eintragen?\n"
    "• Titel: %s\n"
    "• Tag: %s\n"
    "• Zeit: %s — %s Uhr\n\n"
    "Bestätige mit »ok« / »ja« oder einem anderen Bestätigungswort.")

_VORSCHLAG_TEMPLATE_MEHRTAGE = (
    "Soll ich diesen Termin eintragen?\n"
    "• Titel: %s\n"
    "• Von: %s\n"
    "• Bis: %s\n\n"
    "Bestätige mit »ok« / »ja« oder einem anderen Bestätigungswort.")

# TES-4 / TES-5: Rückfrage-Texte. Wortlaut ist Implementierungs-Detail.
_RUECKFRAGE_DATUM = (
    "Welchen Tag meinst du? Bitte sag zum Beispiel »heute«, »morgen« oder "
    "einen konkreten Wochentag (z. B. »Donnerstag«, »nächsten Freitag«).")
_RUECKFRAGE_TITEL = (
    "Wie soll der Termin heißen? Bitte gib mir den Termin-Titel.")
_RUECKFRAGE_VERGANGENHEIT = (
    "Der Tag %s liegt in der Vergangenheit — soll ich den Termin trotzdem "
    "eintragen? Bestätige mit »ok« / »ja«.")

# TES-6: Rückfrage bei Startuhrzeit ohne Enduhrzeit/Dauer (EC-22, PLAN-22).
_RUECKFRAGE_ENDZEIT = (
    "Bis wann geht der Termin? Sag z. B. »bis 15 Uhr«, »bis 15:30« oder "
    "»für eine Stunde«.")

# TES-7: Antwort bei Nicht-Bestätigung.
_ANTWORT_VERWORFEN = (
    "Ok — kein Termin eingetragen. Wenn du es erneut versuchen möchtest, "
    "formuliere einfach eine neue Anfrage.")

# TES-12: Erfolgs-Quittung im Privatchat nach erfolgreichem PUT (deterministisch, kein Agent-Loop).
_ANTWORT_EINGETRAGEN = "Eingetragen ✅: {titel} am {datum_fmt}"
_ANTWORT_EINGETRAGEN_ZEITGEBUNDEN = "Eingetragen ✅: {titel} am {datum_fmt}, {start_fmt} — {ende_fmt} Uhr"
_ANTWORT_EINGETRAGEN_MEHRTAGE = "Eingetragen ✅: {titel} von {beginn_fmt} bis {ende_fmt}"

# TES-3: Rückfrage bei abgelaufener oder fehlender Session.
_ANTWORT_ABGELEHNT = (
    "Termin eintragen geht nur für Mitglieder der Familien-Gruppe.")

# TES-6: Familien-Zeitzone (Default Europe/Berlin, TES-6-Spec). In V1 nicht
# aus plan.json geladen — Default ist hier Fallback-Wert. Offset wird zur
# Laufzeit über die Standard-Bibliothek ermittelt (kein externer Wert nötig
# für Europe/Berlin Sommer/Winter).
# open_question: plan.json-Zeitzone-Auslesen verbleibt als offener Punkt
# im Handoff — Default reicht für V1 (TES-6-Spec: „Default Europe/Berlin").
_DEFAULT_TZ_NAME = "Europe/Berlin"

# TES-5: Datums-Wortliste zum Herausfiltern aus dem Titel.
# Erweitert das TER-4-Vokabular um Trigger-Wörter für TES-5.
# „am" ist Datums-Präposition (z. B. „am Freitag") und kein Inhalts-Wort.
_DATUM_TOKENS = frozenset({
    "heute", "morgen",
    "montag", "dienstag", "mittwoch", "donnerstag",
    "freitag", "samstag", "sonntag",
    "mo", "di", "mi", "do", "fr", "sa", "so",
    "nächsten", "nächste", "naechsten", "naechste",
    "dieser", "diese", "nächster", "naechster",
    "woche", "am",
})

# TES-5: Trigger-Wörter, die die Absicht „eintragen" signalisieren — werden
# beim Titel-Extrahieren entfernt (kein Vokabular-Duplikat mit TER-4, nur
# TES-spezifische Semantik).
# Enthält nur echte Aktions-Verben + trennbare Verb-Partikel „ein";
# Inhaltswörter wie „bitte" und „termin" wurden entfernt (Ticket #262,
# TES-5: Titel bleibt roh — Inhaltswörter gehören in den Titel).
_TRIG_TOKENS = frozenset({
    "trag", "trage", "eintrag", "eintrage", "einträgen",
    "eintragen", "einzutragen", "erstell", "erstelle",
    "erstellen", "leg", "lege", "anlegen", "anlege",
    "termineintragen",
    "ein",   # trennbares Verb-Partikel von „eintragen/einlegen/…"
})


# ============================================================
#  TES-4 — Datum-Parsing (baut auf TER-4 auf, erweitert um Einzel-Tag)
# ============================================================

def parse_datum(text, heute=None):
    """Löst einen Anstoß-Text in ein einzelnes Termin-Datum auf (TES-4).

    Verwendet `parse_zeitraum` aus `termine_erfragen` als Basis (E-TES-4,
    geteilte Wahrheit). Zusätzlich erkennt TES Einzel-Wochentage als
    konkreten Tag — bei parse_zeitraum sind diese bereits als mehrdeutig
    (None) markiert, wir lösen sie hier auf (nächster oder aktueller
    Wochentag in der Woche, je nach Stand).

    Liefert ein `date`-Objekt oder `None` (mehrdeutig → Rückfrage, EC-22).

    Abweichungen von TER-4 (TES-4):
    - Keine Zeiträume (tage > 1) → „unklar"/Rückfrage.
    - Konkrete Wochentage ohne „nächste"-Marker → nächster solcher Tag
      ab heute (inkl. heute, wenn passend).
    - „nächsten <Wochentag>" → eindeutig nächste Woche.
    """
    if heute is None:
        heute = date.today()
    t = (text or "").lower().strip()

    # „nächsten <Wochentag>" — E-TES-4: Helfer aus termine_erfragen (SSoT).
    match_naechst = re.search(
        r"n[äa]chsten?\s+(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so)",
        t)
    if match_naechst:
        return parse_naechsten_wochentag(heute, match_naechst.group(1))

    # Konkreter Wochentag ohne „nächste"-Marker — E-TES-4: Helfer aus termine_erfragen (SSoT).
    # Wortgrenze prüfen, damit „Mittwoch" nicht „Mi" überlappt.
    for wt_name in wochentag_nr_dict():
        if re.search(r'\b' + re.escape(wt_name) + r'\b', t):
            ergebnis = parse_wochentag(wt_name, heute)
            if ergebnis is not None:
                return ergebnis

    # Alle übrigen Datums-Ausdrücke (heute, morgen, diese Woche, nächste Woche,
    # die nächsten N Tage) via parse_zeitraum aus termine_erfragen (E-TES-4).
    # Wochentage liefert parse_zeitraum als None (mehrdeutig, TER-4) — die sind
    # oben bereits abgehandelt.
    zeitraum = parse_zeitraum(t, heute=heute)
    if zeitraum is None:
        return None
    start, tage = zeitraum
    if tage == 1:
        # Einzel-Tag (heute, morgen): direktes Datum.
        return start
    # Zeitraum (z. B. „diese Woche" = 7 Tage) ist kein einzelner Tag → Rückfrage.
    return None


# ============================================================
#  TES-5 — Titel-Extraktion
# ============================================================

def extrahiere_titel(text):
    """Extrahiert den Termin-Titel aus dem Anstoß-Text (TES-5).

    V1: der Titel wird roh aus dem Text gewonnen, indem Trigger-Wörter
    (trag/eintragen/…), Datums-Ausdrücke, Datums-Token und Uhrzeit-Ausdrücke
    entfernt werden (TES-5/TES-6). Was übrig bleibt, ist der Titel. Ist das
    Ergebnis leer oder enthält es nur Datums-Vokabular, liefert die Funktion
    `""` — der Aufrufer stellt dann eine Rückfrage (TES-5).

    Keine automatische Personen-Anreicherung (OPEN-TES-B, V1 roh).
    """
    if not text:
        return ""
    # Datums-Ausdrücke mit Markern entfernen (nächsten Donnerstag etc.)
    t = re.sub(
        r'\bn[äa]chsten?\s+(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so)\b',
        '', text, flags=re.IGNORECASE)
    # Uhrzeit-Ausdrücke entfernen (TES-6): HH:MM, H Uhr, bis H Uhr, für X Stunden, X h.
    t = re.sub(r'\b(?:um|ab|von|bis)?\s*\d{1,2}(?::\d{2})?\s*uhr\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\b\d{1,2}:\d{2}\b', '', t)
    t = re.sub(r'\bf[üu]r\s+(?:\d+|eine)\s*stunden?\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\b\d+\s*h\b', '', t)
    # Alle Wörter tokenisieren und filtern
    woerter = re.findall(r'\S+', t)
    gefiltert = []
    for w in woerter:
        w_lower = w.lower().strip(",.!?-")
        if w_lower in _DATUM_TOKENS or w_lower in _TRIG_TOKENS or w_lower in _UHRZEIT_TOKENS:
            continue
        if not w.strip():
            continue
        gefiltert.append(w.strip(",.!?"))
    return " ".join(gefiltert).strip()


def _ist_nur_datum_vokabular(titel):
    """True, wenn der extrahierte Titel leer oder nur aus Datums-Vokabular
    besteht (TES-5: Rückfrage erforderlich)."""
    if not titel:
        return True
    woerter = re.findall(r'\S+', titel.lower())
    return all(w.strip(",.!?") in _DATUM_TOKENS or w.strip(",.!?") in _TRIG_TOKENS
               for w in woerter)


# ============================================================
#  TES-6 — Uhrzeit-Parsing (hart-codiert, kein LLM, EC-12)
# ============================================================

# Uhrzeit-Token zum Herausfiltern beim Titel (TES-5/TES-6).
# Diese werden aus dem Titel-Token-Filter ausgefiltert, damit „14 Uhr" etc.
# nicht im Titel erscheinen.
_UHRZEIT_TOKENS = frozenset({
    "uhr", "von", "bis", "ab", "für", "fuer", "stunden", "stunde", "h",
})


def _parse_uhrzahl(t, pos_start):
    """Liest HH:MM oder H (ganzzahlig) ab `pos_start` aus dem String `t`.

    Hilfsmethode für parse_uhrzeit — nicht für externe Nutzung.
    Gibt `(h, m, pos_end)` zurück oder `None`.
    """
    m = re.match(r'(\d{1,2}):(\d{2})', t[pos_start:])
    if m:
        return int(m.group(1)), int(m.group(2)), pos_start + m.end()
    m = re.match(r'(\d{1,2})', t[pos_start:])
    if m:
        return int(m.group(1)), 0, pos_start + m.end()
    return None


def parse_uhrzeit(text):
    """Liest Uhrzeit-Angaben aus dem Anstoß-Text (TES-6, EC-12: hart-codiert).

    Erkennt folgendes Vokabular (Spec TES-6):
    - Startuhrzeit: HH:MM, H Uhr, H:MM Uhr (ganzzahlige oder Halbstunden)
    - Enduhrzeit:  bis HH:MM, bis H Uhr
    - Dauer:       für X Stunden, X h, für eine Stunde

    Gibt ein Dict zurück:
      { "start_h": int, "start_m": int,
        "end_h": int|None, "end_m": int|None,
        "dauer_min": int|None }
    oder None, wenn kein Uhrzeit-Vokabular gefunden.

    „start_h"/„start_m" sind immer gesetzt wenn Uhrzeit vorhanden;
    bei reiner Dauer-Antwort (z. B. »für eine Stunde«) sind sie 0.
    „end_h"/„end_m" sind gesetzt, wenn eine Enduhrzeit explizit angegeben.
    „dauer_min" ist gesetzt, wenn eine Dauer angegeben.
    """
    t = (text or "").lower().strip()

    # 1. Vollständige Muster „von H:MM bis H:MM" / „H:MM bis H:MM" / „H Uhr bis H Uhr"
    #    Prüfen zuerst, bevor Teil-Matches stören.

    # „von HH:MM bis HH:MM" / „von H Uhr bis H Uhr"
    m = re.search(
        r'\bvon\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr\b)?\s*bis\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr\b)?',
        t)
    if m:
        sh, sm = int(m.group(1)), int(m.group(2) or 0)
        eh, em = int(m.group(3)), int(m.group(4) or 0)
        return {"start_h": sh, "start_m": sm, "end_h": eh, "end_m": em, "dauer_min": None}

    # „HH:MM bis HH:MM" (ohne „von") — nur wenn beide Seiten HH:MM haben
    m = re.search(r'\b(\d{1,2}):(\d{2})\s*(?:uhr\b)?\s*bis\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr\b)?', t)
    if m:
        sh, sm = int(m.group(1)), int(m.group(2))
        eh, em = int(m.group(3)), int(m.group(4) or 0)
        return {"start_h": sh, "start_m": sm, "end_h": eh, "end_m": em, "dauer_min": None}

    # „H Uhr bis H Uhr" / „H:MM Uhr bis H Uhr"
    m = re.search(
        r'\b(\d{1,2})(?::(\d{2}))?\s*uhr\b\s*bis\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr\b)?',
        t)
    if m:
        sh, sm = int(m.group(1)), int(m.group(2) or 0)
        eh, em = int(m.group(3)), int(m.group(4) or 0)
        return {"start_h": sh, "start_m": sm, "end_h": eh, "end_m": em, "dauer_min": None}

    # 2. Dauer ohne Startuhrzeit (Rückfrage-Antwort: „für eine Stunde", „2 h").
    #    Erkennen vor dem Startuhrzeit-Match, damit die Dauer-Antwort greift.
    dauer_min = None
    m_dauer = re.search(r'\bf[üu]r\s+(\d+)\s*stunden?\b', t)
    if m_dauer:
        dauer_min = int(m_dauer.group(1)) * 60
    elif re.search(r'\bf[üu]r\s+eine\s+stunde\b', t):
        dauer_min = 60

    # Startuhrzeit: HH:MM (auch ohne „Uhr"), H Uhr / ab H Uhr / um H Uhr
    start_h = start_m = None

    # HH:MM mit optionalem „Uhr"
    m_start = re.search(r'\b(?:(?:um|ab)\s+)?(\d{1,2}):(\d{2})\s*(?:uhr\b)?', t)
    if m_start:
        start_h, start_m = int(m_start.group(1)), int(m_start.group(2))
    else:
        # H Uhr / um H Uhr / ab H Uhr
        m_start2 = re.search(r'\b(?:(?:um|ab)\s+)?(\d{1,2})\s+uhr\b', t)
        if m_start2:
            start_h, start_m = int(m_start2.group(1)), 0

    if start_h is None and dauer_min is None:
        return None  # Kein Uhrzeit-Vokabular gefunden.

    # Wenn nur Dauer, aber keine Startzeit (Rückfrage-Antwort: „für eine Stunde")
    if start_h is None:
        return {"start_h": None, "start_m": None, "end_h": None, "end_m": None,
                "dauer_min": dauer_min}

    # 3. Enduhrzeit „bis HH:MM" / „bis H Uhr"
    end_h = end_m = None
    m_end = re.search(r'\bbis\s+(\d{1,2}):(\d{2})\s*(?:uhr\b)?', t)
    if m_end:
        end_h, end_m = int(m_end.group(1)), int(m_end.group(2))
    else:
        m_end2 = re.search(r'\bbis\s+(\d{1,2})\s*(?:uhr\b)?', t)
        if m_end2:
            end_h, end_m = int(m_end2.group(1)), 0

    # Dauer „X h" (nur wenn keine explizite Enduhrzeit und noch keine Dauer)
    if dauer_min is None and end_h is None:
        m_dauer3 = re.search(r'\b(\d+)\s*h\b', t)
        if m_dauer3:
            dauer_min = int(m_dauer3.group(1)) * 60

    return {
        "start_h": start_h, "start_m": start_m,
        "end_h": end_h, "end_m": end_m,
        "dauer_min": dauer_min,
    }


def _baue_zeitgebunden(tag, start_h, start_m, end_h, end_m, tz_offset_h=1):
    """Baut beginn/ende-Strings für einen zeitgebundenen Termin (TES-6, PLAN-22).

    `tz_offset_h` — UTC-Offset in Stunden (Standard: 1 für CET / Europe/Berlin Winter;
    Sommer = 2). Default 1 ist Fallback — TES-6-Spec erlaubt Default Europe/Berlin.

    Bestimmt den aktuellen UTC-Offset von Europe/Berlin via stdlib-datetime
    (keine externe Bibliothek nötig für den reinen Sommer/Winter-Wechsel).
    """
    try:
        # stdlib zoneinfo (Python ≥ 3.9) — bevorzugt, weil keine pytz-Abhängigkeit.
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(_DEFAULT_TZ_NAME)
        dt_naive = datetime(tag.year, tag.month, tag.day, start_h, start_m)
        dt_aware = dt_naive.replace(tzinfo=tz)
        offset = dt_aware.utcoffset()
        total_h = int(offset.total_seconds()) // 3600
        offset_str = "%+03d:00" % total_h
    except Exception:
        # Fallback: Europe/Berlin UTC+1 Winter, UTC+2 Sommer (grobe Näherung).
        import time as _time
        dst = _time.daylight and _time.localtime().tm_isdst
        total_h = -(_time.timezone // 3600) + (1 if dst else 0)
        offset_str = "%+03d:00" % total_h

    dt_beginn = "%04d-%02d-%02dT%02d:%02d:00%s" % (
        tag.year, tag.month, tag.day, start_h, start_m, offset_str)

    # Mitternachts-Übergang: liegt Endzeit vor Startzeit → +1 Tag (TES-6-Spec).
    end_tag = tag
    if end_h < start_h or (end_h == start_h and end_m < start_m):
        end_tag = tag + timedelta(days=1)

    dt_ende = "%04d-%02d-%02dT%02d:%02d:00%s" % (
        end_tag.year, end_tag.month, end_tag.day, end_h, end_m, offset_str)

    return dt_beginn, dt_ende


def parse_mehrtage_spanne(text, heute=None):
    """Erkennt eine Mehrtages-Spanne im Anstoß-Text (TES-6, kein Uhrzeit-Anteil).

    Vokabular:
    - „von <Tag> bis <Tag>" — Wochentag-Namen (TES-4/TER-4 SSoT)
    - „<Tag> und <Tag>"    — zwei aufeinanderfolgende Tage

    Gibt `(beginn_date, ende_date)` zurück oder `None` (kein Spann-Ausdruck).
    `heute` ist für Tests injizierbar.
    """
    if heute is None:
        heute = date.today()
    t = (text or "").lower().strip()

    # „von <Tag> bis <Tag>"
    wt_pattern = (r"(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag"
                  r"|mo|di|mi|do|fr|sa|so)")
    m = re.search(r'\bvon\s+(' + wt_pattern + r')\s+bis\s+(' + wt_pattern + r')\b', t)
    if m:
        start = parse_wochentag(m.group(1), heute)
        end = parse_wochentag(m.group(2), heute)
        if start is not None and end is not None and end >= start:
            return start, end

    # „<Tag> und <Tag>" (genau zwei Wochentag-Namen)
    m2 = re.search(r'\b(' + wt_pattern + r')\s+und\s+(' + wt_pattern + r')\b', t)
    if m2:
        start = parse_wochentag(m2.group(1), heute)
        end = parse_wochentag(m2.group(2), heute)
        if start is not None and end is not None and end >= start:
            return start, end

    return None


# ============================================================
#  TES-1 — Haupt-Funktion
# ============================================================

def termin_eintragen(tg, private_chat_id, from_user_id,
                     family_group_chat_id, anstos_text,
                     plan_client, is_member_fn, next_message,
                     heute=None,
                     typing_fn: Callable[[], None] | None = None):
    """Termin eintragen — aufrufbare Funktion (TES-1).

    Klärt einen Termin im Privatchat des Aufrufers und trägt ihn nach
    Bestätigung über die Plan-Buddy-Termin-Schnittstelle ein (PLAN-22, TES-8).

    `tg`                    — Telegram-Kanal (send_message, get_chat_member).
    `private_chat_id`       — Privatchat des Aufrufers (TES-3, Pflicht).
    `from_user_id`          — Telegram-User-ID des Aufrufers (TES-2).
    `family_group_chat_id`  — ID der gebundenen Familien-Gruppe (TES-2).
    `anstos_text`           — Natürlichsprachiger Anstoß-Text (TES-4/TES-5).
    `plan_client`           — PlanClient-Instanz (TES-8).
    `is_member_fn`          — Callable `(user_id) -> bool` (TES-2).
    `next_message`          — Callable → TesInput|None (Privatchat-Stream, TES-3).
    `heute`                 — Injektierbar für Tests (Default: date.today()).
    `typing_fn`             — Optionaler Callable ohne Argumente; wird vor jeder
                              send_message-Phase aufgerufen (EC-14: Best-Effort,
                              Fehler werden geschluckt). Default None → No-op
                              (Backward-Compat). Vgl. before_provider_call in
                              agent.py (Issue #156).

    Ergebnis-Signal (TES-1):
      „eingetragen"       — Termin angelegt (event_id aus PLAN-22).
      „verworfen"         — Vorschlag nicht bestätigt (TES-7).
      „abgebrochen"       — Session-Timeout / Prozess-Neustart (SESS-3).
      „abgelehnt"         — Berechtigung fehlt (TES-2).
      „nicht_erreichbar"  — Plan-Buddy-Fehler (TES-9).
      „unklar"            — Datum/Titel nach Rückfrage nicht ermittelbar.
    """
    if heute is None:
        heute = date.today()

    # TES-1: ohne Privatchat-ID kein Dialog.
    if private_chat_id is None:
        logger.warning("termin_eintragen: private_chat_id fehlt — Abbruch")
        return SIGNAL_ABGELEHNT

    # TES-2: Live-Berechtigung. Die Prüfung liegt bei der Funktion (E-TES-1).
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("termin_eintragen: User %s ist kein Familienmitglied — abgelehnt",
                    from_user_id)
        _fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_ABGELEHNT)
        return SIGNAL_ABGELEHNT

    # TES-6: Uhrzeit und Mehrtages-Spanne aus dem Anstoß-Text ermitteln.
    # Diese Extraktion läuft VOR dem Datum-Parsing, da Mehrtage-Spannen
    # eigene Datumsangaben enthalten.
    uhrzeit = parse_uhrzeit(anstos_text)
    mehrtage = parse_mehrtage_spanne(anstos_text, heute=heute) if uhrzeit is None else None

    if mehrtage is not None:
        # TES-6: Mehrtages-Spanne (ganztägig + beginn/ende Datum).
        beginn_tag, ende_tag = mehrtage
        if beginn_tag < heute:
            datum_str = _formatiere_datum(beginn_tag)
            _fire_typing(typing_fn)
            _send(tg, private_chat_id, _RUECKFRAGE_VERGANGENHEIT % datum_str)
            msg = next_message()
            if msg is None:
                return SIGNAL_ABGEBROCHEN
            if not confirm.is_confirmation(_get_text(msg)):
                _fire_typing(typing_fn)
                _send(tg, private_chat_id, _ANTWORT_VERWORFEN)
                return SIGNAL_VERWORFEN
        titel = extrahiere_titel(anstos_text)
        if _ist_nur_datum_vokabular(titel):
            _fire_typing(typing_fn)
            _send(tg, private_chat_id, _RUECKFRAGE_TITEL)
            msg = next_message()
            if msg is None:
                return SIGNAL_ABGEBROCHEN
            titel = _get_text(msg).strip()
            if not titel or _ist_nur_datum_vokabular(titel):
                return SIGNAL_UNKLAR
        # EC-10: vollständig (Mehrtage bekannt + Titel bekannt) → EINE Nachricht.
        _fire_typing(typing_fn)
        _send(tg, private_chat_id,
              _VORSCHLAG_TEMPLATE_MEHRTAGE % (
                  titel,
                  _formatiere_datum(beginn_tag),
                  _formatiere_datum(ende_tag)))
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        if not confirm.is_confirmation(_get_text(msg)):
            _fire_typing(typing_fn)
            _send(tg, private_chat_id, _ANTWORT_VERWORFEN)
            return SIGNAL_VERWORFEN
        try:
            event_id = plan_client.put_termin(
                titel, beginn_tag.isoformat(), ende_tag.isoformat())
        except PlanClientError as e:
            logger.warning("termin_eintragen: Plan-Buddy nicht erreichbar — %s", e)
            _fire_typing(typing_fn)
            _send(tg, private_chat_id, _ANTWORT_NICHT_ERREICHBAR)
            return SIGNAL_NICHT_ERREICHBAR
        logger.info(
            "termin_eintragen: Mehrtage-Termin »%s« %s–%s eingetragen (event_id=%s)",
            titel, beginn_tag.isoformat(), ende_tag.isoformat(), event_id)
        _fire_typing(typing_fn)
        _send(tg, private_chat_id,
              _ANTWORT_EINGETRAGEN_MEHRTAGE.format(
                  titel=titel,
                  beginn_fmt=_formatiere_datum(beginn_tag),
                  ende_fmt=_formatiere_datum(ende_tag)))
        return SIGNAL_EINGETRAGEN

    # TES-4: Datum aus Anstoß-Text ermitteln.
    tag = parse_datum(anstos_text, heute=heute)

    if tag is None:
        # Mehrdeutiger Datums-Ausdruck → eine Rückfrage (EC-22).
        _fire_typing(typing_fn)
        _send(tg, private_chat_id, _RUECKFRAGE_DATUM)
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        tag = parse_datum(_get_text(msg), heute=heute)
        if tag is None:
            return SIGNAL_UNKLAR

    # TES-4 Edge-Case Vergangenheit: einmalige Rückfrage.
    if tag < heute:
        datum_str = _formatiere_datum(tag)
        _fire_typing(typing_fn)
        _send(tg, private_chat_id, _RUECKFRAGE_VERGANGENHEIT % datum_str)
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        if not confirm.is_confirmation(_get_text(msg)):
            _fire_typing(typing_fn)
            _send(tg, private_chat_id, _ANTWORT_VERWORFEN)
            return SIGNAL_VERWORFEN

    # TES-5: Titel aus dem Anstoß-Text extrahieren.
    titel = extrahiere_titel(anstos_text)

    if _ist_nur_datum_vokabular(titel):
        # Kein erkennbarer Titel → eine Rückfrage.
        _fire_typing(typing_fn)
        _send(tg, private_chat_id, _RUECKFRAGE_TITEL)
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        titel = _get_text(msg).strip()
        if not titel or _ist_nur_datum_vokabular(titel):
            return SIGNAL_UNKLAR

    if uhrzeit is not None:
        # TES-6: Zeitgebundener Termin — beginn und ende als ISO-Datetime.
        start_h = uhrzeit["start_h"]
        start_m = uhrzeit["start_m"]
        end_h = uhrzeit.get("end_h")
        end_m = uhrzeit.get("end_m")
        dauer_min = uhrzeit.get("dauer_min")

        # Ende aus Dauer berechnen, wenn keine direkte Enduhrzeit.
        if end_h is None and dauer_min is not None:
            total_m = start_h * 60 + start_m + dauer_min
            end_h = (total_m // 60) % 24
            end_m = total_m % 60

        if end_h is None:
            # Nur Startzeit → gezielte Rückfrage nach Enduhrzeit oder Dauer (EC-22).
            _fire_typing(typing_fn)
            _send(tg, private_chat_id, _RUECKFRAGE_ENDZEIT)
            msg = next_message()
            if msg is None:
                return SIGNAL_ABGEBROCHEN
            antwort_text = _get_text(msg)
            end_info = parse_uhrzeit(antwort_text)
            if end_info is not None:
                if end_info.get("end_h") is not None:
                    end_h, end_m = end_info["end_h"], end_info["end_m"]
                elif end_info.get("dauer_min") is not None:
                    total_m = start_h * 60 + start_m + end_info["dauer_min"]
                    end_h, end_m = (total_m // 60) % 24, total_m % 60
                else:
                    # Nur Startzeit in Antwort → als Enduhrzeit interpretieren.
                    end_h, end_m = end_info["start_h"], end_info["start_m"]
            else:
                return SIGNAL_UNKLAR

        # Validierung: ende muss nach beginn liegen (mod. Mitternacht wird in
        # _baue_zeitgebunden behandelt).
        dt_beginn, dt_ende = _baue_zeitgebunden(tag, start_h, start_m, end_h, end_m)

        start_fmt = "%02d:%02d" % (start_h, start_m)
        ende_fmt = "%02d:%02d" % (end_h, end_m)
        datum_str = _formatiere_datum(tag)

        # EC-10: vollständig (Tag+Titel+Start+Ende alle bekannt) → EINE Nachricht.
        _fire_typing(typing_fn)
        _send(tg, private_chat_id,
              _VORSCHLAG_TEMPLATE_ZEITGEBUNDEN % (titel, datum_str, start_fmt, ende_fmt))
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        if not confirm.is_confirmation(_get_text(msg)):
            _fire_typing(typing_fn)
            _send(tg, private_chat_id, _ANTWORT_VERWORFEN)
            return SIGNAL_VERWORFEN

        try:
            event_id = plan_client.put_termin(titel, dt_beginn, dt_ende)
        except PlanClientError as e:
            logger.warning("termin_eintragen: Plan-Buddy nicht erreichbar — %s", e)
            _fire_typing(typing_fn)
            _send(tg, private_chat_id, _ANTWORT_NICHT_ERREICHBAR)
            return SIGNAL_NICHT_ERREICHBAR

        logger.info(
            "termin_eintragen: Zeitgebundener Termin »%s« am %s %s–%s eingetragen "
            "(event_id=%s)", titel, tag.isoformat(), start_fmt, ende_fmt, event_id)
        _fire_typing(typing_fn)
        _send(tg, private_chat_id,
              _ANTWORT_EINGETRAGEN_ZEITGEBUNDEN.format(
                  titel=titel,
                  datum_fmt=datum_str,
                  start_fmt=start_fmt,
                  ende_fmt=ende_fmt))
        return SIGNAL_EINGETRAGEN

    # TES-6: Ganztägig eintägig (kein Uhrzeit, keine Mehrtage).
    # EC-10: vollständig (Tag+Titel bekannt) → EINE kombinierte Nachricht.
    # TES-7: Vorschlag + Bestätigungswort vor dem PUT.
    datum_str = _formatiere_datum(tag)
    _fire_typing(typing_fn)
    _send(tg, private_chat_id, _VORSCHLAG_TEMPLATE_GANZTAGS % (titel, datum_str))
    msg = next_message()
    if msg is None:
        return SIGNAL_ABGEBROCHEN
    if not confirm.is_confirmation(_get_text(msg)):
        _fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_VERWORFEN)
        return SIGNAL_VERWORFEN

    # TES-8: Termin über Plan-Buddy-Schnittstelle anlegen (ganztägig eintägig).
    try:
        event_id = plan_client.put_termin(titel, tag.isoformat())
    except PlanClientError as e:
        logger.warning("termin_eintragen: Plan-Buddy nicht erreichbar — %s", e)
        _fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_NICHT_ERREICHBAR)
        return SIGNAL_NICHT_ERREICHBAR

    logger.info("termin_eintragen: Termin »%s« am %s eingetragen (event_id=%s)",
                titel, tag.isoformat(), event_id)
    _fire_typing(typing_fn)
    _send(tg, private_chat_id,
          _ANTWORT_EINGETRAGEN.format(titel=titel, datum_fmt=_formatiere_datum(tag)))
    return SIGNAL_EINGETRAGEN


# ============================================================
#  Helpers
# ============================================================

def _fire_typing(typing_fn):
    """Ruft typing_fn auf, wenn gesetzt — Fehler werden geschluckt (EC-14: Best-Effort).

    Analog `before_provider_call` in agent.py (Issue #156): der Typing-Indikator
    ist Komfort, kein Gate. Scheitert der Aufruf (z. B. wegen TelegramError),
    läuft termin_eintragen() trotzdem durch.
    """
    if typing_fn is None:
        return
    try:
        typing_fn()
    except Exception:  # noqa: BLE001 — Typing ist Komfort, kein Gate
        logger.debug("_fire_typing: Aufruf fehlgeschlagen (geschluckt)", exc_info=True)


def _get_text(msg):
    """Liest den Text aus einem TesInput-Objekt oder einem String."""
    if hasattr(msg, "text"):
        return (msg.text or "").strip()
    return (msg or "").strip()


def _formatiere_datum(tag):
    """Formatiert ein date-Objekt als lesbare Datumsangabe (TT.MM.JJJJ)."""
    return "%02d.%02d.%04d" % (tag.day, tag.month, tag.year)


def _send(tg, chat_id, text):
    """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt,
    aber brechen die Funktion nicht ab — analog `familie_anlegen._send`."""
    try:
        tg.send_message(chat_id, text)
    except TelegramError as e:
        logger.warning("termin_eintragen: Senden an %s fehlgeschlagen: %s",
                       chat_id, e)
