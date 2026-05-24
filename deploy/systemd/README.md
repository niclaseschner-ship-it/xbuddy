# XBuddy systemd — Service-Vorlagen für eine Pi-Instanz

Vorlagen für die `systemd`-Units, die eine XBuddy-Instanz auf einem Pi (oder
einem vergleichbaren Linux-Host) am Leben halten. Sie ergänzen die nginx-
Origin (`deploy/nginx/xbuddy-origin.conf`) um die Komponenten-Prozesse, die
hinter dieser Origin laufen.

Hintergrund: `specs/platform/urls.md` — URL-12 (eine Origin, Routing über
Pfad-Prefix) und URL-14 (Origin-Routing-Tabelle). Die nginx-Conf reverse-
proxyt auf die hier beschriebenen Komponenten.

## Was die Vorlagen tun

| Service | Petrantwortung | Bindet auf |
|---|---|---|
| `xbuddy-router.service` | Router (Display, Controller, generisches API) | `127.0.0.1:5000` |
| `xbuddy-plan.service` | Plan-Buddy (`/display/plan/`, `/api/v1/plan/`) | `127.0.0.1:5020` |
| `xbuddy-familie.service` | Familien-Mit-Host (FAM-7/FAM-8, `/api/v1/familie/`) | `127.0.0.1:5010` |
| `elternchat-bot.service` | Eltern-Chat Telegram-Bot (kein HTTP-Port, geht raus zu Telegram) | — |

Jeder Service bindet ausschließlich auf `127.0.0.1` — von außen erreichbar ist
nur die nginx-Origin auf `:8443` (URL-12). Alle Services laufen mit
`Restart=always` und überleben Reboots, sobald sie `enabled` sind.

## Platzhalter

Die `*.service`-Dateien enthalten Per-Instanz-Werte als Platzhalter im Format
`__NAME__`. Vor `systemctl enable` müssen sie alle ersetzt werden:

| Platzhalter | Bedeutung | Beispiel (Pi-Instanz) |
|---|---|---|
| `__XBUDDY_USER__` | Unprivilegierter Linux-User, unter dem die Services laufen. | `buddy` |
| `__XBUDDY_HOME__` | Home-Verzeichnis dieses Users (`$HOME`). | `/home/buddy` |
| `__XBUDDY_REPO__` | Pfad zum gecheckten xbuddy-Repo auf der Instanz. | `/home/buddy/repos/xbuddy` |
| `__XBUDDY_PYTHON__` | Python-Interpreter mit installierten Repo-Abhängigkeiten. | `/home/buddy/apps/venv/bin/python` |

Wer denselben Stil wie die nginx-Vorlage bevorzugt (`deploy/nginx/README.md`
nennt die Per-Instanz-Pfade exemplarisch): die `__…__`-Platzhalter erzwingen,
dass nichts versehentlich vor dem `cp` als „passt schon" durchgeht — wer einen
Service-File mit `__XBUDDY_REPO__` in `/etc/systemd/system/` ablegt, sieht
sofort, was fehlt.

## Geheimnisse / `EnvironmentFile`

`elternchat-bot.service` verweist auf eine `EnvironmentFile=`-Datei
(`__XBUDDY_REPO__/eltern-chat/.env`), die der Bot beim Start einliest. Diese
Datei **liegt nicht im Repo** — sie enthält Per-Instanz-Geheimnisse (mindestens
den Telegram-Bot-Token, ggf. weitere Eltern-Chat-Konfiguration).

Beim Aufsetzen einer Instanz: die `.env` am genannten Pfad neu erzeugen, mit
mindestens dem Telegram-Bot-Token (`TELEGRAM_BOT_TOKEN=…`). Das exakte Schema
und die optionalen Variablen ergeben sich aus dem `eltern-chat`-Code.

Die übrigen Services haben keine `EnvironmentFile`-Abhängigkeit.

## Ausrollen — einmal pro Instanz

1. **Repo auf der Instanz checken** an den Pfad, den `__XBUDDY_REPO__` benennt;
   Python-Abhängigkeiten in das Venv installieren, das `__XBUDDY_PYTHON__`
   nutzt.

2. **`.env` für den Eltern-Chat-Bot** an `__XBUDDY_REPO__/eltern-chat/.env`
   anlegen (siehe „Geheimnisse").

3. **Vorlagen kopieren und Platzhalter ersetzen.** Beispiel mit `sed`:

   ```bash
   for svc in xbuddy-router xbuddy-plan xbuddy-familie elternchat-bot; do
     sudo sed \
       -e 's|__XBUDDY_USER__|buddy|g' \
       -e 's|__XBUDDY_HOME__|/home/buddy|g' \
       -e 's|__XBUDDY_REPO__|/home/buddy/repos/xbuddy|g' \
       -e 's|__XBUDDY_PYTHON__|/home/buddy/apps/venv/bin/python|g' \
       "deploy/systemd/${svc}.service" \
       | sudo tee "/etc/systemd/system/${svc}.service" >/dev/null
   done
   ```

   Wer die Werte einmal in ein kleines Mapping-Skript packt, vermeidet
   spätere Drift zwischen Repo-Vorlage und Pi-Stand.

4. **Aktivieren und starten:**

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now xbuddy-router.service
   sudo systemctl enable --now xbuddy-plan.service
   sudo systemctl enable --now xbuddy-familie.service
   sudo systemctl enable --now elternchat-bot.service
   ```

5. **Status prüfen** — alle vier müssen `active (running)` melden:

   ```bash
   systemctl status xbuddy-router xbuddy-plan xbuddy-familie elternchat-bot
   ```

## Restart nach Code-Update (Pflicht)

`Restart=always` deckt nur Crashes ab. Ein `git pull` im Repo-Checkout
verändert keinen laufenden Prozess — der Code lebt im RAM. Nach jedem Merge,
der einen Komponenten-Pfad anfasst, gehört der zugehörige Service neu
gestartet, sonst läuft der alte Code weiter und Symptome führen in die Irre.

Zuordnung (analog zur Memory-Notiz `feedback-pi-service-restart`):

| Geänderter Repo-Pfad | Restart |
|---|---|
| `router/` | `sudo systemctl restart xbuddy-router` |
| `plan/` | `sudo systemctl restart xbuddy-plan` |
| `familie/` | `sudo systemctl restart xbuddy-familie` |
| `eltern-chat/` | `sudo systemctl restart elternchat-bot` |
| `deploy/nginx/xbuddy-origin.conf` | `sudo nginx -t && sudo systemctl reload nginx` |

Configs (`routing.json`, `config.json`, `familie.json`, …) zählen wie Code:
sie werden beim Start geladen, kein Hot-Reload (ROU-18). Also auch nach reinen
Config-Änderungen den jeweiligen Service neu starten.

Reihenfolge bei einem Sammel-Pull, der mehrere Komponenten anfasst:
zuerst die unabhängigen Backends (`xbuddy-familie`, `xbuddy-plan`,
`elternchat-bot`), dann der Router (er fasst die anderen über die nginx-Origin
zusammen), zuletzt `nginx reload`, falls die Conf mit angefasst wurde.

Verifikation: `systemctl status <service>` — die `Active: active (running)
since …`-Zeitstempel muss **nach** dem Merge liegen. Wenn nicht: restart vor
allem anderen.
