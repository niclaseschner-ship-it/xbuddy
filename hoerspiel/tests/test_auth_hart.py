"""HART-Cookie-Auth der hoerspiel-Datenrouten (T1640, auth.md AUTH-2/3/5/8).

Phase-3-Migration: die hoerspiel-Datenrouten (config, alben, alben/<id>/manifest,
resume, themen, folgen-vorschlag) tragen jetzt den HART-Factory-Decorator
(`tools/initdata/auth_gate.make_require_init_data`, Name `require_init_data`).
Diese Suite belegt die vier Auth-Zweige an einer echten AUTH-3-Route plus die
Audio-mp3-Route:

  - extern OHNE Quelle (X-Forwarded-For gesetzt) → 401 (hoerspiel-AUTH-8-HTML),
  - extern MIT gültigem Cookie → 200 + Rolling-Refresh (Set-Cookie),
  - extern MIT gültigem tma-Header + Familien-Mitglied → 200,
  - Loopback (127.0.0.1 ohne XFF) → Pass-through 200,
  - GEDREHT (T1833, #1805, AUTH-11): die Audio-mp3-Route ist NICHT mehr PUBLIC.
    Der frühere AUTH-4-Publicness-Eintrag für `alben/<id>/audio/<track>.mp3`
    ist per Nic-Setzung 2026-08-11 (auth.md AUTH-3.a-ÜBERHOLT-Passage, deckt
    diese Route über die generische Vorrang-Klausel eines parallel
    entstehenden AUTH-4-ÜBERHOLT-Markers ab) aufgehoben — Nic hat die Route
    am 2026-08-11 namentlich mitentschieden ("auch die Kind-Tablet-Audio-
    Route"), weil der Kiosk seit dem RAT-32-Cookie-Umbau ein gültiges Cookie
    bis 2026-11-09 trägt. Die frühere "sonst bricht das Playback"-Prämisse war
    eine behauptete, nie gemessene Folge (dieselbe Klasse Fehlschluss wie die
    inzwischen widerlegte PBE-3-"cookieloses Kiosk-Gerät"-Prämisse) — extern
    OHNE Identität liefert die Route jetzt wie jede andere AUTH-3-Datenroute
    401.
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
# GEDREHT (T1833, #1805, AUTH-11, AUTH-4-ÜBERHOLT): Audio-mp3 ist jetzt
# require_init_data-gegated wie jede andere Datenroute dieses Buddys — die
# frühere PUBLIC-Ausnahme (AUTH-4) ist per Nic-Setzung 2026-08-11 aufgehoben.
# 404 (kein Album) bleibt der Beleg für den erreichten View, aber jetzt NUR
# noch MIT Identität (s. test_audio_route_extern_mit_cookie_ist_200_wegen_404
# unten) — ohne Identität steht die Auth-Membran davor (401).
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


def test_audio_route_extern_ohne_identitaet_ist_401(app_client):
    """GEDREHT (T1833, #1805, AUTH-11): die Audio-mp3-Route verlangt jetzt Identität.

    Bis 2026-08-11 stand hier die Umkehrung — "Audio-mp3 bleibt PUBLIC (AUTH-4),
    401 bricht das Kind-Tablet-Playback". Die Prämisse war eine BEHAUPTETE,
    nie gemessene Folge (dieselbe Fehlerklasse wie die zwischenzeitlich am
    Live-Stand widerlegte PBE-3-Prämisse "cookieloses Kiosk-Gerät"). Nic hat
    diese Route am 2026-08-11 namentlich mitentschieden ("auch die
    Kind-Tablet-Audio-Route") — der Kiosk trägt seit dem RAT-32-Cookie-Umbau
    ein gültiges Cookie bis 2026-11-09. Der frühere AUTH-4-PUBLIC-Eintrag ist
    über die generische Vorrang-Klausel des parallel entstehenden
    AUTH-4-ÜBERHOLT-Markers (spec/1805-auth11-bootstrap-ausnahmen) abgedeckt.
    Fremd-Request ohne Cookie/tma → 401 wie jede andere require_init_data-Route
    (s. test_daten_route_extern_ohne_quelle_ist_401 oben, dasselbe Muster).
    """
    r = app_client.get(_AUDIO_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 401, (
        "Audio-mp3 muss ohne Identität 401 liefern (AUTH-11, Nic-Setzung 2026-08-11 "
        "hebt den früheren AUTH-4-PUBLIC-Stand auf)"
    )
    body = r.get_data(as_text=True)
    assert "neu verbinden" in body.lower(), "AUTH-8-Re-Pair-HTML erwartet"


def test_audio_route_extern_mit_cookie_ist_200_wegen_404(app_client):
    """Positiv-Gegenprobe zur gedrehten Zusicherung oben: mit gültigem Cookie
    kommt die Audio-mp3-Route durch — 404 (kein Album x1) beweist, dass der
    View erreicht wird und nicht die Auth-Membran greift."""
    token = session_cookie.sign_session(42, TEST_BOT_TOKEN)
    app_client.set_cookie(session_cookie.COOKIE_NAME, token, domain="localhost")
    r = app_client.get(_AUDIO_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 404, (
        "erwartet 404 (kein Album x1) mit gültigem Cookie — beweist, dass der "
        "View hinter der Auth-Membran erreicht wird"
    )
