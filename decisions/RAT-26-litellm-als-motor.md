# RAT-26 — LiteLLM als tools/llm-Motor (separates `_vendor/litellm.py` unter der Fassade)

- **Entschieden:** 2026-07-05 (berater-runde „LiteLLM-Motor / RAT-20-Reopen", Berater + Antiberater; Reopen von Nic bestätigt).
- **Ratifiziert:** 2026-07-05 (Nic-Verdikt „a" auf dem berater-runde-Board).
- **Überschreibt:** RAT-20 Entscheidung #1 („nicht LiteLLM-Buy") auf der **Build-vs-Buy-Achse**. RAT-20 sonst unberührt.

## Kontext — warum der Reopen legitim ist
RAT-20 (2026-06-21) verwarf LiteLLM auf **zwei** unabhängigen Achsen: (a) Build-vs-Buy (E-EC-5, `eltern-chat.md:1814-1818`: kein Framework, weil es eine fremde Anbieter-Abstraktion mitbringt und die Austauschbarkeit EC-11/12 untergräbt) und (b) Lib-vs-Service (Heim-Server-Topologie). #1316 will LiteLLM als **SDK-in-Prozess** — kein Service-Hop, Achse (b) also unberührt. Achse (a) stand auf der **Prämisse** „der Loop ist klein genug, dass die Eigenleistung günstiger ist als die Fremdbindung". Diese Prämisse ist durch den Scope-Wachstum (mehr Anbieter + Fallback + self-hosted) gekippt — legitime Re-Litigation, kein Übersehen.

## Entscheidung
1. **LiteLLM als NEUES, separates Vendor-Modul** `tools/llm/_vendor/litellm.py` (ModelResponse-/OpenAI-Shape-Parse), **NICHT** in `anthropic.py`/`mistral.py` eingepflanzt. Die Hand-Vendoren bleiben zunächst parallel → der Tausch ist **zweiseitig reversibel** (Slot-Segment zurück auf Hand-Vendor), solange nicht gelöscht. (Antiberater-BRICHT: der In-place-Seam ist am Code falsifiziert — anthropic.py parst SDK-Objekt, mistral.py OpenAI-Dict, litellm liefert ModelResponse.)
2. **Die vier Public-Sichten + das kanonische, anbieter-neutrale Modell (E-EC-6, EC-11/12) bleiben unverändert.** LiteLLM ist Motor **unter** der Fassade, keine neue API.
3. **Golden-Set (#1315) ZUERST** grün (Regressions-Netz), **dann** Slot-für-Slot über den ratifizierten LLMP-5-Segmenttausch migrieren: `seiten`/`hoerspiel` (singleshot, cache-frei) **vor** `kibuddy`/`eltern-chat` (get_chat, cache-abhängig).
4. **Cross-Provider-Fallback (`fallbacks=[…]`) ist DEFERRED** — er verlangt Multi-Key **oberhalb** der Vendor-Files (= die abgelehnte Super-Vendor-Form, kippt LLMP-5). Nic-Ziel ist Provider-Wahl **je Schnittstelle** (LLMP-5-Slot), nicht Auto-Fallback — das ist mit dem Segmenttausch bereits erfüllt.
5. **Telemetrie bleibt Hand:** `telemetry.write_call` → `provider_calls.jsonl` (SVC-5) bleibt SSoT, `pricing.py` bleibt Preis-SSoT — **nicht** litellm-native-Callbacks / `model_cost` (Zahl-Stabilität bei Rollback + Preis-Drift-Schutz). **[AMENDIERT 2026-07-30]** Der **Preis-SSoT-Teil ist umgekehrt:** die Kosten-QUELLE ist jetzt LiteLLM-nativ (`response_cost`, USD→EUR), die `pricing.py`-Tabelle stirbt, genuine Katalog-Lücken werden per `litellm.register_model()` in dieselbe Engine geseedet. Die zwei ursprünglichen Gründe (Rollback-Zahl-Stabilität + Preis-Drift-Schutz) sind stattdessen durch einen **gepinnten litellm** (RAT-33 pyproject-SSoT) adressiert — neue Preise nur mit bewusstem Bump. Live-Probe (litellm 1.93.0, 2026-07-30) belegte volle Provider-Abdeckung inkl. Audio (`tts-1-hd` per-character, `azure/whisper-1` per-second). `telemetry.write_call` bleibt **Schreib**-SSoT (unverändert). Ratifiziert Berater-Runde 2026-07-30 (`brainstorm/berater-runde/20260730-2130-RATIFIZIERT-unified-cost-adapter.md`), Bau #1620 (Kinder #1634/#1635/#1636).
6. **Abnahme-Bedingung (Nic, 2026-07-05):** je Schnittstelle liefert LiteLLM, was das Hand-Setup konnte, UND verschiedene Provider sind je Schnittstelle testbar. Wenn gegeben → so weiter.

## Kill-Kriterium
(a) Golden #1315 reproduziert `cache_read_tokens>0` auf Multi-Turn NICHT → cache-abhängiger Slot bleibt auf Hand-Vendor. (b) RSS-Delta/Import-Zeit auf dem pi5-Runner mit 10 geladenen Sessions über Schwelle → abbrechen. Rückweg immer: Slot-Segment zurück auf Hand-Vendor. Der **Lösch-Schritt** (Hand-Vendoren raus + Dependency-Pin) ist die **Ein-Wege-Tür** — zuletzt, erst nach n Wochen grünem Golden über alle Slots.

## Anti-Pattern-Check (gegen RAT-20)
Service-Hop-Ablehnung (RAT-20 Achse b) bleibt gültig — LiteLLM läuft in-Prozess, kein Hop. Buy-Ablehnung (Achse a) wird bewusst überschrieben, WEIL ihre Kosten-Prämisse gekippt ist; die Austauschbarkeit (EC-11/12) wird durch die **erhaltene Fassade + LLMP-5** geschützt, nicht mehr durch den Hand-Kern.

## Offene Folge-Punkte (eigene Runden)
- LLMP-4-Spannung (ein litellm-File frontet mehrere Anbieter mit divergenten Caps) + LLMP-5-Multi-Key/Fallback → Convention-Delta-Runde.
- Cache-Passthrough-Beleg (`cache_control` + `usage.cache_read_input_tokens`) als Golden-Fixture-Pflicht (iOS-/Anbieter-Aktualitäts-Klinge).

## Belege
Ratifiziertes Paket: `brainstorm/berater-runde/20260705-2223-RATIFIZIERT-1316-litellm-rat26.md`. Bezug RAT-20, E-EC-5/E-EC-6, LLMP-2/-4/-5.

Refs #1316 #1315 #1268
