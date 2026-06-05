# Ratifizierungs-Ledger — Index

SSoT für „was ist entschieden". Jede Zeile = eine ratifizierte Architektur-/
Design-Entscheidung. Volle Deliberation als Evidenz in `brainstorm/berater-runde/`
(verlinkt im jeweiligen Record). Modell + Spielregeln: [README.md](README.md).

> Re-Litigations-Check: Bevor eine Frage neu beraten wird, hier prüfen, ob sie
> schon entschieden ist. Diese Liste ist der Anker dafür.

| ID | Thema | Entschieden | Beschluss (1 Satz) | Betrifft | Record |
|----|-------|-------------|--------------------|----------|--------|
| RAT-1 | Panel-Registry-API (Controller-Lego-Stein) | 2026-06-03 | Eigener Service `xbuddy-panel` (Plattform-Port) mit `panels.json`; Router proxyt + cacht `config.json`/`tiles.json`; Multi-Controller über unabhängige Panel-IDs. | `specs/platform/panel-registry.md`, `specs/.../app-panel.md`, `router.md`, `ports.md`, `urls.md`; #329 (Welle 2) | [RAT-1](RAT-1-panel-registry-api.md) |
| RAT-2 | #328 — Garderoben-Regeln im Eltern-Chat pflegbar | 2026-06-05 | Eltern-Chat liefert **Link** zu einer eltern-seitigen, mobil-tauglichen Web-Seite im Wetter-Buddy, die die Regelmatrix **zeigt UND editiert** (kein PNG, kein Chat-Schreibdialog). Auth = Heimnetz/Tailscale-Grenze. | `specs/buddies/wetter.md` (WETTER-26, Entwurf); #328 | [RAT-2](RAT-2-328-garderoben-regelmatrix.md) |
