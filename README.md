# XBuddy

### ▶︎ Live-Demo — **[xbuddy-demo-mobil.pages.dev](https://xbuddy-demo-mobil.pages.dev/)**

Sieben Karten, die in einer Minute zeigen, worum es geht — läuft ohne Anmeldung
im Browser.

---

**Ein selbst-gehostetes Assistenz-System für Familien.** Ein Kind sieht am
Display, wer es heute abholt, was es zu essen gibt und was es morgens anziehen
soll — und hört seine Hörspiele, ohne ein Elternteil zu fragen. Eltern sprechen
mit demselben System über einen Telegram-Chat und kleine Web-Apps: „Setz Brot auf
die Einkaufsliste", „Wer holt Freitag ab?".

**North Star.** XBuddy ist dann erfolgreich, wenn ein Kind etwas selbst tun kann,
wofür es vorher ein Elternteil gebraucht hätte. Jede Funktion misst sich daran:
Verschiebt sie eine Aufgabe vom Elternteil zum Kind — gibt sie Selbstwirksamkeit
zurück?

Alles läuft auf **eigener Hardware** (ein Raspberry Pi genügt) und bindet die
Geräte ein, die die Familie schon hat, statt neue zu erzwingen. KI steckt
darunter als **Infrastruktur, nicht als Feature** — die Familie erlebt nicht
„KI", sondern die Ergebnisse.

## Screenshots

Aus dem Demo-Stack, den dieses Repo mitbringt (`tools/demo/run_stack.sh`) —
generische Demo-Familie **Sonntag**, keine echten Familieninhalte.

**Was Kinder sehen** — Vollbild-Displays, kein Menü, keine Anmeldung:

| | |
|---|---|
| ![Wochenplan](docs/screenshots/plan-woche.png) | ![Morgen-Routine](docs/screenshots/routine-morgen.png) |
| Wochenplan — wer holt ab, was ist heute | Morgen-Routine — was muss ich tun, wie viel Zeit bleibt |
| ![Wetter & Anziehen](docs/screenshots/wetter-heute.png) | ![Essens-Wünsche](docs/screenshots/essen-wunsch.png) |
| Wetter mit Anzieh-Empfehlung | Essens-Wünsche — das Kind schreibt selbst auf die Einkaufsliste |
| ![Hörspiele](docs/screenshots/hoerspiel-alben.png) | ![Foto-Rahmen](docs/screenshots/photo-rahmen.png) |
| Hörspiel-Bibliothek | Foto-Rahmen |

**Was Eltern sehen** — der Chat und vier kleine Web-Apps am Handy:

| | |
|---|---|
| ![Eltern-Chat](docs/screenshots/eltern-chat-sonntag.png) | ![Einkaufsliste](docs/screenshots/einkauf.png) |
| Eltern-Chat in Telegram — die Haupt-Schnittstelle | Einkaufsliste |
| ![Plan-Einstellungen](docs/screenshots/plan-einstellungen.png) | ![Routine anpassen](docs/screenshots/routine-anpassen.png) |
| Wochenplan einrichten | Morgenroutine anpassen |
| ![Hörspiel-Einstellungen](docs/screenshots/hoerspiel-eltern.png) | |
| Hörspiel-Einstellungen (Tempo, Pausen, Stimme) | |

> Alle Views + Anleitung zum Neu-Erzeugen: [`docs/screenshots/`](docs/screenshots/).
> Der Eltern-Chat ist ein **erfundener** Beispiel-Verlauf, kein echter Chat.

## Selbst ausprobieren — ein Befehl, kein Server nötig

```
tools/demo/run_stack.sh          # seedet Demo-Daten + startet alle Views lokal
                                 # → http://127.0.0.1:8199
```

Dann z. B. `/display/plan/woche`, `/display/hoerspiel/mia/alben` oder die
Eltern-Apps unter `/seiten/essen/einkauf/` und `/seiten/plan/einstellungen/`
öffnen. `Ctrl-C` räumt alles wieder ab.

Der Stack legt seine Daten in ein **Wegwerf-Verzeichnis** `xbuddy-data-demo/` und
läuft auf Ports ab 8100 — eine echte Instanz auf derselben Maschine bleibt
unangetastet. Einzelne Bilder machen: `tools/demo/shoot.sh /display/plan/woche`.

Die Eltern-Chat-Sicht ist ein Telegram-Bot und lässt sich nicht als Web-View
zeigen; dafür liegt eine statische Beispielseite bereit:
[`tools/demo/chat_transcript/eltern-chat-sonntag.html`](tools/demo/chat_transcript/eltern-chat-sonntag.html)
— einfach im Browser öffnen.

Die Piktogramme stammen von [ARASAAC](https://arasaac.org) (CC BY-NC-SA 4.0 ·
Sergio Palao, [`NOTICE`](tools/demo/assets/icons/NOTICE)).

## Wie es aufgebaut ist

XBuddy ist keine Ein-Datei-App, sondern mehrere kleine Dienste — einer je
„Buddy" (Plan, Routine, Wetter, Essen, Hörspiel, Foto …). Zusammen bilden sie
eine **Familien-Instanz**. Was von Familie zu Familie verschieden ist, steht in
Konfigurationsdateien, die nicht im Git liegen; der Code hier ist die Vorlage.

Qualitätsattribute in Prioritätsreihenfolge: **Zuverlässigkeit** (ein Board, das
morgens den Plan nicht zeigt, ist schlechter als kein Board), **Einfachheit**,
**Privacy** (Verarbeitung in Deutschland, Anonymisierung bevor Daten die
Geräte-Ebene verlassen), **Offline-Fähigkeit** und **nicht-invasiv** (keine
Push-Benachrichtigungen, kein Engagement-Design).

## Von `git clone` zu einer laufenden Familie

1. **Umgebung.** `pyproject.toml` ist die einzige Dependency-Quelle:

   ```
   python3 -m venv .venv
   .venv/bin/pip install .        # Laufzeit-Abhängigkeiten
   .venv/bin/pip install pytest   # nur für die Tests
   ```

2. **Per-Instanz-Dateien anlegen.** Jede familienspezifische Datei liegt als
   Vorlage `*.example.json` neben dem Code ihres Dienstes — kopieren und füllen:
   - `<dienst>/config.example.json` → `config.json` (Bind-Host/Port, Log-Level,
     KI-Anbieter/Modell; jeder Wert auch per Umgebungsvariable überschreibbar,
     z. B. `PLAN_LISTEN_PORT`)
   - Daten-Vorlagen je Dienst, etwa `familie/familie.example.json` (wer gehört
     zur Familie), `hoerspiel/hoerspiel.example.json`, `essen/wuensche.example.json`
   - Der gemeinsame Datenordner kommt aus `XBUDDY_DATA_DIR`

3. **Geheimnisse** (KI-Anbieter-Key, Google-OAuth, Telegram-Bot-Token) gehören
   **nicht** im Klartext in Dateien oder Umgebungsvariablen, sondern in den
   Zugangsdaten-Speicher: [`tools/zugangsdaten`](tools/zugangsdaten/README.md).

4. **Dienste starten** — jeder Buddy als eigener Prozess (`python3 -m <dienst>`,
   Details im jeweiligen Verzeichnis). Der `seiten`-Dienst liefert die
   Eltern-Seiten und die Web-Apps aus.

## Wo was liegt

- **[`AGENTS.md`](AGENTS.md)** — die Einstiegskarte: was wo liegt und in welcher
  Reihenfolge man es liest. Wer neu ist (Mensch oder KI-Agent), startet dort.
- **[`specs/`](specs/)** — lebende Specs, die Quelle der Wahrheit fürs Verhalten;
  [`constitution.md`](specs/constitution.md) hält die Prinzipien
- **[`conventions/`](conventions/)** — Bauregeln über Komponenten hinweg
- **[`decisions/`](decisions/)** — Ledger der Architektur-Entscheidungen: einmal
  entschieden, festgehalten, nicht neu aufgerollt
- **[`WORKFLOW.md`](WORKFLOW.md)** — wie Tickets und PRs laufen ·
  **[`CLAUDE.md`](CLAUDE.md)** — Arbeitsregeln im Repo
- **[`lotse`](https://github.com/niclaseschner-ship-it/lotse)** — die Methode, mit
  der XBuddy gebaut wird, als eigenes public Repo
  ([Live-Demo](https://lotse-demo.pages.dev/))

## Tests & Lint

```
make test      # python3 -m pytest -q   — repo-weite Suite
make lint      # lint-imports           — Modul-Grenzen
make ruff      # uvx ruff@0.15.15 check — Style-Lint
```

Alle drei sind auch CI-Gates
([`pytest.yml`](.github/workflows/pytest.yml),
[`lint-imports.yml`](.github/workflows/lint-imports.yml),
[`ruff.yml`](.github/workflows/ruff.yml)). Wer eine neue Test-Suite anlegt, ohne
sie in `pytest.ini` einzutragen, wird von einem Guard-Test daran erinnert — so
fällt keine Suite unbemerkt aus dem Lauf.

## Mitarbeit

Issues und PRs folgen [`WORKFLOW.md`](WORKFLOW.md). Kein Code ohne
Requirement-ID in der Spec — was das heißt, steht in
[`specs/README.md`](specs/README.md).
