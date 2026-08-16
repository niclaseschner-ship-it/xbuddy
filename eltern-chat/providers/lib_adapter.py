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

from tools.llm import LLMCapabilityError, get_agent, litellm_slot_for_provider
from tools.llm import ProviderError as LibProviderError

logger = logging.getLogger(__name__)

# Anbieter-Default-Modell pro Brand-Vendor (EC-15: Anbieter-Modell = Anbieter-
# Default). Ursprünglich gespiegelt von den Alt-Adaptern providers/claude.py /
# providers/mistral.py (T1085) — beide sind seit dem Hand-Vendor-Abriss #1510
# gelöscht. Kein Spec-Pin dahinter: der konkrete Wert lebt seither allein hier.
# `anthropic` auf `claude-opus-5` gehoben (T1807, gleicher Preis wie
# `claude-opus-4-7`, s. Handoff für den Katalog-Beleg).
_VENDOR_DEFAULT_MODEL = {
    "anthropic": "claude-opus-5",
    "mistral": "mistral-medium-2508",
}

# T1492 (LLMP-S13 n=2-Naht): Slot-Namensbildung über die geteilte Lib-Funktion
# (tools.llm.litellm_slot_for_provider), statt lokaler Tabelle. Die Funktion
# baut `eltern-chat-litellm-<purpose>` nach LLMP-5 — kein Vendor-Slug im purpose,
# damit parse_slot nicht zwei Vendoren matcht (LLMP-5-Falle; `eu` statt `mistral`
# für Mistral). Identische Tabelle war in hoerspiel/main.py:_LIB_SLOT_FOR_PROVIDER
# dupliziert (T1454); n=2 → Naht zentralisiert.
_CALLER = "eltern-chat"


class LibAgentAdapter:
    """Übersetzt das kanonische Modell <-> `tools.llm`-Agent-Sicht (T1085).

    `provider` ist der eltern-chat-Adapter-Name (`claude`/`mistral`), wie ihn
    config liefert; `provider_model` ist das konfigurierte Modell (leer →
    Anbieter-Default). Der Konstruktor wählt den anbieter-benannten litellm-Slot
    (`_LIB_SLOT_FOR_PROVIDER`, LLMP-S13) und baut die Lib-Fassade einmal — den
    API-Key holt die Lib selbst aus dem Zugangsdaten-Speicher (ZD-5). Das
    `mistral/`-Präfix ergänzt die Lib zentral (LLMP-S13, `_build_vendor`); der
    Adapter reicht den blanken Modellnamen durch.
    """

    def __init__(self, provider, provider_model=""):
        # Lokaler Import: bricht keinen Zyklus, hält den Modulkopf schlank und
        # spiegelt das Lazy-Muster der Alt-Adapter (anthropic/httpx lazy).
        # `vendor_slug_for_adapter` NUR für den Alt-Modell-Default-Lookup:
        # `claude` → `anthropic` → `claude-opus-5`, `mistral` → `mistral` →
        # `mistral-medium-2508` (EC-15, `_VENDOR_DEFAULT_MODEL`). Der Slug wird
        # NICHT in den Slot-Namen gebaut — der Slot ist anbieter-benannt (LLMP-S13).
        from onboarding_store import vendor_slug_for_adapter

        vendor = vendor_slug_for_adapter(provider)
        # LLMP-S13 / T1492: Slot nach effektivem Provider über die geteilte
        # Lib-Naht (litellm_slot_for_provider). Unbekannter Provider ist ein
        # Konfig-Fehler (KeyError) — sichtbar am Boot, kein Silent-Fallback.
        slot = litellm_slot_for_provider(_CALLER, provider)
        # Effektives Modell: konfiguriertes Modell, sonst Anbieter-Default des
        # Brand-Vendors (`_VENDOR_DEFAULT_MODEL`, EC-15) — blanker Modellname
        # (z. B. `mistral-medium-2508`); das `mistral/`-Präfix ergänzt
        # `tools.llm` zentral (LLMP-S13).
        self._model = (provider_model or "").strip() or _VENDOR_DEFAULT_MODEL.get(vendor, "")
        self._provider = provider
        self._slot = slot

        # Lib-Fassade EINMAL bauen (Slot + effektives Modell + alt-treuem
        # max_tokens). Ein `LLMCapabilityError` hier ist ein Boot-Konfig-Fehler
        # (fehlender Key, Capability-Mismatch) — er propagiert klar (wie der alte
        # fehlender-Key-Pfad) und wird NICHT als ProviderError verschluckt.
        # max_tokens=4096: historischer Wert aus dem inzwischen gelöschten
        # Hand-Vendor providers/claude.py MAX_TOKENS=4096 (T1129, #1510-Abriss);
        # ohne explizite Übergabe würde die Lib DEFAULT_MAX_TOKENS=2048 nutzen —
        # stille Halbierung, die lange Antworten trunkieren kann (vgl. #1084-502).
        # T1807/AC3: claude-opus-5 erlaubt laut litellm-Katalog max_output_tokens
        # 128000 — 4096 bleibt weit darunter, kein Cutoff-Risiko durch den
        # Modell-Wechsel selbst.
        self._agent = get_agent(slot=slot, model=self._model, max_tokens=4096)

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
        """Neutrale `usage` → `ProviderUsage` — alle Vendor-Formen (T1085/#1463).

        Drei Formen:
          - Mistral (Hand-Vendor): DICT (`prompt_tokens`/`completion_tokens`,
            kein Caching).
          - Anthropic (Hand-Vendor): RAW-Objekt (`input_tokens`/`output_tokens`/
            `cache_read_input_tokens`/`cache_creation_input_tokens`).
          - LiteLLM (Motor seit #1452/#1463): RAW-Objekt in OpenAI-Form
            (`prompt_tokens`/`completion_tokens`), Anthropic-Cache-Zahlen additiv
            (`cache_read_input_tokens`/`cache_creation_input_tokens`, Prompt-
            Caching-Passthrough). Darum liest der getattr-Zweig BEIDE Token-
            Namen — `input_tokens` bevorzugt, sonst `prompt_tokens` (analog
            output). Fehlt usage komplett → None (wie claude.py: dann hängt
            _call_provider keinen ProviderCall an).
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
        # RAW-Objekt (Anthropic ODER LiteLLM/OpenAI-förmig). Token-Namen je nach
        # Backend: Anthropic `input_tokens`, LiteLLM `prompt_tokens` — der
        # bevorzugte Name gewinnt, sonst der Alternativname.
        input_tokens = getattr(usage, "input_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(usage, "prompt_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(usage, "completion_tokens", 0)
        return ProviderUsage(
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_creation_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            model_id=self._model,
        )


# Re-Export, damit ein Test/Konsument den Boot-Konfig-Fehler-Typ greifen kann,
# ohne `tools.llm` selbst zu importieren (analog claude.py-Schnitt).
__all__ = ["LLMCapabilityError", "LibAgentAdapter"]
