#!/usr/bin/env python3
"""Hörspiel-Buddy-App — HTTP-Schnittstelle + Entrypoint (HSP-17/HSP-28).

Siehe specs/buddies/hoerspiel.md. Endpunkte:

  GET  /api/v1/hoerspiel/bible                       — Welt-Bible als Markdown
  GET  /api/v1/hoerspiel/folgen-historie             — Folgen-Historie als Markdown
  GET  /api/v1/hoerspiel/alben                       — Liste freigegebener Alben
  GET  /api/v1/hoerspiel/alben/<id>/manifest         — Album-Manifest
  POST /api/v1/hoerspiel/folgen-vorschlag            — LLM-Vorschlag (Side-Effekt-frei)
  POST /api/v1/hoerspiel/alben                       — Album bauen (TTS + Historie)
  GET  /api/v1/hoerspiel/config                      — Provider/Modell lesen
  PATCH /api/v1/hoerspiel/config                     — Provider/Modell setzen
  GET  /api/v1/hoerspiel/shared-assets/status        — Vorhandensein je Voice
  POST /api/v1/hoerspiel/shared-assets/rebuild       — alle vier MP3s neu bauen

Daten-Router (HSP-26):
  GET  /display/hoerspiel/data/<sub>                 — Audio-/Cover-Assets

Port: 5053 (HSP-28). Service-Topologie: schlanke eigenständige Flask-App
(Geschwister von wetter/, routine/, plan/).
"""

import argparse
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
}


def configure(*, runtime_config, data_config, data_root: str,
              llm_factory=None, llm=None,
              tts_engine=None, now=None) -> None:
    """Setzt Konfiguration und Adapter-Fabriken (Test-Naht, HSP-24).

    `llm_factory(cfg) -> LLMProvider` baut den Provider passend zur aktiven
    Runtime-Config — bei `PATCH /config` mit neuem Provider/Modell wird er
    erneut gerufen. In Tests bleibt `llm_factory=None` und `llm=` wird
    direkt gesetzt.

    `now` ist die HSP-24-Naht für deterministische Zeit (Manifest-`erstellt-
    am`, Historie-Datum, ...).
    """
    runtime["runtime_config"] = runtime_config
    runtime["data_config"] = data_config
    runtime["data_root"] = data_root
    runtime["llm_factory"] = llm_factory
    runtime["llm"] = llm
    runtime["tts_engine"] = tts_engine
    if now is not None:
        runtime["now"] = now


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
    llm = factory(cfg)
    runtime["llm"] = llm
    return llm


def _tts():
    return runtime.get("tts_engine")


def _now() -> datetime:
    return runtime["now"]()


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__, static_url_path="/display/hoerspiel/static")


# ---- Display-View (HSP-2, HSP-3 — Single-Page-Splitscreen Paula-View) ----

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

    try:
        ergebnis = album_builder.baue_album(
            titel=titel, text=text, voice=voice, idee=idee,
            data_root=_data_root(),
            llm=llm, tts_engine=tts,
            now=runtime["now"],
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

@app.route("/api/v1/hoerspiel/config", methods=["GET", "PATCH"])
def config_endpoint():
    cfg = _runtime_cfg()
    if cfg is None:
        return jsonify({"fehler": "runtime-config nicht geladen"}), 503

    if request.method == "GET":
        public = cfg.to_public_dict()
        dcfg = _data_cfg()
        if dcfg is not None:
            public["default_voice"] = dcfg.default_voice
            public["serien_name"] = dcfg.serien_name
        return jsonify(public)

    body = request.get_json(silent=True) or {}
    try:
        new_cfg = config_mod.patch_runtime(cfg, body)
    except config_mod.ConfigError as e:
        return jsonify({"fehler": str(e)}), 422

    runtime["runtime_config"] = new_cfg
    # Cache invalidieren — Provider-/Modell-Wechsel zwingt Neuaufbau.
    if (new_cfg.llm_provider, new_cfg.llm_model) != (cfg.llm_provider, cfg.llm_model):
        runtime["llm"] = None
    public = new_cfg.to_public_dict()
    dcfg = _data_cfg()
    if dcfg is not None:
        public["default_voice"] = dcfg.default_voice
        public["serien_name"] = dcfg.serien_name
    return jsonify(public)


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
