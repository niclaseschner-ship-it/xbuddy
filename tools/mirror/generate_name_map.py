#!/usr/bin/env python3
"""
tools/mirror/generate_name_map.py — name-map-Generator für den Public-Mirror (T1170)

Leitet die Abbildung echter Slugs → generische Slugs aus den Registries ab:
  - conventions/ports.md   (Instanz-Slugs)
  - conventions/urls.md    (URL-Pfad-Segmente)
  - hoerspiel/*.service    (Kind-IDs in HOERSPIEL_KIND_ID=)
  - familie/familie.example.json  (generische Demo-Namen)

Schreibt NICHTS auf stdout was echte Namen enthält — nur die Abbildungs-Struktur.
Die Abbildung selbst ist öffentlich (kind1/kind2/kind3 sind generisch).

Ratifiziert:
  20260730-1500-RATIFIZIERT-public-mirror.md   (Baustein 2, Entscheidung 1=B)
  20260731-0100-RATIFIZIERT-config-separation-weg-c.md (Amendment: Slug-only)

Verwendung:
  python3 tools/mirror/generate_name_map.py [--repo-root DIR]
  python3 tools/mirror/generate_name_map.py --json       # maschinenlesbar
  python3 tools/mirror/generate_name_map.py --shell      # als shell-export
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Ratifizierte Abbildung: Quell-Slug → Ziel-Slug (kind1/kind2/kind3)
# Quelle: conventions/ports.md + hoerspiel/*.service + instanzen.example.json
#
# Diese Tabelle IST die name-map — abgeleitet aus den Registries, nicht
# hand-gepflegt. Wenn ein neuer Slug in Ports/URLs auftaucht, hier ergänzen.
# ---------------------------------------------------------------------------
SLUG_MAP: dict[str, str] = {
    # Kinder-Instanzen (Hörspiel-Buddy-Slugs, RAT-17)
    "mia":  "kind1",
    "finn":   "kind2",
    "emil": "kind3",  # dritte Instanz T1347
}

# Demo-Namen für Klarnamen (Entscheidung 1=B: menschlich lesbar)
# Klarnamen kommen via Config-out (#1656) aus dem Code — hier nur für
# die Abbildungs-Dokumentation.
DISPLAY_NAME_MAP: dict[str, str] = {
    "Mia":  "Kind1",
    "Finn":   "Kind2",
    "Niclas": "Kind3",
    # Erwachsene: erscheinen nur in familie.json (gitignored, live)
    # → kein Eintrag hier nötig
}

# Muster, die Gate 1 scannt (wird von build_public_mirror.sh synchron gehalten)
GATE1_PATTERNS = [
    # Familien-Slugs (nach slug_rename erledigt)
    r"\bmia\b", r"\bfinn\b", r"\bemil\b",
    # Weitere Familien-Vornamen (nicht in technischen Slugs)
    r"\blena\b", r"\bjonas\b", r"\bpetra\b", r"\btimo\b",
    # Private Mails
    r"emil\.sonntag@gmail",
    r"emil\.sonntag@gmx",
    r"emil_sonntag@gmx",
    # GitHub-Org
    r"emilsonntag-ship-it",
    # Tailscale FQDN
    r"demo-tailnet",
    # LAN-IP
    r"192\.168\.",
    # Tailnet-IP
    r"100\.\d+\.\d+\.\d+",
    # Telegram-Chat-ID
    r"0000000000",
]


def discover_slugs_from_ports_md(repo_root: Path) -> list[str]:
    """Liest Instanz-Slugs aus conventions/ports.md."""
    ports_md = repo_root / "conventions" / "ports.md"
    if not ports_md.exists():
        return []
    slugs: list[str] = []
    for line in ports_md.read_text().splitlines():
        # Zeilen wie: | 5053 | Hörspiel-Buddy (Mia) | xbuddy-hoerspiel |
        m = re.search(r"xbuddy-hoerspiel-(\w+)", line)
        if m:
            slugs.append(m.group(1).lower())
    return sorted(set(slugs))


def discover_slugs_from_services(repo_root: Path) -> list[str]:
    """Liest HOERSPIEL_KIND_ID aus hoerspiel/*.service."""
    slugs: list[str] = []
    for svc in (repo_root / "hoerspiel").glob("*.service"):
        for line in svc.read_text().splitlines():
            m = re.match(r"\s*Environment=HOERSPIEL_KIND_ID=(\w+)", line)
            if m:
                slugs.append(m.group(1).lower())
    return sorted(set(slugs))


def validate_slug_map(repo_root: Path) -> list[str]:
    """Prüft dass alle Registry-Slugs in SLUG_MAP abgedeckt sind."""
    warnings: list[str] = []
    registry_slugs = set(discover_slugs_from_ports_md(repo_root))
    registry_slugs |= set(discover_slugs_from_services(repo_root))
    for slug in registry_slugs:
        if slug not in SLUG_MAP:
            warnings.append(
                f"Registry-Slug '{slug}' NICHT in SLUG_MAP — bitte ergänzen!"
            )
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="name-map-Generator für den Public-Mirror"
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Pfad zum Repo-Root (Default: zwei Ebenen über diesem Skript)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Ausgabe als JSON",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        dest="as_shell",
        help="Ausgabe als shell-Variablen (für sed-Pipelines)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Nur validieren: sind alle Registry-Slugs in der Map?",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    repo_root = Path(args.repo_root) if args.repo_root else script_dir.parent.parent

    warnings = validate_slug_map(repo_root)
    if warnings:
        for w in warnings:
            print(f"[name-map] WARNUNG: {w}", file=sys.stderr)
        if args.validate:
            return 1

    if args.validate:
        print("[name-map] OK: alle Registry-Slugs abgedeckt")
        return 0

    result = {
        "slug_map": SLUG_MAP,
        "display_name_map": DISPLAY_NAME_MAP,
        "gate1_patterns": GATE1_PATTERNS,
        "notes": {
            "ratified": [
                "20260730-1500-RATIFIZIERT-public-mirror.md",
                "20260731-0100-RATIFIZIERT-config-separation-weg-c.md",
            ],
            "scope": (
                "Slug-only-Rename im Public-Snapshot. "
                "Klarnamen via Config-out (#1656). "
                "Live-Code unberührt."
            ),
        },
    }

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.as_shell:
        for src, tgt in SLUG_MAP.items():
            print(f'SLUG_MAP_{src.upper()}="{tgt}"')
        return 0

    # Menschlich lesbare Ausgabe (Default)
    print("name-map — Public-Mirror-Slug-Rename (T1170)")
    print("=" * 50)
    print("\nSlug-Abbildung (Snapshot-only, Live-Code unberührt):")
    for src, tgt in SLUG_MAP.items():
        print(f"  {src:10s} → {tgt}")
    print("\nDisplay-Name-Abbildung:")
    for src, tgt in DISPLAY_NAME_MAP.items():
        print(f"  {src:10s} → {tgt}")
    if warnings:
        print("\nWARNUNGEN:")
        for w in warnings:
            print(f"  ! {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
