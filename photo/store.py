"""Photo-Buddy — Medien-Library: duenner Adapter auf tools.medien_store.store.

Photo-spezifische Belange:
  - Photo-Medium erbt von Medium und traegt `in_library` (T799).
  - `load()` liest `in_library` aus dem Index (Backwards-Compat: fehlt -> True).
  - `add()` persistiert `in_library` als Teil des Index-Eintrags.
  - `sortiere()` / `auto_delete()` bleiben photo-seitig (nutzen config_mod).

Re-Exports: alle heutigen Public-Symbole fuer photo/main.py + Tests.
"""

import contextlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime

from tools.medien_store import store as _lib_store

from . import config as config_mod

logger = logging.getLogger(__name__)

# Re-Exports fuer Konsumenten (main.py, tests, ingest.py)
TYP_FOTO = _lib_store.TYP_FOTO
TYP_VIDEO = _lib_store.TYP_VIDEO
INDEX_DATEI = _lib_store.INDEX_DATEI
StoreError = _lib_store.StoreError

# Re-Export der Hilfsfunktionen aus der Library.
serve_pfad = _lib_store.serve_pfad
thumb_pfad = _lib_store.thumb_pfad
_atomar_schreiben = _lib_store._atomar_schreiben  # fuer Test-Monkeypatching (test_photo.py)


class Medium(_lib_store.Medium):
    """Photo-spezifisches Medium: erbt library.Medium + traegt in_library (T799).

    `in_library` steuert die Library-Sichtbarkeit (T799): False schliesst das
    Medium aus der Standard-Listenansicht aus (z. B. Essen-Fotos), es bleibt
    aber ueber die Einzel-URL abrufbar (PHOTO-15, ESSEN-22).
    """

    def __init__(self, id, datei, thumbnail, typ, hinzugefuegt,
                 aufgenommen=None, dauer=None, in_library=True):
        super().__init__(
            id=id, datei=datei, thumbnail=thumbnail, typ=typ,
            hinzugefuegt=hinzugefuegt, aufgenommen=aufgenommen, dauer=dauer)
        self.in_library = in_library

    def to_index_dict(self):
        """Voller Eintrag fuer library.json einschliesslich in_library."""
        d = super().to_index_dict()
        d["in_library"] = self.in_library
        return d

    def to_meta_dict(self):
        """Schlanke Metadaten fuer die Listen-API (PHOTO-14) — ohne Dateinamen."""
        return {
            "id": self.id,
            "typ": self.typ,
            "hinzugefuegt": self.hinzugefuegt,
            "aufgenommen": self.aufgenommen,
            "dauer": self.dauer,
            "in_library": self.in_library,
        }


def _photo_medium_aus_dict(raw):
    """Baut ein photo-spezifisches Medium aus einem Index-Dict."""
    return Medium(
        id=raw["id"],
        datei=raw["datei"],
        thumbnail=raw["thumbnail"],
        typ=raw["typ"],
        hinzugefuegt=raw["hinzugefuegt"],
        aufgenommen=raw.get("aufgenommen"),
        dauer=raw.get("dauer"),
        in_library=raw.get("in_library", True),  # T799: Default True (backwards-compat)
    )


def load(library_verzeichnis):
    """Laedt den Library-Index mit photo-spezifischem Medium (in_library).

    Fehlt/kaputt -> leere Library (kein Crash). Unvollstaendige Eintraege
    werden uebersprungen.
    """
    path = _lib_store._index_path(library_verzeichnis)
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
            medien.append(_photo_medium_aus_dict(raw))
        except (KeyError, TypeError) as e:
            logger.warning(
                "library.json-Eintrag unvollstaendig (%r): %s — uebersprungen", raw, e)
    return medien


def add(library_verzeichnis, *, id, typ, daten, dateiname, thumbnail_daten,
        thumbnail_name, aufgenommen=None, dauer=None, in_library=True, now=None):
    """Schreibt Vollmedium + Thumbnail + Index-Eintrag atomar zusammen (PHOTO-10).

    Persistiert in_library als Teil des Index-Eintrags (photo-spezifisch).
    Liefert ein photo-spezifisches Medium (mit in_library).

    Reihenfolge mit Rollback (DCOMP-4): erst Vollmedium, dann Thumbnail, dann
    Index. Scheitert ein Teilschritt, werden die zuvor geschriebenen Teile
    wieder entfernt.
    """
    if now is None:
        now = datetime.now(UTC)
    hinzugefuegt = now.replace(microsecond=0).isoformat()

    medien_pfad = os.path.join(library_verzeichnis, dateiname)
    thumb_pfad_abs = os.path.join(library_verzeichnis, thumbnail_name)

    _atomar_schreiben(medien_pfad, daten)
    try:
        _atomar_schreiben(thumb_pfad_abs, thumbnail_daten)
    except StoreError:
        _lib_store._entferne_still(medien_pfad)
        raise

    medium = Medium(
        id=id, datei=dateiname, thumbnail=thumbnail_name, typ=typ,
        hinzugefuegt=hinzugefuegt, aufgenommen=aufgenommen, dauer=dauer,
        in_library=in_library)

    medien = load(library_verzeichnis)
    medien.append(medium)
    try:
        _save_index(library_verzeichnis, medien)
    except StoreError:
        _lib_store._entferne_still(medien_pfad)
        _lib_store._entferne_still(thumb_pfad_abs)
        raise
    return medium


def _save_index(library_verzeichnis, medien):
    """Schreibt den Index mit photo-Medium-Eintraegen (inkl. in_library) atomar."""
    os.makedirs(library_verzeichnis, exist_ok=True)
    path = _lib_store._index_path(library_verzeichnis)
    payload = {"medien": [m.to_index_dict() for m in medien]}
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".library.", suffix=".json.tmp", dir=library_verzeichnis)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except OSError as e:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise StoreError("library.json konnte nicht geschrieben werden: %s" % e) from e


def delete(library_verzeichnis, medium_id):
    """Entfernt Vollmedium + Thumbnail + Index-Eintrag atomar (PHOTO-16/10).

    Schreibt zuerst den Index ohne den Eintrag (atomar), dann loescht die
    Dateien. Liefert True, wenn ein Eintrag entfernt wurde, sonst False.
    """
    medien = load(library_verzeichnis)
    rest = [m for m in medien if m.id != medium_id]
    if len(rest) == len(medien):
        return False
    ziel = next(m for m in medien if m.id == medium_id)
    _save_index(library_verzeichnis, rest)
    _lib_store._entferne_still(os.path.join(library_verzeichnis, ziel.datei))
    _lib_store._entferne_still(os.path.join(library_verzeichnis, ziel.thumbnail))
    return True


# ============================================================
#  Reihenfolge (PHOTO-11) & Auto-Delete (PHOTO-12)
# ============================================================

def _sortier_stempel(medium, stempel_quelle):
    """Der Stempel, nach dem sortiert wird (PHOTO-11)."""
    if stempel_quelle == config_mod.STEMPEL_AUFGENOMMEN and medium.aufgenommen:
        return medium.aufgenommen
    return medium.hinzugefuegt


def sortiere(medien, sortier_richtung, stempel_quelle):
    """Ordnet die Library nach PHOTO-11 (Richtung x Stempel-Quelle)."""
    absteigend = sortier_richtung == config_mod.RICHTUNG_NEU
    return sorted(
        medien,
        key=lambda m: (_sortier_stempel(m, stempel_quelle), m.id),
        reverse=absteigend)


def auto_delete(library_verzeichnis, auto_delete_tage, now=None):
    """Entfernt Medien aelter als TTL am Hinzufuege-Stempel (PHOTO-12).

    `auto_delete_tage = 0` heisst AUS (E-PHOTO-6, Default).
    `now` ist die injizierbare Zeitquelle (Test-Determinismus, PHOTO-23).
    Liefert die Liste der entfernten ids.
    """
    if not auto_delete_tage:
        return []
    if now is None:
        now = datetime.now(UTC)
    grenze_s = auto_delete_tage * 86400
    entfernt = []
    for medium in load(library_verzeichnis):
        alter_s = (now - _parse_iso(medium.hinzugefuegt)).total_seconds()
        if alter_s > grenze_s and delete(library_verzeichnis, medium.id):
            entfernt.append(medium.id)
    return entfernt


def _parse_iso(stempel):
    """Parst einen ISO-8601-Stempel und stellt sicher, dass er tz-bewusst ist."""
    dt = datetime.fromisoformat(stempel)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
