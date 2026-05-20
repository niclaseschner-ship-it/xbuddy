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
- `/api/v1/<resource>` — Hub-Backend (State, Events, Config)
- `/health`, `/version` — System-Meta

Andere Top-Level-Pfade sind nicht erlaubt.

- Tickets: —

### URL-2 — Display-Pfade

Display-Pfade folgen dem Muster `/display/<buddy>/<view>`, wo `<buddy>`
ein Buddy-Slug und `<view>` ein View-Name ist. Display-Pfade enthalten
keine Verben — sie benennen Views, keine Aktionen. Varianten einer View
(z. B. Kinder- vs. Eltern-Ansicht, Personen-Bezug) werden als
Query-Parameter ausgedrückt, nicht im Pfad.

- Tickets: —

### URL-3 — Controller-Pfade

Controller-Pfade folgen dem Muster `/controller/<source>/<action>`, wo
`<source>` die Eingabequelle (z. B. `figure`, `nfc`, `voice`) und
`<action>` die Aktion (z. B. `place`, `rotate`, `scan`) ist. Verben sind
hier erlaubt — die Aktion ist die Semantik. Das Prefix heißt `controller`,
auch wenn es keinen dedizierten Controller-Buddy gibt.

- Tickets: —

### URL-4 — API-Pfade

Backend-API-Pfade folgen dem Muster `/api/v<n>/<resource>` mit explizitem
Versions-Segment (z. B. `/api/v1/state`). Collections werden im Plural
benannt (`/api/v1/events`), einzelne Ressourcen oder Aggregate im
Singular (`/api/v1/state`).

- Tickets: —

### URL-5 — Meta-Pfade

Liveness- und Versions-Endpunkte sitzen flach auf Top-Level:
`/health` liefert den Gesundheitszustand des Diensts, `/version` die
laufende Version. Sie tragen kein Prefix.

- Tickets: —

### URL-6 — Casing und Trennzeichen

Alle URL-Segmente sind kleingeschrieben und nutzen Bindestriche (`-`) als
Wort-Trenner. Underscores, camelCase oder Großbuchstaben sind nicht
erlaubt — also `now-playing`, nicht `now_playing` oder `nowPlaying`.

- Tickets: —

### URL-7 — Sprache

App-Domänen-Begriffe sind deutsch (`kalender`, `woche`, `morgen`,
`wetter`). Technische Begriffe sind englisch (`state`, `events`, `health`,
`version`). Folgt der Sprach-Konvention aus `CLAUDE.md` §3.

- Tickets: —

### URL-8 — Stabilität

Pfad-Segmente werden nach Veröffentlichung nicht umbenannt. Varianten und
Filter werden als Query-Parameter ausgedrückt (z. B. `?ansicht=kind`,
`?for=mila`). Eine einmal vergebene URL behält ihre Semantik dauerhaft.

- Tickets: —

### URL-9 — Versionierung

Versionierung passiert ausschließlich im API-Bereich über das
Pfad-Segment `v<n>`. Bei Breaking Changes am Backend entsteht ein
paralleler Sub-Tree `/api/v<n+1>/…`; die alte Version bleibt mindestens
einen Major-Zyklus erreichbar. Display- und Controller-Pfade werden
nicht versioniert — sie halten dauerhaft.

- Tickets: —

### URL-10 — Kein Hardware-Bezug im Pfad

Pfade enthalten keine Hinweise auf das konkrete Endgerät (Display-Größe,
Hardware-Typ). Derselbe Pfad bedient BuddyBoard, Tablet und Phone.
Anpassungen passieren client-seitig (Responsive Design) oder über
Content-Negotiation, nicht im URL-Pfad.

- Tickets: —

## Beispiele

```
/display/kalender/woche?ansicht=kind&for=mila
/display/musik/now-playing
/display/wetter/kompakt

/controller/figure/place
/controller/figure/rotate
/controller/figure/remove
/controller/nfc/scan

/api/v1/state
/api/v1/events
/api/v1/config

/health
/version
```
