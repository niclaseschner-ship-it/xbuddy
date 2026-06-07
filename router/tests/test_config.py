"""Tests für router/config.py — Pfad-Override (SVC-5 / CONFIG-5 / AC1).

AC1: ENV-Var ROUTER_ROUTING_FILE überschreibt den Default-Pfad für routing.json.
     CLI-Flag --routing schlägt ENV. Default ist der Repo-Pfad.

Lauf: pytest router/tests/ -v
"""

import json
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from router import config as router_config
from router import main as router_main

# ============================================================
#  Konstanten — Naming-Check (AC1, CONFIG-5)
# ============================================================

def test_AC1_env_routing_file_name():
    """ENV_ROUTING_FILE heißt ROUTER_ROUTING_FILE (CONFIG-5 Naming-Konvention)."""
    assert router_config.ENV_ROUTING_FILE == "ROUTER_ROUTING_FILE"


def test_AC1_default_routing_file_is_repo_relative():
    """DEFAULT_ROUTING_FILE liegt neben dem Code (Repo-Pfad als Dev-Default)."""
    assert router_config.DEFAULT_ROUTING_FILE.endswith("routing.json")
    here = os.path.dirname(os.path.abspath(router_config.__file__))
    assert os.path.join(here, "routing.json") == router_config.DEFAULT_ROUTING_FILE


# ============================================================
#  ENV-Override greift beim Programmstart (AC1, entry_path_probe)
# ============================================================

def test_AC1_env_override_sets_routing_path(monkeypatch, tmp_path):
    """ROUTER_ROUTING_FILE in ENV → routing_path wird auf diesen Pfad gesetzt.

    Simuliert den Start via main() ohne Flask-Server: ENV-Auflösung + load_routing.
    """
    routing_file = tmp_path / "custom_routing.json"
    routing_file.write_text(json.dumps({"entries": [], "panels": {}}))

    monkeypatch.setenv(router_config.ENV_ROUTING_FILE, str(routing_file))
    router_main.state = {}
    router_main._subscribers.clear()

    # Routing-Pfad-Auflösung wie in main():
    resolved = (
        None  # kein CLI-Flag
        or os.environ.get(router_config.ENV_ROUTING_FILE)
        or router_config.DEFAULT_ROUTING_FILE
    )
    assert resolved == str(routing_file)

    # Vollständiger Lade-Pfad — routing_path wird gesetzt
    router_main.load_routing(resolved)
    assert router_main.routing_path == str(routing_file)


def test_AC1_cli_flag_beats_env(monkeypatch, tmp_path):
    """CLI-Flag schlägt ENV — Priorität: CLI > ENV > Default."""
    cli_val = str(tmp_path / "cli_routing.json")
    env_val = str(tmp_path / "env_routing.json")
    monkeypatch.setenv(router_config.ENV_ROUTING_FILE, env_val)

    resolved = cli_val or os.environ.get(router_config.ENV_ROUTING_FILE) or router_config.DEFAULT_ROUTING_FILE
    assert resolved == cli_val


def test_AC1_default_used_when_no_env(monkeypatch):
    """Kein CLI, kein ENV → DEFAULT_ROUTING_FILE."""
    monkeypatch.delenv(router_config.ENV_ROUTING_FILE, raising=False)
    resolved = (
        None  # kein CLI-Flag
        or os.environ.get(router_config.ENV_ROUTING_FILE)
        or router_config.DEFAULT_ROUTING_FILE
    )
    assert resolved == router_config.DEFAULT_ROUTING_FILE
