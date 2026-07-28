# RAT-33 — pyproject.toml als einzige Dependency-SSoT: requirements.txt entfällt (Amendment RAT-6)

**Status:** RATIFIZIERT 2026-07-28 (Nic-Setzung „Option A direkt")
**Amendment zu:** RAT-6 (Familien-Schnittstelle skalieren)
**Epic:** #1338 (Auth-Härtung) · **Bezug:** #1515 (Divergenz-Fund: litellm fehlte), #1446 (Analyse), #1534 (Umsetzung)
**Entscheid-File:** `brainstorm/berater-runde/20260728-RATIFIZIERT-pyproject-ssot.md`

## Setzung
`pyproject.toml` wird die **einzige Dependency-SSoT** für xbuddy. CI und Deploy
installieren direkt daraus (`pip install .`); die bisherige Praxis, aus
per-Service-`requirements.txt` + Hand-venv zu ziehen, entfällt. Das
beseitigt einen zweiten abgeleiteten Wahrheitsort, der gelaufen war.

## Problem (Anlass)
Zwei Orte galten beide als SSoT: `pyproject.toml` im Repo-Root und
per-Service-`requirements.txt`-Dateien (zB `seiten/requirements.txt`). Der Diff
zwischen ihnen wurde nicht laufend synchronisiert; bei neuen Dependencies
(zB litellm in #1515) entstanden Divergenzen — Entwicklung lief lokal über
`pyproject.toml`, aber CI/Deploy zog aus `requirements.txt` und war rot.

## Entscheidung (Option A)
**Einziger Wahrheitsort: `pyproject.toml`** mit `[project.dependencies]`
und `[project.optional-dependencies]` (zB `[project.optional-dependencies.seiten]`).

- CI (`pytest.yml`, `ruff.yml`) und Deploy (xbuddy-Systemd-Units) führen
  `pip install .` (oder `pip install .[seiten]` für Scope) aus, NICHT
  Perforce-`requirements.txt`-Clones.
- Die bisherigen `seiten/requirements.txt`, `hoerspiel/requirements.txt` etc.
  entfallen. Sie waren derived (Fehlerquelle), nicht SSoT.
- `pyproject.toml` ist strukturiert und versioniert; `pip` liest die
  Metadaten zur Build-Zeit und Lockfile-Zeit, nie ein zweites Format.

## Verworfen
**Variante B (generieren):** `requirements.txt` aus `pyproject.toml` per CI
generieren (zB `pip freeze > seiten/requirements.txt` nach jedem Push).
Begründung: das ist noch ein zweiter Wahrheitsort, nur „derived": Lockfile
ist nicht Version-kontrolliert, Merges schaffen Konflikte, Handgriffe zur
Überbrückung entstehen. Gelten nicht.

## Umsetzung
Ticket #1534 (feature/1534-pyproject-ssot):
- `pyproject.toml` um fehlende Services/Sub-Deps vervollständigen (seiten,
  hoerspiel, kibuddy etc.).
- Alle `seiten/requirements.txt`, `hoerspiel/requirements.txt` etc. **löschen**.
- CI-Workflows: `pip install .` oder service-Scope direkt aus pyproject.
- Deploy-Systemd-Units (`ExecStart=…/venv/bin/python …`): env-Setup über
  `pip install -e .` oder Wheel-Install mit Service-Scope.
- Verify: ein eigentümlicher Service (`seiten`) startet mit vollem Dependency-Set.

## Rollout
Keine Vollprävention-Gate. Alle pro-Service-Branches müssen die
Abhängigkeits-Erkennung lokal via `pip install .` validieren, bevor Merge
(Teil des arbeitstag-Preflight §A.2 „Mergeability"); Live-Fehler
(fehlende Dependencies pro Service) sind über klassisches Deploy-Rollback
auffangbar.

## Kill-Kriterium
Kehrt eine Divergenz wieder auf (zwei Services nehmen ein Package auf,
eines vergisst es in `pyproject.toml`), und das wird nicht in 2 Tagen
fixiert → Rückfall zu `requirements.txt` UND Escalation zu Nic (Signal,
dass der Prozess zum Halten nicht taugt).

## Wo es landet
`pyproject.toml` (überarbeitet); `seiten/requirements.txt` (Löschung);
`hoerspiel/requirements.txt` (Löschung); CI-Workflows `.github/workflows/…`
(pip-Kommando); Deploy-Systemd-Units `~xbuddy/.service` (systemd-Umfeld);
`decisions/INDEX.md`.

## Randnotiz
Dieser Satz ist schlicht fehlende Doku einer längst praktizierten Setzung
(Nic #1446). `pyproject.toml` als SSoT ist die Norm in der Python-Welt;
der Umweg über getrennte `requirements.txt` war ein Puffer-Zugeständnis
an (Frage: hat sich erledigt? Ja, #1515-Lücke war der Beweis). Record
schafft Klarheit für zukünftige Dependency-Diskussionen.
