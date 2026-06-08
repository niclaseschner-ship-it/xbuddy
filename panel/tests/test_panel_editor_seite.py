"""Tests für PBE-1/PBE-2: Editor-Seite je Panel-Instanz (T452, #330).

Abgedeckt:
  test_pbe1_editor_route_returns_html             — GET /controller/app-panel/<id>/bearbeiten → 200 + HTML
  test_pbe1_editor_route_embeds_panel_id          — data-panel-id wird in HTML injiziert (analog PANEL-2)
  test_pbe1_editor_route_unknown_panel_returns_404 — 404 bei unbekannter panel_id
  test_pbe1_editor_route_serves_bearbeiten_js     — Bundle-JS wird ausgeliefert
  test_pbe1_editor_route_serves_bearbeiten_css    — Bundle-CSS wird ausgeliefert
  test_pbe1_editor_route_no_auth_layer            — PBE-3: keine zusätzliche Auth-Schicht in der Route
  test_pbe1_html_references_bundle_assets          — HTML lädt bearbeiten.js + bearbeiten.css
  test_pbe1_html_has_safe_area_viewport            — PBE-1 viewport-fit=cover + safe-area-inset-top im CSS

Lauf: python3 -m pytest panel/tests/ -v
"""

import json
import os
import sys

import pytest

_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main  # noqa: E402
from panel import registry as registry_mod  # noqa: E402

_BEARBEITEN_DIR = os.path.normpath(os.path.join(
    _REPO_ROOT, "controller", "app-panel"))


# ============================================================
#  Demo-Daten + Fixtures
# ============================================================

DEMO_PANELS = {
    "panels": [
        {
            "panel_id": "kueche-01",
            "source_id": "app-panel:kueche-01",
            "display_id": "pi-display-flur-01",
            "router_url": "",
            "config": {
                "source_id": "app-panel:kueche-01",
                "display_id": "pi-display-flur-01",
                "router_url": "",
            },
            "tiles": {"tiles": []},
        },
    ]
}


@pytest.fixture(autouse=True)
def stub_externe_dienste(monkeypatch):
    """PREG-12: Geräte-Registry + Router stubben — kein Netz."""
    monkeypatch.setattr(panel_main, "display_existiert",
                        lambda d: True)
    monkeypatch.setattr(panel_main, "router_panels_upsert",
                        lambda s, d: True)


@pytest.fixture
def demo_instanz(tmp_path):
    p = tmp_path / "panels.json"
    p.write_text(json.dumps(DEMO_PANELS), encoding="utf-8")
    return str(p)


@pytest.fixture
def editor_client(demo_instanz):
    """Lese-Modus mit registry_path: GET-Route liefert frisch von Disk."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, registry_path=demo_instanz)
    panel_main.app.testing = True
    return panel_main.app.test_client()


# ============================================================
#  AC1 — Route liefert HTML-Bundle, 404 bei unbekannter panel_id
# ============================================================

def test_pbe1_editor_route_returns_html(editor_client):
    """PBE-1/PBE-2: GET /controller/app-panel/<id>/bearbeiten → 200 + text/html."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten")
    assert r.status_code == 200, r.get_data(as_text=True)
    ct = r.headers.get("Content-Type", "")
    assert "text/html" in ct, "Editor-Seite muss text/html ausliefern (bekommen: %r)" % ct
    body = r.get_data(as_text=True)
    assert "<html" in body.lower()
    assert "<body" in body.lower()


def test_pbe1_editor_route_embeds_panel_id(editor_client):
    """PBE-1: Panel-Identität liegt als data-panel-id am body — analog PANEL-2,
    damit die JS-Schicht ohne weiteren Roundtrip ihre Identität kennt."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'data-panel-id="kueche-01"' in body, \
        "<body> muss data-panel-id='<id>' tragen (bekommen: %r)" % body[:500]


def test_pbe1_editor_route_unknown_panel_returns_404(editor_client):
    """PBE-1: Eine unbekannte panel_id darf keine Editor-Seite bekommen —
    die Seite ist an die `panel_id` gebunden."""
    r = editor_client.get("/controller/app-panel/unbekannt-99/bearbeiten")
    assert r.status_code == 404, r.get_data(as_text=True)


def test_pbe1_editor_route_serves_bearbeiten_js(editor_client):
    """PBE-1: bearbeiten.js wird als application/javascript ausgeliefert."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten.js")
    assert r.status_code == 200, r.get_data(as_text=True)
    ct = r.headers.get("Content-Type", "")
    assert "javascript" in ct, "bearbeiten.js muss als javascript-MIME ausgeliefert werden"
    body = r.get_data(as_text=True)
    # Sanity: das Bundle exportiert editorLib (UMD-Pattern).
    assert "editorLib" in body, "bearbeiten.js muss editorLib exportieren"


def test_pbe1_editor_route_serves_bearbeiten_css(editor_client):
    """PBE-1: bearbeiten.css wird als text/css ausgeliefert."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten.css")
    assert r.status_code == 200, r.get_data(as_text=True)
    ct = r.headers.get("Content-Type", "")
    assert "text/css" in ct, "bearbeiten.css muss als text/css ausgeliefert werden"


def test_pbe1_editor_route_unknown_panel_js_returns_404(editor_client):
    """PBE-1: bearbeiten.js für unbekannte panel_id → 404."""
    r = editor_client.get("/controller/app-panel/unbekannt-99/bearbeiten.js")
    assert r.status_code == 404


# ============================================================
#  AC5 — PBE-3: keine zusätzliche Auth-Schicht in der Route
# ============================================================

def test_pbe1_editor_route_no_auth_layer(editor_client):
    """PBE-3: keine Rollen-/Login-Schicht in V1 — Heimnetz/Tailscale-Grenze
    ist das Gate (RAT-2). Eigentest: ohne Auth-Header bekommt der Client 200."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten")
    # Keine 401/403 — Auth ist nicht route-seitig.
    assert r.status_code == 200, \
        "PBE-3: kein zusätzlicher Auth-Schritt — Heimnetz/Tailscale-Gate ist das Gate"


# ============================================================
#  Statik: HTML referenziert das Bundle + Safe-Area-Inset
# ============================================================

def test_pbe1_html_references_bundle_assets():
    """PBE-1 / AC2: bearbeiten.html lädt bearbeiten.js + bearbeiten.css."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    assert "bearbeiten.js" in html, "HTML muss bearbeiten.js laden"
    assert "bearbeiten.css" in html, "HTML muss bearbeiten.css laden"


def test_pbe1_html_has_safe_area_viewport():
    """PBE-1: viewport-fit=cover muss im <meta name=viewport> stehen,
    damit env(safe-area-inset-top) am iPhone-Notch greift."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    assert "viewport-fit=cover" in html, \
        "PBE-1: viewport-fit=cover muss im <meta name=viewport> stehen"


def test_pbe1_css_uses_safe_area_inset_top():
    """PBE-1: CSS muss safe-area-inset-top für den Editor-Kopf anwenden,
    damit Titel/Aktionen nicht unter dem Notch verschwinden."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.css"),
              encoding="utf-8") as f:
        css = f.read()
    assert "safe-area-inset-top" in css, \
        "PBE-1: CSS muss env(safe-area-inset-top) für den Kopfbereich nutzen"


# ============================================================
#  AC3 — PBE-8: Editor zeigt keine Aus-Kachel als Bearbeitungs-Item
#  (Defense-in-Depth: stripAusKachel im JS — hier nur Anker-Test der HTML)
# ============================================================

def test_pbe1_html_lists_only_real_tiles_no_aus_marker():
    """PBE-8: Die Aus-Kachel ist kein tiles.json-Eintrag; die Editor-HTML
    enthält keinen statischen Aus-Eintrag. (Dynamische Filterung passiert
    im JS, getestet in tests/test_bearbeiten.py.)"""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    # __aus__ darf nicht im HTML stehen — es ist Display-seitig.
    assert "__aus__" not in html, \
        "PBE-8: Editor-HTML darf keinen Aus-Kachel-Marker enthalten"


# ============================================================
#  AC2 — HTML enthält Drag/Reorder + Hide/Remove + Hinzufügen + Speichern/Verwerfen
# ============================================================

def test_pbe1_html_has_save_discard_add_buttons():
    """AC2: alle Editor-Aktions-Buttons sind im HTML deklariert."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    for ident in ("btn-save", "btn-discard", "btn-add", "tile-list"):
        assert ident in html, "AC2: HTML muss '%s' enthalten" % ident


def test_pbe1_html_has_empty_state_hint():
    """PBE-9: leerer Zustand — Hinweis-Text ist im HTML angelegt."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    assert "empty-hint" in html, \
        "PBE-9: HTML muss einen Hinweis-Text-Container für den leeren Zustand haben"
