"""Tests pro PANEL-Requirement (PANEL-9). pytest, analog router/tests/.

Statische Prüfungen auf index.html / app.js (Pattern-Grep, JSON-Parse) +
Node-Subprozess für die reinen Logik-Funktionen aus app.js (UMD-Export
panelLib). Damit ist die ganze Suite mit `python3 -m pytest` lauffähig —
kein eigener JS-Test-Runner nötig.

Lauf: python3 -m pytest controller/app-panel/tests/ -v
"""

import json
import os
import re
import subprocess
import sys
import textwrap

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH    = os.path.join(ROOT, 'index.html')
APPJS_PATH   = os.path.join(ROOT, 'app.js')
CSS_PATH     = os.path.join(ROOT, 'style.css')
MANIFEST_PATH = os.path.join(ROOT, 'manifest.json')
SW_PATH      = os.path.join(ROOT, 'sw.js')
TILES_EXAMPLE = os.path.join(ROOT, 'tiles.example.json')
CONFIG_EXAMPLE = os.path.join(ROOT, 'config.example.json')


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def run_node(snippet):
    """Lädt panelLib aus app.js, führt JS-Snippet aus, gibt parsedes JSON
    zurück (das Snippet muss am Ende `console.log(JSON.stringify(...))`)."""
    src = textwrap.dedent('''
        const panelLib = require(%r);
        %s
    ''' % (APPJS_PATH, snippet))
    res = subprocess.run(
        ['node', '-e', src],
        capture_output=True, text=True, timeout=10)
    if res.returncode != 0:
        raise AssertionError(
            'node-Subprozess fehlgeschlagen:\n' + res.stderr + '\n--- src ---\n' + src)
    out = res.stdout.strip()
    if not out:
        return None
    return json.loads(out)


# ============================================================
#  PANEL-1 — Panel & Routing-Trennung
# ============================================================

def test_PANEL_1_tap_sends_event_no_local_routing():
    """Ein Tap auf eine Kachel sendet ein Event — das Panel entscheidet
    NICHTS über das Routing (keine Display-Wechsel-Logik in der Seite).
    Geprüft: makeTileSelected liefert ein Event mit Pflichtfeldern, aber
    keine URL und keine Display-Auswahl. (Das Routing macht der Router-
    Adapter ROU-24, dafür gibt es eigene Router-Tests.)"""
    out = run_node('''
        const ev = panelLib.makeTileSelected(
            'app-panel:test',
            { key: 'k1', app: 'plan', view: 'woche', label: 'L', icon: 'i', sichtbar: true });
        console.log(JSON.stringify(ev));
    ''')
    assert out['source_id'] == 'app-panel:test'
    assert out['type'] == 'tile_selected'
    assert out['app'] == 'plan'
    assert out['view'] == 'woche'
    assert 'url' not in out
    assert 'display_id' not in out


def test_PANEL_1_app_js_does_not_route_to_displays_directly():
    """Negativ-Probe: das Frontend macht keine direkten URL-Wechsel auf
    /display/<app>/<view>. Routing-Verantwortung liegt allein beim Router."""
    js = read(APPJS_PATH)
    # location.href-Manipulation auf /display/ wäre Routing aus der Seite.
    assert not re.search(r"location\.href\s*=.*['\"]/display/", js), \
        'Panel darf nicht selbst auf /display/<app>/<view> navigieren — das ist Router-Sache (PANEL-1)'
    assert not re.search(r"window\.open\(.*['\"]/display/", js), \
        'Panel darf das Display nicht selbst öffnen'


# ============================================================
#  PANEL-2 — URL-Verortung + Identitäts-Rendering
# ============================================================
#
# Die HTTP-Auslieferung testet der Router (test_router.py::test_PANEL_2_*).
# Hier prüfen wir nur den Marker, an dem das Frontend die Identität liest.

def test_PANEL_2_html_reads_panel_id_from_data_attribute():
    html = read(HTML_PATH)
    # body trägt den Slot, der vom Router beim Ausliefern gefüllt wird.
    assert re.search(r'<body[^>]*>', html), 'body-Tag fehlt'
    js = read(APPJS_PATH)
    assert re.search(r'document\.body[\s\S]*?dataset[\s\S]*?panelId', js), \
        'app.js muss die Panel-Identität aus document.body.dataset.panelId lesen'


# ============================================================
#  PANEL-3 — tiles.json: Listen-Reihenfolge ist Anzeige-Reihenfolge,
#  `key` eindeutig
# ============================================================

def test_PANEL_3_tiles_render_in_list_order():
    """visibleTiles gibt sichtbare Kacheln in Original-Reihenfolge zurück."""
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'p', view: 'v', label: 'A', icon: 'i', sichtbar: true },
            { key: 'b', app: 'p', view: 'v', label: 'B', icon: 'i', sichtbar: true },
            { key: 'c', app: 'p', view: 'v', label: 'C', icon: 'i', sichtbar: true },
        ];
        console.log(JSON.stringify(panelLib.visibleTiles(tiles).map(t => t.key)));
    ''')
    assert out == ['a', 'b', 'c']


def test_PANEL_3_keys_in_example_are_unique():
    data = json.loads(read(TILES_EXAMPLE))
    keys = [t['key'] for t in data['tiles']]
    assert len(keys) == len(set(keys)), 'tiles.example.json: key muss eindeutig sein'


def test_PANEL_3_tiles_example_format_valid():
    data = json.loads(read(TILES_EXAMPLE))
    for t in data['tiles']:
        for k in ('key', 'app', 'view', 'label', 'icon'):
            assert k in t and isinstance(t[k], str) and t[k], \
                'Pflichtfeld %s fehlt oder ist kein String: %r' % (k, t)
        assert isinstance(t['sichtbar'], bool)


# ============================================================
#  PANEL-4 — sichtbar:false wird nicht gerendert (kein Event möglich)
# ============================================================

def test_PANEL_4_invisible_tiles_filtered():
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'p', view: 'v', label: 'A', icon: 'i', sichtbar: true },
            { key: 'b', app: 'p', view: 'v', label: 'B', icon: 'i', sichtbar: false },
            { key: 'c', app: 'p', view: 'v', label: 'C', icon: 'i', sichtbar: true },
        ];
        console.log(JSON.stringify(panelLib.visibleTiles(tiles).map(t => t.key)));
    ''')
    assert out == ['a', 'c'], 'sichtbar:false-Kachel darf nicht durchgereicht werden'


# ============================================================
#  PANEL-5 — Transport: POST mit Retry (200/1000/5000), dann Drop
# ============================================================

def test_PANEL_5_retry_schema_drops_after_3_attempts():
    """Drei Netzfehler in Folge → Retry mit Backoffs 200/1000/5000 ms,
    danach Drop. Wir mocken fetch+setTimeout, sammeln die Versuche und
    prüfen Anzahl + Delays."""
    out = run_node('''
        const calls = [];
        const delays = [];
        const fakeFetch = () => {
            calls.push(1);
            return Promise.reject(new Error('boom'));
        };
        const fakeTimeout = (fn, ms) => { delays.push(ms); fn(); };
        let dropReason = null;
        panelLib.postWithRetry({
            fetchImpl: fakeFetch,
            setTimeoutImpl: fakeTimeout,
            url: 'http://x',
            body: { hello: 1 },
            onDrop: (r) => { dropReason = r; },
        });
        // Promises auflösen
        setImmediate(() => {
            console.log(JSON.stringify({ calls: calls.length, delays, dropReason }));
        });
    ''')
    # Erster Versuch + 3 Retries = 4 calls; Delays sind genau die Backoffs.
    assert out['calls'] == 4, 'Erst-Versuch + 3 Retries = 4 fetch-Aufrufe (bekommen: %s)' % out['calls']
    assert out['delays'] == [200, 1000, 5000], \
        'Retry-Delays müssen 200/1000/5000 sein (bekommen: %s)' % out['delays']
    assert out['dropReason'] is not None, 'onDrop muss nach Erschöpfung gerufen werden'


def test_PANEL_5_backoffs_constant_exported():
    out = run_node('console.log(JSON.stringify(panelLib.BACKOFFS));')
    assert out == [200, 1000, 5000]


def test_PANEL_5_success_no_retry():
    """Erfolgreicher POST → kein Retry."""
    out = run_node('''
        let calls = 0;
        const fakeFetch = () => { calls++; return Promise.resolve({ ok: true }); };
        let ok = false;
        panelLib.postWithRetry({
            fetchImpl: fakeFetch,
            setTimeoutImpl: (fn, ms) => fn(),
            url: 'http://x',
            body: {},
            onSuccess: () => { ok = true; },
        });
        setImmediate(() => console.log(JSON.stringify({ calls, ok })));
    ''')
    assert out == {'calls': 1, 'ok': True}


# ============================================================
#  PANEL-6 — Event-Schema + Aus-Kachel
# ============================================================

def test_PANEL_6_tile_selected_has_required_fields():
    out = run_node('''
        const ev = panelLib.makeTileSelected(
            'app-panel:k',
            { key: 'k', app: 'plan', view: 'woche', label: 'L', icon: 'i', sichtbar: true });
        console.log(JSON.stringify(ev));
    ''')
    assert out['source_id'] == 'app-panel:k'
    assert isinstance(out['ts'], str) and len(out['ts']) > 0
    assert out['type'] == 'tile_selected'
    assert out['app'] == 'plan'
    assert out['view'] == 'woche'
    assert 'query' not in out, 'query darf nicht gesetzt sein, wenn die Kachel keins hat'


def test_PANEL_6_tile_selected_query_only_when_set():
    out = run_node('''
        const ev = panelLib.makeTileSelected(
            'app-panel:k',
            { key: 'k', app: 'plan', view: 'woche', label: 'L', icon: 'i', sichtbar: true,
              query: { ansicht: 'klein' } });
        console.log(JSON.stringify(ev));
    ''')
    assert out['query'] == {'ansicht': 'klein'}


def test_PANEL_6_panel_cleared_has_no_descriptor():
    out = run_node('''
        const ev = panelLib.makePanelCleared('app-panel:k');
        console.log(JSON.stringify(ev));
    ''')
    assert out['source_id'] == 'app-panel:k'
    assert out['type'] == 'panel_cleared'
    assert isinstance(out['ts'], str)
    for k in ('app', 'view', 'query'):
        assert k not in out, '%s darf in panel_cleared nicht auftauchen' % k


def test_PANEL_6_aus_kachel_always_last_in_app_js():
    """Render-Reihenfolge: nach sichtbaren Kacheln aus tiles.json kommt
    die eingebaute Aus-Kachel — auch wenn tiles.json leer ist."""
    js = read(APPJS_PATH)
    # Reihenfolge im Code: zuerst Schleife über visible, dann makeAusKachel.
    assert re.search(
        r'for\s*\([\s\S]{0,200}?visible[\s\S]{0,400}?makeAusKachel',
        js), 'Render-Reihenfolge: visible-Kacheln vor der Aus-Kachel'


def test_PANEL_6_aus_kachel_is_not_from_tiles_json():
    """Negativ-Probe: die Aus-Kachel taucht weder als Eintrag in der
    Beispiel-tiles.json auf, noch lässt sie sich per `sichtbar` steuern."""
    data = json.loads(read(TILES_EXAMPLE))
    keys = [t.get('key') for t in data.get('tiles', [])]
    assert '__aus__' not in keys, 'Aus-Kachel darf kein tiles.json-Eintrag sein'
    js = read(APPJS_PATH)
    # makeAusKachel wird unkonditional aufgerufen — kein Branch über sichtbar.
    assert re.search(r"makeAusKachel\(onClear\)", js), \
        'Aus-Kachel muss unkonditional gerendert werden'


def test_PANEL_6_aus_kachel_sends_panel_cleared():
    """Tap auf die Aus-Kachel → panel_cleared ohne Descriptor."""
    js = read(APPJS_PATH)
    # onClear ruft makePanelCleared
    assert re.search(
        r"onClear\(\)\s*\{\s*sendEvent\([^,]+,\s*panelLib\.makePanelCleared",
        js), 'onClear muss panel_cleared senden'


# ============================================================
#  PANEL-7 — Descriptor flach (Strings/Zahlen)
# ============================================================

def test_PANEL_7_nested_query_rejected_as_config_error():
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L', icon: 'i',
            sichtbar: true,
            query: { nested: { inner: 'x' } },
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is not None and 'query' in out['err'].lower()


def test_PANEL_7_list_query_rejected():
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L', icon: 'i',
            sichtbar: true,
            query: { list: [1, 2] },
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is not None


def test_PANEL_7_flat_string_or_number_query_ok():
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L', icon: 'i',
            sichtbar: true,
            query: { s: 'abc', n: 42 },
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is None


# ============================================================
#  PANEL-8 — config.json: stiller Fallback bei Fehlern,
#                         sichtbarer Fehler bei Konsistenz-Verletzung
# ============================================================

def test_PANEL_8_html_loads_config_via_fetch():
    js = read(APPJS_PATH)
    assert re.search(r"fetch\(\s*['\"]\.\/config\.json['\"]", js), \
        'app.js muss ./config.json per fetch laden'


def test_PANEL_8_missing_config_falls_back_silently_to_defaults():
    """Fehlende/kaputte config.json → console.warn + Defaults. Keine Crash."""
    js = read(APPJS_PATH)
    # In loadConfig: catch-Block mit console.warn und Rückgabe der Defaults.
    assert re.search(
        r"catch\s*\([^)]*\)\s*\{[\s\S]*?console\.warn[\s\S]*?return\s+defaults",
        js), 'Fehlende config.json darf die Seite nicht crashen — stumm auf Defaults'


def test_PANEL_8_config_overrides_defaults():
    """Object.assign(defaults, fileCfg) — fileCfg überschreibt Defaults."""
    out = run_node('''
        const defaults = panelLib.configDefaults();
        const merged = Object.assign({}, defaults, { router_url: 'https://x' });
        console.log(JSON.stringify(merged));
    ''')
    assert out['router_url'] == 'https://x'
    # Werte, die in fileCfg fehlen, kommen aus den Defaults.
    assert out['source_id'] == 'app-panel:demo'


def test_PANEL_8_source_id_consistency_error_visible():
    """Diskrepanz source_id ↔ data-panel-id → sichtbare Fehler-Meldung."""
    out = run_node('''
        const err = panelLib.checkConfigConsistency(
            { source_id: 'app-panel:wohnzimmer', display_id: 'display:x' },
            'kueche');
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is not None
    assert 'source_id' in out['err']


def test_PANEL_8_display_id_required_in_config_consistency():
    out = run_node('''
        const err = panelLib.checkConfigConsistency(
            { source_id: 'app-panel:k' },
            'k');
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is not None
    assert 'display_id' in out['err']


def test_PANEL_8_matching_config_no_error():
    out = run_node('''
        const err = panelLib.checkConfigConsistency(
            { source_id: 'app-panel:k', display_id: 'display:x' },
            'k');
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is None


def test_PANEL_8_config_example_format_valid():
    data = json.loads(read(CONFIG_EXAMPLE))
    # Pflichtfelder (siehe PANEL-8 Body) — plus Kommentar-Keys.
    for k in ('source_id', 'display_id', 'router_url'):
        assert k in data, 'Pflicht-Feld %s fehlt in config.example.json' % k
    assert data['source_id'].startswith('app-panel:')
    assert data['display_id'].startswith('display:')


# ============================================================
#  PANEL-9 — Meta: alle Tests existieren
# ============================================================

def test_PANEL_9_test_file_covers_all_panel_ids():
    """Selbst-Probe: für jede PANEL-ID aus dem Mindest-Abdeckungs-Block
    der Spec gibt es mindestens einen Test in dieser Datei."""
    here = read(os.path.abspath(__file__))
    for pid in ['PANEL_1', 'PANEL_2', 'PANEL_3', 'PANEL_4', 'PANEL_5',
                'PANEL_6', 'PANEL_7', 'PANEL_8', 'PANEL_10', 'PANEL_11']:
        assert re.search(r'def test_%s_' % pid, here), \
            'kein Test gefunden für %s' % pid


# ============================================================
#  PANEL-10 — Manifest fullscreen, Wake Lock, requestFullscreen
# ============================================================

def test_PANEL_10_manifest_declares_fullscreen():
    m = json.loads(read(MANIFEST_PATH))
    assert m['display'] == 'fullscreen'


def test_PANEL_10_html_binds_manifest_and_registers_sw():
    html = read(HTML_PATH)
    assert re.search(
        r'<link[^>]+rel=["\']manifest["\'][^>]+href=["\']\.\/manifest\.json["\']',
        html)
    js = read(APPJS_PATH)
    assert re.search(r"navigator\.serviceWorker\.register\(['\"]\.\/sw\.js['\"]\)",
                     js), 'SW-Registrierung fehlt'


def test_PANEL_10_wake_lock_requested_on_load_and_visibility():
    js = read(APPJS_PATH)
    assert re.search(r"navigator\.wakeLock\.request\(\s*['\"]screen['\"]\s*\)", js), \
        'Wake Lock wird nicht angefordert'
    # Erneut bei visibilitychange→visible.
    assert re.search(r"visibilitychange", js)
    assert re.search(
        r"visibilityState\s*===\s*['\"]visible['\"][\s\S]{0,80}?request\s*\(",
        js), 'Wake Lock muss nach visibilitychange erneut geholt werden'


def test_PANEL_10_request_fullscreen_on_first_gesture():
    js = read(APPJS_PATH)
    assert re.search(r"requestFullscreen", js)
    assert re.search(
        r"addEventListener\(\s*['\"]touchend['\"]\s*,\s*tryFullscreen",
        js), 'Fullscreen-Trigger muss an touchend hängen (touchstart gewährt keine Aktivierung)'
    assert re.search(
        r"addEventListener\(\s*['\"]click['\"]\s*,\s*tryFullscreen", js)
    # Fehler abfangen, nicht werfen
    assert re.search(r"document\.fullscreenElement", js), \
        'Vollbild-Guard muss den echten Status prüfen (nicht ein verbrennbares Flag)'


def test_PANEL_10_fullscreen_failure_does_not_throw():
    js = read(APPJS_PATH)
    # try/catch um requestFullscreen — Fehler werden geschluckt.
    assert re.search(r"try\s*\{[\s\S]{0,200}?req\.call\(el\)[\s\S]{0,200}?catch", js), \
        'Fehler beim requestFullscreen müssen abgefangen werden'


# ============================================================
#  PANEL-11 — Aktiv-Markierung aus SSE-Stream
# ============================================================

def test_PANEL_11_subscribes_to_display_events_stream():
    """app.js baut die Stream-URL aus dem display_id und ruft EventSource
    auf — der Pfad /api/v1/displays/.../events muss im Quelltext auftauchen
    (ROU-22)."""
    js = read(APPJS_PATH)
    assert re.search(r"['\"]/api/v1/displays/['\"]", js), \
        'app.js muss /api/v1/displays/<display_id>/events abonnieren (ROU-22)'
    assert re.search(r"['\"]/events['\"]", js), \
        'Stream-Pfad endet auf /events'
    assert re.search(r"new\s+EventSource\(", js), \
        'EventSource muss zum Streamen verwendet werden'
    assert re.search(r"encodeURIComponent\(\s*displayId\s*\)", js), \
        'display_id muss URL-encoded werden, damit Sonderzeichen tragen'


def test_PANEL_11_active_marker_matches_plain_url():
    """payload.url = /display/plan/woche → Kachel { app: plan, view: woche } aktiv."""
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icon: 'i', sichtbar: true },
            { key: 'b', app: 'plan', view: 'woche', query: { ansicht: 'klein' }, label: 'L', icon: 'i', sichtbar: true },
        ];
        const active = panelLib.findActiveTile(tiles, '/display/plan/woche');
        console.log(JSON.stringify({ key: active && active.key }));
    ''')
    assert out['key'] == 'a'


def test_PANEL_11_active_marker_matches_query_url():
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icon: 'i', sichtbar: true },
            { key: 'b', app: 'plan', view: 'woche', query: { ansicht: 'klein' }, label: 'L', icon: 'i', sichtbar: true },
        ];
        const active = panelLib.findActiveTile(tiles, '/display/plan/woche?ansicht=klein');
        console.log(JSON.stringify({ key: active && active.key }));
    ''')
    assert out['key'] == 'b'


def test_PANEL_11_null_stream_no_active_tile():
    """payload.url null / Session-Ende → keine Kachel aktiv."""
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icon: 'i', sichtbar: true },
        ];
        const active = panelLib.findActiveTile(tiles, null);
        console.log(JSON.stringify({ active }));
    ''')
    assert out['active'] is None


def test_PANEL_11_mismatch_no_active_tile():
    """Display-Inhalt, der zu keiner Kachel passt (z. B. eine andere App)
    → keine Kachel aktiv."""
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icon: 'i', sichtbar: true },
        ];
        const active = panelLib.findActiveTile(tiles, '/display/figur/szene-x');
        console.log(JSON.stringify({ active }));
    ''')
    assert out['active'] is None


def test_PANEL_11_stream_break_keeps_last_marker():
    """DC-6-Linie: Bei Stream-Abbruch macht der Code nichts aktiv (kein
    clearAll-Aufruf). Statisch geprüft: kein Reset der active-Klasse im
    error/onerror-Handler."""
    js = read(APPJS_PATH)
    # Keine 'updateActiveMarker(null)'-Stelle im EventSource-error-Pfad.
    # Vereinfachte Negativ-Probe: kein 'es.onerror' der Markierung löscht.
    if re.search(r"es\.onerror|addEventListener\(\s*['\"]error['\"]", js):
        # Falls vorhanden, darf er die Markierung nicht resetten.
        assert not re.search(
            r"(es\.onerror|addEventListener\(\s*['\"]error['\"][\s\S]{0,200}?updateActiveMarker\s*\(\s*null",
            js), 'Bei Stream-Abbruch darf die letzte Markierung nicht gelöscht werden (DC-6)'


def test_PANEL_11_eventsource_used_for_reconnect():
    """Browser-EventSource bringt Standard-Reconnect mit (DC-7) — Test
    auf die Verwendung von EventSource statt eigener fetch-Streaming-Logik."""
    js = read(APPJS_PATH)
    assert re.search(r"new\s+EventSource\(", js), \
        'app.js muss EventSource verwenden (Standard-Reconnect, DC-7)'
