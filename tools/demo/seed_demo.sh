#!/usr/bin/env bash
# Demo-Modus (#1725, Part of #1309 public/verkaufsreif).
#
# Populiert ein **gitignored Wegwerf-Dir** (`xbuddy-data-demo/`) aus den
# generischen, getrackten Seeds (Familie Sonntag — `*.example.json`, seit #1719).
# Danach kann eine Demo-Instanz gegen dieses Dir laufen → populiertes System für
# Screenshots/Onboarding/Demo-Material, OHNE getrackte Dateien zu verschmutzen
# und OHNE die Live-Services/-Daten anzufassen.
#
# ⚠️ SICHERHEIT: dieses Skript schreibt AUSSCHLIESSLICH nach `xbuddy-data-demo/`.
#    Es startet/neustartet KEINE systemd-Services und fasst `/home/buddy/xbuddy-data/`
#    (die echte Familie) NIE an. Der Demo-Run läuft separat (siehe `--env` + README).
#
# Lauf:
#   tools/demo/seed_demo.sh            # populiert das Wegwerf-Dir
#   tools/demo/seed_demo.sh --env      # + druckt die ENV-Exports für den Demo-Run
#
# Ziel-Dir überschreibbar via XBUDDY_DEMO_DIR.

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$_HERE/../.." && pwd)"
DEMO_DIR="${XBUDDY_DEMO_DIR:-$REPO/xbuddy-data-demo}"

# Kuratierte Seed → Ziel-Map: der Live-Dateiname weicht teils vom example-Namen
# ab (z. B. routine.example.json → routine_store.json). Nur DATEN-Seeds, die die
# Views populieren — Config (Ports/Origins) kommt aus den Code-Defaults/ENV.
SEED_KEYS=(
  "instanzen.example.json"
  "familie/familie.example.json"
  "plan/plan.example.json"
  "essen/gerichte.example.json"
  "essen/wuensche.example.json"
  "essen/einkaufsliste.example.json"
  "routine/routine.example.json"
  "wetter/wetter.example.json"
  "panel/panels.example.json"
  "kibuddy/kibuddy.example.json"
  "hoerspiel/hoerspiel.example.json"
)
seed_target() {
  case "$1" in
    "instanzen.example.json")        echo "instanzen.json" ;;
    "familie/familie.example.json")  echo "familie/familie.json" ;;
    "plan/plan.example.json")        echo "plan/plan.json" ;;
    "essen/gerichte.example.json")   echo "essen/gerichte.json" ;;
    "essen/wuensche.example.json")   echo "essen/wuensche.json" ;;
    "essen/einkaufsliste.example.json") echo "essen/einkaufsliste.json" ;;
    "routine/routine.example.json")  echo "routine/routine_store.json" ;;
    "wetter/wetter.example.json")    echo "wetter/wetter.json" ;;
    "panel/panels.example.json")     echo "panel/panels.json" ;;
    "kibuddy/kibuddy.example.json")  echo "kibuddy/kibuddy.json" ;;
    "hoerspiel/hoerspiel.example.json") echo "hoerspiel/hoerspiel.json" ;;
  esac
}

echo "[demo] Ziel-Dir (Wegwerf, gitignored): $DEMO_DIR"
rm -rf "$DEMO_DIR"
n=0
for seed in "${SEED_KEYS[@]}"; do
  src="$REPO/$seed"
  [ -f "$src" ] || { echo "[demo] WARN: Seed fehlt: $seed" >&2; continue; }
  target="$DEMO_DIR/$(seed_target "$seed")"
  mkdir -p "$(dirname "$target")"
  cp "$src" "$target"
  n=$((n + 1))
done
echo "[demo] $n Seeds ins Wegwerf-Dir kopiert (Familie Sonntag)."

# Plan-Wochenplan (#1761): der /display/plan/woche-Grid ist kalender-getrieben
# (plan/kalender.py, sonst Google-only) → für die Demo generieren wir eine lokale
# Kalender-Datei mit Terminen relativ zu HEUTE (aktuelle Mo–So-Woche), die der
# plan-Service über PLAN_KALENDER_DEMO_FILE + DateiTransport liest. So rendert die
# Woche voll, ohne OAuth. Personen-Zuordnung über den Namen im Titel (PLAN-19).
mkdir -p "$DEMO_DIR/plan"
python3 - "$DEMO_DIR/plan/kalender-demo.json" <<'PYCAL'
import json, sys
from datetime import datetime, timedelta, timezone

out_path = sys.argv[1]
tz = timezone(timedelta(hours=2))  # Europe/Berlin-nah; Offset reicht für die Demo
today = datetime.now(tz)
monday = (today - timedelta(days=today.weekday())).replace(
    hour=0, minute=0, second=0, microsecond=0)

# (Wochentag 0=Mo, Startstunde, Dauer_h, Titel, creator-Email)
PLAN = [
    (0, 15, 1, "Schwimmen (Mia)",        "lena@example.org"),
    (0, 16, 1, "Klettern (Finn)",        "jonas@example.org"),
    (1, 14, 1, "Kreativ (Emil)",         "petra@example.org"),
    (1, 16, 1, "Musikschule (Mia)",      "lena@example.org"),
    (2, 15, 2, "Turnen (Finn)",          "jonas@example.org"),
    (3, 14, 1, "Vorlesen (Emil)",        "petra@example.org"),
    (3, 17, 1, "Fußball (Finn)",         "jonas@example.org"),
    (4, 15, 1, "Basteln (Mia)",          "lena@example.org"),
    (4, 16, 2, "Spielplatz (alle)",      "emil@example.org"),
    (5, 10, 2, "Familienausflug",        "emil@example.org"),
    (6, 15, 1, "Backen (Mia & Emil)",    "petra@example.org"),
]
items = []
for i, (wtag, h, dur, titel, mail) in enumerate(PLAN):
    beginn = monday + timedelta(days=wtag, hours=h)
    ende = beginn + timedelta(hours=dur)
    items.append({
        "id": "demo-%02d" % i,
        "summary": titel,
        "start": {"dateTime": beginn.isoformat()},
        "end": {"dateTime": ende.isoformat()},
        "creator": {"email": mail},
    })
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump({"items": items}, fh, ensure_ascii=False, indent=2)
print("[demo] Kalender-Demo: %d Termine (Woche ab %s) → %s"
      % (len(items), monday.date(), out_path))
PYCAL

# Hörspiel-Alben (#1764): der /display/hoerspiel/<kind>/alben-Grid liest Album-
# Manifeste aus dem Datendir (nicht aus example.json) → für die Demo seeden wir
# 3 freigegebene Alben (Tiefenschnitt-Struktur wie live, aber generische Titel —
# KEINE echten Kind-/Freundes-Namen/Orte) + das generische Default-Cover. Kein
# Audio nötig: die Alben-Liste zeigt Titel + Cover. Demo-Slug: mia.
HSP_KID="mia"
HSP_ALBEN="$DEMO_DIR/hoerspiel/alben"
HSP_SHARED="$DEMO_DIR/hoerspiel/shared-assets"
mkdir -p "$HSP_ALBEN" "$HSP_SHARED"
cp "$REPO/tools/demo/assets/hoerspiel-cover-default.jpg" "$HSP_SHARED/cover-default.jpg"
python3 - "$HSP_ALBEN" "$HSP_KID" <<'PYHSP'
import json, sys
alben_dir, kid = sys.argv[1], sys.argv[2]
cover = "/display/hoerspiel/%s/data/shared-assets/cover-default.jpg" % kid
# (nummer, titel) — generisch, ohne echte Namen/Orte.
ALBEN = [
    (1, "Die Schatzsuche im Garten"),
    (2, "Das Wettrennen zum großen Stein"),
    (3, "Der mutige Ausflug zum Leuchtturm"),
]
index = {}
for nummer, titel in ALBEN:
    folge = "folge-%d" % nummer
    index["demo%02d0000000000" % nummer] = folge
    tracks = [{
        "id": "intro-shimmer", "position": 1, "art": "intro",
        "audio-asset": "/display/hoerspiel/%s/data/shared-assets/intro_shimmer.mp3" % kid,
        "dauer-sek": 0,
    }]
    for pos in range(2, 6):  # 4 Inhalts-Tracks (Tiefenschnitt-Struktur wie live)
        tracks.append({
            "id": "%s-track-%02d" % (folge, pos), "position": pos, "art": "inhalt",
            "audio-asset": "/display/hoerspiel/%s/data/alben/%s/audio/track-%02d.mp3"
                           % (kid, folge, pos),
            "dauer-sek": 180 + pos * 12, "titel": None,
        })
    manifest = {
        "id": folge, "nummer": nummer, "titel": titel, "voice": "shimmer",
        "erstellt-am": "2026-06-12", "freigegeben": True,
        "cover-asset": cover, "pikto-hauptbegriffe": [], "tracks": tracks,
    }
    import os
    os.makedirs(os.path.join(alben_dir, folge), exist_ok=True)
    with open(os.path.join(alben_dir, folge, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
with open("%s/.index.json" % alben_dir, "w", encoding="utf-8") as fh:
    json.dump(index, fh, ensure_ascii=False, indent=2)
print("[demo] Hörspiel-Demo: %d Alben + Cover → %s (Slug %s)"
      % (len(ALBEN), alben_dir, kid))
PYHSP

# Personen-Fotos (#1764): familie.example.json erwartet emil.jpg/mia.jpg… — ohne
# die Dateien zeigt das plan-Display kaputte Icons. Wir mappen die generischen
# Demo-Fotos (specs/mockups/…/fotos/demo-*.jpg) auf die erwarteten Namen.
FOTO_SRC="$REPO/specs/mockups/plan-einstellungen/assets/fotos"
FOTO_DST="$DEMO_DIR/familie/fotos"
mkdir -p "$FOTO_DST"
if [ -d "$FOTO_SRC" ]; then
  cp "$FOTO_SRC/demo-a1.jpg" "$FOTO_DST/emil.jpg"
  cp "$FOTO_SRC/demo-a2.jpg" "$FOTO_DST/lena.jpg"
  cp "$FOTO_SRC/demo-a1.jpg" "$FOTO_DST/jonas.jpg"
  cp "$FOTO_SRC/demo-a2.jpg" "$FOTO_DST/petra.jpg"
  cp "$FOTO_SRC/demo-k1.jpg" "$FOTO_DST/mia.jpg"
  cp "$FOTO_SRC/demo-k2.jpg" "$FOTO_DST/finn.jpg"
  echo "[demo] Personen-Fotos: 6 Demo-Fotos → $FOTO_DST"
else
  echo "[demo] WARN: Demo-Foto-Quelle fehlt: $FOTO_SRC" >&2
fi

# Photo-Buddy-Rahmen (#1773-Folge): /display/photo/rahmen liest Medien aus einer
# library (tools.medien_store) → für die Demo bauen wir sie aus den gebündelten
# CC0-Fotos (tools/demo/assets/photos/, Unsplash-Lizenz, keine echten Familien-
# fotos). Thumbnail = Vollbild (Demo, kein PIL nötig). Austauschbar: eigene Fotos.
PHOTO_SRC="$REPO/tools/demo/assets/photos"
PHOTO_DST="$DEMO_DIR/photo/medien"
mkdir -p "$PHOTO_DST"
if compgen -G "$PHOTO_SRC/*.jpg" >/dev/null 2>&1; then
  PYTHONPATH="$REPO" python3 - "$PHOTO_SRC" "$PHOTO_DST" <<'PYPHOTO'
import glob, os, sys
from tools.medien_store import store
src, dst = sys.argv[1], sys.argv[2]
fotos = sorted(glob.glob(os.path.join(src, "*.jpg")))
for n, f in enumerate(fotos, 1):
    with open(f, "rb") as fh:
        daten = fh.read()
    mid = "demo%02d" % n
    store.add(dst, id=mid, typ=store.TYP_FOTO, daten=daten,
              dateiname="%s.jpg" % mid, thumbnail_daten=daten,
              thumbnail_name="%s_thumb.jpg" % mid)
print("[demo] Photo-Demo: %d Fotos → %s" % (len(fotos), dst))
PYPHOTO
else
  echo "[demo] WARN: Photo-Bundle fehlt: $PHOTO_SRC" >&2
fi

if [ "${1:-}" = "--env" ]; then
  cat <<ENV

# ── Demo-Run: diese ENV-Exports zeigen die Services auf das Wegwerf-Dir ──
# (Auf ALTERNATIVEN Ports starten, damit die Live-Services unberührt bleiben —
#  siehe README. Config-Datei-Pfade sind demo-spezifisch, Live bleibt getrennt.)
export INSTANZEN_CONFIG_FILE="$DEMO_DIR/instanzen.json"
export FAMILIE_STORE_FILE="$DEMO_DIR/familie/familie.json"
export PLAN_CONFIG_FILE="$DEMO_DIR/plan/plan.json"
# Demo-Kalender (#1761): schaltet plan auf die lokale Wochen-Datei statt Google.
export PLAN_KALENDER_DEMO_FILE="$DEMO_DIR/plan/kalender-demo.json"
export ROUTINE_STORE_FILE="$DEMO_DIR/routine/routine_store.json"
export WETTER_CONFIG_FILE="$DEMO_DIR/wetter/wetter.json"
# essen liest per-Datei-ENVs (ESSEN_*_FILE), NICHT ESSEN_DATA_DIR (#1773-Folge).
export ESSEN_WUENSCHE_FILE="$DEMO_DIR/essen/wuensche.json"
export ESSEN_EINKAUFSLISTE_FILE="$DEMO_DIR/essen/einkaufsliste.json"
export ESSEN_GERICHTE_FILE="$DEMO_DIR/essen/gerichte.json"
export PHOTO_LIBRARY_VERZEICHNIS="$DEMO_DIR/photo/medien"
export PANEL_REGISTRY_FILE="$DEMO_DIR/panel/panels.json"
export KIBUDDY_CONFIG_FILE="$DEMO_DIR/kibuddy/kibuddy.json"
export HOERSPIEL_DATA_ROOT="$DEMO_DIR/hoerspiel"
# Demo-Hörspiel-Instanz (#1764): Slug mia — matcht die Album-Cover-/Audio-Pfade.
# Display: /display/hoerspiel/mia/alben.
export HOERSPIEL_KIND_ID="mia"
ENV
fi

echo "[demo] fertig. Getrackte Dateien unberührt (git status bleibt sauber)."
