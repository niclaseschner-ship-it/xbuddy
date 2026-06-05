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

### STYLE-2 — Code-Tracks self-gaten gegen ruff vor dem Handoff
Jeder Python-schreibende Subagent läuft vor seinem Handoff das diff-gescopte
Gate über den eigenen Branch-Diff:

    uvx ruff@0.15.15 check $(git diff --name-only --diff-filter=d origin/main...HEAD -- '*.py')

Exit 1 blockt den Handoff. Über `uvx` (vorhanden unter `~/.local/bin`) — keine
Installation in Worktree, venv oder Pi. Version ist gepinnt. Der Filter scopt
automatisch nur die im Track geänderten `.py` (datei-, nicht zeilen-gescopt —
ruff kann nicht zeilen-scopen). **Niemals `--diff`**: das ist ein Fix-Preview
und liefert exit 0 auch bei rein nicht-fixbaren Verstößen (empirisch verifiziert,
ruff 0.15.15). Spec-/Doku-/JSON-Tracks haben kein Gate (`lint_command` leer).

Durchgesetzt wird STYLE-2 vom `/arbeitstag`-Orchestrator-Prozess (Contract-First-Flow,
`~/.claude/contracts/` + `~/.claude/commands/arbeitstag.md`) — also prozessual außerhalb
des Repos, nicht durch Repo-CI. Diese Konvention ist die Repo-seitige Festlegung der
Regel; der Prozess vollzieht sie. Der Andockpunkt liegt damit bewusst außerhalb des Repos
(der arbeitstag-Skill ist kein Repo-Artefakt) — STYLE-1/2/3 sind deshalb nicht „tot".

### STYLE-3 — `per-file-ignore` wird beim Anfassen abgebaut, nicht ergänzt
Die Altlast-Einträge in `[tool.ruff.lint.per-file-ignores]` sind geduldete
Schuld mit `# TODO <code>`-Marker. Wer eine gelistete Datei aus anderem Grund
anfasst, baut ihren Ignore-Eintrag ab (behebt den Verstoß), statt einen neuen
hinzuzufügen. Eine wachsende Ignore-Liste ist ein Signal, dass das Gate nicht
trägt — Messpunkt nach 4 Wochen: Liste kürzer.
