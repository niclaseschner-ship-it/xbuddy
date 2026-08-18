# Panel-Registry — Spec     (ID-Präfix: PREG)

> Status: V1-Entwurf · Refs #58 (App-Panel) · ratifiziert 2026-06-03
> (`decisions/RAT-1`)

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
gehören zu dieser Familie" und liefert je Panel stabile Identität und die
Kachel-Konfiguration. Sie besitzt diese Daten; die Panel-Seite ist ihr Nutzer.

> **RAT-31 E6a (2026-07-27):** Die Multi-Geräte-Wirbelsäule ist abgerissen
> (ein Gerät für immer). Die Panel-Registry ist auf eine reine
> **tiles/config/panel_id-Registry** eingedampft. Die frühere Display-Bindung
> (`display_id`), die Router-Origin (`router_url`), die Display-Validierung
> (PREG-7), das Router-Proxy-Serving (PREG-9), die loopback-geschützte
> Router-Schreib-Kante (PREG-10) und der verteilte Reconcile-Pfad
> (Forward/Repair, PREG-16/17/18, ROU-29) **entfallen**. Governance:
> `decisions/RAT-31-wirbelsaeule-abriss.md`, Epic #1339.

**Scope:** Der Service `xbuddy-panel` mit `panels.json`; je Panel die Felder aus
PREG-3 (`panel_id`, `source_id`, `config`, `tiles`); eine Lese- und eine
Schreib-Schnittstelle (HTTP); der PBE-4-Editor je Panel-Instanz.

**Out-of-Scope** (je eigenes Ticket): Kopieren/Löschen einer Panel-Instanz
über die Schnittstelle — OPEN-PREG-A · benannte Tile-Sets — OPEN-PREG-D.

## 1. Reichweite

### PREG-1 — Eine Instanz, eine Panel-Registry
Die Registry einer XBuddy-Instanz beschreibt genau die App-Panels einer
Familie — der Familie des Hubs, auf dem die Instanz läuft. Es gibt keinen
familienübergreifenden Bezeichner und keinen Cross-Familie-Zugriff. Konsistent
mit `geraete.md` GER-1 und `familie.md` FAM-1.

*Tickets:* #58

### PREG-2 — Mehrere Panels, je eigene Identität
Es kann **mehrere** Panel-Instanzen geben — jede unter einer eigenen,
unabhängigen `panel_id` und damit unter einer eigenen URL
`/controller/app-panel/<panel_id>` (PANEL-2), als je eigene WebAPK
installierbar (PWA-1). Die `panel_id` ist load-bearing: sie ist das Segment,
über das die zugehörige `config.json`/`tiles.json` der richtigen Instanz
zugeordnet wird.

Verschiedene Panel-Instanzen sind schlicht mehrere `panels.json`-Einträge mit
verschiedenen `panel_id`s.

*Tickets:* #58

## 2. Panel-Modell

### PREG-3 — Eigenschaften einer Panel-Instanz
Jede Panel-Instanz trägt:

| Feld          | Pflicht  | Werte                                                       | Bedeutung |
|---------------|----------|-------------------------------------------------------------|-----------|
| `panel_id`    | Pflicht  | stabiler Slug nach PREG-6 (`<slug>-<nn>`)                   | Stabiler, eindeutiger Bezeichner der Panel-Instanz. Wird nie neu vergeben. Das `<id>`-Segment aus `/controller/app-panel/<id>` (PANEL-2). |
| `source_id`   | Pflicht  | `app-panel:<panel_id>`                                       | Identität im Event-Sinn (PANEL-6). Aus `panel_id` abgeleitet, in der Datei als eigenes Feld geführt, damit Konsumenten nicht parsen müssen. |
| `config`      | Pflicht  | `config.json`-Objekt nach PANEL-8 (Tuning)                  | Die Pro-Instanz-Konfiguration der Panel-Seite. **Nicht übermalbar** durch einen Tile-Schreiber (E-PANEL-3, PREG-5). |
| `tiles`       | Pflicht  | `tiles.json`-Objekt nach PANEL-3 (Daten)                    | Die Kachel-Liste der Panel-Instanz. **Änderbar** durch einen Tile-Schreiber (E-PANEL-3, PBE-4), ohne `config` zu berühren. |

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
mit leerer Panel-Liste weiter, statt abzubrechen (symmetrisch zu FAM-6). Ein
Konsument, dessen Antwort von einer unbekannten `panel_id` abhängt, behandelt
das im eigenen Kontext.

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

Zusätzlich stellt der Service die beiden Serving-Sichten bereit:

- `GET /api/v1/panels/<panel_id>/config.json` — liefert das `config`-Feld
  (PANEL-8) der Instanz als eigenständiges JSON-Dokument, in genau der Form,
  die die Panel-Seite per `fetch('./config.json')` erwartet.
- `GET /api/v1/panels/<panel_id>/tiles.json` — liefert das `tiles`-Feld
  (PANEL-3) der Instanz als eigenständiges JSON-Dokument, in genau der Form,
  die die Panel-Seite per `fetch('./tiles.json')` erwartet.

Unbekannte `panel_id` ist auch hier 404 mit JSON-Fehler.

*Tickets:* #58

### PREG-15 — `POST /api/v1/panels/` legt eine Panel-Instanz an
`POST /api/v1/panels/` mit JSON-Body `{slug, config?, tiles?}` legt eine neue
Panel-Instanz an und liefert die angelegte Instanz als JSON inkl. vergebener
`panel_id` und abgeleitetem `source_id`. Erfüllt OPEN-PANEL-C der App-Panel-Spec
(Panel-Instanz-Setup über eine Schnittstelle statt manueller Datei-Pflege).

- Pflichtfeld: `slug` (Basis der `panel_id`, PREG-6).
- Optional: `config` (Tuning-Objekt, s. u.); `tiles`
  (PANEL-3; fehlt es, startet die Instanz mit leerer Kachel-Liste —
  die Aus-Kachel rendert die Seite auch dann, PANEL-6).
- Die `panel_id` vergibt der Server kollisionsfrei nach PREG-6 — der Client
  liefert sie **nicht**, sondern nur den `slug`.

**Server-autoritativer `config`-Aufbau (Nic-Entscheid 2026-06-03):**
Das `config`-Identitätsfeld `source_id` ist **server-autoritativ** — der Server
leitet es selbst ab und schreibt es in jedem Fall in die gespeicherte `config`,
unabhängig davon, ob der Aufrufer eine `config` mitgibt oder nicht:

- `config.source_id` = `app-panel:<panel_id>` (PREG-3, PANEL-6) — aus der
  server-vergebenen `panel_id` abgeleitet.

Eine vom Aufrufer mitgegebene `config` liefert **nur Tuning** (z. B. `backoffs`,
künftige PANEL-8-Erweiterungen). Die Merge-Regel ist: `{<Aufrufer-Tuning>,
<server-Identität>}` — das server-gesetzte `source_id` überschreibt immer, auch
wenn der Aufrufer es bereits gesetzt hätte.

Ein POST **ohne** `config` liefert eine gespeicherte `config` mit genau dem
`source_id`-Feld — nie mehr das leere Objekt `{}`. Ein POST **mit** `config`
(z. B. `{"backoffs": [200]}`) liefert `{"backoffs": [200], "source_id": …}`.

Validierungsfehler (fehlendes Pflichtfeld, verschachteltes `query` in `tiles`
entgegen PANEL-7) sind **400** mit JSON-Fehler. Disk-Schreibfehler (Datei nicht
schreibbar, DCOMP-4-Pfad scheitert) sind **503** mit JSON-Fehler — `panels.json`
bleibt dann unverändert.

Parallele POSTs werden serialisiert (Read-Modify-Write hinter einem Schreib-Lock),
damit zwei Threads zwei **verschiedene** `panel_id`s bekommen und beide Einträge
landen — kein verlorengehendes Update (analog GER-15). Geschrieben wird atomar
nach DCOMP-4.

*Tickets:* #58

## 6. Konfiguration

### PREG-11 — Konfigurationswerte
Familienspezifische Werte (die Panel-Instanzen selbst) leben in `panels.json`
(PREG-4). Der Pfad zur Registry-Datei kann nicht in der Datei stehen und bleibt
Env/CLI. Die Tabelle folgt der Konfigurations-Konvention
[`conventions/config.md`](../../conventions/config.md) CONFIG-2: jeder Wert hat
einen Default und eine Quelle.

| Wert                 | Default                          | Quelle                                              |
|----------------------|----------------------------------|-----------------------------------------------------|
| Registry-Datei       | `panels.json` neben dem Code     | Env (`PANELS_REGISTRY`) · CLI (`--panels`)          |

Der eigene Loopback-Port des Service `xbuddy-panel` ist **kein** Config-Wert in
dieser Tabelle, sondern fest im Port-Katalog (PORT-2) vergeben — er ist ein
Plattform-Port, nicht aus dem Buddy-Reserveblock 5050-5099 (Muss-Korrektur:
`5050` ff. ist Buddys vorbehalten, dorthin zielt der Wetter-Buddy). Die
konkrete Port-Zeile setzt der `ports.md`-Satellit (siehe Handoff).

*Tickets:* #58

## 7. Tests

### PREG-12 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), ohne Netz. Mindest-Abdeckung:

- **PREG-4** — fehlende `panels.json` → Warnung, leere Panel-Liste, kein
  Crash; Datei mit Panels → alle PREG-3-Felder geladen; Schreiben setzt `0600`.
- **PREG-5** — eine Tile-Änderung berührt `config` byte-gleich nicht; eine
  Anlage setzt beide Felder.
- **PREG-6** — `panel_id` folgt IDENT-1/`<slug>-<nn>`; eine in dieser Instanz
  bereits vergebene `panel_id` wird nicht erneut vergeben; zwei Anlagen mit
  gleichem `slug` ergeben `<slug>-01` und `<slug>-02`.
- **PREG-13** — `GET /api/v1/panels/` liefert alle Instanzen als JSON-Array.
- **PREG-14** — `GET /api/v1/panels/<id>` liefert die passende Instanz;
  unbekannte `panel_id` ist 404; die `/config.json`- und `/tiles.json`-Sichten
  liefern die jeweiligen Felder als eigenständiges Dokument.
- **PREG-15** — POST mit gültigem Body liefert 200 + IDENT-1-`panel_id` und
  persistiert atomar; POST ohne `slug` ist 400; parallele POSTs ergeben zwei
  verschiedene `panel_id`s (beide persistiert); POST **ohne** `config` liefert
  eine `config` mit `source_id` — nie `{}`; POST **mit** Tuning-`config`
  (z. B. `backoffs`) → Tuning bleibt erhalten + `source_id` server-gesetzt;
  `config.source_id == app-panel:<panel_id>` (PANEL-8-Konsistenz).

*Tickets:* #58

---

## Offene Punkte

- **OPEN-PREG-A — Kopieren/Löschen einer Panel-Instanz über die Schnittstelle.**
  Anlegen (PREG-15), Lesen (PREG-13/14) und Tile-Editing (PBE-4) sind da. Eine
  Panel-Instanz kopieren oder hart löschen ist noch offen. Das Datenmodell
  (PREG-5, stabile `key`-Felder aus PANEL-3) ist bereits darauf vorbereitet.

- **OPEN-PREG-D — Benannte Tile-Sets.** Benannte, wiederverwendbare
  Kachel-Sätze sind noch offen — additiv, sobald der Bedarf belegt ist.

> **RAT-31 E6a — entfernt:** OPEN-PREG-B (Reconcile-Pfad), OPEN-PREG-C
> (Eltern-Chat-Skill `panel_anlegen`), OPEN-PREG-E (cross-origin `router_url`),
> OPEN-PREG-F (Router-Cache-Invalidierung) und der `repair_trigger`-Eintrag
> bezogen sich alle auf die abgerissene Display-/Router-Wirbelsäule und sind mit
> ihr entfallen. Governance: `decisions/RAT-31-wirbelsaeule-abriss.md`.

---

## Bezug

- **Serving-Seite:** `app-panel.md` PANEL-2 (URL-Verortung), PANEL-3 (`tiles`),
  PANEL-8 (`config`, OPEN-PANEL-C wird durch PREG-15 erfüllt), E-PANEL-3
  (Daten/Tuning-Trennung → PREG-5). PBE-4 (Tile-Editor je Instanz).
- **Bauregeln:** `conventions/data-components.md` DCOMP-1 (HTTP statt Import),
  DCOMP-2 (Reload-on-Read), DCOMP-3 (Last-Known-Good), DCOMP-4 (atomares
  Schreiben); `conventions/ports.md` PORT-1/2 (Plattform-Port, kein
  Buddy-Reserveblock); `conventions/urls.md` URL-14 (Origin-Routing-Tabelle);
  `conventions/identifiers.md` IDENT-1 (`panel_id`-Form).
