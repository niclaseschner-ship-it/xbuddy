"""Mistral-Anbieter-Adapter — siehe specs/platform/eltern-chat.md EC-11 (Refs #508).

Dies ist der EINZIGE Ort mit anbieter-spezifischem (Mistral-) JSON. Der Adapter
übersetzt das kanonische Modell (model.py) in die Mistral-Chat-Completions-API
und die Antwort zurück. Der Agent-Kern fasst Mistral-Typen nie an.

DSGVO-Hinweis: Mistral AI ist EU-Anbieter (Paris, Frankreich) — konformer
Ersatz für US-Anbieter, solange OPEN-EC-A offen.
"""

import json
import logging

import httpx
from model import (
    GenerationResponse,
    ImageBlock,
    ProviderError,
    ProviderUsage,
    TaskCallBlock,
    TaskResultBlock,
    TextBlock,
)

logger = logging.getLogger(__name__)

_MISTRAL_API_BASE = "https://api.mistral.ai/v1"
_CHAT_ENDPOINT = _MISTRAL_API_BASE + "/chat/completions"


class MistralProvider:
    """Übersetzt kanonisches Modell <-> Mistral-Chat-Completions-API."""

    # ECP-1: Brand-Vendor-Slug — eine Wahrheitsquelle für den Zugangsdaten-Slot.
    brand_vendor = "mistral"

    # Anbieter-Default-Modell (EC-15: Anbieter-Modell, Default = Anbieter-Default).
    DEFAULT_MODEL = "mistral-medium-2508"
    MAX_TOKENS = 4096

    def __init__(self, api_key, model=""):
        self._api_key = api_key
        self._model = model or self.DEFAULT_MODEL

    def generate(self, request):
        """Führt eine Anbieter-Anfrage aus und liefert eine `GenerationResponse`.

        Wirft `ProviderError`, wenn der Anbieter nicht erreichbar ist oder
        fehlerhaft antwortet (EC-14).
        """
        mistral_messages = []
        # System-Prompt als eigene `system`-Nachricht (Mistral-API-Konvention).
        if request.system:
            mistral_messages.append({"role": "system", "content": request.system})
        for m in request.messages:
            mistral_messages.extend(self._to_mistral_message(m))

        tools = [self._to_mistral_tool(t) for t in request.task_defs]

        payload = {
            "model": self._model,
            "max_tokens": self.MAX_TOKENS,
            "messages": mistral_messages,
        }
        if tools:
            payload["tools"] = tools

        response_data = self._call_api(payload)
        self._log_token_usage(response_data)
        result = self._from_mistral_response(response_data)
        # EC-23 (#268): Token-Counts in das anbieter-neutrale Modell heben.
        usage = response_data.get("usage")
        if usage is not None:
            result.usage = ProviderUsage(
                input_tokens=usage.get("prompt_tokens", 0) or 0,
                output_tokens=usage.get("completion_tokens", 0) or 0,
                cache_read_tokens=0,
                cache_creation_tokens=0,
                model_id=self._model,
            )
        return result

    def _call_api(self, payload):
        """Führt den HTTP-POST gegen die Mistral-API aus."""
        try:
            response = httpx.post(
                _CHAT_ENDPOINT,
                headers={
                    "Authorization": "Bearer %s" % self._api_key,
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
                timeout=120.0,
            )
        except httpx.RequestError as e:
            logger.warning("Mistral-Anbieter nicht erreichbar: %s", e)
            raise ProviderError("Netzwerkfehler: %s" % e) from e
        if response.status_code != 200:
            logger.warning("Mistral-Anbieter HTTP-Fehler: %s %s",
                           response.status_code, response.text)
            raise ProviderError(
                "HTTP %d: %s" % (response.status_code, response.text))
        return response.json()

    def _log_token_usage(self, response_data):
        """Schreibt eine kompakte INFO-Zeile mit der Token-Nutzung pro Aufruf
        (E-EC-11) — Grundlage für Kosten-Aggregation per `grep` über die Zeit.

        Format: eine Zeile pro Aufruf, drei Counter + Modell. Fehlt das Feld
        `usage` (etwa in einem Test-Mock), bleibt das Logging still."""
        usage = response_data.get("usage")
        if usage is None:
            return
        logger.info(
            "tokens input=%s cache_create=%s cache_read=%s output=%s model=%s",
            usage.get("prompt_tokens", 0),
            0,
            0,
            usage.get("completion_tokens", 0),
            self._model,
        )

    # -- kanonisch -> Mistral ----------------------------------------

    @staticmethod
    def _to_mistral_message(message):
        """Übersetzt eine kanonische Message in eine Liste von Mistral-Nachrichten.

        Gibt immer eine Liste zurück (im Regelfall genau ein Element), damit der
        Aufrufer `.extend()` nutzen kann. Ausnahme: TaskResultBlocks — jedes
        Ergebnis wird als eigene `{"role": "tool", ...}`-Nachricht serialisiert
        (Mistral erwartet pro tool_call_id eine eigene Nachricht).
        """
        # Mistral: Tool-Calls gehören in die `assistant`-Nachricht als `tool_calls`.
        if any(isinstance(b, TaskCallBlock) for b in message.blocks):
            tool_calls = []
            text_parts = []
            for block in message.blocks:
                if isinstance(block, TaskCallBlock):
                    tool_calls.append({
                        "id": block.call_id,
                        "type": "function",
                        "function": {
                            "name": block.task,
                            "arguments": json.dumps(block.arguments),
                        },
                    })
                elif isinstance(block, TextBlock):
                    text_parts.append(block.text)
            msg = {"role": "assistant", "tool_calls": tool_calls}
            if text_parts:
                msg["content"] = "\n".join(text_parts).strip()
            return [msg]

        # Mistral: jedes Tool-Ergebnis als eigene `tool`-Nachricht.
        result_blocks = [b for b in message.blocks if isinstance(b, TaskResultBlock)]
        if result_blocks:
            return [
                {
                    "role": "tool",
                    "tool_call_id": block.call_id,
                    "content": str(block.content),
                }
                for block in result_blocks
            ]

        # Normale Text-/Bild-Nachricht.
        content = []
        for block in message.blocks:
            if isinstance(block, TextBlock):
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ImageBlock):
                # Mistral erwartet image_url mit data-URL (base64-kodiert).
                data_url = "data:%s;base64,%s" % (block.media_type, block.data_b64)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": data_url},
                })
        if len(content) == 1 and content[0].get("type") == "text":
            return [{"role": message.role, "content": content[0]["text"]}]
        return [{"role": message.role, "content": content}]

    @staticmethod
    def _to_mistral_tool(task_def):
        # Mistral erwartet tools in `{"type": "function", "function": {...}}`-Form.
        return {
            "type": "function",
            "function": {
                "name": task_def.name,
                "description": task_def.description,
                "parameters": task_def.parameters,
            },
        }

    # -- Mistral -> kanonisch ----------------------------------------

    @staticmethod
    def _from_mistral_response(response_data):
        text_parts = []
        task_calls = []
        choices = response_data.get("choices") or []
        for choice in choices:
            message = choice.get("message") or {}
            # Freitext.
            text = message.get("content") or ""
            if text:
                text_parts.append(text)
            # Tool-Calls.
            for tc in message.get("tool_calls") or []:
                fn = tc.get("function") or {}
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                task_calls.append(TaskCallBlock(
                    call_id=tc.get("id", ""),
                    task=fn.get("name", ""),
                    arguments=args if isinstance(args, dict) else {},
                ))
        return GenerationResponse(text="\n".join(text_parts).strip(),
                                  task_calls=task_calls)
