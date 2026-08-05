# XBuddy

XBuddy ist ein Ökosystem, das Familien dabei hilft, gut begleitet durch
einen zunehmend digitalen und KI-geprägten Alltag zu kommen.

Dieses Repo hält **Code und Specs**. Die ausführliche Vision lebt im internen
Schwester-Repo `xbuddy-knowledge`; der **Kern** (was es ist, North Star) ist hier
gespiegelt, damit dieses Repo zusammen mit [`lotse`](#aufbau) allein trägt.

## Was XBuddy ist

XBuddy ist der Greenfield-Neuaufbau von **BuddyBoard**. Der Produktname nach außen
bleibt BuddyBoard; XBuddy ist der Projekt- und Repo-Name dieses Neuanfangs.

Es baut die Barrieren zwischen Familien und nützlicher Technologie ab —
Verfügbarkeit, Komplexität, Interface und Vertrauen. **Kinder** bekommen Autonomie
und Orientierung: Sie sehen, wer sie abholt, was es zu essen gibt, hören ihre Lieder
— ohne ein Elternteil fragen zu müssen. **Eltern** bekommen Entlastung vom Mental
Load. KI ist dabei **Infrastruktur, kein Feature** — Familien erleben nicht „KI",
sondern die Ergebnisse.

XBuddy ist kein einzelnes Gerät, sondern ein Ökosystem aus Display, Controller, Hub
und Buddys, das vorhandene Hardware der Familie einbindet statt neue zu erzwingen.
Die Familien-Schnittstelle ist **konversationell und plattform-eigen** — Familien
sprechen XBuddy in ihrer Sprache an (Eltern-Chat), nicht über zweite Settings-Welten.

**North Star.** XBuddy ist dann erfolgreich, wenn ein Kind etwas selbst tun kann,
wofür es vorher ein Elternteil gebraucht hätte. Jede Funktion misst sich daran:
Verschiebt sie eine Aufgabe vom Elternteil zum Kind — gibt sie Selbstwirksamkeit
zurück? Qualitätsattribute in Prioritätsreihenfolge: **Zuverlässigkeit** (ein Board,
das morgens nicht den Plan zeigt, ist schlechter als kein Board), **Einfachheit**,
**Privacy & Datensicherheit** (Verarbeitung in Deutschland, Anonymisierung vor
Verlassen der Geräte-Ebene — harter Boden), **Offline-Fähigkeit** (mit Hub ohne
Internet) und **Nicht-invasiv** (keine Push-Notifications, kein Engagement-Design).

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

## Quickstart — von clone zu laufender Familie

XBuddy ist keine Ein-Datei-App, sondern mehrere kleine Dienste (je Buddy einer),
die eine Familien-Instanz bilden. Der Weg von `git clone` zu einem laufenden System:

1. **Umgebung** — venv wie oben (`pip install .`).

2. **Per-Instanz-Dateien anlegen.** Alle familienspezifischen Dateien sind
   `gitignored` und liegen als getrackte Vorlage `*.example.json` neben dem Code
   jedes Dienstes. Kopieren und füllen:
   - `<dienst>/config.example.json` → `config.json` — Runtime (Bind-Host/Port,
     Log-Level, Provider/Modell). Werte auch per ENV überschreibbar
     (`tools/configloader.py`, z. B. `PLAN_LISTEN_PORT`).
   - Daten-Vorlagen je Dienst, z. B. `familie/familie.example.json` (Familien-
     Registry), `hoerspiel/hoerspiel.example.json`, `essen/wuensche.example.json`.
   - Der gemeinsame Datenwurzel-Pfad kommt aus **`XBUDDY_DATA_DIR`**
     (Default `/home/buddy/xbuddy-data`).

3. **Geheimnisse** (KI-Anbieter-Key, Google-OAuth, **Telegram-Bot-Token**) NICHT
   in Dateien/ENV im Klartext, sondern über den einen Per-Instanz-Speicher
   [`tools/zugangsdaten`](tools/zugangsdaten/README.md) (ZD-5) — ein geteiltes
   Modul, aus dem alle Dienste lesen/schreiben.

4. **Dienste starten** — jeder Buddy als eigener Prozess (`python3 -m <dienst>` bzw.
   die im jeweiligen `<dienst>/`-Verzeichnis dokumentierte Startzeile); der
   `seiten`-Dienst liefert die Eltern-Seiten und PWA-Mäntel same-origin aus.

### Demo-Einstieg (ohne echte Familie)

Zum Ausprobieren/für Screenshots gibt es einen Demo-Modus, der ein **gitignored
Wegwerf-Verzeichnis** `xbuddy-data-demo/` aus den generischen Seeds („Familie
Sonntag", die `*.example.json`) befüllt — die echte Instanz bleibt unangetastet:

```
tools/demo/seed_demo.sh          # populiert das Wegwerf-Dir
tools/demo/seed_demo.sh --env    # + druckt die ENV-Exports für den Demo-Run
```

**„Try it" — ein Befehl, alle Views (kein Pi/Server nötig):**

```
tools/demo/run_stack.sh          # seedet + startet alle Display-Services lokal
                                 # → Demo-Basis: http://127.0.0.1:8199
```

Der Stack startet die Buddy-Services auf **Alt-Ports** (≥ 8100, strikt außerhalb
des Live-Bereichs 5000–5099 — verweigert Live-Ports) und bündelt die Views
same-origin über einen Mini-Reverse-Proxy. Dann z. B.
`http://127.0.0.1:8199/display/plan/woche` (voller Wochenplan über den lokalen
Demo-Kalender, ohne Google), `/display/hoerspiel/mia/alben`, `/display/routine/…`
öffnen. `Ctrl-C` räumt alles ab (Teardown). Screenshots:
`tools/demo/shoot.sh /display/plan/woche`.

Details: [`tools/demo/seed_demo.sh`](tools/demo/seed_demo.sh) (#1725),
[`run_stack.sh`](tools/demo/run_stack.sh) / [`proxy.py`](tools/demo/proxy.py) /
[`shoot.sh`](tools/demo/shoot.sh) (#1767). Die gebündelten Piktogramme stammen
von [ARASAAC](https://arasaac.org) (CC BY-NC-SA 4.0 · Sergio Palao,
[`tools/demo/assets/icons/NOTICE`](tools/demo/assets/icons/NOTICE)).

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
