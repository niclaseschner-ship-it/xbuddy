"""Routine-Buddy — Konfigurations-Auflösung (ROUTINE-12).

Zwei getrennte Config-Dateien (BUD-2a):
  routine/routine.json  — Daten-Konfig (Routine-Punkte, Abfahrtszeit, …)
  routine/config.json   — Runtime-Konfig (Bind, Log)

Die Runtime-Config wird über den gemeinsamen tools.configloader geladen
(CONFIG-1/CONFIG-5). Die Daten-Config wird hier eigenständig geparst,
weil ihre Struktur (Items, Zeitwerte) über ein flaches Schema hinausgeht.

Fehlende Datei → Defaults + Warnung, Prozess startet (CONFIG-4).
ENV-Overrides: ROUTINE_<KEY> (CONFIG-5, via configloader für Runtime;
  für Daten-Config: ROUTINE_CONFIG_FILE / ROUTINE_DATA_FILE für Pfade).
"""

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# ROUTINE-12: Pfade der beiden Config-Dateien, per Env überschreibbar.
ENV_DATA_FILE = "ROUTINE_DATA_FILE"
DEFAULT_DATA_FILE = os.path.join(HERE, "routine.json")

# ROUTINE-12: Daten-Konfig-Defaults (alles, was je Familie variiert, CONFIG-4).
# quelle=default-Items haben keinen sinnvollen Default — sie kommen aus der Datei.
DATA_DEFAULTS = {
    "abfahrtszeit": None,          # Pflicht (je Wochentag mögl.)
    "anzieh_vorlauf_min": 8,       # Tuning-Wert, Config-Schlüssel (ROUTINE-9)
    "items": [],
    "zeit_referenzen": {"an": False, "paare": []},
    "zeitzone": "Europe/Berlin",
}


class ConfigError(Exception):
    """Pflicht-Konfiguration fehlt oder ist ungültig (ROUTINE-12)."""


@dataclass
class RoutineItem:
    """Ein Routine-Punkt mit allen Feldern (ROUTINE-4).

    quelle ∈ {default, einmalig, bedingt} — V1 füllt nur default.
    Das Modell trägt quelle von Anfang an, damit spätere Erweiterungen
    keine Datenmodell-Migration erzwingen (E-ROUTINE-2).
    """
    id: str
    label: str
    piktogramm: str                      # numerische ARASAAC-ID als String
    quelle: str = "default"              # default | einmalig | bedingt
    piktogramm_url: str | None = None  # befüllt durch render.icon_url()

    QUELLEN = frozenset({"default", "einmalig", "bedingt"})

    def __post_init__(self):
        if self.quelle not in self.QUELLEN:
            raise ConfigError(
                "RoutineItem %r: quelle=%r ist ungültig "
                "(erwartet: default | einmalig | bedingt)" % (self.id, self.quelle))


@dataclass
class ZeitReferenz:
    """Ein Zeit-Referenz-Balken (ROUTINE-13).

    piktogramm: ARASAAC-ID. dauer_min: Referenz-Dauer in Minuten.
    """
    piktogramm: str
    dauer_min: int


@dataclass
class RoutineConfig:
    """Aufgelöste Daten-Konfiguration des Routine-Buddys (ROUTINE-12)."""
    abfahrtszeit: str              # "HH:MM" (Pflicht)
    anzieh_vorlauf_min: int        # Tuning-Wert (ROUTINE-9)
    items: list[RoutineItem]
    zeitreferenzen_an: bool        # zeit_referenzen.an (ROUTINE-13)
    zeitreferenzen: list[ZeitReferenz]  # Paare (ROUTINE-13)
    zeitzone: str


def _load_file(path, datei_art):
    """Lädt JSON-Datei. Fehlt sie → leeres Dict + Warnung (CONFIG-4)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.warning(
            "%s nicht gefunden (%s) — Defaults gelten, Prozess startet",
            datei_art, path)
        return {}
    except json.JSONDecodeError as e:
        logger.warning(
            "%s nicht parsebar (%s): %s — Defaults bleiben, Prozess startet",
            datei_art, path, e)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "%s hat kein Objekt als Inhalt (%s) — Defaults bleiben",
            datei_art, path)
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _parse_abfahrtszeit(roh):
    """Parst abfahrtszeit — entweder 'HH:MM' oder Wochentag-Dict.

    Gibt immer einen String zurück: 'HH:MM' (für einen fixen Wert)
    oder den Roh-Dict für tagesgenaue Auflösung (handled in uhr.py).
    Ist roh None, wirft ConfigError.
    """
    if roh is None:
        raise ConfigError(
            "`abfahrtszeit` fehlt (Pflicht, ROUTINE-12). "
            "Setze in routine.json: abfahrtszeit: 'HH:MM'")
    return roh  # uhr.py wertet Wochentag-Dict aus


def _parse_items(raw_items):
    """Baut RoutineItem-Liste aus Config-Einträgen (ROUTINE-4).

    V1 erwartet quelle=default; das Modell akzeptiert alle drei Quellen.
    Gibt leere Liste zurück bei leerem oder fehlendem Abschnitt.
    """
    if not raw_items:
        return []
    items = []
    seen_ids = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            logger.warning("items-Eintrag ist kein Objekt: %r — übersprungen", raw)
            continue
        item_id = raw.get("id")
        if not item_id:
            logger.warning("items-Eintrag ohne 'id': %r — übersprungen", raw)
            continue
        if item_id in seen_ids:
            raise ConfigError(
                "Doppelte Item-ID %r (ROUTINE-5). IDs müssen eindeutig sein." % item_id)
        seen_ids.add(item_id)
        label = raw.get("label") or ""
        pikto = str(raw.get("piktogramm", ""))
        quelle = raw.get("quelle", "default")
        try:
            items.append(RoutineItem(
                id=item_id, label=label, piktogramm=pikto, quelle=quelle))
        except ConfigError as e:
            logger.warning("items-Eintrag %r ungültig: %s — übersprungen", item_id, e)
    return items


def _parse_zeitreferenzen(raw_zr):
    """Parst zeit_referenzen-Block (ROUTINE-13, config-schaltbar)."""
    if not isinstance(raw_zr, dict):
        return False, []
    an = bool(raw_zr.get("an", False))
    paare = []
    for raw in raw_zr.get("paare") or []:
        if not isinstance(raw, dict):
            continue
        pikto = str(raw.get("piktogramm", ""))
        dauer = raw.get("dauer_min")
        if not pikto or dauer is None:
            continue
        try:
            paare.append(ZeitReferenz(piktogramm=pikto, dauer_min=int(dauer)))
        except (TypeError, ValueError):
            logger.warning("zeitreferenzen-Paar ungültig: %r — übersprungen", raw)
    return an, paare


def resolve_data(data_path=None, env=None):
    """Löst die Daten-Konfiguration (routine.json) auf (ROUTINE-12).

    data_path: Pfad zu routine.json (Default: ROUTINE_DATA_FILE / Default-Pfad).
    env: überschreibbar für Tests.
    Wirft ConfigError, wenn abfahrtszeit fehlt.
    """
    if env is None:
        env = os.environ
    if data_path is None:
        data_path = env.get(ENV_DATA_FILE) or DEFAULT_DATA_FILE

    raw = _load_file(data_path, "routine.json")

    # Schicht: Defaults < Datei (ROUTINE-12 / CONFIG-4)
    values = dict(DATA_DEFAULTS)
    for key in DATA_DEFAULTS:
        if key in raw:
            values[key] = raw[key]

    abfahrtszeit = _parse_abfahrtszeit(values["abfahrtszeit"])

    try:
        vorlauf = int(values["anzieh_vorlauf_min"])
    except (TypeError, ValueError):
        logger.warning(
            "anzieh_vorlauf_min %r ist keine Zahl — Default 8 greift",
            values["anzieh_vorlauf_min"])
        vorlauf = DATA_DEFAULTS["anzieh_vorlauf_min"]

    items = _parse_items(values["items"])
    an, paare = _parse_zeitreferenzen(values["zeit_referenzen"])
    zeitzone = str(values["zeitzone"]).strip() or DATA_DEFAULTS["zeitzone"]

    return RoutineConfig(
        abfahrtszeit=abfahrtszeit,
        anzieh_vorlauf_min=vorlauf,
        items=items,
        zeitreferenzen_an=an,
        zeitreferenzen=paare,
        zeitzone=zeitzone,
    )
