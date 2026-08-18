# Connector-Übersicht — Spec     (ID-Präfix: CONN)

> Status: V1 · Refs [#1086](../../README.md) (T5, Keystone [RAT-20](../../decisions/RAT-20-llm-gateway-ist-lib.md))
> · Werft-Lauf 2026-06-25 (F1–F4), Scope-Entscheid
> `decisions/RAT-51`
> · Mockup: `specs/mockups/connector/index.html`

Eine **Eltern-PWA-Seite**, die die externe KI-Anbieter-Landschaft einer XBuddy-Instanz
**zeigt**: welche Schnittstellen angebunden sind, was sie kosten, welcher Buddy welche
nutzt. Schreib-Aktionen (Anbieter wechseln, Key anlegen) verweist sie in den
bestehenden Eltern-Chat — die Seite selbst ist in V1 **read-only**.

**Datenquellen:** `var/llm/provider_calls.jsonl` (LLMP-S4, Verbrauch/Kosten) +
`tools/zugangsdaten`-Slot-Inventar (ZD-2, welche Verbindungen).

**Heimat (Gate A 2026-06-25):** Eltern-App-Plus-Seite (PWA) unter dem
`seiten/`-Mantel. **V1-Auth = PUBLIC** (auth.md AUTH-6, fail-open), exakt wie
die übrigen `seiten/`-Mini-Apps (plan-einstellungen, einkauf) — **keine** neue
Auth-Klasse. (Nic 2026-06-26: AUTH-3/Cookie-Auth ist ungebaut; bis dahin trägt
der Connector dieselbe PUBLIC-Posture wie die Geschwister-Seiten und härtet
gemeinsam mit ihnen über [#948](../../README.md).)

**V1-Posture (Berater-Runde 2026-06-25):** Die Seite schreibt in V1 **keine** ZD-Slots
und **keine** Provider-Config über HTTP (`tools/zugangsdaten` ist Lib-kein-HTTP,
`specs/platform/zugangsdaten.md` ZD; API-Key-Wechsel hat den schärferen ONB-11/12-Flow).
HTTP-Secrets-Editor + In-Page-Switch = **V2**, blockiert auf [#948](../../README.md)
(Auth-Klasse für sensible lokale Schreib-Routen — diese Seite ist der erste Treiber) +
nginx-Funnel-deny + Spec-Patch + ggf. [#1030](../../README.md) (Hot-Swap).

## 1. Aufbau — drei klare Blöcke (Nordstern #1669)

Die Seite ist in **drei Blöcke in fester Reihenfolge** gegliedert (Nic 2026-07-31,
Ticket #1669 — die frühere „zwei Sektionen als Peer-Tabelle" war „wild zusammengewürfelt",
weil LiteLLM als Peer neben Anthropic/Mistral stand, obwohl es das **Gateway** ist):

```
① GESAMTKOSTEN  (oben, prominent)  → CONN-4 (Summe über alles: 30 Tage + 7 Tage + Daten-ab-Marker)
② WELCHE APP NUTZT WAS             → CONN-2 (pro App aktuelles Modell + Kosten + Wechseln-Affordanz)
③ ANBIETER-STATUS (klein, Fußzeile) → CONN-1 (LiteLLM als Gateway benannt, konfigurierte Keys mit Status)
```

### CONN-1 — Block ③ „Anbieter-Status": LiteLLM als Gateway, darunter die Schlüssel
Der Block nennt **zuerst LiteLLM als gemeinsames Gateway** — alle Apps sprechen über
dieses eine Gateway, die Anbieter darunter sind die **dahinter konfigurierten Schlüssel**,
**keine** getrennten Peer-Zugänge (das war der „macht kein Sinn"-Murks, #1669). Darunter
eine kompakte Liste, **eine Zeile pro externer Verbindung**, gruppiert nach **(Vendor,
Purpose)** — **nicht** allein nach Vendor-Slug und nicht pro Buddy (ENTSCHEID-1262 →
„Patch D", Nic 2026-07-03: „eigene erkennbare Foto-Analyse-Zeile"). Zwei Slots desselben
Vendors mit **unterschiedlichem Purpose** — z. B. `eltern-chat-anthropic-api-key` (Chat) und
`eltern-chat-anthropic-foto-analyse-api-key` (Foto-Analyse) — ergeben **zwei**
unterscheidbare Zeilen; zwei Slots mit gleichem (Vendor, Purpose) über verschiedene caller
bleiben **eine** aggregierte Zeile. Pro Zeile: Anbieter-Logo + Name, ein **menschenlesbares
Zweck-Label** (abgeleitet aus dem Purpose-Sub-Qualifier vor dem Schlüsseltyp-Suffix:
`foto-analyse-api-key` → „Foto-Analyse"; ein Purpose nur aus dem Schlüsseltyp (`api-key`)
→ Default-Label „Chat" — **nie** der ZD-Slot-Klartext, CONN-7), Status, **wer-bucht-darauf**
(Chips der nutzenden Apps). *Wenn* ein Slot einen Key trägt, *dann* Status „konfiguriert";
*wenn* nicht genutzt + von keinem aktiven Pfad referenziert (`hoerspiel-llm-provider-*`),
*dann* „inaktiv / Altlast". Der Block sitzt als **kleine Fußzeile** unter Block ②, nicht als
prominente Peer-Tabelle. Zeilen-Klick öffnet das Detail-Sheet (CONN-6/CONN-7).
Test-Anker: seiten/tests/test_connector_schnittstellen.py::test_conn1_vendor_purpose_zwei_zeilen

### CONN-2 — Block ② „Welche App nutzt was", eine Zeile pro App × Funktion
Eine Zeile pro **App × Funktion**: eltern-chat (LLM-Chat **und**
LLM-Foto-Analyse — zwei Zeilen seit #1262, konsistent zur (Vendor,Purpose)-Route aus
CONN-1), hoerspiel (LLM **und** TTS — zwei Zeilen), kibuddy (LLM). Pro Zeile: App-Icon
(aus `<buddy>/views.json`), Funktion, **aktuell genutzt** (Vendor + Modell), Kosten und
eine **sichtbare `[Wechseln ▸]`-Affordanz** (CONN-6). Zeilen-Klick öffnet den
7-Tage-Verlauf (CONN-5).

### CONN-3 — TTS als aktive Verbindung, Verbrauch noch nicht erfasst
*Wenn* ein Buddy einen TTS-Dienst nutzt (hoerspiel → Azure OpenAI, `hoerspiel/tts/azure.py`),
*dann* erscheint die Verbindung als **aktiv** in CONN-1 und als eigene Funktions-Zeile in
CONN-2 — aber das Kosten-Feld zeigt **„Telemetrie folgt"** (nicht 0, nicht „—"), weil TTS
außerhalb des `tools/llm`-Telemetrie-Scopes liegt (LLMP-S6). Folge: TTS-Spend-Instrumentierung
(eigenes Ticket).

## 2. Verbrauch & Kosten

### CONN-4 — Aggregation aus JSONL, Tail-Fenster + Gesamtsumme prominent (Block ①)
Die Seite aggregiert `var/llm/provider_calls.jsonl` (LLMP-S4) pro caller × model_id ×
Zeitraum: Summe `est_cost_eur`, Calls, Tokens. *Wenn* ein Modell unbekannten Preis hat
(`est_cost_eur: null`, OPEN-LLMP-A), *dann* zeigt die Kosten-Zelle „—", nicht 0.
**Block ① (Nordstern #1669):** die **Gesamtsumme über alle Apps** steht **ganz oben,
prominent** — nicht mehr im `tfoot` der App-Tabelle. Sie zeigt zwei Fenster
(z. B. „letzte 30 Tage" + „letzte 7 Tage") plus den „Daten ab <Datum>"-Marker. Die
7-Tage-Summe wird aus den ohnehin gerechneten Tages-Serien der App-Zeilen (CONN-5)
gebildet — **kein** zusätzlicher Telemetrie-Lesevorgang.
**Lese-Disziplin:** die Aggregation liest **nicht** die volle Datei bei jedem Aufruf —
V1 ein Tail-Zeitfenster (z. B. 30 Tage) oder Lazy-Aggregat-Cache; bei abgeschnittenem
Fenster ein „Daten ab <Datum>"-Marker. (Schützt vor OPEN-LLMP-E; Kill-Kriterium:
synthetische 100MB/1GB-JSONL auf dem Pi muss im Latenzbudget bleiben.)

### CONN-5 — 7-Tage-Verlauf pro Zeile
*Wenn* der Elternteil eine Verbindungs- oder Buddy-Zeile antippt, *dann* öffnet sich ein
kleines Diagramm „letzte 7 Tage" (Calls/Kosten pro Tag, aus der tageweisen JSONL-Aggregation).

## 3. Schreib-Aktionen (V1: Verweis, kein HTTP-Schreiben)

### CONN-6 — Wechseln-Affordanz verweist in den Eltern-Chat (ehrlich pro Pfad)
Jede App-Zeile in Block ② trägt eine **sichtbare `[Wechseln ▸]`-Affordanz** — der
Provider-Wechsel ist damit als **Möglichkeit sichtbar** (Nordstern #1669: „Provider
wechseln, z. B. eltern-chat Claude→Mistral"), auch wenn er in V1 **technisch noch
inaktiv** ist. *Wenn* die Affordanz ausgelöst wird, *dann* öffnet die Seite ein Sheet mit
der realen Möglichkeit — **kein** HTTP-Schreiben, **keine** funktionierende Wechsel-Mechanik,
nur die ehrliche Ansage „läuft über den Eltern-Chat / kommt in V2". Die Realität ist pro
Pfad verschieden und wird ehrlich gezeigt (`anbieter_wechseln` kennt nur eltern-chat):
- **eltern-chat LLM:** Anbieter wechselbar über den Eltern-Chat (`anbieter_wechseln`, ONB-11/12).
- **hoerspiel LLM / kibuddy LLM:** **kein** Self-Service — heute nur Config + Service-Neustart → V2.
- **hoerspiel TTS:** Azure-only, **kein** Anbieterwechsel → V2.
- **Neue Schnittstelle/Key:** über den Eltern-Chat anlegen (ONB-11/12); In-Page-Editor = V2.

### CONN-7 — Kein Geheimnis, kein Slot-Klartext
Die Seite zeigt **nie** einen Key-Wert **und keinen** ZD-Slot-Klartext-Namen (technisches
Rauschen ohne Nutzer-Mehrwert). Nur: Status „konfiguriert/inaktiv" + welche Buddys die
Verbindung nutzen.

## 4. Schnittstelle & Auth

### CONN-8 — Read-only HTTP, PUBLIC (AUTH-6), server-gerendert
Exponiert unter dem bestehenden nginx-`^~ /api/v1/seiten/`-Block (keine
nginx-Änderung; ein `/seiten/connector/`-Block existiert **nicht**):
- `GET /api/v1/seiten/connector/` — PWA-HTML-Shell, die das **read-only
  Aggregat server-rendert** (Track A + ZD-Inventar als JSON-Blob in die Seite;
  das JS rendert beide Tabellen + 7-Tage-Charts daraus).
- `GET /api/v1/seiten/static/connector/<datei>` — PWA-Mantel (manifest.json,
  sw.js, style.css, logos/*), via Flask-static.

**Kein** separater `/uebersicht`-Sub-Endpunkt und **kein** Asset-Sub-Pfad unter
`/api/v1/seiten/connector/`: der Manifest⇔Route-Eigentest (SREG-12,
`seiten/tests/test_views_manifest_eigentest.py`) verlangt, dass jede
`/api/v1/seiten/<sub>`-Rule ein **gelisteter View** ist — ein Daten- oder
Asset-Endpunkt wäre ein Nicht-View und würde die Eltern-Übersicht verschmutzen.
Darum trägt der Connector genau **eine** Rule (die HTML-Shell, als PWA-View in
`seiten/views.json` gelistet, SREG-15), und die Daten reisen **eingebettet**
mit. *(Wenn der Eigentest später einen Daten-Sub-Pfad zulässt, kann V2 auf eine
fetch-/PWA-First-Variante mit eigenem `…/uebersicht`-Endpunkt umstellen.)*

**Kein** PUT/POST/DELETE in V1. Konsumiert: `provider_calls.jsonl` (lesen, via
`tools.llm.telemetry_read`) + ZD-Slot-Inventar (nur Anzahl/Status, **nicht**
Namen, **nicht** Werte — CONN-7).

**Auth = PUBLIC (auth.md AUTH-6, fail-open)**, wie plan-einstellungen/einkauf —
**nicht** Cookie-Auth AUTH-3 (Nic 2026-06-26: AUTH-3 ungebaut; härtet mit
[#948](../../README.md)). Die ältere Fassung (`GET /api/v1/connector/uebersicht`,
Cookie-Auth) war deploy-inkompatibel (eigener nginx-Block) und ist ersetzt.

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
