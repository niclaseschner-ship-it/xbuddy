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
`WARNING` für Drift-Symptome (z. B. petraltete Config-Schlüssel ignoriert),
`ERROR` für Fehler, die Aufmerksamkeit erfordern.

### LOG-3 — Keine PII in Logs
Personen-Namen, Telegram-Chat-IDs, Bot-Tokens, API-Keys, E-Mail-Adressen
gehören nicht in Log-Zeilen. Eltern-Chat-Nachrichteninhalte erst recht
nicht. Privacy & Datensicherheit ist Constitution-Qualitätsattribut #3.

Für notwendige Identifikation reichen anonymisierte IDs (z. B.
`chat:abcd1234` statt Klarnamen).
