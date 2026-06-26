#!/usr/bin/env bash
# deploy-methode.sh — PW-74 / RAT-23 Glue-SSoT-Deploy
#
# Spiegelt die im Repo unter methode/ versionierte Methoden-Glue (Agents,
# Commands, Contracts, Hooks) nach ~/.claude/, dem Laufzeit-Ort, den der
# Claude-Code-Harness liest. Repo = SSoT (Edit + Review + Action-Sicht),
# ~/.claude = Deploy-Ziel.
#
# Quelle ist IMMER ein git-Objekt-Ref (`git archive`), NIE der Working Tree —
# objektbasiert und immun gegen den Branch-Flip, den der Shared-Root fährt
# (RAT-14, arbeitstag.md CHK-1). Kein Symlink → keine Interaktion mit dem
# CHK-1-Ref-Reset.
#
# Nutzung:
#   deploy-methode.sh [--source-ref <sha|branch>] [--dry-run] [--verify-only]
#
#   --source-ref REF   Quelle. Default: origin/main (gilt NACH dem Merge).
#                      Vor dem Merge: expliziter Pilot-Branch/-SHA, der methode/
#                      bereits trägt (origin/main tut das anfangs noch nicht).
#   --dry-run          Zeigt, was sich änderte, ohne zu schreiben.
#   --verify-only      Schreibt nichts; vergleicht ~/.claude gegen den Ref
#                      (sha256) und meldet Drift. Kill-Kriterium-Probe (RAT-23).
set -euo pipefail

REPO="${XBUDDY_REPO:-/home/buddy/repos/xbuddy}"
DEST="${CLAUDE_HOME:-$HOME/.claude}"
SORTEN=(agents commands contracts hooks)
SOURCE_REF="origin/main"
DRY_RUN=0
VERIFY_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --source-ref) SOURCE_REF="$2"; shift 2;;
    --dry-run)    DRY_RUN=1; shift;;
    --verify-only) VERIFY_ONLY=1; shift;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "Unbekanntes Argument: $1" >&2; exit 2;;
  esac
done

command -v git >/dev/null || { echo "git fehlt" >&2; exit 1; }

# Bei Remote-Ref aktuell halten (lokale Refs/SHAs unangetastet lassen).
if printf '%s' "$SOURCE_REF" | grep -q '^origin/'; then
  git -C "$REPO" fetch origin --quiet
fi

# methode/ aus dem Objekt-Tree des Ref extrahieren (NICHT Working Tree).
if ! git -C "$REPO" cat-file -e "${SOURCE_REF}:methode" 2>/dev/null; then
  echo "FEHLER: '${SOURCE_REF}' trägt kein methode/ — falscher Ref?" >&2
  echo "Hinweis: vor dem Welle-1-Merge --source-ref <pilot-branch> nutzen." >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$REPO" archive "$SOURCE_REF" methode/ | tar -x -C "$TMP"
SRC="$TMP/methode"

sha() { sha256sum "$1" | cut -d' ' -f1; }

drift=0
changed=0
for sorte in "${SORTEN[@]}"; do
  [ -d "$SRC/$sorte" ] || continue
  while IFS= read -r -d '' f; do
    rel="${f#"$SRC/$sorte/"}"
    target="$DEST/$sorte/$rel"
    if [ ! -f "$target" ]; then
      echo "  [NEU]    $sorte/$rel"
      changed=1; drift=1
    elif [ "$(sha "$f")" != "$(sha "$target")" ]; then
      echo "  [DIFF]   $sorte/$rel"
      changed=1; drift=1
    fi
  done < <(find "$SRC/$sorte" -type f -print0)
done

if [ "$VERIFY_ONLY" -eq 1 ]; then
  if [ "$drift" -eq 1 ]; then
    echo "✗ DRIFT: ~/.claude weicht von ${SOURCE_REF}:methode/ ab (s.o.)." >&2
    exit 1
  fi
  echo "✓ Kein Drift: ~/.claude == ${SOURCE_REF}:methode/ (alle Sorten)."
  exit 0
fi

if [ "$changed" -eq 0 ]; then
  echo "✓ Bereits aktuell — nichts zu deployen (${SOURCE_REF})."
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "(dry-run) — obige Änderungen würden nach $DEST/ geschrieben."
  exit 0
fi

for sorte in "${SORTEN[@]}"; do
  [ -d "$SRC/$sorte" ] || continue
  mkdir -p "$DEST/$sorte"
  rsync -a --checksum "$SRC/$sorte/" "$DEST/$sorte/"
done
# Hooks ausführbar halten.
chmod +x "$DEST"/hooks/*.py 2>/dev/null || true
echo "✓ Deployed ${SOURCE_REF}:methode/ → $DEST/ ($(printf '%s ' "${SORTEN[@]}"))."
