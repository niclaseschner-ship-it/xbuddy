"""Tests fuer das Shared-Asset-Serving in seiten (ROU-23 + ROU-30, RAT-31 E6f-A, #1582).

Spec-Anker: specs/platform/seiten-registry.md (SREG-17) + specs/platform/urls.md (ROU-23, ROU-30).
Lauf: python3 -m pytest seiten/tests/test_shared_serving.py -q

Deckt:
  - GET /controller/_shared/<asset> → 200 mit richtigem Content-Type (ROU-23).
  - GET /display/_shared/design/<asset> → 200 mit richtigem Content-Type (ROU-30 / DTOK-1/2).
  - Traversal-Schutz fuer beide Pfade: ../ → 404.
  - Auth-Gate: beide Pfade sind UNGATED (kein require_dual_gate), analog Router.
  - entry_path_probe: config.js (controller/_shared) + tokens.css (display/_shared/design) → 200.

Test-Naht: _DEFAULT_CONTROLLER_SHARED_DIR + _DEFAULT_DISPLAY_SHARED_DESIGN_DIR werden
via monkeypatch.setattr auf tmp_path-Verzeichnisse umgebogen.
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)

sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


@pytest.fixture
def controller_shared_tmp(monkeypatch, tmp_path):
    """Isoliertes controller/_shared/-Verzeichnis via _DEFAULT_CONTROLLER_SHARED_DIR-Override."""
    shared_dir = tmp_path / "_shared"
    shared_dir.mkdir()
    (shared_dir / "config.js").write_text(
        "// config.js shared", encoding="utf-8")
    (shared_dir / "extra.css").write_text(
        "/* extra */", encoding="utf-8")
    monkeypatch.setattr(seiten_main, "_DEFAULT_CONTROLLER_SHARED_DIR", str(shared_dir))
    return shared_dir


@pytest.fixture
def display_shared_design_tmp(monkeypatch, tmp_path):
    """Isoliertes display/_shared/design/-Verzeichnis via _DEFAULT_DISPLAY_SHARED_DESIGN_DIR-Override."""
    design_dir = tmp_path / "design"
    design_dir.mkdir()
    (design_dir / "tokens.css").write_text(
        ":root { --color: red; }", encoding="utf-8")
    monkeypatch.setattr(seiten_main, "_DEFAULT_DISPLAY_SHARED_DESIGN_DIR", str(design_dir))
    return design_dir


# ── controller/_shared — ROU-23 ───────────────────────────────────────────────

def test_ROU_23_controller_shared_config_js(client, controller_shared_tmp):
    """entry_path_probe: GET /controller/_shared/config.js → 200 application/javascript (ROU-23)."""
    resp = client.get("/controller/_shared/config.js")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/javascript"), (
        f"Erwarteter Content-Type 'application/javascript', got: {resp.headers['Content-Type']!r}"
    )
    assert b"config.js shared" in resp.get_data()


def test_ROU_23_controller_shared_css_asset(client, controller_shared_tmp):
    """GET /controller/_shared/<css-asset> → 200 text/css (ROU-23, beliebiges Asset)."""
    resp = client.get("/controller/_shared/extra.css")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/css"), (
        f"Erwarteter Content-Type 'text/css', got: {resp.headers['Content-Type']!r}"
    )


def test_ROU_23_controller_shared_not_found(client, controller_shared_tmp):
    """GET /controller/_shared/<nicht-existierende-datei> → 404."""
    resp = client.get("/controller/_shared/does-not-exist.js")
    assert resp.status_code == 404


def test_ROU_23_controller_shared_traversal_blocked(client, controller_shared_tmp):
    """Path-Traversal via ../ → 404 (realpath-Check, Defense in Depth, ROU-23)."""
    resp = client.get("/controller/_shared/..%2f..%2fmain.py")
    assert resp.status_code == 404


def test_ROU_23_controller_shared_ungated(client, controller_shared_tmp):
    """ROU-23: /controller/_shared/ ist UNGATED — kein Cookie noetig (analog Router).

    config.js wird vom Service-Worker precacht, bevor ein Auth-Cookie gesetzt ist.
    Ein Gate wuerde den SW-Precache brechen.
    """
    # Kein Cookie gesetzt — Route muss trotzdem 200 liefern (ungated).
    resp = client.get("/controller/_shared/config.js")
    assert resp.status_code == 200, (
        f"controller/_shared/ ist unerwartet gegated (Status {resp.status_code}). "
        "Der Route darf kein require_dual_gate-Decorator haengen (analog Router ROU-23)."
    )


# ── display/_shared/design — ROU-30 / DTOK-1/2 ────────────────────────────────

def test_ROU_30_display_shared_design_tokens_css(client, display_shared_design_tmp):
    """entry_path_probe: GET /display/_shared/design/tokens.css → 200 text/css (ROU-30)."""
    resp = client.get("/display/_shared/design/tokens.css")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/css"), (
        f"Erwarteter Content-Type 'text/css', got: {resp.headers['Content-Type']!r}"
    )
    assert b"--color" in resp.get_data()


def test_ROU_30_display_shared_design_not_found(client, display_shared_design_tmp):
    """GET /display/_shared/design/<nicht-existierende-datei> → 404."""
    resp = client.get("/display/_shared/design/does-not-exist.css")
    assert resp.status_code == 404


def test_ROU_30_display_shared_design_traversal_blocked(client, display_shared_design_tmp):
    """Path-Traversal via ../ → 404 (realpath-Check, Defense in Depth, ROU-30)."""
    resp = client.get("/display/_shared/design/..%2f..%2fmain.py")
    assert resp.status_code == 404


def test_ROU_30_display_shared_design_ungated(client, display_shared_design_tmp):
    """ROU-30: /display/_shared/design/ ist UNGATED — kein Cookie noetig (analog Router).

    tokens.css wird vom Service-Worker precacht und von JEDEM Buddy-View geladen.
    Ein Gate wuerde den SW-Precache und nicht-authentifizierte Display-Views brechen.
    """
    resp = client.get("/display/_shared/design/tokens.css")
    assert resp.status_code == 200, (
        f"display/_shared/design/ ist unerwartet gegated (Status {resp.status_code}). "
        "Der Route darf kein require_dual_gate-Decorator haengen (analog Router ROU-30)."
    )
