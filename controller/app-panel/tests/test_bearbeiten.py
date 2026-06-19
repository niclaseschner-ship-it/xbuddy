"""Tests pro PBE-Requirement (T452 — Editor-Seite Frontend, AC6).

Statische Prüfungen auf bearbeiten.html / bearbeiten.js / bearbeiten.css +
Node-Subprozess für die reinen Logik-Funktionen aus bearbeiten.js (UMD-Export
editorLib). Analog zu test_app_panel.py — kein eigener JS-Test-Runner nötig.

Lauf: python3 -m pytest controller/app-panel/tests/ -v
"""

import json
import os
import subprocess
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(ROOT, 'bearbeiten.html')
JS_PATH = os.path.join(ROOT, 'bearbeiten.js')
CSS_PATH = os.path.join(ROOT, 'bearbeiten.css')


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def run_node(snippet):
    """Lädt editorLib aus bearbeiten.js, führt JS-Snippet aus, gibt parsedes
    JSON zurück (das Snippet muss am Ende `console.log(JSON.stringify(...))`)."""
    src = textwrap.dedent('''
        const editorLib = require(%r);
        %s
    ''' % (JS_PATH, snippet))
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
#  AC2 / PBE-5 — Verschieben (Reorder)
# ============================================================

def test_PBE_5_move_tile_up_preserves_keys():
    """PBE-5: Verschieben ändert nur Reihenfolge, nicht Inhalt oder `key`."""
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
          { key: 'b', app: 'p', view: 'v', label: 'B', icons: ['i.png'], sichtbar: true },
          { key: 'c', app: 'p', view: 'v', label: 'C', icons: ['i.png'], sichtbar: true },
        ];
        const out = editorLib.moveTile(tiles, 'c', 'up');
        console.log(JSON.stringify(out.map(t => t.key)));
    ''')
    assert out == ['a', 'c', 'b'], 'moveTile up muss c und b vertauschen'


def test_PBE_5_move_tile_down_preserves_keys():
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
          { key: 'b', app: 'p', view: 'v', label: 'B', icons: ['i.png'], sichtbar: true },
          { key: 'c', app: 'p', view: 'v', label: 'C', icons: ['i.png'], sichtbar: true },
        ];
        const out = editorLib.moveTile(tiles, 'a', 'down');
        console.log(JSON.stringify(out.map(t => t.key)));
    ''')
    assert out == ['b', 'a', 'c']


def test_PBE_5_move_tile_at_top_up_is_noop():
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
          { key: 'b', app: 'p', view: 'v', label: 'B', icons: ['i.png'], sichtbar: true },
        ];
        const out = editorLib.moveTile(tiles, 'a', 'up');
        console.log(JSON.stringify(out.map(t => t.key)));
    ''')
    assert out == ['a', 'b'], 'moveTile up am Anfang ist no-op'


def test_PBE_5_move_tile_to_drops_at_index():
    """PBE-5 / Drag&Drop: moveTileTo platziert ein Tile am Ziel-Index."""
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
          { key: 'b', app: 'p', view: 'v', label: 'B', icons: ['i.png'], sichtbar: true },
          { key: 'c', app: 'p', view: 'v', label: 'C', icons: ['i.png'], sichtbar: true },
          { key: 'd', app: 'p', view: 'v', label: 'D', icons: ['i.png'], sichtbar: true },
        ];
        const out = editorLib.moveTileTo(tiles, 'd', 1);
        console.log(JSON.stringify(out.map(t => t.key)));
    ''')
    assert out == ['a', 'd', 'b', 'c']


def test_PBE_5_move_preserves_tile_content():
    """PBE-5: Verschieben ändert weder query noch icons noch label."""
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'plan', view: 'woche', query: {ansicht: 'klein'},
            label: 'Wochenplan klein', icons: ['a.png', 'k.png'], sichtbar: true },
          { key: 'b', app: 'plan', view: 'woche', label: 'Wochenplan',
            icons: ['a.png'], sichtbar: true },
        ];
        const out = editorLib.moveTile(tiles, 'a', 'down');
        console.log(JSON.stringify(out));
    ''')
    a = next(t for t in out if t['key'] == 'a')
    assert a['query'] == {'ansicht': 'klein'}
    assert a['icons'] == ['a.png', 'k.png']
    assert a['label'] == 'Wochenplan klein'


# ============================================================
#  AC2 / PBE-6 — Ausblenden (reversibel) und Entfernen (hart)
# ============================================================

def test_PBE_6_toggle_visibility_sets_false():
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
        ];
        const out = editorLib.toggleVisibility(tiles, 'a');
        console.log(JSON.stringify({ sichtbar: out[0].sichtbar, key: out[0].key, len: out.length }));
    ''')
    assert out['sichtbar'] is False
    assert out['key'] == 'a', 'PBE-6: Kachel bleibt in der Liste (reversibel)'
    assert out['len'] == 1


def test_PBE_6_toggle_visibility_is_reversible():
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
        ];
        const step1 = editorLib.toggleVisibility(tiles, 'a');
        const step2 = editorLib.toggleVisibility(step1, 'a');
        console.log(JSON.stringify({ s1: step1[0].sichtbar, s2: step2[0].sichtbar }));
    ''')
    assert out['s1'] is False
    assert out['s2'] is True, 'PBE-6: zweimal toggeln stellt sichtbar wieder her'


def test_PBE_6_remove_tile_removes_entry():
    """PBE-6: Entfernen löscht die Kachel hart aus der Liste."""
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
          { key: 'b', app: 'p', view: 'v', label: 'B', icons: ['i.png'], sichtbar: true },
        ];
        const out = editorLib.removeTile(tiles, 'a');
        console.log(JSON.stringify(out.map(t => t.key)));
    ''')
    assert out == ['b'], 'PBE-6: Entfernen löscht den Eintrag hart'


def test_PBE_6_remove_unknown_key_is_noop():
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
        ];
        const out = editorLib.removeTile(tiles, 'unbekannt');
        console.log(JSON.stringify(out.map(t => t.key)));
    ''')
    assert out == ['a']


# ============================================================
#  AC2 / PBE-7 — Hinzufügen aus der Seiten-Registry (Sorte a + Varianten)
# ============================================================

def test_PBE_7_flatten_registry_entry_with_variant():
    """PBE-7 + SREG-1: eine View mit endlichen Varianten erscheint als
    getrennte, direkt wählbare Einträge (Default + jede Variante)."""
    out = run_node('''
        const entry = {
          typ: 'display',
          pfad: '/display/plan/woche',
          label: 'Wochenplan',
          icons: ['arasaac/32488.png'],
          varianten: [
            { slug: 'klein', query: { ansicht: 'klein' },
              label: 'Wochenplan klein',
              icons: ['arasaac/32488.png', 'arasaac/2484.png'] },
          ],
        };
        const cands = editorLib.flattenRegistryEntry(entry);
        console.log(JSON.stringify(cands));
    ''')
    assert len(out) == 2, 'PBE-7: Default + 1 Variante → 2 Candidates'
    assert out[0]['app'] == 'plan'
    assert out[0]['view'] == 'woche'
    default_q = out[0].get('query')
    assert not default_q, 'PBE-7: Default-Eintrag hat kein query'
    assert out[1]['query'] == {'ansicht': 'klein'}
    assert out[1]['icons'] == ['arasaac/32488.png', 'arasaac/2484.png']


def test_PBE_7_flatten_registry_entry_multi_segment_view():
    """AC3 / T1007-S2: flattenRegistryEntry parst Multi-Segment-Views korrekt.
    /display/hoerspiel/mia/alben → app='hoerspiel', view='mia/alben'.
    Vorher schnitt der 2-Segment-Regex das view auf 'mia' ab."""
    out = run_node('''
        const entry = {
          typ: 'display',
          pfad: '/display/hoerspiel/mia/alben',
          label: 'Mias Hörspiele',
          icons: ['arasaac/5915.png'],
        };
        const cands = editorLib.flattenRegistryEntry(entry);
        console.log(JSON.stringify(cands));
    ''')
    assert len(out) == 1, 'flattenRegistryEntry: 1 Eintrag erwartet (kein Varianten)'
    assert out[0]['app'] == 'hoerspiel', \
        'app muss "hoerspiel" sein, bekommen: %r' % out[0].get('app')
    assert out[0]['view'] == 'mia/alben', \
        'view muss "mia/alben" sein (Multi-Segment), bekommen: %r' % out[0].get('view')


def test_PBE_7_flatten_registry_entry_multi_segment_with_query_edge():
    """AC4 / T1007-S2: flattenRegistryEntry mit Query-String im pfad erzeugt
    korrekte app/view ohne trailing Query (Query landet NICHT im view)."""
    out = run_node('''
        const entry = {
          typ: 'display',
          pfad: '/display/plan/woche?ansicht=klein',
          label: 'Wochenplan klein',
          icons: ['arasaac/32488.png'],
        };
        const cands = editorLib.flattenRegistryEntry(entry);
        console.log(JSON.stringify(cands));
    ''')
    # Der pfad ist ungewöhnlich (Query üblicherweise via varianten.query),
    # aber der Regex muss sauber parsen ohne Query in das view aufzunehmen.
    assert len(out) == 1, 'flattenRegistryEntry mit Query-pfad: 1 Eintrag erwartet'
    assert out[0]['app'] == 'plan'
    assert out[0]['view'] == 'woche', \
        'view darf keinen Query-String enthalten, bekommen: %r' % out[0].get('view')


def test_PBE_7_flatten_skips_non_display_sorts():
    """PBE-7: nur Display-Views (Sorte a) — Sorte b/c/d/e werden ausgefiltert."""
    out = run_node('''
        const seiten = [
          { typ: 'display',    pfad: '/display/plan/woche',           label: 'Plan',    icons: ['a.png'] },
          { typ: 'eltern',     pfad: '/display/wetter/regeln',         label: 'Wetter-Editor', icons: ['b.png'] },
          { typ: 'controller', pfad: '/controller/figuren-erkennung/', label: 'Figuren' },
          { typ: 'panel',      pfad: '/controller/app-panel/kueche',   label: 'Panel kueche' },
        ];
        const cands = editorLib.buildAddCandidates(seiten);
        console.log(JSON.stringify(cands.map(c => c.app + '/' + c.view)));
    ''')
    assert out == ['plan/woche'], 'PBE-7: nur Sorte a (Display-Views) als Add-Kandidaten'


def test_PBE_7_add_candidate_creates_panel3_valid_tile():
    """PBE-7: addCandidate erzeugt eine PANEL-3-gültige Kachel
    (key/app/view/label/icons/sichtbar) am ENDE der Liste, sichtbar:true."""
    out = run_node('''
        const tiles = [
          { key: 'wetter', app: 'wetter', view: 'now', label: 'Wetter',
            icons: ['w.png'], sichtbar: true },
        ];
        const cand = { app: 'plan', view: 'woche', label: 'Wochenplan',
                       icons: ['arasaac/32488.png'], slug: null };
        const out = editorLib.addCandidate(tiles, cand);
        console.log(JSON.stringify(out));
    ''')
    assert len(out) == 2
    new = out[1]
    assert new['app'] == 'plan'
    assert new['view'] == 'woche'
    assert new['label'] == 'Wochenplan'
    assert new['icons'] == ['arasaac/32488.png']
    assert new['sichtbar'] is True, 'PBE-7: neue Kachel ist sichtbar:true'
    assert isinstance(new['key'], str)
    assert new['key'], 'PBE-7: key darf nicht leer sein'
    assert new['key'] != out[0]['key'], \
        'PBE-7 / PANEL-3: neuer key muss vom bestehenden distinkt sein'


def test_PBE_7_add_candidate_with_query_variant():
    """PBE-7: Variante mit query → flach als Objekt in der Kachel."""
    out = run_node('''
        const cand = { app: 'plan', view: 'woche', label: 'Wochenplan klein',
                       icons: ['a.png', 'k.png'],
                       slug: 'klein', query: { ansicht: 'klein' } };
        const out = editorLib.addCandidate([], cand);
        console.log(JSON.stringify(out));
    ''')
    assert len(out) == 1
    assert out[0]['query'] == {'ansicht': 'klein'}
    assert out[0]['icons'] == ['a.png', 'k.png']


def test_PBE_7_add_candidate_keys_are_unique_within_list():
    """PBE-7 / PANEL-3: bei key-Kollision bekommt der neue Eintrag einen
    eindeutigen Suffix — nie ein doppelter key."""
    out = run_node('''
        let tiles = [];
        const cand = { app: 'plan', view: 'woche', label: 'L',
                       icons: ['a.png'], slug: null };
        tiles = editorLib.addCandidate(tiles, cand);
        tiles = editorLib.addCandidate(tiles, cand);
        tiles = editorLib.addCandidate(tiles, cand);
        console.log(JSON.stringify(tiles.map(t => t.key)));
    ''')
    assert len(set(out)) == 3, 'PBE-7 / PANEL-3: alle 3 keys müssen distinkt sein (bekommen: %r)' % out


# ============================================================
#  T452-S2 / AC4 — Add-Pfad gegen ECHTE /api/v1/seiten-Response-Form
# ============================================================
#
# SREG-3: `/api/v1/seiten` liefert `{eintraege: [...], snapshot_pending: [...]}`.
# Vorher las bearbeiten.js fälschlich `data.seiten` (existiert nicht), fiel auf
# das ganze Antwort-Objekt zurück (truthy → buildAddCandidates([...]) mit
# Array.isArray-Guard liefert []) und zeigte „Keine Display-Views" — obwohl
# Display-Einträge da waren. Diese Tests fixieren den korrekten Schlüssel.


def test_AC4_build_add_candidates_on_real_inventar_form():
    """T452-S2 / AC4: buildAddCandidates muss mit einer realistischen
    `eintraege`-Liste (Form aus seiten.aggregator.baue_inventar, SREG-3)
    Display-Kandidaten erzeugen."""
    out = run_node('''
        // SREG-4-konforme Einträge: Sorte a (display), Sorte b (eltern),
        // Sorte c (controller), Sorte d (panel) — analog
        // seiten/aggregator.py manifest_eintraege + panel_eintraege.
        const eintraege = [
          { key: 'plan-woche', typ: 'display', app: 'plan',
            pfad: '/display/plan/woche', label: 'Wochenplan',
            icons: ['arasaac/32488.png'],
            varianten: [
              { slug: 'klein', query: { ansicht: 'klein' },
                label: 'Wochenplan klein',
                icons: ['arasaac/32488.png', 'arasaac/2484.png'] },
            ],
          },
          { key: 'wetter-now', typ: 'display', app: 'wetter',
            pfad: '/display/wetter/now', label: 'Wetter jetzt',
            icons: ['arasaac/2517.png'] },
          { key: 'wetter-regeln-bearbeiten', typ: 'eltern',
            app: 'wetter', pfad: '/display/wetter/regeln',
            label: 'Wetter-Regeln' },
          { key: 'figuren-erkennung', typ: 'controller',
            app: 'figuren-erkennung',
            pfad: '/controller/figuren-erkennung/',
            label: 'Figuren-Erkennung' },
          { key: 'kueche-01', typ: 'panel', app: 'app-panel',
            pfad: '/controller/app-panel/kueche-01/',
            label: 'Panel kueche-01' },
        ];
        const cands = editorLib.buildAddCandidates(eintraege);
        console.log(JSON.stringify(cands.map(c => ({
          app: c.app, view: c.view, label: c.label,
          slug: c.slug, query: c.query || null,
        }))));
    ''')
    # Erwartung: 3 Display-Kandidaten — plan/woche (Default), plan/woche
    # (Variante klein), wetter/now. Andere Sorten (eltern/controller/panel)
    # werden ausgefiltert.
    assert len(out) == 3, \
        'AC4: 3 Display-Kandidaten erwartet (2x plan/woche, 1x wetter/now), bekommen: %r' % out
    apps_views = [(c['app'], c['view']) for c in out]
    assert ('plan', 'woche') in apps_views
    assert ('wetter', 'now') in apps_views
    # Variante muss als eigener Eintrag erscheinen.
    variant_q = [c['query'] for c in out if c.get('query')]
    assert {'ansicht': 'klein'} in variant_q, \
        'AC4: Variante mit query muss als getrennter Kandidat erscheinen'


def test_AC4_load_add_inventar_reads_eintraege_key_not_seiten():
    """T452-S2 / AC4 (Regress-Anker): die loadAddInventar-Funktion im Bootstrap
    muss `data.eintraege` lesen — NICHT `data.seiten`.

    Diese statische Probe schützt gegen Re-Regress des T452-S1-Bugs (das
    `data.seiten`-Fallback brachte „Keine Display-Views" trotz vollem Inventar)."""
    js = read(JS_PATH)
    # Positiv: der Bootstrap liest `data.eintraege`.
    assert 'data.eintraege' in js, (
        'AC4: bearbeiten.js muss data.eintraege lesen (SREG-3: '
        '/api/v1/seiten liefert {eintraege: [...], snapshot_pending: [...]})')
    # Negativ-Probe: kein `data.seiten`-Lesepfad (existiert in der Response
    # nicht, würde das ganze Objekt durchreichen und „Keine Display-Views"
    # produzieren).
    assert 'data.seiten' not in js, (
        'T452-S2 Regress: bearbeiten.js darf NICHT data.seiten lesen — '
        '/api/v1/seiten liefert keinen "seiten"-Schlüssel (SREG-3)')


def test_AC4_build_add_candidates_returns_empty_for_empty_eintraege():
    """SREG-3 Kaltstart: wenn `eintraege` leer ist (kein einziges Display-Manifest
    bisher), liefert buildAddCandidates eine leere Liste — kein Crash."""
    out = run_node('''
        const cands = editorLib.buildAddCandidates([]);
        console.log(JSON.stringify(cands));
    ''')
    assert out == []


# ============================================================
#  AC2 / PBE-4 — Speichern: vollständige Liste per PUT
# ============================================================

def test_PBE_4_save_sends_full_tiles_list_in_put():
    """PBE-4: Speichern schickt EINEN PUT der vollen tiles-Liste."""
    out = run_node('''
        let captured = null;
        const fakeFetch = (url, init) => {
            captured = { url, method: init.method, body: init.body };
            return Promise.resolve({ status: 200, ok: true,
                                     json: () => Promise.resolve({ ok: true }) });
        };
        let succ = false;
        editorLib.saveTiles({
            fetchImpl: fakeFetch,
            url: '/api/v1/panels/kueche-01/tiles',
            tiles: [{ key: 'a', app: 'p', view: 'v', label: 'A',
                      icons: ['i.png'], sichtbar: true }],
            onSuccess: () => { succ = true; },
        }).then(() => {
            console.log(JSON.stringify({ captured, succ }));
        });
    ''')
    assert out['captured']['method'] == 'PUT'
    assert out['captured']['url'] == '/api/v1/panels/kueche-01/tiles'
    body = json.loads(out['captured']['body'])
    assert 'tiles' in body
    assert body['tiles'][0]['key'] == 'a'
    assert out['succ'] is True


def test_PBE_11_save_422_calls_validation_error_with_message():
    """PBE-11 / AC4: bei 422 zeigt die Seite die Fehler-Message."""
    out = run_node('''
        const fakeFetch = () => Promise.resolve({
            status: 422, ok: false,
            json: () => Promise.resolve({ error: 'icons[] ist leer' }),
        });
        let msg = null;
        editorLib.saveTiles({
            fetchImpl: fakeFetch,
            url: '/api/v1/panels/kueche-01/tiles',
            tiles: [],
            onValidationError: (m) => { msg = m; },
            onSuccess: () => { msg = 'unexpected-success'; },
            onError: (m) => { msg = 'unexpected-error:' + m; },
        }).then(() => {
            console.log(JSON.stringify({ msg }));
        });
    ''')
    assert out['msg'] == 'icons[] ist leer', \
        'PBE-11: 422-Begründung muss durch onValidationError fließen'


def test_PBE_4_save_network_error_calls_on_error():
    out = run_node('''
        const fakeFetch = () => Promise.reject(new Error('connection refused'));
        let err = null;
        editorLib.saveTiles({
            fetchImpl: fakeFetch,
            url: '/api/v1/panels/x/tiles',
            tiles: [],
            onError: (m) => { err = m; },
        }).then(() => {
            console.log(JSON.stringify({ err }));
        });
    ''')
    assert 'connection refused' in (out['err'] or '')


# ============================================================
#  AC2 — Verwerfen-Logik: tilesAreEqual als Dirty-Anker
# ============================================================

def test_AC2_tiles_are_equal_strict():
    """Verwerfen-Anker: tilesAreEqual liefert true für gleiche Listen."""
    out = run_node('''
        const a = [{ key: 'k', app: 'p', view: 'v', label: 'L',
                     icons: ['i.png'], sichtbar: true }];
        const b = [{ key: 'k', app: 'p', view: 'v', label: 'L',
                     icons: ['i.png'], sichtbar: true }];
        const c = [{ key: 'k', app: 'p', view: 'v', label: 'L',
                     icons: ['i.png'], sichtbar: false }];
        console.log(JSON.stringify({
            ab: editorLib.tilesAreEqual(a, b),
            ac: editorLib.tilesAreEqual(a, c),
        }));
    ''')
    assert out['ab'] is True
    assert out['ac'] is False


def test_AC2_clone_tiles_deep_copies_query():
    """cloneTiles muss query so deep kopieren, dass spätere Mutationen
    am Original nicht durchschlagen — wichtig für Verwerfen."""
    out = run_node('''
        const tiles = [{ key: 'k', app: 'p', view: 'v', label: 'L',
                         icons: ['i.png'], sichtbar: true,
                         query: { ansicht: 'klein' } }];
        const clone = editorLib.cloneTiles(tiles);
        tiles[0].query.ansicht = 'gross';
        tiles[0].icons.push('extra.png');
        console.log(JSON.stringify({
            cloneQ: clone[0].query.ansicht,
            cloneIcons: clone[0].icons,
        }));
    ''')
    assert out['cloneQ'] == 'klein', 'cloneTiles muss query deep-kopieren'
    assert out['cloneIcons'] == ['i.png'], 'cloneTiles muss icons deep-kopieren'


# ============================================================
#  AC3 — PBE-8: Aus-Kachel wird NICHT als bearbeitbarer Eintrag gezeigt
# ============================================================

def test_PBE_8_strip_aus_kachel_removes_marker():
    """PBE-8: Defense-in-Depth — wenn ein __aus__-Pseudo-Eintrag je in
    tiles.json landet, filtert der Editor ihn aus."""
    out = run_node('''
        const tiles = [
          { key: 'a', app: 'p', view: 'v', label: 'A', icons: ['i.png'], sichtbar: true },
          { key: '__aus__', app: 'aus', view: 'aus', label: 'Aus',
            icons: ['arasaac/8252.png'], sichtbar: true },
          { key: 'b', app: 'p', view: 'v', label: 'B', icons: ['i.png'], sichtbar: true },
        ];
        const out = editorLib.stripAusKachel(tiles);
        console.log(JSON.stringify(out.map(t => t.key)));
    ''')
    assert out == ['a', 'b'], 'PBE-8: __aus__-Marker muss herausgefiltert werden'


def test_PBE_8_is_aus_kachel_marker_detects_key():
    out = run_node('''
        console.log(JSON.stringify({
            real: editorLib.isAusKachelMarker({ key: 'a' }),
            aus:  editorLib.isAusKachelMarker({ key: '__aus__' }),
        }));
    ''')
    assert out['real'] is False
    assert out['aus'] is True


# ============================================================
#  AC3 — PBE-9: leerer Zustand erlaubt
# ============================================================

def test_PBE_9_empty_tiles_pass_through_operations():
    """PBE-9: alle Operationen müssen mit einer leeren Liste umgehen können."""
    out = run_node('''
        const empty = [];
        console.log(JSON.stringify({
            move: editorLib.moveTile(empty, 'x', 'up').length,
            hide: editorLib.toggleVisibility(empty, 'x').length,
            rm:   editorLib.removeTile(empty, 'x').length,
            eq:   editorLib.tilesAreEqual(empty, []),
        }));
    ''')
    assert out['move'] == 0
    assert out['hide'] == 0
    assert out['rm'] == 0
    assert out['eq'] is True


# ============================================================
#  AC5 / PBE-3 — keine Auth-Schicht im JS
# ============================================================

def test_PBE_3_no_auth_token_or_login_in_js():
    """PBE-3: JS darf keine Token-/Login-Logik enthalten — Heimnetz/Tailscale
    ist das Gate (RAT-2). Negativ-Probe gegen Login/Cookie/Authorization-Patterns."""
    js = read(JS_PATH)
    lowered = js.lower()
    assert 'authorization' not in lowered, \
        'PBE-3: kein Authorization-Header — Auth ist Netz-Schicht (RAT-2)'
    assert 'document.cookie' not in lowered, \
        'PBE-3: kein Cookie-Auth-Pfad in der Seite'
    assert 'login' not in lowered, \
        'PBE-3: kein Login-UI in der Editor-Seite'


# ============================================================
#  AC2 / PBE-1 — UMD-Export für Node-Tests
# ============================================================

def test_AC2_editor_lib_exports_expected_api():
    """AC6: editorLib exportiert die API, die Tests + Bootstrap konsumieren."""
    out = run_node('''
        console.log(JSON.stringify(Object.keys(editorLib).sort()));
    ''')
    expected = {
        'cloneTiles', 'deepCopyTile', 'indexOfKey',
        'moveTile', 'moveTileTo', 'toggleVisibility', 'removeTile',
        'flattenRegistryEntry', 'buildAddCandidates', 'makeKeyFromCandidate',
        'addCandidate',
        'tilesAreEqual', 'saveTiles',
        'isAusKachelMarker', 'stripAusKachel',
    }
    missing = expected - set(out)
    assert not missing, 'editorLib-API unvollständig — fehlt: %r' % sorted(missing)


# ============================================================
#  AC2 / PBE-1 — Statik-Bundle vorhanden, korrekt vernäht
# ============================================================

def test_AC2_html_loads_js_and_css():
    """AC2: HTML lädt bearbeiten.js + bearbeiten.css (script/link)."""
    html = read(HTML_PATH)
    assert 'bearbeiten.js' in html
    assert 'bearbeiten.css' in html


def test_PBE_1_html_safe_area_viewport():
    """PBE-1: viewport-fit=cover ist gesetzt."""
    html = read(HTML_PATH)
    assert 'viewport-fit=cover' in html


def test_PBE_1_css_safe_area_inset_top():
    """PBE-1: CSS nutzt env(safe-area-inset-top) für den Kopfbereich."""
    css = read(CSS_PATH)
    assert 'safe-area-inset-top' in css


def test_AC2_html_has_drag_handle_pattern_in_js():
    """AC2: Drag/Drop ist über dragstart/dragover/drop verdrahtet."""
    js = read(JS_PATH)
    for evt in ('dragstart', 'dragover', 'drop'):
        assert evt in js, 'AC2: %s muss in bearbeiten.js verdrahtet sein' % evt
