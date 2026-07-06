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

Service-Topologie wie wetter/main.py: eine schlanke eigenständige Flask-App, ein
Geschwister von router/, familie/, plan/, wetter/. Statische Assets unter
/display/photo/static/<asset> (URL-13). Port 5051 (PHOTO-20, PORT-2).
"""

import argparse
import logging
import os
import sys
import threading

from flask import Flask, jsonify, render_template, request, send_file

# Repo-Wurzel auf den Importpfad — die App konsumiert die Library
# `tools.configloader`/`tools.logsetup` (DCOMP-1-Ausnahme: `tools/` ist
# gemeinsamer Bibliotheks-Code).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import configloader, logsetup  # noqa: E402
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
}

# Schreib-Serialisierung (PHOTO-10/13/16): Read-Modify-Write des library.json-
# Index aus parallelen Flask-Threads würde ohne Lock verloren-gehende Updates
# produzieren (Muster familie/main.py `_write_lock`). Das Lock klammert nur den
# Schreib-Pfad (Ingest/Delete) — Lesen bleibt lock-frei (DCOMP-2).
_write_lock = threading.Lock()


def configure(cfg, config_path=None):
    """Setzt die Konfiguration (Test-Naht, DCOMP-2).

    Ohne `config_path` bleibt das übergebene `cfg` die Quelle (Test-Modus, kein
    Disk-Reload). Mit `config_path` liest der Buddy `photo.json` pro Aufruf
    frisch (Reload-on-Read).
    """
    runtime["config"] = cfg
    runtime["config_path"] = config_path


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
#  Flask-App
# ============================================================

# URL-13: statische Assets im Display-Namensraum des Buddys, damit sie hinter
# der einen Origin geroutet werden (der Flask-Default `/static` läge außerhalb
# der URL-Prefixe).
app = Flask(__name__, static_url_path="/display/photo/static")


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


def _bad_request(msg, status=400):
    """4xx/503 mit JSON-Fehler, keine Stack-Traces vor dem Konsumenten (FAM-12/13)."""
    return jsonify({"error": msg}), status


# ── API: Ingest (PHOTO-13) ─────────────────────────────────────────────────

@app.route("/api/v1/photo/medien", methods=["POST"])
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
def get_medium(medium_id):
    """PHOTO-15: Vollmedium (JPEG|MP4) mit korrektem Content-Type (send_file)."""
    cfg = _current_config()
    pfad = store.serve_pfad(cfg.library_verzeichnis, medium_id)
    if pfad is None:
        return _bad_request("unbekannte id", status=404)
    return send_file(pfad)


@app.route("/api/v1/photo/medien/<medium_id>/thumbnail", methods=["GET"])
def get_thumbnail(medium_id):
    """PHOTO-15: Thumbnail/Poster-Frame (JPEG) mit korrektem Content-Type (FAM-8)."""
    cfg = _current_config()
    pfad = store.thumb_pfad(cfg.library_verzeichnis, medium_id)
    if pfad is None:
        return _bad_request("unbekannte id", status=404)
    return send_file(pfad)


# ── API: Löschen (PHOTO-16) ─────────────────────────────────────────────────

@app.route("/api/v1/photo/medien/<medium_id>", methods=["DELETE"])
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
