"""Wetter-Buddy — kuratierte Kleidungs-Palette (WETTER-29).

Siehe specs/buddies/wetter.md §10. Dieses Modul besitzt die **Palette-Daten**:
die mit dem Buddy ausgelieferte Liste vorgegebener Kleidungsstücke
`{name, pikto}`, aus der der Garderoben-Editor (WETTER-26 ff.) wählen lässt.
Die Familie tippt **keine** ARASAAC-ID — sie wählt aus dieser Liste (WETTER-29).

Die Palette ist Daten, kein Code (CLAUDE.md §6, Daten-vs-Code): sie steht in
`palette.json` neben diesem Modul; dieses Modul lädt sie und stellt die
Lookups bereit, die der Editor und die Schreib-Validierung (WETTER-30)
brauchen.

Public-API: `laden() -> list[dict]`, `erlaubte_piktos() -> set[str]`,
`ist_in_palette(pikto) -> bool`.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PALETTE_DATEI = os.path.join(HERE, "palette.json")


def laden():
    """Lädt die kuratierte Palette (WETTER-29) als Liste `{name, pikto}`-dicts.

    Liest `palette.json` relativ zu diesem Modul. `pikto` ist immer ein String
    (die ARASAAC-ID, WETTER-18) — so vergleicht sich der Validierungs-Lookup
    konsistent gegen die Werte aus `wetter.json`, die config.py ebenfalls als
    String parst.
    """
    with open(PALETTE_DATEI, encoding="utf-8") as f:
        data = json.load(f)
    stuecke = []
    for raw in data.get("stuecke", []):
        stuecke.append({"name": str(raw["name"]), "pikto": str(raw["pikto"])})
    return stuecke


def erlaubte_piktos():
    """Menge der erlaubten ARASAAC-IDs (WETTER-29/30) für den schnellen Lookup."""
    return {stueck["pikto"] for stueck in laden()}


def ist_in_palette(pikto):
    """True, wenn `pikto` (als String) eine ID der kuratierten Palette ist (WETTER-30)."""
    return str(pikto) in erlaubte_piktos()
