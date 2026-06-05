# RAT-2 — #328: Garderoben-Regeln im Eltern-Chat pflegbar

- **Entschieden:** 2026-06-05 (Nic), Berater + Codex-Antiberater. Zweistufig.
- **Betrifft:** `specs/buddies/wetter.md` (WETTER-26, **nur Entwurf** — Spec-Landung
  steht aus); Issue #328.
- **Transkript (Evidenz):** `brainstorm/berater-runde/20260605-194834-RATIFIZIERT-328-garderoben-png-render.md`
  → Vorschlag `20260605-194834-vorschlag-...md`, Antiberater `2026-06-05-1949-antiberater-...md`.

> Hinweis: Die Transkript-Dateinamen tragen noch „png-render" — der Beschluss ist
> bewusst von PNG auf Link/Editor umgeschwenkt. Maßgeblich ist dieser Record.

## Beschluss

Der Eltern-Chat schickt einen **Link** zu einer **eltern-seitigen Web-Seite** im
Wetter-Buddy, die die **Garderoben-Regelmatrix zeigt UND editiert** (direkt im
Handy-Browser). Inhalt = die Regelmatrix (Regeln in Reihenfolge × Schwellen:
gefühlte Temperatur, Regenwahrscheinlichkeit/-menge, Wind, Sonne → Kleidungs-Set
pflicht/optional), aus `wetter.json`-Config, **kein Live-Wetter**, **nicht** das
Heute-Outfit. Editieren schreibt `wetter.json` + Reload.

**Verworfen:** PNG-Render (chromium/headless) und der mehrstufige Chat-Schreibdialog.

## Warum

- **Link/Editor statt PNG:** löst den offenen Rand „wie ändert das Elternteil eine
  Regel?" direkt (Web-Bearbeitung) statt über einen fragilen mehrstufigen Chat-Dialog.
- **Damit fallen alle drei Antiberater-Risiken weg** (nicht gelöst — weg): Origin-/
  Shared-Asset-Abhängigkeit, 12s-Open-Meteo-Latenz, Render-Fragilität.
- **Regelmatrix, nicht Heute-Outfit:** Eltern wollen ihre *Regeln* anfassen
  („ab welcher Regenmenge Matschhose? welche Regel gewinnt?"), nicht das ausgewertete
  Tagesergebnis.
- **Keine Kinder-View:** Eltern-Config-Oberfläche, mobil-tauglich, **Scrollen erlaubt** —
  nicht an die Kiosk-Design-Constraints (WETTER-25) gebunden.

## Zugang / Auth

**Keine zusätzliche Sicherung.** Die Seite ist nur im **Heimnetz / über Tailscale**
erreichbar; wer den Link hat, darf editieren. Bedrohungsmodell = „Leute im Haushalt";
das Netz ist die Vertrauensgrenze (Heim-Server-Realität). Leitplanke: die Edit-Seite
darf **nicht** über einen ins Internet exponierten Pfad erreichbar sein
(LAN/Tailscale-Interface, kein Port-Forwarding nach außen).

## Status

WETTER-26 ist **Entwurf** — daher steht #328 auf `status:spec` (nicht ready):
nach WORKFLOW.md heißt `status:ready` „Spec reviewt und gemerged". Erst nach
Spec-Freigabe + Merge wird #328 wieder reif.
