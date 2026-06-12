"""Hörspiel-Buddy — LLM-Provider Basis-Schnittstelle (HSP-10).

Ein konkreter Provider erbt von `LLMProvider` und implementiert `complete`.
Der `llm_service` ruft nur diese eine Methode — keine Provider-spezifischen
Typen verlassen das Provider-Modul.

V2-Anker: ein zweiter Provider (`mistral.py`, OPEN-HSP-N) tritt hinter
dieselbe Schnittstelle, ohne dass `llm_service` oder `album_builder`
geändert werden müssen.
"""


class ProviderError(Exception):
    """Provider nicht erreichbar oder antwortet fehlerhaft (HSP-17 → HTTP 503)."""


class LLMProvider:
    """Provider-Basis. Konkrete Implementierungen liefern `complete`.

    `complete(system, user)` schickt einen einzelnen User-Turn an das Modell
    und gibt den Antwort-Text zurück. Mehrturn-Verläufe sind in V1 nicht
    nötig — Folgen-Vorschlag und Synopse sind Einzel-Calls (HSP-11/HSP-16).
    """

    name: str = ""
    model: str = ""

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError
