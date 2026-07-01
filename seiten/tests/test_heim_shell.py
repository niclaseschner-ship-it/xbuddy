"""Tests fuer Heim-Shell (SHELL-1..10) — GET /shell/<panel_id>.

Test-Anker: shell1/2/3/5/9/10 (specs/platform/heim-shell.md, Refs #1182).
Lauf: python3 -m pytest seiten/tests/test_heim_shell.py -q

Teststruktur:
  test_shell1_route_html           — SHELL-1: Route liefert 200 + text/html
  test_shell2_lookup_display_id    — SHELL-2: display_id per Router-Lookup (nicht Reverse-Inferenz)
  test_shell2_lookup_real_url      — SHELL-2: _lookup_display_id baut korrekte ROU-32-URL
  test_shell3_zwei_iframes_src     — SHELL-3: zwei Iframes (Panel-Nav + Buddy-View) mit korrekten srcs
  test_shell3_kein_iframe_ohne_display — SHELL-3: Fehler-Meldung + kein Display-Iframe bei None
  test_shell5_kein_displib_import  — SHELL-5: kein displib-Import in Shell-HTML
  test_shell9_keine_hardcode_ids   — SHELL-9: keine Pilot-IDs im Template/Route-Code
  test_shell10_url_in_uebersicht   — SHELL-10: Shell-URL in GET /api/v1/seiten/uebersicht
"""

import json
import os
import sys
import urllib.request

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

# Pilot-IDs — nur in Tests, nie im Produktiv-Code (SHELL-9).
PANEL_ID = "paulas-panel-01"
DISPLAY_ID = "tablet-tablet-paula-01"


# ============================================================
#  Shared Fixture
# ============================================================

@pytest.fixture
def client(monkeypatch):
    """Testclient mit gemocktem display_id-Lookup (SHELL-2) und Origin-Config."""
    monkeypatch.setattr(
        seiten_main, "_lookup_display_id",
        lambda pid: DISPLAY_ID if pid == PANEL_ID else None,
    )
    seiten_main.configure(heim_origin="http://heim.test", tailscale_origin="https://tail.test")
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


# ============================================================
#  test_shell1_route_html — SHELL-1
# ============================================================

def test_shell1_route_html(client):
    """SHELL-1: GET /shell/<panel_id> liefert HTTP 200 + text/html."""
    resp = client.get("/shell/" + PANEL_ID)
    assert resp.status_code == 200, "Route muss 200 liefern"
    assert "text/html" in resp.mimetype, "Antwort muss text/html sein"


def test_shell1_route_html_enthaelt_panel_id(client):
    """SHELL-1: HTML enthaelt panel_id (im Iframe-Src oder Titel)."""
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)
    assert PANEL_ID in body


# ============================================================
#  test_shell2_lookup_display_id — SHELL-2
# ============================================================

def test_shell2_lookup_display_id(monkeypatch):
    """SHELL-2: _lookup_display_id wird mit panel_id aufgerufen; Ergebnis im HTML."""
    calls = []

    def fake_lookup(pid):
        calls.append(pid)
        return DISPLAY_ID

    monkeypatch.setattr(seiten_main, "_lookup_display_id", fake_lookup)
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    resp = c.get("/shell/" + PANEL_ID)
    assert resp.status_code == 200
    assert calls == [PANEL_ID], "Lookup muss genau einmal mit panel_id aufgerufen werden"
    body = resp.get_data(as_text=True)
    # display_id aus Lookup muss im rechten Iframe-Src erscheinen
    assert "/display/" + DISPLAY_ID + "/" in body


def test_shell2_lookup_real_url(monkeypatch):
    """SHELL-2: _lookup_display_id baut korrekte ROU-32-URL (app-panel:<panel_id>)."""
    fetched = []

    class _FakeResp:
        status = 200
        def read(self):
            return json.dumps({"display_id": DISPLAY_ID}).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def fake_urlopen(url, timeout=None):
        fetched.append(url)
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    seiten_main.configure(router_url="http://router.test:5000")
    result = seiten_main._lookup_display_id(PANEL_ID)
    assert result == DISPLAY_ID, "Lookup muss display_id aus JSON-Antwort zurueckgeben"
    assert len(fetched) == 1, "Genau ein HTTP-Aufruf erwartet"
    assert "app-panel:" + PANEL_ID in fetched[0], "URL muss source_id app-panel:<panel_id> enthalten"
    assert "router.test:5000" in fetched[0], "URL muss router_url-Origin enthalten"


def test_shell2_lookup_gibt_none_bei_404(monkeypatch):
    """SHELL-2: _lookup_display_id liefert None bei 404 (unbekanntes Panel)."""
    class _NotFound:
        status = 404
        def read(self):
            return b'{"error": "unknown source_id"}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: _NotFound())
    result = seiten_main._lookup_display_id("gibts-nicht")
    assert result is None


# ============================================================
#  test_shell3_zwei_iframes_src — SHELL-3
# ============================================================

def test_shell3_zwei_iframes_src(client):
    """SHELL-3: HTML enthaelt genau zwei Iframes (Panel-Nav + Buddy-View) mit korrekten srcs."""
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)
    assert "/controller/app-panel/" + PANEL_ID + "/" in body, "Linker Panel-Iframe-Src fehlt"
    assert "/display/" + DISPLAY_ID + "/" in body, "Rechter Display-Iframe-Src fehlt"
    assert body.count("<iframe") == 2, "Genau zwei Iframes erwartet"


def test_shell3_kein_iframe_ohne_display(monkeypatch):
    """SHELL-3: Kein Display-Iframe wenn Lookup None liefert — sichtbarer Fehler."""
    monkeypatch.setattr(seiten_main, "_lookup_display_id", lambda pid: None)
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    body = c.get("/shell/" + PANEL_ID).get_data(as_text=True)
    # Linker Panel-Iframe bleibt
    assert "/controller/app-panel/" + PANEL_ID + "/" in body
    # Kein rechter Display-Iframe
    assert "/display/" not in body
    # Sichtbarer Fehler vorhanden (kein stiller Fallback)
    assert "nicht bekannt" in body or "zugeordnet" in body or "fehler" in body.lower()


def test_shell3_rail_css_enthaelt_280px(client):
    """SHELL-3: heim-shell.css definiert Rail-Breite 280px (Gate-B)."""
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "heim-shell.css",
    )
    with open(css_path, encoding="utf-8") as fh:
        css = fh.read()
    assert "280px" in css, "Rail-Breite 280px muss in heim-shell.css definiert sein"


# ============================================================
#  test_shell5_kein_displib_import — SHELL-5
# ============================================================

def test_shell5_kein_displib_import(client):
    """SHELL-5: Shell-HTML enthaelt keinen displib-Import (keine Display-Client-Codekopie)."""
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)
    assert "displib" not in body, "displib darf NICHT in Shell-HTML erscheinen (SHELL-5)"
    assert "displib.js" not in body


# ============================================================
#  test_shell9_keine_hardcode_ids — SHELL-9
# ============================================================

def test_shell9_keine_hardcode_ids():
    """SHELL-9: Template und Route-Handler enthalten keine hartkodierten Pilot-IDs."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Template pruefen
    template_path = os.path.join(base, "templates", "heim-shell.html")
    with open(template_path, encoding="utf-8") as fh:
        tmpl = fh.read()
    assert "paulas-panel-01" not in tmpl, "Pilot-Panel-ID nicht im Template"
    assert "tablet-tablet-paula-01" not in tmpl, "Pilot-Display-ID nicht im Template"

    # CSS pruefen
    css_path = os.path.join(base, "static", "heim-shell.css")
    with open(css_path, encoding="utf-8") as fh:
        css = fh.read()
    assert "paulas-panel-01" not in css
    assert "tablet-tablet-paula-01" not in css

    # Manifest-Route pruefen: liefert panel_id aus URL, kein Hardcode
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    manifest_resp = c.get("/shell/test-panel-99/manifest.json")
    assert manifest_resp.status_code == 200
    data = json.loads(manifest_resp.get_data(as_text=True))
    assert "test-panel-99" in data["start_url"], "start_url muss panel_id aus URL enthalten"
    assert "paulas-panel-01" not in data["start_url"], "Kein Hardcode in start_url"


# ============================================================
#  test_shell10_url_in_uebersicht — SHELL-10
# ============================================================

def test_shell10_url_in_uebersicht(monkeypatch, tmp_path):
    """SHELL-10: Shell-URL /shell/<panel_id> erscheint in GET /api/v1/seiten/uebersicht."""
    inventar_path = str(tmp_path / "inventar.json")
    # Snapshot: ein Display gesteuert von einem Panel (Hero-Paar)
    monkeypatch.setattr(seiten_main, "hole_panels",
                        lambda: [{"panel_id": PANEL_ID, "display_id": DISPLAY_ID}])
    monkeypatch.setattr(seiten_main, "hole_geraete",
                        lambda: [{"id": DISPLAY_ID, "verwendung": "display",
                                  "status": "aktiv"}])
    seiten_main.configure(
        root=str(tmp_path),
        inventar_path=inventar_path,
        ttl=30,
        heim_origin="http://heim.test",
        tailscale_origin="https://tail.test",
    )
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    body = c.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    # SHELL-10: Shell-URL muss im HTML der Uebersicht erscheinen
    assert "/shell/" + PANEL_ID in body, (
        "Shell-URL /shell/%s muss in /api/v1/seiten/uebersicht erscheinen (SHELL-10)" % PANEL_ID
    )


def test_shell10_manifest_route(client):
    """SHELL-10 / SHELL-PWA: GET /shell/<panel_id>/manifest.json liefert gueltiges PWA-Manifest."""
    resp = client.get("/shell/" + PANEL_ID + "/manifest.json")
    assert resp.status_code == 200
    assert "manifest+json" in resp.headers.get("Content-Type", "")
    data = json.loads(resp.get_data(as_text=True))
    assert data["start_url"] == "/shell/" + PANEL_ID
    assert data["display"] == "fullscreen", "SHELL-PWA AC1: display muss 'fullscreen' sein"
    assert PANEL_ID in data["name"]


# ============================================================
#  test_shell11_* — SHELL-11: Shell-Vollbild-Besitz + embedded-Guards (Panel + Display-Client)
# ============================================================

def test_shell11_panel_embedded_guard():
    """SHELL-11/AC1: app.js enthält embedded-Guard (self===top) in attachFullscreenOnGesture."""
    app_js_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "controller", "app-panel", "app.js",
    )
    with open(app_js_path, encoding="utf-8") as fh:
        src = fh.read()
    # Guard muss im Kontext von attachFullscreenOnGesture stehen (window.self === window.top)
    assert "window.self" in src, "Guard-Ausdruck 'window.self' fehlt in app.js"
    assert "window.top" in src, "Guard-Ausdruck 'window.top' fehlt in app.js"
    # attachFullscreenImpl darf NUR aufgerufen werden wenn guard passiert —
    # der Guard-Block muss vor attachFullscreenImpl.call erscheinen
    guard_pos = src.find("window.self !== window.top")
    attach_pos = src.find("attachFullscreenImpl", guard_pos)
    assert guard_pos != -1, "Guard 'window.self !== window.top' nicht gefunden"
    assert attach_pos != -1, (
        "attachFullscreenImpl nach dem Guard nicht gefunden — Guard und Aufruf passen nicht zusammen"
    )


def test_shell11_display_client_embedded_guard():
    """SHELL-11/AC4 + DC-11 embedded-Ausnahme: display-client/index.html enthält Guard
    (window.self === window.top) vor attachFullscreenOnGesture — symmetrisch zum Panel-Guard."""
    index_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "display-client", "index.html",
    )
    with open(index_path, encoding="utf-8") as fh:
        src = fh.read()
    # Guard-Ausdruck muss vorhanden sein
    assert "window.self" in src, "Guard-Ausdruck 'window.self' fehlt in display-client/index.html"
    assert "window.top" in src, "Guard-Ausdruck 'window.top' fehlt in display-client/index.html"
    # Guard muss VOR dem attachFullscreenOnGesture-Aufruf stehen
    guard_pos = src.find("window.self === window.top")
    attach_pos = src.find("attachFullscreenOnGesture", guard_pos)
    assert guard_pos != -1, (
        "Guard 'window.self === window.top' nicht in display-client/index.html gefunden (DC-11 embedded-Ausnahme)"
    )
    assert attach_pos != -1, (
        "attachFullscreenOnGesture nach dem Guard nicht gefunden — Guard sitzt nicht vor dem DC-11-Aufruf"
    )
    # displib.js darf NICHT den Guard enthalten — Guard ausschließlich im Konsument
    displib_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "display-client", "displib.js",
    )
    with open(displib_path, encoding="utf-8") as fh:
        displib_src = fh.read()
    assert "window.self !== window.top" not in displib_src, (
        "displib.js darf den embedded-Guard nicht enthalten — Lib bleibt unangetastet (SHELL-11 stop_rule)"
    )


def test_shell11_shell_fullscreen_script(client):
    """SHELL-11/AC2: Shell-HTML enthaelt Vollbild-Script (requestFullscreen auf Shell-Dokument)."""
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)
    assert "requestFullscreen" in body or "webkitRequestFullscreen" in body, (
        "Shell-HTML muss requestFullscreen enthalten (SHELL-11)"
    )
    assert "tryFullscreen" in body, (
        "Shell-HTML muss tryFullscreen-Funktion enthalten (SHELL-11)"
    )


# ============================================================
#  test_shell_pwa_ac* — SHELL-PWA (AC1..AC4, #1212)
# ============================================================

def test_shell_pwa_ac1_icons_nicht_leer(client):
    """SHELL-PWA AC1: Manifest icons-Array ist nicht leer + enthaelt 192/512/maskable."""
    resp = client.get("/shell/" + PANEL_ID + "/manifest.json")
    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))
    icons = data.get("icons", [])
    assert len(icons) >= 3, "SHELL-PWA AC1: Manifest muss mindestens 3 Icons (192/512/maskable) tragen"
    sizes = {i["sizes"] for i in icons}
    assert "192x192" in sizes, "SHELL-PWA AC1: icon-192 fehlt"
    assert "512x512" in sizes, "SHELL-PWA AC1: icon-512 fehlt"
    purposes = {i.get("purpose", "any") for i in icons}
    assert "maskable" in purposes, "SHELL-PWA AC1: maskable-Icon fehlt"


def test_shell_pwa_ac1_display_fullscreen(client):
    """SHELL-PWA AC1: Manifest.display ist 'fullscreen' (nicht standalone)."""
    resp = client.get("/shell/" + PANEL_ID + "/manifest.json")
    data = json.loads(resp.get_data(as_text=True))
    assert data["display"] == "fullscreen", (
        "SHELL-PWA AC1: display muss 'fullscreen' sein fuer WebAPK-Vollbild"
    )


def test_shell_pwa_ac1_scope(client):
    """SHELL-PWA AC1: Manifest enthaelt scope /shell/."""
    resp = client.get("/shell/" + PANEL_ID + "/manifest.json")
    data = json.loads(resp.get_data(as_text=True))
    assert "scope" in data, "SHELL-PWA AC1: Manifest muss scope-Feld tragen"
    assert data["scope"] == "/shell/", "SHELL-PWA AC1: scope muss /shell/ sein"


def test_shell_pwa_ac2_sw_route(client):
    """SHELL-PWA AC2: GET /shell/<panel_id>/sw.js liefert JavaScript (Content-Type + Service-Worker-Allowed)."""
    resp = client.get("/shell/" + PANEL_ID + "/sw.js")
    assert resp.status_code == 200, "SHELL-PWA AC2: sw.js-Route muss 200 liefern"
    assert "javascript" in resp.headers.get("Content-Type", ""), (
        "SHELL-PWA AC2: sw.js muss als application/javascript ausgeliefert werden"
    )
    allowed = resp.headers.get("Service-Worker-Allowed", "")
    assert "/shell/" in allowed, (
        "SHELL-PWA AC2: Service-Worker-Allowed: /shell/ Header muss gesetzt sein "
        "(erlaubt Scope jenseits des SW-Datei-Pfads)"
    )


def test_shell_pwa_ac2_sw_build_id_ersetzt(client):
    """SHELL-PWA AC2: __BUILD_ID__-Platzhalter in sw.js wird beim Ausliefern ersetzt."""
    resp = client.get("/shell/" + PANEL_ID + "/sw.js")
    body = resp.get_data(as_text=True)
    assert "__BUILD_ID__" not in body, (
        "SHELL-PWA AC2: __BUILD_ID__-Platzhalter muss in sw.js ersetzt sein (Cache-Versionierung)"
    )
    assert "shell-pwa-" in body, "SHELL-PWA AC2: CACHE_NAME muss 'shell-pwa-' enthalten"


def test_shell_pwa_ac2_icon_routes(client, monkeypatch, tmp_path):
    """SHELL-PWA AC2: icon-*.png-Routen liefern image/png aus seiten/static/shell/."""
    import shutil
    # Test-Asset-Verzeichnis mit echten PNG-Kopien aufbauen.
    shell_assets = tmp_path / "shell"
    shell_assets.mkdir()
    real_shell = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "shell",
    )
    for fname in ("icon-192.png", "icon-512.png", "icon-maskable-512.png"):
        shutil.copy(os.path.join(real_shell, fname), str(shell_assets / fname))
    monkeypatch.setitem(seiten_main.runtime, "shell_asset_dir", str(shell_assets))

    for fname in ("icon-192.png", "icon-512.png", "icon-maskable-512.png"):
        resp = client.get("/shell/" + PANEL_ID + "/" + fname)
        assert resp.status_code == 200, f"SHELL-PWA AC2: {fname}-Route muss 200 liefern"
        assert "image/png" in resp.headers.get("Content-Type", ""), (
            f"SHELL-PWA AC2: {fname} muss als image/png ausgeliefert werden"
        )


def test_shell_pwa_ac2_html_registriert_sw(client):
    """SHELL-PWA AC2: Shell-HTML bindet Manifest + registriert sw.js via navigator.serviceWorker."""
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)
    assert 'rel="manifest"' in body, "SHELL-PWA AC2: manifest-Link fehlt in Shell-HTML"
    assert "serviceWorker" in body, "SHELL-PWA AC2: Service-Worker-Registrierung fehlt in Shell-HTML"
    assert "sw.js" in body, "SHELL-PWA AC2: sw.js-Referenz fehlt in Shell-HTML"
    assert "/shell/" in body, "SHELL-PWA AC2: SW-Scope /shell/ muss in HTML erscheinen"


def test_shell_pwa_ac3_rail_iframe_nativ(client):
    """T1224/AC1: heim-shell.css enthaelt KEINEN scale(0.5)/200%-Hack mehr.

    Rail-Iframe rendert nativ (width:100%; height:100%) — Panel-Inhalt skaliert
    jetzt kachel-relativ via Container-Queries in controller/app-panel/style.css.
    """
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "heim-shell.css",
    )
    with open(css_path, encoding="utf-8") as fh:
        css = fh.read()
    assert "scale(0.5)" not in css, (
        "T1224/AC1: scale(0.5)-Hack muss aus heim-shell.css entfernt sein"
    )
    assert "200%" not in css, (
        "T1224/AC1: 200%-Ueberdimensionierung muss aus heim-shell.css entfernt sein"
    )
    # Rail-Iframe rendert nativ
    assert ".rail iframe" in css, ".rail iframe-Regel muss weiter vorhanden sein"
    # Container-Query in style.css (AC2)
    style_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "controller", "app-panel", "style.css",
    )
    with open(style_path, encoding="utf-8") as fh:
        style = fh.read()
    assert "container-type" in style, (
        "T1224/AC2: container-type muss in controller/app-panel/style.css gesetzt sein"
    )
    assert "cqmin" in style, (
        "T1224/AC2: cqmin-Einheit muss in style.css fuer kachel-relatives Scaling verwendet werden"
    )


def test_shell12_resume_reload_script(client):
    """SHELL-12: Shell-HTML enthaelt Resume-Reload-Script (Clock-Drift + visibilitychange + pageshow).

    AC1: Clock-Drift-Detektor (setInterval 2000ms, _lastTick, Gap>10000ms) ist primaerer Trigger.
    AC2: Reload via window.location.reload(); _reloading-Guard verhindert Mehrfach-Reload.
         visibilitychange(>3000ms) + pageshow.persisted als Fallback-Trigger. Refs #1239.
    """
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)

    # --- AC1: Clock-Drift-Detektor ---
    # setInterval-Tick-Schleife
    assert "setInterval" in body, (
        "SHELL-12/AC1: setInterval (Clock-Drift-Detektor) fehlt im Shell-HTML"
    )
    # _lastTick-Variable fuer Drift-Erkennung
    assert "_lastTick" in body, (
        "SHELL-12/AC1: _lastTick-Variable fehlt — Clock-Drift-Detektor nicht vorhanden"
    )
    # Drift-Schwelle (Gap > 10000ms) muss als Konstante sichtbar sein
    assert "CLOCK_DRIFT_THRESHOLD_MS" in body, (
        "SHELL-12/AC1: CLOCK_DRIFT_THRESHOLD_MS-Schwelle fehlt im Shell-HTML"
    )

    # --- AC2: Reload-Mechanismus + Guard ---
    # Reload via window.location.reload() (NICHT iframe.src-Trick)
    assert "window.location.reload()" in body, (
        "SHELL-12/AC2: window.location.reload() fehlt — Reload muss ganze Shell neu laden"
    )
    # _reloading-Guard verhindert Mehrfach-Reload
    assert "_reloading" in body, (
        "SHELL-12/AC2: _reloading-Guard fehlt im Shell-HTML"
    )

    # --- Fallback-Trigger ---
    # visibilitychange-Schwelle (RESUME_RELOAD_THRESHOLD_MS, 3000ms)
    assert "RESUME_RELOAD_THRESHOLD_MS" in body, (
        "SHELL-12: RESUME_RELOAD_THRESHOLD_MS-Konstante fehlt im Shell-HTML"
    )
    assert "visibilitychange" in body, (
        "SHELL-12: visibilitychange-Fallback-Handler fehlt im Shell-HTML"
    )
    # Kurzzeit-Verdeckung (< Schwelle) darf KEINEN Reload ausloesen
    assert "_hiddenAt" in body, (
        "SHELL-12: _hiddenAt-Zeitstempel fehlt — kein Flash bei kurzer Verdeckung"
    )
    # pageshow + persisted (bfcache-Resume)
    assert "pageshow" in body, (
        "SHELL-12: pageshow-Fallback-Handler fehlt im Shell-HTML"
    )
    assert "persisted" in body, (
        "SHELL-12: persisted-Check fehlt im Shell-HTML (bfcache-Resume)"
    )


def test_shell12_clock_drift_und_guard(client):
    """SHELL-12/AC1+AC2 (Refs #1239): Clock-Drift-Parameter + location.reload + _reloading-Guard.

    Prueft dass:
    - setInterval mit TICK_INTERVAL_MS (2000ms) vorhanden ist
    - CLOCK_DRIFT_THRESHOLD_MS (10000ms Gap) als Schwelle sichtbar ist
    - window.location.reload() der Reload-Mechanismus ist (kein iframe.src-Trick)
    - _reloading-Guard Mehrfach-Reload verhindert
    - iframe.src = iframe.src NICHT mehr als Reload-Mechanismus vorhanden ist
    """
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)

    # Tick-Intervall 2000ms — direkt im setInterval-Aufruf
    assert "2000" in body, (
        "SHELL-12/AC1: Tick-Intervall 2000ms fehlt im Shell-HTML"
    )
    # Drift-Schwelle 10000ms
    assert "10000" in body, (
        "SHELL-12/AC1: CLOCK_DRIFT_THRESHOLD_MS=10000ms fehlt im Shell-HTML"
    )
    # window.location.reload() ist Reload-Mechanismus
    assert "window.location.reload()" in body, (
        "SHELL-12/AC2: window.location.reload() ist Pflicht-Reload-Mechanismus"
    )
    # Guard vorhanden
    assert "_reloading" in body, (
        "SHELL-12/AC2: _reloading-Guard fehlt"
    )
    # Alter iframe.src = iframe.src-Trick darf NICHT mehr vorhanden sein
    assert "iframes[i].src = iframes[i].src" not in body, (
        "SHELL-12/AC2: iframe.src = iframe.src-No-Op-Trick muss entfernt sein (Refs #1239)"
    )


def test_shell12_connectivity_gated_reload(client):
    """SHELL-12/AC1 (#1245): Wake reloadet nicht direkt, sondern erst nach Netz-Probe.

    Prueft:
    - waitForConnectivityThenReload-Funktion vorhanden.
    - Probe via fetch HEAD, no-store, auf eine same-origin URL.
    - _reloading-Guard + window.location.reload() erst bei res.ok.
    - Retry-Cap (PROBE_MAX_ATTEMPTS) → kein Endlos-Loop.
    """
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)

    assert "waitForConnectivityThenReload" in body, (
        "SHELL-12/AC1: waitForConnectivityThenReload-Funktion fehlt im Shell-HTML"
    )
    # Probe: fetch HEAD no-store
    assert "fetch(" in body, "SHELL-12/AC1: fetch-Probe fehlt"
    assert "'HEAD'" in body or '"HEAD"' in body, (
        "SHELL-12/AC1: HEAD-Methode fuer Connectivity-Probe fehlt"
    )
    assert "no-store" in body, (
        "SHELL-12/AC1: cache:'no-store' fuer Connectivity-Probe fehlt"
    )
    # Nur bei res.ok reloaden (Guard + reload)
    assert "res.ok" in body, (
        "SHELL-12/AC1: res.ok-Bedingung (nur bei Netz reloaden) fehlt"
    )
    assert "window.location.reload()" in body, (
        "SHELL-12/AC1: window.location.reload() fehlt"
    )
    assert "_reloading" in body, "SHELL-12/AC1: _reloading-Guard fehlt"
    # Retry-Cap gegen Endlos-Loop
    assert "PROBE_MAX_ATTEMPTS" in body, (
        "SHELL-12/AC1: PROBE_MAX_ATTEMPTS-Cap fehlt (kein Endlos-Loop)"
    )
    # console.log-Diagnose, kein sichtbares Overlay
    assert "[shell-wake]" in body, (
        "SHELL-12: console.log-Diagnose ([shell-wake] …) fehlt"
    )


def test_shell12_online_und_iframe_error_trigger(client):
    """SHELL-12/AC1+AC2 (#1245): online-Event + Iframe-onerror triggern die Probe.

    - online-Event ruft waitForConnectivityThenReload (WLAN zurueck).
    - same-origin Iframes (.rail/.buddy) mit error-Listener → Probe
      (OS-Kill-dann-Relaunch, kein Clock-Drift).
    """
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)

    # online-Trigger
    assert "'online'" in body or '"online"' in body, (
        "SHELL-12/AC1: online-Event-Listener fehlt im Shell-HTML"
    )
    # Iframe-onerror-Beobachtung der same-origin Iframes
    assert ".rail iframe" in body, (
        "SHELL-12/AC2: .rail iframe-Selektor fuer onerror-Beobachtung fehlt"
    )
    assert ".buddy iframe" in body, (
        "SHELL-12/AC2: .buddy iframe-Selektor fuer onerror-Beobachtung fehlt"
    )
    assert "'error'" in body or '"error"' in body, (
        "SHELL-12/AC2: error-Listener fuer Iframe-Load-Fehler fehlt"
    )
    # Trigger fuehren zur Probe-Funktion
    assert body.count("waitForConnectivityThenReload") >= 2, (
        "SHELL-12: waitForConnectivityThenReload muss von mehreren Triggern gerufen werden"
    )


def test_shell12_online_flap_guard_variablen(client):
    """SHELL-12/Flap-Guard: _offlineSince-Variable + offline-Listener vorhanden.

    Prueft dass:
    - _offlineSince als Guard-Variable im Script deklariert ist.
    - Ein 'offline'-Event-Listener vorhanden ist (setzt _offlineSince).
    - Der online-Handler _offlineSince prueft (Bedingung im Script sichtbar).
    - RESUME_RELOAD_THRESHOLD_MS fuer den Flap-Guard wiederverwendet wird.
    """
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)

    # Guard-Variable muss deklariert sein
    assert "_offlineSince" in body, (
        "SHELL-12/Flap-Guard: _offlineSince-Variable fehlt im Shell-HTML"
    )
    # offline-Listener muss vorhanden sein
    assert "'offline'" in body or '"offline"' in body, (
        "SHELL-12/Flap-Guard: offline-Event-Listener fehlt — setzt _offlineSince"
    )
    # Bedingungspruefung im online-Handler: _offlineSince !== null
    assert "_offlineSince !== null" in body, (
        "SHELL-12/Flap-Guard: Bedingung '_offlineSince !== null' fehlt im online-Handler"
    )
    # RESUME_RELOAD_THRESHOLD_MS als Schwelle wiederverwenden (3000ms)
    # Prueft dass die Schwellen-Variable auch im Flap-Guard-Kontext erscheint
    # (mind. 2x im Body: einmal fuer visibilitychange, einmal fuer Flap-Guard)
    assert body.count("RESUME_RELOAD_THRESHOLD_MS") >= 2, (
        "SHELL-12/Flap-Guard: RESUME_RELOAD_THRESHOLD_MS muss im Flap-Guard-Kontext "
        "erscheinen (visibilitychange + online-Flap-Guard = mind. 2 Vorkommen)"
    )


def test_shell12_online_flap_guard_reset(client):
    """SHELL-12/Flap-Guard: _offlineSince wird nach online-Event zurueckgesetzt (null).

    Nach dem online-Event (egal ob Reload ausgeloest oder Flap ignoriert) muss
    _offlineSince = null gesetzt werden — sonst triggert ein spaeterer
    online-Event faelschlicherweise einen Reload obwohl der Aussetzer kurz war.
    """
    body = client.get("/shell/" + PANEL_ID).get_data(as_text=True)

    # _offlineSince = null muss im online-Handler-Kontext erscheinen
    # (Prueft: der Reset existiert, nicht nur die Initialisierung)
    # Mindestens 2 Vorkommen: Initialisierung (var _offlineSince = null) + Reset im Handler
    assert body.count("_offlineSince = null") >= 2, (
        "SHELL-12/Flap-Guard: _offlineSince = null muss mind. 2x erscheinen "
        "(Initialisierung + Reset im online-Handler nach Pruefung)"
    )


def test_shell12_panel_display_unangetastet():
    """SHELL-12/AC2 stop_rule: controller/app-panel/** und display-client/** unangetastet."""
    import subprocess
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for path in ("controller/app-panel/app.js", "display-client/index.html"):
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", path],
            capture_output=True, text=True,
            cwd=repo_root,
        )
        changed = result.stdout.strip()
        assert changed == "", (
            "SHELL-12/AC2 stop_rule: %s darf NICHT geaendert sein (Panel/Display unangetastet)" % path
        )


# ============================================================
#  test_shell_pwa_sw_* — SHELL-PWA-SW (#1241)
#  Prueft: network-first fuer HTML-Navigation, cache-first fuer Static-Assets.
# ============================================================

def _read_sw_js():
    """Liefert den sw.js-Quelltext (aus seiten/static/shell/sw.js)."""
    sw_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "shell", "sw.js",
    )
    with open(sw_path, encoding="utf-8") as fh:
        return fh.read()


def test_shell_pwa_sw_html_network_first():
    """SHELL-PWA-SW/AC1 (#1241): sw.js verwendet network-first fuer Shell-HTML-Navigation.

    Prueft:
    - isShellHtmlNavigation (oder aequivalente Funktion) unterscheidet HTML von Assets.
    - networkFirst-Funktion ist vorhanden und hat Offline-Fallback (caches.match).
    - request.mode === 'navigate' wird als Erkennungs-Signal verwendet.
    - HTML-Navigation ruft networkFirst auf, nicht cacheFirst.
    """
    src = _read_sw_js()
    # Network-first-Funktion muss vorhanden sein
    assert "networkFirst" in src, (
        "SHELL-PWA-SW/AC1: networkFirst-Funktion fehlt in sw.js"
    )
    # Offline-Fallback (caches.match) muss in networkFirst vorhanden sein
    # (keep_installable: Offline-Fallback darf nicht fehlen)
    nf_start = src.find("function networkFirst")
    assert nf_start != -1, "networkFirst-Funktion nicht gefunden"
    # caches.match muss innerhalb der networkFirst-Funktion oder erreichbar sein
    assert "caches.match" in src[nf_start:], (
        "SHELL-PWA-SW/AC1: Offline-Fallback caches.match fehlt in networkFirst "
        "(keep_installable: Installierbarkeit erfordert fetch-Handler mit Offline-Fallback)"
    )
    # request.mode === 'navigate' als primaeres HTML-Signal
    assert "navigate" in src, (
        "SHELL-PWA-SW/AC1: request.mode === 'navigate' fehlt — "
        "HTML-Navigation muss per mode erkannt werden"
    )
    # isShellHtmlNavigation (oder analoge Erkennungs-Funktion) muss existieren
    assert "isShellHtmlNavigation" in src, (
        "SHELL-PWA-SW/AC1: isShellHtmlNavigation-Funktion fehlt in sw.js"
    )
    # HTML-Navigation muss networkFirst aufrufen (nicht cacheFirst)
    # Prueft: respondWith(networkFirst(...)) erscheint im Kontext von isShellHtmlNavigation
    html_nav_pos = src.find("isShellHtmlNavigation")
    assert html_nav_pos != -1
    # Suche networkFirst nach der HTML-Nav-Pruefung (im fetch-Handler-Zweig)
    nf_call_pos = src.find("networkFirst", html_nav_pos)
    assert nf_call_pos != -1, (
        "SHELL-PWA-SW/AC1: networkFirst wird nach isShellHtmlNavigation nicht aufgerufen"
    )


def test_shell_pwa_sw_assets_cache_first():
    """SHELL-PWA-SW/AC2 (#1241): sw.js behaelt cache-first fuer Static-Assets.

    Prueft:
    - isShellStaticAsset (oder aequivalente Funktion) matcht manifest.json,
      icons, heim-shell.css, platform.js.
    - cacheFirst-Funktion bleibt vorhanden.
    - Static-Asset-Zweig ruft cacheFirst auf.
    - /controller/ und /display/ bleiben pass-through (unveraendert).
    - BUILD_ID/CACHE_NAME-Versionierung + activate-Cleanup erhalten.
    """
    src = _read_sw_js()
    # cacheFirst muss weiterhin vorhanden sein
    assert "cacheFirst" in src, (
        "SHELL-PWA-SW/AC2: cacheFirst-Funktion fehlt in sw.js"
    )
    # Statische Asset-Erkennung muss vorhanden sein
    assert "isShellStaticAsset" in src, (
        "SHELL-PWA-SW/AC2: isShellStaticAsset-Funktion fehlt in sw.js"
    )
    # manifest.json und icon werden per zweitem Pfad-Segment unterschieden
    # (oder explizit geprueft) — 'includes' als Schluessel-Pattern
    assert "manifest" in src or "includes('/')" in src, (
        "SHELL-PWA-SW/AC2: Asset-Unterscheidung (manifest / zweites Segment) fehlt"
    )
    # heim-shell und platform.js muessen als statische Assets erkannt werden
    assert "heim-shell" in src, (
        "SHELL-PWA-SW/AC2: heim-shell-Asset fehlt in isShellStaticAsset"
    )
    assert "platform.js" in src, (
        "SHELL-PWA-SW/AC2: platform.js fehlt in isShellStaticAsset"
    )
    # Static-Asset-Zweig ruft cacheFirst auf
    static_pos = src.find("isShellStaticAsset")
    assert static_pos != -1
    cf_call_pos = src.find("cacheFirst", static_pos)
    assert cf_call_pos != -1, (
        "SHELL-PWA-SW/AC2: cacheFirst wird nach isShellStaticAsset nicht aufgerufen"
    )
    # pass-through fuer /controller/ und /display/ erhalten
    assert "/controller/" in src, (
        "SHELL-PWA-SW/AC2: /controller/ pass-through fehlt in sw.js"
    )
    assert "/display/" in src, (
        "SHELL-PWA-SW/AC2: /display/ pass-through fehlt in sw.js"
    )
    # BUILD_ID/CACHE_NAME-Versionierung erhalten
    assert "BUILD_ID" in src, "SHELL-PWA-SW/AC2: BUILD_ID fehlt"
    assert "CACHE_NAME" in src, "SHELL-PWA-SW/AC2: CACHE_NAME fehlt"
    assert "shell-pwa-" in src, "SHELL-PWA-SW/AC2: shell-pwa- Namespace-Prefix fehlt"
    # activate-Cleanup erhalten
    assert "caches.delete" in src, (
        "SHELL-PWA-SW/AC2: activate-Cleanup (caches.delete alter Namespaces) fehlt"
    )


def test_shell_pwa_sw_html_timeout():
    """SHELL-PWA-SW/AC3 (#1245): networkFirst rennt gegen ein Timeout (Wake-Hang vermeiden).

    Prueft:
    - networkFirst verwendet Promise.race (fetch vs. Timeout).
    - ~2000ms-Timeout als Konstante sichtbar.
    - Cache-Fallback (caches.match) bei Timeout/Fehler erhalten (keep_installable).
    - Static-Assets/cacheFirst unveraendert (kein Timeout dort).
    """
    src = _read_sw_js()
    nf_start = src.find("function networkFirst")
    assert nf_start != -1, "networkFirst-Funktion nicht gefunden"
    nf_body = src[nf_start:]
    assert "Promise.race" in nf_body, (
        "SHELL-PWA-SW/AC3: networkFirst muss Promise.race([fetch, timeout]) nutzen"
    )
    assert "NETWORK_TIMEOUT_MS" in nf_body, (
        "SHELL-PWA-SW/AC3: NETWORK_TIMEOUT_MS-Timeout fehlt in networkFirst"
    )
    assert "NETWORK_TIMEOUT_MS = 2000" in src, (
        "SHELL-PWA-SW/AC3: ~2000ms-Timeout-Konstante fehlt in sw.js"
    )
    assert "setTimeout" in nf_body, (
        "SHELL-PWA-SW/AC3: Timeout-Promise (setTimeout) fehlt in networkFirst"
    )
    # Cache-Fallback erhalten
    assert "caches.match" in nf_body, (
        "SHELL-PWA-SW/AC3: Cache-Fallback (caches.match) muss erhalten bleiben (keep_installable)"
    )
    # cacheFirst darf KEIN Timeout tragen (Static unveraendert)
    cf_start = src.find("function cacheFirst")
    assert cf_start != -1
    cf_body = src[cf_start:src.find("self.addEventListener('fetch'", cf_start)]
    assert "Promise.race" not in cf_body, (
        "SHELL-PWA-SW/AC3: cacheFirst (Static-Assets) darf KEIN Timeout tragen — unveraendert"
    )


def test_shell_pwa_ac3_panel_unangetastet():
    """SHELL-PWA AC3 stop_rule: controller/app-panel/app.js (PANEL-12-Grid/JS) unveraendert.

    Bewacht wird ausschliesslich app.js — die JS-seitige Grid-Geometrie darf nicht
    angefasst werden. Panel-CSS (style.css) ist fuer die kachel-relative
    Inhalts-Skalierung (Container-Query / cqmin) ausdruecklich erlaubt (T1224,
    Nic-angewiesen 2026-06-30).
    """
    import subprocess
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # Git-Status pruefen: app.js darf keine ungestaged/staged Aenderungen haben.
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "controller/app-panel/app.js"],
        capture_output=True, text=True,
        cwd=repo_root,
    )
    changed = result.stdout.strip()
    assert changed == "", (
        "SHELL-PWA AC3 stop_rule: controller/app-panel/app.js darf NICHT geaendert sein "
        "(PANEL-12-Grid/JS unveraendert — nur style.css fuer Container-Query erlaubt)"
    )
