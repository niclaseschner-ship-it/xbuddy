"""Gemeinsame Test-Fixtures der Wetter-Buddy-Suite (WETTER-24).

Die Suite läuft OHNE Netz: der Open-Meteo-Zugriff wird durch eine kontrollierte
Doppelung (FakeTransport) ersetzt — die Test-Naht aus wetter/meteo.py. Keine
echten HTTP-Aufrufe (WETTER-24, analog plan/tests/conftest.py PLAN-29).
"""

import json
import os
import sys

import pytest

# Repo-Wurzel auf den Importpfad — die Suite importiert `wetter` als Paket.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from wetter import config as config_mod   # noqa: E402
from wetter import meteo as meteo_mod     # noqa: E402


# ============================================================
#  FakeTransport — die kontrollierte Wetter-Doppelung (WETTER-24)
# ============================================================

def _hourly(tag, code, temp, feels, rain_prob, rain_amount, wind, uv):
    """Baut eine Open-Meteo-`hourly`-Rohstruktur mit 24 Stunden, alle gleich.

    So liefert jede Tageszeit (08:00, 12:00) denselben Wert — Tests, die EINEN
    Zustand prüfen wollen, halten ihn so konstant; Tests, die zwei Tageszeiten
    unterscheiden, nutzen `raw_with_two_hours`.
    """
    times = ["%sT%02d:00" % (tag.isoformat(), h) for h in range(24)]
    return {
        "time": times,
        "temperature_2m": [temp] * 24,
        "apparent_temperature": [feels] * 24,
        "precipitation_probability": [rain_prob] * 24,
        "precipitation": [rain_amount] * 24,
        "weathercode": [code] * 24,
        "windspeed_10m": [wind] * 24,
        "uv_index": [uv] * 24,
    }


class FakeTransport:
    """Ersetzt OpenMeteoTransport in Tests — kein Netz (WETTER-24).

    `raw` ist die Rohantwort, die `fetch` liefert. `fail=True` simuliert einen
    Anbieter-Ausfall (WETTER-17). `raw_factory(tag)` erlaubt Datums-abhängige
    Antworten (Rollover-Test WETTER-6).
    """

    def __init__(self, raw=None, fail=False, raw_factory=None):
        self.raw = raw
        self.fail = fail
        self.raw_factory = raw_factory
        self.calls = []

    def fetch(self, tag):
        self.calls.append(tag)
        if self.fail:
            raise meteo_mod.WetterUnavailable("FakeTransport: simulierter Ausfall")
        if self.raw_factory is not None:
            return self.raw_factory(tag)
        return self.raw


@pytest.fixture
def make_transport():
    """Factory: liefert einen FakeTransport mit einem 1-Stundenwert-Tag.

    Aufruf: make_transport(tag, code=0, temp=22, feels=22, rain_prob=10,
    rain_amount=0.0, wind=8, uv=6). low/high werden aus daily abgeleitet.
    """
    def _make(tag, code=0, temp=22.0, feels=22.0, rain_prob=10,
              rain_amount=0.0, wind=8.0, uv=6.0, low=14.0, high=24.0):
        raw = {
            "hourly": _hourly(tag, code, temp, feels, rain_prob, rain_amount, wind, uv),
            "daily": {
                "time": [tag.isoformat()],
                "temperature_2m_min": [low],
                "temperature_2m_max": [high],
            },
        }
        return FakeTransport(raw=raw)
    return _make


# ============================================================
#  Demo-Config (WETTER-21)
# ============================================================

DEMO_CONFIG = {
    "ort": {"name": "Teststadt", "lat": 48.0, "lon": 11.0},
    "sunscreen_uv": 3,
    "zeit_morgens": "08:00",
    "zeit_mittags": "12:00",
    "rollover_abend": "17:00",
    "zeitzone": "Europe/Berlin",
    "wardrobe": {
        "regeln": [
            {
                "bedingung": {"rain_amount_min": 1.0},
                "pflicht": [{"name": "Regenjacke", "pikto": "2588"},
                            {"name": "Gummistiefel", "pikto": "2417"}],
                "optional": [],
                "hinweis": "Es regnet.",
            },
            {
                "bedingung": {"feels_max": 4},
                "pflicht": [{"name": "Winterjacke", "pikto": "2319"},
                            {"name": "Wintermütze", "pikto": "39395"}],
                "optional": [],
                "hinweis": "Kalt — warm anziehen.",
            },
            {
                "bedingung": {"feels_min": 4, "feels_max": 14},
                "pflicht": [{"name": "Jacke", "pikto": "2319"}],
                "optional": [{"name": "Mütze", "pikto": "39395"}],
                "hinweis": "Kühl.",
            },
            {
                "bedingung": {"feels_min": 22, "sunscreen": True},
                "pflicht": [{"name": "T-Shirt", "pikto": "2309"},
                            {"name": "Sonnenmütze", "pikto": "2411"}],
                "optional": [{"name": "Sonnenbrille", "pikto": "3330"}],
                "hinweis": "Warm — Sonnenmütze auf.",
            },
            {
                "bedingung": {"feels_min": 14},
                "pflicht": [{"name": "T-Shirt", "pikto": "2309"}],
                "optional": [],
                "hinweis": "Mild.",
            },
        ],
        "fallback": {
            "pflicht": [{"name": "Jacke", "pikto": "2319"}],
            "optional": [],
            "hinweis": "Bequem anziehen.",
        },
    },
}


@pytest.fixture
def demo_config(tmp_path):
    """Aufgelöste Wetter-Buddy-Config aus DEMO_CONFIG (WETTER-21)."""
    cfg_path = tmp_path / "wetter.json"
    cfg_path.write_text(json.dumps(DEMO_CONFIG))
    return config_mod.resolve(str(cfg_path))
