#!/usr/bin/env python3
"""Routine-Buddy-App — HTTP-Schnittstelle + Entrypoint (ROUTINE-1 … ROUTINE-19).

Siehe specs/buddies/routine.md. Der Routine-Buddy ist die XBuddy-App mit
dem Buddy-Slug `routine` (ROUTINE-1). Er besitzt seine Daten (Routine-Punkte
und Zeiten, ROUTINE-12), seine Funktion (die ablaufende Uhr, ROUTINE-9) und
stellt das Ergebnis über seine Display-View bereit (APP-1).

Endpunkte:
  GET  /display/routine/morgen          — View `morgen` (ROUTINE-2)
  POST /display/routine/morgen          — Tap → Abhak-Toggle (ROUTINE-7, URL-2)
                                          item_id im Request-Body (JSON oder Form)

  PUT  /api/v1/routine/config           — Zeiten setzen (ROUTINE-14, #343)
  GET  /healthz                         — Health-Check (SVC-1)

Reload-on-Read (ROUTINE-14, DCOMP-3): ab #343 liest der Buddy seine
Daten-Konfig je Request frisch aus routine.json; Last-Known-Good-Snapshot
bei transient kaputtem Read (kein Fall auf Code-Defaults).
Statische Assets unter /display/routine/static/<asset> (URL-13).
Port: 5050 (ROUTINE-15).
"""

import argparse
import contextlib
import dataclasses
import functools
import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

if __package__:
    from ._jsonio import read_json_or_empty
else:
    from routine._jsonio import read_json_or_empty

from flask import Flask, g, jsonify, redirect, render_template, request, url_for

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# MAD-7 / T1015: Init-Data-Auth aus tools.initdata (Cluster-A-Option-B
# ratifiziert 2026-06-18-1720 — kein sys.path-Hack auf eltern-chat mehr).
from tools import configloader, logsetup  # noqa: E402
from tools import familie_client as _familie_client_mod  # noqa: E402
from tools.familie_client import DEFAULT_ORIGIN as _FAMILIE_DEFAULT_ORIGIN  # noqa: E402
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.service_diagnostics import register_version  # noqa: E402

if __package__:
    from . import config as config_mod
    from . import items as items_mod
    from . import render as render_mod
    from . import uhr as uhr_mod
else:  # python3 routine/main.py
    sys.path.insert(0, _REPO_ROOT)
    from routine import config as config_mod
    from routine import items as items_mod
    from routine import render as render_mod
    from routine import uhr as uhr_mod


# ============================================================
#  Abhak-Datenhaltung (ROUTINE-8)
# ============================================================
#
# Schlanke JSON-Datei neben dem Code, gitignored (ROUTINE-8, BUD-2a).
# Hält nur den flüchtigen Tageszustand (welche Item-IDs heute abgehakt sind).
# Punkt-Definitionen kommen aus der Config — keine doppelte Wahrheit.


def _store_path():
    # SVC-5 / CONFIG-5: runtime["store_path"] (Test-Naht) schlägt ENV schlägt Default.
    # ENV_STORE_FILE / DEFAULT_STORE_FILE kommen aus config_mod (Symmetrie zu
    # ENV_DATA_FILE / DEFAULT_DATA_FILE — beide Pfade gleich aufgelöst).
    if runtime.get("store_path"):
        return runtime["store_path"]
    return (
        os.environ.get(config_mod.ENV_STORE_FILE)
        or config_mod.DEFAULT_STORE_FILE
    )


def _load_store():
    """Lädt den Abhak-Store. Fehlt die Datei → leerer Zustand (ROUTINE-8)."""
    return read_json_or_empty(_store_path())


def _save_store(data):
    """Speichert den Abhak-Store atomar (DCOMP-4: Temp+Replace)."""
    path = _store_path()
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp",
                                        prefix="store_write_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
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
    # MAD-7 / T708-C: Mini-App-Auth (Test-Naht; im Produktiv-Betrieb aus ENV).
    "bot_token":         None,
    "init_data_config":  None,
    # T1015: FAM-Lookup via tools.familie_client (HTTP); Test-Doppel mit
    # get_telegram_ids()-Methode oder FamilieClient-Instanz, None → ENV.
    "familie_client":    None,
}


def configure(cfg, data_path=None, store_path=None,
              bot_token=None, init_data_config=None, familie_client=None):
    """Setzt die Konfiguration (Test-Naht).

    `bot_token`, `init_data_config` (MAD-7 / T708-C): Auth-Naht für Tests;
    im Produktiv-Betrieb aus ENV.
    `familie_client` (T1015): Test-Doppel oder FamilieClient-Instanz; None →
    aus ENV ``ROUTINE_FAMILIE_ORIGIN`` bauen.
    """
    runtime["config"] = cfg
    runtime["data_path"] = data_path
    runtime["store_path"] = store_path
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if init_data_config is not None:
        runtime["init_data_config"] = init_data_config
    if familie_client is not None:
        runtime["familie_client"] = familie_client


def _current_config():
    """DCOMP-3 Reload-on-Read: liest routine.json je Request frisch (ROUTINE-14, #343).

    Eltern-Chat-Skill schreibt Cross-Service in routine.json (RZS, EC-21).
    Der lesende Routine-Buddy muss den neuen Stand ohne Service-Restart sehen
    — neue Zeiten erscheinen beim nächsten Aufruf von /display/routine/morgen.

    Fehlertoleranz (DCOMP-3 Last-Known-Good): scheitert der Read oder Parse
    (Datei kurz weg, atomares Replace-Race aus DCOMP-4, kaputtes JSON),
    fällt der Aufruf auf den letzten erfolgreich geladenen Snapshot zurück.
    KEIN Fall auf Code-Defaults solange ein gültiger Stand existiert.

    V2-Disziplin: liefert die ROH-Form — KEINE V1→V2-Synth-Migration. Die
    Migration ist ein Display-Render-Pfad-Anliegen (ROUTINE-28 Welle A) und
    wird vom Aufrufer (View `morgen`) explizit via config_mod.migriere_v1_anker
    gehoben, wenn der Render Synth-Anker braucht. Lese-API-Pfade (`GET /items`,
    `GET /config`) zeigen den persistierten ROH-Stand — V1-Felder bleiben als
    Spiegel sichtbar, items[] zeigt nur die wirklich persistierten Einträge.
    Damit bleiben Schreib-Pfad-Symmetrie + V1-Bestands-Tests stabil.
    """
    data_path = runtime.get("data_path")
    snapshot = runtime["config"]
    if not data_path:
        return snapshot
    try:
        # Roher JSON-Read: strikter Fail bei Datei weg oder kaputtem JSON (DCOMP-3).
        # Scheitert dieser Schritt, bleibt der Snapshot unverändert erhalten.
        with open(data_path, encoding="utf-8") as f:
            json.load(f)
    except (OSError, ValueError) as e:
        logger.debug(
            "reload-on-read fiel auf snapshot zurück (%s); "
            "Lookup nutzt zuletzt erfolgreich geladenen Stand", e)
        return snapshot
    try:
        new_cfg = config_mod.resolve_data(data_path)
    except Exception as e:
        logger.debug(
            "reload-on-read resolve fehlgeschlagen (%s); "
            "Lookup nutzt letzten Stand", e)
        return snapshot
    # Snapshot mitführen — nächster fehlgeschlagener Read hat immer den
    # zuletzt erfolgreichen Stand als Fallback (DCOMP-3).
    runtime["config"] = new_cfg
    return new_cfg


def _now(zeitzone):
    """Aktuelle Zeit in der Familien-Zeitzone.
    Now-Injektion für Tests liegt in uhr.py (E-ROUTINE-9, ROUTINE-18).
    """
    return datetime.now(ZoneInfo(zeitzone))


# ============================================================
#  MAD-7 Mini-App-Auth (T708-C)
# ============================================================

_ENV_BOT_TOKEN = "ELTERNCHAT_BOT_TOKEN"
# T1015: Familie-Service-Origin per Komponenten-ENV (CONFIG-5-Schema).
# Default kommt aus tools.familie_client.DEFAULT_ORIGIN (zentral, CLIENT-1).
_ENV_FAMILIE_ORIGIN = "ROUTINE_FAMILIE_ORIGIN"


def _get_bot_token():
    """Bot-Token aus runtime-Dict (Test-Naht) oder ENV (APP-7)."""
    return runtime.get("bot_token") or os.environ.get(_ENV_BOT_TOKEN)


def _get_familie_client():
    """Liefert einen FamilieClient (Test-Naht oder frisch aus ENV, T1015).

    Replaced den früheren familie.json-Direkt-Read (DCOMP-1 / FAM-7-Heilung,
    Cluster-A-Option-B 2026-06-18-1720).
    """
    cached = runtime.get("familie_client")
    if cached is not None:
        return cached
    origin = os.environ.get(_ENV_FAMILIE_ORIGIN, _FAMILIE_DEFAULT_ORIGIN)
    return _familie_client_mod.FamilieClient(origin_url=origin)


def require_init_data(fn):
    """Decorator: SOFT-AUTH (V3, #898) — Header optional.

    Verhalten:
    - Fehlt Authorization-Header: pass-through, g.init_data = None.
      Grund: Kind-Tablet-Calls (Display-View-JS) haben kein initData, rufen
      aber dieselben /api/v1/routine/*-Routen wie die Eltern-Mini-App.
    - Header vorhanden, ungültig: 401.
    - Header vorhanden, gültig + Mitglied: g.init_data gesetzt.
    - Header vorhanden, gültig + Nicht-Mitglied: 403.
    - Localhost-Bypass (Server-zu-Server): pass-through.

    Routes, die Eltern-only-Verhalten brauchen, prüfen explizit g.init_data.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        # Localhost-Bypass für Internal-Service-Calls.
        if (not request.headers.get("X-Forwarded-For")
                and request.remote_addr in ("127.0.0.1", "::1")):
            g.init_data = None
            return fn(*args, **kwargs)

        # V3 Soft-Auth: Header optional. Fehlt ODER leerer "tma "-Wert
        # (Mini-App-JS außerhalb Telegram-Kontext) → pass-through.
        auth_header = (request.headers.get("Authorization") or "").strip()
        if not auth_header or auth_header.lower() in ("tma", "tma "):
            g.init_data = None
            return fn(*args, **kwargs)
        if auth_header.lower().startswith("tma ") and not auth_header[4:].strip():
            g.init_data = None
            return fn(*args, **kwargs)

        # Header da → validieren.
        bot_token = _get_bot_token()
        if not bot_token:
            logger.error("MAD-7: %s nicht gesetzt — Mini-App-Route nicht nutzbar.", _ENV_BOT_TOKEN)
            return ("", 500)

        cfg = runtime.get("init_data_config")
        if cfg is None:
            cfg = _init_data_mod.load_config()
            runtime["init_data_config"] = cfg

        try:
            init_data = _init_data_mod.validate_header(
                auth_header,
                bot_token,
                cfg["max_age_seconds"],
            )
        except _init_data_mod.InitDataError:
            return ("", 401)

        # FAM-7/8: User-ID gegen Familien-Registry prüfen (HTTP-Pfad, T1015).
        familie_ids = _get_familie_client().get_telegram_ids()
        if familie_ids is not None and init_data.user_id not in familie_ids:
            logger.warning("FAM-7: user_id %s ist kein Familien-Mitglied → 403", init_data.user_id)
            return ("", 403)

        g.init_data = init_data
        return fn(*args, **kwargs)
    return wrapper


# ============================================================
#  Flask-App
# ============================================================

# URL-13: statische Assets im Display-Namensraum des Buddys (ROUTINE-2, BUD-1).
app = Flask(__name__, static_url_path="/display/routine/static")


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


@app.route("/display/routine/morgen", methods=["GET", "POST"])
def morgen():
    """View `morgen` — Routine-Checkliste + ablaufende Uhr (ROUTINE-2).

    GET:  Eine einzige Canvas: links Checkliste, rechts Uhr. Kein Routing, kein Tab
          (ROUTINE-2). Rendert heutige Items mit Abhak-Zustand und Uhr-Block.

    POST: Tap → Abhak-Toggle (ROUTINE-7, URL-2: kein Verb im Pfad, HTTP-Methode
          trägt die Aktion). item_id im Request-Body (JSON: {"item_id": "..."} oder
          Form: item_id=...). Toggelt den heutigen Abhak-Zustand, persistiert über
          Reload. Daten-Konfig per Reload-on-Read frisch (ROUTINE-14, DCOMP-3).
    """
    cfg = _current_config()

    if request.method == "POST":
        # item_id aus JSON- oder Form-Body lesen
        if request.is_json:
            body = request.get_json(silent=True) or {}
            item_id = body.get("item_id")
        else:
            item_id = request.form.get("item_id")

        if not item_id:
            return jsonify({"error": "item_id fehlt im Request-Body"}), 400

        # Validierung: Item-ID muss in der Config ODER in den einmalig-Items existieren
        # (ROUTINE-5: einmalig:-Präfix kollidiert nie mit default-IDs)
        item_ids = {item.id for item in cfg.items}
        einmalig_heute = items_mod.load_einmalig_heute(_store_path(), cfg.zeitzone)
        item_ids.update(e.get("id") for e in einmalig_heute if isinstance(e, dict))
        if item_id not in item_ids:
            return jsonify({"error": "unbekannte Item-ID"}), 404

        neuer_zustand = _toggle_abhak(item_id, cfg.zeitzone)
        return jsonify({"id": item_id, "abgehakt": neuer_zustand})

    # GET: View rendern
    zeitzone = cfg.zeitzone
    now = _now(zeitzone)
    tag = now.date()

    # Uhr (ROUTINE-9): injizierbares now; aufstehzeit aus Config (AC-FIX1, #335)
    try:
        zeiten = uhr_mod.berechne_zeiten(
            cfg.abfahrtszeit, cfg.anzieh_vorlauf_min, zeitzone, tag,
            aufstehzeit_cfg=cfg.aufstehzeit)
        uhr_view = uhr_mod.baue_uhr_view(zeiten, now) if zeiten else None
    except Exception as e:
        logger.error("Uhr-Berechnung fehlgeschlagen: %s — Uhr wird ausgeblendet", e)
        uhr_view = None

    # V2 (ROUTINE-28 Welle A): Display-Render zieht Synth-End-Anker aus den
    # V1-Feldern (aufstehzeit/abfahrtszeit), falls items[] keine eigenen
    # locked-Anker trägt. Lese-API (`GET /items`) bleibt bewusst auf der
    # ROH-Form — Migration ist ein Display-Anliegen, nicht ein Schreib-Mirror.
    cfg_display = config_mod.migriere_v1_anker(cfg)

    # Einmalig-Items für heute laden und zu den default-Items hinzufügen (ROUTINE-6/8)
    # ROUTINE-6: nach Tageswechsel sind einmalig-Items automatisch weg (load_einmalig_heute)
    einmalig_heute = items_mod.load_einmalig_heute(_store_path(), zeitzone)
    if einmalig_heute:
        einmalig_item_objs = [
            config_mod.RoutineItem(
                id=e["id"],
                label=e.get("label", ""),
                piktogramm=str(e.get("piktogramm", "")),
                quelle="einmalig",
                zeit=e.get("zeit") if isinstance(e.get("zeit"), dict) else None,
            )
            for e in einmalig_heute
            if isinstance(e, dict) and e.get("id")
        ]
        cfg_merged = dataclasses.replace(
            cfg_display, items=cfg_display.items + einmalig_item_objs)
    else:
        cfg_merged = cfg_display

    abhak = _abhak_zustand(zeitzone)
    view = render_mod.baue_view(cfg_merged, abhak, uhr_view)

    return render_template("morgen.html", view=view)


@app.route("/display/routine/")
@app.route("/display/routine")
def index():
    """Weiterleitung zur View `morgen` (BUD-1, ROUTINE-2)."""
    return redirect(url_for("morgen"))


@app.route("/api/v1/routine/config", methods=["GET"])
def api_config_get():
    """Zeiten-Lese-API (ROUTINE-14, #728, URL-14).

    Liefert die aktuell aktive RoutineConfig als JSON-Body — Schema spiegelt
    exakt das, was PUT akzeptiert (Schema-Symmetrie, ROUTINE-14):
      abfahrtszeit       — "HH:MM" oder Wochentag-Map
      aufstehzeit        — "HH:MM" oder Wochentag-Map
      anzieh_vorlauf_min — int ≥ 0

    Reload-on-Read (DCOMP-3): ruft _current_config() — liest je Request
    frisch aus routine.json, fällt bei Fehler auf Last-Known-Good zurück.
    Kein konfigurierter data_path → 500 mit ehrlichem Fehler (KEINE leeren Defaults).
    """
    data_path = runtime.get("data_path")
    if not data_path:
        return jsonify({"error": "data_path nicht konfiguriert — kein Lesen möglich"}), 500

    cfg = _current_config()
    if cfg is None:
        return jsonify({"error": "Keine Konfiguration geladen"}), 500

    body = {
        "abfahrtszeit": cfg.abfahrtszeit,
        "aufstehzeit": cfg.aufstehzeit,
        "anzieh_vorlauf_min": cfg.anzieh_vorlauf_min,
    }
    logger.info("GET /api/v1/routine/config (ROUTINE-14, #728)")
    return jsonify(body)


@app.route("/api/v1/routine/config", methods=["PUT"])
def api_config():
    """Zeiten-Schreib-API (ROUTINE-14, #343, URL-14).

    Setzt die Zeit-Schlüssel der Daten-Konfig (ROUTINE-12):
      abfahrtszeit      — "HH:MM" oder Wochentag-Map
      aufstehzeit       — "HH:MM" oder Wochentag-Map
      anzieh_vorlauf_min — int ≥ 0

    Payload: JSON-Body, alle Felder optional, mindestens eines erforderlich.
    Validierung (ROUTINE-14): strikt HH:MM (24h), nur gültige Wochentags-Keys,
    anzieh_vorlauf_min nicht-negativer Integer.
    Ungültig → 400, kein Schreiben, kein Teil-Write (AC2).
    Persistenz atomar in routine.json (DCOMP-4) via config_mod.write_data().
    Reload-on-Read: neue Zeiten sind ohne Neustart beim nächsten Aufruf
    von /display/routine/morgen sichtbar (DCOMP-3, EC-21).
    """
    data_path = runtime.get("data_path")
    if not data_path:
        # Kein data_path konfiguriert (z.B. reine In-Memory-Tests) — kein Schreiben möglich.
        return jsonify({"error": "data_path nicht konfiguriert — kein Schreiben möglich"}), 500

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON-Body erwartet"}), 400

    try:
        config_mod.write_data(data_path, body)
    except config_mod.ValidationError as e:
        return jsonify({"error": str(e)}), 400

    # ROUTINE-25: V1-Bridge mit Deprecation-Hinweis (200-Antwort + Header).
    # V2-Pfad ist PUT /api/v1/routine/items mit zeit-Sub-Block (ROUTINE-24);
    # PUT /config bleibt funktionsfähig (Welle A, ROUTINE-28).
    resp = jsonify({"ok": True, "deprecated": True})
    resp.headers["X-Deprecation"] = (
        "PUT /api/v1/routine/items akzeptiert zeit-Block (ROUTINE-25)")
    return resp


# ============================================================
#  Items-Schreib-API (ROUTINE-14, #354)
# ============================================================

def _items_paths():
    """Liefert (data_path, store_path) aus runtime — oder (None, None) wenn nicht gesetzt."""
    return runtime.get("data_path"), _store_path()


def _items_zeitzone():
    """Aktuelle Zeitzone aus dem aktuellen Config-Snapshot (Reload-on-Read)."""
    cfg = _current_config()
    if cfg and cfg.zeitzone:
        return cfg.zeitzone
    return "Europe/Berlin"


@app.route("/api/v1/routine/items", methods=["GET"])
def api_items_get():
    """Aktuelle Items-Liste lesen (ROUTINE-14, V1.2, #469).

    Antwort: {"default": [{id, label, piktogramm}, …],
              "einmalig_heute": [{id, label, piktogramm}, …]}.
    Reload-on-Read (DCOMP-3): per Request frisch aus routine.json + Store lesen.
    Trennung bindend: default und einmalig haben unterschiedliche Persistenz (RPS-3).
    """
    cfg = _current_config()
    zeitzone = cfg.zeitzone if cfg and cfg.zeitzone else "Europe/Berlin"

    default_items = []
    for item in (cfg.items if cfg else []):
        out = {"id": item.id, "label": item.label, "piktogramm": item.piktogramm}
        # ROUTINE-24/25: zeit-Block in der Antwort durchreichen (für Mini-App-Konsumenten).
        if item.zeit is not None:
            out["zeit"] = item.zeit
        default_items.append(out)

    einmalig_raw = items_mod.load_einmalig_heute(_store_path(), zeitzone)
    einmalig_items = []
    for e in einmalig_raw:
        if not (isinstance(e, dict) and e.get("id")):
            continue
        out = {
            "id": e["id"],
            "label": e.get("label", ""),
            "piktogramm": str(e.get("piktogramm", "")),
        }
        if isinstance(e.get("zeit"), dict):
            out["zeit"] = e["zeit"]
        einmalig_items.append(out)

    return jsonify({"default": default_items, "einmalig_heute": einmalig_items})


@app.route("/api/v1/routine/items", methods=["POST"])
def api_items_post():
    """Punkt anlegen (ROUTINE-14, #354, URL-14).

    JSON-Body: quelle (default | einmalig), label, piktogramm (ARASAAC-ID).
    quelle=default → in routine.json (persistent, ROUTINE-12).
    quelle=einmalig → in den Tages-State (heute, Auto-Verfall ROUTINE-6).
    Antwort: {"id": <neue_id>} (ID-Form ROUTINE-5).
    ROUTINE-19: ≥8 Items → 400 + ehrlicher Fehler, kein Schreiben.
    Reload-on-Read: neuer Punkt ohne Neustart auf /display/routine/morgen sichtbar.
    """
    data_path, store_path = _items_paths()
    if not data_path:
        return jsonify({"error": "data_path nicht konfiguriert — kein Schreiben möglich"}), 500

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON-Body erwartet"}), 400

    quelle = body.get("quelle", "default")
    label = body.get("label", "")
    piktogramm = body.get("piktogramm", "")
    zeit = body.get("zeit")  # ROUTINE-24/25: optionaler zeit-Sub-Block
    zeitzone = _items_zeitzone()

    try:
        result = items_mod.add_item(
            data_path, store_path, quelle, label, piktogramm, zeitzone, zeit=zeit)
    except items_mod.ItemsError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result), 201


@app.route("/api/v1/routine/items", methods=["PUT"])
def api_items_put():
    """Geordnete default-Liste ersetzen (ROUTINE-14, #354, URL-14).

    Idempotent: ersetzt die komplette items-Liste durch die übergebene
    (Reihenfolge ändern / Bulk, RPS-3). Kein einmalig-Einfluss.
    JSON-Body: Liste von {id, label, piktogramm}.
    ROUTINE-19: >8 Einträge → 400, kein Schreiben.
    """
    data_path, _ = _items_paths()
    if not data_path:
        return jsonify({"error": "data_path nicht konfiguriert — kein Schreiben möglich"}), 500

    body = request.get_json(silent=True)
    if not isinstance(body, list):
        return jsonify({"error": "JSON-Array erwartet"}), 400

    try:
        result = items_mod.replace_default_items(data_path, body)
    except items_mod.ItemsError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result)


@app.route("/api/v1/routine/items/<item_id>", methods=["DELETE"])
def api_items_delete(item_id):
    """Punkt entfernen (ROUTINE-14, #354, URL-14).

    default-ID → aus routine.json (atomar, DCOMP-4).
    einmalig:-ID → aus Tages-State (atomar).
    Existiert die ID nicht → 404.
    """
    data_path, store_path = _items_paths()
    if not data_path:
        return jsonify({"error": "data_path nicht konfiguriert — kein Schreiben möglich"}), 500

    zeitzone = _items_zeitzone()

    try:
        result = items_mod.delete_item(data_path, store_path, item_id, zeitzone)
    except items_mod.ItemsError as e:
        # ID nicht gefunden → 404; sonstige Fehler → 400
        msg = str(e)
        if "nicht gefunden" in msg:
            return jsonify({"error": msg}), 404
        return jsonify({"error": msg}), 400

    return jsonify(result)


# ============================================================
#  Entrypoint (ROUTINE-15/17)
# ============================================================

logger = logging.getLogger(__name__)

# Runtime-Konfig-Schema (CONFIG-1): nur Service-Start-Werte.
# Port 5050 (ROUTINE-15, OPEN-ROUTINE-H — erster freier Buddy-Block-Port).


# ── Health-Check (SVC-1) ─────────────────────────────────────────────────

@app.route("/healthz", methods=["GET"])
def healthz():
    """SVC-1: Health-Endpoint — liefert immer 200 + OK."""
    return jsonify({"ok": True}), 200


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
