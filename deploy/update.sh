#!/usr/bin/env bash
# deploy/update.sh — XBuddy Deploy-Regelkreis, Stufe 1 (SVC-6, T1311/#1311).
#
# Ablauf des Vollaufs (ohne Argumente):
#   pull --ff-only origin main
#     → Diff (git diff --name-only <alt> <neu>)
#     → betroffene Services ableiten: geteilter Mapper
#       ~/.claude/hooks/restart_pending_log.py:services_for_paths PLUS
#       Shared-Pfad-Fan-out (eine Änderung unter tools/ oder conventions/
#       trifft ALLE Services — geteilter Code / geteilte Konvention, SVC-6)
#     → deploy/version schreiben (die Datei, die /version jedes Service liest)
#     → nur die betroffenen Services `systemctl restart`
#     → verifizieren: is-active == active  UND  Start-TS > Merge-TS  UND
#       /healthz == 200 (Falsch-grün-Schutz, SVC-6)
#     → restart_done:true in restart_pending.jsonl zurückschreiben.
#
# NICHT Teil von Stufe 1 (ausdrücklich): Release-Worktree (RAT-14-b2),
# Rollback, Alerts (Stufe 2) und Runner-Health (#1113, eigene Autonomie-Zeile).
# nginx (deploy/nginx/*) ist ein paralleler Track (#1347) — dieses Skript
# restartet ausschließlich `xbuddy-*`-Services, kein nginx-Reload.
#
# Test-Nähte ohne sudo/git/systemctl (deploy/tests/):
#   update.sh --derive PATH...     → druckt die abgeleiteten Service-Namen
#   update.sh --write-version SHA  → schreibt nur die deploy/version-Datei
#   update.sh --mark-done RANGE    → markiert restart_pending.jsonl-Eintrag
#   update.sh --sync-deps          → installiert pyproject-Deps in den Service-venv
# Der Live-Restart läuft im Orchestrator-Deploy (sudo/systemctl nötig).
#
# Dependency-Sync (RAT-33 Option A, #1534): VOR den Restarts installiert der
# Vollauf [project.dependencies] aus pyproject.toml (EIN Dependency-SSoT) in den
# Service-venv, damit neu gestartete Services neue/geänderte Deps direkt sehen —
# statt Hand-Pflege des venv (die #1515-Klasse: litellm fehlte). Idempotent: pip
# ist bei unverändertem pyproject ein No-Op-Roundtrip.
#
# Konfigurierbar über ENV (Test + Instanz):
#   XBUDDY_REPO           Repo-Wurzel (Default: das Elternverzeichnis von deploy/)
#   XBUDDY_DATA_DIR       Datenwurzel für deploy/version (Default /home/buddy/xbuddy-data)
#   RESTART_PENDING_LOG   JSONL des restart_pending-Hooks
#                         (Default /home/buddy/.claude/logs/restart_pending.jsonl)
#   XBUDDY_VENV           Service-venv für den Dep-Sync (Default /home/buddy/apps/venv).
#                         "none" überspringt den Sync (Test-Naht ohne pip/Netz).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${XBUDDY_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
DATA_DIR="${XBUDDY_DATA_DIR:-/home/buddy/xbuddy-data}"
RESTART_LOG="${RESTART_PENDING_LOG:-/home/buddy/.claude/logs/restart_pending.jsonl}"
VENV="${XBUDDY_VENV:-/home/buddy/apps/venv}"

# ---------------------------------------------------------------------------
# Service-Ableitung: geteilter Mapper + Shared-Pfad-Fan-out.
# args: geänderte Pfade. stdout: Service-Namen (xbuddy-*), sortiert-unique,
# einer pro Zeile. (Pfade kommen als argv — der Heredoc belegt stdin.)
# ---------------------------------------------------------------------------
derive_services() {
    XBUDDY_REPO="$REPO" python3 - "$@" <<'PY'
import os
import re
import sys

repo = os.environ["XBUDDY_REPO"]
sys.path.insert(0, repo)
from methode.hooks.restart_pending_log import load_mapping, services_for_paths

paths = [p.strip() for p in sys.argv[1:] if p.strip()]
mapping = load_mapping()


def svc_names(cmd):
    # Ein Mapping-Kommando kann mehrere Restarts enthalten (hoerspiel: Mia
    # UND Finn in einem `&&`-Kommando) — alle einsammeln.
    return re.findall(r"systemctl\s+restart\s+(xbuddy-\S+)", cmd)


all_services = {n for _p, cmd in mapping for n in svc_names(cmd)}

# Shared-Pfad-Fan-out (SVC-6): tools/ (inkl. tools/llm/) und conventions/
# treffen ALLE Services. deploy/nginx bleibt außen vor (paralleler Track).
shared_touched = any(p.startswith(("tools/", "conventions/")) for p in paths)

services = set()
for cmd in services_for_paths(paths, mapping):
    services.update(svc_names(cmd))
if shared_touched:
    services |= all_services

for n in sorted(services):
    print(n)
PY
}

# deploy/version schreiben (SVC-6). Jeder Service liest diese Datei für /version.
write_version_file() {
    local sha="$1"
    local dir="$DATA_DIR/deploy"
    if ! mkdir -p "$dir"; then
        echo "update: konnte $dir nicht anlegen" >&2
        return 1
    fi
    printf '%s\n' "$sha" >"$dir/version"
    echo "update: deploy/version = $sha"
}

# Dependency-Sync in den Service-venv aus pyproject.toml (RAT-33 Option A,
# #1534). EIN Dependency-SSoT: `pip install .` zieht [project.dependencies] und
# ergänzt fehlende/geänderte Pakete idempotent. `pip` selbst baut KEIN xbuddy-
# Paket in den Import-Pfad ein (pyproject: py-modules = [] / kein Distributions-
# Paket); die Services laufen weiter aus dem Checkout. Rückgabe 0 = ok/übersprungen.
sync_deps() {
    if [ -z "$VENV" ] || [ "$VENV" = "none" ]; then
        echo "update: Dep-Sync übersprungen (XBUDDY_VENV=none)"
        return 0
    fi
    local pip="$VENV/bin/pip"
    if [ ! -x "$pip" ]; then
        echo "update: Dep-Sync übersprungen — kein pip unter $pip" >&2
        return 0
    fi
    echo "update: Dep-Sync aus pyproject.toml → $VENV"
    if "$pip" install --quiet "$REPO"; then
        echo "update: Dep-Sync ok"
        return 0
    fi
    echo "    ✗ Dep-Sync (pip install) fehlgeschlagen — Deps evtl. petraltet" >&2
    return 1
}

# Loopback-Port eines Service aus conventions/ports.md PORT-2 (SSoT, PORT-1).
# Leer, wenn der Service NICHT in der PORT-2-Tabelle steht (portlos ODER unbekannt).
service_port() {
    local svc="$1"
    awk -F'|' -v s="$svc" '
        { gsub(/[[:space:]]/, "", $2); gsub(/[[:space:]]/, "", $4) }
        $4 == s && $2 ~ /^[0-9]+$/ { print $2; exit }
    ' "$REPO/conventions/ports.md"
}

# Services ohne HTTP-Port (SVC-1/PORT-2, deploy/systemd/README.md): eltern-chat
# geht nur RAUS zu Telegram, bindet keinen Port. Für diese ist ein leerer
# service_port ERWARTET — nicht zu verwechseln mit einem Tippfehler/Drift.
is_known_portless() {
    case "$1" in
        xbuddy-eltern-chat) return 0 ;;
        *) return 1 ;;
    esac
}

# Klassifiziert einen Service für den /healthz-Verify (Falsch-grün-Schutz, SVC-6):
#   PORT:<n> — HTTP-Port in PORT-2 → /healthz MUSS geprüft werden (rc 0)
#   PORTLESS — bekannt portlos (eltern-chat) → /healthz zu Recht übersprungen (rc 0)
#   UNKNOWN  — leerer Port bei NICHT-portlosem Service → Drift/Tippfehler (rc 1)
# Trennt so den früher stumm übersprungenen Fall (leerer Port ⇒ Falsch-grün)
# vom legitim portlosen Fall.
port_class() {
    local svc="$1" port
    port="$(service_port "$svc")"
    if [ -n "$port" ]; then
        printf 'PORT:%s\n' "$port"
        return 0
    fi
    if is_known_portless "$svc"; then
        echo "PORTLESS"
        return 0
    fi
    echo "UNKNOWN"
    return 1
}

# Start-Zeitpunkt eines Service als Unix-Epoch (ActiveEnterTimestamp).
service_start_epoch() {
    local svc="$1" ts
    ts="$(systemctl show "$svc" -p ActiveEnterTimestamp --value 2>/dev/null || true)"
    [ -z "$ts" ] && return 0
    date -d "$ts" +%s 2>/dev/null || true
}

# HTTP-Code von /healthz auf einem Loopback-Port ("000" wenn nicht erreichbar).
healthz_code() {
    local port="$1"
    curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
        "http://127.0.0.1:${port}/healthz" 2>/dev/null || echo "000"
}

# Falsch-grün-Schutz (SVC-6): is-active UND Start-TS>Merge-TS UND /healthz==200.
# Rückgabe 0 = ok, 1 = Verifikation fehlgeschlagen.
verify_service() {
    local svc="$1" merge_ts="$2" start_ts port code

    if [ "$(systemctl is-active "$svc" 2>/dev/null || true)" != "active" ]; then
        echo "    ✗ $svc: is-active != active"
        return 1
    fi

    start_ts="$(service_start_epoch "$svc")"
    if [ -z "$start_ts" ] || [ "$start_ts" -lt "$merge_ts" ]; then
        echo "    ✗ $svc: Start-TS (${start_ts:-?}) nicht nach Merge-TS ($merge_ts) — nicht neu gestartet?"
        return 1
    fi

    local class
    class="$(port_class "$svc")"
    case "$class" in
        PORT:*)
            port="${class#PORT:}"
            code="$(healthz_code "$port")"
            case "$code" in
                200) ;;
                404)
                    # Prozess erreichbar, aber SVC-6-/healthz noch nicht ausgerollt.
                    echo "    ⚠ $svc: /healthz fehlt (HTTP 404, SVC-6-Rollout offen) — Prozess erreichbar"
                    ;;
                000 | "")
                    echo "    ✗ $svc: /healthz nicht erreichbar (Prozess tot / bindet nicht?)"
                    return 1
                    ;;
                *)
                    echo "    ✗ $svc: /healthz HTTP $code"
                    return 1
                    ;;
            esac
            ;;
        PORTLESS)
            # eltern-chat u. Ä.: kein HTTP-Port (PORT-2) — /healthz zu Recht übersprungen.
            echo "    ℹ $svc: kein HTTP-Port (PORT-2) — /healthz-Verify übersprungen"
            ;;
        UNKNOWN)
            # Früher stiller Skip → Falsch-grün. Jetzt harter Fehler: der Service
            # steht nicht in ports.md und ist nicht bekannt-portlos (Drift/Tippfehler).
            echo "    ✗ $svc: kein Port in ports.md (PORT-2) und nicht bekannt-portlos — Drift/Tippfehler? /healthz-Verify nicht möglich"
            return 1
            ;;
    esac
    return 0
}

# restart_done:true in den passenden restart_pending.jsonl-Eintrag schreiben.
mark_restart_done() {
    local commit_range="$1"
    [ -f "$RESTART_LOG" ] || return 0
    COMMIT_RANGE="$commit_range" RESTART_LOG="$RESTART_LOG" python3 - <<'PY'
import json
import os

log = os.environ["RESTART_LOG"]
rng = os.environ["COMMIT_RANGE"]
want_post = rng.split("..")[-1]

out = []
changed = False
try:
    with open(log, encoding="utf-8") as f:
        lines = f.readlines()
except OSError:
    raise SystemExit(0)

for line in lines:
    line = line.strip()
    if not line:
        continue
    try:
        entry = json.loads(line)
    except ValueError:
        out.append(line)
        continue
    cr = entry.get("commit_range", "") or ""
    entry_post = cr.split("..")[-1]
    # Der Hook schreibt evtl. gekürzte SHAs (7-40 Zeichen) — Präfix-Match beidseitig.
    match = bool(entry_post) and (
        want_post.startswith(entry_post) or entry_post.startswith(want_post) or cr == rng
    )
    if match and not entry.get("restart_done"):
        entry["restart_done"] = True
        changed = True
    out.append(json.dumps(entry, ensure_ascii=False))

if changed:
    with open(log, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("update: restart_done:true gesetzt für %s" % rng)
PY
}

# ---------------------------------------------------------------------------
# Vollauf.
# ---------------------------------------------------------------------------
run_full() {
    local pre post merge_ts rc=0
    local -a services=()

    pre="$(git -C "$REPO" rev-parse HEAD)"
    git -C "$REPO" pull --ff-only origin main
    post="$(git -C "$REPO" rev-parse HEAD)"

    if [ "$pre" = "$post" ]; then
        echo "update: nichts Neues ($post) — kein Restart."
        return 0
    fi

    merge_ts="$(date +%s)"
    local -a changed_arr=()
    mapfile -t changed_arr < <(git -C "$REPO" diff --name-only "$pre" "$post")
    echo "update: $pre..$post"
    echo "geänderte Pfade:"
    printf '  %s\n' "${changed_arr[@]}"

    # deploy/version VOR den Restarts schreiben, damit die neu gestarteten
    # Services beim Boot direkt den neuen SHA über /version melden.
    write_version_file "$post"

    # Dependency-Sync aus pyproject VOR den Restarts (#1534): neu gestartete
    # Services sehen so neue/geänderte Deps. Ein Fehlschlag setzt rc, blockt aber
    # nicht die Restarts (bestehende Deps bleiben verfügbar; Verify meldet Bruch).
    if ! sync_deps; then
        rc=1
    fi

    mapfile -t services < <(derive_services "${changed_arr[@]}")
    if [ "${#services[@]}" -eq 0 ]; then
        echo "update: keine ratifizierten Service-Pfade betroffen — kein Restart."
        mark_restart_done "$pre..$post"
        return 0
    fi

    echo "Restart betroffener Services: ${services[*]}"
    for svc in "${services[@]}"; do
        if ! sudo systemctl restart "$svc"; then
            echo "    ✗ $svc: systemctl restart fehlgeschlagen"
            rc=1
            continue
        fi
        if verify_service "$svc" "$merge_ts"; then
            echo "    ✓ $svc"
        else
            rc=1
        fi
    done

    mark_restart_done "$pre..$post"

    if [ "$rc" -ne 0 ]; then
        echo "update: FERTIG MIT FEHLERN — Verifikation eines Service schlug fehl (journalctl prüfen)." >&2
    else
        echo "update: fertig, alle betroffenen Services verifiziert."
    fi
    return "$rc"
}

main() {
    case "${1:-}" in
        --derive)
            shift
            derive_services "$@"
            ;;
        --write-version)
            shift
            write_version_file "${1:?SHA fehlt}"
            ;;
        --mark-done)
            shift
            mark_restart_done "${1:?commit_range fehlt}"
            ;;
        --port-class)
            shift
            port_class "${1:?Service-Name fehlt}"
            ;;
        --sync-deps)
            sync_deps
            ;;
        "")
            run_full
            ;;
        *)
            echo "usage: update.sh [--derive PATH... | --write-version SHA | --mark-done RANGE | --port-class SVC | --sync-deps]" >&2
            exit 2
            ;;
    esac
}

main "$@"
