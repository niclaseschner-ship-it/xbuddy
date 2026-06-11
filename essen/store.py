"""Essens-Buddy — persistenter Store für Wünsche und Gerichte (ESSEN-7/20).

Umsetzt: atomares Schreiben (DCOMP-4, Temp-Datei + os.replace), Last-Known-Good
(DCOMP-3), Reload-on-Read (ESSEN-20) — jede Lese-Operation liest frisch von Disk.

**V1 #653 (ESSEN-7) — Trennung nach klasse:**
- `wuensche.json`       → klasse=wunsch
- `einkaufsliste.json`  → klasse=einkauf
- `zaehler.json`        → globaler Quellen-Zähler (klasse-übergreifend)

Migration (Alt-Stand): existierende `wuensche.json` mit `zaehler`-Schlüssel im
selben File wird weiter gelesen; der Zähler wird beim Lesen mit zurückgegeben,
sodass `main.py` ihn beim ersten Schreiben nach `zaehler.json` heben kann.
Alt-Einträge ohne `klasse` werden vom Reader als `klasse='wunsch'`,
`abgehakt=false` aufgefüllt (ESSEN-4 Migrations-Regel).

Öffentliche API:
  lade_wuensche(path, snapshot)         → dict {wuensche, zaehler?}
  speichere_wuensche(path, d)           → None (atomar)
  lade_einkaufsliste(path, snapshot)    → dict {wuensche}
  speichere_einkaufsliste(path, d)      → None (atomar)
  lade_zaehler(path, snapshot)          → dict {kind, eltern}
  speichere_zaehler(path, d)            → None (atomar)
  lade_gerichte(path)                   → dict {gerichte, zaehler}
  speichere_gerichte(path, d)           → None (atomar)
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


# ── Migrations-Helfer ─────────────────────────────────────────────────────

def _sanitize_wunsch_eintrag(w):
    """Füllt fehlende V1-#653-Felder mit Defaults auf (ESSEN-4 Migrations-Regel).

    Alt-Einträge ohne `klasse` werden als `klasse='wunsch'` gelesen,
    `abgehakt` Default `false`. Persistente Felder bleiben unverändert.
    """
    out = dict(w)
    out.setdefault("klasse",   "wunsch")
    out.setdefault("abgehakt", False)
    return out


# ── Wunsch-Store (klasse=wunsch, ESSEN-7) ─────────────────────────────────

_WUENSCHE_LEER = {"wuensche": []}


def lade_wuensche(path, snapshot=None):
    """Lädt die Wunsch-Liste (klasse=wunsch) frisch von Disk (ESSEN-20).

    Bei kaputtem/fehlendem Read: wenn `snapshot` gesetzt (Last-Known-Good,
    DCOMP-3) → Snapshot zurück; sonst Leer-Zustand (ESSEN-7, Initialzustand).

    Migration: ein Alt-File mit `zaehler`-Schlüssel wird gelesen; der Zähler
    bleibt im Result-Dict erhalten (`zaehler`-Key), damit der Aufrufer ihn
    nach `zaehler.json` heben kann. Alt-Einträge ohne `klasse` werden als
    `klasse='wunsch'` ergänzt (ESSEN-4 Migrations-Regel).
    """
    daten = _lade_json(path)
    if daten is None or not isinstance(daten, dict):
        if snapshot is not None:
            logger.debug("lade_wuensche: Datei nicht lesbar — Last-Known-Good")
            return snapshot
        logger.info("lade_wuensche: Datei fehlt/kaputt (%s) — leerer Zustand", path)
        return copy.deepcopy(_WUENSCHE_LEER)

    roh_wuensche = daten.get("wuensche", [])
    wuensche = [_sanitize_wunsch_eintrag(w) for w in roh_wuensche]
    result = {"wuensche": wuensche}
    # Migration: Alt-Format mit zaehler im selben File. Wir reichen den
    # Zähler zum Aufrufer durch, damit main.py ihn nach zaehler.json heben kann.
    if "zaehler" in daten:
        result["zaehler"] = daten["zaehler"]
    return result


def speichere_wuensche(path, daten):
    """Schreibt die Wunsch-Liste (klasse=wunsch) atomar (DCOMP-4, ESSEN-20).

    Erwartet `daten = {"wuensche": [...]}`. Wenn `zaehler` im dict liegt,
    wird er NICHT mitgeschrieben — er gehört nach zaehler.json (ESSEN-7).
    """
    nur_wuensche = {"wuensche": daten.get("wuensche", [])}
    _atomar_schreiben(path, nur_wuensche)


# ── Einkaufsliste-Store (klasse=einkauf, ESSEN-7) ─────────────────────────

_EINKAUFSLISTE_LEER = {"wuensche": []}


def lade_einkaufsliste(path, snapshot=None):
    """Lädt die Einkaufsliste (klasse=einkauf) frisch von Disk (ESSEN-20).

    Initialzustand: leer. Die Datei wird erst beim ersten POST mit
    `klasse=einkauf` angelegt (ESSEN-7).
    """
    daten = _lade_json(path)
    if daten is None or not isinstance(daten, dict):
        if snapshot is not None:
            logger.debug("lade_einkaufsliste: Datei nicht lesbar — Last-Known-Good")
            return snapshot
        logger.info("lade_einkaufsliste: Datei fehlt/kaputt (%s) — leerer Zustand", path)
        return copy.deepcopy(_EINKAUFSLISTE_LEER)
    roh = daten.get("wuensche", [])
    wuensche = [_sanitize_wunsch_eintrag(w) for w in roh]
    # Einträge ohne klasse in einkaufsliste.json setzen wir auf klasse='einkauf'.
    for w in wuensche:
        if w.get("klasse") not in ("wunsch", "einkauf"):
            w["klasse"] = "einkauf"
    return {"wuensche": wuensche}


def speichere_einkaufsliste(path, daten):
    """Schreibt die Einkaufsliste atomar (DCOMP-4, ESSEN-20)."""
    nur_wuensche = {"wuensche": daten.get("wuensche", [])}
    _atomar_schreiben(path, nur_wuensche)


# ── Zähler-Store (klasse-übergreifend, ESSEN-5/ESSEN-7) ───────────────────

_ZAEHLER_LEER = {"kind": 0, "eltern": 0}


def lade_zaehler(path, snapshot=None):
    """Lädt den globalen Quellen-Zähler frisch von Disk (ESSEN-5/ESSEN-7).

    Initialzustand: `{"kind": 0, "eltern": 0}`. Migration: fehlt das File,
    leitet `main.py` die Stände bei Bedarf aus den Max-IDs der vorhandenen
    Klasse-Files ab (ESSEN-5).
    """
    daten = _lade_json(path)
    if daten is None or not isinstance(daten, dict):
        if snapshot is not None:
            logger.debug("lade_zaehler: Datei nicht lesbar — Last-Known-Good")
            return snapshot
        return copy.deepcopy(_ZAEHLER_LEER)
    return {
        "kind":   int(daten.get("kind",   0) or 0),
        "eltern": int(daten.get("eltern", 0) or 0),
    }


def speichere_zaehler(path, daten):
    """Schreibt den globalen Zähler atomar (DCOMP-4)."""
    _atomar_schreiben(path, {
        "kind":   int(daten.get("kind",   0) or 0),
        "eltern": int(daten.get("eltern", 0) or 0),
    })


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
