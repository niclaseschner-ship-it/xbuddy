# RAT-1 — Panel-Registry-API (Controller-Lego-Stein)

- **Entschieden:** 2026-06-03 (Nic), Brett-Runde Berater + Codex-Antiberater.
- **Betrifft:** `specs/platform/panel-registry.md`, `app-panel.md`, `router.md`,
  `ports.md`, `urls.md`; Welle 2 = #329 (Panel-Routing-Reconcile).
- **Transkript (Evidenz):** `brainstorm/berater-runde/2026-06-03-RATIFIZIERT-panel-registry-api.md`
  → Vorschlag `20260602-2350-vorschlag-panel-registry-api.md`,
  Antiberater `2026-06-03-0907-antiberater-panel-registry-api.md`.

## Beschluss

Eigener Service **`xbuddy-panel`** auf einem **Plattform-Port** (nicht aus dem
Buddy-Reserveblock 5030/5050–5099 — neben der Geräte-Registry :5040), mit
`panels.json` als Registry aller Instanzen (gitignored, atomar geschrieben,
Reload, last-known-good). Der Router serviert weiter `index.html` + statischen
Code, **proxyt** aber `GET /controller/app-panel/<id>/config.json|tiles.json` an
den panel-Service (`<panel_id>` wird load-bearing) und **cacht** die Antwort
(last-known-good). Multi-Controller pro Gerät über unabhängige Panel-IDs/URLs
(je eigene WebAPK). Ein Panel referenziert das **Display** (Kachel-Ziel), nicht
das Controller-Gerät. API analog GER-13/14/15.

## Warum

- **Eigener Service statt Router-Inline:** Panels sind Per-Instanz-Daten — gehören
  als Registry neben den Code, nicht in Router-Konstanten (CLAUDE.md §6, Daten vs. Code).
- **Plattform-Port, nicht Buddy-Block:** `5050` ist für Buddys reserviert
  (`ports.md`), Wetter zielt dorthin (WETTER-22) — Kollision vermeiden.
- **Router cacht (last-known-good):** sonst lädt ein Controller bei panel-Service-
  Ausfall Demo-Defaults + leere Tiles.
- **Validierung gegen die Geräte-Registry (GER), nicht `known_displays`:** sonst wird
  das erste Panel für ein frisch angelegtes Display abgelehnt.
- **Router-Schreib-API loopback-/`/admin/`-geschützt:** nicht offen im Familien-LAN;
  nur der panel-Service ruft sie.

## Schnitt

- **Welle 1 (rework-frei):** Service + `panels.json` · API `list/get/config/tiles` +
  `POST` anlegen · Router-Schreib-API (loopback, GER-validiert) · instanz-fähiges
  Serving (Proxy + Cache) · nginx URL-14-Zeile · Demo-Migration.
- **Welle 2 (#329):** copy/delete/Tile-Editing · Reconcile-/Reparatur-Pfad der
  verteilten 2-Schritt-Anlage · Eltern-Chat-Skill (+ `panel_client.py`) · Tile-Sets ·
  optional `geraet_id`-Metadatum.

E-PANEL-3-Trennung (tiles änderbar / config nicht übermalbar) bleibt im Datenmodell
erhalten; Welle-2-Tile-Editing fasst die Router-Kante (ROU-18) nicht an.
