# Privatchat-Session — Konvention     (ID-Präfix: SESS)

Eltern-Chat-Funktionen, die eine konversationelle Eingabe brauchen
(Anbieter-Key, Personen-Anlage, OAuth-Code), führen das Gespräch im
**Privatchat** zwischen Bot und einem berechtigten Familienmitglied —
nie in der Familien-Gruppe. Diese Konvention legt fest, wie die
Privatchat-Session technisch geformt ist, damit Funktionen das Muster
wiederverwenden statt jedes Mal neu zu erfinden.

Heimat in den Komponenten: `eltern-chat-onboarding.md` ONB-3,
`familie-anlegen.md` FAA-9, `kalender-verbinden.md` KAV-6.

### SESS-1 — Worker-Form
Eine laufende Privatchat-Session läuft in einem **eigenen Thread mit
Queue + `next_message`-Callable**, nicht inline im Telegram-Update-
Handler. Eingehende Privatchat-Nachrichten des Session-Inhabers werden
in die Queue gelegt; der Worker konsumiert sie über `next_message` und
treibt den Dialog deterministisch voran.

Begründung: ein Worker je Session entkoppelt die Konversation vom
allgemeinen Update-Loop und macht Parallel-Sessions verschiedener
Familienmitglieder konfliktfrei.

### SESS-2 — Zwischenzustand nur im Speicher
Der Zustand der laufenden Session (welche Felder schon erfasst sind,
welche Frage als nächstes kommt, welches Foto schon heruntergeladen
wurde, welcher `state`-Token offen ist) liegt **im Prozess-Speicher**
und **nicht** auf Disk. Persistent geschrieben wird **erst** beim
endgültigen Commit der Funktion (FAM-11, ZD-5 o. ä.) — vorher gibt es
keinen halben Zustand zu lesen.

Stürzt der Prozess während einer Session ab oder wird neu gestartet,
ist die Session verloren — kein Wiederaufnahme-Pfad. Bereits durch den
endgültigen Commit geschriebene Daten bleiben unberührt.

### SESS-3 — 30-Minuten-Timeout
Eine Session, die **30 Minuten** keine passende eingehende Nachricht
sieht, läuft automatisch ab und liefert das Ergebnis-Signal
„abgebrochen" zurück an die Aufrufer-Schicht. Eine Onboarding-typische
Konversation darf nicht ewig blockieren.

### SESS-4 — Re-Prompt bei nicht-passender Eingabe
Eine eingehende Privatnachricht, die erkennbar **nicht** die erwartete
Eingabe ist (Begrüßung, Frage, Foto statt Code, leerer Text), wird
**nicht** validiert oder als Fehler gewertet. Stattdessen antwortet die
Funktion mit einer freundlichen Erinnerung an die aktuelle Frage und
wartet weiter. So bleibt der Bot nie stumm und meldet nie fälschlich
einen ungültigen Wert.
