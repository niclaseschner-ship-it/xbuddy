# XBuddy systemd — Hinweis: Service-Vorlagen leben jetzt neben dem Code

Konvention `conventions/services.md` (SVC-2) verlangt, dass die `.service`-
Vorlage jeder Komponente im Repo **neben dem Code** liegt, unter
`<komponente>/<komponente>.service`. Dieses Verzeichnis hostet deshalb keine
Service-**Dateien** mehr — es hält die Installer-Hilfsmittel (siehe „Was hier
später wieder landet") und seit #1785 die versionierten **Drop-Ins** unter
`xbuddy-<komponente>.service.d/` (siehe „Drop-Ins im Repo").

Hintergrund-Kontext (warum es Services gibt, wie sie zur nginx-Origin
passen): `deploy/nginx/xbuddy-origin.conf` und `conventions/urls.md` —
URL-12 (eine Origin, Routing über Pfad-Prefix) und URL-14
(Origin-Routing-Tabelle). Die nginx-Conf reverse-proxyt auf die
Komponenten-Prozesse, die durch diese Services am Leben gehalten werden.

## Wo welche Service-Vorlage liegt

| Service-Name (SVC-1) | Vorlage im Repo (SVC-2) | Verantwortung | Bindet auf |
|---|---|---|---|
| `xbuddy-plan.service` | `plan/plan.service` | Plan-Buddy (`/display/plan/`, `/api/v1/plan/`) | `127.0.0.1:5020` |
| `xbuddy-wetter.service` | `wetter/wetter.service` | Wetter-Buddy (`/display/wetter/`) | `127.0.0.1:5030` |
| `xbuddy-routine.service` | `routine/routine.service` | Routine-Buddy (`/display/routine/`) | `127.0.0.1:5050` |
| `xbuddy-photo.service` | `photo/photo.service` | Photo-Buddy (`/display/photo/`, `/api/v1/photo/`) | `127.0.0.1:5051` |
| `xbuddy-familie.service` | `familie/familie.service` | Familien-Mit-Host (FAM-7/FAM-8, `/api/v1/familie/`) | `127.0.0.1:5010` |
| `xbuddy-seiten.service` | `seiten/seiten.service` | Seiten-Registry (SREG-3, `GET /api/v1/seiten`) | `127.0.0.1:5042` |
| `xbuddy-panel.service` | `panel/panel.service` | Panel-Registry (PREG-13/PREG-14/PREG-15, `GET /api/v1/panels`) | `127.0.0.1:5041` |
| `xbuddy-essen.service` | `essen/essen.service` | Essens-Buddy (`/display/essen/`, `/api/v1/essen/`, ESSEN-23) | `127.0.0.1:5052` |
| `xbuddy-eltern-chat.service` | `eltern-chat/eltern-chat.service` | Eltern-Chat Telegram-Bot (kein HTTP-Port, geht raus zu Telegram) | — |
| `xbuddy-hoerspiel.service` | `hoerspiel/hoerspiel.service` | Hörspiel-Buddy für Mia (`/display/hoerspiel/mia/`, `/api/v1/hoerspiel/mia/`) | `127.0.0.1:5053` |
| `xbuddy-hoerspiel-finn.service` | `hoerspiel/hoerspiel-finn.service` | Hörspiel-Buddy für Finn (`/display/hoerspiel/finn/`, `/api/v1/hoerspiel/finn/`) | `127.0.0.1:5055` |
| `xbuddy-kibuddy.service` | `kibuddy/kibuddy.service` | KI-Buddy (KIBUDDY-21, `/api/v1/kibuddy/`, OpenAI/Anthropic-LLM-Integration) | `127.0.0.1:5054` |

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
| `__XBUDDY_DATA__` | Wurzel der Per-Instanz-Daten außerhalb des Checkouts (SVC-5). | `/home/buddy/xbuddy-data` |
| `__XBUDDY_DISPLAY_ORIGIN_HEIM__` | Heimnetz-Origin für Display-URLs (SREG-7: eine Origin, Routing im Router). | `https://xbuddy-hub.local:8443` |
| `__XBUDDY_DISPLAY_ORIGIN_TAILSCALE__` | Tailscale-Origin für Display-URLs (SREG-7: 4-Segment-Form, tauscht Platzhalter in Tailnet-Slug). | `https://xbuddy-hub.tailnet-xxxx.ts.net:8443` |
| `__XBUDDY_DISPLAY_ORIGIN_FUNNEL__` | Funnel-FQDN mit LE-Cert für Familien-User-Geräte (SREG-7, AUTH-7b). Leer = kein externer User-Geräte-Zugang (SEITEN_FUNNEL_ORIGIN). | `https://buddyboard.<tailscale-id>.ts.net` |

Die `__…__`-Platzhalter erzwingen, dass nichts versehentlich vor dem `cp`
als „passt schon" durchgeht — wer einen Service-File mit `__XBUDDY_REPO__`
in `/etc/systemd/system/` ablegt, sieht sofort, was fehlt.

## Geheimnisse / `EnvironmentFile`

`eltern-chat/eltern-chat.service` verweist auf eine `EnvironmentFile=`-
Datei (`__XBUDDY_DATA__/eltern-chat/.env`), die der Bot beim Start einliest.
Diese Datei **liegt nicht im Repo**, sondern unter der Per-Instanz-Datenwurzel
(SVC-5) — sie enthält Per-Instanz-Geheimnisse (mindestens den Telegram-Bot-Token,
ggf. weitere Eltern-Chat-Konfiguration).

Beim Aufsetzen einer Instanz: die `.env` am genannten Pfad neu erzeugen, mit
mindestens dem Telegram-Bot-Token (`TELEGRAM_BOT_TOKEN=…`). Das exakte Schema
und die optionalen Variablen ergeben sich aus dem `eltern-chat`-Code.

Die übrigen Services ohne Bot-Token-Bedarf haben keine `EnvironmentFile`-Abhängigkeit.
`seiten` und `essen` lesen die Token-Datei über Token-Sharing (siehe unten).

### KIBuddy-Geheimnisse (KIBUDDY-21, T1082)

`xbuddy-kibuddy` zieht seine Geheimnisse aus zwei Quellen, beide außerhalb des
Checkouts (SVC-5):

1. **ENV-Datei** `__XBUDDY_DATA__/zugangsdaten/kibuddy-env` (STT/TTS/Azure-Keys),
   erzeugt von `tools/sync_kibuddy_env.py` und via Drop-In `10-secrets.conf`
   geladen.
2. **LLM-Provider-Key** über den `tools.llm`-Slot `kibuddy-anthropic-api-key`,
   den dasselbe Skript in den **Per-Instanz-Zugangsdaten-Store** spiegelt
   (`__XBUDDY_DATA__/zugangsdaten/zugangsdaten.json`).

`tools.llm` löst den Store über `resolve_store_path()` auf; der ZD-8-Default ist
nur der **Code-Fallback** im Checkout. Der **Live-Ort** liegt nach SVC-5 außerhalb
des Checkouts — die Unit setzt den Pfad per Override-Variable (analog Router/ROU-18):

```ini
# 30-zugangsdaten-path.conf
[Service]
Environment=ZUGANGSDATEN_STORE_FILE=__XBUDDY_DATA__/zugangsdaten/zugangsdaten.json
```

Deploy-Reihenfolge: `python3 -m tools.sync_kibuddy_env` (schreibt ENV-Datei +
Slot) → `daemon-reload` → `systemctl restart xbuddy-kibuddy`. Ohne den Slot wirft
der erste Kind-Call `LLMCapabilityError`.

> Dies ist das ratifizierte SVC-5-Muster (Live-Daten außerhalb des Checkouts,
> Unit setzt den Pfad), **nicht** kibuddy-spezifisch und keine offene Frage:
> `xbuddy-eltern-chat` fährt seit jeher denselben Override (Drop-In
> `20-zugangsdaten.conf`). Jeder Service, der den Zugangsdaten-Store für
> Live-Geheimnisse liest, bekommt dieses Drop-In.

## Token-Sharing (Mini-App-Auth, RAT-16 / #684)

Der Telegram-Bot-Token liegt physisch in `__XBUDDY_DATA__/eltern-chat/.env` —
Eigentümer ist der **eltern-chat**-Service. Damit `seiten` und `essen` die
Telegram-`initData`-Signatur prüfen können (Mini-App-Auth), lesen sie dieselbe
Datei über `EnvironmentFile=`:

```ini
EnvironmentFile=__XBUDDY_DATA__/eltern-chat/.env
```

Token NICHT in zusätzliche Per-Service-`.env`-Dateien duplizieren — Eigentum
bleibt klar.

## Ausrollen — einmal pro Instanz

1. **Repo auf der Instanz checken** an den Pfad, den `__XBUDDY_REPO__` benennt;
   Python-Abhängigkeiten in das Venv installieren, das `__XBUDDY_PYTHON__`
   nutzt. Der EINE Dependency-SSoT ist `pyproject.toml` (RAT-33 Option A,
   #1534) — installiert wird repo-weit daraus:

   ```bash
   /home/buddy/apps/venv/bin/pip install /home/buddy/repos/xbuddy
   ```

   Denselben Schritt fährt der Deploy-Regelkreis bei jedem Vollauf automatisch
   (`deploy/update.sh` → `sync_deps`, VOR den Restarts), sodass neu gestartete
   Services neue/geänderte Deps direkt sehen. Es gibt KEINE per-Service-
   `requirements.txt` mehr (Hand-Pflege-Divergenz war die #1515-Klasse).

2. **`.env` für den Eltern-Chat-Bot** an `__XBUDDY_DATA__/eltern-chat/.env`
   anlegen (siehe „Geheimnisse").

3. **Vorlagen kopieren und Platzhalter ersetzen.** Beispiel mit `sed`:

   ```bash
   declare -A SVC_SRC=(
     [xbuddy-plan]=plan/plan.service
     [xbuddy-wetter]=wetter/wetter.service
     [xbuddy-routine]=routine/routine.service
     [xbuddy-photo]=photo/photo.service
     [xbuddy-familie]=familie/familie.service
     [xbuddy-seiten]=seiten/seiten.service
     [xbuddy-panel]=panel/panel.service
     [xbuddy-essen]=essen/essen.service
     [xbuddy-eltern-chat]=eltern-chat/eltern-chat.service
   )
   for svc in "${!SVC_SRC[@]}"; do
     sudo sed \
       -e 's|__XBUDDY_USER__|buddy|g' \
       -e 's|__XBUDDY_HOME__|/home/buddy|g' \
       -e 's|__XBUDDY_REPO__|/home/buddy/repos/xbuddy|g' \
       -e 's|__XBUDDY_PYTHON__|/home/buddy/apps/venv/bin/python|g' \
       -e 's|__XBUDDY_DATA__|/home/buddy/xbuddy-data|g' \
       -e 's|__XBUDDY_DISPLAY_ORIGIN_HEIM__|https://xbuddy-hub.local:8443|g' \
       -e 's|__XBUDDY_DISPLAY_ORIGIN_TAILSCALE__|https://xbuddy-hub.tailnet-xxxx.ts.net:8443|g' \
       -e 's|__XBUDDY_DISPLAY_ORIGIN_FUNNEL__|https://buddyboard.<tailscale-id>.ts.net|g' \
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
   sudo systemctl enable --now xbuddy-plan.service
   sudo systemctl enable --now xbuddy-wetter.service
   sudo systemctl enable --now xbuddy-routine.service
   sudo systemctl enable --now xbuddy-photo.service
   sudo systemctl enable --now xbuddy-familie.service
   sudo systemctl enable --now xbuddy-seiten.service
   sudo systemctl enable --now xbuddy-panel.service
   sudo systemctl enable --now xbuddy-essen.service
   sudo systemctl enable --now xbuddy-eltern-chat.service
   ```

5. **Status prüfen** — alle Services müssen `active (running)` melden:

   ```bash
   systemctl status xbuddy-plan xbuddy-wetter xbuddy-routine xbuddy-photo xbuddy-familie xbuddy-seiten xbuddy-panel xbuddy-essen xbuddy-eltern-chat
   ```

## Drop-Ins im Repo (#1785)

Die Basis-Unit einer Komponente liegt neben dem Code (SVC-2). **Drop-Ins**
(`/etc/systemd/system/<service>.service.d/*.conf`) ergänzen sie pro Instanz und
lagen bisher **nur** am Pi — was nur in `/etc` steht, kommt nicht in eine andere
Familie (Drift-Schutz, SVC-2). Deshalb leben versionierte Drop-Ins ab #1785 hier:

| Drop-In im Repo | Ziel auf der Instanz | Zweck |
|---|---|---|
| `deploy/systemd/xbuddy-plan.service.d/memory.conf` | `/etc/systemd/system/xbuddy-plan.service.d/memory.conf` | Speicher-Notbremse (`MemoryHigh`, `OOMScoreAdjust`) |
| `deploy/systemd/xbuddy-familie.service.d/memory.conf` | `/etc/systemd/system/xbuddy-familie.service.d/memory.conf` | Speicher-Notbremse (`MemoryHigh`, `OOMScoreAdjust`) |
| `deploy/systemd/xbuddy-plan.service.d/restart-window.conf` | `/etc/systemd/system/xbuddy-plan.service.d/restart-window.conf` | Neustart-Bremse (`StartLimitIntervalSec`, `StartLimitBurst`) — #1801 |
| `deploy/systemd/xbuddy-familie.service.d/restart-window.conf` | `/etc/systemd/system/xbuddy-familie.service.d/restart-window.conf` | Neustart-Bremse (`StartLimitIntervalSec`, `StartLimitBurst`) — #1801 |

Alle vier Drop-Ins enthalten **keine** `__XBUDDY_*__`-Platzhalter: ihre Werte
sind host-unabhängig. Der `sed`-Schritt aus „Ausrollen" entfällt für sie —
`cp` genügt.

Zwei bekannte Abweichungen, absichtlich so gelassen und hier notiert statt
still gefixt:

- **Datei-Name ohne Zahlen-Präfix.** Die am Pi hand-gepflegten Drop-Ins heißen
  `10-data-path.conf`, `20-eltern-token.conf`, `40-auth-token.conf`.
  `memory.conf` sortiert alphabetisch **hinter** allen Ziffern, lädt also
  zuletzt — unschädlich, weil es keinen Schlüssel mit den anderen teilt. Eine
  Umbenennung auf `50-memory.conf` wäre die konsequente Form (Folge-Ticket).
- **`deploy/bootstrap.sh` rollt Drop-Ins nicht aus.** Das Skript kennt nur die
  `SVC_SRC`-Map der Basis-Units. Drop-Ins gehen deshalb bis auf Weiteres den
  manuellen Weg unten. Das ist dasselbe Muster, mit dem `bootstrap.sh` schon
  `nginx` behandelt (BOOT-3: bewusst außerhalb, dokumentierter Hand-Schritt) —
  **aber aus einem anderen Grund**: nginx ist ausgeschlossen, weil ein
  Automatik-Zugriff dort schon Schaden angerichtet hat (T966); Drop-Ins sind
  nur noch nicht angebunden. Sie in `bootstrap.sh` aufzunehmen ist erwünscht
  und Folge-Ticket, nicht verboten.

### Ausrollen der Speicher-Notbremse — Reihenfolge

Reihenfolge ist nicht beliebig: erst die Unit-Definition prüfen, dann laden,
dann anwenden, dann belegen. Ein `daemon-reload` auf einer driftenden Unit kann
den Dienst kippen — deshalb Schritt 1 zuerst.

1. **Drift-Check vor allem anderen.** Vergleiche das effektive `ExecStart` der
   Live-Unit mit der `argparse`-Signatur des Dienstes:

   ```bash
   systemctl cat xbuddy-plan.service xbuddy-familie.service | grep -n 'ExecStart\|Restart='
   grep -n 'add_argument' plan/main.py familie/main.py
   ```

   Jedes `--flag` im `ExecStart` muss in `parse_args()` existieren. Weicht etwas
   ab: **stopp**, erst die Unit richten. (Stand 2026-08-10: die Live-`ExecStart`
   beider Dienste sind argparse-konform. Die *Repo-Vorlagen* driften — siehe
   „Bekannte Vorlagen-Drift" unten.)

2. **Drop-Ins kopieren.** Kein `sed`, keine Platzhalter:

   ```bash
   for svc in xbuddy-plan xbuddy-familie; do
     sudo install -d -m 0755 "/etc/systemd/system/${svc}.service.d"
     sudo install -m 0644 "deploy/systemd/${svc}.service.d/memory.conf" \
       "/etc/systemd/system/${svc}.service.d/memory.conf"
   done
   ```

3. **Unit-Definition neu einlesen.** `daemon-reload` allein wendet
   `MemoryHigh`/`OOMScoreAdjust` noch **nicht** auf den laufenden Prozess an:

   ```bash
   sudo systemctl daemon-reload
   ```

4. **Anwenden.** `MemoryHigh` lässt sich live nachziehen, `OOMScoreAdjust` nicht
   — das ist eine Prozess-Eigenschaft und braucht einen neuen Prozess:

   ```bash
   sudo systemctl restart xbuddy-plan.service xbuddy-familie.service
   ```

5. **Live belegen** (Abnahme-Kriterium des Tickets):

   ```bash
   systemctl show -p MemoryHigh -p OOMScoreAdjust -p MemoryCurrent \
     xbuddy-plan.service xbuddy-familie.service
   ```

   Erwartet: `MemoryHigh=134217728` (= 128M) und `OOMScoreAdjust=-500` für
   beide. `MemoryCurrent` muss deutlich darunter liegen (~30M) — läge es an der
   Grenze, wäre der Grenzwert falsch gewählt.

6. **Nachkontrolle nach ein paar Tagen** — hat die Bremse je gegriffen?

   ```bash
   grep '^high' /sys/fs/cgroup/system.slice/xbuddy-plan.service/memory.events \
                /sys/fs/cgroup/system.slice/xbuddy-familie.service/memory.events
   ```

   `high 0` heißt: nie gedrosselt, der Grenzwert stört den Normalbetrieb nicht.
   Ein steigender Zähler ist das erste echte Leck-Signal — und der Punkt, an dem
   die Ursachen-Suche im Anwendungscode anfängt.

Rollback ist symmetrisch: Drop-In löschen, `daemon-reload`, `restart`.

### Ausrollen der Neustart-Bremse — Reihenfolge (#1801)

Selbe Reihenfolge-Logik wie oben: erst prüfen, dann laden, dann anwenden,
dann belegen. `StartLimitIntervalSec`/`StartLimitBurst` sind reine
Unit-Direktiven — sie brauchen keinen Prozess-Neustart, ein `daemon-reload`
reicht, den Zähler auf den neuen Wert umzustellen. Alle Befehle mit
repo-relativen Pfaden (`deploy/systemd/...`) laufen aus dem Wurzelverzeichnis
des Checkouts (`__XBUDDY_REPO__`, z. B. `/home/buddy/repos/xbuddy` — siehe
Platzhalter-Tabelle oben), nicht aus `deploy/systemd/` selbst.

1. **Drift-Check vor allem anderen** (identisch zum Speicher-Abschnitt oben,
   hier wichtiger: Schritt 3 verlangt gleich einen vorgeführten Crash-Loop,
   und genau dort wird eine `ExecStart`-Drift scharf — ein umgebogener
   `ExecStart` auf einer bereits driftenden Unit testet die falsche Sache).
   Vergleiche das effektive `ExecStart` der Live-Unit mit der
   `argparse`-Signatur des Dienstes:

   ```bash
   systemctl cat xbuddy-plan.service xbuddy-familie.service | grep -n 'ExecStart\|Restart='
   grep -n 'add_argument' plan/main.py familie/main.py
   ```

   Jedes `--flag` im `ExecStart` muss in `parse_args()` existieren. Weicht
   etwas ab: **stopp**, erst die Unit richten. (Stand 2026-08-10: die
   Live-`ExecStart` beider Dienste sind argparse-konform — siehe „Bekannte
   Vorlagen-Drift" unten für die *Repo-Vorlagen*-Drift, die unabhängig davon
   bekannt und unbehoben ist.)

2. **Drop-Ins kopieren** (Arbeitsverzeichnis: Repo-Root):

   ```bash
   for svc in xbuddy-plan xbuddy-familie; do
     sudo install -d -m 0755 "/etc/systemd/system/${svc}.service.d"
     sudo install -m 0644 "deploy/systemd/${svc}.service.d/restart-window.conf" \
       "/etc/systemd/system/${svc}.service.d/restart-window.conf"
   done
   sudo systemctl daemon-reload
   ```

3. **Live belegen** (Abnahme-Kriterium des Tickets):

   ```bash
   systemctl show -p Restart -p RestartUSec -p StartLimitIntervalUSec \
     -p StartLimitBurst xbuddy-plan.service xbuddy-familie.service
   ```

   Erwartet: `StartLimitIntervalUSec=2min` (= 120s), `StartLimitBurst=5`,
   `RestartUSec=10s` für beide. Vor dem Rollout (Stand 2026-08-17, gemessen
   für dieses Ticket) zeigte derselbe Befehl `StartLimitIntervalUSec=10s`
   (systemd-Default, ungesetzt) — identisch mit `RestartUSec`, die Bremse
   konnte nie greifen.

4. **Vorgeführt, nicht gerechnet** (Abnahme verlangt einen vorgeführten
   Dauerabsturz, kein Papier-Beweis): einen künstlichen Crash-Loop erzeugen
   (z. B. `ExecStart` kurzzeitig auf einen sofort abstürzenden Befehl setzen
   oder den Prozess wiederholt `kill -SEGV` schicken) und beobachten, dass
   systemd nach dem fünften Versuch **innerhalb** von 120s mit
   `start-limit-hit` stoppt:

   ```bash
   journalctl -u xbuddy-plan -f
   # erwartete Zeile: "... start request repeated too quickly, refusing to start."
   systemctl status xbuddy-plan   # Active: failed (Result: start-limit-hit)
   ```

   Reset danach: `sudo systemctl reset-failed xbuddy-plan xbuddy-familie`.

Rollback ist symmetrisch: Drop-In löschen, `daemon-reload`.

### Bekannte Vorlagen-Drift (Stand 2026-08-10, #1785)

Diese Abweichungen sind **gemeldet, nicht gefixt** — sie zu ändern gehört in ein
eigenes Ticket, weil `bootstrap.sh` die Basis-Units überschreibt und das jeden
Live-Dienst anfasst:

| Ort | Repo-Vorlage | Live in `/etc` | Wirkung |
|---|---|---|---|
| `familie/familie.service` → `ExecStart` | ohne `--host`/`--port` | `--host 127.0.0.1 --port 5010` | Harmlos: `familie/main.py` `RUNTIME_SCHEMA` hat genau diese Werte als Default. Trotzdem Drift. |
| `familie/familie.service` → `--registry` | `__XBUDDY_REPO__/familie/familie.json` (**im Checkout**) | `__XBUDDY_DATA__/familie/familie.json` (per Drop-In `10-data-path.conf`) | Die Vorlage verletzt SVC-5; live rettet das nur ein Drop-In mit `ExecStart=`-Reset. |
| `plan/plan.service` → `EnvironmentFile` | inline in der Vorlage | per Drop-In `20-eltern-token.conf` | Doppelter Ort für dieselbe Zuweisung. |
| beide → `Restart=` | `on-failure` (SVC-3-konform) | `always` (hand-editiert) | Siehe SVC-3 in `conventions/services.md`. Die Drift lebt **nur** in `/etc`; ein `bootstrap.sh`-Lauf würde sie von allein beseitigen. Für #1801 re-verifiziert (2026-08-17): `systemctl show xbuddy-plan xbuddy-familie -p Restart` zeigt weiterhin `always` auf beiden. |

## Restart nach Code-Update (Pflicht)

`Restart=on-failure` deckt nur Crashes ab. Ein `git pull` im Repo-Checkout
verändert keinen laufenden Prozess — der Code lebt im RAM. Nach jedem Merge,
der einen Komponenten-Pfad anfasst, gehört der zugehörige Service neu
gestartet, sonst läuft der alte Code weiter und Symptome führen in die Irre.

Zuordnung (analog zur Memory-Notiz `feedback-pi-service-restart`):

| Geänderter Repo-Pfad | Restart |
|---|---|
| `plan/` | `sudo systemctl restart xbuddy-plan` |
| `wetter/` | `sudo systemctl restart xbuddy-wetter` |
| `routine/` | `sudo systemctl restart xbuddy-routine` |
| `photo/` | `sudo systemctl restart xbuddy-photo` |
| `familie/` | `sudo systemctl restart xbuddy-familie` |
| `seiten/` oder ein `views.json`-Manifest | `sudo systemctl restart xbuddy-seiten` |
| `panel/` oder ein `panels.json`-Manifest | `sudo systemctl restart xbuddy-panel` |
| `essen/` | `sudo systemctl restart xbuddy-essen` |
| `eltern-chat/` | `sudo systemctl restart xbuddy-eltern-chat` |
| `hoerspiel/` (Repo-Code, shared zwischen Instanzen) | `sudo systemctl restart xbuddy-hoerspiel && sudo systemctl restart xbuddy-hoerspiel-finn` |
| `kibuddy/` | `sudo systemctl restart xbuddy-kibuddy` |
| `deploy/nginx/xbuddy-origin.conf` | `sudo nginx -t && sudo systemctl reload nginx` |

**Hörspiel n-Instanz-Realität (RAT-17, `decisions/RAT-17-907-hoerbuchbuddy-n-instanzen.md`; PW-58 V1, ENTSCHEID-File `brainstorm/berater-runde/20260617-2330-RATIFIZIERT-pw58-pw52-disziplin-mechanik-katalog.md` Sektion „R2-Empfehlung → Fall 1 Schritt 1" mit Codex-Pass-2-Korrektur):**

Mia und Finn sind getrennte Services (`conventions/ports.md:25-27`, `conventions/urls.md:207-208`). **Kind-spezifische Daten liegen NICHT im Repo**, sondern unter `xbuddy-data/hoerspiel/<kind_id>/` (`specs/buddies/hoerspiel.md:751-820`). Ein `git pull` sieht diese Daten nie — alle `hoerspiel/`-Repo-Touches sind per Definition Shared-Code und brauchen **BEIDE Services** neu gestartet.

Eine frühere Idee, anhand des Pfad-Segments (`hoerspiel/config/mia.json`) zwischen Mia-only und Finn-only zu unterscheiden, wurde mit dem ratifizierten Stand verworfen: solche Pfade existieren im Repo nicht, und Datei-Namen mit „mia"/„finn" (Tests, CSS-Klassen, Mocks) sind selten kind-exklusiv. Reine Pfad-Segment-Heuristik wäre fragil — daher BEIDE bei jedem Repo-Diff unter `hoerspiel/`.

Reihenfolge bei einem Sammel-Pull, der mehrere Komponenten anfasst:
zuerst die unabhängigen Backends (`xbuddy-familie`, `xbuddy-plan`,
`xbuddy-eltern-chat`), zuletzt `nginx reload`, falls die Conf mit
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
