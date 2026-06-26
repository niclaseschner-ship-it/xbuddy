# AGENTS.md — Einstieg für KI-Agents & Mitstreiter

Tool-neutraler Einstiegspunkt für dieses Repo (Format-Konvention `agents.md`,
heute unter der Agentic-AI-Foundation/Linux-Foundation gestewardet; u.a. von
OpenAI Codex, Cursor, Jules gelesen). Dieses File **ersetzt nichts** — es zeigt
auf die etablierten Quellen.

## Wo was steht

| Du willst… | Lies |
|---|---|
| die **Arbeits-Methode** (wie wir arbeiten: `/werft`, `/arbeitstag`, `/berater-runde`, Subagents, Contracts, Hooks) | `methode/` — Einstieg `methode/README.md` |
| die **Repo-Arbeitsregeln** (Code, Sprache, Git, Safety) | `CLAUDE.md` |
| den **Ticket-/PR-Workflow** | `WORKFLOW.md` |
| das Soll-**Verhalten** der Komponenten | `specs/` (Modell: `specs/README.md`) |
| die **Bauregeln** über Komponenten hinweg | `conventions/` |
| ratifizierte **Architektur-Entscheidungen** | `decisions/INDEX.md` |
| das **Warum** (Vision/Kontext) | Repo `xbuddy-knowledge` → `CONTEXT.md` |

## Die Methode in einem Satz

Die Methoden-Glue ist SSoT unter `methode/` versioniert und wird per
`methode/deploy-methode.sh` nach `~/.claude/` gespiegelt, dem Laufzeit-Ort, den
der Claude-Code-Harness liest (decisions/RAT-23). Bearbeitet wird im Repo (PR +
Review + Action-Sicht), ausgeführt aus `~/.claude/`.

## Mitarbeit

`main` ist über PRs geschützt (`closes-guard`, RAT-9/RAT-10). Arbeit auf
Feature-Branches, Details in `CLAUDE.md` §8 und `WORKFLOW.md`. Sprache: Deutsch
(etablierte Fachbegriffe bleiben englisch).
