#!/usr/bin/env python3
"""Routine-Buddy-App — HTTP-Schnittstelle + Entrypoint (ROUTINE-1 … ROUTINE-19).

Siehe specs/buddies/routine.md. Der Routine-Buddy ist die XBuddy-App mit
dem Buddy-Slug `routine` (ROUTINE-1). Er besitzt seine Daten (Routine-Punkte
und Zeiten, ROUTINE-12), seine Funktion (die ablaufende Uhr, ROUTINE-9) und
stellt das Ergebnis über seine Display-View bereit (APP-1).

Endpunkt:
  GET  /display/routine/morgen          — View `morgen` (ROUTINE-2)
  POST /display/routine/toggle/<id>     — Tap → Abhak-Toggle (ROUTINE-7)

V1 hat keine externe API (ROUTINE-14, E-ROUTINE-5).
Statische Assets unter /display/routine/static/<asset> (URL-13).
Port: 5050 (ROUTINE-15).
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, redirect, render_template, url_for

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import configloader, logsetup  # noqa: E402

if __package__:
    from . import config as config_mod
    from . import render as render_mod
    from . import uhr as uhr_mod
else:  # python3 routine/main.py
    sys.path.insert(0, _REPO_ROOT)
    from routine import config as config_mod
    from routine import render as render_mod
    from routine import uhr as uhr_mod


# ============================================================
#  Abhak-Datenhaltung (ROUTINE-8)
# ============================================================
#
# Schlanke JSON-Datei neben dem Code, gitignored (ROUTINE-8, BUD-2a).
# Hält nur den flüchtigen Tageszustand (welche Item-IDs heute abgehakt sind).
# Punkt-Definitionen kommen aus der Config — keine doppelte Wahrheit.

_STORE_FILE = os.path.join(_HERE, "routine_store.json")


def _store_path():
    return runtime.get("store_path") or _STORE_FILE


def _load_store():
    """Lädt den Abhak-Store. Fehlt die Datei → leerer Zustand (ROUTINE-8)."""
    path = _store_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Abhak-Store nicht lesbar (%s): %s — starte leer", path, e)
        return {}


def _save_store(data):
    """Speichert den Abhak-Store."""
    path = _store_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("Abhak-Store konnte nicht gespeichert werden (%s): %s", path, e)


def _heute_str(zeitzone):
    """Heutiges Datum als 'YYYY-MM-DD' in der Familien-Zeitzone."""
    return datetime.now(ZoneInfo(zeitzone)).date().isoformat()


def _abhak_zustand(zeitzone):
    """Liefert den Abhak-Zustand für heute (ROUTINE-6/7/8).

    Tageswechsel → Zustand leer (täglicher Reset, ROUTINE-6).
    """
    store = _load_store()
    heute = _heute_str(zeitzone)
    tag_daten = store.get("tag", {})
    if tag_daten.get("datum") != heute:
        # Tageswechsel: Zustand zurücksetzen (ROUTINE-6)
        return {}
    return tag_daten.get("abgehakt", {})


def _toggle_abhak(item_id, zeitzone):
    """Toggelt den Abhak-Zustand eines Items für heute (ROUTINE-7).

    Persistiert über Reload (ROUTINE-7), Reset bei Tageswechsel (ROUTINE-6).
    """
    store = _load_store()
    heute = _heute_str(zeitzone)
    tag_daten = store.get("tag", {})
    if tag_daten.get("datum") != heute:
        tag_daten = {"datum": heute, "abgehakt": {}}
    abgehakt = tag_daten.get("abgehakt", {})
    abgehakt[item_id] = not abgehakt.get(item_id, False)
    tag_daten["abgehakt"] = abgehakt
    store["tag"] = tag_daten
    _save_store(store)
    return abgehakt[item_id]


# ============================================================
#  Laufzeit-Zustand
# ============================================================

runtime = {
    "config": None,       # routine.config.RoutineConfig — Last-Known-Good-Snapshot
    "data_path": None,    # Pfad zu routine.json — für späteres Reload-on-Read
    "store_path": None,   # Pfad zu routine_store.json (Test-Naht)
}


def configure(cfg, data_path=None, store_path=None):
    """Setzt die Konfiguration (Test-Naht)."""
    runtime["config"] = cfg
    runtime["data_path"] = data_path
    runtime["store_path"] = store_path


def _current_config():
    """Liefert die aktuelle Config (Last-Known-Good-Snapshot)."""
    return runtime["config"]


def _now(zeitzone):
    """Aktuelle Zeit in der Familien-Zeitzone. Test-Naht: `?_now=HH:MM` (opt.)."""
    return datetime.now(ZoneInfo(zeitzone))


# ============================================================
#  Flask-App
# ============================================================

# URL-13: statische Assets im Display-Namensraum des Buddys (ROUTINE-2, BUD-1).
app = Flask(__name__, static_url_path="/display/routine/static")


@app.route("/display/routine/morgen", methods=["GET"])
def morgen():
    """View `morgen` — Routine-Checkliste + ablaufende Uhr (ROUTINE-2).

    Eine einzige Canvas: links Checkliste, rechts Uhr. Kein Routing, kein Tab
    (ROUTINE-2). Rendert heutige Items mit Abhak-Zustand und Uhr-Block.
    """
    cfg = _current_config()
    zeitzone = cfg.zeitzone
    now = _now(zeitzone)
    tag = now.date()

    # Uhr (ROUTINE-9): injizierbares now
    try:
        zeiten = uhr_mod.berechne_zeiten(
            cfg.abfahrtszeit, cfg.anzieh_vorlauf_min, zeitzone, tag)
        uhr_view = uhr_mod.baue_uhr_view(zeiten, now) if zeiten else None
    except Exception as e:
        logger.error("Uhr-Berechnung fehlgeschlagen: %s — Uhr wird ausgeblendet", e)
        uhr_view = None

    abhak = _abhak_zustand(zeitzone)
    view = render_mod.baue_view(cfg, abhak, uhr_view)

    return render_template("morgen.html", view=view)


@app.route("/display/routine/toggle/<item_id>", methods=["POST"])
def toggle(item_id):
    """Tap → Abhak-Toggle (ROUTINE-7). View-eigene Interaktion (ROUTINE-3).

    Toggelt den heutigen Abhak-Zustand des Items, persistiert über Reload.
    Keine externe API (ROUTINE-14: V1 hat keine /api/v1/routine/).
    """
    cfg = _current_config()

    # Validierung: Item-ID muss in der Config existieren (ROUTINE-5)
    item_ids = {item.id for item in cfg.items}
    if item_id not in item_ids:
        return jsonify({"error": "unbekannte Item-ID"}), 404

    neuer_zustand = _toggle_abhak(item_id, cfg.zeitzone)
    return jsonify({"id": item_id, "abgehakt": neuer_zustand})


@app.route("/display/routine/")
@app.route("/display/routine")
def index():
    """Weiterleitung zur View `morgen` (BUD-1, ROUTINE-2)."""
    return redirect(url_for("morgen"))


# ============================================================
#  Entrypoint (ROUTINE-15/17)
# ============================================================

logger = logging.getLogger(__name__)

# Runtime-Konfig-Schema (CONFIG-1): nur Service-Start-Werte.
# Port 5050 (ROUTINE-15, OPEN-ROUTINE-H — erster freier Buddy-Block-Port).
RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5050,
    "log_level":   "INFO",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Routine-Buddy-App V1")
    p.add_argument("--config", dest="data_file", default=None,
                   help="Pfad zu routine.json (ROUTINE-12)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key", help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_runtime_config(args):
    """Host/Port/Log-Level: Datei < ENV < CLI (CONFIG-1/CONFIG-5)."""
    cfg = configloader.load(component="routine", schema=RUNTIME_SCHEMA)
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

    data_path = (args.data_file
                 or os.environ.get(config_mod.ENV_DATA_FILE)
                 or config_mod.DEFAULT_DATA_FILE)
    cfg = config_mod.resolve_data(data_path)
    configure(cfg, data_path=data_path)

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logger.info(
        "Routine-Buddy hört auf %s://%s:%s (items=%d, zeitzone=%s)",
        scheme, rt["listen_host"], rt["listen_port"],
        len(cfg.items), cfg.zeitzone)
    app.run(host=rt["listen_host"], port=rt["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
