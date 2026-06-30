# EC-12 / Datenretention: belegt (AC-6)

RAT-3s tragendes Argument war Privacy/ZDR (EC-12/E-EC-4, Datenretention): der
**gehostete** Anthropic-MCP-Connector nutzt eigene MCP-Blöcke (Beta
`mcp-client-2025-11-20`) und ist **nicht ZDR-fähig** — für Kinderdaten ein
Bruch. RAT-3-Reopen fragt: vermeidet die **lokale** Form diesen Bruch wirklich?

## Datenfluss in der lokalen Form (gemessen/gebaut)

```
eltern-chat (Pi)
   └─ MCP-Client (lokal)  ──stdio ODER HTTP 127.0.0.1:5191──▶  MCP-Server (Pi)
                                                                  └─ EssenClient
                                                                       └─ HTTP 127.0.0.1:5152
                                                                            └─ Essen-Buddy (Pi)
```

**Alles auf 127.0.0.1, alles auf dem Pi.** Die MCP-Schicht (Client + Server)
liegt vollständig zwischen zwei lokalen Prozessen. Familien-/Kinderdaten
verlassen die Maschine an **derselben** Grenze wie heute: erst wenn die KI im
`tool_use`-Loop die Anthropic-API ruft (claude.py), gehen Daten nach außen — und
das ist exakt der Pfad, den das kanonische Skill-Adapter-Modell heute auch geht.

## Was retainiert (auch lokal/Logs)

- **MCP-Server-Prozess**: hält keine Persistenz; er wrappt nur EssenClient-
  HTTP-Calls. Im Spike sah man `Processing request of type CallToolRequest`
  auf stderr — d. h. die MCP-Schicht **loggt Tool-Aufrufe** (Default-Logging
  der SDK). Tool-NAMEN und -Zeitpunkte landen also in einem weiteren Log;
  Tool-ARGUMENTE (z. B. `label`, `item_id`) können je nach Loglevel
  mitlaufen. Das ist eine **zusätzliche lokale Log-Oberfläche**, die heute
  nicht existiert — retentions-/redaktionspflichtig wie jeder Buddy-Log.
- **Essen-Buddy (5152/Produktiv 5052)**: die Daten-Persistenz (wuensche.json
  etc.) ist unverändert — die MCP-Schicht fügt dort nichts hinzu.
- **Kein gehosteter Connector, kein ZD-Store-als-Tool**: im Spike bewusst
  nicht gebaut (RAT-3-Scope + stop_rule rat3_breach). Der Schreib-Tool-Pfad
  lief ausschließlich gegen die isolierte Scratch-essen-Instanz (Port 5152,
  ESSEN_*_FILE→scratch-data/); Produktiv-5052 wurde nie berührt (verifiziert:
  0 Spike-Treffer auf 5052).

## Befund EC-12

Die **lokale** MCP-Form vermeidet den EC-12-Bruch des gehosteten Connectors:
- Keine `mcp-client`-Beta-Blöcke Richtung Anthropic; das Modell sieht nur
  normale `tool_use` (ZDR-Status identisch zu heute).
- Datengrenze unverändert (erst bei der Anthropic-API, wie beim Skill-Adapter).

ABER sie führt **eine neue lokale Retentions-Oberfläche** ein: die
MCP-Schicht-Logs (Tool-Namen, ggf. -Argumente). Das ist kein ZDR-Bruch, aber
ein zusätzlicher Datenpunkt, der unter die Pi-Log-Retention/Redaktion fallen
muss. Netto: RAT-3s Privacy-Argument trifft die lokale Form **nicht** — der
ZDR-Bruch war spezifisch der gehostete Connector.

## RAT-3-Konformität dieses Spikes

- Lokal, Client+Server auf 127.0.0.1. ✓
- Kein gehosteter Connector. ✓
- Kein Zugangsdaten-Store als Tool. ✓
- Kein Produktiv-Rollout; Schreibpfad nur gegen Scratch-5152. ✓
- EC-12 + Provider-Umbau mitgemessen (diese Datei + provider_umbau_befund.md). ✓
