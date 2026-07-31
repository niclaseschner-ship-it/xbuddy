"""HART-Cookie-Auth der hoerspiel-Datenrouten (T1640, auth.md AUTH-2/3/5/8).

Phase-3-Migration: die hoerspiel-Datenrouten (config, alben, alben/<id>/manifest,
resume, themen, folgen-vorschlag) tragen jetzt den HART-Factory-Decorator
(`tools/initdata/auth_gate.make_require_init_data`, Name `require_init_data`).
Diese Suite belegt die vier Auth-Zweige an einer echten AUTH-3-Route plus die
KRITISCHE Playback-Ausnahme:

  - extern OHNE Quelle (X-Forwarded-For gesetzt) → 401 (hoerspiel-AUTH-8-HTML),
  - extern MIT gültigem Cookie → 200 + Rolling-Refresh (Set-Cookie),
  - extern MIT gültigem tma-Header + Familien-Mitglied → 200,
  - Loopback (127.0.0.1 ohne XFF) → Pass-through 200,
  - KRITISCH: die Audio-mp3-Route bleibt PUBLIC (AUTH-4) — extern ohne Cookie
    liefert KEIN 401 (sonst bräche das Kind-Tablet-Playback).
"""

import hashlib
import hmac
import json
import sys
import time
import urllib.parse
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hoerspiel import main as main_mod  # noqa: E402
from tools.initdata import session_cookie  # noqa: E402

TEST_BOT_TOKEN = "123456:ABCdef_testtoken"

# AUTH-3-Datenroute (GET alben liefert auch mit leerem data_root 200 → []).
_DATA_ROUTE = "/api/v1/hoerspiel/mia/alben"
# KRITISCH: Audio-mp3 bleibt PUBLIC (AUTH-4). 404 (kein Album) beweist, dass der
# View OHNE Auth-401 erreicht wird — die Auth-Membran greift nicht.
_AUDIO_ROUTE = "/api/v1/hoerspiel/mia/alben/x1/audio/track-01.mp3"


def _bau_init_data(bot_token=TEST_BOT_TOKEN, user_id=42):
    """Baut einen validen Telegram-initData-String mit korrektem HMAC."""
    felder = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "Test"},
                           separators=(",", ":")),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(felder.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    felder["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(felder)


class _FamilieStub:
    """Fail-open-Doppel: liefert die Familien-IDs (user_id=42 enthalten)."""

    def get_telegram_ids(self):
        return {42}


@pytest.fixture
def app_client(runtime_config, data_config, data_root, fake_llm, fake_tts, fixed_now):
    # HART-Auth: echter bot_token (nicht "TEST"), init_data_config + FAM-Stub.
    main_mod.configure(
        runtime_config=runtime_config, data_config=data_config,
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        familie_client_auth=_FamilieStub(),
    )
    main_mod.app.config["TESTING"] = True
    return main_mod.app.test_client()


def test_daten_route_extern_ohne_quelle_ist_401(app_client):
    """Fremd-Request (XFF, kein Cookie/tma) → HART 401 mit AUTH-8-HTML."""
    r = app_client.get(_DATA_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 401, "HART-Auth muss ohne Quelle 401 liefern"
    body = r.get_data(as_text=True)
    assert "neu verbinden" in body.lower(), "AUTH-8-Re-Pair-HTML erwartet"
    assert r.headers.get("Content-Type", "").startswith("text/html")


def test_daten_route_extern_mit_cookie_ist_200_und_rolling_refresh(app_client):
    """Gültiger xbuddy_session-Cookie → 200 + Set-Cookie (Rolling-Refresh)."""
    token = session_cookie.sign_session(42, TEST_BOT_TOKEN)
    app_client.set_cookie(session_cookie.COOKIE_NAME, token, domain="localhost")
    r = app_client.get(_DATA_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200, "gültiger Cookie muss durchlassen"
    assert session_cookie.COOKIE_NAME in r.headers.get("Set-Cookie", ""), \
        "Rolling-Refresh: frischer Cookie erwartet"


def test_daten_route_extern_mit_gueltigem_tma_ist_200(app_client):
    """Gültiger tma-Header + Familien-Mitglied (Stub) → 200 (Eltern-Mini-App)."""
    r = app_client.get(_DATA_ROUTE, headers={
        "X-Forwarded-For": "1.2.3.4",
        "Authorization": "tma " + _bau_init_data(user_id=42),
    })
    assert r.status_code == 200, "gültiger tma-Header eines Mitglieds muss durchlassen"


def test_daten_route_loopback_ohne_xff_ist_pass_through(app_client):
    """Server-zu-Server (127.0.0.1, kein XFF) → Pass-through 200 (AUTH-5)."""
    r = app_client.get(_DATA_ROUTE)
    assert r.status_code == 200, "Loopback ohne XFF muss durchlaufen (AUTH-5)"


def test_audio_route_extern_ohne_cookie_bleibt_public(app_client):
    """KRITISCH (T1640): die Audio-mp3-Route ist NICHT gegatet (AUTH-4 public).

    Fremd-Request ohne Cookie darf KEIN 401 sehen — sonst bräche das
    Kind-Tablet-Playback. 404 (kein Album x1) beweist: der View läuft, die
    Auth-Membran greift nicht (401 würde vor dem 404 stehen).
    """
    r = app_client.get(_AUDIO_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code != 401, (
        "Audio-mp3 muss PUBLIC bleiben (AUTH-4) — 401 bricht das Playback (T1640)"
    )
    assert r.status_code == 404, (
        "erwartet 404 (kein Album x1) — beweist, dass der View ohne Auth erreicht wird"
    )
