"""Photo-Buddy — die XBuddy-App mit dem Buddy-Slug `photo` (PHOTO-1).

Siehe specs/buddies/photo.md. Der Photo-Buddy ist ein digitaler
Bilderrahmen: er besitzt seine Daten (die Medien-Library, PHOTO-7), seine
Funktion (Ingest + Normalisierung Abschnitt 4, Durchlauf Abschnitt 1) und
stellt das Ergebnis über seine Display-View `rahmen` bereit (PHOTO-2, APP-1).

Modul-Aufteilung (eine Verantwortung je Modul, CLAUDE.md §6; einseitige
Abhängigkeiten, keine Zyklen):

  config     — Daten-/Verhaltens-Konfig (photo.json), ConfigError (PHOTO-19)
  store      — Library-Index (library.json) + atomares add/delete + Reihenfolge
               (PHOTO-7/10/11/12)
  normalize  — defensive Normalisierung HEIC→JPEG / HEVC-MOV→MP4 + Thumbnail/
               Poster-Frame + Aufnahmedatum (PHOTO-8/9)
  ingest     — orchestriert normalize → video_max_s-Check → store.add (PHOTO-13)
  render     — View-Modell `rahmen` aus dem geordneten Index (PHOTO-5/6)
  main       — Flask: 5 API-Endpunkte + /display/photo/rahmen (PHOTO-13..16, PHOTO-2)

Abhängigkeitsrichtung: main → {ingest, store, render, config};
ingest → {normalize, store, config}; render → store. Keine Zyklen.
"""
