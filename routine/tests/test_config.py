"""Tests für routine/config.py — Pfad-Konstanten (SVC-5 / CONFIG-5).

AC3: ENV-Var ROUTINE_STORE_FILE überschreibt den Default-Pfad für
routine_store.json — parallel zu ROUTINE_DATA_FILE für routine.json.

Lauf: pytest routine/tests/ -v
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip


# ============================================================
#  Konstanten — Vollständigkeits-Check (Symmetrie ENV_DATA_FILE / ENV_STORE_FILE)
# ============================================================

def test_AC3_env_store_file_name():
    """ENV_STORE_FILE heißt ROUTINE_STORE_FILE (CONFIG-5 Naming-Konvention)."""
    assert config_mod.ENV_STORE_FILE == "ROUTINE_STORE_FILE"


def test_AC3_env_data_file_name_unchanged():
    """ENV_DATA_FILE bleibt ROUTINE_DATA_FILE — Store-Konstante ersetzt sie nicht."""
    assert config_mod.ENV_DATA_FILE == "ROUTINE_DATA_FILE"


def test_AC3_default_store_file_is_repo_relative():
    """DEFAULT_STORE_FILE liegt neben dem Code (Repo-Pfad als Dev-Default)."""
    assert config_mod.DEFAULT_STORE_FILE.endswith("routine_store.json")
    assert os.path.dirname(config_mod.DEFAULT_STORE_FILE) == os.path.dirname(
        os.path.abspath(config_mod.__file__))


def test_AC3_default_data_file_separate_from_store():
    """DEFAULT_DATA_FILE und DEFAULT_STORE_FILE sind verschiedene Pfade."""
    assert config_mod.DEFAULT_DATA_FILE != config_mod.DEFAULT_STORE_FILE
