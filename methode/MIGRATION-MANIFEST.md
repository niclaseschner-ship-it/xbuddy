# MIGRATION-MANIFEST — PW-74 / RAT-23 Glue-SSoT-Migration

Maschinell-auditierbarer Record der Erst-Migration der Methoden-Glue aus
`~/.claude` ins Repo unter `methode/`. Hält Quelle, Inhalt (sha256-Snapshot) und
die begründete Auswurf-Liste fest.

## Quelle (Provenienz)

- **Quell-Repo:** `~/.claude` (lokal, remote-los — die „zweite git-Welt").
- **Quell-Snapshot `S0`:** Commit `6b3a904` — „S0: Methoden-Glue-Stand gepinnt als
  Migrations-Quelle für PW-74". Vor der Migration wurde der dirty Working-Tree per
  Commit-first aufgelöst (HEAD == Working-Tree == `S0`), damit die migrierte
  Wahrheit eindeutig ist (RISKANT-a-Patch der Berater-Runde).
- **Migrations-Datum:** 2026-06-26.

## Migrierter Inhalt (sha256, 16-Zeichen-Präfix beim Snapshot)

| Datei (`methode/…`) | sha256 (Präfix) |
|---|---|
| `agents/xbuddy-antiberater.md` | `b6c03dad6dabe213` |
| `agents/xbuddy-architecture-watchdog.md` | `454a2e0b62d09b02` |
| `agents/xbuddy-berater.md` | `29001e3e99c2c773` |
| `agents/xbuddy-watchdog-prep.md` | `549bb20de7fe2df1` |
| `commands/arbeitstag.md` | `8d8dac2d10b2ab13` |
| `commands/arbeitstag-prep.md` | `ae5a7095ef12b8f8` |
| `commands/berater-runde.md` | `8d3b8427db17ae91` |
| `commands/prozesswerkstatt.md` | `eb95f9af74767af7` |
| `commands/watchdog-codex.md` | `a90c07e2ccb3d454` |
| `commands/watchdog.md` | `fe15c258090841b5` |
| `commands/werft.md` | `26a68c639dde6000` |
| `contracts/example-T137.md` | `cf5c690681f61e6d` |
| `contracts/preflight.md` | `23d4a68fb3dceb34` |
| `contracts/README.md` | `8902899f1eb2852b` |
| `contracts/retro.md` | `a20e05f6f971f12c` |
| `contracts/schemas.md` | `8e4644a1205c8c98` |
| `hooks/dispatch_status_guard.py` | `12a80221c47a1906` |
| `hooks/handoff_check.py` | `383945d5304e2930` |
| `hooks/restart_pending_log.py` | `64ca2fe785149729` |
| `hooks/status_rollback_guard.py` | `8db168622371c663` |

20 Dateien: 4 Agents · 7 Commands · 5 Contracts · 4 Hooks.

> Hinweis: Dieser Hash-Block ist ein **Snapshot-Record** (Stand `S0`/Migration).
> Die laufende Integritätsprüfung macht `deploy-methode.sh --verify-only`: es
> vergleicht `~/.claude` direkt gegen `git archive <ref>:methode/` (tautologie-frei,
> keine Manifest-Pflege bei jedem Edit). Bei künftigen Methoden-Änderungen ist
> dieser Block optional nachzuziehen, nicht zwingend.

## Bewusst AUSGESCHLOSSEN (mit Grund)

| Pfad in `~/.claude` | Grund |
|---|---|
| `commands/cynthra.md` | Fremdkörper — Launcher für `/srv/cynthra`, nicht xbuddy-Methode (Auswurf). |
| `hooks/cynthra_fence.py` | Fremdkörper — schützt `/srv/cynthra` (Auswurf). |
| `settings.json` (Voll-Datei) | Maschinen-lokaler Kompositions-Root: mischt kommandobruecke-Hooks + Permissions. Nur `settings.fragment.json` (xbuddy-Hook-Block) migriert als Referenz. |
| `hooks/_probe_dump.py`, `hooks/__pycache__/` | Scratch / Build-Artefakt. |
| `retros/*` (~160 Dateien) | Session-Auswurf, keine Methode (≠ governter Migrations-Scope). |
| `logs/*`, `projects/*`, `.credentials.json` u.a. | Runtime-State / Secrets — per `~/.claude/.gitignore` default-deny, nie Methode. |

## Laufzeit-Konstanten (bleiben `~/.claude`, kein Bug)

- `hooks/handoff_check.py` → `LOG_PATH = ~/.claude/logs/handoff_misses.jsonl`
- `hooks/restart_pending_log.py` → `LOG_PATH = ~/.claude/logs/restart_pending.jsonl`

Runtime-State am Deploy-Ziel, gitignored, keine Methode — bewusst unverändert.
