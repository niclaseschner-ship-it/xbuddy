"""Tests für routine/main.py — Store-Pfad-Override via ENV (SVC-5 / CONFIG-5 / AC3).

Prüft, dass _store_path() ROUTINE_STORE_FILE aus der Umgebung liest und
damit den Default-Pfad überschreibt — analog ROUTINE_DATA_FILE (ROUTINE-12).

Lauf: pytest routine/tests/ -v
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import main as main_mod      # noqa: E402  # isort:skip


# ============================================================
#  _store_path — Auflösungs-Reihenfolge (AC3)
# ============================================================

def test_AC3_store_path_default_without_env(monkeypatch):
    """Ohne ENV und ohne runtime["store_path"] → DEFAULT_STORE_FILE."""
    monkeypatch.delenv(config_mod.ENV_STORE_FILE, raising=False)
    main_mod.runtime["store_path"] = None
    assert main_mod._store_path() == config_mod.DEFAULT_STORE_FILE


def test_AC3_store_path_env_override(monkeypatch, tmp_path):
    """ROUTINE_STORE_FILE in ENV → überschreibt Default (SVC-5 / CONFIG-5)."""
    override = str(tmp_path / "env_store.json")
    monkeypatch.setenv(config_mod.ENV_STORE_FILE, override)
    main_mod.runtime["store_path"] = None
    assert main_mod._store_path() == override


def test_AC3_store_path_runtime_beats_env(monkeypatch, tmp_path):
    """runtime['store_path'] (Test-Naht) schlägt ENV — höchste Priorität."""
    runtime_val = str(tmp_path / "runtime_store.json")
    env_val = str(tmp_path / "env_store.json")
    monkeypatch.setenv(config_mod.ENV_STORE_FILE, env_val)
    main_mod.runtime["store_path"] = runtime_val
    try:
        assert main_mod._store_path() == runtime_val
    finally:
        main_mod.runtime["store_path"] = None


def test_AC3_store_reads_from_env_path(monkeypatch, tmp_path, demo_config):
    """Abhak-Zustand wird aus dem ENV-Override-Pfad gelesen und geschrieben."""
    store_file = tmp_path / "custom_store.json"
    # Store mit bekanntem Zustand vorbelegen
    store_file.write_text(json.dumps({"2099-01-01": ["fruehstueck"]}))

    monkeypatch.setenv(config_mod.ENV_STORE_FILE, str(store_file))
    main_mod.runtime["store_path"] = None
    main_mod.configure(demo_config)  # data_path=None, store_path=None → ENV greift

    loaded = main_mod._load_store()
    assert "2099-01-01" in loaded
