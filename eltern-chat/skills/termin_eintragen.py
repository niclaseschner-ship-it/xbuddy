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
from datetime import date

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
# Vorschlag enthält Titel + Tag, Bestätigungswort erforderlich (E-EC-7).
_VORSCHLAG_TEMPLATE = (
    "Soll ich diesen Termin eintragen?\n"
    "• Titel: %s\n"
    "• Tag: %s\n\n"
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

# TES-7: Antwort bei Nicht-Bestätigung.
_ANTWORT_VERWORFEN = (
    "Ok — kein Termin eingetragen. Wenn du es erneut versuchen möchtest, "
    "formuliere einfach eine neue Anfrage.")

# TES-7: Quittung nach erfolgreichem PUT (E-EC-7: deterministische Bestätigung).
_ANTWORT_EINGETRAGEN = "Eingetragen ✅: {titel} am {datum_fmt}"

# TES-3: Rückfrage bei abgelaufener oder fehlender Session.
_ANTWORT_ABGELEHNT = (
    "Termin eintragen geht nur für Mitglieder der Familien-Gruppe.")

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
    (trag/eintragen/…), Datums-Ausdrücke und Datums-Token entfernt werden.
    Was übrig bleibt, ist der Titel. Ist das Ergebnis leer oder enthält es
    nur Datums-Vokabular, liefert die Funktion `""` — der Aufrufer stellt
    dann eine Rückfrage (TES-5).

    Keine automatische Personen-Anreicherung (OPEN-TES-B, V1 roh).
    """
    if not text:
        return ""
    # Datums-Ausdrücke mit Markern entfernen (nächsten Donnerstag etc.)
    t = re.sub(
        r'\bn[äa]chsten?\s+(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|mo|di|mi|do|fr|sa|so)\b',
        '', text, flags=re.IGNORECASE)
    # Alle Wörter tokenisieren und filtern
    woerter = re.findall(r'\S+', t)
    gefiltert = []
    for w in woerter:
        w_lower = w.lower().strip(",.!?-")
        if w_lower in _DATUM_TOKENS or w_lower in _TRIG_TOKENS:
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
#  TES-1 — Haupt-Funktion
# ============================================================

def termin_eintragen(tg, private_chat_id, from_user_id,
                     family_group_chat_id, anstos_text,
                     plan_client, is_member_fn, next_message,
                     heute=None):
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
        _send(tg, private_chat_id, _ANTWORT_ABGELEHNT)
        return SIGNAL_ABGELEHNT

    # TES-4: Datum aus Anstoß-Text ermitteln.
    tag = parse_datum(anstos_text, heute=heute)

    if tag is None:
        # Mehrdeutiger Datums-Ausdruck → eine Rückfrage (EC-22).
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
        _send(tg, private_chat_id, _RUECKFRAGE_VERGANGENHEIT % datum_str)
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        if not confirm.is_confirmation(_get_text(msg)):
            _send(tg, private_chat_id, _ANTWORT_VERWORFEN)
            return SIGNAL_VERWORFEN

    # TES-5: Titel aus dem Anstoß-Text extrahieren.
    titel = extrahiere_titel(anstos_text)

    if _ist_nur_datum_vokabular(titel):
        # Kein erkennbarer Titel → eine Rückfrage.
        _send(tg, private_chat_id, _RUECKFRAGE_TITEL)
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        titel = _get_text(msg).strip()
        if not titel or _ist_nur_datum_vokabular(titel):
            return SIGNAL_UNKLAR

    # TES-7: Vorschlag + Bestätigungswort vor dem PUT.
    datum_str = _formatiere_datum(tag)
    _send(tg, private_chat_id, _VORSCHLAG_TEMPLATE % (titel, datum_str))
    msg = next_message()
    if msg is None:
        return SIGNAL_ABGEBROCHEN
    if not confirm.is_confirmation(_get_text(msg)):
        _send(tg, private_chat_id, _ANTWORT_VERWORFEN)
        return SIGNAL_VERWORFEN

    # TES-8: Termin über Plan-Buddy-Schnittstelle anlegen.
    try:
        event_id = plan_client.put_termin(titel, tag.isoformat())
    except PlanClientError as e:
        logger.warning("termin_eintragen: Plan-Buddy nicht erreichbar — %s", e)
        _send(tg, private_chat_id, _ANTWORT_NICHT_ERREICHBAR)
        return SIGNAL_NICHT_ERREICHBAR

    logger.info("termin_eintragen: Termin »%s« am %s eingetragen (event_id=%s)",
                titel, tag.isoformat(), event_id)
    _send(tg, private_chat_id,
          _ANTWORT_EINGETRAGEN.format(titel=titel, datum_fmt=_formatiere_datum(tag)))
    return SIGNAL_EINGETRAGEN


# ============================================================
#  Helpers
# ============================================================

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
