# Leak-Guard (gitleaks)

Verhindert, dass versehentlich **Privates** (Klarnamen, Familien-Mail, Heim-IPs,
Tailnet-Identifier, Telegram-Chat-ID) ins Repo — und damit **public** — gerät.
Teil des Verkaufsreife-/Public-Wegs (#1309, Weg A „develop-in-the-open", #1724).
Das Custom-Ruleset recycelt das ratifizierte **Gate-1-Set** des früheren,
inzwischen entfernten Mirror-Skripts; die Muster leben heute direkt in
`.gitleaks.toml` (keine neuen Muster erfunden).

## Zwei Configs, nicht eine

Das ist der Kern und die häufigste Verwechslung:

| Datei | getrackt? | Inhalt | wer nutzt sie |
|---|---|---|---|
| `.gitleaks.toml` | ja, **public** | generische Muster: Chat-ID, Heim-IP, Tailnet-Identifier, Klarnamen der Erwachsenen, Org-Name | CI |
| `.gitleaks-local.toml` | **nein**, gitignored | die Werte, die nicht public sein dürfen: **Wohnort, private Mail, Kind-Slugs** | pre-commit lokal |
| `.gitleaks-local.example.toml` | ja, public | Vorlage mit Platzhaltern für das Supplement | Fresh-Install |

Das Supplement extendet die public Config (`[extend] path = ".gitleaks.toml"`)
und erbt damit deren Regeln plus die gitleaks-Standard-Secret-Regeln
(`useDefault = true`, AWS-/GitHub-Token etc.).

Warum diese Trennung: eine Detektor-Regel muss den Wert nennen, den sie sucht.
Eine public Regel für den Wohnort würde den Wohnort veröffentlichen — die
Schutzregel wäre selbst das Leck. Deshalb liegen genau diese Werte lokal
(#1759 für Wohnort und Mail, #1783 für die Kind-Slugs).

**Konsequenz, die man wissen muss:** CI ist damit absichtlich *stumpfer* als
lokal. CI kann eine neu eingeführte Wohnort-Nennung nicht sehen. Der Schutz
dagegen ist der pre-commit-Hook, nicht die Pipeline.

## Drei Einsatzpunkte

| Punkt | Datei | Config | Wirkung |
|---|---|---|---|
| 1. Lokal (pre-commit) | `.pre-commit-config.yaml` → `tools/leak-guard/precommit.sh` | Supplement, sonst public | blockt den Commit **vor** dem Push |
| 2. CI (PR) | `.github/workflows/leak-guard.yml` | public | rot bei Treffer |
| 3. Ad-hoc-Scan | `gitleaks dir` | frei wählbar | Leak-Liste zum Aufräumen |

## Lokal einrichten (einmal pro Klon)

```bash
# 1. gitleaks-Binary, falls nicht vorhanden: Release v8.21.2 von
#    github.com/gitleaks/gitleaks laden und nach ~/apps/bin/gitleaks legen.

# 2. Das scharfe Supplement anlegen — DIESER SCHRITT WIRD AM HÄUFIGSTEN
#    VERGESSEN, und ohne ihn erkennt der Guard Wohnort und Mail nicht:
cp .gitleaks-local.example.toml .gitleaks-local.toml
#    dann die <PLATZHALTER> durch die echten Familien-Werte ersetzen

# 3. Hook einhängen:
uvx pre-commit install        # oder: pipx install pre-commit && pre-commit install

# Ad-hoc-Scan des Arbeitsbaums:
~/apps/bin/gitleaks dir --config .gitleaks-local.toml --redact --no-banner .
```

### Der Wrapper und warum es ihn gibt

Der Hook läuft nicht direkt gegen gitleaks, sondern über
`tools/leak-guard/precommit.sh`. Grund: das Supplement ist gitignored und liegt
damit nur im Haupt-Klon. Ein Worktree hat es nicht — und dieses Projekt arbeitet
permanent mit Worktrees. gitleaks bricht bei fehlender `--config` **fatal** ab,
also wäre jeder Commit in jedem Worktree und jedem Frischklon blockiert. Genau
deshalb war der Hook vor #1783 nie installiert und hat nie gefeuert.

Der Wrapper löst die Config in drei Stufen auf:

1. `.gitleaks-local.toml` im Root des aktuellen Arbeitsbaums
2. `.gitleaks-local.toml` neben dem `--git-common-dir` — **Worktrees erben damit
   das Supplement des Haupt-Klons und sind voll scharf**, ohne Kopie pro Worktree
3. `.gitleaks.toml` plus laute Warnung, dass reduziert gescannt wird

Stufe 3 warnt und bricht **nicht** ab. Ein Guard, der bei fehlender Datei alles
verriegelt, wird nach dem zweiten blockierten Commit abgeschaltet — und schützt
danach gar nichts. Sichtbar reduziert ist besser als tot.

### Falle: `core.hooksPath`

Ist `core.hooksPath` in `.git/config` gesetzt, verweigert `pre-commit install`
die Arbeit („Cowardly refusing to install hooks with `core.hooksPath` set") —
auch dann, wenn der Pfad auf das Standardverzeichnis zeigt und damit wirkungslos
ist. Auf dem Pi war genau das der Fall. Zwei Wege:

```bash
git config --unset-all core.hooksPath && uvx pre-commit install
```

oder `.git/hooks/pre-commit` von Hand anlegen und dort den Wrapper aufrufen —
so läuft es derzeit auf dem Pi (siehe Kopf der Datei).

## Zweite Schicht: GitHub-seitig — **aktiv**

**Secret Scanning** und **Push Protection** sind seit 2026-08-10 aktiviert
(Settings → Code security). Sie fangen Standard-Provider-Tokens server-seitig
ab, ergänzend zum Custom-PII-Ruleset hier. Push Protection blockt einen Push mit
erkanntem Token, bevor er ankommt.

Nicht aktiviert: `secret_scanning_validity_checks` und
`secret_scanning_non_provider_patterns` — die schicken Fundstellen zur Prüfung
an Dritte bzw. erzeugen deutlich mehr Rauschen. Bewusst aus.

## Status des CI-Jobs — grün-fähig, noch nicht `required`

`gitleaks dir --config .gitleaks.toml` auf die getrackten Dateien liefert
**0 Treffer**. Der Job **kann** grün sein (#1810).

Das war bis #1810 anders: 5 Treffer, alle von `xbuddy-github-org`, alle derselbe
Fall — Markdown-Links auf das public Repo `lotse`. Der Org-Name steht in der
Clone-URL jedes Besuchers dieses public Repos; er ist die Adresse, kein
Geheimnis. Ein Guard, der auf die eigene Adresse anschlägt, ist dauerhaft rot,
und ein dauerhaft roter Job wird ignoriert — dann leistet er auch als Anzeige
nichts mehr.

Was die Regel wirklich sucht, ist die **hartkodierte Kopplung**: ein Pfad, ein
Remote, ein API-Aufruf, der dieses eine Konto festschreibt, macht das Repo für
eine fremde Familie unbrauchbar. Deshalb ist nur **eine** Form ausgenommen, der
Markdown-Inline-Link `](https://github.com/…`. Es bleibt Treffer: dieselbe URL
als String im Code, ein `git@github.com:`-Remote, und der Org-Name ohne Link
auch in Markdown.

Wichtig für den nächsten Umbau: **gitleaks 8.21.2 kennt `matchCondition` nicht**
und verknüpft mehrere Allowlist-Kriterien mit ODER. Der naheliegende Ansatz
„`paths = ['\.md$']` UND Zeilen-Regex" wäre damit viel zu breit — nachgewiesen
über eine Präzisions-Matrix in #1810. Der Link-Kontext im Muster selbst erreicht
das UND ohne das Feature.

**Noch nicht `required`:** die Branch-Protection führt `closes-guard`, `ruff`,
`lint-imports`. Ob `leak-guard` dazukommt, ist eine Gate-Entscheidung und gehört
nach **#1803** (Merge-Gate, analog RAT-30) — nicht hierher. Grün-fähig ist die
Voraussetzung dafür, nicht die Entscheidung selbst.

## Was der Guard NICHT leistet

- **Historie.** Er prüft Arbeitsbaum bzw. gestagede Änderungen. Was schon in der
  Historie liegt, holt er nicht zurück — dafür war der `filter-repo`-Lauf (#1729).
- **Branches und `refs/pull/*`.** Der Scrub erfasste `main`. Zu den Branches
  siehe #1786; die PR-Head-Refs bleiben bestehen und sind bewusst getragenes
  Restrisiko (Nic-Setzung 2026-08-10).
- **CI-Erkennung der zwei sensiblen Werte.** Siehe „Zwei Configs" oben — das ist
  Aufgabe des lokalen Hooks.
