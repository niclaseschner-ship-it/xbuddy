# Panel-Registry — Spec     (ID-Präfix: PREG)

> Status: V1-Entwurf · Refs #58 (App-Panel) · ratifiziert 2026-06-03
> (`brainstorm/berater-runde/2026-06-03-RATIFIZIERT-panel-registry-api.md`)

Die Panel-Registry ist die **zentrale** Liste der App-Panel-Instanzen einer
Familie. Bisher lebte jede Panel-Instanz als Paar gitignorierter Dateien
(`config.json` + `tiles.json`) im Auslieferungs-Verzeichnis neben dem
Panel-Code (`app-panel.md` PANEL-8 / PANEL-3). Das skaliert nicht auf den
Welle-1-Bedarf „zwei Controller fürs selbe iPhone per Befehl anlegen": jede
neue Instanz verlangte einen manuellen Datei-Eingriff am Hub.

Die Registry hebt diesen Eingriff in einen eigenen Service `xbuddy-panel`
(eigener Prozess, eigener Plattform-Port, SVC-1), der **alle** Panel-Instanzen
einer Familie in einer Per-Instanz-Datei `panels.json` besitzt und über eine
Schnittstelle bereitstellt. Sie ist die eine Quelle für „welche App-Panels
gehören zu dieser Familie" und liefert je Panel stabile Identität,
Display-Bindung, Router-Origin und die Kachel-Konfiguration. Sie besitzt diese
Daten; Router und Panel-Seite sind ihre Nutzer.

Die Panel-Registry ist das Schwester-Modell der Geräte-Registry
([`geraete.md`](geraete.md), GER): ein eigener Daten-Service mit Lese- und
Schreib-Schnittstelle, atomarem Schreiben, Reload-on-Read und Last-Known-Good.
Wo GER **Geräte** besitzt, besitzt PREG **Panel-Instanzen** — und referenziert
GER für die Display-Validierung (PREG-7).

**V1-Scope (Welle 1):** Der Service `xbuddy-panel` mit `panels.json`; je Panel
die Felder aus PREG-3; eine Lese- und eine Schreib-Schnittstelle (HTTP),
analog GER-13/14/15; das instanz-fähige Serving der `config.json`/`tiles.json`
über den Router (Proxy + Last-Known-Good-Cache, PREG-9); die Display-Validierung
gegen die Geräte-Registry (PREG-7); die loopback-/`/admin/`-geschützte
Router-Schreib-API (PREG-10).

**Out-of-Scope V1** (Welle 2, je eigenes Ticket): Kopieren/Löschen einer
Panel-Instanz und Tile-Editing über die Schnittstelle (V1: Anlegen + Lesen —
OPEN-PREG-A) · Reconcile-/Reparatur-Pfad für die verteilte 2-Schritt-Anlage
(Panel + Routing-Eintrag) — OPEN-PREG-B · der Eltern-Chat-Skill, der Panels per
Telegram anlegt (+ `panel_client.py`) — OPEN-PREG-C · benannte Tile-Sets und
ein optionales `geraet_id`-Metadatum — OPEN-PREG-D.

## 1. Reichweite

### PREG-1 — Eine Instanz, eine Panel-Registry
Die Registry einer XBuddy-Instanz beschreibt genau die App-Panels einer
Familie — der Familie des Hubs, auf dem die Instanz läuft. Es gibt keinen
familienübergreifenden Bezeichner und keinen Cross-Familie-Zugriff. Konsistent
mit `geraete.md` GER-1 und `familie.md` FAM-1.

*Tickets:* #58

### PREG-2 — Mehrere Panels pro Gerät, je eigene Identität
Ein physisches Gerät (z. B. ein iPhone) kann **mehrere** Panel-Instanzen
tragen — jede unter einer eigenen, unabhängigen `panel_id` und damit unter
einer eigenen URL `/controller/app-panel/<panel_id>` (PANEL-2), als je eigene
WebAPK installierbar (PWA-1). Die `panel_id` ist load-bearing: sie ist das
Segment, über das der Router das Serving der zugehörigen
`config.json`/`tiles.json` der richtigen Instanz zuordnet (PREG-9).

Eine Panel-Instanz referenziert das **Display** (das Kachel-Ziel, `display_id`),
**nicht** das Controller-Gerät, auf dem sie läuft. Auf welchem Telefon eine
Panel-WebAPK installiert ist, ist V1 kein Registry-Datum (ein späteres,
optionales `geraet_id`-Metadatum ist OPEN-PREG-D). „Zwei Controller fürs selbe
iPhone" sind damit zwei `panels.json`-Einträge mit verschiedenen `panel_id`s
und ggf. gleichem oder verschiedenem `display_id`.

*Tickets:* #58

## 2. Panel-Modell

### PREG-3 — Eigenschaften einer Panel-Instanz
Jede Panel-Instanz trägt:

| Feld          | Pflicht  | Werte                                                       | Bedeutung |
|---------------|----------|-------------------------------------------------------------|-----------|
| `panel_id`    | Pflicht  | stabiler Slug nach PREG-6 (`<slug>-<nn>`)                   | Stabiler, eindeutiger Bezeichner der Panel-Instanz. Wird nie neu vergeben. Das `<id>`-Segment aus `/controller/app-panel/<id>` (PANEL-2). |
| `source_id`   | Pflicht  | `app-panel:<panel_id>`                                       | Identität im Event-/Routing-Sinn (PANEL-6, ROU-18). Aus `panel_id` abgeleitet, in der Datei als eigenes Feld geführt, damit Konsumenten nicht parsen müssen. |
| `display_id`  | Pflicht  | `display_id` aus der Geräte-Registry (GER-7), gegen GER validiert (PREG-7) | Das Display, das diese Panel-Instanz steuert — genau eines (E-PANEL-5). Kachel-Ziel und Quelle des Aktiv-Markierungs-Streams (PANEL-11). |
| `router_url`  | Optional | Origin des Routers (Schema + Host[:Port], **ohne Pfad**), oder leer/fehlend | Origin, an die das Panel Events sendet und von der es Assets lädt. **Leer/fehlend = same-origin** über den Router, der die Seite ausliefert (PREG-8). |
| `config`      | Pflicht  | `config.json`-Objekt nach PANEL-8 (Tuning)                  | Die Pro-Instanz-Konfiguration der Panel-Seite. **Nicht übermalbar** durch einen Tile-Schreiber (E-PANEL-3, PREG-5). |
| `tiles`       | Pflicht  | `tiles.json`-Objekt nach PANEL-3 (Daten)                    | Die Kachel-Liste der Panel-Instanz. **Änderbar** durch einen späteren Tile-Schreiber (E-PANEL-3, OPEN-PREG-A), ohne `config` zu berühren. |

Die Panel-Instanzen sind **Daten** und stehen vollständig in der Datei aus
PREG-4 — nicht im Code (CLAUDE.md §6). Die E-PANEL-3-Trennung bleibt im
Datenmodell erhalten: `config` (Tuning, instanz-stabil) und `tiles` (Daten,
wachsen mit dem App-Bestand) sind zwei getrennte Felder mit getrennten
Lebenszyklen und getrennten Schreib-Rechten (PREG-5).

*Tickets:* #58

## 3. Datenhaltung & Schnittstelle

### PREG-4 — Registry als Per-Instanz-Datei
Die Panel-Liste liegt als JSON-Datei `panels.json` neben dem Service-Code, je
Instanz separat gepflegt und per `.gitignore` aus dem Repo ausgeschlossen —
analog `geraete.json` (`geraete.md` GER-4) und `routing.json` (`router.md`
ROU-18). Die Datei trägt Eigentümer-Rechte `0600` (familienprivat, gleicher
Eigentümer-Schutz wie GER-4 / ZD-3). Eine `panels.example.json` dokumentiert
das Format (kommt mit dem Impl-PR).

Fehlt die Datei beim Start, protokolliert der Service eine Warnung und läuft
mit leerer Panel-Liste weiter, statt abzubrechen (symmetrisch zu GER-4 /
ROU-18 / FAM-6). Ein Konsument, dessen Antwort von einer unbekannten
`panel_id` abhängt, behandelt das im eigenen Kontext (PREG-9: der Router
serviert dann den Last-Known-Good-Cache oder, fehlt auch der, die
Panel-Code-Defaults).

*Tickets:* #58

### PREG-5 — Getrennte Schreib-Rechte für `config` und `tiles`
`config` (PANEL-8-Tuning) und `tiles` (PANEL-3-Daten) sind im Datenmodell
getrennte Felder mit **getrennten Schreib-Rechten** — die E-PANEL-3-Lehre auf
Registry-Ebene:

- Die Anlage einer Panel-Instanz (PREG-15) setzt **beide** Felder.
- Ein späterer Tile-Schreiber (Eltern-Chat, OPEN-PREG-A) ändert **nur**
  `tiles` und darf `config` **nicht** übermalen — gegenseitiges Übermalen ist
  genau der Schaden, den E-PANEL-3 verhindert.

V1 hat noch keinen Tile-Schreiber (OPEN-PREG-A); die Trennung wird aber jetzt
im Modell festgeschrieben, damit der spätere Schreibpfad ein scharf
geschnittenes Feld vorfindet und nicht das ganze Objekt überschreibt.

*Tickets:* #58

### PREG-6 — `panel_id`-Vergabe
Die `panel_id` einer Panel-Instanz ist ihr stabiler Bezeichner — derselbe, der
als `<id>`-Segment in `/controller/app-panel/<id>` (PANEL-2) und als
`source_id`-Suffix (`app-panel:<panel_id>`, PANEL-6) auftaucht. Sie folgt
IDENT-1 in der Form `<slug>-<nn>` (stabil, nicht neu vergeben).

Panel-spezifisch zur allgemeinen Regel:

- `<slug>` ist kleingeschrieben, Bindestrich-getrennt, ohne Sonderzeichen
  (URL-6 sinngemäß — die `panel_id` taucht in Controller-URLs auf, PANEL-2).
- `<nn>` beginnt je Slug bei `01` — „zwei Controller fürs selbe iPhone" werden
  so z. B. `kueche-01` und `kueche-02`, oder zwei semantisch verschiedene Slugs.
- Kollisionsfreiheit prüft der Service **je Familie** — eine `panel_id`, die in
  dieser Instanz schon existiert, wird nicht erneut vergeben.

Beispiele: `kueche-01`, `flur-tablet-01`, `mama-iphone-spielen-01`.

*Tickets:* #58

### PREG-7 — Display-Validierung gegen die Geräte-Registry
Beim Anlegen einer Panel-Instanz (PREG-15) prüft der Service, dass das
angegebene `display_id` **in der Geräte-Registry existiert** — über deren
HTTP-Lese-Schnittstelle (`geraete.md` GER-14, `GET /api/v1/geraete/<id>`),
nicht gegen eine eigene Display-Liste und **nicht** gegen die
`known_displays`/`routing.json` des Routers.

Begründung (Muss-Korrektur aus der Ratifizierung): Die Geräte-Registry ist die
eine Quelle für die Geräte einer Familie (GER-1). Validierte man gegen
`known_displays` des Routers, würde das erste Panel für ein frisch in der
Geräte-Registry angelegtes Display abgelehnt, solange der Router-Eintrag noch
fehlt — ein zeitlicher Kopplungs-Fehler. Die Geräte-Registry weiß zuerst, dass
ein Display existiert.

Ist `display_id` in der Geräte-Registry unbekannt, lehnt PREG-15 die Anlage mit
einem Validierungsfehler ab (400). Ist die Geräte-Registry nicht erreichbar,
ist das ein vorübergehender Fehler der Anlage (503), kein stilles Durchwinken —
ein Panel auf ein nicht validierbares Display anzulegen ist keine sichere
Default-Annahme. Der Aufruf über HTTP folgt DCOMP-1 (kein Python-Import der
Geräte-Komponente).

*Tickets:* #58

### PREG-8 — `router_url`-Semantik: leer = same-origin
`router_url` (PREG-3) ist **optional**. Ist es leer oder fehlt es, bedeutet das
**same-origin**: das Panel sendet Events an und lädt Assets von der Origin, die
seine Seite ausliefert (der Router hinter der einen Origin, URL-12). Das ist
der heutige, im Code bereits gelebte Default
(`controller/app-panel/app.js:578-582`: leerer `router_url` → Browser nimmt die
Origin der Seite; die Demo-`config.json` nutzt das).

Ein **abweichender** `router_url` (ein cross-origin Geräte-Profil, bei dem die
Panel-Seite von einer anderen Origin geladen wird als der Router) ist V1
**nicht** der Normalfall und wird erst über das Geräte-Profil-Onboarding
gesetzt (siehe OPEN-PREG-E, Bezug #82). Ein leerer `router_url` ist **kein**
„kaputt"-Zustand und blockiert eine same-origin-Panel-Instanz nicht.

*Tickets:* #58

## 4. HTTP-API

> Analog zur Geräte-Registry-API (`geraete.md` GER-13/14/15). Der Service
> `xbuddy-panel` stellt seine Schnittstelle unter dem Origin-Prefix
> `/api/v1/panels/` bereit (URL-14-Satellit, siehe Handoff). Jeder Lesevorgang
> liest `panels.json` **frisch von Disk** (DCOMP-2 Reload-on-Read), damit
> Schreibvorgänge ohne Service-Restart sichtbar werden; bei Lesefehler greift
> Last-Known-Good (DCOMP-3 / E-RELOAD-1). Konsumenten reden ausschließlich über
> HTTP, nicht über `import` (DCOMP-1).

### PREG-13 — `GET /api/v1/panels/` liefert alle Panel-Instanzen
`GET /api/v1/panels/` liefert alle Panel-Instanzen der Familie als JSON-Array —
je Instanz die PREG-3-Felder, in der Reihenfolge der Registry-Datei.

*Tickets:* #58

### PREG-14 — `GET /api/v1/panels/<panel_id>` liefert eine Instanz
`GET /api/v1/panels/<panel_id>` liefert die PREG-3-Felder genau einer
Panel-Instanz als JSON. Unbekannte `panel_id`: 404 mit JSON-Fehler
`{"error": "unbekannte panel_id"}` — kein 500, kein Stack-Trace.

Zusätzlich stellt der Service die beiden Serving-Sichten bereit, die der Router
proxyt (PREG-9):

- `GET /api/v1/panels/<panel_id>/config.json` — liefert das `config`-Feld
  (PANEL-8) der Instanz als eigenständiges JSON-Dokument, in genau der Form,
  die die Panel-Seite per `fetch('./config.json')` erwartet.
- `GET /api/v1/panels/<panel_id>/tiles.json` — liefert das `tiles`-Feld
  (PANEL-3) der Instanz als eigenständiges JSON-Dokument, in genau der Form,
  die die Panel-Seite per `fetch('./tiles.json')` erwartet.

Unbekannte `panel_id` ist auch hier 404 mit JSON-Fehler.

*Tickets:* #58

### PREG-15 — `POST /api/v1/panels/` legt eine Panel-Instanz an
`POST /api/v1/panels/` mit JSON-Body `{slug, display_id, router_url?, config?,
tiles?}` legt eine neue Panel-Instanz an und liefert die angelegte Instanz als
JSON inkl. vergebener `panel_id` und abgeleitetem `source_id`. Erfüllt
OPEN-PANEL-C der App-Panel-Spec (Panel-Instanz-Setup über eine Schnittstelle
statt manueller Datei-Pflege).

- Pflichtfelder: `slug` (Basis der `panel_id`, PREG-6), `display_id`
  (gegen die Geräte-Registry validiert, PREG-7).
- Optional: `router_url` (Default leer = same-origin, PREG-8); `config`
  (PANEL-8-Felder; fehlt es, gelten die Panel-Code-Defaults plus die aus
  `panel_id`/`source_id`/`display_id` abgeleiteten Pflichtwerte); `tiles`
  (PANEL-3; fehlt es, startet die Instanz mit leerer Kachel-Liste —
  die Aus-Kachel rendert die Seite auch dann, PANEL-6).
- Die `panel_id` vergibt der Server kollisionsfrei nach PREG-6 — der Client
  liefert sie **nicht**, sondern nur den `slug`.

Validierungsfehler (fehlendes Pflichtfeld, `display_id` in der Geräte-Registry
unbekannt nach PREG-7, verschachteltes `query` in `tiles` entgegen PANEL-7) sind
**400** mit JSON-Fehler. Geräte-Registry nicht erreichbar (PREG-7) ist **503**.
Disk-Schreibfehler (Datei nicht schreibbar, DCOMP-4-Pfad scheitert) sind
**503** mit JSON-Fehler — in beiden 503-Fällen bleibt `panels.json` unverändert.

Parallele POSTs werden serialisiert (Read-Modify-Write hinter einem Schreib-Lock),
damit zwei Threads zwei **verschiedene** `panel_id`s bekommen und beide Einträge
landen — kein verlorengehendes Update (analog GER-15). Geschrieben wird atomar
nach DCOMP-4.

*Tickets:* #58

## 5. Router-Anbindung (Serving)

### PREG-9 — Router proxyt und cacht das Instanz-Serving
Der Router serviert die Panel-Seite weiter wie heute: `index.html` und den
statischen Panel-Code unter `/controller/app-panel/<id>` (PANEL-2, URL-14
Eintrag 8, `router/main.py` Asset-Serving). **Neu**: die beiden
instanz-spezifischen Datendateien holt der Router nicht mehr aus dem
Auslieferungs-Verzeichnis, sondern **proxyt** sie an den panel-Service:

- `GET /controller/app-panel/<id>/config.json`
  → `GET /api/v1/panels/<id>/config.json` am panel-Service (PREG-14),
- `GET /controller/app-panel/<id>/tiles.json`
  → `GET /api/v1/panels/<id>/tiles.json` am panel-Service (PREG-14).

`<id>` (= `panel_id`) ist dabei load-bearing: er wählt die Instanz. Der
Panel-Code bleibt unverändert — er lädt weiter `./config.json` und
`./tiles.json` relativ zu seiner eigenen URL (PANEL-8 / PANEL-3); dass der
Router diese zwei Pfade an den panel-Service weiterreicht statt aus einer Datei
zu lesen, ist für die Seite transparent.

**Last-Known-Good-Cache (Härtung Welle 1).** Der Router hält die zuletzt
erfolgreich vom panel-Service geholte `config.json`/`tiles.json` je `panel_id`
als Snapshot und serviert diesen Snapshot, **wenn der panel-Service
vorübergehend nicht erreichbar ist oder fehlerhaft antwortet** — gleicher Geist
wie ROU-25 / DCOMP-3 (E-RELOAD-1). Begründung (Härtung aus der Ratifizierung):
ohne Cache lädt ein Controller bei panel-Service-Ausfall die Demo-Defaults und
eine leere Kachel-Liste (`config.js`, `app.js`) — ein bestückter Familien-Bildschirm
würde leer. Fehlt auch der Snapshot (Service war seit Router-Start nie
erreichbar), fällt die Seite auf ihre Code-Defaults zurück (PANEL-8, stiller
Fallback) — kein Crash.

*Tickets:* #58

### PREG-10 — Panel-bezogene Router-Schreib-/Reload-Kante ist loopback-/`/admin/`-geschützt
Jede panel-bezogene Schreib-/Reload-Kante des Routers — etwa eine
Cache-Invalidierung oder ein Cache-Refresh-Trigger für den PREG-9-Cache — liegt
unter dem `/admin/`-Pfad und ist **loopback-only** — genau wie der Admin-Reload
des Routers
(`POST /api/v1/router/admin/reload`, ROU-18-Body, `router/main.py`). nginx
blockt `/admin/` von außen (`deploy/nginx/xbuddy-origin.conf`), sodass die Kante
**nicht** offen im Familien-LAN steht. **Nur der panel-Service** ruft sie über
Loopback; kein Controller-Gerät und kein Familienmitglied erreicht sie.

Ob V1 überhaupt eine aktive Invalidierungs-Kante exponiert oder der
Last-Known-Good-Cache (PREG-9) rein upstream-first mit Fallback arbeitet (und
damit **keine** panel-bezogene Schreib-Kante nötig ist), legt der
`router.md`-Satellit fest (OPEN-PREG-F). Die hier festgelegte
loopback-/`/admin/`-Invariante gilt für jede exponierte Kante unabhängig davon;
PREG-12 prüft sie als **Negativ-Test** (eine externe, nicht-Loopback-Origin
erreicht die Kante nicht).

Begründung (Muss-Korrektur aus der Ratifizierung): eine Schreib-/Reload-Kante,
die offen im LAN steht, ließe jedes Gerät im Heim-Netz den Router-Cache
manipulieren — der Heim-Server hat keine LAN-interne Authentifizierung, die
loopback-/`/admin/`-Schranke ist das etablierte Schutzmuster (ROU-Admin-Reload).

*Tickets:* #58

## 6. Konfiguration

### PREG-11 — Konfigurationswerte
Familienspezifische Werte (die Panel-Instanzen selbst) leben in `panels.json`
(PREG-4). Der Pfad zur Registry-Datei und die Adressen der Nachbar-Services
können nicht in der Datei stehen und bleiben Env/CLI. Die Tabelle folgt der
Konfigurations-Konvention [`conventions/config.md`](../../conventions/config.md)
CONFIG-2: jeder Wert hat einen Default und eine Quelle.

| Wert                 | Default                          | Quelle                                              |
|----------------------|----------------------------------|-----------------------------------------------------|
| Registry-Datei       | `panels.json` neben dem Code     | Env (`PANELS_REGISTRY`) · CLI (`--panels`)          |
| Geräte-Registry-URL  | `http://127.0.0.1:5040`          | Env (`GERAETE_URL`) · CLI (`--geraete-url`)         |

Der eigene Loopback-Port des Service `xbuddy-panel` ist **kein** Config-Wert in
dieser Tabelle, sondern fest im Port-Katalog (PORT-2) vergeben — er ist ein
Plattform-Port, nicht aus dem Buddy-Reserveblock 5050-5099 (Muss-Korrektur:
`5050` ff. ist Buddys vorbehalten, dorthin zielt der Wetter-Buddy). Die
konkrete Port-Zeile setzt der `ports.md`-Satellit (siehe Handoff).

*Tickets:* #58

## 7. Tests

### PREG-12 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), ohne Netz (Geräte-Registry und Router werden gestubbt).
Mindest-Abdeckung:

- **PREG-4** — fehlende `panels.json` → Warnung, leere Panel-Liste, kein
  Crash; Datei mit Panels → alle PREG-3-Felder geladen; Schreiben setzt `0600`.
- **PREG-5** — eine simulierte Tile-Änderung (OPEN-PREG-A-Vorgriff im Test)
  berührt `config` byte-gleich nicht; eine Anlage setzt beide Felder.
- **PREG-6** — `panel_id` folgt IDENT-1/`<slug>-<nn>`; eine in dieser Instanz
  bereits vergebene `panel_id` wird nicht erneut vergeben; zwei Anlagen mit
  gleichem `slug` ergeben `<slug>-01` und `<slug>-02`.
- **PREG-7** — Anlage mit einem `display_id`, das die (gestubbte)
  Geräte-Registry kennt, gelingt; unbekanntes `display_id` ist 400;
  Geräte-Registry nicht erreichbar ist 503; es wird **nicht** gegen
  `known_displays`/`routing.json` validiert.
- **PREG-8** — fehlender/leerer `router_url` wird als same-origin gespeichert
  und über die API leer zurückgegeben (kein Default-Host eingesetzt).
- **PREG-9** — `GET /controller/app-panel/<id>/config.json|tiles.json` liefert
  die Instanz-Daten des panel-Service; bei simuliertem panel-Service-Ausfall
  liefert der Router den Last-Known-Good-Snapshot; ohne je erfolgreichen Abruf
  fällt die Seite auf Code-Defaults zurück (kein Crash).
- **PREG-10** — die Router-Schreib-/Reload-Kante antwortet auf Loopback,
  ist über die externe Origin (nicht-Loopback / ohne `/admin/`-Freigabe) **nicht**
  erreichbar.
- **PREG-13** — `GET /api/v1/panels/` liefert alle Instanzen als JSON-Array.
- **PREG-14** — `GET /api/v1/panels/<id>` liefert die passende Instanz;
  unbekannte `panel_id` ist 404; die `/config.json`- und `/tiles.json`-Sichten
  liefern die jeweiligen Felder als eigenständiges Dokument.
- **PREG-15** — POST mit gültigem Body liefert 200 + IDENT-1-`panel_id` und
  persistiert atomar; POST ohne `slug`/`display_id` ist 400; POST mit
  unbekanntem `display_id` ist 400; POST bei nicht erreichbarer Geräte-Registry
  ist 503; parallele POSTs ergeben zwei verschiedene `panel_id`s (beide
  persistiert).

*Tickets:* #58

---

## Offene Punkte

- **OPEN-PREG-A — Kopieren/Löschen/Tile-Editing über die Schnittstelle
  (Welle 2).** V1 hat Anlegen (PREG-15) und Lesen (PREG-13/14). Eine Panel-Instanz
  kopieren, hart löschen oder ihre `tiles` über die API ändern (unter Wahrung
  von PREG-5: `config` bleibt unberührt) ist Welle 2. Das Datenmodell (PREG-5,
  stabile `key`-Felder aus PANEL-3) ist bereits darauf vorbereitet.

- **OPEN-PREG-B — Reconcile-/Reparatur-Pfad für die 2-Schritt-Anlage
  (Welle 2).** Eine Panel-Instanz vollständig betriebsbereit zu machen heißt
  heute zwei verteilte Schritte: (1) den `panels.json`-Eintrag (PREG-15) und
  (2) den zugehörigen `panels`-Eintrag in der Router-`routing.json` (ROU-18),
  über den der Adapter (ROU-24) das `tile_selected`/`panel_cleared` auf die
  richtige `display_id` setzt. Reißt einer der beiden Schritte ab, ist die
  Instanz halb angelegt. Ein Reconcile-/Reparatur-Pfad (Soll-Abgleich + Nachzug
  des fehlenden Schritts) ist **Welle 2** — von Nic in der Ratifizierung
  ausdrücklich als „vollkommen vertretbar" für später eingeordnet. **Nic-Frage:**
  bestätigen, dass V1 ohne automatischen Reconcile ausgeliefert wird (manuelles
  Nachziehen des Routing-Eintrags akzeptabel).

- **OPEN-PREG-C — Eltern-Chat-Skill „Panel anlegen" (Welle 2) braucht einen
  namentlichen `handle_update`-Routing-Block.** Der spätere Skill, der eine
  Panel-Instanz per Telegram anlegt (+ ein `panel_client.py`, das PREG-15
  ruft), ist Welle 2 und hier **nicht** spezifiziert. **Vorbedingung, die nicht
  vergessen werden darf:** Ist der Skill eine async-schreibende Aufgabe mit
  Worker-Thread, genügt die Registrierung in `build_catalog` **nicht** — er
  braucht zusätzlich einen **namentlichen Routing-Block in `handle_update`**
  mit der richtigen Session-Map (`conventions/tasks.md` TASK-7,
  `tasks.py:253-380` / `main.py:107-140`) und einen Test, der das
  Privatchat-Routing durch `handle_update` prüft — nicht nur die
  Katalog-Anwesenheit. Sonst ist der Skill registriert, aber die Familie landet
  nie beim Worker (die stille Lego-Falle aus TASK-7).

- **OPEN-PREG-D — Tile-Sets und optionales `geraet_id`-Metadatum (Welle 2).**
  Benannte, wiederverwendbare Kachel-Sätze und ein optionales `geraet_id`,
  das festhält, auf welchem Controller-Gerät (GER) eine Panel-WebAPK installiert
  ist, sind Welle 2. V1 bindet eine Panel-Instanz nur an ihr **Display**, nicht
  an ihr Controller-Gerät (PREG-2).

- **OPEN-PREG-E — Cross-origin `router_url` via Geräte-Profil (#82).** Ein von
  same-origin abweichender `router_url` (PREG-8) — nötig, wenn die Panel-Seite
  von einer anderen Origin geladen wird als der Router — wird **später** über
  das Geräte-Profil-Onboarding gesetzt (#82, „CA-/Geräte-Profil pro Gerät").
  Das blockiert eine same-origin-Panel-Instanz in V1 **nicht**: leerer
  `router_url` ist der gültige Normalfall, kein Wartezustand. **Nic-Frage:**
  bestätigen, dass V1 ausschließlich same-origin-Panels adressiert und der
  cross-origin-Fall erst mit #82 kommt.

- **OPEN-PREG-F — Cache-Invalidierungs-Mechanik des Routers (PREG-9/PREG-10).**
  Ob der Last-Known-Good-Cache (PREG-9) rein upstream-first arbeitet (jeder
  erfolgreiche Proxy-Abruf frischt den Snapshot, der Cache dient nur als
  Ausfall-Fallback — dann ist **keine** aktive Schreib-/Invalidierungs-Kante
  nötig) oder ob beim `panels.json`-Schreiben eine explizite Invalidierung
  ausgelöst wird, legt der `router.md`-Satellit fest, wenn dort die
  Router-Caching-Strategie spezifiziert wird. PREG-10 legt nur die
  Sicherheits-Invariante fest (jede exponierte Kante loopback-/`/admin/`-only),
  unabhängig von dieser Wahl.

---

## Bezug

- **Analog-Vorlage:** `geraete.md` (GER-Registry-Pattern — eigener
  Daten-Service, Per-Instanz-Datei, Lese-/Schreib-Schnittstelle GER-13/14/15,
  atomares Schreiben, Reload-on-Read).
- **Konsument & Serving-Partner:** `router.md` ROU-18 (`panels`-Abschnitt der
  `routing.json`), ROU-24 (App-Panel-Adapter), ROU-25 (E-RELOAD-1) — der Router
  proxyt/cacht das Instanz-Serving (PREG-9) und schützt seine Schreib-Kante
  (PREG-10).
- **Serving-Seite:** `app-panel.md` PANEL-2 (URL-Verortung), PANEL-3 (`tiles`),
  PANEL-8 (`config`, OPEN-PANEL-C wird durch PREG-15 erfüllt), E-PANEL-3
  (Daten/Tuning-Trennung → PREG-5), E-PANEL-5 (ein Panel = ein Display →
  `display_id` Singular).
- **Validierungs-Quelle:** `geraete.md` GER-14 (Display-Existenz, PREG-7).
- **Bauregeln:** `conventions/data-components.md` DCOMP-1 (HTTP statt Import),
  DCOMP-2 (Reload-on-Read), DCOMP-3 (Last-Known-Good), DCOMP-4 (atomares
  Schreiben); `conventions/ports.md` PORT-1/2 (Plattform-Port, kein
  Buddy-Reserveblock); `conventions/urls.md` URL-14 (Origin-Routing-Tabelle);
  `conventions/identifiers.md` IDENT-1 (`panel_id`-Form).
- **Welle-2-Vorbedingung:** `conventions/tasks.md` TASK-7 (namentlicher
  `handle_update`-Routing-Block für den späteren Anlage-Skill, OPEN-PREG-C).
- **Hängt an:** der Geräte-Registry (GER, für PREG-7). Andere Tickets hängen an
  dieser Spec (der Welle-2-Eltern-Chat-Skill, OPEN-PREG-C).
