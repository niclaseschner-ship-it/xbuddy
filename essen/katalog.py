"""Essens-Buddy — Katalog-Ladelogik (ESSEN-12/13/14).

Zuständig für:
  - Repo-Default `katalog.default.json` für die drei Lebensmittel-Kategorien
    (ESSEN-12).
  - Per-Instanz-Override `katalog.json`: ersetzt den Default vollständig, kein
    Merge (ESSEN-13, Familie-3-Probe).
  - Last-Known-Good beim Override (DCOMP-3): kaputte Override-Datei → zuletzt
    erfolgreich geladener Stand; nie ein Override → Repo-Default.
  - Gerichte-Katalog wird separat über store.py geladen (ESSEN-14) — dieser
    Modul liefert nur die drei Lebensmittel-Kategorien.

Öffentliche API:
  lade_lebensmittel(katalog_file, default_file, snapshot=None)
    → dict { "obst_gemuese": [...], "brotbelag": [...], "sonstiges": [...] }
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

KATEGORIEN = ("obst_gemuese", "brotbelag", "sonstiges")


def _lade_katalog_datei(path):
    """Liest und parst eine Katalog-JSON-Datei. None bei Fehler/Fehlen."""
    try:
        with open(path, encoding="utf-8") as f:
            daten = json.load(f)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Katalog-Datei nicht lesbar (%s): %s", path, e)
        return None
    if not isinstance(daten, dict) or "kategorien" not in daten:
        logger.warning("Katalog-Datei hat kein 'kategorien'-Objekt (%s)", path)
        return None
    return daten["kategorien"]


def lade_lebensmittel(katalog_file, default_file, snapshot=None):
    """Lädt den Lebensmittel-Katalog (ESSEN-12/13/20, Reload-on-Read).

    Wenn Override vorhanden und gültig: Override nehmen.
    Wenn Override fehlt: Default nehmen (ESSEN-13: Fehlen = OK, Default gilt).
    Wenn Override kaputt: snapshot (Last-Known-Good, DCOMP-3); kein snapshot →
    Default (ESSEN-13: kein je erfolgreicher Override → Repo-Default).

    Gibt dict mit Schlüsseln obst_gemuese, brotbelag, sonstiges zurück.
    """
    # Override-Versuch (ESSEN-13).
    override = None
    if os.path.exists(katalog_file):
        override = _lade_katalog_datei(katalog_file)
        if override is None:
            # Datei existiert, aber kaputt → Last-Known-Good (DCOMP-3).
            if snapshot is not None:
                logger.info("Lebensmittel-Override kaputt (%s) — Last-Known-Good", katalog_file)
                return snapshot
            # Nie erfolgreich gelesen → auf Default fallen (ESSEN-13).
            logger.info(
                "Lebensmittel-Override kaputt (%s), kein vorheriger Stand — Default",
                katalog_file)
        else:
            logger.debug("Lebensmittel-Override geladen: %s", katalog_file)
    # Override fehlt oder override ist None (und snapshot auch) → Default.
    quell_daten = override if override is not None else _lade_katalog_datei(default_file)
    if quell_daten is None:
        logger.warning("Lebensmittel-Default nicht ladbar (%s) — leerer Katalog", default_file)
        quell_daten = {}

    # Normalisiere auf die drei bekannten Kategorien.
    ergebnis = {}
    for kat in KATEGORIEN:
        rohitems = quell_daten.get(kat, [])
        items = []
        for item in rohitems:
            if not isinstance(item, dict):
                continue
            items.append({
                "id":        str(item.get("id", "")),
                "label":     str(item.get("label", "")),
                "bild_ref":  str(item.get("bild_ref", "")),
                "kategorie": kat,
            })
        ergebnis[kat] = items
    return ergebnis
