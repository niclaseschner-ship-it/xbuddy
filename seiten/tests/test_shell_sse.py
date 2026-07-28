"""Tests für den same-device Live-Refresh in seiten/ (RAT-31 E2, SHELL-4).

Verpflanzt aus router/main.py (ROU-22 SSE + POST /events tile_selected-Ingest),
BEVOR der Router-Fanout stirbt (heim-shell.md E0-Banner). Ein Gerät = ein Ziel:
KEIN routing.json-Lookup, KEIN display_id-Key, KEIN router/panel/controller-Hop.

Lauf: python3 -m pytest seiten/tests/test_shell_sse.py -q

Acceptance (Contract T1495):
  AC1 — seiten/ liefert einen SSE-Zustands-Stream (kein routing.json)
  AC2 — seiten/ nimmt tile_selected-Ingest + publiziert an SSE (kein router-Hop)
  AC3 — Pre-Merge-Smoke: Tap-links → Refresh-rechts, router+panel umgangen
"""

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import render as seiten_render  # noqa: E402
from tools.initdata import session_cookie as _sc  # noqa: E402

PANEL_ID = "paulas-panel-01"
BOT_TOKEN = "123456:ABCdef_testtoken"


@pytest.fixture(autouse=True)
def _reset_shell_state():
    """Jeder Test startet mit sauberem, prozess-weitem Shell-Zustand + leerer
    Subscriber-Menge (die Naht ist bewusst prozess-weit — RAT-31 ein Gerät)."""
    seiten_main.configure(bot_token=BOT_TOKEN)
    seiten_main._shell_state = None
    with seiten_main._shell_subscribers_lock:
        seiten_main._shell_subscribers.clear()
    yield
    seiten_main._shell_state = None
    with seiten_main._shell_subscribers_lock:
        seiten_main._shell_subscribers.clear()


def _auth_client():
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    c.set_cookie(_sc.COOKIE_NAME, _sc.sign_session("op", BOT_TOKEN))
    return c


# ============================================================
#  render.build_panel_url — byte-gleich zum Router (kein Render-Drift)
# ============================================================

def test_build_panel_url_ohne_query():
    assert seiten_render.build_panel_url("hoerspiel", "player", None) == "/display/hoerspiel/player"


def test_build_panel_url_mit_query_sortiert():
    """Byte-gleiche, deterministisch sortierte Query-Reihenfolge (wie ROU-24)."""
    url = seiten_render.build_panel_url("essen", "liste", {"b": "2", "a": "1"})
    assert url == "/display/essen/liste?a=1&b=2"


# ============================================================
#  AC1 — SSE-Zustands-Stream (Analog ROU-22, ohne routing.json)
# ============================================================

def test_ac1_sse_liefert_initialen_state():
    """AC1: GET /shell/<panel_id>/events liefert einen text/event-stream, dessen
    erstes data:-Event der initiale Zustand ist (None beim Kaltstart)."""
    c = _auth_client()
    resp = c.get("/shell/" + PANEL_ID + "/events", buffered=False)
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert resp.headers.get("Cache-Control") == "no-cache"
    # Erstes Event aus dem Generator ziehen (Zustand beim Verbinden).
    gen = resp.response
    first = next(iter(gen))
    if isinstance(first, bytes):
        first = first.decode("utf-8")
    assert first.startswith("data: ")
    assert json.loads(first[len("data: "):].strip()) is None
    gen.close()


def test_ac1_sse_kein_routing_json():
    """AC1: Der Stream hängt an KEINEM routing.json/display_id-Lookup — der
    prozess-weite Zustand ist die einzige Quelle (ein Gerät = ein Ziel)."""
    # Zustand vorbelegen, ohne Router/routing.json anzufassen:
    seiten_main._apply_shell_trigger({"app": "hoerspiel", "view": "player"})
    c = _auth_client()
    resp = c.get("/shell/" + PANEL_ID + "/events", buffered=False)
    gen = resp.response
    first = next(iter(gen))
    if isinstance(first, bytes):
        first = first.decode("utf-8")
    state = json.loads(first[len("data: "):].strip())
    assert state["payload"]["url"] == "/display/hoerspiel/player"
    gen.close()


# ============================================================
#  AC2 — tile_selected-Ingest → publish an SSE (kein router-Hop)
# ============================================================

def test_ac2_ingest_setzt_state_und_baut_url():
    """AC2: POST tile_selected an den seiten-Ingest setzt den Shell-Zustand mit
    payload.url == /display/<app>/<view>[?query] — kein router-Hop."""
    c = _auth_client()
    resp = c.post(
        "/shell/" + PANEL_ID + "/events",
        json={"type": "tile_selected", "app": "essen", "view": "liste",
              "query": {"tag": "montag"}},
    )
    assert resp.status_code == 204
    assert seiten_main._shell_state["payload"]["url"] == "/display/essen/liste?tag=montag"


def test_ac2_ingest_publiziert_an_offenen_stream():
    """AC2: Ein Ingest publiziert den neuen Zustand an einen offenen SSE-Stream
    (beobachtbar in der Subscriber-Queue) — Tap → SSE-Event, ohne router."""
    q = seiten_main._shell_subscribe()
    try:
        c = _auth_client()
        r = c.post(
            "/shell/" + PANEL_ID + "/events",
            json={"type": "tile_selected", "app": "hoerspiel", "view": "player"},
        )
        assert r.status_code == 204
        published = q.get(timeout=1.0)
        assert published["payload"]["url"] == "/display/hoerspiel/player"
    finally:
        seiten_main._shell_unsubscribe(q)


def test_ac2_panel_cleared_setzt_ruhezustand():
    """AC2: panel_cleared setzt den Ruhe-Zustand (None) und publiziert ihn."""
    seiten_main._apply_shell_trigger({"app": "hoerspiel", "view": "player"})
    q = seiten_main._shell_subscribe()
    try:
        c = _auth_client()
        r = c.post("/shell/" + PANEL_ID + "/events", json={"type": "panel_cleared"})
        assert r.status_code == 204
        assert seiten_main._shell_state is None
        assert q.get(timeout=1.0) is None
    finally:
        seiten_main._shell_unsubscribe(q)


def test_ac2_ingest_lehnt_ungueltiges_event_ab():
    """AC2: Validierung wie router adapt_app_panel — fehlendes view → 400."""
    c = _auth_client()
    r = c.post("/shell/" + PANEL_ID + "/events",
               json={"type": "tile_selected", "app": "essen"})
    assert r.status_code == 400
    r2 = c.post("/shell/" + PANEL_ID + "/events",
                json={"type": "quatsch"})
    assert r2.status_code == 400
    r3 = c.post("/shell/" + PANEL_ID + "/events",
                json={"type": "tile_selected", "app": "e", "view": "v",
                      "query": {"bad": {"nested": 1}}})
    assert r3.status_code == 400


# ============================================================
#  AC3 — Pre-Merge-Smoke: Tap-links → Refresh-rechts, router+panel umgangen
# ============================================================

def test_ac3_smoke_tap_links_refresh_rechts_ohne_router():
    """AC3: End-to-end same-device in-Prozess — ein tile_selected-Ingest (was die
    linke Nav bei leerem router_url an die Origin postet, app.js:985) erreicht
    einen offenen SSE-Stream (rechtes Pane) als payload.url. Weder router noch
    panel/controller sind beteiligt: der Pfad läuft rein über seiten_main.

    Das ist der entry_path_probe-Beweis (Ingest → SSE publish → Pane)."""
    # Rechtes Pane: SSE-Stream öffnen und initialen (Ruhe-)Zustand konsumieren.
    c = _auth_client()
    stream = c.get("/shell/" + PANEL_ID + "/events", buffered=False)
    gen = iter(stream.response)
    initial = next(gen)
    if isinstance(initial, bytes):
        initial = initial.decode("utf-8")
    assert json.loads(initial[len("data: "):].strip()) is None, "Start im Ruhe-Zustand"

    # Linke Nav tippt eine Kachel → Ingest an die seiten-Origin (kein router).
    tap = c.post(
        "/shell/" + PANEL_ID + "/events",
        json={"type": "tile_selected", "app": "hoerspiel", "view": "player"},
    )
    assert tap.status_code == 204

    # Rechtes Pane sieht die Änderung als nächstes SSE-Event (der Swap-Trigger).
    nxt = next(gen)
    if isinstance(nxt, bytes):
        nxt = nxt.decode("utf-8")
    state = json.loads(nxt[len("data: "):].strip())
    assert state is not None
    assert state.get("type") != "heartbeat"
    assert state["payload"]["url"] == "/display/hoerspiel/player", (
        "Tap-links muss als payload.url im SSE-Event des rechten Panes ankommen"
    )
    stream.response.close()


# ============================================================
#  AC3 — Body-Kompatibilität: makeTileSelected-Form → seiten-Ingest (T1519)
# ============================================================

def test_ac3_adapt_shell_event_akzeptiert_tile_selected_body():
    """AC3 (T1519): _adapt_shell_event akzeptiert den Body, den app.js
    via makeTileSelected baut (type/app/view Pflichtfelder, PANEL-6).

    Der sendEvent-Aufruf in app.js liefert genau diese Felder; seiten-Ingest
    muss ihn ohne 400 durchlassen. Kein router-Hop, kein source_id-Match —
    seiten nimmt jedes valide tile_selected (ein Gerät = ein Ziel)."""
    # Repräsentativer Body wie makeTileSelected ihn erzeugt (PANEL-6):
    body = {
        "source_id": "app-panel:paulas-panel-01",
        "ts": "2026-07-28T10:00:00.000Z",
        "type": "tile_selected",
        "app": "hoerspiel",
        "view": "player",
    }
    result, err = seiten_main._adapt_shell_event(body)
    assert err is None, (
        "_adapt_shell_event muss den makeTileSelected-Body ohne Fehler akzeptieren, "
        "bekommen: %r" % err
    )
    kind, descriptor = result
    assert kind == "trigger", "tile_selected muss 'trigger'-Kind liefern"
    assert descriptor["app"] == "hoerspiel"
    assert descriptor["view"] == "player"


def test_ac3_adapt_shell_event_akzeptiert_body_mit_query():
    """AC3 (T1519): _adapt_shell_event akzeptiert tile_selected mit optionalem
    query-Dict (PANEL-6/PANEL-7 — flaches Objekt) — wie app.js makeTileSelected
    es sendet, wenn tile.query gesetzt ist."""
    body = {
        "source_id": "app-panel:paulas-panel-01",
        "ts": "2026-07-28T10:00:00.000Z",
        "type": "tile_selected",
        "app": "essen",
        "view": "liste",
        "query": {"tag": "montag"},
    }
    result, err = seiten_main._adapt_shell_event(body)
    assert err is None, "Body mit query darf nicht abgelehnt werden: %r" % err
    _kind, descriptor = result
    assert descriptor.get("query") == {"tag": "montag"}


def test_ac3_ingest_endpunkt_akzeptiert_tile_selected_body():
    """AC3 (T1519): POST /shell/<panel_id>/events mit dem makeTileSelected-Body
    liefert HTTP 204 — server-seitiger Endpunkt-Beweis fuer die Sender/Empfaenger-
    Kompatibilitaet (Entry-Path-Probe ohne Tap auf echtem Tablet)."""
    c = _auth_client()
    body = {
        "source_id": "app-panel:paulas-panel-01",
        "ts": "2026-07-28T10:00:00.000Z",
        "type": "tile_selected",
        "app": "hoerspiel",
        "view": "player",
    }
    r = c.post("/shell/" + PANEL_ID + "/events", json=body)
    assert r.status_code == 204, (
        "POST /shell/<panel_id>/events mit makeTileSelected-Body muss 204 liefern "
        "(Sender-Empfaenger-Kompatibilitaet T1519 AC3), got %d" % r.status_code
    )
    assert seiten_main._shell_state is not None
    assert seiten_main._shell_state["payload"]["url"] == "/display/hoerspiel/player"


# ============================================================
#  T1538 — SW-Regression: SSE-Endpoint darf NICHT als Shell-HTML abgefangen werden
# ============================================================
#
# Wurzel: isShellHtml() in sw.js gab fuer /shell/<pid>/events fälschlich true
# zurueck (Suffix-Blacklist griff nicht auf sufixlosen Pfad). networkFirst
# klon-backpressured dann den SSE-Stream → rechte Buddy-Pane empfing nie payload.url.
# Fix: Regex-Check /^\/shell\/[^/]+\/?$/ — nur der bare Nav-Request ist HTML.
# Diese Tests fangen die Regression auf Python-Ebene: die gerenderte sw.js
# (shell_sw_view-Antwort-Body) muss den korrekten Regex enthalten.

_SW_JS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "shell", "sw.js",
)


def _rendered_sw_body() -> str:
    """Liest sw.js direkt vom Pfad (ohne BUILD_ID-Substitution, reicht fuer Regex-Pruefung)."""
    with open(_SW_JS_PATH, encoding="utf-8") as fh:
        return fh.read()


def test_t1538_sw_enthaelt_shell_html_regex():
    """T1538 AC2: Die gerenderte sw.js enthaelt den Navigations-Regex fuer isShellHtml.

    Der Regex ^/shell/[^/]+/?$ matcht NUR den bare Nav-Pfad /shell/<panel_id>
    (optional Trailing-Slash) — nicht Sub-Pfade wie /events, /sw.js, /icon-*.png.
    Sein Vorhandensein im Body beweist, dass die Suffix-Blacklist-Regression
    (T1538) nicht zurueckgekehrt ist.
    """
    body = _rendered_sw_body()
    assert r'/^\/shell\/[^/]+\/?$/' in body, (
        "sw.js muss den Navigations-Regex /^\\/shell\\/[^/]+\\/?$/ in isShellHtml "
        "enthalten — Suffix-Blacklist-Regression (T1538) wurde reintroduciert"
    )


def test_t1538_sw_events_pfad_nicht_als_html():
    """T1538 AC2: /shell/<pid>/events wird vom SW NICHT als Shell-HTML behandelt.

    Prueft direkt, ob der isShellHtml-Regex den SSE-Endpoint ausschliesst.
    Der Regex ^/shell/[^/]+/?$ darf '/shell/paulas-panel-01/events' NICHT matchen
    (events-Segment ist ein dritter Pfad-Teil). Schlaegt dieser Test fehl, wuerde der
    SSE-Stream durch networkFirst klon-backpressured und das rechte Pane blaese nie auf.
    """
    import re
    # Den Regex aus der sw.js direkt in Python uebersetzen und Pfade pruefen.
    shell_nav_re = re.compile(r'^/shell/[^/]+/?$')

    assert not shell_nav_re.match('/shell/paulas-panel-01/events'), (
        "isShellHtml-Regex darf /shell/<pid>/events NICHT matchen "
        "(SSE-Stream wuerde durch networkFirst erwuergt — T1538)"
    )
    assert shell_nav_re.match('/shell/paulas-panel-01'), (
        "isShellHtml-Regex muss /shell/<pid> matchen (bare Nav-Pfad — T1448)"
    )
    assert shell_nav_re.match('/shell/paulas-panel-01/'), (
        "isShellHtml-Regex muss /shell/<pid>/ matchen (Trailing-Slash-Variante)"
    )
    assert not shell_nav_re.match('/shell/paulas-panel-01/sw.js'), (
        "isShellHtml-Regex darf /shell/<pid>/sw.js NICHT matchen"
    )
    assert not shell_nav_re.match('/shell/paulas-panel-01/icon-192.png'), (
        "isShellHtml-Regex darf /shell/<pid>/icon-192.png NICHT matchen"
    )
