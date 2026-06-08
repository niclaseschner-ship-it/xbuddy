# RAT-15 — Claim-PR-at-pick (Aktivierung von PW-11 A.1 für PW-17)

**Entschieden:** 2026-06-08 (Nic)
**Status:** RATIFIZIERT (Werkstatt-Ratifizierung — Berater-Runde + Codex-R2)
**Betrifft:** `~/.claude/commands/arbeitstag.md` (CONTRACT-FIRST FLOW),
`~/.claude/contracts/schemas.md` (parent_ticket-Schema),
`~/.claude/hooks/dispatch_status_guard.py` (neu),
`~/.claude/settings.json` (PreToolUse-Matcher),
`.github/workflows/ticket-status-flow.yml` (Doppelbau-Cleanup-Schutz + fail-loud-Drift).
**Anlässe:**
- xbuddy-prozess#17 (PW-17: Memo→Action-Gap — Orchestrator vergisst
  `status:in-progress` vor Dispatch, n=2 nach PW-11)
- PW-11 (Vormerk A.1, Z. 19-20 + Z. 32 — Record-Slot reserviert)
**Deliberation:** `brainstorm/berater-runde/20260608-RATIFIZIERT-pw17-memo-action.md`
(+ Vorschläge R1/R2 + Codex-Reports R1/R2)

## Beschluss (1 Satz)

Das Setzen von `status:in-progress` beim Aufgreifen eines `status:ready`-Tickets
erfolgt durch einen **leeren Draft-PR mit `Closes #<nr>`** (positive Mechanik,
Action-getrieben via `ticket-status-flow.yml`) **plus einen
PreToolUse-Hook-Guard** (negative Versicherung gegen Dispatch ohne Claim) —
nie per Shell-`gh issue edit` durch den Orchestrator (RECON-3-Verstoß,
PW-11 R1 ratifiziert verboten).

## Kontext / Problem

- **PW-17-Pain:** Orchestrator vergisst Label-Setzung. Quellgeprüft n=2:
  `~/.claude/retros/2026-06-07-arbeitstag-session2.md:60-84` +
  `2026-06-08-arbeitstag.md:8-12`. Root-Cause-Selbstdiagnose im 06-08-Retro:
  „Die `/arbeitstag.md`-Sektion `CONTRACT-FIRST FLOW` listet als
  Pflicht-Schritte: Contract-Posten, Preflight, Sub-Agent-Contract. **Das
  Label-Setzen taucht dort nicht als eigener Schritt auf.**"
- **RECON-3 verbietet Shell-Setzen** (`conventions/reconcile.md:36-54`,
  PW-13-Klarstellung Z. 49-54, RAT-10:61-67) — auch für den Orchestrator,
  Klausel ist akteurs-unabhängig.
- **PW-11 hat A.1 (Draft-PR-at-pick) als „SOURCE-FEST und ratifiziert-konform"
  klassifiziert** (Z. 19-20). Reopen-Trigger von PW-11 ist „Normalfall UND
  echter Doppelbau" — der zweite Konjunkt gilt für PW-11s eigenen
  Exklusivitäts-Pain, nicht für PW-17s Vergessens-Pain. PW-17 aktiviert die
  vormerk-substantiierte Mechanik auf einen zweiten belegten Pain — kein
  Re-Litigation, sondern Anwendung.

## Die harten Fakten (Codex-gehärtet, R1+R2)

**Was geht:**
- `ticket-status-flow.yml:46-127` setzt bei `opened` (mit
  `closingIssuesReferences`) `status:in-progress`, bei `closed UNmerged`
  `status:ready`. Verify-by-read fail-loud (Z. 120-127). RECON-3-konform.
- `PreToolUse`-Hook kann `Agent` matchen (Anthropic-Hook-Doku 2026-06-08,
  Codex-verifiziert). Read-only Reject-Pfad nach Vorbild `cynthra_fence.py`.
- `schemas.md:281-285` führt `parent_ticket` als maschinenlesbares Feld im
  Subagent-Contract.

**Was Codex-R2 zerlegt hat (eingebaut in diesem RAT):**
- (1) Branch-Bindung kaputt mit `isolation:worktree` → **Manueller Worktree
  ist Pflicht** (Orchestrator legt Branch + Worktree explizit an, Claim-PR
  und Subagent arbeiten auf demselben Branch). Das ist sowieso die Lehre des
  06-08-Retro:17 (CWD-Bug).
- (2) Doppelbau-Cleanup-Race in `ticket-status-flow.yml`: bei closed-UNmerged
  setzt der Workflow blind `status:ready`, auch wenn ein anderer offener
  Closing-PR existiert. **Patch:** vor `add-label status:ready` prüfen, ob
  andere offene Closing-PRs existieren; wenn ja, skip (Schritt bleibt beim
  anderen Owner). PR-Anteil dieses RAT.
- (3) `parent_ticket` ohne Repo-Identität — Hook hat keinen verlässlichen
  `gh issue view`-Pfad. **Schema-Erweiterung:**
  `parent_ticket: <owner>/<repo>#<nr>` als kanonische Form.
- (4) Hook-Bypass bei fehlendem `parent_ticket`. **Hook strenger:** kein
  `parent_ticket` im Subagent-Prompt = deny mit Reason
  „Contract fehlt oder Repo-Marker fehlt".
- (5) `ticket-status-flow.yml:110` hatte noch `|| true` (Reste-Drift). **PR
  räumt das auf** — fail-loud per `set -e` zieht jetzt sauber.

## Entscheidung im Detail

### A. Workflow-Patch (`.github/workflows/ticket-status-flow.yml`, in diesem PR)
- **Doppelbau-Cleanup-Schutz:** bei `TARGET=ready` GraphQL-Query auf
  `closedByPullRequestsReferences`, andere offene Closing-PRs zählen. ≥1 →
  skip ready-Übergang (anderer PR hat Ownership).
- **fail-loud-Drift:** `|| true` beim CURRENT-Read in Z. 110 entfernt.

### B. Schema-Erweiterung (`~/.claude/contracts/schemas.md`)
- `parent_ticket: <owner>/<repo>#<nr>` (vorher `T<nr>` ohne Repo).
- Kommentar im §1-Block: „Repo-Identität nötig für PreToolUse-Hook (RAT-15)".

### C. arbeitstag.md CONTRACT-FIRST FLOW (`~/.claude/commands/arbeitstag.md`)
- Neue Sektion „Claim-PR-at-pick (RAT-15)" zwischen Contract-Post und
  Subagent-Dispatch.
- Drei Schritte:
  1. Manueller Worktree + Branch (`git -C <repo> worktree add …`).
  2. Leerer Draft-PR: `git commit --allow-empty -m "WIP: T<nr>"; git push;
     gh pr create --draft --title "WIP: T<nr>" --body "Closes #<nr>"`.
  3. Verify-by-read: `gh issue view <nr> --json labels` muss
     `status:in-progress` zeigen, sonst Halt.
- Cleanup-Pfad: bei Track-Abbruch `gh pr close <pr-nr>` → Workflow setzt
  zurück auf `ready` (mit Doppelbau-Schutz von A).
- Hinweis auf den PreToolUse-Hook als Read-only-Sicherungsnetz.

### D. PreToolUse-Hook (`~/.claude/hooks/dispatch_status_guard.py`)
- Schema-Vorbild `cynthra_fence.py`.
- Liest `tool_input.prompt`, extrahiert
  `parent_ticket: <owner>/<repo>#<nr>`.
- Kein `parent_ticket` → **deny** (nicht still durchlassen — Codex-Bruch (4)).
- Mit `parent_ticket`: `gh issue view <repo> <nr> --json labels`. Enthält
  `status:in-progress` → durchlassen. Sonst → deny mit Reason
  „Claim-PR fehlt — Achse-E-Schritt vor Dispatch ausführen".
- `~/.claude/settings.json` PreToolUse-Matcher um `Agent` erweitern.

### E. Forward-Vermerk in PW-11-ENTSCHEID-File
- Zeile am Ende: „PW-17 (xbuddy-prozess#17, 2026-06-08) aktiviert A.1
  ratifiziert via RAT-15 für den Vergessens-Pain. Kein formales Reopen."

## Was an arbeitstag/Werft bricht (gewollt)

- `isolation: worktree`-Bequemlichkeit fällt für Code-Tracks weg —
  Orchestrator legt Worktree manuell an. Genau das, was die 06-08-Retro:17
  als CWD-Bug-Lösung benannt hatte.
- Ein leerer Draft-PR + Action-Lauf pro Subagent-Dispatch (Solo-Overhead,
  PW-11 hat das schon ratifiziert akzeptiert).
- Subagent-Prompts ohne `parent_ticket: <owner>/<repo>#<nr>` werden vom
  Hook hart geblockt — alte Contract-Formen müssen geupdatet werden.

## Wo es landet

- Dieser RAT (`decisions/RAT-15-claim-pr-at-pick.md`).
- Workflow-Patch (`.github/workflows/ticket-status-flow.yml`) — in
  diesem PR mit.
- Außerhalb des Repos (Harness): `arbeitstag.md`, `schemas.md`, `settings.json`,
  `dispatch_status_guard.py` — separater Commit in `~/.claude`-Repo.

## Reopen-Trigger

- Hook-Probe zeigt, dass `PreToolUse: "Agent"` nicht matcht in installierter
  Claude-Code-Version → D ist tot, Eskalation.
- Doppelbau tritt trotz Workflow-Patch auf → PW-11 echter Reopen.
- Mechanik versagt unter Last (mehrere parallele Sessions) →
  Race-Conditions im Workflow-Patch nachschärfen.
