"""Routine-Punkte lesen — specs/platform/routine-punkte-setzen.md
(RPS-3 V1.2, EC-9).

Aufrufbare, trigger-agnostische Funktion (RPS-3 V1.2, EC-9):
liest die aktuelle Items-Liste des Routine-Buddys (ROUTINE-14) und
liefert eine formatierte Antwort. Lesend — kein propose→confirm
(EC-9: trigger-agnostisch, E-RPS-1 betrifft nur Schreiben).

Ausgang: Ergebnis-Tuple `(signal, daten)`:
  („gelesen",          {"default": […], "einmalig_heute": […],
                        "text": <str>})          — Lese-Antwort (V1.2).
  („nicht_erreichbar", {"detail": <str>})        — Buddy nicht erreichbar.
  („abgelehnt",        {})                       — Nicht-Mitglied (RPS-2).
"""

import logging

from skills.routine_client import RoutineClientError

logger = logging.getLogger(__name__)


# RPS-3 V1.2: Ergebnis-Signale der Lese-Funktion.
SIGNAL_GELESEN          = "gelesen"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"
SIGNAL_ABGELEHNT        = "abgelehnt"


def routine_punkte_lesen(*, routine_client, is_member_fn, from_user_id):
    """Routine-Punkte lesen — aufrufbare Funktion (RPS-3 V1.2, EC-9).

    Eine **lesende** Aufgabe (EC-9): keine propose→confirm-Schiene —
    direkter Output, kein Schreiben.

    `routine_client` — RoutineClient-Instanz mit get_items()-Methode (RPS-6).
    `is_member_fn`   — Callable `(user_id) -> bool` (RPS-2).
    `from_user_id`   — Telegram-User-ID des Aufrufers (RPS-2).

    Ergebnis: (signal, daten) — siehe Modul-Docstring.
    """
    # RPS-2: Berechtigung — live geprüft, identisch zum RZS-/FSE-Muster.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("routine_punkte_lesen: User %s nicht in Familien-Gruppe "
                    "— abgelehnt (RPS-2)", from_user_id)
        return SIGNAL_ABGELEHNT, {}

    return _lesen(routine_client)


def _lesen(routine_client):
    """RPS-3 V1.2: Aktuelle Items-Liste lesen (EC-9 — trigger-agnostisch).

    Kein propose→confirm (E-RPS-1 betrifft nur Schreiben). Die Antwort
    ist ein formatierter Text im Format aus RPS-3 V1.2:
      „**Dauerhaft:** 1. Anziehen 👕 · 2. Frühstücken 🍞 · 3. Zähne putzen 🪥
       · **Heute zusätzlich:** 1. Turnbeutel 🎒."

    Liefert SIGNAL_GELESEN mit den Rohdaten (default/einmalig_heute) und
    dem formatierten Text.
    """
    try:
        daten = routine_client.get_items()
    except RoutineClientError as e:
        fehler_str = str(e)
        logger.warning("routine_punkte_lesen: Routine-Buddy nicht erreichbar — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}

    default_items = daten.get("default") or []
    einmalig_items = daten.get("einmalig_heute") or []

    # Format: „Dauerhaft: 1. Label 🔣 · 2. … · Heute zusätzlich: 1. …"
    teile = []
    if default_items:
        einzel = " · ".join(
            "%d. %s %s" % (i + 1, item.get("label", ""),
                           item.get("piktogramm", ""))
            for i, item in enumerate(default_items)
        )
        teile.append("**Dauerhaft:** " + einzel)
    else:
        teile.append("**Dauerhaft:** (keine Punkte)")

    if einmalig_items:
        einzel = " · ".join(
            "%d. %s %s" % (i + 1, item.get("label", ""),
                           item.get("piktogramm", ""))
            for i, item in enumerate(einmalig_items)
        )
        teile.append("**Heute zusätzlich:** " + einzel)

    text = " · ".join(teile) + "."

    logger.info("routine_punkte_lesen: Liste gelesen — %d default, %d einmalig",
                len(default_items), len(einmalig_items))
    return SIGNAL_GELESEN, {
        "default": default_items,
        "einmalig_heute": einmalig_items,
        "text": text,
    }
