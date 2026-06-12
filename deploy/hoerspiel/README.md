# Hörspiel-Buddy — Deploy-Anleitung

Einmaliger Aufbau auf der Pi-Instanz. Alle Befehle als User `buddy`, außer den
`sudo`-Schritten.

## 1. Service-Vorlage einrichten

```bash
sudo cp hoerspiel/hoerspiel.service /etc/systemd/system/xbuddy-hoerspiel.service
# Platzhalter ersetzen (analog deploy/systemd/README.md):
sudo sed -i \
  -e 's|__XBUDDY_USER__|buddy|g' \
  -e 's|__XBUDDY_HOME__|/home/buddy|g' \
  -e 's|__XBUDDY_REPO__|/home/buddy/repos/xbuddy|g' \
  -e 's|__XBUDDY_PYTHON__|/home/buddy/apps/venv/bin/python|g' \
  -e 's|__XBUDDY_DATA__|/home/buddy/xbuddy-data|g' \
  /etc/systemd/system/xbuddy-hoerspiel.service
```

## 2. Secrets-Drop-In einrichten

```bash
sudo mkdir -p /etc/systemd/system/xbuddy-hoerspiel.service.d/
sudo cp deploy/hoerspiel/10-secrets.conf \
    /etc/systemd/system/xbuddy-hoerspiel.service.d/10-secrets.conf
```

## 3. ENV-Datei aus zugangsdaten.json erzeugen

```bash
python3 tools/sync_hoerspiel_env.py
```

Erzeugt `/home/buddy/xbuddy-data/zugangsdaten/hoerspiel-env` (Permissions 600)
aus den Keys `hoerspiel-*` in `zugangsdaten.json` (HSP-27).

## 4. Datenwurzel vorbereiten

```bash
bash deploy/hoerspiel/bootstrap.sh
```

Legt `/home/buddy/xbuddy-data/hoerspiel/data/` mit Unterverzeichnissen, Bible,
Folgen-Historie, Default-Cover und Intro/Outro-Reimen an (idempotent, HSP-25).

## 5. Service aktivieren

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xbuddy-hoerspiel
```

## 6. Eltern-Chat neu starten (HFE-Skill laden)

```bash
sudo systemctl restart xbuddy-eltern-chat
```

## 7. nginx neu laden (neuer Origin-Block)

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## Smoke-Tests

```bash
# Hörspiel-Buddy Health
curl -sk https://192.0.2.10:8443/api/v1/hoerspiel/config | python3 -m json.tool

# Display-View erreichbar
curl -sk -o /dev/null -w "%{http_code}" https://192.0.2.10:8443/display/hoerspiel/

# Service-Status
systemctl status xbuddy-hoerspiel xbuddy-eltern-chat
```
