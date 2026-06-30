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

## Reopen — bedingt und eng geschnitten für einen Mess-Spike (2026-06-30, Nic)

Nic hat RAT-3 am 2026-06-30 (beim `/arbeitstag-prep`) **bedingt reopnet**. Anlass:
die **lokale, client-seitige MCP-Form** war 2026-05-31 nicht evaluiert — der
damalige ZDR-Bruch betraf ausschließlich den **gehosteten** Anthropic-`mcp-client`-
Connector. Bei einem MCP-Server, den der Pi selbst betreibt (Client lokal,
Server auf `localhost`, **kein** gehosteter Connector, **kein** Zugangsdaten-Store
als Tool), fließen die Daten dieselbe Grenze wie heute (`tool_use` → Skill-Adapter
→ API). Diese neue Prämisse rechtfertigt einen **Mess-Spike**, um die Reopen-
Bedingung (b) (belegter Use-Case-Nutzen) überhaupt mit Zahlen füllen zu können.

**Scope des Reopen:** NUR der Mess-Spike **#1181** (Vehikel einkauf-Buddy, lokal,
ohne ZD-Store, **kein** Produktiv-Rollout). Der Spike **muss** RAT-3s ursprüngliche
Gründe **mitmessen**, nicht umgehen:
- **EC-12/Datenretention** — wo fließen die Daten in der lokalen Form genau hin,
  retainiert irgendetwas (auch lokal/Logs)? Belegen, dass die lokale Form den
  EC-12-Bruch wirklich vermeidet.
- **Provider-Adapter-Umbau** — zwingt der lokale MCP-Client Änderungen an
  `model.py`/`providers/claude.py`/`agent.py` + EC-10-Tests, oder lebt er sauber
  außerhalb des `ClaudeProvider`?

**Weiterhin GESCHLOSSEN ohne neue Ratifizierung:** „MCP-Server pro App" als
**Produktiv-Architektur** und der **gehostete** Anthropic-MCP-Connector. Die
Architektur-Entscheidung (pro-Buddy / Aggregator / Hybrid) fällt erst nach den
Spike-Zahlen über die #1164-Linie.
