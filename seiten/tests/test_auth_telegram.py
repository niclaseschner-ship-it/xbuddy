"""#1946 — Telegram-Anmeldung: `POST /auth/telegram` tauscht initData gegen Cookie.

Nic 2026-09-25: eine Übersicht für Browser und Telegram. Der Telegram-WebView
hat nicht sicher ein `xbuddy_session`-Cookie; die Übersicht tauscht deshalb die
signierte initData einmal gegen dasselbe Cookie, das `/auth/pair` setzt
(auth.md AUTH-2.b).

Abgedeckt (Abnahme #1946):
  - gültig + Familienmitglied (Erwachsener ODER Kind, #1951) → 200 + Cookie (verifizierbar, Attribute wie /auth/pair)
  - manipuliert → 401, kein Cookie
  - zu alt (auth_date jenseits max_age_seconds) → 401, kein Cookie
  - Fremder (nicht in der Familie) → 403, kein Cookie
  - Familie-Service weg → 503, kein Cookie (fail-closed)
  - das ausgestellte Cookie öffnet eine hart gegatete seiten-Route
  - Übersicht und 401-Anweisungsseite binden das Tausch-Skript ein
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse

import pytest

from seiten import main as seiten_main
from tools.initdata import session_cookie as sc

BOT_TOKEN = "1234:TESTTOKEN-1946"
MAX_AGE = 3600
ERWACHSENER = 42
KIND = 77
EXTERN = {"X-Forwarded-For": "203.0.113.9", "X-Real-IP": "203.0.113.9"}


class _FamilieDoppel:
    """Test-Doppel mit der Oberfläche von tools.familie_client.FamilieClient."""

    def __init__(self, erwachsene, kinder, erreichbar=True):
        self._erwachsene = set(erwachsene)
        self._kinder = set(kinder)
        self._erreichbar = erreichbar

    def get_telegram_ids(self):
        if not self._erreichbar:
            return None
        return self._erwachsene | self._kinder

    def get_erwachsene_telegram_ids(self):
        if not self._erreichbar:
            return None
        return set(self._erwachsene)


@pytest.fixture
def client():
    seiten_main.app.config["TESTING"] = True
    vorher = {k: seiten_main.runtime.get(k)
              for k in ("bot_token", "familie_client", "init_data_config")}
    seiten_main.runtime["bot_token"] = BOT_TOKEN
    seiten_main.runtime["familie_client"] = _FamilieDoppel([ERWACHSENER], [KIND])
    seiten_main.runtime["init_data_config"] = {"max_age_seconds": MAX_AGE}
    yield seiten_main.app.test_client()
    seiten_main.runtime.update(vorher)


def _init_data(user_id, auth_date=None, token=BOT_TOKEN):
    """Signierte initData wie Telegram sie liefert (HMAC, WebAppData-Schlüssel)."""
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "q-1946",
        "user": json.dumps({"id": user_id, "first_name": "T"}, separators=(",", ":")),
    }
    data_check = "\n".join("%s=%s" % kv for kv in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)


def _tausch(client, init_data):
    return client.post("/auth/telegram", headers=dict(EXTERN, Authorization="tma " + init_data))


def _set_cookie_header(resp):
    return [h for h in resp.headers.getlist("Set-Cookie") if h.startswith(sc.COOKIE_NAME + "=")]


def _cookie_wert(resp):
    header = _set_cookie_header(resp)[0]
    return header.split(";", 1)[0].split("=", 1)[1]


# ── gültig ────────────────────────────────────────────────────────────────────

def test_gueltige_initdata_eines_erwachsenen_setzt_das_cookie(client):
    resp = _tausch(client, _init_data(ERWACHSENER))
    assert resp.status_code == 200
    assert len(_set_cookie_header(resp)) == 1


def test_cookie_traegt_die_telegram_user_id_als_subjekt(client):
    resp = _tausch(client, _init_data(ERWACHSENER))
    assert sc.verify_session(_cookie_wert(resp), BOT_TOKEN) == str(ERWACHSENER)


def test_cookie_attribute_wie_auth_pair(client):
    header = _set_cookie_header(_tausch(client, _init_data(ERWACHSENER)))[0].lower()
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    assert "path=/" in header


def test_antwort_wird_nicht_gecacht(client):
    resp = _tausch(client, _init_data(ERWACHSENER))
    assert resp.headers.get("Cache-Control") == "no-store"


def test_ausgestelltes_cookie_oeffnet_eine_hart_gegatete_route(client):
    """Ende-zu-Ende: das Cookie aus dem Tausch trägt durch require_init_data
    (immer hart) — dieselbe Identität wie ein gepairtes Gerät."""
    wert = _cookie_wert(_tausch(client, _init_data(ERWACHSENER)))
    frisch = seiten_main.app.test_client()
    assert frisch.get("/api/v1/seiten", headers=EXTERN).status_code == 401
    frisch.set_cookie(sc.COOKIE_NAME, wert)
    assert frisch.get("/api/v1/seiten", headers=EXTERN).status_code == 200


# ── abgelehnt ────────────────────────────────────────────────────────────────

def test_ohne_initdata_401_ohne_cookie(client):
    resp = client.post("/auth/telegram", headers=EXTERN)
    assert resp.status_code == 401
    assert _set_cookie_header(resp) == []


def test_manipulierte_initdata_401_ohne_cookie(client):
    echt = _init_data(ERWACHSENER)
    # user-Feld nachträglich auf eine andere ID gedreht, Hash bleibt alt.
    manipuliert = echt.replace("%22id%22%3A42", "%22id%22%3A43")
    assert manipuliert != echt
    resp = _tausch(client, manipuliert)
    assert resp.status_code == 401
    assert _set_cookie_header(resp) == []


def test_mit_fremdem_bot_token_signierte_initdata_401(client):
    resp = _tausch(client, _init_data(ERWACHSENER, token="9999:ANDERER"))
    assert resp.status_code == 401
    assert _set_cookie_header(resp) == []


def test_zu_alte_initdata_401_ohne_cookie(client):
    alt = int(time.time()) - MAX_AGE - 60
    resp = _tausch(client, _init_data(ERWACHSENER, auth_date=alt))
    assert resp.status_code == 401
    assert _set_cookie_header(resp) == []


def test_kind_bekommt_das_cookie_auch(client):
    # #1951: das Kinder-Tablet gehört zum Ökosystem, sein Telegram-Konto auch.
    resp = _tausch(client, _init_data(KIND))
    assert resp.status_code == 200
    assert sc.verify_session(_cookie_wert(resp), BOT_TOKEN) == str(KIND)


def test_fremder_bekommt_kein_cookie_403(client):
    resp = _tausch(client, _init_data(555))
    assert resp.status_code == 403
    assert _set_cookie_header(resp) == []


def test_familie_service_weg_ist_fail_closed_503(client):
    seiten_main.runtime["familie_client"] = _FamilieDoppel([ERWACHSENER], [], erreichbar=False)
    resp = _tausch(client, _init_data(ERWACHSENER))
    assert resp.status_code == 503
    assert _set_cookie_header(resp) == []


def test_nur_post(client):
    assert client.get("/auth/telegram", headers=EXTERN).status_code == 405


# ── Einbindung in die eine Übersicht ─────────────────────────────────────────

_SKRIPT = "/api/v1/seiten/static/telegram-anmeldung.js"


def test_401_anweisungsseite_bindet_das_tausch_skript_ein(client):
    """Im hard-Modus liefert die Übersicht ohne Cookie die AUTH-8-Seite — sie
    muss den Tausch selbst anstoßen können, sonst käme Telegram nie hinein."""
    resp = client.get("/api/v1/seiten", headers=EXTERN)
    assert resp.status_code == 401
    body = resp.get_data(as_text=True)
    assert _SKRIPT in body
    assert "data-tauschen" in body


def test_uebersicht_ohne_cookie_tauscht(client):
    body = client.get("/api/v1/seiten/uebersicht", headers=EXTERN).get_data(as_text=True)
    assert _SKRIPT in body
    assert "data-tauschen" in body


def test_uebersicht_mit_cookie_tauscht_nicht(client):
    client.set_cookie(sc.COOKIE_NAME, sc.sign_session(str(ERWACHSENER), BOT_TOKEN))
    resp = client.get("/api/v1/seiten/uebersicht", headers=EXTERN)
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert _SKRIPT in body
    assert "data-tauschen" not in body


def test_tausch_skript_wird_ausgeliefert(client):
    resp = client.get(_SKRIPT)
    assert resp.status_code == 200
    assert b"/auth/telegram" in resp.data


def test_mini_app_uebersicht_ist_weg(client):
    assert client.get("/api/v1/seiten/mini-app-uebersicht").status_code == 404
