# RAT-31 — Abriss der Mehr-Geräte-Routing-Wirbelsäule: ein Gerät für immer, Wirbelsäule stirbt

**Datum:** 2026-07-27 · **Ratifiziert:** Nic-Setzung 2026-07-27 (Nic-Go „Boote verbrennen") · **Refs:** #1339 (Epic), #1494–#1499, #1469, #1470, #1400 · **Supersedes:** RAT-29 (Kill-Kriterium) · **Extends:** RAT-29, RAT-27

> Ledger/Herleitung: `brainstorm/berater-runde/20260727-144443-RATIFIZIERT-wirbelsaeule-abriss.md` (Berater-Runde: MACH ES, Antiberater = Opus-Fallback wegen Codex-Limit bis 2026-08-26).

## Kontext — warum die Wirbelsäule stirbt, nicht nur der Default

RAT-29 (2026-07-24) stellte den **Default** um: ein Gerät (Heim-Shell) reicht, der Zwei-Geräte-Default entfällt — behielt aber die Multi-Geräte-Maschinerie **bewusst** als Fallback (Kill-Kriterium Zeile 50: „klassisches Zwei-Geräte-Modell bleibt parallel nutzbar").

**Nic-Setzung 2026-07-27** (wissend): Für die erste Veröffentlichung ist das Setup **fest ein Chat + ein Gerät (Heim-Shell PWA), für immer ein Gerät**. Die Multi-Geräte-Routing-**Wirbelsäule wird physisch abgerissen** — nicht dormant gehalten. Damit **erlischt RAT-29s Kill-Kriterium** (es gibt keinen Zwei-Geräte-Rückfall mehr; das ist der wissend akzeptierte Preis). Die Familie-3-/Zweitschirm-Achse ist bewusst geschlossen.

## Kern-Prinzip

Die Multi-Geräte-**Wirbelsäule** (Fanout, Geräte-Bindung, Tracking) stirbt. Drei **nutzer-sichtbare Konzepte** überleben, same-origin in `seiten/`/Shell umgezogen — **keine App, keine Funktion, kein Editor geht verloren** (RAT-29 „alle Apps bleiben" gilt weiter):

1. **Geräte-Einrichten** — `geraet_anlegen` bleibt, eingedampft auf Binär `{Kind|Eltern}` → Pairing-Link. Kind → `/shell/<panel_id>`, Eltern → Cookie + Mini-App-Übersicht. Registry-Tracking + `paired_at` sterben (Cookie-Revoke war ohnehin nur Alles-oder-nichts via Bot-Token-Rotation).
2. **Kachel-Kuratierung** — panel `tiles` + `config` + `panel_id` + PBE-4-Editor (#1400) bleiben (Nic: „einzelne Funktionen ausblenden"). Nur `display_id`-Bindung + `router_url` + Router-Proxy (PREG-7/PREG-9) sterben.
3. **Live-Refresh** — same-device SSE erbt den Push (`router/main.py:52-183`-Kern verpflanzt); der display_id-Fanout stirbt.

## Entscheidung

### 1. Heim-Shell wird self-contained
Linke Panel-Nav + rechtes Buddy-Pane + Tile-Tap-Ingest + Live-Refresh laufen **alle same-origin über `seiten/`**. Kein router-Fanout, keine ROU-32-`panel_id→display_id`-Indirektion (ein Gerät = ein Ziel). `heim-shell.md` SHELL-1..11 wird entsprechend umgeschrieben.

### 2. Was stirbt / was bleibt
- **Stirbt:** `geraete/`-Registry, `display/` + `display-client/` (Fremdgerät-Renderer), `router/` (Fanout-Dienst), panel-`display_id`/`router_url`-Bindung + Router-Proxy. Die vier eltern-chat-Skills `panel_anlegen`, `cookie_nachschicken`, `ca-verteilung` (+ `geraet_anlegen` eingedampft, nicht gelöscht).
- **Bleibt / re-home same-origin:** Shell, tiles+Editor (#1400), `controller/app-panel`-Assets (linke Nav), alle Buddy-Views, Pairing/Cookie/Kind-Eltern-Redirect, Mini-App-Übersicht (Quelle → Buddy-Manifeste statt Registries). Der HMAC-Cookie-Auth-Pfad (`tools/initdata/auth_gate.py`) ist von `geraete/` **entkoppelt** — bleibt.
- **Offen (Etappe 6):** `controller/figuren-erkennung/` — Live-Feature (bleibt, re-home) oder Spike (stirbt)? Nicht blind löschen.

### 3. Abriss in 8 main-grün-gegateten Etappen (Epic #1339)
0. Spec-Fundament (diese Datei + `heim-shell.md` self-contained + `seiten-registry.md` Ein-Gerät) — #1494
1. Blätter kappen + `geraet_anlegen` eindampfen — #1470
2. **KRITISCH:** SSE-Erbe same-device (2a Pane, 2b Nav+Tile-Tap) + Pre-Merge-Smoke — #1495
3. Aggregator/Übersicht auf Buddy-Manifeste — #1496
4. `/auth/pair` Kind/Eltern aus Pairing-Token statt geraete.json — #1469 (kreuzt #1338)
5. Test-Kreuzungen entschärfen — #1497
6. Wirbelsäule löschen/eindampfen (panel #1400 bleibt) — #1498
7. Specs archivieren + tote Referenzen — #1499

### 4. Kritischer Pfad + Kill-Kriterium
Etappe 2 (SSE-Erbe same-device) muss **grün bewiesen** sein (Pre-Merge-Smoke: Tap-links → Refresh-rechts ohne router), BEVOR Etappe 6 den Router löscht. Lässt sich 2b (Tile-Tap-Ingest) nicht ohne `panel/` bauen → Abriss stoppt bei Etappe 5, `router/` wird auf einen minimalen **Ein-Gerät-Event-Kern eingedampft** statt gelöscht. Bis Etappe 6 ist alles reversibel; jede Löschung ein eigener PR, lokal `pytest`-gegatet (Pi-Runner-Bottleneck).

## Nicht-Implikationen
- **Alle Apps bleiben** — essen-einkauf, plan, hoerspiel, connector, routine etc. unverändert als Buddy-Views. Kein „App X abbauen".
- **Panel-Editor bleibt** — Kachel-Kuratierung (#1400) überlebt re-homed; nur die Geräte-Bindung stirbt.
- **Auth-Modell** — RAT-27 gilt weiter (EIN Cookie, Dual-Gate); der Kind/Eltern-Redirect wandert in den Pairing-Token.

## Kill-Kriterium (Gesamt)
Siehe §4 — der einzige technische Stopp-Punkt ist ein nicht ohne `panel/` verpflanzbarer Tile-Tap-Ingest (Etappe 2b); dann router-Kern eindampfen statt löschen. Ein UX-Rückfall auf das Zwei-Geräte-Modell (RAT-29-Kill) existiert **nicht mehr** — bewusst aufgehoben.

## Belege
Nic-Setzung 2026-07-27 (Chat: „ein Chat + ein Gerät … für immer ein Gerät", „Boote verbrennen"). Berater-Runde-Ledger `brainstorm/berater-runde/20260727-144443-RATIFIZIERT-wirbelsaeule-abriss.md`. R1-Bestandskarte (SSE-Erbe `router/main.py:769`/`:725`/`:52-183`; Nicht-Multi-Device-Konsumenten `seiten/main.py:214-231`/`:816`; Auth-Entkopplung `tools/initdata/auth_gate.py:57-63`). Antiberater-Befund (Test-Kreuzungen `tools/tests/test_service_diagnostics.py:60`, `seiten/aggregator.py:104-142`). Panel-Modell (`specs/platform/panel-registry.md:83` tiles=änderbar). RAT-29 Kill-Kriterium (`decisions/RAT-29-heim-shell-ziel-default.md:48-50`).

Refs #1339 #1494 #1495 #1496 #1497 #1498 #1499 #1469 #1470 #1400 #1338
