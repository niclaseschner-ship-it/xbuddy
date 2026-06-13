#!/usr/bin/env python3
"""T799 One-Shot: bestehende Essen-Fotos in library.json auf in_library=false setzen.

Liest gerichte.json + foto_overrides.json, sammelt foto_refs, patcht library.json.
Sicher: idempotent, atomar (tmp + os.replace). Keine Netz-Aufrufe.

Nutzung:
    python3 deploy/migrate-essen-fotos-library.py [--data-dir <pfad>]

Standardmäßig liest der Pfad aus DATA = /home/buddy/xbuddy-data.
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="T799: Essen-Fotos in library.json als in_library=false markieren"
    )
    parser.add_argument(
        "--data-dir",
        default="/home/buddy/xbuddy-data",
        help="Pfad zum xbuddy-data-Verzeichnis (Default: /home/buddy/xbuddy-data)",
    )
    args = parser.parse_args()

    data = Path(args.data_dir)
    lib = data / "photo" / "medien" / "library.json"
    gerichte = data / "essen" / "gerichte.json"
    overrides = data / "essen" / "foto_overrides.json"

    # Essen-foto_refs aus gerichte.json sammeln.
    essen_refs = set()
    if gerichte.exists():
        g = json.loads(gerichte.read_text(encoding="utf-8"))
        for ger in g.get("gerichte", []):
            ref = ger.get("foto_ref")
            if ref:
                essen_refs.add(ref)
        print(f"gerichte.json: {len(essen_refs)} foto_ref(s) gesammelt")
    else:
        print(f"gerichte.json fehlt ({gerichte}) — übersprungen")

    # Essen-foto_refs aus foto_overrides.json sammeln.
    if overrides.exists():
        ov = json.loads(overrides.read_text(encoding="utf-8"))
        if isinstance(ov, dict):
            refs_aus_overrides = {v for v in ov.values() if v}
            essen_refs.update(refs_aus_overrides)
            print(f"foto_overrides.json: {len(refs_aus_overrides)} ref(s) gesammelt")
    else:
        print(f"foto_overrides.json fehlt ({overrides}) — übersprungen")

    if not essen_refs:
        print("Keine Essen-Refs gefunden — nichts zu tun")
        raise SystemExit(0)

    print(f"Gesamt Essen-Refs: {sorted(essen_refs)}")

    if not lib.exists():
        print(f"library.json fehlt ({lib}) — nichts zu tun")
        raise SystemExit(0)

    lib_data = json.loads(lib.read_text(encoding="utf-8"))
    changed = 0
    for m in lib_data.get("medien", []):
        if m["id"] in essen_refs and m.get("in_library", True) is True:
            m["in_library"] = False
            changed += 1
            print(f"  {m['id']}: in_library → false")

    # Atomar zurückschreiben (tmp + os.replace).
    tmp = lib.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(lib_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(lib)
    print(f"FERTIG — {changed} Einträge angepasst")


if __name__ == "__main__":
    main()
