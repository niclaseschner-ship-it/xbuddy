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
Seite (einschließlich der PWA-Begleitdateien aus PANEL-10) — kommt im
Impl-Folge-Ticket; Eltern-Chat als Schreiber der Kachel-Konfiguration
(Phase 2, → OPEN-PANEL-A); zeitgesteuerte Sichtbarkeit von Kacheln
(→ OPEN-PANEL-B); die Apps und Views, die über die Kacheln aufgerufen
werden, selbst (`buddies/<name>.md`, z. B. `plan.md`).

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

Diese Abweichung ist zentral als Teil der Übersicht aller
URL-3a-Abweichungen in
[`../../conventions/urls.md`](../../conventions/urls.md) (URL-3a) aufgelistet.

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

| Feld       | Typ            | Pflicht | Bedeutung                                                                 |
|------------|----------------|---------|---------------------------------------------------------------------------|
| `key`      | string         | ja      | Stabiler Identifier der Kachel, eindeutig innerhalb der `tiles.json`.     |
| `app`      | string         | ja      | App-Slug (z. B. `plan`, `kalender`) — fließt in den Descriptor (PANEL-7). |
| `view`     | string         | ja      | View-Name innerhalb der App (z. B. `woche`, `now-playing`).               |
| `query`    | object (flach) | nein    | Optionale Query-Parameter (Strings/Zahlen) für die Ziel-View.             |
| `label`    | string         | ja      | Beschriftung der Kachel im UI.                                            |
| `icons`    | string[]       | ja      | Liste von Icon-Pfaden (≥1, max 3). Pfade relativ zur Icon-Basis (siehe unten). Mehrere Icons werden in einer Reihe nebeneinander gerendert. |
| `sichtbar` | boolean        | ja      | `true` → Kachel wird gerendert; `false` → nicht gerendert (siehe PANEL-4). |

**Icon-Pfade und Icon-Basis:** Die Default-Icon-Quelle ist die zentrale
ARASAAC-Bibliothek (ICONS-1, #135). Pfade in `icons[]` werden als
relativ zur Icon-Basis `/display/_shared/icons/` aufgelöst (ROU-26,
same-origin). Beispiel: `"arasaac/32488.png"` → URL
`/display/_shared/icons/arasaac/32488.png`.

**Kinder-Varianten-Pattern (Tile-Set-Konvention):** Eine Kachel, die
eine **Kinder-Ansicht** einer App darstellt (z. B. `ansicht: klein`),
trägt als **zweites Icon** einen Kinderkopf aus der zentralen
Bibliothek (`arasaac/2484.png`) — nebeneinander neben dem primären
App-Icon, **nicht** als zusammengesetztes Bild. Das Muster gilt für
alle Kinder-Varianten im Tile-Set dieses Panels; die zweite Stelle in
`icons[]` fungiert so als visueller Rollen-Marker.

Hinweis: Sobald ein zweiter Buddy oder Controller-Typ dieselbe Kinder-Marker-
Konvention braucht, gehört das Muster nach `conventions/` — heute ist das
App-Panel der erste und einzige Ort (nichts auf Vorrat, CLAUDE.md §6).

Die **Listen-Reihenfolge in `tiles.json` ist die Anzeige-Reihenfolge**
der Kacheln im Panel. `key` ist bewusst stabil: ein späterer
Schreiber (OPEN-PANEL-A) kann eine Kachel daran finden und gezielt
ändern oder entfernen, ohne die Listenposition zu kennen.

**Selbsttragend:** Die Datei liegt im Panel-Verzeichnis und wird
mitausgeliefert. Pro Panel-Instanz separat verwaltet — `tiles.json` ist
per `.gitignore` aus dem Repo ausgeschlossen; `tiles.example.json`
dokumentiert das Format im Repo. (Decision 4)

*Tickets:* #58, #136

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
von ROU-3. Retry- und Drop-Verhalten folgt der Event-Transport-
Konvention `conventions/event-transport.md` (EVT-1 Retry-Backoff,
EVT-2 Drop nach N Versuchen, kein Persistenz-Puffer) — symmetrisch
zu FIG-12.

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

`panel_cleared` kommt von einer **eigenen 'Aus'-Kachel im Kachel-Grid**,
die **von der Seite eingefügt wird** und **nicht aus `tiles.json`
gerendert** ist. Sie wirkt analog zu `session_ended` der
Figuren-Erkennung: der Router-Adapter (ROU-24) übersetzt das Event in
das Session-Ende-Signal aus ROU-11. Begründung der Aufnahme: ein Panel
hat kein physisches „Figur abheben"; ohne expliziten Ruhe-Pfad könnte
das Display nie wieder dunkel werden, was der Constitution
„nicht-invasiv" und dem Display-Ruhe-Zustand DC-5 widerspricht.
(Decision 3)

**Form & Position der Aus-Kachel:**

- **Position:** stets am **Ende der Kachel-Liste**, nach allen
  sichtbaren Kacheln aus `tiles.json`. Reihenfolge:
  `[tiles.json (sichtbare)] → [Aus-Kachel]`. Die Aus-Kachel ist auch
  dann die letzte Position, wenn `tiles.json` leer ist.
- **Visualisierung:** gleiche Kachelgröße und gleiches Gitter-Verhalten
  wie eine reguläre Kachel — sie unterscheidet sich nur durch Inhalt
  (`label` „Aus" und ein neutrales Symbol). Das Icon der Aus-Kachel ist
  das ARASAAC-Piktogramm `arasaac/8252.png` (ID 8252 = „aus",
  Wort→ID aus `pictogram_cache.json`, Stand 2026-06-02) aus der
  zentralen Bibliothek (ICONS-5, ROU-26). Fallback: wenn das Icon
  nicht geladen werden kann, bleibt die Kachel mit Label „Aus" und
  leerem Icon-Slot funktionsfähig. (#136)
- **Tap-Mechanik:** **einfacher Tap** (`tap`/`click`) — symmetrisch zu
  regulären Kacheln. Kein Long-Press, keine Doppel-Bestätigung.
- **Sichtbarkeit:** **immer sichtbar**, unabhängig vom Display-State.
  PANEL-1 bleibt: die Seite kennt den Display-State nicht. Ein Tap bei
  bereits leerem Display sendet trotzdem `panel_cleared` (idempotent,
  analog FIG-10).
- **Nicht in `tiles.json`:** die Aus-Kachel ist kein konfigurierbarer
  Kachel-Eintrag. Editieren von `tiles.json` (auch `sichtbar: false`)
  hat keinen Effekt auf die Aus-Kachel.

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

**Format:** JSON-Objekt mit mindestens den folgenden Feldern in
CONFIG-2-Form (weitere Tuning-Werte können später dazukommen, ohne
Breaking Change):

| Name         | Default                          | Datei-Schlüssel | gesetzt durch (Onboarding-Schritt) |
|--------------|----------------------------------|-----------------|------------------------------------|
| `source_id`  | (kein Default — Pflicht)         | `source_id`     | — (offen, OPEN-PANEL-C)            |
| `display_id` | (kein Default — Pflicht)         | `display_id`    | — (offen, OPEN-PANEL-C)            |
| `router_url` | (kein Default — Pflicht)         | `router_url`    | — (offen, OPEN-PANEL-C)            |

`source_id` ist die Identität dieser Panel-Instanz (z. B.
`app-panel:kueche`). `display_id` erwartet IDENT-1-Form (`<typ>-<slug>-<nn>`,
z. B. `tablet-wohnzimmer-01`); der Panel-Code validiert die Form in V1
nicht hart — ein Display, feste Tablets, keine Laufzeit-Prüfung nötig.
`router_url` ist die Origin des Routers (Schema + Host[:Port], **ohne
Pfad**, analog FIG-23). *(#305)*

**Kein URL-Parameter-Overlay:** Das App-Panel liest seine Konfiguration
ausschließlich aus `config.json` — URL-Parameter überschreiben die
Konfiguration **nicht**. Begründung: V1, feste Tablets, kein wechselnder
Kontext pro Seitenaufruf. Ein URL-Overlay ist nachrüstbar, sobald der
Onboarding-Skill (Ticket #183, App-Panel-Onboarding) es braucht.
Dies ist eine bewusste Ausnahme von PWA-4, die dort für andere
Controller-Typen (z. B. Figuren-Erkennung) weiterhin gilt. *(#251)*

**Priorität & Fehler-Fallback:** Folgen der Konfigurations-Konvention
`conventions/config.md` (CONFIG-5: Priorität CLI > ENV > config.json > Defaults —
ohne URL-Parameter-Override für das App-Panel, siehe oben;
CONFIG-4: fehlende/kaputte Datei → Defaults + Warnung, Prozess startet) — analog FIG-23 / ROU-19. (Decision 4)

**Selbsttragend:** Datei liegt im Panel-Verzeichnis und wird
mitausgeliefert. Pro Instanz separat verwaltet — `config.json` ist
gitignored; `config.example.json` dokumentiert das Format. Mehrere
Panels = mehrere Instanzen, je Panel **eine eigene `config.json`
zusammen mit einer eigenen `tiles.json`** im jeweiligen Auslieferungs-
Verzeichnis.

**Kopplung zum Router:** `source_id` muss mit dem `source_id`-Wert
eines `panels`-Eintrags der Routing-Tabelle (ROU-18) übereinstimmen,
sonst greift der Adapter (ROU-24) für diese Panel-Instanz nicht.
Zusätzlich muss `display_id` mit dem `display_id`-Wert desselben
`panels`-Eintrags übereinstimmen — der Panel-Code abonniert genau
diesen Display-Zustands-Stream (ROU-22) für die Aktiv-Kachel-Markierung
(PANEL-11). Diese load-bearing-Kopplung wird beim Start geprüft
(analog der `source_id`-Konsistenz-Prüfung); eine Diskrepanz erscheint
als sichtbarer Fehler.

*Tickets:* #58

## 5. Kiosk-Absicherung

### PANEL-10 — Vollbild & Bildschirm wach halten
Das Panel ist eine Controller-PWA und erfüllt damit die Pflichten aus
`conventions/controller-pwa.md` (PWA-1 Pflicht-Dateien, PWA-2
Manifest-Pflichtfelder inkl. `display: fullscreen`, PWA-3 Wake-Lock +
Fullscreen-API beim ersten User-Gesture, PWA-4 Config-Lade-Konvention)
— analog DC-11 und FIG-24/FIG-26.

**Hinweis:** **App-Pinning** ist Familien-Onboarding-Aufgabe und kein
Code-Verhalten — wird in einem entsprechenden Onboarding-Schritt für
das Familien-Tablet eingerichtet (analog dem Display-Tablet). Die
Spec nennt das, fordert aber keinen Code dafür.

*Tickets:* #58

## 6. Aktive-Kachel-Markierung

### PANEL-11 — Aktive Kachel im Panel-UI optisch markieren
Wenn der User eine Kachel antippt und das zugeordnete Display den
entsprechenden Inhalt zeigt, wird **diese Kachel im Panel-UI optisch
markiert** — sichtbar von der Restmenge unterschieden
(Hintergrund-Hervorhebung oder Border). Die konkreten Design-Tokens
kommen im Impl-PR; die Spec verlangt nur „sichtbar unterscheidbar".

**Quelle der Wahrheit der Markierung:** der Panel-Code abonniert beim
Laden den **SSE-Zustands-Stream seines zugeordneten Displays**
(ROU-22: `GET /api/v1/displays/<display_id>/events`, `<display_id>`
aus `config.json`, PANEL-8) und vergleicht die im Stream gelieferte
`payload.url` mit den `{ app, view, query? }`-Werten seiner Kacheln.
Die Kachel, deren Konvention `/display/<app>/<view>[?<query>]` (vgl.
ROU-24) zur aktuellen Display-`payload.url` passt, ist aktiv markiert
— maximal eine Kachel gleichzeitig.

- **Display-Ruhe-Zustand** (Stream meldet `null` / Session-Ende,
  ROU-10/ROU-11/ROU-12) → **keine** Kachel markiert.
- **Stream-Abbruch** (Netz-Fehler) → die zuletzt bekannte Markierung
  **bleibt stehen** (analog DC-6 „Inhalt bleibt bei Störung stehen").
  Re-Verbindung über den Browser-`EventSource`-Standard-Reconnect
  (analog DC-7); nach erfolgreicher Wiederverbindung richtet sich die
  Markierung neu nach dem Stream-Zustand.
- **Display-Inhalt ohne Kachel-Match** (z. B. eine URL, die durch
  Figuren-Erkennung übersteuert wurde und zu keiner Panel-Kachel passt)
  → **keine** Kachel markiert (kein Match → kein Highlight).
- **`panel_cleared`-Tap:** der Panel-Code wartet auf das Stream-Update,
  das den Wechsel auf `null` meldet, dann verschwindet die Markierung.
  Ein optimistisches lokales Update (Markierung sofort weg) ist
  erlaubt, aber das Stream-Update bleibt die Wahrheit — bei Diskrepanz
  korrigiert sich die Markierung beim nächsten Stream-Ereignis.

PANEL-1 bleibt gewahrt: das Panel entscheidet weiterhin **nichts** über
das Routing — es liest den Display-Zustand nur, um seine eigene UI zu
spiegeln.

*Tickets:* #58

## 7. Tests

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
  Descriptor-Feld. **Aus-Kachel:** wird **immer** als letzte Kachel
  gerendert, auch wenn `tiles.json` leer ist; ist **nicht** in
  `tiles.json` enthalten und wird **nicht** durch ein Editieren der
  Datei beeinflusst (kein `sichtbar: false`-Effekt); ein Tap auf die
  Aus-Kachel sendet `panel_cleared` mit den drei Pflichtfeldern
  (`source_id`, `ts`, `type`) und ohne Descriptor-Felder.
- PANEL-7 — Descriptor ist flach (Strings/Zahlen); ein verschachteltes
  `query` wird als Konfigurations-Fehler abgewiesen.
- PANEL-8 — Fehlende oder kaputte `config.json` lässt die Seite mit
  Defaults laufen (keine Crashen, `console.warn`-Eintrag).
  Konfigurierbare Werte überschreiben Defaults in der dokumentierten
  Priorität. Der Config-Bootstrap nutzt `pwaShared.loadPwaConfig`
  (PWA-4, `controller/_shared/config.js`) für Fetch, Merge und stummen
  Fallback; `panelLib.checkConfigConsistency` prüft danach die
  load-bearing Kopplungen.
  *Tests:* die load-bearing Kopplung „`source_id` aus
  `config.json` == Schlüssel im `panels`-Abschnitt der `routing.json`
  des Routers" (siehe PANEL-8 Body, ROU-18) wird beim Start geprüft;
  eine Diskrepanz erscheint als sichtbarer Fehler (Test prüft die
  sichtbare Fehler-Signalisierung). Zusätzlich wird die Kopplung
  „`display_id` aus `config.json` == `display_id` desselben
  `panels`-Eintrags" beim Start geprüft; ein fehlendes oder
  abweichendes `display_id` erscheint ebenfalls als sichtbarer Fehler.
  Der stumme Default-Fallback bei fehlender/kaputter `config.json`
  bleibt erlaubt und ist konsistent zu FIG-23/ROU-19 — geprüft wird,
  dass beide Wege (sichtbarer Konsistenz-Fehler vs. stummer
  Datei-Fallback) sich nicht vermischen.
- PANEL-10 — Das PWA-Manifest deklariert `display: fullscreen`
  (Manifest-Test). `navigator.wakeLock.request('screen')` wird beim
  Laden aufgerufen; bei `visibilitychange` auf `visible` erneut.
  `requestFullscreen()` wird beim ersten Nutzer-Gesture versucht; ein
  Fehler dabei wirft den Code nicht ab.
- PANEL-11 — Das Panel verbindet sich beim Laden mit
  `/api/v1/displays/<display_id>/events` (ROU-22), `display_id` aus
  `config.json` (PANEL-8). Ein Stream-Update mit
  `payload.url = /display/plan/woche` markiert die zugehörige Kachel
  (`app: plan`, `view: woche`); ein folgendes Update mit
  `payload.url = /display/plan/woche?ansicht=klein` verschiebt die
  Markierung auf die Kachel mit passendem `query`. Ein Stream-Update
  auf `null` (Session-Ende, ROU-11) entfernt jede Markierung.
  Display-Inhalt, der zu keiner Kachel passt (z. B. eine URL aus
  einer anderen App, durch Figuren-Erkennung übersteuert), markiert
  keine Kachel. Ein simulierter Stream-Abbruch lässt die letzte
  Markierung sichtbar (analog DC-6); nach erfolgter Reconnect-Phase
  (analog DC-7) richtet sich die Markierung neu nach dem aktuellen
  Stream-Zustand.

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
- **OPEN-PANEL-C** — Onboarding-Schritt für Panel-Instanz-Setup. Die
  CONFIG-2-Tabelle in PANEL-8 hat heute drei Pflicht-Felder ohne
  Default **und** ohne Onboarding-Schritt (`source_id`, `display_id`,
  `router_url`) — formell eine CONFIG-2-Verletzung. Praktisch werden
  Panel-Instanzen in V1 manuell beim Deployment befüllt
  (`config.example.json` als Vorlage). Sobald Panel-Instanzen über den
  Eltern-Chat eingerichtet werden können (analog der Funktions-Spec
  `familie-anlegen.md`), bekommt jede Zeile der PANEL-8-Tabelle einen
  konkreten Schritt-Namen.
- **OPEN-PANEL-D** — *Erfüllt:* Backoff-Werte des Event-Transports in
  PANEL-5 leben jetzt in der Event-Transport-Konvention
  `conventions/event-transport.md` (EVT-1/EVT-2) — eine eigene
  Tuning-Tabelle in `app-panel.md` ist damit nicht mehr nötig. Ein
  späterer Override-Pfad (Datei-Schlüssel je Controller) gehört in die
  Konvention, nicht in diese Spec.

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

Eigene **'Aus'-Kachel im Grid** statt diskretem Aus-Knopf am Rand:
konsistent zum Kachel-Pattern — ein Kind erkennt, dass auch das
Ruhe-Element „eine Kachel ist, die etwas tut". Einfacher Tap analog
zu regulären Kacheln; eine Doppel-Bestätigung würde die Ruhe-Aktion
gegenüber den anderen Aktionen aufwerten und damit der
Constitution-Eigenschaft `nicht-invasiv` zuwiderlaufen.

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

### E-PANEL-5 — Ein Panel = genau ein Display
*Datum:* 2026-05-25 (Ticket #58)

**Verworfen:** ein Panel kann mehrere Displays gleichzeitig steuern
(frühere ROU-18-Variante mit `display_ids`-Plural im `panels`-Eintrag).

**Stattdessen:** harte 1:1-Bindung Panel ↔ Display, verbalisiert in
PANEL-8 (`display_id` als Pflichtfeld in `config.json`) und in ROU-18
(`panels`-Eintrag mit Singular `display_id`).

Begründungen:

- **Aktiv-Markierung wird eindeutig (PANEL-11):** Die Markierung
  braucht **genau einen** Display-Stream als Wahrheits-Quelle (ROU-22).
  Bei mehreren Displays pro Panel wäre unklar, welche Display-`payload.url`
  für die Markierung maßgeblich ist; eine neue Router-API zur
  Mehrziel-Auflösung wäre nötig — Infrastruktur-Aufwand ohne
  V1-Nutzen.
- **Familie-3-Probe / Symmetrie zu Mehrfach-Instanzen:** Wer zwei
  Displays steuern will, betreibt **zwei Panel-Instanzen** — dasselbe
  Muster wie bei mehreren Familien-Hubs oder mehreren
  Phone-Controllern. Symmetrisch, kein Sonderfall im Code.
- **CLAUDE.md §6 „nichts auf Vorrat":** Mehrziel-Steuerung ist heute
  kein konkreter Bedarf. Spätere Wiederzulassung ist als kompatible
  Erweiterung möglich (`display_id` → `display_ids[]` in einer
  zukünftigen Spec-Version, mit Migrations-Hinweis) — die Entscheidung
  ist nicht endgültig zubetoniert, nur für V1 die einfachere Form.
