# XBuddy Runner-Health — self-hosted Runner gezielt entstauen (#1113)

## Der Schmerz

Der self-hosted GitHub-Actions-Runner `pi5-buddy`
(`actions.runner.<your-org>-xbuddy.pi5-buddy.service`) hängt
gelegentlich: er meldet `status: online`, `busy: false`, nimmt aber KEINE Jobs
an. Workflow-Runs stehen 8–18 Minuten in `queued`, bis jemand den Service von
Hand neustartet. Das blockiert die ganze CI — Claim-Flow und Auto-Merge stehen
(vgl. Memory `reference_pi5_runner_stall`).

Dieses Verzeichnis bringt einen periodischen Health-Check, der genau diesen
Stau erkennt und den Runner-Service gezielt neustartet — **ohne je einen
gesunden Runner zu killen.**

## Kill-Safety — warum der Restart eng gegated ist

Der Check restartet **nur** bei diesem eng definierten Zustand:

> Service `active` **UND** Runner `busy: false` **UND** mindestens ein `queued`
> Workflow-Run älter als der Schwellwert **N** (Default 5 Minuten).

Alles andere ist explizit `no_action`:

| Zustand | Bedeutung | Aktion |
|---|---|---|
| Service nicht `active` | anderer Fehlerpfad (Crash/gestoppt) | keine |
| Runner `busy: true` | arbeitet gerade an einem Job | **keine** (ein Restart würde den Job abwürgen) |
| Runner `busy: false`, keine/frische Queue | gesunder idle-Runner | keine |
| Runner `busy: false`, Queue-Alter > N | **stuck** (der #1113-Fall) | **restart** |

Die Entscheidung ist eine reine Funktion `decide(state, N)` in
`runner_health.py` — Zustand rein, Verdikt raus, kein I/O. Sie ist mit
gemockten Eingaben getestet (`tests/test_runner_health.py`), inklusive der
Kill-Safety-Fälle (busy-Runner mit alter Queue → `no_action`; idle-Runner ohne
Stau → `no_action`). Der reale `gh api`-Aufruf, `systemctl is-active` und
`systemctl restart` sind eine dünne I/O-Schale drumherum.

## Bekannte Einschränkung — Queued-Runs ohne Label-Filter

`gather_state` zählt **alle** queued Workflow-Runs aus der GitHub-API, unabhängig
davon, welches `runs-on`-Label ein Run benötigt. Runs für GitHub-hosted-Runner
(`ubuntu-latest` o. ä.) fließen ununterschieden in `queued_ages_seconds` ein
und können den Stuck-Threshold erreichen.

Das ist bewusst akzeptiert, weil **pi5-buddy der einzige Self-Hosted-Runner**
in diesem Repo ist: jeder queued Run muss von pi5-buddy bedient werden, ein
Label-Filter wäre redundant. Bei einem gemischten Setup (mehrere Self-Hosted-Runner
oder GitHub-hosted-Runs für andere Labels) würde der Check zu früh feuern —
dann müsste `gather_state` pro queued Run die Jobs-Endpoint abfragen
(`actions/runs/{id}/jobs`) und Labels abgleichen.

## Warum NICHT `Restart=always` (verworfen)

Naheliegend, aber falsch: `Restart=always` bzw. eine `WatchdogSec`-Watchdog-Logik
in der Runner-Unit selbst würde den Stau nicht lösen.

- Der hängende Runner-Prozess **läuft** (`active`, `busy: false`) — er ist nicht
  abgestürzt. `Restart=always` greift nur bei Prozess-Ende, hier gibt es keins.
- `WatchdogSec` verlangt, dass der überwachte Prozess aktiv `sd_notify`-Pings
  sendet; der GitHub-Runner tut das nicht — die Watchdog-Logik greift nie.
- Ein pauschaler Neustart-Reflex würde den Runner auch **mitten im Job** killen
  (`busy: true`) und laufende CI-Jobs abwürgen.

Deshalb ein **externer, zustands-gewahrter** Check, der `busy` und das
Queue-Alter liest, bevor er handelt — kein blinder Restart-Reflex.

## Aufruf

```bash
# Entscheiden + bei Bedarf handeln (das macht der Timer):
python3 deploy/runner/runner_health.py

# Nur entscheiden + loggen, NICHT restarten (zum Prüfen von Hand):
python3 deploy/runner/runner_health.py --dry-run
```

Jeder Lauf schreibt eine JSON-Zeile nach stdout (journald ist die Quelle der
Wahrheit): `action`, `reason`, `runner_found`, `runner_busy`,
`max_queue_age_seconds`, `threshold_seconds`, `dry_run`. Bei `--dry-run` wird
nie restartet.

`runner_found: false` im Log bedeutet: der konfigurierte Runner-Name wurde
nicht in der GitHub-API-Antwort gefunden — wahrscheinlich ein Namens-Tippfehler
in `--runner-name` oder der Service-Unit. In diesem Fall wird immer `no_action`
zurückgegeben (kein stiller Restart).

Flags / ENV-Overrides (nichts hartkodiert):
`--repo` (Default `<your-org>/xbuddy`), `--service`,
`--runner-name` (Default `pi5-buddy`), `--threshold-seconds` (Default `300`).

## Schwellwert N und Timer-Intervall

- **N = 300 s (5 Minuten).** Ein idle-Runner greift einen queued Job in
  Sekunden. 5 Minuten lässt kurze Registrierungs-/Pickup-Fenster (z. B. während
  eines Runner-Neustarts) unangetastet und schlägt trotzdem lange vor der
  bisher beobachteten 8–18-Minuten-Handarbeit an.
- **Timer alle 5 Minuten** (`OnUnitActiveSec=5min`, erster Lauf 2 min nach
  Boot). Zusammen mit N=5min wird ein Stau spätestens ~10 Minuten nach dem
  Hängenbleiben entstaut.

## Auth — kein Secret im Repo

`runner_health.py` liest den CI-Zustand über `gh api`. `gh` braucht Auth. Zwei
secret-freie Wege, in Reihenfolge der Präferenz:

1. **`gh`-CLI-Login des Service-Users.** Läuft der Health-Service unter einem
   User, dessen `gh` bereits eingeloggt ist, ist nichts weiter nötig.
2. **`GH_TOKEN` aus einer per-Instanz-EnvironmentFile** außerhalb des Checkouts
   (SVC-5). Die Service-Unit lädt optional
   `__XBUDDY_DATA__/runner/health.env`:

   ```ini
   # __XBUDDY_DATA__/runner/health.env  (liegt NICHT im Repo)
   GH_TOKEN=github_pat_...
   ```

   Der Token braucht nur **Lese**-Rechte auf Actions (`actions:read` bzw. ein
   Fine-Grained-PAT mit „Actions: Read-only" für das Repo). Der Restart ist ein
   lokales `systemctl` und braucht keinen GitHub-Scope.

> Läuft der Health-Service als **root** (nötig, damit `systemctl restart` den
> als System-Service installierten Runner treffen darf), hat root i. d. R.
> keinen `gh`-Login — dann ist Weg 2 (EnvironmentFile mit `GH_TOKEN`) der reale
> Deploy-Pfad. Ohne verfügbaren Token bricht der erste `gh api`-Call ab; das ist
> eine Onboarding-Frage (Token bereitstellen), kein Grund, ein Secret ins Repo
> zu legen.

## Ausrollen — einmal pro Instanz

Diese Dateien sind **Vorlagen** (`__…__`-Platzhalter, analog
`deploy/systemd/README.md`). Vor `systemctl enable` ersetzen und nach
`/etc/systemd/system/` kopieren:

```bash
sudo sed \
  -e 's|__XBUDDY_REPO__|/home/buddy/repos/xbuddy|g' \
  -e 's|__XBUDDY_PYTHON__|/home/buddy/apps/venv/bin/python|g' \
  -e 's|__XBUDDY_DATA__|/home/buddy/xbuddy-data|g' \
  -e 's|__XBUDDY_RUNNER_NAME__|pi5-buddy|g' \
  -e 's|__XBUDDY_RUNNER_SERVICE__|actions.runner.<your-org>-xbuddy.pi5-buddy.service|g' \
  deploy/runner/xbuddy-runner-health.service \
  | sudo tee /etc/systemd/system/xbuddy-runner-health.service >/dev/null

sudo cp deploy/runner/xbuddy-runner-health.timer \
  /etc/systemd/system/xbuddy-runner-health.timer

# Optional: Token bereitstellen (siehe „Auth")
sudo install -d /home/buddy/xbuddy-data/runner
# echo 'GH_TOKEN=...' | sudo tee /home/buddy/xbuddy-data/runner/health.env

sudo systemctl daemon-reload
sudo systemctl enable --now xbuddy-runner-health.timer
```

Erst-Verifikation von Hand (ohne zu handeln):

```bash
sudo systemctl start xbuddy-runner-health.service   # ein oneshot-Lauf
journalctl -u xbuddy-runner-health.service -n 5     # JSON-Zeile lesen
```

## Rollback

```bash
sudo systemctl disable --now xbuddy-runner-health.timer
sudo rm /etc/systemd/system/xbuddy-runner-health.timer \
        /etc/systemd/system/xbuddy-runner-health.service
sudo systemctl daemon-reload
```

Nach dem Entfernen ist der Zustand exakt der vorherige — der Runner-Service
selbst bleibt unangetastet, der Check hat keinen persistenten Zustand.

## Warum hier und nicht in `deploy/systemd/`

`deploy/systemd/` hostet die **Produkt**-Services (SVC-1..5: Router, Plan,
Wetter, …), die neben ihrem Komponenten-Code liegen. Der Runner ist keine
xbuddy-Produkt-Komponente, sondern CI-Infrastruktur ohne Repo-Code-Ort —
deshalb ein eigenes `deploy/runner/`, das Skript, Test und Units zusammenhält.

## Tests

```bash
python -m pytest deploy/runner -q
```

Belegt die Entscheidungs-Logik rot/grün, inkl. Kill-Safety (busy-Runner und
gesunder idle-Runner werden nie restartet) und Entstau (nur active + busy:false
+ Queue-Alter > N ergibt `restart`).
