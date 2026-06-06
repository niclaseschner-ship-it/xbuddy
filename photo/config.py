"""Photo-Buddy — Daten-/Verhaltens-Konfiguration (PHOTO-19).

Siehe specs/buddies/photo.md §6. Durchlauf-Intervall, Sortier-Achsen,
Auto-Delete-TTL, Video-Maximaldauer und das Library-Verzeichnis sind
**Per-Instanz-Daten**, kein Code (E-PHOTO-8): sie stehen in `photo/photo.json`,
`photo/photo.example.json` dokumentiert das Format.

Auflösung jedes Werts: Umgebungsvariable > Config-Datei > Default — analog
wetter/config.py (WETTER-21) und der CONFIG-1/CONFIG-5-Konvention. Anders als
beim Wetter-Buddy ist hier KEIN Wert Pflicht: eine fehlende `photo.json` ergibt
eine gültige Default-Config (die Library beginnt leer, PHOTO-6).

Die Runtime-Konfig (Bind, Log) liegt separat in `photo/config.json` und wird in
main.py über `tools.configloader` geladen — das ist eine andere Sache
(Service-Start-Knöpfe statt Verhaltens-Daten).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# PHOTO-11: erlaubte Werte der zwei Sortier-Achsen (Richtung × Stempel-Quelle).
RICHTUNG_NEU = "neueste-zuerst"
RICHTUNG_ALT = "aelteste-zuerst"
RICHTUNGEN = (RICHTUNG_NEU, RICHTUNG_ALT)

STEMPEL_HINZUGEFUEGT = "hinzugefuegt"
STEMPEL_AUFGENOMMEN = "aufgenommen"
STEMPEL_QUELLEN = (STEMPEL_HINZUGEFUEGT, STEMPEL_AUFGENOMMEN)

# Eine Familie schreibt die Werte laut Spec (specs/buddies/photo.md:113-116) —
# dort mit Diakritika (`älteste-zuerst`, `hinzugefügt`). Code spiegelt die Spec
# (CLAUDE.md §6): beide Schreibweisen werden akzeptiert und auf die interne
# ASCII-Form kanonisiert.
_RICHTUNG_ALIASES = {
    "neueste-zuerst": RICHTUNG_NEU,
    "älteste-zuerst": RICHTUNG_ALT,
    "aelteste-zuerst": RICHTUNG_ALT,
}
_STEMPEL_ALIASES = {
    "hinzugefügt": STEMPEL_HINZUGEFUEGT,
    "hinzugefuegt": STEMPEL_HINZUGEFUEGT,
    "aufgenommen": STEMPEL_AUFGENOMMEN,
}

# PHOTO-19: nicht-geheime Werte mit ihren Defaults (CONFIG-1: Code-Konstante ist
# nur Fallback-Default, jeder Wert hat einen Override-Pfad). Sortierung und TTL
# sind der Familie-3-Fall (E-PHOTO-8). Auto-Delete ist Default AUS (E-PHOTO-6):
# `auto_delete_tage = 0` bedeutet „keine TTL → nie automatisch löschen".
DEFAULTS = {
    "intervall_s": 8,                      # PHOTO-3/19 — Durchlauf-Intervall
    "sortier_richtung": RICHTUNG_NEU,      # PHOTO-11/19
    "stempel_quelle": STEMPEL_HINZUGEFUEGT,  # PHOTO-11/19
    "auto_delete_tage": 0,                 # PHOTO-12/19 — 0 = AUS (E-PHOTO-6)
    "video_max_s": 60,                     # PHOTO-13/19/OPEN-PHOTO-J
    "library_verzeichnis": "medien",       # PHOTO-7/19 — neben dem Code
}

# PHOTO-19/CONFIG-5: ENV-Overrides nach `PHOTO_<KEY>`-Schema.
ENV_OVERRIDES = {
    "intervall_s": "PHOTO_INTERVALL_S",
    "sortier_richtung": "PHOTO_SORTIER_RICHTUNG",
    "stempel_quelle": "PHOTO_STEMPEL_QUELLE",
    "auto_delete_tage": "PHOTO_AUTO_DELETE_TAGE",
    "video_max_s": "PHOTO_VIDEO_MAX_S",
    "library_verzeichnis": "PHOTO_LIBRARY_VERZEICHNIS",
}

# PHOTO-19: Pfad der Daten-Config-Datei selbst — per Env überschreibbar.
ENV_CONFIG_FILE = "PHOTO_CONFIG_FILE"
DEFAULT_CONFIG_FILE = os.path.join(HERE, "photo.json")


class ConfigError(Exception):
    """Ein Konfigurationswert ist ungültig (PHOTO-19)."""


class Config:
    """Aufgelöste Photo-Buddy-Instanz-Konfiguration (PHOTO-19)."""

    def __init__(self, intervall_s, sortier_richtung, stempel_quelle,
                 auto_delete_tage, video_max_s, library_verzeichnis,
                 config_path=None):
        self.intervall_s = intervall_s                # PHOTO-3
        self.sortier_richtung = sortier_richtung      # PHOTO-11
        self.stempel_quelle = stempel_quelle          # PHOTO-11
        self.auto_delete_tage = auto_delete_tage      # PHOTO-12 (0 = AUS)
        self.video_max_s = video_max_s                # PHOTO-13
        # PHOTO-7: das Library-Verzeichnis liegt neben dem Code (gitignored).
        # Ein relativer Wert wird CWD-unabhängig gegen das Verzeichnis der
        # photo.json (bzw. den Default-Standort) aufgelöst — gleiches Muster
        # wie FAM-9 `resolved_foto_verzeichnis`, damit drei Konsumenten mit
        # drei CWDs dieselbe physische Stelle treffen.
        basis = os.path.dirname(os.path.abspath(config_path)) if config_path else HERE
        if os.path.isabs(library_verzeichnis):
            self.library_verzeichnis = library_verzeichnis
        else:
            self.library_verzeichnis = os.path.join(basis, library_verzeichnis)


def _load_file(path):
    """Lädt die Config-Datei. Fehlt sie, ist das in Ordnung — Defaults gelten
    (CONFIG-4, PHOTO-6: leere Library als Startzustand). Kaputtes JSON → leere
    Config + Warnung (kein Absturz vor dem Kind)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("photo.json nicht gefunden (%s) — Defaults gelten", path)
        return {}
    except json.JSONDecodeError as e:
        logger.warning("photo.json nicht parsebar (%s): %s — Defaults bleiben", path, e)
        return {}
    if not isinstance(data, dict):
        logger.warning("photo.json hat kein Objekt als Inhalt (%s) — Defaults bleiben", path)
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _als_int(roh, feld, minimum=None):
    try:
        wert = int(roh)
    except (TypeError, ValueError) as e:
        raise ConfigError("%r ist keine Ganzzahl: %r" % (feld, roh)) from e
    if minimum is not None and wert < minimum:
        raise ConfigError("%r muss >= %d sein: %r" % (feld, minimum, wert))
    return wert


def resolve(config_path=None, env=None):
    """Löst die Photo-Buddy-Konfiguration nach PHOTO-19 auf.

    `config_path` ist der Pfad der Daten-Config (Default: $PHOTO_CONFIG_FILE
    oder `photo/photo.json`). `env` ist überschreibbar (Tests). Wirft
    ConfigError, wenn ein gesetzter Wert ungültig ist (z. B. unbekannte
    Sortier-Richtung, negative TTL).
    """
    if env is None:
        env = os.environ
    if config_path is None:
        config_path = env.get(ENV_CONFIG_FILE) or DEFAULT_CONFIG_FILE

    file_cfg = _load_file(config_path)

    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in file_cfg:
            values[key] = file_cfg[key]
        env_name = ENV_OVERRIDES[key]
        if env_name in env:
            values[key] = env[env_name]

    intervall_s = _als_int(values["intervall_s"], "intervall_s", minimum=1)
    auto_delete_tage = _als_int(values["auto_delete_tage"], "auto_delete_tage", minimum=0)
    video_max_s = _als_int(values["video_max_s"], "video_max_s", minimum=1)

    richtung = _RICHTUNG_ALIASES.get(str(values["sortier_richtung"]).strip())
    if richtung is None:
        raise ConfigError(
            "sortier_richtung %r unbekannt (erlaubt: %r)"
            % (values["sortier_richtung"], list(_RICHTUNG_ALIASES)))
    stempel = _STEMPEL_ALIASES.get(str(values["stempel_quelle"]).strip())
    if stempel is None:
        raise ConfigError(
            "stempel_quelle %r unbekannt (erlaubt: %r)"
            % (values["stempel_quelle"], list(_STEMPEL_ALIASES)))

    return Config(
        intervall_s=intervall_s,
        sortier_richtung=richtung,
        stempel_quelle=stempel,
        auto_delete_tage=auto_delete_tage,
        video_max_s=video_max_s,
        library_verzeichnis=str(values["library_verzeichnis"]).strip(),
        config_path=config_path,
    )
