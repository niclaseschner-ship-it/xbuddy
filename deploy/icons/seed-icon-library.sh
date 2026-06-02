#!/usr/bin/env bash
#
# seed-icon-library.sh — befüllt die zentrale Icon-Wurzel aus dem
# vorhandenen KIBuddy-Piktogramm-Cache.
#
# Setzt specs/platform/icons.md ICONS-4 um:
#   - kopiert die ARASAAC-PNGs nach  <icon-root>/arasaac/<id>.png  (ICONS-1)
#   - kopiert  pictogram_cache.json  in die Icon-Wurzel             (ICONS-3)
#   - idempotent: bereits vorhandene Zieldateien werden uebersprungen
#   - KEIN Re-Fetch von ARASAAC, KEIN Zugriff auf KIBuddy-Code — nur Assets
#
# Verwendung:
#   ./seed-icon-library.sh [ICON_ROOT] [KIBUDDY_CACHE]
#
#   ICON_ROOT       Ziel-Wurzel (ICONS-2). Default /home/buddy/apps/icons/.
#                   Auch per ENV ICON_ROOT setzbar; das Arg gewinnt.
#   KIBUDDY_CACHE   Quelle: KIBuddy-Piktogramm-Verzeichnis. Default
#                   /home/buddy/apps/kibuddy/static/pictograms/.
#                   Auch per ENV KIBUDDY_CACHE setzbar; das Arg gewinnt.
#
# Das pictogram_cache.json wird relativ zum KIBuddy-Cache erwartet
# (../pictogram_cache.json), wie im vorhandenen KIBuddy-Layout.
#
# Fehlende IDs spaeter nachladen (ICONS-4: bewusst NICHT automatisiert):
# eine einzelne ARASAAC-ID zieht man bei Bedarf manuell, z. B.
#   curl -fsSL "https://api.arasaac.org/api/pictograms/<id>?download=false" \
#        -o "<icon-root>/arasaac/<id>.png"
# (CC BY-NC-SA beachten, ICONS-6.)

set -euo pipefail

ICON_ROOT="${1:-${ICON_ROOT:-/home/buddy/apps/icons/}}"
KIBUDDY_CACHE="${2:-${KIBUDDY_CACHE:-/home/buddy/apps/kibuddy/static/pictograms/}}"

# Pfade normalisieren (kein doppelter Slash) und ableiten.
ICON_ROOT="${ICON_ROOT%/}"
KIBUDDY_CACHE="${KIBUDDY_CACHE%/}"
ARASAAC_DEST="${ICON_ROOT}/arasaac"
CACHE_JSON_SRC="$(dirname "${KIBUDDY_CACHE}")/pictogram_cache.json"
CACHE_JSON_DEST="${ICON_ROOT}/pictogram_cache.json"

log() { printf '[seed-icons] %s\n' "$*"; }

if [[ ! -d "${KIBUDDY_CACHE}" ]]; then
  log "FEHLER: Quelle nicht gefunden: ${KIBUDDY_CACHE}" >&2
  exit 1
fi

log "Quelle : ${KIBUDDY_CACHE}"
log "Ziel   : ${ARASAAC_DEST}"

mkdir -p "${ARASAAC_DEST}"

copied=0
skipped=0
shopt -s nullglob
for src in "${KIBUDDY_CACHE}"/*.png; do
  name="$(basename "${src}")"
  dest="${ARASAAC_DEST}/${name}"
  if [[ -e "${dest}" ]]; then
    skipped=$((skipped + 1))
    continue
  fi
  cp -p "${src}" "${dest}"
  copied=$((copied + 1))
done
shopt -u nullglob

log "PNGs: ${copied} kopiert, ${skipped} uebersprungen (bereits vorhanden)"

# Wort->ID-Mapping mitnehmen (ICONS-3), ebenfalls idempotent.
if [[ -f "${CACHE_JSON_SRC}" ]]; then
  if [[ -e "${CACHE_JSON_DEST}" ]]; then
    log "pictogram_cache.json: bereits vorhanden, uebersprungen"
  else
    cp -p "${CACHE_JSON_SRC}" "${CACHE_JSON_DEST}"
    log "pictogram_cache.json: kopiert"
  fi
else
  log "WARNUNG: ${CACHE_JSON_SRC} nicht gefunden — Mapping nicht geseedet" >&2
fi

log "fertig."
