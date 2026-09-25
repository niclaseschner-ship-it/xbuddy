# earlyoom — versionierte Schutzliste (#1800)

`earlyoom.default` ist der Soll-Zustand für `/etc/default/earlyoom`, die
`EnvironmentFile` des System-Diensts `earlyoom.service`. earlyoom ist die
tatsächliche Speicher-Notbremse auf diesem Pi — der Kernel-OOM-Killer greift
hier praktisch nie (`memory.events:oom_kill` bleibt 0).

Kein xbuddy-Dienst im Sinn von `deploy/systemd/` (keine `xbuddy-*.service`,
kein Eintrag in der `SVC_SRC`-Map von `deploy/bootstrap.sh`) — earlyoom ist
host-weite Infrastruktur, die alle Dienste auf dem Pi betrifft, xbuddy
eingeschlossen. Deshalb ein eigener, kleiner Deploy-Pfad statt eines
Drop-Ins unter `deploy/systemd/` (Vorbild: `deploy/nginx/`, ebenfalls
host-weit statt pro-Dienst).

## Deploy

```
./deploy/earlyoom/install.sh
```

Idempotent: kopiert nur, wenn Quelle und Ziel abweichen; sichert die
vorherige Datei nach `/etc/default/earlyoom.bak`; startet `earlyoom.service`
neu und prüft danach `systemctl is-active` — schlägt der Neustart fehl, wird
das Backup automatisch zurückgespielt.

## Warum diese Liste so aussieht

Siehe die Kommentare in `earlyoom.default` — sie tragen die Begründung pro
Eintrag (Ton-Stapel, Datei-Dienste, Schlüsselbund auf `--avoid`; Kiosk-Chromium
von `--prefer` entfernt, Immich/Paperless bewusst weiter auf `--prefer`).
Kurzfassung: `--avoid` schützt Cockpit-Sitzungen, die Datenbank und die
kleinen Sitzungsdienste (Ton, Dateizugriff, Zugangsdaten), deren Tod nichts
gewinnt, aber Arbeit kostet (#1800). `--prefer` lässt die Maschine bei Druck
weiter zuerst Immich/Paperless verlieren, nicht mehr aber den Kiosk (#1870).

## Drift-Hinweis

Wird `/etc/default/earlyoom` von Hand geändert (wie zuletzt am 2026-08-17),
läuft das an dieser Datei vorbei — es gibt (bewusst, siehe
`deploy/tests/test_dropins_vollstaendig.py`) keinen Maschinen-Abgleich-Test.
Wer von Hand eingreift, sollte die Änderung hierher zurückspielen, sonst
verliert ein Neuaufsetzen sie wieder.
