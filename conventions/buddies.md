# Buddies — Konvention     (ID-Präfix: BUD)

Ein **Buddy** ist eine XBuddy-App mit eigener **Display-View** für die
Familie (Plan-Buddy, Wetter-Buddy, …). Diese Konvention legt fest, wie ein
Buddy gebaut wird und wo er im System auftauchen muss. Sie zitiert die
allgemeinen App-Regeln ([`apps.md`](apps.md), APP-1..6) sowie URL-, Port-,
Service-, Config- und Modul-Konventionen — sie **dupliziert** keine von ihnen.

Warum ein eigenes Präfix neben APP: [`apps.md`](apps.md) regelt das
Eigentums-**Prinzip** und gilt auch für Nicht-Display-Apps. Ein Buddy ist die
Unterklasse „App **mit** Display-View" (Verortung: APP-6). BUD bündelt, was
zusätzlich gilt, sobald eine App eine Display-View für die Familie rendert.

**Leitsatz:** *Buddy = Slug + Display-Pfad. Alles andere folgt aus dem, was der
Buddy zusätzlich **tut**, nicht aus seiner Buddy-Eigenschaft.*

> **Genre-Grenze (was diese Konvention NICHT abdeckt):** BUD deckt bewusst nur
> die **Display-Seite** eines Buddys vollständig ab. Der familienseitige
> Beitrag eines Buddys (eine Aufgabe im Eltern-Chat — Skill-Adapter,
> `build_catalog`, Task-Tests) ist hier **aufgeschoben**, nicht stillschweigend
> weggelassen: Wohnort und Pflege regelt [`apps.md`](apps.md) APP-4, die heutige
> V1-Heimat der Aktivierung ist `build_catalog` ([`tasks.md`](tasks.md) TASK-7),
> aber der Installations-/Aktivierungs-Mechanismus existiert noch nicht als
> spezifizierter Prozess (offenes Problem #296 — App-Installations-Prozess für
> die Familien-Schnittstelle fehlt). Ein Buddy mit familienseitigem Beitrag
> muss bis #296 den Eltern-Chat-Mittelpunkt punktuell mit anfassen (konkretes
> Beispiel: #328 — Ort/Garderobe des Wetter-Buddys über den Eltern-Chat
> pflegbar machen); sobald #296 entschieden ist, bekommt BUD eine „nur wenn
> familienseitiger Beitrag"-Regel dafür.

## Die Regeln — „immer" vs. „nur wenn"

Die mit **immer** markierten Regeln gelten für jeden Buddy. Die mit
**nur wenn** markierten hängen daran, was der Buddy zusätzlich tut — eine
nicht zutreffende Regel wird nicht zur leeren Pflicht (sonst Heim-Server-
Overhead, Anti-Goal). Beispiele für „nur wenn" leben in den Buddy-Specs
unter [`../specs/buddies/`](../specs/buddies/), nicht hier.

### BUD-1 — Slug + Display-Pfad (immer)
Ein Buddy hat einen stabilen **Slug** und rendert unter genau einem
**Display-Pfad** `/display/<slug>/<view>` ([`urls.md`](urls.md) URL-2). Der
Pfad benennt eine View, kein Verb; Varianten sind Query-Parameter (URL-2,
URL-8). Statische Assets liegen im Display-Namensraum des Buddys
`/display/<slug>/static/<asset>` (URL-13), nicht unter einem eigenen
Top-Level-Pfad.

### BUD-1a — Eigener Prozess (nur wenn der Buddy einen eigenen Service braucht)
Läuft der Buddy als eigener Prozess (typischerweise als Flask-Service),
dann braucht er
- eine **feste Port-Nummer** aus dem Loopback-Block, eingetragen im Katalog
  [`ports.md`](ports.md) PORT-2 (Bindung nur an `127.0.0.1`, PORT-3);
- eine **systemd-Service-Vorlage** `xbuddy-<slug>.service` neben dem Code
  ([`services.md`](services.md) SVC-1/SVC-2, `Restart=on-failure` SVC-3,
  Logs an stdout/stderr SVC-4);
- eine **Zeile in der Origin-Routing-Tabelle** [`urls.md`](urls.md) URL-14,
  die `/display/<slug>/` auf diesen Upstream-Port abbildet.

Ein reiner Display-Buddy, der keinen eigenen Prozess betreibt (z. B. eine
View, die der Router selbst rendert), braucht das nicht.

### BUD-1b — Eigene API (nur wenn andere Apps Daten des Buddys konsumieren)
Stellt der Buddy Daten oder Funktion für andere Apps/Konsumenten bereit, dann
unter einem **API-Pfad** `/api/v1/<slug>/<resource>` ([`urls.md`](urls.md)
URL-4) mit eigener Zeile in der Origin-Routing-Tabelle (URL-14, spezifischer
API-Prefix vor dem allgemeinen `/api/v1/`-Eintrag). Fremde Apps sprechen den
Buddy nur über diese Schnittstelle an, nie über Datei-Zugriff
([`apps.md`](apps.md) APP-3).

Gibt es keinen Konsumenten, gibt es **keine** API — eine API auf Vorrat ist
Heim-Server-Overhead (Anti-Goal).

### BUD-2 — Per-Instanz-Config (immer)
Ein Buddy hat eine **Per-Instanz-Config-Datei** neben dem Code
([`config.md`](config.md) CONFIG-1, gitignored), keine hartcodierten Pfade,
IDs oder Familien-Namen (Familie-3-Probe). Werte fehlen → Code-Default greift
mit Warnung, der Prozess startet weiter (CONFIG-4). ENV-Overrides folgen
`<SLUG>_<KEY>` (CONFIG-5). Die Buddy-Spec listet jeden Wert mit Default und
Onboarding-Pfad (CONFIG-2).

### BUD-2a — Domänendaten getrennt von Config (nur wenn der Eltern-Chat Domänendaten schreibt)
Schreibt der Eltern-Chat **Domänendaten** in den Buddy (z. B. Termine), liegen
diese **getrennt** von der Runtime-Config — analog `plan.json` ⟂ `config.json`.
Hat ein Buddy keine vom Eltern-Chat geschriebenen Domänendaten, gibt es EINE
Config-Datei und keine leere Pflicht-Datendatei.

### BUD-2b — Per-Instanz-Daten-Ausschluss lebt beim Buddy (immer dort, wo BUD-2 oder BUD-2a existiert)
Der Ausschluss der Per-Instanz-Dateien (BUD-2 Runtime-Config; BUD-2a
Domänendaten) lebt als **`<slug>/.gitignore`** **neben dem Code**, nicht in
einem zentralen Top-Level-`.gitignore`. Ein Buddy bringt seinen eigenen
Ausschluss mit — analog zur Service-Datei (SVC-2) und zum Manifest (BUD-3).
So bleibt jeder Buddy **standalone übertragbar** (Familie-3-Probe): wer einen
Buddy kopiert oder entfernt, fasst genau ein Verzeichnis an, nicht zwei
Orte. Ein bewusst gewollter repo-weiter Ausschluss (`__pycache__`, `*.pyc`,
generische Artefakte) bleibt im Top-Level-`.gitignore` — der ist nicht
buddy-spezifisch.

### BUD-3 — Aufrufbare Views als committetes Manifest deklarieren (immer, sobald der Buddy Display-Views hat)
Ein Buddy/Controller mit menschen-aufrufbaren View-Einstiegspunkten committet
ein **`views.json`-Manifest** neben dem Code — **committet, nicht gitignored**
(anders als die Per-Instanz-Config, BUD-2). Es deklariert je View: `slug`,
`pfad`, `label`, `synonyme[]`, `zeigt` (1 Satz, was die Seite zeigt), optional
`varianten[]` (endliche bekannte Query-Varianten, je `slug`/`query`/`label`),
`zielgruppe` (`kind`/`eltern`, deskriptiv). Das sind genau die manifest-
gelieferten Felder des SREG-4-Eintragsschemas; `key`/`typ`/`app` leitet der
Aggregator ab.

**Eigentest bindet das Manifest an den Code** — je nach Komponententyp:
- **Buddy mit eigenen Flask-Display-Routen:** jede **HTML-rendernde GET-Route**
  unter `/display/<slug>/…` hat **genau einen** Manifest-Eintrag und umgekehrt.
  **Ausgenommen:** Redirect-/Alias-Routen (z. B. `/display/routine/` →
  `/display/routine/morgen` — nur der kanonische Einstieg zählt) sowie
  Nicht-GET-/Nicht-HTML-Endpunkte (z. B. POST auf demselben verbfreien
  View-Pfad gemäß URL-2, oder JSON-Statik-Sub-Pfade einer Komponente).
- **Controller-App ohne eigene Flask-Route** (der Router serviert dynamisch
  `/controller/<app>/`, es gibt keine komponenten-eigene Route): das Manifest
  wird gegen die **Existenz des Controller-Slugs** geprüft (Verzeichnis/
  Registrierung), nicht gegen eine Flask-Route.

So kann eine neue Seite nicht ohne Manifest-Eintrag entstehen (kein stilles
Fehlen, keine driftende Zweitliste). Freie/unendliche Query-Parameter (z. B.
`?ab=<datum>`) erzeugen **keinen** Eintrag. Das Manifest ist die **ausfallfeste
Wahrheitsquelle** der Seiten-Registry (SREG,
[`../specs/platform/seiten-registry.md`](../specs/platform/seiten-registry.md)):
es liegt auf der Platte, eine Seite bleibt also gelistet, auch wenn ihr Prozess
gerade aus ist. (Landet mit dem 2. Manifest-Vorkommen, nicht auf Vorrat —
konsistent mit der Reifelogik unten.)

### BUD-4 — Kachel-Icon(s) je Display-View im Manifest (sobald der Buddy als Panel-Kachel adressierbar ist)
**Geltungsbereich: Display-Views (SREG-4-Sorte a, `/display/<app>/<view>`)** — die
einzige Sorte, die ein Panel-Tile targeten kann (PANEL-7 Descriptor `{app, view}`).
Eltern-Settings-Views (Sorte b, z. B. `/display/wetter/regeln`) und Controller-Apps
(Sorte c) werden **nie** Panel-Kacheln und tragen **kein** `icons[]` (kein Vorrat,
CLAUDE.md §6).

Jeder **Display-View**-Eintrag im `views.json`-Manifest (BUD-3) trägt `icons[]` —
die **vollständige, final anzuzeigende** Liste der Kachel-Icon-Pfade dieser View
(≥1, max 3), **relativ zur Icon-Basis `/display/_shared/icons/`** (PANEL-3/ICONS-5;
ARASAAC ist die heutige Default-Quelle, z. B. `arasaac/<id>.png`, aber das Feld
ist die Pfad-Form, nicht die Quelle).

**Jede `varianten[]`-Zeile (BUD-3) trägt ihr eigenes, vollständiges `icons[]`** —
explizit, **keine Erbung vom View-Icon, keine Ableitung**. Eine Kleinkind-Variante
führt z. B. `["…/plan.png", "arasaac/2484.png"]` (Kinder-Marker als zweites Icon),
die Default-Variante nur `["…/plan.png"]`. `varianten[].query` ist ein **flaches
Objekt** (`{"ansicht":"klein"}`), kein String — passt direkt ins
Kachel-/Descriptor-Schema (PANEL-7).

**Warum die volle Liste je Eintrag:** das Manifest ist die **eine Wahrheit** der
Kachel-Darstellung. Sowohl der Panel-Add (`specs/platform/panel-bearbeiten.md`
PBE-7) als auch der Panel-Anlege-Skill (`panel_anlegen`) lesen sie, statt jeder die
`icons[]` selbst zu komponieren. Eine Marker-Ableitung aus `zielgruppe` wäre
**falsch**: eine `kind`-View **ohne** Variante trägt **keinen** Kinder-Marker — nur
die Kleinkind-**Variante** tut das.

**Icon-Existenz ist ein Deploy-/Backfill-Gate, kein Aggregator-Test:** ein Pfad in
`icons[]` muss als PNG im `_shared/icons`-Cache liegen (ICONS-4 seedet nur aus dem
Cache, lädt nichts nach). Verifiziert wird das beim Backfill per lokalem
`GET /display/_shared/icons/<pfad>` → `200 image/png` (Verantwortung: der
Backfill-PR, #387), **nicht** in der Aggregator-Durchreichung (SREG-10). Ein
Kachel-Icon ist **nie** ein app-eigenes Asset (URL-13) und **nie** das
View-Hero-Bild.

**Durchsetzungs-Stufe** definiert SREG-10 (Schalter `icons_erforderlich`), nicht
dieser Text — so bleibt die gestaffelte Einführung (Toleranz → Backfill → Härtung)
ohne Selbstwiderspruch. Rollout-Detail im Ticket #387.

## Andock-Checkliste „neuer Buddy"

Ein Buddy muss an mehreren Stellen des Systems auftauchen. Diese Checkliste
sagt **wo** — und **verweist** für die jeweilige Regel und den Eintrag auf die
zuständige SSoT-Datei. Sie kopiert keine Tabelle: jeder Eintrag lebt genau an
seinem Ort, sonst entsteht ein weiterer Drift-Ort (die systemd-README driftet
bereits gegenüber der Conf — eine zweite Kopie hier würde es verschlimmern).

Reihenfolge der drei Routing-/Prozess-Andockpunkte ist **SSoT zuerst, dann
nginx, dann Code** (URL-14: „erst hier eine Zeile, dann nginx, dann Code").

1. **Port** — feste Nummer im Katalog [`ports.md`](ports.md) PORT-2 (Block
   5050-5099 ist für neue Buddys reserviert). *(BUD-1a, nur wenn eigener
   Prozess.)*
2. **Origin-Routing** — Zeile in [`urls.md`](urls.md) URL-14 für
   `/display/<slug>/` (und ggf. `/api/v1/<slug>/`), spezifisch vor allgemein
   (**längster Prefix gewinnt** — Teil der Spec, nicht nur nginx-Marotte).
   *(BUD-1a — für den Display-Prefix, sobald der Buddy ein eigener Prozess
   hinter der Origin ist (in der Regel jeder); der API-Prefix nur bei BUD-1b.)*
3. **nginx-Origin-Conf** — `location /display/<slug>/`-Block in
   [`../deploy/nginx/xbuddy-origin.conf`](../deploy/nginx/xbuddy-origin.conf),
   eingeordnet vor den allgemeinen `/display/`- bzw. `/api/v1/`-Blöcken
   (Umsetzung von URL-14). *(BUD-1a.)*
4. **systemd** — Service-Vorlage `<slug>/<slug>.service` und Aufnahme in die
   Ausroll-/Restart-Tabellen von
   [`../deploy/systemd/README.md`](../deploy/systemd/README.md) (SVC-1/SVC-2).
   *(BUD-1a.)*
5. **pytest-testpaths** — `<slug>/tests` in
   [`../pytest.ini`](../pytest.ini) eintragen, sonst läuft die Buddy-Suite im
   repo-weiten Lauf nicht mit. *(Immer — ein Buddy ohne mitlaufende Tests ist
   unbelegtes Verhalten, CLAUDE.md §6.)*
6. **import-linter** — den Buddy als `root_package` in
   [`../.importlinter`](../.importlinter) aufnehmen, damit er denselben
   Layer-Contracts unterliegt wie `plan/`
   ([`module-boundaries.md`](module-boundaries.md) MOD-1..5). *(Nur wenn
   eigenes Python-Paket — typischerweise jeder Prozess-Buddy.)*

## Skelett-Datei-Topologie

Buddys **teilen die Topologie, nicht den Inhalt**: jeder Buddy spiegelt
dieselben Datei-Namen und -Rollen, gefüllt mit seiner eigenen Domäne. Das ist
keine Code-Duplikation (jede Datei hat eine eigene Verantwortung, CLAUDE.md
§6), sondern ein wiedererkennbares Skelett.

| Datei | Rolle |
|---|---|
| `<slug>/main.py` | HTTP-Schnittstelle + Entrypoint (Flask, `-m <slug>.main`) |
| `<slug>/config.py` | Config-Auflösung (CONFIG-1/CONFIG-5) |
| `<slug>/render.py` | View-Rendering (Domänen-Daten → Template-Kontext) |
| `<slug>/templates/<view>.html` | Display-View (BUD-1) |
| `<slug>/static/` | buddy-eigene Assets (URL-13) |
| `<slug>/config.example.json` | dokumentiertes **Runtime-Config**-Format (BUD-2, committet ohne echte Werte; CONFIG-3) |
| `<slug>/<domäne>.example.json` | dokumentiertes **Domänendaten**-Format pro Domäne (BUD-2a, eine oder mehrere; nur wenn der Eltern-Chat Domänendaten schreibt) |
| `<slug>/.gitignore` | Per-Instanz-Daten-Ausschluss neben dem Code (BUD-2b) |
| `<slug>/<slug>.service` | systemd-Vorlage (SVC-2; Andockpunkt 4) |
| `<slug>/tests/` | Buddy-Tests (Andockpunkt 5) |
| `<slug>/__init__.py` | macht den Buddy zum importierbaren Paket (Andockpunkt 6) |

Domänen-eigene Module (z. B. `wetter/meteo.py`, `wetter/clothing.py`,
`plan/kalender.py`, `plan/db.py`) kommen je nach Funktion dazu — sie sind kein
Pflicht-Skelett, sondern folgen aus dem, was der Buddy tut (Leitsatz).

**pytest-Satz:** Jeder Buddy trägt `<slug>/tests` in
[`../pytest.ini`](../pytest.ini) `testpaths` ein (Andockpunkt 5); die Tests
importieren über den Paketpfad (`from <slug> import main`), damit gleichnamige
`main`-Module im repo-weiten Lauf eindeutig bleiben (siehe `pytest.ini`-Kopf,
#52).

## Prozess: Spec erst nach dem Display-Design ratifizieren

Die **Spec** eines Buddys (`specs/buddies/<slug>.md`, Verortung APP-6) wird
erst ratifiziert, **nachdem das Display-Design steht** — die Display-View ist
das Herz eines Buddys, und ihr Verhalten folgt aus dem Design, nicht umgekehrt.
BUD regelt das Bauen; was der Buddy der Familie zeigt, bleibt Sache der
Buddy-Spec und ihres Design-Fundaments.
