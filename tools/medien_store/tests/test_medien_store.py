"""Domain-neutrale Tests der tools.medien_store-Library (T806/AC4).

Kein photo/-Bezug. Testet: normalize JPEG/HEIC/MP4, ingest + Index,
load, delete, auto_delete TTL=0 no-op, ID-Vergabe stabil.
"""

import io
import os
import shutil
import sys
from datetime import UTC, datetime, timedelta

import pillow_heif
import pytest
from PIL import Image

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

pillow_heif.register_heif_opener()

from tools.medien_store import (  # noqa: E402
    TYP_FOTO,
    TYP_VIDEO,
    NormalizeError,
    auto_delete,
    delete,
    ingest,
    load,
    normalisiere,
    serve_pfad,
    thumb_pfad,
)
from tools.medien_store import store as store_mod  # noqa: E402
from tools.medien_store.normalize import THUMBNAIL_MAX_KANTE  # noqa: E402

HAT_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
ffmpeg_noetig = pytest.mark.skipif(not HAT_FFMPEG, reason="ffmpeg/ffprobe nicht verfuegbar")


# ============================================================
#  Fixtures
# ============================================================

def _jpeg_bytes(farbe=(180, 120, 60), groesse=(64, 48), exif_datum=None):
    bild = Image.new("RGB", groesse, farbe)
    puffer = io.BytesIO()
    if exif_datum is not None:
        exif = Image.Exif()
        exif[36867] = exif_datum
        bild.save(puffer, format="JPEG", exif=exif)
    else:
        bild.save(puffer, format="JPEG")
    return puffer.getvalue()


def _heic_bytes(farbe=(40, 160, 90), groesse=(64, 48)):
    bild = Image.new("RGB", groesse, farbe)
    puffer = io.BytesIO()
    bild.save(puffer, format="HEIF")
    return puffer.getvalue()


def _mp4_bytes(tmp_path, dauer="1", creation_time=None):
    """Erzeugt ein kurzes MP4/H.264 via ffmpeg."""
    pfad = str(tmp_path / "test.mp4")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           "testsrc=duration=%s:size=64x48:rate=5" % dauer,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "mp4"]
    if creation_time is not None:
        cmd += ["-metadata", "creation_time=%s" % creation_time]
    cmd.append(pfad)
    import subprocess
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError("ffmpeg-Fixture fehlgeschlagen: %s" % out.stderr[-400:])
    with open(pfad, "rb") as f:
        return f.read()


# ============================================================
#  normalize — Foto
# ============================================================

def test_normalize_jpeg_liefert_jpeg():
    """normalize: JPEG-Eingabe -> JPEG-Ausgabe mit Thumbnail."""
    norm = normalisiere(_jpeg_bytes(), "foto.jpg")
    assert norm.typ == TYP_FOTO
    assert norm.endung == ".jpg"
    bild = Image.open(io.BytesIO(norm.daten))
    assert bild.format == "JPEG"
    thumb = Image.open(io.BytesIO(norm.thumbnail))
    assert thumb.format == "JPEG"


def test_normalize_jpeg_thumbnail_max_kante():
    """normalize: Thumbnail ist nicht groesser als THUMBNAIL_MAX_KANTE."""
    norm = normalisiere(_jpeg_bytes(groesse=(1200, 900)), "gross.jpg")
    thumb = Image.open(io.BytesIO(norm.thumbnail))
    assert max(thumb.size) <= THUMBNAIL_MAX_KANTE


def test_normalize_heic_zu_jpeg():
    """normalize: HEIC-Eingabe wird nach JPEG konvertiert."""
    norm = normalisiere(_heic_bytes(), "IMG_0001.HEIC")
    assert norm.typ == TYP_FOTO
    assert norm.endung == ".jpg"
    bild = Image.open(io.BytesIO(norm.daten))
    assert bild.format == "JPEG"


def test_normalize_exif_aufnahmedatum():
    """normalize: EXIF-Aufnahmedatum wird extrahiert und als ISO-8601 geliefert."""
    daten = _jpeg_bytes(exif_datum="2024:12:24 18:30:00")
    norm = normalisiere(daten, "foto.jpg")
    assert norm.aufgenommen == "2024-12-24T18:30:00"


def test_normalize_ohne_exif_kein_aufnahmedatum():
    """normalize: ohne EXIF bleibt aufgenommen==None."""
    norm = normalisiere(_jpeg_bytes(), "foto.jpg")
    assert norm.aufgenommen is None


def test_normalize_leeres_medium_wirft():
    """normalize: leere Bytes -> NormalizeError."""
    with pytest.raises(NormalizeError):
        normalisiere(b"", "foto.jpg")


def test_normalize_unbekanntes_format_wirft():
    """normalize: unbekannte Endung -> NormalizeError."""
    with pytest.raises(NormalizeError):
        normalisiere(b"garbage", "datei.xyz")


# ============================================================
#  normalize — Video (ffmpeg erforderlich)
# ============================================================

@ffmpeg_noetig
def test_normalize_mp4_h264_pass_through(tmp_path):
    """normalize: bereits web-taugliches MP4/H.264 wird durchgereicht (pass-through)."""
    roh = _mp4_bytes(tmp_path)
    norm = normalisiere(roh, "clip.mp4")
    assert norm.typ == TYP_VIDEO
    assert norm.endung == ".mp4"
    assert norm.daten == roh


@ffmpeg_noetig
def test_normalize_mp4_poster_frame(tmp_path):
    """normalize: MP4-Ingest liefert einen Poster-Frame als JPEG."""
    norm = normalisiere(_mp4_bytes(tmp_path), "clip.mp4")
    poster = Image.open(io.BytesIO(norm.thumbnail))
    assert poster.format == "JPEG"
    assert norm.dauer is not None
    assert norm.dauer > 0


# ============================================================
#  ingest + Index
# ============================================================

def test_ingest_schreibt_medium_und_thumbnail(tmp_path):
    """ingest: schreibt Vollmedium, Thumbnail und Index-Eintrag."""
    lib = str(tmp_path / "lib")
    medium = ingest(lib, _jpeg_bytes(), "foto.jpg")
    assert medium.typ == TYP_FOTO
    assert os.path.isfile(os.path.join(lib, medium.datei))
    assert os.path.isfile(os.path.join(lib, medium.thumbnail))
    medien = load(lib)
    assert len(medien) == 1
    assert medien[0].id == medium.id


def test_ingest_atomar_rollback_bei_thumbnail_fehler(tmp_path, monkeypatch):
    """ingest: scheitert das Thumbnail-Schreiben, bleibt kein Medium und kein Index."""
    lib = str(tmp_path / "lib")
    echtes_schreiben = store_mod._atomar_schreiben
    aufrufe = {"n": 0}

    def flaky(ziel_pfad, daten):
        aufrufe["n"] += 1
        if aufrufe["n"] == 2:
            raise store_mod.StoreError("simulierter Fehler")
        return echtes_schreiben(ziel_pfad, daten)

    monkeypatch.setattr(store_mod, "_atomar_schreiben", flaky)
    with pytest.raises(store_mod.StoreError):
        ingest(lib, _jpeg_bytes(), "foto.jpg")

    assert load(lib) == []
    rest = list(os.listdir(lib)) if os.path.isdir(lib) else []
    assert not any(f.endswith(".jpg") for f in rest)


def test_ingest_erzeugt_thumbnail_datei(tmp_path):
    """ingest: die Thumbnail-Datei existiert nach dem Ingest."""
    lib = str(tmp_path / "lib")
    medium = ingest(lib, _jpeg_bytes(), "foto.jpg")
    thumb = thumb_pfad(lib, medium.id)
    assert thumb is not None
    assert os.path.isfile(thumb)
    bild = Image.open(thumb)
    assert bild.format == "JPEG"


# ============================================================
#  load
# ============================================================

def test_load_leeres_verzeichnis(tmp_path):
    """load: fehlt die library.json, kommt eine leere Liste zurueck."""
    lib = str(tmp_path / "lib")
    assert load(lib) == []


def test_load_kaputtes_json(tmp_path):
    """load: kaputtes JSON -> leere Liste (kein Crash)."""
    lib = str(tmp_path / "lib")
    os.makedirs(lib)
    with open(os.path.join(lib, store_mod.INDEX_DATEI), "w", encoding="utf-8") as f:
        f.write("KEIN JSON")
    assert load(lib) == []


# ============================================================
#  delete
# ============================================================

def test_loesche_entfernt_alle_drei(tmp_path):
    """delete: entfernt Medium, Thumbnail und Index-Eintrag."""
    lib = str(tmp_path / "lib")
    medium = ingest(lib, _jpeg_bytes(), "foto.jpg")
    assert serve_pfad(lib, medium.id) is not None

    assert delete(lib, medium.id) is True
    assert load(lib) == []
    assert serve_pfad(lib, medium.id) is None
    assert thumb_pfad(lib, medium.id) is None
    rest = [f for f in os.listdir(lib) if f != store_mod.INDEX_DATEI]
    assert rest == []


def test_loesche_unbekannte_id_false(tmp_path):
    """delete: unbekannte id -> False (kein Fehler)."""
    lib = str(tmp_path / "lib")
    assert delete(lib, "foto-99") is False


# ============================================================
#  ID-Vergabe
# ============================================================

def test_id_vergabe_stabil(tmp_path):
    """_neue_id: vergibt stabile, kollisionsfreie ids ab foto-01."""
    lib = str(tmp_path / "lib")
    m1 = ingest(lib, _jpeg_bytes(), "a.jpg")
    m2 = ingest(lib, _jpeg_bytes(), "b.jpg")
    m3 = ingest(lib, _jpeg_bytes(), "c.jpg")
    assert m1.id == "foto-01"
    assert m2.id == "foto-02"
    assert m3.id == "foto-03"


def test_id_vergabe_luecke_wird_gefuellt(tmp_path):
    """_neue_id: nach Loeschen eines Eintrags wird die Luecke mit neuer id gefuellt."""
    lib = str(tmp_path / "lib")
    m1 = ingest(lib, _jpeg_bytes(), "a.jpg")
    m2 = ingest(lib, _jpeg_bytes(), "b.jpg")
    delete(lib, m1.id)  # loescht foto-01
    m3 = ingest(lib, _jpeg_bytes(), "c.jpg")
    assert m3.id == "foto-01"  # Luecke wird gefuellt
    assert m2.id == "foto-02"


# ============================================================
#  auto_delete
# ============================================================

def test_auto_delete_ttl_null_no_op(tmp_path):
    """auto_delete: TTL=0 loescht nie, egal wie alt das Medium ist."""
    lib = str(tmp_path / "lib")
    now = datetime(2020, 1, 1, tzinfo=UTC)
    ingest(lib, _jpeg_bytes(), "a.jpg", now=now)
    entfernt = auto_delete(lib, 0, now=now + timedelta(days=99999))
    assert entfernt == []
    assert len(load(lib)) == 1


def test_auto_delete_vor_ttl_bleibt(tmp_path):
    """auto_delete: Medium juenger als TTL bleibt erhalten."""
    lib = str(tmp_path / "lib")
    now = datetime(2026, 6, 1, tzinfo=UTC)
    ingest(lib, _jpeg_bytes(), "a.jpg", now=now)
    entfernt = auto_delete(lib, 7, now=now + timedelta(days=3))
    assert entfernt == []
    assert len(load(lib)) == 1


def test_auto_delete_nach_ttl_entfernt(tmp_path):
    """auto_delete: Medium aelter als TTL wird entfernt (Datei + Index)."""
    lib = str(tmp_path / "lib")
    now = datetime(2026, 6, 1, tzinfo=UTC)
    medium = ingest(lib, _jpeg_bytes(), "a.jpg", now=now)
    entfernt = auto_delete(lib, 7, now=now + timedelta(days=10))
    assert entfernt == [medium.id]
    assert load(lib) == []
    assert serve_pfad(lib, medium.id) is None


# ============================================================
#  extra_felder (Konsumenten-Erweiterung)
# ============================================================

def test_ingest_extra_felder_im_index(tmp_path):
    """ingest: extra_felder werden in den Index-Eintrag geschrieben."""
    lib = str(tmp_path / "lib")
    ingest(lib, _jpeg_bytes(), "foto.jpg", in_library=False)
    import json
    index_pfad = os.path.join(lib, store_mod.INDEX_DATEI)
    with open(index_pfad, encoding="utf-8") as f:
        raw = json.load(f)
    eintrag = raw["medien"][0]
    assert eintrag["in_library"] is False
