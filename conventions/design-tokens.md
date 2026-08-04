# Design-Tokens — Konvention     (ID-Präfix: DTOK)

XBuddy-Buddys teilen einen gemeinsamen visuellen Grundton: Montessori-Pädagogik
(konkret, ruhig, natürlich), Minimalismus (Reduktion, Raum zum Atmen) und das
Mitwachsen-Prinzip (dieselben Token-Namen, stufen-abhängige Werte). Diese
Konvention legt fest, wie Buddys an diesen Grundton andocken und ihn nicht
verdoppeln — damit Design-Anpassungen an einem Ort gemacht werden und überall
ankommen.

### DTOK-1 — Ein geteilter Token-Strang ist die EINE Quelle visueller Werte

Es gibt genau eine Datei, die die system-weiten Design-Token definiert:
`display/_shared/design/tokens.css` — ein Superset, das als **XBUDDY DESIGN
TOKENS v2.0** kommentiert ist und das Mitwachsen-Stufen-System
(`data-stage="toddler|reader|parent"`) trägt. Sie liegt im geteilten
Display-Asset-Verzeichnis `display/_shared/` (DTOK-2) und wird von dort
referenziert.

Die ältere `plan/static/design/tokens.css` (v1.0, BuddyBoard-Artefakt) ist mit
der Design-Tokens-Migration (Schritt 2, #323) abgelöst und entfernt; der
v2.0-Inhalt lebt nun unter `display/_shared/design/tokens.css`. Es gibt damit
genau eine Token-Datei im Repo.

*Tickets:* #323

### DTOK-2 — Andockpunkt: geteilter Display-Asset-Namensraum `/display/_shared/`

Assets, die keinem einzelnen Buddy gehören, liegen unter `/display/_shared/`
(URL-16, [`../conventions/urls.md`](urls.md)). Der Token-Strang ist das zweite
geteilte Display-Asset — nach den ARASAAC-Piktogrammen (`/display/_shared/icons/`,
URL-16, ROU-26).

Routing: der Router serviert den Token-Strang **read-only aus dem In-Repo-
Verzeichnis** `display/_shared/design/` (ROU-30) — ein Zwilling zu
`/controller/_shared/` (ROU-23, Repo-Inhalt), **nicht** zu `/display/_shared/icons/`
(ROU-26/Icons, die als Per-Instanz-Daten außerhalb des Repos liegen). Design-Tokens
sind die Marke: bei allen Familien identisch, mit dem Code versioniert, kein
manueller Pro-Pi-Schritt, keine Divergenz (Nic-Entscheid 2026-06-05). Kein eigener
nginx-Block, keine Reihenfolge-Sonderregel: `/display/_shared/design/` fällt wie
`/display/_shared/icons/` an den allgemeinen `/display/`→Router-Eintrag. Andock-Regel:
der Strang ist unter `/display/_shared/` erreichbar und wird von dort referenziert.

*Tickets:* #323, #135 (Icon-Bibliothek als Referenz-Umsetzung von URL-16)

### DTOK-3 — Neue Buddys REFERENZIEREN den geteilten Strang, sie KOPIEREN ihn nicht

Ein Buddy darf keine eigene Kopie des token-CSS anlegen. Dasselbe Visual-System
zweimal im Repo zu führen ist ein direktes Lego-/§6-Anti-Pattern: ≥ 2 Exemplare
derselben Sorte ohne gemeinsamen Andockpunkt machen Wert-Drift unvermeidlich —
eine Farbänderung muss dann in jeder Kopie nachgezogen werden, und Folge-Agents
kopieren das Muster weiter.

Erlaubt: buddy-eigene ergänzende CSS-Dateien mit Buddy-spezifischen Werten, die
*über* die Token-Layer gelegt werden (z. B. Layout, komponentenspezifische
Größen). Nicht erlaubt: eigene Deklarationen für Token-Werte, die der geteilte
Strang bereits definiert.

*CLAUDE.md-Verweis:* §6, „Ein Modul = eine Verantwortung" und „Dieselbe Logik
zweimal zu schreiben ist verboten — gemeinsamer Code lebt an EINEM Ort."

### DTOK-4 — Stufen-System: Token-Namen stabil, Werte stufen-abhängig

Der v2.0-Strang trägt das Mitwachsen-System über das `data-stage`-Attribut:
dieselben Token-Namen (`--stage-bg`, `--stage-font`, `--stage-fs-body` …) erhalten
je Stufe andere Werte. Eine Komponente liest ausschließlich die `--stage-*`-Tokens
für stufen-abhängige Werte — sie ändert sich nicht, ihr Kontext tut es.

Stufen: `toddler` (3 J, handgezeichnet, XL), `reader` (6–10 J, ruhig, generös),
`parent` (Erwachsener, dicht, nüchtern). Defaults entsprechen der Reader-Stufe.
Die aktive Stufe wird per `data-stage="..."` an einem Root-Element gesetzt —
typischerweise der Query-Parameter `?stage=` steuert das serverseitig.

### DTOK-5 — Hardcode-Verbot

Farb-, Maß- und Schrift-Werte werden niemals als Literale im Buddy-CSS
hartcodiert. Jeder Wert referenziert einen Token: `color: var(--text)`, nicht
`color: #2B2A28`. Neue Tokens, die der geteilte Strang noch nicht führt, kommen
zuerst dort hinein — kein Buddy-CSS definiert neue visuelle Grundwerte still
nebenher.

*CLAUDE.md-Verweis:* §6, „Was sich ändern kann, gehört in eine Datei."
