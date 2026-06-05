"""Panel-Registry — Panel-Modell + Datenhaltung.

Siehe specs/platform/panel-registry.md (Refs #58). Dieses Modul besitzt die
App-Panel-Instanzen einer Familie (PREG-1) und stellt sie über eine
Schnittstelle bereit (PREG-13/14/15). Es lädt sie aus einer Per-Instanz-Datei
(PREG-4) und schreibt sie race-frei zurück (PREG-15) — Dateirechte 0600.

Die Panel-Instanzen sind Daten, nicht Code (CLAUDE.md §6): dieses Modul enthält
keine hartkodierte Panel-Liste, nur das Laden, das atomare Schreiben, das
Modell und die Schnittstelle. Schwester-Modell der Geräte-Registry
(geraete/registry.py, GER) — gleiche Lock-/Atomar-/LKG-Muster, eigene Daten.
"""

import json
import logging
import os
import re
import stat
import tempfile

# PREG-4: Dateirechte auf den Eigentümer beschränkt — analog GER-4 / ZD-3.
FILE_MODE = 0o600

# PREG-6: Schema-Regex für die `panel_id` — `<slug>-<nn>` mit slug
# kleingeschrieben, Bindestrich-getrennt, ohne Sonderzeichen (IDENT-1).
# Anders als GER-7 hat die `panel_id` KEIN `<typ>`-Präfix — sie ist ein
# freier Slug plus zweistellige Folgenummer.
_ID_RE = re.compile(
    r"^(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<nr>\d{2})$")

# Umlauttabelle für `slugify` (PREG-6): slug ohne Umlaute.
_UMLAUT_MAP = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})

# PREG-3: Präfix der `source_id` — `app-panel:<panel_id>` (PANEL-6).
SOURCE_ID_PREFIX = "app-panel:"


class RegistryError(Exception):
    """Die Registry-Datei ist inhaltlich ungültig (z. B. fehlendes
    Pflichtfeld) ODER der Schreib-Aufruf ist fehlgeschlagen (PREG-15)."""


def source_id_for(panel_id):
    """Leitet die `source_id` aus der `panel_id` ab (PREG-3, PANEL-6)."""
    return SOURCE_ID_PREFIX + panel_id


class Panel:
    """Eine App-Panel-Instanz der Familie (PREG-3).

    Pflichtfelder: `panel_id`, `source_id`, `display_id`, `config`, `tiles`.
    `router_url` ist optional (PREG-8: leer/fehlend = same-origin). `config`
    (Tuning, instanz-stabil) und `tiles` (Daten) sind getrennte Felder mit
    getrennten Lebenszyklen (PREG-5, E-PANEL-3). Konsumenten lesen nur über
    `to_dict()`, nicht über interne Attribute (CLAUDE.md §6).
    """

    def __init__(self, panel_id, display_id, config, tiles,
                 router_url="", source_id=None):
        self.panel_id = panel_id
        # `source_id` wird aus `panel_id` abgeleitet, in der Datei aber als
        # eigenes Feld geführt (PREG-3), damit Konsumenten nicht parsen müssen.
        self.source_id = source_id if source_id is not None else source_id_for(panel_id)
        self.display_id = display_id
        # PREG-8: leerer/fehlender router_url = same-origin. Wir normalisieren
        # None/fehlend auf den Leerstring — kein Default-Host wird eingesetzt.
        self.router_url = router_url or ""
        self.config = config
        self.tiles = tiles

    def to_dict(self):
        """Panel-Daten für die Schnittstelle (PREG-13/14) und die Datei (PREG-4).

        Bewusst stabile Feld-Reihenfolge, damit save() byte-stabile Diffs
        produziert (analog GER-6 / FAM-11).
        """
        return {
            "panel_id": self.panel_id,
            "source_id": self.source_id,
            "display_id": self.display_id,
            "router_url": self.router_url,
            "config": self.config,
            "tiles": self.tiles,
        }


class Registry:
    """Die geladene Panel-Registry — eine Instanz, eine Familie (PREG-1).

    Hält die Panels in-memory und stellt die Lese-Schnittstelle bereit:
    ein Panel je `panel_id`, alle Panels listen (PREG-13/14). Schreiben
    (PREG-15) läuft über `add` plus die freie save()-Funktion.
    """

    def __init__(self, panels=None):
        # panel_id -> Panel; dict bewahrt die Datei-Reihenfolge.
        self._by_id = {}
        for p in (panels or []):
            self._by_id[p.panel_id] = p

    # -- Lese-Schnittstelle (PREG-13/14) ----------------------------------

    def get(self, panel_id):
        """Ein Panel je `panel_id` (PREG-14). Unbekannte id: None."""
        return self._by_id.get(panel_id)

    def list_all(self):
        """Alle Panel-Instanzen der Familie (PREG-13) — Datei-Reihenfolge."""
        return list(self._by_id.values())

    # -- Schreib-Schnittstelle (PREG-15) ----------------------------------

    def add(self, panel):
        """Ergänzt ein Panel in der In-Memory-Registry (PREG-15-Helfer).

        Wirft RegistryError, wenn die `panel_id` bereits vergeben ist (PREG-6:
        einmal vergebene `panel_id` wird nicht neu vergeben). Wer
        kollisionsfrei anlegen will, ruft vorher `neue_id(...)` auf.
        """
        if panel.panel_id in self._by_id:
            raise RegistryError(
                "Panel mit panel_id %r existiert bereits (PREG-6)" % panel.panel_id)
        validated = _validate_dict(panel.to_dict())
        self._by_id[panel.panel_id] = validated


# ============================================================
#  Slug- und ID-Vergabe (PREG-6)
# ============================================================

def slugify(name):
    """Erzeugt einen PREG-6-konformen `slug` aus einem freien Namen.

    Kleinbuchstaben, Bindestrich-getrennt, keine Umlaute, keine
    Sonderzeichen. Mehrfach-Trenner werden zusammengefasst, führende/
    abschließende Bindestriche entfernt. Ein leerer Eingabewert wirft
    ValueError — ohne Slug keine `panel_id`.
    """
    if not isinstance(name, str):
        raise ValueError("slug-Basis muss ein String sein")
    s = name.translate(_UMLAUT_MAP).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    if not s:
        raise ValueError("Eingabe %r liefert leeren Slug" % name)
    return s


def neue_id(registry, slug):
    """Vergibt kollisionsfrei eine neue `panel_id` nach PREG-6.

    Schema: `<slug(slug)>-<nn>` mit `<nn>` als nullgepolsterter, zweistelliger
    Folgenummer, die je `<slug>` bei `01` beginnt und auf den nächsten in der
    Registry freien Wert gesetzt wird. Bestehende `panel_id`s werden nie neu
    vergeben (PREG-6) — die Identität bleibt stabil.

    `slug` wird selbst noch `slugify`-normalisiert: der Client liefert eine
    Basis (PREG-15), der Service formt daraus den kanonischen Slug.
    """
    norm = slugify(slug)
    praefix = "%s-" % norm
    belegt = set()
    for p in registry.list_all():
        m = _ID_RE.match(p.panel_id)
        if m and m.group("slug") == norm:
            belegt.add(int(m.group("nr")))
    nr = 1
    while nr in belegt:
        nr += 1
    if nr > 99:
        raise RegistryError(
            "kein freier `nn` mehr für Slug %r (PREG-6)" % norm)
    return "%s%02d" % (praefix, nr)


# ============================================================
#  Validierung & Parsen
# ============================================================

def _validate_query_flat(tiles, panel_id):
    """PANEL-7: `query` einer Kachel ist flach (Strings/Zahlen), kein
    verschachteltes Objekt oder Liste. PREG-15 weist verschachteltes `query`
    als Konfigurations-Fehler ab. Tiles ohne `tiles`-Liste oder ohne `query`
    sind unauffällig — wir prüfen nur, was vorhanden ist.
    """
    if not isinstance(tiles, dict):
        return
    eintraege = tiles.get("tiles")
    if not isinstance(eintraege, list):
        return
    for tile in eintraege:
        if not isinstance(tile, dict):
            continue
        if "query" not in tile:
            continue
        query = tile["query"]
        if not isinstance(query, dict):
            raise RegistryError(
                "Panel %r: tile %r query muss ein flaches Objekt sein (PANEL-7)"
                % (panel_id, tile.get("key")))
        for k, v in query.items():
            if not isinstance(v, (str, int, float)) or isinstance(v, bool):
                raise RegistryError(
                    "Panel %r: tile %r query.%s muss String/Zahl sein, "
                    "kein verschachteltes Objekt (PANEL-7)"
                    % (panel_id, tile.get("key"), k))


def _validate_dict(raw):
    """Baut ein Panel aus Rohdaten und validiert die PREG-3-Felder.

    Wirft RegistryError, wenn ein Pflichtfeld fehlt oder ein Wert das Schema
    verletzt. Wird sowohl beim Laden der Datei als auch beim `add`-Aufruf
    benutzt — eine Stelle, die die Validierung kennt.
    """
    for feld in ("panel_id", "display_id", "config", "tiles"):
        if feld not in raw or raw[feld] in (None, ""):
            raise RegistryError("Panel ohne Pflichtfeld %r: %r" % (feld, raw))
    panel_id = raw["panel_id"]
    if not _ID_RE.match(panel_id):
        raise RegistryError(
            "Panel %r: panel_id-Schema verletzt (PREG-6 erwartet `<slug>-<nn>`)"
            % panel_id)
    # `source_id` ist aus `panel_id` abgeleitet (PREG-3); ein abweichend
    # gespeicherter Wert würde lügen.
    source_id = raw.get("source_id")
    erwartet = source_id_for(panel_id)
    if source_id is not None and source_id != erwartet:
        raise RegistryError(
            "Panel %r: source_id %r passt nicht zu panel_id (erwartet %r, PREG-3)"
            % (panel_id, source_id, erwartet))
    if not isinstance(raw["config"], dict):
        raise RegistryError(
            "Panel %r: config muss ein Objekt sein (PANEL-8)" % panel_id)
    if not isinstance(raw["tiles"], dict):
        raise RegistryError(
            "Panel %r: tiles muss ein Objekt sein (PANEL-3)" % panel_id)
    _validate_query_flat(raw["tiles"], panel_id)
    # PREG-8: router_url ist optional; None/fehlend → Leerstring (same-origin).
    router_url = raw.get("router_url") or ""
    return Panel(
        panel_id=panel_id,
        display_id=raw["display_id"],
        config=raw["config"],
        tiles=raw["tiles"],
        router_url=router_url,
        source_id=erwartet,
    )


# ============================================================
#  Laden & Schreiben (PREG-4, PREG-15)
# ============================================================

def load(path):
    """Lädt die Registry-Datei (PREG-4).

    Fehlt die Datei oder ist sie nicht parsebar, protokolliert das System EINE
    Warnung und liefert eine leere Registry — kein Crash (PREG-4, symmetrisch
    zu GER-4 / ROU-18 / FAM-6). Inhaltlich ungültige Daten (fehlendes
    Pflichtfeld, kollidierende ids) sind dagegen ein echter Fehler und werfen
    RegistryError — die Datei ist Daten, falsche Daten sind ein Datei-Fehler,
    kein stiller Default.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.warning(
            "panels.json nicht gefunden: %s — starte mit leerer Panel-Liste",
            path)
        return Registry()
    except json.JSONDecodeError as e:
        logging.warning(
            "panels.json nicht parsebar (%s): %s — starte mit leerer Panel-Liste",
            path, e)
        return Registry()

    raw_panels = data.get("panels") if isinstance(data, dict) else None
    if raw_panels is None:
        raw_panels = []
    if not isinstance(raw_panels, list):
        raise RegistryError(
            "panels.json: `panels` muss eine Liste sein, ist %r" % type(raw_panels))

    panels = []
    seen = set()
    for raw in raw_panels:
        if not isinstance(raw, dict):
            raise RegistryError("panels.json: Eintrag ist kein Objekt: %r" % raw)
        p = _validate_dict(raw)
        if p.panel_id in seen:
            raise RegistryError(
                "doppelte panel_id %r in der Registry-Datei (PREG-6)" % p.panel_id)
        seen.add(p.panel_id)
        panels.append(p)

    logging.info("panels geladen: %d", len(panels))
    return Registry(panels)


def save(registry, path):
    """Schreibt die Registry atomar mit 0600-Rechten in die Datei (PREG-4/15).

    Pattern wie geraete.save (GER-6): erst eine Temp-Datei im Zielverzeichnis,
    kontrolliert mit `os.open(..., 0o600)` geöffnet, dann `os.replace` (in-
    Filesystem atomares Rename, DCOMP-4). Bei einem Fehlschlag wird die
    Temp-Datei aufgeräumt und ein RegistryError geworfen — die alte Datei
    bleibt unverändert.
    """
    payload = {"panels": [p.to_dict() for p in registry.list_all()]}

    target_dir = os.path.dirname(os.path.abspath(path))
    if target_dir and not os.path.isdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".panels.", suffix=".json.tmp", dir=target_dir)
    os.close(tmp_fd)
    try:
        fd = os.open(tmp_path, os.O_WRONLY | os.O_TRUNC, FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=False)
            f.write("\n")
        os.chmod(tmp_path, FILE_MODE)
        os.replace(tmp_path, path)
    except OSError as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise RegistryError(
            "panels.json konnte nicht geschrieben werden: %s" % e) from e

    os.chmod(path, FILE_MODE)


def is_owner_only(path):
    """True, wenn `path` die Dateirechte aus PREG-4 (0600) trägt.

    Hilfsfunktion für Diagnose und Tests — analog `geraete.is_owner_only`.
    """
    mode = stat.S_IMODE(os.stat(path).st_mode)
    return mode == FILE_MODE
