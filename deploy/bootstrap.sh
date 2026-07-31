#!/usr/bin/env bash
# bootstrap.sh — XBuddy Host-Profil-Substitution für systemd-Units + Venv (#1667, löst #178b).
#
# Zweck: Einen frischen Pi (oder eine neue Familie-Instanz) aufsetzen, indem
# die 8 __XBUDDY_*__-Host-Platzhalter aus einem Host-Profil in alle
# systemd-Unit-Vorlagen substituiert und das Python-Venv eingerichtet wird.
#
# Was dieses Skript NICHT macht (harte Grenzen, RATIFIZIERT 2026-07-31):
#   - nginx/xbuddy-origin.conf NIEMALS anfassen (T966-Vorfall, STOP-DEPLOY-Warnung).
#     nginx-Conf + FQDN-Fill bleiben der dokumentierte manuelle sed-Schritt.
#   - KEINE neue Kind-Instanz erzeugen (RAT-17). Port/kind_id/Datenpfad sind
#     handverdrahtet im Unit-Körper — der Bootstrap substituiert nur Host-Werte.
#   - NICHTS berechnen (INST-3-Guard). Jeder Wert kommt 1:1 aus dem Host-Profil.
#
# Aufruf:
#   bash deploy/bootstrap.sh --profile deploy/host-profile.env
#   bash deploy/bootstrap.sh --profile deploy/host-profile.env --dry-run
#   bash deploy/bootstrap.sh --profile deploy/host-profile.env --setup-venv
#
# --dry-run:    Substituierte Units nach /tmp schreiben statt /etc/systemd/system.
#               Keine Live-Änderung. Diff zeigt nur ersetzte Platzhalter.
# --setup-venv: Venv anlegen (falls nicht vorhanden) und Repo-Abhängigkeiten
#               aus pyproject.toml installieren (RAT-33 Option A, #1534).
#               Im --dry-run-Modus wird nur der venv-Pfad geprüft, nicht angelegt.
#
# Idempotenz + Backup-Rollback: Vorbild deploy/nginx/install.sh.
#   - Backup der bestehenden Unit-Datei vor Überschreiben (<ziel>.bak).
#   - Nur backuppen wenn Ziel existiert (kein leeres .bak bei Erst-Installation).
#   - set -euo pipefail: jeder Fehler stoppt das Skript.

set -euo pipefail

# ---------------------------------------------------------------------------
# Unit-Quellen-Map: systemd-Name → Repo-Pfad zur Vorlage (relativ zu SCRIPT_DIR/..)
# Vollständige Liste (README-Schleife + 3 fehlende Units hoerspiel/hoerspiel-neko/kibuddy
# + hoerspiel-niclas).
# ---------------------------------------------------------------------------
declare -A SVC_SRC=(
    [xbuddy-plan]=plan/plan.service
    [xbuddy-wetter]=wetter/wetter.service
    [xbuddy-routine]=routine/routine.service
    [xbuddy-photo]=photo/photo.service
    [xbuddy-familie]=familie/familie.service
    [xbuddy-seiten]=seiten/seiten.service
    [xbuddy-panel]=panel/panel.service
    [xbuddy-essen]=essen/essen.service
    [xbuddy-eltern-chat]=eltern-chat/eltern-chat.service
    [xbuddy-hoerspiel]=hoerspiel/hoerspiel.service
    [xbuddy-hoerspiel-neko]=hoerspiel/hoerspiel-neko.service
    [xbuddy-hoerspiel-niclas]=hoerspiel/hoerspiel-niclas.service
    [xbuddy-kibuddy]=kibuddy/kibuddy.service
)

# Ziel-Verzeichnis für systemd-Units (überschreibbar per ENV für Tests).
SYSTEMD_DEST_DIR="${XBUDDY_SYSTEMD_DEST_DIR:-/etc/systemd/system}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { printf '[bootstrap.sh] %s\n' "$*"; }
die()  { printf '[bootstrap.sh] FEHLER: %s\n' "$*" >&2; exit 1; }
info() { printf '[bootstrap.sh] INFO:   %s\n' "$*"; }

usage() {
    cat >&2 <<EOF
Aufruf: $0 --profile <profil-datei> [--dry-run] [--setup-venv]

  --profile <datei>  Host-Profil mit den 8 XBUDDY_*-Variablen (Pflicht).
                     Beispiel: deploy/host-profile.example.env
  --dry-run          Substituierte Units nach /tmp schreiben statt nach
                     ${SYSTEMD_DEST_DIR}. Keine Live-Änderung.
  --setup-venv       Venv anlegen/aktualisieren (pip install aus pyproject.toml).
                     Im --dry-run-Modus wird nur der Venv-Pfad geprüft.
EOF
    exit 1
}

# ---------------------------------------------------------------------------
# Argument-Parsing
# ---------------------------------------------------------------------------
PROFILE_FILE=""
DRY_RUN=0
SETUP_VENV=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)
            [[ $# -ge 2 ]] || die "--profile braucht einen Datei-Pfad als Argument."
            PROFILE_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --setup-venv)
            SETUP_VENV=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            die "Unbekanntes Argument: $1 — $(usage 2>&1 | head -1)"
            ;;
    esac
done

[[ -n "${PROFILE_FILE}" ]] || { log "Kein --profile angegeben."; usage; }

# ---------------------------------------------------------------------------
# Pfade ableiten (relativ zum Skript)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Host-Profil laden
# ---------------------------------------------------------------------------
[[ -r "${PROFILE_FILE}" ]] || die "Profil-Datei nicht lesbar: ${PROFILE_FILE}"
log "Lade Host-Profil: ${PROFILE_FILE}"
# shellcheck source=/dev/null
source "${PROFILE_FILE}"

# ---------------------------------------------------------------------------
# Vollständigkeits-Prüfung: alle 8 Variablen müssen gesetzt und nicht leer sein
# ---------------------------------------------------------------------------
REQUIRED_VARS=(
    XBUDDY_USER
    XBUDDY_HOME
    XBUDDY_REPO
    XBUDDY_PYTHON
    XBUDDY_DATA
    XBUDDY_DISPLAY_ORIGIN_HEIM
    XBUDDY_DISPLAY_ORIGIN_TAILSCALE
    XBUDDY_DISPLAY_ORIGIN_FUNNEL
)
for var in "${REQUIRED_VARS[@]}"; do
    [[ -n "${!var:-}" ]] || die "Profil-Variable nicht gesetzt oder leer: ${var}  (Beispiel: deploy/host-profile.example.env)"
done
log "Alle 8 Host-Profil-Variablen vorhanden."

# ---------------------------------------------------------------------------
# Dry-Run-Banner
# ---------------------------------------------------------------------------
if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "DRY-RUN-Modus aktiv — Units werden nach /tmp geschrieben, KEINE Live-Änderung."
    EFFECTIVE_DEST="/tmp/bootstrap-dry-run-$$"
    mkdir -p "${EFFECTIVE_DEST}"
else
    EFFECTIVE_DEST="${SYSTEMD_DEST_DIR}"
fi

# ---------------------------------------------------------------------------
# sed-Ausdruck zusammenbauen (1:1 aus Profil, KEINE Berechnung)
# ---------------------------------------------------------------------------
SED_EXPR=(
    -e "s|__XBUDDY_USER__|${XBUDDY_USER}|g"
    -e "s|__XBUDDY_HOME__|${XBUDDY_HOME}|g"
    -e "s|__XBUDDY_REPO__|${XBUDDY_REPO}|g"
    -e "s|__XBUDDY_PYTHON__|${XBUDDY_PYTHON}|g"
    -e "s|__XBUDDY_DATA__|${XBUDDY_DATA}|g"
    -e "s|__XBUDDY_DISPLAY_ORIGIN_HEIM__|${XBUDDY_DISPLAY_ORIGIN_HEIM}|g"
    -e "s|__XBUDDY_DISPLAY_ORIGIN_TAILSCALE__|${XBUDDY_DISPLAY_ORIGIN_TAILSCALE}|g"
    -e "s|__XBUDDY_DISPLAY_ORIGIN_FUNNEL__|${XBUDDY_DISPLAY_ORIGIN_FUNNEL}|g"
)

# ---------------------------------------------------------------------------
# Unit-Substitution
# ---------------------------------------------------------------------------
log "Starte Unit-Substitution (${#SVC_SRC[@]} Units) → ${EFFECTIVE_DEST}"

for svc in "${!SVC_SRC[@]}"; do
    src_rel="${SVC_SRC[${svc}]}"
    src_abs="${REPO_ROOT}/${src_rel}"
    dest_file="${EFFECTIVE_DEST}/${svc}.service"
    backup_file="${dest_file}.bak"

    [[ -r "${src_abs}" ]] || die "Vorlage nicht lesbar: ${src_abs}"

    # Backup — nur wenn Ziel schon existiert (Idempotenz, kein leeres .bak)
    if [[ -e "${dest_file}" ]]; then
        if [[ "${DRY_RUN}" -eq 0 ]]; then
            log "  Backup: ${dest_file} → ${backup_file}"
            sudo cp -p "${dest_file}" "${backup_file}"
        fi
    fi

    # Substituieren + schreiben
    if [[ "${DRY_RUN}" -eq 1 ]]; then
        sed "${SED_EXPR[@]}" "${src_abs}" > "${dest_file}"
        info "  [dry-run] ${svc}.service → ${dest_file}"
    else
        sudo sed "${SED_EXPR[@]}" "${src_abs}" \
            | sudo tee "${dest_file}" >/dev/null
        log "  ${svc}.service → ${dest_file}"
    fi
done

log "Unit-Substitution abgeschlossen."

# ---------------------------------------------------------------------------
# Venv-Setup (optional, --setup-venv)
# ---------------------------------------------------------------------------
if [[ "${SETUP_VENV}" -eq 1 ]]; then
    VENV_DIR="$(dirname "${XBUDDY_PYTHON}")"
    # XBUDDY_PYTHON zeigt auf <venv>/bin/python — Venv-Root ist zwei Ebenen höher
    VENV_ROOT="$(cd "${VENV_DIR}/../.." 2>/dev/null && pwd || echo "")"
    [[ -n "${VENV_ROOT}" ]] || die "Venv-Root konnte nicht aus XBUDDY_PYTHON abgeleitet werden: ${XBUDDY_PYTHON}"

    PYPROJECT="${REPO_ROOT}/pyproject.toml"
    [[ -r "${PYPROJECT}" ]] || die "pyproject.toml nicht gefunden: ${PYPROJECT} — ist XBUDDY_REPO korrekt?"

    SYSTEM_PYTHON="${SYSTEM_PYTHON:-python3}"
    command -v "${SYSTEM_PYTHON}" >/dev/null 2>&1 \
        || die "System-Python nicht gefunden: ${SYSTEM_PYTHON}"

    if [[ "${DRY_RUN}" -eq 1 ]]; then
        info "[dry-run] Venv-Pfad: ${VENV_ROOT}"
        info "[dry-run] pyproject.toml: ${PYPROJECT}"
        info "[dry-run] Venv vorhanden: $([[ -d ${VENV_ROOT} ]] && echo ja || echo nein)"
    else
        if [[ ! -d "${VENV_ROOT}" ]]; then
            log "Venv anlegen: ${VENV_ROOT}"
            "${SYSTEM_PYTHON}" -m venv "${VENV_ROOT}"
        else
            log "Venv bereits vorhanden: ${VENV_ROOT}"
        fi

        log "Abhängigkeiten installieren aus pyproject.toml (RAT-33 Option A) ..."
        "${XBUDDY_PYTHON%/bin/python}/bin/pip" install --quiet "${REPO_ROOT}"
        log "pip install abgeschlossen."
    fi
fi

# ---------------------------------------------------------------------------
# systemd daemon-reload (nur im Live-Modus)
# ---------------------------------------------------------------------------
if [[ "${DRY_RUN}" -eq 0 ]]; then
    log "systemctl daemon-reload ..."
    sudo systemctl daemon-reload
    log "Fertig."
    log ""
    log "Nächste Schritte (manuell):"
    log "  sudo systemctl enable --now xbuddy-plan.service"
    log "  sudo systemctl enable --now xbuddy-wetter.service"
    log "  sudo systemctl enable --now xbuddy-routine.service"
    log "  sudo systemctl enable --now xbuddy-photo.service"
    log "  sudo systemctl enable --now xbuddy-familie.service"
    log "  sudo systemctl enable --now xbuddy-seiten.service"
    log "  sudo systemctl enable --now xbuddy-panel.service"
    log "  sudo systemctl enable --now xbuddy-essen.service"
    log "  sudo systemctl enable --now xbuddy-eltern-chat.service"
    log "  sudo systemctl enable --now xbuddy-hoerspiel.service"
    log "  sudo systemctl enable --now xbuddy-hoerspiel-neko.service"
    log "  sudo systemctl enable --now xbuddy-hoerspiel-niclas.service"
    log "  sudo systemctl enable --now xbuddy-kibuddy.service"
    log ""
    log "nginx-Conf + FQDN-Fill: manueller sed-Schritt (deploy/nginx/README.md) —"
    log "dieser Bootstrap fasst nginx NICHT an (T966-Vorfall, STOP-DEPLOY-Warnung)."
else
    log "Dry-Run abgeschlossen. Substituierte Units liegen unter: ${EFFECTIVE_DEST}"
    log "Diff-Check (zeigt nur ersetzte Platzhalter-Zeilen):"
    for svc in "${!SVC_SRC[@]}"; do
        src_rel="${SVC_SRC[${svc}]}"
        src_abs="${REPO_ROOT}/${src_rel}"
        dest_file="${EFFECTIVE_DEST}/${svc}.service"
        if ! diff -u "${src_abs}" "${dest_file}" >/dev/null 2>&1; then
            log "  diff ${svc}.service:"
            diff -u "${src_abs}" "${dest_file}" | grep -E "^[+-]" | grep -v "^[+-]{3}" || true
        fi
    done
fi
