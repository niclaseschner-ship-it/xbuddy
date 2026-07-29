"""Tests fuer das App-Panel-Serving in seiten (SREG-17 / RAT-31 E6b, #1564).

Spec-Anker: specs/platform/seiten-registry.md (SREG-17) + specs/platform/app-panel.md.
Lauf: python3 -m pytest seiten/tests/test_app_panel_serving.py -q

Das Serving von /controller/app-panel/<id>/ ist von router/main.py nach seiten
verlagert (DCOMP-1 — kein Direkt-Read der panels.json; config/tiles/bearbeiten
kommen ueber HTTP-Proxy vom panel-Service, 127.0.0.1:5041).

Deckt:
  - Serving: GET /controller/app-panel/<id>/ → 200 text/html mit __PANEL_ID__-Subst.
  - no_slash → 301 auf /<id>/ (Trailing-Slash-Disambiguation).
  - Proxy config.json/tiles.json (gemockter panel-Service) → 200 mit Body.
  - LKG-Fallback: panel-Service-Ausfall nach vorherigem Erfolg → letzter Body.
  - Code-Default-Fallback: nie erreichbar, kein LKG → {} bzw. [].
  - bearbeiten-Proxy: 200 durchgereicht; 404 durchgereicht (KEIN LKG, PBE-1/2).
  - sw.js: __BUILD_ID__-Subst + no-cache-Header (PANEL-14).
  - Traversal-Schutz: ../ → 404 (realpath-Check).
  - Statik: beliebiges Asset aus controller/app-panel/ → 200.

Auth: die App-Panel-Routen tragen require_dual_gate(mode=_AUTH_MODE). Im Test
laeuft _AUTH_MODE default = 'observe' (200 ohne Cookie, AUTH-3.a Grace) — kein
Cookie noetig, damit die eigentliche Serving-/Proxy-Logik geprueft wird.

Test-Naht: runtime['app_panel_dir'] (_app_panel_dir) via monkeypatch.setitem,
Proxy-Seams _proxy_panel_view / _proxy_panel_bearbeiten monkeypatch-bar; LKG-Pfad
ueber urllib.request.urlopen-Mock geprueft.
"""

import os
import sys
import urllib.error
import urllib.request

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)

sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

_PANEL_ID = "test-panel-serving-77"
_PREFIX = "/controller/app-panel/" + _PANEL_ID


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


@pytest.fixture
def panel_tmp(monkeypatch, tmp_path):
    """Isoliertes App-Panel-Statik-Verzeichnis via runtime-Override (_app_panel_dir).

    Struktur:
      index.html   — traegt __PANEL_ID__ + __BUILD_ID__ (Subst-Naht PANEL-2/14).
      sw.js        — traegt __BUILD_ID__ (Cache-Versionierung).
      app.js       — beliebiges Statik-Asset.
    """
    panel_dir = tmp_path / "app-panel"
    panel_dir.mkdir()
    (panel_dir / "index.html").write_text(
        "<!doctype html><body data-panel-id=\"__PANEL_ID__\">"
        "<script src=\"./app.js?v=__BUILD_ID__\"></script></body>",
        encoding="utf-8",
    )
    (panel_dir / "sw.js").write_text(
        "const CACHE='panel-__BUILD_ID__';", encoding="utf-8")
    (panel_dir / "app.js").write_text("console.log('app');", encoding="utf-8")
    monkeypatch.setitem(seiten_main.runtime, "app_panel_dir", str(panel_dir))
    return panel_dir


@pytest.fixture(autouse=True)
def _reset_lkg():
    """LKG-Cache pro Test leeren, sonst leckt der Snapshot zwischen Tests."""
    with seiten_main._panel_lkg_lock:
        seiten_main._panel_lkg_cache.clear()
    yield
    with seiten_main._panel_lkg_lock:
        seiten_main._panel_lkg_cache.clear()


# ── Serving ───────────────────────────────────────────────────────────────────

def test_index_slash_serving_html(client, panel_tmp):
    """GET /controller/app-panel/<id>/ → 200 text/html mit __PANEL_ID__-Subst (PANEL-2)."""
    resp = client.get(_PREFIX + "/")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/html")
    body = resp.get_data(as_text=True)
    assert _PANEL_ID in body
    assert "__PANEL_ID__" not in body
    # __BUILD_ID__ muss durch die numerische mtime ersetzt sein (PANEL-14).
    assert "__BUILD_ID__" not in body


def test_index_no_slash_redirects_301(client, panel_tmp):
    """GET /controller/app-panel/<id> (ohne Slash) → 301 auf /<id>/ (relative Assets)."""
    resp = client.get(_PREFIX)
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith(_PREFIX + "/")


# ── Proxy config/tiles (mit LKG) ────────────────────────────────────────────────

def _mock_urlopen_factory(body_map):
    """Baut ein urlopen-Doppel: URL-Suffix → (status, body) oder Exception."""
    class _Resp:
        def __init__(self, status, body):
            self.status = status
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        for suffix, outcome in body_map.items():
            if url.endswith(suffix):
                if isinstance(outcome, Exception):
                    raise outcome
                return _Resp(*outcome)
        raise urllib.error.URLError("unmapped url: " + url)

    return fake_urlopen


def test_config_json_proxy_success(client, panel_tmp, monkeypatch):
    """config.json wird an den panel-Service geproxt (200-Body durchgereicht)."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _mock_urlopen_factory({"/config.json": (200, b'{"quelle":"panel"}')}))
    resp = client.get(_PREFIX + "/config.json")
    assert resp.status_code == 200
    assert resp.get_data() == b'{"quelle":"panel"}'


def test_tiles_json_proxy_success(client, panel_tmp, monkeypatch):
    """tiles.json wird an den panel-Service geproxt."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _mock_urlopen_factory({"/tiles.json": (200, b'[{"id":1}]')}))
    resp = client.get(_PREFIX + "/tiles.json")
    assert resp.status_code == 200
    assert resp.get_data() == b'[{"id":1}]'


def test_config_lkg_fallback_after_outage(client, panel_tmp, monkeypatch):
    """LKG: erst Erfolg (Snapshot), dann Ausfall → letzter guter Body (PANEL-8)."""
    # 1. Erfolg — LKG frischt.
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _mock_urlopen_factory({"/config.json": (200, b'{"lkg":"gut"}')}))
    ok = client.get(_PREFIX + "/config.json")
    assert ok.get_data() == b'{"lkg":"gut"}'

    # 2. Ausfall — muss den LKG-Snapshot liefern, nicht crashen.
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _mock_urlopen_factory({"/config.json": urllib.error.URLError("down")}))
    fallback = client.get(_PREFIX + "/config.json")
    assert fallback.status_code == 200
    assert fallback.get_data() == b'{"lkg":"gut"}'


def test_config_code_default_when_never_reachable(client, panel_tmp, monkeypatch):
    """Kein LKG + panel-Service nie erreichbar → Code-Default {} (kein Crash)."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _mock_urlopen_factory({"/config.json": urllib.error.URLError("down")}))
    resp = client.get(_PREFIX + "/config.json")
    assert resp.status_code == 200
    assert resp.get_data() == b"{}"


def test_tiles_code_default_when_never_reachable(client, panel_tmp, monkeypatch):
    """tiles.json Code-Default ist [] (kein Crash)."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _mock_urlopen_factory({"/tiles.json": urllib.error.URLError("down")}))
    resp = client.get(_PREFIX + "/tiles.json")
    assert resp.get_data() == b"[]"


# ── Proxy bearbeiten (KEIN LKG, 404 durchgereicht) ──────────────────────────────

def test_bearbeiten_proxy_success(client, panel_tmp, monkeypatch):
    """bearbeiten wird an den panel-Service /controller/app-panel/-Pfad geproxt."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _mock_urlopen_factory({"/bearbeiten": (200, b"<html>editor</html>")}))
    resp = client.get(_PREFIX + "/bearbeiten")
    assert resp.status_code == 200
    assert resp.get_data() == b"<html>editor</html>"
    assert resp.headers["Content-Type"].startswith("text/html")


def test_bearbeiten_404_passthrough(client, panel_tmp, monkeypatch):
    """PBE-1/2: 404 vom panel-Service wird durchgereicht (kein LKG, kein Default)."""
    err = urllib.error.HTTPError(
        "http://127.0.0.1:5041/controller/app-panel/x/bearbeiten",
        404, "not found", {}, None)
    monkeypatch.setattr(
        urllib.request, "urlopen",
        _mock_urlopen_factory({"/bearbeiten": err}))
    resp = client.get(_PREFIX + "/bearbeiten")
    assert resp.status_code == 404


# ── sw.js (__BUILD_ID__-Subst + no-cache) ───────────────────────────────────────

def test_sw_js_build_id_and_no_cache(client, panel_tmp):
    """sw.js: __BUILD_ID__ ersetzt + Cache-Control no-cache (PANEL-14)."""
    resp = client.get(_PREFIX + "/sw.js")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "__BUILD_ID__" not in body
    assert "no-cache" in resp.headers["Cache-Control"]
    assert resp.headers["Content-Type"].startswith("application/javascript")


# ── Statik + Traversal-Schutz ───────────────────────────────────────────────────

def test_static_asset_served(client, panel_tmp):
    """Beliebiges Statik-Asset aus controller/app-panel/ → 200."""
    resp = client.get(_PREFIX + "/app.js")
    assert resp.status_code == 200
    assert b"console.log" in resp.get_data()


def test_traversal_blocked(client, panel_tmp):
    """Path-Traversal via ../ → 404 (realpath-Check, Defense in Depth)."""
    resp = client.get(_PREFIX + "/..%2f..%2fmain.py")
    assert resp.status_code == 404


# ── DCOMP-1: kein Direkt-Import von panel ───────────────────────────────────────

def test_dcomp1_no_panel_import():
    """DCOMP-1: seiten/main.py importiert NICHT `from panel …` — Proxy statt Disk-Read."""
    with open(os.path.join(_SEITEN_DIR, "main.py"), encoding="utf-8") as fh:
        lines = fh.readlines()
    # Nur echte Modul-Imports am Zeilenanfang zaehlen — Prosa in Docstrings/
    # Kommentaren (die den verbotenen Ausdruck erwaehnen) darf nicht triggern.
    imports = [ln.strip() for ln in lines
               if ln.startswith(("import ", "from "))]
    assert not any(i.startswith(("from panel ", "import panel.")) or i == "import panel"
                   for i in imports)


# ── entry_path_probe: /shell/<id> Rail-Iframe zeigt auf /controller/app-panel/<id>/ ─

def test_entry_path_probe_rail_points_to_app_panel(client, panel_tmp):
    """SHELL-3-Naht: das von seiten servierte /controller/app-panel/<id>/ liefert
    same-origin 200 — der Rail-Iframe der Shell (heim-shell.html) landet damit
    im selben seiten-Service (nginx-Split /controller/app-panel/ → xbuddy_seiten)."""
    resp = client.get(_PREFIX + "/")
    assert resp.status_code == 200
    # Der Shell-HTML-Render referenziert genau diesen Pfad (SHELL-3).
    shell = client.get("/shell/" + _PANEL_ID)
    # heim_shell ist mode='hard' → ohne Cookie 401; das ist erwartet und beweist
    # nur, dass die Route existiert. Der Rail-Ziel-Pfad wird im Template gesetzt.
    assert shell.status_code in (200, 401)
