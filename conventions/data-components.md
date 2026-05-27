# Data-Components — Konvention     (ID-Präfix: DCOMP)

XBuddy-Komponenten laufen als getrennte Prozesse (SVC-1) und halten je
eigene Daten. Diese Konvention legt fest, wie sie miteinander reden und
wie sie persistente Daten lesen — damit Skill-Schreibvorgänge sichtbar
werden und damit Komponenten unabhängig voneinander startbar bleiben
(Lego-Prinzip, siehe Constitution).

### DCOMP-1 — Komponenten reden über HTTP, nicht über Python-Import
XBuddy-Komponenten kommunizieren untereinander ausschließlich über lokale
HTTP-Aufrufe auf den Loopback-Ports aus PORT-2. Eine Komponente importiert
keinen Python-Code einer anderen Komponente — auch nicht „nur kurz für
diese Funktion".

Begründung: Komponenten sind getrennte Prozesse (SVC-1) mit eigenen Logs
(SVC-4, LOG-1) und eigenem Lifecycle. Ein direkter Import koppelt die
Lifecycles: stürzt der importierte Code, fällt der Importeur mit; startet
eine Komponente neu, hat der Importeur einen petralteten Modul-Stand im
Speicher. HTTP entkoppelt sauber und macht den Aufruf in den Logs
diagnostizierbar.

Gemeinsamer Code, der nicht prozessgebunden ist, lebt unter `tools/`
als Bibliothek (Beispiel: `tools/configloader.py`, CONFIG-1) und wird
von jeder Komponente per Import aus `tools/` genutzt — das ist der eine
erlaubte Pfad für Code-Wiederverwendung (CLAUDE.md §6, „gemeinsamer Code
lebt an EINEM Ort"). Was zu `tools/` gehört: Loader, Formatter, reine
Helfer ohne eigenen Prozess. Was *nicht* dorthin gehört: alles, was eine
Komponente *ist*.

### DCOMP-2 — Persistente Daten werden pro Aufruf frisch von Disk gelesen
Komponenten, die persistente Daten lesen (`plan.json`, `routing.json`,
`zugangsdaten.json` und ähnliche), lesen sie **pro Aufruf frisch von
Disk**. Sie laden sie nicht einmal beim Prozessstart in den Speicher und
arbeiten danach mit dem Cache.

Begründung: Eltern-Chat-Skills schreiben Cross-Service in Datendateien
fremder Komponenten ([[project-xbuddy-skill-service-reload]],
EC-21, Refs #140). Der lesende Service muss den neuen Stand ohne Restart
sehen — sonst zeigt der Plan-Buddy noch den alten Termin, obwohl der
Skill bereits geschrieben hat. Stale Cache nach Cross-Service-Write ist
der konkrete Schaden, den diese Konvention verhindert.

Reload-on-Read ist damit der Default. Das eigentliche
Cross-Service-Vertragsmodell bleibt APP-3 („andere Apps sprechen eine
App nur über deren Schnittstelle an"); DCOMP-2 deckt den internen
Lese-Pfad innerhalb derselben App ab, der durch Skill-Schreibvorgänge
berührt wird.

Ausnahme: wer aus Performance-Gründen cachen will (z. B. heiße Hot-Path-
Lookups), begründet das in der Komponenten-Spec und benennt einen
expliziten Invalidierungs-Pfad. Stillschweigendes Caching ist
Konventions-Verstoß.
