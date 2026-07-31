"""Tests fuer GET /seiten/essen/einkauf — ESSEN-31 / EZG-6 / MAD-7 / AC1 / AC2 / AC3.

Testet:
  AC1  — Route ist in seiten/main.py implementiert und antwortet mit HTML.
  AC2  — Init-Data-Auth (MAD-7): ohne Authorization-Header → 401;
          manipulierter Hash → 401; gueltiger Header → 200.
  AC3  — HTML-Render: Bring!-Card-Skelett ist im Template vorhanden (statisches
          HTML); die dynamische Liste wird per JS gerendert (kein Server-Render
          noetig fuer diesen Test).
  AC4  — FAM-7/8: User-ID nicht in familie.json → 403.

Lauf: python3 -m pytest seiten/tests/test_essen_einkauf_route.py -x -v

Entry-Path-Probe (AC1):
  grep '/seiten/essen/einkauf' seiten/main.py
  → @app.route("/seiten/essen/einkauf", methods=["GET"])

MAD-7: Auth via 'Authorization: tma <initData>'-Header (nicht mehr Query-Param).
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

# T1015: init_data lebt unter tools.initdata; kein sys.path-Hack mehr auf
# eltern-chat (Cluster-A-Option-B 2026-06-18-1720).

from seiten import main as seiten_main  # noqa: E402
from seiten.tests._familie_test_doppel import FileFakeFamilieClient  # noqa: E402

# ── Hilfs-Funktionen fuer initData-Erzeugung ─────────────────────────────────

BOT_TOKEN = "123456:ABCdef_testtoken"


def _baue_init_data(bot_token=BOT_TOKEN, user_id=42, offset_seconds=0):
    """Baut einen validen Telegram-initData-String mit korrektem HMAC.

    Algorithmus (eltern-chat/init_data.py, Telegram-Doku):
      secret_key = HMAC_SHA256(key=b'WebAppData', data=bot_token)
      hash       = HMAC_SHA256(key=secret_key,  data=data_check_string).hexdigest()
    """
    auth_date = int(time.time()) + offset_seconds
    user_json = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))

    felder = {
        "auth_date": str(auth_date),
        "user":      user_json,
    }

    # data_check_string: alphabetisch sortierte key=value-Zeilen
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(felder.items())
    )

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
    params["hash"] = "0" * 64  # falscher Hash
    return urllib.parse.urlencode(params)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch):
    """Setzt runtime-Dict vor jedem Test zurueck und konfiguriert Test-Modus."""
    # Minimale Configure ohne Disk-Inventar
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token=BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        # familie_client=None → FAM-Check uebersprungen (fail-open, T1015)
    )
    seiten_main.app.config["TESTING"] = True
    # Stub fuer Holer: keine echten HTTP-Calls


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — Route vorhanden und liefert HTML ────────────────────────────────────

def test_ac1_route_liefert_200_mit_gueltigem_init_data(client):
    """AC1: GET /seiten/essen/einkauf mit gueltiger initData → 200 HTML (MAD-7 Header)."""
    init_data = _baue_init_data()
    resp = client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


def test_ac1_route_in_main_py():
    """AC1 evidence_hint: Route ist in seiten/main.py implementiert."""
    main_path = os.path.join(_SEITEN_DIR, "main.py")
    with open(main_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "/seiten/essen/einkauf" in inhalt, \
        "Route /seiten/essen/einkauf fehlt in seiten/main.py"


# ── AC2 — Init-Data-Auth: drei Pfade ─────────────────────────────────────────

@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_ohne_init_data_liefert_200_skeleton(client):
    """AC2 (MAD-7): Request ohne Authorization-Header → 401."""
    resp = client.get("/seiten/essen/einkauf")
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth
    body = resp.get_json()
    assert body is not None
    assert body.get("error")  # irgendeine Fehler-Meldung


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_manipulierter_hash_liefert_200_skeleton(client):
    """AC2 (MAD-7): Authorization-Header mit manipuliertem Hash → 401."""
    init_data = _baue_init_data_manipuliert()
    resp = client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth
    body = resp.get_json()
    assert body is not None


def test_ac2_gueltiger_init_data_liefert_200(client):
    """AC2 (MAD-7): Authorization-Header mit gueltiger HMAC-Signatur → 200."""
    init_data = _baue_init_data(user_id=99)
    resp = client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_falsches_schema_liefert_200_skeleton(client):
    """AC2 (MAD-7): Authorization-Header mit falschem Schema (kein 'tma '-Praefix) → 401."""
    init_data = _baue_init_data()
    resp = client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "Bearer " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_abgelaufener_init_data_liefert_200_skeleton(client):
    """AC2 (MAD-7): auth_date mehr als max_age_seconds in der Vergangenheit → 401."""
    # max_age_seconds = 86400 (1 Tag); wir setzen offset auf -86401
    init_data = _baue_init_data(offset_seconds=-(86400 + 1))
    resp = client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_fehlendes_bot_token_liefert_200_skeleton(client, monkeypatch):
    """AC2 (MAD-7): Bot-Token fehlt in ENV und runtime → 500 Konfig-Fehler."""
    seiten_main.runtime["bot_token"] = None
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    init_data = _baue_init_data()
    resp = client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Token-Check nur am validate-Endpoint


# ── AC4 — FAM-7/8-Check ──────────────────────────────────────────────────────

@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac4_fremde_user_id_liefert_200_skeleton(client, tmp_path):
    """AC4 (FAM-7/8): User-ID nicht in familie.json → 403."""
    familie = {"erwachsene": [{"id": "p1", "name": "Elter", "ring": "blue", "telegram_id": 99999}], "kinder": []}
    f = tmp_path / "familie.json"
    f.write_text(__import__("json").dumps(familie), encoding="utf-8")
    seiten_main.runtime["familie_client"] = FileFakeFamilieClient(str(f))

    # User-ID 42 ist nicht in der Registry (nur 99999 ist drin)
    init_data = _baue_init_data(user_id=42)
    resp = client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, FAM-Check via JS-ensureAuth
    body = resp.get_json()
    assert body is not None

    # Cleanup
    seiten_main.runtime["familie_client"] = None


def test_ac4_bekannte_user_id_liefert_200(client, tmp_path):
    """AC4 (FAM-7/8): User-ID in familie.json → 200."""
    familie = {"erwachsene": [{"id": "p1", "name": "Elter", "ring": "blue", "telegram_id": 42}], "kinder": []}
    f = tmp_path / "familie.json"
    f.write_text(__import__("json").dumps(familie), encoding="utf-8")
    seiten_main.runtime["familie_client"] = FileFakeFamilieClient(str(f))

    init_data = _baue_init_data(user_id=42)
    resp = client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200

    # Cleanup
    seiten_main.runtime["familie_client"] = None


# ── AC3 — HTML-Render: statisches Skelett korrekt ────────────────────────────

def _get_html(client, user_id=42):
    """Helper: GET /seiten/essen/einkauf mit gueltiger MAD-7-Auth."""
    init_data = _baue_init_data(user_id=user_id)
    return client.get(
        "/seiten/essen/einkauf",
        headers={"Authorization": "tma " + init_data},
    ).get_data(as_text=True)


def test_ac3_html_enthaelt_listen_container(client):
    """AC3: HTML traegt #liste-Container (JS rendert Karten darin)."""
    body = _get_html(client)
    assert 'id="liste"' in body


def test_ac3_html_enthaelt_quick_add_button(client):
    """AC3: HTML traegt ➕-FAB fuer Quick-Add (ESSEN-31)."""
    body = _get_html(client)
    assert 'id="quick-add"' in body


def test_ac3_html_laedt_platform_js(client):
    """AC3 / AC7: HTML laedt platform.js (RAT-16-Wrapper) vor essen-einkauf.js."""
    body = _get_html(client)
    assert "platform.js" in body
    assert "essen-einkauf.js" in body
    # platform.js muss VOR essen-einkauf.js erscheinen (ESSEN-31 Lade-Reihenfolge)
    pos_platform = body.index("platform.js")
    pos_app = body.index("essen-einkauf.js")
    assert pos_platform < pos_app, \
        "platform.js muss vor essen-einkauf.js geladen werden (RAT-16)"


def test_ac3_html_enthaelt_sheet_overlay(client):
    """AC3: HTML traegt sheet-overlay fuer ESSEN-30-Bottom-Sheets."""
    body = _get_html(client)
    assert 'id="sheet-overlay"' in body


# ── AC7 — Kein direkter Telegram.WebApp-Aufruf in JS ─────────────────────────

def test_ac7_kein_telegram_webapp_in_js():
    """AC7: essen-einkauf.js enthaelt keinen direkten window.Telegram.WebApp-Aufruf.
    Alle Platform-Calls laufen ueber getPlatform() (RAT-16).
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "essen-einkauf.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # "Telegram.WebApp" darf nicht direkt aufgerufen werden (nur in platform.js erlaubt)
    assert "Telegram.WebApp" not in js_inhalt, \
        "essen-einkauf.js ruft Telegram.WebApp direkt auf — AC7/RAT-16-Verletzung"


# ── T1662: Scroll-Guard (Eltern-View, kein overflow:hidden auf html/body) ─────

def test_t1662_essen_einkauf_css_kein_body_overflow_hidden():
    """T1662: essen-einkauf.css enthaelt kein html/body { overflow: hidden }.

    Eltern-Views MUESSEN auf Chrome/Blink (Windows + Android) scrollen.
    overflow:hidden auf html oder body blockiert Scroll hart in Blink —
    iOS Safari (WebKit) toleriert es via Momentum, Chrome nicht (T1662-Befund).
    overflow-x: hidden (horizontaler Lock) ist erlaubt und unberuehrt.
    """
    import re
    css_path = os.path.join(_SEITEN_DIR, "static", "essen-einkauf.css")
    with open(css_path, encoding="utf-8") as f:
        content = f.read()

    def _normiere(s: str) -> str:
        return s.replace("overflow: hidden", "overflow:hidden")

    for selektor in ("html", "body", "html, body", "html,body"):
        muster = rf'{re.escape(selektor)}\s*\{{[^}}]*\}}'
        for block in re.findall(muster, content, re.DOTALL):
            normiert = _normiere(block)
            assert "overflow:hidden" not in normiert, (
                f"essen-einkauf.css: '{selektor}'-Block enthaelt overflow:hidden "
                f"— T1662 Scroll-Guard verletzt:\n{block}"
            )


# ── T1696: Scroll-Container-Guard (body traegt height:100dvh + overflow-y:auto) ──

def test_t1696_essen_einkauf_css_body_scroll_container():
    """T1696: essen-einkauf.css body-Block traegt height:100dvh + overflow-y:auto.

    Telegram-Desktop/Android-WebView scrollt den frei wachsenden Body NICHT
    zuverlaessig (iOS schon). Der gebundene Scroll-Container (height:100dvh,
    overflow-y:auto) ist der verifizierte Fix (T1662-Muster, Nic-Verifikation
    #1662 Windows). Kein ganzheitliches overflow:hidden auf html oder body
    (wuerde Scroll blockieren).
    """
    import re
    css_path = os.path.join(_SEITEN_DIR, "static", "essen-einkauf.css")
    with open(css_path, encoding="utf-8") as f:
        content = f.read()

    # Pruefe body-Block auf gebundenen Scroll-Container.
    body_blocks = re.findall(r'body\s*\{[^}]*\}', content, re.DOTALL)
    assert body_blocks, "essen-einkauf.css enthaelt keinen body-Block"

    combined = "\n".join(body_blocks)
    assert "height: 100dvh" in combined, (
        "essen-einkauf.css body-Block enthaelt kein 'height: 100dvh' "
        "— T1696 Scroll-Container-Guard verletzt"
    )
    assert "overflow-y: auto" in combined, (
        "essen-einkauf.css body-Block enthaelt kein 'overflow-y: auto' "
        "— T1696 Scroll-Container-Guard verletzt"
    )
