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

*Tickets:* #335 · #364 (Fallback fehlender Map-Tag, AC-FIX4)

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

**Wenn** die Config 8 Punkte enthält, **dann** sind alle 8 gleichzeitig sichtbar
(kein Scroll); **wenn** sie 3 enthält, **dann** füllen 3 größere Karten den Raum.
*Test-Implikation:* der View-Render mit 8 `default`-Punkten erzeugt 8 Karten und
keinen Scroll-Container; die Kartenhöhe ist eine Funktion der Anzahl.
*(Layout-Probe für 8 am echten Display ist Impl-Feinschliff.)*

*Tickets:* #335

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

*Tickets:* #335, #343, #354

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
`einmalig`-Auto-Verfall am Tageswechsel ROUTINE-6).

*Tickets:* #335

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
