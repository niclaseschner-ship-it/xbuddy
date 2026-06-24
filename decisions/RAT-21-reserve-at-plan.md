# RAT-21 — Reserve-at-plan (schärft RAT-15 für Parallel-Last nach)

**Entschieden:** 2026-06-24 (Nic)
**Status:** RATIFIZIERT (berater-runde leicht gefahren — R1-Bestandskarte + Codex-Antiberater, Zwei-Wege-Tür)
**Betrifft:** `~/.claude/commands/arbeitstag.md` (Reserve-at-plan-Block + Board reserviert≠live),
`~/.claude/commands/arbeitstag-prep.md` (Build-Claim-Respekt vor Release).
**Anlass:** xbuddy-prozess#70 (PW-70 — Cross-Session-Ticket-Reservierung). Aktiviert
RAT-15 Reopen-Trigger #3 („Mechanik versagt unter Last (mehrere parallele Sessions) →
Race-Conditions nachschärfen", `RAT-15:136-137`).
**Deliberation:** `brainstorm/berater-runde/20260624-1430-RATIFIZIERT-pw70-claim-early-reservierung.md`
(+ Vorschlag + Codex-Report).

## Beschluss (1 Satz)

Ein Arbeitstag reserviert **die ganze vertikale Scheibe exklusiv bei Plan-Ende**
(reserve-at-plan, nur Draft-PR → `status:in-progress`, Worktree+Dispatch bleiben
at-pick); eine verwaiste Reservierung wird über einen **ticket-sichtbaren
Lebenszeichen-Marker** räumbar — Räumen niemals zeit-allein, sondern
Kandidat→Räumabsicht→Bestätigung.

## Kontext / Problem

- **#1075-Vorfall (2026-06-22):** Parallele Session schloss ein aktiv beprepptes
  Ticket als „completed"; closes-guard blockte den Impl-Merge, ~1h Reopen-Reibung.
- **CHK-1/RAT-14 deckt nur Root-HEAD-Git-Ops**, nicht Issue-State — Reservierung muss
  übers Ticket laufen, nicht über den Root-Lock.
- **RAT-15 war claim-at-pick (late):** Claim sitzt pro Dispatch (`arbeitstag.md:204-211`);
  zwischen Plan und Pick ist ein Ticket ungeschützt. Bei real ~10 Parallel-Sessions
  (kommandobruecke) ist der Doppelgriff strukturell wahrscheinlich.
- **Nic-Setzung:** Exklusive Plan-Reservierung ist der einzig valide Weg; Stale-Lock
  wird über Räumbarkeit (Zwischenstand im Ticket) gelöst, nicht über enges Lock-Fenster.

## Entscheidung im Detail

### A. Reserve-at-plan (`arbeitstag.md`, Phase-0→Contract-First-Übergang)
- Pro Scheibe-Ticket die **volle RAT-15-Dreierkette** (Worktree mit `-b` + leerer
  Claim-Commit + Draft-PR `Closes #<nr>` + verify → `status:in-progress`), nur bei
  Plan-Ende statt pro Dispatch. Die Worktrees bleiben stehen bis zum Bau (billig).
- **Build-at-pick dispatcht in den bestehenden Worktree** — kein zweiter Claim-PR, kein
  zweiter Branch. (Antiberater-Pass-2-Korrektur: „nur Schritt 2 reservieren" war gebrochen,
  weil RAT-15-Schritt 2 den Branch aus Schritt 1 voraussetzt — `arbeitstag.md:215-225`.
  Deshalb volle Kette bei Reservierung, Worktree persistiert.)

### B. Lebenszeichen-Marker (ersetzt PR-Topologie als live-Signal — Codex-BRICHT DF4)
- Issue-Comment, erste Zeile greppbar:
  `reservierung-lebenszeichen: <ISO-ts> · phase: reserviert|live|handoff|review · session: <id> · branch: feature/<branch>`
- Trägt Zustand (reserviert/live) UND Lebenszeichen. `status:in-progress` ist nicht mehr
  allein das live-Signal. Kadenz an Phasengrenzen (PEP-Checkpoints), kein Zeit-Tick.

### C. Räumen — Kandidat statt Zeit-Tod (Codex-BRICHT DF2)
- Marker-Alter macht ein Ticket nur zum **Räum-Kandidaten** — ein konformer Multi-Day-Track
  (`arbeitstag.md:106-112`) darf lange ohne Marker laufen. Vor `gh pr close`:
  (1) Räumabsicht-Comment, (2) zweiter Beleg (kein neuer Marker in Karenzzeit). Dann
  Draft-PR close → `ready` (Doppelbau-Schutz). Inspektionsgetrieben, kein cron.

### D. Build-Claim-Respekt im prep (`arbeitstag-prep.md`, vor Release-Flip)
- Guard-Zeile: trägt das Ticket vor dem Release-to-ready `status:in-progress` → Halt +
  Comment, kein Flip. Schließt den #1075-Pfad.

## Kill-Kriterien (laufen mit)
- **DF1-Last (RISKANT):** N Reservierungs-Draft-PRs = N `ticket-status-flow`-Läufe auf dem
  Pi-Runner. Erster Lauf misst N · Action-Laufzeit · Runner-Queue · Rate-Limit. Rollback
  auf claim-at-pick, wenn Queue sichtbar staut ODER >5 min bis alle `in-progress` verified.
- **DF2-Fehlräumung:** Erstes fälschlich geräumtes aktives Ticket → Räum-Regel verschärfen.
- **DF4-Lesbarkeit:** Live vs. reserviert aus Ticket+Marker nicht eindeutig → Marker-Schema
  nachschärfen.

## Was an RAT-15 nachgeschärft wird (gewollt)
- Claim-Timing: at-pick → at-plan (Reservierung); Build-Maschinerie bleibt at-pick.
- `status:in-progress` bekommt zwei Bedeutungen (reserviert/live); der Marker trägt die
  Wahrheit, das Board zeigt `phase`.
- WIP-Limit zählt nur live-Tracks, nicht die reservierte Scheibe.

## Reopen-Trigger
- DF1-Messung sprengt die Schwelle → Rollback auf claim-at-pick.
- Marker-Disziplin reißt (Tracks posten keine Lebenszeichen) → mechanischer Tick statt
  Disziplin nötig (cron/Heartbeat), neue Runde.
