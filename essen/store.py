"""Essens-Buddy — persistenter Store für Wünsche und Gerichte (ESSEN-7/20).

Umsetzt: atomares Schreiben (DCOMP-4, Temp-Datei + os.replace), Last-Known-Good
(DCOMP-3), Reload-on-Read (ESSEN-20) — jede Lese-Operation liest frisch von Disk.

Öffentliche API:
  lade_wuensche(path)         → dict {wuensche, zaehler}
  speichere_wuensche(path, d) → None (atomar)
  lade_gerichte(path)         → dict {gerichte, zaehler}
  speichere_gerichte(path, d) → None (atomar)
"""

import contextlib
import copy
import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# ── Atomares Schreiben (DCOMP-4) ──────────────────────────────────────────

def _atomar_schreiben(path, daten):
    """Schreibt `daten` JSON-atomar auf `path` (DCOMP-4).

    Strategie: Temp-Datei im Zielverzeichnis anlegen, JSON hineinschreiben,
    dann os.replace() — auf demselben Dateisystem, daher atomar.
    """
    zieldir = os.path.dirname(os.path.abspath(path))
    os.makedirs(zieldir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=zieldir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Temp-Datei aufräumen, falls vorhanden.
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _lade_json(path):
    """Liest JSON von `path`. FileNotFoundError → None; ParseError → None + Warnung."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("JSON-Datei nicht lesbar (%s): %s", path, e)
        return None


# ── Wunsch-Store ──────────────────────────────────────────────────────────

_WUENSCHE_LEER = {"wuensche": [], "zaehler": {"kind": 0, "eltern": 0}}


def lade_wuensche(path, snapshot=None):
    """Lädt die Wunsch-Liste frisch von Disk (Reload-on-Read, ESSEN-20).

    Bei kaputtem/fehlendem Read: wenn `snapshot` gesetzt (Last-Known-Good,
    DCOMP-3) → Snapshot zurück; sonst Leer-Zustand (ESSEN-7, Initialzustand).
    """
    daten = _lade_json(path)
    if daten is None or not isinstance(daten, dict):
        if snapshot is not None:
            logger.debug("lade_wuensche: Datei nicht lesbar — Last-Known-Good")
            return snapshot
        logger.info("lade_wuensche: Datei fehlt/kaputt (%s) — leerer Zustand", path)
        return copy.deepcopy(_WUENSCHE_LEER)
    # Sanitize: fehlende Felder mit Defaults auffüllen.
    wuensche = daten.get("wuensche", [])
    zaehler = daten.get("zaehler", {"kind": 0, "eltern": 0})
    return {"wuensche": wuensche, "zaehler": zaehler}


def speichere_wuensche(path, daten):
    """Schreibt die Wunsch-Liste atomar (DCOMP-4, ESSEN-20)."""
    _atomar_schreiben(path, daten)


# ── Gerichte-Store ────────────────────────────────────────────────────────

_GERICHTE_LEER = {"gerichte": [], "zaehler": 0}


def lade_gerichte(path, snapshot=None):
    """Lädt den Gerichte-Katalog frisch von Disk (Reload-on-Read, ESSEN-20).

    Initialzustand: leer (ESSEN-14). Last-Known-Good wenn Datei defekt (DCOMP-3).
    """
    daten = _lade_json(path)
    if daten is None or not isinstance(daten, dict):
        if snapshot is not None:
            logger.debug("lade_gerichte: Datei nicht lesbar — Last-Known-Good")
            return snapshot
        logger.info("lade_gerichte: Datei fehlt/kaputt (%s) — leerer Zustand", path)
        return copy.deepcopy(_GERICHTE_LEER)
    gerichte = daten.get("gerichte", [])
    zaehler = daten.get("zaehler", 0)
    return {"gerichte": gerichte, "zaehler": zaehler}


def speichere_gerichte(path, daten):
    """Schreibt den Gerichte-Katalog atomar (DCOMP-4, ESSEN-19)."""
    _atomar_schreiben(path, daten)
