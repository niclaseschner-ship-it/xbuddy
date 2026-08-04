# RAT-30 — CI-Fluss unter RAT-9 gehärtet: advisory-Rauschen weg, billige Checks bindend (Amendment zu RAT-9/RAT-10)

**Entschieden:** 2026-07-27 (Nic „ja passt" — Paket mit den drei vorgeschlagenen Werten)
**Status:** RATIFIZIERT (Teile 2/3/5 in diesem PR umgesetzt; Teil 1 Aktivierung pending Messung; Teil 4 NOCH NICHT)
**Betrifft:** `.github/workflows/ruff.yml`/`pytest.yml`/`lint-imports.yml` (push:main weg, pytest-Cache), `.github/workflows/main-health.yml` (neu), GitHub-Ruleset `main-verriegelung` (Teil-1-Flip pending), `methode/commands/arbeitstag.md` (Merge-Gate-Zeile), `methode/contracts/preflight.md`/`schemas.md` (Anker); `decisions/RAT-9`/`RAT-10` (Marginalie); xbuddy-prozess#88 (PW-88); Ticket #1478
**Deliberation:** `brainstorm/berater-runde/20260727-111903-RATIFIZIERT-pw88-ci-gate-fluss.md` (+ Vorschlag `20260727-111903-vorschlag-pw88-ci-gate-fluss.md`, Codex-Antiberater `2026-07-27-1120-antiberater-pw88-ci-gate-fluss.md`)

## Beschluss (1 Satz)
Kein Check bleibt „sichtbar-aber-folgenlos" — er ist entweder **bindend** (required, gatet den Merge) oder **still** (läuft, macht `main` nicht rot, mailt nicht einzeln): billige deterministische Checks (ruff + lint-imports) werden bindend, der teure (pytest) bleibt still und wird gemessen bevor er gatet, und die push:[main]-Dreifachläufe werden zu EINEM beobachteten `main-health.yml` dedupliziert.

## Kontext / Problem — die von RAT-9 versprochene Folge-Runde
RAT-9 (2026-06-06) hielt CI-Gates bewusst draußen („Solo-Overhead, Watchdog IST die Review") und terminierte selbst eine Folge-Runde: *„Eigene Folge-Runde, wenn zwei Linien gefahren werden. Engpass wandert dann zu Nic + dem einen Pi"* (RAT-9:41-42). Diese Bedingung ist eingetreten und überholt: **10 parallele Sessions**, ein self-hosted Pi-Runner, advisory ruff/pytest/lint-imports, die **doppelt feuern** (PR + push:main) → „main rot" blockt Sessions + erzeugt eine Mail-Flut. Die Solo-Overhead-Prämisse ist bei n=10 tot. Dies ist ein **Amendment** zu RAT-9/RAT-10, kein Bruch: `origin`=SSoT, PR-Pflicht, `closes-guard`-required und der Label-Lebenszyklus bleiben unverändert.

## Das Paket (Codex-gehärtet) — die fünf Teile

### Teil 1 — `ruff` + `lint-imports` werden required (Aktivierung **pending Messung**)
Beide laufen in Sekunden und sind deterministisch (ruff gepinnt `0.15.15`, kein CI-Autofix; lint-imports-Allowlist leer). Ihr Durchrutschen war PW-15s Original-Schmerz (#402). Sie werden **required Status-Checks** im Ruleset `main-verriegelung` (id 17352637) — **aber erst nach einer belegten Grünserie**.

- **Ratifizierter Wert (Grünserie):** die **letzten 10 PR-Läufe von ruff + lint-imports grün** vor dem Required-Flip.
- **Aktivierung:** NICHT in diesem PR. Die 10-grün-Messung beginnt erst zu laufen, nachdem die push:[main]-Trigger raus sind (dieser PR). Kein `gh api`-PATCH aufs Ruleset hier.
- **Flip-Kommando (Referenz, wenn die Serie steht):** die beiden Check-Namen zu `required_status_checks` des Rulesets hinzufügen, z. B.
  ```
  gh api -X PUT repos/<your-org>/xbuddy/rulesets/17352637 \
    --input <ruleset.json>   # required_status_checks.required_status_checks[] += {context: "ruff"}, {context: "lint-imports"}
  ```
  (Ruleset zuerst per `gh api repos/<your-org>/xbuddy/rulesets/17352637` ziehen, `required_status_checks`-Regel um die zwei Kontexte ergänzen, zurück-PUTten — closes-guard bleibt erhalten.)
- **Brick-Notausgang (ratifiziert):** dokumentiertes Ruleset-Rollback — den jeweiligen required-Check wieder **entfernen** (gleiches PUT ohne den Kontext), sobald ein STYLE-2-konformer PR nur wegen Altlast/Queue-Stau blockiert. Zwei-Wege-Tür.

### Teil 2 — push:[main]-Dreifachlauf → EIN beobachteter `main-health.yml` (**umgesetzt**)
`push: branches:[main]` ist aus `ruff.yml`, `pytest.yml`, `lint-imports.yml` entfernt (`pull_request` bleibt). Ersatz = **`main-health.yml`** (neu, `on: push: branches:[main]`, `runs-on:[self-hosted, ARM64]`, EIN Job): ruff → lint-imports → pytest, **jeder Prüf-Schritt mit `if: always()`** (Codex-Härtung: kein serieller Abbruch, der pytest überspringt) → genau EINE Workflow-Meldung bei Rot. Erhält das post-merge-main-Health-Signal (Cross-PR-Konflikte), halbiert Mail + Doppel-Last.

- **Watcher (ratifizierter Wert):** der **arbeitstag-Reflex „main-health-Status prüfen"** (Merge-Gate/Session-Start, `methode/commands/arbeitstag.md`) — nicht nur passive Mail. „Still" ohne Beobachtungs-Vertrag ist kein Betriebsmodus.
- **Kill-Klausel:** wird ein rotes main-health nicht binnen eines Arbeitstags triagiert → zurück zu getrennten push-Jobs oder expliziter Notification. Zwei-Wege-Tür.

### Teil 3 — pytest nur cachen, KEIN Modul-Filter (**umgesetzt**)
`actions/cache@v4` für den pip-Download (`~/.cache/pip`, Key aus Hash von `eltern-chat/requirements.txt` + `photo/requirements.txt`) in `pytest.yml` UND im pytest-Schritt von `main-health.yml`. **KEIN** `-k`/Modul-/`testpaths`-Filter (Codex-BRICHT: `pytest.ini` protokolliert die Cross-Suite-Import-Kollision — Einzelsuiten grün, Gesamtlauf rot; `testpaths` ist bewusst vollständig). pytest bleibt **repo-weit** `-q`. Ein `paths:`-Trigger-Filter wurde **weggelassen** (im Zweifel weglassen; ein falscher Filter würde reine Doku/Spec-PRs still nicht testen oder Code-PRs versehentlich ausnehmen). Zwei-Wege-Tür.

### Teil 4 — pytest required + zweiter Runner (**NOCH NICHT**)
- **Auslöser pytest-required (ratifizierter Wert):** required-Flip erst wenn **pytest (mit Cache) stabil <60s über 10 Läufe** ist. Bis dahin bleibt pytest advisory (nur `closes-guard` ist required — siehe `reference_main_ruleset_nur_closes_guard`).
- **Auslöser 2. Runner:** wenn nach Teil 1-3 der eine Runner nachweislich Merge-Stau-Engpass bleibt (Claim-Flip-Poll regelmäßig über Schwelle). Dann ein **zweiter self-hosted** (nicht hosted, wegen Actions-Quote `project_actions_quote_monitoring`) vs. hosted-für-Leicht-Checks als eigene kleine Gabel.
- **Memory-Kontext (Nic):** kein neuer Rechner; der xbuddy→public-Übergang (~Aug '26) löst Actions-Quote + Runner-Frage gemeinsam — 2. Runner deshalb nicht jetzt beschaffen, sondern gegen diesen Übergang planen.
- **Sofort:** Mess-Ledger (Laufzeit/Queue-Zeit/Claim-Flip-Poll je PR) als Datenbasis für beide Auslöser.

### Teil 5 — „vor Merge lokal die volle Suite" vertraglich verankern (**umgesetzt**)
Solange pytest advisory ist (nur `closes-guard` required), ist der bislang nur in Memory lebende Reflex (`reference_pi_runner_pytest_bottleneck`) eine **harte Merge-Gate-Zeile**: vor jedem Merge muss lokal die volle Suite grün sein (`python3 -m pytest -q` + `uvx ruff@0.15.15 check` + `lint-imports`). Landepunkt = **`methode/` SSoT** (`methode/commands/arbeitstag.md` Merge-Gate + Anker in `methode/contracts/preflight.md`/`schemas.md`), **NICHT** direkt `~/.claude` (Codex: RAT-23 SSoT-Drift). Ein-Wege-Tür (SSoT) → nach Merge muss `deploy-methode.sh --verify-only` grün sein.

## Reversibilität (gesamt)
Mechanik durchweg Zwei-Wege-Tür (reversible Config/Ruleset, <1 Tag rückbaubar). Der einzige Prinzip-berührende Akt ist der Teil-1-Required-Flip (RAT-9-Amendment) → Nic-Gate erfüllt (dieser Record).

## Was Codex dem Berater voraushatte
1. Die 35%-/Doppel-Trigger-Zahlen sind live via `gh` verifiziert, aber KEINE Repo-Artefakte — als solche gekennzeichnet.
2. main-health braucht einen Besitzer; „still" ohne Watch-Vertrag ist kein Betriebsmodus → Watcher-Reflex in Teil 2 festgeschrieben.
3. pytest-Modul-Filter BRICHT an der `pytest.ini`-Cross-Suite-Kollision → auf Cache-only reduziert (Teil 3).
4. Teil-5-Landepunkt `~/.claude` würde RAT-23-SSoT-Drift erzeugen → nach `methode/` korrigiert.

## Belege
xbuddy-prozess#88 (PW-88). RAT-9 (Git-Modell, selbst terminierte Folge-Runde :41-42), RAT-10 (Ruleset `main-verriegelung`, closes-guard required), RAT-23 (methode/ SSoT). Memories `reference_main_ruleset_nur_closes_guard`, `reference_pi_runner_pytest_bottleneck`, `project_actions_quote_monitoring`, `project_kommandobruecke_scale` (n=10).

Refs #1478
