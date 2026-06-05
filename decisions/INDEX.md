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
| RAT-3 | KI-zu-API: kanonisches Tool-Modell, **keine** MCP-/Skill-Zwischenschicht | 2026-06-05 | Zwischen Eltern-Chat-KI und Buddy-APIs kommt keine MCP-Schicht (nicht ZDR-fähig, Provider-Adapter-Umbau ungerechtfertigt); KI ruft über bestehende `tool_use`-Skill-Adapter (HTTP). Schließt #278 Thema B. | `eltern-chat/model.py`, `providers/claude.py`, `agent.py`; `specs/platform/eltern-chat.md`; #278 (geschlossen) | [RAT-3](RAT-3-ki-zu-api-keine-mcp-schicht.md) |
| RAT-4 | Plan-Buddy Slot-Modell familien-spezifisch (`cycle` pro Slot) — **defer** | 2026-06-05 | Jetzt NICHT bauen: per-Slot-`cycle` verschiebt E-PLAN-8 (Familienroutinen bleiben Code, Generalisierung erst bei Trigger); kein belegter Familie-3-Fall. Reopen erst bei echtem Familie-3-Fork (>3 Code-Stellen) oder bewusstem E-PLAN-8-Neuzug. Parkt #259. | `plan/config.py`, `render.py`, `main.py`, `plan_kinder.html`; `specs/buddies/plan.md` (PLAN-7/E-PLAN-8/PLAN-30); #259 | [RAT-4](RAT-4-259-slot-modell-defer.md) |
| RAT-5 | Router generisches Event-Modell (ROU-27/28) — **defer** | 2026-06-05 | Jetzt NICHT speccen: Routing-Kern ist schon descriptor-agnostisch (ROU-2, E-ROU-8 bewusste Pfad-Trennung), Figuren-Erkennung aktuell nicht im MVP. Reopen erst bei echtem 3. Controller, der einen dritten apply_*-Pfad erzwingt; ROU-27 muss dann E-PANEL-5 schützen. Parkt #65. | `router/main.py`; `specs/platform/router.md` (ROU-2/9/24/E-ROU-8); `app-panel.md` (E-PANEL-5); #65 | [RAT-5](RAT-5-65-event-modell-defer.md) |
