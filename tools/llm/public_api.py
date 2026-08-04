"""Public-API der LLM-Provider-Lib — vier Sichten auf einem Vendor-Kern
(LLMP-S1, LLMP-2, LLMP-3, LLMP-5).

Jede `get_*`-Funktion ist eine Factory: sie löst den Slot (LLMP-5), lädt das
Vendor-Modul (LLMP-4), prüft die deklarierten `CAPABILITIES` gegen das
sicht-eigene Required-Set (LLMP-3, LLMP-S3) und liefert eine **Sicht-Fassade**
zurück. Bei Mismatch wirft sie `LLMCapabilityError` — kein Runtime-Silent-
Fallback (LLMP-S3 Begründung).

Externe Importe gehen ausschließlich über `from tools.llm import get_chat, …`
(LLMP-4 Re-Export-Form, analog ZD-5/MOD-5).
"""

from typing import Any

from ._resolver import load_vendor_module, normalize_model, parse_slot, resolve_api_key
from ._types import Capability, LLMCapabilityError, LLMProvider

# LLMP-3: Required-Capability-Sets pro Sicht (V1, sechs ratifizierte
# Capabilities aus `conventions/llm-providers.md` LLMP-3).
# LLMP-3-Patch (T1085, R0): `cache_control` ist NICHT mehr Boot-Minimum für
# get_agent. Cache ist eine Anthropic-Optimierung (am Vendor weiterhin gesetzt,
# wo verfügbar), aber kein Pflicht-Gate — sonst könnte ein cache-loser Vendor
# (Mistral) die Agent-Sicht nie bedienen. R0-Spec ist gemergt; dieser Code
# zieht sie nach. Boot-Minimum: tool_use + multi_turn_assistant_prefill +
# system_message_distinct.
REQUIRED_AGENT: frozenset[Capability] = frozenset({
    "tool_use",
    "multi_turn_assistant_prefill",
    "system_message_distinct",
})
REQUIRED_SINGLESHOT: frozenset[Capability] = frozenset({
    "structured_output",
    "system_message_distinct",
})
REQUIRED_CHAT: frozenset[Capability] = frozenset({
    "multi_turn_assistant_prefill",
    "cache_control",
    "system_message_distinct",
})
# LLMP-S1 (#1131, vierte Sicht `get_completion`): Freitext-Singleshot. Boot-
# Minimum ist bewusst NUR `system_message_distinct` — KEIN `structured_output`
# und KEIN `cache_control` (llm-providers.md:78-82). So trägt die Sicht beide
# Slots eines dual-provider-Buddys (hoerspiel Claude UND Mistral); `get_chat`
# wäre auf dem Mistral-Slot boot-fatal (Mistral ⊥ `cache_control`, LLMP-S9).
REQUIRED_COMPLETION: frozenset[Capability] = frozenset({
    "system_message_distinct",
})
# LLMP-S6/RAT-28 (T1410): Audio-Sichten. Boot-Minimum ist genau die eine
# Audio-Capability — Spiegel REQUIRED_COMPLETION. Nur der litellm-Vendor
# deklariert `speech`/`transcription`; ein Text-Hand-Vendor (anthropic/mistral)
# unter einem Audio-Slot wäre boot-fatal (LLMP-S3), was korrekt ist — er kann
# kein Audio.
REQUIRED_SPEECH: frozenset[Capability] = frozenset({
    "speech",
})
REQUIRED_TRANSCRIPTION: frozenset[Capability] = frozenset({
    "transcription",
})


def _build_vendor(
    slot: str,
    sicht_name: str,
    required: frozenset[Capability],
    model: str = "",
    max_tokens: int = 0,
) -> tuple[Any, str, str, frozenset[Capability]]:
    """Slot → (Vendor-Instanz, caller, slot-name, available-caps) mit Capability-
    Boot-Fail (LLMP-S3).

    Verantwortlich für die vier mechanischen Schritte aus LLMP-5:
      1. Slot parsen (caller, vendor, purpose)
      2. Vendor-Modul laden
      3. `CAPABILITIES` gegen Required-Set prüfen (LLMP-3, LLMP-S3)
      4. API-Key über `tools.zugangsdaten` holen + Vendor instanzieren

    `model` (T1085-additiv): wenn nicht-leer, wählt der Konsument das effektive
    Modell explizit — der Vendor nutzt es statt seines `DEFAULT_MODEL`. Leer
    (Default) bewahrt das alte Verhalten (Vendor-Default). Die Vendoren
    akzeptieren `model=` bereits am Konstruktor; hier wird es nur durchgereicht.

    `max_tokens` (T1084-additiv): wenn >0, überschreibt das Vendor-`DEFAULT_MAX_TOKENS`.
    0 (Default) bewahrt das alte Verhalten (Vendor-Default). Analog der
    `model`-Logik: nur durchreichen, wenn der Konsument einen Wert wählt —
    Test-Fakes ohne `max_tokens=`-Kwarg bleiben grün.

    Bei Cap-Mismatch oder fehlender `CAPABILITIES`-Konstante: `LLMCapabilityError`
    als erster Fehler vor allem anderen (LLMP-S3, LLMP-4 Watchdog-Regel).
    """
    caller, vendor, _purpose = parse_slot(slot)
    module = load_vendor_module(vendor)

    available = getattr(module, "CAPABILITIES", None)
    if available is None or not isinstance(available, frozenset):
        # LLMP-4 Watchdog: jeder Vendor-File ohne CAPABILITIES-frozenset ist
        # ein Bruch — beim Boot sichtbar, nicht im 47. Turn.
        raise LLMCapabilityError(
            "tools.llm: Vendor %r deklariert keine CAPABILITIES-frozenset "
            "am Modulkopf (LLMP-4)" % vendor
        )

    missing = required - available
    if missing:
        # LLMP-S3: harter Boot-Fail — sichtbare Konfigurations-Entscheidung,
        # kein Silent-Fallback auf reduziertes Verhalten.
        raise LLMCapabilityError(
            "tools.llm: Sicht %r verlangt Capabilities %s, Vendor %r liefert nur %s "
            "(fehlt: %s) — LLMP-3/LLMP-S3"
            % (sicht_name, sorted(required), vendor, sorted(available), sorted(missing))
        )

    api_key = resolve_api_key(slot)
    if not api_key:
        # ZD-7: der Speicher entscheidet nicht, was ein fehlender Wert bedeutet.
        # `tools.llm` interpretiert „kein Key" als Konfigurationsfehler des
        # Konsumenten — der Boot ist Pflicht-Zeitpunkt, kein Lazy-Pfad.
        raise LLMCapabilityError(
            "tools.llm: kein API-Key im Zugangsdaten-Speicher für Slot %r "
            "(LLMP-5/ZD-5)" % slot
        )

    vendor_cls = _vendor_class(module, vendor)
    # LLMP-S13 (#1463): anbieter-spezifische Modell-Präfix-Normalisierung ZENTRAL
    # hier — der EINE Ort vor den `get_*`-Sichten. Nur der litellm-Motor
    # (Multi-Anbieter-Router) braucht das `provider/`-Präfix; die Hand-Vendoren
    # (`anthropic`/`mistral`) sprechen ihre API direkt mit blanken Namen. Diese
    # eine Gate-Zeile ersetzt die vom Incident #1452 geforderte Verortung — sie
    # trägt eltern-chat UND hoerspiel-mistral gemeinsam, ohne Pro-Vendor-`if`
    # über mehrere Files (Stop-Rule no_vendor_branching).
    if vendor == "litellm":
        model = normalize_model(model)
    # `model` und `max_tokens` nur durchreichen, wenn der Konsument sie wählt —
    # so bleibt der Default-Pfad `vendor_cls(api_key=…)` exakt wie bisher
    # (rückwärtskompatibel für Vendoren/Test-Fakes ohne diese Kwargs).
    # Die Prod-Vendoren akzeptieren beide Params und defaulten auf ihre eigenen
    # Defaults (T1085-Durchreich für model; T1084-Durchreich für max_tokens).
    kwargs: dict[str, Any] = {"api_key": api_key}
    if model:
        kwargs["model"] = model
    if max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    instance = vendor_cls(**kwargs)
    # `available` (die Vendor-CAPABILITIES) wandert mit hinaus: die Singleshot-
    # Fassade braucht sie zur Call-Zeit für das multimodal_input-Gate (T1262,
    # LLMP-S11) — ein images-Aufruf gegen einen Vendor ohne `multimodal_input`
    # wirft `LLMCapabilityError`, nicht Silent-Drop im Vendor.
    return instance, caller, slot, available


def _vendor_class(module: Any, vendor: str) -> type:
    """Lokalisiert die Vendor-Klasse im Modul nach Konvention `<Vendor>Vendor`.

    Beispiel: `_vendor/anthropic.py` enthält `class AnthropicVendor`. Die
    Konvention ist intern (Lib-private), kein Bruch der Public-API.
    """
    class_name = vendor.capitalize() + "Vendor"
    cls = getattr(module, class_name, None)
    if cls is None:
        raise LLMCapabilityError(
            "tools.llm: Vendor-Modul %r enthält keine Klasse %s (Bauregel)"
            % (vendor, class_name)
        )
    return cls


# ----------------------------------------------------------------------
#  Sicht-Fassaden — eine pro Public-API-Funktion (LLMP-S1)
# ----------------------------------------------------------------------


class _ChatFacade:
    """Sicht-Fassade für `get_chat` (LLMP-S1).

    Übersetzt den KIBuddy-Vertrag `complete_multiturn(system, turns,
    user_message)` 1:1 auf den Vendor-Kern und reicht die LLMP-S4-
    Telemetrie-Felder (`caller`, `slot`, optional `correlation_id`)
    transparent durch.
    """

    def __init__(self, vendor: Any, caller: str, slot: str):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        # Für Diagnose und Tests sichtbar (LLMP-S4 `model_id`-Quelle).
        self.model = getattr(vendor, "model", "")
        self.name = "chat"

    def complete_multiturn(
        self,
        system: str,
        turns: list[dict[str, Any]],
        user_message: str,
        *,
        correlation_id: str | None = None,
    ) -> str:
        """1:1-Vertrag zur Alt-`kibuddy.providers.base.LLMProvider`-Form."""
        return self._vendor.chat_multiturn(
            system=system,
            turns=turns,
            user_message=user_message,
            caller=self._caller,
            slot=self._slot,
            correlation_id=correlation_id,
        )


class _SingleshotFacade:
    """Sicht-Fassade für `get_singleshot` (LLMP-S1, hoerspiel-Heimat).

    Übersetzt den Structured-Singleshot-Vertrag `complete_structured(system,
    prompt, schema)` auf den Vendor-Kern und injiziert die LLMP-S4-Telemetrie-
    Felder (`caller`, `slot`) — der Konsument sieht sie nicht (analog
    `_ChatFacade.complete_multiturn`).
    """

    def __init__(self, vendor: Any, caller: str, slot: str,
                 caps: frozenset[Capability] = frozenset()):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        # Vendor-CAPABILITIES für das Call-Zeit-Gate (T1262): ein images-Aufruf
        # gegen einen Vendor ohne `multimodal_input` wirft LLMCapabilityError.
        self._caps = caps
        self.model = getattr(vendor, "model", "")
        self.name = "singleshot"

    def complete_structured(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        *,
        tool_name: str = "ergebnis",
        tool_description: str = "Strukturiertes Ergebnis-Objekt nach Schema.",
        images: list[dict[str, Any]] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Ein Call, forced `tool_use` → Schema-konformes dict (LLMP-S1).

        `images` (T1262-additiv, kw-only): neutrale Wire-Form
        `[{"bytes": <raw>, "media_type": <str>}, …]`, an den Vendor durchgereicht
        (base64-Kodierung IM Vendor). `images=None` ist byte-identisch der
        heutige Text-Pfad (Regression-frei für hoerspiel/get_singleshot-Bestand).

        Cap-Gate (LLMP-3/LLMP-S11): bei nicht-leerem `images` gegen einen Vendor
        OHNE `multimodal_input` wird `LLMCapabilityError` geworfen — der Gate
        sitzt in der LIB (zur Call-Zeit), nicht im Vendor. Der Text-Pfad
        (`images=None`) bleibt für Vendoren ohne `multimodal_input` offen.
        """
        if images and "multimodal_input" not in self._caps:
            raise LLMCapabilityError(
                "tools.llm: complete_structured(images=…) verlangt Capability "
                "'multimodal_input', der Vendor für Slot %r liefert sie nicht "
                "(vorhanden: %s) — LLMP-3/LLMP-S11"
                % (self._slot, sorted(self._caps))
            )
        # `images` NUR bei nicht-leerem Wert an den Vendor durchreichen: so
        # bleibt der Text-Pfad (`images=None`) byte-identisch der Alt-Form —
        # Vendoren, deren `singleshot_structured` (noch) kein `images`-Kwarg
        # kennt (Mistral), bleiben unangetastet (Regression-frei).
        extra: dict[str, Any] = {"images": images} if images else {}
        return self._vendor.singleshot_structured(
            system=system,
            prompt=prompt,
            schema=schema,
            caller=self._caller,
            slot=self._slot,
            tool_name=tool_name,
            tool_description=tool_description,
            correlation_id=correlation_id,
            **extra,
        )


class _CompletionFacade:
    """Sicht-Fassade für `get_completion` (LLMP-S1, hoerspiel-Synopse-Heimat).

    Übersetzt den Freitext-Singleshot-Vertrag `complete(system, user) -> str`
    auf den Vendor-Kern und injiziert die LLMP-S4-Telemetrie-Felder
    (`caller`, `slot`) — der Konsument sieht sie nicht (analog
    `_SingleshotFacade.complete_structured`). Ein System + ein User, ein
    Vendor-Call, KEIN Tool und KEIN Schema (#1131).
    """

    def __init__(self, vendor: Any, caller: str, slot: str):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        self.model = getattr(vendor, "model", "")
        self.name = "completion"

    def complete(
        self,
        system: str,
        user: str,
        *,
        correlation_id: str | None = None,
    ) -> str:
        """Ein Call, Freitext-Antwort → str (LLMP-S1, kein Tool/Schema)."""
        return self._vendor.singleshot_text(
            system=system,
            user=user,
            caller=self._caller,
            slot=self._slot,
            correlation_id=correlation_id,
        )


class _AgentFacade:
    """Sicht-Fassade für `get_agent` (LLMP-S1, eltern-chat-Heimat).

    Übersetzt den Agent-Tool-Loop-Vertrag `run(system, messages, tools,
    tool_runner)` auf den Vendor-Kern und injiziert `caller`/`slot` (LLMP-S4),
    analog `_ChatFacade`.
    """

    def __init__(self, vendor: Any, caller: str, slot: str,
                 caps: frozenset[Capability] = frozenset()):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        # T1371: die Vendor-CAPABILITIES sichtbar machen, damit ein Konsument
        # das opt-in `web_search`-Server-Tool NUR aktiviert, wenn der Slot-Vendor
        # es deklariert (Anthropic ja, Mistral nein). `web_search` ist KEIN
        # Boot-Minimum (REQUIRED_AGENT unverändert) — der Gate sitzt beim Rufer.
        self.capabilities = caps
        self.model = getattr(vendor, "model", "")
        self.name = "agent"

    def run(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_runner: Any = None,
        max_iterations: int = 8,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Tool-Use-Loop mit Mid-Turn-Continuation (LLMP-S1)."""
        return self._vendor.agent_run(
            system=system,
            messages=messages,
            tools=tools,
            caller=self._caller,
            slot=self._slot,
            tool_runner=tool_runner,
            max_iterations=max_iterations,
            correlation_id=correlation_id,
        )

    def step(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Single-Turn-Sicht: EIN Provider-Create, KEIN interner Tool-Loop (T1085).

        Für Konsumenten wie eltern-chat, die ihren eigenen Loop behalten und pro
        Iteration genau einen Create wollen (vgl. `run()`, das den Loop selbst
        fährt). Liefert die geparste Provider-Antwort
        `{"text", "tool_calls", "usage", "web_search", "web_search_requests"}`
        durch — Tool-Use-Blöcke werden NICHT ausgeführt, nur geparst. Die beiden
        `web_search`-Schlüssel sind additiv (T1371): ohne aktiviertes
        `web_search`-Server-Tool bleiben sie `[]`/`0`. Telemetrie pro Create am
        Vendor (LLMP-S4).
        """
        return self._vendor.agent_step(
            system=system,
            messages=messages,
            tools=tools,
            caller=self._caller,
            slot=self._slot,
            correlation_id=correlation_id,
        )


class _SpeechFacade:
    """Sicht-Fassade für `get_speech` (LLMP-S6/RAT-28, KIBuddy-TTS-Heimat).

    Übersetzt `synth(text, *, voice, model, speed, response_format,
    correlation_id) -> bytes` auf `vendor.speech(...)` und injiziert die
    LLMP-S4-Telemetrie-Felder (`caller`, `slot`) — der Konsument sieht sie
    nicht (analog `_ChatFacade`).
    """

    def __init__(self, vendor: Any, caller: str, slot: str):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        self.model = getattr(vendor, "model", "")
        self.name = "speech"

    def synth(
        self,
        text: str,
        *,
        voice: str,
        model: str = "",
        speed: float = 1.0,
        response_format: str = "mp3",
        correlation_id: str | None = None,
    ) -> bytes:
        """Ein TTS-Call → Audio-Bytes (LLMP-S6)."""
        return self._vendor.speech(
            text,
            voice=voice,
            model=model,
            speed=speed,
            response_format=response_format,
            caller=self._caller,
            slot=self._slot,
            correlation_id=correlation_id,
        )


class _TranscriptionFacade:
    """Sicht-Fassade für `get_transcription` (LLMP-S6/RAT-28, KIBuddy-STT-Heimat).

    Übersetzt `transcribe(audio, *, filename, model, language, correlation_id)
    -> str` auf `vendor.transcription(...)` und injiziert `caller`/`slot`
    (LLMP-S4), analog `_SpeechFacade`.
    """

    def __init__(self, vendor: Any, caller: str, slot: str):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        self.model = getattr(vendor, "model", "")
        self.name = "transcription"

    def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "audio.mp3",
        model: str = "",
        language: str = "de",
        correlation_id: str | None = None,
    ) -> str:
        """Ein STT-Call → Transkript-Text (LLMP-S6).

        `audio` ist bereits normalisiert (ffmpeg-#1442 sitzt im STT-Engine-
        Adapter VOR diesem Call, nicht in der Lib).
        """
        return self._vendor.transcription(
            audio,
            filename=filename,
            model=model,
            language=language,
            caller=self._caller,
            slot=self._slot,
            correlation_id=correlation_id,
        )


# ----------------------------------------------------------------------
#  Public-API — die vier `get_*`-Sichten (LLMP-2)
# ----------------------------------------------------------------------


def get_chat(slot: str) -> LLMProvider:
    """Liefert die Multi-Turn-Chat-Sicht (LLMP-S1, KIBuddy-Heimat).

    Required Capabilities (LLMP-3): `multi_turn_assistant_prefill`,
    `cache_control`, `system_message_distinct`. Boot-Fail bei Mismatch.
    """
    vendor, caller, slot_name, _caps = _build_vendor(slot, "get_chat", REQUIRED_CHAT)
    return _ChatFacade(vendor, caller, slot_name)


def get_singleshot(slot: str, model: str = "", max_tokens: int = 0) -> Any:
    """Liefert die Structured-Singleshot-Sicht (LLMP-S1, hoerspiel-Heimat).

    Required Capabilities (LLMP-3): `structured_output`, `system_message_distinct`.
    Boot-Fail bei Mismatch.

    `model` (T1084-additiv): wählt das effektive Modell explizit; leer (Default)
    nutzt den Vendor-`DEFAULT_MODEL` (rückwärtskompatibel — `get_singleshot(slot)`
    bleibt unverändert). hoerspiel reicht hier sein konfiguriertes Modell durch
    (z. B. `claude-opus-4-7`), damit der Lib-Pfad das Modell-Verhalten des
    Alt-Adapters exakt erhält (Spiegel `get_agent`).

    `max_tokens` (T1084-additiv): überschreibt das Vendor-`DEFAULT_MAX_TOKENS` wenn >0;
    0 (Default) erhält den Vendor-Default (2048 Anthropic / 4096 Mistral).
    hoerspiel reicht hier die Provider-eigenen MAX_TOKENS durch (8192 / 4096),
    damit lange Folgentexte nicht beim DEFAULT_MAX_TOKENS=2048 trunkiert werden.
    """
    vendor, caller, slot_name, caps = _build_vendor(
        slot, "get_singleshot", REQUIRED_SINGLESHOT, model, max_tokens,
    )
    return _SingleshotFacade(vendor, caller, slot_name, caps)


def get_completion(slot: str, model: str = "", max_tokens: int = 0) -> Any:
    """Liefert die Freitext-Singleshot-Sicht (LLMP-S1, hoerspiel-Synopse-Heimat).

    Ein System + ein User → Freitext-String über `.complete(system, user)`;
    kein Tool, kein Schema, ein Vendor-Call (#1131 — die von RAT-20/LLMP-S1
    vor-autorisierte vierte Sicht).

    Required Capabilities (LLMP-3): NUR `system_message_distinct` — bewusst
    KEIN `structured_output` und KEIN `cache_control` (llm-providers.md:78-82),
    damit die Sicht beide Slots eines dual-provider-Buddys trägt (hoerspiel
    Claude UND Mistral); `get_chat` wäre auf dem Mistral-Slot boot-fatal
    (LLMP-S9). Boot-Fail bei Mismatch.

    `model` (analog `get_singleshot`): wählt das effektive Modell explizit; leer
    (Default) nutzt den Vendor-`DEFAULT_MODEL` (rückwärtskompatibel).

    `max_tokens` (analog `get_singleshot`/T1084): überschreibt das Vendor-
    `DEFAULT_MAX_TOKENS` wenn >0; 0 (Default) erhält den Vendor-Default
    (2048 Anthropic / 4096 Mistral). hoerspiel reicht hier die Provider-eigenen
    MAX_TOKENS (8192 / 4096) durch, damit lange Synopse-Freitexte nicht beim
    DEFAULT_MAX_TOKENS=2048 trunkiert werden (T1084-Parität).
    """
    vendor, caller, slot_name, _caps = _build_vendor(
        slot, "get_completion", REQUIRED_COMPLETION, model, max_tokens,
    )
    return _CompletionFacade(vendor, caller, slot_name)


def get_agent(slot: str, model: str = "", max_tokens: int = 0) -> Any:
    """Liefert die Agent-Tool-Loop-Sicht (LLMP-S1, eltern-chat-Heimat).

    Required Capabilities (LLMP-3, T1085-Patch): `tool_use`,
    `multi_turn_assistant_prefill`, `system_message_distinct` — `cache_control`
    ist NICHT mehr Boot-Minimum (R0). Liefert `.run()` (Tool-Loop) und
    `.step()` (Single-Turn, ein Create).

    Opt-in `web_search` (T1371): die Fassade legt die Vendor-`CAPABILITIES` als
    `.capabilities` offen. Ein Konsument aktiviert das server-seitige
    `web_search`-Tool NUR, wenn `"web_search" in agent.capabilities` (Anthropic
    ja, Mistral nein) — `web_search` ist KEIN Required-Set-Mitglied, also nie
    Boot-Minimum; der Gate sitzt beim Rufer, nicht im Boot.

    `model` (T1085-additiv): wählt das effektive Modell explizit; leer (Default)
    nutzt den Vendor-`DEFAULT_MODEL` (rückwärtskompatibel — `get_agent(slot)`
    bleibt unverändert). eltern-chat reicht hier das alte effektive Modell durch
    (provider_model bzw. Anbieter-Default), damit der Lib-Pfad das Modell-
    Verhalten des Alt-Adapters exakt erhält.

    `max_tokens` (T1129-additiv): überschreibt das Vendor-`DEFAULT_MAX_TOKENS` wenn >0;
    0 (Default) erhält den Vendor-Default (2048 Anthropic / 4096 Mistral).
    eltern-chat reicht hier den alt-treuen MAX_TOKENS (4096, claude.py:32) durch,
    damit lange Antworten nicht beim DEFAULT_MAX_TOKENS=2048 trunkiert werden
    (Spiegel `get_singleshot`, T1084).
    """
    vendor, caller, slot_name, caps = _build_vendor(
        slot, "get_agent", REQUIRED_AGENT, model, max_tokens,
    )
    return _AgentFacade(vendor, caller, slot_name, caps)


def get_speech(slot: str, model: str = "") -> Any:
    """Liefert die TTS-Sicht (LLMP-S6/RAT-28, KIBuddy-TTS-Heimat).

    Required Capability (LLMP-3): `speech`. Boot-Fail bei Mismatch — ein
    Text-Hand-Vendor unter dem Slot kann kein Audio (korrekt boot-fatal,
    LLMP-S3).

    `model` (analog `get_singleshot`): wählt das effektive TTS-Modell explizit
    (z. B. `azure/tts-1-hd`); leer nutzt den Vendor-`DEFAULT_MODEL`. `max_tokens`
    entfällt (kein Text-Generierungs-Limit bei Audio).
    """
    vendor, caller, slot_name, _caps = _build_vendor(
        slot, "get_speech", REQUIRED_SPEECH, model,
    )
    return _SpeechFacade(vendor, caller, slot_name)


def get_transcription(slot: str, model: str = "") -> Any:
    """Liefert die STT-Sicht (LLMP-S6/RAT-28, KIBuddy-STT-Heimat).

    Required Capability (LLMP-3): `transcription`. Boot-Fail bei Mismatch
    (LLMP-S3).

    `model` (analog `get_speech`): wählt das effektive STT-Modell explizit
    (z. B. `azure/whisper-1`); leer nutzt den Vendor-`DEFAULT_MODEL`.
    """
    vendor, caller, slot_name, _caps = _build_vendor(
        slot, "get_transcription", REQUIRED_TRANSCRIPTION, model,
    )
    return _TranscriptionFacade(vendor, caller, slot_name)
