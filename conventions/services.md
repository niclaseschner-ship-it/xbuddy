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
