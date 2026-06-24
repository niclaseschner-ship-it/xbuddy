# LLM-Provider-Schicht — Spec     (ID-Präfix: LLMP)

> Status: V1 · Ratifiziert via [RAT-20](../../decisions/RAT-20-llm-gateway-ist-lib.md)
> · Refs: RAT-6:71 (überschrieben), OPEN-KIBUDDY-F (geschlossen)

Die LLM-Provider-Schicht ist die **eine** Stelle, an der eine XBuddy-Instanz
ihre Anthropic/Azure-OpenAI/OpenAI/Mistral-Aufrufe baut. Statt dass jeder
Buddy (eltern-chat, hoerspiel, kibuddy) seinen eigenen Provider-Adapter
pflegt, lesen und schreiben alle über diese geteilte Lib. Sie hält drei
Public-API-Sichten (Agent, Singleshot, Chat) auf einem gemeinsamen
Vendor-File-Kern.

**Library-Status (DCOMP-1):** Die LLM-Provider-Schicht ist eine **Library** —
kein eigener Prozess, kein Service, kein HTTP-Endpoint. Code lebt unter
`tools/llm/`, Konsumenten importieren via `from tools.llm import …` (analog
`tools.zugangsdaten`, `tools.configloader`, `tools.logsetup`). Die Lib hat
keinen eigenen Port und keinen eigenen systemd-Service
(`conventions/llm-providers.md` LLMP-1; RAT-20 Sektion „Patch 1").

**V1-Scope:** Drei Public-API-Sichten auf einem `_vendor/<vendor>.py`-Kern
(LLMP-2) · Capability-Matrix mit hartem Boot-Fail (LLMP-3/4) · synchrone
Telemetrie-Projektion nach `var/llm/provider_calls.jsonl` zusätzlich zur
bestehenden SQLite-Senke pro Buddy · Slot-Lookup über `tools.zugangsdaten`
(LLMP-5). Vendor V1: Anthropic.

**Out-of-Scope V1** (eigene Folge-Werften / Folge-RATs, sobald gebraucht):
HTTP-Fassade als Plattform-Dienst (erst bei externem Konsument außerhalb
Python) · TTS-/STT-Schicht (eigene Frage mit eigenen Anchors, kein
`tools/tts/` Vorweg) · EC-23-Umstieg auf JSONL-only (separate Folge-RAT) ·
Fusion zweier Sichten (Re-Litigation nach Vertrag-Drift-Schwelle).

## 1. Public-API

### LLMP-S1 — Drei Sichten, ein Vendor-File
Die Lib stellt drei Funktionen bereit: `get_agent(slot)`, `get_singleshot(slot)`
und `get_chat(slot)`. Jede gibt ein Sicht-Objekt zurück, das auf demselben
`_vendor/<vendor>.py`-Kern aufsetzt. Ein neuer Vendor (eine Datei) aktiviert
alle drei Sichten — kein Adapter-Code pro Buddy
(RAT-20 Sektion „Finale Landung — MACH ES" → Was sich ändert).

- **`get_agent(slot)` — Agent-Tool-Loop.** Für Konversationen mit Tool-Use
  und Mid-Turn-Continuation. Heutiger Use-Case: eltern-chat
  (`providers/claude.py`-Bestand). Required Capabilities: `tool_use`,
  `multi_turn_assistant_prefill`, `cache_control`, `system_message_distinct`
  (LLMP-3).
- **`get_singleshot(slot)` — Structured Singleshot.** Eine Anfrage, ein
  Schema-konformer Antwort-Block. Heutiger Use-Case: hoerspiel
  (Folgen-Beschreibung via JSON-Schema, heute via forced `tool_use`).
  Required Capabilities: `structured_output`, `system_message_distinct`
  (LLMP-3).
- **`get_chat(slot)` — Multi-Turn-Chat.** Konversation mit History und
  System-Prompt, ohne Tool-Use im Kern-Pfad. Heutiger Use-Case: kibuddy
  (Sokratisch-Dialog mit Kind, Multi-Turn-Kontext). Required Capabilities:
  `multi_turn_assistant_prefill`, `cache_control`, `system_message_distinct`
  (LLMP-3).

Eine vierte Sicht wird erst hinzugefügt, wenn ein vierter Use-Case mit
eigenem Vertrag belegt ist (CLAUDE.md §6, „Vorschlagen, wenn Werte sich
vermehren").

### LLMP-S2 — Slot-Lookup über ZD
Der Slot-Parameter folgt der `<konsument>-<vendor>-<purpose>`-Konvention
aus ZD-2 (`zugangsdaten.md:48-53`). Die Lib übergibt den Slot-Namen an
`tools.zugangsdaten` und erhält den API-Key zurück (ZD-5). Die Lib selbst
kennt keine Vendor-/Konsumenten-Aufteilung — welcher Vendor unter welchem
Slot lebt, ist Buddy-Konfiguration (z. B. EC-15 `provider`-Wert)
(`conventions/llm-providers.md` LLMP-5; ENTSCHEID-File Sektion „Worum es
geht").

### LLMP-S3 — Capability-Matrix, harter Boot-Fail
Jeder `_vendor/<vendor>.py` deklariert `CAPABILITIES = frozenset({...})`
am Modulkopf (LLMP-4). Beim Boot vergleicht die Lib die Vendor-Capabilities
gegen das Required-Set der angefragten Sicht (LLMP-3). Bei Mismatch wirft
sie `LLMCapabilityError` — der Service-Start bricht ab, **kein** Silent-
Fallback auf reduziertes Verhalten zur Laufzeit
(RAT-20 Sektion „Patch 2 — Capability-Matrix + harter Boot-Fail";
ENTSCHEID-File Sektion „Patch 2").

Begründung: Ein stiller Fallback (z. B. Vendor ohne `cache_control` läuft
ohne Cache) sieht aus wie ein Performance-Bug, ist aber ein Konfigurations-
Fehler. Der harte Fail beim Boot macht das Mismatch zur sichtbaren
Konfigurations-Entscheidung.

## 2. Telemetrie-Disziplin

### LLMP-S4 — Doppelschreibung (SSoT bleibt SQLite, JSONL ist Projektion)
Die Lib schreibt **zusätzlich** synchron einen Append-Eintrag nach
`var/llm/provider_calls.jsonl`. Die bisherigen Buddy-eigenen SQLite-/Backend-
Pfade bleiben **SSoT pro Buddy** und werden **nicht** angetastet —
insbesondere eltern-chats `conversations.db.provider_calls` (EC-23 +
E-EC-11). Die Lib schreibt JSONL synchron im selben Call; bei
Schreibfehler nur Warning, kein Crash
(RAT-20 Sektion „Patch 3 — Telemetrie-Doppelschreibung";
ENTSCHEID-File Sektion „Patch 3 — Telemetrie-Doppelschreibung" →
Tier 1 + Tier 2 + Fehler-Verhalten).

**Event-Schema (V1):**

```json
{
  "ts": "2026-06-21T19:30:00Z",
  "caller": "eltern-chat",
  "correlation_id": "turn-xyz123",
  "slot": "eltern-chat-anthropic-api-key",
  "model_id": "claude-opus-4-7",
  "input_tokens": 1234,
  "output_tokens": 567,
  "cache_read_tokens": 8901,
  "cache_creation_tokens": 234,
  "wall_ms": 1850,
  "est_cost_eur": 0.0432
}
```

**Felder im Detail:**

- `correlation_id` ist **Caller-Sache** — eltern-chat: `turn_id`; hoerspiel:
  `episode_id`; kibuddy: `chat_id`. Die Lib akzeptiert beliebige Strings
  und ordnet nicht selbst zu.
- `caller` ist der Buddy-Kurzname (`eltern-chat`, `hoerspiel`, `kibuddy`).
- `slot` ist der ZD-Name (LLMP-5).
- `model_id` ist der vom Vendor zurückgegebene Modell-Identifier.
- `est_cost_eur` wird in der Lib auf Basis einer Preis-Tabelle berechnet
  (Preis-Tabelle ist Vendor-File-Sache, V1 hart in `_vendor/anthropic.py`;
  Multi-Vendor-Preis-Tabelle ist Folge-Werft).

**EC-23-Umstieg auf JSONL-only ist separate Folge-RAT**, nicht Teil dieser
Spec. Bis dahin schreiben Buddies, die heute SQLite-Telemetrie führen,
diese weiter (Doppelschreibung)
(RAT-20 Sektion „Re-Litigation").

### LLMP-S5 — Datenpfad SVC-5-konform
`var/llm/provider_calls.jsonl` liegt unter dem SVC-5-Datenpfad
(`__XBUDDY_DATA__/llm/provider_calls.jsonl` in der Repo-Form;
`services.md` SVC-5). Rotation: siehe `OPEN-LLMP-E`.

## 3. TTS/STT — Abgrenzung

### LLMP-S6 — TTS/STT sind nicht Teil dieser Spec
Diese Spec ratifiziert ausschließlich die LLM-Provider-Schicht. TTS- und
STT-Schichten sind **nicht Teil** und werden hier auch nicht antizipiert
(kein `tools/tts/`, keine „Schwester-Lib im selben Stil"-Behauptung). Die
TTS-Reibung in `kibuddy.md:487` ist real, aber eigene Frage mit eigenen
Anchors (Asset-Lifecycle bei hoerspiel, speed-Cache bei kibuddy) — eigene
Folge-Werft mit eigener Berater-Runde
(RAT-20 Sektion „Patch 4 — TTS aus Scope";
ENTSCHEID-File Sektion „Patch 4 — TTS aus Scope").

## 4. Migrationspfad

### LLMP-S7 — Spike-Stufe-1 vor zweitem Buddy
KIBuddy ist die Spike-Umgebung (LLMP-S8) und gleichzeitig der erste
Migrations-Buddy. **Vor dem zweiten Migrations-Buddy** (hoerspiel) laufen
**drei Fixtures** gegen denselben `_vendor/anthropic.py` ohne Familien-Verkehr
— sie belegen die Lego-Wiederholbarkeit der Vendor-Kern-These über die
KIBuddy-Erfahrung hinaus, bevor ein kritischerer Buddy migriert wird:

1. **Agent-Tool-Loop** (eltern-chat-ähnlich): `get_agent("test-slot").run(...)`
   mit Tool-Definition + Tool-Call + Mid-Turn-Continuation.
2. **Structured-Singleshot** (hoerspiel-ähnlich):
   `get_singleshot("test-slot").complete_structured(system, prompt, schema)`
   forced via Tool-Use.
3. **Multi-Turn-Chat** (kibuddy-ähnlich): `get_chat("test-slot").complete_multiturn(system, turns, user_message)`
   mit System-Prompt + 3-Turn-History.

Erfolg = alle drei grün **mit derselben** Vendor-Datei. Der Vertrag wird
**nicht** ratifiziert (RAT-20 zurückziehen), wenn einer dieser drei
**Lego-Brüche** eintritt (ENTSCHEID-File `20260624-1330-RATIFIZIERT-llm-s7-loc-kill.md`
Paket-Sektion „Drei Lego-Bruch-Tests" → Kill-Kriterium):

1. **Capability-Flucht:** Eine Sicht zwingt den Kern, eine Capability außerhalb
   der **sechs ratifizierten** LLMP-3-Capabilities (`CAPABILITIES`-frozenset) zu
   nutzen — die Ein-File-These versteckt dann echte Vendor-Divergenz. Das
   Required-Set einer Sicht ist nur das **Boot-Fail-Minimum** (LLMP-S3), **kein**
   Nutzungs-Whitelist: dass `get_chat`/`get_singleshot`/`get_agent` zusätzlich
   eine der sechs ratifizierten Capabilities nutzen, die nicht in *ihrem*
   Required-Set steht (z. B. `cache_control` in Singleshot), ist erlaubt.
   Erweitern der sechs ist selbst eine Spec-Änderung (LLMP-3) und damit der
   eigentliche Bruch-Pfad (ENTSCHEID Paket-Sektion „Capability-Bruch scharf"
   → Capability-Flucht).
2. **Adapter-Wildwuchs:** Eine Sicht erfordert Vendor-Verzweigung pro
   Buddy/Konsument im Kern (`if caller == …`) statt sicht-uniformer
   Behandlung — der „kein Adapter-Code pro Buddy"-Anspruch (LLMP-S1) ist
   gebrochen.
3. **Copy-Paste-Divergenz:** Zwei Sicht-Methoden duplizieren ≥8 nicht-triviale
   zusammenhängende Zeilen mit gleicher Kontrollstruktur, ohne dass ein
   gemeinsamer Helfer existiert — Indiz für faule Abstraktion. Der Review muss
   beide `Datei:Zeile`-Ranges nennen; ohne konkrete Ranges kein Kill (gemessen
   am Review, nicht an roher Gesamt-Zeilenzahl).

**LOC-Frühwarnung (nicht-bindend, aber pflichtig):** Wächst der Kern beim
Aktivieren einer Sicht um >30% LOC, ist das **kein** automatischer
Vertrags-Stopp — aber der PR/Handoff **muss** eine Drei-Zeilen-Abhakung mit
`Datei:Zeile` tragen (Capability-Flucht nein/ja · Adapter-Wildwuchs nein/ja ·
Copy-Paste-Divergenz nein/ja). So stoppt das Signal nicht automatisch, kann
aber nicht ignoriert verschwinden (ENTSCHEID Paket-Sektion „LOC-Frühwarn-Artefakt"
→ nicht-bindend aber pflichtig). Reines Wachstum durch inhärent große,
helfer-faktorierte Interaktionsmuster (z. B. Tool-Use-Loop) ist erlaubt.

### LLMP-S8 — Migrations-Reihenfolge KIBuddy → hoerspiel → eltern-chat
1. **KIBuddy** (zuerst, weil wörtlicher RAT-6-Trigger „ab KIBuddy"; Blast-
   Radius am kleinsten — KIBuddy-Ausfall = nur Kind-Chat down, kein
   Familien-Workflow gefährdet; Multi-Turn deckt Kontext-Akkumulations-
   Detailfunde früh auf).
2. **hoerspiel** (strukturiert, bekommt Telemetrie+Pricing als Bonus;
   klein/isoliert genug, um Capability-Matrix-Review vor dem Voll-Last-
   Buddy zu wiederholen).
3. **eltern-chat** (zuletzt, weil EC-23-Doppel-Schreib-Disziplin am
   ausgereiftesten erprobt sein muss; Voll-Last-Beweis der JSONL-
   Projektion in Familie-1).

Pro Migration **additiv-rückrollbar**: alter `<buddy>/providers/`-Ordner
bleibt zunächst, neuer Pfad über `tools.llm`, sobald grün: alten Ordner
löschen (Zwei-Schritt-Migration analog ZD-Migration ONB-5→ZD,
`zugangsdaten.md:74-87`)
(ENTSCHEID-File Sektion „Migration nach Spike-Erfolg"; Verdikt Frage 6 —
Nic 2026-06-21: „KIBuddy zuerst").

**Re-Order 2026-06-24 (Nic):** Nach KIBuddy (T1) wird **eltern-chat (T4) vor
hoerspiel (T3) gezogen** — hoerspiel hat gerade andere Probleme und wird
nachgezogen. Damit ist **eltern-chat der n=2-Beleg** der Vendor-Kern-These
(statt hoerspiel). Bewusst getauschter Trade-off: der Voll-Last-Buddy kommt
als n=2 **ohne** die kleinere hoerspiel-Generalprobe; akzeptiert, weil
hoerspiel blockiert ist und die Migration additiv-rückrollbar bleibt (alter
`providers/`-Ordner bleibt bis beide Anbieter grün). Die ursprüngliche
Reihenfolge oben bleibt als Audit-Spur; gilt wieder, sobald hoerspiel
entblockt ist.

### LLMP-S9 — Re-Evaluierung vor jedem Buddy
Vor jedem Migrations-Buddy: Capability-Matrix-Review gegen den realen
Bestand des Buddys (für eltern-chat: das Agent-Loop-Required-Set **und** der
Mistral-Anbieter, da eltern-chat dual-provider fährt). Der **Spike-Stufe-2-Beleg**
(7 Tage Familie-1, JSONL-vs-SQLite-`est_cost_eur`-Diff < 1%/Tag — sonst
Schreibpfad-Fix vor weiterer Migration) ist **die Live-Probe des
eltern-chat-Migrations-Tickets selbst** und läuft folgerichtig **nach** dessen
Merge (eltern-chat ist der erste Voll-Last-Konsument; Stufe-2 ohne live
migrierten eltern-chat ist nicht erhebbar). Re-Order-Konsequenz 2026-06-24:
da eltern-chat als n=2 vorgezogen ist, fällt Stufe-2 mit der eltern-chat-
Migration zusammen, nicht mit einem davorliegenden dritten Buddy
(ENTSCHEID-File Sektion „Spike-Experiment (2 Stufen)" → Stufe 2 +
Re-Evaluierungs-Klausel; Re-Order Nic 2026-06-24).

## 5. Tests

### LLMP-S11 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), ohne Netz. Mindest-Abdeckung:

- **LLMP-S1** — die drei Sichten existieren und liefern sicht-spezifische
  Objekte mit dokumentierten Methoden.
- **LLMP-S3** — Capability-Mismatch beim Boot wirft `LLMCapabilityError`
  (Fake-Vendor mit reduzierter `CAPABILITIES`-Frozenset; jede Sicht
  separat getestet).
- **LLMP-S4** — JSONL-Schreibung enthält alle Pflichtfelder; Schreibfehler
  führt zu Warning, nicht zu Crash (Fake-FS mit ReadOnly).

Watchdog-Regel (mechanisch, analog `module-boundaries.md`): jeder File
unter `tools/llm/_vendor/` ohne `CAPABILITIES`-Frozenset am Modulkopf
ist ein Bruch (LLMP-4).

---

## Offene Punkte

- **OPEN-LLMP-A — Multi-Vendor-Preis-Tabelle.** V1 hardcodet die Anthropic-
  Preise in `_vendor/anthropic.py`. Sobald ein zweiter Vendor live ist
  (Azure-OpenAI als wahrscheinlichster Kandidat aus dem ZD-Bestand —
  vier eltern-chat-Vendor-Slots gepflegt), wird die Preis-Tabelle aus dem
  Vendor-File in eine geteilte Schicht gezogen. Trigger: zweiter Vendor
  live oder erster Vendor-Preis-Update mit Code-Change-Schmerz.
- **OPEN-LLMP-B — EC-23-Umstieg auf JSONL-only.** Wenn JSONL nach
  >3 Monaten Familie-1 stabil ist UND die Analyse-Pipeline auf JSONL
  umgestellt ist UND kein Backfüll-Bedarf aus SQLite mehr besteht →
  separate Folge-RAT öffnen, die EC-23/E-EC-11 umstellt. Bis dahin
  Doppelschreibung (LLMP-S4).
- **OPEN-LLMP-C — Fusion zweier Sichten.** Wenn nach 6 Monaten Live-Betrieb
  zwei Sichten >70% Code teilen → Re-Litigation: fusionieren? Capability-
  Matrix-Verstecken-Frage neu öffnen
  (RAT-20 Sektion „Kill-Kriterium" → Vertrag-Drift).
- **OPEN-LLMP-D — HTTP-Fassade als Plattform-Dienst.** Erst, wenn ein
  externer (nicht-Python / nicht-In-Prozess) Konsument belegt ist
  (Browser-Extension, andere-Sprache-Service, externes Familien-Mitglied
  über LAN-Boundary). Re-Trigger: konkreter dritter LLM-Konsument
  außerhalb Python.
- **OPEN-LLMP-E — JSONL-Rotation.** V1 schreibt eine einzige
  `provider_calls.jsonl`-Datei ohne Rotation (Paket nennt keine Rotation
  als ratifiziert). Trigger für Re-Litigation: Datei wächst über praktisch
  handhabbare Größe (`jq`-Auswertung zu langsam, Disk-Druck auf Pi).
- **OPEN-LLMP-F — Konfigurations-Schalter (`LLM_TELEMETRY_*`).** Der
  Bedarf an Test-Harness-Schaltern (Datei-Pfad-Override, Telemetrie-aus
  für Fixtures ohne Datei-Erzeugung) entstand beim Berater-Entwurf, ist
  aber **nicht** Teil des ratifizierten Pakets. Form der Schalter (ENV,
  CLI, beides) entscheidet die KIBuddy-Spike-Werft pragmatisch; falls
  daraus eine generelle Konvention wird, eigene Werft.

---

## Kill-Kriterien (E-LLMP-Erweiterung)

### E-LLMP-1 — Capability-Drift
*Datum:* 2026-06-21

Wenn der harte Boot-Fail (LLMP-S3) in der Praxis mehr Reibung verursacht
als er Fehler abfängt — Belegfall-Schwelle: ≥3 Boot-Fail-Vorfälle pro
Quartal aus Capability-Drift (Vendor-File-Update bricht Required-Set
einer Sicht), nicht aus echtem Mismatch — wird Soft-Warn als Fallback
re-litigiert. Bis dahin: hart bleibt hart
(RAT-20 Sektion „Re-Litigation").

### E-LLMP-2 — JSONL-Doppelschreib-Bruch
*Datum:* 2026-06-21

Wenn Spike-Stufe-2 zeigt, dass JSONL-Lock-Contention oder synchrone
Schreib-Latenz die Telegram-Antwort-Latenz von eltern-chat bricht (>500 ms
Median-Anstieg über 7 Tage), wird Patch 3 (Doppelschreibung) zurückgezogen
und RAT-20 als NOCH-NICHT neu verhandelt
(ENTSCHEID-File Sektion „Kill-Kriterium" → Telemetrie-Doppelschreib).

### E-LLMP-3 — Vertrag-Drift
*Datum:* 2026-06-21

Wenn nach 6 Monaten zwei Sichten >70% gemeinsamen Code haben, ist die
Drei-Sichten-Trennung Über-Differenzierung — dann fusionieren und die
Capability-Matrix-Verstecken-Frage (Berater hatte gewarnt, dass eine
einzige Sicht Capabilities verstecken könnte) neu öffnen
(RAT-20 Sektion „Kill-Kriterium" → Vertrag-Drift).

### E-LLMP-4 — Proxy-Metrik korrigiert
*Datum:* 2026-06-24

Die ursprüngliche LLMP-S7-Kill-Schwelle „>30% LOC = Vertrag nicht
ratifizieren" war eine Vor-Bau-Daumenregel und löste beim gebauten
Spike-Stufe-1-Artefakt (#1083, Commit `12e68f4`: 223→356 Z, +59,6%)
falsch-positiv aus — drei Sichten liefen grün gegen denselben Vendor-File,
ohne Capability-Flucht. Das LOC-Bein wurde durch drei direkte Lego-Bruch-Tests
ersetzt (Capability-Flucht / Adapter-Wildwuchs / Copy-Paste-Divergenz); LOC
blieb als nicht-bindendes, aber pflichtiges Frühwarn-Artefakt erhalten (siehe
LLMP-S7 oben). Lehre: ein Proxy darf einen Vertrag nicht killen, wenn das
direkte Maß widerspricht — Proxy nachschärfen, wenn die Realität die Schätzung
schlägt (ENTSCHEID-File `20260624-1330-RATIFIZIERT-llm-s7-loc-kill.md`).
