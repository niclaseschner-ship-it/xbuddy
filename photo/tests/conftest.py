"""Gemeinsame Test-Fixtures der Photo-Buddy-Suite (PHOTO-23).

Die Suite läuft OHNE Netz. Test-Mediendateien werden **programmatisch** erzeugt
(Pillow für JPEG/HEIC, ffmpeg für MP4/H.264 und HEVC/MOV) statt Binärdateien zu
committen — so bleibt das Repo binärfrei und die Fixtures deterministisch
(Contract: Fixtures bevorzugt programmatisch).

ffmpeg/ffprobe sind eine System-Dependency (PHOTO-8/9); Tests, die sie brauchen,
überspringen sich selbst, wenn das Binary fehlt.
"""

import io
import os
import shutil
import subprocess
import sys

import pillow_heif
import pytest
from PIL import Image

# Repo-Wurzel auf den Importpfad — die Suite importiert `photo` als Paket.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

pillow_heif.register_heif_opener()

HAT_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
ffmpeg_noetig = pytest.mark.skipif(not HAT_FFMPEG, reason="ffmpeg/ffprobe nicht verfügbar")


# ============================================================
#  Programmatische Foto-Fixtures (PHOTO-8)
# ============================================================

def _jpeg_bytes(farbe=(180, 120, 60), groesse=(64, 48), exif_datum=None):
    """Ein kleines JPEG, optional mit EXIF-DateTimeOriginal (PHOTO-8)."""
    bild = Image.new("RGB", groesse, farbe)
    puffer = io.BytesIO()
    if exif_datum is not None:
        exif = Image.Exif()
        exif[36867] = exif_datum  # DateTimeOriginal: "YYYY:MM:DD HH:MM:SS"
        bild.save(puffer, format="JPEG", exif=exif)
    else:
        bild.save(puffer, format="JPEG")
    return puffer.getvalue()


def _heic_bytes(farbe=(40, 160, 90), groesse=(64, 48)):
    """Ein kleines HEIC (über pillow-heif) — der iPhone-„als Datei"-Pfad (PHOTO-8)."""
    bild = Image.new("RGB", groesse, farbe)
    puffer = io.BytesIO()
    bild.save(puffer, format="HEIF")
    return puffer.getvalue()


@pytest.fixture
def jpeg_bytes():
    return _jpeg_bytes


@pytest.fixture
def heic_bytes():
    return _heic_bytes


# ============================================================
#  Programmatische Video-Fixtures (PHOTO-8) — via ffmpeg
# ============================================================

def _erzeuge_video(pfad, codec, container_args, dauer="1", creation_time=None):
    """Erzeugt ein kurzes Test-Video mit ffmpeg (testsrc-Pattern)."""
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           "testsrc=duration=%s:size=64x48:rate=5" % dauer,
           "-c:v", codec, "-pix_fmt", "yuv420p"]
    if creation_time is not None:
        cmd += ["-metadata", "creation_time=%s" % creation_time]
    cmd += [*container_args, pfad]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError("ffmpeg-Fixture fehlgeschlagen: %s" % out.stderr[-400:])
    with open(pfad, "rb") as f:
        return f.read()


@pytest.fixture
def mp4_h264_bytes(tmp_path):
    """Bereits web-taugliches MP4/H.264 (E-PHOTO-9 Pass-through-Pfad)."""
    def _make(dauer="1", creation_time=None):
        pfad = str(tmp_path / "h264.mp4")
        return _erzeuge_video(pfad, "libx264", ["-f", "mp4"], dauer, creation_time)
    return _make


@pytest.fixture
def hevc_mov_bytes(tmp_path):
    """HEVC/MOV — der iPhone-„als Datei"-Pfad, muss transcodiert werden (PHOTO-8)."""
    def _make(dauer="1", creation_time=None):
        pfad = str(tmp_path / "hevc.mov")
        return _erzeuge_video(pfad, "libx265", ["-tag:v", "hvc1", "-f", "mov"],
                              dauer, creation_time)
    return _make
