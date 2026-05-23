"""Tests pro ROU-Requirement (ROU-17). pytest + Flask-Testclient.

Lauf: python3 -m pytest router/tests/ -v
"""

import json
import os
import sys

import pytest

# router/ ist ein Paket — die Repo-Wurzel (zwei Ebenen über tests/) auf den
# Importpfad legen und main als router.main importieren. So bleibt der
# Modulname eindeutig und kollidiert beim repo-weiten Lauf nicht mit den
# main-Modulen anderer Komponenten (#52).
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from router import main as router_main  # noqa: E402


# ============================================================
#  Helpers
# ============================================================

DEMO_ROUTING = {
    "entries": [
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 0},
            "display_ids": ["default"],
            "payload":    {"url": "http://example.test/klein"},
        },
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 1},
            "display_ids": ["default"],
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
    router_main._subscribers.clear()
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
    return client.post('/api/v1/events',
                       data=json.dumps(payload),
                       content_type='application/json')


# ============================================================
#  ROU-3 / ROU-4 / ROU-5 — POST /api/v1/events
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
    r = client_with_routing.post('/api/v1/events', data='not json',
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
#  ROU-12 / ROU-13 — GET /api/v1/displays/<id>/state
# ============================================================

def test_ROU_12_get_state_returns_current_payload(client_with_routing):
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 1,
    })
    r = client_with_routing.get('/api/v1/displays/default/state')
    assert r.status_code == 200
    body = r.get_json()
    assert body['payload']['url'] == 'http://example.test/groß'
    assert body['descriptor']['bucket'] == 1


def test_ROU_12_get_state_returns_null_when_inactive(client_with_routing):
    """Bekanntes Display ohne aktiven Trigger → 200 mit null."""
    r = client_with_routing.get('/api/v1/displays/default/state')
    assert r.status_code == 200
    assert r.get_json() is None


def test_ROU_12_unknown_display_returns_404(client_with_routing):
    r = client_with_routing.get('/api/v1/displays/nonexistent/state')
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
#  ROU-14 / ROU-20 — Debug + Display-Client
# ============================================================

def test_ROU_14_diag_serves_html(client_with_routing):
    r = client_with_routing.get('/api/v1/diag')
    assert r.status_code == 200
    assert b'<html' in r.data.lower()
    assert b'/api/v1/diag' in r.data


def test_ROU_20_display_serves_display_client(client_with_routing):
    """ROU-20 / E-DC-3: /display/<id> liefert den Display-Client mit
    inline gezogenem displib.js (eine same-origin-Antwort)."""
    r = client_with_routing.get('/display/default')
    assert r.status_code == 200
    assert b'createClient' in r.data                   # index.html-Bootstrap
    assert b'function parseDisplayId' in r.data         # displib.js inline gezogen
    assert b'<script src="displib.js">' not in r.data   # Tag wurde ersetzt


def test_ROU_20_display_serves_client_for_unknown_id(client_with_routing):
    """ROU-20: der Client wird auch für eine unbekannte <id> ausgeliefert —
    fehlerhafte Einrichtung wird am Gerät sichtbar (DC-8), nicht als 404."""
    r = client_with_routing.get('/display/nonexistent')
    assert r.status_code == 200
    assert b'createClient' in r.data


# ============================================================
#  ROU-22 — GET /api/v1/displays/<id>/events — Zustands-Stream
# ============================================================

def test_ROU_22_unknown_display_returns_404(client_with_routing):
    r = client_with_routing.get('/api/v1/displays/nonexistent/events')
    assert r.status_code == 404
    assert 'error' in r.get_json()


def test_ROU_22_known_display_serves_event_stream(client_with_routing, monkeypatch):
    """Bekannte id → 200 mit Content-Type text/event-stream. Der endlose
    Stream wird für den HTTP-Test durch einen endlichen Generator ersetzt."""
    monkeypatch.setattr(router_main, 'display_event_stream',
                        lambda did: iter(['data: null\n\n']))
    r = client_with_routing.get('/api/v1/displays/default/events')
    assert r.status_code == 200
    assert r.mimetype == 'text/event-stream'


def test_ROU_22_stream_sends_current_state_on_connect(client_with_routing):
    """Beim Verbinden liefert der Stream den aktuellen Zustand des Displays."""
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 1,
    })
    gen = router_main.display_event_stream('default')
    try:
        first = next(gen)
        assert first.startswith('data: ')
        payload = json.loads(first[len('data: '):].strip())
        assert payload['payload']['url'] == 'http://example.test/groß'
    finally:
        gen.close()


def test_ROU_22_stream_sends_event_on_state_change(client_with_routing):
    """Jede Zustandsänderung (ROU-11) erzeugt ein weiteres Stream-Ereignis."""
    gen = router_main.display_event_stream('default')
    try:
        first = next(gen)                       # Verbinden: aktuell null
        assert json.loads(first[len('data: '):].strip()) is None
        post_event(client_with_routing, {       # Zustandsänderung
            'source_id': 'phone:test-1', 'type': 'figure_detected',
            'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
        })
        second = next(gen)
        payload = json.loads(second[len('data: '):].strip())
        assert payload['payload']['url'] == 'http://example.test/klein'
    finally:
        gen.close()


def test_ROU_22_stream_sends_null_on_session_end(client_with_routing):
    """session_ended setzt den State auf null — der Stream meldet es."""
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    gen = router_main.display_event_stream('default')
    try:
        next(gen)                               # Verbinden: aktueller Zustand
        post_event(client_with_routing, {
            'source_id': 'phone:test-1', 'type': 'session_ended',
            'figure_id': 'rotes-a', 'reason': 'user_button',
        })
        evt = next(gen)
        assert json.loads(evt[len('data: '):].strip()) is None
    finally:
        gen.close()


def test_ROU_22_stream_unsubscribes_after_close(client_with_routing):
    """Nach dem Schließen hält der Router keinen Zustand über die Verbindung
    hinaus — die Subscription ist wieder abgeräumt."""
    gen = router_main.display_event_stream('default')
    next(gen)
    assert router_main._subscribers.get('default')
    gen.close()
    assert not router_main._subscribers.get('default')


# ============================================================
#  ROU-23 — Controller-PWA-Auslieferung
# ============================================================


def test_ROU_23_index_html_served_with_html_content_type(client_with_routing):
    r = client_with_routing.get('/controller/')
    assert r.status_code == 200
    assert r.mimetype == 'text/html'
    # Die echte index.html der Controller-PWA enthält den Titel.
    assert b'Figuren-Erkennung' in r.data


def test_ROU_23_sw_js_served_with_javascript_content_type(client_with_routing):
    r = client_with_routing.get('/controller/sw.js')
    assert r.status_code == 200
    assert r.mimetype == 'application/javascript'


def test_ROU_23_manifest_json_served_with_manifest_content_type(client_with_routing):
    r = client_with_routing.get('/controller/manifest.json')
    assert r.status_code == 200
    # Manifests MÜSSEN application/manifest+json sein — sonst verwirft der
    # Browser sie und die PWA ist nicht installierbar.
    assert r.mimetype == 'application/manifest+json'


@pytest.mark.parametrize('icon', [
    'icon-192.png', 'icon-512.png', 'icon-maskable-512.png'])
def test_ROU_23_icons_served_with_png_content_type(client_with_routing, icon):
    r = client_with_routing.get('/controller/' + icon)
    assert r.status_code == 200
    assert r.mimetype == 'image/png'


def test_ROU_23_figlib_js_served_with_javascript_content_type(client_with_routing):
    r = client_with_routing.get('/controller/figlib.js')
    assert r.status_code == 200
    assert r.mimetype == 'application/javascript'


def test_ROU_23_path_traversal_returns_404(client_with_routing):
    """Versuch, aus dem Controller-Wurzelverzeichnis auszubrechen → 404.
    Flask normalisiert .. im URL-Pfad selbst, deshalb prüfen wir mehrere
    Angriffsvektoren: kodiert und über send_from_directory direkt."""
    # Klassischer Path-Traversal-Versuch via Asset-Pfad. Flask leitet ihn
    # nicht weiter; falls doch, muss der Router 404 antworten.
    r = client_with_routing.get('/controller/..%2Frouter%2Fmain.py')
    assert r.status_code == 404
    # Direkter Aufruf der Asset-Funktion mit ../ — werkzeug safe_join +
    # unser realpath-Check müssen beide zuschlagen.
    r2 = client_with_routing.get('/controller/../router/main.py')
    # Flask wird '..' im URL meist normalisieren oder ablehnen — beide
    # Wege sind ok, solange nicht 200 zurückkommt.
    assert r2.status_code != 200


def test_ROU_23_nonexistent_asset_returns_404(client_with_routing):
    r = client_with_routing.get('/controller/does-not-exist.txt')
    assert r.status_code == 404


def test_ROU_23_controller_dir_override_via_runtime_config(tmp_path, client_with_routing):
    """runtime_config['controller_dir'] schaltet den Wurzelpfad um — der
    Code liest nicht hartcodiert, sondern aus der Config (ROU-15)."""
    fake_root = tmp_path / 'fake-controller'
    fake_root.mkdir()
    (fake_root / 'index.html').write_text('<!doctype html><title>FAKE</title>')
    original = router_main.runtime_config.get('controller_dir', '')
    router_main.runtime_config['controller_dir'] = str(fake_root)
    try:
        r = client_with_routing.get('/controller/')
        assert r.status_code == 200
        assert b'FAKE' in r.data
    finally:
        router_main.runtime_config['controller_dir'] = original


def test_ROU_15_controller_dir_env_var_resolves(monkeypatch, tmp_path):
    monkeypatch.setenv('ROUTER_CONTROLLER_DIR', '/tmp/some-controller')
    args = router_main.parse_args(['--routing', str(tmp_path / 'missing.json')])
    cfg = router_main.resolved_config(args)
    assert cfg['controller_dir'] == '/tmp/some-controller'


def test_ROU_15_controller_dir_cli_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv('ROUTER_CONTROLLER_DIR', '/tmp/from-env')
    args = router_main.parse_args([
        '--routing', str(tmp_path / 'missing.json'),
        '--controller-dir', '/tmp/from-cli',
    ])
    cfg = router_main.resolved_config(args)
    assert cfg['controller_dir'] == '/tmp/from-cli'


# ============================================================
#  ROU-18 — Routing aus Datei
# ============================================================

def test_ROU_18_missing_routing_starts_with_empty_table(client_no_routing):
    """Fehlende routing.json → leere Tabelle, keine bekannten Displays, 404."""
    r = client_no_routing.get('/api/v1/displays/default/state')
    assert r.status_code == 404


def test_ROU_18_unparseable_routing_starts_with_empty_table(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text('{not valid json')
    router_main.state = {}
    router_main.load_routing(str(bad))
    assert router_main.routing_entries == []
    assert router_main.known_displays == set()


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
#  ROU-21 — CDP-Push
# ============================================================

def test_ROU_21_push_on_state_set(client_with_routing, monkeypatch):
    """Trigger mit Match → cdp_navigate_async wird mit payload.url aufgerufen."""
    router_main.runtime_config['cdp_target'] = 'http://localhost:9222'
    calls = []
    monkeypatch.setattr(router_main, 'cdp_navigate_async', lambda url: calls.append(url))
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 1,
    })
    assert calls == ['http://example.test/groß']


def test_ROU_21_push_on_session_end_uses_idle_url(client_with_routing, monkeypatch):
    router_main.runtime_config['cdp_target']   = 'http://localhost:9222'
    router_main.runtime_config['cdp_idle_url'] = 'http://example.test/idle'
    calls = []
    monkeypatch.setattr(router_main, 'cdp_navigate_async', lambda url: calls.append(url))
    # Erst state setzen
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    calls.clear()
    # session_ended → idle-url
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'session_ended',
        'figure_id': 'rotes-a', 'reason': 'user_button',
    })
    assert calls == ['http://example.test/idle']


def test_ROU_21_no_match_no_push(client_with_routing, monkeypatch):
    """Unbekannter Trigger ändert State nicht und löst keinen Push aus."""
    router_main.runtime_config['cdp_target'] = 'http://localhost:9222'
    calls = []
    monkeypatch.setattr(router_main, 'cdp_navigate_async', lambda url: calls.append(url))
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'unbekannte-figur', 'angle': 0, 'bucket': 0,
    })
    assert calls == []


def test_ROU_21_empty_cdp_target_skips_push(monkeypatch):
    """cdp_target leer → cdp_navigate_async startet keinen Thread."""
    router_main.runtime_config['cdp_target'] = ''
    real_calls = []
    monkeypatch.setattr(router_main, 'cdp_navigate', lambda *a, **k: real_calls.append(a))
    router_main.cdp_navigate_async('http://example.test/x')
    import time
    time.sleep(0.05)
    assert real_calls == []


def test_ROU_21_navigate_failure_returns_false_no_raise():
    """Verbindungs-Fehler → False, kein Exception nach außen."""
    # Port 65530 ist mit hoher Wahrscheinlichkeit frei → connection refused
    result = router_main.cdp_navigate('http://127.0.0.1:65530', 'http://example.test', timeout=0.5)
    assert result is False


def test_ROU_21_push_does_not_break_event_endpoint(client_with_routing, monkeypatch):
    """Ein scheiternder Push darf POST /api/v1/events nicht in 5xx kippen."""
    router_main.runtime_config['cdp_target'] = 'http://127.0.0.1:65530'  # tot
    # synchroner cdp_navigate — kein Thread, damit der Test deterministisch ist
    monkeypatch.setattr(router_main, 'cdp_navigate_async',
                        lambda url: router_main.cdp_navigate(router_main.runtime_config['cdp_target'], url, timeout=0.3))
    r = post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    assert r.status_code == 204


def test_ROU_15_cdp_env_vars_resolve(monkeypatch, tmp_path):
    monkeypatch.setenv('ROUTER_CDP_TARGET',   'http://foo:9222')
    monkeypatch.setenv('ROUTER_CDP_IDLE_URL', 'http://foo/idle')
    args = router_main.parse_args(['--routing', str(tmp_path / 'missing.json')])
    cfg = router_main.resolved_config(args)
    assert cfg['cdp_target']   == 'http://foo:9222'
    assert cfg['cdp_idle_url'] == 'http://foo/idle'
