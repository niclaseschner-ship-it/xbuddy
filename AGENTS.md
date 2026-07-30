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
5. Repo **`lotse`** (`~/repos/lotse`, `README.md`) — **wie wir arbeiten** (die Methode)

Dann je nach Aufgabe gezielt unten weiterspringen.

## Wo was steht

| Du willst… | Lies |
|---|---|
| die **Arbeits-Methode** (wie wir arbeiten: `/werft`, `/arbeitstag`, `/berater-runde`, Subagents, Contracts, Hooks) | Repo **`lotse`** (`~/repos/lotse`) — Einstieg `README.md` |
| die **Repo-Arbeitsregeln** (Code, Sprache, Git, Safety) | `CLAUDE.md` |
| den **Ticket-/PR-Workflow** | `WORKFLOW.md` |
| das Soll-**Verhalten** der Komponenten | `specs/` (Modell: `specs/README.md`) |
| die **Bauregeln** über Komponenten hinweg | `conventions/` |
| ratifizierte **Architektur-Entscheidungen** | `decisions/INDEX.md` |
| das **Warum** (Vision/Kontext) | Repo `xbuddy-knowledge` → `CONTEXT.md` |

## Die Methode in einem Satz

Die Methoden-Glue lebt seit dem Lotse-Cutover (decisions/RAT-23, Stufe 2) im
**eigenen Repo `lotse`** (`~/repos/lotse`) — nicht mehr unter `methode/` in
diesem Repo. Sie wird per `lotse/deploy.sh` nach `~/.claude/` gespiegelt, dem
Laufzeit-Ort, den der Claude-Code-Harness liest. Bearbeitet wird im lotse-Repo
(PR + Review + CI-Sicht), ausgeführt aus `~/.claude/`.

## Mitarbeit

`main` ist über PRs geschützt (`closes-guard`, RAT-9/RAT-10). Arbeit auf
Feature-Branches, Details in `CLAUDE.md` §8 und `WORKFLOW.md`. Sprache: Deutsch
(etablierte Fachbegriffe bleiben englisch).
