#!/usr/bin/env python3
"""Photo-Buddy-App — HTTP-Schnittstelle + Entrypoint (PHOTO-1 … PHOTO-23).

Siehe specs/buddies/photo.md. Der Photo-Buddy ist die XBuddy-App mit dem
Buddy-Slug `photo` (PHOTO-1). Er besitzt seine Daten (die Medien-Library,
PHOTO-7), seine Funktion (Ingest + Normalisierung, Durchlauf) und stellt das
Ergebnis über seine Display-View `rahmen` bereit (PHOTO-2, APP-1).

Endpunkte:
  POST   /api/v1/photo/medien                  — Ingest, multipart `medium` (PHOTO-13)
  GET    /api/v1/photo/medien                  — Library-Metadaten, geordnet (PHOTO-14)
  GET    /api/v1/photo/medien/<id>             — Vollmedium JPEG|MP4 (PHOTO-15)
  GET    /api/v1/photo/medien/<id>/thumbnail   — Thumbnail/Poster-JPEG (PHOTO-15)
  DELETE /api/v1/photo/medien/<id>             — Löschen, atomar (PHOTO-16)
  GET    /display/photo/rahmen                 — View `rahmen` (PHOTO-2)

AUTH-11 (#1844): `/display/photo/rahmen` und der implizite
`/display/photo/static/<path:filename>`-Endpunkt tragen den AUTH-7b-Dual-Gate
(`xbuddy_session`-Cookie, hard) — Browser-/Kiosk-Fläche, kein tma-Kontext.

Service-Topologie wie wetter/main.py: eine schlanke eigenständige Flask-App, ein
Geschwister von router/, familie/, plan/, wetter/. Statische Assets unter
/display/photo/static/<asset> (URL-13). Port 5051 (PHOTO-20, PORT-2).
"""

import argparse
import logging
import os
import sys
import threading

from flask import Flask, jsonify, make_response, render_template, request, send_file

# Repo-Wurzel auf den Importpfad — die App konsumiert die Library
# `tools.configloader`/`tools.logsetup` (DCOMP-1-Ausnahme: `tools/` ist
# gemeinsamer Bibliotheks-Code).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import configloader, logsetup  # noqa: E402
from tools import familie_client as _familie_client_mod  # noqa: E402
from tools.familie_client import DEFAULT_ORIGIN as _FAMILIE_DEFAULT_ORIGIN  # noqa: E402
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.initdata.auth_gate import (  # noqa: E402
    make_require_dual_gate,
    make_require_init_data,
)
from tools.service_diagnostics import register_version  # noqa: E402

# Das photo-Paket als Paket importieren, damit die relativen Imports in
# config/store/ingest/render greifen — auch beim Direktstart von main.py.
if __package__:
    from . import config as config_mod
    from . import ingest as ingest_mod
    from . import render as render_mod
    from . import store
else:  # python3 photo/main.py
    sys.path.insert(0, _REPO_ROOT)
    from photo import config as config_mod
    from photo import ingest as ingest_mod
    from photo import render as render_mod
    from photo import store


logger = logging.getLogger(__name__)


# ============================================================
#  Laufzeit-Zustand (DCOMP-2 Reload-on-Read)
# ============================================================
#
# Wie beim Wetter-/Plan-Buddy: `config` ist der Last-Known-Good-Snapshot, nicht
# die Lookup-Wahrheit. Endpoints lesen via `_current_config()` pro Aufruf frisch
# von Disk (eine geänderte Sortierung/TTL wirkt ohne Restart); der Snapshot
# dient als Fallback, wenn ein einzelner Read scheitert (DCOMP-3).
runtime = {
    "config": None,         # photo.config.Config — Last-Known-Good-Snapshot
    "config_path": None,    # Pfad zur photo.json — Naht für DCOMP-2
    "bot_token": None,          # AUTH-3 (T1321): Bot-Token — Test-Naht oder ENV
    "init_data_config": None,   # AUTH-3 (T1321): tma-Header-Validierungs-Config
    "familie_client": None,     # AUTH-3 (T1321): FAM-7-Client (get_telegram_ids)
}

# Schreib-Serialisierung (PHOTO-10/13/16): Read-Modify-Write des library.json-
# Index aus parallelen Flask-Threads würde ohne Lock verloren-gehende Updates
# produzieren (Muster familie/main.py `_write_lock`). Das Lock klammert nur den
# Schreib-Pfad (Ingest/Delete) — Lesen bleibt lock-frei (DCOMP-2).
_write_lock = threading.Lock()


def configure(cfg, config_path=None,
              bot_token=None, init_data_config=None, familie_client=None):
    """Setzt die Konfiguration (Test-Naht, DCOMP-2).

    Ohne `config_path` bleibt das übergebene `cfg` die Quelle (Test-Modus, kein
    Disk-Reload). Mit `config_path` liest der Buddy `photo.json` pro Aufruf
    frisch (Reload-on-Read).

    `bot_token` / `init_data_config` / `familie_client` (AUTH-3, T1321):
    Auth-Naht für Tests (Muster essen); im Produktiv-Betrieb aus ENV.
    """
    runtime["config"] = cfg
    runtime["config_path"] = config_path

    # AUTH-3 Hart-Auth (T1321): Test-Naht analog essen.
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if init_data_config is not None:
        runtime["init_data_config"] = init_data_config
    if familie_client is not None:
        runtime["familie_client"] = familie_client


def _current_config():
    """DCOMP-2 Reload-on-Read: liefert die photo.json-Config pro Aufruf frisch.

    Scheitert Read/Parse, fällt der Aufruf auf den Last-Known-Good-Snapshot
    zurück (DCOMP-3). Ohne konfigurierten `config_path` (Tests) wird der
    Snapshot direkt zurückgegeben.
    """
    path = runtime.get("config_path")
    snapshot = runtime["config"]
    if not path:
        return snapshot
    try:
        return config_mod.resolve(path)
    except (config_mod.ConfigError, OSError) as e:
        logger.debug("reload-on-read fiel auf snapshot zurück (%s)", e)
        return snapshot


# ============================================================
#  AUTH-3 Hart-Auth (T1321 — auth.md AUTH-2/3/5/8/9)
# ============================================================
#
# Wörtliche Übernahme des essen-Decorators (essen/main.py, T948). Der
# Audit-Funnel-Befund #1338 klassifiziert die /api/v1/photo/*-Datenrouten neu
# als AUTH-3 (hart geschützt): extern über den Funnel waren Fotos abruf-/löschbar.

# ENV-Variable für Bot-Token (APP-7 / MAD-9): cluster-weit, wie essen.
_ENV_BOT_TOKEN = "ELTERNCHAT_BOT_TOKEN"
# CONFIG-5: Familie-Service-Origin per Komponenten-ENV.
_ENV_FAMILIE_ORIGIN = "PHOTO_FAMILIE_ORIGIN"


def _get_bot_token():
    """Bot-Token aus runtime-Dict (Test-Naht) oder ENV (APP-7)."""
    return runtime.get("bot_token") or os.environ.get(_ENV_BOT_TOKEN)


def _get_familie_client():
    """Liefert einen FamilieClient — gecacht im runtime-Dict oder frisch (T1015).

    Test-Naht: ``configure(familie_client=...)`` setzt direkt einen Stub.
    Produktiv-Pfad: ``tools.familie_client.FamilieClient`` aus ENV
    ``PHOTO_FAMILIE_ORIGIN`` (Default ``http://127.0.0.1:5010``).
    """
    cached = runtime.get("familie_client")
    if cached is not None:
        return cached
    origin = os.environ.get(_ENV_FAMILIE_ORIGIN, _FAMILIE_DEFAULT_ORIGIN)
    return _familie_client_mod.FamilieClient(origin_url=origin)


def _get_init_data_config():
    """Tma-Config (``max_age_seconds``) — gecacht im runtime-Dict oder frisch.

    Wörtlich der vormals inline im Decorator gelesene Pfad
    (``runtime.get("init_data_config")`` → ``_init_data_mod.load_config()`` + Cache).
    Getter-Naht für die AUTH-Decorator-Lib-Factory (#1626).
    """
    cfg = runtime.get("init_data_config")
    if cfg is None:
        cfg = _init_data_mod.load_config()
        runtime["init_data_config"] = cfg
    return cfg


# AUTH-8: 401 rendert eine Anweisungsseite statt eines rohen Status-Codes.
_AUTH_401_HTML = (
    "<!doctype html>\n"
    "<html lang=\"de\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    "<title>Gerät neu verbinden</title></head>"
    "<body style=\"font-family:system-ui,sans-serif;max-width:32rem;"
    "margin:3rem auto;padding:0 1rem;line-height:1.5\">"
    "<h1>Dieses Gerät muss neu verbunden werden.</h1>"
    "<p>Öffne im Familien-Bot den Befehl "
    "<code>/gerät_neu_pairen &lt;display_id&gt;</code> und folge dem Link "
    "auf diesem Gerät.</p>"
    "</body></html>"
)


def _auth_401():
    """AUTH-8: 401 mit HTML-Anweisungsseite (nicht roher Status-Code)."""
    resp = make_response(_AUTH_401_HTML, 401)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


# Decorator: HART-AUTH (T948/T1321, auth.md AUTH-2/3/5/8). Der hand-kopierte
# Wrapper-Body ist mit #1626 auf die AUTH-Decorator-Lib-Factory geflippt
# (tools/initdata/auth_gate.py::make_require_init_data, #1625). Der Name
# `require_init_data` BLEIBT (AUTH-9-Coverage-Test trägt per AST-Namen); die
# Buddy-eigenen Getter + `_auth_401` gehen WÖRTLICH als Closures rein — die
# Factory ruft genau diesen `_auth_401`, 401/403/500-Shape bleibt byte-gleich.
require_init_data = make_require_init_data(
    get_bot_token=_get_bot_token,
    get_familie_client=_get_familie_client,
    get_init_data_config=_get_init_data_config,
    auth_401=_auth_401,
)


# ============================================================
#  AUTH-11 (#1844): Dual-Gate für die Browser-Fläche /display/photo/*
# ============================================================
# /display/photo/rahmen ist eine Kiosk-/Browser-Fläche (Tablet), kein
# Telegram-Mini-App-Kontext — kein tma-Header, sondern der
# xbuddy_session-Cookie (AUTH-7b). Bot-Token-Getter und 401-Renderer sind mit
# require_init_data geteilt (kein zweites Geheimnis, kein zweiter 401-Text).

def _client_ip():
    """Client-IP fürs AUTH-7-Observe-Log (RAT-32: kein Gate mehr, nur Log)."""
    xri = request.headers.get("X-Real-IP")
    if xri:
        return xri.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


require_dual_gate = make_require_dual_gate(
    get_bot_token=_get_bot_token,
    get_client_ip=_client_ip,
    auth_401=_auth_401,
    default_mode="hard",  # Nic-Setzung 2026-08-11 (AUTH-11), NICHT observe
)


# ============================================================
#  Flask-App
# ============================================================

# URL-13: statische Assets im Display-Namensraum des Buddys, damit sie hinter
# der einen Origin geroutet werden (der Flask-Default `/static` läge außerhalb
# der URL-Prefixe).
app = Flask(__name__, static_url_path="/display/photo/static")

# AUTH-11 (#1844): Flasks impliziter static-Endpunkt trägt keine @app.route-
# Dekoration — einziger Ansatzpunkt ist die View-Funktion nach der
# App-Erzeugung. Liefert das echte photo.css/photo.js aus, muss also hinter
# dem Gate stehen wie die Display-View selbst.
app.view_functions["static"] = require_dual_gate()(app.view_functions["static"])


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


def _bad_request(msg, status=400):
    """4xx/503 mit JSON-Fehler, keine Stack-Traces vor dem Konsumenten (FAM-12/13)."""
    return jsonify({"error": msg}), status


# ── API: Ingest (PHOTO-13) ─────────────────────────────────────────────────

@app.route("/api/v1/photo/medien", methods=["POST"])
@require_init_data
def post_medium():
    """PHOTO-13: Medium aufnehmen. Multipart-Feld `medium` (Muster FAM-13).

    Normalisiert (PHOTO-8), erzeugt Thumbnail/Poster (PHOTO-9) und schreibt
    alles atomar (PHOTO-10). Antwort `{"id", "typ"}`. Video über `video_max_s`
    → 413. Leeres/fehlendes Feld → 400. Schreib-/Verarbeitungsfehler → 503.
    """
    if "medium" not in request.files:
        return _bad_request("multipart-Feld 'medium' fehlt")
    upload = request.files["medium"]
    dateiname = (upload.filename or "").strip()
    if not dateiname:
        return _bad_request("Medien-Dateiname fehlt")
    rohbytes = upload.read()
    if not rohbytes:
        return _bad_request("Medien-Inhalt ist leer")

    cfg = _current_config()
    with _write_lock:
        try:
            medium = ingest_mod.ingest(
                cfg.library_verzeichnis, cfg, rohbytes, dateiname)
        except ingest_mod.VideoZuLang as e:
            return _bad_request(str(e), status=413)
        except ingest_mod.normalize_mod.NormalizeError as e:
            return _bad_request("Medium nicht verarbeitbar: %s" % e)
        except store.StoreError as e:
            logger.warning("post_medium: Schreiben fehlgeschlagen: %s", e)
            return _bad_request(str(e), status=503)
    return jsonify({"id": medium.id, "typ": medium.typ}), 200


# ── API: Liste (PHOTO-14) ───────────────────────────────────────────────────

@app.route("/api/v1/photo/medien", methods=["GET"])
@require_init_data
def get_medien():
    """PHOTO-14: Library-Metadaten, geordnet nach PHOTO-11 — Datenquelle der View."""
    cfg = _current_config()
    medien = store.load(cfg.library_verzeichnis)
    geordnet = store.sortiere(medien, cfg.sortier_richtung, cfg.stempel_quelle)
    meta = [{"id": m.id, "typ": m.typ, "hinzugefuegt": m.hinzugefuegt,
             "aufgenommen": m.aufgenommen, "dauer": m.dauer}
            for m in geordnet]
    return jsonify(meta)


# ── API: Einzelmedium & Thumbnail (PHOTO-15) ────────────────────────────────

@app.route("/api/v1/photo/medien/<medium_id>", methods=["GET"])
@require_init_data
def get_medium(medium_id):
    """PHOTO-15: Vollmedium (JPEG|MP4) mit korrektem Content-Type (send_file)."""
    cfg = _current_config()
    pfad = store.serve_pfad(cfg.library_verzeichnis, medium_id)
    if pfad is None:
        return _bad_request("unbekannte id", status=404)
    return send_file(pfad)


@app.route("/api/v1/photo/medien/<medium_id>/thumbnail", methods=["GET"])
@require_init_data
def get_thumbnail(medium_id):
    """PHOTO-15: Thumbnail/Poster-Frame (JPEG) mit korrektem Content-Type (FAM-8)."""
    cfg = _current_config()
    pfad = store.thumb_pfad(cfg.library_verzeichnis, medium_id)
    if pfad is None:
        return _bad_request("unbekannte id", status=404)
    return send_file(pfad)


# ── API: Löschen (PHOTO-16) ─────────────────────────────────────────────────

@app.route("/api/v1/photo/medien/<medium_id>", methods=["DELETE"])
@require_init_data
def delete_medium(medium_id):
    """PHOTO-16: Vollmedium + Thumbnail + Index-Eintrag atomar entfernen (PHOTO-10)."""
    cfg = _current_config()
    with _write_lock:
        try:
            entfernt = store.delete(cfg.library_verzeichnis, medium_id)
        except store.StoreError as e:
            logger.warning("delete_medium: Löschen fehlgeschlagen: %s", e)
            return _bad_request(str(e), status=503)
    if not entfernt:
        return _bad_request("unbekannte id", status=404)
    return jsonify({"id": medium_id}), 200


# ── Display-View (PHOTO-2) ──────────────────────────────────────────────────

@app.route("/display/photo/rahmen", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-11 (#1844): Kiosk-/Browser-Fläche, Cookie-Gate
def rahmen():
    """View `rahmen` — gerahmter Bilderrahmen mit Auto-Durchlauf (PHOTO-2..6).

    GET-only: Slideshow, Pfeile, Pause/Play und das Übersichts-Grid sind
    clientseitige In-View-Zustände (E-PHOTO-10, photo.js). Die View liefert die
    geordnete Medien-Liste + das Intervall; eine leere Library zeigt den
    neutralen Zustand (PHOTO-6).
    """
    cfg = _current_config()
    medien = store.load(cfg.library_verzeichnis)
    view = render_mod.baue_view(cfg, medien)
    return render_template("rahmen.html", view=view)


# ============================================================
#  Entrypoint (PHOTO-20)
# ============================================================

# Runtime-Konfig-Schema (CONFIG-1): nur die Service-Start-Werte — Bind,
# Log-Level. Verhaltens-Daten (Intervall/Sortierung/TTL/Library) leben in
# photo.json (PHOTO-19). Listen-Port 5051 (PHOTO-20, PORT-2 `xbuddy-photo`).
RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5051,
    "log_level":   "INFO",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Photo-Buddy-App V1")
    p.add_argument("--config", dest="config_file", default=None,
                   help="Pfad zur photo.json (PHOTO-19; sonst $PHOTO_CONFIG_FILE / Default)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key", help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_runtime_config(args):
    """Host/Port/Log-Level: Datei < ENV < CLI (CONFIG-1/CONFIG-5)."""
    cfg = configloader.load(component="photo", schema=RUNTIME_SCHEMA)
    if args.host:
        cfg["listen_host"] = args.host
    if args.port:
        cfg["listen_port"] = args.port
    if args.log_level:
        cfg["log_level"] = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rt = resolved_runtime_config(args)
    logsetup.setup(rt["log_level"])

    config_path = (args.config_file
                   or os.environ.get(config_mod.ENV_CONFIG_FILE)
                   or config_mod.DEFAULT_CONFIG_FILE)
    cfg = config_mod.resolve(config_path)
    configure(cfg, config_path=config_path)

    # PHOTO-12: Startup-Sweep, damit eine gesetzte TTL auch ohne neuen Ingest
    # greift (lang laufende oder selten gefütterte Instanz). Default 0 => No-Op.
    store.auto_delete(cfg.library_verzeichnis, cfg.auto_delete_tage)

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logger.info("Photo-Buddy hört auf %s://%s:%s (library=%s, intervall=%ds)",
                scheme, rt["listen_host"], rt["listen_port"],
                cfg.library_verzeichnis, cfg.intervall_s)
    app.run(host=rt["listen_host"], port=rt["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
