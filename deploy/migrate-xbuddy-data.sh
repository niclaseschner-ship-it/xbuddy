#!/usr/bin/env bash
# PW-6 Etappe 1 — Instanz-Daten aus dem Checkout nach /home/buddy/xbuddy-data/ herauslösen.
# cp (nicht mv) → Originale bleiben, Rollback = Drop-in entfernen + restart.
# Nur die 7 voll override-fähigen Dienste. router/zugangsdaten/routine_store = Code-Folge.
set -euo pipefail
REPO=/home/buddy/repos/xbuddy
DATA=/home/buddy/xbuddy-data
DROP=/etc/systemd/system
VENV=/home/buddy/apps/venv/bin/python

say(){ echo "==== $* ===="; }
health(){ # $1=url $2=name
  code=$(curl -sL -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo 000)
  if [[ "$code" =~ ^(200|301|302|308|404)$ ]]; then echo "  OK  $2 → HTTP $code"; else echo "  FAIL $2 → HTTP $code"; return 1; fi
}
dropin(){ # $1=service  $2=conf-body
  mkdir -p "$DROP/$1.service.d"
  printf '%s\n' "$2" > "$DROP/$1.service.d/10-data-path.conf"
}

# ---------- Daten kopieren ----------
say "1) Daten kopieren (cp -p, Verzeichnisse -r)"
mkdir -p "$DATA"/{familie,geraete,panel,plan,wetter,photo,eltern-chat}
cp -p  "$REPO/familie/familie.json"            "$DATA/familie/familie.json"
cp -rp "$REPO/familie/fotos/."                 "$DATA/familie/fotos/" 2>/dev/null || mkdir -p "$DATA/familie/fotos"
cp -p  "$REPO/geraete/geraete.json"            "$DATA/geraete/geraete.json"
cp -p  "$REPO/panel/panels.json"               "$DATA/panel/panels.json"
cp -p  "$REPO/plan/plan.json"                  "$DATA/plan/plan.json"
cp -p  "$REPO/plan/plan.db"                    "$DATA/plan/plan.db"
cp -p  "$REPO/wetter/wetter.json"              "$DATA/wetter/wetter.json"
mkdir -p "$DATA/photo/medien"; cp -rp "$REPO/photo/medien/." "$DATA/photo/medien/" 2>/dev/null || true
cp -p  "$REPO/eltern-chat/.env"                "$DATA/eltern-chat/.env"
cp -p  "$REPO/eltern-chat/conversations.db"    "$DATA/eltern-chat/conversations.db"
chmod 600 "$DATA/eltern-chat/.env" "$DATA/familie/familie.json" "$DATA/geraete/geraete.json" "$DATA/panel/panels.json" "$DATA/plan/plan.json" "$DATA/wetter/wetter.json" 2>/dev/null || true
echo "  kopiert."

# ---------- Drop-ins ----------
say "2) systemd Drop-ins schreiben (ExecStart-Override / Environment / EnvironmentFile)"
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
echo "  geschrieben."

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
