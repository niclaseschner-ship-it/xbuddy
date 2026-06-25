"""Tests fuer PLAN-35 — Plan-Einstellungs-PWA (Mantel + Routen).

Spec-Anker: specs/buddies/plan.md PLAN-35 (P2: Eltern-Einstellungs-Seite,
PWA-Mantel). Surface: /seiten/plan/einstellungen.

Lauf:
  python3 -m pytest seiten/tests/test_plan_einstellungen_route.py -x -v

Deckt:
  - AC1: HTML-Route /seiten/plan/einstellungen + Trailing-Slash → 200 text/html.
  - AC1-ASSETS: manifest.json (200 + application/manifest+json) + sw.js (200 + JS).
  - AC1-MANTEL: manifest.json Pflichtfelder (PWA-2) + sw.js fetch-Handler.
  - AC3-PUBLIC: kein ensureAuth / authHeaders / initData / Authorization in plan-einstellungen.js.
  - AC4-PATH-TRAVERSAL: ../ → 404.
  - AC4-NONEXISTENT: nicht-existierendes Asset → 404.
  - AC_ENTRY: HTML traegt manifest-Link, SW-Registrierung, Hauptcontainer, Speichern-Btn.
  - ICONS-DIR: seiten/static/plan/ enthaelt alle Pflicht-Assets.

Entry-Path-Probe (AC_ENTRY):
  expected_entry_point = GET /seiten/plan/einstellungen → 200 text/html (PUBLIC).
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
_PLAN_ASSET_DIR = os.path.join(_SEITEN_DIR, "static", "plan")

sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

_ENTRY_PATH = "/seiten/plan/einstellungen"
_ASSET_PREFIX = "/seiten/plan/einstellungen/"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch):
    """Setzt runtime-Dict zurueck (analog test_essen_einkauf_pwa.py).

    Plan-Einstellungs-PWA ist PUBLIC — kein bot_token / init_data noetig.
    Wir setzen es trotzdem, damit andere Modul-globale Snapshots sauber bleiben.
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
    monkeypatch.setattr(seiten_main, "hole_panels", list)
    monkeypatch.setattr(seiten_main, "hole_geraete", list)
    yield
    for key, val in rt_snapshot.items():
        seiten_main.runtime[key] = val


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1: HTML-Route ───────────────────────────────────────────────────────────

def test_ac1_html_route_200(client):
    """AC1: GET /seiten/plan/einstellungen → 200 text/html (PUBLIC, kein Auth noetig)."""
    resp = client.get(_ENTRY_PATH)
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


def test_ac1_trailing_slash_200(client):
    """AC1 Trailing-Slash: GET /seiten/plan/einstellungen/ → 200 text/html.

    manifest.start_url = /seiten/plan/einstellungen/ — dieser Pfad muss
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
    assert "/seiten/plan/einstellungen" in inhalt, \
        "Route /seiten/plan/einstellungen fehlt in seiten/main.py"


# ── AC1-ASSETS: manifest.json + sw.js ────────────────────────────────────────

def test_ac1_manifest_json(client):
    """AC1-ASSETS: GET /seiten/plan/einstellungen/manifest.json → 200 application/manifest+json."""
    resp = client.get(_ASSET_PREFIX + "manifest.json")
    assert resp.status_code == 200
    assert resp.mimetype == "application/manifest+json"


def test_ac1_sw_js(client):
    """AC1-ASSETS: GET /seiten/plan/einstellungen/sw.js → 200 application/javascript."""
    resp = client.get(_ASSET_PREFIX + "sw.js")
    assert resp.status_code == 200
    assert resp.mimetype == "application/javascript"


def test_ac1_icon_192(client):
    """AC1-ASSETS: GET /seiten/plan/einstellungen/icon-192.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-192.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_ac1_icon_512(client):
    """AC1-ASSETS: GET /seiten/plan/einstellungen/icon-512.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-512.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


def test_ac1_icon_maskable(client):
    """AC1-ASSETS: GET /seiten/plan/einstellungen/icon-maskable-512.png → 200 image/png."""
    resp = client.get(_ASSET_PREFIX + "icon-maskable-512.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"


# ── AC1-MANTEL: manifest.json Inhalt + sw.js Struktur ────────────────────────

def test_ac1_manifest_pflichtfelder(client):
    """AC1-MANTEL / PWA-2: manifest.json enthaelt name/short_name/start_url/display/icons/theme_color."""
    body = client.get(_ASSET_PREFIX + "manifest.json").get_json()
    assert body is not None, "manifest.json ist kein gueltiges JSON"
    for feld in ("name", "short_name", "start_url", "display", "icons", "theme_color"):
        assert feld in body, f"manifest.json fehlt Pflichtfeld '{feld}' (PWA-2)"
    assert isinstance(body["icons"], list)
    assert len(body["icons"]) >= 2
    purposes = [icon.get("purpose", "") for icon in body["icons"]]
    assert any("maskable" in p for p in purposes), \
        "manifest.json: mindestens ein Icon braucht purpose='maskable' (PWA-2)"


def test_ac1_manifest_start_url_trailing_slash(client):
    """AC1-MANTEL: manifest.start_url endet auf '/' und ist als Route erreichbar."""
    import json as _json

    manifest_path = os.path.join(_PLAN_ASSET_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = _json.load(fh)

    start_url = manifest["start_url"]
    assert start_url.endswith("/"), "manifest.start_url muss auf '/' enden (PWA-Open-Pfad)"

    resp = client.get(start_url)
    assert resp.status_code == 200, (
        f"manifest.start_url '{start_url}' liefert {resp.status_code} statt 200 — "
        "PWA-Open nach Install landet in Fehler"
    )
    assert resp.content_type.startswith("text/html")


def test_ac1_sw_js_fetch_handler(client):
    """AC1-MANTEL / PWA-1: sw.js hat fetch-Handler (Chrome verweigert WebAPK-Install ohne)."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "addEventListener('fetch'" in body or 'addEventListener("fetch"' in body, \
        "sw.js fehlt fetch-Handler — Chrome verweigert WebAPK-Install"


def test_ac1_sw_js_build_id_ersetzt(client):
    """AC1-MANTEL / PLAN-35: sw.js hat keinen __BUILD_ID__-Platzhalter mehr (wurde ersetzt)."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "__BUILD_ID__" not in body, \
        "sw.js: BUILD_ID-Platzhalter wurde nicht ersetzt (Cache-Versionierung)"


def test_ac1_sw_js_activate_loescht_alte_caches(client):
    """AC1-MANTEL: sw.js activate-Event loescht alte Cache-Namespaces."""
    body = client.get(_ASSET_PREFIX + "sw.js").get_data(as_text=True)
    assert "addEventListener('activate'" in body or 'addEventListener("activate"' in body
    assert "caches.delete" in body
    assert "caches.keys" in body


# ── AC3-PUBLIC: kein Auth-Code in plan-einstellungen.js ─────────────────────

def test_ac3_public_kein_ensureauth():
    """AC3-PUBLIC: plan-einstellungen.js enthaelt kein ensureAuth / authHeaders / initData / Authorization.

    PLAN-35 Auth: PUBLIC / Netz-Trust. Die PWA laedt ohne Telegram-Kontext
    im externen Browser — kein Telegram-Auth-Code darf vorhanden sein.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "ensureAuth" not in js, \
        "ensureAuth gefunden in plan-einstellungen.js — AC3-PUBLIC verletzt"
    assert "authHeaders" not in js, \
        "authHeaders gefunden in plan-einstellungen.js — AC3-PUBLIC verletzt"
    assert "initData" not in js, \
        "initData gefunden in plan-einstellungen.js — AC3-PUBLIC verletzt"
    assert "Authorization" not in js, \
        "Authorization gefunden in plan-einstellungen.js — AC3-PUBLIC verletzt"


def test_ac3_public_kein_telegram_webapp():
    """AC3-PUBLIC: plan-einstellungen.js referenziert Telegram.WebApp nicht direkt."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "Telegram.WebApp" not in js, \
        "Telegram.WebApp gefunden in plan-einstellungen.js — AC3-PUBLIC / MAD-5-Verletzung"


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


# ── AC_ENTRY: HTML-Inhalt ────────────────────────────────────────────────────

def test_ac_entry_html_manifest_link(client):
    """AC_ENTRY / PWA-1: HTML traegt <link rel='manifest'>."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'rel="manifest"' in body
    assert "/seiten/plan/einstellungen/manifest.json" in body


def test_ac_entry_html_service_worker(client):
    """AC_ENTRY / PWA-1: HTML registriert sw.js mit Scope."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "navigator.serviceWorker" in body
    assert "/seiten/plan/einstellungen/sw.js" in body
    assert "/seiten/plan/einstellungen/" in body


def test_ac_entry_html_wake_lock(client):
    """AC_ENTRY / PWA-3: HTML enthaelt navigator.wakeLock.request."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "navigator.wakeLock" in body
    assert "wakeLock.request" in body
    assert "visibilitychange" in body


def test_ac_entry_html_fullscreen(client):
    """AC_ENTRY / PWA-3: HTML enthaelt requestFullscreen aus touchend/click."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "requestFullscreen" in body
    assert "touchend" in body
    assert "click" in body


def test_ac_entry_html_theme_color(client):
    """AC_ENTRY: HTML traegt <meta name='theme-color'>."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'name="theme-color"' in body


def test_ac_entry_html_slots_container(client):
    """AC_ENTRY: HTML traegt #slots-container (JS rendert Slot-Liste darin)."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'id="slots-container"' in body, \
        "#slots-container fehlt — Slot-Liste kann nicht gerendert werden"


def test_ac_entry_html_speichern_btn(client):
    """AC_ENTRY: HTML traegt #speichern-btn (sichtbarer Speichern-Knopf statt Telegram MainButton)."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'id="speichern-btn"' in body, \
        "#speichern-btn fehlt — Speichern-Button (kein Telegram MainButton) muss sichtbar sein"


def test_ac_entry_html_sheet_icon(client):
    """AC_ENTRY: HTML traegt #sheet-icon (ARASAAC-Such-Bottom-Sheet)."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'id="sheet-icon"' in body, \
        "#sheet-icon fehlt — ARASAAC-Icon-Picker-Sheet nicht vorhanden"


def test_ac_entry_html_sheet_person(client):
    """AC_ENTRY: HTML traegt #sheet-person (Personen-Picker-Sheet)."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'id="sheet-person"' in body, \
        "#sheet-person fehlt — Personen-Picker-Sheet nicht vorhanden"


def test_ac_entry_html_plan_einstellungen_js(client):
    """AC_ENTRY: HTML laedt plan-einstellungen.js."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "plan-einstellungen.js" in body, \
        "plan-einstellungen.js fehlt im Template"


def test_ac_entry_html_plan_einstellungen_css(client):
    """AC_ENTRY: HTML laedt plan-einstellungen.css."""
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert "plan-einstellungen.css" in body, \
        "plan-einstellungen.css fehlt im Template"


# ── ICONS-DIR: Pflicht-Dateien im seiten/static/plan/ Verzeichnis ────────────

def test_plan_asset_dir_pflicht_dateien():
    """ICONS-DIR: seiten/static/plan/ enthaelt alle Pflicht-Dateien."""
    pflichten = ["manifest.json", "sw.js", "icon-192.png", "icon-512.png",
                 "icon-maskable-512.png"]
    fehlt = [p for p in pflichten if not os.path.isfile(os.path.join(_PLAN_ASSET_DIR, p))]
    assert not fehlt, f"PWA-Pflicht-Dateien fehlen in {_PLAN_ASSET_DIR}: {fehlt}"


# ── JS-Struktur: API-Calls + Bottom-Sheets + Reorder ────────────────────────

def test_js_ruft_plan_defaults_api():
    """AC2: plan-einstellungen.js ruft /api/v1/plan/defaults."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "/api/v1/plan/defaults" in js, \
        "/api/v1/plan/defaults fehlt in plan-einstellungen.js (PLAN-36)"


def test_js_ruft_plan_slot_modell_api():
    """AC2: plan-einstellungen.js ruft /api/v1/plan/slot-modell."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "/api/v1/plan/slot-modell" in js, \
        "/api/v1/plan/slot-modell fehlt in plan-einstellungen.js (PLAN-37)"


def test_js_ruft_familie_personen_api():
    """AC2: plan-einstellungen.js ruft /api/v1/familie/personen."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "/api/v1/familie/personen" in js, \
        "/api/v1/familie/personen fehlt in plan-einstellungen.js (FAM-8)"


def test_js_ruft_icons_suche_api():
    """AC2: plan-einstellungen.js ruft /api/v1/icons/suche (ICONS-1)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "/api/v1/icons/suche" in js, \
        "/api/v1/icons/suche fehlt in plan-einstellungen.js (ICONS-1)"


def test_js_hat_pfeil_reorder():
    """AC2: plan-einstellungen.js implementiert ▲▼-Reorder (pfeil-hoch/pfeil-runter)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "pfeil-hoch" in js, "pfeil-hoch fehlt — ▲-Reorder nicht implementiert"
    assert "pfeil-runter" in js, "pfeil-runter fehlt — ▼-Reorder nicht implementiert"
    assert "bewegeSlot" in js, "bewegeSlot fehlt — Reorder-Logik nicht implementiert"


def test_js_hat_debounce_icon_suche():
    """AC2: plan-einstellungen.js nutzt Debounce fuer Icon-Suche (verhindert Race-Conditions)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "_debounceTimer" in js, "_debounceTimer fehlt — Debounce fuer Icon-Suche nicht implementiert"
    assert "setTimeout" in js, "setTimeout fehlt — Debounce nicht implementiert"


def test_js_hat_put_fuer_speichern():
    """AC2: plan-einstellungen.js nutzt PUT fuer Speichern (PLAN-36/37)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert '"PUT"' in js or "'PUT'" in js or "method: \"PUT\"" in js, \
        "PUT fehlt in plan-einstellungen.js — Speichern-Logik (PLAN-36/37) nicht implementiert"


# ── SREG-15: views.json-Registry-Eintrag ────────────────────────────────────

def test_sreg15_views_json_enthaelt_einstellungen():
    """SREG-15: seiten/views.json traegt slug 'einstellungen' mit typ 'pwa'.

    Eigentest BUD-3/SREG: der Eintrag muss in views.json vorhanden sein,
    damit GET /api/v1/seiten (Aggregator) die Plan-Einstellungs-PWA listet.
    """
    import json as _json

    views_path = os.path.join(_SEITEN_DIR, "views.json")
    with open(views_path, encoding="utf-8") as fh:
        data = _json.load(fh)

    views = data.get("views", [])
    slugs = {v.get("slug"): v for v in views if isinstance(v, dict)}
    assert "einstellungen" in slugs, \
        "seiten/views.json: slug 'einstellungen' fehlt (SREG-15)"
    eintrag = slugs["einstellungen"]
    assert eintrag.get("typ") == "pwa", \
        "seiten/views.json: einstellungen-Eintrag hat nicht typ='pwa' (SREG-15)"
    assert "pwa" in eintrag, \
        "seiten/views.json: einstellungen-Eintrag fehlt pwa-Block (SREG-15)"
    pwa = eintrag["pwa"]
    for feld in ("manifest", "start_url", "service_worker"):
        assert feld in pwa, \
            f"seiten/views.json: pwa.{feld} fehlt im einstellungen-Eintrag (SREG-15)"
    assert eintrag.get("auth") == "public", \
        "seiten/views.json: einstellungen-Eintrag hat nicht auth='public' (SREG-15)"


# ── PWA-2: manifest display=fullscreen ───────────────────────────────────────

def test_manifest_display_fullscreen(client):
    """PWA-2 (conventions/pwa.md): manifest.json muss display='fullscreen' haben.

    'standalone' ist ungenuegend — PWA-2 verlangt fullscreen fuer XBuddy-PWAs.
    """
    body = client.get(_ASSET_PREFIX + "manifest.json").get_json()
    assert body is not None, "manifest.json ist kein gueltiges JSON"
    assert body.get("display") == "fullscreen", (
        f"manifest.json: display='{body.get('display')}' statt 'fullscreen' (PWA-2)"
    )
