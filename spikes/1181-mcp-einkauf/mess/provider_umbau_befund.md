# Provider-Adapter-Umbau: belegt (AC-5)

RAT-3s zweite Wieder-Aufmach-Bedingung verlangt zu prüfen, ob der **lokale**
MCP-Client Änderungen an `model.py` / `providers/claude.py` / `agent.py` +
EC-10-Tests erzwingt — oder sauber außerhalb des `ClaudeProvider` lebt. Nur
gelesen/belegt, NICHT geändert (forbidden_files: eltern-chat Edit).

## Die kanonische Tool-Naht (1:1-Vergleichspunkt)

`eltern-chat/model.py` definiert `TaskDef(name, description, kind, parameters)`
(model.py:70-79). `eltern-chat/providers/claude.py:142-150`
`_to_anthropic_tool` übersetzt das in den Anthropic-Tool-Dict
(`{name, description, input_schema}`). Der Agent-Loop ruft in
`agent.py:436` `catalog.task_defs()` und reicht sie über
`GenerationRequest.task_defs` (agent.py:481) an `provider.generate`
(agent.py:304).

## Was der lokale MCP-Client NICHT anfasst

- **`providers/claude.py`**: unverändert. Das Modell sieht in der lokalen
  MCP-Form **dieselben** `tool_use`-Blöcke wie heute — die Anthropic-API kennt
  kein MCP (der gehostete Connector ist via RAT-3 verboten). MCP-Tool-Schemas
  müssten ohnehin nach `TaskDef` → `_to_anthropic_tool` übersetzt werden. Die
  Provider-Naht bleibt der Engpass, durch den alles läuft.
- **`model.py`**: unverändert. `TaskDef`/`GenerationRequest`/`GenerationResponse`
  bleiben das anbieter-neutrale Modell; MCP-Tools werden in `TaskDef` gegossen.
- **EC-10-Provider-Tests**: unverändert — der Provider-Vertrag ändert sich nicht.

→ RAT-3s ursprüngliche, schärfste Befürchtung („ein einziger MCP-Tool-Call
zwingt Änderungen an model.py/claude.py + EC-10-Tests") **materialisiert sich in
der lokalen Form NICHT.** Das ist das ehrliche Entlastungs-Ergebnis für die
lokale Prämisse.

## Was der lokale MCP-Client DOCH erzwingt (der reale Delta)

- **`agent.py` / `tasks.py` — Tool-Discovery + Dispatch:**
  Heute liefert `catalog.task_defs()` die Tools statisch aus tasks.py, und
  `catalog.execute_write_task` / `task.run` (tasks.py:170/253) ruft die
  Skill-Adapter (EssenClient) **direkt** auf. Für MCP müsste die
  Discovery über einen `list_tools`-Handshake laufen und der Dispatch die
  Calls an `mcp.ClientSession.call_tool` routen statt an den Direkt-Client.
  Das ist neuer Glue-Code im Agent-Loop — plus neue Dispatch-Tests (nicht
  EC-10-Provider-Tests).
- **async-Bruch in `agent.py`:** Der mcp-Python-Client ist async-only;
  `agent.py` ist rein synchron (0 async/await/asyncio — verifiziert). Der
  lokale MCP-Client zwingt `asyncio.run()` pro Tool-Call (Event-Loop-
  Auf/Abbau) ODER einen async-Umbau des Agent-Loops — der gleiche wunde
  Punkt wie „HFE synchron blockt Chat-Turn".

## Befund

Die lokale MCP-Form **entlastet** RAT-3 an der Stelle, an der es am meisten
befürchtet wurde (Provider-Adapter/model.py/claude.py/EC-10 unverändert) —
**verlagert** die Umbau-Kosten aber in den Tool-Discovery/Dispatch-Layer von
agent.py/tasks.py und in einen sync→async-Bruch. Der Umbau ist also real,
nur an einer anderen Datei als RAT-3 formuliert hatte.
