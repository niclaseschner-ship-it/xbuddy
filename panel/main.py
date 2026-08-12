#!/usr/bin/env python3
"""Panel-Registry — HTTP-Schnittstelle + Entrypoint.

Siehe specs/platform/panel-registry.md (Refs #58, #329). Diese Datei ist die
echte Komponente um `panel/registry.py` herum: Flask-App + systemd-Service-
Entrypoint. Konsumenten reden über HTTP (DCOMP-1), nicht über `import panel`.

Endpunkte:
  GET  /api/v1/panels/                       — alle Panels (PREG-13)
  GET  /api/v1/panels/<id>                    — ein Panel je `panel_id` (PREG-14)
  GET  /api/v1/panels/<id>/config.json        — config-Sicht (PREG-14)
  GET  /api/v1/panels/<id>/tiles.json         — tiles-Sicht (PREG-14)
  PUT  /api/v1/panels/<id>/tiles              — tiles schreiben, atomar (PBE-4, #330)
  POST /api/v1/panels/                        — Panel anlegen, atomar (PREG-15)
  GET  /healthz                              — Health-Check (SVC-1)

Service-Topologie (Lego-Prinzip): die Registry läuft als schlanker
eigenständiger Flask-Prozess auf Loopback-Port 5041 (PORT-2). nginx-Origin
matcht `/api/v1/panels/` auf diesen Prozess (URL-14, `xbuddy_panel`).
"""

import argparse
import logging
import os
import sys
import threading

from flask import Flask, Response, jsonify, request

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1) und
# `tools.logsetup` (LOG-4) auch beim Direktstart `python3 panel/main.py`
# gefunden werden.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from panel import registry as registry_mod  # noqa: E402
from tools import configloader, logsetup  # noqa: E402
from tools.initdata import auth_gate as _auth_gate  # noqa: E402
from tools.service_diagnostics import register_version  # noqa: E402

# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Die geladene Registry und der Registry-Pfad. Der Entrypoint befüllt das Dict;
# Tests setzen es über `configure()`.
runtime = {
    "registry":      registry_mod.Registry(),
    "registry_path": None,
    "bot_token":     None,   # AUTH-7b (#1400): Cookie-Signatur-Key, ENV-Fallback
}


def configure(reg, registry_path=None, bot_token=None):
    """Setzt die laufende Registry und den Registry-Pfad.

    Wird `registry_path` nicht übergeben, bleibt das übergebene Registry-Objekt
    die Quelle (Test-Modus, ohne Disk-Schreiben). Mit `registry_path` liest
    jeder Request frisch von Disk (DCOMP-2), und POST schreibt persistent
    (DCOMP-4 über `panel.save`).
    """
    runtime["registry"] = reg
    runtime["registry_path"] = registry_path
    if bot_token is not None:
        runtime["bot_token"] = bot_token


# ============================================================
#  AUTH-7b Dual-Gate (PBE-4, #1400 / #1389, auth.md AUTH-7 / RAT-32)
# ============================================================
# Der Panel-Tiles-SCHREIB-Endpoint (PUT .../tiles) ist WRITE → wenn funnel-
# erreichbar HART ab Tag 0 (AUTH-3.a, keine Observe-Grace). Cookie gültig →
# 200 + Rolling-Refresh; keine Cookie-Quelle → 401-Re-Pair. Faithful zum
# seiten-Vorbild über die #1625-Factory (make_require_dual_gate).

def _get_bot_token():
    """Bot-Token (HMAC-Cookie-Key) aus runtime-Dict (Test-Naht) oder ENV
    ELTERNCHAT_BOT_TOKEN (systemd EnvironmentFile-Sharing, #684) → TELEGRAM_BOT_TOKEN."""
    return (
        runtime.get("bot_token")
        or os.environ.get("ELTERNCHAT_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
    )


def _client_ip():
    """Client-IP für das AUTH-7-Observe-Log (RAT-32: kein Gate mehr, nur Log).
    `X-Real-IP` vom Origin-nginx ist die vertrauenswürdige Quelle; Fallbacks
    X-Forwarded-For (erstes Token), dann remote_addr."""
    xri = request.headers.get("X-Real-IP")
    if xri:
        return xri.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


_DUAL_GATE_401_HTML = (
    "<!doctype html><html lang=de><meta charset=utf-8>"
    "<title>Zugang koppeln</title>"
    "<body style='font-family:sans-serif;padding:2rem;max-width:32rem'>"
    "<h1>Zugang nötig</h1>"
    "<p>Dieser Bereich braucht ein gekoppeltes Gerät. Bitte öffne den "
    "Pairing-Link aus dem Eltern-Chat auf diesem Gerät und versuche es erneut.</p>"
    "</body></html>"
)


def _dual_auth_401():
    """AUTH-8-Re-Pair-401 (D1, panel-Variante) — einziger Ort des 401-Texts."""
    resp = Response(_DUAL_GATE_401_HTML, status=401)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


require_dual_gate = _auth_gate.make_require_dual_gate(
    get_bot_token=_get_bot_token,
    get_client_ip=_client_ip,
    auth_401=_dual_auth_401,
    default_mode="hard",  # AUTH-11 (#1834, Nic-Setzung 2026-08-11): "hart", nicht "observe".
)


# Schreib-Serialisierung (PREG-15): Read-Modify-Write der Registry-Datei aus
# parallelen Flask-Threads würde ohne Lock verlorengehende Updates produzieren.
# Das Lock klammert nur den Schreib-Pfad — Lesen bleibt lock-frei (DCOMP-2).
_write_lock = threading.Lock()


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)


# AUTH-11 (#1834): Flask legt den impliziten `static`-Endpunkt
# (`/static/<path:filename>`) für JEDE `Flask(__name__)`-Instanz an, auch ohne
# `static/`-Verzeichnis (panel/ hat keins — der Endpunkt liefert nur 404,
# siehe Handoff-Beobachtung). Er steht trotzdem in `app.url_map` und damit unter
# AUTH-11 — kein `@app.route`, also kein Decorator-Ansatzpunkt; wir tauschen die
# View-Funktion nach der App-Erzeugung aus (kein `functools.wraps` nötig, der
# Gate trägt es schon).
app.view_functions["static"] = require_dual_gate()(app.view_functions["static"])


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


def _aktuelle_registry():
    """Liefert die aktuelle Panel-Registry für genau diesen Request (DCOMP-2).

    Ist ein `registry_path` gesetzt, wird pro Request frisch von Disk geladen —
    sonst sähe der Service Cross-Service-Schreibvorgänge erst nach Restart. Im
    Test-Modus (`configure()` ohne `registry_path`) bleibt das in-memory-Objekt
    die Quelle.
    """
    path = runtime.get("registry_path")
    if path is None:
        return runtime["registry"]
    return registry_mod.load(path)


@app.route("/api/v1/panels/", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1834): Lesepfad-Ausnahme in PBE-3 ist ÜBERHOLT.
def get_panels():
    """PREG-13: alle Panel-Instanzen der Familie als JSON-Array."""
    return jsonify([p.to_dict() for p in _aktuelle_registry().list_all()])


@app.route("/api/v1/panels/<panel_id>", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1834): Lesepfad-Ausnahme in PBE-3 ist ÜBERHOLT.
def get_panel(panel_id):
    """PREG-14: ein Panel je `panel_id`. Unbekannte id: 404 mit JSON-Fehler."""
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.to_dict())


@app.route("/api/v1/panels/<panel_id>/config.json", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1834): Lesepfad-Ausnahme in PBE-3 ist ÜBERHOLT.
def get_panel_config(panel_id):
    """PREG-14: das `config`-Feld als eigenständiges JSON-Dokument (PANEL-8).

    Genau die Form, die die Panel-Seite per `fetch('./config.json')` erwartet.
    """
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.config)


@app.route("/api/v1/panels/<panel_id>/tiles.json", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1834): Lesepfad-Ausnahme in PBE-3 ist ÜBERHOLT.
def get_panel_tiles(panel_id):
    """PREG-14: das `tiles`-Feld als eigenständiges JSON-Dokument (PANEL-3).

    Genau die Form, die die Panel-Seite per `fetch('./tiles.json')` erwartet.
    """
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.tiles)


def _unprocessable(msg):
    """PBE-11: 422 mit JSON-Fehler für ungültige tiles-Liste."""
    return jsonify({"error": msg}), 422


@app.route("/api/v1/panels/<panel_id>/tiles", methods=["PUT"])
@require_dual_gate(mode="hard")  # AUTH-7b / AUTH-3.a (#1400, #1389): WRITE hart ab Tag 0
def put_panel_tiles(panel_id):
    """PBE-4: vollständige neue tiles-Liste schreiben.

    Body: ein tiles-Objekt {"tiles": [...]} — die vollständige neue Liste
    (nicht ein Patch). Last-Write-Wins (Nic 2026-06-07).

    - PBE-11 Validierung VOR dem Schreiben → 422 + JSON-Fehler, Datei unverändert.
    - Unbekannte panel_id → 404.
    - Schreibfehler am Dateisystem → 500 + JSON-Fehler (GER-6/DCOMP-4-Geist).
    - PREG-5: config-Feld der Instanz wird NICHT berührt.
    - DCOMP-4: atomares Schreiben (Temp + os.replace) über registry_mod.save().
    """
    path = runtime.get("registry_path")
    if path is None:
        return jsonify({"error": "kein Registry-Pfad konfiguriert"}), 503

    body = request.get_json(silent=True)
    if body is None:
        return _unprocessable("kein gültiges JSON im Request-Body (PBE-11)")

    # PBE-11: Validierung vor dem Schreiben — via registry_mod (konsolidiert).
    try:
        registry_mod.validate_tiles_payload(body)
    except registry_mod.RegistryError as e:
        return _unprocessable(str(e))

    with _write_lock:
        # DCOMP-2: frisch von Disk lesen — nie einen veralteten Stand überschreiben.
        reg = registry_mod.load(path)
        panel = reg.get(panel_id)
        if panel is None:
            return jsonify({"error": "unbekannte panel_id (PBE-4)"}), 404

        # PREG-5: nur tiles ersetzen, config unberührt.
        geaendertes_panel = registry_mod.Panel(
            panel_id=panel.panel_id,
            config=panel.config,
            tiles=body,
            source_id=panel.source_id,
        )
        # Registry mit geändertem Panel aufbauen — alle anderen Panels erhalten.
        neue_panels = []
        for p in reg.list_all():
            if p.panel_id == panel_id:
                neue_panels.append(geaendertes_panel)
            else:
                neue_panels.append(p)
        neue_reg = registry_mod.Registry(neue_panels)

        try:
            registry_mod.save(neue_reg, path)
        except registry_mod.RegistryError as e:
            logging.warning("put_panel_tiles: Schreiben fehlgeschlagen: %s", e)
            return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True, "panel_id": panel_id}), 200


def _bad_request(msg):
    """PREG-15: 4xx mit JSON-Fehler, keine Stack-Traces (analog GER-15)."""
    return jsonify({"error": msg}), 400


# ============================================================
#  PBE-1/PBE-2 — Editor-Seite je Panel-Instanz (Frontend-Auslieferung)
# ============================================================
#
# Der panel-Service liefert je Panel-Instanz die Editor-Seite (PBE-1) unter
# der deterministisch aus der `panel_id` abgeleiteten URL
# `/controller/app-panel/<panel_id>/bearbeiten` (PBE-2) aus. Der Daten-Eigentümer
# (panel-Service) liefert seine eigene Editor-Seite, die zeigt UND editiert —
# Muster RAT-2 / #328 (Garderoben-Editor). Auth = AUTH-11-Dual-Gate (#1834):
# die PBE-3-Heimnetz/Tailscale-Prämisse ist per Nic-Setzung 2026-08-11 als
# ÜBERHOLT markiert (specs/platform/panel-bearbeiten.md, direkt unter PBE-3) —
# der Live-Stand zeigt, dass das Kiosk-Gerät bereits einen gültigen Cookie
# trägt (RAT-32-Pairing), also gaten auch die Editor-Routen jetzt hart.
#
# Die Statik liegt in `controller/app-panel/bearbeiten.{html,js,css}` neben der
# bestehenden Display-Seite. Wir lesen die HTML-Datei einmalig pro Request und
# substituieren die Panel-Identität in den <body>-Tag (analog zu router/main.py
# render_app_panel_index, PANEL-2-Muster), damit die JS-Schicht ohne weiteren
# Roundtrip ihre Panel-ID kennt.

# controller/app-panel/ liegt parallel zum panel-Service-Verzeichnis im Repo.
_BEARBEITEN_STATIC_DIR = os.path.normpath(os.path.join(
    _HERE, "..", "controller", "app-panel"))


def _editor_static_dir():
    """Erlaubt Tests, das Auslieferungs-Verzeichnis zu überschreiben."""
    return runtime.get("editor_static_dir") or _BEARBEITEN_STATIC_DIR


def _read_editor_html(filename):
    """Liest die Editor-HTML-Datei aus dem Auslieferungs-Verzeichnis (PBE-1)."""
    path = os.path.join(_editor_static_dir(), filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


# PBE-1 Token-Substitution: das echte <body>-Tag in bearbeiten.html trägt
# `data-panel-id="__PANEL_ID__"`. Wir ersetzen genau dieses Token — kein
# Substring-Match auf `<body>` (das stünde sonst auch im HTML-Kommentar und
# würde dort fälschlich substituiert, sodass das echte Tag leer bliebe).
# IDENT-5 — Server-side-Identitäts-Token in HTML-Templates.
_PANEL_ID_TOKEN = "__PANEL_ID__"


def _send_editor_static(panel_id, filename, mimetype):
    """Liefert eine statische Editor-Datei aus (PBE-1, Konsolidierung).

    Gemeinsame Helferfunktion für HTML/JS/CSS-Routen — kein dreifach kopierter
    Read+404+OSError-Block. Die 404-Probe auf `panel_id` läuft hier zentral:
    eine unbekannte Identität darf weder HTML noch JS/CSS für diese Instanz
    bekommen (PBE-1: Seite ist an die `panel_id` gebunden).
    """
    if _aktuelle_registry().get(panel_id) is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    try:
        body = _read_editor_html(filename)
    except OSError as e:
        logging.warning("Editor-Statik %r konnte nicht gelesen werden: %s",
                        filename, e)
        return jsonify({"error": "%s nicht verfügbar" % filename}), 500
    return Response(body, status=200, mimetype=mimetype)


@app.route("/controller/app-panel/<panel_id>/bearbeiten", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1834): PBE-3-Ausnahme ist ÜBERHOLT.
def get_panel_editor(panel_id):
    """PBE-1/PBE-2: Editor-Seite je Panel-Instanz.

    Liefert `bearbeiten.html` mit der Panel-Identität als `data-panel-id` am
    <body> (analog PANEL-2-Muster im Router). 404 bei unbekannter `panel_id`
    (PBE-1: die Seite ist an die `panel_id` gebunden — sie editiert nie eine
    andere Instanz; eine unbekannte Identität darf keine Editor-Seite bekommen).

    AUTH-11 (#1834, Nic-Setzung 2026-08-11): die PBE-3-Prämisse „keine
    zusätzliche Auth-Schicht, Heimnetz/Tailscale-Gate trägt den Zugriff" ist
    in `specs/platform/panel-bearbeiten.md` als ÜBERHOLT markiert — die Route
    trägt jetzt den AUTH-7b-Dual-Gate wie die anderen panel-Routen.

    PBE-1: Panel-Identität wird per Token-Substitution `__PANEL_ID__` im echten
    `<body>`-Tag durch die `panel_id` ersetzt — die Editor-JS-Schicht liest sie
    per `document.body.dataset.panelId` und braucht keinen Roundtrip. Token
    statt Substring-Match auf `<body>`, damit HTML-Kommentare nicht
    versehentlich gematcht werden.
    """
    if _aktuelle_registry().get(panel_id) is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    try:
        html = _read_editor_html("bearbeiten.html")
    except OSError as e:
        logging.warning("Editor-HTML konnte nicht gelesen werden: %s", e)
        return jsonify({"error": "Editor-Seite nicht verfügbar"}), 500
    html = html.replace(_PANEL_ID_TOKEN, panel_id)
    return Response(html, status=200,
                    mimetype="text/html; charset=utf-8")


@app.route("/controller/app-panel/<panel_id>/bearbeiten.js", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1834): PBE-3-Ausnahme ist ÜBERHOLT.
def get_panel_editor_js(panel_id):
    """PBE-1: Editor-JS-Bundle (statisch). 404 bei unbekannter panel_id."""
    return _send_editor_static(panel_id, "bearbeiten.js", "application/javascript")


@app.route("/controller/app-panel/<panel_id>/bearbeiten.css", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1834): PBE-3-Ausnahme ist ÜBERHOLT.
def get_panel_editor_css(panel_id):
    """PBE-1: Editor-CSS (statisch). 404 bei unbekannter panel_id."""
    return _send_editor_static(panel_id, "bearbeiten.css", "text/css; charset=utf-8")


@app.route("/api/v1/panels/", methods=["POST"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1834): WRITE, Nic-Setzung 2026-08-11.
def post_panel():
    """PREG-15: Panel-Instanz anlegen.

    JSON-Body `{slug, config?, tiles?}`:

    - `slug` (Pflicht) — Basis der `panel_id` (PREG-6); der Server vergibt die
      `panel_id` kollisionsfrei, der Client liefert sie NICHT.
    - `config` (optional) — Tuning-Felder (z. B. `backoffs`); das
      Identitätsfeld `source_id` wird vom Server gesetzt und überschreibt einen
      gleichnamigen Aufrufer-Wert (PREG-15 server-autoritativer `config`-Aufbau,
      Nic-Entscheid 2026-06-03).
    - `tiles` (optional) — PANEL-3; fehlt es, leere Kachel-Liste.

    Antwort 200 mit dem Panel-JSON inkl. vergebener `panel_id` und abgeleitetem
    `source_id`. Ungültige Eingabe → 400; Schreibfehler → 503 (panels.json
    bleibt unverändert). Read-Modify-Write läuft hinter `_write_lock` (parallele
    POSTs erhalten verschiedene `panel_id`s, beide Einträge landen, DCOMP-4 atomar).
    """
    path = runtime.get("registry_path")
    if path is None:
        return jsonify({"error": "kein Registry-Pfad konfiguriert"}), 503

    body = request.get_json(silent=True) or {}
    slug = (body.get("slug") or "").strip()
    caller_config = body.get("config")
    tiles = body.get("tiles")

    if not slug:
        return _bad_request("slug fehlt")
    if caller_config is None:
        caller_config = {}
    if tiles is None:
        tiles = {}
    if not isinstance(caller_config, dict):
        return _bad_request("config muss ein Objekt sein (PANEL-8)")
    if not isinstance(tiles, dict):
        return _bad_request("tiles muss ein Objekt sein (PANEL-3)")

    with _write_lock:
        # DCOMP-2: frisch von Disk lesen — sonst überschreiben parallele Writes.
        reg = registry_mod.load(path)
        try:
            panel_id = registry_mod.neue_id(reg, slug)
        except (registry_mod.RegistryError, ValueError) as e:
            return _bad_request(str(e))

        # PREG-15 server-autoritativer config-Aufbau (Nic-Entscheid 2026-06-03):
        # Merge-Regel: Aufrufer-Tuning zuerst, dann server-Identität überschreibt.
        # So bleibt Tuning (backoffs, …) erhalten, source_id ist immer
        # server-gesetzt — auch wenn der Aufrufer es weggelassen oder falsch
        # gesetzt hätte (PANEL-8).
        config = dict(caller_config)
        config["source_id"] = registry_mod.source_id_for(panel_id)

        try:
            panel = registry_mod.Panel(
                panel_id=panel_id, config=config, tiles=tiles)
            reg.add(panel)
        except registry_mod.RegistryError as e:
            return _bad_request(str(e))
        try:
            registry_mod.save(reg, path)
        except registry_mod.RegistryError as e:
            logging.warning("post_panel: Schreiben fehlgeschlagen: %s", e)
            return jsonify({"error": str(e)}), 503

    return jsonify(panel.to_dict()), 200


# ============================================================
#  Entrypoint (PREG-11)
# ============================================================

# Runtime-Konfig-Schema (CONFIG-1): nur die Werte, die der Service-Start
# braucht — Bind, Log-Level. Datei + ENV laufen über `tools.configloader`,
# CLI-Flags überschreiben den Loader-Output danach. Familienspezifische Werte
# (Panels selbst) liegen in `panels.json` (PREG-4).


# ── Health-Check (SVC-1) ─────────────────────────────────────────────────

@app.route("/healthz", methods=["GET"])
def healthz():
    """SVC-1: Health-Endpoint — liefert immer 200 + OK."""
    return jsonify({"ok": True}), 200


RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5041,
    "log_level":   "INFO",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Panel-Registry V1")
    # PREG-11: Pfad zur Registry-Datei kann nicht in der Datei selbst stehen.
    p.add_argument("--panels", default="panels.json",
                   help="Pfad zur Registry-Datei (PREG-4/11)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level",
                   help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key",  help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_config(args):
    """Auflösung der RUNTIME-Konfiguration: Datei < ENV < CLI (CONFIG-1).

    Host/Port/Log-Level kommen vom gemeinsamen `tools.configloader`. `panels`
    (Registry-Pfad, PREG-11) bleibt außerhalb des Loader-Schemas. ENV-Override
    deckt den Dev-Override ab (`PANELS_REGISTRY`).
    """
    cfg = configloader.load(component="panel", schema=RUNTIME_SCHEMA)
    cfg["panels"] = os.environ.get("PANELS_REGISTRY", args.panels)
    if args.host:      cfg["listen_host"] = args.host
    if args.port:      cfg["listen_port"] = args.port
    if args.log_level: cfg["log_level"]   = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    logsetup.setup(cfg["log_level"])

    reg = registry_mod.load(cfg["panels"])
    configure(reg, registry_path=cfg["panels"])

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logging.info(
        "Panel-Registry hört auf %s://%s:%s (panels=%s)",
        scheme, cfg["listen_host"], cfg["listen_port"], cfg["panels"])
    app.run(host=cfg["listen_host"], port=cfg["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
