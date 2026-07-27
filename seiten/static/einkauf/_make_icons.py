#!/usr/bin/env python3
"""_make_icons.py — Generiert die drei PWA-Pflicht-Icons fuer essen-einkauf.

ESSEN-33: 192x192, 512x512, maskable-512 (PWA-2-Pflichtfelder).
Brand-Token: Olivgruen (#47503C, analog App-Panel), Sand-Hintergrund (#F5F1E8).
Symbol: stilisierter Einkaufskorb (Bring!-Benchmark, ESSEN-31-Ueberbau).

Wird einmal vor dem Commit ausgefuehrt; PNG-Output ist Bytes-stabil
(deterministische PIL-Draw-Operationen ohne Anti-Alias-Randomness).

Lauf:  cd seiten/static/einkauf/ && python3 _make_icons.py
Dann:  PNG-Dateien committen, Skript bleibt als Quelle der Wahrheit
       fuer spaetere Brand-Tweaks.
"""

from PIL import Image, ImageDraw

# XBuddy-Brand-Tokens (analog controller/app-panel/manifest.json)
THEME_COLOR  = "#47503C"   # Olivgruen — Vordergrund-Symbol
ACCENT_COLOR = "#D87A3E"   # warmes Orange — Akzent (Korb-Griff)
BG_COLOR     = "#F5F1E8"   # Sand — Hintergrund


def _draw_einkaufskorb(draw, size, *, padding_ratio=0.18):
    """Stilisierter Einkaufskorb: Trapez-Korb + zwei Griffe.

    Geometrie skaliert mit size; padding_ratio laesst Rand frei (wichtig fuer
    maskable-Icon-Variante — Android-Launcher schneidet die aeusseren ~20% weg).
    """
    s = size
    p = int(s * padding_ratio)
    inner = s - 2 * p

    # Korb-Trapez (breit oben, schmaler unten)
    korb_top_y = p + int(inner * 0.30)
    korb_bot_y = p + int(inner * 0.90)
    korb_top_x_left  = p + int(inner * 0.08)
    korb_top_x_right = p + int(inner * 0.92)
    korb_bot_x_left  = p + int(inner * 0.20)
    korb_bot_x_right = p + int(inner * 0.80)

    draw.polygon(
        [
            (korb_top_x_left,  korb_top_y),
            (korb_top_x_right, korb_top_y),
            (korb_bot_x_right, korb_bot_y),
            (korb_bot_x_left,  korb_bot_y),
        ],
        fill=THEME_COLOR,
    )

    # Korb-Oberkante (dicke Leiste)
    leiste_h = max(2, int(inner * 0.06))
    draw.rectangle(
        [
            (korb_top_x_left - int(inner * 0.04), korb_top_y - leiste_h),
            (korb_top_x_right + int(inner * 0.04), korb_top_y),
        ],
        fill=THEME_COLOR,
    )

    # Griffe (zwei Boegen) — als Ellipsen-Sektoren simuliert
    griff_h     = int(inner * 0.18)
    griff_thick = max(2, int(inner * 0.04))
    griff_y_top = korb_top_y - leiste_h - griff_h
    # linker Griff
    draw.arc(
        [
            (korb_top_x_left + int(inner * 0.04), griff_y_top),
            (korb_top_x_left + int(inner * 0.30), korb_top_y - leiste_h + griff_h // 2),
        ],
        start=180, end=360,
        fill=ACCENT_COLOR, width=griff_thick,
    )
    # rechter Griff
    draw.arc(
        [
            (korb_top_x_right - int(inner * 0.30), griff_y_top),
            (korb_top_x_right - int(inner * 0.04), korb_top_y - leiste_h + griff_h // 2),
        ],
        start=180, end=360,
        fill=ACCENT_COLOR, width=griff_thick,
    )

    # Rippen am Korb (drei vertikale Streifen)
    n_rippen = 3
    for i in range(1, n_rippen + 1):
        frac = i / (n_rippen + 1)
        x_top = korb_top_x_left + int((korb_top_x_right - korb_top_x_left) * frac)
        x_bot = korb_bot_x_left + int((korb_bot_x_right - korb_bot_x_left) * frac)
        rippe_thick = max(2, int(inner * 0.025))
        draw.line(
            [(x_top, korb_top_y), (x_bot, korb_bot_y)],
            fill=BG_COLOR, width=rippe_thick,
        )


def make_icon(size, path, *, maskable=False):
    """Erzeugt ein PWA-Icon der gegebenen Groesse als PNG.

    maskable=True: kein zusaetzliches Padding (Symbol fuellt die Safe-Area),
    Hintergrund vollflaechig — Android-Launcher schneidet seine Maske ein.
    """
    img = Image.new("RGBA", (size, size), BG_COLOR)
    draw = ImageDraw.Draw(img)

    if maskable:
        # Maskable: kleineres Padding, Symbol darf bis ~5% an den Rand,
        # Hintergrund-Farbe fuellt die volle Flaeche (kein Transparent-Rand).
        _draw_einkaufskorb(draw, size, padding_ratio=0.20)
    else:
        # Any-Purpose: groesseres Padding, gibt Browser-Default-Maske Platz.
        _draw_einkaufskorb(draw, size, padding_ratio=0.14)

    img.save(path, format="PNG", optimize=True)
    print(f"  → {path} ({size}x{size}, maskable={maskable})")


if __name__ == "__main__":
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    print("Generiere essen-einkauf-PWA-Icons (ESSEN-33)…")
    make_icon(192, os.path.join(here, "icon-192.png"),           maskable=False)
    make_icon(512, os.path.join(here, "icon-512.png"),           maskable=False)
    make_icon(512, os.path.join(here, "icon-maskable-512.png"),  maskable=True)
    print("Fertig.")
