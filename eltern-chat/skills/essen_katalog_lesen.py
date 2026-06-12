"""Essens-Katalog lesen — specs/buddies/essen.md (ESSEN-22 V1.1, EC-9).

Aufrufbare, trigger-agnostische Funktion (ESSEN-22 V1.1 Vor-Routing, EC-9):
liest den Essens-Katalog (Gerichte + Lebensmittel-Items) und liefert eine
strukturierte Antwort für den LLM-Lookup. Lesend — kein propose→confirm
(EC-9: trigger-agnostisch, kein Schreiben).

Zweck: Das Bot-LLM ruft diese Funktion VOR essen_foto_setzen, um
Caption-Items gegen Gerichte und Basis-Items im Katalog zu matchen.
So landet essen_foto_setzen mit konkretem gericht_id oder item_id
(ESSEN-22 V1.1 Vor-Routing).

Ausgang: Ergebnis-Tuple `(signal, daten)`:
  („gelesen",          {"kategorien": [<item-dict>, ...]}) — Katalog gelesen.
  („nicht_erreichbar", {"detail": <str>})                  — Buddy nicht erreichbar.
  („abgelehnt",        {})                                 — Nicht-Mitglied (EC-2).

Jedes Item-Dict enthält: id, label, bild_ref (kann fehlen), foto_ref (optional).
"""

import logging

from skills.essen_client import EssenClientError

logger = logging.getLogger(__name__)


# ESSEN-22 V1.1: Ergebnis-Signale der Lese-Funktion.
SIGNAL_GELESEN          = "gelesen"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"
SIGNAL_ABGELEHNT        = "abgelehnt"


def essen_katalog_lesen(*, essen_client, is_member_fn, from_user_id):
    """Essens-Katalog lesen — aufrufbare Funktion (ESSEN-22 V1.1, EC-9).

    Eine **lesende** Aufgabe (EC-9): keine propose→confirm-Schiene —
    direkter Output, kein Schreiben.

    `essen_client`  — EssenClient-Instanz mit lese_katalog()-Methode (ESSEN-18).
    `is_member_fn`  — Callable `(user_id) -> bool` (EC-2).
    `from_user_id`  — Telegram-User-ID des Aufrufers (EC-2).

    Ergebnis: (signal, daten) — siehe Modul-Docstring.
    """
    # EC-2: Berechtigung — live geprüft, identisch zum RPL-/RZS-/FSE-Muster.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "essen_katalog_lesen: User %s nicht in Familien-Gruppe — abgelehnt (EC-2)",
            from_user_id)
        return SIGNAL_ABGELEHNT, {}

    return _lesen(essen_client)


def _lesen(essen_client):
    """ESSEN-22 V1.1: Katalog lesen (EC-9 — trigger-agnostisch).

    lese_katalog() liefert eine flache Liste aller Items über alle
    Kategorien (inklusive Gerichte). Das reicht für das LLM, um Caption-
    Items per id/label-Match zu finden.

    Liefert SIGNAL_GELESEN mit der Item-Liste unter dem Schlüssel
    'kategorien' (rückwärtskompatibles Strukturformat).
    """
    try:
        items = essen_client.lese_katalog()
    except EssenClientError as e:
        fehler_str = str(e)
        logger.warning("essen_katalog_lesen: Essens-Buddy nicht erreichbar — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}

    if not isinstance(items, list):
        items = []

    logger.info("essen_katalog_lesen: Katalog gelesen — %d Items", len(items))
    return SIGNAL_GELESEN, {"kategorien": items}
