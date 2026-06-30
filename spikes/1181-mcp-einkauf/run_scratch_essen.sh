#!/usr/bin/env bash
# MCP-Spike #1181 — isolierte Scratch-essen-Instanz (stop_rule prod_data).
#
# Startet den realen Essen-Buddy (essen/main.py) auf Port 5152 mit ALLEN
# Datei-Pfaden in scratch-data/ umgebogen (ESSEN_*_FILE). So fasst der Spike-
# Schreib-Pfad NIE die Produktiv-Instanz (Port 5052) und NIE deren Daten an.
# Port 5152 ist bewusst != 5052/5052-Bereich.
#
# Aufruf:   ./run_scratch_essen.sh
# Stoppen:  Ctrl-C  (oder den geloggten PID killen)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SCRATCH="$HERE/scratch-data"
PORT="${SCRATCH_ESSEN_PORT:-5152}"

if [ "$PORT" = "5052" ]; then
  echo "ABBRUCH: Port 5052 ist Produktiv (PORT-2). Scratch MUSS != 5052." >&2
  exit 1
fi

mkdir -p "$SCRATCH"

# Alle Domänendaten-Pfade (essen/config.py: ENV_*_FILE) in scratch-data/ biegen.
export ESSEN_WUENSCHE_FILE="$SCRATCH/wuensche.json"
export ESSEN_EINKAUFSLISTE_FILE="$SCRATCH/einkaufsliste.json"
export ESSEN_ZAEHLER_FILE="$SCRATCH/zaehler.json"
export ESSEN_GERICHTE_FILE="$SCRATCH/gerichte.json"
export ESSEN_KATALOG_FILE="$SCRATCH/katalog.json"
export ESSEN_FOTO_OVERRIDES_FILE="$SCRATCH/foto_overrides.json"
export ESSEN_FOTOS_VERZEICHNIS="$SCRATCH/fotos"

echo "Scratch-essen: Port $PORT, Daten in $SCRATCH (NIE 5052/Produktiv)"
cd "$REPO_ROOT"
exec python3 -m essen.main --host 127.0.0.1 --port "$PORT"
