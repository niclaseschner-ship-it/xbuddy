"""Routine-Zeiten setzen — specs/platform/routine-zeiten-setzen.md (RZS-1 … RZS-7).

Aufrufbare, trigger-agnostische Funktion (RZS-1, E-RZS-1): klärt die gewünschte
Routine-Zeit im Telegram-Privatchat des Aufrufers, schreibt sie nach ausdrücklicher
Bestätigung über die Routine-Buddy-Schnittstelle (ROUTINE-14, RZS-6) und liefert
ein Ergebnis-Signal zurück.

Bewusste Copy der TES-Linie (RAT-6, RAT-12 — keine gemeinsame Abstraktion).

V1 synchron (RZS-7): ein globaler Einzelwert, kein mehrstufiger Sammel-Dialog.
Die EC-10-Bestätigung (propose/execute) ist die einzige Bestätigung; die Funktion
schreibt direkt nach dem Aufruf (kein Privatchat-internes Confirmation-Gate).
Bei unvollständigem Anstoß stellt sie gezielte Rückfragen via next_message (EC-22).

Eingang: Telegram-Privatchat-ID, User-ID (Berechtigung RZS-2), freier
Anstoß-Text (Zeit-Art/Wert-Parsing RZS-3/RZS-4), next_message-Callable
(Privatchat-Stream, RZS-4), RoutineClient (RZS-6), is_member_fn (RZS-2).

Ausgang: Ergebnis-Signal als String (RZS-1):
  „gesetzt"           — Zeiten-Wert geschrieben, PUT erfolgreich.
  „abgebrochen"       — Session-Timeout oder Prozess-Neustart (SESS-3).
  „abgelehnt"         — Berechtigung fehlt (RZS-2).
  „nicht_erreichbar"  — Routine-Buddy nicht erreichbar oder PUT fehlgeschlagen (RZS-5).
  „unklar"            — Zeit-Art/Wert nicht ermittelbar, Rückfrage ohne Antwort (RZS-4).
"""

import logging
import re
from collections.abc import Callable

from telegram import TelegramError

from skills.routine_client import RoutineClientError
from skills.typing_indicator import fire_typing

logger = logging.getLogger(__name__)


# RZS-1: Ergebnis-Signale der Funktion.
SIGNAL_GESETZT          = "gesetzt"
SIGNAL_ABGEBROCHEN      = "abgebrochen"
SIGNAL_ABGELEHNT        = "abgelehnt"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"
SIGNAL_UNKLAR           = "unklar"

# RZS-3: Erlaubte Zeit-Arten und ihre menschenlesbaren Namen.
ZEIT_ARTEN = {
    "abfahrtszeit":       "Abfahrtszeit",
    "aufstehzeit":        "Aufstehzeit",
    "anzieh_vorlauf_min": "Anzieh-Vorlauf (Minuten)",
}

# RZS-3 / RZS-4: Schlüsselwörter, mit denen eine Zeit-Art erkannt wird.
# Reihenfolge: spezifischeres zuerst (anzieh vor abfahrt).
_ZEIT_ART_TRIGGER = [
    ("anzieh_vorlauf_min", ["anzieh", "vorlauf", "anziehzeit", "anziehen"]),
    ("abfahrtszeit",       ["abfahrt", "losgehen", "abfahrtszeit"]),
    ("aufstehzeit",        ["aufsteh", "aufwach", "aufstehzeit"]),
]

# RZS-4: Rückfrage-Texte (EC-22).
_RUECKFRAGE_ZEIT_ART = (
    "Welche Zeit möchtest du setzen? Sag zum Beispiel »Abfahrtszeit«, "
    "»Aufstehzeit« oder »Anzieh-Vorlauf«.")
_RUECKFRAGE_WERT_UHRZEIT = (
    "Auf welche Uhrzeit? Sag zum Beispiel »08:15« oder »7 Uhr 30«.")
_RUECKFRAGE_WERT_MINUTEN = (
    "Wie viele Minuten? Sag zum Beispiel »10« oder »15 Minuten«.")

# RZS-5: Ehrliche Antwort bei 4xx vom Buddy (EC-7).
_ANTWORT_UNGUELTIG = (
    "Der Routine-Buddy hat den Wert abgelehnt — bitte prüfe das Format "
    "(z. B. HH:MM für Zeiten) und versuche es erneut.")

# RZS-5: Ehrliche Antwort bei nicht erreichbarem Routine-Buddy (EC-7).
_ANTWORT_NICHT_ERREICHBAR = (
    "Der Routine-Buddy ist gerade nicht erreichbar — ich konnte die Zeit "
    "nicht setzen, bitte gleich nochmal probieren.")

# RZS-2: Antwort bei fehlender Berechtigung.
_ANTWORT_ABGELEHNT = (
    "Routine-Zeiten setzen geht nur für Mitglieder der Familien-Gruppe.")

# RZS-5: Erfolgs-Quittung nach erfolgreichem PUT (EC-21, ROUTINE-14 Reload-on-Read).
_ANTWORT_GESETZT_UHRZEIT = (
    "%s gesetzt auf %s — beim nächsten Öffnen des Routine-Displays sichtbar.")
_ANTWORT_GESETZT_MINUTEN = (
    "%s gesetzt auf %d Minuten — beim nächsten Öffnen des Routine-Displays sichtbar.")


# ============================================================
#  RZS-3 — Zeit-Art- und Wert-Parsing
# ============================================================

def _erkenne_zeit_art(text):
    """Erkennt die Zeit-Art aus dem Text (RZS-3).

    Gibt einen der ZEIT_ARTEN-Schlüssel zurück oder None (→ Rückfrage).
    """
    t = (text or "").lower()
    for schluessel, trigger in _ZEIT_ART_TRIGGER:
        for tok in trigger:
            if tok in t:
                return schluessel
    return None


def _erkenne_uhrzeit(text):
    """Erkennt einen HH:MM-Wert im Text (RZS-3).

    Erkennt:
    - HH:MM (z. B. 08:15, 7:30)
    - H Uhr [MM] (z. B. 8 Uhr, 7 Uhr 30)
    - H:MM Uhr
    Gibt einen normalisierten „HH:MM"-String zurück oder None.
    """
    t = (text or "").strip()

    # HH:MM [Uhr]
    m = re.search(r'\b(\d{1,2}):(\d{2})\s*(?:uhr\b)?', t, re.IGNORECASE)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return "%02d:%02d" % (h, mi)

    # H Uhr [MM] — z. B. „8 Uhr", „8 Uhr 30"
    m = re.search(r'\b(\d{1,2})\s+uhr\s*(\d{1,2})?\b', t, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) is not None else 0
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return "%02d:%02d" % (h, mi)

    return None


def _erkenne_minuten(text):
    """Erkennt einen ganzzahligen Minuten-Wert ≥ 0 im Text (RZS-3).

    Gibt int zurück oder None.
    """
    t = (text or "").strip()
    m = re.search(r'\b(\d+)\s*(?:min(?:uten?)?)?\b', t, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# ============================================================
#  RZS-1 — Haupt-Funktion
# ============================================================

def routine_zeiten_setzen(tg, private_chat_id, from_user_id,
                          family_group_chat_id, anstos_text,
                          routine_client, is_member_fn, next_message,
                          typing_fn: Callable[[], None] | None = None):
    """Routine-Zeiten setzen — aufrufbare Funktion (RZS-1).

    Klärt die gewünschte Zeit und schreibt sie über die Routine-Buddy-
    Schnittstelle (ROUTINE-14, RZS-6). Die EC-10-Bestätigung (propose/execute
    auf Agent-Ebene) ist die einzige Bestätigung — diese Funktion schreibt
    direkt nach Aufruf und wartet nicht auf eine Privatchat-interne Bestätigung.

    Bei unvollständigem Anstoß stellt die Funktion gezielte Rückfragen über
    `next_message` (EC-22). In V1-Sync-Kontext gibt next_message None zurück →
    SIGNAL_UNKLAR / SIGNAL_ABGEBROCHEN.

    `tg`                    — Telegram-Kanal (send_message, get_chat_member).
    `private_chat_id`       — Privatchat des Aufrufers (RZS-4, Pflicht).
    `from_user_id`          — Telegram-User-ID des Aufrufers (RZS-2).
    `family_group_chat_id`  — ID der gebundenen Familien-Gruppe (RZS-2).
    `anstos_text`           — Natürlichsprachiger Anstoß-Text (RZS-3/RZS-4).
    `routine_client`        — RoutineClient-Instanz (RZS-6).
    `is_member_fn`          — Callable `(user_id) -> bool` (RZS-2).
    `next_message`          — Callable → Nachricht|None (Privatchat-Stream, RZS-4).
    `typing_fn`             — Optionaler Callable ohne Argumente; Best-Effort
                              Typing-Indikator (EC-25). Default None → No-op.

    Ergebnis-Signal (RZS-1):
      „gesetzt"           — Zeit-Wert gesetzt.
      „abgebrochen"       — next_message lieferte None (SESS-3).
      „abgelehnt"         — Berechtigung fehlt (RZS-2).
      „nicht_erreichbar"  — Routine-Buddy-Fehler (RZS-5, EC-7).
      „unklar"            — Zeit-Art/Wert nach Rückfrage nicht ermittelbar.
    """
    # RZS-1: ohne Privatchat-ID kein Dialog.
    if private_chat_id is None:
        logger.warning("routine_zeiten_setzen: private_chat_id fehlt — Abbruch")
        return SIGNAL_ABGELEHNT

    # RZS-2: Live-Berechtigung. Die Prüfung liegt bei der Funktion (E-RZS-1).
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("routine_zeiten_setzen: User %s ist kein Familienmitglied — abgelehnt",
                    from_user_id)
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_ABGELEHNT)
        return SIGNAL_ABGELEHNT

    # RZS-3 / RZS-4: Zeit-Art aus dem Anstoß-Text ermitteln.
    zeit_art = _erkenne_zeit_art(anstos_text)

    if zeit_art is None:
        # Unvollständiger Anstoß → gezielte Rückfrage nach der Zeit-Art (EC-22).
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _RUECKFRAGE_ZEIT_ART)
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        zeit_art = _erkenne_zeit_art(_get_text(msg))
        if zeit_art is None:
            return SIGNAL_UNKLAR

    ist_minuten = (zeit_art == "anzieh_vorlauf_min")
    zeit_art_name = ZEIT_ARTEN[zeit_art]

    # RZS-3 / RZS-4: Wert aus dem Anstoß-Text ermitteln.
    wert = _erkenne_minuten(anstos_text) if ist_minuten else _erkenne_uhrzeit(anstos_text)

    if wert is None:
        # Kein Wert im Anstoß-Text → gezielte Rückfrage nach dem Wert (EC-22).
        fire_typing(typing_fn)
        if ist_minuten:
            _send(tg, private_chat_id, _RUECKFRAGE_WERT_MINUTEN)
        else:
            _send(tg, private_chat_id, _RUECKFRAGE_WERT_UHRZEIT)
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        wert = _erkenne_minuten(_get_text(msg)) if ist_minuten else _erkenne_uhrzeit(_get_text(msg))
        if wert is None:
            return SIGNAL_UNKLAR

    # RZS-6 / APP-3: Schreiben über die Routine-API (nie direkt in routine.json).
    payload = {zeit_art: wert}
    try:
        routine_client.put_config(payload)
    except RoutineClientError as e:
        logger.warning("routine_zeiten_setzen: Routine-Buddy-Fehler — %s", e)
        # 4xx: Buddy-Validierungsfehler → ehrliche Grenze (EC-7, RZS-5).
        fehler_str = str(e)
        if "HTTP 4" in fehler_str:
            fire_typing(typing_fn)
            _send(tg, private_chat_id, _ANTWORT_UNGUELTIG)
        else:
            fire_typing(typing_fn)
            _send(tg, private_chat_id, _ANTWORT_NICHT_ERREICHBAR)
        return SIGNAL_NICHT_ERREICHBAR

    logger.info(
        "routine_zeiten_setzen: %s=%r gesetzt (User %s)",
        zeit_art, wert, from_user_id)

    # RZS-5: Erfolgs-Quittung (EC-21 via Reload-on-Read, ROUTINE-14).
    fire_typing(typing_fn)
    if ist_minuten:
        _send(tg, private_chat_id,
              _ANTWORT_GESETZT_MINUTEN % (zeit_art_name, wert))
    else:
        _send(tg, private_chat_id,
              _ANTWORT_GESETZT_UHRZEIT % (zeit_art_name, wert))
    return SIGNAL_GESETZT


# ============================================================
#  Helpers
# ============================================================

def _get_text(msg):
    """Liest den Text aus einem Nachricht-Objekt oder einem String."""
    if hasattr(msg, "text"):
        return (msg.text or "").strip()
    return (msg or "").strip()


def _send(tg, chat_id, text):
    """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt,
    aber brechen die Funktion nicht ab — analog termin_eintragen._send."""
    try:
        tg.send_message(chat_id, text)
    except TelegramError as e:
        logger.warning("routine_zeiten_setzen: Senden an %s fehlgeschlagen: %s",
                       chat_id, e)
