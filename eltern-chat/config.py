"""Konfigurations-Auflösung — siehe specs/platform/eltern-chat.md EC-15 (Refs #27).

Priorität: Umgebungsvariable > Konfigurationsdatei > Default. Geheimnisse
(Bot-Token, Anbieter-API-Key) kommen ausschließlich aus Umgebungsvariablen und
landen nie in einer Datei im Repo (CLAUDE.md §8).
"""

import json
import logging
import os


# EC-15: nicht-geheime Werte mit ihren Defaults.
DEFAULTS = {
    "provider":             "claude",     # KI-Anbieter (EC-11)
    "provider_model":       "",           # leer → Anbieter-Default des Adapters
    "family_group_chat_id": "",           # Pflicht (kein sinnvoller Default)
    "context_depth":        20,           # Gesprächskontext-Tiefe (EC-6)
}

# Umgebungsvariablen-Namen.
ENV_BOT_TOKEN        = "ELTERNCHAT_BOT_TOKEN"          # Geheimnis
ENV_PROVIDER_API_KEY = "ELTERNCHAT_PROVIDER_API_KEY"   # Geheimnis
ENV_OVERRIDES = {
    "provider":             "ELTERNCHAT_PROVIDER",
    "provider_model":       "ELTERNCHAT_PROVIDER_MODEL",
    "family_group_chat_id": "ELTERNCHAT_FAMILY_GROUP_CHAT_ID",
    "context_depth":        "ELTERNCHAT_CONTEXT_DEPTH",
}


class ConfigError(Exception):
    """Eine Pflicht-Konfiguration fehlt oder ist ungültig (EC-15)."""


class Config:
    """Aufgelöste Instanz-Konfiguration."""

    def __init__(self, bot_token, provider_api_key, provider, provider_model,
                 family_group_chat_id, context_depth):
        self.bot_token = bot_token
        self.provider_api_key = provider_api_key
        self.provider = provider
        self.provider_model = provider_model
        self.family_group_chat_id = family_group_chat_id
        self.context_depth = context_depth


def _load_file(path):
    """Lädt die optionale Konfigurationsdatei. Fehlt sie, ist das in Ordnung."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logging.warning("config.json nicht parsebar (%s): %s — Defaults bleiben", path, e)
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def resolve(config_path, env=None):
    """Löst die Konfiguration nach EC-15 auf. `env` ist überschreibbar (Tests).

    Wirft ConfigError, wenn ein Pflicht-Wert fehlt.
    """
    if env is None:
        env = os.environ
    file_cfg = _load_file(config_path)

    # Nicht-geheime Werte: Env > Datei > Default.
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in file_cfg:
            values[key] = file_cfg[key]
        env_name = ENV_OVERRIDES[key]
        if env_name in env:
            values[key] = env[env_name]

    # context_depth muss eine positive Ganzzahl sein.
    try:
        context_depth = int(values["context_depth"])
    except (TypeError, ValueError):
        raise ConfigError("context_depth ist keine Ganzzahl: %r" % values["context_depth"])
    if context_depth < 1:
        raise ConfigError("context_depth muss >= 1 sein, ist %d" % context_depth)

    # Geheimnisse: nur aus Env, Pflicht.
    bot_token = env.get(ENV_BOT_TOKEN, "").strip()
    if not bot_token:
        raise ConfigError("%s ist nicht gesetzt (Pflicht, EC-15)" % ENV_BOT_TOKEN)
    provider_api_key = env.get(ENV_PROVIDER_API_KEY, "").strip()
    if not provider_api_key:
        raise ConfigError("%s ist nicht gesetzt (Pflicht, EC-15)" % ENV_PROVIDER_API_KEY)

    family_group_chat_id = str(values["family_group_chat_id"]).strip()
    if not family_group_chat_id:
        raise ConfigError("family_group_chat_id ist nicht gesetzt (Pflicht, EC-15)")

    return Config(
        bot_token=bot_token,
        provider_api_key=provider_api_key,
        provider=str(values["provider"]).strip(),
        provider_model=str(values["provider_model"]).strip(),
        family_group_chat_id=family_group_chat_id,
        context_depth=context_depth,
    )
