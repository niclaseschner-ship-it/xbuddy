"""Tests für GET /api/v1/seiten/kacheln — Auswahl-Seite (#1906, eigener Pfad #1961).

Nic-Wahl C (25.09.2026): EINE Karte "Kacheln bearbeiten" auf der Übersicht
führt auf eine Auswahl-Seite, die die zur Laufzeit existierenden Panel-
Instanzen listet und je Instanz auf ihren deterministischen Editor
(/controller/app-panel/<id>/bearbeiten) verlinkt. Die Panel-Liste selbst wird
NICHT server-seitig gebaut (keine Familien-Daten im Repo) — das Client-JS holt
sie per fetch('/api/v1/panels/'). Diese Suite prüft nur die Server-Seite: die
Auswahl-Seite selbst rendert, gated wie die Übersicht, verlinkt zurück, und
listet sich in seiten/views.json (Manifest-Eigentest deckt das zusätzlich ab,
seiten/tests/test_views_manifest_eigentest.py).

#1961 (Nic, 26.09.2026): eigene installierbare App — eigener Mantel
(pwa_mantel.REGISTRY['kacheln']) unter eigenem Schwester-Pfad
/api/v1/seiten/kacheln; die alte Adresse /api/v1/seiten/uebersicht/kacheln
leitet um.

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
from seiten import pwa_mantel  # noqa: E402

_PFAD = "/api/v1/seiten/kacheln"


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
    resp = client.get(_PFAD)
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"


def test_html_traegt_zurueck_link_zur_uebersicht(client):
    body = client.get(_PFAD).get_data(as_text=True)
    assert 'href="/api/v1/seiten/uebersicht"' in body


def test_html_holt_panels_clientseitig_ohne_server_proxy(client):
    """Keine Familien-Daten im Repo (RAT-31 E3 bleibt abgerissen): die Seite
    baut die Panel-Liste NICHT server-seitig, sondern das Client-JS fetcht
    sie same-origin."""
    body = client.get(_PFAD).get_data(as_text=True)
    assert "fetch(\"/api/v1/panels/\"" in body
    assert "/controller/app-panel/" in body


def test_html_traegt_den_eigenen_mantel(client):
    """#1961: eigenes Manifest, eigene Icons, eigener SW — nicht der der Übersicht."""
    body = client.get(_PFAD).get_data(as_text=True)
    assert 'href="/api/v1/seiten/kacheln/manifest.json"' in body
    assert 'href="/api/v1/seiten/kacheln/icon-192.png"' in body
    assert "/api/v1/seiten/uebersicht/manifest.json" not in body
    assert 'register("/api/v1/seiten/kacheln/sw.js", { scope: "/api/v1/seiten/kacheln" })' in body


def test_mantel_scope_liegt_neben_der_uebersicht_nicht_darin():
    """Zwei Apps, zwei Scopes nebeneinander — keiner ist Präfix des anderen."""
    kacheln = pwa_mantel.REGISTRY["kacheln"]
    uebersicht = pwa_mantel.REGISTRY["uebersicht"]
    assert kacheln.start_url == _PFAD
    assert not kacheln.sw_scope.startswith(uebersicht.sw_scope)
    assert not uebersicht.sw_scope.startswith(kacheln.sw_scope)


def test_manifest_und_sw_des_eigenen_mantels(client):
    m = client.get(_PFAD + "/manifest.json")
    assert m.status_code == 200
    daten = m.get_json()
    assert daten["start_url"] == _PFAD
    assert daten["scope"] == _PFAD
    assert daten["name"] == "Kacheln bearbeiten · XBuddy"
    for icon in daten["icons"]:
        assert client.get(icon["src"]).status_code == 200, icon["src"]
    sw = client.get(_PFAD + "/sw.js")
    assert sw.status_code == 200
    assert sw.headers["Service-Worker-Allowed"] == _PFAD


def test_alte_adresse_leitet_um(client):
    r = client.get("/api/v1/seiten/uebersicht/kacheln")
    assert r.status_code == 302
    assert r.headers["Location"].endswith(_PFAD)


def test_route_ist_gegated_wie_die_uebersicht(client):
    """require_dual_gate(mode=_AUTH_MODE) wortgleich zur Übersicht (AUTH-11)."""
    from seiten.main import app as flask_app

    kacheln_view = flask_app.view_functions["get_seiten_kacheln"]
    uebersicht_view = flask_app.view_functions["get_seiten_uebersicht"]
    assert hasattr(kacheln_view, "__wrapped__")
    assert type(kacheln_view) is type(uebersicht_view)


def test_manifest_listet_die_kacheln_seite():
    """seiten/views.json trägt den Sorte-b-Eintrag 'kacheln' (SREG-11-Ersatz)."""
    with open(os.path.join(_SEITEN_DIR, "views.json"), encoding="utf-8") as f:
        daten = json.load(f)
    kacheln = next((v for v in daten["views"] if v["slug"] == "kacheln"), None)
    assert kacheln is not None
    assert kacheln["pfad"] == _PFAD
    assert kacheln["zielgruppe"] == "eltern"
    # #1961: typ pwa → die Übersicht bietet „Installieren" an (#1955).
    assert kacheln["typ"] == "pwa"
    assert kacheln["pwa"]["start_url"] == _PFAD
