#!/usr/bin/env python3
"""XBuddy Router V1 — siehe specs/platform/router.md (Refs #5).

Adapter ↔ Routing-Kern strikt getrennt (ROU-1). Nimmt POST /api/v1/events
entgegen, mappt Phone-Events 1:1 auf das kanonische Trigger-Modell
(ROU-6), löst per M:N-Tabelle aus routing.json (ROU-18) auf und hält
State pro Display in-memory (ROU-10).
"""

from flask import Flask, request, jsonify, abort
from datetime import datetime, timezone
import argparse
import json
import logging
import os
import sys
import threading
import urllib.request

# ============================================================
#  Zustand (in-memory, V1)
# ============================================================

state = {}                # ROU-10: { display_id: {…} | None }
routing_entries = []      # ROU-9 / ROU-18
known_displays = set()    # Vereinigung aller display_ids in den Einträgen


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
    # ROU-21: bei State=null auf idle-URL springen
    if affected:
        cdp_navigate_async(runtime_config.get('cdp_idle_url') or 'about:blank')


# ============================================================
#  Chrome DevTools Protocol Push (ROU-21)
# ============================================================

# Laufzeit-Konfig wird vom Entrypoint befüllt. Tests setzen direkt.
runtime_config = {
    'cdp_target':   '',
    'cdp_idle_url': 'about:blank',
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
#  Laden von Dateien (ROU-18 / ROU-19)
# ============================================================

def load_routing(path):
    global routing_entries, known_displays
    routing_entries = []
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
        for d in e.get('display_ids', []):
            known_displays.add(d)
    logging.info('routing geladen: %d Einträge, %d Displays (%s)',
                 len(routing_entries), len(known_displays), ', '.join(sorted(known_displays)) or '—')


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


@app.route('/display/<display_id>', methods=['GET'])
def display(display_id):
    if display_id not in known_displays:
        return jsonify({'error': 'unknown display'}), 404
    did_json = json.dumps(display_id)
    return (
        '<!DOCTYPE html><html><head><title>Display ' + display_id + '</title>'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>html,body{margin:0;padding:0;width:100%;height:100%;background:#000;color:#e8e8e8;font-family:system-ui;overflow:hidden}'
        '#bar{position:fixed;top:0;left:0;right:0;padding:4px 10px;background:rgba(0,0,0,0.45);'
        'font-family:monospace;font-size:10px;letter-spacing:0.5px;z-index:99;'
        'opacity:0.25;transition:opacity 0.2s}'
        '#bar:hover{opacity:1;background:rgba(0,0,0,0.85)}'
        '#bar .lbl{color:#888;margin-right:6px}#bar .v{color:#4ade80;margin-right:18px}'
        '#frame{position:fixed;inset:0;width:100%;height:100%;border:0;background:#000}'
        '#empty{position:fixed;inset:0;background:#000}'
        '</style></head><body>'
        '<div id="bar"><span class="lbl">display</span><span class="v">' + display_id + '</span>'
        '<span class="lbl">url</span><span class="v" id="url">—</span>'
        '<span class="lbl">since</span><span class="v" id="since">—</span></div>'
        '<div id="empty"></div>'
        '<iframe id="frame" style="display:none"></iframe>'
        '<script>'
        'const did=' + did_json + ';let lastUrl=null;'
        'async function poll(){try{'
        'const r=await fetch("/api/v1/displays/"+did+"/state",{cache:"no-store"});'
        'const st=await r.json();'
        'const url=st&&st.payload&&st.payload.url?st.payload.url:null;'
        'document.getElementById("url").textContent=url||"—";'
        'document.getElementById("since").textContent=st&&st.since?st.since:"—";'
        'if(url!==lastUrl){'
        'const f=document.getElementById("frame"),e=document.getElementById("empty");'
        'if(url){f.src=url;f.style.display="block";e.style.display="none";}'
        'else{f.src="about:blank";f.style.display="none";e.style.display="flex";}'
        'lastUrl=url;}}catch(err){console.warn("poll",err);}}'
        'setInterval(poll,500);poll();'
        '</script></body></html>')


# ============================================================
#  Entrypoint (ROU-15 / ROU-16)
# ============================================================

DEFAULTS = {
    'listen_host':  '127.0.0.1',
    'listen_port':  5000,
    'log_level':    'INFO',
    'cdp_target':   '',
    'cdp_idle_url': 'about:blank',
}


def parse_args(argv):
    p = argparse.ArgumentParser(description='XBuddy Router V1')
    p.add_argument('--routing', default='routing.json', help='Pfad zur Routing-Tabelle (ROU-18)')
    p.add_argument('--config',  default='config.json',  help='Pfad zur Konfig (ROU-19)')
    p.add_argument('--host',    help='Bind-Host (überschreibt config + ENV)')
    p.add_argument('--port',    type=int, help='Bind-Port (überschreibt config + ENV)')
    p.add_argument('--log-level', dest='log_level', help='DEBUG | INFO | WARNING | ERROR')
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
    if args.host:      cfg['listen_host'] = args.host
    if args.port:      cfg['listen_port'] = args.port
    if args.log_level: cfg['log_level']   = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    logging.basicConfig(
        level=getattr(logging, cfg['log_level'].upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(message)s')
    runtime_config['cdp_target']   = cfg.get('cdp_target', '')
    runtime_config['cdp_idle_url'] = cfg.get('cdp_idle_url', 'about:blank')
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
