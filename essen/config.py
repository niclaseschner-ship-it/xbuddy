"""Essens-Buddy — Runtime-Konfigurations-Auflösung (ESSEN-21).

Pflegt ausschließlich die Service-Start-Werte (Host, Port, Log-Level).
Die Domänendaten (Wunsch-Liste, Gerichte-Katalog, Lebensmittel-Override) sind
getrennt von der Runtime-Config (BUD-2a) und leben in den ENV-überschreibbaren
Datei-Pfaden.

Auflösung: Datei < ENV < CLI — analog wetter/config.py (CONFIG-1/CONFIG-5).
Fehlende/kaputte Datei → Defaults + Warnung, Prozess startet (CONFIG-4).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# ── Runtime-Schema (CONFIG-1) ──────────────────────────────────────────────
RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5052,  # PORT-2: Essens-Buddy
    "log_level":   "INFO",
}

# ── Datei-Pfad-Defaults (ESSEN-21, CONFIG-5) ──────────────────────────────

# Wunsch-Liste (Daten-State, ESSEN-21) — ENV-Override: ESSEN_WUENSCHE_FILE
DEFAULT_WUENSCHE_FILE    = os.path.join(HERE, "wuensche.json")
ENV_WUENSCHE_FILE        = "ESSEN_WUENSCHE_FILE"

# Gerichte-Katalog (Daten-State, ESSEN-14/21) — ENV-Override: ESSEN_GERICHTE_FILE
DEFAULT_GERICHTE_FILE    = os.path.join(HERE, "gerichte.json")
ENV_GERICHTE_FILE        = "ESSEN_GERICHTE_FILE"

# Per-Instanz-Lebensmittel-Override (ESSEN-13) — ENV-Override: ESSEN_KATALOG_FILE
DEFAULT_KATALOG_FILE     = os.path.join(HERE, "katalog.json")
ENV_KATALOG_FILE         = "ESSEN_KATALOG_FILE"

# Repo-Default des Lebensmittel-Katalogs (ESSEN-12, CONFIG-3-analog) —
# ENV-Override: ESSEN_KATALOG_DEFAULT_FILE
DEFAULT_KATALOG_DEFAULT_FILE = os.path.join(HERE, "katalog.default.json")
ENV_KATALOG_DEFAULT_FILE     = "ESSEN_KATALOG_DEFAULT_FILE"


def _load_file(path):
    """Lädt JSON-Config-Datei. Fehlt sie oder ist kaputt → {} + Warnung (CONFIG-4)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("config.json nicht gefunden (%s) — Defaults gelten", path)
        return {}
    except json.JSONDecodeError as e:
        logger.warning("config.json nicht parsebar (%s): %s — Defaults bleiben", path, e)
        return {}
    if not isinstance(data, dict):
        logger.warning("config.json hat kein Objekt (%s) — Defaults bleiben", path)
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def resolve_runtime(config_path=None, env=None):
    """Löst die Runtime-Konfiguration (Host/Port/Log) nach CONFIG-1/CONFIG-5 auf.

    `config_path` ist der Pfad zur essen/config.json. `env` ist überschreibbar.
    Fehlende Werte → Defaults + Warnung, kein Absturz (CONFIG-4).
    """
    if env is None:
        env = os.environ

    file_cfg = _load_file(config_path) if config_path else {}

    cfg = dict(RUNTIME_SCHEMA)
    for key in RUNTIME_SCHEMA:
        if key in file_cfg:
            cfg[key] = file_cfg[key]
        env_key = "ESSEN_" + key.upper()
        if env_key in env:
            cfg[env_key.lower().replace("essen_", "")] = env[env_key]

    # Explizite ENV-Overrides für Runtime-Keys (CONFIG-5).
    for key in ("listen_host", "listen_port", "log_level"):
        env_key = "ESSEN_" + key.upper()
        if env_key in env:
            cfg[key] = env[env_key]

    try:
        cfg["listen_port"] = int(cfg["listen_port"])
    except (TypeError, ValueError):
        logger.warning("listen_port nicht parsebar (%r) — Default 5052", cfg["listen_port"])
        cfg["listen_port"] = RUNTIME_SCHEMA["listen_port"]

    return cfg


def data_paths(env=None):
    """Liefert die vier Datei-Pfade für Domänendaten (ENV-Overrides, ESSEN-21/CONFIG-5).

    Gibt ein dict mit Schlüsseln:
      wuensche_file, gerichte_file, katalog_file, katalog_default_file
    """
    if env is None:
        env = os.environ
    return {
        "wuensche_file":         env.get(ENV_WUENSCHE_FILE,          DEFAULT_WUENSCHE_FILE),
        "gerichte_file":         env.get(ENV_GERICHTE_FILE,          DEFAULT_GERICHTE_FILE),
        "katalog_file":          env.get(ENV_KATALOG_FILE,           DEFAULT_KATALOG_FILE),
        "katalog_default_file":  env.get(ENV_KATALOG_DEFAULT_FILE,   DEFAULT_KATALOG_DEFAULT_FILE),
    }
