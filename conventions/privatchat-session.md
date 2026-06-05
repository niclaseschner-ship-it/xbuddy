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

### SESS-5 — Session-Sorten-Registry und Routing-Form
Jede Privatchat-Session-Sorte (FAA, GAA, KAV, TES, PAA, …) ist durch
vier Bausteine beschrieben:

1. **Context-Slot** (`ctx.<sort>_sessions: dict`) — in-memory Map
   `chat_id → Session`. Der Worker-Thread schreibt seinen Eintrag
   hinein; `handle_update` liest denselben Zeiger heraus. Nur über
   denselben Zeiger ist die Routing-Garantie gegeben (Lego-Falle).

2. **handle_update-Block** — `handle_update` iteriert die
   **Session-Sorten-Registry** (`_SESSION_SORTS` in `main.py`) und
   routet eine eingehende Privatnachricht an die erste Sorte, deren
   Session-Map einen nicht-fertigen Eintrag für `msg.chat_id` enthält.
   Pro Sorte gibt es KEINEN eigenen if-Block mehr — die Registry-
   Iteration ist die EINE Stelle (CLAUDE.md §6).

3. **make_input-Helfer** (`make_<sort>_input(incoming_message)`) —
   sortenspezifische Funktion, die eine `IncomingMessage` (Telegram-
   Nachricht) in den skill-internen Input-Typ übersetzt. Liegt im
   `<sort>_task.py`-Modul der Sorte, nicht in `main.py`.

4. **Session-Sorten-Registry** (`_SESSION_SORTS`) — modul-weites
   Tupel von `SessionSortEntry(ctx_attr, make_input_fn)` in `main.py`,
   gebaut von `_build_session_sorts()` beim Modul-Load. Neue Sorten
   werden hier additiv ergänzt, nirgendwo sonst.

**Reihenfolge** der Registry-Einträge entspricht der früheren
if-Kette (FAA→GAA→KAV→TES→PAA) und darf nicht geändert werden, ohne
das Routing-Verhalten zu prüfen — ein Chat kann gleichzeitig in
mehreren Maps einen Eintrag haben (Edge-Case bei abgebrochenen
Sessions), und die erste Übereinstimmung gewinnt.

**Neue Sorte hinzufügen** (Ticket #319):
- Context-Slot ergänzen (`<sort>_sessions: dict = None`)
- `make_<sort>_input` im Task-Modul definieren
- `SessionSortEntry` zu `_SESSION_SORTS` in `_build_session_sorts()` in
  `main.py` hinzufügen (am Ende der Tuple)
- Routing-Test für die neue Sorte schreiben (analog
  `test_handle_update_routes_to_tes_session`)
