"""AUTH-11 — Rück-Verriegelung für den panel-Service (#1834, auth.md AUTH-11).

Deckt den Teil des Tickets, der ohne Konflikt mit bestehenden, außerhalb des
Schreib-Scopes liegenden Tests umsetzbar war:

  test_default_mode_ist_hard_nicht_observe   — AC3: Factory-Default ist "hart"
  test_static_endpoint_ohne_cookie_ist_401   — AC1/AC4: impliziter Flask-static-
                                                Endpunkt trägt jetzt den Gate
  test_static_endpoint_mit_cookie_passiert_gate — AC4: gültiger Cookie lässt
                                                die (leere) static-Route durch

**Nicht abgedeckt (siehe Handoff-STOP):** `POST /api/v1/panels/` (AC2) sowie
die vier übrigen Lese-Routen (`GET /api/v1/panels/`, `.../<id>`,
`.../config.json`, `.../tiles.json`) und die drei Editor-Routen
(`/controller/app-panel/<id>/bearbeiten[.js|.css]`) sind NICHT gegatet.
Ein Experiment (siehe Handoff) belegt: das Gaten dieser acht Routen bricht
25 Tests in `panel/tests/test_panel.py` und
`panel/tests/test_panel_editor_seite.py` — beide außerhalb
`write_allowed_files` dieses Contracts. Zusätzlich widerspricht das Gaten der
vier Lese-Routen wörtlich `specs/platform/panel-bearbeiten.md` PBE-3
("Der Lesepfad bleibt außerhalb AUTH-3 … ein app-seitiges Gaten würde den
Display-Fetch erschlagen, belegter #1338-Bruch").

Lauf: python3 -m pytest panel/tests/test_auth11_panel.py -v
"""

import os
import sys

import pytest

_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_BOT_TOKEN = "123456:ABCdef_auth11testtoken"


@pytest.fixture
def gate_client():
    """Kein registry_path nötig — die geprüften Routen brauchen keinen."""
    panel_main.configure(panel_main.runtime["registry"], bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    return panel_main.app.test_client()


# ---------------------------------------------------------------------------
# AC3 — Factory-Default ist "hard", nicht "observe" (Nic-Setzung 2026-08-11)
# ---------------------------------------------------------------------------


def test_default_mode_ist_hard_nicht_observe(gate_client):
    """panel/main.py:123: `default_mode="hard"`. Beleg verhaltensseitig über
    eine bare `@require_dual_gate()`-Route (hier: der static-Endpunkt) — ohne
    Cookie-Quelle muss der Default-Pfad 401 liefern, nicht 200 (Observe-Grace)."""
    resp = gate_client.get("/static/irgendwas.txt")
    assert resp.status_code == 401, (
        "default_mode muss 'hard' sein — 401 ohne Cookie erwartet, got %d "
        "(default_mode vermutlich noch 'observe')" % resp.status_code
    )


# ---------------------------------------------------------------------------
# AC1/AC4 — impliziter Flask-`static`-Endpunkt trägt jetzt den Gate
# ---------------------------------------------------------------------------


def test_static_endpoint_ohne_cookie_ist_401(gate_client):
    """AC1: `/static/<path:filename>` (Flask-impliziter Endpunkt, panel/main.py:147)
    ist über die URL-Map sichtbar (AUTH-11-Messbasis) und jetzt gegated."""
    resp = gate_client.get("/static/anything.txt")
    assert resp.status_code == 401
    assert "neu verbunden" not in resp.get_data(as_text=True)  # panel-401-Text prüfen:
    assert "Zugang" in resp.get_data(as_text=True)


def test_static_endpoint_mit_cookie_passiert_gate(gate_client):
    """AC4: gültiger Session-Cookie lässt die static-Route durchs Gate — panel/
    hat kein `static/`-Verzeichnis, die (durchgelassene) Flask-Static-View
    liefert dann 404 (Datei fehlt), NICHT 401 (Auth-Fehler). Das belegt: der
    Cookie hat das Gate passiert, die 404 kommt aus der Werkzeug-static-View
    dahinter (die 404 kommt aus einer geworfenen `NotFound`-Exception der
    static-View — dort läuft der Rolling-Refresh nicht mehr mit, siehe
    `test_static_endpoint_mit_cookie_und_datei_setzt_rolling_refresh` für den
    Erfolgsfall inkl. Set-Cookie)."""
    gate_client.set_cookie(sc.COOKIE_NAME, sc.sign_session("op", _BOT_TOKEN))
    resp = gate_client.get("/static/anything.txt")
    assert resp.status_code == 404, (
        "mit gültigem Cookie muss die static-View selbst antworten (404, Datei "
        "fehlt) statt am Gate zu scheitern (401), got %d" % resp.status_code
    )


def test_static_endpoint_mit_cookie_und_datei_setzt_rolling_refresh(gate_client, tmp_path):
    """AC4/Rolling-Refresh (AUTH-2:78): existiert tatsächlich eine Datei im
    static-Ordner, liefert die durchgelassene static-View 200 UND das Gate
    setzt bei jedem Pass einen frischen Cookie (Rolling-Refresh)."""
    (tmp_path / "hallo.txt").write_text("hallo", encoding="utf-8")
    original_static_folder = panel_main.app.static_folder
    panel_main.app.static_folder = str(tmp_path)
    try:
        gate_client.set_cookie(sc.COOKIE_NAME, sc.sign_session("op", _BOT_TOKEN))
        resp = gate_client.get("/static/hallo.txt")
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert sc.COOKIE_NAME in resp.headers.get("Set-Cookie", "")
    finally:
        panel_main.app.static_folder = original_static_folder
