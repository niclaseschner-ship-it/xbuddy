#!/usr/bin/env python3
"""Panel-Registry — HTTP-Schnittstelle + Entrypoint.

Siehe specs/platform/panel-registry.md (Refs #58). Diese Datei ist die echte
Komponente um `panel/registry.py` herum: Flask-App + systemd-Service-
Entrypoint. Konsumenten reden über HTTP (DCOMP-1), nicht über `import panel`.

Endpunkte:
  GET  /api/v1/panels/                       — alle Panels (PREG-13)
  GET  /api/v1/panels/<id>                    — ein Panel je `panel_id` (PREG-14)
  GET  /api/v1/panels/<id>/config.json        — config-Sicht (PREG-14)
  GET  /api/v1/panels/<id>/tiles.json         — tiles-Sicht (PREG-14)
  POST /api/v1/panels/                        — Panel anlegen, atomar (PREG-15)

Service-Topologie (Lego-Prinzip): die Registry läuft als schlanker
eigenständiger Flask-Prozess auf Loopback-Port 5041 (PORT-2), Schwester der
Geräte-Registry (GER/5040). nginx-Origin matcht `/api/v1/panels/` auf diesen
Prozess (URL-14, `xbuddy_panel`).

Der EINZIGE Cross-Component-Teil ist die Display-Validierung beim POST: der
Service prüft `display_id` über HTTP gegen die Geräte-Registry (GER-14,
PREG-7) — kein Python-Import der Geräte-Komponente (DCOMP-1).
"""

import argparse
import logging
import os
import sys
import threading
import urllib.error
import urllib.request

from flask import Flask, jsonify, request

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1) und
# `tools.logsetup` (LOG-4) auch beim Direktstart `python3 panel/main.py`
# gefunden werden — analog geraete/main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from panel import registry as registry_mod  # noqa: E402
from tools import configloader, logsetup  # noqa: E402


# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Die geladene Registry, der Registry-Pfad und die Geräte-Registry-URL.
# Der Entrypoint befüllt das Dict; Tests setzen es über `configure()`.
runtime = {
    "registry":      registry_mod.Registry(),
    "registry_path": None,
    "geraete_url":   "http://127.0.0.1:5040",
}


def configure(reg, registry_path=None, geraete_url=None):
    """Setzt die laufende Registry, den Registry-Pfad + die Geräte-Registry-URL.

    Wird `registry_path` nicht übergeben, bleibt das übergebene Registry-Objekt
    die Quelle (Test-Modus, ohne Disk-Schreiben). Mit `registry_path` liest
    jeder Request frisch von Disk (DCOMP-2), und POST schreibt persistent
    (DCOMP-4 über `panel.save`).
    """
    runtime["registry"] = reg
    runtime["registry_path"] = registry_path
    if geraete_url is not None:
        runtime["geraete_url"] = geraete_url


# Schreib-Serialisierung (PREG-15): Read-Modify-Write der Registry-Datei aus
# parallelen Flask-Threads würde ohne Lock verlorengehende Updates produzieren.
# Das Lock klammert nur den Schreib-Pfad — Lesen bleibt lock-frei (DCOMP-2).
_write_lock = threading.Lock()


# ============================================================
#  Geräte-Validierung (PREG-7, GER-14) — der eine Cross-Component-Teil
# ============================================================

class _GeraeteUnreachable(Exception):
    """Die Geräte-Registry ist nicht erreichbar — PREG-7 → 503."""


def display_existiert(display_id):
    """Prüft per HTTP gegen die Geräte-Registry, ob `display_id` existiert.

    GER-14 / PREG-7: `GET <geraete_url>/api/v1/geraete/<display_id>`.
    200 → existiert (True), 404 → unbekannt (False). Jeder Transport- oder
    sonstige Fehler ist `_GeraeteUnreachable` (PREG-7 → 503): ein Panel auf ein
    nicht validierbares Display anzulegen ist keine sichere Default-Annahme.

    Bewusst über HTTP, KEIN Python-Import der Geräte-Komponente (DCOMP-1). Als
    Funktion auf Modulebene, damit Tests sie stubben können (PREG-12: ohne Netz).
    """
    base = runtime["geraete_url"].rstrip("/")
    url = "%s/api/v1/geraete/%s" % (base, display_id)
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        # Andere HTTP-Fehler (5xx der Geräte-Registry) sind kein „unbekannt",
        # sondern ein nicht-validierbarer Zustand → unreachable (503).
        raise _GeraeteUnreachable(
            "Geräte-Registry antwortet mit %s" % e.code) from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise _GeraeteUnreachable(str(e)) from e


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)


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
def get_panels():
    """PREG-13: alle Panel-Instanzen der Familie als JSON-Array."""
    return jsonify([p.to_dict() for p in _aktuelle_registry().list_all()])


@app.route("/api/v1/panels/<panel_id>", methods=["GET"])
def get_panel(panel_id):
    """PREG-14: ein Panel je `panel_id`. Unbekannte id: 404 mit JSON-Fehler."""
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.to_dict())


@app.route("/api/v1/panels/<panel_id>/config.json", methods=["GET"])
def get_panel_config(panel_id):
    """PREG-14: das `config`-Feld als eigenständiges JSON-Dokument (PANEL-8).

    Genau die Form, die die Panel-Seite per `fetch('./config.json')` erwartet —
    der Router proxyt diese Sicht (PREG-9).
    """
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.config)


@app.route("/api/v1/panels/<panel_id>/tiles.json", methods=["GET"])
def get_panel_tiles(panel_id):
    """PREG-14: das `tiles`-Feld als eigenständiges JSON-Dokument (PANEL-3).

    Genau die Form, die die Panel-Seite per `fetch('./tiles.json')` erwartet —
    der Router proxyt diese Sicht (PREG-9).
    """
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.tiles)


def _bad_request(msg):
    """PREG-15: 4xx mit JSON-Fehler, keine Stack-Traces (analog GER-15)."""
    return jsonify({"error": msg}), 400


@app.route("/api/v1/panels/", methods=["POST"])
def post_panel():
    """PREG-15: Panel-Instanz anlegen.

    JSON-Body `{slug, display_id, router_url?, config?, tiles?}`:

    - `slug` (Pflicht) — Basis der `panel_id` (PREG-6); der Server vergibt die
      `panel_id` kollisionsfrei, der Client liefert sie NICHT.
    - `display_id` (Pflicht) — gegen die Geräte-Registry validiert (PREG-7).
    - `router_url` (optional, Default leer = same-origin, PREG-8).
    - `config` (optional) — PANEL-8-Felder; fehlt es, leeres Objekt.
    - `tiles` (optional) — PANEL-3; fehlt es, leere Kachel-Liste.

    Antwort 200 mit dem Panel-JSON inkl. vergebener `panel_id` und abgeleitetem
    `source_id`. Unbekanntes `display_id` → 400; Geräte-Registry nicht
    erreichbar → 503; Schreibfehler → 503 (panels.json bleibt unverändert).
    Read-Modify-Write läuft hinter `_write_lock` (parallele POSTs erhalten
    verschiedene `panel_id`s, beide Einträge landen, DCOMP-4 atomar).
    """
    path = runtime.get("registry_path")
    if path is None:
        return jsonify({"error": "kein Registry-Pfad konfiguriert"}), 503

    body = request.get_json(silent=True) or {}
    slug = (body.get("slug") or "").strip()
    display_id = (body.get("display_id") or "").strip()
    router_url = (body.get("router_url") or "").strip()
    config = body.get("config")
    tiles = body.get("tiles")

    if not slug:
        return _bad_request("slug fehlt")
    if not display_id:
        return _bad_request("display_id fehlt")
    if config is None:
        config = {}
    if tiles is None:
        tiles = {}
    if not isinstance(config, dict):
        return _bad_request("config muss ein Objekt sein (PANEL-8)")
    if not isinstance(tiles, dict):
        return _bad_request("tiles muss ein Objekt sein (PANEL-3)")

    # PREG-7: display_id gegen die Geräte-Registry validieren (GER-14, HTTP).
    try:
        if not display_existiert(display_id):
            return _bad_request(
                "display_id %r in der Geräte-Registry unbekannt (PREG-7)"
                % display_id)
    except _GeraeteUnreachable as e:
        return jsonify({"error": "Geräte-Registry nicht erreichbar: %s" % e}), 503

    with _write_lock:
        # DCOMP-2: frisch von Disk lesen — sonst überschreiben parallele Writes.
        reg = registry_mod.load(path)
        try:
            panel_id = registry_mod.neue_id(reg, slug)
        except (registry_mod.RegistryError, ValueError) as e:
            return _bad_request(str(e))
        try:
            panel = registry_mod.Panel(
                panel_id=panel_id, display_id=display_id,
                config=config, tiles=tiles, router_url=router_url)
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
    p.add_argument("--geraete-url", dest="geraete_url",
                   help="Origin der Geräte-Registry (PREG-7/11)")
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
    (Registry-Pfad, PREG-11) und `geraete_url` (Geräte-Registry-Origin, PREG-7/
    11) bleiben außerhalb des Loader-Schemas — analog geraete/main.py. ENV-
    Overrides decken den Dev-Override ab (`PANELS_REGISTRY`, `GERAETE_URL`).
    """
    cfg = configloader.load(component="panel", schema=RUNTIME_SCHEMA)
    cfg["panels"] = os.environ.get("PANELS_REGISTRY", args.panels)
    cfg["geraete_url"] = (
        args.geraete_url
        or os.environ.get("GERAETE_URL", "http://127.0.0.1:5040"))
    if args.host:      cfg["listen_host"] = args.host
    if args.port:      cfg["listen_port"] = args.port
    if args.log_level: cfg["log_level"]   = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    logsetup.setup(cfg["log_level"])

    reg = registry_mod.load(cfg["panels"])
    configure(reg, registry_path=cfg["panels"], geraete_url=cfg["geraete_url"])

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logging.info(
        "Panel-Registry hört auf %s://%s:%s (panels=%s, geraete=%s)",
        scheme, cfg["listen_host"], cfg["listen_port"],
        cfg["panels"], cfg["geraete_url"])
    app.run(host=cfg["listen_host"], port=cfg["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
