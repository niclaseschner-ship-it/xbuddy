# Code-Style — Konvention     (ID-Präfix: STYLE)

XBuddy-Python wird einheitlich gehalten, damit der teure Architektur-Watchdog
sich auf Logik und Drift konzentriert und mechanische Funde (unused import,
Import-Reihenfolge) gar nicht erst entstehen. Der durchsetzbare Standard lebt
in `pyproject.toml [tool.ruff]` — diese Konvention *zeigt* darauf und legt das
Gate fest, sie dupliziert den Regelsatz nicht.

### STYLE-1 — Der Regelsatz lebt in `pyproject.toml`, nicht hier
Die Wahrheit über erlaubte/verbotene Lint-Verstöße ist `pyproject.toml
[tool.ruff.lint]`. Wer eine Regel ändern will (select/ignore), ändert die toml,
nicht diese Datei — sonst driften zwei Quellen. Diese Konvention nennt nur das
*Wie der Durchsetzung*, der Regelsatz selbst steht genau einmal (CLAUDE.md §6,
„Kopiere niemals Inhalt zwischen Dokumenten").

### STYLE-2 — Code-Tracks self-gaten gegen Ruff und Modul-Grenzen vor dem Handoff
Jeder Python-schreibende Subagent läuft vor seinem Handoff einen **zweistufigen
Block** über den eigenen Branch-Diff. Beide Stufen müssen Exit 0 liefern — die
Konjunktion stellt sicher, dass ein Verstoß einer der beiden Stufen den
Handoff blockt:

    uvx ruff@0.15.15 check $(git diff --name-only --diff-filter=d origin/main...HEAD -- '*.py') \
      && uvx --from import-linter==2.11.* lint-imports --no-cache

Stufe 1 (Ruff) prüft Code-Stil und Lint-Regeln (Wahrheit: `pyproject.toml
[tool.ruff.lint]`). Stufe 2 (`lint-imports`) prüft die Modul-Grenzen MOD-1..5
für die in `.importlinter` `root_packages` erfassten Komponenten (Wahrheit:
`.importlinter` + `conventions/module-boundaries.md`). **Deckungs-Caveat:**
fehlt eine Komponente in `root_packages`, prüft Stufe 2 sie nicht — heutige
bekannte Lücke: `panel/` (Folge-Ticket #412). Stufe 2 ist ratifiziert
via PW-15 (Prozess-Repo, xbuddy-prozess#15; Auslöser
PR #402: MOD-5-Verstoß mit grünem Auto-Merge, weil das Repo-Gate `lint-imports`
nicht required ist — RAT-9 hält CI-Gates draußen).

Exit ≠ 0 blockt den Handoff. Über `uvx` (vorhanden unter `~/.local/bin`) —
keine Installation in Worktree, venv oder Pi. Versionen sind gepinnt. `--no-cache`
in Stufe 2 vermeidet den Default-`.import_linter_cache`-Schreibvorgang im
Worktree (read-only-tauglich). Der Diff-Filter in Stufe 1 scopt automatisch nur
die im Track geänderten `.py` (datei-, nicht zeilen-gescopt — Ruff kann nicht
zeilen-scopen). **Niemals `--diff`** auf Ruff: das ist ein Fix-Preview und
liefert exit 0 auch bei rein nicht-fixbaren Verstößen (empirisch verifiziert,
Ruff 0.15.15). Spec-/Doku-/JSON-Tracks haben kein Gate (`lint_command` leer).

Durchgesetzt wird STYLE-2 vom `/arbeitstag`-Orchestrator-Prozess
(Contract-First-Flow, `~/.claude/contracts/` + `~/.claude/commands/arbeitstag.md`)
— also prozessual außerhalb des Repos, nicht durch Repo-CI. Diese Konvention
ist die Repo-seitige Festlegung der Regel; der Prozess vollzieht sie. Der
Andockpunkt liegt damit bewusst außerhalb des Repos (der arbeitstag-Skill ist
kein Repo-Artefakt) — STYLE-1/2/3 sind deshalb nicht „tot". `lint_clean: true`
bleibt eine Subagent-Selbstauskunft (preflight.md §B.2 prüft nur das Boolean,
kein Tool-Lauf); fängt Vergessen/Umgehen nicht. Falls empirisch nötig, wird
eine Evidence-/Probe-Mechanik in einer eigenen Runde nachgezogen (PW-15
Restfrage C, heute bewusst nicht).

### STYLE-3 — `per-file-ignore` wird beim Anfassen abgebaut, nicht ergänzt
Die Altlast-Einträge in `[tool.ruff.lint.per-file-ignores]` sind geduldete
Schuld mit `# TODO <code>`-Marker. Wer eine gelistete Datei aus anderem Grund
anfasst, baut ihren Ignore-Eintrag ab (behebt den Verstoß), statt einen neuen
hinzuzufügen. Eine wachsende Ignore-Liste ist ein Signal, dass das Gate nicht
trägt — Messpunkt nach 4 Wochen: Liste kürzer.
