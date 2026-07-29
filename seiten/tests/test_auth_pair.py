"""AUTH-2.a — Pairing-Endpoint /auth/pair (T948, RAT-31 E6c).

Testet den seiten-Endpoint GET /auth/pair?token=<X> (auth.md AUTH-2.a):
  - gültiger Token → 302 auf /api/v1/seiten/uebersicht (SREG-12, neutral)
    + Set-Cookie xbuddy_session (HttpOnly/Secure/SameSite=Lax).
  - ungültiger/abgelaufener/fehlender Token → 400 mit Anweisungsseite.
  - Cookie-Subjekt ist das Token-Subjekt (verifizierbar über die Lib).

RAT-31 E6c (Nic-Setzung 2026-07-29): KEINE geraete-Registry mehr — kein
paired_at-Write, keine verwendungs-abhängige Ziel-Ableitung. Alle Geräte
landen neutral auf der Übersicht; die Rolle wählt das Elternteil beim
PWA-Install.

Lauf: python3 -m pytest seiten/tests/test_auth_pair.py -q
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

BOT_TOKEN = "123456:ABCdef_testtoken"
SUBJEKT_ID = "tablet-elias-01"


@pytest.fixture
def client():
    """Standard-Fixture: Bot-Token gesetzt, keine geraete-Registry mehr."""
    seiten_main.configure(bot_token=BOT_TOKEN)
    return seiten_main.app.test_client()


def test_gueltiger_token_setzt_cookie_und_redirected_neutral(client):
    token = sc.sign_pairing(SUBJEKT_ID, BOT_TOKEN)
    resp = client.get("/auth/pair?token=%s" % token)

    assert resp.status_code == 302
    # RAT-31 E6c: neutraler Redirect auf die Übersicht für ALLE Geräte.
    assert resp.headers["Location"].endswith("/api/v1/seiten/uebersicht")

    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Lax" in set_cookie

    # Cookie-Subjekt ist das Token-Subjekt.
    wert = set_cookie.split(sc.COOKIE_NAME + "=", 1)[1].split(";", 1)[0]
    assert sc.verify_session(wert, BOT_TOKEN) == SUBJEKT_ID


def test_ungueltiger_token_gibt_400_mit_anweisung(client):
    resp = client.get("/auth/pair?token=total.kaputt.deadbeef")
    assert resp.status_code == 400
    body = resp.get_data(as_text=True)
    assert "ungültig oder abgelaufen" in body
    assert resp.headers["Content-Type"].startswith("text/html")
    # Kein Cookie bei Misserfolg.
    assert sc.COOKIE_NAME not in resp.headers.get("Set-Cookie", "")


def test_abgelaufener_token_gibt_400(client):
    token = sc.sign_pairing(SUBJEKT_ID, BOT_TOKEN, now=0)  # längst abgelaufen
    resp = client.get("/auth/pair?token=%s" % token)
    assert resp.status_code == 400


def test_fehlender_token_gibt_400(client):
    resp = client.get("/auth/pair")
    assert resp.status_code == 400
