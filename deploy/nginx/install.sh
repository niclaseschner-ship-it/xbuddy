#!/usr/bin/env bash
# install.sh — XBuddy nginx-Origin-Conf auf die Pi rollen (#164).
#
# Schmerz, der dieses Skript hervorgebracht hat (Session 2026-05-26, PR #149
# Router-Reload-Endpoint): die produktive nginx-Conf unter
# /etc/nginx/conf.d/xbuddy-origin.conf war eine Hand-Kopie der Repo-Version.
# Vergisst der Mensch den `sudo cp`, driftet Repo und Live auseinander —
# sicherheits-relevante Änderungen (Admin-Loopback-Schutz) wirken erst nach
# dem Deploy-Schritt. Dieses Skript macht den Schritt explizit, idempotent
# und mit Backup-Rollback bei nginx-Validierungs-Fehlern.
#
# Aufruf:
#   ./deploy/nginx/install.sh
#
# Verhalten:
#   1. Voraussetzungen prüfen (nginx vorhanden, Quell-Datei lesbar).
#   2. Diff Quelle ↔ Ziel — identisch → Exit 0 (nichts zu tun).
#   3. Backup der aktuellen Ziel-Datei (falls vorhanden) → <ziel>.bak.
#   4. `sudo cp` Quelle → Ziel.
#   5. `sudo nginx -t` — Fehlschlag → Backup zurückspielen, Exit 1.
#   6. `sudo systemctl reload nginx`.
#   7. Erfolg melden.
#
# Familie-3-Probe: Pfade sind nicht an `/home/buddy/...` gebunden. Quell-Pfad
# leitet sich aus der Skript-Position ab; Ziel-Pfad ist der nginx-Standard
# `/etc/nginx/conf.d/`.

set -euo pipefail

# --- Pfade ableiten ----------------------------------------------------------
# Quell-Pfad: relativ zum Skript (deploy/nginx/install.sh → deploy/nginx/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_CONF="${SCRIPT_DIR}/xbuddy-origin.conf"

# Ziel-Pfad: nginx-Standard-Drop-in. Überschreibbar per ENV für Tests/Familie-3.
DEST_CONF="${XBUDDY_NGINX_DEST:-/etc/nginx/conf.d/xbuddy-origin.conf}"
BACKUP_CONF="${DEST_CONF}.bak"

# --- Helpers -----------------------------------------------------------------
log() { printf '[install.sh] %s\n' "$*"; }
die() { printf '[install.sh] FEHLER: %s\n' "$*" >&2; exit 1; }

# --- 1. Voraussetzungen ------------------------------------------------------
command -v nginx >/dev/null 2>&1 || die "nginx ist nicht installiert oder nicht im PATH."
command -v sudo  >/dev/null 2>&1 || die "sudo nicht verfügbar — dieses Skript braucht Root-Rechte für cp/nginx -t/reload."
[ -r "${SRC_CONF}" ] || die "Quell-Datei nicht lesbar: ${SRC_CONF}"

log "Quelle: ${SRC_CONF}"
log "Ziel:   ${DEST_CONF}"

# --- 2. Diff: identisch → fertig --------------------------------------------
# `cmp -s` ist still und liefert Exit 0 bei Gleichheit. Wir vergleichen
# Quelle und Ziel; Ziel kann fehlen — dann ist „nicht identisch", also weiter.
if [ -e "${DEST_CONF}" ] && sudo cmp -s "${SRC_CONF}" "${DEST_CONF}"; then
    log "Ziel ist bereits identisch mit Quelle — nichts zu tun."
    exit 0
fi

# --- 3. Backup --------------------------------------------------------------
# Nur backuppen, wenn das Ziel existiert. Bei Erst-Installation gibt es nichts
# zu sichern — und wir wollen kein leeres .bak anlegen.
if [ -e "${DEST_CONF}" ]; then
    log "Backup: ${DEST_CONF} → ${BACKUP_CONF}"
    sudo cp -p "${DEST_CONF}" "${BACKUP_CONF}"
    HAD_PREVIOUS=1
else
    log "Kein bestehendes Ziel — Erst-Installation, kein Backup nötig."
    HAD_PREVIOUS=0
fi

# --- 4. Kopieren ------------------------------------------------------------
log "Kopiere Quelle → Ziel ..."
sudo cp "${SRC_CONF}" "${DEST_CONF}"

# --- 5. Validieren — bei Fehler: Backup zurück ------------------------------
log "nginx-Config validieren (sudo nginx -t) ..."
if ! sudo nginx -t; then
    log "nginx -t fehlgeschlagen — rolle Ziel-Datei zurück."
    if [ "${HAD_PREVIOUS}" -eq 1 ]; then
        sudo cp -p "${BACKUP_CONF}" "${DEST_CONF}"
        log "Backup wiederhergestellt: ${BACKUP_CONF} → ${DEST_CONF}"
    else
        # Bei Erst-Installation gibt es nichts zum Zurückspielen; wir entfernen
        # die kaputte Datei, damit nginx beim nächsten Reload keinen halben
        # Zustand sieht.
        sudo rm -f "${DEST_CONF}"
        log "Kaputte Erst-Installation entfernt: ${DEST_CONF}"
    fi
    die "nginx-Validierung fehlgeschlagen. Original-Stand wiederhergestellt. Bitte Quell-Conf prüfen."
fi

# --- 6. Reload --------------------------------------------------------------
log "nginx neu laden (sudo systemctl reload nginx) ..."
sudo systemctl reload nginx

# --- 7. Erfolg --------------------------------------------------------------
log "Fertig. Aktive Conf: ${DEST_CONF}"
log "Backup (vorheriger Stand): ${BACKUP_CONF}"
