"""KIBuddy — Daten-IO-Helfer (SVC-5, KIBUDDY-15).

Atomar schreiben (Temp+Replace), lesen mit Fallback.
Symmetrie zu hoerspiel/data_io.py.
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


def atomic_write_text(path: str, text: str) -> None:
    """Schreibt Text atomar in path (Temp+Replace, KIBUDDY-15)."""
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp", prefix="kibuddy_write_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except OSError as e:
        raise OSError("Datei konnte nicht atomar geschrieben werden (%s): %s" % (path, e)) from e


def atomic_write_bytes(path: str, data: bytes) -> None:
    """Schreibt Bytes atomar in path (Temp+Replace) — für MP3-Audio-Cache."""
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp", prefix="kibuddy_write_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except OSError as e:
        raise OSError("Datei konnte nicht atomar geschrieben werden (%s): %s" % (path, e)) from e


def atomic_write_json(path: str, data: dict[str, Any]) -> None:
    """Schreibt data atomar als JSON in path (Temp+Replace)."""
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp", prefix="kibuddy_write_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
    except OSError as e:
        raise OSError("Datei konnte nicht atomar geschrieben werden (%s): %s" % (path, e)) from e


def write_prompt(data_root: str, prompt_text: str) -> None:
    """Schreibt den System-Prompt atomar, sichert die Vorgänger-Version (KIBUDDY-15).

    Bestehende prompt.txt wandert nach prompt.txt.bak (eine Generation,
    je PUT überschrieben — Last-Known-Good für Notfall-Rollback).
    """
    prompt_path = os.path.join(data_root, "prompt.txt")
    bak_path = os.path.join(data_root, "prompt.txt.bak")
    # Backup der alten Version (sofern vorhanden).
    if os.path.isfile(prompt_path):
        try:
            shutil.copy2(prompt_path, bak_path)
        except OSError as e:
            logger.warning("Backup von prompt.txt fehlgeschlagen: %s", e)
    atomic_write_text(prompt_path, prompt_text)


def prompt_path(data_root: str) -> str:
    return os.path.join(data_root, "prompt.txt")


def audio_dir(data_root: str) -> str:
    return os.path.join(data_root, "audio")


def audio_path(data_root: str, audio_id: str) -> str:
    return os.path.join(audio_dir(data_root), "%s.mp3" % audio_id)
