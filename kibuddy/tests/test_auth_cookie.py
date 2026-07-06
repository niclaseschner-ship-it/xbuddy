"""AUTH-2/3/8 — kibuddy-Decorator HART + Cookie-Pfad (T1321, auth.md AUTH-9).

Prüft den auf HART geflippten `require_init_data` an kibuddy-Ziel-Routen —
Muster essen/tests/test_auth_cookie.py:
  - Session-Cookie `xbuddy_session` valide → 200 + Rolling-Refresh-Set-Cookie.
  - Weder Cookie noch tma noch Loopback → HART 401 mit AUTH-8-HTML.
  - Ungültiger Cookie → 401.
  - tma-Pfad (Mini-App) bricht NICHT (valider Header + FAM-Mitglied → 200).
  - Loopback (127.0.0.1, kein X-Forwarded-For) → 200 (AUTH-5, Server-zu-Server).
  - ZUSÄTZLICH: /frage NDJSON-Streaming-Route trägt Rolling-Refresh (Cookie im
    Stream-Response, `make_response(Response(stream_with_context))`+set_cookie).

Alle „externen" Requests setzen X-Forwarded-For, um den AUTH-5-Loopback-Bypass
zu umgehen. Der `kibuddy_sid`-after_request-Hook (ANDERER Cookie-Name)
koexistiert konfliktfrei mit `xbuddy_session`.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import sys
import time
import urllib.parse

_KIBUDDY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_KIBUDDY_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from kibuddy import main as kibuddy_main  # noqa: E402
from kibuddy.session_memory import SessionRegistry  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_XFF = {"X-Forwarded-For": "1.2.3.4"}
TEST_BOT_TOKEN = "123456:ABCdef_testtoken"

_ZIEL = "/api/v1/kibuddy/config"


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


def _set_cookie_gesamt(resp):
    """Alle Set-Cookie-Header verbunden (kibuddy setzt zusätzlich kibuddy_sid)."""
    return "; ".join(resp.headers.get_all("Set-Cookie"))


class _FamilieStub:
    """Deterministischer FAM-Lookup — user_id 42 ist Mitglied."""

    def get_telegram_ids(self):
        return {42, 7}


@pytest.fixture
def raw_client(runtime_config, data_root, fake_llm, fake_stt, fake_tts):
    """Test-Client OHNE Auto-Auth-Cookie, mit deterministischem FAM-Stub."""
    kibuddy_main.configure(
        runtime_config=runtime_config,
        data_root=data_root,
        llm=fake_llm,
        stt_engine=fake_stt,
        tts_engine=fake_tts,
        session_registry=SessionRegistry(),
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        familie_client=_FamilieStub(),
    )
    return kibuddy_main.app.test_client()


def test_gueltiger_cookie_gibt_200_und_rolling_refresh(raw_client):
    raw_client.set_cookie(sc.COOKIE_NAME,
                          sc.sign_session("tablet-elias-01", TEST_BOT_TOKEN))
    resp = raw_client.get(_ZIEL, headers=_XFF)
    assert resp.status_code == 200
    set_cookie = _set_cookie_gesamt(resp)
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
    init_data = _baue_init_data(bot_token=TEST_BOT_TOKEN, user_id=42)
    resp = raw_client.get(_ZIEL, headers={**_XFF, "Authorization": "tma " + init_data})
    assert resp.status_code == 200


def test_loopback_ohne_auth_gibt_200(raw_client):
    resp = raw_client.get(_ZIEL)
    assert resp.status_code == 200


def test_frage_streaming_traegt_rolling_refresh(raw_client):
    """AUTH-2:78 — die NDJSON-Streaming-Route /frage rollt den Cookie mit
    (make_response wrappt die stream_with_context-Response; Header vor Body)."""
    raw_client.set_cookie(sc.COOKIE_NAME,
                          sc.sign_session("tablet-elias-01", TEST_BOT_TOKEN))
    resp = raw_client.post(
        "/api/v1/kibuddy/frage",
        headers=_XFF,
        data={"audio": (io.BytesIO(b"fake-audio-bytes"), "aufnahme.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.mimetype == "application/x-ndjson"
    # Rolling-Refresh auch auf dem Stream-Response.
    assert sc.COOKIE_NAME in _set_cookie_gesamt(resp)
    # Der Stream liefert die Kind-Stufe (FakeSTT-Transkript).
    body = resp.get_data(as_text=True)
    assert '"event": "kind"' in body


def test_frage_ohne_auth_gibt_401(raw_client):
    resp = raw_client.post(
        "/api/v1/kibuddy/frage",
        headers=_XFF,
        data={"audio": (io.BytesIO(b"fake-audio-bytes"), "aufnahme.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 401
