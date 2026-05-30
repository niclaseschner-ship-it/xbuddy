# Plan-Buddy — Spec     (ID-Präfix: PLAN)

> Status: V1 · Refs #40

Der Plan-Buddy ist eine eigenständige XBuddy-**App**. Er zeigt einer Familie
ihren Wochenplan auf einem Display in der Wohnung — wer welches Kind bringt und
holt, wer kocht und ins Bett bringt, was die Kinder vorhaben, welche Termine
anstehen. Ein Kind sieht hier selbst nach, statt zu fragen. Als App **besitzt**
der Plan-Buddy seine Daten (die Petrantwortlichkeiten) und seine Funktion (die
Kalender-Anbindung) und stellt beides über Schnittstellen bereit; andere
XBuddy-Apps sind seine Nutzer (E-PLAN-1).

**V1-Scope:** Die View `woche` in zwei Mitwachsen-Stufen · eine Schedule-Rail
aus konfigurierbaren Slots · per Tippen zugewiesene, lokal gespeicherte
Petrantwortlichkeiten · Kind-Aktivitäten und Termine aus dem Familien-Kalender ·
die Anbindung an diesen Google-Kalender (lesen/schreiben) als App-eigene
Fähigkeit · eine Termin-Schnittstelle, die andere XBuddy-Apps nutzen können.
Das Layout wird **1:1** aus dem Wireframe-Handoff übernommen (E-PLAN-5).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): eine Eltern-Ansicht
mit Namen und freiem Editieren · ein Personen-Picker statt des Klick-Cycles
(PLAN-8) · eine Sperre/Auth vor dem Editieren am Display · Routine-Module
(Morgen-/Abendablauf) · weitere Views über `woche` hinaus · mehrere Aktivitäten
pro Kind pro Tag · mehrere Kalender je Familie (OPEN-PLAN-F) · ein geführtes
OAuth-Onboarding (geschlossen durch `kalender-verbinden.md`).

## 1. Die App & ihre Views

### PLAN-1 — Plan-Buddy ist eine App mit eigenem Besitz
Der Plan-Buddy ist die XBuddy-App mit dem Buddy-Slug `plan`. Er besitzt:
seine **Daten** — die Petrantwortlichkeiten (PLAN-9) —, seine **Funktion** — die
Anbindung an den Familien-Kalender (Abschnitt 6) — und stellt beides über
**Schnittstellen** bereit (Abschnitt 7). Was der Plan-Buddy nicht selbst
besitzt, holt er von zentralen Komponenten: Personen-Identität von der
Familien-Registry (`familie.md`), Geheimnisse vom Zugangsdaten-Speicher
(`zugangsdaten.md`). Eine Funktion des Plan-Buddys steht anderen Apps nur zur
Verfügung, wenn der Plan-Buddy installiert ist (PLAN-23, E-PLAN-1).

*Tickets:* #40

### PLAN-2 — View `woche`
Die Wochen-View liegt unter `/display/plan/woche` (URL-2:
`/display/<buddy>/<view>`, keine Verben im Pfad).

*Tickets:* #40

### PLAN-3 — Zwei Mitwachsen-Stufen als Varianten einer View
Die View `woche` gibt es in zwei adressatengerechten Stufen. Die Stufe ist ein
Query-Parameter, kein eigener Pfad (URL-2: Varianten als Query-Parameter):

- **Lese-Kind** (Default, ohne Parameter) — `/display/plan/woche` — für Kinder,
  die schon lesen (Richtwert 6–8 Jahre): rollierende 7-Tage-Ansicht inklusive
  Termin-Leiste.
- **Kleinkind** — `/display/plan/woche?ansicht=klein` — für nicht lesende
  Kinder (Richtwert 3 Jahre): 3 Tage, XL-Maße, runde Aktivitäts-Stempel statt
  beschrifteter Pillen, **ohne** Termin-Leiste.

Beide Stufen zeigen **dieselben Daten derselben Familie** — nur die
Aufbereitung unterscheidet sich. Das ist „Mitwachsen" der Constitution:
gleicher Inhalt, adressatengerecht übersetzt.

*Tickets:* #40

### PLAN-4 — Rollierendes Fenster ab heute
Die View zeigt ein Fenster aus aufeinanderfolgenden Tagen, das **mit dem
heutigen Tag beginnt** — Lese-Kind 7 Tage, Kleinkind 3 Tage (PLAN-28). Der
Anker ist über `?ab=<iso-datum>` verschiebbar (URL-8: Filter als
Query-Parameter); ohne Parameter ist der Anker heute. Das Fenster kann eine
Kalenderwoche überschreiten — PLAN-10 löst das.

*Tickets:* #40

## 2. Tagesraster

### PLAN-5 — Tages-Spalten
Jeder Tag des Fensters ist eine Spalte mit einem Day-Chip: Wochentag-Kürzel und
Datum. Der **heutige** Tag ist hervorgehoben — kräftigere Tagesfarbe, leichte
Rotation, Schatten. Tage tragen je Wochentag eine eigene Pastellfarbe; heute
und morgen tragen zusätzlich ein Über-Label („heute" / „morgen").

*Tickets:* #40

## 3. Schedule-Rail

### PLAN-6 — Slot-Zeilen, konfigurierbar
Die Schedule-Rail besteht aus Slot-Zeilen — je Zeile ein wiederkehrender
Tagesablauf-Punkt. Welche Slots eine Familie hat, ist **Konfiguration**, kein
fest verdrahteter Code (CLAUDE.md §6, E-PLAN-2). Jeder Slot definiert in der
Konfiguration: stabiler Schlüssel, Art (`erwachsenen-slot` | `aktivitäts-slot`),
Icon und — bei Aktivitäts-Slots — das zugehörige Kind. Die Beispiel-Konfiguration
bildet die sieben Slots des Wireframe-Handoffs 1:1 ab: `bring`, `pick`, `act1`
(Kind A), `act2` (Kind B), `cook`, `bed1` (Kind A), `bed2` (Kind B).

*Tickets:* #40

### PLAN-7 — Erwachsenen-Slots: Zuweisung per Klick-Cycle
Eine Zelle eines Erwachsenen-Slots zeigt entweder das Foto-im-Ring (FAM-4)
eines Erwachsenen oder einen leeren Slot mit Plus-Icon. Ein Tippen schaltet
zyklisch weiter: Erwachsener 1 → Erwachsener 2 → … → leer → Erwachsener 1. Nur
Erwachsene der Familien-Registry (`familie.md` FAM-2) sind im Cycle; die
Reihenfolge ist die der Registry.

*Tickets:* #40

### PLAN-8 — Petrantwortlichkeiten lokal speichern
Jede Zuweisung aus PLAN-7 wird **lokal** gespeichert (PLAN-9) — nicht im
Kalender. Eine Zuweisung gilt für einen Slot an einem Wochentag einer Woche;
eine spätere Anfrage derselben Woche zeigt dieselbe Zuweisung.

*Tickets:* #40

### PLAN-9 — Datenhaltung der Petrantwortlichkeiten
Die Petrantwortlichkeiten liegen in einer SQLite-Datei neben dem Code, je
Instanz separat, per `.gitignore` ausgeschlossen (analog `eltern-chat.md`
EC-16). Fehlt die Datei beim Start, legt das System sie leer an. Die Datei hält
**nur** die Zuweisungen je Woche — Personen kommen aus der Registry, Aktivitäten
und Termine aus dem Kalender; keine doppelte Wahrheit. Dies ist die App-eigene
Datenhaltung aus PLAN-1.

*Tickets:* #40

### PLAN-10 — Default-Petrantwortlichkeiten & wochenübergreifendes Fenster
Die Familie hinterlegt in der Konfiguration Standard-Zuweisungen je Slot und
Wochentag. Wird eine Woche zum ersten Mal angezeigt, werden ihre Slots aus
diesen Defaults vorbelegt; danach ist jede Woche unabhängig editierbar (PLAN-7).
Weil das Fenster ab heute rollt (PLAN-4), überspannt es regelmäßig zwei
Kalenderwochen — die View liest und vorbelegt **alle** berührten Wochen und
ordnet jede Spalte ihrer Woche zu.

*Tickets:* #40

## 4. Aktivitäts-Slots der Kinder

### PLAN-11 — Aktivitäts-Slots liegen im Kalender
Ein Aktivitäts-Slot zeigt, was ein Kind an einem Tag vorhat. Diese Aktivitäten
liegen **nicht** lokal, sondern im Familien-Kalender (Abschnitt 6). Ein Tippen
auf eine Aktivitäts-Zelle öffnet einen Picker mit Standard-Aktivitäten und der
Option „Event löschen". Eine Auswahl legt über die Kalender-Anbindung (PLAN-18)
einen ganztägigen Termin an bzw. ändert oder löscht ihn — Titel nach der
Konvention `<Aktivität> <Kindname>` (PLAN-19). Wer eine Aktivität ändert — am
Display oder direkt im Google-Kalender — ist gleichwertig; die View spiegelt
beim nächsten Aufruf den Kalender-Stand.

*Tickets:* #40

### PLAN-12 — Aktivität einem Kind zuordnen
Ein Kalender-Event wird genau dann als Kind-Aktivität in einen Aktivitäts-Slot
einsortiert, wenn sein Titel den Namen eines Kindes der Registry trägt (PLAN-19).
Die Art der Aktivität (Icon/Label) folgt aus einem Schlüsselwort im Titel.
Trägt ein Event keinen Kindernamen, ist es kein Aktivitäts-Slot-Inhalt, sondern
ein Termin (PLAN-13).

*Tickets:* #40

## 5. Termin-Leiste

### PLAN-13 — Einzel-Termine
Unter der Schedule-Rail zeigt die Lese-Kind-Stufe (PLAN-3) eine Termin-Leiste:
je Tagesspalte die Termine dieses Tages aus dem Familien-Kalender, die keine
Kind-Aktivität sind (PLAN-12). Ein Termin zeigt — falls vorhanden — Uhrzeit,
Titel und das Foto-im-Ring der zugeordneten Person (PLAN-19 → `familie.md`
FAM-4). Sind keine Credentials da oder ist der Kalender nicht erreichbar
(PLAN-20), bleibt die Leiste leer; die übrige View funktioniert weiter. Die
Kleinkind-Stufe hat keine Termin-Leiste (PLAN-3).

*Tickets:* #40

### PLAN-14 — Mehrtages-Termine als Spanne
Ein Termin über mehrere Tage des Fensters wird **einmal** als durchgehender
Balken über die betroffenen Spalten gezeigt, nicht je Tag wiederholt. Die
Zusammengehörigkeit wird über die stabile Event-`id` (PLAN-17) erkannt — für
ganztägige wie für zeitgebundene mehrtägige Events.

*Tickets:* #40

## 6. Kalender-Anbindung (App-eigene Funktion)

> Die Anbindung an den Google-Familien-Kalender ist eine Funktion **dieser
> App** — keine eigenständige Plattform-Fähigkeit (E-PLAN-6). Andere Apps
> erreichen den Kalender nur über die Schnittstelle aus Abschnitt 7.

### PLAN-15 — Ein Familien-Kalender
Die App ist auf genau einen Google-Kalender konfiguriert — den gemeinsamen
Familien-Kalender (PLAN-28). Alle Lese- und Schreibvorgänge beziehen sich auf
diesen einen Kalender.

*Tickets:* #40

### PLAN-16 — OAuth-Zugang über den Zugangsdaten-Speicher
Der Zugang läuft über OAuth 2.0 (OAuth-Client + Refresh-Token; aus dem
Refresh-Token wird bei Bedarf ein Access-Token geholt). Client und Token liegen
im zentralen Zugangsdaten-Speicher (`zugangsdaten.md`), **nicht** in einer
eigenen Datei der App und nie im Repo (CLAUDE.md §8). Der OAuth-Client muss in
der Google Cloud Console auf **Production** veröffentlicht sein (E-PLAN-7).

*Tickets:* #40

### PLAN-17 — Events eines Zeitraums lesen, normalisiertes Modell
Für einen Start-Tag und eine Tagesanzahl liefert die Anbindung die Termine des
Kalenders, wiederkehrende Termine in Einzel-Vorkommen aufgelöst. Jedes Event
wird in ein anbieter-neutrales Modell übersetzt — mindestens: stabile `id`
(trägt die Multi-Day-Gruppierung, PLAN-14), Titel, Beginn, Ende, Ganztags-Flag,
aufgelöste Person (PLAN-19). Google-Rohfelder, die V1 nicht braucht, werden
nicht durchgereicht (CLAUDE.md §6).

*Tickets:* #40

### PLAN-18 — Events anlegen, ändern, löschen
Die Anbindung kann im konfigurierten Kalender ein Event anlegen, über seine
`id` ändern und über seine `id` löschen. Sie entscheidet nicht, *ob*
geschrieben wird — das tut der aufrufende Teil (PLAN-11 oder die Schnittstelle
aus PLAN-22).

*Tickets:* #40

### PLAN-19 — Titel-Konvention & Personen-Auflösung
Ein Event, das eine Person betrifft, trägt deren **Namen im Titel** — Form
`<Titel> <Name>` (z. B. „Klettern Finn", „Shibari Jonas"). Die Anbindung ordnet
jedes Event höchstens einer Person der Familien-Registry zu, in dieser
Reihenfolge: (1) **Titel-Treffer** — kommt ein Personenname (FAM-3) im Titel
vor, ist das die Person; bei mehreren gewinnt der früheste; (2) **Creator-E-Mail**
— sonst, ist die Creator-Adresse die E-Mail eines Erwachsenen, ist das die
Person; (3) sonst keine Zuordnung. Diese Konvention ist die tragende
Entscheidung der Anbindung — Personen-Zuordnung und das Aktivitäts-Routing
(PLAN-12) fallen aus ihr heraus.

*Tickets:* #40

### PLAN-20 — Kalender nicht erreichbar oder ohne Credentials
Fehlen die OAuth-Daten oder ist Google nicht erreichbar, wirft die App keinen
unbehandelten Fehler: eine Lese-Anfrage liefert ein leeres Ergebnis, eine
Schreib-Anfrage einen klar erkennbaren Misserfolg — beides protokolliert. Die
Display-View bleibt funktionsfähig (PLAN-13): ein Display ohne Kalender zeigt
eben keine Termine.

*Tickets:* #40

## 7. Exponierte Schnittstellen

### PLAN-21 — Display-Views für die Familie
Die Stufen der View `woche` (PLAN-3) sind die Schnittstelle zur Familie — über
`/display/plan/woche` an einem Display abrufbar.

*Tickets:* #40

### PLAN-22 — Termin-Schnittstelle für andere XBuddy-Apps
Der Plan-Buddy stellt den Familien-Kalender anderen XBuddy-Apps über eine
HTTP-Schnittstelle unter `/api/v1/plan/` bereit (URL-4) — Termine eines
Zeitraums lesen und Termine anlegen/ändern. Andere Apps rufen den Google-Kalender
**nicht direkt** auf, sondern nur über diese Schnittstelle (einseitige
Abhängigkeit, CLAUDE.md §6). So kann etwa der Eltern-Chat Termine verwalten,
ohne selbst eine Kalender-Anbindung zu haben.

**GET-Vertrag** — `GET /api/v1/plan/termine`:

Query-Parameter: `ab=<ISO-Datum>` (Start-Tag; Default: heute), `tage=<n>`
(Anzahl Tage; Default: `7`). Antwort: JSON-Array der normalisierten Events
im Zeitraum — je Event mindestens `id`, `titel`, `beginn`, `ende`,
`ganztags`, `person_id` (oder `null`). Events werden nach PLAN-17 in ein
anbieter-neutrales Modell übersetzt. Ungültige `ab`- oder `tage`-Werte
antworten HTTP 400 mit JSON-Fehler. Fehlen Credentials oder ist Google
nicht erreichbar, liefert die Schnittstelle ein leeres Array (PLAN-20).
Reload-on-Read: Config und Transport werden pro Aufruf frisch geladen
(DCOMP-2), sodass ein KAV-Schreibvorgang ohne Service-Restart sichtbar
wird.

**PUT-Vertrag** — `PUT /api/v1/plan/termine`:

Body: `{ "titel": "<string>", "datum": "<ISO-Datum>" [, "event_id": "<id>"] }`.
`titel` ist Pflicht (nicht leer). Ohne `event_id`: neuer ganztägiger Termin
unter `titel` an `datum` — antwortet `{ "ok": true, "action": "created",
"event_id": "<id>" }`. Mit `event_id`: bestehenden Termin umbenennen —
antwortet `{ "ok": true, "action": "patched", "event_id": "<id>" }`.
Kalender nicht erreichbar: HTTP 502. Ungültige Eingabe: HTTP 400.

*Tickets:* #40

### PLAN-30 — Lese-API für Wochenzuteilungen
Der Plan-Buddy stellt die persistierten Erwachsenen-Slot-Zuteilungen einer
Woche unter `GET /api/v1/plan/zuteilung?week_start=<YYYY-MM-DD>` bereit —
Form analog FAM-7 (GET, Query-Parameter, JSON-Antwort). Antwort:
`{ "week_start": "<YYYY-MM-DD>", "slots": [ { "day": 0..6, "slot": "<key>",
"person_id": "<id>|null" }, … ] }`. Die Liste enthält je Wochentag je
Erwachsenen-Slot eine Zeile; leere Stellen tragen `person_id: null`. Ein
ungültiges oder fehlendes `week_start` antwortet HTTP 400 mit JSON-Fehler,
kein 500.

Die Lese-API folgt der DCOMP-2-Linie (Reload-on-Read): plan.json und
plan.db werden pro Aufruf frisch gelesen (`_current_config()`, `_db()`).
Auf dem Erst-Lesepfad wird die Woche wie in der View aus den
Default-Petrantwortlichkeiten (PLAN-10) vorbelegt — damit liefert die
Lese-API denselben Stand wie eine View-Anfrage.

Damit haben andere XBuddy-Apps (z. B. ein zukünftiges Eltern-Chat-Skill,
das Wochen-Petrantwortlichkeiten anzeigt) einen stabilen Lese-Vertrag —
ohne direkten Zugriff auf `plan.db` (APP-3, einseitige Abhängigkeit).

*Tickets:* #214

### PLAN-31 — Schreib-API für Erwachsenen-Slot-Zuteilungen
Der Plan-Buddy nimmt Zuteilungen von anderen XBuddy-Apps über
`PUT /api/v1/plan/zuteilung` entgegen — analog PLAN-30 (Lese-Seite).
Body: `{ "week_start": "<YYYY-MM-DD>", "day": 0..6, "slot": "<key>",
"person_id": "<id>"|null }`. Alle vier Felder sind Pflicht (außer
`person_id`, das `null` sein darf, um einen Slot zu leeren). Wirkung:
schreibt die Zuweisung atomar in `plan.db` (PLAN-9) — identisch mit dem
Klick-Cycle im View (PLAN-7/PLAN-8). Antwort: `{ "ok": true }`.

Fehler-Semantik: `400` mit JSON-Fehler bei fehlendem Pflichtfeld, `slot`
nicht vorhanden oder kein Erwachsenen-Slot (PLAN-6), `person_id` unbekannt
(FAM-3), ungültigem `day`. Reload-on-Read gilt auch hier: Slot-Definition
und Registry werden pro Aufruf frisch gelesen (DCOMP-2).

*Tickets:* #214

### PLAN-23 — Eine App-Fähigkeit gibt es nur, wenn die App installiert ist
Die Termin-Schnittstelle (PLAN-22) existiert genau dann, wenn der Plan-Buddy
auf dem Hub installiert ist und läuft. Ist er es nicht, ist die Schnittstelle
nicht erreichbar — eine konsumierende App erkennt das und bietet die zugehörige
Fähigkeit dann **nicht** an, statt zu scheitern. Es gibt keinen halben Zustand:
entweder die App ist da und die Fähigkeit steht, oder beides fehlt. Das ist die
allgemeine Logik für XBuddy-Apps (E-PLAN-1).

*Tickets:* #40

## 8. Gestaltung & Bedienung

### PLAN-24 — Identität nur über Foto im Ring
In allen Stufen wird eine Person ausschließlich über ihr Foto im farbigen Ring
gezeigt (`familie.md` FAM-4) — keine Personennamen im Plan-Buddy-UI. Das ist
die Voraussetzung dafür, dass auch die Kleinkind-Stufe ohne Lesen funktioniert.

*Tickets:* #40

### PLAN-25 — Wenig Affordances, alles tippbar
Die Bedienung ist bewusst karg: leere Slots tragen ein Plus-Icon als einziges
Signal, es gibt keine Hover-Animationen, kein Glow. Jede Slot-Zelle ist tippbar.
V1 hat **keine** Sperre — jedes Kind am Display darf jeden Slot ändern
(Auth out-of-scope, OPEN-PLAN-D).

*Tickets:* #40

### PLAN-26 — Stufen-Maße
Lese-Kind: 7 Spalten, Termin-Leiste sichtbar. Kleinkind: 3 Spalten, XL-Maße,
Aktivitäts-Slots als runde Stempel ohne Label, keine Termin-Leiste. Die Maße
beider Stufen werden 1:1 aus dem Wireframe-Handoff übernommen (E-PLAN-5). Das
Layout zielt auf ein 1920×1080-Kiosk-Display; die Lese-Kind-Stufe passt ohne
Scrollen.

*Tickets:* #40

### PLAN-27 — Wireframe-Look
Der visuelle Stil ist handgezeichnet: die Schriftarten Caveat und Patrick Hand,
harte Schatten ohne Weichzeichnung, warmer Cream-Hintergrund, leichte
Rotationen. Die Farb-, Maß- und Schrift-Werte sind Tokens (`--kids-*`), 1:1 aus
dem Handoff-Artefakt `tokens-kids.css` übernommen. Hardcodierte Farben/Maße im
Buddy-CSS sind unzulässig.

*Tickets:* #40

## 9. Konfiguration

### PLAN-28 — Konfigurationswerte
Die Konfiguration verteilt sich auf zwei Per-Instanz-Dateien neben dem
Code (CONFIG-1) — beide gitignored:

- `plan/plan.json` — Daten-Konfig (Slots, Defaults, Kalender-ID, …).
  Format: `plan/plan.example.json`. Der Plan-Buddy liest die Datei pro
  Aufruf frisch von Disk (DCOMP-2 / DCOMP-3, Reload-on-Read mit
  Last-Known-Good-Fallback, siehe
  [`conventions/data-components.md`](../../conventions/data-components.md)).
  Der Admin-Reload-Endpoint (`POST /api/v1/plan/admin/reload`, #140)
  ist nur noch expliziter Reload-Marker.
- `plan/config.json` — Runtime-Konfig (Bind-Adresse, Log-Level), vom
  gemeinsamen `tools/configloader.py` (#179) nach CONFIG-1 geladen.

**Daten-Konfig (`plan/plan.json`)** — Schreibstelle ist der Eltern-Chat
(CONFIG-1).

| Name                         | Default                          | Datei-Schlüssel                | Gesetzt durch (Onboarding-Schritt) |
|------------------------------|----------------------------------|--------------------------------|------------------------------------|
| Slot-Definitionen            | die 7 Slots des Handoffs         | `slots`                        | n/a V1 (familienspezifisch hartcodiert, E-PLAN-8) |
| Default-Petrantwortlichkeiten | leer                             | `defaults`                     | n/a V1 (Familie trägt initial in Datei ein) |
| Fenster Lese-Kind            | 7 Tage                           | `fenster_lesekind`             | n/a (Default reicht) |
| Fenster Kleinkind            | 3 Tage                           | `fenster_kleinkind`            | n/a (Default reicht) |
| Wochenstart                  | Montag (`0`)                     | `wochenstart`                  | n/a (Default reicht) |
| SQLite-Datei                 | `plan.db` neben dem Code         | `db_datei`                     | n/a (Default reicht) |
| Google-Kalender-ID           | (Pflicht, kein Default)          | `kalender_id`                  | KAV — Kalender verbinden (`kalender-verbinden.md`) |
| OAuth-Client / -Token        | (Pflicht)                        | — (im Zugangsdaten-Speicher, ZD-3) | KAV — Kalender verbinden |
| Zeitzone                     | `Europe/Berlin`                  | `zeitzone`                     | n/a (Default reicht) |
| Familie-Origin-URL           | `http://127.0.0.1:5010`          | `familie_origin_url`           | n/a (Default reicht; Loopback auf den Familie-Port aus PORT-2) |

> **Begriffsabgrenzung:** `wochenstart` (PLAN-28) legt den **Wochentag** fest,
> an dem eine Datenbankwoche beginnt (0 = Montag) — intern für PLAN-10 und
> `plan.db`. Er ist unabhängig vom **View-Anker** (`?ab=`, PLAN-4), der
> steuert, welcher Tag als erste Spalte angezeigt wird.

`familie_origin_url` ist die Loopback-Origin, unter der der Plan-Buddy
die Familie-Komponente per HTTP anspricht (FAM-7) — kein direkter
Python-Import (DCOMP-1). Default zeigt auf den Familie-Port aus PORT-2;
ein abweichendes Pi-Setup setzt die Datei (CONFIG-1) oder die ENV-
Variable `PLAN_FAMILIE_ORIGIN_URL` (CONFIG-5).

**Runtime-Konfig (`plan/config.json`)** — Bind/Log, gemeinsamer Loader
(#179). Eltern-Chat schreibt diese Werte nicht.

| Name        | Default       | Datei-Schlüssel | Gesetzt durch (Onboarding-Schritt) |
|-------------|---------------|-----------------|------------------------------------|
| Listen-Host | `127.0.0.1`   | `listen_host`   | n/a (Default reicht, falls Pi nicht abweicht) |
| Listen-Port | `5020`        | `listen_port`   | n/a (Default reicht, falls Pi nicht abweicht) |
| Log-Level   | `INFO`        | `log_level`     | n/a (Default reicht) |

ENV-Variablen folgen CONFIG-5 (`PLAN_<KEY>`) und sind Dev-Override, keine
Familien-Form. CLI-Flags (`--host`, `--port`, `--log-level`, `--config`)
sind Test-Werkzeug.

*Tickets:* #40, #179, #210, #214

## 10. Tests

### PLAN-29 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), reproduzierbar und **ohne Netz** — der Google-Kalender-Zugriff
wird durch eine kontrollierte Doppelung ersetzt. Mindest-Abdeckung: PLAN-3
(`?ansicht=klein` → 3 Spalten, keine Termin-Leiste) · PLAN-4 (Fenster beginnt
heute; `?ab=` schiebt den Anker) · PLAN-7/PLAN-8 (Klick-Cycle schreibt, erneuter
Abruf zeigt die Zuweisung) · PLAN-10 (erste Anzeige einer Woche belegt aus
Defaults; Fenster über zwei Wochen liest beide) · PLAN-12 (Event mit Kindername
→ Aktivitäts-Slot; ohne → Termin) · PLAN-14 (Event über mehrere Tage → eine
Spanne) · PLAN-17/PLAN-19 (Rohantwort → normalisiertes Modell; Titel-Treffer
schlägt Creator-E-Mail; früherer Treffer gewinnt) · PLAN-18 (anlegen/ändern/
löschen rufen die richtige Operation) · PLAN-20 (fehlende Credentials → leeres
Lese-Ergebnis, View funktioniert) · PLAN-22/PLAN-23 (Termin-Schnittstelle
liefert Termine; ist der Plan-Buddy nicht erreichbar, ist die Schnittstelle
nicht erreichbar) · PLAN-28 (Reload-on-Read: nach Cross-Service-Schreibvorgang
in plan.json liefern `_current_config()` und `_db()` beim nächsten Request den
neuen Stand ohne Service-Restart — DCOMP-2) · PLAN-30 (Lese-API liefert
Defaults bei leerer Woche, spiegelt PUTs, antwortet 400 bei ungültigem
`week_start`) · PLAN-31 (PUT /api/v1/plan/zuteilung: Pflichtfeld-400, ungültiger
Slot-400, unbekannte person_id-400, gültiger PUT schreibt und ist per GET
sichtbar).

Läufe gegen den **echten** Kalender sind opt-in und nicht Teil des
Standard-Durchlaufs (analog `eltern-chat.md` EC-17).

*Tickets:* #40

---

## Offene Punkte

- **OPEN-PLAN-A — Slot-Liste je Familie.** Die sieben Slots des Handoffs sind
  für eine Familie kuratiert. Andere Familien brauchen andere (Hund,
  Hausaufgaben). PLAN-6 macht die Slots konfigurierbar — offen ist, ob es dafür
  ein UI braucht oder die Config-Datei genügt.

- **OPEN-PLAN-B — Aktivitäts-Erkennung ist eine Heuristik.** Die Zuordnung
  Kind ↔ Aktivität (PLAN-12) ist ein Substring-Abgleich im Titel — robust für
  bekannte Namen, aber eine Heuristik.

- **OPEN-PLAN-C — Picker-Aktualisierung.** Der Quell-Prototyp lädt nach einer
  Aktivitäts-Änderung die Seite neu (`location.reload()`) statt die Zelle
  gezielt zu aktualisieren. Funktional, aber ein Workaround. Kein V1-Blocker.

- **OPEN-PLAN-D — Sperre vor dem Editieren.** V1 erlaubt jedem am Display jede
  Änderung (PLAN-25). Ob Petrantwortlichkeiten gegen versehentliches Ändern
  geschützt werden, ist eine spätere Entscheidung.

- **OPEN-PLAN-F — Mehrere Kalender je Familie.** Familien- und Schul-/Vereins-
  Kalender getrennt zu führen, bräuchte eine Quellen-Zuordnung je Event. V1
  kennt genau einen Kalender (PLAN-15). Kein V1-Bedarf belegt.

---

## Entscheidungen

### E-PLAN-1 — Plan-Buddy ist eine App: besitzt Daten, Funktion, Schnittstelle
*Datum:* 2026-05-22

Der Plan-Buddy ist eine eigenständige App. Er **besitzt** seine Daten (die
Petrantwortlichkeiten, PLAN-9) und seine Funktion (die Kalender-Anbindung,
Abschnitt 6) und stellt beides über **Schnittstellen** bereit (Abschnitt 7).
Andere XBuddy-Apps sind Nutzer dieser Schnittstellen, nicht Mit-Eigentümer. Eine
von der App bereitgestellte Fähigkeit existiert für einen Konsumenten genau
dann, wenn die App installiert ist (PLAN-23) — der Eltern-Chat kann Termine nur
verwalten, wenn der Plan-Buddy da ist.

**Verworfen:** die Kalender-Anbindung als freistehende Plattform-Fähigkeit zu
spezifizieren, die mehrere Apps gleichberechtigt mitbenutzen. Das hätte einen
zweiten Eigentümer für dieselbe Funktion geschaffen. Klare Eigentümerschaft —
eine App besitzt, andere nutzen — hält die Abhängigkeiten einseitig
(CLAUDE.md §6).

> **Hochgehoben (2026-05-27):** Das Muster „App besitzt Daten + Funktion +
> Schnittstelle" gilt seit heute für alle XBuddy-Apps — als Prinzip in der
> [Constitution](../constitution.md#app-eigentümerschaft) und operativ in
> [`conventions/apps.md`](../../conventions/apps.md) (APP-1 … APP-3).
> E-PLAN-1 bleibt als historische Erstanwendung des Musters stehen.

### E-PLAN-2 — Slots und Defaults sind Konfiguration, nicht Code
*Datum:* 2026-05-22

Die Slot-Liste und die Default-Petrantwortlichkeiten leben in einer Config-Datei.
Im Quell-Prototyp war die Slot-Liste an drei Stellen hart verdrahtet — der
`planbuddy-kids`-Handoff benannte das als teuerste Refactor-Stelle. XBuddy
verbietet Code-Konstanten ohne Override-Pfad (CLAUDE.md §6). Das ist **keine**
Layout-Optimierung (das Layout bleibt 1:1, E-PLAN-5), sondern die Trennung von
Daten und Code. Die Beispiel-Config bildet die sieben Slots exakt ab.

### E-PLAN-3 — Zwei Stufen als Query-Variante einer View
*Datum:* 2026-05-22

Lese-Kind- und Kleinkind-Stufe sind **eine** View `woche` mit einem
Query-Parameter, nicht zwei Views. Die URL-Konvention verlangt Varianten als
Query-Parameter (URL-2). Inhaltlich *ist* es eine View — dieselben Daten,
adressatengerecht übersetzt, exakt das „Mitwachsen" der Constitution.

### E-PLAN-4 — Petrantwortlichkeiten lokal, Aktivitäten & Termine im Kalender
*Datum:* 2026-05-22 (übernommen aus dem Handoff `planbuddy-kids`)

Wer-bringt-wen (PLAN-8) liegt **lokal** in SQLite, Kind-Aktivitäten und Termine
(PLAN-11, PLAN-13) liegen im **Kalender**. Petrantwortlichkeiten sind eine
plan-interne Konvention, die es im Google-Kalender nicht natürlich gibt — lokal
zu halten ist einfach. Aktivitäten und Termine *sind* Kalender-Einträge; sie
dort zu halten heißt, dass eine Änderung im Google-Kalender und eine am Display
dasselbe Ergebnis haben — keine zweite Wahrheit, kein Sync.

### E-PLAN-5 — Layout 1:1 aus dem Wireframe-Handoff
*Datum:* 2026-05-22

Das Layout beider Stufen wird unverändert aus dem Wireframe-Handoff „PlanBuddy
Kids" übernommen — in XBuddy **nicht** neu gestaltet. Das Handoff-Paket liefert
Template (`plan_kinder.html`) und Tokens (`tokens-kids.css`) als Artefakte. Was
in XBuddy neu entsteht, ist die Anbindung an Registry, Zugangsdaten-Speicher,
Kalender und URL-Konvention — nicht das Aussehen. Das Layout ist bereits gegen
den Design-Handoff abgenommen; eine Neugestaltung wäre verworfene Arbeit.

### E-PLAN-6 — Kalender-Anbindung gehört der App
*Datum:* 2026-05-22

Die Google-Kalender-Anbindung ist eine Funktion des Plan-Buddys (Abschnitt 6),
keine eigene Plattform-Spec. Sie ist Folge von E-PLAN-1: der Plan-Buddy ist die
App, die mit dem Familien-Plan arbeitet — also besitzt er den Kalender-Zugang
und stellt ihn über PLAN-22 bereit. Der Eltern-Chat braucht für „Termine aus
Bild" denselben Zugang; er bekommt ihn als Nutzer der Schnittstelle (PLAN-22),
nicht über eine eigene Anbindung. Die Eltern-Chat-seitige Nutzung der
Schnittstelle ist ein eigenes Ticket auf dem Eltern-Chat-Track, kein Teil
dieser Spec.

### E-PLAN-7 — Eigener OAuth-Client, auf Production veröffentlicht
*Datum:* 2026-05-22

XBuddy legt einen eigenen Google-OAuth-Client an und veröffentlicht ihn auf
**Production**. Ein Client im Testing-Modus lässt Refresh-Tokens nach 7 Tagen
verfallen (Symptom: HTTP 400 `invalid_grant`, Termine verschwinden) — ein
Betriebs-Risiko, das das Veröffentlichen einmalig beseitigt.

### E-PLAN-8 — V1 ist familienspezifisch hartcodiert; Familie 2–4 per Repo-Fork
*Datum:* 2026-05-23

Der Plan-Buddy ist in V1 auf die Abläufe **einer** Familie zugeschnitten —
zwei Kinder, abendliche Bringen-und-Ins-Bett-Routine, eine spezifische Liste
von Kind-Aktivitäten. Diese familienspezifischen Inhalte leben absichtlich
als Code-Konstanten: der Aktivitäts-Katalog in `plan/aktivitaeten.py`
(`AKTIVITAETEN`), die Personen-Auflösung über Titel-Treffer in
`plan/kalender.py` (PLAN-19), die Abend-Routine als feste Slot-Sequenz
hinter E-PLAN-2.

Familie 2–4 entstehen per **Repo-Fork und Hand-Anpassung mit Claude**,
nicht über generische Konfiguration. Das ist nicht Bequemlichkeit, sondern
bewusste Anwendung von CLAUDE.md §6 („auf Vorrat externalisieren bleibt
Wildwuchs"): solange keine fünfte Familie da ist, deren Ablauf wieder
anders ist, gibt es keinen konkreten Schmerz, der eine Plan-Engine
rechtfertigt.

**Trigger zum Umdenken** — frühestens dann generalisieren wir:
- ≥5 aktive Familien-Forks, ODER
- eine Familien-Anpassung berührt mehr als ~3 Code-Stellen pro Familie,
  ODER
- Code-vs-Live-Drift zwischen zwei Familien wird zum wiederkehrenden
  Sync-Problem.

**Verworfen:** jetzt eine Plan-Engine mit Aktivitäts-Katalog-DSL und
Ablauf-Templates bauen. Wäre exakt die Vorrats-Generalisierung, die §6
verbietet — und würde die V1-Liefermenge in eine offene Architektur-Frage
zurückwerfen.

Diese Entscheidung ergänzt E-PLAN-2: dort ist die **Slot-Struktur** Daten
(sieben Slots als Config), hier sind die **Familien-Routinen** Code. Die
Linie liegt bewusst tief — wer den Plan inhaltlich ändert, fasst Python
an. Wer einen Slot dazunimmt, fasst die Config an.
