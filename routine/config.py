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

import json
import logging
import os
from dataclasses import dataclass

if __package__:
    from ._jsonio import atomic_write_json, read_json_or_empty
else:
    from routine._jsonio import atomic_write_json, read_json_or_empty

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# ROUTINE-12: Pfade der beiden Config-Dateien, per Env überschreibbar.
ENV_DATA_FILE = "ROUTINE_DATA_FILE"
DEFAULT_DATA_FILE = os.path.join(HERE, "routine.json")

# SVC-5 / CONFIG-5: Pfad der Abhak-Store-Datei (routine_store.json),
# per ENV überschreibbar — parallel zu ENV_DATA_FILE / DEFAULT_DATA_FILE.
# Naming-Konvention: <KOMP>_<ZWECK>_FILE → ROUTINE_STORE_FILE.
ENV_STORE_FILE = "ROUTINE_STORE_FILE"
DEFAULT_STORE_FILE = os.path.join(HERE, "routine_store.json")

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
    """Ein Routine-Punkt mit allen Feldern (ROUTINE-4, ROUTINE-24).

    quelle ∈ {default, einmalig, bedingt} — V1 füllt nur default.
    Das Modell trägt quelle von Anfang an, damit spätere Erweiterungen
    keine Datenmodell-Migration erzwingen (E-ROUTINE-2).

    ROUTINE-24 (V2): optionaler `zeit`-Sub-Block — drei Formen:
      - None / fehlt   → reiner Punkt ohne Zeit (V1-Verhalten)
      - {typ:'anker',   uhrzeit:'HH:MM', locked?:bool}
      - {typ:'vorlauf', minuten:int, bezug:'vorheriger_anker'}
    Validierung läuft in items.py vor jedem Schreib-Vorgang
    (single source: _validate_zeit_block); resolve_data liest hier nur
    den Roh-Dict ein und übergibt ihn unverändert.
    """
    id: str
    label: str
    piktogramm: str                      # numerische ARASAAC-ID als String
    quelle: str = "default"              # default | einmalig | bedingt
    piktogramm_url: str | None = None  # befüllt durch render.icon_url()
    zeit: dict | None = None             # ROUTINE-24: zeit-Sub-Block (None | anker | vorlauf)

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
        # ROUTINE-24: zeit-Sub-Block übernehmen, wenn vorhanden (None|dict).
        # Validierung der inneren Struktur passiert in items.py vor Schreib-Vorgängen
        # (single source: _validate_zeit_block); Lese-Pfad ist tolerant — Roh-Dict
        # wird durchgereicht, ungültiger Inhalt wird vom Render robust ignoriert.
        zeit = raw.get("zeit")
        if zeit is not None and not isinstance(zeit, dict):
            logger.warning(
                "items[%r].zeit hat ungültigen Typ %r — als None behandelt",
                item_id, type(zeit).__name__)
            zeit = None
        try:
            items.append(RoutineItem(
                id=item_id, label=label, piktogramm=pikto, quelle=quelle, zeit=zeit))
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


# ARASAAC-IDs der V1-Anker (ROUTINE-28 Welle B — V1-Hartcode-Cleanup).
_V1_ANKER_AUFSTEHEN_PIKTO = "8152"
_V1_ANKER_ANZIEHEN_PIKTO = "6627"
_V1_ANKER_LOSGEHEN_PIKTO = "8142"


def _v1_zeit_string(wert):
    """Liefert eine HH:MM-Repräsentation eines V1-Zeit-Werts (str oder Wochentag-Dict).

    Für Wochentag-Dict greift ein 'default'-Key, sonst der erste non-leere
    Wochentag-Eintrag, sonst None. Synth-Anker tragen Read-Only-Spiegel —
    Wochentag-Aufdröselung im items[]-Schema ist OUT-of-V2-Scope.
    """
    if isinstance(wert, str) and wert:
        return wert
    if isinstance(wert, dict):
        # Bevorzugt 'default'-Key, sonst erster non-leerer Wert
        if isinstance(wert.get("default"), str) and wert["default"]:
            return wert["default"]
        for v in wert.values():
            if isinstance(v, str) and v:
                return v
    return None


def migriere_v1_anker(cfg):
    """ROUTINE-28 Welle A: liefert eine RoutineConfig-Kopie mit Synth-End-Ankern.

    Eintrittspunkt für Display-Render und Lese-API: main.py:_current_config()
    ruft diese Funktion, bevor das Ergebnis an Render/JSON geht. Schreib-Pfad
    (items.py write_data / replace_default_items) bleibt unverändert — V1-Felder
    bleiben als Read-only-Spiegel (Welle A, ROUTINE-28).

    Idempotent: existieren bereits items mit zeit.typ=anker, locked=True →
    cfg wird unverändert zurückgegeben (kein Doppel-Synth).
    Synth-IDs 'aufstehen'/'losgehen' kollidieren mit user-IDs nur, wenn diese
    KEIN locked-Anker tragen — dann gewinnt der user-Eintrag implizit, weil
    seine ID den Synth-Eintrag in items.py vorgehen würde (Schreib-Pfad).
    """
    items_neu = _synth_v1_anker(
        cfg.items, cfg.aufstehzeit, cfg.abfahrtszeit, cfg.anzieh_vorlauf_min)
    if items_neu is cfg.items:
        return cfg
    import dataclasses
    return dataclasses.replace(cfg, items=items_neu)


def _synth_v1_anker(items, aufstehzeit_cfg, abfahrtszeit_cfg,
                     anzieh_vorlauf_min=None):
    """Erzeugt synth. End-Anker (+ Anziehen-Vorlauf-Item) aus V1-Feldern,
    wenn items[] keine eigenen locked-Anker trägt (ROUTINE-28 Welle B).

    Liefert die items-Liste (neu, falls Synth angewandt;
    sonst das Original, damit Aufrufer per Identitäts-Vergleich erkennen können).

    anzieh_vorlauf_min: int > 0 → Anziehen-Vorlauf-Item wird zwischen
    Aufstehen und Losgehen eingefügt (MAD-1: nur wenn gesetzt und > 0).
    """
    hat_locked_anker = any(
        isinstance(it.zeit, dict)
        and it.zeit.get("typ") == "anker"
        and bool(it.zeit.get("locked"))
        for it in items
    )
    if hat_locked_anker:
        return items  # Identität — Aufrufer kann erkennen: keine Mutation

    aufstehen_str = _v1_zeit_string(aufstehzeit_cfg)
    losgehen_str = _v1_zeit_string(abfahrtszeit_cfg)
    if not aufstehen_str or not losgehen_str:
        # Kein vollständiges V1-Anker-Paar → keine Synthese
        return items  # Identität

    aufstehen_item = RoutineItem(
        id="aufstehen",
        label="Aufstehen",
        piktogramm=_V1_ANKER_AUFSTEHEN_PIKTO,
        quelle="default",
        zeit={"typ": "anker", "uhrzeit": aufstehen_str, "locked": True},
    )
    losgehen_item = RoutineItem(
        id="losgehen",
        label="Losgehen",
        piktogramm=_V1_ANKER_LOSGEHEN_PIKTO,
        quelle="default",
        zeit={"typ": "anker", "uhrzeit": losgehen_str, "locked": True},
    )

    # Anziehen-Vorlauf-Item (ROUTINE-28 Welle B, MAD-1): nur wenn gesetzt.
    # bezug="naechster_anker" = Vorlauf relativ zu Losgehen
    # (V1-Anziehen-Semantik aus ROUTINE-9: `abfahrtszeit − anzieh_vorlauf_min`,
    # Nic-Setzung 2026-06-22 #1070).
    middle_items = list(items)
    if isinstance(anzieh_vorlauf_min, int) and not isinstance(anzieh_vorlauf_min, bool) \
            and anzieh_vorlauf_min > 0:
        anziehen_item = RoutineItem(
            id="anziehen",
            label="Anziehen",
            piktogramm=_V1_ANKER_ANZIEHEN_PIKTO,
            quelle="default",
            zeit={"typ": "vorlauf", "minuten": anzieh_vorlauf_min,
                  "bezug": "naechster_anker"},
        )
        middle_items = [anziehen_item, *middle_items]

    return [aufstehen_item, *middle_items, losgehen_item]


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
    aktuell = read_json_or_empty(data_path)

    # Updates mergen (normierte Form, ROUTINE-12: capitalized Wochentag-Keys)
    aktuell.update(normiert)

    # Atomar schreiben (DCOMP-4)
    atomic_write_json(data_path, aktuell)

    logger.info(
        "routine.json aktualisiert (ROUTINE-14): %s",
        ", ".join("%s=%r" % (k, v) for k, v in normiert.items()))
