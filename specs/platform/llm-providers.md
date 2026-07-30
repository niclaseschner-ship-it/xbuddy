# LLM-Provider-Schicht — Spec     (ID-Präfix: LLMP)

> Status: V1 · Ratifiziert via [RAT-20](../../decisions/RAT-20-llm-gateway-ist-lib.md)
> · Refs: RAT-6:71 (überschrieben), OPEN-KIBUDDY-F (geschlossen)

Die LLM-Provider-Schicht ist die **eine** Stelle, an der eine XBuddy-Instanz
ihre Anthropic/Azure-OpenAI/OpenAI/Mistral-Aufrufe baut. Statt dass jeder
Buddy (eltern-chat, hoerspiel, kibuddy) seinen eigenen Provider-Adapter
pflegt, lesen und schreiben alle über diese geteilte Lib. Sie hält sechs
Public-API-Sichten (Agent, Singleshot, Chat, Completion + Speech, Transcription)
auf einem gemeinsamen Vendor-File-Kern. Die vier Text-Sichten sind V1; die zwei
Audio-Sichten (Speech/Transcription) kommen mit T1410 additiv über LiteLLM dazu
(LLMP-S6/RAT-28).

**Library-Status (DCOMP-1):** Die LLM-Provider-Schicht ist eine **Library** —
kein eigener Prozess, kein Service, kein HTTP-Endpoint. Code lebt unter
`tools/llm/`, Konsumenten importieren via `from tools.llm import …` (analog
`tools.zugangsdaten`, `tools.configloader`, `tools.logsetup`). Die Lib hat
keinen eigenen Port und keinen eigenen systemd-Service
(`conventions/llm-providers.md` LLMP-1; RAT-20 Sektion „Patch 1").

**Scope:** Sechs Public-API-Sichten auf einem `_vendor/<vendor>.py`-Kern
(LLMP-2; die vierte Sicht `get_completion` mit #1131 belegt; die fünfte + sechste
`get_speech`/`get_transcription` mit T1410/RAT-28 belegt) · Capability-Matrix mit hartem Boot-Fail (LLMP-3/4) · synchrone
Telemetrie-Projektion nach `var/llm/provider_calls.jsonl` zusätzlich zur
bestehenden SQLite-Senke pro Buddy · Slot-Lookup über `tools.zugangsdaten`
(LLMP-5). Vendor V1: Anthropic.

**Out-of-Scope V1** (eigene Folge-Werften / Folge-RATs, sobald gebraucht):
HTTP-Fassade als Plattform-Dienst (erst bei externem Konsument außerhalb
Python) · TTS-/STT-Schicht (eigene Frage mit eigenen Anchors, kein
`tools/tts/` Vorweg) · EC-23-Umstieg auf JSONL-only (separate Folge-RAT) ·
Fusion zweier Sichten (Re-Litigation nach Vertrag-Drift-Schwelle).

## 1. Public-API

### LLMP-S1 — Sechs Sichten, ein Vendor-File
Die Lib stellt sechs Funktionen bereit: `get_agent(slot)`, `get_singleshot(slot)`,
`get_chat(slot)`, `get_completion(slot)` (die vier Text-Sichten, V1) sowie
`get_speech(slot)` und `get_transcription(slot)` (die zwei Audio-Sichten, T1410
additiv via LiteLLM, LLMP-S6/RAT-28). Jede gibt ein Sicht-Objekt zurück, das auf demselben
`_vendor/<vendor>.py`-Kern aufsetzt. Ein neuer Vendor (eine Datei) aktiviert
alle sechs Sichten — kein Adapter-Code pro Buddy
(RAT-20 Sektion „Finale Landung — MACH ES" → Was sich ändert).

- **`get_agent(slot, model="", max_tokens=0)` — Agent-Tool-Loop.** Für Konversationen mit Tool-Use
  und Mid-Turn-Continuation. Heutiger Use-Case: eltern-chat
  (`providers/claude.py`-Bestand). `model` ist optional (leer → Vendor-Default);
  Konsumenten mit eigenem `provider_model` reichen es durch, ohne dass die Lib
  das Vendor-DEFAULT erzwingt. `max_tokens` ist optional (0 → Vendor-Default
  2048); Konsumenten mit eigenem Fidelity-Bedarf reichen ihren Wert durch
  (eltern-chat: 4096 wie vor der Migration, statt stillem Rückfall auf den
  Lib-Default 2048 — analog `get_singleshot`/T1084, damit die Migration keinen
  unsichtbaren Token-Deckel-Rückgang verursacht). Required Capabilities: `tool_use`,
  `multi_turn_assistant_prefill`, `system_message_distinct` (LLMP-3).
  `cache_control` ist bewusst **kein** Boot-Fail-Minimum (LLMP-S7:
  Required-Set ist Boot-Fail-Minimum, kein Nutzungs-Whitelist) —
  LLMP-S9-Capability-Matrix-Review 2026-06-24 (eltern-chat dual-provider):
  Mistral unterstützt kein Prompt-Caching (`eltern-chat/providers/pricing.py:27`,
  `eltern-chat/providers/mistral.py:77-80`) und würde mit `cache_control` im
  Required-Set einen `LLMCapabilityError` beim Boot werfen. Vendoren mit
  Caching (Anthropic) setzen Cache-Marker weiterhin.
  **Opt-in `web_search` (T1371):** die Agent-Sicht darf ein **server-seitiges**
  `web_search`-Tool (Anthropic `web_search_20260209`, Opus 4.8/4.7/4.6 + Sonnet
  4.6) als Eintrag im `tools`-Array deklarieren — Suche auf Anbieter-Infra, **kein**
  externer Such-Provider und **kein** neuer ZD-Slot (nutzt den vorhandenen
  Vendor-Key). `web_search` ist die **7. ratifizierte Capability** (LLMP-3), aber
  **kein** Required-Set-Mitglied (nie Boot-Minimum — Mistral deklariert sie nicht,
  sonst wäre jeder Mistral-Agent-Slot boot-fatal). Die Fassade legt die
  Vendor-`CAPABILITIES` als `.capabilities` offen; der Rufer aktiviert das Tool
  NUR bei `"web_search" in agent.capabilities`. `.step(...)` extrahiert additiv
  `web_search` (Quellen `{url,title,page_age}` aus den `web_search_tool_result`-
  Blöcken) + `web_search_requests` (Anzahl der Suchen); ohne aktiviertes Tool
  bleiben beide `[]`/`0` (eltern-chat unberührt). Erster Konsument:
  hoerspiel-Recherche-Vorschritt (HSP-57).
- **`get_singleshot(slot, model="", max_tokens=0)` — Structured Singleshot.** Eine Anfrage, ein
  Schema-konformer Antwort-Block. Heutige Use-Cases: hoerspiel
  (Folgen-Beschreibung via JSON-Schema, forced `tool_use`) und
  Foto-Analyse/TAB (Termin-Liste aus einem Bild, forced `tool_use`, #1262).
  `model` ist optional (leer → Vendor-Default); Konsumenten mit eigenem Modell
  reichen es durch (analog `get_agent`). `max_tokens` ist optional (0 → Vendor-Default
  2048/4096); hoerspiel reicht Provider-MAX_TOKENS (8192/4096) durch, damit lange
  Folgentexte nicht trunkiert werden (T1084). Die Sicht-Methode ist
  `.complete_structured(system, prompt, schema, *, images=None)`: **`images`** ist eine
  optionale Liste von Bild-Blöcken (`{bytes, media_type}`), die neben dem Text an den
  Vendor gehen. **`images=None` ist byte-identisch der bisherige Text-Pfad** (hoerspiel
  unberührt; additiv wie `model`/`max_tokens`, T1084/T1129). Übergibt ein Rufer `images`,
  prüft die Lib die Vendor-Capability `multimodal_input` (LLMP-3, per-Rufer-Opt-in) und
  wirft `LLMCapabilityError`, falls der Slot-Vendor Bilder nicht kann. Required
  Capabilities (Boot-Fail-Minimum): `structured_output`, `system_message_distinct`
  (LLMP-3) — `multimodal_input` ist **nicht** im Required-Set (sonst würde jeder
  Text-only-Singleshot-Slot beim Boot fatal). **Keine eigene Text-Sicht für Foto-Analyse:**
  Foto-Analyse teilt TABs strukturierten Singleshot-Vertrag (forced `tool_use` → Schema-dict);
  eine eigene Text-Sicht käme erst bei eigenem Vertrag (ENTSCHEID-1262 → „KEINE fünfte
  Text-Sicht"); die fünfte und sechste Sicht sind `get_speech`/`get_transcription` (LLMP-S6).
- **`get_chat(slot)` — Multi-Turn-Chat.** Konversation mit History und
  System-Prompt, ohne Tool-Use im Kern-Pfad. Heutiger Use-Case: kibuddy
  (Sokratisch-Dialog mit Kind, Multi-Turn-Kontext). Required Capabilities:
  `multi_turn_assistant_prefill`, `cache_control`, `system_message_distinct`
  (LLMP-3).
- **`get_completion(slot, model="", max_tokens=0)` — Freitext-Singleshot.** Eine
  Anfrage (ein System + ein User), ein **Freitext-String** ohne Schema;
  Sicht-Methode `.complete(system, user) -> str` (kein Tool, kein Schema, ein
  Vendor-Call). Heutiger Use-Case: hoerspiel (Synopse-Fließtext, #1131 — der von dieser Klausel
  vor-autorisierte vierte Use-Case). `model`/`max_tokens` optional und
  durchgereicht (analog `get_singleshot`; hoerspiel reicht Provider-MAX_TOKENS
  8192/4096 durch, sonst stiller Rückfall auf Lib-Default 2048 und ein kleineres
  Modell). Required Capabilities: **nur** `system_message_distinct` — bewusst
  **kein** `structured_output` und **kein** `cache_control`, damit die Sicht
  beide Slots eines dual-provider-Buddys trägt (hoerspiel Claude **und** Mistral);
  `get_chat` wäre auf dem Mistral-Slot boot-fatal (LLMP-S9: Mistral ⊥
  `cache_control`).
- **`get_speech(slot, model="")` — TTS (T1410, LLMP-S6/RAT-28).** Sicht-Methode
  `.synth(text, *, voice, model="", speed=1.0, response_format="mp3") -> bytes`;
  ein Vendor-Call (`litellm.speech()`), Audio-Bytes zurück. Heutiger Use-Case:
  kibuddy-TTS (Motor-Swap weg von direktem Azure-SDK). Required Capability
  (LLMP-3): **nur** `speech`. `model` optional (leer → Vendor-Default); `max_tokens`
  entfällt (kein Text-Generierungs-Limit bei Audio). Ein Text-Hand-Vendor unter
  dem Slot ist boot-fatal (LLMP-S3) — er kann kein Audio, und das ist korrekt.
- **`get_transcription(slot, model="")` — STT (T1410, LLMP-S6/RAT-28).**
  Sicht-Methode `.transcribe(audio, *, filename="audio.mp3", model="", language="de")
  -> str`; ein Vendor-Call (`litellm.transcription()`), Transkript-Text zurück.
  Heutiger Use-Case: kibuddy-STT. `audio` ist bereits normalisiert — die
  ffmpeg-Transcodierung (#1442) sitzt im STT-Engine-Adapter VOR diesem Call, nicht
  in der Lib. Required Capability (LLMP-3): **nur** `transcription`. Boot-Fail bei
  Text-Hand-Vendor (LLMP-S3).

Eine siebte Sicht wird erst hinzugefügt, wenn ein weiterer Use-Case mit
**eigenem** Vertrag belegt ist (CLAUDE.md §6, „Vorschlagen, wenn Werte sich
vermehren"). Die zwei Audio-Sichten haben einen eigenen Modalitäts-Ein-/Ausgabe-
Vertrag (`bytes` rein/raus statt Text) — genau das rechtfertigt sie als Sicht
statt als Capability-Opt-in innerhalb einer Text-Sicht (Gegenprobe
`multimodal_input`, LLMP-2/Convention).

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

### LLMP-S14 — Monats-Roll-up + Preis-Staleness-Warnung (Telemetrie C, #1368)
Eine wiederholbare Pro-Familie-Kosten-Auswertung über die bereits gebaute
`tools/llm/telemetry_read.aggregate(events, group_keys)`-Mechanik: der
**Monats-Roll-up** gruppiert die `provider_calls.jsonl`-Events nach
`(caller, modality, month)` — `month` als `YYYY-MM` aus dem `ts`-Feld abgeleitet —
und liefert pro Gruppe `calls`, `input_tokens`, `output_tokens`, `est_cost_eur`
(LLMP-S4-Schema, Null-Preis-Semantik `OPEN-LLMP-A`). Die Gruppierung IST die
Topf-Trennung — kein separater Topf-Schlüssel.

**Staleness-Warnung:** Trägt eine Gruppe `est_cost_eur: None`-Beiträge (Preiszeile
fehlt/veraltet) ODER stützt sie sich auf eine Preiszeile mit altem `as_of`, wird die
Gruppe als **„Preis unvollständig/veraltet"** markiert — der Roll-up meldet nie eine
scheinbar vollständige Summe über einer lückenhaften Preisbasis.

**Bewusst NICHT jetzt (n=1, RAT-17-Disziplin):** KEIN `instance_id`-/Familien-Feld —
solange nur eine Familie/Instanz läuft, ist die Instanz-Achse ein Lego-Bruch auf
Vorrat. Vertagt bis reale Familie-2-Hardware (berater-Paket
`20260706-2140-telemetrie-1268`); bis dahin gruppiert der Roll-up nur nach
`caller × modality × month`.

## 3. TTS/STT — in Scope via LiteLLM (RAT-28)

### LLMP-S6 — TTS und STT via LiteLLM in Scope (Umkehr RAT-20)

> **RAT-28 (2026-07-24)** kehrt den RAT-20-Ausschluss um. Der ursprüngliche
> Grund war „eigene Frage mit eigenen Anchors" — das entfällt, da LiteLLM
> beide Modalitäten abdeckt (`litellm.speech()` / `litellm.transcription()`).
> LLMP-S6 bleibt als Paragraph erhalten, sein Inhalt ist jetzt umgekehrt.

TTS und STT sind **Teil dieser Spec**. Provider wird Config-Sache analog Chat
(LLMP-5-Slot). Der Buchhalter (`write_call`) bleibt SSoT auch für Audio-Calls
— die Kosten-QUELLE ist seit dem RAT-26-§5-Amendment (2026-07-30) auch für
Audio LiteLLM-nativ: `tts-1-hd` trägt `input_cost_per_character`, whisper
(`azure/whisper-1`) Kosten pro Sekunde (Live-Probe litellm 1.93.0). Der frühere
„für Audio nicht genutzt"-Ausschluss und der akzeptierte Präzisions-Gap
entfallen damit (RAT-28 §4 mit-amendiert).

**TTS** (`litellm.speech(text, voice=..., model=...)`): Provider per Slot
(Azure als Default; ElevenLabs/Groq/OpenAI testbar). Kein Provider-Code mehr
direkt in kibuddy/eltern-chat. Public-Sicht: `get_speech(slot)` (LLMP-S1);
Required Capability `speech` (LLMP-3).

**STT** (`litellm.transcription(file=..., model=...)`): Provider per Slot
(analog TTS). berater-runde-1268-Defer „NOCH NICHT" durch LiteLLM-Doktrin
aufgehoben (RAT-28). Public-Sicht: `get_transcription(slot)` (LLMP-S1);
Required Capability `transcription` (LLMP-3).

**Ratifiziert (T1410, RAT-28):** die zwei Audio-Sichten (`get_speech`,
`get_transcription`) und die zwei Audio-Capabilities (`speech`, `transcription`)
sind Teil der Public-API-Matrix (LLMP-S1/LLMP-2) und der Capability-Liste
(LLMP-3). Nur der litellm-Vendor deklariert die zwei Capabilities; ein Text-
Hand-Vendor unter einem Audio-Slot ist boot-fatal (LLMP-S3), was korrekt ist.
Kein Text-Vertrag (Agent/Singleshot/Chat/Completion) ändert sich durch die
Erweiterung.

**Was NICHT in dieser Spec liegt:** kibuddy-speed-Cache (technischer Vorteil
durch lokale Zwischenspeicherung), hoerspiel-Asset-Lifecycle (Kapitelschnitt,
Transkript-Pipeline). Diese wohnen UM den LiteLLM-Call herum in den
Buddy-Specs (`specs/buddies/kibuddy.md`, `specs/buddies/hoerspiel.md`).

Kill-Kriterium: `litellm.speech()` zeigt Inkompatibilität mit
Azure-TTS-Parametern, die kibuddy-speed-Cache oder hoerspiel-Vorauflösungs-Pfad
brechen → Slot fällt zurück auf direkten Azure-SDK-Call. Bau: #1410.

## 4. Motor = LiteLLM (in-Prozess, RAT-20 unangetastet)

### LLMP-S12 — LiteLLM als Vendor-Motor unter der Fassade (RAT-26)

> **RAT-26 (2026-07-05)** ratifiziert LiteLLM als neues, separates Vendor-Modul
> `tools/llm/_vendor/litellm.py` — in-Prozess, kein HTTP-Hop, kein eigener
> Service, kein eigener Port. RAT-20 bleibt in allen anderen Punkten vollständig
> gültig (Lib-Form, keine Service-Fassade, keine HTTP-Fassade, LLMP-1).

Die vier Text-Sichten (`get_chat`, `get_singleshot`, `get_completion`,
`get_agent`), der LLMP-5-Slot-Resolver, die Capability-Matrix (LLMP-3) und die
Telemetrie (LLMP-S4) bleiben **unverändert**. LiteLLM ist Motor **unter** der
Fassade — kein neuer API-Vertrag.

**Gestaffelte Migration (drei Slots):**

> **Revision 2026-07-24 (Nic-Setzung):** Revidiert die ursprüngliche
> RAT-26-§3-Sequenz (cache-frei zuerst). kibuddy-Chat (`get_chat`) wird als
> bewusster Slot-1-Pilot vorgezogen (#1433, gemergt 2026-07-24). Die
> Cache-Passthrough-Verifikation ist nachgelagert: der Live-Test hat
> `cache_control`-Marker-Akzeptanz + `usage`-Mapping bereits belegt; volle
> Multi-Turn-Cache-Hit-Prüfung (`cache_read_tokens>0`) erfolgt via
> #1315-Golden-Fixture (nicht als Slot-1-Vorbedingung).

1. **Slot 1 — kibuddy-Chat** (`get_chat`): `kibuddy`-Slot als bewusster
   Erstmigrant (#1433, gemergt 2026-07-24). Cache-abhängig, aber bewusst
   vorgezogen: `cache_control`-Marker-Akzeptanz und `usage`-Mapping per
   Live-Test belegt; vollständige Multi-Turn-Cache-Hit-Prüfung nachgelagert
   (#1315-Golden).
2. **Slot 2 — Chat + Singleshot (Rest)** (`get_chat`, `get_singleshot`,
   `get_completion`): verbleibende `seiten`/`hoerspiel`-Slots sowie `eltern-chat`.
   Voraussetzung: Golden-Set #1315 grün.
3. **Slot 3 — Vendor-Cleanup:** Hand-Vendor-Files (`_vendor/anthropic.py`,
   `_vendor/mistral.py`) werden erst gelöscht + Dependency-Pin gesetzt,
   nachdem alle Slots mehrere Wochen grün auf LiteLLM laufen. Der Lösch-Schritt
   ist die Ein-Wege-Tür — Rückweg über Slot-Segment-Tausch bleibt bis dahin
   offen.

**Hand-Vendoren laufen bis Slot-3-Cleanup parallel weiter.** Kein Buddy-Code
ändert sich durch den Motor-Wechsel (Fassade unverändert). Rückweg: Slot-Segment
im ZD-Slot-Namen zurück auf Hand-Vendor-Segment, ohne Code-Change.

**Telemetrie-Schreib-SSoT bleibt Hand, Preis-QUELLE ist LiteLLM-nativ**
(LLMP-S12, RAT-26 §5 **amendiert 2026-07-30**): `telemetry.write_call` →
`provider_calls.jsonl` (LLMP-S4/SVC-5) bleibt **Schreib-SSoT**. Die
Kosten-Quelle wechselt von der Hand-`pricing.py`-Tabelle auf LiteLLMs
`response_cost` (USD→EUR an der `_emit_*`-Naht); genuine Katalog-Lücken werden
beim Adapter-Init per `litellm.register_model()` in dieselbe Engine geseedet
(kein paralleles pricing.py). Zahl-Stabilität bei Rollback + Preis-Drift-Schutz
(der ursprüngliche RAT-26-§5-Grund) sind jetzt durch einen **gepinnten litellm**
(RAT-33 pyproject-SSoT) adressiert — neue Preise nur mit bewusstem litellm-Bump.
Bau via #1620 (Kinder #1634/#1635/#1636).

**LLMP-4-Spannung:** `_vendor/litellm.py` frontet mehrere Anbieter mit
divergenten Capabilities — die Aufhängung der `CAPABILITIES`-frozenset an einen
Multi-Anbieter-Motor ist eine offene Convention-Delta-Frage (RAT-26 Offene
Folge-Punkte; Convention-Delta-Runde noch ausstehend).

Bau-Ticket: #1316. Ratifiziertes Paket:
`brainstorm/berater-runde/20260705-2223-RATIFIZIERT-1316-litellm-rat26.md`.

### LLMP-S13 — `mistral/`-Modell-Präfix zentral normalisieren; Store-Slots im LLMP-5-Format

**Anlass:** Deploy-Regression #1452 — LiteLLM erwartet für Mistral-Modelle den
Modellnamen mit dem Präfix `mistral/`; ohne diese Normalisierung schlug ein
Deploy fehl und musste zurückgerollt werden.

**Präfix-Normalisierung — zentral (Nic-Setzung 2026-07-25, Variante A, #1463).**
Die Ergänzung des anbieter-spezifischen Modell-Präfixes (`mistral/…`) passiert
**zentral in der Modell-Auflösung, vor den `get_*`-Sichten** — an **einer** Stelle
für alle Anbieter, **nicht** pro Vendor-File. So gibt es genau einen Ort, an dem
Modellnamen anbieter-korrekt normalisiert werden, und der Aufrufer muss das
Präfix nicht kennen.

**Store-Slot-Benennung — LLMP-5-Form mit litellm-Motor-Segment (Nic-Setzung
2026-07-27, #1463; Realitäts-Nachzug T1492).**
Die Zugangsdaten-Store-Slots für die litellm-Motor-Pfade folgen der LLMP-5-
Konvention `<konsument>-<vendor>-<purpose>`, wobei `<vendor>` = `litellm`
(der sanktionierte Motor-Slug, LLMP-4/RAT-26) und `<purpose>` einen
**vendor-slug-freien** Marker trägt — kein zweiter Anbieter-Slug im Purpose,
sonst matcht `parse_slot` zwei Vendoren (litellm UND den Anbieter) und bricht
boot-fatal (LLMP-5-Falle). Konkrete Purpose-Marker:

- `claude-api-key` — Claude-Anbieter-Zugang via litellm-Motor
- `eu-api-key` — EU-Rechenzentrum-Zugang (Mistral) via litellm-Motor

Beispiele: `eltern-chat-litellm-claude-api-key`, `hoerspiel-litellm-eu-api-key`.
Die Slot-Namen werden über `tools.llm.litellm_slot_for_provider(caller, provider)`
gebildet (T1492, n=2-Naht); jede App entscheidet app-lokal, welchen Zugang sie
nutzt — dieser Parameter ist App-Config (App-Config-Prinzip: Welcher Anbieter-
Zugang genutzt wird, ist Buddy-Sache, nicht Lib-Sache, LLMP-5). Dies gilt als
Interim, **bis der begonnene zentrale Routing-/Zugangs-Service** diese Wahl
übernimmt; danach kann die Zuordnung dorthin wandern.

> **Nic-Confirm ausstehend:** Die Setzung 2026-07-27 formulierte „nach dem
> Anbieter benannt (`Mistral`, `Claude`)" als Ziel-Richtung. Der real gebaute
> Code (#1463) folgt zwingend LLMP-5 (`<app>-litellm-<purpose>`) — ein
> Bare-Slug `Mistral` hat <3 Segmente und ist parse_slot-boot-fatal. Dieser
> Abschnitt zieht die Realität nach; er enакт keine neue Mechanik-Entscheidung,
> sondern beschreibt den fertig gebauten Stand (T1492).

**Setzt RAT-26/LLMP-S12 um** (keine Re-Litigation) — konkretisiert nur die
mistral-Präfix-Verortung und die Slot-Namen für die Slot-2-Migration
(`eltern-chat` dual-provider). Bau: #1463. Slot-Konsolidierung: T1492.

## 5. Migrationspfad (Buddy-Abfolge)

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
   der **ratifizierten** LLMP-3-Capabilities (`CAPABILITIES`-frozenset) zu
   nutzen — die Ein-File-These versteckt dann echte Vendor-Divergenz. Das
   Required-Set einer Sicht ist nur das **Boot-Fail-Minimum** (LLMP-S3), **kein**
   Nutzungs-Whitelist: dass `get_chat`/`get_singleshot`/`get_agent` zusätzlich
   eine ratifizierte Capability nutzen, die nicht in *ihrem*
   Required-Set steht (z. B. `cache_control` in Singleshot, `web_search` in Agent),
   ist erlaubt. Erweitern der Liste ist selbst eine Spec-Änderung (LLMP-3) und der
   eigentliche Bruch-Pfad (ENTSCHEID Paket-Sektion „Capability-Bruch scharf"
   → Capability-Flucht). So geschehen bei `web_search` (7. Capability, T1371):
   ratifiziert und additiv aufgenommen, kein Required-Set berührt.
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

**Skill-lokale Multimodal-Adapter folgen derselben Zwei-Schritt-Disziplin
(ENTSCHEID-1262 → „Patch B").** Zieht ein eltern-chat-Skill seine eigene
Vendor-Naht (`eltern-chat/skills/_multimodal/`, TAB, #1262) auf `tools.llm`, gilt die
additiv-rückrollbare Sequenz wörtlich: **PR 1** stellt den Skill auf
`get_singleshot(...).complete_structured(..., images=…)` um und markiert
`skills/_multimodal/` als deprecated (Legacy bleibt lauffähig); **PR 2** löscht
`skills/_multimodal/` erst **nach** grüner Live-Probe (keine produktive
`skills._multimodal`-Nutzung, Tests grün, Foto-Telemetrie-Zeile sichtbar). Kein
Migrieren-und-Löschen im selben PR (CLAUDE.md „deprecate → migrate → separater
Lösch-PR").

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
Mistral-Anbieter, da eltern-chat dual-provider fährt).

**LLMP-S9-Befund eltern-chat 2026-06-24:** Mistral ⊥ `cache_control`
(kein Prompt-Caching; `pricing.py:27`, `mistral.py:77-80`). Konsequenz:
`cache_control` aus dem `get_agent`-Required-Set entfernt — Begründung
und Patch in LLMP-3 (Convention) und LLMP-S1 (Spec, `get_agent`-Bullet).

Der **Spike-Stufe-2-Beleg**
(7 Tage Familie-1, JSONL-vs-SQLite-`est_cost_eur`-Diff < 1%/Tag — sonst
Schreibpfad-Fix vor weiterer Migration) ist **die Live-Probe des
eltern-chat-Migrations-Tickets selbst** und läuft folgerichtig **nach** dessen
Merge (eltern-chat ist der erste Voll-Last-Konsument; Stufe-2 ohne live
migrierten eltern-chat ist nicht erhebbar). Re-Order-Konsequenz 2026-06-24:
da eltern-chat als n=2 vorgezogen ist, fällt Stufe-2 mit der eltern-chat-
Migration zusammen, nicht mit einem davorliegenden dritten Buddy
(ENTSCHEID-File Sektion „Spike-Experiment (2 Stufen)" → Stufe 2 +
Re-Evaluierungs-Klausel; Re-Order Nic 2026-06-24).

## 6. Tests

### LLMP-S11 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), ohne Netz. Mindest-Abdeckung:

- **LLMP-S1** — die vier Text-Sichten existieren und liefern sicht-spezifische
  Objekte mit dokumentierten Methoden; `get_speech`/`get_transcription` (LLMP-S6)
  decken die zwei Audio-Sichten ab.
- **LLMP-S1 (Bild-Content)** — `complete_structured(..., images=[…])` reicht
  Bild-Blöcke an den Vendor durch; `images=None` erzeugt einen byte-identischen
  Text-only-Call (hoerspiel-Pfad unverändert). `images=[…]` gegen einen Fake-Vendor
  ohne `multimodal_input` wirft `LLMCapabilityError` (ENTSCHEID-1262).
- **LLMP-S3** — Capability-Mismatch beim Boot wirft `LLMCapabilityError`
  (Fake-Vendor mit reduzierter `CAPABILITIES`-Frozenset; jede Sicht
  separat getestet).
- **LLMP-S4** — JSONL-Schreibung enthält alle Pflichtfelder; Schreibfehler
  führt zu Warning, nicht zu Crash (Fake-FS mit ReadOnly).
- **LLMP-S6 (Audio-Dispatch, T1410)** — `get_speech`/`get_transcription`
  liefern Sicht-Objekte mit `.synth`/`.transcribe`; der Runtime-Dispatch
  `cfg.{stt,tts}_provider=="litellm"` → `kibuddy.main._build_{stt,tts}` baut die
  `Litellm*Engine` mit dem konfigurierten Slot/Modell (Entry-Path, nicht nur
  isolierte Engine-Konstruktion); unbekannter Provider-Wert → `ConfigError` beim
  `resolve_runtime` (Whitelist `VALID_{STT,TTS}_PROVIDERS`). Beleg:
  `kibuddy/tests/test_litellm_dispatch.py` + `kibuddy/tests/test_stt_litellm.py`.

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
