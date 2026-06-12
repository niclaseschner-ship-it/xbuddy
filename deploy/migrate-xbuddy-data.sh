#!/usr/bin/env bash
# PW-6 Etappe 1 — Instanz-Daten aus dem Checkout nach /home/buddy/xbuddy-data/
# herauslösen + systemd-Drop-ins setzen.
#
# Idempotent (#737): existierende Datei im Ziel wird NICHT überschrieben
# („vorhanden, übersprungen" im Output). Re-Run auf voll befülltem
# xbuddy-data/ ändert keine Daten — Live-Stand von familie.json, plan.db,
# conversations.db etc. bleibt unangetastet.
#
# Reset (manuell, vor Re-Befüllung): `sudo mv /home/buddy/xbuddy-data
# /home/buddy/xbuddy-data.bak-$(date +%s)` — kein --force-Modus im Skript.
# Pi-Maintainer = Nic = root; eine manuelle Reset-Geste reicht (#737 Nic-Wahl A).
#
# Rollback der Drop-ins: Datei unter $DROP/xbuddy-*.service.d/10-data-path.conf
# entfernen + `systemctl daemon-reload` + Service-Restart. Originale im
# Checkout bleiben unangetastet.

set -euo pipefail
REPO=/home/buddy/repos/xbuddy
DATA=/home/buddy/xbuddy-data
DROP=/etc/systemd/system
VENV=/home/buddy/apps/venv/bin/python

say(){ echo "==== $* ===="; }

# Kopiert eine Datei OHNE bestehende zu überschreiben. Idempotent: Re-Run
# auf voll befüllter Ziel-Datei tut nichts (#737).
copy_file_safe(){ # $1=src $2=dst
  if [[ -e "$2" ]]; then
    echo "  übersprungen: $2 (vorhanden)"
  elif [[ ! -e "$1" ]]; then
    echo "  fehlt im Repo: $1"
  else
    cp -p "$1" "$2"
    echo "  kopiert:    $2"
  fi
}

# Sync für Verzeichnisse mit `cp -np` (no-clobber pro Datei). Existierende
# Dateien im Ziel werden überspringen; nur neue/fehlende Dateien werden
# nachgezogen. GNU cp -n verhält sich pro Datei (#737 AC2).
copy_dir_safe(){ # $1=src/. $2=dst/
  mkdir -p "$2"
  if [[ ! -d "${1%/.}" ]]; then echo "  fehlt im Repo: ${1%/.}"; return; fi
  cp -rnp "$1" "$2" 2>/dev/null || true
  echo "  Verzeichnis-Sync (no-clobber): $2"
}

health(){ # $1=url $2=name
  code=$(curl -sL -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo 000)
  if [[ "$code" =~ ^(200|301|302|308|404)$ ]]; then echo "  OK  $2 → HTTP $code"; else echo "  FAIL $2 → HTTP $code"; return 1; fi
}

# Schreibt ein Drop-in NUR, wenn der Soll-Inhalt vom Ist-Inhalt abweicht.
# Verhindert mtime-Drift bei Re-Runs (#737).
dropin(){ # $1=service  $2=conf-body
  local conf="$DROP/$1.service.d/10-data-path.conf"
  mkdir -p "$DROP/$1.service.d"
  if [[ -f "$conf" ]] && diff -q <(printf '%s\n' "$2") "$conf" >/dev/null 2>&1; then
    echo "  unverändert: $conf"
  else
    printf '%s\n' "$2" > "$conf"
    echo "  geschrieben: $conf"
  fi
}

# ---------- Daten kopieren ----------
say "1) Daten kopieren (cp -np: no-clobber, Live-Stand bleibt; Re-Run idempotent)"
mkdir -p "$DATA"/{familie,geraete,panel,plan,wetter,photo,eltern-chat}
copy_file_safe "$REPO/familie/familie.json"          "$DATA/familie/familie.json"
copy_dir_safe  "$REPO/familie/fotos/."               "$DATA/familie/fotos/"
copy_file_safe "$REPO/geraete/geraete.json"          "$DATA/geraete/geraete.json"
copy_file_safe "$REPO/panel/panels.json"             "$DATA/panel/panels.json"
copy_file_safe "$REPO/plan/plan.json"                "$DATA/plan/plan.json"
copy_file_safe "$REPO/plan/plan.db"                  "$DATA/plan/plan.db"
copy_file_safe "$REPO/wetter/wetter.json"            "$DATA/wetter/wetter.json"
copy_dir_safe  "$REPO/photo/medien/."                "$DATA/photo/medien/"
copy_file_safe "$REPO/eltern-chat/.env"              "$DATA/eltern-chat/.env"
copy_file_safe "$REPO/eltern-chat/conversations.db"  "$DATA/eltern-chat/conversations.db"
# chmod 600 ist Set-only auf vorhandene Files — kein Inhalt-Touch.
chmod 600 "$DATA/eltern-chat/.env" "$DATA/familie/familie.json" "$DATA/geraete/geraete.json" "$DATA/panel/panels.json" "$DATA/plan/plan.json" "$DATA/wetter/wetter.json" 2>/dev/null || true

# ---------- Drop-ins ----------
say "2) systemd Drop-ins (nur schreiben wenn Inhalt abweicht)"
dropin xbuddy-familie "[Service]
ExecStart=
ExecStart=$VENV -m familie.main --host 127.0.0.1 --port 5010 --registry $DATA/familie/familie.json"
dropin xbuddy-geraete "[Service]
ExecStart=
ExecStart=$VENV -m geraete.main --host 127.0.0.1 --port 5040 --geraete $DATA/geraete/geraete.json"
dropin xbuddy-panel "[Service]
ExecStart=
ExecStart=$VENV -m panel.main --host 127.0.0.1 --port 5041 --panels $DATA/panel/panels.json --geraete-url http://127.0.0.1:5040"
dropin xbuddy-plan "[Service]
Environment=PLAN_CONFIG_FILE=$DATA/plan/plan.json
Environment=PLAN_DB_DATEI=$DATA/plan/plan.db"
dropin xbuddy-wetter "[Service]
Environment=WETTER_CONFIG_FILE=$DATA/wetter/wetter.json"
dropin xbuddy-photo "[Service]
Environment=PHOTO_LIBRARY_VERZEICHNIS=$DATA/photo/medien"
dropin xbuddy-eltern-chat "[Service]
EnvironmentFile=
EnvironmentFile=$DATA/eltern-chat/.env
ExecStart=
ExecStart=$VENV main.py --db $DATA/eltern-chat/conversations.db"

# ---------- Reload + Restart + Health ----------
say "3) daemon-reload + Restart + Health-Check je Dienst (Abbruch bei FAIL)"
systemctl daemon-reload
for s in familie geraete panel plan wetter photo eltern-chat; do systemctl restart "xbuddy-$s"; done
sleep 3
health http://127.0.0.1:5010/api/v1/familie/ familie
health http://127.0.0.1:5040/api/v1/geraete/ geraete
health http://127.0.0.1:5041/api/v1/panels/ panel
health http://127.0.0.1:5020/ plan
health http://127.0.0.1:5030/ wetter
health http://127.0.0.1:5051/ photo
if systemctl is-active --quiet xbuddy-eltern-chat; then echo "  OK  eltern-chat → active"; else echo "  FAIL eltern-chat inaktiv"; exit 1; fi

say "4) effektive ExecStart/Env nach Migration"
for s in familie geraete panel plan wetter photo eltern-chat; do
  echo "--- xbuddy-$s ---"; systemctl show "xbuddy-$s" -p ExecStart -p Environment -p EnvironmentFiles | sed 's/^/  /'
done
echo "FERTIG — Originale im Checkout unangetastet (Rollback möglich)."
