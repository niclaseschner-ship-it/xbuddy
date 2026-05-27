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

## 3a. App-Panel-Adapter

### ROU-24 — App-Panel-Adapter
Der App-Panel-Adapter ist der zweite Controller-Adapter neben dem
Phone-Adapter (ROU-6). Er nimmt die zwei Event-Typen des
App-Panel-Controllers (siehe [`app-panel.md`](app-panel.md), PANEL-6):

| App-Panel-Event (PANEL-6) | Adapter-Verhalten |
|---|---|
| `tile_selected { app, view, query? }` | Bildet einen kanonischen Trigger und setzt den State (ROU-11) für die `display_id` aus dem `panels`-Eintrag der Routing-Tabelle (ROU-18). |
| `panel_cleared` | Session-Ende-Signal (ROU-11): das Display, dessen aktueller State die `source_id` dieser Panel-Instanz trägt, wird auf `null` gesetzt. |

**Routing per Konvention, nicht per Kachel-Eintrag.** Der Adapter
nutzt **nicht** das Descriptor-Matching von ROU-9. Stattdessen leitet er
die Payload-URL **per Konvention** aus dem Descriptor ab:

- Bei `tile_selected` ist `payload.url` = `/display/<app>/<view>` nach
  URL-2; ist `query` im Event gesetzt, wird sie als
  Query-String an die URL gehängt (`?<key>=<value>&…`,
  URL-Encoding nach Standard).
- `display_id` für das State-Update kommt aus dem `panels`-Abschnitt
  der `routing.json` (ROU-18), Schlüssel `source_id` — genau ein Display
  pro Panel-Instanz (E-PANEL-5). Findet der Adapter die Panel-Instanz
  dort nicht, wird wie bei einem nicht-gematchten Trigger im
  Routing-Kern verfahren (ROU-11, „Trigger ohne Match"): Event mit 2xx
  beantworten, eine Warnung loggen, keinen State ändern.

**Hardcode-frei.** Der Adapter führt **keine App-Liste**, kein `switch`
über App-Namen und keine Mapping-Tabelle `app → URL`. Eine neue App in
einem Panel ist allein eine neue Zeile in der `tiles.json` des Panels
(PANEL-3) — weder Router-Code noch `routing.json` müssen angefasst
werden. Dieses Konventions-Routing ist die Entscheidung E-ROU-8.

`payload` folgt ROU-13 (`{ "url": "<string>" }`); spätere Felder sind
reine Erweiterung. Der Trigger im internen State (ROU-10) trägt für
Panel-Events `descriptor = { app, view, query? }` — analog zum
Phone-Descriptor, mit den App-Panel-Feldern statt
`figure_id`/`bucket`.

ROU-1 bleibt gewahrt: das Panel entscheidet nichts, der Adapter
übersetzt und übergibt; der Routing-Kern setzt State.

*Tickets:* #58

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

Der Lookup liest `routing.json` **pro Aufruf frisch von Disk**
(Reload-on-Read, [`conventions/data-components.md`](../../conventions/data-components.md)
DCOMP-2) — Details unter ROU-18.

*Tickets:* #5, #24, #11

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
Dokumentierte Abweichung — zentral als Teil der Übersicht aller
URL-3a-Abweichungen in [`urls.md`](urls.md) (URL-3a) aufgelistet.

*Tickets:* #5, #24, #30

### ROU-21 — Direkt-Push an Display via CDP

> **Abgelöst (#30), entfernt (#102).** Die Display-Benachrichtigung läuft
> über den SSE-Zustands-Stream **ROU-22** — er erreicht auch Display-Geräte,
> die nicht am Pi hängen (Tablets); CDP erreichte nur lokales Chromium.
> Begründung: E-DC-1 in [`display-client.md`](display-client.md). Der
> CDP-Push-Code samt der Konfigurationswerte `cdp_target` und
> `cdp_idle_url` ist mit #102 aus dem Router entfernt; ältere `config.json`-
> Dateien mit diesen Schlüsseln werden beim Laden ignoriert und mit einem
> Log-Hinweis quittiert (kein Crash).

*Tickets:* #17, #102

### ROU-23 — GET /controller/&lt;app&gt;/&lt;asset&gt; — Auslieferung der Controller-PWA
`GET /controller/<app>/` und `GET /controller/<app>/<asset>` liefern die
Controller-PWA (siehe [`figuren-erkennung.md`](figuren-erkennung.md)) unter
einem zwei-segmentigen Pfad nach URL-3 aus — das erste Segment ist der
Slug der Controller-App (z. B. `figuren-erkennung`), das zweite das
Asset. Der Router ist hier nur Auslieferungsstelle der Statik; Verhalten
und Eigenschaften der PWA legt `figuren-erkennung.md` fest.

Anders als der Display-Client (ROU-20, eine inline gezogene Seite) ist
der Controller eine echte PWA — `sw.js`, `manifest.json` und Icons müssen
als **eigene Pfade mit ihrem korrekten Content-Type** ankommen, sonst
verweigert der Browser Service-Worker-Registrierung oder Manifest-Parse.
Acceptance-Kriterien (mit dem Default-App-Slug `figuren-erkennung`):

| Pfad | Antwort |
|---|---|
| `GET /controller/figuren-erkennung/` | 200, `text/html`, Inhalt aus `index.html` |
| `GET /controller/figuren-erkennung/sw.js` | 200, `application/javascript` |
| `GET /controller/figuren-erkennung/manifest.json` | 200, `application/manifest+json` |
| `GET /controller/figuren-erkennung/icon-192.png` | 200, `image/png` |
| `GET /controller/figuren-erkennung/icon-512.png` | 200, `image/png` |
| `GET /controller/figuren-erkennung/icon-maskable-512.png` | 200, `image/png` |
| `GET /controller/figuren-erkennung/figlib.js` | 200, `application/javascript` |
| `GET /controller/` (ohne App-Slug) | 404 — URL-3 verlangt zwei Segmente |
| `GET /controller/<anderer-slug>/...` | 404 — nur der konfigurierte App-Slug ist gültig |
| Pfad außerhalb des Controller-Wurzelverzeichnisses (Path-Traversal, z. B. `/controller/figuren-erkennung/../../router/main.py`) | 404 |
| Nicht existierendes Asset im Controller-Verzeichnis | 404 |

Das Wurzelverzeichnis ist konfigurierbar (`controller_dir`, ROU-15);
sein Basisname ist der gültige App-Slug im Pfad. Defaults zeigen auf
`controller/figuren-erkennung/` neben dem Router-Code — daher der
Default-App-Slug `figuren-erkennung`. Anfragen, die auflöst aus diesem
Wurzelverzeichnis ausbrechen würden, liefern 404 — kein Dateizugriff
jenseits der Wurzel.

Service-Worker-Scope: Da `sw.js` unter `/controller/<app>/sw.js` liegt,
kontrolliert die PWA per Default nur ihren eigenen App-Namensraum
`/controller/<app>/` — nicht den ganzen `/controller/`-Prefix. Das passt
zur Trennung in URL-3: Action-Endpoints anderer Sources (z. B.
`/controller/figure/place`) bleiben außerhalb des PWA-Caches.

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

**Heartbeat:** Solange der Stream offen ist und kein Zustands-Ereignis
ansteht, sendet der Router in regelmäßigem Abstand (≤ 30 s, Default
15 s) einen SSE-Kommentar (`: keepalive\n\n`). Das hat zwei Zwecke:

1. Der Stream sieht für Reverse-Proxies und Mobil-NAT-Boxen nicht idle
   aus — sie schließen ihn nicht stillschweigend wegen Idle-Timeout
   (vgl. `deploy/nginx/xbuddy-origin.conf`, `proxy_read_timeout 1h`).
2. Der Router-Generator erkennt verschwundene Clients zuverlässig
   (write-Fehler), räumt seine Subscription ab und hinterlässt keine
   Leiche.

Der Kommentar ist keine SSE-Nachricht (kein `data:`-Feld) — der Client
sieht ihn nicht als Inhalts-Ereignis. Verlässt sich der Client allein
auf den Standard-Reconnect des Browsers (DC-7), trägt dieser Heartbeat
die Garantie, dass eine offene Verbindung tatsächlich offen *bleibt*,
solange Netz und Router stehen.

> Hinweis (Deployment): Hinter einem Reverse-Proxy darf dieser
> Long-Lived-Stream nicht gepuffert werden, sonst erreichen die
> Ereignisse den Client nie. Die HTTPS-Origin schaltet das Puffern
> für diesen Pfad ab (`deploy/nginx/xbuddy-origin.conf`, #70).

*Tickets:* #30, #116

## 6. Konfiguration

### ROU-15 — Tuning-Werte (analog FIG-17)
Defaults stehen als Konstanten im Code. Sie können per
`config.json` im Router-Verzeichnis (siehe ROU-19) überschrieben werden.
Die Tabelle folgt der Konfigurations-Konvention CONFIG-2: jeder Wert hat
einen Default und einen Datei-Schlüssel in `config.json` (ROU-19). Der
Onboarding-Schritt, der einen Wert produktiv setzt, ist heute noch nicht
definiert — Router-Werte werden in V1 manuell beim Deployment befüllt;
ein Eltern-Chat-Schritt für Router-Setup ist ein offener Punkt (siehe
OPEN-ROU-C).

Dev-Override per ENV-Variable und CLI-Flag ist möglich (CONFIG-1:
ENV/CLI sind Dev-Werkzeug bzw. Test-Werkzeug, nicht produktive
Familien-Form) — Liste am Ende der Spec unter „Dev-Anhang". Priorität
bleibt **CLI > ENV > config.json > Defaults**.

| Name             | Default                                                     | Datei-Schlüssel  | gesetzt durch (Onboarding-Schritt) |
|------------------|-------------------------------------------------------------|------------------|------------------------------------|
| `listen_host`    | `127.0.0.1`                                                 | `listen_host`    | — (offen, OPEN-ROU-C)              |
| `listen_port`    | `5000`                                                      | `listen_port`    | — (offen, OPEN-ROU-C)              |
| `log_level`      | `INFO`                                                      | `log_level`      | — (offen, OPEN-ROU-C)              |
| `controller_dir` | `../controller/figuren-erkennung` (relativ zum Router-Code) | `controller_dir` | — (offen, OPEN-ROU-C)              |

Werte, die nur als Code-Konstante existieren — ohne Override-Pfad —
sind Spec-Verletzung (CLAUDE.md §6 Daten vs. Code).

*Tickets:* #5, #180

### ROU-16 — Lokaler Start
Der Router startet lokal per einem dokumentierten Kommando (siehe
README im Router-Verzeichnis, wird im Impl-PR angelegt). Kein
Daemon-/systemd-Setup im V1-Scope, kein Container.

Hör auf `listen_host:listen_port` (ROU-15).

*Tickets:* #5

### ROU-18 — Routing-Tabelle via `routing.json`
Die M:N-Tabelle (ROU-9) lebt als JSON-Datei `routing.json` neben dem
Router-Code (analog FIG-23 für die Phone-Seite). Format mit zwei
Abschnitten — `entries` für descriptor-basiertes Matching (ROU-9) und
`panels` für den App-Panel-Adapter (ROU-24, Konventions-Routing):

```json
{
  "entries": [
    {
      "source_id": "phone:test-1",
      "descriptor": { "figure_id": "gelbes-e", "bucket": 0 },
      "display_ids": ["default"],
      "payload": { "url": "https://buddy.local/scene/gelbes-e-0" }
    }
  ],
  "panels": {
    "app-panel:kueche": { "display_id": "default" }
  }
}
```

Der `panels`-Abschnitt ist eine Map `source_id` → `{ display_id: <string> }`
— **eine Zeile pro Panel-Instanz, nicht pro Kachel**, und genau **ein
Display pro Panel-Instanz** (E-PANEL-5; siehe auch PANEL-8). Wechselt ein
Panel auf ein anderes Display, ändert sich diese eine Zeile; das Hinzufügen
einer neuen Kachel ändert hier **nichts** (E-ROU-8, ROU-24). Wer zwei
Displays steuern will, betreibt **zwei Panel-Instanzen** mit eigener
`source_id` und eigener `tiles.json`/`config.json` (PANEL-3/PANEL-8) —
symmetrisch zum Muster „mehrere Familien-Hubs = mehrere Instanzen". Fehlt
der `panels`-Abschnitt oder fehlt eine Panel-`source_id` darin, verhält
sich der App-Panel-Adapter wie bei einem nicht-gematchten Trigger
(ROU-11/ROU-24): 2xx, Warnung, kein State-Update.

- **Fehlerfälle:** Datei fehlt oder nicht parsebar → der Router startet
  mit leerer Tabelle und protokolliert eine Warnung. Ein laufender
  Router darf nicht crashen, weil die Datei fehlt — das macht ihn auch
  als Entwicklungs-Werkzeug brauchbar, das man ohne fertige Tabelle
  hochfährt.
- **Selbsttragend:** Datei liegt im Router-Verzeichnis und wird mit
  ausgeliefert. Pro Instanz separat verwaltet — `routing.json` ist per
  `.gitignore` aus dem Repo ausgeschlossen, `routing.example.json`
  dokumentiert das Format.
- **Kopplung zur Controller-Instanz:** `source_id` muss mit dem
  `source_id`-Wert in der Controller-Instanz-Konfiguration (FIG-23)
  übereinstimmen — sonst findet `lookup` (ROU-9) für die Events dieser
  Instanz keinen Eintrag.
- **Reload-on-Read** ([`conventions/data-components.md`](../../conventions/data-components.md)
  DCOMP-2): Lookups (descriptor-Match nach ROU-9, panels-Lookup nach
  ROU-24, `known`-Prüfung für `GET /api/v1/displays/<id>/state` und
  `/events`) lesen `routing.json` **pro Aufruf frisch von Disk**.
  Schreibt ein Skill die Datei (Cross-Service-Write, EC-21), wird der
  neue Stand vom nächsten Lookup sofort gesehen — ohne Service-Restart
  und ohne expliziten Reload-Trigger. Der zuletzt erfolgreich geladene
  Stand wird als Snapshot gehalten und nur dann als Fallback verwendet,
  wenn ein einzelner Read scheitert (Datei kurz weg, atomares Replace-
  Race, kaputtes JSON) — gleicher atomarer Geist wie der Admin-Reload
  (E-RELOAD-1).
- **Admin-Reload** (`POST /api/v1/router/admin/reload`, #140): bleibt
  bestehen, ist aber **nicht mehr nötig**, damit Skill-Schreibvorgänge
  sichtbar werden — das übernimmt Reload-on-Read. Der Endpoint bleibt
  nützlich als expliziter, loggbarer Reload-Marker (Skill-Service-
  Reload-Pattern, EC-21) und aktualisiert den Snapshot-Cache.

*Tickets:* #5, #24, #72, #11

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
  `panels`-Abschnitt fehlt → App-Panel-Adapter behandelt jedes
  `tile_selected` wie einen unbekannten Trigger (2xx, kein State).
- ROU-23 — `/controller/` liefert die PWA-Statik mit korrekten
  Content-Types; Path-Traversal-Anfragen werden mit 404 abgewiesen.
- ROU-24 — App-Panel-Adapter: `tile_selected { app, view }` setzt
  State des Displays aus dem `panels`-Eintrag mit
  `payload.url = /display/<app>/<view>`; `tile_selected` mit
  `query` hängt den Query-String korrekt an die URL; `panel_cleared`
  setzt State des Displays mit dieser `source_id` auf `null`;
  Panel-`source_id` ohne `panels`-Eintrag wird wie ein unbekannter
  Trigger behandelt (2xx, Warnung, kein State).

*Tickets:* #5, #24, #58

---

## Offene Punkte

- **OPEN-ROU-B** — Wo lebt die Routing-Tabelle langfristig? V1 als
  JSON-Datei (ROU-18); V2 als Routing-DB (SQLite) gemäß
  brainstorm-Architektur; V3 ggf. zentraler Figuren-Registry-Service
  (vgl. OPEN-FIG-B). Keine V1-Entscheidung nötig — Kontext für
  Folge-Tickets.
- **OPEN-ROU-C** — Onboarding-Schritt für Router-Setup. Die
  CONFIG-2-Tabelle in ROU-15 hat heute keine Onboarding-Schritte für
  `listen_host`, `listen_port`, `log_level` und `controller_dir` —
  Router werden in V1 manuell beim Deployment befüllt (vgl. die
  systemd-Vorlage `router/router.service`, SVC-2). Sobald der Router
  über den Eltern-Chat eingerichtet werden kann (analog der
  Funktions-Spec `familie-anlegen.md`, vgl. das schwester-Ticket
  Eltern-Chat-Skill „Panel-Tablet einrichten" #183), bekommt jede
  Zeile der ROU-15-Tabelle einen konkreten Schritt-Namen.

---

## Dev-Anhang — ENV-Variable und CLI-Flag (Dev-Override)

Nach CONFIG-1 sind ENV-Variablen ein **Dev-Override** und CLI-Flags ein
**Test-Werkzeug**, nicht die produktive Familien-Form. Die folgenden
Overrides überschreiben für den laufenden Router-Prozess die Werte aus
`config.json` (ROU-19) bzw. die Code-Defaults. ENV-Namen folgen der
Konvention `<COMPONENT>_<KEY>` (CONFIG-1).

| Datei-Schlüssel  | ENV                       | CLI                |
|------------------|---------------------------|--------------------|
| `listen_host`    | `ROUTER_LISTEN_HOST`      | `--host`           |
| `listen_port`    | `ROUTER_LISTEN_PORT`      | `--port`           |
| `log_level`      | `ROUTER_LOG_LEVEL`        | `--log-level`      |
| `controller_dir` | `ROUTER_CONTROLLER_DIR`   | `--controller-dir` |

Priorität: **CLI > ENV > config.json > Defaults**.

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

### E-ROU-8 — App-Panel: Routing per Konvention, nicht per Kachel
*Datum:* 2026-05-25 (Ticket #58)

Frühe Variante: Jede Kachel eines App-Panels ist ein vollständiger
Eintrag in `routing.json` — analog zum descriptor-basierten Matching
der Figuren-Erkennung (ROU-9). **Verworfen** aus zwei Gründen:

1. **Doppelpflege Controller-Konfig ⇄ Router-Konfig.** Eine neue Kachel
   müsste sowohl in der `tiles.json` des Panels (PANEL-3, UI-Wahrheit)
   als auch in der `routing.json` des Routers (Routing-Wahrheit)
   gepflegt werden. Der spätere Schreiber aus OPEN-PANEL-A (Eltern-Chat
   schreibt Kacheln) müsste damit zusätzlich in die Router-Konfiguration
   schreiben — eine zweite, technisch sensitivere Datei.
2. **Der Descriptor `{ app, view }` (E-PANEL-1) ist bereits fast die
   Ziel-URL** nach URL-2. Der Adapter kann sie per Konvention
   zusammensetzen, ohne dass irgendwo eine zweite Tabelle
   `(app, view) → URL` gepflegt wird.

Stattdessen: Der App-Panel-Adapter (ROU-24) leitet die Payload-URL
**per Konvention** aus dem Descriptor ab; `routing.json` hält im
`panels`-Abschnitt nur **eine Zeile pro Panel-Instanz**:
`source_id → { display_id }` (Singular, ein Display pro Panel-Instanz,
E-PANEL-5). ROU-1 bleibt gewahrt — der Router
(über seinen Adapter) entscheidet das Routing, das Panel niemals selbst.

`tiles.json` ist damit **alleinige Wahrheit der Kacheln**; Änderungen
an Apps und Views eines Panels passieren ohne Eingriff in
`routing.json` oder Router-Code. Die Router-Konfiguration ändert sich
nur, wenn ein Panel installiert, umgezogen oder entfernt wird.

Folgewirkung: Der App-Panel-Adapter ist **hardcode-frei** — keine
App-Liste, kein `switch` über App-Namen (siehe ROU-24).
