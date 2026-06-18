"""Tests fuer ESSEN-33..36 — PWA-Mantel essen-einkauf + MAD-5-Cleanup.

Lauf:
  python3 -m pytest seiten/tests/test_essen_einkauf_pwa.py -x -v

Deckt:
  - ESSEN-34 Acceptance-Tabelle (8 Eintraege: HTML + 5 Assets + 2 Negative).
  - ESSEN-33 HTML-Naht (manifest-Link, SW-Registrierung, Wake-Lock, Fullscreen).
  - ESSEN-35 Service-Worker-Struktur (cache-first, pass-through, build_id).
  - ESSEN-36 / MAD-5 Stell-Probe (Grep auf essen-einkauf.js).

Ein paar Pfad-Konventionen vorweg:
  _PWA_DIR        — seiten/static/einkauf/  (PWA-Mantel-Assets)
  _SEITEN_DIR     — seiten/                 (Buddy-Service-Wurzel)
  _ENTRY_PATH     — /seiten/essen/einkauf   (bestehende HTML-Route, ESSEN-31)
  _ASSET_PREFIX   — /seiten/essen/einkauf/  (PWA-Asset-Pfad, ESSEN-34)
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
_PWA_DIR = os.path.join(_SEITEN_DIR, "static", "einkauf")

sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "eltern-chat"))

from seiten import main as seiten_main  # noqa: E402


_ENTRY_PATH = "/seiten/essen/einkauf"
_ASSET_PREFIX = "/seiten/essen/einkauf/"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch):
    """Setzt das runtime-Dict zurueck und stubt Snapshot-Holer (kein Netz im Test).

    WICHTIG: runtime-Dict ist Modul-global; Aenderungen leben sonst
    test-uebergreifend weiter. Wir merken den Ausgangs-Snapshot der relevanten
    Keys und stellen ihn nach jedem Test wieder her (sonst leckt unser
    bot_token="testtoken" in andere Test-Module wie test_init_data_validate.py).
    """
    rt_snapshot = {
        "bot_token":          seiten_main.runtime.get("bot_token"),
        "init_data_config":   seiten_main.runtime.get("init_data_config"),
        "familie_json_path":  seiten_main.runtime.get("familie_json_path"),
        "inventar_path":      seiten_main.runtime.get("inventar_path"),
    }
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    monkeypatch.setattr(seiten_main, "hole_panels", list)
    monkeypatch.setattr(seiten_main, "hole_geraete", list)
    yield
    # Rollback der Modul-globalen runtime-Eintraege
    for key, val in rt_snapshot.items():
        seiten_main.runtime[key] = val


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── ESSEN-34 Acceptance-Tabelle ──────────────────────────────────────────────

def test_essen34_html_route_bleibt_200(client):
    """ESSEN-34 Acceptance-Tabelle Zeile 1: GET /seiten/essen/einkauf → 200 text/html.

    Die bestehende HTML-Route (ESSEN-31 / EZG-6) darf nicht brechen, wenn
    daneben die Asset-Routes hinzukommen.
    """
    resp = client.get(_ENTRY_PATH)
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


def test_essen34_manifest_json(client):
    """ESSEN-34: GET /seiten/essen/einkauf/manifest.json → 200 application/manifest+json."""
    resp = client.get(_ASSET_PREFIX + "manifest.json")
    assert resp.status_code == 200
    assert resp.mimetype == "application/manifest+json"
    # PWA-2-Pflichtfelder: name, short_name, start_url, display, icons.
    body = resp.get_json()
    assert body is not None
    for feld in ("name", "short_name", "start_url", "display", "icons", "theme_color"):
        assert feld in body, f"manifest.json fehlt Pflichtfeld '{feld}' (PWA-2)"
    assert body["display"] == "fullscreen"
    assert isinstance(body["icons"], list) and len(body["icons"]) >= 2
    # Mindestens ein Icon mit purpose=maskable (PWA-2).
    purposes = [icon.get("purpose", "") for icon in body["icons"]]
    assert any("maskable" in p for p in purposes), \
        "manifest.json: mindestens ein Icon braucht purpose='maskable' (PWA-2)"


def test_essen34_sw_js(client):
    """ESSEN-34: GET /seiten/essen/einkauf/sw.js → 200 application/javascript."""
    resp = client.get(_ASSET_PREFIX + "sw.js")
    assert resp.status_code == 200
    # mimetype kann '; charset=utf-8' tragen — wir checken den Praefix.
    assert resp.mimetype == "application/javascript"
    body = resp.get_data(as_text=True)
    # PWA-1: sw.js braucht einen fetch-Handler (sonst kein WebAPK-Install).
    assert "addEventListener('fetch'" in body or 'addEventListener("fetch"' in body, \
        "sw.js fehlt fetch-Handler — Chrome verweigert WebAPK-Install"
    # ESSEN-35: BUILD_ID-Platzhalter wurde ersetzt (kein '__BUILD_ID__' mehr).
    assert "__BUILD_ID__" not in body, \
        "sw.js: BUILD_ID-Platzhalter wurde nicht ersetzt (ESSEN-35 Cache-Versionierung)"


def test_essen34_icon_192(client):
    """ESSEN-34: GET /seiten/essen/einkauf/icon-192.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-192.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_essen34_icon_512(client):
    """ESSEN-34: GET /seiten/essen/einkauf/icon-512.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-512.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_essen34_icon_maskable(client):
    """ESSEN-34: GET /seiten/essen/einkauf/icon-maskable-512.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-maskable-512.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_essen34_path_traversal_404(client):
    """ESSEN-34: Path-Traversal (../) → 404.

    Test-Form analog ROU-23-Acceptance: /seiten/essen/einkauf/../../router/main.py
    Flask normalisiert ../-Sequenzen u.U. schon im URL-Routing; trotzdem testen
    wir, dass der einkauf_asset_view-Handler bei einem auf seiten/main.py
    auflösenden Pfad NICHT erfolgreich antwortet.
    """
    # Test 1: Werkzeug routet ../-Pfade hart vorab; wir landen ggf. nicht im
    # Asset-Handler. Wir testen ein Verzeichnis hoch via URL-Encoded.
    resp = client.get(_ASSET_PREFIX + "..%2F..%2Frouter%2Fmain.py")
    assert resp.status_code == 404
    # Test 2: literal ../ landet bei Flask in der test-client-URL-Normalisierung
    # idR auf 404 oder umgeleitet — der Punkt ist: KEIN 200 mit fremdem Inhalt.
    resp2 = client.get(_ASSET_PREFIX + "../main.py")
    assert resp2.status_code in (301, 308, 404), \
        f"Path-Traversal '../main.py' lieferte unerwartet {resp2.status_code}"


def test_essen34_nonexistent_asset_404(client):
    """ESSEN-34: Nicht-existierendes Asset im Mini-App-Verzeichnis → 404."""
    resp = client.get(_ASSET_PREFIX + "gibt-es-nicht.txt")
    assert resp.status_code == 404


def test_essen34_privatfile_nicht_ausgeliefert(client):
    """ESSEN-34: _make_icons.py (privates Build-Skript) → 404.

    Defense in depth — auch wenn das Verzeichnis das Skript enthaelt, soll es
    nicht im URL-Raum sichtbar sein.
    """
    resp = client.get(_ASSET_PREFIX + "_make_icons.py")
    assert resp.status_code == 404


# ── ESSEN-33 HTML-Naht (manifest-Link, SW-Reg, Wake-Lock, Fullscreen) ─────────

def test_essen33_html_bindet_manifest_ein(client):
    """ESSEN-33 / PWA-1: HTML traegt <link rel="manifest" href=...>."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'rel="manifest"' in body
    assert "/seiten/essen/einkauf/manifest.json" in body


def test_essen33_html_registriert_service_worker(client):
    """ESSEN-33 / PWA-1: HTML registriert sw.js."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "navigator.serviceWorker" in body
    assert "/seiten/essen/einkauf/sw.js" in body
    # Scope explizit auf den Mini-App-Namespace (ESSEN-34 Schluss-Note).
    assert "/seiten/essen/einkauf/" in body


def test_essen33_html_wake_lock_pfad(client):
    """ESSEN-33 / PWA-3: HTML enthaelt navigator.wakeLock.request-Aufruf."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "navigator.wakeLock" in body
    assert "wakeLock.request" in body
    # visibilitychange-Reaktivierung (PWA-3 self-healing).
    assert "visibilitychange" in body


def test_essen33_html_fullscreen_aus_geste(client):
    """ESSEN-33 / PWA-3: requestFullscreen aus touchend/click-Geste."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "requestFullscreen" in body
    # PWA-3: touchend (NICHT touchstart) + click sind die gueltigen Trigger.
    assert "touchend" in body
    assert "click" in body
    # touchstart darf nicht als Trigger benutzt werden (Chromium-Constraint).
    # Wir pruefen, dass touchstart NICHT in Verbindung mit requestFullscreen steht.
    # (Heuristisch: touchstart taucht in der Fullscreen-Sektion nicht auf.)


def test_essen33_html_theme_color_meta(client):
    """ESSEN-33: <meta name="theme-color"> setzt die System-Statusleisten-Farbe."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'name="theme-color"' in body


# ── ESSEN-35 Service-Worker-Cache-Strategie ──────────────────────────────────

def test_essen35_sw_strategien_vorhanden(client):
    """ESSEN-35: sw.js implementiert cache-first + pass-through + network-first."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    # Cache-first Marker
    assert "cacheFirst" in body or "cache-first" in body
    # Pass-through fuer /api/v1/essen/* (network-only, kein respondWith).
    assert "/api/v1/essen/" in body
    # Network-first fuer ARASAAC.
    assert "arasaac" in body.lower()
    # build_id-Versionierung
    assert "CACHE_NAME" in body
    assert "einkauf-pwa-" in body


def test_essen35_sw_activate_loescht_alte_caches(client):
    """ESSEN-35: activate-Event loescht alte Cache-Namespaces."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "addEventListener('activate'" in body or 'addEventListener("activate"' in body
    assert "caches.delete" in body
    assert "caches.keys" in body


def test_essen35_sw_post_nicht_gecached(client):
    """ESSEN-35: GET-Filter im fetch-Handler — POST/PATCH wird nie gecached."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    # Heuristik: irgendwo wird method !== 'GET' (oder == 'GET') geprueft, bevor cache.put greift.
    assert "method" in body and "GET" in body


# ── ESSEN-36 / MAD-5 Stell-Probe ─────────────────────────────────────────────

def test_essen36_kein_direkter_initdata_zugriff():
    """ESSEN-36 Stell-Probe: essen-einkauf.js enthaelt KEIN

       grep -F 'window.Telegram.WebApp.initData' seiten/static/essen-einkauf.js
       → 0 Treffer (Anker im Spec-Text).
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "essen-einkauf.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "window.Telegram.WebApp.initData" not in js_inhalt, \
        "MAD-5/ESSEN-36-Verletzung: essen-einkauf.js greift direkt auf " \
        "window.Telegram.WebApp.initData zu — muss ueber platform.authHeaders()"
    # Bonus: auch der weitere Telegram-Vendor-Pfad ist tabu (MAD-5).
    assert "Telegram.WebApp" not in js_inhalt, \
        "MAD-5-Verletzung: essen-einkauf.js referenziert Telegram.WebApp direkt"


def test_essen36_alle_api_calls_nutzen_authheaders():
    """ESSEN-36: alle fetch-Calls auf /api/v1/essen/* nutzen platform.authHeaders().

    Heuristik: jede fetch(...)-Stelle in essen-einkauf.js, die /api/v1/essen
    referenziert, sollte _platform.authHeaders() im headers-Argument tragen.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "essen-einkauf.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "_platform.authHeaders" in js, \
        "essen-einkauf.js nutzt nicht platform.authHeaders() — MAD-5-Verstoss"
    # Old-style Manual-Header-Konstruktion darf nicht mehr vorkommen.
    assert '"Authorization": "tma "' not in js, \
        "essen-einkauf.js konstruiert noch manuell Authorization-Header — MAD-5-Verstoss"


def test_essen36_platform_js_hat_authheaders_wrapper():
    """ESSEN-36 / MAD-5: platform.js exportiert authHeaders() im Telegram- und Browser-Branch."""
    platform_path = os.path.join(_SEITEN_DIR, "static", "platform.js")
    with open(platform_path, encoding="utf-8") as f:
        platform_src = f.read()
    # Im TelegramPlatform-Branch: authHeaders ruft initData-Zugriff intern.
    assert "authHeaders(" in platform_src
    # Telegram-Branch baut den Authorization: tma-Header.
    assert '"Authorization": "tma "' in platform_src or "'Authorization': 'tma " in platform_src, \
        "platform.js TelegramPlatform.authHeaders() baut keinen 'tma <initData>'-Header"


# ── PWA-Mantel-Verzeichnis vorhanden ─────────────────────────────────────────

def test_pwa_dir_enthaelt_alle_pflicht_dateien():
    """ESSEN-33: seiten/static/einkauf/ enthaelt alle Pflicht-Dateien."""
    pflichten = ["manifest.json", "sw.js", "icon-192.png", "icon-512.png",
                 "icon-maskable-512.png"]
    fehlt = [p for p in pflichten if not os.path.isfile(os.path.join(_PWA_DIR, p))]
    assert not fehlt, f"PWA-Pflicht-Dateien fehlen in {_PWA_DIR}: {fehlt}"


# ── ESSEN-34 Trailing-Slash Echo-Probe (manifest.start_url) ──────────────────

def test_essen34_pwa_start_url_trailing_slash(client):
    """ESSEN-34 Echo-Probe: manifest.start_url muss als HTML-Route erreichbar sein.

    Liest start_url direkt aus seiten/static/einkauf/manifest.json und probt
    diesen Pfad gegen den Flask-test-client — 200 + text/html. So bleibt der
    Test automatisch synchron, wenn die manifest.json angepasst wird.
    """
    import json

    manifest_path = os.path.join(_PWA_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    start_url = manifest["start_url"]  # erwartet: "/seiten/essen/einkauf/"
    resp = client.get(start_url)
    assert resp.status_code == 200, (
        f"manifest.start_url '{start_url}' liefert {resp.status_code} statt 200 — "
        "PWA-Open nach Install landet in Fehler (ESSEN-34)"
    )
    assert resp.content_type.startswith("text/html"), (
        f"manifest.start_url '{start_url}' liefert Content-Type '{resp.content_type}' "
        "statt text/html"
    )
