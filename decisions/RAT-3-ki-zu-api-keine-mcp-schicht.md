# RAT-3 — KI-zu-API bleibt kanonisches Tool-Modell, keine MCP-/Skill-Zwischenschicht

- **Entschieden:** 2026-05-31 (Berater-Verdikt, Lego-Vertrag-Runde),
  **ratifiziert** 2026-06-05 (Nic, beim `/arbeitstag-prep`).
- **Betrifft:** `eltern-chat/model.py`, `eltern-chat/providers/claude.py`,
  `eltern-chat/agent.py`; das kanonische Tool-Modell in `specs/platform/eltern-chat.md`
  (EC-12/E-EC-4, Datenretention). Schließt **#278** Thema B.
- **Transkript (Evidenz):** `brainstorm/berater-runde/2026-05-31-1949-antiberater-lego-vertrag-skalierbar.md`,
  Abschnitt **»[RISKANT] γ/MCP wird korrekt abgelehnt, aber teils aus falschem Grund«**
  → Vorschlag `20260531-vorschlag-lego-vertrag-skalierbar.md`.

## Beschluss

Zwischen der Eltern-Chat-KI und den Buddy-APIs kommt **keine MCP-/Skill-Zwischen­schicht**
(kein Anthropic-MCP-Connector, kein MCP-Server pro App). Der Eltern-Chat behält sein
**kanonisches Tool-Modell**: das Modell sieht nur normale Anthropic `tool_use`-Blöcke
(`eltern-chat/model.py:71-80`, `eltern-chat/providers/claude.py:134-159`), die KI ruft
Buddy-Funktionen über die bestehenden **Skill-Adapter** (HTTP zu den Buddy-APIs, DCOMP-treu),
nicht über eine generische MCP-Tool-Schicht.

## Warum

- **Privacy/ZDR ist das tragende Argument** (nicht Prozess-Inflation, die der Berater
  ausdrücklich relativiert hat): Der Anthropic-MCP-Connector nutzt eigene MCP-Blöcke,
  aktuelle Beta `mcp-client-2025-11-20`, und ist **nicht ZDR-fähig** — für einen
  Familien-Hub mit Kinderdaten ein Bruch (EC-12/E-EC-4, Datenretention).
- **Umbau des kanonischen Provider-Modells nicht gerechtfertigt:** Ein einziger
  MCP-Tool-Call gegen den bestehenden `ClaudeProvider` zwingt Änderungen an
  `model.py`, `providers/claude.py`, `agent.py` und den EC-10-Tests — hoher Umbau
  ohne belegten Nutzen gegenüber dem HTTP-Skill-Adapter.
- **Der Berater hat die Wiederauferstehung vorhergesagt:** »γ wird später mit
  ‚geht ja ohne extra Prozess' rehabilitiert, ohne EC-12/E-EC-4, Datenretention und
  Provider-Adapter-Umbau zu prüfen.« Genau dieses Déjà-vu beendet RAT-3.

## Re-Litigation nur bei belegtem neuem Bruch

Diese Frage gilt als **entschieden**. Neu aufmachen nur, wenn beides belegt ist:
(a) der MCP-Connector wird **ZDR-fähig** (raus aus Beta, Datenretention geklärt),
**und** (b) ein konkreter Use-Case zeigt, dass das kanonische `tool_use`-Skill-Adapter-Modell
ihn nicht trägt. Andernfalls: schließen mit Verweis auf RAT-3.
