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
  PATCH  /api/v1/essen/katalog/gerichte/<id> — Gericht-Bild ändern (ESSEN-19a)
  POST   /api/v1/essen/fotos              — Foto ingest, multipart `medium` (ESSEN-22 V1.2)
  GET    /api/v1/essen/fotos/<id>         — Vollbild JPEG (ESSEN-22 V1.2)
  GET    /api/v1/essen/fotos/<id>/thumbnail — Thumbnail JPEG (ESSEN-22 V1.2)
  DELETE /api/v1/essen/fotos/<id>         — Löschen atomar (ESSEN-22 V1.2)
"""

import argparse
import logging
import os
import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, make_response, render_template, request, send_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# MAD-7 / T1015: Init-Data-Auth aus tools.initdata (vorher per sys.path-Hack
# aus eltern-chat/init_data.py — MOD-6 / Cluster-A-Option-B 2026-06-18-1720).
import tools.medien_store as medien_store  # noqa: E402
from tools import configloader, logsetup  # noqa: E402
from tools import familie_client as _familie_client_mod  # noqa: E402
from tools.familie_client import DEFAULT_ORIGIN as _FAMILIE_DEFAULT_ORIGIN  # noqa: E402
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.initdata.auth_gate import make_require_init_data  # noqa: E402
from tools.service_diagnostics import register_version  # noqa: E402

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
    # MAD-7 / T708-C: Mini-App-Auth (Test-Naht; im Produktiv-Betrieb aus ENV).
    "bot_token":         None,
    "init_data_config":  None,
    # T1015 / Cluster-A-Option-B: FAM-Lookup geht via tools.familie_client
    # gegen Familie-Service-HTTP-API (DCOMP-1 / FAM-7) statt familie.json
    # direkt zu lesen. familie_client darf eine FamilieClient-Instanz oder
    # ein Test-Doppel mit get_telegram_ids()-Methode sein.
    "familie_client":    None,
}

# Schreib-Serialisierung für Foto-Ingest (ESSEN-22 V1.2): Read-Modify-Write
# des fotos-Index aus parallelen Flask-Threads würde ohne Lock verloren-gehende
# Updates produzieren (Muster photo/main.py _write_lock). Das Lock klammert
# nur den Schreib-Pfad (Ingest/Delete) — Lesen bleibt lock-frei.
_foto_write_lock = threading.Lock()


def configure(paths, zeitzone="Europe/Berlin", listen_grenze=None,
              listen_grenze_wunsch=None, listen_grenze_einkauf=None,
              bot_token=None, init_data_config=None, familie_client=None):
    """Setzt die Datei-Pfade, Zeitzone und Listen-Grenzen (Test-Naht).

    `paths` ist ein dict aus config_mod.data_paths().
    Listen-Grenzen (ESSEN-29): `listen_grenze_wunsch` / `listen_grenze_einkauf`
    überschreiben den Default 100; `listen_grenze` (Übergangs-Schlüssel) greift
    für beide, wenn spezifische Werte fehlen.
    `bot_token`, `init_data_config` (MAD-7 / T708-C): Auth-Naht für Tests;
    im Produktiv-Betrieb aus ENV.
    `familie_client` (T1015): Test-Doppel mit `get_telegram_ids()`-Methode
    oder eine ``tools.familie_client.FamilieClient``-Instanz. None → ein
    frischer FamilieClient aus ENV ``ESSEN_FAMILIE_ORIGIN`` wird gebaut.
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

    # MAD-7 Auth-Naht (Test-Modus)
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if init_data_config is not None:
        runtime["init_data_config"] = init_data_config
    # T1015: familie_client Test-Naht (None bedeutet „aus ENV bauen", siehe
    # _get_familie_client). Test-Doppel überschreibt explizit.
    if familie_client is not None:
        runtime["familie_client"] = familie_client


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
    for gericht in gerichte_daten.get("gerichte", []):
        item = {
            "id":        str(gericht.get("id", "")),
            "label":     gericht.get("label", ""),
            "kategorie": "gericht",
        }
        # ESSEN-22: Gericht trägt entweder bild_ref ODER foto_ref (ESSEN-19/19a).
        if "foto_ref" in gericht:
            item["foto_ref"] = gericht["foto_ref"]
        else:
            item["bild_ref"] = gericht.get("bild_ref", "")
        gerichte_items.append(item)
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


def _foto_ref_existiert(foto_ref):
    """Prüft, ob foto_ref im Essen-Buddy-Foto-Index existiert (ESSEN-19/19a, V1.2).

    Lookup gegen `tools.medien_store.load(cfg.fotos_verzeichnis)`. Nach Welle 2
    (T808/#804) liegen Essens-Fotos im Essen-Buddy selbst — kein Cross-Buddy-
    Call mehr. Test-Naht: `medien_store.load` im Modul-Namespace per monkeypatch
    ersetzbar.
    Bei Fehler (Verzeichnis fehlt o. ä.) → False (kein Exception-Durchbruch).
    """
    paths = _paths()
    verzeichnis = paths.get("fotos_verzeichnis")
    if not verzeichnis:
        return False
    try:
        medien = medien_store.load(verzeichnis)
    except Exception:
        return False
    return any(m.id == foto_ref for m in medien)


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
#  MAD-7 Mini-App-Auth (T708-C)
# ============================================================

# ENV-Variable für Bot-Token (APP-7 / MAD-9): gesetzt via systemd EnvironmentFile
# aus eltern-chat/.env (Token-Sharing #684).
_ENV_BOT_TOKEN = "ELTERNCHAT_BOT_TOKEN"
# T1015: Familie-Service-Origin per Komponenten-ENV (CONFIG-5-Schema).
# Default kommt aus tools.familie_client.DEFAULT_ORIGIN (zentral, CLIENT-1).
_ENV_FAMILIE_ORIGIN = "ESSEN_FAMILIE_ORIGIN"


def _get_bot_token():
    """Bot-Token aus runtime-Dict (Test-Naht) oder ENV (APP-7)."""
    return runtime.get("bot_token") or os.environ.get(_ENV_BOT_TOKEN)


def _get_familie_client():
    """Liefert einen FamilieClient — gecacht im runtime-Dict oder frisch (T1015).

    Test-Naht: ``configure(familie_client=...)`` setzt direkt einen Stub.
    Produktiv-Pfad: ``FamilieClient`` aus ENV ``ESSEN_FAMILIE_ORIGIN`` (Default
    ``http://127.0.0.1:5010``). Replaced den früheren direkten familie.json-
    Read (DCOMP-1 / FAM-7-Heilung, Cluster-A-Option-B).
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
# Essen-API-Routen tragen keine display_id im Pfad → neutraler Geräte-Hinweis
# (auth.md AUTH-8: „sonst neutraler Hinweis"). V1 reine Text-Anweisung; der
# `tg://`-Deep-Link ist V2 (auth.md AUTH-8).
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


# Decorator: HART-AUTH (T948, auth.md AUTH-2/3/5/8). Der hand-kopierte
# Wrapper-Body ist mit #1626 auf die AUTH-Decorator-Lib-Factory geflippt
# (tools/initdata/auth_gate.py::make_require_init_data, #1625). Der Name
# `require_init_data` BLEIBT (AUTH-9-Copetrage-Test trägt per AST-Namen); die
# Buddy-eigenen Getter + `_auth_401` gehen WÖRTLICH als Closures rein — die
# Factory ruft genau diesen `_auth_401`, 401/403/500-Shape bleibt byte-gleich.
# Routes, die Eltern-only-Verhalten brauchen, prüfen explizit g.init_data.
require_init_data = make_require_init_data(
    get_bot_token=_get_bot_token,
    get_familie_client=_get_familie_client,
    get_init_data_config=_get_init_data_config,
    auth_401=_auth_401,
)


# ============================================================
#  Flask-App
# ============================================================

# URL-13: statische Assets im Display-Namensraum des Essens-Buddys.
app = Flask(__name__, static_url_path="/display/essen/static")


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


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
        foto_overrides_pfad=_paths()["foto_overrides_file"],
    )
    return render_template("wunsch.html", view=view)


# ── API: Wünsche (ESSEN-15..17, ESSEN-32) ────────────────────────────────

@app.route("/api/v1/essen/wuensche", methods=["GET"])
@require_init_data
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
@require_init_data
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
    foto_ref    = body.get("foto_ref", "")    # ESSEN-22 #922: Foto-Gerichte-Alternative
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
    # ESSEN-22 (#922): bild_ref ODER foto_ref Pflicht (mind. einer). Foto-Gerichte
    # tragen foto_ref aus dem Katalog statt einer numerischen ARASAAC-ID.
    if not bild_ref and not foto_ref:
        fehler.append("bild_ref oder foto_ref muss gesetzt sein")
    elif bild_ref and not _valide_bild_ref(bild_ref):
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
    # Ausnahme: frei:-Präfix ist ohne Katalog-Match zulässig (ESSEN-16-Ausnahme,
    # EIN-4/ESSEN-31 — freie Eingabe-Pfad aus Mini-App und Quick-Add).
    item_id_raw = str(item_id).strip()
    if not item_id_raw.lower().startswith("frei:"):
        alle_kategorien = _lade_alle_kategorien()
        alle_item_ids = {
            item["id"]
            for items in alle_kategorien.values()
            for item in items
        }
        if item_id_raw not in alle_item_ids:
            return jsonify({"fehler": "item_id unbekannt — nicht im Lebensmittel- oder Gerichte-Katalog"}), 400

    p = _paths()
    item_id_str = item_id_raw

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
        # ESSEN-22 (#922): Foto-Gerichte tragen foto_ref statt bild_ref.
        # Reader-Logik (ESSEN-22 in render.py) konsumiert beides; persistieren
        # was gesetzt ist.
        "bild_ref":    str(bild_ref) if bild_ref else "",
        "foto_ref":    str(foto_ref) if foto_ref else "",
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
@require_init_data
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
@require_init_data
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
@require_init_data
def katalog_lesen():
    """GET /api/v1/essen/katalog — Katalog lesen (ESSEN-18).

    Antwort: { "kategorien": { gericht, obst_gemuese, brotbelag, sonstiges } }
    Gerichte-Kategorie leer bis erste GAN-Eintragung (ESSEN-14).
    """
    kategorien = _lade_alle_kategorien()
    return jsonify({"kategorien": kategorien}), 200


@app.route("/api/v1/essen/katalog/gerichte", methods=["POST"])
@require_init_data
def gericht_anlegen():
    """POST /api/v1/essen/katalog/gerichte — Gericht anlegen (ESSEN-19).

    Payload: { label, bild_ref | foto_ref }  (kategorie ist implizit 'gericht')
    Genau eines von bild_ref / foto_ref ist Pflicht. Beide → 400, keines → 400.
    Bei foto_ref: Photo-Buddy-Validierung (GET /api/v1/photo/medien/<id>, ESSEN-22).
    Antwort: { "id": "<n>" }
    Duplikates label → 409 (ESSEN-19).
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"fehler": "Kein JSON-Body"}), 400

    label    = body.get("label", "")
    bild_ref = body.get("bild_ref")
    foto_ref = body.get("foto_ref")

    fehler = []
    if not label or not str(label).strip():
        fehler.append("label darf nicht leer sein")

    # ESSEN-19: genau eines von bild_ref / foto_ref ist Pflicht.
    hat_bild_ref = bild_ref is not None and str(bild_ref).strip() != ""
    hat_foto_ref = foto_ref is not None and str(foto_ref).strip() != ""
    if hat_bild_ref and hat_foto_ref:
        fehler.append("bild_ref und foto_ref schließen sich gegenseitig aus — genau eines angeben")
    elif not hat_bild_ref and not hat_foto_ref:
        fehler.append("eines von bild_ref (ARASAAC-ID) oder foto_ref (Photo-Buddy-Medien-ID) ist Pflicht")
    elif hat_bild_ref and not _valide_bild_ref(bild_ref):
        fehler.append("bild_ref muss eine numerische ARASAAC-ID sein")

    if fehler:
        return jsonify({"fehler": fehler}), 400

    # Photo-Buddy-Validierung (ESSEN-19, ESSEN-22): foto_ref muss existieren.
    if hat_foto_ref and not _foto_ref_existiert(str(foto_ref).strip()):
        return jsonify({"fehler": "foto_ref: Medien-ID im Photo-Buddy nicht gefunden"}), 400

    p = _paths()
    daten = store_mod.lade_gerichte(p["gerichte_file"], runtime["gerichte_snapshot"])
    gerichte = daten.get("gerichte", [])

    # Duplikat-Check (ESSEN-19: gleiches label → 409).
    label_norm = str(label).strip().lower()
    for gericht in gerichte:
        if gericht.get("label", "").strip().lower() == label_norm:
            return jsonify({"fehler": "Gericht mit diesem Label existiert bereits"}), 409

    zaehler = daten.get("zaehler", 0) + 1
    neue_id = str(zaehler)
    neues_gericht = {
        "id":        neue_id,
        "label":     str(label).strip(),
        "kategorie": "gericht",
    }
    # ESSEN-22: entweder bild_ref ODER foto_ref — nie beides im Eintrag.
    if hat_foto_ref:
        neues_gericht["foto_ref"] = str(foto_ref).strip()
    else:
        neues_gericht["bild_ref"] = str(bild_ref)

    gerichte = list(gerichte)
    gerichte.append(neues_gericht)
    neu_daten = {"gerichte": gerichte, "zaehler": zaehler}
    store_mod.speichere_gerichte(p["gerichte_file"], neu_daten)
    runtime["gerichte_snapshot"] = neu_daten

    logger.info("Gericht angelegt id=%s label=%r foto_ref=%s bild_ref=%s",
                neue_id, label, foto_ref, bild_ref)
    return jsonify({"id": neue_id}), 201


@app.route("/api/v1/essen/katalog/gerichte/<gericht_id>", methods=["DELETE"])
@require_init_data
def gericht_loeschen(gericht_id):
    """DELETE /api/v1/essen/katalog/gerichte/<id> — Gericht löschen (ESSEN-19b).

    Reihenfolge (ESSEN-19b "Katalog ist Wahrheit, Foto-Waise toleriert"):
    1. Gericht-Eintrag aus gerichte.json atomar (DCOMP-4) entfernen.
    2. Foto-Kaskade (best-effort): trägt das Gericht ein `foto_ref`, wird das
       Familien-Foto aus dem Foto-Verzeichnis synchron entfernt. Scheitert
       der Foto-Lösch, bleibt ein Foto-Waise — der Gericht-Lösch bleibt
       wirksam (Watchdog-Folge zu PR #1068: mildere Asymmetrie, Katalog ist
       Wahrheit; Re-Run via aufräum-Skript möglich).
    3. `bild_ref`-Gerichte haben keine Foto-Kaskade.

    Antwort: 204 bei Erfolg (inkl. Foto-Waise-Fall). 404 bei unbekannter ID.
    Idempotenz: zweites DELETE auf gelöschte ID → 404 (ESSEN-19b-Spec).
    """
    p = _paths()
    daten = store_mod.lade_gerichte(p["gerichte_file"], runtime["gerichte_snapshot"])
    gerichte = daten.get("gerichte", [])

    # Gericht suchen — 404 bei unbekannter ID (ESSEN-19b).
    ziel = next((g for g in gerichte if str(g.get("id", "")) == gericht_id), None)
    if ziel is None:
        return jsonify({"fehler": "Gericht nicht gefunden", "id": gericht_id}), 404

    foto_ref = ziel.get("foto_ref")

    # 1) Gericht aus Liste entfernen und atomar schreiben (DCOMP-4) — VOR Foto-Lösch.
    #    Katalog ist Wahrheit (ESSEN-19b). Scheitert dieser Schritt, bleibt das
    #    Gericht im Katalog (kein Halb-Zustand, kein verwaistes Foto).
    gerichte_neu = [g for g in gerichte if str(g.get("id", "")) != gericht_id]
    neu_daten = {"gerichte": gerichte_neu, "zaehler": daten.get("zaehler", 0)}
    store_mod.speichere_gerichte(p["gerichte_file"], neu_daten)
    runtime["gerichte_snapshot"] = neu_daten

    # 2) Foto-Kaskade (best-effort): bei Fehler Foto-Waise tolerieren.
    #    Watchdog-Folge zu PR #1068: Reihenfolge tauschen, Katalog-Lösch zuerst.
    if foto_ref:
        fotos_verz = p.get("fotos_verzeichnis")
        if fotos_verz:
            with _foto_write_lock:
                try:
                    entfernt = medien_store.delete(fotos_verz, str(foto_ref))
                except medien_store.StoreError as e:
                    # Foto-Waise: Gericht ist weg, Foto-Datei bleibt liegen.
                    # Spec ESSEN-19b toleriert das (Katalog ist Wahrheit).
                    logger.warning(
                        "gericht_loeschen: Foto-Lösch fehlgeschlagen — Foto-Waise "
                        "id=%s foto_ref=%s: %s", gericht_id, foto_ref, e)
                else:
                    if not entfernt:
                        logger.warning(
                            "gericht_loeschen: foto_ref=%s nicht im Foto-Index "
                            "(Gericht id=%s ist trotzdem gelöscht)",
                            foto_ref, gericht_id)

    logger.info("DELETE Gericht id=%s label=%r foto_ref=%s",
                gericht_id, ziel.get("label"), foto_ref)
    return ("", 204)


@app.route("/api/v1/essen/katalog/gerichte/<gericht_id>", methods=["PATCH"])
@require_init_data
def gericht_bild_patchen(gericht_id):
    """PATCH /api/v1/essen/katalog/gerichte/<id> — Gericht-Bild ändern (ESSEN-19a).

    Payload (sparse update analog ESSEN-32, alle Felder optional):
      foto_ref (string) — neues Familien-Foto (Photo-Buddy-Medien-ID).
      bild_ref (string) — zurück zum Pikto-Default (ARASAAC-ID).
    Genau eines (oder keines). Beide → 400. Unbekannte Felder → ignoriert.
    Antwort: 200 mit dem aktualisierten Gericht-Eintrag.
    404 bei unbekannter id (ESSEN-19a).
    """
    body = request.get_json(silent=True)
    if body is None:
        body = {}

    # ESSEN-19a: foto_ref + bild_ref gleichzeitig → 400.
    hat_bild_ref = "bild_ref" in body and body["bild_ref"] is not None and str(body["bild_ref"]).strip() != ""
    hat_foto_ref = "foto_ref" in body and body["foto_ref"] is not None and str(body["foto_ref"]).strip() != ""
    if hat_bild_ref and hat_foto_ref:
        return jsonify({"fehler": "bild_ref und foto_ref schließen sich gegenseitig aus — genau eines angeben"}), 400

    # Gericht suchen (ESSEN-19a: 404 bei unbekannter ID).
    p = _paths()
    daten = store_mod.lade_gerichte(p["gerichte_file"], runtime["gerichte_snapshot"])
    gerichte = daten.get("gerichte", [])
    ziel = next((g for g in gerichte if str(g.get("id", "")) == gericht_id), None)
    if ziel is None:
        return jsonify({"fehler": "Gericht nicht gefunden", "id": gericht_id}), 404

    # Validierungen.
    if hat_bild_ref and not _valide_bild_ref(body["bild_ref"]):
        return jsonify({"fehler": "bild_ref muss eine numerische ARASAAC-ID sein"}), 400
    if hat_foto_ref and not _foto_ref_existiert(str(body["foto_ref"]).strip()):
        return jsonify({"fehler": "foto_ref: Medien-ID im Photo-Buddy nicht gefunden"}), 400

    # Sparse update: nur Bild-Felder änderbar (ESSEN-19a).
    # Unbekannte/Label/Zutaten-Felder werden ignoriert (Vorwärtskompatibilität).
    aktualisiert = dict(ziel)
    if hat_foto_ref:
        aktualisiert["foto_ref"] = str(body["foto_ref"]).strip()
        aktualisiert.pop("bild_ref", None)   # ESSEN-19a: ersetzt bild_ref
    elif hat_bild_ref:
        aktualisiert["bild_ref"] = str(body["bild_ref"])
        aktualisiert.pop("foto_ref", None)   # ESSEN-19a: ersetzt foto_ref

    # Atomar schreiben (DCOMP-4, analog ESSEN-19).
    gerichte_neu = [aktualisiert if str(g.get("id", "")) == gericht_id else g for g in gerichte]
    neu_daten = {"gerichte": gerichte_neu, "zaehler": daten.get("zaehler", 0)}
    store_mod.speichere_gerichte(p["gerichte_file"], neu_daten)
    runtime["gerichte_snapshot"] = neu_daten

    logger.info("PATCH Gericht id=%s foto_ref=%s bild_ref=%s",
                gericht_id, body.get("foto_ref"), body.get("bild_ref"))
    return jsonify(aktualisiert), 200


# ── API: Fotos (ESSEN-22 V1.2) ──────────────────────────────────────────────
# Essen-Buddy besitzt seine eigenen Foto-Daten (MEDIEN-2, SVC-5).
# Mechanik über tools.medien_store (MEDIEN-1), kein Adapter-Layer nötig.


def _bad_request(msg, status=400):
    """4xx/503 mit JSON-Fehler, keine Stack-Traces vor dem Konsumenten."""
    return jsonify({"error": msg}), status


@app.route("/api/v1/essen/fotos", methods=["POST"])
@require_init_data
def post_foto():
    """ESSEN-22 V1.2: Foto aufnehmen. Multipart-Feld `medium`.

    Normalisiert (HEIC→JPEG, Thumbnail), schreibt atomar in das Essen-eigene
    Foto-Verzeichnis (MEDIEN-2, SVC-5). Antwort `{"id", "typ"}`.
    Leeres/fehlendes Feld → 400. Schreib-/Petrarbeitungsfehler → 503.
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

    fotos_verz = _paths()["fotos_verzeichnis"]
    with _foto_write_lock:
        try:
            medium = medien_store.ingest(fotos_verz, rohbytes, dateiname)
        except medien_store.NormalizeError as e:
            return _bad_request("Medium nicht petrarbeitbar: %s" % e)
        except medien_store.StoreError as e:
            logger.warning("post_foto: Schreiben fehlgeschlagen: %s", e)
            return _bad_request(str(e), status=503)
    return jsonify({"id": medium.id, "typ": medium.typ}), 200


@app.route("/api/v1/essen/fotos/<medium_id>", methods=["GET"])
@require_init_data
def get_foto(medium_id):
    """ESSEN-22 V1.2: Vollbild (JPEG) mit korrektem Content-Type (send_file)."""
    fotos_verz = _paths()["fotos_verzeichnis"]
    pfad = medien_store.serve_pfad(fotos_verz, medium_id)
    if pfad is None:
        return _bad_request("unbekannte id", status=404)
    return send_file(pfad)


@app.route("/api/v1/essen/fotos/<medium_id>/thumbnail", methods=["GET"])
@require_init_data
def get_foto_thumbnail(medium_id):
    """ESSEN-22 V1.2: Thumbnail-JPEG mit korrektem Content-Type."""
    fotos_verz = _paths()["fotos_verzeichnis"]
    pfad = medien_store.thumb_pfad(fotos_verz, medium_id)
    if pfad is None:
        return _bad_request("unbekannte id", status=404)
    return send_file(pfad)


@app.route("/api/v1/essen/fotos/<medium_id>", methods=["DELETE"])
@require_init_data
def delete_foto(medium_id):
    """ESSEN-22 V1.2: Vollbild + Thumbnail + Index-Eintrag atomar entfernen."""
    fotos_verz = _paths()["fotos_verzeichnis"]
    with _foto_write_lock:
        try:
            entfernt = medien_store.delete(fotos_verz, medium_id)
        except medien_store.StoreError as e:
            logger.warning("delete_foto: Löschen fehlgeschlagen: %s", e)
            return _bad_request(str(e), status=503)
    if not entfernt:
        return _bad_request("unbekannte id", status=404)
    return jsonify({"id": medium_id}), 200


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
