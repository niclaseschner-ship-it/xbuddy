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
from zugangsdaten import Zugangsdaten, resolve_store_path  # noqa: E402

# Das plan-Paket wird als Paket importiert, damit die relativen Imports in
# config/db/kalender/render greifen — auch wenn main.py direkt gestartet wird.
if __package__:
    from . import config as config_mod
    from . import db as db_mod
    from . import kalender as kalender_mod
    from . import render as render_mod
else:  # python3 plan/main.py
    sys.path.insert(0, _REPO_ROOT)
    from plan import config as config_mod
    from plan import db as db_mod
    from plan import kalender as kalender_mod
    from plan import render as render_mod


# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Der Entrypoint befüllt `runtime`; Tests setzen es direkt über configure().
runtime = {
    "config": None,            # plan.config.Config
    "registry": registry_mod.Registry(),
    "transport": None,         # plan.kalender.GoogleTransport (oder Fake in Tests)
}


def configure(cfg, registry, transport):
    """Setzt Konfiguration, Familien-Registry und Kalender-Transport.

    `transport` ist die Test-Naht (PLAN-29): in Produktion ein
    GoogleTransport, in Tests ein Fake.
    """
    runtime["config"] = cfg
    runtime["registry"] = registry
    runtime["transport"] = transport


def _kalender():
    """Baut die Kalender-Anbindung aus dem laufenden Transport (PLAN-15…20)."""
    return kalender_mod.Kalender(
        runtime["transport"], runtime["registry"].alle())


def _db():
    """Öffnet die SQLite-Verbindung (PLAN-9). Pro Request frisch (V1)."""
    return db_mod.connect(runtime["config"].db_datei)


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)

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
    cfg = runtime["config"]
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
    try:
        view = render_mod.baue_view(
            cfg, conn, _kalender(), runtime["registry"],
            anker, anzahl_tage, mit_terminen)
    finally:
        conn.close()

    personen = runtime["registry"].alle()
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
    slot = runtime["config"].slot(body["slot"])
    if slot is None or not slot.ist_erwachsenen_slot():
        return jsonify({"error": "kein Erwachsenen-Slot: %r" % body["slot"]}), 400
    person_id = body.get("person_id")
    if person_id is not None and runtime["registry"].get(person_id) is None:
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
        kind = runtime["registry"].get(kind_id)
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
    """Anzeige-Label einer Aktivitäts-Art für den Event-Titel (PLAN-11)."""
    return {
        "klettern": "Klettern", "kreativ": "Kreativ", "schwimmen": "Schwimmen",
        "spielplatz": "Spielplatz", "musik": "Musik", "ausflug": "Ausflug",
        "geburtstag": "Geburtstag", "petrabredung": "Petrabredung",
        "waldgang": "Waldgang",
    }.get(art, art.capitalize() if art else art)


# ============================================================
#  Entrypoint (PLAN-28)
# ============================================================

logger = logging.getLogger(__name__)

DEFAULTS = {
    "listen_host": "127.0.0.1",
    "listen_port": 5020,
    "log_level": "INFO",
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
    """Host/Port/Log-Level: Defaults < ENV < CLI."""
    cfg = dict(DEFAULTS)
    if "PLAN_HOST" in os.environ:      cfg["listen_host"] = os.environ["PLAN_HOST"]
    if "PLAN_PORT" in os.environ:      cfg["listen_port"] = int(os.environ["PLAN_PORT"])
    if "PLAN_LOG_LEVEL" in os.environ: cfg["log_level"] = os.environ["PLAN_LOG_LEVEL"]
    if args.host:      cfg["listen_host"] = args.host
    if args.port:      cfg["listen_port"] = args.port
    if args.log_level: cfg["log_level"] = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rt = resolved_runtime_config(args)
    logging.basicConfig(
        level=getattr(logging, rt["log_level"].upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s")

    cfg = config_mod.resolve(args.config_file)
    registry = registry_mod.load(args.registry)
    store = Zugangsdaten(resolve_store_path())
    transport = kalender_mod.GoogleTransport(store, cfg.kalender_id)
    configure(cfg, registry, transport)

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
