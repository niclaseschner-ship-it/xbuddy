"""Tests fuer T1324 / PWAM-3 — sw_scope-Naht plan-einstellungen.

Prüft, dass das ausgelieferte HTML den SW-Scope aus pwa_mantel.REGISTRY['plan']
enthaelt — register-scope ist SSoT aus der Registry, kein hartkodiertes Literal
im Template (PWAM-3 / T1324).

Muster: analog test_connector.py::test_ac3_sw_scope_in_html_aus_registry.

Lauf:
  python3 -m pytest seiten/tests/test_plan_einstellungen.py -q
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import pwa_mantel  # noqa: E402

_HTML_PATH = "/seiten/plan/einstellungen"


@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch):
    """Konfiguriert Test-Modus; stubt Inventar-Holer (kein Netz)."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True


@pytest.fixture
def client():
    return seiten_main.app.test_client()


def test_ac1_sw_scope_in_html_aus_registry(client):
    """T1324 / PWAM-3: gerendertes HTML enthaelt den SW-Scope aus REGISTRY['plan'].

    Kein hartkodiertes Literal im Template — {{ sw_scope }} wird mit dem
    pwa_mantel.REGISTRY['plan'].sw_scope-Wert substituiert.
    """
    body = client.get(_HTML_PATH).get_data(as_text=True)
    # Jinja2-Platzhalter muss ersetzt sein
    assert "{{ sw_scope }}" not in body, (
        "HTML enthaelt noch '{{ sw_scope }}'-Platzhalter — Jinja2-Substitution fehlgeschlagen"
    )
    erwartet_scope = pwa_mantel.REGISTRY["plan"].sw_scope
    assert erwartet_scope in body, (
        f"SW-Scope {erwartet_scope!r} aus REGISTRY fehlt im gerenderten HTML (PWAM-3 / T1324)"
    )
