#!/usr/bin/env python3
"""T810 (Welle 3 von #804): bestehende Essen-Fotos aus photo/medien/ in essen/fotos/ verschieben.

Ablauf:
- Liest xbuddy-data/essen/gerichte.json + foto_overrides.json
- Sammelt alle foto_ref-IDs
- Fuer jede ID: liest photo-Datei + Thumbnail, schreibt via tools.medien_store.add
  in essen/fotos/, patcht gerichte.json + foto_overrides.json mit neuer ID,
  entfernt alten Eintrag aus photo/library.json + die Dateien atomar.
- Idempotent: prueft ob photo-foto_refs noch in photo/library.json existieren
  — wenn nicht, uebersprungen (bereits migriert oder nie vorhanden).
- Smoke-Output am Ende.

Nutzung:
    python3 deploy/migrate-essen-fotos-aus-photo.py [--data-dir <pfad>] [--dry-run]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Inject repo root — laeuft sowohl als Skript als auch via pytest
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.medien_store import add as ms_add  # noqa: E402
from tools.medien_store import delete as ms_delete  # noqa: E402
from tools.medien_store import load as ms_load  # noqa: E402

logger = logging.getLogger(__name__)


DEFAULT_DATA_DIR = Path("/home/buddy/xbuddy-data")


def _neue_essen_id(essen_fotos_verzeichnis, typ):
    """Vergibt eine kollisionsfreie id `<typ>-<nn>` im essen/fotos-Verzeichnis."""
    belegt = {m.id for m in ms_load(str(essen_fotos_verzeichnis))}
    n = 1
    while True:
        kand = "%s-%02d" % (typ, n)
        if kand not in belegt:
            return kand
        n += 1


def _atomic_write_json(path, content_dict):
    """Schreibt JSON atomar via .tmp + os.replace."""
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(
        json.dumps(content_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def main(data_dir=None, dry_run=False):
    """Migrations-Kernlogik. `data_dir` ist ein Path-Objekt.

    Gibt die Anzahl migrierter Items zurueck (int).
    """
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR

    data_dir = Path(data_dir)
    photo_dir = data_dir / "photo" / "medien"
    photo_lib_path = photo_dir / "library.json"
    essen_fotos = data_dir / "essen" / "fotos"
    essen_gerichte_path = data_dir / "essen" / "gerichte.json"
    essen_overrides_path = data_dir / "essen" / "foto_overrides.json"

    # ── Quelldaten lesen ──────────────────────────────────────────────────

    if not essen_gerichte_path.exists():
        print("essen/gerichte.json fehlt — nichts zu tun")
        return 0

    gerichte_data = json.loads(essen_gerichte_path.read_text(encoding="utf-8"))
    overrides = {}
    if essen_overrides_path.exists():
        try:
            overrides = json.loads(essen_overrides_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Warnung: foto_overrides.json nicht lesbar ({e}) — uebersprungen")

    photo_lib = {"medien": []}
    if photo_lib_path.exists():
        try:
            photo_lib = json.loads(photo_lib_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Warnung: photo/library.json nicht lesbar ({e}) — kein Cleanup moeglich")

    photo_index = {m["id"]: m for m in photo_lib.get("medien", [])}

    # ── foto_refs sammeln (aus gerichte + overrides) ───────────────────────

    refs_aus_gerichten = set()
    for g in gerichte_data.get("gerichte", []):
        ref = g.get("foto_ref")
        if ref:
            refs_aus_gerichten.add(ref)

    refs_aus_overrides = set()
    if isinstance(overrides, dict):
        for v in overrides.values():
            if v:
                refs_aus_overrides.add(v)

    alle_refs = refs_aus_gerichten | refs_aus_overrides
    if not alle_refs:
        print("Keine foto_refs gefunden — nichts zu tun")
        return 0

    print(f"foto_refs: {len(alle_refs)} gesamt "
          f"({len(refs_aus_gerichten)} aus Gerichten, "
          f"{len(refs_aus_overrides)} aus Overrides)")

    # ── Essen-Fotos-Verzeichnis anlegen ────────────────────────────────────

    if not dry_run:
        essen_fotos.mkdir(parents=True, exist_ok=True)

    # ── Migration: photo-ID → essen-ID ────────────────────────────────────

    id_map = {}  # alte photo-ID → neue essen-ID

    for old_ref in sorted(alle_refs):
        if old_ref not in photo_index:
            print(f"  {old_ref}: nicht in photo/library.json "
                  "(vermutlich bereits migriert oder nie vorhanden) — uebersprungen")
            continue

        photo_entry = photo_index[old_ref]
        src_datei = photo_dir / photo_entry["datei"]
        thumb_datei_rel = photo_entry.get("thumbnail", "")
        thumb_datei = photo_dir / thumb_datei_rel if thumb_datei_rel else None

        if not src_datei.exists():
            print(f"  {old_ref}: Vollmedium {photo_entry['datei']} fehlt — uebersprungen")
            continue

        rohbytes = src_datei.read_bytes()
        thumb_bytes = None
        if thumb_datei and thumb_datei.exists():
            thumb_bytes = thumb_datei.read_bytes()
        else:
            print(f"  {old_ref}: Thumbnail fehlt — Vollmedium wird als Thumbnail genutzt")
            thumb_bytes = rohbytes

        typ = photo_entry.get("typ", "foto")
        datei_suffix = Path(photo_entry["datei"]).suffix
        thumb_suffix = (
            Path(thumb_datei_rel).suffix if thumb_datei_rel else ".jpg"
        )

        new_id = _neue_essen_id(essen_fotos, typ)
        new_dateiname = new_id + datei_suffix
        new_thumb_name = new_id + ".thumb" + thumb_suffix

        if dry_run:
            print(f"  [DRY-RUN] {old_ref} → {new_id} "
                  f"({new_dateiname}, {new_thumb_name})")
            id_map[old_ref] = new_id
            continue

        ms_add(
            str(essen_fotos),
            id=new_id,
            typ=typ,
            daten=rohbytes,
            dateiname=new_dateiname,
            thumbnail_daten=thumb_bytes,
            thumbnail_name=new_thumb_name,
            aufgenommen=photo_entry.get("aufgenommen"),
            dauer=photo_entry.get("dauer"),
        )
        id_map[old_ref] = new_id
        print(f"  {old_ref} → {new_id}")

    if not id_map:
        print("FERTIG — 0 Items migriert (alle bereits migriert oder nicht vorhanden)")
        return 0

    # ── gerichte.json patchen ──────────────────────────────────────────────

    for g in gerichte_data.get("gerichte", []):
        old = g.get("foto_ref")
        if old and old in id_map:
            g["foto_ref"] = id_map[old]

    # ── foto_overrides.json patchen ────────────────────────────────────────

    if isinstance(overrides, dict):
        for item_id in list(overrides.keys()):
            old = overrides[item_id]
            if old in id_map:
                overrides[item_id] = id_map[old]

    # ── Atomares Schreiben der gepatchten JSON-Dateien ─────────────────────

    if not dry_run:
        _atomic_write_json(essen_gerichte_path, gerichte_data)
        print(f"  gerichte.json: {len(refs_aus_gerichten & id_map.keys())} Eintraege gepatcht")

        if essen_overrides_path.exists() or (refs_aus_overrides & id_map.keys()):
            _atomic_write_json(essen_overrides_path, overrides)
            print(f"  foto_overrides.json: "
                  f"{len(refs_aus_overrides & id_map.keys())} Eintraege gepatcht")

        # ── Alte photo-Eintraege entfernen ─────────────────────────────────

        for old_ref in id_map:
            try:
                entfernt = ms_delete(str(photo_dir), old_ref)
                if entfernt:
                    print(f"  {old_ref}: aus photo/library.json + Dateien entfernt")
                else:
                    print(f"  {old_ref}: war nicht (mehr) in photo/library.json")
            except Exception as e:
                print(f"  Warnung: Fehler beim Loeschen von {old_ref} aus photo: {e}")

    anzahl = len(id_map)
    print(f"FERTIG — {anzahl} Item(s) migriert")
    return anzahl


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="T810: Essen-Fotos aus photo/medien/ nach essen/fotos/ migrieren"
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Pfad zum xbuddy-data-Verzeichnis (Default: %s)" % DEFAULT_DATA_DIR,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur ausgeben, was migriert wuerde — keine Aenderungen schreiben",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    args = _parse_args()
    main(data_dir=Path(args.data_dir), dry_run=args.dry_run)
    sys.exit(0)
