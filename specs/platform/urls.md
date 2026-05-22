# URLs — Spec

> ID-Präfix: URL
> Plattform-Vertrag zwischen Display, Controller und Hub: wie HTTP-Pfade
> aufgebaut sind und benannt werden.

## Zweck

URL-Konventionen für alle HTTP-Endpunkte des XBuddy-Ökosystems. Stellt
sicher, dass Pfade vorhersagbar, stabil und kollisionsfrei sind — auch
wenn über die Zeit dutzende bis ~100 Endpunkte dazukommen.

## Anforderungen

### URL-1 — Vier Top-Level-Prefixe

Das System bietet HTTP-Endpunkte nur unter einem dieser vier Prefixe an:

- `/display/<buddy>/<view>` — Display-Views eines Buddys
- `/controller/<source>/<action>` — Controller-Aktionen
- `/api/v1/<resource>` — Hub-Backend (State, Events, Config, Diagnose)
- `/health`, `/version` — System-Meta

Andere Top-Level-Pfade sind nicht erlaubt.

*Tickets:* #24

### URL-2 — Display-Pfade

Display-Pfade folgen dem Muster `/display/<buddy>/<view>`, wo `<buddy>`
ein Buddy-Slug und `<view>` ein View-Name ist. Display-Pfade enthalten
keine Verben — sie benennen Views, keine Aktionen. Varianten einer View
(z. B. Kinder- vs. Eltern-Ansicht, Personen-Bezug) werden als
Query-Parameter ausgedrückt, nicht im Pfad.

*Tickets:* #24

### URL-3 — Controller-Pfade

Controller-Pfade folgen dem Muster `/controller/<source>/<action>`, wo
`<source>` die Eingabequelle (z. B. `figure`, `nfc`, `voice`) und
`<action>` die Aktion (z. B. `place`, `rotate`, `scan`) ist. Verben sind
hier erlaubt — die Aktion ist die Semantik. Das Prefix heißt `controller`,
auch wenn es keinen dedizierten Controller-Buddy gibt.

*Tickets:* #24

### URL-4 — API-Pfade

Backend-API-Pfade folgen dem Muster `/api/v<n>/<resource>` mit explizitem
Versions-Segment (z. B. `/api/v1/events`). Collections werden im Plural
benannt (`/api/v1/events`, `/api/v1/displays`), einzelne Ressourcen oder
Aggregate im Singular (`/api/v1/displays/<id>/state`).

*Tickets:* #24

### URL-5 — Meta-Pfade

Liveness- und Versions-Endpunkte sitzen flach auf Top-Level:
`/health` liefert den Gesundheitszustand des Diensts, `/version` die
laufende Version. Sie tragen kein Prefix.

*Tickets:* #24

### URL-6 — Casing und Trennzeichen

Alle URL-Segmente sind kleingeschrieben und nutzen Bindestriche (`-`) als
Wort-Trenner. Underscores, camelCase oder Großbuchstaben sind nicht
erlaubt — also `now-playing`, nicht `now_playing` oder `nowPlaying`.

*Tickets:* #24

### URL-7 — Sprache

App-Domänen-Begriffe sind deutsch (`kalender`, `woche`, `morgen`,
`wetter`). Technische Begriffe sind englisch (`state`, `events`, `health`,
`version`). Folgt der Sprach-Konvention aus `CLAUDE.md` §3.

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
verteilt wird, ist Sache der Umsetzung.

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

/health
/version
```
