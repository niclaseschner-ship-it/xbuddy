"""Tests für GET /api/v1/seiten/uebersicht/kacheln — Auswahl-Seite (#1906).

Nic-Wahl C (25.09.2026): EINE Karte "Kacheln bearbeiten" auf der Übersicht
führt auf eine Auswahl-Seite, die die zur Laufzeit existierenden Panel-
Instanzen listet und je Instanz auf ihren deterministischen Editor
(/controller/app-panel/<id>/bearbeiten) verlinkt. Die Panel-Liste selbst wird
NICHT server-seitig gebaut (keine Familien-Daten im Repo) — das Client-JS holt
sie per fetch('/api/v1/panels/'). Diese Suite prüft nur die Server-Seite: die
Auswahl-Seite selbst rendert, gated wie die Übersicht, verlinkt zurück, und
listet sich in seiten/views.json (Manifest-Eigentest deckt das zusätzlich ab,
seiten/tests/test_views_manifest_eigentest.py).

Lauf: python3 -m pytest seiten/tests/test_kacheln_route.py -v
"""

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402


def _schreibe_manifest(root, app_slug, views):
    d = os.path.join(root, app_slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "views.json"), "w", encoding="utf-8") as f:
        json.dump({"views": views}, f)


def _view(slug, pfad, zielgruppe="kind"):
    return {"slug": slug, "pfad": pfad, "label": "Label-" + slug,
            "synonyme": [slug], "zeigt": "Zeigt-" + slug, "zielgruppe": zielgruppe}


@pytest.fixture
def manifest_root(tmp_path):
    root = str(tmp_path / "repo")
    _schreibe_manifest(root, "wetter", [_view("heute", "/display/wetter/heute")])
    return root


@pytest.fixture
def client(manifest_root, tmp_path):
    inventar_path = str(tmp_path / "inventar.json")
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30,
                          heim_origin="https://heim.test", tailscale_origin="")
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


def test_route_antwortet_200_mit_html(client):
    resp = client.get("/api/v1/seiten/uebersicht/kacheln")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"


def test_html_traegt_zurueck_link_zur_uebersicht(client):
    body = client.get("/api/v1/seiten/uebersicht/kacheln").get_data(as_text=True)
    assert 'href="/api/v1/seiten/uebersicht"' in body


def test_html_holt_panels_clientseitig_ohne_server_proxy(client):
    """Keine Familien-Daten im Repo (RAT-31 E3 bleibt abgerissen): die Seite
    baut die Panel-Liste NICHT server-seitig, sondern das Client-JS fetcht
    sie same-origin."""
    body = client.get("/api/v1/seiten/uebersicht/kacheln").get_data(as_text=True)
    assert "fetch(\"/api/v1/panels/\"" in body
    assert "/controller/app-panel/" in body


def test_html_reuse_den_uebersichts_mantel(client):
    """Kein eigenes Manifest/SW — derselbe Mantel wie die Übersicht (#1906)."""
    body = client.get("/api/v1/seiten/uebersicht/kacheln").get_data(as_text=True)
    assert 'href="/api/v1/seiten/uebersicht/manifest.json"' in body


def test_route_ist_gegated_wie_die_uebersicht(client):
    """require_dual_gate(mode=_AUTH_MODE) wortgleich zur Übersicht (AUTH-11)."""
    from seiten.main import app as flask_app

    kacheln_view = flask_app.view_functions["get_seiten_uebersicht_kacheln"]
    uebersicht_view = flask_app.view_functions["get_seiten_uebersicht"]
    assert hasattr(kacheln_view, "__wrapped__")
    assert type(kacheln_view) is type(uebersicht_view)


def test_manifest_listet_die_kacheln_seite():
    """seiten/views.json trägt den Sorte-b-Eintrag 'kacheln' (SREG-11-Ersatz)."""
    with open(os.path.join(_SEITEN_DIR, "views.json"), encoding="utf-8") as f:
        daten = json.load(f)
    kacheln = next((v for v in daten["views"] if v["slug"] == "kacheln"), None)
    assert kacheln is not None
    assert kacheln["pfad"] == "/api/v1/seiten/uebersicht/kacheln"
    assert kacheln["zielgruppe"] == "eltern"
