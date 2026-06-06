# RAT-10 — Tool-erzwungene Ticket-Reconcile-Verriegelung (gibt RAT-9 Zähne)

**Entschieden:** 2026-06-06 (Nic)
**Status:** RATIFIZIERT — Variante 1 (GitHub Pro). Umsetzung gated auf Pro-Aktivierung.
**Betrifft:** GitHub-Ruleset auf `main`; `.github/workflows/closes-guard.yml` (neu),
`ticket-status-flow.yml` (fail-loud); `decisions/RAT-9`; `conventions/` (RECON-1); arbeitstag.md/Werft.
**Deliberation:** `brainstorm/berater-runde/20260606-ENTSCHEID-reconcile-verriegelung.md`
(+ Vorschlag, Codex-Antiberater)

## Beschluss (1 Satz)
`main` wird per GitHub-Branch-Protection verriegelt (PR-Pflicht, 0 Pflicht-Reviewer → Bot
self-merge, required `closes-guard`-Check); damit ist Direkt-Push physisch unmöglich,
Auto-Close garantiert und der Status-/Label-Lebenszyklus ausschließlich Action-getrieben —
kein Agent fasst je wieder Labels per Shell an.

## Kontext / Problem
Reconcile-Lücke (Code auf `main`, Ticket bleibt offen + Label hängt) + #315-Klasse (stiller
`gh`-Shell-Fehler beim Label-Umlegen). Bekannte Lücke (feedback-ticket-reconcile-gap), war
seit Tagen besprochen, wurde nicht hart durchgegriffen. RAT-9 *beschrieb* „nach main nur über
PR", erzwang es aber nicht („nicht durch Push-Vermeidung, kein CI-Zwang" = die offene Tür).

## Der harte Fakt
Branch Protection/Rulesets sind auf privaten **Free**-Repos gesperrt (HTTP 403, live geprüft).
Owner-Typ User → Freischaltung via **GitHub Pro (~4$/Monat)**. Nic hat sich für Pro
entschieden (Variante 1) gegen Variante 2 (free Halb-Lösung) und Variante 3 (public, Exposition).

## Entscheidung im Detail (Codex-gehärtet)
- **Ruleset auf `main`:** „Require a pull request before merging", required approvals = **0**
  (Bot merget eigene PRs, kein Mensch-Engpass). **Linear history NICHT** aktivieren — sie
  kollidiert mit RAT-9 `gh pr merge --merge`; `--merge` bleibt.
- **`closes-guard` als required status check** mit DREI Ausgängen (sonst blockt er valide PRs):
  1. Impl-PR: `Closes/Fixes/Resolves #<offenes-issue>` → grün.
  2. Spec-PR: `Refs #<nr>` (pull_request_template) → grün (kein Closing erwartet).
  3. Infra/Chore-PR ticketlos: Label `infra`/`chore` am PR → grün.
  Sonst rot → nicht mergebar.
- **`ticket-status-flow.yml` fail-loud:** das `2>/dev/null || true` (:104) muss weg — ABER
  korrekt: erst vorhandene `status:*`-Label abfragen, nur die entfernen, dann echtes Scheitern
  laut + zurücklesen (sonst rot bei nicht-vorhandenem Label). Killt #315-Klasse.
- **Option C (PAT ohne Contents:write) ist tot** (Merge-Endpoint braucht Contents:write).
- **Option B (Commit-Message-Auto-Close) verworfen** (`fix(#nr)` ≠ Abschluss; #344 hatte
  Teilcommits + Deploy-Fix → würde zu früh schließen).

## Umsetzungs-Reihenfolge
1. **Nic:** GitHub Pro aktivieren (Settings → Billing → Plans). Blocker für das Ruleset.
2. Bauen (frei): closes-guard.yml, ticket-status-flow fail-loud, RAT-10/RECON-1.
3. Pro live → Ruleset via `gh api` setzen, closes-guard als required.
4. **Alles über den ersten Dogfood-PR landen** (erste echte Probe des RAT-9-Modells).

## Was an arbeitstag/Werft bricht (gewollt)
- Lokaler ff-Merge fällt ganz weg — `main` nicht mehr lokal beschreibbar, alles via `gh pr merge`.
- Werft-`git push` auf `main` bricht hart → Werft pusht Feature-Branch + PR.

## Wo es landet
Dieser Record (RAT-10) + RECON-1 in `conventions/` (Bauregel: „Status-/Reconcile-Übergänge
fasst nur eine Action an, nie ein Agent per Shell; nach `main` nur über PR"). Mechanik in
`.github/workflows/` + Ruleset-Config.
