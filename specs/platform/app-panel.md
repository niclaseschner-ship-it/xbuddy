# App-Panel — Spec     (ID-Präfix: PANEL)

> Status: V1-Kern · Refs #58

Ein zweiter Controller-Typ neben der Figuren-Erkennung
([`figuren-erkennung.md`](figuren-erkennung.md)): ein Bildschirm mit
Kacheln, je Kachel eine XBuddy-App-View. Eine Familie ohne physische
Figuren tippt eine Kachel → ein Event geht an den Router → der Router
schaltet das Display auf die zugehörige View. Welche Kacheln ein Panel
zeigt, steht modular in einer Datei neben dem Controller-Code; das Panel
selbst entscheidet **nichts** über Routing (ROU-1).

**V1-Scope:** Kachel-Panel als zweiter Controller-Typ; modulare
Kachel-Konfiguration als Datei (`tiles.json`); zwei Event-Typen
(`tile_selected`, `panel_cleared`); Descriptor-Schema `{ app, view }`
(optional `query`); Instanz-Konfiguration für mehrere Panels über
separate `config.json`-Dateien.

**Out-of-Scope (je eigenes Folge-Ticket):** Implementierungscode der
Seite und der PWA-Begleitdateien; Eltern-Chat als Schreiber der
Kachel-Konfiguration (Phase 2, → OPEN-PANEL-A); zeitgesteuerte
Sichtbarkeit von Kacheln (→ OPEN-PANEL-B); Auth- bzw.
Kiosk-Absicherung des Panels (→ OPEN-PANEL-C); die Apps und Views, die
über die Kacheln aufgerufen werden, selbst (`buddies/<name>.md`, z. B.
`plan.md`).

## Erweiterbarkeit (Leitgedanke)

Das Panel ist so geschnitten, dass eine **neue App oder eine neue View
ohne Code-Änderung** in den Bestand kommt:

- Die Seite rendert die Kacheln **rein aus `tiles.json` zur Laufzeit** —
  keine App-Liste, kein `switch` über App-Namen, kein Hardcode.
- Der Router-seitige App-Panel-Adapter (`router.md`, ROU-24) leitet die
  Ziel-URL **per Konvention** aus dem Descriptor ab — auch dort kein
  Hardcode-Mapping von App auf URL.
- Eine neue App im Panel = **eine neue Zeile in `tiles.json`** des
  jeweiligen Panels. Kein Eingriff in Controller-Code, kein Eingriff in
  Router-Code, kein Eintrag in `routing.json` pro Kachel
  (`routing.json` braucht nur einen Eintrag pro Panel-Instanz, siehe
  ROU-18).
- Mehrere parallel betriebene Panels = mehrere Instanz-`config.json`,
  je Panel eine eigene `tiles.json` (PANEL-3, PANEL-8). Jede Instanz
  bestückt sich unabhängig.
- Der Feldname `key` einer Kachel in `tiles.json` ist **stabil**
  (PANEL-3), damit ein späterer Schreiber (Eltern-Chat, OPEN-PANEL-A)
  Kacheln gezielt ändern oder entfernen kann, ohne den Rest der Datei
  zu kennen.

## 1. Panel-Funktion

### PANEL-1 — Panel & Routing-Trennung
Das Panel ist ein Kachel-Bildschirm; je Kachel eine App-View. Ein Tap
auf eine Kachel sendet ein Event an den Router. Der **Router** entscheidet
das Routing (Display-Auswahl, Ziel-URL) — das Panel **niemals selbst**.
Diese Trennung folgt ROU-1 und ist analog zur Figuren-Erkennung: der
Controller liefert Semantik, der Router macht Routing.

*Tickets:* #58

### PANEL-2 — URL-Verortung
Die Panel-Seite wird unter `/controller/app-panel/<id>` ausgeliefert —
unter dem zulässigen `/controller/`-Prefix (URL-1). Das zweite Segment
`<id>` ist die Instanz-Identität des Panels (z. B. `kueche`,
`flur-tablet`), kein Aktions-Verb. Das ist eine **dokumentierte
Abweichung von URL-3**, analog ROU-20 für `/display/<id>`: der Pfad
sitzt im richtigen Prefix, weicht aber bewusst von der
Action-/Asset-Form ab, weil eine Panel-Instanz adressiert wird, nicht
eine Aktion oder ein Asset. (Decision 5)

Die Aktion eines Kachel-Taps läuft **nicht** über einen eigenen
Controller-Aktions-Pfad (kein `/controller/app-panel/<id>/select`),
sondern über den generischen Event-Eingang `POST /api/v1/events`
(ROU-3, URL-4, siehe PANEL-5).

*Tickets:* #58

## 2. Kachel-Konfiguration

### PANEL-3 — `tiles.json` neben dem Code
Die Kacheln eines Panels stehen in der Datei `tiles.json` im selben
Verzeichnis wie der Panel-Code (analog FIG-23 und ROU-18). Format: ein
JSON-Objekt mit dem Feld `tiles`, das eine Liste von Kachel-Einträgen
enthält. Jeder Eintrag hat folgende Felder:

| Feld     | Typ            | Pflicht | Bedeutung                                                                 |
|----------|----------------|---------|---------------------------------------------------------------------------|
| `key`    | string         | ja      | Stabiler Identifier der Kachel, eindeutig innerhalb der `tiles.json`.     |
| `app`    | string         | ja      | App-Slug (z. B. `plan`, `kalender`) — fließt in den Descriptor (PANEL-7). |
| `view`   | string         | ja      | View-Name innerhalb der App (z. B. `woche`, `now-playing`).               |
| `query`  | object (flach) | nein    | Optionale Query-Parameter (Strings/Zahlen) für die Ziel-View.             |
| `label`  | string         | ja      | Beschriftung der Kachel im UI.                                            |
| `icon`   | string         | ja      | Verweis auf die Kachel-Grafik (lokales Asset im selben Verzeichnis).      |
| `sichtbar` | boolean      | ja      | `true` → Kachel wird gerendert; `false` → nicht gerendert (siehe PANEL-4). |

Die **Listen-Reihenfolge in `tiles.json` ist die Anzeige-Reihenfolge**
der Kacheln im Panel. `key` ist bewusst stabil: ein späterer
Schreiber (OPEN-PANEL-A) kann eine Kachel daran finden und gezielt
ändern oder entfernen, ohne die Listenposition zu kennen.

**Selbsttragend:** Die Datei liegt im Panel-Verzeichnis und wird
mitausgeliefert. Pro Panel-Instanz separat verwaltet — `tiles.json` ist
per `.gitignore` aus dem Repo ausgeschlossen; `tiles.example.json`
dokumentiert das Format im Repo. (Decision 4)

*Tickets:* #58

### PANEL-4 — `sichtbar`-Flag
Eine Kachel mit `sichtbar: false` wird **nicht gerendert** und kann
deshalb nicht angetippt werden — sie sendet nichts. Das ist die
einfachste Form von „Kachel temporär weg" („heute keine Fotos") und
verlangt entweder ein Flag oder das Entfernen der Zeile aus
`tiles.json` (beide Wege sind gültig). Zeitgesteuerte Sichtbarkeit
(Tageszeit, Wochentag, Person) ist OPEN-PANEL-B.

*Tickets:* #58

## 3. Events an den Router

### PANEL-5 — Transport
Events gehen per HTTP POST an `<router_url>/api/v1/events`, JSON-Body,
`Content-Type: application/json` — derselbe Eingang wie für die
Figuren-Erkennung (FIG-9). Der Pfad folgt URL-4 und ist die Gegenseite
von ROU-3. Retry-Verhalten analog FIG-12: bis zu **3 Wiederholungen**
mit Backoff 200 ms / 1 s / 5 s, danach Drop, kein Persistenz-Puffer.

*Tickets:* #58

### PANEL-6 — Event-Schema
Zwei Event-Typen, beide als Zustands-Aussage (idempotent).
**Pflichtfelder auf allen Events:** `source_id`, `ts`, `type` (analog
FIG-10).

```json
// Beim Tap auf eine sichtbare Kachel
{ "source_id": "app-panel:kueche", "ts": "<iso8601>",
  "type": "tile_selected",
  "app":  "<string>", "view": "<string>", "query": { ... } }

// Beim Tap auf das eingebaute Ruhe-Element (Panel löschen)
{ "source_id": "app-panel:kueche", "ts": "<iso8601>",
  "type": "panel_cleared" }
```

`source_id` identifiziert die Panel-Instanz (PANEL-8) im Format
`app-panel:<instanz>`. `tile_selected` enthält den vollständigen
Descriptor (PANEL-7), damit der Router-Adapter ohne Rückgriff auf
`tiles.json` arbeiten kann. `query` ist nur dann gesetzt, wenn die
Kachel in `tiles.json` ein `query`-Objekt hat — andernfalls fehlt das
Feld.

`panel_cleared` kommt von einem **fest in der Seite eingebauten
Ruhe-Element** (kein konfigurierbarer Kachel-Eintrag in `tiles.json`)
und wirkt analog zu `session_ended` der Figuren-Erkennung: der
Router-Adapter (ROU-24) übersetzt es in das Session-Ende-Signal aus
ROU-11. Begründung der Aufnahme: ein Panel hat kein physisches „Figur
abheben"; ohne expliziten Ruhe-Pfad könnte das Display nie wieder
dunkel werden, was der Constitution „nicht-invasiv" und dem
Display-Ruhe-Zustand DC-5 widerspricht. (Decision 3)

*Tickets:* #58

### PANEL-7 — Descriptor-Schema
Der Trigger-Descriptor (ROU-2) einer Panel-Kachel ist semantisch und
flach:

```
descriptor = { "app": "<string>", "view": "<string>"[,
               "query": { <string>: <string|number>, ... }] }
```

`app` und `view` sind die zwei Segmente der Ziel-URL nach URL-2
(`/display/<app>/<view>`). `query` ist eine flache Map mit Strings
oder Zahlen — keine verschachtelten Objekte oder Listen, damit ROU-2
gewahrt bleibt. Der Adapter (ROU-24) leitet aus diesem Descriptor die
Ziel-URL **per Konvention** ab; es gibt kein opakes `tile_id` und
keine zusätzliche Tabelle, die `tile_id` auf URL mappen müsste.
(Decision 1)

*Tickets:* #58

## 4. Konfiguration

### PANEL-8 — Instanz-Konfiguration `config.json`
Beim Laden der Seite wird `./config.json` per `fetch` geladen und auf
die Defaults im Panel-Code angewendet (analog FIG-23 und ROU-19).
Pro-Instanz-Werte liegen damit **als Daten neben dem Code** — der
Panel-Code bleibt reine Logik und ist über alle Panel-Instanzen
identisch.

**Format:** JSON-Objekt mit mindestens den folgenden Feldern (weitere
Tuning-Werte können später dazukommen, ohne Breaking Change):

| Feld         | Typ    | Bedeutung                                                          |
|--------------|--------|--------------------------------------------------------------------|
| `source_id`  | string | Identität dieser Panel-Instanz, z. B. `app-panel:kueche`.          |
| `router_url` | string | Origin des Routers (Schema + Host[:Port], **ohne Pfad**, analog FIG-23). |

**Priorität & Fehler-Fallback:** Identisch zu FIG-23 / ROU-19. URL-
Parameter überschreiben `config.json` überschreibt Defaults. Existiert
die Datei nicht oder ist sie nicht parsebar, fällt die Seite **stumm**
auf die Defaults zurück und protokolliert `console.warn` — die Seite
bleibt funktionsfähig. (Decision 4)

**Selbsttragend:** Datei liegt im Panel-Verzeichnis und wird
mitausgeliefert. Pro Instanz separat verwaltet — `config.json` ist
gitignored; `config.example.json` dokumentiert das Format. Mehrere
Panels = mehrere Instanzen, je Panel **eine eigene `config.json`
zusammen mit einer eigenen `tiles.json`** im jeweiligen Auslieferungs-
Verzeichnis.

**Kopplung zum Router:** `source_id` muss mit dem `source_id`-Wert
eines `panels`-Eintrags der Routing-Tabelle (ROU-18) übereinstimmen,
sonst greift der Adapter (ROU-24) für diese Panel-Instanz nicht.

*Tickets:* #58

## 5. Tests

### PANEL-9 — Automatisierte Tests pro Requirement
Jede Requirement-ID, die Code-Verhalten beschreibt, hat einen
automatisierten Test (CLAUDE.md §6; analog ROU-17, PLAN-29). Die Tests
entstehen mit dem Implementierungs-Ticket.

Mindest-Abdeckung:

- PANEL-1 — Ein Tap auf eine Kachel sendet ein Event und löst keine
  Routing-Entscheidung im Panel selbst aus (kein Display-Wechsel
  ohne Router-Antwort).
- PANEL-2 — *Tests:* GET `/controller/app-panel/<id>` antwortet mit
  HTTP 200 und `Content-Type: text/html`; der `<id>`-Wert aus dem
  URL-Segment landet im gerenderten HTML als Instanz-Identität
  (z. B. als `data-source-id`-Attribut oder vergleichbares
  Spec-neutrales Token), so dass die Seite ihre eigene Panel-Identität
  ohne weiteren Roundtrip kennt.
- PANEL-3 — `tiles.json` mit gemischten Einträgen wird in der
  Listen-Reihenfolge gerendert; `key` ist eindeutig.
- PANEL-4 — Eintrag mit `sichtbar: false` wird nicht gerendert und
  sendet beim Versuch kein Event (Element existiert nicht).
- PANEL-5 — Erfolgreicher POST wird gesendet; bei Netzwerk-Fehler
  greift das Retry-Schema (200 ms / 1 s / 5 s, dann Drop).
- PANEL-6 — `tile_selected`-Event hat alle Pflichtfelder (`source_id`,
  `ts`, `type`, `app`, `view`) und `query` nur wenn in `tiles.json`
  gesetzt. `panel_cleared` hat `source_id`, `ts`, `type` und kein
  Descriptor-Feld.
- PANEL-7 — Descriptor ist flach (Strings/Zahlen); ein verschachteltes
  `query` wird als Konfigurations-Fehler abgewiesen.
- PANEL-8 — Fehlende oder kaputte `config.json` lässt die Seite mit
  Defaults laufen (keine Crashen, `console.warn`-Eintrag).
  Konfigurierbare Werte überschreiben Defaults in der dokumentierten
  Priorität. *Tests:* die load-bearing Kopplung „`source_id` aus
  `config.json` == Schlüssel im `panels`-Abschnitt der `routing.json`
  des Routers" (siehe PANEL-8 Body, ROU-18) wird beim Start geprüft;
  eine Diskrepanz erscheint als sichtbarer Fehler (Test prüft die
  sichtbare Fehler-Signalisierung). Der stumme Default-Fallback bei
  fehlender/kaputter `config.json` bleibt erlaubt und ist konsistent
  zu FIG-23/ROU-19 — geprüft wird, dass beide Wege (sichtbarer
  Konsistenz-Fehler vs. stummer Datei-Fallback) sich nicht
  vermischen.

*Tickets:* #58

---

## Offene Punkte

- **OPEN-PANEL-A** — Eltern-Chat als Schreiber von `tiles.json`
  (Phase 2): Ein späteres Ticket erlaubt es Eltern, Kacheln per
  Telegram-Bot zu erstellen, zu ändern oder zu entfernen. Das ist der
  Grund, warum `key` in PANEL-3 stabil ist — ein Schreiber muss eine
  bestehende Kachel zuverlässig referenzieren können, auch wenn sich
  Reihenfolge oder Anzahl ändern.
- **OPEN-PANEL-B** — Zeitgesteuerte Sichtbarkeit: Heutige Variante ist
  `sichtbar: true|false` (PANEL-4). Eine spätere Variante könnte
  Tageszeit-, Wochentag- oder Personen-Filter unterstützen (z. B.
  „Foto-Kachel nur am Wochenende"). Eigenes Ticket, sobald gebraucht.
- **OPEN-PANEL-C** — Auth- und Kiosk-Absicherung: Das Panel läuft V1
  ungesichert (jeder, der die URL aufruft, kann tippen). Wie das Panel
  auf einem dedizierten Familien-Tablet gegen versehentliches
  Verlassen, fremde Zugriffe oder versehentliche Konfigurations-
  Änderungen abgesichert wird, ist ein eigenes Folge-Ticket.

---

## Entscheidungen

Architektur-Entscheidungen aus der Konzept-Session zu Ticket #58,
festgehalten an der Spec, weil sie nicht aus dem Code ableitbar sind
und für Folge-Tickets load-bearing bleiben.

### E-PANEL-1 — Descriptor `{ app, view }` (+ optional `query`), nicht opak `{ tile_id }`
*Datum:* 2026-05-25 (Ticket #58)

Frühe Variante: Der Descriptor ist ein opaker `tile_id`-String, den
der Router gegen eine Mapping-Tabelle `tile_id → (app, view, query)`
auflöst. **Verworfen** aus zwei Gründen:

1. Die Mapping-Tabelle wäre eine zweite Wahrheit neben `tiles.json` —
   jede neue Kachel müsste sowohl in `tiles.json` (für die UI) als auch
   in einer Router-Tabelle (für die Auflösung) gepflegt werden.
   Doppelpflege; bei einem späteren Schreiber (Eltern-Chat,
   OPEN-PANEL-A) wäre das ein zweiter Schreibpfad.
2. `{ app, view }` ist bereits **fast die Ziel-URL** nach URL-2. Damit
   kann der Adapter (ROU-24) sie **per Konvention** zusammenstellen, ohne
   eine zusätzliche Indirektion zu pflegen — genau die Vereinfachung,
   die der Router-Kern (ROU-9) durch direkten Feld-Match ohnehin
   verlangt.

Stattdessen: semantischer Descriptor `{ app, view }` mit optionalem
flachen `query`. ROU-2-konform (flache Strings/Zahlen). Folgewirkung:
E-ROU-8 in `router.md` (Routing per Konvention, nicht per Kachel-
Eintrag in `routing.json`).

### E-PANEL-2 — Zwei Event-Typen: `tile_selected` und `panel_cleared`
*Datum:* 2026-05-25 (Ticket #58)

`tile_selected` alleine reicht zum Anschalten — aber ein Panel hat kein
physisches „Figur abheben" wie `session_ended` der Figuren-Erkennung
(FIG-11). Ohne expliziten Ruhe-Pfad könnte das Display nie wieder
dunkel werden. Das widerspricht der Constitution-Eigenschaft
„nicht-invasiv" und dem Display-Ruhe-Zustand DC-5.

Stattdessen: ein **eingebautes** Ruhe-Element der Seite (keine
konfigurierbare Kachel, kein Eintrag in `tiles.json`) sendet
`panel_cleared`. Der Router-Adapter (ROU-24) übersetzt das in das
Session-Ende-Signal aus ROU-11 und alle Displays, die zu dieser
Panel-Instanz gehören, kehren in den Ruhe-Zustand zurück.

Die Symmetrie zum `session_ended` der Figuren-Erkennung ist
beabsichtigt — der Router-Kern bleibt agnostisch davon, welcher
Controller-Typ ein Session-Ende signalisiert.

### E-PANEL-3 — Zwei Dateien: `tiles.json` (Daten) ↔ `config.json` (Tuning)
*Datum:* 2026-05-25 (Ticket #58)

Übernimmt die Lehre aus **E-ROU-6**: Daten und Tuning haben
unterschiedliche Lebenszyklen — Daten wachsen mit dem Bestand (mehr
Apps → mehr Kacheln), Tuning wächst mit dem Deployment (neue Instanz →
neue `source_id`, neuer `router_url`). Eine gemeinsame Datei würde
gegenseitiges Übermalen begünstigen, besonders sobald ein automatischer
Schreiber (OPEN-PANEL-A) `tiles.json` ändert, aber `config.json`
nicht anfassen darf.

Stattdessen zwei getrennte Dateien neben dem Code, beide
gitignored, beide mit einer dokumentierten `*.example.json`-Vorlage.
CLAUDE.md §6 (Daten vs. Code).

### E-PANEL-4 — Panel-Seite unter `/controller/app-panel/<id>`; Kachel-Tap via `POST /api/v1/events`
*Datum:* 2026-05-25 (Ticket #58)

Die Seite sitzt im erlaubten `/controller/`-Prefix (URL-1). Das
`<id>`-Segment statt eines Aktions-Verbs ist **dokumentierte
URL-3-Abweichung** analog ROU-20 — die Panel-Instanz ist eine
Identität, kein Action-Endpoint, kein Asset-Pfad.

Kein eigener `/controller/app-panel/<id>/<action>`-Pfad für den Tap:
ROU-3 ist der eine generische Event-Eingang für **alle**
Controller-Typen. Eine zusätzliche Action-URL pro Controller-Typ
würde dieses Prinzip aufweichen und für jeden neuen Controller-Typ
einen weiteren Pfad in der Origin-Routing-Tabelle (URL-14) verlangen.
Die Figuren-Erkennung folgt derselben Linie (FIG-9 / ROU-3).
