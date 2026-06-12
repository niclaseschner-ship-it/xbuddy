"""Hörspiel-Buddy — Claude-Provider (HSP-10).

Übersetzt einen einzelnen System+User-Turn in einen Anthropic-Messages-Call
und liefert den reinen Antwort-Text. Das Provider-Modul ist der einzige Ort
mit anbieter-spezifischem JSON (Symmetrie zu eltern-chat/providers/claude.py).
"""

import logging

from .base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-7"
# 2700-Wörter-Folge ≈ ~3500 Tokens; Sicherheits-Puffer für JSON-Schale.
MAX_TOKENS = 8192


class ClaudeProvider(LLMProvider):
    """Anthropic-Messages-Adapter für den Hörspiel-Buddy."""

    name = "claude"

    def __init__(self, api_key: str, model: str = ""):
        # Lazy-Import: `anthropic` ist eine optionale Laufzeit-Abhängigkeit
        # — Tests laufen mit einem Fake-Provider und brauchen das SDK nicht.
        import anthropic
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model or DEFAULT_MODEL

    def complete(self, system: str, user: str) -> str:
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except self._anthropic.APIError as e:
            logger.warning("Claude-Anbieter nicht erreichbar: %s", e)
            raise ProviderError(str(e)) from e

        text_parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts).strip()
