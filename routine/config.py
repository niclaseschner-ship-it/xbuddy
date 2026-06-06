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

Schreib-API (ROUTINE-14, #343):
  write_data(data_path, updates) — validiert Zeiten-Schlüssel und schreibt
  atomar (DCOMP-4) in routine.json. Einzige Schreibstelle — keine andere
  Komponente schreibt direkt in routine.json (APP-3).
"""

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# ROUTINE-12: Pfade der beiden Config-Dateien, per Env überschreibbar.
ENV_DATA_FILE = "ROUTINE_DATA_FILE"
DEFAULT_DATA_FILE = os.path.join(HERE, "routine.json")

# ROUTINE-12: Daten-Konfig-Defaults (alles, was je Familie variiert, CONFIG-4).
# Diese Werte sind Fallback-Defaults — die Wahrheit bleibt die Datei/der Eltern-Chat.
# Keine Familie-1-Einbackung: Defaults ermöglichen Prozessstart ohne Datei,
# sind aber durch routine.json oder später per Eltern-Chat (OPEN-ROUTINE-B)
# überschreibbar. (#335)
# _DEFAULT_ITEMS: bewusster, eingefrorener Bootstrap-Fallback-Satz (4 Items aus
# routine.example.json). Änderung des Example-Sets → mitziehen. Wahrheit bleibt
# die Config-Datei/der Eltern-Chat.
_DEFAULT_ITEMS = [
    {"id": "fruehstueck", "label": "Frühstück",    "piktogramm": "4626",  "quelle": "default"},
    {"id": "zaehne",      "label": "Zähne putzen", "piktogramm": "2326",  "quelle": "default"},
    {"id": "brotdose",    "label": "Brotdose",     "piktogramm": "31091", "quelle": "default"},
    {"id": "rucksack",    "label": "Rucksack",     "piktogramm": "2475",  "quelle": "default"},
]

DATA_DEFAULTS = {
    "abfahrtszeit": "08:30",       # Fallback-Default (CONFIG-4, #335); Wahrheit kommt aus Datei
    "aufstehzeit": "07:00",        # Fallback-Default (AC-FIX1, #335); Config-Schlüssel, nicht abgeleitet
    "anzieh_vorlauf_min": 8,       # Tuning-Wert, Config-Schlüssel (ROUTINE-9)
    "items": _DEFAULT_ITEMS,       # 4 Fallback-Punkte (aus routine.example.json); Wahrheit aus Datei
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
    abfahrtszeit: str              # "HH:MM" oder Wochentag-Dict; Default '08:30' (CONFIG-4)
    aufstehzeit: str               # "HH:MM" oder Wochentag-Dict; Default '07:00' (AC-FIX1, #335)
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


def _parse_zeit_cfg(roh, schluessel, default):
    """Parst einen Zeit-Konfig-Wert — entweder 'HH:MM' oder Wochentag-Dict.

    Gibt immer einen String/Dict zurück: 'HH:MM' (für einen fixen Wert)
    oder den Roh-Dict für tagesgenaue Auflösung (handled in uhr.py).
    Ist roh None oder kein String/Dict → Warnung + default (CONFIG-4, #335).
    Kein ConfigError — Prozess startet immer (Nic-Entscheidung ROUTINE-12).

    schluessel: Config-Schlüssel-Name für Warn-Meldung (z. B. 'abfahrtszeit').
    default: Fallback-Wert aus DATA_DEFAULTS.
    """
    if roh is None or not isinstance(roh, (str, dict)):
        logger.warning(
            "`%s` fehlt oder hat ungültigen Typ (%r) — "
            "Default %r greift (CONFIG-4, #335). "
            "Setze in routine.json: %s: 'HH:MM'", schluessel, roh, default, schluessel)
        return default
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
    Fehlende/kaputte Datei oder fehlende Werte → Defaults + Warnung,
    Prozess startet (CONFIG-4, #335). Kein ConfigError für fehlende abfahrtszeit.
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

    abfahrtszeit = _parse_zeit_cfg(
        values["abfahrtszeit"], "abfahrtszeit", DATA_DEFAULTS["abfahrtszeit"])
    aufstehzeit = _parse_zeit_cfg(
        values["aufstehzeit"], "aufstehzeit", DATA_DEFAULTS["aufstehzeit"])

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
        aufstehzeit=aufstehzeit,
        anzieh_vorlauf_min=vorlauf,
        items=items,
        zeitreferenzen_an=an,
        zeitreferenzen=paare,
        zeitzone=zeitzone,
    )


# ============================================================
#  Schreib-API (ROUTINE-14, #343): Validierung + atomares Schreiben
# ============================================================

# Gültige Wochentags-Keys laut ROUTINE-14 (fester Satz, lowercase).
# API nimmt lowercase entgegen (ROUTINE-14); write_data normalisiert beim
# Persistieren auf capitalized File-Form (Mo..So), die uhr.py liest (ROUTINE-12).
GUELTIGE_WOCHENTAGS_KEYS = frozenset({"mo", "di", "mi", "do", "fr", "sa", "so"})

# Normalisierungs-Map: API-lowercase → File-capitalized (ROUTINE-12, ROUTINE-14).
# Schreib-API nimmt mo/di/... entgegen; routine.json speichert Mo/Di/...;
# uhr.py._parse_abfahrtszeit sucht die capitalized Form ["Mo","Di",...].
_WOCHENTAG_LOWERCASE_ZU_CAPITALIZED = {
    "mo": "Mo", "di": "Di", "mi": "Mi",
    "do": "Do", "fr": "Fr", "sa": "Sa", "so": "So",
}


class ValidationError(Exception):
    """Ungültige Eingabe am Schreib-Endpoint (ROUTINE-14, AC2)."""


def _validate_zeitwert(schluessel, wert):
    """Validiert einen Zeitwert: entweder 'HH:MM' (24h) oder Wochentag-Map.

    Ungültiges Format → ValidationError, kein Schreiben (ROUTINE-14, AC2).
    """
    if isinstance(wert, str):
        # Strikt HH:MM (24h)
        import re
        if not re.fullmatch(r"[0-2]\d:[0-5]\d", wert):
            raise ValidationError(
                "%s: '%s' ist kein gültiges HH:MM-Format (24h, z.B. '08:30')"
                % (schluessel, wert))
        # Stunden-Range: 00–23
        stunden = int(wert[:2])
        if stunden > 23:
            raise ValidationError(
                "%s: Stunden '%s' außerhalb 00–23" % (schluessel, wert))
    elif isinstance(wert, dict):
        # Wochentag-Map: nur gültige Keys, Werte entweder '' (kein Schultag) oder HH:MM
        for key, val in wert.items():
            if key.lower() not in GUELTIGE_WOCHENTAGS_KEYS:
                raise ValidationError(
                    "%s: ungültiger Wochentags-Key '%s' "
                    "(erlaubt: %s)"
                    % (schluessel, key,
                       ", ".join(sorted(GUELTIGE_WOCHENTAGS_KEYS))))
            if val != "":
                import re
                if not re.fullmatch(r"[0-2]\d:[0-5]\d", val):
                    raise ValidationError(
                        "%s[%s]: '%s' ist kein gültiges HH:MM-Format "
                        "(oder '' für kein Schultag)" % (schluessel, key, val))
                stunden = int(val[:2])
                if stunden > 23:
                    raise ValidationError(
                        "%s[%s]: Stunden '%s' außerhalb 00–23"
                        % (schluessel, key, val))
    else:
        raise ValidationError(
            "%s: erwartet 'HH:MM'-String oder Wochentag-Map, "
            "erhalten: %r" % (schluessel, type(wert).__name__))


def write_data(data_path, updates):
    """Schreibt Zeit-Schlüssel der Daten-Konfig atomar in routine.json (ROUTINE-14).

    updates: Dict mit einem oder mehreren der Zeit-Schlüssel:
      abfahrtszeit  — 'HH:MM' oder Wochentag-Map
      aufstehzeit   — 'HH:MM' oder Wochentag-Map
      anzieh_vorlauf_min — int ≥ 0

    Validierung VOR dem Schreiben (ROUTINE-14, AC2): ungültige Eingabe →
    ValidationError, kein Schreiben, kein Teil-Write.

    Persistenz (DCOMP-4): schreibt erst in eine Temp-Datei im selben
    Verzeichnis, dann atomares os.replace → kein halb-geschriebener Stand
    für gleichzeitige Lese-Zugriffe.

    Nur diese Funktion schreibt routine.json (APP-3, ROUTINE-14) — kein
    anderer Pfad.
    """
    SCHREIBBARE_SCHLUESSEL = frozenset(
        {"abfahrtszeit", "aufstehzeit", "anzieh_vorlauf_min"})

    # Mindestens ein Schlüssel erforderlich (ROUTINE-14)
    relevante = {k: v for k, v in updates.items() if k in SCHREIBBARE_SCHLUESSEL}
    if not relevante:
        raise ValidationError(
            "Mindestens einer der Schlüssel %s ist erforderlich"
            % sorted(SCHREIBBARE_SCHLUESSEL))

    # Validierung ALLER Felder vor dem ersten Schreib-Byte (kein Teil-Write)
    for schluessel, wert in relevante.items():
        if schluessel in ("abfahrtszeit", "aufstehzeit"):
            _validate_zeitwert(schluessel, wert)
        elif schluessel == "anzieh_vorlauf_min":
            if not isinstance(wert, int) or isinstance(wert, bool):
                raise ValidationError(
                    "anzieh_vorlauf_min muss ein Integer sein, erhalten: %r"
                    % type(wert).__name__)
            if wert < 0:
                raise ValidationError(
                    "anzieh_vorlauf_min muss ≥ 0 sein, erhalten: %d" % wert)

    # Normalisierung: Wochentag-Maps von lowercase API-Form → capitalized File-Form.
    # API akzeptiert lowercase (mo/di/..., ROUTINE-14); routine.json und uhr.py
    # erwarten capitalized Keys (Mo/Di/..., ROUTINE-12).
    normiert = {}
    for schluessel, wert in relevante.items():
        if schluessel in ("abfahrtszeit", "aufstehzeit") and isinstance(wert, dict):
            normiert[schluessel] = {
                _WOCHENTAG_LOWERCASE_ZU_CAPITALIZED.get(k.lower(), k): v
                for k, v in wert.items()
            }
        else:
            normiert[schluessel] = wert

    # Aktuellen Stand lesen (fehlende Datei → leeres Dict → Defaults greifen beim Lesen)
    try:
        with open(data_path, encoding="utf-8") as f:
            aktuell = json.load(f)
        if not isinstance(aktuell, dict):
            aktuell = {}
    except FileNotFoundError:
        aktuell = {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(
            "routine.json nicht lesbar vor dem Schreiben (%s): %s — "
            "schreibe Updates über leere Basis", data_path, e)
        aktuell = {}

    # Updates mergen (normierte Form, ROUTINE-12: capitalized Wochentag-Keys)
    aktuell.update(normiert)

    # Atomar schreiben: Temp-Datei im selben Verzeichnis, dann os.replace (DCOMP-4)
    verzeichnis = os.path.dirname(os.path.abspath(data_path))
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp",
                                        prefix="routine_write_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(aktuell, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, data_path)
        except Exception:
            # Temp-Datei aufräumen, wenn os.replace fehlschlägt
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except OSError as e:
        raise OSError(
            "routine.json konnte nicht atomar geschrieben werden (%s): %s"
            % (data_path, e)) from e

    logger.info(
        "routine.json aktualisiert (ROUTINE-14): %s",
        ", ".join("%s=%r" % (k, v) for k, v in normiert.items()))
