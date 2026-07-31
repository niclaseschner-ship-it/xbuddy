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


# RAT-35 (#1546): Der Shell-Zustand ist per ephemerer `sid` gekeyed. Die Tests
# fahren gegen die "legacy"-Fallback-sid (sid-loser HTTP-Request → gleicher Key),
# damit HTTP-Client-Calls ohne ?sid= und interne API-Calls dieselbe Session
# treffen. Der Zwei-sid-Isolations-Test nutzt bewusst explizite sids A/B.
_SID = seiten_main._SHELL_LEGACY_SID


@pytest.fixture(autouse=True)
def _reset_shell_state():
    """Jeder Test startet mit leeren Shell-Sessions (RAT-35: sid-gekeyt). Der
    Reset räumt ALLE Sessions, damit kein Zustand zwischen Tests leakt."""
    seiten_main.configure(bot_token=BOT_TOKEN)
    with seiten_main._shell_sessions_lock:
        seiten_main._shell_sessions.clear()
    yield
    with seiten_main._shell_sessions_lock:
        seiten_main._shell_sessions.clear()


def _shell_state_for(sid=_SID):
    """Liest den aktuellen State einer sid-Session (oder None), threadsicher."""
    with seiten_main._shell_sessions_lock:
        sess = seiten_main._shell_sessions.get(sid)
        return sess["state"] if sess is not None else None


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
    """AC1: GET /shell/<panel_id>/events liefert einen text/event-stream (#1542
    last-state-on-subscribe): hat der Server beim Verbinden einen gesetzten Zustand,
    ist das erste Event payload.url; ist er None, kein Geister-Event (nur Heartbeats).

    Dieser Test prueft den gesetzten Fall: Zustand vorbelegen, dann verbinden —
    erstes Event traegt payload.url (AC1). Den None-Fall deckt test_ac3_ruhe_zustand_nur_heartbeat."""
    seiten_main._apply_shell_trigger(_SID, {"app": "hoerspiel", "view": "player"})
    c = _auth_client()
    resp = c.get("/shell/" + PANEL_ID + "/events", buffered=False)
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert resp.headers.get("Cache-Control") == "no-cache"
    # Erstes Event muss den gesetzten Zustand tragen (kein Geister-null vor dem echten State).
    gen = resp.response
    first = next(iter(gen))
    if isinstance(first, bytes):
        first = first.decode("utf-8")
    assert first.startswith("data: ")
    state = json.loads(first[len("data: "):].strip())
    assert state is not None, (
        "Erstes SSE-Event bei gesetztem Zustand darf KEIN null sein "
        "(last-state-on-subscribe #1542)"
    )
    assert state["payload"]["url"] == "/display/hoerspiel/player"
    gen.close()


def test_ac1_sse_kein_routing_json():
    """AC1: Der Stream hängt an KEINEM routing.json/display_id-Lookup — der
    prozess-weite Zustand ist die einzige Quelle (ein Gerät = ein Ziel)."""
    # Zustand vorbelegen, ohne Router/routing.json anzufassen:
    seiten_main._apply_shell_trigger(_SID, {"app": "hoerspiel", "view": "player"})
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
    assert _shell_state_for()["payload"]["url"] == "/display/essen/liste?tag=montag"


def test_ac2_ingest_publiziert_an_offenen_stream():
    """AC2: Ein Ingest publiziert den neuen Zustand an einen offenen SSE-Stream
    (beobachtbar in der Subscriber-Queue) — Tap → SSE-Event, ohne router."""
    q = seiten_main._shell_subscribe(_SID)
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
        seiten_main._shell_unsubscribe(_SID, q)


def test_ac2_panel_cleared_setzt_ruhezustand():
    """AC2: panel_cleared setzt den Ruhe-Zustand (None) und publiziert ihn."""
    seiten_main._apply_shell_trigger(_SID, {"app": "hoerspiel", "view": "player"})
    q = seiten_main._shell_subscribe(_SID)
    try:
        c = _auth_client()
        r = c.post("/shell/" + PANEL_ID + "/events", json={"type": "panel_cleared"})
        assert r.status_code == 204
        assert _shell_state_for() is None
        assert q.get(timeout=1.0) is None
    finally:
        seiten_main._shell_unsubscribe(_SID, q)


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
#  RAT-35 (#1546) — sid-Isolation: der Bug-Beweis
# ============================================================

def test_rat35_publish_erreicht_nur_eigene_sid():
    """RAT-35 (#1546) KERN-AC: Zwei Shell-Dokumente mit VERSCHIEDENEN sids (A/B,
    z. B. Pi und Tablet mit derselben panel_id) sind voneinander isoliert.

    Ein _apply_shell_trigger auf sid A publiziert NUR an A-Subscriber; die
    B-Queue bleibt leer. Das ist der eigentliche Bug-Beweis: vor RAT-35 teilten
    sich beide Geräte einen prozess-weiten Zustand + eine Subscriber-Menge, ein
    Tap auf einem Gerät swappte auch das andere. Mit sid-Keying nicht mehr."""
    import queue as _queue

    sid_a = "sid-A-pi"
    sid_b = "sid-B-tablet"

    q_a = seiten_main._shell_subscribe(sid_a)
    q_b = seiten_main._shell_subscribe(sid_b)
    try:
        # Trigger NUR auf A.
        seiten_main._apply_shell_trigger(sid_a, {"app": "hoerspiel", "view": "player"})

        # A-Subscriber bekommt das Event ...
        published_a = q_a.get(timeout=1.0)
        assert published_a is not None
        assert published_a["payload"]["url"] == "/display/hoerspiel/player"

        # ... B-Subscriber bekommt NICHTS (der Isolations-Beweis).
        with pytest.raises(_queue.Empty):
            q_b.get(timeout=0.2)

        # Auch der gespeicherte State ist pro sid getrennt:
        assert _shell_state_for(sid_a) is not None
        assert _shell_state_for(sid_b) is None
    finally:
        seiten_main._shell_unsubscribe(sid_a, q_a)
        seiten_main._shell_unsubscribe(sid_b, q_b)


def test_rat35_leerer_subscriber_set_gc_loescht_session():
    """RAT-35 (#1546): Geht der letzte Subscriber einer sid, wird ihre Session
    GC'd — sonst leaken anonyme sids prozess-weit (Registry-frei-Riegel)."""
    sid = "sid-ephemeral"
    q = seiten_main._shell_subscribe(sid)
    with seiten_main._shell_sessions_lock:
        assert sid in seiten_main._shell_sessions
    seiten_main._shell_unsubscribe(sid, q)
    with seiten_main._shell_sessions_lock:
        assert sid not in seiten_main._shell_sessions, (
            "Session muss nach dem letzten Unsubscribe GC'd sein (kein sid-Leak)"
        )


def test_t1602_publish_n3_erreicht_nur_eigene_sid():
    """T1602 (RAT-35, n=3-Abnahme): Nics realer Betrieb ist Pi + 2 Tablets = DREI
    Geräte am selben Panel-Link, jedes mit eigener ephemerer `sid`. Server-seitiger
    Beweis der Isolations-Invariante bei n=3: ein Trigger auf Gerät A landet NUR bei
    A — B UND C bleiben beide leer (nicht nur „das eine andere" wie im n=2-Test).

    Das ist der Server-Anteil der #1602-Abnahme; der Tap-Isolations-Nachweis auf
    echter Hardware bleibt manuelle_probe (heim-shell.md SHELL-4, nicht headless
    automatisierbar)."""
    import queue as _queue

    sid_pi = "sid-pi-1920"
    sid_tab_a = "sid-tablet-a"
    sid_tab_b = "sid-tablet-b"

    q_pi = seiten_main._shell_subscribe(sid_pi)
    q_a = seiten_main._shell_subscribe(sid_tab_a)
    q_b = seiten_main._shell_subscribe(sid_tab_b)
    try:
        # Trigger NUR auf dem Pi.
        seiten_main._apply_shell_trigger(sid_pi, {"app": "hoerspiel", "view": "player"})

        # Pi-Subscriber bekommt das Event ...
        published_pi = q_pi.get(timeout=1.0)
        assert published_pi is not None
        assert published_pi["payload"]["url"] == "/display/hoerspiel/player"

        # ... BEIDE Tablets bekommen NICHTS (n=3-Isolations-Beweis: kein Leak auf
        # ein weiteres Gerät, nicht nur auf „das eine andere").
        with pytest.raises(_queue.Empty):
            q_a.get(timeout=0.2)
        with pytest.raises(_queue.Empty):
            q_b.get(timeout=0.2)

        # State ist pro sid getrennt — nur der Pi trägt Zustand.
        assert _shell_state_for(sid_pi) is not None
        assert _shell_state_for(sid_tab_a) is None
        assert _shell_state_for(sid_tab_b) is None
    finally:
        seiten_main._shell_unsubscribe(sid_pi, q_pi)
        seiten_main._shell_unsubscribe(sid_tab_a, q_a)
        seiten_main._shell_unsubscribe(sid_tab_b, q_b)


def test_t1602_reconnect_zyklus_n3_leakt_keine_sessions():
    """T1602 (RAT-35 SHELL-4-Kill-Kriterium auf n=3): Wiederholte Netz-Cut/
    Reconnect-Zyklen mit drei Geräten dürfen die Session-Zahl NICHT wachsen
    lassen (Geister-`sid`-Leak). Nach jedem vollständigen Disconnect-Zyklus ist
    die Session-Menge wieder auf dem Ausgangsstand — der Server-Beweis für das
    „EventSource-/`sid`-Zahl wächst nicht"-Kriterium des #1602-Gates."""
    with seiten_main._shell_sessions_lock:
        baseline = len(seiten_main._shell_sessions)

    sids = ["sid-pi-1920", "sid-tablet-a", "sid-tablet-b"]
    for _ in range(5):  # fünf Cut/Reconnect-Runden
        queues = [(s, seiten_main._shell_subscribe(s)) for s in sids]
        with seiten_main._shell_sessions_lock:
            assert len(seiten_main._shell_sessions) == baseline + 3
        # Netz-Cut: alle drei Geräte verlieren die Verbindung.
        for s, q in queues:
            seiten_main._shell_unsubscribe(s, q)
        with seiten_main._shell_sessions_lock:
            assert len(seiten_main._shell_sessions) == baseline, (
                "Nach Reconnect-Zyklus dürfen keine Geister-Sessions bleiben "
                "(SHELL-4-Kill-Kriterium, n=3)"
            )


def test_rat35_events_ohne_sid_fallen_auf_legacy():
    """RAT-35 (#1546): Ein POST OHNE ?sid= (gecachtes altes Shell-Dokument) trifft
    die weiche "legacy"-Session — funktionsfähig, additiv, kein 400/Registry."""
    c = _auth_client()
    r = c.post(
        "/shell/" + PANEL_ID + "/events",
        json={"type": "tile_selected", "app": "essen", "view": "liste"},
    )
    assert r.status_code == 204
    assert _shell_state_for(seiten_main._SHELL_LEGACY_SID) is not None
    assert _shell_state_for(seiten_main._SHELL_LEGACY_SID)["payload"]["url"] == \
        "/display/essen/liste"


def test_rat35_events_mit_sid_trennt_von_legacy():
    """RAT-35 (#1546): Ein POST MIT ?sid=X landet in Session X, NICHT in legacy —
    HTTP-Ebene-Beweis, dass der Query-Param durchgereicht wird."""
    c = _auth_client()
    r = c.post(
        "/shell/" + PANEL_ID + "/events?sid=geraet-X",
        json={"type": "tile_selected", "app": "hoerspiel", "view": "player"},
    )
    assert r.status_code == 204
    assert _shell_state_for("geraet-X") is not None
    assert _shell_state_for("geraet-X")["payload"]["url"] == "/display/hoerspiel/player"
    # legacy blieb unberuehrt (keine Cross-Kontamination):
    assert _shell_state_for(seiten_main._SHELL_LEGACY_SID) is None


def test_t1542_subscribe_nach_post_liefert_zustand_sofort():
    """#1542 AC2 — Race-Reproduktion: Subscribe NACH einem tile_selected-POST.

    Szenario: Der erste Tap setzt _shell_state (POST), findet aber noch keinen
    Subscriber (SSE-connect-Race) — der Broadcast verpufft. Mit last-state-on-
    subscribe liest der Generator NACH _shell_subscribe() den bereits gesetzten
    Zustand und liefert ihn als erstes SSE-Event, OHNE auf einen zweiten Tap
    zu warten. Das ist der Beweis, dass der Doppel-Tap-Bug geschlossen ist.

    Test-Reihenfolge erzwingt die Race: _shell_state setzen (kein Subscriber),
    dann _shell_event_stream starten — erstes Event muss payload.url tragen.
    Wir nutzen die interne API direkt (kein HTTP via Werkzeug-Testclient), weil
    c.get(buffered=False) bis zum ersten yield blockiert — das ist beim Werkzeug-
    Testclient normales Verhalten und kein Bug im Server-Code."""
    c = _auth_client()

    # POST zuerst — kein Subscriber → Broadcast geht ins Leere (Race-Kern).
    r = c.post(
        "/shell/" + PANEL_ID + "/events",
        json={"type": "tile_selected", "app": "hoerspiel", "view": "player"},
    )
    assert r.status_code == 204
    assert _shell_state_for() is not None, (
        "POST muss den sid-State setzen, unabhaengig von Subscribern"
    )

    # Jetzt SSE-Generator direkt starten — prueft last-state-on-subscribe intern.
    # _shell_event_stream liest _shell_state NACH _shell_subscribe() (Reihenfolge
    # load-bearing: Race-Schluss). Erster yield muss sofort den Zustand liefern.
    gen = seiten_main._shell_event_stream(_SID)
    try:
        first_raw = next(gen)
        if isinstance(first_raw, bytes):
            first_raw = first_raw.decode("utf-8")

        # Erstes Event muss den Zustand des ersten Taps tragen (kein zweiter Tap noetig).
        assert first_raw.startswith("data: "), "SSE-Event muss mit 'data: ' beginnen"
        state = json.loads(first_raw[len("data: "):].strip())
        assert state is not None, (
            "Erstes SSE-Event nach Subscribe muss den gesetzten Zustand tragen, "
            "nicht null (last-state-on-subscribe #1542 — Race nicht geschlossen)"
        )
        assert state.get("type") != "heartbeat", (
            "Erstes Event darf kein Heartbeat sein — Zustand muss sofort kommen"
        )
        assert state["payload"]["url"] == "/display/hoerspiel/player", (
            "payload.url muss dem tile_selected-POST entsprechen "
            "(erster Tap muss Pane swappen, zweiter Tap darf nicht noetig sein)"
        )
    finally:
        gen.close()


def test_t1542_ruhe_zustand_nur_heartbeat():
    """#1542 AC3 — Subscribe bei leerem Zustand (None): kein Geister-Event.

    Ist _shell_state None beim Connect, sendet der Stream KEIN initiales data-
    Event (kein 'data: null\\n\\n'). Die Queue blockiert bis zum naechsten
    tile_selected-Broadcast oder Heartbeat-Timeout. Dieser Test prueft, dass
    kein spontanes null-Event kommt, das den Client-Guard (current=null) falsch
    vorbelegt — das wuerde einen spaeteren panel_cleared-Broadcast unsichtbar machen
    (next===current===null → kein removeAttribute('src')).

    Probe via Generator + Broadcast: Generator starten (subscribes), dann einen
    Nicht-None-Zustand broadcasen — erstes yield muss den Broadcast tragen, nicht
    ein vorangegangenes Geister-null. So beweisen wir, dass kein null vor dem
    echten State yield wird."""
    import threading

    # Voraussetzung: Ruhe-Zustand.
    assert _shell_state_for() is None

    gen = seiten_main._shell_event_stream(_SID)
    result = []
    exc_holder = []

    def _advance():
        try:
            val = next(gen)
            result.append(val)
        except StopIteration:
            result.append(b"STOP")
        except Exception as e:
            exc_holder.append(e)

    # Generator in Background starten — blockiert bis erstes yield.
    t = threading.Thread(target=_advance, daemon=True)
    t.start()

    # Kurz warten bis subscriber registriert ist (Generator laeuft bis q.get()).
    def _sid_subscribers():
        with seiten_main._shell_sessions_lock:
            sess = seiten_main._shell_sessions.get(_SID)
            return set(sess["subscribers"]) if sess is not None else set()

    import time
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if _sid_subscribers():
            break
        time.sleep(0.01)

    assert _sid_subscribers(), (
        "Generator muss sich innerhalb 1s subscriben"
    )
    # Noch kein yield eingetreten (kein Geister-null-Event).
    assert not result, (
        "Generator darf bei None-Zustand KEINEN sofortigen Yield vor Broadcast "
        "liefern (kein 'data: null' — AC3 #1542). Yield war: %r" % result
    )

    # Jetzt einen Zustand broadcasen — das erste yield muss diesen State tragen.
    seiten_main._apply_shell_trigger(_SID, {"app": "essen", "view": "liste"})
    t.join(timeout=1.0)
    assert result, "Generator muss nach Broadcast yielden"
    assert not exc_holder, "Unerwartete Exception: %r" % exc_holder

    first = result[0]
    if isinstance(first, bytes):
        first = first.decode("utf-8")
    state = json.loads(first[len("data: "):].strip())
    assert state is not None, (
        "Erstes SSE-Event muss den gesendeten State sein, nicht null "
        "(kein Geister-null vor dem echten State — AC3 #1542)"
    )
    assert state["payload"]["url"] == "/display/essen/liste", (
        "payload.url muss dem Broadcast entsprechen"
    )
    gen.close()


# ============================================================
#  AC3 — Pre-Merge-Smoke: Tap-links → Refresh-rechts, router+panel umgangen
# ============================================================

def test_ac3_smoke_tap_links_refresh_rechts_ohne_router():
    """AC3: End-to-end same-device in-Prozess — ein tile_selected-Ingest (was die
    linke Nav bei leerem router_url an die Origin postet, app.js:985) erreicht
    einen offenen SSE-Stream (rechtes Pane) als payload.url. Weder router noch
    panel/controller sind beteiligt: der Pfad läuft rein über seiten_main.

    Das ist der entry_path_probe-Beweis (Ingest → SSE publish → Pane).

    Implementierungshinweis zu Werkzeug-Testclient: buffered=False blockiert beim
    c.get() bis das erste yield aus dem Generator kommt. Deshalb setzen wir den
    Zustand vor dem GET — so liefert der Generator sofort das erste Event (kein
    15s-Heartbeat-Wait). Der zweite Tap prueft den Broadcast-Pfad (subscriber
    existiert, publish → Queue → naechstes next(gen) liefert neuen Zustand)."""
    # Rechtes Pane: Zustand vorbelegen, dann SSE öffnen.
    # (last-state-on-subscribe: erster yield liefert sofort den vorhandenen Zustand)
    seiten_main._apply_shell_trigger(_SID, {"app": "hoerspiel", "view": "player"})
    c = _auth_client()
    stream = c.get("/shell/" + PANEL_ID + "/events", buffered=False)
    gen = iter(stream.response)

    # Erstes Event: der beim Connect nachgelieferte Zustand (last-state-on-subscribe).
    initial = next(gen)
    if isinstance(initial, bytes):
        initial = initial.decode("utf-8")
    init_state = json.loads(initial[len("data: "):].strip())
    assert init_state is not None, "Erstes Event muss den vorhandenen Zustand liefern"
    assert init_state["payload"]["url"] == "/display/hoerspiel/player"

    # Linke Nav tippt eine andere Kachel → Ingest an die seiten-Origin (kein router).
    # subscriber existiert jetzt → broadcast landet in der Queue.
    tap = c.post(
        "/shell/" + PANEL_ID + "/events",
        json={"type": "tile_selected", "app": "essen", "view": "liste"},
    )
    assert tap.status_code == 204

    # Rechtes Pane sieht die Änderung als nächstes SSE-Event (Broadcast-Pfad).
    nxt = next(gen)
    if isinstance(nxt, bytes):
        nxt = nxt.decode("utf-8")
    state = json.loads(nxt[len("data: "):].strip())
    assert state is not None
    assert state.get("type") != "heartbeat"
    assert state["payload"]["url"] == "/display/essen/liste", (
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
    assert _shell_state_for() is not None
    assert _shell_state_for()["payload"]["url"] == "/display/hoerspiel/player"


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


# ============================================================
#  T1547 — Aus-Kachel / panel_cleared → Pane leeren (JS-Template-Fix)
# ============================================================

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates", "heim-shell.html",
)


def _template_body() -> str:
    with open(_TEMPLATE_PATH, encoding="utf-8") as fh:
        return fh.read()


def test_t1547_template_enthaelt_remove_attribute_src():
    """T1547 AC1: Das Template hat einen else-/null-Zweig mit removeAttribute('src').

    Beweist, dass cleared (next===null) die Pane leert statt sie zu ignorieren.
    Der Guard muss NACH dem if(next){...}-Block stehen, damit der truthy-Pfad
    (pane.src=next + Fokus) unberuehrt bleibt (AC2).
    """
    body = _template_body()
    assert "pane.removeAttribute('src')" in body, (
        "heim-shell.html muss pane.removeAttribute('src') im null-Zweig enthalten "
        "(T1547: Aus-Kachel leert die Pane)"
    )


def test_t1547_template_truthy_pfad_unveraendert():
    """T1547 AC2: Der truthy-Pfad (pane.src = next) bleibt im Template erhalten.

    Stellt sicher, dass der Fix den existing Swap-Pfad nicht entfernt hat.
    """
    body = _template_body()
    assert "pane.src = next;" in body, (
        "heim-shell.html muss weiterhin 'pane.src = next;' im truthy-Zweig enthalten "
        "(T1547: truthy-Pfad darf nicht veraendert werden)"
    )
    # Fokus-Logik ebenfalls unveraendert vorhanden:
    assert "pane.blur" in body, (
        "Fokus-Logik (pane.blur) darf durch T1547-Fix nicht entfernt worden sein"
    )


def test_t1547_cleared_event_setzt_shell_state_auf_none():
    """T1547 AC3 (Backend): panel_cleared publiziert None — der SSE-Null-Trigger,
    den der Browser-Client als 'next===null' auswertet und mit removeAttribute('src')
    beantwortet.

    Prueft den seiten-seitigen Publish-Pfad: nach Cleared ist _shell_state==None
    und der publizierte Wert in der Queue ebenfalls None.
    """
    seiten_main._apply_shell_trigger(_SID, {"app": "hoerspiel", "view": "player"})
    q = seiten_main._shell_subscribe(_SID)
    try:
        c = _auth_client()
        r = c.post("/shell/" + PANEL_ID + "/events", json={"type": "panel_cleared"})
        assert r.status_code == 204
        assert _shell_state_for() is None, (
            "sid-State muss nach panel_cleared None sein"
        )
        published = q.get(timeout=1.0)
        assert published is None, (
            "publizierter Wert nach panel_cleared muss None sein "
            "(Browser empfaengt null → next===null → removeAttribute('src'))"
        )
    finally:
        seiten_main._shell_unsubscribe(_SID, q)


def test_t1547_truthy_event_setzt_url_in_state():
    """T1547 AC3 (Backend): tile_selected publiziert payload.url — der truthy-Trigger,
    den der Browser-Client als 'next!==null' auswertet und mit pane.src=next beantwortet.
    """
    q = seiten_main._shell_subscribe(_SID)
    try:
        c = _auth_client()
        r = c.post(
            "/shell/" + PANEL_ID + "/events",
            json={"type": "tile_selected", "app": "essen", "view": "liste"},
        )
        assert r.status_code == 204
        published = q.get(timeout=1.0)
        assert published is not None, "truthy Event muss einen nicht-None-State publizieren"
        assert published["payload"]["url"] == "/display/essen/liste", (
            "payload.url muss /display/essen/liste sein"
        )
    finally:
        seiten_main._shell_unsubscribe(_SID, q)


# ============================================================
#  T1551 — Aus/Cleared → schwarzer Bildschirm (Display-aus-Anmutung)
# ============================================================

def test_t1551_css_buddy_hintergrund_schwarz():
    """T1551 AC1: heim-shell.css setzt background:#000 auf .buddy — der Ruhe-
    Zustand scheint schwarz durch, wenn der Iframe (display:none) versteckt ist.
    """
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "heim-shell.css",
    )
    with open(css_path, encoding="utf-8") as fh:
        css = fh.read()
    assert "background: #000" in css, (
        "heim-shell.css muss 'background: #000' auf .buddy setzen "
        "(T1551: schwarzer Ruhe-Zustand wenn Iframe versteckt ist)"
    )


def test_t1551_template_cleared_zweig_display_none():
    """T1551 AC1/AC3: Der cleared-Zweig im Template setzt pane.style.display='none',
    damit der schwarze .buddy-Container (background:#000) durchscheint.

    Ein leerer oder about:blank-Iframe rendert standardmaessig weiss/beige;
    display:none + schwarzer Elterncontainer liefert die Aus-Anmutung zuverlaessig.
    """
    body = _template_body()
    assert "pane.style.display = 'none'" in body, (
        "heim-shell.html muss pane.style.display='none' im cleared-Zweig enthalten "
        "(T1551: Iframe verstecken sodass .buddy background:#000 sichtbar wird)"
    )


def test_t1551_template_truthy_zweig_stellt_display_wieder_her():
    """T1551 AC2: Der truthy-Zweig setzt pane.style.display='' (zurueck auf Block)
    BEVOR pane.src=next, damit der neue Buddy-View sofort sichtbar ist.

    Kein Regress am normalen Swap: Sichtbarkeit kommt VOR dem Src-Swap.
    """
    body = _template_body()
    assert "pane.style.display = '';" in body, (
        "heim-shell.html muss pane.style.display='' im truthy-Zweig enthalten "
        "(T1551: Sichtbarkeit vor pane.src=next wiederherstellen)"
    )
    # Sicherstellen, dass display-Reset VOR pane.src=next steht (Reihenfolge).
    idx_display = body.index("pane.style.display = '';")
    idx_src = body.index("pane.src = next;")
    assert idx_display < idx_src, (
        "pane.style.display='' muss im Template VOR pane.src=next stehen "
        "(T1551: erst sichtbar, dann src, kein Flash)"
    )


# ============================================================
#  T1542 — X-Accel-Buffering: no (Gürtel — App-seitiger Fix)
# ============================================================
#
# shell_events muss `X-Accel-Buffering: no` setzen, damit nginx die SSE-Response
# nicht puffert, auch wenn keine Regex-Location greift (Gürtel + Hosenträger).


def test_t1542_shell_events_traegt_x_accel_buffering_no():
    """T1542 (Gürtel): GET /shell/<panel_id>/events liefert den Header
    `X-Accel-Buffering: no`, der nginx anweist, diese Response NICHT zu puffern.

    Ohne diesen Header kommen Pane-Swap-SSE-Events erst beim 2. Tap an, weil
    nginx den Stream puffert bis ein internes Chunk-Limit erreicht ist.
    """
    seiten_main._apply_shell_trigger(_SID, {"app": "hoerspiel", "view": "player"})
    c = _auth_client()
    resp = c.get("/shell/" + PANEL_ID + "/events", buffered=False)
    assert resp.status_code == 200
    assert resp.headers.get("X-Accel-Buffering") == "no", (
        "shell_events muss 'X-Accel-Buffering: no' setzen "
        "(T1542 Gürtel: nginx-Pufferung am Stream-Ursprung abschalten)"
    )
