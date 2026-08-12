"""AUTH-11 „kleine b": wetter/photo/familie hinter dem Dual-Gate (#1844, T1844-S1).

specs/platform/auth.md AUTH-11: jede Route in der URL-Map trägt einen
Auth-Decorator oder steht namentlich in der Ausnahme-Liste. `/healthz` und
`/version` bleiben Ausnahmen (unangetastet); alle übrigen Routen in wetter,
photo und familie sind jetzt gegated.

`/display/…`-Routen sind Browser-/Kiosk-Flächen (Tablet) — kein tma-Kontext,
sondern der `xbuddy_session`-Cookie (AUTH-7b-Dual-Gate, `default_mode="hard"`,
Nic-Setzung 2026-08-11). Geprüft wird je Service EINE offene Route ohne Cookie
(→ 401) und mit gültigem Cookie (→ 200 bzw. 404):

  - wetter:  GET /display/wetter/heute
  - photo:   GET /display/photo/rahmen
  - familie: GET /static/<path:filename> — Flasks impliziter Default-Endpunkt
             (familie hat kein eigenes static/-Verzeichnis; der Request passiert
             den Gate und fällt danach mangels Datei auf 404 — das belegt, dass
             der Gate VOR dem fehlenden Static-Verzeichnis sitzt).

Lauf: python3 -m pytest tests/test_auth11_kleine_b.py -q
"""

from __future__ import annotations

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from familie import main as familie_main  # noqa: E402
from familie import registry as registry_mod  # noqa: E402
from photo import config as photo_config_mod  # noqa: E402
from photo import main as photo_main  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402
from wetter import config as wetter_config_mod  # noqa: E402
from wetter import main as wetter_main  # noqa: E402
from wetter import meteo as wetter_meteo_mod  # noqa: E402
from wetter.tests.conftest import DEMO_CONFIG as WETTER_DEMO_CONFIG  # noqa: E402
from wetter.tests.conftest import FakeTransport as _WetterFakeTransport  # noqa: E402

BOT_TOKEN = "123456:ABCdef_auth11testtoken"
SUBJECT = "tablet-elias-01"


# ---------------------------------------------------------------------------
# wetter — GET /display/wetter/heute (AUTH-11, T1844-S1)
# ---------------------------------------------------------------------------


@pytest.fixture
def wetter_client(tmp_path):
    cfg_path = tmp_path / "wetter.json"
    cfg_path.write_text(json.dumps(WETTER_DEMO_CONFIG), encoding="utf-8")
    cfg = wetter_config_mod.resolve(str(cfg_path))
    # WETTER-17: FakeTransport(fail=True) liefert den neutralen Fallback —
    # dieser Test prüft den AUTH-11-Gate, nicht die Meteo-Anbindung.
    anbindung = wetter_meteo_mod.WetterAnbindung(
        _WetterFakeTransport(fail=True),
        cfg.stunde_morgens, cfg.stunde_mittags, cfg.sunscreen_uv)
    wetter_main.configure(cfg, anbindung, config_path=str(cfg_path),
                          bot_token=BOT_TOKEN)
    wetter_main.app.testing = True
    return wetter_main.app.test_client()


def test_wetter_heute_ohne_cookie_ist_401(wetter_client):
    """AC2: GET /display/wetter/heute ohne Cookie → 401 (AUTH-7b-Dual-Gate hard)."""
    resp = wetter_client.get("/display/wetter/heute")
    assert resp.status_code == 401
    assert "neu verbunden" in resp.get_data(as_text=True).lower()


def test_wetter_heute_mit_cookie_ist_200(wetter_client):
    """AC2: GET /display/wetter/heute mit gültigem Cookie → 200 + Rolling-Refresh."""
    wetter_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(SUBJECT, BOT_TOKEN))
    resp = wetter_client.get("/display/wetter/heute")
    assert resp.status_code == 200
    assert sc.COOKIE_NAME in resp.headers.get("Set-Cookie", "")


# ---------------------------------------------------------------------------
# photo — GET /display/photo/rahmen (AUTH-11, T1844-S1)
# ---------------------------------------------------------------------------


@pytest.fixture
def photo_client(tmp_path):
    cfg = photo_config_mod.resolve(env={})
    lib = tmp_path / "medien"
    lib.mkdir()
    cfg.library_verzeichnis = str(lib)
    photo_main.configure(cfg, bot_token=BOT_TOKEN)
    photo_main.app.testing = True
    return photo_main.app.test_client()


def test_photo_rahmen_ohne_cookie_ist_401(photo_client):
    """AC2: GET /display/photo/rahmen ohne Cookie → 401 (AUTH-7b-Dual-Gate hard)."""
    resp = photo_client.get("/display/photo/rahmen")
    assert resp.status_code == 401
    assert "neu verbunden" in resp.get_data(as_text=True).lower()


def test_photo_rahmen_mit_cookie_ist_200(photo_client):
    """AC2: GET /display/photo/rahmen mit gültigem Cookie → 200 + Rolling-Refresh."""
    photo_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(SUBJECT, BOT_TOKEN))
    resp = photo_client.get("/display/photo/rahmen")
    assert resp.status_code == 200
    assert sc.COOKIE_NAME in resp.headers.get("Set-Cookie", "")


# ---------------------------------------------------------------------------
# familie — GET /static/<path:filename> (Flasks impliziter Endpunkt, AUTH-11)
# ---------------------------------------------------------------------------
#
# familie hat kein eigenes static/-Verzeichnis (die Datenrouten sind bereits
# per require_init_data gegated, s. familie/tests/test_auth_hart.py) — offen
# war nur der implizite Werkzeug-static-Endpunkt. AUTH-11 geht von der
# URL-Map aus, nicht von der Nützlichkeit: ohne Cookie muss der Gate VOR dem
# fehlenden Verzeichnis greifen (401, nicht 404). Mit Cookie passiert der
# Request den Gate und fällt danach mangels Datei auf 404 — genau das belegt,
# dass der Gate wirklich davorsitzt und nicht bloß zufällig 404 zurückkäme.


@pytest.fixture
def familie_client():
    reg = registry_mod.Registry()
    familie_main.configure(reg, foto_verzeichnis="/tmp/fake-fotos-auth11",
                           bot_token=BOT_TOKEN)
    familie_main.app.config["TESTING"] = True
    return familie_main.app.test_client()


def test_familie_static_ohne_cookie_ist_401(familie_client):
    """AC2: GET /static/<datei> ohne Cookie → 401 (Gate sitzt vor dem 404)."""
    resp = familie_client.get("/static/irgendwas.css")
    assert resp.status_code == 401
    assert "neu verbinden" in resp.get_data(as_text=True).lower()


def test_familie_static_mit_cookie_ist_404_nicht_401(familie_client):
    """AC2: mit gültigem Cookie passiert der Request den Gate — 404 (keine
    Datei, kein static/-Verzeichnis), NICHT 401. Der 404 ist hier der
    Nachweis, dass der Gate DAVOR sitzt (401 wäre der Gate, 404 ist danach)."""
    familie_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(SUBJECT, BOT_TOKEN))
    resp = familie_client.get("/static/irgendwas.css")
    assert resp.status_code == 404
