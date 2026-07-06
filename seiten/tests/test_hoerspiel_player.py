"""AUTH-2 Cookie-Gate — Hörspiel-Player-Routen (#1292, HSP-47).

Prüft das Cookie-Gate auf beiden Player-Routen:
  AC1 — kein/ungültiger Cookie → 401 (HTML-Shell + Assets).
  AC2 — gültiger xbuddy_session-Cookie → 200.

Muster: essen/tests/test_auth_cookie.py (sign_session / COOKIE_NAME).
Anker: specs/platform/auth.md AUTH-2 (Cookie-only) Hörspiel-Player-PWA.

Lauf: python3 -m pytest seiten/tests/test_hoerspiel_player.py -x -v
"""

from __future__ import annotations

import os
import sys

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from seiten import main as seiten_main  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_TEST_BOT_TOKEN = "testtoken-t1292-auth"
_HTML_URL = "/seiten/hoerspiel/player"
_MANIFEST_URL = "/seiten/hoerspiel/player/manifest.json"
_SW_URL = "/seiten/hoerspiel/player/sw.js"
_UNKNOWN_URL = "/seiten/hoerspiel/player/gibt-es-nicht.txt"
_TRAVERSAL_URL = "/seiten/hoerspiel/player/..%2f..%2fmain.py"

_VALID_COOKIE = sc.sign_session("tablet-player-test", _TEST_BOT_TOKEN)


@pytest.fixture(autouse=True)
def reset_runtime():
    """Player-Service konfigurieren — analog test_hoerspiel_player_pwa.py."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token=_TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — kein Cookie → 401 ───────────────────────────────────────────────────


def test_html_kein_cookie_gibt_401(client):
    """AC1: GET /seiten/hoerspiel/player ohne Cookie → 401 (HSP-47)."""
    resp = client.get(_HTML_URL)
    assert resp.status_code == 401


def test_html_ungueltiger_cookie_gibt_401(client):
    """AC1: ungültiger/gefälschter Cookie → 401."""
    client.set_cookie(sc.COOKIE_NAME, "kaputt.abc.deadbeef")
    resp = client.get(_HTML_URL)
    assert resp.status_code == 401


def test_manifest_kein_cookie_gibt_401(client):
    """AC1: GET manifest.json ohne Cookie → 401."""
    resp = client.get(_MANIFEST_URL)
    assert resp.status_code == 401


def test_sw_kein_cookie_gibt_401(client):
    """AC1: GET sw.js ohne Cookie → 401."""
    resp = client.get(_SW_URL)
    assert resp.status_code == 401


# ── AC2 — gültiger Cookie → 200 ──────────────────────────────────────────────


def test_html_gueltiger_cookie_gibt_200(client):
    """AC2: GET HTML-Shell mit gültigem Cookie → 200."""
    client.set_cookie(sc.COOKIE_NAME, _VALID_COOKIE)
    resp = client.get(_HTML_URL)
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/html")


def test_manifest_gueltiger_cookie_gibt_200(client):
    """AC2: GET manifest.json mit gültigem Cookie → 200 + manifest+json."""
    client.set_cookie(sc.COOKIE_NAME, _VALID_COOKIE)
    resp = client.get(_MANIFEST_URL)
    assert resp.status_code == 200
    assert "manifest" in resp.headers.get("Content-Type", "")


def test_sw_gueltiger_cookie_gibt_200(client):
    """AC2: GET sw.js mit gültigem Cookie → 200."""
    client.set_cookie(sc.COOKIE_NAME, _VALID_COOKIE)
    resp = client.get(_SW_URL)
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("Content-Type", "")


def test_unbekanntes_asset_mit_cookie_gibt_404(client):
    """Auth passiert, 404-Guard greift danach: unbekanntes Asset → 404."""
    client.set_cookie(sc.COOKIE_NAME, _VALID_COOKIE)
    resp = client.get(_UNKNOWN_URL)
    assert resp.status_code == 404


def test_traversal_mit_cookie_gibt_404(client):
    """Auth passiert, Traversal-Guard greift danach: Path-Traversal → 404."""
    client.set_cookie(sc.COOKIE_NAME, _VALID_COOKIE)
    resp = client.get(_TRAVERSAL_URL)
    assert resp.status_code == 404
