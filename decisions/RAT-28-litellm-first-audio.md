# RAT-28 — LiteLLM-first für Audio: TTS + STT in Scope (LLMP-S6 Umkehr)

**Datum:** 2026-07-24 · **Ratifiziert:** Nic-Verdikt „a" (arbeitstag-prep 2026-07-24) · **Epic:** #1268 · **Ticket:** #1410

## Kontext — warum LLMP-S6 jetzt umgekehrt wird

RAT-20 (2026-06-21) hatte TTS/STT via **LLMP-S6** explizit aus der LLM-Provider-Spec ausgeschlossen. Begründung damals: „eigene Frage mit eigenen Anchors" (Asset-Lifecycle bei hoerspiel, speed-Cache bei kibuddy — keine sinnvolle Abstraktion über tools/llm). Das galt, solange LiteLLM selbst noch kein Thema war.

RAT-26 (2026-07-05) etablierte LiteLLM als Motor unter der Fassade für Chat-Completions. TTS/STT wurden damals nicht adressiert (LLMP-S6-Scope-Ausschluss noch aktiv).

**Nic-Setzung 2026-07-08** (wörtlich): „Was LiteLLM abdeckt, nehmen wir mit; was wir drumherum wirklich nicht über LiteLLM abgedeckt bekommen, bauen wir minimal selbst." LiteLLM deckt TTS via `litellm.speech()` und STT via `litellm.transcription()` ab — damit fällt das LLMP-S6-Ausschluss-Argument weg: es gibt keine Eigenentwicklung mehr zu schützen, nur noch eine Config-Entscheidung (welcher Provider je Modalität).

Die berater-runde #1268 hatte STT mit „NOCH NICHT" empfohlen (thin benefit, Dauer-/Kosten-Präzision nicht erfasst). Dieser Defer ist durch die Doktrin überstimmt: Präzisionsanforderungen an die Audio-Telemetrie hat Nic explizit als „nicht so wichtig" eingestuft.

## Entscheidung

1. **TTS in Scope via `litellm.speech()`** — Provider wird Config-Sache (Azure als Default, ElevenLabs/Groq/OpenAI testbar per LLMP-5-Slot). Kein Provider-Code mehr in kibuddy/eltern-chat direkt.

2. **STT in Scope via `litellm.transcription()`** — berater-runde-1268-Defer „NOCH NICHT" durch Nic-Doktrin aufgehoben. Migrationspfad identisch zu TTS (Config-Swap, kein neuer Code-Kern).

3. **LLMP-S6 umgekehrt:** TTS + STT werden Teil der `specs/platform/llm-providers.md`. Spec-Delta erforderlich: LLMP-S6-Ausschluss-Paragraph entfernen, stattdessen TTS/STT-Absatz mit je einem `litellm.speech()`-/`litellm.transcription()`-Verweis. Nicht-LiteLLM-Anteile (kibuddy-speed-Cache, hoerspiel-Asset-Lifecycle) bleiben in ihren Buddy-Specs — sie wohnen UM den LiteLLM-Call herum, ersetzen ihn aber nicht.

4. **Telemetrie-SSoT bleibt `write_call`** — auch für Audio. ~~LiteLLM-native-Callbacks / `completion_cost()` für Audio-Calls NICHT nutzen~~ **[AMENDIERT 2026-07-30 — kohärent mit RAT-26 §5-Amendment]:** die Kosten-QUELLE ist jetzt auch für Audio LiteLLM-nativ — `tts-1-hd` trägt `input_cost_per_character`, `azure/whisper-1` Kosten pro Sekunde (Live-Probe 2026-07-30). Der frühere „für Audio nicht nutzen"-Ausschluss und der akzeptierte Präzisions-Gap entfallen damit. `write_call` bleibt Schreib-SSoT.

5. **Auto-Fallback weiter deferred** — RAT-26 §4 gilt weiter für Audio. Provider-Wahl je Schnittstelle (LLMP-5-Slot) ist das Modell, kein automatisches Überlaufen.

6. **Bau-Ticket: #1410** — „Audio via LiteLLM (TTS + STT)". Absorbiert #1367 (Telemetrie B: TTS/STT-Wiring, geschlossen 2026-07-08 als in #1410 gefaltet). Reihenfolge: nach #1316-Slot-1 (Singleshot-Slots singleshot, cache-frei zuerst).

## Nicht-Implikationen

- kibuddy-speed-Cache bleibt Custom (technischer Vorteil durch lokale Zwischenspeicherung, nicht durch LiteLLM lösbar).
- hoerspiel-Asset-Lifecycle (Kapitelschnitt, Transkript-Pipeline) bleibt in `specs/buddies/hoerspiel.md` — die Audio-Erzeugung selbst fließt durch LiteLLM, die Datei-Verwaltung drumherum nicht.
- LLMP-S6 wird inhaltlich umgekehrt, nicht gelöscht — der Paragraph bleibt als „jetzt nicht mehr ausgeschlossen, siehe RAT-28" referenzierbar.

## Kill-Kriterium

`litellm.speech()` zeigt Inkompatibilitäten mit Azure-TTS-Parametern, die den kibuddy-speed-Cache oder den hoerspiel-Vorauflösungs-Pfad brechen → betroffener Slot fällt zurück auf direkten Azure-SDK-Call (Hand-Vendor-Segment; erhalten, solange nicht gelöscht). Der Lösch-Schritt (Hand-Vendoren raus) ist die Ein-Wege-Tür — erst nach n=1 grünem Produktions-Lauf.

## Belege

Nic-Setzung 2026-07-08 (Chat-Turn). Berater-runde #1268 (codex_crosscheck, STT-Defer: thin benefit, Dauer-Schätzung). Bezug: RAT-20 (LLMP-S6), RAT-26 (LiteLLM-Motor, §4 Fallback-Defer, §5 Telemetrie-SSoT).

Refs #1410 #1268 #1316
