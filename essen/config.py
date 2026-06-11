"""Essens-Buddy — sortenspezifische Datei-Pfade (ESSEN-21).

Runtime-Auflösung (Host, Port, Log-Level) läuft jetzt über
`tools.configloader` in `essen/main.py` (CONFIG-1/CONFIG-5).
Hier nur noch die Datei-Pfade für Domänendaten (BUD-2a).
"""

import logging
import os

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# ── Datei-Pfad-Defaults (ESSEN-21, CONFIG-5) ──────────────────────────────

# Wunsch-Liste (Daten-State, ESSEN-21) — ENV-Override: ESSEN_WUENSCHE_FILE
DEFAULT_WUENSCHE_FILE    = os.path.join(HERE, "wuensche.json")
ENV_WUENSCHE_FILE        = "ESSEN_WUENSCHE_FILE"

# Einkaufsliste (Daten-State, V1 #653, ESSEN-7) — ENV-Override: ESSEN_EINKAUFSLISTE_FILE
DEFAULT_EINKAUFSLISTE_FILE = os.path.join(HERE, "einkaufsliste.json")
ENV_EINKAUFSLISTE_FILE     = "ESSEN_EINKAUFSLISTE_FILE"

# Globaler Quellen-Zähler (V1 #653, ESSEN-5/ESSEN-7), klasse-übergreifend.
# ENV-Override: ESSEN_ZAEHLER_FILE
DEFAULT_ZAEHLER_FILE = os.path.join(HERE, "zaehler.json")
ENV_ZAEHLER_FILE     = "ESSEN_ZAEHLER_FILE"

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


def data_paths(env=None):
    """Liefert die Datei-Pfade für Domänendaten (ENV-Overrides, ESSEN-21/CONFIG-5).

    Gibt ein dict mit Schlüsseln:
      wuensche_file, einkaufsliste_file, zaehler_file,
      gerichte_file, katalog_file, katalog_default_file
    """
    if env is None:
        env = os.environ
    return {
        "wuensche_file":         env.get(ENV_WUENSCHE_FILE,          DEFAULT_WUENSCHE_FILE),
        "einkaufsliste_file":    env.get(ENV_EINKAUFSLISTE_FILE,     DEFAULT_EINKAUFSLISTE_FILE),
        "zaehler_file":          env.get(ENV_ZAEHLER_FILE,           DEFAULT_ZAEHLER_FILE),
        "gerichte_file":         env.get(ENV_GERICHTE_FILE,          DEFAULT_GERICHTE_FILE),
        "katalog_file":          env.get(ENV_KATALOG_FILE,           DEFAULT_KATALOG_FILE),
        "katalog_default_file":  env.get(ENV_KATALOG_DEFAULT_FILE,   DEFAULT_KATALOG_DEFAULT_FILE),
    }
