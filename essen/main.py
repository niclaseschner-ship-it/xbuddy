#!/usr/bin/env python3
"""Essens-Buddy-App — HTTP-Schnittstelle + Entrypoint (ESSEN-1 … ESSEN-25).

Siehe specs/buddies/essen.md. Der Essens-Buddy ist die XBuddy-App mit dem
Buddy-Slug `essen` (ESSEN-1). Er besitzt seine Daten (Wunsch-Liste und
Gerichte-Katalog, ESSEN-21) und seine Funktion (Katalog-Strukturierung,
Schreibpfade) und stellt das Ergebnis über seine Display-View und HTTP-API
bereit (ESSEN-15..ESSEN-20).

Endpunkte:
  GET  /display/essen/wunsch             — View (Tabbed Single-Canvas, ESSEN-2)
  GET  /healthz                          — Health-Check (SVC-1)
  GET  /api/v1/essen/wuensche            — Wunsch-Liste lesen (ESSEN-15)
  POST /api/v1/essen/wuensche            — Wunsch hinzufügen (ESSEN-16)
  DELETE /api/v1/essen/wuensche/<id>     — Wunsch entfernen (ESSEN-17)
  GET  /api/v1/essen/katalog             — Katalog lesen (ESSEN-18)
  POST /api/v1/essen/katalog/gerichte    — Gericht anlegen (ESSEN-19)
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import configloader, logsetup  # noqa: E402

if __package__:
    from . import config as config_mod
    from . import katalog as katalog_mod
    from . import render as render_mod
    from . import store as store_mod
else:
    sys.path.insert(0, _REPO_ROOT)
    from essen import config as config_mod
    from essen import katalog as katalog_mod
    from essen import render as render_mod
    from essen import store as store_mod


# ============================================================
#  Laufzeit-Zustand
# ============================================================
#
# Analog wetter/main.py: `runtime` hält Last-Known-Good-Snapshots (DCOMP-3).
# Alle Endpoints lesen frisch von Disk (Reload-on-Read, ESSEN-20).
runtime = {
    "paths":             None,   # dict: wuensche_file, gerichte_file, katalog_file, …
    "wuensche_snapshot": None,   # Last-Known-Good für Wunsch-Liste (DCOMP-3)
    "gerichte_snapshot": None,   # Last-Known-Good für Gerichte (DCOMP-3)
    "katalog_snapshot":  None,   # Last-Known-Good für Lebensmittel-Override (DCOMP-3)
    "zeitzone":          "Europe/Berlin",
}


def configure(paths, zeitzone="Europe/Berlin"):
    """Setzt die Datei-Pfade und Zeitzone (Test-Naht, analog WETTER-24).

    `paths` ist ein dict aus config_mod.data_paths().
    In Tests werden Test-Pfade übergeben, kein Disk-IO außerhalb.
    """
    runtime["paths"] = paths
    runtime["zeitzone"] = zeitzone


def _paths():
    return runtime["paths"]


def _jetzt():
    """Aktuelle Zeit in der Familien-Zeitzone."""
    return datetime.now(ZoneInfo(runtime["zeitzone"])).isoformat()


def _lade_wuensche_frisch():
    """Reload-on-Read: Wunsch-Liste frisch von Disk (ESSEN-20).

    Aktualisiert den Last-Known-Good-Snapshot bei Erfolg (DCOMP-3).
    """
    p = _paths()
    daten = store_mod.lade_wuensche(p["wuensche_file"], runtime["wuensche_snapshot"])
    runtime["wuensche_snapshot"] = daten
    return daten


def _lade_gerichte_frisch():
    """Reload-on-Read: Gerichte-Katalog frisch von Disk (ESSEN-20)."""
    p = _paths()
    daten = store_mod.lade_gerichte(p["gerichte_file"], runtime["gerichte_snapshot"])
    runtime["gerichte_snapshot"] = daten
    return daten


def _lade_katalog_frisch():
    """Reload-on-Read: Lebensmittel-Katalog frisch (ESSEN-20, ESSEN-12/13)."""
    p = _paths()
    lebensmittel = katalog_mod.lade_lebensmittel(
        p["katalog_file"],
        p["katalog_default_file"],
        runtime["katalog_snapshot"],
    )
    runtime["katalog_snapshot"] = lebensmittel
    return lebensmittel


def _lade_alle_kategorien():
    """Vollständiger Katalog: Lebensmittel + Gerichte (ESSEN-18)."""
    lebensmittel = _lade_katalog_frisch()
    gerichte_daten = _lade_gerichte_frisch()
    gerichte_items = []
    for g in gerichte_daten.get("gerichte", []):
        gerichte_items.append({
            "id":        str(g.get("id", "")),
            "label":     g.get("label", ""),
            "bild_ref":  g.get("bild_ref", ""),
            "kategorie": "gericht",
        })
    return dict(lebensmittel, gericht=gerichte_items)


# ── Validierungshelfer ────────────────────────────────────────────────────

GUELTIGE_QUELLE    = {"kind", "eltern"}
GUELTIGE_KATEGORIE = {"gericht", "obst_gemuese", "brotbelag", "sonstiges"}


def _valide_bild_ref(bild_ref):
    """Prüft, ob bild_ref eine numerische ARASAAC-ID ist (ESSEN-16).

    ICONS-5 verlangt, dass ein lokales PNG existiert. In V1 prüfen wir
    die Numerik der ID — die Plattform-Verfügbarkeit liegt im Icon-Service.
    """
    try:
        int(bild_ref)
        return True
    except (TypeError, ValueError):
        return False


# ============================================================
#  Flask-App
# ============================================================

# URL-13: statische Assets im Display-Namensraum des Essens-Buddys.
app = Flask(__name__, static_url_path="/display/essen/static")


# ── Health-Check (SVC-1) ─────────────────────────────────────────────────

@app.route("/healthz", methods=["GET"])
def healthz():
    """SVC-1: Health-Endpoint — liefert immer 200 + OK."""
    return jsonify({"ok": True}), 200


# ── Display-View (ESSEN-2/3/8/9) ────────────────────────────────────────

@app.route("/display/essen/wunsch", methods=["GET"])
def wunsch_view():
    """View `wunsch` — Tabbed Single-Canvas (ESSEN-2, E-ESSEN-7).

    Drei stets sichtbare Bereiche: Kategorien-Tabs oben, Item-Grid der
    aktiven Kategorie links/Mitte, Wunsch-Liste rechts (ESSEN-8).
    Default-aktiver Tab: obst_gemuese (ESSEN-9).
    """
    aktiv_tab = request.args.get("tab", render_mod.DEFAULT_TAB)

    kategorien = _lade_alle_kategorien()
    wuensche_daten = _lade_wuensche_frisch()

    view = render_mod.baue_view(
        kategorien,
        wuensche_daten.get("wuensche", []),
        aktiv_tab=aktiv_tab,
    )
    return render_template("wunsch.html", view=view)


# ── API: Wünsche (ESSEN-15..17) ──────────────────────────────────────────

@app.route("/api/v1/essen/wuensche", methods=["GET"])
def wuensche_lesen():
    """GET /api/v1/essen/wuensche — Liste lesen (ESSEN-15).

    Antwort: { "wuensche": [...] }, chronologisch (erstellt_am aufsteigend).
    Leer = 200, nicht 404 (ESSEN-15).
    """
    daten = _lade_wuensche_frisch()
    wuensche = sorted(
        daten.get("wuensche", []),
        key=lambda w: w.get("erstellt_am", ""),
    )
    return jsonify({"wuensche": wuensche}), 200


@app.route("/api/v1/essen/wuensche", methods=["POST"])
def wunsch_hinzufuegen():
    """POST /api/v1/essen/wuensche — Wunsch hinzufügen (ESSEN-16).

    Payload: { label, bild_ref, quelle, kategorie, item_id }
    Antwort: { "id": "<quelle>:<n>" }
    Ungültige Eingabe → 400, kein Schreiben (ESSEN-16).
    Duplikat (gleiche item_id bereits auf Liste) → 409 Conflict (ESSEN-16, BUD-2).
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"fehler": "Kein JSON-Body"}), 400

    label     = body.get("label", "")
    bild_ref  = body.get("bild_ref", "")
    quelle    = body.get("quelle", "")
    kategorie = body.get("kategorie", "")
    item_id   = body.get("item_id", "")

    # Fachliche Validierung im Buddy (ESSEN-16, BUD-2: Buddy besitzt seine Daten).
    fehler = []
    if not label or not str(label).strip():
        fehler.append("label darf nicht leer sein")
    if quelle not in GUELTIGE_QUELLE:
        fehler.append("quelle muss 'kind' oder 'eltern' sein")
    if kategorie not in GUELTIGE_KATEGORIE:
        fehler.append("kategorie muss gericht, obst_gemuese, brotbelag oder sonstiges sein")
    if not bild_ref or not _valide_bild_ref(bild_ref):
        fehler.append("bild_ref muss eine numerische ARASAAC-ID sein")
    if not item_id or not str(item_id).strip():
        fehler.append("item_id darf nicht leer sein")
    if fehler:
        return jsonify({"fehler": fehler}), 400

    # item_id muss in einem der konsultierten Kataloge existieren (ESSEN-16, ESSEN-13/14).
    alle_kategorien = _lade_alle_kategorien()
    alle_item_ids = {
        item["id"]
        for items in alle_kategorien.values()
        for item in items
    }
    if str(item_id).strip() not in alle_item_ids:
        return jsonify({"fehler": "item_id unbekannt — nicht im Lebensmittel- oder Gerichte-Katalog"}), 400

    # Atomar schreiben (DCOMP-4, ESSEN-20) — Wunsch-Liste frisch laden,
    # dann ergänzen, dann atomar zurückschreiben.
    p = _paths()
    daten = store_mod.lade_wuensche(p["wuensche_file"], runtime["wuensche_snapshot"])

    # Duplikat-Schutz (ESSEN-16, BUD-2): item_id bereits auf Liste → 409 Conflict.
    item_id_str = str(item_id).strip()
    for w in daten.get("wuensche", []):
        if w.get("item_id") == item_id_str:
            return jsonify({"fehler": "item_already_on_list", "item_id": item_id_str}), 409

    zaehler = daten.get("zaehler", {"kind": 0, "eltern": 0})
    n = zaehler.get(quelle, 0) + 1
    neue_id = "%s:%d" % (quelle, n)
    zaehler[quelle] = n

    neuer_wunsch = {
        "id":          neue_id,
        "label":       str(label).strip(),
        "bild_ref":    str(bild_ref),
        "quelle":      quelle,
        "kategorie":   kategorie,
        "item_id":     item_id_str,
        "erstellt_am": _jetzt(),
    }
    wuensche = list(daten.get("wuensche", []))
    wuensche.append(neuer_wunsch)
    neu_daten = {"wuensche": wuensche, "zaehler": zaehler}

    store_mod.speichere_wuensche(p["wuensche_file"], neu_daten)
    runtime["wuensche_snapshot"] = neu_daten

    logger.info("Wunsch angelegt id=%s item_id=%s label=%r quelle=%s kategorie=%s",
                neue_id, item_id_str, label, quelle, kategorie)
    return jsonify({"id": neue_id}), 201


@app.route("/api/v1/essen/wuensche/<wunsch_id>", methods=["DELETE"])
def wunsch_loeschen(wunsch_id):
    """DELETE /api/v1/essen/wuensche/<id> — Wunsch entfernen (ESSEN-17).

    Idempotent: zweites DELETE auf dieselbe ID → 200 (ESSEN-17).
    """
    p = _paths()
    daten = store_mod.lade_wuensche(p["wuensche_file"], runtime["wuensche_snapshot"])
    wuensche = [w for w in daten.get("wuensche", []) if w.get("id") != wunsch_id]
    neu_daten = {"wuensche": wuensche, "zaehler": daten.get("zaehler", {"kind": 0, "eltern": 0})}
    store_mod.speichere_wuensche(p["wuensche_file"], neu_daten)
    runtime["wuensche_snapshot"] = neu_daten
    return jsonify({}), 200


# ── API: Katalog (ESSEN-18/19) ────────────────────────────────────────────

@app.route("/api/v1/essen/katalog", methods=["GET"])
def katalog_lesen():
    """GET /api/v1/essen/katalog — Katalog lesen (ESSEN-18).

    Antwort: { "kategorien": { gericht, obst_gemuese, brotbelag, sonstiges } }
    Gerichte-Kategorie leer bis erste GAN-Eintragung (ESSEN-14).
    """
    kategorien = _lade_alle_kategorien()
    return jsonify({"kategorien": kategorien}), 200


@app.route("/api/v1/essen/katalog/gerichte", methods=["POST"])
def gericht_anlegen():
    """POST /api/v1/essen/katalog/gerichte — Gericht anlegen (ESSEN-19).

    Payload: { label, bild_ref }  (kategorie ist implizit 'gericht')
    Antwort: { "id": "<n>" }
    Duplikates label → 409 (ESSEN-19).
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"fehler": "Kein JSON-Body"}), 400

    label    = body.get("label", "")
    bild_ref = body.get("bild_ref", "")

    fehler = []
    if not label or not str(label).strip():
        fehler.append("label darf nicht leer sein")
    if not bild_ref or not _valide_bild_ref(bild_ref):
        fehler.append("bild_ref muss eine numerische ARASAAC-ID sein")
    if fehler:
        return jsonify({"fehler": fehler}), 400

    p = _paths()
    daten = store_mod.lade_gerichte(p["gerichte_file"], runtime["gerichte_snapshot"])
    gerichte = daten.get("gerichte", [])

    # Duplikat-Check (ESSEN-19: gleiches label → 409).
    label_norm = str(label).strip().lower()
    for g in gerichte:
        if g.get("label", "").strip().lower() == label_norm:
            return jsonify({"fehler": "Gericht mit diesem Label existiert bereits"}), 409

    zaehler = daten.get("zaehler", 0) + 1
    neue_id = str(zaehler)
    neues_gericht = {
        "id":        neue_id,
        "label":     str(label).strip(),
        "bild_ref":  str(bild_ref),
        "kategorie": "gericht",
    }
    gerichte = list(gerichte)
    gerichte.append(neues_gericht)
    neu_daten = {"gerichte": gerichte, "zaehler": zaehler}
    store_mod.speichere_gerichte(p["gerichte_file"], neu_daten)
    runtime["gerichte_snapshot"] = neu_daten

    logger.info("Gericht angelegt id=%s label=%r", neue_id, label)
    return jsonify({"id": neue_id}), 201


# ============================================================
#  Entrypoint (ESSEN-23)
# ============================================================

# Runtime-Konfig-Schema (CONFIG-1): nur die Service-Start-Werte — Bind,
# Log-Level. Listen-Port 5052 (ESSEN-21, PORT-2 `xbuddy-essen`).
RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5052,
    "log_level":   "INFO",
}

logger = logging.getLogger(__name__)


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Essens-Buddy-App V1")
    p.add_argument("--host", help="Bind-Host (Default: 127.0.0.1, PORT-3)")
    p.add_argument("--port", type=int, help="Bind-Port (Default: 5052, PORT-2)")
    p.add_argument("--log-level", dest="log_level",
                   help="DEBUG | INFO | WARNING | ERROR")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # Runtime-Config (CONFIG-1/CONFIG-5): config.json < ENV < CLI.
    rt = configloader.load(component="essen", schema=RUNTIME_SCHEMA)
    if args.host:
        rt["listen_host"] = args.host
    if args.port:
        rt["listen_port"] = args.port
    if args.log_level:
        rt["log_level"] = args.log_level
    logsetup.setup(rt["log_level"])

    paths = config_mod.data_paths()
    configure(paths)

    logger.info(
        "Essens-Buddy hört auf %s:%s (ESSEN-23, PORT-2)",
        rt["listen_host"], rt["listen_port"],
    )
    app.run(host=rt["listen_host"], port=rt["listen_port"],
            debug=False, threaded=True)


if __name__ == "__main__":
    main()
