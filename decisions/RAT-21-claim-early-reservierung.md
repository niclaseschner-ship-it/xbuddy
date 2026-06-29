# RAT-21 — Claim-early-Reservierung + räumbarer Zwischenstand (Nachschärfung RAT-15)

- **Entschieden:** 2026-06-24 (Nic „mach es"), **ratifiziert** 2026-06-24
  (Berater-Runde PW-70, Berater + Codex-Antiberater, zwei BRICHT eingearbeitet).
- **Reversibilität:** Zwei-Wege-Tür (Prozess-Regel, rückbaubar auf claim-at-pick),
  mittlerer Blast Radius (~10 Parallel-Sessions).
- **Anlass:** xbuddy-prozess#70 — Cross-Session-Ticket-Reservierung; RAT-15 von
  claim-at-pick (late) auf reserve-at-plan (early) nachschärfen + Stale-Lock
  räumbar machen (Reopen-Trigger #3 von RAT-15 autorisiert).
- **Betrifft:** `~/.claude/commands/arbeitstag.md` (Plan-Claim-Schritt am
  Phase-0-Ende, Reattach-Regel, Marker-Kadenz, reserviert/live-Semantik,
  Räum-Prozedur), `~/.claude/commands/arbeitstag-prep.md`
  (in-progress-Respekt-Guard vor Release), `decisions/INDEX.md`.
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/20260624-1430-RATIFIZIERT-pw70-claim-early-reservierung.md`
  → Vorschlag `20260624-142903-vorschlag-pw70-claim-early-reservierung.md`,
  Antiberater (Codex) `2026-06-24-1430-antiberater-pw70-claim-early.md`.

## Beschluss

RAT-15 wird nachgeschärft: die **ganze vertikale Scheibe** wird bei Plan-Ende
reserviert (claim-early), die Build-Maschinerie bleibt at-pick, und ein expliziter
ticket-sichtbarer Phasen-/Lebenszeichen-Marker macht reserviert-vs-live ablesbar
UND tote Reservierungen räumbar — Räumen niemals zeit-allein, sondern
Kandidat → Absicht → Bestätigung.

1. **Reservierung@Plan (DF1):** Bei Phase-0-Abschluss (nach Ownership-Tabelle +
   Nic-OK) für JEDES Ticket der Scheibe die **volle RAT-15-Claim-Dreierkette**
   (Worktree mit `-b` + Claim-Commit + Draft-PR `Closes #<nr>` + verify) →
   `status:in-progress` (RECON-3-konform, kein `gh issue edit`). Build-at-pick
   dispatcht in den **bestehenden** Worktree — kein zweiter Claim-PR, kein zweiter
   Branch. (Pass-2-BRICHT: der Erstwurf „nur Draft-PR reservieren, Worktree
   at-pick ohne `-b`" war gebrochen, weil RAT-15-Schritt 2 den Branch aus Schritt 1
   voraussetzt → volle Kette bei Reservierung, Worktrees persistieren billig.)
2. **Ein Marker-Comment (DF2+DF4):** Issue-Comment, erste Zeile maschinen-greppbar:
   `reservierung-lebenszeichen: <ISO-ts> · phase: reserviert|live|handoff|review · session: <id> · branch: <ref>`.
   Trägt **beides** — reserviert/live-Zustand UND Lebenszeichen. `status:in-progress`
   ist nicht mehr alleiniges live-Signal; der Marker ist die Wahrheit. Kadenz an
   Phasengrenzen (`reserviert` beim Claim, `live` beim Dispatch, `handoff`/`review`
   an den bestehenden Checkpoints).
3. **Räumen — Kandidat, nicht Zeit-Tod (DF2):** Marker-Alter macht ein Ticket nur
   zum **Räum-Kandidaten**, nicht automatisch tot (ein konformer Multi-Day-Track
   darf lange ohne Marker laufen). Vor `gh pr close`: (1) Räumabsicht-Comment,
   (2) zweiter Beleg, dass kein lebender Owner antwortet (kein neuer Marker in der
   Karenzzeit). Inspektionsgetrieben, kein cron.
4. **Prep respektiert Build-Claim (DF3):** Guard-Zeile in arbeitstag-prep.md — vor
   dem Release-to-ready-Flip prüfen, ob das Ticket `status:in-progress` trägt →
   Halt + Comment „von Build reserviert, prep ausgesetzt".

## Kill-Kriterien (laufen mit)

- **DF1-Last:** Erster Lauf misst N · Action-Laufzeit · Runner-Queue · Rate-Limit.
  Rollback auf claim-at-pick, wenn die Reservierungs-Actions die Pi-Runner-Queue
  sichtbar stauen ODER >5 min bis alle Scheibe-Tickets `in-progress` verified.
- **DF2-Fehlräumung:** Erstes fälschlich geräumtes AKTIVES Ticket → Räum-Regel
  verschärfen oder zurück.
- **DF4-Lesbarkeit:** Ein Dritter kann live nicht eindeutig von reserviert
  unterscheiden → Marker-Schema nachschärfen.
