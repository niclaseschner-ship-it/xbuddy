# URLs — Konvention     (ID-Präfix: URL)

Plattform-Vertrag zwischen Display, Controller und Hub: wie HTTP-Pfade
aufgebaut sind und benannt werden. Stellt sicher, dass Pfade
vorhersagbar, stabil und kollisionsfrei sind — auch wenn über die Zeit
dutzende bis ~100 Endpunkte dazukommen.

### URL-1 — Drei Top-Level-Prefixe

Das System bietet HTTP-Endpunkte nur unter einem dieser drei Prefixe an:

- `/display/<buddy>/<view>` — Display-Views eines Buddys
- `/controller/<source>/<action>` — Controller-Aktionen
- `/api/v1/<resource>` — Hub-Backend (State, Events, Config, Diagnose)

Andere Top-Level-Pfade sind nicht erlaubt.

*Tickets:* #24, #66

### URL-2 — Display-Pfade

Display-Pfade folgen dem Muster `/display/<buddy>/<view>`, wo `<buddy>`
ein Buddy-Slug und `<view>` ein View-Name ist. Display-Pfade enthalten
keine Verben — sie benennen Views, keine Aktionen. Varianten einer View
(z. B. Kinder- vs. Eltern-Ansicht, Personen-Bezug) werden als
Query-Parameter ausgedrückt, nicht im Pfad.

Eine Display-View darf zusätzlich zu `GET` auch `POST` auf **denselben
verbfreien View-Pfad** annehmen, wenn es um ihre **eigene
View-Interaktion** geht (z. B. einen Routine-Punkt abhaken). Die
HTTP-Methode trägt die Aktion — der Pfad bleibt verbfrei (kein
`/toggle`, kein `/aktion`). Davon abzugrenzen ist der
**Cross-App-Schreibzugriff**, der weiterhin über
`/api/v1/<slug>/<resource>` läuft (BUD-1b). Erstes Vorkommen:
Routine-Buddy `POST /display/routine/morgen` (#335, Routine-Integration).

*Tickets:* #24, #335

### URL-3 — Controller-Pfade

Controller-Pfade folgen dem Muster `/controller/<source>/<X>` — zwei
Segmente unter dem `controller`-Prefix. Das erste Segment `<source>` ist
entweder die Eingabequelle einer Action (z. B. `figure`, `nfc`, `voice`)
oder der Slug einer Controller-App, die als PWA ausgeliefert wird
(z. B. `figuren-erkennung`). Das zweite Segment hängt vom HTTP-Verb ab:

- POST: `<X>` ist die Aktion (z. B. `place`, `rotate`, `scan`) — Verben
  sind hier erlaubt, die Aktion ist die Semantik.
- GET: `<X>` ist ein Asset-Pfad innerhalb der Controller-App (z. B.
  `sw.js`, `manifest.json`, `icon-192.png`). Die Statik-Auslieferung
  legt ROU-23 fest.

Eingabequellen sind kurz und beschreibend (`figure`, `nfc`, `voice`),
App-Slugs ausführlicher (`figuren-erkennung`) — eine Kollision würde
auffallen und ist über Naming-Disziplin auszuschließen. Das Prefix
heißt `controller`, auch wenn es keinen dedizierten Controller-Buddy
gibt.

*Tickets:* #24

### URL-3a — Dokumentierte Abweichungen vom Zwei-Segment-Muster

Zwei Pfade sitzen unter einem zulässigen Top-Level-Prefix (URL-1),
weichen aber bewusst von der Action-/Asset-Form (URL-2 bzw. URL-3) ab,
weil ihr zweites Segment eine **Instanz-Identität** ist und kein Verb
und kein Asset:

- **ROU-20** — ENTFALLEN (RAT-31 E6d #1566 / E6f #1568): `GET /display/<id>`
  lieferte den Display-Client; mit dem Ein-Gerät-Heim-Display (`heim-shell.md`)
  und dem Router-Abriss gibt es diese Route nicht mehr. Historischer Anker:
  [`../specs/platform/router.md`](../specs/platform/router.md) (ENTFALLEN), ROU-20.
- **PANEL-2** — `/controller/app-panel/<id>` liefert die Panel-Seite;
  `<id>` ist die Panel-Instanz-Identität (PANEL-8). Abweichung von URL-3
  (`/controller/<source>/<X>`). Quelle:
  [`../specs/platform/app-panel.md`](../specs/platform/app-panel.md),
  PANEL-2.
- **HSP-25/HSP-26** — `/display/hoerspiel/<kind_id>/<view>` und
  `/api/v1/hoerspiel/<kind_id>/<resource>` tragen die Kind-Instanz-
  Identität als zweites Segment (Hörbuchbuddy V1 mit zwei expliziten
  Instanzen Mia + Finn; eine Hörbuchbuddy-Klasse, n Instanzen pro Pi,
  handverdrahtet — siehe RAT-17). Abweichung von URL-2/URL-4 (Kind ist
  kein View und kein Resource-Name). Quelle:
  [`../specs/buddies/hoerspiel.md`](../specs/buddies/hoerspiel.md),
  HSP-25/HSP-26/HSP-28a.

Die Identitäts-Form ist konsistent über Event-Schema, Config und
Routing-Tabelle: die Schlüssel des `panels`-Abschnitts in `routing.json`
(ROU-18) tragen die volle `source_id`-Form (`app-panel:<id>`, analog
`phone:<instanz>` für die Phone/Controller-Routing-Tabelle — IDENT-2).

Neue Abweichungen werden hier eingetragen, sobald sie in ihrer
Komponenten-Spec eine eigene ID bekommen — `urls.md` bleibt die
Übersicht, die jeweilige Komponenten-Spec die Begründung.

*Tickets:* #122, #907

### URL-4 — API-Pfade

Backend-API-Pfade folgen dem Muster `/api/v<n>/<resource>` mit explizitem
Versions-Segment (z. B. `/api/v1/events`). Collections werden im Plural
benannt (`/api/v1/events`, `/api/v1/displays`), einzelne Ressourcen oder
Aggregate im Singular (`/api/v1/displays/<id>/state`).

*Tickets:* #24

### URL-6 — Casing und Trennzeichen

Alle URL-Segmente sind kleingeschrieben und nutzen Bindestriche (`-`) als
Wort-Trenner. Underscores, camelCase oder Großbuchstaben sind nicht
erlaubt — also `now-playing`, nicht `now_playing` oder `nowPlaying`.

*Tickets:* #24

### URL-7 — Sprache

App-Domänen-Begriffe sind deutsch (`kalender`, `woche`, `morgen`,
`wetter`). Technische Begriffe sind englisch (`state`, `events`). Folgt
der Sprach-Konvention aus `CLAUDE.md` §3.

*Tickets:* #24

### URL-8 — Stabilität

Pfad-Segmente werden nach Veröffentlichung nicht umbenannt. Varianten und
Filter werden als Query-Parameter ausgedrückt (z. B. `?ansicht=kind`,
`?for=mila`). Eine einmal vergebene URL behält ihre Semantik dauerhaft.

*Tickets:* #24

### URL-9 — Versionierung

Versionierung passiert ausschließlich im API-Bereich über das
Pfad-Segment `v<n>`. Bei Breaking Changes am Backend entsteht ein
paralleler Sub-Tree `/api/v<n+1>/…`; die alte Version bleibt mindestens
einen Major-Zyklus erreichbar. Display- und Controller-Pfade werden
nicht versioniert — sie halten dauerhaft.

*Tickets:* #24

### URL-10 — Kein Hardware-Bezug im Pfad

Pfade enthalten keine Hinweise auf das konkrete Endgerät (Display-Größe,
Hardware-Typ). Derselbe Pfad bedient BuddyBoard, Tablet und Phone.
Anpassungen passieren client-seitig (Responsive Design) oder über
Content-Negotiation, nicht im URL-Pfad.

*Tickets:* #24

### URL-11 — HTTPS für alle Endpunkte

Alle HTTP-Endpunkte des XBuddy-Ökosystems (URL-1) werden über HTTPS
ausgeliefert; einen Klartext-Zugang im laufenden Betrieb gibt es nicht. Damit
ist Mixed Content zwischen einer Display-Seite und darin eingebettetem
Buddy-Inhalt ausgeschlossen, und Browser-Fähigkeiten, die einen Secure Context
verlangen (Kamera, Mikrofon, Service-Worker und PWA-Installation), stehen zur
Verfügung. Das Server-Zertifikat einer Instanz wird von der lokalen Root-CA
dieser Instanz signiert, der die Geräte der Familie vertrauen — wie diese CA
erzeugt und auf die Geräte verteilt wird, ist Sache der Umsetzung, nicht dieses
Pfad-Vertrags. Lokale Entwicklung und automatisierte Tests dürfen ohne TLS
laufen.

*Tickets:* #36

### URL-12 — Eine Origin für alle Endpunkte

Alle HTTP-Endpunkte einer XBuddy-Instanz (URL-1) werden unter **einer** Origin
ausgeliefert: gleiches Schema, gleicher Host, gleicher Port. Welche Komponente
eine Anfrage bedient, ergibt sich allein aus dem Pfad-Prefix (URL-1) — nicht aus
Host oder Port. Damit sind eine Display-Seite und ein darin eingebetteter
Buddy-Inhalt same-origin (kein Mixed Content), und eine Instanz trägt genau ein
Server-Zertifikat (URL-11). Wie die Origin intern auf die Komponenten-Prozesse
verteilt wird, ist Sache der Umsetzung — die konkrete Pfad-zu-Upstream-Zuordnung
regelt URL-14.

*Tickets:* #36

### URL-13 — Statische Assets im Display-Namensraum des Buddys

Statische Assets eines Buddys (Stylesheets, Schriften, Bilder, Skripte) werden
unter einem reservierten Sub-Pfad seines Display-Namensraums ausgeliefert:
`/display/<buddy>/static/<asset>`. Damit liegen sie unter einem der vier
Top-Level-Prefixe (URL-1) und sind hinter der einen Origin (URL-12) erreichbar —
ein Buddy darf seine Assets nicht unter einem eigenen Top-Level-Pfad wie
`/static/…` anbieten, weil ein solcher Pfad von der Origin nicht geroutet wird
und ins Leere fällt.

*Tickets:* #61

### URL-14 — Origin-Routing-Tabelle

Die eine Origin (URL-12) verteilt eingehende Anfragen nach Pfad-Prefix auf die
getrennten Komponenten-Prozesse einer Instanz. Welcher Prefix zu welchem
Upstream gehört, ist nicht Sache der Umsetzung, sondern Vertrag — sonst hat
jeder Konsument (nginx-Conf, Onboarding-Schritte, neue Komponenten) eine eigene
Annahme.

Die Origin matcht Pfade in dieser Reihenfolge (spezifisch vor allgemein — der
längste Prefix gewinnt, das ist Teil der Spec, nicht nur eine nginx-Marotte):

| # | Pfad-Prefix                     | Upstream-Komponente | Bemerkung                                                                 |
|---|---------------------------------|---------------------|---------------------------------------------------------------------------|
| 1 | `/display/plan/`                | Plan-Buddy          | Display-Views des Plan-Buddys (URL-2): `/display/plan/woche` (PLAN-2/3).  |
| 2 | `/display/wetter/`              | Wetter-Buddy        | Display-View des Wetter-Buddys (WETTER-2): `/display/wetter/heute`.       |
| 3 | `/display/routine/`             | Routine-Buddy       | Display-View des Routine-Buddys (ROUTINE-2): `/display/routine/morgen`.   |
| 4 | `/display/photo/`               | Photo-Buddy         | Display-View des Photo-Buddys (PHOTO-2): `/display/photo/rahmen`.         |
| 5 | `/display/essen/`               | Essens-Buddy        | Display-View des Essens-Buddys (ESSEN-2): `/display/essen/wunsch`. Upstream: xbuddy-essen (:5052, PORT-2). |
| 6 | `/display/hoerspiel/mia/`     | Hörspiel-Buddy (Mia) | Display-View Mia-Instanz (HSP-3a, HSP-26, RAT-17, URL-3a). Schließt `/display/hoerspiel/mia/static/` (URL-13) und `/display/hoerspiel/mia/data/<sub>` (Per-Instanz-Audio/Cover) ein. Upstream: xbuddy-hoerspiel (:5053, PORT-2). |
| 7 | `/display/hoerspiel/finn/`      | Hörspiel-Buddy (Finn)  | Display-View Finn-Instanz (HSP-28a, RAT-17, URL-3a). Schließt `/display/hoerspiel/finn/static/` (URL-13) und `/display/hoerspiel/finn/data/<sub>` (Per-Instanz-Audio/Cover) ein. Upstream: xbuddy-hoerspiel-finn (:5055, PORT-2). |
| 8 | `/display/hoerspiel/emil/`    | Hörspiel-Buddy (Emil)  | Display-View Emil-Instanz (HSP-28a, RAT-17, URL-3a, T1347). Schließt `/display/hoerspiel/emil/static/` (URL-13) und `/display/hoerspiel/emil/data/<sub>` (Per-Instanz-Audio/Cover) ein. Upstream: xbuddy-hoerspiel-emil (:5056, PORT-2). |
| 9 | `/display/hoerspiel/`           | Hörspiel-Buddy (Mia, Fallback) | Fallback ohne `<kind_id>`-Segment (z.B. `/display/hoerspiel/alben` und `/display/hoerspiel/themen` vor T4 #910). Übergangs-Provisorium — T4 #910 hebt diese Route auf kind_id-tragende Form. Upstream: xbuddy-hoerspiel (:5053, PORT-2). |
| 10 | `/display/kibuddy/`             | KI-Buddy            | Display-View des KI-Buddys (KIBUDDY-2): `/display/kibuddy/frage`. Schließt `/display/kibuddy/static/` (URL-13) ein. Upstream: xbuddy-kibuddy (:5054, PORT-2). |
| 11 | `/api/v1/plan/`                | Plan-Buddy          | Plan-Buddy-Backend: `GET\|PUT /api/v1/plan/termine` (PLAN-22), `GET /api/v1/plan/zuteilung` (PLAN-30), `PUT /api/v1/plan/zuteilung` (PLAN-31), `PUT\|DELETE /api/v1/plan/aktivitaet` (PLAN-11). |
| 12 | `/api/v1/familie/`             | Familie             | Familien-Mit-Host (Personen, Foto).                                       |
| 13 | `/api/v1/geraete/`             | Geräte              | Geräte-Registry (GER-13/14/15) — Liste, Einzeln, Anlegen.                 |
| 14 | `/api/v1/photo/`               | Photo-Buddy         | Photo-Buddy-Backend: Medien-Library + interface-first Ingest (PHOTO-13..16): `POST\|GET /api/v1/photo/medien`, `GET /api/v1/photo/medien/<id>[/thumbnail]`, `DELETE /api/v1/photo/medien/<id>`. |
| 15 | `/api/v1/essen/`               | Essens-Buddy        | Essens-Buddy-Backend: Wunsch-Liste (ESSEN-15..17) + Katalog (ESSEN-18..19). Upstream: xbuddy-essen (:5052, PORT-2). |
| 16 | `/api/v1/routine/`             | Routine-Buddy       | Routine-Buddy-Backend: Schreib-API für Zeiten/Items (ROUTINE-14). Upstream: xbuddy-routine (:5050, PORT-2). |
| 17 | `/api/v1/hoerspiel/mia/`     | Hörspiel-Buddy (Mia) | Hörspiel-Backend Mia-Instanz (HSP-17, HSP-26, RAT-17, URL-3a): Bible/Historie-Read, Alben-Liste + Manifest, Folgen-Vorschlag, Album-Bau, Config (PATCH), Shared-Assets-Status/Rebuild. Upstream: xbuddy-hoerspiel (:5053, PORT-2). |
| 18 | `/api/v1/hoerspiel/finn/`      | Hörspiel-Buddy (Finn)  | Hörspiel-Backend Finn-Instanz (HSP-28a, RAT-17, URL-3a): gleiche API-Surface wie Mia. Upstream: xbuddy-hoerspiel-finn (:5055, PORT-2). |
| 19 | `/api/v1/hoerspiel/emil/`    | Hörspiel-Buddy (Emil)  | Hörspiel-Backend Emil-Instanz (HSP-28a, RAT-17, URL-3a, T1347): gleiche API-Surface wie Mia und Finn. Upstream: xbuddy-hoerspiel-emil (:5056, PORT-2). |
| 20 | `/api/v1/hoerspiel/`           | Hörspiel-Buddy (Mia, Fallback) | Fallback ohne `<kind_id>`-Segment (z.B. `/api/v1/hoerspiel/themen` vor T4 #910). Übergangs-Provisorium — T4 #910 hebt diese Route auf kind_id-tragende Form. Upstream: xbuddy-hoerspiel (:5053, PORT-2). |
| 21 | `/api/v1/kibuddy/`             | KI-Buddy            | KI-Buddy-Backend (KIBUDDY-24): Frage-Verarbeitung (`POST /api/v1/kibuddy/frage`), Audio-Cache-Replay (`GET /api/v1/kibuddy/audio/<id>.mp3`), TTS-Replay (`POST /api/v1/kibuddy/vorlesen`), Session-Reset (`POST /api/v1/kibuddy/reset`), Prompt (`GET\|PUT /api/v1/kibuddy/prompt`, KIBUDDY-15), Config (`GET\|PUT /api/v1/kibuddy/config`). Upstream: xbuddy-kibuddy (:5054, PORT-2). |
| 22 | `/display/_shared/icons/`      | Seiten-Registry     | ARASAAC-Piktogramme (ROU-26, RAT-31 E6f-B, #1586). Upstream: xbuddy-seiten (:5042, PORT-2). |
| 23 | `/display/_shared/design/`     | Seiten-Registry     | Design-Tokens (ROU-30, RAT-31 E6f-A, #1582). Upstream: xbuddy-seiten (:5042, PORT-2). |
| 24 | `/controller/app-panel/`       | Seiten-Registry     | App-Panel-Instanz-Views (SREG-17, RAT-31 E6b, #1564). Upstream: xbuddy-seiten (:5042, PORT-2). |
| 25 | `/controller/_shared/`         | Seiten-Registry     | PWA-übergreifende Helper (ROU-23, RAT-31 E6f-A, #1582). Upstream: xbuddy-seiten (:5042, PORT-2). |
| 26 | `/api/v1/panels/`              | Panel-Registry      | Panel-Registry-API (PREG-13/14/15) — Liste, Einzeln, Anlegen. Upstream: xbuddy-panel (:5041, PORT-2). |
| 27 | `/api/v1/seiten`               | Seiten-Registry     | Seiten-/Adress-Registry (SREG): `GET /api/v1/seiten` = Inventar aller aufrufbaren Views. Upstream: xbuddy-seiten (:5042, PORT-2). |
| 28 | `/api/v1/icons/suche`          | Seiten-Registry     | Stichwort-Suche über den Icon-Cache (ROU-31, RAT-31 E6f-B, #1586). Upstream: xbuddy-seiten (:5042, PORT-2). |
| 29 | `/` (alles übrige)             | —                   | 404 (URL-1: andere Top-Level-Pfade sind nicht erlaubt). RAT-31 (#1568): die allgemeinen `/display/`-, `/controller/`-, `/api/v1/`-Router-Prefixe und der SSE-Stream `/api/v1/displays/<id>/events` (ROU-22) sind mit dem Router-Abriss entfallen. |

Diese Tabelle ist die Quelle für (a) die nginx-Origin-Konfiguration in
`deploy/nginx/xbuddy-origin.conf` und (b) Onboarding-Schritte, die Origin-Routing
eintragen (z. B. wenn das Geräte-Profil bestimmt, welche Komponenten lokal
laufen). Konsumenten dieser Tabelle: #85 (nginx-Origin-Conf: Familie-Upstream
ergänzen), #60 (Familie anlegen agentisch — schreibt Familie in den Routing-Plan
einer Instanz), #82 (Geräte-Profil im Onboarding — wählt aus dieser Tabelle die
Prefixe, die auf der Instanz aktiv sind), #135 (Icon-Bibliothek: geteilte
Display-Assets von der Seiten-Registry serviert seit RAT-31 E6f-B/#1586, URL-16, ROU-26), #909 (zweite Hörspiel-Instanz Mia+Finn), #1347 (dritte Hörspiel-Instanz Emil).

Eine neue Komponente, die einen eigenen Prozess hinter der Origin betreibt,
muss zuerst hier eine Zeile bekommen — dann nginx, dann Code. Reihenfolge
spezifisch-vor-allgemein wird beibehalten; spezifischere Prefixe (`/api/v1/plan/`,
`/api/v1/familie/`) stehen immer vor allgemeineren (`/api/v1/`).

*Tickets:* #85, #135, #909, #1347

### URL-15 — Origin im LAN erreichbar, nicht nur lokal

Die eine HTTPS-Origin einer XBuddy-Instanz (URL-12) muss von den Endgeräten
der Familie im selben LAN erreichbar sein — nicht nur lokal auf dem Host, der
sie bedient. Konkret heißt das: die Origin antwortet sowohl über den
Host-Namen, den ihr Server-Zertifikat (URL-11) als Subject Alternative Name
trägt (z. B. `xbuddy-hub.local`), als auch über die LAN-IP des Hosts —
identisch zu `localhost`. Eine Origin, die nur auf `localhost` antwortet,
schließt Tablets und Handys aus und macht das Single-Origin-Design (URL-12)
für die Familie unbenutzbar.

Umsetzung: der HTTPS-Listener bindet auf alle Interfaces (nicht nur
`127.0.0.1`), der `server_name` deckt Host-Name und ggf. `localhost` ab, und
das Server-Zertifikat enthält den Host-Namen sowie die LAN-IP als SAN
(`tools/ca/make-ca.sh --san "DNS:xbuddy-hub.local,IP:<pi-lan-ip>"`). Die
Komponenten-Prozesse hinter der Origin bleiben auf `127.0.0.1` gebunden
(URL-12, Routing ausschließlich über die Origin).

*Tickets:* #67

### URL-16 — Geteilter Display-Asset-Namensraum `/display/_shared/`

Assets, die keinem einzelnen Buddy gehören, sondern von mehreren
Komponenten gemeinsam genutzt werden, liegen unter dem reservierten
Sub-Pfad `/display/_shared/<sache>/`. Damit bleiben sie unter dem
Top-Level-Prefix `/display/` (URL-1) und hinter der einen Origin
(URL-12) — ohne einen eigenen Top-Level-Pfad zu belegen.

Bauregeln:

- **read-only**: der Namensraum liefert Assets aus; er nimmt keine
  Schreib-Anfragen entgegen. HTTP-Methoden außer `GET`/`HEAD` werden
  abgelehnt.
- **Zwei legitime Quell-Typen, von der Seiten-Registry serviert**: seit
  RAT-31 (E6f-A/B, #1582/#1586; Router abgerissen #1568) liefert der
  **Seiten-Registry-Dienst** die Assets aus — analog zur Controller-Helper-
  Auslieferung `/controller/_shared/` (ROU-23). Er läuft als User `buddy`
  und liest sowohl Per-Instanz-Pfade als auch In-Repo-Verzeichnisse,
  während ein statischer nginx-`alias` (nginx = `www-data`) an
  `0700`-Home-Permissions scheitern kann (#135). Für die Assets selbst
  sind zwei Quell-Typen erlaubt:
  - **Per-Instanz** (außerhalb des Repos, instanzspezifisch): der Dienst
    liefert aus einem konfigurierbaren Per-Instanz-Verzeichnis aus.
    Beispiel: `/display/_shared/icons/` → ARASAAC-Piktogramme
    (ICONS-5, ROU-26, #135).
  - **Repo-serviert** (im Repo versioniert, bei allen Instanzen identisch):
    der Dienst liefert direkt aus dem In-Repo-Verzeichnis aus — kein
    manueller Pro-Pi-Schritt, keine Divergenz. Beispiel:
    `/display/_shared/design/` → Design-Tokens (DTOK-1, ROU-30, #323).
- **nicht buddy-gebunden**: ein Asset unter `/display/_shared/` gehört
  keinem einzelnen Buddy (für buddy-eigene Assets gilt URL-13).
- **Routing über eigene spezifische Blöcke**: seit RAT-31 (#1568) gibt es
  keinen allgemeinen `/display/`→Router-Fallback mehr; jeder `_shared`-Pfad
  (`/display/_shared/icons/`, `/display/_shared/design/`) hat einen eigenen
  nginx-`location`-Block auf die Seiten-Registry, VOR den Buddy-Prefixen
  (URL-14, längster Prefix gewinnt).

Instanzen: `/display/_shared/icons/` (ARASAAC-Piktogramme, Per-Instanz,
ROU-26, #135) und `/display/_shared/design/` (Design-Tokens, repo-serviert,
ROU-30, #323). Weitere geteilte Display-Assets folgen einem der beiden
Muster je nachdem, ob sie instanzspezifisch sind oder mit dem Code versioniert.

*Tickets:* #135, #323

### URL-17 — Admin-Sub-Pfad pro Komponente: `/api/v1/<komponente>/admin/`

**Ausschließlich host-intern aufgerufene, nicht familienseitige
Admin-Endpunkte** einer Komponente (Reload-, Wartungs- und interne
Schreib-Kanten zwischen Diensten) liegen unter einem reservierten
Sub-Pfad ihres `/api/v1/<komponente>/`-Namensraums:
`/api/v1/<komponente>/admin/<aktion>`. Davon abzugrenzen sind
**familienseitige Schreib-APIs** (z. B. `POST /api/v1/familie/personen`,
`PUT /api/v1/routine/config`, `PUT /api/v1/panels/<panel_id>/tiles`),
die bewusst **außerhalb** `/admin/` leben und vom LAN aus erreichbar
bleiben.

Damit hat jede Komponente, die Admin-Endpunkte braucht, *eine*
vorhersagbare Stelle dafür — und die Origin kann die gesamte Form an
*einer* Stelle gegen den LAN-Zugriff abriegeln.

Bauregeln:

- **Loopback-only**: Admin-Endpunkte akzeptieren ausschließlich Requests,
  deren **ursprüngliche Caller-IP** `127.0.0.1` **oder** `::1` ist
  (IPv4- und IPv6-Loopback), und antworten sonst mit `403`. Der Guard
  lebt im Code der Komponente (Defense in Depth gegenüber der
  Origin-Sperre).

  **Wichtig — Reverse-Proxy-Kontext:** Da jede Komponente hinter dem
  nginx-Reverse-Proxy auf `127.0.0.1` lauscht (PORT-3), ist die direkte
  TCP-Quelle eines durch nginx kommenden Requests **immer** `127.0.0.1`
  — auch wenn der ursprüngliche Caller im Internet sitzt. Der Code-Guard
  muss deshalb die **echte Caller-IP** prüfen, nicht `request.remote_addr`
  unverarbeitet. Konkrete Form: `werkzeug.middleware.proxy_fix.ProxyFix`
  (oder äquivalent) mit `x_for=1` aufsetzen — das setzt `REMOTE_ADDR` aus
  dem `X-Forwarded-For`-Header, **trusted** auf genau eine Proxy-Hop
  (den eigenen nginx). Der Code-Guard prüft danach den ursprünglichen
  Caller. Ohne diese Verkettung ist der Code-Guard wirkungslos gegen
  externe Bypass-Versuche.
- **Origin-seitig mit `404` geblockt**: die Origin **soll** jeden Pfad,
  der auf `^/api/v1/[^/]+/admin/` matcht, mit `404` abweisen — vor allen
  `/api/v1/<komponente>/`-Prefixen (URL-14, spezifisch-vor-allgemein).
  `404` statt `403`, damit die Existenz von Admin-Endpunkten von außen
  nicht sichtbar wird. Die operative Umsetzung in `deploy/nginx/`
  trägt diesen Vertrag und wird durch Verhaltenstests (Stub-Upstream)
  verriegelt — der Code-Guard (oben) ist die zweite Linie.
- **`^~`-Sonderfall**: Nutzt eine Komponente einen `^~`-Prefix-Block
  (wie `^~ /api/v1/seiten/`), muss ihr Admin-Block
  `^~ /api/v1/<komponente>/admin/` **davor** stehen — nginx wertet `^~`
  vor Regex aus, sodass ein allgemeiner Regex-Admin-Block sonst nicht
  greift. Vorbild: `^~ /api/v1/seiten/admin/` vor `^~ /api/v1/seiten/`
  in `deploy/nginx/xbuddy-origin.conf`.
- **Keine Pflicht zur Admin-API**: Komponenten ohne Reload-/Wartungs-/
  internen-Schreib-Bedarf brauchen keinen Admin-Sub-Pfad. URL-17
  reserviert die Form, ohne sie vorzuschreiben.

Spec-Heimat der Verhaltens-Begründung pro Endpunkt: die Komponenten-
Spec (z. B. PLAN-34 für die Plan-Admin-Aktivitäten, EC-21 für den
eltern-chat-Reload). Die früheren Router-Admin-Kanten (ROU-18/28/29,
PBE-10) sind mit RAT-31 (#1568) entfallen.
`urls.md` trägt nur die Pfadform und den Origin-Vertrag.

*Tickets:* —

## Beispiele

```
/display/kalender/woche?ansicht=kind&for=mila
/display/musik/now-playing
/display/wetter/kompakt

/controller/figure/place
/controller/figure/rotate
/controller/figure/remove
/controller/nfc/scan

/api/v1/events
/api/v1/displays/wohnzimmer/state
/api/v1/diag
```
