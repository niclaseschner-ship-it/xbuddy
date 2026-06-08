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
from router import main as router_main

# ============================================================
#  Helpers
# ============================================================

DEMO_ROUTING = {
    "entries": [
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 0},
            "display_ids": ["display-default-01"],
            "payload":    {"url": "http://example.test/klein"},
        },
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 1},
            "display_ids": ["display-default-01"],
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
    s = router_main.state.get('display-default-01')
    assert s is not None
    assert s['source_id'] == 'phone:test-1'
    assert s['descriptor'] == {'figure_id': 'rotes-a', 'bucket': 0}


def test_ROU_6_angle_field_is_not_used_for_routing(client_with_routing):
    """angle aus dem Event ändert das Routing nicht — Bucket ist autoritativ."""
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'angle_update',
        'figure_id': 'rotes-a', 'angle': 723.4, 'bucket': 1,
    })
    s = router_main.state.get('display-default-01')
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
    s = router_main.state['display-default-01']
    assert s['payload'] == {'url': 'http://example.test/groß'}


def test_ROU_11_no_match_does_not_update_state(client_with_routing, caplog):
    """ROU-11: unbekannter Trigger → kein State-Update, aber Warning geloggt."""
    # Erst einen Match setzen
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    before = dict(router_main.state['display-default-01'])

    # Dann unbekanntes figure_id schicken
    with caplog.at_level('WARNING'):
        post_event(client_with_routing, {
            'source_id': 'phone:test-1', 'type': 'figure_detected',
            'figure_id': 'unbekannte-figur', 'angle': 0, 'bucket': 0,
        })

    # State unverändert
    assert router_main.state['display-default-01'] == before
    # Warning wurde geloggt
    assert any('kein Match' in rec.message for rec in caplog.records)


def test_ROU_11_session_ended_sets_state_to_null(client_with_routing):
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 0,
    })
    assert router_main.state['display-default-01'] is not None
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'session_ended',
        'figure_id': 'rotes-a', 'reason': 'user_button',
    })
    assert router_main.state['display-default-01'] is None


# ============================================================
#  ROU-12 / ROU-13 — GET /api/v1/displays/<id>/state
# ============================================================

def test_ROU_12_get_state_returns_current_payload(client_with_routing):
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 1,
    })
    r = client_with_routing.get('/api/v1/displays/display-default-01/state')
    assert r.status_code == 200
    body = r.get_json()
    assert body['payload']['url'] == 'http://example.test/groß'
    assert body['descriptor']['bucket'] == 1


def test_ROU_12_get_state_returns_null_when_inactive(client_with_routing):
    """Bekanntes Display ohne aktiven Trigger → 200 mit null."""
    r = client_with_routing.get('/api/v1/displays/display-default-01/state')
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
    s = router_main.state['display-default-01']
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
    r = client_with_routing.get('/api/v1/displays/display-default-01/events')
    assert r.status_code == 200
    assert r.mimetype == 'text/event-stream'


def test_ROU_22_stream_sends_current_state_on_connect(client_with_routing):
    """Beim Verbinden liefert der Stream den aktuellen Zustand des Displays."""
    post_event(client_with_routing, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'angle': 0, 'bucket': 1,
    })
    gen = router_main.display_event_stream('display-default-01')
    try:
        first = next(gen)
        assert first.startswith('data: ')
        payload = json.loads(first[len('data: '):].strip())
        assert payload['payload']['url'] == 'http://example.test/groß'
    finally:
        gen.close()


def test_ROU_22_stream_sends_event_on_state_change(client_with_routing):
    """Jede Zustandsänderung (ROU-11) erzeugt ein weiteres Stream-Ereignis."""
    gen = router_main.display_event_stream('display-default-01')
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
    gen = router_main.display_event_stream('display-default-01')
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
    gen = router_main.display_event_stream('display-default-01')
    next(gen)
    assert router_main._subscribers.get('display-default-01')
    gen.close()
    assert not router_main._subscribers.get('display-default-01')


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
    gen = router_main.display_event_stream('display-default-01')
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


# ============================================================
#  ROU-26 — Geteilte Display-Assets (Icon-Bibliothek)
# ============================================================
#
# Entry-Path-Probe: der ECHTE Pfad /display/_shared/icons/<source>/<id>.png
# über den Flask-Testclient, gegen ein temporäres icon_root mit ein paar
# Test-PNGs (NICHT die echten 176 MB — runtime_config-Override wie ROU-23).

# Kleinstes gültiges PNG (1x1, transparent) — reicht für den Content-Type-
# und Auslieferungs-Beleg, ohne ein Binär-Fixture im Repo zu halten.
_TINY_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
    '0000000b49444154789c6360000200000500017a5eab3f'
    '0000000049454e44ae426082')


@pytest.fixture
def icon_root_override(tmp_path):
    """Setzt runtime_config['icon_root'] auf ein temporäres Verzeichnis mit
    1-2 Test-PNGs unter arasaac/ und stellt den alten Wert danach wieder her."""
    root = tmp_path / 'icons'
    (root / 'arasaac').mkdir(parents=True)
    (root / 'arasaac' / '2239.png').write_bytes(_TINY_PNG)
    original = router_main.runtime_config.get('icon_root', '')
    router_main.runtime_config['icon_root'] = str(root)
    try:
        yield root
    finally:
        router_main.runtime_config['icon_root'] = original


def test_ROU_26_icon_served_with_png_content_type(client_with_routing, icon_root_override):
    """ROU-26: /display/_shared/icons/arasaac/<id>.png → 200, image/png,
    Inhalt aus der icon-root."""
    r = client_with_routing.get('/display/_shared/icons/arasaac/2239.png')
    assert r.status_code == 200
    assert r.mimetype == 'image/png'
    assert r.data == _TINY_PNG


def test_ROU_26_nonexistent_icon_returns_404(client_with_routing, icon_root_override):
    r = client_with_routing.get('/display/_shared/icons/arasaac/does-not-exist.png')
    assert r.status_code == 404


def test_ROU_26_path_traversal_returns_404(client_with_routing, icon_root_override):
    """Ausbruch aus der icon-root → 404 (Defense in Depth wie ROU-23)."""
    # Kodierter Versuch — Flask leitet ihn meist nicht weiter; falls doch,
    # muss der realpath-Check zuschlagen.
    r = client_with_routing.get('/display/_shared/icons/..%2F..%2Frouter%2Fmain.py')
    assert r.status_code == 404
    r2 = client_with_routing.get('/display/_shared/icons/../../router/main.py')
    assert r2.status_code != 200


def test_ROU_26_icon_root_override_via_runtime_config(client_with_routing, tmp_path):
    """runtime_config['icon_root'] schaltet die Wurzel um — der Code liest
    nicht hartcodiert, sondern aus der Config (ROU-15/CONFIG-1)."""
    fake_root = tmp_path / 'fake-icons'
    (fake_root / 'arasaac').mkdir(parents=True)
    (fake_root / 'arasaac' / '1.png').write_bytes(_TINY_PNG)
    original = router_main.runtime_config.get('icon_root', '')
    router_main.runtime_config['icon_root'] = str(fake_root)
    try:
        r = client_with_routing.get('/display/_shared/icons/arasaac/1.png')
        assert r.status_code == 200
        assert r.data == _TINY_PNG
    finally:
        router_main.runtime_config['icon_root'] = original


def test_ROU_26_icon_root_env_var_resolves(monkeypatch, tmp_path):
    monkeypatch.setenv('ROUTER_ICON_ROOT', '/tmp/some-icons')
    args = router_main.parse_args(['--routing', str(tmp_path / 'missing.json')])
    cfg = router_main.resolved_config(args)
    assert cfg['icon_root'] == '/tmp/some-icons'


def test_ROU_26_icon_root_cli_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv('ROUTER_ICON_ROOT', '/tmp/from-env')
    args = router_main.parse_args([
        '--routing', str(tmp_path / 'missing.json'),
        '--icon-root', '/tmp/from-cli',
    ])
    cfg = router_main.resolved_config(args)
    assert cfg['icon_root'] == '/tmp/from-cli'


# ============================================================
#  ROU-30 — Geteilter Design-Token-Strang (display/_shared/design/)
# ============================================================
#
# Entry-Path-Probe: der ECHTE Pfad /display/_shared/design/tokens.css über den
# Flask-Testclient. Anders als ROU-26 (Per-Instanz-icon-root via tmp_path)
# serviert ROU-30 aus dem In-Repo-Verzeichnis display/_shared/design/ — wie
# ROU-23 /controller/_shared/. Die Datei liegt im Repo, also kein Override.

def test_ROU_30_tokens_served_with_css_content_type(client_with_routing):
    """ROU-30: /display/_shared/design/tokens.css → 200, text/css, Inhalt aus
    dem In-Repo-Strang (Beleg: ein bekannter Token ist enthalten)."""
    r = client_with_routing.get('/display/_shared/design/tokens.css')
    assert r.status_code == 200
    assert r.mimetype == 'text/css'
    assert b'--kids-bg' in r.data


def test_ROU_30_path_traversal_returns_404(client_with_routing):
    """Ausbruch aus display/_shared/design/ → 404 (Defense in Depth wie ROU-23)."""
    r = client_with_routing.get('/display/_shared/design/..%2F..%2Frouter%2Fmain.py')
    assert r.status_code == 404
    r2 = client_with_routing.get('/display/_shared/design/../../router/main.py')
    assert r2.status_code != 200


def test_ROU_30_nonexistent_asset_returns_404(client_with_routing):
    r = client_with_routing.get('/display/_shared/design/does-not-exist.css')
    assert r.status_code == 404


# ============================================================
#  ROU-31 — Stichwort-Suche /api/v1/icons/suche
# ============================================================
#
# Entry-Path-Probe: die ECHTE Route /api/v1/icons/suche über den Flask-
# Testclient, gegen ein temporäres icon_root mit pictogram_cache.json und
# selektiv vorhandenen PNGs (icon_root_override-Fixture-Stil, ICONS-7).

@pytest.fixture
def icon_root_suche(tmp_path):
    """icon-root mit pictogram_cache.json; selektiv vorhandene PNGs.

    Cache:
      'hund' → 101, 'hunde' → 101     (hund-Gruppe, PNG vorhanden)
      'katze' → 202                    (eigene Gruppe, PNG vorhanden)
      'tier303' → 303                  (kein PNG — AC4: Skip; teilt 'tier'-Substring)
      'tier' → 401, 'tiere' → 402,
      'haustier' → 403,
      'lieblingstier' → 404            (alle mit 'tier'-Substring, PNG vorhanden)

    PNGs: 101, 202, 401, 402, 403, 404 vorhanden; 303 fehlt absichtlich (AC4).
    """
    root = tmp_path / 'icons_suche'
    arasaac = root / 'arasaac'
    arasaac.mkdir(parents=True)
    for icon_id in (101, 202, 401, 402, 403, 404):
        (arasaac / f'{icon_id}.png').write_bytes(_TINY_PNG)
    # 303.png bewusst nicht anlegen
    cache = {
        'hund': 101,
        'hunde': 101,
        'katze': 202,
        'tier303': 303,
        'tier': 401,
        'tiere': 402,
        'haustier': 403,
        'lieblingstier': 404,
    }
    (root / 'pictogram_cache.json').write_text(
        json.dumps(cache), encoding='utf-8'
    )
    original = router_main.runtime_config.get('icon_root', '')
    router_main.runtime_config['icon_root'] = str(root)
    # pictogram-Cache invalidieren (neues icon_root → stale)
    router_main._pictogram_cache_root = ''
    try:
        yield root
    finally:
        router_main.runtime_config['icon_root'] = original
        router_main._pictogram_cache_root = ''


def test_ROU_31_suche_returns_matches(client_with_routing, icon_root_suche):
    """AC1: q=hund → 200, application/json, [{id, url}] mit korrektem URL-Format."""
    r = client_with_routing.get('/api/v1/icons/suche?q=hund')
    assert r.status_code == 200
    assert r.content_type.startswith('application/json')
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    item = data[0]
    assert item['id'] == 101
    assert item['url'] == '/display/_shared/icons/arasaac/101.png'


def test_ROU_31_suche_no_match_returns_empty(client_with_routing, icon_root_suche):
    """AC2: q ohne Treffer → 200, leere Liste []."""
    r = client_with_routing.get('/api/v1/icons/suche?q=xyznotexistent')
    assert r.status_code == 200
    assert r.get_json() == []


def test_ROU_31_suche_missing_q_returns_400(client_with_routing, icon_root_suche):
    """AC3: kein q-Parameter → 400."""
    r = client_with_routing.get('/api/v1/icons/suche')
    assert r.status_code == 400


def test_ROU_31_suche_filters_ids_without_local_png(client_with_routing, icon_root_suche):
    """AC4: ID 303 (tier303) hat kein PNG → darf nicht in der Antwort erscheinen."""
    r = client_with_routing.get('/api/v1/icons/suche?q=tier&max=10')
    assert r.status_code == 200
    data = r.get_json()
    ids = [item['id'] for item in data]
    assert 303 not in ids


def test_ROU_31_suche_dedupes_and_respects_max(client_with_routing, icon_root_suche):
    """Dedup: 'hund'/'hunde' → beide treffen ID 101; Dedup → ein Kandidat.
    max=1 begrenzt, max=10 liefert alle vorhandenen."""
    # Teilwort 'hund' trifft 'hund' (101) und 'hunde' (101) — Dedup → 1 Eintrag
    r = client_with_routing.get('/api/v1/icons/suche?q=hund&max=10')
    assert r.status_code == 200
    data = r.get_json()
    ids = [item['id'] for item in data]
    assert ids.count(101) == 1, 'ID 101 muss dedupliziert sein'

    # max=1 klemmt auf einen Treffer
    r2 = client_with_routing.get('/api/v1/icons/suche?q=a&max=1')
    assert r2.status_code == 200
    assert len(r2.get_json()) <= 1


def test_ROU_31_suche_default_max_3_no_param(client_with_routing, icon_root_suche):
    """AC5: GET /api/v1/icons/suche?q=tier ohne max-Query → genau 3 Treffer (Default-Cap).

    Fixture hat 4 IDs mit 'tier'-Substring und PNG (401, 402, 403, 404) plus 303
    ohne PNG (wird wegen fehlendem PNG geskippt). Ohne max → Default 3 klemmt scharf.
    Mutation Default 3→10 würde diesen Test brechen.
    """
    r = client_with_routing.get('/api/v1/icons/suche?q=tier')
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 3, f'Default-Cap 3 erwartet, bekam {len(data)}: {data}'


def test_ROU_31_suche_explicit_max_10_no_cap(client_with_routing, icon_root_suche):
    """AC5 Gegenprobe: max=10 → kein Default-Cap, alle 4 tier-IDs mit PNG erscheinen."""
    r = client_with_routing.get('/api/v1/icons/suche?q=tier&max=10')
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) >= 4, f'Erwartet >=4 Treffer mit max=10, bekam {len(data)}: {data}'


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
    r = client_no_routing.get('/api/v1/displays/display-default-01/state')
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
    # CONFIG-1-Konvention (#179): ENV-Override über `<COMPONENT>_<KEY>`,
    # hier `ROUTER_LISTEN_PORT` statt früher `ROUTER_PORT`.
    monkeypatch.setenv('ROUTER_LISTEN_PORT', '6002')

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


def test_ROU_19_unknown_config_keys_are_ignored(tmp_path):
    """Unbekannte Schlüssel in config.json (z. B. Kommentar-Felder) tauchen
    nicht im aufgelösten cfg auf. Der gemeinsame Loader (CONFIG-1, #179)
    übernimmt nur Schema-Keys; alles andere wird mit Warn-Log ignoriert."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({'_comment': 'doc', 'listen_port': 7000}))
    args = router_main.parse_args([
        '--config', str(cfg_path),
        '--routing', str(tmp_path / "missing.json"),
    ])
    resolved = router_main.resolved_config(args)
    assert resolved['listen_port'] == 7000
    assert '_comment' not in resolved


# ============================================================
#  Migrations-Schutz: alte CDP-Keys aus abgelöstem ROU-21 (Refs #102)
# ============================================================

def test_102_legacy_cdp_config_keys_ignored_without_crash(monkeypatch, tmp_path, caplog):
    """Eine alte config.json mit `cdp_target`/`cdp_idle_url` darf den Router
    nicht crashen — die Keys werden ignoriert, ein Log-Hinweis fällt an."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        'cdp_target':   'http://localhost:9222',
        'cdp_idle_url': 'http://example.test/idle',
        'listen_port':  6000,
    }))
    args = router_main.parse_args([
        '--routing', str(tmp_path / 'missing.json'),
        '--config',  str(cfg_path),
    ])
    with caplog.at_level('WARNING'):
        cfg = router_main.resolved_config(args)
    assert 'cdp_target'   not in cfg
    assert 'cdp_idle_url' not in cfg
    assert cfg['listen_port'] == 6000
    assert any('cdp_target' in r.message for r in caplog.records)


def test_102_legacy_cdp_env_vars_ignored_without_crash(monkeypatch, tmp_path, caplog):
    """Alte ENV-Variablen ROUTER_CDP_* lösen nur einen Hinweis aus."""
    monkeypatch.setenv('ROUTER_CDP_TARGET',   'http://foo:9222')
    monkeypatch.setenv('ROUTER_CDP_IDLE_URL', 'http://foo/idle')
    args = router_main.parse_args(['--routing', str(tmp_path / 'missing.json')])
    with caplog.at_level('WARNING'):
        cfg = router_main.resolved_config(args)
    assert 'cdp_target'   not in cfg
    assert 'cdp_idle_url' not in cfg
    assert any('ROUTER_CDP_TARGET' in r.message for r in caplog.records)


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


def test_PANEL_2_index_config_js_uses_absolute_path(client_with_panels):
    """Regressions-Guard #317: config.js-Referenz in index.html muss den
    ABSOLUTEN Pfad /controller/_shared/config.js tragen, NICHT den kaputten
    Relativpfad ../_shared/config.js.

    Hintergrund: Das App-Panel wird unter /controller/app-panel/<panel_id>/
    serviert (drei URL-Segmente tief unter /controller/). Der Relativpfad
    ../_shared/ würde von dort zu /controller/app-panel/_shared/ auflösen —
    404. Nur /controller/_shared/config.js ist tiefenrobust, egal wie tief
    die panel_id-URL liegt."""
    r = client_with_panels.get('/controller/app-panel/kueche/')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    # Absoluter Pfad muss vorhanden sein.
    assert '/controller/_shared/config.js' in html, (
        'index.html muss config.js über den absoluten Pfad '
        '/controller/_shared/config.js laden (Ticket #317)'
    )
    # Kaputten Relativpfad darf es nicht mehr geben.
    assert '../_shared/config.js' not in html, (
        'Kaputten Relativpfad ../_shared/config.js in index.html gefunden — '
        'führt zu 404 und schwarzer Seite (Ticket #317)'
    )
    # Alle übrigen Script-/Link-Tags nutzen ./-Relativpfade (kein ../).
    import re
    cross_tree = re.findall(
        r'(?:src|href)=["\'](\.\./[^"\']+)["\']', html)
    non_config = [p for p in cross_tree if '_shared/config.js' not in p]
    assert non_config == [], (
        'Unerwartete ../  Relativpfade in index.html: %s' % non_config
    )


# ============================================================
#  Admin-Reload (#140, EC-21) — POST /api/v1/router/admin/reload
# ============================================================
#
# EC-21 (Eltern-Chat-Spec): „Änderungen wirken sofort und ehrlich". Schreibt
# ein Skill routing.json, muss der Router den neuen Zustand übernehmen — ohne
# Reload-Aufruf bliebe der In-Memory-Routing-Cache stehen und das Versprechen
# wäre falsch. Der Endpoint ist loopback-only (nginx leitet ihn zusätzlich
# nicht weiter) und atomar (alter State bleibt bei Lade-Fehler erhalten).

RELOAD_URL = '/api/v1/router/admin/reload'

DEMO_ROUTING_INITIAL = {
    "entries": [
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 0},
            "display_ids": ["display-default-01"],
            "payload":    {"url": "http://example.test/klein"},
        },
    ]
}

DEMO_ROUTING_RELOADED = {
    "entries": [
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 0},
            "display_ids": ["display-default-01"],
            "payload":    {"url": "http://example.test/klein"},
        },
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "blaues-b", "bucket": 0},
            "display_ids": ["display-default-01", "neuer-bildschirm"],
            "payload":    {"url": "http://example.test/blau"},
        },
    ]
}


@pytest.fixture
def reload_client(tmp_path):
    """Frischer Router, der von einer schreibbaren routing.json geladen wurde.
    Tests verändern die Datei und triggern dann den Reload-Endpoint."""
    routing_file = tmp_path / "routing.json"
    routing_file.write_text(json.dumps(DEMO_ROUTING_INITIAL))
    router_main.state = {}
    router_main._subscribers.clear()
    router_main.load_routing(str(routing_file))
    router_main.app.testing = True
    client = router_main.app.test_client()
    return client, routing_file


def test_140_reload_endpoint_success_returns_200_with_details(reload_client):
    """Erfolg: Endpoint liefert HTTP 200 und JSON {reloaded: true, details: ...}.
    Die geänderte routing.json muss sichtbar geworden sein."""
    client, routing_file = reload_client
    # Datei ergänzen — der Router hat den neuen Eintrag noch nicht.
    assert 'neuer-bildschirm' not in router_main.known_displays
    routing_file.write_text(json.dumps(DEMO_ROUTING_RELOADED))

    r = client.post(RELOAD_URL)
    assert r.status_code == 200
    body = r.get_json()
    assert body['reloaded'] is True
    assert 'routing.json reloaded' in body['details']
    assert '2 Eintr' in body['details']
    # Neuer Eintrag ist in-memory angekommen — EC-21 „sofort und ehrlich".
    assert 'neuer-bildschirm' in router_main.known_displays


def test_140_reload_endpoint_is_idempotent(reload_client):
    """Idempotenz: zweimal aufrufen → gleicher Endzustand, gleiches Ergebnis.
    Der Endpoint hat keine Akkumulationssemantik."""
    client, _ = reload_client
    r1 = client.post(RELOAD_URL)
    state_after_1 = (
        list(router_main.routing_entries),
        dict(router_main.panels),
        set(router_main.known_displays),
    )
    r2 = client.post(RELOAD_URL)
    state_after_2 = (
        list(router_main.routing_entries),
        dict(router_main.panels),
        set(router_main.known_displays),
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert state_after_1 == state_after_2
    # Beide Antworten enthalten dieselbe Einträge-Zahl.
    assert r1.get_json()['details'] == r2.get_json()['details']


def test_140_reload_endpoint_atomar_bei_parse_fehler(reload_client):
    """Atomarität (E-RELOAD-1 / ROU-25): kaputtes routing.json → 500 mit
    {reloaded: false, error: ...}, ABER der alte State bleibt unverändert.
    Der Router beantwortet Events nach dem Fehler weiter wie vor dem Aufruf."""
    client, routing_file = reload_client
    # Zustand vor dem Reload-Versuch festhalten.
    entries_before = list(router_main.routing_entries)
    panels_before = dict(router_main.panels)
    known_before = set(router_main.known_displays)

    # Datei zerschießen.
    routing_file.write_text('{nicht valides json')

    r = client.post(RELOAD_URL)
    assert r.status_code == 500
    body = r.get_json()
    assert body['reloaded'] is False
    assert body.get('error')

    # Alter State unverändert.
    assert router_main.routing_entries == entries_before
    assert router_main.panels == panels_before
    assert router_main.known_displays == known_before

    # Der Router antwortet weiter wie vorher.
    s = client.get('/api/v1/displays/display-default-01/state')
    assert s.status_code == 200


def test_140_reload_endpoint_atomar_bei_fehlender_datei(reload_client):
    """Atomarität bei FileNotFoundError: routing.json wird gelöscht →
    500, alter State steht. Eine versehentlich gelöschte Datei darf den
    laufenden Router nicht in den leeren Zustand kippen."""
    client, routing_file = reload_client
    entries_before = list(router_main.routing_entries)
    known_before = set(router_main.known_displays)

    routing_file.unlink()

    r = client.post(RELOAD_URL)
    assert r.status_code == 500
    assert r.get_json()['reloaded'] is False
    assert router_main.routing_entries == entries_before
    assert router_main.known_displays == known_before


def test_140_reload_endpoint_rejects_non_loopback(reload_client):
    """Loopback-Schutz: Aufruf aus dem Netz (z. B. 10.0.0.5) → HTTP 403.
    Flask-Testclient erlaubt environ_overrides, um remote_addr zu setzen —
    das simuliert einen Aufruf, der NICHT von 127.0.0.1 kommt."""
    client, _ = reload_client
    r = client.post(RELOAD_URL, environ_overrides={'REMOTE_ADDR': '10.0.0.5'})
    assert r.status_code == 403
    body = r.get_json()
    assert body['reloaded'] is False
    assert '127.0.0.1' in body['error'] or 'loopback' in body['error'].lower()


def test_140_reload_endpoint_accepts_ipv6_loopback(reload_client):
    """IPv6-Loopback (::1) zählt auch als loopback — sonst schlägt der
    Endpoint auf Systemen fehl, die lokal über IPv6 angebunden sind."""
    client, _ = reload_client
    r = client.post(RELOAD_URL, environ_overrides={'REMOTE_ADDR': '::1'})
    assert r.status_code == 200
    assert r.get_json()['reloaded'] is True


def test_140_reload_endpoint_only_post_allowed(reload_client):
    """Der Endpoint ist eine Aktion (POST), kein Lese-Endpoint. GET → 405."""
    client, _ = reload_client
    r = client.get(RELOAD_URL)
    assert r.status_code == 405


def test_140_reload_picks_up_new_panels_section(reload_client):
    """Realistisches Szenario: ein Eltern-Chat-Skill schreibt einen neuen
    panels-Eintrag. Vor dem Reload kennt der Router den panels-source_id
    nicht; nach dem Reload schon — und ein `tile_selected` triggert den
    neuen Eintrag."""
    client, routing_file = reload_client
    # Neue routing.json mit panels-Eintrag.
    routing_file.write_text(json.dumps({
        "entries": [],
        "panels": {
            "app-panel:neu": {"display_id": "display:neu"},
        },
    }))
    r = client.post(RELOAD_URL)
    assert r.status_code == 200
    assert router_main.panels.get('app-panel:neu') == {'display_id': 'display:neu'}
    # tile_selected → neues Display kennt jetzt seinen State.
    post_event(client, {
        'source_id': 'app-panel:neu', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche',
    })
    assert router_main.state['display:neu']['payload']['url'] == '/display/plan/woche'


# ============================================================
#  DCOMP-2 — Reload-on-Read (Refs #11, #166)
# ============================================================
#
# Die Konvention DCOMP-2 (conventions/data-components.md) verlangt:
# Komponenten, die persistente Daten lesen, lesen sie pro Aufruf frisch von
# Disk. Stale Cache nach Cross-Service-Write (Eltern-Chat-Skill schreibt
# routing.json) ist genau der Schaden, den DCOMP-2 verhindert.
#
# Diese Tests beweisen den Vertrag für den Router: routing.json wird zur
# Laufzeit editiert, und der nächste Lookup sieht den neuen Stand OHNE
# Service-Restart UND OHNE Admin-Reload-Aufruf (#140).

def test_DCOMP_2_lookup_sieht_neuen_eintrag_ohne_reload(reload_client):
    """Reload-on-Read auf dem descriptor-basierten Match-Pfad (ROU-9):
    Schreibt ein Skill einen neuen Routing-Eintrag in routing.json, sieht
    der nächste `POST /api/v1/events` den Eintrag bereits — ohne dass
    irgendwer den Admin-Reload-Endpoint angetriggert hat."""
    client, routing_file = reload_client
    # Initial: nur ein Eintrag (bucket 0 → /klein). bucket 1 ist unbekannt.
    post_event(client, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'bucket': 1,
    })
    # bucket 1 ist nicht in DEMO_ROUTING_INITIAL → kein State-Update.
    assert router_main.state.get('display-default-01') is None or \
        router_main.state.get('display-default-01', {}).get('descriptor', {}).get('bucket') != 1

    # Skill schreibt routing.json um — neuer Eintrag für bucket 1.
    routing_file.write_text(json.dumps(DEMO_ROUTING_RELOADED))

    # KEIN Admin-Reload-Aufruf hier — DCOMP-2 verlangt, dass der nächste
    # Lookup den Stand frisch von Disk holt.
    post_event(client, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'blaues-b', 'bucket': 0,
    })
    # Der neue Eintrag (blaues-b → /blau für default + neuer-bildschirm)
    # ist sichtbar geworden, ohne Service-Restart, ohne Admin-Reload.
    s = router_main.state.get('display-default-01')
    assert s is not None
    assert s['payload']['url'] == 'http://example.test/blau'


def test_DCOMP_2_panels_sieht_neue_zeile_ohne_reload(reload_client):
    """Reload-on-Read auf dem panels-Pfad (ROU-24): ein neuer panels-Eintrag
    in routing.json wirkt sofort — der Eltern-Chat-Skill-Workflow für
    Panel-Onboarding muss ohne expliziten Reload-Aufruf funktionieren."""
    client, routing_file = reload_client
    # Initial hat keinen panels-Abschnitt — tile_selected würde als
    # unbekannter Trigger durchlaufen (2xx, kein State).
    routing_file.write_text(json.dumps({
        "entries": list(DEMO_ROUTING_INITIAL["entries"]),
        "panels": {
            "app-panel:hot": {"display_id": "display:wohnzimmer"},
        },
    }))
    # KEIN Reload-Aufruf — direkt das Event schicken.
    r = post_event(client, {
        'source_id': 'app-panel:hot', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche',
    })
    assert r.status_code == 204
    s = router_main.state.get('display:wohnzimmer')
    assert s is not None, \
        'DCOMP-2: neuer panels-Eintrag muss ohne Admin-Reload sichtbar sein'
    assert s['payload']['url'] == '/display/plan/woche'


def test_DCOMP_2_get_state_sieht_neues_display_ohne_reload(reload_client):
    """Reload-on-Read auf dem Read-Endpoint: ein neu via Skill angelegtes
    Display ist sofort über `GET /api/v1/displays/<id>/state` erreichbar
    (200/null statt 404). Sonst hinkt der Endpoint dem Skill nach."""
    client, routing_file = reload_client
    # Vorher: 'neu-display' ist unbekannt → 404.
    r0 = client.get('/api/v1/displays/neu-display/state')
    assert r0.status_code == 404

    # Skill schreibt routing.json um.
    routing_file.write_text(json.dumps({
        "entries": [
            {
                "source_id":  "phone:test-1",
                "descriptor": {"figure_id": "rotes-a", "bucket": 0},
                "display_ids": ["neu-display"],
                "payload":    {"url": "http://example.test/neu"},
            },
        ]
    }))
    # Kein Reload-Aufruf.
    r1 = client.get('/api/v1/displays/neu-display/state')
    assert r1.status_code == 200, \
        'DCOMP-2: neu angelegtes Display muss ohne Admin-Reload erreichbar sein'
    assert r1.get_json() is None  # bekannt, aber noch kein aktiver State


def test_DCOMP_2_kaputtes_routing_json_faellt_auf_snapshot(reload_client, caplog):
    """Resilienz-Anforderung: kippt die Datei kurzzeitig (atomares
    Replace-Race, kaputtes JSON), fällt der Lookup auf den letzten
    erfolgreich geladenen Snapshot zurück — der laufende Router rutscht
    nicht in einen leeren Zustand, nur weil ein Skill mitten im Schreiben
    war. Spiegel des atomaren Admin-Reload-Verhaltens (E-RELOAD-1 / ROU-25)."""
    client, routing_file = reload_client
    # Snapshot enthält den 'display-default-01'-Eintrag aus DEMO_ROUTING_INITIAL.
    assert 'display-default-01' in router_main.known_displays

    # Datei zerschießen.
    routing_file.write_text('{nicht-valides-json')

    # Lookup soll trotzdem aus Snapshot bedient werden — kein 500, kein
    # leeres known_displays, der Router bleibt antwortfähig.
    with caplog.at_level('DEBUG'):
        r = client.get('/api/v1/displays/display-default-01/state')
    assert r.status_code == 200, \
        'DCOMP-2 Resilienz: kaputtes routing.json darf bekannte Displays nicht ' \
        'aus dem Endpoint kippen — Snapshot-Fallback muss greifen'

    # Ein neuer Trigger gegen den Snapshot-Eintrag landet sauber.
    post_event(client, {
        'source_id': 'phone:test-1', 'type': 'figure_detected',
        'figure_id': 'rotes-a', 'bucket': 0,
    })
    s = router_main.state.get('display-default-01')
    assert s is not None
    assert s['payload']['url'] == 'http://example.test/klein'


# ============================================================
#  ROU-27 — Proxy + Last-Known-Good-Cache für Panel-Instanz-Serving
# ============================================================
#
# panel-Service (Track A) existiert hier nicht — _proxy_panel_view wird per
# monkeypatch gemockt. Integration (echter HTTP-Call) wird nach A-Deploy separat
# geprüft (Entry-Path-Probe: lower_level).

@pytest.fixture(autouse=False)
def reset_panel_lkg_cache():
    """Leert den LKG-Cache vor und nach jedem ROU-27-Test, damit Tests
    sich nicht gegenseitig beeinflussen."""
    with router_main._panel_lkg_lock:
        router_main._panel_lkg_cache.clear()
    yield
    with router_main._panel_lkg_lock:
        router_main._panel_lkg_cache.clear()


def test_ROU_27_config_json_proxied_to_panel_service(
        client_with_panels, monkeypatch, reset_panel_lkg_cache):
    """AC1: GET /controller/app-panel/<id>/config.json wird an den
    panel-Service geproxt. Der panel-Service liefert das Objekt zurück,
    der Router reicht es 1:1 weiter."""
    panel_payload = b'{"source_id": "app-panel:kueche", "display_id": "display:wohnzimmer"}'

    def fake_proxy(panel_id, sicht):
        assert sicht == 'config.json'
        return panel_payload, 'application/json'

    monkeypatch.setattr(router_main, '_proxy_panel_view', fake_proxy)
    r = client_with_panels.get('/controller/app-panel/kueche/config.json')
    assert r.status_code == 200
    assert r.mimetype == 'application/json'
    assert r.data == panel_payload


def test_ROU_27_tiles_json_proxied_to_panel_service(
        client_with_panels, monkeypatch, reset_panel_lkg_cache):
    """AC1: GET /controller/app-panel/<id>/tiles.json wird an den
    panel-Service geproxt."""
    tiles_payload = b'[{"key": "plan", "app": "plan", "view": "woche", "label": "Wochenplan"}]'

    def fake_proxy(panel_id, sicht):
        assert sicht == 'tiles.json'
        return tiles_payload, 'application/json'

    monkeypatch.setattr(router_main, '_proxy_panel_view', fake_proxy)
    r = client_with_panels.get('/controller/app-panel/kueche/tiles.json')
    assert r.status_code == 200
    assert r.mimetype == 'application/json'
    assert r.data == tiles_payload


def test_ROU_27_panel_id_passed_to_proxy(
        client_with_panels, monkeypatch, reset_panel_lkg_cache):
    """AC1: die panel_id aus der URL wird korrekt an den Proxy weitergegeben —
    /controller/app-panel/flur/config.json ruft _proxy_panel_view('flur', ...) auf."""
    seen = {}

    def fake_proxy(panel_id, sicht):
        seen['panel_id'] = panel_id
        seen['sicht'] = sicht
        return b'{}', 'application/json'

    monkeypatch.setattr(router_main, '_proxy_panel_view', fake_proxy)
    client_with_panels.get('/controller/app-panel/flur/config.json')
    assert seen['panel_id'] == 'flur'
    assert seen['sicht'] == 'config.json'


def test_ROU_27_non_proxy_asset_served_from_directory(
        client_with_panels, reset_panel_lkg_cache):
    """AC1: Assets, die NICHT config.json oder tiles.json sind, werden
    weiterhin aus dem Auslieferungs-Verzeichnis geliefert (Verzeichnis-Serving
    bleibt unverändert). Wir prüfen app.js als stellvertretenden statischen Asset."""
    r = client_with_panels.get('/controller/app-panel/kueche/app.js')
    assert r.status_code == 200
    assert r.mimetype == 'application/javascript'


def test_ROU_27_lkg_snapshot_frischt_bei_erfolg(
        client_with_panels, monkeypatch, reset_panel_lkg_cache):
    """AC2: ein erfolgreicher Proxy-Abruf schreibt den Snapshot in den
    LKG-Cache — der nächste Ausfall kann ihn dann verwenden."""
    panel_payload = b'{"lkg": true}'
    call_count = {'n': 0}

    def fake_urlopen(req, timeout=None):
        call_count['n'] += 1

        class FakeResp:
            status = 200
            def read(self): return panel_payload
            def __enter__(self): return self
            def __exit__(self, *a): pass

        return FakeResp()

    monkeypatch.setattr(router_main.urllib.request, 'urlopen', fake_urlopen)

    r = client_with_panels.get('/controller/app-panel/kueche/config.json')
    assert r.status_code == 200
    assert r.data == panel_payload
    # LKG-Cache wurde befüllt.
    with router_main._panel_lkg_lock:
        cached = router_main._panel_lkg_cache.get(('kueche', 'config.json'))
    assert cached is not None
    assert cached[0] == panel_payload


def test_ROU_27_lkg_snapshot_geliefert_bei_ausfall(
        client_with_panels, monkeypatch, reset_panel_lkg_cache):
    """AC2: wenn der panel-Service ausfällt (Exception in urlopen), liefert
    der Router den Last-Known-Good-Snapshot, sofern er einen hat."""
    lkg_data = b'{"from_lkg": true}'
    # LKG-Cache vorbelegen, als ob zuvor ein erfolgreicher Abruf stattfand.
    with router_main._panel_lkg_lock:
        router_main._panel_lkg_cache[('kueche', 'config.json')] = (
            lkg_data, 'application/json')

    def fail_urlopen(req, timeout=None):
        raise ConnectionRefusedError('panel-Service nicht erreichbar')

    monkeypatch.setattr(router_main.urllib.request, 'urlopen', fail_urlopen)

    r = client_with_panels.get('/controller/app-panel/kueche/config.json')
    assert r.status_code == 200
    assert r.data == lkg_data
    assert r.mimetype == 'application/json'


def test_ROU_27_code_default_fallback_ohne_lkg(
        client_with_panels, monkeypatch, reset_panel_lkg_cache):
    """AC2 / PREG-9: wenn der panel-Service nie erreichbar war (kein LKG-Snapshot)
    und der Abruf scheitert, fällt der Router auf den Code-Default-Fallback zurück
    — kein Crash, kein 500. config.json → {}, tiles.json → []."""
    def fail_urlopen(req, timeout=None):
        raise ConnectionRefusedError('panel-Service nicht erreichbar')

    monkeypatch.setattr(router_main.urllib.request, 'urlopen', fail_urlopen)

    r_config = client_with_panels.get('/controller/app-panel/kueche/config.json')
    assert r_config.status_code == 200
    assert r_config.data == b'{}'

    r_tiles = client_with_panels.get('/controller/app-panel/kueche/tiles.json')
    assert r_tiles.status_code == 200
    assert r_tiles.data == b'[]'


def test_ROU_27_lkg_cache_keyed_per_panel_id(
        client_with_panels, monkeypatch, reset_panel_lkg_cache):
    """AC2: der LKG-Cache ist je panel_id getrennt — kueche und flur haben
    verschiedene Snapshots, ein Ausfall bei kueche nutzt den kueche-Snapshot,
    nicht den flur-Snapshot."""
    lkg_kueche = b'{"id": "kueche"}'
    lkg_flur   = b'{"id": "flur"}'
    with router_main._panel_lkg_lock:
        router_main._panel_lkg_cache[('kueche', 'config.json')] = (
            lkg_kueche, 'application/json')
        router_main._panel_lkg_cache[('flur', 'config.json')] = (
            lkg_flur, 'application/json')

    def fail_urlopen(req, timeout=None):
        raise ConnectionRefusedError('panel-Service nicht erreichbar')

    monkeypatch.setattr(router_main.urllib.request, 'urlopen', fail_urlopen)

    r_kueche = client_with_panels.get('/controller/app-panel/kueche/config.json')
    r_flur   = client_with_panels.get('/controller/app-panel/flur/config.json')
    assert r_kueche.data == lkg_kueche
    assert r_flur.data   == lkg_flur


def test_ROU_27_panel_service_url_configurable(
        monkeypatch, tmp_path, reset_panel_lkg_cache):
    """AC1/ROU-27: die URL des panel-Service ist konfigurierbar über
    runtime_config['panel_service_url']. Default ist http://127.0.0.1:5041."""
    seen_url = {}

    def fake_urlopen(req, timeout=None):
        seen_url['url'] = req.full_url

        class FakeResp:
            status = 200
            def read(self): return b'{}'
            def __enter__(self): return self
            def __exit__(self, *a): pass

        return FakeResp()

    monkeypatch.setattr(router_main.urllib.request, 'urlopen', fake_urlopen)

    original = router_main.runtime_config.get('panel_service_url', '')
    router_main.runtime_config['panel_service_url'] = 'http://127.0.0.1:9999'
    try:
        router_main._proxy_panel_view('test-01', 'config.json')
        assert '9999' in seen_url['url'], \
            'panel_service_url in runtime_config muss die URL steuern'
        assert '/api/v1/panels/test-01/config.json' in seen_url['url']
    finally:
        router_main.runtime_config['panel_service_url'] = original


def test_ROU_27_default_panel_service_url_is_5041(monkeypatch):
    """Spec-Konstante: der Default-Port des panel-Service ist 5041 (PORT-2)."""
    original = router_main.runtime_config.get('panel_service_url', '')
    router_main.runtime_config['panel_service_url'] = ''
    try:
        base = router_main._panel_service_base()
        assert '5041' in base, \
            'Default-panel_service_url muss Port 5041 enthalten (PORT-2, PREG-11)'
    finally:
        router_main.runtime_config['panel_service_url'] = original


# ============================================================
#  ROU-28 — Panel-bezogene Schreib-/Reload-Kante loopback-/admin/-geschützt
# ============================================================
#
# ROU-28 legt fest, dass jede panel-bezogene Schreib-/Reload-Kante unter
# /admin/ und loopback-only liegt. V1 exponiert keine aktive Invalidierungs-
# Kante (OPEN-PREG-F — upstream-first Proxy, keine Push-Kante nötig). Der
# Test prüft die Invariante am Muster des bestehenden admin/reload-Endpoints:
# Loopback (127.0.0.1) → erlaubt, nicht-Loopback → 403.

def test_ROU_28_admin_reload_loopback_accepted(reload_client):
    """ROU-28 Invariante: der Admin-Reload-Endpoint (Beispiel-Kante unter /admin/)
    antwortet auf Loopback mit 200 — loopback-only-Schutz funktioniert."""
    client, _ = reload_client
    r = client.post('/api/v1/router/admin/reload',
                    environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert r.status_code == 200
    assert r.get_json()['reloaded'] is True


def test_ROU_28_admin_reload_non_loopback_rejected(reload_client):
    """ROU-28 Invariante: eine Anfrage von einer nicht-Loopback-Origin
    wird mit 403 abgelehnt — sie erreicht die /admin/-Kante nicht."""
    client, _ = reload_client
    r = client.post('/api/v1/router/admin/reload',
                    environ_overrides={'REMOTE_ADDR': '192.168.1.42'})
    assert r.status_code == 403
    body = r.get_json()
    assert body['reloaded'] is False


# ============================================================
#  ROU-29 — POST /api/v1/router/admin/panels/ — panels-Eintrag schreiben
# ============================================================
#
# Zweite, konkrete Ausprägung der ROU-28-Invariante (loopback-/`/admin/`). Der
# panel-Service ruft die Kante (PREG-16/PREG-17), um source_id → { display_id }
# in die routing.json zu schreiben. display_id wird gegen die Geräte-Registry
# (GER-14) validiert, NICHT gegen known_displays. Die Geräte-Registry wird hier
# über display_existiert gestubbt (analog panel-Tests: ohne Netz, PREG-12).

PANELS_URL = '/api/v1/router/admin/panels/'

# Routing mit einem entries-Eintrag (muss unberührt bleiben) + einem
# bestehenden panels-Eintrag (für den Umzug-/Update-Test).
PANELS_WRITE_ROUTING = {
    "entries": [
        {
            "source_id":  "phone:test-1",
            "descriptor": {"figure_id": "rotes-a", "bucket": 0},
            "display_ids": ["display-default-01"],
            "payload":    {"url": "http://example.test/klein"},
        },
    ],
    "panels": {
        "app-panel:bestand": {"display_id": "display:alt"},
    },
}


@pytest.fixture
def panels_client(tmp_path, monkeypatch):
    """Frischer Router mit schreibbarer routing.json. display_existiert wird per
    Default auf „alles bekannt" gestubbt; einzelne Tests überschreiben das."""
    routing_file = tmp_path / "routing.json"
    routing_file.write_text(json.dumps(PANELS_WRITE_ROUTING))
    router_main.state = {}
    router_main._subscribers.clear()
    router_main.load_routing(str(routing_file))
    router_main.app.testing = True
    # Default-Stub: jedes display_id existiert. So muss kein Netz laufen.
    monkeypatch.setattr(router_main, 'display_existiert', lambda did: True)
    client = router_main.app.test_client()
    return client, routing_file


def post_panel(client, body, remote='127.0.0.1'):
    return client.post(PANELS_URL,
                       data=json.dumps(body),
                       content_type='application/json',
                       environ_overrides={'REMOTE_ADDR': remote})


def test_ROU_29_write_new_panel_entry_returns_200(panels_client):
    """Happy-Path: neuer panels-Eintrag → 200 mit {written, source_id, display_id}.
    Der Eintrag steht atomar in der routing.json."""
    client, routing_file = panels_client
    r = post_panel(client, {
        'source_id': 'app-panel:kueche', 'display_id': 'display:wohnzimmer'})
    assert r.status_code == 200
    body = r.get_json()
    assert body == {
        'written': True,
        'source_id': 'app-panel:kueche',
        'display_id': 'display:wohnzimmer',
    }
    on_disk = json.loads(routing_file.read_text())
    assert on_disk['panels']['app-panel:kueche'] == {'display_id': 'display:wohnzimmer'}


def test_ROU_29_new_entry_visible_to_tile_selected_without_reload(panels_client):
    """AC6 / DCOMP-2: ein direkt folgender tile_selected-Lookup (ROU-24) sieht
    das neue display_id OHNE Service-Restart und OHNE Admin-Reload."""
    client, _ = panels_client
    r = post_panel(client, {
        'source_id': 'app-panel:neu', 'display_id': 'display:frisch'})
    assert r.status_code == 200
    # Ohne jeden Reload-Aufruf: tile_selected muss das neue Display treffen.
    r2 = post_event(client, {
        'source_id': 'app-panel:neu', 'type': 'tile_selected',
        'app': 'plan', 'view': 'woche'})
    assert r2.status_code == 204
    s = router_main.state.get('display:frisch')
    assert s is not None, 'DCOMP-2: neuer panels-Eintrag ohne Reload sichtbar'
    assert s['payload'] == {'url': '/display/plan/woche'}


def test_ROU_29_update_existing_entry_moves_panel(panels_client):
    """Update/Umzug: zweiter POST mit gleicher source_id und anderem display_id
    überschreibt die Zeile (Panel zieht auf ein anderes Display um)."""
    client, routing_file = panels_client
    # Bestehend: app-panel:bestand → display:alt. Umzug auf display:neu.
    r = post_panel(client, {
        'source_id': 'app-panel:bestand', 'display_id': 'display:neu'})
    assert r.status_code == 200
    on_disk = json.loads(routing_file.read_text())
    assert on_disk['panels']['app-panel:bestand'] == {'display_id': 'display:neu'}
    # Genau eine Zeile für die source_id — kein Duplikat.
    assert list(on_disk['panels'].keys()).count('app-panel:bestand') == 1


def test_ROU_29_entries_section_untouched(panels_client):
    """AC1: der entries-Abschnitt (descriptor-Matching, ROU-9) bleibt von der
    panels-Schreib-Kante unberührt."""
    client, routing_file = panels_client
    entries_before = json.loads(routing_file.read_text())['entries']
    post_panel(client, {
        'source_id': 'app-panel:kueche', 'display_id': 'display:wohnzimmer'})
    on_disk = json.loads(routing_file.read_text())
    assert on_disk['entries'] == entries_before


def test_ROU_29_missing_source_id_returns_400(panels_client):
    """AC4: fehlendes Pflichtfeld source_id → 400 (ROU-5-Form)."""
    client, routing_file = panels_client
    before = routing_file.read_text()
    r = post_panel(client, {'display_id': 'display:wohnzimmer'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'source_id'
    assert routing_file.read_text() == before  # unverändert


def test_ROU_29_missing_display_id_returns_400(panels_client):
    """AC4: fehlendes Pflichtfeld display_id → 400 (ROU-5-Form)."""
    client, routing_file = panels_client
    before = routing_file.read_text()
    r = post_panel(client, {'source_id': 'app-panel:kueche'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'display_id'
    assert routing_file.read_text() == before


def test_ROU_29_display_ids_plural_returns_400(panels_client):
    """AC4 / E-PANEL-5: die veraltete Plural-Form display_ids im Body ist eine
    Schema-Verletzung (400), damit sie gar nicht erst in die Datei gelangt."""
    client, routing_file = panels_client
    before = routing_file.read_text()
    r = post_panel(client, {
        'source_id': 'app-panel:kueche', 'display_ids': ['display:a', 'display:b']})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'display_ids'
    assert routing_file.read_text() == before


def test_ROU_29_invalid_json_body_returns_400(panels_client):
    """AC4: kein/ungültiger JSON-Body → 400 (ROU-5-Form)."""
    client, _ = panels_client
    r = client.post(PANELS_URL, data='not json',
                    content_type='application/json',
                    environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_ROU_29_unknown_display_returns_400(panels_client, monkeypatch):
    """AC2: display_id in der Geräte-Registry unbekannt (GER-14 → 404) → 400
    {error: 'display unbekannt'}; routing.json bleibt unverändert."""
    client, routing_file = panels_client
    before = routing_file.read_text()
    monkeypatch.setattr(router_main, 'display_existiert', lambda did: False)
    r = post_panel(client, {
        'source_id': 'app-panel:kueche', 'display_id': 'display:gibtsnicht'})
    assert r.status_code == 400
    assert r.get_json()['error'] == 'display unbekannt'
    assert routing_file.read_text() == before


def test_ROU_29_geraete_registry_unreachable_returns_503(panels_client, monkeypatch):
    """AC2: Geräte-Registry nicht erreichbar → 503, routing.json unverändert
    (kein stilles Durchwinken, symmetrisch zu PREG-7)."""
    client, routing_file = panels_client
    before = routing_file.read_text()

    def boom(did):
        raise router_main._GeraeteUnreachable('connection refused')

    monkeypatch.setattr(router_main, 'display_existiert', boom)
    r = post_panel(client, {
        'source_id': 'app-panel:kueche', 'display_id': 'display:wohnzimmer'})
    assert r.status_code == 503
    assert 'error' in r.get_json()
    assert routing_file.read_text() == before


def test_ROU_29_validates_against_geraete_registry_not_known_displays(
        panels_client, monkeypatch):
    """AC2: die Validierung läuft gegen die Geräte-Registry (display_existiert),
    NICHT gegen known_displays. Ein Display, das die Geräte-Registry kennt, aber
    das NOCH in keinem entries-Eintrag der routing.json steht (also nicht in
    known_displays), muss durchgehen — sonst der Kopplungs-Fehler aus PREG-7."""
    client, routing_file = panels_client
    # Sicherstellen: das Ziel-Display ist NICHT in known_displays.
    assert 'display:nur-in-geraete' not in router_main.known_displays
    seen = {}

    def stub(did):
        seen['did'] = did
        return True  # Geräte-Registry kennt es

    monkeypatch.setattr(router_main, 'display_existiert', stub)
    r = post_panel(client, {
        'source_id': 'app-panel:k', 'display_id': 'display:nur-in-geraete'})
    assert r.status_code == 200
    assert seen['did'] == 'display:nur-in-geraete'  # genau dieses Display geprüft
    on_disk = json.loads(routing_file.read_text())
    assert on_disk['panels']['app-panel:k'] == {'display_id': 'display:nur-in-geraete'}


def test_ROU_29_disk_write_error_returns_503(panels_client, monkeypatch):
    """AC5: IO-/Replace-Fehler beim atomaren Schreiben → 503, routing.json
    unverändert."""
    client, routing_file = panels_client
    before = routing_file.read_text()

    def boom(source_id, display_id):
        raise router_main._PanelsWriteError('os.replace failed')

    monkeypatch.setattr(router_main, '_write_panels_entry', boom)
    r = post_panel(client, {
        'source_id': 'app-panel:kueche', 'display_id': 'display:wohnzimmer'})
    assert r.status_code == 503
    assert 'error' in r.get_json()
    assert routing_file.read_text() == before


def test_ROU_29_non_loopback_origin_returns_403(panels_client):
    """AC3 / ROU-28: Aufruf von nicht-Loopback-Origin → 403 (wie Admin-Reload);
    routing.json unverändert."""
    client, routing_file = panels_client
    before = routing_file.read_text()
    r = post_panel(client, {
        'source_id': 'app-panel:kueche', 'display_id': 'display:wohnzimmer'},
        remote='10.0.0.5')
    assert r.status_code == 403
    assert r.get_json()['written'] is False
    assert routing_file.read_text() == before


def test_ROU_29_ipv6_loopback_accepted(panels_client):
    """AC3: IPv6-Loopback (::1) ist ebenfalls erlaubt (gleicher Guard wie
    Admin-Reload)."""
    client, _ = panels_client
    r = post_panel(client, {
        'source_id': 'app-panel:kueche', 'display_id': 'display:wohnzimmer'},
        remote='::1')
    assert r.status_code == 200
    assert r.get_json()['written'] is True


def test_ROU_29_only_post_allowed(panels_client):
    """Methoden-Schutz: GET auf die Schreib-Kante ist nicht erlaubt (405)."""
    client, _ = panels_client
    r = client.get(PANELS_URL, environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert r.status_code == 405


def test_ROU_29_parallel_posts_no_lost_update(panels_client):
    """AC5: zwei verschiedene source_ids parallel geschrieben → beide landen
    (Schreib-Lock serialisiert, kein lost update; symmetrisch zu PREG-15)."""
    import threading as _threading
    client, routing_file = panels_client

    sources = ['app-panel:p%02d' % i for i in range(12)]
    barrier = _threading.Barrier(len(sources))
    results = {}

    def worker(src):
        barrier.wait()  # alle gleichzeitig loslassen
        r = post_panel(client, {'source_id': src, 'display_id': 'display:x'})
        results[src] = r.status_code

    threads = [_threading.Thread(target=worker, args=(s,)) for s in sources]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(code == 200 for code in results.values())
    on_disk = json.loads(routing_file.read_text())
    for src in sources:
        assert on_disk['panels'][src] == {'display_id': 'display:x'}
    # entries-Eintrag hat keinen der parallelen Writes verloren.
    assert len(on_disk['entries']) == 1


# ============================================================
#  T459 / PBE-1 / PBE-2 — Router-Proxy für /bearbeiten Editor-Seite
# ============================================================
#
# AC1: GET /controller/app-panel/<id>/bearbeiten → 200 HTML vom panel-Service
# AC2: GET /controller/app-panel/<id>/bearbeiten.js + .css → 200
# AC3: Unbekannte panel_id → 404 vom panel-Service wird durchgereicht
# AC4: Bestehende Proxy-Routen für tiles.json + config.json unverändert
# AC5: Happy-Path je .html/.js/.css + 404. Self-Gate Ruff + lint-imports.


def test_T459_bearbeiten_html_proxied_200(client_with_panels, monkeypatch):
    """AC1: GET /controller/app-panel/<id>/bearbeiten liefert 200 HTML
    vom panel-Service durch — text/html Content-Type."""
    html_body = b'<html><body>Editor</body></html>'

    def fake_proxy(panel_id, sicht):
        assert panel_id == 'kueche'
        assert sicht == 'bearbeiten'
        return html_body, 'text/html; charset=utf-8', 200

    monkeypatch.setattr(router_main, '_proxy_panel_bearbeiten', fake_proxy)
    r = client_with_panels.get('/controller/app-panel/kueche/bearbeiten')
    assert r.status_code == 200
    assert r.mimetype == 'text/html'
    assert r.data == html_body


def test_T459_bearbeiten_js_proxied_200(client_with_panels, monkeypatch):
    """AC2: GET /controller/app-panel/<id>/bearbeiten.js liefert 200
    application/javascript."""
    js_body = b'console.log("bearbeiten");'

    def fake_proxy(panel_id, sicht):
        assert sicht == 'bearbeiten.js'
        return js_body, 'application/javascript; charset=utf-8', 200

    monkeypatch.setattr(router_main, '_proxy_panel_bearbeiten', fake_proxy)
    r = client_with_panels.get('/controller/app-panel/kueche/bearbeiten.js')
    assert r.status_code == 200
    assert r.mimetype == 'application/javascript'
    assert r.data == js_body


def test_T459_bearbeiten_css_proxied_200(client_with_panels, monkeypatch):
    """AC2: GET /controller/app-panel/<id>/bearbeiten.css liefert 200
    text/css."""
    css_body = b'body { margin: 0; }'

    def fake_proxy(panel_id, sicht):
        assert sicht == 'bearbeiten.css'
        return css_body, 'text/css; charset=utf-8', 200

    monkeypatch.setattr(router_main, '_proxy_panel_bearbeiten', fake_proxy)
    r = client_with_panels.get('/controller/app-panel/kueche/bearbeiten.css')
    assert r.status_code == 200
    assert r.mimetype == 'text/css'
    assert r.data == css_body


def test_T459_bearbeiten_unknown_panel_id_returns_404(client_with_panels, monkeypatch):
    """AC3: Unbekannte panel_id → 404 vom panel-Service wird durchgereicht.
    Kein LKG-Fallback, kein Code-Default."""
    def fake_proxy(panel_id, sicht):
        assert panel_id == 'unbekannt-xyz'
        return b'{"error": "unbekannte panel_id"}', 'application/json', 404

    monkeypatch.setattr(router_main, '_proxy_panel_bearbeiten', fake_proxy)
    r = client_with_panels.get('/controller/app-panel/unbekannt-xyz/bearbeiten')
    assert r.status_code == 404


def test_T459_bearbeiten_panel_id_forwarded_correctly(client_with_panels, monkeypatch):
    """AC1: die panel_id aus der URL wird korrekt an den Proxy weitergegeben."""
    seen = {}

    def fake_proxy(panel_id, sicht):
        seen['panel_id'] = panel_id
        seen['sicht'] = sicht
        return b'<html></html>', 'text/html; charset=utf-8', 200

    monkeypatch.setattr(router_main, '_proxy_panel_bearbeiten', fake_proxy)
    client_with_panels.get('/controller/app-panel/flur/bearbeiten')
    assert seen['panel_id'] == 'flur'
    assert seen['sicht'] == 'bearbeiten'


def test_T459_existing_config_json_proxy_still_works(client_with_panels, monkeypatch,
                                                     reset_panel_lkg_cache):
    """AC4: bestehende Proxy-Route für config.json unverändert — T459 bricht
    die ROU-27-Logik nicht."""
    payload = b'{"source_id": "app-panel:kueche"}'

    def fake_proxy(panel_id, sicht):
        return payload, 'application/json'

    monkeypatch.setattr(router_main, '_proxy_panel_view', fake_proxy)
    r = client_with_panels.get('/controller/app-panel/kueche/config.json')
    assert r.status_code == 200
    assert r.data == payload


def test_T459_existing_tiles_json_proxy_still_works(client_with_panels, monkeypatch,
                                                    reset_panel_lkg_cache):
    """AC4: bestehende Proxy-Route für tiles.json unverändert — T459 bricht
    die ROU-27-Logik nicht."""
    payload = b'[{"key": "plan"}]'

    def fake_proxy(panel_id, sicht):
        return payload, 'application/json'

    monkeypatch.setattr(router_main, '_proxy_panel_view', fake_proxy)
    r = client_with_panels.get('/controller/app-panel/kueche/tiles.json')
    assert r.status_code == 200
    assert r.data == payload
