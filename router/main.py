#!/usr/bin/env python3
"""XBuddy Router V1 — siehe specs/platform/router.md (Refs #5).

Adapter ↔ Routing-Kern strikt getrennt (ROU-1). Nimmt POST /api/v1/events
entgegen, mappt Phone-Events 1:1 auf das kanonische Trigger-Modell
(ROU-6), löst per M:N-Tabelle aus routing.json (ROU-18) auf und hält
State pro Display in-memory (ROU-10).
"""

from flask import Flask, request, jsonify, send_from_directory, abort
from datetime import datetime, timezone
from urllib.parse import urlencode
import argparse
import json
import logging
import os
import queue
import sys
import threading
import urllib.request

# ============================================================
#  Zustand (in-memory, V1)
# ============================================================

state = {}                # ROU-10: { display_id: {…} | None }
routing_entries = []      # ROU-9 / ROU-18
panels = {}               # ROU-18 panels-Abschnitt: source_id → { display_id }
known_displays = set()    # Vereinigung aller display_ids in den Einträgen + panels


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


# ============================================================
#  Routing-Kern (ROU-9 .. ROU-11)
# ============================================================

def lookup(source_id, descriptor):
    """Erster Match per Feld-Gleichheit. None wenn kein Eintrag passt."""
    for entry in routing_entries:
        if entry.get('source_id') != source_id:
            continue
        e_desc = entry.get('descriptor', {})
        if all(descriptor.get(k) == v for k, v in e_desc.items()):
            return entry.get('display_ids', []), entry.get('payload', {})
    return None


def apply_trigger(source_id, descriptor):
    """ROU-11 Match: setzt State für alle display_ids. Kein Match: nur loggen."""
    match = lookup(source_id, descriptor)
    if match is None:
        logging.warning('kein Match: source_id=%s descriptor=%s', source_id, descriptor)
        return
    display_ids, payload = match
    ts = now_iso()
    for did in display_ids:
        state[did] = {
            'source_id': source_id,
            'descriptor': descriptor,
            'payload':   payload,
            'since':     ts,
        }
        # ROU-22: jede Zustandsänderung an die offenen SSE-Streams melden.
        publish(did, state[did])
    # ROU-21: Direkt-Push an Chromium via CDP, falls konfiguriert.
    url = payload.get('url') if isinstance(payload, dict) else None
    if url:
        cdp_navigate_async(url)


def apply_session_end(source_id):
    """ROU-11: alle Displays, deren State diese source_id trägt, auf null."""
    affected = False
    for did in list(state.keys()):
        s = state[did]
        if s and s.get('source_id') == source_id:
            state[did] = None
            affected = True
            # ROU-22: den null-Zustand an die offenen SSE-Streams melden.
            publish(did, None)
    # ROU-21: bei State=null auf idle-URL springen
    if affected:
        cdp_navigate_async(runtime_config.get('cdp_idle_url') or 'about:blank')


# ============================================================
#  SSE-Zustands-Stream (ROU-22)
# ============================================================
#
#  Pro offener Stream-Verbindung eine Queue. Eine Zustandsänderung (ROU-11)
#  legt den neuen Zustand in jede Queue des betroffenen Displays. Reine
#  Intra-Prozess-Verdrahtung — kein Broker, keine Topics: E-DC-1 grenzt SSE
#  ausdrücklich vom verschobenen MQTT-Transport (E-ROU-2) ab.

_subscribers = {}                 # display_id -> set[queue.Queue]
_subscribers_lock = threading.Lock()

# Heartbeat-Intervall: hält die Verbindung über Proxies offen und lässt den
# Generator abgebrochene Clients erkennen (sonst bliebe seine Queue für immer
# blockiert und die Subscription läge als Leiche herum).
SSE_HEARTBEAT_SECONDS = 15


def subscribe(display_id):
    q = queue.Queue()
    with _subscribers_lock:
        _subscribers.setdefault(display_id, set()).add(q)
    return q


def unsubscribe(display_id, q):
    with _subscribers_lock:
        subs = _subscribers.get(display_id)
        if subs:
            subs.discard(q)
            if not subs:
                del _subscribers[display_id]


def publish(display_id, display_state):
    """Legt den neuen Zustand in jede offene Stream-Queue des Displays."""
    with _subscribers_lock:
        subs = list(_subscribers.get(display_id, ()))
    for q in subs:
        q.put(display_state)


def sse_pack(display_state):
    """Formatiert einen Display-State (ROU-10) als SSE-Nachricht."""
    return 'data: ' + json.dumps(display_state, ensure_ascii=False) + '\n\n'


def display_event_stream(display_id):
    """Generator für ROU-22: liefert den aktuellen Zustand beim Verbinden,
    danach jede Änderung. Heartbeat-Kommentare halten die Verbindung und
    räumen die Subscription ab, sobald der Client weg ist."""
    q = subscribe(display_id)
    try:
        yield sse_pack(state.get(display_id))      # Zustand beim Verbinden
        while True:
            try:
                s = q.get(timeout=SSE_HEARTBEAT_SECONDS)
            except queue.Empty:
                yield ': keepalive\n\n'
                continue
            yield sse_pack(s)
    finally:
        unsubscribe(display_id, q)


# ============================================================
#  Chrome DevTools Protocol Push (ROU-21)
# ============================================================

# Laufzeit-Konfig wird vom Entrypoint befüllt. Tests setzen direkt.
runtime_config = {
    'cdp_target':   '',
    'cdp_idle_url': 'about:blank',
    'controller_dir': '',   # ROU-23: leer = Default aus DEFAULTS_CONTROLLER_DIR
}


def cdp_navigate(target, url, timeout=2.0):
    """Synchrone Variante (für Tests + interne Nutzung).

    Liefert True bei Erfolg, False bei jedem Fehler (gelogged).
    Blockiert nie länger als `timeout` Sekunden insgesamt.
    """
    if not target:
        return False
    try:
        # 1. Liste der Tabs holen
        with urllib.request.urlopen(target.rstrip('/') + '/json', timeout=timeout) as resp:
            tabs = json.loads(resp.read().decode('utf-8'))
        ws_url = None
        for tab in tabs:
            if tab.get('type') == 'page' and tab.get('webSocketDebuggerUrl'):
                ws_url = tab['webSocketDebuggerUrl']
                break
        if not ws_url:
            logging.warning('CDP: kein Page-Tab gefunden auf %s', target)
            return False
        # 2. WebSocket + Page.navigate (websocket-client, synchron)
        import websocket  # lazy import: nicht benötigt wenn cdp_target leer
        ws = websocket.create_connection(ws_url, timeout=timeout)
        try:
            ws.send(json.dumps({
                'id': 1,
                'method': 'Page.navigate',
                'params': {'url': url},
            }))
            # Antwort lesen (best effort) — Page.navigate bestätigt schnell.
            ws.recv()
        finally:
            ws.close()
        logging.info('CDP push → %s', url)
        return True
    except Exception as e:  # noqa: BLE001 — V1: alle Fehler isolieren
        logging.warning('CDP push fehlgeschlagen (%s): %s', target, e)
        return False


def cdp_navigate_async(url):
    """Feuert den CDP-Push in einem Daemon-Thread — POST /api/v1/events bleibt schnell."""
    target = runtime_config.get('cdp_target') or ''
    if not target:
        return
    t = threading.Thread(target=cdp_navigate, args=(target, url), daemon=True)
    t.start()


# ============================================================
#  Phone-Adapter (ROU-6)
# ============================================================

def adapt_phone(event):
    """1:1-Mapping ohne Logik. Liefert (kind, source_id, payload) oder (None, fehler)."""
    t = event.get('type')
    sid = event.get('source_id')
    if t in ('figure_detected', 'angle_update'):
        if 'figure_id' not in event:
            return None, 'figure_id fehlt'
        if 'bucket' not in event:
            return None, 'bucket fehlt'
        return ('trigger', sid, {
            'figure_id': event['figure_id'],
            'bucket':    event['bucket'],
        }), None
    if t == 'session_ended':
        return ('end', sid, None), None
    return None, 'unbekannter type "%s"' % t


# ============================================================
#  App-Panel-Adapter (ROU-24)
# ============================================================
#
# Hardcode-frei: keine App-Liste, kein switch über App-Namen. Die Payload-URL
# wird per Konvention aus dem Descriptor abgeleitet (URL-2: /display/<app>/<view>),
# `query` (optional) hängt als URL-encoded Query-String an. `display_id` für
# das State-Update kommt aus dem panels-Abschnitt der routing.json (ROU-18) —
# eine Zeile pro Panel-Instanz, nicht pro Kachel (E-PANEL-5).

def adapt_app_panel(event):
    """Validiert ein App-Panel-Event und liefert (kind, source_id, descriptor)
    oder (None, fehler-string). Behandelt zwei Event-Typen (PANEL-6):
    `tile_selected` mit Pflichtfeldern `app`, `view` (Strings/Zahlen) und
    optional flachem `query`; `panel_cleared` ohne Descriptor.

    Wir akzeptieren nur flache Werte (Strings/Zahlen) — verschachtelte query-
    Objekte oder Listen verletzen ROU-2 und PANEL-7 und werden mit einem
    sprechenden Fehler abgewiesen.
    """
    t = event.get('type')
    sid = event.get('source_id')
    if t == 'panel_cleared':
        return ('end', sid, None), None
    if t == 'tile_selected':
        if 'app' not in event:
            return None, 'app fehlt'
        if 'view' not in event:
            return None, 'view fehlt'
        app_val = event['app']
        view_val = event['view']
        if not isinstance(app_val, (str, int, float)) or isinstance(app_val, bool):
            return None, 'app muss String oder Zahl sein'
        if not isinstance(view_val, (str, int, float)) or isinstance(view_val, bool):
            return None, 'view muss String oder Zahl sein'
        query = event.get('query')
        if query is not None:
            if not isinstance(query, dict):
                return None, 'query muss ein flaches Objekt sein'
            for k, v in query.items():
                # PANEL-7: Strings/Zahlen, keine verschachtelten Objekte/Listen.
                if isinstance(v, bool) or not isinstance(v, (str, int, float)):
                    return None, ('query.%s muss String oder Zahl sein '
                                  '(keine verschachtelten Objekte/Listen)' % k)
        descriptor = {'app': app_val, 'view': view_val}
        if query:
            descriptor['query'] = dict(query)
        return ('trigger', sid, descriptor), None
    return None, 'unbekannter type "%s"' % t


def build_panel_url(app_val, view_val, query):
    """ROU-24 Konvention: /display/<app>/<view>[?<urlencoded query>].
    Hardcode-frei — funktioniert für jedes app/view-Tupel ohne Code-Änderung."""
    base = '/display/%s/%s' % (app_val, view_val)
    if query:
        # Stabile, deterministische Reihenfolge der Query-Schlüssel — testbar.
        items = [(k, query[k]) for k in sorted(query.keys())]
        return base + '?' + urlencode(items)
    return base


def apply_panel_trigger(source_id, descriptor):
    """ROU-24: Panel-Trigger anwenden. display_id aus panels-Eintrag, payload.url
    per Konvention. Findet sich kein Eintrag → wie ROU-11 unbekannter Trigger:
    2xx, Warnung, kein State-Update."""
    panel_entry = panels.get(source_id)
    if panel_entry is None:
        logging.warning('App-Panel ohne panels-Eintrag: source_id=%s', source_id)
        return
    display_id = panel_entry.get('display_id')
    if not display_id:
        logging.warning('panels-Eintrag ohne display_id: source_id=%s', source_id)
        return
    url = build_panel_url(
        descriptor['app'], descriptor['view'], descriptor.get('query'))
    payload = {'url': url}
    ts = now_iso()
    state[display_id] = {
        'source_id':  source_id,
        'descriptor': descriptor,
        'payload':    payload,
        'since':      ts,
    }
    publish(display_id, state[display_id])
    cdp_navigate_async(url)


# ============================================================
#  Laden von Dateien (ROU-18 / ROU-19)
# ============================================================

def load_routing(path):
    global routing_entries, known_displays, panels
    routing_entries = []
    panels = {}
    known_displays = set()
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.warning('routing.json nicht gefunden: %s — starte mit leerer Tabelle', path)
        return
    except json.JSONDecodeError as e:
        logging.warning('routing.json nicht parsebar (%s): %s — starte mit leerer Tabelle', path, e)
        return
    routing_entries = data.get('entries', []) or []
    for e in routing_entries:
        # Migrations-Schutz: die alte Form `display_ids` (Plural) bleibt für
        # descriptor-basiertes Matching (ROU-9) gültig. Eine alte Form
        # `display_ids` im panels-Abschnitt würde E-PANEL-5 widersprechen —
        # darum wird der panels-Abschnitt strikt gegen Singular validiert.
        for d in e.get('display_ids', []):
            known_displays.add(d)
    raw_panels = data.get('panels', {}) or {}
    if not isinstance(raw_panels, dict):
        logging.warning('panels-Abschnitt ist kein Objekt — ignoriere')
        raw_panels = {}
    for source_id, entry in raw_panels.items():
        if not isinstance(entry, dict):
            logging.warning('panels[%s] ist kein Objekt — ignoriere', source_id)
            continue
        # E-PANEL-5 / ROU-18: Singular `display_id`. Die Plural-Form aus dem
        # frühen Entwurf wird hier sichtbar abgelehnt, damit eine versehentliche
        # Wiedereinführung beim Reload nicht stumm verschwindet.
        if 'display_ids' in entry and 'display_id' not in entry:
            logging.warning(
                'panels[%s] nutzt veraltete Form `display_ids` (Plural); '
                'E-PANEL-5 verlangt `display_id` (Singular) — Eintrag ignoriert',
                source_id)
            continue
        display_id = entry.get('display_id')
        if not isinstance(display_id, str) or not display_id:
            logging.warning('panels[%s] ohne gültiges `display_id` — ignoriere', source_id)
            continue
        panels[source_id] = {'display_id': display_id}
        known_displays.add(display_id)
    logging.info('routing geladen: %d Einträge, %d Panels, %d Displays (%s)',
                 len(routing_entries), len(panels), len(known_displays),
                 ', '.join(sorted(known_displays)) or '—')


def load_config(path, defaults):
    cfg = dict(defaults)
    try:
        with open(path) as f:
            file_cfg = json.load(f)
        for k, v in file_cfg.items():
            if k.startswith('_'):  # Kommentar-Felder
                continue
            cfg[k] = v
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as e:
        logging.warning('config.json nicht parsebar (%s): %s — Defaults bleiben', path, e)
    return cfg


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)


@app.route('/api/v1/events', methods=['POST'])
def events_endpoint():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'JSON-Body fehlt oder ungültig'}), 400
    if 'source_id' not in body or 'type' not in body:
        return jsonify({'error': 'source_id und type sind Pflicht'}), 400
    # ROU-24: Adapter-Auswahl per Event-Type. ROU-24 beschreibt den App-Panel-
    # Adapter über die Events, die er verarbeitet (`tile_selected`,
    # `panel_cleared`) — nicht über eine `source_id`-Konvention. Damit bleibt
    # der Routing-Kern hardcode-frei (ROU-1) und keine source_id-Form ist
    # auf der Dispatch-Ebene privilegiert.
    etype = body.get('type')
    if etype in ('tile_selected', 'panel_cleared'):
        adapted, err = adapt_app_panel(body)
        if err:
            return jsonify({'error': err}), 400
        kind, source_id, descriptor = adapted
        if kind == 'end':
            apply_session_end(source_id)
            return '', 204
        apply_panel_trigger(source_id, descriptor)
        return '', 204
    adapted, err = adapt_phone(body)
    if err:
        return jsonify({'error': err}), 400
    kind, source_id, payload = adapted
    if kind == 'end':
        apply_session_end(source_id)
        return '', 204
    apply_trigger(source_id, payload)
    return '', 204


@app.route('/api/v1/displays/<display_id>/state', methods=['GET'])
def get_state(display_id):
    if display_id not in known_displays:
        return jsonify({'error': 'unknown display'}), 404
    return jsonify(state.get(display_id))


@app.route('/api/v1/displays/<display_id>/events', methods=['GET'])
def display_events(display_id):
    # ROU-22: SSE-Zustands-Stream. Unbekannte id → 404 (wie ROU-12).
    if display_id not in known_displays:
        return jsonify({'error': 'unknown display'}), 404
    resp = app.response_class(display_event_stream(display_id),
                              mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/api/v1/diag', methods=['GET'])
def diag():
    rows = []
    for did in sorted(known_displays):
        rows.append('<h4>%s</h4><pre>%s</pre>' % (
            did,
            json.dumps(state.get(did), indent=2, ensure_ascii=False)))
    return (
        '<!DOCTYPE html><html><head><title>Router /api/v1/diag</title>'
        '<meta http-equiv="refresh" content="1">'
        '<style>body{font-family:monospace;background:#0b0b10;color:#e8e8e8;padding:20px;margin:0}'
        'pre{background:#1a1a25;padding:14px;border-radius:6px;overflow:auto}'
        'h2,h3,h4{color:#4ade80;margin:14px 0 6px}p{color:#888}</style>'
        '</head><body><h2>Router /api/v1/diag</h2>'
        '<p>displays: %s · routing-einträge: %d</p>'
        '<h3>State pro Display</h3>%s</body></html>') % (
            ', '.join(sorted(known_displays)) or '(keine)',
            len(routing_entries),
            ''.join(rows) or '<p>(noch nichts)</p>')


# ============================================================
#  Display-Client-Auslieferung (ROU-20 / E-DC-3)
# ============================================================

DISPLAY_CLIENT_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'display-client'))


def render_display_client():
    """Liefert die Display-Client-Seite: index.html mit inline gezogenem
    displib.js, damit der Client als eine einzige same-origin-Antwort
    ankommt (E-DC-3). Identität und Verhalten bestimmt der Client selbst
    aus der Einstiegs-URL (specs/platform/display-client.md)."""
    with open(os.path.join(DISPLAY_CLIENT_DIR, 'index.html'), encoding='utf-8') as f:
        html = f.read()
    with open(os.path.join(DISPLAY_CLIENT_DIR, 'displib.js'), encoding='utf-8') as f:
        displib = f.read()
    return html.replace(
        '<script src="displib.js"></script>',
        '<script>\n' + displib + '\n</script>')


@app.route('/display/<display_id>', methods=['GET'])
def display(display_id):
    # ROU-20: liefert den Display-Client unabhängig davon, ob <display_id>
    # bekannt ist. Ob das Display existiert, klärt der Client beim Verbinden
    # mit seinem Zustands-Stream (ROU-22); bei unbekannter id zeigt er einen
    # Einrichtungs-Hinweis (DC-8). Die id liest der Client aus der URL.
    return render_display_client()


# ============================================================
#  Controller-PWA-Auslieferung (ROU-23)
# ============================================================
#
# Anders als der Display-Client ist der Controller eine echte PWA: sw.js,
# manifest.json und Icons müssen als eigene Pfade mit korrekten
# Content-Types ankommen. Flask's send_from_directory blockiert
# Path-Traversal von sich aus (werkzeug safe_join), zusätzlich prüfen wir
# explizit, dass der aufgelöste Pfad innerhalb des Wurzelverzeichnisses
# liegt — Defense in Depth.

DEFAULT_CONTROLLER_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'controller', 'figuren-erkennung'))

# ROU-24 / PANEL-2: App-Panel-Statik liegt unter controller/app-panel/.
# Anders als der Figuren-Erkennung-Controller (1 Slug) ist app-panel ein
# Controller-Typ mit beliebig vielen Instanzen — `<id>` im Pfad ist die
# Instanz-Identität (E-PANEL-4), nicht ein App-Slug.
DEFAULT_APP_PANEL_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'controller', 'app-panel'))

# Explizites Content-Type-Mapping. Browser entscheiden anhand des Headers,
# nicht anhand der Endung — ein .json mit text/html würde das Manifest
# verwerfen, ein .js mit text/plain die SW-Registrierung scheitern lassen.
_CONTROLLER_MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js':   'application/javascript',
    '.json': 'application/manifest+json',
    '.png':  'image/png',
}


def controller_dir():
    return runtime_config.get('controller_dir') or DEFAULT_CONTROLLER_DIR


def controller_app_slug():
    # URL-3 / ROU-23: der gültige App-Slug im Pfad ist der Basisname des
    # konfigurierten Controller-Wurzelverzeichnisses.
    return os.path.basename(controller_dir().rstrip('/'))


def _send_controller_asset(rel_path):
    root = os.path.realpath(controller_dir())
    # werkzeug safe_join würfe bei .. selbst; wir lassen es flach abprüfen,
    # damit send_from_directory sauber 404 wirft und wir uns nicht auf
    # ein einziges Verteidigungs-Layer verlassen.
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _CONTROLLER_MIME.get(ext, 'application/octet-stream')
    return send_from_directory(root, rel_path, mimetype=mime)


@app.route('/controller/<app>/', methods=['GET'])
def controller_index(app):
    # ROU-23: /controller/<app>/ → index.html mit text/html.
    # Nur der konfigurierte App-Slug ist gültig (URL-3, zwei Segmente).
    if app != controller_app_slug():
        abort(404)
    return _send_controller_asset('index.html')


@app.route('/controller/<app>/<path:asset>', methods=['GET'])
def controller_asset(app, asset):
    # ROU-23: alle Statik-Pfade unter /controller/<app>/ aus controller_dir().
    # send_from_directory + realpath-Check verhindern Path-Traversal.
    # App-Panel hat seinen eigenen Pfad-Baum (ROU-24, PANEL-2) — siehe unten.
    if app == 'app-panel':
        abort(404)
    if app != controller_app_slug():
        abort(404)
    return _send_controller_asset(asset)


# ============================================================
#  App-Panel-Auslieferung (PANEL-2, ROU-24)
# ============================================================
#
# Anders als der Figuren-Erkennung-Controller (ein Slug, eine Identität via
# config.json) ist die App-Panel-Seite ein Controller-Typ mit beliebig vielen
# Instanzen — jede Instanz adressiert über `<id>` im Pfad (E-PANEL-4). Der
# Router liefert dieselbe Statik unter jeder `<id>` aus und rendert die
# `<id>` als Datenattribut in die HTML — die Seite kennt damit ohne weiteren
# Roundtrip ihre eigene Panel-Identität (PANEL-2 Test).

def app_panel_dir():
    # Defense in Depth: realpath, damit symbolische Links keine traversierung
    # aus dem Wurzelverzeichnis erlauben.
    return DEFAULT_APP_PANEL_DIR


def _send_app_panel_asset(rel_path):
    root = os.path.realpath(app_panel_dir())
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _CONTROLLER_MIME.get(ext, None)
    # CSS muss als text/css ausgeliefert werden — sonst lehnen Browser das
    # Stylesheet ab. App-Panel hat als einziger Controller heute eine eigene
    # CSS-Datei, daher das Mime-Mapping hier lokal erweitert.
    if mime is None and ext == '.css':
        mime = 'text/css; charset=utf-8'
    if mime is None and ext == '.svg':
        mime = 'image/svg+xml'
    return send_from_directory(root, rel_path,
                               mimetype=mime or 'application/octet-stream')


def render_app_panel_index(panel_id):
    """PANEL-2: liefert index.html mit der Panel-Identität als data-source-id
    im <body>-Tag. Die Seite kennt damit ohne weiteren Roundtrip ihre eigene
    Identität — die Konsistenz-Prüfung (PANEL-8) vergleicht den Wert dann mit
    der `source_id` aus config.json."""
    index_path = os.path.join(app_panel_dir(), 'index.html')
    with open(index_path, encoding='utf-8') as f:
        html = f.read()
    # data-source-id ist Spec-neutrales Token (PANEL-2 Test). Wir setzen es
    # auf der <body>-Wurzel, damit JS es per document.body.dataset lesen kann.
    return html.replace(
        '<body>',
        '<body data-panel-id="%s">' % panel_id,
        1)


@app.route('/controller/app-panel/<panel_id>', methods=['GET'])
def app_panel_index_no_slash(panel_id):
    return render_app_panel_index(panel_id), 200, {
        'Content-Type': 'text/html; charset=utf-8'}


@app.route('/controller/app-panel/<panel_id>/', methods=['GET'])
def app_panel_index_slash(panel_id):
    return render_app_panel_index(panel_id), 200, {
        'Content-Type': 'text/html; charset=utf-8'}


@app.route('/controller/app-panel/<panel_id>/<path:asset>', methods=['GET'])
def app_panel_asset(panel_id, asset):
    return _send_app_panel_asset(asset)


# ============================================================
#  Entrypoint (ROU-15 / ROU-16)
# ============================================================

DEFAULTS = {
    'listen_host':  '127.0.0.1',
    'listen_port':  5000,
    'log_level':    'INFO',
    'cdp_target':   '',
    'cdp_idle_url': 'about:blank',
    'controller_dir': '',  # ROU-23: leer = DEFAULT_CONTROLLER_DIR
}


def parse_args(argv):
    p = argparse.ArgumentParser(description='XBuddy Router V1')
    p.add_argument('--routing', default='routing.json', help='Pfad zur Routing-Tabelle (ROU-18)')
    p.add_argument('--config',  default='config.json',  help='Pfad zur Konfig (ROU-19)')
    p.add_argument('--host',    help='Bind-Host (überschreibt config + ENV)')
    p.add_argument('--port',    type=int, help='Bind-Port (überschreibt config + ENV)')
    p.add_argument('--log-level', dest='log_level', help='DEBUG | INFO | WARNING | ERROR')
    p.add_argument('--controller-dir', dest='controller_dir',
                   help='Pfad zur Controller-PWA-Statik (ROU-23)')
    p.add_argument('--cert', help='TLS-Cert (optional, für HTTPS-Modus)')
    p.add_argument('--key',  help='TLS-Key (optional, für HTTPS-Modus)')
    return p.parse_args(argv)


def resolved_config(args):
    """ROU-15-Priorität: Defaults < config.json < ENV < CLI."""
    cfg = load_config(args.config, DEFAULTS)
    if 'ROUTER_HOST'         in os.environ: cfg['listen_host']  = os.environ['ROUTER_HOST']
    if 'ROUTER_PORT'         in os.environ: cfg['listen_port']  = int(os.environ['ROUTER_PORT'])
    if 'ROUTER_LOG_LEVEL'    in os.environ: cfg['log_level']    = os.environ['ROUTER_LOG_LEVEL']
    if 'ROUTER_CDP_TARGET'   in os.environ: cfg['cdp_target']   = os.environ['ROUTER_CDP_TARGET']
    if 'ROUTER_CDP_IDLE_URL' in os.environ: cfg['cdp_idle_url'] = os.environ['ROUTER_CDP_IDLE_URL']
    if 'ROUTER_CONTROLLER_DIR' in os.environ: cfg['controller_dir'] = os.environ['ROUTER_CONTROLLER_DIR']
    if args.host:           cfg['listen_host']    = args.host
    if args.port:           cfg['listen_port']    = args.port
    if args.log_level:      cfg['log_level']      = args.log_level
    if args.controller_dir: cfg['controller_dir'] = args.controller_dir
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    logging.basicConfig(
        level=getattr(logging, cfg['log_level'].upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(message)s')
    runtime_config['cdp_target']    = cfg.get('cdp_target', '')
    runtime_config['cdp_idle_url']  = cfg.get('cdp_idle_url', 'about:blank')
    runtime_config['controller_dir'] = cfg.get('controller_dir', '')
    logging.info('Controller-PWA-Statik: %s', controller_dir())
    if runtime_config['cdp_target']:
        logging.info('CDP-Push aktiv: %s (idle=%s)',
                     runtime_config['cdp_target'], runtime_config['cdp_idle_url'])
    load_routing(args.routing)
    ssl_context = None
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = 'https'
    else:
        scheme = 'http'
    logging.info('Router hört auf %s://%s:%s', scheme, cfg['listen_host'], cfg['listen_port'])
    app.run(host=cfg['listen_host'], port=cfg['listen_port'],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == '__main__':
    main()
