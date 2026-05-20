"""Tests pro ROU-Requirement (ROU-17). pytest + Flask-Testclient.

Lauf: python3 -m pytest router/tests/ -v
"""

import json
import os
import sys

import pytest

# Modul laden — router/main.py liegt eine Ebene über tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as router_main  # noqa: E402


# ============================================================
#  Helpers
# ============================================================

DEMO_ROUTING = {
    "entries": [
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 0},
            "screen_ids": ["default"],
            "payload":    {"url": "http://example.test/klein"},
        },
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 1},
            "screen_ids": ["default"],
            "payload":    {"url": "http://example.test/groß"},
        },
    ]
}


@pytest.fixture
def client_with_routing(tmp_path):
    """Frischer Router-State + Routing-Tabelle aus DEMO_ROUTING."""
    routing_path = tmp_path / "routing.json"
    routing_path.write_text(json.dumps(DEMO_ROUTING))
    router_main.state = {}
    router_main.load_routing(str(routing_path))
    router_main.app.testing = True
    return router_main.app.test_client()


@pytest.fixture
def client_no_routing(tmp_path):
    """Router ohne Routing-Datei — startet mit leerer Tabelle (ROU-18)."""
    router_main.state = {}
    router_main.load_routing(str(tmp_path / "no-such-file.json"))
    router_main.app.testing = True
    return router_main.app.test_client()


def post_event(client, payload):
    return client.post('/event',
                       data=json.dumps(payload),
                       content_type='application/json')


# ============================================================
#  ROU-3 / ROU-4 / ROU-5 — POST /event
# ============================================================

def test_ROU_3_event_accepts_phone_event(client_with_routing):
    r = post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'ts': '2026-05-20T10:00:00Z',
        'type': 'figure_detected', 'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    assert r.status_code == 204


def test_ROU_4_missing_required_fields_returns_4xx(client_with_routing):
    r = post_event(client_with_routing, {'type': 'figure_detected'})  # source_id fehlt
    assert 400 <= r.status_code < 500
    assert 'error' in r.get_json()


def test_ROU_4_no_5xx_on_unknown_event_type(client_with_routing):
    r = post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'wat_is_dat',
    })
    assert 400 <= r.status_code < 500


def test_ROU_5_error_body_describes_problem(client_with_routing):
    r = post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        # figure_id + bucket fehlen
    })
    assert r.status_code == 400
    body = r.get_json()
    assert 'figure_id' in body['error'] or 'bucket' in body['error']


def test_ROU_5_invalid_json_body_returns_4xx(client_with_routing):
    r = client_with_routing.post('/event', data='not json',
                                  content_type='application/json')
    assert r.status_code == 400


# ============================================================
#  ROU-6 — Phone-Adapter 1:1, keine Quantisierung
# ============================================================

def test_ROU_6_phone_event_maps_1to1_to_canonical_trigger(client_with_routing):
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    s = router_main.state.get('default')
    assert s is not None
    assert s['source_id'] == 'phone:test-1'
    assert s['descriptor'] == {'figure_id': 'rotes-a', 'bucket': 0}


def test_ROU_6_angle_field_is_not_used_for_routing(client_with_routing):
    """angle aus dem Event ändert das Routing nicht — Bucket ist autoritativ."""
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'angle_update',
        'figure_id': 'rotes-a', 'angle': 723.4, 'bucket': 1,
    })
    s = router_main.state.get('default')
    assert s['payload']['url'] == 'http://example.test/groß'
    # angle taucht weder im descriptor noch im State auf
    assert 'angle' not in s['descriptor']


# ============================================================
#  ROU-9 / ROU-11 — Lookup + Lebenszyklus
# ============================================================

def test_ROU_9_match_sets_state_with_payload(client_with_routing):
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 1,
    })
    s = router_main.state['default']
    assert s['payload'] == {'url': 'http://example.test/groß'}


def test_ROU_11_no_match_does_not_update_state(client_with_routing, caplog):
    """ROU-11: unbekannter Trigger → kein State-Update, aber Warning geloggt."""
    # Erst einen Match setzen
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    before = dict(router_main.state['default'])

    # Dann unbekanntes figure_id schicken
    with caplog.at_level('WARNING'):
        post_event(client_with_routing, {
            'source_id': 'phone:test-1', 'type': 'figure_detected',
            'figure_id': 'unbekannte-figur', 'angle': 0, 'bucket': 0,
        })

    # State unverändert
    assert router_main.state['default'] == before
    # Warning wurde geloggt
    assert any('kein Match' in rec.message for rec in caplog.records)


def test_ROU_11_session_ended_sets_state_to_null(client_with_routing):
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    assert router_main.state['default'] is not None
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'session_ended',
        'figure_id': 'rotes-a', 'reason': 'user_button',
    })
    assert router_main.state['default'] is None


# ============================================================
#  ROU-12 / ROU-13 — GET /screen/<id>/state
# ============================================================

def test_ROU_12_get_state_returns_current_payload(client_with_routing):
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 1,
    })
    r = client_with_routing.get('/screen/default/state')
    assert r.status_code == 200
    body = r.get_json()
    assert body['payload']['url'] == 'http://example.test/groß'
    assert body['descriptor']['bucket'] == 1


def test_ROU_12_get_state_returns_null_when_inactive(client_with_routing):
    """Bekannter Screen ohne aktiven Trigger → 200 mit null."""
    r = client_with_routing.get('/screen/default/state')
    assert r.status_code == 200
    assert r.get_json() is None


def test_ROU_12_unknown_screen_returns_404(client_with_routing):
    r = client_with_routing.get('/screen/nonexistent/state')
    assert r.status_code == 404
    assert 'error' in r.get_json()


def test_ROU_13_payload_is_object_not_string(client_with_routing):
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    s = router_main.state['default']
    assert isinstance(s['payload'], dict)
    assert 'url' in s['payload']


# ============================================================
#  ROU-14 / ROU-20 — Debug + Display
# ============================================================

def test_ROU_14_diag_serves_html(client_with_routing):
    r = client_with_routing.get('/diag')
    assert r.status_code == 200
    assert b'<html' in r.data.lower()
    assert b'/diag' in r.data


def test_ROU_20_display_known_screen_serves_html(client_with_routing):
    r = client_with_routing.get('/display/default')
    assert r.status_code == 200
    assert b'<iframe' in r.data
    assert b'/screen/' in r.data  # JS-Polling-Snippet drin


def test_ROU_20_display_unknown_screen_404(client_with_routing):
    r = client_with_routing.get('/display/nonexistent')
    assert r.status_code == 404


# ============================================================
#  ROU-18 — Routing aus Datei
# ============================================================

def test_ROU_18_missing_routing_starts_with_empty_table(client_no_routing):
    """Fehlende routing.json → leere Tabelle, keine bekannten Screens, 404."""
    r = client_no_routing.get('/screen/default/state')
    assert r.status_code == 404


def test_ROU_18_unparseable_routing_starts_with_empty_table(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text('{not valid json')
    router_main.state = {}
    router_main.load_routing(str(bad))
    assert router_main.routing_entries == []
    assert router_main.known_screens == set()


# ============================================================
#  ROU-15 / ROU-19 — Config-Override
# ============================================================

def test_ROU_15_cli_overrides_env_overrides_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({'listen_port': 6001, 'log_level': 'DEBUG'}))
    monkeypatch.setenv('ROUTER_PORT', '6002')

    args = router_main.parse_args([
        '--config', str(cfg),
        '--routing', str(tmp_path / "missing.json"),
        '--port', '6003',
    ])
    cfg_resolved = router_main.resolved_config(args)
    # CLI gewinnt
    assert cfg_resolved['listen_port'] == 6003
    # ohne CLI würde ENV gewinnen, ohne ENV die config
    assert cfg_resolved['log_level'] == 'DEBUG'


def test_ROU_19_config_underscore_keys_are_ignored(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({'_comment': 'doc', 'listen_port': 7000}))
    resolved = router_main.load_config(str(cfg), {'listen_port': 5000})
    assert resolved['listen_port'] == 7000
    assert '_comment' not in resolved


# ============================================================
#  CORS
# ============================================================

def test_cors_headers_on_post_event(client_with_routing):
    r = post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    assert r.headers.get('Access-Control-Allow-Origin') == '*'


def test_cors_options_preflight_returns_204(client_with_routing):
    r = client_with_routing.options('/event')
    assert r.status_code == 204
    assert 'POST' in r.headers.get('Access-Control-Allow-Methods', '')
