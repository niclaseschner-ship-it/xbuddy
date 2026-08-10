# Router — Spec     (ID-Präfix: ROU)

> ⚠️ **ENTFALLEN durch RAT-31 E6f (#1568), 2026-07-29.**
> `router/` ist gelöscht. Es gibt keinen zentralen Routing-/State-Hub-Prozess
> mehr — das Heim-Display ist fest ein Gerät (Heim-Shell PWA, `heim-shell.md`),
> die verbleibenden Router-Funktionen (Icon-Suche ROU-31, /display/_shared/
> ROU-26/ROU-30, /controller/_shared/ ROU-23, App-Panel-Serving) sind in den
> Seiten-Registry-Dienst verlagert (`seiten-registry.md`, RAT-31 E6b/E6f-A/B).
> Die nginx-Origin hat keinen `xbuddy_router`-Upstream und keine allgemeinen
> /display/-, /controller/-, /api/v1/-Fallbacks mehr.
> Diese Spec bleibt als historischer Anker erhalten.
> Governance: `decisions/RAT-31-wirbelsaeule-abriss.md`, Epic #1339.
>
> Status: V1 (ENTFALLEN) · Refs #5 #1568

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
> **Serving verlagert nach seiten (RAT-31 E6b, #1564):** Das **Ausliefern** der
> App-Panel-Views (`GET /controller/app-panel/<id>/` — index.html + Assets +
> config/tiles/bearbeiten-Proxy) ist zum seiten-Service verlagert
> (seiten-registry.md SREG-17, app-panel.md PANEL-2). nginx routet
> `/controller/app-panel/` an `xbuddy_seiten`. Der **Event-Adapter** (die Tabelle
> unten: `tile_selected`/`panel_cleared` → State-Setzen) bleibt Router-Aufgabe —
> nur das HTTP-Serving zieht um. Der Router-seitige Serving-Code
> (`app_panel_index_*`/`app_panel_asset` in `router/main.py`) lebt als **toter
> Zwilling** weiter, bis der Abriss #1568 ihn entfernt; er wird nicht mehr
> erreicht (nginx-Split greift davor).

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

**Trailing-Slash und 301-Redirect** (analog Display-Pattern, Refs #516):

| Pfad | Antwort |
|---|---|
| `GET /controller/app-panel/<panel_id>/` | 200, `text/html`, Panel-PWA mit inline gezogenem `panellib.js` |
| `GET /controller/app-panel/<panel_id>` (no-slash) | 301 → `GET /controller/app-panel/<panel_id>/` |

Der 301-Redirect auf die Slash-Form ist notwendig, weil die Panel-PWA relative
Pfade enthält (`./manifest.json`, `./icon-*.png`). Ohne Trailing-Slash resolvt
der Browser `./` auf den Parent-Pfad (`/controller/app-panel/`) statt auf
`/controller/app-panel/<panel_id>/` — alle Asset-Requests landen auf 404. Der
Redirect entspricht dem HTTP-Standard für Directory-vs-File-Disambiguation und
ist identisch zum Display-Client-Pattern (ROU-20).

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
| `GET /controller/_shared/<asset>` | 200 mit Content-Type aus `controller/_shared/` — PWA-übergreifender Helper-Pfad (`conventions/pwa.md` PWA-4) |
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
folgt `conventions/config.md` **CONFIG-5**.

| Name             | Default                                                     | Datei-Schlüssel  | gesetzt durch (Onboarding-Schritt) |
|------------------|-------------------------------------------------------------|------------------|------------------------------------|
| `listen_host`    | `127.0.0.1`                                                 | `listen_host`    | — (offen, OPEN-ROU-C)              |
| `listen_port`    | `5000`                                                      | `listen_port`    | — (offen, OPEN-ROU-C)              |
| `log_level`      | `INFO`                                                      | `log_level`      | — (offen, OPEN-ROU-C)              |
| `controller_dir` | `../controller/figuren-erkennung` (relativ zum Router-Code) | `controller_dir` | — (offen, OPEN-ROU-C)              |
| `icon_root`      | `/home/buddy/apps/icons/` (ICONS-2)                         | `icon_root`      | — (offen, OPEN-ROU-C)              |
| `panel_service_url` | `http://127.0.0.1:5041` (leer = Default, PORT-2; ROU-27) | `panel_service_url` | — (offen, OPEN-ROU-C)           |
| `geraete_url`    | `http://127.0.0.1:5040` (leer = Default, GER PORT-2; ROU-29) | `geraete_url`    | — (offen, OPEN-ROU-C)              |
| `routing_datei`  | `router/routing.json` (Code-Fallback; Live-Ort nach SVC-5: `xbuddy-data/router/routing.json`, ROU-18) | — (kein `config.json`-Schlüssel; ein routing-Pfad in der eigenen Datei wäre rekursiv) | Installer / Unit-Datei (SVC-5) |

Override-Pfade (Dev-Anhang): `panel_service_url` via ENV
`ROUTER_PANEL_SERVICE_URL` / CLI `--panel-service-url`; `geraete_url` via ENV
`ROUTER_GERAETE_URL` / CLI `--geraete-url`; `routing_datei` via ENV
`ROUTER_ROUTING_FILE` / CLI `--routing`.

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
- **Selbsttragend:** Pro Instanz separat verwaltet. Pfad und
  Override-Wege folgen ROU-15 (Live-Ort nach SVC-5 außerhalb des
  Checkouts). `router/routing.json` im Repo ist per `.gitignore`
  ausgeschlossen, `routing.example.json` dokumentiert das Format.
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
  (E-RELOAD-1 / ROU-25).
- **Admin-Reload** (`POST /api/v1/router/admin/reload`, #140): bleibt
  bestehen, ist aber **nicht mehr nötig**, damit Skill-Schreibvorgänge
  sichtbar werden — das übernimmt Reload-on-Read. Der Endpoint bleibt
  nützlich als expliziter, loggbarer Reload-Marker (Skill-Service-
  Reload-Pattern, EC-21) und aktualisiert den Snapshot-Cache.

*Tickets:* #5, #24, #72, #11

### ROU-19 — `config.json` für Tuning-Werte
Analog FIG-23: optionale Datei `config.json` im Router-Verzeichnis,
deren Werte die Code-Defaults überschreiben. Felder gemäß ROU-15.
Verhalten bei fehlender oder kaputter Datei folgt
`conventions/config.md` CONFIG-4 (Defaults + Warnung, Prozess startet
weiter) — Python: `logging.warning`.

*Tickets:* #5

### ROU-25 — E-RELOAD-1: Atomarer Reload-Geist
Der Reload-Pfad (Admin-Reload nach ROU-18, Reload-on-Read als Fallback
nach DCOMP-2) ist **atomar**: solange Datei-Read oder JSON-Parse einer
geladenen Datei (`routing.json`) scheitern, bleibt der zuletzt
erfolgreich geladene Stand unverändert in Kraft, und der Router
beantwortet Lookups (ROU-9, ROU-22, ROU-24) weiter aus diesem Snapshot.
Übernommen wird erst nach erfolgreich vollständigem Parse — ein halb
geschriebenes oder kaputtes JSON darf weder `routing_entries` noch
`panels`/`known_displays` verfälschen.

Dieselbe Eigenschaft trägt der Anker-Name **E-RELOAD-1**, der heute
schon in Router-Code (`router/main.py`) und in benachbarten
Komponenten zitiert wird, die denselben Geist umsetzen (z. B. der
Plan-Buddy beim Reload von `plan/plan.json`, vgl. `plan/main.py`). Die
allgemeine Verortung als Bauregel für alle Daten-Komponenten ist Sache
einer eigenen Konvention (DCOMP-3, eigenes Ticket); bis dahin definiert
diese Stelle die Anforderung im Router-Kontext, und andere Komponenten
verweisen darauf, statt eigene Anker zu erfinden.

*Tickets:* #140

### ROU-26 — GET /display/_shared/icons/&lt;asset&gt; — geteilte Display-Assets

> **Serving verlagert nach seiten (RAT-31 E6f-B, #1586):** Das Ausliefern
> der Icon-Bibliothek unter `/display/_shared/icons/` ist zum seiten-Service
> verlagert (seiten-registry.md SREG-17, nginx-Block spezifisch vor dem
> allgemeinen `/display/`→Router-Block — URL-14). Der Router-seitige
> Serving-Code (`_send_icon_asset` / `display_shared_icon` in
> `router/main.py`) lebt als **toter Zwilling** weiter, bis der Abriss
> #1568 ihn entfernt; er wird nicht mehr erreicht (nginx-Split greift davor).

`GET /display/_shared/icons/<source>/<id>.<ext>` liefert die zentrale
Icon-Bibliothek (ARASAAC-Piktogramme, siehe
[`icons.md`](icons.md) ICONS-1..6) read-only aus der **icon-root** aus —
ein **Zwilling** zur Controller-Helper-Auslieferung `/controller/_shared/`
(ROU-23). Das Segment `_shared` ist der in
[`../../conventions/urls.md`](../../conventions/urls.md) URL-16 definierte
Namensraum für geteilte Display-Assets, die keinem einzelnen Buddy gehören.

Anders als `/controller/_shared/` (Helper-**Code** im Repo) zeigt dieser
Pfad auf die **icon-root** — Per-Instanz-Daten außerhalb des Repos
(ICONS-2, Default `/home/buddy/apps/icons/`). Der **seiten-Service** liefert
sie aus, statt nginx einen statischen `alias` zu geben: der Prozess läuft
als User `buddy` und liest die icon-root problemlos, während ein nginx-`alias`
(nginx = `www-data`) an der `0700`-Home-Permission scheiterte und 404 lieferte
(#135). Auslieferung wie ROU-23: `send_from_directory` mit explizitem
Content-Type und Defense-in-Depth-Path-Traversal-Schutz (werkzeug `safe_join`
+ `realpath`-Check gegen die aufgelöste Wurzel).

Acceptance-Kriterien:

| Pfad | Antwort |
|---|---|
| `GET /display/_shared/icons/arasaac/<id>.png` | 200, `image/png`, Inhalt aus `<icon-root>/arasaac/<id>.png` |
| Nicht existierendes Asset in der icon-root | 404 |
| Path-Traversal (z. B. `/display/_shared/icons/../../router/main.py`) | 404 — kein Dateizugriff jenseits der Wurzel |

Die icon-root ist konfigurierbar (`icon_root`, ROU-15); Default zeigt auf
`/home/buddy/apps/icons/` (ICONS-2). In der Origin-Routing-Tabelle
([`../../conventions/urls.md`](../../conventions/urls.md) URL-14) fällt
`/display/_shared/icons/` an den allgemeinen `/display/`→Router-Eintrag —
kein eigener statischer nginx-Block mehr.

*Tickets:* #135

### ROU-31 — GET /api/v1/icons/suche — Stichwort-Suche über den lokalen Icon-Cache

> **Serving verlagert nach seiten (RAT-31 E6f-B, #1586):** `GET /api/v1/icons/suche`
> ist zum seiten-Service verlagert (nginx exakter Match `= /api/v1/icons/suche`
> → `xbuddy_seiten`, spezifisch vor dem allgemeinen `/api/v1/`-Block — URL-14).
> Der Router-seitige Code (`icons_suche` / `_load_pictogram_cache` / `_score_match`
> in `router/main.py`) lebt als **toter Zwilling** weiter, bis der Abriss
> #1568 ihn entfernt.

`GET /api/v1/icons/suche?q=<stichwort>&max=<n>` durchsucht den lokalen
`pictogram_cache.json` (Wort→ID) in der icon-root und liefert JSON-Kandidaten —
das Verhalten (Matching, ID-Dedup, nur lokal vorhandene PNGs, `max`-Grenze, kein
Re-Fetch) ist in [`icons.md`](icons.md) **ICONS-7** definiert. Der **seiten-Service**
ist der Host, weil er die icon-root ohnehin besitzt (ROU-26-Zwilling); kein eigener
Dienst. Lesen mit demselben Path-/Wurzel-Schutz wie ROU-26 (kein Zugriff jenseits
der icon-root).

Acceptance-Kriterien:

| Pfad | Antwort |
|---|---|
| `GET /api/v1/icons/suche?q=hund` | 200, JSON-Liste `[{id,url}]` — nur IDs mit lokalem PNG |
| `GET /api/v1/icons/suche?q=<ohne-treffer>` | 200, leere Liste `[]` (kein Fehler) |
| `GET /api/v1/icons/suche` (kein `q`) | 400 |
| `GET /api/v1/icons/suche?q=hund` (kein `max`) | 200, höchstens 3 Treffer (Default, ICONS-7) |
| `GET /api/v1/icons/suche?q=hund&max=999999` | 200, höchstens 50 Treffer (Klemme, ICONS-7) |
| `GET /api/v1/icons/suche?q=hund&max=abc` | 200, höchstens 3 Treffer (Nicht-numerisch → Default, ICONS-7) |

*Tickets:* #390, #407, #408

### ROU-32 — GET /api/v1/router/panels/&lt;source_id&gt; — Panel→Display-Lookup

`GET /api/v1/router/panels/<source_id>` liefert die `display_id`-Zuordnung einer
Panel-Instanz aus dem `panels`-Abschnitt der `routing.json` (ROU-18). Antwort:
JSON `{"display_id": "<id>"}`. Unbekannte `source_id` → 404.

Der Router ist die **EINE Wahrheit** für die Panel→Display-Zuordnung — die
`display_id` darf NICHT in der Panel-`config.json` gespiegelt werden (Nic-Entscheid
2026-06-08 / #414; PANEL-8 entsprechend geschärft). Der Panel-Code zieht
`display_id` per Bootstrap-Lookup und abonniert genau diesen Display-Stream
(PANEL-11 → ROU-22) — Drift zwischen „Tile-Tap-Ziel" (ROU-24-Adapter) und
„Stream-Subscription" ist damit per Konstruktion unmöglich.

Endpoint-Naht zum panel-Service: `/api/v1/router/panels/` (Router-Namespace) ist
bewusst getrennt von `/api/v1/panels/` (panel-Service / PREG-13/PREG-15) —
Router zeigt nur die `routing.json`-Sicht, panel-Service zeigt die
Panel-Registry-Sicht. Keine Verwechslung möglich.

Acceptance-Kriterien:

| Pfad | Antwort |
|---|---|
| `GET /api/v1/router/panels/app-panel:kueche` (eingetragen in `panels`) | 200, `{"display_id": "<id>"}` |
| `GET /api/v1/router/panels/app-panel:unbekannt` (nicht eingetragen) | 404 |
| `GET /api/v1/router/panels/` (kein `<source_id>`) | 404 (kein List-Endpoint) |

Read-only, keine Schreibwirkung. Auth wie ROU-22 (Heimnetz-Grenze).

*Tickets:* #414

### ROU-30 — GET /display/_shared/design/&lt;asset&gt; — geteilter Design-Token-Strang

`GET /display/_shared/design/<asset>` liefert den geteilten Design-Token-Strang
(`display/_shared/design/tokens.css`, Konvention
[`../../conventions/design-tokens.md`](../../conventions/design-tokens.md)
DTOK-1/DTOK-2) read-only aus — ein **Zwilling** zur Controller-Helper-Auslieferung
`/controller/_shared/` (ROU-23). Das Segment `_shared` ist der in
[`../../conventions/urls.md`](../../conventions/urls.md) URL-16 definierte
Namensraum für geteilte Display-Assets, die keinem einzelnen Buddy gehören.

Anders als `/display/_shared/icons/` (ROU-26), das auf die **icon-root** als
Per-Instanz-Daten **außerhalb** des Repos zeigt, liegt der Token-Strang **im
Repo**: Design-Tokens sind die Marke — bei allen Familien identisch und mit dem
Code versioniert, kein manueller Pro-Pi-Schritt, keine Divergenz (Nic-Entscheid
2026-06-05). Der Router serviert daher aus dem festen In-Repo-Verzeichnis
`display/_shared/design/` (Pfad relativ zu `router/main.py`), genau wie
`/controller/_shared/` aus `controller/_shared/` (ROU-23) — keine Config-Wurzel.
Auslieferung wie ROU-23: `send_from_directory` mit explizitem Content-Type
(`.css` → `text/css`) und Defense-in-Depth-Path-Traversal-Schutz (werkzeug
`safe_join` + `realpath`-Check gegen die aufgelöste Wurzel).

Acceptance-Kriterien:

| Pfad | Antwort |
|---|---|
| `GET /display/_shared/design/tokens.css` | 200, `text/css`, Inhalt aus `display/_shared/design/tokens.css` |
| Nicht existierendes Asset im Verzeichnis | 404 |
| Path-Traversal (z. B. `/display/_shared/design/../../router/main.py`) | 404 — kein Dateizugriff jenseits der Wurzel |

In der Origin-Routing-Tabelle
([`../../conventions/urls.md`](../../conventions/urls.md) URL-14) fällt
`/display/_shared/design/` — wie `/display/_shared/icons/` — an den allgemeinen
`/display/`→Router-Eintrag; kein eigener statischer nginx-Block.

*Tickets:* #323

### ROU-27 — Proxy und Last-Known-Good-Cache für das Panel-Instanz-Serving
> **Verlagert nach seiten (RAT-31 E6b, #1564):** Dieser Proxy- + LKG-Cache-
> Mechanismus ist 1:1 in den seiten-Service übernommen (seiten-registry.md
> SREG-17) und wird dort produktiv ausgeführt. Der hier beschriebene Router-Code
> lebt als **toter Zwilling** weiter, bis der Abriss #1568 ihn entfernt — nach
> dem nginx-Split (`/controller/app-panel/` → `xbuddy_seiten`) erreicht ihn kein
> Request mehr. Das beschriebene **Verhalten** (Proxy, LKG-Cache, Code-Default,
> PBE-1/2 bearbeiten-Passthrough) gilt unverändert weiter, nur der ausführende
> Service wechselt.

Der Router proxyt die beiden instanz-spezifischen Datendateien an den
panel-Service (`xbuddy-panel`, PORT-2 :5041), statt sie aus dem
Auslieferungs-Verzeichnis zu lesen (Spiegel zu PREG-9):

- `GET /controller/app-panel/<id>/config.json`
  → `GET /api/v1/panels/<id>/config.json` am panel-Service
- `GET /controller/app-panel/<id>/tiles.json`
  → `GET /api/v1/panels/<id>/tiles.json` am panel-Service

`<id>` (= `panel_id`) ist dabei load-bearing: er wählt die Instanz
(PREG-2). Der Panel-Code bleibt unverändert — er lädt weiter
`./config.json` und `./tiles.json` relativ zu seiner eigenen URL;
dass der Router diese zwei Pfade weiterreicht, ist für die Seite
transparent.

**Last-Known-Good-Cache (Härtung Welle 1):** Der Router hält die
zuletzt erfolgreich vom panel-Service geholte `config.json`/`tiles.json`
je `panel_id` als Snapshot und serviert diesen Snapshot, wenn der
panel-Service vorübergehend nicht erreichbar ist oder fehlerhaft
antwortet — gleicher Geist wie ROU-25 / DCOMP-3 (E-RELOAD-1). Fehlt
auch der Snapshot (Service war seit Router-Start nie erreichbar), fällt
die Seite auf ihre Code-Defaults zurück (PANEL-8, stiller Fallback) —
kein Crash. Die genaue Cache-Invalidierungs-Mechanik (upstream-first mit
Fallback oder aktive Kante) ist OPEN-PREG-F; PREG-10/ROU-28 legen die
Sicherheits-Invariante fest.

*Tests:* ROU-17 Mindest-Abdeckung für dieses Requirement: #58

*Tickets:* #58

### ROU-34 — Proxy für die Panel-Editor-Seite (statische Assets, ohne LKG/Default)
Der Router proxyt zusätzlich die **Editor-Seite einer Panel-Instanz** und
ihre statischen Assets an den panel-Service:

- `GET /controller/app-panel/<id>/bearbeiten` → panel-Service
- `GET /controller/app-panel/<id>/bearbeiten.js` → panel-Service
- `GET /controller/app-panel/<id>/bearbeiten.css` → panel-Service

Dieses Verhalten ist **bewusst anders** als ROU-27 (Daten-Proxy für
`config.json`/`tiles.json`):

- **Kein Last-Known-Good-Cache.** Statische HTML-/JS-/CSS-Assets sind
  Code, der bei Service-Ausfall nicht aus einem Snapshot rekonstruiert
  werden soll — eine veraltete Editor-Seite würde die Eltern in falsche
  Annahmen über den aktuellen Editor-Stand führen.
- **Kein Code-Default-Fallback.** Fehlt der panel-Service, liefert der
  Router den vom Upstream gekommenen Status (404/5xx) **direkt durch**
  — die Editor-Seite ist Eltern-Tool (PBE-3), kein Display-Render-Pfad,
  und Eltern erkennen einen Service-Ausfall lieber direkt als hinter
  einem Cache versteckt.
- **Cache-Invalidierungs-Naht** existiert für diesen Pfad nicht — es
  gibt keinen Cache, der invalidiert werden müsste.

Begründung der Trennung von ROU-27: die zwei Pfade haben unterschiedliche
Verfügbarkeits-Erwartungen. ROU-27 dient dem Display-Render (das soll
selbst bei Service-Ausfall etwas zeigen, daher LKG); ROU-34 dient der
Eltern-Editor-Bedienung (die soll bei Service-Ausfall den Ausfall
zeigen, daher direkt-durchgereicht).

*Tests:* ROU-17 Mindest-Abdeckung für dieses Requirement: #459

*Tickets:* #459, #462

### ROU-28 — Panel-bezogene Schreib-/Reload-Kante ist loopback-/`/admin/`-geschützt
Jede panel-bezogene Schreib-/Reload-Kante des Routers — etwa ein
Cache-Invalidierungs- oder Cache-Refresh-Trigger für den ROU-27-Cache —
liegt unter dem `/admin/`-Pfad und ist **loopback-only** (Spiegel zu
PREG-10), genau wie der Admin-Reload des Routers
(`POST /api/v1/router/admin/reload`, ROU-18). nginx blockt `/admin/`
von außen (`deploy/nginx/xbuddy-origin.conf`), sodass die Kante
**nicht** offen im Familien-LAN steht. Nur der panel-Service ruft sie
über Loopback; kein Controller-Gerät und kein Familienmitglied erreicht
sie.

Ob V1 überhaupt eine aktive Invalidierungs-Kante exponiert oder der
Last-Known-Good-Cache (ROU-27) rein upstream-first mit Fallback arbeitet
(und damit keine panel-bezogene Schreib-Kante nötig ist), legt der
Impl-PR fest — die hier festgelegte loopback-/`/admin/`-Invariante gilt
für jede exponierte Kante unabhängig davon (OPEN-PREG-F).

ROU-29 ist die konkrete panels-Schreib-Kante unter dieser
loopback-/`/admin/`-Invariante (die zweite Ausprägung nach dem Admin-Reload,
ROU-18).

*Tests:* ROU-17 Mindest-Abdeckung für dieses Requirement: #58

*Tickets:* #58

### ROU-29 — `POST /api/v1/router/admin/panels/` — panels-Eintrag schreiben/aktualisieren
Der Router exponiert eine **konkrete Schreib-Kante** für den
`panels`-Abschnitt der `routing.json` (ROU-18). Sie ist die zweite, konkrete
Ausprägung der loopback-/`/admin/`-Invariante aus ROU-28 (die erste ist der
Admin-Reload, ROU-18) und der Endpunkt, den der panel-Service für die
2-Schritt-Anlage und den Reconcile-Pfad ruft (`panel-registry.md` PREG-16/PREG-17).

**Endpunkt-Form.** `POST /api/v1/router/admin/panels/` — konsistent zum
bestehenden Admin-Reload (`POST /api/v1/router/admin/reload`, ROU-18): unter
`/api/v1/router/admin/` (URL-4: `/api/v1/`, Komponente `router`, dann das
`admin/`-Segment), Collection `panels` im Plural.

**Body.** JSON-Objekt `{ "source_id": <string>, "display_id": <string> }`.
Der Endpunkt schreibt oder aktualisiert genau **einen** `panels`-Eintrag der
`routing.json` — die Map-Zeile `source_id → { display_id }` (ROU-18). Ist die
`source_id` schon vorhanden, wird ihr `display_id` überschrieben (Umzug eines
Panels auf ein anderes Display); ist sie neu, wird die Zeile angelegt. **Genau
ein Display pro Panel-Instanz** (Singular `display_id`, E-PANEL-5 / ROU-24) —
ein `display_ids`-Plural im Body ist eine Schema-Verletzung (4xx), damit die
veraltete Plural-Form (vom `_parse_routing`-Pfad in ROU-18 schon abgelehnt) gar
nicht erst in die Datei gelangt.

**Loopback-/`/admin/`-geschützt (ROU-28).** Die Kante ist **loopback-only**
(gleicher `_is_loopback`-Guard wie der Admin-Reload, `127.0.0.1`/`::1`) und
liegt unter `/admin/`, das nginx von außen blockt
(`deploy/nginx/xbuddy-origin.conf`). **Nur der panel-Service** ruft sie über
Loopback (PREG-16/PREG-17); kein Controller-Gerät und kein Familienmitglied
erreicht sie. Ein Aufruf von einer nicht-Loopback-Origin bekommt 403 (wie der
Admin-Reload).

**GER-Validierung gegen die Geräte-Registry, nicht gegen `known_displays`.**
Vor dem Schreiben prüft der Router, dass `display_id` **in der Geräte-Registry
existiert** — über deren HTTP-Lese-Schnittstelle (`geraete.md` GER-14,
`GET /api/v1/geraete/<id>`, DCOMP-1), genau wie die Panel-Registry beim Anlegen
(PREG-7). **Nicht** gegen `known_displays`/die eigene `routing.json` des
Routers: Validierte man dort, würde ein `panels`-Eintrag für ein frisch
angelegtes Display abgelehnt, solange noch kein `entries`-Eintrag dieses
Display referenziert — derselbe zeitliche Kopplungs-Fehler, den PREG-7
beschreibt (Muss-Korrektur 1 der Ratifizierung). Die Geräte-Registry weiß
zuerst, dass ein Display existiert.

**Atomar geschrieben, sofort sichtbar.** Der Eintrag wird **atomar** in die
`routing.json` geschrieben (Temp-Datei + `os.replace`, DCOMP-4) — ein parallel
laufender Lookup (ROU-9/ROU-24) sieht nie eine halb geschriebene Datei. Weil der
Router `routing.json` **pro Aufruf frisch von Disk** liest (Reload-on-Read,
DCOMP-2 / ROU-18), wird der neue `panels`-Eintrag vom nächsten
`tile_selected`-Lookup (ROU-24) **ohne Service-Restart und ohne expliziten
Reload-Trigger** gesehen. Ein expliziter Admin-Reload (ROU-18) ist nicht nötig,
aktualisiert aber wie gehabt den Snapshot-Cache.

**Fehlerverhalten.**

| Fall | Antwort |
|---|---|
| Schreiben/Aktualisieren erfolgreich | 200, JSON `{ "written": true, "source_id": <…>, "display_id": <…> }` |
| Fehlendes Pflichtfeld (`source_id`/`display_id`) oder `display_ids`-Plural im Body | 400, JSON `{ "error": "<Feld>" }` (ROU-5-Form) |
| `display_id` in der Geräte-Registry unbekannt (GER-14 → 404) | 400, JSON `{ "error": "display unbekannt" }` |
| Geräte-Registry nicht erreichbar | 503, JSON-Fehler — `routing.json` bleibt unverändert (kein stilles Durchwinken, symmetrisch zu PREG-7) |
| IO-/Schreibfehler (`routing.json` nicht schreibbar, atomares Replace scheitert) | 503, JSON-Fehler — `routing.json` bleibt unverändert |
| Aufruf von nicht-Loopback-Origin | 403 (ROU-28, wie Admin-Reload) |

Der Router schreibt **nur** den `panels`-Abschnitt; der `entries`-Abschnitt
(descriptor-basiertes Matching, ROU-9) bleibt von dieser Kante unberührt — die
Read-Modify-Write-Operation liest die ganze `routing.json`, ersetzt genau die
eine `panels`-Zeile und schreibt das Gesamtobjekt atomar zurück. Parallele
`POST`s werden serialisiert (Schreib-Lock), damit zwei verschiedene
`source_id`-Einträge beide landen — kein verlorengehendes Update (symmetrisch zu
PREG-15 / GER-15).

*Tests:* ROU-17 Mindest-Abdeckung für dieses Requirement: #329

*Tickets:* #329

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
- ROU-26 — `/display/_shared/icons/<source>/<id>.png` liefert ein Asset
  aus der icon-root mit `image/png`; nicht existierendes Asset und
  Path-Traversal werden mit 404 abgewiesen; `icon_root` ist per
  `runtime_config` überschreibbar.
- ROU-27 — `GET /controller/app-panel/<id>/config.json|tiles.json`
  liefert die Instanz-Daten vom panel-Service (proxy); bei simuliertem
  panel-Service-Ausfall liefert der Router den Last-Known-Good-Snapshot;
  ohne je erfolgreichen Abruf fällt die Seite auf Code-Defaults zurück
  (kein Crash).
- ROU-28 — eine panel-bezogene Schreib-/Reload-Kante unter `/admin/`
  antwortet auf Loopback; eine Anfrage von einer externen, nicht-Loopback-
  Origin (ohne `/admin/`-Freigabe durch nginx) erreicht sie nicht.
- ROU-29 — `POST /api/v1/router/admin/panels/` mit gültigem
  `{source_id, display_id}` (Geräte-Registry gestubbt, Display bekannt)
  schreibt den `panels`-Eintrag atomar und der nächste `tile_selected`-Lookup
  (ROU-24) sieht ihn ohne Reload; ein zweiter POST mit gleicher `source_id`
  und anderem `display_id` aktualisiert die Zeile (Umzug); fehlendes
  Pflichtfeld bzw. `display_ids`-Plural ist 400; `display_id` in der
  Geräte-Registry unbekannt ist 400; Geräte-Registry nicht erreichbar ist 503
  (`routing.json` unverändert); Disk-Schreibfehler ist 503 (`routing.json`
  unverändert); ein Aufruf von nicht-Loopback-Origin bekommt 403; der
  `entries`-Abschnitt bleibt unberührt.

*Tickets:* #5, #24, #58, #329

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

ENV-Naming, Priorität (`CLI > ENV > config.json > Default`) und der
gemeinsame `--log-level`-Flag folgen `conventions/config.md` CONFIG-5.
Die folgende Tabelle ist die konkrete Router-Belegung dieser
Konvention:

| Datei-Schlüssel  | ENV                       | CLI                |
|------------------|---------------------------|--------------------|
| `listen_host`    | `ROUTER_LISTEN_HOST`      | `--host`           |
| `listen_port`    | `ROUTER_LISTEN_PORT`      | `--port`           |
| `log_level`      | `ROUTER_LOG_LEVEL`        | `--log-level`      |
| `controller_dir` | `ROUTER_CONTROLLER_DIR`   | `--controller-dir` |
| `icon_root`      | `ROUTER_ICON_ROOT`        | `--icon-root`      |
| `routing_file`   | `ROUTER_ROUTING_FILE`     | `--routing`        |

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
2026-05-15; internes Deliberations-Artefakt, nicht Teil des public Repos).
Für V1 mit einem Display, das pollen kann, ist Reconnect- und
State-Recovery-Logik überdimensioniert.

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

Der Router V1 (#5) wurde gebaut, bevor `conventions/urls.md` (die
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
nicht. Wäre `conventions/urls.md` vor dem Router-Bau gemergt gewesen,
hätte es diese Migration nicht gebraucht.

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
