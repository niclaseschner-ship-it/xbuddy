# Hörspiel-Folge erzeugen — Spec     (ID-Präfix: HFE)

> Status: V1 · Refs #729

Damit ein Elternteil im Eltern-Chat eine neue Hörspiel-Folge für Mia
anstoßen kann, definiert diese Spec **Hörspiel-Folge erzeugen als
aufrufbare Funktion**: Sie nimmt eine Folgen-Idee entgegen, lässt vom
Hörspiel-Buddy einen Folgentext erzeugen, legt ihn dem Elternteil mit
Voice-Wahl als strukturierten Vorschlag zur Bestätigung vor und stößt
den Album-Bau beim Hörspiel-Buddy an. Sie gehört zum **Familien-
Schnittstelle-Beitrag** des Hörspiel-Buddys (APP-4, gepflegt vom
Hörspiel-Buddy-Owner).

Die Funktion ist **trigger-agnostisch** (analog WZE-1, EZG-1): wer sie
aufruft — eine Eltern-Chat-Aufgabe in V1, ein Sprach-Trigger für Mia in
V2 (OPEN-HSP-B) — ist nicht Teil ihres Vertrags. **Der LLM-Aufruf lebt
nicht in dieser Funktion** (E-HFE-1, HSP-10/11). Sie ist ein dünner
Konsument zweier Hörspiel-Buddy-Endpoints (`POST /folgen-vorschlag`,
`POST /alben`).

**Lego-Einordnung (`conventions/eltern-chat-skills.md`, 2026-06-12):**
HFE ist eine **Klasse-C-Aufgabe** — kanonisch `propose` → `confirm`,
schreibend mit Vorab-Bestätigung. Die A2-Klausel (Klasse D) trifft
nicht: der Album-Bau ist kein One-Shot-`POST` (1–5 min synchrone TTS-
Pipeline), die Voice-Wahl verlangt einen vorab sichtbaren Vorschlag,
und ein „idempotentes `DELETE`" auf ein gerade gebautes Album mit Audio-
Assets im Sinne der A2-Disziplin gibt es V1 nicht.

**V1-Scope:** Eltern-Chat-Aufgabe als Trigger (EC-8, analog
`termine-erfragen.md` TER-9) · Folgen-Idee aus dem Aufrufer-Text
extrahieren · `POST /api/v1/hoerspiel/folgen-vorschlag` aufrufen ·
strukturierter Vorschlag (Text + Voice-Default + Bestätigungs-Frage)
zur Bestätigung vorlegen nach EC-10 zweistufig · `POST /api/v1/hoerspiel/alben`
in `execute()` nach Bestätigung aufrufen · Erfolgs-Bubble mit Album-Link
nach erfolgreichem Build.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Inline-Edit der Vorschau** — wenn die Eltern die Vorschau nicht mögen,
  starten sie den Skill mit anderer Idee neu. Iteratives Re-Rolling auf
  Knopfdruck ist V2.
- **Async-Generierung mit „später benachrichtigen"** — V1 blockiert in
  `execute()` für die Synthese-Dauer (1–5 min). Async ist OPEN-HSP-L.
- **Audio-Probehören vor Freigabe** — V1 ist Text-Gate (E-HSP-7).
- **LLM-Provider/-Modell-Wechsel im selben Chat** — seit Werft-Lauf
  2026-06-15 (Refs #848, schließt OPEN-HSP-N #750) lebt der Wechsel in
  der Eltern-Mini-App (HSP-34 `PATCH /config`), nicht in einem
  Chat-Skill. Dieser Skill hier wechselt weder Provider noch Modell.
- **Sprach-Trigger für Mia** — V2 (OPEN-HSP-B); bedient denselben
  Vorschlag-Endpoint.

---

## HFE-1 — Hörspiel-Folge erzeugen ist eine `WriteTask` (Klasse C)

„Hörspiel-Folge erzeugen" ist eine klar abgegrenzte, **aufrufbare
Funktion** mit definierter Schnittstelle. Implementations-Form: eine
`WriteTask` mit `propose()` + `execute()` (TASK-4) — die kanonische
Bauform für Klasse C nach
[`conventions/eltern-chat-skills.md`](../../conventions/eltern-chat-skills.md).

**`propose()`** läuft im Agent-Loop und ist **sprachlos im Sinne EC-29**
(TASK-10): der Skill returnt einen User-tauglichen Antwort-Text als
Tool-Result-String, das LLM postet die Bot-Nachricht. **Eingang:** die
Telegram-Chat-Identität, die Telegram-User-ID des Aufrufers, und eine
**Folgen-Idee** als Text (1–2 Sätze, vom Agent aus der Eltern-Nachricht
extrahiert). **Wirkung:** ein lesender Aufruf an `POST
/api/v1/hoerspiel/folgen-vorschlag` (HFE-3), **keine** Familien-Daten-
Änderung — die Vorschlag-Erzeugung schreibt nichts (HSP-11). **Ausgang:**
ein strukturierter Vorschlag mit Text-Vorschau, gewählter Voice (Default-
Resolution HFE-4) und Bestätigungs-Frage in einer einzigen Tool-Result-
Antwort.

**`execute()`** läuft **außerhalb** des Agent-Loops nach erfolgter
EC-10-Bestätigung (TASK-10: der `execute()`-Frame darf nach Confirm
selbst senden). **Wirkung:** ein Aufruf an `POST /api/v1/hoerspiel/alben`
(HFE-5) und ein Erfolgs- oder Fehler-Bubble mit Album-Link über
`tg.send_message`.

Die Funktion ist **trigger-agnostisch** (E-HFE-1 analog E-WZE-1). Der
LLM-Aufruf zur Folgen-Erzeugung lebt **nicht** in dieser Funktion — er
lebt im Hörspiel-Buddy (HSP-10/11, E-HFE-2).

## HFE-2 — Berechtigung: Eltern

Die Funktion ist nur für Telegram-User mit Status `Eltern` aufrufbar
(analog WZE-2, EZG-2). Berechtigungs-Bruch im Agent-Loop wirft
`BerechtigungError` aus `eltern-chat/skills/_errors.py` (TASK-10) — kein
skill-eigener Exception-Typ.

## HFE-3 — `propose()`: Folgen-Vorschlag holen und vorlegen

**Eingang:** die vom Agent extrahierte Folgen-Idee.

**Diskussions-Schleife** (Werft-Lauf 2026-06-15, Refs #848): `propose()`
fungiert vor dem Vorschlag-Endpoint-Aufruf als zwei-stufiger Filter:

1. **Idee ist leer oder sehr mehrdeutig** (z. B. nur „mach eine Folge"):
   `propose()` ruft zusätzlich `GET /api/v1/hoerspiel/themen?alter=4`
   (HSP-38; der Alter-Wert lebt V1 hart als Skill-Modul-Konstante für
   Mia, Mehr-Kind-Petrallgemeinerung ist V2) und gibt einen Tool-
   Result-Text zurück, der **die EC-22-Rückfrage plus die Themen-Liste**
   trägt. Form: „Worum soll's gehen? Hier ein paar Vorschläge für
   4-jährige Kinder: <thema-1>, <thema-2>, …" — Kein Buddy-Vorschlag-
   Endpoint-Aufruf. Antwortet der Themen-Endpoint 404 (Alter nicht
   gepflegt, HSP-38), trägt der Tool-Result-Text **nur** die
   EC-22-Rückfrage ohne Themen.

2. **Idee ist konkret aber unvollständig** (z. B. „mach eine Folge über
   Mut"): `propose()` gibt einen Tool-Result-Text mit Pattern
   `{"diskussion": true, "idee_bisher": "<text>"}` zurück. Der Eltern-
   Chat-Agent stellt 1–N Rückfragen, um die Idee zu konkretisieren
   („mit Stigi alleine oder Schmuggli dabei?", „lustig oder lehrreich?").
   Die Rückfragen leben **im Agent-Prompt** (EC-30-Trennlinie), nicht
   im Skill — der Skill nimmt nur den Diskussions-Trigger entgegen.

**Eltern-Signal beendet die Diskussion.** Die Mutter äußert ein
Vorschlag-Trigger-Signal („los", „los gehts", „schreib", „mach das",
„passt so", „fang an", „jetzt vertonen", „okay so" — Phrasen leben
im Eltern-Chat-Agent-Prompt). Der Agent ruft daraufhin `propose()`
**erneut** mit der zusammengeführten konkreten Idee aus der Diskussion
(kein `diskussion: true` mehr). Der Skill geht den Standard-Pfad und
ruft den Vorschlag-Endpoint.

**Kein technischer Loop-Schutz im Skill** (Nic-Setzung 2026-06-15):
die Mutter entscheidet, wann genug Klärung war. Eine Iterations-Cap
im Skill würde die Eltern-Hoheit über die Diskussion verletzen.

Mit gefüllter konkreter Idee ruft `propose()` den Hörspiel-Buddy:

```
POST /api/v1/hoerspiel/folgen-vorschlag
Body: {"idee": "<text>"}
→ 200 {"titel": "<titel>", "text": "<markdown>", "folgen-nr-vorschlag": <int>}
```

Der Aufruf dauert je nach LLM-Provider 20–90 s. **Während des Aufrufs
darf `propose()` keinen separaten „Moment …"-Bubble senden** (EC-29:
eine Stimme im Turn). Der Wartezeit-Hinweis liegt — wenn überhaupt
nötig — im LLM-System-Prompt der Eltern-Chat-Aufgabe, nicht im Skill.

Mit der Antwort baut `propose()` den strukturierten Vorschlag als
Tool-Result-Text (HFE-4) und gibt ihn zurück. Das LLM formuliert
daraus die Bot-Nachricht.

**Fehlerpfade in `propose()`:**

- HTTP 503 (kein LLM-Provider-Key, HSP-26): Tool-Result-Text trägt
  „Der LLM-Provider ist nicht eingerichtet — gerade kann keine Folge
  geschrieben werden."
- HTTP 5xx sonst / Timeout: Tool-Result-Text trägt „Der GeschichtenBuddy
  ist gerade nicht erreichbar."

In beiden Fehlerpfaden wird **kein Vorschlag** vorgelegt — das EC-10-Gate
löst nicht aus, `execute()` wird nicht gerufen.

## HFE-4 — Strukturierter Vorschlag mit Voice-Default

Der Tool-Result-Text aus `propose()` trägt drei Blöcke, in dieser
Reihenfolge (Quittung-trägt-geparste-Werte-prominent-zuerst-Prinzip
analog EC-10):

1. **Titel-Zeile** mit Folgen-Nummer-Vorschlag und Titel
2. **Vollständiger Folgentext** der Vorschau (Markdown, Absätze mit `\n\n`).
   Intro/Outro-Reime sind in der Vorschau **nicht** enthalten — sie sind
   geteilte Serien-Assets (HSP-8) und für die Eltern-Freigabe nicht
   relevant.
3. **Bestätigungs-Block** mit gewählter Voice und Bestätigungs-Frage:

   ```
   Voice: <voice-default> (oder schreib „shimmer" / „onyx")
   Soll ich vertonen? Das dauert 1–5 Minuten.
   ```

**Voice-Default-Resolution** in `propose()`:

- Hat der Aufrufer im selben Turn eine Voice genannt (`shimmer`/`onyx`),
  setzt `propose()` diese Voice.
- Sonst liest `propose()` die Default-Voice aus `GET
  /api/v1/hoerspiel/config` (HSP-26, Default `shimmer`) und nutzt sie.
- Antwortet der Aufrufer auf den Vorschlag mit „onyx" statt
  Bestätigungswort, ruft der Agent `propose()` erneut mit der neuen
  Voice — der vorherige Vorschlag wird ersetzt (Standard-EC-10-
  Verhalten ohne Sonderregel).

**Pflicht-Felder** im Sinne EC-22 sind hier: `idee` (vom Aufrufer);
`voice` ist nie Pflicht-Feld, sie hat immer einen Default.

## HFE-5 — `execute()`: Album-Bau auslösen

Nach EC-10-Bestätigung läuft `execute()` außerhalb des Agent-Loops mit
den Argumenten aus dem bestätigten Vorschlag (`titel`, `text`, `voice`,
`idee`). Es ruft den Hörspiel-Buddy:

```
POST /api/v1/hoerspiel/alben
Body: {"titel": "<titel>", "text": "<text>", "voice": "<voice>", "idee": "<idee>"}
→ 200 {"album-id": "<id>", "manifest-pfad": "<pfad>", "dauer-sek-gesamt": <int>}
```

Der Aufruf blockiert bis zur Fertigstellung (V1 synchron; OPEN-HSP-L).
`execute()` darf nach Confirm selbst senden (TASK-10) und postet bei
Erfolg über `tg.send_message` einen Erfolgs-Bubble in den aufrufenden
Chat:

```
✅ Folge <nr> ist in der App.
http://<display-origin>/display/hoerspiel/alben
```

Die Display-Origin kommt aus der bestehenden Eltern-Chat-Config
(`display_url_origin`, EC-15 / GAA-3.7), nicht aus einer skill-eigenen
Quelle.

**Fehlerpfade in `execute()`:**

- HTTP 412 (Shared-Assets fehlen für die Voice, HSP-29): Bubble „Die
  Intro/Outro-Aufnahmen für `<voice>` müssen erst einmalig
  vorsynthetisiert werden." — keine Auto-Rebuild-Logik im Skill
  (HSP-29 koppelt das an einen Setup-Aufruf des Hub-Owners, nicht den
  Skill).
- HTTP 503 (Azure-TTS nicht erreichbar): Bubble „Die Vertonungs-Engine
  ist gerade nicht erreichbar." — die Folge ist nicht gebaut, der
  Aufrufer kann später erneut anstoßen.
- HTTP 5xx sonst: Bubble „Beim Album-Bau ist etwas schiefgegangen."

In allen Fehlerpfaden ist die **Folgen-Historie unverändert** (HSP-15
koppelt das Historie-Update an Album-Bau-Erfolg).

## HFE-6 — Trigger-Phrasen (für LLM-Intent)

Der Eltern-Chat-Agent erkennt diese Phrasen als HFE-Aufruf (Beispiele,
nicht abschließend — die LLM-Intent-Erkennung ist im Agent-Prompt
petrankert, nicht im Skill, EC-30-Trennlinie):

- „Schreib eine Folge in der …"
- „Eine neue Folge über …"
- „Mach Mia eine Folge zu …"
- „Hörspiel-Folge: <Idee>"
- „Neues Hörbuch über …"

**Themen-Anfrage-Phrasen** (HFE-3 erweitert 2026-06-15 Refs #848 — der
Agent ruft `propose()` mit leerer Idee, was die Themen-Liste auslöst):

- „Welche Themen gibt es?"
- „Was könnte ich Mia erzählen?"
- „Vorschläge?"
- „Mach Mia eine Folge." (ohne Inhalts-Stichwort)

**Eltern-Signal-Phrasen** (HFE-3 erweitert — beenden die Diskussion und
triggern den Vorschlag-Endpoint):

- „los", „los gehts", „los, schreib"
- „mach das", „passt so", „okay so", „fang an"
- „jetzt vertonen", „schreib jetzt"

**Abgrenzung zu Provider-/Modell-Wechsel:** Wechsel von LLM-Provider
oder Modell lebt seit Werft-Lauf 2026-06-15 (Refs #848, schließt
OPEN-HSP-N #750) in der Eltern-Mini-App (HSP-34 `PATCH /config`),
nicht in einem eigenen Chat-Skill. Eltern-Nachrichten der Form
„wechsel auf mistral" werden vom Agent mit einem Hinweis-Text
beantwortet („Anbieter und Modell wählst du in der Hörspiel-Mini-App")
und **nicht** als HFE-Trigger interpretiert.

## HFE-7 — Eine Stimme im Agent-Turn (EC-29)

`propose()` postet **nichts** selbst — kein „Moment …"-Bubble, kein
Zwischenstand, keine Voice-Rückfrage als eigener Telegram-`send_message`.
Der gesamte User-sichtbare Text der Propose-Phase liegt im Tool-Result-
String, das LLM formt die Bot-Nachricht (EC-29, TASK-10).
`execute()` ist außerhalb des Agent-Loops und sendet selbst (TASK-10
expliziter Ausschluss).

## HFE-8 — Skill-Modul-Verortung und Owner

Skill-Modul: `eltern-chat/skills/hoerspiel_folge_erzeugen.py` (Aufgabe
nach `WriteTask`-Pattern, TASK-4) + Registrierung in `build_catalog`
(TASK-7). Wenn `POST /alben` einen Reload-Trigger an einer fremden
Komponente nötig macht (V1: nein, der Hörspiel-Buddy aktualisiert das
View-Backend selbst), wird das über `post_execute_hooks` (TASK-6)
angebunden.

Der Owner ist der **Hörspiel-Buddy-Owner** (APP-4); Änderungen an dieser
Funktion (Vorschlag-Format, Trigger-Phrasen, Voice-Default-Resolution)
werden im Rahmen von Hörspiel-Buddy-Tickets gepflegt.

**Wenn** der Hörspiel-Buddy nicht erreichbar ist (HFE-3-Fehler), **dann**
ist die Funktion lese-/schreibfrei für Familien-Daten — sie hat selbst
keinen Datenbereich, keinen Cache, keine Persistenz.

## HFE-9 — Tests je Anforderung (ohne Netz)

Automatisierte Tests, reproduzierbar **ohne Netz** (der Hörspiel-Buddy
wird durch einen kontrollierten Doppelten ersetzt):

- HFE-2 (Berechtigung: `BerechtigungError` aus `_errors.py` für
  nicht-Eltern-User; kein Buddy-Aufruf erfolgt)
- HFE-3 (leere Idee + Themen-Liste verfügbar, Mock-Buddy gibt 200 mit
  8 Themen für Alter 4 → Tool-Result-Text trägt die Themen + EC-22-
  Rückfrage; **kein** Vorschlag-Endpoint-Aufruf)
- HFE-3 (leere Idee + Alter ohne Themen-Liste, Mock-Buddy gibt 404 →
  Tool-Result-Text trägt **nur** die EC-22-Rückfrage, keine Themen-
  Aufzählung; kein Vorschlag-Endpoint-Aufruf)
- HFE-3 (konkrete-aber-unvollständige Idee → Tool-Result-Text mit
  `{"diskussion": true, "idee_bisher": "<text>"}`-Pattern; **kein**
  Vorschlag-Endpoint-Aufruf)
- HFE-3 (konkrete vollständige Idee nach Diskussion → Standard-Pfad zum
  Vorschlag-Endpoint mit einem `POST /folgen-vorschlag`)
- HFE-3 (HTTP 503 / 5xx vom Vorschlag-Endpoint → Tool-Result trägt
  Klartext-Hinweis, **kein** Vorschlag-Block, EC-10-Gate löst nicht aus)
- HFE-4 (Tool-Result-Text trägt Titel + Vorschau-Text + Bestätigungs-
  Block mit Voice; Intro/Outro nicht im Vorschau-Text)
- HFE-4 (Voice-Default: kein Voice-Hinweis im Aufrufer-Text → Skill
  liest `GET /config` und setzt Default; Voice im Aufrufer-Text →
  diese Voice gesetzt)
- HFE-5 (Confirm → `execute()` ruft `POST /alben` mit den vier
  Vorschlag-Feldern; erfolgreicher Build → Erfolgs-Bubble mit Display-URL;
  HTTP 412 → Shared-Asset-Hinweis ohne erneuten Build-Versuch; HTTP 503
  / 5xx → Fehler-Bubble ohne Build-Versuch)
- HFE-7 (Routing-Test: in `propose()` erfolgt kein `tg.send_*`-Aufruf;
  Verifikation analog der Lint-/Test-Baseline aus TASK-10 Helper-Grenze)
- HFE-8 (Skill ist in `build_catalog` registriert; `Catalog.register`
  akzeptiert die `WriteTask`-Vererbung)

Läufe gegen echte Engines (Hörspiel-Buddy mit echter Azure-/LLM-Anbindung)
sind opt-in und nicht Teil der V1-Standard-Test-Suite.

## HFE-10 — Settings-Beifang-Button (einmal pro Turn, erste `propose()`-Antwort)

**Werft-Lauf 2026-06-15 (Refs #848).** In der **ersten** `propose()`-
Antwort eines HFE-Turns trägt das presentation-Dict einen **zweiten**
inline_button neben dem Bestätigungs-/Antwort-Knopf:

- **Label:** `⚙️ Einstellungen`
- **web_app_url:** `<mini_app_base_url>/seiten/hoerspiel/eltern#einstellungen`

Damit bekommt Eltern **einmal pro Anstoß** die Chance, vor dem Album-Bau
Voice / LLM-Anbieter / LLM-Modell / Playback-Tempo / Pausen in der
Eltern-Mini-App (HSP-33, HSP-34) zu tunen — ohne den HFE-Turn zu
verlassen, ohne einen separaten HOE-Aufruf provozieren zu müssen.

**Gilt für alle drei HFE-3-Sub-Cases der ersten `propose()`-Antwort:**

1. **Leere / mehrdeutige Idee** → Themen-Liste + EC-22-Rückfrage → erste
   Antwort trägt Beifang-Button.
2. **Konkrete-aber-unvollständige Idee** → Diskussions-Pattern
   (`{"diskussion": true, ...}`) → erste Antwort trägt Beifang-Button.
3. **Konkrete vollständige Idee** → Standard-Pfad mit Vorschlag-Endpoint-
   Aufruf → erste Antwort (mit Bestätigungs-Vorschlag) trägt Beifang-
   Button.

**Folge-Antworten der Diskussions-Schleife** (zweite, dritte, … Rückfrage
des Agents nach der Eröffnung) tragen den Beifang-Button **nicht**. Die
**EC-10-Bestätigungs-Antwort** des Agents trägt den Beifang-Button
**nicht** (Confirm-Phase ist Bestätigungs-Frage, kein Tuning-Anlass mehr).
Die Quittung in `execute()` (Erfolg- oder Fehler-Bubble) trägt den
Beifang-Button **nicht**.

Begründung: einmal pro Anstoß die Tuning-Tür öffnen — nicht jeden
Folge-Turn mit zwei Buttons aufblähen. Konsistent mit EC-29 („eine Stimme
im Turn") und der HFE-7-Klausel: der Beifang ändert nichts an der
sprachlosen `propose()`-Form — er erscheint im selben Tool-Result-Text,
das LLM bekommt einen erweiterten `presentation`-Dict-Eintrag.

**Implementations-Hinweis (für Track HSP-2):** Der Skill erkennt „erste
Antwort des Turns" anhand des `turn_context`-Markers (analog dem
Diskussions-Trigger-Pattern aus HFE-3 — der Subagent in HSP-2 wählt die
saubere Mechanik). Der Beifang-Button wird im **gleichen** Form-(b)-Dict
abgelegt (TASK-10c) — zwei Button-Einträge im `inline_keyboard`. Wenn
`mini_app_base_url` leer ist (Konfig-Lücke analog HOE-7), **fällt der
Beifang-Button still aus**: kein Fehler-Text, kein Skill-Abbruch — der
bestehende HFE-Output bleibt grün, nur ohne Beifang. Begründung: HFE-
Erzeugen-Pfad darf nicht an einer fehlenden Mini-App-Konfig scheitern;
der Beifang ist additiv, nicht Pflicht.

*Test-Implikation:* Skill-Test prüft, dass die erste `propose()`-
Antwort des Turns (alle drei Sub-Cases je einmal) im
`presentation.inline_button`-Array zwei Einträge enthält, davon einer
mit Label `⚙️ Einstellungen` und URL endend auf `#einstellungen`.
Folge-Diskussions-Antworten (`{"diskussion": true, ...}` mit
`turn_context.is_first = false`) sowie die Confirm-/Execute-Bubbles
enthalten den Beifang-Button **nicht**. Bei fehlender
`mini_app_base_url` enthält auch die erste Antwort den Beifang-Button
**nicht**, der Rest der Antwort bleibt unverändert.

---

## Entscheidungen

### E-HFE-1 — Skill ist trigger-agnostische Funktion, nicht Telegram-spezifisch
*Datum:* 2026-06-12 · Analog E-WZE-1, E-EZG-1. Wer den Skill aufruft —
Eltern-Chat-Aufgabe in V1, künftiger Sprach-Trigger für Mia (OPEN-HSP-B)
in V2 — ist nicht Teil seines Vertrags. Der V1-Trigger ist eine Eltern-
Chat-Aufgabe (EC-8). **Verworfen:** Telegram-API-Aufrufe oder Chat-Form-
Erwartungen in die Funktionsdefinition zu schreiben.

### E-HFE-2 — Skill ist dünner Konsument, LLM-Aufruf lebt im Hörspiel-Buddy
*Datum:* 2026-06-12 (Werft-Lauf) · APP-1: die Folgen-Erzeugungs-Funktion
braucht die Welt-Bible-Daten, gehört darum zur App, der die Daten gehören
(HSP-1, HSP-11, E-HSP-6). Der Skill ist trigger-agnostischer Bot-Adapter;
er ruft `POST /folgen-vorschlag` und `POST /alben`, ohne eigenen LLM-
Provider und ohne eigene Bible-Kenntnis. **Verworfen:** LLM-SDK im Skill,
Bible-Pull per `GET /bible` + lokales Prompten (würde Skill dick machen,
APP-1 verletzen, Trigger-Agnostik verletzen).

### E-HFE-3 — Text-Gate vor Vertonung (V1)
*Datum:* 2026-06-12 (Brainstorm 2026-06-11/12, E-HSP-7) · Eltern geben den
Folgentext frei, **bevor** das Album gebaut wird — keine Synthese ohne
Bestätigung. Audio-Probehören ist offen für V2 und vermutlich nicht
nötig. **Verworfen:** Audio-Probehör-Gate, das Synthese-Kosten + 1–5 min
Wartezeit für möglicherweise verworfene Aufnahmen verursacht.

### E-HFE-4 — Synchroner Build mit Wartezeit-Hinweis
*Datum:* 2026-06-12 · V1 hält `execute()` 1–5 min lang offen und meldet
bei Fertigstellung den Link. Eine asynchrone Variante mit Benachrichtigung
am Ende ist OPEN-HSP-L. **Verworfen:** Async-Pattern in V1 (verlangt einen
Job-Tracking-Mechanismus, der V1 noch nicht trägt).

### E-HFE-5 — Klasse C, nicht Klasse D (A2-Klausel trifft nicht)
*Datum:* 2026-06-12 (Werft-Lauf, gegen die am selben Tag ratifizierte
Lego-Initiative `conventions/eltern-chat-skills.md`) · A2 verlangt
One-Shot-Schreibakt + stabile ID + idempotentes `DELETE` + Pre-Flight-
Check. HFE bricht die ersten zwei Bedingungen: der Album-Bau ist eine
1–5-minütige Pipeline mit TTS-Kosten je Aufruf (kein One-Shot), und die
„Rückgängigmachung" einer gebauten Folge mit Audio-Assets ist V1 nicht
als idempotentes `DELETE` modelliert. Die Voice-Wahl braucht zudem eine
vorab sichtbare Vorschau (E-HFE-3). Klasse C (EC-10 zweistufig) ist
darum die richtige Form. **Verworfen:** A2-Sofort-Write mit Undo-Wort
(würde den Text-Gate-Schutz E-HFE-3 unterlaufen und gegen die HSP-29-
Vorsynthese-Disziplin laufen).
