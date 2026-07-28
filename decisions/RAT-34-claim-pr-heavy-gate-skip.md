# RAT-34 — Leere Claim-Flip-PRs vom pytest/ruff-Heavy-Gate ausnehmen (Amendment RAT-30 Teil 3/4)

**Entschieden:** 2026-07-28 (Nic „Ja, bauen")
**Status:** RATIFIZIERT (umgesetzt: `if:`-Zeile auf pytest+ruff; Vor-Commit-Experiment als Merge-Gate)
**Betrifft:** `.github/workflows/pytest.yml`/`ruff.yml` (Job-Level-`if:`); `decisions/RAT-30` (Marginalie-Wunsch, siehe unten); xbuddy-prozess#89 (PW-88 Teil 4); Ticket #1544
**Deliberation:** `brainstorm/berater-runde/20260728-143000-RATIFIZIERT-claim-pr-heavy-gate-skip.md` (+ Vorschlag `20260728-143000-vorschlag-claim-pr-heavy-gate-skip.md`); Antiberater = Opus-Fallback (Codex am Usage-Limit; schwächer/Echo-Risiko, BRICHT/RISKANT-Punkte an Live-`gh api` geerdet)

## Beschluss (1 Satz)
`pytest.yml` + `ruff.yml` bekommen ein Job-Level-`if: ${{ github.event.pull_request.changed_files != 0 }}` — **fail-open**: sie überspringen NUR belegte Null-Diff-PRs (leere Claim-Flips), laufen bei fehlendem/null Feld weiter und nehmen so nie Code aus.

## Kontext / Problem
Single-Pi-Runner-Nadelöhr (`project_kommandobruecke_scale`: n=10 parallele Sessions, ein self-hosted Pi-Runner). Leere Claim-Flip-PRs (RAT-15/RAT-21: `status:in-progress` via leerem Draft-PR mit `Closes #<nr>`) triggern die volle repo-weite pytest+ruff-Suite für **null Code** — grob die Hälfte der Runner-Last der Nacht (Retro 2026-07-28, n≥8/Nacht). Dies ist ein **Amendment** zu RAT-30 Teil 3/4, kein Bruch: `origin`=SSoT, PR-Pflicht, `closes-guard`-required und der Label-Lebenszyklus bleiben unverändert.

## Die Entscheidung — fail-open, nicht Filter
Job-Level-`if: ${{ github.event.pull_request.changed_files != 0 }}` auf dem `pytest`- und dem `ruff`-Job.

- **Warum `!= 0`, NICHT `> 0`:** `changed_files` ist async/lazy — am `opened`-Event transient null/fehlend (GitHub-Async-Race). `!= 0` lässt null/fehlend **LAUFEN** und nimmt so nie Code aus. Ein `> 0` wäre der falsifizierte Bruch (der Antiberater-BRICHT), weil es beim Race einen echten Code-PR fälschlich überspringen würde.
- **Kein Konflikt mit RAT-30 Teil 3 (RAT-30:36 „Code nie versehentlich ausnehmen"):** dies ist **kein** `paths:`-/Modul-/`testpaths`-Filter, sondern ein Null-Diff-Kurzschluss, der per Konstruktion nur nichts-ändernde PRs ausnimmt — genau NICHT der Failure-Mode, den RAT-30:36 verbot (reine Doku/Spec-PRs still nicht testen oder Code-PRs versehentlich ausnehmen). Die Suite bleibt repo-weit; nichts wird gefiltert.
- **`closes-guard` (einziger required Check, billig) bleibt unangetastet** und gatet weiter; der `on: pull_request`-Trigger und `runs-on` bleiben unberührt.

## Reversibilität
Zwei-Wege-Tür für die YAML-Zeile (<5 Min rückbaubar). Norm-Berührung (Amendment RAT-30) = eigener Record → Nic-Gate erfüllt (dieser Record).

## Kill-Kriterium
Geht `main-health.yml` (post-merge, repo-weit, RAT-30 Teil 2) je rot auf etwas, das ein pre-merge-pytest gefangen hätte, und die Ursache ist ein fälschlich übersprungener Job → `if:` zurückbauen.

## Vor-Commit-Experiment (billiger Realitäts-Test gegen den GHA-Async-Blindfleck)
EIN echter Feature-PR mit fertigem Diff öffnen und prüfen, dass pytest+ruff **starten** (nicht skipped) — belegt, dass `!= 0` bei vorhandenem Code nicht fälschlich überspringt. (Der Antiberater konnte den Race read-only nicht live provozieren; das Experiment schließt die Lücke vor dem Landen.)

## Explizit NICHT erledigt
Dieser Skip behebt das **Symptom** (Leer-Claim-Kosten), NICHT die Wurzel (Runner-Engpass). PW-88 Teil-4 „**Sofort: Mess-Ledger** (Laufzeit/Queue-Zeit/Claim-Flip-Poll je PR)" bleibt **ungebaut und offen** — der 2.-Runner-/pytest-required-Trigger kann ohne das Ledger nicht objektiv feuern. Dieser Skip darf NICHT als „RAT-30 Teil 4 erledigt" verbucht werden. (Gekoppelt an Epic #73-Herzschlag, HALTEN-Re-Visit.)

## Marginalie an RAT-30 (offen)
Eine kurze Amendment-Zeile an `decisions/RAT-30-ci-fluss-advisory-haerten.md` Teil 3/4, die auf RAT-34 verweist, wäre wünschenswert — außerhalb der write-allowed-Liste dieses Bauschritts, deshalb hier als offener Punkt vermerkt (an Orchestrator gemeldet, nicht selbst geschrieben).

## Belege
xbuddy-prozess#89 (PW-88 Teil 4). RAT-30 (CI-Fluss-Härtung, Teil 3 „paths-Filter weggelassen / Code nie versehentlich ausnehmen" :36, Teil 4 Mess-Ledger :42), RAT-15 (Claim-PR-at-pick: leerer Draft-PR), RAT-21 (Claim-early-Reservierung). Memories `project_kommandobruecke_scale` (n=10), `reference_main_ruleset_nur_closes_guard`.

Refs #1544
