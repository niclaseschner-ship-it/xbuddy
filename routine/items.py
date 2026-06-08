"""Routine-Buddy — Items-API-Logik (ROUTINE-14, #354).

POST/PUT/DELETE /api/v1/routine/items für zwei Herkunfts-Typen:
  default  — persistent in routine.json (Daten-Konfig, ROUTINE-12)
  einmalig — flüchtig im Tages-State (routine_store.json, ROUTINE-8/6)

ROUTINE-5: stabile, herkunfts-eindeutige IDs.
  default  → ID wird aus label slugifiziert (URL-safe, keine Kollision mit einmalig:)
  einmalig → ID-Präfix einmalig:, kollidiert nie mit default-ID

ROUTINE-6: einmalig-Punkte nach Tageswechsel automatisch weg.
  Sie liegen im Tages-State-Block (store["tag"]["einmalig"]) und werden
  beim Tageswechsel zusammen mit dem Abhak-Zustand verworfen.

ROUTINE-19: max. 8 Punkte — POST liefert HTTP 400 + Fehlermeldung wenn ≥8.
  Zählung: default-Items aus routine.json + einmalig-Items von heute.

Atomar schreiben (DCOMP-4): default-Pfad wie config.write_data (Temp+Replace);
  einmalig-Pfad ebenso (eigene atomic_write-Hilfsfunktion hier).
  Kein Teil-Write: Validierung VOR dem ersten Schreib-Byte (ROUTINE-14, AC2).

Nur diese Funktionen schreiben die Items (APP-3, ROUTINE-14).
"""

import contextlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Maximale Anzahl sichtbarer Punkte (ROUTINE-19)
MAX_ITEMS = 8


class ItemsError(Exception):
    """Fachlicher Fehler bei der Items-Schreib-API (ROUTINE-14)."""


# ============================================================
#  Hilfsfunktionen
# ============================================================

def _slug(text):
    """Erzeugt eine stabile, URL-safe ID aus einem Label (ROUTINE-5).

    Lowercase, nur alphanumerisch + Bindestrich, mehrfache Bindestriche
    kollabiert, führende/abschließende Bindestriche entfernt.
    """
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9ÄÖÜäöüß]+", "-", s)
    # Umlaute/Eszett normalisieren
    s = (s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
          .replace("Ä", "ae").replace("Ö", "oe").replace("Ü", "ue")
          .replace("ß", "ss"))
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s or "item"


def _make_default_id(label, existing_ids):
    """Erzeugt eine stabile, eindeutige default-ID (ROUTINE-5).

    Basis: _slug(label). Kollision mit vorhandener ID → -2, -3, …
    """
    base = _slug(label)
    candidate = base
    n = 2
    while candidate in existing_ids:
        candidate = "%s-%d" % (base, n)
        n += 1
    return candidate


def _atomic_write_json(path, data):
    """Schreibt data atomar als JSON in path (DCOMP-4: Temp+Replace)."""
    verzeichnis = os.path.dirname(os.path.abspath(path))
    os.makedirs(verzeichnis, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=verzeichnis, suffix=".tmp",
                                        prefix="items_write_")
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


def _load_routine_json(data_path):
    """Lädt routine.json. Fehlt sie → leeres Dict (CONFIG-4)."""
    try:
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("routine.json nicht lesbar (%s): %s", data_path, e)
        return {}


def _load_store(store_path):
    """Lädt routine_store.json. Fehlt sie → leeres Dict (ROUTINE-8)."""
    try:
        with open(store_path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("routine_store.json nicht lesbar (%s): %s", store_path, e)
        return {}


def _heute_str(zeitzone):
    """Heutiges Datum als 'YYYY-MM-DD' in der Familien-Zeitzone."""
    return datetime.now(ZoneInfo(zeitzone)).date().isoformat()


def load_einmalig_heute(store_path, zeitzone):
    """Lädt einmalig-Items für heute. Tageswechsel → leere Liste (ROUTINE-6)."""
    store = _load_store(store_path)
    heute = _heute_str(zeitzone)
    tag = store.get("tag", {})
    if tag.get("datum") != heute:
        return []
    return list(tag.get("einmalig", []))


def _save_einmalig_heute(store_path, zeitzone, einmalig_items):
    """Speichert einmalig-Items für heute, bewahrt bestehenden Abhak-Zustand (ROUTINE-6/8)."""
    store = _load_store(store_path)
    heute = _heute_str(zeitzone)
    tag = store.get("tag", {})
    if tag.get("datum") != heute:
        # Tageswechsel: Abhak-Zustand verwerfen, aber neues Datum setzen
        tag = {"datum": heute, "abgehakt": {}}
    tag["einmalig"] = einmalig_items
    store["tag"] = tag
    _atomic_write_json(store_path, store)


# ============================================================
#  Item-Zählung (ROUTINE-19)
# ============================================================

def count_all_items(data_path, store_path, zeitzone):
    """Zählt alle aktuell sichtbaren Items: default + einmalig (ROUTINE-19).

    Wird für die max-8-Klemme beim POST verwendet.
    """
    routine = _load_routine_json(data_path)
    default_items = routine.get("items", [])
    if not isinstance(default_items, list):
        default_items = []
    n_default = len(default_items)
    n_einmalig = len(load_einmalig_heute(store_path, zeitzone))
    return n_default + n_einmalig


# ============================================================
#  Validierung (ROUTINE-14, AC4)
# ============================================================

def _validate_new_item(quelle, label, piktogramm):
    """Validiert Felder eines neuen Items (ROUTINE-14).

    Wirft ItemsError bei ungültiger Eingabe.
    """
    gueltige_quellen = frozenset({"default", "einmalig"})
    if quelle not in gueltige_quellen:
        raise ItemsError(
            "quelle muss 'default' oder 'einmalig' sein, erhalten: %r" % quelle)
    if not label or not str(label).strip():
        raise ItemsError("label darf nicht leer sein")
    if not piktogramm or not str(piktogramm).strip():
        raise ItemsError("piktogramm darf nicht leer sein")


def _validate_replace_items(items):
    """Validiert eine zu ersetzende default-Itemliste (PUT, ROUTINE-14).

    Erwartet eine Liste von Dicts mit id, label, piktogramm.
    Wirft ItemsError bei ungültiger Eingabe.
    """
    if not isinstance(items, list):
        raise ItemsError("items muss eine Liste sein")
    if len(items) > MAX_ITEMS:
        raise ItemsError(
            "zu viele Items: %d (maximal %d, ROUTINE-19)" % (len(items), MAX_ITEMS))
    seen_ids = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ItemsError("items[%d]: kein Objekt" % i)
        item_id = item.get("id")
        if not item_id or not str(item_id).strip():
            raise ItemsError("items[%d]: id darf nicht leer sein" % i)
        if item_id in seen_ids:
            raise ItemsError("items[%d]: doppelte id %r (ROUTINE-5)" % (i, item_id))
        seen_ids.add(item_id)
        if not item.get("label") or not str(item.get("label", "")).strip():
            raise ItemsError("items[%d]: label darf nicht leer sein" % i)
        if not item.get("piktogramm") or not str(item.get("piktogramm", "")).strip():
            raise ItemsError("items[%d]: piktogramm darf nicht leer sein" % i)


# ============================================================
#  API-Operationen
# ============================================================

def add_item(data_path, store_path, quelle, label, piktogramm, zeitzone="Europe/Berlin"):
    """Fügt ein neues Item hinzu (POST /api/v1/routine/items, ROUTINE-14).

    quelle=default → in routine.json (persistent, ROUTINE-12)
    quelle=einmalig → in den Tages-State (heute, Auto-Verfall ROUTINE-6)

    ROUTINE-19: max. 8 Items — bei ≥8 ItemsError.
    ROUTINE-5: stabile, herkunfts-eindeutige ID.

    Gibt dict {"id": <neue_id>} zurück.
    """
    # Validierung VOR dem Schreiben (kein Teil-Write, ROUTINE-14, AC2)
    _validate_new_item(quelle, label, piktogramm)

    # max-8-Klemme (ROUTINE-19)
    gesamt = count_all_items(data_path, store_path, zeitzone)
    if gesamt >= MAX_ITEMS:
        raise ItemsError(
            "Maximal %d Routine-Punkte erlaubt (ROUTINE-19). "
            "Bitte erst einen Punkt löschen." % MAX_ITEMS)

    label = str(label).strip()
    piktogramm = str(piktogramm).strip()

    if quelle == "default":
        return _add_default_item(data_path, label, piktogramm)
    else:
        return _add_einmalig_item(store_path, zeitzone, label, piktogramm)


def _add_default_item(data_path, label, piktogramm):
    """Fügt ein default-Item in routine.json ein (atomar, DCOMP-4)."""
    routine = _load_routine_json(data_path)
    items = routine.get("items", [])
    if not isinstance(items, list):
        items = []

    existing_ids = {item.get("id") for item in items if isinstance(item, dict)}
    new_id = _make_default_id(label, existing_ids)

    new_item = {
        "id": new_id,
        "label": label,
        "piktogramm": piktogramm,
        "quelle": "default",
    }
    items.append(new_item)
    routine["items"] = items
    _atomic_write_json(data_path, routine)

    logger.info("default-Item hinzugefügt: %r (ROUTINE-14, #354)", new_id)
    return {"id": new_id}


def _add_einmalig_item(store_path, zeitzone, label, piktogramm):
    """Fügt ein einmalig-Item in den Tages-State ein (atomar, DCOMP-4).

    ID-Präfix einmalig: (ROUTINE-5) — kollidiert nie mit default-IDs.
    """
    einmalig = load_einmalig_heute(store_path, zeitzone)

    existing_ids = {item.get("id") for item in einmalig if isinstance(item, dict)}
    base_id = "einmalig:" + _slug(label)
    candidate_id = base_id
    n = 2
    while candidate_id in existing_ids:
        candidate_id = base_id + ("-%d" % n)
        n += 1

    new_item = {
        "id": candidate_id,
        "label": label,
        "piktogramm": piktogramm,
        "quelle": "einmalig",
    }
    einmalig.append(new_item)
    _save_einmalig_heute(store_path, zeitzone, einmalig)

    logger.info("einmalig-Item hinzugefügt: %r (ROUTINE-14, ROUTINE-6, #354)", candidate_id)
    return {"id": candidate_id}


def delete_item(data_path, store_path, item_id, zeitzone="Europe/Berlin"):
    """Löscht ein Item per ID (DELETE /api/v1/routine/items/<id>, ROUTINE-14).

    default-ID → aus routine.json entfernen (atomar)
    einmalig:-ID → aus Tages-State entfernen (atomar)

    Gibt {"id": item_id} zurück. Existiert die ID nicht → ItemsError.
    """
    if not item_id:
        raise ItemsError("item_id darf nicht leer sein")

    if item_id.startswith("einmalig:"):
        return _delete_einmalig_item(store_path, zeitzone, item_id)
    else:
        return _delete_default_item(data_path, item_id)


def _delete_default_item(data_path, item_id):
    """Löscht ein default-Item aus routine.json (atomar, DCOMP-4)."""
    routine = _load_routine_json(data_path)
    items = routine.get("items", [])
    if not isinstance(items, list):
        items = []

    vorher = len(items)
    items = [item for item in items
             if not (isinstance(item, dict) and item.get("id") == item_id)]

    if len(items) == vorher:
        raise ItemsError("Item-ID nicht gefunden: %r" % item_id)

    routine["items"] = items
    _atomic_write_json(data_path, routine)

    logger.info("default-Item gelöscht: %r (ROUTINE-14, #354)", item_id)
    return {"id": item_id}


def _delete_einmalig_item(store_path, zeitzone, item_id):
    """Löscht ein einmalig-Item aus dem Tages-State (atomar, DCOMP-4)."""
    einmalig = load_einmalig_heute(store_path, zeitzone)

    vorher = len(einmalig)
    einmalig = [item for item in einmalig
                if not (isinstance(item, dict) and item.get("id") == item_id)]

    if len(einmalig) == vorher:
        raise ItemsError("einmalig-Item-ID nicht gefunden: %r" % item_id)

    _save_einmalig_heute(store_path, zeitzone, einmalig)

    logger.info("einmalig-Item gelöscht: %r (ROUTINE-14, ROUTINE-6, #354)", item_id)
    return {"id": item_id}


def replace_default_items(data_path, items):
    """Ersetzt die geordnete default-Liste in routine.json (PUT /api/v1/routine/items).

    Idempotent: setzt die items-Liste auf genau die übergebenen Einträge.
    Reihenfolge im Request = Anzeige-Reihenfolge (ROUTINE-14, RPS-3).
    ROUTINE-19: max. 8 Einträge.

    items: Liste von Dicts {id, label, piktogramm, quelle?}
    Gibt {"count": n} zurück.
    """
    # Validierung VOR dem Schreiben
    _validate_replace_items(items)

    routine = _load_routine_json(data_path)

    # Canonical-Form: quelle immer 'default' setzen, _comment-Keys droppen
    normalized = []
    for item in items:
        normalized.append({
            "id": str(item["id"]).strip(),
            "label": str(item["label"]).strip(),
            "piktogramm": str(item["piktogramm"]).strip(),
            "quelle": "default",
        })

    routine["items"] = normalized
    _atomic_write_json(data_path, routine)

    logger.info("default-Items ersetzt: %d Einträge (ROUTINE-14, #354)", len(normalized))
    return {"count": len(normalized)}
