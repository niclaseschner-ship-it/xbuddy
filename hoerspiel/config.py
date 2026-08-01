"""Hörspiel-Buddy — Konfigurations-Auflösung (HSP-26/HSP-27).

Zwei Per-Instanz-Dateien neben dem Code (BUD-2/BUD-2a, beide gitignored):
  - `config.json` — Runtime-Config (Bind, Log, Provider, Modelle).
  - `hoerspiel.json` — Daten-Konfig (Default-Voice, Serien-Name,
    Pausen-Werte, Playback-Tempo, Themen je Alter).

Geheimnisse (Anthropic-Key, Mistral-Key, Azure-Key) kommen ausschließlich
aus ENV (CONFIG-3) und sind nie Teil der Datei-Quelle. Der Loader verwaltet
sie zusammen mit den restlichen Werten, damit der Live-Pfad einen Ort hat.

V1: gültige `llm_provider`-Werte sind `claude` und `mistral` (HSP-27).
Andere Werte lehnt `resolve_runtime` mit ConfigError ab — dieselbe Klasse,
die der PATCH-Endpoint in HTTP 422 übersetzt.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

ENV_RUNTIME_CONFIG_FILE = "HOERSPIEL_CONFIG_FILE"
DEFAULT_RUNTIME_CONFIG_FILE = os.path.join(HERE, "config.json")

ENV_DATA_CONFIG_FILE = "HOERSPIEL_DATA_CONFIG_FILE"
DEFAULT_DATA_CONFIG_FILE = os.path.join(HERE, "hoerspiel.json")

ENV_DATA_ROOT = "HOERSPIEL_DATA_ROOT"
DEFAULT_DATA_ROOT = os.path.join(HERE, "data")

ENV_KIND_ID = "HOERSPIEL_KIND_ID"
DEFAULT_KIND_ID = "mia"

ENV_KIND_NAME = "HOERSPIEL_KIND_NAME"    # V1-Übergangs-ENV — bis instance.json je Kind angelegt
ENV_KIND_ALTER = "HOERSPIEL_KIND_ALTER"  # V1-Übergangs-ENV — bis instance.json je Kind angelegt

ENV_ANTHROPIC_KEY = "HOERSPIEL_ANTHROPIC_KEY"
ENV_MISTRAL_KEY = "HOERSPIEL_MISTRAL_KEY"
ENV_AZURE_ENDPOINT = "HOERSPIEL_AZURE_OPENAI_ENDPOINT"
ENV_AZURE_DEPLOYMENT = "HOERSPIEL_AZURE_OPENAI_DEPLOYMENT"
ENV_AZURE_KEY = "HOERSPIEL_AZURE_OPENAI_KEY"

VALID_PROVIDERS = ("claude", "mistral")
VALID_VOICES = ("shimmer", "onyx")

DEFAULT_LLM_MODEL = "claude-opus-4-7"
DEFAULT_VOICE = "onyx"
# T1382/OPEN-HSP-W/-X: kein Code-Default-Serien-Name mehr (Mia-Leak). serien_name
# ist rein instanz-getragen (instance.json, HSP-27); neutral leer wenn ungesetzt.

# INST-1 (conventions/instanzen-config.md, #1656): die Instanz-Liste ist KEINE
# Code-Konstante mehr — sie kommt aus der Repo-Root-`instanzen.json`
# (tools.instanzen). Fehlt/kaputt die Datei, greift der Loader-Default (INST-6).
# Diese Komponente nutzt nur kind_id (Ring-Reihenfolge in main.py) + name.
# Mapping: kind_id = slug, name = display_name. Scope-Grenze (INST-3): NIE
# port/origin/service/pfad — die bleiben conventions/ports.md / Runtime-Config.
def instanzen() -> list[dict]:
    """hörspiel-lokale Instanz-Liste (kind_id/name) aus instanzen.json (INST-1).

    Reine Anzeige-/Reihenfolge-Ableitung — generiert keinen Port/keine Route
    (INST-3). Fehlt die Datei, kommt der eingebettete Loader-Default (INST-6).
    """
    from tools import instanzen as _instanzen_mod
    return [
        {"kind_id": e["slug"], "name": e["display_name"]}
        for e in _instanzen_mod.lade_instanzen("hoerspiel")
    ]

# HSP-14 / HSP-27 — Pausen-Defaults (familien-konfigurierbar in hoerspiel.json).
DEFAULT_PAUSE_ABSATZ_SEK: float = 0.55
DEFAULT_PAUSE_TITEL_SEK: float = 1.8
DEFAULT_PLAYBACK_TEMPO: float = 1.0

# HSP-27a — Themen-Defaults für V1 (Alter 4 → 8 Themen).
DEFAULT_THEMEN_JE_ALTER: dict[str, list[str]] = {
    "4": [
        "Mut beim Probieren",
        "Streit vertragen",
        "Selbst anziehen / aufräumen",
        "Warten lernen",
        "Gefühle erkennen und benennen",
        "Jahreszeiten erleben",
        "Bitte und Danke",
        "Neue Sachen essen",
    ],
}


class InstanceConfig:
    """Per-Kind-Instanz-Daten — aus instance.json (HSP-27) oder ENV-Fallback (V1).

    Felder:
    - kind_id   — Instanz-Identität (Pflicht-Feld in instance.json)
    - name      — Anzeige-Name des Kindes (z. B. "Mia")
    - alter     — Alter als int (aus instance.json oder ENV HOERSPIEL_KIND_ALTER)
    - themen_je_alter — Map alter-str → list[str] (aus instance.json oder DataConfig)
    - zielgruppe   — deskriptiv "kind" | "erwachsen" — steuert Prompt-Schnitt + Recherche-Vorschritt (HSP-56/58)
    - ton          — Erzähl-Ton der Serie (HSP-45, Story-Prompt-Kontext)
    - perspektive  — Erzähl-Perspektive (HSP-45, Story-Prompt-Kontext)
    - serien_name  — Serien-Rahmung dieser Instanz (HSP-45, Name-Drift-Fix)
    - voices       — Sprecher→Voice-Map für Multi-Voice-TTS (T1621, optional);
                     None/leer → Single-Voice-Pfad (Kind-Instanzen unverändert).
                     Jede gemappte Voice muss in VALID_VOICES sein (ValueError sonst).

    zielgruppe/ton/perspektive/serien_name kommen aus instance.json (HSP-27); leer
    → keine Serien-Zeile im Prompt (DEFAULT_SERIEN_RAHMEN='' neutral, T1336/OPEN-HSP-W).
    """

    def __init__(self, kind_id: str, name: str, alter: int,
                 themen_je_alter: dict[str, list[str]] | None = None,
                 zielgruppe: str = "kind", ton: str = "",
                 perspektive: str = "", serien_name: str = "",
                 voices: "dict[str, str] | None" = None):
        self.kind_id = kind_id
        self.name = name
        self.alter = alter
        self.themen_je_alter = themen_je_alter if themen_je_alter is not None \
            else dict(DEFAULT_THEMEN_JE_ALTER)
        self.zielgruppe = zielgruppe
        self.ton = ton
        self.perspektive = perspektive
        self.serien_name = serien_name
        self.voices = voices or None


def load_instance(data_root: str, kind_id: str,
                  env: dict[str, str] | None = None,
                  data_cfg: "DataConfig | None" = None) -> InstanceConfig:
    """Lädt die instance.json aus <data_root>/instance.json (HSP-27).

    Fallback-Kette (V1-Übergangs-Lösung bis instance.json je Kind angelegt):
      1. instance.json vorhanden + gültig: dessen Werte.
      2. Datei fehlt oder ungültig: ENV HOERSPIEL_KIND_NAME + ENV
         HOERSPIEL_KIND_ALTER + themen_je_alter aus DataConfig (oder Default).

    Ist weder instance.json noch ENV gesetzt, liefert `name` einen
    leeren String und `alter` 0. Die Themen-Endpoint-Route gibt dann
    422 zurück (Alter 0 ist nie in themen_je_alter — klare Fehlermeldung
    statt Mia-Hardcode). Kein hardcoded Mia-Default.
    """
    if env is None:
        env = dict(os.environ)

    instance_path = os.path.join(data_root, "instance.json")
    raw = _load_json(instance_path)

    # Wenn instance.json vorhanden und kind_id-Feld stimmt: Datei-Werte nutzen.
    if raw and raw.get("kind_id") == kind_id:
        try:
            alter_raw = raw.get("alter")
            alter = int(alter_raw) if alter_raw is not None else 0
        except (TypeError, ValueError):
            alter = 0

        name = str(raw.get("name") or "").strip()

        raw_themen = raw.get("themen_je_alter")
        if isinstance(raw_themen, dict):
            themen_je_alter = {str(k): list(v) for k, v in raw_themen.items()
                               if isinstance(v, list)}
        elif data_cfg is not None:
            themen_je_alter = dict(data_cfg.themen_je_alter)
        else:
            themen_je_alter = dict(DEFAULT_THEMEN_JE_ALTER)

        # HSP-45 / #1263: Erwachsenen-Achse + Name-Drift-Kontext rein aus Daten.
        # Leer → keine „Serie:"-Zeile (DEFAULT_SERIEN_RAHMEN='' neutral, T1336/OPEN-HSP-W).

        # T1621: Sprecher→Voice-Map für Multi-Voice-TTS (optional, nur emil-Instanz).
        # None/leer → Single-Voice-Pfad (Kind-Instanzen unverändert, byte-gleich).
        voices_raw = raw.get("voices")
        voices: dict[str, str] | None = None
        if isinstance(voices_raw, dict) and voices_raw:
            validated: dict[str, str] = {}
            for sprecher, v in voices_raw.items():
                v_str = str(v).strip().lower()
                if v_str not in VALID_VOICES:
                    raise ValueError(
                        "instance.json voices[%r]=%r ist V1 nicht unterstützt — "
                        "erlaubt: %s (T1621)" % (sprecher, v, ", ".join(VALID_VOICES)))
                validated[str(sprecher)] = v_str
            voices = validated if validated else None

        return InstanceConfig(
            kind_id=kind_id,
            name=name,
            alter=alter,
            themen_je_alter=themen_je_alter,
            zielgruppe=str(raw.get("zielgruppe") or "kind").strip(),
            ton=str(raw.get("ton") or "").strip(),
            perspektive=str(raw.get("perspektive") or "").strip(),
            serien_name=str(raw.get("serien_name") or "").strip(),
            voices=voices,
        )

    # Fallback: instance.json fehlt oder für andere kind_id — ENV-Overgangs-Werte.
    logger.info(
        "hoerspiel/config: instance.json nicht gefunden oder kind_id-Mismatch "
        "(%s) — nutze ENV-Fallback HOERSPIEL_KIND_NAME / HOERSPIEL_KIND_ALTER",
        instance_path)

    name = str(env.get(ENV_KIND_NAME) or "").strip()
    alter_env = env.get(ENV_KIND_ALTER, "").strip()
    try:
        alter = int(alter_env) if alter_env else 0
    except (TypeError, ValueError):
        alter = 0

    themen_je_alter = (dict(data_cfg.themen_je_alter) if data_cfg is not None
                       else dict(DEFAULT_THEMEN_JE_ALTER))

    return InstanceConfig(
        kind_id=kind_id,
        name=name,
        alter=alter,
        themen_je_alter=themen_je_alter,
    )


class ConfigError(Exception):
    """Pflicht-Konfiguration fehlt oder ist ungültig (HSP-26/HSP-27)."""


def _resolve_kind_id(raw: Any) -> str:
    """Validiert die kind_id gegen [a-z]+ (CONFIG-3, HSP-25, URL-3a)."""
    import re
    val = (str(raw) if raw is not None else DEFAULT_KIND_ID).strip().lower()
    if not val or not re.fullmatch(r"[a-z]+", val):
        raise ConfigError(
            "HOERSPIEL_KIND_ID %r ist ungültig — erlaubt: lowercase [a-z]+ (HSP-25, URL-3a)"
            % val)
    return val


class RuntimeConfig:
    """Runtime-Config-Snapshot (Bind, Log, Provider, Modell + Secrets + kind_id)."""

    def __init__(self, listen_host: str, listen_port: int, log_level: str,
                 llm_provider: str, llm_model: str,
                 anthropic_key: str | None,
                 mistral_key: str | None = None,
                 azure_endpoint: str | None = None,
                 azure_deployment: str | None = None,
                 azure_key: str | None = None,
                 kind_id: str = DEFAULT_KIND_ID):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.log_level = log_level
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.anthropic_key = anthropic_key
        self.mistral_key = mistral_key
        self.azure_endpoint = azure_endpoint
        self.azure_deployment = azure_deployment
        self.azure_key = azure_key
        self.kind_id = kind_id

    def to_public_dict(self) -> dict[str, Any]:
        """Basis-Form für `GET /config` (HSP-17). Geheimnisse fliegen raus (LOG-3).

        Wird von main.py mit DataConfig-Feldern und modelle_je_anbieter ergänzt.
        """
        return {
            "kind_id": self.kind_id,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "default_voice": None,
            "serien_name": None,
            "anthropic_key_set": bool(self.anthropic_key),
            "mistral_key_set": bool(self.mistral_key),
            "azure_key_set": bool(self.azure_key),
        }


class DataConfig:
    """Daten-Konfig — familien-spezifisch (HSP-27).

    Felder (alle in hoerspiel.json, via PATCH /config setzbar):
    - default_voice       — Default-Voice für neue Folgen (HSP-13)
    - serien_name         — Anzeige-Name der Serie
    - pause_absatz_sek    — Stille zwischen Inhalts-Absätzen (HSP-14)
    - pause_titel_sek     — Stille nach Titel-Absatz (HSP-14)
    - playback_tempo      — Wiedergabe-Geschwindigkeit im Player (HSP-34)
    - themen_je_alter     — kuratierte Themen-Liste je Alter (HSP-27a)
    """

    def __init__(self, default_voice: str, serien_name: str,
                 pause_absatz_sek: float = DEFAULT_PAUSE_ABSATZ_SEK,
                 pause_titel_sek: float = DEFAULT_PAUSE_TITEL_SEK,
                 playback_tempo: float = DEFAULT_PLAYBACK_TEMPO,
                 themen_je_alter: dict | None = None):
        self.default_voice = default_voice
        self.serien_name = serien_name
        self.pause_absatz_sek = pause_absatz_sek
        self.pause_titel_sek = pause_titel_sek
        self.playback_tempo = playback_tempo
        self.themen_je_alter = themen_je_alter if themen_je_alter is not None \
            else dict(DEFAULT_THEMEN_JE_ALTER)


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("config-Datei nicht gefunden (%s) — Defaults gelten", path)
        return {}
    except json.JSONDecodeError as e:
        logger.warning("config-Datei nicht parsebar (%s): %s — Defaults bleiben", path, e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _resolve_provider(raw: Any) -> str:
    """Validiert den `llm_provider`-Wert gegen die V1-Whitelist (HSP-27)."""
    val = (str(raw) if raw is not None else "claude").strip().lower()
    if val not in VALID_PROVIDERS:
        raise ConfigError(
            "llm_provider %r ist nicht unterstützt — erlaubt: %s (HSP-27)"
            % (val, ", ".join(VALID_PROVIDERS)))
    return val


def resolve_runtime(config_path: str | None = None,
                    env: dict[str, str] | None = None) -> RuntimeConfig:
    """Löst die Runtime-Config nach HSP-26/HSP-27 auf.

    Reihenfolge: Code-Default < Datei < ENV (CONFIG-1/CONFIG-5).
    Secrets kommen ausschließlich aus ENV (CONFIG-3).
    """
    if env is None:
        env = dict(os.environ)
    if config_path is None:
        config_path = env.get(ENV_RUNTIME_CONFIG_FILE) or DEFAULT_RUNTIME_CONFIG_FILE

    file_cfg = _load_json(config_path)

    listen_host = str(env.get("HOERSPIEL_LISTEN_HOST")
                      or file_cfg.get("listen_host") or "127.0.0.1")
    listen_port_raw = env.get("HOERSPIEL_LISTEN_PORT") or file_cfg.get("listen_port") or 5053
    try:
        listen_port = int(listen_port_raw)
    except (TypeError, ValueError) as e:
        raise ConfigError("listen_port ist keine Zahl: %r" % listen_port_raw) from e
    log_level = str(env.get("HOERSPIEL_LOG_LEVEL")
                    or file_cfg.get("log_level") or "INFO").upper()

    llm_provider = _resolve_provider(env.get("HOERSPIEL_LLM_PROVIDER")
                                     or file_cfg.get("llm_provider") or "claude")
    llm_model = str(env.get("HOERSPIEL_LLM_MODEL")
                    or file_cfg.get("llm_model") or DEFAULT_LLM_MODEL).strip()

    kind_id = _resolve_kind_id(env.get(ENV_KIND_ID) or DEFAULT_KIND_ID)

    return RuntimeConfig(
        listen_host=listen_host,
        listen_port=listen_port,
        log_level=log_level,
        llm_provider=llm_provider,
        llm_model=llm_model,
        anthropic_key=env.get(ENV_ANTHROPIC_KEY),
        mistral_key=env.get(ENV_MISTRAL_KEY),
        azure_endpoint=env.get(ENV_AZURE_ENDPOINT),
        azure_deployment=env.get(ENV_AZURE_DEPLOYMENT),
        azure_key=env.get(ENV_AZURE_KEY),
        kind_id=kind_id,
    )


def resolve_data(config_path: str | None = None,
                 env: dict[str, str] | None = None) -> DataConfig:
    """Löst die Daten-Konfig auf (HSP-27).

    Liest Default-Voice, Serien-Name, Pausen-Werte, Playback-Tempo
    und Themen je Alter aus hoerspiel.json.
    Reihenfolge: Code-Default < Datei (CONFIG-1).
    Audio immer lokal am App-Gerät (HSP-41 aufgehoben).
    """
    if env is None:
        env = dict(os.environ)
    if config_path is None:
        config_path = env.get(ENV_DATA_CONFIG_FILE) or DEFAULT_DATA_CONFIG_FILE
    file_cfg = _load_json(config_path)

    default_voice = str(file_cfg.get("default_voice") or DEFAULT_VOICE).strip().lower()
    if default_voice not in VALID_VOICES:
        raise ConfigError(
            "default_voice %r ist V1 nicht unterstützt — erlaubt: %s (HSP-13)"
            % (default_voice, ", ".join(VALID_VOICES)))
    # T1382/HSP-45: neutral leer statt 'Stigi & Co.' als Default — kein Mia-Leak
    # auf Nicht-Mia-Instanzen. Instanz-spezifischer serien_name lebt in instance.json
    # (HSP-27); hoerspiel.json trägt nur PATCH-gesetzten Override (DEFAULT_SERIEN_RAHMEN='').
    serien_name = str(file_cfg.get("serien_name") or "")

    # Pausen-Werte (Range-Validierung analog PATCH /config).
    try:
        pause_absatz = float(file_cfg.get("pause_absatz_sek", DEFAULT_PAUSE_ABSATZ_SEK))
    except (TypeError, ValueError):
        pause_absatz = DEFAULT_PAUSE_ABSATZ_SEK

    try:
        pause_titel = float(file_cfg.get("pause_titel_sek", DEFAULT_PAUSE_TITEL_SEK))
    except (TypeError, ValueError):
        pause_titel = DEFAULT_PAUSE_TITEL_SEK

    try:
        playback_tempo = float(file_cfg.get("playback_tempo", DEFAULT_PLAYBACK_TEMPO))
    except (TypeError, ValueError):
        playback_tempo = DEFAULT_PLAYBACK_TEMPO

    themen_je_alter_raw = file_cfg.get("themen_je_alter")
    if isinstance(themen_je_alter_raw, dict):
        themen_je_alter = {str(k): list(v) for k, v in themen_je_alter_raw.items()
                           if isinstance(v, list)}
    else:
        themen_je_alter = dict(DEFAULT_THEMEN_JE_ALTER)

    return DataConfig(
        default_voice=default_voice,
        serien_name=serien_name,
        pause_absatz_sek=pause_absatz,
        pause_titel_sek=pause_titel,
        playback_tempo=playback_tempo,
        themen_je_alter=themen_je_alter,
    )


def patch_runtime(cfg: RuntimeConfig, patch: dict[str, Any]) -> RuntimeConfig:
    """Applies `PATCH /config`-Body auf einen Runtime-Snapshot (HSP-17).

    Erkennt `llm_provider` und `llm_model`. Andere Schlüssel ignoriert.
    Wirft ConfigError bei unbekanntem Provider — `main.py` übersetzt das in
    HTTP 422. Wirft ConfigError, wenn der gewählte Provider keinen
    konfigurierten API-Key hat (HSP-17, „Provider-Switch ohne Key
    wird nie aktiv").
    """
    new_provider = cfg.llm_provider
    new_model = cfg.llm_model
    if "llm_provider" in patch:
        new_provider = _resolve_provider(patch["llm_provider"])
    if "llm_model" in patch and patch["llm_model"] is not None:
        new_model = str(patch["llm_model"]).strip()
    if new_provider == "claude" and not cfg.anthropic_key:
        raise ConfigError(
            "llm_provider=claude verlangt einen Anthropic-Key (HOERSPIEL_ANTHROPIC_KEY) — "
            "Provider-Switch ohne Key wird nicht aktiv (HSP-17)")
    if new_provider == "mistral" and not cfg.mistral_key:
        raise ConfigError(
            "llm_provider=mistral verlangt einen Mistral-Key (HOERSPIEL_MISTRAL_KEY / "
            "ZD-Slot hoerspiel-mistral-api-key) — Provider-Switch ohne Key wird nicht aktiv (HSP-27)")
    return RuntimeConfig(
        listen_host=cfg.listen_host, listen_port=cfg.listen_port,
        log_level=cfg.log_level,
        llm_provider=new_provider, llm_model=new_model,
        anthropic_key=cfg.anthropic_key,
        mistral_key=cfg.mistral_key,
        azure_endpoint=cfg.azure_endpoint,
        azure_deployment=cfg.azure_deployment,
        azure_key=cfg.azure_key,
        kind_id=cfg.kind_id,
    )


def data_config_to_dict(dcfg: DataConfig) -> dict[str, Any]:
    """Serialisiert DataConfig zu dict für hoerspiel.json (HSP-27)."""
    return {
        "default_voice": dcfg.default_voice,
        "serien_name": dcfg.serien_name,
        "pause_absatz_sek": dcfg.pause_absatz_sek,
        "pause_titel_sek": dcfg.pause_titel_sek,
        "playback_tempo": dcfg.playback_tempo,
        "themen_je_alter": dcfg.themen_je_alter,
    }


def persist_data(dcfg: DataConfig, config_path: str | None = None,
                 env: dict[str, str] | None = None) -> None:
    """Schreibt DataConfig atomar in hoerspiel.json (DCOMP-4, HSP-27).

    Bisher hat PATCH /config nur den Runtime-Snapshot ersetzt — Werte
    überlebten keinen Restart. Mit dieser Funktion persistiert PATCH die
    Datei. Gilt für ALLE Daten-Config-Felder.
    """
    if env is None:
        env = dict(os.environ)
    if config_path is None:
        config_path = env.get(ENV_DATA_CONFIG_FILE) or DEFAULT_DATA_CONFIG_FILE
    # Existing-Datei lesen, _comment-Feld bewahren (falls vorhanden)
    from . import data_io
    existing = data_io.read_json_or_empty(config_path)
    new_data = data_config_to_dict(dcfg)
    # _comment und sonstige Meta-Felder behalten
    for k, v in existing.items():
        if k.startswith("_") and k not in new_data:
            new_data[k] = v
    data_io.atomic_write_json(config_path, new_data)


def patch_data(dcfg: DataConfig, patch: dict[str, Any]) -> DataConfig:
    """Applies `PATCH /config`-Body auf einen DataConfig-Snapshot (HSP-17/34).

    Erkennt: default_voice, pause_absatz_sek, pause_titel_sek, playback_tempo.
    Wirft ConfigError bei Range-Verletzungen oder unbekannter Voice —
    `main.py` übersetzt das in HTTP 422.
    Unbekannte Patch-Felder werden still ignoriert.
    """
    new_voice = dcfg.default_voice
    new_pause_absatz = dcfg.pause_absatz_sek
    new_pause_titel = dcfg.pause_titel_sek
    new_playback_tempo = dcfg.playback_tempo

    if "default_voice" in patch:
        v = str(patch["default_voice"]).strip().lower()
        if v not in VALID_VOICES:
            raise ConfigError(
                "default_voice %r ist nicht unterstützt — erlaubt: %s (HSP-13)"
                % (v, ", ".join(VALID_VOICES)))
        new_voice = v

    if "pause_absatz_sek" in patch:
        try:
            val = float(patch["pause_absatz_sek"])
        except (TypeError, ValueError) as exc:
            raise ConfigError("pause_absatz_sek muss eine Zahl sein") from exc
        if not (0.0 <= val <= 2.0):
            raise ConfigError(
                "pause_absatz_sek %r liegt außerhalb des erlaubten Bereichs 0.0–2.0" % val)
        new_pause_absatz = val

    if "pause_titel_sek" in patch:
        try:
            val = float(patch["pause_titel_sek"])
        except (TypeError, ValueError) as exc:
            raise ConfigError("pause_titel_sek muss eine Zahl sein") from exc
        if not (0.5 <= val <= 3.0):
            raise ConfigError(
                "pause_titel_sek %r liegt außerhalb des erlaubten Bereichs 0.5–3.0" % val)
        new_pause_titel = val

    if "playback_tempo" in patch:
        try:
            val = float(patch["playback_tempo"])
        except (TypeError, ValueError) as exc:
            raise ConfigError("playback_tempo muss eine Zahl sein") from exc
        if not (0.7 <= val <= 1.3):
            raise ConfigError(
                "playback_tempo %r liegt außerhalb des erlaubten Bereichs 0.7–1.3" % val)
        new_playback_tempo = val

    return DataConfig(
        default_voice=new_voice,
        serien_name=dcfg.serien_name,
        pause_absatz_sek=new_pause_absatz,
        pause_titel_sek=new_pause_titel,
        playback_tempo=new_playback_tempo,
        themen_je_alter=dcfg.themen_je_alter,
    )
