"""Tests für die geteilte SVC-6-Diagnose-Naht (tools/service_diagnostics.py).

Deckt die EINE `/version`-Definition parametrisiert über alle 11 HTTP-Services
ab (AC2, löst PW-12-klein): Router + 10 Buddy-Services registrieren dieselbe
Naht, das Verhalten ist identisch (file-based, kein `git rev-parse`).

Lauf: python3 -m pytest tools/tests/test_service_diagnostics.py -v
"""

import importlib
import os
import sys

import pytest
from flask import Flask

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools import service_diagnostics  # noqa: E402

# ── Naht direkt (file-based, kein git rev-parse — SVC-6) ────────────────────

def test_deploy_version_liest_datei(monkeypatch, tmp_path):
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "version").write_text("feeddead1234\n")
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    assert service_diagnostics._deploy_version() == "feeddead1234"


def test_deploy_version_null_ohne_datei(monkeypatch, tmp_path):
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    assert service_diagnostics._deploy_version() is None


def test_deploy_version_ist_file_based_nicht_git(monkeypatch, tmp_path):
    """SVC-6: Fantasie-SHA in der Datei kommt 1:1 zurück — kein git rev-parse."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "version").write_text("nicht-ein-echter-git-sha\n")
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    assert service_diagnostics._deploy_version() == "nicht-ein-echter-git-sha"


def test_register_version_auf_frischer_app(monkeypatch, tmp_path):
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "version").write_text("abc123\n")
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    app = Flask(__name__)
    service_diagnostics.register_version(app)
    app.testing = True
    resp = app.test_client().get("/version")
    assert resp.status_code == 200
    assert resp.get_json() == {"version": "abc123"}


# ── parametrisiert über alle 11 Services (AC2) ─────────────────────────────

# (Import-Pfad, App-Attribut) je Service. Die Buddy-Services teilen
# dieselbe Naht — genau die Duplikat-Menge, die T1311 eingeschmolzen hat.
# (Router mit RAT-31/#1568 abgerissen.)
_SERVICE_MODULES = [
    "familie.main",
    "plan.main",
    "wetter.main",
    "panel.main",
    "seiten.main",
    "routine.main",
    "photo.main",
    "essen.main",
    "hoerspiel.main",
    "kibuddy.main",
]


@pytest.mark.parametrize("modpath", _SERVICE_MODULES)
def test_version_endpoint_je_service(modpath, monkeypatch, tmp_path):
    """AC2: /version liefert in JEDEM Service die SHA aus der Datei (200)."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "version").write_text("cafef00d99\n")
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    mod = importlib.import_module(modpath)
    mod.app.testing = True
    resp = mod.app.test_client().get("/version")
    assert resp.status_code == 200, f"{modpath} /version != 200"
    assert resp.get_json() == {"version": "cafef00d99"}, modpath


@pytest.mark.parametrize("modpath", _SERVICE_MODULES)
def test_version_null_je_service(modpath, monkeypatch, tmp_path):
    """AC2: fehlende deploy/version → {"version": null} in jedem Service."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    mod = importlib.import_module(modpath)
    mod.app.testing = True
    resp = mod.app.test_client().get("/version")
    assert resp.status_code == 200
    assert resp.get_json() == {"version": None}, modpath
