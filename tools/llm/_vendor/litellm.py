"""LiteLLM-Vendor-File für `tools.llm` (LLMP-4, LLMP-S12/RAT-26).

LiteLLM ist der Motor **unter** der Fassade (in-Prozess, kein HTTP-Hop, kein
eigener Service — RAT-20 unangetastet). Diese Datei ist ein separates Vendor-
Modul neben `_vendor/anthropic.py`; die vier Public-Sichten, der Slot-Resolver,
die Capability-Matrix und die Telemetrie (LLMP-S4) bleiben unverändert.

V1 (Slot 1, #1316/#1433) implementierte NUR `chat_multiturn(...)` für die
KIBuddy-Migration — like-for-like Motor-Swap (gleiches Modell
`claude-haiku-4-5`, Route `litellm` statt `anthropic`).

Slot 2 (#1449/#1452) migriert die Agent-Sicht: `agent_step(...)` ist jetzt
implementiert (Spiegel `_vendor/mistral.py`, aber getattr-Zugriff gegen die
LiteLLM-`ModelResponse`-Objekte statt dict.get). Sie übersetzt die neutrale
(Anthropic-shaped) Wire-Form beidseitig auf/von der OpenAI-Chat-Completions-
Form, setzt `cache_control: ephemeral` am System-Block (Kosten-Parität zum
Alt-eltern-chat-Pfad) und liefert die neutrale
`{"text", "tool_calls", "usage", "web_search", "web_search_requests"}`-Form
(web_search leer/0 — der Vendor deklariert kein web_search). `singleshot_*`
bleibt `NotImplementedError` (Slot 2-Rest, #1316); wer es heute ruft, sieht
klar, dass die Sicht auf diesem Vendor noch nicht migriert ist.

Cache-Marker-Strategie (LLMP-S1 `get_chat` Required `cache_control`): identisch
zur Anthropic-Hand-Form — der **System-Prompt** trägt `cache_control:
ephemeral`. LiteLLM reicht `cache_control`-Marker auf Content-Blöcken zum
Anthropic-Backend durch (offizielles LiteLLM-Prompt-Caching-Passthrough); der
Marker sitzt am stabilen System-Block, damit er über Turns trägt.

Telemetrie bleibt Hand (LLMP-S12): `telemetry.write_call` →
`provider_calls.jsonl` bleibt SSoT; LiteLLM-native `completion_cost()` wird
NICHT genutzt (Zahl-Stabilität bei Rollback). LiteLLM liefert Usage OpenAI-
förmig (`prompt_tokens`/`completion_tokens`); diese werden auf das interne
`input`/`output`-Schema gemappt, `pricing.compute_eur` rechnet mit `self.model`.
"""

import io
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from .. import pricing, telemetry
from .._types import ProviderError
from ._base import VendorBase

logger = logging.getLogger(__name__)

# LLMP-4 / LLMP-3: maschinell prüfbare Capability-Deklaration am Modulkopf.
# V1 (Slot 1) deklarierte das `get_chat`-Boot-Minimum (REQUIRED_CHAT):
# multi_turn_assistant_prefill + cache_control + system_message_distinct.
# Slot 2 (#1449/#1452) migriert die Agent-Sicht (`agent_step`) auf LiteLLM und
# fügt darum `tool_use` hinzu — das `get_agent`-Boot-Minimum (REQUIRED_AGENT)
# ist damit gedeckt (tool_use + multi_turn_assistant_prefill +
# system_message_distinct). `web_search` wird BEWUSST NICHT deklariert: der
# server-seitige web_search-Pfad bleibt auf dem anthropic-Vendor (hoerspiel);
# eltern-chat fährt reine Client-Tools. structured_output/multimodal_input
# folgen mit den noch nicht migrierten singleshot-Sichten (#1316).
# `speech` + `transcription` (T1410, LLMP-S6/RAT-28): dieser Vendor implementiert
# beide Audio-Modalitäten über `litellm.speech()` / `litellm.transcription()` —
# darum werden sie hier deklariert (REQUIRED_SPEECH / REQUIRED_TRANSCRIPTION in
# public_api.py gaten die get_speech/get_transcription-Sichten dagegen).
CAPABILITIES = frozenset({
    "tool_use",
    "multi_turn_assistant_prefill",
    "cache_control",
    "system_message_distinct",
    "speech",
    "transcription",
})

# Vendor-Default-Modell, falls der Konsument keines wählt. Like-for-like zur
# KIBuddy-Alt-Form (Anthropic-Hand-Vendor DEFAULT_MODEL): `claude-haiku-4-5`.
# LiteLLM erkennt Anthropic-Modelle am Präfix bzw. am blanken Namen und routet
# auf die Anthropic-Messages-API.
DEFAULT_MODEL = "claude-haiku-4-5"
DEFAULT_MAX_TOKENS = 2048

# Hinweis für die noch nicht migrierten singleshot-Sichten (#1316).
_NOT_IMPLEMENTED_HINT = (
    "litellm-vendor: %s ist noch nicht auf LiteLLM migriert — "
    "chat_multiturn (get_chat) und agent_step (get_agent) sind migriert. "
    "singleshot folgt mit #1316. Nutze bis dahin den anthropic-Slot."
)


class LitellmVendor(VendorBase):
    """LiteLLM-Messages-Adapter — `chat_multiturn` + `agent_step` + Audio.

    Hält den lazy-importierten `litellm`-SDK-Handle. `agent_step` (Slot 2,
    #1449/#1452) ist implementiert; die `singleshot_*`-Sichten werfen weiterhin
    `NotImplementedError` mit klarem Slot-Hinweis, damit ein versehentlicher
    `get_singleshot`-Ruf gegen diesen Vendor sofort sichtbar wird (Spiegel
    Anthropic-V1-Ansatz).

    `agent_run` und `_tool_result_block` werden von `VendorBase` geerbt (LLMP-S7,
    kein Copy — Spiegel `_vendor/mistral.py`); der Loop dort ruft `agent_step`
    dynamisch.
    """

    name = "litellm"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        # Lazy-Import des SDKs analog `_vendor/anthropic.py` — Tests, die
        # `tools.llm` ohne echte SDK-Last laden (Capability-Boot-Fail, Resolver,
        # Telemetrie, Pricing), brauchen `litellm` nicht als Test-Dependency;
        # die Vendor-Tests mocken `litellm.completion` über sys.modules.
        import litellm

        self._litellm = litellm
        self._api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------
    #  Sicht: get_chat — Multi-Turn-Konversation (KIBuddy, T1082/T1433)
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
        """Mehrturn-LiteLLM-Call mit Cache-Control auf dem System-Prompt
        (LLMP-S1 `get_chat`, LLMP-S4 Tier-2-Schreibung).

        OpenAI-Message-Form: der System-Prompt wird als eigene
        `{"role": "system", …}`-Message vorangestellt (system_message_distinct).
        Der Cache-Marker sitzt als `cache_control: ephemeral` auf dem System-
        Content-Block (Liste-Form), den LiteLLM zum Anthropic-Backend
        durchreicht — identische Strategie wie `_vendor/anthropic.py`, damit der
        Cache über Turns trägt (stabiler System-Block, nicht die frische
        Nutzer-Nachricht).

        Synchron im selben Call schreibt die Methode den JSONL-Telemetrie-
        Eintrag (LLMP-S4 Doppelschreibung). LiteLLM-API-Fehler werden als
        `ProviderError` propagiert (analog anthropic-Vendor).
        """
        # system_message_distinct + cache_control: der System-Prompt als eigene
        # OpenAI-Message, sein Content ist eine Block-Liste mit dem Cache-Marker
        # (LiteLLM-Anthropic-Prompt-Caching-Passthrough).
        messages = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            },
            *turns,
            {"role": "user", "content": user_message},
        ]

        t_start = time.monotonic()
        try:
            response = self._litellm.completion(
                model=self.model,
                messages=messages,
                api_key=self._api_key,
                max_tokens=self.max_tokens,
            )
        except self._litellm.exceptions.APIError as e:
            logger.warning("litellm-vendor: API-Fehler: %s", e)
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

        return self._extract_text(response)

    # ------------------------------------------------------------------
    #  Sicht: get_speech / get_transcription — Audio (KIBuddy, T1410)
    # ------------------------------------------------------------------

    def speech(
        self,
        text: str,
        *,
        voice: str,
        caller: str,
        slot: str,
        model: str = "",
        speed: float = 1.0,
        response_format: str = "mp3",
        correlation_id: str | None = None,
    ) -> bytes:
        """TTS über `litellm.speech()` → Audio-Bytes (LLMP-S6/RAT-28).

        Mappt auf `litellm.speech(model, voice, input=text, speed,
        response_format, api_key)`. `model` überschreibt den Vendor-Default
        (leer → self.model); `speed` und `response_format` werden explizit
        durchgereicht (Azure-tts-1-hd akzeptiert beide, Spiegel des Alt-
        Azure-SDK-Pfads `audio.speech.create`).

        Azure-Routing (dokumentierte Annahme, echter Byte-Beweis am Nic-Deploy):
        das effektive Modell trägt das LiteLLM-Präfix `azure/<deployment>`
        (z. B. `azure/tts-1-hd`); `api_base`/`api_version` reicht LiteLLM aus den
        ENV-Variablen `AZURE_API_BASE`/`AZURE_API_VERSION` bzw. wird vom Konsumenten
        gesetzt — dieser Vendor gibt nur model/voice/api_key vor.

        Robuster Byte-Extraktor: LiteLLM liefert je nach Provider ein Objekt mit
        `.content` (bytes), sonst mit `.read()` (Stream), sonst bereits raw bytes.
        Telemetrie synchron im selben Call (modality=tts). LiteLLM-API-Fehler →
        `ProviderError`.
        """
        eff_model = model or self.model
        t_start = time.monotonic()
        try:
            response = self._litellm.speech(
                model=eff_model,
                voice=voice,
                input=text,
                speed=speed,
                response_format=response_format,
                api_key=self._api_key,
            )
        except self._litellm.exceptions.APIError as e:
            logger.warning("litellm-vendor: speech-API-Fehler: %s", e)
            raise ProviderError(str(e)) from e
        wall_ms = int((time.monotonic() - t_start) * 1000)

        audio_bytes = self._extract_audio_bytes(response)

        self._emit_audio_telemetry(
            modality="tts",
            model_id=eff_model,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )
        return audio_bytes

    def transcription(
        self,
        audio: bytes,
        *,
        caller: str,
        slot: str,
        model: str = "",
        filename: str = "audio.mp3",
        language: str = "de",
        correlation_id: str | None = None,
    ) -> str:
        """STT über `litellm.transcription()` → Transkript-Text (LLMP-S6/RAT-28).

        Verpackt `audio` in einen `io.BytesIO` mit `.name = filename` (LiteLLM/
        OpenAI leiten das Audio-Format aus der Extension ab), mappt auf
        `litellm.transcription(model, file, language, api_key)` und zieht `.text`
        aus der Response. `model` überschreibt den Vendor-Default (leer →
        self.model).

        Azure-Routing (dokumentierte Annahme, echter Byte-Beweis am Nic-Deploy):
        das effektive Modell trägt das LiteLLM-Präfix `azure/<deployment>` (z. B.
        `azure/whisper-1`); `api_base`/`api_version` wie bei `speech()`.

        Wichtig (#1442): die ffmpeg-Normalisierung des Browser-webm läuft VOR
        diesem Call — sie sitzt im STT-Engine-Adapter (kibuddy/stt_service.py),
        nicht hier, damit der Vendor Provider-neutral bleibt. Telemetrie synchron
        (modality=stt). LiteLLM-API-Fehler → `ProviderError`.
        """
        eff_model = model or self.model
        audio_file = io.BytesIO(audio)
        audio_file.name = filename

        t_start = time.monotonic()
        try:
            response = self._litellm.transcription(
                model=eff_model,
                file=audio_file,
                language=language,
                api_key=self._api_key,
            )
        except self._litellm.exceptions.APIError as e:
            logger.warning("litellm-vendor: transcription-API-Fehler: %s", e)
            raise ProviderError(str(e)) from e
        wall_ms = int((time.monotonic() - t_start) * 1000)

        text = self._extract_transcript(response)

        self._emit_audio_telemetry(
            modality="stt",
            model_id=eff_model,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )
        return text

    # ------------------------------------------------------------------
    #  Sicht: get_agent — Single-Turn + Tool-Loop (eltern-chat, Slot 2/#1452)
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
        """Single-Turn-Create gegen LiteLLM: EIN Call, kein interner Loop.

        Spiegel `_vendor/mistral.py:agent_step` — übersetzt die neutrale
        (Anthropic-shaped) Wire-Form → OpenAI-Chat-Completions-Payload, ruft
        `litellm.completion`, emittiert Telemetrie (LLMP-S4) und parst die
        LiteLLM-`ModelResponse` (Attribut-/getattr-Zugriff, NICHT dict.get) in
        die neutrale Rückgabe. `agent_run` (VendorBase) fährt den Tool-Loop und
        ruft diese Methode pro Iteration.

        Cache-Parität (LLMP-S1): der System-Prompt trägt `cache_control:
        ephemeral` als eigene `{"role":"system", …}`-Message (Muster
        `chat_multiturn`), damit der Anthropic-Backend-Cache über Turns trägt —
        wie der Alt-eltern-chat-Pfad (`providers/claude.py:66-68`) cachte.

        Liefert die neutrale Anthropic-shaped Form
        `{"text", "tool_calls":[{"id","name","input"}…], "usage": <raw>,
        "web_search": [], "web_search_requests": 0}`. Die beiden web_search-
        Schlüssel sind additiv-konstant leer/0 (dieser Vendor deklariert kein
        web_search; eltern-chat fährt reine Client-Tools). LiteLLM-API-Fehler →
        `ProviderError` (analog `chat_multiturn`).
        """
        wire_messages = self._to_litellm_messages(system, messages)
        wire_tools = [self._to_litellm_tool(t) for t in tools]

        completion_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": wire_messages,
            "api_key": self._api_key,
            "max_tokens": self.max_tokens,
        }
        if wire_tools:
            completion_kwargs["tools"] = wire_tools

        t_start = time.monotonic()
        try:
            response = self._litellm.completion(**completion_kwargs)
        except self._litellm.exceptions.APIError as e:
            logger.warning("litellm-vendor: agent-API-Fehler: %s", e)
            raise ProviderError(str(e)) from e
        wall_ms = int((time.monotonic() - t_start) * 1000)

        self._emit_telemetry(
            response=response,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )
        return self._parse_agent_response(response)

    # ------------------------------------------------------------------
    #  Slot 2-Rest — singleshot noch nicht migriert (#1316)
    # ------------------------------------------------------------------

    def singleshot_structured(self, *args: Any, **kwargs: Any) -> Any:
        """Slot 2 (get_singleshot) — noch nicht auf LiteLLM migriert (#1316)."""
        raise NotImplementedError(_NOT_IMPLEMENTED_HINT % "singleshot_structured")

    def singleshot_text(self, *args: Any, **kwargs: Any) -> Any:
        """Slot 2 (get_completion) — noch nicht auf LiteLLM migriert (#1316)."""
        raise NotImplementedError(_NOT_IMPLEMENTED_HINT % "singleshot_text")

    # ------------------------------------------------------------------
    #  neutrale (Anthropic-shaped) Wire-Form -> OpenAI-Payload (agent_step)
    # ------------------------------------------------------------------

    def _to_litellm_messages(
        self,
        system: str,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Baut die OpenAI-Message-Liste aus der neutralen Agent-Wire-Form.

        Der System-Prompt wird als eigene `{"role":"system", …}`-Message mit
        `cache_control: ephemeral` auf dem Content-Block vorangestellt
        (system_message_distinct + Cache-Parität, Muster `chat_multiturn`). Jede
        neutrale Message wird über `_to_litellm_message` in eine Liste OpenAI-
        Nachrichten übersetzt (tool_result-Blöcke expandieren zu je einer
        `{"role":"tool", …}`-Nachricht — daher `.extend()`).
        """
        wire: list[dict[str, Any]] = []
        if system:
            wire.append({
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            })
        for m in messages:
            wire.extend(self._to_litellm_message(m))
        return wire

    @classmethod
    def _to_litellm_message(cls, message: dict[str, Any]) -> list[dict[str, Any]]:
        """Neutrale Message → Liste OpenAI-Nachrichten (Spiegel
        `mistral._to_mistral_message`, gleiche Block-Semantik).

        String-`content` bleibt String. Block-`content` (Anthropic-shaped) wird
        je Block-Typ übersetzt: `tool_use` → assistant-`tool_calls`,
        `tool_result` → je Block eine eigene `{"role":"tool", …}`-Nachricht
        (is_error-Prefix wie mistral), `text`/`image` → OpenAI-content-parts
        (image_url data-URL).
        """
        role = message.get("role", "user")
        content = message.get("content")

        if isinstance(content, str):
            return [{"role": role, "content": content}]

        blocks = content or []

        # Assistant mit tool_use-Blöcken → OpenAI tool_calls.
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
            # OpenAI erlaubt content=None bei reinen tool_calls; Text-Prefill
            # (falls vorhanden) als String durchreichen.
            msg["content"] = "\n".join(text_parts).strip() if text_parts else None
            return [msg]

        # User/Tool mit tool_result-Blöcken → je Result eine tool-Nachricht.
        tool_results = [b for b in blocks if b.get("type") == "tool_result"]
        if tool_results:
            return [cls._tool_result_to_litellm(b) for b in tool_results]

        # Normale Text-/Bild-Nachricht → OpenAI content-parts.
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
    def _tool_result_to_litellm(block: dict[str, Any]) -> dict[str, Any]:
        """Neutraler tool_result-Block → OpenAI-`{"role":"tool", …}`-Nachricht.

        `tool_call_id` bindet das Result an den Aufruf; is_error-Wissen wird wie
        in `mistral._tool_result_to_mistral` in den Inhalt gehoben (OpenAI-tool-
        Messages tragen kein eigenes Fehler-Flag).
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

    @staticmethod
    def _to_litellm_tool(tool: dict[str, Any]) -> dict[str, Any]:
        """Neutrales `{name, description, input_schema}` → OpenAI-function-Form
        (Spiegel `mistral._to_mistral_tool`)."""
        return {
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }

    def _parse_agent_response(self, response: Any) -> dict[str, Any]:
        """LiteLLM-`ModelResponse` → neutrale Anthropic-shaped Agent-Form.

        Attribut-/getattr-Zugriff gegen das ModelResponse-Objekt (NICHT dict.get
        wie mistral, das gegen `response.json()` arbeitet):
        `response.choices[0].message.content` (Text, kann None sein),
        `.message.tool_calls[i].id / .function.name / .function.arguments`.
        `input = json.loads(arguments or "{}")` defensiv (JSONDecodeError/
        TypeError → {}). `usage` bleibt das RAW-LiteLLM-Objekt (der Konsument
        liest es getattr-förmig, Spiegel anthropic). web_search konstant leer/0
        (dieser Vendor deklariert kein web_search).
        """
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for choice in getattr(response, "choices", None) or []:
            message = getattr(choice, "message", None)
            if message is None:
                continue
            content = getattr(message, "content", None)
            if content:
                text_parts.append(content)
            for tc in getattr(message, "tool_calls", None) or []:
                fn = getattr(tc, "function", None)
                raw_args = getattr(fn, "arguments", None) or "{}"
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({
                    "id": getattr(tc, "id", "") or "",
                    "name": getattr(fn, "name", "") or "",
                    "input": args if isinstance(args, dict) else {},
                })
        return {
            "text": "\n".join(text_parts).strip(),
            "tool_calls": tool_calls,
            "usage": getattr(response, "usage", None),
            "web_search": [],
            "web_search_requests": 0,
        }

    # ------------------------------------------------------------------
    #  Response-Parse + Telemetrie-Hilfen (LLMP-S4)
    # ------------------------------------------------------------------

    def _extract_text(self, response: Any) -> str:
        """Zieht den Antwort-Text aus der OpenAI-förmigen LiteLLM-Response.

        LiteLLM liefert `.choices[0].message.content` (str). Fehlt der Pfad
        (unerwartete Response-Form) → `ProviderError`, kein stiller Leer-String,
        damit ein Wire-Bruch sichtbar wird (Spiegel Anthropic-Vendor, der einen
        fehlenden Text-Block sichtbar macht).
        """
        try:
            choices = response.choices
            content = choices[0].message.content
        except (AttributeError, IndexError, TypeError) as e:
            raise ProviderError(
                "litellm-vendor: unerwartete Response-Form, kein "
                "choices[0].message.content: %s" % e
            ) from e
        return (content or "").strip()

    def _emit_telemetry(
        self,
        *,
        response: Any,
        caller: str,
        slot: str,
        correlation_id: str | None,
        wall_ms: int,
    ) -> None:
        """Baut den `ProviderCallEvent` aus der LiteLLM-Response und reicht ihn
        an `tools.llm.telemetry.write_call` weiter (LLMP-S4, LLMP-S12).

        LiteLLM liefert Usage OpenAI-förmig (`prompt_tokens`/`completion_tokens`);
        gemappt auf das interne `input`/`output`-Schema. Anthropic-Cache-Zahlen
        (`cache_read_input_tokens`/`cache_creation_input_tokens`) hängt LiteLLM
        bei Anthropic-Routing an das Usage-Objekt (Prompt-Caching-Passthrough) —
        wo vorhanden, werden sie mitgeschrieben; wo nicht (0). Pricing rechnet
        mit `self.model` (Hand-Telemetrie, KEIN litellm.completion_cost —
        Zahl-Stabilität bei Rollback, LLMP-S12).

        Bei fehlendem `usage`-Feld (älterer Test-Mock) bleiben die Token-Counts
        auf 0 — der JSONL-Eintrag entsteht trotzdem (gleiche Defensive wie
        `_vendor/anthropic.py`).
        """
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
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

    # ------------------------------------------------------------------
    #  Audio-Response-Parse + Audio-Telemetrie (T1410, LLMP-S6)
    # ------------------------------------------------------------------

    def _extract_audio_bytes(self, response: Any) -> bytes:
        """Zieht die Audio-Bytes robust aus der LiteLLM-`speech()`-Response.

        LiteLLM/Provider-SDKs liefern hier heterogen: mal ein Objekt mit
        `.content` (bytes, OpenAI-`HttpxBinaryResponseContent`), mal ein Stream
        mit `.read()`, mal bereits `bytes`. Wir probieren in dieser Reihenfolge;
        schlägt alles fehl → `ProviderError` (kein stiller Leer-Blob, damit ein
        Wire-Bruch sichtbar wird — Spiegel `_extract_text`).
        """
        if isinstance(response, (bytes, bytearray)):
            return bytes(response)
        content = getattr(response, "content", None)
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        read = getattr(response, "read", None)
        if callable(read):
            data = read()
            if isinstance(data, (bytes, bytearray)):
                return bytes(data)
        raise ProviderError(
            "litellm-vendor: unerwartete speech()-Response-Form, keine Bytes "
            "über .content / .read() / raw (Typ: %s)" % type(response).__name__
        )

    def _extract_transcript(self, response: Any) -> str:
        """Zieht den Transkript-Text aus der LiteLLM-`transcription()`-Response.

        LiteLLM liefert ein Objekt mit `.text` (str). Fehlt es, wird die
        Response defensiv per `str(...)` verwendet (OpenAI-Text-Direktform),
        analog Alt-Azure-Adapter. Leer/None → leerer String (kein Crash;
        die Stille-Halluzinations-Filterung sitzt im STT-Service).
        """
        text = getattr(response, "text", None)
        if text is None:
            text = response
        return str(text or "").strip()

    def _emit_audio_telemetry(
        self,
        *,
        modality: str,
        model_id: str,
        caller: str,
        slot: str,
        correlation_id: str | None,
        wall_ms: int,
    ) -> None:
        """Schreibt einen Audio-`ProviderCallEvent` (LLMP-S4/LLMP-S6, RAT-28).

        Eigener Pfad neben `_emit_telemetry` (NICHT geteilt): Audio-Responses
        tragen KEINE `usage.prompt_tokens` — input/output_tokens bleiben 0,
        `est_cost_eur` ist `None` (die Pricing-Tabelle kennt keine Audio-Modelle,
        `completion_cost()` wird für Audio bewusst nicht genutzt, LLMP-S6). Das
        `modality`-Feld ("tts"|"stt") unterscheidet den Eintrag im JSONL.
        `write_call` bleibt SSoT (serialisiert beliebige Felder).
        """
        event = {
            "ts": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "caller": caller,
            "slot": slot,
            "model_id": model_id,
            "modality": modality,
            "input_tokens": 0,
            "output_tokens": 0,
            "wall_ms": wall_ms,
            "est_cost_eur": None,
        }
        if correlation_id is not None:
            event["correlation_id"] = correlation_id

        telemetry.write_call(event)
