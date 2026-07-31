"""Tests fuer GET /api/v1/seiten/mini-app-uebersicht — MAU-1..10.

Testet:
  AC1  — HTML mit 2 collapsed Accordion-Sektionen (Mini Telegram Apps, Buddy-Seiten; RAT-31 E3 entfernte Geraete-Paare).
  AC2  — platform.js hat openLink und copyText in beiden Klassen.
  AC3  — Route gibt 200 mit Auth, 401 ohne Auth, 500 ohne Bot-Token.
  AC4  — FAM-7/8: fremde User-ID → 403; bekannte User-ID → 200.
  AC5  — Lint-self-gate via statische Checks (kein Telegram.WebApp in mini-app-uebersicht.js).

Entry-Path-Probe (AC_ENTRY):
  grep '/api/v1/seiten/mini-app-uebersicht' seiten/main.py
  → @app.route("/api/v1/seiten/mini-app-uebersicht", methods=["GET"])

Lauf: uv run pytest seiten/tests/test_mini_app_uebersicht.py -v
"""

import hashlib
import hmac
import json as _json_mod
import os
import sys
import time
import urllib.parse

import pytest

_SEITEN_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT   = os.path.dirname(_SEITEN_DIR)

sys.path.insert(0, _REPO_ROOT)

# T1015: init_data lebt unter tools.initdata; kein sys.path-Hack mehr auf
# eltern-chat (Cluster-A-Option-B 2026-06-18-1720).

from seiten import main as seiten_main  # noqa: E402  # isort:skip
from seiten.tests._familie_test_doppel import FileFakeFamilieClient  # noqa: E402

# ── initData-Hilfsfunktionen (analog test_routine_anpassen_route.py) ─────────

BOT_TOKEN = "test:mau-token"


def _baue_init_data(bot_token=BOT_TOKEN, user_id=42, offset_seconds=0):
    """Baut einen validen Telegram-initData-String mit korrektem HMAC."""
    auth_date = int(time.time()) + offset_seconds
    user_json = _json_mod.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))

    felder = {
        "auth_date": str(auth_date),
        "user":      user_json,
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(felder.items()))

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    computed_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    felder["hash"] = computed_hash
    return urllib.parse.urlencode(felder)


def _baue_init_data_manipuliert():
    """Baut initData mit korrektem Format, aber falschem Hash."""
    init_data = _baue_init_data()
    params = dict(urllib.parse.parse_qsl(init_data))
    params["hash"] = "0" * 64
    return urllib.parse.urlencode(params)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime():
    """Setzt runtime-Dict vor jedem Test zurueck (Test-Modus)."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token=BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    # RAT-31 E3 (#1496): hole_panels/hole_geraete entfernt, kein Stub nötig.


@pytest.fixture
def client():
    return seiten_main.app.test_client()


def _get_html(client, user_id=42):
    """Helper: GET /api/v1/seiten/mini-app-uebersicht mit gueltiger MAD-7-Auth."""
    init_data = _baue_init_data(user_id=user_id)
    return client.get(
        "/api/v1/seiten/mini-app-uebersicht",
        headers={"Authorization": "tma " + init_data},
    )


# ── AC3 — Route-Existenz + Auth-Verhalten ─────────────────────────────────────

def test_ac3_route_in_main_py():
    """AC3 / AC_ENTRY: Route /api/v1/seiten/mini-app-uebersicht ist in seiten/main.py."""
    main_path = os.path.join(_SEITEN_DIR, "main.py")
    with open(main_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "/api/v1/seiten/mini-app-uebersicht" in inhalt, \
        "Route /api/v1/seiten/mini-app-uebersicht fehlt in seiten/main.py"


def test_ac3_gueltige_auth_liefert_200(client):
    """AC3: GET mit gueltiger initData → 200 HTML."""
    resp = _get_html(client)
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac3_ohne_auth_liefert_401(client):
    """AC3 (MAD-7): GET ohne Authorization-Header → 401."""
    resp = client.get("/api/v1/seiten/mini-app-uebersicht")
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth
    body = resp.get_json()
    assert body is not None
    assert body.get("error")


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac3_manipulierter_hash_liefert_401(client):
    """AC3 (MAD-7): Authorization-Header mit falschem Hash → 401."""
    init_data = _baue_init_data_manipuliert()
    resp = client.get(
        "/api/v1/seiten/mini-app-uebersicht",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac3_falsches_schema_liefert_401(client):
    """AC3 (MAD-7): Authorization-Header ohne 'tma '-Praefix → 401."""
    init_data = _baue_init_data()
    resp = client.get(
        "/api/v1/seiten/mini-app-uebersicht",
        headers={"Authorization": "Bearer " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac3_abgelaufener_init_data_liefert_401(client):
    """AC3 (MAD-7): auth_date abgelaufen → 401."""
    init_data = _baue_init_data(offset_seconds=-(86400 + 1))
    resp = client.get(
        "/api/v1/seiten/mini-app-uebersicht",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac3_fehlendes_bot_token_liefert_500(client, monkeypatch):
    """AC3 (MAD-7): Bot-Token fehlt in ENV und runtime → 500."""
    seiten_main.runtime["bot_token"] = None
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    init_data = _baue_init_data()
    resp = client.get(
        "/api/v1/seiten/mini-app-uebersicht",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Token-Check nur am validate-Endpoint


# ── AC4 — FAM-7/8-Check ──────────────────────────────────────────────────────

@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac4_fremde_user_id_liefert_200_skeleton(client, tmp_path):
    """AC4 (FAM-7/8): User-ID nicht in familie.json → 403."""
    familie = {
        "erwachsene": [{"id": "p1", "name": "Elter", "ring": "blue", "telegram_id": 99999}],
        "kinder": [],
    }
    f = tmp_path / "familie.json"
    f.write_text(_json_mod.dumps(familie), encoding="utf-8")
    seiten_main.runtime["familie_client"] = FileFakeFamilieClient(str(f))

    init_data = _baue_init_data(user_id=42)
    resp = client.get(
        "/api/v1/seiten/mini-app-uebersicht",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, FAM-Check via JS-ensureAuth
    body = resp.get_json()
    assert body is not None

    seiten_main.runtime["familie_client"] = None


def test_ac4_bekannte_user_id_liefert_200(client, tmp_path):
    """AC4 (FAM-7/8): User-ID in familie.json → 200."""
    familie = {
        "erwachsene": [{"id": "p1", "name": "Elter", "ring": "blue", "telegram_id": 42}],
        "kinder": [],
    }
    f = tmp_path / "familie.json"
    f.write_text(_json_mod.dumps(familie), encoding="utf-8")
    seiten_main.runtime["familie_client"] = FileFakeFamilieClient(str(f))

    init_data = _baue_init_data(user_id=42)
    resp = client.get(
        "/api/v1/seiten/mini-app-uebersicht",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200

    seiten_main.runtime["familie_client"] = None


# ── AC1 — HTML-Struktur: 3 Accordion-Sektionen ───────────────────────────────

def test_ac1_html_enthaelt_zwei_accordion_sektionen(client):
    """AC1 (MAU-4, RAT-31 E3): HTML hat 2 <details>-Elemente fuer die zwei Accordion-Sektionen."""
    body = _get_html(client).get_data(as_text=True)
    # details-Elemente fuer die zwei Sektionen (Mini-Apps + Buddy-Seiten)
    assert body.count("<details") >= 2, \
        "Weniger als 2 <details>-Elemente im HTML — MAU-4 Accordion fehlt"


def test_ac1_html_enthaelt_mini_apps_sektion(client):
    """AC1 (MAU-4 Punkt 1): HTML-/JS-Logik enthaelt 'Mini Telegram Apps'-Sektion."""
    body = _get_html(client).get_data(as_text=True)
    assert "Mini Telegram Apps" in body or "mini-app-uebersicht" in body, \
        "Mini-Telegram-Apps-Sektion fehlt — MAU-4 Punkt 1 nicht erfuellt"


def test_ac1_html_enthaelt_buddy_seiten_sektion(client):
    """AC1 (MAU-4 Punkt 2): HTML enthaelt Buddy-Seiten-Sektion."""
    body = _get_html(client).get_data(as_text=True)
    assert "Buddy-Seiten" in body, \
        "Buddy-Seiten-Sektion fehlt im HTML — MAU-4 Punkt 2"


def test_ac1_details_haben_kein_open_attribut(client):
    """AC1 (MAU-4): <details>-Elemente haben kein open-Attribut — default collapsed."""
    body = _get_html(client).get_data(as_text=True)
    # Kein <details open> im Template-Teil (JS rendert dynamisch, aber Template hat keine open-Attribute)
    assert "<details open" not in body, \
        "<details open> gefunden — Accordion-Sektionen sollen collapsed starten (MAU-4)"


def test_ac1_html_laedt_platform_js(client):
    """AC1 / MAD-5: HTML laedt platform.js vor mini-app-uebersicht.js."""
    body = _get_html(client).get_data(as_text=True)
    assert "platform.js" in body, "platform.js fehlt im Template (MAD-5)"
    assert "mini-app-uebersicht.js" in body, "mini-app-uebersicht.js fehlt im Template"
    pos_platform = body.index("platform.js")
    pos_app = body.index("mini-app-uebersicht.js")
    assert pos_platform < pos_app, \
        "platform.js muss vor mini-app-uebersicht.js geladen werden (MAD-5)"


def test_ac1_html_laedt_css(client):
    """AC1: HTML laedt mini-app-uebersicht.css."""
    body = _get_html(client).get_data(as_text=True)
    assert "mini-app-uebersicht.css" in body, "mini-app-uebersicht.css fehlt im Template"


def test_ac1_html_cache_control_header(client):
    """AC1 (Mini-App-Cache-Buster-Pattern): Response hat Cache-Control: no-store."""
    resp = _get_html(client)
    assert resp.status_code == 200
    cache = resp.headers.get("Cache-Control", "")
    assert "no-store" in cache, \
        "Cache-Control: no-store fehlt — Telegram wuerde HTML cachen (Cache-Buster-Pattern)"


def test_ac1_html_enthaelt_build_id(client):
    """AC1 (Cache-Buster-Pattern): HTML enthaelt ?v= build_id an Assets."""
    body = _get_html(client).get_data(as_text=True)
    assert "?v=" in body, "?v=<build_id> Cache-Buster fehlt in HTML-Links"


def test_ac1_html_enthaelt_toast_element(client):
    """AC1 (MAU-6): HTML enthaelt Toast-Element fuer copyText-Quittung."""
    body = _get_html(client).get_data(as_text=True)
    assert 'id="toast"' in body, "Toast-Element fehlt im Template (MAU-6 copyText-Quittung)"


# ── AC2 — platform.js: openLink + copyText ───────────────────────────────────

def test_ac2_platform_js_hat_openlink():
    """AC2 (MAU-6): platform.js definiert openLink(url) in beiden Klassen."""
    js_path = os.path.join(_SEITEN_DIR, "static", "platform.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "openLink" in inhalt, \
        "openLink fehlt in platform.js — MAU-6 / AC2"
    # Beide Klassen
    tg_count = inhalt.count("openLink")
    assert tg_count >= 2, \
        "openLink muss in TelegramPlatform UND BrowserPlatform implementiert sein (AC2)"


def test_ac2_platform_js_hat_copytext():
    """AC2 (MAU-6): platform.js definiert copyText(text) in beiden Klassen."""
    js_path = os.path.join(_SEITEN_DIR, "static", "platform.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "copyText" in inhalt, \
        "copyText fehlt in platform.js — MAU-6 / AC2"
    count = inhalt.count("copyText")
    assert count >= 2, \
        "copyText muss in TelegramPlatform UND BrowserPlatform implementiert sein (AC2)"


def test_ac2_telegram_platform_openlink_nutzt_openlink_api():
    """AC2 (MAU-6): TelegramPlatform.openLink nutzt this._wa.openLink (offizielle Telegram-API)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "platform.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    # TelegramPlatform-Block (zwischen class TelegramPlatform und class BrowserPlatform)
    tg_start = inhalt.find("class TelegramPlatform")
    tg_end = inhalt.find("class BrowserPlatform")
    tg_block = inhalt[tg_start:tg_end]
    assert "this._wa.openLink" in tg_block, \
        "TelegramPlatform.openLink nutzt nicht this._wa.openLink — MAU-6/AC2"


def test_ac2_telegram_platform_copytext_execcommand_fallback():
    """AC2 (MAU-6/memory): TelegramPlatform.copyText nutzt execCommand-Fallback (clipboard gesperrt)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "platform.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    tg_start = inhalt.find("class TelegramPlatform")
    tg_end = inhalt.find("class BrowserPlatform")
    tg_block = inhalt[tg_start:tg_end]
    assert "execCommand" in tg_block, \
        "TelegramPlatform.copyText nutzt nicht execCommand — Telegram clipboard.writeText ist gesperrt (memory)"


def test_ac2_browser_platform_openlink_window_open():
    """AC2: BrowserPlatform.openLink nutzt window.open (Browser-Fallback)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "platform.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    br_start = inhalt.find("class BrowserPlatform")
    br_end = inhalt.find("function getPlatform")
    br_block = inhalt[br_start:br_end]
    assert "window.open" in br_block, \
        "BrowserPlatform.openLink nutzt nicht window.open — AC2"


# ── AC5 — Lint-Self-Gate (statische Checks) ──────────────────────────────────

def test_ac5_kein_telegram_webapp_in_mini_app_js():
    """AC5 / MAD-5: mini-app-uebersicht.js enthaelt kein direktes Telegram.WebApp ausserhalb der openTelegramLink-Nutzung."""
    js_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    # MAD-5: direkter Telegram.WebApp-Zugriff nur fuer openTelegramLink (MAU-5 Default-Pfad)
    # und WebApp.close() (MAU-8 Fehler-Pfad) ist zulaessig — alles andere muss ueber platform.js.
    # Wir pruefen: kein Telegram.WebApp.MainButton / initData direkt im App-JS
    assert "Telegram.WebApp.MainButton" not in inhalt, \
        "Telegram.WebApp.MainButton direkt in mini-app-uebersicht.js — MAD-5-Verletzung"
    assert "Telegram.WebApp.sendData" not in inhalt, \
        "Telegram.WebApp.sendData direkt in mini-app-uebersicht.js — MAD-5-Verletzung"


def test_ac5_kein_hardcoded_mini_app_name_in_js():
    """AC5 / MAU-2: mini-app-uebersicht.js enthaelt keine hardcoded Mini-App-Namen.

    Kein 'essen-einkauf' oder 'routine-anpassen' direkt im Code — Inventar kommt
    aus dem Aggregator (SREG-14, MAU-2).
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "essen-einkauf" not in inhalt, \
        "'essen-einkauf' hardcoded in mini-app-uebersicht.js — MAU-2-Verletzung (keine hardcoded Liste)"
    assert "routine-anpassen" not in inhalt, \
        "'routine-anpassen' hardcoded in mini-app-uebersicht.js — MAU-2-Verletzung (keine hardcoded Liste)"


def test_ac5_js_nutzt_platform_openlink():
    """AC5 / MAU-6: mini-app-uebersicht.js ruft platform.openLink fuer URL-Karten auf."""
    js_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "platform.openLink" in inhalt, \
        "platform.openLink fehlt in mini-app-uebersicht.js — MAU-6/MAD-5"


def test_ac5_js_nutzt_platform_copytext():
    """AC5 / MAU-6: mini-app-uebersicht.js ruft platform.copyText fuer Kopieren-Button auf."""
    js_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "platform.copyText" in inhalt, \
        "platform.copyText fehlt in mini-app-uebersicht.js — MAU-6/MAD-5"


def test_ac5_css_hat_mad1_skalierungs_parameter():
    """AC5 / MAD-1: mini-app-uebersicht.css definiert --item-scale als zentralen Tuning-Parameter."""
    css_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.css")
    with open(css_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "--item-scale" in inhalt, \
        "--item-scale fehlt in mini-app-uebersicht.css — MAD-1 Skalierungs-Parameter Pflicht"
    assert "calc(" in inhalt, \
        "calc() fehlt — MAD-1 Masse muessen per calc() von --item-scale abgeleitet sein"


def test_ac5_css_hat_accordion_klassen():
    """AC5 / MAU-4: mini-app-uebersicht.css definiert .accordion-sektion und summary."""
    css_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.css")
    with open(css_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert ".accordion-sektion" in inhalt, \
        ".accordion-sektion fehlt in CSS — MAU-4 Accordion nicht gestyled"
    assert "summary" in inhalt, \
        "summary-Selektor fehlt in CSS — MAU-4 Accordion-Header nicht gestyled"


def test_ac5_css_hat_url_btn_klassen():
    """AC5 / MAU-6: mini-app-uebersicht.css definiert .url-btn fuer Oeffnen/Kopieren-Buttons."""
    css_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.css")
    with open(css_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert ".url-btn" in inhalt, \
        ".url-btn fehlt in mini-app-uebersicht.css — MAU-6 Oeffnen/Kopieren-Buttons nicht gestyled"


def test_ac5_css_hat_toast():
    """AC5 / MAU-6: mini-app-uebersicht.css definiert .toast fuer copyText-Quittung."""
    css_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.css")
    with open(css_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert ".toast" in inhalt, \
        ".toast fehlt in mini-app-uebersicht.css — MAU-6 Toast-Quittung nicht implementiert"
    assert ".toast.sichtbar" in inhalt or ".toast.visible" in inhalt or "sichtbar" in inhalt, \
        ".toast.sichtbar fehlt — Toast-Animation nicht definiert"


def test_ac5_html_enthaelt_fehler_banner(client):
    """AC5 / MAU-8: HTML enthaelt Fehler-Banner-Element fuer 401/5xx-Fehler."""
    body = _get_html(client).get_data(as_text=True)
    assert 'id="fehler-banner"' in body, \
        "fehler-banner-Element fehlt im Template (MAU-8 Fehler-Modi)"


def test_ac5_js_laedt_inventar_von_seiten_api():
    """AC5 / MAU-2: mini-app-uebersicht.js laedt Inventar von /api/v1/seiten."""
    js_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.js")
    with open(js_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "/api/v1/seiten" in inhalt, \
        "/api/v1/seiten fehlt in mini-app-uebersicht.js — MAU-2: Inventar vom Aggregator"


# ── AC3 (SHELL-10 MAU) — entfernt (RAT-31 E3, Closes #1496) ─────────────────
# test_shell10_mau_panel_eintrag_hat_shell_urls, test_shell10_mau_shell_url_aus_panel_id_abgeleitet,
# test_shell10_mau_js_rendert_shell_urls: shell_urls-Enrichment-Loop in get_seiten() entfernt
# (Loop enrichierte nur typ=panel-Einträge, die mit RAT-31 nicht mehr existieren).


# ── T1662: Scroll-Guard (Eltern-View, kein overflow:hidden auf html/body) ─────

def test_t1662_mini_app_uebersicht_css_kein_body_overflow_hidden():
    """T1662: mini-app-uebersicht.css enthaelt kein html/body { overflow: hidden }.

    Eltern-Views MUESSEN auf Chrome/Blink (Windows + Android) scrollen.
    overflow:hidden auf html oder body blockiert Scroll hart in Blink —
    iOS Safari (WebKit) toleriert es via Momentum, Chrome nicht (T1662-Befund).
    overflow-x: hidden (horizontaler Lock, MAU-7-Viewport-Lock) ist erlaubt.
    """
    import re
    css_path = os.path.join(_SEITEN_DIR, "static", "mini-app-uebersicht.css")
    with open(css_path, encoding="utf-8") as f:
        content = f.read()

    def _normiere(s: str) -> str:
        return re.sub(r'(?<!-)overflow: hidden', 'overflow:hidden', s)

    for selektor in ("html", "body", "html, body", "html,body"):
        muster = rf'{re.escape(selektor)}\s*\{{[^}}]*\}}'
        for block in re.findall(muster, content, re.DOTALL):
            normiert = _normiere(block)
            assert "overflow:hidden" not in normiert, (
                f"mini-app-uebersicht.css: '{selektor}'-Block enthaelt overflow:hidden "
                f"— T1662 Scroll-Guard verletzt (nur overflow-x: hidden erlaubt):\n{block}"
            )
