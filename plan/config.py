"""Plan-Buddy — Konfigurations-Auflösung (PLAN-6, PLAN-10, PLAN-28).

Siehe specs/buddies/plan.md §9. Slot-Definitionen und Default-Petrantwort-
lichkeiten sind **Daten**, keine Code-Konstanten (E-PLAN-2): sie stehen in
einer Config-Datei, `plan/plan.example.json` dokumentiert das Format.

Auflösung der einzelnen Werte: Umgebungsvariable > Config-Datei > Default —
analog router/main.py (ROU-15) und eltern-chat/config.py (EC-15). Pflichtwerte
ohne sinnvollen Default (Google-Kalender-ID) werfen ConfigError, wenn sie
fehlen.

Die Slot-Liste ist die zentrale Datei-getriebene Struktur: jeder Slot hat
einen stabilen Schlüssel, eine Art (`erwachsenen-slot` | `aktivitaets-slot`),
ein Icon und — bei Aktivitäts-Slots — das zugehörige Kind (PLAN-6).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# PLAN-6: die zwei Slot-Arten.
SLOT_ERWACHSENEN = "erwachsenen-slot"
SLOT_AKTIVITAET = "aktivitaets-slot"
SLOT_ARTEN = (SLOT_ERWACHSENEN, SLOT_AKTIVITAET)

# PLAN-28: nicht-geheime Werte mit ihren Defaults. Code-Konstanten sind hier
# nur Fallback-Default — jeder Wert hat einen Override-Pfad (Config/Env).
DEFAULTS = {
    "fenster_lesekind": 7,              # PLAN-3/PLAN-4
    "fenster_kleinkind": 3,             # PLAN-3/PLAN-4
    "wochenstart": 0,                   # 0 = Montag (PLAN-10/PLAN-28)
    "zeitzone": "Europe/Berlin",        # PLAN-28
    "db_datei": os.path.join(HERE, "plan.db"),        # PLAN-9/PLAN-28
    "kalender_id": "",                  # PLAN-15/PLAN-28 — Pflicht
}

# PLAN-28: Umgebungsvariablen, die die Datei-Werte überschreiben.
ENV_OVERRIDES = {
    "fenster_lesekind": "PLAN_FENSTER_LESEKIND",
    "fenster_kleinkind": "PLAN_FENSTER_KLEINKIND",
    "wochenstart": "PLAN_WOCHENSTART",
    "zeitzone": "PLAN_ZEITZONE",
    "db_datei": "PLAN_DB_DATEI",
    "kalender_id": "PLAN_KALENDER_ID",
}

# PLAN-28: Pfad der Config-Datei selbst — per Env überschreibbar.
ENV_CONFIG_FILE = "PLAN_CONFIG_FILE"
DEFAULT_CONFIG_FILE = os.path.join(HERE, "plan.json")


class ConfigError(Exception):
    """Eine Pflicht-Konfiguration fehlt oder ist ungültig (PLAN-28)."""


class Slot:
    """Eine Slot-Definition aus der Config (PLAN-6).

    `schluessel` ist stabil und identifiziert den Slot in der Datenhaltung
    (PLAN-9) und in der View. `art` ist eine der SLOT_ARTEN. `icon` benennt
    das Rail-Icon. `kind` ist die Personen-`id` des zugehörigen Kindes:
    Pflicht für Aktivitäts-Slots (PLAN-6); bei Erwachsenen-Slots optional —
    ein bett-bringt-Slot etwa zeigt das Kind im Rail, weist aber einem
    Erwachsenen zu (Wireframe-Handoff `bed1`/`bed2`).
    """

    def __init__(self, schluessel, art, icon, kind=None):
        self.schluessel = schluessel
        self.art = art
        self.icon = icon
        self.kind = kind

    def ist_erwachsenen_slot(self):
        return self.art == SLOT_ERWACHSENEN

    def ist_aktivitaets_slot(self):
        return self.art == SLOT_AKTIVITAET

    def to_dict(self):
        d = {"schluessel": self.schluessel, "art": self.art, "icon": self.icon}
        if self.kind is not None:
            d["kind"] = self.kind
        return d


class Config:
    """Aufgelöste Plan-Buddy-Instanz-Konfiguration (PLAN-28)."""

    def __init__(self, slots, default_petrantwortlichkeiten, fenster_lesekind,
                 fenster_kleinkind, wochenstart, zeitzone, db_datei, kalender_id):
        # PLAN-6: Slot-Liste (Reihenfolge = Rail-Reihenfolge).
        self.slots = slots
        # PLAN-10: Default-Zuweisungen je Slot-Schlüssel und Wochentag.
        # Form: { slot_schluessel: { wochentag(0-6): person_id | None } }
        self.default_petrantwortlichkeiten = default_petrantwortlichkeiten
        self.fenster_lesekind = fenster_lesekind
        self.fenster_kleinkind = fenster_kleinkind
        self.wochenstart = wochenstart
        self.zeitzone = zeitzone
        self.db_datei = db_datei
        self.kalender_id = kalender_id

    def slot(self, schluessel):
        """Slot-Definition je Schlüssel, oder None."""
        for s in self.slots:
            if s.schluessel == schluessel:
                return s
        return None

    def erwachsenen_slots(self):
        return [s for s in self.slots if s.ist_erwachsenen_slot()]

    def aktivitaets_slots(self):
        return [s for s in self.slots if s.ist_aktivitaets_slot()]


def _load_file(path):
    """Lädt die Config-Datei. Fehlt sie, ist das in Ordnung — Defaults gelten."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.info("plan.json nicht gefunden (%s) — Defaults gelten", path)
        return {}
    except json.JSONDecodeError as e:
        logger.warning("plan.json nicht parsebar (%s): %s — Defaults bleiben", path, e)
        return {}
    if not isinstance(data, dict):
        logger.warning("plan.json hat kein Objekt als Inhalt (%s) — Defaults bleiben", path)
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _parse_slots(raw_slots):
    """Baut Slot-Objekte aus dem `slots`-Abschnitt der Config (PLAN-6).

    Wirft ConfigError, wenn ein Slot ein Pflichtfeld vermisst, eine
    unbekannte Art trägt oder ein Aktivitäts-Slot kein Kind benennt.
    """
    slots = []
    seen = set()
    for raw in raw_slots:
        if not isinstance(raw, dict):
            raise ConfigError("Slot-Eintrag ist kein Objekt: %r" % (raw,))
        for feld in ("schluessel", "art", "icon"):
            if not raw.get(feld):
                raise ConfigError("Slot ohne Pflichtfeld %r: %r" % (feld, raw))
        art = raw["art"]
        if art not in SLOT_ARTEN:
            raise ConfigError(
                "Slot %r: Art %r unbekannt (erlaubt: %s)"
                % (raw["schluessel"], art, ", ".join(SLOT_ARTEN)))
        kind = raw.get("kind")
        if art == SLOT_AKTIVITAET and not kind:
            raise ConfigError(
                "Aktivitäts-Slot %r braucht ein `kind` (PLAN-6)" % raw["schluessel"])
        if raw["schluessel"] in seen:
            raise ConfigError("doppelter Slot-Schlüssel %r" % raw["schluessel"])
        seen.add(raw["schluessel"])
        slots.append(Slot(raw["schluessel"], art, raw["icon"], kind))
    return slots


def _parse_defaults(raw_defaults, slots):
    """Baut die Default-Petrantwortlichkeiten aus der Config (PLAN-10).

    Erwartet `{ slot_schluessel: [p0, p1, p2, p3, p4, p5, p6] }` — eine
    Personen-`id` (oder null) je Wochentag (0=Mo … 6=So). Kürzere Listen
    werden mit None aufgefüllt. Defaults sind leer, wenn der Abschnitt fehlt
    (PLAN-28). Nur Erwachsenen-Slots können Defaults tragen.
    """
    erwachsenen_keys = {s.schluessel for s in slots if s.ist_erwachsenen_slot()}
    out = {}
    for slot_key, by_day in (raw_defaults or {}).items():
        if slot_key not in erwachsenen_keys:
            raise ConfigError(
                "Default-Petrantwortlichkeit für unbekannten/Nicht-Erwachsenen-Slot %r"
                % slot_key)
        if not isinstance(by_day, list):
            raise ConfigError("Default-Petrantwortlichkeit %r ist keine Liste" % slot_key)
        tage = {}
        for wd in range(7):
            tage[wd] = by_day[wd] if wd < len(by_day) else None
        out[slot_key] = tage
    return out


def resolve(config_path=None, env=None):
    """Löst die Plan-Buddy-Konfiguration nach PLAN-28 auf.

    `config_path` ist der Pfad der Config-Datei (Default: $PLAN_CONFIG_FILE oder
    `plan/plan.json`). `env` ist überschreibbar (Tests). Wirft ConfigError,
    wenn ein Pflichtwert fehlt oder eine Slot-/Default-Definition ungültig ist.
    """
    if env is None:
        env = os.environ
    if config_path is None:
        config_path = env.get(ENV_CONFIG_FILE) or DEFAULT_CONFIG_FILE

    file_cfg = _load_file(config_path)

    # PLAN-6: Slots — Datei oder leer.
    slots = _parse_slots(file_cfg.get("slots") or [])
    # PLAN-10: Defaults — Datei oder leer.
    defaults = _parse_defaults(file_cfg.get("default_petrantwortlichkeiten") or {}, slots)

    # PLAN-28: Skalar-Werte, Env > Datei > Default.
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in file_cfg:
            values[key] = file_cfg[key]
        env_name = ENV_OVERRIDES[key]
        if env_name in env:
            values[key] = env[env_name]

    try:
        fenster_lesekind = int(values["fenster_lesekind"])
        fenster_kleinkind = int(values["fenster_kleinkind"])
        wochenstart = int(values["wochenstart"])
    except (TypeError, ValueError) as e:
        raise ConfigError("Fenster-/Wochenstart-Wert ist keine Ganzzahl: %s" % e)
    if fenster_lesekind < 1 or fenster_kleinkind < 1:
        raise ConfigError("Fenster-Größen müssen >= 1 sein")
    if not (0 <= wochenstart <= 6):
        raise ConfigError("wochenstart muss 0..6 sein (0=Montag), ist %d" % wochenstart)

    # PLAN-28: Google-Kalender-ID ist Pflicht, kein Default.
    kalender_id = str(values["kalender_id"]).strip()
    if not kalender_id:
        raise ConfigError(
            "kalender_id ist nicht gesetzt (Pflicht, PLAN-28) — "
            "Config-Feld `kalender_id` oder $%s" % ENV_OVERRIDES["kalender_id"])

    return Config(
        slots=slots,
        default_petrantwortlichkeiten=defaults,
        fenster_lesekind=fenster_lesekind,
        fenster_kleinkind=fenster_kleinkind,
        wochenstart=wochenstart,
        zeitzone=str(values["zeitzone"]).strip(),
        db_datei=str(values["db_datei"]),
        kalender_id=kalender_id,
    )
