"""Plan-Buddy — Konfigurations-Auflösung (PLAN-6, PLAN-10, PLAN-28, PLAN-34).

Siehe specs/buddies/plan.md §9. Slot-Definitionen und Default-Verantwort-
lichkeiten sind **Daten**, keine Code-Konstanten (E-PLAN-2): sie stehen in
einer Config-Datei, `plan/plan.example.json` dokumentiert das Format.

Auflösung der einzelnen Werte: Umgebungsvariable > Config-Datei > Default —
analog router/main.py (ROU-15) und eltern-chat/config.py (EC-15). Pflichtwerte
ohne sinnvollen Default (Google-Kalender-ID) werfen ConfigError, wenn sie
fehlen.

Die Slot-Liste ist die zentrale Datei-getriebene Struktur: jeder Slot hat
einen stabilen Schlüssel, eine Art (`verantwortlich` | `kalender-read`),
ein Icon und — bei Kalender-read-Slots — das zugehörige Kind (PLAN-6).

Der Aktivitäts-Katalog (`aktivitaeten`-Section in plan.json) ist die zweite
Datei-getriebene Struktur: jeder Eintrag hat art, label, keywords und
piktogramm (PLAN-12, PLAN-28, PLAN-34). Fehlt die Sektion, greift der
Code-Default AKTIVITAETEN_V1 aus `plan/aktivitaeten.py` (CONFIG-4).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

# PLAN-6: die zwei Slot-Arten (V1.4 — Sprint 2, neue Strings).
SLOT_VERANTWORTLICH = "verantwortlich"
SLOT_KALENDER_READ = "kalender-read"
SLOT_ARTEN = (SLOT_VERANTWORTLICH, SLOT_KALENDER_READ)

# PLAN-6 V1.4 — Slot-Art-Migrations-Lesephase: alte Strings werden mit
# WARN-Log akzeptiert; neu geschriebene Slots tragen die neuen Strings.
_LEGACY_SLOT_ART = {
    "erwachsenen-slot": SLOT_VERANTWORTLICH,
    "aktivitaets-slot": SLOT_KALENDER_READ,
}

# PLAN-6 V1.3 — ab dieser Slot-Anzahl warnt der Parser (kein ERROR): die
# Familien-1-Display-Geometrie (DC-15, 1920×1080 quer) ist nur bis 8 Slots
# vertikal lesbar getestet. WARN, weil die Familie weiterläuft — das Risiko
# ist Lesbarkeit, nicht Datenverlust.
SLOT_WARN_AB = 9

# PLAN-28: nicht-geheime Werte mit ihren Defaults. Code-Konstanten sind hier
# nur Fallback-Default — jeder Wert hat einen Override-Pfad (Config/Env).
#
# `familie_origin_url` ist die Loopback-Origin der Familie-Komponente
# (DCOMP-1): der Plan-Buddy spricht die Familie ueber HTTP an, nicht ueber
# Python-Import. Default zeigt auf den lokalen Familie-Port (PORT-2: 5010).
DEFAULTS = {
    "fenster_lesekind": 7,              # PLAN-3/PLAN-4
    "fenster_kleinkind": 3,             # PLAN-3/PLAN-4
    "wochenstart": 0,                   # 0 = Montag (PLAN-10/PLAN-28)
    "zeitzone": "Europe/Berlin",        # PLAN-28
    "db_datei": os.path.join(HERE, "plan.db"),        # PLAN-9/PLAN-28
    "kalender_id": "",                  # PLAN-15/PLAN-28 — Pflicht
    "familie_origin_url": "http://127.0.0.1:5010",    # DCOMP-1 / PORT-2
}

# PLAN-28: Umgebungsvariablen, die die Datei-Werte überschreiben (CONFIG-5:
# `PLAN_<KEY>`-Schema).
ENV_OVERRIDES = {
    "fenster_lesekind": "PLAN_FENSTER_LESEKIND",
    "fenster_kleinkind": "PLAN_FENSTER_KLEINKIND",
    "wochenstart": "PLAN_WOCHENSTART",
    "zeitzone": "PLAN_ZEITZONE",
    "db_datei": "PLAN_DB_DATEI",
    "kalender_id": "PLAN_KALENDER_ID",
    "familie_origin_url": "PLAN_FAMILIE_ORIGIN_URL",
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

    `label` ist ein optionaler Anzeige-Name (Eltern-Einstellungs-Seite,
    PLAN-6/PLAN-37); fehlt er, nutzt die Anzeige den `schluessel` als
    Fallback. Rein anzeigend — keine Datenhaltungs-Bedeutung.
    """

    def __init__(self, schluessel, art, icon, kind=None, label=None):
        self.schluessel = schluessel
        self.art = art
        self.icon = icon
        self.kind = kind
        self.label = label

    def ist_verantwortlich_slot(self):
        return self.art == SLOT_VERANTWORTLICH

    def ist_kalender_read_slot(self):
        return self.art == SLOT_KALENDER_READ

    def to_dict(self):
        d = {"schluessel": self.schluessel, "art": self.art, "icon": self.icon}
        if self.kind is not None:
            d["kind"] = self.kind
        if self.label is not None:
            d["label"] = self.label
        return d


class Aktivitaet:
    """Ein Aktivitäts-Katalog-Eintrag (PLAN-12, PLAN-28, PLAN-34).

    `art` ist der stabile Schlüssel, `label` der Anzeigetext für den Event-
    Titel (Schreib-Seite, PLAN-11), `keywords` sind die Substring-Treffer im
    Titel zur Erkennung (Lese-Seite, PLAN-12). `piktogramm` ist eine
    ARASAAC-id als String (PLAN-12 V1.1, ICONS-4/ICONS-7).
    """

    def __init__(self, art, label, keywords, piktogramm):
        self.art = art
        self.label = label
        self.keywords = keywords
        self.piktogramm = piktogramm

    def to_dict(self):
        return {
            "art": self.art,
            "label": self.label,
            "keywords": list(self.keywords),
            "piktogramm": self.piktogramm,
        }


class Config:
    """Aufgelöste Plan-Buddy-Instanz-Konfiguration (PLAN-28)."""

    def __init__(self, slots, default_verantwortlichkeiten, fenster_lesekind,
                 fenster_kleinkind, wochenstart, zeitzone, db_datei, kalender_id,
                 familie_origin_url, aktivitaeten=None):
        # PLAN-6: Slot-Liste (Reihenfolge = Rail-Reihenfolge).
        self.slots = slots
        # PLAN-10: Default-Zuweisungen je Slot-Schlüssel und Wochentag.
        # Form: { slot_schluessel: { wochentag(0-6): person_id | None } }
        self.default_verantwortlichkeiten = default_verantwortlichkeiten
        self.fenster_lesekind = fenster_lesekind
        self.fenster_kleinkind = fenster_kleinkind
        self.wochenstart = wochenstart
        self.zeitzone = zeitzone
        self.db_datei = db_datei
        self.kalender_id = kalender_id
        # DCOMP-1: Loopback-Origin der Familie-Komponente — HTTP statt Import.
        self.familie_origin_url = familie_origin_url
        # PLAN-12/PLAN-28/PLAN-34: Aktivitäts-Katalog — Liste von Aktivitaet-
        # Objekten. None bedeutet: Sektion fehlte in plan.json → CONFIG-4-
        # Fallback AKTIVITAETEN_V1 greift in aktivitaeten.py.
        self.aktivitaeten = aktivitaeten  # None | list[Aktivitaet]

    def slot(self, schluessel):
        """Slot-Definition je Schlüssel, oder None."""
        for s in self.slots:
            if s.schluessel == schluessel:
                return s
        return None

    def erwachsenen_slots(self):
        return [s for s in self.slots if s.ist_verantwortlich_slot()]

    def aktivitaets_slots(self):
        return [s for s in self.slots if s.ist_kalender_read_slot()]


def _load_file(path):
    """Lädt die Config-Datei. Fehlt sie, ist das in Ordnung — Defaults gelten.

    Fehler-Pfade (alle geben `{}` zurück, kein Absturz):
    - FileNotFoundError: plan.json noch nicht angelegt → INFO-Log, leere Config.
    - json.JSONDecodeError: Datei kaputt oder halb geschrieben (atomares
      Replace-Race, DCOMP-4) → WARNING-Log, leere Config; der Aufrufer
      (_current_config) greift auf den Last-Known-Good-Snapshot zurück
      (DCOMP-3 / E-RELOAD-1 / ROU-25), sodass kein kaputtes JSON je den
      laufenden Stand verfälscht.
    - Inhalt kein dict: format-ungültig → WARNING-Log, leere Config.
    """
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


def _migriere_slot_art(schluessel, art):
    """Slot-Art-Migrations-Lesephase (PLAN-6 V1.4 — Sprint 2).

    Ein alter Art-String (`erwachsenen-slot` → `verantwortlich`,
    `aktivitaets-slot` → `kalender-read`) wird mit WARN-Log auf den neuen
    String übersetzt; neue Strings werden unverändert durchgereicht. So
    akzeptiert der Parser bestehende plan.json-Dateien ohne Deploy-Block —
    die Lesephase ist Übergangs-Kompatibilität, neu geschriebene Slots sollen
    die neuen Strings tragen.
    """
    if art in _LEGACY_SLOT_ART:
        neu = _LEGACY_SLOT_ART[art]
        logger.warning(
            "Slot %r: alter Art-String %r → %r (Slot-Art-Migrations-Lesephase, "
            "PLAN-6 V1.4) — neu geschriebene Slots sollten den neuen String tragen",
            schluessel, art, neu)
        return neu
    return art


def _parse_slots(raw_slots):
    """Baut Slot-Objekte aus dem `slots`-Abschnitt der Config (PLAN-6).

    Wirft ConfigError, wenn ein Slot ein Pflichtfeld vermisst, eine
    unbekannte Art trägt oder ein Kalender-read-Slot kein Kind benennt.

    Ab `SLOT_WARN_AB` Slots schreibt der Parser einen WARN-Log (kein ERROR —
    die Familie läuft weiter, das Risiko ist Lesbarkeit, nicht Datenverlust).

    PLAN-6 V1.4: alte Slot-Art-Strings werden über die Slot-Art-Migrations-
    Lesephase (`_migriere_slot_art`) auf die neuen Strings übersetzt (WARN).
    """
    slots = []
    seen = set()
    for raw in raw_slots:
        if not isinstance(raw, dict):
            raise ConfigError("Slot-Eintrag ist kein Objekt: %r" % (raw,))
        for feld in ("schluessel", "art", "icon"):
            if not raw.get(feld):
                raise ConfigError("Slot ohne Pflichtfeld %r: %r" % (feld, raw))
        art = _migriere_slot_art(raw["schluessel"], raw["art"])
        if art not in SLOT_ARTEN:
            raise ConfigError(
                "Slot %r: Art %r unbekannt (erlaubt: %s)"
                % (raw["schluessel"], art, ", ".join(SLOT_ARTEN)))
        kind = raw.get("kind")
        if art == SLOT_KALENDER_READ and not kind:
            raise ConfigError(
                "Kalender-read-Slot %r braucht ein `kind` (PLAN-6)" % raw["schluessel"])
        # PLAN-6/PLAN-37: optionaler Anzeige-Name. Fehlt/None erlaubt; wenn
        # vorhanden, muss er ein String sein (keine weitere Validierung).
        label = raw.get("label")
        if label is not None and not isinstance(label, str):
            raise ConfigError(
                "Slot %r: label muss ein String sein, gefunden: %r"
                % (raw["schluessel"], label))
        if raw["schluessel"] in seen:
            raise ConfigError("doppelter Slot-Schlüssel %r" % raw["schluessel"])
        seen.add(raw["schluessel"])
        icon = raw["icon"]
        slots.append(Slot(raw["schluessel"], art, icon, kind, label))
    # PLAN-6 V1.3: WARN ab 9 Slots — Display-Geometrie nur bis 8 getestet.
    if len(slots) >= SLOT_WARN_AB:
        logger.warning(
            "Plan-Buddy: %d Slots konfiguriert (>= %d) — die Display-Geometrie "
            "(DC-15, 1920×1080 quer) ist nur bis 8 Slots vertikal lesbar getestet "
            "(PLAN-6 V1.3). Kein Fehler, aber die Schedule-Rail kann überlaufen.",
            len(slots), SLOT_WARN_AB)
    return slots


def _parse_aktivitaeten(raw_aktivitaeten):
    """Baut Aktivitaet-Objekte aus dem `aktivitaeten`-Abschnitt der Config (PLAN-12).

    Wirft ConfigError, wenn ein Eintrag ein Pflichtfeld vermisst, einen leeren
    Wert trägt oder `keywords` keine nicht-leere Liste nicht-leerer Strings ist.
    Doppelte `art`-Schlüssel sind ein Fehler (analog doppelter Slot-Schlüssel).
    """
    aktivitaeten = []
    seen = set()
    for raw in raw_aktivitaeten:
        if not isinstance(raw, dict):
            raise ConfigError(
                "aktivitaeten-Eintrag ist kein Objekt: %r" % (raw,))
        for feld in ("art", "label", "piktogramm"):
            if not raw.get(feld):
                raise ConfigError(
                    "aktivitaeten-Eintrag ohne Pflichtfeld %r: %r" % (feld, raw))
        art = raw["art"]
        if art in seen:
            raise ConfigError("doppelter aktivitaeten-Schlüssel %r" % art)
        seen.add(art)
        keywords = raw.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ConfigError(
                "aktivitaeten-Eintrag %r: keywords muss eine nicht-leere Liste sein"
                % art)
        for kw in keywords:
            if not isinstance(kw, str) or not kw:
                raise ConfigError(
                    "aktivitaeten-Eintrag %r: jedes keyword muss ein nicht-leerer "
                    "String sein, gefunden: %r" % (art, kw))
        aktivitaeten.append(Aktivitaet(art, raw["label"], keywords, raw["piktogramm"]))
    return aktivitaeten


def _parse_defaults(raw_defaults, slots):
    """Baut die Default-Verantwortlichkeiten aus der Config (PLAN-10).

    Erwartet `{ slot_schluessel: [p0, p1, p2, p3, p4, p5, p6] }` — eine
    Personen-`id` (oder null) je Wochentag (0=Mo … 6=So). Kürzere Listen
    werden mit None aufgefüllt. Defaults sind leer, wenn der Abschnitt fehlt
    (PLAN-28). Nur Erwachsenen-Slots können Defaults tragen.
    """
    erwachsenen_keys = {s.schluessel for s in slots if s.ist_verantwortlich_slot()}
    out = {}
    for slot_key, by_day in (raw_defaults or {}).items():
        if slot_key not in erwachsenen_keys:
            raise ConfigError(
                "Default-Verantwortlichkeit für unbekannten/Nicht-Erwachsenen-Slot %r"
                % slot_key)
        if not isinstance(by_day, list):
            raise ConfigError("Default-Verantwortlichkeit %r ist keine Liste" % slot_key)
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
    defaults = _parse_defaults(file_cfg.get("default_verantwortlichkeiten") or {}, slots)
    # PLAN-12/PLAN-28: Aktivitäts-Katalog — Datei oder None (→ CONFIG-4-Fallback
    # AKTIVITAETEN_V1 in aktivitaeten.py; None signalisiert: Sektion fehlt).
    raw_akt = file_cfg.get("aktivitaeten")
    aktivitaeten = _parse_aktivitaeten(raw_akt) if raw_akt is not None else None

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

    familie_origin_url = str(values["familie_origin_url"]).strip().rstrip("/")

    return Config(
        slots=slots,
        default_verantwortlichkeiten=defaults,
        fenster_lesekind=fenster_lesekind,
        fenster_kleinkind=fenster_kleinkind,
        wochenstart=wochenstart,
        zeitzone=str(values["zeitzone"]).strip(),
        db_datei=str(values["db_datei"]),
        kalender_id=kalender_id,
        familie_origin_url=familie_origin_url,
        aktivitaeten=aktivitaeten,
    )
