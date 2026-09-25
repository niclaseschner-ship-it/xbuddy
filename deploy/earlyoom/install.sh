#!/usr/bin/env bash
# install.sh — versionierte earlyoom-Schutzliste auf die Pi rollen (#1800).
#
# Schmerz, der dieses Skript hervorgebracht hat: /etc/default/earlyoom lag bis
# #1800 ausschliesslich auf der Maschine, zuletzt von Hand am 2026-08-17 09:26
# geaendert. Ein Neuaufsetzen haette die Schutzliste nicht mitgebracht — und
# wer die Datei liest, konnte nicht sehen, warum sie so aussieht wie sie
# aussieht. Dieses Skript macht den Deploy-Schritt explizit, idempotent und
# mit Backup-Rollback, wenn earlyoom nach dem Neustart nicht sauber hochkommt
# (Vorbild: deploy/nginx/install.sh).
#
# Aufruf:
#   ./deploy/earlyoom/install.sh
#
# Verhalten:
#   1. Voraussetzungen pruefen (earlyoom-Paket vorhanden, Quell-Datei lesbar).
#   2. Diff Quelle <-> Ziel — identisch -> Exit 0 (nichts zu tun).
#   3. Backup der aktuellen Ziel-Datei (falls vorhanden) -> <ziel>.bak.
#   4. `sudo cp` Quelle -> Ziel.
#   5. `sudo systemctl restart earlyoom`.
#   6. Aktiv-Probe (`systemctl is-active`) — Fehlschlag -> Backup zurueckspielen
#      + erneut starten, Exit 1.
#   7. Erfolg melden.
#
# Familie-3-Probe: kein absoluter Host-Pfad. Quell-Pfad leitet sich aus der
# Skript-Position ab; Ziel-Pfad ist der Debian-Standard fuer earlyoom.

set -euo pipefail

# --- Pfade ableiten ----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_CONF="${SCRIPT_DIR}/earlyoom.default"

# Ziel-Pfad: earlyoom-Standard. Ueberschreibbar per ENV fuer Tests/Familie-3.
DEST_CONF="${XBUDDY_EARLYOOM_DEST:-/etc/default/earlyoom}"
BACKUP_CONF="${DEST_CONF}.bak"

# --- Helpers -----------------------------------------------------------------
log() { printf '[install.sh] %s\n' "$*"; }
die() { printf '[install.sh] FEHLER: %s\n' "$*" >&2; exit 1; }

# --- 1. Voraussetzungen ------------------------------------------------------
systemctl list-unit-files earlyoom.service >/dev/null 2>&1 \
    || die "earlyoom.service ist auf diesem Host nicht bekannt."
command -v sudo >/dev/null 2>&1 \
    || die "sudo nicht verfuegbar — dieses Skript braucht Root-Rechte fuer cp/restart."
[ -r "${SRC_CONF}" ] || die "Quell-Datei nicht lesbar: ${SRC_CONF}"

log "Quelle: ${SRC_CONF}"
log "Ziel:   ${DEST_CONF}"

# --- 2. Diff: identisch -> fertig --------------------------------------------
if [ -e "${DEST_CONF}" ] && sudo cmp -s "${SRC_CONF}" "${DEST_CONF}"; then
    log "Ziel ist bereits identisch mit Quelle — nichts zu tun."
    exit 0
fi

# --- 3. Backup ----------------------------------------------------------------
if [ -e "${DEST_CONF}" ]; then
    log "Backup: ${DEST_CONF} -> ${BACKUP_CONF}"
    sudo cp -p "${DEST_CONF}" "${BACKUP_CONF}"
    HAD_PREVIOUS=1
else
    log "Kein bestehendes Ziel — Erst-Installation, kein Backup noetig."
    HAD_PREVIOUS=0
fi

# --- 4. Kopieren --------------------------------------------------------------
log "Kopiere Quelle -> Ziel ..."
sudo cp "${SRC_CONF}" "${DEST_CONF}"

# --- 5. Neustart ---------------------------------------------------------------
# earlyoom hat keinen Reload/Validate-Modus (EnvironmentFile wird nur beim
# Start gelesen) — die Aktiv-Probe nach dem Neustart ist die Validierung.
log "earlyoom neu starten (sudo systemctl restart earlyoom) ..."
sudo systemctl restart earlyoom

# --- 6. Aktiv-Probe — bei Fehler: Backup zurueck -------------------------------
sleep 1
if ! systemctl is-active --quiet earlyoom; then
    log "earlyoom kam nach dem Neustart nicht aktiv hoch — rolle Ziel-Datei zurueck."
    if [ "${HAD_PREVIOUS}" -eq 1 ]; then
        sudo cp -p "${BACKUP_CONF}" "${DEST_CONF}"
        sudo systemctl restart earlyoom || true
        log "Backup wiederhergestellt: ${BACKUP_CONF} -> ${DEST_CONF}"
    else
        sudo rm -f "${DEST_CONF}"
        log "Kaputte Erst-Installation entfernt: ${DEST_CONF}"
    fi
    die "earlyoom nach dem Deploy nicht aktiv. Original-Stand wiederhergestellt. Bitte Quell-Datei pruefen."
fi

# --- 7. Erfolg -----------------------------------------------------------------
log "Fertig. Aktive Datei: ${DEST_CONF}"
log "Backup (vorheriger Stand): ${BACKUP_CONF}"
