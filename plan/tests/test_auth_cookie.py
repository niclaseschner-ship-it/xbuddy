"""AUTH-2/3/8 — plan-Decorator HART + Cookie-Pfad (T1321, auth.md AUTH-9).

Prüft den auf HART geflippten `require_init_data` an einer plan-Ziel-Route
(GET /api/v1/plan/zuteilung) — Muster essen/tests/test_auth_cookie.py:
  - Session-Cookie `xbuddy_session` valide → 200 + Rolling-Refresh-Set-Cookie.
  - Weder Cookie noch tma noch Loopback → HART 401 mit AUTH-8-HTML.
  - Ungültiger Cookie → 401.
  - tma-Pfad (Mini-App) bricht NICHT (valider Header + FAM-Mitglied → 200).
  - Loopback (127.0.0.1, kein X-Forwarded-For) → 200 (AUTH-5, Server-zu-Server).
  - PUT-Schreibpfad trägt den Decorator → 401 ohne Auth.

Plan ist Nicht-Mini-App (PWA): der Cookie-Pfad ist der Regel-Pfad. Der
FAM-Client für den tma-Zweig ist ein EIGENER Slot (`auth_familie_client`), nicht
der Registry-`familie_client` (der `snapshot()`, nicht `get_telegram_ids()` hat).

Alle „externen" Requests setzen X-Forwarded-For, um den AUTH-5-Loopback-Bypass
zu umgehen (nginx setzt den Header im Produktiv-Pfad).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse

_PLAN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PLAN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402
from _plan_fakes import FakeTransport  # noqa: E402

from plan import main as plan_main  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_XFF = {"X-Forwarded-For": "1.2.3.4"}
TEST_BOT_TOKEN = "123456:ABCdef_testtoken"

_ZIEL = "/api/v1/plan/zuteilung?week_start=2026-07-06"


def _baue_init_data(bot_token=TEST_BOT_TOKEN, user_id=42, offset_seconds=0):
    """Baut einen validen Telegram-initData-String mit korrektem HMAC (Muster essen)."""
    auth_date = int(time.time()) + offset_seconds
    user_json = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))
    felder = {"auth_date": str(auth_date), "user": user_json}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(felder.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    felder["hash"] = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(felder)


class _FamilieStub:
    """Deterministischer FAM-Lookup — user_id 42 ist Mitglied."""

    def get_telegram_ids(self):
        return {42, 7}


@pytest.fixture
def raw_client(demo_config, demo_registry):
    """Test-Client OHNE Auto-Auth, mit deterministischem FAM-Stub.

    `demo_config`/`demo_registry` stammen aus plan/tests/conftest.py.
    """
    plan_main.configure(
        demo_config, demo_registry, FakeTransport(),
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        auth_familie_client=_FamilieStub(),
    )
    plan_main.app.testing = True
    return plan_main.app.test_client()


def test_gueltiger_cookie_gibt_200_und_rolling_refresh(raw_client):
    raw_client.set_cookie(sc.COOKIE_NAME,
                          sc.sign_session("tablet-elias-01", TEST_BOT_TOKEN))
    resp = raw_client.get(_ZIEL, headers=_XFF)
    assert resp.status_code == 200
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Lax" in set_cookie


def test_keine_quelle_gibt_hart_401_mit_auth8(raw_client):
    resp = raw_client.get(_ZIEL, headers=_XFF)
    assert resp.status_code == 401
    body = resp.get_data(as_text=True)
    assert "neu verbunden" in body
    assert resp.headers["Content-Type"].startswith("text/html")


def test_ungueltiger_cookie_gibt_401(raw_client):
    raw_client.set_cookie(sc.COOKIE_NAME, "kaputt.123.deadbeef")
    resp = raw_client.get(_ZIEL, headers=_XFF)
    assert resp.status_code == 401


def test_tma_pfad_bricht_nicht(raw_client):
    # Valider tma-Header, FAM-Stub kennt user 42 → Mitglied → 200.
    init_data = _baue_init_data(bot_token=TEST_BOT_TOKEN, user_id=42)
    resp = raw_client.get(_ZIEL, headers={**_XFF, "Authorization": "tma " + init_data})
    assert resp.status_code == 200


def test_tma_nichtmitglied_gibt_403(raw_client):
    init_data = _baue_init_data(bot_token=TEST_BOT_TOKEN, user_id=999)
    resp = raw_client.get(_ZIEL, headers={**_XFF, "Authorization": "tma " + init_data})
    assert resp.status_code == 403


def test_loopback_ohne_auth_gibt_200(raw_client):
    resp = raw_client.get(_ZIEL)
    assert resp.status_code == 200


def test_put_zuteilung_ist_geschuetzt(raw_client):
    # Schreibpfad (PUT) trägt den Decorator → 401 ohne Auth.
    resp = raw_client.put("/api/v1/plan/zuteilung", headers=_XFF, json={})
    assert resp.status_code == 401
