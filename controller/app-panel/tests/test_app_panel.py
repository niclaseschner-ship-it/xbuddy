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
    # Defaults intakt: source_id startet mit "app-panel:", display_id mit "display:".
    assert out['cfg']['source_id'].startswith('app-panel:')
    assert out['cfg']['display_id'].startswith('display:')


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


def test_PANEL_11_stream_break_keeps_last_marker():
    """DC-6-Linie: Bei Stream-Abbruch darf die letzte Markierung NICHT
    gelöscht werden. Dynamische Probe über die Stream-Handler-Fabrik
    (panelLib.makeStreamHandlers): erst onMessage mit passender Payload-URL
    setzt die Markierung; danach feuert onError; assert: onError ruft den
    onActive-Callback nicht (kein Reset auf null)."""
    out = run_node('''
        const tiles = [
            { key: 'a', app: 'plan', view: 'woche', label: 'L', icons: ['arasaac/test.png'], sichtbar: true},
        ];
        const calls = [];
        const handlers = panelLib.makeStreamHandlers(
            () => tiles,
            (active) => { calls.push(active && active.key); });
        // Stream liefert State, der zur Kachel passt → Marker aktiv.
        handlers.onMessage({ data: JSON.stringify({
            payload: { url: '/display/plan/woche' }
        }) });
        // Stream bricht ab.
        handlers.onError();
        console.log(JSON.stringify({ calls }));
    ''')
    # Genau ein Aufruf: das onMessage. onError darf onActive NICHT triggern,
    # damit die letzte Markierung im UI hängen bleibt (DC-6).
    assert out['calls'] == ['a'], (
        'onError darf den Marker nicht ändern — letzte Markierung muss bleiben (DC-6). '
        'Gesehen: %r' % out['calls'])


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
