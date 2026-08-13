# Services — Konvention     (ID-Präfix: SVC)

XBuddy-Komponenten laufen auf dem Hub als systemd-Services. Diese
Konvention legt fest, wie ein Service strukturiert ist und wo seine
Definition lebt — damit eine neue Familie (Familie 3, 4, …) die
Services ohne Hand-Verdrahtung übernehmen kann.

### SVC-1 — Service-Name folgt `xbuddy-<komponente>.service`
Jeder Service heißt `xbuddy-<komponente>.service`
(z. B. `xbuddy-plan.service`, `xbuddy-eltern-chat.service`).
Das `xbuddy-`-Präfix macht klar, wessen Komponente das ist, und vermeidet
Namensraum-Kollisionen mit anderen Diensten am Heim-Server.

Bestehende Services ohne Präfix (`elternchat-bot.service`, `wetter.service`)
sind Drift und werden in einer Migrationsrunde angeglichen
(Folge-Ticket).

### SVC-2 — Service-Datei lebt im Repo, neben dem Code
Die `.service`-Datei jeder Komponente liegt im Repo unter
`<komponente>/<komponente>.service`. Der Installer-Schritt verlinkt sie
nach `/etc/systemd/system/` und ersetzt instanz-abhängige Pfade
(siehe Folge-Ticket „Installer + Pfad-Substitution").

Drift-Schutz: was nur am Pi steht und nicht im Repo, kommt nicht in eine
andere Familie.

### SVC-3 — Restart-Strategie ist `Restart=on-failure`
Jeder Service hat `Restart=on-failure` (nicht `always`). Crashes sollen
erkannt und beobachtbar bleiben; eine Endlosschleife aus Restart maskiert
echte Fehler. Wer aus gutem Grund anders entscheiden will, dokumentiert
das in der Komponenten-Spec.

**Klarstellung (#1785): „der Dienst kann per OOM sterben" ist KEIN Grund für
`always`.** `on-failure` deckt Signal-Tode bereits ab — ein OOM-Kill ist
`SIGKILL` (`status=9/KILL`), ein Segfault ist `SIGSEGV` (`status=11/SEGV`), und
systemd zählt beide als `Result=signal`, also als *failure*. Der **einzige**
Unterschied von `always` ist der Neustart nach einem **sauberen** `exit 0` — und
genau der ist der Fall, in dem ein Restart einen echten Bug verdeckt: ein
HTTP-Service, der sich freiwillig beendet, hat einen Grund dazu, und den will man
sehen. `always` kauft für den OOM-Fall nichts und kostet Beobachtbarkeit.

Live-Beleg für die Kosten: `xbuddy-plan` und `xbuddy-familie` trugen am Pi
hand-editiert `always`, ohne Begründung an irgendeiner Stelle. Am 2026-08-10
starben beide 14× hintereinander mit `SIGSEGV`, sofort beim Start, im
`RestartSec=10`-Takt — eine Endlosschleife, die niemandem auffiel, weil
`RestartSec` größer ist als das `StartLimitIntervalSec`-Fenster und die
Rate-Begrenzung deshalb nie greift. Genau das Maskieren, das SVC-3 verhindern
soll.

**Verdikt: keine Ausnahme.** Die Abweichung wird auf SVC-3 zurückgeführt; die
Repo-Vorlagen (`plan/plan.service`, `familie/familie.service`) sagen ohnehin
schon `on-failure`, die Drift lebt nur in `/etc`. Wer künftig `always` will,
braucht einen Grund, der über „stirbt manchmal" hinausgeht — und trägt ihn nach
SVC-3 Satz 3 in die Komponenten-Spec ein, nicht in eine `/etc`-Datei.

Ergänzend gehört zu einem Dienst, der unbeaufsichtigt neu startet, eine
**Speicher-Obergrenze**, damit ein Restart-Zyklus nicht den Host mitnimmt: die
gemessene Herleitung und der Ausroll-Weg dieser Grenzwerte stehen in
`deploy/systemd/README.md` („Drop-Ins im Repo"). Bewusst **keine** eigene
Convention-ID — bei n=2 Diensten wäre das eine Vorrats-Konvention (CLAUDE.md §6);
sobald ein dritter Dienst dieselbe Bremse braucht, ist der Moment für eine
SVC-Regel gekommen.

### SVC-4 — Logs gehen an stdout/stderr, nicht in Dateien
Service-Code loggt nach stdout/stderr. `journalctl -u <service>` ist die
Quelle der Wahrheit für Logs — keine Datei-Logs nebenher. Log-Format
selbst legt `conventions/logging.md` fest (Folge-Konvention).

### SVC-5 — Instanz-Daten leben außerhalb des Checkouts
Die per-Instanz-Daten eines Service (Registry-/Config-JSON, DB, Profilfotos,
Medien, `.env`) liegen **nicht** im Code-Checkout, sondern unter
`/home/buddy/xbuddy-data/<komponente>/`. Der Service zeigt per **absolutem
Pfad** dorthin — über die schon vorhandene `<KOMPONENTE>_*`-Env-Variable
(`Environment=` in der Unit, z. B. `PLAN_DB_DATEI`, `WETTER_CONFIG_FILE`,
`PHOTO_LIBRARY_VERZEICHNIS`, `ROUTINE_DATA_FILE`) oder per CLI-Arg
(`--registry`/`--geraete`/`--panels`/`--db`). Das ist die in SVC-2 vorgesehene
„Pfad-Substitution durch den Installer". Code-Defaults (`HERE/…`, CWD) bleiben
nur Fallback (CLAUDE.md §6), sind aber nie der Live-Ort.

Begründung: Der Checkout ist Dev-Root **und** Service-CWD zugleich; liegen die
Live-Daten darin, koppeln sie an Branch-Stand und blockieren das Entkoppeln von
Code und Release (PW-6/RAT-14). Daten außerhalb des Checkouts machen Branch-Flips
und einen späteren Release-Checkout (Etappe 2) gefahrlos.

Migration ist additiv-rückrollbar: Daten per `cp` (nicht `mv`) nach
`xbuddy-data/`, Unit umhängen, Service-für-Service am Live-Verhalten verifizieren,
**dann erst** die Alt-Datei im Checkout entfernen. Komponenten ohne Pfad-Override
(heute `router`/routing.json, `tools/zugangsdaten`, `routine`/routine_store.json)
brauchen zuerst einen kleinen Override-Patch — bis dahin bleiben ihre Daten im
Checkout (Etappe 1b).

**Repo-Form des Datenpfads ist der Platzhalter `__XBUDDY_DATA__`** (verbindlich,
#429). In Service-Vorlagen unter `<komponente>/<komponente>.service` und in der
Installer-Doku unter `deploy/systemd/README.md` steht für den SVC-5-Datenpfad
**dieser Platzhalter**, nicht der absolute Wert; der Installer ersetzt ihn beim
Ausrollen auf die kanonische Auflösung `/home/buddy/xbuddy-data`
(`deploy/systemd/README.md` Platzhalter-Tabelle bleibt die Quelle der Wert-
Auflösung). So hat eine neue Service-Vorlage einen klar benannten Anker: jede
Stelle, die SVC-5-Daten anspricht, schreibt `__XBUDDY_DATA__/<komponente>/…` —
**nicht** den absoluten Pfad direkt. **Verworfen:** eine eigene Sub-ID „SVC-6
Platzhalter-Konvention" für alle `__XBUDDY_*__`-Platzhalter — Vorrats-Konvention
(CLAUDE.md §6), die anderen Platzhalter (User/Home/Repo/Python) tragen ihre
Bedeutung bereits in der Installer-README ohne dass eine Convention-ID nötig
ist; nur die SVC-5-Datenwurzel braucht einen eigenen Convention-Anker, weil sie
das Spec-Verhalten („Daten außerhalb des Checkouts") trägt.

### SVC-5a — Per-Instanz-Verzeichnis gehört dem Service-User
`xbuddy-data/<komponente>/` und alle darin enthaltenen Dateien **gehören dem
Service-User** (auf dem Pi: `buddy:buddy`). Root-Ownership auf diesem
Verzeichnis ist ein Fehler — Schreib-Services schlagen dann mit Fehler 500
fehl (Live-Beleg 2026-06-09: 8 von 10 data-dirs root:root nach Migration,
sqlite „readonly database").

Wie die korrekte Ownership hergestellt wird (ExecStartPre, Migrations-Skript,
Reset-Runbook …) bleibt Implementierungs-Spielraum und wird nicht hier
festgelegt.

### SVC-6 — Health- und Version-Endpunkt je Service

Jeder HTTP-Service exponiert zwei unauthentifizierte Diagnose-Endpunkte:

- **`GET /healthz`** — liefert `200` mit `{"status":"ok"}`, sobald der Service
  request-bereit ist (Readiness, kein Deep-Check). Vereinheitlicht die bereits
  gebaute Präzedenz (`essen/main.py`, `kibuddy/main.py` — n=2); **kein** zweiter
  Name `/health` am Service selbst. Der Router aggregiert die Per-Service-`/healthz`
  optional zu einem Fan-in-`/health` (anderer Typ: Readiness-Aggregat, nicht
  Per-Service-Endpunkt).
- **`GET /version`** — liefert die Commit-SHA **des Codes, den dieser Service
  gerade ausführt**. Jeder Service ermittelt sie **einmal beim Start** und hält
  sie im Speicher; jeder Service hat seinen **eigenen** Wert.

  **[GEÄNDERT 2026-08-13 — Nic-Verdikte zu #1788]** Die frühere Fassung verlangte
  eine beim Deploy geschriebene gemeinsame Datei und verbot ausdrücklich die
  Ermittlung zur Laufzeit. Beides ist überholt:

  - Die Datei wurde **von niemandem geschrieben** — das zuständige Skript hatte
    keinen einzigen Aufrufer. Alle zwölf Endpunkte meldeten monatelang denselben
    veralteten Stand.
  - Eine **gemeinsame** Datei kann nicht ausdrücken, was sie ausdrücken soll:
    hängt ein einzelner Service auf altem Code, zeigt sie trotzdem den Stand des
    zuletzt gestarteten. Genau der Fall wäre unsichtbar — und genau dieser Fall
    ist der einzige, der zählt.
  - Die alte Begründung („ein paralleler Worktree würde einen falschen SHA
    einfrieren") stammt aus der Zeit vor dem Wirbelsäulen-Abriss. Sie trägt
    heute nicht mehr, und sie war der einzige Grund für das Verbot.

  Ermittlung beim Start statt bei jeder Anfrage ist wichtig: der Wert soll den
  **laufenden Prozess** beschreiben, nicht die Platte. Zieht jemand neuen Code,
  ohne neu zu starten, muss `/version` weiterhin den **alten** Stand melden —
  das ist die Anzeige, an der man den fälligen Neustart erkennt.

Der Deploy-Regelkreis (`deploy/update.sh`, Stufe 1) leitet aus dem gemergten Diff
die betroffenen Services ab — **geteilter Mapper** mit
`~/.claude/hooks/restart_pending_log.py:services_for_paths` (Harness-Deploy aus lotse), inklusive
**Shared-Pfad-Fan-out**: eine Änderung unter `tools/`, `tools/llm/` oder
`conventions/` trifft **alle** HTTP-Services —, startet sie neu und verifiziert
`is-active` **und** Service-Start-TS > Merge-TS **und** `/healthz`==200
(Falsch-grün-Schutz). Der Release-Worktree (RAT-14-b2) bleibt außerhalb Stufe 1;
Runner-Health (#1113) ist eine eigene Autonomie-Zeile mit 48h-Dry-Run.

**Ergänzung — Bot-Services ohne HTTP (T1666):** Telegram-Polling-Bots (eltern-chat)
haben keinen HTTP-Stack und können deshalb kein `/healthz` exponieren. Sie werden
stattdessen per **Heartbeat-Datei** überwacht: Der Bot schreibt nach jedem
erfolgreichen `getUpdates`-Poll (auch bei leerer Update-Liste) den aktuellen
Unix-Timestamp als einzeiligen Integer atomar in
`<XBUDDY_DATA_DIR>/eltern-chat/heartbeat`. Ein externer Alerting-Poller
(`#1646`) liest diese Datei und schlägt Alarm, wenn der Timestamp zu alt wird.
Das ist eine **Ergänzung** von SVC-6 (Grundsatz „jeder Service ist überwachbar"
bleibt unverändert), keine Ausnahme.

### SVC-7 — Startup-Secret-Preflight: fehlende Secrets brechen sichtbar, nicht still

Jeder Service, der zum Betrieb bestimmte Secrets/Zugangsdaten braucht (Bot-Token,
Anbieter-Keys, o. Ä.), prüft **beim Start**, ob alle von ihm benötigten Secrets
auflösbar sind — aus dem zentralen Zugangsdaten-Store bzw. dem definierten
Env-Fallback. Fehlt eines, **failt der Start sichtbar und laut** (Prozess startet
nicht bzw. beendet sich mit klarer Fehlermeldung im Log), statt request-bereit zu
werden und erst beim ersten Nutzer-Request still einen `500` zu liefern.

**Warum.** Der #1440-Vorfall (kibuddy hing 17 Tage vom `ELTERNCHAT_BOT_TOKEN` ab,
der Deploy rollte ihn nie aus → `/frage` gab für **alle** Nutzer `500`, 17 Tage
unbemerkt) zeigte: eine reine Onboarding-/Runbook-Disziplin (»denk daran, das
Secret mitzurollen«) bricht in der Praxis. Die Prüfung gehört **mechanisch an den
Service selbst** (fail-fast beim Start), nicht in einen Handzettel.

**Form.**

- Der Service kennt seine **Pflicht-Secrets** (Liste der benötigten Slots/Env-Namen)
  und löst sie beim Start auf. Nicht-auflösbar → **kein** `is-active`, klare
  Log-Zeile (`FEHLT: <slot/env-name>`).
- Der Preflight nutzt dieselbe Auflösungsreihenfolge wie der Laufzeit-Zugriff
  (Store bevorzugt, Env als Fallback — siehe zugangsdaten.md und E-ONB-5).
- **Nur Präsenz**, kein Gültigkeits-Deep-Check (kein Test-Call gegen den Anbieter);
  ein präsentes-aber-falsches Secret ist ein anderes Problem.
- Greift mit **SVC-6** ineinander: der Deploy-Regelkreis verifiziert bereits
  `is-active` + `/healthz`==200; ein am Preflight gescheiterter Service wird damit
  automatisch als roter Deploy sichtbar, statt als stiller Dauerausfall.

Präzedenz/Anlass: #1440 (kibuddy-Bot-Token-Lücke), #1447 (diese Konvention),
Nic-Setzung 2026-07-25 (Variante A: »Dienst prüft beim Start selbst«).

### SVC-8 — Bot-Services ohne HTTP: Liveness per Heartbeat statt `/healthz`

Ein Service **ohne** Flask/HTTP-Server (reiner Telegram-Polling-Bot, z. B.
`eltern-chat`) kann kein `/healthz` (SVC-6) exponieren, muss aber im
unbeaufsichtigten Betrieb überwacht sein. Statt einer SVC-6-Ausnahme schreibt
ein solcher Bot ein **Heartbeat**: eine Datei mit dem Zeitstempel des letzten
erfolgreichen Arbeits-Zyklus (z. B. `getUpdates`-Poll) unter
`xbuddy-data/<service>/heartbeat`, bei jedem Zyklus aktualisiert.

Der Fern-Alerting-Poller (#1646) liest den Heartbeat **statt** `/healthz`:
Zeitstempel älter als ein Schwellwert N → Bot tot/hängend → Alert an den
Owner-Kanal. Damit ist der Bot genauso überwacht wie ein HTTP-Service —
SVC-6 bleibt HTTP-only, SVC-8 ist der Nicht-HTTP-Zwilling, keine Ausnahme.

Präzedenz/Anlass: #1641 (eltern-chat kein /healthz), Nic-Wahl b 2026-07-31
(Signal statt Ausnahme). Bau #1666.
