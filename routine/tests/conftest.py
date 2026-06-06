"""Gemeinsame Test-Fixtures der Routine-Buddy-Suite (ROUTINE-18).

Die Suite läuft OHNE Netz. Die Uhr wird durch injizierbares `now` ersetzt
(E-ROUTINE-9, ROUTINE-18). Daten kommen aus In-Memory-Config-Dicts.
"""

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import main as main_mod  # noqa: E402  # isort:skip


# ============================================================
#  Demo-Daten-Config (ROUTINE-12)
# ============================================================

DEMO_ROUTINE = {
    "abfahrtszeit": "07:45",
    "anzieh_vorlauf_min": 8,
    "zeitzone": "Europe/Berlin",
    "items": [
        {"id": "fruehstueck",  "label": "Frühstück",    "piktogramm": "4626",  "quelle": "default"},
        {"id": "zaehne",       "label": "Zähne putzen", "piktogramm": "2326",  "quelle": "default"},
        {"id": "brotdose",     "label": "Brotdose",     "piktogramm": "31091", "quelle": "default"},
        {"id": "rucksack",     "label": "Rucksack",     "piktogramm": "2475",  "quelle": "default"},
    ],
    "zeit_referenzen": {
        "an": True,
        "paare": [
            {"piktogramm": "9802", "dauer_min": 30},
            {"piktogramm": "2694", "dauer_min": 3},
        ],
    },
}


@pytest.fixture
def demo_config(tmp_path):
    """Aufgelöste RoutineConfig aus DEMO_ROUTINE."""
    p = tmp_path / "routine.json"
    p.write_text(json.dumps(DEMO_ROUTINE))
    return config_mod.resolve_data(str(p))


@pytest.fixture
def demo_store(tmp_path):
    """Pfad zu einem leeren Abhak-Store in tmp_path."""
    return str(tmp_path / "routine_store.json")


@pytest.fixture
def client(demo_config, demo_store):
    """Flask-Test-Client mit demo_config und isoliertem Store."""
    main_mod.configure(demo_config, store_path=demo_store)
    return main_mod.app.test_client()
