"""KIBuddy — Konfigurations-Auflösung (KIBUDDY-21).

Per-Instanz-Datei `config.json` unter $KIBUDDY_DATA_ROOT (SVC-5).
Geheimnisse (Anthropic-Key, Azure-Key, OpenAI-Key) kommen ausschließlich aus ENV (CONFIG-3).

V1: einziger gültiger `llm_provider` ist `claude` (KIBUDDY-14).
V1: `stt_provider` ist `openai` (Default) oder `azure_openai` (KIBUDDY-12).
T1410 (LLMP-S6/RAT-28): `stt_provider`/`tts_provider` können auf `litellm`
gesetzt werden — dann läuft Audio über `tools.llm.get_transcription` /
`get_speech` hinter einem ZD-Slot statt über direkten Provider-SDK-Code.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

ENV_CONFIG_FILE = "KIBUDDY_CONFIG_FILE"
DEFAULT_CONFIG_FILE = os.path.join(HERE, "config.json")

ENV_DATA_ROOT = "KIBUDDY_DATA_ROOT"
DEFAULT_DATA_ROOT = os.path.join(HERE, "data")

ENV_ANTHROPIC_KEY = "ANTHROPIC_API_KEY"
ENV_AZURE_ENDPOINT = "AZURE_OPENAI_ENDPOINT"
ENV_AZURE_KEY = "AZURE_OPENAI_API_KEY"
ENV_AZURE_API_VERSION = "AZURE_OPENAI_API_VERSION"
ENV_OPENAI_KEY = "OPENAI_API_KEY"

DEFAULT_AZURE_API_VERSION = "2024-10-01-preview"

VALID_PROVIDERS = ("claude",)
# T1410 (LLMP-S6/RAT-28): `litellm` als zusätzlicher Audio-Provider — Audio läuft
# dann über die tools.llm-Fassade (get_speech/get_transcription) hinter einem
# ZD-Slot, kein direkter Provider-SDK-Code mehr in kibuddy.
VALID_STT_PROVIDERS = ("openai", "azure_openai", "litellm")
VALID_TTS_PROVIDERS = ("azure_openai", "litellm")
VALID_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")

DEFAULT_LLM_PROVIDER = "claude"
DEFAULT_LLM_MODEL = "claude-haiku-4-5"
DEFAULT_STT_PROVIDER = "openai"
# TTS-Default bleibt `azure_openai` (heutiges Live-Verhalten, kein Zwangs-Umzug);
# `litellm` ist opt-in per config/ENV (LLMP-S6/RAT-28, Rückweg = Provider-Wechsel).
DEFAULT_TTS_PROVIDER = "azure_openai"
DEFAULT_TTS_VOICE = "onyx"
DEFAULT_TTS_MODEL = "tts-1-hd"
DEFAULT_TTS_SPEED = 0.9
DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_STT_SPRACHE = "de"

# T1410: ZD-Slots + LiteLLM-Modelle für den Audio-Pfad (LLMP-5/LLMP-S6). Die
# `azure/`-Präfixe routen LiteLLM auf Azure-OpenAI-Deployments (api_base/
# api_version aus der ENV — dokumentierte Annahme, Byte-Beweis am Nic-Deploy).
DEFAULT_LITELLM_TTS_SLOT = "kibuddy-litellm-tts-key"
DEFAULT_LITELLM_STT_SLOT = "kibuddy-litellm-stt-key"
DEFAULT_LITELLM_TTS_MODEL = "azure/tts-1-hd"
DEFAULT_LITELLM_STT_MODEL = "azure/whisper-1"
# #1905: Azure-Deployments tragen frei gewählte Namen (`azure/tts`), die im
# LiteLLM-Preis-Katalog nicht stehen. `litellm_tts_base_model` benennt das
# Katalog-Modell dahinter, damit LiteLLM die Ton-Kosten selbst nachschlagen
# kann. Zuordnung, kein Preis — nachprüfbar über
# `GET <endpoint>/openai/deployments` (dort: id=tts → model=tts-hd).
# Leer = Deployment-Name ist selbst der Katalog-Name (z. B. OpenAI-direkt).
DEFAULT_LITELLM_TTS_BASE_MODEL = ""
DEFAULT_AUFNAHME_QUELLE = "display"
DEFAULT_AUFNAHME_MAX_SEK = 30
DEFAULT_INAKTIVITAET_SEK = 60
DEFAULT_PROMPT_MAX_BYTES = 50000
DEFAULT_VAD_STILLE_SEK = 1.5
DEFAULT_VAD_THRESHOLD_DB = -50.0
DEFAULT_VAD_LONG_HOLD_LOCK_SEK = 3.0
DEFAULT_AUFNAHME_MIN_SEK = 0.5


class ConfigError(Exception):
    """Pflicht-Konfiguration fehlt oder ist ungültig (KIBUDDY-21)."""


class RuntimeConfig:
    """Runtime-Config-Snapshot (Bind, Log, Provider, Modelle + Secrets)."""

    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        log_level: str,
        llm_provider: str,
        llm_model: str,
        tts_voice: str,
        tts_model: str,
        tts_speed: float,
        stt_provider: str,
        stt_model: str,
        stt_sprache: str,
        aufnahme_quelle: str,
        aufnahme_max_sek: int,
        inaktivitaet_sek: int,
        prompt_max_bytes: int,
        vad_stille_sek: float,
        vad_threshold_db: float,
        vad_long_hold_lock_sek: float,
        aufnahme_min_sek: float,
        anthropic_key: str | None,
        azure_endpoint: str | None,
        azure_key: str | None,
        azure_api_version: str,
        openai_key: str | None,
        # T1410 (LLMP-S6): additive Audio-Provider-Felder mit Defaults — so
        # bleiben bestehende positionale RuntimeConfig(...)-Konstruktionen
        # (kibuddy/tests/conftest.py) rückwärtskompatibel. resolve_runtime
        # reicht die aufgelösten Werte per Keyword durch.
        tts_provider: str = DEFAULT_TTS_PROVIDER,
        litellm_tts_slot: str = DEFAULT_LITELLM_TTS_SLOT,
        litellm_stt_slot: str = DEFAULT_LITELLM_STT_SLOT,
        litellm_tts_model: str = DEFAULT_LITELLM_TTS_MODEL,
        litellm_stt_model: str = DEFAULT_LITELLM_STT_MODEL,
        litellm_tts_base_model: str = DEFAULT_LITELLM_TTS_BASE_MODEL,
    ):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.log_level = log_level
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.tts_provider = tts_provider
        self.tts_voice = tts_voice
        self.tts_model = tts_model
        self.tts_speed = tts_speed
        self.stt_provider = stt_provider
        self.stt_model = stt_model
        self.stt_sprache = stt_sprache
        self.litellm_tts_slot = litellm_tts_slot
        self.litellm_stt_slot = litellm_stt_slot
        self.litellm_tts_model = litellm_tts_model
        self.litellm_stt_model = litellm_stt_model
        self.litellm_tts_base_model = litellm_tts_base_model
        self.aufnahme_quelle = aufnahme_quelle
        self.aufnahme_max_sek = aufnahme_max_sek
        self.inaktivitaet_sek = inaktivitaet_sek
        self.prompt_max_bytes = prompt_max_bytes
        self.vad_stille_sek = vad_stille_sek
        self.vad_threshold_db = vad_threshold_db
        self.vad_long_hold_lock_sek = vad_long_hold_lock_sek
        self.aufnahme_min_sek = aufnahme_min_sek
        self.anthropic_key = anthropic_key
        self.azure_endpoint = azure_endpoint
        self.azure_key = azure_key
        self.azure_api_version = azure_api_version
        self.openai_key = openai_key

    def to_public_dict(self) -> dict[str, Any]:
        """Form für GET /config (KIBUDDY-24). Geheimnisse fliegen raus (LOG-3)."""
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "tts_provider": self.tts_provider,
            "tts_voice": self.tts_voice,
            "tts_model": self.tts_model,
            "tts_speed": self.tts_speed,
            "stt_provider": self.stt_provider,
            "stt_model": self.stt_model,
            "stt_sprache": self.stt_sprache,
            "aufnahme_quelle": self.aufnahme_quelle,
            "aufnahme_max_sek": self.aufnahme_max_sek,
            "inaktivitaet_sek": self.inaktivitaet_sek,
            "vad_stille_sek": self.vad_stille_sek,
            "vad_threshold_db": self.vad_threshold_db,
            "vad_long_hold_lock_sek": self.vad_long_hold_lock_sek,
            "aufnahme_min_sek": self.aufnahme_min_sek,
            "anthropic_key_set": bool(self.anthropic_key),
            "azure_key_set": bool(self.azure_key),
            "openai_key_set": bool(self.openai_key),
        }

    def to_vad_cfg(self) -> dict[str, Any]:
        """Minimales VAD-Dict für Template-Render (KIBUDDY-21/AC3)."""
        return {
            "vad_stille_sek": self.vad_stille_sek,
            "vad_threshold_db": self.vad_threshold_db,
            "vad_long_hold_lock_sek": self.vad_long_hold_lock_sek,
            "aufnahme_min_sek": self.aufnahme_min_sek,
        }


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("config-Datei nicht gefunden (%s) — Defaults gelten", path)
        return {}
    except json.JSONDecodeError as e:
        logger.warning("config-Datei nicht parsebar (%s): %s — Defaults bleiben", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _resolve_provider(raw: Any) -> str:
    """Validiert den `llm_provider`-Wert gegen die V1-Whitelist (KIBUDDY-14)."""
    val = (str(raw) if raw is not None else DEFAULT_LLM_PROVIDER).strip().lower()
    if val not in VALID_PROVIDERS:
        raise ConfigError(
            "llm_provider %r ist V1 nicht unterstützt — erlaubt: %s (KIBUDDY-14)"
            % (val, ", ".join(VALID_PROVIDERS))
        )
    return val


def _resolve_stt_provider(raw: Any) -> str:
    """Validiert den `stt_provider`-Wert gegen die Whitelist (KIBUDDY-12/T1410)."""
    val = (str(raw) if raw is not None else DEFAULT_STT_PROVIDER).strip().lower()
    if val not in VALID_STT_PROVIDERS:
        raise ConfigError(
            "stt_provider %r ist V1 nicht unterstützt — erlaubt: %s (KIBUDDY-12/T1410)"
            % (val, ", ".join(VALID_STT_PROVIDERS))
        )
    return val


def _resolve_tts_provider(raw: Any) -> str:
    """Validiert den `tts_provider`-Wert gegen die Whitelist (T1410, LLMP-S6)."""
    val = (str(raw) if raw is not None else DEFAULT_TTS_PROVIDER).strip().lower()
    if val not in VALID_TTS_PROVIDERS:
        raise ConfigError(
            "tts_provider %r ist V1 nicht unterstützt — erlaubt: %s (T1410)"
            % (val, ", ".join(VALID_TTS_PROVIDERS))
        )
    return val


def resolve_runtime(
    config_path: str | None = None,
    env: dict[str, str] | None = None,
) -> RuntimeConfig:
    """Löst die Runtime-Config nach KIBUDDY-21 auf.

    Reihenfolge: Code-Default < Datei < ENV (CONFIG-1/CONFIG-5).
    Secrets kommen ausschließlich aus ENV (CONFIG-3).
    """
    if env is None:
        env = dict(os.environ)
    if config_path is None:
        config_path = env.get(ENV_CONFIG_FILE) or DEFAULT_CONFIG_FILE

    file_cfg = _load_json(config_path)

    listen_host = str(env.get("KIBUDDY_LISTEN_HOST") or file_cfg.get("listen_host") or "127.0.0.1")
    listen_port_raw = env.get("KIBUDDY_LISTEN_PORT") or file_cfg.get("listen_port") or 5054
    try:
        listen_port = int(listen_port_raw)
    except (TypeError, ValueError) as e:
        raise ConfigError("listen_port ist keine Zahl: %r" % listen_port_raw) from e

    log_level = str(env.get("KIBUDDY_LOG_LEVEL") or file_cfg.get("log_level") or "INFO").upper()

    llm_provider = _resolve_provider(env.get("KIBUDDY_LLM_PROVIDER") or file_cfg.get("llm_provider") or DEFAULT_LLM_PROVIDER)
    llm_model = str(env.get("KIBUDDY_LLM_MODEL") or file_cfg.get("llm_model") or DEFAULT_LLM_MODEL).strip()

    stt_provider = _resolve_stt_provider(env.get("KIBUDDY_STT_PROVIDER") or file_cfg.get("stt_provider") or DEFAULT_STT_PROVIDER)
    tts_provider = _resolve_tts_provider(env.get("KIBUDDY_TTS_PROVIDER") or file_cfg.get("tts_provider") or DEFAULT_TTS_PROVIDER)

    litellm_tts_slot = str(env.get("KIBUDDY_LITELLM_TTS_SLOT") or file_cfg.get("litellm_tts_slot") or DEFAULT_LITELLM_TTS_SLOT).strip()
    litellm_stt_slot = str(env.get("KIBUDDY_LITELLM_STT_SLOT") or file_cfg.get("litellm_stt_slot") or DEFAULT_LITELLM_STT_SLOT).strip()
    litellm_tts_model = str(env.get("KIBUDDY_LITELLM_TTS_MODEL") or file_cfg.get("litellm_tts_model") or DEFAULT_LITELLM_TTS_MODEL).strip()
    litellm_stt_model = str(env.get("KIBUDDY_LITELLM_STT_MODEL") or file_cfg.get("litellm_stt_model") or DEFAULT_LITELLM_STT_MODEL).strip()
    litellm_tts_base_model = str(
        env.get("KIBUDDY_LITELLM_TTS_BASE_MODEL")
        or file_cfg.get("litellm_tts_base_model")
        or DEFAULT_LITELLM_TTS_BASE_MODEL
    ).strip()

    tts_voice = str(env.get("KIBUDDY_VOICE") or file_cfg.get("tts_voice") or DEFAULT_TTS_VOICE).strip().lower()
    tts_model = str(env.get("KIBUDDY_TTS_MODEL") or file_cfg.get("tts_model") or DEFAULT_TTS_MODEL).strip()
    try:
        tts_speed = float(env.get("KIBUDDY_SPEED") or file_cfg.get("tts_speed") or DEFAULT_TTS_SPEED)
    except (TypeError, ValueError) as e:
        raise ConfigError("tts_speed ist keine Zahl") from e

    stt_model = str(env.get("KIBUDDY_STT_MODEL") or file_cfg.get("stt_model") or DEFAULT_STT_MODEL).strip()
    stt_sprache = str(env.get("KIBUDDY_STT_SPRACHE") or file_cfg.get("stt_sprache") or DEFAULT_STT_SPRACHE).strip()
    aufnahme_quelle = str(env.get("KIBUDDY_AUFNAHME_QUELLE") or file_cfg.get("aufnahme_quelle") or DEFAULT_AUFNAHME_QUELLE).strip()

    try:
        aufnahme_max_sek = int(env.get("KIBUDDY_AUFNAHME_MAX_SEK") or file_cfg.get("aufnahme_max_sek") or DEFAULT_AUFNAHME_MAX_SEK)
    except (TypeError, ValueError):
        aufnahme_max_sek = DEFAULT_AUFNAHME_MAX_SEK
    try:
        inaktivitaet_sek = int(env.get("KIBUDDY_INAKTIVITAET_SEK") or file_cfg.get("inaktivitaet_sek") or DEFAULT_INAKTIVITAET_SEK)
    except (TypeError, ValueError):
        inaktivitaet_sek = DEFAULT_INAKTIVITAET_SEK
    try:
        prompt_max_bytes = int(env.get("KIBUDDY_PROMPT_MAX_BYTES") or file_cfg.get("prompt_max_bytes") or DEFAULT_PROMPT_MAX_BYTES)
    except (TypeError, ValueError):
        prompt_max_bytes = DEFAULT_PROMPT_MAX_BYTES
    try:
        vad_stille_sek = float(env.get("KIBUDDY_VAD_STILLE_SEK") or file_cfg.get("vad_stille_sek") or DEFAULT_VAD_STILLE_SEK)
    except (TypeError, ValueError):
        vad_stille_sek = DEFAULT_VAD_STILLE_SEK
    try:
        vad_threshold_db = float(env.get("KIBUDDY_VAD_THRESHOLD_DB") or file_cfg.get("vad_threshold_db") or DEFAULT_VAD_THRESHOLD_DB)
    except (TypeError, ValueError):
        vad_threshold_db = DEFAULT_VAD_THRESHOLD_DB
    try:
        vad_long_hold_lock_sek = float(
            env.get("KIBUDDY_VAD_LONG_HOLD_LOCK_SEK")
            or file_cfg.get("vad_long_hold_lock_sek")
            or DEFAULT_VAD_LONG_HOLD_LOCK_SEK
        )
    except (TypeError, ValueError):
        vad_long_hold_lock_sek = DEFAULT_VAD_LONG_HOLD_LOCK_SEK
    try:
        aufnahme_min_sek = float(
            env.get("KIBUDDY_AUFNAHME_MIN_SEK")
            or file_cfg.get("aufnahme_min_sek")
            or DEFAULT_AUFNAHME_MIN_SEK
        )
    except (TypeError, ValueError):
        aufnahme_min_sek = DEFAULT_AUFNAHME_MIN_SEK

    return RuntimeConfig(
        listen_host=listen_host,
        listen_port=listen_port,
        log_level=log_level,
        llm_provider=llm_provider,
        llm_model=llm_model,
        tts_provider=tts_provider,
        tts_voice=tts_voice,
        tts_model=tts_model,
        tts_speed=tts_speed,
        stt_provider=stt_provider,
        stt_model=stt_model,
        stt_sprache=stt_sprache,
        litellm_tts_slot=litellm_tts_slot,
        litellm_stt_slot=litellm_stt_slot,
        litellm_tts_model=litellm_tts_model,
        litellm_stt_model=litellm_stt_model,
        litellm_tts_base_model=litellm_tts_base_model,
        aufnahme_quelle=aufnahme_quelle,
        aufnahme_max_sek=aufnahme_max_sek,
        inaktivitaet_sek=inaktivitaet_sek,
        prompt_max_bytes=prompt_max_bytes,
        vad_stille_sek=vad_stille_sek,
        vad_threshold_db=vad_threshold_db,
        vad_long_hold_lock_sek=vad_long_hold_lock_sek,
        aufnahme_min_sek=aufnahme_min_sek,
        anthropic_key=env.get(ENV_ANTHROPIC_KEY),
        azure_endpoint=env.get(ENV_AZURE_ENDPOINT),
        azure_key=env.get(ENV_AZURE_KEY),
        azure_api_version=env.get(ENV_AZURE_API_VERSION) or DEFAULT_AZURE_API_VERSION,
        openai_key=env.get(ENV_OPENAI_KEY),
    )


def patch_aufnahme_quelle(cfg: RuntimeConfig, neue_quelle: str) -> RuntimeConfig:
    """Setzt aufnahme_quelle (KAQS-Skill, PUT /config KIBUDDY-24).

    V1 akzeptiert nur das Feld `aufnahme-quelle` (KIBUDDY-24).
    Andere Felder werden abgelehnt (HTTP 400 — der Caller übersetzt).
    """
    neue_quelle = neue_quelle.strip().lower()
    return RuntimeConfig(
        listen_host=cfg.listen_host,
        listen_port=cfg.listen_port,
        log_level=cfg.log_level,
        llm_provider=cfg.llm_provider,
        llm_model=cfg.llm_model,
        tts_provider=cfg.tts_provider,
        tts_voice=cfg.tts_voice,
        tts_model=cfg.tts_model,
        tts_speed=cfg.tts_speed,
        stt_provider=cfg.stt_provider,
        stt_model=cfg.stt_model,
        stt_sprache=cfg.stt_sprache,
        litellm_tts_slot=cfg.litellm_tts_slot,
        litellm_stt_slot=cfg.litellm_stt_slot,
        litellm_tts_model=cfg.litellm_tts_model,
        litellm_stt_model=cfg.litellm_stt_model,
        litellm_tts_base_model=cfg.litellm_tts_base_model,
        aufnahme_quelle=neue_quelle,
        aufnahme_max_sek=cfg.aufnahme_max_sek,
        inaktivitaet_sek=cfg.inaktivitaet_sek,
        prompt_max_bytes=cfg.prompt_max_bytes,
        vad_stille_sek=cfg.vad_stille_sek,
        vad_threshold_db=cfg.vad_threshold_db,
        vad_long_hold_lock_sek=cfg.vad_long_hold_lock_sek,
        aufnahme_min_sek=cfg.aufnahme_min_sek,
        anthropic_key=cfg.anthropic_key,
        azure_endpoint=cfg.azure_endpoint,
        azure_key=cfg.azure_key,
        azure_api_version=cfg.azure_api_version,
        openai_key=cfg.openai_key,
    )
