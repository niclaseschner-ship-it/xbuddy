"""HART-Cookie-Auth der routine-Datenrouten (#1639, auth.md AUTH-2/3/5/8).

Phase-2-Migration: der routine-Decorator `require_init_data` ist von SOFT
(V3 #898, Pass-through ohne Quelle) auf die HART-Factory
(`tools/initdata/auth_gate.make_require_init_data`) geflippt. Diese Suite
belegt die vier Auth-Zweige an einer echten routine-AUTH-3-Route:

  - extern OHNE Quelle (X-Forwarded-For gesetzt) → 401 (routine-AUTH-8-HTML),
  - extern MIT gültigem Cookie → 200 + Rolling-Refresh (Set-Cookie),
  - extern MIT gültigem tma-Header + Familien-Mitglied → 200,
  - Loopback (127.0.0.1 ohne XFF) → Pass-through 200.
"""

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import main as main_mod  # noqa: E402  # isort:skip
from routine.tests._test_auth import (  # noqa: E402  # isort:skip
    TEST_BOT_TOKEN,
    bau_init_data,
)
from tools.initdata import session_cookie  # noqa: E402  # isort:skip

# Eine echte AUTH-3-Route (READ, ohne data_path-Zwang-500: config braucht
# data_path, items GET liefert auch ohne 200). Wir nehmen items GET.
_ROUTE = "/api/v1/routine/items"


class _FamilieStub:
    """Fail-open-Doppel: liefert die Familien-IDs (user_id=42 enthalten)."""

    def get_telegram_ids(self):
        return {42}


def _configure(tmp_path):
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "zeitzone": "Europe/Berlin",
        "items": [{"id": "a", "label": "A", "piktogramm": "1", "quelle": "default"}],
    }))
    cfg = config_mod.resolve_data(str(p))
    main_mod.configure(
        cfg,
        data_path=str(p),
        store_path=str(tmp_path / "store.json"),
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        familie_client=_FamilieStub(),
    )


@pytest.fixture
def app_client(tmp_path):
    _configure(tmp_path)
    main_mod.app.config["TESTING"] = True
    return main_mod.app.test_client()


def test_extern_ohne_quelle_ist_401(app_client):
    """Fremd-Request (X-Forwarded-For, kein Cookie/tma) → HART 401 mit AUTH-8-HTML."""
    r = app_client.get(_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 401, "HART-Auth muss ohne Quelle 401 liefern"
    body = r.get_data(as_text=True)
    assert "neu verbinden" in body.lower(), "AUTH-8-Re-Pair-HTML erwartet, nicht roher 401"
    assert r.headers.get("Content-Type", "").startswith("text/html")


def test_extern_mit_cookie_ist_200_und_rolling_refresh(app_client):
    """Gültiger xbuddy_session-Cookie → 200 + Set-Cookie (Rolling-Refresh, AUTH-2)."""
    token = session_cookie.sign_session(42, TEST_BOT_TOKEN)
    app_client.set_cookie(session_cookie.COOKIE_NAME, token, domain="localhost")
    r = app_client.get(_ROUTE, headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 200, "gültiger Cookie muss durchlassen"
    set_cookie = r.headers.get("Set-Cookie", "")
    assert session_cookie.COOKIE_NAME in set_cookie, "Rolling-Refresh: frischer Cookie erwartet"


def test_extern_mit_gueltigem_tma_ist_200(app_client):
    """Gültiger tma-Header + Familien-Mitglied (Stub) → 200 (Eltern-Mini-App-Pfad)."""
    r = app_client.get(_ROUTE, headers={
        "X-Forwarded-For": "1.2.3.4",
        "Authorization": "tma " + bau_init_data(user_id=42),
    })
    assert r.status_code == 200, "gültiger tma-Header eines Mitglieds muss durchlassen"


def test_loopback_ohne_xff_ist_pass_through(app_client):
    """Server-zu-Server (127.0.0.1, kein X-Forwarded-For) → Pass-through 200 (AUTH-5)."""
    r = app_client.get(_ROUTE)  # remote_addr default 127.0.0.1, kein XFF
    assert r.status_code == 200, "Loopback ohne XFF muss durchlaufen (AUTH-5)"
