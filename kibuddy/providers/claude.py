"""KIBuddy — Claude-Provider (KIBUDDY-14).

Übersetzt System-Prompt + Mehrturn-History + neue Kind-Frage in einen
Anthropic-Messages-Call und liefert den reinen Antwort-Text.
"""

import logging
from typing import Any

from .base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5"
# Kinderfreundliche Antworten sind kurz; großzügiger Puffer für sokratische Struktur.
MAX_TOKENS = 2048


class ClaudeProvider(LLMProvider):
    """Anthropic-Messages-Adapter für den KIBuddy."""

    name = "claude"

    def __init__(self, api_key: str, model: str = ""):
        # Lazy-Import: `anthropic` ist eine optionale Laufzeit-Abhängigkeit
        # — Tests laufen mit einem Fake-Provider und brauchen das SDK nicht.
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model or DEFAULT_MODEL

    def complete_multiturn(
        self,
        system: str,
        turns: list[dict[str, Any]],
        user_message: str,
    ) -> str:
        """Mehrturn-Anthropic-Call mit Session-History (KIBUDDY-16)."""
        messages = [*turns, {"role": "user", "content": user_message}]
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
            )
        except self._anthropic.APIError as e:
            logger.warning("Claude-Anbieter nicht erreichbar: %s", e)
            raise ProviderError(str(e)) from e

        text_parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts).strip()
