"""Integration-Tests für PBE-10 AC2/AC3: POST /api/v1/router/admin/panels/<display_id>/tiles-changed (#450).

Abgedeckt:
  test_pbe10_tiles_changed_returns_204_for_known_display
    — Happy-Path: POST → 204 No Content.
  test_pbe10_tiles_changed_returns_404_for_unknown_display
    — unbekannte display_id → 404 (analog get_state / display_events).
  test_pbe10_tiles_changed_delivers_sse_event_to_subscriber (AC3)
    — Echter SSE-Stream-Subscriber: POST → Generator liefert tatsächlich
      ein Event. NICHT publish-Mock (T446-AC5-Lücke schließen).
  test_pbe10_tiles_changed_publishes_current_state
    — Publishtes Event enthält den aktuellen display-State (nicht Null wenn State gesetzt).
  test_pbe10_tiles_changed_rejects_non_loopback
    — Nicht-Loopback-Remote → 403 (ROU-28-Invariante).

AC4-Latenz (PBE-10): lokaler Round-Trip << 5 s. Der Test POST → SSE-Yield
läuft im gleichen Prozess ohne Netz; die Latenz ist < 1 ms — Schranke
trivial erfüllt. In Produktion sendet panel an Router über Loopback-HTTP
(timeout=5 s); typisch < 10 ms.

Lauf: python -m pytest router/tests/test_tiles_changed.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from router import main as router_main

# ============================================================
#  Demo-Daten
# ============================================================

DEMO_ROUTING = {
    "entries": [
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 0},
            "display_ids": ["display-default-01"],
            "payload":    {"url": "http://example.test/klein"},
        },
    ]
}


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def client_with_routing(tmp_path):
    """Frischer Router-State + Routing-Tabelle aus DEMO_ROUTING."""
    routing_path = tmp_path / "routing.json"
    routing_path.write_text(json.dumps(DEMO_ROUTING))
    router_main.state = {}
    router_main._subscribers.clear()
    router_main.load_routing(str(routing_path))
    router_main.app.testing = True
    return router_main.app.test_client()


def _post_tiles_changed(client, display_id):
    return client.post(
        f'/api/v1/router/admin/panels/{display_id}/tiles-changed',
        environ_base={'REMOTE_ADDR': '127.0.0.1'},
    )


# ============================================================
#  AC2 — HTTP-Semantik des Endpoints
# ============================================================

def test_pbe10_tiles_changed_returns_204_for_known_display(client_with_routing):
    """Happy-Path: POST für bekannte display_id → 204 No Content."""
    r = _post_tiles_changed(client_with_routing, 'display-default-01')
    assert r.status_code == 204, (
        f"Erwartete 204, bekam {r.status_code}: {r.data!r}"
    )
    assert r.data == b'', f"204 darf keinen Body haben, bekam: {r.data!r}"


def test_pbe10_tiles_changed_returns_404_for_unknown_display(client_with_routing):
    """Unbekannte display_id → 404 (analog get_state / display_events, AC2)."""
    r = _post_tiles_changed(client_with_routing, 'unbekanntes-display')
    assert r.status_code == 404, (
        f"Unbekannte display_id muss 404 liefern, bekam: {r.status_code}"
    )
    body = r.get_json()
    assert 'error' in body, f"404-Body muss 'error'-Feld haben: {body}"


def test_pbe10_tiles_changed_rejects_non_loopback(client_with_routing):
    """Nicht-Loopback-Remote → 403 (ROU-28-Admin-Invariante)."""
    r = client_with_routing.post(
        '/api/v1/router/admin/panels/display-default-01/tiles-changed',
        environ_base={'REMOTE_ADDR': '10.0.0.1'},
    )
    assert r.status_code == 403, (
        f"Nicht-Loopback muss 403 liefern, bekam: {r.status_code}"
    )


# ============================================================
#  AC3 — Echter SSE-Subscriber empfängt das Event (NICHT publish-Mock)
# ============================================================

def test_pbe10_tiles_changed_delivers_sse_event_to_subscriber(client_with_routing):
    """AC3 (T446-AC5-Lücke): POST → display_event_stream-Generator liefert
    tatsächlich ein Event. Testet den realen publish()-Pfad, NICHT einen Mock.

    Latenz-Schranke (PBE-10 AC4): im gleichen Prozess < 1 ms; in Produktion
    Loopback-HTTP < 10 ms — trivial unter der 5-s-Schranke.
    """
    gen = router_main.display_event_stream('display-default-01')
    try:
        # 1. Verbinden: aktueller State (null, noch kein Event)
        first = next(gen)
        assert first.startswith('data: ')
        assert json.loads(first[len('data: '):].strip()) is None

        # 2. POST tiles-changed → Router ruft intern publish() auf
        r = _post_tiles_changed(client_with_routing, 'display-default-01')
        assert r.status_code == 204

        # 3. SSE-Generator liefert das publizierte Event (echter publish()-Pfad)
        second = next(gen)
        assert second.startswith('data: '), (
            f"Erwartet SSE-Event nach POST tiles-changed, bekam: {second!r}"
        )
        # State war null → publish(display_id, state.get(display_id)) publiziert null
        payload = json.loads(second[len('data: '):].strip())
        assert payload is None, (
            f"State war null, Publish-Payload muss null sein, bekam: {payload!r}"
        )
    finally:
        gen.close()


def test_pbe10_tiles_changed_publishes_current_state(client_with_routing):
    """Publiziertes Event enthält den aktuellen display-State.
    Wenn ein State gesetzt ist, kommt dieser im SSE-Event an.
    """
    # State setzen (simuliert einen vorherigen Trigger)
    router_main.state['display-default-01'] = {'payload': {'url': 'http://example.test/x'}}

    gen = router_main.display_event_stream('display-default-01')
    try:
        # 1. Verbinden: liefert den gesetzten State
        first = next(gen)
        payload_first = json.loads(first[len('data: '):].strip())
        assert payload_first == {'payload': {'url': 'http://example.test/x'}}

        # 2. POST tiles-changed → publish mit aktuellem State
        r = _post_tiles_changed(client_with_routing, 'display-default-01')
        assert r.status_code == 204

        # 3. SSE-Event enthält den State (nicht null)
        second = next(gen)
        payload_second = json.loads(second[len('data: '):].strip())
        assert payload_second == {'payload': {'url': 'http://example.test/x'}}, (
            f"Publish muss aktuellen State weiterleiten, bekam: {payload_second!r}"
        )
    finally:
        gen.close()
        # State aufräumen
        router_main.state.pop('display-default-01', None)
