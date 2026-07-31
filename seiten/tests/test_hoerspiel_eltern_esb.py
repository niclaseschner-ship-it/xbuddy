"""Tests fuer T1681 — hoerspiel-eltern ESB-konform (ESB-1..4 / PWAM-5).

Spec-Anker: conventions/eltern-seite.md ESB-1..4. Surface: /seiten/hoerspiel/<kind_id>/eltern.

Lauf:
  python3 -m pytest seiten/tests/test_hoerspiel_eltern_esb.py -x -v

Deckt:
  - ESB-1 (PWAM-5): REGISTRY-Eintrag, HTML-Route 200, manifest.json, sw.js, Icons.
  - ESB-2: Verifizierungshinweis (grepped in analysis_plan — nicht hier getestet).
  - ESB-3: hoerspiel/views.json enthaelt Eintrag mit zielgruppe: eltern.
  - ESB-4: kein body-overflow:hidden in eltern.css.
  - AC_ENTRY: HTML traegt manifest-Link, SW-Registrierung, theme-color, __HSP_INSTANZEN__.

Entry-Path-Probe (AC_ENTRY):
  expected_entry_point = GET /seiten/hoerspiel/paula/eltern → 200 text/html.
"""

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
_HOERSPIEL_STATIC = os.path.join(_REPO_ROOT, "hoerspiel", "static")
_HOERSPIEL_VIEWS_JSON = os.path.join(_REPO_ROOT, "hoerspiel", "views.json")

sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import pwa_mantel  # noqa: E402

_KIND_ID = "paula"
_ENTRY_PATH = f"/seiten/hoerspiel/{_KIND_ID}/eltern"
_ASSET_PREFIX = f"/seiten/hoerspiel/{_KIND_ID}/eltern/"
_COMPONENT = "hoerspiel-eltern"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime():
    """Setzt runtime-Dict zurueck. HTML-Route ist public (MAD-7)."""
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


# ── ESB-1 / PWAM-5: REGISTRY ─────────────────────────────────────────────────

def test_registry_eintrag_vorhanden():
    """ESB-1 / PWAM-5: pwa_mantel.REGISTRY enthaelt 'hoerspiel-eltern' (T1681)."""
    assert _COMPONENT in pwa_mantel.REGISTRY, \
        f"REGISTRY['{_COMPONENT}'] fehlt — ESB-1 verletzt"


def test_registry_pflichtfelder():
    """ESB-1 / PWML-1: REGISTRY-Eintrag enthaelt alle PWML-1-Pflichtfelder."""
    cfg = pwa_mantel.REGISTRY[_COMPONENT]
    assert cfg.name, "name fehlt (PWML-1)"
    assert cfg.start_url, "start_url fehlt (PWML-1)"
    assert cfg.display, "display fehlt (PWML-1)"
    assert cfg.theme_color, "theme_color fehlt (PWML-1)"
    assert cfg.background_color, "background_color fehlt (PWML-1)"
    assert cfg.icons, "icons fehlt (PWAM-2)"
    assert cfg.sw_scope, "sw_scope fehlt (PWAM-3)"
    assert cfg.html_cache_mode, "html_cache_mode fehlt (PWAM-3)"
    assert cfg.build_id_source_set, "build_id_source_set fehlt (PWAM-4)"


def test_registry_sw_scope_deckt_alle_kind_ids():
    """ESB-1: sw_scope ist /seiten/hoerspiel/ — deckt alle kind_id-Pfade (T1681 scope-Form)."""
    cfg = pwa_mantel.REGISTRY[_COMPONENT]
    assert cfg.sw_scope == "/seiten/hoerspiel/", (
        f"sw_scope muss '/seiten/hoerspiel/' sein, ist: {cfg.sw_scope!r} "
        "(deckt alle kind_id-Instanzen)"
    )


# ── ESB-1: HTML-Route ─────────────────────────────────────────────────────────

def test_html_route_200(client):
    """ESB-1 / AC_ENTRY: GET /seiten/hoerspiel/<kind_id>/eltern → 200 text/html."""
    resp = client.get(_ENTRY_PATH)
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


def test_html_route_neko_200(client):
    """ESB-1: kind_id='neko' funktioniert auch (Route ist kind_id-generisch)."""
    resp = client.get("/seiten/hoerspiel/neko/eltern")
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


# ── ESB-1: manifest.json + sw.js + Icons ────────────────────────────────────

def test_manifest_json_200(client):
    """ESB-1 / PWML-1: GET .../eltern/manifest.json → 200 application/manifest+json."""
    resp = client.get(_ASSET_PREFIX + "manifest.json")
    assert resp.status_code == 200
    assert resp.mimetype == "application/manifest+json"


def test_manifest_json_pflichtfelder(client):
    """ESB-1 / PWML-1: manifest.json enthaelt name/short_name/start_url/display/icons/theme_color."""
    body = client.get(_ASSET_PREFIX + "manifest.json").get_json()
    assert body is not None, "manifest.json ist kein gueltiges JSON"
    for feld in ("name", "short_name", "start_url", "display", "icons", "theme_color"):
        assert feld in body, f"manifest.json fehlt Pflichtfeld '{feld}' (PWML-1)"
    assert isinstance(body["icons"], list)
    purposes = [icon.get("purpose", "") for icon in body["icons"]]
    assert any("maskable" in p for p in purposes), \
        "manifest.json: mindestens ein Icon braucht purpose='maskable' (PWAM-2)"


def test_manifest_lib_generiert():
    """ESB-1 / PWAM-5: kein manifest.json auf Platte in hoerspiel/static/ (Lib-generiert)."""
    static_manifest = os.path.join(_HOERSPIEL_STATIC, "manifest.json")
    assert not os.path.isfile(static_manifest), (
        "hoerspiel/static/manifest.json existiert — muss LIB-generiert sein (PWAM-5)"
    )


def test_sw_js_200(client):
    """ESB-1 / PWML-2: GET .../eltern/sw.js → 200 application/javascript."""
    resp = client.get(_ASSET_PREFIX + "sw.js")
    assert resp.status_code == 200
    assert resp.mimetype == "application/javascript"


def test_sw_js_fetch_handler(client):
    """ESB-1 / PWAM-3: sw.js hat fetch-Handler (Chrome verweigert WebAPK-Install ohne)."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "addEventListener('fetch'" in body or 'addEventListener("fetch"' in body, \
        "sw.js fehlt fetch-Handler — Chrome verweigert WebAPK-Install"


def test_sw_js_build_id_ersetzt(client):
    """ESB-1 / PWAM-4: sw.js hat keinen __BUILD_ID__-Platzhalter (wurde server-seitig ersetzt)."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "__BUILD_ID__" not in body, \
        "sw.js: BUILD_ID-Platzhalter wurde nicht ersetzt (Cache-Versionierung)"


def test_sw_js_service_worker_allowed_header(client):
    """ESB-1 / PWAM-3: sw.js-Route setzt Service-Worker-Allowed-Header."""
    resp = client.get(_ASSET_PREFIX + "sw.js")
    assert "Service-Worker-Allowed" in resp.headers, (
        "Service-Worker-Allowed-Header fehlt (PWAM-3)"
    )


def test_sw_js_lib_generiert():
    """ESB-1 / PWAM-5: kein sw.js auf Platte in hoerspiel/static/ fuer eltern (Lib-generiert)."""
    # Hinweis: hoerspiel/static/ enthaelt player.js, nicht einen Eltern-SW.
    eltern_sw = os.path.join(_HOERSPIEL_STATIC, "eltern-sw.js")
    assert not os.path.isfile(eltern_sw), (
        "hoerspiel/static/eltern-sw.js existiert — muss LIB-generiert sein (PWAM-5)"
    )


def test_icon_192_200(client):
    """ESB-1 / PWAM-2: GET .../eltern/icon-192.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-192.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_icon_512_200(client):
    """ESB-1 / PWAM-2: GET .../eltern/icon-512.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-512.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_icon_maskable_200(client):
    """ESB-1 / PWAM-2: GET .../eltern/icon-maskable-512.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-maskable-512.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_icons_in_hoerspiel_static():
    """ESB-1 / PWAM-2: hoerspiel/static/ enthaelt alle Pflicht-Icons (PNG 192/512/maskable)."""
    pflichten = ["icon-192.png", "icon-512.png", "icon-maskable-512.png"]
    fehlt = [p for p in pflichten if not os.path.isfile(os.path.join(_HOERSPIEL_STATIC, p))]
    assert not fehlt, f"PWA-Pflicht-Icons fehlen in hoerspiel/static/: {fehlt}"


# ── ESB-3: views.json ─────────────────────────────────────────────────────────

def test_views_json_eintrag_vorhanden():
    """ESB-3 / SREG-4: hoerspiel/views.json enthaelt Eintrag mit zielgruppe: eltern (T1681)."""
    with open(_HOERSPIEL_VIEWS_JSON, encoding="utf-8") as f:
        views = json.load(f)
    eltern_entries = [v for v in views["views"] if v.get("zielgruppe") == "eltern"]
    assert eltern_entries, (
        "hoerspiel/views.json hat keinen Eintrag mit zielgruppe: eltern (ESB-3 verletzt)"
    )


def test_views_json_eltern_typ_pwa():
    """ESB-3 / Heimat-Sub-Regel: eltern-Eintrag traegt typ: pwa (ESB-1 + ESB-3)."""
    with open(_HOERSPIEL_VIEWS_JSON, encoding="utf-8") as f:
        views = json.load(f)
    eltern_entries = [v for v in views["views"]
                      if v.get("zielgruppe") == "eltern" and v.get("slug") == "hoerspiel-eltern"]
    assert eltern_entries, "hoerspiel-eltern-Eintrag (slug) fehlt in hoerspiel/views.json"
    entry = eltern_entries[0]
    assert entry.get("typ") == "pwa", (
        f"hoerspiel-eltern views.json-Eintrag: typ muss 'pwa' sein, ist: {entry.get('typ')!r}"
    )


# ── ESB-4: scrollbar ──────────────────────────────────────────────────────────

def test_esb4_kein_body_overflow_hidden():
    """ESB-4: eltern.css enthaelt kein body { overflow: hidden } (scrollbar, nicht Kiosk)."""
    css_path = os.path.join(_HOERSPIEL_STATIC, "eltern.css")
    assert os.path.isfile(css_path), f"eltern.css nicht gefunden: {css_path}"
    with open(css_path, encoding="utf-8") as f:
        content = f.read()
    # Pruefe auf body-scoped overflow:hidden (PANEL-12-Sorte).
    # Text-overflow:hidden in Inline-Elementen ist erlaubt.
    # Naive Heuristik: 'body' und 'overflow: hidden' duerfen nicht im selben Block stehen.
    import re
    body_blocks = re.findall(r'body\s*\{[^}]*\}', content, re.DOTALL)
    for block in body_blocks:
        normalisiert = block.replace("overflow: hidden", "overflow:hidden")
        assert "overflow:hidden" not in normalisiert, (
            f"eltern.css: body-Block enthaelt overflow:hidden — ESB-4 verletzt (Kiosk-Sorte):\n{block}"
        )


# ── T1696: Scroll-Container-Guard (body traegt height:100dvh + overflow-y:auto) ──

def test_t1696_hoerspiel_eltern_css_body_scroll_container():
    """T1696: eltern.css body-Block traegt height:100dvh + overflow-y:auto.

    Telegram-Desktop/Android-WebView scrollt den frei wachsenden Body NICHT
    zuverlaessig (iOS schon). Der gebundene Scroll-Container (height:100dvh,
    overflow-y:auto) ist der verifizierte Fix (T1662-Muster, Nic-Verifikation
    #1662 Windows). Sonderfall eltern.css: min-height:100dvh wurde durch
    height:100dvh ersetzt (min-height laesst den Body frei wachsen = genau der Bug).
    Kinder-Kiosk ist unberuehrt (eigene Views, ESB-4/PANEL-12).
    """
    import re
    css_path = os.path.join(_HOERSPIEL_STATIC, "eltern.css")
    assert os.path.isfile(css_path), f"eltern.css nicht gefunden: {css_path}"
    with open(css_path, encoding="utf-8") as f:
        content = f.read()

    # Pruefe body-Block auf gebundenen Scroll-Container.
    body_blocks = re.findall(r'body\s*\{[^}]*\}', content, re.DOTALL)
    assert body_blocks, "eltern.css enthaelt keinen body-Block"

    combined = "\n".join(body_blocks)
    assert "height: 100dvh" in combined, (
        "eltern.css body-Block enthaelt kein 'height: 100dvh' "
        "— T1696 Scroll-Container-Guard verletzt (min-height waere der Scroll-Bug)"
    )
    assert "overflow-y: auto" in combined, (
        "eltern.css body-Block enthaelt kein 'overflow-y: auto' "
        "— T1696 Scroll-Container-Guard verletzt"
    )
    # Kein min-height als CSS-Property auf body (wuerde Body frei wachsen lassen = Scroll-Bug).
    # Kommentare werden entfernt, bevor geprueft wird.
    combined_no_comments = re.sub(r'/\*.*?\*/', '', combined, flags=re.DOTALL)
    assert "min-height" not in combined_no_comments, (
        "eltern.css body-Block enthaelt noch 'min-height' als CSS-Property "
        "— T1696 Scroll-Container-Guard verletzt (min-height laesst Body frei wachsen)"
    )


# ── AC_ENTRY: HTML-Inhalt ────────────────────────────────────────────────────

def test_ac_entry_manifest_link(client):
    """AC_ENTRY / ESB-1: HTML traegt <link rel='manifest'> auf kind_id-Pfad."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'rel="manifest"' in body
    assert f"/seiten/hoerspiel/{_KIND_ID}/eltern/manifest.json" in body


def test_ac_entry_service_worker(client):
    """AC_ENTRY / ESB-1: HTML registriert sw.js mit Scope."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "navigator.serviceWorker" in body
    assert f"/seiten/hoerspiel/{_KIND_ID}/eltern/sw.js" in body


def test_ac_entry_sw_scope(client):
    """AC_ENTRY / PWAM-3: SW-Registrierung nutzt sw_scope aus REGISTRY (/seiten/hoerspiel/)."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "/seiten/hoerspiel/" in body, (
        "sw_scope '/seiten/hoerspiel/' fehlt in HTML (SW kann kind_id-Pfad nicht kontrollieren)"
    )


def test_ac_entry_theme_color(client):
    """AC_ENTRY / PWML-1: HTML traegt <meta name='theme-color'>."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'name="theme-color"' in body


def test_ac_entry_hsp_instanzen(client):
    """AC_ENTRY / INST-1 (#1670): HTML enthaelt window.__HSP_INSTANZEN__ (server-injiziert)."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "window.__HSP_INSTANZEN__" in body, \
        "__HSP_INSTANZEN__ fehlt im Template (INST-1 / #1670)"


def test_ac_entry_eltern_js(client):
    """AC_ENTRY: HTML laedt eltern.js."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "eltern.js" in body, "eltern.js fehlt im Template"


# ── Path-Traversal-Guard ──────────────────────────────────────────────────────

def test_path_traversal_404(client):
    """Sicherheit: ../ → 404 (Traversal-Guard analog ESSEN-34)."""
    resp = client.get(_ASSET_PREFIX + "..%2F..%2Fmain.py")
    assert resp.status_code == 404
    resp2 = client.get(_ASSET_PREFIX + "../main.py")
    assert resp2.status_code in (301, 308, 404)


def test_nonexistent_asset_404(client):
    """Nicht-existierendes Asset → 404."""
    resp = client.get(_ASSET_PREFIX + "gibt-es-nicht.txt")
    assert resp.status_code == 404
