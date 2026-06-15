#!/usr/bin/env python3
"""KIBuddy-App — HTTP-Schnittstelle + Entrypoint (KIBUDDY-24/25).

Endpunkte (KIBUDDY-24):

  GET  /display/kibuddy/frage            — Frage-View (Stub, Stück B baut UI)
  POST /api/v1/kibuddy/frage             — Audio → STT → LLM → Tokenisierung → TTS
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
Icon-Lookup: clientseitig via Browser-Fetch-API (KIBUDDY-17 letzter Absatz).
"""

import argparse
import logging
import os
import sys

from flask import Flask, g, jsonify, render_template, request, send_from_directory

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import logsetup  # noqa: E402

if __package__:
    from . import config as config_mod
    from . import data_io, icon_render, llm_service, stt_service, tts_service
    from .providers.base import LLMProvider, ProviderError
    from .session_memory import SID_COOKIE, SessionMemory, SessionRegistry
    from .stt.azure_whisper import STTError
    from .tts.azure import TTSError
else:  # python3 kibuddy/main.py
    sys.path.insert(0, _REPO_ROOT)
    from kibuddy import config as config_mod
    from kibuddy import data_io, icon_render, llm_service, stt_service, tts_service
    from kibuddy.providers.base import LLMProvider, ProviderError
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
) -> None:
    """Setzt Konfiguration und Adapter-Fabriken (Test-Naht).

    `llm_factory(cfg) -> LLMProvider` baut den Provider.
    In Tests bleibt `llm_factory=None` und `llm=` wird direkt gesetzt.

    `session_registry` (SessionRegistry) ist die Test-Naht — erlaubt Injection
    einer vorbereiteten Registry mit fest gesetzten SIDs via Cookie.
    """
    runtime["runtime_config"] = runtime_config
    runtime["data_root"] = data_root
    runtime["llm_factory"] = llm_factory
    runtime["llm"] = llm
    runtime["stt_engine"] = stt_engine
    runtime["tts_engine"] = tts_engine
    runtime["session_registry"] = session_registry if session_registry is not None else SessionRegistry()


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
#  Flask-App
# ============================================================

app = Flask(__name__, template_folder="templates", static_url_path="/display/kibuddy/static")


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
def display_frage():
    return render_template("frage.html")


# ---- Audio-Cache-Auslieferung (KIBUDDY-24) ----

@app.route("/api/v1/kibuddy/audio/<path:audio_filename>", methods=["GET"])
def audio_file(audio_filename: str):
    """Liefert MP3 aus dem Audio-Cache (KIBUDDY-24)."""
    audio_dir = data_io.audio_dir(_data_root())
    return send_from_directory(audio_dir, audio_filename)


# ---- Haupt-Endpoint: Frage (KIBUDDY-24) ----

@app.route("/api/v1/kibuddy/frage", methods=["POST"])
def frage():
    """POST audio → STT → LLM (mit Memory) → Tokenisierung → TTS → JSON.

    Multipart-Form mit Feld `audio` (Browser-Audio, WebM/Opus o. ä.).
    Response: { text, transkript, words: [{text, is_inhaltswort}], tts_audio_url }

    Icon-Lookup läuft clientseitig (KIBUDDY-17 letzter Absatz):
    Stück B ruft /api/v1/icons/suche parallel per Browser-Fetch für alle
    is_inhaltswort=true-Wörter auf.

    Cookie: kibuddy_sid (HttpOnly, SameSite=Lax) wird gesetzt wenn fehlend.
    """
    # Audio aus Request holen.
    audio_file_obj = request.files.get("audio")
    if audio_file_obj is None:
        return jsonify({"fehler": "audio-Feld fehlt (multipart/form-data)"}), 400

    audio_bytes = audio_file_obj.read()
    if not audio_bytes:
        return jsonify({"fehler": "audio-Feld ist leer"}), 400

    filename = audio_file_obj.filename or "audio.webm"

    # Session-Memory via Cookie (KIBUDDY-16).
    _sid, memory = _get_or_create_session()

    # STT.
    stt = _stt()
    if stt is None:
        return jsonify({"fehler": "stt-engine nicht konfiguriert"}), 503
    try:
        frage_text = stt_service.transkribiere(audio_bytes, stt, filename=filename)
    except STTError as e:
        return jsonify({"fehler": "stt-anbieter nicht erreichbar: %s" % e}), 503

    if not frage_text.strip():
        return jsonify({"fehler": "transkript leer — konnte die Frage nicht verstehen"}), 422

    # LLM (mit Memory).
    llm = _llm()
    if llm is None:
        return jsonify({
            "fehler": "llm-provider %s hat keinen API-Key"
            % (_runtime_cfg().llm_provider if _runtime_cfg() else "?"),
        }), 503
    try:
        antwort_text = llm_service.beantworte_frage(
            frage_text=frage_text,
            data_root=_data_root(),
            memory=memory,
            llm=llm,
        )
    except ProviderError as e:
        return jsonify({"fehler": "llm-provider nicht erreichbar: %s" % e}), 503

    # Tokenisierung + Wortklassen-Filter (clientseitiger Icon-Lookup, KIBUDDY-17).
    words_api = icon_render.worte_zu_words_api(antwort_text)

    # TTS (Resilienz: Fehler → tts_audio_url: null, KIBUDDY-24).
    cfg = _runtime_cfg()
    tts = _tts()
    tts_audio_url = None
    if tts is not None and cfg is not None:
        try:
            audio_id = tts_service.synthetisiere(
                text=antwort_text,
                voice=cfg.tts_voice,
                speed=cfg.tts_speed,
                data_root=_data_root(),
                tts_engine=tts,
            )
            tts_audio_url = "/api/v1/kibuddy/audio/%s.mp3" % audio_id
        except TTSError as e:
            logger.warning("tts: fehler bei frage-endpoint: %s", e)
            # tts_audio_url bleibt None — Kind sieht zumindest Text (KIBUDDY-24).

    response_data = {
        "text": antwort_text,
        "transkript": frage_text,
        "words": words_api,
        "tts_audio_url": tts_audio_url,
    }
    return jsonify(response_data)


# ---- Vorlesen-Endpoint (KIBUDDY-24, KIBUDDY-31) ----

@app.route("/api/v1/kibuddy/vorlesen", methods=["POST"])
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
    if cfg.llm_provider == "claude":
        if not cfg.anthropic_key:
            return None
        from .providers.claude import ClaudeProvider
        return ClaudeProvider(api_key=cfg.anthropic_key, model=cfg.llm_model)
    return None


def _build_stt(cfg):
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

    # KIBUDDY-17.3: Funktionswort-Override einmalig beim Start laden (befüllt Modul-Cache).
    icon_render.load_stop_words(data_root=data_root)

    configure(
        runtime_config=runtime_cfg,
        data_root=data_root,
        llm_factory=_build_llm,
        stt_engine=_build_stt(runtime_cfg),
        tts_engine=_build_tts(runtime_cfg),
    )

    logger.info(
        "KIBuddy hört auf http://%s:%s (provider=%s model=%s voice=%s speed=%.1f data=%s)",
        runtime_cfg.listen_host, runtime_cfg.listen_port,
        runtime_cfg.llm_provider, runtime_cfg.llm_model,
        runtime_cfg.tts_voice, runtime_cfg.tts_speed, data_root,
    )
    app.run(host=runtime_cfg.listen_host, port=runtime_cfg.listen_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
