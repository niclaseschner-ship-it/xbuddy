"""AUTH-2/3/8 — essen-Decorator HART + Cookie-Pfad (T948, AC2).

Prüft den auf HART geflippten `require_init_data` (auth.md AUTH-2/3/5/8):
  - Session-Cookie `xbuddy_session` valide → 200 + Rolling-Refresh-Set-Cookie.
  - Weder Cookie noch tma noch Loopback → HART 401 mit AUTH-8-HTML.
  - Ungültiger/abgelaufener Cookie → 401.
  - tma-Pfad (Mini-App) bricht NICHT (valider Header + FAM-Mitglied → 200).
  - Loopback (127.0.0.1, kein X-Forwarded-For) → 200 (AUTH-5, Server-zu-Server).

Alle „externen" Requests setzen X-Forwarded-For, um den AUTH-5-Loopback-Bypass
zu umgehen (nginx setzt den Header im Produktiv-Pfad). Ein Familie-Client-Stub
wird injiziert, damit der FAM-Check deterministisch ist (kein Live-Service).
"""

from __future__ import annotations

import os
import sys

_ESSEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_ESSEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from essen import main as essen_main  # noqa: E402
from essen.tests.conftest import TEST_BOT_TOKEN, _baue_init_data  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_XFF = {"X-Forwarded-For": "1.2.3.4"}


class _FamilieStub:
    """Deterministischer FAM-Lookup — user_id 42 ist Mitglied."""

    def get_telegram_ids(self):
        return {42, 7}


@pytest.fixture
def raw_client(demo_paths):
    """Test-Client OHNE Auto-Auth-Header (anders als die conftest-`client`-
    Fixture, die tma automatisch setzt) und mit deterministischem FAM-Stub."""
    for snap in ("wuensche_snapshot", "einkauf_snapshot", "zaehler_snapshot",
                 "gerichte_snapshot", "katalog_snapshot"):
        essen_main.runtime[snap] = None
    essen_main.configure(
        demo_paths,
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        familie_client=_FamilieStub(),
    )
    return essen_main.app.test_client()


def test_gueltiger_cookie_gibt_200_und_rolling_refresh(raw_client):
    raw_client.set_cookie(sc.COOKIE_NAME,
                          sc.sign_session("tablet-elias-01", TEST_BOT_TOKEN))
    resp = raw_client.get("/api/v1/essen/wuensche", headers=_XFF)
    assert resp.status_code == 200
    # Rolling-Refresh: die Antwort setzt xbuddy_session neu (auth.md AUTH-2:78).
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Lax" in set_cookie


def test_keine_quelle_gibt_hart_401_mit_auth8(raw_client):
    resp = raw_client.get("/api/v1/essen/wuensche", headers=_XFF)
    assert resp.status_code == 401
    body = resp.get_data(as_text=True)
    assert "neu verbunden" in body  # AUTH-8-Anweisungsseite (HTML, kein roher 401)
    assert resp.headers["Content-Type"].startswith("text/html")


def test_ungueltiger_cookie_gibt_401(raw_client):
    raw_client.set_cookie(sc.COOKIE_NAME, "kaputt.123.deadbeef")
    resp = raw_client.get("/api/v1/essen/wuensche", headers=_XFF)
    assert resp.status_code == 401


def test_abgelaufener_cookie_gibt_401(raw_client):
    raw_client.set_cookie(
        sc.COOKIE_NAME,
        sc.sign_session("tablet-elias-01", TEST_BOT_TOKEN, ttl_seconds=10, now=1000),
    )
    resp = raw_client.get("/api/v1/essen/wuensche", headers=_XFF)
    assert resp.status_code == 401


def test_tma_pfad_bricht_nicht(raw_client):
    # Valider tma-Header, FAM-Stub kennt user 42 → Mitglied → 200.
    init_data = _baue_init_data(bot_token=TEST_BOT_TOKEN, user_id=42)
    resp = raw_client.get(
        "/api/v1/essen/wuensche",
        headers={**_XFF, "Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200


def test_tma_nichtmitglied_gibt_403(raw_client):
    init_data = _baue_init_data(bot_token=TEST_BOT_TOKEN, user_id=999)
    resp = raw_client.get(
        "/api/v1/essen/wuensche",
        headers={**_XFF, "Authorization": "tma " + init_data},
    )
    assert resp.status_code == 403


def test_ungueltiger_tma_header_gibt_401(raw_client):
    resp = raw_client.get(
        "/api/v1/essen/wuensche",
        headers={**_XFF, "Authorization": "tma total-kaputt"},
    )
    assert resp.status_code == 401


def test_loopback_ohne_auth_gibt_200(raw_client):
    # Kein X-Forwarded-For, remote_addr=127.0.0.1 (Test-Default) → AUTH-5-Bypass.
    resp = raw_client.get("/api/v1/essen/wuensche")
    assert resp.status_code == 200


def test_delete_gericht_ist_geschuetzt(raw_client):
    # OD5: DELETE gericht_loeschen trägt den Decorator → 401 ohne Auth.
    resp = raw_client.delete("/api/v1/essen/katalog/gerichte/xyz", headers=_XFF)
    assert resp.status_code == 401
