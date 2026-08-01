# Leak-Guard (gitleaks)

Verhindert, dass versehentlich **Privates** (Klarnamen, Familien-Mail, Heim-IPs,
Tailnet-Identifier, Telegram-Chat-ID) ins Repo — und damit später **public** —
gerät. Teil des Verkaufsreife-/Public-Wegs (#1309, Weg A „develop-in-the-open",
#1724). Das Custom-Ruleset recycelt das ratifizierte **Gate-1-Set** aus
`tools/mirror/build_public_mirror.sh` (keine neuen Muster erfunden).

## Drei Einsatzpunkte, EIN Ruleset (`.gitleaks.toml`)

| Punkt | Datei | Wirkung |
|-------|-------|---------|
| 1. Lokal (pre-commit) | `.pre-commit-config.yaml` | blockt einen Commit mit Treffer auf dem Pi, vor dem Push |
| 2. CI (PR) | `.github/workflows/leak-guard.yml` | scannt jeden PR mit gitleaks; rot bei Treffer |
| 3. HEAD-Scan | `gitleaks detect --no-git` | Leak-Liste für den Clean (feed #1719) |

`.gitleaks.toml` aktiviert zusätzlich (`useDefault = true`) die gitleaks-Standard-
Secret-Regeln (AWS/GitHub-Token etc.) als zweite Schicht.

## Lokal einrichten (einmal pro Klon)

```bash
pipx install pre-commit        # oder: uvx pre-commit
pre-commit install             # hängt den Hook in .git/hooks/pre-commit
# Ad-hoc-Scan des Arbeitsbaums:
gitleaks detect --no-git --config .gitleaks.toml --redact
```

gitleaks-Binary (falls nicht vorhanden): Release von
`github.com/gitleaks/gitleaks` (v8.21.2) laden, nach `~/apps/bin/` legen.

## Sequenzierung — NOCH NICHT `required`

Bis **#1719** den Baum auf generische Werte (`kind1/kind2/kind3`, `<tailscale-id>`
etc.) scrubbt, trägt HEAD ~2143 Treffer — überwiegend die **funktionalen Slugs**
`paula/neko/niclas` (Buddy-IDs im Live-Code), plus die echten Secrets
(`taile235cf`, Heim-IP, Chat-ID). Der CI-Job ist bis dahin **bewusst rot** als
Fortschritts-Anzeige des Clean.

**Erst NACH #1719 (gitleaks detect grün auf HEAD)** den `leak-guard`-Job in die
required-checks der Branch-Protection aufnehmen (analog RAT-30) — vorher würde er
alle Merges blockieren.

## Zweite Schicht, sobald public

Sobald das Repo public ist: **GitHub Secret Scanning + Push Protection**
aktivieren (Settings → Code security). Das fängt Standard-Provider-Tokens
server-seitig ab, ergänzend zum Custom-PII-Ruleset hier.
