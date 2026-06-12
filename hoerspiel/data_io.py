"""Hörspiel-Buddy — Daten-IO-Helfer (DCOMP-4, HSP-15/HSP-16).

Atomar schreiben (Temp+Replace), lesen mit Fallback, Datei kopieren — alles,
was `album_builder.py` und `main.py` mehrfach brauchen, lebt hier in einer
Datei. Symmetrie zu `routine/_jsonio.py`.
"""

import contextlib
import json
import logging
import os
import shutil
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def read_json_or_empty(path: str) -> dict[str, Any]:
    """Liest eine JSON-Datei und gibt ein Dict zurück. Fehlt sie → {}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("JSON-Datei nicht lesbar (%s): %s", path, e)
        return {}


def read_text_or_empty(path: str) -> str:
    """Liest eine Text-Datei und gibt ihren Inhalt zurück. Fehlt sie → ''."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except OSError as e:
        logger.warning("Text-Datei nicht lesbar (%s): %s", path, e)
        return ""


def atomic_write_json(path: str, data: dict[str, Any]) -> None:
    """Schreibt data atomar als JSON in path (DCOMP-4: Temp+Replace)."""
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp",
                                        prefix="hoerspiel_write_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except OSError as e:
        raise OSError(
            "Datei konnte nicht atomar geschrieben werden (%s): %s" % (path, e)) from e


def atomic_write_text(path: str, text: str) -> None:
    """Schreibt Text atomar in path (DCOMP-4: Temp+Replace)."""
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp",
                                        prefix="hoerspiel_write_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except OSError as e:
        raise OSError(
            "Datei konnte nicht atomar geschrieben werden (%s): %s" % (path, e)) from e


def atomic_write_bytes(path: str, data: bytes) -> None:
    """Schreibt Bytes atomar in path (DCOMP-4: Temp+Replace) — für MP3-Assets."""
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp",
                                        prefix="hoerspiel_write_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except OSError as e:
        raise OSError(
            "Datei konnte nicht atomar geschrieben werden (%s): %s" % (path, e)) from e


def append_text_atomic(path: str, addendum: str) -> None:
    """Hängt addendum an die Datei an, ersetzt atomar (DCOMP-4, HSP-16).

    Liest den aktuellen Inhalt, hängt addendum an, schreibt das Ganze über
    Temp+Replace zurück. Damit bleibt eine parallel laufende `GET
    /folgen-historie`-Abfrage konsistent — sie sieht entweder den Stand
    davor oder den Stand danach, nie eine halbe Datei.
    """
    existing = read_text_or_empty(path)
    atomic_write_text(path, existing + addendum)


def copy_into(dest_path: str, src_path: str) -> None:
    """Kopiert src nach dest atomar (Temp im Ziel-Verzeichnis + Replace)."""
    verzeichnis = os.path.dirname(os.path.abspath(dest_path))
    os.makedirs(verzeichnis, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp",
                                    prefix="hoerspiel_copy_")
    os.close(fd)
    try:
        shutil.copyfile(src_path, tmp_path)
        os.replace(tmp_path, dest_path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
