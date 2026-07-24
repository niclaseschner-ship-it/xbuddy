# LLM-Provider — Konvention     (ID-Präfix: LLMP)

XBuddy hat heute (2026-06-21) drei Konsumenten, die LLM-Provider ansprechen:
`eltern-chat/` (Agent-Tool-Loop), `hoerspiel/` (Structured-Singleshot) und
`kibuddy/` (Multi-Turn-Chat). Jeder pflegt seinen eigenen Provider-Adapter
mit eigenem Vertrag — derselbe Vendor (Anthropic) ist dreimal verdrahtet
(1087 Z Provider-Code total, Drift belegt).

Diese Konvention legt fest, wie die geteilte LLM-Provider-Schicht
`tools/llm/` strukturiert ist — als Lib-Schwester zu `tools/zugangsdaten/`
(E-ZD-3), nicht als Service mit HTTP-Hop. Ratifiziert in
[RAT-20](../decisions/RAT-20-llm-gateway-ist-lib.md), 2026-06-21. Die Spec
mit dem Verhalten der Lib (Telemetrie-Disziplin, Spike-Stufen, Migration)
liegt in [`specs/platform/llm-providers.md`](../specs/platform/llm-providers.md);
diese Datei beschreibt die Bauregel, die Spec beschreibt das Verhalten.

### LLMP-1 — Lib-Form, kein eigener Prozess
Die LLM-Provider-Schicht lebt unter `tools/llm/`. Konsumenten importieren via
`from tools.llm import …` (analog `tools.zugangsdaten`, `tools.configloader`,
`tools.logsetup`). Es gibt **keinen** `xbuddy-llm.service`, **keine**
HTTP-Fassade, **keinen** eigenen Port. Service-Form ist erst zu prüfen,
wenn ein externer (nicht-Python / nicht-In-Prozess) Konsument belegt ist —
bis dahin wäre der Hop Cloud-Reflex ohne Mehrwert
(RAT-20 Sektion „Patch 1" → Form ist Lib; ENTSCHEID-File Sektion
„Patch 1 — RAT-N überschreibt RAT-6-Wortlaut explizit").

### LLMP-2 — Sechs Public-API-Sichten
`tools/llm` stellt sechs Konsumenten-Sichten bereit, jede mit einem
eigenen Vertrag, alle auf demselben `_vendor/<vendor>.py`-Kern (V1 = vier
Text-Sichten; `get_speech`/`get_transcription` sind die 5. + 6., T1410 additiv
via LiteLLM, LLMP-S6/RAT-28):

| Sicht             | Use-Case                                      | Heute belegt durch |
|-------------------|-----------------------------------------------|--------------------|
| `get_agent(slot)` | Tool-Loop mit Mid-Turn-Continuation           | eltern-chat        |
| `get_singleshot(slot)` | Strukturierte Einzel-Antwort (Schema-erzwungen via Tool-Use) | hoerspiel |
| `get_chat(slot)`  | Multi-Turn-Konversation mit History + System-Prompt | kibuddy      |
| `get_completion(slot)` | Freitext-Singleshot (ein Absatz Prosa, kein Schema) | hoerspiel (Synopse, #1131) |
| `get_speech(slot)` | TTS: Text → Audio-Bytes (`.synth(text, *, voice, …)`) | kibuddy (T1410, RAT-28) |
| `get_transcription(slot)` | STT: Audio-Bytes → Transkript (`.transcribe(audio, *, …)`) | kibuddy (T1410, RAT-28) |

Eine neue Vendor-Datei aktiviert automatisch alle sechs Sichten — kein
Adapter-Code pro Buddy. Eine siebte Sicht wird erst hinzugefügt, wenn ein
weiterer Use-Case mit **eigenem** Vertrag belegt ist (CLAUDE.md §6, „Vorschlagen,
wenn Werte sich vermehren"). Verschmelzung zweier Sichten ist Re-Litigation
nach Vertrag-Drift-Schwelle (RAT-20 „Kill-Kriterium")
(ENTSCHEID-File Sektion „Finale Landung — MACH ES" → Was sich ändert /
Trade-off; Verdikt Frage 6).

Die zwei Audio-Sichten sind **eigene Verträge**, keine Untervariante der vier
Text-Sichten: `get_speech` liefert `bytes` (Audio), `get_transcription` nimmt
`bytes` und liefert `str` — beide haben eine Modalitäts-Ein-/Ausgabe, die keine
Text-Sicht teilt. Genau das rechtfertigt sie als 5. + 6. Sicht statt als
Capability-Opt-in innerhalb einer Text-Sicht (Gegenprobe `multimodal_input`:
Bild-Input ist eine Modalität **quer über** den Singleshot-Text-Vertrag und
bleibt deshalb Capability, keine Sicht — Audio hingegen hat einen eigenen
Ein-/Ausgabe-Vertrag). Provider ist Config-Sache (LLMP-5-Slot); LiteLLM ist der
Motor (`litellm.speech()` / `litellm.transcription()`, LLMP-S12/S6).

### LLMP-3 — Capability-Matrix mit hartem Boot-Fail
Jede Sicht deklariert ihr **Required-Capability-Set**; jeder Vendor-File
deklariert sein **Available-Capability-Set**. Bei Slot-Vendor-Mismatch
wirft die Lib beim Boot `LLMCapabilityError` und bricht den Service-Start
ab — **kein** Runtime-Silent-Fallback auf ein Untermenge-Verhalten
(ENTSCHEID-File Sektion „Patch 2 — Capability-Matrix + harter Boot-Fail").

Die neun ratifizierten Capabilities (V1 = sechs; `web_search` ist die 7.,
T1371 additiv; `speech` + `transcription` sind die 8. + 9., T1410 additiv via
LiteLLM, LLMP-S6/RAT-28):

| Capability                       | Bedeutung                                                                 |
|----------------------------------|---------------------------------------------------------------------------|
| `tool_use`                       | Vendor unterstützt Anthropic-style `tool_use`/`tool_result`-Cycle         |
| `multi_turn_assistant_prefill`   | Vendor erlaubt Assistant-Prefill für laufenden Turn                       |
| `structured_output`              | Vendor erzwingt JSON-Schema im Output (nativ oder via forced `tool_use`)  |
| `cache_control`                  | Vendor unterstützt expliziten Cache-Block-Marker                          |
| `multimodal_input`               | Vendor akzeptiert Bild-/Audio-Input neben Text                            |
| `system_message_distinct`        | Vendor trennt System-Prompt von User/Assistant-Turns (eigener Parameter)  |
| `web_search`                     | Vendor bietet ein **server-seitiges** `web_search`-Tool (Suche auf Anbieter-Infra, als `tools`-Array-Eintrag; kein externer Such-Provider, kein neuer Key) |
| `speech`                         | Vendor kann Text-zu-Sprache (`litellm.speech()`; nur der litellm-Vendor deklariert sie, Text-Hand-Vendoren nicht) |
| `transcription`                  | Vendor kann Sprache-zu-Text (`litellm.transcription()`; nur der litellm-Vendor deklariert sie) |

**Required-Sets pro Sicht (V1):**

- `get_agent`: `{tool_use, multi_turn_assistant_prefill,
  system_message_distinct}` — `cache_control` ist **kein** Boot-Fail-
  Minimum mehr (LLMP-S7: Required-Set = Boot-Fail-Minimum, kein
  Nutzungs-Whitelist). Vendoren mit Prompt-Caching (Anthropic) setzen
  Cache-Marker weiterhin; Vendoren ohne Caching (Mistral, kein
  Prompt-Caching — LLMP-S9-Befund eltern-chat dual-provider
  2026-06-24) booten ohne Fail.
- `get_singleshot`: `{structured_output, system_message_distinct}` (heute
  via `tool_use`-Erzwingung; Vendor ohne `structured_output` darf
  `tool_use` als Substitut nicht auto-fallback — das ist Vendor-File-
  Vertrag).
- `get_chat`: `{multi_turn_assistant_prefill, cache_control,
  system_message_distinct}`
- `get_completion`: `{system_message_distinct}` — bewusst **kein**
  `structured_output`/`cache_control`, damit die Freitext-Sicht dual-provider-
  Slots (hoerspiel Claude+Mistral) ohne Boot-Fail trägt (#1131; `get_chat` wäre
  auf dem Mistral-Slot boot-fatal).
- `get_speech`: `{speech}` (T1410, LLMP-S6) — genau die eine Audio-Capability.
  Ein Text-Hand-Vendor (anthropic/mistral) unter einem TTS-Slot ist boot-fatal
  (LLMP-S3), was korrekt ist: er kann kein Audio.
- `get_transcription`: `{transcription}` (T1410, LLMP-S6) — Spiegel `get_speech`.

**`web_search` ist per-Rufer-Opt-in in der `get_agent`-Sicht — keine eigene
Sicht und kein Required-Set-Mitglied (T1371, ratifizierte Analyse 2026-07-05/06).**
Nur Anthropic deklariert sie (Tool-Version `web_search_20260209`, Opus 4.8/4.7/4.6
+ Sonnet 4.6); Mistral **nicht**. Läge `web_search` im Boot-Fail-Minimum von
`get_agent`, würde jeder Mistral-Agent-Slot (eltern-chat dual-provider) beim Boot
fatal — deshalb bleibt sie Nutzungs-Opt-in (Spiegel `multimodal_input`). Der
Rufer aktiviert das Server-Tool NUR, wenn `"web_search" in agent.capabilities`
(die `get_agent`-Fassade legt die Vendor-`CAPABILITIES` offen); ein Slot-Vendor
ohne `web_search` degradiert sauber (kein Silent-Send eines unbekannten Tools).
Erster Konsument: hoerspiel-Recherche-Vorschritt (HSP-57, emil-erwachsen).

**`multimodal_input` ist per-Rufer-Opt-in — keine Sicht und kein Required-Set-
Mitglied (ENTSCHEID-1262 → „multimodal_input = Capability, keine Sicht").**
`get_singleshot` nimmt Bilder über den optionalen `images`-Parameter seiner
`complete_structured`-Methode (LLMP-S1); die Sicht bleibt dieselbe. Die Lib prüft
`multimodal_input` **nur, wenn ein Rufer `images` übergibt** — dann gegen das
Available-Set des Slot-Vendors, mit `LLMCapabilityError` bei Fehlen. Läge
`multimodal_input` im **Boot-Fail-Minimum** der Sicht (LLMP-S3), würde jeder
Text-only-Singleshot-Slot ohne Bild-Fähigkeit beim Boot fatal — deshalb bleibt es
Nutzungs-Zeit-Check. Es kommt **keine** fünfte Sicht dazu: Bild-Input ist eine
Modalitäts-Capability quer über den Singleshot-Vertrag, kein eigener Vertrag (Gate:
neue Sicht nur bei eigenem Vertrag — das unterscheidet `multimodal_input` von
`speech`/`transcription`, die genau **wegen** ihres eigenen Audio-Ein-/Ausgabe-
Vertrags als 5. + 6. Sicht aufgenommen wurden, LLMP-2).

Erweiterung der Capability-Liste ist Spec-Änderung (`specs/platform/llm-providers.md`),
nicht Convention-Drift.

### LLMP-4 — Vendor-File-Skelett
Jeder `_vendor/<vendor>.py` deklariert am Modulkopf:

```python
CAPABILITIES = frozenset({
    "tool_use",
    "multi_turn_assistant_prefill",
    "cache_control",
    "system_message_distinct",
    # optional je nach Vendor:
    # "structured_output",
    # "multimodal_input",
    # "web_search",       # nur Anbieter mit server-seitigem Such-Tool (T1371)
    # "speech",           # nur Anbieter mit litellm.speech()-Route (T1410)
    # "transcription",    # nur Anbieter mit litellm.transcription()-Route (T1410)
})
```

Das ist die **maschinell prüfbare** Wurzel von LLMP-3 — Watchdog-Regel
(analog `module-boundaries.md` MOD-1..6): jeder File unter `tools/llm/_vendor/`
ohne `CAPABILITIES`-Frozenset am Modulkopf ist ein Bruch. Die Lib lädt
die Konstante beim Boot und vergleicht gegen die Sicht-Required-Sets;
fehlt sie, ist `LLMCapabilityError` der erste Fehler vor allem anderen
(ENTSCHEID-File Sektion „Patch 2 — Capability-Matrix + harter Boot-Fail").

Re-Export-Form analog `tools.zugangsdaten` (MOD-5): externer Zugriff
**nur** über `from tools.llm import get_agent, get_singleshot, get_chat, get_completion`,
**nie** direkt aus `tools.llm._vendor.<vendor>`. Der Unterstrich vor
`_vendor` macht die Privat-Natur sichtbar; ein analoger MOD-Contract
(z. B. „LLM-Vendor-Module nur über Public-API") darf nach der dritten
Vendor-Datei mechanisch nachgezogen werden — heute ist n=1 (Anthropic),
keine antizipative Generalisierung.

**`_vendor/litellm.py` ist der sanktionierte Motor- und Anbieter-Weg (RAT-26).**
Er muss dieselbe LLMP-4-Bauform erfüllen wie jede andere Vendor-Datei:
`CAPABILITIES = frozenset({…})` am Modulkopf, `<Vendor>Vendor`-Klasse,
kein direkter Konsumenten-Code außerhalb der Public-API. Hand-Vendor-Files
(`_vendor/anthropic.py`, `_vendor/mistral.py`) laufen bis zum Slot-3-Cleanup
(LLMP-S12) parallel weiter — sie sind weder deprecated noch zu entfernen,
solange nicht alle Slots auf LiteLLM grün sind. Neue Anbieter oder
Provider-Experimente gehen über `_vendor/litellm.py`, **nicht** als neues
Hand-Vendor-File (Ausnahme: ein Anbieter ist explizit nicht über LiteLLM
verfügbar — dann eigene Werft vor Hand-Vendor-Anlage).

### LLMP-5 — Slot-Konvention-Brücke zu ZD
Slot-Namen folgen der `<konsument>-<vendor>-<purpose>`-Namens-Konvention aus
ZD-2 (`specs/platform/zugangsdaten.md:48-53`). Die Lib selbst kennt keine
Vendor-/Konsumenten-Aufteilung — sie übergibt den Slot-Namen an
`tools.zugangsdaten` und erhält den Schlüssel zurück. Welcher Vendor unter
welchem Slot lebt, ist Buddy-Konfiguration (z. B. EC-15 `provider`-Wert);
die Lib trifft diese Entscheidung nicht.

Die Lib zerlegt den Slot-Namen am `-` und sucht das Vendor-Segment in der
Liste der `_vendor/<vendor>.py`-Module: alles davor wird `caller` (für die
JSONL-Telemetrie, LLMP-S4), alles danach `purpose` (für die ZD-Slot-
Adresse). Damit dürfen Konsumenten-Namen Bindestriche enthalten
(`eltern-chat`) — der Parser identifiziert den Vendor per Modul-Lookup,
nicht per Positions-Annahme. Slots ohne bekanntes Vendor-Segment werfen
beim Boot `LLMCapabilityError` (LLMP-S3) — kein stiller `ModuleNotFoundError`.

Konkretes Beispiel: `get_agent("eltern-chat-anthropic-api-key")` löst zu
caller `eltern-chat`, vendor `anthropic`, purpose `api-key` auf, liest den
Slot via ZD-5, lädt `_vendor/anthropic.py`, prüft `CAPABILITIES` gegen das
`get_agent`-Required-Set (LLMP-3) und liefert die Agent-Sicht — oder
bricht mit `LLMCapabilityError` ab, falls der Vendor `tool_use` nicht
unterstützt

Zweites konkretes Beispiel (Multi-Slot pro Vendor, #1262): dieselbe Instanz kann **zwei**
Anthropic-Slots halten — `eltern-chat-anthropic-api-key` (Chat/Agent) und
`eltern-chat-anthropic-foto-analyse-api-key` (Foto-Analyse/TAB, Structured-Singleshot mit
Bild). Der Parser liefert für den zweiten: caller `eltern-chat`, vendor `anthropic`,
purpose `foto-analyse-api-key` (Suffix `api-key` = Schlüsseltyp nach ZD-2; `foto-analyse`
= Sub-Purpose-Qualifier). Die Foto-Route ist damit ein **eigener Slot** — Anbieter-Wechsel
durch Tausch des Vendor-Segments, ohne Code (ENTSCHEID-1262 → „Anbieter-Wechselbarkeit
via ZD-Slot").
(ENTSCHEID-File Sektion „Worum es geht" + Bezug ZD-2).
