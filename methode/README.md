# methode/ — die Arbeits-Methode als SSoT

Hier lebt die **Methoden-Glue** des xbuddy-Ökosystems versioniert: die
Orchestrierungs-Commands, die Subagent-Definitionen, die maschinen-lesbaren
Contracts und die Guard-Hooks. Vor PW-74 lag sie command-only in einem lokalen,
remote-losen `~/.claude`-Repo — nicht reviewbar, nicht von Actions/Mitstreitern
lesbar. Dieser Ordner beendet die Spaltung (decisions/RAT-23).

## Das Modell: Repo = SSoT, `~/.claude` = Deploy-Ziel

- **Bearbeitet** wird hier (`methode/`), über normale Feature-Branch-PRs nach
  `main` (Review + closes-guard + Action-Sicht).
- **Ausgeführt** wird aus `~/.claude/{agents,commands,contracts,hooks}/` — das ist
  der Ort, den der Claude-Code-Harness liest. `./deploy-methode.sh` spiegelt die
  ratifizierte SSoT dorthin.
- **Pfad-Verweise** in den Commands/Contracts zeigen bewusst auf `~/.claude/…` —
  das ist der **Laufzeit-Ort**, an dem sich die Glue gegenseitig referenziert.
  Sie sind nach dem Deploy korrekt; sie werden NICHT auf `methode/`-Pfade
  umgeschrieben.

## Inhalt

| Ordner | Was | Sorte |
|--------|-----|-------|
| `agents/` | Subagent-Definitionen (berater, antiberater, watchdog, watchdog-prep) | reine Methode |
| `commands/` | `/arbeitstag`, `/arbeitstag-prep`, `/berater-runde`, `/prozesswerkstatt`, `/watchdog`, `/watchdog-codex`, `/werft` | Methode |
| `contracts/` | `schemas.md`, `preflight.md`, `retro.md`, `README.md`, `example-T137.md` | Schema/Doku |
| `hooks/` | `dispatch_status_guard.py`, `handoff_check.py`, `status_rollback_guard.py`, `restart_pending_log.py` | ausführbares Harness |

`settings.fragment.json` dokumentiert die xbuddy-Hook-Verdrahtung (die echte
`~/.claude/settings.json` bleibt maschinen-lokaler Kompositions-Root — sie mischt
kommandobruecke-Hooks und Permissions hinzu).

**Bewusst NICHT hier** (siehe `MIGRATION-MANIFEST.md`): Cynthra (`cynthra.md`,
`cynthra_fence.py` — Fremdkörper `/srv/cynthra`), `~/.claude/retros/` (Session-
Auswurf), Scratch (`_probe_dump.py`, `__pycache__`), `~/.claude/logs/` (Runtime-
State).

## Deploy

```bash
# Nach einem Merge nach main (Default-Quelle origin/main):
methode/deploy-methode.sh

# Vor dem Merge gegen einen Pilot-Branch testen (origin/main trägt methode/
# anfangs noch nicht):
methode/deploy-methode.sh --source-ref feature/pw74-glue-ssot --dry-run

# Drift-Probe (Kill-Kriterium RAT-23): weicht ~/.claude von der SSoT ab?
methode/deploy-methode.sh --verify-only
```

Quelle ist immer ein git-Objekt-Ref (`git archive`), nie der Working Tree —
branch-flip-immun (RAT-14). Nach jedem Merge einer Methoden-Änderung gehört der
Deploy zur „nach Merge"-Disziplin (wie `systemctl restart` für Services).
