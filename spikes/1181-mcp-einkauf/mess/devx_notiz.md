# Dev-Erfahrung: MCP vs. tool_use-Skill-Adapter (AC-4, qualitativ)

Erfahrungsbericht aus dem Bau dieses Spikes, gegen den bestehenden
Skill-Adapter-Stil (eltern-chat/skills/essen_client.py + tasks.py-Katalog).

## MCP-Server bauen (dieser Spike)

- **mcp-SDK**: `uv pip install mcp` (1.28.1) zog 20+ transitive Deps
  (starlette, uvicorn, httpx, pydantic, sse-starlette, anyio …). Im
  Spike-venv bewusst isoliert — NICHT in requirements/Repo-Deps (RAT-3-Scope:
  kein Produktiv-Rollout). Für den realen Einsatz wäre das ein erheblicher
  neuer Dependency-Block in einem Repo, das heute mit reiner stdlib + flask
  + anthropic auskommt.
- **FastMCP-Dekorator** (`@mcp.tool()`) ist angenehm knapp: Funktion +
  Docstring → Tool-Schema wird aus Signatur + Typannotationen generiert. Das
  ist DX-seitig schöner als der manuelle TaskDef(parameters=…)-JSON-Schema-Stil
  in tasks.py.
- **ABER**: das Schema-Generieren ist Magie, die man nicht steuert. Der
  bestehende Stil (handgeschriebenes input_schema in tasks.py) ist
  expliziter und liegt direkt neben der DCOMP-/Klasse-Logik (READ/WRITE),
  die MCP gar nicht kennt.

## Skill-Adapter-Stil (Status quo)

- EssenClient ist ein ~540-Zeilen-HTTP-Client mit einer Fehler-Klasse
  (EssenClientError + Marker), Test-Naht (transport=Callable), 2-s-Timeout —
  CLIENT-1..4-Konvention. Bekannt, getestet, lokal lesbar.
- Neuer Buddy-Tool-Punkt = eine Methode + ein TaskDef im Katalog. Kein
  zweiter Prozess, kein Transport, kein async.
- Die KI sieht über claude.py:_to_anthropic_tool ohnehin nur normale
  tool_use-Blöcke — derselbe Token-Aufschlag wie bei MCP (siehe
  mess_token_delta).

## Async-Bruch (der eigentliche DX-Schmerz)

- Der mcp-Python-Client ist **async-only** (`async with stdio_client`,
  `ClientSession`, `await session.call_tool`). eltern-chat/agent.py ist
  **rein synchron** (0 async/await/asyncio — verifiziert).
- Einen lokalen MCP-Client in den synchronen Agent-Loop zu heben heißt
  entweder `asyncio.run()` pro Tool-Call (Event-Loop-Auf-/Abbau pro Aufruf)
  ODER agent.py auf async umbauen — und „HFE synchron blockt Chat-Turn"
  (project_hfe_folgenverlust / feedback_hfe_synchron) zeigt, dass die
  Sync/Async-Grenze in genau diesem Loop schon ein wunder Punkt ist.

## Fazit DX

MCP-Server-Bauen fühlt sich pro Tool minimal angenehmer an (Dekorator-Magie),
kostet aber: großer neuer Dependency-Block, ein zweiter Transport + Prozess-
Lebenszyklus, und einen async-Bruch gegen den synchronen Agent-Loop. Der
Skill-Adapter-Stil ist mehr Tipparbeit pro Tool, aber bleibt in einem Prozess,
einer Sprache (sync), einem Dependency-Set — und produziert für die KI
denselben tool_use-Block. Netto-DX-Gewinn von MCP für diesen Anwendungsfall:
nicht erkennbar; Netto-DX-Kosten: real.

> Verzerrungs-Hinweis: Der uv-Pull der mcp-SDK gelang (kein hand-gerollter
> JSON-RPC-Fallback nötig), die DX-Bewertung beruht also auf der echten SDK.
