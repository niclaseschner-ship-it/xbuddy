#!/usr/bin/env bash
# Screenshot-Helper für den Demo-Stack (#1767): rendert eine View über den
# laufenden Demo-Proxy (run_stack.sh) headless und legt ein PNG ab.
#
#   tools/demo/run_stack.sh &                 # Stack starten
#   tools/demo/shoot.sh /display/plan/woche   # → xbuddy-data-demo/shots/plan-woche.png
#
# Auflösung: Default 1920×1080 (Kiosk). Die „richtige" native Display-Auflösung
# ist device-abhängig und wird mit #1594 (Design-Schicht device-agnostisch)
# koordiniert — hier überschreibbar via DEMO_SHOT_W / DEMO_SHOT_H.
#
set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$_HERE/../.." && pwd)"
DEMO_DIR="${XBUDDY_DEMO_DIR:-$REPO/xbuddy-data-demo}"
PROXY_PORT="${DEMO_PROXY_PORT:-8199}"
W="${DEMO_SHOT_W:-1920}"
H="${DEMO_SHOT_H:-1080}"

PFAD="${1:-/display/plan/woche}"
OUT_DIR="$DEMO_DIR/shots"
mkdir -p "$OUT_DIR"
# Lokale .html-Datei (z. B. das synthetische Eltern-Chat-Transcript, #1773) →
# file://-URL; sonst ein Proxy-Pfad über den laufenden Stack.
if [ -f "$PFAD" ] && [ "${PFAD##*.}" = "html" ]; then
  ABS="$(cd "$(dirname "$PFAD")" && pwd)/$(basename "$PFAD")"
  URL="file://$ABS"
  NAME="$(basename "$PFAD" .html)"
else
  URL="http://127.0.0.1:$PROXY_PORT$PFAD"
  NAME="$(echo "$PFAD" | sed -E 's#^/+##; s#/+$##; s#[/?=&]+#-#g')"
fi
[ -n "$NAME" ] || NAME="index"
OUT="$OUT_DIR/$NAME.png"

# Chromium finden (puppeteer/chromium-Pfad wie im Render-Gate, sonst PATH).
CHROME=""
for c in "${CHROMIUM:-}" chromium chromium-browser google-chrome-stable google-chrome; do
  [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && { CHROME="$c"; break; }
done
if [ -z "$CHROME" ]; then
  echo "[shoot] kein chromium gefunden — setze CHROMIUM=<pfad>." >&2
  exit 4
fi

echo "[shoot] $URL  →  $OUT  (${W}×${H})"
"$CHROME" --headless --no-sandbox --disable-gpu --hide-scrollbars \
  --window-size="${W},${H}" --screenshot="$OUT" \
  --virtual-time-budget=4000 "$URL" >/dev/null 2>&1 || true

if [ -s "$OUT" ]; then
  echo "[shoot] fertig: $OUT ($(wc -c <"$OUT") bytes)"
else
  echo "[shoot] FEHLER: kein Screenshot erzeugt (läuft der Stack? run_stack.sh)" >&2
  exit 5
fi
