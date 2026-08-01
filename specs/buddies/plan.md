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
(Morgen-/Abendablauf) — eigene App, der Routine-Buddy (`routine.md`, #335) ·
weitere Views über `woche` hinaus · mehrere Aktivitäten
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
Konfiguration: stabiler Schlüssel, Art (`petrantwortlich` | `kalender-read`),
Icon und — bei Kalender-Read-Slots (Aktivitäts-Slots) — das zugehörige Kind.
Die Art-Maschinen-Strings sind seit Sprint 2 `petrantwortlich` (Konzept
„Petrantwortlichkeits-Slot", PLAN-7 — war `erwachsenen-slot`, nach Toggle-All
V1.3 eine Namens-Lüge, da Kinder zuweisbar sind) und `kalender-read` (Konzept
„Aktivitäts-Slot", PLAN-11 — read-only aus dem Kalender, war `aktivitaets-slot`).
Der Parser liest beide Schreibweisen (Lese-Toleranz, siehe unten). Die Beispiel-Konfiguration
bildet die sieben Slots des Wireframe-Handoffs 1:1 ab: `bring`, `pick`, `act1`
(Kind A), `act2` (Kind B), `cook`, `bed1` (Kind A), `bed2` (Kind B).

**Anzeige-Name `label` (optional, #1126):** Ein Slot trägt zusätzlich ein
**optionales `label`** — einen frei wählbaren Anzeige-Namen für die Eltern-
Einstellungs-Seite (PLAN-35/PLAN-37). Es ist **rein anzeigend**: der stabile
`schluessel` (PLAN-9) bleibt unberührter Identifikator, `label` ändert keine
Datenhaltung. **Wenn** ein Slot ein `label` trägt, **dann** muss es ein String
sein und die Anzeige nutzt es; **fehlt** es (`null`/weggelassen), **dann** zeigt
die Einstellungs-Seite den `schluessel` als Fallback. Der Parser
(`plan/config.py:_parse_slots`) liest `label` tolerant (optional, kein
Pflichtfeld) — bestehende `plan.json`-Dateien ohne `label` laufen unverändert.

**Icon-Form (V1.2, #578):** Das `icon`-Feld eines Slots ist eine **ARASAAC-`id`**
(Integer-String, identisch zur Form in PLAN-12). Der Plan-Buddy konsumiert das
Bild über den geteilten Icon-Pfad `/display/_shared/icons/arasaac/<id>.png`
(ICONS-5, analog ROUTINE-10) — **ein Icon-Pfad** (CLAUDE.md §6). Verworfen:
interne Icon-Keys (`sun`/`clock`/`fork`/`moon`/`star`) — das wären zwei
Icon-Quellen (Schedule-Rail vs. Aktivitäts-Katalog), Stilbruch innerhalb der
View. Die V1.2-Defaults in `plan/plan.example.json`: bring → `37807`
(petrabschieden), pick → `39520` (wiedersehen), act1/act2 → `3071` (kalender,
generisches Aktivitäts-Slot-Icon), cook → `2342` (kochen), bed1/bed2 → `6027`
(bett — Werft #578 Revision Nic 2026-06-10 #647, ersetzt Mond 2933). **Revision 2026-06-10 (Nic, Werft #578):** act1/act2 wurden von `2752`
(Stern) auf `3071` (Kalender) revidiert — der Stern-Icon wäre eine zweite
Darstellung des Kalender-Slots neben dem Termin-Piktogramm, der Kalender-Icon
ist konsistenter (Befund Pi-Deploy). Diese Werte sind Werft-Befunde und können
je Familie über `plan.json` überschrieben werden (CONFIG-1).

**Layout (V1.3 — Display-Robustheit, RAT-4-Auflösung 2026-06-22):** Die
Schedule-Rail liegt als CSS-Grid im Frame mit der Zeilen-Form
`grid-template-rows: auto auto repeat(var(--slot-count), 80px) 1fr`:
Header, Day-Row, je Slot eine fixe Zeile (80 px), und die Termin-Leiste
(PLAN-13) bekommt den verbleibenden Platz (`1fr`). Slot-Anzahl ist
konfigurierbar via `--slot-count` (keine Hardcode-Annahme). Ab **9 Slots**
schreibt `_parse_slots` ein WARN-Log — die Familien-1-Display-Geometrie
(DC-15, 1920×1080 quer) ist nur bis 8 Slots vertikal lesbar getestet.
Pflicht-Experiment vor Layout-Merge: Tablet-Screenshot mit 8 Slots × 3
Tagen × 5 Terminen + 2 Spans, Termin-Bereich ≥ 200 px sichtbar.
**Verworfen:** freier `flex`-Wuchs des Schedule-Bereichs, der die
Termin-Leiste aus dem Frame drückte (heutige Form, Befund 2026-06-22).
**Verworfen:** `vh`-Skalierung — auf fixem Tablet kein Viewport-Wechsel,
nur Indirektion ohne Nutzen.

**Icon-Migration abgeschlossen (V1.3 → T1114, 2026-06-30):** Die
Migrations-Lesephase für alte interne Icon-Keys (`sun`/`clock`/`fork`/`moon`/
`star`) ist entfernt. Alle `plan.json`-Dateien tragen ARASAAC-IDs direkt
(V1.2-Form). Das Template rendert `slot.icon` direkt über den geteilten
Icon-Pfad; der Template-Mapper `SLOT_ICON_ID` ist entfallen.

**Slot-Art-Lese-Toleranz (V1.4 — Sprint 2, Schema-Vereinheitlichung):** Die
Slot-Art-Maschinen-Strings wurden umbenannt — `erwachsenen-slot` →
`petrantwortlich`, `aktivitaets-slot` → `kalender-read` (Treiber: Toggle-All
V1.3 machte „erwachsenen" zur Lüge; „kalender-read" benennt die read-only
Kalender-Herkunft klar). Es ist **reines Rename** — kein Verhaltenswechsel an
den Slots. Der Parser (`plan/config.py:_parse_slots`) trägt analog zur
Icon-Lesephase eine **Migrations-Lesephase**: die alten Art-Strings werden
mit **WARN-Log** akzeptiert, neu geschriebene Slots tragen die neuen Strings.
Live-`plan.json`-Migration läuft **extern im Deploy-Schritt** (BUD-2);
`plan.example.json` wird im selben PR umgestellt. Die Lese-Toleranz ist
Übergangshilfe — Folge-Ticket nach Stabilität entfernt sie. Der API-Wire-
Vertrag (PLAN-30/31) ist **nicht** betroffen: die Payload trägt einen
Slot-`key`, nie die Art.

*Tickets:* #40, #578, #642, #1116

### PLAN-7 — Petrantwortlichkeits-Slots: Zuweisung per Klick-Cycle
Eine Zelle eines Petrantwortlichkeits-Slots (`petrantwortlich`) zeigt entweder das Foto-im-Ring (FAM-4)
einer Person oder einen leeren Slot mit Plus-Icon. Ein Tippen schaltet
zyklisch weiter: Person 1 → Person 2 → … → leer → Person 1.

**Toggle-All (V1.3 — RAT-4-Auflösung 2026-06-22):** Der Cycle iteriert über
**alle Personen** aus der Familien-Registry (`familie.md` FAM-2) —
Erwachsene **und** Kinder. Die Reihenfolge ist die Registry-Reihenfolge.
Diese Klausel löst die V1-Beschränkung „nur Erwachsene im Cycle" auf;
eine Slot-spezifische Whitelist gibt es nicht (RAT-4-Auflösung). Wer in
welchem Slot landen darf, ist familien-konfigurierbar über die
Toggle-Wahl, nicht über Code (E-PLAN-8). Schreib-API-Validierung
(PLAN-31) bleibt orthogonal: sie prüft Slot-Sorte und Personen-Existenz
(FAM-3), nicht Personen-Art.

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
Ein Kalender-Event wird genau dann als Aktivitäts-Slot-Inhalt einsortiert, wenn
sein Titel den Namen einer Person trägt, die einen kalender-read-Slot besitzt
(PLAN-19). kalender-read-Slots dürfen Personen jeder Art referenzieren — Kind
ODER Erwachsener; das Slot-Feld `kind` ist ein stabiler Personen-Identifier
(FAM-3), kein Art-Filter (T1178).
Die Art der Aktivität (Icon/Label) folgt aus einem Schlüsselwort im Titel.
Trägt ein Event keinen solchen Personennamen, ist es kein Aktivitäts-Slot-Inhalt,
sondern ein Termin (PLAN-13).

**Mehrere Slots pro Kind (#1145, #1150):** Hat ein Kind mehrere
Aktivitäts-Slot-Zeilen (PLAN-11) — zwei Zeilen für dasselbe Kind —, erscheint
ein passendes Kalender-Event in **jeder** dieser Slot-Zeilen als regulärer
Aktivitäts-Chip: gleiche Event-`id`, gleiches Aktivitäts-Icon und Label. Das
Kind→Slot-Mapping ist 1:n, nicht 1:1; kein einzelner Slot „gewinnt" das Event
für sich. Dies ist die Kind-Geschwister-Klausel zur Multi-Person-Regel
(PLAN-19, „landet in **jeder** der zugeordneten Slot-Zeilen, gleiche
Event-`id`").

Ein Kind-Aktivitäts-Eintrag trägt immer ein Symbol: das Piktogramm der
erkannten Aktivitäts-Art (Schlüsselwort im Titel) oder — wenn kein Schlüsselwort
passt — ein generisches Fallback-Symbol. Ein Kind-Slot-Eintrag ist nie
symbol-/typlos.

Die Schlüsselwörter zur Aktivitäts-Erkennung und die zugehörigen Termin-Icons
(PLAN-13) kommen aus **einer gemeinsamen Quelle**: dem Aktivitäts-Katalog in
`plan.json` (Sektion `aktivitaeten`, siehe PLAN-28). `plan/aktivitaeten.py`
trägt den V1-Default als CONFIG-4-Fallback (fehlt die Sektion, läuft die
Familie-1-Bestückung unverändert). Beide Hälften — Erkennung und Termin-Icon —
lesen aus derselben Quelle, damit sie nicht divergieren können.

**Picker (V1.1, #642):** Der Aktivitäts-Picker zeigt alle Einträge aus
`Config.aktivitaeten` (AKTIVITAETEN_V1 als CONFIG-4-Fallback). Die
`picker_options`-Liste wird von `render.py:baue_view` als Teil des View-
Modells gebaut — keine zweite hartcodierte Aktivitäts-Liste im Template
(CLAUDE.md §6). Tint-Farben pro Aktivität optional: V1-Familien-Einträge
haben feste Tints, unbekannte arts bekommen den Default `#eeeeee`. Reihenfolge:
die konfigurierte Katalog-Reihenfolge (V1: Familien-Aktivitäten zuerst, dann
Termin-spezifische Einträge).

**Leere Kinder-Aktivitäts-Slots (V1.1, #642):** Ein leerer Aktivitäts-Slot
eines Kindes (kein Kalender-Event für diesen Slot) zeigt ein **Plus-Symbol**
als Anlege-Indikator — Inline-SVG, gedimmt (opacity 0.4, ~30 px). Erwachsenen-
Slots zeigen weiterhin `empty-face`; volle Kinder-Slots zeigen den Aktivitäts-
Chip. Nur leere Kinder-Aktivitäts-Slots tragen das Plus, nicht Petrantwortlichkeits-Slots.

**Piktogramm-Form über die zentrale Bibliothek (ICONS-4/ICONS-7-Konsum,
verbindlich, V1.1 #471):** Das Feld `piktogramm` eines `aktivitaeten`-
Eintrags ist eine **ARASAAC-`id`** (Integer-String, identisch zur Form in
ROUTINE-10). Der Plan-Buddy konsumiert das Bild über den geteilten
Icon-Pfad `/display/_shared/icons/arasaac/<id>.png` (analog ROUTINE-10
und CLAUDE.md §6: ein Icon-Pfad). **Verworfen:** Plan-eigene
Bilder/Datei-Namen unter `plan/static/icons/` oder ähnlichem — das wäre
ein zweiter Icon-Pfad und damit Wildwuchs. Bei einer fehlenden ARASAAC-ID
(weder im Eintrag noch im Default) rendert der Plan-Buddy das generische
Fallback-Symbol (gleicher Mechanismus wie ROUTINE-Punkt-Render bei
fehlendem PNG, ICONS-7-Garantie auf lokal vorliegendes PNG).

*Tickets:* #40, #308, #445, #642

## 5. Termin-Leiste

### PLAN-13 — Einzel-Termine
Unter der Schedule-Rail zeigt die Lese-Kind-Stufe (PLAN-3) eine Termin-Leiste:
je Tagesspalte die Termine dieses Tages aus dem Familien-Kalender, die keine
Kind-Aktivität sind (PLAN-12). Ein Termin zeigt — falls vorhanden — Uhrzeit,
Titel und das Foto-im-Ring der zugeordneten Person (PLAN-19 → `familie.md`
FAM-4). Sind keine Credentials da oder ist der Kalender nicht erreichbar
(PLAN-20), bleibt die Leiste leer; die übrige View funktioniert weiter. Die
Kleinkind-Stufe hat keine Termin-Leiste (PLAN-3).

Ein zeitgebundener (nicht-ganztägiger) Einzel-Termin erscheint in der
Termin-Leiste mit seiner Uhrzeit — auch wenn sein Titel einen Kindernamen
trägt (PLAN-12, PLAN-24-Ausnahme) und er deshalb zusätzlich im Aktivitäts-Slot erscheint. Beide
Darstellungen zeigen denselben Kalender-Event (gleiche Event-`id`). Eine
ganztägige Kind-Aktivität erscheint nur im Aktivitäts-Slot, nicht in der
Termin-Leiste. Mehrtägige Events folgen PLAN-14 bzw. bleiben bei child-named
mehrtägig im Kind-Slot.

Die Keyword-Heuristik für Termin-Icons bezieht ihre Aktivitäts-Keywords aus
dem Aktivitäts-Katalog (PLAN-12, gemeinsame Quelle mit `plan/aktivitaeten.py`,
#308). Termin-spezifische Einträge ohne eigene Aktivitäts-Art (Zahnarzt,
Ferien/Urlaub, Treff, Garten, Schule) **wandern in V1.2 in den Aktivitäts-
Katalog** (`plan.json`-Sektion `aktivitaeten`) — als reguläre Einträge mit
`art`/`label`/`keywords`/`piktogramm`. Die V1.2-Werft-Migration (#578) wählt
ARASAAC-IDs: zahn → `11229`, ferien/urlaub → `3166`, treff → `6487`,
garten → `2434`, schule → `3082`. **Verworfen:** zweite Quelle in
`render.py` `_TERMIN_ICON_EXTRAS` — eine Quelle (CLAUDE.md §6: kein Fakt
zweimal), Familie kann jeden Eintrag über den PAS-Skill (PAS-3) oder
direkten `plan.json`-Edit anpassen.

**Termin-Fallback (V1.2):** Trägt ein Termin kein passendes Keyword, rendert
die Pille das generische Termin-Icon `kalender` (ARASAAC `3071`) statt des
heutigen Wireframe-`icon_sparkle`. Auch das ist eine ARASAAC-`id`, nicht ein
interner Key — eine Icon-Quelle, eine Form (PLAN-12 / PLAN-6).

**Termin-Überschuss (V1.3 — RAT-4-Auflösung 2026-06-22):** Trägt eine
Tagesspalte mehr Termine, als die Termin-Leiste vertikal ohne Druck
darstellt, zeigt die Spalte die ersten N sichtbar und unten einen Counter
`+M weitere` als gedimmten Text-Indikator. Der Counter ist V1.3 reine
Sichtbarkeits-Mechanik **ohne Klick-Pfad** — eine Klick-Detail-View
(Tages-Overlay) ist Folge-Ticket (QW4). **Verworfen:** vertikales Scrollen
(Display-Modus ohne Touch-Fokus); dynamischer Schrift-Shrink (Pille wird
unlesbar).

*Tickets:* #40, #308, #578

### PLAN-14 — Mehrtages-Termine als Spanne
Ein Termin über mehrere Tage des Fensters wird **einmal** als durchgehender
Balken über die betroffenen Spalten gezeigt, nicht je Tag wiederholt. Die
Zusammengehörigkeit wird über die stabile Event-`id` (PLAN-17) erkannt — für
ganztägige wie für zeitgebundene mehrtägige Events.

**Sichtbarkeit (V1.3 — RAT-4-Auflösung 2026-06-22):** Eine Mehrtages-Spanne
wird erst ab ihrem **Start-Tag** im sichtbaren Fenster gerendert.
- Beginnt ein Event **vor** dem Fenster und reicht in das Fenster hinein
  (z. B. Mo–Fr, Anzeige ab Mi), zeigt die Spanne ab dem ersten Fenster-Tag
  (der Termin läuft bereits).
- Beginnt ein Event **nach** dem ersten Fenster-Tag (z. B. Mi–Sa, Anzeige
  ab Mo), bleibt die Termin-Zeile in den Vorlauf-Spalten (Mo–Di) **frei**
  für andere Termine. Die Spanne reserviert ihre Zeile nicht ab Anzeige-
  Beginn.

**Verworfen:** durchgehende Zeilen-Reservierung über das ganze Fenster
(heutige Form, Befund 2026-06-22: blockiert die Anzeige an Tagen, an
denen die Spanne noch nicht läuft).

**PLAN-14-PACKING — Termin-Packing als Puzzle-Fill (V1.4 — #1146, 2026-07-01):** Der
Termin-Bereich ist ein 2D-Raster aus 7 Spalten × **R** Zeilen. R leitet sich aus
der realen Tablet-Geometrie ab (verfügbare 1fr-Höhe nach Kopf, Slot-Zeilen,
Chrome, reservierter Counter-Zeile und Marge, geteilt durch die Zeilenhöhe H);
R ist **span-unabhängig** (der frühere globale Lane-Abzug war der Bug #1146).

1. **Spans zuerst:** `pack_span_lanes` weist jeder Mehrtages-Spanne eine **Lane**
   (oberste Zeilen) zu; der Balken belegt seine Lane-Zeile durchgehend über
   `[start_day..end_day]`.
2. **Freie Zellen pro Spalte von oben:** Eine Zelle (Zeile r, Tag d) ist **frei**,
   wenn dort KEIN Span liegt — inkl. **Löcher in Lane-Zeilen** (eine Lane an einem
   Tag belegt, an einem anderen frei) und aller Zeilen unter dem Lane-Band.
3. **Tages-Termine zeitsortiert von oben in die freien Zellen:** früheste Zelle
   zuerst. Ein Tages-Termin **darf über einem Span-Balken sitzen**, wenn das die
   oberste freie Zelle ist (**Regel i**); die Zeitreihenfolge ist früh-oben
   (**Regel ii**).
4. **Sortier-Setzung (Orchestrator, #1146):** Innerhalb eines Tages kommen
   **ganztägige/zeitlose** Termine ZUERST (oben), dann die getakteten aufsteigend
   nach Beginn.
5. **Überschuss pro Spalte:** Termine über die freien Zellen einer Spalte hinaus
   fasst ein gedimmter `+N weitere`-Counter zusammen (V1.3-Mechanik, kein
   Klick-Pfad), bündig unter der letzten belegten Zeile.

**Invariante:** Eine Spalte clippt einen Termin **nur**, wenn ihre eigenen freien
Zellen voll sind — **nie**, weil ein Span in einer **anderen** Spalte Platz kostet.

**Geometrie-Kopplung:** H (Python `GEOMETRIE_PILLE_HOEHE`) ist die Zeilenhöhe des
Termin-Rasters; die Overlay-Lane-Höhe (`GEOMETRIE_SPAN_LANE_HOEHE`) ist auf H
angeglichen. Im Template tragen `.appts-col` (Tages-Termine) und `.appts-spans`
(Balken-Overlay) dieselbe Zeilenhöhe (`grid-auto-rows: H`) und denselben
Zeilen-Gap, damit ein Loch-Termin mit dem Balken der Nachbarspalte fluchtet. Der
frühere globale Span-Band-Abzug (`GEOMETRIE_SPAN_GAP`, `--span-band`,
`.under-span`-Padding) ist entfallen. **Verworfen:** globales Deckeln der
Sichtbarkeit über alle Spalten (Bug #1146).

*Tickets:* #40, #1146

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

### PLAN-19 — Titel-Konvention & Personen-Auflösung (V1.1 Multi-Person)
Ein Event, das Personen betrifft, trägt deren **Namen im Titel** — Form
`<Titel> <Name1>` für eine Person (z. B. „Klettern Finn", „Shibari Jonas")
oder `<Titel> <Name1> <Name2>` für zwei (z. B. „Mia Finn Schwimmkurs",
„Sandra Jonas Eltern-Abend"). Die Anbindung ordnet jedes Event **einer
oder zwei Personen** der Familien-Registry zu, in dieser Reihenfolge:
(1) **Titel-Treffer** — kommen ein oder mehrere Personennamen (FAM-3) im
Titel vor, sind das die Personen (bis maximal zwei, in Reihenfolge der
ersten Erwähnung; weitere Erwähnungen werden ignoriert); (2) **Creator-
E-Mail** — sonst, ist die Creator-Adresse die E-Mail eines Erwachsenen,
ist das die einzige Person; (3) sonst keine Zuordnung. Diese Konvention
ist die tragende Entscheidung der Anbindung — Personen-Zuordnung und
das Aktivitäts-Routing (PLAN-12) fallen aus ihr heraus.

**Maximal zwei Personen** in V1.1 (#473) — pragmatische Obergrenze, weil
ein zeitgleicher Drei-Personen-Termin in der Praxis seltener ist und das
Layout der Termin-Leiste/des Aktivitäts-Slots bei 3+ Avataren zerfällt
(eine Werft-Frage, die V1.1 bewusst nicht aufmacht). Ein drittes
Vorkommen im Titel wird verworfen, nicht abgelehnt — das Event landet
mit den ersten zwei aufgelösten Personen. **Verworfen:** unbeschränkte
Personenliste (Layout-Risiko).

**Datenmodell-Form:** das Feld heißt `personen` und ist immer eine
Liste (Single-Person-Events sind eine Ein-Element-Liste). Bestehende
plan.json-Daten ohne `personen`-Feld bleiben kompatibel — der Parser
ergänzt die Liste leer oder aus PLAN-19-Auflösung.

**Display (V1.2-Korrektur, #578):** Das Display zeigt Multi-Person-Events
**je nach Stelle** unterschiedlich — die Personen-Identität wird so getragen,
dass kein Slot zerfällt:

- **Aktivitäts-Slot-Zeile (PLAN-12):** Ein Event mit zwei Personen-IDs
  landet in **jeder** der zugeordneten Personen-Slot-Zeilen als regulärer
  Aktivitäts-Chip — die Personen-Identität ist durch die Zeile gegeben,
  nicht durch eine Avatar-Doppelung im Chip. Beide Zeilen zeigen denselben
  Kalender-Event (gleiche Event-`id`), mit demselben Aktivitäts-Icon und
  Label. Eine Änderung über den Klick (Picker, PLAN-11) wirkt auf den
  einen Kalender-Event und ist beim nächsten Render in beiden Zeilen
  sichtbar.
- **Termin-Leiste (PLAN-13):** Eine Termin-Pille zeigt **zwei Avatare
  nebeneinander** vor dem Termin-Label im Foto-im-Ring-Stil — ein Termin,
  mehrere Personen, eine Pille. Die Termin-Leiste behält die Zwei-Avatar-
  Form, weil die Pillen pro Tag-Spalte stehen (nicht pro Person), und die
  Personen-Zuordnung dort sonst unsichtbar wäre.

Ein Einzel-Person-Event bleibt unverändert: ein Avatar in der Termin-Pille
bzw. ein Chip in der Personen-Zeile. Ein „Familie"-Sammel-Icon bei N>1 ist
**verworfen** (zu generisch — die Familie sieht nicht, wen es betrifft).

**Verworfen 2026-06-09 (#578, Werft-Korrektur):** die ursprüngliche V1.1-
Form „zwei Avatare nebeneinander geteilt auf den Aktivitäts-Slot" — der
Slot ist zu eng (chip-Form mit Icon + Label), zwei 24px-Avatare brechen die
Pillenform; die Personen-Identität ist über die Zeile bereits gegeben (das
ist der eigentliche Zweck der Aktivitäts-Slot-Zeilen pro Kind). Termin-
Leiste behält die Doppel-Avatar-Form (s. o.).

**Personen-Match für kalender-read (T1178):** `klassifiziere_event_multi`
erhält als Match-Liste alle Personen, die einen kalender-read-Slot besitzen
— nicht ausschließlich Kinder. Das Slot-Feld `kind` ist ein stabiler
Personen-Identifier (FAM-3); ein Slot kann Kind ODER Erwachsener zugeordnet
sein. Die Funktion ist art-agnostisch — sie prüft Namens-Treffer im Titel
gegen die übergebene Personen-Liste.

*Tickets:* #40, #473, #578, #1178

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

Body: `{ "titel": "<string>", "beginn": "<ISO>", "ende"?: "<ISO>" [, "event_id": "<id>"] }`.
`titel` ist Pflicht (nicht leer). `datum` ist Alias für ganztägiges `beginn`
(Rückwärts-Compat — `{ "titel", "datum" }` verhält sich wie `{ "titel", "beginn" }`).

**Typ-Erkennung über `T` im String** (spiegelt `_parse_when` aus dem Lese-Pfad):

- `beginn` ohne `T` → **ganztägig**: `beginn` und `ende` sind ISO-Datumsstrings
  (`YYYY-MM-DD`). `ende` ist optional; fehlt es, ist der Termin eintägig. Der
  Adapter schreibt `start.date=beginn`, `end.date=ende+1Tag` (Google-exklusiv-Ende).
  `ende` darf nicht vor `beginn` liegen → 400.
- `beginn` mit `T` → **zeitgebunden**: `beginn` und `ende` sind ISO-Datetime-Strings
  mit Offset. `ende` ist Pflicht; `ende` muss nach `beginn` liegen → sonst 400.
  Der Adapter schreibt `start.dateTime=beginn.isoformat()`,
  `end.dateTime=ende.isoformat()`. Naive Datetimes werden in der Familien-Zeitzone
  (`plan.json`-Schlüssel `zeitzone`, Default `Europe/Berlin`) aware gemacht.
- Typ-Mismatch: `beginn` date + `ende` datetime oder umgekehrt → 400.
- `datum` und `beginn` beide gesetzt, aber ungleich → 400.
- Datum/Zeit eines bestehenden Termins via `event_id` ändern ist nicht unterstützt
  (nur Umbenennen) — Folge-Ticket.

Ohne `event_id` → `{ "ok": true, "action": "created", "event_id": "<id>" }`.
Mit `event_id` → bestehenden Termin umbenennen →
`{ "ok": true, "action": "patched", "event_id": "<id>" }`.
Kalender nicht erreichbar: HTTP 502. Ungültige Eingabe: HTTP 400.

*Tickets:* #40, #256

### PLAN-33 — Bulk-Termin-Schnittstelle: mehrere Termine in einem Aufruf anlegen
Der Plan-Buddy stellt eine **Bulk-Schreib-Schnittstelle** für Termine
bereit, mit der konsumierende Apps **mehrere** Termine in **einem**
HTTP-Aufruf anlegen können — Form: `POST /api/v1/plan/termine/bulk`.
Erst-Konsument ist `specs/platform/termine-aus-bild.md` TAB-9 (Termine
aus Bild); PLAN-22 (Einzel-PUT) bleibt unverändert daneben für Aufgaben
mit einem Termin (TES). Eine konsumierende App entscheidet zwischen
PLAN-22 (Einzel) und PLAN-33 (Bulk) anhand ihres eigenen Vertrags —
PLAN-33 ist nicht „besser" als PLAN-22, sondern für mengenmäßig anderen
Konsum.

**Body** (`Content-Type: application/json`):
`{ "request_id": "<UUIDv4>", "items": [ <PLAN-22-PUT-Body>, … ] }`.
- `request_id` ist Pflicht (Idempotenz, PLAN-33.5).
- `items` ist eine nicht-leere Liste; jedes Element folgt der
  PLAN-22-PUT-Body-Form (`titel`, `beginn`, `ende?`); kein
  `event_id` (PLAN-33 legt nur an, ändert nicht).

#### PLAN-33.1 — Pre-validate + best-effort write, kein Rollback
Der Bulk-PUT petrarbeitet die Items in zwei Phasen:

1. **Pre-validate** — alle `items` werden vor irgendeinem Google-Schreib-
   Call gegen die PLAN-22-Validierungs-Regeln geprüft (Pflichtfelder,
   Typ-Erkennung über `T` in `beginn`, Datums-Bedingung **ganztägig
   `ende ≥ beginn`** bzw. **zeitgebunden `ende > beginn`** wie in PLAN-22
   PUT-Vertrag, kein Typ-Mismatch). Schlägt **mindestens eines** der
   Items in der
   Pre-Validate-Phase fehl, antwortet der Endpoint mit HTTP 400 und
   einer `results`-Liste, in der **alle** Items als `{ "ok": false,
   "error_code": "validation", "error": "<Detail>" }` markiert sind —
   es wird **nichts** geschrieben. Das schützt die Familie vor
   inkonsistenten Teil-Listen, in denen einige Termine bereits aus
   Strukturfehlern verworfen wären.

2. **Best-effort write** — ist die Pre-Validate-Phase sauber, schreibt
   der Bulk-PUT die Items **einzeln** in den Google-Kalender. Schlägt
   ein einzelner Google-Schreib-Call fehl (Rate-Limit, Auth-Verlust,
   anderer Google-Fehler), werden die **anderen** Items **trotzdem**
   geschrieben — der Endpoint macht **kein** Rollback. Die `results`-
   Liste meldet je Item den Erfolg oder den `error_code`. Begründung:
   ein Rollback nach Teil-Erfolg bräuchte Google-DELETE-Calls auf
   bereits geschriebene Events, die ihrerseits scheitern können — eine
   Rollback-Schicht, die ihre eigene Rollback-Schicht braucht. Die
   Familie sieht die N-von-M-Quittung und entscheidet, ob sie die
   gescheiterten Items per PLAN-22 (Einzel-PUT) nachträgt.

#### PLAN-33.2 — HTTP-Status-Tabelle und per-Item `error_code`
Antwort-Statuscodes:

- **HTTP 200** mit Body `{ "ok": true, "geschrieben": <N>, "gesamt":
  <M>, "results": [ … ] }` — der Bulk-Aufruf wurde petrarbeitet, einige
  Items können trotzdem in `results` als `{"ok": false}` markiert sein
  (best-effort, PLAN-33.1). `geschrieben` ist die Anzahl der erfolgreich
  geschriebenen Items; `gesamt` = `len(items)`. Reihenfolge in
  `results` entspricht der Reihenfolge in `items`.
- **HTTP 400** — Pre-Validate-Fehler (PLAN-33.1) **oder** Body-Struktur
  ungültig (fehlende `request_id`, `items` leer, `items` nicht Liste,
  `request_id` keine UUIDv4-Form) **oder** Cap-Überschreitung
  (PLAN-33.3). Body enthält bei Pre-Validate-Fehler die `results`-
  Liste; bei Struktur-Fehler einen einfachen `{"error": "…"}`-Body.
- **HTTP 401/403** — Loopback-/Auth-Verstoß analog PLAN-22 (Bulk-Pfad
  hat keine zusätzlichen Auth-Regeln gegenüber Einzel-PUT).
- **HTTP 409** — Idempotenz-Konflikt (PLAN-33.5: derselbe `request_id`
  mit anderem `items_hash`).
- **HTTP 502** — Kalender als Ganzes nicht erreichbar (Google-Service
  tot, OAuth-Token-Refresh schlägt fehl) — analog PLAN-20. Body
  `{"error": "calendar_unavailable"}`. **Nichts** wurde geschrieben.
- **HTTP 5xx (übrig)** — Plan-Buddy-interner Fehler. Die Antwort enthält
  keine `results`-Liste; der Konsument behandelt das wie PLAN-23-
  Szenario (App nicht erreichbar, TAB-10).

Per-Item `error_code`-Vokabular (in `results[i].error_code`):

- `validation` — Item scheitert an den PLAN-22-Validierungs-Regeln.
- `calendar_rate_limit` — Google-Calendar-API hat 429 oder 403 mit
  Rate-Limit-Hinweis zurückgegeben; PLAN-33.6 hat alle Retries
  aufgebraucht.
- `calendar_auth` — OAuth-Token-Refresh oder Calendar-Auth scheitert
  für dieses Item (kann passieren, wenn das Token zwischen Items
  abläuft).
- `calendar_other` — anderer Google-Fehler (5xx, malformed response,
  unbekannter Status), der nicht in `rate_limit`/`auth` fällt.

#### PLAN-33.3 — Server-Cap: maximal 30 Items je Aufruf
Der Endpoint lehnt Bulk-Aufrufe mit `len(items) > 30` mit HTTP 400 und
`{"error": "too_many_items", "max": 30}` ab. **Nichts** wird petrarbeitet.

Begründung der Zahl 30: Plan-Buddy macht in der heutigen Google-
Adapter-Form `plan/kalender.py:147` einen **OAuth-Token-Refresh pro
Insert** — eine Bulk-PUT mit 30 Items entspricht ungefähr 60 Google-
HTTP-Requests (30 Token-Refresh + 30 Insert), was bei einer
mittleren Insert-Latenz von ~250 ms und üblicher Quota-Auslastung
unter der 15-Sekunden-Antwort-Grenze (PLAN-33.4) bleibt. Die Token-
Cache-Optimierung aus PLAN-33.4 senkt das auf ~31 Requests
(1 Token-Refresh + 30 Insert) und gibt Reserve nach oben — ein
späteres Heben des Caps ist möglich, sobald der Token-Cache belegt
funktioniert (Folge-Ticket, sobald belegter Bedarf > 30 da ist).

Begründung „nicht 100, nicht unbegrenzt": ein Aufrufer, der 100 Termine
in einem Aufruf schickt, hat fast immer einen Bug (LLM-Halluzination
einer Tabelle, fehlerhafte Bild-Erkennung); 30 deckt einen vollständigen
Schul-Wochenplan oder einen typischen Vereins-Saisonplan ab, ohne
gleichzeitig Loops in die Familien-Daten zu öffnen.

#### PLAN-33.4 — Antwort-Zeit-Budget 15 s, Token-Cache, Client-Timeout
**Server-seitig:** Der Endpoint hält ein internes Antwort-Zeit-Budget
von **15 Sekunden** ein. Läuft die Bulk-Petrarbeitung in dieses Budget
(inklusive PLAN-33.6 Backoff-Wartezeiten), antwortet der Endpoint mit
dem Stand der Petrarbeitung — verbleibende Items werden als
`{"ok": false, "error_code": "calendar_rate_limit"}` markiert (Backoff
hat 15-s-Cap getroffen). Das Budget schützt den Eltern-Chat-Konsumenten
vor unbegrenzt langen Buddy-Calls.

**Token-Cache:** Der Plan-Buddy hält den OAuth-Access-Token während
der Bulk-Petrarbeitung **prozess-lokal** zwischen — ein Refresh am
Anfang, dann dieselbe Bearer-Authorization für alle 30 Inserts. Das
senkt die Request-Zahl von `2N` (Refresh + Insert je Item) auf
`N + 1` (ein Refresh + N Inserts). Der Cache läuft nur **innerhalb**
eines Bulk-Aufrufs (kein persistierter Token-Cache zwischen Aufrufen
— das wäre eine zweite Token-Wahrheit gegenüber dem
Zugangsdaten-Speicher und ist Out-of-Scope; siehe CLAUDE.md §6
„kein Fakt zweimal").

**Client-Timeout (im Konsumenten):** Der Eltern-Chat-Konsument
(`termine-aus-bild.md` TAB-9) setzt für **diesen** Bulk-Aufruf einen
HTTP-Client-Timeout von **20 Sekunden** (15 s Server-Budget + 5 s
Reserve für Transport-Latenz). Andere Eltern-Chat → Plan-Buddy-Calls
(z. B. PLAN-22 Einzel-PUT in TES-8, PLAN-30 Lese) bleiben beim
bisherigen 2-Sekunden-Client-Timeout — das ist ein **explizit
gezielter** Override für den Bulk-Pfad, kein globaler Anstieg.

#### PLAN-33.5 — Idempotenz via `request_id` (UUIDv4-Pflicht in V1)
Jeder Bulk-Aufruf trägt eine `request_id` (UUIDv4) im Body. Der Endpoint
hält eine **In-Memory-Map** mit LRU-Verhalten:

- **Größe:** 256 Einträge (LRU-Eviction, wenn voll).
- **Zeit-Begrenzung:** Einträge verfallen nach **15 Minuten** ab
  Aufnahme — eine Familie, die einen Aufruf nach mehr als 15 Minuten
  „nochmal versuchen" lässt, bekommt eine reguläre Neu-Petrarbeitung,
  kein Idempotenz-Treffer.

**Verhalten bei wiederholter `request_id`:**

- Selber `request_id` **mit identischem `items_hash`** (SHA-256 über die
  kanonisierte `items`-Liste) → der Endpoint antwortet mit der
  **gespeicherten Antwort** des Erst-Aufrufs (HTTP 200 + dieselbe
  `results`-Liste). Der Aufruf hat **keinen** Nebeneffekt im
  Google-Kalender — er wird **nicht** doppelt geschrieben.
- Selber `request_id` **mit anderem `items_hash`** → HTTP 409 mit
  `{"error": "request_id_collision"}`. Begründung: ein
  `request_id`-Konflikt mit unterschiedlichen Items deutet auf einen
  Aufrufer-Bug (`request_id` wiederverwendet) oder einen Konflikt
  zwischen zwei Eltern-Chat-Instanzen — ein 409 ist die ehrlichere
  Antwort als „still überschreiben".

Die `request_id` lebt **nicht** persistent in `plan.db`. Begründung: nach
einem Prozess-Neustart ist der Schutz weg — das ist akzeptiert, weil ein
Familien-Neustart-während-Aufruf-Szenario extrem selten ist und der
Aufrufer in dem Fall ohnehin den ganzen TAB-7-Sammel-Vorschlag neu
bestätigt (also einen **neuen** `request_id` generiert). UUIDv4-Pflicht in
V1, weil eine Familien-Skill-Implementierung sonst versucht sein könnte,
einen integer-Zähler oder einen Hash zu verwenden, der über Instanzen
hinweg kollidiert (`xbuddy-knowledge/CONTEXT.md` Mehr-Familien-Linie:
jede Instanz darf nicht in das ID-System einer anderen geraten).

#### PLAN-33.6 — Exponential backoff mit Jitter für 403/429
Schlägt ein einzelner Google-Insert mit HTTP 403 (Rate-Limit) oder 429
(zu viele Requests) fehl, wartet der Plan-Buddy **exponential mit
Jitter** und versucht es erneut — Google-Doku-konforme Retry-Linie
(`Retry-After`-Header wird respektiert):

- **Versuche je Item:** maximal **3 Retries** (= 4 Versuche insgesamt je
  Item — der erste Insert plus 3 Retry-Versuche), dann
  `error_code: calendar_rate_limit`.
- **Backoff-Wartezeiten:** vor jedem Retry-Versuch wird gewartet. **Drei
  Wartezeiten** (zwischen den vier Versuchen): **1 s → 2 s → 4 s**,
  jeweils mit ±25 % Jitter. Initialwert 1 s; je nächster Retry
  verdoppelt. Hard cap pro Wartezeit: **8 s** (die Sequenz bei 3 Retries
  übersteigt den Cap ohne `Retry-After` nicht).
- **`Retry-After`-Header:** Sendet Google einen `Retry-After`-Header,
  **sticht** der Header-Wert die berechnete Backoff-Zeit — **außer**
  wenn der Header-Wert das **verbleibende Server-Budget** aus
  PLAN-33.4 übersteigt: dann wird das Item **ohne** weitere Wartezeit
  als `calendar_rate_limit` markiert. Das 15-s-Server-Cap ist hart und
  geht über `Retry-After` — der Server kann auf einen `Retry-After: 60`
  nicht warten, weil er innerhalb von 15 s antworten muss.
- **Budget-Anrechnung:** Backoff-Wartezeit zählt **in** das 15-s-Server-
  Budget aus PLAN-33.4. Frisst der Backoff das Budget auf, werden
  verbleibende Items mit `calendar_rate_limit` markiert, ohne erneuten
  Versuch.

Begründung „nicht nur 429 + Retry-After": Google Calendar API gibt bei
Quota-Überschreitung sowohl 403 (`userRateLimitExceeded`,
`rateLimitExceeded`) als auch 429 zurück (siehe Google Cloud-Doku zu
Calendar-API-Quoten). Eine reine 429-Erkennung würde die häufigeren
403-Rate-Limit-Fälle als `calendar_other` fehlinterpretieren.

*Tickets:* #475 (TAB Erst-Konsument)

### PLAN-30 — Lese-API für Wochenzuteilungen
Der Plan-Buddy stellt die persistierten Petrantwortlichkeits-Slot-Zuteilungen einer
Woche unter `GET /api/v1/plan/zuteilung?week_start=<YYYY-MM-DD>` bereit —
Form analog FAM-7 (GET, Query-Parameter, JSON-Antwort). Antwort:
`{ "week_start": "<YYYY-MM-DD>", "slots": [ { "day": 0..6, "slot": "<key>",
"person_id": "<id>|null" }, … ] }`. Die Liste enthält je Wochentag je
Petrantwortlichkeits-Slot eine Zeile; leere Stellen tragen `person_id: null`. Ein
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

### PLAN-31 — Schreib-API für Petrantwortlichkeits-Slot-Zuteilungen
Der Plan-Buddy nimmt Zuteilungen von anderen XBuddy-Apps über
`PUT /api/v1/plan/zuteilung` entgegen — analog PLAN-30 (Lese-Seite).
Body: `{ "week_start": "<YYYY-MM-DD>", "day": 0..6, "slot": "<key>",
"person_id": "<id>"|null }`. Alle vier Felder sind Pflicht (außer
`person_id`, das `null` sein darf, um einen Slot zu leeren). Wirkung:
schreibt die Zuweisung atomar in `plan.db` (PLAN-9) — identisch mit dem
Klick-Cycle im View (PLAN-7/PLAN-8). Antwort: `{ "ok": true }`.

Fehler-Semantik: `400` mit JSON-Fehler bei fehlendem Pflichtfeld, `slot`
nicht vorhanden oder kein Petrantwortlichkeits-Slot (PLAN-6), `person_id` unbekannt
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

Diese Regel betrifft die **vom Plan-Buddy selbst** gesetzte Personen-Identität (Foto-im-Ring statt Namens-Label).

**Termin-Label-Strip bei eindeutiger Foto-Resolution (V1.3 — RAT-4-Auflösung 2026-06-22, Nic-Tatsachenbeleg „es ist zu voll, ich kann Zahnarzt heute nicht lesen"):** In Termin-Labels (PLAN-13) und Mehrtages-Span-Pillen (PLAN-14) wird ein erkannter Personen-Name aus dem familien-eigenen Kalender-Titel **gestrippt**, **wenn** `resolve_personen(titel)` (`plan/kalender.py`, PLAN-19) genau **eine** Person liefert. Die Foto-Resolution trägt dann die Identität (Foto-im-Ring), das Label trägt den verbleibenden Termin-Inhalt. Beispiel: „Emil Zahnarzt" → Label „Zahnarzt" + Foto Emil.

**Verbatim bei Mehrdeutigkeit:** Bei **≥2 Personen-Treffern** im Titel (z. B. „Sport mit Petra und Emil") bleibt das Label **verbatim**, weil die Foto-Resolution mehrdeutig wird und der Namens-Bezug semantisch trägt. Auch ohne Personen-Treffer bleibt das Label verbatim — Strippen passiert nur bei n=1.

**Geltungsbereich:** Der Strip betrifft den Termin-Bereich (PLAN-13 + PLAN-14). Die Aktivitäts-Slot-Routing-Mechanik (PLAN-12) bleibt unberührt — Kind-Aktivitäten werden weiter über Titel-Kindername zugeordnet. Diese V1.3-Klausel **ersetzt** die V1-Ausnahme „Strippt nicht den wörtlichen Kalender-Titel" für den eindeutigen Single-Person-Fall; alle anderen Fälle (Mehrdeutigkeit, kein Treffer) behalten die V1-Verbatim-Form.

*Tickets:* #40, #303

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
Rotationen. Die Farb-, Maß- und Schrift-Werte sind Tokens (`--kids-*`).

Die `--kids-*`-Tokens kommen aus dem **geteilten Design-Token-Strang**
([`conventions/design-tokens.md`](../../conventions/design-tokens.md), DTOK-1).
Plan referenziert den Strang — er kopiert ihn nicht (DTOK-3). Der Strang liegt
unter `display/_shared/design/tokens.css` (v2.0) und wird von dort über
`/display/_shared/design/tokens.css` referenziert (ROU-30, #323).

Font-Werte (Caveat als Display-Font, Patrick Hand als Body-Font) bleiben
semantisch identisch; künftig ggf. über Aliase (`--kids-font-display`,
`--kids-font-body`) aus dem geteilten Strang bezogen.

Hardcodierte Farben/Maße im Buddy-CSS sind unzulässig (DTOK-5).

*Tickets:* #40, #323

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

**Daten-Konfig (`plan/plan.json`)** — Eigentümer der Datei ist der Plan-Buddy.
Werte, die im Onboarding entstehen (heute `kalender_id`), setzt der Eltern-Chat
über die Plan-Admin-API (PLAN-32, APP-3) — nicht durch Direkt-Schreiben
(CONFIG-1).

| Name                         | Default                          | Datei-Schlüssel                | Gesetzt durch (Onboarding-Schritt) |
|------------------------------|----------------------------------|--------------------------------|------------------------------------|
| Slot-Definitionen            | die 7 Slots des Handoffs         | `slots`                        | n/a V1 (familienspezifisch hartcodiert, E-PLAN-8) |
| Default-Petrantwortlichkeiten | leer                             | `default_petrantwortlichkeiten` | Eltern-Einstellungs-Seite P2 (PLAN-35) via PLAN-36; Familie kann `plan.json` zusätzlich direkt editieren |
| Aktivitäts-Katalog           | 9 Einträge (V1-Default)          | `aktivitaeten`                 | Skill „Plan-Aktivitäten setzen" (`plan-aktivitaeten-setzen.md` PAS) ruft PLAN-34; Familie kann `plan.json` zusätzlich direkt editieren |
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

### PLAN-32 — Admin-Endpoint: `kalender_id` setzen (Plan-Buddy schreibt selbst)
Der Plan-Buddy nimmt seine `kalender_id` über einen Admin-Endpoint entgegen,
statt dass ein fremder Dienst `plan.json` direkt schreibt (APP-3):
`PUT /api/v1/plan/admin/kalender`, Body `{ "kalender_id": "<id>" }`.

- **Loopback-only** (`127.0.0.1`/`::1`, sonst 403); die nginx-Origin leitet
  `…/admin/…` nicht weiter — dieselbe Härtung wie `admin/reload` (#140).
- Der Plan-Buddy **schreibt selbst** nur den `kalender_id`-Schlüssel atomar in
  `plan/plan.json` (Temp-Datei + `os.replace`; alle anderen Werte byte-gleich)
  — er ist Eigentümer seiner Datei.
- Übernahme **in-process** auf demselben atomaren Pfad wie `admin/reload`
  (Config neu bauen, Transport mit neuer `kalender_id` neu binden; bei Parse-/
  Schreibfehler bleibt der alte Snapshot unberührt).
- Antwortet **400** bei fehlendem/leerem `kalender_id`, **200** bei Erfolg.

Damit ist die `kalender_id`-Schreibstelle der Plan-Buddy selbst; der Eltern-Chat
(KAV) **ruft** diesen Endpoint, statt `plan.json` zu schreiben.

*Tickets:* #341

### PLAN-34 — Admin-API für den Aktivitäts-Katalog (lesen, hinzufügen, löschen)
Der Plan-Buddy stellt seinen Aktivitäts-Katalog (PLAN-12, `plan.json`-Sektion
`aktivitaeten`) anderen XBuddy-Apps über drei Endpoints zur Verfügung — der
Plan-Buddy schreibt seine `plan.json` selbst (APP-3, analog PLAN-32), ein
konsumierender Skill ruft die Endpoints, statt die Datei direkt zu öffnen.
Ein Lese-Endpoint ergänzt die Schreibseite, damit ein Skill den Bestand
vor einem Vorschlag prüfen kann.

**GET-Vertrag** — `GET /api/v1/plan/aktivitaeten` (öffentlich, kein Loopback-Gate):

Antwort: JSON-Array der aktuellen Katalog-Einträge — je Eintrag
`{ "art": "<schlüssel>", "label": "<text>", "keywords": ["…", …],
"piktogramm": "<arasaac-id>" }`. Reload-on-Read (DCOMP-2): pro Aufruf
frisch aus `plan.json`. Fehlt die Sektion in `plan.json`, antwortet der
Endpoint mit dem Code-Default (CONFIG-4-Fallback, PLAN-12).

**POST-Vertrag** — `POST /api/v1/plan/admin/aktivitaeten` (loopback-only):

Body: `{ "art": "<schlüssel>", "label": "<text>", "keywords": ["…", …],
"piktogramm": "<arasaac-id>" }`. Alle vier Felder Pflicht, alle nicht-leer.
`art` muss neu sein (keine doppelte `art`) — sonst HTTP 409
`{"error": "art_existiert"}`. `keywords` ist eine nicht-leere Liste
nicht-leerer Strings (Aktivitäts-Erkennung PLAN-12). `piktogramm` ist
eine ARASAAC-`id` als String (PLAN-12, ICONS-1) — die Existenz des PNG in
der Icon-Wurzel wird vom Plan-Buddy **nicht** geprüft (ein Icon-Pfad,
CLAUDE.md §6: ICONS-7 garantiert lokales PNG nur, wenn der Wert über die
Suche kam; bringt ein Aufrufer eine ID „aus der Hand", trägt er das
Risiko des Fallback-Symbols). Wirkung: der Eintrag wird der Sektion
`aktivitaeten` in `plan.json` atomar hinzugefügt (Temp-Datei +
`os.replace`, alle anderen Werte byte-gleich — derselbe Schreib-Pfad wie
PLAN-32). Existiert die Sektion noch nicht, wird sie aus dem CONFIG-4-
Fallback (PLAN-12) als Startpunkt materialisiert und der neue Eintrag
angehängt. Antwort: `{ "ok": true, "art": "<schlüssel>" }`.

**DELETE-Vertrag** — `DELETE /api/v1/plan/admin/aktivitaeten/<art>` (loopback-only):

Wirkung: der Eintrag mit der gegebenen `art` wird aus der `aktivitaeten`-
Sektion entfernt — atomar wie POST. Existiert die Sektion in `plan.json`
noch nicht, wird sie aus dem CONFIG-4-Fallback (PLAN-12) materialisiert
und der Eintrag daraus gelöscht. Antwort: `{ "ok": true, "art": "<schlüssel>" }`.

**Fehler-Semantik:** `400` bei fehlendem/leerem Pflichtfeld oder
ungültigem Body, `403` bei nicht-Loopback-Aufruf der Admin-Endpoints
(analog PLAN-32, nginx leitet `…/admin/…` nicht weiter), `404` beim
DELETE auf eine unbekannte `art`, `409` bei doppelter `art` im POST. Bei
Parse-/Schreibfehler im POST/DELETE bleibt der alte Snapshot atomar
unberührt (analog PLAN-32 / `admin/reload`).

**Wirkung im Display:** Reload-on-Read greift automatisch (DCOMP-2): der
nächste Plan-Display-Aufruf oder GET sieht den neuen Stand ohne Service-
Restart. Ein bestehender Kalender-Event, dessen Titel das neue Keyword
trägt, wird ab dann mit dem zugehörigen ARASAAC-Piktogramm gerendert
(PLAN-12 Heuristik).

Damit ist die Schreibstelle für den Aktivitäts-Katalog der Plan-Buddy
selbst; der Eltern-Chat-Skill „Plan-Aktivitäten setzen"
(`plan-aktivitaeten-setzen.md` PAS) **ruft** diese Endpoints, statt
`plan.json` zu schreiben (APP-3).

*Tickets:* #445, #471, #578

### PLAN-35 — P2: Eltern-Einstellungs-Seite (PWA-Mantel)

> P2 der Drei-Phasen-Lieferung (RAT-4-Auflösung 2026-06-22, decisions/RAT-4-259).
> Liefer-Form 2026-06-25 ratifiziert: PWA-Mantel + dedizierte plan-API, NICHT
> Wetter-interner-Save.
> ENTSCHEID-File 20260625-074425 Paket-Sektion „(a) Frontend-Ort" → seiten/-PWA-Mantel; Sektion „Call 1 (Sorte)" → typ:pwa-Schablone; Sektion „Call 2 (Auth)" → PUBLIC-Kopplung ohne authHeaders.

Die Eltern-Einstellungs-Seite des Plan-Buddys ist eine **Homescreen-PWA**
(`typ: "pwa"`, SREG-15) — kein Telegram-Mini-App-Formfaktor. Frontend-Mantel
(Manifest, Service-Worker, statische Assets) lebt im Aggregator-Service `seiten`
unter dessen Asset-Wurzel; die Daten-API bleibt beim Plan-Buddy (APP-1-Eigentum,
PLAN-36/PLAN-37). Surface: `/seiten/plan/einstellungen`.

Die Seite trägt **zwei Editor-Bereiche** nebeneinander: den **Defaults-Editor**
(Default-Petrantwortlichkeiten, PLAN-10, über PLAN-36) und den
**Slot-Modell-Editor** (Slot-Definitionen anlegen/löschen/ändern, PLAN-6, über
PLAN-37). Beide bedienen dieselbe Instanz-Konfiguration (`plan.json`). Der
Personen-Picker bietet **alle** Personen aus `familie.json` (FAM-3) an
(Toggle-All, RAT-4-Auflösung: keine Slot-Whitelist); die Piktogramm-Suche im
Slot-Modell-Editor nutzt den **geteilten Icon-Such-Pfad** (ICONS-1).

**Zielgruppe:** Eltern. Die Seite ist **deskriptiv eltern-adressiert**, kein
Berechtigungs-Gate (SREG-6).

**Defaults-Editor — Verhalten:**
- **Wenn** die Seite geladen wird, **dann** zeigt sie den aktuellen Stand der
  Default-Petrantwortlichkeiten (PLAN-10) — bezogen über `GET /api/v1/plan/defaults`
  (PLAN-36) — als bearbeitbares Raster Slot × Wochentag, mit den togglebaren
  Personen aus `familie.json` (Toggle-All, RAT-4-Auflösung: keine Slot-Whitelist).
- **Wenn** Eltern eine Slot/Wochentag-Zelle einer Person zuweisen oder leeren,
  **dann** persistiert die Seite den Gesamtstand über `PUT /api/v1/plan/defaults`
  (PLAN-36) — und die Default-Petrantwortlichkeiten gelten ab dem nächsten
  Reload-on-Read (DCOMP-2) ohne Direkt-Schreiben in die Datei (CONFIG-1).
- **Wenn** eine zugewiesene `person_id` nicht (mehr) in `familie.json` existiert,
  **dann** weist PLAN-36 den Schreibvorgang ab (HTTP 400), und die Seite zeigt
  den unveränderten Vorzustand.

**Abgrenzung — Umfang von P2 (Nic-Setzung 2026-06-25):**
- Die **wochenkonkrete** Petrantwortlichkeits-Zuteilung hat bereits einen
  Schreib-/Lesevertrag (PLAN-30/PLAN-31, `/api/v1/plan/zuteilung`). PLAN-35
  editiert ausschließlich die **Default**-Vorbelegung (PLAN-10), nicht die
  Wochen-Overrides.
- Das **Slot-Modell** (Slot-Definitionen — anlegen, löschen, `art`/`icon`/`kind`
  ändern) IST jetzt Teil von P2: der Slot-Modell-Editor (PLAN-37) ist der zweite
  Bereich dieser Seite. „Dafür machen wir ja die ganze Übung; P1/P2 waren die
  Vorbereitung dafür" (Nic 2026-06-25, überstimmt die frühere ENTSCHEID-Linie
  „slot-modell NOCH NICHT → P3").
- **NICHT in P2 — sauber abgegrenzt:** Der **per-Slot-`cycle`-Filter** (eine
  familien-spezifische Whitelist „wer darf in *diesem* Slot stehen", altes
  #259/E-PLAN-8) bleibt **RAT-4-Defer** (decisions/RAT-4-259). PLAN-7 V1.3
  Toggle-All gilt weiter: jede Person aus der Registry ist in jeden
  Petrantwortlichkeits-Slot zuweisbar, es gibt keine Slot-Whitelist. Das ist die
  **per-Slot-`cycle`-Generalisierung**, NICHT das Slot-CRUD — und nur sie ist
  vertagt (siehe PLAN-37-Abgrenzung).

**Auth:** PUBLIC / Netz-Trust (auth.md AUTH-6, `/api/v1/plan/*`). Die Seite zieht
**keine** Identitäts-Header — der Browser-Pfad liefert leere Auth (kein `initData`,
keine `authHeaders`/`ensureAuth`).

*Tickets:* #1126 (Refs #259)

### PLAN-36 — Defaults-Schreib-API: `GET/PUT /api/v1/plan/defaults`

> Echte Lücke: für die Default-Petrantwortlichkeiten (PLAN-10) gibt es heute
> keinen nicht-loopback Schreibpfad — nur Direkt-Edit der Datei oder der
> loopback-only Admin-Reload (PLAN-32-Muster). PLAN-36 schließt sie genau für P2.
> ENTSCHEID-File 20260625-074425 Paket-Sektion „(b) Daten-API" → genau EINE neue Route; Sektion „Call 3 (defaults-Korrektheit)" → Form↔Datei-Mapping + Roundtrip.

Der Plan-Buddy stellt die Default-Petrantwortlichkeiten (PLAN-10) unter
`/api/v1/plan/defaults` bereit — Form analog PLAN-30/PLAN-31.

**`GET /api/v1/plan/defaults`** — liefert den aktuellen Stand:
`{ "defaults": { "<slot_key>": { "<wochentag 0..6>": "<person_id>|null }, … } }`.
Reload-on-Read (DCOMP-2): die Konfig wird pro Aufruf frisch gelesen.

**`PUT /api/v1/plan/defaults`** — nimmt den Gesamtstand entgegen. Body:
`{ "defaults": { "<slot_key>": { "<wochentag 0..6>": "<person_id>|null }, … } }`.

- **Wenn** der Body wohlgeformt ist und alle genannten `person_id` in
  `familie.json` (FAM-3) existieren und alle `slot_key` ein Petrantwortlichkeits-Slot
  (PLAN-6) sind, **dann** wird der Stand persistiert und die Antwort ist
  `{ "ok": true }`.
- **Wenn** ein Pflichtfeld fehlt, ein `slot_key` unbekannt / kein
  Petrantwortlichkeits-Slot ist, ein `wochentag` außerhalb 0..6 liegt oder eine
  `person_id` unbekannt ist (FAM-3), **dann** HTTP 400 mit JSON-Fehler, **kein** 500,
  und es wird **nichts** geschrieben (Validierung vor Persistenz).

**Form↔Datei-Mapping (verbindlich):** Die API-Nutzform heißt `defaults`. Die
Datei-Persistenz schreibt den Stand ZWINGEND unter dem Datei-Schlüssel
`default_petrantwortlichkeiten` — denn das ist der Schlüssel, den der Config-Loader
liest (`plan/config.py`). Ein Schreiben unter `defaults` würde beim nächsten Laden
ignoriert.

**Persistenz-Verhalten:**
- **Wenn** ein `PUT` erfolgreich validiert, **dann** wird die Konfig-Datei
  **atomar** geschrieben (kein Teilstand bei Absturz) und der Buddy übernimmt den
  neuen Stand ohne Prozess-Neustart (Reload, PLAN-32-Muster `admin/reload`).
- **Roundtrip-Garantie (testbares Requirement):** Nach einem erfolgreichen
  `PUT defaults=X` liefert ein anschließendes `load_config` / `GET defaults`
  denselben Stand X. Dieser Roundtrip ist als Test Pflicht.
- **Schreib-Serialisierung gegen Lost-Update (#1149):** Alle `plan.json`-Schreibpfade
  lesen-ändern-schreiben **dieselbe** Datei — es gibt fünf solche RMW-Pfade:
  PLAN-32 (`admin/kalender` — `kalender_id` setzen), PLAN-34 (`admin/aktivitaeten`
  POST + DELETE), PLAN-36 (`defaults`), PLAN-37 (`slot-modell`). Zwei zeitgleiche
  Schreiber (z. B. `PUT defaults` + `PUT slot-modell`) dürfen sich **nicht**
  überschreiben — kein verlorenes Section-Update. Da der Plan-Buddy ein einzelner
  Prozess mit `threaded=True` ist, **genügt eine prozess-interne Serialisierung**:
  ein gemeinsamer In-Process-Lock (`threading.Lock`) um alle fünf
  Read-Modify-Write-Pfade. Ein Datei-Lock über Prozessgrenzen ist **nicht** nötig
  (ein Prozess, konsistent mit RAT-14). Das atomare Schreiben (DCOMP-4) verhindert
  nur Torn-Reads, **nicht** den Lost-Update bei überlappendem Read-Modify-Write —
  daher diese zusätzliche Serialisierung.

**Auth:** PUBLIC / Netz-Trust (auth.md AUTH-6, `/api/v1/plan/*`).

*Tickets:* #1126 (Refs #259)

### PLAN-37 — Slot-Modell-Editor & Slot-Modell-API: `GET/PUT /api/v1/plan/slot-modell`

> P2-Erweiterung (Nic-Setzung 2026-06-25): das Editieren des Slot-Modells
> (Slot-Definitionen, PLAN-6) ist der zweite Editor-Bereich der P2-PWA
> (PLAN-35). „Dafür machen wir ja die ganze Übung; P1/P2 waren die Vorbereitung
> dafür." Überstimmt die frühere ENTSCHEID-Linie „slot-modell NOCH NICHT → P3".
> ENTSCHEID-File 20260625-074425 Paket-Sektion „(b) Daten-API" → slot-modell jetzt IN P2 (Nic 2026-06-25, überstimmt „→ P3"); Sektion „Call 1 (Sorte)" → typ:pwa-Schablone trägt auch diesen zweiten Editor-Bereich; Sektion „Call 3 (defaults-Korrektheit)" → Form↔Datei-Mapping + atomarer Multi-Sektion-Write + Roundtrip-Test, hier auf slots + default_petrantwortlichkeiten gespiegelt.

**Surface:** Teil derselben P2-PWA (`/seiten/plan/einstellungen`, PLAN-35) — ein
zweiter Editor-Bereich neben dem Defaults-Editor (PLAN-35/PLAN-36). Die Daten-API
bleibt beim Plan-Buddy (APP-1-Eigentum).

**Integritäts-Default (Nic-Setzung 2026-06-25): `schluessel` ist UNVERÄNDERLICH.**
Der Slot-`schluessel` ist der stabile Identifikator des Slots in der Datenhaltung
(PLAN-9) und in den Defaults (PLAN-10) — siehe PLAN-6. Der Editor erlaubt genau
drei Operationen:
- **Slot ANLEGEN** — ein neuer `schluessel`, der vorher nicht existierte.
- **Slot LÖSCHEN** — ein bestehender `schluessel` wird aus der Liste entfernt.
- **Slot ÄNDERN** — bei einem bestehenden `schluessel` dürfen NUR `art`, `icon`,
  das optionale `label` (Anzeige-Name, PLAN-6) und (bei `kalender-read`) `kind`
  geändert werden — **nicht** der `schluessel`.

Ein **Umbenennen** des `schluessel` ist **nicht erlaubt** (vermeidet, dass
Defaults (PLAN-10) und historische DB-Zuteilungen (PLAN-30/31) verwaisen, und
spart eine DB-Migration). Umbenennen = Slot löschen + Slot neu anlegen, bewusst
zweistufig.

**`GET /api/v1/plan/slot-modell`** — liefert die aktuelle Slot-Liste:
`{ "slots": [ { "schluessel": "<key>", "art": "petrantwortlich|kalender-read",
"icon": "<arasaac-id>", "kind": "<person_id>"?, "label": "<anzeige-name>"? },
… ] }` — Form aus PLAN-6 (`plan/config.py` `Slot.to_dict`). `label` ist der
optionale Anzeige-Name (fehlt, wenn nicht gesetzt). Reload-on-Read (DCOMP-2): die
Konfig wird pro Aufruf frisch gelesen.

**`PUT /api/v1/plan/slot-modell`** — nimmt die **Gesamt-Slot-Liste** entgegen
(Body wie GET). Die übergebene Liste IST der Soll-Zustand; was fehlt, gilt als
gelöscht.

- **Wenn** der Body wohlgeformt ist — jeder Slot hat `schluessel`, `art`, `icon`;
  `art ∈ {petrantwortlich, kalender-read}`; jeder `kalender-read`-Slot trägt ein
  `kind`, das in `familie.json` (FAM-3) existiert; ein etwaiges `label` ist ein
  String (optional, fehlen/`null` erlaubt); alle `schluessel` sind eindeutig —
  und kein Rename-Versuch vorliegt (s. u.), **dann** wird die Slot-Liste inkl.
  `label` persistiert, die Defaults werden konsistent gehalten (s. u.), die
  Konfig neu geladen, und die Antwort ist `{ "ok": true }`. **Fehlt** das `label`
  eines Slots, **dann** wird es nicht persistiert (kein `null`-Müll) und der GET
  liefert den Slot ohne `label`.
- **LÖSCHEN als Folge des Soll-Zustands:** **Wenn** ein `schluessel`, der vorher
  in der Konfig stand, in der PUT-Liste **fehlt**, **dann** gilt das als LÖSCHEN:
  der Slot UND seine Einträge in `default_petrantwortlichkeiten` (PLAN-10) werden
  entfernt. Historische DB-Zuteilungen (PLAN-30/31) des gelöschten Slots bleiben
  **unangetastet** (kein Cascade-Delete) — sie rendern nicht mehr, weil der Slot
  fehlt, und sind harmlos.
- **Rename-Versuch wird abgewiesen:** **Wenn** der PUT einen `schluessel` eines
  bestehenden Slots *änderte* — also ein Schlüssel verschwindet UND ein neuer
  auftaucht, der die Änderung eines bestehenden sein soll — wird das als Löschen
  (alt) + Anlegen (neu) behandelt; ein direkter In-Place-Rename desselben Slots
  ist nicht ausdrückbar, weil die Identität AM `schluessel` hängt. Trägt der Body
  eine Form, die den `schluessel` eines existierenden Slots umschreiben will
  (z. B. ein Editor-Feld, das ihn als veränderbar anbietet), weist die API das
  mit **HTTP 400** ab (`schluessel ist unveränderlich`). Anlegen ist nur über
  einen `schluessel`, der vorher nicht existierte.
- **>8 Slots:** **Wenn** die PUT-Liste mehr als 8 Slots trägt (`SLOT_WARN_AB = 9`,
  PLAN-6 V1.3), **dann** schreibt der Buddy ein **WARN-Log** und persistiert
  trotzdem — **kein** Fehler (das Risiko ist Display-Lesbarkeit, nicht
  Datenverlust).
- **Wenn** ein Pflichtfeld fehlt, eine `art` unbekannt ist, ein
  `kalender-read`-Slot kein/ein unbekanntes `kind` trägt (FAM-3), ein
  `schluessel` doppelt vorkommt oder ein Rename-Versuch (s. o.) vorliegt,
  **dann** HTTP 400 mit JSON-Fehler, **kein** 500, und es wird **nichts**
  geschrieben (Validierung **vor** Persistenz).

**Form↔Datei-Mapping (verbindlich — Multi-Sektion-Save):** Ein erfolgreicher PUT
schreibt die `slots`-Sektion **und** bereinigt die `default_petrantwortlichkeiten`-
Sektion (entfernt Einträge gelöschter Slots) **atomar in EINEM Write**. Das ist
genau der Multi-Sektion-Save, für den die API-first-Form gewählt wurde
(RAT-4-Kill-Kriterium erfüllt: zwei Sektionen müssen konsistent in einem Schreib-
vorgang fallen, was ein view-internes Einzelfeld-Save nicht leistet).

**Persistenz-Verhalten:**
- **Wenn** ein PUT erfolgreich validiert, **dann** wird die Konfig-Datei
  **atomar** geschrieben (kein Teilstand bei Absturz, kein 500 bei Bad-Input) und
  der Buddy übernimmt den neuen Stand ohne Prozess-Neustart (Reload,
  PLAN-32-Muster `admin/reload`).
- **Roundtrip-Garantie (testbares Requirement, Pflicht):** Nach einem
  erfolgreichen `PUT slot-modell=X` liefert ein anschließendes `load_config` /
  `GET slot-modell` denselben Stand X. Ein gelöschter Slot fehlt danach **auch**
  in `default_petrantwortlichkeiten` (Multi-Sektion-Konsistenz). Dieser Roundtrip
  inkl. Defaults-Bereinigung ist als Test Pflicht.

**Abgrenzung — Slot-CRUD JA, per-Slot-`cycle` NEIN (sauber trennen):**
- **In P2 (PLAN-37):** Slot-CRUD = Slot **anlegen**, **löschen** und bei
  bestehenden `art`/`icon`/`kind` (nicht `schluessel`) **ändern**.
- **NICHT in P2 — bleibt RAT-4-Defer (decisions/RAT-4-259):** der per-Slot-
  `cycle`-Filter, also eine familien-spezifische **Whitelist** „wer darf in
  *diesem* Slot stehen" (altes #259 / E-PLAN-8). PLAN-7 V1.3 **Toggle-All** gilt
  unverändert weiter: der Cycle iteriert über **alle** Personen der Registry
  (Erwachsene und Kinder), jede Person ist in jeden Petrantwortlichkeits-Slot
  zuweisbar; es gibt **keine** Slot-Whitelist. Diese per-Slot-`cycle`-
  Generalisierung ist die vertagte Sache — NICHT das Slot-CRUD.

**Auth:** PUBLIC / Netz-Trust (auth.md AUTH-6, `/api/v1/plan/*`), wie PLAN-36.

*Tickets:* #1126 (Refs #259)

## 10. Tests

### PLAN-29 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), reproduzierbar und **ohne Netz** — der Google-Kalender-Zugriff
wird durch eine kontrollierte Doppelung ersetzt. Mindest-Abdeckung: PLAN-3
(`?ansicht=klein` → 3 Spalten, keine Termin-Leiste) · PLAN-4 (Fenster beginnt
heute; `?ab=` schiebt den Anker) · PLAN-7/PLAN-8 (Klick-Cycle schreibt, erneuter
Abruf zeigt die Zuweisung) · PLAN-10 (erste Anzeige einer Woche belegt aus
Defaults; Fenster über zwei Wochen liest beide) · PLAN-12 (Event mit Kindername
→ Aktivitäts-Slot; ohne → Termin; child-named ohne Katalog-Keyword → Kind-Slot
trägt trotzdem ein Symbol, ist nie typlos) · PLAN-13 (child-named zeitgebundener
Einzel-Termin erscheint mit Uhrzeit in der Termin-Leiste UND im Kind-Slot, beide
mit derselben Event-`id`; child-named ganztägige Aktivität nur im Kind-Slot,
nicht in der Termin-Leiste) · PLAN-14 (Event über mehrere Tage → eine
Spanne) · PLAN-17/PLAN-19 (Rohantwort → normalisiertes Modell; Titel-Treffer
schlägt Creator-E-Mail; früherer Treffer gewinnt) · PLAN-18 (anlegen/ändern/
löschen rufen die richtige Operation) · PLAN-20 (fehlende Credentials → leeres
Lese-Ergebnis, View funktioniert) · PLAN-22/PLAN-23 (Termin-Schnittstelle
liefert Termine; ist der Plan-Buddy nicht erreichbar, ist die Schnittstelle
nicht erreichbar; PUT mit beginn+ende als Datumsstrings legt eine
Mehrtages-Ganztags-Spanne an; PUT mit beginn+ende als Datetimes legt einen
zeitgebundenen Termin an; datum als Alias für ganztägiges beginn bleibt
rückwärtskompatibel; fehlende oder widersprüchliche Felder antworten 400;
nach einem PUT liefert GET das Event mit korrektem beginn/ende/ganztags zurück)
· PLAN-28 (Reload-on-Read: nach einem Schreibvorgang
in plan.json liefern `_current_config()` und `_db()` beim nächsten Request den
neuen Stand ohne Service-Restart — DCOMP-2) · PLAN-30 (Lese-API liefert
Defaults bei leerer Woche, spiegelt PUTs, antwortet 400 bei ungültigem
`week_start`) · PLAN-31 (PUT /api/v1/plan/zuteilung: Pflichtfeld-400, ungültiger
Slot-400, unbekannte person_id-400, gültiger PUT schreibt und ist per GET
sichtbar) · PLAN-32 (PUT /api/v1/plan/admin/kalender: nicht-Loopback→403;
fehlendes/leeres kalender_id→400; gültiger PUT schreibt nur den
kalender_id-Schlüssel atomar, nächster Request liest die neue ID; Schreib-/
Parse-Fehler lässt den alten Snapshot stehen) · **PLAN-33** (Bulk-Termin-
Schnittstelle): Pre-Validate-Fehler bei mindestens einem Item → HTTP 400
mit kompletter `results`-Liste, **kein** Schreib-Versuch in Google
(PLAN-33.1); gemischter Erfolg → HTTP 200 mit `geschrieben < gesamt` und
korrekten `error_code`-Werten je Item (PLAN-33.2); Idempotenz: derselbe
`request_id` mit identischem `items_hash` liefert die gespeicherte
Antwort ohne zweiten Google-Call, mit abweichendem `items_hash` →
HTTP 409 (PLAN-33.5); Cap-Überschreitung (`len(items) > 30`) → HTTP 400
ohne Schreib-Versuch (PLAN-33.3); 429/403-Rate-Limit-Antworten des
Google-Stubs lösen den Exponential-Backoff aus (PLAN-33.6) — drei
Retries je Item, dann `error_code: calendar_rate_limit`, und
`Retry-After`-Header sticht die berechnete Wartezeit; Token-Cache: ein
Bulk-Aufruf macht **einen** Token-Refresh, nicht N (PLAN-33.4)
· **PLAN-34** (Admin-API Aktivitäts-Katalog): GET liefert den
CONFIG-4-Fallback bei fehlender `aktivitaeten`-Sektion in `plan.json`;
GET spiegelt POST-Zustand nach dem nächsten Aufruf (Reload-on-Read);
POST mit doppelter `art` → 409, POST mit fehlendem/leerem Pflichtfeld
→ 400, POST aus nicht-Loopback → 403; DELETE auf unbekannte `art` →
404; atomares Schreiben — bei Schreib-/Parse-Fehler bleibt der alte
Snapshot byte-gleich; ein Test belegt: ein neuer Eintrag (Keyword
+ ARASAAC-`id`) wird beim nächsten Render eines Kalender-Events mit
diesem Keyword im Titel zum Aktivitäts-Slot mit ARASAAC-Piktogramm.

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

### E-PLAN-5 — Layout-Struktur 1:1 aus dem Wireframe-Handoff; Icon-Quelle wechselt in V1.2 auf ARASAAC
*Datum:* 2026-05-22 · Präzisierung 2026-06-09 (Werft #578)

Die **Layout-Struktur** beider Stufen wird unverändert aus dem Wireframe-Handoff
„PlanBuddy Kids" übernommen — in XBuddy **nicht** neu gestaltet. Das Handoff-Paket
liefert Template (`plan_kinder.html`) und Tokens (`tokens-kids.css`) als Artefakte.
Was in XBuddy neu entsteht, ist die Anbindung an Registry, Zugangsdaten-Speicher,
Kalender und URL-Konvention — nicht die Layout-Aufteilung. Die Struktur ist
bereits gegen den Design-Handoff abgenommen; eine Neugestaltung wäre verworfene
Arbeit.

**Präzisierung 2026-06-09 (Werft #578, Gate B):** „1:1" meint die **Layout-
Struktur** (Schedule-Rail-Aufteilung, Day-Chips, Activity-Chip-Pille, Termin-
Leiste, Toddler-Stempel-Geometrie, Font-Strang Caveat/Patrick Hand, Cream-
Hintergrund, harte Tinten-Schatten). **Die Icon-Quelle** wechselt in V1.2 von
handgezeichneten Wireframe-SVG-Macros auf **ARASAAC-Piktogramme** — sowohl im
Aktivitäts-Katalog (PLAN-12) als auch in der Schedule-Rail (PLAN-6) als auch in
der Termin-Leiste (PLAN-13, Fallback `kalender` 3071). Das ist **eine** Icon-
Quelle, nicht zwei (CLAUDE.md §6: kein Fakt zweimal).

Der **Stilbruch** zwischen Wireframe-Cards (monochrome Tinte, handgezeichnet)
und bunten ARASAAC-Piktogrammen ist **akzeptiert**: Kinder erkennen bunte
Piktogramme schneller, Aktivitäts-Identität wird durch Farbe getragen, Familie
nutzt den PAS-Skill (`plan-aktivitaeten-setzen.md`) zum Erweitern. PLAN-27
(Wireframe-Look) gilt nach V1.2 nur noch für das **Drumherum** (Cards,
Pille-Rahmen, Day-Chips, Fonts, Schatten) — nicht mehr für die Icons selbst.

**Verworfen 2026-06-09:** Wireframe-SVG-Macros für die Icons beizubehalten
(Stil-Konsistenz mit dem Drumherum). Hätte zwei Folgen: (1) PAS-Skill wäre
nutzlos für visuelles Hinzufügen — Familie müsste die Spec ändern, nicht
nur den Katalog; (2) ICONS-7-Pfad wäre nicht der eine Pfad, sondern ein
Spezial-Pfad nur für „Aktivitäten" — Stilbruch innerhalb der View
(Aktivitäts-Chip vs. Schedule-Rail) wäre ohnehin da.

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
zwei Kinder, abendliche Bringen-und-Ins-Bett-Slots, eine spezifische Liste
von Kind-Aktivitäten. Diese familienspezifischen Inhalte leben absichtlich
als Code-Konstanten: die Personen-Auflösung über Titel-Treffer in
`plan/kalender.py` (PLAN-19) und die abendliche Slot-Sequenz hinter
E-PLAN-2. (Echte Morgen-/Abendablauf-*Routinen* — Reihenfolge, Abhaken,
Zeitlogik — sind **nicht** Plan-Buddy, sondern der Routine-Buddy
(`routine.md`, #335); der Plan-Buddy trägt nur die Wochenübersicht und ihre
kleine Variante.)

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

**Korrektur 2026-06-08 — Aktivitäts-Katalog ist Daten, nicht Code.** Der
Aktivitäts-Katalog (`AKTIVITAETEN` + `_ART_ZU_ICON` in `plan/aktivitaeten.py`)
war ursprünglich Teil dieser Code-Liste. Er ist nach `plan.json` (Sektion
`aktivitaeten`, siehe PLAN-12 und PLAN-28) ausgelagert worden, weil die zwei
gekoppelten Strukturen den Drift-Trigger schon **innerhalb einer einzigen
Familie** erfüllten: `plan/tests/test_plan.py:940` überspringt fehlende
Icon-Zuordnungen stillschweigend, ein Familien-Edit nur in `AKTIVITAETEN`
blieb lautlos inkonsistent zu `_ART_ZU_ICON`. Code-Default in
`plan/aktivitaeten.py` bleibt als CONFIG-4-Fallback (V1-Familie läuft ohne
Migration). Hinweis an automatische Reviews: ein Befund „Aktivitäts-Katalog
ist familienspezifischer Code" bezieht sich auf den Stand vor 2026-06-08;
nach der Umlagerung ist der Katalog Daten und allein **kein** Trigger für
weitere Externalisierung. Begründung im Detail:
`brainstorm/berater-runde/20260608-RATIFIZIERT-wd-e-plan-8-familien-katalog.md`.
Slot-Sequenz und PLAN-19-Personen-Auflösung bleiben Code.

**Verworfen:** jetzt eine Plan-Engine mit Aktivitäts-Katalog-DSL und
Ablauf-Templates bauen. Wäre exakt die Vorrats-Generalisierung, die §6
verbietet — und würde die V1-Liefermenge in eine offene Architektur-Frage
zurückwerfen. (Die `plan.json`-Umlagerung des Aktivitäts-Katalogs ist
**keine** DSL und **keine** Engine: dieselben vier Felder
`art`/`label`/`keywords`/`icon` wie heute, nur als JSON-Liste statt als zwei
Python-Konstanten.)

Diese Entscheidung ergänzt E-PLAN-2: dort ist die **Slot-Struktur** Daten
(sieben Slots als Config), hier sind die **Familien-Routinen** Code. Die
Linie liegt bewusst tief — wer den Plan inhaltlich ändert, fasst Python
an. Wer einen Slot dazunimmt, fasst die Config an.
