"""Photo-Buddy — defensive Normalisierung beim Ingest (PHOTO-8/9).

Siehe specs/buddies/photo.md §4. Dieses Modul überführt ein eingehendes Medium
in ein **web-anzeigbares Format** und erzeugt das Thumbnail / den Poster-Frame:

  Foto  → JPEG  (HEIC wird über Pillow + pillow-heif dekodiert und re-encodiert;
                 bereits web-taugliches JPEG/PNG/WebP wird durchgereicht bzw. zu
                 JPEG normalisiert) + verkleinertes Thumbnail (PHOTO-9).
  Video → MP4/H.264 (HEVC/MOV wird per ffmpeg transcodiert; bereits
                 web-taugliches MP4/H.264 wird durchgereicht, E-PHOTO-9) +
                 Poster-Frame als JPEG + Dauer (PHOTO-9, via ffprobe/ffmpeg).

Defensiv (E-PHOTO-7/9): Telegram re-encodiert nur den **Kompressions-Pfad**
serverseitig; der „als Datei/Dokument"-Pfad liefert iPhone-HEIC / HEVC-MOV
roh. Wir verlassen uns nicht auf Telegram, sondern normalisieren selbst —
im Kompressions-Pfad ist das ein billiger Pass-through.

Das **Aufnahmedatum** (EXIF beim Foto, Container-Metadaten beim Video) wird
**vor** der Konvertierung extrahiert (PHOTO-8), bevor es verloren geht.

Public-API: `normalisiere(rohbytes, dateiname) -> NormResult`.
"""

import io
import json
import logging
import os
import subprocess
import tempfile

import pillow_heif
from PIL import Image, ImageOps

from . import store

logger = logging.getLogger(__name__)

# pillow-heif als Pillow-Decoder registrieren, damit Image.open() HEIC/HEIF liest.
pillow_heif.register_heif_opener()

# PHOTO-9: längste Kante des Thumbnails. Kein Familie-3-Wert (kein Override-Pfad
# nötig) — eine reine technische Konstante des Übersichts-Grids.
THUMBNAIL_MAX_KANTE = 480

# Web-taugliche Foto-Formate (E-PHOTO-9): wird so ein Format erkannt, ist die
# Anzeige im Browser sicher — wir normalisieren trotzdem nach JPEG, damit die
# View einen einheitlichen Content-Type ausliefert (HEIC ist nie web-tauglich).
_FOTO_ENDUNGEN = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
_VIDEO_ENDUNGEN = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".hevc")


class NormalizeError(Exception):
    """Das Medium konnte nicht normalisiert werden (unbekanntes/kaputtes
    Format, fehlendes Tool). PHOTO-13 lehnt es mit einem klaren Fehler ab."""


class NormResult:
    """Ergebnis der Normalisierung (PHOTO-8/9).

    `daten`/`thumbnail` sind die fertigen Bytes (Vollmedium + Thumbnail/Poster).
    `endung` ist die Datei-Endung des normalisierten Vollmediums (`.jpg`/`.mp4`).
    `aufgenommen` ist der ISO-8601-Aufnahmestempel oder None. `dauer` ist die
    Video-Dauer in Sekunden (float) oder None.
    """

    def __init__(self, typ, daten, endung, thumbnail, thumbnail_endung,
                 aufgenommen=None, dauer=None):
        self.typ = typ
        self.daten = daten
        self.endung = endung
        self.thumbnail = thumbnail
        self.thumbnail_endung = thumbnail_endung
        self.aufgenommen = aufgenommen
        self.dauer = dauer


def normalisiere(rohbytes, dateiname):
    """Normalisiert ein eingehendes Medium (PHOTO-8/9).

    Erkennt Foto vs. Video an der Datei-Endung und delegiert. Hebt
    NormalizeError bei leeren Daten oder unbekanntem/kaputtem Format.
    """
    if not rohbytes:
        raise NormalizeError("leeres Medium")
    endung = os.path.splitext(dateiname or "")[1].lower()
    if endung in _VIDEO_ENDUNGEN:
        return _normalisiere_video(rohbytes, endung)
    if endung in _FOTO_ENDUNGEN or endung == "":
        # Ohne Endung versuchen wir Foto (Pillow erkennt das Format selbst).
        return _normalisiere_foto(rohbytes)
    raise NormalizeError("unbekanntes Medien-Format: %r" % endung)


# ============================================================
#  Foto (PHOTO-8/9)
# ============================================================

def _normalisiere_foto(rohbytes):
    """Foto → JPEG + Thumbnail; Aufnahmedatum aus EXIF (PHOTO-8/9).

    HEIC wird über den registrierten pillow-heif-Opener gelesen. EXIF-
    Aufnahmedatum wird VOR dem Re-Encode extrahiert (PHOTO-8). EXIF-
    Orientierung wird angewandt, damit das Bild aufrecht steht.
    """
    try:
        bild = Image.open(io.BytesIO(rohbytes))
        bild.load()
    except Exception as e:  # Pillow wirft diverse Exceptions je Format
        raise NormalizeError("Foto nicht dekodierbar: %s" % e) from e

    aufgenommen = _exif_aufnahmedatum(bild)
    bild = ImageOps.exif_transpose(bild)
    if bild.mode not in ("RGB", "L"):
        bild = bild.convert("RGB")

    voll = _als_jpeg(bild, max_kante=None)
    thumb_bild = bild.copy()
    thumb_bild.thumbnail((THUMBNAIL_MAX_KANTE, THUMBNAIL_MAX_KANTE))
    thumb = _als_jpeg(thumb_bild, max_kante=None)

    return NormResult(
        typ=store.TYP_FOTO, daten=voll, endung=".jpg",
        thumbnail=thumb, thumbnail_endung=".jpg",
        aufgenommen=aufgenommen, dauer=None)


def _als_jpeg(bild, max_kante=None):
    if max_kante is not None:
        bild = bild.copy()
        bild.thumbnail((max_kante, max_kante))
    if bild.mode not in ("RGB", "L"):
        bild = bild.convert("RGB")
    puffer = io.BytesIO()
    bild.save(puffer, format="JPEG", quality=85)
    return puffer.getvalue()


# EXIF-Tag 36867 = DateTimeOriginal, 306 = DateTime (Fallback).
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


def _exif_aufnahmedatum(bild):
    """Liest das EXIF-Aufnahmedatum als ISO-8601 (PHOTO-8) — oder None.

    EXIF speichert `YYYY:MM:DD HH:MM:SS`; wir wandeln in ISO-8601. Fehlt EXIF
    oder das Feld, ist None korrekt (Fallback auf den Hinzufüge-Stempel,
    E-PHOTO-8)."""
    try:
        exif = bild.getexif()
    except Exception:
        return None
    if not exif:
        return None
    roh = exif.get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
    if not roh:
        return None
    return _exif_zeit_zu_iso(str(roh))


def _exif_zeit_zu_iso(roh):
    """`YYYY:MM:DD HH:MM:SS` → `YYYY-MM-DDTHH:MM:SS`. Ungültig → None."""
    roh = roh.strip()
    try:
        datum, zeit = roh.split(" ", 1)
        datum = datum.replace(":", "-")
        return "%sT%s" % (datum, zeit)
    except ValueError:
        return None


# ============================================================
#  Video (PHOTO-8/9)
# ============================================================

def _normalisiere_video(rohbytes, endung):
    """Video → MP4/H.264 + Poster-Frame + Dauer; Aufnahmedatum aus Container
    (PHOTO-8/9).

    E-PHOTO-9: bereits web-taugliche MP4/H.264-Eingaben werden durchgereicht
    (nicht re-encodiert). Andere Container/Codecs (HEVC/MOV) werden per ffmpeg
    nach MP4/H.264 transcodiert. Aufnahmedatum kommt aus den Container-Metadaten
    (ffprobe `creation_time`) — vor der Konvertierung gelesen.
    """
    with tempfile.TemporaryDirectory(prefix="photo-norm-") as tmp:
        eingang = os.path.join(tmp, "eingang" + (endung or ".mp4"))
        with open(eingang, "wb") as f:
            f.write(rohbytes)

        probe = _ffprobe(eingang)
        aufgenommen = _container_aufnahmedatum(probe)
        codec = _video_codec(probe)

        if endung == ".mp4" and codec == "h264":
            # E-PHOTO-9: bereits web-tauglich → Pass-through, kein Re-Encode.
            voll = rohbytes
            voll_pfad = eingang
        else:
            voll_pfad = os.path.join(tmp, "voll.mp4")
            _transcode_mp4(eingang, voll_pfad)
            with open(voll_pfad, "rb") as f:
                voll = f.read()

        dauer = _video_dauer(_ffprobe(voll_pfad))
        thumb = _poster_frame(voll_pfad, tmp)

    return NormResult(
        typ=store.TYP_VIDEO, daten=voll, endung=".mp4",
        thumbnail=thumb, thumbnail_endung=".jpg",
        aufgenommen=aufgenommen, dauer=dauer)


def _ffprobe(pfad):
    """ffprobe-JSON (streams + format) — oder {} bei Fehler/Abwesenheit."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", pfad],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("ffprobe fehlgeschlagen für %s: %s", pfad, e)
        return {}
    if out.returncode != 0:
        return {}
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return {}


def _video_codec(probe):
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream.get("codec_name")
    return None


def _video_dauer(probe):
    """Dauer in Sekunden (float) aus dem Format-Block — oder None."""
    roh = (probe.get("format") or {}).get("duration")
    if roh is None:
        return None
    try:
        return round(float(roh), 3)
    except (TypeError, ValueError):
        return None


def _container_aufnahmedatum(probe):
    """`creation_time` aus Format-/Stream-Tags als ISO-8601 (PHOTO-8) — oder None."""
    tags = (probe.get("format") or {}).get("tags") or {}
    roh = tags.get("creation_time")
    if not roh:
        for stream in probe.get("streams", []):
            roh = (stream.get("tags") or {}).get("creation_time")
            if roh:
                break
    if not roh:
        return None
    # ffmpeg liefert i. d. R. `YYYY-MM-DDTHH:MM:SS.000000Z` — bereits ISO-8601.
    return roh.strip()


def _transcode_mp4(eingang, ausgang):
    """HEVC/MOV → MP4/H.264 via ffmpeg (PHOTO-8). Hebt NormalizeError bei Fehler."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-y", "-i", eingang,
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-movflags", "+faststart", ausgang],
            capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        raise NormalizeError("Video-Transcode fehlgeschlagen: %s" % e) from e
    if out.returncode != 0 or not os.path.isfile(ausgang):
        raise NormalizeError("Video-Transcode fehlgeschlagen: %s" % out.stderr[-500:])


def _poster_frame(video_pfad, tmp):
    """Poster-Frame als JPEG-Bytes (PHOTO-9): erster Frame via ffmpeg, dann über
    Pillow auf Thumbnail-Größe gebracht. Hebt NormalizeError bei Fehler."""
    poster_pfad = os.path.join(tmp, "poster.jpg")
    try:
        out = subprocess.run(
            ["ffmpeg", "-y", "-i", video_pfad, "-frames:v", "1",
             "-q:v", "3", poster_pfad],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        raise NormalizeError("Poster-Frame fehlgeschlagen: %s" % e) from e
    if out.returncode != 0 or not os.path.isfile(poster_pfad):
        raise NormalizeError("Poster-Frame fehlgeschlagen: %s" % out.stderr[-500:])
    try:
        bild = Image.open(poster_pfad)
        bild.load()
    except Exception as e:
        raise NormalizeError("Poster-Frame nicht lesbar: %s" % e) from e
    bild.thumbnail((THUMBNAIL_MAX_KANTE, THUMBNAIL_MAX_KANTE))
    return _als_jpeg(bild)
