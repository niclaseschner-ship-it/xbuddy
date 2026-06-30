# BERICHT — MCP-Spike #1181 (Einkauf-Buddy, lokal)

Mess-Spike zur bedingten RAT-3-Wiederaufnahme. Frage: Trägt die **lokale,
client-seitige** MCP-Form einen belegten Use-Case-Nutzen (Reopen-Bedingung b),
ohne RAT-3s Gründe (EC-12/Datenretention, Provider-Adapter-Umbau) zu verletzen?
Beide Transporte (stdio + HTTP/SSE) wurden real gebaut und gegen eine isolierte
Scratch-essen-Instanz (Port 5152) gemessen. Produktiv-5052 nie berührt.

Modell für Token: `claude-opus-4-7` (eltern-chat ClaudeProvider.DEFAULT_MODEL).
Hardware: der reale Pi (Ziel-HW), Messungen via `/proc` (VmRSS/VmHWM).

---

## AC-1 — RAM & Spawn (echte Zahlen, Median über N=7)

| Pfad | RAM | Spawn-Zeit | Extra-Prozess |
|---|---|---|---|
| Interpreter-Boden (nacktes venv-Python) | 8,7 MB (VmHWM) | — | — |
| **stdio** (pro Aufruf gespawnt) | **56,8 MB** Peak-RSS (Δ +48 MB) | **559 ms** Spawn→erster Tool-Call (min 549 / max 600) | +1 pro Turn |
| **HTTP-Dauerdienst** (streamable-http, :5191) | **55,7 MB** idle-RSS (Δ +47 MB), permanent | — (kein Spawn/Turn) | +1 permanent |
| **Baseline Direkt-Adapter** (RAT-3-Status quo) | ~0 marginal (EssenClient läuft im bestehenden eltern-chat-Prozess) | ~0 | **0** |

Der Direkt-Adapter kostet 0 Extra-Prozesse und 0 Spawn — der EssenClient ist ein
stdlib-urllib-Wrapper im schon laufenden eltern-chat-Prozess. Jede MCP-Form fügt
einen ganzen ~56-MB-Python-Prozess hinzu.

## AC-2 — Token-Delta pro Turn (Tool-Defs MIT vs OHNE)

Kein Live-`count_tokens`-Key in der Harness-ENV → **dokumentierte
Offline-Schätzung** (kein tiktoken — falscher Tokenizer):
- 2 Tool-Defs als Anthropic-JSON = **919 Zeichen/Bytes**.
- Geschätztes Token-Delta: **~230–278 Tokens/Turn** (Spanne 3,3–4,0 Zeichen/Token).
- Exakte Zahl: Lauf mit gesetztem `ANTHROPIC_API_KEY` wiederholen (LIVE-Pfad ist
  im Skript gebaut).

**Entscheidender Befund:** Dieser Token-Aufschlag ist **identisch**, ob die
Tool-Defs über MCP oder über das kanonische `tool_use`-Skill-Adapter-Modell
kommen — das Modell sieht in beiden Fällen dieselben name/description/
input_schema-Blöcke (claude.py:_to_anthropic_tool). **Token ist also KEINE
Achse, die MCP vs. Status quo unterscheidet** — er ist eine Eigenschaft von
„wie viele Tools exponiere ich dem Modell", orthogonal zum Transport.

## AC-3 — Ops: HTTP-Dauerdienst vs. stdio

(Details: `mess/ops_vergleich.md`.) stdio: kein Port/systemd/Healthcheck, aber
+559 ms Latenz pro Turn + 57-MB-Spitze. HTTP: ~0 Per-Call-Latenz, aber
permanenter ~56-MB-Block + ein weiterer Dauerdienst pro Buddy mit Port,
systemd-Unit, Restart-nach-Merge-Pflicht, Boot-Race-Risiko und Drop-In-Pflege.
Beide sind echter Mehraufwand gegen den Direkt-Adapter (0 Ports, 0 Spawn).

## AC-4 — Dev-Erfahrung MCP vs. Skill-Adapter (qualitativ)

(Details: `mess/devx_notiz.md`.) FastMCPs `@mcp.tool()`-Dekorator ist pro Tool
minimal angenehmer (Schema aus Signatur), kostet aber: 20+ neue transitive
Deps (starlette/uvicorn/httpx/pydantic …) in einem Repo, das heute mit
stdlib+flask+anthropic auskommt; ein zweiter Transport/Prozess-Lebenszyklus;
und einen **async-Bruch** gegen den rein synchronen Agent-Loop. Netto-DX-Gewinn:
nicht erkennbar. Verzerrungs-Hinweis: uv-Pull gelang, Bewertung beruht auf der
echten mcp-SDK (kein hand-gerollter JSON-RPC-Fallback).

## AC-5 — Provider-Adapter-Umbau (belegt, nur gelesen)

(Details: `mess/provider_umbau_befund.md`.) Die lokale MCP-Form **entlastet**
RAT-3 dort, wo es am meisten fürchtete: `model.py`, `providers/claude.py` und
die **EC-10-Provider-Tests bleiben unverändert** — das Modell sieht weiter
normale `tool_use`-Blöcke. Der reale Umbau-Delta liegt woanders: in der
Tool-Discovery/Dispatch-Schicht von `agent.py`/`tasks.py` (Tools per
`list_tools`-Handshake statt statischer Katalog; Calls an
`mcp.ClientSession.call_tool` statt Direkt-Client) plus einem **sync→async-Bruch**
(mcp-Client ist async-only, agent.py rein synchron — vgl. „HFE synchron blockt
Chat-Turn"). Umbau ist real, nur an anderer Datei als RAT-3 formuliert hatte.

## AC-6 — EC-12 / Datenretention (belegt)

(Details: `mess/ec12_datenfluss.md`.) Datenfluss komplett auf 127.0.0.1/Pi:
eltern-chat → MCP-Client → MCP-Server → EssenClient → Essen-Buddy. Daten
verlassen die Maschine an **derselben** Grenze wie heute (erst bei der
Anthropic-API). **Die lokale Form vermeidet den ZDR-Bruch des gehosteten
Connectors** — keine `mcp-client`-Beta-Blöcke, ZDR-Status identisch zu heute.
Neue Oberfläche: die MCP-Schicht **loggt Tool-Aufrufe** (im Spike sichtbar:
`Processing request of type CallToolRequest`) — ein zusätzlicher lokaler
Retentions-/Redaktions-Datenpunkt, kein ZDR-Bruch.

---

## Hochrechnung × ~6–7 eltern-chat-Buddys

(essen, foto, plan, routine, panel, geraete, familie … ≈ 6–7 Skill-Adapter.)

| Form | RAM-Hochrechnung | Latenz | Ops-Fläche |
|---|---|---|---|
| **Pro-Buddy HTTP-Dauerdienst** | 6–7 × ~56 MB = **~334–390 MB permanent** | ~0/Turn | 6–7 Dauerdienste, Ports, Drop-Ins, Restarts, Boot-Races |
| **Pro-Buddy stdio** | transiente 57-MB-Spitzen | **+0,56 s × berührte Buddys/Turn** | gering (kein Dienst) |
| **Aggregator** (ein MCP-Server vor allen Buddys) | **~56 MB permanent** (1 Prozess) | ~0/Turn | 1 Dienst, aber koppelt alle Buddys + kennt alle Origins |
| **Direkt-Adapter (Status quo)** | **~0 marginal** | ~0 | 0 |

Der Pi trägt laut Memory bereits 10 Cockpit-Sessions + Chromium-Kiosk + alle
Buddy-Services + nginx. ~0,33–0,39 GB permanenter RAM nur für MCP-Wrapper, die
dem Modell **keine** zusätzliche Fähigkeit geben, sind teuer.

---

## Empfehlung: KEINE MCP-Schicht — RAT-3 bleibt geschlossen

Der Spike liefert die Zahlen, die Reopen-Bedingung (b) verlangte — und **(b) ist
nicht erfüllt.** Die lokale Form räumt zwar beide *Befürchtungen* aus
(kein ZDR-Bruch; Provider-Adapter/model.py/claude.py/EC-10 unverändert), zeigt
aber **keinen belegten Nutzen**. Jede Achse ist entweder neutral oder ein
Netto-Kostenpunkt:

- **Token (AC-2): neutral** — identisch zum Status quo, kein Argument für MCP.
- **RAM/Spawn (AC-1): Netto-Kosten** — pro-Buddy +334–390 MB permanent ODER
  +0,56 s/Turn; Aggregator +56 MB; Direkt-Adapter ~0.
- **Ops (AC-3): Netto-Kosten** — Ports/Dienste/Restarts/Boot-Races.
- **DX (AC-4): Netto-Kosten** — Dependency-Block + async-Bruch.
- **EC-12 (AC-6): leicht negativ** — neue lokale Log-Oberfläche.
- **Umbau (AC-5): Netto-Kosten** — agent.py-Dispatch + sync→async.

**Empfehlung an die #1164-Linie:** RAT-3 mit Verweis auf diesen Spike
geschlossen halten. Das kanonische `tool_use`-Skill-Adapter-Modell gewinnt für
das Wrappen **eigener** Buddys eindeutig.

**Falls MCP je erzwungen wird** (echter neuer Use-Case — z. B. ein **fremder**
MCP-Server, den die Familie nutzen will, nicht das Wrappen eigener Buddys):
Rangfolge **Aggregator > Hybrid > Pro-Buddy**. Aggregator schlägt Pro-Buddy um
~280–330 MB RAM; Hybrid (stdio pro Turn für seltene Buddys + Direkt-Adapter für
heiße) schlägt nie einfach „Direkt-Adapter behalten". Diese Rangfolge ist
ausdrücklich nur für den hypothetischen Fall — der Default-Empfehlung
(keine MCP-Schicht) widerspricht sie nicht.
