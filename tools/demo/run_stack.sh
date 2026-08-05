#!/usr/bin/env bash
# Demo-Stack (#1767): git clone → EIN Befehl → alle reichen Views laufen lokal
# same-origin, OHNE Pi/Server-Deploy und OHNE Live-Familien-Daten anzufassen.
#
# Startet die Display-Services auf ALT-PORTS (≥ 8100, strikt außerhalb des
# Live-Bereichs 5000–5099 — #1767-Befund 5: routine-Demo lief versehentlich auf
# 5050=Live → echte Daten im Screenshot) + einen Mini-Reverse-Proxy (proxy.py),
# der die nginx-Pfad-Präfixe same-origin bündelt. Sauberes Teardown per trap.
#
# Reines Demo-Tooling (Zwei-Wege-Tür): rückbaubar durch Löschen von tools/demo/.
#
#   tools/demo/run_stack.sh            # seedet + startet, Ctrl-C beendet alles
#   DEMO_PROXY_PORT=8199 …             # überschreibbar
#
set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$_HERE/../.." && pwd)"
DEMO_DIR="${XBUDDY_DEMO_DIR:-$REPO/xbuddy-data-demo}"
PY="${PYTHON:-python3}"

# ── Alt-Port-Belegung (ALLE ≥ 8100) ──────────────────────────────────────────
PROXY_PORT="${DEMO_PROXY_PORT:-8199}"
declare -A PORT=(
  [familie]=8110 [plan]=8120 [wetter]=8130 [seiten]=8140
  [routine]=8150 [essen]=8152 [hoerspiel]=8153
)

# ── Sicherheits-Sperre: NIE einen Live-Port (5000–5099) belegen (#1767-Befund 5).
guard_port() {
  local p="$1"
  if [ "$p" -ge 5000 ] && [ "$p" -le 5099 ]; then
    echo "[demo] ABBRUCH: Port $p liegt im Live-Bereich 5000–5099 — Demo darf" \
         "keine Live-Services überfahren." >&2
    exit 3
  fi
}
for p in "$PROXY_PORT" "${PORT[@]}"; do guard_port "$p"; done

# ── Seed (Wegwerf-Dir, gitignored) ───────────────────────────────────────────
echo "[demo] seede Familie Sonntag …"
XBUDDY_DEMO_DIR="$DEMO_DIR" bash "$_HERE/seed_demo.sh" >/dev/null

# Icon-Root: das gebündelte Subset (#1767) — seiten liefert /display/_shared/icons.
ICON_ROOT="$_HERE/assets/icons"

FAM_ORIGIN="http://127.0.0.1:${PORT[familie]}"

PIDS=()
teardown() {
  echo "[demo] Teardown — beende ${#PIDS[@]} Prozesse …"
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap teardown EXIT INT TERM

start() {  # start <name> <modul> <env-assignments…>
  local name="$1" modul="$2"; shift 2
  echo "[demo] starte $name auf :${PORT[$name]}"
  ( cd "$REPO" && env "$@" "$PY" -m "$modul" --host 127.0.0.1 --port "${PORT[$name]}" \
      >"$DEMO_DIR/$name.log" 2>&1 ) &
  PIDS+=("$!")
}

start familie   familie.main   FAMILIE_REGISTRY="$DEMO_DIR/familie/familie.json"
start seiten    seiten.main    ICON_ROOT="$ICON_ROOT" SEITEN_FAMILIE_ORIGIN="$FAM_ORIGIN"
start plan      plan.main      PLAN_CONFIG_FILE="$DEMO_DIR/plan/plan.json" \
                               PLAN_FAMILIE_ORIGIN="$FAM_ORIGIN" \
                               PLAN_KALENDER_DEMO_FILE="$DEMO_DIR/plan/kalender-demo.json"
start routine   routine.main   ROUTINE_STORE_FILE="$DEMO_DIR/routine/routine_store.json" \
                               ROUTINE_FAMILIE_ORIGIN="$FAM_ORIGIN"
start wetter    wetter.main    WETTER_CONFIG_FILE="$DEMO_DIR/wetter/wetter.json" \
                               WETTER_FAMILIE_ORIGIN="$FAM_ORIGIN"
start essen     essen.main     ESSEN_DATA_DIR="$DEMO_DIR/essen" ESSEN_FAMILIE_ORIGIN="$FAM_ORIGIN"
start hoerspiel hoerspiel.main HOERSPIEL_DATA_ROOT="$DEMO_DIR/hoerspiel" HOERSPIEL_KIND_ID=mia

# ── Reverse-Proxy: nginx-Pfad-Präfixe same-origin über die Alt-Ports ──────────
ROUTES="/api/v1/familie/=${PORT[familie]}"
ROUTES+=";/display/plan/=${PORT[plan]};/api/v1/plan/=${PORT[plan]}"
ROUTES+=";/display/routine/=${PORT[routine]};/api/v1/routine/=${PORT[routine]}"
ROUTES+=";/display/wetter/=${PORT[wetter]};/api/v1/wetter/=${PORT[wetter]}"
ROUTES+=";/display/hoerspiel/=${PORT[hoerspiel]};/api/v1/hoerspiel/=${PORT[hoerspiel]}"
ROUTES+=";/api/v1/essen/=${PORT[essen]}"
ROUTES+=";/display/_shared/=${PORT[seiten]};/api/v1/icons/=${PORT[seiten]}"
ROUTES+=";/shell/=${PORT[seiten]};/seiten/=${PORT[seiten]};/controller/=${PORT[seiten]}"
ROUTES+=";*=${PORT[seiten]}"   # Default: seiten
echo "[demo] starte Reverse-Proxy auf :$PROXY_PORT"
( cd "$REPO" && PROXY_PORT="$PROXY_PORT" PROXY_ROUTES="$ROUTES" \
    "$PY" "$_HERE/proxy.py" >"$DEMO_DIR/proxy.log" 2>&1 ) &
PIDS+=("$!")

sleep 2
cat <<INFO

[demo] Stack läuft — Demo-Basis: http://127.0.0.1:$PROXY_PORT
  Kiosk-/Display-Views (Familie Sonntag, gefüllt, keine Live-Daten):
    /display/plan/woche            Wochenplan (Demo-Kalender)
    /display/hoerspiel/mia/alben   Hörspiel-Alben
    /display/routine/…             Routine
    /display/wetter/…              Wetter
  Eltern-Sicht — PWA-Mini-Apps (#1768, observe-Modus, ohne Cookie):
    /seiten/essen/einkauf/         Einkauf
    /seiten/plan/einstellungen/    Plan-Einstellungen
    /seiten/routine/anpassen       Routine-Anpassen
    /seiten/hoerspiel/mia/eltern   Hörspiel-Eltern
  Eltern-Chat — statische Demo-Seite (#1773, synthetisch, kein Server nötig):
    tools/demo/chat_transcript/eltern-chat-sonntag.html  (direkt im Browser öffnen)
  Screenshots: tools/demo/shoot.sh <pfad|datei.html>
  Beenden: Ctrl-C (Teardown räumt alle Prozesse + Ports).
INFO

wait
