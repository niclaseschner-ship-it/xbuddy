"""Hörspiel-Buddy — Konfigurations-Auflösung (HSP-26/HSP-27).

Zwei Per-Instanz-Dateien neben dem Code (BUD-2/BUD-2a, beide gitignored):
  - `config.json` — Runtime-Config (Bind, Log, Provider, Modelle).
  - `hoerspiel.json` — Daten-Konfig (Default-Voice, Serien-Name).

Geheimnisse (Anthropic-Key, Azure-Key) kommen ausschließlich aus ENV
(CONFIG-3) und sind nie Teil der Datei-Quelle. Der Loader verwaltet sie
zusammen mit den restlichen Werten, damit der Live-Pfad einen Ort hat.

V1: einziger gültiger `llm_provider` ist `claude` (HSP-10). `mistral` etc.
lehnt `resolve_runtime` mit ConfigError ab — dieselbe Klasse, die der
PATCH-Endpoint in HTTP 422 übersetzt.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

ENV_RUNTIME_CONFIG_FILE = "HOERSPIEL_CONFIG_FILE"
DEFAULT_RUNTIME_CONFIG_FILE = os.path.join(HERE, "config.json")

ENV_DATA_CONFIG_FILE = "HOERSPIEL_DATA_CONFIG_FILE"
DEFAULT_DATA_CONFIG_FILE = os.path.join(HERE, "hoerspiel.json")

ENV_DATA_ROOT = "HOERSPIEL_DATA_ROOT"
DEFAULT_DATA_ROOT = os.path.join(HERE, "data")

ENV_ANTHROPIC_KEY = "HOERSPIEL_ANTHROPIC_KEY"
ENV_AZURE_ENDPOINT = "HOERSPIEL_AZURE_OPENAI_ENDPOINT"
ENV_AZURE_DEPLOYMENT = "HOERSPIEL_AZURE_OPENAI_DEPLOYMENT"
ENV_AZURE_KEY = "HOERSPIEL_AZURE_OPENAI_KEY"

VALID_PROVIDERS = ("claude",)
VALID_VOICES = ("shimmer", "onyx")

DEFAULT_LLM_MODEL = "claude-opus-4-7"
DEFAULT_VOICE = "shimmer"
DEFAULT_SERIEN_NAME = "Stigi & Co."


class ConfigError(Exception):
    """Pflicht-Konfiguration fehlt oder ist ungültig (HSP-26/HSP-27)."""


class RuntimeConfig:
    """Runtime-Config-Snapshot (Bind, Log, Provider, Modell + Secrets)."""

    def __init__(self, listen_host: str, listen_port: int, log_level: str,
                 llm_provider: str, llm_model: str,
                 anthropic_key: str | None,
                 azure_endpoint: str | None,
                 azure_deployment: str | None,
                 azure_key: str | None):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.log_level = log_level
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.anthropic_key = anthropic_key
        self.azure_endpoint = azure_endpoint
        self.azure_deployment = azure_deployment
        self.azure_key = azure_key

    def to_public_dict(self) -> dict[str, Any]:
        """Form für `GET /config` (HSP-17). Geheimnisse fliegen raus (LOG-3)."""
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "default_voice": None,
            "serien_name": None,
            "anthropic_key_set": bool(self.anthropic_key),
            "azure_key_set": bool(self.azure_key),
        }


class DataConfig:
    """Daten-Konfig (Default-Voice, Serien-Name) — familien-spezifisch."""

    def __init__(self, default_voice: str, serien_name: str):
        self.default_voice = default_voice
        self.serien_name = serien_name


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
    """Validiert den `llm_provider`-Wert gegen die V1-Whitelist (HSP-10)."""
    val = (str(raw) if raw is not None else DEFAULT_LLM_MODEL.split("-")[0]).strip().lower()
    if val not in VALID_PROVIDERS:
        raise ConfigError(
            "llm_provider %r ist V1 nicht unterstützt — erlaubt: %s (HSP-10)"
            % (val, ", ".join(VALID_PROVIDERS)))
    return val


def resolve_runtime(config_path: str | None = None,
                    env: dict[str, str] | None = None) -> RuntimeConfig:
    """Löst die Runtime-Config nach HSP-26/HSP-27 auf.

    Reihenfolge: Code-Default < Datei < ENV (CONFIG-1/CONFIG-5).
    Secrets kommen ausschließlich aus ENV (CONFIG-3).
    """
    if env is None:
        env = dict(os.environ)
    if config_path is None:
        config_path = env.get(ENV_RUNTIME_CONFIG_FILE) or DEFAULT_RUNTIME_CONFIG_FILE

    file_cfg = _load_json(config_path)

    listen_host = str(env.get("HOERSPIEL_LISTEN_HOST")
                      or file_cfg.get("listen_host") or "127.0.0.1")
    listen_port_raw = env.get("HOERSPIEL_LISTEN_PORT") or file_cfg.get("listen_port") or 5053
    try:
        listen_port = int(listen_port_raw)
    except (TypeError, ValueError) as e:
        raise ConfigError("listen_port ist keine Zahl: %r" % listen_port_raw) from e
    log_level = str(env.get("HOERSPIEL_LOG_LEVEL")
                    or file_cfg.get("log_level") or "INFO").upper()

    llm_provider = _resolve_provider(env.get("HOERSPIEL_LLM_PROVIDER")
                                     or file_cfg.get("llm_provider") or "claude")
    llm_model = str(env.get("HOERSPIEL_LLM_MODEL")
                    or file_cfg.get("llm_model") or DEFAULT_LLM_MODEL).strip()

    return RuntimeConfig(
        listen_host=listen_host,
        listen_port=listen_port,
        log_level=log_level,
        llm_provider=llm_provider,
        llm_model=llm_model,
        anthropic_key=env.get(ENV_ANTHROPIC_KEY),
        azure_endpoint=env.get(ENV_AZURE_ENDPOINT),
        azure_deployment=env.get(ENV_AZURE_DEPLOYMENT),
        azure_key=env.get(ENV_AZURE_KEY),
    )


def resolve_data(config_path: str | None = None,
                 env: dict[str, str] | None = None) -> DataConfig:
    """Löst die Daten-Konfig auf (Default-Voice + Serien-Name, HSP-27)."""
    if env is None:
        env = dict(os.environ)
    if config_path is None:
        config_path = env.get(ENV_DATA_CONFIG_FILE) or DEFAULT_DATA_CONFIG_FILE
    file_cfg = _load_json(config_path)

    default_voice = str(file_cfg.get("default_voice") or DEFAULT_VOICE).strip().lower()
    if default_voice not in VALID_VOICES:
        raise ConfigError(
            "default_voice %r ist V1 nicht unterstützt — erlaubt: %s (HSP-13)"
            % (default_voice, ", ".join(VALID_VOICES)))
    serien_name = str(file_cfg.get("serien_name") or DEFAULT_SERIEN_NAME)

    return DataConfig(default_voice=default_voice, serien_name=serien_name)


def patch_runtime(cfg: RuntimeConfig, patch: dict[str, Any]) -> RuntimeConfig:
    """Applies `PATCH /config`-Body auf einen Runtime-Snapshot (HSP-17).

    Erkennt nur `llm_provider` und `llm_model`. Andere Schlüssel ignoriert.
    Wirft ConfigError bei unbekanntem Provider — `main.py` übersetzt das in
    HTTP 422. Wirft ConfigError, wenn der gewählte Provider keinen
    konfigurierten API-Key hat (HSP-17, „Provider-Switch ohne Key
    wird nie aktiv").
    """
    new_provider = cfg.llm_provider
    new_model = cfg.llm_model
    if "llm_provider" in patch:
        new_provider = _resolve_provider(patch["llm_provider"])
    if "llm_model" in patch and patch["llm_model"] is not None:
        new_model = str(patch["llm_model"]).strip()
    if new_provider == "claude" and not cfg.anthropic_key:
        raise ConfigError(
            "llm_provider=claude verlangt einen Anthropic-Key (HOERSPIEL_ANTHROPIC_KEY) — "
            "Provider-Switch ohne Key wird nicht aktiv (HSP-17)")
    return RuntimeConfig(
        listen_host=cfg.listen_host, listen_port=cfg.listen_port,
        log_level=cfg.log_level,
        llm_provider=new_provider, llm_model=new_model,
        anthropic_key=cfg.anthropic_key,
        azure_endpoint=cfg.azure_endpoint,
        azure_deployment=cfg.azure_deployment,
        azure_key=cfg.azure_key,
    )
