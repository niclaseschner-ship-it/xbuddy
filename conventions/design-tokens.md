# Design-Tokens — Konvention     (ID-Präfix: DTOK)

XBuddy-Buddys teilen einen gemeinsamen visuellen Grundton: Montessori-Pädagogik
(konkret, ruhig, natürlich), Minimalismus (Reduktion, Raum zum Atmen) und das
Mitwachsen-Prinzip (dieselben Token-Namen, stufen-abhängige Werte). Diese
Konvention legt fest, wie Buddys an diesen Grundton andocken und ihn nicht
verdoppeln — damit Design-Anpassungen an einem Ort gemacht werden und überall
ankommen.

### DTOK-1 — Ein geteilter Token-Strang ist die EINE Quelle visueller Werte

Es gibt genau eine Datei, die die system-weiten Design-Token definiert. Aktuell
ist das `wetter/static/design/colors_and_type.css` — ein Superset, das als
**XBUDDY DESIGN TOKENS v2.0** kommentiert ist und das Mitwachsen-Stufen-System
(`data-stage="toddler|reader|parent"`) trägt.

Die ältere `plan/static/design/tokens.css` (v1.0, BuddyBoard-Artefakt) wird
durch den v2.0-Strang abgelöst. Sie bleibt solange im Repo, bis Plan-Buddy auf
den geteilten Pfad umgestellt ist (Schritt 2, #323 — Design-Tokens-Migration).

*Tickets:* #323

### DTOK-2 — Andockpunkt: geteilter Display-Asset-Namensraum `/display/_shared/`

Assets, die keinem einzelnen Buddy gehören, liegen unter `/display/_shared/`
(URL-16, [`../conventions/urls.md`](urls.md)). Der Token-Strang ist das zweite
geteilte Display-Asset — nach den ARASAAC-Piktogrammen (`/display/_shared/icons/`,
URL-16, ROU-26).

Routing: analog Icons serviert der Router den Token-Strang aus einem
konfigurierbaren Per-Instanz-Verzeichnis — kein eigener nginx-Block, keine
Reihenfolge-Sonderregel. Das ist die Schritt-2-Arbeit (#323); hier gilt nur die
Andock-Regel: sobald der Strang unter `/display/_shared/` erreichbar ist, wird er
von dort referenziert.

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
