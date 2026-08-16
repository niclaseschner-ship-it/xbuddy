#!/usr/bin/env python3
"""Hörspiel-Buddy-App — HTTP-Schnittstelle + Entrypoint (HSP-17/HSP-28).

Siehe specs/buddies/hoerspiel.md. Endpunkte (seit #908 URL-3a-konform, HSP-26):

  GET  /api/v1/hoerspiel/<kind_id>/bible             — Welt-Bible als Markdown
  GET  /api/v1/hoerspiel/<kind_id>/folgen-historie   — Folgen-Historie als Markdown
  GET  /api/v1/hoerspiel/<kind_id>/alben             — Liste freigegebener Alben
  GET  /api/v1/hoerspiel/<kind_id>/alben/<id>/manifest — Album-Manifest
  POST /api/v1/hoerspiel/<kind_id>/folgen-vorschlag  — LLM-Vorschlag (Side-Effekt-frei)
  POST /api/v1/hoerspiel/<kind_id>/alben             — Album bauen (TTS + Historie)
  GET  /api/v1/hoerspiel/<kind_id>/config            — Eltern-Tuning-Konfig lesen (HSP-34)
  PATCH /api/v1/hoerspiel/<kind_id>/config           — Eltern-Tuning setzen (HSP-34)
  GET  /api/v1/hoerspiel/<kind_id>/themen             — Themen-Liste je Alter (HSP-38, T4, RAT-17)
  GET  /api/v1/hoerspiel/<kind_id>/alben/<id>/audio/<track>.mp3 — Audio-Track (HSP-37)
  GET  /api/v1/hoerspiel/<kind_id>/resume?album=<id> — Resume-Stand lesen (HSP-36)
  PUT  /api/v1/hoerspiel/<kind_id>/resume            — Resume-Stand setzen (HSP-36)
  GET  /api/v1/hoerspiel/<kind_id>/shared-assets/status — Vorhandensein je Voice
  POST /api/v1/hoerspiel/<kind_id>/shared-assets/rebuild — alle vier MP3s neu bauen

Daten-Router (HSP-26, URL-3a):
  GET  /display/hoerspiel/<kind_id>/alben            — Alben-View (HTML)
  GET  /display/hoerspiel/<kind_id>/data/<sub>       — Audio-/Cover-Assets

  GET  /healthz                                      — Health-Check (SVC-1)

Port: 5053 (HSP-28). Service-Topologie: schlanke eigenständige Flask-App
(Geschwister von wetter/, routine/, plan/).
"""

import argparse
import contextlib
import json
import logging
import os
import queue
import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    Response,
    jsonify,
    make_response,
    render_template,
    request,
    send_from_directory,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import familie_client as _tools_familie_client_mod  # noqa: E402
from tools import logsetup  # noqa: E402
from tools.familie_client import DEFAULT_ORIGIN as _FAMILIE_DEFAULT_ORIGIN  # noqa: E402
from tools.service_diagnostics import register_version  # noqa: E402

if __package__:
    from . import album_builder, data_io, llm_service, tts_service
    from . import config as config_mod
    from . import familie_client as familie_client_mod
    from .providers.base import LLMProvider, ProviderError
    from .tts.azure import TTSError
else:  # python3 hoerspiel/main.py
    sys.path.insert(0, _REPO_ROOT)
    from hoerspiel import album_builder, data_io, llm_service, tts_service
    from hoerspiel import config as config_mod
    from hoerspiel import familie_client as familie_client_mod
    from hoerspiel.providers.base import LLMProvider, ProviderError
    from hoerspiel.tts.azure import TTSError

# MAD-7 / HSP-39 / T1015: Init-Data-Auth aus tools.initdata (Cluster-A-Option-B
# 2026-06-18-1720 — kein sys.path-Hack auf eltern-chat mehr).
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.initdata.auth_gate import (  # noqa: E402
    make_require_dual_gate,
    make_require_init_data,
)

_INIT_DATA_AVAILABLE = True


logger = logging.getLogger(__name__)

# ============================================================
#  Laufzeit-Zustand (Test-Naht analog wetter/main.py)
# ============================================================

# HSP-3a / HSP-43 (#1263) / INST-1 (#1656): die „anderen Kinder" ergeben sich aus
# der Instanz-Liste `config.instanzen()` (Leser von instanzen.json, alle Einträge
# außer der eigenen kind_id) — kein binärer mia↔finn-Toggle mehr, damit n≥3
# (emil) additiv trägt (HSP-3a n≥3, HSP-46). KEINE Registry, KEIN Cross-Service-Import.

# ENV-Key für den Familie-Service-Origin (DCOMP-1 / CLIENT-1).
# Default kommt aus tools.familie_client.DEFAULT_ORIGIN (zentral, CLIENT-1).
ENV_FAMILIE_ORIGIN = "HOERSPIEL_FAMILIE_ORIGIN"

runtime: dict = {
    "runtime_config": None,    # config.RuntimeConfig
    "data_config": None,       # config.DataConfig
    "data_root": None,         # str — HSP-25-Daten-Bereich
    "llm_factory": None,       # cfg -> LLMProvider
    "llm": None,               # LLMProvider (Cache; gebunden an provider+model+key)
    "tts_engine": None,        # tts.azure.AzureTTSEngine (oder Fake in Tests)
    "now": lambda: datetime.now(ZoneInfo("Europe/Berlin")),
    # MAD-7 / HSP-39: Bot-Token + init_data-Konfig für Mini-App-Auth.
    "bot_token": None,         # str | None — aus ENV ELTERNCHAT_BOT_TOKEN
    "init_data_config": None,  # dict — gecacht nach erstem Lauf
    # T1015: FAM-Auth-Lookup via tools.familie_client (HTTP); ersetzt den
    # früheren familie.json-Direkt-Read (DCOMP-1 / FAM-7-Heilung).
    "familie_client_auth": None,  # tools.familie_client.FamilieClient | Test-Doppel | None
    "resume_store": {},        # dict album_id -> track_position (in-process für V1)
    # HSP-3a: lokaler FamilieClient für Face-Pille snapshot() (Test-Naht: direkt setzen).
    "familie_client": None,    # familie_client_mod.FamilieClient | None
}


def configure(*, runtime_config, data_config, data_root: str,
              llm_factory=None, llm=None,
              tts_engine=None, now=None,
              bot_token=None, init_data_config=None,
              familie_client_auth=None,
              familie_client=None) -> None:
    """Setzt Konfiguration und Adapter-Fabriken (Test-Naht, HSP-24).

    `llm_factory(cfg) -> LLMProvider` baut den Provider passend zur aktiven
    Runtime-Config — bei `PATCH /config` mit neuem Provider/Modell wird er
    erneut gerufen. In Tests bleibt `llm_factory=None` und `llm=` wird
    direkt gesetzt.

    `now` ist die HSP-24-Naht für deterministische Zeit (Manifest-`erstellt-
    am`, Historie-Datum, ...).

    `bot_token` + `init_data_config` + `familie_client_auth`: MAD-7/HSP-39
    Auth-Naht. ``familie_client_auth`` ist ein Test-Doppel mit
    ``get_telegram_ids()``-Methode oder eine ``tools.familie_client.FamilieClient``-
    Instanz; None → Produktiv-Pfad via ENV ``HOERSPIEL_FAMILIE_ORIGIN``
    (T1015 / Cluster-A-Option-B).

    `familie_client`: HSP-3a-Face-Pille-Test-Naht — lokaler hoerspiel-Client
    mit ``snapshot()``-API für die Pille-Darstellung. Separat vom Auth-Client,
    weil zwei verschiedene Antwort-Formen gebraucht werden (Person-Lookup vs.
    Telegram-IDs).
    """
    runtime["runtime_config"] = runtime_config
    runtime["data_config"] = data_config
    runtime["data_root"] = data_root
    runtime["llm_factory"] = llm_factory
    runtime["llm"] = llm
    runtime["tts_engine"] = tts_engine
    if now is not None:
        runtime["now"] = now
    # Auth-Felder immer überschreiben damit Test-Isolation funktioniert (HSP-40).
    # Wer einen leeren Client will muss explizit bot_token=None übergeben.
    runtime["bot_token"] = bot_token
    runtime["init_data_config"] = init_data_config
    runtime["familie_client_auth"] = familie_client_auth
    runtime["resume_store"] = {}
    runtime["familie_client"] = familie_client


def _runtime_cfg():
    return runtime["runtime_config"]


def _data_cfg():
    return runtime["data_config"]


def _data_root() -> str:
    root = runtime["data_root"]
    if not root:
        raise RuntimeError("hoerspiel: data_root nicht konfiguriert (configure())")
    return root


def _llm() -> LLMProvider | None:
    if runtime.get("llm") is not None:
        return runtime["llm"]
    factory = runtime.get("llm_factory")
    cfg = _runtime_cfg()
    if factory is None or cfg is None:
        return None
    if cfg.llm_provider == "claude" and not cfg.anthropic_key:
        return None
    if cfg.llm_provider == "mistral" and not cfg.mistral_key:
        return None
    llm = factory(cfg)
    runtime["llm"] = llm
    return llm


def _tts():
    return runtime.get("tts_engine")


def _now() -> datetime:
    return runtime["now"]()


# ============================================================
#  MAD-7 / HSP-39: Auth-Helpers
# ============================================================

def _get_bot_token() -> str | None:
    """Liest den Bot-Token aus runtime-Dict oder ENV (MAD-7 / APP-7)."""
    return (
        runtime.get("bot_token")
        or os.environ.get("ELTERNCHAT_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
    )


def _get_familie_client_auth():
    """Liefert den FAM-Auth-Client (T1015, Cluster-A-Option-B).

    Test-Naht: ``configure(familie_client_auth=...)``. Produktiv-Pfad:
    ``tools.familie_client.FamilieClient`` aus ENV
    ``HOERSPIEL_FAMILIE_ORIGIN`` (Default ``http://127.0.0.1:5010``).
    Wiederverwendet denselben ENV-Namen wie der Face-Pille-Client, weil beide
    auf denselben Familie-Service zeigen — die zwei Clients teilen Origin,
    nur API-Form unterscheidet sich.
    """
    cached = runtime.get("familie_client_auth")
    if cached is not None:
        return cached
    origin = os.environ.get(ENV_FAMILIE_ORIGIN, _FAMILIE_DEFAULT_ORIGIN)
    return _tools_familie_client_mod.FamilieClient(origin_url=origin)


# ============================================================
#  AUTH-3 HART-Cookie — Datenrouten (T1640, auth.md AUTH-3)
# ============================================================
# Phase-3-Migration (2026-07-30 gefeuert): die hoerspiel-Datenrouten
# (config, alben, alben/<id>/manifest, resume, themen, folgen-vorschlag) wandern
# von AUTH-6/SOFT auf HART-Cookie (auth.md AUTH-3, RAT-32 cookie-only).
# Verdrahtung identisch zum #1639-routine-Muster (make_require_init_data-Factory).
# NICHT auf /api/v1/hoerspiel/<kind_id>/alben/<id>/audio/<track>.mp3 (AUTH-4
# public — <audio>-Element lädt ohne zuverlässiges Cookie) und NICHT auf
# audio-stream (AUTH-6 public, Phase-4-Trigger). Player-HTML-Shell lebt in seiten.


def _get_init_data_config():
    """Tma-Config (``max_age_seconds``) — gecacht im runtime-Dict oder frisch.

    Getter-Naht für die AUTH-Decorator-Lib-Factory (T1640).
    Pfad: ``runtime.get("init_data_config")`` → ``_init_data_mod.load_config()`` + Cache.
    """
    cfg = runtime.get("init_data_config")
    if cfg is None:
        cfg = _init_data_mod.load_config()
        runtime["init_data_config"] = cfg
    return cfg


# AUTH-8: 401 rendert eine HTML-Anweisungsseite statt eines rohen Status-Codes
# (kanonisches Re-Pair-HTML analog photo/essen/routine — hoerspiel hatte unter
# SOFT keins, weil der SOFT-Pfad nie 401 auf fehlende Quelle warf).
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


# Decorator: HART-AUTH (auth.md AUTH-2/3/5/8, T1640 Phase-3-Migration). Der Name
# `require_init_data` trägt den AUTH-9-Coverage-Test per AST-Namen
# (_AUTH_DECORATORS). Buddy-eigene Getter + `_auth_401` gehen als Closures rein.
require_init_data = make_require_init_data(
    get_bot_token=_get_bot_token,
    get_familie_client=_get_familie_client_auth,
    get_init_data_config=_get_init_data_config,
    auth_401=_auth_401,
)


# ============================================================
#  AUTH-11 Dual-Gate — /display/hoerspiel/*-Browser-Flaechen (T1833, #1805)
# ============================================================
# Die /display/hoerspiel/…-Renderer-Routen (samt dem impliziten Flask-
# static-Endpunkt) sind reine Browser-Flaechen — kein tma-Header (das
# <img>/<script>/<a href>-Laden traegt keinen Authorization-Header), kein
# Server-zu-Server-Loopback-Aufrufer. Analog seiten/main.py require_dual_gate
# (AUTH-7b) und dem #1833-Geschwister-Track routine: NUR der
# xbuddy_session-Cookie zaehlt (kein tma, kein Loopback-Bypass — anders als
# require_init_data oben). Bot-Token-Getter und 401-Renderer werden mit
# require_init_data GETEILT (gleicher HMAC-Sign-Key, kein zweites Geheimnis;
# ein zweiter fast identischer 401-Text waere ein Genre-Duplikat).


def _client_ip():
    """Client-IP fuers AUTH-7-Observe-Log (RAT-32: kein Gate mehr, nur Log)."""
    xri = request.headers.get("X-Real-IP")
    if xri:
        return xri.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


# RAT-32-Nicht-Verhandelbares: der Observe->Hard-Flip laeuft ueber die ENV-Naht
# XBUDDY_AUTH_MODE, NIEMALS ueber einen hartkodierten Code-Wert (Lehre
# #1427->#1430: „der Hard-Flip war hartkodiert, der Revert ein Code-Diff").
# Kill-Kriterium: liefert eine Route einem gepairten Geraet 401, wo es vorher
# 200 bekam -> ENV sofort zurueck auf observe (Zwei-Wege-Tuer, kein Deploy).
# Default hier ist "hard" (Nic-Setzung 2026-08-11, auth.md AUTH-3.a-UEBERHOLT)
# — abweichend vom seiten-Vorbild (Default "observe"), weil hoerspiel erst
# jetzt (T1833) gegated wird und ohne Observe-Vorlauf startet. Muster:
# seiten/main.py:469.
_AUTH_MODE = os.environ.get("XBUDDY_AUTH_MODE", "hard")


require_dual_gate = make_require_dual_gate(
    get_bot_token=_get_bot_token,
    get_client_ip=_client_ip,
    auth_401=_auth_401,
    default_mode=_AUTH_MODE,
)


# ============================================================
#  HSP-3a: Familie-Client-Accessor + Face-Pille-Helfer
# ============================================================

def _get_familie_client() -> "familie_client_mod.FamilieClient":
    """Gibt den FamilieClient zurück (gecacht oder frisch aus ENV).

    Test-Naht: wenn runtime['familie_client'] gesetzt, diesen nutzen.
    Produktiv-Pfad: neue Instanz aus HOERSPIEL_FAMILIE_ORIGIN (oder Default).
    """
    client = runtime.get("familie_client")
    if client is not None:
        return client
    origin = (os.environ.get(ENV_FAMILIE_ORIGIN) or _FAMILIE_DEFAULT_ORIGIN)
    return familie_client_mod.FamilieClient(origin_url=origin)


def _pille_vars(kind_id: str) -> dict:
    """Holt aktives Kind + Cycle-Ziel (naechstes_kind) aus Familie-Service.

    HSP-3a / HSP-43 — Nic-Setzung 2026-07-08 (supersedes ENTSCHEID-1263 F2):
    EIN Cycle-Toggle statt Face-Pillen-Reihe bei n≥3.

    Gibt dict zurück:
    - 'aktives_kind'  — Person | None (das in der URL adressierte Kind)
    - 'naechstes_kind' — {'person': Person, 'url': str} | None
        Nächste Instanz im Ring (wrap-around) nach dem aktiven kind_id,
        iteriert über config.INSTANZEN-Reihenfolge (mia→finn→emil→mia),
        gefiltert auf im Familie-Snapshot vorhandene Personen.
        None bei Solo-Betrieb (nur 1 Instanz im Snapshot) oder wenn aktives
        Kind selbst nicht im Snapshot ist.
    - 'andere_kinder' — Leer-Liste (nur noch für Template-Kompatibilität;
        der n≥3-Cycle-Toggle nutzt 'naechstes_kind').

    Fehlt eine Person im Snapshot (z. B. emil vor Provisionierung) oder ist
    der Familie-Service unerreichbar, fällt sie aus dem Ring — das naechstes_kind
    überspringt sie (PLAN-20-Geist).
    """
    client = _get_familie_client()
    registry = client.snapshot()

    aktives_kind = registry.get(kind_id)

    # Ring: nur Instanzen, die im Snapshot vorhanden sind (PLAN-20-Geist).
    ring_ids = [
        inst["kind_id"]
        for inst in config_mod.instanzen()
        if registry.get(inst["kind_id"]) is not None
    ]

    # Naechstes Kind im Ring (wrap-around), Muster: player.js nextKindId.
    naechstes_kind = None
    if len(ring_ids) > 1 and kind_id in ring_ids:
        idx = ring_ids.index(kind_id)
        next_id = ring_ids[(idx + 1) % len(ring_ids)]
        next_person = registry.get(next_id)
        if next_person is not None:
            naechstes_kind = {
                "person": next_person,
                "url": "/display/hoerspiel/%s/alben" % next_id,
            }

    return {
        "aktives_kind": aktives_kind,
        "naechstes_kind": naechstes_kind,
        "andere_kinder": [],  # Cycle-Toggle ersetzt Reihe (Nic-Setzung 2026-07-08).
    }


# ============================================================
#  URL-3a / HSP-26: kind_id-Self-Check
# ============================================================

def _self_kind_id() -> str:
    """Gibt die eigene kind_id der Instanz zurück (aus RuntimeConfig, HSP-26)."""
    cfg = runtime.get("runtime_config")
    if cfg is not None and hasattr(cfg, "kind_id"):
        return cfg.kind_id
    return config_mod.DEFAULT_KIND_ID


def _assert_self_kind(kind_id: str):
    """Prüft URL-`<kind_id>` gegen eigene Instanz-Identität (HSP-26, URL-3a).

    Gibt None zurück wenn ok, oder eine (response, status)-Tuple für 404.
    Fremde kind_ids werden nicht weitergeleitet — 404, nicht 302 (RAT-17).
    """
    if kind_id != _self_kind_id():
        return jsonify({"fehler": "unbekannte kind_id %r — dieser Service ist %r (HSP-26, URL-3a)"
                        % (kind_id, _self_kind_id())}), 404
    return None


# ============================================================
#  HSP-27b — Modell-Listen-Aggregation
# ============================================================

# HSP-27b / #1510 — ratifizierte V1-Modell-Liste für Mistral. Der direkte
# httpx-Adapter wurde mit #1281 entfernt (tools.llm-Route trägt den Pfad); die
# Konstante lebte danach nur noch als reiner Konstanten-Halter in
# `hoerspiel/providers/mistral.py`. #1510 re-homed sie hierher (die einzige
# Nutzung ist `_modelle_je_anbieter`) und löscht das Provider-Modul. Die
# Claude-Konstante bleibt asymmetrisch in `hoerspiel/providers/claude.py`
# (nicht löschgelistet). Label-Format: "<Bezeichnung> (<Charakterisierung>)".
_MISTRAL_AVAILABLE_MODELS: list[tuple[str, str]] = [
    ("mistral-large-2411",  "Large 2.1 (Frontier, kreativ)"),
    ("mistral-medium-2508", "Medium 3.1 (ausgewogen, V1-Default Mistral)"),
    ("mistral-small-2503",  "Small 3.1 (schnell, günstig)"),
]


def _modelle_je_anbieter() -> dict:
    """Gibt die AVAILABLE_MODELS aller Provider als Dict zurück (HSP-27b).

    Format: {"claude": [{"id": ..., "label": ...}, ...], "mistral": [...]}
    """
    result = {}
    try:
        from hoerspiel.providers.claude import AVAILABLE_MODELS as CLAUDE_MODELS
    except ImportError:
        try:
            from .providers.claude import AVAILABLE_MODELS as CLAUDE_MODELS
        except ImportError:
            CLAUDE_MODELS = []
    result["claude"] = [{"id": mid, "label": label} for mid, label in CLAUDE_MODELS]

    # #1510: Mistral-Modelle aus der re-homed lokalen Konstante (kein Import aus
    # dem gelöschten hoerspiel/providers/mistral.py mehr).
    result["mistral"] = [{"id": mid, "label": label}
                         for mid, label in _MISTRAL_AVAILABLE_MODELS]
    return result


def _provider_verfuegbar(cfg) -> list[str]:
    """Gibt nur Provider zurück, für die ein Key konfiguriert ist (HSP-17)."""
    verfuegbar = []
    if cfg.anthropic_key:
        verfuegbar.append("claude")
    if cfg.mistral_key:
        verfuegbar.append("mistral")
    return verfuegbar


def _validate_llm_model(provider: str, model: str) -> bool:
    """Prüft ob model in AVAILABLE_MODELS des Providers enthalten ist (HSP-27b)."""
    models = _modelle_je_anbieter()
    provider_models = models.get(provider, [])
    return any(m["id"] == model for m in provider_models)


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__, static_url_path="/display/hoerspiel/static")

# AUTH-11 (T1833/#1805): der implizite Flask-static-Endpoint
# (/display/hoerspiel/static/<path:filename>) traegt KEINE @app.route-
# Dekoration — Werkzeug registriert ihn intern als Endpunkt "static". Der
# einzige Ansatzpunkt ist die View-Funktion nach der App-Erzeugung. Bricht
# nichts: die Views laden ihr JS/CSS ueber denselben Origin, der Browser
# schickt denselben Cookie mit.
app.view_functions["static"] = require_dual_gate(mode=_AUTH_MODE)(app.view_functions["static"])

# AUTH-11-Ausnahme (Fix-Nachtrag #1857, Watchdog-Befund auf T1833/#1805): der
# generische Static-Gate-Tausch oben faengt AUCH das PWA-Manifest ab.
# `alben.html:12` traegt `<link rel="manifest" href="/display/hoerspiel/
# static/manifest.webmanifest">` OHNE `crossorigin="use-credentials"` — der
# Browser holt das Manifest per Fetch-Spec credential-los, bei JEDEM
# Seitenladen (nicht nur bei der Erst-Installation). Ein gepairter
# Kind-Tablet-Kiosk bekaeme sonst 401 auf sein Manifest bei jedem Laden (die
# #1437-Regressionsklasse, die auth.md AUTH-4 fuer genau diesen Fall
# dokumentiert: „credential-los per Fetch-Spec").
#
# Geprueft (AC3, #1857): kein Favicon, kein apple-touch-icon, kein
# Service-Worker unter /display/hoerspiel/static/ — nur das Manifest selbst
# ist credential-los referenziert. Die drei PNG-Icon-Dateien in
# hoerspiel/static/ (icon-192.png, icon-512.png, icon-maskable-512.png) sind
# NICHT im Manifest verlinkt (das Manifest zeigt auf
# /display/_shared/icons/arasaac/5915.png — bereits ratifizierte
# AUTH-11-Ausnahme) und in keinem Template/JS referenziert — sie bleiben
# ungenutzt hinter dem generischen Static-Gate. eltern.html/player.html
# haengen an /seiten/hoerspiel/… (separater seiten-Dienst, out of scope hier).
#
# Eigene, explizite Route statt einer Bedingung im Wrapper: Werkzeug matcht
# einen literalen Pfad IMMER vor dem generischen `<path:filename>`-Catch-all
# des impliziten Static-Endpunkts, unabhaengig von der Registrierungs-
# reihenfolge — die Route unten greift vor dem gegateten Fallback (Muster
# kibuddy/main.py:405-450, Watchdog-verifiziert inkl. Traversal-Proben).
# KEIN Pfad-Parameter: der Dateiname ist eine Konstante im Handler, Traversal
# ist damit strukturell unmoeglich.


@app.route("/display/hoerspiel/static/manifest.webmanifest", methods=["GET"])
def hoerspiel_manifest_public():
    """Oeffentliches PWA-Manifest (kein Gate, AUTH-11-Ausnahme s.o.)."""
    return send_from_directory(app.static_folder, "manifest.webmanifest")


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


# ---- Display-View (HSP-2, HSP-3 — Single-Page-Splitscreen Mia-View) ----

@app.route("/display/hoerspiel/<kind_id>/", methods=["GET"])
@app.route("/display/hoerspiel/<kind_id>", methods=["GET"])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-11 (T1833/#1805): Browser-Flaeche, Cookie-only.
def display_index_redirect(kind_id: str):
    """#1612: /display/hoerspiel/<kind_id>[/] rendert die Alben-View DIREKT (200).

    Früher 302-Redirect auf /alben. Der Redirect war die EINZIGE strukturelle
    Differenz zu funktionierenden Buddy-Tiles (plan/wetter liefern direkt 200):
    die Heim-Shell lädt diese URL als buddy-pane iframe.src, und über den
    externen Funnel/HTTP-2 verpuffte der 302 im iframe (ERR_CONNECTION_CLOSED —
    „keine Hörbücher auf dem Tablet"; Pi via Hairpin unauffällig). alben.html ist
    eine Single-Page-Splitscreen-View, die ihre Daten über absolute /api/v1/-Pfade
    holt — die Basis-URL ist egal, direktes Rendern bricht nichts. /alben bleibt
    als eigene Route erhalten (Direktzugriff/Lesezeichen).
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    pille = _pille_vars(kind_id)
    return render_template(
        "alben.html",
        aktives_kind=pille["aktives_kind"],
        naechstes_kind=pille["naechstes_kind"],
    )


@app.route("/display/hoerspiel/<kind_id>/alben", methods=["GET"])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-11 (T1833/#1805): Browser-Flaeche, Cookie-only.
def display_alben(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    # HSP-3a / HSP-43: Cycle-Toggle aus Familie-Service holen (Nic-Setzung 2026-07-08).
    pille = _pille_vars(kind_id)
    return render_template(
        "alben.html",
        aktives_kind=pille["aktives_kind"],
        naechstes_kind=pille["naechstes_kind"],
    )


# ---- Lese-Endpoints (HSP-17, Side-Effekt-frei) ----

@app.route("/api/v1/hoerspiel/<kind_id>/bible", methods=["GET"])
@require_init_data  # AUTH-11 (T1833/#1805): Profil der Fantasiewelt eines realen Kindes.
def bible(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    text = data_io.read_text_or_empty(os.path.join(_data_root(), "bible.md"))
    return text, 200, {"Content-Type": "text/markdown; charset=utf-8"}


@app.route("/api/v1/hoerspiel/<kind_id>/folgen-historie", methods=["GET"])
@require_init_data  # AUTH-11 (T1833/#1805): Profil der Fantasiewelt eines realen Kindes.
def folgen_historie(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    text = data_io.read_text_or_empty(os.path.join(_data_root(), "folgen-historie.md"))
    return text, 200, {"Content-Type": "text/markdown; charset=utf-8"}


@app.route("/api/v1/hoerspiel/<kind_id>/alben", methods=["GET", "POST"])
@require_init_data
def alben(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    if request.method == "GET":
        return jsonify(album_builder.liste_alben(_data_root()))
    return _post_alben(kind_id)


@app.route("/api/v1/hoerspiel/<kind_id>/alben/<album_id>/manifest", methods=["GET"])
@require_init_data
def album_manifest_get(kind_id: str, album_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    manifest = album_builder.lade_manifest(_data_root(), album_id)
    if manifest is None:
        return jsonify({"fehler": "album nicht gefunden"}), 404
    return jsonify(manifest)


# ---- Schreib-Endpoints (HSP-17, Eltern-Chat-Skill) ----

@app.route("/api/v1/hoerspiel/<kind_id>/folgen-vorschlag", methods=["POST"])
@require_init_data
def folgen_vorschlag(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    body = request.get_json(silent=True) or {}
    idee = (body.get("idee") or "").strip()
    if not idee:
        return jsonify({"fehler": "idee fehlt"}), 400
    # HSP-57/58: tiefe optional aus dem Request-Body; Default "mittel".
    tiefe = (body.get("tiefe") or "").strip() or "mittel"

    llm = _llm()
    if llm is None:
        return jsonify({
            "fehler": "llm-provider %s hat keinen API-Key — siehe HOERSPIEL_ANTHROPIC_KEY"
                      % (_runtime_cfg().llm_provider if _runtime_cfg() else "?"),
        }), 503

    bible_text = data_io.read_text_or_empty(os.path.join(_data_root(), "bible.md"))
    historie = data_io.read_text_or_empty(
        os.path.join(_data_root(), "folgen-historie.md"))
    naechste = _naechste_nummer_aus_historie(historie)
    # HSP-45 / #1263: Instanz-Rahmung der aktiven Instanz in den Story-Prompt
    # reichen (Name-Drift-Fix — Muster wie themen_endpoint :846). Leere Felder
    # fängt der transitionale Fallback in llm_service ab (mia/finn byte-gleich).
    instance = config_mod.load_instance(
        data_root=_data_root(),
        kind_id=_self_kind_id(),
        data_cfg=_data_cfg(),
    )
    try:
        vorschlag = llm_service.erzeuge_folgen_vorschlag(
            idee=idee, bible=bible_text, historie=historie,
            naechste_nummer=naechste, llm=llm,
            name=instance.name, alter=instance.alter,
            ton=instance.ton, perspektive=instance.perspektive,
            serien_name=instance.serien_name,
            # HSP-56/57: zielgruppe steuert Prompt-Wahl + Recherche-Vorschritt.
            # emil-Instanz (zielgruppe=erwachsen) löst den Recherche-Pfad aus;
            # Kind-Instanzen (mia/finn, zielgruppe=kind) bleiben unverändert.
            zielgruppe=instance.zielgruppe,
            tiefe=tiefe,
        )
    except ProviderError as e:
        return jsonify({"fehler": "llm-provider nicht erreichbar: %s" % e}), 503
    except llm_service.LLMServiceError as e:
        return jsonify({"fehler": "llm-antwort unbrauchbar: %s" % e}), 502
    return jsonify(vorschlag)


def _naechste_nummer_aus_historie(historie: str) -> int:
    # Re-export der gleichen Logik aus album_builder, damit der Endpoint
    # keinen Privat-Import braucht (Symmetrie zum POST /alben-Pfad).
    return album_builder._naechste_nummer(historie)


def _post_alben(kind_id: str):
    body = request.get_json(silent=True) or {}
    titel = (body.get("titel") or "").strip()
    text = (body.get("text") or "").strip()
    voice = (body.get("voice") or "").strip().lower()
    idee = (body.get("idee") or "").strip()
    # HSP-60: META-Block optional; wird vom Client aus dem /folgen-vorschlag-
    # Response übernommen und an baue_album weitergereicht für den Historic-Eintrag.
    meta_raw = body.get("meta")
    meta = meta_raw if isinstance(meta_raw, dict) else None
    if not titel or not text or voice not in config_mod.VALID_VOICES:
        return jsonify({"fehler": "pflichtfeld fehlt oder voice ungültig"}), 400

    tts = _tts()
    if tts is None:
        return jsonify({"fehler": "tts-engine nicht konfiguriert"}), 503

    llm = _llm()
    if llm is None:
        return jsonify({"fehler": "llm-provider nicht eingerichtet"}), 503

    dcfg = _data_cfg()
    pause_absatz = dcfg.pause_absatz_sek if dcfg is not None else config_mod.DEFAULT_PAUSE_ABSATZ_SEK
    pause_titel = dcfg.pause_titel_sek if dcfg is not None else config_mod.DEFAULT_PAUSE_TITEL_SEK

    # T1632: Multi-Voice-Verdrahtung — instance.voices an baue_album durchreichen
    instance = config_mod.load_instance(
        data_root=_data_root(),
        kind_id=kind_id,
        data_cfg=dcfg,
    )

    try:
        ergebnis = album_builder.baue_album(
            titel=titel, text=text, voice=voice, idee=idee,
            data_root=_data_root(),
            kind_id=_self_kind_id(),
            llm=llm, tts_engine=tts,
            now=runtime["now"],
            pause_absatz_sek=pause_absatz,
            pause_titel_sek=pause_titel,
            meta=meta,
            voices=instance.voices,
        )
    except tts_service.SharedAssetsMissing as e:
        return jsonify({"fehler": str(e)}), 412
    except TTSError as e:
        return jsonify({"fehler": "tts-engine nicht erreichbar: %s" % e}), 503
    except ProviderError as e:
        return jsonify({"fehler": "llm-provider nicht erreichbar: %s" % e}), 503

    return jsonify({
        "album-id": ergebnis.album_id,
        "manifest-pfad": ergebnis.manifest_pfad,
        "dauer-sek-gesamt": ergebnis.dauer_sek_gesamt,
        "cached": ergebnis.cached,
    })


# ---- Config-Endpoints (HSP-17, V2-Provider-Wechsel-Vorgriff) ----

def _build_config_response(cfg, dcfg, instance_cfg=None) -> dict:
    """Baut die vollständige GET /config-Antwort (HSP-17/34/41).

    T1382/OPEN-HSP-X: instance_cfg.serien_name hat Vorrang (spiegelt LLM-Pfad
    OPEN-HSP-W, :543); dcfg.serien_name als Fallback (PATCH-gesetzt); neutral
    ("") wenn beides leer — kein Modul-Default (Display/config-Neutralisierung).
    """
    public = cfg.to_public_dict()
    if dcfg is not None:
        public["default_voice"] = dcfg.default_voice
        public["serien_name"] = (
            instance_cfg.serien_name
            if instance_cfg and instance_cfg.serien_name
            else dcfg.serien_name
        )
        public["pause_absatz_sek"] = dcfg.pause_absatz_sek
        public["pause_titel_sek"] = dcfg.pause_titel_sek
        public["playback_tempo"] = dcfg.playback_tempo
    else:
        public.setdefault("default_voice", config_mod.DEFAULT_VOICE)
        public.setdefault("pause_absatz_sek", config_mod.DEFAULT_PAUSE_ABSATZ_SEK)
        public.setdefault("pause_titel_sek", config_mod.DEFAULT_PAUSE_TITEL_SEK)
        public.setdefault("playback_tempo", config_mod.DEFAULT_PLAYBACK_TEMPO)
    public["voices_verfuegbar"] = list(config_mod.VALID_VOICES)
    public["provider_verfuegbar"] = _provider_verfuegbar(cfg)
    public["modelle_je_anbieter"] = _modelle_je_anbieter()
    return public


@app.route("/api/v1/hoerspiel/<kind_id>/config", methods=["GET", "PATCH"])
@require_init_data
def config_endpoint(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    cfg = _runtime_cfg()
    if cfg is None:
        return jsonify({"fehler": "runtime-config nicht geladen"}), 503

    if request.method == "GET":
        # T1382: instance.json serien_name reichen — wie LLM-Pfad (:543).
        _instance = config_mod.load_instance(_data_root(), _self_kind_id(), data_cfg=_data_cfg())
        return jsonify(_build_config_response(cfg, _data_cfg(), _instance))

    body = request.get_json(silent=True) or {}

    # Runtime-Felder (llm_provider, llm_model).
    try:
        new_cfg = config_mod.patch_runtime(cfg, body)
    except config_mod.ConfigError as e:
        return jsonify({"fehler": str(e)}), 422

    # Modell-Validierung gegen AVAILABLE_MODELS des Providers (HSP-27b).
    if ("llm_model" in body and body["llm_model"] is not None
            and not _validate_llm_model(new_cfg.llm_provider, new_cfg.llm_model)):
        return jsonify({
            "fehler": "llm_model %r ist für Anbieter %r nicht bekannt (HSP-27b)"
                      % (new_cfg.llm_model, new_cfg.llm_provider),
        }), 422

    runtime["runtime_config"] = new_cfg
    # LLM-Cache invalidieren — Provider-/Modell-Wechsel zwingt Neuaufbau.
    if (new_cfg.llm_provider, new_cfg.llm_model) != (cfg.llm_provider, cfg.llm_model):
        runtime["llm"] = None

    # Daten-Konfig-Felder (default_voice, pause_*, playback_tempo).
    dcfg = _data_cfg()
    try:
        new_dcfg = config_mod.patch_data(dcfg, body) if dcfg is not None else dcfg
    except config_mod.ConfigError as e:
        return jsonify({"fehler": str(e)}), 422
    runtime["data_config"] = new_dcfg

    # Persistenz (DCOMP-4, HSP-27): Werte überleben Restart.
    # Vorher schrieb PATCH nur den Memory-Snapshot — playback_tempo, default_voice
    # etc. fielen nach systemctl restart auf Datei-Default zurück.
    if new_dcfg is not None:
        try:
            config_mod.persist_data(new_dcfg)
        except OSError as e:
            logger.warning("hoerspiel/config: persist_data fehlgeschlagen — %s", e)
            # Kein 5xx an den Client — Memory-Stand bleibt aktuell, nur Restart-Persistenz
            # ist betroffen. Eltern sehen den Wert sofort, nach Restart fällt er zurück.

    # T1382: instance.json serien_name reichen — wie LLM-Pfad (:543).
    _instance = config_mod.load_instance(_data_root(), _self_kind_id(), data_cfg=new_dcfg)
    return jsonify(_build_config_response(new_cfg, new_dcfg, _instance))


# ---- Audio-Stream-SSE (HSP-42 / PANEL-13) ----
#
# HSP-41 (audio_ziel-Routing-Weiche) ist aufgehoben — Audio immer lokal am App-Gerät.
# /audio-stream (SSE) bleibt als aktive PANEL-13-Naht: controller/app-panel/app.js:819-966
# öffnet pro HSP-Instanz eine EventSource auf diesen Endpoint (audio_play-Events).
# /play-extern (keine Nicht-Test-Caller) wurde mit HSP-42 Option B (Nic 2026-07-27) entfernt.
# Auth: PUBLIC (AUTH-6-Backlog).

SSE_HEARTBEAT_SECONDS = 15
_audio_subscribers: list[queue.Queue] = []
_audio_subscribers_lock = threading.Lock()


def _audio_register_subscriber() -> queue.Queue:
    q: queue.Queue = queue.Queue()
    with _audio_subscribers_lock:
        _audio_subscribers.append(q)
    return q


def _audio_unregister_subscriber(q: queue.Queue) -> None:
    with _audio_subscribers_lock, contextlib.suppress(ValueError):
        _audio_subscribers.remove(q)


def _audio_broadcast(event: dict) -> None:
    """Ruhende Naht: Pusht ein audio_play-Event an alle verbundenen Panel-PWAs.

    Der einzige Producer (/play-extern, HSP-42) wurde 2026-07-27 entfernt.
    Diese Funktion ist aktuell aufruferlos — /audio-stream sendet nur Heartbeats.
    Reaktivierung gebunden an #1471-Rückbau / HSP-44 (neuer Producer-Trigger).
    Consumer: controller/app-panel/app.js:819-966 (PANEL-13 Silent-Audio-Prime).
    """
    with _audio_subscribers_lock:
        subs = list(_audio_subscribers)
    for q in subs:
        with contextlib.suppress(queue.Full):
            q.put_nowait(event)


def _sse_pack(event: dict | None) -> str:
    """Formatiert ein Event als SSE-Nachricht (analog router/main.py:147)."""
    if event is None:
        return ": heartbeat\n\n"
    return "data: %s\n\n" % json.dumps(event, ensure_ascii=False)


def _audio_event_stream():
    """SSE-Generator: initialer Heartbeat, dann Events oder periodische Heartbeats.

    Heartbeats werden als data-Events gesendet (statt SSE-Comments), damit das
    Client-JS sie als Lebenszeichen verbuchen kann — Comments triggern kein
    `message`-Event im Browser. Watchdog im Client erkennt damit stillgewordene
    Verbindungen und reconnectet (R6 aus Track-E: Mobile-Browser kappen
    EventSource im Hintergrund, ohne onerror auszulösen).
    """
    q = _audio_register_subscriber()
    try:
        # Initialer Heartbeat — Browser bestätigt Verbindung
        yield 'data: {"type":"heartbeat"}\n\n'
        while True:
            try:
                event = q.get(timeout=SSE_HEARTBEAT_SECONDS)
                yield _sse_pack(event)
            except queue.Empty:
                yield 'data: {"type":"heartbeat"}\n\n'
    finally:
        _audio_unregister_subscriber(q)


@app.route("/api/v1/hoerspiel/<kind_id>/audio-stream", methods=["GET"])
@require_init_data  # AUTH-11 (T1833/#1805): war PUBLIC (AUTH-6), jetzt Cookie-Pfad.
def audio_stream(kind_id: str):
    """HSP-42: SSE-Stream für Audio-Source-Push an Panel-PWA.

    Caller: app-panel-PWA (controller/app-panel/), pro HSP-Instanz eine
    EventSource-Verbindung. Browser-Native-Reconnect übernimmt Reconnect
    bei Tab-visibility-Change (DC-7-Pattern). EventSource kann keinen
    Authorization-Header setzen — die Identitätsquelle ist der
    xbuddy_session-Cookie, den der Browser bei einem SSE-Connect wie bei
    jedem anderen same-origin-GET automatisch mitschickt.

    Auth: AUTH-11 (T1833/#1805) — require_init_data (Cookie-Zweig trägt
    den echten Aufrufer; Loopback bleibt als Server-zu-Server-Fallback).
    Vormals PUBLIC (AUTH-6, Trigger „Phase 4 HSP-Audio-Routing" — überholt).
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    response = Response(_audio_event_stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"  # nginx-Buffering aus
    return response


# ---- Themen-Endpoint (HSP-38, URL-3a, RAT-17) ----

@app.route("/api/v1/hoerspiel/<kind_id>/themen", methods=["GET"])
@require_init_data
def themen_endpoint(kind_id: str):
    """HSP-38: GET /api/v1/hoerspiel/<kind_id>/themen → kuratierte Themen-Liste.

    Kein ?alter=-Query mehr (RAT-17, URL-3a): Alter zieht der Buddy aus
    seiner instance.json. kind_id-Self-Check via _assert_self_kind (HSP-26).

    200 {"kind_id": "mia", "name": "Mia", "alter": 4, "themen": [...]}
    404 wenn kind_id unbekannt (kein hoerspiel-Pfad für diesen Wert)
    422 wenn das Alter der Instanz nicht in themen_je_alter gepflegt ist
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err

    instance = config_mod.load_instance(
        data_root=_data_root(),
        kind_id=_self_kind_id(),
        data_cfg=_data_cfg(),
    )

    alter_str = str(instance.alter)
    themen = instance.themen_je_alter.get(alter_str)
    if themen is None:
        return jsonify({
            "fehler": "Themen-Liste für Alter %s nicht gepflegt — "
                      "instance.json.themen_je_alter muss Schlüssel %r tragen. "
                      "Eltern können im Chat eine eigene Idee geben." % (
                          alter_str, alter_str),
        }), 422

    return jsonify({
        "kind_id": instance.kind_id,
        "name": instance.name,
        "alter": instance.alter,
        "themen": themen,
    })


# ---- Audio-Streaming-Endpoint (HSP-37) ----

@app.route("/api/v1/hoerspiel/<kind_id>/alben/<album_id>/audio/<path:track_filename>",
           methods=["GET"])
@require_init_data  # AUTH-11 (T1833/#1805): war PUBLIC (AUTH-4), jetzt Cookie-Pfad.
def album_audio(kind_id: str, album_id: str, track_filename: str):
    """HSP-37: Audio-Track streamen mit Range-Requests.

    Auth: AUTH-11 (T1833/#1805) — require_init_data. Der frühere PUBLIC-Stand
    (AUTH-4, auth.md:366) ist überholt (Nic-Setzung 2026-08-11: alle Adressen
    hinter dem Cookie). Das reale Kind-Tablet-Playback läuft ohnehin nicht
    über diesen Pfad, sondern über den Manifest-`audio-asset`, der auf
    `/display/hoerspiel/<kind_id>/data/alben/…` zeigt (dual-gate-geschützt,
    `album_manifest.py`); diese Route hat aktuell keinen realen Caller
    (verifiziert: `hoerspiel/static/eltern.js:726-731`-Kommentar). Gaten
    bricht daher kein Live-Playback. send_from_directory blockt Pfad-
    Traversal. `Content-Type: audio/mpeg`, `Cache-Control: private, max-age=86400`.
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    audio_dir = os.path.join(_data_root(), "alben", album_id, "audio")
    if not os.path.isdir(audio_dir):
        return jsonify({"fehler": "album nicht gefunden"}), 404

    response = send_from_directory(
        audio_dir,
        track_filename,
        mimetype="audio/mpeg",
        conditional=True,  # aktiviert Range-Request-Support via Flask/Werkzeug
    )
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


# ---- Resume-Endpoints (HSP-36) ----

@app.route("/api/v1/hoerspiel/<kind_id>/resume", methods=["GET", "PUT"])
@require_init_data
def resume_endpoint(kind_id: str):
    """HSP-36: Resume-Stand lesen (GET) und setzen (PUT).

    GET ?album=<id> → {"album": "<id>", "track": <int>, [status: "neu"]} (200; status="neu" wenn kein Stand existiert — HSP-36).
    PUT Body: {"album": "<id>", "track": <position>} → 200 + Echo.

    V1: in-process-Store (runtime['resume_store']). Last-Write-Wins.
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    store = runtime.get("resume_store")
    if store is None:
        store = {}
        runtime["resume_store"] = store

    if request.method == "GET":
        album_id = (request.args.get("album") or "").strip()
        if not album_id:
            return jsonify({"fehler": "album-Parameter fehlt"}), 400
        if album_id not in store:
            # HSP-36 (geändert): kein Stand → 200 mit Default-Body, kein 404.
            # Frontend fragt präventiv für jede Folge; 404-Burst (~8x) ist vermeidbar.
            return jsonify({"album": album_id, "track": 0, "status": "neu"})
        return jsonify({"album": album_id, "track": store[album_id]})

    # PUT
    body = request.get_json(silent=True) or {}
    album_id = (body.get("album") or "").strip()
    track = body.get("track")
    if not album_id or track is None:
        return jsonify({"fehler": "album und track sind Pflichtfelder"}), 400
    try:
        track_pos = int(track)
    except (TypeError, ValueError):
        return jsonify({"fehler": "track muss eine Ganzzahl sein"}), 400
    store[album_id] = track_pos
    return jsonify({"album": album_id, "track": track_pos})


# ---- Shared-Assets (HSP-17/22/29) ----

@app.route("/api/v1/hoerspiel/<kind_id>/shared-assets/status", methods=["GET"])
@require_init_data  # AUTH-11 (T1833/#1805): war PUBLIC (AUTH-4/Diagnose), jetzt Cookie-Pfad.
def shared_assets_status(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    return jsonify(tts_service.status_shared_assets(_data_root()))


@app.route("/api/v1/hoerspiel/<kind_id>/shared-assets/rebuild", methods=["POST"])
@require_init_data  # AUTH-11 (T1833/#1805): schreibend, hoechste Prioritaet — s.u.
def shared_assets_rebuild(kind_id: str):
    """HSP-22/29: alle vier Shared-Assets-MP3s (Intro/Outro je Voice) neu bauen.

    Auth: AUTH-11 (T1833/#1805) — require_init_data. Kein Docstring/Kommentar
    hier behauptete früher „loopback-only", aber der Decorator selbst fehlte
    komplett: am 2026-08-11 war die Route live ohne Cookie erreichbar und
    antwortete nach 24s mit 200 (unautorisierter Rebuild-Trigger, teuer per
    TTS-Kosten). Jetzt hart gegated wie jede andere AUTH-3-Schreibroute.
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    tts = _tts()
    if tts is None:
        return jsonify({"fehler": "tts-engine nicht konfiguriert"}), 503
    try:
        return jsonify(tts_service.rebuild_alle(data_root=_data_root(), engine=tts))
    except TTSError as e:
        return jsonify({"fehler": "tts-engine nicht erreichbar: %s" % e}), 503


# ---- Daten-Router (HSP-26 `GET /display/hoerspiel/<kind_id>/data/<sub>`, URL-3a) ----

@app.route("/display/hoerspiel/<kind_id>/data/<path:sub>", methods=["GET"])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-11 (T1833/#1805): Browser-Flaeche, Cookie-only.
def display_data(kind_id: str, sub: str):
    """Liefert Audio-/Cover-Assets aus dem Daten-Bereich aus (HSP-26, URL-3a).

    Streng auf Subpfade unter `data/` begrenzt — `send_from_directory`
    blockt Pfad-Traversal.
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    return send_from_directory(_data_root(), sub)


# ── Health-Check (SVC-1) ─────────────────────────────────────────────────

@app.route("/healthz", methods=["GET"])
def healthz():
    """SVC-1: Health-Endpoint — liefert immer 200 + OK."""
    return jsonify({"ok": True}), 200


# ============================================================
#  Entrypoint (HSP-28)
# ============================================================

def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Hörspiel-Buddy-App V1")
    p.add_argument("--config", dest="config_file", default=None,
                   help="Pfad zur Runtime-Config (HSP-27)")
    p.add_argument("--data-config", dest="data_config_file", default=None,
                   help="Pfad zur Daten-Konfig (HSP-27)")
    p.add_argument("--data-root", dest="data_root", default=None,
                   help="Daten-Bereich (HSP-25; sonst $HOERSPIEL_DATA_ROOT / Default)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    return p.parse_args(argv)


# T1084: Der strukturierte Folgen-Pfad (HSP-11) läuft seit #1084 über
# T1492 (LLMP-S13 n=2-Naht): Slot-Namensbildung über tools.llm.litellm_slot_for_provider
# (statt lokaler Tabelle _LIB_SLOT_FOR_PROVIDER, die strukturell identisch mit
# eltern-chat/providers/lib_adapter.py war — n=2 → Naht zentralisiert).
# Lazy-Import in _build_llm analog LibSingleshotAdapter (kein Modul-Load-Zyklus).
_CALLER = "hoerspiel"

# T1454: Der Recherche-Agent (web_search-Vorschritt, HSP/T1371) bleibt auf dem
# anthropic-Hand-Vendor — der litellm-Vendor deklariert kein `web_search`.
# Entkoppelt vom Struktur-/Synopse-Slot oben (`agent_slot`-Param im Adapter).
# Nur der Claude-Brand recherchiert (der Mistral-Brand degradiert den
# Vorschritt bereits über `agent.capabilities`, T1371).
_AGENT_SLOT_FOR_PROVIDER = {
    "claude": "hoerspiel-anthropic-api-key",
    "mistral": "hoerspiel-anthropic-api-key",
}

# T1281: MAX_TOKENS aus den entfernten Alt-Providern hier zentralisiert.
# claude=8192 — Sicherheits-Puffer für ~3500-Token-Folge. T1807/AC3, GEMESSEN
# statt geraten (Modell jetzt claude-opus-5): die Folgen-Generierung
# (`complete_structured` → `_vendor/litellm.singleshot_structured`) zwingt
# `tool_choice` auf das EINE `folgen_vorschlag`-Tool — Anthropic schaltet
# automatisches Thinking bei erzwungenem `tool_choice` AUS. Realer Lauf über
# die echte Route (identisches Schema/System-Prompt-Muster, max_tokens=8192):
# 5597/8192 Token verbraucht (68 %), 0 Thinking-Blöcke, finish_reason
# "tool_calls" (nicht "length") — der Modell-Wechsel ändert an diesem Budget
# nichts. OFFEN (nicht gemessen, gleicher Konstanten-Topf): `complete()`
# (Synopse, `get_completion`/Freitext, kein Tool-Zwang) und
# `recherche_agent()` (`get_agent` auf dem anthropic-Hand-Vendor, ebenfalls
# KEIN erzwungener `tool_choice`) hängen an DERSELBEN 8192-Konstante, sind
# aber strukturell dem eltern-chat-Fall ähnlicher (Thinking könnte dort
# an sein) — nicht live gemessen (hoerspiel/providers/lib_adapter.py ist in
# diesem Ticket nicht im Schreib-Scope, siehe Handoff-Befund).
# mistral=4096 — ratifizierter Wert HSP-27b.
_MAX_TOKENS_FOR_PROVIDER = {
    "claude": 8192,
    "mistral": 4096,
}


def _build_llm(cfg) -> LLMProvider | None:
    if cfg.llm_provider == "claude":
        if not cfg.anthropic_key:
            return None
    elif cfg.llm_provider == "mistral":
        if not cfg.mistral_key:
            return None
    else:
        return None

    from tools.llm import litellm_slot_for_provider

    from .providers.lib_adapter import LibSingleshotAdapter
    slot = litellm_slot_for_provider(_CALLER, cfg.llm_provider)
    agent_slot = _AGENT_SLOT_FOR_PROVIDER[cfg.llm_provider]
    max_tokens = _MAX_TOKENS_FOR_PROVIDER[cfg.llm_provider]
    # `model` + `max_tokens` durchreichen: Modell-Erhalt (z. B. claude-opus-5,
    # T1807) und Token-Limit (T1084: DEFAULT_MAX_TOKENS=2048 < ~3500 Token
    # Folgentext).
    # LLMP-S13 (#1463): der Mistral-`mistral/`-Präfix ist jetzt ZENTRAL gelöst —
    # `tools.llm` normalisiert den blanken Mistral-Modellnamen
    # (`mistral-medium-2508` → `mistral/mistral-medium-2508`) vor den `get_*`-
    # Sichten (`_resolver.normalize_model`, gegatet auf den litellm-Motor). Die
    # hoerspiel-AVAILABLE_MODELS führen weiter blanke Namen — dieser Pfad reicht
    # sie unverändert durch (früher #1454-Deploy-Config-Frage, jetzt am Motor
    # normalisiert). Claude-Modelle bleiben blank — litellm erkennt sie so.
    # `agent_slot` (T1454): Recherche-Agent bleibt anthropic (web_search-nativ).
    return LibSingleshotAdapter(
        slot=slot, model=cfg.llm_model, max_tokens=max_tokens,
        agent_slot=agent_slot,
    )


def _build_tts(cfg):
    if not (cfg.azure_endpoint and cfg.azure_deployment and cfg.azure_key):
        return None
    from .tts.azure import AzureTTSEngine
    return AzureTTSEngine(endpoint=cfg.azure_endpoint, api_key=cfg.azure_key,
                          deployment=cfg.azure_deployment)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    runtime_cfg = config_mod.resolve_runtime(args.config_file)
    data_cfg = config_mod.resolve_data(args.data_config_file)

    if args.host:
        runtime_cfg.listen_host = args.host
    if args.port:
        runtime_cfg.listen_port = args.port
    if args.log_level:
        runtime_cfg.log_level = args.log_level

    logsetup.setup(runtime_cfg.log_level)

    data_root = (args.data_root
                 or os.environ.get(config_mod.ENV_DATA_ROOT)
                 or config_mod.DEFAULT_DATA_ROOT)
    os.makedirs(data_root, exist_ok=True)

    configure(
        runtime_config=runtime_cfg,
        data_config=data_cfg,
        data_root=data_root,
        llm_factory=_build_llm,
        tts_engine=_build_tts(runtime_cfg),
    )

    logger.info("Hörspiel-Buddy hört auf http://%s:%s (provider=%s, model=%s, data=%s)",
                runtime_cfg.listen_host, runtime_cfg.listen_port,
                runtime_cfg.llm_provider, runtime_cfg.llm_model, data_root)
    app.run(host=runtime_cfg.listen_host, port=runtime_cfg.listen_port,
            debug=False, threaded=True)


if __name__ == "__main__":
    main()
