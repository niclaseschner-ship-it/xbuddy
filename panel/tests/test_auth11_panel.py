"""AUTH-11 — Rück-Verriegelung für den panel-Service (#1834, auth.md AUTH-11).

  test_default_mode_ist_hard_nicht_observe   — AC3: ENV-Auflösung `_AUTH_MODE`
                                                fällt ohne Override auf "hart"
  test_static_endpoint_ohne_cookie_ist_401   — AC1/AC4: impliziter Flask-static-
                                                Endpunkt trägt jetzt den Gate
  test_static_endpoint_mit_cookie_passiert_gate — AC4: gültiger Cookie lässt
                                                die (leere) static-Route durch
  test_static_endpoint_mit_cookie_und_datei_setzt_rolling_refresh — AC4:
                                                existiert die Datei, liefert
                                                die Route 200 + Rolling-Refresh
  test_auth_mode_env_naht_observe_ist_rueckroll_default_bleibt_hart — RAT-32
                                                Nicht-Verhandelbar: End-to-End-
                                                Beleg der ENV-Naht über einen
                                                echten Modul-Reload
  test_post_panel_bleibt_hart_unter_observe  — AUTH-3.a: WRITE ignoriert die
                                                ENV-Naht, kein Observe-Grace

Von den ursprünglich acht ungegateten Routen sind nach dem Watchdog-Befund
(2026-08-11/12, Live-Reproduktion) **drei** gegated geblieben:
`GET /api/v1/panels/`, `GET /api/v1/panels/<panel_id>` (laufen live per nginx
direkt an den Browser-Cookie, `panel:5041`) und `POST /api/v1/panels/`
(literales `mode="hard"`, AUTH-3.a — wie `PUT .../tiles`, siehe unten). Die
übrigen fünf (`.../config.json`, `.../tiles.json`, die drei Editor-Routen)
laufen live über `seiten._proxy_panel_view` / `_proxy_panel_bearbeiten`
(PREG-9-Proxy, seiten/main.py:2140/2170) — ein Aufruf ohne Cookie/Header.
Der ÜBERHOLT-Marker in `specs/platform/panel-bearbeiten.md` PBE-3 widerlegt
nur die "cookieloses Kiosk-Gerät"-Prämisse für das GERÄT (RAT-32-Pairing);
über den PREG-9-Proxy-Aufrufer (ein Prozess, kein Gerät) sagt er nichts.
Diese fünf Routen bleiben deshalb UNGEGATED, bis eine separat ticketierte
Design-Entscheidung (Nic) eine Identität am Proxy-Hop schafft — siehe
`panel/main.py` (Kommentare bei `get_panel_config` / `get_panel_editor`)
und `panel/tests/test_panel_editor_seite.py::test_pbe1_editor_route_no_auth_layer`.

RAT-32 Nicht-Verhandelbar (decisions/RAT-32-auth-cookie-only-hart.md:39-46,
Lehre #1427→#1430): der Hard-Flip ist eine ENV-Naht (`XBUDDY_AUTH_MODE`),
kein Code-Diff — `panel/main.py:_AUTH_MODE = os.environ.get("XBUDDY_AUTH_MODE",
"hard")` wird EINMAL beim Modul-Import gelesen, wie beim seiten-Vorbild
(seiten/main.py:469). `importlib.reload` simuliert den Prozess-Neustart im
Testprozess; die Fixture `_reset_panel_main_env` stellt danach garantiert
den Default-Zustand wieder her — `panel.main` ist ein Singleton in
`sys.modules`, ein liegen gebliebener Reload würde sonst AC3 in JEDER
anderen Testdatei dieser Suite stumm brechen (Form wortgleich zum
routine-Vorbild, `routine/tests/test_auth11_routine.py`).

Lauf: python3 -m pytest panel/tests/test_auth11_panel.py -v
"""

import importlib
import json
import os
import sys

import pytest

_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main  # noqa: E402
from panel import registry as registry_mod  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_BOT_TOKEN = "123456:ABCdef_auth11testtoken"


@pytest.fixture
def gate_client():
    """Kein registry_path nötig — die geprüften Routen brauchen keinen."""
    panel_main.configure(panel_main.runtime["registry"], bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    return panel_main.app.test_client()


# ---------------------------------------------------------------------------
# AC3 — ENV-Auflösung fällt ohne Override auf "hard", nicht "observe"
# (Nic-Setzung 2026-08-11 betrifft den WERT, nicht den Mechanismus — die
# Naht selbst ist RAT-32 Nicht-Verhandelbar, siehe Testblock weiter unten)
# ---------------------------------------------------------------------------


def test_default_mode_ist_hard_nicht_observe():
    """panel/main.py: `_AUTH_MODE = os.environ.get("XBUDDY_AUTH_MODE", "hard")`.

    Belegt den WERT der ENV-Auflösung direkt (kein Literal im Factory-Aufruf
    mehr, s. `default_mode="hard"`-Historie in Vor-Version dieses Tests) —
    ohne `XBUDDY_AUTH_MODE`-Override bleibt der Default "hard", nicht
    "observe" (Nic-Setzung 2026-08-11). Form wie
    `tests/test_dual_gate_7b.py::test_auth_mode_env_seam_default_observe`
    bei seiten (dort Default "observe")."""
    assert os.environ.get("XBUDDY_AUTH_MODE", "hard") == panel_main._AUTH_MODE
    assert panel_main._AUTH_MODE in ("observe", "hard")


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


# ---------------------------------------------------------------------------
# ENV-Naht XBUDDY_AUTH_MODE — RAT-32 Nicht-Verhandelbar
# ---------------------------------------------------------------------------
#
# `_AUTH_MODE` und der daraus gebaute `require_dual_gate`-Decorator werden
# EINMAL beim Modul-Import aus `os.environ` gelesen (wie beim seiten-Vorbild)
# — ein live laufender Prozess flippt nicht mit, genau wie in Produktion
# (ENV-Änderung + systemd-Neustart, nie ein Live-Toggle). `importlib.reload`
# simuliert diesen Neustart im Testprozess. Da `panel.main` ein Singleton in
# `sys.modules` ist und andere Testdateien (`test_panel.py`,
# `test_panel_editor_seite.py`, dieser Datei selbst) dieselbe Modul-Referenz
# halten, stellt die Fixture den Default-Zustand (kein ENV-Override,
# mode="hard") garantiert wieder her — sonst würde ein liegen gebliebener
# Reload AC3 in JEDER anderen Testdatei dieser Suite stumm brechen.


@pytest.fixture
def _reset_panel_main_env(monkeypatch):
    yield
    monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
    importlib.reload(panel_main)


@pytest.mark.usefixtures("_reset_panel_main_env")
def test_auth_mode_env_naht_observe_ist_rueckroll_default_bleibt_hart(monkeypatch):
    """RAT-32 Nicht-Verhandelbar (decisions/RAT-32-auth-cookie-only-hart.md:39-46,
    Lehre #1427→#1430): der Hard-Flip ist eine ENV-Naht, kein Code-Diff
    (Kill-Kriterium der Entscheidung wörtlich: "gepairtes Gerät bekommt nach
    dem Flip 401 → ENV sofort zurück auf observe"). `XBUDDY_AUTH_MODE=observe`
    muss den static-Endpunkt (bare `@require_dual_gate()`, kein Route-Override)
    ohne Cookie durchs Gate lassen; ohne ENV-Override bleibt der Default
    "hard" (Nic-Setzung 2026-08-11 — Unterschied zum seiten-Vorbild, dessen
    Default "observe" ist, seiten/main.py:469). Auch der
    `app.view_functions["static"]`-Tausch (panel/main.py) hängt an derselben
    Naht — ein Static-Endpunkt, der hart bliebe, während der Rest zurückrollt,
    wäre ein halber Rückroll.

    panel/ hat kein `static/`-Verzeichnis (wie in `test_static_endpoint_mit_
    cookie_passiert_gate` oben) — ein durchgelassener Request liefert daher
    404 (Werkzeug-static-View, Datei fehlt), NICHT 200; das unterscheidet
    "Gate hat durchgelassen" (404) von "Gate hat geblockt" (401)."""
    monkeypatch.setenv("XBUDDY_AUTH_MODE", "observe")
    importlib.reload(panel_main)
    assert panel_main._AUTH_MODE == "observe"
    panel_main.configure(panel_main.runtime["registry"], bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    r_observe = panel_main.app.test_client().get("/static/irgendwas.txt")
    assert r_observe.status_code == 404, (
        "XBUDDY_AUTH_MODE=observe muss den static-Endpunkt ohne Cookie "
        "durchs Gate lassen (RAT-32-Rückroll-Pfad) — 404 aus der dahinter "
        "liegenden static-View (keine Datei), NICHT 401 (Gate-Block), "
        "got %d" % r_observe.status_code
    )

    monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
    importlib.reload(panel_main)
    assert panel_main._AUTH_MODE == "hard"
    panel_main.configure(panel_main.runtime["registry"], bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    r_default = panel_main.app.test_client().get("/static/irgendwas.txt")
    assert r_default.status_code == 401, (
        "ohne ENV-Override muss der Default weiterhin 'hard' sein "
        "(Nic-Setzung 2026-08-11), got %d" % r_default.status_code
    )


# ---------------------------------------------------------------------------
# AUTH-3.a — WRITE bleibt hart, auch unter XBUDDY_AUTH_MODE=observe
# (Watchdog-Befund 2026-08-11/12, Live-Reproduktion: ohne diesen literalen
# mode="hard" legt ein Request OHNE jeden Cookie unter observe eine
# Panel-Instanz an — genau der "je 200 ohne valide Quelle"-Regressions-Bug,
# den auth.md AUTH-3.a wörtlich ausschließt)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_reset_panel_main_env")
def test_post_panel_bleibt_hart_unter_observe(monkeypatch, tmp_path):
    """AUTH-3.a (specs/platform/auth.md:300-303/320-323, wörtlich):
    "WRITE-Routen (POST/PUT/PATCH/DELETE) … bleiben HART ab Tag 0. Keine
    Grace, kein Observe-Fenster" und "Eine WRITE-/#1321-Route, die je 200
    ohne valide Quelle liefert, ist ein Regressions-Bug (nie beabsichtigt)."

    `POST /api/v1/panels/` trägt `@require_dual_gate(mode="hard")` literal
    (panel/main.py, wie `PUT .../tiles`) — NICHT `mode=_AUTH_MODE`. Die
    ENV-Naht (RAT-32 Nicht-Verhandelbar, s. Testblock oben) gilt für den
    Rückroll-Pfad der READ-Display-Fläche, nicht für Schreib-Endpunkte:
    selbst mit `XBUDDY_AUTH_MODE=observe` muss ein POST ohne Cookie 401
    bleiben, sonst legt ein anonymer Request eine Panel-Instanz an."""
    monkeypatch.setenv("XBUDDY_AUTH_MODE", "observe")
    importlib.reload(panel_main)
    assert panel_main._AUTH_MODE == "observe"

    panels_path = tmp_path / "panels.json"
    panels_path.write_text('{"panels": []}', encoding="utf-8")
    reg = registry_mod.load(str(panels_path))
    panel_main.configure(reg, registry_path=str(panels_path), bot_token=_BOT_TOKEN)
    panel_main.app.testing = True

    r = panel_main.app.test_client().post(
        "/api/v1/panels/", json={"slug": "anonym"})
    assert r.status_code == 401, (
        "AUTH-3.a: POST /api/v1/panels/ muss auch unter "
        "XBUDDY_AUTH_MODE=observe ohne Cookie 401 liefern (WRITE hart ab "
        "Tag 0, kein Observe-Grace), got %d — %r"
        % (r.status_code, r.get_data(as_text=True))
    )
    # Backstop: die Instanz wurde NICHT angelegt.
    daten = json.loads(panels_path.read_text(encoding="utf-8"))
    assert daten["panels"] == [], (
        "AUTH-3.a-Regressions-Bug: POST hat trotz 401 eine Panel-Instanz "
        "angelegt — panels.json: %r" % daten
    )
