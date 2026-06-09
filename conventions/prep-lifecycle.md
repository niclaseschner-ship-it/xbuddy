# Prep-Lifecycle — Konvention     (ID-Präfix: PREP)

Wie ein Ticket im prep-Lebenszyklus (von `status:spec` über das Reife-Urteil bis
`status:ready`) **mechanisch** reift — nicht „der Skill denkt dran". Diese
Konvention petrankert die PW-26-Ratifizierung (xbuddy-prozess#26, 2026-06-09) im
Code-Repo. Maschinell durchgesetzt durch `~/.claude/hooks/status_rollback_guard.py`;
Bauregeln hier, Implementations-Anker am Ende.

Diese Konvention setzt RECON-1/RECON-2/RECON-3 (`reconcile.md`) voraus — `main`-
Verriegelung, Spec-PR-Ausgang über `closes-guard`, Action-getriebener `status:*`-
Lebenszyklus. PREP regelt, **wie ein Ticket reif wird, bevor `status:ready`
gesetzt werden darf**; RECON regelt, **wie der Stempel mechanisch in den Lifecycle
greift**.

## PREP-1 — Spec-vor-Karte als Sequenz-Vorbedingung

Eine Stempel-Karte (Reife-Vorlage an Nic) existiert **nur**, wenn die zitierte
Requirement-ID bindend auf `origin/main` liegt. Es gibt keinen Pfad, in dem
ein Spec-PR-Merge an den Stempel gekoppelt ist („Falls Spec-PR: zuerst mergen,
dann Label" ist abgeschafft).

Drei Karten-Klassen existieren:

1. **Stempel-Karte** — Spec liegt auf `origin/main`. Nic stempelt oder lehnt.
2. **Mini-Wahl-Karte** — Architektur-Wahl steht offen (`architecture_class:
   wahl`). Nic wählt eine Variante VOR dem Spec-Merge; Skill mergt dann den
   Spec-PR mit der gewählten Variante; in der nächsten Charge erscheint die
   Stempel-Karte. Wahl-Karten produzieren **kein** `prep_verdict`-Comment
   (mechanische Unterscheidbarkeit gegen versehentlichen Stempel).
3. **Cross-Spec-Koord-Karte** — der Spec-Pfad wird parallel von einem
   `status:in-progress`-Ticket konsumiert. Nic entscheidet die Reihenfolge.

Grund: drei dokumentierte Belegfälle am 2026-06-09 (Vormittag, Nachmittag,
Abend — drei verschiedene `/arbeitstag-prep`-Läufe, drei Nic-Korrekturen
„spec ist deine Aufgabe"), trotz expliziter „Pflicht-Klausel" im Skill-Text
seit dem Vormittag. PW-22-Wurzelbefund („Text-Pflicht trägt nicht") 1:1
angewandt: die Mechanik ist Sequenz-Vorbedingung, nicht weitere Disziplin.

## PREP-2 — `architecture_class` als Pflicht-Achse des prep_verdict

Der `xbuddy-watchdog-prep`-Agent setzt `architecture_class` für jedes Ticket
auf einen der zwei Werte:

- **`nachzeichnen`** — der Spec-Inhalt ist aus Constitution + RAT-Bestand
  ableitbar (Wortlaut-Schärfung, Mechanik-Klausel für WAS/WIE-Spalt, Refactor-
  Spec für gebauten Pfad, Drift-Fix gegen vorhandene Spec). Skill darf den
  Spec-PR autonom schreiben und mergen.
- **`wahl`** — Issue-Body trägt A/B-Optionen; OPEN-*-Spec ohne entscheidbaren
  Pfad; RAT-Konflikt-Verdacht; `eine_frage_an_nic` mit Architektur-Charakter;
  neuer Buddy/Schnittstelle; Privacy- oder Familien-Setup-Frage. Skill darf den
  Spec-PR **nicht** autonom mergen.

**Default bei Unsicherheit: `wahl`.** Codex-Bruch 2 (PW-26): autonomes
Mergen einer gewählten Variante wäre Vorgriff vor Nic-Ratifizierung
(`decisions/README.md` — Berater-Runde → Nic ratifiziert → DANN RAT + Spec-PR).
RAT-11-Disziplin („im Zweifel nie Richtung `spec-gemergt` raten") 1:1 hier
übertragen.

## PREP-3 — Strukturierte `reif_*`-Felder im prep_verdict

Achse REIF wird durch fünf flache Felder im YAML-Block des prep_verdict-Comments
getragen, **nicht** durch einen Freitext-`reif_evidence`-String:

```yaml
axes:
  reif: spec-gemergt | spec-fehlt | keine-spec-noetig
  reif_spec_path: "specs/<...>.md | conventions/<...>.md | null"
  reif_requirement_id: "<ID, z. B. ROU-15 oder SVC-5> | null"
  reif_definition_line: <int> | null
  reif_section_heading: "<wörtlich der Heading-String> | null"
  reif_binding: true | false | null
```

`specs/` und `conventions/` sind als `reif_spec_path` **gleichberechtigt** —
Requirements leben in beiden Genres (z. B. `SVC-5` in `conventions/services.md`,
`ROU-15` in `specs/buddies/routine.md`).

Grund: Codex-Bruch 1 (PW-26) — der naive `grep "<ID>"` ist RAT-11-widrig, weil
er den Abschnittskontext (`## Offene Punkte` / `ENTWURF` / `OPEN-*`-Präfix)
nicht prüft. Strukturierte Felder erlauben dem Hook die semantische Probe.

## PREP-4 — Zwei Sub-Klassen bei `keine-spec-noetig`

- **Drift-gegen-Spec**: Watchdog-Befund „Code weicht von bindender Spec ab"
  (z. B. `routine.py:142` bricht `ROU-15`). `reif_*`-Felder zeigen auf die
  gedriftete Spec-Stelle wie bei `spec-gemergt`; zusätzlich Pflicht-Feld
  `drift_target` mit Datei:Zeile der Code-Drift. Stempel-Karte zeigt eine
  DRIFT-Zeile zusätzlich zum SPEC-DIFF.

- **Reines Chore** (Dead-Code, Format, Type-Hint): keine Spec-ID zitierbar.
  `reif_*`-Felder bleiben `null`; stattdessen Pflicht-Feld `chore_evidence`
  mit Datei:Zeile + Convention/CLAUDE.md-Verweis (z. B. `routine.py:88
  ungenutzter _legacy_handler — CLAUDE.md §6 'Kein toter Code'`). Hook prüft,
  dass die Datei auf `origin/main` existiert.

Beides ist Stempel-fähig ohne Spec-PR. Sind beide Felder gefüllt, ist das
ein Verdikt-Bug — Hook deniert.

## PREP-5 — `verdict_repo_sha` immutable, `stamp_repo_sha` separat

`verdict_repo_sha` wird vom `xbuddy-watchdog-prep`-Agent im Prep-Moment gesetzt
(`git rev-parse origin/main`) und ist **immutable**. Der Skill darf den Wert
beim Stempeln **nicht** ersetzen. Für den Stempel-Moment existiert ein zweites
Feld `stamp_repo_sha` (vom Skill gesetzt) — semantisch getrennt.

Hash-Marker (`<!-- prep_verdict v1 issue:NR sha:HASH -->`) umfasst bei
PW-26-Schema (`architecture_class:` im Verdikt-Body) zusätzlich
`verdict_repo_sha` und `architecture_class`:

- **PW-26-Schema**: `sha256(json({verdict, axes, verdict_repo_sha,
  architecture_class}, sort_keys=True))[:16]`.
- **Legacy PW-30-Schema** (vor PW-26): `sha256(json({verdict, axes},
  sort_keys=True))[:16]`. Bestand-kompatibel.

Grund: Codex-Bruch 4 (PW-26) — vor PW-26 deckte der Hash nur `{verdict, axes}`,
sodass ein altes Verdikt mit frischem `verdict_repo_sha` „gewaschen" werden
konnte. Mit dem erweiterten Hash invalidiert jeder SHA-Tausch den Marker
mechanisch.

## PREP-6 — Hook-Sperren beim Stempel und beim Spec-PR-Merge

`~/.claude/hooks/status_rollback_guard.py` implementiert vier Sperren:

1. **Beim `gh issue edit … --add-label status:ready`** (Stempel oder
   prep-Release-forward):
   - prep_verdict-Comment am Ticket Pflicht (PW-30, `VERDICT_MARKER_RE`).
   - Hash-Probe: Marker-SHA muss zum Body passen (PREP-5).
   - Drift-Probe: `specs/`/`decisions/` zwischen `verdict_repo_sha` und
     aktuellem `origin/main` müssen unverändert sein.
   - Spec-Binding-Probe (`check_spec_binding`): semantisch über die fünf
     `reif_*`-Felder + Heading-Negativfilter (`## Offene Punkte` / `ENTWURF` /
     `OPEN-*`) + `git show <verdict_repo_sha>:<reif_spec_path>`-Existenzprobe
     der Requirement-ID. Bei `keine-spec-noetig` mit `chore_evidence`:
     Datei-Existenz auf `verdict_repo_sha`.

2. **Beim `gh pr merge` auf einem `spec/<nr>-…`-Branch**:
   - `architecture_class: wahl` ohne `arch_choice`-Marker am Issue
     (`<!-- arch_choice v1 issue:<nr> choice:A -->`) → deny. Codex-Bruch 2.
   - Cross-Spec-Probe (`check_spec_path_exclusive`): einer der PR-Pfade wird
     als `reif_spec_path` in einem anderen offenen `status:in-progress`-Ticket
     zitiert → deny mit Hinweis auf das konfligierende Ticket. Codex-Bruch 3.

3. **Bei `gh issue edit … --add-label status:spec-in-progress`** (prep-Claim,
   PW-33): Skip-Marker-Pflicht. Nur dieser Übergang ist via Skip erlaubt.

4. **Bei `gh issue edit … --remove-label status:spec-in-progress
   --add-label status:spec`** (prep-Release-back): Skip-Marker-Pflicht.

Andere `status:*`-Mutationen per Shell sind durch RECON-3 ohnehin verboten —
der Hook deniert sie unabhängig vom Skip-Marker, weil die parsierten
Label-Mutationen nicht den vier dokumentierten Pfaden entsprechen.

## PREP-7 — Rollback-Pfad bei autonom gemergter Fehl-Spec

Sagt Nic beim Stempel `zurück: Spec falsch` (Fehler in einer vom Skill autonom
gemergten Spec, `nachzeichnen`-Klasse), läuft der Rollback in zwei Pfaden:

- **Trivial** (keine Folge-Merges auf der betroffenen Spec-Datei zwischen
  `spec_merge_sha` und `origin/main`): `git revert -m 1 <spec_merge_sha>` als
  neuer Spec-PR (`Refs #<nr>`, Label `type:docs` falls `conventions/`),
  closes-guard greift über den Spec-Ausgang. Label zurück auf `status:spec`
  per dokumentiertem Skip-Pfad.

- **Nicht trivial** (Folge-Merges berühren die Spec-Datei): Skill produziert
  `rollback-koord`-Karte; Nic wählt zwischen Folge-Reverts und Vorwärts-Fix.
  Skill landet keinen der zwei autonom — diese Klasse ist Architektur-Wahl,
  die nicht aus RAT ableitbar ist.

Beim Rollback wird zusätzlich ein Comment am Issue gepostet (durabler Mess-
Anker für die Reopen-Probe):

```
<!-- prep_rollback v1 issue:<nr> spec_pr:<x> rollback_pr:<y> reason:"<text>" -->
```

## PREP-8 — `conventions/`-Touch ist konservativ in `wahl`

Spec-PRs, die `conventions/`-Dateien ändern, fallen per Default in
`architecture_class: wahl` — auch wenn der Inhalt klein wirkt. Grund: eine
Konvention bindet quer mehrere Komponenten; ein autonomer Merge ohne Nic-
Wahl kann Cross-Spec-Drift in `status:in-progress`-Tickets erzeugen, bevor
der Watchdog dort eingreifen würde.

Ausnahme: Verdikt trägt `convention_low_blast_radius: true` (z. B. reine
Wortlaut-Schärfung an einer Klausel, die in keinem offenen Ticket zitiert
wird). Empirisch zu prüfen, nicht Heuristik.

## PREP-9 — Reopen-Bedingungen für diese Konvention

Die PW-26-Mechanik wird **nicht** stillschweigend erweitert. Reopen-Trigger
(als neue `/berater-runde`-Anlass):

1. **Klassifikator-False-`nachzeichnen`**: autonom gemergter Spec war
   Architektur-Wahl ohne Nic-Wort → Trigger-Liste enger ziehen.
2. **Rollback-Quote >20%** in 14 Tagen ab Ratifizierung (Mess-Skript
   xbuddy-prozess#34) → Vor-Validierungs-Stufe vor autonomem Merge erwägen.
3. **`conventions/`-Touch-Vorfall** ohne explizite
   `convention_low_blast_radius`-Markierung → PREP-8 verschärfen.

## Warum tool-erzwungen statt Prosa

Vor PW-26 lebte die Spec-PR-Pflicht im Koord-Block als „Pflicht, nicht
Optional"-Klausel im Skill-Text (`arbeitstag-prep.md` Z. 55 ab 2026-06-09).
Trotzdem fiel sie am selben Tag dreimal durch — n=3 dokumentierte Belegfälle
zeigen, dass Text-Pflicht unter Last übersprungen wird, auch nach mehreren
Memory-Updates und Skill-Edits. Die `status_rollback_guard.py`-Hook-Sperre
ist der mechanische Ersatz: ohne grüne Probe kein Stempel, ohne grüne
Cross-Spec/Wahl-Probe kein Spec-Merge.

## Implementations-Anker

Die Konvention beschreibt die Bauregel; die Implementation lebt im
Skill-Harness (außerhalb dieses Repos):

- `~/.claude/commands/arbeitstag-prep.md` — Skill-Sequenz, Karten-Render
- `~/.claude/agents/xbuddy-watchdog-prep.md` — Verdikt-Schema (PREP-2/3/4/5)
- `~/.claude/hooks/status_rollback_guard.py` — vier Hook-Sperren (PREP-6)

Spur:

- PW-26 RATIFIZIERT: `brainstorm/berater-runde/20260609-195710-RATIFIZIERT-pw26-spec-vor-karte.md`
- xbuddy-prozess#26 — Original-Ticket
- xbuddy-prozess#33 — RECON-3-1 Skip-Pfad-Klarstellung (Folge-Ticket, vertagt)
- xbuddy-prozess#34 — Mess-Skript für Rollback-Quote (Folge-Ticket, vertagt)
