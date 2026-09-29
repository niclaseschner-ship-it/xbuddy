"""#1969: die zwei extern geöffneten Leserouten hinter dem Cookie (auth.md).

nginx reicht GET /api/v1/familie/personen und GET /api/v1/familie/foto/<id>
an den familie-Dienst durch und setzt dabei X-Forwarded-For. Der Dienst sieht
den Request also von 127.0.0.1, aber MIT X-Forwarded-For — genau diese Lage
bildet diese Suite nach (REMOTE_ADDR 127.0.0.1 explizit + XFF), damit belegt
ist, dass der Loopback-Bypass (AUTH-5) extern nicht greift und AUTH-3 HART
gilt: ohne Cookie 401, mit gültigem xbuddy_session-Cookie 200.
"""

import json
import os
import sys

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

# Lage hinter nginx: Peer ist der lokale Proxy, XFF trägt den echten Client.
_HINTER_NGINX = {"environ_base": {"REMOTE_ADDR": "127.0.0.1"},
                 "headers": {"X-Forwarded-For": "203.0.113.5"}}

# Kleine Registry: emil mit Foto-Datei, mia ohne Datei-Bedarf.
_REGISTRY = {
    "erwachsene": [{"id": "emil", "name": "Emil", "ring": "blue", "foto": "emil.png"}],
    "kinder": [{"id": "mia", "name": "Mia", "ring": "purple"}],
}
# Inhalt ist für die Route egal (send_file) — Hauptsache, er kommt 1:1 zurück.
_FOTO_BYTES = b"\x89PNG\r\n\x1a\n-test-1969"

_LESEROUTEN = ["/api/v1/familie/personen", "/api/v1/familie/foto/emil"]


class _FamilieStub:
    def get_telegram_ids(self):
        return {_TEST_USER_ID}


@pytest.fixture
def app_client(tmp_path):
    reg_path = tmp_path / "familie.json"
    reg_path.write_text(json.dumps(_REGISTRY))
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    (fotos / "emil.png").write_bytes(_FOTO_BYTES)
    familie_main.configure(
        registry_mod.load(str(reg_path)),
        foto_verzeichnis=str(fotos),
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
        familie_client=_FamilieStub(),
    )
    familie_main.app.config["TESTING"] = True
    return familie_main.app.test_client()


@pytest.mark.parametrize("route", _LESEROUTEN)
def test_1969_hinter_nginx_ohne_cookie_ist_401(app_client, route):
    """Extern (XFF gesetzt, Peer 127.0.0.1) ohne Cookie → 401, kein Bypass."""
    r = app_client.get(route, **_HINTER_NGINX)
    assert r.status_code == 401, f"{route}: extern ohne Cookie muss 401 sein"


@pytest.mark.parametrize("route", _LESEROUTEN)
def test_1969_hinter_nginx_mit_cookie_ist_200(app_client, route):
    """Extern (XFF gesetzt) mit gültigem xbuddy_session-Cookie → 200."""
    token = session_cookie.sign_session(_TEST_USER_ID, TEST_BOT_TOKEN)
    app_client.set_cookie(session_cookie.COOKIE_NAME, token, domain="localhost")
    r = app_client.get(route, **_HINTER_NGINX)
    assert r.status_code == 200, f"{route}: gültiger Cookie muss 200 liefern"


def test_1969_personen_mit_cookie_liefert_die_familie(app_client):
    token = session_cookie.sign_session(_TEST_USER_ID, TEST_BOT_TOKEN)
    app_client.set_cookie(session_cookie.COOKIE_NAME, token, domain="localhost")
    r = app_client.get("/api/v1/familie/personen", **_HINTER_NGINX)
    assert {p["id"] for p in r.get_json()} == {"emil", "mia"}


def test_1969_foto_mit_cookie_liefert_das_bild(app_client):
    token = session_cookie.sign_session(_TEST_USER_ID, TEST_BOT_TOKEN)
    app_client.set_cookie(session_cookie.COOKIE_NAME, token, domain="localhost")
    r = app_client.get("/api/v1/familie/foto/emil", **_HINTER_NGINX)
    assert r.data == _FOTO_BYTES
