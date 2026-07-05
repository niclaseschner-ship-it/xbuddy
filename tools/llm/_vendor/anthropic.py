"""Anthropic-Vendor-File für `tools.llm` (LLMP-4).

Eine Datei je Vendor: deklariert `CAPABILITIES` am Modulkopf
(maschinell prüfbare Wurzel von LLMP-3, Watchdog-Regel LLMP-4) und stellt
die Sicht-Methoden bereit, die `public_api.get_*` als Fassade ausliefert.

V1 implementiert `chat_multiturn(...)` für die KIBuddy-Migration (heutiger
Use-Case `get_chat`); `agent` und `singleshot` bleiben als `NotImplementedError`
stehen, weil sie erst mit T3 (hoerspiel) und T4 (eltern-chat) live gehen
(Spike-Stufe-1 baut die Fixtures separat, siehe LLMP-S7). Wer sie heute
ruft, sieht klar, dass die Sicht noch nicht migriert ist.

Goldstandard-Vorbild für Cache-Control und Token-Counts: `eltern-chat/providers/claude.py`
— wir folgen genau dieser Cache-Marker-Strategie (stabiler System-Prompt-Block
trägt `cache_control: ephemeral`), damit die KIBuddy-Spike-Stufe-1 später
ohne SDK-Anpassung hoerspiel/eltern-chat mit übernimmt.
"""

import base64
import logging
import time
from datetime import UTC, datetime
from typing import Any

from .. import pricing, telemetry
from .._types import ProviderError
from ._base import VendorBase

logger = logging.getLogger(__name__)

# LLMP-4 / LLMP-3: maschinell prüfbare Capability-Deklaration am Modulkopf.
# Watchdog-Regel: jeder File unter `tools/llm/_vendor/` ohne diese Konstante
# (oder ohne `frozenset`) ist ein Bruch. Die Lib lädt die Konstante beim Boot
# und vergleicht gegen die Sicht-Required-Sets — bei Mismatch
# `LLMCapabilityError` als erster Fehler vor allem anderen (LLMP-S3).
CAPABILITIES = frozenset({
    "tool_use",
    "multi_turn_assistant_prefill",
    "structured_output",
    "cache_control",
    "multimodal_input",
    "system_message_distinct",
})

# Vendor-Default-Modell, falls der Konsument keines wählt. V1 verwendet das
# kibuddy-Default-Modell aus `kibuddy/providers/claude.py` (DEFAULT_MODEL =
# `claude-haiku-4-5`) als geteilten Lib-Default — kindgerechte Antworten sind
# kurz, der Default deckt heute alle drei Sichten ausreichend.
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_MAX_TOKENS = 2048


class AnthropicVendor(VendorBase):
    """Anthropic-Messages-Adapter — gemeinsamer Kern aller drei Sichten (LLMP-S1).

    Hält genau **eine** SDK-Client-Instanz und stellt die drei Sicht-Methoden
    bereit, die die jeweiligen `get_*`-Fassaden in `public_api` aufrufen. Ein
    neuer Vendor entsteht durch eine neue Datei mit derselben Methoden-Liste
    (LLMP-2 Trade-off: Vendor-Wechsel ist ein File, kein Adapter pro Buddy).

    ``agent_run`` und ``_tool_result_block`` werden von ``VendorBase`` geerbt
    (T1130 — LLMP-S7 n=3-Extraktion; keine Copy mehr).
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        # Lazy-Import des SDKs analog `kibuddy/providers/claude.py` —
        # Tests, die `tools.llm` ohne echte SDK-Last laden wollen
        # (Capability-Boot-Fail, Resolver, Telemetrie, Pricing), brauchen
        # `anthropic` nicht als Test-Dependency.
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------
    #  Sicht: get_chat — Multi-Turn-Konversation (KIBuddy, T1082)
    # ------------------------------------------------------------------

    def chat_multiturn(
        self,
        system: str,
        turns: list[dict[str, Any]],
        user_message: str,
        *,
        caller: str,
        slot: str,
        correlation_id: str | None = None,
    ) -> str:
        """Mehrturn-Anthropic-Call mit Cache-Control auf dem System-Prompt
        (LLMP-S1 `get_chat`, LLMP-S4 Tier-2-Schreibung).

        Cache-Marker-Strategie: identisch zu `eltern-chat/providers/claude.py`
        — der **System-Prompt** trägt `cache_control: ephemeral`, weil er
        zwischen Turns stabil bleibt. Würden wir stattdessen das Top-Level-
        Kwarg `cache_control` setzen, markiert der SDK automatisch den
        letzten cacheable Block (typisch die frische Nutzer-Nachricht); der
        Cache trüge dann nicht über Turns.

        Synchron im selben Call schreibt die Methode den JSONL-Telemetrie-
        Eintrag (LLMP-S4 Doppelschreibung). Vendor-API-Fehler werden als
        `ProviderError` propagiert (analog kibuddy-Alt-Form).
        """
        messages = [*turns, {"role": "user", "content": user_message}]

        # LLMP-S1 `get_chat` Required: `system_message_distinct` + `cache_control`
        # → System trennen, am System-Block den Cache-Marker setzen.
        system_blocks = [{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }]

        t_start = time.monotonic()
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_blocks,
                messages=messages,
            )
        except self._anthropic.APIError as e:
            logger.warning("anthropic-vendor: API-Fehler: %s", e)
            raise ProviderError(str(e)) from e
        wall_ms = int((time.monotonic() - t_start) * 1000)

        # LLMP-S4: synchron im selben Call die JSONL-Projektion schreiben.
        self._emit_telemetry(
            response=response,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )

        text_parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts).strip()

    # ------------------------------------------------------------------
    #  Geteilte Bausteine aller drei Sichten (LLMP-S1, LLMP-S7-Lego-These)
    # ------------------------------------------------------------------

    def _system_blocks(self, system: str) -> list[dict[str, Any]]:
        """System-Block (distinct) mit Cache-Marker — wie `chat_multiturn`."""
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    def _user_content(
        self, prompt: str, images: list[dict[str, Any]] | None,
    ) -> Any:
        """Baut den user-Content (T1262 multimodal_input).

        Ohne `images` byte-identisch der Alt-Form (der reine `prompt`-String).
        Mit `images` `[image-Block(s), text-Block]`: jedes Bild wird aus der
        neutralen Wire-Form `{"bytes", "media_type"}` in einen Anthropic-
        `image`-Block mit base64-`source` gehoben (base64 IM Vendor, wie
        `_multimodal/claude.py:186`). Der text-Block trägt den `prompt`.
        """
        if not images:
            return prompt
        blocks: list[dict[str, Any]] = []
        for img in images:
            raw = img["bytes"]
            media_type = img.get("media_type") or "image/jpeg"
            data_b64 = base64.standard_b64encode(raw).decode("ascii")
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data_b64,
                },
            })
        blocks.append({"type": "text", "text": prompt})
        return blocks

    def _create(self, **kwargs: Any) -> Any:
        """`messages.create` mit APIError→ProviderError (wie `chat_multiturn`)."""
        try:
            return self._client.messages.create(
                model=self.model, max_tokens=self.max_tokens, **kwargs,
            )
        except self._anthropic.APIError as e:
            logger.warning("anthropic-vendor: API-Fehler: %s", e)
            raise ProviderError(str(e)) from e

    # ------------------------------------------------------------------
    #  Sicht: get_singleshot — Structured Singleshot (hoerspiel, T3)
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
        images: list[dict[str, Any]] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Ein Call, forced `tool_use` → Schema-konformes dict (LLMP-S1
        `get_singleshot`). Required: `structured_output` +
        `system_message_distinct` (+ `cache_control`). Telemetrie + ProviderError
        wie `chat_multiturn`.

        `images` (T1262-additiv, multimodal_input): neutrale Wire-Form
        `[{"bytes": <raw>, "media_type": <str>}, …]`. Bei nicht-leerem `images`
        wird der user-Content zu `[image-Block(s), text-Block]` — die base64-
        Kodierung geschieht HIER im Vendor (wie Legacy `_multimodal/claude.py:186`,
        der Konsument reicht nur Rohbytes). `images=None`/leer → byte-identischer
        Text-Pfad (`content=prompt`, Regression-frei für hoerspiel).
        """
        tools = [{
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
            "cache_control": {"type": "ephemeral"},
        }]

        t_start = time.monotonic()
        response = self._create(
            system=self._system_blocks(system),
            messages=[{"role": "user", "content": self._user_content(prompt, images)}],
            tools=tools,
            tool_choice={"type": "tool", "name": tool_name},
        )
        wall_ms = int((time.monotonic() - t_start) * 1000)

        self._emit_telemetry(
            response=response,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
                return dict(block.input) if block.input else {}
        raise ProviderError(
            "anthropic-vendor: forced tool_use lieferte keinen %r-Block" % tool_name
        )

    # ------------------------------------------------------------------
    #  Sicht: get_completion — Freitext-Singleshot (hoerspiel-Synopse, #1131)
    # ------------------------------------------------------------------

    def singleshot_text(
        self,
        system: str,
        user: str,
        *,
        caller: str,
        slot: str,
        correlation_id: str | None = None,
    ) -> str:
        """Ein Call, Freitext-Antwort → str (LLMP-S1 `get_completion`).

        Spiegel `singleshot_structured` OHNE `tools`/`tool_choice`/`schema` —
        ein System + ein User, der reine Text-Content zurück (wie
        `chat_multiturn`). Required: nur `system_message_distinct`; `cache_control`
        ist NICHT Boot-Minimum (llm-providers.md:78-82), Anthropic setzt den
        Cache-Marker am System-Block trotzdem weiter (LLMP-S9). Telemetrie +
        ProviderError wie `chat_multiturn`/`singleshot_structured`.
        """
        t_start = time.monotonic()
        response = self._create(
            system=self._system_blocks(system),
            messages=[{"role": "user", "content": user}],
        )
        wall_ms = int((time.monotonic() - t_start) * 1000)

        self._emit_telemetry(
            response=response,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )

        text_parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts).strip()

    # ------------------------------------------------------------------
    #  Sicht: get_agent — Agent-Tool-Loop (eltern-chat, T4)
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
        """Single-Turn-Create (T1085): EIN Vendor-Call, kein interner Loop.

        Für Konsumenten, die ihren eigenen Loop fahren (eltern-chat). Setzt die
        2× ephemeral-Marker (System-Block + letzter Tool — Anthropic-Semantik,
        `eltern-chat/providers/claude.py:66-68`), emittiert Telemetrie pro Call
        (LLMP-S4) und PARST die Antwort, ohne Tool-Use auszuführen. Bild-Input:
        `messages` wird unverändert durchgereicht (image-Blöcke bleiben). Liefert
        `{"text": <str>, "tool_calls": [{"id","name","input"}…], "usage": <raw>}`.
        """
        system_blocks = self._system_blocks(system)
        # Cache-Marker auf letzten Tool-Eintrag (markiert implizit alle —
        # Anthropic-Semantik, `eltern-chat/providers/claude.py:66-68`).
        wire_tools = [dict(t) for t in tools]
        if wire_tools:
            wire_tools[-1] = {**wire_tools[-1], "cache_control": {"type": "ephemeral"}}

        t_start = time.monotonic()
        response = self._create(
            system=system_blocks,
            messages=list(messages),
            tools=wire_tools,
        )
        wall_ms = int((time.monotonic() - t_start) * 1000)
        self._emit_telemetry(
            response=response,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )

        text = "\n".join(
            b.text for b in response.content
            if getattr(b, "type", None) == "text"
        ).strip()
        tool_calls = [
            {"id": b.id, "name": b.name, "input": dict(b.input) if b.input else {}}
            for b in response.content
            if getattr(b, "type", None) == "tool_use"
        ]
        return {
            "text": text,
            "tool_calls": tool_calls,
            "usage": getattr(response, "usage", None),
        }

    # ------------------------------------------------------------------
    #  Telemetrie-Hilfen (LLMP-S4)
    # ------------------------------------------------------------------

    def _emit_telemetry(
        self,
        *,
        response: Any,
        caller: str,
        slot: str,
        correlation_id: str | None,
        wall_ms: int,
    ) -> None:
        """Baut den `ProviderCallEvent` aus der Anthropic-Response und reicht
        ihn an `tools.llm.telemetry.write_call` weiter (LLMP-S4).

        Bei fehlendem `usage`-Feld (älterer Test-Mock) bleiben die Token-Counts
        auf 0 — der JSONL-Eintrag entsteht trotzdem, damit das Schreib-Format
        in Tests sichtbar bleibt (gleiche Defensive wie
        `eltern-chat/providers/claude._log_token_usage`).
        """
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
        cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0) if usage else 0
        cache_creation_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0) if usage else 0

        est_cost_eur = pricing.compute_eur(
            self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )

        event = {
            "ts": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "caller": caller,
            "slot": slot,
            "model_id": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "wall_ms": wall_ms,
            "est_cost_eur": est_cost_eur,
        }
        if correlation_id is not None:
            event["correlation_id"] = correlation_id

        telemetry.write_call(event)
