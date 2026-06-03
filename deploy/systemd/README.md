# XBuddy systemd — Hinweis: Service-Vorlagen leben jetzt neben dem Code

Konvention `conventions/services.md` (SVC-2) verlangt, dass die `.service`-
Vorlage jeder Komponente im Repo **neben dem Code** liegt, unter
`<komponente>/<komponente>.service`. Dieses Verzeichnis hostet deshalb keine
Service-Dateien mehr — es ist Platzhalter für die Installer-Hilfsmittel, die
mit einem Folge-PR landen (siehe „Was hier später wieder landet").

Hintergrund-Kontext (warum es Services gibt, wie sie zur nginx-Origin
passen): `deploy/nginx/xbuddy-origin.conf` und `conventions/urls.md` —
URL-12 (eine Origin, Routing über Pfad-Prefix) und URL-14
(Origin-Routing-Tabelle). Die nginx-Conf reverse-proxyt auf die
Komponenten-Prozesse, die durch diese Services am Leben gehalten werden.

## Wo welche Service-Vorlage liegt

| Service-Name (SVC-1) | Vorlage im Repo (SVC-2) | Verantwortung | Bindet auf |
|---|---|---|---|
| `xbuddy-router.service` | `router/router.service` | Router (Display, Controller, generisches API) | `127.0.0.1:5000` |
| `xbuddy-plan.service` | `plan/plan.service` | Plan-Buddy (`/display/plan/`, `/api/v1/plan/`) | `127.0.0.1:5020` |
| `xbuddy-wetter.service` | `wetter/wetter.service` | Wetter-Buddy (`/display/wetter/`) | `127.0.0.1:5030` |
| `xbuddy-familie.service` | `familie/familie.service` | Familien-Mit-Host (FAM-7/FAM-8, `/api/v1/familie/`) | `127.0.0.1:5010` |
| `xbuddy-geraete.service` | `geraete/geraete.service` | Geräte-Registry (GER-5/GER-6/GER-15) | `127.0.0.1:5040` |
| `xbuddy-eltern-chat.service` | `eltern-chat/eltern-chat.service` | Eltern-Chat Telegram-Bot (kein HTTP-Port, geht raus zu Telegram) | — |

Jeder HTTP-Service bindet ausschließlich auf `127.0.0.1` (PORT-3) — von
außen erreichbar ist nur die nginx-Origin auf `:8443` (URL-12). Alle
Services laufen mit `Restart=on-failure` (SVC-3) und überleben Reboots,
sobald sie `enabled` sind. Logs gehen an stdout/stderr (SVC-4) —
`journalctl -u <service>` ist die Quelle der Wahrheit.

## Platzhalter-Konvention

Die `*.service`-Dateien enthalten Per-Instanz-Werte als Platzhalter im Format
`__NAME__`. Vor `systemctl enable` müssen sie alle ersetzt werden:

| Platzhalter | Bedeutung | Beispiel (Pi-Instanz) |
|---|---|---|
| `__XBUDDY_USER__` | Unprivilegierter Linux-User, unter dem die Services laufen. | `buddy` |
| `__XBUDDY_HOME__` | Home-Verzeichnis dieses Users (`$HOME`). | `/home/buddy` |
| `__XBUDDY_REPO__` | Pfad zum gecheckten xbuddy-Repo auf der Instanz. | `/home/buddy/repos/xbuddy` |
| `__XBUDDY_PYTHON__` | Python-Interpreter mit installierten Repo-Abhängigkeiten. | `/home/buddy/apps/venv/bin/python` |

Die `__…__`-Platzhalter erzwingen, dass nichts versehentlich vor dem `cp`
als „passt schon" durchgeht — wer einen Service-File mit `__XBUDDY_REPO__`
in `/etc/systemd/system/` ablegt, sieht sofort, was fehlt.

## Geheimnisse / `EnvironmentFile`

`eltern-chat/eltern-chat.service` verweist auf eine `EnvironmentFile=`-
Datei (`__XBUDDY_REPO__/eltern-chat/.env`), die der Bot beim Start einliest.
Diese Datei **liegt nicht im Repo** — sie enthält Per-Instanz-Geheimnisse
(mindestens den Telegram-Bot-Token, ggf. weitere Eltern-Chat-Konfiguration).

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
   declare -A SVC_SRC=(
     [xbuddy-router]=router/router.service
     [xbuddy-plan]=plan/plan.service
     [xbuddy-wetter]=wetter/wetter.service
     [xbuddy-familie]=familie/familie.service
     [xbuddy-geraete]=geraete/geraete.service
     [xbuddy-eltern-chat]=eltern-chat/eltern-chat.service
   )
   for svc in "${!SVC_SRC[@]}"; do
     sudo sed \
       -e 's|__XBUDDY_USER__|buddy|g' \
       -e 's|__XBUDDY_HOME__|/home/buddy|g' \
       -e 's|__XBUDDY_REPO__|/home/buddy/repos/xbuddy|g' \
       -e 's|__XBUDDY_PYTHON__|/home/buddy/apps/venv/bin/python|g' \
       "${SVC_SRC[$svc]}" \
       | sudo tee "/etc/systemd/system/${svc}.service" >/dev/null
   done
   ```

   Wer die Werte einmal in ein kleines Mapping-Skript packt, vermeidet
   spätere Drift zwischen Repo-Vorlage und Pi-Stand — genau dieses
   Installer-Skript ist Folge-Ticket (#178b).

4. **Aktivieren und starten:**

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now xbuddy-router.service
   sudo systemctl enable --now xbuddy-plan.service
   sudo systemctl enable --now xbuddy-wetter.service
   sudo systemctl enable --now xbuddy-familie.service
   sudo systemctl enable --now xbuddy-geraete.service
   sudo systemctl enable --now xbuddy-eltern-chat.service
   ```

5. **Status prüfen** — alle Services müssen `active (running)` melden:

   ```bash
   systemctl status xbuddy-router xbuddy-plan xbuddy-wetter xbuddy-familie xbuddy-eltern-chat
   ```

## Restart nach Code-Update (Pflicht)

`Restart=on-failure` deckt nur Crashes ab. Ein `git pull` im Repo-Checkout
verändert keinen laufenden Prozess — der Code lebt im RAM. Nach jedem Merge,
der einen Komponenten-Pfad anfasst, gehört der zugehörige Service neu
gestartet, sonst läuft der alte Code weiter und Symptome führen in die Irre.

Zuordnung (analog zur Memory-Notiz `feedback-pi-service-restart`):

| Geänderter Repo-Pfad | Restart |
|---|---|
| `router/` | `sudo systemctl restart xbuddy-router` |
| `plan/` | `sudo systemctl restart xbuddy-plan` |
| `wetter/` | `sudo systemctl restart xbuddy-wetter` |
| `familie/` | `sudo systemctl restart xbuddy-familie` |
| `geraete/` | `sudo systemctl restart xbuddy-geraete` |
| `eltern-chat/` | `sudo systemctl restart xbuddy-eltern-chat` |
| `deploy/nginx/xbuddy-origin.conf` | `sudo nginx -t && sudo systemctl reload nginx` |

Reihenfolge bei einem Sammel-Pull, der mehrere Komponenten anfasst:
zuerst die unabhängigen Backends (`xbuddy-familie`, `xbuddy-plan`,
`xbuddy-eltern-chat`), dann der Router (er fasst die anderen
über die nginx-Origin zusammen), zuletzt `nginx reload`, falls die Conf mit
angefasst wurde.

Verifikation: `systemctl status <service>` — die `Active: active (running)
since …`-Zeitstempel muss **nach** dem Merge liegen. Wenn nicht: restart vor
allem anderen.

## Was hier später wieder landet

`deploy/systemd/` bleibt als Verzeichnis bestehen für die
**Installer-Hilfsmittel**, die mit einem Folge-PR ankommen (#178b
„Installer + Pfad-Substitution"): ein Skript, das die Vorlagen aus den
Komponenten-Verzeichnissen einsammelt, die `__…__`-Platzhalter aus einer
Instanz-Konfiguration ersetzt und das Ergebnis nach
`/etc/systemd/system/` ablegt. Bis dahin ist das hier reine Doku.
