# Essens-Buddy — Spec     (ID-Präfix: ESSEN)

> Status: V1 · Refs #474

## Problem & North-Star-Bezug

Beim Wochen-Einkauf vergessen Eltern, was die Kinder sich gewünscht haben, und
das Kind erlebt nicht, dass seine Wünsche ernst genommen werden. Der
Essens-Buddy gibt dem Kind ein **eigenes Wunsch-Interface** am Display
(textloser Touch-Katalog) und gibt dem Elternteil im Eltern-Chat **auf Anfrage**
die aktuelle Wunsch-Liste. Das verschiebt die Kommunikation vom „Frag-Antwort"-
Ritual zur **eigenen, sichtbaren Ablage** des Kindes — und macht den Einkauf
zur kollektiven Liste statt zum Eltern-Erinnerungsspiel (North Star,
`constitution.md`).

Der Essens-Buddy ist eine eigenständige XBuddy-**App** mit einer
Touch-Display-View (APP-1). Als App **besitzt** er seine Daten (die Wunsch-Liste
und den Familien-Katalog) und seine Funktion (die Katalog-Strukturierung in
Kategorien sowie die dynamische Gerichte-Pflege durch den Eltern-Chat-Skill).

**V1-Scope:** mehrstufige Touch-Menü-Führung am Display (Kategorie → Item →
Wunsch ablegen) · drei Lebensmittel-Kategorien aus dem Repo-Basis-Katalog
(`obst_gemuese`, `brotbelag`, `sonstiges`) · eine Gerichte-Kategorie, in V1 leer
bis der Eltern-Chat-Skill `gericht-anlegen` (GAN) sie füllt · Wunsch-Liste
dauerhaft persistent (kein Auto-Verfall, kein Tagesreset) · vollständige
HTTP-API (interface-first; Konsumenten teils erst V1.x) · zwei Eltern-Chat-Skills
in V1: `wuensche-zeigen` (WZE, lesend) und `gericht-anlegen` (GAN, schreibend) ·
ARASAAC-Piktogramme über die geteilte Icon-Plattform (ICONS-5/ICONS-7) ·
eigener Service auf Port 5052 · Boxen im Buddy-Card-Stil des WetterBuddys.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Eltern-Chat-Pflege-Skills** für Wunsch-Liste (löschen, leeren, eigenen
  Wunsch hinzufügen) — OPEN-ESSEN-A.
- **Echte Produktfotos** statt ARASAAC-Piktogrammen (z. B. OpenFoodFacts als
  zweite Bild-Plattform) — OPEN-ESSEN-B.
- **Personen-Auflösung** über den Familien-Buddy (pro-Kind-Liste) —
  OPEN-ESSEN-C. V1 trägt nur `quelle ∈ {kind, eltern}`.
- **Rezept→Zutaten-Übersetzung** (Wunsch „Lasagne" → Einkaufsliste „Hackfleisch,
  Nudeln, Tomaten") — OPEN-ESSEN-D. V1 zeigt die Wünsche wörtlich.
- **Mitwachsen-Stufen** über die textlose Piktogramm-Stufe hinaus.

## 1. Die App & ihre View

### ESSEN-1 — Essens-Buddy ist eine App mit eigenem Besitz
Der Essens-Buddy ist die XBuddy-App mit dem Buddy-Slug `essen`. Er besitzt
seine **Daten** (die Wunsch-Liste und die Katalog-Pflege, ESSEN-21) und seine
**Funktion** (die Katalog-Strukturierung in Kategorien und der Schreibpfad für
Wünsche), und stellt das Ergebnis über seine **Display-View** und über die
HTTP-API bereit (APP-1, ESSEN-15..ESSEN-19).

*Tickets:* #474

### ESSEN-2 — Single-Canvas-View `wunsch` mit Kategorien-Tabs
Die View liegt unter `/display/essen/wunsch` (BUD-1, URL-2:
`/display/<slug>/<view>`, kein Verb im Pfad). Sie ist eine **einzige Canvas**
(wie die Routine-View `morgen`, ROUTINE-2) und enthält drei stets sichtbare
Bereiche: eine **Tab-Zeile** mit den vier Kategorien oben, das **Item-Grid** der
aktiven Kategorie links/Mitte, und die **Wunsch-Liste** rechts (Gate-B-Wahl
2026-06-09, Variante A „Tabbed Single-Canvas"). Kein Drill-Down, keine separate
Step-2-Ansicht, keine Settings-Seite. Statische Assets liegen unter
`/display/essen/static/<asset>` (URL-13).

**Wenn** die View aufgerufen wird, **dann** rendert sie die vier Kategorien-Tabs
mit einem voreingestellten aktiven Tab, das zugehörige Item-Grid und die
aktuelle Wunsch-Liste — alle drei Bereiche gleichzeitig.
*Test-Implikation:* GET `/display/essen/wunsch` rendert vier Tabs, ein
Item-Grid (= Items der aktiven Kategorie) und einen Liste-Block in einer
einzigen Canvas; ein Tap auf einen anderen Tab tauscht nur das Item-Grid aus.

*Tickets:* #474

### ESSEN-3 — Touch-Display, zwei Tap-Affordanzen
Die View ist für ein Touch-/Kiosk-Display gebaut. Es gibt **zwei**
Bedien-Affordanzen, beide als Tap: (a) ein **Kategorien-Tab** tippen — wechselt
das aktive Tab und damit das gerenderte Item-Grid, ohne den Liste-Bereich zu
verändern; (b) eine **Item-Kachel** tippen — legt einen Wunsch mit `quelle=kind`
ab (ESSEN-16) und aktualisiert sichtbar den Liste-Bereich. Kein Hover, kein
Wischen, kein Aufklappen, keine weiteren Bedien-Elemente.

**Wenn** das Kind eine Item-Kachel tippt, **dann** wird ein neuer Wunsch
angelegt und die Liste-Anzeige aktualisiert sich; **wenn** es einen anderen Tab
tippt, **dann** wechselt nur das Item-Grid; **wenn** es irgendwo sonst tippt,
**dann** passiert nichts.
*Test-Implikation:* nur Kategorien-Tabs und Item-Kacheln tragen einen
Tap-Handler; Hintergrund, Liste-Block und Wunsch-Einträge sind nicht
interaktiv.

*Tickets:* #474

## 2. Datenmodell der Wünsche

### ESSEN-4 — Ein Wunsch und seine Felder
Ein **Wunsch** (Item in der Liste) hat die Felder: stabile `id` (ESSEN-5),
`label` (kurzer Text, aus dem Katalog), `bild_ref` (ARASAAC-`id` über
ICONS-5/ICONS-7, ESSEN-11), `quelle ∈ {kind, eltern}` (Display vs. Eltern-Chat
als Schreibpfad, E-ESSEN-8), `kategorie ∈ {gericht, obst_gemuese, brotbelag,
sonstiges}` (ESSEN-9), `erstellt_am` (ISO-Zeitstempel mit Familien-Zeitzone).

`gericht` und die drei Lebensmittel-Kategorien sind im Modell **gleichwertig**
(E-ESSEN-2): ein Wunsch trägt seine Herkunfts-Kategorie als Datum, das die
Liste-Anzeige gruppieren kann; der Schreibpfad ist immer derselbe (ESSEN-16).

*Test-Implikation:* das interne Wunsch-Modell akzeptiert alle vier
`kategorie`-Werte und beide `quelle`-Werte; der Display-POST setzt
`quelle=kind`, der spätere Eltern-Chat-Schreibpfad setzt `quelle=eltern`
(V1.x, OPEN-ESSEN-A).

*Tickets:* #474

### ESSEN-5 — Stabile, herkunfts-eindeutige Wunsch-IDs
Jeder Wunsch trägt eine stabile `id` (IDENT-1 für stabile IDs) mit
**Quell-Präfix** entsprechend `quelle`: `kind:<n>` (Display-Wunsch) oder
`eltern:<n>` (Eltern-Chat-Wunsch, V1.x). So kollidieren sie nie und der Quell-
Pfad ist aus der ID lesbar. Die laufende Nummer `<n>` ist je Quelle monoton
steigend und wird im persistenten Store gehalten (ESSEN-7).

*Test-Implikation:* zwei Display-Wünsche haben nie dieselbe `id`; eine
`kind:`-ID kollidiert nie mit einer `eltern:`-ID; Reihenfolge in der Liste
folgt `erstellt_am`, nicht der ID-Nummer.

*Tickets:* #474

### ESSEN-6 — Wünsche leben dauerhaft, bis Eltern sie löscht
Ein Wunsch bleibt in der Liste, bis der Eltern-Chat ihn explizit entfernt (über
einen V1.x-Pflege-Skill, OPEN-ESSEN-A). V1 hat **keinen** Auto-Verfall, **keinen**
Tageswechsel-Reset, **keinen** Zeit-basierten Aufräum-Mechanismus
(E-ESSEN-3). Das passt zum Einkaufslisten-Modell: Wünsche sammeln sich, bis sie
bewusst abgehakt werden.

**Wenn** ein Wunsch heute angelegt wird und die View morgen neu geladen wird,
**dann** ist der Wunsch weiter da; **wenn** der Display-Prozess oder das
Tablet neustartet, **dann** sind alle Wünsche weiter da (persistente Datei,
ESSEN-7).
*Test-Implikation:* ein POST eines Wunsches, gefolgt von einem GET, liefert ihn
zurück; auch nach simuliertem Tageswechsel über die Test-Uhr bleibt er
unverändert.

*Tickets:* #474

### ESSEN-7 — App-eigene Datenhaltung der Wunsch-Liste
Die Wunsch-Liste liegt in der App-eigenen Datenhaltung neben dem Code, je
Instanz separat, per `.gitignore` ausgeschlossen (BUD-2a: Domänendaten
getrennt von der Runtime-Config). Fehlt sie beim Start, wird sie leer angelegt.
Sie hält die persistierten Wünsche und den Quellen-Zähler für die ID-Vergabe
(ESSEN-5). Form (schlanke JSON-Datei oder SQLite) ist Implementierungswahl;
entscheidend ist die Reload-Persistenz (ESSEN-6) und der atomare Schreibpfad
(ESSEN-20).

*Tickets:* #474

## 3. Display-Bereiche

### ESSEN-8 — Drei stets sichtbare Bereiche: Tabs, Item-Grid, Wunsch-Liste
Die View rendert drei Bereiche gleichzeitig auf einer Canvas (Gate-B-Wahl
2026-06-09, Variante A „Tabbed Single-Canvas"):

1. **Kategorien-Tabs** (oben, horizontal): vier Tabs nebeneinander, je
   Kategorie ein Tab mit Piktogramm und Kategorie-Label (ESSEN-9). Genau ein
   Tab ist **aktiv** (visuell hervorgehoben — gewählter Hintergrundton);
   anfangs Default-Tab nach ESSEN-9.
2. **Item-Grid der aktiven Kategorie** (links/Mitte): Grid von Item-Kacheln
   aus dem Katalog dieser Kategorie (ESSEN-12..ESSEN-14). Jede Kachel zeigt
   Piktogramm + Label. Tap legt einen Wunsch ab (ESSEN-3).
3. **Wunsch-Liste** (rechts): die aktuelle Wunsch-Liste, gruppiert nach
   Kategorie (Gerichte → Obst & Gemüse → Brotbelag → Sonstiges, gleiche feste
   Reihenfolge wie WZE-5), je Gruppe mit Sub-Überschrift und Einträgen
   (Piktogramm + Label). Aktualisiert sich nach jedem Tap einer Item-Kachel
   sichtbar (frischer GET `/api/v1/essen/wuensche` reicht, kein Vollreload
   nötig).

Es gibt **keinen Drill-Down, kein Zurück, keine zweite Seite** — alles auf
einer Canvas.

**Wenn** das Kind eine Item-Kachel tippt, **dann** erscheint der Wunsch in der
Wunsch-Liste (Bereich rechts); **wenn** es einen anderen Tab tippt, **dann**
tauscht sich nur das Item-Grid aus, Tabs und Liste bleiben unverändert.
*Test-Implikation:* die Render-Funktion erzeugt in einem Aufruf vier Tabs +
ein Item-Grid (der aktiven Kategorie) + den kategorie-gruppierten Liste-Block;
ein Tab-Wechsel-Render tauscht nur das Item-Grid aus.

*Tickets:* #474

### ESSEN-9 — Vier Tabs, drei aus Repo-Basis + einer dynamisch
V1 kennt genau vier Tabs in fester Reihenfolge: `gericht`, `obst_gemuese`,
`brotbelag`, `sonstiges`. Die drei Lebensmittel-Tabs (`obst_gemuese`,
`brotbelag`, `sonstiges`) zeigen Items aus dem Repo-Basis-Katalog (ESSEN-12),
optional per-Instanz überschrieben (ESSEN-13). Der Gerichte-Tab (`gericht`) ist
in V1 **dynamisch** und initial **leer**: er wird ausschließlich über den
Eltern-Chat-Skill `gericht-anlegen` (GAN) befüllt (ESSEN-14, ESSEN-19).

**Default-aktiver Tab:** `obst_gemuese` (deckt den häufigsten Wunschfall ab
und ist die für ein Kind direkt sichtbarste Kategorie). Auch wenn der
Gerichte-Tab leer ist, rendert er sichtbar in der Tab-Zeile; wird er aktiv
getippt, zeigt das Item-Grid eine ehrliche Leer-Meldung („noch keine
Gerichte"). So ist der spätere Schreibpfad immer sichtbar, ohne dass ein
leerer Tab die UI bricht.

*Test-Implikation:* der Render zeigt vier Tabs; mit leerem Gerichte-Katalog
ist der Gerichte-Tab sichtbar, sein Item-Grid (wenn aktiv) trägt eine
Leer-Meldung; nach einem POST auf `/api/v1/essen/katalog/gerichte` erscheint
das neue Gericht im Item-Grid des Gerichte-Tabs ohne Neustart (ESSEN-20).

*Tickets:* #474

### ESSEN-10 — Raumfüllende, lesbare Darstellung; Stil aus dem Design-Strang
Die Kacheln und die Liste-Sicht **nutzen den vorhandenen Platz** (Kiosk-Fläche
gut gefüllt, gute Lesbarkeit aus Distanz). Der visuelle Stil bindet an den
**geteilten Design-Token-Strang** unter `/display/_shared/design/tokens.css`
(`conventions/design-tokens.md`, DTOK-1/DTOK-2/DTOK-3) und **referenziert** ihn,
statt ihn zu kopieren (DTOK-3). **Keine hartcodierten Farben/Maße im
Buddy-CSS** (DTOK-5); alle Stilwerte als Token, ggf. stufen-abhängig (DTOK-4).
**Boxen/Karten übernehmen die bestehende Buddy-Card-Optik** des WetterBuddys
(`wetter/static/wetter.css` `.card`/`.card-label`), damit der Essens-Buddy
nicht „neu" aussieht (E-ESSEN-9, Pattern E-ROUTINE-10) — gleiche Tokens allein
garantieren keine gleiche Optik. Konkrete Maße folgen dem Gate-B-Artefakt
(OPEN-ESSEN-E).

*Tickets:* #474

### ESSEN-11 — Piktogramm je Kachel über die geteilte Icon-Plattform (Default; Familien-Foto-Override siehe ESSEN-22)
Jede Item-Kachel und jede Kategorie-Kachel trägt **per Default** ein
**ARASAAC-Piktogramm**, bezogen **über die zentrale Icon-Plattform** —
read-only unter der geteilten URL `/display/_shared/icons/arasaac/<id>.png`
(`icons.md` ICONS-5) —, **kein** buddy-eigener ARASAAC-Bezug (sonst zweiter
Icon-Pfad, CLAUDE.md §6 / Lego, gleiche Regel wie ROUTINE-10 / WETTER-18).
**Kein Emoji.** Die Katalog-Items und die Kategorie-Definitionen bilden auf
numerische ARASAAC-IDs ab. Die Lizenz-/NC-Frage liegt zentral in `icons.md`
ICONS-6 und wird hier nur referenziert, nicht erneut entschieden.

**Familien-Foto-Override (V1.1, ESSEN-22):** Trägt ein Item ein Familien-Foto
über den Photo-Buddy, ersetzt dieses Foto den ARASAAC-Default für genau
dieses Item. Items ohne Familien-Foto behalten den ARASAAC-Default. Die
Übergangs-Logik ist deterministisch (Foto vorhanden → Foto rendert; sonst
ARASAAC).

*Test-Implikation:* ein Item ohne Familien-Foto rendert sein Piktogramm über
den `/display/_shared/`-Pfad (kein buddy-lokaler ARASAAC-Download); ein Item
mit Familien-Foto rendert das Foto über die Photo-Buddy-Schnittstelle
(PHOTO-15) statt des Piktogramms.

*Tickets:* #474, #531

## 4. Katalog (Daten-Quellen)

### ESSEN-12 — Lebensmittel-Basis-Katalog als Repo-Default
Die drei Lebensmittel-Kategorien (`obst_gemuese`, `brotbelag`, `sonstiges`)
haben einen **Repo-Basis-Katalog** in `essen/katalog.default.json` (committet,
CONFIG-3-analog: Beispiel-Datei mit echten Default-Werten). Der Default deckt
eine kleine Familien-taugliche Auswahl je Kategorie ab (Größenordnung 8-15
Items je Kategorie — keine starre Obergrenze, weil das ein Tuning-Wert ist).
Jedes Katalog-Item trägt: `id` (stabil je Repo-Eintrag, IDENT-1), `label`
(Anzeigetext), `bild_ref` (ARASAAC-`id`), `kategorie`.

Der Repo-Default ist Fallback, **nicht Wahrheit**: er ist die Basis, die jede
Familie bekommt, wenn sie keinen Per-Instanz-Override pflegt (ESSEN-13).

*Test-Implikation:* `essen/katalog.default.json` liegt committet im Repo,
trägt für jede der drei Lebensmittel-Kategorien mindestens einen Eintrag und
validiert gegen das Item-Schema.

*Tickets:* #474

### ESSEN-13 — Per-Instanz-Override `essen/katalog.json` (Familie-3-Probe)
Eine Familie kann den Repo-Default mit einer eigenen `essen/katalog.json`
(neben dem Code, gitignored, BUD-2/CONFIG-1) **überschreiben**. Die Override-
Datei ersetzt den Katalog vollständig (kein Merge je Kategorie), weil das
Bedeutungs-Modell „die Familie pflegt ihren eigenen Katalog" klarer ist als
„die Familie hängt etwas an" — Familie-3-Probe-konform (CLAUDE.md §6: was je
Familie variiert, ist Config, nicht Code; E-ROUTINE-4 analog).

**Wenn** `essen/katalog.json` existiert und gültig ist, **dann** wird sie
genommen; **wenn** sie fehlt oder leer ist, **dann** wird der Repo-Default
genommen (CONFIG-4: Defaults + Warnung, Prozess startet). Bei einer kaputten
Override-Datei greift Last-Known-Good (DCOMP-3): die zuletzt erfolgreich
gelesene Override-Datei wird weiter verwendet; **erst** wenn es nie eine gab,
fällt der Buddy auf den Repo-Default zurück.

*Test-Implikation:* mit nur dem Repo-Default rendert der Display den
Default-Katalog; mit einer gesetzten Override-Datei rendert er deren Items;
mit einer kaputten Override-Datei rendert er den letzten guten Stand (oder den
Repo-Default, wenn nie ein Override gelesen wurde).

*Tickets:* #474

### ESSEN-14 — Gerichte-Katalog ist dynamisch, lebt im Daten-State
Der Gerichte-Katalog liegt **nicht** im statischen Katalog (ESSEN-12/ESSEN-13),
sondern in der App-eigenen Datenhaltung (`essen/gerichte.json`, ESSEN-21) — er
ist **dynamisch** und wird ausschließlich über die Schreib-API
`POST /api/v1/essen/katalog/gerichte` (ESSEN-19) befüllt. Konsument der
Schreib-API in V1 ist der Eltern-Chat-Skill `gericht-anlegen` (`gericht-anlegen.md`,
GAN); Display oder andere Buddies schreiben nicht in den Gerichte-Katalog.

Initialzustand: leer. Damit ist die Gerichte-Kategorie am Display zunächst eine
Kachel ohne Items (ESSEN-9). Sobald die erste Gericht-Eintragung über GAN
landet, ist sie ohne Neustart sichtbar (Reload-on-Read, ESSEN-20).

*Test-Implikation:* `GET /api/v1/essen/katalog` rendert auch ohne
Gerichte-Datei eine konsistente Antwort (leerer Gerichte-Bereich); nach einem
`POST /api/v1/essen/katalog/gerichte` taucht das Gericht in der
Display-Item-Grid-Antwort dieser Kategorie auf.

*Tickets:* #474

## 5. API-Schnittstellen

### ESSEN-15 — `GET /api/v1/essen/wuensche` — Liste lesen
Liest die vollständige Wunsch-Liste. **Konsument in V1: der Eltern-Chat-Skill
`wuensche-zeigen`** (`wuensche-zeigen.md`, WZE) — die einzige Lese-Schnittstelle.
Eigener API-Pfad `/api/v1/essen/<resource>` (BUD-1b).

**Antwort (JSON-Body):** `{ "wuensche": [ { "id": …, "label": …, "bild_ref":
…, "quelle": …, "kategorie": …, "erstellt_am": … }, … ] }`. Reihenfolge:
`erstellt_am` aufsteigend (älteste zuerst).

*Test-Implikation:* mit drei persistierten Wünschen liefert der Endpunkt
genau diese drei in chronologischer Reihenfolge; mit leerer Liste liefert er
`{ "wuensche": [] }` (200, nicht 404 — leer ist kein Fehler).

*Tickets:* #474

### ESSEN-16 — `POST /api/v1/essen/wuensche` — Wunsch hinzufügen
Legt einen neuen Wunsch an. **Konsument in V1: die Display-View** (Kind-Tap im
Item-Grid, ESSEN-3, setzt `quelle=kind`). **V1.x-Konsument:** ein
Eltern-Chat-Schreib-Skill (`quelle=eltern`, OPEN-ESSEN-A).

**Payload (JSON-Body):** `label` (string, nicht leer), `bild_ref` (ARASAAC-`id`,
string), `quelle` (`"kind"` oder `"eltern"`), `kategorie` (einer der vier Werte
aus ESSEN-9).

**Fachliche Validierung im Buddy (vor jedem Schreiben):** alle Felder
erforderlich; `label` nicht leer; `quelle` und `kategorie` aus dem definierten
Satz; `bild_ref` muss eine ARASAAC-`id` sein, für die ein lokales PNG vorliegt
(ICONS-5). Ungültige Eingabe → **4xx, kein Schreiben** (kein Teil-Write). Die
Prüfung liegt im Buddy, nicht im Skill (BUD-2: der Buddy besitzt seine Daten).

**Antwort:** `{ "id": "<quelle>:<n>" }` (ESSEN-5).

**Persistenz:** schreibt atomar in `essen/wuensche.json` (DCOMP-4), die neue
ID wird vom Quellen-Zähler vergeben.

*Test-Implikation:* gültiger POST liefert eine neue `id` und macht den Wunsch
im nächsten GET sichtbar; ungültiger POST (leeres Label / unbekannte
`kategorie` / fehlende `bild_ref`) → 4xx, GET unverändert.

*Tickets:* #474

### ESSEN-17 — `DELETE /api/v1/essen/wuensche/<id>` — Wunsch entfernen
Entfernt einen Wunsch aus der Liste. **In V1 exposed** (vollständige API,
interface-first). **Konsumenten:** (a) Display-Lösch-Geste am Wunsch-Listen-
Eintrag (ESSEN-27, V1); (b) Eltern-Chat-Pflege-Skill (OPEN-ESSEN-A, V1.x).
Idempotent: ein DELETE auf eine bereits entfernte ID liefert 200 mit leerer
Antwort (kein 404), damit der spätere Skill nicht zwischen „war nie da" und
„schon weg" unterscheiden muss.

*Test-Implikation:* DELETE auf eine vorhandene ID → 200; nachfolgendes GET
enthält die ID nicht mehr; zweites DELETE auf dieselbe ID → 200, GET weiter
unverändert.

*Tickets:* #474, #532

### ESSEN-18 — `GET /api/v1/essen/katalog` — Katalog lesen
Liefert den vollständigen Katalog gruppiert nach Kategorie: die drei
Lebensmittel-Kategorien aus dem Repo-Default oder Per-Instanz-Override
(ESSEN-12/ESSEN-13) sowie die dynamische Gerichte-Kategorie (ESSEN-14).
**Konsument: die Display-View** (rendert Item-Grids in Schritt 2). Lesen ist
Pflicht-Lese-Pfad und unkonditional erreichbar.

**Antwort (JSON-Body):** `{ "kategorien": { "obst_gemuese": [ {item}, … ],
"brotbelag": [ {item}, … ], "sonstiges": [ {item}, … ], "gericht": [ {item}, … ]
} }`. Jedes Item: `id`, `label`, `bild_ref`, `kategorie`.

*Test-Implikation:* mit nur dem Repo-Default sind drei Kategorien gefüllt,
`gericht` leer; nach einem POST auf `/api/v1/essen/katalog/gerichte` enthält
`gericht` mindestens einen Eintrag.

*Tickets:* #474

### ESSEN-19 — `POST /api/v1/essen/katalog/gerichte` — Gericht anlegen
Legt ein neues Gericht in den dynamischen Gerichte-Katalog (ESSEN-14).
**Konsument in V1: der Eltern-Chat-Skill `gericht-anlegen`**
(`gericht-anlegen.md`, GAN). Andere Schreibpfade gibt es nicht (APP-3: der
Buddy besitzt seine Daten, der Skill schreibt nie direkt in `gerichte.json`).

**Payload (JSON-Body):** `label` (string, nicht leer), `bild_ref` (ARASAAC-`id`
über die Icon-Such-API ICONS-7, vom Skill bereits aufgelöst). `kategorie` ist
implizit `gericht` und wird nicht gesendet.

**Fachliche Validierung im Buddy:** `label` nicht leer, kein Duplikat
(gleiches `label` existiert bereits → 409 Conflict, kein zweiter Eintrag);
`bild_ref` muss eine ARASAAC-`id` mit lokal vorliegendem PNG sein (ICONS-5).
Ungültig → 4xx, kein Schreiben.

**Antwort:** `{ "id": "<n>" }` (laufende Nummer im Gerichte-Katalog,
quellen-eindeutig analog ESSEN-5).

**Persistenz:** schreibt atomar in `essen/gerichte.json` (DCOMP-4).

*Test-Implikation:* gültiger POST liefert eine neue `id` und macht das Gericht
in `GET /api/v1/essen/katalog` (Kategorie `gericht`) sichtbar; doppeltes
Anlegen mit demselben `label` → 409.

*Tickets:* #474

### ESSEN-20 — Reload-on-Read, atomares Schreiben, Last-Known-Good
Der Buddy liest seine persistenten Dateien (`wuensche.json`, `gerichte.json`,
Override-`katalog.json`) **je Request frisch** (Reload-on-Read, ROUTINE-14-
Pattern). Damit sind Schreibvorgänge ohne Neustart sichtbar. Schreibvorgänge
sind **atomar** über Temp-Datei + Rename (DCOMP-4); bei einem transient
kaputten oder teilweise geschriebenen Read greift **Last-Known-Good** (DCOMP-3)
— der Buddy fällt nicht auf Code-Defaults zurück, solange ein gültiger letzter
Stand existiert.

*Test-Implikation:* nach `POST /wuensche` ist der Wunsch im sofort folgenden
GET sichtbar (kein Restart); ein partiell geschriebener `wuensche.json`-Stand
führt nicht zu Wunsch-Verlust (Last-Known-Good wird gelesen).

*Tickets:* #474

## 6. Konfiguration

### ESSEN-21 — Konfigurationswerte
Per-Instanz-Config neben dem Code (BUD-2, CONFIG-1, gitignored), kein
hartcodierter Pfad/Name/keine Familie-1-Annahme (Familie-3-Probe). Die
Domänendaten (Wunsch-Liste, Gerichte-Katalog, Lebensmittel-Override) sind
**getrennt** von der Runtime-Config zu halten (BUD-2a):

- `essen/wuensche.json` — **Wunsch-Liste (Daten-State).** Initialzustand
  leer; angelegt beim ersten Schreibvorgang.
- `essen/gerichte.json` — **Gerichte-Katalog (Daten-State).** Initialzustand
  leer; angelegt beim ersten Schreibvorgang von GAN.
- `essen/katalog.json` — **Per-Instanz-Lebensmittel-Override** (ESSEN-13).
  Optional; fehlt sie, gilt `essen/katalog.default.json` aus dem Repo.
- `essen/katalog.default.json` — **Repo-Default des Lebensmittel-Katalogs.**
  Committet, CONFIG-3-analog. Form: `{ "kategorien": { … } }` (gleiches Schema
  wie ESSEN-18-Antwort).
- `essen/config.json` — **Runtime-Konfig** (Bind, Log), via gemeinsamem
  `tools/configloader.py` (CONFIG-1/CONFIG-5).

**Runtime-Konfig (`essen/config.json`):**

| Name        | Default       | Datei-Schlüssel | Gesetzt durch |
|-------------|---------------|-----------------|---------------|
| Listen-Host | `127.0.0.1`   | `listen_host`   | n/a (PORT-3)  |
| Listen-Port | `5052` (ESSEN-23) | `listen_port` | n/a |
| Log-Level   | `INFO`        | `log_level`     | n/a |

**Datei-Pfad-Overrides (ENV, CONFIG-5):**

| Wert                      | Default                              | ENV                     |
|---------------------------|--------------------------------------|-------------------------|
| Wunsch-Liste-Pfad         | `essen/wuensche.json`                | `ESSEN_WUENSCHE_FILE`   |
| Gerichte-Katalog-Pfad     | `essen/gerichte.json`                | `ESSEN_GERICHTE_FILE`   |
| Override-Katalog-Pfad     | `essen/katalog.json`                 | `ESSEN_KATALOG_FILE`    |
| Default-Katalog-Pfad      | `essen/katalog.default.json` (Repo)  | `ESSEN_KATALOG_DEFAULT_FILE` |

**Fehlende/kaputte Datei oder fehlende Einzelwerte → Defaults + Warnung,
Prozess startet** (CONFIG-4). Code-Defaults sind Fallback, nicht Wahrheit:
Wahrheit kommt aus den Dateien. ENV-Overrides `ESSEN_<KEY>` (CONFIG-5).

*Tickets:* #474

## 6a. Familien-Foto-Override (V1.1)

### ESSEN-22 — Familien-Foto je Item via Photo-Buddy (Eltern-Chat-Skill `essen_foto_setzen`)
Die Familie kann je Katalog-Item ein **eigenes Foto** hinterlegen, das den
ARASAAC-Default am Display ersetzt (ESSEN-11). Der Pfad lebt über bestehende
Naht: Eltern-Chat-Skill (analog FSE-Pattern `foto_senden_task`) +
**Photo-Buddy** als Familien-Foto-Speicher (PHOTO-15).

**Skill-Form (analog FSE, im Eltern-Chat-Katalog EC-8):**

- Trigger: Eltern schicken ein Foto im Privatchat oder in der Familien-Gruppe.
  Der Skill `essen_foto_setzen` fragt, zu welchem Katalog-Item das Foto gehört
  (Auswahl aus dem aktuellen Essens-Katalog, propose→confirm analog
  `routine_punkte_setzen`).
- Confirm: Mit einem Bestätigungswort (E-EC-7) speichert der Skill das Foto
  im Photo-Buddy mit einem **essen-spezifischen Tag** (Form: `essen:<item_id>`,
  analog PHOTO-15-Tag-Schema). Existiert für das Item bereits ein Familien-
  Foto, wird es ersetzt (genau ein Foto je Item, V1).

**Display-Konsum (ESSEN-11-Override):**

- Pro Render-Cycle prüft der Essens-Buddy je Katalog-Item: liegt ein
  Photo-Buddy-Foto mit Tag `essen:<item_id>` vor? Wenn ja → Foto-URL aus
  Photo-Buddy (PHOTO-15) rendern statt des ARASAAC-Default-Pfads. Wenn
  nein → ARASAAC-Default (ESSEN-11).
- Der Essens-Buddy hält **keine eigene Foto-Kopie**. Photo-Buddy bleibt die
  einzige Speicher-Stelle (APP-3: Photo-Buddy besitzt seine Daten).

**Lösch-Pfad (V1.1):**

- Wer das Familien-Foto eines Items entfernen will, nutzt den Photo-Buddy-
  Lösch-Pfad (PHOTO-Spec) — das Tag wird entfernt, das Display fällt
  automatisch beim nächsten Reload-on-Read (DCOMP-2) auf den ARASAAC-Default
  zurück. Ein eigener Essens-Foto-Lösch-Skill ist V1.1 nicht nötig (siehe
  *Out-of-Scope V1.1* unten).

**Out-of-Scope V1.1** (jeweils eigenes Ticket, sobald gebraucht):

- **Automatisches Freistellen** des Tellers / Hintergrund-Entfernung: V2-
  Ausbaustufe (E-ESSEN-10). V1.1 nimmt das Foto 1:1 wie hochgeladen.
- **Mehrere Fotos pro Item** (Karussell). V1.1 trägt genau eins.
- **OpenFoodFacts oder externe Foto-Datenbank**: OPEN-ESSEN-B bleibt
  vertagt, eigener Werft-Lauf (E-ESSEN-6).

*Test-Implikation:* Ein Skill-Test legt ein Foto für Item X an, ein Render-
Test belegt, dass Item X danach das Foto statt des ARASAAC-Pfads rendert.
Negativ-Test: Items ohne Familien-Foto rendern weiter den ARASAAC-Default
unverändert. Lösch-Test: nach Photo-Buddy-Tag-Entfernung rendert Item X
wieder ARASAAC.

*Tickets:* #531

## 7. Service & Registrierung (BUD-Andock)

### ESSEN-23 — Eigener Service, fester Port
Der Essens-Buddy läuft als eigener Prozess `xbuddy-essen.service` (BUD-1a,
SVC-1..4, Service-Vorlage im Repo, `Restart=on-failure`, Logs an stdout/stderr)
und bindet nur an `127.0.0.1` (PORT-3). Port **5052** — die nächste freie
Nummer im Buddy-Reserveblock 5052-5099 (PORT-2; 5050 ist Routine, 5051 ist
Photo). Eintrag in `conventions/ports.md` PORT-2 ist Teil dieses Spec-PRs.

*Tickets:* #474

### ESSEN-24 — Registrierung in der Plattform (Andock-Checkliste)
Der Slug `essen` durchläuft die **Andock-Checkliste „neuer Buddy"**
(`conventions/buddies.md`): (1) Port in PORT-2 (mit diesem Spec-PR gelandet),
(2) Origin-Routing-Zeilen URL-14 für `/display/essen/` und `/api/v1/essen/`,
(3) nginx-Origin-Conf-Block, (4) systemd in `deploy/systemd/README.md`,
(5) `essen/tests` in `pytest.ini`, (6) `essen` als `root_package` in
`.importlinter` (MOD-1-Gate), (7) `essen/views.json` für die Seiten-Registry
(BUD-3, SREG, RAT-13). Diese Verkabelung ist **Integration**, nicht
App-Eigentum — Gegenstand des Track-Schnitts im Übergabe-Ticket.

**Familien-Schnittstelle-Beitrag (APP-4):** Die zwei Eltern-Chat-Skills
`wuensche-zeigen` (WZE) und `gericht-anlegen` (GAN) werden über den
bestehenden **TASK-7-Pfad** aktiviert — `build_catalog` registriert sie hinter
Origin-Guards (siehe WZE-8 und GAN-7). Sie hängen damit **nicht** am offenen
App-Installations-Mechanismus (#296); die Andock-Punkte für die Aufgabe regelt
`conventions/tasks.md` (TASK-7, RAT-12-konform).

*Tickets:* #474

## 8. Skelett & Tests

### ESSEN-25 — Skelett-Topologie
Der Buddy spiegelt die geteilte Skelett-Topologie (`conventions/buddies.md`):
`essen/main.py` (HTTP + Entrypoint), `essen/config.py` (CONFIG-1/5),
`essen/render.py` (Domänen-Daten → Template-Kontext), `essen/templates/wunsch.html`,
`essen/static/`, `essen/katalog.default.json` (committet),
`essen/wuensche.example.json` und `essen/gerichte.example.json` (committet,
CONFIG-3), `essen/views.json` (BUD-3 / SREG), `essen/essen.service`,
`essen/tests/`, `essen/__init__.py`. Die Katalog-Lade-Logik (Default vs.
Override) ist ein domänen-eigenes Modul (z. B. `essen/katalog.py`), kein
Pflicht-Skelett, sondern folgt aus dem, was der Buddy tut.

*Tickets:* #474

### ESSEN-26 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), reproduzierbar und **ohne Netz**. Mindest-Abdeckung:
ESSEN-2 (View rendert Kategorien-Kacheln + Liste-Block) ·
ESSEN-3 (Tap auf Item-Kachel löst POST aus, Hintergrund nicht interaktiv) ·
ESSEN-4 (Wunsch-Modell akzeptiert alle vier `kategorie`- und beide
`quelle`-Werte) ·
ESSEN-5 (IDs sind quellen-eindeutig, Kollisionsfrei zwischen `kind:`/`eltern:`) ·
ESSEN-6 (POST + Tageswechsel via Test-Uhr + GET → Wunsch noch da) ·
ESSEN-8 (mehrstufiger Render: Schritt 1 vier Kategorien, Schritt 2
Item-Grid + Zurück) ·
ESSEN-9 (leere Gerichte-Kachel rendert mit Hinweis; nach POST sichtbar
ohne Restart) ·
ESSEN-11 (Piktogramme über `/display/_shared/`-Pfad, kein buddy-lokaler
ARASAAC-Bezug) ·
ESSEN-12 (Repo-Default lädt für drei Lebensmittel-Kategorien) ·
ESSEN-13 (Per-Instanz-Override ersetzt Repo-Default; kaputter Override →
Last-Known-Good; nie gelesener Override → Repo-Default, CONFIG-4) ·
ESSEN-14 (Gerichte-Katalog initial leer, dynamisch befüllt) ·
ESSEN-15 (GET liefert chronologisch, leer = 200) ·
ESSEN-16 (gültiger POST persistiert; ungültiges Label/`kategorie`/`bild_ref`
→ 4xx, kein Teil-Write) ·
ESSEN-17 (DELETE idempotent: zweites DELETE auf dieselbe ID = 200) ·
ESSEN-18 (Katalog-GET gruppiert über vier Kategorien, auch mit leerer
Gerichte-Liste) ·
ESSEN-19 (gültiger POST persistiert; doppeltes `label` → 409) ·
ESSEN-20 (Reload-on-Read sichtbar nach POST ohne Restart; partiell
geschriebene Datei → Last-Known-Good, DCOMP-3/4) ·
ESSEN-21 (CONFIG-4: fehlende/kaputte Datei → Defaults + Warnung, Prozess
startet) ·
ESSEN-27 (Display-Lösch-Geste: Mülltonnen-Symbol sichtbar an jeder
`liste-eintrag`; Tap löst DELETE auf die richtige ID aus; Liste rendert
neu gemäß ESSEN-20).

*Tickets:* #474

### ESSEN-27 — Display-Lösch-Geste am Wunsch-Listen-Eintrag
Jede `liste-eintrag`-Kachel auf `/display/essen/wunsch` trägt **sichtbar
auf der Kachel** ein Mülltonnen-Symbol (ARASAAC ID **2355**, geliefert über
die geteilte Icon-Plattform ICONS-5: `/display/_shared/icons/arasaac/2355.png`).
Position: kinder-tappbar im sichtbaren Kachel-Bereich, nicht in eine Eck-Ecke
gedrückt. **Genau ein Tap** auf das Symbol löst `DELETE /api/v1/essen/wuensche/<id>`
(ESSEN-17) aus; die Liste rendert unmittelbar danach neu und zeigt den
Eintrag nicht mehr (Reload-on-Read, ESSEN-20).

**Render-Vertrag:** Jede `liste-eintrag` trägt `data-wunsch-id="<id>"` (heute
fehlt das Attribut, neu in V1.x-Render).

**Bewusst NICHT in V1:** Bestätigungs-Dialog / Long-Press / Bulk-Lösch
(„Liste leeren"). Versehentliches Löschen wird über das erneute Eintragen
aufgefangen (Einkaufslisten-Modell, Reibung gering, kein Datenverlust mit
Bedeutung).

*Test-Implikation:* der Render zeigt das Mülltonnen-Symbol an jeder
`liste-eintrag`; eine Klick-Simulation auf das Symbol triggert genau einen
DELETE-Request mit der korrekten `data-wunsch-id`; nachfolgender GET liefert
die ID nicht mehr (Reload-on-Read).

*Tickets:* #532

---

## Offene Punkte

- **OPEN-ESSEN-A — Eltern-Chat-Pflege-Skills (Wunsch löschen, Liste leeren,
  eigenen Wunsch hinzufügen).** Die Pflege-Konsumenten von ESSEN-16
  (`quelle=eltern`), ESSEN-17 (DELETE) und einer späteren Liste-Leeren-API.
  V1 exposed die Schreib-/Lösch-API vollständig (interface-first); die
  konsumierenden Skills werden in eigenen Tickets nachgezogen. Wahrscheinlicher
  Skill-Schnitt: `wunsch-hinzufuegen` (WHZ, propose→confirm, Pattern RPS),
  `wunsch-loeschen` (WLO, propose→confirm), `wuensche-leeren` (WLE,
  propose→confirm mit harter Bestätigung).

- **OPEN-ESSEN-B — Echte Produktfotos statt ARASAAC-Piktogramme.** Für
  Lebensmittel wie spezifische Marken-Produkte (z. B. „der gelbe Joghurt") wäre
  ein echtes Foto aussagekräftiger als ein ARASAAC-Piktogramm. **OpenFoodFacts**
  (CC-BY-SA, deutsche Subsite, AWS-Image-Dataset) ist der wahrscheinliche
  Kandidat, würde aber einen **zweiten Bild-Pfad** neben ARASAAC etablieren
  (CLAUDE.md §6: ein Asset-Pfad). Das ist Architektur-Stoff für einen
  **eigenen Werft-Lauf**, nicht für diesen Buddy. V1 trägt mit ARASAAC.

- **OPEN-ESSEN-C — FAM-Integration für pro-Kind-Liste.** V1 trägt nur
  `quelle ∈ {kind, eltern}`. Wenn die Familie wissen will „welches Kind hat
  welchen Wunsch", braucht es Personen-Auflösung über den Familien-Buddy
  (FAM). Das zieht eine Fremd-API-Konsum-Beziehung in den Buddy und gehört in
  ein eigenes Ticket, sobald belegter Schmerz da ist.

- **OPEN-ESSEN-D — Rezept→Zutaten-Übersetzung.** Wunsch „Lasagne" zur
  Einkaufsliste „Hackfleisch, Nudeln, Tomaten" zu wandeln. Die Quellenlage ist
  schwierig: Chefkoch-Web-Scrape ist lizenz-riskant (Admin-Aussage: keine
  Weiterverbreitung), kommerzielle APIs (Spoonacular, Edamam) tragen wenig
  deutsche Familien-Gerichte. Wahrscheinlich besser via LLM (Eltern-Chat-
  Anbieter) on-the-fly. Eigenes Ticket, eigene Architektur-Runde.

- **OPEN-ESSEN-E — Display-Design (Gate B).** ERLEDIGT 2026-06-09 (Werft-Lauf
  #474, Gate B): Variante A „Tabbed Single-Canvas" gewählt — drei stets
  sichtbare Bereiche (Tabs oben · Item-Grid Mitte · Wunsch-Liste rechts), kein
  Drill-Down. Mockup-Artefakt:
  `brainstorm/idee-mvp/essen/mockups/variante-A-tabbed.html`. Spec ESSEN-2 /
  ESSEN-3 / ESSEN-8 / ESSEN-9 / E-ESSEN-7 entsprechend reconcilet.

- **OPEN-ESSEN-F — ARASAAC-Abdeckungsprüfung Lebensmittel-Domäne.** ERLEDIGT
  2026-06-09 (Werft-Lauf #474, vor Gate B): alle 20 Repo-Default-Items in den
  drei Lebensmittel-Kategorien (8 Obst&Gemüse · 6 Brotbelag · 6 Sonstiges)
  haben verifizierte ARASAAC-IDs mit CDN-Render-Beleg. Befund-Artefakt:
  `brainstorm/idee-mvp/essen/arasaac-probe/befund.md`. Repo-Default-Vorschlag:
  `brainstorm/idee-mvp/essen/mockups/katalog.default.json`. Spec ESSEN-12
  bleibt unverändert; die konkreten Items werden im Implementierungs-Ticket
  (#474-Impl) ins Repo als `essen/katalog.default.json` aufgenommen.

---

## Entscheidungen

### E-ESSEN-1 — Essens-Buddy ist eine App: besitzt Daten, Funktion, View
*Datum:* 2026-06-09 · App-Muster (`constitution.md` „App-Eigentümerschaft",
APP-1). Besitzt Wunsch-Liste + Gerichte-Katalog (Daten) und die Katalog-
Strukturierung/Schreibpfade (Funktion); stellt das Ergebnis über die
Display-View und über die HTTP-API bereit. North-Star-Fit: die Wünsche des
Kindes werden in einer eigenen, sichtbaren Ablage ernst genommen und sind im
Einkauf abrufbar.

### E-ESSEN-2 — Gericht und Lebensmittel sind im Modell gleichwertig
*Datum:* 2026-06-09 · Ein Wunsch trägt `kategorie ∈ {gericht, obst_gemuese,
brotbelag, sonstiges}` als Datum (ESSEN-4); der Schreibpfad ist immer derselbe
(ESSEN-16). Begründung Nic 2026-06-09: V1 sollte „beides gleich denken" — die
Trennung gehört in den Katalog (Repo-Default vs. dynamisch), nicht in zwei
separate Schreibpfade. **Verworfen:** ein V1 mit zwei Schreibpfaden (einer für
Lebensmittel, einer für Gerichte) — wäre Duplizierung ohne Bedeutungsgewinn.

### E-ESSEN-3 — Wünsche leben dauerhaft, bis Eltern sie löscht
*Datum:* 2026-06-09 (Nic) · Kein Auto-Verfall, kein Tagesreset (ESSEN-6).
Passt zum Einkaufslisten-Modell (Wünsche sammeln sich über Tage bis zum
Einkauf) und signalisiert dem Kind „mein Wunsch wird ernst genommen, nicht
über Nacht vergessen". **Verworfen:** Auto-Verfall nach N Tagen (würde Wünsche
vor dem nächsten Einkauf verlieren) und Tages-State analog Routine (würde das
Einkaufslisten-Modell brechen).

### E-ESSEN-4 — V1 trägt zwei Eltern-Chat-Skills (`wuensche-zeigen` + `gericht-anlegen`)
*Datum:* 2026-06-09 (Nic) · V1 darf wachsen, weil ohne `gericht-anlegen` die
Gerichte-Kategorie nie befüllt würde und das „beides gleich denken" (E-ESSEN-2)
ohne Konsument bliebe. Risiko bewusst akzeptiert: Werft-Methode hat
„mehrere neue Skills gleichzeitig + Eltern-Chat-Schreibpfad in einem Buddy"
noch nicht durchgespielt — Pattern (TER + RPS) ist aber jeweils erprobt.
**Verworfen:** display-only V1 wie Routine V1 (Gerichte-Kategorie bliebe
strukturell tot, V1.x-Aufschub ohne Konsumenten-Nachweis).

### E-ESSEN-5 — Rezept→Zutaten-Übersetzung ist nicht V1
*Datum:* 2026-06-09 (Nic) · Die Vision aus #474 enthielt eine
Chefkoch-Integration (Lasagne → Hackfleisch/Nudeln/Tomaten). V1 lässt sie weg:
Chefkoch-Web-Scrape ist lizenz-riskant (Admin-Aussage „Weiterverbreitung
disallowed", robots.txt restriktiv), die Übersetzung verdoppelt die V1-
Komplexität (zweite Datenquelle, neue Spec für Best-Fit-Heuristik), und V1
hat Wert auch ohne die Übersetzung (Eltern liest die Wünsche wörtlich und
weiß meist, was sie braucht). **Verworfen:** Chefkoch-Web-Scrape in V1 (Lizenz
+ Fragilität).

### E-ESSEN-6 — ARASAAC via ICONS-7 als Default; Familien-Foto als interne zweite Bild-Quelle (V1.1); OpenFoodFacts weiter vertagt
*Datum:* 2026-06-09 (V1) · Schärfung 2026-06-10 (V1.1, Refs #531)

**Default-Bildquelle** für Item-Kacheln (ESSEN-11) ist ARASAAC über die
zentrale Icon-Plattform (ICONS-5/ICONS-7), gleicher Pfad wie Routine
(ROUTINE-10) und Wetter (WETTER-18). Für andere Buddys gilt weiterhin: **ein
Asset-Pfad**, kein zweiter (RAT-13-Geist, Lego).

**Schärfung 2026-06-10 (V1.1, Familien-Setup #531):** Essens-Buddy bekommt
als erster Buddy eine **interne** zweite Bild-Quelle — **Familien-Fotos via
Photo-Buddy** (PHOTO-15, FSE-Pattern als Vorbild). Familien-Foto ersetzt den
ARASAAC-Default je Item (ESSEN-22). Begründung: bei Gerichten und Produkten
ist ein Familien-eigenes Foto („unsere Lasagne", „der Joghurt-Becher den die
Kinder kennen") für die Familien-Wiedererkennung deutlich aussagekräftiger
als ein generisches ARASAAC-Piktogramm. Der Transport bleibt ratifizierter
Pfad: Photo-Buddy als Familien-Foto-Speicher (PHOTO-Spec), nicht ein neuer
Asset-Pfad.

**Begriffsklärung:** „zweite Bild-Plattform" im V1-Wortlaut meinte
**externe Plattformen** wie ARASAAC oder OpenFoodFacts — diese tragen ihre
eigenen Lizenz-/Lebenszyklus-/CDN-Fragen und bleiben weiterhin Werft-/
Berater-Runden-pflichtig. Familien-Foto ist **kein externer Asset-Pfad**,
sondern Familien-eigener Inhalt im bereits ratifizierten Photo-Buddy.

**OpenFoodFacts (echte Produktfotos) bleibt vertagt** als OPEN-ESSEN-B —
eine **externe** zweite Bild-Plattform neben ARASAAC bräuchte weiterhin
Werft-Lauf + Berater-Runde / Cross-Engine-Probe.

**Verworfen:** den Familien-Foto-Pfad als „zweite Asset-Plattform" zu
behandeln und damit gleich-blockiert wie OpenFoodFacts. Der Asset-Pfad-
Schutz richtet sich gegen externe Lieferungen mit unkontrolliertem
Lebenszyklus — er trifft Familien-Foto-Inhalt nicht.

### E-ESSEN-7 — Tabbed Single-Canvas (Gate-B-Wahl, kein Drill-Down)
*Datum:* 2026-06-09 (Gate B, Werft-Lauf #474, Variante A) · Das Display ist
**eine** Canvas mit drei sichtbaren Bereichen — Kategorien-Tabs oben,
Item-Grid der aktiven Kategorie links/Mitte, Wunsch-Liste rechts (ESSEN-2,
ESSEN-8). Kein Drill-Down, kein „Schritt 1 → Schritt 2", kein Zurück-Button.
Begründung Gate B: Nic wählte Variante A („Tabbed") nach Vergleich mit
Variante B („Drill-Down") und C („Sidebar") — Vorteile: alles in einem Blick,
keine Klick-Verluste, das Kind sieht beim Auswählen sofort, was schon auf der
Liste steht; die Kategorien-Strukturierung trägt der Tab-Wechsel, nicht ein
mehrstufiger Auswahl-Pfad. Frühere Spec-Form (drei Schritte mit
Drill-Down/Zurück) verworfen mit Gate B. **Verworfen:** Drill-Down (Variante
B) — sauberer Spec-mehrstufig, aber zusätzlicher Tap-Aufwand ohne Mehrwert,
weil Schritt 1 keinen Item-Inhalt mitbringt. **Verworfen:** Sidebar-Layout
(Variante C) — gleiches „alles sichtbar"-Versprechen, wirkt am Kiosk-Format
aber „App-artig" (Information-Density) statt kindgerecht-plakativ.
**Verworfen:** Single-View mit allen Items flach nebeneinander (würde die
Kategorien-Strukturierung unsichtbar machen). **Artefakt:** Variante-A-Mockup
unter `brainstorm/idee-mvp/essen/mockups/variante-A-tabbed.html`.

### E-ESSEN-8 — Personen-Schicht minimal: `quelle ∈ {kind, eltern}`
*Datum:* 2026-06-09 (Nic) · V1 unterscheidet nur, **woher** ein Wunsch kommt
(Display = Kind, Chat = Eltern), nicht **welches** Familienmitglied ihn
gestellt hat. FAM-Buddy-Integration für pro-Kind-Listen ist eigene
Architektur-Stoff (OPEN-ESSEN-C). **Verworfen:** Personen-Auswahl am Display
in V1 (würde FAM-Abhängigkeit in V1 ziehen und das Display um einen
„wer-bist-du"-Schritt vor jeder Wunsch-Eingabe verlängern).

### E-ESSEN-9 — Box-/Card-Optik aus dem bestehenden Buddy (Wetter), nicht neu
*Datum:* 2026-06-09 · Die Boxen/Karten übernehmen die etablierte
Buddy-Card-Optik des WetterBuddys (`wetter/static/wetter.css`
`.card`/`.card-label`) statt eines neuen Stils — gleiche Tokens allein
garantieren keine gleiche Optik (Pattern E-ROUTINE-10). **Verworfen:** einen
eigenen Box-Stil nur aus Tokens neu bauen (sieht „neu"/inkonsistent aus).

### E-ESSEN-10 — Familien-Foto V1.1: 1:1-Übernahme; automatisches Freistellen V2-Ausbaustufe
*Datum:* 2026-06-10 · ESSEN-22 nimmt das hochgeladene Familien-Foto **1:1**
wie geliefert und rendert es statt des ARASAAC-Defaults. Automatisches
Freistellen des Tellers / Hintergrund-Entfernung ist als **V2-Ausbaustufe**
explizit benannt — kein V1.1-Blocker.

**Verworfen:** V1.1 mit serverseitigem Bild-Filter (Hintergrund-Entfernung,
Teller-Detection) zu liefern. Begründung: (a) Komplexitäts-Falle (Modell-
Auswahl, GPU-Last, Edge-Cases bei diffusen Hintergründen — Familien-Küche ist
nicht Studio), (b) Familien-3-Probe — selbst-gemachtes Foto ohne
Bildbearbeitung ist die kleinste, robusteste Form, (c) wer das vermisst, weiß
sofort „V2 kommt" und hat den richtigen Erwartungs-Horizont.

**V2-Trigger** (für das Folge-Ticket bei Bedarf): Wenn die Familien-Tests
zeigen, dass nicht-freigestellte Fotos die Erkennbarkeit/Optik im Item-Grid
spürbar mindern (mehrere Familien-Rückmeldungen ODER Werft-Befund am
Tablet-Probe). Bis dahin nichts auf Vorrat.
