# RAT-14 — Shared-Root Mehr-Akteur-Koordination (füllt die RAT-9-„neu bewerten"-Lücke)

- **Entschieden:** 2026-06-07 (berater-runde aus der Prozess-Werkstatt, Vorschlag +
  Codex-Antiberater, 2 Runden), **ratifiziert** 2026-06-07 (Nic, Verdikt:
  (a) flock-CHK-1 JA; (b1) Daten-Migration JA + überwacht ausgeführt; (b2) Release-
  Worktree vertagt).
- **Betrifft:** `~/.claude/commands/arbeitstag.md` (Shared-Root-HEAD-Serialisierung
  CHK-1), `~/.claude/commands/werft.md` (CHK-1-Disziplin), `conventions/services.md`
  (SVC-5 — Instanz-Daten außerhalb Checkout), `decisions/RAT-9` (füllt dessen explizit
  offen gelassene „zwei parallele arbeitstage → neu bewerten"-Lücke, CLAUDE.md §8),
  `decisions/RAT-10` (Stale-Text-Korrektur). Prozess-Ticket: **xbuddy-prozess#6 (PW-6)**.
- **Transkript (Evidenz):** `brainstorm/berater-runde/20260607-ENTSCHEID-pw6-shared-root.md`
  → Vorschlag R1 `20260607-vorschlag-pw6-shared-root.md`, Antiberater
  `2026-06-07-1231-antiberater-pw6-shared-root.md`, Berater R2 (Nachbesserung) im ENTSCHEID.

## Problem

Der geteilte Checkout `/home/buddy/repos/xbuddy` trägt drei kollidierende Rollen:
Dev-Root (Branch-Flips), lokale Merge-Basis, **und** Service-CWD (alle 9 `xbuddy-*`-
Units laufen mit `WorkingDirectory` im Checkout). Sobald zwei Top-Level-Sessions
(`/arbeitstag` + `/werft`/`/arbeitstag-prep`/Cron) parallel laufen, ist „ich besitze
den Root" falsch — der RAT-9-Eskalations-Trigger ist gefallen. Belegt in 5 Retros
(2026-06-03/06-06): Branch-Flip-Race, Push-shared-main, Deploy-Fenster-Kollision.

## Beschluss

**Scope-Entlastung:** Direkt-Push auf `origin/main` ist durch das RAT-10-Ruleset
`main-verriegelung` (live, `enforcement:active`, `bypass_actors:[]`) physisch
unmöglich. „Push-shared-main" ist an origin tot; übrig bleibt nur lokaler
`main`-Clobber (heilbar `git branch -f main origin/main`, kein Datenverlust).

**(a) CHK-1 — Shared-Root-HEAD-Serialisierung (ratifiziert).** Jede Root-HEAD-
Operation (`git checkout`, `merge`, `branch -f main`, Root-`pull --ff-only`) läuft
unter `flock -n /home/buddy/repos/xbuddy/.git/shared-root.lock`. Wer den Lock nicht
kriegt, arbeitet Worktree-only weiter (origin ist Wahrheit, lokaler `main` nur Cache).
Reine Worktree-Arbeit nimmt den Lock nie. `flock` (atomar, auto-Freigabe bei
Prozesstod — experimentell bestätigt) statt nicht-atomarem Marker-File. CHK-1 ist
eine **Dev-Prozess-Regel** und lebt in `arbeitstag.md`/`werft.md`, nicht in
`conventions/` (Genre-Trennung Produkt-Bauregel ≠ Prozess).

**(b1) Instanz-Daten aus dem Checkout (ratifiziert + ausgeführt).** SVC-5: per-Instanz-
Daten leben unter `/home/buddy/xbuddy-data/<komponente>/`, referenziert per absolutem
Unit-Pfad. Am 2026-06-07 für 7 Dienste ausgeführt + verifiziert (familie, geraete,
panel, plan, wetter, photo, eltern-chat; `cp`-statt-`mv`, Alt-Dateien als Rollback-Netz
bewahrt). **Etappe 1b offen:** router/routing.json, tools/zugangsdaten, routine/
routine_store.json haben keinen Pfad-Override → kleiner Code-Patch nötig (Folge-Ticket).

**(b2) Release-Code-Worktree — VERTAGT.** Services + Deploy auf einen vom Dev-Root
entkoppelten `release/xbuddy`-Worktree heben (schließt: Crash-Restart lädt geflippten
Code). Erst nach Etappe-1b-Erfahrung neu bewerten; gitignorte Daten überleben
Branch-Flips, daher ohne Release-Worktree kein akuter Datenverlust — b1 ist Prep für b2.

## Was ausdrücklich NICHT beschlossen wurde
- Kein erzwingender Lock-Daemon / `flock`-Blocking (Heim-Server, ein Mensch sieht
  beide Sessions). Nachrüsten erst, wenn zwei Sessions GLEICHZEITIG AUTOMATISIERT den
  Root flippen müssen.
- Keine Verlagerung der Unit-Files nach `deploy/` (SVC-2: Units leben neben dem Code).
- Kein zweiter `git clone` für b2 (ein `git worktree` teilt die Objekt-DB).
