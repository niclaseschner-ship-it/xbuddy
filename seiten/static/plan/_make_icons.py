#!/usr/bin/env python3
"""_make_icons.py — Generiert die drei PWA-Pflicht-Icons fuer plan-einstellungen.

PLAN-35: 192x192, 512x512, maskable-512 (PWA-2-Pflichtfelder).
Brand-Token: Olivgruen (#47503C, analog App-Panel), Sand-Hintergrund (#F5F1E8).
Symbol: stilisierter Kalender (Plan-Buddy).

Wird einmal vor dem Commit ausgefuehrt; PNG-Output ist Bytes-stabil
(deterministische PIL-Draw-Operationen ohne Anti-Alias-Randomness).

Lauf:  cd seiten/static/plan/ && python3 _make_icons.py
       oder: python3 seiten/static/plan/_make_icons.py
Dann:  PNG-Dateien committen, Skript bleibt als Quelle der Wahrheit
       fuer spaetere Brand-Tweaks.
"""

from PIL import Image, ImageDraw

# XBuddy-Brand-Tokens (analog controller/app-panel/manifest.json)
THEME_COLOR  = "#47503C"   # Olivgruen — Vordergrund-Symbol
ACCENT_COLOR = "#D87A3E"   # warmes Orange — Akzent (Kalender-Kopf)
BG_COLOR     = "#F5F1E8"   # Sand — Hintergrund


def _parse_hex(hex_color):
    """Konvertiert #RRGGBB zu (R, G, B)-Tuple."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _draw_kalender(draw, size, *, padding_ratio=0.14):
    """Stilisierter Kalender: Rahmen, Kopf-Balken, Ring-Oesen, Kalender-Grid.

    Geometrie skaliert mit size; padding_ratio laesst Rand frei (wichtig fuer
    maskable-Icon-Variante — Android-Launcher schneidet die aeusseren ~20% weg).
    """
    s = size
    p = int(s * padding_ratio)
    inner = s - 2 * p

    theme = _parse_hex(THEME_COLOR)
    accent = _parse_hex(ACCENT_COLOR)
    bg = _parse_hex(BG_COLOR)

    # Gesamt-Kalender-Rahmen (abgerundetes Rechteck)
    kal_left   = p
    kal_top    = p + int(inner * 0.08)
    kal_right  = p + inner
    kal_bottom = p + inner

    radius = max(4, int(inner * 0.08))

    # Hintergrund-Rechteck (Kalender-Koerper)
    draw.rounded_rectangle(
        [kal_left, kal_top, kal_right, kal_bottom],
        radius=radius,
        fill=bg,
        outline=theme,
        width=max(2, int(inner * 0.04)),
    )

    # Kopf-Balken (Accent-Farbe — obere ~22% des Kalenders)
    kopf_height = int((kal_bottom - kal_top) * 0.22)
    kopf_bottom = kal_top + kopf_height

    draw.rounded_rectangle(
        [kal_left, kal_top, kal_right, kopf_bottom + radius],
        radius=radius,
        fill=accent,
    )
    # Unterkante des Kopfs gerade (kein Rundung unten)
    draw.rectangle(
        [kal_left + 1, kopf_bottom - radius, kal_right - 1, kopf_bottom],
        fill=accent,
    )

    # Ring-Oesen (zwei Spiralbindungs-Punkte, oben aus dem Rahmen ragend)
    ring_y_top = kal_top - int(inner * 0.06)
    ring_y_bot = kal_top + int(inner * 0.06)
    ring_thick = max(2, int(inner * 0.04))

    # Linker Ring
    ring_x1_l = kal_left + int(inner * 0.22)
    ring_x2_l = kal_left + int(inner * 0.36)
    draw.ellipse(
        [ring_x1_l, ring_y_top, ring_x2_l, ring_y_bot],
        outline=theme,
        width=ring_thick,
    )

    # Rechter Ring
    ring_x1_r = kal_left + int(inner * 0.64)
    ring_x2_r = kal_left + int(inner * 0.78)
    draw.ellipse(
        [ring_x1_r, ring_y_top, ring_x2_r, ring_y_bot],
        outline=theme,
        width=ring_thick,
    )

    # Kalender-Grid: 3x3 Zellen (Wochentage)
    grid_left   = kal_left  + int(inner * 0.08)
    grid_right  = kal_right - int(inner * 0.08)
    grid_top    = kopf_bottom + int((kal_bottom - kopf_bottom) * 0.12)
    grid_bottom = kal_bottom  - int((kal_bottom - kopf_bottom) * 0.10)

    grid_w = grid_right - grid_left
    grid_h = grid_bottom - grid_top

    cols = 3
    rows = 3
    cell_w = grid_w / cols
    cell_h = grid_h / rows

    dot_r = max(2, int(min(cell_w, cell_h) * 0.22))

    for row in range(rows):
        for col in range(cols):
            cx = int(grid_left + (col + 0.5) * cell_w)
            cy = int(grid_top  + (row + 0.5) * cell_h)
            # Erste Reihe: Theme-Farbe (Wochentag-Label-Anmutung)
            # Restliche: etwas heller (Tages-Zahlen)
            fill = theme if row == 0 else tuple(int(c * 0.55 + int(bg[i]) * 0.45)
                                                 for i, c in enumerate(theme))
            draw.ellipse(
                [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                fill=fill,
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
        _draw_kalender(draw, size, padding_ratio=0.18)
    else:
        # Any-Purpose: groesseres Padding, gibt Browser-Default-Maske Platz.
        _draw_kalender(draw, size, padding_ratio=0.12)

    img.save(path, format="PNG", optimize=True)
    print(f"  → {path} ({size}x{size}, maskable={maskable})")


if __name__ == "__main__":
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    print("Generiere plan-einstellungen-PWA-Icons (PLAN-35)…")
    make_icon(192, os.path.join(here, "icon-192.png"),           maskable=False)
    make_icon(512, os.path.join(here, "icon-512.png"),           maskable=False)
    make_icon(512, os.path.join(here, "icon-maskable-512.png"),  maskable=True)
    print("Fertig.")
