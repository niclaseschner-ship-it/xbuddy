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

Port: 5053 (HSP-28). Service-Topologie: schlanke eigenständige Flask-App
(Geschwister von wetter/, routine/, plan/).
"""

import argparse
import contextlib
import functools
import json
import logging
import os
import queue
import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import familie_client as _tools_familie_client_mod  # noqa: E402
from tools import logsetup  # noqa: E402
from tools.familie_client import DEFAULT_ORIGIN as _FAMILIE_DEFAULT_ORIGIN  # noqa: E402

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

_INIT_DATA_AVAILABLE = True


logger = logging.getLogger(__name__)

# ============================================================
#  Laufzeit-Zustand (Test-Naht analog wetter/main.py)
# ============================================================

# HSP-3a / HSP-43 (#1263): die „anderen Kinder" ergeben sich aus der hörspiel-
# lokalen Instanz-Liste `config.INSTANZEN` (alle Einträge außer der eigenen
# kind_id) — kein binärer mia↔finn-Toggle mehr, damit n≥3 (emil) additiv
# trägt (HSP-3a n≥3, HSP-46). KEINE Registry, KEIN Cross-Service-Import.

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
    """Prüft ob user_id in der Familien-Registry registriert ist (FAM-7/8).

    T1015: HTTP-Pfad über ``tools.familie_client`` (DCOMP-1-konform, ersetzt
    den früheren familie.json-Direkt-Read).
    """
    familie_ids = _get_familie_client_auth().get_telegram_ids()
    if familie_ids is None:
        return None  # Familie-Service unerreichbar → fail-open
    if user_id not in familie_ids:
        logger.warning("FAM-7: user_id %s ist kein Familien-Mitglied → 403", user_id)
        return jsonify({"error": "Nicht autorisiert — kein Familienmitglied"}), 403
    return None


def require_mini_app_auth(f):
    """Decorator: SOFT-AUTH (V3, #898) — Header optional.

    Verhalten:
    - Fehlt Authorization-Header: pass-through (Kind-Tablet-V1-Niveau).
    - Header vorhanden, ungültig: 401 (vom Helper).
    - Header vorhanden, gültig + Familien-Mitglied: weiter.
    - Header vorhanden, gültig + Nicht-Mitglied: 403.
    - Localhost-Bypass: pass-through.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        # Localhost-Bypass für Internal-Service-Calls.
        if (not request.headers.get("X-Forwarded-For")
                and request.remote_addr in ("127.0.0.1", "::1")):
            return f(*args, **kwargs)

        # V3 Soft-Auth: Header optional. Fehlt ODER leerer "tma "-Wert → pass.
        ah = request.headers.get("Authorization", "").strip()
        if not ah or ah.lower() in ("tma", "tma ") or (
            ah.lower().startswith("tma ") and not ah[4:].strip()
        ):
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
    """Holt aktives Kind + andere Kinder aus Familie-Service (HSP-3a / HSP-43).

    Gibt dict mit 'aktives_kind' (Person | None) und 'andere_kinder' (Liste von
    {'person': Person, 'url': str}) zurück — ein Eintrag je Instanz aus
    `config.INSTANZEN`, deren kind_id != aktive kind_id UND die im Familie-
    Snapshot als Person vorliegt (HSP-3a n≥3, #1263). Fehlt eine Person im
    Snapshot (z. B. emil vor Provisionierung) oder ist der Familie-Service
    unerreichbar, fällt der jeweilige Eintrag weg — Template rendert dann die
    verbleibenden Pillen bzw. gar keine (PLAN-20-Geist).
    """
    client = _get_familie_client()
    registry = client.snapshot()

    aktives_kind = registry.get(kind_id)
    andere_kinder = []
    for inst in config_mod.INSTANZEN:
        other_id = inst["kind_id"]
        if other_id == kind_id:
            continue
        person = registry.get(other_id)
        if person is None:
            continue
        andere_kinder.append({
            "person": person,
            "url": "/display/hoerspiel/%s/alben" % other_id,
        })

    return {"aktives_kind": aktives_kind, "andere_kinder": andere_kinder}


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

@app.route("/display/hoerspiel/<kind_id>/", methods=["GET"])
@app.route("/display/hoerspiel/<kind_id>", methods=["GET"])
def display_index_redirect(kind_id: str):
    """Convenience-Redirect: /display/hoerspiel/<kind_id>/ → /alben.

    Browser-Cache-freundlich: 302 (Found) statt 301 (Moved Permanently),
    damit ein versehentlich abgekürzter URL nicht dauerhaft im Browser-
    Cache landet (Memory feedback_lief_gestern_geht_heute_nicht_reflex —
    Cache-Trap auf URL-Ebene).
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    from flask import redirect
    return redirect("/display/hoerspiel/%s/alben" % kind_id, code=302)


@app.route("/display/hoerspiel/<kind_id>/alben", methods=["GET"])
def display_alben(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    # HSP-3a / HSP-43: Face-Pillen-Reihe aus Familie-Service holen (n≥3, #1263).
    pille = _pille_vars(kind_id)
    return render_template(
        "alben.html",
        aktives_kind=pille["aktives_kind"],
        andere_kinder=pille["andere_kinder"],
    )


# ---- Lese-Endpoints (HSP-17, Side-Effekt-frei) ----

@app.route("/api/v1/hoerspiel/<kind_id>/bible", methods=["GET"])
def bible(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    text = data_io.read_text_or_empty(os.path.join(_data_root(), "bible.md"))
    return text, 200, {"Content-Type": "text/markdown; charset=utf-8"}


@app.route("/api/v1/hoerspiel/<kind_id>/folgen-historie", methods=["GET"])
def folgen_historie(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    text = data_io.read_text_or_empty(os.path.join(_data_root(), "folgen-historie.md"))
    return text, 200, {"Content-Type": "text/markdown; charset=utf-8"}


@app.route("/api/v1/hoerspiel/<kind_id>/alben", methods=["GET", "POST"])
def alben(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    if request.method == "GET":
        return jsonify(album_builder.liste_alben(_data_root()))
    return _post_alben()


@app.route("/api/v1/hoerspiel/<kind_id>/alben/<album_id>/manifest", methods=["GET"])
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
def folgen_vorschlag(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
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
            serien_name=instance.serien_name)
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
            kind_id=_self_kind_id(),
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
    """Baut die vollständige GET /config-Antwort (HSP-17/34/41)."""
    public = cfg.to_public_dict()
    if dcfg is not None:
        public["default_voice"] = dcfg.default_voice
        public["serien_name"] = dcfg.serien_name
        public["pause_absatz_sek"] = dcfg.pause_absatz_sek
        public["pause_titel_sek"] = dcfg.pause_titel_sek
        public["playback_tempo"] = dcfg.playback_tempo
        public["audio_ziel"] = dcfg.audio_ziel
    else:
        public.setdefault("default_voice", config_mod.DEFAULT_VOICE)
        public.setdefault("pause_absatz_sek", config_mod.DEFAULT_PAUSE_ABSATZ_SEK)
        public.setdefault("pause_titel_sek", config_mod.DEFAULT_PAUSE_TITEL_SEK)
        public.setdefault("playback_tempo", config_mod.DEFAULT_PLAYBACK_TEMPO)
        public.setdefault("audio_ziel", config_mod.DEFAULT_AUDIO_ZIEL)
    public["voices_verfuegbar"] = list(config_mod.VALID_VOICES)
    public["audio_ziel_verfuegbar"] = list(config_mod.VALID_AUDIO_ZIEL)
    public["provider_verfuegbar"] = _provider_verfuegbar(cfg)
    public["modelle_je_anbieter"] = _modelle_je_anbieter()
    return public


@app.route("/api/v1/hoerspiel/<kind_id>/config", methods=["GET", "PATCH"])
def config_endpoint(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
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

    # Daten-Konfig-Felder (default_voice, pause_*, playback_tempo, audio_ziel HSP-41).
    dcfg = _data_cfg()
    try:
        new_dcfg = config_mod.patch_data(dcfg, body) if dcfg is not None else dcfg
    except config_mod.ConfigError as e:
        return jsonify({"fehler": str(e)}), 422
    runtime["data_config"] = new_dcfg

    # Persistenz (DCOMP-4, HSP-27/HSP-41): Werte überleben Restart.
    # Vorher schrieb PATCH nur den Memory-Snapshot — playback_tempo, default_voice
    # etc. fielen nach systemctl restart auf Datei-Default zurück.
    if new_dcfg is not None:
        try:
            config_mod.persist_data(new_dcfg)
        except OSError as e:
            logger.warning("hoerspiel/config: persist_data fehlgeschlagen — %s", e)
            # Kein 5xx an den Client — Memory-Stand bleibt aktuell, nur Restart-Persistenz
            # ist betroffen. Eltern sehen den Wert sofort, nach Restart fällt er zurück.

    return jsonify(_build_config_response(new_cfg, new_dcfg))


# ---- Audio-Stream-SSE + play-extern (HSP-42, RATIFIZIERT 2026-06-17) ----
#
# Bei audio_ziel=panel pusht der HSP-Service über SSE an die Panel-PWA.
# Pattern aus router/main.py:106-161 wiederverwendet — Subscribers in einer
# Queue-Liste pro Prozess, Lock für Thread-Safety, 15s-Heartbeat.
#
# Auth: PUBLIC heute (AUTH-6-Backlog, Trigger „Phase 4 HSP-Audio-Routing").
# Caller von /play-extern ist alben.js am Kinder-Tablet (Display-Renderer-
# Klasse AUTH-7); Caller von /audio-stream ist die Panel-PWA. Browser über
# nginx ist kein Loopback (X-Forwarded-For greift).

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
    """Pusht das Event an alle aktuell verbundenen Panel-PWAs."""
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
def audio_stream(kind_id: str):
    """HSP-42: SSE-Stream für Audio-Source-Push an Panel-PWA.

    Caller: app-panel-PWA (controller/app-panel/), pro HSP-Instanz eine
    EventSource-Verbindung. Browser-Native-Reconnect übernimmt Reconnect
    bei Tab-visibility-Change (DC-7-Pattern).

    Auth: PUBLIC (AUTH-6, Trigger „Phase 4 HSP-Audio-Routing").
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    response = Response(_audio_event_stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"  # nginx-Buffering aus
    return response


@app.route("/api/v1/hoerspiel/<kind_id>/play-extern", methods=["POST"])
def play_extern(kind_id: str):
    """HSP-42: Audio-Steuerung an Panel-PWA via SSE-Broadcast.

    Body: {
      "action": "play" | "pause" | "resume",  // Default "play"
      "album_id": <str>,                       // Pflicht bei action=play
      "track_idx": <int>                       // Pflicht bei action=play
    }
    Antwort: 200 {"ok": true} bei Erfolg, 404 unbekanntes album, 422 ungültige Felder.

    Caller: alben.js am Kinder-Tablet bei audio_ziel=panel (HSP-22-Erweiterung).
    Auth: PUBLIC (AUTH-6, Trigger „Phase 4 HSP-Audio-Routing").
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err

    body = request.get_json(silent=True) or {}
    action = body.get("action", "play")

    if action not in ("play", "pause", "resume"):
        return jsonify({"fehler": "action muss play|pause|resume sein"}), 422

    # pause/resume sind body-frei (kein album_id/track_idx nötig).
    if action in ("pause", "resume"):
        event = {"type": "audio_" + action, "kind_id": kind_id}
        _audio_broadcast(event)
        return jsonify({"ok": True})

    # action=play braucht album_id + track_idx + Audio-URL-Auflösung
    album_id = body.get("album_id")
    track_idx = body.get("track_idx")

    if not isinstance(album_id, str) or not album_id:
        return jsonify({"fehler": "album_id (string) fehlt"}), 422
    if not isinstance(track_idx, int):
        return jsonify({"fehler": "track_idx (int) fehlt"}), 422

    # Manifest holen, um Track-Filename + Audio-URL zu bauen
    manifest_path = os.path.join(_data_root(), "alben", album_id, "manifest.json")
    if not os.path.isfile(manifest_path):
        return jsonify({"fehler": "album_id nicht gefunden"}), 404
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("play-extern: manifest %s nicht lesbar — %s", album_id, e)
        return jsonify({"fehler": "manifest nicht lesbar"}), 500

    tracks = manifest.get("tracks") or []
    if not isinstance(tracks, list) or track_idx < 0 or track_idx >= len(tracks):
        return jsonify({"fehler": "track_idx außerhalb des Track-Bereichs"}), 422

    track = tracks[track_idx]
    # Audio-URL über offizielle HSP-37-API-Form (kind_id-tragend)
    audio_filename = track.get("audio-asset") or track.get("filename") or ""
    # audio-asset könnte schon vollständige URL sein, oder nur Dateiname
    if audio_filename.startswith(("/api/v1/", "/display/")):
        audio_url = audio_filename
    else:
        # Fallback: Dateiname aus track-N.mp3-Konvention bauen
        audio_url = "/api/v1/hoerspiel/%s/alben/%s/audio/%s" % (
            kind_id, album_id, os.path.basename(audio_filename))

    event = {
        "type": "audio_play",
        "kind_id": kind_id,
        "album_id": album_id,
        "track_idx": track_idx,
        "audio_url": audio_url,
    }
    _audio_broadcast(event)
    return jsonify({"ok": True})


# ---- Themen-Endpoint (HSP-38, URL-3a, RAT-17) ----

@app.route("/api/v1/hoerspiel/<kind_id>/themen", methods=["GET"])
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
def album_audio(kind_id: str, album_id: str, track_filename: str):
    """HSP-37: Audio-Track streamen mit Range-Requests.

    Auth-Check (HSP-39) läuft via require_mini_app_auth-Decorator vor der
    Range-Logik (401 trumpft 206). send_from_directory blockt Pfad-Traversal.
    `Content-Type: audio/mpeg`, `Cache-Control: private, max-age=86400`.
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
def shared_assets_status(kind_id: str):
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
    return jsonify(tts_service.status_shared_assets(_data_root()))


@app.route("/api/v1/hoerspiel/<kind_id>/shared-assets/rebuild", methods=["POST"])
def shared_assets_rebuild(kind_id: str):
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
def display_data(kind_id: str, sub: str):
    """Liefert Audio-/Cover-Assets aus dem Daten-Bereich aus (HSP-26, URL-3a).

    Streng auf Subpfade unter `data/` begrenzt — `send_from_directory`
    blockt Pfad-Traversal.
    """
    err = _assert_self_kind(kind_id)
    if err is not None:
        return err
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


# T1084: Der strukturierte Folgen-Pfad (HSP-11) läuft seit #1084 über
# `tools.llm` (Singleshot-Sicht). Slot pro Brand-Vendor — derselbe ZD-Slot, den
# die Alt-Provider nutzen (hoerspiel-<vendor>-api-key, HSP-27).
_LIB_SLOT_FOR_PROVIDER = {
    "claude": "hoerspiel-anthropic-api-key",
    "mistral": "hoerspiel-mistral-api-key",
}

# T1281: MAX_TOKENS aus den entfernten Alt-Providern hier zentralisiert.
# claude=8192 — Sicherheits-Puffer für ~3500-Token-Folge.
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

    from .providers.lib_adapter import LibSingleshotAdapter
    slot = _LIB_SLOT_FOR_PROVIDER[cfg.llm_provider]
    max_tokens = _MAX_TOKENS_FOR_PROVIDER[cfg.llm_provider]
    # `model` + `max_tokens` durchreichen: Modell-Erhalt (z. B. claude-opus-4-7)
    # und Token-Limit (T1084: DEFAULT_MAX_TOKENS=2048 < ~3500 Token Folgentext).
    return LibSingleshotAdapter(
        slot=slot, model=cfg.llm_model, max_tokens=max_tokens,
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
