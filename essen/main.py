#!/usr/bin/env python3
"""Essens-Buddy-App — HTTP-Schnittstelle + Entrypoint (ESSEN-1 … ESSEN-32).

Siehe specs/buddies/essen.md. Der Essens-Buddy ist die XBuddy-App mit dem
Buddy-Slug `essen` (ESSEN-1). Er besitzt seine Daten (Wunsch-Liste,
Einkaufsliste und Gerichte-Katalog, ESSEN-7/21) und seine Funktion
(Katalog-Strukturierung, Schreibpfade) und stellt das Ergebnis über seine
Display-View und HTTP-API bereit (ESSEN-15..ESSEN-20, ESSEN-32).

V1 #653 — klasse-Trennung (ESSEN-7) + neue Endpoints:
- klasse-getrennte Persistenz: wuensche.json / einkaufsliste.json / zaehler.json.
- GET-Filter ?klasse= und ?abgehakt= (ESSEN-15).
- POST-Routing nach klasse (ESSEN-16), Listen-Grenze (ESSEN-29).
- PATCH-Endpoint für sparse-update auf abgehakt / aus_gericht (ESSEN-32).

Endpunkte:
  GET    /display/essen/wunsch             — View (Tabbed Single-Canvas, ESSEN-2)
  GET    /healthz                          — Health-Check (SVC-1)
  GET    /api/v1/essen/wuensche            — Wunsch-Liste lesen (ESSEN-15)
  POST   /api/v1/essen/wuensche            — Wunsch/Einkauf hinzufügen (ESSEN-16)
  PATCH  /api/v1/essen/wuensche/<id>       — Sparse update (ESSEN-32)
  DELETE /api/v1/essen/wuensche/<id>       — Wunsch/Einkauf entfernen (ESSEN-17)
  GET    /api/v1/essen/katalog             — Katalog lesen (ESSEN-18)
  POST   /api/v1/essen/katalog/gerichte    — Gericht anlegen (ESSEN-19)
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
    "paths":                None,   # dict: wuensche_file, einkaufsliste_file, zaehler_file, …
    "wuensche_snapshot":    None,   # Last-Known-Good klasse=wunsch
    "einkauf_snapshot":     None,   # Last-Known-Good klasse=einkauf
    "zaehler_snapshot":     None,   # Last-Known-Good globaler Quellen-Zähler
    "gerichte_snapshot":    None,   # Last-Known-Good Gerichte-Katalog
    "katalog_snapshot":     None,   # Last-Known-Good Lebensmittel-Override
    "zeitzone":             "Europe/Berlin",
    "listen_grenze_wunsch":  100,   # ESSEN-29
    "listen_grenze_einkauf": 100,   # ESSEN-29
}


def configure(paths, zeitzone="Europe/Berlin", listen_grenze=None,
              listen_grenze_wunsch=None, listen_grenze_einkauf=None):
    """Setzt die Datei-Pfade, Zeitzone und Listen-Grenzen (Test-Naht).

    `paths` ist ein dict aus config_mod.data_paths().
    Listen-Grenzen (ESSEN-29): `listen_grenze_wunsch` / `listen_grenze_einkauf`
    überschreiben den Default 100; `listen_grenze` (Übergangs-Schlüssel) greift
    für beide, wenn spezifische Werte fehlen.
    """
    runtime["paths"] = paths
    runtime["zeitzone"] = zeitzone

    # Listen-Grenzen (ESSEN-29): spezifische Overrides haben Vorrang,
    # Übergangs-Schlüssel listen_grenze gilt für beide.
    grenze_w = 100
    grenze_e = 100
    if listen_grenze is not None:
        grenze_w = int(listen_grenze)
        grenze_e = int(listen_grenze)
    if listen_grenze_wunsch is not None:
        grenze_w = int(listen_grenze_wunsch)
    if listen_grenze_einkauf is not None:
        grenze_e = int(listen_grenze_einkauf)
    runtime["listen_grenze_wunsch"]  = grenze_w
    runtime["listen_grenze_einkauf"] = grenze_e


def _paths():
    return runtime["paths"]


def _jetzt():
    """Aktuelle Zeit in der Familien-Zeitzone."""
    return datetime.now(ZoneInfo(runtime["zeitzone"])).isoformat()


# ── Reload-on-Read-Helfer (ESSEN-20, ESSEN-7) ─────────────────────────────

def _lade_wuensche_frisch():
    """Reload-on-Read: klasse=wunsch-File frisch von Disk (ESSEN-20, ESSEN-7).

    Migrations-Hook (ESSEN-7): ist im Alt-Format ein `zaehler` im
    wuensche.json-File und wir haben noch kein zaehler.json, so heben
    wir den Zähler beim Lesen heraus und schreiben ihn nach zaehler.json.
    """
    p = _paths()
    daten = store_mod.lade_wuensche(
        p["wuensche_file"], runtime["wuensche_snapshot"])

    # Migration: wuensche.json hatte `zaehler`-Schlüssel (Alt-Format vor #653).
    # → Zähler nach zaehler.json heben, wenn dort noch nichts steht. Alt-File
    #   wird beim nächsten Schreiben ohne `zaehler` zurückgeschrieben.
    if "zaehler" in daten:
        alt_zaehler = daten["zaehler"] or {"kind": 0, "eltern": 0}
        # Nur migrieren, wenn zaehler.json fehlt/leer ist.
        existierender = store_mod.lade_zaehler(p["zaehler_file"], snapshot=None)
        if existierender == {"kind": 0, "eltern": 0}:
            zu_schreiben = {
                "kind":   int(alt_zaehler.get("kind",   0) or 0),
                "eltern": int(alt_zaehler.get("eltern", 0) or 0),
            }
            try:
                store_mod.speichere_zaehler(p["zaehler_file"], zu_schreiben)
                runtime["zaehler_snapshot"] = zu_schreiben
                logger.info(
                    "Migration: zaehler aus wuensche.json nach zaehler.json gehoben (%s)",
                    zu_schreiben,
                )
            except OSError as e:
                logger.warning("Migration zaehler.json schreiben fehlgeschlagen: %s", e)
        # `zaehler` aus dem return-Dict entfernen — er gehört nicht
        # zur klasse=wunsch-Sicht.
        daten = {"wuensche": daten.get("wuensche", [])}

    runtime["wuensche_snapshot"] = daten
    return daten


def _lade_einkauf_frisch():
    """Reload-on-Read: klasse=einkauf-File frisch von Disk (ESSEN-20, ESSEN-7)."""
    p = _paths()
    daten = store_mod.lade_einkaufsliste(
        p["einkaufsliste_file"], runtime["einkauf_snapshot"])
    runtime["einkauf_snapshot"] = daten
    return daten


def _lade_zaehler_frisch():
    """Reload-on-Read: globaler Quellen-Zähler (ESSEN-5/ESSEN-7).

    Wenn die Datei fehlt UND noch nichts im Snapshot ist, leiten wir die
    Stände aus dem Max der IDs in beiden Klasse-Files ab (Crash-Recovery,
    ESSEN-5).
    """
    p = _paths()
    daten = store_mod.lade_zaehler(
        p["zaehler_file"], runtime["zaehler_snapshot"])
    # Crash-Recovery: bei {0,0} und vorhandenen Einträgen leiten wir ab.
    if daten == {"kind": 0, "eltern": 0}:
        abgeleitet = _zaehler_aus_max_ids()
        if abgeleitet != {"kind": 0, "eltern": 0}:
            logger.info(
                "Zähler aus Max-IDs abgeleitet (Crash-Recovery): %s", abgeleitet)
            daten = abgeleitet
    runtime["zaehler_snapshot"] = daten
    return daten


def _zaehler_aus_max_ids():
    """Leitet `{kind, eltern}`-Stand aus den Max-IDs in beiden Klasse-Files ab.

    Format der IDs: `<quelle>:<n>` (ESSEN-5).
    """
    stand = {"kind": 0, "eltern": 0}
    for daten in (_lade_wuensche_aus_file_only(), _lade_einkauf_aus_file_only()):
        for w in daten.get("wuensche", []):
            w_id = str(w.get("id", ""))
            if ":" in w_id:
                quelle, _, n = w_id.partition(":")
                try:
                    n_int = int(n)
                except ValueError:
                    continue
                if quelle in stand and n_int > stand[quelle]:
                    stand[quelle] = n_int
    return stand


def _lade_wuensche_aus_file_only():
    """Wie _lade_wuensche_frisch, aber ohne Migrations-Hook + ohne snapshot-Schreiben.
    (Nur Helfer für _zaehler_aus_max_ids.)"""
    p = _paths()
    daten = store_mod.lade_wuensche(p["wuensche_file"], snapshot=None)
    if "zaehler" in daten:
        daten = {"wuensche": daten.get("wuensche", [])}
    return daten


def _lade_einkauf_aus_file_only():
    p = _paths()
    return store_mod.lade_einkaufsliste(p["einkaufsliste_file"], snapshot=None)


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


def _lade_klasse_frisch(klasse):
    """Lädt das File einer einzelnen klasse (ESSEN-7)."""
    if klasse == "wunsch":
        return _lade_wuensche_frisch()
    if klasse == "einkauf":
        return _lade_einkauf_frisch()
    raise ValueError("unbekannte klasse: %r" % klasse)


def _finde_eintrag_in_beiden(wunsch_id):
    """Sucht einen Eintrag per ID in beiden Klasse-Files (ESSEN-7).

    Liefert ein Tupel `(klasse, eintrag)` oder `(None, None)` wenn unbekannt.
    IDs sind global eindeutig (ESSEN-5), daher Treffer in genau einem File.
    """
    daten_w = _lade_wuensche_frisch()
    for w in daten_w.get("wuensche", []):
        if w.get("id") == wunsch_id:
            return ("wunsch", w)
    daten_e = _lade_einkauf_frisch()
    for w in daten_e.get("wuensche", []):
        if w.get("id") == wunsch_id:
            return ("einkauf", w)
    return (None, None)


# ── Validierungshelfer ────────────────────────────────────────────────────

GUELTIGE_QUELLE    = {"kind", "eltern"}
GUELTIGE_KATEGORIE = {"gericht", "obst_gemuese", "brotbelag", "sonstiges"}
GUELTIGE_KLASSE    = {"wunsch", "einkauf"}   # ESSEN-4/ESSEN-7

DEFAULT_ABHAKER = "eltern"   # ESSEN-32: Auth-Default für abgehakt_von


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


def _parse_bool_query(wert):
    """Parsed `true`/`false`-Query-Strings nach bool. None bei unbekanntem Wert."""
    if wert is None:
        return None
    w = str(wert).strip().lower()
    if w == "true":
        return True
    if w == "false":
        return False
    return "INVALID"   # Sentinel: Filter-Wert war angegeben, aber ungültig.


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

    V1 #653 (ESSEN-8): Display rendert ausschließlich `klasse=wunsch` —
    explizit nur aus wuensche.json (Doppel-Robustheit).
    """
    aktiv_tab = request.args.get("tab", render_mod.DEFAULT_TAB)

    kategorien = _lade_alle_kategorien()
    wuensche_daten = _lade_wuensche_frisch()   # ESSEN-8: nur klasse=wunsch.

    view = render_mod.baue_view(
        kategorien,
        wuensche_daten.get("wuensche", []),
        aktiv_tab=aktiv_tab,
    )
    return render_template("wunsch.html", view=view)


# ── API: Wünsche (ESSEN-15..17, ESSEN-32) ────────────────────────────────

@app.route("/api/v1/essen/wuensche", methods=["GET"])
def wuensche_lesen():
    """GET /api/v1/essen/wuensche — Liste lesen (ESSEN-15).

    Antwort: { "wuensche": [...] }, chronologisch (erstellt_am aufsteigend).
    Leer = 200, nicht 404 (ESSEN-15).

    Query-Filter (V1 #653, ESSEN-15):
      ?klasse=wunsch|einkauf  — liest nur das passende File (ESSEN-7).
      ?abgehakt=true|false    — UND-Filter nach dem Lesen.
    Mehrere Filter sind UND-verknüpft. Unbekannter Filter-Wert → 400.
    """
    klasse_filter = request.args.get("klasse")
    abgehakt_filter_raw = request.args.get("abgehakt")

    # Validierung Filter-Werte.
    if klasse_filter is not None and klasse_filter not in GUELTIGE_KLASSE:
        return jsonify({"fehler": "klasse muss 'wunsch' oder 'einkauf' sein"}), 400

    abgehakt_filter = _parse_bool_query(abgehakt_filter_raw)
    if abgehakt_filter == "INVALID":
        return jsonify({"fehler": "abgehakt muss 'true' oder 'false' sein"}), 400

    # File-Routing (ESSEN-15): klasse-Filter wählt das File — kein Filter
    # heißt beide Files mergen.
    wuensche = []
    if klasse_filter == "wunsch":
        wuensche.extend(_lade_wuensche_frisch().get("wuensche", []))
    elif klasse_filter == "einkauf":
        wuensche.extend(_lade_einkauf_frisch().get("wuensche", []))
    else:
        wuensche.extend(_lade_wuensche_frisch().get("wuensche", []))
        wuensche.extend(_lade_einkauf_frisch().get("wuensche", []))

    # abgehakt-Filter (UND-verknüpft, ESSEN-15).
    if abgehakt_filter is True:
        wuensche = [w for w in wuensche if w.get("abgehakt") is True]
    elif abgehakt_filter is False:
        wuensche = [w for w in wuensche if not w.get("abgehakt")]

    # Chronologische Reihenfolge (ESSEN-15).
    wuensche_sortiert = sorted(
        wuensche,
        key=lambda w: w.get("erstellt_am", ""),
    )
    return jsonify({"wuensche": wuensche_sortiert}), 200


@app.route("/api/v1/essen/wuensche", methods=["POST"])
def wunsch_hinzufuegen():
    """POST /api/v1/essen/wuensche — Wunsch/Einkauf hinzufügen (ESSEN-16).

    Payload: { label, bild_ref, quelle, kategorie, item_id,
               klasse?, aus_gericht? }
    Antwort: { "id": "<quelle>:<n>" }

    V1 #653 (ESSEN-16):
    - `klasse` default `wunsch` (rückwärtskompatibel).
    - `aus_gericht` NUR bei `klasse='einkauf'`.
    - Routing nach klasse zum richtigen File (ESSEN-7).
    - Duplikat-Regel ist (item_id, klasse)-Tupel orthogonal.
    - Listen-Grenze (ESSEN-29) je File geprüft.
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"fehler": "Kein JSON-Body"}), 400

    label       = body.get("label", "")
    bild_ref    = body.get("bild_ref", "")
    quelle      = body.get("quelle", "")
    kategorie   = body.get("kategorie", "")
    item_id     = body.get("item_id", "")
    klasse      = body.get("klasse", "wunsch")   # ESSEN-4: Default wunsch.
    aus_gericht = body.get("aus_gericht")        # optional, nur klasse=einkauf.

    # Fachliche Validierung im Buddy (ESSEN-16, BUD-2).
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
    if klasse not in GUELTIGE_KLASSE:
        fehler.append("klasse muss 'wunsch' oder 'einkauf' sein")
    # aus_gericht nur bei klasse=einkauf zulässig (ESSEN-16/ESSEN-4).
    if aus_gericht is not None and aus_gericht != "" and klasse != "einkauf":
        fehler.append("aus_gericht ist nur bei klasse='einkauf' zulässig")
    if fehler:
        return jsonify({"fehler": fehler}), 400

    # item_id muss im Katalog existieren (ESSEN-16, ESSEN-13/14).
    alle_kategorien = _lade_alle_kategorien()
    alle_item_ids = {
        item["id"]
        for items in alle_kategorien.values()
        for item in items
    }
    if str(item_id).strip() not in alle_item_ids:
        return jsonify({"fehler": "item_id unbekannt — nicht im Lebensmittel- oder Gerichte-Katalog"}), 400

    p = _paths()
    item_id_str = str(item_id).strip()

    # Ziel-File je klasse laden (ESSEN-7).
    if klasse == "wunsch":
        daten = _lade_wuensche_frisch()
        ziel_file = p["wuensche_file"]
        speichere_fn = store_mod.speichere_wuensche
        snapshot_key = "wuensche_snapshot"
        grenze = runtime["listen_grenze_wunsch"]
    else:
        daten = _lade_einkauf_frisch()
        ziel_file = p["einkaufsliste_file"]
        speichere_fn = store_mod.speichere_einkaufsliste
        snapshot_key = "einkauf_snapshot"
        grenze = runtime["listen_grenze_einkauf"]

    # Duplikat-Schutz (ESSEN-16): (item_id, klasse)-Tupel UND nicht abgehakt.
    # Klassen orthogonal — derselbe item_id darf einmal je klasse offen sein.
    for w in daten.get("wuensche", []):
        if w.get("item_id") == item_id_str and not w.get("abgehakt"):
            return jsonify({
                "fehler":   "item_already_on_list",
                "item_id":  item_id_str,
                "klasse":   klasse,
            }), 409

    # Listen-Grenze (ESSEN-29): offene Einträge je File ≤ Grenze. Vor jedem
    # POST geprüft — wir würden mit `+1` über die Grenze springen → 413.
    offen_jetzt = sum(1 for w in daten.get("wuensche", []) if not w.get("abgehakt"))
    if offen_jetzt + 1 > grenze:
        return jsonify({
            "error":       "listen_grenze",
            "offen_jetzt": offen_jetzt,
            "grenze":      grenze,
        }), 413

    # Quellen-Zähler holen (klasse-übergreifend, ESSEN-5/ESSEN-7).
    zaehler = _lade_zaehler_frisch()
    n = int(zaehler.get(quelle, 0) or 0) + 1
    neue_id = "%s:%d" % (quelle, n)
    zaehler_neu = dict(zaehler)
    zaehler_neu[quelle] = n

    neuer_eintrag = {
        "id":          neue_id,
        "label":       str(label).strip(),
        "bild_ref":    str(bild_ref),
        "quelle":      quelle,
        "kategorie":   kategorie,
        "item_id":     item_id_str,
        "klasse":      klasse,                # ESSEN-4
        "abgehakt":    False,                 # ESSEN-4: initial false
        "erstellt_am": _jetzt(),
    }
    if klasse == "einkauf" and aus_gericht:
        neuer_eintrag["aus_gericht"] = str(aus_gericht).strip()

    # Atomar schreiben (DCOMP-4, ESSEN-20). Reihenfolge: erst Zähler heben,
    # dann das klasse-File. Wenn das klasse-File-Schreiben scheitert, ist der
    # Zähler bereits gehoben — das ist OK, denn IDs müssen monoton wachsen,
    # auch wenn ein Schreiben fehlschlägt (vermeidet ID-Re-Vergabe nach Crash).
    store_mod.speichere_zaehler(p["zaehler_file"], zaehler_neu)
    runtime["zaehler_snapshot"] = zaehler_neu

    wuensche = list(daten.get("wuensche", []))
    wuensche.append(neuer_eintrag)
    neu_daten = {"wuensche": wuensche}
    speichere_fn(ziel_file, neu_daten)
    runtime[snapshot_key] = neu_daten

    logger.info(
        "POST id=%s klasse=%s item_id=%s label=%r quelle=%s kategorie=%s",
        neue_id, klasse, item_id_str, label, quelle, kategorie,
    )
    return jsonify({"id": neue_id}), 201


@app.route("/api/v1/essen/wuensche/<wunsch_id>", methods=["PATCH"])
def wunsch_patchen(wunsch_id):
    """PATCH /api/v1/essen/wuensche/<id> — sparse update (ESSEN-32).

    Payload (alle Felder optional):
      `abgehakt` (bool) — true setzt automatisch abgehakt_von + abgehakt_am,
                          false leert beide.
      `aus_gericht` (string) — nur bei klasse=einkauf, sonst 400.

    Klassen-Felder (klasse/quelle/label/kategorie/item_id/bild_ref) sind
    NICHT änderbar. Unbekannte Felder werden ignoriert (Vorwärtskompat).
    PATCH auf unbekannte ID → 404.

    Antwort: 200 mit dem aktualisierten Eintrag (volle Form wie GET-Element).
    """
    body = request.get_json(silent=True)
    if body is None:
        body = {}

    klasse, eintrag = _finde_eintrag_in_beiden(wunsch_id)
    if eintrag is None:
        return jsonify({"fehler": "unbekannte id", "id": wunsch_id}), 404

    # Sparse update vorbereiten.
    aktualisiert = dict(eintrag)
    changes_made = False

    # ── abgehakt ──────────────────────────────────────────────────────────
    if "abgehakt" in body:
        wert = body["abgehakt"]
        if not isinstance(wert, bool):
            return jsonify({"fehler": "abgehakt muss bool sein"}), 400
        aktualisiert["abgehakt"] = wert
        if wert:
            # ESSEN-32: abgehakt=true setzt abgehakt_von + abgehakt_am.
            # Default-Eltern, weil V1 keine Auth-Identität durchreicht
            # (Mini-App-Auth wird über Telegram initData in einem späteren
            # Track gepflegt).
            aktualisiert["abgehakt_von"] = (
                body.get("abgehakt_von") or DEFAULT_ABHAKER
            )
            aktualisiert["abgehakt_am"] = _jetzt()
        else:
            # ESSEN-32: abgehakt=false leert von + am.
            aktualisiert.pop("abgehakt_von", None)
            aktualisiert.pop("abgehakt_am",  None)
        changes_made = True

    # ── aus_gericht ──────────────────────────────────────────────────────
    if "aus_gericht" in body:
        if klasse != "einkauf":
            return jsonify({
                "fehler": "aus_gericht ist nur bei klasse='einkauf' zulässig"
            }), 400
        wert = body["aus_gericht"]
        if wert is None or wert == "":
            aktualisiert.pop("aus_gericht", None)
        else:
            aktualisiert["aus_gericht"] = str(wert).strip()
        changes_made = True

    # Unbekannte/klassen-feste Felder werden ignoriert (ESSEN-32: Vorwärtskompat).
    # (Keine 400 für unbekannte Felder — Spec verlangt Ignorieren.)

    # Schreiben (nur wenn tatsächlich etwas geändert wurde; idempotent OK).
    p = _paths()
    if klasse == "wunsch":
        daten = _lade_wuensche_frisch()
        ziel_file = p["wuensche_file"]
        speichere_fn = store_mod.speichere_wuensche
        snapshot_key = "wuensche_snapshot"
    else:
        daten = _lade_einkauf_frisch()
        ziel_file = p["einkaufsliste_file"]
        speichere_fn = store_mod.speichere_einkaufsliste
        snapshot_key = "einkauf_snapshot"

    if changes_made:
        wuensche_neu = []
        for w in daten.get("wuensche", []):
            if w.get("id") == wunsch_id:
                wuensche_neu.append(aktualisiert)
            else:
                wuensche_neu.append(w)
        neu_daten = {"wuensche": wuensche_neu}
        speichere_fn(ziel_file, neu_daten)
        runtime[snapshot_key] = neu_daten

    logger.info(
        "PATCH id=%s klasse=%s changes=%s", wunsch_id, klasse, sorted(body.keys()),
    )
    return jsonify(aktualisiert), 200


@app.route("/api/v1/essen/wuensche/<wunsch_id>", methods=["DELETE"])
def wunsch_loeschen(wunsch_id):
    """DELETE /api/v1/essen/wuensche/<id> — Wunsch/Einkauf entfernen (ESSEN-17).

    Idempotent: zweites DELETE auf dieselbe ID → 200 (ESSEN-17).
    V1 #653: sucht in beiden Klasse-Files (ESSEN-7).
    """
    p = _paths()

    # Klasse=wunsch
    daten_w = _lade_wuensche_frisch()
    wuensche_w_neu = [w for w in daten_w.get("wuensche", []) if w.get("id") != wunsch_id]
    if len(wuensche_w_neu) != len(daten_w.get("wuensche", [])):
        neu = {"wuensche": wuensche_w_neu}
        store_mod.speichere_wuensche(p["wuensche_file"], neu)
        runtime["wuensche_snapshot"] = neu

    # Klasse=einkauf
    daten_e = _lade_einkauf_frisch()
    wuensche_e_neu = [w for w in daten_e.get("wuensche", []) if w.get("id") != wunsch_id]
    if len(wuensche_e_neu) != len(daten_e.get("wuensche", [])):
        neu = {"wuensche": wuensche_e_neu}
        store_mod.speichere_einkaufsliste(p["einkaufsliste_file"], neu)
        runtime["einkauf_snapshot"] = neu

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

# Runtime-Konfig-Schema (CONFIG-1):
#  - Service-Start-Werte (Bind/Port/Log-Level).
#  - V1 #653 (ESSEN-29): Listen-Grenzen je klasse, plus Übergangs-Schlüssel.
RUNTIME_SCHEMA = {
    "listen_host":           "127.0.0.1",
    "listen_port":           5052,
    "log_level":             "INFO",
    "listen_grenze":         100,    # Übergangs-Schlüssel (ESSEN-29)
    "listen_grenze_wunsch":  100,    # ESSEN-29
    "listen_grenze_einkauf": 100,    # ESSEN-29
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
    configure(
        paths,
        listen_grenze=rt.get("listen_grenze"),
        listen_grenze_wunsch=rt.get("listen_grenze_wunsch"),
        listen_grenze_einkauf=rt.get("listen_grenze_einkauf"),
    )

    logger.info(
        "Essens-Buddy hört auf %s:%s (ESSEN-23, PORT-2)",
        rt["listen_host"], rt["listen_port"],
    )
    app.run(host=rt["listen_host"], port=rt["listen_port"],
            debug=False, threaded=True)


if __name__ == "__main__":
    main()
