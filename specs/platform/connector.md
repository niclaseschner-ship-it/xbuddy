# Connector-Übersicht — Spec     (ID-Präfix: CONN)

> Status: V1 · Refs [#1086](../../README.md) (T5, Keystone [RAT-20](../../decisions/RAT-20-llm-gateway-ist-lib.md))
> · Werft-Lauf 2026-06-25 (F1–F4), Scope-Entscheid
> `brainstorm/berater-runde/20260625-1145-RATIFIZIERT-connector-v1-scope.md`
> · Mockup: `specs/mockups/connector/index.html`

Eine **Eltern-PWA-Seite**, die die externe KI-Anbieter-Landschaft einer XBuddy-Instanz
**zeigt**: welche Schnittstellen angebunden sind, was sie kosten, welcher Buddy welche
nutzt. Schreib-Aktionen (Anbieter wechseln, Key anlegen) verweist sie in den
bestehenden Eltern-Chat — die Seite selbst ist in V1 **read-only**.

**Datenquellen:** `var/llm/provider_calls.jsonl` (LLMP-S4, Verbrauch/Kosten) +
`tools/zugangsdaten`-Slot-Inventar (ZD-2, welche Verbindungen).

**Heimat (Gate A 2026-06-25):** Eltern-App-Plus-Seite (PWA), Cookie-Auth AUTH-3
(RAT-18 PWA-First) — **nicht** die fail-open/PUBLIC `seiten/`-Übersicht, weil
Kosten-/Nutzungsdaten gezeigt werden.

**V1-Posture (Berater-Runde 2026-06-25):** Die Seite schreibt in V1 **keine** ZD-Slots
und **keine** Provider-Config über HTTP (`tools/zugangsdaten` ist Lib-kein-HTTP,
`specs/platform/zugangsdaten.md` ZD; API-Key-Wechsel hat den schärferen ONB-11/12-Flow).
HTTP-Secrets-Editor + In-Page-Switch = **V2**, blockiert auf [#948](../../README.md)
(Auth-Klasse für sensible lokale Schreib-Routen — diese Seite ist der erste Treiber) +
nginx-Funnel-deny + Spec-Patch + ggf. [#1030](../../README.md) (Hot-Swap).

## 1. Aufbau — zwei Sektionen als Tabelle

### CONN-1 — Sektion „Schnittstellen & Tokens"
Eine Tabellen-Zeile pro **externer Verbindung** (Vendor-Slot), nicht pro Buddy. Pro
Zeile: Anbieter-Logo + Name, Status, **wer-bucht-darauf** (Chips der nutzenden Buddys),
**Summe abgerechnet** (aggregiert über alle caller dieses Vendors). *Wenn* ein Slot
einen Key trägt, *dann* Status „konfiguriert"; *wenn* nicht genutzt + von keinem aktiven
Pfad referenziert (`hoerspiel-llm-provider-*`), *dann* „inaktiv / Altlast".

### CONN-2 — Sektion „Je Buddy", eine Zeile pro Funktion
Eine Tabellen-Zeile pro **Buddy × Funktion**: eltern-chat (LLM), hoerspiel (LLM **und**
TTS — zwei Zeilen), kibuddy (LLM). Pro Zeile: Buddy-Icon (aus `<buddy>/views.json`),
Funktion, **aktuell genutzt** (Vendor + Modell), Calls/Kosten, Edit-Aktion (CONN-6).

### CONN-3 — TTS als aktive Verbindung, Verbrauch noch nicht erfasst
*Wenn* ein Buddy einen TTS-Dienst nutzt (hoerspiel → Azure OpenAI, `hoerspiel/tts/azure.py`),
*dann* erscheint die Verbindung als **aktiv** in CONN-1 und als eigene Funktions-Zeile in
CONN-2 — aber das Kosten-Feld zeigt **„Telemetrie folgt"** (nicht 0, nicht „—"), weil TTS
außerhalb des `tools/llm`-Telemetrie-Scopes liegt (LLMP-S6). Folge: TTS-Spend-Instrumentierung
(eigenes Ticket).

## 2. Verbrauch & Kosten

### CONN-4 — Aggregation aus JSONL, Tail-Fenster
Die Seite aggregiert `var/llm/provider_calls.jsonl` (LLMP-S4) pro caller × model_id ×
Zeitraum: Summe `est_cost_eur`, Calls, Tokens. *Wenn* ein Modell unbekannten Preis hat
(`est_cost_eur: null`, OPEN-LLMP-A), *dann* zeigt die Kosten-Zelle „—", nicht 0.
**Lese-Disziplin:** die Aggregation liest **nicht** die volle Datei bei jedem Aufruf —
V1 ein Tail-Zeitfenster (z. B. 30 Tage) oder Lazy-Aggregat-Cache; bei abgeschnittenem
Fenster ein „Daten ab <Datum>"-Marker. (Schützt vor OPEN-LLMP-E; Kill-Kriterium:
synthetische 100MB/1GB-JSONL auf dem Pi muss im Latenzbudget bleiben.)

### CONN-5 — 7-Tage-Verlauf pro Zeile
*Wenn* der Elternteil eine Verbindungs- oder Buddy-Zeile antippt, *dann* öffnet sich ein
kleines Diagramm „letzte 7 Tage" (Calls/Kosten pro Tag, aus der tageweisen JSONL-Aggregation).

## 3. Schreib-Aktionen (V1: Verweis, kein HTTP-Schreiben)

### CONN-6 — Edit/Add verweisen in den Eltern-Chat (ehrlich pro Pfad)
*Wenn* eine Schreib-Aktion ausgelöst wird, *dann* öffnet die Seite ein Modal mit der
realen Möglichkeit — **kein** HTTP-Schreiben. Die Realität ist pro Pfad verschieden und
wird ehrlich gezeigt (`anbieter_wechseln` kennt nur eltern-chat):
- **eltern-chat LLM:** Anbieter wechselbar über den Eltern-Chat (`anbieter_wechseln`, ONB-11/12).
- **hoerspiel LLM / kibuddy LLM:** **kein** Self-Service — heute nur Config + Service-Neustart → V2.
- **hoerspiel TTS:** Azure-only, **kein** Anbieterwechsel → V2.
- **Neue Schnittstelle/Key:** über den Eltern-Chat anlegen (ONB-11/12); In-Page-Editor = V2.

### CONN-7 — Kein Geheimnis, kein Slot-Klartext
Die Seite zeigt **nie** einen Key-Wert **und keinen** ZD-Slot-Klartext-Namen (technisches
Rauschen ohne Nutzer-Mehrwert). Nur: Status „konfiguriert/inaktiv" + welche Buddys die
Verbindung nutzen.

## 4. Schnittstelle & Auth

### CONN-8 — Read-only HTTP, Cookie-Auth
Exponiert `GET /api/v1/connector/uebersicht` (read-only, Cookie-Auth AUTH-3). **Kein**
PUT/POST/DELETE in V1. Konsumiert: `provider_calls.jsonl` (lesen) + ZD-Slot-Inventar
(nur Namen-Existenz/Status, **nicht** Werte).

## Familie-3-Probe
Pro Familie variiert allein das **Slot-Inventar** (welche Verbindungen) — Config im
ZD-Store, nicht Code. Die Seite ist generisch über das Inventar, kein Familie-1-Hardcode.

## Mobile-First
Normalfall ist das Handy. Beide Tabellen brechen auf Handy-Breite (≤480px) in gestapelte
Karten um (Label-Wert), Edit-Aktion + Tippen-zum-Diagramm bleiben. Desktop/Tablet behalten
die breite Tabelle. Stil aus `display/_shared/design/tokens.css` (DTOK), Machart an
`specs/mockups/plan-einstellungen/` geerdet.

## Was NICHT V1 (V2 / Folge, mit Trigger)
- **In-Page-Secrets-Editor** (HTTP-Key-Schreiben) → #948 (Auth, priorisiert) + Funnel-deny + Spec-Patch.
- **In-Page-/Live-Provider-Switch** → #948 (Schreib-Auth) bzw. #1030 (Hot-Swap ohne Restart).
- **TTS-Spend-Telemetrie** (Azure-TTS in die Verbrauchs-Sicht) → eigenes Ticket (LLMP-S6-Folge).
- **Cost-Caps / Budget-Alarme.**
- **JSONL-Rotation** (OPEN-LLMP-E).

## Offene Punkte
- OPEN-CONN-B: Live-Health-Ping pro Slot (über „konfiguriert" hinaus) — V1 vertagt.
- OPEN-CONN-D: Tail-Fenster-Größe + Aggregat-Cache-Form — `/arbeitstag` Phase-0-Detail.
