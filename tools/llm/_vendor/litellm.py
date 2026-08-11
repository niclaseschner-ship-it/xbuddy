"""LiteLLM-Vendor-File für `tools.llm` (LLMP-4, LLMP-S12/RAT-26).

LiteLLM ist der Motor **unter** der Fassade (in-Prozess, kein HTTP-Hop, kein
eigener Service — RAT-20 unangetastet). Diese Datei ist ein separates Vendor-
Modul neben `_vendor/anthropic.py`; die vier Public-Sichten, der Slot-Resolver,
die Capability-Matrix und die Telemetrie (LLMP-S4) bleiben unverändert.

V1 (Slot 1, #1316/#1433) implementierte NUR `chat_multiturn(...)` für die
KIBuddy-Migration — like-for-like Motor-Swap (gleiches Modell
`claude-haiku-4-5`, Route `litellm` statt `anthropic`).

Slot 2 (#1449/#1452) migriert die Agent-Sicht: `agent_step(...)` ist jetzt
implementiert (getattr-Zugriff gegen die LiteLLM-`ModelResponse`-Objekte statt
dict.get). Sie übersetzt die neutrale (Anthropic-shaped) Wire-Form beidseitig
auf/von der OpenAI-Chat-Completions-Form, setzt `cache_control: ephemeral` am
System-Block (Kosten-Parität zum Alt-eltern-chat-Pfad) und liefert die neutrale
`{"text", "tool_calls", "usage", "web_search", "web_search_requests"}`-Form
(web_search leer/0 — der Vendor deklariert kein web_search).

Slot 3 (#1454) migriert die Singleshot-Sichten: `singleshot_structured(...)`
(forced tool_choice named form) und `singleshot_text(...)` (Freitext) sind jetzt
implementiert — getattr-Zugriff gegen die LiteLLM-`ModelResponse` statt dict.get
(wie `agent_step`). Damit trägt der litellm-Vendor die hoerspiel-Folgen-/Synopse-
Pfade (get_singleshot / get_completion); `structured_output` ist in CAPABILITIES
aufgenommen.

Slot 4 (#1509, multimodal_input): `singleshot_structured` nimmt jetzt das
optionale `images`-Kwarg (neutrale Wire-Form `[{"bytes": <raw>, "media_type":
<str>}, …]`) und übersetzt Bild-Blocks in das OpenAI-Vision-Format
(`image_url` mit `data:<media_type>;base64,<data>`-URL). Die base64-Kodierung
geschieht im Vendor (Spiegel `_vendor/anthropic.py:235-245`). `multimodal_input`
ist damit in CAPABILITIES aufgenommen. `foto_analyse` nutzt jetzt diesen Slot
statt des anthropic-Hand-Vendors (LLMP-S1, TAB-5, E-TAB-8).

Cache-Marker-Strategie (LLMP-S1 `get_chat` Required `cache_control`): identisch
zur Anthropic-Hand-Form — der **System-Prompt** trägt `cache_control:
ephemeral`. LiteLLM reicht `cache_control`-Marker auf Content-Blöcken zum
Anthropic-Backend durch (offizielles LiteLLM-Prompt-Caching-Passthrough); der
Marker sitzt am stabilen System-Block, damit er über Turns trägt.

Telemetrie (#1635): `telemetry.write_call` → `provider_calls.jsonl` bleibt
SSoT. Kosten kommen jetzt aus LiteLLM-native `response._hidden_params
["response_cost"]` (Primärpfad) oder `litellm.completion_cost()` (Fallback) —
`pricing.compute_eur` ist damit in diesem Vendor pensioniert (LLMP-S12
überholt). LiteLLM liefert Usage OpenAI-förmig (`prompt_tokens`/
`completion_tokens`); diese werden auf das interne `input`/`output`-Schema gemappt.
"""

import base64
import io
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from .. import pricing, telemetry
from .._types import LLMTimeoutError, ProviderError
from ._base import TIMEOUT_MELDUNG, VendorBase

logger = logging.getLogger(__name__)

# LLMP-4 / LLMP-3: maschinell prüfbare Capability-Deklaration am Modulkopf.
# V1 (Slot 1) deklarierte das `get_chat`-Boot-Minimum (REQUIRED_CHAT):
# multi_turn_assistant_prefill + cache_control + system_message_distinct.
# Slot 2 (#1449/#1452) migriert die Agent-Sicht (`agent_step`) auf LiteLLM und
# fügt darum `tool_use` hinzu — das `get_agent`-Boot-Minimum (REQUIRED_AGENT)
# ist damit gedeckt (tool_use + multi_turn_assistant_prefill +
# system_message_distinct). `web_search` wird BEWUSST NICHT deklariert: der
# server-seitige web_search-Pfad bleibt auf dem anthropic-Vendor (hoerspiel);
# eltern-chat fährt reine Client-Tools.
# Slot 3 (#1454) migriert die Singleshot-Sichten (`singleshot_structured` +
# `singleshot_text`) und fügt `structured_output` hinzu — REQUIRED_SINGLESHOT
# (structured_output + system_message_distinct) und REQUIRED_COMPLETION
# (system_message_distinct) sind damit gedeckt.
# Slot 4 (#1509, multimodal_input): `singleshot_structured` nimmt jetzt das
# optionale `images`-Kwarg und übersetzt Bild-Blocks ins OpenAI-Vision-Format.
# LiteLLM routet `image_url data-URL`-Blocks transparent zum Anthropic-Backend
# durch (offizielles Multimodal-Passthrough). `multimodal_input` wird darum jetzt
# deklariert — der Capability-Gate in `public_api._SingleshotFacade` lässt
# images-Aufrufe gegen diesen Vendor durch (LLMP-3/LLMP-S11).
# `speech` + `transcription` (T1410, LLMP-S6/RAT-28): dieser Vendor implementiert
# beide Audio-Modalitäten über `litellm.speech()` / `litellm.transcription()` —
# darum werden sie hier deklariert (REQUIRED_SPEECH / REQUIRED_TRANSCRIPTION in
# public_api.py gaten die get_speech/get_transcription-Sichten dagegen).
CAPABILITIES = frozenset({
    "tool_use",
    "multi_turn_assistant_prefill",
    "cache_control",
    "multimodal_input",
    "structured_output",
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

# --------------------------------------------------------------------------
#  register_model-Seed (T1634/U3, RAT-26-§5-Amendment)
# --------------------------------------------------------------------------
# Nach diesem Seed ist `litellm.model_cost` die EINE Kosten-SSoT (#1620): die
# `_emit_*`-Naht (#1635) liest dann `response_cost` statt der Hand-`pricing.py`-
# Tabelle. Dieser Schritt füllt nur GENUINE Katalog-Lücken — Modelle, die
# litellm NATIV korrekt kennt (claude-*, mistral/mistral-medium-2508, tts-1-hd,
# whisper-1) werden NICHT überschrieben (Live-Probe litellm 1.93.0). Die eine
# reale Lücke heute ist `mistral/mistral-medium-3504` (Multimodal-Mistral, HSP-27
# — weder blank noch `mistral/`-präfixt im Katalog). Die Kosten kommen aus den
# heutigen `pricing.py`-Zahlen (USD/1M → litellm-Token-Schema); `as_of` fährt als
# Metadatum mit (monthly_rollup-Staleness-Konsument, U3).
#
# Prozess-weit idempotent geguarded: der Seed läuft beim ERSTEN `LitellmVendor`-
# Init einmal, alle Folge-Inits sind no-op (Modul-Flag). `register_model`
# akzeptiert das native `model_cost`-Schema; wir schreiben nur Lücken, nie
# Overrides (Stop-Ventil: native korrekte Einträge unberührt).

_SEED_DONE = False


def _pricing_to_litellm_entry(prices, as_of):
    """USD/1M-Tripel (input, cached_input, output) → litellm-`model_cost`-Eintrag.

    litellm rechnet Kosten pro EINZEL-Token (`input_cost_per_token` /
    `output_cost_per_token`), pricing.py führt USD pro 1 Million Tokens — also
    `/ 1_000_000`. `cache_read_input_token_cost` trägt den (niedrigeren)
    Cached-Input-Preis (Anthropic-Prompt-Caching-Bucket, Spiegel pricing.py).
    `as_of` wandert als reines Metadatum mit (monthly_rollup-Staleness, U3) —
    litellm ignoriert unbekannte Keys.
    """
    input_usd_1m, cached_usd_1m, output_usd_1m = prices
    return {
        "input_cost_per_token": input_usd_1m / 1_000_000.0,
        "output_cost_per_token": output_usd_1m / 1_000_000.0,
        "cache_read_input_token_cost": cached_usd_1m / 1_000_000.0,
        "mode": "chat",
        "as_of": as_of,
    }


def _litellm_response_cost_eur(response: Any, litellm_sdk: Any) -> float | None:
    """Liest `est_cost_eur` aus einer LiteLLM-Response (litellm-native, #1635).

    Reihenfolge:
    1. `response._hidden_params.get("response_cost")` (USD, LiteLLM-native) → EUR.
    2. Fallback: `litellm.completion_cost(completion_response=response)` → EUR.
    3. Ist beides None/0/Fehler → None (z. B. Audio ohne LiteLLM-Kosten-Wissen).

    USD→EUR-Kurs: `pricing.EUR_PER_USD` (0.92, fest wie bisher, E-EC-11).
    `litellm_sdk` wird als Parameter übergeben, damit Tests den Mock nutzen können.
    """
    if response is None:
        return None

    # 1. Primär: _hidden_params.response_cost (USD)
    hidden = getattr(response, "_hidden_params", None)
    cost_usd: float | None = None
    try:
        if hidden is not None and isinstance(hidden, dict):
            raw = hidden.get("response_cost")
            if raw is not None:
                fval = float(raw)
                if fval > 0:
                    cost_usd = fval
    except Exception:
        pass  # Defensiv: kein Absturz bei unerwartetem hidden_params-Typ

    # 2. Fallback: litellm.completion_cost()
    if cost_usd is None:
        try:
            fb = litellm_sdk.completion_cost(completion_response=response)
            if fb is not None:
                fval_fb = float(fb)
                if fval_fb > 0:
                    cost_usd = fval_fb
        except Exception:
            pass  # Best-effort; Audio/unbekannte Modelle können hier 0/Exception geben

    if cost_usd is None:
        return None
    return cost_usd * pricing.EUR_PER_USD


def _seed_model_cost(litellm) -> None:
    """Seedet genuine `litellm.model_cost`-Lücken aus `pricing.py` (U3, idempotent).

    Iteriert die Hand-`pricing.py`-Tabelle, normalisiert jeden Modellnamen auf
    den litellm-Routing-Namen (`normalize_model` — dieselbe Kanonik, mit der der
    Vendor tatsächlich routet, z. B. `mistral-medium-3504` →
    `mistral/mistral-medium-3504`) und registriert NUR die Namen, die litellm
    noch NICHT (oder mit reinen Null-Token-Kosten) kennt. Modelle mit bereits
    nativ gesetzten ≠0-Token-Kosten bleiben unberührt (kein Override — Stop-
    Ventil). Prozess-weit einmalig über das Modul-Flag `_SEED_DONE`.
    """
    global _SEED_DONE
    if _SEED_DONE:
        return

    from .._resolver import normalize_model

    catalog = getattr(litellm, "model_cost", {}) or {}
    to_register: dict[str, Any] = {}
    for bare_name, prices in pricing._PRICES_USD_PER_MILLION.items():
        routing_name = normalize_model(bare_name)
        existing = catalog.get(routing_name) or {}
        native_in = existing.get("input_cost_per_token")
        native_out = existing.get("output_cost_per_token")
        # Nur GENUINE Lücke seeden: kein Eintrag ODER Token-Kosten fehlen/0
        # (native korrekte ≠0-Einträge NICHT überschreiben — Stop-Ventil).
        if native_in and native_out:
            continue
        as_of = pricing.as_of_for(bare_name)
        to_register[routing_name] = _pricing_to_litellm_entry(prices, as_of)

    if to_register:
        litellm.register_model(to_register)

    _SEED_DONE = True


class LitellmVendor(VendorBase):
    """LiteLLM-Messages-Adapter — `chat_multiturn` + `agent_step` + singleshot + Audio.

    Hält den lazy-importierten `litellm`-SDK-Handle. `agent_step` (Slot 2,
    #1449/#1452) UND die `singleshot_*`-Sichten (Slot 3, #1454) sind
    implementiert — der Vendor trägt damit alle vier Text-Sichten
    (get_chat/get_agent/get_singleshot/get_completion) sowie Audio.

    `agent_run` und `_tool_result_block` werden von `VendorBase` geerbt (LLMP-S7,
    kein Copy); der Loop dort ruft `agent_step` dynamisch.
    """

    name = "litellm"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float | None = None,
    ):
        # Lazy-Import des SDKs analog `_vendor/anthropic.py` — Tests, die
        # `tools.llm` ohne echte SDK-Last laden (Capability-Boot-Fail, Resolver,
        # Telemetrie, Pricing), brauchen `litellm` nicht als Test-Dependency;
        # die Vendor-Tests mocken `litellm.completion` über sys.modules.
        import litellm

        # T1634/U3: genuine litellm.model_cost-Lücken aus pricing.py seeden
        # (prozess-weit einmalig, idempotent). Danach ist model_cost die eine
        # Kosten-SSoT für die #1635-Naht. Best-effort — ein register_model-
        # Fehler darf den Vendor-Boot nicht killen (Kosten sind Diagnose-Substrat,
        # kein Wire-Pfad; die #1635-Naht hält bis dahin ohnehin pricing.py).
        try:
            _seed_model_cost(litellm)
        except Exception:  # Seed ist Best-effort, nie boot-fatal
            logger.warning("litellm-vendor: model_cost-Seed fehlgeschlagen", exc_info=True)

        self._litellm = litellm
        self._api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens
        # T1784: EIN Zeit-Budget für alle sechs SDK-Call-Sites dieses Vendors.
        # Ohne das greift litellms Default von 600 s — und der Call hängt im
        # Worker-Thread, der die PrivateChatSession hält (eltern-chat/tasks.py).
        self.timeout = self._resolve_timeout(timeout)
        # Die Timeout-Fehlerklassen EINMAL beim Init auflösen (der SDK-Namensraum
        # ändert sich zur Laufzeit nicht) — `litellm.exceptions.Timeout` erbt
        # NICHT von `litellm.exceptions.APIError` und muss eigens gefangen werden.
        self._timeout_errors = self._timeout_error_classes(
            litellm.exceptions, "Timeout", "APITimeoutError")

    def _sdk_call(self, sdk_fn: Any, *, kontext: str, **kwargs: Any) -> Any:
        """Ein litellm-SDK-Aufruf mit Zeit-Budget + Fehler-Übersetzung (T1784).

        DIE eine Naht für alle sechs Call-Sites dieses Vendors (LLMP-S7: kein
        Copy-Paste über die Sichten). `timeout=self.timeout` geht damit an
        jeden `completion`/`speech`/`transcription`-Aufruf — es gibt keinen
        Pfad mehr, auf dem litellms 600-s-Default gilt.

        `kontext` ist das Sicht-Kürzel für die Log-Zeile ("chat", "agent",
        "singleshot", "completion", "speech", "transcription"). Die
        Sekundenzahl steht im Log (LOG-4-Diagnose), nicht in der Meldung, die
        beim Konsumenten landet.
        """
        try:
            return sdk_fn(timeout=self.timeout, **kwargs)
        except self._timeout_errors as e:
            logger.warning("litellm-vendor: %s-Timeout nach %.1fs: %s",
                           kontext, self.timeout, e)
            raise LLMTimeoutError(TIMEOUT_MELDUNG) from e
        except self._litellm.exceptions.APIError as e:
            logger.warning("litellm-vendor: %s-API-Fehler: %s", kontext, e)
            raise ProviderError(str(e)) from e

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
        response = self._sdk_call(
            self._litellm.completion,
            kontext="chat",
            model=self.model,
            messages=messages,
            api_key=self._api_key,
            max_tokens=self.max_tokens,
        )
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
        response = self._sdk_call(
            self._litellm.speech,
            kontext="speech",
            model=eff_model,
            voice=voice,
            input=text,
            speed=speed,
            response_format=response_format,
            api_key=self._api_key,
        )
        wall_ms = int((time.monotonic() - t_start) * 1000)

        audio_bytes = self._extract_audio_bytes(response)

        self._emit_audio_telemetry(
            modality="tts",
            model_id=eff_model,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
            response=response,
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
        response = self._sdk_call(
            self._litellm.transcription,
            kontext="transcription",
            model=eff_model,
            file=audio_file,
            language=language,
            api_key=self._api_key,
        )
        wall_ms = int((time.monotonic() - t_start) * 1000)

        text = self._extract_transcript(response)

        self._emit_audio_telemetry(
            modality="stt",
            model_id=eff_model,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
            response=response,
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

        Übersetzt die neutrale (Anthropic-shaped) Wire-Form →
        OpenAI-Chat-Completions-Payload, ruft `litellm.completion`, emittiert
        Telemetrie (LLMP-S4) und parst die LiteLLM-`ModelResponse`
        (Attribut-/getattr-Zugriff, NICHT dict.get) in die neutrale Rückgabe.
        `agent_run` (VendorBase) fährt den Tool-Loop und ruft diese Methode pro
        Iteration.

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
        response = self._sdk_call(
            self._litellm.completion, kontext="agent", **completion_kwargs)
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
    #  Sicht: get_singleshot — Structured Singleshot (hoerspiel, Slot 3/#1454)
    # ------------------------------------------------------------------

    def _user_content(
        self,
        prompt: str,
        images: list[dict[str, Any]] | None,
    ) -> Any:
        """Baut den user-Content für singleshot_structured (Slot 4, #1509).

        Ohne `images` byte-identisch der Alt-Form (der reine `prompt`-String,
        KEIN Cap-Gate-Eingriff, Regression-frei für den Text-Pfad).
        Mit `images` OpenAI-Vision-Content-Liste `[image_url-Block(s),
        text-Block]`: jedes Bild aus der neutralen Wire-Form `{"bytes",
        "media_type"}` wird als base64-Data-URL in einen
        `{"type":"image_url","image_url":{"url":"data:<t>;base64,<d>"}}` gehoben
        (base64-Kodierung IM Vendor, Spiegel `_vendor/anthropic.py:235-245`).
        Der text-Block trägt den `prompt` als letzten Eintrag (LLM-Konvention:
        Bild(er) zuerst, dann Instruktion). LiteLLM routet `image_url`-Blocks
        transparent zum Anthropic-Backend durch (OpenAI-Vision-Passthrough).
        """
        if not images:
            return prompt
        parts: list[dict[str, Any]] = []
        for img in images:
            raw = img["bytes"]
            media_type = img.get("media_type") or "image/jpeg"
            data_b64 = base64.standard_b64encode(raw).decode("ascii")
            parts.append({
                "type": "image_url",
                "image_url": {
                    "url": "data:%s;base64,%s" % (media_type, data_b64),
                },
            })
        parts.append({"type": "text", "text": prompt})
        return parts

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
        `get_singleshot`).

        Baut den OpenAI-Chat-Completions-Payload aus EINER user-Message
        (`prompt`) + EINEM Tool (`_to_litellm_tool` — geteilt mit der Agent-
        Sicht) und erzwingt es über die **benannte** `tool_choice`-Form
        (`{"type":"function","function":{"name":tool_name}}`, OpenAI-Parität).

        `images` (Slot 4/#1509, multimodal_input): neutrale Wire-Form
        `[{"bytes": <raw>, "media_type": <str>}, …]`. Bei nicht-leerem `images`
        wird der user-Content zu `[image_url-Block(s), text-Block]` (OpenAI-
        Vision-Format) — die base64-Kodierung geschieht HIER im Vendor (Spiegel
        `_vendor/anthropic.py`; der Konsument reicht nur Rohbytes). `images=None`
        → byte-identischer Text-Pfad (`content=prompt`, Regression-frei).

        Der System-Prompt wird als eigene `{"role":"system", …}`-Message
        vorangestellt (system_message_distinct). ANDERS als `chat_multiturn`/
        `agent_step` wird HIER KEIN `cache_control`-Marker gesetzt: ein
        Singleshot ist ein Ein-Turn-Call ohne Cache-Nutzen.

        Parst die LiteLLM-`ModelResponse` per getattr:
        `response.choices[i].message.tool_calls[j].function.name/arguments`.
        `json.loads(function.arguments)` defensiv (JSONDecodeError/TypeError →
        {}). Kein `tool_call` mit `name==tool_name` → `ProviderError`. Telemetrie
        via geteiltem `_emit_telemetry` (kein Copy-Paste — LLMP-S7). LiteLLM-API-
        Fehler → `ProviderError` (analog `chat_multiturn`/`agent_step`).
        """
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": self._user_content(prompt, images)})

        completion_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "api_key": self._api_key,
            "max_tokens": self.max_tokens,
            "tools": [self._to_litellm_tool({
                "name": tool_name,
                "description": tool_description,
                "input_schema": schema,
            })],
            # Benannte Form (OpenAI-Parität, Spiegel mistral) — pinnt das EINE
            # Schema-Tool statt "auto"/"required".
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
        }

        t_start = time.monotonic()
        response = self._sdk_call(
            self._litellm.completion, kontext="singleshot", **completion_kwargs)
        wall_ms = int((time.monotonic() - t_start) * 1000)

        self._emit_telemetry(
            response=response,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )

        for choice in getattr(response, "choices", None) or []:
            message = getattr(choice, "message", None)
            if message is None:
                continue
            for tc in getattr(message, "tool_calls", None) or []:
                fn = getattr(tc, "function", None)
                if getattr(fn, "name", None) != tool_name:
                    continue
                raw_args = getattr(fn, "arguments", None) or "{}"
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                return args if isinstance(args, dict) else {}
        raise ProviderError(
            "litellm-vendor: forced tool_use lieferte keinen %r-Block" % tool_name
        )

    # ------------------------------------------------------------------
    #  Sicht: get_completion — Freitext-Singleshot (hoerspiel-Synopse, Slot 3/#1454)
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

        Baut den Payload aus EINEM system + EINEM user-Message, OHNE
        `tools`/`tool_choice`/`schema`, und gibt den Text-Content zurück
        (`_extract_text` — geteilt mit `chat_multiturn`). KEIN
        `cache_control`-Marker (Ein-Turn-Singleshot).
        Telemetrie via geteiltem `_emit_telemetry` (kein Copy-Paste — LLMP-S7).
        LiteLLM-API-Fehler → `ProviderError` (analog `chat_multiturn`).
        """
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        t_start = time.monotonic()
        response = self._sdk_call(
            self._litellm.completion,
            kontext="completion",
            model=self.model,
            messages=messages,
            api_key=self._api_key,
            max_tokens=self.max_tokens,
        )
        wall_ms = int((time.monotonic() - t_start) * 1000)

        self._emit_telemetry(
            response=response,
            caller=caller,
            slot=slot,
            correlation_id=correlation_id,
            wall_ms=wall_ms,
        )
        return self._extract_text(response)

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
        """Neutrale Message → Liste OpenAI-Nachrichten.

        String-`content` bleibt String. Block-`content` (Anthropic-shaped) wird
        je Block-Typ übersetzt: `tool_use` → assistant-`tool_calls`,
        `tool_result` → je Block eine eigene `{"role":"tool", …}`-Nachricht
        (is_error-Prefix), `text`/`image` → OpenAI-content-parts
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

        `tool_call_id` bindet das Result an den Aufruf; is_error-Wissen wird in
        den Inhalt gehoben (OpenAI-tool-Messages tragen kein eigenes Fehler-Flag).
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
        """Neutrales `{name, description, input_schema}` → OpenAI-function-Form."""
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
        an `tools.llm.telemetry.write_call` weiter (LLMP-S4, #1635).

        Kosten-Quelle: LiteLLM-native `response._hidden_params["response_cost"]`
        (USD, von LiteLLM aus dem nativ geseedeten model_cost berechnet), dann
        USD→EUR mit `pricing.EUR_PER_USD` (0.92, fester Kurs wie bisher).
        Ist `response_cost` None/0 → Fallback auf `litellm.completion_cost()`
        (ebenfalls USD→EUR). Beide Pfade sind LiteLLM-native (LLMP-S12 überholt).

        LiteLLM liefert Usage OpenAI-förmig (`prompt_tokens`/`completion_tokens`);
        gemappt auf das interne `input`/`output`-Schema. Anthropic-Cache-Zahlen
        (`cache_read_input_tokens`/`cache_creation_input_tokens`) hängt LiteLLM
        bei Anthropic-Routing an das Usage-Objekt (Prompt-Caching-Passthrough) —
        wo vorhanden, werden sie mitgeschrieben; wo nicht (0).

        Bei fehlendem `usage`-Feld (älterer Test-Mock) bleiben die Token-Counts
        auf 0 — der JSONL-Eintrag entsteht trotzdem (gleiche Defensive wie
        `_vendor/anthropic.py`).
        """
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0) if usage else 0
        cache_creation_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0) if usage else 0

        est_cost_eur = _litellm_response_cost_eur(response, self._litellm)

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
        response: Any = None,
    ) -> None:
        """Schreibt einen Audio-`ProviderCallEvent` (LLMP-S4/LLMP-S6, RAT-28, #1635).

        Eigener Pfad neben `_emit_telemetry` (NICHT geteilt): Audio-Responses
        tragen KEINE `usage.prompt_tokens` — input/output_tokens bleiben 0.
        `est_cost_eur` kommt aus LiteLLM-native `response_cost` (falls vorhanden),
        Fallback `completion_cost()`. Ist beides None/0/Fehler → bleibt `None`
        (Audio-Ausnahme-Pfad LLMP-S6: LiteLLM kennt TTS/STT-Kosten nativ, aber
        der Hand-Fallback aus pricing.py ist für Audio nicht vorhanden — None
        ist der sichere Wert, wenn LiteLLM keine Kosten liefert).
        Das `modality`-Feld ("tts"|"stt") unterscheidet den Eintrag im JSONL.
        `write_call` bleibt SSoT (serialisiert beliebige Felder).
        """
        est_cost_eur = _litellm_response_cost_eur(response, self._litellm) if response is not None else None

        event = {
            "ts": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "caller": caller,
            "slot": slot,
            "model_id": model_id,
            "modality": modality,
            "input_tokens": 0,
            "output_tokens": 0,
            "wall_ms": wall_ms,
            "est_cost_eur": est_cost_eur,
        }
        if correlation_id is not None:
            event["correlation_id"] = correlation_id

        telemetry.write_call(event)
