# RAT-20 — LLM-Provider-Schicht: `tools/llm/` als Lib-Schwester zu `tools/zugangsdaten/`

- **Entschieden:** 2026-06-21 (Berater-Runde „LLM-Provider-Schicht — Lib vs.
  Service vs. Buy", Berater + Codex-Antiberater, zwei Runden + sechs Nic-
  Verdikte), **ratifiziert** 2026-06-21 (Nic, alle sechs Fragen mit „ja"
  entschieden; Migrations-Reihenfolge umgedreht auf **KIBuddy → hoerspiel →
  eltern-chat**).
- **Betrifft:** `conventions/llm-providers.md` (neu, LLMP-1..LLMP-5),
  `specs/platform/llm-providers.md` (neu, LLMP-Verhaltens-Spec mit
  Telemetrie-Doppelschreib-Disziplin), `decisions/RAT-6-296-…` (Marginalie
  an :71 — siehe Norm-Diff unten), `specs/buddies/kibuddy.md` (OPEN-KIBUDDY-F
  geschlossen), `decisions/INDEX.md`. Folge-Werften (eigene Tickets, nicht
  Teil dieser RAT): Spike-Stufe-1-Fixtures, Migrations-Werft KIBuddy,
  Migrations-Werft hoerspiel, Migrations-Werft eltern-chat.
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/20260621-231847-RATIFIZIERT-llm-provider-lib.md`
  → Vorschlag `20260621-231847-vorschlag-llm-provider-lib.md`,
  Antiberater (Codex) `2026-06-21-2320-antiberater-llm-provider-lib.md`.

## Norm-Diff zu RAT-6:71 (Patch-1-Klausel, harte Überschreibung)

Diese Ratifizierung **ersetzt** in `decisions/RAT-6-296-familien-schnittstelle-skalierung.md:71`
den Wortlaut

> „LLM-Gateway (Plattform-Dienst B): ab KIBuddy (2. Konsument)."

durch

> **„LLM-Gateway (Plattform-Lib `tools/llm/`): ab KIBuddy (2. Konsument).
> Form ist Lib mit In-Prozess-Public-API; eine HTTP-Fassade als Plattform-
> Dienst wird erst ratifiziert, wenn ein externer (nicht-Python / nicht-In-
> Prozess) Konsument belegt ist."**

RAT-6 selbst wird **nicht editiert** (Wortlaut bleibt als Diff-Anker stehen);
die Marginalie an :71 macht den Sieger sichtbar
(ENTSCHEID-File Sektion „Patch 1 — RAT-N überschreibt RAT-6-Wortlaut explizit").

## Beschluss

Die LLM-Provider-Schicht zieht aus den drei Buddies (eltern-chat, hoerspiel,
kibuddy) in die Plattform als **Library** unter `tools/llm/` — analog
`tools/zugangsdaten/`, kein eigener Prozess, kein HTTP-Hop. Konsumenten
importieren `from tools.llm import get_agent, get_singleshot, get_chat`. Die
Lib hat **drei Public-API-Sichten** auf einem gemeinsamen
`_vendor/<vendor>.py`-Kern; ein neuer Vendor ist ein File, alle drei Sichten
sind ohne Adapter-Kopie verfügbar
(ENTSCHEID-File Sektion „Finale Landung — MACH ES").

**Sechs konkrete Entscheidungen (ratifiziert):**

1. **Form ist Lib, nicht Service, nicht LiteLLM-Buy.** Plattform-Dienst-Form
   erst, wenn ein externer (nicht-Python / nicht-In-Prozess) Konsument
   belegt ist. Norm-Diff zu RAT-6:71 oben
   (ENTSCHEID-File Sektion „Patch 1 — RAT-N überschreibt RAT-6-Wortlaut
   explizit").
2. **Capability-Matrix mit hartem Boot-Fail.** Vendor-File deklariert
   `CAPABILITIES = frozenset({...})` am Modulkopf; jede `get_*`-Sicht
   deklariert ihr Required-Set; bei Slot-Vendor-Mismatch wirft die Lib
   beim Boot `LLMCapabilityError`, kein Runtime-Silent-Fallback
   (ENTSCHEID-File Sektion „Patch 2 — Capability-Matrix + harter Boot-Fail").
3. **Telemetrie-Doppelschreibung** (Patch 3). eltern-chats SQLite
   (`conversations.db.provider_calls`, EC-23 + E-EC-11) bleibt **SSoT** und
   wird **nicht** angetastet; die Lib schreibt **zusätzlich** synchron
   `var/llm/provider_calls.jsonl`. EC-23-Umstieg auf JSONL-only ist
   **separate Folge-RAT**, nicht Teil dieser Ratifizierung
   (ENTSCHEID-File Sektion „Patch 3 — Telemetrie-Doppelschreibung").
4. **TTS/STT aus Scope.** Diese RAT ratifiziert ausschließlich die
   LLM-Provider-Schicht. Keine `tools/tts/`-Vorwegnahme, keine
   „Schwester-Lib im selben Stil"-Behauptung
   (ENTSCHEID-File Sektion „Patch 4 — TTS aus Scope").
5. **Spike-Stufe-1 vor zweitem Buddy.** Drei Fixtures (Agent-Tool-Loop,
   Structured-Singleshot, Multi-Turn-Chat) gegen denselben
   `_vendor/anthropic.py`. Erfolg = alle drei grün mit derselben Vendor-
   Datei. Stufe-2 = eltern-chat (oder erster Voll-Last-Buddy) 7 Tage
   Familie-1, Diff JSONL-vs-SQLite-Kosten >1%/Tag = Schreibpfad-Fix vor
   weiteren Migrationen
   (ENTSCHEID-File Sektion „Spike-Experiment (2 Stufen)").
6. **Migrations-Reihenfolge KIBuddy → hoerspiel → eltern-chat.**
   KIBuddy zuerst, weil (a) wörtlicher RAT-6-Trigger („ab KIBuddy"),
   (b) Blast-Radius am kleinsten (KIBuddy-Ausfall = nur Kind-Chat down,
   kein Familien-Workflow gefährdet), (c) Multi-Turn deckt mögliche
   Detail-Funde früh auf. eltern-chat zuletzt, weil dort EC-23-Doppel-
   Schreib-Disziplin am ausgereiftesten erprobt sein muss. Pro Migration
   additiv-rückrollbar (alter `<buddy>/providers/`-Ordner bleibt, bis
   neuer Pfad grün; dann erst Alt-Pfad löschen)
   (ENTSCHEID-File Sektion „Migration nach Spike-Erfolg" — Verdikt
   Frage 6).

## Warum

- **Constitution-Rang Einfachheit (Rang 2) schlägt Flexibilität.** Eine Lib
  mit drei Sichten + Capability-Matrix erhöht API-Oberfläche moderat;
  drei separate Adapter-Kopien (heutiger Stand, 1087 Z Provider-Code in
  drei Vertragsformen für denselben Vendor) erhöhen Wartungs-Last
  überproportional. Trade-off bricht über Rang 2
  (ENTSCHEID-File Sektion „Finale Landung — MACH ES" → Trade-off-Block).
- **E-ZD-3-Präjudiz.** `tools/zugangsdaten/` hat genau dieselbe Frage
  („Lib oder Netz-Dienst?") explizit zu Lib entschieden (`zugangsdaten.md:215-221`,
  „Ein Dienst wäre Komplexität ohne belegten Bedarf"). LLM-Provider hat
  identische Konsumenten-Topologie (alle In-Prozess auf demselben Hub).
- **DCOMP-1-Satz-2** verankert das Layer-Modell: `tools/` ist die
  prozesslose Library-Schicht (`conventions/module-boundaries.md:18-20`).
  `tools/llm/` setzt das Muster ohne neue Schicht fort.
- **Heim-Server-Linse.** HTTP-Hop zwischen Buddy und LLM-Provider auf
  demselben Pi ist Cloud-Reflex ohne belegten Mehrwert (kein externer
  Konsument, keine Sprach-Isolation nötig — alle drei Konsumenten sind
  Python).
- **RAT-6-Trigger erfüllt.** „LLM-Gateway ab KIBuddy (2. Konsument)" —
  KIBuddy ist der zweite Konsument (eltern-chat = 1., hoerspiel = 2./3.,
  KIBuddy macht Multi-Turn als drittes Vertrags-Muster). Trigger sauber
  mehrfach verankert: RAT-6:71, OPEN-KIBUDDY-F (`kibuddy.md:784-787`),
  HSP-Antizipation (`hoerspiel.md:362-365`).

## Was die Runde explizit NICHT ratifiziert hat

- **HTTP-Fassade als Plattform-Dienst.** Erst, wenn ein externer
  (nicht-Python / nicht-In-Prozess) Konsument belegt ist. Re-Trigger:
  belegter dritter LLM-Konsument außerhalb der Python-Welt.
- **TTS/STT-Schicht.** Eigene Folge-Werften mit eigenen Anchors
  (Asset-Lifecycle, speed-Cache). `kibuddy.md:487`-TTS-Trigger ist real,
  aber eigene Frage
  (ENTSCHEID-File Sektion „Patch 4 — TTS aus Scope").
- **EC-23-Umstieg auf JSONL-only.** SQLite bleibt SSoT bei eltern-chat;
  JSONL ist Lib-Projektion zusätzlich. Umstieg = separate Folge-RAT
  (ENTSCHEID-File Sektion „Patch 3 — Telemetrie-Doppelschreibung").
- **Fusion zweier Sichten** (wenn nach 6 Monaten zwei Sichten >70% Code
  teilen). Eigene Re-Litigation
  (ENTSCHEID-File Sektion „Kill-Kriterium" → Vertrag-Drift).

## Kill-Kriterium

- **Lib-Form bricht:** Spike-Stufe-1-Fixture 1 (Agent-Tool-Loop) braucht
  Vendor-spezifischen Code jenseits Capability-Matrix → RAT zurückziehen,
  NOCH NICHT. Re-Trigger: konkreter dritter LLM-Konsument außerhalb
  Python.
- **Telemetrie-Doppelschreib bricht:** Spike-Stufe-2 zeigt nach 7 Tagen
  Familie-1, dass JSONL-Lock-Contention Telegram-Latenz bricht → Patch 3
  nicht haltbar, NOCH NICHT.
- **Vertrag-Drift:** Nach 6 Monaten teilen zwei Sichten >70% Code →
  fusionieren; Capability-Matrix-Verstecken-Frage neu öffnen
  (ENTSCHEID-File Sektion „Kill-Kriterium").

## Re-Litigation / Reopen nur bei erfülltem Trigger

- **Form re-litigieren:** belegter dritter LLM-Konsument außerhalb der
  Python-Welt (Browser-Extension, andere-Sprache-Service, externes
  Familien-Mitglied) → HTTP-Fassade neu prüfen.
- **EC-23-Umstieg:** wenn JSONL nach >3 Monaten Familie-1 stabil ist UND
  die Analyse-Pipeline auf JSONL umgestellt ist UND kein
  Backfüll-Bedarf aus SQLite mehr besteht → separate Folge-RAT öffnen.
- **Capability-Matrix-Strenge re-litigieren:** wenn der harte Boot-Fail
  in der Praxis mehr Reibung verursacht als er Fehler abfängt
  (Belegfall-Schwelle: ≥3 Boot-Fail-Vorfälle pro Quartal aus Capability-
  Drift, nicht aus echtem Mismatch).

## Anti-Pattern-Check

- **Premature Generalization:** vermieden — RAT-6-Trigger ist erfüllt
  (2. Konsument); drei Vertragsformen für denselben Vendor sind belegter
  Drift, keine antizipierte Architektur.
- **Premature Mechanism (PW-37):** vermieden — Convention LLMP entsteht
  *mit* der Lib (gleicher PR-Kontext), nicht vor ihr; der Capability-
  Matrix-Boot-Fail ist eine mechanische Durchsetzung der ratifizierten
  Bauregel LLMP-3 (zulässig nach `conventions/README.md:24-27`).
- **Industrie-Reflex (Service-Hop, LiteLLM):** vermieden — Antiberater
  hat E-EC-5/E-EC-6 als Halt für Buy-Ablehnung bestätigt; E-ZD-3-Präjudiz
  + Heim-Server-Topologie als Halt für Lib statt Service.
- **Architecture Astronaut:** vermieden — drei Sichten sind nicht „auf
  Vorrat", sondern entsprechen drei belegten Vertragsformen im Bestand
  (eltern-chat Agent, hoerspiel Singleshot, kibuddy Multi-Turn).
