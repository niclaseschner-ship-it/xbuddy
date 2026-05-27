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

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1, #179)
# auch beim Direktstart `python3 familie/main.py` gefunden wird — analog zu
# plan/main.py und router/main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Paket-Import wie der Plan-Buddy (plan/main.py): `from familie import …`,
# damit `python -m familie.main` aus dem Repo-Root funktioniert. Der nackte
# `import registry` funktionierte nur, wenn der Service aus dem
# familie/-Verzeichnis direkt gestartet wurde — Workaround auf dem Pi war
# `WorkingDirectory=…/familie` im systemd-File.
from familie import registry as registry_mod  # noqa: E402
from tools import configloader, logsetup  # noqa: E402


# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Die geladene Registry + das Foto-Verzeichnis (FAM-9) + der Registry-Pfad
# (Fix-Familie-Registry-Konsistenz: Pro-Request-Reload + Foto-Pfad „neben
# der Registry-Datei"). Der Entrypoint befüllt das Dict; Tests setzen es
# direkt über configure().
runtime = {
    "registry":         registry_mod.Registry(),
    "foto_verzeichnis": "fotos",
    "registry_path":    None,
}


def configure(reg, foto_verzeichnis=None, registry_path=None):
    """Setzt die laufende Registry + das aufgelöste Foto-Verzeichnis (FAM-9).

    Wird `foto_verzeichnis` nicht übergeben, leitet die Funktion es aus
    `reg.settings` ab. Wenn auch `registry_path` gesetzt ist, wird die
    FAM-9-Aussage „**neben der Registry-Datei**" eingelöst:
    `registry_mod.resolved_foto_verzeichnis` löst relative Werte gegen das
    Registry-Verzeichnis auf. Ohne `registry_path` bleibt das alte
    Verhalten (nackter Settings/ENV/Default-Wert) — für Tests, die nur eine
    Registry hereinreichen und das Foto-Verzeichnis selbst absolut machen.
    """
    runtime["registry"] = reg
    runtime["registry_path"] = registry_path
    if foto_verzeichnis is None:
        if registry_path is not None:
            foto_verzeichnis = registry_mod.resolved_foto_verzeichnis(
                reg.settings, registry_path)
        else:
            foto_verzeichnis = registry_mod.effective_setting(
                reg.settings.foto_verzeichnis, "FAMILIE_FOTOS",
                DEFAULTS["foto_verzeichnis"])
    runtime["foto_verzeichnis"] = foto_verzeichnis


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)


def _aktuelle_registry():
    """Liefert die aktuelle Familien-Registry für genau diesen Request.

    Bugfix aus dem Pi-Live-Test: Service-Start lud `familie.json` einmal in
    `runtime["registry"]` als Python-Objekt im RAM. Sobald FAA über den
    Eltern-Chat-Bot extern eine Person ergänzte, sah dieser Service den
    neuen Stand erst nach Restart — kein Produkt.

    Heute ist die Familie winzig (≤10 Personen), JSON-Disk-IO unter 1 ms.
    Wir laden bei jedem Request frisch, statt einen mtime-Cache zu bauen
    (eigenes Ticket, wenn das je teurer wird). Im Test-Modus (kein
    `registry_path` gesetzt) bleibt das in-memory-Objekt aus `configure()`
    die Quelle.
    """
    path = runtime.get("registry_path")
    if path is None:
        return runtime["registry"]
    return registry_mod.load(path)


@app.route("/api/v1/familie/personen", methods=["GET"])
def get_personen():
    """FAM-7: alle Personen der Familie (ohne Foto-Binär)."""
    return jsonify([p.to_dict() for p in _aktuelle_registry().alle()])


@app.route("/api/v1/familie/personen/<person_id>", methods=["GET"])
def get_person(person_id):
    """FAM-7: eine Person je id. Unbekannte id: 404."""
    person = _aktuelle_registry().get(person_id)
    if person is None:
        return jsonify({"error": "unbekannte id"}), 404
    return jsonify(person.to_dict())


@app.route("/api/v1/familie/foto/<person_id>", methods=["GET"])
def get_foto(person_id):
    """FAM-8: Profilfoto über HTTP.

    Bekannte id mit Foto: 200 mit der Bilddatei. Bekannte id ohne Foto oder
    unbekannte id: 404. Der Pfad ist geräte-neutral (URL-10).
    """
    # Foto-Verzeichnis ebenfalls je Request über den FAM-9-Resolver auflösen,
    # damit ein Settings-Wechsel in `familie.json` (Foto-Verzeichnis) ohne
    # Service-Restart greift — gleiche Begründung wie für Personen.
    reg = _aktuelle_registry()
    path = runtime.get("registry_path")
    if path is not None:
        foto_verzeichnis = registry_mod.resolved_foto_verzeichnis(
            reg.settings, path)
    else:
        foto_verzeichnis = runtime["foto_verzeichnis"]
    pfad = registry_mod.foto_pfad(reg, foto_verzeichnis, person_id)
    if pfad is None:
        return jsonify({"error": "kein Foto"}), 404
    return send_file(pfad)


# ============================================================
#  Entrypoint (FAM-9)
# ============================================================

# Familienspezifische Defaults (FAM-9-Tabelle) — diese Werte liegen in
# `familie.json` settings und werden über den Settings-Lader aufgelöst
# (`load_settings`), nicht über `tools.configloader`. Sie bleiben hier als
# Fallback-Defaults für `load_settings()`/`configure()`, damit FAA dieselbe
# Quelle nutzt (zentral in `registry.FAM9_DEFAULTS`).
DEFAULTS = {
    "foto_verzeichnis":     registry_mod.FAM9_DEFAULTS["foto_verzeichnis"],
    "profilbild_max_kante": registry_mod.FAM9_DEFAULTS["profilbild_max_kante"],
}

# Runtime-Konfig-Schema (CONFIG-1, #179): nur die Werte, die der Service-Start
# braucht — Bind, Log-Level. Datei + ENV laufen über den gemeinsamen
# `tools.configloader`, CLI-Flags überschreiben den Loader-Output danach.
# Familienspezifische Werte (Foto-Verzeichnis, Profilbild-Max-Kante) liegen
# weiter in `familie.json` settings (FAM-9) — das ist eine andere Sache,
# Registry-Datei statt Runtime-Knöpfe.
RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5010,
    "log_level":   "INFO",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Familien-Registry V1")
    # FAM-9: Der Pfad zur Registry-Datei kann nicht in der Datei selbst stehen
    # und bleibt deshalb Env/CLI. Alle übrigen familienspezifischen Werte
    # liegen in `familie.json` settings (kein eigenes CLI-Flag, FAM-9).
    p.add_argument("--registry", default="familie.json",
                   help="Pfad zur Registry-Datei (FAM-9)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key",  help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_config(args):
    """Auflösung der RUNTIME-Konfiguration: Datei < ENV < CLI (CONFIG-1).

    Host/Port/Log-Level kommen vom gemeinsamen `tools.configloader` (CONFIG-1,
    #179) — Datei (`familie/config.json`, gitignored, optional) und ENV
    (`FAMILIE_LISTEN_HOST`, `FAMILIE_LISTEN_PORT`, `FAMILIE_LOG_LEVEL`).
    CLI-Flags überschreiben den Loader-Output danach (CONFIG-1: CLI ist
    Test-Werkzeug, nicht Konfiguration).

    `registry` ist der Pfad zur Registry-Datei (FAM-9) selbst und bleibt
    außerhalb des Loader-Schemas — analog zu plan/main.py, wo `--config` /
    `ENV_CONFIG_FILE` ebenfalls separat aufgelöst werden. ENV-Override
    `FAMILIE_REGISTRY` bleibt erhalten.

    Familienspezifische Werte (Foto-Verzeichnis, Profilbild-Max-Kante) liegen
    nach FAM-9 in `familie.json` settings und werden über `load_settings`
    aufgelöst — nicht hier.
    """
    cfg = configloader.load(component="familie", schema=RUNTIME_SCHEMA)
    cfg["registry"] = os.environ.get("FAMILIE_REGISTRY", args.registry)
    if args.host:      cfg["listen_host"] = args.host
    if args.port:      cfg["listen_port"] = args.port
    if args.log_level: cfg["log_level"]   = args.log_level
    return cfg


def load_settings(registry, registry_path=None):
    """FAM-9-Auflösung der familienspezifischen Settings.

    Liefert ein Dict {`foto_verzeichnis`, `profilbild_max_kante`} mit den
    EFFEKTIVEN Werten — das ist, was die Konsumenten sehen sollen. Quelle je
    Wert: Registry-Settings (`familie.json`) > ENV-Override (Ops-Notfall) >
    hartkodierter Default (DEFAULTS). Es gibt nach FAM-9 KEIN CLI-Override
    mehr.

    Bei gesetztem `registry_path` löst `foto_verzeichnis` zusätzlich die
    FAM-9-Aussage „neben der Registry-Datei" ein: ein relativer Wert wird
    gegen das Verzeichnis der Registry-Datei aufgelöst, statt gegen den
    CWD des Prozesses (Bug aus dem Pi-Live-Test: drei Konsumenten, drei
    CWDs, drei Auflösungen — Fotos lagen woanders als die Registry).
    """
    if registry_path is not None:
        foto_verzeichnis = registry_mod.resolved_foto_verzeichnis(
            registry.settings, registry_path)
    else:
        foto_verzeichnis = registry_mod.effective_setting(
            registry.settings.foto_verzeichnis,
            "FAMILIE_FOTOS",
            DEFAULTS["foto_verzeichnis"])
    return {
        "foto_verzeichnis": foto_verzeichnis,
        "profilbild_max_kante": registry_mod.effective_setting(
            registry.settings.profilbild_max_kante,
            "FAMILIE_PROFILBILD_MAX_KANTE",
            DEFAULTS["profilbild_max_kante"]),
    }


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    # LOG-4 (#166): zentraler Setup statt eigenem basicConfig. Level kommt
    # aus der Runtime-Config (CONFIG-1/CONFIG-2, RUNTIME_SCHEMA — #209).
    logsetup.setup(cfg["log_level"])

    reg = registry_mod.load(cfg["registry"])
    settings = load_settings(reg, registry_path=cfg["registry"])
    configure(reg, settings["foto_verzeichnis"], registry_path=cfg["registry"])

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logging.info("Familien-Registry hört auf %s://%s:%s (fotos=%s)",
                 scheme, cfg["listen_host"], cfg["listen_port"],
                 settings["foto_verzeichnis"])
    app.run(host=cfg["listen_host"], port=cfg["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
