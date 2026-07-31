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
    """SREG-15 / ESB-3-Heimat: plan/views.json traegt slug 'einstellungen' mit typ 'pwa'.

    ESB-3-Heimat-Regel: plan-einstellungen gehoert in die Buddy-Heimat plan/views.json,
    nicht in seiten/views.json (T1680-Umbau). Eigentest BUD-3/SREG: der Eintrag muss in
    plan/views.json vorhanden sein, damit GET /api/v1/seiten (Aggregator) die
    Plan-Einstellungs-PWA als 'plan-einstellungen' listet.
    """
    import json as _json

    views_path = os.path.join(_REPO_ROOT, "plan", "views.json")
    with open(views_path, encoding="utf-8") as fh:
        data = _json.load(fh)

    views = data.get("views", [])
    slugs = {v.get("slug"): v for v in views if isinstance(v, dict)}
    assert "einstellungen" in slugs, \
        "plan/views.json: slug 'einstellungen' fehlt (SREG-15 / ESB-3-Heimat, T1680)"
    eintrag = slugs["einstellungen"]
    assert eintrag.get("typ") == "pwa", \
        "plan/views.json: einstellungen-Eintrag hat nicht typ='pwa' (SREG-15)"
    assert "pwa" in eintrag, \
        "plan/views.json: einstellungen-Eintrag fehlt pwa-Block (SREG-15)"
    pwa = eintrag["pwa"]
    for feld in ("manifest", "start_url", "service_worker"):
        assert feld in pwa, \
            f"plan/views.json: pwa.{feld} fehlt im einstellungen-Eintrag (SREG-15)"
    assert eintrag.get("auth") == "public", \
        "plan/views.json: einstellungen-Eintrag hat nicht auth='public' (SREG-15)"


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


# ── PLAN-37: kind-Feld-Vertrag (GET liest "kind", PUT sendet "kind") ──────────

def test_plan37_put_payload_sendet_kind_nicht_kind_id():
    """PLAN-37 Feld-Vertrag: PUT-Payload sendet 'kind', nicht 'kind_id' als Objekt-Key.

    Backend plan/config.py Slot.kind erwartet das Feld 'kind'.
    Wenn JS 'kind_id' als Key sendet, antwortet die API mit HTTP 400 (kalender-read-Slot
    braucht ein bekanntes kind) und Kind/Foto verschwindet.

    Gesucht: das slotsPayload-Objekt-Literal enthaelt 'kind:' (API-Key) und
    NICHT 'kind_id:' als API-Key (kind_id darf als interner Zugriff 'kind_id ||' vorkommen).
    """
    import re

    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    # Extrahiere den slotsPayload-Objekt-Block (der an speichereSlotModell geht)
    # Suche das Map-Objekt: "schluessel: s.schluessel" bis ende der Map-Funktion
    payload_match = re.search(
        r"(schluessel:\s*s\.schluessel.+?reihenfolge:\s*i\s*,?\s*\})",
        js,
        re.DOTALL,
    )
    assert payload_match, (
        "slotsPayload-Objekt-Block nicht gefunden — onSpeichern()-Struktur hat sich geaendert"
    )
    payload_block = payload_match.group(0)

    # Im Payload-Objekt muss "kind:" als Key stehen (API-Feld gemaess PLAN-37)
    assert re.search(r"\bkind\s*:", payload_block), (
        "slotsPayload sendet kein 'kind:'-Feld — Backend erwartet 'kind' (PLAN-37)"
    )

    # Im Payload-Objekt darf KEIN "kind_id:" als Key stehen (wuerde HTTP 400 provozieren)
    assert not re.search(r"\bkind_id\s*:", payload_block), (
        "slotsPayload sendet 'kind_id:' als Key — Backend erwartet 'kind', nicht 'kind_id' "
        "(PLAN-37: Feld-Vertrag verletzt → HTTP 400)"
    )


def test_plan37_get_liest_kind_feld():
    """PLAN-37 Feld-Vertrag: ladeSlotModell() mapped API-Feld 'kind' auf internes kind_id.

    Backend liefert im GET das Feld 'kind'. Ohne Mapping zeigen kalender-read-Slots
    'kein Kind', weil slot.kind_id undefined ist.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    # ladeSlotModell muss s.kind lesen (API-Rand-Mapping)
    assert "s.kind" in js, (
        "plan-einstellungen.js: ladeSlotModell() liest 's.kind' nicht — "
        "GET-Antwort von /api/v1/plan/slot-modell liefert 'kind', nicht 'kind_id' (PLAN-37)"
    )


# ── AC1: Freies Icon-Suchfeld im Anlege-Flow ─────────────────────────────────

def test_ac1_neu_icon_suche_input_im_html(client):
    """AC1: HTML traegt .neu-icon-suche-Input im sheet-neu-slot (freies Suchfeld).

    Benutzer muss 'kalender' suchen koennen, auch wenn Slot-Name 'Termine Niclas' ist.
    Das Suchfeld ist von .neu-label-input getrennt.
    """
    body = client.get(_ENTRY_PATH).get_data(as_text=True)
    assert 'class="neu-icon-suche"' in body or "neu-icon-suche" in body, (
        ".neu-icon-suche fehlt in plan-einstellungen.html (AC1: freies Suchfeld im Anlege-Flow)"
    )


def test_ac1_js_hat_neu_icon_suche_queryselector():
    """AC1: plan-einstellungen.js verdrahtet .neu-icon-suche (freies Suchfeld)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert ".neu-icon-suche" in js, (
        ".neu-icon-suche fehlt in plan-einstellungen.js — freies Suchfeld nicht verdrahtet (AC1)"
    )


def test_ac1_suche_entkoppelt_von_label():
    """AC1: Icon-Suche im Neu-Slot-Sheet ist nicht ausschliesslich an labelInput gebunden.

    Die Suchfunktion muss auch aus iconSucheInput ausgeloest werden koennen.
    Geprüft: sowohl 'neu-icon-suche' als auch unabhaengige Suchfunktion vorhanden.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    # Freies Suchfeld muss eigenen Event-Listener haben
    assert "iconSucheInput" in js, (
        "iconSucheInput fehlt — freies Suchfeld hat keinen eigenen Listener (AC1)"
    )
    # Label-Auto-Suche darf nur ausfuehren wenn Suche-Feld leer (Entkopplungs-Guard)
    assert "suchQ.length === 0" in js or 'suchQ === ""' in js or "suchQ.length == 0" in js, (
        "Entkopplungs-Guard fehlt — Label-Auto-Suche wird auch ausgefuehrt wenn Suche-Feld gefuellt (AC1)"
    )


# ── AC2: Label-Fallback ───────────────────────────────────────────────────────

def test_ac2_slot_label_funktion_vorhanden():
    """AC2: plan-einstellungen.js hat slotLabel()-Funktion fuer Fallback-Logik."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "function slotLabel(" in js, (
        "slotLabel() fehlt in plan-einstellungen.js (AC2: Fallback-Funktion)"
    )


def test_ac2_slot_label_fallback_bring():
    """AC2: slotLabel() liefert 'Bringen' fuer key='bring'."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert '"Bringen"' in js or "'Bringen'" in js, (
        "Fallback 'Bringen' fehlt in slotLabel() (AC2)"
    )


def test_ac2_slot_label_fallback_holen():
    """AC2: slotLabel() liefert 'Holen' fuer key='pick'."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert '"Holen"' in js or "'Holen'" in js, (
        "Fallback 'Holen' fehlt in slotLabel() (AC2)"
    )


def test_ac2_slot_label_fallback_kochen():
    """AC2: slotLabel() liefert 'Kochen' fuer key='cook'."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert '"Kochen"' in js or "'Kochen'" in js, (
        "Fallback 'Kochen' fehlt in slotLabel() (AC2)"
    )


def test_ac2_slot_label_fallback_bett():
    """AC2: slotLabel() hat Fallback-Logik fuer bed-Schluessen."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert '"Bett"' in js or "'Bett'" in js or "Bett" in js, (
        "Fallback 'Bett <Kind>' fehlt in slotLabel() (AC2)"
    )


def test_ac2_slot_label_fallback_termine():
    """AC2: slotLabel() hat Fallback-Logik fuer act-Schluessen (Termine <Kind>)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "Termine" in js, (
        "Fallback 'Termine <Kind>' fehlt in slotLabel() (AC2)"
    )


# ── AC3: Label-Edit fuer bestehende Slots ────────────────────────────────────

def test_ac3_slot_label_input_im_slot_body():
    """AC3: plan-einstellungen.js rendert .slot-label-input in Slot-Body (Label-Edit)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "slot-label-input" in js, (
        ".slot-label-input fehlt in plan-einstellungen.js — Label-Edit nicht implementiert (AC3)"
    )


def test_ac3_setze_slot_label_funktion():
    """AC3: plan-einstellungen.js hat setzeSlotLabel()-Funktion."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert "function setzeSlotLabel(" in js, (
        "setzeSlotLabel() fehlt in plan-einstellungen.js (AC3)"
    )


def test_ac3_label_input_change_listener():
    """AC3: plan-einstellungen.js hat change-Listener fuer .slot-label-input."""
    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    assert '"change"' in js or "'change'" in js, (
        "change-Listener fehlt — .slot-label-input-Aenderungen werden nicht getrackt (AC3)"
    )


# ── AC4: PWA-Icons sind Kalender (nicht Einkaufswagen) ───────────────────────

def test_ac4_plan_icons_verschieden_von_einkauf():
    """AC4: seiten/static/plan/ Icons unterscheiden sich von einkauf/ Icons (kein Copy-Paste)."""
    import hashlib

    from PIL import Image

    plan_dir   = os.path.join(_SEITEN_DIR, "static", "plan")
    einkauf_dir = os.path.join(_SEITEN_DIR, "static", "einkauf")

    for name in ("icon-192.png", "icon-512.png", "icon-maskable-512.png"):
        plan_path   = os.path.join(plan_dir, name)
        einkauf_path = os.path.join(einkauf_dir, name)

        assert os.path.isfile(plan_path), f"{name} fehlt in seiten/static/plan/"
        assert os.path.isfile(einkauf_path), f"{name} fehlt in seiten/static/einkauf/ (Referenz)"

        plan_img   = Image.open(plan_path)
        einkauf_img = Image.open(einkauf_path)

        h_plan   = hashlib.md5(plan_img.tobytes()).hexdigest()
        h_einkauf = hashlib.md5(einkauf_img.tobytes()).hexdigest()

        assert h_plan != h_einkauf, (
            f"{name}: Plan-Icon ist identisch mit Einkauf-Icon — "
            "Kalender-Motiv fehlt, Einkaufswagen-Copy wurde nicht ersetzt (AC4)"
        )


def test_ac4_make_icons_py_vorhanden():
    """AC4: seiten/static/plan/_make_icons.py existiert (Kalender-Icon-Generator)."""
    make_icons_path = os.path.join(_SEITEN_DIR, "static", "plan", "_make_icons.py")
    assert os.path.isfile(make_icons_path), (
        "_make_icons.py fehlt in seiten/static/plan/ — Icon-Generator nicht erstellt (AC4)"
    )


def test_ac4_make_icons_py_referenziert_kalender():
    """AC4: seiten/static/plan/_make_icons.py beschreibt Kalender-Motiv (kein Einkaufskorb)."""
    make_icons_path = os.path.join(_SEITEN_DIR, "static", "plan", "_make_icons.py")
    with open(make_icons_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "kalender" in inhalt.lower() or "calendar" in inhalt.lower(), (
        "_make_icons.py beschreibt kein Kalender-Motiv — Einkaufskorb-Code koennte kopiert sein (AC4)"
    )
    assert "einkauf" not in inhalt.lower(), (
        "_make_icons.py referenziert 'einkauf' — Einkaufswagen-Symbol statt Kalender (AC4)"
    )
    assert "einkaufskorb" not in inhalt.lower(), (
        "_make_icons.py referenziert 'einkaufskorb' — falsches Symbol (AC4)"
    )


# ── PLAN-1139-FIX1: Null-Guard im Anlege-Flow ───────────────────────────────

def test_fix1139_lege_slot_an_null_guard():
    """PLAN-1139-FIX1: legeSlotAn() hat Null-Guard — erzeugt nie icon='null'.

    Bug: legeSlotAn(label, art, null) lieferte icon='null' (String(null)),
    das zu /display/_shared/icons/arasaac/null.png (404) fuehrt und '?' anzeigt.
    Fix: defensiver Null-Guard bricht den Anlege-Pfad ab, bevor der falsche Wert
    in den Slot-State landet.
    """
    import re

    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    # legeSlotAn muss vor icon: String(iconId) einen Null-Guard haben.
    # Gesucht: eine Pruefung auf falsy/null/undefined vor der Slot-Erstellung.
    lege_fn_match = re.search(
        r"function legeSlotAn\s*\([^)]+\)\s*\{(.+?)^}",
        js,
        re.DOTALL | re.MULTILINE,
    )
    assert lege_fn_match, "legeSlotAn()-Funktion nicht gefunden"
    lege_body = lege_fn_match.group(1)

    # Null-Guard: return vor dem Slot-Anlegen wenn iconId fehlt
    assert "return" in lege_body, (
        "legeSlotAn() hat kein 'return' — Null-Guard-Abbruch fehlt (PLAN-1139-FIX1)"
    )
    assert "iconId" in lege_body or "icon" in lege_body.lower(), (
        "legeSlotAn() referenziert 'iconId' nicht — Null-Guard fuer Icon fehlt (PLAN-1139-FIX1)"
    )

    # Die Pruefung muss VOR dem neuerSlot-Objekt stehen (frueher Abbruch)
    guard_pos = lege_body.find("!iconId")
    slot_pos  = lege_body.find("neuerSlot")
    if guard_pos == -1:
        # Alternativer Guard-Pattern
        guard_pos = lege_body.find('"null"')
    assert guard_pos != -1, (
        "legeSlotAn(): kein Null-Guard mit '!iconId' oder '\"null\"'-Pruefung gefunden (PLAN-1139-FIX1)"
    )
    if slot_pos != -1:
        assert guard_pos < slot_pos, (
            "legeSlotAn(): Null-Guard steht NACH dem neuerSlot-Objekt — fruehzeitiger Abbruch fehlt"
        )


def test_fix1139_anlegen_btn_disabled_ohne_icon():
    """PLAN-1139-FIX1: aktualisiereAnlegenBtn() prueft auf echte Icon-ID (kein 'null'-String).

    Der Anlegen-Knopf darf nicht aktiv sein, wenn _pickerIconId den String 'null' traegt.
    """
    import re as _re

    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    # aktualisiereAnlegenBtn muss gegen "null"-String pruuefen
    fn_match = _re.search(
        r"function aktualisiereAnlegenBtn\s*\(\)\s*\{(.+?)^}",
        js,
        _re.DOTALL | _re.MULTILINE,
    )
    assert fn_match, "aktualisiereAnlegenBtn()-Funktion nicht gefunden"
    fn_body = fn_match.group(1)

    # Muss "null"-String-Pruefung enthalten
    assert '"null"' in fn_body or "'null'" in fn_body, (
        "aktualisiereAnlegenBtn() prueft nicht auf '\"null\"'-String — "
        "Anlegen-Button koennte bei kaputtem _pickerIconId aktiv sein (PLAN-1139-FIX1)"
    )


def test_fix1139_neu_icon_btn_click_guard():
    """PLAN-1139-FIX1: Icon-Klick im Neu-Slot-Sheet prueft dataset.iconId vor Setzen von _pickerIconId.

    Ein icon-pick-btn mit leerem/null dataset-Wert darf _pickerIconId nicht auf
    'null' oder '' setzen — sonst landet der kaputte Wert im Anlege-Flow.
    """
    import re as _re

    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    # Suche den neu-icon-btn click-Handler-Block
    click_match = _re.search(
        r'neu-icon-btn["\']?\s*\).*?_pickerIconId\s*=',
        js,
        _re.DOTALL,
    )
    assert click_match, (
        "neu-icon-btn click → _pickerIconId-Zuweisung nicht gefunden (PLAN-1139-FIX1)"
    )
    block = click_match.group(0)

    # Muss eine Pruefung auf rawId/null vor der Zuweisung haben
    assert "null" in block or "rawId" in block, (
        "neu-icon-btn click-Handler prueft dataset.iconId nicht auf null/leer (PLAN-1139-FIX1)"
    )


# ── PLAN-1139-FIX2: onSpeichern() save-race ─────────────────────────────────

def test_fix1139_save_race_sequenzielle_puts():
    """PLAN-1139-FIX2: onSpeichern() fuehrt speichereSlotModell + speichereDefaults SEQUENZIELL aus.

    Bug (4/12 Runs verlieren Daten): speichereSlotModell + speichereDefaults wurden
    mit Promise.all parallel gefeuert. Beide sind Read-Modify-Write auf dieselbe
    plan.json (Backend threaded=True) — der PUT mit Defaults liest manchmal den Stand
    VOR dem Slot-PUT und ueberschreibt die Slot-Aenderung (neue Slots verschwinden,
    geloeschte Slots kommen zurück).

    Fix: Beide PUTs SEQUENZIELL ausfuehren — erst speichereSlotModell, dann
    speichereDefaults. Die Regression-Pruefung stellt sicher, dass kein Promise.all
    die beiden Calls mehr bündelt und dass beide als separate awaits vorliegen.
    """
    import re

    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    # Suche die onSpeichern()-Funktion
    on_speichern_match = re.search(
        r"async function onSpeichern\s*\(\)\s*\{(.+?)^}",
        js,
        re.DOTALL | re.MULTILINE,
    )
    assert on_speichern_match, "onSpeichern()-Funktion nicht gefunden"
    on_speichern_body = on_speichern_match.group(1)

    # Regressionstest 1: kein Promise.all mit speichereSlotModell + speichereDefaults
    # (Promise.all wuerde wieder zur Race-Condition fuehren)
    promise_all_match = re.search(
        r"Promise\.all\s*\[\s*speichereSlotModell\s*\(",
        on_speichern_body,
        re.DOTALL,
    )
    assert not promise_all_match, (
        "onSpeichern(): Promise.all um speichereSlotModell gefunden — "
        "Save-Race-Fix wurde nicht angewendet oder revert-wurde (PLAN-1139-FIX2)"
    )

    # Regressionstest 2: speichereSlotModell mit await vorhanden
    assert re.search(
        r"await\s+speichereSlotModell\s*\(",
        on_speichern_body,
        re.DOTALL,
    ), (
        "onSpeichern(): 'await speichereSlotModell()' nicht gefunden — "
        "Sequenzielle Ausfuehrung nicht implementiert (PLAN-1139-FIX2)"
    )

    # Regressionstest 3: speichereDefaults mit await vorhanden (NACH speichereSlotModell)
    assert re.search(
        r"await\s+speichereDefaults\s*\(",
        on_speichern_body,
        re.DOTALL,
    ), (
        "onSpeichern(): 'await speichereDefaults()' nicht gefunden — "
        "Sequenzielle Ausfuehrung nicht implementiert (PLAN-1139-FIX2)"
    )


# ── PLAN-1139-FIX3: Anlegen-Handler speichert iconId VOR Schließen ────────────

def test_fix1139_anlegen_handler_reihenfolge():
    """PLAN-1139-FIX3: Anlegen-Handler sichert iconId BEVOR schliesseNeuSlotSheet() ihn nullt.

    Bug (PLAN-1139 Hauptursache): im Anlegen-Click-Handler wurde schliesseNeuSlotSheet()
    vor legeSlotAn() aufgerufen — aber schliesseNeuSlotSheet() nullt _pickerIconId (Zeile 461).
    Folge: legeSlotAn() erhielt null statt der echten Icon-ID → Anlegen abgebrochen.

    Fix: _pickerIconId wird in einer lokalen Konstante `iconId` GEFANGEN, BEVOR das Sheet
    geschlossen wird. legeSlotAn() erhält dann diese lokale Konstante, nicht das nullte Global.

    Regression-Schutz: der Test verifiziert die Reihenfolge:
    1. const iconId = _pickerIconId    ← Gefängnis BEVOR schliesse…()
    2. schliesseNeuSlotSheet()
    3. legeSlotAn(label, art, iconId)  ← lokale Variable, nicht global
    """
    import re

    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    # Suche den Anlegen-Button-Click-Handler im neuSlotSheet-Click-Listener
    anlegen_match = re.search(
        r'if\s*\(\s*e\.target\.closest\s*\(\s*["\']\.neu-slot-anlegen["\']\s*\)\s*\)\s*\{(.+?)^\s*\}',
        js,
        re.DOTALL | re.MULTILINE,
    )
    assert anlegen_match, (
        "Anlegen-Handler (.neu-slot-anlegen) nicht gefunden — Test-Struktur hat sich geaendert"
    )
    handler_body = anlegen_match.group(1)

    # Verifikation 1: eine lokale `iconId`-Konstante wird gesetzt
    assert re.search(r"const\s+iconId\s*=\s*_pickerIconId", handler_body), (
        "Anlegen-Handler: 'const iconId = _pickerIconId' nicht gefunden — "
        "Icon wird nicht in lokale Variable gesichert (PLAN-1139-FIX3)"
    )

    # Verifikation 2: schliesseNeuSlotSheet() wird aufgerufen
    assert "schliesseNeuSlotSheet()" in handler_body, (
        "Anlegen-Handler: 'schliesseNeuSlotSheet()' nicht gefunden — "
        "Handler-Struktur hat sich geaendert (PLAN-1139-FIX3)"
    )

    # Verifikation 3: legeSlotAn() wird mit der lokalen iconId aufgerufen
    assert re.search(r"legeSlotAn\s*\(\s*label\s*,\s*art\s*,\s*iconId\s*\)", handler_body), (
        "Anlegen-Handler: legeSlotAn(label, art, iconId) nicht gefunden — "
        "Icon wird nicht von der gesicherten Konstante gelesen (PLAN-1139-FIX3)"
    )

    # Verifikation 4: Reihenfolge-Check — const iconId vor schliesseNeuSlotSheet vor legeSlotAn
    iconid_pos = handler_body.find("const iconId")
    schliesse_pos = handler_body.find("schliesseNeuSlotSheet()")
    lege_pos = handler_body.find("legeSlotAn(")

    assert iconid_pos != -1, (
        "Anlegen-Handler: 'const iconId' nicht gefunden"
    )
    assert schliesse_pos != -1, (
        "Anlegen-Handler: 'schliesseNeuSlotSheet()' nicht gefunden"
    )
    assert lege_pos != -1, (
        "Anlegen-Handler: 'legeSlotAn(' nicht gefunden"
    )
    assert iconid_pos < schliesse_pos < lege_pos, (
        "Anlegen-Handler: falsche Reihenfolge — "
        f"const iconId ({iconid_pos}) muss VOR schliesseNeuSlotSheet ({schliesse_pos}) "
        f"kommen, und beide VOR legeSlotAn ({lege_pos}) (PLAN-1139-FIX3 Regression-Schutz)"
    )


# ── PLAN-1139-FIX4: Icon-Picker speichert iconId VOR Schließen ───────────────

def test_fix1139_icon_picker_reihenfolge():
    """PLAN-1139-FIX4: Icon-Picker-Click-Handler sichert iconId BEVOR schliesseIconPicker() ihn nullt.

    Bug (PLAN-1139 Icon-Änderung bei bestehenden Slots): im Icon-Picker-Click-Handler
    wurde schliesseIconPicker() aufgerufen, bevor das Callback die Icon-ID las — aber
    schliesseIconPicker() nullt _pickerIconId (Zeile 337). Folge: callback(null) →
    setzeSlotIcon(slotKey, null) → Null-Guard greift → Icon ändert sich NICHT.

    Fix: _pickerIconId wird in einer lokalen Konstante `iconId` GEFANGEN, BEVOR das Sheet
    geschlossen wird. Das Callback erhält dann diese lokale Konstante, nicht das nullte Global.

    Regression-Schutz: der Test verifiziert die Reihenfolge:
    1. const iconId = btn.dataset.iconId    ← Gefängnis BEVOR schließen
    2. schliesseIconPicker()
    3. kontext.callback(iconId)             ← lokale Variable, nicht global
    """
    import re

    js_path = os.path.join(_SEITEN_DIR, "static", "plan-einstellungen.js")
    with open(js_path, encoding="utf-8") as f:
        js = f.read()

    # Suche den Icon-Grid-Click-Handler (sheet-icon Handler)
    icon_picker_match = re.search(
        r'iconGrid\.addEventListener\s*\(\s*["\']click["\']\s*,\s*\(\s*e\s*\)\s*=>\s*\{(.+?)^\s*\}\s*\);',
        js,
        re.DOTALL | re.MULTILINE,
    )
    assert icon_picker_match, (
        "Icon-Picker-Click-Handler (iconGrid) nicht gefunden — Test-Struktur hat sich geaendert"
    )
    handler_body = icon_picker_match.group(1)

    # Verifikation 1: eine lokale `iconId`-Konstante wird gesetzt
    assert re.search(r"const\s+iconId\s*=\s*btn\.dataset\.iconId", handler_body), (
        "Icon-Picker-Handler: 'const iconId = btn.dataset.iconId' nicht gefunden — "
        "Icon wird nicht in lokale Variable gesichert (PLAN-1139-FIX4)"
    )

    # Verifikation 2: schliesseIconPicker() wird aufgerufen
    assert "schliesseIconPicker()" in handler_body, (
        "Icon-Picker-Handler: 'schliesseIconPicker()' nicht gefunden — "
        "Handler-Struktur hat sich geaendert (PLAN-1139-FIX4)"
    )

    # Verifikation 3: callback wird mit der lokalen iconId aufgerufen
    assert re.search(r"kontext\.callback\s*\(\s*iconId\s*\)", handler_body), (
        "Icon-Picker-Handler: 'kontext.callback(iconId)' nicht gefunden — "
        "Icon wird nicht von der gesicherten Konstante gelesen (PLAN-1139-FIX4)"
    )

    # Verifikation 4: Reihenfolge-Check — const iconId vor schliesseIconPicker vor callback
    iconid_pos = handler_body.find("const iconId")
    schliesse_pos = handler_body.find("schliesseIconPicker()")
    callback_pos = handler_body.find("kontext.callback(")

    assert iconid_pos != -1, (
        "Icon-Picker-Handler: 'const iconId' nicht gefunden"
    )
    assert schliesse_pos != -1, (
        "Icon-Picker-Handler: 'schliesseIconPicker()' nicht gefunden"
    )
    assert callback_pos != -1, (
        "Icon-Picker-Handler: 'kontext.callback(' nicht gefunden"
    )
    assert iconid_pos < schliesse_pos < callback_pos, (
        "Icon-Picker-Handler: falsche Reihenfolge — "
        f"const iconId ({iconid_pos}) muss VOR schliesseIconPicker ({schliesse_pos}) "
        f"kommen, und beide VOR kontext.callback ({callback_pos}) (PLAN-1139-FIX4 Regression-Schutz)"
    )
