#!/usr/bin/env python3
"""_make_icons.py — Generiert die drei PWA-Pflicht-Icons fuer die Connector-PWA.

CONN-8 / PWAM-2: 192x192, 512x512, maskable-512 (PWAM-2-Pflichtfelder).
Brand-Token: Olivgruen (#47503C, analog App-Panel), Sand-Hintergrund (#F5F1E8).
Symbol: stilisierter Stecker (Plug) — steht fuer "Connector / Anbieter-Verbindung".

Wird einmal vor dem Commit ausgefuehrt; PNG-Output ist Bytes-stabil
(deterministische PIL-Draw-Operationen ohne Anti-Alias-Randomness).

Lauf:  cd seiten/static/connector/ && python3 _make_icons.py
Dann:  PNG-Dateien committen, Skript bleibt als Quelle der Wahrheit
       fuer spaetere Brand-Tweaks.
"""

from PIL import Image, ImageDraw

# XBuddy-Brand-Tokens (analog einkauf/_make_icons.py)
THEME_COLOR  = "#47503C"   # Olivgruen — Vordergrund-Symbol
ACCENT_COLOR = "#D87A3E"   # warmes Orange — Akzent (Stecker-Stifte)
BG_COLOR     = "#F5F1E8"   # Sand — Hintergrund


def _draw_stecker(draw, size, *, padding_ratio=0.18):
    """Stilisierter Stecker (Plug): zwei Stifte + breiter Koerper + Kabel-Ausgang.

    Geometrie skaliert mit size; padding_ratio laesst Rand frei (wichtig fuer
    maskable-Icon-Variante — Android-Launcher schneidet die aeusseren ~20% weg).
    """
    s = size
    p = int(s * padding_ratio)
    inner = s - 2 * p
    center_x = p + inner // 2

    # ── Zwei Stifte (Prongs) ─────────────────────────────────────────────────
    prong_w = max(3, int(inner * 0.13))
    prong_h = max(4, int(inner * 0.20))
    prong_gap = max(3, int(inner * 0.10))   # Abstand vom Mittelpunkt

    prong_y0 = p + int(inner * 0.04)
    prong_y1 = prong_y0 + prong_h

    lp_x0 = center_x - prong_gap - prong_w
    lp_x1 = center_x - prong_gap
    rp_x0 = center_x + prong_gap
    rp_x1 = center_x + prong_gap + prong_w

    draw.rectangle([lp_x0, prong_y0, lp_x1, prong_y1], fill=THEME_COLOR)
    draw.rectangle([rp_x0, prong_y0, rp_x1, prong_y1], fill=THEME_COLOR)

    # Akzent-Punkte an den Stift-Spitzen (orange, wie Kupfer-Kontakte)
    tip_r = max(2, int(inner * 0.04))
    for x0, x1 in [(lp_x0, lp_x1), (rp_x0, rp_x1)]:
        cx = (x0 + x1) // 2
        draw.ellipse([cx - tip_r, prong_y0 - tip_r,
                      cx + tip_r, prong_y0 + tip_r], fill=ACCENT_COLOR)

    # ── Breiter Stecker-Koerper ───────────────────────────────────────────────
    body_x0 = p + int(inner * 0.12)
    body_x1 = p + int(inner * 0.88)
    body_y0 = prong_y1
    body_y1 = p + int(inner * 0.72)
    draw.rectangle([body_x0, body_y0, body_x1, body_y1], fill=THEME_COLOR)

    # ── Kabel-Ausgang (schmales Rechteck unter dem Koerper) ───────────────────
    cord_w = max(3, int(inner * 0.10))
    cord_x0 = center_x - cord_w // 2
    cord_x1 = center_x + cord_w // 2
    cord_y0 = body_y1
    cord_y1 = p + int(inner * 0.90)
    draw.rectangle([cord_x0, cord_y0, cord_x1, cord_y1], fill=THEME_COLOR)

    # ── Kleine Verbindungs-Linie im Koerper (Akzent-Querbalken) ──────────────
    bar_h = max(2, int(inner * 0.04))
    bar_margin = int(inner * 0.08)
    bar_y = body_y0 + (body_y1 - body_y0) // 2 - bar_h // 2
    draw.rectangle(
        [body_x0 + bar_margin, bar_y,
         body_x1 - bar_margin, bar_y + bar_h],
        fill=ACCENT_COLOR,
    )


def make_icon(size, path, *, maskable=False):
    """Erzeugt ein PWA-Icon der gegebenen Groesse als PNG.

    maskable=True: kein zusaetzliches Padding (Symbol fuellt die Safe-Area),
    Hintergrund vollflaechig — Android-Launcher schneidet seine Maske ein.
    """
    img = Image.new("RGBA", (size, size), BG_COLOR)
    draw = ImageDraw.Draw(img)

    if maskable:
        # Maskable: kleineres Padding, Symbol darf bis ~5% an den Rand.
        _draw_stecker(draw, size, padding_ratio=0.20)
    else:
        # Any-Purpose: groesseres Padding, gibt Browser-Default-Maske Platz.
        _draw_stecker(draw, size, padding_ratio=0.14)

    img.save(path, format="PNG", optimize=True)
    print(f"  -> {path} ({size}x{size}, maskable={maskable})")


if __name__ == "__main__":
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    print("Generiere connector-PWA-Icons (CONN-8 / PWAM-2)...")
    make_icon(192, os.path.join(here, "icon-192.png"),           maskable=False)
    make_icon(512, os.path.join(here, "icon-512.png"),           maskable=False)
    make_icon(512, os.path.join(here, "icon-maskable-512.png"),  maskable=True)
    print("Fertig.")
