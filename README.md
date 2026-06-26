# XBuddy

XBuddy ist ein Ökosystem, das Familien dabei hilft, gut begleitet durch
einen zunehmend digitalen Alltag zu kommen.

Dieses Repo hält **Code und Specs**. Vision und Kontext leben im
Schwester-Repo `xbuddy-knowledge`.

## Einstieg

**[`AGENTS.md`](AGENTS.md)** ist die tool-neutrale Karte des Repos — was wo liegt
und in welcher Reihenfolge man liest. Wer neu ist (Mensch oder KI-Agent), startet
dort.

## Aufbau

- **[`AGENTS.md`](AGENTS.md)** — Einstiegs-Karte (Map aller Quellen)
- **[`methode/`](methode/)** — die versionierte Arbeits-Methode (Commands,
  Subagents, Contracts, Hooks); SSoT, `~/.claude` ist Deploy-Ziel
- **[`specs/`](specs/)** — lebende Specs, Quelle der Wahrheit fürs Verhalten
  - [`specs/constitution.md`](specs/constitution.md) — Prinzipien
  - [`specs/README.md`](specs/README.md) — Spec-Modell + die eine Sync-Regel
- **[`conventions/`](conventions/)** — Bauregeln über Komponenten hinweg
- **[`decisions/`](decisions/)** — Ratifizierungs-Ledger (Architektur-Entscheidungen)
- **[`WORKFLOW.md`](WORKFLOW.md)** — Ticket-/PR-Workflow
- **[`CLAUDE.md`](CLAUDE.md)** — Repo-Arbeitsregeln

## Mitarbeit

Issues und PRs folgen `WORKFLOW.md`. Kein Code ohne Requirement-ID in
der Spec.
