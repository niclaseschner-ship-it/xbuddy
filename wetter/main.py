#!/usr/bin/env python3
"""Wetter-Buddy-App — HTTP-Schnittstelle + Entrypoint (WETTER-1 … WETTER-22).

Siehe specs/buddies/wetter.md. Der Wetter-Buddy ist die XBuddy-App mit dem
Buddy-Slug `wetter` (WETTER-1). Er besitzt seine Daten (Ort + Garderoben-Regeln,
WETTER-21) und seine Funktion (die Open-Meteo-Anbindung, WETTER-16) und stellt
das Ergebnis über seine Display-View bereit (WETTER-2).

Endpunkte:
  GET /display/wetter/heute              — View `heute`, Diptychon (WETTER-2)
  GET /display/wetter/heute?stage=toddler — Mitwachsen-Stufe (WETTER-4; V1 nur toddler)
  GET /healthz                           — Health-Check (SVC-1)

Service-Topologie wie plan/main.py: eine schlanke eigenständige Flask-App, ein
Geschwister von router/, familie/ und plan/.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, make_response, render_template, request

# Repo-Wurzel auf den Importpfad — die App konsumiert die Library
# `tools.configloader`/`tools.logsetup` (DCOMP-1-Ausnahme: `tools/` ist
# gemeinsamer Bibliotheks-Code).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import configloader, logsetup  # noqa: E402
from tools import familie_client as _familie_client_mod  # noqa: E402
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.initdata.auth_gate import make_require_init_data  # noqa: E402
from tools.service_diagnostics import register_version  # noqa: E402

# Das wetter-Paket wird als Paket importiert, damit die relativen Imports in
# config/meteo/clothing/render greifen — auch wenn main.py direkt gestartet wird.
if __package__:
    from . import config as config_mod
    from . import editor as editor_mod
    from . import meteo as meteo_mod
    from . import palette as palette_mod
    from . import render as render_mod
    from . import store as store_mod
else:  # python3 wetter/main.py
    sys.path.insert(0, _REPO_ROOT)
    from wetter import config as config_mod
    from wetter import editor as editor_mod
    from wetter import meteo as meteo_mod
    from wetter import palette as palette_mod
    from wetter import render as render_mod
    from wetter import store as store_mod


# ============================================================
#  Laufzeit-Zustand
# ============================================================
#
# Wie beim Plan-Buddy (DCOMP-2, Reload-on-Read): `config` ist der
# Last-Known-Good-Snapshot, nicht die Lookup-Wahrheit. Endpoints lesen via
# `_current_config()` pro Aufruf frisch von Disk; der Snapshot dient nur als
# Fallback, wenn ein einzelner Read scheitert (DCOMP-3).
runtime = {
    "config": None,             # wetter.config.Config — Last-Known-Good-Snapshot
    "anbindung": None,          # wetter.meteo.WetterAnbindung (oder Fake in Tests)
    "config_path": None,        # Pfad zur wetter.json — Naht für DCOMP-2
    "anbindung_factory": None,  # cfg -> WetterAnbindung — neu binden, wenn Ort/Stunden wechseln
    "bot_token": None,          # AUTH-3 (#1715): Cookie/tma-Signatur-Key, ENV-Fallback
    "auth_familie_client": None,  # AUTH-3 Test-Naht (get_telegram_ids-Stub)
    "init_data_config": None,   # AUTH-3 tma-Config-Cache
}


# ============================================================
#  AUTH-3 (ESB-1.a/ESB-2, #1715): Datenrouten /api/v1/wetter/regeln hart
# ============================================================
# Die Regeln-Mini-App (seiten-gehostet, ESB-1.a) liest/schreibt über die
# Buddy-Datenrouten — die tragen den HART-Decorator (Cookie ODER tma, 401 ohne;
# AUTH-5-Loopback pass-through). Faithful zum plan/essen/photo-Zwilling über die
# #1625-Factory (make_require_init_data).
_ENV_BOT_TOKEN = "ELTERNCHAT_BOT_TOKEN"
_ENV_FAMILIE_ORIGIN = "WETTER_FAMILIE_ORIGIN"
_FAMILIE_DEFAULT_ORIGIN = "http://127.0.0.1:5010"


def _get_bot_token():
    """Bot-Token aus runtime-Dict (Test-Naht) oder ENV (APP-7)."""
    return runtime.get("bot_token") or os.environ.get(_ENV_BOT_TOKEN)


def _get_familie_client():
    """AUTH-3-FAM-Client — Test-Naht `configure(auth_familie_client=...)` oder
    produktiv `FamilieClient` aus ENV `WETTER_FAMILIE_ORIGIN` (Personen/Telegram-IDs)."""
    cached = runtime.get("auth_familie_client")
    if cached is not None:
        return cached
    origin = os.environ.get(_ENV_FAMILIE_ORIGIN, _FAMILIE_DEFAULT_ORIGIN)
    return _familie_client_mod.FamilieClient(origin_url=origin)


def _get_init_data_config():
    """Tma-Config (`max_age_seconds`) — gecacht im runtime-Dict oder frisch."""
    cfg = runtime.get("init_data_config")
    if cfg is None:
        cfg = _init_data_mod.load_config()
        runtime["init_data_config"] = cfg
    return cfg


_AUTH_401_HTML = (
    "<!doctype html>\n<html lang=\"de\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    "<title>Gerät neu verbinden</title></head>"
    "<body style=\"font-family:system-ui,sans-serif;max-width:32rem;"
    "margin:3rem auto;padding:0 1rem;line-height:1.5\">"
    "<h1>Dieses Gerät muss neu verbunden werden.</h1>"
    "<p>Öffne im Familien-Bot den Pairing-Befehl und folge dem Link auf diesem "
    "Gerät.</p></body></html>"
)


def _auth_401():
    """AUTH-8: 401 mit HTML-Anweisungsseite (nicht roher Status-Code)."""
    resp = make_response(_AUTH_401_HTML, 401)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


require_init_data = make_require_init_data(
    get_bot_token=_get_bot_token,
    get_familie_client=_get_familie_client,
    get_init_data_config=_get_init_data_config,
    auth_401=_auth_401,
)


def configure(cfg, anbindung, config_path=None, anbindung_factory=None,
              bot_token=None, auth_familie_client=None):
    """Setzt Konfiguration und Wetter-Anbindung (Test-Naht, WETTER-24).

    `anbindung` ist die Test-Naht: in Produktion eine WetterAnbindung mit
    OpenMeteoTransport, in Tests eine mit einem Fake-Transport.

    `config_path` ist die Naht für DCOMP-2 (Reload-on-Read): wird er gesetzt,
    liest der Wetter-Buddy `wetter.json` pro Aufruf frisch von Disk — eine
    geänderte Garderoben-Regel oder ein neuer Ort werden ohne Service-Restart
    sichtbar. Ohne `config_path` bleibt das übergebene `cfg` die Quelle
    (Test-Modus, kein Disk-IO).

    `anbindung_factory(cfg) -> anbindung` wird im Reload-on-Read-Pfad
    aufgerufen, sobald sich Ort oder Tageszeit-Stunden gegenüber der zuletzt
    gebauten Anbindung ändern. In Tests bleibt der Default `None` — die Tests
    setzen die Anbindung direkt.
    """
    runtime["config"] = cfg
    runtime["anbindung"] = anbindung
    runtime["config_path"] = config_path
    runtime["anbindung_factory"] = anbindung_factory
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if auth_familie_client is not None:
        runtime["auth_familie_client"] = auth_familie_client


def _current_config():
    """DCOMP-2 Reload-on-Read: liefert die wetter.json-Config pro Aufruf frisch.

    Scheitert Read oder Parse, fällt der Aufruf auf den Last-Known-Good-Snapshot
    in `runtime["config"]` zurück (DCOMP-3) — der Kiosk kippt bei einem kurzen
    Race nicht in einen leeren Zustand. Ohne konfigurierten `config_path`
    (Tests) wird der Snapshot direkt zurückgegeben.
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
    runtime["config"] = new_cfg
    return new_cfg


def _anbindung(cfg):
    """Baut/liefert die Wetter-Anbindung passend zur aktuellen Config (DCOMP-2).

    Wechselt der Ort oder die Tageszeit-Stunden in wetter.json, muss die
    Anbindung die neuen Werte kennen. Steht eine `anbindung_factory` bereit
    (Live-Pfad), bauen wir sie bei Bedarf neu; der Snapshot in
    `runtime["anbindung"]` bleibt als Fallback. Tests ohne Factory behalten die
    fest gesetzte Test-Anbindung (Test-Naht, WETTER-24).
    """
    anbindung = runtime["anbindung"]
    factory = runtime.get("anbindung_factory")
    if factory is None:
        return anbindung
    # Signatur, die einen Neu-Bau erzwingt: Ort-Koordinaten + Tageszeit-Stunden
    # + Sonnencreme-Schwelle. Ändert sich eine, ist die alte Anbindung stale.
    sig = (cfg.ort.lat, cfg.ort.lon, cfg.stunde_morgens,
           cfg.stunde_mittags, cfg.sunscreen_uv)
    if getattr(anbindung, "_wetter_sig", None) != sig:
        anbindung = factory(cfg)
        anbindung._wetter_sig = sig
        runtime["anbindung"] = anbindung
    return anbindung


# ============================================================
#  Flask-App
# ============================================================

# URL-13: statische Assets des Wetter-Buddys liegen in seinem Display-
# Namensraum (`/display/wetter/static/...`), damit sie hinter der einen Origin
# (URL-12) geroutet werden — der Flask-Default `/static` läge außerhalb der
# URL-1-Prefixe.
app = Flask(__name__, static_url_path="/display/wetter/static")


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


def _zielTag(cfg, jetzt):
    """Der angezeigte Tag nach dem Abend-Rollover (WETTER-6).

    Vor der Abend-Rollover-Zeit: heute. Ab der Abend-Zeit: morgen — damit man
    abends die Kleidung für den nächsten Tag herauslegen kann (E-WETTER-9).
    Liefert (tag, fuer_morgen).
    """
    h, m = cfg.rollover_abend
    rollover = time(hour=h, minute=m)
    if jetzt.time() >= rollover:
        return jetzt.date() + timedelta(days=1), True
    return jetzt.date(), False


def _jetzt(cfg):
    """Aktuelle Zeit in der Familien-Zeitzone (WETTER-6). Test-Naht über `?_now=`
    bleibt bewusst aus — Tests rufen `_zielTag`/`baue_view` direkt mit einem
    festen `jetzt` auf (WETTER-24)."""
    return datetime.now(ZoneInfo(cfg.zeitzone))


@app.route("/display/wetter/heute", methods=["GET"])
def heute():
    """View `heute` als Diptychon, Stufe `toddler` (WETTER-2, WETTER-4).

    `?stage=toddler` (Default ohne Parameter). V1 implementiert nur `toddler`
    (WETTER-4, E-WETTER-4); ein anderer Stage-Wert wird auf `toddler`
    zurückgesetzt — die View bleibt nutzbar, kein Fehler vor dem Kind.

    DCOMP-2: wetter.json pro Request frisch von Disk (`_current_config()`) —
    eine geänderte Garderoben-Regel oder ein neuer Ort wirken ohne Restart.
    """
    cfg = _current_config()
    stage = request.args.get("stage", "toddler")
    if stage != "toddler":
        logger.info("stage=%r nicht implementiert (V1 nur toddler, WETTER-4) "
                    "— falle auf toddler zurück", stage)
        stage = "toddler"

    tag, fuer_morgen = _zielTag(cfg, _jetzt(cfg))
    morgens, mittags = _anbindung(cfg).fuer_tag(tag)
    view = render_mod.baue_view(cfg, morgens, mittags, fuer_morgen=fuer_morgen)

    return render_template("wetter_heute.html", stage=stage, view=view)


# ============================================================
#  Garderoben-Editor (WETTER-26 … WETTER-30)
# ============================================================
#
# Eltern-seitige Editor-Seite + interner Save-Handler im eigenen wetter-Display-
# Namespace auf derselben Origin (OPEN-WETTER-I — ENTSCHIEDEN, #328). Schutz =
# Netz-Grenze (WETTER-31, LAN/Tailscale, kein Port-Forwarding) — kein Login,
# kein Token, kein separater Bind. Die Seite ist kein Kiosk-View und von
# WETTER-25 ausgenommen (Scrollen/Menü erlaubt, hochkant am Handy).


def _lade_rohstand():
    """Lädt wetter.json als Roh-dict (read-only Felder + wardrobe), DCOMP-2.

    Der Editor (WETTER-27) und der Save-Handler (WETTER-30) arbeiten auf dem
    rohen wetter.json — sie tragen Ort/Schwellen/Hinweise unverändert weiter
    (WETTER-28). Wird pro Request frisch von Disk gelesen (`config_path`, die
    DCOMP-2-Naht). Fehlt der Pfad (Tests ohne Disk-IO) oder die Datei, liefert
    der Helfer ein leeres dict — der Editor zeigt dann eine leere Matrix.
    """
    path = runtime.get("config_path")
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("wetter.json nicht lesbar für Editor (%s): %s", path, e)
        return {}
    return data if isinstance(data, dict) else {}


@app.route("/display/wetter/regeln", methods=["GET", "POST"])
def regeln():
    """Garderoben-Editor-Seite: GET liefert Übersicht + Fokus (WETTER-26/27);
    POST validiert + schreibt die Matrix atomar (WETTER-30).

    GET: Zeigt alle Regeln in ihrer Reihenfolge (erste passende gewinnt,
    WETTER-14) mit read-only Bedingung und editierbaren Kleidungs-Sets aus der
    kuratierten Palette (WETTER-28/29). Keine Live-Wetter-Daten — nur Config.

    POST: Nimmt die editierte Matrix als JSON-Body, validiert gegen die
    kuratierte Palette und den frisch geladenen Stand (WETTER-28/30) und
    schreibt `wetter.json` atomar auf `runtime['config_path']` — der Kiosk
    übernimmt per DCOMP-2 ohne Restart. Ungültig → 422 + Begründung, Datei
    unverändert. Ohne konfigurierten `config_path` (kein Ziel) → 409.

    GET + POST auf verbfreiem Pfad (URL-2).
    """
    if request.method == "POST":
        path = runtime.get("config_path")
        if not path:
            return jsonify({"ok": False, "fehler": "Kein wetter.json-Pfad konfiguriert"}), 409
        matrix = request.get_json(silent=True)
        if matrix is None:
            return jsonify({"ok": False, "fehler": "Kein JSON-Body"}), 400
        try:
            store_mod.speichere_garderobe(
                path, matrix, palette_mod, geladener_stand=_lade_rohstand())
        except store_mod.ValidierungsFehler as e:
            return jsonify({"ok": False, "fehler": str(e)}), 422
        except store_mod.StoreError as e:
            logger.error("Garderobe-Save fehlgeschlagen: %s", e)
            return jsonify({"ok": False, "fehler": str(e)}), 500
        return jsonify({"ok": True})
    view = editor_mod.baue_view(_lade_rohstand(), palette_mod)
    return render_template("wetter_regeln.html", view=view)


# ============================================================
#  AUTH-3-Datenrouten (#1715, ESB-1.a/ESB-2): die seiten-gehostete Regeln-
#  Mini-App liest/schreibt hier. Hart (Cookie ODER tma, 401 ohne; Loopback pass).
# ============================================================
@app.route("/api/v1/wetter/regeln", methods=["GET"])
@require_init_data
def api_regeln_get():
    """GET: die Garderoben-View als JSON (Palette + read-only Bedingungen +
    editierbare Sets, WETTER-28/29) — dieselbe `baue_view`-Quelle wie das
    (abzulösende) Server-Template, nur als Daten für die JS-Shell."""
    return jsonify(editor_mod.baue_view(_lade_rohstand(), palette_mod))


@app.route("/api/v1/wetter/regeln", methods=["POST"])
@require_init_data
def api_regeln_post():
    """POST: editierte Matrix validieren + `wetter.json` atomar schreiben
    (WETTER-30); Kiosk übernimmt per DCOMP-2 ohne Restart. Ungültig → 422,
    Datei unverändert; kein Ziel → 409 (identisch zum bisherigen POST)."""
    path = runtime.get("config_path")
    if not path:
        return jsonify({"ok": False, "fehler": "Kein wetter.json-Pfad konfiguriert"}), 409
    matrix = request.get_json(silent=True)
    if matrix is None:
        return jsonify({"ok": False, "fehler": "Kein JSON-Body"}), 400
    try:
        store_mod.speichere_garderobe(
            path, matrix, palette_mod, geladener_stand=_lade_rohstand())
    except store_mod.ValidierungsFehler as e:
        return jsonify({"ok": False, "fehler": str(e)}), 422
    except store_mod.StoreError as e:
        logger.error("Garderobe-Save (api) fehlgeschlagen: %s", e)
        return jsonify({"ok": False, "fehler": str(e)}), 500
    return jsonify({"ok": True})


# ============================================================
#  Entrypoint (WETTER-22)
# ============================================================

logger = logging.getLogger(__name__)

# Runtime-Konfig-Schema (CONFIG-1): nur die Service-Start-Werte — Bind,
# Log-Level. Ort/Regeln/Tageszeiten leben in wetter.json (WETTER-21).
# Listen-Port 5030 (belegt in conventions/ports.md, PORT-2, `xbuddy-wetter`).


# ── Health-Check (SVC-1) ─────────────────────────────────────────────────

@app.route("/healthz", methods=["GET"])
def healthz():
    """SVC-1: Health-Endpoint — liefert immer 200 + OK."""
    return jsonify({"ok": True}), 200


RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5030,
    "log_level":   "INFO",
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Wetter-Buddy-App V1")
    p.add_argument("--config", dest="config_file", default=None,
                   help="Pfad zur wetter.json (WETTER-21; sonst $WETTER_CONFIG_FILE / Default)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key", help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_runtime_config(args):
    """Host/Port/Log-Level: Datei < ENV < CLI (CONFIG-1/CONFIG-5).

    Datei + ENV kommen vom gemeinsamen `tools.configloader`. CLI-Flags bleiben
    Test-Werkzeug und überschreiben den Loader-Output.
    """
    cfg = configloader.load(component="wetter", schema=RUNTIME_SCHEMA)
    if args.host:      cfg["listen_host"] = args.host
    if args.port:      cfg["listen_port"] = args.port
    if args.log_level: cfg["log_level"]   = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rt = resolved_runtime_config(args)
    logsetup.setup(rt["log_level"])

    config_path = (args.config_file
                   or os.environ.get(config_mod.ENV_CONFIG_FILE)
                   or config_mod.DEFAULT_CONFIG_FILE)
    cfg = config_mod.resolve(config_path)

    def anbindung_factory(cfg):
        transport = meteo_mod.OpenMeteoTransport(cfg.ort.lat, cfg.ort.lon)
        return meteo_mod.WetterAnbindung(
            transport, cfg.stunde_morgens, cfg.stunde_mittags, cfg.sunscreen_uv)

    anbindung = anbindung_factory(cfg)
    configure(cfg, anbindung, config_path=config_path,
              anbindung_factory=anbindung_factory)

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logger.info("Wetter-Buddy hört auf %s://%s:%s (ort=%s, lat=%s, lon=%s)",
                scheme, rt["listen_host"], rt["listen_port"],
                cfg.ort.name or "(ohne Name)", cfg.ort.lat, cfg.ort.lon)
    app.run(host=rt["listen_host"], port=rt["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
