#!/usr/bin/env bash
# tools/mirror/build_public_mirror.sh — Sanitized-Public-Mirror-Bau (T1170)
#
# Ratifiziertes Design:
#   20260730-1500-RATIFIZIERT-public-mirror.md (Baustein 1 + 2 + 3 Gates)
#   20260731-0100-RATIFIZIERT-config-separation-weg-c.md (Baustein-2-Amendment:
#     Slug-only im Snapshot, Klarnamen via Config-out #1656)
#
# Drei-Phasen-Mechanik:
#   Baustein 1: Orphan-Squash via git archive → history-loses Snapshot
#   Baustein 2: Slug-only-Rename (mia→kind1, finn→kind2, emil→kind3)
#               + LICENSE-Mail-Scrub (Entscheidung B)
#   Gate 1: Text-Grep auf Klarnamen / FQDN / IPs / Telegram-IDs
#   Gate 2: Binär-Inventar (kein nicht-allowgelistetes Binary)
#   Gate 3: Python compile-Probe (syntax grün nach Slug-Rename)
#
# Ein-Wege-Tür: Push ist NICHT Teil dieses Skripts.
#               Skript-Exit≠0 bei jedem Gate-Treffer → kein Artefakt.
#
# Verwendung:
#   build_public_mirror.sh [--dry-run] [--out DIR] [--src DIR]
#
# Optionen:
#   --dry-run       Snapshot erzeugen + Gates laufen lassen, KEIN git-init/Commit
#   --out DIR       Ziel-Verzeichnis (Default: /tmp/xbuddy-mirror-XXXXXX)
#   --src DIR       Quell-Repository (Default: Repo dieses Skripts via git)
#
# Exit-Codes:
#   0  Alle Gates grün — Snapshot bereit für manuellen Push durch Nic
#   1  Gate-Fehler (Klarname / Binary / Compile) — Snapshot NICHT verwenden
#   2  Fehler in Vorbedingungen (git, src-Pfad, etc.)

set -euo pipefail

###############################################################################
# Hilfsfunktionen
###############################################################################

log()  { printf '[mirror] %s\n' "$*" >&2; }
ok()   { printf '[mirror] ✓ %s\n' "$*" >&2; }
fail() { printf '[mirror] ✗ GATE-FEHLER: %s\n' "$*" >&2; }
die()  { printf '[mirror] FATAL: %s\n' "$*" >&2; exit 2; }

###############################################################################
# Argument-Parsing
###############################################################################

DRY_RUN=0
OUT_DIR=""
SRC_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=1; shift ;;
        --out)        OUT_DIR="$2"; shift 2 ;;
        --src)        SRC_DIR="$2"; shift 2 ;;
        -h|--help)
            sed -n '/^# Verwendung:/,/^[^#]/p' "$0" | head -20
            exit 0
            ;;
        *) die "Unbekannte Option: $1 (--help für Hilfe)" ;;
    esac
done

###############################################################################
# Quell-Repo ermitteln
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$SRC_DIR" ]]; then
    # Zwei Ebenen hoch: tools/mirror → tools → repo-root
    SRC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

# .git kann ein Verzeichnis (normales Repo) oder eine Datei (Worktree) sein
[[ -e "$SRC_DIR/.git" ]] || die "Kein Git-Repo unter: $SRC_DIR"
log "Quelle: $SRC_DIR"
log "Branch: $(git -C "$SRC_DIR" rev-parse --abbrev-ref HEAD)"
log "Commit: $(git -C "$SRC_DIR" rev-parse HEAD)"

###############################################################################
# Ziel-Verzeichnis
###############################################################################

if [[ -z "$OUT_DIR" ]]; then
    OUT_DIR="$(mktemp -d /tmp/xbuddy-mirror-XXXXXX)"
    log "Ziel (auto): $OUT_DIR"
else
    mkdir -p "$OUT_DIR"
    log "Ziel: $OUT_DIR"
fi

SNAP_DIR="$OUT_DIR/snapshot"
mkdir -p "$SNAP_DIR"

###############################################################################
# Baustein 1 — Orphan-Squash via git archive
###############################################################################

log "--- Baustein 1: Orphan-Squash ---"
log "git archive HEAD | tar -x → $SNAP_DIR"
git -C "$SRC_DIR" archive HEAD | tar -x -C "$SNAP_DIR"
[[ -d "$SNAP_DIR/.git" ]] && die ".git im Snapshot vorhanden — git archive hat .git exportiert (unerwartet)"
ok "Kein .git im Snapshot"

###############################################################################
# Baustein 2 — Instanz-Identifier-Scrub + Slug-Rename + LICENSE-Mail-Scrub
###############################################################################

log "--- Baustein 2: Identifier-Scrub + Slug-Rename ---"

# name-map-Generator (inline, aus Registries abgeleitet)
# Quell-Slugs/Namen → generische Ziele (Snapshot-only, Live-Code unberührt)
#
# Kinder-Slugs (technisch, in URLs / Service-Namen):
#   mia  → kind1   finn   → kind2   emil → kind3
#
# Erwachsenen-Namen (in Specs, plan.example.json, Doku):
#   emil/Niclas  → kind3/Kind3 (Slug-Doppel: kind-Rolle + Erwachsener)
#   lena/Lena  → erwachsen1/Erwachsen1
#   jonas/Jonas  → erwachsen2/Erwachsen2
#   petra/Petra      → erwachsen3/Erwachsen3
#   timo/Timo      → erwachsen4/Erwachsen4
#
# Entscheidung 1=B (2026-07-30): Demo-Namen (menschlich lesbar)
# Ratifiziert: 20260730-1500-RATIFIZIERT-public-mirror.md
# Amendment: 20260731-0100-RATIFIZIERT-config-separation-weg-c.md (Slug-only im Snapshot)
#
# REIHENFOLGE ist wichtig:
#   Schritt A: Instanz-spezifische Compound-Identifier zuerst
#              (emilsonntag-ship-it muss VOR emil→kind3 ersetzt werden,
#               sonst wird es zu kind3sonntag-ship-it)
#   Schritt B: Slug-Rename (paul/finn/emil/erwachsene)
#   Schritt C: LICENSE-Mail

is_text_file() {
    file "$1" | grep -qiE 'text|script|json|xml|html|yaml|ini|conf|markdown|empty'
}
export -f is_text_file

# --- Schritt A: Compound-Identifier + Instanz-spezifische IDs ---
log "  Schritt A: Compound-Identifier-Scrub ..."
find "$SNAP_DIR" -type f | while IFS= read -r f; do
    if ! is_text_file "$f"; then continue; fi
    sed -i \
        -e 's|emilsonntag-ship-it/xbuddy|<your-org>/xbuddy|g' \
        -e 's|emilsonntag-ship-it|<your-org>|g' \
        -e 's|buddyboard\.demo-tailnet\.ts\.net|buddyboard.<tailscale-id>.ts.net|g' \
        -e 's|demo-tailnet|<tailscale-id>|g' \
        -e 's|192\.168\.178\.[0-9]\+|192.168.x.x|g' \
        -e 's|100\.108\.61\.31|100.x.y.z|g' \
        -e 's|\b0000000000\b|<chat-id>|g' \
        -e 's|emil\.sonntag@gmail\.com|<contact via repo issues>|g' \
        -e 's|emil\.sonntag@gmx\.de|<contact via repo issues>|g' \
        -e 's|emil_sonntag@gmx\.de|<contact via repo issues>|g' \
        -e 's|@gmx\.de|@example.de|g' \
        -e 's|@gmx\\\.de|@example.de|g' \
        -e 's|real-email-gmx|real-email-example|g' \
        "$f"
done
ok "Compound-Identifier ersetzt"

# --- Schritt B: Slug-Rename ---
# \b = Wortgrenze — für 'petra' PFLICHT wegen 'Petrantwortung', 'unpetraendert' etc.
# mia/finn/emil: ohne Wortgrenze für camelCase-Identifier (miaFolge, finnCall)
log "  Schritt B: Slug-Rename ..."
slug_rename_file() {
    local f="$1"
    local bn
    bn="$(basename "$f")"
    # LICENSE wird separat behandelt (Copyright-Zeile bleibt, nur Mail raus)
    if [[ "$bn" == "LICENSE" ]]; then return 0; fi
    # Nicht-Textdateien überspringen — explizites if verhindert set -e-Abbruch
    if ! is_text_file "$f"; then return 0; fi
    sed -i \
        -e 's/mia/kind1/g' \
        -e 's/Mia/Kind1/g' \
        -e 's/MIA/KIND1/g' \
        -e 's/finn/kind2/g' \
        -e 's/Finn/Kind2/g' \
        -e 's/FINN/KIND2/g' \
        -e 's/emil/kind3/g' \
        -e 's/Niclas/Kind3/g' \
        -e 's/NICLAS/KIND3/g' \
        -e 's/\blena\b/erwachsen1/g' \
        -e 's/\bLena\b/Erwachsen1/g' \
        -e 's/\bLENA\b/ERWACHSEN1/g' \
        -e 's/lenas\b/erwachsen1s/g' \
        -e 's/Lenas\b/Erwachsen1s/g' \
        -e 's/\bjonas\b/erwachsen2/g' \
        -e 's/\bJonas\b/Erwachsen2/g' \
        -e 's/\bJONAS\b/ERWACHSEN2/g' \
        -e 's/jonass\b/erwachsen2s/g' \
        -e 's/Jonass\b/Erwachsen2s/g' \
        -e 's/\bpetra\b/erwachsen3/g' \
        -e 's/\bPetra\b/Erwachsen3/g' \
        -e 's/\bPETRA\b/ERWACHSEN3/g' \
        -e 's/\btimo\b/erwachsen4/g' \
        -e 's/\bTimo\b/Erwachsen4/g' \
        -e 's/\bTIMO\b/ERWACHSEN4/g' \
        -e 's/\bEschner\b/<Familienname>/g' \
        -e 's/\bESCHNER\b/<FAMILIENNAME>/g' \
        "$f"
}

export -f slug_rename_file
find "$SNAP_DIR" -type f | while IFS= read -r f; do
    slug_rename_file "$f" || true   # slug_rename_file returns 0; || true schützt zusätzlich
done
ok "Slug-Rename abgeschlossen (mia/finn/emil + lena/jonas/petra/timo + Eschner)"

# --- Schritt C: LICENSE: private Mail raus (Entscheidung B — Nic 2026-07-30) ---
LICENSE_FILE="$SNAP_DIR/LICENSE"
if [[ -f "$LICENSE_FILE" ]]; then
    # Zeile mit "@" in der Kontakt-Zeile entfernen; öffentliche Repo-URL stattdessen
    sed -i '/^Kontakt:.*@/d' "$LICENSE_FILE"
    # Fallback: generisches Mail-Pattern
    sed -i 's|[a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]*\.[a-zA-Z]\{2,\}|<issues im Repository>|g' "$LICENSE_FILE"
    ok "LICENSE: private Mail-Adresse entfernt (Copyright-Name 'Niclas Eschner' ratifiziert behalten)"
fi

###############################################################################
# Gate 1 — Text-Grep: KEIN Klarname / FQDN / IP / Telegram-ID
###############################################################################

log "--- Gate 1: Klarname-Grep ---"
GATE1_FAIL=0

# Alle Suchmuster (aus ratifiziertem Design + Weg-C-Amendment)
# Hinweis: Groß/klein durch slug_rename bereits abgedeckt;
# hier suchen wir auf verbleibende Treffer
PATTERNS=(
    # Familien-Namen (nach Slug-Rename erledigt — mit \b Wortgrenzen!)
    # Ohne \b würde 'petra' in 'Petrantwortung' treffen.
    '\blena\b'
    '\bjonas\b'
    '\bpetra\b'
    '\btimo\b'
    '\bsonntag\b'
    # Private Mail-Adresse
    'emil\.sonntag@gmail'
    'emil\.sonntag@gmx'
    'emil_sonntag@gmx'
    # Familien-E-Mail-Domain (in privacy_gate.py als Detektor referenziert → nach @example.de scrubben)
    '@gmx\.de'
    # GitHub-Org (enthält echten Benutzernamen)
    'emilsonntag-ship-it'
    # Tailscale FQDN-Identifier (instanz-spezifisch)
    'demo-tailnet'
    # Spezifische LAN-IP (Heimnetz-Adresse, NICHT generische RFC-1918-CIDRs)
    '192\.168\.178\.'
    # Spezifische Tailnet-IP (100.64.0.10 — NICHT 100.64.0.0/10 CIDR-Range)
    '100\.108\.61\.'
    # Bekannte Telegram Chat-ID
    '0000000000'
)

for pat in "${PATTERNS[@]}"; do
    # \bsonntag\b: LICENSE ist ratifiziert ausgenommen (Copyright-Name bleibt, 2026-07-30)
    if [[ "$pat" == '\bsonntag\b' ]]; then
        hits=$(grep -rniE "$pat" "$SNAP_DIR" 2>/dev/null \
               | grep -v '^Binary' \
               | grep -v '/LICENSE:' \
               || true)
    else
        hits=$(grep -rniE "$pat" "$SNAP_DIR" 2>/dev/null | grep -v '^Binary' || true)
    fi
    if [[ -n "$hits" ]]; then
        fail "Muster '$pat' gefunden:"
        echo "$hits" | head -5 >&2
        GATE1_FAIL=1
    fi
done

# Slug-Rename-Check: Keine der alten Slugs mehr
for slug in mia Mia MIA finn Finn FINN; do
    hits=$(grep -rnE "\b${slug}\b" "$SNAP_DIR" 2>/dev/null | grep -v '^Binary' || true)
    if [[ -n "$hits" ]]; then
        fail "Alter Slug '$slug' noch vorhanden (Rename unvollständig):"
        echo "$hits" | head -5 >&2
        GATE1_FAIL=1
    fi
done

# emil als Slug — LICENSE ausgenommen (Copyright-Name ratifiziert behalten, 2026-07-30)
for slug in emil Niclas NICLAS; do
    hits=$(grep -rnE "\b${slug}\b" "$SNAP_DIR" 2>/dev/null \
           | grep -v '^Binary' \
           | grep -v '/LICENSE:' \
           || true)
    if [[ -n "$hits" ]]; then
        fail "Alter Slug '${slug}' noch vorhanden:"
        echo "$hits" | head -5 >&2
        GATE1_FAIL=1
    fi
done

if [[ $GATE1_FAIL -eq 0 ]]; then
    ok "Gate 1: Kein Klarname / FQDN / IP / Telegram-ID im Snapshot"
else
    fail "Gate 1 NICHT BESTANDEN — Snapshot darf NICHT veröffentlicht werden"
    exit 1
fi

###############################################################################
# Gate 2 — Binär-Inventar
###############################################################################

log "--- Gate 2: Binär-Inventar ---"

# Allowlist synthetischer Binär-Assets (Erweiterungen)
ALLOWED_BINARY_EXTS="png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot|svg|pdf|mp3|ogg|wav|webp"

GATE2_FAIL=0
while IFS= read -r f; do
    # Echte Binär-Dateien: ELF-Executables, Archive, komprimierte Daten
    # "text executable" (Python mit +x) ist KEIN Binary — nur ELF / Bytecode
    if file "$f" | grep -qiE '^[^:]+: (ELF |PE32|Mach-O|.*archive|.*compressed|.*bytecode|.*byte-compiled)'; then
        rel="${f#$SNAP_DIR/}"
        fail "Nicht-erlaubtes Binary: $rel"
        GATE2_FAIL=1
    fi
done < <(find "$SNAP_DIR" -type f | grep -vE "\.($ALLOWED_BINARY_EXTS)$")

if [[ $GATE2_FAIL -eq 0 ]]; then
    ok "Gate 2: Kein unerlaubtes Binary im Snapshot"
else
    fail "Gate 2 NICHT BESTANDEN"
    exit 1
fi

###############################################################################
# Gate 3 — Python compile-Probe
###############################################################################

log "--- Gate 3: Python compile-Probe ---"
GATE3_FAIL=0

if command -v python3 &>/dev/null; then
    while IFS= read -r f; do
        if ! python3 -m py_compile "$f" 2>/dev/null; then
            rel="${f#$SNAP_DIR/}"
            fail "Python-Syntaxfehler nach Slug-Rename: $rel"
            GATE3_FAIL=1
        fi
    done < <(find "$SNAP_DIR" -name "*.py" -type f)

    if [[ $GATE3_FAIL -eq 0 ]]; then
        ok "Gate 3: Alle Python-Dateien kompilieren nach Slug-Rename"
    else
        fail "Gate 3 NICHT BESTANDEN — Rename hat Python-Syntax gebrochen"
        exit 1
    fi
else
    log "python3 nicht gefunden — Gate 3 übersprungen"
fi

###############################################################################
# Baustein 1 — git init + generischer Init-Commit (nur wenn nicht dry-run)
###############################################################################

if [[ $DRY_RUN -eq 1 ]]; then
    log "--- DRY-RUN: kein git init / kein Commit ---"
    log "Snapshot liegt in: $SNAP_DIR"
    log "Alle Gates bestanden. Snapshot ist bereit für manuelle Prüfung."
    log ""
    log "NÄCHSTER SCHRITT (nur durch Nic):"
    log "  cd $SNAP_DIR"
    log "  git init && git add . && git commit -m 'Initial public release'"
    log "  git remote add origin <public-repo-url>"
    log "  git push -u origin main"
    exit 0
fi

log "--- git init + Init-Commit ---"
cd "$SNAP_DIR"
git init -q
git add .
GIT_AUTHOR_NAME="xbuddy" \
GIT_AUTHOR_EMAIL="noreply@example.org" \
GIT_COMMITTER_NAME="xbuddy" \
GIT_COMMITTER_EMAIL="noreply@example.org" \
git commit -q -m "Initial public release"

COMMIT_COUNT=$(git log --oneline | wc -l)
if [[ "$COMMIT_COUNT" -ne 1 ]]; then
    die "Orphan-Check: erwartet 1 Commit, gefunden: $COMMIT_COUNT"
fi
ok "Orphan-Squash: genau 1 Commit, keine History-Blobs"

###############################################################################
# Abschluss
###############################################################################

log ""
log "======================================================================="
ok "Alle Gates bestanden. Snapshot liegt in:"
log "  $SNAP_DIR"
log ""
log "WARNUNG — Ein-Wege-Tür:"
log "  Push auf ein öffentliches Repo ist ein MANUELLER Nic-Akt."
log "  Dieses Skript hat NICHTS öffentlich gepusht."
log ""
log "Nächster Schritt (nur durch Nic):"
log "  cd $SNAP_DIR"
log "  git remote add origin <public-repo-url>"
log "  git push -u origin main"
log "======================================================================="
