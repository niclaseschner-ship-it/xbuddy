"""KIBuddy — Icon-Render-Hilfsmodul (KIBUDDY-17 Buzzword-Refactor, T865).

Wortklassen-Filter und Tokenisierung sind entfernt.
Die per-Instanz-Datei kibuddy/data/funktionswort-liste.default.txt bleibt
liegen (nicht löschen), wird aber von diesem Modul nicht mehr geladen.

Einzig verbleibende öffentliche Funktion: validate_buzzwords() — sanitisiert
die Buzzword-Liste aus der LLM-JSON-Antwort (AC6-Vereinfachungen, T865).
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
