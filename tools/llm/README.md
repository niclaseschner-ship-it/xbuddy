# LLM-Provider-Lib (`tools/llm/`)

V1-Implementierung der Spec [`specs/platform/llm-providers.md`](../../specs/platform/llm-providers.md)
und Konvention [`conventions/llm-providers.md`](../../conventions/llm-providers.md).
Ratifiziert in [RAT-20](../../decisions/RAT-20-llm-gateway-ist-lib.md), Refs T1082.

Die **eine** Stelle, an der eine XBuddy-Instanz Anthropic-/Azure-OpenAI-/…-
Calls baut. Statt dass jeder Buddy (eltern-chat, hoerspiel, kibuddy) seinen
eigenen Provider-Adapter pflegt, lesen und schreiben alle über diese geteilte
Lib — drei Public-API-Sichten auf einem gemeinsamen Vendor-File-Kern (LLMP-2).

Library im `tools/`-Genre (DCOMP-1, LLMP-1) — analog
[`tools/zugangsdaten/`](../zugangsdaten/), [`tools/configloader.py`](../configloader.py),
[`tools/logsetup.py`](../logsetup.py): kein eigener Prozess, kein Service,
kein HTTP-Endpoint. Eine HTTP-Fassade wird erst ratifiziert, wenn ein
externer (nicht-Python / nicht-In-Prozess) Konsument belegt ist (OPEN-LLMP-D).

## Nutzung

```python
from tools.llm import get_chat, LLMCapabilityError

# Heute (KIBuddy, T1082): Multi-Turn-Chat
chat = get_chat(slot="kibuddy-anthropic-api-key")
text = chat.complete_multiturn(
    system=system_prompt,
    turns=[{"role": "user", "content": "..."}, ...],
    user_message="Was ist Wasser?",
)

# Skelett bis T3/T4:
# - get_singleshot(slot)  → Structured-Singleshot (hoerspiel, T3)
# - get_agent(slot)       → Agent-Tool-Loop (eltern-chat, T4)
```

Eine Komponente importiert **nur** aus dem Paket `tools.llm`, nie aus
internen Pfaden (LLMP-4 Re-Export-Form, analog ZD-5/MOD-5).

## Drei Sichten, ein Vendor-File (LLMP-S1, LLMP-2)

| Sicht                  | Use-Case                                                  | Heutiger Konsument       |
|------------------------|-----------------------------------------------------------|--------------------------|
| `get_chat(slot)`       | Multi-Turn mit History + System-Prompt, ohne Tool-Use     | kibuddy (T1082, live)    |
| `get_singleshot(slot)` | Strukturierte Einzel-Antwort (forced via Tool-Use)        | hoerspiel (T3, Skelett)  |
| `get_agent(slot)`      | Tool-Loop mit Mid-Turn-Continuation                       | eltern-chat (T4, Skelett)|

Eine neue Vendor-Datei aktiviert automatisch alle drei Sichten — kein
Adapter-Code pro Buddy (LLMP-2 Trade-off).

## Capability-Matrix mit hartem Boot-Fail (LLMP-3, LLMP-S3)

Jede Sicht deklariert ihr **Required-Capability-Set** (`public_api.REQUIRED_*`);
jeder Vendor-File deklariert sein **Available-Capability-Set** als
`CAPABILITIES = frozenset({...})` am Modulkopf (LLMP-4). Bei
Slot-Vendor-Mismatch wirft die Lib beim Boot `LLMCapabilityError` und
bricht den Service-Start ab — **kein** Runtime-Silent-Fallback auf
reduziertes Verhalten.

Die sechs ratifizierten Capabilities (V1):

| Capability                       | Bedeutung                                                                 |
|----------------------------------|---------------------------------------------------------------------------|
| `tool_use`                       | Vendor unterstützt Anthropic-style `tool_use`/`tool_result`-Cycle         |
| `multi_turn_assistant_prefill`   | Vendor erlaubt Assistant-Prefill für laufenden Turn                       |
| `structured_output`              | Vendor erzwingt JSON-Schema im Output (nativ oder via forced `tool_use`)  |
| `cache_control`                  | Vendor unterstützt expliziten Cache-Block-Marker                          |
| `multimodal_input`               | Vendor akzeptiert Bild-/Audio-Input neben Text                            |
| `system_message_distinct`        | Vendor trennt System-Prompt von User/Assistant-Turns (eigener Parameter)  |

**Watchdog-Regel (LLMP-4):** jeder File unter `tools/llm/_vendor/` ohne
`CAPABILITIES`-Frozenset am Modulkopf ist ein Bruch — beim Boot sichtbar,
nicht im 47. Turn.

## Telemetrie-Doppelschreibung (LLMP-S4)

Die Lib schreibt **zusätzlich** synchron einen Append-Eintrag nach
`var/llm/provider_calls.jsonl` (Datenpfad-Default
`/home/buddy/xbuddy-data/llm/provider_calls.jsonl`, ENV-overridable über
`XBUDDY_DATA_DIR`). Die Buddy-eigenen SQLite-/Backend-Pfade bleiben **SSoT**
pro Buddy und werden **nicht** angetastet — insbesondere eltern-chats
`conversations.db.provider_calls` (EC-23/E-EC-11).

Schreibfehler werden geloggt (`warning`) und geschluckt — ein Telemetrie-Bruch
darf den Konsumenten-Call nicht abreißen (LLMP-S4 Fehler-Verhalten).

## Slot-Konvention (LLMP-5)

Slot-Namen folgen der `<konsument>-<vendor>-<purpose>`-Form aus ZD-2:

- `kibuddy-anthropic-api-key`
- `hoerspiel-anthropic-api-key`
- `eltern-chat-anthropic-api-key`

Die Lib übergibt den Slot-Namen an `tools.zugangsdaten` und erhält den
API-Key zurück (ZD-5). Welcher Vendor unter welchem Slot lebt, ist
Buddy-Konfiguration (z. B. EC-15 `provider`-Wert); die Lib trifft diese
Entscheidung nicht.

## Datenpfad (LLMP-S5, SVC-5)

| Wert | Default | Override |
|---|---|---|
| JSONL-Telemetrie | `/home/buddy/xbuddy-data/llm/provider_calls.jsonl` | `$XBUDDY_DATA_DIR` |

## Dateien

- `__init__.py` — Public-API; Komponenten importieren nur hierüber.
- `public_api.py` — `get_agent`, `get_singleshot`, `get_chat` mit
  Capability-Boot-Fail (LLMP-S3).
- `_resolver.py` — Slot-Parsing (LLMP-5) und Vendor-Modul-Import.
- `_types.py` — `LLMCapabilityError`, `ProviderError`, `LLMProvider`-
  Protokoll, `ProviderCallEvent`-TypedDict.
- `_vendor/anthropic.py` — Anthropic-Vendor-Kern mit `CAPABILITIES`-
  Frozenset (LLMP-4).
- `pricing.py` — Modell-Preis-Tabelle (V1 hardcodet Anthropic, OPEN-LLMP-A).
- `telemetry.py` — JSONL-Schreiber (LLMP-S4/S5).

## Tests

```bash
uv run pytest tools/llm/tests/ -v
```

Eine Test-Datei je Bauregel (LLMP-S11). Die Suite läuft **ohne Netz** — die
Vendor-Klassen werden mit Fake-Modulen ersetzt, das anthropic-SDK ist Lazy-
Import (analog `kibuddy/providers/claude.py`).
