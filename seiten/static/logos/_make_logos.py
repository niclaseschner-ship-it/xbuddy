#!/usr/bin/env python3
"""_make_logos.py — erzeugt die Buddy-Logos aus seiten/logos.json (#1953).

Je Buddy aus `buddies` entstehen unter seiten/static/logos/<buddy>/ die drei
PWA-Pflicht-Icons (PWAM-2): icon-192.png, icon-512.png, icon-maskable-512.png.
Danach werden sie in den Icon-Ordner jedes Mantels aus `maentel` kopiert —
so ist das Logo des Buddys zugleich das PWA-Icon aller seiner Mäntel.

Stil (eine Form für alle): Sand-Hintergrund #F5F1E8 (Mantel background_color),
das ARASAAC-Piktogramm mittig; maskable mit kleinerem Rand (Safe Zone).
Quelle: lokaler ARASAAC-Cache /home/buddy/apps/icons/arasaac/<id>.png (ICONS-1),
sonst Download von static.arasaac.org. Lizenz: CC BY-NC-SA 4.0 (ICONS-6),
Nachweis in seiten/static/logos/SOURCES.md.

Lauf:  python3 seiten/static/logos/_make_logos.py
"""

import io
import json
import os
import shutil
import sys
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
LOGOS_JSON = os.path.join(REPO, "seiten", "logos.json")
BG_COLOR = (0xF5, 0xF1, 0xE8, 255)
LOKAL = "/home/buddy/apps/icons/arasaac/%d.png"
URL = "https://static.arasaac.org/pictograms/%d/%d_500.png"
ICONS = (("icon-192.png", 192, False), ("icon-512.png", 512, False),
         ("icon-maskable-512.png", 512, True))


def lade_piktogramm(arasaac_id):
    pfad = LOKAL % arasaac_id
    if os.path.isfile(pfad):
        return Image.open(pfad).convert("RGBA")
    req = urllib.request.Request(URL % (arasaac_id, arasaac_id),
                                 headers={"User-Agent": "xbuddy-logo-builder/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGBA")


def male(quelle, groesse, maskable):
    canvas = Image.new("RGBA", (groesse, groesse), BG_COLOR)
    pad = int(groesse * (0.16 if maskable else 0.10))
    inner = groesse - 2 * pad
    bild = quelle.resize((inner, inner), Image.LANCZOS)
    canvas.paste(bild, (pad, pad), bild)
    return canvas.convert("RGB")


def main():
    with open(LOGOS_JSON, encoding="utf-8") as fh:
        cfg = json.load(fh)
    buddies = {k: v for k, v in cfg["buddies"].items() if not k.startswith("_")}
    for buddy, eintrag in sorted(buddies.items()):
        quelle = lade_piktogramm(eintrag["arasaac"])
        ziel = os.path.join(HERE, buddy)
        os.makedirs(ziel, exist_ok=True)
        for datei, groesse, maskable in ICONS:
            male(quelle, groesse, maskable).save(
                os.path.join(ziel, datei), format="PNG", optimize=True)
        print("  %-10s ARASAAC %s" % (buddy, eintrag["arasaac"]))
    maentel = {k: v for k, v in cfg["maentel"].items() if not k.startswith("_")}
    for mantel, eintrag in sorted(maentel.items()):
        ordner = os.path.join(REPO, eintrag["ordner"])
        for datei in eintrag.get("dateien", [d for d, _, _ in ICONS]):
            shutil.copyfile(os.path.join(HERE, eintrag["buddy"], datei),
                            os.path.join(ordner, datei))
        print("  Mantel %-16s <- %s" % (mantel, eintrag["buddy"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
