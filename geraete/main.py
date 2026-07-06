#!/usr/bin/env python3
"""Geräte-Registry — HTTP-Schnittstelle + Entrypoint.

Siehe specs/platform/geraete.md (Refs #105, #212). Diese Datei ist die echte
Komponente um `geraete/registry.py` herum: Flask-App + systemd-Service-
Entrypoint. Konsumenten reden über HTTP (DCOMP-1), nicht über
`import geraete` — die `__init__`-Re-Exports bleiben heute als
Übergangs-Schicht, bis die letzten Importeure auf HTTP umgezogen sind.

Endpunkte:
  GET  /api/v1/geraete/        — alle Geräte (GER-13)
  GET  /api/v1/geraete/<id>    — ein Gerät je `display_id` (GER-14)
  POST /api/v1/geraete/        — Gerät anlegen, atomar (GER-15)

Service-Topologie (Lego-Prinzip): die Registry läuft als schlanker
eigenständiger Flask-Prozess auf Loopback-Port 5040 (PORT-2), genau wie der
Familien-Mit-Host (FAM/5010, Vorlage). nginx-Origin matcht
`/api/v1/geraete/` auf diesen Prozess (URL-14, `xbuddy_geraete`).
"""

import argparse
import logging
import os
import sys
import threading

from flask import Flask, jsonify, request

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1) und
# `tools.logsetup` (LOG-4) auch beim Direktstart `python3 geraete/main.py`
# gefunden werden — analog familie/main.py, plan/main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Paket-Import wie Plan-Buddy / Familie: `from geraete import …`, damit
# `python -m geraete.main` aus dem Repo-Root funktioniert.
from geraete import registry as registry_mod  # noqa: E402
from tools import configloader, logsetup  # noqa: E402
from tools.service_diagnostics import register_version  # noqa: E402

# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Die geladene Registry + der Registry-Pfad. Der Entrypoint befüllt das
# Dict; Tests setzen es direkt über `configure()`. Ohne `registry_path`
# bleibt das in-memory-Objekt die Quelle — analog familie/main.py.
runtime = {
    "registry":      registry_mod.Registry(),
    "registry_path": None,
}


def configure(reg, registry_path=None):
    """Setzt die laufende Registry + den Registry-Pfad.

    Wird `registry_path` nicht übergeben, bleibt das übergebene Registry-
    Objekt die Quelle (Test-Modus, ohne Disk-Schreiben). Mit `registry_path`
    liest jeder Request frisch von Disk (DCOMP-2), und POST schreibt
    persistent (DCOMP-4 über `geraete.save`).
    """
    runtime["registry"] = reg
    runtime["registry_path"] = registry_path


# Schreib-Serialisierung (GER-15): Read-Modify-Write der Registry-Datei aus
# parallelen Flask-Threads würde ohne Lock verlorengehende Updates
# produzieren (zwei POSTs lesen denselben Stand, beide schreiben, der zweite
# überschreibt den ersten). Das Lock klammert nur den Schreib-Pfad — Lesen
# bleibt lock-frei (DCOMP-2 Reload-on-Read).
_write_lock = threading.Lock()


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


def _aktuelle_registry():
    """Liefert die aktuelle Geräte-Registry für genau diesen Request.

    DCOMP-2: ist ein `registry_path` gesetzt, wird pro Request frisch von
    Disk geladen — sonst sieht der Service Cross-Service-Schreibvorgänge
    (z. B. von der Eltern-Chat-Skill-Anlage, GAA) erst nach Restart. Im
    Test-Modus (`configure()` ohne `registry_path`) bleibt das in-memory-
    Objekt die Quelle.
    """
    path = runtime.get("registry_path")
    if path is None:
        return runtime["registry"]
    return registry_mod.load(path)


@app.route("/api/v1/geraete/", methods=["GET"])
def get_geraete():
    """GER-13: alle Geräte der Familie (GER-5)."""
    return jsonify([g.to_dict() for g in _aktuelle_registry().list_all()])


@app.route("/api/v1/geraete/<geraet_id>", methods=["GET"])
def get_geraet(geraet_id):
    """GER-14: ein Gerät je `display_id` (GER-5). Unbekannte id: 404."""
    g = _aktuelle_registry().get(geraet_id)
    if g is None:
        return jsonify({"error": "unbekannte id"}), 404
    return jsonify(g.to_dict())


def _bad_request(msg):
    """GER-15: 4xx mit JSON-Fehler, keine Stack-Traces (analog FAM-12)."""
    return jsonify({"error": msg}), 400


@app.route("/api/v1/geraete/", methods=["POST"])
def post_geraet():
    """GER-15: Gerät anlegen.

    JSON-Body `{typ, name, aufloesung, os, verwendung, status?}`:

    - `typ` (Pflicht) — einer aus GER-2
    - `name` (Pflicht) — Anzeigename, nicht leer
    - `aufloesung` (Pflicht) — `{w, h}` mit positiven Ganzzahlen (GER-3)
    - `os` (Pflicht) — einer aus GER-3 OS_WERTE
    - `verwendung` (Pflicht) — einer aus GER-3 VERWENDUNGEN
    - `status` (optional, Default `aktiv`) — einer aus GER-3 STATUS_WERTE

    Antwort 200 mit dem Geräte-JSON inkl. vergebener IDENT-1-`id`
    (`<typ>-<slug>-<nn>` über `geraete.neue_id`, GER-7).

    Read-Modify-Write läuft hinter `_write_lock`, damit parallele POSTs
    nicht den jeweils anderen Eintrag verlieren — zwei Threads bekommen
    damit zwei verschiedene `display_id`s, beide Einträge landen in der
    Registry (DCOMP-4 atomar über `geraete.save`).
    """
    path = runtime.get("registry_path")
    if path is None:
        # In-Memory-Modus (Tests ohne Registry-Pfad): wir markieren das
        # explizit als 503 statt eine halbe Wahrheit zu liefern — analog
        # familie/main.py post_person.
        return jsonify({"error": "kein Registry-Pfad konfiguriert"}), 503

    body = request.get_json(silent=True) or {}
    typ = (body.get("typ") or "").strip()
    name = (body.get("name") or "").strip()
    aufloesung_raw = body.get("aufloesung")
    os_wert = (body.get("os") or "").strip()
    verwendung = (body.get("verwendung") or "").strip()
    status = (body.get("status") or "aktiv").strip()

    if not typ:
        return _bad_request("typ fehlt")
    if typ not in registry_mod.TYPEN:
        return _bad_request(
            "typ %r nicht in %r (GER-2)" % (typ, list(registry_mod.TYPEN)))
    if not name:
        return _bad_request("name fehlt oder ist leer")
    if os_wert not in registry_mod.OS_WERTE:
        return _bad_request(
            "os %r nicht in %r (GER-3)" % (os_wert, list(registry_mod.OS_WERTE)))
    if verwendung not in registry_mod.VERWENDUNGEN:
        return _bad_request(
            "verwendung %r nicht in %r (GER-3)"
            % (verwendung, list(registry_mod.VERWENDUNGEN)))
    if status not in registry_mod.STATUS_WERTE:
        return _bad_request(
            "status %r nicht in %r (GER-3)"
            % (status, list(registry_mod.STATUS_WERTE)))
    # `aufloesung` wird in `Registry.add`/`_validate_dict` gegen GER-3 geprüft —
    # wir reichen sie 1:1 weiter und übersetzen RegistryError in 400.
    if not isinstance(aufloesung_raw, dict):
        return _bad_request(
            "aufloesung muss {w,h} mit positiven Ganzzahlen sein (GER-3)")

    with _write_lock:
        # DCOMP-2: frisch von Disk lesen — sonst sehen wir parallele
        # Cross-Service-Schreibvorgänge (z. B. GAA) nicht und überschreiben sie.
        reg = registry_mod.load(path)
        try:
            display_id = registry_mod.neue_id(reg, typ, name)
        except (registry_mod.RegistryError, ValueError) as e:
            return _bad_request(str(e))
        try:
            geraet = registry_mod.Geraet(
                id=display_id, typ=typ, name=name,
                aufloesung=aufloesung_raw, os=os_wert,
                verwendung=verwendung, status=status)
            reg.add(geraet)
        except registry_mod.RegistryError as e:
            return _bad_request(str(e))
        try:
            registry_mod.save(reg, path)
        except registry_mod.RegistryError as e:
            logging.warning("post_geraet: Schreiben fehlgeschlagen: %s", e)
            return jsonify({"error": str(e)}), 503
    return jsonify(geraet.to_dict()), 200


# ============================================================
#  Entrypoint (GER-9)
# ============================================================

# Runtime-Konfig-Schema (CONFIG-1): nur die Werte, die der Service-Start
# braucht — Bind, Log-Level. Datei + ENV laufen über den gemeinsamen
# `tools.configloader`, CLI-Flags überschreiben den Loader-Output danach.
# Familienspezifische Werte (Geräte selbst) liegen in `geraete.json` (GER-4)
# — das ist eine andere Sache, Registry-Datei statt Runtime-Knöpfe.
RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5040,
    "log_level":   "INFO",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Geräte-Registry V1")
    # GER-9: Der Pfad zur Registry-Datei kann nicht in der Datei selbst stehen
    # und bleibt deshalb Env/CLI.
    p.add_argument("--geraete", default="geraete.json",
                   help="Pfad zur Registry-Datei (GER-9)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level",
                   help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key",  help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_config(args):
    """Auflösung der RUNTIME-Konfiguration: Datei < ENV < CLI (CONFIG-1).

    Host/Port/Log-Level kommen vom gemeinsamen `tools.configloader`
    (CONFIG-1) — Datei (`geraete/config.json`, gitignored, optional) und
    ENV (`GERAETE_LISTEN_HOST`, `GERAETE_LISTEN_PORT`, `GERAETE_LOG_LEVEL`).
    CLI-Flags überschreiben den Loader-Output danach (CONFIG-1: CLI ist
    Test-Werkzeug, nicht Konfiguration).

    `geraete` ist der Pfad zur Registry-Datei (GER-9) selbst und bleibt
    außerhalb des Loader-Schemas — analog familie/main.py. ENV-Override
    `GERAETE_REGISTRY` deckt den Dev-Override für den Registry-Pfad ab
    (Namensschema CONFIG-5: `<COMPONENT>_<KEY>`).
    """
    cfg = configloader.load(component="geraete", schema=RUNTIME_SCHEMA)
    cfg["geraete"] = os.environ.get("GERAETE_REGISTRY", args.geraete)
    if args.host:      cfg["listen_host"] = args.host
    if args.port:      cfg["listen_port"] = args.port
    if args.log_level: cfg["log_level"]   = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    # LOG-4: zentraler Setup statt eigenem basicConfig. Level kommt aus der
    # Runtime-Config (CONFIG-1/CONFIG-2).
    logsetup.setup(cfg["log_level"])

    reg = registry_mod.load(cfg["geraete"])
    configure(reg, registry_path=cfg["geraete"])

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logging.info("Geräte-Registry hört auf %s://%s:%s (registry=%s)",
                 scheme, cfg["listen_host"], cfg["listen_port"], cfg["geraete"])
    app.run(host=cfg["listen_host"], port=cfg["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
