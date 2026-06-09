"""Routine-Buddy — JSON-I/O-Helpers (DCOMP-4, ROUTINE-8/12, #431).

Zwei Helpers für das wiederkehrende Lese-mit-Fallback- und
Atomar-Schreiben-Pattern innerhalb der routine/-Komponente.

CLAUDE.md §6: dieselbe Logik nur einmal.
"""

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def read_json_or_empty(path: str | Path) -> dict[str, Any]:
    """Liest eine JSON-Datei und gibt ein Dict zurück. Fehlt sie → {}.

    Fehlertoleranz (CONFIG-4):
      - Datei nicht vorhanden → {} (kein Fehler, kein Log)
      - OSError oder JSONDecodeError → {} + WARNING-Log mit Pfad
      - Inhalt kein Dict → {}

    Diese Funktion wirft nie eine Exception.
    """
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


def atomic_write_json(path: str | Path, data: dict[str, Any]) -> None:
    """Schreibt data atomar als JSON in path (DCOMP-4: Temp+Replace).

    Schreibt erst in eine temporäre Datei im selben Verzeichnis,
    dann atomares os.replace → kein halb-geschriebener Stand für
    gleichzeitige Lese-Zugriffe.

    Verzeichnis wird bei Bedarf angelegt (os.makedirs).
    Schlägt das Schreiben fehl → OSError mit erklärender Meldung.
    """
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp",
                                        prefix="routine_write_")
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
