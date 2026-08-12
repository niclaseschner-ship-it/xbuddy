#!/usr/bin/env python3
"""KIBuddy-App — HTTP-Schnittstelle + Entrypoint (KIBUDDY-24/25).

Endpunkte (KIBUDDY-24):

  GET  /display/kibuddy/frage            — Frage-View (Stub, Stück B baut UI)
  POST /api/v1/kibuddy/frage             — Audio → STT → LLM → Buzzwords → TTS
  POST /api/v1/kibuddy/vorlesen          — Text-zu-TTS für Vorlese-Knopf
  POST /api/v1/kibuddy/reset             — Session-Memory + Audio-Cache leeren
  GET  /api/v1/kibuddy/audio/<id>.mp3   — MP3 aus Audio-Cache
  GET  /api/v1/kibuddy/config            — Aktuelle Config (ohne Keys)
  PUT  /api/v1/kibuddy/config            — Aufnahme-Quelle setzen (KAQS-Skill)
  GET  /api/v1/kibuddy/prompt            — Aktuellen System-Prompt lesen
  PUT  /api/v1/kibuddy/prompt            — Neuen System-Prompt schreiben
  GET  /healthz                          — Health-Check (SVC-1)

Port: 5054 (PORT-2, KIBUDDY-25). Service: xbuddy-kibuddy (SVC-1).

Session-Cookie: kibuddy_sid (HttpOnly, SameSite=Lax) pro Browser (KIBUDDY-16).
Icon-Lookup: clientseitig via Browser-Fetch-API (KIBUDDY-17 Buzzword-Render, T865).
"""

import argparse
import json
import logging
import os
import sys

from flask import (
    Flask,
    Response,
    g,
    jsonify,
    make_response,
    render_template,
    request,
    send_from_directory,
    stream_with_context,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import familie_client as _familie_client_mod  # noqa: E402
from tools import logsetup  # noqa: E402
from tools.familie_client import DEFAULT_ORIGIN as _FAMILIE_DEFAULT_ORIGIN  # noqa: E402
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.initdata.auth_gate import (  # noqa: E402
    make_require_dual_gate,
    make_require_init_data,
)
from tools.llm import LLMProvider  # noqa: E402 — LLMP-S8 Migration (T1082)
from tools.service_diagnostics import register_version  # noqa: E402

if __package__:
    from . import config as config_mod
    from . import data_io, llm_service, stt_service, tts_service
    from .llm_service import ProviderError  # LLMP-S8 Tuple-Re-Export, additiv-rückrollbar
    from .session_memory import SID_COOKIE, SessionMemory, SessionRegistry
    from .stt.azure_whisper import STTError
    from .tts.azure import TTSError
else:  # python3 kibuddy/main.py
    sys.path.insert(0, _REPO_ROOT)
    from kibuddy import config as config_mod
    from kibuddy import data_io, llm_service, stt_service, tts_service
    from kibuddy.llm_service import ProviderError  # LLMP-S8 Tuple-Re-Export
    from kibuddy.session_memory import SID_COOKIE, SessionMemory, SessionRegistry
    from kibuddy.stt.azure_whisper import STTError
    from kibuddy.tts.azure import TTSError


logger = logging.getLogger(__name__)

# ============================================================
#  Laufzeit-Zustand (Test-Naht analog hoerspiel/main.py)
# ============================================================

runtime: dict = {
    "runtime_config": None,    # config.RuntimeConfig
    "data_root": None,         # str — SVC-5-Daten-Bereich
    "llm_factory": None,       # cfg -> LLMProvider
    "llm": None,               # LLMProvider (Cache)
    "stt_engine": None,        # AzureWhisperSTT (oder Fake in Tests)
    "tts_engine": None,        # AzureTTSEngine (oder Fake in Tests)
    "session_registry": None,  # SessionRegistry (KIBUDDY-16 Cookie-Session)
    "bot_token": None,          # AUTH-3 (T1321): Bot-Token — Test-Naht oder ENV
    "init_data_config": None,   # AUTH-3 (T1321): tma-Header-Validierungs-Config
    "familie_client": None,     # AUTH-3 (T1321): FAM-7-Client (get_telegram_ids)
}


def configure(
    *,
    runtime_config,
    data_root: str,
    llm_factory=None,
    llm=None,
    stt_engine=None,
    tts_engine=None,
    session_registry=None,     # Registry-Injection (Test-Naht, KIBUDDY-16)
    bot_token=None,            # AUTH-3 (T1321): Bot-Token — Test-Naht oder ENV
    init_data_config=None,     # AUTH-3 (T1321): tma-Header-Validierungs-Config
    familie_client=None,       # AUTH-3 (T1321): FAM-7-Client (get_telegram_ids)
) -> None:
    """Setzt Konfiguration und Adapter-Fabriken (Test-Naht).

    `llm_factory(cfg) -> LLMProvider` baut den Provider.
    In Tests bleibt `llm_factory=None` und `llm=` wird direkt gesetzt.

    `session_registry` (SessionRegistry) ist die Test-Naht — erlaubt Injection
    einer vorbereiteten Registry mit fest gesetzten SIDs via Cookie.

    `bot_token` / `init_data_config` / `familie_client` (AUTH-3, T1321):
    Auth-Naht für Tests (Muster essen); im Produktiv-Betrieb aus ENV.
    """
    runtime["runtime_config"] = runtime_config
    runtime["data_root"] = data_root
    runtime["llm_factory"] = llm_factory
    runtime["llm"] = llm
    runtime["stt_engine"] = stt_engine
    runtime["tts_engine"] = tts_engine
    runtime["session_registry"] = session_registry if session_registry is not None else SessionRegistry()

    # AUTH-3 Hart-Auth (T1321): Test-Naht analog essen.
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if init_data_config is not None:
        runtime["init_data_config"] = init_data_config
    if familie_client is not None:
        runtime["familie_client"] = familie_client


def _runtime_cfg():
    return runtime["runtime_config"]


def _data_root() -> str:
    root = runtime["data_root"]
    if not root:
        raise RuntimeError("kibuddy: data_root nicht konfiguriert (configure())")
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
    built = factory(cfg)
    runtime["llm"] = built
    return built


def _stt():
    return runtime.get("stt_engine")


def _tts():
    return runtime.get("tts_engine")


def _registry() -> SessionRegistry:
    return runtime["session_registry"]


def _get_or_create_session() -> tuple[str, SessionMemory]:
    """Liest kibuddy_sid-Cookie oder erzeugt eine neue SID (KIBUDDY-16).

    Gibt (sid, memory) zurück.
    Wenn kein Cookie da war, wird g._kibuddy_new_sid gesetzt — der
    after_request-Hook setzt dann den Cookie konsistent für alle Endpunkte.
    """
    registry = _registry()
    sid = request.cookies.get(SID_COOKIE)
    if sid is None:
        sid = registry.new_sid()
        g._kibuddy_new_sid = sid  # Signal für after_request-Hook (FIX-5)
    return sid, registry.get_or_create(sid)


# ============================================================
#  AUTH-3 Hart-Auth (T1321 — auth.md AUTH-2/3/5/8/9)
# ============================================================
#
# Wörtliche Übernahme des essen-Decorators (essen/main.py, T948). Der
# Audit-Funnel-Befund #1338 klassifiziert die /api/v1/kibuddy/*-Datenrouten
# neu als AUTH-3 (hart geschützt): extern war der KiBuddy-Prompt überschreibbar.
# Der `kibuddy_sid`-after_request-Hook (ANDERER Cookie-Name) koexistiert
# konfliktfrei mit `xbuddy_session`.

# ENV-Variable für Bot-Token (APP-7 / MAD-9): cluster-weit, wie essen.
_ENV_BOT_TOKEN = "ELTERNCHAT_BOT_TOKEN"
# CONFIG-5: Familie-Service-Origin per Komponenten-ENV.
_ENV_FAMILIE_ORIGIN = "KIBUDDY_FAMILIE_ORIGIN"


def _get_bot_token():
    """Bot-Token aus runtime-Dict (Test-Naht), ENV (APP-7) oder Zugangsdaten-Store (T1440).

    Reihenfolge: runtime['bot_token'] → os.environ[ELTERNCHAT_BOT_TOKEN] → Store-Slot
    'eltern-chat-bot-token'. Der Store-Read ist lazy und defensiv — fehlt der Store
    oder schlägt der Import fehl, wird None zurückgegeben (kein Crash).
    """
    token = runtime.get("bot_token") or os.environ.get(_ENV_BOT_TOKEN)
    if token:
        return token
    try:
        from tools.zugangsdaten import Zugangsdaten, resolve_store_path
        return Zugangsdaten(resolve_store_path()).get("eltern-chat-bot-token")
    except Exception:
        return None


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


def _secret_preflight(cfg=None):
    """SVC-7 — Startup-Secret-Preflight: Pflicht-Secrets vor app.run prüfen (#1447, #1493).

    Löst alle Pflicht-Secrets mit derselben Reihenfolge wie zur Laufzeit auf
    (runtime-Dict → ENV → Zugangsdaten-Store, via _get_bot_token).
    Nur Präsenz-Prüfung — kein Test-Call gegen den Anbieter (SVC-7).
    Fehlt ein Secret: Log-Zeile 'FEHLT: <slot/env-name>' + sys.exit(1).

    #1493: zusätzlich die config-gated LLM-Slots auf PRÄSENZ prüfen — jeweils NUR,
    wenn der zugehörige Pfad beim Boot auch wirklich einen `tools.llm`-Slot eager
    zieht. So bricht ein fehlender LLM-Slot hier sichtbar (FEHLT: <slot> + exit)
    statt als roher `LLMCapabilityError` im `_build_*`-Pfad. `cfg` ist der
    RuntimeConfig-Snapshot (main() reicht ihn durch); None überspringt die
    LLM-Slot-Prüfung (Rückwärtskompat für Alt-Aufrufe/Tests, die nur das
    Bot-Token prüfen).
    """
    token = _get_bot_token()
    if not token:
        logger.critical("FEHLT: eltern-chat-bot-token (ELTERNCHAT_BOT_TOKEN)")
        sys.exit(1)

    if cfg is None:
        return

    from tools.llm import slot_present

    # LLM-Chat-Slot: NUR im claude-Pfad MIT anthropic_key (exakt der `_build_llm`-
    # Gate, main:709-713) — sonst baut kibuddy die get_chat-Fassade beim Boot gar
    # nicht, und der Slot ist nicht boot-kritisch.
    if cfg.llm_provider == "claude" and cfg.anthropic_key \
            and not slot_present("kibuddy-litellm-api-key"):
        logger.critical(
            "FEHLT: kibuddy-litellm-api-key — LLM-Chat-Slot fehlt im "
            "Zugangsdaten-Speicher (llm_provider=claude) (SVC-7/#1493)")
        sys.exit(1)

    # STT-Slot: NUR wenn stt_provider=='litellm' (LitellmSTTEngine zieht ihn,
    # main:717-725).
    if cfg.stt_provider == "litellm" and not slot_present(cfg.litellm_stt_slot):
        logger.critical(
            "FEHLT: %s — STT-Slot fehlt im Zugangsdaten-Speicher "
            "(stt_provider=litellm) (SVC-7/#1493)", cfg.litellm_stt_slot)
        sys.exit(1)

    # TTS-Slot: NUR wenn tts_provider=='litellm' (LitellmTTSEngine zieht ihn,
    # main:748-756).
    if cfg.tts_provider == "litellm" and not slot_present(cfg.litellm_tts_slot):
        logger.critical(
            "FEHLT: %s — TTS-Slot fehlt im Zugangsdaten-Speicher "
            "(tts_provider=litellm) (SVC-7/#1493)", cfg.litellm_tts_slot)
        sys.exit(1)


def _get_familie_client():
    """Liefert einen FamilieClient — gecacht im runtime-Dict oder frisch (T1015).

    Test-Naht: ``configure(familie_client=...)`` setzt direkt einen Stub.
    Produktiv-Pfad: ``tools.familie_client.FamilieClient`` aus ENV
    ``KIBUDDY_FAMILIE_ORIGIN`` (Default ``http://127.0.0.1:5010``).
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
# `make_response` in der Factory wrappt auch die NDJSON-Streaming-Response von
# /frage (stream_with_context) korrekt (Set-Cookie steht vor dem Body).
require_init_data = make_require_init_data(
    get_bot_token=_get_bot_token,
    get_familie_client=_get_familie_client,
    get_init_data_config=_get_init_data_config,
    auth_401=_auth_401,
)


# Decorator: AUTH-7b Dual-Gate (auth.md AUTH-7, RAT-32, #1836 AUTH-11). Die
# Display-Flaeche (`/display/kibuddy/frage`, ihr implizites Flask-Static) ist
# ein Browser-Pfad auf dem Kind-Tablet — dort gibt es keinen tma-Header,
# sondern ein `xbuddy_session`-Cookie (AUTH-7b). `require_init_data` (HART-
# tma, oben) bleibt fuer die Mini-App-Datenrouten (`/api/v1/kibuddy/*`)
# zustaendig; dieser zweite Gate deckt die Display-Flaeche. Bot-Token-Getter
# wird zwischen beiden Gates geteilt (gleicher HMAC-Sign-Key, AUTH-2:62 —
# kein zweites Geheimnis). `auth_401` teilt sich ebenfalls den bestehenden
# `_auth_401`-Renderer: der Re-Pair-Text ist bereits generisch "Gerät neu
# verbinden" formuliert (nicht tma-spezifisch) — ein zweiter, fast
# identischer 401-Text waere ein Genre-Duplikat ohne Mehrwert (D1 bleibt
# gewahrt: EIN Renderer pro Buddy, hier fuer beide Gates geteilt).
# RAT-32 Nicht-Verhandelbar (decisions/RAT-32-auth-cookie-only-hart.md:39-46,
# Lehre #1427->#1430): der Hard-Flip ist eine ENV-Naht, kein Code-Diff — der
# Rueckroll-Pfad ist "XBUDDY_AUTH_MODE=observe + Neustart", nicht "PR + Merge
# + Deploy". Form wortgleich zum seiten-Vorbild (seiten/main.py:469); Default
# hier ist "hard" statt seitens "observe" — Nic-Setzung 2026-08-11 (#1836)
# betrifft den WERT (Display-Flaeche ist Cookie-hart ab Tag 0), nicht den
# Mechanismus (dieselbe ENV-Naht, derselbe Rueckroll-Pfad wie seiten/routine).
_AUTH_MODE = os.environ.get("XBUDDY_AUTH_MODE", "hard")


# default_mode=_AUTH_MODE (ENV-Naht, s.o.) — Default "hard": jede Adresse
# hinter dem Cookie, kein Observe-Grace fuer die Display-Flaeche, es sei denn
# XBUDDY_AUTH_MODE=observe ist gesetzt (Rueckroll-Pfad / Demo-Stack).
require_dual_gate = make_require_dual_gate(
    get_bot_token=_get_bot_token,
    get_client_ip=_client_ip,
    auth_401=_auth_401,
    default_mode=_AUTH_MODE,
)


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__, template_folder="templates", static_url_path="/display/kibuddy/static")

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


@app.after_request
def _set_session_cookie(response):
    """Setzt kibuddy_sid-Cookie wenn in diesem Request eine neue SID erzeugt wurde (FIX-5).

    Gilt für ALLE Endpunkte — kein Phantom-Session-Leak bei /reset-zuerst-Pattern.
    """
    new_sid = getattr(g, "_kibuddy_new_sid", None)
    if new_sid is not None:
        response.set_cookie(
            SID_COOKIE,
            new_sid,
            httponly=True,
            samesite="Lax",
            path="/",
        )
    return response


# ---- Health-Check (SVC-1) ----

@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


# ---- Display-View (KIBUDDY-2, Stub für Stück B) ----

@app.route("/display/kibuddy/frage", methods=["GET"])
@require_dual_gate()  # AUTH-11 (#1836): Display-Flaeche, mode=_AUTH_MODE (ENV-Naht)
def display_frage():
    cfg = _runtime_cfg()
    # VAD-Konfig an Template übergeben (KIBUDDY-21/AC3, KIBUDDY-7/T864)
    kibuddy_cfg = cfg.to_vad_cfg() if cfg is not None else {
        "vad_stille_sek": config_mod.DEFAULT_VAD_STILLE_SEK,
        "vad_threshold_db": config_mod.DEFAULT_VAD_THRESHOLD_DB,
        "vad_long_hold_lock_sek": config_mod.DEFAULT_VAD_LONG_HOLD_LOCK_SEK,
        "aufnahme_min_sek": config_mod.DEFAULT_AUFNAHME_MIN_SEK,
    }
    return render_template("frage.html", kibuddy_cfg=kibuddy_cfg)


# ---- Audio-Cache-Auslieferung (KIBUDDY-24) ----

@app.route("/api/v1/kibuddy/audio/<path:audio_filename>", methods=["GET"])
@require_init_data
def audio_file(audio_filename: str):
    """Liefert MP3 aus dem Audio-Cache (KIBUDDY-24)."""
    audio_dir = data_io.audio_dir(_data_root())
    return send_from_directory(audio_dir, audio_filename)


# ---- Haupt-Endpoint: Frage (KIBUDDY-24) ----

@app.route("/api/v1/kibuddy/frage", methods=["POST"])
@require_init_data
def frage():
    """POST audio → NDJSON-Stream: Stage 1 (kind) sofort nach STT, Stage 2 (buddy) nach LLM+TTS.

    Multipart-Form mit Feld `audio` (Browser-Audio, WebM/Opus o. ä.).
    Response: application/x-ndjson, zwei Zeilen:
      {"event":"kind","transkript":"...","transkript_words":[...]}\n
      {"event":"buddy","text":"...","words":[...],"tts_audio_url":"..."}\n

    Bei Fehler vor Stage 1: {"event":"error","stage":"stt","detail":"..."}\n
    Bei Fehler nach Stage 1: {"event":"error","stage":"llm",...}\n

    Icon-Lookup läuft clientseitig (KIBUDDY-17 letzter Absatz).
    Cookie: kibuddy_sid (HttpOnly, SameSite=Lax) wird gesetzt wenn fehlend.
    """
    # Audio aus Request holen (vor Generator — Flask-Request ist nur im Request-Kontext lesbar).
    audio_file_obj = request.files.get("audio")
    if audio_file_obj is None:
        return jsonify({"fehler": "audio-Feld fehlt (multipart/form-data)"}), 400

    audio_bytes = audio_file_obj.read()
    if not audio_bytes:
        return jsonify({"fehler": "audio-Feld ist leer"}), 400

    filename = audio_file_obj.filename or "audio.webm"

    # Session-Memory via Cookie (KIBUDDY-16) — vor Generator, damit Cookie-Hook greift.
    _sid, memory = _get_or_create_session()

    stt = _stt()
    if stt is None:
        return jsonify({"fehler": "stt-engine nicht konfiguriert"}), 503

    llm = _llm()
    if llm is None:
        return jsonify({
            "fehler": "llm-provider %s hat keinen API-Key"
            % (_runtime_cfg().llm_provider if _runtime_cfg() else "?"),
        }), 503

    # Snapshot-Referenzen für den Generator (Request-Kontext endet nach Response-Start).
    cfg = _runtime_cfg()
    tts = _tts()
    data_root = _data_root()

    def generate():
        # ---- Stage 1: STT ----
        try:
            frage_text = stt_service.transkribiere(audio_bytes, stt, filename=filename)
        except STTError as e:
            yield json.dumps({"event": "error", "stage": "stt", "detail": str(e)}) + "\n"
            return

        if not frage_text.strip():
            yield json.dumps({"event": "error", "stage": "stt", "detail": "transkript leer — konnte die Frage nicht verstehen"}) + "\n"
            return

        # KIBUDDY-12-H (T952): Whisper liefert bei Stille gern DE-YouTube-
        # Untertitel-Halluzinationen ("Untertitel im Auftrag von Funk")
        # statt leerem String. Gleicher Fehler-Pfad wie leeres Transkript.
        if stt_service.ist_stille_halluzination(frage_text):
            logger.info("stt: Stille-Halluzination gefiltert: '%s'", frage_text[:80])
            yield json.dumps({"event": "error", "stage": "stt", "detail": "transkript leer — konnte die Frage nicht verstehen"}) + "\n"
            return

        # transkript_words: Diagnose-Feld (KIBUDDY-24/T865).
        # Frontend ignoriert es (Kind-Bubble text-only, KIBUDDY-19/AC4).
        # Wortklassen-Tokenisierung entfällt (T865 stop_rules keine_breaking_kind_change):
        # leere Liste — kompatibel mit bestehendem Schema, kein STT-Mehraufwand.
        yield json.dumps({
            "event": "kind",
            "transkript": frage_text,
            "transkript_words": [],
        }) + "\n"
        # Werkzeug/Gunicorn flusht bei jedem yield — Stage 1 wird sofort gesendet.

        # ---- Stage 2: LLM + TTS ----
        try:
            llm_result = llm_service.beantworte_frage(
                frage_text=frage_text,
                data_root=data_root,
                memory=memory,
                llm=llm,
            )
        except ProviderError as e:
            yield json.dumps({"event": "error", "stage": "llm", "detail": str(e)}) + "\n"
            return

        antwort_text = llm_result["antwort"]
        buzzwords = llm_result["buzzwords"]

        tts_audio_url = None
        if tts is not None and cfg is not None:
            try:
                audio_id = tts_service.synthetisiere(
                    text=antwort_text,
                    voice=cfg.tts_voice,
                    speed=cfg.tts_speed,
                    data_root=data_root,
                    tts_engine=tts,
                )
                tts_audio_url = "/api/v1/kibuddy/audio/%s.mp3" % audio_id
            except TTSError as e:
                logger.warning("tts: fehler bei frage-endpoint: %s", e)
                # tts_audio_url bleibt None — Kind sieht zumindest Text (KIBUDDY-24).

        yield json.dumps({
            "event": "buddy",
            "text": antwort_text,
            "buzzwords": buzzwords,
            "tts_audio_url": tts_audio_url,
        }) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},  # nginx: kein Response-Buffering (ROU-22 analog)
    )


# ---- Vorlesen-Endpoint (KIBUDDY-24, KIBUDDY-31) ----

@app.route("/api/v1/kibuddy/vorlesen", methods=["POST"])
@require_init_data
def vorlesen():
    """POST {text} oder {tts_audio_id} → TTS-Audio.

    Body: {"text": "<text>"} — frische TTS-Synthese.
    Oder:  {"tts_audio_id": "<id>"} — Audio-Replay aus Cache.
    Response: {"tts_audio_url": "<pfad>"}
    """
    _get_or_create_session()  # Cookie konsistent setzen (FIX-5, KIBUDDY-16)
    body = request.get_json(silent=True) or {}
    cfg = _runtime_cfg()
    tts = _tts()

    if tts is None or cfg is None:
        return jsonify({"fehler": "tts-engine nicht konfiguriert"}), 503

    # Replay-Pfad.
    audio_id = (body.get("tts_audio_id") or "").strip()
    if audio_id:
        path = data_io.audio_path(_data_root(), audio_id)
        if not __import__("os").path.isfile(path):
            return jsonify({"fehler": "audio-id nicht im Cache"}), 404
        return jsonify({"tts_audio_url": "/api/v1/kibuddy/audio/%s.mp3" % audio_id})

    # Frische TTS-Synthese aus Text.
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"fehler": "text oder tts_audio_id fehlt"}), 400

    try:
        audio_id = tts_service.synthetisiere(
            text=text,
            voice=cfg.tts_voice,
            speed=cfg.tts_speed,
            data_root=_data_root(),
            tts_engine=tts,
        )
    except TTSError as e:
        return jsonify({"fehler": "tts-anbieter nicht erreichbar: %s" % e}), 503

    return jsonify({"tts_audio_url": "/api/v1/kibuddy/audio/%s.mp3" % audio_id})


# ---- Reset-Endpoint (KIBUDDY-24, KIBUDDY-29) ----

@app.route("/api/v1/kibuddy/reset", methods=["POST"])
@require_init_data
def reset():
    """Löscht Session-Memory des Aufrufers + Audio-Cache (KIBUDDY-16/29).

    Löscht NUR die Session der aufrufenden SID, nicht alle Sessions.
    Die Session-History wird geleert (reset()); die SID bleibt aktiv.
    Audio-Cache bleibt global (per content-Hash dedupliziert, OPEN-KIBUDDY-K).
    """
    sid, memory = _get_or_create_session()
    turn_count = len(memory)
    memory.reset()
    audio_count = tts_service.clear_audio_cache(_data_root())
    logger.info("reset: %d turns gelöscht (sid=%s), %d audio-dateien gelöscht", turn_count, sid[:8], audio_count)
    return jsonify({"ok": True, "turns_geloescht": turn_count, "audio_geloescht": audio_count})


# ---- Config-Endpoints (KIBUDDY-24, KIBUDDY-21) ----

@app.route("/api/v1/kibuddy/config", methods=["GET", "PUT"])
@require_init_data
def config_endpoint():
    _get_or_create_session()  # Cookie konsistent setzen (FIX-5, KIBUDDY-16)
    cfg = _runtime_cfg()
    if cfg is None:
        return jsonify({"fehler": "runtime-config nicht geladen"}), 503

    if request.method == "GET":
        return jsonify(cfg.to_public_dict())

    # PUT: V1 akzeptiert nur aufnahme-quelle (KIBUDDY-24).
    body = request.get_json(silent=True) or {}
    neue_quelle = body.get("aufnahme-quelle") or body.get("aufnahme_quelle")
    if neue_quelle is None:
        return jsonify({"fehler": "V1 akzeptiert nur aufnahme-quelle (KIBUDDY-24)"}), 400

    new_cfg = config_mod.patch_aufnahme_quelle(cfg, str(neue_quelle))
    runtime["runtime_config"] = new_cfg
    logger.info("config: aufnahme_quelle geändert → %s", new_cfg.aufnahme_quelle)
    return jsonify(new_cfg.to_public_dict())


# ---- Prompt-Endpoints (KIBUDDY-15, KIBUDDY-24) ----

@app.route("/api/v1/kibuddy/prompt", methods=["GET"])
@require_init_data
def prompt_get():
    """Liest den aktuell wirksamen System-Prompt (KIBUDDY-15/24)."""
    _get_or_create_session()  # Cookie konsistent setzen (FIX-5, KIBUDDY-16)
    path = data_io.prompt_path(_data_root())
    text = data_io.read_text_or_empty(path)
    if not text.strip():
        text = llm_service.DEFAULT_SYSTEM_PROMPT

    import os as _os
    geaendert_am = None
    if _os.path.isfile(path):
        import datetime
        geaendert_am = datetime.datetime.fromtimestamp(
            _os.path.getmtime(path)
        ).isoformat()

    return jsonify({
        "prompt": text,
        "byte-laenge": len(text.encode("utf-8")),
        "geaendert-am": geaendert_am,
    })


@app.route("/api/v1/kibuddy/prompt", methods=["PUT"])
@require_init_data
def prompt_put():
    """Schreibt neuen System-Prompt atomar (KIBUDDY-15/24)."""
    _get_or_create_session()  # Cookie konsistent setzen (FIX-5, KIBUDDY-16)
    body = request.get_json(silent=True) or {}
    neuer_prompt = body.get("prompt", "")
    if not isinstance(neuer_prompt, str) or not neuer_prompt.strip():
        return jsonify({"fehler": "prompt darf nicht leer sein (KIBUDDY-24)"}), 400

    cfg = _runtime_cfg()
    max_bytes = cfg.prompt_max_bytes if cfg else config_mod.DEFAULT_PROMPT_MAX_BYTES
    encoded = neuer_prompt.encode("utf-8")
    if len(encoded) > max_bytes:
        return jsonify({
            "fehler": "prompt zu lang (%d bytes, max %d, KIBUDDY-21)" % (len(encoded), max_bytes),
        }), 400

    # Aktuelle Länge für Response.
    path = data_io.prompt_path(_data_root())
    bisherige = data_io.read_text_or_empty(path)
    bisherige_laenge = len(bisherige.encode("utf-8"))

    try:
        data_io.write_prompt(_data_root(), neuer_prompt)
    except OSError as e:
        logger.error("prompt-put: schreibfehler: %s", e)
        return jsonify({"fehler": "schreibfehler — alter Prompt bleibt wirksam: %s" % e}), 500

    logger.info("prompt-put: %d bytes geschrieben", len(encoded))
    return jsonify({"ok": True, "byte-laenge": len(encoded), "bisherige-laenge": bisherige_laenge})


# ============================================================
#  Entrypoint
# ============================================================

def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy KIBuddy-App V1")
    p.add_argument("--config", dest="config_file", default=None, help="Pfad zur Config-Datei")
    p.add_argument("--data-root", dest="data_root", default=None, help="Daten-Bereich (SVC-5)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level", help="DEBUG | INFO | WARNING | ERROR")
    return p.parse_args(argv)


def _build_llm(cfg) -> LLMProvider | None:
    """Baut die LLM-Sicht über `tools.llm.get_chat` (LLMP-S8/LLMP-S12, T1082/T1433).

    Slot folgt LLMP-5: `kibuddy-litellm-api-key` (Konsument-Vendor-Purpose).
    Motor-Swap RAT-26/LLMP-S12 Slot 1 — like-for-like: gleiches Modell
    (`claude-haiku-4-5`), Route `litellm` statt `anthropic`. Die Fassade
    (`get_chat`) ist unverändert; nur das Vendor-Segment im Slot-Namen wechselt.
    Rückweg ohne Code-Change: Slot-Segment zurück auf `anthropic` (der
    Hand-Vendor läuft bis Slot-3-Cleanup parallel weiter, LLMP-S12).

    Der API-Key kommt aus dem Zugangsdaten-Speicher (ZD-5); die heutige ENV-
    `ANTHROPIC_API_KEY`-Quelle bleibt in `config.py` für die Boot-Lebendigkeits-
    Probe (`if cfg.anthropic_key`), damit die Spike-Stufe-1 ohne ZD-Migration
    läuft — die Lib selbst zieht über ZD nach Plan.
    """
    if cfg.llm_provider == "claude":
        if not cfg.anthropic_key:
            return None
        from tools.llm import get_chat
        return get_chat(slot="kibuddy-litellm-api-key")
    return None


def _build_stt(cfg):
    if cfg.stt_provider == "litellm":
        # LLMP-S6/RAT-28 (T1410): STT über die tools.llm-Fassade hinter einem
        # ZD-Slot. ffmpeg-#1442 sitzt im LitellmSTTEngine VOR dem Provider-Call.
        return stt_service.LitellmSTTEngine(
            slot=cfg.litellm_stt_slot,
            model=cfg.litellm_stt_model,
            sprache=cfg.stt_sprache,
        )
    if cfg.stt_provider == "openai":
        if not cfg.openai_key:
            return None
        from .stt.openai_whisper import OpenAIWhisperSTT
        return OpenAIWhisperSTT(
            api_key=cfg.openai_key,
            model=cfg.stt_model,
            sprache=cfg.stt_sprache,
        )
    # azure_openai
    if not (cfg.azure_endpoint and cfg.azure_key):
        return None
    from .stt.azure_whisper import AzureWhisperSTT
    return AzureWhisperSTT(
        endpoint=cfg.azure_endpoint,
        api_key=cfg.azure_key,
        api_version=cfg.azure_api_version,
        deployment=cfg.stt_model,
        sprache=cfg.stt_sprache,
    )


def _build_tts(cfg):
    if cfg.tts_provider == "litellm":
        # LLMP-S6/RAT-28 (T1410): TTS über die tools.llm-Fassade hinter einem
        # ZD-Slot. Die Voice/Speed kommen weiter aus der Config (durchgereicht im
        # synthetisiere()-Aufruf, tts_service.py).
        return tts_service.LitellmTTSEngine(
            slot=cfg.litellm_tts_slot,
            model=cfg.litellm_tts_model,
        )
    # azure_openai (Default)
    if not (cfg.azure_endpoint and cfg.azure_key):
        return None
    from .tts.azure import AzureTTSEngine
    return AzureTTSEngine(
        endpoint=cfg.azure_endpoint,
        api_key=cfg.azure_key,
        api_version=cfg.azure_api_version,
        deployment=cfg.tts_model,
    )


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    runtime_cfg = config_mod.resolve_runtime(args.config_file)

    if args.host:
        runtime_cfg.listen_host = args.host
    if args.port:
        runtime_cfg.listen_port = args.port
    if args.log_level:
        runtime_cfg.log_level = args.log_level

    logsetup.setup(runtime_cfg.log_level)

    data_root = (
        args.data_root
        or os.environ.get(config_mod.ENV_DATA_ROOT)
        or config_mod.DEFAULT_DATA_ROOT
    )
    os.makedirs(data_root, exist_ok=True)
    os.makedirs(data_io.audio_dir(data_root), exist_ok=True)

    # KIBUDDY-20: Audio-Cache beim Service-Start leeren.
    tts_service.clear_audio_cache_dir(data_root)

    # SVC-7: Startup-Secret-Preflight — fehlende Pflicht-Secrets/LLM-Slots brechen
    # sichtbar (#1447, #1493). MUSS VOR `configure(...)` laufen: `_build_stt`/
    # `_build_tts` bauen die Litellm-Engines eager (get_transcription/get_speech),
    # die bei fehlendem Slot sonst hier schon `LLMCapabilityError` würfen — der
    # Preflight fängt das vorher mit einer klaren FEHLT-Zeile ab.
    _secret_preflight(runtime_cfg)

    configure(
        runtime_config=runtime_cfg,
        data_root=data_root,
        llm_factory=_build_llm,
        stt_engine=_build_stt(runtime_cfg),
        tts_engine=_build_tts(runtime_cfg),
    )

    logger.info(
        "KIBuddy hört auf http://%s:%s (llm=%s model=%s stt=%s voice=%s speed=%.1f data=%s)",
        runtime_cfg.listen_host, runtime_cfg.listen_port,
        runtime_cfg.llm_provider, runtime_cfg.llm_model,
        runtime_cfg.stt_provider,
        runtime_cfg.tts_voice, runtime_cfg.tts_speed, data_root,
    )
    app.run(host=runtime_cfg.listen_host, port=runtime_cfg.listen_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
