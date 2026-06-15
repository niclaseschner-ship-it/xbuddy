# KIBuddy-Prompt anpassen — Spec     (ID-Präfix: KPA)

> Status: V1 · Refs #819

Damit ein Elternteil im Eltern-Chat den **System-Prompt** des KIBuddys
schrittweise verbessern kann — Tonfall justieren, neue Beispiele
einarbeiten, Verhaltens-Regeln ergänzen — ohne die Datei zu öffnen,
definiert diese Spec **KIBuddy-Prompt anpassen als aufrufbare Funktion**:
Aufgerufen, führt sie einen **sokratischen Mehrturn-Dialog** mit dem
Elternteil im Privatchat, lässt das LLM einen verbesserten Prompt
verfassen, zeigt eine **Diff-Vorschau** und schreibt nach ausdrücklicher
Bestätigung über die KIBuddy-Schnittstelle (`kibuddy.md` KIBUDDY-24, `PUT
/api/v1/kibuddy/prompt`) in die Per-Instanz-`prompt.txt`.

Es ist eine **schreibende** Aufgabe (EC-10): die Funktion verändert das
zentrale Verhaltens-Artefakt des KIBuddys (Wirkung auf jede künftige
Kind-Frage) und darf erst nach einer ausdrücklichen Bestätigung wirken
(E-EC-7). Die Funktion ist **trigger-agnostisch** (E-KPA-1 analog
`routine-zeiten-setzen.md` E-RZS-1).

**Lego-Einordnung:** Klasse-C-Aufgabe nach
`conventions/eltern-chat-skills.md` — kanonisch `propose` → `confirm` mit
schreibendem Effekt nach Bestätigung. Sokratische Mehrturn-Struktur ist
KPA-spezifisch, der Schreib-Vertrag identisch zu KAQS.

**V1-Scope:** sokratisch-iterativer Dialog im Privatchat des Aufrufers
(KPA-3) · LLM-gesteuerte Prompt-Verbesserung mit dem Eltern-Wunsch als
Eingabe (KPA-4) · auf Nachfrage Anzeige des **vollständigen aktuellen
Prompts** (KPA-5) · **Diff-Vorschau** (vorher/nachher der geänderten
Stellen) vor der Bestätigung (KPA-6) · Schreiben über die KIBuddy-
Schnittstelle (KIBUDDY-24, `PUT /api/v1/kibuddy/prompt`, KPA-7) · der
Trigger als Eltern-Chat-Aufgabe (EC-8, EC-10, TASK-7-Registrierung,
KPA-8).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Prompt-Versions-Historie** mit Rückgängig pro Versionsnummer. V1 hat
  nur **eine Rückgängig-Generation** (`prompt.txt.bak`, KIBUDDY-15) —
  Versionierung mit mehreren Stufen ist V2.
- **Per-Kind-Prompts.** V1 ist familien-global. Per-Kind-Profile sind
  OPEN-KIBUDDY-J im KIBuddy-Backlog, nicht hier separat.
- **A/B-Test zwischen Prompts.** V1 schreibt immer den aktiven Prompt
  (eine Datei). Mehrere parallel aktive Prompts mit Routing-Regel: V2.
- **Sprach-Trigger.** Die Funktion ist trigger-agnostisch (E-KPA-1) —
  ein späterer Sprach-Trigger am Display oder im Telegram-Mini-App-
  Frontend bedient denselben Skill-Eingang ohne API-Bruch.

---

## KPA-1 — Trigger-agnostische Funktion
„KIBuddy-Prompt anpassen" nimmt {Eltern-Wunsch als Text-Beschreibung,
optional: bestehende Konversation} und ruft am Ende `PUT
/api/v1/kibuddy/prompt` (KIBUDDY-24). Sie ist die Heimat der Fähigkeit;
der Telegram-Task ist ein dünner Trigger (TASK-1). Skill-Modul:
`eltern-chat/skills/kibuddy_prompt_anpassen.py` (Funktion) +
`eltern-chat/skills/kibuddy_prompt_anpassen_task.py` (TASK-1-Trigger).

## KPA-2 — Klasse-C-Aufgabe mit Mehrturn-Eigenheit
KPA ist eine **WriteTask** mit `propose()` + `execute()` (TASK-4, Klasse C
nach `conventions/eltern-chat-skills.md`). Die Eigenheit gegenüber RZS/KAQS:
**`propose()` läuft Mehrturn**. Der erste Aufruf startet den Dialog,
folgende Eltern-Nachrichten im selben Privatchat fließen als weitere
Turns in dieselbe Skill-Session bis der Vorschlag fertig ist —
implementiert über den **bestehenden Agent-Loop** (TASK-10): der Skill
returnt jedes Mal einen User-tauglichen Tool-Result-String mit dem
nächsten sokratischen Schritt oder dem fertigen Vorschlag mit
Bestätigungs-Frage. Erst die Bestätigung führt zu `execute()` und damit
zum Schreibvorgang.

**Kein eigener State-Store im Skill** — der Konversations-Kontext lebt
in der laufenden Agent-Session (EC-15: privater Chat ist Kontextgrenze)
und im LLM-Token-Verlauf des Eltern-Chat-Hubs.

## KPA-3 — Konversation im Privatchat
Wie KAQS-3: ausschließlicher Privatchat-Kontext (EC-2, EC-5). Gruppenchat-
Aufruf führt zu höflichem Verweis auf den Privatchat.

## KPA-4 — Sokratischer Dialog zur Prompt-Verbesserung
Der LLM-Agent führt einen **sokratischen Dialog** mit dem Elternteil —
analog zur Sokratischen Struktur des KIBuddy-Prompts selbst (KIBUDDY-15):

1. **Eltern-Wunsch verstehen** — der Bot fragt nach, **was** der Elternteil
   am Buddy-Verhalten ändern möchte (Tonfall? Themen? Verweigerungen?
   bestimmte Reaktion auf bestimmte Frage-Klassen?).
2. **Konkretisierung** — bei vagem Wunsch („soll netter sein") fragt der
   Bot nach konkreten Beispielen aus erlebten Antworten.
3. **Vorschlag-Skizze** — der Bot **schlägt eine Prompt-Änderung vor** als
   Text-Beschreibung („Ich würde in den Abschnitt »Wie du sprichst« eine
   neue Regel einbauen: …").
4. **Iteration** — der Elternteil kann nachjustieren („mach das positiver"
   / „kürzer" / „auch für ältere Geschwister") und der Bot überarbeitet.
5. **Diff-Vorschau + Bestätigung** (KPA-6).

Der **Bot zeigt den aktuellen Prompt nicht von sich aus** — er ist groß
(~3 000 Zeichen) und überfordert die Telegram-Lese-Erfahrung. **Aber:**
wenn der Elternteil im Dialog explizit nachfragt („zeig mir den Prompt"
/ „was steht da gerade?"), zeigt der Bot den **vollständigen aktuellen
Prompt** in einer einzelnen Telegram-Nachricht oder mehrere, falls
Telegram-Längen-Limit überschritten (KPA-5).

## KPA-5 — Auf Nachfrage: vollständigen aktuellen Prompt zeigen
**Wenn** der Elternteil im KPA-Dialog die Anzeige des aktuellen Prompts
verlangt (Erkennung über LLM-Agent — der versteht „zeig mir den Prompt",
„was steht aktuell drin", „prompt anzeigen" usw.), **dann** liest der
Skill den Prompt über `GET /api/v1/kibuddy/prompt` (KIBUDDY-24) und postet
ihn als Telegram-Nachricht in den Chat.

**Längen-Behandlung:** bei mehr als 3 500 Zeichen (Telegram-Limit 4 096
mit Sicherheitsmarge) wird der Prompt **in mehrere Nachrichten** geteilt,
jede Nachricht hat einen Header `(Teil X/Y)`. Der Skill schickt die
Nachrichten direkt im `propose()`-Frame über das vom TASK-10-Vertrag
sanktionierte „nach erfolgter Iteration kann der Skill selbst senden"
(in V1: `propose()` returnt einen kurzen „Hier kommt der Prompt:"-Hinweis,
unmittelbar gefolgt von den Prompt-Teilen, die der Skill direkt sendet
— sanktionierte Ausnahme von „propose ist sprachlos in EC-29-Sinne",
weil das Vorlesen des aktuellen Prompts **lesend** ist, keine Schreibung).

Nach der Anzeige läuft der sokratische Dialog (KPA-4) normal weiter.

## KPA-6 — Diff-Vorschau vor der Bestätigung
**Bevor** der Skill `execute()` aufruft, postet er eine **Diff-Vorschau**
in den Privatchat. Form:

- **Headline:** „So würde dein neuer Prompt aussehen — ein letzter Blick:"
- **Format:** unified-diff-Stil mit Zeilen-Markierung (Telegram-`monospace`):
  - `- alte Zeile` (rot wirkende Vorzeichen für Entfernung)
  - `+ neue Zeile` (grün wirkende Vorzeichen für Hinzufügung)
  - Unveränderte Zeilen werden mit einer kurzen Markierung übersprungen
    (`… N unveränderte Zeilen …`) — nur Kontext-Zeilen um die geänderten
    Stellen werden gezeigt (Kontext 2 Zeilen vor/nach).
- **Fußzeile mit Bestätigungs-Frage:** „Soll ich den neuen Prompt
  übernehmen? Tippe **ja** zum Bestätigen, **nein** zum Verwerfen, oder
  beschreibe weitere Änderungen."

Falls die Diff-Ausgabe selbst über das Telegram-Längen-Limit wächst,
wird sie analog zu KPA-5 in Teile zerlegt mit `(Teil X/Y)`-Header.

**Kein Schreibvorgang ohne sichtbare Diff-Vorschau.** Diese Klausel
schützt gegen LLM-Halluzinationen, die unter der „verbesserter Prompt"-
Tarnung subtile Änderungen einschleichen könnten — die Eltern sehen,
was wirklich passiert.

## KPA-7 — Schreiben über die KIBuddy-Schnittstelle
`execute()` ruft `PUT /api/v1/kibuddy/prompt` mit Body `{"prompt": "<voller
neuer Text>"}` (KIBUDDY-24). Bei Erfolg postet der `execute()`-Frame
eine Erfolgs-Bubble: „Der neue Prompt ist aktiv — der KIBuddy nutzt ihn
ab der nächsten Frage." Bei Fehler eine Fehler-Bubble mit Hinweis auf
die letzte funktionsfähige Version unter `prompt.txt.bak` (KIBUDDY-15).

**Keine eigene Datei-Logik im Skill** — die Datenhaltung des KIBuddys
gehört dem Buddy (KIBUDDY-15, KIBUDDY-26); der Skill schreibt
ausschließlich über die HTTP-API.

## KPA-8 — Registrierung als Eltern-Chat-Aufgabe (TASK-7)
Analog KAQS-6:
- **Name:** `kibuddy_prompt_anpassen`
- **Klasse:** WriteTask (Klasse C nach `conventions/eltern-chat-skills.md`),
  Mehrturn-`propose` (KPA-2)
- **Beschreibung im Skill-Katalog:** „Verbessert den KIBuddy-Prompt im
  Gespräch."
- **Args-Schema:** keine harten Args — der Eltern-Wunsch fließt als
  Konversations-Eingabe ein (KPA-4 Schritt 1).

## E-KPA-1 — Trigger-agnostisch (Erklär-ID)
Der Vertrag der Funktion ist {Eltern-Wunsch + Konversation} → Schreibung
über KIBUDDY-24, kein Telegram-Vokabular. Ein späterer Trigger (Sprach-
Einspielung am Display, Mini-App-Frontend) bedient denselben Skill-
Eingang ohne API-Bruch.

## E-KPA-2 — Warum sokratisch (Erklär-ID)
Eltern wissen oft, **was** sie am Buddy ändern wollen („soll bei
Sterbe-Fragen weniger erschreckend antworten"), aber nicht, **wie** sich
das in einer Prompt-Klausel niederschlägt. Der Bot übernimmt die
Übersetzungs-Arbeit von „Wunsch" zu „Prompt-Edit" — analog zur
Sokratischen Frage-Schleife, die der KIBuddy selbst Kindern gegenüber
fährt. **Spiegel-Konsistenz:** dasselbe sokratische Pattern, in das die
Eltern bei der Werkzeug-Anpassung selbst hineingezogen werden, ist auch
das Pattern, das ihre Kinder erleben — sie verstehen Buddy-Verhalten
besser durch eigene Erfahrung damit.

## Tests

- **Dialog-Start-Test:** erster Skill-Aufruf returnt einen sokratischen
  Klärschritt nach KPA-4 Schritt 1; **kein** Aufruf an `GET /prompt`,
  kein Schreibversuch.
- **Prompt-Anzeige-Test:** Eltern-Nachricht „zeig den Prompt" führt zu
  einem `GET /prompt`-Call + Telegram-Nachricht mit dem Volltext (ggf.
  in Teilen); danach läuft der Dialog weiter.
- **Diff-Vorschau-Test:** vor jedem `execute()`-Aufruf wird genau eine
  Diff-Vorschau gepostet; Bestätigungswort „ja" führt zum Schreiben,
  „nein" verwirft, sonstige Texte fließen als Iteration zurück in KPA-4.
- **Schreib-Test:** `execute()` mit gemocktem KIBuddy-Backend ruft `PUT
  /prompt` mit dem korrekten Body und postet die Erfolgs-Bubble.
- **Fehler-Test:** Backend-500 führt zu Fehler-Bubble mit
  `prompt.txt.bak`-Hinweis; keine zweite Schreibversuch-Schleife.
- **Halluzinations-Test:** wenn die Diff-Vorschau Zeilen enthält, die
  vom Elternteil nicht im Dialog gewünscht wurden, soll das beim
  manuellen Test als Issue erkennbar sein — V1-Schutz ist die sichtbare
  Diff selbst (KPA-6), nicht ein Algorithmus.
