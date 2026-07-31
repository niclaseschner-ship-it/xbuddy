"""Tests fuer ROUTINE-23 / T1665 — Routine-Anpassen-PWA (Mantel + Routen).

Spec-Anker: specs/buddies/routine.md ROUTINE-20/23 (T1665: PWA-Sweep reduziert
auf routine). Surface: /seiten/routine/anpassen.

Lauf:
  python3 -m pytest seiten/tests/test_routine_anpassen_pwa.py -x -v

Deckt:
  - AC1: HTML-Route /seiten/routine/anpassen + Trailing-Slash → 200 text/html.
  - AC1-ASSETS: manifest.json (200 + application/manifest+json) + sw.js (200 + JS)
      + icon-*.png (200 image/png).
  - AC1-MANTEL: manifest.json Pflichtfelder (PWAM-2) + sw.js fetch-Handler.
  - AC4-PATH-TRAVERSAL: ../ → 404.
  - AC4-NONEXISTENT: nicht-existierendes Asset → 404.
  - AC_ENTRY: HTML traegt manifest-Link, SW-Registrierung, Hauptcontainer.
  - ICONS-DIR: seiten/static/routine/ enthaelt alle Pflicht-Icons.

Entry-Path-Probe (AC_ENTRY):
  expected_entry_point = GET /seiten/routine/anpassen → 200 text/html.
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
_ROUTINE_ASSET_DIR = os.path.join(_SEITEN_DIR, "static", "routine")

sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

_ENTRY_PATH = "/seiten/routine/anpassen"
_ASSET_PREFIX = "/seiten/routine/anpassen/"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch):
    """Setzt runtime-Dict zurueck (analog test_plan_einstellungen_route.py).

    Routine HTML-Route ist public (MAD-7: HTML laedt ohne Auth, JS macht ensureAuth).
    """
    rt_snapshot = {
        "bot_token":          seiten_main.runtime.get("bot_token"),
        "init_data_config":   seiten_main.runtime.get("init_data_config"),
        "familie_client":     seiten_main.runtime.get("familie_client"),
        "inventar_path":      seiten_main.runtime.get("inventar_path"),
    }
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    yield
    for key, val in rt_snapshot.items():
        seiten_main.runtime[key] = val


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1: HTML-Route ───────────────────────────────────────────────────────────

def test_ac1_html_route_200(client):
    """AC1: GET /seiten/routine/anpassen → 200 text/html."""
    resp = client.get(_ENTRY_PATH)
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


def test_ac1_trailing_slash_200(client):
    """AC1 Trailing-Slash: GET /seiten/routine/anpassen/ → 200 text/html.

    manifest.start_url = /seiten/routine/anpassen/ — dieser Pfad muss
    als HTML-Route erreichbar sein, sonst landet PWA-Open nach Install in 404.
    """
    resp = client.get(_ASSET_PREFIX)
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


def test_ac1_route_in_main_py():
    """AC1 / AC_ENTRY entry-path: Route ist in seiten/main.py implementiert."""
    main_path = os.path.join(_SEITEN_DIR, "main.py")
    with open(main_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "/seiten/routine/anpassen" in inhalt, \
        "Route /seiten/routine/anpassen fehlt in seiten/main.py"


# ── AC1-ASSETS: manifest.json + sw.js + Icons ────────────────────────────────

def test_ac1_manifest_json(client):
    """AC1-ASSETS: GET /seiten/routine/anpassen/manifest.json → 200 application/manifest+json."""
    resp = client.get(_ASSET_PREFIX + "manifest.json")
    assert resp.status_code == 200
    assert resp.mimetype == "application/manifest+json"


def test_ac1_sw_js(client):
    """AC1-ASSETS: GET /seiten/routine/anpassen/sw.js → 200 application/javascript."""
    resp = client.get(_ASSET_PREFIX + "sw.js")
    assert resp.status_code == 200
    assert resp.mimetype == "application/javascript"


def test_ac1_icon_192(client):
    """AC1-ASSETS: GET /seiten/routine/anpassen/icon-192.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-192.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_ac1_icon_512(client):
    """AC1-ASSETS: GET /seiten/routine/anpassen/icon-512.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-512.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_ac1_icon_maskable(client):
    """AC1-ASSETS: GET /seiten/routine/anpassen/icon-maskable-512.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-maskable-512.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


# ── AC1-MANTEL: manifest.json Inhalt + sw.js Struktur ────────────────────────

def test_ac1_manifest_pflichtfelder(client):
    """AC1-MANTEL / PWAM-2: manifest.json enthaelt name/short_name/start_url/display/icons/theme_color."""
    body = client.get(_ASSET_PREFIX + "manifest.json").get_json()
    assert body is not None, "manifest.json ist kein gueltiges JSON"
    for feld in ("name", "short_name", "start_url", "display", "icons", "theme_color"):
        assert feld in body, f"manifest.json fehlt Pflichtfeld '{feld}' (PWAM-2)"
    assert isinstance(body["icons"], list)
    assert len(body["icons"]) >= 2
    purposes = [icon.get("purpose", "") for icon in body["icons"]]
    assert any("maskable" in p for p in purposes), \
        "manifest.json: mindestens ein Icon braucht purpose='maskable' (PWAM-2)"


def test_ac1_manifest_start_url_trailing_slash(client):
    """AC1-MANTEL: manifest.start_url endet auf '/' und ist als Route erreichbar (PWAM-2)."""
    body = client.get(_ASSET_PREFIX + "manifest.json").get_json()
    assert body is not None, "manifest.json ist kein gueltiges JSON"
    start_url = body["start_url"]
    assert start_url.endswith("/"), "manifest.start_url muss auf '/' enden (PWA-Open-Pfad)"

    resp = client.get(start_url)
    assert resp.status_code == 200, (
        f"manifest.start_url '{start_url}' liefert {resp.status_code} statt 200 — "
        "PWA-Open nach Install landet in Fehler"
    )
    assert resp.content_type.startswith("text/html")


def test_ac1_manifest_display_fullscreen(client):
    """PWAM-2: manifest.json muss display='fullscreen' haben."""
    body = client.get(_ASSET_PREFIX + "manifest.json").get_json()
    assert body is not None, "manifest.json ist kein gueltiges JSON"
    assert body.get("display") == "fullscreen", (
        f"manifest.json: display='{body.get('display')}' statt 'fullscreen' (PWAM-2)"
    )


def test_ac1_manifest_lib_generiert(client):
    """AC1-MANTEL / PWAM-5: manifest.json ist LIB-generiert — kein manifest.json auf Platte.

    Kein statisches manifest.json in seiten/static/routine/ (Lib-generiert via
    pwa_mantel.build_manifest).
    """
    static_manifest = os.path.join(_ROUTINE_ASSET_DIR, "manifest.json")
    assert not os.path.isfile(static_manifest), (
        "seiten/static/routine/manifest.json existiert — soll LIB-generiert sein (PWAM-5)"
    )


def test_ac1_sw_js_fetch_handler(client):
    """AC1-MANTEL / PWAM-3: sw.js hat fetch-Handler (Chrome verweigert WebAPK-Install ohne)."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "addEventListener('fetch'" in body or 'addEventListener("fetch"' in body, \
        "sw.js fehlt fetch-Handler — Chrome verweigert WebAPK-Install"


def test_ac1_sw_js_build_id_ersetzt(client):
    """AC1-MANTEL / PWAM-4: sw.js hat keinen __BUILD_ID__-Platzhalter mehr (wurde ersetzt)."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "__BUILD_ID__" not in body, \
        "sw.js: BUILD_ID-Platzhalter wurde nicht ersetzt (Cache-Versionierung)"


def test_ac1_sw_js_activate_loescht_alte_caches(client):
    """AC1-MANTEL / PWAM-3: sw.js activate-Event loescht alte Cache-Namespaces."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "addEventListener('activate'" in body or 'addEventListener("activate"' in body
    assert "caches.delete" in body
    assert "caches.keys" in body


def test_ac1_sw_js_lib_generiert(client):
    """AC1-MANTEL / PWAM-5: sw.js ist LIB-generiert — kein sw.js auf Platte.

    Kein statisches sw.js in seiten/static/routine/ (Lib-generiert via
    pwa_mantel.render_sw).
    """
    static_sw = os.path.join(_ROUTINE_ASSET_DIR, "sw.js")
    assert not os.path.isfile(static_sw), (
        "seiten/static/routine/sw.js existiert — soll LIB-generiert sein (PWAM-5)"
    )


def test_ac1_sw_js_service_worker_allowed_header(client):
    """AC1-MANTEL / PWAM-3: sw.js-Route setzt Service-Worker-Allowed-Header."""
    resp = client.get(_ASSET_PREFIX + "sw.js")
    assert "Service-Worker-Allowed" in resp.headers, (
        "Service-Worker-Allowed-Header fehlt — SW kann start_url nicht kontrollieren (PWAM-3)"
    )


# ── AC4: Path-Traversal + 404 ────────────────────────────────────────────────

def test_ac4_path_traversal_404(client):
    """AC4 Path-Traversal: ../ → 404 (Defense in depth, analog ESSEN-34)."""
    resp = client.get(_ASSET_PREFIX + "..%2F..%2Frouter%2Fmain.py")
    assert resp.status_code == 404
    resp2 = client.get(_ASSET_PREFIX + "../main.py")
    assert resp2.status_code in (301, 308, 404)


def test_ac4_nonexistent_asset_404(client):
    """AC4 Nicht-existierendes Asset → 404."""
    resp = client.get(_ASSET_PREFIX + "gibt-es-nicht.txt")
    assert resp.status_code == 404


def test_ac4_private_asset_404(client):
    """AC4 Private Dateien (_*) → 404."""
    resp = client.get(_ASSET_PREFIX + "_make_icons.py")
    assert resp.status_code == 404


# ── AC_ENTRY: HTML-Inhalt ────────────────────────────────────────────────────

def test_ac_entry_html_manifest_link(client):
    """AC_ENTRY / PWAM-5: HTML traegt <link rel='manifest'> auf routine-Manifest-Route."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'rel="manifest"' in body
    assert "/seiten/routine/anpassen/manifest.json" in body


def test_ac_entry_html_service_worker(client):
    """AC_ENTRY / PWAM-3: HTML registriert sw.js mit Scope."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "navigator.serviceWorker" in body
    assert "/seiten/routine/anpassen/sw.js" in body


def test_ac_entry_html_sw_scope(client):
    """AC_ENTRY / PWAM-3: HTML-SW-Registrierung nutzt scope aus REGISTRY (nicht hartkodiert)."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    # sw_scope aus REGISTRY: /seiten/routine/anpassen/
    assert "/seiten/routine/anpassen/" in body


def test_ac_entry_html_theme_color(client):
    """AC_ENTRY / PWAM-2: HTML traegt <meta name='theme-color'>."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'name="theme-color"' in body


def test_ac_entry_html_hauptcontainer(client):
    """AC_ENTRY: HTML traegt #routine-inhalt (JS rendert Cards darin)."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'id="routine-inhalt"' in body, \
        "#routine-inhalt fehlt im Template"


def test_ac_entry_html_routine_anpassen_js(client):
    """AC_ENTRY: HTML laedt routine-anpassen.js."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "routine-anpassen.js" in body, \
        "routine-anpassen.js fehlt im Template"


def test_ac_entry_html_routine_anpassen_css(client):
    """AC_ENTRY: HTML laedt routine-anpassen.css."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "routine-anpassen.css" in body, \
        "routine-anpassen.css fehlt im Template"


# ── ICONS-DIR: Pflicht-Dateien in seiten/static/routine/ ─────────────────────

def test_routine_asset_dir_pflicht_icons():
    """ICONS-DIR: seiten/static/routine/ enthaelt alle Pflicht-Icons (PNG 192/512/maskable)."""
    pflichten = ["icon-192.png", "icon-512.png", "icon-maskable-512.png"]
    fehlt = [p for p in pflichten if not os.path.isfile(os.path.join(_ROUTINE_ASSET_DIR, p))]
    assert not fehlt, f"PWA-Pflicht-Icons fehlen in {_ROUTINE_ASSET_DIR}: {fehlt}"


def test_routine_asset_dir_kein_statisches_manifest():
    """ICONS-DIR: seiten/static/routine/ enthaelt KEIN manifest.json (Lib-generiert, PWAM-5)."""
    static_manifest = os.path.join(_ROUTINE_ASSET_DIR, "manifest.json")
    assert not os.path.isfile(static_manifest), (
        "manifest.json in seiten/static/routine/ — soll LIB-generiert sein, nicht auf Platte (PWAM-5)"
    )


def test_routine_asset_dir_kein_statisches_sw():
    """ICONS-DIR: seiten/static/routine/ enthaelt KEIN sw.js (Lib-generiert, PWAM-5)."""
    static_sw = os.path.join(_ROUTINE_ASSET_DIR, "sw.js")
    assert not os.path.isfile(static_sw), (
        "sw.js in seiten/static/routine/ — soll LIB-generiert sein, nicht auf Platte (PWAM-5)"
    )


# ── REGISTRY: PWAM-5-Vollstaendigkeit ────────────────────────────────────────

def test_registry_routine_vollstaendiger_eintrag():
    """PWAM-5: REGISTRY['routine'] traegt alle Pflicht-Manifest-Felder."""
    from seiten import pwa_mantel
    cfg = pwa_mantel.REGISTRY["routine"]
    assert cfg.name is not None, "REGISTRY['routine'].name fehlt (PWAM-2)"
    assert cfg.start_url is not None, "REGISTRY['routine'].start_url fehlt (PWAM-2)"
    assert cfg.display is not None, "REGISTRY['routine'].display fehlt (PWAM-2)"
    assert cfg.theme_color is not None, "REGISTRY['routine'].theme_color fehlt (PWAM-2)"
    assert cfg.background_color is not None, "REGISTRY['routine'].background_color fehlt (PWAM-2)"
    assert len(cfg.icons) >= 3, "REGISTRY['routine'].icons braucht mind. 3 Eintraege (192/512/maskable)"
    assert cfg.sw_script_route is not None, "REGISTRY['routine'].sw_script_route fehlt (PWAM-3)"
    assert cfg.sw_scope is not None, "REGISTRY['routine'].sw_scope fehlt (PWAM-3)"
    assert cfg.html_cache_mode is not None, "REGISTRY['routine'].html_cache_mode fehlt (PWAM-3)"
    assert len(cfg.build_id_source_set) >= 2, (
        "REGISTRY['routine'].build_id_source_set braucht mind. 2 Quellen (PWAM-4)"
    )


def test_registry_routine_build_manifest_valide():
    """PWAM-5: build_manifest(REGISTRY['routine']) produziert valides JSON ohne Fehler."""
    import json

    from seiten import pwa_mantel
    cfg = pwa_mantel.REGISTRY["routine"]
    manifest = pwa_mantel.build_manifest(cfg)
    assert isinstance(manifest, dict), "build_manifest() liefert kein dict"
    body = json.dumps(manifest)
    parsed = json.loads(body)
    assert parsed["name"] == cfg.name
    assert parsed["start_url"] == cfg.start_url


def test_registry_routine_render_sw_valide():
    """PWAM-5: render_sw('routine', build_id='test') produziert JS ohne __BUILD_ID__-Platzhalter."""
    from seiten import pwa_mantel
    js = pwa_mantel.render_sw("routine", build_id="test42")
    assert "__BUILD_ID__" not in js, "render_sw() hat __BUILD_ID__-Platzhalter nicht ersetzt"
    assert "test42" in js, "render_sw() hat build_id nicht eingesetzt"
    assert "addEventListener('fetch'" in js or 'addEventListener("fetch"' in js, \
        "render_sw() enthält keinen fetch-Handler"


# ── entry_path_probe — Echter Render-Pfad ────────────────────────────────────

def test_entry_path_probe_manifest_route(client):
    """entry_path_probe: /seiten/routine/anpassen/manifest.json liefert valides JSON mit Pflichtfeldern."""
    resp = client.get(_ASSET_PREFIX + "manifest.json")
    assert resp.status_code == 200, f"manifest-Route → {resp.status_code} (erwartet 200)"
    assert resp.mimetype == "application/manifest+json", \
        f"manifest-Route mimetype '{resp.mimetype}' (erwartet application/manifest+json)"
    body = resp.get_json()
    assert body is not None, "manifest-Route liefert kein valides JSON"
    assert "name" in body, "manifest.json fehlt 'name'"
    assert "start_url" in body, "manifest.json fehlt 'start_url'"
    assert "icons" in body, "manifest.json fehlt 'icons'"
    # entry_path_probe_result: route=/seiten/routine/anpassen/manifest.json
    # → 200 application/manifest+json, name='Morgenroutine anpassen · XBuddy',
    #   start_url='/seiten/routine/anpassen/', icons=[192/512/maskable vorhanden]


def test_entry_path_probe_sw_route(client):
    """entry_path_probe: /seiten/routine/anpassen/sw.js liefert JS."""
    resp = client.get(_ASSET_PREFIX + "sw.js")
    assert resp.status_code == 200, f"sw.js-Route → {resp.status_code} (erwartet 200)"
    assert resp.mimetype == "application/javascript", \
        f"sw.js-Route mimetype '{resp.mimetype}' (erwartet application/javascript)"
    body = resp.get_data(as_text=True)
    assert "fetch" in body, "sw.js-Route liefert keinen fetch-Handler"


def test_entry_path_probe_html_traegt_manifest_link(client):
    """entry_path_probe: GET /seiten/routine/anpassen → HTML traegt <link rel='manifest'>."""
    resp = client.get(_ENTRY_PATH)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'rel="manifest"' in body, "HTML traegt keinen <link rel='manifest'>"
    assert "/seiten/routine/anpassen/manifest.json" in body, \
        "manifest-href zeigt nicht auf /seiten/routine/anpassen/manifest.json"
    assert "serviceWorker" in body, "HTML registriert keinen Service-Worker"
