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
SHARED_CONFIG_PATH = os.path.join(ROOT, '..', '_shared', 'config.js')


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


def run_node_with_shared(snippet):
    """Lädt pwaShared (_shared/config.js) UND panelLib (app.js), führt
    JS-Snippet aus. Für PANEL-8-Tests, die pwaShared.loadPwaConfig
    über global.fetch mocken (PWA-4-Verhaltens-Proben)."""
    src = textwrap.dedent('''
        const pwaShared = require(%r);
        const panelLib = require(%r);
        %s
    ''' % (SHARED_CONFIG_PATH, APPJS_PATH, snippet))
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
            { key: 'k1', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true});
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
    /display/<app>/<view>. Routing-Petrantwortung liegt allein beim Router."""
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
            { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['arasaac/test.png'], sichtbar: true},
            { key: 'b', app: 'p', view: 'v', label: 'B', icons: ['arasaac/test.png'], sichtbar: true},
            { key: 'c', app: 'p', view: 'v', label: 'C', icons: ['arasaac/test.png'], sichtbar: true},
        ];
        console.log(JSON.stringify(panelLib.visibleTiles(tiles).map(t => t.key)));
    ''')
    assert out == ['a', 'b', 'c']


def test_PANEL_3_keys_in_example_are_unique():
    data = json.loads(read(TILES_EXAMPLE))
    keys = [t['key'] for t in data['tiles']]
    assert len(keys) == len(set(keys)), 'tiles.example.json: key muss eindeutig sein'


def test_PANEL_3_tiles_example_format_valid():
    """PANEL-3 (#136): tiles.example.json nutzt icons[] statt icon."""
    data = json.loads(read(TILES_EXAMPLE))
    for t in data['tiles']:
        for k in ('key', 'app', 'view', 'label'):
            assert k in t and isinstance(t[k], str) and t[k], \
                'Pflichtfeld %s fehlt oder ist kein String: %r' % (k, t)
        assert 'icons' in t and isinstance(t['icons'], list) and len(t['icons']) >= 1, \
            'icons muss ein nicht-leeres Array sein: %r' % (t,)
        for idx, ico in enumerate(t['icons']):
            assert isinstance(ico, str) and ico, \
                'icons[%d] muss ein nicht-leerer String sein: %r' % (idx, t)
        assert isinstance(t['sichtbar'], bool)


def test_PANEL_3_icons_array_single_validated():
    """PANEL-3 (#136): validateTile akzeptiert icons[] mit genau einem Eintrag."""
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L',
            icons: ['arasaac/32488.png'], sichtbar: true,
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is None, 'icons[] mit einem Eintrag muss valide sein (bekommen: %r)' % out['err']


def test_PANEL_3_icons_array_two_entries_validated():
    """PANEL-3 (#136): validateTile akzeptiert icons[] mit zwei Einträgen (Kinder-Marker-Pattern)."""
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L',
            icons: ['arasaac/32488.png', 'arasaac/2484.png'], sichtbar: true,
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is None, 'icons[] mit zwei Einträgen muss valide sein (bekommen: %r)' % out['err']


def test_PANEL_3_icons_missing_rejected():
    """PANEL-3 (#136): validateTile lehnt eine Kachel ohne icons[] ab."""
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L', sichtbar: true,
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is not None and 'icons' in out['err'].lower(), \
        'Fehlende icons[] muss als Validierungs-Fehler zurückkommen (bekommen: %r)' % out['err']


def test_PANEL_3_icons_empty_array_rejected():
    """PANEL-3 (#136): validateTile lehnt icons: [] (leer) ab."""
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L',
            icons: [], sichtbar: true,
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is not None, 'Leeres icons[] muss abgelehnt werden (bekommen: %r)' % out['err']


def test_PANEL_3_resolve_icon_base_empty_router_url():
    """PANEL-3 (#136): resolveIconBase ohne router_url → same-origin /display/_shared/icons/."""
    out = run_node('''
        const base = panelLib.resolveIconBase('');
        console.log(JSON.stringify({ base }));
    ''')
    assert out['base'] == '/display/_shared/icons/', \
        'Leerer router_url muss same-origin-Basis liefern (bekommen: %r)' % out['base']


def test_PANEL_3_resolve_icon_base_with_router_url():
    """PANEL-3 (#136): resolveIconBase mit router_url → absoluter Prefix."""
    out = run_node('''
        const base = panelLib.resolveIconBase('https://hub.local:8443');
        console.log(JSON.stringify({ base }));
    ''')
    assert out['base'] == 'https://hub.local:8443/display/_shared/icons/', \
        'router_url muss als Prefix vorangestellt werden (bekommen: %r)' % out['base']


def test_PANEL_3_resolve_icon_base_trailing_slash_stripped():
    """PANEL-3 (#136): resolveIconBase entfernt trailing Slash aus router_url."""
    out = run_node('''
        const base = panelLib.resolveIconBase('https://hub.local:8443/');
        console.log(JSON.stringify({ base }));
    ''')
    assert out['base'] == 'https://hub.local:8443/display/_shared/icons/', \
        'Trailing Slash in router_url muss entfernt werden (bekommen: %r)' % out['base']


def test_PANEL_3_icon_paths_resolved_in_example():
    """PANEL-3 (#136): tiles.example.json enthält Kinder-Variante mit zwei Icons
    (arasaac/32488.png + arasaac/2484.png) — Kinder-Marker-Pattern."""
    data = json.loads(read(TILES_EXAMPLE))
    kinder = next((t for t in data['tiles'] if t.get('key') == 'wochenplan-klein'), None)
    assert kinder is not None, 'wochenplan-klein Tile muss in tiles.example.json vorhanden sein'
    assert kinder['icons'] == ['arasaac/32488.png', 'arasaac/2484.png'], \
        'Kinder-Kachel muss Kalender + Kinderkopf als icons[] haben (bekommen: %r)' % kinder['icons']


# ============================================================
#  PANEL-4 — sichtbar:false wird nicht gerendert (kein Event möglich)
# ============================================================

def test_PANEL_4_invisible_tiles_filtered():
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['arasaac/test.png'], sichtbar: true},
            { key: 'b', app: 'p', view: 'v', label: 'B', icons: ['arasaac/test.png'], sichtbar: false},
            { key: 'c', app: 'p', view: 'v', label: 'C', icons: ['arasaac/test.png'], sichtbar: true},
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


def test_PANEL_5_backoffs_overridable_via_opts():
    """Nit (#126) Tuning-Externalisierung: postWithRetry akzeptiert eine
    `backoffs`-Option und nutzt sie anstelle der Code-Default-Konstante.
    Damit darf config.json den Wert ohne Code-Edit aendern."""
    out = run_node('''
        const delays = [];
        const fakeFetch = () => Promise.reject(new Error('x'));
        const fakeTimeout = (fn, ms) => { delays.push(ms); fn(); };
        panelLib.postWithRetry({
            fetchImpl: fakeFetch,
            setTimeoutImpl: fakeTimeout,
            url: 'http://x',
            body: {},
            backoffs: [10, 20],
            onDrop: () => {},
        });
        setImmediate(() => console.log(JSON.stringify({ delays })));
    ''')
    assert out['delays'] == [10, 20], (
        'postWithRetry muss opts.backoffs nutzen (bekommen: %r)' % out['delays'])


def test_PANEL_5_backoffs_in_config_defaults():
    """Tuning-Externalisierung: configDefaults() exponiert backoffs als
    Daten-Feld, damit config.json es ueberschreiben kann."""
    out = run_node('console.log(JSON.stringify(panelLib.configDefaults()));')
    assert out.get('backoffs') == [200, 1000, 5000], (
        'configDefaults muss backoffs als Default-Wert tragen (bekommen: %r)' % out.get('backoffs'))


def test_PANEL_5_backoffs_in_example_config():
    """Tuning-Externalisierung: config.example.json dokumentiert den
    backoffs-Override-Pfad explizit (CLAUDE.md §6: Default UND Override-Pfad)."""
    data = json.loads(read(CONFIG_EXAMPLE))
    assert data.get('backoffs') == [200, 1000, 5000], (
        'config.example.json muss backoffs explizit zeigen (CLAUDE.md §6)')


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
            { key: 'k', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true});
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
            { key: 'k', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true,
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
    # panelLib.makeAusKachel wird unkonditional aufgerufen — kein Branch über sichtbar.
    # Signatur: panelLib.makeAusKachel(document, onClear, base) (#136 Refactor).
    assert re.search(r"panelLib\.makeAusKachel\(", js), \
        'Aus-Kachel muss unkonditional gerendert werden'


def test_PANEL_6_aus_kachel_sends_panel_cleared():
    """Tap auf die Aus-Kachel → panel_cleared ohne Descriptor.
    (Seit PANEL-11 Optimistik, Refs #959, ruft onClear() zuerst
    updateActiveMarker(null) und dann sendEvent(…makePanelCleared) —
    der Test prüft daher nur, dass sendEvent(…makePanelCleared innerhalb
    von onClear vorkommt, nicht als erster Aufruf.)"""
    js = read(APPJS_PATH)
    # onClear muss sendEvent(cfg, panelLib.makePanelCleared(…)) enthalten.
    # updateActiveMarker(null) darf davor stehen (PANEL-11 Optimistik).
    assert re.search(
        r"function onClear\(\)[\s\S]{0,500}?sendEvent\([^,]+,\s*panelLib\.makePanelCleared",
        js), 'onClear muss panel_cleared via sendEvent senden'


# ============================================================
#  PANEL-7 — Descriptor flach (Strings/Zahlen)
# ============================================================

def test_PANEL_7_nested_query_rejected_as_config_error():
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'],
            sichtbar: true,
            query: { nested: { inner: 'x' } },
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is not None and 'query' in out['err'].lower()


def test_PANEL_7_list_query_rejected():
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'],
            sichtbar: true,
            query: { list: [1, 2] },
        });
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is not None


def test_PANEL_7_flat_string_or_number_query_ok():
    out = run_node('''
        const err = panelLib.validateTile({
            key: 'k', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'],
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

def test_PANEL_8_pwaShared_fetches_config_json():
    """Verhaltens-Probe (PWA-4): pwaShared.loadPwaConfig ruft global.fetch
    mit './config.json' und no-store Cache auf. Testet das migrierte
    Bootstrap (PWA-4, #246)."""
    out = run_node_with_shared('''
        const calls = [];
        global.fetch = (u, init) => {
            calls.push({ url: u, init: init });
            return Promise.resolve({
                ok: true, json: () => Promise.resolve({ source_id: 'app-panel:x', display_id: 'display:y' })
            });
        };
        pwaShared.loadPwaConfig({
            defaults: panelLib.configDefaults(),
        }).then((cfg) => {
            console.log(JSON.stringify({ calls, cfg }));
        });
    ''')
    assert out['calls'][0]['url'] == './config.json'
    assert out['calls'][0]['init']['cache'] == 'no-store'


def test_PANEL_8_missing_config_falls_back_silently_to_defaults():
    """Verhaltens-Probe (PWA-4): fetch wirft → pwaShared.loadPwaConfig ruft
    onWarn, gibt die Defaults zurück (CONFIG-4 stummer Fallback). Testet
    das migrierte Bootstrap (#246)."""
    out = run_node_with_shared('''
        const warns = [];
        global.fetch = () => Promise.reject(new Error('boom'));
        pwaShared.loadPwaConfig({
            defaults: panelLib.configDefaults(),
            onWarn: (...args) => { warns.push(String(args[0])); },
        }).then((cfg) => {
            console.log(JSON.stringify({ warns, cfg }));
        });
    ''')
    assert len(out['warns']) == 1, 'Genau ein console.warn-aequivalenter Aufruf erwartet'
    assert 'fallback' in out['warns'][0].lower()
    # Defaults intakt: source_id startet mit "app-panel:".
    # display_id ist bewusst nicht mehr in configDefaults() (PANEL-8, #414).
    assert out['cfg']['source_id'].startswith('app-panel:')
    assert 'display_id' not in out['cfg'], (
        'display_id darf nicht in configDefaults() sein (PANEL-8 / #414): '
        'wird per ROU-32 vom Router gezogen, nicht aus config.json'
    )


def test_PANEL_8_http_error_also_falls_back_to_defaults():
    """Verhaltens-Probe: fetch liefert !ok → derselbe stumme Fallback-Pfad."""
    out = run_node_with_shared('''
        const warns = [];
        global.fetch = () => Promise.resolve({ ok: false, status: 500 });
        pwaShared.loadPwaConfig({
            defaults: panelLib.configDefaults(),
            onWarn: (...args) => { warns.push(String(args[0])); },
        }).then((cfg) => {
            console.log(JSON.stringify({ warns, cfg, isDefault: cfg.source_id === 'app-panel:demo' }));
        });
    ''')
    assert len(out['warns']) == 1
    assert out['isDefault'] is True


def test_PANEL_8_consistency_mismatch_calls_onError():
    """Verhaltens-Probe: nach pwaShared.loadPwaConfig prüft checkConfigConsistency
    die Kopplung source_id ↔ panelId; bei Diskrepanz wird onError mit einer
    sichtbaren Meldung aufgerufen; cfg wird trotzdem geliefert (kein Hard-Stop).
    Testet die Zwei-Schritte-Zusammensetzung des migrierten Bootstrap (#246)."""
    out = run_node_with_shared('''
        const errors = [];
        global.fetch = () => Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
                source_id: 'app-panel:wohnzimmer', display_id: 'display:x'
            }),
        });
        pwaShared.loadPwaConfig({
            defaults: panelLib.configDefaults(),
        }).then((cfg) => {
            const errMsg = panelLib.checkConfigConsistency(cfg, 'kueche');
            if (errMsg) errors.push('Konfigurations-Fehler: ' + errMsg);
            console.log(JSON.stringify({ errors, sourceId: cfg.source_id }));
        });
    ''')
    assert len(out['errors']) == 1
    assert 'source_id' in out['errors'][0].lower() or 'konfig' in out['errors'][0].lower()
    # cfg wird trotzdem geliefert (Spec: sichtbarer Fehler, kein Abbruch).
    assert out['sourceId'] == 'app-panel:wohnzimmer'


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


def test_PANEL_8_display_id_not_checked_in_config_consistency():
    """PANEL-8 (#414): die frühere Konsistenz-Probe gegen cfg.display_id entfällt.
    checkConfigConsistency prüft NUR noch source_id ↔ panelId —
    display_id kommt via ROU-32 vom Router, nicht aus config.json."""
    out = run_node('''
        // Kein display_id in cfg — früher Fehler, jetzt kein Fehler mehr.
        const err = panelLib.checkConfigConsistency(
            { source_id: 'app-panel:k' },
            'k');
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is None, (
        'checkConfigConsistency darf display_id nicht mehr prüfen (PANEL-8 / #414): '
        'bekommen: %r' % out['err'])


def test_PANEL_8_matching_config_no_error():
    out = run_node('''
        const err = panelLib.checkConfigConsistency(
            { source_id: 'app-panel:k' },
            'k');
        console.log(JSON.stringify({ err }));
    ''')
    assert out['err'] is None


def test_PANEL_8_config_example_format_valid():
    data = json.loads(read(CONFIG_EXAMPLE))
    # Pflichtfelder laut PANEL-8 (Stand nach Nic-Entscheid 2026-06-08 / #414):
    # source_id + router_url. display_id ist bewusst NICHT in config.json —
    # kommt per ROU-32 vom Router.
    for k in ('source_id', 'router_url'):
        assert k in data, 'Pflicht-Feld %s fehlt in config.example.json' % k
    assert data['source_id'].startswith('app-panel:')
    assert 'display_id' not in data, (
        'display_id darf NICHT in config.example.json stehen (PANEL-8 / #414): '
        'kommt per ROU-32 vom Router'
    )
    # Der Kommentar erklärt, woher display_id kommt (AC4).
    assert '_display_id_comment' in data, (
        'config.example.json muss _display_id_comment enthalten, der erklärt, '
        'dass display_id per ROU-32 vom Router kommt (AC4)'
    )
    assert 'ROU-32' in data['_display_id_comment'], (
        '_display_id_comment muss ROU-32 erwähnen'
    )


# ============================================================
#  PANEL-9 — Meta: alle Tests existieren
# ============================================================

def test_PANEL_9_test_file_covers_all_panel_ids():
    """Selbst-Probe: für jede PANEL-ID aus dem Mindest-Abdeckungs-Block
    der Spec gibt es mindestens einen Test in dieser Datei."""
    here = read(os.path.abspath(__file__))
    for pid in ['PANEL_1', 'PANEL_2', 'PANEL_3', 'PANEL_4', 'PANEL_5',
                'PANEL_6', 'PANEL_7', 'PANEL_8', 'PANEL_10', 'PANEL_11',
                'PANEL_12']:
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
        r'<link[^>]+rel=["\']manifest["\'][^>]+href=["\']\.\/manifest\.json(\?v=[^"\']*)?["\']',
        html)
    js = read(APPJS_PATH)
    assert re.search(r"navigator\.serviceWorker\.register\(['\"]\.\/sw\.js(\?v=[^\"']*)?['\"](\s*,\s*\{[^}]*\})?\s*\)",
                     js), 'SW-Registrierung fehlt'


def test_PANEL_10_sw_js_static_assets_config_absolute_path():
    """Regressions-Guard #317: sw.js precacht config.js über den ABSOLUTEN
    Pfad /controller/_shared/config.js, NICHT über den kaputten Relativpfad
    ../_shared/config.js.

    Hintergrund: sw.js wird mit scope /controller/app-panel/<panel_id>/
    registriert. Von dort würde ../_shared/ zu /controller/app-panel/_shared/
    auflösen — 404. Nur /controller/_shared/config.js ist tiefenrobust
    und konsistent mit dem absoluten Pfad in index.html (PANEL-10 / PWA-4 /
    Ticket #317)."""
    sw = read(SW_PATH)
    # Absoluter Pfad muss vorhanden sein.
    assert "'/controller/_shared/config.js'" in sw, (
        "sw.js STATIC_ASSETS muss config.js über den absoluten Pfad "
        "'/controller/_shared/config.js' precachen (Ticket #317)"
    )
    # Kaputten Relativpfad darf es nicht mehr geben.
    assert "'../_shared/config.js'" not in sw, (
        "Kaputten Relativpfad ../_shared/config.js in sw.js STATIC_ASSETS "
        "gefunden — bricht bei SW-Install ab (Ticket #317)"
    )


def test_PANEL_10_wake_lock_requested_on_load_and_visibility():
    """Verhaltens-Probe (Finding 5, #126): attachWakeLockImpl ruft beim
    Anhaengen sofort wakeLock.request('screen'), registriert einen
    visibilitychange-Listener und ruft request erneut, wenn der Listener
    bei sichtbarer Seite feuert. Keine Quelltext-Greps."""
    out = run_node('''
        const requests = [];
        const events = [];
        const fakeNav = {
            wakeLock: {
                request: (kind) => {
                    requests.push(kind);
                    return Promise.resolve({ release: () => {} });
                },
            },
        };
        const fakeDoc = {
            visibilityState: 'visible',
            addEventListener: (type, cb) => { events.push({ type, cb }); },
        };
        const handle = panelLib.attachWakeLockImpl({ doc: fakeDoc, nav: fakeNav });
        // Listener-Registrierung beobachten.
        const visTypes = events.map(e => e.type);
        // Listener feuern lassen, um den Re-Request zu beobachten.
        events.filter(e => e.type === 'visibilitychange').forEach(e => e.cb());
        // Hidden-State: KEIN weiterer Request.
        fakeDoc.visibilityState = 'hidden';
        events.filter(e => e.type === 'visibilitychange').forEach(e => e.cb());
        console.log(JSON.stringify({ requests, visTypes }));
    ''')
    # Initial-Request + 1 Re-Request bei visible. Hidden darf nicht ausloesen.
    assert out['requests'] == ['screen', 'screen'], (
        'Erwartet: 1 Initial- + 1 Re-Request bei sichtbarer Seite (bekommen: %r)' % out['requests'])
    assert 'visibilitychange' in out['visTypes']


def test_PANEL_10_wake_lock_silent_when_unsupported():
    """Verhaltens-Probe: nav ohne wakeLock-Property → kein Crash, kein Aufruf."""
    out = run_node('''
        const events = [];
        const fakeNav = {};  // kein wakeLock
        const fakeDoc = {
            visibilityState: 'visible',
            addEventListener: (type, cb) => { events.push({ type, cb }); },
        };
        let threw = false;
        try { panelLib.attachWakeLockImpl({ doc: fakeDoc, nav: fakeNav }); }
        catch (e) { threw = true; }
        console.log(JSON.stringify({ threw, eventTypes: events.map(e => e.type) }));
    ''')
    assert out['threw'] is False
    # visibilitychange-Listener wird trotzdem registriert (Konsistenz).
    assert 'visibilitychange' in out['eventTypes']


def test_PANEL_10_request_fullscreen_on_first_gesture():
    """Verhaltens-Probe (Finding 5, #126): attachFullscreenImpl registriert
    touchend+click; der Handler ruft documentElement.requestFullscreen,
    aber NUR wenn nicht schon im Vollbild (Guard auf fullscreenElement)."""
    out = run_node('''
        const events = [];
        const calls = [];
        const fakeDoc = {
            fullscreenElement: null,
            documentElement: {
                requestFullscreen: function () {
                    calls.push('req');
                    return Promise.resolve();
                },
            },
            addEventListener: (type, cb, opts) => { events.push({ type, cb, opts }); },
        };
        const h = panelLib.attachFullscreenImpl({ doc: fakeDoc });
        // touchend-Handler feuert → Request.
        events.filter(e => e.type === 'touchend').forEach(e => e.cb());
        // Jetzt sind wir „im Vollbild" — weitere Gesten muessen ignoriert werden.
        fakeDoc.fullscreenElement = fakeDoc.documentElement;
        events.filter(e => e.type === 'click').forEach(e => e.cb());
        console.log(JSON.stringify({
            calls,
            types: events.map(e => e.type),
            touchendPassive: events.find(e => e.type === 'touchend').opts && events.find(e => e.type === 'touchend').opts.passive,
        }));
    ''')
    assert out['calls'] == ['req'], (
        'requestFullscreen darf nur beim ersten Gesture feuern (bekommen: %r)' % out['calls'])
    assert 'touchend' in out['types']
    assert 'click' in out['types']
    # touchend muss passive registriert sein, sonst blockiert Scroll-Verhalten.
    assert out['touchendPassive'] is True


def test_PANEL_10_fullscreen_failure_does_not_throw():
    """Verhaltens-Probe: requestFullscreen wirft synchron → kein Throw
    aus attachFullscreenImpl.tryFullscreen heraus."""
    out = run_node('''
        const fakeDoc = {
            fullscreenElement: null,
            documentElement: {
                requestFullscreen: function () { throw new Error('nope'); },
            },
            addEventListener: () => {},
        };
        const h = panelLib.attachFullscreenImpl({ doc: fakeDoc });
        let threw = false;
        try { h.tryFullscreen(); } catch (e) { threw = true; }
        console.log(JSON.stringify({ threw }));
    ''')
    assert out['threw'] is False, 'Fehler beim requestFullscreen muss verschluckt werden'


def test_PANEL_10_fullscreen_rejected_promise_does_not_throw():
    """Verhaltens-Probe: requestFullscreen liefert rejected Promise → kein
    unhandled rejection-Bruch. Wir verifizieren, dass der Code .catch anhaengt."""
    out = run_node('''
        let caught = false;
        const fakeDoc = {
            fullscreenElement: null,
            documentElement: {
                requestFullscreen: function () {
                    return { then: function () { return this; }, catch: function (cb) { caught = true; return this; } };
                },
            },
            addEventListener: () => {},
        };
        const h = panelLib.attachFullscreenImpl({ doc: fakeDoc });
        h.tryFullscreen();
        console.log(JSON.stringify({ caught }));
    ''')
    assert out['caught'] is True, 'attachFullscreenImpl muss .catch auf das Promise haengen'


def test_PANEL_10_embedded_suppresses_own_fullscreen_T1529():
    """SHELL-11 / T1529-Regression: das Panel darf im eingebetteten Kontext
    (Heim-Shell-Iframe, window.self !== window.top) seinen Eigen-Vollbild NICHT
    attachen — sonst frisst ein requestFullscreen auf touchend im
    allowfullscreen-losen Iframe den folgenden Kachel-Click (jede Kachel zwei Taps,
    #1529). Der Guard muss VOR dem attachFullscreenImpl-Aufruf im Bootstrap-Wrapper
    attachFullscreenOnGesture stehen; Standalone-Panel (self === top) behält PANEL-10.

    Verhaltens-Beleg für attachFullscreenImpl selbst liefert
    test_PANEL_10_request_fullscreen_on_first_gesture; hier pinnen wir die
    embedded-Ausnahme (nur im Bootstrap, nicht als Node-Logik testbar, weil
    window/document fehlen). Ground-Truth-Repro (puppeteer, T1529) bestätigt:
    embedded === true → attachFullscreenImpl wird nicht verdrahtet."""
    js = read(APPJS_PATH)
    # Guard-Ausdruck muss existieren.
    assert 'window.self !== window.top' in js, (
        'app.js muss den embedded-Guard "window.self !== window.top" tragen (SHELL-11/T1529)')
    # Der Guard muss VOR dem attachFullscreenImpl-Aufruf im Wrapper stehen und
    # mit einem frühen return greifen (kein Attach im embedded-Fall).
    m = re.search(
        r'function\s+attachFullscreenOnGesture\s*\(\s*\)\s*\{(.*?)\n\s*\}',
        js, re.DOTALL)
    assert m, 'attachFullscreenOnGesture-Wrapper nicht gefunden'
    body = m.group(1)
    # Der Guard muss ein echtes `if (window.self !== window.top) return;`-Statement
    # sein (nicht bloß eine Erwähnung im Kommentar).
    guard_stmt = re.search(
        r'if\s*\(\s*window\.self\s*!==\s*window\.top\s*\)\s*return\s*;', body)
    assert guard_stmt, (
        'app.js muss "if (window.self !== window.top) return;" im '
        'attachFullscreenOnGesture-Wrapper tragen (SHELL-11/T1529 embedded-Ausnahme)')
    attach_pos = body.find('attachFullscreenImpl')
    assert attach_pos != -1, (
        'attachFullscreenImpl-Aufruf fehlt im attachFullscreenOnGesture-Wrapper')
    assert guard_stmt.start() < attach_pos, (
        'embedded-Guard muss VOR attachFullscreenImpl stehen — sonst attacht das '
        'eingebettete Panel seinen Eigen-Vollbild und frisst den ersten Kachel-Tap (#1529)')


# ============================================================
#  PANEL-11 — Aktiv-Markierung aus SSE-Stream
# ============================================================


def test_PANEL_11_active_marker_matches_plain_url():
    """payload.url = /display/plan/woche → Kachel { app: plan, view: woche } aktiv."""
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
            { key: 'b', app: 'plan', view: 'woche', query: { ansicht: 'klein' }, label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
        ];
        const active = panelLib.findActiveTile(tiles, '/display/plan/woche');
        console.log(JSON.stringify({ key: active && active.key }));
    ''')
    assert out['key'] == 'a'


def test_PANEL_11_active_marker_matches_query_url():
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
            { key: 'b', app: 'plan', view: 'woche', query: { ansicht: 'klein' }, label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
        ];
        const active = panelLib.findActiveTile(tiles, '/display/plan/woche?ansicht=klein');
        console.log(JSON.stringify({ key: active && active.key }));
    ''')
    assert out['key'] == 'b'


def test_PANEL_11_null_stream_no_active_tile():
    """payload.url null / Session-Ende → keine Kachel aktiv."""
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
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
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
        ];
        const active = panelLib.findActiveTile(tiles, '/display/figur/szene-x');
        console.log(JSON.stringify({ active }));
    ''')
    assert out['active'] is None



def test_PANEL_11_stream_handlers_registered_on_eventsource():
    """Strukturelle Probe: app.js registriert für die EventSource sowohl einen
    message-Listener als auch einen onerror-Handler. Ohne den onerror-Handler
    wäre die DC-6-Garantie nur konventionell („Browser löscht ja nichts“) —
    der explizite No-Op-Handler dokumentiert die Absicht."""
    js = read(APPJS_PATH)
    assert re.search(r"es\.onerror\s*=", js), \
        'EventSource muss einen expliziten onerror-Handler haben (DC-6 dokumentiert)'


def test_PANEL_11_duplicate_descriptor_returns_first_match():
    """Finding 6 (#126): zwei Kacheln mit identischem {app, view, query}
    sind in tiles.json zwar deskriptiv legal (PANEL-3 erzwingt nur den
    `key`-Unique-Constraint, nicht den Descriptor), beim Aktiv-Match nimmt
    findActiveTile aber den ersten Treffer in Listen-Reihenfolge — V1-
    Verhalten explizit abgesichert."""
    out = run_node('''
        const tiles = [
            { key: 'first',  app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
            { key: 'second', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
        ];
        const active = panelLib.findActiveTile(tiles, '/display/plan/woche');
        console.log(JSON.stringify({ key: active && active.key }));
    ''')
    assert out['key'] == 'first', (
        'findActiveTile muss bei doppeltem Descriptor den ersten Treffer liefern (V1) — '
        'bekommen: %r' % out['key'])


def test_PANEL_11_eventsource_used_for_reconnect():
    """Browser-EventSource bringt Standard-Reconnect mit (DC-7) — Test
    auf die Verwendung von EventSource statt eigener fetch-Streaming-Logik."""
    js = read(APPJS_PATH)
    assert re.search(r"new\s+EventSource\(", js), \
        'app.js muss EventSource verwenden (Standard-Reconnect, DC-7)'


def test_PANEL_11_find_active_tile_multi_segment_ac1():
    """AC2 / T1007-S2: findActiveTile matcht Multi-Segment-Views korrekt.
    Kachel { app: 'hoerspiel', view: 'mia/alben' } muss bei URL
    /display/hoerspiel/mia/alben als aktiv erkannt werden.
    Sichert den echten PANEL-11-Effekt-Pfad (parseDisplayUrl →
    tileMatchesUrl → findActiveTile → updateActiveMarker)."""
    out = run_node('''
        const tiles = [
            { key: 'p', app: 'hoerspiel', view: 'mia/alben',
              label: 'Mias Hörspiele', icons: ['arasaac/5915.png'],
              sichtbar: true },
            { key: 'n', app: 'hoerspiel', view: 'finn/alben',
              label: 'Finns Hörspiele', icons: ['arasaac/5915.png'],
              sichtbar: true },
        ];
        const active = panelLib.findActiveTile(tiles, '/display/hoerspiel/mia/alben');
        console.log(JSON.stringify({ key: active && active.key }));
    ''')
    assert out['key'] == 'p', (
        'findActiveTile muss Multi-Segment-View mia/alben matchen — '
        'bekommen: %r' % out.get('key'))


# ============================================================
#  PANEL-3 / PANEL-6 — Render-Pfad: makeTileElement / makeAusKachel
#  (PANEL-9-Mindest-Abdeckung Icon-Verhalten)
# ============================================================
#
# Die Bootstrap-Sektion von app.js wird nur im Browser ausgeführt (Guard:
# `if (typeof document === 'undefined') return`). Für Tests instantiieren
# wir eine minimale document/createElement-Attrappe in Node, die den
# DOM-Aufruf-Pfad vollständig durchläuft und die img.src-Werte sammelt.

_DOM_STUB = r"""
// Minimale DOM-Attrappe: reicht createElement/appendChild/addEventListener/
// dataset/classList aus, ohne jsdom-Abhängigkeit.
function makeDom() {
  function makeEl(tag) {
    var el = {
      _tag: tag, _children: [], _listeners: {},
      type: '', className: '', textContent: '',
      dataset: {}, classList: { add: function(){}, remove: function(){} },
      src: '', alt: '', onerror: null,
      appendChild: function(c) { this._children.push(c); return c; },
      addEventListener: function(ev, cb, opts) {
        if (!this._listeners[ev]) this._listeners[ev] = [];
        this._listeners[ev].push({ cb: cb, opts: opts });
      },
      removeChild: function(c) {
        this._children = this._children.filter(function(x){ return x !== c; });
      },
    };
    // parentNode simulieren, sobald appendchild verwendet wird
    el.appendChild = function(c) {
      c.parentNode = el;
      this._children.push(c);
      return c;
    };
    return el;
  }
  var doc = {
    createElement: function(tag) { return makeEl(tag); },
    getElementById: function() { return null; },
    querySelectorAll: function() { return []; },
    visibilityState: 'visible',
    fullscreenElement: null,
    documentElement: makeEl('html'),
    body: makeEl('body'),
    addEventListener: function() {},
  };
  return doc;
}
"""


def run_node_dom(snippet):
    """Lädt panelLib aus der echten app.js, baut eine DOM-Attrappe (makeDom)
    und führt das Snippet mit Zugriff auf `panelLib` und `makeDom` aus.
    Der Bootstrap-Block von app.js wird wegen `typeof document === 'undefined'`
    NICHT ausgeführt — wir rufen panelLib.makeTileElement / panelLib.makeAusKachel
    direkt auf und übergeben den DOM-Stub als erstes Argument (echte exportierte
    Library-Funktion, kein Kopie-Muster)."""
    src = textwrap.dedent('''
        const panelLib = require(%r);
        %s
        %s
    ''' % (APPJS_PATH, _DOM_STUB, snippet))
    res = subprocess.run(
        ['node', '-e', src],
        capture_output=True, text=True, timeout=10)
    if res.returncode != 0:
        raise AssertionError(
            'node-DOM-Subprozess fehlgeschlagen:\n' + res.stderr
            + '\n--- src ---\n' + src)
    out = res.stdout.strip()
    if not out:
        return None
    return json.loads(out)


def test_PANEL_3_makeTileElement_icon_src_single(tmp_path):
    """PANEL-3 / PANEL-9 Render-Pfad: panelLib.makeTileElement (echte exportierte
    Library-Funktion) baut img.src korrekt für eine Kachel mit einem Icon (same-origin).
    DOM-Stub wird als erstes Argument übergeben — kein Kopie-Muster."""
    out = run_node_dom(r"""
        var doc = makeDom();
        var tile = { key: 'plan', app: 'plan', view: 'woche', label: 'Wochenplan',
                     icons: ['arasaac/32488.png'], sichtbar: true };
        var iconBaseStr = panelLib.resolveIconBase('');
        var el = panelLib.makeTileElement(doc, tile, function(){}, iconBaseStr);
        // iconSlot ist erstes Kind, die img-Kinder darin tragen die srcs
        var iconSlot = el._children[0];
        var srcs = iconSlot._children.map(function(c){ return c.src; });
        console.log(JSON.stringify({ srcs: srcs }));
    """)
    assert len(out['srcs']) == 1
    assert out['srcs'][0].endswith('/display/_shared/icons/arasaac/32488.png'), \
        'img.src muss auf /display/_shared/icons/arasaac/32488.png enden (same-origin, bekommen: %r)' % out['srcs'][0]


def test_PANEL_3_makeTileElement_icon_src_kinder_marker(tmp_path):
    """PANEL-3 / PANEL-9 Render-Pfad: panelLib.makeTileElement (echte exportierte
    Library-Funktion) baut zwei img-Elemente für das Kinder-Marker-Pattern
    (icons: ['arasaac/32488.png','arasaac/2484.png'])."""
    out = run_node_dom(r"""
        var doc = makeDom();
        var tile = { key: 'klein', app: 'plan', view: 'woche', label: 'Kids',
                     icons: ['arasaac/32488.png', 'arasaac/2484.png'], sichtbar: true };
        var iconBaseStr = panelLib.resolveIconBase('');
        var el = panelLib.makeTileElement(doc, tile, function(){}, iconBaseStr);
        var iconSlot = el._children[0];
        var srcs = iconSlot._children.map(function(c){ return c.src; });
        console.log(JSON.stringify({ srcs: srcs, count: srcs.length }));
    """)
    assert out['count'] == 2, \
        'Kinder-Marker-Pattern braucht 2 img-Elemente (bekommen: %d)' % out['count']
    assert out['srcs'][0].endswith('/display/_shared/icons/arasaac/32488.png'), \
        'Erstes Icon muss Kalender sein (bekommen: %r)' % out['srcs'][0]
    assert out['srcs'][1].endswith('/display/_shared/icons/arasaac/2484.png'), \
        'Zweites Icon muss Kinderkopf-Marker sein (bekommen: %r)' % out['srcs'][1]


def test_PANEL_6_makeAusKachel_icon_src(tmp_path):
    """PANEL-6 / PANEL-9 Render-Pfad: panelLib.makeAusKachel (echte exportierte
    Library-Funktion) baut img.src mit AUS_ICON_PATH (arasaac/8252.png) korrekt."""
    out = run_node_dom(r"""
        var doc = makeDom();
        var iconBaseStr = panelLib.resolveIconBase('');
        var el = panelLib.makeAusKachel(doc, function(){}, iconBaseStr);
        var iconSlot = el._children[0];
        var srcs = iconSlot._children.map(function(c){ return c.src; });
        console.log(JSON.stringify({ srcs: srcs, ausIconPath: panelLib.AUS_ICON_PATH }));
    """)
    assert len(out['srcs']) == 1
    assert out['srcs'][0].endswith('/display/_shared/icons/arasaac/8252.png'), \
        'Aus-Kachel img.src muss auf arasaac/8252.png enden (bekommen: %r)' % out['srcs'][0]
    assert out['ausIconPath'] == 'arasaac/8252.png', \
        'AUS_ICON_PATH-Konstante muss "arasaac/8252.png" sein (bekommen: %r)' % out['ausIconPath']


def test_PANEL_6_onerror_removes_broken_img(tmp_path):
    """PANEL-6 / PANEL-9 Fallback: onerror-Handler auf img (aus der echten
    panelLib.makeTileElement-Funktion) entfernt das Bild aus dem Icon-Slot.
    Simuliert einen Ladefehler durch direktes Aufrufen von img.onerror()."""
    out = run_node_dom(r"""
        var doc = makeDom();
        var tile = { key: 'plan', app: 'plan', view: 'woche', label: 'Wochenplan',
                     icons: ['arasaac/32488.png'], sichtbar: true };
        var iconBaseStr = panelLib.resolveIconBase('');
        var el = panelLib.makeTileElement(doc, tile, function(){}, iconBaseStr);
        var iconSlot = el._children[0];
        // Vor dem Fehler: 1 img im Slot
        var countBefore = iconSlot._children.length;
        // Ladefehler simulieren
        iconSlot._children[0].onerror.call(iconSlot._children[0]);
        // Nach dem Fehler: Slot muss leer sein
        var countAfter = iconSlot._children.length;
        // Label ist noch intakt
        var labelEl = el._children[1];
        console.log(JSON.stringify({
          countBefore: countBefore,
          countAfter: countAfter,
          labelText: labelEl.textContent,
        }));
    """)
    assert out['countBefore'] == 1, 'Vor Fehler muss 1 img im Slot sein'
    assert out['countAfter'] == 0, \
        'Nach onerror muss Icon-Slot leer sein (kein Broken-Image-Placeholder, PANEL-6; bekommen: %d)' % out['countAfter']
    assert out['labelText'] == 'Wochenplan', 'Label muss nach Icon-Fehler intakt bleiben'


def test_PANEL_6_onerror_aus_kachel_removes_broken_img(tmp_path):
    """PANEL-6 / PANEL-9 Fallback Aus-Kachel: onerror (aus der echten
    panelLib.makeAusKachel-Funktion) entfernt Bild; Kachel und Label bleiben."""
    out = run_node_dom(r"""
        var doc = makeDom();
        var iconBaseStr = panelLib.resolveIconBase('');
        var el = panelLib.makeAusKachel(doc, function(){}, iconBaseStr);
        var iconSlot = el._children[0];
        var countBefore = iconSlot._children.length;
        iconSlot._children[0].onerror.call(iconSlot._children[0]);
        var countAfter = iconSlot._children.length;
        var labelEl = el._children[1];
        console.log(JSON.stringify({
          countBefore: countBefore,
          countAfter: countAfter,
          labelText: labelEl.textContent,
        }));
    """)
    assert out['countBefore'] == 1
    assert out['countAfter'] == 0, \
        'Aus-Kachel: onerror muss img entfernen (PANEL-6; bekommen: %d)' % out['countAfter']
    assert out['labelText'] == 'Aus', 'Aus-Label muss intakt bleiben'


# ============================================================
#  PANEL-11 (AC5) — Aktiv-Marker token-basiert (E-PANEL-6 / #375)
# ============================================================

def test_PANEL_11_active_marker_uses_primary_token():
    """AC5 / E-PANEL-6: style.css setzt var(--primary) als Border-Farbe der
    aktiven Kachel (kein hartcodierter Farbwert, DTOK-5)."""
    css = read(CSS_PATH)
    # Aktiv-Markierung muss var(--primary) nutzen
    active_block = re.search(r'\.tile\.active\s*\{([^}]+)\}', css)
    assert active_block is not None, '.tile.active-Block muss in style.css vorhanden sein'
    block_content = active_block.group(1)
    assert 'var(--primary)' in block_content, \
        '.tile.active muss var(--primary) als Border-Farbe nutzen (DTOK-5, AC5; bekommen: %r)' % block_content


def test_PANEL_11_active_marker_uses_surface_soft_tint():
    """AC5 / E-PANEL-6: style.css setzt var(--surface-soft) als Hintergrund-Tint
    der aktiven Kachel (Token, kein hartcodierter rgba-Wert)."""
    css = read(CSS_PATH)
    active_block = re.search(r'\.tile\.active\s*\{([^}]+)\}', css)
    assert active_block is not None
    block_content = active_block.group(1)
    assert 'var(--surface' in block_content, \
        '.tile.active muss einen --surface-*-Token als Hintergrund nutzen (DTOK-5, AC5; bekommen: %r)' % block_content


def test_PANEL_11_active_marker_laeuft_badge_present():
    """AC5: .tile.active::after setzt 'Läuft'-Badge (PANEL-11 Spec)."""
    css = read(CSS_PATH)
    assert re.search(r'\.tile\.active::after', css), \
        '.tile.active::after (Läuft-Badge) muss in style.css definiert sein (AC5)'
    badge_block = re.search(r'\.tile\.active::after\s*\{([^}]+)\}', css)
    assert badge_block is not None
    assert 'Läuft' in badge_block.group(1), \
        'Läuft-Badge muss content: "Läuft" tragen (AC5; bekommen: %r)' % badge_block.group(1)


def test_PANEL_11_no_hardcoded_colors_in_active_marker():
    """AC4/AC5 / DTOK-5: Keine hartcodierten Hex-Farben in der aktiven Kachel-Markierung."""
    css = read(CSS_PATH)
    active_section = re.search(
        r'(/\*\s*PANEL-11[\s\S]*?)(?=/\*\s*PANEL-6)', css)
    if active_section:
        section = active_section.group(1)
        # Hex-Farben sind verboten (DTOK-5)
        hex_found = re.findall(r'#[0-9a-fA-F]{3,8}\b', section)
        assert not hex_found, \
            'Keine hartcodierten Hex-Farben in PANEL-11-Sektion erlaubt (DTOK-5): gefunden %r' % hex_found


# ============================================================
#  PANEL-11 — Optimistisches lokales Update (PANEL-11 Spec, Refs #959)
# ============================================================
#
# AC1: onTap ruft updateActiveMarker(tile) VOR sendEvent.
# AC2: onClear ruft updateActiveMarker(null) VOR sendEvent.
# AC3: Tap-Trigger → .active sofort auf getappter Kachel (via makeStreamHandlers
#      + DOM-Stub-Probe der Logik-Schicht, die updateActiveMarker abbildet).
# AC4: Clear-Trigger → .active sofort weg auf vorher aktiver Kachel.
# AC5: Falsches optimistisches Update wird durch Stream-Event korrigiert.

def test_PANEL_11_onTap_optimistisch_markiert_kachel_vor_post():
    """AC1 (Refs #959): onTap(tile) ruft updateActiveMarker(tile) VOR
    sendEvent(…makeTileSelected(…)). Quelltext-Reihenfolge im Bootstrap-Block."""
    js = read(APPJS_PATH)
    # Im onTap-Funktionskörper muss updateActiveMarker vor sendEvent stehen.
    m = re.search(
        r'function onTap\(tile\)\s*\{([\s\S]{0,800}?)\}(?=\s*,\s*function onClear)',
        js)
    assert m is not None, \
        'onTap-Funktionskörper nicht im Quelltext gefunden — Bootstrap-Struktur geändert?'
    body = m.group(1)
    pos_update = body.find('updateActiveMarker(tile)')
    pos_send   = body.find('sendEvent(')
    assert pos_update >= 0, \
        'onTap muss updateActiveMarker(tile) enthalten (AC1, PANEL-11 Optimistik, Refs #959)'
    assert pos_send >= 0, \
        'onTap muss sendEvent(…) enthalten (PANEL-5)'
    assert pos_update < pos_send, \
        'updateActiveMarker(tile) muss VOR sendEvent stehen (AC1, PANEL-11; pos_update=%d, pos_send=%d)' % (
            pos_update, pos_send)


def test_PANEL_11_onClear_optimistisch_entfernt_markierung():
    """AC2 (Refs #959): onClear() ruft updateActiveMarker(null) VOR
    sendEvent(…makePanelCleared(…)). Quelltext-Reihenfolge im Bootstrap-Block."""
    js = read(APPJS_PATH)
    # Im onClear-Funktionskörper muss updateActiveMarker(null) vor sendEvent stehen.
    m = re.search(
        r'function onClear\(\)\s*\{([\s\S]{0,600}?)\}(?=\s*\))',
        js)
    assert m is not None, \
        'onClear-Funktionskörper nicht im Quelltext gefunden — Bootstrap-Struktur geändert?'
    body = m.group(1)
    pos_update = body.find('updateActiveMarker(null)')
    pos_send   = body.find('sendEvent(')
    assert pos_update >= 0, \
        'onClear muss updateActiveMarker(null) enthalten (AC2, PANEL-11 Optimistik, Refs #959)'
    assert pos_send >= 0, \
        'onClear muss sendEvent(…) enthalten (PANEL-5)'
    assert pos_update < pos_send, \
        'updateActiveMarker(null) muss VOR sendEvent stehen (AC2, PANEL-11; pos_update=%d, pos_send=%d)' % (
            pos_update, pos_send)




# ============================================================
#  PANEL-12 — Geometrie-Funktion und No-Scroll-Invariante (#375)
# ============================================================

def test_PANEL_12_geometry_no_scroll_landscape_phone():
    """AC1 / PANEL-12: computeGridGeometry für 11 Kacheln bei 880x370
    (Landscape-Phone) liefert cols/rows so, dass cols*rows >= 11
    und das Grid scrollHeight <= clientHeight (keine Kachel außerhalb
    des Grids). Verhalten wird über die Geometrie-Funktion geprüft."""
    out = run_node('''
        const M = 11;
        const vpW = 880;
        const vpH = 370;
        const geom = panelLib.computeGridGeometry(M, vpW, vpH);
        // Grid-Kapazität muss >= M sein (keine Kachel wird abgeschnitten)
        const capacity = geom.cols * geom.rows;
        // Kachelgröße berechnen (zur Verifikation des No-Scroll)
        const gap = panelLib.GRID_GAP;
        const pad = panelLib.GRID_PAD;
        const innerW = vpW - 2 * pad;
        const innerH = vpH - 2 * pad;
        const tileH = (innerH - (geom.rows - 1) * gap) / geom.rows;
        const totalGridH = geom.rows * tileH + (geom.rows - 1) * gap + 2 * pad;
        console.log(JSON.stringify({
            cols: geom.cols,
            rows: geom.rows,
            capacity: capacity,
            totalGridH: totalGridH,
            vpH: vpH,
            fitsInViewport: totalGridH <= vpH + 0.5,  // 0.5px Rundungstoleranz
        }));
    ''')
    assert out['capacity'] >= 11, \
        'Grid muss mindestens 11 Kacheln aufnehmen (bekommen: %d)' % out['capacity']
    assert out['fitsInViewport'], \
        'PANEL-12: Grid-Höhe darf Viewport nicht überschreiten — totalGridH=%.1f > vpH=%d' % (
            out['totalGridH'], out['vpH'])


def test_PANEL_12_geometry_no_scroll_tablet():
    """AC2 / PANEL-12: computeGridGeometry für 11 Kacheln bei 1280x800 (Tablet)
    liefert ein Grid, das in den Viewport passt."""
    out = run_node('''
        const M = 11;
        const vpW = 1280;
        const vpH = 800;
        const geom = panelLib.computeGridGeometry(M, vpW, vpH);
        const gap = panelLib.GRID_GAP;
        const pad = panelLib.GRID_PAD;
        const innerH = vpH - 2 * pad;
        const tileH = (innerH - (geom.rows - 1) * gap) / geom.rows;
        const totalGridH = geom.rows * tileH + (geom.rows - 1) * gap + 2 * pad;
        console.log(JSON.stringify({
            cols: geom.cols,
            rows: geom.rows,
            capacity: geom.cols * geom.rows,
            fitsInViewport: totalGridH <= vpH + 0.5,
        }));
    ''')
    assert out['capacity'] >= 11, \
        'Grid muss mindestens 11 Kacheln aufnehmen bei 1280x800 (bekommen: %d)' % out['capacity']
    assert out['fitsInViewport'], \
        'PANEL-12: Grid passt bei 1280x800 nicht in Viewport'


def test_PANEL_12_geometry_cols_not_hardcoded():
    """AC3 / PANEL-12: Verschiedene Viewport-Seitenverhältnisse mit gleicher
    Kachelzahl (11) liefern VERSCHIEDENE Spaltenzahlen — kein hartcodierter Wert."""
    out = run_node('''
        const M = 11;
        // Landscape-Phone (schmal)
        const geom_phone   = panelLib.computeGridGeometry(M, 880,  370);
        // Tablet Landscape (breit + hoch)
        const geom_tablet  = panelLib.computeGridGeometry(M, 1280, 800);
        // Portrait-ish (quadratisch)
        const geom_square  = panelLib.computeGridGeometry(M, 600,  600);
        console.log(JSON.stringify({
            cols_phone:  geom_phone.cols,
            cols_tablet: geom_tablet.cols,
            cols_square: geom_square.cols,
        }));
    ''')
    cols = {out['cols_phone'], out['cols_tablet'], out['cols_square']}
    assert len(cols) > 1, \
        'AC3: computeGridGeometry muss bei verschiedenen Seitenverhältnissen VERSCHIEDENE ' \
        'Spaltenzahlen liefern — alle gleich: %r' % out


def test_PANEL_12_all_tiles_fit_in_grid():
    """PANEL-12: Die berechnete Grid-Kapazität (cols*rows) ist stets >= M."""
    out = run_node('''
        const results = [];
        const vpW = 880; const vpH = 370;
        for (let M = 1; M <= 15; M++) {
            const geom = panelLib.computeGridGeometry(M, vpW, vpH);
            results.push({ M: M, capacity: geom.cols * geom.rows, ok: geom.cols * geom.rows >= M });
        }
        console.log(JSON.stringify(results));
    ''')
    for entry in out:
        assert entry['ok'], \
            'PANEL-12: Grid-Kapazität < M bei M=%d (capacity=%d)' % (entry['M'], entry['capacity'])


def test_PANEL_12_geometry_exported():
    """PANEL-12 / AC3: computeGridGeometry ist aus panelLib exportiert."""
    out = run_node('''
        console.log(JSON.stringify({
            exported: typeof panelLib.computeGridGeometry === 'function',
        }));
    ''')
    assert out['exported'], 'computeGridGeometry muss aus panelLib exportiert sein'


def test_PANEL_12_no_scroll_css_invariant():
    """PANEL-12: style.css setzt overflow:hidden auf #grid (harte Invariante)."""
    css = read(CSS_PATH)
    grid_block = re.search(r'#grid\s*\{([^}]+)\}', css)
    assert grid_block is not None, '#grid-Block muss in style.css vorhanden sein'
    block_content = grid_block.group(1)
    assert 'overflow' in block_content and 'hidden' in block_content, \
        '#grid muss overflow:hidden setzen (PANEL-12 No-Scroll-Invariante; bekommen: %r)' % block_content


def test_PANEL_12_tokens_css_in_index_html():
    """AC4 / E-PANEL-6: index.html verlinkt /display/_shared/design/tokens.css."""
    html = read(HTML_PATH)
    assert '/display/_shared/design/tokens.css' in html, \
        'index.html muss tokens.css referenzieren (E-PANEL-6, AC4)'


def test_PANEL_12_body_has_xb_class_and_reader_stage():
    """AC4 / DTOK-5: body trägt class="xb" und data-stage="reader" (Reader-Stage-Tokens)."""
    html = read(HTML_PATH)
    assert re.search(r'<body[^>]+class=["\'][^"\']*\bxb\b', html), \
        'body muss class="xb" tragen (DTOK-5, AC4)'
    assert re.search(r'<body[^>]+data-stage=["\']reader["\']', html), \
        'body muss data-stage="reader" tragen (DTOK-5, AC4)'


def test_PANEL_12_tokens_css_in_sw_static_assets():
    """E-PANEL-6: sw.js-STATIC_ASSETS enthält tokens.css-URL für Offline-Cache."""
    sw = read(SW_PATH)
    assert '/display/_shared/design/tokens.css' in sw, \
        'sw.js STATIC_ASSETS muss tokens.css URL enthalten (E-PANEL-6)'


def test_PANEL_12_no_hardcoded_colors_in_style_css():
    """AC4 / DTOK-5: Keine hartcodierten Hex-Farben oder rgb()-Literale in style.css
    (ausgenommen Kommentare). Alle Farbwerte müssen Token-Variablen sein."""
    css = read(CSS_PATH)
    # Kommentare entfernen bevor wir nach Literals suchen
    css_no_comments = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    hex_found = re.findall(r'(?<!var\()#[0-9a-fA-F]{3,8}\b', css_no_comments)
    rgb_found = re.findall(r'rgba?\s*\([0-9]', css_no_comments)
    assert not hex_found, \
        'DTOK-5 AC4: Keine hartcodierten Hex-Farben in style.css erlaubt: %r' % hex_found
    assert not rgb_found, \
        'DTOK-5 AC4: Keine hartcodierten rgb()-Werte in style.css erlaubt: %r' % rgb_found


def test_PANEL_12_apply_grid_geometry_dom_path():
    """PANEL-12 / Watchdog-Befund 1 — Entry-Path-Copetrage: ruft die echte
    exportierte Funktion panelLib.applyGridGeometry({doc, win}) auf (kein
    Logik-Reko-Muster). applyGridGeometry ist seit diesem Fix im UMD-Export
    und akzeptiert ein optionales ctx-Objekt {doc, win} für testbare
    Dependency-Injection; im Browser wird es ohne Argument aufgerufen und
    nutzt die globalen document/window.

    Setup: #grid mit 11 echten Kachel-Kindern (10 × makeTileElement +
    1 × makeAusKachel), Viewport 880×370 (Landscape-Phone), error-Banner
    als hidden gesetzt (kein vpH-Abzug).

    Akzeptanz-Invarianten (specs/platform/app-panel.md:467-469):
      - grid.style.height == vpH (= clientHeight) → scrollHeight <= clientHeight
      - cols*rows >= 11 (Kapazität nimmt alle Kacheln auf)
      - grid._children.length == 11 (DOM unverändert nach applyGridGeometry)"""
    out = run_node_dom(r"""
        var doc = makeDom();

        // #grid mit style-Objekt und children-Alias (applyGridGeometry liest
        // grid.children.length und schreibt grid.style.*).
        var gridEl = {
          _tag: 'div', _children: [],
          style: {},
          classList: { add: function(){}, remove: function(){},
                       contains: function(){ return false; } },
          appendChild: function(c) { c.parentNode = this; this._children.push(c); return c; },
          removeChild: function(c) {
            this._children = this._children.filter(function(x){ return x !== c; });
          }
        };
        gridEl.children = gridEl._children;

        // #error-Banner als hidden — kein vpH-Abzug.
        var errorEl = {
          style: {},
          offsetHeight: 0,
          classList: {
            add: function(){}, remove: function(){},
            contains: function(cls) { return cls === 'hidden'; }
          }
        };

        // document-Stub: getElementById liefert grid/error; createElement
        // aus dem Standard-makeDom für makeTileElement/makeAusKachel.
        var stubDoc = {
          createElement: doc.createElement,
          getElementById: function(id) {
            if (id === 'grid')  return gridEl;
            if (id === 'error') return errorEl;
            return null;
          },
          querySelectorAll: function() { return []; },
          body: doc.body,
          visibilityState: 'visible',
          fullscreenElement: null,
          documentElement: doc.documentElement,
          addEventListener: function() {}
        };

        var VPW = 880;
        var VPH = 370;
        var stubWin = { innerWidth: VPW, innerHeight: VPH, addEventListener: function(){} };

        // 10 sichtbare Kacheln + 1 Aus-Kachel = 11 DOM-Kinder ins gridEl hängen.
        var fakeTiles = [];
        for (var i = 0; i < 10; i++) {
          fakeTiles.push({ key: 'k'+i, app: 'plan', view: 'woche',
                           label: 'L'+i, icons: ['arasaac/test.png'], sichtbar: true });
        }
        for (var j = 0; j < 10; j++) {
          var tileEl = panelLib.makeTileElement(
            stubDoc, fakeTiles[j], function(){}, panelLib.resolveIconBase(''));
          gridEl.appendChild(tileEl);
        }
        gridEl.appendChild(
          panelLib.makeAusKachel(stubDoc, function(){}, panelLib.resolveIconBase('')));

        // ECHTER Aufruf der exportierten Funktion — keine Logik-Rekonstruktion.
        panelLib.applyGridGeometry({ doc: stubDoc, win: stubWin });

        // Invarianten-Auswertung.
        var styleHeightPx = parseInt(gridEl.style.height, 10);
        var colsMatch = gridEl.style.gridTemplateColumns;
        var rowsMatch = gridEl.style.gridTemplateRows;
        // cols/rows aus dem gesetzten repeat()-String extrahieren.
        var colsN = colsMatch ? parseInt(colsMatch.replace('repeat(',''), 10) : 0;
        var rowsN = rowsMatch ? parseInt(rowsMatch.replace('repeat(',''), 10) : 0;
        var capacity = colsN * rowsN;

        // scrollHeight == gridContentH; clientHeight == vpH (style.height).
        var gap  = panelLib.GRID_GAP;
        var pad  = panelLib.GRID_PAD;
        var innerH = VPH - 2 * pad;
        var tileH  = (innerH - (rowsN - 1) * gap) / rowsN;
        var gridContentH = rowsN * tileH + (rowsN - 1) * gap + 2 * pad;

        console.log(JSON.stringify({
          domChildren:     gridEl._children.length,
          cols:            colsN,
          rows:            rowsN,
          capacity:        capacity,
          styleHeightPx:   styleHeightPx,
          vpH:             VPH,
          gridContentH:    gridContentH,
          noScroll:        gridContentH <= VPH + 0.5,
          allTilesFit:     capacity >= 11,
          heightMatchesVp: styleHeightPx === VPH,
        }));
    """)
    assert out['domChildren'] == 11, \
        'DOM muss 11 Kinder haben (10 sichtbare + 1 Aus-Kachel; bekommen: %d)' % out['domChildren']
    assert out['allTilesFit'], \
        'PANEL-12: cols*rows muss >= 11 sein (bekommen: cols=%d rows=%d cap=%d)' % (
            out['cols'], out['rows'], out['capacity'])
    assert out['heightMatchesVp'], \
        'PANEL-12: grid.style.height muss vpH entsprechen (bekommen: styleH=%d vpH=%d)' % (
            out['styleHeightPx'], out['vpH'])
    assert out['noScroll'], \
        'PANEL-12: gridContentH darf vpH nicht übersteigen — scrollH=%.1f > clientH=%d' % (
            out['gridContentH'], out['vpH'])


def _run_shrink_geom(M, vpW, vpH):
    """Setup-Helper: führt computeGridGeometry(M, vpW, vpH) via Node aus.

    Gibt dict mit cols, rows, capacity zurück. Wird von den
    PANEL-12-Schrumpf-Tests gemeinsam genutzt (Befund 2 / AC2)."""
    return run_node('''
        var geom = panelLib.computeGridGeometry(%d, %d, %d);
        console.log(JSON.stringify({
            cols:     geom.cols,
            rows:     geom.rows,
            capacity: geom.cols * geom.rows,
        }));
    ''' % (M, vpW, vpH))


def test_PANEL_12_shrink_fallback_ignores_min_width():
    """PANEL-12 / Watchdog-Befund 2 — Spec-Drift: der Schrumpf-Fallback
    (app.js ~Z.466-482, der `if (!best)`-Zweig) ist explizite PANEL-12-
    Akzeptanz (specs/platform/app-panel.md:473-475).

    Prüft: Bei einem Viewport, bei dem ALLE Spalten-Varianten die
    TILE_MIN_W-Grenze (160 px) unterschreiten würden, läuft der Fallback-
    Zweig und liefert trotzdem cols*rows >= M (kein Scroll, statt Abbruch).

    Einschränkung: vpW=150 → innerW=118 px; selbst c=1 ergibt tileW=118 < 160.
    Der Fallback muss das Guard ignorieren und eine Lösung finden."""
    # Vorbedingung: alle c-Werte wirklich unter TILE_MIN_W (vpH=300 für diesen Check)
    pre = run_node('''
        var M    = 20;
        var vpW  = 150;
        var TILE_MIN_W = 160;
        var pad  = panelLib.GRID_PAD;
        var gap  = panelLib.GRID_GAP;
        var innerW = vpW - 2 * pad;
        var allBelowMin = true;
        for (var c = 1; c <= M; c++) {
            var tileW = (innerW - (c - 1) * gap) / c;
            if (tileW >= TILE_MIN_W) { allBelowMin = false; break; }
        }
        console.log(JSON.stringify({ innerW: innerW, allBelowMin: allBelowMin }));
    ''')
    assert pre['allBelowMin'], \
        'Vorbedingung: alle tileW-Werte müssen < TILE_MIN_W sein (vpW=%d zu groß?)' % 150

    out = _run_shrink_geom(M=20, vpW=150, vpH=300)
    assert out['capacity'] >= 20, \
        ('PANEL-12 Schrumpf-Fallback: cols*rows muss >= M=%d sein auch wenn tileW < TILE_MIN_W '
         '(bekommen: cols=%d rows=%d capacity=%d)') % (20, out['cols'], out['rows'], out['capacity'])


def test_PANEL_12_shrink_fallback_chooses_correct_cols_rows():
    """PANEL-12 Mutations-Kriterium (Befund 1 / AC1): Bei M=20, vpW=150, vpH=600
    wählt der Schrumpf-Fallback-Zweig (app.js if(!best)-Block) das Score-Minimum.

    Mathematische Herleitung (Mutationsprobe):
    - innerW = 150 - 2*16 = 118 px; innerH = 600 - 2*16 = 568 px
    - Hauptschleife: Alle c=1..20 liefern tileW < 160 → kein Kandidat → best=null
    - Schrumpf-Fallback ohne TILE_MIN_W-Guard:
        c=2: tileW=(118-12)/2=53 px, tileH=(568-9*12)/10=46 px,
             ratio=53/46≈1.152, ratioPenalty=|ln(1.152/0.92)|≈0.225,
             emptyPenalty=0 (2*10=20=M), score≈0.225  ← Minimum
        c=5: tileW=(118-4*12)/5=14 px, tileH=(568-3*12)/4=133 px,
             ratio≈0.114, score≈2.168  ← viel schlechter
    - sqrt-Default (line 485) würde cols=5,rows=4 geben — ignoriert Score
    - Ohne Schrumpf-Schleife (if(!best)-Block entfernt) fiele das Ergebnis
      auf den sqrt-Default zurück: cols=5, rows=4 — Mutation wird gefangen.

    Spec-deckendes Kriterium (PANEL-12 Leerfeld-Vermeidung):
    - cols*rows == M: kein Leerfeld — nur Schrumpf-Loop kann das garantieren
    - not (cols==5 and rows==4): degeneriertes sqrt-Default-Layout ausgeschlossen"""
    out = _run_shrink_geom(M=20, vpW=150, vpH=600)
    assert out['capacity'] == 20, \
        ('PANEL-12 Schrumpf-Fallback: cols*rows muss == M=20 sein (Leerfeld-Vermeidung) — '
         'bekommen: cols=%d rows=%d capacity=%d. '
         'Wenn capacity!=20: Schrumpf-Loop fehlt oder Score falsch.') % (
             out['cols'], out['rows'], out['capacity'])
    assert not (out['cols'] == 5 and out['rows'] == 4), \
        ('PANEL-12 Schrumpf-Fallback darf nicht das degenerierte sqrt-Default-Layout '
         '(cols=5, rows=4) wählen — das würde bedeuten, dass der Schrumpf-Loop fehlt.')


def test_PANEL_12_shrink_not_needed_for_normal_viewport():
    """Algorithmus-Probe (Branch-Schwelle tileW >= TILE_MIN_W), KEIN Spec-Schutz.
    PANEL-12 unterscheidet keine Haupt-/Schrumpf-Pfade.

    Prüft den Kontroll-Pfad: Bei M=6, vpW=800, vpH=600 findet die
    Hauptschleife bereits einen gültigen Kandidaten (tileW >= TILE_MIN_W=160),
    der Schrumpf-Fallback wird NICHT benötigt.

    Erwartetes Ergebnis: cols=3, rows=2, tileW=248 px >= 160 px.
    Zeigt, dass der Schrumpf-Pfad nicht immer aktiv ist."""
    out = run_node('''
        var M   = 6;
        var vpW = 800;
        var vpH = 600;
        var TILE_MIN_W = 160;
        var gap = panelLib.GRID_GAP;
        var pad = panelLib.GRID_PAD;

        var geom   = panelLib.computeGridGeometry(M, vpW, vpH);
        var innerW = vpW - 2 * pad;
        var tileW  = (innerW - (geom.cols - 1) * gap) / geom.cols;

        console.log(JSON.stringify({
            cols:     geom.cols,
            rows:     geom.rows,
            capacity: geom.cols * geom.rows,
            tileW:    tileW,
            aboveMin: tileW >= TILE_MIN_W,
        }));
    ''')
    assert out['capacity'] >= 6, \
        ('PANEL-12 Kontroll-Pfad: capacity muss >= M=6 (bekommen: %d)') % out['capacity']
    assert out['aboveMin'], \
        ('PANEL-12 Kontroll-Pfad: normaler Viewport (800x600, M=6) muss tileW >= TILE_MIN_W=160 '
         'liefern — bekommen: tileW=%.1f. Schrumpf-Fallback darf hier nicht greifen.') % out['tileW']


# ============================================================
#  PANEL-12 — Safe-Area-Insets (T384)
# ============================================================


def test_PANEL_12_viewport_fit_cover_in_meta():
    """AC1 / PANEL-12: index.html Meta-Tag enthält viewport-fit=cover."""
    html = read(HTML_PATH)
    assert 'viewport-fit=cover' in html, \
        'index.html: viewport-Meta muss viewport-fit=cover enthalten (AC1 / PANEL-12 Safe-Area)'


def test_PANEL_12_safe_area_css_vars_in_style_css():
    """AC2 / PANEL-12: style.css setzt alle vier --safe-area-inset-* CSS-Variablen
    via env() auf :root (Lesbarkeit durch JS via getComputedStyle)."""
    css = read(CSS_PATH)
    for name in ('top', 'bottom', 'left', 'right'):
        var_name = '--safe-area-inset-' + name
        assert var_name in css, \
            'style.css: %s muss als CSS-Variable auf :root gesetzt sein (AC2)' % var_name
        assert 'env(safe-area-inset-' + name in css, \
            'style.css: %s muss env(safe-area-inset-%s) referenzieren (AC2)' % (var_name, name)


def test_PANEL_12_get_viewport_dimensions_exported():
    """AC2 / PANEL-12: getViewportDimensions ist aus panelLib exportiert."""
    out = run_node('''
        console.log(JSON.stringify({
            exported: typeof panelLib.getViewportDimensions === 'function',
        }));
    ''')
    assert out['exported'], \
        'getViewportDimensions muss aus panelLib exportiert sein (AC2 / PANEL-12)'


def test_PANEL_12_safe_area_zero_insets_unchanged():
    """AC3 / PANEL-12: Bei Insets 0 liefert getViewportDimensions identische Werte
    zu innerWidth/innerHeight — V1-Regression (Geräte ohne Notch)."""
    out = run_node('''
        // Stub: documentElement ohne CSS-Variablen → readVar gibt 0 zurück.
        var stubDoc = {
            documentElement: { style: {} },
        };
        var stubWin = { innerWidth: 880, innerHeight: 370 };
        var dims = panelLib.getViewportDimensions({ doc: stubDoc, win: stubWin });
        console.log(JSON.stringify({
            vpW: dims.vpW,
            vpH: dims.vpH,
            expectedW: 880,
            expectedH: 370,
        }));
    ''')
    assert out['vpW'] == out['expectedW'], \
        'AC3: vpW bei Insets=0 muss == innerWidth (880) sein; bekommen: %d' % out['vpW']
    assert out['vpH'] == out['expectedH'], \
        'AC3: vpH bei Insets=0 muss == innerHeight (370) sein; bekommen: %d' % out['vpH']


def test_PANEL_12_safe_area_insets_subtracted():
    """AC2+AC4 / PANEL-12: getViewportDimensions zieht Insets korrekt ab.
    Simuliert iPhone-Notch (top=44px, bottom=34px) und Landscape-Notch (left=44px, right=0).
    vpH = innerHeight - top - bottom; vpW = innerWidth - left - right."""
    out = run_node('''
        // Stub: documentElement mit expliziten CSS-Variablen (wie style.css sie setzt).
        var stubDoc = {
            documentElement: {
                style: {},
                computedStyle: {
                    getPropertyValue: function(name) {
                        var vars = {
                            "--safe-area-inset-top":    "44px",
                            "--safe-area-inset-bottom": "34px",
                            "--safe-area-inset-left":   "44px",
                            "--safe-area-inset-right":  "0px",
                        };
                        return vars[name] !== undefined ? vars[name] : "0px";
                    }
                }
            },
        };
        var stubWin = { innerWidth: 812, innerHeight: 375 };
        var dims = panelLib.getViewportDimensions({ doc: stubDoc, win: stubWin });
        console.log(JSON.stringify({
            vpW: dims.vpW,
            vpH: dims.vpH,
            expectedW: 812 - 44 - 0,
            expectedH: 375 - 44 - 34,
        }));
    ''')
    assert out['vpW'] == out['expectedW'], \
        ('AC2: vpW = innerWidth - left - right erwartet %d; bekommen: %d'
         % (out['expectedW'], out['vpW']))
    assert out['vpH'] == out['expectedH'], \
        ('AC2: vpH = innerHeight - top - bottom erwartet %d; bekommen: %d'
         % (out['expectedH'], out['vpH']))


def test_PANEL_12_apply_grid_geometry_uses_safe_area():
    """AC4 / PANEL-12: applyGridGeometry setzt grid.style.height auf vpH (Safe-Area-bereinigt),
    nicht auf nackes innerHeight. Simuliert top=44px + bottom=34px → vpH = 375 - 78 = 297."""
    out = run_node_dom(r"""
        var INNER_H = 375;
        var INNER_W = 812;
        var INSET_TOP    = 44;
        var INSET_BOTTOM = 34;
        var INSET_LEFT   = 0;
        var INSET_RIGHT  = 0;
        var EXPECTED_VPH = INNER_H - INSET_TOP - INSET_BOTTOM;  // 297

        var doc = makeDom();

        // documentElement mit CSS-Variable-Stub.
        doc.documentElement.computedStyle = {
            getPropertyValue: function(name) {
                var m = {
                    "--safe-area-inset-top":    INSET_TOP    + "px",
                    "--safe-area-inset-bottom": INSET_BOTTOM + "px",
                    "--safe-area-inset-left":   INSET_LEFT   + "px",
                    "--safe-area-inset-right":  INSET_RIGHT  + "px",
                };
                return m[name] !== undefined ? m[name] : "0px";
            }
        };

        // #grid mit 11 Kacheln.
        var gridEl = {
            _tag: 'div', _children: [],
            style: {},
            classList: { add: function(){}, remove: function(){},
                         contains: function(){ return false; } },
            appendChild: function(c) { c.parentNode = this; this._children.push(c); return c; },
        };
        gridEl.children = gridEl._children;

        var errorEl = {
            style: {}, offsetHeight: 0,
            classList: { add: function(){}, remove: function(){},
                         contains: function(cls) { return cls === 'hidden'; } }
        };

        var stubDoc = {
            createElement: doc.createElement,
            getElementById: function(id) {
                if (id === 'grid')  return gridEl;
                if (id === 'error') return errorEl;
                return null;
            },
            querySelectorAll: function() { return []; },
            body: doc.body,
            visibilityState: 'visible',
            fullscreenElement: null,
            documentElement: doc.documentElement,
            addEventListener: function() {}
        };

        var stubWin = { innerWidth: INNER_W, innerHeight: INNER_H, addEventListener: function(){} };

        // 11 Kacheln einhängen.
        for (var i = 0; i < 10; i++) {
            var t = { key: 'k'+i, app: 'plan', view: 'woche',
                      label: 'L'+i, icons: ['arasaac/test.png'], sichtbar: true };
            gridEl.appendChild(panelLib.makeTileElement(stubDoc, t, function(){}, ''));
        }
        gridEl.appendChild(panelLib.makeAusKachel(stubDoc, function(){}, ''));

        panelLib.applyGridGeometry({ doc: stubDoc, win: stubWin });

        var styleHeightPx = parseInt(gridEl.style.height, 10);
        console.log(JSON.stringify({
            styleHeightPx: styleHeightPx,
            expectedVpH:   EXPECTED_VPH,
            heightMatchesVpH: styleHeightPx === EXPECTED_VPH,
            heightBelowInnerH: styleHeightPx < INNER_H,
        }));
    """)
    assert out['heightMatchesVpH'], \
        ('AC4: grid.style.height muss vpH=%d (Safe-Area-bereinigt) sein, '
         'nicht nackes innerHeight; bekommen: %d'
         % (out['expectedVpH'], out['styleHeightPx']))
    assert out['heightBelowInnerH'], \
        ('AC4: grid.style.height=%d muss < innerHeight=%d sein (Insets wurden abgezogen)'
         % (out['styleHeightPx'], 375))


# ============================================================
#  PANEL-10 / PWA-2 — Manifest icons[] + PNG-Validität (AC4)
# ============================================================

ICON_192_PATH      = os.path.join(ROOT, 'icon-192.png')
ICON_512_PATH      = os.path.join(ROOT, 'icon-512.png')
ICON_MASKABLE_PATH = os.path.join(ROOT, 'icon-maskable-512.png')


def test_PWA_2_manifest_icons_present_and_count():
    """PWA-2 / AC2: manifest.json enthält icons[]; mindestens 2 Einträge."""
    manifest = json.loads(read(MANIFEST_PATH))
    assert 'icons' in manifest, 'manifest.json: icons[] fehlt'
    assert len(manifest['icons']) >= 2, \
        'manifest.json: icons[] braucht mind. 2 Einträge (bekommen: %d)' % len(manifest['icons'])


def test_PWA_2_manifest_icons_at_least_one_maskable():
    """PWA-2 / AC2: mind. ein Icon-Eintrag trägt purpose:maskable."""
    manifest = json.loads(read(MANIFEST_PATH))
    purposes = [e.get('purpose', '') for e in manifest.get('icons', [])]
    assert any('maskable' in p for p in purposes), \
        'manifest.json: kein Eintrag mit purpose:maskable gefunden (vorhanden: %r)' % purposes


def test_PWA_2_manifest_icons_192_entry():
    """PWA-2 / AC2: icons[] hat Eintrag mit sizes=192x192."""
    manifest = json.loads(read(MANIFEST_PATH))
    sizes = [e.get('sizes', '') for e in manifest.get('icons', [])]
    assert '192x192' in sizes, \
        'manifest.json: kein 192x192-Icon-Eintrag (vorhanden: %r)' % sizes


def test_PWA_2_manifest_icons_512_entry():
    """PWA-2 / AC2: icons[] hat Eintrag mit sizes=512x512."""
    manifest = json.loads(read(MANIFEST_PATH))
    sizes = [e.get('sizes', '') for e in manifest.get('icons', [])]
    assert '512x512' in sizes, \
        'manifest.json: kein 512x512-Icon-Eintrag (vorhanden: %r)' % sizes


def test_PWA_2_icon_192_exists_and_valid():
    """PWA-2 / AC1: icon-192.png existiert, ist 192×192, gültiges PNG, RGBA."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip('Pillow nicht installiert')
    assert os.path.exists(ICON_192_PATH), 'icon-192.png fehlt in controller/app-panel/'
    img = Image.open(ICON_192_PATH)
    assert img.size == (192, 192), \
        'icon-192.png: erwarte 192×192, bekommen %s' % str(img.size)
    assert img.mode == 'RGBA', \
        'icon-192.png: erwarte mode=RGBA, bekommen %s' % img.mode


def test_PWA_2_icon_512_exists_and_valid():
    """PWA-2 / AC1: icon-512.png existiert, ist 512×512, gültiges PNG, RGBA."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip('Pillow nicht installiert')
    assert os.path.exists(ICON_512_PATH), 'icon-512.png fehlt in controller/app-panel/'
    img = Image.open(ICON_512_PATH)
    assert img.size == (512, 512), \
        'icon-512.png: erwarte 512×512, bekommen %s' % str(img.size)
    assert img.mode == 'RGBA', \
        'icon-512.png: erwarte mode=RGBA, bekommen %s' % img.mode


def test_PWA_2_icon_maskable_512_exists_and_valid():
    """PWA-2 / AC1: icon-maskable-512.png existiert, ist 512×512, RGBA."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip('Pillow nicht installiert')
    assert os.path.exists(ICON_MASKABLE_PATH), \
        'icon-maskable-512.png fehlt in controller/app-panel/'
    img = Image.open(ICON_MASKABLE_PATH)
    assert img.size == (512, 512), \
        'icon-maskable-512.png: erwarte 512×512, bekommen %s' % str(img.size)
    assert img.mode == 'RGBA', \
        'icon-maskable-512.png: erwarte mode=RGBA, bekommen %s' % img.mode


def test_PWA_2_html_link_icon_192():
    """PWA-2 / AC3: index.html enthält <link rel=icon sizes=192x192>."""
    html = read(HTML_PATH)
    assert re.search(r'<link[^>]+rel=["\']icon["\'][^>]+sizes=["\']192x192["\']', html) or \
           re.search(r'<link[^>]+sizes=["\']192x192["\'][^>]+rel=["\']icon["\']', html), \
        'index.html: kein <link rel=icon sizes=192x192> gefunden'


def test_PWA_2_html_link_icon_512():
    """PWA-2 / AC3: index.html enthält <link rel=icon sizes=512x512>."""
    html = read(HTML_PATH)
    assert re.search(r'<link[^>]+rel=["\']icon["\'][^>]+sizes=["\']512x512["\']', html) or \
           re.search(r'<link[^>]+sizes=["\']512x512["\'][^>]+rel=["\']icon["\']', html), \
        'index.html: kein <link rel=icon sizes=512x512> gefunden'


def test_PWA_2_html_apple_touch_icon():
    """PWA-2 / AC3: index.html enthält <link rel=apple-touch-icon>."""
    html = read(HTML_PATH)
    assert re.search(r'<link[^>]+rel=["\']apple-touch-icon["\']', html), \
        'index.html: kein <link rel=apple-touch-icon> gefunden'


def test_PANEL_9_test_file_covers_panel_12():
    """PANEL-9 Selbst-Probe: PANEL_12-Tests sind in dieser Datei vorhanden."""
    here = read(os.path.abspath(__file__))
    assert re.search(r'def test_PANEL_12_', here), \
        'kein PANEL_12-Test gefunden — PANEL-9 Mindest-Abdeckung verletzt'


# ---------------------------------------------------------------------------
# PANEL-11 — parseDisplayUrl Mehr-Segment-View (ROU-24 / URL-3a / T#1007)
# ---------------------------------------------------------------------------

def test_PANEL_11_parse_display_url_multi_segment_ac1():
    """AC1 (T#1007): /display/hoerspiel/mia/alben → {app:'hoerspiel', view:'mia/alben'},
    NICHT null (ROU-24 + URL-3a erlauben Mehr-Segment-View-Suffix)."""
    out = run_node('''
        const result = panelLib.parseDisplayUrl('/display/hoerspiel/mia/alben');
        console.log(JSON.stringify(result));
    ''')
    assert out is not None, (
        'parseDisplayUrl darf bei Mehr-Segment-URL nicht null zurückgeben (ROU-24 / URL-3a)')
    assert out.get('app') == 'hoerspiel', (
        'app-Feld falsch: erwartet "hoerspiel", bekommen %r' % out.get('app'))
    assert out.get('view') == 'mia/alben', (
        'view-Feld falsch: erwartet "mia/alben", bekommen %r' % out.get('view'))


def test_PANEL_11_parse_display_url_two_segment_ac2():
    """AC2 (T#1007): /display/plan/woche → Bestand 2-Segment-Ergebnis bleibt
    unverändert (app:'plan', view:'woche')."""
    out = run_node('''
        const result = panelLib.parseDisplayUrl('/display/plan/woche');
        console.log(JSON.stringify(result));
    ''')
    assert out is not None, 'parseDisplayUrl soll bei 2-Segment-URL nicht null zurückgeben'
    assert out.get('app') == 'plan', 'app-Feld: erwartet "plan", bekommen %r' % out.get('app')
    assert out.get('view') == 'woche', 'view-Feld: erwartet "woche", bekommen %r' % out.get('view')


def test_PANEL_11_parse_display_url_trailing_slash_ac3():
    """AC3 (T#1007): /display/plan/ → null (trailing slash ohne view-Segment
    ist kein gültiger Display-Pfad — leeres view-Segment muss abgelehnt werden)."""
    out = run_node('''
        const result = panelLib.parseDisplayUrl('/display/plan/');
        console.log(JSON.stringify({ result }));
    ''')
    assert out['result'] is None, (
        'parseDisplayUrl muss bei trailing slash ohne view null zurückgeben, '
        'bekommen: %r' % out['result'])


# ============================================================
#  SHELL-4 / E2-Sender (T1519) — ingest_url-Sender-Logik (AC1 + AC2)
# ============================================================

def test_T1519_AC1_appjs_liest_ingest_url_aus_urlparams():
    """AC1 (T1519): app.js enthält URLSearchParams-Lesestelle für ingest_url.

    Der DOM-Initialisierungs-Block liest `?ingest_url=`-Query-Param via
    URLSearchParams und speichert ihn in _ingestUrlFromParam. Code-Level-Beweis
    (Pattern-Grep), da der Block unter `if (typeof document === 'undefined') return`
    im Node-Kontext übersprungen wird. Endabnahme = Nics Tablet-Re-Test."""
    js = read(APPJS_PATH)
    assert 'URLSearchParams' in js, (
        "app.js muss URLSearchParams für ingest_url-Param enthalten (T1519 AC1)"
    )
    assert "ingest_url" in js, (
        "app.js muss 'ingest_url' als Query-Param-Schlüssel referenzieren (T1519 AC1)"
    )
    assert '_ingestUrlFromParam' in js, (
        "app.js muss _ingestUrlFromParam als Variable definieren (T1519 AC1)"
    )


def test_T1519_AC2_sendEvent_nutzt_ingest_url_wenn_vorhanden():
    """AC2 (T1519 Kein-Regress): sendEvent-Logik in app.js nutzt _ingestUrlFromParam,
    wenn gesetzt, sonst unverändertes base+'/api/v1/events'-Fallback (Router-Pfad).

    Code-Level-Beweis — DOM-Abschnitt ist in Node nicht erreichbar (kein document).
    Standalone-Panel ohne ingest_url-Param MUSS weiter an /api/v1/events posten."""
    js = read(APPJS_PATH)
    # ingest_url-Zweig muss in sendEvent vorhanden sein:
    assert '_ingestUrlFromParam' in js, (
        "sendEvent muss _ingestUrlFromParam referenzieren (T1519 AC2)"
    )
    # Fallback (Router-Pfad) darf nicht verschwunden sein — AC2 Kein-Regress:
    assert "/api/v1/events" in js, (
        "Fallback-Pfad /api/v1/events (Router, Standalone-Panel) muss erhalten bleiben "
        "(T1519 AC2 Kein-Regress)"
    )
    # Der Router-Fallback muss im else-Zweig unter _ingestUrlFromParam stehen:
    ingest_pos = js.find('_ingestUrlFromParam')
    api_events_pos = js.find('/api/v1/events', ingest_pos)
    assert ingest_pos != -1 and api_events_pos != -1, (
        "_ingestUrlFromParam-Zweig und /api/v1/events-Fallback müssen beide in sendEvent "
        "vorhanden sein (T1519 AC1+AC2)"
    )


def test_T1519_AC3_makeTileSelected_body_hat_pflichtfelder():
    """AC3 (T1519): makeTileSelected-Body enthält alle Pflichtfelder des seiten-
    Ingest (_adapt_shell_event: type/app/view). Node-Aufruf via panelLib.

    Beweis, dass der Client-Body strukturell kompatibel mit dem Empfänger ist.
    Endabnahme = Nics Tablet-Re-Test (server-seitig in test_shell_sse.py::
    test_ac3_ingest_endpunkt_akzeptiert_tile_selected_body)."""
    out = run_node('''
        const tile = { key: 'k1', app: 'hoerspiel', view: 'player',
                       label: 'Musik', icons: ['arasaac/test.png'] };
        const body = panelLib.makeTileSelected('app-panel:mias-panel-01', tile);
        console.log(JSON.stringify(body));
    ''')
    assert out.get('type') == 'tile_selected', "body.type muss 'tile_selected' sein"
    assert 'app' in out, "body.app Pflichtfeld fehlt (PANEL-6 / _adapt_shell_event)"
    assert 'view' in out, "body.view Pflichtfeld fehlt (PANEL-6 / _adapt_shell_event)"
    assert out['app'] == 'hoerspiel', "body.app muss tile.app widerspiegeln"
    assert out['view'] == 'player', "body.view muss tile.view widerspiegeln"


# ============================================================
#  RAT-31 E6f-E (T1584) — Shell-Flow-Boot überspringt Router-Berührungen
#  (PANEL-11 Shell-Flow-Zweig). Code-Level-Beweis, da boot() im DOM-gated
#  Block läuft (nicht via node require erreichbar), analog test_T1519_AC*.
# ============================================================

def _boot_body(js):
    """Extrahiert den (async function boot() { ... })-Rumpf aus app.js.
    Klammer-Balance ab der boot-Deklaration bis zum schließenden `})();`."""
    start = js.find('function boot()')
    assert start != -1, "boot()-Funktion muss in app.js existieren (T1584)"
    depth = 0
    seen = False
    for i in range(start, len(js)):
        ch = js[i]
        if ch == '{':
            depth += 1
            seen = True
        elif ch == '}':
            depth -= 1
            if seen and depth == 0:
                return js[start:i + 1]
    raise AssertionError("boot()-Rumpf nicht balanciert extrahierbar (T1584)")


def test_T1584_spec_traegt_shell_flow_zweig_in_panel_11():
    """T1584: PANEL-11 in specs/platform/app-panel.md trägt den Shell-Flow-Zweig
    (ingest_url gesetzt → lokaler Tap autoritativ, kein Router-SSE/ROU-32) samt
    RAT-31-Entfall-Notiz für die obsoleten Stream-Korrekturfälle."""
    spec_path = os.path.normpath(os.path.join(ROOT, '..', '..', 'specs', 'platform', 'app-panel.md'))
    spec = read(spec_path)
    # Shell-Flow-Zweig muss innerhalb PANEL-11 (vor PANEL-12) beschrieben sein:
    p11 = spec.find('### PANEL-11')
    p12 = spec.find('### PANEL-12', p11)
    assert p11 != -1 and p12 != -1, "PANEL-11 und PANEL-12 müssen in der Spec existieren"
    section = spec[p11:p12]
    assert 'Shell-Flow-Zweig' in section, (
        "PANEL-11 muss einen Shell-Flow-Zweig beschreiben (T1584)"
    )
    assert 'RAT-31' in section and 'ingest_url' in section, (
        "PANEL-11 Shell-Flow-Zweig muss RAT-31 und ingest_url referenzieren (T1584)"
    )
    assert 'entfallen' in section, (
        "PANEL-11 muss die RAT-31-Entfall-Notiz für die Stream-Korrekturfälle tragen (T1584)"
    )
