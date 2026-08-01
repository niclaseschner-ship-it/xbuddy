"""Wetter-Regeln-Mini-App-Mantel (#1715, ESB-1.a Zweig A): seiten-gehostet.

Prüft die Ausliefer-Seite (seiten serviert Shell + PWA-Mantel-Assets); die
Datenrouten /api/v1/wetter/regeln (im wetter-Service, AUTH-3) sind separat
(wetter/tests/test_auth_regeln.py).

Lauf: python3 -m pytest seiten/tests/test_wetter_regeln_mantel.py -q
"""

import os
import sys

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import pwa_mantel  # noqa: E402


def _client():
    seiten_main.app.testing = True
    return seiten_main.app.test_client()


def test_shell_html_public_200():
    """MAD-7: die HTML-Shell ist public (JS macht ensureAuth) → 200 + no-store."""
    r = _client().get("/seiten/wetter/regeln")
    assert r.status_code == 200
    assert "Garderoben-Regeln" in r.get_data(as_text=True)
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_trailing_slash_alias_200():
    r = _client().get("/seiten/wetter/regeln/")
    assert r.status_code == 200


def test_manifest_baut_aus_registry():
    """PWAM-2/5: manifest.json aus der REGISTRY (Icons 192/512/maskable valide)."""
    r = _client().get("/seiten/wetter/regeln/manifest.json")
    assert r.status_code == 200
    m = r.get_json()
    assert m["start_url"] == "/seiten/wetter/regeln/"
    assert m["scope"] == "/seiten/wetter/regeln/"
    sizes = {i["sizes"] for i in m["icons"]}
    assert "192x192" in sizes
    assert "512x512" in sizes


def test_sw_js_traegt_scope_header():
    r = _client().get("/seiten/wetter/regeln/sw.js")
    assert r.status_code == 200
    assert r.headers.get("Service-Worker-Allowed") == "/seiten/wetter/regeln/"


def test_css_und_icon_served():
    c = _client()
    assert c.get("/seiten/wetter/regeln/wetter-regeln.css").status_code == 200
    assert c.get("/seiten/wetter/regeln/icon-192.png").status_code == 200


def test_registry_traegt_wetter_regeln():
    assert "wetter-regeln" in pwa_mantel.REGISTRY
    cfg = pwa_mantel.REGISTRY["wetter-regeln"]
    assert cfg.start_url == "/seiten/wetter/regeln/"


def test_asset_traversal_guard():
    """Traversal-Schutz: kein Ausbruch aus dem Asset-Root."""
    r = _client().get("/seiten/wetter/regeln/../pwa_mantel.py")
    assert r.status_code == 404
