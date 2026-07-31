"""Tests fuer Heim-Shell (SHELL-1..11) — GET /shell/<panel_id>.

Test-Anker: shell1/3/4/5/9/10/11 (specs/platform/heim-shell.md, Refs #1182).
RAT-31: SHELL-2 (display_id per Router-Lookup) obsolet — entfernt (#1588).
Lauf: python3 -m pytest seiten/tests/test_heim_shell.py -q

Teststruktur:
  test_shell1_route_html           — SHELL-1: Route liefert 200 + text/html
  test_shell3_zwei_iframes         — SHELL-3: zwei Iframes (Panel-Nav-Rail + Buddy-Pane)
  test_shell4_pane_bindet_seiten_sse — SHELL-4: rechtes Pane hat eigene EventSource
  test_shell5_kein_displib_import  — SHELL-5: kein displib-Import in Shell-HTML
  test_shell9_keine_hardcode_ids   — SHELL-9: keine Pilot-IDs im Template/Route-Code
  test_shell10_manifest_route      — SHELL-10: PWA-Manifest je panel_id
  test_shell11_*                   — SHELL-11: Shell-Vollbild-Besitz + embedded-Guards
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
from tools.initdata import session_cookie as _sc  # noqa: E402

# Pilot-IDs — nur in Tests, nie im Produktiv-Code (SHELL-9).
PANEL_ID = "paulas-panel-01"
DISPLAY_ID = "tablet-tablet-paula-01"


# ============================================================
#  Shared Fixture
# ============================================================

# RAT-32: /shell/ ist Cookie-only-hart (Operator-IP als Zugangs-Alternative
# gestrichen). Tests authentifizieren via gültigem xbuddy_session-Cookie am
# Testclient (set_cookie — Werkzeug liest kein manuelles Cookie-Header). Das
# leere _OPERATOR_HEADERS bleibt als Platzhalter, damit die vielen
# `headers=_OPERATOR_HEADERS`-Aufrufstellen unberührt bleiben.
BOT_TOKEN = "123456:ABCdef_testtoken"
_OPERATOR_HEADERS: dict = {}


def _auth_client():
    """Testclient mit gültigem xbuddy_session-Cookie (RAT-32 Cookie-only-hart)."""
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    c.set_cookie(_sc.COOKIE_NAME, _sc.sign_session(DISPLAY_ID, BOT_TOKEN))
    return c


@pytest.fixture(autouse=True)
def _bot_token_konfiguriert():
    """RAT-32: der Cookie-Gate braucht einen konfigurierten Bot-Token, damit
    hat_gueltigen_cookie die Signatur prüfen kann (gilt für alle Tests hier,
    auch die mit Inline-Client). configure() setzt bot_token nur when-not-None,
    also überschreibt die client-Fixture-Konfiguration ihn nicht."""
    seiten_main.configure(bot_token=BOT_TOKEN)
    return


@pytest.fixture
def client(monkeypatch):
    """Cookie-authentifizierter Testclient mit Origin-Config.
    RAT-32: /shell/ ist Cookie-only-hart.
    RAT-31: kein display_id-Lookup-Mock mehr (SHELL-2 obsolet)."""
    seiten_main.configure(heim_origin="http://heim.test", tailscale_origin="https://tail.test")
    return _auth_client()


# ============================================================
#  test_shell1_route_html — SHELL-1
# ============================================================

def test_shell1_route_html(client):
    """SHELL-1: GET /shell/<panel_id> liefert HTTP 200 + text/html.
    T1448: /shell/ ist hard enforced — Operator-IP als Auth-Quelle (opt-in)."""
    resp = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS)
    assert resp.status_code == 200, "Route muss 200 liefern"
    assert "text/html" in resp.mimetype, "Antwort muss text/html sein"


def test_shell1_route_html_enthaelt_panel_id(client):
    """SHELL-1: HTML enthaelt panel_id (im Iframe-Src oder Titel).
    T1448: Operator-IP als Auth-Quelle (opt-in)."""
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
    assert PANEL_ID in body


# ============================================================
#  test_shell2_lookup_display_id — SHELL-2
# ============================================================

def test_shell4_pane_bindet_seiten_sse(client):
    """SHELL-4 (RAT-31 E2): Das rechte Pane hat eine EIGENE EventSource auf den
    seiten-seitigen SSE-Stream /shell/<panel_id>/events — kein statischer
    /display/<display_id>/-Iframe mehr (SHELL-2 überholt durch RAT-31)."""
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
    # Same-origin SSE-Stream statt Router-Lookup-Iframe:
    assert "/shell/" + PANEL_ID + "/events" in body, "Same-origin SSE-Stream-URL fehlt"
    assert "EventSource" in body, "Eigene EventSource im rechten Pane fehlt (SHELL-4 RAT-31 E2)"
    # Kein statischer Display-Client-Iframe mehr — der swap läuft über iframe.src:
    assert "/display/" + DISPLAY_ID + "/" not in body, (
        "Rechtes Pane darf keinen statischen /display/<display_id>/-Iframe mehr tragen"
    )


# ============================================================
#  test_shell3_zwei_iframes_src — SHELL-3
# ============================================================

def test_shell3_zwei_iframes(client):
    """SHELL-3: HTML enthaelt genau zwei Iframes (Panel-Nav-Rail + Buddy-Pane).
    RAT-31 E2: der Panel-Nav-Iframe trägt weiter seinen statischen src, das
    rechte Buddy-Pane bekommt seinen src erst per SSE-Swap (kein statischer src).
    T1448: Operator-IP als Auth-Quelle (opt-in)."""
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
    assert "/controller/app-panel/" + PANEL_ID + "/" in body, "Linker Panel-Iframe-Src fehlt"
    assert 'id="buddy-pane"' in body, "Rechtes Buddy-Pane-Iframe fehlt"
    assert body.count("<iframe") == 2, "Genau zwei Iframes erwartet (Rail + Buddy-Pane)"


def test_shell4_pane_ohne_statischen_src(client):
    """SHELL-4 (RAT-31 E2): Das rechte Buddy-Pane trägt KEINEN statischen src —
    der Inhalt kommt ausschließlich per SSE-getriebenem iframe.src-Swap. Der
    frühere display_id-gegatete Fehler-Pfad (SHELL-2) entfällt (RAT-31)."""
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
    # Linker Panel-Iframe bleibt unverändert:
    assert "/controller/app-panel/" + PANEL_ID + "/" in body
    # Kein statischer /display/-Iframe-Src im initialen HTML:
    assert "/display/" not in body
    # Der Swap läuft über pane.src im Empfänger-Script:
    assert "pane.src" in body, "iframe.src-Swap-Empfänger fehlt (SHELL-5 RAT-31 E2)"


def test_shell4_panel_iframe_traegt_ingest_url_param(client):
    """SHELL-4 / E2-Sender (T1519 AC1) + RAT-35 (#1546): Der linke Panel-Nav-Iframe
    bekommt die ingest_url mit — jetzt CLIENT-SEITIG gesetzt (nicht mehr im
    server-gerenderten src-Attribut), weil sie die ephemere `?sid=` dieses
    Dokuments tragen muss. Der server-gerenderte src ist bewusst LEER; das JS baut
    ihn aus '/controller/app-panel/<panel_id>/?ingest_url=' + encodeURIComponent(
    '/shell/<panel_id>/events?sid=' + sid). app.js liest ingest_url beim Bootstrap
    und postet tile_selected an /shell/<panel_id>/events?sid=<sid> statt an den Router.
    """
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)

    # Der Rail-Iframe hat KEINEN server-gerenderten src mehr (sonst trüge er keine sid):
    assert 'id="panel-rail"' in body, "Panel-Rail-Iframe (id=panel-rail) fehlt"

    # Das JS baut die ingest_url mit der sid — die Bausteine müssen im Dokument stehen:
    assert "'/controller/app-panel/" + PANEL_ID + "/?ingest_url='" in body, (
        "Das Shell-JS muss den Panel-Iframe-src client-seitig aus "
        "'/controller/app-panel/<panel_id>/?ingest_url=' bauen (RAT-35 #1546)"
    )
    assert "'/shell/" + PANEL_ID + "/events?sid=' + encodeURIComponent(sid)" in body, (
        "Das Shell-JS muss die ingest_url als /shell/<panel_id>/events?sid=<sid> bauen "
        "(SHELL-4 / E2-Sender + RAT-35 #1546)"
    )
    assert "rail.src =" in body, (
        "Das Shell-JS muss den Panel-Iframe-src client-seitig setzen (rail.src = ...)"
    )
    # Und die sid selbst wird pro Dokument einmal erzeugt:
    assert "crypto.randomUUID" in body, (
        "Das Shell-JS muss eine ephemere sid via crypto.randomUUID() erzeugen (RAT-35 #1546)"
    )


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
    """SHELL-5: Shell-HTML enthaelt keinen displib-Import (keine Display-Client-Codekopie).
    T1448: Operator-IP als Auth-Quelle (opt-in)."""
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
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
    c = _auth_client()
    manifest_resp = c.get("/shell/test-panel-99/manifest.json")
    assert manifest_resp.status_code == 200
    data = json.loads(manifest_resp.get_data(as_text=True))
    assert "test-panel-99" in data["start_url"], "start_url muss panel_id aus URL enthalten"
    assert "paulas-panel-01" not in data["start_url"], "Kein Hardcode in start_url"


# ============================================================
#  test_shell10_url_in_uebersicht — SHELL-10 (RAT-31 E3: entfernt)
# ============================================================
# test_shell10_url_in_uebersicht entfernt: SHELL-10 shell_urls-Enrichment-Loop
# in get_seiten() wurde mit RAT-31 E3 (#1496) entfernt (Loop enrichierte nur
# typ=panel-Einträge, die nicht mehr existieren).


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


def test_shell11_shell_fullscreen_script(client):
    """SHELL-11/AC2: Shell-HTML enthaelt Vollbild-Script (requestFullscreen auf Shell-Dokument).
    T1448: Operator-IP als Auth-Quelle (opt-in)."""
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
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
    """SHELL-PWA AC2: GET /shell/<panel_id>/sw.js liefert JavaScript (Content-Type + Service-Worker-Allowed).
    T1448: Operator-IP als Auth-Quelle (opt-in)."""
    resp = client.get("/shell/" + PANEL_ID + "/sw.js", headers=_OPERATOR_HEADERS)
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
    """SHELL-PWA AC2: __BUILD_ID__-Platzhalter in sw.js wird beim Ausliefern ersetzt.
    T1448: Operator-IP als Auth-Quelle (opt-in)."""
    resp = client.get("/shell/" + PANEL_ID + "/sw.js", headers=_OPERATOR_HEADERS)
    body = resp.get_data(as_text=True)
    assert "__BUILD_ID__" not in body, (
        "SHELL-PWA AC2: __BUILD_ID__-Platzhalter muss in sw.js ersetzt sein (Cache-Versionierung)"
    )
    assert "shell-pwa-" in body, "SHELL-PWA AC2: CACHE_NAME muss 'shell-pwa-' enthalten"


def test_shell_pwa_ac2_icon_routes(client, monkeypatch, tmp_path):
    """SHELL-PWA AC2: icon-*.png-Routen liefern image/png aus seiten/static/shell/.
    T1448: Operator-IP als Auth-Quelle (opt-in)."""
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
        resp = client.get("/shell/" + PANEL_ID + "/" + fname, headers=_OPERATOR_HEADERS)
        assert resp.status_code == 200, f"SHELL-PWA AC2: {fname}-Route muss 200 liefern"
        assert "image/png" in resp.headers.get("Content-Type", ""), (
            f"SHELL-PWA AC2: {fname} muss als image/png ausgeliefert werden"
        )


def test_shell_pwa_ac2_icon_public_ohne_operator(client, monkeypatch, tmp_path):
    """SHELL-PWA AC2 / AUTH-4: icon-192.png liefert 200 OHNE Cookie und OHNE Operator-IP.

    T1448-S3-fix: shell_asset_view ist AUTH-4-public (kein Decorator); WebAPK-Installer
    holt Icons credential-los (Fetch-Spec). Dieser Test verankert die Public-Eigenschaft
    in der seiten-Suite (ohne Header → 200, nicht 401).
    """
    import shutil
    shell_assets = tmp_path / "shell"
    shell_assets.mkdir()
    real_shell = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "shell",
    )
    shutil.copy(os.path.join(real_shell, "icon-192.png"), str(shell_assets / "icon-192.png"))
    monkeypatch.setitem(seiten_main.runtime, "shell_asset_dir", str(shell_assets))

    # RAT-32: expliziter UN-authentifizierter Client (kein Cookie), damit dieser
    # Test die Public-Eigenschaft (AUTH-4) echt prüft und nicht über den
    # Cookie der _auth_client-Fixture grün wird.
    client = seiten_main.app.test_client()
    # Kein Operator-IP, kein Cookie — Icon muss trotzdem 200 zurueckgeben (AUTH-4).
    resp = client.get("/shell/" + PANEL_ID + "/icon-192.png")
    assert resp.status_code == 200, (
        "SHELL-PWA AC2 / AUTH-4: icon-192.png muss public 200 zurueckgeben "
        "(kein Cookie, kein Operator-IP), got %d" % resp.status_code
    )
    assert "image/png" in resp.headers.get("Content-Type", ""), (
        "SHELL-PWA AC2: icon-192.png muss image/png Content-Type liefern"
    )


def test_shell_pwa_ac2_html_registriert_sw(client):
    """SHELL-PWA AC2: Shell-HTML bindet Manifest + registriert sw.js via navigator.serviceWorker.
    T1448: Operator-IP als Auth-Quelle (opt-in)."""
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
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


def test_shell_pwa_ac3_panel_unangetastet():
    """SHELL-PWA AC3 stop_rule: die PANEL-12-Grid-Geometrie in app.js unveraendert.

    Bewacht wird die JS-seitige Grid-Geometrie (computeGridGeometry /
    applyGridGeometry) — sie darf nicht angefasst werden. Panel-CSS (style.css)
    ist fuer die kachel-relative Inhalts-Skalierung (Container-Query / cqmin)
    ausdruecklich erlaubt (T1224, Nic-angewiesen 2026-06-30).

    T1656 (#1656, INST-1): Der Guard ist von „app.js komplett eingefroren" auf
    „nur die Grid-Geometrie eingefroren" verengt — INST-1 macht app.js
    ausdruecklich zum LESER der Instanz-Liste (window.__HSP_INSTANZEN__), was
    den HSP-Audio-Block (ausserhalb der Grid-Geometrie) legitim aendert.
    """
    app_js_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "controller", "app-panel", "app.js")

    def _grid_region(quelle):
        """Extrahiert den zusammenhaengenden PANEL-12-Geometrie-Block
        (computeGridGeometry + applyGridGeometry) als byte-Signatur.

        Grenzen: vom Geometrie-Section-Header bis zum '//  API'-Divider — das
        umfasst beide Grid-Funktionen und NICHTS vom HSP-Audio-Block danach.
        """
        start = quelle.index("//  PANEL-12 — Geometrie-Berechnung")
        ende = quelle.index("//  API", start)
        return quelle[start:ende]

    with open(app_js_path, encoding="utf-8") as fh:
        aktuell = fh.read()

    import subprocess
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    head = subprocess.run(
        ["git", "show", "HEAD:controller/app-panel/app.js"],
        capture_output=True, text=True, cwd=repo_root,
    ).stdout

    assert _grid_region(aktuell) == _grid_region(head), (
        "SHELL-PWA AC3 stop_rule: die PANEL-12-Grid-Geometrie (computeGridGeometry/"
        "applyGridGeometry) in controller/app-panel/app.js darf NICHT geaendert sein"
    )


# ============================================================
#  test_sw_scope_in_html_aus_registry — T1324 / PWAM-3
# ============================================================

def test_sw_scope_in_html_aus_registry(client):
    """T1324 / PWAM-3: gerendertes HTML enthaelt den SW-Scope aus REGISTRY['shell'].

    Kein hartkodiertes Literal im Template — {{ sw_scope }} wird mit dem
    pwa_mantel.REGISTRY['shell'].sw_scope-Wert substituiert.
    Muster analog test_connector.py::test_ac3_sw_scope_in_html_aus_registry.
    T1448: Operator-IP als Auth-Quelle (opt-in).
    """
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
    # Jinja2-Platzhalter muss ersetzt sein
    assert "{{ sw_scope }}" not in body, (
        "HTML enthaelt noch '{{ sw_scope }}'-Platzhalter — Jinja2-Substitution fehlgeschlagen"
    )
    erwartet_scope = pwa_mantel.REGISTRY["shell"].sw_scope
    assert erwartet_scope in body, (
        f"SW-Scope {erwartet_scope!r} aus REGISTRY fehlt im gerenderten HTML (PWAM-3 / T1324)"
    )


# ============================================================
#  T1543 — Klebende SWs robust ersetzen (Auto-Heal + Reset-Link)
# ============================================================

def test_t1543_ac1_auto_heal_in_seite_mit_loop_guard(client):
    """T1543 AC1/AC4 (Baustein 1): die SEITE (nicht der SW) enthaelt den Auto-Heal:
    build_id-Mismatch → alle SWs deregistrieren + alle Caches loeschen + EIN Reload,
    gegen Reload-Loop geschuetzt.

    Der Auto-Heal MUSS in der Seite liegen (ein kaputter SW darf ihn nicht erwuergen)
    und darf hoechstens EINMAL heilen (sessionStorage-Riegel + localStorage-Angleich).
    """
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
    # Selbstheil-Bausteine im Seiten-Body (nicht im SW):
    assert "getRegistrations" in body, "Auto-Heal muss ALLE SW-Registrierungen erfassen"
    assert "unregister" in body, "Auto-Heal muss Registrierungen deregistrieren"
    assert "caches.keys" in body, "Auto-Heal muss ALLE Cache-Namespaces erfassen"
    assert "caches.delete" in body, "Auto-Heal muss Caches loeschen"
    assert "location.reload" in body, "Auto-Heal muss neu laden"
    # Vergleich gegen server-gerenderte build_id (nicht den SW befragen):
    static_dir = os.path.join(os.path.dirname(seiten_main.__file__), "static")
    erwartet_build_id = pwa_mantel.build_id_for("shell", static_dir)
    assert erwartet_build_id in body, (
        "Server-build_id muss in die Seite gerendert sein (Mismatch-Vergleich, Baustein 1)"
    )
    # Reload-Loop-Schutz: sessionStorage-Riegel muss vorhanden sein.
    assert "sessionStorage" in body, "Reload-Loop-Schutz (sessionStorage-Riegel) fehlt"
    assert "shell_heal_done" in body, "Reload-Loop-Schutz-Flag fehlt (nur EINMAL heilen)"


def test_t1543_ac2_reset_route_liefert_kill_js(client):
    """T1543 AC2/AC4 (Baustein 2): die Reset-Route liefert 2xx + die Kill-JS,
    die ALLE SWs deregistriert + ALLE Caches loescht + zur Shell zurueckleitet.

    Route liegt AUSSERHALB der /shell/-SW-Scope (unter /api/v1/seiten/), damit ein
    klebender /shell/-SW sie nie kontrolliert; no-store, damit sie immer frisch laedt.
    """
    resp = client.get("/api/v1/seiten/reset")
    assert resp.status_code == 200, "Reset-Route muss 2xx liefern"
    assert "text/html" in resp.headers.get("Content-Type", ""), "Reset-Route muss HTML liefern"
    body = resp.get_data(as_text=True)
    assert "getRegistrations" in body, "Reset-JS muss ALLE SWs erfassen (auch app-panel-Scope)"
    assert "unregister" in body, "Reset-JS muss SWs deregistrieren"
    assert "caches.keys" in body, "Reset-JS muss ALLE Caches erfassen"
    assert "caches.delete" in body, "Reset-JS muss Caches loeschen"
    assert "location.replace" in body or "location.href" in body, (
        "Reset-JS muss nach dem Purge zur Shell zurueckleiten"
    )
    # Route liegt ausserhalb der /shell/-SW-Scope (Scope-Praefix nicht im Pfad).
    assert not "/api/v1/seiten/reset".startswith("/shell/"), (
        "Reset-Pfad muss AUSSERHALB der /shell/-SW-Scope liegen"
    )
    assert "no-store" in resp.headers.get("Cache-Control", ""), (
        "Reset-Route muss no-store sein (klebender SW/Cache darf sie nicht abfangen)"
    )


def test_t1543_ac2_reset_route_ist_public(monkeypatch):
    """T1543 AC2: die Reset-Seite zeigt keine Familiendaten und muss auch ohne
    gueltigen Cookie laden — sie ist genau der Rettungspfad fuer ein Geraet, dessen
    Auth/SW gerade klemmt. Public (AUTH-4, analog shell_asset_view/manifest)."""
    seiten_main.configure(bot_token=BOT_TOKEN)
    c = seiten_main.app.test_client()  # KEIN Session-Cookie
    resp = c.get("/api/v1/seiten/reset")
    assert resp.status_code == 200, (
        "Reset-Route muss public sein (kein Cookie noetig — Rettungspfad fuer klemmendes Geraet)"
    )


def test_t1543_ac2_reset_redirect_open_redirect_schutz(client):
    """T1543 AC2: der ?to=-Redirect ist auf eigene relative Pfade begrenzt
    (Open-Redirect-Schutz) — ein externer Ziel-Host wird verworfen."""
    resp = client.get("/api/v1/seiten/reset?to=https://evil.example/x")
    body = resp.get_data(as_text=True)
    assert "evil.example" not in body, "Open-Redirect: externes Ziel darf nicht durchreichen"


# ============================================================
#  SHELL-12: Device-Fit-Scale (Refs #1595)
# ============================================================

def test_shell12_fit_wrapper_in_html(client):
    """SHELL-12: HTML enthaelt den Fit-Wrapper (.shell-fit) als Eltern-Element von .shell.
    Das JS-Script setzt --shell-scale = innerWidth/1920 als CSS-Custom-Property."""
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
    assert 'class="shell-fit"' in body, (
        "SHELL-12: Fit-Wrapper <div class=\"shell-fit\"> muss in heim-shell.html vorhanden sein"
    )
    # Scale-Script muss innerWidth/1920 berechnen
    assert "innerWidth / 1920" in body or "innerWidth/1920" in body, (
        "SHELL-12: Scale-Script muss window.innerWidth / 1920 als Berechnung enthalten"
    )
    # Custom-Property muss gesetzt werden
    assert "--shell-scale" in body, (
        "SHELL-12: Scale-Script muss --shell-scale als CSS-Custom-Property setzen"
    )


# ============================================================
#  T1603 — SW-Update-on-Boot + clients.claim
# ============================================================

def test_t1603_reg_update_bei_registrierung(client):
    """T1603: Shell-HTML ruft reg.update() nach erfolgreicher SW-Registrierung auf.

    Erzwingt eine SW-Update-Prüfung bei jedem Shell-Boot — ein einziger Reload
    nach Deploy reicht, um die neue SW-Version zu ziehen (update-on-boot).
    """
    body = client.get("/shell/" + PANEL_ID, headers=_OPERATOR_HEADERS).get_data(as_text=True)
    assert "reg.update()" in body, (
        "T1603: reg.update() muss nach der SW-Registrierung aufgerufen werden "
        "(update-on-boot — zieht neuen SW bei jedem Shell-Load)"
    )


def test_t1603_sw_clients_claim_in_activate():
    """T1603: shell/sw.js enthält self.clients.claim() im activate-Event.

    Sichert, dass der neue SW nach dem activate sofort alle offenen Clients
    übernimmt (kein Warten auf den nächsten Navigate-Request).
    """
    sw_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "shell", "sw.js",
    )
    with open(sw_path, encoding="utf-8") as fh:
        sw_src = fh.read()
    # clients.claim() muss im activate-Event stehen (nach 'activate'-Listener-Registrierung)
    activate_pos = sw_src.find("'activate'")
    assert activate_pos != -1, "T1603: 'activate'-Event-Listener fehlt in sw.js"
    claim_pos = sw_src.find("clients.claim()", activate_pos)
    assert claim_pos != -1, (
        "T1603: self.clients.claim() muss im activate-Event-Handler von sw.js stehen "
        "(sofortige Übernahme aller Clients nach SW-Aktivierung)"
    )


def test_t1603_shell_build_id_deckt_alle_quellen(monkeypatch, client):
    """T1603: shell-build_id aus ALLEN Shell-Assets — CSS + platform.js + sw.js + Template.

    Ein heim-shell.html-Bump (ohne CSS-Änderung) erzeugt eine andere build_id
    im gerenderten HTML — der Browser bekommt eine andere sw.js-URL und erkennt
    den neuen SW.
    """
    import seiten.pwa_mantel as _pm
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

    # Baseline: alle Quellen = mtime 100
    def fake_mtime_baseline(path):
        return 100.0

    monkeypatch.setattr(_pm.os.path, "getmtime", fake_mtime_baseline)
    build_id_baseline = _pm.build_id_for("shell", static_dir)

    # HTML-Template gebumpt: heim-shell.html neuer
    def fake_mtime_html_bumped(path):
        if path == os.path.join(templates_dir, "heim-shell.html"):
            return 500.0
        return 100.0

    monkeypatch.setattr(_pm.os.path, "getmtime", fake_mtime_html_bumped)
    build_id_bumped = _pm.build_id_for("shell", static_dir)

    assert build_id_bumped != build_id_baseline, (
        "T1603: heim-shell.html-Bump muss shell-build_id ändern — "
        f"baseline={build_id_baseline!r}, bumped={build_id_bumped!r}. "
        "REGISTRY['shell'].template_source_set muss 'heim-shell.html' tragen."
    )
    assert build_id_bumped == "500", (
        f"T1603: build_id nach HTML-Bump muss '500' sein, erhalten {build_id_bumped!r}"
    )


def test_shell12_css_transform_scale(client):
    """SHELL-12: heim-shell.css definiert .shell-fit mit transform: scale(var(--shell-scale)
    und transform-origin: top left."""
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "heim-shell.css",
    )
    with open(css_path, encoding="utf-8") as fh:
        css = fh.read()
    assert "transform: scale(var(--shell-scale" in css, (
        "SHELL-12: heim-shell.css muss transform: scale(var(--shell-scale...)) in .shell-fit definieren"
    )
    assert "transform-origin: top left" in css, (
        "SHELL-12: heim-shell.css muss transform-origin: top left in .shell-fit setzen"
    )
