"""Mistral-Vendor-File für `tools.llm` (LLMP-4, T1085).

Zweiter Vendor neben `anthropic.py` (n=2). Deklariert `CAPABILITIES` am
Modulkopf (maschinell prüfbare Wurzel von LLMP-3, Watchdog-Regel LLMP-4) und
stellt die Agent-Sicht-Methoden bereit, die `public_api.get_agent` als Fassade
ausliefert.

Wire-Form-Vertrag: die Lib reicht intern die **neutrale (Anthropic-shaped)**
Wire-Form durch (System-String getrennt, `messages` mit content-Blöcken,
`tools` als `{name, description, input_schema}`). Dieser Vendor ist der EINZIGE
Ort mit Mistral-spezifischem JSON — er übersetzt die neutrale Form in die
Mistral-Chat-Completions-API und die Antwort zurück (gleicher Schnitt wie
`eltern-chat/providers/mistral.py`, dort gegen das eltern-chat-Modell).

Mistral hat KEIN Prompt-Caching → `cache_control` ist nicht in CAPABILITIES und
es werden keine Cache-Marker gesetzt. Die get_agent-Sicht verlangt
`cache_control` seit dem T1085-R0-Patch nicht mehr als Boot-Minimum.

DSGVO-Hinweis: Mistral AI ist EU-Anbieter (Paris) — konformer Ersatz für
US-Anbieter (vgl. eltern-chat OPEN-EC-A).
"""

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from .. import pricing, telemetry
from .._types import ProviderError

logger = logging.getLogger(__name__)

# LLMP-4 / LLMP-3: maschinell prüfbare Capability-Deklaration am Modulkopf.
# OHNE `cache_control` (Mistral kann kein Prompt-Caching). Der Boot-Vergleich
# gegen REQUIRED_AGENT (tool_use + multi_turn_assistant_prefill +
# system_message_distinct) geht damit auf.
CAPABILITIES = frozenset({
    "tool_use",
    "multi_turn_assistant_prefill",
    "structured_output",
    "multimodal_input",
    "system_message_distinct",
})

# Anbieter-Default-Modell (EC-15-Spiegel: Anbieter-Modell = Anbieter-Default).
DEFAULT_MODEL = "mistral-medium-2508"
DEFAULT_MAX_TOKENS = 4096

_MISTRAL_API_BASE = "https://api.mistral.ai/v1"
_CHAT_ENDPOINT = _MISTRAL_API_BASE + "/chat/completions"


class MistralVendor:
    """Mistral-Chat-Completions-Adapter — Agent-Sicht für `tools.llm` (LLMP-S1).

    Hält keinen SDK-Client (Mistral spricht reines REST); httpx wird lazy
    importiert (wie `eltern-chat/providers/mistral.py`), damit Tests die Lib
    ohne httpx-Last laden können.
    """

    name = "mistral"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        self._api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------
    #  Sicht: get_agent — Single-Turn + Tool-Loop (eltern-chat, T1085)
    # ------------------------------------------------------------------

    def agent_step(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        caller: str,
        slot: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Single-Turn-Create gegen Mistral: EIN HTTP-POST, kein interner Loop.

        Übersetzt die neutrale (Anthropic-shaped) Wire-Form → Mistral-Payload,
        ruft die API, emittiert Telemetrie (LLMP-S4) und parst die Antwort.
        Liefert `{"text", "tool_calls":[{id,name,input}…], "usage": <dict>}`.
        KEINE Cache-Marker (Mistral kann kein Prompt-Caching).
        """
        payload = self._build_payload(system, messages, tools)
        t_start = time.monotonic()
        response_data = self._call_api(payload)
        wall_ms = int((time.monotonic() - t_start) * 1000)
        return self._emit_and_parse(
            response_data, caller=caller, slot=slot, correlation_id=correlation_id,
            wall_ms=wall_ms,
        )

    def agent_run(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        caller: str,
        slot: str,
        tool_runner: Any = None,
        max_iterations: int = 8,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Tool-Use-Loop über `agent_step` (LLMP-S1 `get_agent`, T1085).

        Pro Iteration EIN `agent_step` (Single POST + Telemetrie, kein
        Copy-Paste — LLMP-S7). Spiegelt assistant-`tool_use` + user-`tool_result`
        in der NEUTRALEN Wire-Form zurück (die nächste `agent_step` übersetzt sie
        nach Mistral). is_error-Härtung wie Anthropic: `tool_runner` darf String
        ODER `{"content":…, "is_error": bool}` liefern. Jeder `agent_step` misst
        seine Wandzeit und emittiert sie in die Telemetrie (LLMP-S4).
        Liefert `{"text", "messages"}`.
        """
        convo = list(messages)
        for _ in range(max_iterations):
            step = self.agent_step(
                system=system,
                messages=convo,
                tools=tools,
                caller=caller,
                slot=slot,
                correlation_id=correlation_id,
            )
            if not step["tool_calls"]:
                return {"text": step["text"], "messages": convo}

            if tool_runner is None:
                raise ProviderError(
                    "mistral-vendor: agent_run bekam tool_use-Blöcke, aber "
                    "keinen tool_runner (Caller muss Tool-Results liefern)"
                )

            convo.append({
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
                    for tc in step["tool_calls"]
                ],
            })
            convo.append({
                "role": "user",
                "content": [
                    self._tool_result_block(tc["id"], tool_runner(tc["name"], tc["input"]))
                    for tc in step["tool_calls"]
                ],
            })

        raise ProviderError(
            "mistral-vendor: agent_run erreichte max_iterations=%d ohne "
            "Abschluss" % max_iterations
        )

    @staticmethod
    def _tool_result_block(tool_use_id: str, runner_result: Any) -> dict[str, Any]:
        """Neutraler `tool_result`-Block aus dem `tool_runner`-Rückgabewert
        (String ODER `{"content":…, "is_error": bool}`). Spiegel zur
        Anthropic-Variante — die Mistral-Übersetzung passiert in
        `_to_mistral_message`."""
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_use_id}
        if isinstance(runner_result, dict):
            block["content"] = runner_result.get("content", "")
            block["is_error"] = bool(runner_result.get("is_error", False))
        else:
            block["content"] = runner_result
        return block

    # ------------------------------------------------------------------
    #  Sicht: get_singleshot — Structured Singleshot (hoerspiel, T1084)
    # ------------------------------------------------------------------

    def singleshot_structured(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        caller: str,
        slot: str,
        tool_name: str = "ergebnis",
        tool_description: str = "Strukturiertes Ergebnis-Objekt nach Schema.",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Ein Call, forced `tool_use` → Schema-konformes dict (LLMP-S1
        `get_singleshot`, Spiegel `anthropic.singleshot_structured`).

        Baut den Mistral-Payload aus EINER user-Message (`prompt`) + EINEM Tool
        (`_to_mistral_tool` — geteilt mit der Agent-Sicht) und erzwingt es über
        die **benannte** `tool_choice`-Form (Anthropic-Parität: dort
        `{"type":"tool","name":…}`). `"any"` ist ein validierter Fallback (vgl.
        `hoerspiel/providers/mistral.py:100`), aber die benannte Form pinnt das
        EINE Schema-Tool. KEINE Cache-Marker (Mistral kann kein Prompt-Caching).
        Telemetrie via geteiltem `_emit_telemetry` (kein Copy-Paste — LLMP-S7).
        Kein `tool_call` mit `name==tool_name` → `ProviderError`
        (Spiegel `anthropic.py:212-214`).
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [],
            "tools": [self._to_mistral_tool({
                "name": tool_name,
                "description": tool_description,
                "input_schema": schema,
            })],
            # Benannte Form (Anthropic-Parität); `"any"` ist validierter
            # Fallback, vgl. hoerspiel/providers/mistral.py:100.
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
        }
        if system:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append({"role": "user", "content": prompt})

        t_start = time.monotonic()
        response_data = self._call_api(payload)
        wall_ms = int((time.monotonic() - t_start) * 1000)
        self._emit_telemetry(
            response_data, caller=caller, slot=slot,
            correlation_id=correlation_id, wall_ms=wall_ms,
        )

        for choice in response_data.get("choices") or []:
            message = choice.get("message") or {}
            for tc in message.get("tool_calls") or []:
                fn = tc.get("function") or {}
                if fn.get("name") != tool_name:
                    continue
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                return args if isinstance(args, dict) else {}
        raise ProviderError(
            "mistral-vendor: forced tool_use lieferte keinen %r-Block" % tool_name
        )

    # ------------------------------------------------------------------
    #  neutrale Wire-Form -> Mistral-Payload
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Baut den Mistral-Chat-Completions-Payload aus der neutralen Form."""
        mistral_messages: list[dict[str, Any]] = []
        if system:
            # System-Prompt als eigene system-Message (system_message_distinct).
            mistral_messages.append({"role": "system", "content": system})
        for m in messages:
            mistral_messages.extend(self._to_mistral_message(m))

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": mistral_messages,
        }
        wire_tools = [self._to_mistral_tool(t) for t in tools]
        if wire_tools:
            payload["tools"] = wire_tools
        return payload

    @staticmethod
    def _to_mistral_tool(tool: dict[str, Any]) -> dict[str, Any]:
        """Neutrales `{name, description, input_schema}` → Mistral-function-Form
        (Spiegel `eltern-chat/providers/mistral.MistralProvider._to_mistral_tool`)."""
        return {
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }

    @classmethod
    def _to_mistral_message(cls, message: dict[str, Any]) -> list[dict[str, Any]]:
        """Übersetzt eine neutrale Message in eine Liste Mistral-Nachrichten.

        Liefert immer eine Liste (Aufrufer nutzt `.extend()`). String-`content`
        bleibt String. Block-`content` (Anthropic-shaped) wird je Block-Typ
        übersetzt: `tool_use` → assistant-`tool_calls`, `tool_result` → eigene
        `{role:tool, …}`-Nachricht (inkl. is_error-Wissen wie
        `eltern-chat/providers/mistral.py`), `image` → `image_url` (data-URL),
        `text` → text-Part.
        """
        role = message.get("role", "user")
        content = message.get("content")

        # Einfacher String-content (häufigster Fall, z. B. erste User-Nachricht).
        if isinstance(content, str):
            return [{"role": role, "content": content}]

        blocks = content or []

        # Assistant mit tool_use-Blöcken → Mistral tool_calls.
        tool_use_blocks = [b for b in blocks if b.get("type") == "tool_use"]
        if tool_use_blocks:
            tool_calls = [
                {
                    "id": b.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": b.get("name", ""),
                        "arguments": json.dumps(b.get("input") or {}),
                    },
                }
                for b in tool_use_blocks
            ]
            text_parts = [b["text"] for b in blocks if b.get("type") == "text"]
            msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
            if text_parts:
                msg["content"] = "\n".join(text_parts).strip()
            return [msg]

        # User mit tool_result-Blöcken → je Result eine eigene tool-Nachricht.
        tool_results = [b for b in blocks if b.get("type") == "tool_result"]
        if tool_results:
            return [
                cls._tool_result_to_mistral(b) for b in tool_results
            ]

        # Normale Text-/Bild-Nachricht.
        parts: list[dict[str, Any]] = []
        for b in blocks:
            if b.get("type") == "text":
                parts.append({"type": "text", "text": b.get("text", "")})
            elif b.get("type") == "image":
                # Neutrale Form: {type:image, source:{type:base64, media_type, data}}
                source = b.get("source") or {}
                data_url = "data:%s;base64,%s" % (
                    source.get("media_type", ""), source.get("data", ""),
                )
                parts.append({"type": "image_url", "image_url": {"url": data_url}})
        if len(parts) == 1 and parts[0].get("type") == "text":
            return [{"role": role, "content": parts[0]["text"]}]
        return [{"role": role, "content": parts}]

    @staticmethod
    def _tool_result_to_mistral(block: dict[str, Any]) -> dict[str, Any]:
        """Neutraler tool_result-Block → Mistral-`{role:tool, …}`-Nachricht.

        is_error-Wissen wird wie in `eltern-chat/providers/mistral.py` in den
        Inhalt gehoben (Mistral hat kein eigenes Fehler-Flag auf tool-Messages).
        """
        content = block.get("content", "")
        msg = {
            "role": "tool",
            "tool_call_id": block.get("tool_use_id", ""),
            "content": str(content),
        }
        if block.get("is_error"):
            msg["content"] = "[FEHLER] " + msg["content"]
        return msg

    # ------------------------------------------------------------------
    #  HTTP + Mistral-Antwort -> neutrale Form
    # ------------------------------------------------------------------

    def _call_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        """HTTP-POST gegen die Mistral-API. APIError/HTTP≠200 → ProviderError
        (Spiegel `eltern-chat/providers/mistral.MistralProvider._call_api`)."""
        import httpx

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
            logger.warning("mistral-vendor: API nicht erreichbar: %s", e)
            raise ProviderError("Netzwerkfehler: %s" % e) from e
        if response.status_code != 200:
            logger.warning(
                "mistral-vendor: HTTP-Fehler: %s %s",
                response.status_code, response.text,
            )
            raise ProviderError(
                "HTTP %d: %s" % (response.status_code, response.text))
        return response.json()

    def _emit_and_parse(
        self,
        response_data: dict[str, Any],
        *,
        caller: str,
        slot: str,
        correlation_id: str | None,
        wall_ms: int,
    ) -> dict[str, Any]:
        """Geteilter Telemetrie-/Parse-Helfer für agent_step UND agent_run
        (kein Copy-Paste — LLMP-S7). Emittiert den JSONL-Eintrag und liefert
        die neutrale Antwort `{"text", "tool_calls", "usage"}`.
        """
        self._emit_telemetry(
            response_data, caller=caller, slot=slot, correlation_id=correlation_id,
            wall_ms=wall_ms,
        )
        return self._parse_response(response_data)

    @staticmethod
    def _parse_response(response_data: dict[str, Any]) -> dict[str, Any]:
        """Mistral-Antwort → neutrale `{"text", "tool_calls", "usage"}`-Form
        (Spiegel `eltern-chat/providers/mistral._from_mistral_response`)."""
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for choice in response_data.get("choices") or []:
            message = choice.get("message") or {}
            text = message.get("content") or ""
            if text:
                text_parts.append(text)
            for tc in message.get("tool_calls") or []:
                fn = tc.get("function") or {}
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args if isinstance(args, dict) else {},
                })
        return {
            "text": "\n".join(text_parts).strip(),
            "tool_calls": tool_calls,
            "usage": response_data.get("usage"),
        }

    # ------------------------------------------------------------------
    #  Telemetrie (LLMP-S4)
    # ------------------------------------------------------------------

    def _emit_telemetry(
        self,
        response_data: dict[str, Any],
        *,
        caller: str,
        slot: str,
        correlation_id: str | None,
        wall_ms: int,
    ) -> None:
        """Baut den JSONL-Eintrag aus der Mistral-`usage` und schreibt ihn via
        `tools.llm.telemetry.write_call` (LLMP-S4). Mistral kennt kein Caching →
        `cache_*` bleiben 0. Fehlendes `usage` (Test-Mock) → Counter 0, Eintrag
        entsteht trotzdem (gleiche Defensive wie Anthropic-Vendor)."""
        usage = response_data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or 0)

        est_cost_eur = pricing.compute_eur(
            self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=0,
            cache_creation_tokens=0,
        )

        event = {
            "ts": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "caller": caller,
            "slot": slot,
            "model_id": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "wall_ms": wall_ms,
            "est_cost_eur": est_cost_eur,
        }
        if correlation_id is not None:
            event["correlation_id"] = correlation_id

        telemetry.write_call(event)
