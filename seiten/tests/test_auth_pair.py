"""AUTH-2.a — Pairing-Endpoint /auth/pair (T948, AC4).

Testet den seiten-Endpoint GET /auth/pair?token=<X> (auth.md AUTH-2.a,
geraet-anlegen.md GAA-3.8, geraete.md GER-3 paired_at):
  - gültiger Pairing-Token → 302 auf /display/<display_id>
    + Set-Cookie xbuddy_session (HttpOnly/Secure/SameSite=Lax)
    + paired_at additiv in geraete.json (bestehende Felder erhalten).
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


def _schreibe_geraete(path):
    """geraete.json mit einem Eintrag (GER-3-Felder) — ohne paired_at."""
    data = {
        "geraete": [
            {
                "id": DISPLAY_ID,
                "typ": "tablet",
                "name": "Tablet Elias",
                "aufloesung": {"w": 1280, "h": 800},
                "os": "android",
                "verwendung": "display",
                "status": "aktiv",
            }
        ]
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


@pytest.fixture
def client(tmp_path):
    geraete_path = str(tmp_path / "geraete.json")
    _schreibe_geraete(geraete_path)
    seiten_main.configure(
        bot_token=BOT_TOKEN,
        geraete_registry_path=geraete_path,
    )
    c = seiten_main.app.test_client()
    c._geraete_path = geraete_path  # Test-Handle
    return c


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
    token = sc.sign_pairing("tablet-unbekannt-99", BOT_TOKEN)
    resp = client.get("/auth/pair?token=%s" % token)
    assert resp.status_code == 302
    assert sc.COOKIE_NAME in resp.headers.get("Set-Cookie", "")
