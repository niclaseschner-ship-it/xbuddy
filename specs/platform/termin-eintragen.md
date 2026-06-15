# Termin eintragen — Spec     (ID-Präfix: TES)

> Status: V1 · Refs #144

Damit ein Elternteil im Eltern-Chat einen Termin in den Familien-Kalender
schreiben kann, ohne die Kalender-App des Smartphones zu öffnen oder am
Display zu tippen, definiert diese Spec **Termin eintragen als aufrufbare
Funktion**: Aufgerufen, klärt sie den Termin im Telegram-Privatchat mit dem
Aufrufer, legt ihn nach ausdrücklicher Bestätigung über die Plan-Buddy-Termin-
Schnittstelle (`plan.md` PLAN-22, `PUT /api/v1/plan/termine`) im Familien-
Kalender an und meldet das Ergebnis zurück. Es ist eine **schreibende**
Aufgabe (EC-10): die Funktion verändert Familien-Daten und darf erst nach
einer ausdrücklichen Bestätigung durch ein Familienmitglied (E-EC-7) wirken.
Die Funktion ist **trigger-agnostisch** (E-TES-1 analog `ca-verteilung.md`
E-CAV-1, `kalender-verbinden.md` E-KAV-1, `familie-anlegen.md` E-FAA-1,
`termine-erfragen.md` E-TER-1): wer sie aufruft — eine Eltern-Chat-Aufgabe,
ein späteres anderes Interface — ist nicht Teil ihres Vertrags.

**V1-Scope:** das Eintragen **eines** Termins je Aufruf · die Konversation
läuft im Privatchat des Aufrufers (TES-3, E-TES-3 analog
`kalender-verbinden.md` KAV-3) · ein hart-codiertes Datums- und
Uhrzeit-Vokabular (TES-4 für den Tag, TES-6 für Uhrzeit und Mehrtages-
Spanne, TES-4 verweist auf `termine-erfragen.md` TER-4 — geteilte
Wahrheit, kein Kopieren) · ganztägige, zeitgebundene und mehrtägige
Termine (TES-6) · der Titel kommt aus der Nutzer-Eingabe (TES-5, roh
übernommen, keine automatische Personen-Anreicherung in V1) · ein
strukturierter Vorschlag im Privatchat + Bestätigungswort nach
`eltern-chat.md` E-EC-7 (TES-7) · Schreiben über die Plan-Buddy-Termin-
Schnittstelle (PLAN-22, `PUT /api/v1/plan/termine`, TES-8) · der Trigger
als Eltern-Chat-Aufgabe (EC-8, EC-10, analog `familie-anlegen.md` FAA-12
und `kalender-verbinden.md` Trigger-Linie).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Termine erfragen** — eigene Funktion (`termine-erfragen.md` TER,
  Refs #143, gerade gemergt). TES schreibt, TER liest — getrennte Funktionen
  mit getrennten Verträgen.
- **Termin ändern** — die PLAN-22-Schnittstelle kennt zwar das `event_id`-
  Feld für Patch, V1 von TES nutzt aber ausschließlich das Anlegen
  (`action=created`). Eine eigene Funktion „Termin ändern" auf demselben
  PUT-Vertrag ist ein Folge-Ticket, sobald belegter Bedarf da ist (die
  Trefferquelle wäre dieselbe Funktion mit `event_id` aus einem vorherigen
  TER-Aufruf).
- **Termin löschen** — Plan-Buddy hat heute keinen DELETE auf der Termin-
  Schnittstelle (`plan/main.py` Z. 421ff. dokumentiert nur GET/PUT, vgl.
  PLAN-18 als Funktion *innerhalb* der App). Ein Lösch-Vertrag ist eigene
  Plan-Buddy-Erweiterung, dann eigene Eltern-Chat-Funktion.
- **Wiederkehrende Termine pflegen** (RRULE) — `plan.md` PLAN-17 löst
  wiederkehrende Termine auf Lese-Seite in Einzel-Vorkommen auf; eine
  Schreib-API für Regeln ist Plan-Buddy-Folge-Ticket.
- **Mehrere Kalender pflegen** — V1 schreibt in den einen konfigurierten
  Familien-Kalender (`plan.md` PLAN-15). Multi-Kalender-Wahl bleibt
  Plan-Buddy-Sache (`plan.md` OPEN-PLAN-F).
- **Termin-Erfassung aus einem Foto** (z. B. ein abfotografierter Schulplan)
  — eigene Funktion: `termine-aus-bild.md` (TAB, Refs #475). TAB schreibt
  als Bulk über `plan.md` PLAN-33; TES bleibt der Einzel-PUT-Pfad
  (PLAN-22). Benötigt mehrstufige Bild-Verarbeitung, die nicht zu dieser
  Funktion gehört.
- **PrivateChatSession-Refactor** zur SESS-Konvention — verfolgt unter
  einem eigenen Plattform-Ticket (PrivateChatSession-Refactor, Folge-
  Linie). TES verweist auf SESS-1..SESS-4 wie KAV und FAA es tun.

## 1. Die Funktion

### TES-1 — Termin eintragen ist eine aufrufbare Funktion
Termin eintragen ist eine klar abgegrenzte, **aufrufbare Funktion** mit
definierter Schnittstelle. **Eingang:** der Telegram-Privatchat des
Aufrufers (Chat-ID und Telegram-User-ID), die ID der gebundenen Familien-
Gruppe (`eltern-chat.md` EC-2) und — als Anstoß — der natürlichsprachige
Anfrage-Text (z. B. „trag Klettern Mila Donnerstag ein"). **Wirkung:** nach
bestätigtem Durchlauf ist im Familien-Kalender genau ein neuer Termin
angelegt, geschrieben über die Plan-Buddy-Termin-Schnittstelle
(`plan.md` PLAN-22). Die Funktion fasst Google nicht selbst an
(E-TES-2 analog `termine-erfragen.md` E-TER-2). **Ausgang:** ein Ergebnis-
Signal an den Aufrufer — „eingetragen" (Termin angelegt, mit der vom
Plan-Buddy zurückgegebenen `event_id`), „verworfen" (Aufrufer hat den
Vorschlag nicht bestätigt oder explizit abgelehnt, TES-7), „abgebrochen"
(Privatchat-Session-Timeout oder Prozess-Neustart, SESS-3/SESS-2),
„abgelehnt" (Berechtigung fehlt, TES-2), „nicht_erreichbar" (Plan-Buddy
nicht erreichbar oder PUT scheitert mit Server-Fehler, TES-9) oder
„unklar" (der Anfrage-Text ließ sich nicht zu einem schreibbaren
Termin verdichten und der Aufrufer hat die Rückfrage nicht beantwortet
oder abgebrochen, TES-4/TES-5). Die Funktion kennt ihren Aufrufer nicht
(E-TES-1).

*Tickets:* #144

### TES-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-
Mitgliedschaft, analog `eltern-chat.md` EC-2, `familie-anlegen.md` FAA-2,
`kalender-verbinden.md` KAV-2 und `termine-erfragen.md` TER-2. Ist er es
nicht, bricht die Funktion mit „abgelehnt" ab und schreibt nichts. Die
Prüfung liegt **bei der Funktion**, nicht beim Aufrufer — sonst hinge die
Berechtigungslogik am Trigger und die Funktion verlöre ihre Trigger-
Agnostik (E-TES-1).

*Tickets:* #144

## 2. Konversation

### TES-3 — Privatchat-Pflicht
Die Konversation läuft ausschließlich im Privatchat des Aufrufers (analog
`kalender-verbinden.md` KAV-3 und `familie-anlegen.md` FAA-12). Wird die
Funktion aus der Familien-Gruppe getriggert, antwortet die Aufrufer-Schicht
in der Gruppe mit einer kurzen Quittung („Ich frag dich gleich im
Privatchat") und startet die Funktion im Privatchat des `from_user_id`-
`TurnContext`. Vorschlag, Rückfragen, Korrekturen und das Bestätigungswort
laufen ausschließlich im 1:1-Chat zwischen Bot und Aufrufer.

Diese Privatchat-Pflicht weicht **bewusst** vom Pendant
`termine-erfragen.md` TER-3 ab — siehe E-TES-3. Begründung: TER ist
einstufig-lesend (Frage rein, Antwort raus) und für die Familien-Gruppe
unproblematisch; TES ist mehrstufig-schreibend (Vorschlag → Bestätigung
→ PUT) und unterliegt damit `eltern-chat.md` EC-20 (mehrstufige Aufgaben
überfluten die Familien-Gruppe nicht). In der Familien-Gruppe darf nur
der Anstoß und die fertige Quittung sichtbar werden, nicht die
Zwischenschritte.

Die Privatchat-Session folgt der Konvention
`conventions/privatchat-session.md` (SESS-1 Worker-Form, SESS-2
Zwischenzustand nur im Speicher, SESS-3 30-Minuten-Timeout → Ergebnis
„abgebrochen", SESS-4 Re-Prompt bei nicht-passender Eingabe) — wie KAV-6
und FAA-9 sie nutzen.

*Tickets:* #144

### TES-4 — Datums-Vokabular und Pflicht-Tag
Die Funktion ermittelt aus dem Anstoß-Text einen **einzelnen Termin-Tag**
(ISO-Datum). Das Datums-Vokabular ist hart-codiert (`eltern-chat.md` EC-12,
anbieter-unabhängige Regeln) und folgt dem Mindest-Vokabular aus
`termine-erfragen.md` TER-4 (geteilte Wahrheit, CLAUDE.md §6: kein Kopieren).
Konkret übernimmt TES aus TER-4 die Auflösung der Ausdrücke „heute",
„morgen" und der konkret benennbaren Wochentage; mehrdeutige Datums-
Ausdrücke (z. B. „nächsten Freitag" am Grenztag, ein konkretes Datum ohne
Jahr im Grenzbereich Jahreswechsel) lösen eine **gezielte Rückfrage** aus
(`eltern-chat.md` EC-22), statt blind zu raten.

Abweichend von TER-4 gibt es bei TES **keinen** Default-Zeitraum — der
Tag ist **Pflicht**, weil ein Termin sonst nicht eindeutig ist. Bleibt
der Tag auch nach einer Rückfrage ungeklärt (Aufrufer schweigt → SESS-3,
oder bricht ab), endet die Funktion mit Ergebnis „unklar" und schreibt
nichts. Wochenanker für „diese/nächste Woche" ist — wie in TER-4 —
Montag (`plan.md` PLAN-28 `wochenstart: 0`).

**Edge-Case Vergangenheit.** Liegt der ermittelte Tag in der Vergangenheit
(strikt vor `heute`), fragt die Funktion einmal kurz zurück, ob das
absichtlich ist; erst nach Bestätigung des vergangenen Datums (E-EC-7-
Wort) trägt sie es ein. So fängt sie versehentliche „letzten Freitag"-
Eingaben ab, ohne ein berechtigtes „trag den Arzttermin von gestern noch
ein" zu blockieren.

*Tickets:* #144

### TES-5 — Titel aus der Nutzer-Eingabe (V1: keine automatische Anreicherung)
Den Termin-Titel übernimmt die Funktion **roh** aus der Nutzer-Eingabe.
Schreibt der Aufrufer „trag Klettern Mila Donnerstag ein", wird `titel =
"Klettern Mila"` (mit dem von der Familie nach `plan.md` PLAN-19
gepflegten Namen im Titel — der Plan-Buddy macht daraus beim Lesen die
Personen-Zuordnung selbst). V1 fügt **nicht** automatisch einen Personen-
Namen an oder verändert die Titel-Form — Personen-Anhängen aus
strukturierter Nutzer-Eingabe ist Folge-Ticket (OPEN-TES-B).

Ist der Titel leer oder besteht er nur aus Datums-Vokabular (etwa „trag
morgen ein" ohne erkennbare Termin-Bezeichnung), fragt die Funktion
einmal nach dem Titel; bleibt er ungeklärt, endet die Funktion mit
Ergebnis „unklar" (TES-1).

Der konkrete Wortlaut der Rückfrage und der Anstoß-Parser leben im Code
als hart-codierte Strings (analog `kalender-verbinden.md` E-KAV-1: keine
LLM-Formulierung, weil die Eingabe-Verstehens-Schicht load-bearing ist).
Die Spec normiert das **Soll**: ein Titel ist Pflicht, leerer/datums-
gleicher Titel löst eine Rückfrage aus.

*Tickets:* #144

### TES-6 — Termin-Typ: ganztägig, zeitgebunden oder mehrtägig

Der Plan-Buddy-PUT-Vertrag (PLAN-22, #256) unterscheidet den Termin-Typ
über das Format von `beginn`:

- **Ganztägig (kein `T` in `beginn`):** `beginn = "YYYY-MM-DD"`, `ende`
  optional (`"YYYY-MM-DD"`). Fehlt `ende`, ist der Termin eintägig.
- **Zeitgebunden (`T` in `beginn`):** `beginn` und `ende` sind
  ISO-Datetime-Strings mit Offset, z. B. `"2026-06-04T14:00:00+02:00"`.
  `ende` ist **Pflicht**; `ende` muss nach `beginn` liegen.
- **Mehrtage (ganztägig + `ende`):** `beginn` = Starttag, `ende` =
  letzter Tag der Spanne (beide `YYYY-MM-DD`, `ende ≥ beginn`).

**Was die Funktion aus dem Anstoß ableitet:**

Enthält der Anstoß-Text ein **Uhrzeit-Vokabular** (Ausdrücke wie „um 14 Uhr",
„14:00", „von 14 bis 15 Uhr", „ab 9 Uhr"), erkennt der Parser die Uhrzeit
hart-codiert (analog TES-4/TES-5: keine LLM-Formulierung, EC-12) und
trägt den Termin **zeitgebunden** ein. Das Vokabular:

- **Startuhrzeit** (`HH:MM` oder `H Uhr` / `H:MM Uhr`, ganzzahlige Stunden):
  → `beginn = <datum>T<HH:MM>:00+<offset>`. V1 verwendet für den Offset fest
  die Default-Zeitzone `Europe/Berlin`; die familien-spezifische Zeitzone aus
  `plan.json` `zeitzone` zu lesen ist Folge-Ticket (OPEN-TES-E).
- **Enduhrzeit** (`bis HH:MM` / `bis H Uhr`): → `ende = <datum>T<HH:MM>:00+<offset>`.
  Liegt die Enduhrzeit vor der Startuhrzeit, wird sie als nächsten Tag
  interpretiert (Mitternachts-Übergang).
- **Dauer** (`für X Stunden` / `X h`): → `ende = beginn + X * 3600 s`.
- Nur Startuhrzeit ohne Enduhrzeit und ohne Dauer: eine **gezielte Rückfrage**
  (EC-22) nach der Enduhrzeit **oder einer Dauer**, da `ende` im zeitgebundenen
  Fall Pflicht ist (PLAN-22). Die Antwort wird mit demselben Uhrzeit-Vokabular
  geparst — sowohl eine Enduhrzeit (z. B. „bis 17 Uhr") als auch eine Dauer
  (z. B. „für eine Stunde", „1 h") ist gültig. Antwortet der Aufrufer nicht
  (SESS-3), endet die Funktion mit „unklar".

Enthält der Anstoß-Text eine **Mehrtages-Spanne** (Ausdrücke wie „von Montag
bis Mittwoch", „Dienstag und Mittwoch", „bis Freitag") und **keine** Uhrzeit,
trägt die Funktion den Termin als **ganztägige Spanne** ein:
`beginn = erster Tag`, `ende = letzter Tag` (beide `YYYY-MM-DD`).
Enddatum-Vokabular folgt dem Mindest-Vokabular aus TES-4/TER-4.

Enthält der Anstoß weder Uhrzeit noch Mehrtages-Spanne, trägt die Funktion
**ganztägig eintägig** ein — bisheriges V1-Verhalten, unverändert.

**Vorschlag und Bestätigung (TES-7)** benennen Typ, Tag(e) und ggf. Uhrzeit,
sodass die Familie sehen kann, was genau eingetragen wird.

*Tickets:* #144 · #289

### TES-7 — Vorschlag + Bestätigungswort vor dem Schreiben
Vor dem Schreiben legt die Funktion im Privatchat einen **strukturierten
Vorschlag** vor („Soll ich diesen Termin eintragen? — Titel: …, Tag: …")
und fordert eine Bestätigung nach dem Pattern aus `eltern-chat.md`
E-EC-7. Die Bestätigung folgt der für den ganzen Eltern-Chat gültigen
Wortliste (E-EC-7: 👍 inkl. Hautton-Varianten, ✅, ok, okay, k, jo, ja,
japp, jepp, passt, mach, machen, go, gogogo, los) — Vergleich case-
insensitiv, ganzes Wort, **deterministisch** und außerhalb des Agent-
Loops (E-EC-4).

Erst eine erkannte Bestätigung schaltet das Schreiben (TES-8) frei.
Antwortet der Aufrufer mit `falsch` (oder einer nicht-bestätigenden
Antwort wie „nein", „abbrechen"), wird **nicht** geschrieben — die
Funktion endet mit Ergebnis „verworfen" und der Familien-Kalender bleibt
unverändert. Eine **inhaltliche Korrektur** läuft über den
**EC-36-Korrektur-Dialog** (`specs/platform/eltern-chat.md` EC-36) —
nach `falsch` fragt der Bot „Was war falsch?", der User formuliert
die Korrektur („nee, doch Freitag") und der Bot baut einen neuen
Vorschlag (Re-Propose mit gepatchten Args, durch Confirm-Gate). Die
alte Vereinfachungs-Linie „kein Korrektur-Branch innerhalb derselben
Session" fällt damit für TES; **FAA-7 bleibt** für `familie_anlegen`
als Klasse-E-Auth-Loop unverändert.

Der konkrete Wortlaut des Vorschlags lebt im Code als hart-codierter
String; die Spec normiert das **Soll** (Vorschlag enthält Titel, den
oder die Tage sowie — bei zeitgebundenen Terminen — Anfangs- und
Endzeit; der Vorschlag ist eindeutig einem PUT zuordenbar und fordert
ein E-EC-7-Wort).

*Tickets:* #144

## 3. Konsumenten-Vertrag

### TES-8 — Schreiben über die Plan-Buddy-Termin-Schnittstelle (PLAN-22 PUT)
Nach Bestätigung (TES-7) schreibt die Funktion den Termin ausschließlich
über die Plan-Buddy-Termin-Schnittstelle aus `plan.md` PLAN-22:

- **Methode:** `PUT`.
- **Pfad:** `/api/v1/plan/termine` (URL-4-konform, Plural-Resource).
- **Body** (`Content-Type: application/json`): `{ "titel": <string,
  Pflicht>, "beginn": <ISO, Pflicht> [, "ende": <ISO, optional>] }`.
  Typ-Erkennung nach PLAN-22: kein `T` in `beginn` → ganztägig;
  `T` in `beginn` → zeitgebunden (`ende` dann Pflicht, Datetime mit
  Offset). Mehrtages-Spanne: ganztägig + `ende`-Datum. V1 setzt **kein**
  `event_id` — TES legt nur an, ändert nicht (siehe „Out-of-Scope V1").
  (Backward-Compat: das `datum`-Alias aus PLAN-22 ist im Konsumenten
  nicht mehr nötig — TES-8 schreibt immer `beginn`.)
- **Erfolgs-Antwort:** HTTP 200 mit JSON `{ "ok": true, "action":
  "created", "event_id": <string> }`. Die Funktion übernimmt die
  `event_id` ins Ergebnis-Signal (TES-1, Wert „eingetragen") — der
  Aufrufer kann sie für ein späteres Ändern/Löschen referenzieren (heute
  außerhalb des V1-Scopes, aber stabiles Vertrags-Element).
- **Fehler-Antworten** (vgl. `plan/main.py` Z. 441–458):
  - **HTTP 400** — (Defense-in-Depth) Plan-Buddy lehnt Body ab (fehlende
    Pflicht-Felder oder ungültiges Datum). Die Funktion wertet das als
    interner Fehler der eigenen Vorschlags-Konstruktion (TES-4/TES-5
    hätten das vorher abfangen müssen) und liefert „nicht_erreichbar" mit
    einer hart-codierten Ehrlich-Antwort im Privatchat. Der Termin ist
    nicht geschrieben.
  - **HTTP 502** — Plan-Buddy meldet `CalendarUnavailable`
    (Google-Kalender nicht erreichbar, PLAN-20). Ergebnis-Signal
    „nicht_erreichbar"; Privatchat-Antwort hart-codiert („Kalender ist
    gerade nicht erreichbar — bitte gleich nochmal probieren"). Termin
    nicht geschrieben.
  - **Connection-Fehler / HTTP-Status ≠ 200, 400, 502 / Antwort nicht
    parsbar / Plan-Buddy nicht installiert** (`plan.md` PLAN-23,
    `conventions/apps.md` APP-2) — Ergebnis „nicht_erreichbar", hart-
    codierte ehrliche Antwort, nichts geschrieben (vgl. TES-9).
- **Origin:** der konfigurierte Plan-Buddy-Origin — Loopback-Port aus
  `conventions/ports.md` PORT-2 (Plan-Buddy hört auf `127.0.0.1:5020`)
  bzw. die per Eltern-Chat-Konfiguration übersteuerbare Origin-URL
  (`eltern-chat.md` EC-15 `plan_origin_url`, derselbe Konfig-Wert wie
  TER-5 nutzt). Direkter Datei-Zugriff auf `plan.db` oder den Google-
  Kalender ist verboten (`conventions/apps.md` APP-3, `conventions/
  data-components.md` DCOMP-1).

Die Funktion hält **keinen eigenen Cache** der PUT-Antwort und führt
**kein eigenes Retry** — ein Retry-Verhalten gehört in den Plan-Buddy
(PLAN-20 entscheidet dort), nicht in den Konsumenten (E-TES-2,
einseitige Abhängigkeit analog `termine-erfragen.md` E-TER-2).

*Tickets:* #144 · #289

### TES-9 — Plan-Buddy nicht erreichbar
Schlägt der HTTP-Aufruf an die Plan-Buddy-Schnittstelle fehl (Connection
tot, HTTP-Status ≠ 200, Antwort nicht parsbar) oder ist der Plan-Buddy
gar nicht installiert (`plan.md` PLAN-23, `conventions/apps.md` APP-2),
liefert die Funktion das Ergebnis-Signal „nicht_erreichbar" zurück und
postet im Privatchat eine hart-codierte ehrliche Antwort — sie erfindet
keinen Termin und meldet **keinen** Erfolg (`eltern-chat.md` EC-7).
Bereits in der Bestätigungs-Phase geschriebener Zustand existiert nicht
(TES-7 hat kein persistentes Zwischenzeugnis, SESS-2). Der Aufrufer kann
den Aufruf jederzeit wiederholen.

Die Antwort benennt die fehlende Fähigkeit in der Sprache der Familie
(„Der Wochenplan ist gerade nicht erreichbar — ich konnte den Termin
nicht eintragen, bitte gleich nochmal probieren"); der konkrete
Wortlaut lebt im Code, die Spec normiert das Soll (Existenz einer
Antwort + keine Halluzination + kein stiller Abbruch).

*Tickets:* #144

### TES-12 — Erfolgs-Quittung im Privatchat nach erfolgreichem PUT
Liefert der Plan-Buddy-PUT HTTP 200 mit `{ "ok": true }`, postet die
Funktion im **Privatchat** des Aufrufers eine **deterministische**
Erfolgs-Quittung — kein Agent-Loop, keine Halluzination, kein optionaler
Satz. Der Wortlaut der Quittung hängt vom Termin-Typ ab:

- **Ganztägig/eintägig:** „Eingetragen ✅: {Titel} am {Datum}"
- **Zeitgebunden:** „Eingetragen ✅: {Titel} am {Datum}, {Startzeit} —
  {Endzeit} Uhr"
- **Mehrtägig:** „Eingetragen ✅: {Titel} von {Beginn} bis {Ende}"

Titel und Datum/Zeit stammen ausschließlich aus dem bestätigten Vorschlag
(TES-7) — keine erneute Auflösung. Der konkrete Wortlaut lebt im Code;
die Spec normiert das Soll (Existenz der Quittung + Termin-Typ-Differenzierung
+ kein stiller Abbruch). Die Quittung erscheint **im Privatchat**, nicht
in der Familien-Gruppe (TES-3).

*Tickets:* #282

## 4. Trigger

### TES-10 — Trigger als Eltern-Chat-Aufgabe (V1)
Solange noch kein anderer Aufrufer existiert, läuft der V1-Trigger der
Funktion als **Aufgabe im Aufgaben-Katalog des Eltern-Chats**
(`eltern-chat.md` EC-8) — analog `familie-anlegen.md` FAA-12,
`ca-verteilung.md` CAV-6 und `termine-erfragen.md` TER-10. Versteht der
Eltern-Chat-Agent die natürlichsprachige Bitte eines Familienmitglieds
(„trag Klettern Mila Donnerstag ein", „Schulausflug am Dienstag"), ruft
er die Funktion auf — die Familie muss keinen Tippbefehl lernen.

Die Aufgabe ist **schreibend** (EC-10, `WriteTask`): über die Funktion
landen neue Termine im Familien-Kalender. Das EC-10-Bestätigungs-Gate
*vor dem Aufgaben-Start* ist mit dem TES-eigenen Bestätigungs-Gate
(TES-7) **redundant** — die Spec macht hier wie `familie-anlegen.md`
FAA-12 **keine Ausnahme** und bleibt Pattern-treu. Die zweistufige
Bestätigung (einmal in der Gruppe „starte die Aufgabe", einmal im
Privatchat „trage den konkreten Termin ein") ist akzeptierter Aufwand
gegenüber Pattern-Bruch.

Die Berechtigung der Aufgabe deckt sich mit TES-2 (Live-Mitgliedschaft in
der Familien-Gruppe): die Aufgabe leitet die Live-Prüfung an die Funktion
durch, die ihre eigene Gate-Logik behält und der Trigger-Agnostik
(E-TES-1) nicht unterläuft. Die Aufgabe ist additiv im Sinne von EC-8 —
der bestehende Katalog bleibt unberührt. Der Privatchat-Wechsel folgt
`eltern-chat.md` EC-20 (mehrstufige Aufgaben überfluten die Familien-
Gruppe nicht).

*Tickets:* #144

## 5. Tests

### TES-11 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec mit Code-Verhalten hat einen automatisierten
Test (CLAUDE.md §6), reproduzierbar und **ohne Netz** — Telegram und die
Plan-Buddy-Termin-Schnittstelle werden durch kontrollierte Doppelungen
ersetzt, analog `eltern-chat.md` EC-17, `kalender-verbinden.md` KAV-10,
`termine-erfragen.md` TER-11, `plan.md` PLAN-29. Mindest-Abdeckung:

- **TES-1** — Aufruf mit minimalem Eingang (Privatchat-IDs + Anstoß-Text
  mit klarem Termin) liefert nach Bestätigung „eingetragen" mit der
  `event_id` aus der PLAN-22-Antwort; ein Aufruf ohne Privatchat-Chat-ID
  bricht ohne Wirkung ab.
- **TES-2** — Aufruf eines Nicht-Familien-Mitglieds wird abgelehnt; es
  wird **kein** PUT an PLAN-22 geschickt, das Ergebnis-Signal ist
  „abgelehnt".
- **TES-3** — Trigger aus der Familien-Gruppe startet die Konversation
  **nicht** in der Gruppe, sondern im Privatchat des `from_user_id`
  (Privatchat-Pflicht); ein Privatchat-Trigger startet direkt dort. Ein
  30-Minuten-Timeout in der laufenden Session beendet sie und liefert
  „abgebrochen" (SESS-3); ein Prozess-Neustart während der Session
  beendet sie ohne PUT (SESS-2).
- **TES-4** — die in TER-4 normierten Datums-Ausdrücke („heute",
  „morgen", konkrete Wochentage) lösen den dokumentierten `datum`-Wert
  im PUT-Body aus; ein mehrdeutiger Ausdruck löst eine Rückfrage aus
  statt eines blinden PUTs (EC-22-Verweis-Test); ein leerer/fehlender
  Tag endet mit „unklar" und löst keinen PUT aus; ein Tag in der
  Vergangenheit löst eine Rückfrage aus und schreibt erst nach
  E-EC-7-Bestätigung der Rückfrage.
- **TES-5** — der Titel aus dem Anstoß-Text wird **roh** in den PUT-Body
  übernommen (kein automatisches Anhängen eines Personen-Namens); ein
  leerer Titel oder ein Titel, der nur aus Datums-Vokabular besteht,
  löst eine Rückfrage aus.
- **TES-6** — Ganztägig eintägig: PUT-Body enthält `titel` und
  `beginn` (ISO-Datum ohne `T`), kein `ende`; Mehrtage: `beginn` +
  `ende` beide ISO-Datum; zeitgebunden: `beginn` und `ende` als
  ISO-Datetime mit Offset. Uhrzeit-Anstoß → zeitgebundener Body;
  Uhrzeit ohne Enduhrzeit/Dauer → Rückfrage nach Ende (EC-22), kein
  blinder PUT. Mehrtages-Anstoß ohne Uhrzeit → ganztägige Spanne.
  Anstoß ohne Uhrzeit und ohne Spanne → eintägig ganztägig wie bisher.
- **TES-7** — vor dem PUT wird ein Vorschlag im Privatchat gepostet, der
  Titel, den oder die Tage sowie — bei zeitgebundenen Terminen —
  Anfangs- und Endzeit enthält; erst ein E-EC-7-Wort als Antwort löst
  den PUT aus; eine nicht-bestätigende Antwort (z. B. „nein",
  „abbrechen", eine inhaltliche Korrektur) liefert „verworfen",
  **ohne** PUT; ein E-EC-7-Wort, das nicht eindeutig dem TES-Vorschlag
  zugeordnet werden kann (`eltern-chat/confirm.py` `PendingStore.take()`
  liefert `None`), löst keinen PUT aus.
- **TES-8** — der HTTP-Aufruf nutzt Methode `PUT`, Pfad
  `/api/v1/plan/termine`, Body `{titel, beginn [, ende]}` ohne
  `event_id`; ganztägig eintägig → nur `beginn`; zeitgebunden →
  `beginn`+`ende` als Datetime mit Offset; Mehrtage → `beginn`+`ende`
  als Datum; eine HTTP-200-Antwort mit `{ok: true, action: "created",
  event_id: ...}` übernimmt die `event_id` ins Ergebnis-Signal;
  HTTP 400 / HTTP 502 / Connection-tot / „Plan-Buddy nicht installiert"
  liefern alle „nicht_erreichbar" mit hart-codierter ehrlicher Antwort
  und **ohne** irgendeine Annahme über den Termin-Stand; kein eigener
  Retry.
- **TES-9** — eine fehlschlagende Plan-Buddy-Antwort (HTTP 502,
  PLAN-23-Szenario, Connection tot) postet die hart-codierte Ehrlich-
  Antwort im Privatchat und liefert „nicht_erreichbar"; keine
  Halluzination einer `event_id`.
- **TES-12** — nach einem erfolgreichen PUT liefert der Stub HTTP 200
  mit `{ok: true}`; im Privatchat erscheint für ganztägige Termine
  die eintägige Quittung mit Titel + Datum, für zeitgebundene die
  Uhrzeit-Variante und für Mehrtage die Spannen-Variante; keine der
  Varianten enthält halluzinierten Text außerhalb des bestätigten
  Vorschlags.
- **TES-10** — die EC-8-Aufgabe wird vom Aufgaben-Katalog gefunden und
  ist als `WriteTask` (EC-10) registriert; sie ruft TES mit den
  korrekten Parametern auf (Privatchat-Chat-ID und User-ID des
  Aufrufers, gebundene Familien-Gruppe) und reicht das Ergebnis-Signal
  an den Aufrufer zurück; ein Aufruf aus dem Familien-Gruppen-Chat
  adressiert die Konversation im Privatchat (EC-20), nicht in der
  Gruppe.

Läufe gegen den **echten** Plan-Buddy bzw. den echten Google-Kalender
sind opt-in und nicht Teil des Standard-Durchlaufs (analog
`eltern-chat.md` EC-17, `termine-erfragen.md` TER-11, `plan.md` PLAN-29).

*Tickets:* #144

---

## Offene Punkte

- ~~**OPEN-TES-A — Termine mit Uhrzeit.**~~ **Erledigt (#289).** PLAN-22
  (#256) nimmt jetzt `beginn`/`ende` als Datetime-Strings entgegen
  und legt zeitgebundene Termine an. TES-6 ist entsprechend erweitert
  (Uhrzeit-Vokabular + Mehrtages-Spanne). Dieses Offener Punkt ist
  geschlossen.

- **OPEN-TES-E — Familien-spezifische Zeitzone aus `plan.json`.** TES-6
  baut den Uhrzeit-Offset in V1 fest mit `Europe/Berlin`. Die familien-
  spezifische Zeitzone aus `plan.json` `zeitzone` zu lesen (und damit
  Familien außerhalb dieser Zone korrekt zu bedienen) ist Folge-Ticket.
  Offen ist dabei auch, ob der Konsument den Offset selbst setzt oder
  naive Datetimes sendet und der Plan-Buddy sie nach PLAN-22 auflöst
  (eine Wahrheit statt doppelter Offset-Berechnung).

- **OPEN-TES-B — Personen-Anreicherung im Titel.** TES-5 übernimmt den
  Titel roh, weil der Plan-Buddy beim Lesen ohnehin die Personen-
  Auflösung über Titel-Treffer macht (`plan.md` PLAN-19). Eine
  TES-seitige Anreicherung („für Mila" am Satz-Ende → automatisch
  `<titel> Mila`) ist denkbar, braucht aber einen klaren Konflikt-Pfad
  mit explizit getipptem Namen. Folge-Ticket sobald Familien beim
  Testen Personen falsch zuordnen, weil sie nicht selbst im Titel
  schreiben.

- **OPEN-TES-C — Konkrete Datumsangaben jenseits des Vokabulars.**
  TES-4 erbt das natürlichsprachige Vokabular von TER-4. Eine Anfrage
  mit konkretem ISO-Datum („am 2026-06-15") oder umgangssprachlichem
  Datum („am 15.6.") ist heute nicht spezifiziert — identisch zu
  `termine-erfragen.md` OPEN-TER-C. Auflösung gemeinsam mit OPEN-TER-C,
  damit beide Funktionen dasselbe Datum-Verständnis behalten.

- **OPEN-TES-D — Konflikt-Erkennung im Kalender.** TES legt einen
  Termin **additiv** an — ein gleichnamiger Termin am selben Tag würde
  Doppelung erzeugen. Eine Vor-Prüfung über `termine-erfragen.md` TER
  (vor dem Vorschlag fragen: „am Donnerstag steht schon X — trotzdem
  Y dazu?") wäre möglich, ist aber V1 nicht — die Spec entscheidet
  bewusst „erst den glatten Pfad bauen, dann auf belegten Konflikt-
  Schmerz reagieren". Folge-Ticket sobald eine Familie versehentlich
  doppelt einträgt.

---

## Entscheidungen

### E-TES-1 — Funktion ist trigger-agnostisch
*Datum:* 2026-05-29

Termin eintragen wird als eigenständige, trigger-agnostische **Funktion**
definiert — nicht als fest verdrahteter Eltern-Chat-Aufgaben-Schritt. Die
Funktion kennt ihren Aufrufer nicht; ihr Vertrag ist TES-1.

**Verworfen:** die Aufgabe direkt im Eltern-Chat-Skill-Code zu
implementieren, ohne sie als Funktion abzugrenzen. Wäre sie ein fester
Skill-Bestandteil, müsste sie für jeden weiteren Aufrufer (ein Display-
Widget, ein anderer Bot-Kanal, ein späterer Termin-aus-Foto-Skill, der
TES als Unter-Aufruf nutzt) neu geschrieben werden — die Trigger-Agnostik
ist die Wiederverwendungs-Garantie. Dasselbe Eigentümer/Nutzer-Muster
gilt für `ca-verteilung.md` (E-CAV-1), `familie-anlegen.md` (E-FAA-1),
`kalender-verbinden.md` (E-KAV-1) und `termine-erfragen.md` (E-TER-1).

### E-TES-2 — Konsument der Plan-Buddy-Schnittstelle, kein Direkt-Zugriff
*Datum:* 2026-05-29

Termine werden **ausschließlich** über die Plan-Buddy-Termin-Schnittstelle
geschrieben (`plan.md` PLAN-22, `PUT /api/v1/plan/termine`) — kein
eigener Google-Kalender-Adapter in dieser Funktion, kein direkter Datei-
Zugriff auf Plan-Daten.

**Begründung.** Der Plan-Buddy besitzt den Familien-Kalender (`plan.md`
E-PLAN-1, `specs/constitution.md` „App-Eigentümerschaft", `conventions/
apps.md` APP-1). Eine zweite Google-Anbindung in dieser Funktion wäre
eine zweite Wahrheit (CLAUDE.md §6) — Token-Refresh, Titel-Konvention
(PLAN-19), Personen-Auflösung würden auseinanderdriften. Der Konsumenten-
Pfad über PLAN-22 ist genau die einseitige Abhängigkeit, die
`conventions/apps.md` APP-3 einfordert; dieselbe Linie hält
`termine-erfragen.md` E-TER-2 für den Lese-Pfad.

**Verworfen:** ein eigener Retry-Loop in dieser Funktion. Plan-Buddy
entscheidet selbst (PLAN-20), wann ein Lese-/Schreib-Versuch endgültig
scheitert; ein zweiter Retry-Layer im Konsumenten würde dieselbe
Entscheidung doppelt treffen und die Diagnose verschmieren. Bei
„nicht_erreichbar" (TES-9) wiederholt der **Aufrufer** (Familie) den
gesamten Aufruf, nicht die Funktion intern.

### E-TES-3 — Privatchat-Pflicht, bewusste Abweichung von TER-3
*Datum:* 2026-05-29

Die Konversation läuft im Privatchat des Aufrufers (TES-3), analog
`kalender-verbinden.md` KAV-3 und `familie-anlegen.md` FAA-12. Diese
Privatchat-Pflicht weicht **bewusst** vom Pendant `termine-erfragen.md`
TER-3 ab, das die Antwort dort lässt, wo die Frage kam (auch in der
Familien-Gruppe).

**Begründung.** TES ist mehrstufig (Anstoß → ggf. Rückfragen zu Datum/
Titel → Vorschlag → Bestätigung → PUT) und **schreibend**. Genau für
diese Klasse legt `eltern-chat.md` EC-20 fest: mehrstufige schreibende
Aufgaben führen ihre Folge im Privatchat. In der Familien-Gruppe wären
Vorschlags-Nachricht, Bestätigungswort und Korrektur-Hin-und-her ein
Strom, der den normalen Familien-Chat überflutet — derselbe Schaden,
den FAA-12 und KAV-3 absorbieren. TER-3 wiederum darf in der Gruppe
bleiben, weil es einstufig-lesend ist (eine Frage, eine Antwort, keine
Familien-Daten verändert — E-TER-3 begründet das).

TES ist also kein TER-Spiegel mit umgedrehtem Vorzeichen, sondern erbt
seine Konversations-Form von der Schreib-/Mehrstufigkeits-Klasse —
identisch zu KAV und FAA, beide ebenfalls Privatchat-pflichtig.

**Verworfen:** den Vorschlag-/Bestätigungs-Dialog in der Familien-Gruppe
zu führen. Bricht EC-20 und macht aus der Bestätigung eine öffentliche
Geste, die andere Familienmitglieder unbeabsichtigt mit einem
E-EC-7-Wort auslösen könnten (E-EC-7 prüft case-insensitiv auf Wort-
Ebene — „ok" in einer unbeteiligten Nachricht würde der `PendingStore`
zwar nur bei genau einem offenen Vorschlag im Chat zuordnen, aber das
ist gerade der Normalfall). Privatchat schiebt diese Schiefe an die
Stelle, an der sie hingehört: die anstoßende Person bestätigt die
Aktion, sonst niemand.

### E-TES-4 — Datums-Vokabular geteilte Wahrheit mit TER-4
*Datum:* 2026-05-29

Das Datums-Vokabular (TES-4) **erbt** seine Auflösung von
`termine-erfragen.md` TER-4 — TES nennt nicht die einzelnen Ausdrücke
neu, sondern verweist auf TER-4 als autoritative Stelle. Folge: TES
weicht von TER-4 nur in den Punkten ab, die für eine **schreibende**
Funktion anders sind: Datum ist Pflicht (kein Default), Vergangenheit
löst eine Rückfrage aus (kein blindes Anlegen), kein Zeitraum, nur ein
einzelner Tag.

**Begründung.** Zwei Stellen, die dasselbe Vokabular pflegen, driften
auseinander (CLAUDE.md §6: kein Fakt zweimal). Wer in TER-4 einen
weiteren Ausdruck ergänzt („übermorgen", konkrete Datumsangaben aus
OPEN-TER-C), bekommt ihn in TES automatisch mit — und umgekehrt.

**Verworfen:** das TER-4-Vokabular in TES-4 zu duplizieren. Selbst mit
sorgfältigem Copy-Edit driften zwei Tabellen — und ein Eltern-Chat-
Skill, der morgen einen neuen Ausdruck versteht, soll nicht von zwei
unabhängigen Listen abhängen.

---

## Querverweise

- `eltern-chat.md` EC-2 (Familien-Gruppe als Berechtigung — TES-2),
  EC-7 (ehrliche Grenze — TES-9), EC-8 (Aufgaben-Katalog — Heimat des
  V1-Triggers TES-10), EC-10 (schreibende Aufgaben nach Bestätigung —
  Trigger-Pattern und TES-7-Anker), EC-12 (anbieter-unabhängige Regeln
  — TES-4, TES-5), EC-17 (Tests ohne Netz — TES-11), EC-20 (mehrstufige
  Aufgaben überfluten die Familien-Gruppe nicht — TES-3, E-TES-3), EC-22
  (gezielt fragen statt Varianten — TES-4 Rückfragen, TES-5 Titel-
  Rückfrage), E-EC-4 (Sicherheits-Gates deterministisch — TES-7),
  E-EC-7 (Bestätigungswort-Liste und -Pattern — TES-7).
- `eltern-chat-onboarding.md` ONB-3 (Privatchat als Eingabekanal —
  TES-3).
- `ca-verteilung.md` CAV-1 (Funktions-Muster — E-TES-1), CAV-6 (EC-8-
  Aufgabe als V1-Trigger — Pattern-Vorbild für TES-10), E-CAV-1
  (trigger-agnostische Funktion — E-TES-1).
- `familie-anlegen.md` FAA-1 (Aufruf-Schnittstelle — TES-1), FAA-2
  (Live-Berechtigungs-Prüfung — TES-2), FAA-7 (Bestätigungswort vor
  Schreiben — TES-7), FAA-9 (Privatchat-Session — TES-3), FAA-12
  (EC-8-Aufgabe als V1-Trigger — Pattern-Vorbild für TES-10), E-FAA-1
  (Trigger-Agnostik — E-TES-1), E-FAA-4 (V1-Trigger als EC-8-Aufgabe —
  Pattern-Vorbild für TES-10).
- `kalender-verbinden.md` KAV-1 (Aufruf-Schnittstelle — Vorbild für
  TES-1), KAV-2 (Live-Berechtigungs-Prüfung — Vorbild für TES-2),
  KAV-3 (Privatchat-Pflicht — Vorbild für TES-3, E-TES-3), KAV-6
  (Privatchat-Session-Muster — TES-3), E-KAV-1 (Trigger-Agnostik —
  E-TES-1).
- `termine-erfragen.md` TER-1 (Aufruf-Schnittstelle — Pendant-Form für
  TES-1), TER-3 (Antwort dort, wo die Frage kam — bewusst nicht
  übernommen, E-TES-3), TER-4 (Datums-Vokabular — geteilte Wahrheit
  für TES-4, E-TES-4), TER-5 (Konsumenten-Vertrag-Form — Vorbild für
  TES-8), TER-6 (Personen-Auflösung beim Plan-Buddy — TES-5-Hintergrund),
  TER-7 (Plan-Buddy nicht erreichbar — Vorbild für TES-9), TER-10
  (EC-8-Aufgabe als V1-Trigger — Pattern-Vorbild für TES-10), E-TER-1
  (Trigger-Agnostik — E-TES-1), E-TER-2 (Konsument der PLAN-22-
  Schnittstelle — E-TES-2), E-TER-3 (Antwort dort, wo die Frage kam —
  bewusst abweichend, E-TES-3 begründet die Abweichung).
- `plan.md` PLAN-15 (ein Familien-Kalender — TES-8 Konsumenten-Vertrag),
  PLAN-17 (normalisiertes Event-Modell — TES-8 Erfolgs-Antwort-Form),
  PLAN-18 (Events anlegen — als Funktion *innerhalb* des Plan-Buddys,
  TES schreibt sie über PLAN-22 nicht direkt), PLAN-19 (Titel-Konvention
  und Personen-Auflösung — TES-5 schreibt den rohen Titel, PLAN-19
  macht beim Lesen die Personen-Zuordnung), PLAN-20 (Kalender nicht
  erreichbar — TES-9 Hintergrund), PLAN-22 (Termin-Schnittstelle
  `PUT /api/v1/plan/termine` — TES-8 Konsumenten-Vertrag), PLAN-23
  (App-Existenz-Bindung — TES-9, TES-8), E-PLAN-1 (App besitzt Funktion
  und Schnittstelle — E-TES-2), E-PLAN-6 (Kalender-Anbindung gehört der
  Plan-Buddy-App — E-TES-2).
- `familie.md` FAM-2 (Familienmitglieder — Berechtigungs-Grundlage für
  TES-2 über `eltern-chat.md` EC-2).
- `conventions/apps.md` APP-1 (App besitzt Daten + Funktion +
  Schnittstelle — E-TES-2-Anker), APP-2 (App-Fähigkeit existiert nur,
  wenn die App installiert ist — TES-9), APP-3 (Andere Apps sprechen
  eine App nur über deren Schnittstelle an — TES-8, E-TES-2).
- `conventions/urls.md` URL-4 (API-Pfade — `/api/v1/plan/termine`-Form
  TES-8), URL-7 (Sprache — TES-Wortlaut).
- `conventions/ports.md` PORT-2 (Loopback-Port-Katalog — Plan-Buddy-
  Origin TES-8 auf `127.0.0.1:5020`).
- `conventions/data-components.md` DCOMP-1 (Komponenten reden über
  HTTP — TES-8 schreibt nicht direkt in `plan.db`).
- `conventions/privatchat-session.md` SESS-1..SESS-4 (Privatchat-Session-
  Muster — TES-3).
- `specs/constitution.md` (App-Eigentümerschaft — E-TES-2-Anker).
- `eltern-chat/confirm.py` (`PendingStore`, `is_confirmation` — Code-
  Stelle für das Bestätigungs-Pattern, das TES-7 wiederverwendet).
