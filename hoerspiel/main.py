#!/usr/bin/env python3
"""Hörspiel-Buddy-App — HTTP-Schnittstelle + Entrypoint (HSP-17/HSP-28).

Siehe specs/buddies/hoerspiel.md. Endpunkte:

  GET  /api/v1/hoerspiel/bible                       — Welt-Bible als Markdown
  GET  /api/v1/hoerspiel/folgen-historie             — Folgen-Historie als Markdown
  GET  /api/v1/hoerspiel/alben                       — Liste freigegebener Alben
  GET  /api/v1/hoerspiel/alben/<id>/manifest         — Album-Manifest
  POST /api/v1/hoerspiel/folgen-vorschlag            — LLM-Vorschlag (Side-Effekt-frei)
  POST /api/v1/hoerspiel/alben                       — Album bauen (TTS + Historie)
  GET  /api/v1/hoerspiel/config                      — Eltern-Tuning-Konfig lesen (HSP-34)
  PATCH /api/v1/hoerspiel/config                     — Eltern-Tuning setzen (HSP-34)
  GET  /api/v1/hoerspiel/themen?alter=N              — Themen-Liste je Alter (HSP-38)
  GET  /api/v1/hoerspiel/alben/<id>/audio/<track>.mp3 — Audio-Track mit Range-Requests (HSP-37)
  GET  /api/v1/hoerspiel/resume?album=<id>           — Resume-Stand lesen (HSP-36)
  PUT  /api/v1/hoerspiel/resume                      — Resume-Stand setzen (HSP-36)
  GET  /api/v1/hoerspiel/shared-assets/status        — Vorhandensein je Voice
  POST /api/v1/hoerspiel/shared-assets/rebuild       — alle vier MP3s neu bauen

Daten-Router (HSP-26):
  GET  /display/hoerspiel/data/<sub>                 — Audio-/Cover-Assets

Port: 5053 (HSP-28). Service-Topologie: schlanke eigenständige Flask-App
(Geschwister von wetter/, routine/, plan/).
"""

import argparse
import functools
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request, send_from_directory

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import logsetup  # noqa: E402

if __package__:
    from . import album_builder, data_io, llm_service, tts_service
    from . import config as config_mod
    from .providers.base import LLMProvider, ProviderError
    from .tts.azure import TTSError
else:  # python3 hoerspiel/main.py
    sys.path.insert(0, _REPO_ROOT)
    from hoerspiel import album_builder, data_io, llm_service, tts_service
    from hoerspiel import config as config_mod
    from hoerspiel.providers.base import LLMProvider, ProviderError
    from hoerspiel.tts.azure import TTSError

# MAD-7 / HSP-39: Init-Data-Auth aus eltern-chat/init_data.py.
_ELTERN_CHAT_DIR = os.path.join(_REPO_ROOT, "eltern-chat")
if _ELTERN_CHAT_DIR not in sys.path:
    sys.path.insert(0, _ELTERN_CHAT_DIR)

try:
    import init_data as _init_data_mod
    _INIT_DATA_AVAILABLE = True
except ImportError:
    _INIT_DATA_AVAILABLE = False
    _init_data_mod = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

# ============================================================
#  Laufzeit-Zustand (Test-Naht analog wetter/main.py)
# ============================================================

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
    "familie_json_path": None, # str | None — aus ENV FAMILIE_JSON_PATH
    "resume_store": {},        # dict album_id -> track_position (in-process für V1)
}


def configure(*, runtime_config, data_config, data_root: str,
              llm_factory=None, llm=None,
              tts_engine=None, now=None,
              bot_token=None, init_data_config=None,
              familie_json_path=None) -> None:
    """Setzt Konfiguration und Adapter-Fabriken (Test-Naht, HSP-24).

    `llm_factory(cfg) -> LLMProvider` baut den Provider passend zur aktiven
    Runtime-Config — bei `PATCH /config` mit neuem Provider/Modell wird er
    erneut gerufen. In Tests bleibt `llm_factory=None` und `llm=` wird
    direkt gesetzt.

    `now` ist die HSP-24-Naht für deterministische Zeit (Manifest-`erstellt-
    am`, Historie-Datum, ...).

    `bot_token` + `init_data_config` + `familie_json_path`: MAD-7/HSP-39 Auth-Naht
    (Test-Modus direkt setzen; Produktiv-Betrieb liest ENV).
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
    runtime["familie_json_path"] = familie_json_path
    runtime["resume_store"] = {}


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


def _lade_familie_telegram_ids():
    """Liest telegram_ids aller Familien-Mitglieder aus familie.json (FAM-7/8)."""
    import json as _json
    path = runtime.get("familie_json_path") or os.environ.get("FAMILIE_JSON_PATH")
    if not path:
        return None  # kein Pfad konfiguriert → FAM-Check überspringen
    try:
        with open(path, encoding="utf-8") as fh:
            data = _json.load(fh)
    except (FileNotFoundError, OSError, _json.JSONDecodeError) as exc:
        logger.warning("FAM-7: familie.json nicht lesbar (%s): %s — FAM-Check uebersprungen",
                       path, exc)
        return None
    ids = set()
    for gruppe in ("erwachsene", "kinder"):
        for person in (data.get(gruppe) or []):
            tg_id = person.get("telegram_id")
            if tg_id is not None:
                ids.add(int(tg_id))
    return ids


def _validate_mini_app_request():
    """Validiert Authorization: tma <initData>-Header (MAD-7 / HSP-39).

    Gibt (InitData, None) bei Erfolg zurück.
    Gibt (None, (json_response, status)) bei Auth-Fehler zurück.
    """
    bot_token = _get_bot_token()

    # HSP-40: Test-Modus-Bypass — bot_token="TEST" überspringt alle Auth-Checks.
    # Das wird ausschließlich in unit-Tests via configure(bot_token="TEST") gesetzt.
    if bot_token == "TEST":
        from types import SimpleNamespace
        return SimpleNamespace(user_id=1), None

    if not _INIT_DATA_AVAILABLE or _init_data_mod is None:
        return None, (jsonify({"error": "Init-Data-Modul nicht verfügbar"}), 500)

    if not bot_token:
        logger.error("MAD-7: ELTERNCHAT_BOT_TOKEN nicht gesetzt — Mini-App-Route nicht nutzbar.")
        return None, (jsonify({"error": "Serverkonfiguration unvollständig (Bot-Token fehlt)"}), 500)

    cfg = runtime.get("init_data_config")
    if cfg is None:
        cfg = _init_data_mod.load_config()
        runtime["init_data_config"] = cfg

    auth_header = request.headers.get("Authorization")
    try:
        init_data = _init_data_mod.validate_header(
            auth_header,
            bot_token,
            cfg["max_age_seconds"],
        )
    except _init_data_mod.InitDataError as exc:
        logger.warning("MAD-7 Auth fehlgeschlagen: %s", exc)
        return None, (jsonify({"error": "initData ungültig, abgelaufen oder fehlt"}), 401)

    return init_data, None


def _check_familie_mitglied(user_id):
    """Prüft ob user_id in der Familien-Registry registriert ist (FAM-7/8)."""
    familie_ids = _lade_familie_telegram_ids()
    if familie_ids is None:
        return None  # kein Pfad konfiguriert → fail-open
    if user_id not in familie_ids:
        logger.warning("FAM-7: user_id %s ist kein Familien-Mitglied → 403", user_id)
        return jsonify({"error": "Nicht autorisiert — kein Familienmitglied"}), 403
    return None


def require_mini_app_auth(f):
    """Decorator: MAD-7 / HSP-39 Auth-Pflicht für Mini-App-API-Routen.

    Prüft Authorization: tma <initData>-Header. Bei Fehler → 401/500.
    Prüft Familien-Registry. Bei Fehler → 403.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        # Localhost-Bypass für Internal-Service-Calls (eltern-chat → hoerspiel).
        # nginx-Forwards tragen X-Forwarded-For; direkte 127.0.0.1-Calls nicht.
        # Public-Mini-App-Calls (Browser via nginx) bleiben auth-gesichert.
        if (not request.headers.get("X-Forwarded-For")
                and request.remote_addr in ("127.0.0.1", "::1")):
            return f(*args, **kwargs)

        init_data, err = _validate_mini_app_request()
        if err is not None:
            return err
        fam_err = _check_familie_mitglied(init_data.user_id)
        if fam_err is not None:
            return fam_err
        return f(*args, **kwargs)
    return wrapper


# ============================================================
#  HSP-27b — Modell-Listen-Aggregation
# ============================================================

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

    try:
        from hoerspiel.providers.mistral import AVAILABLE_MODELS as MISTRAL_MODELS
    except ImportError:
        try:
            from .providers.mistral import AVAILABLE_MODELS as MISTRAL_MODELS
        except ImportError:
            MISTRAL_MODELS = []
    result["mistral"] = [{"id": mid, "label": label} for mid, label in MISTRAL_MODELS]
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


# ---- Display-View (HSP-2, HSP-3 — Single-Page-Splitscreen Mia-View) ----

@app.route("/display/hoerspiel/alben", methods=["GET"])
def display_alben():
    return render_template("alben.html")


# ---- Lese-Endpoints (HSP-17, Side-Effekt-frei) ----

@app.route("/api/v1/hoerspiel/bible", methods=["GET"])
def bible():
    text = data_io.read_text_or_empty(os.path.join(_data_root(), "bible.md"))
    return text, 200, {"Content-Type": "text/markdown; charset=utf-8"}


@app.route("/api/v1/hoerspiel/folgen-historie", methods=["GET"])
def folgen_historie():
    text = data_io.read_text_or_empty(os.path.join(_data_root(), "folgen-historie.md"))
    return text, 200, {"Content-Type": "text/markdown; charset=utf-8"}


@app.route("/api/v1/hoerspiel/alben", methods=["GET", "POST"])
def alben():
    if request.method == "GET":
        return jsonify(album_builder.liste_alben(_data_root()))
    return _post_alben()


@app.route("/api/v1/hoerspiel/alben/<album_id>/manifest", methods=["GET"])
def album_manifest_get(album_id: str):
    manifest = album_builder.lade_manifest(_data_root(), album_id)
    if manifest is None:
        return jsonify({"fehler": "album nicht gefunden"}), 404
    return jsonify(manifest)


# ---- Schreib-Endpoints (HSP-17, Eltern-Chat-Skill) ----

@app.route("/api/v1/hoerspiel/folgen-vorschlag", methods=["POST"])
def folgen_vorschlag():
    body = request.get_json(silent=True) or {}
    idee = (body.get("idee") or "").strip()
    if not idee:
        return jsonify({"fehler": "idee fehlt"}), 400

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
    try:
        vorschlag = llm_service.erzeuge_folgen_vorschlag(
            idee=idee, bible=bible_text, historie=historie,
            naechste_nummer=naechste, llm=llm)
    except ProviderError as e:
        return jsonify({"fehler": "llm-provider nicht erreichbar: %s" % e}), 503
    except llm_service.LLMServiceError as e:
        return jsonify({"fehler": "llm-antwort unbrauchbar: %s" % e}), 502
    return jsonify(vorschlag)


def _naechste_nummer_aus_historie(historie: str) -> int:
    # Re-export der gleichen Logik aus album_builder, damit der Endpoint
    # keinen Privat-Import braucht (Symmetrie zum POST /alben-Pfad).
    return album_builder._naechste_nummer(historie)


def _post_alben():
    body = request.get_json(silent=True) or {}
    titel = (body.get("titel") or "").strip()
    text = (body.get("text") or "").strip()
    voice = (body.get("voice") or "").strip().lower()
    idee = (body.get("idee") or "").strip()
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

    try:
        ergebnis = album_builder.baue_album(
            titel=titel, text=text, voice=voice, idee=idee,
            data_root=_data_root(),
            llm=llm, tts_engine=tts,
            now=runtime["now"],
            pause_absatz_sek=pause_absatz,
            pause_titel_sek=pause_titel,
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

def _build_config_response(cfg, dcfg) -> dict:
    """Baut die vollständige GET /config-Antwort (HSP-17/34)."""
    public = cfg.to_public_dict()
    if dcfg is not None:
        public["default_voice"] = dcfg.default_voice
        public["serien_name"] = dcfg.serien_name
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


@app.route("/api/v1/hoerspiel/config", methods=["GET", "PATCH"])
@require_mini_app_auth
def config_endpoint():
    cfg = _runtime_cfg()
    if cfg is None:
        return jsonify({"fehler": "runtime-config nicht geladen"}), 503

    if request.method == "GET":
        return jsonify(_build_config_response(cfg, _data_cfg()))

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

    return jsonify(_build_config_response(new_cfg, new_dcfg))


# ---- Themen-Endpoint (HSP-38) ----

@app.route("/api/v1/hoerspiel/themen", methods=["GET"])
@require_mini_app_auth
def themen_endpoint():
    """HSP-38: GET /themen?alter=N → kuratierte Themen-Liste je Alter."""
    alter_raw = request.args.get("alter", "").strip()
    dcfg = _data_cfg()
    themen_je_alter = dcfg.themen_je_alter if dcfg is not None else \
        dict(config_mod.DEFAULT_THEMEN_JE_ALTER)

    if alter_raw not in themen_je_alter:
        return jsonify({
            "fehler": "Themen-Liste für Alter %s nicht gepflegt — "
                      "Eltern können im Chat eigene Idee geben." % alter_raw,
        }), 404

    try:
        alter_int = int(alter_raw)
    except (TypeError, ValueError):
        alter_int = 0

    return jsonify({"alter": alter_int, "themen": themen_je_alter[alter_raw]})


# ---- Audio-Streaming-Endpoint (HSP-37) ----

@app.route("/api/v1/hoerspiel/alben/<album_id>/audio/<path:track_filename>",
           methods=["GET"])
@require_mini_app_auth
def album_audio(album_id: str, track_filename: str):
    """HSP-37: Audio-Track streamen mit Range-Requests.

    Auth-Check (HSP-39) läuft via require_mini_app_auth-Decorator vor der
    Range-Logik (401 trumpft 206). send_from_directory blockt Pfad-Traversal.
    `Content-Type: audio/mpeg`, `Cache-Control: private, max-age=86400`.
    """
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

@app.route("/api/v1/hoerspiel/resume", methods=["GET", "PUT"])
@require_mini_app_auth
def resume_endpoint():
    """HSP-36: Resume-Stand lesen (GET) und setzen (PUT).

    GET ?album=<id> → {"album": "<id>", "track": <position>} oder 404.
    PUT Body: {"album": "<id>", "track": <position>} → 200 + Echo.

    V1: in-process-Store (runtime['resume_store']). Last-Write-Wins.
    """
    store = runtime.get("resume_store")
    if store is None:
        store = {}
        runtime["resume_store"] = store

    if request.method == "GET":
        album_id = (request.args.get("album") or "").strip()
        if not album_id:
            return jsonify({"fehler": "album-Parameter fehlt"}), 400
        if album_id not in store:
            return jsonify({"fehler": "kein Resume-Stand für album %s" % album_id}), 404
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

@app.route("/api/v1/hoerspiel/shared-assets/status", methods=["GET"])
def shared_assets_status():
    return jsonify(tts_service.status_shared_assets(_data_root()))


@app.route("/api/v1/hoerspiel/shared-assets/rebuild", methods=["POST"])
def shared_assets_rebuild():
    tts = _tts()
    if tts is None:
        return jsonify({"fehler": "tts-engine nicht konfiguriert"}), 503
    try:
        return jsonify(tts_service.rebuild_alle(data_root=_data_root(), engine=tts))
    except TTSError as e:
        return jsonify({"fehler": "tts-engine nicht erreichbar: %s" % e}), 503


# ---- Daten-Router (HSP-26 `GET /display/hoerspiel/data/<sub>`) ----

@app.route("/display/hoerspiel/data/<path:sub>", methods=["GET"])
def display_data(sub: str):
    """Liefert Audio-/Cover-Assets aus dem Daten-Bereich aus (HSP-26).

    Streng auf Subpfade unter `data/` begrenzt — `send_from_directory`
    blockt Pfad-Traversal.
    """
    return send_from_directory(_data_root(), sub)


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


def _build_llm(cfg) -> LLMProvider | None:
    if cfg.llm_provider == "claude":
        if not cfg.anthropic_key:
            return None
        from .providers.claude import ClaudeProvider
        return ClaudeProvider(api_key=cfg.anthropic_key, model=cfg.llm_model)
    if cfg.llm_provider == "mistral":
        if not cfg.mistral_key:
            return None
        from .providers.mistral import MistralProvider
        return MistralProvider(api_key=cfg.mistral_key, model=cfg.llm_model)
    return None


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
