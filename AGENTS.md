# AGENTS.md — Einstieg für KI-Agents & Mitstreiter

Tool-neutraler Einstiegspunkt für dieses Repo (Format-Konvention `agents.md`,
heute unter der Agentic-AI-Foundation/Linux-Foundation gestewardet; u.a. von
OpenAI Codex, Cursor, Jules gelesen). Dieses File **ersetzt nichts** — es zeigt
auf die etablierten Quellen.

> **Rückgrat-Prinzip:** Jede Regel hat **genau einen Home**. Dieses Dokument (und
> die anderen) **verweisen** auf den Home, statt Regeln zu duplizieren. Wer eine
> Regel ändert, ändert sie an ihrem Home — nicht an einer Kopie.

## Wenn du neu bist — Lese-Reihenfolge

1. `xbuddy-knowledge/CONTEXT.md` — das **Warum** (Vision; anderes Repo)
2. `specs/constitution.md` — operative **Prinzipien**
3. `specs/README.md` — das **Spec-Modell**
4. `WORKFLOW.md` — der **Ticket-/PR-Workflow**
5. `methode/README.md` — **wie wir arbeiten** (die Methode)

Dann je nach Aufgabe gezielt unten weiterspringen.

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
