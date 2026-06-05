"""Gemeinsamer Konfig-Loader nach `conventions/config.md` CONFIG-1 (#179).

Ein Loader für alle XBuddy-Komponenten — statt drei eigene `DEFAULTS`-
Tabellen + drei `resolve(...)`-Funktionen + drei `argparse`-Setups
(Router/Plan/Eltern-Chat). Die Form ist die aus CONFIG-1:

- **Datei ist die Wahrheit.** Per-Instanz-JSON-Datei neben dem
  Komponentencode (z. B. `plan/config.json`, gitignored).
- **ENV als Dev-Override.** Konvention `<COMPONENT>_<KEY>`, also z. B.
  `PLAN_LISTEN_PORT` für den Schema-Key `listen_port` der Komponente
  `plan`.
- **Code-Default als Fallback.** Das Schema bringt für jeden Wert
  einen Default mit; was weder File noch ENV setzt, kommt aus dem
  Schema.

CLI-Flags sind **kein** Loader-Thema (CONFIG-1: „CLI-Flags sind
Test-Werkzeug, nicht Konfiguration"). Komponenten dürfen den
Loader-Output nach `load()` noch mit `args.*` überschreiben — das tun
sie in ihrer eigenen `main()`.

Geheimnisse berührt der Loader nicht (CONFIG-3). Wer Tokens/Keys
braucht, regelt das selbst (in derselben Datei oder einer zweiten —
das ist Komponenten-Entscheidung).

## Public API

    from tools import configloader

    cfg = configloader.load(
        component="plan",
        schema={"listen_host": "127.0.0.1", "listen_port": 5020,
                "log_level": "INFO"},
        config_path=None,  # default: <component>/config.json relativ zum CWD
    )

`cfg` ist ein flaches Dict mit denselben Keys wie das Schema und mit
Werten, die nach den Schema-Typen koerciert sind (ENV liefert immer
Strings — der Loader macht aus `"5020"` einen `int`, aus `"true"`
einen `bool`).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)


def load(component, schema, config_path=None):
    """Lädt die Per-Instanz-Konfiguration einer Komponente (CONFIG-1).

    Reihenfolge: Schema-Default < Datei-Wert < ENV-Override.

    Args:
        component: Slug der Komponente (z. B. `"plan"`). Dient als
            Präfix für die ENV-Override-Konvention:
            `<COMPONENT_UPPER>_<KEY_UPPER>`.
        schema: Flaches Dict `{key: default}`. Der Default trägt den
            Zieltyp — ENV-Strings werden auf diesen Typ koerciert.
        config_path: Pfad zur Konfigurations-Datei. `None` = Default
            `<component>/config.json` relativ zum CWD. Existiert die
            Datei nicht, gilt sie als leer (silent fallback auf
            Defaults — CONFIG-1: Werte, die nicht in der Datei stehen,
            fallen auf den Code-Default zurück).

    Returns:
        Flaches Dict mit denselben Keys wie das Schema, Werte vom
        Schema-Typ.
    """
    if config_path is None:
        config_path = os.path.join(component, "config.json")

    cfg = dict(schema)

    file_values = _load_file(config_path)
    for key, value in file_values.items():
        if key not in schema:
            logger.warning(
                "configloader[%s]: unbekannter Schlüssel %r in %s — ignoriert",
                component, key, config_path)
            continue
        cfg[key] = value

    env_prefix = component.upper() + "_"
    for key in schema:
        env_name = env_prefix + key.upper()
        if env_name in os.environ:
            cfg[key] = _coerce(os.environ[env_name], schema[key], key, env_name)

    return cfg


def _load_file(path):
    """Liest die JSON-Datei. Fehlt sie, gilt sie als leer (CONFIG-1)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        # Eine kaputte Datei lassen wir hochreißen: silent darüber
        # hinweggehen würde Konfigurationsfehler verstecken. CONFIG-1
        # erlaubt nur den „Datei fehlt" → Default-Fallback.
        raise ConfigLoaderError(
            "configloader: %s nicht lesbar: %s" % (path, e)) from e
    if not isinstance(data, dict):
        raise ConfigLoaderError(
            "configloader: %s muss ein JSON-Objekt sein, ist %s"
            % (path, type(data).__name__))
    return data


def _coerce(raw, default, key, env_name):
    """Koerciert einen ENV-String auf den Typ des Schema-Defaults.

    Defaults haben Typen — daran orientieren wir uns. Unterstützt:
    `str`, `int`, `float`, `bool`. Andere Typen (Listen, Dicts) lehnen
    wir ab — die kommen aus der Datei, nicht aus ENV.
    """
    target = type(default)
    if target is str:
        return raw
    if target is bool:
        # "1"/"true"/"yes"/"on" → True, "0"/"false"/"no"/"off" → False.
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ConfigLoaderError(
            "configloader: ENV %s=%r ist kein bool (erwartet 1/0/true/false)"
            % (env_name, raw))
    if target is int:
        try:
            return int(raw)
        except ValueError as e:
            raise ConfigLoaderError(
                "configloader: ENV %s=%r ist kein int" % (env_name, raw)) from e
    if target is float:
        try:
            return float(raw)
        except ValueError as e:
            raise ConfigLoaderError(
                "configloader: ENV %s=%r ist kein float"
                % (env_name, raw)) from e
    raise ConfigLoaderError(
        "configloader: ENV-Override für %r (Typ %s) wird nicht unterstützt; "
        "Wert nur aus Datei zulassen" % (key, target.__name__))


class ConfigLoaderError(Exception):
    """Wird geworfen, wenn die Konfigurations-Datei oder ein ENV-Override
    nicht verarbeitet werden kann. Eine fehlende Datei ist KEIN Fehler
    (CONFIG-1)."""
