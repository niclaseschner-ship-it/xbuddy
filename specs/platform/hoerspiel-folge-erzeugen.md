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
extrahieren · `POST /api/v1/hoerspiel/<kind_id>/folgen-vorschlag` aufrufen ·
strukturierter Vorschlag (Text + Voice-Default + Bestätigungs-Frage)
zur Bestätigung vorlegen nach EC-10 zweistufig · `POST /api/v1/hoerspiel/<kind_id>/alben`
in `execute()` nach Bestätigung aufrufen · Erfolgs-Bubble mit Album-Link
nach erfolgreichem Build.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Inline-Edit der Vorschau** — wenn die Eltern die Vorschau nicht mögen,
  starten sie den Skill mit anderer Idee neu. Iteratives Re-Rolling auf
  Knopfdruck ist V2.
- **Persistierte Job-Wiederaufnahme nach Restart** — V1.1 (HFE-11/12,
  2026-06-19; ENTSCHEID-File Paket-Sektion „R2-Paket → B) Spec-Patch-
  Skizze" → Restart-Klausel;
  `brainstorm/berater-runde/2026-06-19-1505-RATIFIZIERT-hfe-async-schnitt.md`)
  führt `execute()` im Daemon-Thread im Task aus (Polling-Loop bleibt
  frei); ein Pi-Restart während des Baus verliert den Build, persistente
  Wiederaufnahme bleibt OPEN-HSP-L V2.
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
/api/v1/hoerspiel/<kind_id>/folgen-vorschlag` (HFE-3), **keine** Familien-Daten-
Änderung — die Vorschlag-Erzeugung schreibt nichts (HSP-11). **Ausgang:**
ein strukturierter Vorschlag mit Text-Vorschau, gewählter Voice (Default-
Resolution HFE-4) und Bestätigungs-Frage in einer einzigen Tool-Result-
Antwort.

**`execute()`** läuft **außerhalb** des Agent-Loops nach erfolgter
EC-10-Bestätigung (TASK-10: der `execute()`-Frame darf nach Confirm
selbst senden). **Wirkung:** ein Aufruf an `POST /api/v1/hoerspiel/<kind_id>/alben`
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

**Eingang:** die vom Agent extrahierte Folgen-Idee **und** der `kind_id`
der gewünschten Hörspiel-Instanz (Pflicht-Argument seit RAT-17 /
specs/buddies/hoerspiel.md HSP-28a — V1: `mia` oder `finn`). Der
`kind_id` kommt vom aktiven Face-Pille-State der Mini-App oder, wo
keine Mini-App-Auswahl vorliegt, aus dem Chat-Kontext (LLM-Entscheidung
durch den Eltern-Chat-Agent-Prompt). Der Skill validiert nicht — er
reicht den Wert in den kind_id-tragenden API-Pfad durch und gibt einen
Fehler-Tool-Result-Text aus, wenn der Buddy HTTP 404 antwortet (Instanz
unbekannt).

**kind_id-Extraktionsregel a/b (RAT-17 / #910 / HFE-9):** Der Eltern-Chat-Agent
trägt zwei Pfade: a) `kind_id` ist aus dem Chat-Kontext eindeutig ableitbar
(aktive Mini-App-Face-Auswahl, oder Familie hat genau eine Hörspiel-Instanz)
— Agent übergibt den Wert direkt als Pflicht-Argument, keine Rückfrage;
b) `kind_id` ist unklar — Agent fragt einmalig zurück: „Für welches Kind?"
und wartet die Antwort ab, bevor er `propose()` aufruft. `propose()` ohne
`kind_id` wirft `ValueError` (kein Default — E-HFE-6 / #910).

**Diskussions-Schleife** (Werft-Lauf 2026-06-15, Refs #848): `propose()`
fungiert vor dem Vorschlag-Endpoint-Aufruf als zwei-stufiger Filter:

1. **Idee ist leer oder sehr mehrdeutig** (z. B. nur „mach eine Folge"):
   `propose()` ruft zusätzlich
   `GET /api/v1/hoerspiel/<kind_id>/themen` (HSP-38, URL-3a-konform
   nach RAT-17). Der Buddy liest das Alter aus seiner instance.json
   und liefert die kuratierte Themen-Liste je Alter — **kein** Query-
   Parameter, **keine** Skill-Modul-Konstante für das Alter (vor
   RAT-17 trug der Skill `MIA_ALTER = 4` als V1-Hardcode; dieser
   Cross-Service-Schnitt ist mit RAT-17 / #910 aufgelöst). Antwort-
   Form trägt Alter + Name des Kindes mit zurück, damit der Tool-
   Result-Text personalisierbar bleibt:

   ```
   200 {"kind_id": "mia", "name": "Mia", "alter": 4,
        "themen": ["Mut beim Probieren", "Streit vertragen", …]}
   404 wenn kind_id unbekannt (kein hoerspiel-Pfad für diesen Wert)
   422 wenn Alter der Instanz nicht in instance.json.themen_je_alter
       gepflegt
   ```

   Der Tool-Result-Text trägt **die EC-22-Rückfrage plus die Themen-
   Liste** mit dem Kindernamen: „Worum soll's gehen? Hier ein paar
   Vorschläge für \<Name> (\<Alter> Jahre): \<thema-1>, \<thema-2>, …".
   Antwortet der Themen-Endpoint 422 (Alter nicht gepflegt), trägt der
   Tool-Result-Text **nur** die EC-22-Rückfrage ohne Themen. Bei 404
   (kind_id unbekannt) gibt der Skill einen Fehler-Tool-Result-Text
   aus („Für \<kind_id> gibt es keinen Hörspiel-Buddy.") und ruft den
   Vorschlag-Endpoint nicht.

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

Mit gefüllter konkreter Idee ruft `propose()` die kind_id-tragende
Vorschlag-Route des Hörspiel-Buddys:

```
POST /api/v1/hoerspiel/<kind_id>/folgen-vorschlag
Body: {"idee": "<text>"}
→ 200 {"titel": "<titel>", "text": "<markdown>", "folgen-nr-vorschlag": <int>}
```

Die `<kind_id>`-Segment-Form ist URL-3a-konform und einheitlich für alle
Hörspiel-Routen (HSP-25/26/38, RAT-17). `POST /alben` (HFE-5) folgt
demselben Schema.

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
3. **Bestätigungs-Block** mit gesetzter Voice und Bestätigungs-Frage:

   ```
   Voice: <voice-default>
   Vertonen? Antworte nur mit »ja« (oder 👍). Das dauert 1–5 Minuten.
   ```

   Die Bestätigungs-Frage lenkt **bewusst auf ein Einzelwort der EC-10-Wortliste**
   (`eltern-chat/confirm.py` `CONFIRM_WORDS`): EC-10-Confirm matcht ganze Wörter,
   keine Mehrwort-Antworten. Eine offene Frage („Soll ich vertonen?") provoziert
   Antworten wie „ja vertonen"/„los gehts", die durch `is_confirmation` fallen, im
   Agent-Loop landen und dort als Signal-Phrase (Sub-Case 3) einen erneuten
   `propose()` auslösen statt zu bestätigen — getextet-nie-vertont-Schleife.
   (ENTSCHEID `brainstorm/berater-runde/20260624-152550-RATIFIZIERT-hfe-confirm-konflikt.md`,
   Paket-Teil 1; #1118 / Refs #1050.)

**Voice-Default-Resolution** in `propose()` (#995, 2026-06-18):

- Voice-Wechsel lebt **ausschließlich** in der Hörspiel-Mini-App
  (HSP-34 `PATCH /<kind_id>/config`). Im Chat gibt es **keinen** Override-
  Pfad — kein `voice`-Tool-Argument, kein „mit onyx vertonen"-Trigger.
  Der Agent-Prompt weist solche Phrasen ab mit „Voice wählst du in der
  Hörspiel-Mini-App." (analog Anbieter/Modell-Block, Refs #848/#750).
- `propose()` liest die Default-Voice aus `GET /api/v1/hoerspiel/<kind_id>/config`
  (HSP-26, Default `onyx` seit #995) — **nach** dem 90s-Folgen-Vorschlag-
  LLM-Call. Damit fließt eine Mini-App-Änderung, die die Familie während
  des HFE-10-Tune-Fensters (Settings-Beifang-Button) macht, noch in den
  Bestätigungs-Block ein. (Vorher las propose() die Voice vor dem LLM-Call —
  Race: Voice-Stand war beim Vorschlag bis zu 100 s alt, Live-Befund
  2026-06-17 23:54.)
- Fällt der Config-Aufruf aus (HoerspielClientError), nutzt der Skill den
  Code-Fallback `VOICE_DEFAULT = onyx`. Der Vorschlag wird dabei nicht
  blockiert (degrades gracefully).

**Pflicht-Felder** im Sinne EC-22 sind hier: `idee` (vom Aufrufer);
`voice` ist gar kein Tool-Feld mehr (#995) — sie kommt immer aus der
Buddy-Config und ist in der Mini-App familien-konfigurierbar.

## HFE-5 — `execute()`: Album-Bau auslösen

Nach EC-10-Bestätigung läuft `execute()` außerhalb des Agent-Loops mit
den Argumenten aus dem bestätigten Vorschlag (`titel`, `text`, `voice`,
`idee`). Es ruft den Hörspiel-Buddy:

```
POST /api/v1/hoerspiel/<kind_id>/alben
Body: {"titel": "<titel>", "text": "<text>", "voice": "<voice>", "idee": "<idee>"}
→ 200 {"album-id": "<id>", "manifest-pfad": "<pfad>", "dauer-sek-gesamt": <int>}
```

Der Aufruf blockiert bis zur Fertigstellung. **V1.1 (2026-06-19, HFE-11/12;
ENTSCHEID-File Paket-Sektion „R2-Paket → A) Naht-Liste" → N2 Trampolin;
`brainstorm/berater-runde/2026-06-19-1505-RATIFIZIERT-hfe-async-schnitt.md`)**
führt den Aufruf in einem Daemon-Thread im Task aus, sodass der
Polling-Loop während der 1–5 min frei bleibt; persistente
Job-Wiederaufnahme über Restart hinweg bleibt OPEN-HSP-L V2.
`execute()` darf nach Confirm selbst senden (TASK-10) und postet bei
Erfolg über `tg.send_message` einen Erfolgs-Bubble in den aufrufenden
Chat:

```
✅ Folge <nr> ist in der App.
http://<display-origin>/display/hoerspiel/<kind_id>/alben
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
verankert, nicht im Skill, EC-30-Trennlinie):

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

Diese Signal-Phrasen lösen `propose()` **nur aus, solange noch KEIN Vorschlag
vorliegt** (Diskussions-Phase, Sub-Case 2→3). Wurde der HFE-4-Bestätigungs-Block
(„Vertonen? Antworte nur mit »ja«…") bereits gesendet, darf der Agent denselben
Skill bei einer solchen Phrase **NICHT erneut** aufrufen — die Bestätigung läuft
ab da deterministisch außerhalb des Agenten über EC-10 (`is_confirmation`). Sonst
re-proposed das LLM statt zu vertonen (getextet-nie-vertont-Schleife). Diese
Klausel ist Prompt-getragen (Agent-Compliance), keine deterministische Sperre —
ein deterministisches Agent-Gate ist in `specs/platform/eltern-chat.md` (EC-10,
„Verworfen: Agent-Gate") ausdrücklich verworfen und bliebe eine separate
Spec-Frage. (ENTSCHEID `brainstorm/berater-runde/20260624-152550-RATIFIZIERT-hfe-confirm-konflikt.md`,
Paket-Teil 2; #1118 / Refs #1050.)

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
  8 Themen → Tool-Result-Text trägt die Themen + EC-22-Rückfrage mit
  Kindname; **kein** Vorschlag-Endpoint-Aufruf; `GET /<kind_id>/themen`
  ohne `?alter=`-Query — RAT-17)
- HFE-3 (leere Idee + **kind_id unbekannt**, Mock-Buddy gibt **404** →
  Fehler-Tool-Result-Text: „Für <kind_id> gibt es keinen Hörspiel-Buddy";
  kein Vorschlag-Endpoint-Aufruf)
- HFE-3 (leere Idee + Alter nicht gepflegt, Mock-Buddy gibt **422** →
  Tool-Result-Text trägt **nur** die EC-22-Rückfrage ohne Themen-
  Aufzählung; kein Vorschlag-Endpoint-Aufruf)
- HFE-3 (konkrete-aber-unvollständige Idee → Tool-Result-Text mit
  `{"diskussion": true, "idee_bisher": "<text>"}`-Pattern; **kein**
  Vorschlag-Endpoint-Aufruf)
- HFE-3 (konkrete vollständige Idee nach Diskussion → Standard-Pfad zum
  Vorschlag-Endpoint mit einem `POST /<kind_id>/folgen-vorschlag`)
- HFE-3 (HTTP 503 / 5xx vom Vorschlag-Endpoint → Tool-Result trägt
  Klartext-Hinweis, **kein** Vorschlag-Block, EC-10-Gate löst nicht aus)
- E-HFE-6 / #910 (`propose()` ohne `kind_id` → `ValueError`; `kind_id`
  ist Pflicht-Argument ohne Default)
- HFE-4 (Tool-Result-Text trägt Titel + Vorschau-Text + Bestätigungs-
  Block mit Voice; Intro/Outro nicht im Vorschau-Text; **kein**
  „oder schreib …"-Override-Hinweis, #995)
- HFE-4 / #995 (Voice-Default: `propose()` liest `GET /<kind_id>/config`
  **nach** dem `POST /<kind_id>/folgen-vorschlag`-Aufruf — Reihenfolge-
  Test via Call-Order-Spy; kein `voice`-Tool-Argument; Result-Text trägt
  „Voice: <voice>\n" ohne Override-Phrase)
- HFE-4 / #995 (Code-Fallback bei Config-Fehler → `onyx`,
  `VOICE_DEFAULT = "onyx"`)
- HFE-5 (Confirm → `execute()` ruft `POST /<kind_id>/alben` mit den vier
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

**Differenzierung nach HFE-3-Sub-Case:**

1. **Sub-Case 1 — Leere / mehrdeutige Idee** → `propose()` antwortet mit
   präsentationslosem Tool-Result-Text (EC-22-Rückfrage + Themen-Liste,
   Form (a) nach TASK-10c). Kein Form-(b)-Dict vorhanden — **kein
   Beifang-Button** in dieser ersten Antwort.
2. **Sub-Case 2 — Konkrete-aber-unvollständige Idee** → `propose()`
   antwortet mit präsentationslosem Marker-Text
   (`{"diskussion": true, "idee_bisher": "<text>"}`, Form (a) nach
   TASK-10c). Kein Form-(b)-Dict vorhanden — **kein Beifang-Button** in
   dieser ersten Antwort.
3. **Sub-Case 3 — Konkrete vollständige Idee** → `propose()` ruft den
   Vorschlag-Endpoint und liefert HFE-4-Bestätigungs-Vorschlag. In diesem
   Sub-Case wickelt HFE-10 die Antwort in ein TASK-10c-Form-(b)-Dict
   (`{text, presentation}`, TASK-10c), um den Beifang-Button im
   `presentation.inline_button`-Array zu transportieren — zwei Button-Einträge.

**Folge-Antworten der Diskussions-Schleife** (zweite, dritte, … Rückfrage
des Agents nach der Eröffnung) tragen den Beifang-Button **nicht**. Die
**EC-10-Bestätigungs-Antwort** des Agents trägt den Beifang-Button
**nicht** (Confirm-Phase ist Bestätigungs-Frage, kein Tuning-Anlass mehr).
Die Quittung in `execute()` (Erfolg- oder Fehler-Bubble) trägt den
Beifang-Button **nicht**.

Begründung: einmal pro Anstoß die Tuning-Tür öffnen — nicht jeden
Folge-Turn mit zwei Buttons aufblähen. Konsistent mit EC-29 („eine Stimme
im Turn") und der HFE-7-Klausel: der Beifang ändert nichts an der
sprachlosen `propose()`-Form — er erscheint nur dort, wo `propose()` ohnehin
ein Form-(b)-Dict zurückgibt (Sub-Case 3), das LLM bekommt dann einen
erweiterten `presentation`-Dict-Eintrag.

**Implementations-Hinweis (für Track HSP-2):** Der Skill erkennt, ob es
die erste Antwort des Turns ist, anhand der Abwesenheit eines laufenden
Diskussions-Markers in der Idee (Sub-Case-3-Pfad ist per Definition die
erste und einzige nicht-diskutierende Antwort des propose-Turns — der
Subagent in HSP-2 wählt die saubere Mechanik). Der Beifang-Button wird
ausschließlich im Form-(b)-Dict des Sub-Case-3-Pfades abgelegt (TASK-10c)
— zwei Button-Einträge im `presentation.inline_button`-Array. Wenn `mini_app_base_url` leer
ist (Konfig-Lücke analog HOE-7), **fällt der Beifang-Button still aus**:
kein Fehler-Text, kein Skill-Abbruch — der bestehende HFE-Output bleibt
grün, nur ohne Beifang. Begründung: HFE-Erzeugen-Pfad darf nicht an einer
fehlenden Mini-App-Konfig scheitern; der Beifang ist additiv, nicht Pflicht.

*Test-Implikation:* Skill-Test prüft pro Sub-Case separat:
- **Sub-Case 1 + 2 (erste Antwort):** Rückgabe ist präsentationsloser
  Tool-Result-Text (Form (a)); kein `presentation`-Schlüssel im Return-Wert
  vorhanden; kein Beifang-Button erwartet.
- **Sub-Case 3 (erste Antwort):** Rückgabe ist Form-(b)-Dict; das
  `presentation.inline_button`-Array enthält zwei Einträge, davon einer
  mit Label `⚙️ Einstellungen` und URL endend auf `#einstellungen`.
- **Folge-Diskussions-Antworten** (zweite, dritte, … Rückfrage nach der
  Eröffnung) sowie die Confirm-/Execute-Bubbles enthalten den
  Beifang-Button **nicht**. Die Mechanik, anhand derer der Skill erste
  von Folge-Antworten unterscheidet, wird in HSP-2 festgelegt (kein
  `TurnContext`-Feld vorgeschrieben).
- **Fehlende `mini_app_base_url`:** auch die Sub-Case-3-Antwort enthält
  den Beifang-Button **nicht**; der Rest der Antwort bleibt unverändert.

## HFE-11 — Job-Single-Slot pro Chat (V1.1)

**RATIFIZIERT 2026-06-19** (ENTSCHEID-File Paket-Sektion „R2-Paket → A) Naht-Liste" →
`_HfeJobStore` + Trampolin in `execute()`;
`brainstorm/berater-runde/2026-06-19-1505-RATIFIZIERT-hfe-async-schnitt.md`).

`execute()` läuft ab V1.1 in einem Daemon-Thread im Task — der
Polling-Loop ist während des 1–5-min-Album-Baus frei für andere
Familienmitglieder. Ein in-Memory `_HfeJobStore` (privat im Task-Modul
`hoerspiel_folge_erzeugen_task.py`) hält pro `chat_id` einen Single-Slot:

- **Beim Start eines neuen Jobs:** `try_acquire(chat_id)`.
- **Slot belegt:** Skill returnt sofort eine
  „Ich baue gerade noch eine Folge — bitte kurz warten."-Quittung,
  **kein** zweiter Thread, **kein** zweiter HTTP-Call zum Hörspiel-Buddy.
  Der pending-Vorschlag des belegten `chat_id` wird verworfen; der User
  startet die Folge nach Abschluss der laufenden Bauphase neu
  (verhindert Doppel-Confirm-Risiko).
- **Slot frei:** Daemon-Thread (`name="hfe-job-<chat_id>"`) startet,
  Slot belegt mit `started_at = monotonic()`. Im `finally` immer
  `release(chat_id)`.
- **Stuck-Schutz:** Slot gilt nach **600 s** als „stale" und darf von
  einem neuen `try_acquire` überschrieben werden (Schutz vor silent
  Thread-Tod; im Normalfall räumt `finally` viel früher auf, und der
  HTTP-Album-Timeout `HTTP_TIMEOUT_ALBUM_SEKUNDEN = 600.0` greift
  zuerst).
- **Lock:** `threading.RLock` um die Slot-Map.

JobStore ist explizit **nicht** im Eltern-Chat-`Context`, **nicht** in
einer SESS-Sorte (`conventions/privatchat-session.md`) und **nicht**
über `is_async=True` (`conventions/tasks.md` TASK-5). Codex-Bruch
(Antiberater-Report 2026-06-19): SESS würde den Privatchat „beanspruchen"
(Routing würde User-Nachrichten in nutzlose Queue legen statt zum Agenten),
`is_async=True` kollidiert mit künftigen Hook-Verträgen.

Bei n=2 **vertragsgleichem** Long-Skill wird das Pattern Konvention
(siehe Memory `feedback_berater_zwei_gebaute_beispiele.md` und
`conventions/README.md`-Konventionsregeln). „Vertragsgleich" heißt:
Long-Running-lokaler-HTTP-Call mit User-Quittung und Crash-Bubble,
Single-Slot pro `chat_id`, kein User-Input während des Builds. Andere
Long-Latenz-Pattern (z. B. externer Provider-Retry-Mechanismus, bulk-
synchrone Schreibakte) sind **nicht** automatisch HFE-11-Sorten — vor
Konventions-Bau Vertragsgleichheit prüfen (Start/Blockierstelle, Slot-
Schlüssel, Recovery, Hook-Verhalten, User-Quittung).

*Test-Implikation:* `test_jobstore_single_slot`,
`test_jobstore_timeout` (Mock-`monotonic` 700 s in die Zukunft),
`test_execute_returns_before_album_built` (Mock `hfe_mod.execute` mit
`sleep(2)`, Wall-Clock von `task.execute(...)` < 100 ms),
`test_polling_loop_frei_waehrend_job`,
`test_second_confirm_blocked` (zweites `execute` returnt
sofort mit „warte kurz"-Quittung, kein zweiter Thread),
`test_crash_handler_releases_slot` (Mock `hfe_mod.execute` wirft
`RuntimeError`; Crash-Bubble per `tg.send_message`, Slot freigegeben).

## HFE-12 — Restart-Verlust akzeptiert (V1.1)

**RATIFIZIERT 2026-06-19** (ENTSCHEID-File Paket-Sektion „R2-Paket → B)
Spec-Patch-Skizze" → Restart-Klausel;
`brainstorm/berater-runde/2026-06-19-1505-RATIFIZIERT-hfe-async-schnitt.md`).

Ein Pi-/Heimserver-Restart während eines laufenden HFE-`execute()`-Jobs
verliert den Build. Der Daemon-Thread und sein In-Memory-JobStore-Slot
sind weg; es gibt **keinen** persistierten Job-State, **keine**
Wiederaufnahme nach Restart, **keine** Crash-Notice beim Boot.

Der User merkt es am Ausbleiben der Erfolgs-Bubble und startet die Folge
neu. Eine konsistente Persistenz-Lösung (Job-State-DB, Wiederaufnahme,
Crash-Notice beim Boot) bleibt **OPEN-HSP-L V2**.

Begründung: Pi 5 mit Backup-Strom läuft selten in unkontrollierte
Crashes; der Schmerz ist asymmetrisch zugunsten der täglich auftretenden
Polling-Loop-Blockade (HFE-11), die V1.1 löst.

---

## Entscheidungen

### E-HFE-1 — Skill ist trigger-agnostische Funktion, nicht Telegram-spezifisch
*Datum:* 2026-06-12 · Analog E-WZE-1, E-EZG-1. Wer den Skill aufruft —
Eltern-Chat-Aufgabe in V1, künftiger Sprach-Trigger fürs Kind
(OPEN-HSP-B) in V2 — ist nicht Teil seines Vertrags. Der V1-Trigger ist
eine Eltern-Chat-Aufgabe (EC-8). **Verworfen:** Telegram-API-Aufrufe
oder Chat-Form-Erwartungen in die Funktionsdefinition zu schreiben.

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

### E-HFE-4 — Synchroner Build (V1) / Daemon-Thread im Task (V1.1, 2026-06-19)
*Datum V1:* 2026-06-12 · *Update V1.1:* 2026-06-19 — `execute()` läuft
ab V1.1 im Daemon-Thread im Task; der Polling-Loop ist während des
1–5-min-Album-Baus frei. Details: HFE-11 (Job-Single-Slot pro Chat) und
HFE-12 (Restart-Verlust akzeptiert). Ratifizierungs-Paket:
`brainstorm/berater-runde/2026-06-19-1505-RATIFIZIERT-hfe-async-schnitt.md`.
Persistente Job-Wiederaufnahme über Restart bleibt **OPEN-HSP-L V2**.
**Verworfen V1 (2026-06-12):** Async-Pattern ohne Job-Tracking-Mechanismus,
der zu dem Zeitpunkt nicht tragfähig war.

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

### E-HFE-6 — kind_id-Lookup statt Modul-Konstante (RAT-17)
*Datum:* 2026-06-15 · Refs #910, RAT-17. Vor RAT-17 trug der Skill
`MIA_ALTER = 4` als V1-Modul-Konstante; die zweite Hörspiel-Instanz
Finn brach diese Form (Skill hätte für Finn 4-Jährige-Themen geliefert,
unabhängig von Finns echtem Alter). Mit RAT-17 wird `kind_id` zum
Pflicht-Argument des Skills, und das Alter zieht der Buddy implizit aus
seiner instance.json. **Wahl der Endpoint-Form (architecture_class:
wahl, Nic-Verdikt 2026-06-15-22:50): Variante B** — kind_id im URL-Pfad
(`GET /api/v1/hoerspiel/<kind_id>/themen`) statt Query (`?alter=<n>`).
Begründung: URL-3a-Konsistenz mit allen anderen Hörspiel-Routen
(HSP-25/26), Single Source of Truth pro Instanz (Alter lebt nur in
instance.json), keine Drift-Klasse Skill-Alter vs. Server-Alter.
**Verworfen Variante A** (Query bleibt, kind_id als zusätzliches
Skill-Arg): doppelte Wahrheit, Sonderweg im Schnittprinzip.
