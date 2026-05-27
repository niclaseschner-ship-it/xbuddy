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
