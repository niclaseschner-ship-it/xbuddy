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


def test_ROU_22_stream_emits_heartbeat_when_idle(client_with_routing, monkeypatch):
    """ROU-22 Heartbeat (#116): solange keine Zustandsänderung ansteht,
    sendet der Stream periodisch einen SSE-Kommentar. Das hält
    Reverse-Proxies (nginx `proxy_read_timeout`) und Mobil-NAT-Boxen davon
    ab, den idle wirkenden Stream stillschweigend zu schließen — wäre der
    Heartbeat weg, hätte der Browser keinen sauberen Abbruch zu erkennen
    und der Standard-Reconnect (DC-7) griffe nicht.

    Wir verkürzen das Heartbeat-Intervall auf ~0 s, damit der Test nicht
    SSE_HEARTBEAT_SECONDS (15 s) abwartet. Der Effekt ist derselbe: nach
    dem Initial-Event (Zustand beim Verbinden) liefert `next(gen)` einen
    Heartbeat-Kommentar, weil keine Zustandsänderung in der Queue liegt.
    """
    monkeypatch.setattr(router_main, 'SSE_HEARTBEAT_SECONDS', 0.01)
    gen = router_main.display_event_stream('default')
    try:
        first = next(gen)                       # Initial-Zustand (null)
        assert first.startswith('data: ')
        # Keine Zustandsänderung publiziert → nächster Yield muss ein
        # SSE-Kommentar sein (Zeile beginnt mit ":"; kein "data:"-Feld,
        # damit der Client ihn nicht als Inhalts-Ereignis sieht).
        beat = next(gen)
        assert beat.startswith(':'), (
            f'Heartbeat erwartet (SSE-Kommentar, beginnt mit ":"), bekam: {beat!r}'
        )
        assert 'data:' not in beat, (
            'Heartbeat darf kein data:-Feld tragen — sonst wechselt der Client '
            f'fälschlich den Inhalt: {beat!r}'
        )
    finally:
        gen.close()


def test_ROU_22_heartbeat_intervall_default_unter_30s():
    """ROU-22 Spec: Heartbeat-Abstand ≤ 30 s. Default-Konstante muss diese
    Garantie tragen, sonst weicht der Code von der Spec ab."""
    assert router_main.SSE_HEARTBEAT_SECONDS <= 30, (
        'SSE_HEARTBEAT_SECONDS darf laut ROU-22 30 s nicht überschreiten — '
        'nginx-Idle-Timeouts und Mobilfunk-NAT-Boxen schließen sonst den Stream '
        f'(aktuell: {router_main.SSE_HEARTBEAT_SECONDS}).'
    )


# ============================================================
#  ROU-23 — Controller-PWA-Auslieferung
# ============================================================


def test_ROU_23_index_html_served_with_html_content_type(client_with_routing):
    r = client_with_routing.get('/controller/figuren-erkennung/')
    assert r.status_code == 200
    assert r.mimetype == 'text/html'
    # Die echte index.html der Controller-PWA enthält den Titel.
    assert b'Figuren-Erkennung' in r.data


def test_ROU_23_sw_js_served_with_javascript_content_type(client_with_routing):
    r = client_with_routing.get('/controller/figuren-erkennung/sw.js')
    assert r.status_code == 200
    assert r.mimetype == 'application/javascript'


def test_ROU_23_manifest_json_served_with_manifest_content_type(client_with_routing):
    r = client_with_routing.get('/controller/figuren-erkennung/manifest.json')
    assert r.status_code == 200
    # Manifests MÜSSEN application/manifest+json sein — sonst verwirft der
    # Browser sie und die PWA ist nicht installierbar.
    assert r.mimetype == 'application/manifest+json'


@pytest.mark.parametrize('icon', [
    'icon-192.png', 'icon-512.png', 'icon-maskable-512.png'])
def test_ROU_23_icons_served_with_png_content_type(client_with_routing, icon):
    r = client_with_routing.get('/controller/figuren-erkennung/' + icon)
    assert r.status_code == 200
    assert r.mimetype == 'image/png'


def test_ROU_23_figlib_js_served_with_javascript_content_type(client_with_routing):
    r = client_with_routing.get('/controller/figuren-erkennung/figlib.js')
    assert r.status_code == 200
    assert r.mimetype == 'application/javascript'


def test_ROU_23_path_traversal_returns_404(client_with_routing):
    """Versuch, aus dem Controller-Wurzelverzeichnis auszubrechen → 404.
    Flask normalisiert .. im URL-Pfad selbst, deshalb prüfen wir mehrere
    Angriffsvektoren: kodiert und über send_from_directory direkt."""
    # Klassischer Path-Traversal-Versuch via Asset-Pfad. Flask leitet ihn
    # nicht weiter; falls doch, muss der Router 404 antworten.
    r = client_with_routing.get('/controller/figuren-erkennung/..%2F..%2Frouter%2Fmain.py')
    assert r.status_code == 404
    # Direkter Aufruf der Asset-Funktion mit ../ — werkzeug safe_join +
    # unser realpath-Check müssen beide zuschlagen.
    r2 = client_with_routing.get('/controller/figuren-erkennung/../../router/main.py')
    # Flask wird '..' im URL meist normalisieren oder ablehnen — beide
    # Wege sind ok, solange nicht 200 zurückkommt.
    assert r2.status_code != 200


def test_ROU_23_nonexistent_asset_returns_404(client_with_routing):
    r = client_with_routing.get('/controller/figuren-erkennung/does-not-exist.txt')
    assert r.status_code == 404


def test_ROU_23_controller_root_without_app_slug_returns_404(client_with_routing):
    # URL-3: zwei Segmente Pflicht. /controller/ ohne App-Slug existiert nicht.
    r = client_with_routing.get('/controller/')
    assert r.status_code == 404


def test_ROU_23_unknown_app_slug_returns_404(client_with_routing):
    # Nur der konfigurierte App-Slug (basename(controller_dir)) ist gültig —
    # andere Slugs liefern 404, kein Statik-Leak.
    r = client_with_routing.get('/controller/nicht-konfigurierte-app/sw.js')
    assert r.status_code == 404
    r2 = client_with_routing.get('/controller/nicht-konfigurierte-app/')
    assert r2.status_code == 404


def test_ROU_23_controller_dir_override_via_runtime_config(tmp_path, client_with_routing):
    """runtime_config['controller_dir'] schaltet den Wurzelpfad um — der
    Code liest nicht hartcodiert, sondern aus der Config (ROU-15). Der gültige
    App-Slug im URL leitet sich aus dem Basisnamen des Verzeichnisses ab."""
    fake_root = tmp_path / 'fake-controller'
    fake_root.mkdir()
    (fake_root / 'index.html').write_text('<!doctype html><title>FAKE</title>')
    original = router_main.runtime_config.get('controller_dir', '')
    router_main.runtime_config['controller_dir'] = str(fake_root)
    try:
        r = client_with_routing.get('/controller/fake-controller/')
        assert r.status_code == 200
        assert b'FAKE' in r.data
        # Der alte App-Slug ist nach dem Override nicht mehr gültig.
        r2 = client_with_routing.get('/controller/figuren-erkennung/')
        assert r2.status_code == 404
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


# ============================================================
#  ROU-24 — App-Panel-Adapter
# ============================================================
#
# Konventions-Routing per Descriptor `{app, view, query?}`. Hardcode-frei —
# Tests fahren bewusst zwei verschiedene App-Slugs (`plan` und einen fiktiven
# `xyz`) gegeneinander, damit eine versehentliche App-Liste / Mapping-Tabelle
# im Adapter (E-ROU-8 verboten) sofort sichtbar wäre.

PANEL_ROUTING = {
    "entries": [],
    "panels": {
        "app-panel:kueche": {"display_id": "display:wohnzimmer"},
        "app-panel:flur":   {"display_id": "display:flur"},
    },
}


@pytest.fixture
def client_with_panels(tmp_path):
    routing_path = tmp_path / "routing.json"
    routing_path.write_text(json.dumps(PANEL_ROUTING))
    router_main.state = {}
    router_main._subscribers.clear()
    router_main.load_routing(str(routing_path))
    router_main.app.testing = True
    return router_main.app.test_client()


def test_ROU_24_tile_selected_sets_state_with_convention_url(client_with_panels):
    """Konvention: payload.url = /display/<app>/<view>. Erstes Beispiel mit
    App-Slug `plan` (Pi-Demo)."""
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'ts': '2026-05-25T10:00:00Z',
        'type': 'tile_selected', 'app': 'plan', 'view': 'woche',
    })
    assert r.status_code == 204
    s = router_main.state['display:wohnzimmer']
    assert s is not None
    assert s['payload'] == {'url': '/display/plan/woche'}
    assert s['descriptor'] == {'app': 'plan', 'view': 'woche'}
    assert s['source_id'] == 'app-panel:kueche'


def test_ROU_24_tile_selected_works_for_unknown_app_hardcode_free(client_with_panels):
    """Hardcode-Frei-Probe: ein dem Router unbekannter App-Slug (`xyz`)
    funktioniert genauso wie `plan`. Eine versehentliche App-Liste im
    Adapter würde diesen Test rot machen — genau der Schutz, den E-ROU-8
    fordert."""
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'app': 'xyz', 'view': 'irgendwas',
    })
    assert r.status_code == 204
    s = router_main.state['display:wohnzimmer']
    assert s['payload'] == {'url': '/display/xyz/irgendwas'}


def test_ROU_24_tile_selected_with_query_urlencodes(client_with_panels):
    """`query` wird URL-encoded an die Konventions-URL gehängt."""
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche', 'query': {'ansicht': 'klein'},
    })
    assert r.status_code == 204
    s = router_main.state['display:wohnzimmer']
    assert s['payload']['url'] == '/display/plan/woche?ansicht=klein'


def test_ROU_24_tile_selected_query_escapes_special_chars(client_with_panels):
    """URL-Encoding nach Standard — Leerzeichen, &, =, Sonderzeichen."""
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche',
        'query': {'titel': 'a b&c=d'},
    })
    assert r.status_code == 204
    s = router_main.state['display:wohnzimmer']
    assert s['payload']['url'] == '/display/plan/woche?titel=a+b%26c%3Dd'


def test_ROU_24_panel_cleared_sets_state_to_null(client_with_panels):
    """`panel_cleared` ist Session-Ende-Signal: das Display, dessen State
    diese source_id trägt, wird auf null gesetzt (ROU-11)."""
    post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche',
    })
    assert router_main.state['display:wohnzimmer'] is not None
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'panel_cleared',
    })
    assert r.status_code == 204
    assert router_main.state['display:wohnzimmer'] is None


def test_ROU_24_unknown_panel_source_warns_no_state_change(client_with_panels, caplog):
    """Panel-source_id ohne `panels`-Eintrag → 2xx, Warnung, kein State."""
    with caplog.at_level('WARNING'):
        r = post_event(client_with_panels, {
            'source_id': 'app-panel:nicht-konfiguriert',
            'type': 'tile_selected', 'app': 'plan', 'view': 'woche',
        })
    assert r.status_code == 204
    assert 'display:wohnzimmer' not in router_main.state or \
        router_main.state['display:wohnzimmer'] is None
    assert any('panels-Eintrag' in rec.message or 'App-Panel' in rec.message
               for rec in caplog.records)


def test_ROU_24_missing_app_returns_400(client_with_panels):
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'view': 'woche',
    })
    assert r.status_code == 400
    assert 'app' in r.get_json()['error']


def test_ROU_24_missing_view_returns_400(client_with_panels):
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'app': 'plan',
    })
    assert r.status_code == 400
    assert 'view' in r.get_json()['error']


def test_ROU_24_nested_query_object_returns_400(client_with_panels):
    """PANEL-7: query ist flach. Verschachteltes query verletzt das Schema."""
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche',
        'query': {'nested': {'inner': 'value'}},
    })
    assert r.status_code == 400
    assert 'query' in r.get_json()['error']


def test_ROU_24_query_with_list_returns_400(client_with_panels):
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche',
        'query': {'liste': [1, 2, 3]},
    })
    assert r.status_code == 400


def test_ROU_24_unknown_event_type_returns_400(client_with_panels):
    r = post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'foobar',
    })
    assert r.status_code == 400


def test_ROU_24_dispatch_by_event_type_not_source_id_prefix(tmp_path):
    """Hardcode-Frei-Probe auf der Dispatch-Ebene: ROU-24 wählt den App-Panel-
    Adapter über den Event-Type (`tile_selected`/`panel_cleared`) — nicht über
    eine `source_id`-Prefix-Konvention. Ein `tile_selected`-Event mit einer
    source_id OHNE `app-panel:`-Prefix muss trotzdem im App-Panel-Adapter
    landen und gegen den `panels`-Lookup geprüft werden."""
    routing = tmp_path / "routing.json"
    routing.write_text(json.dumps({
        "entries": [],
        "panels": {
            # Bewusst KEIN `app-panel:`-Prefix — der Adapter muss source_ids
            # in beliebiger Form akzeptieren, solange sie im panels-Abschnitt
            # stehen.
            "some-other-name": {"display_id": "display:wohnzimmer"},
        },
    }))
    router_main.state = {}
    router_main._subscribers.clear()
    router_main.load_routing(str(routing))
    router_main.app.testing = True
    client = router_main.app.test_client()
    r = post_event(client, {
        'source_id': 'some-other-name',
        'type': 'tile_selected', 'app': 'plan', 'view': 'woche',
    })
    assert r.status_code == 204, \
        'Dispatch muss über Event-Type laufen, nicht über source_id-Prefix'
    s = router_main.state['display:wohnzimmer']
    assert s is not None
    assert s['payload'] == {'url': '/display/plan/woche'}
    assert s['source_id'] == 'some-other-name'


def test_ROU_24_two_panels_route_to_two_displays(client_with_panels):
    """Hardcode-Frei-Probe Teil 2: zwei verschiedene Panel-Instanzen mit
    unterschiedlichen `display_id`-Zielen werden korrekt auseinandergehalten —
    der Adapter liest die Zuordnung ausschließlich aus `panels`, nicht aus
    irgendeiner Code-Tabelle."""
    post_event(client_with_panels, {
        'source_id': 'app-panel:kueche', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche',
    })
    post_event(client_with_panels, {
        'source_id': 'app-panel:flur', 'type': 'tile_selected',
        'app': 'kalender', 'view': 'heute',
    })
    assert router_main.state['display:wohnzimmer']['payload']['url'] \
        == '/display/plan/woche'
    assert router_main.state['display:flur']['payload']['url'] \
        == '/display/kalender/heute'


def test_ROU_18_panels_singular_display_id_form(tmp_path):
    """E-PANEL-5 / ROU-18: Singular `display_id`. Eine versehentlich
    wiederbelebte Plural-Form `display_ids` im `panels`-Abschnitt muss
    ignoriert werden (Migration-Schutz), damit das Doppel-Display-Setup
    nicht stumm wieder einkippt."""
    routing = tmp_path / "routing.json"
    routing.write_text(json.dumps({
        "entries": [],
        "panels": {
            "app-panel:legacy": {"display_ids": ["display:a", "display:b"]},
            "app-panel:neu":    {"display_id":  "display:c"},
        },
    }))
    router_main.state = {}
    router_main.load_routing(str(routing))
    # Plural-Form: ignoriert.
    assert 'app-panel:legacy' not in router_main.panels
    # Singular-Form: übernommen.
    assert router_main.panels['app-panel:neu']['display_id'] == 'display:c'


def test_ROU_18_panels_section_missing_is_ok(tmp_path):
    """Fehlender `panels`-Abschnitt → leeres dict, App-Panel-Adapter
    behandelt jedes `tile_selected` wie unbekannten Trigger (2xx, kein State)."""
    routing = tmp_path / "routing.json"
    routing.write_text(json.dumps({"entries": []}))
    router_main.state = {}
    router_main.load_routing(str(routing))
    assert router_main.panels == {}
    router_main.app.testing = True
    client = router_main.app.test_client()
    r = post_event(client, {
        'source_id': 'app-panel:irgendwas', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche',
    })
    assert r.status_code == 204
    assert router_main.state == {}


def test_ROU_24_stream_publishes_panel_state_change(client_with_panels):
    """Ein `tile_selected` löst publish() auf den SSE-Stream des
    zugeordneten Displays aus — PANEL-11 verlässt sich darauf."""
    gen = router_main.display_event_stream('display:wohnzimmer')
    try:
        first = next(gen)
        assert json.loads(first[len('data: '):].strip()) is None
        post_event(client_with_panels, {
            'source_id': 'app-panel:kueche', 'type': 'tile_selected',
            'app': 'plan', 'view': 'woche',
        })
        second = next(gen)
        payload = json.loads(second[len('data: '):].strip())
        assert payload['payload']['url'] == '/display/plan/woche'
    finally:
        gen.close()


# ============================================================
#  PANEL-2 — App-Panel-Auslieferung unter /controller/app-panel/<id>
# ============================================================

def test_PANEL_2_app_panel_index_served_with_html(client_with_panels):
    r = client_with_panels.get('/controller/app-panel/kueche/')
    assert r.status_code == 200
    assert r.mimetype == 'text/html'
    # Die <id> aus der URL muss im gerenderten HTML auftauchen, damit die
    # Seite ihre eigene Panel-Identität ohne weiteren Roundtrip kennt.
    assert b'data-panel-id="kueche"' in r.data


def test_PANEL_2_app_panel_index_id_per_instance(client_with_panels):
    """Zwei verschiedene Instanzen → zwei verschiedene Daten-Attribute."""
    r1 = client_with_panels.get('/controller/app-panel/kueche/')
    r2 = client_with_panels.get('/controller/app-panel/flur-tablet/')
    assert b'data-panel-id="kueche"' in r1.data
    assert b'data-panel-id="flur-tablet"' in r2.data


def test_PANEL_2_app_panel_no_slash_redirects_to_slash(client_with_panels):
    """Refs #128: ohne Trailing-Slash kommt 301 zur Slash-Variante — sonst
    brechen die relativen Asset-Pfade (./app.js → /controller/app-panel/app.js
    statt /controller/app-panel/<id>/app.js)."""
    r = client_with_panels.get('/controller/app-panel/kueche')
    assert r.status_code == 301
    assert r.headers['Location'].endswith('/controller/app-panel/kueche/')


def test_PANEL_2_app_panel_assets_served(client_with_panels):
    """app.js, style.css, manifest.json, sw.js müssen mit korrektem Content-Type
    auftauchen — PWA-Registrierung scheitert sonst (analog ROU-23 für die
    Figuren-Erkennung)."""
    r = client_with_panels.get('/controller/app-panel/kueche/app.js')
    assert r.status_code == 200
    assert r.mimetype == 'application/javascript'
    r = client_with_panels.get('/controller/app-panel/kueche/style.css')
    assert r.status_code == 200
    assert r.mimetype == 'text/css'
    r = client_with_panels.get('/controller/app-panel/kueche/manifest.json')
    assert r.status_code == 200
    assert r.mimetype == 'application/manifest+json'
    r = client_with_panels.get('/controller/app-panel/kueche/sw.js')
    assert r.status_code == 200
    assert r.mimetype == 'application/javascript'


def test_PANEL_2_app_panel_unknown_asset_returns_404(client_with_panels):
    r = client_with_panels.get('/controller/app-panel/kueche/does-not-exist.js')
    assert r.status_code == 404


def test_PANEL_2_app_panel_path_traversal_blocked(client_with_panels):
    """Defense in Depth — Versuch, aus app-panel/ auszubrechen."""
    r = client_with_panels.get('/controller/app-panel/kueche/../../router/main.py')
    assert r.status_code != 200


def test_PANEL_2_figuren_erkennung_still_works(client_with_panels):
    """Die generische `/controller/<app>/` Route darf durch die App-Panel-
    Sonderbehandlung nicht beschädigt werden."""
    r = client_with_panels.get('/controller/figuren-erkennung/')
    assert r.status_code == 200
    assert r.mimetype == 'text/html'
