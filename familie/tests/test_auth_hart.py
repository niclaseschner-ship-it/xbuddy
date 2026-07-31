"""HART-Cookie-Auth der familie-Datenrouten (#1638, auth.md AUTH-2/3/5/8).

Familie-Datenrouten enthalten PII (Namen, Fotos, Telegram-IDs) und sind
jetzt mit `require_init_data` (HART-Factory) gegated. Diese Suite belegt
die vier Auth-Zweige an einer echten familie-AUTH-3-Route:

  - extern OHNE Quelle (X-Forwarded-For gesetzt) → 401 (AUTH-8-HTML),
  - extern MIT gültigem Cookie → 200 + Rolling-Refresh (Set-Cookie),
  - extern MIT gültigem tma-Header + Familien-Mitglied → 200,
  - Loopback (127.0.0.1 ohne XFF) → Pass-through 200.

Zusätzlich: Foto-Route mit Cookie (plan-Mini-App lädt <img> same-origin).

Loopback-Note: interne Buddies (plan/kibuddy/eltern-chat/hoerspiel) sprechen
familie via 127.0.0.1:5010 ohne X-Forwarded-For → AUTH-5-Bypass greift.
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse

import pytest

_FAMILIE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_FAMILIE_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from familie import main as familie_main  # noqa: E402
from familie import registry as registry_mod  # noqa: E402
from tools.initdata import session_cookie  # noqa: E402

TEST_BOT_TOKEN = "123456:ABCdef_testtoken"
_TEST_USER_ID = 42


def _bau_init_data(bot_token=TEST_BOT_TOKEN, user_id=_TEST_USER_ID):
    """Baut einen validen Telegram-initData-String mit korrektem HMAC."""
    auth_date = int(time.time())
    user_json = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))
    felder = {"auth_date": str(auth_date), "user": user_json}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(felder.items()))
    secret_key = hmac.new(
        key=b"WebAppData", msg=bot_token.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        key=secret_key, msg=data_check_string.encode("utf-8"), digestmod=hashlib.sha256
    ).hexdigest()
    felder["hash"] = computed_hash
    return urllib.parse.urlencode(felder)


class _FamilieStub:
    """Test-Doppel: liefert die Familien-IDs (user_id=42 enthalten)."""

    def get_telegram_ids(self):
        return {_TEST_USER_ID}


def _configure():
    """Setzt die runtime-Naht für Auth-Tests (In-Memory-Registry)."""
    reg = registry_mod.Registry()
    familie_main.configure(
        reg,
        foto_verzeichnis="/tmp/fake-fotos",
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        familie_client=_FamilieStub(),
    )


# Eine echte AUTH-3-Daten-Route: GET /personen (kein data_path-Zwang).
_ROUTE = "/api/v1/familie/personen"


@pytest.fixture
def app_client():
    _configure()
    familie_main.app.config["TESTING"] = True
    return familie_main.app.test_client()


def test_extern_ohne_quelle_ist_401(app_client):
    """Fremd-Request (X-Forwarded-For, kein Cookie/tma) → HART 401 mit AUTH-8-HTML."""
    r = app_client.get(_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 401, "HART-Auth muss ohne Quelle 401 liefern"
    body = r.get_data(as_text=True)
    assert "neu verbinden" in body.lower(), "AUTH-8-Re-Pair-HTML erwartet, nicht roher 401"
    assert r.headers.get("Content-Type", "").startswith("text/html")


def test_extern_mit_cookie_ist_200_und_rolling_refresh(app_client):
    """Gültiger xbuddy_session-Cookie → 200 + Set-Cookie (Rolling-Refresh, AUTH-2)."""
    token = session_cookie.sign_session(_TEST_USER_ID, TEST_BOT_TOKEN)
    app_client.set_cookie(session_cookie.COOKIE_NAME, token, domain="localhost")
    r = app_client.get(_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200, "gültiger Cookie muss durchlassen"
    set_cookie = r.headers.get("Set-Cookie", "")
    assert session_cookie.COOKIE_NAME in set_cookie, "Rolling-Refresh: frischer Cookie erwartet"


def test_extern_mit_gueltigem_tma_ist_200(app_client):
    """Gültiger tma-Header + Familien-Mitglied (Stub) → 200 (Eltern-Mini-App-Pfad)."""
    r = app_client.get(_ROUTE, headers={
        "X-Forwarded-For": "1.2.3.4",
        "Authorization": "tma " + _bau_init_data(user_id=_TEST_USER_ID),
    })
    assert r.status_code == 200, "gültiger tma-Header eines Mitglieds muss durchlassen"


def test_loopback_ohne_xff_ist_pass_through(app_client):
    """Server-zu-Server (127.0.0.1, kein X-Forwarded-For) → Pass-through 200 (AUTH-5).

    Belegt: interne Buddies (plan/kibuddy/eltern-chat/hoerspiel) lesen familie
    via 127.0.0.1:5010 ohne XFF — Loopback-Bypass greift, kein Auth-Loop.
    """
    r = app_client.get(_ROUTE)  # remote_addr default 127.0.0.1, kein XFF
    assert r.status_code == 200, "Loopback ohne XFF muss durchlaufen (AUTH-5)"


def test_foto_route_mit_cookie_ist_200_oder_404(app_client):
    """Foto-Route mit gültigem Cookie: 200 (Foto vorhanden) oder 404 (kein Foto) — NICHT 401.

    plan-Mini-App lädt <img src='/api/v1/familie/foto/<id>'> same-origin;
    Browser sendet Cookie → Cookie-Zweig des Decorators → 200 (oder 404 wenn
    kein Foto, aber NICHT 401). Belegt: Cookie geht durch.
    """
    token = session_cookie.sign_session(_TEST_USER_ID, TEST_BOT_TOKEN)
    app_client.set_cookie(session_cookie.COOKIE_NAME, token, domain="localhost")
    r = app_client.get("/api/v1/familie/foto/unbekannt-person",
                       headers={"X-Forwarded-For": "1.2.3.4"})
    # 404 (kein Foto/unbekannte Person) ist OK — wichtig ist NICHT 401.
    assert r.status_code != 401, "Cookie-Pfad muss Foto-Route ohne 401 durch (war 401 → PII-Bug)"
    assert r.status_code in (200, 404), "Erwartete 200 oder 404, nicht %d" % r.status_code


def test_foto_route_ohne_quelle_ist_401(app_client):
    """Foto-Route ohne Auth-Quelle → 401 (schließt Funnel-Foto-PII-Leak)."""
    r = app_client.get("/api/v1/familie/foto/emil",
                       headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 401, "Foto-Route muss ohne Quelle 401 liefern (PII-Schutz)"
