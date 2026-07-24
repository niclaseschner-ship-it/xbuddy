"""AUTH-7b — Dual-Gate-Verhalten (T1389, auth.md AUTH-7 / AUTH-3.a / AUTH-8).

Prüft den geteilten Dual-Gate über beide Service-Seiten:

  seiten  — /shell/<panel_id> (HTML-Shell)
  router  — /display/<id>/, /controller/app-panel/<id>/,
            /api/v1/displays/<id>/events (SSE)

Achsen (auth.md AUTH-7:495-504 Dual-Gate + AUTH-3.a:247-253 Observe-Leiter):
  - valider xbuddy_session-Cookie  → 200 + Rolling-Refresh (AUTH-2:78).
  - Operator-IP (X-Real-IP in CIDR) → 200, ohne Cookie.
  - keine Quelle + Observe          → 200 + Log (kein 401, Grace).
  - keine Quelle + Hard             → 401 mit AUTH-8-Re-Pair-HTML.
  - /display/_shared/* bleibt public (AUTH-7:512, kein Gate).
  - SSE-Stream im Pass-Fall bleibt Streaming-Response (kein Buffering).

Plus die pure auth_gate-Lib (CIDR/Cookie) direkt und der paired_at-Write-Proof
(entry_path_probe write_verification).

Lauf: python3 -m pytest tests/test_dual_gate_7b.py -q
"""

from __future__ import annotations

import json
import logging
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from router import main as router_main  # noqa: E402
from seiten import main as seiten_main  # noqa: E402
from tools.initdata import auth_gate  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

BOT_TOKEN = "123456:ABCdef_testtoken"
DISPLAY_ID = "display-wohnzimmer-01"
PANEL_ID = "kueche"

# X-Forwarded-For einer Nicht-Operator-Adresse (öffentliches Internet), damit
# der Test nicht versehentlich über den Operator-IP-Pfad grün wird. X-Real-IP
# ist die Trust-Quelle (ESC-2); wir setzen sie gezielt pro Test.
_EXTERN = {"X-Real-IP": "203.0.113.7"}
_OPERATOR = {"X-Real-IP": "192.168.178.42"}  # auth.md AUTH-7:461 192.168.0.0/16


# ---------------------------------------------------------------------------
# Pure Lib (auth_gate) — CIDR + Cookie
# ---------------------------------------------------------------------------


def test_ist_operator_ip_deckt_die_drei_cidrs():
    assert auth_gate.ist_operator_ip("192.168.178.42")   # 192.168.0.0/16
    assert auth_gate.ist_operator_ip("10.9.8.7")         # 10.0.0.0/8
    assert auth_gate.ist_operator_ip("100.108.61.31")    # 100.64.0.0/10 (Tailnet)
    assert not auth_gate.ist_operator_ip("203.0.113.7")  # öffentlich
    assert not auth_gate.ist_operator_ip("")             # leer
    assert not auth_gate.ist_operator_ip(None)           # fehlt
    assert not auth_gate.ist_operator_ip("kaputt")       # unparsbar


def test_hat_gueltigen_cookie_wrappt_verify_session():
    tok = sc.sign_session(DISPLAY_ID, BOT_TOKEN)
    assert auth_gate.hat_gueltigen_cookie(tok, BOT_TOKEN)
    assert not auth_gate.hat_gueltigen_cookie("kaputt.1.deadbeef", BOT_TOKEN)
    assert not auth_gate.hat_gueltigen_cookie(None, BOT_TOKEN)
    # Abgelaufen → nicht gültig.
    alt = sc.sign_session(DISPLAY_ID, BOT_TOKEN, ttl_seconds=10, now=1000)
    assert not auth_gate.hat_gueltigen_cookie(alt, BOT_TOKEN)


# ---------------------------------------------------------------------------
# Router-Seite: /display/<id>/ + Controller + SSE
# ---------------------------------------------------------------------------

_DEMO_ROUTING = {
    "displays": {DISPLAY_ID: {"app": "kalender"}},
    "panels": {"app-panel:" + PANEL_ID: {"display_id": DISPLAY_ID}},
}


@pytest.fixture
def router_client(tmp_path):
    routing_path = tmp_path / "routing.json"
    routing_path.write_text(json.dumps(_DEMO_ROUTING))
    router_main.state = {}
    router_main._subscribers.clear()
    router_main.load_routing(str(routing_path))
    router_main.runtime_config["bot_token"] = BOT_TOKEN
    router_main.app.testing = True
    yield router_main.app.test_client()
    router_main.runtime_config["bot_token"] = ""


def test_display_operator_ip_gibt_200(router_client):
    resp = router_client.get("/display/%s/" % DISPLAY_ID, headers=_OPERATOR)
    assert resp.status_code == 200


def test_display_cookie_gibt_200_und_rolling_refresh(router_client):
    router_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(DISPLAY_ID, BOT_TOKEN))
    resp = router_client.get("/display/%s/" % DISPLAY_ID, headers=_EXTERN)
    assert resp.status_code == 200
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie  # AUTH-2:78 Rolling-Refresh
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie


def test_display_head_cookie_rolling_refresh_oq1(router_client):
    """OQ-1 / #1390 — HEAD auf /display/<id>/ mit gültigem Cookie.

    Flask leitet HEAD automatisch an die GET-Route weiter (RFC 7231 §4.3.2).
    require_dual_gate muss im Cookie-Pfad unabhängig von der HTTP-Methode
    einen frischen Set-Cookie-Header (Rolling-Refresh, AUTH-2:78) liefern.
    HEAD-Antworten dürfen keinen Body haben — der Status muss 200 sein.
    """
    router_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(DISPLAY_ID, BOT_TOKEN))
    resp = router_client.head("/display/%s/" % DISPLAY_ID, headers=_EXTERN)
    assert resp.status_code == 200
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie, "Rolling-Refresh fehlt im HEAD-Response (AUTH-2:78)"
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie


def test_display_keine_quelle_observe_gibt_200_und_loggt(router_client, caplog):
    with caplog.at_level(logging.WARNING):
        resp = router_client.get("/display/%s/" % DISPLAY_ID, headers=_EXTERN)
    assert resp.status_code == 200  # AUTH-3.a Observe: kein 401
    assert any("AUTH-3.a Observe" in r.message for r in caplog.records)


def test_controller_app_panel_operator_gibt_200(router_client):
    resp = router_client.get("/controller/app-panel/%s/" % PANEL_ID, headers=_OPERATOR)
    assert resp.status_code == 200


def test_display_shared_bleibt_public_ohne_quelle(router_client):
    # AUTH-7:512 — /display/_shared/* trägt keinen Gate. 404 (Asset fehlt im
    # Test) beweist: die Route lief, wurde NICHT auf 401 gegated.
    resp = router_client.get("/display/_shared/icons/arasaac/1.png", headers=_EXTERN)
    assert resp.status_code != 401


def test_sse_pass_bleibt_streaming_response(router_client):
    # Operator-Pfad läuft unverpackt → die Streaming-Response bleibt erhalten
    # (der Decorator puffert den Generator nicht). Wir prüfen den Stream-Flag
    # und den ersten Event-Chunk, ohne den unendlichen Stream auszulesen.
    resp = router_client.get("/api/v1/displays/%s/events" % DISPLAY_ID,
                             headers=_OPERATOR, buffered=False)
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert resp.is_streamed  # nicht in einen len()-baren Body gepuffert
    erster = next(resp.response)
    assert b"data:" in (erster if isinstance(erster, bytes) else erster.encode())
    resp.close()


def test_hard_mode_ohne_quelle_gibt_401_mit_auth8(router_client):
    # require_dual_gate(mode="hard") liefert 401 + AUTH-8-HTML, wenn keine
    # Quelle vorliegt. Wir wenden den Decorator direkt auf eine Dummy-View an,
    # ohne eine Produktiv-Route hart zu schalten (ESC-1: initial alle Observe).
    @router_main.require_dual_gate(mode="hard")
    def _dummy():
        return "ok"

    with router_main.app.test_request_context("/x", headers=_EXTERN):
        resp = router_main.app.make_response(_dummy())
    assert resp.status_code == 401
    assert "neu verbunden" in resp.get_data(as_text=True)
    assert resp.headers["Content-Type"].startswith("text/html")


# ---------------------------------------------------------------------------
# Seiten-Seite: /shell/<panel_id>
# ---------------------------------------------------------------------------


@pytest.fixture
def seiten_client(monkeypatch):
    seiten_main.configure(bot_token=BOT_TOKEN, router_url="http://router.test:5000")
    # SHELL-2-Lookup deterministisch stubben (kein Live-Router).
    monkeypatch.setattr(seiten_main, "_lookup_display_id", lambda pid: DISPLAY_ID)
    seiten_main.app.testing = True
    return seiten_main.app.test_client()


def test_shell_operator_ip_gibt_200(seiten_client):
    resp = seiten_client.get("/shell/%s" % PANEL_ID, headers=_OPERATOR)
    assert resp.status_code == 200


def test_shell_cookie_gibt_200_und_rolling_refresh(seiten_client):
    seiten_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(DISPLAY_ID, BOT_TOKEN))
    resp = seiten_client.get("/shell/%s" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 200
    assert sc.COOKIE_NAME in resp.headers.get("Set-Cookie", "")


def test_shell_keine_quelle_observe_gibt_200(seiten_client, caplog):
    with caplog.at_level(logging.WARNING):
        resp = seiten_client.get("/shell/%s" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 200  # Observe, kein 401
    assert any("AUTH-3.a Observe" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# entry_path_probe — paired_at-Write-Proof (auth.md AUTH-2.a / OD3)
# ---------------------------------------------------------------------------


def test_paired_at_write_proof(tmp_path):
    """write_verification: /auth/pair stempelt paired_at in den GERAETE_REGISTRY-
    Store (GER-3), before/after des tmp-Files zeigen den Stempel."""
    geraete_path = str(tmp_path / "geraete.json")
    before = {"geraete": [{"id": DISPLAY_ID, "name": "Wohnzimmer",
                           "status": "aktiv"}]}
    with open(geraete_path, "w", encoding="utf-8") as f:
        json.dump(before, f)

    # BEFORE: kein paired_at.
    with open(geraete_path, encoding="utf-8") as f:
        assert "paired_at" not in json.load(f)["geraete"][0]

    seiten_main.configure(bot_token=BOT_TOKEN, geraete_registry_path=geraete_path)
    client = seiten_main.app.test_client()
    token = sc.sign_pairing(DISPLAY_ID, BOT_TOKEN)
    resp = client.get("/auth/pair?token=%s" % token)

    # ESC-3: Redirect trägt Trailing-Slash.
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/display/%s/" % DISPLAY_ID)

    # AFTER: paired_at gestempelt, bestehende Felder erhalten (additiv).
    with open(geraete_path, encoding="utf-8") as f:
        eintrag = json.load(f)["geraete"][0]
    assert eintrag.get("paired_at"), "paired_at nicht in den Store geschrieben"
    assert "T" in eintrag["paired_at"]  # ISO-8601
    assert eintrag["name"] == "Wohnzimmer"  # additiv, kein Blind-Overwrite
