# Conventions

`conventions/` ist die **Quelle der Wahrheit** für das *Wie* — die
gemeinsamen Bauregeln von XBuddy. **Lebende Konventionen**: Sie
beschreiben, wie wir wiederkehrende Sachen *heute* einheitlich bauen,
nicht wie sie historisch gewachsen sind (das steht in PRs).

## Die eine Regel

> **Konvention ist Vorschrift.** Wer abweichen will, ändert erst die
> Konvention.

Wer beim Implementieren merkt, dass eine Konvention nicht mehr passt,
korrigiert nicht still nebenher, sondern erst die Konvention. Genauso
wie bei Specs: SSoT zuerst, Code danach (CLAUDE.md §6, „Specs sind SSoT
für Verhalten").

## Aufbau

- Eine Konventions-Datei je **wiederkehrender Sache mit eigenem
  Wie-Vertrag** — `conventions/<name>.md` (z. B. `identifiers.md`,
  `config.md`, `logging.md`, `module-boundaries.md`).

## Provenienz-Zeilen und `brainstorm/`-Pfade

Ältere Konventionen tragen `Quelle:`-Zeilen mit Pfaden nach
`brainstorm/berater-runde/…` — das private Deliberations-Archiv dieses
Projekts (nicht Teil dieses Repos; siehe `../decisions/README.md`). Die
Pfade lösen sich für Außenstehende bewusst nicht auf; die Entscheidung
selbst steht durable in `../decisions/`. **Neue Einträge referenzieren nur
den public Anker** (`Governance: decisions/RAT-<n>`).

Eine Konvention darf **maschinell durchgesetzt** werden, wo das geht:
`module-boundaries.md` (MOD) wird von import-linter (`.importlinter`,
`make lint`, CI) als Gate geprüft; die Datei beschreibt die Bauregel,
der Linter erzwingt sie.

Gegliedert wird nach **Sache**, nicht nach Code-Modul. Eine Datei
entsteht **erst**, wenn dieselbe Sache zum zweiten Mal gebaut wird und
Drift droht — Trigger ist konkreter Schmerz, nicht Antizipation
(CLAUDE.md §6, „Vorschlagen, wenn Werte sich vermehren"). Nichts auf
Vorrat.

Das „zweite Mal" setzt voraus, dass es **dieselbe** Sache ist. Sind die
Kandidaten heterogen (gleicher Topf, aber unterschiedliche Bau-Verträge),
ist „dieselbe Sache" noch nicht belegt — dann braucht es weitere, wirklich
gleichartige Instanzen, bevor eine Konvention entsteht (vgl. RAT-7).

Was *nicht* hierhin gehört:

- **Verhalten** (was die Familie erlebt) → `specs/`
- **Prinzipien** (übergreifende Werte) → `specs/constitution.md`

## Eine Konvention schreiben

Jede Regel hat eine **stabile ID** (Präfix + laufende Nummer) und einen
knappen, präskriptiven Satz — analog zur Spec-Form, aber im Sollens-Stil
statt Wenn/Dann. Eine kurze Begründung als zweiter Absatz ist erlaubt,
wenn die Regel sonst willkürlich wirkt.

```markdown
# Identifier — Konvention     (ID-Präfix: IDENT)

### IDENT-1 — Objekt-ID
Geräte, Personen und ähnliche Objekte tragen den stabilen Namen
`<typ>-<slug>-<nn>`, z. B. `tablet-elias-01`.

### IDENT-2 — Quell-ID im Routing
Im Routing wird ein Objekt unter `<typ>:<instanz>` adressiert,
z. B. `display:wohnzimmer`.
```

IDs werden nie neu vergeben und nie umnummeriert. Spec-Anforderungen
und Code zitieren die IDs (z. B. „Geräte-ID folgt IDENT-1") — das ist
der Link zwischen Konvention, Spec und Code.
