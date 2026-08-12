#!/usr/bin/env python3
"""Familien-Registry — HTTP-Schnittstelle + Entrypoint.

Siehe specs/platform/familie.md (Refs #38).

Service-Topologie (Impl-Entscheidung, FAM bewusst offen): die Registry läuft
als schlanke eigenständige Flask-App — ein Geschwister von router/ und
eltern-chat/. KEIN auf Vorrat gebauter Dienst-Verbund: die App kann allein
starten, und ihre Endpunkte sind über `app` als Blueprint-loses Flask-Objekt
auch von einem späteren Mit-Host importierbar. Mehr braucht V1 nicht.

Endpunkte:
  GET  /api/v1/familie/personen              — alle Personen (FAM-7)
  GET  /api/v1/familie/personen/<id>         — eine Person je id (FAM-7)
  GET  /api/v1/familie/foto/<id>             — Profilfoto, 200/404 (FAM-8)
  POST /api/v1/familie/personen              — Person anlegen (FAM-12)
  POST /api/v1/familie/personen/<id>/foto    — Profilfoto setzen (FAM-13)
  GET  /healthz                              — Health-Check (SVC-1)
"""

import argparse
import logging
import os
import sys
import threading

from flask import Flask, jsonify, make_response, request, send_file

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
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.initdata.auth_gate import (  # noqa: E402
    make_require_dual_gate,
    make_require_init_data,
)
from tools.service_diagnostics import register_version  # noqa: E402

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
    # MAD-7 / T708-C: Mini-App-Auth (Test-Naht; im Produktiv-Betrieb aus ENV).
    "bot_token":        None,
    "init_data_config": None,
    # T1638: familie_client-Doppel für Tests (None → lokaler Direkt-Read, s. u.)
    "familie_client":   None,
}


def configure(reg, foto_verzeichnis=None, registry_path=None,
              bot_token=None, init_data_config=None, familie_client=None):
    """Setzt die laufende Registry + das aufgelöste Foto-Verzeichnis (FAM-9).

    Wird `foto_verzeichnis` nicht übergeben, leitet die Funktion es aus
    `reg.settings` ab. Wenn auch `registry_path` gesetzt ist, wird die
    FAM-9-Aussage „**neben der Registry-Datei**" eingelöst:
    `registry_mod.resolved_foto_verzeichnis` löst relative Werte gegen das
    Registry-Verzeichnis auf. Ohne `registry_path` bleibt das alte
    Verhalten (nackter Settings/ENV/Default-Wert) — für Tests, die nur eine
    Registry hereinreichen und das Foto-Verzeichnis selbst absolut machen.

    `bot_token`, `init_data_config` (T1638): Auth-Naht für Tests; im
    Produktiv-Betrieb aus ENV.
    `familie_client` (T1638): Test-Doppel; None → lokaler Direkt-Read
    aus `_aktuelle_registry()` (kein HTTP-Self-Call, kein Deadlock).
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
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if init_data_config is not None:
        runtime["init_data_config"] = init_data_config
    if familie_client is not None:
        runtime["familie_client"] = familie_client


# Schreib-Serialisierung (FAM-12/FAM-13): Read-Modify-Write der Registry-
# Datei aus parallelen Flask-Threads würde ohne Lock verloren-gehende
# Updates produzieren (zwei POSTs lesen denselben Stand, beide schreiben,
# der zweite überschreibt den ersten). Das Lock klammert nur den Schreib-
# Pfad — Lesen bleibt lock-frei (DCOMP-2 Reload-on-Read).
_write_lock = threading.Lock()


# ============================================================
#  MAD-7 Mini-App-Auth (T1638 — AUTH-3-HART-Cookie, analog routine/main.py)
# ============================================================

_ENV_BOT_TOKEN = "ELTERNCHAT_BOT_TOKEN"


def _get_bot_token():
    """Bot-Token aus runtime-Dict (Test-Naht) oder ENV (APP-7)."""
    return runtime.get("bot_token") or os.environ.get(_ENV_BOT_TOKEN)


class _LocalRegistryFamilieClient:
    """Test-freier Direkt-Read-Adapter: liest Telegram-IDs aus der laufenden
    Registry ohne HTTP-Selbst-Call (T1638, kein Deadlock, kein Self-Loop).

    familie IST die Registry — der Decorator braucht nur die Menge der
    telegram_id-Werte, die direkt aus `_aktuelle_registry()` gelesen werden
    können. Ein HTTP-Self-Call auf 127.0.0.1:5010 würde nach dem Gaten 401
    zurückgeben (die Loopback-Bypass-Bedingung gilt nur, wenn remote_addr
    wirklich 127.0.0.1 ist — das ist beim urllib-Call nicht garantiert,
    solange der Prozess auf allen Interfaces lauscht). Direkt-Read ist
    sauberer: kein Netz, keine Race-Condition, keine Abhängigkeit.
    """

    def get_telegram_ids(self):
        reg = _aktuelle_registry()
        ids = set()
        for p in reg.alle():
            if p.telegram_id is not None:
                try:
                    ids.add(int(p.telegram_id))
                except (TypeError, ValueError):
                    pass
        return ids or None


def _get_familie_client():
    """Liefert den Familie-Client — Test-Doppel aus runtime oder Direkt-Read-Adapter.

    Im Produktiv-Betrieb: `_LocalRegistryFamilieClient` liest die Telegram-IDs
    direkt aus der laufenden Registry (kein HTTP-Self-Call, T1638).
    In Tests: ein injiziertes Doppel aus `runtime["familie_client"]`.
    """
    cached = runtime.get("familie_client")
    if cached is not None:
        return cached
    return _LocalRegistryFamilieClient()


def _get_init_data_config():
    """Tma-Config (`max_age_seconds`) — gecacht im runtime-Dict oder frisch.

    Analog routine/main.py:_get_init_data_config (AUTH-Decorator-Lib).
    """
    cfg = runtime.get("init_data_config")
    if cfg is None:
        cfg = _init_data_mod.load_config()
        runtime["init_data_config"] = cfg
    return cfg


# AUTH-8: 401 rendert eine Anweisungsseite statt eines rohen Status-Codes
# (kanonisches Re-Pair-HTML analog routine/hoerspiel — T1638).
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


# Decorator: HART-AUTH (auth.md AUTH-2/3/5/8, T1638). Der Name
# `require_init_data` BLEIBT (AUTH-9-Coverage-Test trägt per AST-Namen);
# die Buddy-eigenen Getter + `_auth_401` gehen als Closures rein.
# Loopback-Bypass (AUTH-5): interne Buddies (plan/kibuddy/eltern-chat/
# hoerspiel) lesen familie via 127.0.0.1:5010 ohne XFF → pass-through.
# Foto-Route mit Cookie: Browser-<img> sendet Cookie same-origin → 200.
require_init_data = make_require_init_data(
    get_bot_token=_get_bot_token,
    get_familie_client=_get_familie_client,
    get_init_data_config=_get_init_data_config,
    auth_401=_auth_401,
)


# ============================================================
#  AUTH-11 (#1844): Dual-Gate für Flasks impliziten static-Endpunkt
# ============================================================
# familie hat keine eigene Browser-Fläche (Datenrouten sind bereits per
# require_init_data gegatet) — offen war nur Flasks Default-static-Endpunkt
# (kein eigenes static/-Verzeichnis im Service, liefert also faktisch nichts
# aus). AUTH-11 geht von der URL-Map aus, nicht von der Nützlichkeit: der
# Endpunkt existiert in der Map, also trägt er einen Decorator. Bot-Token-
# Getter und 401-Renderer sind mit require_init_data geteilt.

def _client_ip():
    """Client-IP fürs AUTH-7-Observe-Log (RAT-32: kein Gate mehr, nur Log)."""
    xri = request.headers.get("X-Real-IP")
    if xri:
        return xri.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


# RAT-32 Nicht-Verhandelbar (decisions/RAT-32-auth-cookie-only-hart.md, Lehre
# #1427→#1430): der Hard-Flip ist eine ENV-Naht, kein Code-Diff — der
# Rueckroll-Pfad ist "XBUDDY_AUTH_MODE=observe + Neustart", nicht "PR + Merge
# + Deploy". Form wortgleich zum seiten-Vorbild (seiten/main.py:469); Default
# hier ist "hard" statt seitens "observe" — Nic-Setzung 2026-08-11 (AUTH-11)
# betrifft den WERT (Display-Fläche ist Cookie-hart ab Tag 0), nicht den
# Mechanismus (dieselbe ENV-Naht, derselbe Rückroll-Pfad wie seiten).
_AUTH_MODE = os.environ.get("XBUDDY_AUTH_MODE", "hard")

require_dual_gate = make_require_dual_gate(
    get_bot_token=_get_bot_token,
    get_client_ip=_client_ip,
    auth_401=_auth_401,
    default_mode=_AUTH_MODE,
)


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)

# AUTH-11 (#1844): Flasks impliziter static-Endpunkt trägt keine @app.route-
# Dekoration — einziger Ansatzpunkt ist die View-Funktion nach der
# App-Erzeugung. familie hat kein eigenes static/-Verzeichnis (liefert also
# faktisch nichts aus), aber der Endpunkt steht in der URL-Map und AUTH-11
# prüft von dort aus, nicht von der Nützlichkeit.
app.view_functions["static"] = require_dual_gate()(app.view_functions["static"])


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


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
@require_init_data
def get_personen():
    """FAM-7: alle Personen der Familie (ohne Foto-Binär)."""
    return jsonify([p.to_dict() for p in _aktuelle_registry().alle()])


@app.route("/api/v1/familie/personen/<person_id>", methods=["GET"])
@require_init_data
def get_person(person_id):
    """FAM-7: eine Person je id. Unbekannte id: 404."""
    person = _aktuelle_registry().get(person_id)
    if person is None:
        return jsonify({"error": "unbekannte id"}), 404
    return jsonify(person.to_dict())


@app.route("/api/v1/familie/foto/<person_id>", methods=["GET"])
@require_init_data
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


def _aktuelles_foto_verzeichnis(reg):
    """Foto-Verzeichnis je Request über den FAM-9-Resolver auflösen, damit ein
    Settings-Wechsel in `familie.json` ohne Restart greift — wie für die
    Lese-Endpoints (siehe `get_foto`)."""
    path = runtime.get("registry_path")
    if path is not None:
        return registry_mod.resolved_foto_verzeichnis(reg.settings, path)
    return runtime["foto_verzeichnis"]


def _bad_request(msg):
    """FAM-12/FAM-13: 4xx mit JSON-Fehler, keine Stack-Traces (Disziplin
    aus dem Auftrag #213)."""
    return jsonify({"error": msg}), 400


@app.route("/api/v1/familie/personen", methods=["POST"])
@require_init_data
def post_person():
    """FAM-12: Person anlegen. JSON-Body `{name, art?, ring?, foto?, email?,
    telegram_id?}`, Antwort 200 mit dem Personen-JSON inkl. vergebener
    IDENT-1-`id`.

    Read-Modify-Write läuft hinter `_write_lock`, damit parallele POSTs nicht
    den jeweils anderen Eintrag verlieren — zwei Threads bekommen damit zwei
    verschiedene `id`s und beide Einträge landen in der Registry.
    """
    path = runtime.get("registry_path")
    if path is None:
        # In-Memory-Modus (Tests): wir schreiben nicht auf Disk, sondern nur
        # in das geladene Registry-Objekt — analog `_aktuelle_registry`.
        # Praktisch wird die Schreib-API immer mit `registry_path` betrieben;
        # diesen Pfad markieren wir als 503, statt eine halbe Wahrheit zu
        # liefern.
        return jsonify({"error": "kein Registry-Pfad konfiguriert"}), 503

    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return _bad_request("name fehlt oder ist leer")
    art = body.get("art") or registry_mod.KIND_ERWACHSENE
    if art not in (registry_mod.KIND_ERWACHSENE, registry_mod.KIND_KINDER):
        return _bad_request("art muss 'erwachsene' oder 'kinder' sein")
    ring = body.get("ring") or None
    foto = body.get("foto") or None
    email = body.get("email") or None
    telegram_id = body.get("telegram_id")

    with _write_lock:
        # DCOMP-2: frisch von Disk lesen — sonst sehen wir parallele
        # Cross-Service-Schreibvorgänge (z. B. von der Eltern-Chat-Skill-
        # Anlage) nicht und überschreiben sie.
        reg = registry_mod.load(path)
        try:
            person = registry_mod.add_person(
                reg, name=name, art=art, ring=ring, foto=foto,
                email=email, telegram_id=telegram_id)
        except registry_mod.RegistryError as e:
            return _bad_request(str(e))
        try:
            registry_mod.save(reg, path)
        except registry_mod.RegistryError as e:
            logging.warning("post_person: Schreiben fehlgeschlagen: %s", e)
            return jsonify({"error": str(e)}), 503
    return jsonify(person.to_dict()), 200


@app.route("/api/v1/familie/personen/<person_id>/foto", methods=["POST"])
@require_init_data
def post_foto(person_id):
    """FAM-13: Profilfoto setzen. Multipart-Feld `foto`. Schreibt das Foto
    atomar in `<foto_verzeichnis>/<id>/<dateiname>` und aktualisiert das
    `foto`-Feld der Person — beides hinter `_write_lock`, sodass ein
    paralleles `POST /personen` nicht die gerade geschriebene Foto-Person
    überschreibt."""
    path = runtime.get("registry_path")
    if path is None:
        return jsonify({"error": "kein Registry-Pfad konfiguriert"}), 503

    if "foto" not in request.files:
        return _bad_request("multipart-Feld 'foto' fehlt")
    upload = request.files["foto"]
    dateiname = (upload.filename or "").strip()
    if not dateiname:
        return _bad_request("Foto-Dateiname fehlt")
    daten = upload.read()
    if not daten:
        return _bad_request("Foto-Inhalt ist leer")

    with _write_lock:
        reg = registry_mod.load(path)
        if reg.get(person_id) is None:
            return jsonify({"error": "unbekannte id"}), 404
        foto_verzeichnis = _aktuelles_foto_verzeichnis(reg)
        try:
            foto_pfad = registry_mod.setze_foto(
                reg, foto_verzeichnis, person_id, dateiname, daten)
        except registry_mod.RegistryError as e:
            logging.warning("post_foto: Foto-Anlage fehlgeschlagen: %s", e)
            return jsonify({"error": str(e)}), 503
        try:
            registry_mod.save(reg, path)
        except registry_mod.RegistryError as e:
            # Foto bereits geschrieben, aber Registry-Save scheitert:
            # geschriebene Foto-Datei zurückrollen, sonst hätten wir eine
            # Foto-Datei ohne Verweis im Registry (FAM-11 letzter Satz).
            ziel = os.path.join(
                foto_verzeichnis, person_id, os.path.basename(dateiname))
            try:
                os.remove(ziel)
            except OSError:
                pass
            logging.warning("post_foto: Registry-Save fehlgeschlagen: %s", e)
            return jsonify({"error": str(e)}), 503
    return jsonify({"id": person_id, "foto_pfad": foto_pfad}), 200


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


# ── Health-Check (SVC-1) ─────────────────────────────────────────────────

@app.route("/healthz", methods=["GET"])
def healthz():
    """SVC-1: Health-Endpoint — liefert immer 200 + OK."""
    return jsonify({"ok": True}), 200


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
