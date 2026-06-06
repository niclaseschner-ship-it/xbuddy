"""Photo-Buddy — Medien-Library: Index + atomares Schreiben/Löschen (PHOTO-7/10).

Siehe specs/buddies/photo.md §2-3. Dieses Modul besitzt die **Library-Daten**:
den Index `library.json` neben den Mediendateien (im library_verzeichnis,
gitignored, FAM-9-Muster) und das atomare Zusammenschreiben/-löschen von
Vollmedium + Thumbnail + Index-Eintrag (PHOTO-10, DCOMP-4).

Es spiegelt das ratifizierte Familie-Foto-Schreibmuster (FAM-13/`setze_foto`,
E-PHOTO-3): Temp-Datei im Zielverzeichnis + `os.replace`, Rollback bei
Teil-Fehler — **kein zweiter Schreibstil**. Ein geteilter Upload-Helfer wird
bewusst NICHT extrahiert (OPEN-PHOTO-F, Stop-Rule des Contracts) — das Muster
lebt hier lokal.

Public-API: `load`, `add`, `delete`, `serve_pfad`, `thumb_pfad`,
`sortiere`, `auto_delete`.

Reihenfolge (PHOTO-11): vier Kombinationen Richtung × Stempel-Quelle; fehlt bei
`aufgenommen` der EXIF-/Container-Stempel, fällt das Medium auf den
Hinzufüge-Stempel zurück. Auto-Delete (PHOTO-12) nimmt ein injizierbares `now`
für Test-Determinismus.
"""

import contextlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime

from . import config as config_mod

logger = logging.getLogger(__name__)

TYP_FOTO = "foto"
TYP_VIDEO = "video"

INDEX_DATEI = "library.json"


class StoreError(Exception):
    """Ein Library-Schreib-/Lösch-Aufruf ist fehlgeschlagen (PHOTO-10)."""


class Medium:
    """Ein Eintrag der Library (PHOTO-7).

    `aufgenommen`/`dauer` sind optional (None, wenn nicht ermittelbar bzw. kein
    Video). `datei`/`thumbnail` sind Dateinamen relativ zum library_verzeichnis.
    """

    def __init__(self, id, datei, thumbnail, typ, hinzugefuegt,
                 aufgenommen=None, dauer=None):
        self.id = id
        self.datei = datei
        self.thumbnail = thumbnail
        self.typ = typ
        self.hinzugefuegt = hinzugefuegt    # ISO-8601, immer (TTL-Basis + Sortier-Fallback)
        self.aufgenommen = aufgenommen      # ISO-8601 | None
        self.dauer = dauer                  # Sekunden float | None (nur Video)

    def to_index_dict(self):
        """Voller Eintrag für library.json (PHOTO-7)."""
        return {
            "id": self.id,
            "datei": self.datei,
            "thumbnail": self.thumbnail,
            "typ": self.typ,
            "hinzugefuegt": self.hinzugefuegt,
            "aufgenommen": self.aufgenommen,
            "dauer": self.dauer,
        }

    def to_meta_dict(self):
        """Schlanke Metadaten für die Listen-API (PHOTO-14) — ohne Dateinamen."""
        return {
            "id": self.id,
            "typ": self.typ,
            "hinzugefuegt": self.hinzugefuegt,
            "aufgenommen": self.aufgenommen,
            "dauer": self.dauer,
        }


def _index_path(library_verzeichnis):
    return os.path.join(library_verzeichnis, INDEX_DATEI)


def load(library_verzeichnis):
    """Lädt den Library-Index (PHOTO-7). Fehlt/kaputt → leere Library (PHOTO-6).

    Eine fehlende Datei ist der Normalfall einer frischen Instanz (leere
    Library → neutraler Zustand vor dem Kind). Kaputtes JSON wird EINMAL
    protokolliert und als leer behandelt — nie ein Crash.
    """
    path = _index_path(library_verzeichnis)
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
            medien.append(Medium(
                id=raw["id"],
                datei=raw["datei"],
                thumbnail=raw["thumbnail"],
                typ=raw["typ"],
                hinzugefuegt=raw["hinzugefuegt"],
                aufgenommen=raw.get("aufgenommen"),
                dauer=raw.get("dauer"),
            ))
        except (KeyError, TypeError) as e:
            logger.warning("library.json-Eintrag unvollständig (%r): %s — übersprungen", raw, e)
    return medien


def _save_index(library_verzeichnis, medien):
    """Schreibt den Index atomar (DCOMP-4, Muster FAM-11): Temp im
    Zielverzeichnis + os.replace. Hebt StoreError bei Schreibfehler und lässt
    keine verwaiste Temp-Datei zurück."""
    os.makedirs(library_verzeichnis, exist_ok=True)
    path = _index_path(library_verzeichnis)
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


def _atomar_schreiben(ziel_pfad, daten):
    """Schreibt eine Binärdatei atomar (DCOMP-4, FAM-13-Muster): Temp im selben
    Verzeichnis + os.replace. Hebt StoreError, ohne eine halbe Datei oder eine
    verwaiste Temp-Datei zu hinterlassen."""
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


def add(library_verzeichnis, *, id, typ, daten, dateiname, thumbnail_daten,
        thumbnail_name, aufgenommen=None, dauer=None, now=None):
    """Schreibt Vollmedium + Thumbnail + Index-Eintrag atomar zusammen (PHOTO-10).

    Reihenfolge mit Rollback (DCOMP-4): erst Vollmedium, dann Thumbnail, dann der
    Index. Scheitert ein Teilschritt, werden die zuvor geschriebenen Teile wieder
    entfernt — es bleibt **weder** ein halb geschriebenes Medium **noch** ein
    verwaister Index-Eintrag zurück (PHOTO-10). Liefert das neue `Medium`.

    `now` ist die injizierbare Zeitquelle für den Hinzufüge-Stempel (PHOTO-12,
    Test-Determinismus) — nie eine Wall-Clock tief im Code.
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
        _entferne_still(medien_pfad)
        raise

    medium = Medium(
        id=id, datei=dateiname, thumbnail=thumbnail_name, typ=typ,
        hinzugefuegt=hinzugefuegt, aufgenommen=aufgenommen, dauer=dauer)

    medien = load(library_verzeichnis)
    medien.append(medium)
    try:
        _save_index(library_verzeichnis, medien)
    except StoreError:
        # Index-Save gescheitert → die beiden geschriebenen Dateien zurückrollen,
        # sonst lägen Medium+Thumbnail ohne Index-Verweis herum (PHOTO-10).
        _entferne_still(medien_pfad)
        _entferne_still(thumb_pfad_abs)
        raise
    return medium


def delete(library_verzeichnis, medium_id):
    """Entfernt Vollmedium + Thumbnail + Index-Eintrag atomar (PHOTO-16/10).

    Schreibt zuerst den Index ohne den Eintrag (atomar) — danach gibt es für
    keinen Leser mehr einen Verweis auf das Medium — und löscht dann die
    Dateien. Liefert True, wenn ein Eintrag entfernt wurde, sonst False
    (unbekannte id → 404 in der API).
    """
    medien = load(library_verzeichnis)
    rest = [m for m in medien if m.id != medium_id]
    if len(rest) == len(medien):
        return False
    ziel = next(m for m in medien if m.id == medium_id)
    _save_index(library_verzeichnis, rest)
    _entferne_still(os.path.join(library_verzeichnis, ziel.datei))
    _entferne_still(os.path.join(library_verzeichnis, ziel.thumbnail))
    return True


def _entferne_still(pfad):
    """Entfernt eine Datei, ohne bei Fehlen/IO-Fehler zu werfen (Rollback-Helfer)."""
    with contextlib.suppress(OSError):
        os.remove(pfad)


def serve_pfad(library_verzeichnis, medium_id):
    """Absoluter Pfad zur Vollmedium-Datei einer id — oder None (PHOTO-15/404).

    Pfad-Traversal über den gespeicherten Dateinamen schließt der `..`-Check aus
    (Muster FAM `foto_pfad`)."""
    return _datei_pfad(library_verzeichnis, medium_id, attr="datei")


def thumb_pfad(library_verzeichnis, medium_id):
    """Absoluter Pfad zum Thumbnail/Poster-Frame einer id — oder None (PHOTO-15/404)."""
    return _datei_pfad(library_verzeichnis, medium_id, attr="thumbnail")


def _datei_pfad(library_verzeichnis, medium_id, attr):
    medien = load(library_verzeichnis)
    medium = next((m for m in medien if m.id == medium_id), None)
    if medium is None:
        return None
    rel = getattr(medium, attr)
    if not rel or ".." in rel.split("/"):
        return None
    pfad = os.path.join(library_verzeichnis, rel)
    return pfad if os.path.isfile(pfad) else None


# ============================================================
#  Reihenfolge (PHOTO-11) & Auto-Delete (PHOTO-12)
# ============================================================

def _sortier_stempel(medium, stempel_quelle):
    """Der Stempel, nach dem sortiert wird (PHOTO-11).

    Bei `aufgenommen` ohne EXIF-/Container-Stempel fällt das Medium auf den
    Hinzufüge-Stempel zurück (E-PHOTO-8) — `hinzugefuegt` ist immer gesetzt.
    """
    if stempel_quelle == config_mod.STEMPEL_AUFGENOMMEN and medium.aufgenommen:
        return medium.aufgenommen
    return medium.hinzugefuegt


def sortiere(medien, sortier_richtung, stempel_quelle):
    """Ordnet die Library nach PHOTO-11 (Richtung × Stempel-Quelle).

    `neueste-zuerst` = absteigend, `aelteste-zuerst` = aufsteigend. Sekundär-
    Schlüssel ist die `id` — deterministisch bei gleichen Stempeln (z. B. zwei
    Medien in derselben Sekunde hinzugefügt).
    """
    absteigend = sortier_richtung == config_mod.RICHTUNG_NEU
    return sorted(
        medien,
        key=lambda m: (_sortier_stempel(m, stempel_quelle), m.id),
        reverse=absteigend)


def auto_delete(library_verzeichnis, auto_delete_tage, now=None):
    """Entfernt Medien älter als TTL am Hinzufüge-Stempel (PHOTO-12).

    `auto_delete_tage = 0` heißt AUS — es wird **nie** gelöscht (E-PHOTO-6,
    Default). `now` ist die injizierbare Zeitquelle (Test-Determinismus,
    PHOTO-23) — nie eine Wall-Clock tief im Code. Liefert die Liste der
    entfernten ids.
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
    """Parst einen ISO-8601-Stempel und stellt sicher, dass er tz-bewusst ist
    (UTC als Fallback) — sonst schlägt die Subtraktion gegen ein aware `now`
    fehl."""
    dt = datetime.fromisoformat(stempel)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
