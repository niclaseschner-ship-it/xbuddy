# Termine aus Bild — Spec     (ID-Präfix: TAB)

> Status: V1 · Refs #475, #524

Damit ein Elternteil im Eltern-Chat **mehrere Termine** aus einem
abfotografierten Plan (Schulplan, Kursplan, Vereins-Saisonübersicht) in den
Familien-Kalender schreiben kann, ohne die einzelnen Termine selbst tippen zu
müssen, definiert diese Spec **Termine aus Bild als aufrufbare Funktion**:
Aufgerufen mit einem Bild und einem Signalwort, schickt sie das Bild an einen
multimodalen KI-Anbieter, extrahiert daraus eine Liste von Termin-Vorschlägen,
legt der Familie diese Liste im Telegram-Privatchat des Aufrufers vor und
trägt sie nach **einer** ausdrücklichen Bestätigung als **Bulk** über die
Plan-Buddy-Termin-Schnittstelle (`plan.md` PLAN-33 — Bulk-Schreib-Endpoint,
neue Klausel im Rahmen #475) in den Familien-Kalender ein.

Es ist eine **schreibende, mehrstufige** Aufgabe (`eltern-chat.md` EC-10,
EC-20): die Funktion verändert Familien-Daten und darf erst nach einer
ausdrücklichen Bestätigung wirken. Die Funktion ist **trigger-agnostisch**
(E-TAB-1 analog `termin-eintragen.md` E-TES-1): wer sie aufruft — eine
Eltern-Chat-Aufgabe heute, ein anderer Aufrufer später — ist nicht Teil ihres
Vertrags.

**Abgrenzung zu `termin-eintragen.md` (TES) und `foto-senden.md` (FSE).** TES
trägt **einen** Termin aus natürlichsprachigem Text ein, TAB **mehrere
Termine aus einem Bild**. FSE übernimmt ein **kommentarloses** Medium in die
Photo-Library; TAB greift, wenn ein Medium **mit Signalwort** kommt (siehe
TAB-4 — Disambig zu `foto-senden.md` FSE-3). Photo-Buddy wird in TAB nicht
involviert; das Bild wird nach der Extraktion verworfen (E-TAB-5).

**V1-Scope:** ein Bild je Aufruf · Signalwort-Trigger (TAB-4) · Privatchat-
Pflicht (TAB-3) · Berechtigung live geprüft (TAB-2) · multimodale Extraktion
über den konfigurierten KI-Anbieter (TAB-5) · LLM-Output-Validierung mit
Plausi-Fenster (TAB-6) · Sammel-Vorschlag mit **einem** Bestätigungswort
(TAB-7, E-EC-7) · gezielte Lücken-Sammel-Rückfrage in einer Runde mit
deterministischem Parser für Pflichtfelder (TAB-8) · Schreiben als **Bulk**
über PLAN-33 (TAB-9) · Erfolgs-Quittung „N von M eingetragen" (TAB-11) ·
Registrierung als Eltern-Chat-Aufgabe (TAB-12, `conventions/tasks.md`
TASK-7 + TASK-4 `WriteTask` propose→confirm).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Termin aus URL oder Screenshot eines Web-Plans** — eigene Funktion,
  siehe V2-Block unten. Risiken (SSRF, Auth-Walls, beliebige Seiten) werden
  in V2 mit Whitelist gelöst, nicht in V1.
- **Termin-Konflikt-Erkennung** — TAB legt Termine **additiv** an. Eine
  Vor-Prüfung gegen bestehende Termine („am Donnerstag steht schon X")
  wäre möglich, ist aber V1 nicht (OPEN-TAB-Konflikt).
- **Mehrere Bilder hintereinander** — V1 verarbeitet ein Bild je Aufruf.
  Eine Skill-Queue (Mehr-Bilder-Folge in einer Session) ist Folge-Ticket
  (OPEN-TAB-Queue).
- **Personen-Anreicherung der Termin-Titel** — TAB-8.2 hängt **keine**
  Namen automatisch an Termin-Titel an; siehe E-TAB-Personen-Hinweise und
  `termin-eintragen.md` OPEN-TES-B (Personen-Anreicherung im Titel — heute
  nicht in TES und nicht in TAB).
- **Termin-Erfassung aus Plan-Text** (kopierter Schulplan-Text statt Foto)
  — heute durch TES (`termin-eintragen.md`) für einzelne Termine
  abgedeckt; eine Bulk-Variante aus reinem Text ohne Bild ist eigenes
  Ticket, sobald belegter Bedarf da ist.

## 1. Die Funktion

### TAB-1 — Termine aus Bild ist eine aufrufbare Funktion
Termine aus Bild ist eine klar abgegrenzte, **aufrufbare Funktion** mit
definierter Schnittstelle, analog `termin-eintragen.md` TES-1. **Eingang:**
der Telegram-Privatchat des Aufrufers (Chat-ID und Telegram-User-ID), die
ID der gebundenen Familien-Gruppe (`eltern-chat.md` EC-2), das **Bild** als
Telegram-Datei-ID (oder direkter Byte-Strom — der Aufrufer entscheidet,
welche Form er liefert) und der **Begleittext** des Bildes (das Caption-
Feld der Telegram-Nachricht; mindestens ein Signalwort, siehe TAB-4).
**Wirkung:** nach bestätigtem Durchlauf sind im Familien-Kalender bis zu
N Termine angelegt, geschrieben über die Plan-Buddy-Bulk-Termin-
Schnittstelle (`plan.md` PLAN-33). Die Funktion fasst Google nicht selbst
an (analog `termin-eintragen.md` E-TES-2). **Ausgang:** ein Ergebnis-Signal
an den Aufrufer — „eingetragen" (mit `geschrieben` und `gesamt` als
Zähler aus der Bulk-Antwort), „verworfen" (Aufrufer hat den Sammel-
Vorschlag nicht bestätigt), „abgebrochen" (Privatchat-Session-Timeout
oder Prozess-Neustart, SESS-3/SESS-2), „abgelehnt" (Berechtigung fehlt,
TAB-2), „nicht_erreichbar" (Plan-Buddy nicht erreichbar **bevor** der
Bulk-Aufruf das Schreiben erreicht hat, TAB-10), „**unbekannt**"
(Plan-Buddy-Verbindung **mitten** im Bulk-Aufruf abgerissen — der Server
schreibt threaded weiter, die Funktion weiß nicht, welche Items gelandet
sind, TAB-10), „provider_fehler" (KI-Anbieter nicht erreichbar oder
Extraktion liefert keinen verwertbaren Output, EC-14 + TAB-6) oder
„unklar" (Pflichtfeld-Lücken auch nach zwei Rückfrage-Runden ungeklärt,
TAB-8.3). Die Funktion kennt ihren Aufrufer nicht (E-TAB-1).

*Tickets:* #475

### TAB-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-
Mitgliedschaft, analog `eltern-chat.md` EC-2, `termin-eintragen.md` TES-2,
`foto-senden.md` FSE-2. Ist er es nicht, bricht die Funktion mit
„abgelehnt" ab und schreibt nichts; das Bild wird auch nicht an den
KI-Anbieter geschickt. Die Prüfung liegt **bei der Funktion**, nicht beim
Aufrufer — sonst hinge die Berechtigungslogik am Trigger und die Funktion
verlöre ihre Trigger-Agnostik (E-TAB-1).

*Tickets:* #475

## 2. Trigger und Konversation

### TAB-3 — Privatchat-Pflicht
Die Konversation läuft ausschließlich im Privatchat des Aufrufers (analog
`termin-eintragen.md` TES-3, `kalender-verbinden.md` KAV-3,
`familie-anlegen.md` FAA-12). Wird die Funktion aus der Familien-Gruppe
getriggert (das Bild kam in der Gruppe an), antwortet die Aufrufer-Schicht
in der Gruppe mit einer kurzen Quittung („Ich frag dich gleich im
Privatchat") und startet die Funktion im Privatchat des `from_user_id`-
`TurnContext`. Sammel-Vorschlag, Lücken-Rückfrage, Korrekturen und das
Bestätigungswort laufen ausschließlich im 1:1-Chat zwischen Bot und
Aufrufer.

Begründung: TAB ist mehrstufig-schreibend und unterliegt damit
`eltern-chat.md` EC-20 (mehrstufige Aufgaben überfluten die Familien-
Gruppe nicht). Das ist dieselbe Linie wie TES-3 (E-TES-3) — siehe E-TAB-3.

Die Privatchat-Session folgt `conventions/privatchat-session.md` (SESS-1
Worker-Form, SESS-2 Zwischenzustand nur im Speicher, SESS-3 30-Minuten-
Timeout → Ergebnis „abgebrochen", SESS-4 Re-Prompt bei nicht-passender
Eingabe) — wie KAV-6, FAA-9 und TES-3 sie nutzen.

*Tickets:* #475

### TAB-4 — Signalwort-Hinweis im Tool-Schema, Disambig zu `foto-senden.md` FSE-3
Die Trigger-Wahl folgt der bestehenden Linie aus `foto-senden.md` FSE-3:
**das LLM entscheidet im Tool-Wahl-Schritt** (`eltern-chat.md` EC-`tool_use`),
welche Funktion ein eingehendes Bild bedient — es gibt **keinen
deterministischen Pre-Router**, der Bilder vor dem LLM-Schritt einsortiert.
TAB ist eine Aufgabe **neben** FSE im Aufgaben-Katalog (EC-8); welche
Aufgabe das LLM aufruft, hängt von Bild **und** Begleittext ab.

Damit das LLM die richtige Aufgabe wählt, sind die Tool-Beschreibungen
beider Aufgaben so geschnitten, dass sie sich **nicht überlappen**:

- **Foto-Senden (FSE)** ist im Tool-Schema beschrieben als „Foto/Video
  **ohne Begleittext** in die Photo-Library" (FSE-3 unverändert).
- **Termine-aus-Bild (TAB)** ist im Tool-Schema beschrieben als
  „Foto **mit einem Signalwort im Begleittext** in den Familien-Kalender".
  Die Tool-Beschreibung nennt eine **hart-codierte Liste** von Signalwörtern
  (V1: `termin`, `termine`, `kalender`, `eintragen`, `plan`, `schulplan`,
  `kursplan` — der Code hält die exakte Liste, die Spec normiert das
  **Soll**: die Liste ist hart-codiert, deutsch, und enthält mindestens
  diese Wörter). Die Beschreibung weist das LLM ausdrücklich an: trifft
  **kein** Signalwort, **nicht** TAB aufrufen. Umgekehrt: **bei Foto mit
  Termin-Signalwort ruft das LLM `termine_aus_bild` zwingend auf und
  erfindet keine Termine aus dem Gesprächskontext oder eigenem Wissen** —
  das Bild ist die alleinige Quelle (Ref #1334, #1387).

Die Signalwort-Liste lebt im Code als hart-codierter String-Tupel und
fließt **in die Tool-Schema-Beschreibung** ein (nicht in einen
deterministischen Pre-Router-Code). Sie ist load-bearing für die Wahl,
aber die Wahl selbst trifft das LLM — wie bei jeder anderen Aufgabe im
Katalog (EC-8, E-EC-6 Adapter-Form). Das ist konsistent zur
`foto-senden.md` FSE-3-Linie („Die Entscheidung trifft das LLM beim
Tool-Wahl-Schritt, kein Vor-Router").

**Folge für die Tests (TAB-13):** der Anbieter-Stub muss prüfen, dass
das Tool-Schema die Signalwort-Liste in der Beschreibung trägt; ein
End-to-End-Test mit echtem Anbieter (opt-in, EC-17) verifiziert, dass
die Wahl bei „Bild + Signalwort" auf TAB und bei „Bild ohne Begleittext"
auf FSE fällt.

*Tickets:* #475

## 3. Extraktion

### TAB-5 — Multimodal-Pipeline über den konfigurierten Provider-Adapter
Die Funktion extrahiert die Termin-Liste aus dem Bild über den **für die
Instanz konfigurierten KI-Anbieter** (`eltern-chat.md` EC-11, EC-13), nicht
über eine eigene OCR-Schicht. Konkret:

- Der Aufruf läuft über die geteilte LLM-Provider-Lib `tools.llm` —
  `get_singleshot(<foto-slot>).complete_structured(system, prompt, schema, images=[…])`
  (LLMP-S1, Bild-Content additiv; **kein** eltern-chat-Text-Adapter, **kein**
  skill-lokaler `_multimodal/`-Adapter mehr — E-TAB-8, #1262). Der Foto-Slot ist ein
  **eigener** ZD-Slot (`eltern-chat-anthropic-foto-analyse-api-key`, ZD-2/LLMP-5),
  gepinnt auf Claude; Anbieter-Wechsel via Vendor-Segment ohne Code. Übergeben werden
  ein `image`-Content-Block (`bytes` + `media_type`) und ein hart-codiertes Tool-Schema
  (forced `tool_use`), das die Antwort als JSON-Liste von Termin-Vorschlägen erzwingt
  (`titel`, `beginn`, `ende?`, `ganztags`, `personen_hinweise?` — die Felder spiegeln
  das PLAN-22-PUT-Schema, soweit aus dem Bild ableitbar).
- Das Tool-Schema ist hart-codiert, nicht modell-formuliert (analog
  `termin-eintragen.md` TES-7). Damit ist die Schnittstelle stabil und
  testbar.
- Der konkrete Inhalt des System-Prompts und die Wahl des konkreten
  Modells leben im Code; die Spec normiert das **Soll**: ein
  multimodaler Aufruf mit einem `image`-Block und einem Tool-Schema,
  das eine validierbare Liste zurückgibt.
- Die Foto-Route hat ihren **eigenen** Anbieter-Slot (E-TAB-8, #1262), entkoppelt
  vom Text-Chat-Provider (EC-11): so kippt sie nicht mehr mit einem Wechsel des
  Chat-Default-Providers mit. Der historische „zweite Adapter-Slot multimodal" aus
  E-TAB-6 ist damit realisiert — jetzt als `tools.llm`-(vendor,purpose)-Slot statt als
  skill-lokaler `_multimodal/`-Ordner.
- **Begleittext (Telegram-Caption) als Verfeinerungs-Hinweis (#528).**
  Trägt die Nachricht einen Begleittext, ist dieser ein **User-Hinweis
  an die Extraktion** — Beispiele: „Jahr 2026 verwenden", „nur die
  Geburtstage", „ohne die Wochenenden". Der Anbieter-Adapter wendet
  den Hinweis auf das aus dem Bild Extrahierte an (Jahres-Override,
  Filter-Auswahl, …), er erfindet **keine** Termine, die nicht im Bild
  stehen. Fehlt eine Information im Bild (z. B. die Jahreszahl in
  einem Saison-Plan), ist der Begleittext die zulässige Quelle, die
  Lücke zu schließen; sonst bleibt das Feld leer (E-TAB-5-Disziplin
  „Erfinde nicht"). Wortlaut von System-Prompt und Tool-Schema-
  Description leben im Code — die Spec normiert das **Soll**: Caption
  ist Steuer-Kontext, nicht Erfinden-Auftrag.

Datenlinie (was an den Anbieter geht): das Bild selbst, der Begleittext
und das Tool-Schema. Darüber hinausgehende Familien-Daten gehen nicht an
den Anbieter (`eltern-chat.md` EC-13). Das Bild selbst wird nach der
Extraktion **nicht persistiert** und nicht an den Photo-Buddy weiter-
gereicht (E-TAB-5).

Fehler-Verhalten: schlägt der Anbieter-Aufruf fehl (Timeout, HTTP-Fehler,
ungültige JSON-Antwort, leere Tool-Output-Struktur, kein verwertbares
`image`-Verständnis), liefert die Funktion das Ergebnis-Signal
„provider_fehler" zurück und postet eine hart-codierte ehrliche Antwort
im Privatchat (analog `eltern-chat.md` EC-14). Kein eigener Retry.

*Tickets:* #475

### TAB-6 — LLM-Output-Validierung
Die vom Anbieter zurückgegebene Termin-Liste wird **vor** dem Sammel-
Vorschlag deterministisch validiert (außerhalb des Agent-Loops,
`eltern-chat.md` E-EC-4):

- **Plausi-Fenster:** Jeder Termin-Tag muss im Intervall
  `[heute - 400 Tage, heute + 2 Jahre]` liegen. Termine außerhalb des
  Fensters werden verworfen — sie sind mit überwiegender Wahrscheinlichkeit
  LLM-Fehlausgaben (Modell-Halluzination einer Jahreszahl, fehlinterpretierte
  Tabellen-Kopfzeile). Begründung 400 Tage (~13 Monate) rückwärts:
  Kita-/Schulpläne werden saisonsweise wiederverwendet — ein „Juni 2025"-
  Wochenplan wird im Juni 2026 erneut ausgehängt; das bisherige 30-Tage-
  Fenster hat solche Pläne als „unklar" abgelehnt (Live-Bug, Refs #524).
  400 Tage decken eine volle Saison plus Reserve ab; Termine älter als
  ~13 Monate sind auch bei Wiederverwendung keine plausiblen Einträge mehr.
  Begründung 2 Jahre vorwärts: Schul-/Vereins-Saisonpläne reichen bis zu
  einem Schuljahr, ein zweites als Reserve.
- **Schema-Vollständigkeit:** Jeder Termin muss `titel` (nicht leer) und
  `beginn` (gültiges ISO-Datum oder ISO-Datetime) enthalten — sonst
  wandert er in den Lücken-Sammler (TAB-8.1).
- **Leere Liste:** Liefert der Anbieter nach der Filterung eine **leere**
  Liste — alle Termine außerhalb des Fensters oder gar keine Termine
  extrahiert —, endet die Funktion mit Ergebnis „unklar" und postet eine
  hart-codierte ehrliche Antwort im Privatchat („Aus dem Bild konnte ich
  keine Termine ablesen — bitte gleich nochmal versuchen oder einzeln
  tippen", `eltern-chat.md` EC-7). Das **schreibt nichts**.
- **Robuste Erkennung, nicht reines OCR:** Die Spec normiert ausdrücklich,
  dass das LLM **Tabellen UND Fließtext** verstehen können soll — ein
  Schulplan ist meist eine Tabelle, eine Kursplan-Notiz meist Fließtext.
  Eine OCR-Schicht, die nur Text-Bounding-Boxen liefert, reicht **nicht**
  — TAB-5 verlangt eine multimodale Pipeline, weil die Struktur (welche
  Zeile ist welcher Termin) Teil der Extraktion ist.

Der konkrete Validierungs-Code lebt im Eltern-Chat; die Spec normiert das
**Soll** (Existenz der Validierung, Plausi-Fenster-Grenzen `heute-400d`
bis `heute+2J`, Verhalten bei leerer Liste).

*Tickets:* #475, #524

## 4. Konversation

### TAB-7 — Sammel-Vorschlag mit einem Bestätigungswort
Vor dem Schreiben legt die Funktion im Privatchat **einen einzigen
Sammel-Vorschlag** vor, der **alle** extrahierten Termine als nummerierte
Liste enthält, und fordert **ein** Bestätigungswort nach dem Pattern aus
`eltern-chat.md` E-EC-7. Die Liste wird als HTML-`<pre>`-Block formatiert
(monospace, kopierbar). TAB-7 **aktiviert** dafür den HTML-Modus pro
Nachricht (siehe `eltern-chat.md` EC-27 — HTML ist opt-in, nicht Default)
und **escaped** dynamisch eingesetzte Termin-Titel vor dem Senden
(`<`/`>`/`&` → `&lt;`/`&gt;`/`&amp;`), damit Titel mit `<` oder `&`
die `<pre>`-Klammer nicht zerstören.

Form des Sammel-Vorschlags:

```
Soll ich diese Termine eintragen?

1) <Datum> — <Titel> [— <Uhrzeit-Spanne, falls zeitgebunden>]
2) <Datum> — <Titel> [— <Uhrzeit-Spanne>]
…
N) <Datum> — <Titel> [— <Uhrzeit-Spanne>]
```

Erst eine erkannte Bestätigung (E-EC-7-Wort: ok, ja, passt, …) schaltet
das **Bulk-Schreiben** (TAB-9) frei. Die Bestätigung gilt für die **ganze**
Liste — siehe E-TAB-4. Antwortet der Aufrufer mit `falsch` (oder einer
nicht-bestätigenden Antwort wie „nein", „abbrechen"), wird **nicht**
geschrieben — die Funktion endet mit Ergebnis „verworfen" und der
Familien-Kalender bleibt unverändert. V1 hat **keinen** selektiven Streich-
Pfad innerhalb der Bestätigung („nur 1, 2 und 5"); eine **inhaltliche
Korrektur** läuft über den **EC-36-Korrektur-Dialog**
(`specs/platform/eltern-chat.md` EC-36) — nach `falsch` fragt der Bot
„Was war falsch?", der User formuliert die Korrektur (z. B. „alle Termine
einen Tag nach vorne") und der Bot baut einen neuen Sammel-Vorschlag.
Die alte Vereinfachungs-Linie „kein Korrektur-Branch in derselben
Session" (vorher analog TES-7 / FAA-7) fällt damit für TAB; **FAA-7
bleibt** für `familie_anlegen` als Klasse-E-Auth-Loop unverändert
(Auth-Identität braucht Schritt-für-Schritt-Folge, kein Patch-
Re-Propose).

Der konkrete Wortlaut des Sammel-Vorschlags lebt im Code als hart-
codierter String; die Spec normiert das **Soll** (nummerierte Liste mit
Datum + Titel + ggf. Uhrzeit-Spanne, im `<pre>`-Block, **ein** E-EC-7-
Wort bestätigt alles).

**Vergangenheits-Hinweis-Klausel (Refs #524):** Liegen **mindestens ein**
der gefilterten Termine vor dem heutigen Datum (beginn_date < heute, aber
innerhalb des Plausi-Fensters — also nicht verworfen), **stellt die
Funktion dem Sammel-Vorschlag einen Hinweis-Header voran**. Wortlaut
(hart-codiert, V1):

```
ℹ️ Hinweis: N der M Termine liegen vor heute. Mit ja eintragen, mit nein verwerfen.
```

Begründung: die Familie soll sofort sehen, dass der Plan vergangenheitliche
Termine enthält (typisch bei saisonsweise wiederverwendeten Kita-/Schulplänen,
Live-Bug Refs #524) — und bewusst bestätigen oder verwerfen. Der KI-
formulierte Hinweis (angepasster Wortlaut je Kontext) ist V2 (Refs #525).

*Tickets:* #475, #524

### TAB-8 — Lücken-Sammel-Rückfrage bei unvollständigen Pflichtfeldern

#### TAB-8.1 — Pflichtfeld-Lücken werden gesammelt einmal abgefragt
Hat die LLM-Extraktion (TAB-5) bei einem oder mehreren Termin-Vorschlägen
Pflichtfelder leer gelassen (`titel` leer, `beginn` fehlt oder ist
ungültig) oder ist ein zeitgebundener Termin ohne `ende` (PLAN-22:
`ende` ist bei zeitgebundenen Terminen Pflicht), legt die Funktion **vor**
dem Sammel-Vorschlag eine **gezielte Lücken-Rückfrage** im Privatchat
vor: **eine** Nachricht mit allen Lücken auf einmal, kopierbar
strukturiert mit `[?]`-Sentinels für jedes fehlende Feld. Form:

```
Bei diesen Terminen fehlt mir noch etwas — bitte die [?] ersetzen:

3) <Datum> — [?titel?] — <Uhrzeit-Spanne falls vorhanden>
7) <Datum> — Sportfest — bis [?endzeit?]
```

(Die Sentinel-Form ist bewusst **eckig** statt spitz gewählt — eckige
Klammern kollidieren nicht mit Telegrams HTML-Modus EC-27 und brauchen
kein Escape. Spitze `<?>`-Sentinels würde Telegram als unbekanntes Tag
ablehnen.)

Der Aufrufer kopiert die Vorlage, ersetzt die `[?…?]`-Sentinels durch
seine Antworten und sendet die Nachricht zurück. Der Parser ist
**deterministisch** (außerhalb des Agent-Loops, `eltern-chat.md` E-EC-4):
er liest die Zeilen anhand der Nummer und ersetzt die Sentinels durch den
Inhalt der entsprechenden Zeile in der Antwort. Schlägt der Parser fehl
(Zeilen-Nummern stimmen nicht überein, Sentinel-Form nicht mehr da, neuer
ungültiger Wert), fordert die Funktion eine erneute Korrektur an (siehe
TAB-8.3, max 2 Runden insgesamt).

Begründung des Sentinel-Pfads: der Aufrufer **sieht** alle Lücken auf
einmal (keine Hin-und-her-Sequenz von N Einzelrückfragen) und der Parser
kann die Antwort eindeutig zuordnen, weil die Struktur erhalten bleibt.
Das ist die Lego-Variante einer Lücken-Abfrage — kopierbar statt
zeilenweise.

#### TAB-8.2 — Personen-Hinweise sind nie Pflicht; keine automatische Titel-Anreicherung
Wenn die LLM-Extraktion `personen_hinweise` zurückgibt (etwa „für Mila",
„Klasse 3b"), trägt die Funktion diese **nicht** automatisch in den
Termin-Titel ein. `personen_hinweise` sind **nie** Pflicht und führen
**nie** zu einer Lücken-Rückfrage (TAB-8.1). Wer Personen-Bezug im Titel
haben will, schreibt den Namen selbst — entweder im Kopier-Pfad (Sentinel
ersetzen) oder, wenn der Vorschlag schon vollständig war, durch
Verwerfen + neuer Aufruf.

Begründung: diese Linie respektiert `termin-eintragen.md` OPEN-TES-B
(`specs/platform/termin-eintragen.md:471-478` — Personen-Anreicherung im
Titel ist heute auch in TES nicht implementiert; eine TAB-seitige
Anreicherung würde TES überholen und die TES/TAB-Konvergenz aufbrechen).
Plan-Buddy macht beim **Lesen** ohnehin die Personen-Auflösung über
Titel-Treffer (`plan.md` PLAN-19) — die Familie pflegt den Namen im Titel
nach, wenn sie ihn braucht.

#### TAB-8.3 — Maximal zwei Rückfrage-Runden
Bleibt eine Pflicht-Lücke auch nach **zwei** Rückfrage-Runden ungeklärt
(Aufrufer antwortet nicht parsbar, antwortet mit weiterem `[?]`, oder
antwortet gar nicht → SESS-3-Timeout in der laufenden Session), endet die
Funktion mit Ergebnis „unklar" und schreibt **nichts**. Eine erfolgreiche
Erstklärung **einer** Lücke nach der ersten Runde lässt verbleibende
Lücken in die zweite Runde — gezählt werden Rückfrage-**Nachrichten**, nicht
Lücken-**Felder**. Begründung der Obergrenze: nach zwei Runden ist
spürbar, dass das Bild für den Bot nicht hinreichend lesbar ist; weitere
Runden ermüden den Aufrufer und treffen meist auf dasselbe Verstehens-
Problem.

*Tickets:* #475

## 5. Konsumenten-Vertrag

### TAB-9 — Bulk-Schreiben über die Plan-Buddy-Termin-Schnittstelle (PLAN-33)
Nach Sammel-Bestätigung (TAB-7) schreibt die Funktion die Termine
**ausschließlich** als **einen** Bulk-PUT über die neue Plan-Buddy-Bulk-
Termin-Schnittstelle aus `plan.md` PLAN-33:

- **Methode:** `POST`.
- **Pfad:** `/api/v1/plan/termine/bulk` (URL-4-konform, Plural-Resource
  + Sub-Resource).
- **Body** (`Content-Type: application/json`): `{ "request_id": "<UUIDv4>",
  "items": [ <PLAN-22-PUT-Body>, … ] }` — `request_id` ist Pflicht
  (Idempotenz, PLAN-33.5), `items` ist eine nicht-leere Liste von Termin-
  Bodies in der gleichen Form wie PLAN-22-PUT (`titel`, `beginn`,
  `ende?`), maximal 30 Items je Aufruf (Server-Cap PLAN-33.3).
- **Antwort:** HTTP 200 mit JSON `{ "ok": true, "geschrieben": <N>,
  "gesamt": <M>, "results": [ { "ok": true, "event_id": "<id>" } |
  { "ok": false, "error_code": "<code>" }, … ] }`. Die Reihenfolge der
  `results` entspricht der Reihenfolge der `items` im Request.
- **Origin:** der konfigurierte Plan-Buddy-Origin — `eltern-chat.md`
  EC-15 `plan_origin_url` (derselbe Konfig-Wert wie TES-8 und TER-5),
  Loopback-Port `127.0.0.1:5020` als Default (`conventions/ports.md`
  PORT-2). Direkter Datei-Zugriff auf `plan.db` oder den Google-Kalender
  ist verboten (`conventions/apps.md` APP-3, `conventions/data-
  components.md` DCOMP-1).

Die Funktion führt **keinen** eigenen Retry — Retry-Verhalten gehört in
den Plan-Buddy (PLAN-33.6 Exponential Backoff für 403/429), nicht in den
Konsumenten (E-TAB-2 analog `termin-eintragen.md` E-TES-2). **Kein**
Re-Versand bei teilweise gescheiterten Items; die Familie erhält die
N-von-M-Quittung und entscheidet, ob sie die fehlenden Items per TES
einzeln nachträgt.

*Tickets:* #475

### TAB-10 — Plan-Buddy nicht erreichbar oder Verbindung abgerissen

Die Funktion unterscheidet drei Fehler-Lagen am PLAN-33-Aufruf, weil
der Plan-Buddy threaded läuft (`plan/main.py` Z. 876f.) und der Server
nach Connection-Abbruch eines Clients **weiterschreiben kann**:

- **Plan-Buddy gar nicht erreichbar** (Verbindung kommt nie zustande,
  HTTP-Status `< 200` oder Plan-Buddy nicht installiert, `plan.md`
  PLAN-23, `conventions/apps.md` APP-2). Hier hat der Server das
  Schreiben nicht begonnen: 0 Termine im Familien-Kalender. Ergebnis-
  Signal „nicht_erreichbar". Familien-Wortlaut (hart-codiert) ehrlich
  und eindeutig: „Plan-Buddy nicht erreichbar — kein Termin
  eingetragen, bitte gleich nochmal probieren."

- **Verbindung mitten im Bulk-Aufruf abgerissen** (Client-Timeout 20 s
  PLAN-33.4 überschritten, lokaler Socket-Error nach Sende-Bestätigung,
  Prozess-Restart auf Eltern-Chat-Seite). Hier hat der Plan-Buddy
  möglicherweise **schon Items geschrieben** — die Funktion weiß
  nicht, welche. Ergebnis-Signal „**unbekannt**". Familien-Wortlaut
  (hart-codiert) ehrlich: „Verbindung zum Plan-Buddy war kurz weg —
  ich weiß nicht sicher, welche der Termine eingetragen wurden. Bitte
  einmal kurz im Wochenplan nachschauen; doppelte Eintragsversuche
  fängt der Plan-Buddy ab (Idempotenz, PLAN-33.5), wenn ich dieselbe
  Anfrage gleich nochmal stelle." **Die Funktion stellt die Anfrage
  nicht automatisch erneut** — Retry-Verhalten ist Aufrufer-Sache
  (E-TAB-2 analog `termin-eintragen.md` E-TES-2). PLAN-33.5
  `request_id` ist Pflicht und ist load-bearing für den **manuellen**
  Wiederversuch durch die Familie (gleicher Aufruf-Kontext = gleiche
  `request_id` aus der Session, in einer neuen Aufgaben-Session = neue
  `request_id`).

- **HTTP-Antwort kommt zurück, aber Server meldet Komplett-Fehler.**
  Zwei Unterfälle:
  - **HTTP 502 mit Body `{"error": "calendar_unavailable"}`** (PLAN-33.2,
    Server hat **vor** dem ersten Item-Schreib-Versuch aufgegeben — kein
    `results[]` erwartet, weil der Server selbst sicher weiß, dass nichts
    geschrieben wurde) → Ergebnis-Signal „nicht_erreichbar".
  - **HTTP 5xx ohne parsbaren Body** (Plan-Buddy-interner Fehler nach
    Schreib-Beginn, oder anderer Server-Fehler) → „unbekannt" (gleiche
    Linie wie der Verbindungsabbruch, weil die Funktion den Server-
    Zustand nicht kennt).

In **allen** drei Lagen erfindet die Funktion keine Termine und meldet
keinen Erfolg (`eltern-chat.md` EC-7). Der konkrete Wortlaut der
Antworten lebt im Code; die Spec normiert das **Soll** (Unterscheidung
„nicht_erreichbar" vs. „unbekannt" + Existenz beider Antworten + keine
Halluzination einer `event_id` + kein stiller Abbruch). Analog
`termin-eintragen.md` TES-9 (das nur „nicht_erreichbar" kennt, weil ein
Einzel-PUT keinen partiellen Mittelzustand hat).

**SESS-2-Verträglichkeit:** Stürzt der Eltern-Chat-Prozess **während**
des Bulk-Aufrufs ab, läuft die Privatchat-Session nicht weiter — beim
Neustart ist der `request_id`-Kontext der Session verloren (SESS-2:
„Zwischenzustand nur im Speicher"). Eine erneute Familien-Anfrage geht
mit neuer `request_id` raus; doppelte Termine sind in dieser Lage
möglich (PLAN-33.5 idempotiert nur **innerhalb** der 15-min-TTL je
`request_id`, nicht zwischen zwei verschiedenen `request_id`s mit
inhaltlich gleichen Items). Das ist akzeptierte V1-Last; eine echte
Cross-Session-Idempotenz wäre Folge-Ticket.

*Tickets:* #475

### TAB-11 — Erfolgs-Quittung im Privatchat
Liefert der Plan-Buddy-Bulk-PUT HTTP 200, postet die Funktion im
**Privatchat** des Aufrufers eine **deterministische** Erfolgs-Quittung
— kein Agent-Loop, keine Halluzination. Form:

```
Eingetragen ✅: {N} von {M} Terminen.
```

Bei `N < M` listet die Quittung zusätzlich, **welche** Items gescheitert
sind, mit der Nummer aus dem Sammel-Vorschlag und dem `error_code` aus
PLAN-33 (z. B. „Nummer 3 (validation), Nummer 7 (calendar_rate_limit)").
Der konkrete Wortlaut lebt im Code; die Spec normiert das **Soll**
(N-von-M-Quittung + Fehler-Liste bei Teil-Misserfolg + im Privatchat,
nicht in der Familien-Gruppe — TAB-3). Analog `termin-eintragen.md`
TES-12 (Erfolgs-Quittung deterministisch).

*Tickets:* #475

## 6. Trigger als Eltern-Chat-Aufgabe

### TAB-12 — V1-Trigger als Eltern-Chat-Aufgabe (WriteTask, TASK-4, async)
Solange noch kein anderer Aufrufer existiert, läuft der V1-Trigger der
Funktion als **Aufgabe im Aufgaben-Katalog des Eltern-Chats**
(`eltern-chat.md` EC-8) — analog `termin-eintragen.md` TES-10,
`familie-anlegen.md` FAA-12, `ca-verteilung.md` CAV-6.

- **Registrierung:** über `build_catalog` (`conventions/tasks.md` TASK-7),
  **Guard** auf `plan_origin_url` (`eltern-chat.md` EC-15) und
  `family_group_chat_id_getter` — die Aufgabe wird nur registriert, wenn
  beide konfiguriert sind. Ohne Plan-Buddy-Origin keine TAB-Aufgabe; ohne
  Familien-Gruppen-Bindung kein Berechtigungs-Anker für TAB-2.
- **Form:** `WriteTask` mit `propose` + `execute` (TASK-4), **nicht**
  TASK-9 (Sofort-Schreib-Aufgabe mit Undo). Begründung siehe E-TAB-2.
- **Async-Form:** TASK-5 `is_async=True` — TAB ist eine mehrstufige
  Privatchat-Session (Bild → Anbieter-Aufruf → ggf. Lücken-Rückfrage →
  Sammel-Vorschlag → Bestätigung → Bulk-PUT), die zwischen Familien-
  Antworten **auf das nächste Update warten** muss. Vorbild: TES-
  Routing-Test (`eltern-chat/skills/termin_eintragen_task.py` Z. 97-112
  und Z. 155-216) — Antworten der Familie laufen über `handle_update`
  in die **geteilte Session-Map** des Skills, der `WriteTask`-Worker
  blockt auf eine `next_message`-Coroutine. TAB muss denselben Pfad
  nutzen (gleiche Session-Map, dasselbe `handle_update`-Routing), damit
  Familien-Antworten beim TAB-Worker ankommen.
- **Berechtigung:** deckt sich mit TAB-2 (Live-Mitgliedschaft); die
  Aufgabe leitet die Live-Prüfung an die Funktion durch, die ihre eigene
  Gate-Logik behält und der Trigger-Agnostik (E-TAB-1) nicht unterläuft.
- **Privatchat-Wechsel:** folgt `eltern-chat.md` EC-20 (mehrstufige
  Aufgaben überfluten die Familien-Gruppe nicht) und TAB-3 (Privatchat-
  Pflicht).

Die Aufgabe ist additiv im Sinne von EC-8 — der bestehende Katalog
bleibt unberührt.

*Tickets:* #475

## 7. Tests

### TAB-13 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec mit Code-Verhalten hat einen automatisierten
Test (CLAUDE.md §6), reproduzierbar und **ohne Netz** — Telegram, der
KI-Anbieter und die Plan-Buddy-Bulk-Schnittstelle werden durch
kontrollierte Doppelungen ersetzt, analog `eltern-chat.md` EC-17,
`termin-eintragen.md` TES-11, `foto-senden.md` FSE-8. Mindest-Abdeckung:

- **TAB-1** — Aufruf mit minimalem Eingang (Privatchat-IDs + Bild +
  Begleittext mit Signalwort + plausible Termin-Liste vom Anbieter-Stub)
  liefert nach Bestätigung „eingetragen" mit `geschrieben=M, gesamt=M`;
  ein Aufruf ohne Privatchat-Chat-ID bricht ohne Wirkung ab.
- **TAB-2** — Aufruf eines Nicht-Familien-Mitglieds wird abgelehnt; das
  Bild geht **nicht** an den KI-Anbieter; das Ergebnis-Signal ist
  „abgelehnt".
- **TAB-3** — Trigger aus der Familien-Gruppe startet die Konversation
  im Privatchat des `from_user_id` (Privatchat-Pflicht); ein Privatchat-
  Trigger startet direkt dort; ein 30-Minuten-Timeout in der laufenden
  Session beendet sie und liefert „abgebrochen" (SESS-3); der
  Prozess-Neustart-Pfad (SESS-2 — kein halber persistenter Zustand,
  kein Bulk-PUT nach Restart) wird konventionsweit über die
  `conventions/privatchat-session.md` SESS-2-Test-Pflicht abgedeckt
  und hier nicht dupliziert (Verweis-Pattern analog TES-11).
- **TAB-4** — Bild **ohne** Begleittext → die Funktion greift **nicht**
  (FSE übernimmt); Bild **mit** Signalwort → TAB greift; Bild mit
  Begleittext ohne Signalwort → TAB greift **nicht**.
- **TAB-5** — der Anbieter-Stub erhält einen Request mit einem `image`-
  Content-Block und dem hart-codierten Tool-Schema; das Bild wird nach
  der Extraktion **nicht** persistiert (kein Photo-Buddy-Aufruf); ein
  Anbieter-Fehler (Timeout, ungültige JSON-Antwort) liefert
  „provider_fehler" mit hart-codierter ehrlicher Antwort, ohne Bulk-PUT.
- **TAB-6** — ein Termin mit `beginn` außerhalb von `[heute-400d,
  heute+2J]` wird verworfen; ein Termin mit `beginn = heute-200d` liegt im
  Fenster und bleibt erhalten (Refs #524); bleibt nach der Filterung eine
  leere Liste, endet die Funktion mit „unklar" und ohne Bulk-PUT; ein Termin
  ohne `titel`/`beginn`/Pflicht-`ende` wandert in den Lücken-Sammler
  (TAB-8.1).
- **TAB-7** — vor dem Bulk-PUT wird **eine** Vorschlags-Nachricht im
  Privatchat gepostet, im HTML-`<pre>`-Block, mit allen Termin-
  Vorschlägen nummeriert; **ein** E-EC-7-Wort als Antwort löst den
  Bulk-PUT für **alle** Items aus; eine nicht-bestätigende Antwort
  liefert „verworfen", **ohne** Bulk-PUT; liegt **mindestens ein** Termin
  vor heute, wird dem Vorschlag der Vergangenheits-Hinweis vorangestellt
  (Refs #524); sind alle Termine in der Zukunft, entfällt der Hinweis.
- **TAB-8.1** — bei einer Pflicht-Lücke wird die Sentinel-Nachricht
  gepostet (alle Lücken auf einmal, `[?…?]`-Form, eckig); eine korrekt
  ersetzte Antwort wird deterministisch geparst und die Liste
  vervollständigt; eine fehlerhaft ersetzte Antwort löst eine zweite
  Rückfrage aus.
- **TAB-8.2** — `personen_hinweise` aus dem Anbieter-Output lösen
  **keine** Lücken-Rückfrage aus; der Titel wird **nicht** automatisch
  angereichert.
- **TAB-8.3** — nach zwei Rückfrage-Runden ohne valide Antwort endet
  die Funktion mit „unklar"; eine erfolgreiche Erstklärung **einer**
  Lücke in Runde 1 zählt nicht gegen Runde 2.
- **TAB-9** — der HTTP-Aufruf nutzt Methode `POST`, Pfad
  `/api/v1/plan/termine/bulk`, Body mit `request_id` (UUIDv4) und
  `items[]`; HTTP 200 mit `{ok: true, geschrieben, gesamt, results}`
  übernimmt `geschrieben` und `gesamt` ins Ergebnis-Signal; die
  Fehler-Lagen (HTTP 502 ohne `results[]`, Verbindungsabbruch nach
  Sende-Bestätigung, 5xx ohne parsbaren Body) sind in TAB-10 spezifiziert
  und dort getestet; kein eigener Retry.
- **TAB-10** — drei Lagen je eigener Test:
  - Plan-Buddy gar nicht erreichbar (PLAN-23, Connection refused vor
    Item 1) → „nicht_erreichbar" + Wortlaut „Plan-Buddy nicht erreichbar
    — kein Termin eingetragen".
  - **Verbindung mitten im Bulk-Aufruf abgerissen** (Server-Stub schreibt
    Item 1, schließt die HTTP-Verbindung ohne Response-Body) →
    „unbekannt" + Wortlaut „Verbindung war kurz weg — bitte im
    Wochenplan nachschauen".
  - HTTP 502 mit `{"error": "calendar_unavailable"}` (PLAN-33.2, kein
    `results[]`-Array; Server hat vor Item 1 aufgegeben, 0 geschrieben)
    → „nicht_erreichbar".
  - HTTP 5xx ohne parsbaren Body → „unbekannt" + selber Wortlaut wie
    Verbindungsabbruch.
  In allen Lagen: keine Halluzination einer `event_id`.
- **TAB-11** — bei HTTP 200 mit `geschrieben=3, gesamt=5` erscheint im
  Privatchat die N-von-M-Quittung mit den zwei Fehler-Nummern und
  ihren `error_code`-Werten.
- **TAB-12** — die EC-8-Aufgabe wird vom Aufgaben-Katalog gefunden,
  ist als `WriteTask` (TASK-4 `propose`+`execute`) und mit
  `is_async=True` (TASK-5) registriert; sie wird nur registriert, wenn
  `plan_origin_url` und der Familien-Gruppen-Chat-Bindung-Getter beide
  gesetzt sind (Guard); ein Aufruf aus dem Familien-Gruppen-Chat
  adressiert die Konversation im Privatchat (EC-20), nicht in der
  Gruppe.
  **Routing-Test (analog TES, `eltern-chat/skills/termin_eintragen_task.py`
  Z. 97-112, 155-216):** eine eingehende Familien-Antwort im Privatchat
  läuft über `handle_update` in die geteilte Session-Map des Skills und
  erreicht den blockierenden `next_message`-Aufruf des TAB-Workers —
  ein Test mit Stub-Telegram und Stub-Anbieter belegt, dass der Worker
  die Familien-Antwort (z. B. das E-EC-7-Bestätigungswort) **innerhalb**
  derselben Session sieht und nicht in eine zweite Session-Map fällt.
- **TAB-12/Medien-Naht** — propose→confirm-Persistenz der Medien-Naht
  (TASK-4 `TurnContext`-Persistenz, Refs #514): der propose-Turn enthält
  ein Foto (`media_telegram_file_id` gesetzt, `medium_typ="foto"`); der
  confirm-Turn enthält nur ein Bestätigungswort (kein Medium). Ein Test
  belegt, dass der TAB-Worker in `execute()` die `media_telegram_file_id`
  des propose-Turns erhält — identisch mit dem, was `propose()` sah —
  und das Foto damit korrekt nachlädt; ein leerer `medium_typ` im
  confirm-Turn führt **nicht** zu einer »kein Bild«-Quittung.

Läufe gegen den **echten** Anbieter bzw. den **echten** Plan-Buddy sind
opt-in und nicht Teil des Standard-Durchlaufs (analog `eltern-chat.md`
EC-17, `termin-eintragen.md` TES-11, `plan.md` PLAN-29).

*Tickets:* #475

## V2 — URL- und Screenshot-Pfad (nicht implementiert)

V2 erweitert TAB um einen **URL-Pfad**: ein Aufrufer schickt eine URL
(z. B. die Schul-Website mit dem Wochenplan), die Funktion lädt die Seite
oder rendert einen Screenshot und extrahiert daraus die Termin-Liste.

V2 ist **nicht** Teil dieser V1-Spec. Die bekannten Risiken werden hier
**dokumentiert**, damit sie bei V2-Aufnahme nicht neu entdeckt werden
müssen:

- **SSRF (Server-Side Request Forgery).** Eine vom Aufrufer übergebene
  URL darf nicht beliebige interne Dienste treffen (Loopback, RFC1918,
  Cloud-Metadata-Endpoints). V2 nutzt eine **Whitelist** von URL-Mustern
  (Schul-Domains, bekannte Kursanbieter), nicht eine offene URL-Annahme.
- **Auth-Walls.** Schul-Plattformen sind oft passwortgeschützt; ein
  ungebuchter Aufruf landet auf einer Login-Seite und liefert keinen
  Plan. V2 muss explizit eine „Login erforderlich"-Heuristik haben und
  dem Aufrufer ehrlich zurückmelden, dass die Seite Auth braucht
  (`eltern-chat.md` EC-7).
- **Beliebige Seiten als Angriffs-Pfad.** Eine vom LLM verarbeitete
  beliebige Seite ist eine Prompt-Injection-Quelle. Das Tool-Schema
  (TAB-5) bleibt für V2 dieselbe Verteidigung — kein Free-Text-Output,
  nur strukturierte Termin-Liste —, aber V2 sollte zusätzlich den Text-
  Inhalt der Seite **nicht** in den Sammel-Vorschlag aufnehmen.

Auflösung als Folge-Ticket, sobald V1 belegt funktioniert und eine
Familie nach „URL statt Foto" fragt.

---

## Offene Punkte

- ~~**OPEN-TAB-Privacy — KI-Anbieter mit DSGVO-Belegen für Bild-Verarbeitung.**~~
  **ERLEDIGT 2026-06-11 durch E-TAB-7 (Refs #486); Anbieter-Wahl aktualisiert
  2026-07-03 durch E-TAB-8 (Refs #1262).** E-TAB-7 legte Auswahl-Katalog + DE→EU-
  Aufweichung fest (weiter gültig als Auswahl-Regel); die **aktive** Foto-Route ist
  seit E-TAB-8 **Claude über `tools.llm`** (eigener ZD-Slot), nicht mehr der
  Mistral-`_multimodal/`-Adapter.

  Die **generelle** Frage „Wann endet die Bewertungsphase und deckt die
  Familien-Einwilligung Bilder?" wird **eltern-chat-weit** gelöst, nicht
  TAB-spezifisch — siehe Folge-Ticket „Eltern-Chat Privacy-Linie
  generalisieren" (#485, geparkt mit Trigger „erste Nicht-Test-Familie").
  Bewertungsphase-Ende heute = wenn Nic `OPEN-EC-A` (`eltern-chat.md`
  Z. 533ff.) schließt. Das Wortlaut von `eltern-chat.md` E-EC-9 wird
  **nicht** in dieser TAB-Spec geändert.

- **OPEN-TAB-Queue — Mehrere Bilder hintereinander.** V1 verarbeitet ein
  Bild je Aufruf. Schickt eine Familie zwei Bilder kurz hintereinander
  (Schulplan Seite 1 und Seite 2), entstehen zwei parallele TAB-Aufrufe
  — V1 macht keinen Queue-Mechanismus. Folge-Ticket „TAB-Skill-Queue:
  Mehr-Bilder-Folge zusammenfassen", sobald eine Familie das spürt.

- **OPEN-TAB-Konflikt — Kollisions-Erkennung im Kalender.** TAB legt
  Termine **additiv** an. Eine Vor-Prüfung gegen bestehende Termine über
  `termine-erfragen.md` TER („am Donnerstag steht schon X — trotzdem
  Y dazu?") wäre möglich, ist aber V1 nicht — die Spec entscheidet
  bewusst „erst den glatten Pfad bauen, dann auf belegten Konflikt-
  Schmerz reagieren" (analog `termin-eintragen.md` OPEN-TES-D). Folge-
  Ticket sobald eine Familie versehentlich doppelt einträgt.

---

## Entscheidungen

### E-TAB-1 — Funktion ist trigger-agnostisch
*Datum:* 2026-06-08

Termine aus Bild wird als eigenständige, trigger-agnostische **Funktion**
definiert — nicht als fest verdrahteter Eltern-Chat-Aufgaben-Schritt. Die
Funktion kennt ihren Aufrufer nicht; ihr Vertrag ist TAB-1.

**Verworfen:** die Aufgabe direkt im Eltern-Chat-Skill-Code zu
implementieren, ohne sie als Funktion abzugrenzen. Wäre sie ein fester
Skill-Bestandteil, müsste sie für jeden weiteren Aufrufer (ein späterer
URL-Pfad nach V2, ein anderer Bot-Kanal, ein Display-Widget) neu
geschrieben werden — die Trigger-Agnostik ist die Wiederverwendungs-
Garantie. Dasselbe Eigentümer/Nutzer-Muster gilt für
`termin-eintragen.md` (E-TES-1), `termine-erfragen.md` (E-TER-1),
`ca-verteilung.md` (E-CAV-1), `familie-anlegen.md` (E-FAA-1) und
`kalender-verbinden.md` (E-KAV-1).

### E-TAB-2 — propose→confirm (TASK-4) statt Sofort-mit-Undo (TASK-9)
*Datum:* 2026-06-08

Die Aufgabe ist als `WriteTask` mit `propose` + `execute` (TASK-4)
registriert, **nicht** als TASK-9 (Sofort-Schreib-Aufgabe mit Undo).
Damit weicht TAB **bewusst** von `foto-senden.md` E-FSE-1 ab (FSE wirkt
sofort und bietet Undo).

**Begründung in drei Sätzen:**

1. **Signalwort ≠ ausdrückliche Schreib-Handlung im TASK-9-Sinn.** TASK-9
   greift, wenn der **Akt selbst** (kommentarloses Foto an den Bot) als
   ausdrückliche Geste „mach das" gilt — die Familie *will* das Foto im
   Rahmen, das Senden ist die Handlung. Bei TAB ist die Geste „erkenn die
   Termine" — die Familie will **die Termine sehen, bevor** sie im
   Kalender landen. Ein Signalwort signalisiert Absicht zur Erkennung,
   nicht Absicht zum sofortigen Eintragen aller erkannten Termine.
2. **PLAN-22 hat heute keinen DELETE.** Ein Undo nach Bulk-Schreiben
   bräuchte einen DELETE-Pfad auf der Plan-Buddy-Schnittstelle, den es
   heute nicht gibt (`plan.md` PLAN-18 spricht von „löschen" nur
   *innerhalb* der App, nicht als HTTP-API; `termin-eintragen.md` Out-of-
   Scope-Block verweist explizit: „Plan-Buddy hat heute keinen DELETE auf
   der Termin-Schnittstelle"). Ein TASK-9-Undo wäre also **ohne**
   technischen Hebel — die Familie sähe die Termine im Kalender, könnte
   sie aber nicht per Skill zurücknehmen.
3. **EC-10-Mehrstufigkeit deckt den Komfort-Wunsch ohne TASK-9 ab.**
   `eltern-chat.md` EC-10 erlaubt eine Ein-Schritt-Bestätigung, wenn der
   Anstoß vollständig ist (TES nutzt das). Bei TAB ist der Sammel-
   Vorschlag (TAB-7) selbst diese Ein-Schritt-Form: eine Nachricht, eine
   Bestätigung — der Aufrufer trägt nicht mehrere E-EC-7-Wörter ab. Die
   Komfort-Lücke zwischen „sofort eintragen + Undo" und „kurz prüfen +
   eintragen" ist klein; der Sicherheits-Gewinn (kein Bulk-Müll im
   Kalender bei fehlinterpretierter Tabelle) ist groß.

**Verworfen:** TASK-9 mit Bulk-DELETE-Undo. Das hieße, parallel zu dieser
TAB-Spec einen Bulk-DELETE-Pfad in der Plan-Buddy-Schnittstelle zu
spezifizieren — eine Ausweitung, die Out-of-Scope von #475 ist und die
TES-Out-of-Scope-Linie unterlaufen würde.

### E-TAB-3 — Privatchat-Pflicht (EC-20-Klasse)
*Datum:* 2026-06-08

Die Konversation läuft im Privatchat des Aufrufers (TAB-3), analog
`termin-eintragen.md` E-TES-3 und `kalender-verbinden.md` KAV-3.

**Begründung.** TAB ist mehrstufig (Bild rein → Anbieter-Aufruf →
Sammel-Vorschlag → ggf. Lücken-Rückfrage → Bestätigung → Bulk-PUT) und
**schreibend**. Genau für diese Klasse legt `eltern-chat.md` EC-20 fest:
mehrstufige schreibende Aufgaben führen ihre Folge im Privatchat. In der
Familien-Gruppe wären Sammel-Vorschlag (HTML-`<pre>`-Block mit N
Terminen), Lücken-Rückfrage und Bestätigungswort-Hin-und-her ein Strom,
der den normalen Familien-Chat überflutet — derselbe Schaden, den TES-3,
KAV-3 und FAA-12 absorbieren. Außerdem fängt der Privatchat die EC-20-
Sorge zusätzlich ab, dass ein E-EC-7-Wort in der Gruppe versehentlich von
einem anderen Familienmitglied gesprochen würde (E-TES-3 begründet das
ausführlich).

**Verworfen:** den Sammel-Vorschlag in der Familien-Gruppe zu führen.
Bricht EC-20, macht die Liste für alle Familienmitglieder einsehbar
(auch für Kinder, deren Termine darin auftauchen) und öffnet die
versehentliche-Bestätigung-Falle.

### E-TAB-4 — Sammel-Bestätigung mit EINEM E-EC-7-Wort
*Datum:* 2026-06-08

Der Sammel-Vorschlag (TAB-7) fordert **ein** Bestätigungswort, das die
**gesamte** Liste freischaltet — kein E-EC-7-Wort je Termin, kein
selektives „nur 1, 2 und 5".

**Begründung.** `eltern-chat.md` E-EC-7 verlangt eine ausdrückliche
Bestätigung; der Schutzgegenstand ist „die Familie weiß, was geschrieben
wird". Die Liste **ist** vollständig sichtbar im `<pre>`-Block (TAB-7,
EC-27 HTML opt-in pro Nachricht). Damit ist die Sichtbarkeits-Bedingung von EC-10
erfüllt, und das Bestätigungswort kann sich auf die gesamte Liste
beziehen — der Aufrufer hat alle Items vor sich, bevor er „ok" sagt.

**Verworfen:** je Termin ein E-EC-7-Wort. Würde aus einer Aufgabe N
Bestätigungs-Schritte machen, träfe die Komfort-Linie aus
`eltern-chat.md` EC-10 („Ein-Schritt-Bestätigung bei vollständigem
Anstoß") und wäre für 15-Termine-Schulpläne untragbar. Außerdem würde es
die TAB-7-Form (eine `<pre>`-Liste) gegen N Einzel-Nachrichten tauschen
— Bot-Spam im Privatchat.

**Auch verworfen:** selektive Streich-Bestätigung in derselben Session
(„ok 1, 2, 5"). V1 ist „alles oder verwerfen + neuer Aufruf". Begründung:
ein selektiver Parser-Pfad bringt einen weiteren deterministischen
Parser (`eltern-chat.md` E-EC-4), den V1 nicht braucht — eine Familie,
die zwei der fünf Termine nicht will, kann sie nach dem Eintragen
einzeln im Kalender löschen (heute manuell) oder die Bulk-Bestätigung
verweigern und die fünf Termine einzeln per TES erfassen.

### E-TAB-5 — Bild wird nach Extraktion verworfen, kein Photo-Buddy-Beleg
*Datum:* 2026-06-08

Das Bild geht an den KI-Anbieter (TAB-5) und wird **nach** der
Extraktion verworfen — kein Aufruf an den Photo-Buddy (kein PHOTO-13-
Ingest), kein lokales Persistieren des Bilds neben den Eltern-Chat-
Daten.

**Begründung.** Das Bild ist ein **Hilfsmittel** für die Termin-
Erkennung, nicht der Inhalt, den die Familie speichern will. Ein
abfotografierter Schulplan im Photo-Buddy würde den Bilderrahmen mit
sachfremdem Inhalt fluten und wäre eine **zweite** Datenlinie für
denselben Eingang — der Bilderrahmen ist Familien-Foto-Galerie, kein
Dokumenten-Archiv (`foto-senden.md` FSE-Out-of-Scope-Linie). Außerdem
ist das Bild bereits an den KI-Anbieter gegangen (EC-13 dokumentiert
die Datenlinie); ein zusätzlicher Photo-Buddy-Beleg würde die
Privacy-Linie ohne Nutzen erweitern.

**Verworfen:** das Bild parallel an den Photo-Buddy zu schicken, als
„Quittung für die Familie, woraus die Termine extrahiert wurden". Die
Quittung kommt textuell über TAB-7 (Sammel-Vorschlag): die Familie
sieht die extrahierten Termine und bestätigt — das ist die
Verifikations-Schicht, die zählt. Der zusätzliche Bild-Beleg wäre
DSGVO-Last (zweite Speicherstelle, zweite Lösch-Linie) ohne
Funktions-Gewinn.

### E-TAB-6 — V1 nutzt konfigurierten Anbieter; V2 = additiver Adapter-Slot
*Datum:* 2026-06-08

V1 nutzt den für die Instanz konfigurierten KI-Anbieter
(`eltern-chat.md` EC-11) — derselbe Anbieter, der die Text-Anfragen des
Eltern-Chats abwickelt, mit einem `image`-Content-Block (TAB-5).
**Keine** zweite Adapter-Konfiguration in V1.

V2-Pfad als additive Erweiterung: sollte sich zeigen, dass der
konfigurierte Text-Anbieter Bilder nicht ausreichend kann oder ein
**anderer** Anbieter DSGVO-konformer für Bild-Verarbeitung ist (siehe
OPEN-TAB-Privacy), erweitert V2 das EC-11-Schema um einen **zweiten**
Adapter-Slot „multimodal" — eine Familie kann dann z. B. Text bei
Anbieter A und Bilder bei Anbieter B verarbeiten lassen. Das ist eine
**additive** Erweiterung des `eltern-chat.md` EC-11-Vertrags, keine
Umbau-Migration.

**Anbieter-Kriterien-Katalog** für die V2-Auswahl (in OPEN-TAB-Privacy
nachzutragen, hier zur Referenz):

- **DE-Hosting** der multimodalen Inferenz (`xbuddy-knowledge/CONTEXT.md`
  §3 „Privacy" — „Verarbeitung in Deutschland").
- **Belegte Zero Data Retention** im DPA des Anbieters (kein
  Training-Use des übermittelten Bilds, kein langfristiges Logging).
- **Aktiver Lifecycle** des konkret eingesetzten multimodalen Modells
  (aktive Modell-Pflege, dokumentierte Sicherheits-Updates).
- **Pi-lokal verworfen:** der Pi der Familien-Instanzen hat nicht die
  Inferenz-Leistung für multimodale Modelle dieser Klasse in
  akzeptabler Latenz (Beleg-Quelle bei der V2-Anbieter-Wahl
  nachzutragen — heute Erfahrungs-Wert, kein Benchmark).
- **Ausgeschlossene Kandidaten (Stand 2026-06-08):**
  - **Pixtral 12B** — deprecated seit 2025-12-02
    ([Mistral Models — Pixtral 12B](https://docs.mistral.ai/models/pixtral-12b-24-09)).
    Ausschluss-Grund: aktiver Lifecycle nicht mehr erfüllt.
  - **Pixtral Large** — deprecated seit 2026-02-27
    ([Mistral Models — Pixtral Large](https://docs.mistral.ai/models/pixtral-large-24-11)).
    Ausschluss-Grund: aktiver Lifecycle nicht mehr erfüllt.

  Diese Ausschlüsse sind **stichtagsbezogen** (Anbieter pflegt seine
  Modell-Lebenszyklen weiter); eine V2-Anbieter-Wahl prüft die jeweils
  aktuelle Mistral-Modell-Übersicht und andere multimodale EU/DE-
  Kandidaten gegen den Kriterien-Katalog oben.

**Wichtig:** der Bewertungsphase-Endpunkt — „ab wann darf TAB im
Regelbetrieb laufen, deckt die Familien-Einwilligung Bilder?" — wird
**eltern-chat-weit** gelöst (siehe OPEN-TAB-Privacy), nicht TAB-
spezifisch. Heute = solange `OPEN-EC-A` (`eltern-chat.md` Z. 533ff.) offen
ist, läuft TAB nur in den Test-Familien, die ausdrücklich eingewilligt
haben. Das Wortlaut von `eltern-chat.md` E-EC-9 wird in dieser TAB-Spec
**nicht** geändert.

**Verworfen:** in V1 bereits einen zweiten Adapter-Slot zu spezifizieren,
ohne belegten Bedarf. CLAUDE.md §6 „Lege nichts auf Vorrat an" — die
Erweiterung kommt erst, wenn V1 belegt zeigt, dass der bestehende
Adapter nicht reicht.

### E-TAB-7 — V2-Anbieter Mistral Medium 3.5; DE→EU-Aufweichung des Hosting-Kriteriums bewusst ratifiziert
*Datum:* 2026-06-11 · Refs #486

> **HISTORISCH SUPERSEDED durch E-TAB-8 (2026-07-03, #1262):** Der hier ratifizierte
> Mistral-Multimodal-Adapter (`eltern-chat/skills/_multimodal/mistral.py`) ist **nicht
> mehr** der aktive TAB-Pfad. Die Foto-Analyse läuft jetzt über `tools.llm` mit **Claude**
> gepinnt (eigener ZD-Slot). Der Anbieter-Auswahl-Katalog und die DE→EU-Hosting-Begründung
> unten bleiben als **Auswahl-Regel** gültig; nur die konkrete Anbieter-Wahl
> (Mistral → Claude) ist überholt.

Der V2-Multimodal-Adapter-Slot (E-TAB-6 V2-Pfad) wird ratifiziert mit
**Mistral Medium 3.5** (`mistral-medium-3504`, Frontier-class, multimodal-
optimiert) als gewählter Anbieter. Code-Naht ist durch #508 deployed
(`eltern-chat/skills/_multimodal/mistral.py`, EU-gehostet via Mistral La
Plateforme, Paris/Frankreich).

**Bewusst aufgeweicht:** das in E-TAB-6 (Z.868) genannte Hosting-Kriterium
„DE-Hosting" wird in V2 zu **EU-Hosting**. Begründung im Wortlaut:

- **Pi-Inferenz unrealistisch**: E-TAB-6 hat „Pi-lokal verworfen" schon
  belegt (Multimodal-Modelle dieser Klasse erreichen am Pi nicht die
  Latenz für Familien-tauglichen Bot-Pfad).
- **DE-Anbieter-Lage heute begrenzt**: Aleph Alpha Vision ist Stand
  2026-06 limitiert in multimodaler Stärke gegen die Familien-Aushang-
  Erkennung (Plan-Aushänge mit handschriftlichen Terminen); andere
  DE-Multimodal-Anbieter mit Frontier-Qualität sind nicht etabliert.
  Hartes Warten auf DE-Hosting würde TAB-V2 unbestimmt blockieren.
- **Pixtral-Familie (Mistral) ist deprecated** — sowohl Pixtral 12B als
  auch Pixtral Large (E-TAB-6 Z.876-884); aktive Mistral-Wahl ist
  ausschließlich `mistral-medium-3504` (Frontier-Klasse) und
  `mistral-medium-2508` (Premier, Konversation).
- **Mistral DPA trägt Zero Data Retention**: kein Training-Use der
  übermittelten Bilder, kein langfristiges Logging — das ist der harte
  Privacy-Hebel, der DE-Hosting funktional **ersetzt** für unseren
  Use-Case.
- **AVV EU-DSGVO-konform**: Mistral hat EU-Sitz (Paris), keine CLOUD-
  Act-Exponierung, keine US-Mutterkonzern-Hintertür. Schrems-II-Linie
  des EuGH ist nicht relevant.
- **EU statt DE als V2-Hosting-Bodenlinie** ist ein konservativer
  Schritt: Constitution §3 („Verarbeitung in Deutschland") bleibt für
  alle Per-Familie-Datenspeicher (Hub, Photo-Buddy, Zugangsdaten,
  Routine-Store) **unverändert harte Linie**. Nur die KI-Anbieter-
  Verarbeitung weicht auf EU auf — und auch das ist eine Bewertungs-
  phasen-Aufweichung (E-EC-9 läuft), keine dauerhafte Senkung.

**Folgen für andere Anbieter-Slots:**

- **Konversations-Slot** (heute Mistral Medium 3.1, FR/EU): folgt
  derselben Aufweichung — DE-Anbieter mit Frontier-Konversation sind
  Stand 2026-06 nicht verfügbar. Wenn künftig ein DE-Anbieter mit
  ausreichender Qualität verfügbar wird (Aleph Alpha Konversations-
  Modell, deutsche Hyperscaler-LLM-Initiative), wird ein Wechsel
  evaluiert (Folge-Ticket bei konkretem Bedarf).
- **Andere Buddys** (Routine, Wetter, …) ohne KI-Anbieter-Aufrufe
  bleiben von dieser Aufweichung unberührt.

**Wiederaufnahme-Trigger für strengere Linie** (V3 oder Folge-
Ratifikation):

- Belegter DE-Multimodal-Anbieter mit Frontier-Qualität verfügbar
  (Cross-Engine-Vergleich gegen Mistral Medium 3.5 zeigt Gleichstand
  oder besser).
- Kommerzielle Phase erreicht (E-EC-9 + OPEN-EC-A geschlossen,
  Anonymisierungs-Layer aktiv) — dann ist die Bewertungsphasen-
  Aufweichung nicht mehr gerechtfertigt und Hosting-Linie wird neu
  ratifiziert.
- Mistral-Lifecycle bricht (DPA-Verschlechterung, AVV-Bruch, US-
  Mutterkonzern-Übernahme, ZDR-Aufhebung).

**Verworfen:**

- **Variante B**: #486 schließen mit „Slot fertig, Anbieter-Wahl wartet
  auf DE-Hosting". Hätte Mistral in einem Spec-Limbo gelassen, während
  Mistral live im Familien-Hub deployed ist — ehrliches Ratifizieren ist
  sauberer als stille Live-Praxis.
- **Variante C**: nur Kriterien-Katalog ergänzen ohne Festlegung. Doppelter
  Schritt; Festlegung muss sowieso passieren, und die Verzögerung schafft
  keine Klarheit, sondern mehr Doku-Schuld.
- **Aleph Alpha Vision als Alternative**: heute (2026-06) nicht in
  Multimodal-Stärke gegen Frontier-Klasse belegt. Beleg wäre Voraussetzung,
  und der existiert nicht.

*Tickets:* #486 (Ratifikation), #508 (Code-Naht), #485 (eltern-chat-weite
Privacy-Schärfung — parallel, getrennt).

### E-TAB-8 — Multimodal-Route auf `tools.llm` gehoben, Anbieter Claude gepinnt (supersedes E-TAB-7-Deployment)
*Datum:* 2026-07-03 · Refs #1262 (subsumiert #1119)

**Neue Wahrheit:** Die Foto-Analyse/TAB-Extraktion (TAB-5) läuft über die geteilte
LLM-Provider-Lib `tools.llm` — `get_singleshot(<foto-slot>).complete_structured(system,
prompt=caption, schema=TOOL_SCHEMA, images=[…])` (LLMP-S1, Bild-Content additiv) — mit
**Anthropic/Claude** als gepinntem Anbieter. Der ZD-Slot ist
`eltern-chat-anthropic-foto-analyse-api-key` (ZD-2, LLMP-5): eine **eigene** Foto-Route,
unabhängig vom Chat-Slot `eltern-chat-anthropic-api-key`.

**Warum:** Die Foto-Analyse hing am globalen eltern-chat-Provider-Default und kippte mit
einem Mistral-Default-Wechsel mit (#1262-Anlass). Eigene Route + eigener Slot entkoppeln
die Bild-Verarbeitung von der Text-Chat-Anbieterwahl; **Anbieter-Wechsel** geschieht durch
Tausch des Vendor-Segments im Slot, ohne Code (ENTSCHEID-1262 → „Anbieter wechseln können").

**Supersedes:** E-TAB-7 ratifizierte den V2-Multimodal-Adapter mit **Mistral Medium 3.5**
über `eltern-chat/skills/_multimodal/mistral.py` als deployed — das ist **historisch**;
kein Soll-Satz führt Mistral-Multimodal mehr als aktiven TAB-Pfad. Die dort dokumentierte
DE→EU-Hosting-Aufweichung und der Kriterien-Katalog (E-TAB-6/7) bleiben als
**Anbieter-Auswahl-Regel** für die Foto-Route gültig.

**Migration additiv-rückrollbar (LLMP-S8, ENTSCHEID-1262 → „Patch B"):** **PR 1** stellt
TAB auf `tools.llm` um und markiert `skills/_multimodal/` als deprecated; **PR 2** löscht
`skills/_multimodal/` erst nach grüner Live-Probe. Kein Migrieren-und-Löschen im selben PR.

**Falsch, wenn:** ein zweiter multimodaler Rufer mit **Nicht-Singleshot**-Vertrag auftaucht
— dann ist Bild-Input als Cross-Cutting-Mixin neu zu verhandeln, nie als fünfte Sicht
(ENTSCHEID-1262 → Kill).

*Tickets:* #1262 · subsumiert #1119

---

## Querverweise

- `eltern-chat.md` EC-2 (Familien-Gruppe als Berechtigung — TAB-2),
  EC-6 (Gesprächskontext — Adapter-Form TAB-5), EC-7 (ehrliche Grenze
  — TAB-6, TAB-10), EC-8 (Aufgaben-Katalog — Heimat des V1-Triggers
  TAB-12), EC-10 (schreibende Aufgaben nach Bestätigung — TAB-7),
  EC-11 (KI-Anbieter je Instanz wählbar — TAB-5, E-TAB-6), EC-12
  (anbieter-unabhängige Regeln — TAB-4 Signalwort-Liste, TAB-6
  Validierung), EC-13 (Datenübermittlung an den KI-Anbieter — TAB-5,
  E-TAB-5), EC-14 (Anbieter nicht erreichbar — TAB-5 „provider_fehler"),
  EC-15 (`plan_origin_url` — TAB-9, TAB-12-Guard), EC-17 (Tests ohne
  Netz — TAB-13), EC-20 (mehrstufige Aufgaben überfluten die Familien-
  Gruppe nicht — TAB-3, E-TAB-3), EC-22 (gezielt fragen statt Varianten
  — TAB-8.1 Sentinel-Lückenform), **EC-27 (HTML-Modus opt-in pro
  Nachricht — TAB-7 `<pre>`-Block, TAB-8.1 Sentinel-Form)**, **EC-28
  (Buddy-Call-Renewal — TAB-9 Bulk-PUT-Renewal)**, E-EC-4 (Sicherheits-
  Gates deterministisch — TAB-4 Signalwort, TAB-6 Validierung, TAB-8.1
  Parser, TAB-7 Bestätigung), E-EC-7 (Bestätigungswort-Liste — TAB-7),
  E-EC-9 (V1 ohne Anonymisierung — Bewertungsphase-Kontext für TAB-5,
  E-TAB-6).
- `termin-eintragen.md` TES-1 (Aufruf-Schnittstelle-Vorbild — TAB-1),
  TES-2 (Live-Berechtigung — TAB-2), TES-3 (Privatchat-Pflicht — TAB-3,
  E-TAB-3), TES-7 (Vorschlag + Bestätigungswort — Vorbild für TAB-7),
  TES-8 (PLAN-22-Konsumenten-Vertrag — Vorbild für TAB-9), TES-9
  (Plan-Buddy nicht erreichbar — Vorbild für TAB-10), TES-10 (EC-8-
  Aufgabe als V1-Trigger — Vorbild für TAB-12), TES-11 (Tests-Form —
  Vorbild für TAB-13), TES-12 (Erfolgs-Quittung deterministisch —
  Vorbild für TAB-11), E-TES-1 (Trigger-Agnostik — Vorbild für E-TAB-1),
  E-TES-2 (Konsument der PLAN-22-Schnittstelle, kein Direkt-Zugriff —
  Vorbild für TAB-9), E-TES-3 (Privatchat-Pflicht — Vorbild für E-TAB-3),
  **OPEN-TES-B** (Personen-Anreicherung im Titel — TAB-8.2 respektiert
  die TES-Linie, hängt **keine** Namen automatisch an).
- `foto-senden.md` FSE-1 (Trigger-Agnostik — Pendant), FSE-2 (Live-
  Berechtigung — Pendant), **FSE-3** (kommentarloses Medium ist das
  Intent-Signal — Disambig-Anker für TAB-4), FSE-6 (bekannte erklärbare
  Funktion — Form-Vorbild), E-FSE-1 (Sofort-Ingest mit Rückgängig — TAB
  weicht bewusst ab, siehe E-TAB-2).
- `termine-erfragen.md` TER-4 (Datums-Vokabular — TAB übernimmt den
  Tag aus dem extrahierten ISO-Datum, kein TER-4-Vokabular nötig),
  TER-Out-of-Scope (Konflikt-Pfad — OPEN-TAB-Konflikt).
- `plan.md` PLAN-15 (ein Familien-Kalender — TAB-9 Konsumenten-Vertrag),
  PLAN-17 (normalisiertes Event-Modell — TAB-9-Antwort-Form), PLAN-19
  (Titel-Konvention und Personen-Auflösung — TAB-8.2 respektiert
  PLAN-19 beim Lesen), PLAN-20 (Kalender nicht erreichbar — TAB-10),
  PLAN-22 (Einzel-PUT — TAB-9 Bulk-Variante referenziert PLAN-22-Body-
  Form), **PLAN-33 (Bulk-Termin-Schnittstelle — TAB-9 Konsumenten-
  Vertrag, neu im Rahmen #475)**, PLAN-23 (App-Existenz-Bindung —
  TAB-10), PLAN-29 (Tests-Form — TAB-13), E-PLAN-1 (App besitzt
  Funktion und Schnittstelle — E-TAB-2-Anker), E-PLAN-6 (Kalender-
  Anbindung gehört der Plan-Buddy-App — E-TAB-2-Anker).
- `familie.md` FAM-2 (Familienmitglieder — Berechtigungs-Grundlage
  für TAB-2 über `eltern-chat.md` EC-2).
- `conventions/tasks.md` **TASK-4** (`WriteTask` mit `propose` +
  `execute` — TAB-12), **TASK-7** (Registrierung in `build_catalog`
  mit Guard — TAB-12), TASK-9 (Sofort-Schreib-Aufgabe mit Undo —
  bewusst **nicht** gewählt, siehe E-TAB-2).
- `conventions/apps.md` APP-1 (App besitzt Daten + Funktion +
  Schnittstelle — E-TAB-2-Anker), APP-2 (App-Fähigkeit existiert nur,
  wenn die App installiert ist — TAB-10), APP-3 (Andere Apps sprechen
  eine App nur über deren Schnittstelle an — TAB-9, E-TAB-2).
- `conventions/urls.md` URL-4 (API-Pfade —
  `/api/v1/plan/termine/bulk`-Form TAB-9), URL-7 (Sprache — TAB-
  Wortlaut).
- `conventions/ports.md` PORT-2 (Loopback-Port-Katalog — Plan-Buddy-
  Origin TAB-9 auf `127.0.0.1:5020`).
- `conventions/data-components.md` DCOMP-1 (Komponenten reden über
  HTTP — TAB-9 schreibt nicht direkt in `plan.db`).
- `conventions/privatchat-session.md` SESS-1..SESS-4 (Privatchat-
  Session-Muster — TAB-3).
- `specs/constitution.md` (App-Eigentümerschaft — E-TAB-2-Anker;
  Qualitätsattribut Privacy — E-TAB-5, E-TAB-6).
- `xbuddy-knowledge/CONTEXT.md` §3 „Privacy" (DE-Hosting-Anker —
  E-TAB-6 Anbieter-Kriterien-Katalog).
- `eltern-chat/confirm.py` (`PendingStore`, `is_confirmation` — Code-
  Stelle für das Bestätigungs-Pattern, das TAB-7 wiederverwendet —
  analog `termin-eintragen.md` TES-7).
