"""Typen und Fehlerklassen für `tools.llm` (LLMP-3, LLMP-S4).

Hier liegen die Vertrags-Typen, die sowohl die Public-API als auch die
Vendor-Files brauchen, ohne Vendor-spezifische Importe — damit `tools.llm`
unten ist und nichts oberhalb lädt (MOD-1/MOD-3).

- `LLMCapabilityError` — Boot-Fail bei Slot-Vendor-Capability-Mismatch
  (LLMP-3, LLMP-S3). Wird beim Aufruf einer `get_*`-Sicht geworfen, **nicht**
  erst im 47. Turn.
- `ProviderError` — Vendor antwortet fehlerhaft oder ist nicht erreichbar.
  Konsumenten reagieren typisch mit HTTP 503.
- `LLMTimeoutError` — Sonderfall davon: der Vendor hat das Zeit-Budget
  überschritten (T1784).
- `LLMProvider` — Minimal-Protokoll, das jede Sicht-Fassade erfüllt; deckt
  den heutigen KIBuddy-Vertrag (`complete_multiturn`) ab und lässt sich von
  weiteren Sicht-Methoden erweitern, sobald diese live sind.
- `ProviderCallEvent` — Schema des JSONL-Telemetrie-Eintrags nach LLMP-S4.
- Die Zeit-Budgets (`LLM_TIMEOUT_SECONDS`, `LLM_TIMEOUT_LONGFORM_SECONDS`)
  plus `resolve_timeout` — der EINE Ort, an dem die LLM-Timeouts stehen
  (T1784, CLIENT-2-Form).
"""

import logging
import os
from collections.abc import Mapping
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

_logger = logging.getLogger(__name__)

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


class LLMTimeoutError(ProviderError):
    """Der Vendor hat innerhalb des Zeit-Budgets nicht geantwortet (T1784).

    Subklasse von `ProviderError` — mit Absicht: jeder heutige Konsument fängt
    schon `ProviderError` und behandelt ihn als „Anbieter gerade nicht
    erreichbar". Der Timeout landet damit ohne eine Zeile Konsumenten-Code auf
    demselben Pfad — im eltern-chat also auf dem EC-14-Zweig
    (`main._PROVIDER_DOWN`), der einen familientauglichen deutschen Satz sendet
    statt eines Stacktrace. Wer den Timeout gezielt anders behandeln will
    (Retry, anderes Modell), fängt ihn VOR `ProviderError`.
    """


# --------------------------------------------------------------------------
#  Zeit-Budgets für Vendor-Calls (T1784, CLIENT-2-Form)
# --------------------------------------------------------------------------
# Der EINE Ort, an dem die LLM-Timeouts stehen — kein Wert wird in einem
# Vendor-File oder an einer Call-Site wiederholt. Form wie CLIENT-2 sie für die
# HTTP-Clients vorschreibt: Default als Modul-Konstante, Override am
# Konstruktor.
#
# Warum NICHT die 2,0 s aus CLIENT-2: dort geht es um Loopback-HTTP zwischen
# XBuddy-Komponenten (Normalfall sub-ms). Ein LLM-Call ist eine remote
# Text-Generierung — ein anderes physikalisches Regime. 2,0 s lägen unter dem
# gemessenen p50 des Chat-Pfads und würden die Hälfte aller echten Turns
# abschneiden. Übernommen wird das PRINZIP (zentral, endlich, überschreibbar),
# nicht die Zahl.
#
# Gemessene Realität aus `provider_calls.jsonl` (LLMP-S4-Telemetrie,
# 2026-06-24 .. 2026-08-06, n=188 echte Calls > 50 ms):
#
#   interaktiv (eltern-chat + kibuddy):    p50  3,3 s · p95 11,9 s
#                                          p99 13,7 s · max 14,0 s
#   Langtext (hoerspiel-Folge, litellm):   p50   88 s · max  121 s
#   Langtext (hoerspiel-Recherche, anthr.) p50   89 s · max  308 s
#
# Was ohne diese Budgets gilt — verifiziert gegen die gepinnte litellm==1.93.0
# (nicht aus der Doku abgeschrieben):
#
#   litellm.completion(timeout=None)  → COMPLETION_HTTP_FALLBACK_SECONDS = 600 s
#   litellm.speech(timeout=None)      → litellm.request_timeout = 6000 s (!)
#   litellm.transcription()           → Signatur-Default 600 s
#
# Der TTS-Pfad lag also bei 100 Minuten, nicht bei zehn. Und weil die Calls im
# Worker-Thread laufen, der die `PrivateChatSession` hält
# (eltern-chat/tasks.py), friert ein hängender Anbieter den Chat-TURN der
# Familie ein, nicht bloß den Request. Das ist der Bug aus #1784.
#
# Drei Zeiten sauber getrennt: die Budgets unten sind das GESAMT-Antwort-Budget
# EINES Versuchs (Connect + Zeit-bis-erstes-Token + Generierung). Ein eigenes
# Connect-Budget wird NICHT gesetzt — der Connect ist in allen gemessenen Calls
# im Rausch (< 1 % der Wall-Zeit), und zwei Knöpfe statt einem wären mehr
# Konfigurations-Fläche ohne Erkenntnis-Gewinn. Ein Erstes-Token-Budget wäre
# erst mit Streaming sinnvoll; keine der sechs Sichten streamt heute.
#
# RESTRISIKO, bewusst offen (Retry-Politik ist nicht Gegenstand von #1784):
# litellm setzt `max_retries = litellm.num_retries or openai.DEFAULT_MAX_RETRIES`.
# `litellm.num_retries` ist None, also greift openais Default 2 — der
# HTTP-Client wiederholt einen Timeout bis zu zweimal. Das Budget deckelt
# folglich den EINZELNEN Versuch; die Wall-Zeit im Worst-Case ist ~3× das
# Budget (interaktiv ~90 s statt der ~1800 s von vorher). Wer hart deckeln
# will, setzt `num_retries=0` an den Call-Sites — das ist eine
# Verfügbarkeits-Entscheidung und braucht ein eigenes Ticket.
ENV_TIMEOUT_SECONDS = "XBUDDY_LLM_TIMEOUT_SECONDS"

# Interaktiver Default (Chat-Turn) — ~2,1× das gemessene Maximum von 14,0 s.
# Groß genug, dass eine langsame Anbieter-Stunde keinen falschen Abbruch
# erzeugt; klein genug, dass keine Familie vor einem eingefrorenen Chat sitzt.
LLM_TIMEOUT_SECONDS = 30.0

# Langtext-Generierung (Hörspiel-Folge, Recherche) — ~1,4× das gemessene
# Maximum von 308 s. Hier wartet ein Hintergrund-Job, kein Chat-Turn. Wer
# dieses Budget nutzt, sagt es explizit am `get_*`/Konstruktor-Aufruf; es ist
# NIE der Default.
LLM_TIMEOUT_LONGFORM_SECONDS = 420.0


def resolve_timeout(env: Mapping[str, str] | None = None) -> float:
    """Löst das Default-Zeit-Budget auf: ENV > `LLM_TIMEOUT_SECONDS`.

    Priorität: ENV `XBUDDY_LLM_TIMEOUT_SECONDS` > Default-Konstante. Der
    ENV-Hebel wirkt prozessweit und ist der Not-Knopf am Pi (Anbieter zickt,
    Budget kurz hoch) — jeder Buddy ist seine eigene systemd-Unit, also auch
    pro Buddy setzbar. Ein explizites `timeout=` am Vendor-Konstruktor gewinnt
    immer gegen beides: das ist die bewusste Wahl des Konsumenten (so holt
    hoerspiel sein Langtext-Budget), keine Umgebungs-Frage.

    Unbrauchbare ENV-Werte (kein float, ≤ 0) werden geloggt-ignoriert statt
    boot-fatal: eine krumme ENV darf den Familien-Chat nicht am Start hindern,
    und der Code-Default ist immer ein sicherer Wert. `env`-Parameter ist die
    Test-Naht (analog `telemetry.resolve_jsonl_path`).
    """
    if env is None:
        env = os.environ
    roh = (env.get(ENV_TIMEOUT_SECONDS) or "").strip()
    if not roh:
        return LLM_TIMEOUT_SECONDS
    try:
        wert = float(roh)
    except ValueError:
        _logger.warning(
            "tools.llm: %s=%r ist keine Zahl — nutze Default %.1fs",
            ENV_TIMEOUT_SECONDS, roh, LLM_TIMEOUT_SECONDS)
        return LLM_TIMEOUT_SECONDS
    if wert <= 0:
        _logger.warning(
            "tools.llm: %s=%r ist ≤ 0 (ein unbegrenzter LLM-Call ist der Bug "
            "aus #1784) — nutze Default %.1fs",
            ENV_TIMEOUT_SECONDS, roh, LLM_TIMEOUT_SECONDS)
        return LLM_TIMEOUT_SECONDS
    return wert


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
    input/output_tokens=0 (Audio-Responses tragen keine Token-Usage).

    `audio_chars` / `audio_seconds` (#1905, additiv): die Bezugsgröße, nach der
    das Ton-Modell abrechnet — Zeichen bei TTS (`input_cost_per_character`),
    Sekunden bei STT (`input_cost_per_second`). Beide stehen im Event, damit
    `est_cost_eur` an der Zeile nachrechenbar ist statt nur plausibel
    auszusehen. Konnte die Größe nicht bestimmt werden, fehlt das Feld UND
    `est_cost_eur` bleibt None (leer, nicht null).
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
    audio_chars: int
    audio_seconds: float
