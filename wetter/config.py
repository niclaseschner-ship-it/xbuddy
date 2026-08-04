"""Wetter-Buddy — Konfigurations-Auflösung (WETTER-21).

Siehe specs/buddies/wetter.md §7. Ort und Garderoben-Regeln sind
**Per-Instanz-Daten**, kein Code (E-WETTER-5): sie stehen in einer
Config-Datei, `wetter/wetter.example.json` dokumentiert das Format.

Auflösung der einzelnen Werte: Umgebungsvariable > Config-Datei > Default —
analog plan/config.py (PLAN-28) und der CONFIG-1/CONFIG-5-Konvention. Der Ort
(`ort`, mit Koordinaten) ist Pflicht und wirft ConfigError, wenn er fehlt.

Die Garderoben-Regeln sind die zentrale Datei-getriebene Struktur (WETTER-14):
eine geordnete Liste von Bedingung→Kleidungs-Set, plus ein Fallback-Set. Diese
Datei parst sie in `clothing.Garderobe`; die Auswertung selbst lebt in
clothing.py (eine Verantwortung je Modul, CLAUDE.md §6).
"""

import json
import logging
import os

from . import clothing

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# WETTER-21: nicht-geheime Werte mit ihren Defaults (CONFIG-1: Code-Konstante
# ist nur Fallback-Default, jeder Wert hat einen Override-Pfad). `ort` hat
# bewusst keinen sinnvollen Default — er ist Pflicht (Familie-3-Probe).
DEFAULTS = {
    "sunscreen_uv": 3,          # WETTER-11/OPEN-WETTER-G — UV-Schwelle für „Ja"
    "zeit_morgens": "08:00",    # WETTER-5
    "zeit_mittags": "12:00",    # WETTER-5
    "rollover_abend": "17:00",  # WETTER-6
    "zeitzone": "Europe/Berlin",
}

# WETTER-21/CONFIG-5: ENV-Overrides nach `WETTER_<KEY>`-Schema.
ENV_OVERRIDES = {
    "sunscreen_uv": "WETTER_SUNSCREEN_UV",
    "zeit_morgens": "WETTER_ZEIT_MORGENS",
    "zeit_mittags": "WETTER_ZEIT_MITTAGS",
    "rollover_abend": "WETTER_ROLLOVER_ABEND",
    "zeitzone": "WETTER_ZEITZONE",
}

# WETTER-21: Pfad der Daten-Config-Datei selbst — per Env überschreibbar.
ENV_CONFIG_FILE = "WETTER_CONFIG_FILE"
DEFAULT_CONFIG_FILE = os.path.join(HERE, "wetter.json")


class ConfigError(Exception):
    """Eine Pflicht-Konfiguration fehlt oder ist ungültig (WETTER-21)."""


class Ort:
    """Der konfigurierte Ort (WETTER-21).

    `lat`/`lon` füttern die Wetter-Anbindung (WETTER-16); `name` ist nur für
    Logs/Diagnose, die View zeigt ihn in V1 nicht.
    """

    def __init__(self, name, lat, lon):
        self.name = name
        self.lat = lat
        self.lon = lon


class Config:
    """Aufgelöste Wetter-Buddy-Instanz-Konfiguration (WETTER-21)."""

    def __init__(self, ort, garderobe, sunscreen_uv, zeit_morgens, zeit_mittags,
                 rollover_abend, zeitzone):
        self.ort = ort                      # Ort — Pflicht (WETTER-21)
        self.garderobe = garderobe          # clothing.Garderobe (WETTER-14)
        self.sunscreen_uv = sunscreen_uv    # WETTER-11
        self.zeit_morgens = zeit_morgens    # (hh, mm) — WETTER-5
        self.zeit_mittags = zeit_mittags    # (hh, mm) — WETTER-5
        self.rollover_abend = rollover_abend  # (hh, mm) — WETTER-6
        self.zeitzone = zeitzone

    @property
    def stunde_morgens(self):
        return self.zeit_morgens[0]

    @property
    def stunde_mittags(self):
        return self.zeit_mittags[0]


def _load_file(path):
    """Lädt die Config-Datei. Fehlt sie, ist das in Ordnung — Defaults gelten
    (CONFIG-4). Kaputtes JSON → leere Config + Warnung (kein Absturz)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("wetter.json nicht gefunden (%s) — Defaults gelten", path)
        return {}
    except json.JSONDecodeError as e:
        logger.warning("wetter.json nicht parsebar (%s): %s — Defaults bleiben", path, e)
        return {}
    if not isinstance(data, dict):
        logger.warning("wetter.json hat kein Objekt als Inhalt (%s) — Defaults bleiben", path)
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _parse_zeit(roh, feld):
    """Parst eine `HH:MM`-Zeit in ein (stunde, minute)-Tupel (WETTER-5/6)."""
    try:
        teile = str(roh).split(":")
        h, m = int(teile[0]), int(teile[1])
    except (ValueError, IndexError):
        raise ConfigError("Zeit-Wert %r für %r ist kein HH:MM" % (roh, feld))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ConfigError("Zeit-Wert %r für %r liegt außerhalb 00:00..23:59" % (roh, feld))
    return (h, m)


def _parse_ort(raw_ort):
    """Baut den Ort aus dem `ort`-Abschnitt (WETTER-21). Pflicht."""
    if not isinstance(raw_ort, dict):
        raise ConfigError(
            "`ort` fehlt oder ist kein Objekt (Pflicht, WETTER-21) — "
            "erwartet { name, lat, lon }")
    for feld in ("lat", "lon"):
        if raw_ort.get(feld) is None:
            raise ConfigError("`ort` ohne Pflichtfeld %r (WETTER-21)" % feld)
    try:
        lat = float(raw_ort["lat"])
        lon = float(raw_ort["lon"])
    except (TypeError, ValueError):
        raise ConfigError("`ort.lat`/`ort.lon` sind keine Zahlen (WETTER-21)")
    return Ort(name=raw_ort.get("name", ""), lat=lat, lon=lon)


def _parse_kleidung(raw_liste, kontext):
    """Baut eine Liste `clothing.Kleidungsstueck` aus Config-Einträgen (WETTER-13).

    Jeder Eintrag ist `{ name, pikto }` — `pikto` ist die ARASAAC-ID (WETTER-18).
    """
    teile = []
    for raw in raw_liste or []:
        if not isinstance(raw, dict) or not raw.get("name") or raw.get("pikto") in (None, ""):
            raise ConfigError(
                "Kleidungsstück in %s braucht `name` und `pikto`: %r" % (kontext, raw))
        teile.append(clothing.Kleidungsstueck(str(raw["name"]), str(raw["pikto"])))
    return teile


def _parse_regel(raw, idx):
    """Baut eine `clothing.Regel` aus einem Config-Eintrag (WETTER-14)."""
    if not isinstance(raw, dict):
        raise ConfigError("Garderoben-Regel %d ist kein Objekt: %r" % (idx, raw))
    cond = raw.get("bedingung") or {}

    def _num(key):
        v = cond.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            raise ConfigError(
                "Garderoben-Regel %d: Bedingung %r ist keine Zahl (%r)" % (idx, key, v))

    return clothing.Regel(
        feels_min=_num("feels_min"),
        feels_max=_num("feels_max"),
        rain_prob_min=_num("rain_prob_min"),
        rain_amount_min=_num("rain_amount_min"),
        wind_min=_num("wind_min"),
        sunscreen=cond.get("sunscreen"),
        pflicht=_parse_kleidung(raw.get("pflicht"), "Regel %d (pflicht)" % idx),
        optional=_parse_kleidung(raw.get("optional"), "Regel %d (optional)" % idx),
        hinweis=str(raw.get("hinweis", "")),
    )


def _parse_garderobe(raw_wardrobe):
    """Baut die `clothing.Garderobe` aus dem `wardrobe`-Abschnitt (WETTER-14).

    Erwartet `{ "regeln": [...], "fallback": { pflicht, optional, hinweis } }`.
    Das Fallback ist Pflicht (WETTER-14: nie leer, nie ein Fehler vor dem Kind).
    """
    raw_wardrobe = raw_wardrobe or {}
    regeln = [_parse_regel(r, i) for i, r in enumerate(raw_wardrobe.get("regeln") or [])]
    raw_fb = raw_wardrobe.get("fallback")
    if not isinstance(raw_fb, dict):
        raise ConfigError(
            "`wardrobe.fallback` fehlt (Pflicht, WETTER-14) — ein Outfit, das "
            "gilt, wenn keine Regel matcht")
    fallback = clothing.Outfit(
        pflicht=_parse_kleidung(raw_fb.get("pflicht"), "fallback (pflicht)"),
        optional=_parse_kleidung(raw_fb.get("optional"), "fallback (optional)"),
        hinweis=str(raw_fb.get("hinweis", "")),
    )
    return clothing.Garderobe(regeln, fallback)


def resolve(config_path=None, env=None):
    """Löst die Wetter-Buddy-Konfiguration nach WETTER-21 auf.

    `config_path` ist der Pfad der Daten-Config (Default: $WETTER_CONFIG_FILE
    oder `wetter/wetter.json`). `env` ist überschreibbar (Tests). Wirft
    ConfigError, wenn der Ort fehlt oder eine Regel-/Fallback-Definition
    ungültig ist.
    """
    if env is None:
        env = os.environ
    if config_path is None:
        config_path = env.get(ENV_CONFIG_FILE) or DEFAULT_CONFIG_FILE

    file_cfg = _load_file(config_path)

    ort = _parse_ort(file_cfg.get("ort"))
    garderobe = _parse_garderobe(file_cfg.get("wardrobe"))

    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in file_cfg:
            values[key] = file_cfg[key]
        env_name = ENV_OVERRIDES[key]
        if env_name in env:
            values[key] = env[env_name]

    try:
        sunscreen_uv = float(values["sunscreen_uv"])
    except (TypeError, ValueError):
        raise ConfigError("sunscreen_uv ist keine Zahl: %r" % values["sunscreen_uv"])

    return Config(
        ort=ort,
        garderobe=garderobe,
        sunscreen_uv=sunscreen_uv,
        zeit_morgens=_parse_zeit(values["zeit_morgens"], "zeit_morgens"),
        zeit_mittags=_parse_zeit(values["zeit_mittags"], "zeit_mittags"),
        rollover_abend=_parse_zeit(values["rollover_abend"], "rollover_abend"),
        zeitzone=str(values["zeitzone"]).strip(),
    )
