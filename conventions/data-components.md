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
eine Komponente neu, hat der Importeur einen veralteten Modul-Stand im
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

### DCOMP-3 — Last-Known-Good bei Lese-Fehler (Reload-Pattern E-RELOAD-1)
Wer DCOMP-2 (Reload-on-Read) umsetzt, hält zusätzlich den **zuletzt
erfolgreich geladenen Stand als Snapshot** und benutzt ihn als Fallback,
**wenn ein einzelner Read scheitert** — Datei kurz weg (atomares
Replace-Race aus DCOMP-4), kaputtes JSON, ungültige Pflichtwerte.
Übernommen wird der neue Stand erst nach erfolgreich vollständigem
Parse; ein halb geschriebenes oder kaputtes JSON darf den Snapshot
nicht verfälschen.

Dieselbe Eigenschaft trägt der Anker-Name **E-RELOAD-1**, der heute
schon in Router-Code (`router/main.py`) und Plan-Buddy-Code
(`plan/main.py`) zitiert wird. Komponenten, die dasselbe Muster
umsetzen, verweisen auf DCOMP-3 (oder den Anker-Namen E-RELOAD-1),
statt eigene Anker zu erfinden.

Heimat in den Specs: `router.md` ROU-25 (Router-spezifische
Ausprägung), `plan.md` Daten-Konfig-Abschnitt (Plan-Buddy-Ausprägung).
Optional: Komponenten ohne Last-Known-Good-Pflicht (z. B. weil ihr
Lese-Pfad einen leeren Default verkraftet) dokumentieren das in ihrer
Spec.

### DCOMP-4 — Persistente Schreibvorgänge sind atomar (Temp-Datei + Rename)
Komponenten, die eine persistente Datendatei schreiben (`familie.json`,
`geraete.json` und ähnliche), schreiben **atomar**: erst in eine
Temp-Datei im selben Verzeichnis, dann `os.replace` (oder ein
gleichwertiges atomares Rename) auf den Zielnamen. Ein zeitgleicher
Lesezugriff sieht **nie** eine halb geschriebene Datei.

Begründung: Eltern-Chat-Skills schreiben Cross-Service in Datendateien
(EC-21, siehe DCOMP-1), während der besitzende Service parallel liest.
Ein nicht-atomarer Schreibvorgang würde dem Leser entweder ein leeres
oder ein abgeschnittenes JSON zeigen — der Lese-Pfad würde brechen,
obwohl der Schreiber „nur kurz" mittendrin war. Atomar heißt: aus
Lese-Sicht existiert nur „alter Stand" oder „neuer Stand", nie
„dazwischen".

Implementierungs-Hinweis: Wirft eine Komponente nach einem `except OSError as e:`
einen eigenen Fehler (z. B. `RegistryError`), muss sie `raise ... from e` schreiben,
damit die Fehler-Kausalkette im Traceback erhalten bleibt — der ursprüngliche
`OSError` ist dann als `__cause__` sichtbar und vereinfacht die Diagnose.

Heimat des Patterns in den Specs: `familie.md` FAM-11, `geraete.md`
GER-6, `zugangsdaten.md` ZD-3.
