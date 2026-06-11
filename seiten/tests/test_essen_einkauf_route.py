"""Tests fuer GET /seiten/essen/einkauf — ESSEN-31 / EZG-6 / AC1 / AC2 / AC3.

Testet:
  AC1  — Route ist in seiten/main.py implementiert und antwortet mit HTML.
  AC2  — Init-Data-Auth: ohne initData → 401; manipulierter Hash → 401;
          gueltiger HMAC → 200.
  AC3  — HTML-Render: Bring!-Card-Skelett ist im Template vorhanden (statisches
          HTML); die dynamische Liste wird per JS gerendert (kein Server-Render
          noetig fuer diesen Test).

Lauf: python3 -m pytest seiten/tests/test_essen_einkauf_route.py -x -v

Entry-Path-Probe (AC1):
  grep '/seiten/essen/einkauf' seiten/main.py
  → @app.route("/seiten/essen/einkauf", methods=["GET"])
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

# eltern-chat muss importierbar sein (Lego-Basis)
_ELTERN_CHAT_DIR = os.path.join(_REPO_ROOT, "eltern-chat")
sys.path.insert(0, _ELTERN_CHAT_DIR)

from seiten import main as seiten_main  # noqa: E402

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
    )
    seiten_main.app.config["TESTING"] = True
    # Stub fuer Holer: keine echten HTTP-Calls
    monkeypatch.setattr(seiten_main, "hole_panels", list)
    monkeypatch.setattr(seiten_main, "hole_geraete", list)


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — Route vorhanden und liefert HTML ────────────────────────────────────

def test_ac1_route_liefert_200_mit_gueltigem_init_data(client):
    """AC1: GET /seiten/essen/einkauf mit gueltiger initData → 200 HTML."""
    init_data = _baue_init_data()
    resp = client.get("/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data))
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

def test_ac2_ohne_init_data_liefert_401(client):
    """AC2: Request ohne ?initData= → 401."""
    resp = client.get("/seiten/essen/einkauf")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body is not None
    assert "initData" in body.get("error", "")


def test_ac2_manipulierter_hash_liefert_401(client):
    """AC2: Request mit manipuliertem Hash → 401."""
    init_data = _baue_init_data_manipuliert()
    resp = client.get("/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data))
    assert resp.status_code == 401
    body = resp.get_json()
    assert body is not None


def test_ac2_gueltiger_init_data_liefert_200(client):
    """AC2: Request mit gueltiger HMAC-Signatur → 200."""
    init_data = _baue_init_data(user_id=99)
    resp = client.get("/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data))
    assert resp.status_code == 200


def test_ac2_tg_web_app_data_parameter_akzeptiert(client):
    """AC2: Telegram nutzt manchmal ?tgWebAppData= statt ?initData= — beide werden akzeptiert."""
    init_data = _baue_init_data()
    resp = client.get("/seiten/essen/einkauf?tgWebAppData=" + urllib.parse.quote(init_data))
    assert resp.status_code == 200


def test_ac2_abgelaufener_init_data_liefert_401(client):
    """AC2: auth_date mehr als max_age_seconds in der Vergangenheit → 401."""
    # max_age_seconds = 86400 (1 Tag); wir setzen offset auf -86401
    init_data = _baue_init_data(offset_seconds=-(86400 + 1))
    resp = client.get("/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data))
    assert resp.status_code == 401


def test_ac2_fehlendes_bot_token_liefert_500(client, monkeypatch):
    """AC2: Bot-Token fehlt in ENV und runtime → 500 Konfig-Fehler."""
    # Bot-Token aus runtime loeschen
    seiten_main.runtime["bot_token"] = None
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    init_data = _baue_init_data()
    resp = client.get("/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data))
    assert resp.status_code == 500


# ── AC3 — HTML-Render: statisches Skelett korrekt ────────────────────────────

def test_ac3_html_enthaelt_listen_container(client):
    """AC3: HTML traegt #liste-Container (JS rendert Karten darin)."""
    init_data = _baue_init_data()
    body = client.get(
        "/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data)
    ).get_data(as_text=True)
    assert 'id="liste"' in body


def test_ac3_html_enthaelt_quick_add_button(client):
    """AC3: HTML traegt ➕-FAB fuer Quick-Add (ESSEN-31)."""
    init_data = _baue_init_data()
    body = client.get(
        "/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data)
    ).get_data(as_text=True)
    assert 'id="quick-add"' in body


def test_ac3_html_laedt_platform_js(client):
    """AC3 / AC7: HTML laedt platform.js (RAT-16-Wrapper) vor essen-einkauf.js."""
    init_data = _baue_init_data()
    body = client.get(
        "/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data)
    ).get_data(as_text=True)
    assert "platform.js" in body
    assert "essen-einkauf.js" in body
    # platform.js muss VOR essen-einkauf.js erscheinen (ESSEN-31 Lade-Reihenfolge)
    pos_platform = body.index("platform.js")
    pos_app = body.index("essen-einkauf.js")
    assert pos_platform < pos_app, \
        "platform.js muss vor essen-einkauf.js geladen werden (RAT-16)"


def test_ac3_html_enthaelt_sheet_overlay(client):
    """AC3: HTML traegt sheet-overlay fuer ESSEN-30-Bottom-Sheets."""
    init_data = _baue_init_data()
    body = client.get(
        "/seiten/essen/einkauf?initData=" + urllib.parse.quote(init_data)
    ).get_data(as_text=True)
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
