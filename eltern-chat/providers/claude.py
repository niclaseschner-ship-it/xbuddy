"""Claude-Anbieter-Adapter — siehe specs/platform/eltern-chat.md E-EC-6 (Refs #27).

Dies ist der EINZIGE Ort mit anbieter-spezifischem (Anthropic-) JSON. Der Adapter
übersetzt das kanonische Modell (model.py) in die Anthropic-Messages-API und die
Antwort zurück. Der Agent-Kern fasst Anthropic-Typen nie an.
"""

import logging

import anthropic

from model import (GenerationResponse, ImageBlock, ProviderError, TaskCallBlock,
                   TaskResultBlock, TextBlock)


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

        kwargs = dict(
            model=self._model,
            max_tokens=self.MAX_TOKENS,
            system=request.system,
            messages=anthropic_messages,
            # Stabiles Präfix (System + Aufgaben) cachen, sofern groß genug.
            cache_control={"type": "ephemeral"},
        )
        if tools:
            kwargs["tools"] = tools

        try:
            response = self._client.messages.create(**kwargs)
        except anthropic.APIError as e:
            logging.warning("Claude-Anbieter nicht erreichbar: %s", e)
            raise ProviderError(str(e))

        return self._from_anthropic_response(response)

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
