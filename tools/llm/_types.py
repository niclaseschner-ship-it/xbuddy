"""Typen und Fehlerklassen für `tools.llm` (LLMP-3, LLMP-S4).

Hier liegen die Vertrags-Typen, die sowohl die Public-API als auch die
Vendor-Files brauchen, ohne Vendor-spezifische Importe — damit `tools.llm`
unten ist und nichts oberhalb lädt (MOD-1/MOD-3).

- `LLMCapabilityError` — Boot-Fail bei Slot-Vendor-Capability-Mismatch
  (LLMP-3, LLMP-S3). Wird beim Aufruf einer `get_*`-Sicht geworfen, **nicht**
  erst im 47. Turn.
- `ProviderError` — Vendor antwortet fehlerhaft oder ist nicht erreichbar.
  Konsumenten reagieren typisch mit HTTP 503.
- `LLMProvider` — Minimal-Protokoll, das jede Sicht-Fassade erfüllt; deckt
  den heutigen KIBuddy-Vertrag (`complete_multiturn`) ab und lässt sich von
  weiteren Sicht-Methoden erweitern, sobald diese live sind.
- `ProviderCallEvent` — Schema des JSONL-Telemetrie-Eintrags nach LLMP-S4.
"""

from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

# LLMP-3: die ratifizierten Capabilities. V1 waren es sechs; `web_search` ist
# die 7. (T1371, additiv) — server-seitiges Anthropic-`web_search`-Tool
# (`web_search_20260209`), opt-in in der Agent-Sicht. KEIN Required-Set-Mitglied
# (nie Boot-Minimum): nur Anthropic deklariert sie, Mistral nicht.
# `speech` + `transcription` (T1410, additiv, LLMP-S6/RAT-28) — Audio-Modalitäten
# über `litellm.speech()` / `litellm.transcription()`. Eigene Required-Sets
# (REQUIRED_SPEECH / REQUIRED_TRANSCRIPTION in public_api.py); nur der litellm-
# Vendor deklariert sie (Text-Hand-Vendoren nicht — die können kein Audio).
Capability = Literal[
    "tool_use",
    "multi_turn_assistant_prefill",
    "structured_output",
    "cache_control",
    "multimodal_input",
    "system_message_distinct",
    "web_search",
    "speech",
    "transcription",
]


class LLMCapabilityError(Exception):
    """Slot-Vendor-Mismatch beim Boot (LLMP-3, LLMP-S3).

    Wird beim Aufruf einer `get_*`-Sicht geworfen, wenn der hinter dem Slot
    liegende Vendor nicht alle Required-Capabilities der Sicht deklariert.
    Kein Runtime-Silent-Fallback — das Mismatch ist eine sichtbare
    Konfigurations-Entscheidung, kein versteckter Performance-Bug
    (LLMP-S3 Begründung).
    """


class ProviderError(Exception):
    """Vendor nicht erreichbar oder antwortet fehlerhaft (→ HTTP 503).

    Analog zu `kibuddy.providers.base.ProviderError` (Alt-Form, additiv-
    rückrollbar nach LLMP-S8) — Konsumenten reagieren typisch mit
    HTTP 503. Konkrete Vendor-Files übersetzen ihre SDK-Fehler hierhin.
    """


@runtime_checkable
class LLMProvider(Protocol):
    """Protokoll, das jede Sicht-Fassade aus `get_*` erfüllt (V1-Minimum).

    Heute (T1082) verlangt nur KIBuddy `complete_multiturn(...)`. Weitere
    Methoden werden hinzugefügt, sobald hoerspiel (Structured-Singleshot,
    T3) und eltern-chat (Agent-Tool-Loop, T4) migrieren. Die Methoden-
    Signaturen entstehen mit dem zweiten/dritten Konsumenten, nicht auf
    Vorrat (CLAUDE.md §6).
    """

    def complete_multiturn(
        self,
        system: str,
        turns: list[dict[str, Any]],
        user_message: str,
    ) -> str:
        """Sendet System-Prompt + Turn-Historie + neue Nutzer-Nachricht.

        `turns` ist eine Liste von {"role": "user"|"assistant", "content": str}.
        Gibt den reinen Antwort-Text zurück. Wirft `ProviderError` bei
        Vendor-Fehler.
        """
        ...


class ProviderCallEvent(TypedDict, total=False):
    """JSONL-Eintrag nach LLMP-S4 (Tier-2-Projektion in `var/llm/provider_calls.jsonl`).

    Pflichtfelder (LLMP-S4): `ts`, `caller`, `slot`, `model_id`,
    `input_tokens`, `output_tokens`, `wall_ms`. Optionale Felder:
    `correlation_id` (Caller-Sache; eltern-chat=turn_id, hoerspiel=
    episode_id, kibuddy=chat_id), `cache_read_tokens`,
    `cache_creation_tokens`, `est_cost_eur` (None bei unbekanntem Modell,
    aus `pricing.estimate_cost` — der unified Kosten-Quelle, #1636).

    `modality` (T1410, additiv, LLMP-S6): "tts" | "stt" für Audio-Calls
    (`get_speech` / `get_transcription`). Chat-/Text-Calls setzen es nicht —
    das Feld fehlt dann im JSONL (total=False). Audio-Einträge tragen
    input/output_tokens=0 und est_cost_eur=None (Pricing kennt keine Audio-
    Modelle; Telemetrie für Audio bewusst lockerer, RAT-28).
    """

    ts: str
    caller: str
    correlation_id: str
    slot: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    wall_ms: int
    est_cost_eur: float | None
    modality: str
