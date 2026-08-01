#!/usr/bin/env python3
"""_make_icons.py — PWA-Pflicht-Icons für die wetter-regeln-Mini-App (#1715).

192/512/maskable-512 (PWAM-2). Brand: Sand-BG (#F5F1E8), wie routine/plan.
Symbol: ARASAAC 7233 ("Kleidung/Klamotten") — passend zum Garderoben-Editor.

Lauf:  python3 seiten/static/wetter/_make_icons.py
"""

import io
import os
import sys
import urllib.request

from PIL import Image

BG_COLOR = "#F5F1E8"
ARASAAC_ID = 7233
ARASAAC_URL = f"https://static.arasaac.org/pictograms/{ARASAAC_ID}/{ARASAAC_ID}_500.png"
_LOCAL_ICON_PATHS = [
    os.path.join("/home/buddy/apps/icons/arasaac", f"{ARASAAC_ID}.png"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "../../../../apps/icons/arasaac", f"{ARASAAC_ID}.png"),
]


def _parse_hex(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return (r, g, b, 255)


def _lade_arasaac_png():
    for local_path in _LOCAL_ICON_PATHS:
        resolved = os.path.realpath(local_path)
        if os.path.isfile(resolved):
            print(f"  Lade Piktogramm aus lokaler Bibliothek: {resolved}")
            return Image.open(resolved).convert("RGBA")
    print(f"  Lade Piktogramm von {ARASAAC_URL} …")
    try:
        req = urllib.request.Request(
            ARASAAC_URL, headers={"User-Agent": "xbuddy-pwa-icon-builder/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        print(f"  Download OK ({len(data)} Bytes)")
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as exc:
        raise RuntimeError(
            f"ARASAAC-Piktogramm {ARASAAC_ID} konnte nicht geladen werden: {exc}"
        ) from exc


def make_icon(source_img, size, path, *, maskable=False):
    bg_rgba = _parse_hex(BG_COLOR)
    canvas = Image.new("RGBA", (size, size), bg_rgba)
    pad_ratio = 0.10 if maskable else 0.15
    pad = int(size * pad_ratio)
    inner = size - 2 * pad
    scaled = source_img.resize((inner, inner), Image.LANCZOS)
    canvas.paste(scaled, (pad, pad), scaled)
    canvas.convert("RGB").save(path, format="PNG", optimize=True)
    print(f"  → {path} ({size}x{size}, maskable={maskable})")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    print(f"Generiere wetter-regeln-PWA-Icons (#1715) aus ARASAAC {ARASAAC_ID}…")
    try:
        source = _lade_arasaac_png()
    except RuntimeError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        sys.exit(1)
    make_icon(source, 192, os.path.join(here, "icon-192.png"),          maskable=False)
    make_icon(source, 512, os.path.join(here, "icon-512.png"),          maskable=False)
    make_icon(source, 512, os.path.join(here, "icon-maskable-512.png"), maskable=True)
    print("Fertig.")
