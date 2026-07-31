#!/usr/bin/env python3
"""_make_icons.py — Generiert die drei PWA-Pflicht-Icons fuer routine-anpassen.

ROUTINE-23: 192x192, 512x512, maskable-512 (PWAM-2-Pflichtfelder).
Brand-Token: Sand-Hintergrund (#F5F1E8) — wie plan/kibuddy.
Symbol: echtes ARASAAC-Aufgabenlisten-Piktogramm (ID 30207 — "Liste/Auflistung",
        nummerierte Liste mit schreibender Hand). Bewusst NICHT der plan-Kalender
        (32488): routine ist die Morgen-Aufgabenliste, nicht der Kalender (#1676).

Quell-Piktogramm:
  https://api.arasaac.org/api/pictograms/de/search/liste  → _id 30207
  https://static.arasaac.org/pictograms/30207/30207_500.png

Vorgehen (analog seiten/static/plan/_make_icons.py):
  1. ARASAAC-PNG (500px, transparenter Hintergrund) laden.
  2. Auf Sand-Hintergrund (#F5F1E8) kompositen.
  3. Mit genug Safe-Zone-Padding auf die PWA-Ziel-Groessen skalieren.
  4. Fuer maskable-512: kleineres Padding (Symbol darf bis ~10% an den Rand).

Lauf:  cd seiten/static/routine/ && python3 _make_icons.py
       oder: python3 seiten/static/routine/_make_icons.py
Dann:  PNG-Dateien committen, Skript bleibt als Quelle der Wahrheit
       fuer spaetere Brand-Tweaks (routine-Motiv).
"""

import io
import os
import sys
import urllib.request

from PIL import Image

# XBuddy-Brand-Tokens
BG_COLOR = "#F5F1E8"  # Sand — Hintergrund

# ARASAAC-Aufgabenlisten-Piktogramm (ID 30207 — "Liste/Auflistung",
# nummerierte Liste + schreibende Hand; eigenes Routine-Motiv, #1676)
ARASAAC_ID = 30207
ARASAAC_URL = f"https://static.arasaac.org/pictograms/{ARASAAC_ID}/{ARASAAC_ID}_500.png"

# Lokale Icon-Bibliothek (Fallback, falls kein Netz)
_LOCAL_ICON_PATHS = [
    os.path.join("/home/buddy/apps/icons/arasaac", f"{ARASAAC_ID}.png"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "../../../../apps/icons/arasaac", f"{ARASAAC_ID}.png"),
]


def _parse_hex(hex_color):
    """Konvertiert #RRGGBB zu (R, G, B, 255)-Tuple."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return (r, g, b, 255)


def _lade_arasaac_png():
    """Laedt das ARASAAC-Listen-Piktogramm als RGBA-Image.

    Versucht erst lokale Icon-Bibliothek, dann Download von ARASAAC.
    Wirft RuntimeError wenn beides schlaegt.
    """
    # Lokale Bibliothek pruefen (bevorzugt: kein Netz noetig)
    for local_path in _LOCAL_ICON_PATHS:
        resolved = os.path.realpath(local_path)
        if os.path.isfile(resolved):
            print(f"  Lade Piktogramm aus lokaler Bibliothek: {resolved}")
            img = Image.open(resolved).convert("RGBA")
            return img

    # Fallback: Download von ARASAAC-CDN
    print(f"  Lade Piktogramm von {ARASAAC_URL} …")
    try:
        req = urllib.request.Request(
            ARASAAC_URL,
            headers={"User-Agent": "xbuddy-pwa-icon-builder/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        print(f"  Download OK ({len(data)} Bytes)")
        return img
    except Exception as exc:
        raise RuntimeError(
            f"ARASAAC-Piktogramm {ARASAAC_ID} konnte nicht geladen werden "
            f"(weder lokal noch via {ARASAAC_URL}): {exc}"
        ) from exc


def make_icon(source_img, size, path, *, maskable=False):
    """Erzeugt ein PWA-Icon der gegebenen Groesse als PNG.

    source_img: RGBA-PIL-Image des ARASAAC-Piktogramms.
    maskable=True: kleineres Padding (~10% pro Seite), Hintergrund vollflaechig
                   — Android-Launcher schneidet seine Maske ein.
    maskable=False: groesseres Padding (~15% pro Seite) — gibt Browser-Default-
                    Maske genug Luft.
    """
    bg_rgba = _parse_hex(BG_COLOR)

    # Hintergrund erstellen
    canvas = Image.new("RGBA", (size, size), bg_rgba)

    # Safe-Zone-Padding: maskable braucht mindestens 10% pro Seite (Android).
    # any-purpose: 15% pro Seite — gibt Luft fuer Browser-Masken.
    pad_ratio = 0.10 if maskable else 0.15
    pad = int(size * pad_ratio)
    inner = size - 2 * pad

    # Piktogramm auf inner-Groesse skalieren (LANCZOS fuer scharfe Kanten)
    scaled = source_img.resize((inner, inner), Image.LANCZOS)

    # Auf Hintergrund kompositen (ARASAAC-PNGs haben transparente Hintergruende)
    canvas.paste(scaled, (pad, pad), scaled)

    # Als RGB-PNG speichern (kein Alpha im finalen Icon noetig — BG ist solid)
    final = canvas.convert("RGB")
    final.save(path, format="PNG", optimize=True)
    print(f"  → {path} ({size}x{size}, maskable={maskable})")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    print(f"Generiere routine-anpassen-PWA-Icons (ROUTINE-23) aus ARASAAC-Piktogramm {ARASAAC_ID}…")

    try:
        source = _lade_arasaac_png()
    except RuntimeError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        sys.exit(1)

    make_icon(source, 192, os.path.join(here, "icon-192.png"),           maskable=False)
    make_icon(source, 512, os.path.join(here, "icon-512.png"),           maskable=False)
    make_icon(source, 512, os.path.join(here, "icon-maskable-512.png"),  maskable=True)
    print("Fertig.")
