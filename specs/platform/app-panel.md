# App-Panel — Spec     (ID-Präfix: PANEL)

> ⚠️ **ZIEL-ZUSTAND geändert durch RAT-31 (#1339), 2026-07-27/29 — KEIN ROUTER MEHR.**
> Der zentrale Router-/State-Hub ist gelöscht (`router.md` ENTFALLEN, E6f #1568).
> Damit gilt das ursprüngliche Panel-Routing-Modell **„Tap → Event an den Router →
> Router schaltet das Display"** nicht mehr. Ziel-Zustand (RAT-31 E6b/E6f, Ein-Gerät):
>
> - Das Panel ist die **linke Nav-Leiste der Heim-Shell** (`heim-shell.md` SHELL-3);
>   ein Kachel-Tap treibt das **rechte Buddy-Pane same-origin über `seiten/`** —
>   **ein Gerät = ein Ziel**, kein Router-Fanout, keine `panel_id→display_id`-
>   Indirektion (ROU-32 entfällt).
> - **Bleibt (re-home same-origin):** Kachel-Kuratierung — `tiles.json`,
>   `config.json`, `panel_id`, der PBE-4-Editor (#1400) — und das Ausliefern der
>   `/controller/app-panel/<id>/`-Assets über den seiten-Dienst (SREG-17, siehe
>   PANEL-2-Kasten).
> - **Entfällt ersatzlos:** die `display_id`-Bindung, `router_url` und der
>   Router-Proxy (`panel-registry.md` PREG-7/PREG-9) sowie jeder Verweis auf den
>   Router als Routing-Instanz (ROU-1/ROU-18/ROU-24).
>
> Wo diese Spec unten noch „Router" als Routing-/Serving-Instanz nennt, ist der
> Ziel-Zustand oben maßgeblich. Diese Spec bleibt als Anker erhalten.
> Governance: `decisions/RAT-31-wirbelsaeule-abriss.md`,
> `decisions/RAT-35-registry-frei-multi-geraet.md`, Epic #1339.
>
> Status: V1-Kern (RAT-31-umgeschrieben) · Refs #58 #1339

Ein zweiter Controller-Typ neben der Figuren-Erkennung
([`figuren-erkennung.md`](figuren-erkennung.md)): ein Bildschirm mit
Kacheln, je Kachel eine XBuddy-App-View. Eine Familie ohne physische
Figuren tippt eine Kachel → das rechte Buddy-Pane der Heim-Shell schaltet
same-origin auf die zugehörige View (RAT-31: **kein Router**, siehe ZIEL-Kopf).
Welche Kacheln ein Panel zeigt, steht modular in einer Datei neben dem
Controller-Code; das Panel selbst entscheidet **nichts** über Routing (PANEL-1).

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
Das Panel ist ein Kachel-Bildschirm; je Kachel eine App-View. Ein Tap auf eine
Kachel **treibt same-origin über den seiten-Dienst** das rechte Buddy-Pane der
Heim-Shell auf die zugehörige View (`heim-shell.md` SHELL-3; **ein Gerät = ein
Ziel**). Das Panel liefert nur **Semantik** — welche App/View die Kachel meint
(PANEL-7-Descriptor) — und **entscheidet niemals selbst** über die Ziel-Auflösung;
die Trennung „Controller liefert Semantik, das Routing macht der Dienst" bleibt
(analog Figuren-Erkennung).

**RAT-31 (#1339):** Die Routing-Instanz ist **nicht** mehr ein zentraler Router
(ROU-1 ENTFALLEN, `router.md`), sondern der same-origin-Ingest im seiten-Dienst.
Es gibt keine `panel_id→display_id`-Indirektion und keine Display-Auswahl mehr —
das eine Gerät ist das Ziel (siehe ZIEL-Kopf oben).

*Tickets:* #58 · Router-Entkopplung RAT-31 (#1339)

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

> **Serving-Owner Router→seiten (RAT-31 E6b, #1564):** Das Ausliefern von
> `/controller/app-panel/<id>/` (index.html + Assets, config/tiles/bearbeiten-
> Proxy) ist vom Router zum **seiten-Service** verlagert (SREG-17). Grund:
> `/shell/<id>` (heim-shell.md SHELL-1) und der Rail-Iframe
> `/controller/app-panel/<id>/` (SHELL-3) kommen dann same-origin aus **einem**
> Service. nginx routet `/controller/app-panel/` an `xbuddy_seiten` (vor dem
> allgemeinen `/controller/`-Router-Block). Der Serving-Vertrag (Proxy +
> LKG-Cache + Code-Default + sw.js-Substitution) ist unverändert 1:1
> übernommen. Der Router-seitige Serving-Code (ROU-24/ROU-27) lebt als toter
> Zwilling weiter, bis der Abriss #1568 ihn entfernt.

*Tickets:* #58 · Serving-Verlagerung #1564 (SREG-17)

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

### PANEL-13 — Silent-Audio-Prime als Side-Effect des Tile-Tap

Jeder Tap auf eine sichtbare Kachel (`tile_selected`, PANEL-6) startet
zusätzlich zum Routing-Event einen **silent `<audio>`-Prime** im selben
Panel-Tab: das Panel-PWA-Skript startet ein verstecktes `<audio>`-Element
mit einer kurzen, lautlosen Audio-Quelle (Stille-Loop) und ruft `play()`
innerhalb desselben Synchron-Pfads wie das Event-Dispatch — also unter
derselben Browser-User-Geste, die den Tap getragen hat.

**Sinn.** Das versteckt-laufende `<audio>`-Element verschafft dem
Panel-Tab eine durch User-Geste etablierte Sticky-Activation. Spätere
Audio-Source-Updates auf demselben Element (durch buddy-eigene
Mechaniken, z. B. PANEL-13 HSP-Audio-Stream) lösen Browser-Wiedergabe **ohne weitere
User-Geste** aus. Ohne diesen Prime blockieren Mobile-Browser ein neu
gestartetes `<audio>` mit Autoplay-Policy — empirisch bestätigt
2026-06-17 am Panel-Browser des Familien-Tablets.

**Trennung zu PANEL-1.** Der Prime entscheidet **nichts** über das
Routing: er liefert nur ein audio-fähiges DOM-Element, dessen Source
später von außen gesetzt werden kann. PANEL-1 (Panel entscheidet kein
Routing) und der DC-3-Renderer-only-Charakter des Display-Clients
bleiben unangetastet — das Panel ist nicht der Display-Client, und der
Prime ist ein browser-lokaler Side-Effect der bereits bestehenden
User-Geste, kein neuer Routing-Pfad.

**App-Agnostik.** Der Prime ist app-unabhängig: er wird für jeden
`tile_selected`-Tap geschaltet, nicht nur für audio-konsumierende Apps.
Ein Tile-Tap auf eine still-visuelle App-View lässt das Element auf
Stille stehen; ein nachfolgender Source-Push aus einer audio-fähigen
App findet dann ein bereits geprimtes Element vor. Diese App-Agnostik
verhindert, dass das Panel den App-Typ kennen muss (PANEL-1-konsistent).

**Robustheit.** Bei Tab-Cold-Start (nach Browser-Neustart oder OOM-Kill)
ist der Prime noch nicht aktiv — der erste Tile-Tap nach dem Cold-Start
liefert ihn nach. Das deckt den Familien-Alltag ab: jemand tippt täglich
mindestens einmal auf das Panel.

**Implementierungs-Detail.** Audio-Quelle des Stille-Loops und konkrete
DOM-Verortung (`<audio>` neben dem Kachel-Grid vs. eigenes Hidden-Element)
sind Implementierungsdetail und nicht Teil der Spec — die Spec verlangt
nur, dass nach jedem Tile-Tap ein bereit-stehendes `<audio>`-Element
vorhanden ist, dessen Source von späteren App-Mechaniken austauschbar
ist.

(RATIFIZIERT 2026-06-17 audio-output-routing → Setzung 7 „Sticky-
Activation via Kachel-Tap-Priming"; Empirie-Test 2026-06-17 „Autoplay-
Block auf Mobile-Browser bestätigt; Sticky-Activation reicht")

*Tickets:* (folgt im Bau-Track)

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
| `router_url` | (kein Default — Pflicht)         | `router_url`    | — (offen, OPEN-PANEL-C)            |

`source_id` ist die Identität dieser Panel-Instanz (z. B.
`app-panel:kueche`). `router_url` ist die Origin des Routers (Schema +
Host[:Port], **ohne Pfad**, analog FIG-23). *(#305)*

`display_id` ist **bewusst nicht** in `config.json` (Nic-Entscheid
2026-06-08 / #414, historisch: PANEL-11 zog sie per ROU-32 vom Router).
~~Der Panel-Code zieht beim Bootstrap `display_id` vom Router (ROU-32,
`GET /api/v1/router/panels/<source_id>`) und abonniert ROU-22-Display-Events.~~
**Entfallen durch RAT-31 E6f (#1568, T1601):** ROU-32 und der SSE-Strang
existieren nicht mehr; die Aktiv-Markierung läuft rein lokal (PANEL-11 SUPERSEDED).

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

**Serving via panel-Service (Welle 1):** `config.json` und `tiles.json`
kommen **nicht** aus dem Auslieferungs-Verzeichnis, sondern werden vom
Router aus dem panel-Service proxyt und gecacht (PREG-9, ROU-27). Der
Panel-Code lädt weiter `./config.json` und `./tiles.json` relativ zu
seiner eigenen URL — dass der Router diese Pfade an den panel-Service
weiterreicht, ist für die Seite transparent. Der panel-Service
(`xbuddy-panel`, :5041, PORT-2) ist die einzige Quelle der Wahrheit für
diese Instanz-Daten (PREG-4/PREG-14); manuelle Dateien neben dem
Panel-Code werden von ROU-27 überschattet und nicht mehr gelesen.

**Kopplung zum Router:** `source_id` muss mit dem `source_id`-Wert
eines `panels`-Eintrags der Routing-Tabelle (ROU-18) übereinstimmen,
sonst greift der Adapter (ROU-24) für diese Panel-Instanz nicht. Diese
Kopplung wird beim Start geprüft; eine Diskrepanz erscheint als
sichtbarer Fehler.

Die frühere zweite Konsistenz-Probe gegen `cfg.display_id` ist mit dem
Entscheid 2026-06-08 (#414) entfallen: der Panel-Code zieht `display_id`
pro Bootstrap aus ROU-32 und es gibt keinen lokalen Spiegel-Wert mehr,
gegen den geprüft werden müsste.

*Tickets:* #58

## 5. Kiosk-Absicherung

### PANEL-10 — Vollbild & Bildschirm wach halten (standalone-only)
Das Panel ist eine Controller-PWA und erfüllt damit die Pflichten aus
`conventions/pwa.md` (PWA-1 Pflicht-Dateien, PWA-2 Manifest-
Pflichtfelder inkl. `display: fullscreen`, PWA-3 Wake-Lock +
Fullscreen-API beim ersten User-Gesture, PWA-4 Selbstgenügsamkeit +
Controller-Config-Lade-Konvention) — analog DC-11/DC-16 (Display-
Client als zweiter PWA-Konsument) und FIG-24/FIG-26.

**Embedded-Ausnahme (SHELL-11):** Wird das Panel als Iframe in die
Heim-Shell eingebettet (`window.self !== window.top`), hängt es seinen
Eigen-Vollbild-Listener **nicht** an — die Shell besitzt dann den
Vollbild (SHELL-11). Standalone-Panel-Geräte (`window.self === window.top`)
behalten PANEL-10 unverändert. Umsetzung in
`controller/app-panel/app.js::attachFullscreenOnGesture`.

**Hinweis:** **App-Pinning** ist Familien-Onboarding-Aufgabe und kein
Code-Verhalten — wird in einem entsprechenden Onboarding-Schritt für
das Familien-Tablet eingerichtet (analog dem Display-Tablet). Die
Spec nennt das, fordert aber keinen Code dafür.

*Tickets:* #58

### PANEL-14 — Cache-Buster für App-Panel-Assets (build_id über den Router-Seam)
Änderungen an den App-Panel-Assets (`app.js`, `style.css`, `sw.js` u. a.)
müssen am Familien-Tablet **ohne manuellen Hard-Reload** sichtbar werden.
Ohne Cache-Buster hält der Telegram-/Kiosk-Browser alte Versionen und
Eltern sehen Iterationen nicht (Folge #1219). Das Panel folgt derselben
`build_id`-Linie wie die Mini-Apps (Präzedenz ESSEN-35 in
[`../buddies/essen.md`](../buddies/essen.md); SHELL-PWA-Cache-Versionierung
in [`heim-shell.md`](heim-shell.md)).

**`build_id`-Bildung (Runtime-Asset-Satz, kein Einzelpfad).** Der Router
bildet einen `build_id` aus den **mtimes des vollständigen cache-relevanten
Runtime-Satzes**, nicht nur aus `style.css`+`app.js`. Der Satz umfasst:
`app.js`, `style.css`, `sw.js`, `manifest.json`, `silent.mp3`,
`/controller/_shared/config.js`, `/display/_shared/design/tokens.css`.
Begründung des vollen Satzes: `config.js` und `tokens.css` werden von
`index.html` referenziert und vom Service-Worker precacht (E-PANEL-6,
`sw.js` STATIC_ASSETS) — bei Ableitung nur aus CSS/JS ändert sich ein
Token- oder Config-Asset, der `build_id` bleibt gleich und ein Stale-Asset
überlebt.

**HTML-Injektion über den bestehenden Seam.** Die Asset-URLs in `index.html`
tragen ein `?v=<build_id>` an **allen** cache-relevanten URLs. Die Injektion
läuft über den bereits vorhandenen Render-Seam `render_app_panel_index`
(PANEL-2; ersetzt dort schon `__PANEL_ID__`) — es entsteht **keine** zweite
Templating-Schicht.

**`sw.js`-Auslieferung mit Substitution + no-cache-Header.** Der Cache-Name
des Service-Workers wird **nicht mehr manuell gebumpt** (heute die
`CACHE_NAME`-Konstante in `sw.js`), sondern der Router liefert `sw.js` mit
einer `__BUILD_ID__`-Substitution aus. Die Auslieferung erfolgt als
Custom-Response mit `Cache-Control: no-cache, no-store, must-revalidate`
und `Content-Type: application/javascript; charset=utf-8` (analog den
ratifizierten PWA-Pfaden des seiten-Service). Ohne den no-cache-Header
hält der Browser die alte `sw.js`, es entsteht kein neuer Worker und der
neue Cache-Name greift nicht — die `?v=`-Injektion am HTML allein
invalidiert nur den HTTP-Cache, nicht den SW-Precache; **beide Schichten
sind nötig**.

Kein Convention-Hochzug: das App-Panel ist heute der **einzige**
Controller-Typ mit diesem `mtime→build_id→sw.js`-Bedarf (n=1,
CLAUDE.md §6, `conventions/README.md`). Sobald ein zweiter Controller-Typ
(z. B. Figuren-Erkennung) denselben Mechanismus braucht, gehört das Muster
nach `conventions/pwa.md` — nicht vorher.

*Tickets:* #1226

## 6. Aktive-Kachel-Markierung

### PANEL-11 — Aktive Kachel im Panel-UI optisch markieren

> ⚠️ **SUPERSEDED durch RAT-31 E6f (#1568) + T1601 (#1601), 2026-07-31.**
> Der Router-SSE-Strang (ROU-22, `GET /api/v1/displays/<id>/events`) und der
> ROU-32-Display-Lookup (`GET /api/v1/router/panels/<source_id>`) sind entfernt —
> `attachStream`, `makeStreamHandlers` und der 10s-Watchdog existieren nicht mehr
> im Code. Aktive Quelle der Markierung ist ausschließlich der **lokale Tap-Aktiv-Marker**
> (Shell-Flow-Zweig unten, `onTap`/`onClear`). Der Rest dieser Sektion ist
> historischer Anker. Governance: `decisions/RAT-31-wirbelsaeule-abriss.md`.

Wenn der User eine Kachel antippt und das zugeordnete Display den
entsprechenden Inhalt zeigt, wird **diese Kachel im Panel-UI optisch
markiert** — sichtbar von der Restmenge unterschieden
(Hintergrund-Hervorhebung oder Border). Die konkreten Design-Tokens
kommen im Impl-PR; die Spec verlangt nur „sichtbar unterscheidbar".

~~**Quelle der Wahrheit der Markierung (ENTFALLEN, RAT-31):** der Panel-Code zieht beim
Laden seine `display_id` vom Router (ROU-32:
`GET /api/v1/router/panels/<source_id>`, `<source_id>` aus
`config.json`, PANEL-8) und abonniert dann den **SSE-Zustands-Stream
genau dieses Displays** (ROU-22: `GET /api/v1/displays/<display_id>/events`).
Damit ist die für die Markierung genutzte `display_id` per Konstruktion
identisch mit der, an die der Router Tile-Taps für diese Panel-Instanz
routet — Drift ist nicht mehr möglich (Nic-Entscheid 2026-06-08 / #414).
Der Panel-Code vergleicht dann die im Stream gelieferte `payload.url`
mit den `{ app, view, query? }`-Werten seiner Kacheln.
Die Kachel, deren Konvention `/display/<app>/<view>[?<query>]` (vgl.
ROU-24) zur aktuellen Display-`payload.url` passt, ist aktiv markiert
— maximal eine Kachel gleichzeitig.~~

**Shell-Flow-Zweig (RAT-31, `ingest_url` gesetzt) — aktiv.** Läuft das Panel im
Shell-Flow (eingebettet, `?ingest_url=` gesetzt — vgl. SHELL-4/T1519), dann
trägt der **lokale Tap den Aktiv-Marker autoritativ**: `onTap`/`onClear`
setzen die Markierung optimistisch, und es gibt kein Router-SSE-Abo
(ROU-22) und keinen ROU-32-Display-Lookup mehr. Ein Gerät (RAT-31,
`decisions/RAT-31-wirbelsaeule-abriss.md`) ist die einzige Wahrheit über den
eigenen Anzeige-Zustand; ohne Fremd-Gerät gibt es keinen zu spiegelnden
externen Zustand.

- **`tile_selected`-Tap:** `updateActiveMarker(tile)` wird **optimistisch lokal**
  und **synchron** vor dem POST gesetzt (Refs #959). Der lokale Tap ist final
  (RAT-31, kein fremder Steuernder).
- **`panel_cleared`-Tap:** `updateActiveMarker(null)` wird optimistisch lokal
  und synchron vor dem POST gesetzt.

*Tickets:* #58, #1584, #1601

## 7. Layout (statisch, scroll-frei)

### PANEL-12 — Statisches, scroll-freies Kachel-Layout (Viewport-Fit)
Das Kachel-Grid füllt den **gesamten Viewport ohne vertikales Scrollen**: alle
sichtbaren Kacheln (PANEL-3/PANEL-4) plus die Aus-Kachel (PANEL-6) sind
gleichzeitig sichtbar, ohne dass gescrollt werden muss. Das Panel ist eine
statische Steuerfläche — eine Fernbedienung, kein Dokument.

**Wenn** das Panel mit M sichtbaren Kacheln (sichtbare `tiles.json`-Einträge
+ 1 Aus-Kachel) geladen wird, **dann** leitet die Seite Spalten- und Zeilenzahl
**zur Laufzeit aus M und dem Viewport-Seitenverhältnis ab** (kein hartcodierter
Spaltenwert) und legt das Grid so, dass `document.scrollHeight` den Viewport
(`clientHeight`) **nicht überschreitet**. Bei `resize` wird neu gerechnet.

**Safe-Area-Insets als Teil der Höhen-Invariante:** Auf Geräten mit Notch /
Home-Indicator (iPhone, neuere Android-Telefone) trägt `index.html` ein
`viewport-fit=cover`-Meta; die zur Grid-Höhe verwendete Größe ist deshalb
nicht das nackte `innerHeight`, sondern

    vpH = innerHeight − env(safe-area-inset-top) − env(safe-area-inset-bottom)

Dasselbe für `vpW` mit `left`/`right`-Insets, falls Landscape-Notch im Spiel.
Insets werden **abgezogen, nicht additiv padded** — sonst kehrt das Scrollen
zurück und PANEL-12 bricht. Auf Geräten ohne Notch sind alle Insets 0; die
Geometrie ist unverändert.

**Zielgeräte:** Querformat-Phone **und** Tablet (jeweils Landscape). Das
erweitert die bisherige reine Tablet-Nennung der PWA-Konvention; die
No-Scroll-Garantie gilt zuerst für das kleinere Gerät (Landscape-Phone).

**Kapazität & Fallback:** No-Scroll ist die **harte Invariante** — es wird
**nie** gescrollt. Die **Mindestbreite** (einzeilige, lesbare Labels, auch für
deutsche Langwörter wie „Morgenroutine") ist nachgeordnet: reicht der Viewport
nicht, um alle Kacheln scroll-frei **und** über Mindestbreite zu legen,
**schrumpfen die Kacheln** (Icon und Label skalieren mit; Labels dürfen
mehrzeilig brechen) — gescrollt wird nicht. Die komfortable Garantie
(einzeilige Labels) gilt für **mindestens 10 App-Kacheln + Aus** (= 11) auf
einem Landscape-Phone-Viewport.

**Reihenfolge bleibt:** Die Geometrie-Berechnung ändert **nur** Spalten- und
Zeilenzahl, nicht die Kachel-Reihenfolge (PANEL-3: Listen-Reihenfolge =
Anzeige-Reihenfolge) und nicht die Aus-als-letzte-Position (PANEL-6).

*Tickets:* #58, #375

## 8. Tests

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
  **Render-Pfad (Icon-Verhalten):** `makeTileElement` baut für jedes
  Element in `icons[]` ein `<img>` mit `src = iconBase + icons[i]`
  — geprüft per DOM-Stub-Test für ein einzelnes Icon und für das
  Kinder-Marker-Pattern (zwei Icons: `arasaac/32488.png` +
  `arasaac/2484.png`). Die erzeugten `img.src`-Werte müssen auf
  `/display/_shared/icons/<pfad>` enden (same-origin-Basis).
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
  **Render-Pfad (Icon-Verhalten):** `makeAusKachel` baut `img.src` aus
  `iconBase + AUS_ICON_PATH` (`arasaac/8252.png`) — geprüft per
  DOM-Stub-Test.
  **Icon-Fallback (onerror):** alle Tile-Icons und das Aus-Kachel-Icon
  tragen einen `onerror`-Handler, der das `<img>` aus dem Icon-Slot
  entfernt. Kein Broken-Image-Placeholder; Kachel und Label bleiben
  funktionsfähig — geprüft per DOM-Stub-Test (Ladefehler-Simulation
  durch direktes Aufrufen von `img.onerror`).
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
  sichtbare Fehler-Signalisierung). `display_id` ist seit dem Entscheid
  2026-06-08 (#414) NICHT mehr in `config.json` — der Panel-Code zieht
  sie pro Bootstrap vom Router über `GET /api/v1/router/panels/<source_id>`
  (ROU-32); ein 404 (Router kennt diese `source_id` nicht) erscheint als
  sichtbarer Fehler. Der stumme Default-Fallback bei fehlender/kaputter
  `config.json` bleibt erlaubt und ist konsistent zu FIG-23/ROU-19 —
  geprüft wird, dass beide Wege (sichtbarer Konsistenz-Fehler vs.
  stummer Datei-Fallback) sich nicht vermischen.
- PANEL-10 — Das PWA-Manifest deklariert `display: fullscreen`
  (Manifest-Test). `navigator.wakeLock.request('screen')` wird beim
  Laden aufgerufen; bei `visibilitychange` auf `visible` erneut.
  `requestFullscreen()` wird beim ersten Nutzer-Gesture versucht; ein
  Fehler dabei wirft den Code nicht ab.
- PANEL-11 — ~~Router-SSE-Probe (ROU-22/ROU-32, `attachStream`) — ENTFALLEN
  (RAT-31 E6f, T1601).~~ **Aktiver Test:** `onTap(tile)` ruft
  `updateActiveMarker(tile)` synchron VOR `sendEvent` (optimistisches lokales
  Update, Refs #959). `onClear()` ruft `updateActiveMarker(null)` synchron VOR
  `sendEvent`. `findActiveTile`-Logik matcht Kacheln korrekt gegen
  `/display/<app>/<view>[?<query>]`-URLs (Plain-URL, Query-URL, Multi-Segment,
  Null → kein Match).
- PANEL-12 — Bei Viewport 880×370 (Landscape-Phone) mit 11 Kacheln (10
  sichtbare + Aus) gilt `document.scrollHeight <= clientHeight` (kein
  vertikales Scrollen) und alle 11 Kacheln sind im DOM vorhanden; die Labels
  bleiben einzeilig. Bei Viewport 1280×800 (Tablet) mit 11 Kacheln ebenso
  kein Scroll. Die gewählte Spaltenzahl ist **nicht hartcodiert**: bei gleicher
  Kachelzahl, aber geändertem Viewport-Seitenverhältnis, ändert sich die
  Spaltenzahl. Übersteigt die Kachelzahl die scroll-freie Kapazität, schrumpfen
  die Kacheln unter die Mindestbreite, statt zu scrollen (`scrollHeight <=
  clientHeight` bleibt invariant).
  **Safe-Area-Probe:** mit simulierten Safe-Area-Insets (z. B. iPhone-Notch
  `safe-area-inset-top: 44px`, Home-Indicator `safe-area-inset-bottom: 34px`)
  bleibt `document.scrollHeight <= clientHeight` invariant — die Geometrie zieht
  die Insets von `vpH`/`vpW` ab statt sie additiv als Padding zu ergänzen.
- PANEL-13 — Ein simulierter `tile_selected`-Tap startet ein verstecktes
  `<audio>`-Element mit `play()` im selben Synchron-Pfad wie der
  Event-Dispatch (DOM-Stub-Test: nach dem Tap existiert ein `<audio>`-
  Element im DOM und `play()` wurde aufgerufen). Ein simuliertes
  Source-Update auf demselben Element wirft keinen Autoplay-Fehler
  (gemockter Browser meldet `play()`-Promise resolved). Bricht
  `play()` im Test (gemockter Autoplay-Block), bleibt die Seite
  funktionsfähig — der Test prüft, dass kein User-sichtbarer Crash
  entsteht (Robustheits-Pflicht analog PANEL-10-Wake-Lock-Fehler).
- PANEL-14 — Der Router rendert `index.html` mit `?v=<build_id>` an allen
  Runtime-Asset-URLs; im ausgelieferten HTML bleibt **kein** `__BUILD_ID__`-
  Token (Anker 1). Die ausgelieferte `sw.js` trägt einen `build_id`-
  abhängigen Cache-Namen und **kein** `__BUILD_ID__`-Token (Anker 2). Die
  `sw.js`-Antwort trägt den Header `Cache-Control: no-cache, no-store,
  must-revalidate` (Anker 3). Ein mtime-Wechsel an einem Asset des
  Runtime-Satzes (`/controller/_shared/config.js` **oder**
  `/display/_shared/design/tokens.css`) ändert den `build_id` und damit
  sowohl die `?v=`-Werte im HTML als auch den `sw.js`-Cache-Namen (Anker 4).

*Tickets:* #58, #375

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
- **OPEN-PANEL-C** — *Durch PREG-15 erfüllt (Welle 1):*
  `POST /api/v1/panels/` legt eine Panel-Instanz an und setzt
  `source_id`, `display_id` und `router_url` als Registry-Eintrag im
  panel-Service (PREG-15). Der manuelle Datei-Eingriff entfällt;
  Panel-Instanzen entstehen fortan über diese Schnittstelle. Der
  Eltern-Chat-Skill, der Panels per Telegram anlegt, ist Welle 2
  (OPEN-PREG-C in `specs/platform/panel-registry.md`).
- **OPEN-PANEL-D** — *Erfüllt:* Backoff-Werte des Event-Transports in
  PANEL-5 leben jetzt in der Event-Transport-Konvention
  `conventions/event-transport.md` (EVT-1/EVT-2) — eine eigene
  Tuning-Tabelle in `app-panel.md` ist damit nicht mehr nötig. Ein
  späterer Override-Pfad (Datei-Schlüssel je Controller) gehört in die
  Konvention, nicht in diese Spec.
- **OPEN-PANEL-E** — Lebenszyklus des Silent-Audio-Prime aus PANEL-13:
  Soll der Prime beim `panel_cleared`-Tap (Aus-Kachel) **gestoppt**,
  **stumm weiterlaufen** oder **bei jedem nächsten Tile-Tap neu
  ge-primed** werden? Setzung 7 des RATIFIZIERT-Files 2026-06-17 beschreibt
  nur den Start-Pfad (Kachel-Tap startet Prime), nicht das Stopp- oder
  Re-Prime-Verhalten. Im Bau-Track entscheidet das Browser-Verhalten am
  Live-Setup (Familien-Tablet) — wenn der erste Wechsel nach
  `panel_cleared` stockt, kippt das in eine eigene Klausel. Erst nach
  Messung formalisieren (kein antizipatives Setzen).

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

### E-PANEL-6 — App-Panel referenziert den Token-Strang (DTOK); Offline-Selbstgenügsamkeit weicht
*Datum:* 2026-06-07 (Ticket #375, Werft-Design-Upgrade)

Das App-Panel entstand **vor** den XBuddy-Design-Tokens (DTOK, #323) und trug
ein eigenes dunkles Theme mit hartcodierten Werten. Der Umbau (#375) macht es
DTOK-konform: die Seite **referenziert** `/display/_shared/design/tokens.css`
(same-origin, vom Router via ROU-30 serviert) statt eigener Farb-/Schrift-Werte
(DTOK-1/DTOK-3/DTOK-5).

Das kollidiert mit der PWA-Selbstgenügsamkeit (PWA-1/PWA-4: „keine externen
Asset-Quellen, alles im Verzeichnis"): der Token-Strang liegt cross-directory
und `@import`t Schrift von einem CDN. **Entscheidung (Nic, 2026-06-07):**
referenzieren ist richtig. Das App-Panel ist eine **inhärent online**
Steuerfläche — ohne Seiten-Verbindung kann es weder Kacheln routen (PANEL-1/5)
noch seinen Zustand ingest-en; „offline aber gestylt" ist ein Zustand
ohne Mehrwert. Verloren geht nur Offline-**Styling**-Robustheit, **nicht** die
PWA-Installierbarkeit (Manifest/sw.js/Fullscreen/HTTPS bleiben erhalten,
PWA-2/PWA-3). Die `sw.js`-Cache-Liste wird um die Token-CSS erweitert, damit der
gecachte Fall gestylt bleibt; fehlt die CDN-Schrift (WAN weg), greift der
System-Font-Fallback aus `--font-sans`.

**Offen für die Konventions-Ebene (an /berater-runde via Retro):** ob DTOK
formal auf offline-fähige Controller-PWAs ausgedehnt bzw. die PWA-1-
Selbstgenügsamkeit für referenzierte System-Assets relativiert wird. Diese
Entscheidung deckt nur das App-Panel ab, nicht die Konvention.
