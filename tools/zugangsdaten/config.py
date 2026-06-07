"""Pfad-Auflösung der Zugangsdaten-Speicher-Datei — ZD-8 (Refs #37).

Siehe specs/platform/zugangsdaten.md. Der einzige Konfigurationswert des
Speichers ist die Speicher-Datei: ein fester Default neben dem Code, per
Umgebungsvariable oder CLI überschreibbar (ZD-8).

Priorität: CLI > Umgebungsvariable > Default — analog der Auflösung in
router/main.py (ROU-15). Eine Auflösungs-*Reihenfolge der Werte selbst* erzwingt
der Speicher nicht (ZD-7); diese Datei legt nur fest, *wo* die Datei liegt.

SVC-5 / CONFIG-5: ENV-Var `ZUGANGSDATEN_STORE` überschreibt den Default-Pfad.
Per-Instanz-Daten leben außerhalb des Checkouts (/home/buddy/xbuddy-data/zugangsdaten/).
"""

import argparse
import os

# ZD-8: feste Datei neben dem Code, je Instanz separat, per .gitignore aus dem
# Repo ausgeschlossen.
DEFAULT_STORE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "zugangsdaten.json")

# SVC-5 / CONFIG-5: ENV-Var, die den Default-Pfad überschreibt (ZD-8).
# Naming-Konvention: <KOMP>_<ZWECK>_FILE → ZUGANGSDATEN_STORE.
ENV_STORE_FILE = "ZUGANGSDATEN_STORE"


def resolve_store_path(cli_path=None, env=None):
    """Löst den Pfad der Speicher-Datei nach ZD-8 auf.

    `cli_path` ist der Wert eines CLI-Flags (oder None), `env` ein dict mit
    Umgebungsvariablen (Default: os.environ — für Tests überschreibbar).
    Priorität: CLI > Env > Default.
    """
    if env is None:
        env = os.environ
    if cli_path:
        return str(cli_path)
    if env.get(ENV_STORE_FILE):
        return env[ENV_STORE_FILE]
    return DEFAULT_STORE_FILE


def add_cli_argument(parser):
    """Hängt das `--zugangsdaten-file`-Flag (ZD-8) an einen ArgumentParser.

    So kann jede Komponente, die den Speicher nutzt, denselben CLI-Schalter
    anbieten, ohne den Namen zu duplizieren.
    """
    parser.add_argument(
        "--zugangsdaten-file", dest="zugangsdaten_file", default=None,
        help="Pfad zur Zugangsdaten-Speicher-Datei (ZD-8; sonst $%s oder Default)"
             % ENV_STORE_FILE)
    return parser


def _build_parser():
    p = argparse.ArgumentParser(
        description="Zugangsdaten-Speicher — Pfad-Auflösung (ZD-8)")
    return add_cli_argument(p)
