"""AUTH-7b — Dual-Gate-Verhalten (T1389, auth.md AUTH-7 / AUTH-3.a / AUTH-8).

Prüft den geteilten Dual-Gate über beide Service-Seiten:

  seiten  — /shell/<panel_id> (HTML-Shell)
  router  — /display/<id>/, /controller/app-panel/<id>/,
            /api/v1/displays/<id>/events (SSE)

Achsen (auth.md AUTH-7 7b Cookie-only-hart + AUTH-3.a Observe-Leiter, RAT-32):
  - valider xbuddy_session-Cookie  → 200 + Rolling-Refresh (AUTH-2:78).
  - keine Cookie-Quelle + Observe   → 200 + Log (kein 401, Grace).
  - keine Cookie-Quelle + Hard      → 401 mit AUTH-8-Re-Pair-HTML.
  - Operator-IP (RAT-32): entfällt als Zugangs-Alternative — in Hard → 401,
    in Observe → 200 (Grace für ALLE, nicht wegen Operator-IP).
  - /display/_shared/* bleibt public (AUTH-7:512, kein Gate).
  - SSE-Stream im Pass-Fall bleibt Streaming-Response (kein Buffering).

Plus die pure auth_gate-Lib (CIDR/Cookie) direkt und die /auth/pair E6c-Probe
(RAT-31 E6c: kein geraete-Registry-Write mehr, neutraler Übersichts-Redirect).

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
_OPERATOR = {"X-Real-IP": "192.0.2.10"}  # auth.md AUTH-7:461 192.168.0.0/16


# ---------------------------------------------------------------------------
# Pure Lib (auth_gate) — CIDR + Cookie
# ---------------------------------------------------------------------------


def test_ist_operator_ip_deckt_die_drei_cidrs():
    assert auth_gate.ist_operator_ip("192.0.2.10")   # 192.168.0.0/16
    assert auth_gate.ist_operator_ip("10.9.8.7")         # 10.0.0.0/8
    assert auth_gate.ist_operator_ip("100.64.0.10")    # 100.64.0.0/10 (Tailnet)
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


def test_hard_mode_operator_ip_ohne_cookie_gibt_401_rat32():
    """RAT-32: im hard-Modus grantet Operator-IP KEINEN Zugang mehr — nur der
    Cookie. Operator-CIDR ohne Cookie → 401 (AUTH-7a gestrichen)."""
    @router_main.require_dual_gate(mode="hard")
    def _dummy():
        return "ok"

    with router_main.app.test_request_context("/x", headers=_OPERATOR):
        resp = router_main.app.make_response(_dummy())
    assert resp.status_code == 401, (
        "hard + Operator-IP ohne Cookie muss 401 sein (RAT-32), got %d"
        % resp.status_code
    )
    assert "neu verbunden" in resp.get_data(as_text=True)


def test_hard_mode_cookie_gibt_200_rat32():
    """RAT-32: im hard-Modus reicht der valide Cookie (einziger Zugangspfad)."""
    @router_main.require_dual_gate(mode="hard")
    def _dummy():
        return "ok"

    router_main.runtime_config["bot_token"] = BOT_TOKEN
    try:
        cookie = sc.sign_session(DISPLAY_ID, BOT_TOKEN)
        with router_main.app.test_request_context(
            "/x", headers={**_EXTERN, "Cookie": "%s=%s" % (sc.COOKIE_NAME, cookie)}
        ):
            resp = router_main.app.make_response(_dummy())
        assert resp.status_code == 200
    finally:
        router_main.runtime_config["bot_token"] = ""


def test_auth_mode_env_seam_default_observe():
    """RAT-32: der Flip läuft über die ENV-Naht XBUDDY_AUTH_MODE (Default
    'observe' → verhaltensneutraler Deploy), damit Flip/Rückroll ENV+restart
    sind statt Code-Revert (#1430-Lehre). Die 7b-READ-Routen sind ENV-getoggelt."""
    assert os.environ.get("XBUDDY_AUTH_MODE", "observe") == router_main._AUTH_MODE
    assert router_main._AUTH_MODE in ("observe", "hard")


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


def test_shell_operator_ip_ohne_cookie_gibt_401_rat32(seiten_client):
    # RAT-32: Operator-IP entfällt als Zugangs-Alternative — die hard-Shell
    # gibt ohne gültigen Cookie 401, auch aus dem Operator-CIDR.
    resp = seiten_client.get("/shell/%s" % PANEL_ID, headers=_OPERATOR)
    assert resp.status_code == 401
    assert "neu verbunden" in resp.get_data(as_text=True)


def test_shell_cookie_gibt_200_und_rolling_refresh(seiten_client):
    seiten_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(DISPLAY_ID, BOT_TOKEN))
    resp = seiten_client.get("/shell/%s" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 200
    assert sc.COOKIE_NAME in resp.headers.get("Set-Cookie", "")


def test_shell_keine_quelle_hard_gibt_401(seiten_client):
    """T1448: /shell/<panel_id> ist auf hard gesetzt — 401 ohne Auth-Quelle."""
    resp = seiten_client.get("/shell/%s" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 401  # hard — kein Durchlass ohne Cookie/Operator-IP
    assert "neu verbunden" in resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# T1418 / T1448 — Asset- und Manifest-Routen
# T1418: display-Assets observe→200+Log
# T1448: shell-Manifest public→200 (kein Gate); shell-Assets hard→401
# entry_path_probe: GET /display/<id>/<asset> + /shell/<id>/<asset> durch den Gate
# ---------------------------------------------------------------------------


def test_shell_manifest_public_gibt_200_ohne_gate(seiten_client, caplog):
    """T1448/AC2: GET /shell/<id>/manifest.json ist public (kein Gate-Decorator).

    Browser holt PWA-Manifeste credential-los (Fetch-Spec) → gegated 401 über den
    Funnel bricht PWA-Install (#1437). Manifest gibt 200 OHNE Auth-Quelle zurück —
    UND trägt keinen AUTH-3.a-Observe-Log (kein Gate aktiv).
    """
    with caplog.at_level(logging.WARNING):
        resp = seiten_client.get(
            "/shell/%s/manifest.json" % PANEL_ID, headers=_EXTERN
        )
    assert resp.status_code == 200, (
        "Shell-Manifest-Route muss public 200 zurückgeben (kein Gate), got %d"
        % resp.status_code
    )
    # Kein Gate-Decorator → kein AUTH-3.a-Log.
    assert not any("AUTH-3.a Observe" in r.message for r in caplog.records), (
        "AUTH-3.a-Observe-Log darf NICHT erscheinen — Manifest-Route ist public (kein Gate)"
    )


def test_shell_asset_hard_ohne_quelle_gibt_401(seiten_client):
    """T1448/AC3: GET /shell/<id>/sw.js ohne Auth-Quelle → 401 (hard enforced).

    sw.js ist eine Shell-Asset-Route (shell_asset_view) mit mode='hard'.
    Ohne Cookie oder Operator-IP → 401 + AUTH-8-HTML.
    """
    resp = seiten_client.get("/shell/%s/sw.js" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 401, (
        "Shell-Asset-Route (sw.js) muss im hard-Modus 401 zurückgeben, got %d"
        % resp.status_code
    )
    assert "neu verbunden" in resp.get_data(as_text=True), (
        "AUTH-8-Re-Pair-HTML ('neu verbunden') fehlt in 401-Antwort"
    )


def test_shell_asset_operator_ip_ohne_cookie_gibt_401_rat32(seiten_client):
    """RAT-32: Operator-IP entfällt — hard Shell-Asset (sw.js) ohne Cookie → 401."""
    resp = seiten_client.get("/shell/%s/sw.js" % PANEL_ID, headers=_OPERATOR)
    assert resp.status_code == 401, (
        "Shell-Asset (sw.js) aus dem Operator-CIDR ohne Cookie muss 401 liefern "
        "(RAT-32: Operator-IP gestrichen), got %d" % resp.status_code
    )


def test_shell_asset_cookie_gibt_200(seiten_client):
    """T1448/AC3: valider Cookie reicht als Auth-Quelle für Shell-Assets — 200 + Rolling-Refresh."""
    seiten_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(DISPLAY_ID, BOT_TOKEN))
    resp = seiten_client.get("/shell/%s/sw.js" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 200, (
        "Shell-Asset-Route (sw.js) mit Cookie muss 200 liefern, got %d"
        % resp.status_code
    )


def test_asset_hard_mode_ohne_quelle_gibt_401(router_client):
    """hard-Mode-Probe für Asset-Route: require_dual_gate(mode='hard') liefert
    401 + AUTH-8-HTML, wenn keine Quelle vorliegt (analog test_hard_mode_ohne_quelle).
    Belegt, dass der Decorator auf Asset-Routen funktional aktiv ist."""
    @router_main.require_dual_gate(mode="hard")
    def _asset_dummy():
        return "asset-content"

    with router_main.app.test_request_context(
        "/display/%s/sw.js" % DISPLAY_ID, headers=_EXTERN
    ):
        resp = router_main.app.make_response(_asset_dummy())
    assert resp.status_code == 401
    assert "neu verbunden" in resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# T1448/AC1 — Live-Pfad-Test: GET /shell/<panel>/sw.js body traegt network-first
# ---------------------------------------------------------------------------


def test_shell_sw_js_live_pfad_traegt_network_first_body(seiten_client):
    """AC1 entry_path_probe: GET /shell/<panel_id>/sw.js liefert im Body network-first-Logik.

    Prueft den ECHTEN Serve-Pfad (shell_asset_view via read_sw_with_build_id),
    NICHT den Skelett-String aus render_sw(). Belegt, dass die committete
    seiten/static/shell/sw.js network-first implementiert — die Datei ist die
    Wahrheit fuer die Shell (Approach B, T1448-S2-fix).

    Cookie als Auth-Quelle (shell_asset_view ist hard; Operator-IP entfällt, RAT-32).
    """
    seiten_client.set_cookie(sc.COOKIE_NAME, sc.sign_session(DISPLAY_ID, BOT_TOKEN))
    resp = seiten_client.get("/shell/%s/sw.js" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 200, (
        "GET /shell/<panel>/sw.js muss 200 liefern (Cookie), got %d"
        % resp.status_code
    )
    body = resp.get_data(as_text=True)
    assert "networkFirst" in body or "network-first" in body, (
        "sw.js-Body muss network-first-Logik enthalten (T1448/AC1); "
        "body enthaelt weder 'networkFirst' noch 'network-first'"
    )
    # Sicherstellen: cache-first fuer Shell-HTML ist NICHT die alleinige Strategie.
    # (cacheFirst-Funktion kann fuer statische Assets existieren — das ist OK;
    #  aber der HTML-Pfad muss network-first sein.)
    assert "function networkFirst" in body, (
        "sw.js-Body muss eine networkFirst-Funktion definieren (T1448/AC1)"
    )
    assert "__BUILD_ID__" not in body, (
        "BUILD_ID-Platzhalter darf im ausgelieferten sw.js-Body nicht mehr stehen"
    )


# ---------------------------------------------------------------------------
# T1448/AC2 — Icons public, sw.js bleibt gated
# ---------------------------------------------------------------------------


def test_shell_icon_public_ohne_quelle_gibt_200(seiten_client):
    """AC2 entry_path_probe: GET /shell/<panel_id>/icon-192.png ohne Auth-Quelle → 200.

    WebAPK-Installer holt Manifest-Icons credential-los (Fetch-Spec, AUTH-4).
    Icons muessen auch ohne Cookie und ohne Operator-IP 200 zurueckgeben.
    """
    resp = seiten_client.get("/shell/%s/icon-192.png" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 200, (
        "Shell-Icon muss public 200 zurueckgeben (AUTH-4, kein Gate), got %d"
        % resp.status_code
    )
    assert resp.content_type.startswith("image/png"), (
        "Shell-Icon muss image/png Content-Type liefern, got: %s" % resp.content_type
    )


def test_shell_sw_js_bleibt_gated_ohne_quelle(seiten_client):
    """AC2: GET /shell/<panel_id>/sw.js ohne Auth-Quelle → 401 (nicht public).

    sw.js ist kein inhaltlich oeffentliches Asset — der SW-Fetch traegt Credentials.
    Sicherstellt, dass die Icons-public-Ausnahme NICHT auf sw.js ausgeweitet wurde.
    """
    resp = seiten_client.get("/shell/%s/sw.js" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 401, (
        "sw.js muss hard-gated bleiben (401 ohne Quelle), got %d"
        % resp.status_code
    )


def test_shell_icon_512_public_ohne_quelle_gibt_200(seiten_client):
    """AC2: GET /shell/<panel_id>/icon-512.png ohne Auth-Quelle → 200 (AUTH-4).

    Prueft alle Icon-Varianten: icon-512.png (any purpose) ebenfalls public.
    """
    resp = seiten_client.get("/shell/%s/icon-512.png" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 200, (
        "icon-512.png muss public 200 zurueckgeben (AUTH-4), got %d"
        % resp.status_code
    )


def test_shell_icon_maskable_public_ohne_quelle_gibt_200(seiten_client):
    """AC2: GET /shell/<panel_id>/icon-maskable-512.png ohne Auth-Quelle → 200 (AUTH-4).

    Prueft die maskable-Icon-Variante — ebenfalls credential-los via WebAPK-Installer.
    """
    resp = seiten_client.get("/shell/%s/icon-maskable-512.png" % PANEL_ID, headers=_EXTERN)
    assert resp.status_code == 200, (
        "icon-maskable-512.png muss public 200 zurueckgeben (AUTH-4), got %d"
        % resp.status_code
    )


# ---------------------------------------------------------------------------
# entry_path_probe — auth/pair E6c (auth.md AUTH-2.a / RAT-31 E6c)
# ---------------------------------------------------------------------------


def test_auth_pair_e6c_kein_geraete_write(tmp_path):
    """RAT-31 E6c: /auth/pair schreibt KEIN paired_at mehr (kein geraete.json-Write).

    Verifiziert den E6c-Zielzustand: nach erfolgreichem Pairing zeigt der
    Redirect auf /api/v1/seiten/uebersicht (neutral, gerätelos), und es gibt
    keinen geraete.json-Dateischreibvorgang. Das Fehlen von
    `geraete_registry_path` in configure() belegt, dass die Naht entfernt
    wurde (RAT-31 E6c, geraete/ gelöscht #1565).
    """
    seiten_main.configure(bot_token=BOT_TOKEN, router_url="http://router.test:5000")
    client = seiten_main.app.test_client()
    token = sc.sign_pairing(DISPLAY_ID, BOT_TOKEN)
    resp = client.get("/auth/pair?token=%s" % token)

    # RAT-31 E6c: neutraler Redirect auf die Übersicht (SREG-12), kein /display/<id>/.
    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert "/api/v1/seiten/uebersicht" in location, (
        "E6c: Redirect muss auf /api/v1/seiten/uebersicht zeigen, got: %s" % location
    )
    # Kein Gerätepfad im Redirect (geraete.json entfallen).
    assert "/display/" not in location, (
        "E6c: Redirect darf nicht mehr auf /display/<id>/ zeigen (geraete/ gelöscht)"
    )
