"""KIBuddy — LLM-Provider Basis-Schnittstelle (KIBUDDY-14).

Ein konkreter Provider erbt von `LLMProvider` und implementiert
`complete_multiturn` (Mehrturn-Kontext mit Turn-Liste, KIBUDDY-16).

V2-Anker: ein zweiter Provider tritt hinter dieselbe Schnittstelle,
ohne dass `llm_service` geändert werden muss (OPEN-KIBUDDY-D).
"""

from typing import Any


class ProviderError(Exception):
    """Provider nicht erreichbar oder antwortet fehlerhaft (→ HTTP 503)."""


class LLMProvider:
    """Provider-Basis. Konkrete Implementierungen liefern `complete_multiturn`
    (Mehrturn mit Session-History, KIBUDDY-16).
    """

    name: str = ""
    model: str = ""

    def complete_multiturn(
        self,
        system: str,
        turns: list[dict[str, Any]],
        user_message: str,
    ) -> str:
        """Sendet System-Prompt + Turn-Historie + neue Kind-Frage an den LLM.

        `turns` ist eine Liste von {"role": "user"|"assistant", "content": str}.
        Gibt den Antwort-Text zurück. Wirft ProviderError bei Anbieter-Fehler.
        """
        raise NotImplementedError
