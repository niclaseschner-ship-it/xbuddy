"""tools.medien_store — Medien-Index: Dataclass + atomares Schreiben/Loeschen.

Domain-neutrale Library fuer Medien-Verwaltung. Kein photo/-Bezug,
kein in_library-Feld (photo-spezifisch). Kein Flask.

Public-API: Medium, StoreError, TYP_FOTO, TYP_VIDEO, INDEX_DATEI,
load, add, delete, serve_pfad, thumb_pfad, auto_delete.
"""

import contextlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

TYP_FOTO = "foto"
TYP_VIDEO = "video"

INDEX_DATEI = "library.json"


class StoreError(Exception):
    """Ein Library-Schreib-/Loeschaufruf ist fehlgeschlagen."""


class Medium:
    """Ein Eintrag der Library.

    `aufgenommen`/`dauer` sind optional (None, wenn nicht ermittelbar bzw. kein
    Video). `datei`/`thumbnail` sind Dateinamen relativ zum verzeichnis.
    Kein `in_library`-Feld — das ist photo-spezifisch.
    """

    def __init__(self, id, datei, thumbnail, typ, hinzugefuegt,
                 aufgenommen=None, dauer=None):
        self.id = id
        self.datei = datei
        self.thumbnail = thumbnail
        self.typ = typ
        self.hinzugefuegt = hinzugefuegt    # ISO-8601, immer (TTL-Basis)
        self.aufgenommen = aufgenommen      # ISO-8601 | None
        self.dauer = dauer                  # Sekunden float | None (nur Video)

    def to_index_dict(self):
        """Eintrag fuer library.json — erweiterbar durch Konsumenten."""
        return {
            "id": self.id,
            "datei": self.datei,
            "thumbnail": self.thumbnail,
            "typ": self.typ,
            "hinzugefuegt": self.hinzugefuegt,
            "aufgenommen": self.aufgenommen,
            "dauer": self.dauer,
        }


def _index_path(verzeichnis):
    return os.path.join(verzeichnis, INDEX_DATEI)


def _medium_aus_dict(raw):
    """Baut ein Medium aus einem Index-Dict. Wirft KeyError/TypeError bei Defekten."""
    return Medium(
        id=raw["id"],
        datei=raw["datei"],
        thumbnail=raw["thumbnail"],
        typ=raw["typ"],
        hinzugefuegt=raw["hinzugefuegt"],
        aufgenommen=raw.get("aufgenommen"),
        dauer=raw.get("dauer"),
    )


def load(verzeichnis):
    """Laedt den Library-Index. Fehlt/kaputt -> leere Liste (kein Crash).

    Unvollstaendige Eintraege werden uebersprungen (geloggt). Konsumenten
    koennen `_medium_aus_dict` ueberlagern um Felder zu ergaenzen.
    """
    path = _index_path(verzeichnis)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("library.json nicht lesbar (%s): %s — starte leer", path, e)
        return []
    medien = []
    for raw in (data.get("medien") if isinstance(data, dict) else None) or []:
        try:
            medien.append(_medium_aus_dict(raw))
        except (KeyError, TypeError) as e:
            logger.warning("library.json-Eintrag unvollstaendig (%r): %s — uebersprungen", raw, e)
    return medien


def _save_index(verzeichnis, medien):
    """Schreibt den Index atomar (Temp + os.replace). Hebt StoreError bei Fehler."""
    os.makedirs(verzeichnis, exist_ok=True)
    path = _index_path(verzeichnis)
    payload = {"medien": [m.to_index_dict() for m in medien]}
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".library.", suffix=".json.tmp", dir=verzeichnis)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise StoreError("library.json konnte nicht geschrieben werden: %s" % e) from e


def _atomar_schreiben(ziel_pfad, daten):
    """Schreibt eine Binaerdatei atomar (Temp + os.replace). Hebt StoreError."""
    ziel_dir = os.path.dirname(ziel_pfad)
    os.makedirs(ziel_dir, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".medium.", suffix=".tmp", dir=ziel_dir)
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(daten)
        os.replace(tmp_path, ziel_pfad)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise StoreError("Mediendatei konnte nicht geschrieben werden: %s" % e) from e


def add(verzeichnis, *, id, typ, daten, dateiname, thumbnail_daten,
        thumbnail_name, aufgenommen=None, dauer=None, now=None, **extra_felder):
    """Schreibt Vollmedium + Thumbnail + Index-Eintrag atomar zusammen.

    Reihenfolge mit Rollback: Vollmedium -> Thumbnail -> Index. Scheitert
    ein Teilschritt, werden die zuvor geschriebenen Teile wieder entfernt.

    `now` ist die injizierbare Zeitquelle fuer den Hinzufuege-Stempel.
    `**extra_felder` werden von Konsumenten (z. B. photo/) an den Index
    angehaengt; sie werden durch `load()` beim Einlesen via `raw.get()` gelesen
    sofern der Konsument `_medium_aus_dict` ueberlagert.
    Liefert das neue `Medium`.
    """
    if now is None:
        now = datetime.now(UTC)
    hinzugefuegt = now.replace(microsecond=0).isoformat()

    medien_pfad = os.path.join(verzeichnis, dateiname)
    thumb_pfad_abs = os.path.join(verzeichnis, thumbnail_name)

    _atomar_schreiben(medien_pfad, daten)
    try:
        _atomar_schreiben(thumb_pfad_abs, thumbnail_daten)
    except StoreError:
        _entferne_still(medien_pfad)
        raise

    medium = Medium(
        id=id, datei=dateiname, thumbnail=thumbnail_name, typ=typ,
        hinzugefuegt=hinzugefuegt, aufgenommen=aufgenommen, dauer=dauer)

    # Lade vorhandene Liste; persistiere mit extra_felder falls vorhanden.
    medien = load(verzeichnis)
    medien.append(medium)
    try:
        # extra_felder werden in den Index-Eintrag des neuen Mediums gemischt.
        if extra_felder:
            _save_index_mit_extras(verzeichnis, medien, medium, extra_felder)
        else:
            _save_index(verzeichnis, medien)
    except StoreError:
        _entferne_still(medien_pfad)
        _entferne_still(thumb_pfad_abs)
        raise
    return medium


def _save_index_mit_extras(verzeichnis, medien, neues_medium, extra_felder):
    """Schreibt den Index atomar; das neue Medium erhaelt extra_felder."""
    os.makedirs(verzeichnis, exist_ok=True)
    path = _index_path(verzeichnis)

    def _zu_dict(m):
        d = m.to_index_dict()
        if m is neues_medium:
            d.update(extra_felder)
        return d

    payload = {"medien": [_zu_dict(m) for m in medien]}
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".library.", suffix=".json.tmp", dir=verzeichnis)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise StoreError("library.json konnte nicht geschrieben werden: %s" % e) from e


def delete(verzeichnis, medium_id):
    """Entfernt Vollmedium + Thumbnail + Index-Eintrag atomar.

    Schreibt zuerst den Index ohne den Eintrag (atomar), dann loescht die
    Dateien. Liefert True, wenn ein Eintrag entfernt wurde, sonst False.
    """
    medien = load(verzeichnis)
    rest = [m for m in medien if m.id != medium_id]
    if len(rest) == len(medien):
        return False
    ziel = next(m for m in medien if m.id == medium_id)
    _save_index(verzeichnis, rest)
    _entferne_still(os.path.join(verzeichnis, ziel.datei))
    _entferne_still(os.path.join(verzeichnis, ziel.thumbnail))
    return True


def _entferne_still(pfad):
    """Entfernt eine Datei, ohne bei Fehlen/IO-Fehler zu werfen."""
    with contextlib.suppress(OSError):
        os.remove(pfad)


def serve_pfad(verzeichnis, medium_id):
    """Absoluter Pfad zur Vollmedium-Datei einer id — oder None."""
    return _datei_pfad(verzeichnis, medium_id, attr="datei")


def thumb_pfad(verzeichnis, medium_id):
    """Absoluter Pfad zum Thumbnail/Poster-Frame einer id — oder None."""
    return _datei_pfad(verzeichnis, medium_id, attr="thumbnail")


def _datei_pfad(verzeichnis, medium_id, attr):
    medien = load(verzeichnis)
    medium = next((m for m in medien if m.id == medium_id), None)
    if medium is None:
        return None
    rel = getattr(medium, attr)
    if not rel or ".." in rel.split("/"):
        return None
    pfad = os.path.join(verzeichnis, rel)
    return pfad if os.path.isfile(pfad) else None


def auto_delete(verzeichnis, auto_delete_tage, now=None):
    """Entfernt Medien aelter als TTL am Hinzufuege-Stempel.

    `auto_delete_tage = 0` heisst AUS — es wird nie geloescht.
    `now` ist die injizierbare Zeitquelle (Test-Determinismus).
    Liefert die Liste der entfernten ids.
    """
    if not auto_delete_tage:
        return []
    if now is None:
        now = datetime.now(UTC)
    grenze_s = auto_delete_tage * 86400
    entfernt = []
    for medium in load(verzeichnis):
        alter_s = (now - _parse_iso(medium.hinzugefuegt)).total_seconds()
        if alter_s > grenze_s and delete(verzeichnis, medium.id):
            entfernt.append(medium.id)
    return entfernt


def _parse_iso(stempel):
    """Parst einen ISO-8601-Stempel und stellt sicher, dass er tz-bewusst ist."""
    dt = datetime.fromisoformat(stempel)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
