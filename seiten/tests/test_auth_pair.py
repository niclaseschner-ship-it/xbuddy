"""AUTH-2.a — Pairing-Endpoint /auth/pair (T948, T1372, AC4).

Testet den seiten-Endpoint GET /auth/pair?token=<X> (auth.md AUTH-2.a,
geraet-anlegen.md GAA-3.8, geraete.md GER-3 paired_at):
  - Display-Gerät (verwendung="display") → 302 auf /display/<display_id>/
    + Set-Cookie xbuddy_session (HttpOnly/Secure/SameSite=Lax)
    + paired_at additiv in geraete.json (bestehende Felder erhalten).
  - Nicht-Display-Gerät (verwendung="controller") → 302 auf
    /api/v1/seiten/uebersicht (SREG-12) + Cookie gesetzt.
  - Gerät nicht in Registry → 302 auf /api/v1/seiten/uebersicht + Cookie
    (best-effort: Cookie ist funktionaler Teil, paired_at+verwendung sekundär).
  - ungültiger/abgelaufener Token → 400 mit Anweisungsseite.
  - Cookie-Subjekt ist die display_id (verifizierbar über die Lib).

Lauf: python3 -m pytest seiten/tests/test_auth_pair.py -q
"""

from __future__ import annotations

import json
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
DISPLAY_ID = "tablet-elias-01"
CONTROLLER_ID = "handy-paula-01"


def _schreibe_geraete(path, verwendung="display", extra_geraete=None):
    """geraete.json mit einem Eintrag (GER-3-Felder) — ohne paired_at.

    `verwendung`: GER-3-Verwendung für DISPLAY_ID ("display", "controller",
    "beides"). `extra_geraete`: zusätzliche Einträge in die Liste.
    """
    geraete = [
        {
            "id": DISPLAY_ID,
            "typ": "tablet",
            "name": "Tablet Elias",
            "aufloesung": {"w": 1280, "h": 800},
            "os": "android",
            "verwendung": verwendung,
            "status": "aktiv",
        }
    ]
    if extra_geraete:
        geraete.extend(extra_geraete)
    data = {"geraete": geraete}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


@pytest.fixture
def client(tmp_path):
    """Standard-Fixture: DISPLAY_ID mit verwendung='display'."""
    geraete_path = str(tmp_path / "geraete.json")
    _schreibe_geraete(geraete_path, verwendung="display")
    seiten_main.configure(
        bot_token=BOT_TOKEN,
        geraete_registry_path=geraete_path,
    )
    c = seiten_main.app.test_client()
    c._geraete_path = geraete_path  # Test-Handle
    return c


@pytest.fixture
def client_controller(tmp_path):
    """Fixture mit CONTROLLER_ID (verwendung='controller')."""
    geraete_path = str(tmp_path / "geraete.json")
    data = {
        "geraete": [
            {
                "id": CONTROLLER_ID,
                "typ": "handy",
                "name": "Handy Paula",
                "aufloesung": {"w": 390, "h": 844},
                "os": "ios",
                "verwendung": "controller",
                "status": "aktiv",
            }
        ]
    }
    with open(geraete_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    seiten_main.configure(
        bot_token=BOT_TOKEN,
        geraete_registry_path=geraete_path,
    )
    return seiten_main.app.test_client()


def test_gueltiger_token_setzt_cookie_und_redirected(client):
    token = sc.sign_pairing(DISPLAY_ID, BOT_TOKEN)
    resp = client.get("/auth/pair?token=%s" % token)

    assert resp.status_code == 302
    # T1389 / ESC-3: Ziel trägt Trailing-Slash (/display/<id>/), um den
    # 301-Doppelhop am Router zu vermeiden (auth.md AUTH-7b, router:972).
    assert resp.headers["Location"].endswith("/display/%s/" % DISPLAY_ID)

    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Lax" in set_cookie

    # Cookie-Subjekt ist die display_id (Geräte-Identität).
    wert = set_cookie.split(sc.COOKIE_NAME + "=", 1)[1].split(";", 1)[0]
    assert sc.verify_session(wert, BOT_TOKEN) == DISPLAY_ID


def test_gueltiger_token_schreibt_paired_at_additiv(client):
    token = sc.sign_pairing(DISPLAY_ID, BOT_TOKEN)
    client.get("/auth/pair?token=%s" % token)

    with open(client._geraete_path, encoding="utf-8") as f:
        data = json.load(f)
    eintrag = data["geraete"][0]
    # paired_at gesetzt ...
    assert eintrag.get("paired_at"), "paired_at wurde nicht gestempelt"
    assert "T" in eintrag["paired_at"]  # ISO-8601
    # ... und alle bestehenden GER-3-Felder erhalten (kein Blind-Overwrite).
    assert eintrag["id"] == DISPLAY_ID
    assert eintrag["name"] == "Tablet Elias"
    assert eintrag["aufloesung"] == {"w": 1280, "h": 800}
    assert eintrag["status"] == "aktiv"


def test_ungueltiger_token_gibt_400_mit_anweisung(client):
    resp = client.get("/auth/pair?token=total.kaputt.deadbeef")
    assert resp.status_code == 400
    body = resp.get_data(as_text=True)
    assert "ungültig oder abgelaufen" in body
    assert resp.headers["Content-Type"].startswith("text/html")
    # Kein Cookie bei Misserfolg.
    assert sc.COOKIE_NAME not in resp.headers.get("Set-Cookie", "")


def test_abgelaufener_token_gibt_400(client):
    token = sc.sign_pairing(DISPLAY_ID, BOT_TOKEN, now=0)  # längst abgelaufen
    resp = client.get("/auth/pair?token=%s" % token)
    assert resp.status_code == 400


def test_fehlender_token_gibt_400(client):
    resp = client.get("/auth/pair")
    assert resp.status_code == 400


def test_unbekannte_display_id_setzt_trotzdem_cookie(client):
    # Token für ein Gerät, das nicht in geraete.json steht: Cookie + redirect
    # trotzdem (paired_at best-effort, Cookie ist funktionaler Teil).
    # Redirect-Ziel: /api/v1/seiten/uebersicht (SREG-12) — sicher neutraler Fallback,
    # kein Erfinden einer Display-Verwendung (AUTH-2.a no_usage_source-Stopregel).
    token = sc.sign_pairing("tablet-unbekannt-99", BOT_TOKEN)
    resp = client.get("/auth/pair?token=%s" % token)
    assert resp.status_code == 302
    assert sc.COOKIE_NAME in resp.headers.get("Set-Cookie", "")
    assert resp.headers["Location"].endswith("/api/v1/seiten/uebersicht")


# ------------------------------------------------------------------
# T1372: verwendungs-abhängiger Redirect (AC1 + AC2)
# ------------------------------------------------------------------

def test_controller_redirected_auf_uebersicht(client_controller):
    """AC1/AC2: Nicht-Display-Gerät (controller) → /api/v1/seiten/uebersicht."""
    token = sc.sign_pairing(CONTROLLER_ID, BOT_TOKEN)
    resp = client_controller.get("/auth/pair?token=%s" % token)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/api/v1/seiten/uebersicht"), (
        "Controller-Gerät muss auf Übersichtsseite (SREG-12) landen, "
        "got: %s" % resp.headers.get("Location")
    )
    # Cookie muss trotzdem gesetzt sein (AUTH-2.a: Cookie in BEIDEN Fällen).
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie, "Cookie muss auch bei Controller-Redirect gesetzt sein"
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=Lax" in set_cookie
    # Cookie-Subjekt ist die display_id des Controllers.
    wert = set_cookie.split(sc.COOKIE_NAME + "=", 1)[1].split(";", 1)[0]
    assert sc.verify_session(wert, BOT_TOKEN) == CONTROLLER_ID


def test_display_gerät_redirected_auf_display_pfad(client):
    """AC1/AC2: Display-Gerät (verwendung='display') → /display/<id>/."""
    token = sc.sign_pairing(DISPLAY_ID, BOT_TOKEN)
    resp = client.get("/auth/pair?token=%s" % token)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/display/%s/" % DISPLAY_ID), (
        "Display-Gerät muss auf /display/<id>/ landen, "
        "got: %s" % resp.headers.get("Location")
    )
    # Cookie gesetzt (AC1: Cookie in BEIDEN Fällen).
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie
