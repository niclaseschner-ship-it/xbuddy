#!/usr/bin/env python3
"""_make_icons.py — Generiert die drei PWA-Pflicht-Icons fuer routine-anpassen.

ROUTINE-23: 192x192, 512x512, maskable-512 (PWAM-2-Pflichtfelder).
Brand-Token: Olivgruen (#47503C), Sand-Hintergrund (#F5F1E8).
Symbol: ARASAAC-Morgenroutine-Piktogramm (Aufgabenliste / Routine).

PLATZHALTER: V1 kopiert Plan-Kalender-Icons (T1665 Handoff-Notiz: eigenes
Routine-Motiv folgt als Mini-Folge-Ticket). Installierbar (PWA-2 erfuellt).

Lauf:  cd seiten/static/routine/ && python3 _make_icons.py
       oder: python3 seiten/static/routine/_make_icons.py
Dann:  PNG-Dateien committen, Skript bleibt als Quelle der Wahrheit
       fuer spaetere Brand-Tweaks (routine-Motiv).
"""

# V1-Platzhalter: Plan-Kalender-Icons wiederverwendet (T1665).
# Fuer eigenes Routine-Motiv: ARASAAC-ID fuer "Morgenroutine" einbauen und
# analoges Skalierungs-Skript wie seiten/static/plan/_make_icons.py anwenden.

if __name__ == "__main__":
    print("Platzhalter-Icons bereits vorhanden (aus plan/ kopiert).")
    print("Fuer eigenes Routine-Motiv: ARASAAC-ID einbauen und skripten.")
