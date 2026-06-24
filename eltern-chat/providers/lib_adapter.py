"""Lib-Agent-Adapter — eltern-chat über `tools.llm` (T1085, PR2).

Dieser Adapter erfüllt denselben Vertrag wie `providers/claude.py` und
`providers/mistral.py` — `.generate(GenerationRequest) -> GenerationResponse`
— aber führt den Anbieter-Call NICHT selbst aus: er reicht die Anfrage an die
geteilte LLM-Provider-Library `tools.llm` (Agent-Sicht `get_agent(...).step()`)
durch. Das anbieter-spezifische JSON lebt damit zentral in `tools/llm/_vendor/`
(Anthropic + Mistral), nicht mehr pro eltern-chat-Adapter (E-EC-6 bleibt
gewahrt, der Übersetzungs-Ort wandert nur eine Schicht tiefer).

Schnitt (gespiegelt von `providers/claude.py:_to_anthropic_message/_to_anthropic_tool`):
das kanonische Modell (model.py) → neutrale, Anthropic-shaped Wire-Form, die die
Lib intern an den gewählten Vendor übersetzt. Die Lib-Fassade wird EINMAL im
`__init__` gebaut (Slot + effektives Modell), pro `generate` wiederverwendet —
kein Zugangsdaten-Read pro Turn.

correlation_id (EC-23-Spiegel, T1085): `request.correlation_id` (die turn_id)
wird an `step(...)` durchgereicht; die Lib schreibt damit den JSONL-Telemetrie-
Eintrag (`var/llm/provider_calls.jsonl`, caller=eltern-chat). Die SQLite-Doppel-
schreibung (EC-23) bleibt unangetastet — der Adapter füllt `GenerationResponse.usage`,
`agent._call_provider` + `telemetry.persist_turn` laufen unverändert.
"""

import logging

from model import (
    GenerationResponse,
    ImageBlock,
    ProviderError,
    ProviderUsage,
    TaskCallBlock,
    TaskResultBlock,
    TextBlock,
)

from tools.llm import LLMCapabilityError, get_agent
from tools.llm import ProviderError as LibProviderError

logger = logging.getLogger(__name__)

# Anbieter-Default-Modell pro Brand-Vendor (EC-15: Anbieter-Modell = Anbieter-
# Default). Spiegelt die Alt-Adapter-Defaults (providers/claude.py:31
# `claude-opus-4-7`, providers/mistral.py:38 `mistral-medium-2508`), damit der
# Lib-Pfad EXAKT das Modell nutzt, das der alte Pfad nutzte (Orchestrator-
# Entscheid T1085: Verhalten erhalten).
_VENDOR_DEFAULT_MODEL = {
    "anthropic": "claude-opus-4-7",
    "mistral": "mistral-medium-2508",
}


class LibAgentAdapter:
    """Übersetzt das kanonische Modell <-> `tools.llm`-Agent-Sicht (T1085).

    `provider` ist der eltern-chat-Adapter-Name (`claude`/`mistral`), wie ihn
    config liefert; `provider_model` ist das konfigurierte Modell (leer →
    Anbieter-Default). Der Konstruktor löst den Brand-Vendor-Slug auf
    (`vendor_slug_for_adapter` / `zd_name_provider_api_key` → Slot
    `eltern-chat-<vendor>-api-key`) und baut die Lib-Fassade einmal — den
    API-Key holt die Lib selbst aus dem Zugangsdaten-Speicher (ZD-5).
    """

    def __init__(self, provider, provider_model=""):
        # Lokaler Import: bricht keinen Zyklus, hält den Modulkopf schlank und
        # spiegelt das Lazy-Muster der Alt-Adapter (anthropic/httpx lazy).
        from onboarding_store import vendor_slug_for_adapter, zd_name_provider_api_key

        vendor = vendor_slug_for_adapter(provider)
        slot = zd_name_provider_api_key(provider)
        # Effektives Modell: konfiguriertes Modell, sonst Anbieter-Default des
        # Brand-Vendors (EC-15) — exakt der Alt-Pfad (claude.py:36 /
        # mistral.py:DEFAULT_MODEL).
        self._model = (provider_model or "").strip() or _VENDOR_DEFAULT_MODEL.get(vendor, "")
        self._provider = provider
        self._slot = slot

        # Lib-Fassade EINMAL bauen (Slot + effektives Modell). Ein
        # `LLMCapabilityError` hier ist ein Boot-Konfig-Fehler (fehlender Key,
        # Capability-Mismatch) — er propagiert klar (wie der alte fehlender-Key-
        # Pfad) und wird NICHT als ProviderError verschluckt.
        self._agent = get_agent(slot=slot, model=self._model)

    def generate(self, request):
        """Führt eine Anbieter-Anfrage über `tools.llm` aus und liefert eine
        `GenerationResponse`.

        Wirft `model.ProviderError`, wenn der Anbieter nicht erreichbar ist
        oder fehlerhaft antwortet (EC-14) — `tools.llm.ProviderError` wird hier
        in die kanonische `model.ProviderError` übersetzt, die
        `agent.run_turn._call_provider` fängt.
        """
        messages = [self._to_wire_message(m) for m in request.messages]
        tools = [self._to_wire_tool(t) for t in request.task_defs]

        try:
            result = self._agent.step(
                system=request.system,
                messages=messages,
                tools=tools,
                correlation_id=request.correlation_id,
            )
        except LibProviderError as e:
            # EC-14: Lib-Provider-Fehler → kanonische ProviderError für
            # _call_provider (das den Stub-Call anhängt und 503 auslöst).
            logger.warning("tools.llm-Anbieter nicht erreichbar: %s", e)
            raise ProviderError(str(e)) from e

        return self._from_wire_result(result)

    # -- kanonisch -> neutrale (Anthropic-shaped) Wire-Form ------------------
    # Spiegel von providers/claude.py:_to_anthropic_message/_to_anthropic_tool.

    @staticmethod
    def _to_wire_message(message):
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
    def _to_wire_tool(task_def):
        # `kind` (read/write) bleibt kanonisch — der Anbieter braucht es nicht;
        # die Unterscheidung wertet der Agent-Loop aus (wie claude.py).
        return {
            "name": task_def.name,
            "description": task_def.description,
            "input_schema": task_def.parameters,
        }

    # -- neutrale Wire-Form -> kanonisch -------------------------------------

    def _from_wire_result(self, result):
        """Neutrale Lib-Antwort `{text, tool_calls, usage}` → GenerationResponse."""
        task_calls = [
            TaskCallBlock(
                call_id=tc.get("id", ""),
                task=tc.get("name", ""),
                arguments=dict(tc.get("input") or {}),
            )
            for tc in result.get("tool_calls") or []
        ]
        response = GenerationResponse(
            text=result.get("text", "") or "",
            task_calls=task_calls,
        )
        # EC-23 (#268): Token-Counts ins anbieter-neutrale Modell heben, damit
        # _call_provider + telemetry.persist_turn (SQLite) unverändert laufen.
        response.usage = self._to_provider_usage(result.get("usage"))
        return response

    def _to_provider_usage(self, usage):
        """Neutrale `usage` → `ProviderUsage` — beide Vendor-Formen (T1085-Befund).

        Anthropic liefert ein RAW-Objekt (`getattr` input_tokens/output_tokens/
        cache_read_input_tokens/cache_creation_input_tokens), Mistral ein DICT
        (`prompt_tokens`/`completion_tokens`, cache=0). Fehlt usage komplett →
        None (wie claude.py: dann hängt _call_provider keinen ProviderCall an).
        """
        if usage is None:
            return None
        if isinstance(usage, dict):
            # Mistral-Form: dict, prompt_/completion_tokens, kein Caching.
            return ProviderUsage(
                input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                output_tokens=int(usage.get("completion_tokens", 0) or 0),
                cache_read_tokens=int(usage.get("cache_read_tokens", 0) or 0),
                cache_creation_tokens=int(usage.get("cache_creation_tokens", 0) or 0),
                model_id=self._model,
            )
        # Anthropic-Form: RAW-Objekt mit getattr-Feldern.
        return ProviderUsage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_creation_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            model_id=self._model,
        )


# Re-Export, damit ein Test/Konsument den Boot-Konfig-Fehler-Typ greifen kann,
# ohne `tools.llm` selbst zu importieren (analog claude.py-Schnitt).
__all__ = ["LLMCapabilityError", "LibAgentAdapter"]
