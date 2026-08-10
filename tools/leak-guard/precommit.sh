#!/usr/bin/env bash
#
# Leak-Guard pre-commit-Wrapper (#1783).
#
# WARUM EIN WRAPPER und nicht direkt der gitleaks-Hook mit fester --config:
# Die scharfe Config `.gitleaks-local.toml` ist gitignored (sie traegt die
# echten Familien-Werte) und liegt damit nur im Haupt-Klon. In einem Worktree
# fehlt sie — und dieses Projekt arbeitet permanent mit Worktrees. gitleaks
# bricht bei fehlender --config mit FTL ab, also waere JEDER Commit in JEDEM
# Worktree und in jedem Frischklon blockiert. Genau das ist vor #1783 der Fall
# gewesen; der Hook war deshalb nie installiert und hat nie gefeuert.
#
# Der Wrapper loest die Config in drei Stufen auf:
#   1. `.gitleaks-local.toml` im Root des aktuellen Arbeitsbaums
#   2. `.gitleaks-local.toml` neben dem git-common-dir — dadurch erben
#      Worktrees das Supplement des Haupt-Klons und sind voll scharf, ohne
#      dass es pro Worktree kopiert werden muss
#   3. `.gitleaks.toml` (public Ruleset) plus laute Warnung
#
# Stufe 3 warnt und bricht NICHT ab. Ein Leak-Guard, der bei fehlender Datei
# alles verriegelt, wird nach dem zweiten blockierten Commit abgeschaltet — und
# schuetzt danach gar nichts mehr. Sichtbar reduziert ist besser als tot.

set -euo pipefail

# ── gitleaks-Binary finden ───────────────────────────────────────────────────
if command -v gitleaks >/dev/null 2>&1; then
    GITLEAKS=gitleaks
elif [ -x "$HOME/apps/bin/gitleaks" ]; then
    GITLEAKS="$HOME/apps/bin/gitleaks"
else
    echo "leak-guard: gitleaks nicht gefunden." >&2
    echo "  Release v8.21.2 von github.com/gitleaks/gitleaks holen und nach" >&2
    echo "  ~/apps/bin/gitleaks legen (siehe docs/leak-guard.md)." >&2
    exit 1
fi

# ── Config aufloesen ─────────────────────────────────────────────────────────
ROOT="$(git rev-parse --show-toplevel)"
# --git-common-dir zeigt im Worktree auf das .git des Haupt-Klons; dessen
# Elternverzeichnis ist der Haupt-Arbeitsbaum.
COMMON_DIR="$(cd "$(git rev-parse --git-common-dir)" && pwd)"
SHARED_ROOT="$(dirname "$COMMON_DIR")"

if [ -f "$ROOT/.gitleaks-local.toml" ]; then
    CONFIG="$ROOT/.gitleaks-local.toml"
elif [ -f "$SHARED_ROOT/.gitleaks-local.toml" ]; then
    CONFIG="$SHARED_ROOT/.gitleaks-local.toml"
else
    CONFIG="$ROOT/.gitleaks.toml"
    echo "leak-guard: WARNUNG — lokales Supplement .gitleaks-local.toml fehlt." >&2
    echo "  Der Guard laeuft nur gegen das public Ruleset; Wohnort und private" >&2
    echo "  Mail werden NICHT erkannt. Scharf stellen:" >&2
    echo "    cp .gitleaks-local.example.toml .gitleaks-local.toml" >&2
    echo "    # dann die <PLATZHALTER> durch die echten Werte ersetzen" >&2
fi

# ── Nur die gestageden Aenderungen pruefen ───────────────────────────────────
# `git --staged` ist die nicht-deprecatete Form von `protect --staged`.
# --redact: ein Treffer wird gemeldet, ohne den Rohwert ins Terminal (und damit
# ggf. in ein Log oder einen Screenshot) zu schreiben.
exec "$GITLEAKS" git --staged --redact --no-banner --config "$CONFIG" "$ROOT"
