#!/usr/bin/env python3
"""Plan-Buddy-App — HTTP-Schnittstellen + Entrypoint (PLAN-1 … PLAN-33).

Siehe specs/buddies/plan.md. Der Plan-Buddy ist die XBuddy-App mit dem
Buddy-Slug `plan` (PLAN-1). Er besitzt seine Daten (Verantwortlichkeiten,
plan.db) und seine Funktion (Kalender-Anbindung) und stellt beides über
Schnittstellen bereit (PLAN-21/22/23/33).

Endpunkte:
  GET /display/plan/woche               — View `woche`, Lese-Kind (PLAN-2/3/21)
  GET /display/plan/woche?ansicht=klein — View `woche`, Kleinkind (PLAN-3)
  GET /display/plan/woche?ab=<iso>      — Anker verschieben (PLAN-4)
  PUT /api/v1/plan/zuteilung            — Erwachsenen-Slot zuweisen (PLAN-7/8)
  PUT|DELETE /api/v1/plan/aktivitaet    — Kind-Aktivität setzen/löschen (PLAN-11)
  GET|PUT /api/v1/plan/termine          — Termin-Schnittstelle für Apps (PLAN-22)
  POST /api/v1/plan/termine/bulk        — Bulk-Termin-Schnittstelle (PLAN-33)
  GET|PUT /api/v1/plan/defaults         — Default-Verantwortlichkeiten (PLAN-36, public)
  GET|PUT /api/v1/plan/slot-modell      — Slot-Modell-Editor-API (PLAN-37, public)
  PUT /api/v1/plan/admin/kalender       — kalender_id setzen (PLAN-32, loopback)

Service-Topologie wie familie/main.py: eine schlanke eigenständige Flask-App,
ein Geschwister von router/ und familie/.
"""

import argparse
import collections
import contextlib
import hashlib
import json
import logging
import os
import random
import sys
import tempfile
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, make_response, render_template, request

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
from tools import familie_client as _familie_client_mod  # noqa: E402
from tools.familie_client import DEFAULT_ORIGIN as _FAMILIE_DEFAULT_ORIGIN  # noqa: E402
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.initdata.auth_gate import (  # noqa: E402
    make_require_dual_gate,
    make_require_init_data,
)
from tools.service_diagnostics import register_version  # noqa: E402
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
    "bot_token": None,          # AUTH-3 (T1321): Bot-Token — Test-Naht oder ENV
    "init_data_config": None,   # AUTH-3 (T1321): tma-Header-Validierungs-Config
    "auth_familie_client": None,  # AUTH-3 (T1321): FAM-7-Client (get_telegram_ids)
}


def configure(cfg, registry, transport, familie_client=None,
              config_path=None, transport_factory=None,
              bot_token=None, init_data_config=None,
              auth_familie_client=None):
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

    # AUTH-3 Hart-Auth (T1321): Test-Naht analog essen. `bot_token` /
    # `init_data_config` steuern die tma-Header-Prüfung, `auth_familie_client`
    # ist der FAM-7-Client mit `get_telegram_ids()` — bewusst ein EIGENER Slot
    # (nicht `familie_client`, der hier den RegistryView-`snapshot()`-Client
    # für die Personen-Sicht trägt und KEIN `get_telegram_ids()` hat).
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if init_data_config is not None:
        runtime["init_data_config"] = init_data_config
    if auth_familie_client is not None:
        runtime["auth_familie_client"] = auth_familie_client


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
#  Idempotenz-Cache für Bulk-Endpoint (PLAN-33.5)
# ============================================================
#
# In-Memory-LRU-Map: bis zu 256 Einträge, TTL 15 Minuten.
# Schlüssel: (request_id, items_hash). Wert: gespeichertes Antwort-Dict.
# Gespeicherter Eintrag: {"result": <antwort>, "ts": <monotonic-timestamp>}.
#
# PLAN-33.5: gleicher request_id + gleicher items_hash → gespeicherte Antwort
# zurück; gleicher request_id + anderer hash → HTTP 409.

_IDEM_MAX = 256
_IDEM_TTL = 15 * 60  # 15 Minuten in Sekunden

# OrderedDict als LRU-Backing: ältester Eintrag steht zuerst.
_idem_cache: "collections.OrderedDict[str, dict]" = collections.OrderedDict()


def _idem_set(request_id: str, items_hash: str, result: dict) -> None:
    """Speichert ein Ergebnis unter (request_id, items_hash)."""
    key = request_id + ":" + items_hash
    _idem_cache[key] = {"result": result, "ts": time.monotonic()}
    _idem_cache.move_to_end(key)
    while len(_idem_cache) > _IDEM_MAX:
        _idem_cache.popitem(last=False)


def _idem_get(request_id: str, items_hash: str):
    """Liefert das gespeicherte Ergebnis oder None (abgelaufene Einträge gelten
    als nicht vorhanden). Gibt das Ergebnis-Dict zurück oder None."""
    key = request_id + ":" + items_hash
    entry = _idem_cache.get(key)
    if entry is None:
        return None
    if time.monotonic() - entry["ts"] > _IDEM_TTL:
        # TTL abgelaufen: wie nicht vorhanden.
        _idem_cache.pop(key, None)
        return None
    # Hit: nach LRU ans Ende.
    _idem_cache.move_to_end(key)
    return entry["result"]


def _idem_has_collision(request_id: str, items_hash: str) -> bool:
    """True, wenn request_id bekannt ist aber mit anderem items_hash (409)."""
    for key, entry in list(_idem_cache.items()):
        if time.monotonic() - entry["ts"] > _IDEM_TTL:
            continue
        stored_rid, stored_hash = key.split(":", 1)
        if stored_rid == request_id and stored_hash != items_hash:
            return True
    return False


def _items_hash(items: list) -> str:
    """SHA-256 über die kanonisierte (JSON-sorted-keys) items-Liste (PLAN-33.5)."""
    canonical = json.dumps(items, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_UUID4_RE = None


def _is_uuid4(value: str) -> bool:
    """Prüft, ob `value` die UUIDv4-Form hat (PLAN-33.5, 8-4-4-4-12 hex)."""
    global _UUID4_RE
    if _UUID4_RE is None:
        import re
        _UUID4_RE = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            re.IGNORECASE)
    return bool(_UUID4_RE.match(value))


# ============================================================
#  AUTH-3 Hart-Auth (T1321 — auth.md AUTH-2/3/5/8/9)
# ============================================================
#
# Wörtliche Übernahme des essen-Decorators (essen/main.py, T948). Der
# Audit-Funnel-Befund #1338 klassifiziert die /api/v1/plan/*-Datenrouten neu
# als AUTH-3 (hart geschützt): extern über den Funnel waren sie schreibbar.
# Plan ist Nicht-Mini-App (PWA): der Cookie-Pfad ist der Regel-Pfad; der
# tma-Zweig bleibt kopiert (harmlos, greift nur bei gesetztem tma-Header).

# ENV-Variable für Bot-Token (APP-7 / MAD-9): cluster-weit, wie essen.
_ENV_BOT_TOKEN = "ELTERNCHAT_BOT_TOKEN"
# CONFIG-5: Familie-Service-Origin per Komponenten-ENV.
_ENV_FAMILIE_ORIGIN = "PLAN_FAMILIE_ORIGIN"


def _get_bot_token():
    """Bot-Token aus runtime-Dict (Test-Naht) oder ENV (APP-7)."""
    return runtime.get("bot_token") or os.environ.get(_ENV_BOT_TOKEN)


def _client_ip():
    """Client-IP fuers AUTH-7-Observe-Log (RAT-32: kein Gate mehr, nur Log).

    Wortgleich zum panel-/seiten-Vorbild: `X-Real-IP` vom Origin-nginx ist die
    vertrauenswuerdige Quelle; Fallbacks X-Forwarded-For (erstes Token), dann
    remote_addr.
    """
    xri = request.headers.get("X-Real-IP")
    if xri:
        return xri.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


def _get_familie_client():
    """Liefert den AUTH-3-FAM-Client — gecacht im runtime-Dict oder frisch (T1015).

    Test-Naht: ``configure(auth_familie_client=...)`` setzt direkt einen Stub
    mit ``get_telegram_ids()``. Produktiv-Pfad: ``tools.familie_client.FamilieClient``
    aus ENV ``PLAN_FAMILIE_ORIGIN``. Bewusst ein EIGENER Slot — der
    ``familie_client``-Slot trägt hier den RegistryView-``snapshot()``-Client
    (Personen-Sicht) und hat KEIN ``get_telegram_ids()``.
    """
    cached = runtime.get("auth_familie_client")
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


# Decorator: HART-AUTH (T948/T1321, auth.md AUTH-2/3/5/8). Der hand-kopierte
# Wrapper-Body ist mit #1626 auf die AUTH-Decorator-Lib-Factory geflippt
# (tools/initdata/auth_gate.py::make_require_init_data, #1625). Der Name
# `require_init_data` BLEIBT (AUTH-9-Coverage-Test trägt per AST-Namen); die
# Buddy-eigenen Getter + `_auth_401` gehen WÖRTLICH als Closures rein — die
# Factory ruft genau diesen `_auth_401`, 401/403/500-Shape bleibt byte-gleich.
# D3-Sonderfall: `_get_familie_client` liest UNVERÄNDERT den eigenen
# runtime["auth_familie_client"]-Slot (KEIN repo-weites Slot-Rename).
require_init_data = make_require_init_data(
    get_bot_token=_get_bot_token,
    get_familie_client=_get_familie_client,
    get_init_data_config=_get_init_data_config,
    auth_401=_auth_401,
)


# Decorator: AUTH-7b Dual-Gate (auth.md AUTH-7, RAT-32, #1836 AUTH-11). Die
# Display-Flaeche (`/display/plan/woche`, ihr implizites Flask-Static) ist ein
# Browser-Pfad auf dem Kind-Tablet — dort gibt es keinen tma-Header, sondern
# ein `xbuddy_session`-Cookie (AUTH-7b). `require_init_data` (HART-tma, oben)
# bleibt fuer die Mini-App-Datenrouten (`/api/v1/plan/*`) zustaendig; dieser
# zweite Gate deckt die Display-Flaeche. Bot-Token-Getter wird zwischen
# beiden Gates geteilt (gleicher HMAC-Sign-Key, AUTH-2:62 — kein zweites
# Geheimnis). `auth_401` teilt sich ebenfalls den bestehenden
# `_auth_401`-Renderer: der Re-Pair-Text ist bereits generisch "Gerät neu
# verbinden" formuliert (nicht tma-spezifisch) — ein zweiter, fast
# identischer 401-Text waere ein Genre-Duplikat ohne Mehrwert (D1 bleibt
# gewahrt: EIN Renderer pro Buddy, hier fuer beide Gates geteilt). Die
# 81-KB-Wochenplan-View traegt echte Familien-Namen — die sensibelste der
# sechs #1836-Routen.
# default_mode="hard" — Nic-Setzung 2026-08-11 (#1836): jede Adresse hinter
# dem Cookie, kein Observe-Grace fuer die Display-Flaeche.
require_dual_gate = make_require_dual_gate(
    get_bot_token=_get_bot_token,
    get_client_ip=_client_ip,
    auth_401=_auth_401,
    default_mode="hard",
)


# ============================================================
#  Flask-App
# ============================================================

# URL-13: statische Assets des Plan-Buddys liegen in seinem Display-
# Namensraum. So werden sie hinter der einen Origin (URL-12) geroutet —
# der Flask-Default `/static` läge außerhalb der URL-1-Prefixe (#61).
app = Flask(__name__, static_url_path="/display/plan/static")

# AUTH-11 (#1836): der implizite Flask-Static-Endpunkt traegt keine
# `@app.route`-Dekoration (Werkzeug registriert ihn intern als Endpunkt
# "static") — ein Decorator kann nicht am Pfad ansetzen, der ueber
# `static_folder`/`static_url_path` entsteht. Einziger Ansatzpunkt ist die
# View-Funktion selbst: sie wird nach der App-Erzeugung im
# `view_functions`-Dict durch die gegatete Fassung ersetzt. Bricht nichts,
# weil die View ihr eigenes JS/CSS ueber denselben Origin nachlaedt und der
# Browser dabei denselben Cookie mitschickt (Same-Origin).
app.view_functions["static"] = require_dual_gate()(app.view_functions["static"])


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)

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
@require_dual_gate(mode="hard")  # AUTH-11 (#1836): Display-Flaeche, Cookie-hart
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
        appointment_overflow=view["appointment_overflow"],
        span_appointments=view["span_appointments"],
        span_cover=view["span_cover"],
        span_lanes=view["span_lanes"],
        show_appointments=view["show_appointments"],
        picker_options=view["picker_options"],
        variant=variant,
        anchor=anker.isoformat(),
    )


@app.route("/api/v1/plan/zuteilung", methods=["GET"])
@require_init_data
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
@require_init_data
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
    if slot is None or not slot.ist_verantwortlich_slot():
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
@require_init_data
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
@require_init_data
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


@app.route("/api/v1/plan/termine/bulk", methods=["POST"])
@require_init_data
def api_termine_bulk():
    """Bulk-Termin-Schnittstelle: mehrere Termine in einem Aufruf anlegen
    (PLAN-33).

    Body: { "request_id": "<UUIDv4>", "items": [ <PLAN-22-PUT-Body>, … ] }

    Zwei-Phasen-Verarbeitung (PLAN-33.1):
      1. Pre-validate: alle Items gegen PLAN-22-Regeln.
         Mindestens ein Fehler → HTTP 400, results-Liste, 0 Schreibvorgänge.
      2. Best-effort write: saubere Items einzeln in Google schreiben,
         kein Rollback bei Teil-Misserfolg.

    Cap: len(items) > 30 → HTTP 400 {error: too_many_items, max: 30} (PLAN-33.3).
    Idempotenz LRU 256/15min via request_id + items_hash (PLAN-33.5).
    Token-Cache: ein Token-Refresh für alle N Inserts (PLAN-33.4).
    Exponential Backoff: 1s/2s/4s ±25% Jitter bei 403/429 (PLAN-33.6).
    Server-Budget: 15s (PLAN-33.4).
    """
    # ── Struktur-Validierung ──────────────────────────────────────────────
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON-Body fehlt oder ungültig"}), 400

    request_id = body.get("request_id")
    if not request_id or not isinstance(request_id, str):
        return jsonify({"error": "request_id ist Pflicht"}), 400
    if not _is_uuid4(request_id):
        return jsonify({"error": "request_id muss eine UUIDv4 sein"}), 400

    items = body.get("items")
    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "items ist Pflicht und muss eine nicht-leere Liste sein"}), 400

    # ── Cap-Prüfung (PLAN-33.3) ───────────────────────────────────────────
    if len(items) > 30:
        return jsonify({"error": "too_many_items", "max": 30}), 400

    # ── Idempotenz-Check (PLAN-33.5) ──────────────────────────────────────
    ihash = _items_hash(items)
    cached = _idem_get(request_id, ihash)
    if cached is not None:
        # Gleicher request_id + gleicher items_hash → gespeicherte Antwort.
        return jsonify(cached), 200

    if _idem_has_collision(request_id, ihash):
        # Gleicher request_id, anderer hash → Konflikt.
        return jsonify({"error": "request_id_collision"}), 409

    # ── Pre-validate (PLAN-33.1) ──────────────────────────────────────────
    validation_errors = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            validation_errors.append((i, "Item ist kein JSON-Objekt"))
            continue
        if not item.get("titel"):
            validation_errors.append((i, "titel ist Pflicht"))
            continue
        if item.get("event_id"):
            validation_errors.append((i, "event_id ist im Bulk-Endpoint nicht erlaubt"))
            continue
        try:
            _parse_beginn_ende(item)
        except ValueError as e:
            validation_errors.append((i, str(e)))

    if validation_errors:
        # Mindestens ein Fehler → alle Items als validation-Fehler markieren
        # (PLAN-33.1: "alle Items" im Fehlerfall).
        results = []
        for i, _item in enumerate(items):
            fehler = next((msg for idx, msg in validation_errors if idx == i), None)
            results.append({
                "ok": False,
                "error_code": "validation",
                "error": fehler if fehler else "validation",
            })
        return jsonify({
            "ok": False,
            "geschrieben": 0,
            "gesamt": len(items),
            "results": results,
        }), 400

    # ── Best-effort write (PLAN-33.1/33.4/33.6) ──────────────────────────
    budget_start = time.monotonic()
    _BUDGET_SECS = 15.0
    _BACKOFF_BASE = 1.0      # s
    _BACKOFF_CAP = 8.0       # s
    _BACKOFF_JITTER = 0.25   # ±25 %
    _MAX_RETRIES = 3

    transport = _kalender()._transport  # roher Transport für Token-Cache

    # Token-Cache: ein Refresh für alle N Inserts (PLAN-33.4).
    # Bei CalendarUnavailable → HTTP 502 (Kalender komplett tot).
    try:
        bearer = transport.access_token()
    except kalender_mod.CalendarUnavailable as e:
        logger.error("Bulk-Termin: Token-Refresh fehlgeschlagen: %s", e)
        return jsonify({"error": "calendar_unavailable"}), 502

    results = []
    geschrieben = 0

    for item in items:
        # Budget-Check: verbleibendes Budget prüfen (PLAN-33.4).
        elapsed = time.monotonic() - budget_start
        if elapsed >= _BUDGET_SECS:
            results.append({"ok": False, "error_code": "calendar_rate_limit",
                             "error": "server-budget überschritten"})
            continue

        titel = item.get("titel")
        try:
            beginn, ende = _parse_beginn_ende(item)
        except ValueError as e:
            # Sollte nach Pre-validate nicht mehr auftreten.
            results.append({"ok": False, "error_code": "validation", "error": str(e)})
            continue

        # Baue das Google-Roh-Event (analog Kalender.event_anlegen).
        if isinstance(beginn, datetime):
            raw = {
                "summary": titel,
                "start": {"dateTime": beginn.isoformat()},
                "end": {"dateTime": ende.isoformat()},
            }
        else:
            from datetime import timedelta as _timedelta
            end_exklusiv = (ende if ende is not None else beginn) + _timedelta(days=1)
            raw = {
                "summary": titel,
                "start": {"date": beginn.isoformat()},
                "end": {"date": end_exklusiv.isoformat()},
            }

        # Backoff-Retry-Schleife (PLAN-33.6).
        item_result = None
        backoff = _BACKOFF_BASE
        for attempt in range(_MAX_RETRIES + 1):  # 1 Versuch + 3 Retries = 4 total
            try:
                res = transport.insert_event_with_bearer(raw, bearer)
                event_id = res.get("id")
                item_result = {"ok": True, "event_id": event_id}
                geschrieben += 1
                break
            except kalender_mod.CalendarRateLimited as e:
                if attempt >= _MAX_RETRIES:
                    item_result = {"ok": False, "error_code": "calendar_rate_limit",
                                   "error": str(e)}
                    break
                # Wartezeit berechnen (PLAN-33.6).
                wait = backoff * (1 + random.uniform(-_BACKOFF_JITTER, _BACKOFF_JITTER))
                wait = min(wait, _BACKOFF_CAP)
                # Retry-After-Header sticht, AUSSER wenn Budget überschritten.
                if e.retry_after is not None:
                    remaining = _BUDGET_SECS - (time.monotonic() - budget_start)
                    if e.retry_after >= remaining:
                        # Retry-After sprengt Budget → sofort als rate_limit markieren.
                        item_result = {"ok": False, "error_code": "calendar_rate_limit",
                                       "error": "Retry-After sprengt Server-Budget"}
                        break
                    wait = e.retry_after
                # Budget-Check vor Warten.
                remaining = _BUDGET_SECS - (time.monotonic() - budget_start)
                if wait >= remaining:
                    item_result = {"ok": False, "error_code": "calendar_rate_limit",
                                   "error": "server-budget überschritten vor Retry"}
                    break
                logger.debug(
                    "Bulk-Termin: Backoff %.2fs (Versuch %d/%d): %s",
                    wait, attempt + 1, _MAX_RETRIES, e)
                time.sleep(wait)
                backoff = min(backoff * 2, _BACKOFF_CAP)
            except kalender_mod.CalendarAuthFailed as e:
                item_result = {"ok": False, "error_code": "calendar_auth", "error": str(e)}
                break
            except kalender_mod.CalendarUnavailable as e:
                item_result = {"ok": False, "error_code": "calendar_other", "error": str(e)}
                break

        results.append(item_result)

    response_body = {
        "ok": True,
        "geschrieben": geschrieben,
        "gesamt": len(items),
        "results": results,
    }
    _idem_set(request_id, ihash, response_body)
    return jsonify(response_body), 200


def _aktivitaet_label(art):
    """Anzeige-Label einer Aktivitäts-Art für den Event-Titel (PLAN-11).

    Delegiert an `plan.aktivitaeten` — den gemeinsamen Aktivitäts-Katalog
    (Refs #101). Liest den Live-Katalog via `_current_config()` (AC2,
    Config-Durchstich: POST-hinzugefügte Aktivitäten haben sofort ihr Label).
    """
    return aktivitaeten_mod.label_fuer_art(art, _current_config())


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
@require_init_data
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
@require_init_data
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
        with _plan_json_write_lock(path):
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
#  Admin + Public: Aktivitäts-Katalog (PLAN-34, #445/#578)
# ============================================================
#
# Drei Endpoints — analog der Schreib-Struktur aus PLAN-32 (admin/kalender):
#   GET  /api/v1/plan/aktivitaeten              — öffentlich, Reload-on-Read
#   POST /api/v1/plan/admin/aktivitaeten        — loopback, 4 Pflichtfelder, 409, atomar
#   DELETE /api/v1/plan/admin/aktivitaeten/<art>— loopback, 404, atomar
#
# Schreib-Endpoints materialisieren die aktivitaeten-Section in plan.json
# aus dem CONFIG-4-Fallback AKTIVITAETEN_V1, wenn sie noch nicht existiert.
# Atomarität: Temp-Datei + os.replace (analog _write_kalender_id).

def _read_plan_json_obj(path):
    """Liest plan.json und liefert das Objekt. Wirft OSError/ValueError."""
    with open(str(path), encoding="utf-8") as f:
        data = f.read()
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("plan.json-Wurzel ist kein JSON-Objekt")
    return obj


def _write_plan_json_obj(path, obj):
    """Schreibt obj atomar via Temp-Datei + os.replace nach path."""
    path_str = str(path)
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


# Gemeinsamer In-Process-Lock für alle plan.json-Read-Modify-Write-Pfade
# (PLAN-32/admin_kalender, PLAN-34/aktivitaeten POST+DELETE, PLAN-36/defaults,
# PLAN-37/slot-modell).  Ein Datei-Lock ist nicht nötig — der Plan-Buddy läuft
# als einzelner Prozess mit threaded=True (RAT-14, #1149).
_PLAN_JSON_WRITE_LOCK = threading.Lock()


@contextlib.contextmanager
def _plan_json_write_lock(path):
    """In-Process-Lock (threading.Lock) für den Read-Modify-Write-Pfad.

    Serialisiert gleichzeitige Schreiber auf plan.json.  Alle 5 RMW-Pfade
    (admin_kalender, aktivitaeten POST, aktivitaeten DELETE, defaults,
    slot-modell) nutzen denselben modul-globalen Lock — konsistent mit RAT-14.
    Stdlib only, kein Datei-Lock-Sidecar.
    """
    _PLAN_JSON_WRITE_LOCK.acquire()
    try:
        yield
    finally:
        _PLAN_JSON_WRITE_LOCK.release()


def _current_aktivitaeten_list():
    """Liefert die aktive Aktivitäts-Liste als Dicts (Reload-on-Read DCOMP-2).

    Greift auf _current_config().aktivitaeten; ist None, wird AKTIVITAETEN_V1
    zurückgegeben (CONFIG-4-Fallback, PLAN-12).
    """
    cfg = _current_config()
    if cfg.aktivitaeten is not None:
        return [a.to_dict() for a in cfg.aktivitaeten]
    return list(aktivitaeten_mod.AKTIVITAETEN_V1)


@app.route("/api/v1/plan/aktivitaeten", methods=["GET"])
@require_init_data
def api_aktivitaeten_lesen():
    """PLAN-34: öffentlicher GET — liefert den aktiven Aktivitäts-Katalog.

    Reload-on-Read (DCOMP-2): pro Aufruf frisch aus plan.json. Fehlt die
    Sektion, antwortet der Endpoint mit AKTIVITAETEN_V1 (CONFIG-4-Fallback).
    """
    return jsonify(_current_aktivitaeten_list()), 200


@app.route("/api/v1/plan/admin/aktivitaeten", methods=["POST"])
@require_init_data
def api_aktivitaeten_hinzufuegen():
    """PLAN-34: loopback POST — fügt einen Eintrag zum Aktivitäts-Katalog hinzu.

    Body: { art, label, keywords, piktogramm } — alle vier Pflichtfelder.
    409, wenn art bereits existiert. Atomar: plan.json via Temp + os.replace.
    Existiert die aktivitaeten-Sektion noch nicht, wird sie aus AKTIVITAETEN_V1
    materialisiert.
    """
    if not _is_loopback(request.remote_addr or ""):
        logger.warning("admin/aktivitaeten POST abgelehnt: remote_addr=%s",
                       request.remote_addr)
        return jsonify({
            "ok": False,
            "error": "nur 127.0.0.1 darf den Endpoint erreichen",
        }), 403

    body = request.get_json(silent=True) or {}
    # Pflichtfelder.
    for feld in ("art", "label", "piktogramm"):
        val = body.get(feld)
        if not val or not isinstance(val, str) or not val.strip():
            return jsonify({
                "ok": False,
                "error": "%s ist Pflicht und darf nicht leer sein" % feld,
            }), 400
    keywords = body.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        return jsonify({
            "ok": False,
            "error": "keywords ist Pflicht und muss eine nicht-leere Liste sein",
        }), 400
    for kw in keywords:
        if not isinstance(kw, str) or not kw:
            return jsonify({
                "ok": False,
                "error": "jedes keywords-Element muss ein nicht-leerer String sein",
            }), 400

    art = body["art"].strip()
    label = body["label"].strip()
    piktogramm = body["piktogramm"].strip()

    path = runtime.get("config_path")
    if not path:
        return jsonify({"ok": False, "error": "kein plan.json-Pfad konfiguriert"}), 500

    with _plan_json_write_lock(path):
        try:
            obj = _read_plan_json_obj(path)
        except (OSError, ValueError) as e:
            logger.error("admin/aktivitaeten POST: plan.json nicht lesbar: %s", e)
            return jsonify({"ok": False, "error": "plan.json nicht lesbar: %s" % e}), 500

        # Sektion materialisieren, falls noch nicht vorhanden (CONFIG-4).
        if "aktivitaeten" not in obj or obj["aktivitaeten"] is None:
            obj["aktivitaeten"] = [dict(e) for e in aktivitaeten_mod.AKTIVITAETEN_V1]

        # 409, wenn art bereits existiert.
        existing_arts = {e["art"] for e in obj["aktivitaeten"]}
        if art in existing_arts:
            return jsonify({"ok": False, "error": "art_existiert"}), 409

        obj["aktivitaeten"].append({
            "art": art,
            "label": label,
            "keywords": list(keywords),
            "piktogramm": piktogramm,
        })

        try:
            _write_plan_json_obj(path, obj)
        except OSError as e:
            logger.error("admin/aktivitaeten POST: plan.json nicht schreibbar: %s", e)
            return jsonify({"ok": False, "error": "plan.json nicht schreibbar: %s" % e}), 500

    # In-process-Übernahme — gleicher Pfad wie admin/kalender.
    try:
        reload_plan_config()
    except PlanReloadError as e:
        logger.error("admin/aktivitaeten POST: Reload fehlgeschlagen: %s", e)
        # Datei ist korrekt geschrieben; Reload-on-Read greift beim nächsten Aufruf.

    logger.info("admin/aktivitaeten POST: art=%r hinzugefügt", art)
    return jsonify({"ok": True, "art": art}), 200


@app.route("/api/v1/plan/admin/aktivitaeten/<art>", methods=["DELETE"])
@require_init_data
def api_aktivitaeten_loeschen(art):
    """PLAN-34: loopback DELETE — entfernt einen Eintrag aus dem Katalog.

    404, wenn art unbekannt. Atomar: plan.json via Temp + os.replace.
    Existiert die aktivitaeten-Sektion noch nicht, wird sie aus AKTIVITAETEN_V1
    materialisiert und der Eintrag daraus gelöscht (wie spec).
    """
    if not _is_loopback(request.remote_addr or ""):
        logger.warning("admin/aktivitaeten DELETE abgelehnt: remote_addr=%s",
                       request.remote_addr)
        return jsonify({
            "ok": False,
            "error": "nur 127.0.0.1 darf den Endpoint erreichen",
        }), 403

    path = runtime.get("config_path")
    if not path:
        return jsonify({"ok": False, "error": "kein plan.json-Pfad konfiguriert"}), 500

    with _plan_json_write_lock(path):
        try:
            obj = _read_plan_json_obj(path)
        except (OSError, ValueError) as e:
            logger.error("admin/aktivitaeten DELETE: plan.json nicht lesbar: %s", e)
            return jsonify({"ok": False, "error": "plan.json nicht lesbar: %s" % e}), 500

        # Sektion materialisieren, falls noch nicht vorhanden (CONFIG-4).
        if "aktivitaeten" not in obj or obj["aktivitaeten"] is None:
            obj["aktivitaeten"] = [dict(e) for e in aktivitaeten_mod.AKTIVITAETEN_V1]

        # 404, wenn art unbekannt.
        before = obj["aktivitaeten"]
        after = [e for e in before if e["art"] != art]
        if len(after) == len(before):
            return jsonify({"ok": False, "error": "art unbekannt: %r" % art}), 404

        obj["aktivitaeten"] = after

        try:
            _write_plan_json_obj(path, obj)
        except OSError as e:
            logger.error("admin/aktivitaeten DELETE: plan.json nicht schreibbar: %s", e)
            return jsonify({"ok": False, "error": "plan.json nicht schreibbar: %s" % e}), 500

    # In-process-Übernahme.
    try:
        reload_plan_config()
    except PlanReloadError as e:
        logger.error("admin/aktivitaeten DELETE: Reload fehlgeschlagen: %s", e)
        # Datei ist korrekt geschrieben; Reload-on-Read greift beim nächsten Aufruf.

    logger.info("admin/aktivitaeten DELETE: art=%r entfernt", art)
    return jsonify({"ok": True, "art": art}), 200


# ============================================================
#  Public: Default-Verantwortlichkeiten + Slot-Modell (PLAN-36/PLAN-37, #1126)
# ============================================================
#
# Zwei PUBLIC-Daten-APIs für die Eltern-Einstellungs-PWA (PLAN-35). Anders als
# der Aktivitäts-Katalog (PLAN-34, loopback) sind diese Routen NICHT loopback-
# beschränkt: auth.md AUTH-6 stellt `/api/v1/plan/*` als Netz-Trust-PUBLIC.
# Es gibt KEIN require_init_data, KEINEN initData-Check (P2 ist PWA, nicht
# Telegram-Mini-App).
#
# Persistenz: gleicher atomare Merge-Pfad wie PLAN-34 — _read_plan_json_obj
# liest den ganzen plan.json-Dict, der Endpoint setzt NUR seine Sektion(en),
# _write_plan_json_obj schreibt das ganze (gemergte) Objekt über Temp +
# os.replace. Alle anderen Sektionen (aktivitaeten, kalender_id,
# _-Kommentar-Keys, slots/defaults der je anderen Route) bleiben byte-gleich.


def _defaults_aus_config():
    """Liefert die Default-Verantwortlichkeiten in API-Nutzform `defaults`.

    In-Memory liegt der Stand als `{ slot: { wochentag_int: person_id|None } }`
    vor (`Config.default_verantwortlichkeiten`, PLAN-10). Die API-Form spiegelt
    das mit String-Wochentag-Keys (JSON kennt keine int-Keys):
    `{ "<slot>": { "0".."6": "<pid>"|null } }`.
    Reload-on-Read (DCOMP-2): pro Aufruf frisch via `_current_config()`.
    """
    cfg = _current_config()
    out = {}
    for slot_key, by_day in cfg.default_verantwortlichkeiten.items():
        out[slot_key] = {str(wd): by_day.get(wd) for wd in range(7)}
    return out


@app.route("/api/v1/plan/defaults", methods=["GET"])
@require_init_data
def api_defaults_lesen():
    """PLAN-36: PUBLIC GET — Default-Verantwortlichkeiten (PLAN-10).

    Antwort: `{ "defaults": { "<slot>": { "0".."6": "<pid>"|null } } }`.
    Reload-on-Read (DCOMP-2): pro Aufruf frisch aus plan.json.
    """
    return jsonify({"defaults": _defaults_aus_config()}), 200


@app.route("/api/v1/plan/defaults", methods=["PUT"])
@require_init_data
def api_defaults_schreiben():
    """PLAN-36: PUBLIC PUT — setzt die Default-Verantwortlichkeiten (PLAN-10).

    Body: `{ "defaults": { "<slot>": { "<wochentag 0..6>": "<pid>"|null } } }`.
    Der übergebene Stand ist der Gesamt-Soll-Zustand der Defaults.

    Validierung VOR Persistenz (kein 500, kein Teil-Write bei Fehler):
      - `defaults` ist Pflicht und ein Objekt;
      - jeder slot_key ist ein Verantwortlichkeits-Slot (PLAN-6) der aktuellen
        Config;
      - jeder Wochentag-Key ist 0..6;
      - jede person_id existiert in familie.json (FAM-3) — `null` (leerer Tag)
        ist erlaubt.
    Persistenz (Form↔Datei-Mapping, verbindlich): geschrieben wird ZWINGEND
    unter dem Datei-Schlüssel `default_verantwortlichkeiten` in LISTEN-Form
    `[p0..p6]` — das ist die Form, die der Config-Loader liest
    (`plan/config.py` `_parse_defaults`). Atomar + Reload (PLAN-32-Muster).
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("defaults"), dict):
        return jsonify({"error": "defaults (Objekt) ist Pflicht"}), 400

    cfg = _current_config()
    verantwortlich_keys = {s.schluessel for s in cfg.erwachsenen_slots()}
    registry = _aktuelle_registry()

    # Validierung + Übersetzung in die Datei-Listen-Form — alles VOR Persistenz.
    datei_defaults = {}
    for slot_key, by_day in body["defaults"].items():
        if slot_key not in verantwortlich_keys:
            return jsonify({
                "error": "kein Verantwortlichkeits-Slot: %r" % slot_key
            }), 400
        if not isinstance(by_day, dict):
            return jsonify({
                "error": "defaults[%r] muss ein Wochentag-Objekt sein" % slot_key
            }), 400
        liste = [None] * 7
        for wd_raw, pid in by_day.items():
            try:
                wd = int(wd_raw)
            except (TypeError, ValueError):
                return jsonify({
                    "error": "Wochentag %r ist keine Ganzzahl 0..6" % wd_raw
                }), 400
            if not (0 <= wd <= 6):
                return jsonify({
                    "error": "Wochentag %r liegt außerhalb 0..6" % wd_raw
                }), 400
            if pid is not None and registry.get(pid) is None:
                return jsonify({"error": "unbekannte person_id: %r" % pid}), 400
            liste[wd] = pid
        datei_defaults[slot_key] = liste

    path = runtime.get("config_path")
    if not path:
        return jsonify({"error": "kein plan.json-Pfad konfiguriert"}), 500

    with _plan_json_write_lock(path):
        try:
            obj = _read_plan_json_obj(path)
        except (OSError, ValueError) as e:
            logger.error("PUT defaults: plan.json nicht lesbar: %s", e)
            return jsonify({"error": "plan.json nicht lesbar: %s" % e}), 500

        # Rest-Dict-Merge: nur die eine Sektion setzen, alles andere bleibt stehen.
        obj["default_verantwortlichkeiten"] = datei_defaults

        try:
            _write_plan_json_obj(path, obj)
        except OSError as e:
            logger.error("PUT defaults: plan.json nicht schreibbar: %s", e)
            return jsonify({"error": "plan.json nicht schreibbar: %s" % e}), 500

    # In-process-Übernahme (PLAN-32-Muster); Reload-on-Read greift ohnehin.
    try:
        reload_plan_config()
    except PlanReloadError as e:
        logger.error("PUT defaults: Reload fehlgeschlagen: %s", e)

    logger.info("PUT defaults: %d Slot-Defaults gesetzt", len(datei_defaults))
    return jsonify({"ok": True}), 200


@app.route("/api/v1/plan/slot-modell", methods=["GET"])
@require_init_data
def api_slot_modell_lesen():
    """PLAN-37: PUBLIC GET — die aktuelle Slot-Liste (PLAN-6).

    Antwort: `{ "slots": [ { "schluessel", "art", "icon", "kind"?, "label"? }, … ] }`
    (Form aus `Slot.to_dict`; `label` ist der optionale Anzeige-Name, PLAN-6).
    Reload-on-Read (DCOMP-2).
    """
    cfg = _current_config()
    return jsonify({"slots": [s.to_dict() for s in cfg.slots]}), 200


@app.route("/api/v1/plan/slot-modell", methods=["PUT"])
@require_init_data
def api_slot_modell_schreiben():
    """PLAN-37: PUBLIC PUT — setzt die Gesamt-Slot-Liste (PLAN-6).

    Body: `{ "slots": [ { "schluessel", "art", "icon", "kind"?, "label"? }, … ] }`.
    Die übergebene Liste IST der Soll-Zustand; ein vorher vorhandener
    `schluessel`, der fehlt, gilt als GELÖSCHT.

    Validierung VOR Persistenz (kein 500, kein Teil-Write):
      - `slots` ist Pflicht und eine Liste;
      - jeder Slot trägt `schluessel`, `art`, `icon`;
      - `art ∈ {verantwortlich, kalender-read}`;
      - jeder `kalender-read`-Slot trägt ein `kind`, das in familie.json (FAM-3)
        existiert;
      - `label` ist optional (fehlt/null erlaubt); wenn vorhanden, ein String;
      - alle `schluessel` sind eindeutig;
      - `schluessel` ist UNVERÄNDERLICH: trägt ein Slot ein Feld, das den
        `schluessel` eines bestehenden Slots umbenennen will
        (`schluessel_neu`/`rename`/`neuer_schluessel`), → HTTP 400.
    >8 Slots → WARN-Log, kein Fehler (`SLOT_WARN_AB`, PLAN-6 V1.3) — der Parser
    loggt das beim Reload.

    Multi-Sektion-Save (verbindlich, atomar in EINEM Write): die `slots`-Sektion
    UND die `default_verantwortlichkeiten`-Sektion fallen konsistent — Defaults
    eines gelöschten Slots werden mit entfernt (sonst wirft `_parse_defaults`
    beim nächsten load einen ConfigError, plan/config.py).
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("slots"), list):
        return jsonify({"error": "slots (Liste) ist Pflicht"}), 400

    registry = _aktuelle_registry()
    seen = set()
    sauber = []
    for raw in body["slots"]:
        if not isinstance(raw, dict):
            return jsonify({"error": "Slot-Eintrag ist kein Objekt"}), 400
        # schluessel ist UNVERÄNDERLICH: ein Umbenenn-Feld weisen wir ab (400).
        for verboten in ("schluessel_neu", "neuer_schluessel", "rename"):
            if verboten in raw:
                return jsonify({"error": "schluessel ist unveränderlich"}), 400
        for feld in ("schluessel", "art", "icon"):
            val = raw.get(feld)
            if not val or not isinstance(val, str) or not val.strip():
                return jsonify({
                    "error": "Slot ohne Pflichtfeld %r" % feld
                }), 400
        schluessel = raw["schluessel"]
        art = raw["art"]
        if art not in config_mod.SLOT_ARTEN:
            return jsonify({
                "error": "Slot %r: Art %r unbekannt" % (schluessel, art)
            }), 400
        kind = raw.get("kind")
        if art == config_mod.SLOT_KALENDER_READ:
            if not kind or registry.get(kind) is None:
                return jsonify({
                    "error": "kalender-read-Slot %r braucht ein bekanntes kind"
                             % schluessel
                }), 400
        if schluessel in seen:
            return jsonify({
                "error": "doppelter Slot-Schlüssel %r" % schluessel
            }), 400
        # label ist ein optionaler Anzeige-Name (PLAN-6/PLAN-37). Fehlt/None
        # erlaubt; wenn vorhanden, muss es ein String sein.
        label = raw.get("label")
        if label is not None and not isinstance(label, str):
            return jsonify({
                "error": "Slot %r: label muss ein String sein" % schluessel
            }), 400
        seen.add(schluessel)
        eintrag = {"schluessel": schluessel, "art": art, "icon": raw["icon"]}
        # kind nur übernehmen, wenn gesetzt (verantwortlich-Slots dürfen ein
        # kind tragen — z. B. bett-bringt-Slot — aber es ist optional).
        if kind:
            eintrag["kind"] = kind
        # label nur übernehmen, wenn gesetzt (optionaler Anzeige-Name).
        if label is not None:
            eintrag["label"] = label
        sauber.append(eintrag)

    path = runtime.get("config_path")
    if not path:
        return jsonify({"error": "kein plan.json-Pfad konfiguriert"}), 500

    with _plan_json_write_lock(path):
        try:
            obj = _read_plan_json_obj(path)
        except (OSError, ValueError) as e:
            logger.error("PUT slot-modell: plan.json nicht lesbar: %s", e)
            return jsonify({"error": "plan.json nicht lesbar: %s" % e}), 500

        # Multi-Sektion-Save: slots setzen UND defaults gelöschter/art-gewechselter
        # Slots bereinigen. Ein Default-Eintrag bleibt NUR, wenn sein Slot im neuen
        # Soll-Zustand existiert UND art == verantwortlich ist (PLAN-37). Ein Slot,
        # der von verantwortlich → kalender-read wechselt, verliert seine Defaults
        # genauso wie ein gelöschter — sonst wirft _parse_defaults beim nächsten
        # load einen ConfigError (plan/config.py:351-354).
        verantwortlich_keys = {
            s["schluessel"] for s in sauber
            if s.get("art") == config_mod.SLOT_VERANTWORTLICH
        }
        alte_defaults = obj.get("default_verantwortlichkeiten")
        obj["slots"] = sauber
        if isinstance(alte_defaults, dict):
            obj["default_verantwortlichkeiten"] = {
                k: v for k, v in alte_defaults.items() if k in verantwortlich_keys
            }

        try:
            _write_plan_json_obj(path, obj)
        except OSError as e:
            logger.error("PUT slot-modell: plan.json nicht schreibbar: %s", e)
            return jsonify({"error": "plan.json nicht schreibbar: %s" % e}), 500

    try:
        reload_plan_config()
    except PlanReloadError as e:
        logger.error("PUT slot-modell: Reload fehlgeschlagen: %s", e)

    logger.info("PUT slot-modell: %d Slots gesetzt", len(sauber))
    return jsonify({"ok": True}), 200


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
    # Demo-Modus (#1761): PLAN_KALENDER_DEMO_FILE schaltet den Kalender auf eine
    # lokale JSON-Datei (Familie Sonntag, aktuelle Woche) statt Google — so
    # rendert /display/plan/woche ohne OAuth einen vollen Wochenplan. Live bleibt
    # GoogleTransport (Env ungesetzt).
    demo_kalender = os.environ.get("PLAN_KALENDER_DEMO_FILE")

    def transport_factory(cfg):
        if demo_kalender:
            return kalender_mod.DateiTransport(demo_kalender, cfg.kalender_id)
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
