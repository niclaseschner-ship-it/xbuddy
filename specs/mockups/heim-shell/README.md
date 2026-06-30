# Heim-Shell — Gate-B-Mockups (#1182)

Durabler Gate-B-Beleg (PW-54) für `specs/platform/heim-shell.md` (SHELL).
Ratifiziert 2026-06-30 (Gate B): **Rail 280px, einspaltig** (siehe RAT-25).

- `picker.html` — interaktiver Rail-Breiten-Picker (280 / 320 / 600), gegen
  **echte Daten** gebaut: linke Hälfte = echtes Render von `mias-panel-01`
  (8 echte Tiles + echte ARASAAC-Icons), rechte Hälfte = echtes Render der
  Wochenplan-View (`/display/plan/woche`). Lokal öffnen oder via
  `python3 -m http.server` servieren.
- `assets/rail1col-280.png`, `assets/rail1col-320.png` — Panel einspaltig
  (Rail ≤ ~360px → `computeGridGeometry` reflowt selbst, PANEL-12).
- `assets/panel-600.png` — Panel zweispaltig (Rail 600px, Alternative).
- `assets/buddy-plan.png` — Buddy-Pane-Beispiel (Wochenplan, echtes Render).
- `assets/rendergate-280.png` — **gewählte Variante**, Render-Gate-Komposit
  1920×1200 (Rail 280px + Buddy 1637px).

**Kernbefund:** Das Panel ist robust — es legt seine Kacheln adaptiv nach
Iframe-Breite aus (1 Spalte ab ≤ ~360px), **kein Panel-Code-Change** für die
schmale Rail nötig.
