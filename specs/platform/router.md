# Router — Spec     (ID-Präfix: ROU)

> Status: V1-Kern · Refs #5

Der Router ist die Routing-Logik des Hubs: er nimmt Events von Controllern
entgegen, übersetzt sie in einem **controller-typ-spezifischen Adapter** in
ein kanonisches internes Modell, löst sie im **Routing-Kern** über eine
M:N-Tabelle auf Display-Targets auf und hält den aktuellen Zustand pro
Display in-memory. Display-Komponenten holen den Zustand per HTTP-GET.

**V1-Scope:** Ein Phone-Controller (Spec siehe
[`figuren-erkennung.md`](figuren-erkennung.md)), ein Default-Display,
Bucket-Wechsel als zentrale Aktion. M:N ist als Tabellen-Form angelegt,
die V1-Tabelle hat genau einen Eintrag.

**Out-of-Scope:** MQTT-Transport, persistente Routing-DB (SQLite),
Display-Renderer selbst, AuthN/AuthZ, weitere Controller-Adapter (NFC,
Telegram, Scheduler), Persistierung über Restart, parallele Multi-Display-
oder Multi-Controller-Setups über den V1-Eintrag hinaus. Jeder Baustein
bekommt ein eigenes Ticket sobald er gebraucht wird.

## 1. Architektur

### ROU-1 — Trennung Adapter ↔ Routing-Kern
Im Code leben zwei klar getrennte Verantwortungen:

- **Adapter** (controller-typ-spezifisch): kennt das Roh-Event-Schema
  einer Controller-Familie und übersetzt es in das kanonische interne
  Modell (siehe ROU-2). Pro Controller-Typ ein Adapter; V1 hat genau
  einen — den Phone-Adapter (ROU-6).
- **Routing-Kern**: kennt **nur** das kanonische Modell, kein
  Controller-spezifisches Wissen. Löst Triggern Display-Targets zu und
  hält State.

Abhängigkeitsrichtung: Adapter → Routing-Kern. Der Kern kennt keinen
Adapter.

*Tickets:* #5

### ROU-2 — Kanonisches Trigger-Modell
Ein Trigger ist ein Tupel:

```
{ source_id: <string>, descriptor: <object> }
```

`source_id` ist die Controller-Instanz (siehe FIG-10). `descriptor` ist
controller-typ-spezifisch, aber ein Objekt mit Strings/Zahlen als
Felder. **Phone V1:** `descriptor = { figure_id, bucket }`. Andere
Controller-Typen können andere Descriptor-Schlüssel haben (zukünftig
z. B. NFC: `{ tag_uid }`).

Der Kern behandelt `descriptor` als opaken Schlüssel und vergleicht ihn
gegen Einträge der Routing-Tabelle (ROU-9) per Feld-Gleichheit.

*Tickets:* #5

## 2. HTTP-Eingang

### ROU-3 — POST /api/v1/events
Generischer Eingang: `POST /api/v1/events` mit JSON-Body. Pfad folgt der
URL-Konvention (URL-4: Backend unter `/api/v1/`, Collection im Plural).
Pflichtfelder auf allen Events: `source_id` (`string`), `type`
(`string`). Weitere Felder sind event-spezifisch und werden vom Adapter
validiert.

Phone V1 unterstützt die drei Event-Typen aus FIG-10
(`figure_detected`, `angle_update`, `session_ended`). Neue Event-Typen
sind reine Erweiterung des Adapters — keine Änderung am Kern.

*Tickets:* #5, #24

### ROU-4 — Antwortverhalten
- **2xx** wenn Event akzeptiert und verarbeitet (auch wenn unbekannter
  Trigger — siehe ROU-11).
- **4xx** bei Schema-Verletzung (fehlende Pflichtfelder, unbekannter
  Event-Typ für die `source_id`, falsche Feld-Typen).
- **Kein 5xx im Normalpfad.** Interne Fehler werden geloggt; 5xx nur
  bei unerwartetem Server-Defekt.

*Tickets:* #5

### ROU-5 — Schema-Validierung
Bei Schema-Verletzung liefert der Router 4xx mit JSON-Body
`{ "error": "<kurze Beschreibung>" }`. Beschreibung nennt das fehlende
oder fehlerhafte Feld so genau wie nötig, damit Sender den Fehler
adressieren können.

*Tickets:* #5

## 3. Phone-Adapter

### ROU-6 — 1:1-Mapping ohne Quantisierung
Der Phone-Adapter mappt das Phone-Event direkt auf das kanonische
Modell — **keine eigene Logik, keine Quantisierung, keine Hysterese**.
Diese Verantwortung liegt nach E-FIG-7 in der Phone-Seite, nicht im
Router (siehe auch FIG-20/21 in `figuren-erkennung.md`).

Konkret:

| Phone-Event (FIG-10) | Kanonischer Trigger (ROU-2) |
|---|---|
| `figure_detected { figure_id, bucket }` | `{ source_id, descriptor: { figure_id, bucket } }` |
| `angle_update { figure_id, bucket }` | `{ source_id, descriptor: { figure_id, bucket } }` |
| `session_ended { figure_id }` | Session-Ende-Signal: setzt State auf `null` (siehe ROU-11) |

`angle` aus dem Phone-Event wird V1 nicht weiterverarbeitet — der
Bucket trägt die für den Routing-Lookup relevante Information. `angle`
darf für Diagnose geloggt werden, fließt aber nicht in den State.

*Tickets:* #5

### ROU-7 / ROU-8 — entfallen
Reserviert in der ursprünglichen Aufschneidung für Router-seitige
Quantisierung und Hysterese. Beide entfallen, weil die Logik mit
E-FIG-7 / Ticket #11 in die Phone-Seite gewandert ist. IDs werden
nicht neu vergeben (siehe `specs/README.md`).

## 4. Routing-Kern

### ROU-9 — M:N-Lookup-Tabelle
Die Routing-Tabelle ist eine Liste von Einträgen. Jeder Eintrag
schlüsselt:

```
key   = (source_id, descriptor)
value = (display_ids: [<string>], payload: <object>)
```

Datenhaltung: als JSON-Datei `routing.json` (siehe ROU-18). V1 enthält
genau einen Demo-Eintrag; die Tabellenform ist aber bereits M:N-tauglich
— ein Trigger kann mehrere Displays treffen, ein Display kann von
mehreren Triggern bedient werden.

Vergleich: ein eingehender Trigger wird mit Feld-Gleichheit gegen die
Einträge gematcht. Erster Match gewinnt — die V1-Tabelle ist klein
genug, dass Reihenfolge bewusst gewählt werden kann.

*Tickets:* #5, #24

### ROU-10 — In-Memory State pro Display
Der Router hält pro `display_id` einen State:

```json
{ "source_id": "<string>",
  "descriptor": { ... },
  "payload":   { ... },
  "since":     "<iso8601>" }
```

oder `null`, wenn kein Trigger aktiv ist.

State lebt im Prozess-Speicher; **kein** Persistieren über Restart in
V1.

*Tickets:* #5, #24

### ROU-11 — Lebenszyklus eines States
- **Trigger eingegangen, Match in der Tabelle:** Für jedes Display aus
  `display_ids` des Match-Eintrags wird der State gesetzt oder
  aktualisiert (Felder `source_id`, `descriptor`, `payload`, `since`).
  `since` ist der Zeitpunkt, an dem der **aktuelle Trigger** zuletzt
  eingegangen ist (jedes neue Event mit gleichem Trigger aktualisiert
  `since`).
- **Trigger eingegangen, kein Match:** Event wird akzeptiert (2xx)
  aber **kein** State wird aktualisiert. Eine Warnung wird geloggt
  (`logging.warning`), damit unbekannte Trigger im Betrieb sichtbar
  sind. Begründung: ohne Match weiß der Router nicht, welches Display
  betroffen wäre — eine breite Belegung aller Displays würde
  unbeteiligte Displays löschen, was schlechter ist als der bestehende
  State zu halten.
- **Session-Ende-Signal:** Alle Displays, deren aktueller State diese
  `source_id` trägt, werden auf `null` gesetzt.

Mehrere Trigger auf dasselbe Display (M:N): jeder neue Trigger
überschreibt den State für dieses Display. V1 hat nur einen
Phone-Controller — Multi-Source-Konflikte sind nicht modelliert.

*Tickets:* #5, #24

## 5. HTTP-Ausgang

### ROU-12 — GET /api/v1/displays/&lt;id&gt;/state
Liefert den aktuellen State des angegebenen Displays als JSON. Pfad
folgt der URL-Konvention (URL-4: `/api/v1/`, Collection `displays` im
Plural, `state` als singuläres Aggregat).

- **Bekannte** `<id>` mit aktivem State: 200, JSON-Objekt wie in ROU-10.
- **Bekannte** `<id>` ohne aktiven State: 200, JSON `null`.
- **Unbekannte** `<id>`: 404, JSON `{ "error": "unknown display" }`.

„Bekannt" heißt: in mindestens einem `display_ids`-Feld der
Routing-Tabelle (ROU-9) referenziert. Bei fehlender oder leerer
`routing.json` (siehe ROU-18) ist damit kein Display bekannt — jede
Anfrage liefert 404. Das ist gewollt: ein Dev der den Router ohne
Tabelle startet sieht sofort, dass nichts geroutet wird, statt
stumm `null` zu bekommen.

V1: gängiger Wert für `<id>` ist `default`.

*Tickets:* #5, #24

### ROU-13 — Display-Payload-Schema
`payload` ist ein **JSON-Objekt**, nie ein bloßer String. V1-Minimum:

```json
{ "url": "<string>" }
```

Spätere Felder (`app`, `scene`, `theme`, …) sind reine Erweiterung
ohne Breaking Change.

*Tickets:* #5

### ROU-14 — GET /api/v1/diag
Liefert eine minimale HTML-Debug-Seite, die alle bekannten Displays und
deren aktuellen State live anzeigt. Wird mit JS-Polling (1 Hz)
aktualisiert. Reines Debug-Werkzeug — kein Ersatz für ein Display.
Pfad unter `/api/v1/` (URL-4) — Diagnose zählt zum Hub-Backend.

*Tickets:* #5, #24

### ROU-20 — GET /display/&lt;id&gt; — Auslieferung des Display-Clients
`GET /display/<id>` liefert den Display-Client (siehe
[`display-client.md`](display-client.md)). Der Router ist hier nur
Auslieferungsstelle (E-DC-3); Verhalten und Eigenschaften des Clients
legt `display-client.md` fest. Die `<id>` aus dem Pfad ist die
Identität, mit der der Client arbeitet (DC-1).

Der Endpunkt liefert den Client **unabhängig davon, ob die `<id>` dem
Router bekannt ist** — ob ein Display existiert, klärt der Client beim
Verbinden mit seinem Zustands-Stream (ROU-22); bei unbekannter `<id>`
zeigt er einen Einrichtungs-Hinweis (DC-8). So wird eine fehlerhafte
Einrichtung am Gerät selbst sichtbar, statt mit einer nackten
404-Antwort zu enden.

Der Pfad sitzt unter dem erlaubten `/display/`-Prefix (URL-1), weicht
aber bewusst von der `/display/<buddy>/<view>`-Form (URL-2) ab: er
adressiert ein Display über seine `id`, nicht über Buddy/View.
Dokumentierte Abweichung.

*Tickets:* #5, #24, #30

### ROU-21 — Direkt-Push an Display via CDP

> **Abgelöst (#30).** Die Display-Benachrichtigung läuft über den
> SSE-Zustands-Stream **ROU-22** — er erreicht auch Display-Geräte, die
> nicht am Pi hängen (Tablets); CDP erreicht nur lokales Chromium.
> Begründung: E-DC-1 in [`display-client.md`](display-client.md). Der
> CDP-Push-Code samt der Konfigurationswerte `cdp_target` und
> `cdp_idle_url` (ROU-15) wird in einem separaten PR entfernt
> (CLAUDE.md §6, Entfernen in zwei Schritten). Bis dahin bleibt das
> bestehende Verhalten beschrieben.

Wenn `cdp_target` (siehe ROU-15) gesetzt ist, ruft der Router bei
**jeder State-Änderung** Chromium über das **Chrome DevTools Protocol**
auf, um sofort auf die neue URL zu navigieren — kein Polling-Lag, kein
Iframe-Hop. Mechanik:

1. `GET <cdp_target>/json` — liefert die Liste offener Tabs samt
   `webSocketDebuggerUrl`.
2. WebSocket-Verbindung zum ersten Tab.
3. Senden von `{ "id": <n>, "method": "Page.navigate", "params": { "url": "<ziel>" } }`.

**Push-Trigger:**

- Trigger mit Match (ROU-11): push auf `payload.url`.
- Session-Ende (ROU-11): push auf `cdp_idle_url` (Default `about:blank`).
- Trigger ohne Match: kein Push (State ändert sich nicht).

**Fehlerverhalten:** Der Push läuft **nicht-blockierend** (Thread oder
Async). Verbindungs- oder Protokoll-Fehler werden mit
`logging.warning` protokolliert; `POST /api/v1/events` bleibt 204 und schnell.

**Wenn `cdp_target` leer ist:** Feature ist inaktiv. Der Router pollt-
nur wie zuvor; das ist der Default und das Verhalten des V1-Tests
ohne Pi-Kiosk.

**Warum direkt, nicht per Adapter-Schicht:** V1 hat genau einen
Output-Typ (lokales Chromium). Eine generalisierte
„Output-Adapter"-Abstraktion wäre Antizipation ohne konkreten zweiten
Output. Sobald ein zweiter Push-Pfad dazukommt (etwa MQTT, siehe
E-ROU-2), wird das Generalisieren mit Belegen entschieden — nicht
auf Vorrat (CLAUDE.md §6).

*Tickets:* #17

### ROU-23 — GET /controller/&lt;asset&gt; — Auslieferung der Controller-PWA
`GET /controller/` und `GET /controller/<asset>` liefern die Controller-PWA
(siehe [`figuren-erkennung.md`](figuren-erkennung.md)) unter dem
`/controller/`-Prefix aus URL-1 aus. Der Router ist hier nur
Auslieferungsstelle der Statik; Verhalten und Eigenschaften der PWA legt
`figuren-erkennung.md` fest.

Anders als der Display-Client (ROU-20, eine inline gezogene Seite) ist
der Controller eine echte PWA — `sw.js`, `manifest.json` und Icons müssen
als **eigene Pfade mit ihrem korrekten Content-Type** ankommen, sonst
verweigert der Browser Service-Worker-Registrierung oder Manifest-Parse.
Acceptance-Kriterien:

| Pfad | Antwort |
|---|---|
| `GET /controller/` | 200, `text/html`, Inhalt aus `index.html` |
| `GET /controller/sw.js` | 200, `application/javascript` |
| `GET /controller/manifest.json` | 200, `application/manifest+json` |
| `GET /controller/icon-192.png` | 200, `image/png` |
| `GET /controller/icon-512.png` | 200, `image/png` |
| `GET /controller/icon-maskable-512.png` | 200, `image/png` |
| `GET /controller/figlib.js` | 200, `application/javascript` |
| Pfad außerhalb des Controller-Wurzelverzeichnisses (Path-Traversal, z. B. `/controller/../router/main.py`) | 404 |
| Nicht existierendes Asset im Controller-Verzeichnis | 404 |

Das Wurzelverzeichnis ist konfigurierbar (`controller_dir`, ROU-15).
Defaults zeigen auf `controller/figuren-erkennung/` neben dem Router-Code.
Anfragen, die auflöst aus diesem Wurzelverzeichnis ausbrechen würden,
liefern 404 — kein Dateizugriff jenseits der Wurzel.

*Tickets:* #71

### ROU-22 — GET /api/v1/displays/&lt;id&gt;/events — Zustands-Stream
Liefert einen Server-Sent-Events-Stream für ein Display. Beim Verbinden
sendet der Router den aktuellen Zustand des Displays (Format wie ROU-10)
als erstes Ereignis; bei jeder folgenden Zustandsänderung (ROU-11) ein
weiteres Ereignis mit dem neuen Zustand. So erfährt ein Display-Client
([`display-client.md`](display-client.md)) Inhaltswechsel ohne Polling
und ohne Iframe-Hop.

- Bekannte `<id>`: 200, SSE-Stream (`Content-Type: text/event-stream`).
- Unbekannte `<id>`: 404, JSON `{ "error": "unknown display" }`
  (gleiche Definition wie ROU-12).

Der Pfad sitzt unter `/api/v1/` (URL-4), Collection `displays` im
Plural. Bricht die Verbindung ab, baut der Client sie selbsttätig
wieder auf (`display-client.md` DC-7); der Router hält keinen Zustand
über die Verbindung hinaus.

> Hinweis (Deployment): Hinter einem Reverse-Proxy darf dieser
> Long-Lived-Stream nicht gepuffert werden, sonst erreichen die
> Ereignisse den Client nie. Die HTTPS-Origin schaltet das Puffern
> für diesen Pfad ab (`deploy/nginx/xbuddy-origin.conf`, #70).

*Tickets:* #30

## 6. Konfiguration

### ROU-15 — Tuning-Werte (analog FIG-17)
Defaults stehen als Konstanten im Code. Sie können per
`config.json` im Router-Verzeichnis (siehe ROU-19) oder per
ENV-Variable / CLI-Flag überschrieben werden. Priorität:
**ENV/CLI > config.json > Defaults**.

| Parameter      | Default       | Override                                     |
|----------------|---------------|----------------------------------------------|
| `listen_host`  | `127.0.0.1`   | ENV `ROUTER_HOST` · CLI `--host` · config    |
| `listen_port`  | `5000`        | ENV `ROUTER_PORT` · CLI `--port` · config    |
| `log_level`    | `INFO`        | ENV `ROUTER_LOG_LEVEL` · CLI `--log-level`   |
| `cdp_target`   | `""` (aus)    | ENV `ROUTER_CDP_TARGET` · config             |
| `cdp_idle_url` | `about:blank` | ENV `ROUTER_CDP_IDLE_URL` · config           |
| `controller_dir` | `../controller/figuren-erkennung` (relativ zum Router-Code) | ENV `ROUTER_CONTROLLER_DIR` · CLI `--controller-dir` · config |

Werte, die nur als Code-Konstante existieren — ohne Override-Pfad —
sind Spec-Verletzung (CLAUDE.md §6 Daten vs. Code).

*Tickets:* #5

### ROU-16 — Lokaler Start
Der Router startet lokal per einem dokumentierten Kommando (siehe
README im Router-Verzeichnis, wird im Impl-PR angelegt). Kein
Daemon-/systemd-Setup im V1-Scope, kein Container.

Hör auf `listen_host:listen_port` (ROU-15).

*Tickets:* #5

### ROU-18 — Routing-Tabelle via `routing.json`
Die M:N-Tabelle (ROU-9) lebt als JSON-Datei `routing.json` neben dem
Router-Code (analog FIG-23 für die Phone-Seite). Format:

```json
{
  "entries": [
    {
      "source_id": "phone:test-1",
      "descriptor": { "figure_id": "gelbes-e", "bucket": 0 },
      "display_ids": ["default"],
      "payload": { "url": "https://buddy.local/scene/gelbes-e-0" }
    }
  ]
}
```

- **Fehlerfälle:** Datei fehlt oder nicht parsebar → der Router startet
  mit leerer Tabelle und protokolliert eine Warnung. Ein laufender
  Router darf nicht crashen, weil die Datei fehlt — das macht ihn auch
  als Entwicklungs-Werkzeug brauchbar, das man ohne fertige Tabelle
  hochfährt.
- **Selbsttragend:** Datei liegt im Router-Verzeichnis und wird mit
  ausgeliefert. Pro Instanz separat verwaltet — `routing.json` ist per
  `.gitignore` aus dem Repo ausgeschlossen, `routing.example.json`
  dokumentiert das Format.
- **Reload:** V1 lädt die Datei beim Start. Hot-Reload kommt mit einem
  eigenen Ticket, sobald jemand sie regelmäßig anfasst.

*Tickets:* #5, #24

### ROU-19 — `config.json` für Tuning-Werte
Analog FIG-23: optionale Datei `config.json` im Router-Verzeichnis,
deren Werte die Code-Defaults überschreiben. Felder gemäß ROU-15. Datei
ist optional; Fehler beim Laden fällt stumm auf Defaults zurück und
protokolliert `console.warn`-Äquivalent (Python: `logging.warning`).

*Tickets:* #5

## 7. Tests

### ROU-17 — Automatisierte Tests pro Requirement
Jede Requirement-ID, die Code-Verhalten beschreibt, hat einen
automatisierten Test (CLAUDE.md §6). V1: `pytest` mit dem
Flask-Testclient — reproduzierbar ohne Phone.

Mindest-Abdeckung:

- ROU-3 — POST /api/v1/events akzeptiert ein gültiges Phone-Event.
- ROU-4/ROU-5 — fehlende Pflichtfelder ergeben 4xx mit
  Fehler-Beschreibung.
- ROU-6 — Phone-Event wird 1:1 auf den kanonischen Trigger gemappt
  (keine Quantisierung).
- ROU-9/ROU-11 — Trigger mit Match setzt State; ohne Match bleibt der
  State unverändert.
- ROU-11 — `session_ended` setzt State auf `null`.
- ROU-12/ROU-13 — `GET /api/v1/displays/default/state` liefert das
  aktuelle Payload-Objekt; unbekannte `<id>` liefert 404.
- ROU-18 — fehlendes `routing.json` startet den Router mit leerer
  Tabelle; jeder `GET /api/v1/displays/<id>/state` liefert dann 404.
- ROU-23 — `/controller/` liefert die PWA-Statik mit korrekten
  Content-Types; Path-Traversal-Anfragen werden mit 404 abgewiesen.

*Tickets:* #5, #24

---

## Offene Punkte

- **OPEN-ROU-B** — Wo lebt die Routing-Tabelle langfristig? V1 als
  JSON-Datei (ROU-18); V2 als Routing-DB (SQLite) gemäß
  brainstorm-Architektur; V3 ggf. zentraler Figuren-Registry-Service
  (vgl. OPEN-FIG-B). Keine V1-Entscheidung nötig — Kontext für
  Folge-Tickets.

---

## Entscheidungen

Architektur-Entscheidungen aus der Konzept-Session (Chat 2026-05-20),
festgehalten an der Spec, weil sie nicht aus dem Code ableitbar sind
und für Folge-Tickets load-bearing bleiben.

### E-ROU-1 — Adapter/Routing-Kern-Trennung von Anfang an
*Datum:* 2026-05-20

Frühe Variante: ein einziger Endpoint, der das Phone-Event direkt in
State umsetzt. **Verworfen**, weil ein zweiter Controller-Typ
(NFC/Telegram) im einzigen Endpoint zwei Schema-Validierungen
parallel halten müsste — der Kern würde Controller-Wissen ansammeln.

Stattdessen: Adapter pro Controller-Typ, Kern nur über kanonisches
Modell. Kostet V1 wenige Zeilen mehr, kostet später keinen Umbau.

### E-ROU-2 — MQTT raus für V1
*Datum:* 2026-05-20

MQTT-Transport (Pub/Sub mit Topic-Hierarchie) ist das Zielbild für die
Verteiler-Architektur — siehe brainstorm-Architektur
`brainstorm/ideas/verteilerarchitektur-mqtt/verteilerlogik.md` (Stand
2026-05-15). Für V1 mit einem Display, das pollen kann, ist Reconnect-
und State-Recovery-Logik überdimensioniert.

Display V1 pollt `GET /api/v1/displays/<id>/state`. MQTT kommt als
eigenes Ticket, sobald ein zweites Display oder ein offline-fähiges
Tablet ins Spiel kommt.

### E-ROU-3 — Routing-DB (SQLite) raus für V1
*Datum:* 2026-05-20

Routing-Tabelle ist V1 eine JSON-Datei mit (vermutlich) einem Eintrag
(ROU-18). SQLite mit Migrationen, Indexen und Schema-Validierung wäre
für diesen einen Eintrag Overhead. V2 mit Onboarding-Flow für neue
Figuren (vgl. OPEN-FIG-B) und/oder mehreren Displays bekommt ein
eigenes Ticket.

### E-ROU-4 — 1:1-Mapping im Adapter, keine eigene Logik
*Datum:* 2026-05-20 (Ticket #11)

E-FIG-7 hat Quantisierung und Hysterese in die Phone-Seite gelegt. Der
Phone-Adapter braucht damit keine eigene Logik — er übersetzt das
Event-Schema, mehr nicht. Begründung im Detail in `figuren-erkennung.md`,
E-FIG-7.

Folgewirkung: ROU-7 und ROU-8 (Router-seitige Quantisierung und
Hysterese) wurden gestrichen.

### E-ROU-5 — Python + Flask
*Datum:* 2026-05-20

Passt zur entschiedenen Hub-Architektur (Python-Stack), erlaubt
schnelles Aufsetzen mit dem Flask-Testclient, kommt mit minimaler
Konfiguration aus. Service-Layout entsteht im Impl-PR, minimal und
nicht auf Vorrat (CLAUDE.md §6).

### E-ROU-6 — Tuning + Daten getrennt als zwei Dateien
*Datum:* 2026-05-20

Im Phone hatten wir nach einem ungeplanten Mit-Refactor gelernt:
Daten (Registry) und Tuning (Toleranzen) gehören neben den Code,
nicht in den Code (CLAUDE.md §6 Daten vs. Code). Für den Router
spalten wir gleich von Anfang an in zwei Dateien:

- `routing.json` — Routing-Tabelle (Daten, wächst pro Figur)
- `config.json`  — Tuning-Werte (Port, Host, Log-Level — wachsen pro
  Deployment)

Der Lebenszyklus ist unterschiedlich genug, dass eine gemeinsame Datei
gegenseitiges Übermalen begünstigen würde.

### E-ROU-7 — URL-Konvention nachgezogen + „screen" → „display"
*Datum:* 2026-05-21 (Ticket #24)

Der Router V1 (#5) wurde gebaut, bevor `specs/platform/urls.md` (die
URL-Konvention) gemergt war — die Endpunkte `POST /event`,
`GET /screen/<id>/state` und `GET /diag` verletzten URL-1/URL-4. Mit
#24 wurden sie auf `/api/v1/events`, `/api/v1/displays/<id>/state` und
`/api/v1/diag` gezogen.

Zugleich wurde der Begriff **„screen" vollständig durch „display"
ersetzt** — `screen_id` → `display_id`, `screen_ids` → `display_ids`.
„screen" und „display" bezeichneten dasselbe Konzept (eine Fläche, die
eine Buddy-View zeigt); „display" ist die etablierte Produktsprache
(das BuddyBoard *ist* der Display). Es gibt in V1 kein verstecktes
zweites Konzept.

**Bewusst offen gelassen:** Sollte ein Display je mehrere unabhängige
Regionen bekommen (Split-Screen), wäre „screen" als Unter-Region eines
Displays eine echte zweite Ebene. Spekulativ — wird erst mit Beleg
eingeführt (CLAUDE.md §6).

Lehre: Eine Konvention, die als offener Spec-PR herumliegt, bindet
nicht. Wäre `urls.md` vor dem Router-Bau gemergt gewesen, hätte es
diese Migration nicht gebraucht.
