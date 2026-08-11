# Routine-Buddy — Spec     (ID-Präfix: ROUTINE)

> Status: V1 · Refs #335

## Problem & North-Star-Bezug

Morgens treibt das Elternteil das Kind durch die immer gleiche Abfolge: Pipi,
anziehen, Zähne putzen, Brotdose, Schuhe, los. Jeder Schritt ist ein „Hast du
schon …?". Der Routine-Buddy gibt dem Kind die Morgenroutine **als eigene
Checkliste** — es sieht selbst, was noch offen ist, hakt selbst ab, und sieht
auf einer ablaufenden Uhr selbst, **wann es sich anziehen** und **wann es
losgehen** muss. Das verschiebt das Antreiben vom Elternteil zum Kind (North
Star, `constitution.md`) und gibt dem Kind in einem klaren Rahmen die Kontrolle
über seinen eigenen Morgen.

Der Routine-Buddy ist eine eigenständige XBuddy-**App** mit einer Display-View
(APP-1). Als App **besitzt** er seine Daten (die Routine-Punkte und Zeiten der
Familie) und seine Funktion (die ablaufende Uhr / Zeitberechnung) und stellt
das Ergebnis über die View bereit.

**V1-Scope:** Single-View `morgen` als Routine-Checkliste · Punkte ausschließlich
aus der `default`-Liste der Config · Tap zum Abhaken (täglicher Reset) ·
ablaufende Uhr mit „in X: anziehen" / „in Y: losgehen" als rein **visuelle**
Indikation (kein Ton, kein Push — Nicht-invasiv, `constitution.md` QA-5) ·
injizierbare Uhr für deterministische Tests · dynamische Punkt-Liste bis 8 ohne
Scroll (ROUTINE-19) · textlose, rechtsbündige Zeit-Referenz-Balken
(config-schaltbar, ROUTINE-13) · ARASAAC-Piktogramm je Punkt über die geteilte
Icon-Plattform · eigener Service · Boxen im WetterBuddy-Card-Stil · rendert gegen
den geteilten Design-Token-Strang unter `/display/_shared/design/` (DTOK-1..5;
seit #323 live).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): die Slots `einmalig`
und `bedingt` im Datenmodell **befüllen** (OPEN-ROUTINE-A) · Schreib-API für
Routine-PUNKTE (OPEN-ROUTINE-B Teil 2, #354 — die Zeiten-Schreib-API ist mit
#343 in Scope, ROUTINE-14) · Sonnencreme-Injektion aus dem Wetter-Buddy
(OPEN-ROUTINE-C) · Mülltonne-Injektion aus dem Plan-Buddy (OPEN-ROUTINE-D) ·
Mitwachsen-Stufen über `morgen` hinaus · Controller-Trigger / Erreichbarkeit
jenseits Dauer-Kiosk.

## 1. Die App & ihre View

### ROUTINE-1 — Routine-Buddy ist eine App mit eigenem Besitz
Der Routine-Buddy ist die XBuddy-App mit dem Buddy-Slug `routine`. Er besitzt
seine **Daten** (die Routine-Punkte und die Zeit-Konfiguration, ROUTINE-12),
seine **Funktion** (die ablaufende Uhr / Zeitberechnung, Abschnitt 4) und stellt
das Ergebnis über seine **Display-View** bereit (APP-1). Die display-only-V1
(#335) exponierte **keine** API; der Zeiten-Schreibpfad (#343, ROUTINE-14,
RAT-12) fügt als erste Ausnahme `PUT /api/v1/routine/config` hinzu (bindendes
Requirement, gebaut in #343, E-ROUTINE-5). Cross-Buddy-Konsum bleibt aus
(E-ROUTINE-6).

*Tickets:* #335

### ROUTINE-2 — Single-Page-View `morgen`
Die View liegt unter `/display/routine/morgen` (BUD-1, URL-2:
`/display/<slug>/<view>`, kein Verb im Pfad). Sie ist **eine einzige Canvas** —
links/oben die Routine-Checkliste (Abschnitt 3), prominent die ablaufende Uhr
(Abschnitt 4). Kein Routing, kein Tab, keine Settings-Seite. Statische Assets
unter `/display/routine/static/<asset>` (URL-13).

**Wenn** die View aufgerufen wird, **dann** rendert sie die heutigen
Routine-Punkte mit ihrem aktuellen Abhak-Zustand und die ablaufende Uhr für die
heutige Abfahrtszeit.
*Test-Implikation:* GET `/display/routine/morgen` rendert die Default-Punkte und
einen Uhr-Block; kein zweiter Pfad, kein Tab im Markup.

*Tickets:* #335

### ROUTINE-3 — Touch-Display, genau eine Interaktion: Abhaken
Die View ist für ein Touch-/Kiosk-Display gebaut. Die **einzige** Bedien-
Affordance ist das Tippen eines Routine-Punktes, das ihn ab- bzw. wieder
aufhakt (ROUTINE-7). Jeder Punkt trägt dafür einen **großen Abhak-Knopf**, der
im offenen Zustand klar als antippbar erkennbar ist (deutliche Tipp-Affordanz,
große Trefferfläche) und beim Antippen **grün** wird (Häkchen). Kein Hover, kein
Aufklappen, keine weiteren Bedien-Elemente.
V1 nimmt einen Dauer-Kiosk an; wie das Kind die View sonst erreicht
(Controller-Trigger), ist spätere Integration, nicht Teil dieser Spec.

**Wenn** das Kind einen Punkt tippt, **dann** ändert sich nur dessen
Abhak-Zustand; **wenn** es irgendwo sonst tippt, **dann** passiert nichts.
*Test-Implikation:* nur die Punkt-Elemente tragen einen Tap-Handler; die Uhr und
der Hintergrund sind nicht interaktiv.

*Tickets:* #335

## 2. Datenmodell der Routine-Punkte

### ROUTINE-4 — Ein Routine-Punkt und seine Herkunft
Ein **Routine-Punkt** (Item) hat die Felder: stabile `id`, `label` (kurzer
Text), `piktogramm` (ARASAAC-Referenz, ROUTINE-10), Abhak-Zustand **für heute**
(ROUTINE-6) und eine **Herkunft** `quelle ∈ {default, einmalig, bedingt}`:

- **`default`** — wiederkehrender Punkt aus der Config (ROUTINE-12); steht jeden
  Tag auf der Liste.
- **`einmalig`** — nur für den **heutigen** Tag von außen reingelegt (z. B.
  „Spielzeug für Kindi"); morgen wieder weg.
- **`bedingt`** — von einer **anderen App** injiziert (Sonnencreme ← Wetter-Buddy,
  Mülltonne ← Plan-Buddy), abhängig von einer Bedingung des Tages.

**Display-V1 füllte ausschließlich `default`.** **V1.1 (#354) befüllt zusätzlich
`einmalig`** über den Eltern-Chat-Schreibpfad (`routine-punkte-setzen.md` RPS,
`POST /api/v1/routine/items`). Der Slot **`bedingt`** bleibt vorgesehen, aber
ungebaut (Cross-Buddy-Injektion, OPEN-ROUTINE-C/D). Das Modell trägt die `quelle`
von Anfang an, damit dieser Schreib- bzw. Injektions-Pfad keine
Datenmodell-Migration erzwingt.

*Test-Implikation:* das interne Item-Modell akzeptiert alle drei `quelle`-Werte;
der V1-Builder erzeugt `quelle=default`-Items aus der Config, der V1.1-Items-Ingest
zusätzlich `quelle=einmalig`-Items.

*Tickets:* #335, #354

### ROUTINE-5 — Stabile, herkunfts-eindeutige Item-IDs
Jeder Punkt trägt eine stabile `id` (IDENT-Konvention für stabile IDs). `default`-
IDs stammen aus der Config. **`einmalig`-IDs tragen das Quell-Präfix `einmalig:`**
(z. B. `einmalig:turnbeutel`, #354) — sie kollidieren so nie mit `default`-IDs und
sind als Tages-Punkt erkennbar. `bedingt`-IDs (ungebaut) folgen demselben
Präfix-Muster (`bedingt:…`), Detail offen bis OPEN-ROUTINE-C/D.

*Test-Implikation:* zwei `default`-Punkte haben nie dieselbe `id`; eine
`einmalig:`-ID kollidiert nie mit einer `default`-ID; der Abhak-Zustand (ROUTINE-6)
wird je `id` geführt.

*Tickets:* #335

### ROUTINE-6 — Abhak-Zustand gilt für heute und setzt täglich zurück
Der Abgehakt-Zustand eines Punktes gilt **für den heutigen Tag**. Mit dem
Tageswechsel (lokale Familien-Zeitzone) startet jeder Punkt wieder
**nicht-abgehakt** — die Morgenroutine ist jeden Morgen neu zu erledigen.

**`einmalig`-Punkte verfallen am Tagesende automatisch** (#354): Ein
`einmalig`-Punkt (ROUTINE-4, per Eltern-Chat für heute angelegt) ist mit dem
Tageswechsel **weg** — er liegt im flüchtigen Tages-State (ROUTINE-8), nicht in der
`default`-Config, und wird beim Tageswechsel mit dem Abhak-Zustand verworfen.
`default`-Punkte bleiben.

**Wenn** ein Punkt heute abgehakt wurde und der Tag wechselt, **dann** ist er am
nächsten Tag wieder offen; **wenn** ein `einmalig`-Punkt angelegt wurde und der Tag
wechselt, **dann** ist er am nächsten Tag **nicht mehr da**.
*Test-Implikation:* mit injizierter Uhr (ROUTINE-9) über eine Tagesgrenze hinweg
ist der zuvor abgehakte Punkt im neuen Tag wieder offen.

*Tickets:* #335

### ROUTINE-7 — Abhaken per Tap, persistiert über den Reload
Ein Tap auf einen Punkt schaltet seinen heutigen Abhak-Zustand um (offen ↔
abgehakt). Der Zustand überlebt einen Reload der View innerhalb desselben Tages,
liegt also in der App-eigenen Datenhaltung (ROUTINE-8), nicht nur im Browser.

**Wenn** das Kind einen Punkt abhakt und die View neu lädt, **dann** ist der
Punkt weiter abgehakt (solange derselbe Tag).
*Test-Implikation:* Tap → Persistenz → erneuter View-Render zeigt den Punkt
abgehakt; nach Tageswechsel offen (ROUTINE-6).

*Tickets:* #335

### ROUTINE-8 — App-eigene Datenhaltung des Abhak-Zustands
Der heutige Abhak-Zustand liegt in der App-eigenen Datenhaltung neben dem Code,
je Instanz separat, per `.gitignore` ausgeschlossen (Trennung Domänendaten ⟂
Runtime-Config: BUD-2a).
Fehlt sie beim Start, wird sie leer angelegt. Sie hält **nur** den flüchtigen
Tageszustand (welche Punkte heute abgehakt sind) — die Punkt-**Definitionen**
kommen aus der Config (ROUTINE-12); keine doppelte Wahrheit. Form (SQLite vs.
schlanke JSON-Datei) ist Implementierungswahl; entscheidend ist die
Reload-Persistenz (ROUTINE-7) und der tägliche Reset (ROUTINE-6).

Test-Anker: `routine/tests/test_items_api.py::test_AC1_get_items_einmalig_gefuellt`

*Tickets:* #335

## 3. Routine-Checkliste (Anzeige)

### ROUTINE-9 — Ablaufende Uhr: „anziehen" und „losgehen", injizierbares Now
Die View zeigt prominent eine **ablaufende Uhr** mit zwei Ziel-Zeitpunkten des
heutigen Tages:

- **losgehen** = `abfahrtszeit` (Config, je Wochentag möglich, ROUTINE-12).
- **anziehen** = `abfahrtszeit − anzieh_vorlauf_min` (Default 8 Min). Der
  Vorlauf ist ein **Tuning-Wert** und lebt als Config-Schlüssel, **nicht** als
  Code-Konstante (CLAUDE.md §6).

Die Uhr zeigt die verbleibende Zeit als „in X: anziehen" und „in Y: losgehen".
Sie ist **rein visuell** — **kein Ton, kein Push, keine Vibration**
(Nicht-invasiv, `constitution.md` QA-5, E-ROUTINE-3).

Die aktuelle Zeit (`now`) **muss injizierbar** sein — die Uhr-/Zeit-Logik nimmt
ihr `now` von einer austauschbaren Quelle, nicht aus einem direkten
Wall-Clock-Aufruf tief im Code. (Begründung: dieselbe Test-Reibung wie beim
Wetter-Buddy mit Zeit-abhängiger Logik; ohne injizierbare Uhr ist die
Restzeit-Anzeige nicht deterministisch testbar.)

**Wenn** `now` vor `anziehen` liegt, **dann** zeigt die Uhr beide Restzeiten
positiv; **wenn** `now` zwischen `anziehen` und `losgehen` liegt, **dann** ist
„anziehen" erreicht (Anzeige „jetzt") und „losgehen" noch positiv; **wenn** `now`
nach `losgehen` liegt, **dann** sind beide überfällig.

**Darstellung (Design-Evolution aus echtem Display-Test, #335):** die Uhr ist ein
**linearer Zeitstrahl** (kein Ring) — als **VERTIKALER Balken** orientiert: oben =
früh (**aufstehen 07:00**), unten = spät (**losgehen 08:30**), Zeit fließt nach
unten. Der verstrichene Teil füllt **von oben** (`height` ∝ verstrichener Anteil),
ein „jetzt"-Marker liegt als waagerechter Riegel quer über dem Balken an der
aktuellen Position. Der Balken nutzt **möglichst viel Panel-Höhe**.
Die Tagespunkte — aufstehen, anziehen, losgehen — sitzen als **Piktogramme** an
ihrer **proportionalen Vertikal-Position** (`top:%` nach Zeit) **neben** dem
Balken, jeweils mit **Uhrzeit** (z. B. 07:00 / 08:22 / 08:30). Die Event-Icons
stehen **abwechselnd auf gegenüberliegenden Seiten** des Balkens (aufstehen
**links**, anziehen **rechts**, losgehen **links**). **Keine** separaten
Meilenstein-Kästen (verworfen, kein Mehrwert).
Die Uhrzeit-Labels dürfen **nicht in andere Elemente ragen** — bei engem Abstand
zwischen zwei Punkten (z. B. anziehen/losgehen nur 8 Min auseinander) garantiert
die **Seiten-Alternation** (adjazente Events nie auf derselben Seite) zusammen mit
der vertikalen Länge die Überlappungsfreiheit — **nicht** durch Icon-Verkleinerung;
Kiosk-Lesbarkeit aus Distanz hat Vorrang. (Diese vertikale Achse mit
alternierenden Event-Seiten löst die ältere horizontale variant-f-Orientierung
des Zeitstrahls und die Label-Staffelung AC-FIX3 ab — Layout-Rework aus dem
1920×1080-Display-Test, #335.)
`aufstehen` kommt direkt aus dem Config-Schlüssel `aufstehzeit` (Default `'07:00'`) — **nicht** von anziehen
abgeleitet (AC-FIX1, #335). Die proportionale
Vertikal-Position von `anziehen` (`anziehen_pct` = (anziehen−aufstehen)/(losgehen−aufstehen))
liefert die Uhr-Logik; aufstehen=0 %/losgehen=100 % sind die Fenster-Ränder.

**Fehlender Tag in der `aufstehzeit`-Map → Default `'07:00'` (AC-FIX4, #364):**
Ist `aufstehzeit` als Wochentag→Zeit-Map gegeben (ROUTINE-12) und der **heutige
Tag fehlt** (z. B. leeres Wochenende), fällt `aufstehen` auf den
Pro-Schlüssel-**Default `'07:00'`** zurück — man steht immer auf, die Map liefert
für `aufstehen` nie `None`. Die View rendert dann **wie an einem normalen
Wochentag** (am Wochenende ruft ohnehin niemand die Routine auf; tut es doch
jemand, ist ein Wochentag-Bild harmlos). Das vermeidet den `TypeError` aus
`(losgehen − aufstehen)`/`(now − aufstehen)`, den ein leeres Wochenende in der
`aufstehzeit`-Map zusammen mit einer Fixwert-`abfahrtszeit` (gilt jeden Tag →
`losgehen` gesetzt) sonst auslöst (#364, Watchdog #335). Die
`abfahrtszeit`-Map-Semantik bleibt unberührt (ROUTINE-12, „leerer Tag = kein
Kindi").

*Test-Implikation:* mit injiziertem `now` an je einem Punkt vor `anziehen`,
zwischen den Zeiten und nach `losgehen` liefert die Zeit-Logik die erwarteten
Restzeiten/Phasen — ohne echte Wall-Clock.

**Live-Tick (#824, 2026-06-15):** Solange die View geöffnet ist, läuft der
Zeitstrahl **clientseitig weiter** — ohne Page-Reload. **Wenn** die View
mindestens eine Minute offen ist, **dann** hat sich die Position des „jetzt"-
Markers (`jetzt_pct`) und die Höhe des Verstrichen-Bandes (`elapsed_pct`) mindestens
einmal sichtbar fortgeschrieben. **Quelle der Wahrheit bleibt der Server-Render**
beim Page-Load (`aufstehen`/`anziehen`/`losgehen` als absolute Zeitstempel im
Template). Die clientseitige Fortschreibung interpoliert nur den Zeitablauf
zwischen den vom Server bekannten Ankern. **Server-Zeit-Drift:** Server liefert
`server_now` (ISO-Timestamp) zusätzlich; Client berechnet einmalig
`offset = server_now − Date.now()` und nutzt `Date.now() + offset` als
View-Now — Tablets mit ungetretener Uhr verschieben den Render nicht.
**Polling-Intervall:** ≤ 60 s (Tuning-Wert, V1 darf 60 s im Code-Default
hardcoden; ein zweites Vorkommen mit unterschiedlichem Intervall externalisiert
in die Config-Datei nach CLAUDE.md §6).

**Bewegung des Jetzt-Markers — kontinuierlich, nicht rastend (#824, 2026-06-15):**
Der „jetzt"-Marker (`.timeline-now`) **gleitet sichtbar kontinuierlich** zwischen
zwei Polling-Ticks — nicht in Sprüngen am 5-Min-Raster. Mechanik: CSS-Transition
(`transition: top <poll-intervall> linear`) lässt den Browser die lineare
Interpolation übernehmen; alternativ JS-`requestAnimationFrame`-Loop mit
`top = jetzt_pct(view_now)` pro Frame. Die 5-Min-Striche (siehe nächster Absatz)
sind ausschließlich **Skala für die Restzeit-Lesung des Kindes**, kein
Marker-Raster — der Marker steht zwischen den Strichen genauso oft wie auf
ihnen. *Test-Implikation:* mit injizierter Wall-Clock-Verschiebung um 30 s
zwischen zwei Tick-Render zeigt der Computed-Style von `.timeline-now` eine
`top`-Position, die **zwischen** zwei 5-Min-Strich-Positionen liegt — kein Snap.

**5-Min-Marker am Balken (#824, 2026-06-15):** Der vertikale Balken trägt
**visuelle 5-Minuten-Striche** als Skalen-Hilfe. **Wenn** das Zeitfenster
`aufstehen → losgehen` z. B. 90 Min umfasst, **dann** sind am Balken 18
äquidistante kurze Striche sichtbar (90/5). Die Striche sind feiner als die
Pin-Zeit-Labels und der Jetzt-Marker, damit Letztere weiterhin dominieren
(Kiosk-Lesbarkeit ROUTINE-11). **Daten-getrieben, nicht hartcodiert:** Schrittweite
kommt aus `zeitfenster_min` und einer **Skalen-Schrittweite** (Default 5 Min;
ein zweites Vorkommen mit anderer Schrittweite externalisiert nach
CLAUDE.md §6). **Balken-Breite:** keine harte px-Vorgabe (DTOK-5); die Spec
verlangt: „Track-Breite gewährleistet, dass 5-Min-Striche aus 1,5 m Abstand
erkennbar sind" (Akzeptanz: Sichtprobe am 1920×1080-Kiosk; Gate-B-Probe 2026-06-15
hat 56 px als Empfehlung etabliert). *Test-Implikation:* der View-Render bei
`zeitfenster_min = 90` zeigt 18 Strich-Elemente am Balken (DOM-Assertion).

**Zonen-Farbschema des Verstrichen-Bandes (#824, 2026-06-15):** Das
Verstrichen-Band (`.timeline-elapsed`) nimmt seine Farbe **aus der Position
im Tagesfenster**, sodass der Farbwechsel im verstrichenen Teil selbst die
Zonen-Grenze sichtbar macht. Track-Hintergrund (unverstrichener Teil) bleibt
**neutral** — keine Zonen-Vorschau dahinter; der Track ist „leerer Raum,
der noch nicht durchlaufen wurde".

**Drei Zonen** entlang der Vertikalen (greifen auf das Verstrichen-Band, nicht
auf den Track):

- **0 % bis `anziehen_pct`:** **grün** (Token `--success`) — Zeit reicht.
- **`anziehen_pct` bis 100 %:** **orange** (Token `--warning`) — Restzeit
  knapp, Eltern-Signal „jetzt wird's eng".
- **jenseits 100 %:** **rot** (Token `--danger`) — überfällig.

**Wenn** das Verstrichen-Band die Zonen-Grenze überschreitet, **dann** zeigt
das Band an der Grenze einen sichtbaren Farbwechsel (harter Stop, kein
Gradient-Übergang über die Grenze hinweg). **Wenn** das Verstrichen-Band die
Grenze nicht überschritten hat, **dann** ist es einfarbig grün — die orange
Zone wird im Bild **nicht vorab angedeutet** (der unverstrichene Track-Bereich
bleibt neutral).

*Test-Implikation:* gefüllter Balken mit `elapsed_pct = 0,95` und
`anziehen_pct = 0,908` zeigt am `.timeline-elapsed` einen grünen Bereich
0–90,8 % und orange 90,8–95 %; der Track-Hintergrund (`.timeline-track`)
bleibt unverändert. DOM-/Computed-Style-Assertion auf die CSS-Custom-Property
`--anziehen-stop` und CSS-Token-Bezug (kein Hex). `--success` / `--warning` /
`--danger` existieren im geteilten Token-Strang (`conventions/design-tokens.md`
DTOK-1) und werden referenziert, nicht kopiert (DTOK-3).

**Implementierungs-Hinweis (load-bearing — CSS-Bug vermeiden):** Der
`linear-gradient` sitzt auf `.timeline-elapsed`, dessen Höhe `elapsed_pct` der
**Track-Höhe** entspricht. CSS-Gradient-Stops sind relativ zur **Element-Höhe**,
nicht zur Container-Höhe — daher muss `--anziehen-stop` server-seitig
**umgerechnet** werden auf die Element-Höhe:

```python
if elapsed_pct <= anziehen_pct:
    anziehen_stop_rel = 110.0   # > 100 %, Element ist komplett grün
else:
    anziehen_stop_rel = (anziehen_pct / elapsed_pct) * 100
```

Template setzt im Inline-Style:
`style="height: {elapsed_pct}%; --anziehen-stop: {anziehen_stop_rel}%;"`. So
liegt der Farbwechsel **immer an der korrekten Track-Position** `anziehen_pct`,
egal wie hoch `elapsed_pct` ist. Bei `elapsed_pct ≤ anziehen_pct` bleibt das
Element komplett grün; bei `elapsed_pct > anziehen_pct` zeigt es grün bis zur
Anziehen-Position und orange bis zum Element-Ende. Der rote Bereich erscheint
nur, wenn `elapsed_pct > 100 %` möglich ist (heute clamp auf 100 % in
`uhr.py`).

*Tickets:* #335 · #364 (Fallback fehlender Map-Tag, AC-FIX4) · #824 (Live-Tick + 5-Min-Skala + Zonen-Farbschema)

### ROUTINE-10 — Piktogramm je Punkt über die geteilte Icon-Plattform
Jeder Routine-Punkt trägt ein **ARASAAC-Piktogramm**, bezogen **über die
zentrale Icon-Plattform** — read-only unter der geteilten URL
`/display/_shared/icons/arasaac/<id>.png` (`icons.md` ICONS-5) —, **kein**
buddy-eigener ARASAAC-Bezug (sonst zweiter Icon-Pfad, CLAUDE.md §6 / Lego,
gleiche Regel wie WETTER-18). **Kein Emoji.** Die Punkt-Definition in der Config
bildet auf eine numerische ARASAAC-ID ab. Die Lizenz-/NC-Frage liegt zentral in
`icons.md` ICONS-6 und wird hier nur referenziert, nicht erneut entschieden.

*Test-Implikation:* ein Punkt rendert sein Piktogramm über den
`/display/_shared/`-Pfad; kein buddy-lokaler ARASAAC-Download im Routine-Code.

*Tickets:* #335

### ROUTINE-11 — Raumfüllende, lesbare Darstellung; Stil aus dem Design-Strang
Die Punkte und die Uhr **nutzen den vorhandenen Platz** (Kiosk-Fläche gut
gefüllt, gute Lesbarkeit aus Distanz). Der visuelle Stil bindet an den
**geteilten Design-Token-Strang** unter `/display/_shared/design/tokens.css`
(`conventions/design-tokens.md`, DTOK-1/DTOK-2) und **referenziert** ihn, statt
ihn zu kopieren (DTOK-3). **Keine hartcodierten Farben/Maße im Buddy-CSS**
(DTOK-5); alle Stilwerte als Token, ggf. stufen-abhängig (DTOK-4). Der Strang ist
seit #323 (2026-06-05) live. **Boxen/Karten übernehmen die bestehende
Buddy-Card-Optik** des WetterBuddys (`wetter/static/wetter.css` `.card`/`.card-label`),
damit der Routine-Buddy nicht „neu" aussieht (E-ROUTINE-10) — gleiche Tokens
allein garantieren keine gleiche Optik. Konkrete Maße folgen dem Gate-B-Artefakt
`variant-f`.

*Tickets:* #335

### ROUTINE-19 — Dynamische Punkt-Liste, V1 bis zu 8 Punkte, ohne Scroll
Die Liste der Routine-Punkte ist **dynamisch** — ihre Länge folgt den Daten
(ROUTINE-4 / ROUTINE-12), nicht einer festen Zahl. V1 legt eine **Obergrenze von
8 Punkten** fest. Das Layout muss **jede Anzahl von 1 bis 8 ohne Scrollen** auf
dem Display darstellen: die Karten skalieren in der Höhe mit der Anzahl, bleiben
dabei aber groß genug für eine sichere Touch-Trefferfläche des Abhak-Knopfs
(ROUTINE-3).

**Das Piktogramm einer Routine-Karte skaliert mit der Karten-Höhe** und nutzt
den vorhandenen Platz (ROUTINE-11): wenn die Karten bei wenigen Punkten höher
werden, wächst das Piktogramm sichtbar mit; bei 8 Punkten bleibt es bei der
Untergrenze. CSS-mechanisch über `clamp()` mit `aspect-ratio: 1` auf
`.card-pikto` (Untergrenze ≈ 60 px für die 8-Punkte-Vollbesetzung, Obergrenze
so, dass die Anforderung des Beschriftungs-Schutzes (s. u.) gewahrt bleibt).
**Die Beschriftung (`.card-item-label`) darf vom Piktogramm nicht über den Rand
der Karte gedrückt werden**: bei typischen 1–2-Wort-Labels in `fs-28` bleibt die
Beschriftung einzeilig, ohne Umbruch und ohne den Card-Innenabstand zur Karte
rechts (Check-Knopf) zu unterschreiten. Implementiert wird diese Grenze als
`max-width` des Piktogramms relativ zur Karten-Breite **oder** als
`min-width` der Label-Spalte — das CSS wählt die Variante, die mit Typografie
und Card-Breite zusammenpasst. Die Skalierungsregel gilt **analog** für die
Zeitstrahl-Pin-Piktogramme (`.pin-pikto`) gegenüber der vertikalen
Section-Höhe (ROUTINE-9), mit dem entsprechenden Schutz vor Kollision der
Pin-Time-Beschriftung.

**Wenn** die Config 8 Punkte enthält, **dann** sind alle 8 gleichzeitig sichtbar
(kein Scroll) und die Piktogramme zeigen die Untergrenze; **wenn** sie 3
enthält, **dann** füllen 3 größere Karten den Raum und die Piktogramme wachsen
sichtbar, ohne dass die Beschriftung umbricht oder den Rand berührt.
*Test-Implikation:* der View-Render mit 8 `default`-Punkten erzeugt 8 Karten und
keinen Scroll-Container; die Kartenhöhe ist eine Funktion der Anzahl. Eine
visuelle Sichtprobe bei 3 Punkten + langem Label (≥ 12 Zeichen) zeigt das
Piktogramm größer als bei 8 Punkten, ohne dass das Label umbricht.
*(Layout-Probe für 8 am echten Display ist Impl-Feinschliff.)*

*Tickets:* #335 · #665 (Piktogramm-Skalierung + Beschriftungs-Schutz)

## 4. Zeit-Referenzen (Gate B gewählt, config-schaltbar)

### ROUTINE-13 — Kindgerechte Zeit-Referenzen (Gate B gewählt)
Damit ein nicht-uhr-lesendes Kind die Dauer greifen kann, blendet die View
**unterhalb des (vertikalen) Zeitstrahl-Blocks** eine `zeitref-zone` mit
**textlosen Referenz-Balken** ein: ein Balken, dessen Breite proportional zu
30 Min skaliert, mit dem „Sendung mit der Maus"-Piktogramm daneben, und ein
Balken für 3 Min mit dem Zähneputzen-Piktogramm. Die Balken sind horizontale
`width:%`-Elemente — sie teilen keinen gemeinsamen px/min-Maßstab mit dem
vertikalen Hauptstrahl. So liest das Kind die Referenz als Dauer-Ankerpunkt
(„so lange wie einmal Sendung mit der Maus"). **Kein erklärender Text**, nur
Balken + Bild. (#335)

**Gate B (2026-06-05): gewählt und Teil des V1-Designs** (variant-f). Die
Referenz bleibt **config-schaltbar** (`zeit_referenzen`, ROUTINE-12: an/aus +
Paare als Daten, kein Code); ob sie am echten Kiosk dauerhaft an bleibt, ist
eine spätere Tuning-Frage, kein V1-Blocker.

*Tickets:* #335

## 5. API-Schnittstellen

### ROUTINE-14 — Schreib-API (Zeiten) als bindendes Requirement; übrige Schnittstellen pro Konsument
Der Routine-Buddy konsumiert keine fremde Schnittstelle (E-ROUTINE-6) und
exponiert nur, wofür ein konkreter Konsument existiert (BUD-1b „nur wenn"). Der
**Eltern-Chat ist der konkrete Konsument** der Schreib-API für die Zeiten
(OPEN-ROUTINE-B Teil 1, #343, entblockt durch RAT-12) — dieser eine Endpunkt ist
damit ein **bindendes Requirement** (RAT-11-Überführung Skizze→bindend), nicht
mehr nur entworfen. **Implementierungsstand: gebaut (#343)**:

- **`PUT /api/v1/routine/config` — Zeiten setzen (#343, bindend; gebaut in #343).**
  Eigener API-Pfad `/api/v1/routine/<resource>` (BUD-1b). Die Implementierung
  ergänzt die URL-14-Routing-Zeile (`/api/v1/routine/`, analog Plan/Photo) und
  den nginx-Origin-Block — Teil der Andock-Checkliste (ROUTINE-16); der
  Eltern-Chat erreicht den Endpunkt über `routine_origin_url` (EC-15). Setzt die
  Zeit-Schlüssel der Daten-Konfig (ROUTINE-12):
  - **Payload (JSON-Body), alle Felder optional, mindestens eines erforderlich:**
    - `abfahrtszeit` — `"HH:MM"` **oder** Wochentag→Zeit-Map
      `{ "mo": "08:30", "di": "08:30", … }` (ROUTINE-12 — je Wochentag möglich;
      leerer Tag = kein Kindi).
    - `aufstehzeit` — `"HH:MM"` oder Wochentag→Zeit-Map (gleiche Logik wie
      `abfahrtszeit`; AC-FIX1: direkt gesetzt, nicht abgeleitet).
    - `anzieh_vorlauf_min` — Minuten als Integer ≥ 0 (Tuning-Wert, ROUTINE-9).
  - **Fachliche Validierung im Buddy (vor jedem Schreiben):** Zeitformat strikt
    `HH:MM` (24h); bei Map nur gültige Wochentags-Keys aus einem festen Satz
    (`mo,di,mi,do,fr,sa,so`); `anzieh_vorlauf_min` ein nicht-negativer Integer.
    Ungültige Eingabe → **4xx, kein Schreiben** (kein Teil-Write). Die Prüfung
    liegt im Buddy, nicht im Skill — der Buddy besitzt seine Daten (BUD-2) und
    ist die fachliche Wahrheit; der Skill prüft nur konversationell vor.
  - **Persistenz:** schreibt in `routine/routine.json` (Daten-Konfig, getrennt
    von der Runtime-Config `routine/config.json`, BUD-2a). **Nur** über diese
    API — kein Datei-Zugriff von außen (APP-3); der Eltern-Chat schreibt nie
    direkt in `routine.json`.
  - **Wirkung sofort (EC-21) — Reload-on-Read:** Nach erfolgreichem Schreiben
    sind die neuen Zeiten beim nächsten Öffnen von `/display/routine/morgen`
    sichtbar, ohne Neustart. Dafür liest der Buddy seine Daten-Konfig **je
    Request frisch** aus `routine.json` (Reload-on-Read), statt sie nur beim
    Start zu cachen. Hintergrund: V1 las die Daten einmal beim Start; der Code
    markierte die Lücke selbst (`routine/main.py` „für späteres Reload-on-Read").
    Reload-on-Read ist der gewählte Weg (winzige JSON-Datei → kein Kiosk-Kosten-
    Thema), kein Reload-Hook-Protokoll nötig, da der Buddy selbst der Konsument
    seiner Daten ist. Das Per-Request-Lesen folgt **DCOMP-3** (Last-Known-Good
    bei transient kaputtem/teilweise geschriebenem Read — fällt NICHT auf
    Code-Defaults zurück, solange ein gültiger letzter Stand existiert) und
    **DCOMP-4** (atomares Schreiben Temp-Datei + Rename), damit ein Lese-Fehler
    nicht den Familienstand verliert.

**Routine-Punkte schreiben (`/api/v1/routine/items`) — bindend (#354).** Der
**Eltern-Chat ist der konkrete Konsument** (`routine-punkte-setzen.md` RPS,
OPEN-ROUTINE-B Teil 2) — die Items-Endpunkte sind damit **bindendes Requirement**
(RAT-11-Überführung Skizze→bindend), nicht mehr nur entworfen. Eigener API-Pfad
`/api/v1/routine/<resource>` (BUD-1b), eigene URL-14-Zeile, Reload-on-Read +
DCOMP-3/4 wie `PUT …/config`:

- **`POST /api/v1/routine/items` — Punkt anlegen.** JSON-Body: `quelle`
  (`default` | `einmalig`), `label`, `piktogramm` (ARASAAC-ID, über ICONS-7
  gewählt). `default` → in die `items`-Config (ROUTINE-12, persistent); `einmalig`
  → in den Tages-State (ROUTINE-8, Auto-Verfall ROUTINE-6). Antwort: `{"id": …}`
  (ID-Form ROUTINE-5). Validierung im Buddy (Label nicht leer, gültige ID, max. 8
  Punkte ROUTINE-19) → 4xx bei Verstoß, kein Teil-Write.
- **`DELETE /api/v1/routine/items/<id>` — Punkt entfernen** (`default` aus der
  Config, `einmalig` aus dem Tages-State), atomar.
- **`PUT /api/v1/routine/items` — die geordnete `default`-Liste ersetzen**
  (Reihenfolge ändern / Bulk; idempotent; URL-2 „Methode trägt die Aktion").
- **`GET /api/v1/routine/items` — die aktuelle Liste lesen** (V1.2, #469).
  Antwort: `{"default": [{id, label, piktogramm}, …], "einmalig_heute": [{id, label, piktogramm}, …]}`.
  Quellen: `cfg.items` (default-Liste, persistent) + Tages-State `einmalig_heute`
  (ROUTINE-8). Die Trennung im JSON ist bindend, weil `default` und `einmalig`
  fachlich unterschiedliche Persistenz/Lebensdauer haben (RPS-3) — ein Konsument
  muss den Unterschied erkennen können, ohne erneut zu fragen. Reload-on-Read
  (DCOMP-2): die Antwort spiegelt den aktuellen Stand bei jedem Aufruf.
- **`GET /api/v1/routine/config` — die aktuellen Zeit-Schlüssel lesen** (V1.1,
  #678; bindend ergänzt 2026-06-12 mit ROUTINE-20 als Konsument). Antwort:
  `{"abfahrtszeit": "HH:MM" oder Wochentag→Zeit-Map, "aufstehzeit": "HH:MM" oder
  Map, "anzieh_vorlauf_min": <int>}` — gleiche Schlüssel wie `PUT …/config`,
  nur lesend. Reload-on-Read wie alle Routine-Buddy-Reads. Auslöser: die
  Anpassen-Mini-App (ROUTINE-20) muss die heutigen Zeitwerte zum Vorbelegen ihrer
  Felder kennen; ohne diesen Endpunkt müsste sie raten oder die `routine.json`
  direkt lesen (APP-3-Verstoß). **Befund 2026-06-12 (Werft-F3 Live-Probe):** der
  Live-Buddy antwortet auf `GET` heute `405 Method Not Allowed` — die Implementation
  ergänzt den Lese-Pfad als Teil des Routine-Anpassen-Tracks.

Die übrigen Schnittstellen bleiben **entworfen, aber bewusst nicht gebaut**;
jede wird erst geliefert, wenn ihr konkreter Konsument/Produzent existiert
(analog OPEN-WETTER-B):

- **Konsum Wetter:** liest `/api/v1/wetter/` (Sonnencreme → `quelle=bedingt`).
  Aktiviert die heute geparkte Wetter-Lese-API **OPEN-WETTER-B**. → OPEN-ROUTINE-C.
- **Konsum Plan:** liest `/api/v1/plan/` (Mülltonne → `quelle=bedingt`), später.
  → OPEN-ROUTINE-D.

Wenn eine dieser Schnittstellen gebaut wird, folgt sie BUD-1b (eigener API-Pfad
`/api/v1/routine/<resource>`, eigene URL-14-Zeile, Konsum fremder Apps nur über
deren Schnittstelle, nie per Datei-Zugriff, APP-3).

**Zweiter Konsument der Schreib-API (zusätzlich zum Eltern-Chat-Skill):** die
**Anpassen-Mini-App** (ROUTINE-20). Sie ruft `GET /api/v1/routine/items`, `POST
/api/v1/routine/items`, `DELETE /api/v1/routine/items/<id>`, `PUT
/api/v1/routine/items` und `PUT /api/v1/routine/config` über denselben Pfad —
keine Sonder-Endpunkte für die Mini-App, kein eigener Such-Pfad. Eltern-Chat-Skill
RZS und Mini-App sind **gleichwertige** Konsumenten der API; der Buddy
unterscheidet sie nicht.

*Tickets:* #335, #343, #354, #678 (Mini-App-Konsument)

## 6. Konfiguration

### ROUTINE-12 — Konfigurationswerte
Per-Instanz-Config neben dem Code (BUD-2, CONFIG-1, gitignored), kein
hartcodierter Pfad/Name/keine Familie-1-Annahme (Familie-3-Probe). Die
Domänendaten (Routine-Punkte, Zeiten) sind **getrennt** von der Runtime-Config
zu halten (BUD-2a: Domänendaten getrennt von der Runtime-Config), weil der
Eltern-Chat sie schreibt (Zeiten: RZS #343; Punkte: OPEN-ROUTINE-B Teil 2 #354):

- `routine/routine.json` — **Daten-Konfig.** Format: `routine/routine.example.json`
  (committet, ohne echte Werte, CONFIG-3). Schreibstelle: Familie (Datei) bzw.
  Eltern-Chat (Zeiten RZS #343; Punkte #354).
- `routine/config.json` — **Runtime-Konfig** (Bind, Log), via gemeinsamem
  `tools/configloader.py` (CONFIG-1/CONFIG-5).

**Daten-Konfig (`routine/routine.json`):**

| Name                 | Default                                                    | Datei-Schlüssel    | Gesetzt durch (Onboarding-Schritt) |
|----------------------|------------------------------------------------------------|--------------------|-------------------------------------|
| Abfahrtszeit         | `08:30` (Fallback; je Wochentag mögl.)                    | `abfahrtszeit`     | Familie (Datei) oder Eltern-Chat (RZS, #343) |
| Aufsteh-Zeitpunkt    | `07:00` (Fallback; je Wochentag mögl.) · **Direkt aus Config, NICHT von anziehen abgeleitet** (AC-FIX1, #335) | `aufstehzeit` | Familie (Datei) oder Eltern-Chat (RZS, #343) |
| Anzieh-Vorlauf (Min) | `8`                                                        | `anzieh_vorlauf_min` | n/a (Default reicht) |
| Routine-Punkte       | 4 Default-Punkte (Fallback im Code; Wahrheit bleibt Datei, später per Eltern-Chat editierbar OPEN-ROUTINE-B) | `items` | Familie (V1 in Datei; `default`-Liste) |
| Zeit-Referenzen      | aus (`{ "an": false, … }`)                                | `zeit_referenzen`  | n/a (Gate-B-Experiment, ROUTINE-13) |
| Zeitzone             | `Europe/Berlin`                                            | `zeitzone`         | n/a (Default reicht; für Tages-Reset ROUTINE-6) |

**Runtime-Konfig (`routine/config.json`):**

| Name        | Default       | Datei-Schlüssel | Gesetzt durch |
|-------------|---------------|-----------------|---------------|
| Listen-Host | `127.0.0.1`   | `listen_host`   | n/a (PORT-3)  |
| Listen-Port | `5050` (ROUTINE-15) | `listen_port` | n/a |
| Log-Level   | `INFO`        | `log_level`     | n/a |

**Datei-Pfad-Overrides (ENV, CONFIG-5):**

| Wert               | Default                          | ENV                    | CLI |
|--------------------|----------------------------------|------------------------|-----|
| Daten-Konfig-Pfad  | `routine/routine.json` (neben dem Code) | `ROUTINE_DATA_FILE` | — |
| Abhak-Store-Pfad   | `routine/routine_store.json` (neben dem Code) | `ROUTINE_STORE_FILE` | — |

`abfahrtszeit` je Wochentag: ein Wert oder eine Wochentag→Zeit-Abbildung
(z. B. Sa/So leer = kein Kindi). Punkte und Zeiten sind der Musterfall der
**Familie-3-Probe**: was je Familie variiert, ist Config, nicht Code
(E-ROUTINE-4). **Fehlende/kaputte Datei oder fehlende Einzelwerte (inkl.
`abfahrtszeit`) → Defaults + Warnung, Prozess startet (CONFIG-4, #335).**
Kein Pflicht-Feld ohne Default — alle Werte sind durch Code-Defaults abgedeckt.
Die Code-Defaults sind Fallback, nicht Wahrheit: Wahrheit kommt aus der Datei
und später per Eltern-Chat (OPEN-ROUTINE-B). ENV-Overrides `ROUTINE_<KEY>` (CONFIG-5).

*Tickets:* #335

## 7. Service & Registrierung (BUD-Andock)

### ROUTINE-15 — Eigener Service, fester Port
Der Routine-Buddy läuft als eigener Prozess `xbuddy-routine.service` (BUD-1a,
SVC-1..4, Service-Vorlage im Repo, `Restart=on-failure`, Logs an stdout/stderr)
und bindet nur an `127.0.0.1` (PORT-3). Vorgeschlagener Port **5050** — die erste
freie Nummer im Buddy-Reserveblock 5050-5099 (PORT-2; 5030 ist Wetter, 5040/5041
sind Geräte-/Panel-Registry). Eintrag in `conventions/ports.md` PORT-2 ist
Andockpunkt 1 (OPEN-ROUTINE-H).

*Tickets:* #335

### ROUTINE-16 — Registrierung in der Plattform (Andock-Checkliste)
Der Slug `routine` durchläuft die **Andock-Checkliste „neuer Buddy"**
(`conventions/buddies.md`): (1) Port in PORT-2, (2) Origin-Routing-Zeilen URL-14
für `/display/routine/` (+ `/api/v1/routine/` bei der Zeiten-Schreib-API #343),
(3) nginx-Origin-Conf-Block, (4) systemd in
`deploy/systemd/README.md`, (5) `routine/tests` in `pytest.ini`, (6) `routine`
als `root_package` in `.importlinter` (MOD-1-Gate). Diese Verkabelung ist
**Integration**, nicht App-Eigentum — Gegenstand des Track-Schnitts.

**Familien-Schnittstelle-Beitrag (APP-4):** Der Zeiten-Schreib-Skill (#343)
wird über den bestehenden **TASK-7-Pfad** aktiviert — `build_catalog`
registriert ihn, genau wie `panel_anlegen` (PAA) live ohne #296 läuft (RAT-12).
Er hängt damit **nicht** am offenen App-Installations-Mechanismus (#296); die
Andock-Punkte für die Aufgabe regelt `conventions/tasks.md` (TASK-7). Die
Routine-Punkte (Teil 2, #354) sind spezifiziert (`routine-punkte-setzen.md` RPS,
Items-API bindend in ROUTINE-14) und docken genauso an (TASK-7).

*Tickets:* #335

## 8. Skelett & Tests

### ROUTINE-17 — Skelett-Topologie
Der Buddy spiegelt die geteilte Skelett-Topologie (`conventions/buddies.md`):
`routine/main.py` (HTTP + Entrypoint), `routine/config.py` (CONFIG-1/5),
`routine/render.py` (Domänen-Daten → Template-Kontext), `routine/templates/morgen.html`,
`routine/static/`, `routine/routine.example.json`, `routine/routine.service`,
`routine/tests/`, `routine/__init__.py`. Die Zeit-/Uhr-Logik mit injizierbarem
`now` (ROUTINE-9) ist ein domänen-eigenes Modul (z. B. `routine/uhr.py`), kein
Pflicht-Skelett, sondern folgt aus dem, was der Buddy tut.

*Tickets:* #335

### ROUTINE-18 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test (CLAUDE.md §6),
reproduzierbar und **ohne Netz** — die Uhr wird durch injiziertes `now`
ersetzt (ROUTINE-9). Mindest-Abdeckung: ROUTINE-2 (View rendert Default-Punkte
+ Uhr-Block) · ROUTINE-4 (Modell akzeptiert alle drei `quelle`; V1-Builder
erzeugt nur `default`) · ROUTINE-6 (Tageswechsel → Punkt wieder offen, mit
injiziertem `now`) · ROUTINE-7 (Tap → persistiert → Reload zeigt abgehakt) ·
ROUTINE-9 (drei Now-Phasen vor/zwischen/nach den Zeiten liefern die erwarteten
Restzeiten/Phasen; Wochentag-Dict: Schultag → Zeiten vorhanden, Wochenend-Tag →
None/Uhr ausgeblendet, beide mit injiziertem `now`) · ROUTINE-9
(`anzieh_vorlauf_min` aus Config steuert die „anziehen"-Zeit, keine
Code-Konstante) · ROUTINE-10 (Piktogramm über `/display/_shared/`-Pfad, kein
buddy-lokaler ARASAAC-Bezug) · ROUTINE-12 (fehlende/kaputte Datei und fehlende
`abfahrtszeit` → Defaults + Warnung, Prozess startet, CONFIG-4, #335) ·
AC-FIX1 (fehlende `aufstehzeit` → Default `07:00` + Warnung, Prozess startet; `aufstehzeit` direkt aus Config-Schlüssel, nicht abgeleitet, #335) ·
**ROUTINE-14** (buddy-seitig, #343: gültiges `PUT /api/v1/routine/config`
persistiert in `routine.json` und ist per Reload-on-Read ohne Neustart sichtbar;
ungültiges Zeitformat/ungültiger Wochentags-Key → 4xx, **kein** Teil-Write;
atomares Schreiben Temp+Rename und Last-Known-Good bei kaputtem Read,
DCOMP-3/DCOMP-4) · **ROUTINE-14 Items** (#354: `POST /api/v1/routine/items`
persistiert `default` in `routine.json` und `einmalig` im Tages-State,
Reload-on-Read sichtbar; `DELETE /api/v1/routine/items/<id>` entfernt
atomar; `PUT /api/v1/routine/items` ersetzt die geordnete `default`-Liste
idempotent; ROUTINE-19 max-8-Klemme + Label/Piktogramm-Validierung → 4xx;
`einmalig`-Auto-Verfall am Tageswechsel ROUTINE-6) ·
**ROUTINE-20** (Mini-App-View-Render-Test: gemischte Liste rendert in
korrekter Reihenfolge mit `🌅`-Marker für `einmalig`-heute; drei Zeit-Anker-
Cards mit Schloss-Symbol auf Aufstehen+Losgehen; Inline-Add-Buttons je
Sektion — der Items-Add aktiv, der Zeit-Add `disabled` ohne Click-Handler;
**kein FAB** im DOM; Drag-Bewegung eines `default`-Items erzeugt
`PUT /api/v1/routine/items`-Call mit dem neuen Objects-Array `[{id,label,piktogramm},…]` (kein items-Wrapper); Save mit
Zeit-Änderung erzeugt `PUT …/config` mit nur dem geänderten Schlüssel;
4xx vom Buddy bricht den Save mit ehrlicher Meldung ab; Frontend liest
Zeitwerte aus `GET /api/v1/routine/config`) ·
**ROUTINE-21** (Bottom-Sheet wird vom Items-Inline-Add-Button geöffnet:
Label-Tippen führt zu ICONS-7-Stub-Call mit `q=<label>`, ohne
Wort-Split-Magie; manuelle Suchleiste löst zweiten ICONS-7-Call aus;
Null-Treffer zeigt Klartext + Fokus auf Such-Feld; Save disabled ohne
Pikto-Wahl).

*Tickets:* #335

## 9. Anpassen-Mini-App (Eltern-Chat-Konsument der Schreib-API)

### ROUTINE-20 — Eltern-Anpassen-Mini-App-View (Layout + Bild-Pfad)

Die Eltern-Anpassen-Mini-App ist eine Telegram-Mini-App-View (RAT-16) unter
`<funnel-domain>/seiten/routine/anpassen`, gehostet vom geteilten
`seiten`-Service (analog ESSEN-31). Sie ist der **UI-Heimat-Konsument** der
Schreib-API ROUTINE-14; alle Schreib-Wirkungen laufen über die dort
spezifizierten Endpunkte, **nicht** über Buddy-eigene Sonder-Routen oder
Telegram-`sendData` mit Buddy-Schreibwirkung.

Die View rendert **eine einzige Bedien-Fläche** mit zwei Sektionen:

- **Sektion „Routine-Punkte"** — eine sortierbare Liste der heutigen
  Routine-Punkte (Quellen `default` + `einmalig_heute`, Daten aus `GET
  /api/v1/routine/items`). Jeder Eintrag rendert als Card im
  **Bring!-/Mini-App-Card-Pattern** (analog ESSEN-31): links das ARASAAC-
  Piktogramm, Mitte das Label, rechts ein Quellen-Marker (`🌅` für
  `einmalig`-heute, kein Marker für `default`) und eine **Lösch-Affordanz**.
  Die Cards sind per **Drag-Handle** sortierbar (nur `default`-Items sind
  bewegbar — `einmalig_heute` rutscht ans Ende, wird beim Save nicht in `PUT
  …/items` mitgegeben). Am **Listen-Ende** sitzt ein gestrichelter
  **Inline-Add-Button** `＋ Routine-Punkt hinzufügen`, der das
  **Hinzufügen-Bottom-Sheet** (ROUTINE-21) öffnet. **Kein FAB** — die
  Inline-Add-Geste lebt in der Sektion, in der das Element entsteht
  (siehe ROUTINE-23 Abweichung von MAD-3).
- **Sektion „Zeiten"** — Card-Liste der Zeit-Anker (gleiche Card-Optik wie
  Routine-Punkte für visuelle Konsistenz). V1.1 hat genau **drei feste Anker**:
  Aufstehen (`HH:MM`), Anziehen (Vorlauf in Min vor Losgehen), Losgehen
  (`HH:MM`). Daten aus `GET /api/v1/routine/config`. **Anker-Piktogramme**
  spiegeln die Display-View — heute ARASAAC `8152` (Aufstehen) / `6627`
  (Anziehen) / `8142` (Losgehen), hartcodiert im Display-Template
  (`routine/templates/morgen.html:84-104`) und in V1.1 zusätzlich im
  Mini-App-Frontend gleich gespiegelt; **Lego-Schuld V1.1** (DRY-Verletzung,
  zwei Stellen). Cleanup-Folge zieht die Anker-IDs in eine geteilte Quelle
  (z. B. `routine/anker_default.py`-Konstante), Template + Mini-App-Frontend
  + V2-Migration #726 lesen daraus — eigenes Lego-Cleanup-Ticket.
  Felder sind direkt editierbar; **V1: Globalwert je Feld** (keine
  Per-Wochentag-UI; die API trägt die Map, die V1-UI nicht — Begrenzung wie
  RZS V1-Scope). Eingaben werden im Frontend strikt gegen `HH:MM` /
  nicht-negativen Integer validiert (vor `PUT …/config`). **Aufstehen und
  Losgehen sind unverrückbar** (kein Drag, kein Löschen — Verriegelungs-
  Klausel #726); V1.1 zeigt das visuell durch ein **Schloss-Symbol** statt
  Drag-Handle.

  **[GEÄNDERT 2026-08-11 — Nic-Verdikt]** Der frühere deaktivierte
  Inline-Add-Button am Listen-Ende (`＋ Zwischen-Anker hinzufügen — V2 (#726)`)
  **entfällt ersatzlos**, samt der V1.1-Hinweiszeile darunter. Zwei Gründe:
  Eltern bekamen eine interne Ticket-Nummer zu sehen, und das Versprechen war
  längst eingelöst — die dynamischen Zeit-Anker sind über ROUTINE-24..28
  (Abschnitt 11) ratifiziert und gebaut, der Zwischen-Anker sitzt im
  Hinzufügen-Bottom-Sheet. Ein Knopf, der auf eine vorhandene Funktion
  vertröstet, ist schlechter als kein Knopf.

**V2-Aufbohrpunkt (#726).** Die Zeit-Sektion ist im Frontend bereits als
**Liste von Zeit-Anker-Einträgen** strukturiert (Items-Card-Form), damit V2
ohne UI-Umbau nur das Backend-Schema und den aktiven Add-Button +
Drag-Activation einschaltet. Folge-Ticket trägt das dynamische
`zeit_anker[]`-Schema, die Verriegelungs-Klausel, das API-Tripel und die
Display-Re-Render-Logik.

**Bild-Pfad:** Mini-App fordert die ARASAAC-PNGs **same-origin** unter
`/display/_shared/icons/arasaac/<id>.png` (ICONS-5, MAD-6) — kein
Telegram-Asset-Bezug, kein CORS.

**Save-Pfad:** Telegram-Hauptbutton `Speichern` (`platform.setMainButton`,
MAD-5) — nur aktiv, wenn der lokale Stand vom Server-Stand abweicht. Drückt
Eltern „Speichern", sendet das Frontend **bis zu drei sequentielle Requests**
gegen die ROUTINE-14-API:

1. Falls Items entfernt: je `DELETE /api/v1/routine/items/<id>`.
2. Falls neue Items oder Reihenfolge geändert: ein `PUT /api/v1/routine/items`
   mit der **vollständigen geordneten** `default`-Liste **als Array von Objects**
   (`[{"id": "…", "label": "…", "piktogramm": <id>}, …]` — Reihenfolge
   implizit aus Array-Position, kein `items`-Wrapper, kein `position`-Feld,
   ROUTINE-14-Schema; Backend validiert: `isinstance(body, list)`, sonst 400;
   Drift-Auflösung: #354 Backend-Stand, #728 Frontend-Iter-11, #772 Spec-Korrektur).
3. Falls Zeiten geändert: ein `PUT /api/v1/routine/config` mit den
   abweichenden Schlüsseln.

Schlägt ein Schritt fehl (4xx vom Buddy), bricht der Save mit ehrlicher
Fehlermeldung ab — vorhergehende Schritte werden **nicht** zurückgerollt
(die Mini-App ist optimistisch; eine 4xx-Antwort heißt: Eltern hatte
inkonsistente Eingabe, sie sieht den Teil-Stand und kann korrigieren). Ein
500/Netzfehler wird als „Buddy nicht erreichbar — versuch's gleich
nochmal" angezeigt.

**Auth (V1):** Die HTML-Route lädt **ohne** Auth (MAD-7 V1-Pattern,
`seiten`-Service bound an `127.0.0.1`, Tailscale-Funnel mit Per-Node-Cert);
API-Calls gegen `127.0.0.1`-bound Routine-Buddy laufen same-host. Eine
spätere `Authorization: tma <initData>`-Härtung (V1.x) ist gemeinsame
Mini-App-Aufgabe (siehe `conventions/mini-app-design.md`,
MAD-7-Folge-Ticket „Mini-App-Auth-Header"), kein V1-Blocker hier.

**Launcher (V1.1):** Die Mini-App wird in V1.1 ausschließlich über einen
**Inline-`web_app`-Button** geöffnet (RAO-6). Der breitere Launcher-Pfad
(MAD-10, Button **oder** `t.me`-Direktlink) wird in V1.1 **nicht** scharf
geschaltet, weil seine V1-Vorbedingung — Server-seitige `initData`-Validierung
im `seiten`-Service (`seiten/main.py:378-410`, heute offen) — vorher
geschlossen werden muss. Das ist eine Werft-Naht zum #719-Folge-Ticket-Stapel,
nicht eine Routine-Anpassen-Werft-Eigene-Sache.

*Test-Implikation:* Render-Test mit gemischter Liste (3 `default` + 1
`einmalig`-heute, Config mit Zeiten) → die View zeigt 4 Cards in der richtigen
Reihenfolge, `einmalig` mit `🌅`-Marker am Listen-Ende, drei Zeit-Anker-Cards
(Aufstehen/Anziehen/Losgehen) mit den jeweiligen Anker-Piktos und Schloss-Symbol
auf Aufstehen+Losgehen. Drag eines `default`-Items → Save sendet `PUT
/api/v1/routine/items` mit dem neuen Array. Tap Lösch-Affordanz → `DELETE`
mit korrekter ID. Inline-Add-Button → öffnet Bottom-Sheet (ROUTINE-21). Zeit-Feld
geändert → Save sendet `PUT …/config` mit nur dem geänderten Schlüssel. Der
V2-Add-Button bei Zeit-Anker ist `disabled` (kein Click-Handler in V1.1).

*Tickets:* #678 (MVP-Sammler-Naht), Folge-Implementierungs-Ticket

### ROUTINE-21 — Hinzufügen-Bottom-Sheet mit Icon-Picker

Das Hinzufügen-Bottom-Sheet (MAD-4-Pattern, `role="dialog"`,
`aria-modal="true"`) lebt im Mini-App-Frontend und legt **einen** neuen
Routine-Punkt an. Es enthält:

- **Label-Input** (Text-Feld, Pflicht, max. 40 Zeichen).
- **Quelle-Wahl:** Toggle `dauerhaft` (Default, → `quelle=default`) ·
  `nur heute` (→ `quelle=einmalig`). Default „dauerhaft", weil das die
  häufigere Wahl ist; „nur heute" ist die Ausnahme („Turnbeutel mit").
- **Icon-Picker** (Pflicht — kein Anlegen ohne Pikto-Wahl, ROUTINE-21d):

**ROUTINE-21a — Auto-Suche auf das Label.** Nach Tippen ins Label-Feld
(debounced ~250ms) ruft das Frontend `GET
/api/v1/icons/suche?q=<label>&max=12` (ICONS-7). Antwort-IDs werden als
**Grid-Galerie** (3 Spalten, MAD-2-Card-Pattern) angezeigt — Bilder aus
`/display/_shared/icons/arasaac/<id>.png`. Tap auf ein Bild = Auswahl,
Bottom-Sheet bleibt offen (Eltern kann Label nachschärfen und neu suchen).
Liefert die Voll-String-Suche keine Treffer und enthält die Eingabe Whitespace,
fällt das Frontend transparent auf Einzelwort-Suche zurück. Die Galerie zeigt
einen Klartext-Hinweis „Treffer für *X* und *Y* (Wort-Suche)", damit der
Fallback sichtbar ist (UX-Ehrlichkeit bleibt, keine ID-Erfindung).

**ROUTINE-21b — Manuelle Suchleiste, immer sichtbar.** Über/unter der
Galerie sitzt ein eigenes Such-Feld („Anderes Wort suchen"). Eingabe dort
ersetzt die Auto-Suche und ruft ICONS-7 mit dem manuellen Term. Die manuelle
Suche ist **immer** verfügbar, nicht nur bei Null-Treffern — Eltern muss
nicht erst „etwas Falsches probieren", bevor sie selbst suchen darf.

**ROUTINE-21c — Null-Treffer-Zustand.** Liefert ICONS-7 eine leere Liste,
zeigt die Galerie-Sektion Klartext: „Nichts gefunden für *X* — versuch ein
anderes Wort". **Kein Default-„Fragezeichen"-Piktogramm**, kein implizites Hilfs-Icon (würde
generische Routine-Karten am Display erzeugen, ROUTINE-10-Konsistenz).

**ROUTINE-21d — Save disabled ohne Pikto-Wahl.** Der Bottom-Sheet-Save-Button
ist disabled, solange weder Label noch Pikto-Wahl vorliegen. Drückt Eltern
Save, sendet das Frontend `POST /api/v1/routine/items` mit `{label,
piktogramm, quelle}` (ROUTINE-14-Schema). Erfolg → Bottom-Sheet schließt,
neuer Punkt erscheint in der Liste. 4xx-Antwort (z. B. >8 Punkte, ROUTINE-19)
→ ehrliche Fehlermeldung im Bottom-Sheet, kein Schließen.

*Test-Implikation:* Label-Tippen → ICONS-7-Stub liefert 3 Treffer → Grid
rendert 3 Bilder; Tap eines Bildes → ausgewählt-Markierung. Manuelle Suche
mit anderem Term → neuer ICONS-7-Call mit dem manuellen Wort. Null-Treffer
→ Klartext. Voll-String-Suche mit Whitespace-Eingabe und Null-Treffer →
transparenter Wort-Split-Fallback mit Klartext-Hinweis „Treffer für X und Y (Wort-Suche)".
Save ohne Pikto-Wahl → Button disabled.

*Tickets:* #678, Folge-Implementierungs-Ticket

### ROUTINE-22 — Folge-Punkt: Familien-Lexikon (ICONS-8) defer

Die V1-Mini-App **schreibt keine Wort→Pikto-Wahl zurück** ins
Icon-Lexikon. Wenn Eltern „Capoeira" sucht, ARASAAC keinen direkten Treffer
hat und sie per manueller Suche einen Pikto wählt, ist diese Wahl in V1
**nur in den Routine-Daten** persistiert, nicht im plattform-weiten Lexikon.
Ein zweiter Mini-App-Lauf für ein anderes Kind oder eine andere App muss
die Suche erneut führen.

Der **Familien-Lexikon-Layer** (Schreib-Pfad zurück in den Wort→ID-Cache,
ICONS-7-Erweiterung, Plan-Buddy-Migration) ist ein **eigenes Folge-Ticket**
gegen `icons.md` (vorgesehener ICONS-8). Begründung: das ist eine
Plattform-Klausel über mehrere Konsumenten hinweg (mindestens Mini-App,
Plan-Buddys `aktivitaeten`-Katalog, künftige Mini-Apps), keine
Mini-App-eigene Logik — und es soll erst angegangen werden, wenn ein
zweiter realer Mini-App-Konsument Schmerz belegt (Berater-Disziplin: n=2
gebaut). V1 trägt die manuelle Such-Reibung bewusst.

*Tickets:* Folge-Ticket „ICONS-8 Familien-Lexikon" (separat eröffnet)

### ROUTINE-23 — Mini-App folgt der Mini-App-Design-Vorlage (MAD)

Die Anpassen-Mini-App ist der **zweite Mini-App-Konsument** der Plattform
nach essen-einkauf (#653). Sie folgt bewusst dem
First-Occurrence-Pattern der inzwischen ratifizierten
`conventions/mini-app-design.md`
(MAD-1..7 + MAD-10 + Anti-Patterns; **Stand 2026-06-12 nach #719**: MAD-7
ist offen für Button **oder** `t.me`-Direktlink — beide Wege liefern
`initData`; MAD-8 ausgelagert nach `specs/platform/eltern-chat.md` EC-10
A2-Klausel; MAD-9 ausgelagert in Deployment-Heimat; MAD-10 neu = Launcher-
Capability). Routine-Anpassen folgt: gleicher DTOK-Andock, gleiches
Card-Pattern (MAD-2), gleiches Bottom-Sheet (MAD-4), `platform.js`-Wrapper
(MAD-5), Asset-Pfade (MAD-6), V1-Auth-Modell (MAD-7), V1.1-Launcher als
Inline-Button via MAD-10 (V2-Direktlink-Pfad wartet auf
`initData`-Validierung).

Die Mini-App ist gleichzeitig die formale **Bestätigung der EC-33-Schwelle**
(`specs/platform/eltern-chat.md`): Routine-Anpassen passt das ganze
Routine-Set + drei Zeit-Felder an = ≥5 Werte und ≥2 Achsen pro Anstoß →
WebApp ist der richtige UI-Modus (statt Chat-propose→confirm-pro-Eintrag).
Genau das war auch der Begründungs-Kern der RPS-Deprecation (siehe
`specs/platform/routine-punkte-setzen.md` E-RPS-3).

**Erwartete Abweichungen** (zur Beobachtung im Impl-Lauf, nicht als Veto):

- **Drag-Handle** als sortierender Card-Modifier ist in essen-einkauf nicht
  vorgekommen — neue Erweiterung des MAD-2-Card-Pattern.
- **Mehr-Feld-Save** (Items + Config in einem Save-Vorgang) statt
  Per-Tap-Toggle wie ESSEN-32 — anderer Konsistenz-Anker, weil die
  Anpassen-Mini-App eine Editor-Sitzung modelliert, keine inkrementelle
  Liste.
- **Pikto-Picker im Bottom-Sheet** (ROUTINE-21a/b) statt
  Kategorie-Auto-Match — die essen-einkauf-Quick-Add-Heuristik trifft hier
  nicht, weil Routine-Punkte semantisch einzeln gewählt sind, nicht aus
  einer Brot-Milch-Liste.
- **Inline-Add-Button je Sektion statt FAB** (Abweichung von **MAD-3**, Nic
  2026-06-12). Begründung: Routine-Anpassen ist ein Multi-Sektion-Editor
  (Routine-Punkte + Zeiten) mit **zwei semantisch unterschiedlichen
  Add-Pfaden** — ein einzelner FAB kann das nicht ehrlich tragen, zwei
  FABs verbietet MAD-3 selbst. Die Inline-Geste lebt *in* der Sektion, in
  der das Element entsteht (gleiches `add-row`-CSS für aktiven Items-Add
  und V2-Zeit-Anker-Add); konsistent zwischen den Sektionen, konsistent
  auch zur V2-Aufbohrlogik (gleicher Button schaltet von disabled auf
  aktiv, kein Layout-Umbau). **Eingangsfrage für die MAD-Berater-Runde:**
  soll MAD-3 erweitert werden um „bei Multi-Sektion-Editor: Inline-Add je
  Sektion statt FAB"?

**MAD-Ratifizierung erfolgt NICHT im Spec-PR dieser Mini-App.** Stattdessen
läuft nach Live-Implementation eine eigene `/berater-runde` mit beiden
gebauten Konsumenten (essen-einkauf + Routine-Anpassen) als Belege; die
Berater entscheiden, ob MAD nach `conventions/mini-app-design.md` gehoben
oder restrukturiert wird.

*Tickets:* #678 (Sammler), MAD-Ratifizierungs-Berater-Runde (nach Live)

---

## 11. V2 — Dynamische Zeit-Anker (Zwischenschritte editierbar)

Die V1-Mechanik (drei feste Anker `aufstehzeit` / `anzieh_vorlauf_min` /
`abfahrtszeit` aus `ROUTINE-12`) reicht für die Morgen-Sicht der ersten
Familie. Mit dem 2. Familien-Setup wird der Wunsch konkret, eigene
**Zwischenschritte** einzufügen ("nach Aufstehen 10 Min Hände waschen, dann
Anziehen, 5 Min vor Aufbruch Schuhe an"). V2 trägt das, **additiv** zur V1.
items[] (`ROUTINE-4`) bleibt SSoT der Reihenfolge — V2 erweitert das
Schema um einen optionalen `zeit`-Sub-Block am Item; die V1-Anker werden
schrittweise zu items mit `zeit.typ=anker` (`ROUTINE-28`).

### ROUTINE-24 — Datenmodell-Erweiterung: optionaler `zeit`-Sub-Block am Item

Ein Routine-Punkt (`ROUTINE-4`) bekommt einen optionalen `zeit`-Sub-Block:

```json
{
  "id": "...", "label": "...", "piktogramm": "...", "quelle": "default",
  "zeit": null
  //  oder { "typ": "anker",   "uhrzeit": "08:00", "locked": false }
  //  oder { "typ": "vorlauf", "minuten": 10, "bezug": "vorheriger_anker" }
}
```

- **`zeit` fehlt** (oder `null`) → reiner Routine-Punkt ohne Zeit
  (heutiges V1-items[]-Verhalten); im Display ohne Uhrzeit-Anker.
- **`typ: anker`** → absolute Uhrzeit (lokale Familien-Zeitzone, `HH:MM`).
  Optional `locked: true` schützt das Datenfeld vor Mini-App-Edit
  (V1-Kompat-Anker: `aufstehzeit`/`abfahrtszeit` werden zu
  `locked: true`-Ankern; siehe `ROUTINE-28`).
- **`typ: vorlauf`** → relativ zu einem Anker in der items[]-Ordnung,
  in Minuten. Zwei zulässige `bezug`-Formen:
  - `bezug: "vorheriger_anker"`: Pin-Uhrzeit =
    `vorheriger_anker.uhrzeit − minuten`. Lesart: „X Min vor dem
    letzten Anker davor" (z. B. „5 Min vor dem Frühstück Zähne putzen").
    Fehlt der vorherige Anker (Vorlauf am Listen-Anfang), zeigt das
    Display „—:—".
  - `bezug: "naechster_anker"` (Nic-Setzung 2026-06-22, Folge T1070):
    Pin-Uhrzeit = `naechster_anker.uhrzeit − minuten`. Lesart: „X Min
    vor dem nächsten Anker danach" (z. B. „5 Min vor Losgehen Anziehen").
    Ist die V1-Anziehen-Semantik (ROUTINE-9 `abfahrtszeit −
    anzieh_vorlauf_min`) und wird in ROUTINE-28 Welle B für die
    Migration genutzt. Fehlt der nächste Anker (Vorlauf hinter dem
    letzten Anker), zeigt das Display „—:—".

**items[]-Reihenfolge = Zeitlinie.** Der Display-Render rechnet
Vorlauf-Uhrzeit live aus dem Referenz-Anker − minuten. Fehlt der
Referenz-Anker, zeigt das Display „—:—" (MAD-1-Disziplin: keine
Fake-Daten).

**Verworfen:** (a) eigene `zeit_anker[]`-Liste neben items[] — zwei
Sub-Ressourcen, getrennte Order, mehr Stellen für Drift; bricht
items[]-SSoT. (b) Vorlauf relativ zum Listen-Start (absolute Position)
— verliert die intuitive Lesart „X Min vor Y".

*Tickets:* #726 · #1070

### ROUTINE-25 — Schreib-API-Erweiterung (kein neuer Endpunkt)

`PUT /api/v1/routine/items` und `POST /api/v1/routine/items` (`ROUTINE-14`)
akzeptieren den neuen `zeit`-Sub-Block am Item-Schema. **Kein neuer
Endpunkt.** Items ohne `zeit` bleiben weiter zulässig; `null`-Werte sind
äquivalent zu „kein zeit-Block".

`PUT /api/v1/routine/config` (V1-Schreibpfad für `aufstehzeit`/
`anzieh_vorlauf_min`/`abfahrtszeit`) bleibt als V1-Kompat-Bridge mit
**Deprecation-Hinweis** in den 200-Antworten (`X-Deprecation`-Header oder
JSON-Feld `deprecated: true`). Aufrufer werden auf den items[]-Pfad
verwiesen; der Endpunkt selbst bleibt funktionsfähig.

*Tickets:* #726

### ROUTINE-26 — Display-Erweiterung: items mit `zeit.typ=anker` sind
                Zeitstrahl-Pins

Das Display (`ROUTINE-9`) erweitert sein Zeitstrahl-Rendering wie folgt:

- Alle items mit `zeit.typ=anker` werden als **Pin-Piktogramme** am
  vertikalen Balken gerendert, in items[]-Reihenfolge (oben = frühe
  Uhrzeit, unten = späte Uhrzeit). Seiten-Alternation (`ROUTINE-9`)
  greift weiter; bei N>3 Ankern wechselt die Seite pro Position.
- Items mit `zeit.typ=vorlauf` werden als **eigene Pins zwischen den
  Ankern** dargestellt — mit Uhrzeit-Label `<anker_uhrzeit> − <minuten>`,
  Pikto, und einem feineren visuellen Marker (kleinere Pikto-Skala) als
  die Anker selbst.
- Items ohne `zeit`-Block bleiben in der Checkliste rechts vom Balken
  (heutiges V1-Verhalten der Routine-Karten).
- Das Verstrichen-Band, die 5-Min-Marker und die Zonen-Farben aus
  `ROUTINE-9` rechnen weiterhin gegen `aufstehen` und `losgehen` als
  Fenster-Ränder — diese sind nach `ROUTINE-28` selbst items mit
  `zeit.typ=anker` + `locked: true`.

*Test-Implikation:* items mit drei Ankern (`aufstehen 07:00`,
`Schule-los 08:30`, plus Zwischen-Anker `Pause 07:30`) und einem Vorlauf
(`vor Schule Schuhe 10 Min`) liefern vier Pins am Balken in der
richtigen Reihenfolge mit den richtigen Uhrzeiten.

*Tickets:* #726

### ROUTINE-27 — Mini-App-Erweiterung: Typ-Toggle im Bottom-Sheet

Die Anpassen-Mini-App (`ROUTINE-20`, `ROUTINE-21`) erweitert das
Hinzufügen-Bottom-Sheet um einen **Typ-Toggle** mit drei Werten:

- **Punkt** (Default) — kein `zeit`-Block, heutiges Verhalten.
- **Anker** — Uhrzeit-Picker (`HH:MM`-Input). Das Item bekommt
  `zeit: { typ: "anker", uhrzeit: "<eingabe>", locked: false }`.
- **Vorlauf** — Minuten-Stepper (5er-Schritte, Default 10 Min). Das
  Item bekommt `zeit: { typ: "vorlauf", minuten: <eingabe>,
  bezug: "vorheriger_anker" }`.

Reorder per ▲/▼-Pfeile (`feedback_telegram_drag_vs_arrows`) bleibt; die
Vorlauf-Uhrzeit aktualisiert sich automatisch im Render der Liste, weil
sie auf den vorigen Anker bezogen ist.

**`locked: true`-Anker in der Item-Karte sichtbar gesperrt:** die
Item-Karte zeigt den Anker mit einer read-only Badge „🔒 V1-Anker, ändern
in der Config" (`item-zeit-locked`, `seiten/static/routine-anpassen.js`).
Es gibt **keinen** Edit-Sheet (das Hinzufügen-Sheet ist add-only) — ein
Uhrzeit-Picker existiert für gesperrte Anker nicht; Migration auf
editierbar steht in `ROUTINE-28`.

*Tickets:* #726, #1197

### ROUTINE-28 — Migration V1-Anker → items mit `zeit.typ=anker`

Die V1-Anker `aufstehzeit`/`anzieh_vorlauf_min`/`abfahrtszeit`
(`ROUTINE-12`) leben heute in der Per-Instanz-Config. V2 führt sie
schrittweise als items mit `zeit.typ=anker` + `locked: true` in items[]
ein. Migration zweistufig analog ONB-5→ZD (#84 + #336):

- **Welle A (#726 Welle A):** Beim Start liest der Routine-Buddy
  weiter `ROUTINE-12`-Config UND items[]. Existieren in items[] keine
  Anker mit `locked: true`, werden sie aus `aufstehzeit`/`abfahrtszeit`
  synthetisch erzeugt und mit `locked: true` eingehängt. `PUT /config`
  bleibt funktionsfähig (V1-Bridge, `ROUTINE-25`); ein Schreibvorgang
  darauf aktualisiert den synthetischen Anker im items[]-State live.
- **Welle B (#726 Welle B):** Die synthetische Quelle wird umgekehrt:
  items[] ist die Wahrheit, `ROUTINE-12`-Config-Schlüssel werden read-only
  Ableitungen aus den `locked: true`-Ankern. `PUT /config` wird in der
  Antwort als deprecated markiert. Welle B beendet, wenn alle Familien
  ihre V1-Anker in items[] gesehen haben (Live-Probe).
- **Welle C (zukünftig):** `PUT /config` wird entfernt; Anker leben nur
  in items[].

**Edge-Cases (lösbar ohne Architektur-Runde):**

- **Anker gelöscht** → alle nachfolgenden Vorläufe bekommen den davor-
  Anker zugewiesen (Auto-Rebind, Frontend zeigt einen Hinweis im
  nächsten Save).
- **`locked: true`-Anker verschoben** → erlaubt; `locked` schützt nur das
  Datenfeld vor Mini-App-Edit, nicht die items[]-Position. Reorder via
  ▲/▼ bleibt frei.
- **Vorlauf vor allen Ankern** → Display zeigt „—:—" als Uhrzeit (MAD-1-
  Disziplin: keine Fake-Daten); items[]-Save bleibt zulässig.
- **`zeit.typ=anker`-Items mit gleicher Uhrzeit** → Display-Render
  rendert beide Pins; items[]-Reihenfolge bricht den Tie.

*Tickets:* #726

---

## Offene Punkte

- **OPEN-ROUTINE-A — `einmalig`/`bedingt`-Slots befüllen (Build-Layering).** Das
  Datenmodell trägt `quelle` von Anfang an (ROUTINE-4), V1 baut aber **nur**
  `default`. **Build-Layering:**
  - **V1** = `default`-Liste aus Config + ablaufende Uhr + Tap-Abhaken (täglicher
    Reset) + visuelle anziehen/losgehen-Indikation + textlose Zeit-Referenz-Balken
    (ROUTINE-13). **Kein** Cross-Buddy, **kein** Eltern-Chat, **keine** API.
  - **V1.1** = Eltern-Chat-Schreibpfad (Abfahrtszeit-Config + `einmalig`-Items).
    → OPEN-ROUTINE-B.
  - **V1.2+** = Sonnencreme (Wetter-API, `bedingt`) → OPEN-ROUTINE-C; Mülltonne
    (Plan-API, `bedingt`) → OPEN-ROUTINE-D.
  Die ID-Form herkunfts-eindeutiger Items ist **entschieden** (ROUTINE-5,
  `einmalig:`-Präfix, #354); das `einmalig`-Rendering nutzt das `default`-HTML
  (ROUTINE-19), Auto-Verfall am Tagesende (ROUTINE-6). Offen bleibt nur noch der
  `bedingt`-Slot (OPEN-ROUTINE-C/D).

- **OPEN-ROUTINE-B — Schreib-API für den Eltern-Chat (zweigeteilt).**
  - **Teil 1 — Zeiten (`PUT /api/v1/routine/config`, #343): gebaut.** Backbone
    (`routine/main.py` + `routine/config.py`) fertig, nginx-Routing ergänzt
    (URL-14). Reload-on-Read (DCOMP-3) + atomares Schreiben (DCOMP-4) umgesetzt.
    Skill-Verhalten: `specs/platform/routine-zeiten-setzen.md` (RZS, Track B).
  - **Teil 2 — Routine-Punkte (`/api/v1/routine/items`, #354): spezifiziert,
    bindend.** Items-Endpunkte (POST/DELETE/PUT) sind in ROUTINE-14 bindend;
    Skill-Verhalten: `specs/platform/routine-punkte-setzen.md` (RPS). Icon-Wahl über
    ICONS-7 (#390). ID-Form + Auto-Verfall entschieden (ROUTINE-5/6). Bau offen.
    **Update 2026-06-12 (Routine-Anpassen-Werft, #678):** RPS-Chat-Skill ist
    durch die Anpassen-Mini-App ersetzt (Nic-Wahl: Variante B —
    Mini-App-Bearbeitung statt propose→confirm-pro-Eintrag). Die Items-API
    bleibt bindend; ihr V1.1-Konsument ist die Mini-App (ROUTINE-20), nicht
    der Chat-Skill. RZS (Zeiten-Schnellsatz) bleibt aktiv (Mini-App + Chat
    co-existieren bei Zeiten — sieh dort).

- **OPEN-ROUTINE-C — Sonnencreme aus dem Wetter-Buddy (`bedingt`).** Routine
  liest `/api/v1/wetter/` und injiziert bei UV-Bedarf einen Sonnencreme-Punkt.
  Aktiviert die heute geparkte **OPEN-WETTER-B** (Wetter-Lese-API). Kein
  V1-Bedarf belegt.

- **OPEN-ROUTINE-D — Mülltonne aus dem Plan-Buddy (`bedingt`).** Routine liest
  `/api/v1/plan/` und injiziert an Abfuhrtagen einen Mülltonne-Punkt. Später,
  kein V1-Bedarf belegt.

- **OPEN-ROUTINE-E — Kindgerechte Zeit-Referenzen — in Gate B GEWÄHLT.** Das
  Experiment ist in der Design-Runde (2026-06-05, variant-f) als **textlose,
  maßstabsgetreue, rechtsbündige Referenz-Balken** bestätigt und Teil des
  V1-Designs (ROUTINE-13). Bleibt config-schaltbar; Dauer-an/aus am echten Kiosk
  ist spätere Tuning-Frage.

- **OPEN-ROUTINE-F — Display-Design (Gate B) — ENTSCHIEDEN 2026-06-05.**
  Gewähltes Artefakt: `mockups/variant-f` — Split-Layout (Checkliste | Zeit),
  linearer Zeitstrahl mit Bild-Events + Uhrzeiten, horizontale Referenz-Balken
  unterhalb des Zeitstrahl-Blocks, großer grün-werdender Abhak-Knopf, Boxen im
  WetterBuddy-Card-Stil.
  **Rest-Polish in der Impl:**
  (a) ~~Uhrzeit-Labels am Zeitstrahl dürfen nicht in andere Elemente ragen~~ —
  **ERLEDIGT 2026-06-06 (#335):** gelöst durch **Seiten-Alternation** (ROUTINE-9):
  adjazente Events stehen auf gegenüberliegenden Seiten des vertikalen Balkens;
  aufstehzeit kommt aus Config, nicht abgeleitet (AC-FIX1).
  (b) 8-Punkte-Layout am echten Display verifizieren (ROUTINE-19);
  (c) die drei Zeitstrahl-Piktogramme (anziehen/aufstehen/losgehen)
  gegen die ARASAAC-Suche treffsicher verifizieren.

- **OPEN-ROUTINE-G — Design-Token-Strang-Andockpunkt (#323) — ERLEDIGT.** #323 ist
  am 2026-06-05 gelandet: der geteilte Strang liegt unter
  `/display/_shared/design/tokens.css`, `conventions/design-tokens.md` (DTOK-1..5)
  existiert, plan+wetter sind migriert (v1.0 abgelöst). ROUTINE-11 referenziert den
  realen Strang (DTOK-3). Kein offener Punkt mehr — bleibt zur Nachverfolgung.

- **OPEN-ROUTINE-H — Port-Nummer.** Vorschlag **5050** (erste freie Nummer im
  Buddy-Block 5050-5099, PORT-2; 5030 Wetter, 5040/5041 Registries). Eintrag in
  `conventions/ports.md` PORT-2 ist Teil der Andock-Checkliste (ROUTINE-16), noch
  nicht erfolgt.

- **OPEN-ROUTINE-I — Mitwachsen-Stufen.** V1 hat eine Aufbereitung (nicht
  uhr-lesendes Kind, Piktogramme + ablaufende Uhr). Eine `reader`-Stufe für
  ältere Kinder (Text/Uhrzeit statt Piktogramm/Restzeit) ist die geplante
  Mitwachsen-Achse, aber ohne belegten V1-Bedarf vertagt.

---

## Entscheidungen

### E-ROUTINE-1 — Routine-Buddy ist eine App: besitzt Daten, Funktion, View
*Datum:* 2026-06-05 · App-Muster (`constitution.md` „App-Eigentümerschaft", APP-1).
Besitzt Routine-Punkte + Zeiten (Daten) und die ablaufende Uhr / Zeitberechnung
(Funktion); stellt das Ergebnis über die Display-View bereit. North-Star-Fit: die
Morgenroutine verschiebt das Antreiben vom Elternteil zum Kind. Die Morgenroutine
ist die **Domäne dieses Buddys** (ein Eigentümer, APP-1); frühere Routine-Ansätze
im Plan-Buddy gelten als **Legacy** und sind kein Modell für hier (eigenes
Cleanup-Thema, nicht Teil dieser Spec).

### E-ROUTINE-2 — Datenmodell mit drei Herkünften, V1 füllt nur `default`
*Datum:* 2026-06-05 · Ein Item trägt `quelle ∈ {default, einmalig, bedingt}` von
Anfang an (ROUTINE-4), damit der spätere Schreib-/Injektions-Pfad keine
Datenmodell-Migration erzwingt. V1 **baut und befüllt nur `default`**.
**Verworfen:** ein V1-Modell ohne `quelle` (hätte beim ersten `bedingt`-Punkt
eine Migration erzwungen) **und** ebenso verworfen, die Slots `einmalig`/`bedingt`
in V1 schon zu bauen (wäre Vorrat ohne Konsument, CLAUDE.md §6).

### E-ROUTINE-3 — Ablaufende Uhr ist rein visuell (kein Ton, kein Push)
*Datum:* 2026-06-05 · Die Uhr zeigt „in X: anziehen" / „in Y: losgehen" nur
visuell — kein Ton, keine Vibration, kein Push (`constitution.md` QA-5
Nicht-invasiv; kein Engagement-Design). **Verworfen:** akustischer/Push-Alarm bei
Erreichen von „anziehen"/„losgehen".

### E-ROUTINE-4 — Routine-Punkte und Zeiten sind Per-Instanz-Daten, nicht Code
*Datum:* 2026-06-05 · Abfahrtszeit, Vorlauf, Punkt-Liste und Zeit-Referenzen
variieren je Familie → Config (CLAUDE.md §6, Familie-3-Probe, BUD-2). Der
Anzieh-Vorlauf ist explizit ein **Tuning-Wert in der Config**, keine
Code-Konstante. **Verworfen:** Punkt-Liste oder Vorlauf als Python-Konstante
(wäre Familie-1 eingebacken — die Familie-3-Probe würde scheitern).

### E-ROUTINE-5 — Display-V1 ohne API; Zeiten-Schreib-API ab #343 (bindend)
*Datum:* 2026-06-05 (Display-V1), erweitert 2026-06-06 (RAT-12) · Die
display-only-V1 (#335) hatte keine `/api/v1/routine/` — kein Konsument (BUD-1b
„nur wenn", wie Wetter-Buddy E-WETTER-3). Mit dem Eltern-Chat als konkretem
Konsument ist der Zeiten-Schreibpfad `PUT /api/v1/routine/config` jetzt ein
**bindendes Requirement** (#343, RAT-12, ROUTINE-14), aktiviert über TASK-7 statt
#296. Mit dem RPS-Skill als Konsument sind seit #354 auch die
**Items-Endpunkte** (`/api/v1/routine/items`, POST/DELETE/PUT) bindend (ROUTINE-14).
Weiterhin **keine API auf Vorrat** (Heim-Server-Overhead, Anti-Goal): das
Cross-Buddy-Lesen (`bedingt`) entsteht erst, wenn sein Produzent existiert.

### E-ROUTINE-6 — V1 ohne Cross-Buddy-Konsum (Sonnencreme/Mülltonne vertagt)
*Datum:* 2026-06-05 · V1 konsumiert weder Wetter (`/api/v1/wetter/`) noch Plan
(`/api/v1/plan/`); die `bedingt`-Slots bleiben leer. Sonnencreme würde
OPEN-WETTER-B erst aktivieren (Lese-API existiert heute nicht). **Verworfen:**
die Cross-Buddy-Injektion schon in V1 zu bauen — ohne den Wetter-Lese-Vertrag
wäre das Doppelarbeit und würde die V1-Liefermenge an eine fremde, noch nicht
gebaute API koppeln.

### E-ROUTINE-7 — Stil aus dem geteilten Design-Token-Strang (#323 gelandet)
*Datum:* 2026-06-05 · Der Routine-Buddy rendert gegen den geteilten
Design-Token-Strang unter `/display/_shared/design/tokens.css`
(`conventions/design-tokens.md`, DTOK-1..5) und **referenziert** ihn (DTOK-3).
#323 ist am 2026-06-05 gelandet (plan+wetter migriert, v1.0 abgelöst), der Strang
ist live — keine #323-Abhängigkeit mehr. **Verworfen:** eigene Stilwerte
festklopfen oder einen zweiten Token-Satz aufmachen (DTOK-5 / DTOK-Drift).

### E-ROUTINE-8 — Abhak-Zustand für heute, täglicher Reset, app-eigene Datenhaltung
*Datum:* 2026-06-05 · Der Abhak-Zustand ist Tageszustand: persistiert über den
Reload (ROUTINE-7), setzt mit dem Tageswechsel zurück (ROUTINE-6), liegt in der
gitignorierten App-eigenen Datenhaltung (ROUTINE-8). **Verworfen:** Zustand nur
im Browser (Reload-Verlust) **und** verworfen, abgehakte Punkte über den
Tageswechsel zu behalten (die Morgenroutine ist täglich neu).

### E-ROUTINE-9 — Uhr/Now ist injizierbar (Test-Determinismus als Requirement)
*Datum:* 2026-06-05 · Die Zeit-Logik nimmt `now` von einer austauschbaren Quelle
(ROUTINE-9), nicht aus einem tief vergrabenen Wall-Clock-Aufruf. Begründung:
dieselbe Test-Reibung wie bei zeitabhängiger Wetter-Logik; ohne injizierbares
`now` ist die Restzeit-/Phasen-Anzeige nicht ohne echte Uhr testbar (ROUTINE-18).
**Verworfen:** `datetime.now()` direkt in der Render-/Uhr-Logik (macht die drei
Phasen-Tests von der echten Tageszeit abhängig).

### E-ROUTINE-10 — Box-/Card-Optik aus dem bestehenden Buddy (Wetter), nicht neu
*Datum:* 2026-06-05 · Die Boxen/Karten übernehmen die etablierte Buddy-Card-Optik
des WetterBuddys (`wetter/static/wetter.css` `.card`/`.card-label`) statt eines
neuen Stils — gleiche Tokens allein garantieren keine gleiche Optik (Nic-Befund
Gate B). **Offen/Werkstatt:** ob ein **geteilter Komponenten-Layer** (Card/Button
unter `/display/_shared/`) fällig wird, statt Wetter-CSS zu spiegeln, ist ein
Prozess-Werkstatt-Thema, kein V1-Blocker. **Verworfen:** einen eigenen Box-Stil
nur aus Tokens neu bauen (sieht „neu"/inkonsistent aus).

### E-ROUTINE-11 — Dynamische Liste mit V1-Obergrenze 8, ohne Scroll
*Datum:* 2026-06-05 · Die Punkt-Liste ist dynamisch (ROUTINE-19); V1 deckelt bei
**8** Punkten, alle ohne Scroll darstellbar (Karten skalieren mit der Anzahl).
**Verworfen:** feste 4er-Liste (würde mehr Punkte nicht tragen) **und** eine
unbegrenzte Liste mit Scroll (Kiosk-untauglich für ein Kind).

### E-ROUTINE-12 — V2-Zeit-Anker leben in items[], nicht als separate Liste
*Datum:* 2026-06-15 · V2 (`ROUTINE-24` … `ROUTINE-28`) erweitert items[]
um einen optionalen `zeit`-Sub-Block, statt eine eigene `zeit_anker[]`-
Liste anzulegen. Die items[]-Reihenfolge bleibt die einzige Wahrheit der
Zeitlinie. **Begründung:** zwei Sub-Ressourcen (items[] + zeit_anker[])
müssten ihre Reihenfolge separat synchron halten — bricht
items[]-SSoT und produziert zwei Stellen für Drift. Vorlauf-Items
referenzieren den **vorherigen** Anker statt den nächsten — robust bei
Listen-Ende (kein „nächster" verfügbar) und intuitiver lesbar ("10 Min
nach Aufstehen Zähne putzen"). **Verworfen:** (a) eigene
`zeit_anker[]`-Liste; (b) `bezug: "naechster_anker"`; (c) Vorlauf
relativ zum Listen-Start (absolute Minutenangabe).
