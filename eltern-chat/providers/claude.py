"""Claude-Anbieter-Adapter — siehe specs/platform/eltern-chat.md E-EC-6 (Refs #27).

Dies ist der EINZIGE Ort mit anbieter-spezifischem (Anthropic-) JSON. Der Adapter
übersetzt das kanonische Modell (model.py) in die Anthropic-Messages-API und die
Antwort zurück. Der Agent-Kern fasst Anthropic-Typen nie an.
"""

import logging

import anthropic

from model import (GenerationResponse, ImageBlock, ProviderError, TaskCallBlock,
                   TaskResultBlock, TextBlock)


logger = logging.getLogger(__name__)


class ClaudeProvider:
    """Übersetzt kanonisches Modell <-> Anthropic-Messages-API."""

    # Anbieter-Default-Modell (EC-15: Anbieter-Modell, Default = Anbieter-Default).
    DEFAULT_MODEL = "claude-opus-4-7"
    MAX_TOKENS = 4096

    def __init__(self, api_key, model=""):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model or self.DEFAULT_MODEL

    def generate(self, request):
        """Führt eine Anbieter-Anfrage aus und liefert eine `GenerationResponse`.

        Wirft `ProviderError`, wenn der Anbieter nicht erreichbar ist oder
        fehlerhaft antwortet (EC-14).
        """
        anthropic_messages = [self._to_anthropic_message(m) for m in request.messages]
        tools = [self._to_anthropic_tool(t) for t in request.task_defs]

        # Prompt-Caching (#93): den Cache-Marker an die STABILEN Präfix-Blöcke
        # setzen — System-Prompt und Aufgaben-Liste ändern sich praktisch nie
        # zwischen Turns, der Verlauf wächst nur ans Ende. Würden wir stattdessen
        # das Top-Level-Kwarg `cache_control` setzen, markiert der anthropic-SDK
        # automatisch den letzten cacheable Block — heute typischerweise die
        # frische Nutzer-Nachricht; der Cache trägt dann nicht über Turns.
        system_blocks = [{
            "type": "text",
            "text": request.system,
            "cache_control": {"type": "ephemeral"},
        }]

        kwargs = dict(
            model=self._model,
            max_tokens=self.MAX_TOKENS,
            system=system_blocks,
            messages=anthropic_messages,
        )
        if tools:
            # Letzten Eintrag der Aufgaben-Liste markieren — markiert implizit
            # alle vorhergehenden Tools mit (Anthropic-Cache-Semantik).
            tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
            kwargs["tools"] = tools

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.APIError as e:
            logger.warning("Claude-Anbieter nicht erreichbar: %s", e)
            raise ProviderError(str(e))

        self._log_token_usage(response)
        return self._from_anthropic_response(response)

    def _log_token_usage(self, response):
        """Schreibt eine kompakte INFO-Zeile mit der Token-Nutzung pro Aufruf
        (#93 Item 3) — Grundlage für Kosten-Aggregation per `grep` über die Zeit.

        Format: eine Zeile pro Aufruf, vier Counter + Modell. Fehlt das Feld
        `usage` (etwa in einem Test-Mock ohne Usage), bleibt das Logging still."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        logger.info(
            "tokens input=%s cache_create=%s cache_read=%s output=%s model=%s",
            getattr(usage, "input_tokens", 0),
            getattr(usage, "cache_creation_input_tokens", 0) or 0,
            getattr(usage, "cache_read_input_tokens", 0) or 0,
            getattr(usage, "output_tokens", 0),
            self._model,
        )

    # -- kanonisch -> Anthropic -------------------------------

    @staticmethod
    def _to_anthropic_message(message):
        content = []
        for block in message.blocks:
            if isinstance(block, TextBlock):
                content.append({"type": "text", "text": block.text})
            elif isinstance(block, ImageBlock):
                content.append({
                    "type": "image",
                    "source": {"type": "base64",
                               "media_type": block.media_type,
                               "data": block.data_b64},
                })
            elif isinstance(block, TaskCallBlock):
                content.append({
                    "type": "tool_use",
                    "id": block.call_id,
                    "name": block.task,
                    "input": block.arguments,
                })
            elif isinstance(block, TaskResultBlock):
                content.append({
                    "type": "tool_result",
                    "tool_use_id": block.call_id,
                    "content": block.content,
                    "is_error": block.is_error,
                })
        return {"role": message.role, "content": content}

    @staticmethod
    def _to_anthropic_tool(task_def):
        # `kind` (read/write) bleibt bewusst kanonisch — der Anbieter braucht es
        # nicht; die Unterscheidung wertet der Agent-Loop aus.
        return {
            "name": task_def.name,
            "description": task_def.description,
            "input_schema": task_def.parameters,
        }

    # -- Anthropic -> kanonisch -------------------------------

    @staticmethod
    def _from_anthropic_response(response):
        text_parts = []
        task_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                task_calls.append(TaskCallBlock(
                    call_id=block.id,
                    task=block.name,
                    arguments=dict(block.input) if block.input else {},
                ))
        return GenerationResponse(text="\n".join(text_parts).strip(),
                                  task_calls=task_calls)
