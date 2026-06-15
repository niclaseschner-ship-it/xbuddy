"""Gemeinsame Test-Fixtures der Routine-Buddy-Suite (ROUTINE-18).

Die Suite läuft OHNE Netz. Die Uhr wird durch injizierbares `now` ersetzt
(E-ROUTINE-9, ROUTINE-18). Daten kommen aus In-Memory-Config-Dicts.

Auth (MAD-7 / T708-C): client-Fixture setzt Authorization-Header automatisch
(environ_base), damit bestehende API-Tests ohne Änderung weiterhin 200 erhalten.
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
from routine.tests._test_auth import (  # noqa: E402  # isort:skip
    TEST_BOT_TOKEN,
    patch_client_auth,
)


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


def make_authed_client(app=None):
    """Baut einen Flask-Testclient mit MAD-7-Auth im environ_base.

    Kann auch direkt in lokalen Fixtures aufgerufen werden, die
    main_mod.app.test_client() erzeugen (T708-C).
    """
    if app is None:
        app = main_mod.app
    return patch_client_auth(app.test_client())


@pytest.fixture
def client(demo_config, demo_store):
    """Flask-Test-Client mit demo_config, isoliertem Store und MAD-7-Auth (T708-C).

    environ_base setzt den Authorization-Header automatisch, damit bestehende
    API-Tests ohne Änderung weiterhin 200 erhalten.
    """
    main_mod.configure(
        demo_config,
        store_path=demo_store,
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    return patch_client_auth(main_mod.app.test_client())
