# MCP-Spike #1181 — Einkauf-Buddy als lokaler MCP-Server (Mess-Vehikel)

Mess-Spike zur bedingten RAT-3-Wiederaufnahme
(`decisions/RAT-3-ki-zu-api-keine-mcp-schicht.md`): füllt die Reopen-Bedingung
(b) — belegter Use-Case-Nutzen — mit echten Zahlen. **Kein Produktiv-Rollout,
kein gehosteter Connector, kein ZD-Store-als-Tool.** Vehikel: der Einkauf-Teil
des Essen-Buddys, gewrappt in zwei MCP-Tools.

Ergebnis-Zusammenfassung + Empfehlung: **BERICHT.md**.

## Aufbau

```
server/einkauf_mcp_core.py   2 Tools (lese_einkauf GET, hinzufuegen_einkauf POST), wrappt EssenClient
server/run_stdio.py          stdio-Transport-Start
server/run_http.py           HTTP/SSE-Dauerdienst (streamable-http) auf 127.0.0.1:5191
baseline/direct_adapter_call.py  RAT-3-Status quo: Direkt-Aufruf, 0 Extra-Prozess
mess/mess_ram_spawn.py       AC-1: RAM (VmRSS/VmHWM aus /proc), Spawn-Zeit, Baseline-Delta
mess/mess_token_delta.py     AC-2: Token-Delta MIT vs OHNE Tool-Defs (count_tokens ODER Offline-Schätzung)
mess/ops_vergleich.md        AC-3: Ops HTTP-Dauerdienst vs stdio
mess/devx_notiz.md           AC-4: Dev-Erfahrung MCP vs Skill-Adapter
mess/provider_umbau_befund.md AC-5: Provider-Adapter-Umbau belegt
mess/ec12_datenfluss.md      AC-6: EC-12/Datenretention + RAT-3-Konformität
run_scratch_essen.sh         isolierte Scratch-essen (Port 5152, ESSEN_*_FILE→scratch-data/) — NIE 5052
scratch-data/                Scratch-Daten (gitignored, nur .gitkeep getrackt)
```

## venv (Spike-lokal, NICHT in Repo-Deps)

```bash
cd spikes/1181-mcp-einkauf
uv venv .venv && uv pip install --python .venv/bin/python mcp
```

mcp-SDK liegt bewusst nur im Spike-venv — RAT-3-Scope erlaubt keinen
Produktiv-Dependency-Eintrag.

## Messung fahren

```bash
# 1) Isolierte Scratch-essen starten (eigenes Terminal). NIE Port 5052.
./run_scratch_essen.sh

# 2) RAM & Spawn (AC-1)
.venv/bin/python mess/mess_ram_spawn.py

# 3) Token-Delta (AC-2)
#    Ohne ANTHROPIC_API_KEY -> dokumentierte Offline-Schätzung.
#    Mit Key (echte count_tokens): zusätzlich `uv pip install --python .venv/bin/python anthropic`
.venv/bin/python mess/mess_token_delta.py
```

## Daten-Schutz

Der Schreib-Tool-Pfad läuft ausschließlich gegen die Scratch-essen-Instanz
(`ESSEN_ORIGIN_URL`, Default `http://127.0.0.1:5152`). Die Produktiv-Instanz
(Port 5052) wird nie berührt.
