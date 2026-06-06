#!/usr/bin/env python3
"""Plan-Buddy-App — HTTP-Schnittstellen + Entrypoint (PLAN-1 … PLAN-29).

Siehe specs/buddies/plan.md. Der Plan-Buddy ist die XBuddy-App mit dem
Buddy-Slug `plan` (PLAN-1). Er besitzt seine Daten (Verantwortlichkeiten,
plan.db) und seine Funktion (Kalender-Anbindung) und stellt beides über
Schnittstellen bereit (PLAN-21/22/23).

Endpunkte:
  GET /display/plan/woche               — View `woche`, Lese-Kind (PLAN-2/3/21)
  GET /display/plan/woche?ansicht=klein — View `woche`, Kleinkind (PLAN-3)
  GET /display/plan/woche?ab=<iso>      — Anker verschieben (PLAN-4)
  PUT /api/v1/plan/zuteilung            — Erwachsenen-Slot zuweisen (PLAN-7/8)
  PUT|DELETE /api/v1/plan/aktivitaet    — Kind-Aktivität setzen/löschen (PLAN-11)
  GET|PUT /api/v1/plan/termine          — Termin-Schnittstelle für Apps (PLAN-22)
  PUT /api/v1/plan/admin/kalender       — kalender_id setzen (PLAN-32, loopback)

Service-Topologie wie familie/main.py: eine schlanke eigenständige Flask-App,
ein Geschwister von router/ und familie/.
"""

import argparse
import contextlib
import json
import logging
import os
import sys
import tempfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request

# Repo-Wurzel auf den Importpfad — die App konsumiert die Library
# `tools.zugangsdaten` (PLAN-16, DCOMP-1-Ausnahme: `tools/` ist gemeinsamer
# Bibliotheks-Code, kein Komponenten-Code). Personen-Daten holt der
# Plan-Buddy ueber HTTP von der Familie-Komponente (`familie_client`,
# DCOMP-1) — kein `from familie import …` mehr.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import configloader, logsetup  # noqa: E402
from tools.zugangsdaten import Zugangsdaten, resolve_store_path  # noqa: E402

# Das plan-Paket wird als Paket importiert, damit die relativen Imports in
# config/db/kalender/render greifen — auch wenn main.py direkt gestartet wird.
if __package__:
    from . import aktivitaeten as aktivitaeten_mod
    from . import config as config_mod
    from . import db as db_mod
    from . import familie_client as familie_client_mod
    from . import kalender as kalender_mod
    from . import render as render_mod
else:  # python3 plan/main.py
    sys.path.insert(0, _REPO_ROOT)
    from plan import aktivitaeten as aktivitaeten_mod
    from plan import config as config_mod
    from plan import db as db_mod
    from plan import familie_client as familie_client_mod
    from plan import kalender as kalender_mod
    from plan import render as render_mod


# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Der Entrypoint befüllt `runtime`; Tests setzen es direkt über configure().
# Der `config`-Slot ist ab DCOMP-2 (Reload-on-Read, #210) der Last-Known-Good-
# Snapshot — nicht mehr die Lookup-Wahrheit. Endpoints lesen via
# `_current_config()` pro Aufruf frisch von Disk; der Snapshot dient nur als
# Fallback, wenn ein einzelner Read scheitert (gleicher atomarer Geist wie
# E-RELOAD-1 / ROU-25).
runtime = {
    "config": None,            # plan.config.Config — Last-Known-Good-Snapshot
    "registry": None,          # Test-Naht: direkt gesetzte RegistryView (oder duck-typed)
    "familie_client": None,    # Live: FamilieClient — HTTP zur Familie-Komponente (DCOMP-1)
    "transport": None,         # plan.kalender.GoogleTransport (oder Fake in Tests)
    "config_path": None,       # Pfad zur plan.json — Naht für DCOMP-2 + Reload-Endpoint (#140)
    "transport_factory": None, # cfg -> transport — neu binden, wenn kalender_id wechselt
}


def configure(cfg, registry, transport, familie_client=None,
              config_path=None, transport_factory=None):
    """Setzt Konfiguration, Familien-Zugang und Kalender-Transport.

    `transport` ist die Test-Naht (PLAN-29): in Produktion ein
    GoogleTransport, in Tests ein Fake.

    `registry` ist die Test-Naht fuer Personen-Daten: ein in-memory-
    Objekt mit `.alle()`/`.get(id)` (`plan.familie_client.RegistryView`
    oder das alte `familie.registry.Registry` — beide duck-kompatibel).
    Tests setzen das direkt; `familie_client` bleibt dann `None`.

    `familie_client` ist die Live-Naht (DCOMP-1): ein
    `plan.familie_client.FamilieClient`, der pro Request ueber HTTP einen
    frischen Personen-Snapshot von der Familie-Komponente holt — extern
    (z. B. durch FAA ueber den Eltern-Chat-Bot) angelegte Personen sind
    ohne Plan-Service-Restart sichtbar. Ist `familie_client` gesetzt, hat
    er Vorrang vor `registry`.

    `config_path` ist die Naht für DCOMP-2 (Reload-on-Read, #210) UND den
    Admin-Reload-Endpoint (#140, EC-21): wird er gesetzt, liest der
    Plan-Buddy `plan.json` pro Aufruf frisch von Disk — KAV-Schreibvorgänge
    (Kalender verbinden) werden ohne Service-Restart und ohne Admin-Reload-
    Aufruf sichtbar. Ohne `config_path` bleibt das übergebene `cfg`-Objekt
    die Quelle (Test-Modus, kein Disk-IO).

    `transport_factory(cfg) -> transport` wird sowohl im Reload-on-Read-Pfad
    (`_kalender()`, sobald die `kalender_id` wechselt) als auch im Admin-
    Reload-Pfad aufgerufen, sobald eine neue Config geparst wurde, und liefert
    einen frischen Transport mit der ggf. geänderten `kalender_id`. In Tests
    bleibt der Default-Wert `None` — die Tests setzen den Transport direkt
    oder übergeben einen eigenen Factory-Stub.
    """
    runtime["config"] = cfg
    runtime["registry"] = registry
    runtime["familie_client"] = familie_client
    runtime["transport"] = transport
    runtime["config_path"] = config_path
    runtime["transport_factory"] = transport_factory


def _aktuelle_registry():
    """Liefert die aktuelle Familien-Sicht für genau diesen Request.

    Live (mit `familie_client`): pro Request ein frischer
    `RegistryView`-Snapshot ueber HTTP von der Familie-Komponente (FAM-7,
    DCOMP-1) — extern angelegte Personen sind ohne Restart sichtbar. Bei
    Erreichbarkeitsproblemen liefert der Client einen leeren Snapshot +
    Log-Warnung (PLAN-20-Geist), kein Stack-Trace.
    Test/in-memory (ohne `familie_client`): das uebergebene `registry`-
    Objekt bleibt die Quelle.
    """
    client = runtime.get("familie_client")
    if client is None:
        return runtime["registry"]
    return client.snapshot()


def _current_config():
    """DCOMP-2 Reload-on-Read: liefert die plan.json-Config pro Aufruf
    frisch von Disk (#210, Refs #166).

    Eltern-Chat-Skills schreiben Cross-Service in `plan.json` (KAV — Kalender
    verbinden, EC-21). Der lesende Plan-Buddy muss den neuen Stand ohne
    Service-Restart und ohne Admin-Reload-Aufruf sehen — sonst zeigt er den
    alten Kalender, obwohl KAV bereits eine neue `kalender_id` geschrieben hat.

    Fehlertoleranz (gleicher atomarer Geist wie der Admin-Reload, E-RELOAD-1 / ROU-25):
    scheitert der Read oder Parse (Datei kurz weg, atomares Replace im
    Halbschritt, kaputtes JSON, ungültige Pflichtwerte wie fehlende
    `kalender_id`), fällt der Aufruf auf den Last-Known-Good-Snapshot in
    `runtime["config"]` zurück. Damit kippt der Plan-Buddy bei einem kurzen
    Race nicht in einen leeren Zustand.

    Ohne konfigurierten `config_path` (z. B. unter Tests, die `configure()`
    ohne `config_path` aufgerufen haben) wird der Snapshot direkt
    zurückgegeben — dann ist `runtime["config"]` weiterhin die Quelle und
    die Test-Naht bleibt erhalten.
    """
    path = runtime.get("config_path")
    snapshot = runtime["config"]
    if not path:
        return snapshot
    try:
        new_cfg = config_mod.resolve(path)
    except (config_mod.ConfigError, OSError) as e:
        logger.debug(
            "reload-on-read fiel auf snapshot zurück (%s); "
            "Lookup nutzt zuletzt erfolgreich geladenen Stand", e)
        return snapshot
    # Snapshot mitführen — der nächste fehlgeschlagene Read hat immer den
    # zuletzt erfolgreichen Stand als Fallback.
    runtime["config"] = new_cfg
    return new_cfg


def _kalender():
    """Baut die Kalender-Anbindung aus dem laufenden Transport (PLAN-15…20).

    DCOMP-2 (#210): wechselt die `kalender_id` in plan.json (KAV-Schreibvorgang),
    muss auch der Transport die neue ID kennen. Steht eine `transport_factory`
    bereit (Live-Pfad), bauen wir den Transport bei Bedarf pro Aufruf neu —
    der Snapshot in `runtime["transport"]` bleibt als Fallback. Tests, die
    `transport_factory=None` lassen, behalten den festen Test-Transport — die
    Test-Naht (PLAN-29) bleibt unberührt.
    """
    cfg = _current_config()
    transport = runtime["transport"]
    factory = runtime.get("transport_factory")
    if factory is not None and getattr(transport, "kalender_id", None) != cfg.kalender_id:
        # `kalender_id` hat sich gegenüber dem zuletzt gebauten Transport
        # geändert — frischen Transport bauen und als neuen Snapshot halten.
        transport = factory(cfg)
        runtime["transport"] = transport
    return kalender_mod.Kalender(transport, _aktuelle_registry().alle())


def _db():
    """Öffnet die SQLite-Verbindung (PLAN-9). Pro Request frisch (V1).

    DCOMP-2 (#210): `db_datei` kommt aus `_current_config()`, das pro Aufruf
    frisch von Disk liest — damit ist ein Pfad-Wechsel in plan.json ohne
    Service-Restart wirksam. Abgedeckt durch
    test_DCOMP_2_db_datei_wechsel_wirksam_ohne_restart (Closes #233).
    """
    return db_mod.connect(_current_config().db_datei)


# ============================================================
#  Flask-App
# ============================================================

# URL-13: statische Assets des Plan-Buddys liegen in seinem Display-
# Namensraum. So werden sie hinter der einen Origin (URL-12) geroutet —
# der Flask-Default `/static` läge außerhalb der URL-1-Prefixe (#61).
app = Flask(__name__, static_url_path="/display/plan/static")

# FAM-8: der HTTP-Endpunkt der Familien-Registry, der Profilfotos liefert.
# Eine stabile Cross-Komponenten-URL (URL-8) — der Plan-Buddy verlinkt
# darauf, statt Fotos selbst auszuliefern (MIGRATION.md §2).
FAMILIE_FOTO_BASIS = "/api/v1/familie/foto/"


def _anker_aus_request():
    """Löst den Fenster-Anker aus `?ab=` auf (PLAN-4). Ohne Parameter: heute."""
    ab = request.args.get("ab")
    if ab:
        try:
            return date.fromisoformat(ab)
        except ValueError:
            logger.warning("ungültiger ?ab=-Wert %r — Anker bleibt heute", ab)
    return date.today()


@app.route("/display/plan/woche", methods=["GET"])
def woche():
    """View `woche` in zwei Stufen (PLAN-2, PLAN-3, PLAN-21).

    Ohne Parameter: Lese-Kind (rollierende Lese-Kind-Tage, Termin-Leiste).
    `?ansicht=klein`: Kleinkind (weniger Tage, XL-Maße, keine Termin-Leiste).
    `?ab=<iso>`: verschiebt den Anker (PLAN-4).
    """
    # DCOMP-2 (#210): plan.json pro Request frisch von Disk — KAV-Schreibvorgänge
    # (neue Slot-Liste, neue Defaults, neue Fenster-Größen, neue kalender_id)
    # werden ohne Service-Restart in der View sichtbar.
    cfg = _current_config()
    kleinkind = request.args.get("ansicht") == "klein"
    if kleinkind:
        anzahl_tage = cfg.fenster_kleinkind
        variant = "toddler"
        mit_terminen = False
    else:
        anzahl_tage = cfg.fenster_lesekind
        variant = "full"
        mit_terminen = True

    anker = _anker_aus_request()
    conn = _db()
    registry = _aktuelle_registry()
    try:
        view = render_mod.baue_view(
            cfg, conn, _kalender(), registry,
            anker, anzahl_tage, mit_terminen)
    finally:
        conn.close()

    personen = registry.alle()
    # PLAN-24: Identität nur über Foto im Ring. Das Foto liefert die
    # Familien-Registry über ihren HTTP-Endpunkt FAM-8 — eine stabile
    # Cross-Komponenten-URL (URL-8). Nur Personen mit Foto bekommen einen
    # Eintrag; Personen ohne Foto erscheinen als Ring ohne Bild.
    person_photo_url = {
        p.id: FAMILIE_FOTO_BASIS + p.id for p in personen if p.foto
    }

    return render_template(
        "plan_kinder.html",
        slots=[s.to_dict() for s in cfg.slots],
        personen=[p.to_dict() for p in personen],
        person_photo_url=person_photo_url,
        days=view["tage"],
        schedule=view["schedule"],
        appointments=view["appointments"],
        span_appointments=view["span_appointments"],
        show_appointments=view["show_appointments"],
        variant=variant,
        anchor=anker.isoformat(),
    )


@app.route("/api/v1/plan/zuteilung", methods=["GET"])
def api_zuteilung_lesen():
    """PLAN-30: Lese-API fuer Wochenzuteilungen (analog FAM-7-Form).

    Query: `?week_start=YYYY-MM-DD` (Pflicht). Liefert die persistierten
    Zuteilungen dieser Woche als Liste:
        [ { "day": 0..6, "slot": "<schluessel>", "person_id": "<id>|null" }, ... ]
    Ist die Woche noch nicht initialisiert, antwortet die API mit den
    Default-Verantwortlichkeiten (PLAN-10) — der Erst-Lesepfad belegt die
    Woche aus plan.json vor, sodass ein Konsument denselben Stand sieht wie
    eine View-Anfrage.

    Ungueltiges `week_start` → HTTP 400 mit JSON-Fehler.

    DCOMP-2 (#210): wir lesen plan.json frisch von Disk (`_db()`,
    `_current_config()`) — ein KAV-Schreibvorgang oder eine neue Default-
    Liste ist ohne Service-Restart sichtbar.
    """
    week_start = request.args.get("week_start")
    if not week_start:
        return jsonify({"error": "week_start ist Pflicht"}), 400
    try:
        date.fromisoformat(week_start)
    except (TypeError, ValueError):
        return jsonify({
            "error": "week_start muss ein ISO-Datum YYYY-MM-DD sein"
        }), 400

    cfg = _current_config()
    erwachsenen_keys = [s.schluessel for s in cfg.erwachsenen_slots()]
    conn = _db()
    try:
        # Erst-Lese-Pfad: die Woche wird wie in der View aus den Defaults
        # vorbelegt (PLAN-10). Damit liefert die Lese-API dieselbe Wahrheit
        # wie die View — kein Sonderstand „API sieht Defaults nicht".
        db_mod.init_week(conn, week_start, cfg.default_verantwortlichkeiten)
        zuweisungen = db_mod.assignments_for_weeks(conn, [week_start])
    finally:
        conn.close()

    # Wir liefern eine Zeile je Erwachsenen-Slot je Wochentag (0..6). Slots,
    # die nicht in der Config stehen, erscheinen nicht — die Form orientiert
    # sich an der aktuellen Slot-Definition (DCOMP-2).
    slots = []
    for day in range(7):
        for key in erwachsenen_keys:
            slots.append({
                "day": day,
                "slot": key,
                "person_id": zuweisungen.get((week_start, day, key)),
            })
    return jsonify({"week_start": week_start, "slots": slots})


@app.route("/api/v1/plan/zuteilung", methods=["PUT"])
def api_zuteilung():
    """Weist einem Erwachsenen-Slot eine Person zu (PLAN-7, PLAN-8).

    Body: { week_start, day, slot, person_id }. `person_id` darf null sein
    (leerer Slot). Die Zuweisung wird lokal in plan.db gespeichert (PLAN-9).
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON-Body fehlt oder ungültig"}), 400
    for feld in ("week_start", "day", "slot"):
        if feld not in body:
            return jsonify({"error": "%s ist Pflicht" % feld}), 400
    # DCOMP-2 (#210): die Slot-Definition für die Validierung kommt aus dem
    # frischen plan.json — eine eben hinzugefügte Slot-Form wird sofort als
    # gültig akzeptiert, ohne Restart.
    slot = _current_config().slot(body["slot"])
    if slot is None or not slot.ist_erwachsenen_slot():
        return jsonify({"error": "kein Erwachsenen-Slot: %r" % body["slot"]}), 400
    person_id = body.get("person_id")
    if person_id is not None and _aktuelle_registry().get(person_id) is None:
        return jsonify({"error": "unbekannte person_id: %r" % person_id}), 400
    try:
        day = int(body["day"])
    except (TypeError, ValueError):
        return jsonify({"error": "day ist keine Ganzzahl"}), 400
    conn = _db()
    try:
        db_mod.set_assignment(conn, body["week_start"], day, body["slot"], person_id)
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/v1/plan/aktivitaet", methods=["PUT", "DELETE"])
def api_aktivitaet():
    """Setzt oder löscht eine Kind-Aktivität im Kalender (PLAN-11, PLAN-18).

    PUT-Body: { datum, kind, type[, event_id] } — legt einen ganztägigen
    Termin `<Aktivität> <Kindname>` an oder ändert ihn (PLAN-19).
    DELETE-Body: { event_id } — löscht den Termin.
    """
    body = request.get_json(silent=True) or {}
    kalender = _kalender()
    try:
        if request.method == "DELETE":
            event_id = body.get("event_id")
            if not event_id:
                return jsonify({"error": "event_id ist Pflicht"}), 400
            kalender.event_loeschen(event_id)
            return jsonify({"ok": True, "action": "deleted"})

        kind_id = body.get("kind")
        art = body.get("type")
        datum = body.get("datum")
        kind = _aktuelle_registry().get(kind_id)
        if kind is None or not kind.is_kind():
            return jsonify({"error": "unbekanntes Kind: %r" % kind_id}), 400
        if not art:
            return jsonify({"error": "type ist Pflicht"}), 400
        titel = "%s %s" % (_aktivitaet_label(art), kind.name)
        event_id = body.get("event_id")
        if event_id:
            neue_id = kalender.event_aendern(event_id, titel)
            return jsonify({"ok": True, "action": "patched", "event_id": neue_id})
        if not datum:
            return jsonify({"error": "datum ist Pflicht"}), 400
        # event_anlegen ohne ende → eintägig ganztägig (PLAN-11, verhaltensneutral).
        neue_id = kalender.event_anlegen(titel, date.fromisoformat(datum))
        return jsonify({"ok": True, "action": "created", "event_id": neue_id})
    except kalender_mod.CalendarUnavailable as e:
        # PLAN-20: Schreib-Misserfolg ist klar erkennbar.
        logger.error("Aktivitäts-Schreibvorgang fehlgeschlagen: %s", e)
        return jsonify({"error": "Kalender nicht erreichbar"}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


def _parse_beginn_ende(body):
    """Parst beginn/ende aus einem PUT-/termine-Body (PLAN-22, #256).

    Erkennung via 'T' im String (spiegelt _parse_when aus kalender.py):
    - Enthält der Wert ein 'T': datetime-Modus (zeitgebunden).
    - Sonst: date-Modus (ganztägig).

    Rückwärts-Compat: `datum` ist Alias für ganztägiges `beginn`. Beide
    gesetzt und ungleich → ValueError (AC4).

    Zeitzone (PLAN-28, #256): naive Datum-Zeiten werden in der Familien-
    Zeitzone (`_current_config().zeitzone`, Default Europe/Berlin) aware
    gemacht, bevor sie an event_anlegen übergeben werden.

    Liefert (beginn, ende) wobei `ende` None sein kann (eintägig-ganztägig).
    Wirft ValueError bei Validierungsfehlern (AC4).
    """
    beginn_raw = body.get("beginn")
    datum_raw = body.get("datum")

    # datum ist Alias für ganztägiges beginn (Rückwärts-Compat, AC3).
    if datum_raw and beginn_raw:
        if datum_raw != beginn_raw:
            raise ValueError(
                "datum und beginn sind beide gesetzt aber ungleich — "
                "datum ist Alias für beginn (ganztägig)")
        # Beide identisch: beginn_raw gewinnt, datum_raw ignorieren.
    if beginn_raw is None:
        if datum_raw:
            beginn_raw = datum_raw
        else:
            raise ValueError("beginn (oder datum als Alias) ist Pflicht")

    ende_raw = body.get("ende")

    # Typ-Erkennung via 'T': entspricht der Logik in _parse_when.
    beginn_ist_datetime = isinstance(beginn_raw, str) and "T" in beginn_raw
    ende_ist_datetime = isinstance(ende_raw, str) and "T" in ende_raw if ende_raw else None

    if beginn_ist_datetime:
        # Zeitgebunden: ende Pflicht (AC4).
        if not ende_raw:
            raise ValueError(
                "zeitgebundener Termin (beginn enthält 'T'): ende ist Pflicht")
        if ende_raw and not ende_ist_datetime:
            raise ValueError(
                "Typ-Mismatch: beginn ist datetime, ende muss datetime sein (nicht date)")
        try:
            beginn_dt = datetime.fromisoformat(beginn_raw.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("beginn ist kein gültiges ISO-Datetime: %r" % beginn_raw)
        try:
            ende_dt = datetime.fromisoformat(ende_raw.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("ende ist kein gültiges ISO-Datetime: %r" % ende_raw)
        # Naive Datetimes in Familien-Zeitzone aware machen.
        tz = ZoneInfo(_current_config().zeitzone)
        if beginn_dt.tzinfo is None:
            beginn_dt = beginn_dt.replace(tzinfo=tz)
        if ende_dt.tzinfo is None:
            ende_dt = ende_dt.replace(tzinfo=tz)
        # Validierung ende > beginn (AC4).
        if ende_dt <= beginn_dt:
            raise ValueError("zeitgebundener Termin: ende muss nach beginn liegen")
        return beginn_dt, ende_dt
    else:
        # Ganztägig: beginn und ggf. ende sind Datumsstrings.
        if ende_raw and ende_ist_datetime:
            raise ValueError(
                "Typ-Mismatch: beginn ist date (ganztägig), ende muss date sein (nicht datetime)")
        try:
            beginn_d = date.fromisoformat(beginn_raw)
        except ValueError:
            raise ValueError("beginn ist kein gültiges ISO-Datum: %r" % beginn_raw)
        if ende_raw:
            try:
                ende_d = date.fromisoformat(ende_raw)
            except ValueError:
                raise ValueError("ende ist kein gültiges ISO-Datum: %r" % ende_raw)
            # Validierung ende >= beginn (AC4).
            if ende_d < beginn_d:
                raise ValueError(
                    "ganztägiger Termin: ende darf nicht vor beginn liegen")
            return beginn_d, ende_d
        return beginn_d, None


@app.route("/api/v1/plan/termine", methods=["GET", "PUT"])
def api_termine():
    """Termin-Schnittstelle für andere XBuddy-Apps (PLAN-22).

    GET ?ab=<iso>&tage=<n>: liefert die normalisierten Termine des Zeitraums.

    PUT-Body (vollständiger Vertrag → PLAN-22, #256):
      { titel, beginn, [ende], [event_id] }
      - beginn als ISO-Datum (YYYY-MM-DD)  → ganztägig; ende optional (fehlt: eintägig)
      - beginn als ISO-Datum-Zeit           → zeitgebunden; ende Pflicht
      - datum ist Rückwärts-Alias für ganztägiges beginn (Compat AC3)
      - event_id angegeben                  → Titel-Patch (PLAN-18)
    Validierungsfehler → HTTP 400. Der Familien-Kalender ist nur über diese
    Schnittstelle erreichbar — Apps rufen Google nicht direkt (PLAN-22).
    """
    kalender = _kalender()
    if request.method == "GET":
        ab = request.args.get("ab")
        try:
            start = date.fromisoformat(ab) if ab else date.today()
            tage = int(request.args.get("tage", 7))
        except ValueError:
            return jsonify({"error": "ungültiger ab/tage-Parameter"}), 400
        events = kalender.events(start, tage)
        return jsonify([e.to_dict() for e in events])

    body = request.get_json(silent=True) or {}
    titel = body.get("titel")
    if not titel:
        return jsonify({"error": "titel ist Pflicht"}), 400
    try:
        if body.get("event_id"):
            neue_id = kalender.event_aendern(body["event_id"], titel)
            return jsonify({"ok": True, "action": "patched", "event_id": neue_id})
        # Mehrtages-Spannen und zeitgebundene Termine (PLAN-22, #256).
        beginn, ende = _parse_beginn_ende(body)
        neue_id = kalender.event_anlegen(titel, beginn, ende)
        return jsonify({"ok": True, "action": "created", "event_id": neue_id})
    except kalender_mod.CalendarUnavailable as e:
        logger.error("Termin-Schreibvorgang fehlgeschlagen: %s", e)
        return jsonify({"error": "Kalender nicht erreichbar"}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


def _aktivitaet_label(art):
    """Anzeige-Label einer Aktivitäts-Art für den Event-Titel (PLAN-11).

    Delegiert an `plan.aktivitaeten` — den gemeinsamen Aktivitäts-Katalog
    (Refs #101).
    """
    return aktivitaeten_mod.label_fuer_art(art)


# ============================================================
#  Admin: Reload (#140, EC-21)
# ============================================================
#
# Seit DCOMP-2 / #210 liest der Plan-Buddy `plan.json` pro Aufruf frisch von
# Disk (`_current_config()`). KAV-Schreibvorgänge (Eltern-Chat „Kalender
# verbinden", EC-21) werden damit ohne diesen Endpoint sichtbar — der
# Reload-Endpoint ist NICHT MEHR NÖTIG, damit Skill-Schreibvorgänge wirken.
#
# Er bleibt aber als **expliziter, loggbarer Reload-Marker** für das
# Skill-Service-Reload-Pattern (EC-21): ein Skill kann nach seinem
# Schreibvorgang den Endpoint aufrufen, um ein klares Log-Ereignis zu erzeugen
# („plan.json reloaded: kalender_id=…, slots=…"), und er aktualisiert den
# Last-Known-Good-Snapshot in `runtime["config"]` (sodass spätere
# Read-Fehler den frisch geschriebenen Stand als Fallback haben).
#
# Die Zugangsdaten (OAuth-Client + Refresh-Token) brauchen ebenfalls keinen
# expliziten Reload: `zugangsdaten.Zugangsdaten.get(...)` liest pro Aufruf
# frisch von Disk (ZD-4) — KAV-geschriebene Tokens sind ab dem nächsten
# Aufruf sichtbar.
#
# Drei harte Eigenschaften des Endpoints — analog Router-Reload-Endpoint
# (PR #149):
#   1. Loopback-only (`request.remote_addr` ∈ {127.0.0.1, ::1}). Andere
#      Aufrufer bekommen HTTP 403.
#   2. Atomar (E-RELOAD-1 / ROU-25): bei Parse-Fehler bleibt der alte Snapshot
#      unberührt — Config UND Transport. Die Übernahme passiert erst,
#      nachdem die neue Config erfolgreich gebaut wurde.
#   3. nginx-Origin leitet `/api/v1/<komponente>/admin/...` NICHT weiter —
#      die nginx-Conf ist von PR #149 bereits gehärtet. Der Loopback-Guard
#      hier ist die zweite Schicht.


class PlanReloadError(Exception):
    """Wird vom strikten Reload-Pfad (#140) geworfen, wenn plan.json nicht
    gelesen oder geparst werden konnte. Der Start-Pfad (main) lässt
    ConfigError nach oben durch — der Reload-Pfad fängt ihn ab und gibt ihn
    als PlanReloadError zurück, sodass der Endpoint einen klaren Fehler
    serialisieren kann."""


def reload_plan_config():
    """Aktualisiert den Last-Known-Good-Snapshot aus plan.json (#140,
    E-RELOAD-1 / ROU-25). Expliziter Reload-Marker — die Lookup-Sichtbarkeit hängt
    seit DCOMP-2 (#210) NICHT mehr davon ab.

    Liefert die neue `Config` bei Erfolg. Wirft PlanReloadError, wenn der
    Pfad nicht konfiguriert ist oder die Datei nicht parsbar ist — in dem
    Fall bleibt `runtime["config"]` und `runtime["transport"]` unverändert
    (Atomarität).

    Der Transport wird über die `transport_factory` neu gebaut — sonst
    bliebe die alte `kalender_id` an die alte Transport-Instanz gebunden.
    Tests dürfen `transport_factory=None` lassen; dann tauscht der Reload
    nur die Config aus und der Test-Transport bleibt stehen (das ist genau
    das, was die Test-Naht braucht)."""
    path = runtime.get("config_path")
    if not path:
        raise PlanReloadError("kein plan.json-Pfad konfiguriert")
    try:
        new_cfg = config_mod.resolve(path)
    except config_mod.ConfigError as e:
        raise PlanReloadError("plan.json nicht ladbar: %s" % e) from e
    except OSError as e:
        raise PlanReloadError("plan.json nicht lesbar (%s): %s" % (path, e)) from e

    # Neuer Transport mit ggf. geänderter kalender_id — erst NACH erfolg-
    # reichem Config-Parse, damit ein zerschossenes plan.json den alten
    # Transport nicht kippt.
    factory = runtime.get("transport_factory")
    new_transport = factory(new_cfg) if factory is not None else runtime["transport"]

    # Atomare Übernahme — bis hierher hat kein globaler Slot sich geändert.
    runtime["config"] = new_cfg
    runtime["transport"] = new_transport
    logger.info("plan.json neu geladen: kalender_id=%s, slots=%d",
                new_cfg.kalender_id, len(new_cfg.slots))
    return new_cfg


# Zulässige Aufrufer-Adressen — IPv4- und IPv6-Loopback. Der Flask-
# Testclient setzt per Default 127.0.0.1; ein lokaler `curl` auf den Server
# je nach Stack auch ::1. Beide sind dasselbe physische Interface.
_RELOAD_ALLOWED_REMOTES = {"127.0.0.1", "::1"}


def _is_loopback(remote_addr):
    """Ein Aufruf gilt als loopback, wenn er aus 127.0.0.1 oder ::1 stammt.
    Reverse-Proxy-Forwarding (X-Forwarded-For) wird absichtlich ignoriert —
    der Loopback-Guard prüft, wer wirklich angeklopft hat, nicht was der
    Header behauptet."""
    return remote_addr in _RELOAD_ALLOWED_REMOTES


@app.route("/api/v1/plan/admin/reload", methods=["POST"])
def admin_reload():
    if not _is_loopback(request.remote_addr or ""):
        # 403 statt 404, damit Bedienfehler im LAN sichtbar sind: ein
        # Aufruf aus dem Netz bekommt ein klares „nicht erlaubt", kein
        # diffuses „gibts nicht".
        logger.warning("admin/reload abgelehnt: remote_addr=%s",
                       request.remote_addr)
        return jsonify({
            "reloaded": False,
            "error":    "nur 127.0.0.1 darf den Endpoint erreichen",
        }), 403
    try:
        new_cfg = reload_plan_config()
    except PlanReloadError as e:
        # Atomarität: alter State steht unverändert weiter — der Plan-
        # Buddy beantwortet Requests nach dem Fehler wie vor dem Aufruf.
        logger.warning("admin/reload fehlgeschlagen: %s", e)
        return jsonify({
            "reloaded": False,
            "error":    str(e),
        }), 500
    return jsonify({
        "reloaded": True,
        "details":  ("plan.json reloaded (kalender_id=%s, slots=%d)"
                     % (new_cfg.kalender_id, len(new_cfg.slots))),
    }), 200


# ============================================================
#  Admin: kalender_id setzen (PLAN-32, #341)
# ============================================================
#
# KAV (Kalender-verbinden-Skill) schreibt die gewählte `kalender_id` nicht
# mehr direkt in `plan/plan.json` (Cross-Service-FS-Write), sondern ruft
# diesen Endpoint — der Plan-Buddy ist Eigentümer seiner Datei (APP-3).
#
# Drei harte Eigenschaften — analog admin/reload (#140):
#   1. Loopback-only (127.0.0.1/::1, sonst 403). nginx leitet
#      `/api/v1/<komponente>/admin/...` nicht weiter (gehärtet seit #149).
#   2. Atomar: Plan-Buddy liest plan.json, setzt nur den `kalender_id`-
#      Schlüssel (Temp + os.replace; alle anderen Werte byte-gleich) und
#      übernimmt den neuen Stand in-process (Config + Transport via
#      reload_plan_config). Bei Fehler bleibt der alte Snapshot unberührt.
#   3. 400 bei fehlendem/leerem `kalender_id`, 200 bei Erfolg.

def _write_kalender_id(path, kalender_id):
    """Schreibt nur den `kalender_id`-Schlüssel atomar in plan.json.

    Liest die Datei, setzt den Schlüssel, schreibt über Temp + os.replace.
    Alle anderen Felder bleiben byte-gleich.

    Wirft OSError oder ValueError bei I/O- oder Parse-Fehlern — der Aufrufer
    (admin_kalender) fängt sie und gibt einen 500 zurück.
    """
    path_str = str(path)
    with open(path_str, encoding="utf-8") as f:
        data = f.read()
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("plan.json-Wurzel ist kein JSON-Objekt")
    obj["kalender_id"] = kalender_id
    target_dir = os.path.dirname(os.path.abspath(path_str))
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".plan.", suffix=".json.tmp", dir=target_dir)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path_str)
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


@app.route("/api/v1/plan/admin/kalender", methods=["PUT"])
def admin_kalender():
    """PLAN-32: setzt die `kalender_id` im Plan-Buddy (KAV → dieser Endpoint).

    Body: { "kalender_id": "<google-id>" }.
    Loopback-only (sonst 403). Atomar: nur `kalender_id` in plan.json;
    in-process-Übernahme über reload_plan_config(). 400/403/200.
    """
    if not _is_loopback(request.remote_addr or ""):
        logger.warning("admin/kalender abgelehnt: remote_addr=%s",
                       request.remote_addr)
        return jsonify({
            "ok":    False,
            "error": "nur 127.0.0.1 darf den Endpoint erreichen",
        }), 403

    body = request.get_json(silent=True) or {}
    kalender_id = body.get("kalender_id")
    if not kalender_id:
        return jsonify({
            "ok":    False,
            "error": "kalender_id ist Pflicht und darf nicht leer sein",
        }), 400

    path = runtime.get("config_path")
    if not path:
        return jsonify({
            "ok":    False,
            "error": "kein plan.json-Pfad konfiguriert",
        }), 500

    try:
        _write_kalender_id(path, kalender_id)
    except (OSError, ValueError) as e:
        logger.error("admin/kalender: plan.json konnte nicht geschrieben werden: %s", e)
        return jsonify({
            "ok":    False,
            "error": "plan.json nicht schreibbar: %s" % e,
        }), 500

    # In-process-Übernahme: Config + Transport mit neuer kalender_id neu binden.
    # Gleicher atomarer Pfad wie admin/reload — bei Parse-Fehler bleibt der
    # alte Snapshot unberührt. Da wir gerade erst erfolgreich geschrieben haben,
    # sollte der Parse nicht scheitern; ein Fehler hier gibt 500.
    try:
        new_cfg = reload_plan_config()
    except PlanReloadError as e:
        logger.error("admin/kalender: plan.json geschrieben, aber Reload fehlgeschlagen: %s", e)
        return jsonify({
            "ok":    False,
            "error": "kalender_id geschrieben, In-Process-Reload fehlgeschlagen: %s" % e,
        }), 500

    logger.info("admin/kalender: kalender_id=%s gesetzt", new_cfg.kalender_id)
    return jsonify({"ok": True, "kalender_id": new_cfg.kalender_id}), 200


# ============================================================
#  Entrypoint (PLAN-28)
# ============================================================

logger = logging.getLogger(__name__)

# Runtime-Konfig-Schema (CONFIG-1, #179): nur die nicht-PLAN-28-Werte,
# die der Service-Start braucht — Bind, Log-Level. Slots/Kalender-ID etc.
# leben weiter in plan.json (PLAN-28), das ist eine andere Sache.
RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5020,
    "log_level":   "INFO",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Plan-Buddy-App V1")
    p.add_argument("--config", dest="config_file", default=None,
                   help="Pfad zur plan.json (PLAN-28; sonst $PLAN_CONFIG_FILE / Default)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key", help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_runtime_config(args):
    """Host/Port/Log-Level: Datei < ENV < CLI.

    Datei + ENV kommen vom gemeinsamen `tools.configloader` (CONFIG-1,
    #179). CLI-Flags bleiben Test-Werkzeug (CONFIG-1) und überschreiben
    den Loader-Output.
    """
    cfg = configloader.load(component="plan", schema=RUNTIME_SCHEMA)
    if args.host:      cfg["listen_host"] = args.host
    if args.port:      cfg["listen_port"] = args.port
    if args.log_level: cfg["log_level"]   = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rt = resolved_runtime_config(args)
    # LOG-4 (#166): zentraler Setup statt eigenem basicConfig. Level kommt
    # aus der Runtime-Config (CONFIG-1/CONFIG-2, RUNTIME_SCHEMA).
    logsetup.setup(rt["log_level"])

    # Pfad zur plan.json explizit auflösen — sowohl der erste Lade-Versuch
    # als auch der Reload-Endpoint (#140) nutzen denselben Pfad.
    config_path = (args.config_file
                   or os.environ.get(config_mod.ENV_CONFIG_FILE)
                   or config_mod.DEFAULT_CONFIG_FILE)
    cfg = config_mod.resolve(config_path)
    # DCOMP-1: Personen ueber HTTP von der Familie-Komponente. Der Client
    # haelt nur die Origin-URL — den Personen-Snapshot baut er pro Request
    # frisch (FAM-7).
    familie_client = familie_client_mod.FamilieClient(cfg.familie_origin_url)
    store = Zugangsdaten(resolve_store_path())
    # Naht für #140: der Factory wird im Reload-Pfad mit der frisch
    # geladenen Config aufgerufen und liefert einen Transport, der die
    # ggf. neue kalender_id kennt. Der `store` ist live (ZD-4) und liest
    # OAuth-Daten pro Aufruf frisch von Disk.
    def transport_factory(cfg):
        return kalender_mod.GoogleTransport(store, cfg.kalender_id)
    transport = transport_factory(cfg)
    configure(cfg, registry=None, transport=transport,
              familie_client=familie_client,
              config_path=config_path,
              transport_factory=transport_factory)

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logger.info("Plan-Buddy hört auf %s://%s:%s (kalender=%s, db=%s, familie=%s)",
                scheme, rt["listen_host"], rt["listen_port"],
                cfg.kalender_id, cfg.db_datei, cfg.familie_origin_url)
    app.run(host=rt["listen_host"], port=rt["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
