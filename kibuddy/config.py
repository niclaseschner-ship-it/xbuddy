"""KIBuddy — Konfigurations-Auflösung (KIBUDDY-21).

Per-Instanz-Datei `config.json` unter $KIBUDDY_DATA_ROOT (SVC-5).
Geheimnisse (Anthropic-Key, Azure-Key, OpenAI-Key) kommen ausschließlich aus ENV (CONFIG-3).

V1: einziger gültiger `llm_provider` ist `claude` (KIBUDDY-14).
V1: `stt_provider` ist `openai` (Default) oder `azure_openai` (KIBUDDY-12).
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
VALID_STT_PROVIDERS = ("openai", "azure_openai")
VALID_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")

DEFAULT_LLM_PROVIDER = "claude"
DEFAULT_LLM_MODEL = "claude-haiku-4-5"
DEFAULT_STT_PROVIDER = "openai"
DEFAULT_TTS_VOICE = "onyx"
DEFAULT_TTS_MODEL = "tts-1-hd"
DEFAULT_TTS_SPEED = 0.9
DEFAULT_STT_MODEL = "whisper-1"
DEFAULT_STT_SPRACHE = "de"
DEFAULT_AUFNAHME_QUELLE = "display"
DEFAULT_AUFNAHME_MAX_SEK = 30
DEFAULT_INAKTIVITAET_SEK = 60
DEFAULT_PROMPT_MAX_BYTES = 50000


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
        anthropic_key: str | None,
        azure_endpoint: str | None,
        azure_key: str | None,
        azure_api_version: str,
        openai_key: str | None,
    ):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.log_level = log_level
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.tts_voice = tts_voice
        self.tts_model = tts_model
        self.tts_speed = tts_speed
        self.stt_provider = stt_provider
        self.stt_model = stt_model
        self.stt_sprache = stt_sprache
        self.aufnahme_quelle = aufnahme_quelle
        self.aufnahme_max_sek = aufnahme_max_sek
        self.inaktivitaet_sek = inaktivitaet_sek
        self.prompt_max_bytes = prompt_max_bytes
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
            "tts_voice": self.tts_voice,
            "tts_model": self.tts_model,
            "tts_speed": self.tts_speed,
            "stt_provider": self.stt_provider,
            "stt_model": self.stt_model,
            "stt_sprache": self.stt_sprache,
            "aufnahme_quelle": self.aufnahme_quelle,
            "aufnahme_max_sek": self.aufnahme_max_sek,
            "inaktivitaet_sek": self.inaktivitaet_sek,
            "anthropic_key_set": bool(self.anthropic_key),
            "azure_key_set": bool(self.azure_key),
            "openai_key_set": bool(self.openai_key),
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
    """Validiert den `stt_provider`-Wert gegen die V1-Whitelist (KIBUDDY-12)."""
    val = (str(raw) if raw is not None else DEFAULT_STT_PROVIDER).strip().lower()
    if val not in VALID_STT_PROVIDERS:
        raise ConfigError(
            "stt_provider %r ist V1 nicht unterstützt — erlaubt: %s (KIBUDDY-12)"
            % (val, ", ".join(VALID_STT_PROVIDERS))
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

    return RuntimeConfig(
        listen_host=listen_host,
        listen_port=listen_port,
        log_level=log_level,
        llm_provider=llm_provider,
        llm_model=llm_model,
        tts_voice=tts_voice,
        tts_model=tts_model,
        tts_speed=tts_speed,
        stt_provider=stt_provider,
        stt_model=stt_model,
        stt_sprache=stt_sprache,
        aufnahme_quelle=aufnahme_quelle,
        aufnahme_max_sek=aufnahme_max_sek,
        inaktivitaet_sek=inaktivitaet_sek,
        prompt_max_bytes=prompt_max_bytes,
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
        tts_voice=cfg.tts_voice,
        tts_model=cfg.tts_model,
        tts_speed=cfg.tts_speed,
        stt_provider=cfg.stt_provider,
        stt_model=cfg.stt_model,
        stt_sprache=cfg.stt_sprache,
        aufnahme_quelle=neue_quelle,
        aufnahme_max_sek=cfg.aufnahme_max_sek,
        inaktivitaet_sek=cfg.inaktivitaet_sek,
        prompt_max_bytes=cfg.prompt_max_bytes,
        anthropic_key=cfg.anthropic_key,
        azure_endpoint=cfg.azure_endpoint,
        azure_key=cfg.azure_key,
        azure_api_version=cfg.azure_api_version,
        openai_key=cfg.openai_key,
    )
