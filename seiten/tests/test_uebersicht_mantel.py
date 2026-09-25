"""Übersicht als installierbare PWA (#1940, SREG-12 / ESB-1 / PWAM-5).

Die Übersicht `/api/v1/seiten/uebersicht` war die einzige Eltern-Seite ohne
PWA-Mantel. Diese Tests prüfen den Mantel über die Lib (build_manifest /
render_sw), die Asset-Routen und den Head-Block im Template.

Lauf: python3 -m pytest seiten/tests/test_uebersicht_mantel.py -q
"""

import os
import sys

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import pwa_mantel  # noqa: E402

_START = "/api/v1/seiten/uebersicht"
_TEMPLATE = os.path.join(_SEITEN_DIR, "templates", "uebersicht.html")


def _client():
    seiten_main.app.testing = True
    return seiten_main.app.test_client()


def test_registry_traegt_uebersicht_als_vollen_mantel():
    cfg = pwa_mantel.REGISTRY["uebersicht"]
    assert cfg.start_url == _START
    assert cfg.sw_scope == _START
    assert cfg.sw_script_route == _START + "/sw.js"
    # Inhalt ist no-store → HTML immer frisch, offline letzter Stand.
    assert cfg.html_cache_mode == "network-first"
    assert "uebersicht.css" in cfg.build_id_source_set
    assert "uebersicht.html" in cfg.template_source_set


def test_manifest_aus_registry_installierbar():
    """Chrome/Android-Install: Manifest mit start_url/scope + PNG 192/512/maskable."""
    r = _client().get(_START + "/manifest.json")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/manifest+json")
    m = r.get_json()
    assert m["start_url"] == _START
    assert m["scope"] == _START
    assert m["display"] in ("standalone", "fullscreen")
    sizes_any = {i["sizes"] for i in m["icons"] if i["purpose"] == "any"}
    assert {"192x192", "512x512"} <= sizes_any
    assert any(i["purpose"] == "maskable" for i in m["icons"])
    for icon in m["icons"]:
        assert icon["src"].startswith(_START + "/")


def test_jedes_manifest_icon_wird_ausgeliefert():
    c = _client()
    m = c.get(_START + "/manifest.json").get_json()
    for icon in m["icons"]:
        r = c.get(icon["src"])
        assert r.status_code == 200, icon["src"]
        assert r.headers["Content-Type"] == "image/png"


def test_sw_js_network_first_mit_scope_header():
    r = _client().get(_START + "/sw.js")
    assert r.status_code == 200
    # SW liegt unter …/uebersicht/, der Scope ist …/uebersicht (ohne Schrägstrich).
    assert r.headers.get("Service-Worker-Allowed") == _START
    assert "no-store" in r.headers.get("Cache-Control", "")
    body = r.get_data(as_text=True)
    assert "const HTML_CACHE_MODE = 'network-first';" in body
    assert "__BUILD_ID__" not in body


def test_template_head_block():
    """Head wie bei den anderen Mänteln: Manifest, Icon, apple-touch-icon, SW."""
    html = open(_TEMPLATE, encoding="utf-8").read()
    assert '<link rel="manifest" href="/api/v1/seiten/uebersicht/manifest.json">' in html
    assert 'rel="apple-touch-icon" href="/api/v1/seiten/uebersicht/icon-192.png"' in html
    assert "serviceWorker" in html
    assert "/api/v1/seiten/uebersicht/sw.js" in html
    assert "/api/v1/seiten/static/uebersicht.css?v={{ build_id }}" in html


def test_gerenderte_uebersicht_traegt_mantel():
    r = _client().get(_START)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "/api/v1/seiten/uebersicht/manifest.json" in html
    # build_id und SW-Scope sind eingesetzt, kein leerer Platzhalter.
    assert "uebersicht.css?v=" in html and "uebersicht.css?v=\"" not in html
    assert "scope: \"%s\"" % _START in html
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_css_ueber_public_static():
    r = _client().get("/api/v1/seiten/static/uebersicht.css")
    assert r.status_code == 200


def test_asset_traversal_guard():
    r = _client().get(_START + "/../pwa_mantel.py")
    assert r.status_code == 404
    assert _client().get(_START + "/_make_icons.py").status_code == 404
