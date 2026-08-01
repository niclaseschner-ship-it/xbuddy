#!/usr/bin/env bash
# Demo-Modus (#1725, Part of #1309 public/verkaufsreif).
#
# Populiert ein **gitignored Wegwerf-Dir** (`xbuddy-data-demo/`) aus den
# generischen, getrackten Seeds (Familie Sonntag — `*.example.json`, seit #1719).
# Danach kann eine Demo-Instanz gegen dieses Dir laufen → populiertes System für
# Screenshots/Onboarding/Demo-Material, OHNE getrackte Dateien zu verschmutzen
# und OHNE die Live-Services/-Daten anzufassen.
#
# ⚠️ SICHERHEIT: dieses Skript schreibt AUSSCHLIESSLICH nach `xbuddy-data-demo/`.
#    Es startet/neustartet KEINE systemd-Services und fasst `/home/buddy/xbuddy-data/`
#    (die echte Familie) NIE an. Der Demo-Run läuft separat (siehe `--env` + README).
#
# Lauf:
#   tools/demo/seed_demo.sh            # populiert das Wegwerf-Dir
#   tools/demo/seed_demo.sh --env      # + druckt die ENV-Exports für den Demo-Run
#
# Ziel-Dir überschreibbar via XBUDDY_DEMO_DIR.

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$_HERE/../.." && pwd)"
DEMO_DIR="${XBUDDY_DEMO_DIR:-$REPO/xbuddy-data-demo}"

# Kuratierte Seed → Ziel-Map: der Live-Dateiname weicht teils vom example-Namen
# ab (z. B. routine.example.json → routine_store.json). Nur DATEN-Seeds, die die
# Views populieren — Config (Ports/Origins) kommt aus den Code-Defaults/ENV.
SEED_KEYS=(
  "instanzen.example.json"
  "familie/familie.example.json"
  "plan/plan.example.json"
  "essen/gerichte.example.json"
  "essen/wuensche.example.json"
  "routine/routine.example.json"
  "wetter/wetter.example.json"
  "panel/panels.example.json"
  "kibuddy/kibuddy.example.json"
  "hoerspiel/hoerspiel.example.json"
)
seed_target() {
  case "$1" in
    "instanzen.example.json")        echo "instanzen.json" ;;
    "familie/familie.example.json")  echo "familie/familie.json" ;;
    "plan/plan.example.json")        echo "plan/plan.json" ;;
    "essen/gerichte.example.json")   echo "essen/gerichte.json" ;;
    "essen/wuensche.example.json")   echo "essen/wuensche.json" ;;
    "routine/routine.example.json")  echo "routine/routine_store.json" ;;
    "wetter/wetter.example.json")    echo "wetter/wetter.json" ;;
    "panel/panels.example.json")     echo "panel/panels.json" ;;
    "kibuddy/kibuddy.example.json")  echo "kibuddy/kibuddy.json" ;;
    "hoerspiel/hoerspiel.example.json") echo "hoerspiel/hoerspiel.json" ;;
  esac
}

echo "[demo] Ziel-Dir (Wegwerf, gitignored): $DEMO_DIR"
rm -rf "$DEMO_DIR"
n=0
for seed in "${SEED_KEYS[@]}"; do
  src="$REPO/$seed"
  [ -f "$src" ] || { echo "[demo] WARN: Seed fehlt: $seed" >&2; continue; }
  target="$DEMO_DIR/$(seed_target "$seed")"
  mkdir -p "$(dirname "$target")"
  cp "$src" "$target"
  n=$((n + 1))
done
echo "[demo] $n Seeds ins Wegwerf-Dir kopiert (Familie Sonntag)."

if [ "${1:-}" = "--env" ]; then
  cat <<ENV

# ── Demo-Run: diese ENV-Exports zeigen die Services auf das Wegwerf-Dir ──
# (Auf ALTERNATIVEN Ports starten, damit die Live-Services unberührt bleiben —
#  siehe README. Config-Datei-Pfade sind demo-spezifisch, Live bleibt getrennt.)
export INSTANZEN_CONFIG_FILE="$DEMO_DIR/instanzen.json"
export FAMILIE_STORE_FILE="$DEMO_DIR/familie/familie.json"
export PLAN_CONFIG_FILE="$DEMO_DIR/plan/plan.json"
export ROUTINE_STORE_FILE="$DEMO_DIR/routine/routine_store.json"
export WETTER_CONFIG_FILE="$DEMO_DIR/wetter/wetter.json"
export ESSEN_DATA_DIR="$DEMO_DIR/essen"
export PANEL_REGISTRY_FILE="$DEMO_DIR/panel/panels.json"
export KIBUDDY_CONFIG_FILE="$DEMO_DIR/kibuddy/kibuddy.json"
export HOERSPIEL_DATA_ROOT="$DEMO_DIR/hoerspiel"
ENV
fi

echo "[demo] fertig. Getrackte Dateien unberührt (git status bleibt sauber)."
