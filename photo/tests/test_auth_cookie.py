"""AUTH-2/3/8 — photo-Decorator HART + Cookie-Pfad (T1321, auth.md AUTH-9).

Prüft den auf HART geflippten `require_init_data` an einer photo-Ziel-Route
(GET /api/v1/photo/medien) — Muster essen/tests/test_auth_cookie.py:
  - Session-Cookie `xbuddy_session` valide → 200 + Rolling-Refresh-Set-Cookie.
  - Weder Cookie noch tma noch Loopback → HART 401 mit AUTH-8-HTML.
  - Ungültiger Cookie → 401.
  - tma-Pfad (Mini-App) bricht NICHT (valider Header + FAM-Mitglied → 200).
  - Loopback (127.0.0.1, kein X-Forwarded-For) → 200 (AUTH-5, Server-zu-Server).
  - GET medium (send_file-Binary) trägt den Decorator → 401 ohne Auth.

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

_PHOTO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PHOTO_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from photo import config as config_mod  # noqa: E402
from photo import main as photo_main  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_XFF = {"X-Forwarded-For": "1.2.3.4"}
TEST_BOT_TOKEN = "123456:ABCdef_testtoken"


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
def raw_client(tmp_path):
    """Test-Client OHNE Auto-Auth-Header, mit deterministischem FAM-Stub."""
    cfg = config_mod.resolve(env={})
    lib = tmp_path / "medien"
    lib.mkdir()
    cfg.library_verzeichnis = str(lib)
    photo_main.configure(
        cfg,
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        familie_client=_FamilieStub(),
    )
    return photo_main.app.test_client()


def test_gueltiger_cookie_gibt_200_und_rolling_refresh(raw_client):
    raw_client.set_cookie(sc.COOKIE_NAME,
                          sc.sign_session("tablet-elias-01", TEST_BOT_TOKEN))
    resp = raw_client.get("/api/v1/photo/medien", headers=_XFF)
    assert resp.status_code == 200
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Lax" in set_cookie


def test_keine_quelle_gibt_hart_401_mit_auth8(raw_client):
    resp = raw_client.get("/api/v1/photo/medien", headers=_XFF)
    assert resp.status_code == 401
    body = resp.get_data(as_text=True)
    assert "neu verbunden" in body
    assert resp.headers["Content-Type"].startswith("text/html")


def test_ungueltiger_cookie_gibt_401(raw_client):
    raw_client.set_cookie(sc.COOKIE_NAME, "kaputt.123.deadbeef")
    resp = raw_client.get("/api/v1/photo/medien", headers=_XFF)
    assert resp.status_code == 401


def test_tma_pfad_bricht_nicht(raw_client):
    init_data = _baue_init_data(bot_token=TEST_BOT_TOKEN, user_id=42)
    resp = raw_client.get(
        "/api/v1/photo/medien",
        headers={**_XFF, "Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200


def test_loopback_ohne_auth_gibt_200(raw_client):
    resp = raw_client.get("/api/v1/photo/medien")
    assert resp.status_code == 200


def test_delete_medium_ist_geschuetzt(raw_client):
    # DELETE-Binary-Löschpfad trägt den Decorator → 401 ohne Auth.
    resp = raw_client.delete("/api/v1/photo/medien/xyz", headers=_XFF)
    assert resp.status_code == 401
