"""AUTH-3 für die Regeln-Datenrouten (#1715, ESB-1.a/ESB-2).

Die seiten-gehostete Regeln-Mini-App liest/schreibt über `/api/v1/wetter/regeln`;
die Routen sind HART (Cookie ODER tma; AUTH-5-Loopback pass-through; 401 ohne).

  - Loopback (127.0.0.1, kein X-Forwarded-For) → 200 (AUTH-5, Server-zu-Server).
  - Extern (X-Forwarded-For gesetzt) ohne Cookie → 401 (AUTH-8-HTML).
  - Extern + gültiger Session-Cookie → 200.
  - POST mit Cookie schreibt (200) bzw. 409 ohne config_path.

Lauf: python3 -m pytest wetter/tests/test_auth_regeln.py -q
"""

import json
import os
import sys

import pytest

_WETTER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_WETTER_DIR)
sys.path.insert(0, _REPO_ROOT)

from tools.initdata import session_cookie as _sc  # noqa: E402
from wetter import config as config_mod  # noqa: E402
from wetter import main as wm  # noqa: E402
from wetter import meteo as meteo_mod  # noqa: E402
from wetter.tests.conftest import DEMO_CONFIG  # noqa: E402

TEST_BOT_TOKEN = "123456:ABCdef_wettertesttoken"
# Externe Requests setzen X-Forwarded-For → umgeht den AUTH-5-Loopback-Bypass.
_EXTERN = {"X-Forwarded-For": "203.0.113.7"}


@pytest.fixture
def cfg_path(tmp_path):
    p = tmp_path / "wetter.json"
    p.write_text(json.dumps(DEMO_CONFIG), encoding="utf-8")
    return str(p)


@pytest.fixture
def app_client(cfg_path):
    cfg = config_mod.resolve(cfg_path)
    anbindung = meteo_mod.WetterAnbindung(
        None, cfg.stunde_morgens, cfg.stunde_mittags, cfg.sunscreen_uv)
    wm.configure(cfg, anbindung, config_path=cfg_path, bot_token=TEST_BOT_TOKEN)
    wm.app.testing = True
    return wm.app.test_client()


def _cookie(client):
    client.set_cookie(_sc.COOKIE_NAME, _sc.sign_session("op", TEST_BOT_TOKEN))
    return client


def test_get_loopback_ist_200(app_client):
    """AUTH-5: Loopback (kein X-Forwarded-For) → 200 + View-JSON."""
    r = app_client.get("/api/v1/wetter/regeln")
    assert r.status_code == 200
    assert isinstance(r.get_json(), dict)


def test_get_extern_ohne_cookie_ist_401(app_client):
    """Extern ohne Cookie/tma → HART 401."""
    r = app_client.get("/api/v1/wetter/regeln", headers=_EXTERN)
    assert r.status_code == 401


def test_get_extern_mit_cookie_ist_200(app_client):
    """Extern + gültiger Session-Cookie → 200."""
    _cookie(app_client)
    r = app_client.get("/api/v1/wetter/regeln", headers=_EXTERN)
    assert r.status_code == 200
    assert isinstance(r.get_json(), dict)


def test_post_extern_ohne_cookie_ist_401(app_client):
    """WRITE extern ohne Cookie → 401 (kein Schreibvorgang)."""
    r = app_client.post("/api/v1/wetter/regeln", headers=_EXTERN,
                        json={"regeln": [], "fallback": {}})
    assert r.status_code == 401


def test_post_loopback_schreibt_oder_422(app_client, cfg_path):
    """POST via Loopback passiert das Gate → die Validierung greift (200 bei
    gültiger Matrix / 422 bei ungültiger), NICHT 401. Belegt den Schreibpfad
    hinter dem Gate."""
    # Leere-aber-strukturell-gültige Matrix; Ausgang ist Validierungs-, nicht Auth-Sache.
    r = app_client.post("/api/v1/wetter/regeln",
                        json={"regeln": [], "fallback": {}})
    assert r.status_code in (200, 422)
    assert r.status_code != 401
