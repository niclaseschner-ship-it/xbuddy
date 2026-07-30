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
- **Repo `lotse`** (`~/repos/lotse`) — die versionierte Arbeits-Methode (Commands,
  Subagents, Contracts, Hooks); SSoT im eigenen Repo, `~/.claude` ist Deploy-Ziel
  (Lotse-Cutover, RAT-23 Stufe 2)
- **[`specs/`](specs/)** — lebende Specs, Quelle der Wahrheit fürs Verhalten
  - [`specs/constitution.md`](specs/constitution.md) — Prinzipien
  - [`specs/README.md`](specs/README.md) — Spec-Modell + die eine Sync-Regel
- **[`conventions/`](conventions/)** — Bauregeln über Komponenten hinweg
- **[`decisions/`](decisions/)** — Ratifizierungs-Ledger (Architektur-Entscheidungen)
- **[`WORKFLOW.md`](WORKFLOW.md)** — Ticket-/PR-Workflow
- **[`CLAUDE.md`](CLAUDE.md)** — Repo-Arbeitsregeln

## Abhängigkeiten

`pyproject.toml` ist der **einzige** Dependency-SSoT (`[project.dependencies]`,
RAT-33 Option A, #1534). CI und Deploy installieren daraus (`pip install .`);
es gibt keine per-Service-`requirements.txt` mehr. Ein lokales venv richtest du
so ein:

```
python3 -m venv .venv
.venv/bin/pip install .   # zieht die Laufzeit-Deps aus pyproject.toml
.venv/bin/pip install pytest   # Test-Dep, kein Runtime-Dep
```

`pyproject` deklariert nur die **direkt importierten** Third-Party-Libs; jeder
fehlende direkte Dep macht das isolierte CI-venv (kein `--system-site-packages`)
rot, statt still über globale Pakete kaschiert zu werden.

## Tests & Lint

Die repo-weite Test-Suite läuft über `pytest.ini` (`testpaths` listet alle
Suiten):

```
make test      # python3 -m pytest -q   — repo-weite pytest-Suite
make lint      # lint-imports           — Modul-Grenzen (MOD-*)
make ruff      # uvx ruff@0.15.15 check  — Style-Lint (pyproject.toml)
```

Alle drei sind auch CI-Gates: [`.github/workflows/pytest.yml`](.github/workflows/pytest.yml),
[`lint-imports.yml`](.github/workflows/lint-imports.yml) und
[`ruff.yml`](.github/workflows/ruff.yml) (self-hosted Pi-Runner).

Legt jemand eine neue Test-Suite an, ohne ihr Verzeichnis in
`pytest.ini`/`testpaths` einzutragen, schlägt der Guard
`tests/test_testpaths_vollstaendig.py` an — so fällt keine Suite unbemerkt aus
dem Lauf.

## Mitarbeit

Issues und PRs folgen `WORKFLOW.md`. Kein Code ohne Requirement-ID in
der Spec.
