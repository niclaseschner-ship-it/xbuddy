"""Hörspiel-Buddy — LLM-Provider Basis-Schnittstelle (HSP-10).

Ein konkreter Provider erbt von `LLMProvider` und implementiert
`complete` (freier Text-Output, Synopse-Pfad HSP-16) sowie
`complete_structured` (Schema-gebundener Output, Folgen-Vorschlag HSP-11).

V2-Anker: ein zweiter Provider (`mistral.py`, OPEN-HSP-N) tritt hinter
dieselbe Schnittstelle, ohne dass `llm_service` oder `album_builder`
geändert werden müssen.
"""

from typing import Any


class ProviderError(Exception):
    """Provider nicht erreichbar oder antwortet fehlerhaft (HSP-17 → HTTP 503)."""


class LLMProvider:
    """Provider-Basis. Konkrete Implementierungen liefern `complete`
    (freier Text) und `complete_structured` (strukturierte Tool-Antwort).

    Die strukturierte Form ist wichtig für den Folgen-Vorschlag (HSP-11):
    der Folgentext enthält wörtliche Rede mit Anführungszeichen, ein
    json-stringifiziertes Format-Beispiel im System-Prompt produziert
    daher unzuverlässig parsebares JSON. Anthropics tool_use erzwingt
    wohlgeformte Antworten.
    """

    name: str = ""
    model: str = ""

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def complete_structured(self, system: str, user: str, *,
                            tool_name: str,
                            tool_description: str,
                            input_schema: dict) -> dict[str, Any]:
        raise NotImplementedError
