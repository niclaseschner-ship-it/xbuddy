# RAT-46 — Plan-Aktivitätskatalog wandert nach `plan.json` — kleinste Externalisierung, keine Plan-Engine

**Status:** RATIFIZIERT 2026-06-08 (Nic „ja passt so tun!")
**Betrifft:** `specs/buddies/plan.md` — E-PLAN-8 (umformuliert), PLAN-12
(nachgezogen), PLAN-28 (Onboarding-Tabelle erweitert)
**Bezug:** RAT-4 (Slot-Modell `cycle` pro Slot — **weiter defer**; dieser
Beschluss nimmt dem Fork-Argument nur den Aktivitäts-Katalog weg, nicht die
Slot-Logik); CONFIG-1 (Code-Konstanten sind nur Fallback, nie Wahrheit),
CONFIG-2 (Werte ohne Onboarding-Pfad = Spec-Verletzung), CONFIG-4 (Fallback);
`specs/constitution.md` (Familien-Schnittstelle, Anti-Goal „kein
Wartungsaufwand")
**Ticket:** #259 (Träger des Code-Tracks)
**Entscheid-File:**
`brainstorm/berater-runde/20260608-RATIFIZIERT-wd-e-plan-8-familien-katalog.md`

## Problem

Ein Watchdog-Lauf markierte E-PLAN-8 als kritisch vor Familie 3: der
Aktivitäts-Katalog des Plan-Buddys steht hartcodiert im Code, die Spec erklärt
den **Repo-Fork** zur Familien-Form. Das kollidiert frontal mit CONFIG-1
(„Code-Konstanten sind nur Fallback, nie Wahrheit") und mit dem
Constitution-Anti-Goal „kein Wartungsaufwand" — Branch-Pflege pro Familie ist
genau das.

Die Frage war nicht „ist Fork schlimm", sondern: **kippt der Befund E-PLAN-8
wirklich, oder ist er ein Watchdog-Fehlalarm** — und wenn er kippt, was ist die
kleinste Externalisierung, die keine Plan-Engine nach sich zieht.

## Betrachtete Alternativen

- **A — Befund ignorieren, E-PLAN-8 unverändert.** Familie 3 träfe auf
  Fork-Sync-Schmerz; der CONFIG-1-Konflikt bliebe monatelang ungelöst.
  Verworfen.
- **B — kleinste Externalisierung** (die zwei bestehenden Tabellen 1:1 als
  JSON-Liste nach `plan.json`, Code-Konstanten bleiben als CONFIG-4-Fallback).
  Gewählt.
- **C — volle Generalisierung** (Aktivitäts-Templates, Ablauf-Engine,
  Familien-Profile). Von der Spec selbst schon ausdrücklich verworfen,
  Vorrats-Generalisierung. Stand nicht zur Auswahl.

## Wie entschieden

Zwei Dinge trugen den Beschluss, und beide waren **gemessen, nicht behauptet**.

**Erstens der Drift-Beleg.** Die erste Runde argumentierte mit einem
Zahlen-Fehler („8 Monate im Repo") um Faktor 16 — der Spec-Commit war 16 Tage
alt. Der Antiberater legte das offen und lieferte den besseren Beleg: der
Katalog besteht aus **zwei gekoppelten Strukturen** mit demselben Schlüssel
(`AKTIVITAETEN` + `_ART_ZU_ICON`), die zweite wurde in genau diesen 16 Tagen
nachgezogen, und der Test überspringt Arten ohne Icon-Eintrag stillschweigend.
Der Drift-Trigger ist damit **schon innerhalb einer Familie** erfüllt — die
Familie-3-Sorge ist gar nicht nötig, um die Externalisierung zu rechtfertigen.

**Zweitens ein 10-Minuten-Experiment** auf einer isolierten Wegwerf-Instanz
(eigener Port, eigene Config, Produktions-Instanz unangetastet):
`plan.json` um eine `aktivitaeten`-Sektion mit drei fiktiven Aktivitäten
erweitert, Reload angestoßen — HTTP 200, kein Warning: die Reload-Bahn ist
erweiterungsoffen. Gegenprobe mit absichtlich kaputtem Slot: HTTP 500, Server
lebt weiter, der nächste gute Reload kommt sauber durch — der Reload-Pfad ist
atomar wie versprochen. Damit war B mechanisch unblockiert, bevor eine Zeile
Spec geschrieben wurde.

## Ergebnis

- **E-PLAN-8 bleibt als Prinzip bestehen** — für die *echte* Routinen-Logik
  (Slot-Sequenz, PLAN-19-Personen-Auflösung). Es verliert nur den
  Aktivitäts-Katalog als Anwendungsfall, und die Spec sagt jetzt **warum**
  (die zwei gekoppelten Strukturen).
- **PLAN-12:** der Katalog kommt aus `plan.json` (Sektion `aktivitaeten`); die
  Code-Konstanten bleiben als CONFIG-4-Fallback.
- **PLAN-28:** neue Zeile in der Onboarding-Tabelle mit dokumentiertem
  Onboarding-Pfad „Direkt-Edit" — damit ist CONFIG-2 erfüllt, ohne einen
  Eltern-Chat-Skill auf Vorrat zu fordern.
- **Kein neues Genre, keine neue Konvention, kein Constitution-Eingriff.** Der
  Code-Track (`plan/config.py` liest die Sektion, `plan/aktivitaeten.py` wird
  Lookup-Bibliothek) läuft separat unter #259.

## Woran wir merken würden, dass es falsch war

- **Externalisierung war Vorrat,** wenn die `aktivitaeten`-Sektion über Monate
  in keiner Instanz gefüllt wird. Schaden minimal, Rückbau Minuten — genau
  deshalb war B die günstige Wette.
- **Der Reload-Pfad trägt nicht,** wenn `resolve()` die Sektion einliest, aber
  die Atomarität dabei verliert (kaputte `plan.json` kippt den laufenden
  Stand). Das Experiment hat den Ist-Zustand belegt, nicht den Zustand *nach*
  der Erweiterung — die Gegenprobe gehört in den Code-Track.
- **Nicht geprüft:** ob die neuen Aktivitäten am Ende als Icons im UI landen.
  Das hängt am Lese-Pfad, nicht an dieser Entscheidung, und wurde in der Runde
  ausdrücklich als offen markiert.
