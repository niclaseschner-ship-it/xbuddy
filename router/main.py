#!/usr/bin/env python3
"""XBuddy Router V1 — siehe specs/platform/router.md (Refs #5).

Adapter ↔ Routing-Kern strikt getrennt (ROU-1). Nimmt POST /api/v1/events
entgegen, mappt Phone-Events 1:1 auf das kanonische Trigger-Modell
(ROU-6), löst per M:N-Tabelle aus routing.json (ROU-18) auf und hält
State pro Display in-memory (ROU-10).
"""

import argparse
import functools
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from urllib.parse import urlencode

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    make_response,
    redirect,
    request,
    send_from_directory,
)

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1, #179)
# auch beim Direktstart `python3 router/main.py` gefunden wird.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from router import config as router_config  # noqa: E402
from tools import configloader, logsetup  # noqa: E402
from tools.initdata import auth_gate as _auth_gate  # noqa: E402
from tools.initdata import session_cookie as _session_cookie  # noqa: E402
from tools.service_diagnostics import register_version  # noqa: E402

# ============================================================
#  Zustand (in-memory, V1)
# ============================================================

state = {}                # ROU-10: { display_id: {…} | None }
# Snapshot-Caches der zuletzt erfolgreich gelesenen routing.json. Sie sind
# NICHT mehr die Lookup-Wahrheit (DCOMP-2 / ROU-18: pro Aufruf frisch von
# Disk lesen) — siehe _current_routing(). Sie bleiben als „last-known-good"
# Fallback, wenn ein einzelner Read scheitert, und für den Admin-Reload-
# Endpoint (#140) als sichtbarer Reload-Marker.
routing_entries = []      # ROU-9 / ROU-18 Snapshot
panels = {}               # ROU-18 panels-Snapshot: source_id → { display_id }
known_displays = set()    # Snapshot der Vereinigung aller display_ids
routing_path = None       # zuletzt geladener Pfad — Lookup-Quelle (DCOMP-2)


def now_iso():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


# ============================================================
#  Routing-Kern (ROU-9 .. ROU-11)
# ============================================================

def lookup(source_id, descriptor):
    """Erster Match per Feld-Gleichheit. None wenn kein Eintrag passt.

    DCOMP-2 / ROU-18: liest die Routing-Einträge pro Aufruf frisch von
    Disk — Cross-Service-Schreibvorgänge (Eltern-Chat-Skills) werden
    sofort sichtbar, ohne Service-Restart und ohne Admin-Reload-Aufruf.
    """
    entries, _panels, _known = _current_routing()
    for entry in entries:
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


def apply_session_end(source_id):
    """ROU-11: alle Displays, deren State diese source_id trägt, auf null."""
    for did in list(state.keys()):
        s = state[did]
        if s and s.get('source_id') == source_id:
            state[did] = None
            # ROU-22: den null-Zustand an die offenen SSE-Streams melden.
            publish(did, None)


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
    danach jede Änderung. Heartbeats sind data-Events
    `{"type":"heartbeat"}` statt SSE-Comments, damit Mobile-Browser-
    EventSource sie als Lebenszeichen sieht (Browser sieht Comments nicht
    als message-Events, R6 aus Track-E 2026-06-18). Konsumenten (Panel-PWA-
    Watchdog, Pi-Watchdog) müssen den heartbeat-Typ ignorieren."""
    q = subscribe(display_id)
    try:
        yield sse_pack(state.get(display_id))      # Zustand beim Verbinden
        while True:
            try:
                s = q.get(timeout=SSE_HEARTBEAT_SECONDS)
            except queue.Empty:
                yield 'data: {"type":"heartbeat"}\n\n'
                continue
            yield sse_pack(s)
    finally:
        unsubscribe(display_id, q)


# ============================================================
#  Laufzeit-Konfig
# ============================================================

# Laufzeit-Konfig wird vom Entrypoint befüllt. Tests setzen direkt.
runtime_config = {
    'controller_dir':    '',              # ROU-23: leer = Default aus DEFAULT_CONTROLLER_DIR
    'icon_root':         '',              # ROU-26: leer = Default aus DEFAULT_ICON_ROOT
    'panel_service_url': '',             # ROU-27: leer = Default 127.0.0.1:5041
    'geraete_url':       '',             # ROU-29: leer = Default aus DEFAULT_GERAETE_URL
    'bot_token':         '',              # AUTH-7b: Cookie-Verifikation (Test-Naht/ENV)
}


# ============================================================
#  AUTH-7b — Dual-Gate-Decorator (Cookie ODER Operator-IP)
# ============================================================
#
# Spec-Anker: specs/platform/auth.md AUTH-7 (Dual-Gate, 495-504) +
# AUTH-3.a (Observe→Hard-Leiter, 237-281) + AUTH-8 (401-Anweisungsseite).
# Die pure Prüf-Mechanik (CIDR-Mitgliedschaft, Cookie-Verifikation) lebt
# Flask-frei in tools/initdata/auth_gate.py (RAT-16); dieser Decorator ist der
# Flask-Glue. Er wird — wie require_init_data (essen/…) und require_dual_gate
# in seiten/main.py — PRO SERVICE dupliziert (auth.md AUTH-5:347).

# AUTH-8: 401 rendert die Re-Pair-Anweisungsseite statt eines rohen Codes
# (7b-Public-Ausnahme, auth.md AUTH-7:510 — die 401-Antwort IST die Anweisung).
_DUAL_GATE_401_HTML = (
    "<!doctype html>\n"
    "<html lang=\"de\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    "<title>Gerät neu verbinden</title></head>"
    "<body style=\"font-family:system-ui,sans-serif;max-width:32rem;"
    "margin:3rem auto;padding:0 1rem;line-height:1.5\">"
    "<h1>Dieses Gerät muss neu verbunden werden.</h1>"
    "<p>Frag den Familien-Chatbot einfach nach einem neuen Cookie für dein "
    "Gerät — dann geht es wieder. Oder pair im Chat ein neues Gerät.</p>"
    "</body></html>"
)


def _get_bot_token():
    """Bot-Token für die Cookie-Verifikation (AUTH-7b), analog seiten.

    Reihenfolge: runtime_config (Test-Naht) → ELTERNCHAT_BOT_TOKEN
    (CONFIG-5-Schema aus eltern-chat/.env via systemd EnvironmentFile, #684) →
    TELEGRAM_BOT_TOKEN (Fallback-Name).
    """
    return (
        runtime_config.get('bot_token')
        or os.environ.get('ELTERNCHAT_BOT_TOKEN')
        or os.environ.get('TELEGRAM_BOT_TOKEN')
    )


def _client_ip():
    """Client-IP für die Operator-IP-Prüfung (AUTH-7 7a).

    `X-Real-IP` vom Origin-nginx ist die vertrauenswürdige Quelle (ESC-2:
    Router bindet 127.0.0.1 (router.service), nginx überschreibt den Header —
    ein externer Client kann die Operator-CIDR nicht spoofen). Fallback: erstes
    Token aus `X-Forwarded-For`; zuletzt `request.remote_addr`.
    """
    real_ip = request.headers.get('X-Real-IP', '').strip()
    if real_ip:
        return real_ip
    xff = request.headers.get('X-Forwarded-For', '').strip()
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr


# RAT-32 (Amendment RAT-27): ENV-Toggle für den Observe→Hard-Flip. Default
# 'observe' → verhaltensneutraler Deploy; `XBUDDY_AUTH_MODE=hard` flippt alle
# 7b-READ-Routen auf Cookie-only-hart. ENV+restart = Zwei-Wege-Tür in Sekunden
# (#1430-Lehre: der Rückroll ist KEIN Code-Revert). auth.md AUTH-3.a.
_AUTH_MODE = os.environ.get('XBUDDY_AUTH_MODE', 'observe')


def require_dual_gate(mode: str = 'observe'):
    """AUTH-7b-Decorator: Cookie-only-hart (auth.md AUTH-7 7b, RAT-32).

    `mode="observe"` (AUTH-3.a Soft-Rollout): fehlt eine valide Cookie-Quelle,
    läuft die Route trotzdem (`200`) und der Decorator LOGGT — kein `401`.

    `mode="hard"` (RAT-32, via `XBUDDY_AUTH_MODE=hard`): fehlt ein valider
    Cookie → `401` mit AUTH-8-Re-Pair-HTML. **Operator-IP (AUTH-7a) entfällt
    als Zugangs-Alternative** — der Cookie ist der einzige nicht-Loopback-Pfad.
    (Die PWA-Manifest-Public-Ausnahme lebt route-lokal in seiten, nicht hier:
    die Shell-PWA-Manifest-Route ist bereits ungegatet; das Display-Manifest ist
    Legacy-Vor-Shell und braucht keine Ausnahme.)

    Bei validem Cookie wird der Cookie rolling-refreshed (AUTH-2:78). Der
    Streaming-Fall (SSE) bleibt unversehrt: im Cookie-Pfad reicht `make_response`
    das bereits fertige Response-Objekt durch (kein Buffering des Generators).
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            bot_token = _get_bot_token()
            cookie_val = request.cookies.get(_session_cookie.COOKIE_NAME)
            cookie_ok = bool(bot_token) and _auth_gate.hat_gueltigen_cookie(
                cookie_val, bot_token)
            # RAT-32: Operator-IP entfällt als Zugangs-Alternative (AUTH-7a
            # gestrichen); ist_operator_ip nur noch fürs Observe-Log.
            operator_ok = _auth_gate.ist_operator_ip(_client_ip())

            if cookie_ok:
                subject = _session_cookie.verify_session(cookie_val, bot_token)
                resp = make_response(fn(*args, **kwargs))
                resp.set_cookie(
                    _session_cookie.COOKIE_NAME,
                    _session_cookie.sign_session(subject, bot_token),
                    **_session_cookie.session_cookie_kwargs(),
                )
                return resp

            if mode == 'hard':
                resp = make_response(_DUAL_GATE_401_HTML, 401)
                resp.headers['Content-Type'] = 'text/html; charset=utf-8'
                return resp
            logging.warning(
                "AUTH-3.a Observe (7b): %s — keine valide Quelle "
                "(cookie_vorhanden=%s, operator_ip=%s) → 200 (Grace, kein 401)",
                request.path, bool(cookie_val), operator_ok)
            return fn(*args, **kwargs)
        return wrapper
    return deco

# ROU-27 / PREG-9: Last-Known-Good-Cache für Panel-Instanz-Serving.
# Schlüssel: (panel_id, sicht) — sicht ist 'config.json' oder 'tiles.json'.
# Wert: (body_bytes, content_type) — zuletzt erfolgreich vom panel-Service geholt.
# Zugriff aus Flask-Threads (threaded=True) → Lock.
_panel_lkg_cache: dict = {}
_panel_lkg_lock = threading.Lock()

# Sichten, die der Router an den panel-Service proxyt (ROU-27, PREG-9).
_PANEL_PROXY_VIEWS = frozenset({'config.json', 'tiles.json'})

# Editor-Seite + Assets, die der Router an den panel-Service proxyt (PBE-1/PBE-2, T459).
# Kein LKG-Cache, kein Code-Default: 404 vom panel-Service wird durchgereicht.
_PANEL_BEARBEITEN_VIEWS = frozenset({'bearbeiten', 'bearbeiten.js', 'bearbeiten.css'})

# Content-Type-Mapping für die Bearbeiten-Views (PBE-2 / T459).
_PANEL_BEARBEITEN_CONTENT_TYPES = {
    'bearbeiten':     'text/html; charset=utf-8',
    'bearbeiten.js':  'application/javascript; charset=utf-8',
    'bearbeiten.css': 'text/css; charset=utf-8',
}

# ROU-31 / ICONS-7: Lazy-Cache für pictogram_cache.json (Wort→ID).
# Wird beim ersten Zugriff oder bei Wechsel der icon-root befüllt.
# Zugriff aus Flask-Threads → Lock.
_pictogram_cache: dict = {}          # {wort: id}
_pictogram_cache_root: str = ''      # icon-root, bei der der Cache befüllt wurde
_pictogram_cache_lock = threading.Lock()

_ICONS_SUCHE_MAX_CAP = 50           # obere Klemme für den max-Parameter

# panel-Service-Timeout beim Proxy-Abruf (Sekunden).
_PANEL_PROXY_TIMEOUT = 5

# Code-Default-Fallback für config.json/tiles.json wenn der panel-Service nie
# erreichbar war und kein LKG-Snapshot vorliegt (PREG-9 / PANEL-8, stiller Fallback).
_PANEL_CODE_DEFAULTS = {
    'config.json': b'{}',
    'tiles.json':  b'[]',
}


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
    2xx, Warnung, kein State-Update.

    DCOMP-2 / ROU-18: panels-Abschnitt wird pro Aufruf frisch von Disk
    gelesen — Skill-Schreibvorgänge an `routing.json` (z. B. neues Panel
    anlegen) werden ohne Restart sichtbar.
    """
    _entries, current_panels, _known = _current_routing()
    panel_entry = current_panels.get(source_id)
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


# ============================================================
#  Laden von Dateien (ROU-18 / ROU-19)
# ============================================================

class RoutingLoadError(Exception):
    """Wird vom strikten Reload-Pfad (#140) geworfen, wenn die Datei nicht
    gelesen oder geparst werden konnte. Der Start-Pfad (load_routing) fängt
    das ab und arbeitet weiter mit leerer Tabelle — der Reload-Pfad gibt
    den Fehler nach oben und lässt den alten State stehen (Atomarität)."""


def _parse_routing(path):
    """Liest und validiert routing.json und liefert ein Tupel
    (entries, panels, known_displays). Wirft RoutingLoadError bei IO- oder
    Parse-Fehler. Die Funktion ändert KEINEN globalen Zustand — das macht
    erst die aufrufende Schicht (load_routing oder reload_routing).

    Damit ist die Atomarität (E-RELOAD-1 / ROU-25, #140) sauber getrennt:
    solange diese Funktion einen Fehler wirft, hat der Router seinen alten
    State nicht verändert und beantwortet weitere Events wie zuvor."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise RoutingLoadError('routing.json nicht gefunden: %s' % path) from e
    except OSError as e:
        raise RoutingLoadError('routing.json nicht lesbar (%s): %s' % (path, e)) from e
    except json.JSONDecodeError as e:
        raise RoutingLoadError('routing.json nicht parsebar (%s): %s' % (path, e)) from e

    new_entries = data.get('entries', []) or []
    new_panels = {}
    new_known = set()
    for e in new_entries:
        # Migrations-Schutz: die alte Form `display_ids` (Plural) bleibt für
        # descriptor-basiertes Matching (ROU-9) gültig. Eine alte Form
        # `display_ids` im panels-Abschnitt würde E-PANEL-5 widersprechen —
        # darum wird der panels-Abschnitt strikt gegen Singular validiert.
        for d in e.get('display_ids', []):
            new_known.add(d)
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
                'panels[%s] nutzt petraltete Form `display_ids` (Plural); '
                'E-PANEL-5 verlangt `display_id` (Singular) — Eintrag ignoriert',
                source_id)
            continue
        display_id = entry.get('display_id')
        if not isinstance(display_id, str) or not display_id:
            logging.warning('panels[%s] ohne gültiges `display_id` — ignoriere', source_id)
            continue
        new_panels[source_id] = {'display_id': display_id}
        new_known.add(display_id)
    return new_entries, new_panels, new_known


def _install_routing(new_entries, new_panels, new_known):
    """Übernimmt die geparsten Daten in den Snapshot-Cache. Eigene Funktion,
    damit Start- und Admin-Reload-Pfad denselben Übernahme-Schritt nutzen
    (DRY). Lookups gehen NICHT mehr gegen diesen Cache, sondern via
    _current_routing() pro Aufruf frisch zur Disk (DCOMP-2)."""
    global routing_entries, panels, known_displays
    routing_entries = new_entries
    panels = new_panels
    known_displays = new_known
    logging.info('routing geladen: %d Einträge, %d Panels, %d Displays (%s)',
                 len(routing_entries), len(panels), len(known_displays),
                 ', '.join(sorted(known_displays)) or '—')


def _current_routing():
    """DCOMP-2 / ROU-18 Reload-on-Read: liest `routing.json` pro Aufruf frisch
    von Disk und liefert `(entries, panels, known_displays)`. Eltern-Chat-Skills
    schreiben Cross-Service in diese Datei; der Lookup-Pfad muss den neuen
    Stand ohne Service-Restart und ohne Admin-Reload-Aufruf sehen.

    Fehlertoleranz: scheitert der Read oder Parse (Datei kurz weg, atomares
    Replace im Halbschritt, kaputtes JSON), fällt der Aufruf auf den
    Snapshot-Cache zurück, der beim letzten erfolgreichen Load installiert
    wurde. Damit kippt der Router bei einem kurzen Race nicht in einen
    leeren Zustand — gleicher Geist wie der atomare Admin-Reload (E-RELOAD-1 / ROU-25).

    Ohne konfigurierten `routing_path` (z. B. unter Tests, die `load_routing`
    nicht aufgerufen haben) wird ebenfalls der Snapshot-Cache zurückgegeben.
    """
    if not routing_path:
        return routing_entries, panels, known_displays
    try:
        return _parse_routing(routing_path)
    except RoutingLoadError as e:
        logging.debug(
            'reload-on-read fiel auf snapshot zurück (%s); '
            'Lookup nutzt zuletzt erfolgreich geladenen Stand', e)
        return routing_entries, panels, known_displays


def load_routing(path):
    """Start-Pfad (ROU-18): bei Lesefehler wird mit leerer Tabelle gestartet —
    der Router läuft auch ohne routing.json an. Der Reload-Pfad (reload_routing)
    nutzt dieselbe Parse-Funktion, gibt Fehler aber nach oben durch."""
    global routing_path
    routing_path = path
    try:
        new_entries, new_panels, new_known = _parse_routing(path)
    except RoutingLoadError as e:
        logging.warning('%s — starte mit leerer Tabelle', e)
        _install_routing([], {}, set())
        return
    _install_routing(new_entries, new_panels, new_known)


def reload_routing():
    """Reload-Pfad (#140, E-RELOAD-1 / ROU-25): lädt die zuletzt gesetzte routing.json
    erneut. Bei Erfolg liefert die Funktion die Anzahl der übernommenen
    Einträge, bei Lade-/Parse-Fehler wirft sie RoutingLoadError — der globale
    State bleibt in diesem Fall unverändert (Atomarität).

    Die eigentliche Übernahme passiert erst NACH erfolgreichem Parsen; ein
    zerschossenes routing.json verfälscht damit weder routing_entries noch
    panels/known_displays."""
    if not routing_path:
        raise RoutingLoadError('kein routing.json-Pfad konfiguriert')
    new_entries, new_panels, new_known = _parse_routing(routing_path)
    _install_routing(new_entries, new_panels, new_known)
    return len(new_entries)


# ============================================================
#  Geräte-Validierung + panels-Schreib-Kante (ROU-29)
# ============================================================
#
# ROU-29 ist die konkrete panels-Schreib-Kante: der panel-Service ruft sie
# (PREG-16/PREG-17), um `source_id → { display_id }` in die routing.json zu
# schreiben. Vor dem Schreiben wird `display_id` gegen die Geräte-Registry
# validiert (GER-14, DCOMP-1 über HTTP) — NICHT gegen known_displays/die eigene
# routing.json, sonst würde ein frisch angelegtes Display abgelehnt, solange
# noch kein entries-Eintrag es referenziert (Muss-Korrektur 1 der Ratifizierung,
# symmetrisch zu PREG-7).

# Geräte-Registry-Default (GER/5040, PORT-2) — analog panel/main.py.
DEFAULT_GERAETE_URL = 'http://127.0.0.1:5040'

# ROU-29: parallele POSTs serialisieren, damit zwei verschiedene source_ids
# beide landen (kein lost update; symmetrisch zu PREG-15 / GER-15).
_panels_write_lock = threading.Lock()


def _geraete_base():
    """URL-Basis der Geräte-Registry (ROU-29). Konfigurierbar via runtime_config
    (geraete_url) / ENV ROUTER_GERAETE_URL / CLI --geraete-url.
    Default: http://127.0.0.1:5040 (GER, PORT-2)."""
    return runtime_config.get('geraete_url') or DEFAULT_GERAETE_URL


class _GeraeteUnreachable(Exception):
    """Die Geräte-Registry ist nicht erreichbar — ROU-29 → 503."""


class _PanelsWriteError(Exception):
    """Atomares Schreiben der routing.json schlug fehl — ROU-29 → 503.
    Die alte routing.json bleibt dabei unverändert (Temp + os.replace)."""


def display_existiert(display_id):
    """Prüft per HTTP gegen die Geräte-Registry, ob `display_id` existiert.

    GER-14 / ROU-29: `GET <geraete_url>/api/v1/geraete/<display_id>`. 200 →
    existiert (True), 404 → unbekannt (False). Jeder Transport- oder sonstige
    Fehler ist `_GeraeteUnreachable` (ROU-29 → 503): ein panels-Eintrag auf ein
    nicht validierbares Display zu schreiben ist keine sichere Default-Annahme.

    Bewusst über HTTP, KEIN Python-Import der Geräte-Komponente (DCOMP-1). Auf
    Modulebene, damit Tests sie stubben können (analog panel/main.py)."""
    base = _geraete_base().rstrip('/')
    url = '%s/api/v1/geraete/%s' % (base, display_id)
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        # Andere HTTP-Fehler (5xx der Geräte-Registry) sind kein „unbekannt",
        # sondern ein nicht-validierbarer Zustand → unreachable (503).
        raise _GeraeteUnreachable(
            'Geräte-Registry antwortet mit %s' % e.code) from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise _GeraeteUnreachable(str(e)) from e


def _write_panels_entry(source_id, display_id):
    """ROU-29: schreibt/aktualisiert genau EINEN panels-Eintrag in der
    routing.json (Read-Modify-Write des ganzen Objekts, entries unberührt) und
    schreibt atomar zurück (Temp-Datei + os.replace, DCOMP-4).

    Liest die aktuelle routing.json frisch von Disk (existiert sie nicht oder ist
    sie unparsebar, wird mit leerem Grundgerüst begonnen — der Router läuft auch
    ohne fertige Tabelle, ROU-18), ersetzt die eine `source_id`-Zeile im
    `panels`-Abschnitt und schreibt das Gesamtobjekt atomar. Bei IO-/Replace-
    Fehler bleibt die alte Datei unverändert und es wird `_PanelsWriteError`
    geworfen (ROU-29 → 503).

    Der Aufrufer hält `_panels_write_lock`, damit parallele POSTs serialisiert
    sind (kein lost update)."""
    if not routing_path:
        raise _PanelsWriteError('kein routing.json-Pfad konfiguriert')

    # Read: ganze Datei laden (Read-Modify-Write). Fehlt/kaputt → leeres
    # Grundgerüst, damit der erste panels-Eintrag auch ohne Tabelle landet.
    try:
        with open(routing_path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (FileNotFoundError, OSError, json.JSONDecodeError) as e:
        logging.warning(
            'routing.json für panels-Write nicht lesbar (%s) — beginne mit '
            'leerem Grundgerüst', e)
        data = {}

    # Modify: nur die eine panels-Zeile; entries bleibt unangetastet.
    raw_panels = data.get('panels')
    if not isinstance(raw_panels, dict):
        raw_panels = {}
    raw_panels[source_id] = {'display_id': display_id}
    data['panels'] = raw_panels

    # Write: atomar (Temp-Datei im Zielverzeichnis + os.replace, DCOMP-4) — ein
    # parallel laufender Lookup (ROU-9/ROU-24) sieht nie eine halb geschriebene
    # Datei. Bei Fehler wird die Temp-Datei aufgeräumt; die alte Datei bleibt.
    target_dir = os.path.dirname(os.path.abspath(routing_path)) or '.'
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix='.routing.', suffix='.json.tmp', dir=target_dir)
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')
        os.replace(tmp_path, routing_path)
    except OSError as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise _PanelsWriteError(
            'routing.json konnte nicht geschrieben werden: %s' % e) from e


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
    # Adapter über die Events, die er petrarbeitet (`tile_selected`,
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
    # DCOMP-2: known_displays pro Aufruf frisch berechnen — sonst sieht
    # der Endpoint ein neu via Skill geschriebenes Display nicht.
    _entries, _panels, current_known = _current_routing()
    if display_id not in current_known:
        return jsonify({'error': 'unknown display'}), 404
    return jsonify(state.get(display_id))


@app.route('/api/v1/displays/<display_id>/events', methods=['GET'])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-7b: Cookie-only-hart (RAT-32), ENV-getoggelt (SSE, initial Observe)
def display_events(display_id):
    # ROU-22: SSE-Zustands-Stream. Unbekannte id → 404 (wie ROU-12).
    # DCOMP-2: frisch lesen, damit neu angelegte Displays auch hier
    # sofort verbindungsbereit sind.
    _entries, _panels, current_known = _current_routing()
    if display_id not in current_known:
        return jsonify({'error': 'unknown display'}), 404
    resp = app.response_class(display_event_stream(display_id),
                              mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


# ============================================================
#  ROU-32 — GET /api/v1/router/panels/<source_id> — Panel→Display-Lookup
# ============================================================
#
# Liefert die display_id aus dem panels-Abschnitt der routing.json (ROU-18)
# für eine gegebene source_id. Der Panel-Code zieht damit beim Bootstrap
# die display_id vom Router — kein Spiegel in config.json, kein Drift
# möglich (Nic-Entscheid 2026-06-08 / #414, PANEL-8/PANEL-11).

@app.route('/api/v1/router/panels/<source_id>', methods=['GET'])
def get_panel_display(source_id):
    # DCOMP-2: frisch von Disk lesen, damit skill-seitige Änderungen sofort sichtbar.
    _entries, current_panels, _known = _current_routing()
    panel_entry = current_panels.get(source_id)
    if panel_entry is None:
        return jsonify({'error': 'unknown source_id'}), 404
    return jsonify({'display_id': panel_entry['display_id']})


# ============================================================
#  Admin: Reload (#140, EC-21)
# ============================================================
#
# Eltern-Chat-Skills schreiben routing.json (z. B. „App einbinden") und müssen
# danach den Router zur Übernahme zwingen — EC-21 verlangt, dass Änderungen
# „sofort und ehrlich" wirken. Ohne Reload-Aufruf bliebe der Router auf seinem
# In-Memory-State stehen und das Eltern-Versprechen wäre eine Lüge.
#
# Drei harte Eigenschaften:
#   1. Loopback-only (`request.remote_addr == 127.0.0.1`) — andere Aufrufer
#      bekommen HTTP 403. Der Endpoint ist ein Admin-Werkzeug, kein API.
#   2. Atomar: bei Lade-/Parse-Fehler bleibt der alte State unverändert
#      (siehe _parse_routing — die Übernahme passiert erst NACH erfolgreichem
#      Parsen).
#   3. nginx-Origin leitet `/api/v1/<komponente>/admin/...` NICHT weiter
#      (siehe deploy/nginx/xbuddy-origin.conf) — Defense in Depth, der
#      Loopback-Guard hier ist die zweite Schicht.

# Zulässige Aufrufer-Adressen. IPv4-Loopback (127.0.0.1) und IPv6-Loopback (::1)
# — der Flask-Testclient setzt 127.0.0.1, ein lokaler `curl` auf den Server
# je nach Stack auch ::1. Beide sind dasselbe physische Interface.
_RELOAD_ALLOWED_REMOTES = {'127.0.0.1', '::1'}


def _is_loopback(remote_addr):
    """Ein Aufruf gilt als loopback, wenn er aus 127.0.0.1 oder ::1 stammt.
    Reverse-Proxy-Forwarding (X-Forwarded-For) wird absichtlich ignoriert —
    der Loopback-Guard prüft, wer wirklich angeklopft hat, nicht was der
    Header behauptet."""
    return remote_addr in _RELOAD_ALLOWED_REMOTES


@app.route('/api/v1/router/admin/reload', methods=['POST'])
def admin_reload():
    if not _is_loopback(request.remote_addr or ''):
        # 403 statt 404, damit Bedienfehler im LAN sichtbar sind: ein Aufruf
        # aus dem Netz von außen bekommt ein klares „nicht erlaubt", kein
        # diffuses „gibts nicht".
        logging.warning('admin/reload abgelehnt: remote_addr=%s', request.remote_addr)
        return jsonify({
            'reloaded': False,
            'error':    'nur 127.0.0.1 darf den Endpoint erreichen',
        }), 403
    try:
        n = reload_routing()
    except RoutingLoadError as e:
        # Atomarität: alter State steht unverändert weiter — der Router
        # beantwortet Events nach dem Fehler wie vor dem Aufruf.
        logging.warning('admin/reload fehlgeschlagen: %s', e)
        return jsonify({
            'reloaded': False,
            'error':    str(e),
        }), 500
    return jsonify({
        'reloaded': True,
        'details':  'routing.json reloaded (%d Einträge)' % n,
    }), 200


# ============================================================
#  Admin: panels-Eintrag schreiben (ROU-29) — POST /api/v1/router/admin/panels/
# ============================================================
#
# Zweite, konkrete Ausprägung der loopback-/`/admin/`-Invariante aus ROU-28
# (die erste ist der Admin-Reload oben). Der panel-Service ruft diese Kante für
# die 2-Schritt-Anlage und den Reconcile-Pfad (panel-registry.md PREG-16/PREG-17),
# um `source_id → { display_id }` in die routing.json zu schreiben. Loopback-only
# (gleicher _is_loopback-Guard); nginx blockt /admin/ zusätzlich von außen.

@app.route('/api/v1/router/admin/panels/', methods=['POST'])
def admin_write_panel():
    # ROU-28: loopback-only, gleicher Guard und gleiche 403-Form wie admin_reload.
    if not _is_loopback(request.remote_addr or ''):
        logging.warning('admin/panels abgelehnt: remote_addr=%s', request.remote_addr)
        return jsonify({
            'written': False,
            'error':   'nur 127.0.0.1 darf den Endpoint erreichen',
        }), 403

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'JSON-Body fehlt oder ungültig'}), 400

    # ROU-29 / E-PANEL-5: Singular `display_id` erzwingen. Die petraltete
    # Plural-Form `display_ids` ist eine Schema-Verletzung (ROU-5-Form, 400),
    # damit sie gar nicht erst in die Datei gelangt.
    if 'display_ids' in body:
        return jsonify({'error': 'display_ids'}), 400
    source_id = body.get('source_id')
    if not isinstance(source_id, str) or not source_id:
        return jsonify({'error': 'source_id'}), 400
    display_id = body.get('display_id')
    if not isinstance(display_id, str) or not display_id:
        return jsonify({'error': 'display_id'}), 400

    # ROU-29: display_id gegen die Geräte-Registry validieren (GER-14, HTTP) —
    # NICHT gegen known_displays. Unbekannt → 400, Registry nicht erreichbar →
    # 503 (routing.json bleibt unverändert, kein stilles Durchwinken).
    try:
        if not display_existiert(display_id):
            return jsonify({'error': 'display unbekannt'}), 400
    except _GeraeteUnreachable as e:
        logging.warning('admin/panels: Geräte-Registry nicht erreichbar: %s', e)
        return jsonify({'error': 'Geräte-Registry nicht erreichbar'}), 503

    # ROU-29: parallele POSTs serialisieren (kein lost update); atomar schreiben.
    # IO-/Replace-Fehler → 503, routing.json bleibt unverändert.
    try:
        with _panels_write_lock:
            _write_panels_entry(source_id, display_id)
    except _PanelsWriteError as e:
        logging.warning('admin/panels: Schreiben fehlgeschlagen: %s', e)
        return jsonify({'error': str(e)}), 503

    logging.info('admin/panels: %s → %s geschrieben', source_id, display_id)
    return jsonify({
        'written':    True,
        'source_id':  source_id,
        'display_id': display_id,
    }), 200


# ============================================================
#  Admin: tiles-changed (PBE-10 / #450)
# ============================================================
#
# Empfänger-Endpoint für das SSE-Publish-Signal des Panel-Editors.
# Der Panel-Editor ruft nach einem erfolgreichen PBE-4-Schreibvorgang
# POST .../tiles-changed (leerer Body) auf. Dieser Endpoint ruft intern
# publish(display_id, state.get(display_id)) auf, was das SSE-Ereignis
# an alle offenen Stream-Abonnenten des Displays verteilt.
# Loopback-only (ROU-28-Invariante, gleicher Guard wie admin_reload /
# admin_write_panel). Latenz lokaler Round-Trip << 5 s (PBE-10-Schranke).

@app.route('/api/v1/router/admin/panels/<display_id>/tiles-changed', methods=['POST'])
def admin_tiles_changed(display_id):
    # ROU-28: loopback-only, gleicher Guard wie admin_reload und admin_write_panel.
    if not _is_loopback(request.remote_addr or ''):
        logging.warning('admin/tiles-changed abgelehnt: remote_addr=%s', request.remote_addr)
        return jsonify({
            'error': 'nur 127.0.0.1 darf den Endpoint erreichen',
        }), 403

    # DCOMP-2: frisch von Disk lesen — damit neu angelegte Displays sofort bekannt sind.
    _entries, _panels, current_known = _current_routing()
    if display_id not in current_known:
        return jsonify({'error': 'unknown display'}), 404

    publish(display_id, state.get(display_id))
    logging.info('admin/tiles-changed: publish für display_id=%r ausgeführt', display_id)
    return '', 204


@app.route('/api/v1/diag', methods=['GET'])
def diag():
    # DCOMP-2: Diag spiegelt den aktuellen Lese-Stand — frisch von Disk.
    current_entries, _panels, current_known = _current_routing()
    rows = []
    for did in sorted(current_known):
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
            ', '.join(sorted(current_known)) or '(keine)',
            len(current_entries),
            ''.join(rows) or '<p>(noch nichts)</p>')


# ============================================================
#  Diagnose: /health (Fan-in) + /version (SVC-6)
# ============================================================
#
# SVC-6: Jeder HTTP-Service exponiert `/healthz` (Readiness) und `/version`
# (Deploy-SHA). Der Router aggregiert die Per-Service-`/healthz` zu einem
# Fan-in-`/health` — echter Loopback-Ping der Upstreams statt der bisherigen
# 404-Doku-Fiktion (deploy/nginx/README.md dokumentierte `/health`, der Router
# lieferte real 404). T1311/#1311.
#
# Der Upstream-Katalog ist ein Spiegel von conventions/ports.md PORT-2 — dort
# steht die Wahrheit (PORT-1: nicht der Code als wahre Quelle). Hier nur die
# Loopback-Ziele des Fan-ins, verbatim aus PORT-2 übernommen: ohne den
# Router-Selbstport (5000 — der Router beantwortet diesen Request selbst) und
# ohne eltern-chat (kein HTTP-Port, PORT-2/systemd-README).

_HEALTH_UPSTREAMS = (
    (5010, 'xbuddy-familie'),
    (5020, 'xbuddy-plan'),
    (5030, 'xbuddy-wetter'),
    (5040, 'xbuddy-geraete'),
    (5041, 'xbuddy-panel'),
    (5042, 'xbuddy-seiten'),
    (5050, 'xbuddy-routine'),
    (5051, 'xbuddy-photo'),
    (5052, 'xbuddy-essen'),
    (5053, 'xbuddy-hoerspiel'),
    (5054, 'xbuddy-kibuddy'),
    (5055, 'xbuddy-hoerspiel-finn'),
)

# Loopback ist schnell; ein hängender Upstream darf den Fan-in nicht blockieren.
_HEALTH_PROBE_TIMEOUT = 2


def _probe_healthz(port):
    """Pingt http://127.0.0.1:<port>/healthz (SVC-6) und klassifiziert:

    - reachable: der Prozess antwortet überhaupt (Connect + HTTP-Antwort).
    - healthz:   HTTP-Code der Antwort (oder None bei Connect-Fehler).
    - healthy:   healthz == 200.

    Ein 404 heißt „Prozess läuft, aber der SVC-6-`/healthz` fehlt noch"
    (Rollout offen) → reachable=True, healthy=False. Connection-refused/Timeout
    → reachable=False (Prozess tot / bindet nicht)."""
    url = 'http://127.0.0.1:%d/healthz' % port
    try:
        with urllib.request.urlopen(url, timeout=_HEALTH_PROBE_TIMEOUT) as resp:
            code = resp.status
    except urllib.error.HTTPError as e:
        # HTTP-Antwort erhalten (404/5xx) → Prozess lebt, Endpoint-Status != ok.
        code = e.code
    except (urllib.error.URLError, OSError):
        return {'reachable': False, 'healthz': None, 'healthy': False}
    return {'reachable': True, 'healthz': code, 'healthy': code == 200}


@app.route('/health', methods=['GET'])
def health():
    """SVC-6 Fan-in: echter Loopback-Status aller Upstreams (PORT-2).

    200, wenn jeder Upstream-Prozess erreichbar ist; sonst 503 (mindestens
    einer bindet nicht / ist tot). Der Router selbst ist implizit ok — er
    beantwortet diesen Request. Kein 404 mehr (AC1)."""
    upstreams = []
    all_reachable = True
    for port, name in _HEALTH_UPSTREAMS:
        probe = _probe_healthz(port)
        if not probe['reachable']:
            all_reachable = False
        upstreams.append({
            'service':   name,
            'port':      port,
            'reachable': probe['reachable'],
            'healthz':   probe['healthz'],
            'healthy':   probe['healthy'],
        })
    body = {
        'status':     'ok' if all_reachable else 'degraded',
        'checked_at': now_iso(),
        'upstreams':  upstreams,
    }
    return jsonify(body), (200 if all_reachable else 503)


# /version teilt sich die EINE Naht mit allen 11 Buddy-Services (T1311/#1311):
# tools/service_diagnostics.register_version — file-based, kein git rev-parse
# (SVC-6). Der /health-Fan-in oben bleibt Router-eigen.
register_version(app)


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

# ROU-23: controller/_shared/ liefert PWA-übergreifende Helper (z.B. config.js,
# `conventions/pwa.md` PWA-4 Implementierungs-Naht). Wird von
# /controller/_shared/<asset> ausgeliefert, parallel zu /controller/<app>/.
DEFAULT_CONTROLLER_SHARED_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'controller', '_shared'))

# ROU-30 / DTOK-1 / DTOK-2: der geteilte Design-Token-Strang
# (display/_shared/design/tokens.css) wird unter /display/_shared/design/
# read-only aus dem Repo ausgeliefert — Zwilling zu /controller/_shared/
# (ROU-23, Repo-Inhalt), NICHT zu /display/_shared/icons/ (ROU-26, die als
# Per-Instanz-Daten außerhalb des Repos liegen). Design-Tokens sind die Marke:
# bei allen Familien identisch, mit dem Code versioniert (#323).
DEFAULT_DISPLAY_SHARED_DESIGN_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'display', '_shared', 'design'))

# ROU-26 / ICONS-2: die zentrale Icon-Bibliothek (ARASAAC-Piktogramme) wird
# unter /display/_shared/icons/ ausgeliefert — Zwilling zu /controller/_shared/
# (ROU-23). Anders als die Controller-Helper liegt die icon-root als
# Per-Instanz-Daten AUSSERHALB des Repos (Default /home/buddy/apps/icons/);
# der Router liest sie als User `buddy` problemlos, während ein statischer
# nginx-`alias` an der 0700-Home-Permission (nginx=www-data) scheiterte (#135).
DEFAULT_ICON_ROOT = '/home/buddy/apps/icons/'

# Explizites Content-Type-Mapping. Browser entscheiden anhand des Headers,
# nicht anhand der Endung — ein .json mit text/html würde das Manifest
# verwerfen, ein .js mit text/plain die SW-Registrierung scheitern lassen.
_CONTROLLER_MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js':   'application/javascript',
    '.json': 'application/manifest+json',
    '.png':  'image/png',
    '.css':  'text/css',
}


def controller_dir():
    return runtime_config.get('controller_dir') or DEFAULT_CONTROLLER_DIR


def icon_root():
    # ROU-26: konfigurierbare icon-root (ICONS-2). Leer = Default.
    return runtime_config.get('icon_root') or DEFAULT_ICON_ROOT


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


def _send_shared_asset(rel_path):
    # ROU-23: PWA-übergreifender Helper-Pfad (controller/_shared/), parallel
    # zur App-spezifischen controller/<app>/. Defense in Depth analog
    # _send_controller_asset.
    root = os.path.realpath(DEFAULT_CONTROLLER_SHARED_DIR)
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _CONTROLLER_MIME.get(ext, 'application/octet-stream')
    return send_from_directory(root, rel_path, mimetype=mime)


@app.route('/controller/_shared/<path:asset>', methods=['GET'])
def controller_shared_asset(asset):
    # ROU-23: /controller/_shared/<asset> aus controller/_shared/.
    # conventions/pwa.md PWA-4-Implementierungs-Naht.
    return _send_shared_asset(asset)


def _send_icon_asset(rel_path):
    # ROU-26: geteilte Display-Assets (Icon-Bibliothek) aus der icon-root
    # (ICONS-2), Zwilling zu _send_shared_asset (ROU-23). Defense in Depth:
    # werkzeug safe_join + expliziter realpath-Check gegen Path-Traversal.
    root = os.path.realpath(icon_root())
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _CONTROLLER_MIME.get(ext, 'application/octet-stream')
    return send_from_directory(root, rel_path, mimetype=mime)


def _send_design_asset(rel_path):
    # ROU-30: geteilter Design-Token-Strang aus dem In-Repo-Verzeichnis
    # display/_shared/design/, Zwilling zu _send_shared_asset (ROU-23,
    # Repo-Inhalt). Anders als _send_icon_asset (ROU-26) liegt die Wurzel im
    # Repo, nicht in der Per-Instanz-icon-root. Defense in Depth: werkzeug
    # safe_join (via send_from_directory) + expliziter realpath-Check.
    root = os.path.realpath(DEFAULT_DISPLAY_SHARED_DESIGN_DIR)
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _CONTROLLER_MIME.get(ext, 'application/octet-stream')
    return send_from_directory(root, rel_path, mimetype=mime)


@app.route('/display/_shared/design/<path:asset>', methods=['GET'])
def display_shared_design(asset):
    # ROU-30 / URL-16 / DTOK-1 / DTOK-2: read-only-Auslieferung des geteilten
    # Design-Token-Strangs unter /display/_shared/design/<asset> aus dem
    # In-Repo-Verzeichnis display/_shared/design/. Zwilling zu
    # /controller/_shared/ (ROU-23, Repo-Inhalt) — abzugrenzen von
    # /display/_shared/icons/ (ROU-26, Per-Instanz-Daten außerhalb des Repos).
    return _send_design_asset(asset)


@app.route('/display/_shared/icons/<path:asset>', methods=['GET'])
def display_shared_icon(asset):
    # ROU-26 / URL-16 / ICONS-5: read-only-Auslieferung der zentralen
    # Icon-Bibliothek unter /display/_shared/icons/<source>/<id>.png aus der
    # icon-root. Zwilling zu /controller/_shared/ (ROU-23). Die Assets sind
    # Per-Instanz-Daten außerhalb des Repos (ICONS-2).
    return _send_icon_asset(asset)


def _load_pictogram_cache():
    """ROU-31 / ICONS-7: Liefert den Wort→ID-Cache aus pictogram_cache.json.

    Lazy: wird beim ersten Aufruf oder bei geänderter icon-root geladen.
    Gibt ein leeres Dict zurück, wenn die Datei fehlt (Icon-root noch nicht
    geseedet — kein Fehler, Suche liefert dann []). Thread-sicher via Lock.
    """
    global _pictogram_cache, _pictogram_cache_root
    current_root = icon_root()
    with _pictogram_cache_lock:
        if _pictogram_cache_root == current_root and _pictogram_cache:
            return _pictogram_cache
        cache_path = os.path.join(current_root, 'pictogram_cache.json')
        try:
            with open(cache_path, encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        _pictogram_cache = data
        _pictogram_cache_root = current_root
        return _pictogram_cache


def _score_match(needle: str, word: str) -> float:
    """Match-Score: exact > prefix > word-boundary > substring.

    Längen-Bonus: kürzere Wörter ranken höher (einfacher = bessere ARASAAC-Treffer).
    Prefix-Stufe ist einheitlich (kein Extra für Space-nach-Needle), damit ein
    kurzes Einzel-Wort wie 'menschen' vor einem langen Mehrwort-Phrase wie
    'mensch ärgere dich nicht' landet — der Längen-Bonus entscheidet.
    Returns 0.0 wenn kein Substring-Match (Wort wird ausgeschlossen).
    """
    needle = needle.lower()
    w = word.lower()
    if needle not in w:
        return 0.0
    if w == needle:
        return 1000.0  # exact match
    if w.startswith(needle):
        return 400.0 + 100.0 / max(len(w), 1)  # prefix (kurzes Wort gewinnt via Längen-Bonus)
    if (' ' + needle) in w or ('-' + needle) in w:
        return 100.0 + 50.0 / max(len(w), 1)   # word-boundary in mid-string
    # reine Substring (mid-string ohne word-boundary)
    return 1.0 + 1.0 / max(len(w), 1)


@app.route('/api/v1/icons/suche', methods=['GET'])
def icons_suche():
    """ROU-31 / ICONS-7 / URL-4: Stichwort-Suche über den lokalen Icon-Cache.

    GET /api/v1/icons/suche?q=<stichwort>&max=<n>
    → 200, JSON [{id: int, url: str}], nur IDs mit lokalem PNG.
    400 ohne q. Leere Treffer → 200 [].
    """
    q = request.args.get('q')
    if q is None:
        abort(400)

    try:
        max_results = int(request.args.get('max', 3))
    except (ValueError, TypeError):
        max_results = 3
    max_results = max(1, min(max_results, _ICONS_SUCHE_MAX_CAP))

    # min_score Threshold (Live-Befund 2026-06-15): bei Single-Token-Queries
    # ist ein reiner Substring-Match irreführend ("höhe" findet "erhöhen" mit
    # Score ~1.x — Pikto passt nicht zum Konzept). Default-Schwelle 100
    # akzeptiert exact (1000), prefix (~412), word-boundary (~106), schließt
    # reine Substring-Mid-String aus. Konsumenten können 0 setzen für altes
    # Verhalten (Mehrwort-Routine bleibt unverändert, weil token_hits primär).
    try:
        min_score = float(request.args.get('min_score', 100))
    except (ValueError, TypeError):
        min_score = 100.0

    # ICONS-7 Mehrwort: Whitespace-Split; leere Tokens raus.
    tokens = q.split()
    if not tokens:
        return jsonify([])

    cache = _load_pictogram_cache()

    # Pro Token: Match-Qualitäts-Score (ICONS-7 Match-Score-Refactor).
    # token_hits(id) = Anzahl Tokens, die die ID treffen (primäre Sortierdimension).
    # score(id) additiv über Tokens (sekundär, entscheidet Qualität innerhalb gleicher Copetrage).
    # first_seen für Cache-Reihenfolge-Tiebreaker (tertiär).
    score: dict = {}
    token_hits: dict = {}
    first_seen: dict = {}
    for _ti, token in enumerate(tokens):
        matched_this_token: set = set()
        for idx, (word, icon_id) in enumerate(cache.items()):
            if icon_id in matched_this_token:
                continue
            match_score = _score_match(token, word)
            if match_score > 0:
                matched_this_token.add(icon_id)
                if icon_id not in first_seen:
                    first_seen[icon_id] = idx
                score[icon_id] = score.get(icon_id, 0.0) + match_score
                token_hits[icon_id] = token_hits.get(icon_id, 0) + 1

    # min_score-Filter: schließt zu schwache Substring-Matches aus
    # (Single-Token-Live-Befund "höhe → erhöhen" Pikto irreführend).
    qualified_ids = [i for i in score if score[i] >= min_score]

    # Primär: Token-Copetrage absteigend (wer mehr Tokens matcht, gewinnt).
    # Sekundär: Score absteigend (Qualität innerhalb gleicher Copetrage).
    # Tertiär: Cache-Reihenfolge (first_seen aufsteigend) als Tiebreaker.
    sorted_ids = sorted(
        qualified_ids,
        key=lambda i: (-token_hits[i], -score[i], first_seen[i]),
    )

    # Nur IDs mit lokalem PNG (ICONS-7 / AC4); Pfad-/Wurzel-Schutz wie ROU-26.
    root = os.path.realpath(icon_root())
    results = []
    for icon_id in sorted_ids:
        if len(results) >= max_results:
            break
        rel = os.path.join('arasaac', f'{icon_id}.png')
        target = os.path.realpath(os.path.join(root, rel))
        # Wurzel-Schutz: target muss innerhalb von root liegen (defensiv).
        if not (target == root or target.startswith(root + os.sep)):
            continue
        if os.path.isfile(target):
            results.append({
                'id': icon_id,
                'url': f'/display/_shared/icons/arasaac/{icon_id}.png',
            })

    return jsonify(results)


@app.route('/controller/<app>/', methods=['GET'])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-7b: Cookie-only-hart (RAT-32), ENV-getoggelt (Controller-Index, initial Observe)
def controller_index(app):
    # ROU-23: /controller/<app>/ → index.html mit text/html.
    # Nur der konfigurierte App-Slug ist gültig (URL-3, zwei Segmente).
    if app != controller_app_slug():
        abort(404)
    return _send_controller_asset('index.html')


@app.route('/controller/<app>/<path:asset>', methods=['GET'])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-7b: Cookie-only-hart (RAT-32), ENV-getoggelt (Controller-Assets, initial Observe)
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


def _panel_service_base():
    """URL-Basis des panel-Service (ROU-27). Konfigurierbar via runtime_config
    (panel_service_url) / ENV ROUTER_PANEL_SERVICE_URL / CLI --panel-service-url.
    Default: http://127.0.0.1:5041 (PORT-2)."""
    return runtime_config.get('panel_service_url') or 'http://127.0.0.1:5041'


def _proxy_panel_view(panel_id, sicht):
    """ROU-27 / PREG-9: holt config.json oder tiles.json vom panel-Service und
    liefert (body_bytes, content_type). Bei Erfolg frischt die Funktion den
    Last-Known-Good-Cache; bei Ausfall (Timeout, 5xx, Connection-Fehler) greift
    sie auf den LKG-Snapshot zurück. Fehlt auch der Snapshot, kommt der
    Code-Default-Fallback (PREG-9 / PANEL-8, kein Crash).

    Sicht muss ein Element aus _PANEL_PROXY_VIEWS sein."""
    url = '%s/api/v1/panels/%s/%s' % (_panel_service_base(), panel_id, sicht)
    cache_key = (panel_id, sicht)
    content_type = 'application/json'
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=_PANEL_PROXY_TIMEOUT) as resp:
            if resp.status >= 400:
                raise urllib.error.HTTPError(
                    url, resp.status, 'panel-Service Fehler', {}, None)
            body = resp.read()
        # Erfolg — LKG-Snapshot frischt
        with _panel_lkg_lock:
            _panel_lkg_cache[cache_key] = (body, content_type)
        return body, content_type
    except Exception as exc:
        logging.warning(
            'ROU-27: panel-Service nicht erreichbar (%s/%s): %s — LKG/Fallback',
            panel_id, sicht, exc)
    # LKG-Snapshot
    with _panel_lkg_lock:
        cached = _panel_lkg_cache.get(cache_key)
    if cached is not None:
        return cached
    # Code-Default-Fallback (PANEL-8, stiller Fallback — kein Crash)
    return _PANEL_CODE_DEFAULTS[sicht], content_type


def _proxy_panel_bearbeiten(panel_id, sicht):
    """PBE-1/PBE-2 / T459: holt bearbeiten / bearbeiten.js / bearbeiten.css
    vom panel-Service und liefert (body_bytes, content_type, status_code).

    Anders als _proxy_panel_view gibt es hier KEINEN LKG-Cache und keinen
    Code-Default-Fallback: ein 404 vom panel-Service wird als (body, ct, 404)
    durchgereicht, damit der Browser das korrekte HTTP-Signal erhält (AC3).
    Netz-Fehler / 5xx liefern 502."""
    # Editor-Seite hängt am /controller/app-panel/-Pfad des panel-Service
    # (T446 PBE-1 baut die Route dort: `panel/main.py` get_panel_editor /
    # get_panel_editor_js / get_panel_editor_css), NICHT unter /api/v1/panels/.
    # Production-Bug entdeckt 2026-06-08 nach T459-Merge: urllib-Mock-Tests
    # haben die URL-Form nicht geprüft → Router gab 404 für Browser-Requests.
    url = '%s/controller/app-panel/%s/%s' % (_panel_service_base(), panel_id, sicht)
    content_type = _PANEL_BEARBEITEN_CONTENT_TYPES.get(sicht, 'application/octet-stream')
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=_PANEL_PROXY_TIMEOUT) as resp:
            body = resp.read()
        return body, content_type, 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            body = exc.read() if hasattr(exc, 'read') else b''
            return body, 'application/json', 404
        logging.warning(
            'PBE proxy: panel-Service antwortet mit %s für %s/%s',
            exc.code, panel_id, sicht)
        return b'', 'application/json', 502
    except Exception as exc:
        logging.warning(
            'PBE proxy: panel-Service nicht erreichbar (%s/%s): %s',
            panel_id, sicht, exc)
        return b'', 'application/json', 502


def app_panel_dir():
    # Defense in Depth: realpath, damit symbolische Links keine traversierung
    # aus dem Wurzelverzeichnis erlauben.
    return DEFAULT_APP_PANEL_DIR


def _app_panel_build_id():
    """PANEL-14: build_id aus max(mtime) des vollständigen cache-relevanten
    Runtime-Asset-Satzes (7 Pfade: app.js, style.css, sw.js, manifest.json,
    silent.mp3, controller/_shared/config.js, display/_shared/design/tokens.css).

    Begründung des vollen Satzes: config.js und tokens.css werden von index.html
    referenziert und vom Service-Worker precacht (E-PANEL-6, sw.js STATIC_ASSETS)
    — bei Ableitung nur aus CSS/JS bliebe ein geändertes Token- oder Config-Asset
    unsichtbar (build_id unveränderlich, Stale-Asset überlebt).

    OSError-Fallback: '0' (analog seiten/_mini_app_build_id)."""
    panel_dir = app_panel_dir()
    asset_paths = [
        os.path.join(panel_dir, 'app.js'),
        os.path.join(panel_dir, 'style.css'),
        os.path.join(panel_dir, 'sw.js'),
        os.path.join(panel_dir, 'manifest.json'),
        os.path.join(panel_dir, 'silent.mp3'),
        os.path.join(DEFAULT_CONTROLLER_SHARED_DIR, 'config.js'),
        os.path.join(DEFAULT_DISPLAY_SHARED_DESIGN_DIR, 'tokens.css'),
    ]
    try:
        return str(int(max(os.path.getmtime(p) for p in asset_paths)))
    except OSError:
        return '0'


def _send_app_panel_asset(rel_path):
    root = os.path.realpath(app_panel_dir())
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _CONTROLLER_MIME.get(ext)
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
    der `source_id` aus config.json.

    PANEL-14: ersetzt außerdem alle __BUILD_ID__-Platzhalter in den Asset-URLs
    durch die aktuelle build_id (max mtime des Runtime-Asset-Satzes, vgl.
    _app_panel_build_id). Keine zweite Templating-Schicht — beide Token-
    Ersetzungen laufen über diesen bestehenden Seam."""
    index_path = os.path.join(app_panel_dir(), 'index.html')
    with open(index_path, encoding='utf-8') as f:
        html = f.read()
    # Token-Substitution analog T452-S2: das echte <body>-Tag in index.html
    # trägt `data-panel-id="__PANEL_ID__"`. Wir ersetzen das Token — kein
    # Substring-Match auf `<body>`, damit HTML-Kommentare nicht versehentlich
    # gematcht werden und das echte Tag leer bleibt.
    # IDENT-5 — Server-side-Identitäts-Token in HTML-Templates.
    build_id = _app_panel_build_id()
    return (html
            .replace('__PANEL_ID__', panel_id, 1)
            .replace('__BUILD_ID__', build_id))


@app.route('/controller/app-panel/<panel_id>', methods=['GET'])
def app_panel_index_no_slash(panel_id):
    # Relative Asset-Pfade in index.html (./app.js, ./manifest.json, …) brauchen
    # einen Trailing-Slash, sonst resolvt der Browser ./ auf den Parent und
    # holt /controller/app-panel/app.js (HTML-Fallback) statt
    # /controller/app-panel/<id>/app.js. 301 → /<id>/ ist HTTP-Standard
    # für Directory-vs-File-Disambiguation. Refs #128.
    return redirect('/controller/app-panel/' + panel_id + '/', code=301)


@app.route('/controller/app-panel/<panel_id>/', methods=['GET'])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-7b: Cookie-only-hart (RAT-32), ENV-getoggelt (App-Panel-Index, initial Observe)
def app_panel_index_slash(panel_id):
    return render_app_panel_index(panel_id), 200, {
        'Content-Type': 'text/html; charset=utf-8'}


@app.route('/controller/app-panel/<panel_id>/<path:asset>', methods=['GET'])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-7b: Cookie-only-hart (RAT-32), ENV-getoggelt (App-Panel-Assets, initial Observe)
def app_panel_asset(panel_id, asset):
    # ROU-27 / PREG-9: config.json und tiles.json werden an den panel-Service
    # geproxt + Last-Known-Good-gecacht. Alle anderen Assets kommen weiter
    # aus dem Auslieferungs-Verzeichnis (Statik bleibt Verzeichnis-Serving).
    if asset in _PANEL_PROXY_VIEWS:
        body, content_type = _proxy_panel_view(panel_id, asset)
        return Response(body, status=200, mimetype=content_type)
    # PBE-1/PBE-2 / T459: bearbeiten / bearbeiten.js / bearbeiten.css werden
    # 1:1 an den panel-Service proxyt — kein LKG, 404 wird durchgereicht (AC3).
    if asset in _PANEL_BEARBEITEN_VIEWS:
        body, content_type, status = _proxy_panel_bearbeiten(panel_id, asset)
        return Response(body, status=status, mimetype=content_type)
    # PANEL-14: sw.js wird mit __BUILD_ID__-Substitution + no-cache-Headern
    # ausgeliefert. Ohne den no-cache-Header hält der Browser die alte sw.js,
    # kein neuer Worker registriert sich und der neue Cache-Name greift nicht.
    # Defense-in-Depth-Path-Traversal-Schutz analog _send_app_panel_asset.
    if asset == 'sw.js':
        root = os.path.realpath(app_panel_dir())
        target = os.path.realpath(os.path.join(root, 'sw.js'))
        if not (target == root or target.startswith(root + os.sep)):
            abort(404)
        if not os.path.isfile(target):
            abort(404)
        with open(target, encoding='utf-8') as fh:
            body = fh.read().replace('__BUILD_ID__', _app_panel_build_id())
        resp = Response(body, status=200)
        resp.headers['Content-Type'] = 'application/javascript; charset=utf-8'
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    return _send_app_panel_asset(asset)


# ============================================================
#  Entrypoint (ROU-15 / ROU-16)
# ============================================================

# Runtime-Konfig-Schema (CONFIG-1, #179): host/port/log_level/controller_dir
# sind die Werte, die der Service-Start braucht. Datei + ENV laufen über den
# gemeinsamen `tools.configloader` (Konvention `<COMPONENT>_<KEY>`), CLI-Flags
# überschreiben den Loader-Output danach.
#
# `routing.json` (ROU-18) ist eine ANDERE Sache (Routing-Tabelle, kein
# Runtime-Wert) und bleibt eigene Mechanik mit Hot-Reload (#140).
RUNTIME_SCHEMA = {
    'listen_host':       '127.0.0.1',
    'listen_port':       5000,
    'log_level':         'INFO',
    'controller_dir':    '',  # ROU-23: leer = DEFAULT_CONTROLLER_DIR
    'icon_root':         '',  # ROU-26: leer = DEFAULT_ICON_ROOT
    'panel_service_url': '',  # ROU-27: leer = http://127.0.0.1:5041 (PORT-2)
    'geraete_url':       '',  # ROU-29: leer = http://127.0.0.1:5040 (GER, PORT-2)
}


def parse_args(argv):
    p = argparse.ArgumentParser(description='XBuddy Router V1')
    p.add_argument('--routing', default=None,
                   help='Pfad zur Routing-Tabelle (ROU-18); '
                        'SVC-5/CONFIG-5: CLI > $ROUTER_ROUTING_FILE > Default')
    p.add_argument('--config',  default='config.json',
                   help='Pfad zur Runtime-Konfig (ROU-19); '
                        'CONFIG-1: Datei < ENV < CLI')
    p.add_argument('--host',    help='Bind-Host (Test-Werkzeug, CONFIG-1)')
    p.add_argument('--port',    type=int, help='Bind-Port (Test-Werkzeug, CONFIG-1)')
    p.add_argument('--log-level', dest='log_level', help='DEBUG | INFO | WARNING | ERROR')
    p.add_argument('--controller-dir', dest='controller_dir',
                   help='Pfad zur Controller-PWA-Statik (ROU-23)')
    p.add_argument('--icon-root', dest='icon_root',
                   help='Pfad zur Icon-Bibliothek (ROU-26, ICONS-2)')
    p.add_argument('--panel-service-url', dest='panel_service_url',
                   help='URL-Basis des panel-Service (ROU-27, Default http://127.0.0.1:5041)')
    p.add_argument('--geraete-url', dest='geraete_url',
                   help='URL-Basis der Geräte-Registry (ROU-29, Default http://127.0.0.1:5040)')
    p.add_argument('--cert', help='TLS-Cert (optional, für HTTPS-Modus)')
    p.add_argument('--key',  help='TLS-Key (optional, für HTTPS-Modus)')
    return p.parse_args(argv)


def resolved_config(args):
    """ROU-15 / CONFIG-1: Datei + ENV kommen vom gemeinsamen
    `tools.configloader`, CLI-Flags überschreiben den Loader-Output danach.

    ENV-Konvention: `<COMPONENT>_<KEY>` → `ROUTER_LISTEN_HOST`,
    `ROUTER_LISTEN_PORT`, `ROUTER_LOG_LEVEL`, `ROUTER_CONTROLLER_DIR`,
    `ROUTER_ICON_ROOT`, `ROUTER_GERAETE_URL`.
    """
    # Migrations-Hinweis (#102): die alten CDP-Push-Keys aus dem abgelösten
    # ROU-21 werden ignoriert — eine ältere config.json soll deshalb keinen
    # Crash auslösen, sondern nur einen sichtbaren Log-Hinweis mit Ticket-
    # Bezug hinterlassen. Der Loader warnt parallel über unbekannte Keys;
    # wir warnen zusätzlich, weil unser Hinweis das Folge-Ticket nennt.
    try:
        with open(args.config) as _f:
            _raw = json.load(_f)
        if isinstance(_raw, dict):
            for legacy_key in ('cdp_target', 'cdp_idle_url'):
                if legacy_key in _raw:
                    logging.warning(
                        'config-Schlüssel %r wird ignoriert (ROU-21 abgelöst '
                        'durch SSE ROU-22, Refs #102)', legacy_key)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        # Datei fehlt/kaputt → der Loader hat das bereits passend behandelt.
        pass
    for legacy_env in ('ROUTER_CDP_TARGET', 'ROUTER_CDP_IDLE_URL'):
        if legacy_env in os.environ:
            logging.warning(
                'ENV %s wird ignoriert (ROU-21 abgelöst durch SSE ROU-22, '
                'Refs #102)', legacy_env)

    cfg = configloader.load(
        component='router',
        schema=RUNTIME_SCHEMA,
        config_path=args.config)
    if args.host:               cfg['listen_host']       = args.host
    if args.port:               cfg['listen_port']       = args.port
    if args.log_level:          cfg['log_level']         = args.log_level
    if args.controller_dir:     cfg['controller_dir']    = args.controller_dir
    if args.icon_root:          cfg['icon_root']         = args.icon_root
    if args.panel_service_url:  cfg['panel_service_url'] = args.panel_service_url
    if args.geraete_url:        cfg['geraete_url']       = args.geraete_url
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    # LOG-4 (#166): zentraler Setup statt eigenem basicConfig. Level kommt
    # aus der Runtime-Config (CONFIG-1/CONFIG-2, RUNTIME_SCHEMA).
    logsetup.setup(cfg['log_level'])
    runtime_config['controller_dir']    = cfg.get('controller_dir', '')
    runtime_config['icon_root']         = cfg.get('icon_root', '')
    runtime_config['panel_service_url'] = cfg.get('panel_service_url', '')
    runtime_config['geraete_url']       = cfg.get('geraete_url', '')
    logging.info('Controller-PWA-Statik: %s', controller_dir())
    logging.info('Icon-Bibliothek (ROU-26): %s', icon_root())
    logging.info('Panel-Service (ROU-27): %s', _panel_service_base())
    logging.info('Geräte-Registry (ROU-29): %s', _geraete_base())
    # SVC-5 / CONFIG-5: CLI-Flag > ENV > Default-Repo-Pfad.
    routing_file = router_config.resolve_routing_file(args.routing)
    load_routing(routing_file)
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
