# RAT-9 — Standard-Git-Modell (Pi-SSoT abgelöst)

**Entschieden:** 2026-06-06 (Nic)
**Status:** RATIFIZIERT
**Betrifft:** `~/.claude/commands/arbeitstag.md` (Merge-Gate), `~/.claude/contracts/preflight.md` (§A.2), `CLAUDE.md` §8, `WORKFLOW.md` (war schon Standard); Memories `feedback_pi_ssot`, `feedback_worktree_base_drift`
**Deliberation:** `brainstorm/berater-runde/20260606-RATIFIZIERT-standard-git-migration.md` (+ Vorschlag, Codex-Antiberater 2 Runden)

## Beschluss (1 Satz)
Wir arbeiten Standard-Git: `origin` ist die Wahrheit (Session-Start `pull --ff-only`),
Arbeit auf Feature-Branches die nach `origin` gepusht werden, nach `main` nur über
gemergten PR (`Closes #<nr>`, triggert Ticket-Automatik) nach Watchdog-Freigabe; `main`
ist durch Watchdog + Test geschützt, nicht durch Push-Vermeidung — kein Pi-Bare-Repo,
kein per-Branch-Sicht-Stempel, kein CI-Zwang/Pflicht-Reviewer.

## Kontext / Problem
Pi-SSoT („push erst auf Freigabe am Session-Ende") hielt `origin/main` tagsüber bewusst
veraltet. `isolation: worktree` zweigt von `origin/main` ab → Base-Drift abhängiger
Folge-Tracks, plus ein Stapel Eigenbau-Abfederung (Worktree-Rückhol per Branch-Name,
lokaler Merge, „Rebase aller Live-Tracks weil origin stale"). Das Pi-SSoT-Motiv war
ausschließlich Nics persönlicher Sicht-und-Test-Gate vor Push.

## Entscheidung im Detail
- **`origin` = SSoT, GitHub, ab Tag 1.** Kein Pi-Bare-Repo-Zwischenschritt (schützt vor
  nichts, sperrt externe Devs aus, erzwänge bei Dev-2 zweite Migration). Ein Modell für
  Solo und Team.
- **Gate gewandert:** Nics vertikale-Scheibe-Test läuft auf dem deployten, integrierten
  `main` am Tagesende (war ohnehin schon der arbeitstag-Deploy-Block), nicht mehr „vor Push".
- **PRs bleiben** — sie tragen die Ticket-Automatik (`.github/workflows/ticket-status-flow.yml`
  reagiert nur auf PR-Events + `Closes`). CI-Gates / Pflicht-Reviewer bleiben draußen
  (Solo-Overhead). Watchdog IST die Review.
  > **Amendment RAT-30 (2026-07-27):** Die „Solo-Overhead"-Prämisse ist bei n=10
  > parallelen Sessions tot (die hier :41-42 versprochene Folge-Runde). Billige
  > deterministische Checks (ruff + lint-imports) werden **bindend** (required),
  > pytest bleibt still bis gemessen; push:[main]-Dreifachläufe werden zu EINEM
  > beobachteten `main-health.yml` dedupliziert. Kein Bruch — `origin`=SSoT,
  > PR-Pflicht, `closes-guard` unverändert. Siehe RAT-30.
- **Merge-Gate-Mechanik:** Branch → `push origin` → Leer-Diff-Riegel → Watchdog →
  Rebase-Rendezvous auf `origin/main` (`--force-with-lease` nur auf eigenen Branch) →
  `gh pr merge --merge --delete-branch` → lokal `pull --ff-only`.

## Ehrliche Grenzen (Codex-Antiberater)
- **Kein Tempo-Gewinn im einzelnen arbeitstag:** der visuelle Faithful-Test serialisiert
  weiter (ein nginx `:8443`, ein Buddy-Prozess). Gewinn = weniger Eigenbau-Komplexität.
- **Tempo-Hebel auf nächster Ebene (Nic):** zwei parallele arbeitstage / „wie zwei
  Entwickler" werden erst durch dieses Modell möglich (Standard-Branches + PR-Merge sind
  für N gleichzeitige Merger gebaut; Issues+Labels = geteilte Tafel für freie Lücken).
  Engpass wandert dann zu Nic + dem einen Pi (Review/Test). Eigene Folge-Runde, wenn
  zwei Linien gefahren werden (Ticket-Greif-Konvention: `status:in-progress`+Assignee).
- **Nur Base-Drift behoben** — CWD-Reflex, Shared-Root-Landung, Worktree-Cleanup bleiben
  relevant (andere Ursachen).

## Umsetzung
Tooling direkt umgeschrieben am 2026-06-06 (keine Testphase — Standard-Git ist Commodity).
Sicherung: `/home/buddy/backups/claude-tooling-pre-gitpilot-20260606.tar.gz`.
