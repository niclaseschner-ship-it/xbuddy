#!/usr/bin/env python3
"""Familien-Registry — HTTP-Schnittstelle + Entrypoint.

Siehe specs/platform/familie.md (Refs #38).

Service-Topologie (Impl-Entscheidung, FAM bewusst offen): die Registry läuft
als schlanke eigenständige Flask-App — ein Geschwister von router/ und
eltern-chat/. KEIN auf Vorrat gebauter Dienst-Verbund: die App kann allein
starten, und ihre Endpunkte sind über `app` als Blueprint-loses Flask-Objekt
auch von einem späteren Mit-Host importierbar. Mehr braucht V1 nicht.

Endpunkte:
  GET /api/v1/familie/personen        — alle Personen (FAM-7)
  GET /api/v1/familie/personen/<id>   — eine Person je id (FAM-7)
  GET /api/v1/familie/foto/<id>       — Profilfoto, 200/404 (FAM-8)
"""

import argparse
import logging
import os
import sys

from flask import Flask, jsonify, send_file

import registry as registry_mod


# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Die geladene Registry + das Foto-Verzeichnis (FAM-9). Der Entrypoint befüllt
# sie; Tests setzen sie direkt über configure().
runtime = {
    "registry":         registry_mod.Registry(),
    "foto_verzeichnis": "fotos",
}


def configure(reg, foto_verzeichnis):
    """Setzt die laufende Registry + das Foto-Verzeichnis (FAM-9)."""
    runtime["registry"] = reg
    runtime["foto_verzeichnis"] = foto_verzeichnis


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)


@app.route("/api/v1/familie/personen", methods=["GET"])
def get_personen():
    """FAM-7: alle Personen der Familie (ohne Foto-Binär)."""
    return jsonify([p.to_dict() for p in runtime["registry"].alle()])


@app.route("/api/v1/familie/personen/<person_id>", methods=["GET"])
def get_person(person_id):
    """FAM-7: eine Person je id. Unbekannte id: 404."""
    person = runtime["registry"].get(person_id)
    if person is None:
        return jsonify({"error": "unbekannte id"}), 404
    return jsonify(person.to_dict())


@app.route("/api/v1/familie/foto/<person_id>", methods=["GET"])
def get_foto(person_id):
    """FAM-8: Profilfoto über HTTP.

    Bekannte id mit Foto: 200 mit der Bilddatei. Bekannte id ohne Foto oder
    unbekannte id: 404. Der Pfad ist geräte-neutral (URL-10).
    """
    pfad = registry_mod.foto_pfad(
        runtime["registry"], runtime["foto_verzeichnis"], person_id)
    if pfad is None:
        return jsonify({"error": "kein Foto"}), 404
    return send_file(pfad)


# ============================================================
#  Entrypoint (FAM-9)
# ============================================================

DEFAULTS = {
    "listen_host": "127.0.0.1",
    "listen_port": 5010,
    "log_level":   "INFO",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Familien-Registry V1")
    p.add_argument("--registry", default="familie.json",
                   help="Pfad zur Registry-Datei (FAM-9)")
    p.add_argument("--fotos", dest="foto_verzeichnis",
                   help="Foto-Verzeichnis (FAM-9; Default: fotos/ neben der Registry-Datei)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key",  help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_config(args):
    """FAM-9-Auflösung: Defaults < ENV < CLI."""
    cfg = dict(DEFAULTS)
    cfg["registry"] = args.registry
    # FAM-9: Foto-Verzeichnis Default ist `fotos/` NEBEN der Registry-Datei.
    cfg["foto_verzeichnis"] = os.path.join(
        os.path.dirname(os.path.abspath(args.registry)), "fotos")
    if "FAMILIE_REGISTRY"  in os.environ: cfg["registry"]         = os.environ["FAMILIE_REGISTRY"]
    if "FAMILIE_FOTOS"     in os.environ: cfg["foto_verzeichnis"] = os.environ["FAMILIE_FOTOS"]
    if "FAMILIE_HOST"      in os.environ: cfg["listen_host"]      = os.environ["FAMILIE_HOST"]
    if "FAMILIE_PORT"      in os.environ: cfg["listen_port"]      = int(os.environ["FAMILIE_PORT"])
    if "FAMILIE_LOG_LEVEL" in os.environ: cfg["log_level"]        = os.environ["FAMILIE_LOG_LEVEL"]
    if args.foto_verzeichnis: cfg["foto_verzeichnis"] = args.foto_verzeichnis
    if args.host:             cfg["listen_host"]      = args.host
    if args.port:             cfg["listen_port"]      = args.port
    if args.log_level:        cfg["log_level"]        = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    logging.basicConfig(
        level=getattr(logging, cfg["log_level"].upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s")

    reg = registry_mod.load(cfg["registry"])
    configure(reg, cfg["foto_verzeichnis"])

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logging.info("Familien-Registry hört auf %s://%s:%s (fotos=%s)",
                 scheme, cfg["listen_host"], cfg["listen_port"], cfg["foto_verzeichnis"])
    app.run(host=cfg["listen_host"], port=cfg["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
