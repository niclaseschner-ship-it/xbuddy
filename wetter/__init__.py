"""Wetter-Buddy-App — XBuddy-App mit Buddy-Slug `wetter` (Refs #137).

Siehe specs/buddies/wetter.md. Die App zeigt einer Familie auf einem
Kiosk-Display, wie das Wetter heute (oder ab Abend: morgen) wird und was das
Kind anziehen soll — ein Diptychon aus Wetter-Karte und Anziehen-Karte
(WETTER-2).

Sie besitzt ihre Daten (Ort + Garderoben-Regeln, WETTER-21) und ihre Funktion
(die Open-Meteo-Anbindung, WETTER-16) und stellt das Ergebnis über ihre
Display-View bereit (WETTER-1, APP-1). Was sie nicht selbst besitzt, holt sie
von zentralen Komponenten: die ARASAAC-Piktogramme von der geteilten
Icon-Plattform (ICONS-5, WETTER-18).

Module:
  config    — Ort, Garderoben-Regeln, Tageszeiten, Rollover (WETTER-21)
  meteo     — Open-Meteo-Anbindung + anbieter-neutrales Modell (WETTER-16/17, Test-Naht)
  clothing  — Garderoben-Regeln-Auswertung (WETTER-14/15)
  render    — View-Modell + HTML der View `heute` (WETTER-2…13, WETTER-18/19)
  main      — Flask-App: Display-View + Entrypoint (WETTER-2/4/6, WETTER-22)
"""
