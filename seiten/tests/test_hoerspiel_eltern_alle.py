"""#1953 — generischer Hörspiel-Eltern-Einstieg `/seiten/hoerspiel/alle/eltern`.

Kein Kindername im Repo: „alle" leitet zur Laufzeit auf die erste Instanz der
instanzen.json-Registry (HSP-47). Watchdog-Befund 25.09.2026: der Zweig hatte
keinen Test über den echten Route-Pfad.

Lauf: python3 -m pytest seiten/tests/test_hoerspiel_eltern_alle.py -q
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import pwa_mantel  # noqa: E402
from tools import instanzen as _instanzen_mod  # noqa: E402

_TEST_INSTANZEN = {
    "hoerspiel": [
        {"slug": "kind-a", "port": 5053, "origin": "127.0.0.1:5053",
         "display_name": "Kind A"},
        {"slug": "kind-b", "port": 5055, "origin": "127.0.0.1:5055",
         "display_name": "Kind B"},
    ]
}


@pytest.fixture(autouse=True)
def _instanzen_config(tmp_path, monkeypatch):
    cfg = tmp_path / "instanzen.json"
    cfg.write_text(json.dumps(_TEST_INSTANZEN), encoding="utf-8")
    monkeypatch.setenv(_instanzen_mod.ENV_CONFIG_FILE, str(cfg))


@pytest.fixture
def client():
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


def test_alle_leitet_auf_die_erste_instanz(client):
    resp = client.get("/seiten/hoerspiel/alle/eltern")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/seiten/hoerspiel/kind-a/eltern")


def test_konkreter_slug_wird_nicht_umgeleitet(client):
    resp = client.get("/seiten/hoerspiel/kind-b/eltern")
    assert resp.status_code != 302


def test_fallback_ohne_registry_ist_generisch_statt_kindername(monkeypatch):
    def _leer(_buddy):
        return []
    monkeypatch.setattr(_instanzen_mod, "lade_instanzen", _leer)
    assert pwa_mantel._hoerspiel_primary_slug() == "alle"
