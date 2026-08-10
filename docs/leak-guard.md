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

## Status des CI-Jobs — noch nicht `required`, und warum

Der `leak-guard`-Job ist **nicht** in den required-checks der Branch-Protection
(dort stehen `closes-guard`, `ruff`, `lint-imports`). Der ursprüngliche Grund war
der noch laufende Scrub (#1719, inzwischen erledigt). Der heutige Grund ist ein
anderer:

`gitleaks dir --config .gitleaks.toml` auf getrackte Dateien liefert **5
Treffer**, alle von derselben Regel `xbuddy-github-org` (der GitHub-Org-Name in
`AGENTS.md:19/29/40`, `CLAUDE.md:19`, `README.md:67`).

Diese Regel kann strukturell nicht grün werden: der Org-Name steht in der
Clone-URL jedes Besuchers dieses public Repos. Er ist kein Geheimnis, sondern die
Adresse. Solange die Regel existiert, ist der Job dauerhaft rot und damit als
required-check unbrauchbar.

**Offene Entscheidung (Nic):** entweder `xbuddy-github-org` fällt weg bzw. bekommt
eine Allowlist für Doku-Dateien — dann kann der Job grün und `required` werden.
Oder die Regel bleibt und der Job bleibt bewusst rot, dann ist er aber nur
Anzeige und kein Gate. Nicht entschieden, nicht eigenmächtig geändert.

## Was der Guard NICHT leistet

- **Historie.** Er prüft Arbeitsbaum bzw. gestagede Änderungen. Was schon in der
  Historie liegt, holt er nicht zurück — dafür war der `filter-repo`-Lauf (#1729).
- **Branches und `refs/pull/*`.** Der Scrub erfasste `main`. Zu den Branches
  siehe #1786; die PR-Head-Refs bleiben bestehen und sind bewusst getragenes
  Restrisiko (Nic-Setzung 2026-08-10).
- **CI-Erkennung der zwei sensiblen Werte.** Siehe „Zwei Configs" oben — das ist
  Aufgabe des lokalen Hooks.
