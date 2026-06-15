"""KIBuddy — Icon-Render-Hilfsmodul (KIBUDDY-17 Buzzword-Refactor, T865).

Wortklassen-Filter, Tokenisierung und die Funktionswort-Default-Datei sind
mit T865 ersatzlos entfernt — LLM liefert direkt 3 Buzzwords, Client fetched
Icons pro Buzzword (KIBUDDY-17).

Einzig verbleibende öffentliche Funktion: validate_buzzwords() — sanitisiert
die Buzzword-Liste aus der LLM-JSON-Antwort.
"""

import logging

logger = logging.getLogger(__name__)


def validate_buzzwords(raw_list) -> list[str]:
    """Sanitisiert Buzzword-Liste vom LLM.

    Akzeptiert eine rohe Liste (beliebiger Typ), gibt max 3 bereinigte
    lowercase-Strings zurück. Leere Einträge werden übersprungen.
    """
    if not isinstance(raw_list, list):
        return []
    cleaned = []
    for item in raw_list:
        if isinstance(item, str):
            w = item.strip().lower()
            if w:
                cleaned.append(w)
    return cleaned[:3]
