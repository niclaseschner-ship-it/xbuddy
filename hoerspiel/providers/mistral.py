"""Hörspiel-Buddy — Mistral-Provider-Adapter (HSP-27b, OPEN-HSP-N → V1 jetzt aktiv).

Dies ist der EINZIGE Ort mit Mistral-spezifischem JSON im Hörspiel-Buddy.
Pattern nach eltern-chat/providers/mistral.py, adaptiert auf die hoerspiel-
Provider-Schnittstelle (LLMProvider.complete + complete_structured statt
eltern-chat-MessageBlock-Modell).

Mistral AI ist EU-Anbieter (Paris, Frankreich) — DSGVO-konform.

Geheimnisse: ZD-Slot `hoerspiel-mistral-api-key`, ENV-Fallback
`HOERSPIEL_MISTRAL_KEY` (HSP-27).
"""

import json
import logging

from .base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)

_MISTRAL_API_BASE = "https://api.mistral.ai/v1"
_CHAT_ENDPOINT = _MISTRAL_API_BASE + "/chat/completions"

# HSP-27b — ratifizierte V1-Modell-Liste für Mistral.
# Label-Format: "<Bezeichnung> (<Charakterisierung>)"
AVAILABLE_MODELS: list[tuple[str, str]] = [
    ("mistral-large-2411",  "Large 2.1 (Frontier, kreativ)"),
    ("mistral-medium-2508", "Medium 3.1 (ausgewogen, V1-Default Mistral)"),
    ("mistral-small-2503",  "Small 3.1 (schnell, günstig)"),
]

DEFAULT_MODEL = "mistral-medium-2508"
MAX_TOKENS = 4096


class MistralProvider(LLMProvider):
    """Mistral-Chat-Completions-Adapter für den Hörspiel-Buddy.

    Implementiert die gleiche LLMProvider-Schnittstelle wie ClaudeProvider:
    `complete` (freier Text) und `complete_structured` (Tool-Use über
    Mistral-Function-Calling).
    """

    name = "mistral"

    def __init__(self, api_key: str, model: str = ""):
        # Lazy-Import: `httpx` muss nur vorhanden sein wenn Mistral genutzt wird.
        import httpx  # geprüft hier, genutzt in _call_api
        self._httpx = httpx
        self._api_key = api_key
        self.model = model or DEFAULT_MODEL

    def complete(self, system: str, user: str) -> str:
        """Einfacher Text-Call (Synopse-Pfad HSP-16).

        Gibt den reinen Antwort-Text zurück.
        Wirft ProviderError bei Netzwerkfehler oder HTTP-Fehler.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": messages,
        }
        data = self._call_api(payload)
        return self._extract_text(data)

    def complete_structured(self, system: str, user: str, *,
                            tool_name: str,
                            tool_description: str,
                            input_schema: dict) -> dict:
        """Strukturierter Call via Mistral-Function-Calling (Folgen-Vorschlag HSP-11).

        Gibt das Argument-Dict des Tool-Calls zurück.
        Wirft ProviderError wenn kein Tool-Call in der Antwort enthalten ist.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        tools = [{
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": input_schema,
            },
        }]

        payload = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": messages,
            "tools": tools,
            "tool_choice": "any",
        }
        data = self._call_api(payload)

        # Tool-Call aus der Antwort extrahieren.
        choices = data.get("choices") or []
        for choice in choices:
            message = choice.get("message") or {}
            for tc in message.get("tool_calls") or []:
                fn = tc.get("function") or {}
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                if isinstance(args, dict):
                    return args

        # Fallback: Mistral hat keinen Tool-Call zurückgegeben —
        # Text-Antwort als JSON versuchen (Robustheit).
        text = self._extract_text(data)
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

        raise ProviderError(
            "Mistral-Antwort enthält keinen tool_use-Block für %r" % tool_name)

    def _call_api(self, payload: dict) -> dict:
        """Führt den HTTP-POST gegen die Mistral-API aus."""
        try:
            response = self._httpx.post(
                _CHAT_ENDPOINT,
                headers={
                    "Authorization": "Bearer %s" % self._api_key,
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
                timeout=120.0,
            )
        except self._httpx.RequestError as e:
            logger.warning("Mistral-Anbieter nicht erreichbar: %s", e)
            raise ProviderError("Netzwerkfehler: %s" % e) from e

        if response.status_code != 200:
            logger.warning("Mistral-Anbieter HTTP-Fehler: %s %s",
                           response.status_code, response.text)
            raise ProviderError(
                "HTTP %d: %s" % (response.status_code, response.text))

        data = response.json()
        self._log_token_usage(data)
        return data

    def _extract_text(self, data: dict) -> str:
        """Extrahiert den Freitext aus einer Mistral-Antwort."""
        parts = []
        choices = data.get("choices") or []
        for choice in choices:
            message = choice.get("message") or {}
            text = message.get("content") or ""
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    def _log_token_usage(self, data: dict) -> None:
        """Schreibt eine kompakte INFO-Zeile mit der Token-Nutzung."""
        usage = data.get("usage")
        if usage is None:
            return
        logger.info(
            "tokens input=%s output=%s model=%s",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            self.model,
        )
