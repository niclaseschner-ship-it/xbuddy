# Katalog-Aufgaben — Konvention     (ID-Präfix: TASK)

Der Eltern-Chat-Agent verfügt über einen **Katalog** abgrenzbarer Aufgaben,
die er auf Wunsch der Familie ausführt (EC-8). Es gibt bereits mehrere
Exemplare derselben Sorte — lesende (CAV, TER) und schreibende (FAA, GAA, KAV,
TES). Diese Konvention legt fest, wie ein **neues** Katalog-Aufgaben-Exemplar
gebaut, registriert und verkabelt wird, damit ein Beitragender ein weiteres
liefern kann, indem er die hier **benannten** Andock-Punkte bedient — statt sie
aus sechs Beispielen zusammenzureimen. Sie verspricht **nicht**, dass kein
gemeinsamer Code angefasst wird: die Aktivierung ist heute zentral
(`build_catalog`, TASK-7), und eine async-Privatchat-Aufgabe braucht zusätzlich
einen Eintrag in `_SESSION_SORTS` (`main.py`), damit `handle_update` das
Privatchat-Routing generisch übernimmt (SESS-5/#264 — gemeinsamer Session-Router
seit #264). Die Konvention macht diese Punkte sichtbar; sie beseitigt sie nicht.

Verhalten der einzelnen Aufgaben gehört **nicht** hierher, sondern in die
jeweilige Komponenten-Spec. Heimat der Katalog-Mechanik:
`specs/platform/eltern-chat.md` EC-8 (Katalog), EC-9 (lesend), EC-10
(schreibend mit Bestätigungs-Gate), EC-21 (Post-Execute-Hooks). Die
Privatchat-Form schreibender, mehrstufiger Aufgaben regelt
`conventions/privatchat-session.md` (SESS); die Verortung familienseitiger
App-Beiträge regelt `conventions/apps.md` APP-4.

### TASK-1 — Eine Aufgabe = ein `_task`-Modul, dünner Trigger
Jede Katalog-Aufgabe wohnt in einem eigenen Modul `skills/<aufgabe>_task.py`,
benannt nach der **Aufgabe** (z. B. `ca_task.py`, `termine_erfragen_task.py`,
`geraet_anlegen_task.py`, `termin_eintragen_task.py`,
`kalender_verbinden_task.py`, `familie_anlegen_task.py`). Das Modul enthält
die `ReadTask`/`WriteTask`-Unterklasse und ist ein **dünner Trigger** der
eigentlichen, trigger-agnostischen Funktion — nicht deren Heimat.

Die trigger-agnostische Funktion darf **anders heißen** als das Modul und in
einem **eigenen** Modul wohnen: `ca_task.py` ruft `verteile_ca` aus
`skills/ca_verteilung.py` (`ca_task.py:83`), die Aufgaben-Klasse heißt
`CaVerteilungTask` (`ca_task.py:28`). So bleibt dieselbe Fähigkeit von einem
anderen Trigger (Onboarding, Display) aufrufbar, ohne den Telegram-Pfad
mitzuschleppen.

### TASK-2 — `arguments` ist der Modell-Kanal, `turn_context` der Fakten-Kanal
Eine Aufgabe trennt zwei Eingabe-Quellen strikt: `arguments` ist das, was das
**Modell** vorschlägt (vom Nutzer-Text abgeleitet, manipulierbar);
`turn_context` (`TurnContext`) trägt die **deterministischen** Fakten der
Laufzeit (Chat-ID, ausführende Person, Berechtigungs-Ergebnis), die das Modell
**nicht** beeinflusst.

Sicherheits- und Routing-relevante Werte — vor allem der **Ziel-Chat** —
werden **immer** aus `turn_context` gelesen, **nie** aus `arguments`. Eine
Aufgabe, die den Zielchat aus dem Modell-Kanal nähme, ließe sich per
Prompt-Injection umleiten (vgl. `ca_task.py:33`).

### TASK-3 — Lesende Aufgabe: `ReadTask` mit `run`
Eine lesende Aufgabe (EC-9) erbt von `ReadTask` und implementiert
`run(self, arguments, turn_context) -> str`. Sie liefert nur Information und
ändert **keine** Familien-Daten — kein Bestätigungs-Gate, kein Hook
(`tasks.py:120-131`).

### TASK-4 — Schreibende Aufgabe: `WriteTask` mit `propose` + `execute`
Eine schreibende Aufgabe (EC-10) erbt von `WriteTask` und implementiert beide
Hälften des Bestätigungs-Gates: `propose(self, arguments, turn_context)` legt
einen `Proposal` vor und führt **nichts** aus; `execute(self, arguments,
turn_context)` führt erst **nach** Bestätigung aus (`tasks.py:163-169`).

**TurnContext-Persistenz zwischen propose und execute (Medien-Naht).** Das
Bestätigungs-Gate (EC-10, `confirm.py`) überführt die deterministischen
`TurnContext`-Felder des propose-Turns **transparent** in den execute-Turn:
`media_telegram_file_id` und `medium_typ` werden im `PendingProposal`
(`confirm.py`) festgehalten und in `_execute_confirmed` (`main.py`) in den
neuen `TurnContext` zurückgespielt. Der confirm-Turn trägt nur das
Bestätigungswort — keine Medien-Naht. So sieht `execute()` denselben
deterministischen Kontext wie `propose()`, auch wenn dazwischen keine
Mediendaten ankamen. Bei Schreib-Aufgaben ohne Medium (TES/FAA/GAA/KAV/…)
bleiben beide Felder `None` — kein Verhaltensunterschied zum bisherigen Pfad.
(Refs #514)

Vom Typsystem erzwungen ist nur die **Basisklasse**: `Catalog.register` wirft
`TypeError`, wenn eine Aufgabe weder `ReadTask` noch `WriteTask` ist
(`tasks.py:185-186`). Die **Methoden** selbst sind nicht abstrakt, sondern
werfen `NotImplementedError` (`tasks.py:125-131`, `tasks.py:163-169`) — eine
`WriteTask` ohne korrekt signiertes `execute` wird **registriert** und bricht
erst zur Laufzeit. Die Vollständigkeit von `run`/`propose`/`execute` muss
deshalb Review/Test prüfen, nicht der Import.

### TASK-5 — `is_async` deklariert das Worker-Thread-Pattern korrekt
Eine schreibende Aufgabe, deren `execute()` nur eine **Privatchat-Kurzquittung**
zurückgibt und die eigentliche Schreib-Operation in einem **Worker-Thread**
fortsetzt (mehrstufiger Privatchat-Dialog, SESS), setzt `is_async = True`. Das
Framework liest dieses Klassenattribut und **überspringt** dann die
inline-Hook-Iteration — die Post-Execute-Hooks werden zur Selbstaufgabe des
Workers und am Thread-Ende gefeuert, nicht beim `execute()`-Return
(`tasks.py:218-232`).

`is_async` ist **nicht** code-erzwungen: vergisst eine async-Aufgabe das Flag,
laufen ihre Hooks zu früh (auf einer noch nicht geschriebenen Änderung). Eine
synchrone Aufgabe lässt das Attribut beim Default `False` (`tasks.py:161`).

### TASK-6 — `post_execute_hooks` sind zustandslos und dürfen nicht zurückrollen
Eine schreibende Aufgabe, die nach erfolgreicher Schreib-Operation einen
Konsumenten zum Cache-Reload auffordern muss (EC-21, #140 Skill-Service-Reload),
deklariert das über das Klassenattribut `post_execute_hooks` — eine Liste
**zustandsloser** Hooks. Das Framework iteriert sie nach `execute()`, isoliert
jeden Hook (eine Hook-Exception wird als `HookFailure` gefangen) und fasst
Fehler in **einer** Warnung an die Familie zusammen (`tasks.py:233-250`).

Ein Hook-Fehler rollt die Schreib-Aufgabe **nicht** zurück: die Änderung ist
durch (`tasks.py:210-212`). Default ist die leere Liste — ohne Deklaration
ändert sich am Verhalten nichts (`tasks.py:155`).

Deklariert wird typischerweise als **Klassenattribut**; eine Aufgabe darf die
Liste aber **per Instanz** überschreiben, wenn familien-spezifische
Konfiguration in den Hook muss (Origin/Port des Konsumenten) — KAV baut seine
`ReloadHook`-Liste je Instanz aus `plan_origin_url`
(`kalender_verbinden_task.py:150-154`). Der Hook bleibt zustandslos; nur seine
Ziel-URL ist instanz-konfiguriert (CONFIG-2).

### TASK-7 — Registrierung in `build_catalog`, mit der RICHTIGEN Session-Map (V1)
Eine neue Aufgabe wird in `build_catalog` (`tasks.py:253-380`) registriert —
das ist die heutige V1-Heimat der Aktivierung, **bis** der in `apps.md` APP-4
beschriebene Installations-/Aktivierungs-Mechanismus existiert (#296 —
App-Installations-Prozess für Familien-Schnittstelle fehlt). Diese Regel
versteinert `build_catalog` nicht; sie hält den heutigen Beitrag nur an einem
Ort.

Eine schreibende Aufgabe mit Worker-Thread (TASK-5) **muss** dabei mit der
**richtigen** Session-Map verkabelt werden — genau der Map, die `handle_update`
für das Privatchat-Routing liest (via `_SESSION_SORTS`-Eintrag, `main.py` —
generische Iteration seit SESS-5/#264, FAA/GAA/KAV/TES/PAA). Wird eine
async-Schreib-Aufgabe ohne ihre
Session-Map oder mit der falschen Map registriert, fängt ein reiner
**Registrierungs**-Test das **nicht**: `build_catalog` ersetzt eine fehlende
Map durch ein leeres `{}` (`tasks.py:365`), und der Katalog-Test prüft nur die
Anwesenheit der Aufgabe (`tests/test_termin_eintragen_task.py:180-199`). Die
stille Lego-Falle: Die Aufgabe ist registriert und der Worker schreibt in seine
Map, aber `handle_update` liest eine **andere** Map — die Familie antwortet im
Privatchat und landet nie beim Worker. Eine neue async-Aufgabe braucht deshalb
einen Test, der das **Routing** durch `handle_update` über die geteilte
Session-Map prüft — so wie TES ihn inzwischen hat
(`test_handle_update_routes_to_tes_session`,
`tests/test_termin_eintragen_task.py:316`), nicht nur die Katalog-Anwesenheit.

### TASK-9 — Sofort-Schreib-Aufgabe (Read-API mit Schreib-Wirkung, Undo statt Confirm)
Eine **Sofort-Schreib-Aufgabe** ist eine **ReadTask** im Sinne von TASK-3 —
also über `run`/`execute` im lesenden Pfad des Agent-Loops (`agent.py:run_turn()`)
— läuft aber mit **Schreib-Wirkung** in der Buddy-API. Sie verzichtet bewusst
auf das EC-10-`propose→confirm`-Gate (E-FSE-1), weil das **auslösende
Ereignis selbst die ausdrückliche Handlung** ist (z. B. ein kommentarlos in
die Familien-Gruppe gesendetes Foto ist die Ansage „auf den Bilderrahmen").

**Pflicht:** Die Aufgabe liefert eine kurze **Quittung mit Undo-Möglichkeit**
— einen eigenständig erreichbaren Inverse-Aufruf an der Buddy-API
(z. B. `DELETE` zur vorher angelegten Ressource). Das Undo ist das
Sicherheitsnetz statt der Vorab-Bestätigung; ohne erreichbares Undo darf eine
Aufgabe **nicht** als Sofort-Schreib-Aufgabe gebaut werden, sondern bleibt
TASK-4 (`WriteTask` mit Confirm-Gate).

**Geeignet** für niedrigschwellige One-Shot-Eingaben, deren Auslöser selbst
die ausdrückliche Handlung ist (FSE-1: „Foto in Familien-Gruppe →
Bilderrahmen"). **Nicht geeignet** für mehrstufige Klärungen
(Privatchat-Session, Sammel-Dialoge, mehrere Eingabe-Werte) — die brauchen
das Confirm-Gate (TASK-4) bzw. die Privatchat-Session-Form (TASK-5).

Heimat des Patterns: `eltern-chat/skills/foto_senden_task.py` erbt von
`ReadTask`, `execute()` ruft die trigger-agnostische Funktion direkt; die
`description` der Aufgabe erklärt dem LLM das Undo-Modell (D6/FSE-4 — der
Widerruf ist ein **zweiter** `tool_use` mit der `id` aus der ersten Quittung,
kein neuer State).

**Verweis-Klausel (EC-10 A2-Klausel).** Skills, die unter die EC-10
A2-Klausel fallen (Sofort-Write + Quittung + Undo-Wort als Default —
heute `termin_eintragen`, `einkauf_hinzufuegen`, `foto_senden`),
**verschärfen** TASK-9 auf die enge Form: One-Shot-Ressource mit
**stabiler ID**, **idempotentes `DELETE`** als Inverse, **Pre-Flight-
Check** des Inverse-Aufrufs **vor erstem Live-Einsatz** (Test legt
an, ruft Inverse, prüft Bestätigung — siehe EC-10 A2-Klausel
Bedingung 3). TASK-9 ist die **Obermenge** (jede Sofort-Schreib-
Aufgabe braucht einen erreichbaren Inverse-Aufruf); EC-10 A2 ist die
**engere Form** für den Eltern-Chat-Default. Eine A2-Aufgabe darf
nicht im Sofort-Write-Default laufen, bevor der Pre-Flight-Check
grün ist.

*Tickets:* #TBD-A2-Pre-Flight (Pre-Flight-Tests für die drei
A2-Skills).

### TASK-10 — Lesende Aufgabe ist sprachlos im Agent-Loop
Eine Katalog-Aufgabe, die im Agent-Loop des Eltern-Chats läuft, **sendet
in dieser Aufruf-Phase nicht selbst** über den Telegram-Kanal. Das gilt für
`ReadTask.run()` (TASK-3), für die `propose()`-Hälfte einer `WriteTask`
(TASK-4) und für jede trigger-agnostische Funktion, die von dort aus
gerufen wird — sie returnen einen User-tauglichen Antwort-Text als
Tool-Result-String, das Senden übernimmt das Framework via LLM (Heimat:
`specs/platform/eltern-chat.md` EC-29).

**Marker ist die Aufruf-Phase, nicht `is_async`.** Maßgeblich ist, ob der
Code-Frame unter `task.run()` bzw. `task.propose()` im Agent-Loop liegt.
`is_async` (TASK-5) entscheidet, **wann** die Post-Execute-Hooks einer
schreibenden Aufgabe feuern — nicht, wer im selben Turn sprechen darf. Eine
synchrone schreibende Aufgabe, deren `execute()` **nach** dem
Bestätigungs-Gate (EC-10) läuft, ist außerhalb des Agent-Tool-Frames und
sendet weiterhin selbst (TES-Bestätigungs-Quittung,
RoutineZeitenSetzen-Confirm-Pfad und Vergleichbares).

**Datei-Anhänge: Skill sendet die Datei, LLM postet den Text.** Liefert
eine Aufgabe ein Nicht-Text-Artefakt (Datei via `tg.send_document`, Bild
via `tg.send_photo`), darf der Skill diesen Anhang technisch direkt senden
— das LLM hat keinen Datei-Sende-Vertrag. Der **gesamte Text-Teil**
(Caption, Anleitung, Begleittext) gehört in den Tool-Result; das LLM
postet ihn als seine Bot-Nachricht. Heutiger Konsument: `ca-verteilung.md`
(CAV-4) — Zertifikatsdatei vom Skill, hart-codierte OS-Anleitung vom LLM
aus dem Tool-Result.

**Wortwörtlich-Disziplin für Trust-kritische Texte.** Enthält der
Tool-Result einen Text, der wortwörtlich an die Familie gehen muss
(Sicherheits-Eigenschaft, nicht Stil — heute CAV-5 OS-Installations-
Anleitung), trägt die Aufgaben-`description` eine Klausel an das LLM:
„Diesen Text wortwörtlich übernehmen, nicht umformulieren oder kürzen;
kurze Einleitungs-/Schluss-Bemerkungen sind erlaubt." Das hält die
Sicherheits-Eigenschaft bei voller LLM-Stimme. Ohne Wortwörtlich-Disziplin
darf eine Aufgabe Tool-Result-Texte nicht als trust-kritisch deklarieren.

**Helper-Grenzen.** Ein Body-Lint, der nur auf `tg.send_*`-Aufrufe **im
`run()`/`propose()`-Body** prüft, **reicht nicht**: die heutige Wuensche-
Zeigen-Linie ruft den Send über einen Helper (`wuensche_zeigen.py`-
Funktion), und dieselbe Falle besteht für jede `_task.py`-Trigger-Datei.
Die Absicherung muss über die Aufruf-Grenze hinaus greifen — entweder per
Aufruf-Graph-Analyse vom `run()`/`propose()`-Frame aus, oder per
verbindlichem Routing-Test, der für jede neue Read- bzw. Propose-Aufgabe
**positiv** belegt, dass im Agent-Loop kein Telegram-Send erfolgt. Die
konkrete Lint-/Test-Implementierung ist nicht Bestandteil dieser Konvention
— sie wandert mit der Migration in PR-1 (`wuensche_zeigen`) ein und wird
dort als Baseline für alle Folge-Migrationen festgehalten.

**Berechtigungs-Bruch im Agent-Loop.** Stellt eine Katalog-Aufgabe fest,
dass der Aufrufer kein Familien-Mitglied ist (EC-2, EC-29), wirft sie eine
`BerechtigungError` aus dem geteilten Modul `eltern-chat/skills/_errors.py`
— nicht aus einer eigenen Klasse pro Skill. Der Agent-Loop fängt die
Exception als `is_error=True`-Tool-Result-Block; das LLM formuliert daraus
eine ehrliche Antwort. Eine geteilte Klasse statt mehrerer lokaler vermeidet
Code-Duplikation (CLAUDE.md §6) und hält das Pattern für Folge-Migrationen
klar verankert.

*Tickets:* #551, #564

### TASK-10b — ID-Wahl-Album per ICONS-7-Helper

Eine Katalog-Aufgabe, die dem Elternteil **mehrere ICONS-7-Treffer zur Wahl
per ID** vorlegt (heutige Konsumenten: RPS — Routine-Punkt-Piktogramm, GAN —
Gericht-Piktogramm, PAS — Aktivitäts-Piktogramm), benutzt den geteilten Helper
`eltern-chat/skills/icon_album.py` mit der Signatur

    zeige_kandidaten(tg, chat_id, kandidaten: List[{id, url}], icon_origin_url) -> None

— statt eigenen Multipart-/Album-Code. Der Helper ist die einzige Heimat des
Telegram-Album-Sendepfades für ID-Wahl-Bilder; ein Skill, der ein zweites Mal
`sendMediaGroup` oder `send_photo` für ID-Kandidaten direkt aufruft, ist
Spec-Verletzung (CLAUDE.md §6 „dieselbe Logik zweimal zu schreiben ist
verboten").

**Trefferzahl-Fallback (verbindlich, im Helper, nicht im Skill).** Der Helper
verzweigt anhand der Listen-Länge: 1 Treffer → `tg.send_photo`; 2–3 Treffer →
`tg.send_media_group` (Telegram-API erlaubt erst ab 2 Items ein Album); 0
Treffer → **no-op** (`zeige_kandidaten` macht nichts). Der Skill fängt
**vorher** ab: liefert ICONS-7 keine Treffer, meldet der Skill das selbst
ehrlich (EC-7, vgl. RPS-4 / GAN-4) und ruft den Helper gar nicht. Der no-op-
Zweig ist Sicherheitsnetz, kein normaler Pfad.

**Caption-Klausel: Helper setzt keine Captions.** Das Album bzw. das Einzel-
Foto trägt **keine** Caption an den Bildern. Die Mapping-Information
(„welche Album-Position ist welche ARASAAC-ID") liefert der Skill als Teil
seines Tool-Result-Strings an das LLM in Form

> *„1 = `<id_1>`, 2 = `<id_2>`, 3 = `<id_3>`. Welcher passt? Antworte mit der ID."*

(bzw. der zur jeweiligen Trefferzahl passenden, gekürzten Liste). Das LLM
postet diesen Text als Begleit-Nachricht im selben Turn — das ist genau der
EC-29-Vertrag aus dem Eltern-Chat (eine Stimme: Skill sendet den Anhang, LLM
sendet den Text). EC-29 bleibt von TASK-10b unberührt; die Sub-ID nennt nur
explizit, dass der Skill **keine** Captions ans Album hängt — die
Bilder-und-Text-Trennung des Datei-Anhang-Patterns (TASK-10, „Datei-Anhänge:
Skill sendet die Datei, LLM postet den Text") gilt hier wörtlich.

**URL-Konsum aus ICONS-7.** Die Such-API liefert je Kandidat einen
`{id, url}`-Datensatz (`specs/platform/icons.md` ICONS-7,
`specs/platform/icons.md:131-146`). Der Helper holt das PNG ausschließlich
über `<icon_origin_url> + <url>` per HTTP — er kennt **kein**
ARASAAC-Pfadschema, baut **keinen** Pfad selbst aus der `id`. Damit bleibt
die Konvention austauschbar gegen einen ICONS-Nachfolger, der die URL-Form
ändert; der Skill und der Helper folgen ICONS-7, nicht der Datei-Struktur
(DCOMP-1: keine Pfad-Kopplung zwischen Services). Der Aufrufer (Skill)
muss die `icon_origin_url` als expliziten Parameter mitgeben (Tasks erhalten
sie heute über die `build_catalog`-Injektion, nicht über den IconClient).

**Reihenfolge-/Identitäts-Klausel.** Der Helper sendet die Bilder in genau
der vom Aufrufer übergebenen Reihenfolge der `kandidaten`-Liste und filtert
keine Einträge — der Mapping-Text, den der Skill an das LLM zurückgibt,
bleibt damit verbindlich. Position 1 im Album entspricht `kandidaten[0]`,
Position 2 entspricht `kandidaten[1]`, usw.; eine Position-zu-`id`-
Rückbildung im Skill ist deterministisch sicher.

**Geltungsbereich.** TASK-10b ist die Bauregel für **alle** ID-Wahl-Skills,
die ICONS-7 konsumieren — gebaute Konsumenten heute: RPS-4
(`specs/platform/routine-punkte-setzen.md`), GAN-4
(`specs/platform/gericht-anlegen.md`); spec-aligned und noch nicht gebaut:
PAS-4 (`specs/platform/plan-aktivitaeten-setzen.md`). Spätere Konsumenten
docken an, ohne TASK-10b zu erweitern; der Helper bleibt die eine Heimat.
Die Konvention entsteht jetzt mit zwei *gebauten* + einem spec-aligned
Konsumenten — kein Vorratsbau (CLAUDE.md §6 „Lege nichts auf Vorrat an").

*Tickets:* #470 (Welle 11 — Bilder-Lego, Berater-Runde 2026-06-10
ratifiziert)

### TASK-10c — Strukturiertes Präsentations-Ergebnis (drei zulässige Formen)

Eine Katalog-Aufgabe gibt an das Framework eine von **drei zulässigen
Formen** zurück. Das Framework — nicht der Skill — übersetzt die Form
beim finalen Versand in **eine** Bot-Nachricht (EC-29 „Eine Stimme im
Agent-Turn"). Andere Formen sind verboten.

**Form (a) — reiner String.** Der bisherige Default (EC-29): die
Aufgabe returnt einen User-tauglichen Antwort-Text als
Tool-Result-String; das LLM formuliert daraus die Bot-Nachricht und
postet sie. Heutige Konsumenten: alle Read-Skills ohne Anhang oder
Button.

**Form (b) — `{text, presentation}`-Objekt.** Die Aufgabe returnt
einen Text-Teil **plus maschinenlesbare Präsentations-Hinweise**
(`presentation`). Das Framework übersetzt `presentation` beim finalen
Versand in **eine** Bot-Nachricht, in der Text und der von
`presentation` beschriebene Aufsatz (z. B. `webapp_link`,
`inline_button`) gemeinsam erscheinen. Der Skill sendet **nichts**
selbst.

Diese Form ist der Pfad für strukturierten Button- und WebApp-
Aufsatz: der Skill bleibt sprachlos (EC-29), liefert aber dem
Framework die maschinenlesbare Information, was es an die LLM-
Bot-Nachricht anhängen soll. Das Vokabular der `presentation`-
Hinweise (welche Schlüssel zulässig sind, welche Felder sie tragen)
wird im **Framework-Code** geführt und in einem separaten
Code-Track erweitert — nicht in dieser Konvention.

**Form (c) — Datei-Anhang + Caption-String.** Liefert die Aufgabe
ein Nicht-Text-Artefakt (Datei, Bild), sendet der Skill den Anhang
**direkt** (`tg.send_document`, `tg.send_photo`) und returnt den
Text-Teil (Caption, Anleitung, Begleittext) als Tool-Result-String;
das LLM formuliert daraus die Bot-Nachricht. Das ist die in TASK-10
geregelte Datei-Anhang-Klausel — hier nur als **Querverweis**, damit
die drei zulässigen Formen vollständig nebeneinanderstehen. Heutiger
Konsument: `ca-verteilung.md` CAV-4.

**Verboten:**

1. **`(text, buttons)`-Tuple-Return** als Eigen-Form (ohne
   `presentation`-Schlüssel).
2. **Skill-direktes Senden von Text + Button** in derselben
   Tool-Use-Phase — das ist ein zweiter Sprecher und verletzt EC-29
   („Eine Stimme im Agent-Turn"). Der heutige `einkauf_zeigen`-Pfad
   (`einkauf_zeigen.py:101` — Tuple-Return; `einkauf_zeigen_task.py`
   — Selbst-Send) ist die dokumentierte EC-29-Ausnahme und
   **migriert auf Form (b)**.

**Was sich für die Familie ändert.** Heute schickt `einkauf_zeigen`
zwei sichtbar getrennte Bot-Akte — die Übersicht (Skill-Stimme) und
gleich darauf eine LLM-Nachricht. Mit Form (b) entsteht **eine**
Nachricht: Text und WebApp-Button stehen zusammen, formuliert in
einer Stimme. Kein Doppelversand, keine sichtbare Naht zwischen
Skill und LLM.

**Begründung — Trade-off.** Form (a) als einziger Default ließe
keinen sauberen Pfad für Aufsätze (Button, WebApp-Link); ein Skill,
der einen Button setzen will, müsste selbst senden — und damit die
EC-29-Eine-Stimme-Linie verletzen. Form (b) lagert die
Aufsatz-Mechanik ins Framework aus, sodass der Skill weiterhin
sprachlos bleibt. Form (c) bleibt für echte Datei-Anhänge bestehen,
weil das LLM keinen Datei-Sende-Vertrag hat.

*Tickets:* #TBD-A3 (Framework-`presentation`-Übersetzung in
`run_turn`, Migration von `einkauf_zeigen` auf Form (b))

### TASK-10d — Standard-Quittungen Klasse C über geteilten Helper

Eine **Klasse-C-Katalog-Aufgabe** (kanonisch `propose → confirm`,
`conventions/eltern-chat-skills.md` Klasse C) führt **wiederkehrende
Quittungs-Texte** — Ablehnung mangels Mitgliedschaft, Buddy-API
nicht erreichbar, Buddy-API-Grenze abgelehnt, Piktogramm-Suche
ergibt keinen Treffer — **nicht** als skill-lokale Konstanten,
sondern über den **geteilten Helper** `eltern-chat/skills/_quittungen.py`.

```python
def abgelehnt(skill_verb: str) -> str: ...
def nicht_erreichbar(buddy_name: str) -> str: ...
def grenze(buddy_name: str, aktion: str, detail: str) -> str: ...
KEINE_ICONS = "Ich habe für »{label}« kein Piktogramm gefunden …"
```

`_quittungen.py` ist die einzige Heimat dieser vier Standard-
Quittungs-Texte; ein Skill, der ein zweites Mal eine `_QUITTUNG_ABGELEHNT`-,
`_QUITTUNG_NICHT_ERREICHBAR`-, `_QUITTUNG_GRENZE`- oder
`_QUITTUNG_KEINE_ICONS`-Konstante anlegt, ist Spec-Verletzung
(CLAUDE.md §6 „dieselbe Logik zweimal zu schreiben ist verboten").

**Pflicht-Klausel.** Wer einen Klasse-C-Skill baut oder anfasst,
nutzt die Helper für die vier Standard-Quittungen. Custom-Quittungen
nur dort, wo der Helper das Verhalten **nicht trägt** (skill-eigene
Erfolgs-Quittungen wie `_QUITTUNG_HINZUGEFUEGT`/`_ANGELEGT`/`_GELOESCHT`
und skill-eigene `_QUITTUNG_NICHTS_ZU_TUN_*`-Varianten bleiben
skill-lokal — sie tragen Skill-eigene Semantik). Driftet ein
Standard-Wortlaut im Helper nicht für einen Skill, wird der **Helper
erweitert**, nicht parallel templated.

**Heutige Konsumenten:** `routine_punkte_setzen`, `gericht_anlegen`,
`plan_aktivitaeten_setzen` — drei *gebaute* Klasse-C-Skills mit
nachgewiesener Drift (`_QUITTUNG_KEINE_ICONS` byte-identisch in
allen drei Modulen, `_QUITTUNG_NICHT_ERREICHBAR`/`_GRENZE`/
`_ABGELEHNT` schablonen-identisch mit driftendem Buddy-Namen oder
Aktions-Verb). Die Konvention entsteht jetzt mit drei *gebauten*
Konsumenten — kein Vorratsbau (CLAUDE.md §6 „Lege nichts auf
Vorrat an"), Trigger ist konkreter Schmerz, nicht Antizipation
(`decisions/RAT-7-297-skill-convention-defer.md` — RAT-7 nennt
explizit „3+ Skills, die in Tonfall/Quittungs-Format messbar
voneinander driften" als Re-Opening-Trigger).

**Abgrenzung zu A2-Klasse-D.** Die A2-Klausel (EC-10, drei A2-Skills
`termin_eintragen`, `einkauf_hinzufuegen`, `foto_senden`) trägt eine
**eigene** Quittungs-Pflicht (Undo-Wort `falsch` explizit nennen,
Schlüssel-Werte prominent zuerst — `specs/platform/eltern-chat.md`
EC-10 A2-Klausel). Diese A2-Quittungen sind **nicht** Konsumenten
von `_quittungen.py` heute. Wenn n=2 dort eine gleichartige Drift
zeigt, kann der Helper später A2-Mitnutzer aufnehmen — heute kein
Schmerz, keine Vorrats-Erweiterung.

**Geltungsbereich.** TASK-10d ist die Bauregel für **alle** Klasse-C-
Skills mit den vier Standard-Quittungen. Heutige Konsumenten siehe
oben; spätere Konsumenten docken an, ohne TASK-10d zu erweitern;
der Helper bleibt die eine Heimat. Pattern analog TASK-10b/10c —
gleiche Sub-ID-Form, gleicher Helper-Modul-Ort
(`eltern-chat/skills/<helper>.py`), gleiche n=3-Mechanik.

*Tickets:* #817 (TASK-10d Spec + RPS/GAN/PAS Migration —
n=3-Trigger aus RAT-7, Welle-3 Eltern-Chat-Vereinheitlichung
2026-06-15)

### TASK-11 — Optionale `anzeige_copy`: eltern-taugliche Anzeige-Copy einer Aufgabe

Eine Katalog-Aufgabe **darf** ein optionales Klassenattribut
`anzeige_copy` (`str`) deklarieren — analog `is_async`, `auto_confirm`,
`post_execute_hooks` (`tasks.py`) — mit einer kurzen, eltern-tauglichen
Ein-Satz-Beschreibung der Fähigkeit. Default: nicht gesetzt. Das Attribut
gehört auf die `Task`-Basis, damit auch lesende Aufgaben (`ReadTask`) es
tragen können.

**Bedeutung — eine Heimat.** Was das Feld ist (Anzeige-only, kein Trigger,
keine Berechtigungs-/Sichtbarkeits-Semantik, Fallback auf `description`,
heutige Leser), regelt `specs/platform/eltern-chat.md` EC-42. Diese
Konvention nennt **nur** den Deklarations-Ort — sie wiederholt die Bedeutung
nicht, um zwei gepflegte Heimaten desselben zu vermeiden.

**Wann setzen.** Wer eine Aufgabe baut, deren Fähigkeit in der Selbstauskunft
(`faehigkeiten_zeigen`, EC-43) oder im Onboarding-Teaser (#1104) sauber
klingen soll, setzt `anzeige_copy`; sonst greift der `description`-Fallback
(Router-Jargon, für Eltern ungeeignet).

**Kein Vorrat.** Zwei Leser (faehigkeiten_zeigen, Onboarding) rechtfertigen
das Feld heute. Eine committete Manifest-Registry, ein Drift-Test oder eine
Capability-Karten-Generierung sind **nicht** Teil dieser Regel
(capability-cluster-ENTSCHEID Landung 3, NOCH NICHT).

*Tickets:* #1102, #1104

---

**Hinweis (historisch, jetzt GEBAUT):** Das Privatchat-Session-Routing in
`handle_update` wurde mit SESS-5/#264 (PR #264 — Eltern-Chat Session-Registry)
zu einem gemeinsamen Session-Router umgebaut: `_SESSION_SORTS` (`main.py`)
registriert alle Session-Sorten (FAA/GAA/KAV/TES/PAA), `handle_update`
iteriert generisch darüber — keine vier namentlichen Blöcke mehr. Eine neue
async-Aufgabe fügt nur noch einen `SessionSortEntry` in `_build_session_sorts`
hinzu (Lego-Prinzip erfüllt). Die oben beschriebene Lego-Falle (falsche oder
fehlende Session-Map) besteht weiterhin; der Routing-Test bleibt Pflicht
(TASK-7, letzter Absatz).
