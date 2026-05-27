#!/usr/bin/env python3
"""Plan-Buddy-App — HTTP-Schnittstellen + Entrypoint (PLAN-1 … PLAN-29).

Siehe specs/buddies/plan.md. Der Plan-Buddy ist die XBuddy-App mit dem
Buddy-Slug `plan` (PLAN-1). Er besitzt seine Daten (Petrantwortlichkeiten,
plan.db) und seine Funktion (Kalender-Anbindung) und stellt beides über
Schnittstellen bereit (PLAN-21/22/23).

Endpunkte:
  GET /display/plan/woche               — View `woche`, Lese-Kind (PLAN-2/3/21)
  GET /display/plan/woche?ansicht=klein — View `woche`, Kleinkind (PLAN-3)
  GET /display/plan/woche?ab=<iso>      — Anker verschieben (PLAN-4)
  PUT /api/v1/plan/zuteilung            — Erwachsenen-Slot zuweisen (PLAN-7/8)
  PUT|DELETE /api/v1/plan/aktivitaet    — Kind-Aktivität setzen/löschen (PLAN-11)
  GET|PUT /api/v1/plan/termine          — Termin-Schnittstelle für Apps (PLAN-22)

Service-Topologie wie familie/main.py: eine schlanke eigenständige Flask-App,
ein Geschwister von router/ und familie/.
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta

from flask import Flask, jsonify, render_template, request

# Repo-Wurzel auf den Importpfad — die App konsumiert die Public-API der
# zentralen Komponenten `zugangsdaten` (PLAN-16) und `familie` (PLAN-19).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from familie import registry as registry_mod  # noqa: E402
from tools import configloader, logsetup  # noqa: E402
from zugangsdaten import Zugangsdaten, resolve_store_path  # noqa: E402

# Das plan-Paket wird als Paket importiert, damit die relativen Imports in
# config/db/kalender/render greifen — auch wenn main.py direkt gestartet wird.
if __package__:
    from . import aktivitaeten as aktivitaeten_mod
    from . import config as config_mod
    from . import db as db_mod
    from . import kalender as kalender_mod
    from . import render as render_mod
else:  # python3 plan/main.py
    sys.path.insert(0, _REPO_ROOT)
    from plan import aktivitaeten as aktivitaeten_mod
    from plan import config as config_mod
    from plan import db as db_mod
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
# E-RELOAD-1).
runtime = {
    "config": None,            # plan.config.Config — Last-Known-Good-Snapshot
    "registry": registry_mod.Registry(),  # nur Test-/Fallback-Quelle
    "registry_path": None,     # Live: Pfad zur familie.json — Quelle des Wahren Stands
    "transport": None,         # plan.kalender.GoogleTransport (oder Fake in Tests)
    "config_path": None,       # Pfad zur plan.json — Naht für DCOMP-2 + Reload-Endpoint (#140)
    "transport_factory": None, # cfg -> transport — neu binden, wenn kalender_id wechselt
}


def configure(cfg, registry, transport, registry_path=None,
              config_path=None, transport_factory=None):
    """Setzt Konfiguration, Familien-Registry und Kalender-Transport.

    `transport` ist die Test-Naht (PLAN-29): in Produktion ein
    GoogleTransport, in Tests ein Fake.

    `registry_path` ist die Naht für den Live-Reload (Bugfix
    Familie-Registry-Konsistenz): wird er gesetzt, lädt der Plan-Buddy die
    Registry bei jedem Endpoint frisch aus der Datei — sodass extern (z. B.
    durch FAA über den Eltern-Chat-Bot) angelegte Personen ohne Service-
    Restart sichtbar sind. Tests übergeben heute nur das in-memory-Objekt;
    bleibt `registry_path=None`, ist das `registry`-Objekt die feste Quelle.

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
    runtime["registry_path"] = registry_path
    runtime["transport"] = transport
    runtime["config_path"] = config_path
    runtime["transport_factory"] = transport_factory


def _aktuelle_registry():
    """Liefert die aktuelle Familien-Registry für genau diesen Request.

    Live (mit `registry_path`): pro Request frisch aus `familie.json` —
    extern angelegte Personen sind ohne Restart sichtbar. Heute ist die
    Familie winzig (≤10 Personen), JSON-Disk-IO unter 1 ms. Kein
    mtime-Cache (eigenes Ticket, falls je teurer).
    Test/in-memory (ohne `registry_path`): das übergebene Registry-Objekt
    bleibt die Quelle.
    """
    path = runtime.get("registry_path")
    if path is None:
        return runtime["registry"]
    return registry_mod.load(path)


def _current_config():
    """DCOMP-2 Reload-on-Read: liefert die plan.json-Config pro Aufruf
    frisch von Disk (#210, Refs #166).

    Eltern-Chat-Skills schreiben Cross-Service in `plan.json` (KAV — Kalender
    verbinden, EC-21). Der lesende Plan-Buddy muss den neuen Stand ohne
    Service-Restart und ohne Admin-Reload-Aufruf sehen — sonst zeigt er den
    alten Kalender, obwohl KAV bereits eine neue `kalender_id` geschrieben hat.

    Fehlertoleranz (gleicher atomarer Geist wie der Admin-Reload, E-RELOAD-1):
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

    DCOMP-2 (#210): `db_datei` kommt aus dem frisch gelesenen plan.json —
    falls ein Onboarding-Schritt das Datei-Verzeichnis migriert, wirkt das
    ohne Service-Restart.
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
        neue_id = kalender.event_anlegen(titel, date.fromisoformat(datum), ganztags=True)
        return jsonify({"ok": True, "action": "created", "event_id": neue_id})
    except kalender_mod.CalendarUnavailable as e:
        # PLAN-20: Schreib-Misserfolg ist klar erkennbar.
        logger.error("Aktivitäts-Schreibvorgang fehlgeschlagen: %s", e)
        return jsonify({"error": "Kalender nicht erreichbar"}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/v1/plan/termine", methods=["GET", "PUT"])
def api_termine():
    """Termin-Schnittstelle für andere XBuddy-Apps (PLAN-22).

    GET ?ab=<iso>&tage=<n>: liefert die normalisierten Termine des Zeitraums.
    PUT-Body: { titel, datum[, event_id] } — legt einen ganztägigen Termin an
    oder ändert seinen Titel. Der Familien-Kalender ist nur über diese
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
        datum = body.get("datum")
        if not datum:
            return jsonify({"error": "datum ist Pflicht"}), 400
        neue_id = kalender.event_anlegen(titel, date.fromisoformat(datum), ganztags=True)
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
#   2. Atomar (E-RELOAD-1): bei Parse-Fehler bleibt der alte Snapshot
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
    E-RELOAD-1). Expliziter Reload-Marker — die Lookup-Sichtbarkeit hängt
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
    p.add_argument("--registry", default="familie/familie.json",
                   help="Pfad zur Familien-Registry-Datei (FAM-9)")
    p.add_argument("--fotos", dest="foto_verzeichnis",
                   help="Foto-Verzeichnis der Registry (FAM-9)")
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
    registry = registry_mod.load(args.registry)
    store = Zugangsdaten(resolve_store_path())
    # Naht für #140: der Factory wird im Reload-Pfad mit der frisch
    # geladenen Config aufgerufen und liefert einen Transport, der die
    # ggf. neue kalender_id kennt. Der `store` ist live (ZD-4) und liest
    # OAuth-Daten pro Aufruf frisch von Disk.
    def transport_factory(cfg):
        return kalender_mod.GoogleTransport(store, cfg.kalender_id)
    transport = transport_factory(cfg)
    configure(cfg, registry, transport,
              registry_path=args.registry,
              config_path=config_path,
              transport_factory=transport_factory)

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logger.info("Plan-Buddy hört auf %s://%s:%s (kalender=%s, db=%s)",
                scheme, rt["listen_host"], rt["listen_port"],
                cfg.kalender_id, cfg.db_datei)
    app.run(host=rt["listen_host"], port=rt["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
