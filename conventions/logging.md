# Logging — Konvention     (ID-Präfix: LOG)

XBuddy-Komponenten erzeugen Logs für Diagnose im Betrieb. journalctl ist
die Quelle der Wahrheit (siehe SVC-4); diese Konvention legt Form und
Inhalt der Log-Zeilen fest.

### LOG-1 — Format ist `%(asctime)s %(levelname)s %(message)s`
Jede Komponente verwendet das Python-`logging`-Standard-Modul mit dem
Format `%(asctime)s %(levelname)s %(message)s`. Beispiel:
`2026-05-27 09:24:03,373 INFO Bot @Maischner_bot, Anbieter 'claude'`

Kein eigenes Logging-Framework, keine JSON-Logs für lokale Komponenten —
journalctl ist textorientiert.

### LOG-2 — INFO im Betrieb, DEBUG via Konfig-Override
Im Produktiv-Betrieb läuft jede Komponente auf `INFO`. `DEBUG` wird
situativ aktiviert (Konfigurations-Datei oder ENV-Override, vgl. CONFIG-1).
`WARNING` für Drift-Symptome (z. B. veraltete Config-Schlüssel ignoriert),
`ERROR` für Fehler, die Aufmerksamkeit erfordern.

### LOG-3 — Keine PII in Logs
Personen-Namen, Telegram-Chat-IDs, Bot-Tokens, API-Keys, E-Mail-Adressen
gehören nicht in Log-Zeilen. **Nutzer-Inhalte erst recht nicht — und zwar
ausdrücklich beides: Eltern-Chat-Nachrichten UND gesprochene Kind-Sprache**
(Transkripte, Fragen an den Sprach-Buddy, TTS-Eingaben). Privacy &
Datensicherheit ist Constitution-Qualitätsattribut #3.

Die Nennung der Kind-Sprache ist eine Wortlaut-Schärfung, kein neuer
Beschluss: die Überschrift sagt „keine PII", und ein Kind, das mit dem
Buddy spricht, ist der schutzbedürftigste Fall überhaupt. Anlass war
xbuddy#1806 — vier Stellen protokollierten Kind-Sprachinhalt wörtlich auf
`INFO`: das Transkript, die Frage, die Modell-Antwort samt der daraus
extrahierten Buzzwords und der von der Stille-Halluzinations-Filterung
erkannte Text. Wo der Inhalt fürs Debugging gebraucht wird, ist `DEBUG`
die Bahn (LOG-2), nicht `INFO`.

Für notwendige Identifikation reichen anonymisierte IDs (z. B.
`chat:abcd1234` statt Klarnamen).

### LOG-4 — Komponenten nutzen `tools/logsetup.py`, kein eigenes `basicConfig`
XBuddy-Service-Komponenten richten ihr Logging über
`tools.logsetup.setup(level)` ein, nicht durch einen eigenen
`logging.basicConfig(...)`-Aufruf. Konkret: Jede Komponente ruft `setup`
einmal im Hauptpfad ihres Prozesses auf (typischerweise `main.py`) und
übergibt den Log-Level aus ihrer eigenen Config (CONFIG-1/CONFIG-2-Bahn,
`tools/configloader.py`). Module-lokale `logging.getLogger(__name__)`-
Aufrufe bleiben unberührt — das ist Standard-Python und nicht Teil
dieser Konvention.

Begründung: Das LOG-1-Format ist eine Konvention, die an *einer* Stelle
gelebt wird (CLAUDE.md §6, „gemeinsamer Code lebt an EINEM Ort"). Wenn
sich das Format später ändert (etwa Service-Name als Spalte ergänzen),
trifft die Änderung **eine** Datei, nicht vier.

Ausnahme: Test-Code darf eigenständig Logging konfigurieren
(pytest-Caplog, eigene Handler) — die Konvention adressiert
Service-Prozesse, nicht Test-Harnesses.

`setup()` ersetzt den Root-Handler — wer zusätzliche Handler (z. B.
`RotatingFileHandler` für lokale Tests) anhängen will, tut das **nach**
dem `setup()`-Aufruf. Mehrfacher `setup()`-Aufruf bleibt idempotent;
jeder Aufruf reisst die Handler-Liste auf einen einzigen LOG-1-Handler
zurück.

Bootstrap-Setup vor Config-Resolve ist erlaubt: Wenn die
Config-Auflösung selbst loggen können soll (z. B. damit ein
`ConfigError` mit LOG-1-Format auf journalctl landet, statt als nackter
Traceback), darf eine Komponente vor dem Resolve `setup(level)` mit
einem Default-Level (CLI-Argument oder `INFO`, CLI-Vorrang gemäß
CONFIG-1) aufrufen und nach erfolgreichem Resolve erneut
`setup(cfg.log_level)` mit dem Config-Wert. Die Idempotenz-Klausel oben
macht das Re-Setup sauber — der Root-Handler wird ersetzt, kein
doppelter Handler. Eltern-Chat
nutzt dieses Pattern (Refs PR #196); Router/Plan-Buddy/Familien-Registry
kommen ohne aus, weil ihr Config-Resolve nicht logged.

Querverweise: LOG-1, LOG-2, CONFIG-1, CLAUDE.md §6, `tools/logsetup.py`.
