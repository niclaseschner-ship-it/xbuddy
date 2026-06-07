"""Tests für tools/zugangsdaten/config.py — Pfad-Override (SVC-5 / CONFIG-5 / ZD-8).

AC2: ENV-Var ZUGANGSDATEN_STORE_FILE überschreibt Default-Pfad; 0600-Permissions
     beim Erstellen einer neuen Datei bleiben erhalten (CONFIG-3 / ZD-3).

Lauf: pytest tools/zugangsdaten/tests/ -v
"""

import os
import sys

# Repo-Wurzel auf den Importpfad, damit `tools.zugangsdaten` gefunden wird.
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))))

from tools.zugangsdaten.config import (
    DEFAULT_STORE_FILE,
    ENV_STORE_FILE,
    resolve_store_path,
)
from tools.zugangsdaten.store import Zugangsdaten, is_owner_only

# ============================================================
#  resolve_store_path — Pfad-Auflösung (AC2, SVC-5 / CONFIG-5)
# ============================================================

def test_AC2_default_path_is_repo_relative():
    """Kein CLI, kein ENV → Default-Pfad (Repo-Pfad neben dem Code)."""
    path = resolve_store_path(cli_path=None, env={})
    assert path == DEFAULT_STORE_FILE


def test_AC2_env_override_replaces_default(tmp_path):
    """ZUGANGSDATEN_STORE_FILE in ENV → überschreibt Default (SVC-5 / CONFIG-5)."""
    override = str(tmp_path / "mein_store.json")
    path = resolve_store_path(cli_path=None, env={ENV_STORE_FILE: override})
    assert path == override


def test_AC2_cli_flag_beats_env(tmp_path):
    """CLI-Flag schlägt ENV (Priorität: CLI > ENV > Default)."""
    cli_val = str(tmp_path / "cli_store.json")
    env_val = str(tmp_path / "env_store.json")
    path = resolve_store_path(cli_path=cli_val, env={ENV_STORE_FILE: env_val})
    assert path == cli_val


def test_AC2_env_var_name_is_ZUGANGSDATEN_STORE_FILE():
    """ENV-Var heißt ZUGANGSDATEN_STORE_FILE (CONFIG-5 Naming-Konvention, _FILE-Suffix)."""
    assert ENV_STORE_FILE == "ZUGANGSDATEN_STORE_FILE"


# ============================================================
#  0600-Permissions beim Anlegen (CONFIG-3 / ZD-3)
# ============================================================

def test_AC2_permission_0600_on_new_file(tmp_path):
    """Neue Datei wird mit Rechten 0600 angelegt (CONFIG-3 / ZD-3)."""
    store_path = str(tmp_path / "store.json")
    speicher = Zugangsdaten(store_path)
    speicher.set("test-key", "test-value")
    assert is_owner_only(store_path), (
        "Zugangsdaten-Datei muss 0600-Rechte haben (CONFIG-3 / ZD-3)")


def test_AC2_permission_0600_after_env_override(tmp_path):
    """Auch bei ENV-Override-Pfad wird die Datei mit 0600 angelegt."""
    override_path = str(tmp_path / "override_store.json")
    resolved = resolve_store_path(
        cli_path=None, env={ENV_STORE_FILE: override_path})
    speicher = Zugangsdaten(resolved)
    speicher.set("ein-key", "ein-wert")
    assert is_owner_only(resolved), (
        "Override-Pfad-Datei muss 0600-Rechte haben (CONFIG-3 / ZD-3)")
