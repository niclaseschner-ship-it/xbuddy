# RAT-23 — Methoden-Glue als SSoT ins Repo (`methode/`), Copy-on-Deploy nach `~/.claude`

- **Entschieden:** 2026-06-26 (Berater-Runde „PW-74 Glue-SSoT-Migration",
  Berater + Codex-Antiberater, R1 read → propose → Antiberater → R2 hält Form),
  **ratifiziert** 2026-06-26 (Nic, „Ja — ratifizieren").
- **Anlass:** xbuddy-prozess#74 — die Methode lebte command-only in einem lokalen,
  remote-losen `~/.claude`-Repo (zwei git-Welten): nicht reviewbar, nicht von
  Actions/Mitstreitern lesbar. Der command-only-Beschluss (werft.md, 2026-06-05)
  war „aufgeschoben bis Mitstreiter dazukommen oder ein Gate die Regeln lesen
  muss"; der Trigger fiel mit Nics Public-Plan (2026-06-25).
- **Betrifft:** `methode/` (neu — Agents/Commands/Contracts/Hooks + `deploy-methode.sh`
  + `MIGRATION-MANIFEST.md` + `settings.fragment.json` + `README.md`), `AGENTS.md`
  (neu, Repo-Root, tool-neutraler Pointer), `CLAUDE.md` §1 (methode/-Zeiger),
  `decisions/INDEX.md`. Entsperrt die Glue-Hälfte von #1151 (Kosten-Mechanik:
  `usage`-Pflichtfeld in `methode/contracts/schemas.md §3` + Kollektor in
  `methode/hooks/handoff_check.py` werden normaler Repo-PR statt Hand-Edit).
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/20260626-174500-RATIFIZIERT-ENTSCHEID-pw74-glue-ssot-migration.md`
  → Vorschlag `20260626-173940-vorschlag-pw74-glue-ssot-migration.md`,
  Antiberater (Codex) `2026-06-26-1740-antiberater-pw74-glue-ssot.md`.

## Beschluss

Die governte Methoden-Glue (Agents, Commands, Contracts, Hooks) zieht als **SSoT
ins Repo unter `methode/`**; `~/.claude` wird **Deploy-Ziel**. Bearbeitet wird im
Repo (Feature-Branch-PR + Review + closes-guard + Action-Sicht), ausgeführt aus
`~/.claude/{agents,commands,contracts,hooks}/` (der Ort, den der Harness liest).

### Lese-/Deploy-Mechanismus (der Ein-Wege-Knoten)
**Copy-on-Deploy via `git archive <ref> -- methode/ | tar -x | rsync`** →
`~/.claude/`. Quelle ist **immer ein git-Objekt-Ref**, nie der Working Tree —
objektbasiert und **immun gegen den Branch-Flip**, den der Shared-Root fährt
(RAT-14, arbeitstag.md CHK-1). **Kein Symlink** (würde den CHK-1-`git branch -f
main origin/main`-Ref-Reset blockieren). Spiegelt RAT-14 (b2) Release-Worktree:
Glue = Runtime-Steuerung, liest nicht vom branch-flippenden Dev-Root.
*Constitution: Einfachheit (Rang 2) bricht Copy-vs-Symlink zugunsten Copy — ein
Mechanismus für alle Sorten; Symlink-auf-detached-Worktree bleibt dokumentierter
Rückfall, falls das Kill-Kriterium feuert.*

### Schnitt (was zieht, was bleibt)
- **Ins Repo (SSoT):** 4 Agents, 7 Commands, 5 Contracts, 4 Hooks.
- **Bleibt maschinen-lokal:** `~/.claude/settings.json` — Kompositions-Root, der
  xbuddy-Hooks, kommandobruecke-Hooks (`kb_hook.py`) und Permissions mischt. Nur
  das dokumentierte xbuddy-Hook-Fragment wandert als `methode/settings.fragment.json`.
- **Bleiben `~/.claude` (Runtime-State, gitignored, keine Methode):** die zwei
  `LOG_PATH`-Konstanten (`handoff_check.py`, `restart_pending_log.py`).
- **Auswurf (Fremdkörper /srv/cynthra):** `cynthra.md`, `cynthra_fence.py` —
  nicht migriert, bleiben lokal; eigener Cleanup-Track.
- **Pfad-Verweise** (`~/.claude/…`) in Commands/Contracts bleiben **verbatim** —
  sie zeigen aufs Laufzeit-Ziel und sind nach dem Deploy korrekt; kein Umschreiben
  auf `methode/`-Pfade (das wäre runtime-falsch).

### Quelle/Provenienz (RISKANT-a-Patch — SSoT *herstellen*, nicht nur verschieben)
`~/.claude` war dirty. Vor der Migration **Commit-first → gepinnter Snapshot
`S0`** (`~/.claude`-Commit `6b3a904`), sodass HEAD == Working-Tree == migrierte
Wahrheit. `methode/MIGRATION-MANIFEST.md` hält Quelle `S0`, sha256-Snapshot und
die begründete EXCLUDE-Liste (settings.json/cynthra/retros/Scratch/logs).

### AGENTS.md (RISKANT-b-Patch — belegt)
`AGENTS.md` (Repo-Root) sitzt **neben** CLAUDE.md/WORKFLOW.md als reiner
tool-neutraler **Pointer**, kein Eigenregelwerk. Beleg: Format-Konvention
`agents.md` (heute Agentic-AI-Foundation/Linux-Foundation-gestewardet, OpenAI
Codex gelistet; InfoQ 2025-08 „AGENTS.md Emerges as Open Standard"). Realer Fall:
der Antiberater läuft auf Codex, das AGENTS.md per Konvention liest.

## Kill-Kriterium (bindend)

Ein nach origin/main gemergter Glue-Change erscheint nach dem dokumentierten
Deploy **nicht** in `~/.claude` (Drift — fängt `deploy-methode.sh --verify-only`
per sha256), ODER der Deploy stört einen laufenden /arbeitstag (CHK-1-Branch-Flip
blockiert / Clobber), ODER ein Hook-Smoke divergiert (Exit/Deny deployt ≠ Quelle)
→ **Rückbau der betroffenen Sorte** auf `~/.claude`-lokal-SSoT, Symlink-Gabel
reaktivieren.

**Bekannte Grenze (additiver Deploy, Watchdog-Befund PW-74):** Der Drift-Wächter
fängt „neu/geändert erscheint nicht in `~/.claude`", **nicht** „aus der SSoT
entfernte Glue bleibt in `~/.claude` liegen". Kein `rsync --delete`/Orphan-Scan,
weil `~/.claude` legitim Nicht-Migriertes hält (cynthra, Scratch, `logs/`,
`retros/`). Entfernen einer Glue-Datei erfordert manuelles `~/.claude`-Cleanup.
Dokumentiert in `methode/README.md`.

## Experiment (Ein-Wege-Tür, vor Welle-1-Merge — durchgeführt)

`deploy-methode.sh --source-ref <pilot-branch>` gegen einen Ref, der `methode/`
trägt (origin/main tut das vor dem Merge noch nicht — der Antiberater fand das als
BRICHT am ursprünglichen Experiment; Patch: `--source-ref` + Default origin/main
erst nach Merge). Round-Trip-Probe: ~/.claude spiegelt den Ref branch-unabhängig,
kein Clobber, kein CHK-1-Block.

## Genre-Notiz

**Keine** neue Convention (`conventions/methode-deploy.md`): n=1, ≠ Service-Deploy-
Sorte → spec-lokal in dieser RAT + `methode/README.md`. Premature Generalization
vermieden. Industrie-Reflex (Ansible/chezmoi) verworfen (eine Maschine,
~30-Zeilen-Skript).

## Stufung (Umsetzung)

Welle 0 (diese RAT + `S0`/Manifest) → Welle 1 Pilot 4 Agents (Experiment) →
Welle 2 Contracts+Hooks (entsperrt #1151) → Welle 3 Commands+Fragment → Welle 4
*separates Ticket*: Secrets-Scrub + `gh repo edit --visibility public`. Cynthra-
Cleanup separat. (Diese Welle 0–3 wurden in einem PR zusammengeführt, mit dem
Round-Trip-Experiment als Gate — der Pilot-Charakter der Agents bleibt im
Experiment erhalten.)
