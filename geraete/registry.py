"""Geräte-Registry — Geräte-Modell + Datenhaltung.

Siehe specs/platform/geraete.md (Refs #105). Dieses Modul besitzt die Geräte-
Daten der Familie (GER-1) und stellt sie über eine Schnittstelle bereit
(GER-5, GER-6). Es lädt sie aus einer Per-Instanz-Datei (GER-4) und schreibt
sie race-frei zurück (GER-6) — Dateirechte 0600.

Die Geräte sind Daten, nicht Code (CLAUDE.md §6): dieses Modul enthält keine
hartkodierte Geräte-Liste, nur das Laden, das atomare Schreiben, das Modell
und die Schnittstelle.
"""

import json
import logging
import os
import re
import stat
import tempfile


# GER-2: endliche Liste der Geräte-Typen V1. Ein weiterer Typ ist eine
# Spec-Änderung, kein Config-Wert.
TYPEN = ("tablet", "handy", "monitor", "pi-display")

# GER-3 (`verwendung`): wofür wird das Gerät genutzt.
VERWENDUNGEN = ("display", "controller", "beides")

# GER-3 (`os`): Betriebssystem-Familie. `unbekannt` ist ausdrücklich Teil
# der Menge — die Registry darf das Feld auch tragen, wenn das OS bei der
# Anlage noch nicht feststeht.
OS_WERTE = ("android", "ios", "windows", "macos", "linux", "unbekannt")

# GER-3 (`status`): Soll-Zustand. V1 manuell gesetzt (OPEN-GER-B).
STATUS_WERTE = ("aktiv", "inaktiv")

# GER-4: Dateirechte auf den Eigentümer beschränkt — analog ZD-3 / ONB-5.
FILE_MODE = 0o600

# GER-7: Schema-Regex für die `display_id` — `<typ>-<slug>-<nn>` mit slug
# kleingeschrieben, Bindestrich-getrennt, ohne Sonderzeichen.
_ID_RE = re.compile(
    r"^(?P<typ>tablet|handy|monitor|pi-display)"
    r"-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)"
    r"-(?P<nr>\d{2})$")

# Umlauttabelle für `slugify` (GER-7): name-slug ohne Umlaute.
_UMLAUT_MAP = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})


class RegistryError(Exception):
    """Die Registry-Datei ist inhaltlich ungültig (z. B. unbekannter Typ)
    ODER der Schreib-Aufruf ist fehlgeschlagen (GER-6)."""


class Geraet:
    """Ein Gerät der Familien-Registry (GER-3).

    Pflichtfelder: `id`, `typ`, `name`, `aufloesung`, `os`, `verwendung`,
    `status`. Es gibt V1 keine optionalen Felder — alle GER-3-Felder sind
    Pflicht. Konsumenten lesen nur über `to_dict()`, nicht über interne
    Attribute (CLAUDE.md §6 einseitige Abhängigkeiten).
    """

    def __init__(self, id, typ, name, aufloesung, os, verwendung, status):
        self.id = id
        self.typ = typ
        self.name = name
        self.aufloesung = aufloesung  # {"w": int, "h": int}
        self.os = os
        self.verwendung = verwendung
        self.status = status

    def is_aktiv(self):
        return self.status == "aktiv"

    def to_dict(self):
        """Geräte-Daten für die Schnittstelle (GER-5) und die Datei (GER-6).

        Bewusst stabile Feld-Reihenfolge, damit save() byte-stabile Diffs
        produziert (FAM-11-Analogie).
        """
        return {
            "id": self.id,
            "typ": self.typ,
            "name": self.name,
            "aufloesung": {"w": self.aufloesung["w"], "h": self.aufloesung["h"]},
            "os": self.os,
            "verwendung": self.verwendung,
            "status": self.status,
        }


class Registry:
    """Die geladene Geräte-Registry — eine Instanz, eine Familie (GER-1).

    Hält die Geräte in-memory und stellt die Lese-Schnittstelle bereit:
    ein Gerät je `id`, alle Geräte listen, nach `verwendung` filtern
    (GER-5). Schreiben (GER-6) läuft über `add`, `update`, `deactivate`
    plus die freie save()-Funktion.
    """

    def __init__(self, geraete=None):
        # id -> Geraet; dict bewahrt die Datei-Reihenfolge.
        self._by_id = {}
        for g in (geraete or []):
            self._by_id[g.id] = g

    # -- Lese-Schnittstelle (GER-5) ---------------------------------------

    def get(self, geraet_id):
        """Ein Gerät je `id` (GER-5). Unbekannte `id`: None."""
        return self._by_id.get(geraet_id)

    def list_all(self):
        """Alle Geräte der Familie (GER-5) — Datei-Reihenfolge.

        Liefert aktive UND inaktive Geräte: Konsumenten, die nur die aktiven
        wollen, filtern selbst über `g.is_aktiv()`. `status` ist Soll-Zustand
        des Konsumenten (GER-3), nicht der Registry — sie hält beide vor.
        """
        return list(self._by_id.values())

    def list_by_verwendung(self, verwendung):
        """Geräte gefiltert nach `verwendung` (GER-5).

        `verwendung` ist einer aus `display`/`controller`/`beides`. Ein
        Gerät mit `verwendung="beides"` taucht sowohl im `display`- als auch
        im `controller`-Filter auf — sonst müssten Konsumenten zwei Listen
        zusammenmischen.
        """
        if verwendung not in VERWENDUNGEN:
            raise ValueError(
                "verwendung %r nicht in %r (GER-3)" % (verwendung, list(VERWENDUNGEN)))
        if verwendung == "beides":
            return [g for g in self._by_id.values() if g.verwendung == "beides"]
        return [g for g in self._by_id.values()
                if g.verwendung == verwendung or g.verwendung == "beides"]

    # -- Schreib-Schnittstelle (GER-6) ------------------------------------

    def add(self, geraet):
        """Ergänzt ein Gerät in der In-Memory-Registry (GER-6-Helfer).

        Wirft RegistryError, wenn die `id` bereits vergeben ist (GER-7:
        einmal vergebene `id` wird nicht neu vergeben). Wer kollisionsfrei
        anlegen will, ruft vorher `neue_id(...)` auf.
        """
        if geraet.id in self._by_id:
            raise RegistryError(
                "Gerät mit id %r existiert bereits (GER-7)" % geraet.id)
        self._by_id[geraet.id] = geraet

    def update(self, geraet_id, **felder):
        """Ändert Felder eines bestehenden Geräts (GER-6).

        Erlaubt alle GER-3-Felder außer `id` (stabil, GER-7). Unbekannte
        Felder oder Werte außerhalb der Mengen werfen RegistryError, bevor
        die Registry mutiert wird. Liefert das geänderte Gerät zurück.
        """
        g = self._by_id.get(geraet_id)
        if g is None:
            raise RegistryError("unbekannte Geräte-id %r" % geraet_id)
        if "id" in felder:
            raise RegistryError(
                "Geräte-id ist stabil und kann nicht geändert werden (GER-7)")
        # Eine Kopie aus dem aktuellen Stand bauen, validieren, dann committen —
        # bei einem Validierungsfehler bleibt das Original unberührt.
        neu = dict(g.to_dict())
        neu.update(felder)
        validated = _validate_dict(neu)
        self._by_id[geraet_id] = validated
        return validated

    def deactivate(self, geraet_id):
        """Setzt `status` auf `inaktiv` (GER-6). Convenience für update()."""
        return self.update(geraet_id, status="inaktiv")


# ============================================================
#  Slug- und ID-Vergabe (GER-7)
# ============================================================

def slugify(name):
    """Erzeugt einen GER-7-konformen `name-slug` aus einem freien Namen.

    Kleinbuchstaben, Bindestrich-getrennt, keine Umlaute, keine
    Sonderzeichen. Mehrfach-Trenner werden zusammengefasst, führende/
    abschließende Bindestriche entfernt. Ein leerer Eingabewert wirft
    ValueError — ohne Slug keine `display_id`.
    """
    if not isinstance(name, str):
        raise ValueError("name muss ein String sein")
    s = name.translate(_UMLAUT_MAP).lower()
    # Alles, was nicht a-z 0-9 ist, zu Bindestrich machen.
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if not s:
        raise ValueError("Name %r liefert leeren Slug" % name)
    return s


def neue_id(registry, typ, name):
    """Vergibt kollisionsfrei eine neue `display_id` nach GER-7.

    Schema: `<typ>-<slug(name)>-<nn>` mit `<nn>` als nullgepolsterter,
    zweistelliger Folgenummer, die je (`<typ>-<slug>`)-Kombination bei `01`
    beginnt und auf den nächsten in der Registry freien Wert gesetzt wird.
    Bestehende `id`s werden nie neu vergeben (GER-7), auch nicht solche
    inaktiver Geräte — die Identität bleibt stabil.
    """
    if typ not in TYPEN:
        raise ValueError("typ %r nicht in %r (GER-2)" % (typ, list(TYPEN)))
    slug = slugify(name)
    praefix = "%s-%s-" % (typ, slug)
    belegt = set()
    for g in registry.list_all():
        m = _ID_RE.match(g.id)
        if m and m.group("typ") == typ and m.group("slug") == slug:
            belegt.add(int(m.group("nr")))
    # Beginne bei 01; suche den nächsten freien Wert.
    nr = 1
    while nr in belegt:
        nr += 1
    if nr > 99:
        # Pragmatisch: 99 Geräte je (Typ+Slug)-Kombination je Familie sind
        # weit jenseits jedes realistischen Falls. Ein Überlauf wäre ein
        # Datenfehler, nicht ein Schema-Fehler.
        raise RegistryError(
            "kein freier `nn` mehr für Präfix %r (GER-7)" % praefix)
    return "%s%02d" % (praefix, nr)


# ============================================================
#  Validierung & Parsen
# ============================================================

def _require(raw, feld):
    if feld not in raw or raw[feld] in (None, ""):
        raise RegistryError("Gerät ohne Pflichtfeld %r: %r" % (feld, raw))


def _validate_aufloesung(raw_aufloesung, geraet_id):
    if not isinstance(raw_aufloesung, dict):
        raise RegistryError(
            "Gerät %r: aufloesung muss {w,h} sein, ist %r"
            % (geraet_id, raw_aufloesung))
    for achse in ("w", "h"):
        wert = raw_aufloesung.get(achse)
        if not isinstance(wert, int) or wert <= 0:
            raise RegistryError(
                "Gerät %r: aufloesung.%s muss positive Ganzzahl sein, ist %r"
                % (geraet_id, achse, wert))
    return {"w": raw_aufloesung["w"], "h": raw_aufloesung["h"]}


def _validate_dict(raw):
    """Baut ein Geraet aus Rohdaten und validiert alle GER-3-Felder.

    Wirft RegistryError, wenn ein Feld fehlt oder ein Wert außerhalb der
    Menge liegt. Wird sowohl beim Laden der Datei als auch beim
    `update`-Aufruf benutzt — eine Stelle, die die Validierung kennt.
    """
    for feld in ("id", "typ", "name", "aufloesung", "os", "verwendung", "status"):
        _require(raw, feld)
    geraet_id = raw["id"]
    if not _ID_RE.match(geraet_id):
        raise RegistryError(
            "Gerät %r: id-Schema verletzt (GER-7 erwartet `<typ>-<slug>-<nn>`)"
            % geraet_id)
    if raw["typ"] not in TYPEN:
        raise RegistryError(
            "Gerät %r: typ %r nicht in %r (GER-2)"
            % (geraet_id, raw["typ"], list(TYPEN)))
    # Konsistenz id-Präfix vs. typ-Feld — sonst kann die `id` lügen.
    m = _ID_RE.match(geraet_id)
    if m.group("typ") != raw["typ"]:
        raise RegistryError(
            "Gerät %r: id-Präfix %r passt nicht zum typ %r (GER-7)"
            % (geraet_id, m.group("typ"), raw["typ"]))
    if raw["os"] not in OS_WERTE:
        raise RegistryError(
            "Gerät %r: os %r nicht in %r (GER-3)"
            % (geraet_id, raw["os"], list(OS_WERTE)))
    if raw["verwendung"] not in VERWENDUNGEN:
        raise RegistryError(
            "Gerät %r: verwendung %r nicht in %r (GER-3)"
            % (geraet_id, raw["verwendung"], list(VERWENDUNGEN)))
    if raw["status"] not in STATUS_WERTE:
        raise RegistryError(
            "Gerät %r: status %r nicht in %r (GER-3)"
            % (geraet_id, raw["status"], list(STATUS_WERTE)))
    aufloesung = _validate_aufloesung(raw["aufloesung"], geraet_id)
    return Geraet(
        id=geraet_id,
        typ=raw["typ"],
        name=raw["name"],
        aufloesung=aufloesung,
        os=raw["os"],
        verwendung=raw["verwendung"],
        status=raw["status"],
    )


# ============================================================
#  Laden & Schreiben (GER-4, GER-6)
# ============================================================

def load(path):
    """Lädt die Registry-Datei (GER-4).

    Fehlt die Datei oder ist sie nicht parsebar, protokolliert das System EINE
    Warnung und liefert eine leere Registry — kein Crash (GER-4, symmetrisch
    zu FAM-6/ROU-18). Inhaltlich ungültige Daten (fehlendes Pflichtfeld,
    unbekannter Typ, kollidierende ids) sind dagegen ein echter Fehler und
    werfen RegistryError — die Datei ist Daten, falsche Daten sind ein
    Datei-Fehler, kein stiller Default.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.warning(
            "geraete.json nicht gefunden: %s — starte mit leerer Geräte-Liste",
            path)
        return Registry()
    except json.JSONDecodeError as e:
        logging.warning(
            "geraete.json nicht parsebar (%s): %s — starte mit leerer Geräte-Liste",
            path, e)
        return Registry()

    raw_geraete = data.get("geraete") if isinstance(data, dict) else None
    if raw_geraete is None:
        raw_geraete = []
    if not isinstance(raw_geraete, list):
        raise RegistryError(
            "geraete.json: `geraete` muss eine Liste sein, ist %r" % type(raw_geraete))

    geraete = []
    seen = set()
    for raw in raw_geraete:
        if not isinstance(raw, dict):
            raise RegistryError("geraete.json: Eintrag ist kein Objekt: %r" % raw)
        g = _validate_dict(raw)
        if g.id in seen:
            raise RegistryError("doppelte id %r in der Registry-Datei (GER-7)" % g.id)
        seen.add(g.id)
        geraete.append(g)

    logging.info("geraete geladen: %d (aktiv: %d)",
                 len(geraete), sum(1 for g in geraete if g.is_aktiv()))
    return Registry(geraete)


def save(registry, path):
    """Schreibt die Registry atomar mit 0600-Rechten in die Datei (GER-6).

    Pattern (Mix aus FAM-11 atomarem Rename + ONB-5 race-freier 0600-Anlage):
    schreibt zuerst in eine Temp-Datei im Zielverzeichnis (damit `os.replace`
    ein Filesystem-internes atomares Rename ist), öffnet diese Temp-Datei mit
    `os.open(..., O_CREAT|O_WRONLY|O_EXCL, 0o600)` — der Inhalt liegt zu
    keinem Zeitpunkt mit offeneren Rechten auf der Platte, auch nicht bei
    restriktivem umask-Default. Bei einem Fehlschlag wird die Temp-Datei
    aufgeräumt und ein `RegistryError` geworfen — die alte Datei bleibt
    unverändert, kein verwaistes Temp im Zielverzeichnis.

    Bestehende Geräte bleiben byte-gleich, solange der Aufrufer sie nicht
    explizit ändert (GER-6): die Datei-Reihenfolge wird aus der Registry
    übernommen, Felder werden in `Geraet.to_dict()` stabil sortiert.
    """
    payload = {"geraete": [g.to_dict() for g in registry.list_all()]}

    target_dir = os.path.dirname(os.path.abspath(path))
    if target_dir and not os.path.isdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    # Temp-Datei im Zielverzeichnis → os.replace ist In-Filesystem atomar.
    # `tempfile.mkstemp` ohne `mode`-Argument liefert 0600 im POSIX-Default —
    # wir setzen den Modus zusätzlich explizit via os.chmod, damit ein
    # eventuell anderer Default (Windows, exotisches FS) nicht zu offeneren
    # Rechten führt. Den ersten FD von mkstemp schließen wir gleich wieder
    # und öffnen die Temp-Datei kontrolliert mit os.open(..., FILE_MODE) —
    # so haben wir EINE Stelle, die das 0600-Flag setzt.
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".geraete.", suffix=".json.tmp", dir=target_dir)
    os.close(tmp_fd)
    try:
        # Atomarer 0600-Reopen: O_TRUNC, damit der mkstemp-Inhalt (leer)
        # weg ist; O_CREAT ist redundant, schadet aber nicht.
        fd = os.open(tmp_path, os.O_WRONLY | os.O_TRUNC, FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=False)
            f.write("\n")
        # Defense-in-depth: Modus erzwingen, falls die Temp-Datei bereits
        # mit offeneren Rechten existierte.
        os.chmod(tmp_path, FILE_MODE)
        os.replace(tmp_path, path)
    except OSError as e:
        # Aufräumen: Temp darf nicht zurückbleiben.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise RegistryError("geraete.json konnte nicht geschrieben werden: %s" % e)

    # Bestehende Zieldatei kann offenere Rechte gehabt haben — auch wenn
    # os.replace die Inode der Temp-Datei mit ihren 0600-Rechten übernimmt,
    # erzwingen wir den Modus ein letztes Mal: defense-in-depth gegen
    # exotische Filesysteme.
    os.chmod(path, FILE_MODE)


def is_owner_only(path):
    """True, wenn `path` die Dateirechte aus GER-4 (0600) trägt.

    Hilfsfunktion für Diagnose und Tests — analog `zugangsdaten.is_owner_only`.
    """
    mode = stat.S_IMODE(os.stat(path).st_mode)
    return mode == FILE_MODE
