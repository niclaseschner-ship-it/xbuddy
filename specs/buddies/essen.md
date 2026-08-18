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
sonstiges}` (ESSEN-9), `erstellt_am` (ISO-Zeitstempel mit Familien-Zeitzone),
sowie für die Eltern-Einkaufsliste (V1, #653) **vier orthogonale Felder**:

- `klasse ∈ {wunsch, einkauf}` (Default `wunsch`) — `wunsch` ist eine
  Kind-/Eltern-Wunsch-Eintragung („das hätten wir gern"), `einkauf` ist
  eine reine Eltern-Einkaufsliste-Eintragung („das müssen wir holen").
  Orthogonal zu `quelle`: ein Eltern-Schreibpfad kann beide Klassen setzen.
- `abgehakt ∈ bool` (Default `false`) — abgehakt = erledigt (eingekauft /
  gekocht / aus der Sicht der Eltern erledigt). Lebenszyklus orthogonal zu
  ESSEN-6/E-ESSEN-3 (Wünsche leben dauerhaft, bis Eltern sie löscht):
  `abgehakt=true` löscht den Eintrag NICHT, er bleibt als „erledigt" sichtbar
  bis explizit gelöscht (ESSEN-17).
- `abgehakt_von` (string, optional, nur wenn `abgehakt=true`) — Telegram-User-
  Name / Eltern-Identifier des abhakenden Familienmitglieds.
- `abgehakt_am` (ISO-Zeitstempel, optional, nur wenn `abgehakt=true`).
- `aus_gericht` (string, optional) — Label des Wunsch-Gerichts, aus dessen
  Übernahme-Dialog (ESSEN-30) dieser Eintrag stammt. Trägt den
  📖-Quellen-Marker in der Eltern-Mini-App (ESSEN-31).

`gericht` und die drei Lebensmittel-Kategorien sind im Modell **gleichwertig**
(E-ESSEN-2): ein Wunsch trägt seine Herkunfts-Kategorie als Datum, das die
Liste-Anzeige gruppieren kann; der Schreibpfad ist immer derselbe (ESSEN-16).

**Migrations-Regel V1:** Alt-Einträge (vor #653) ohne `klasse`/`abgehakt`-Felder
werden vom Buddy beim Lesen implizit als `klasse='wunsch'`, `abgehakt=false`
behandelt — kein Datei-Migrations-Skript nötig, der Reader füllt Defaults.
Beim nächsten Schreiben durch ESSEN-16 werden die Felder explizit persistiert.

*Test-Implikation:* das interne Wunsch-Modell akzeptiert alle vier
`kategorie`-Werte und beide `quelle`-Werte; der Display-POST setzt
`quelle=kind`, `klasse=wunsch`; der Eltern-Chat-Schreibpfad setzt `quelle=eltern`
mit `klasse` nach Skill (`wunsch-hinzufuegen` → `wunsch`; `einkauf-hinzufuegen`
→ `einkauf`). Ein gelesener Alt-Eintrag ohne `klasse` ist äquivalent zu einem
mit `klasse='wunsch'`, `abgehakt=false`. `aus_gericht` ist NUR auf
`klasse='einkauf'`-Einträgen zulässig (Buddy lehnt anders ab).

*Tickets:* #474, #653

### ESSEN-5 — Stabile, herkunfts-eindeutige Wunsch-IDs
Jeder Wunsch trägt eine stabile `id` (IDENT-1 für stabile IDs) mit
**Quell-Präfix** entsprechend `quelle`: `kind:<n>` (Display-Wunsch) oder
`eltern:<n>` (Eltern-Chat-Wunsch, V1.x). So kollidieren sie nie und der Quell-
Pfad ist aus der ID lesbar.

**V1 #653 — globaler Zähler je `quelle`, klasse-übergreifend:** Die
laufende Nummer `<n>` ist je `quelle` monoton steigend und **klasse-
übergreifend eindeutig** — auch wenn die Persistenz nach `klasse` getrennt
ist (ESSEN-7), bleibt die ID global eindeutig. Beispiel: nach einem
Display-Wunsch `kind:1`, einem Eltern-Wunsch `eltern:2` und einem Eltern-
Einkauf-Item `eltern:3` hat der Eltern-Zähler den Stand `3`, unabhängig in
welchem File die Einträge liegen. Damit kollidieren IDs nie zwischen den
zwei Klasse-Files (ESSEN-7).

**Persistenz des Zählers:** zentrale Datei `essen/zaehler.json`
(`{"kind": <n>, "eltern": <n>}`), atomar geschrieben (DCOMP-4). Wird sie
beim Start nicht gefunden, leitet der Buddy die Stand-Werte aus dem
Maximum der existierenden IDs in beiden Klasse-Files ab (Migration ohne
Daten-Verlust).

*Test-Implikation:* zwei Display-Wünsche haben nie dieselbe `id`; eine
`kind:`-ID kollidiert nie mit einer `eltern:`-ID; Reihenfolge in der Liste
folgt `erstellt_am`, nicht der ID-Nummer. Ein Eltern-Wunsch `eltern:5`
und ein Eltern-Einkauf-Item kann nie denselben Zählerstand erhalten —
der Zähler ist quellen-globaler Zustand, **nicht** per-File. Crash-Test:
Zähler-Datei gelöscht → Buddy startet, leitet Stände aus Max-ID je File
ab; neu vergebene IDs kollidieren nicht mit Bestand.

*Tickets:* #474, #653

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

### ESSEN-7 — App-eigene Datenhaltung der Wunsch-Liste, getrennt nach `klasse`

Die Datenhaltung liegt in der App-eigenen Datenhaltung neben dem Code, je
Instanz separat, per `.gitignore` ausgeschlossen (BUD-2a: Domänendaten
getrennt von der Runtime-Config). Form: **schlanke JSON-Dateien**; die
Implementierungswahl SQLite ist explizit verworfen (E-ESSEN-12).

**V1 #653 — Trennung nach `klasse`:** Zwei getrennte Files je `klasse`:

- **`essen/wuensche.json`** — `klasse=wunsch`-Einträge. Wahrheits-Quelle für
  die Display-Wunsch-Liste (ESSEN-8). Konsumenten: Display-View, Mini-App-
  View (mit Filter `?klasse=wunsch`).
- **`essen/einkaufsliste.json`** — `klasse=einkauf`-Einträge. Wahrheits-
  Quelle für die Eltern-Einkaufsliste (ESSEN-31). Konsumenten: Mini-App-
  View (Default-Filter `?klasse=einkauf` oder unfiltered für Übersicht
  über beide), Eltern-Chat-Skill `einkauf-zeigen` (EZG).
- **`essen/zaehler.json`** — globaler Quellen-Zähler (ESSEN-5),
  klasse-übergreifend, garantiert ID-Eindeutigkeit über beide Files.

**Migration (Alt-Stand vor #653):** existierende `wuensche.json` mit alten
Einträgen ohne `klasse`-Feld bleibt die `klasse=wunsch`-Datei. Der Reader
füllt für Alt-Einträge `klasse='wunsch'`, `abgehakt=false` als Default
(ESSEN-4-Migrations-Regel). `einkaufsliste.json` wird beim ersten
Eltern-Einkauf-POST angelegt, sonst existiert sie nicht.

**Robustheits-Eigenschaft:** Jede Datei lebt unabhängig — wenn
`einkaufsliste.json` korrumpiert wird, läuft die Display-Wunsch-Liste
weiter; wenn `wuensche.json` korrumpiert wird, läuft die Einkauf-Mini-App
weiter. Reload-on-Read (ESSEN-20) gilt je File, atomares Schreiben
(DCOMP-4) ebenso je File, Last-Known-Good (DCOMP-3) je File.

**Schreibpfad-Routing:** POST mit `klasse=wunsch` schreibt nach
`wuensche.json`, POST mit `klasse=einkauf` schreibt nach
`einkaufsliste.json`. PATCH/DELETE suchen in **beiden** Files (ID ist
global eindeutig, kein Konflikt).

*Test-Implikation:* `POST /api/v1/essen/wuensche` mit `klasse=wunsch`
landet in `wuensche.json`; mit `klasse=einkauf` in `einkaufsliste.json`.
`GET /api/v1/essen/wuensche` ohne Filter liefert beide Files merge-sortiert
nach `erstellt_am`. Korruptions-Test: `einkaufsliste.json` als Müll
überschreiben → Display-View liefert weiter Wünsche aus `wuensche.json`,
`GET /api/v1/essen/wuensche?klasse=einkauf` greift Last-Known-Good oder
liefert leer mit Warnung.

*Tickets:* #474, #653

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
   sichtbar (frischer GET `/api/v1/essen/wuensche?klasse=wunsch` reicht,
   kein Vollreload nötig).

**V1 #653 — Display-Wunsch-Liste rendert ausschließlich `klasse=wunsch`:**
Der Display-View nutzt **immer** den Filter `?klasse=wunsch` beim Lesen.
Eltern-Einkauf-Items (`klasse=einkauf` aus `einkaufsliste.json`,
ESSEN-7) sind im Kinder-Display **nie sichtbar** — der Display ist
strukturell vom Einkaufs-Schreibpfad getrennt durch die Datei-Trennung
(ESSEN-7) UND zusätzlich durch den expliziten Filter im View-Render.
Doppel-Robustheit: selbst wenn ein versehentlicher Eintrag mit
`klasse=einkauf` in `wuensche.json` landet (Bug), filtert der Display ihn
heraus. Selbst wenn der Display den Filter im Code-Pfad weglässt (Bug),
liest er nur `wuensche.json` und sieht keine Eltern-Einkauf-Items.

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

**Familien-Foto-Override (V1.1, ESSEN-22):** Trägt ein Gericht ein
`foto_ref`-Feld, oder gibt es für ein Lebensmittel-Item einen Eintrag in
`essen/foto_overrides.json`, rendert das Display das Foto aus dem
Photo-Buddy statt des ARASAAC-Defaults — **kreisförmig ausgeschnitten** via
CSS, damit der Stil zu den Piktos passt. Items ohne Familien-Foto behalten
den ARASAAC-Default unverändert. Die Übergangs-Logik ist deterministisch
(`foto_ref` / Override-Eintrag vorhanden → Foto rendert; sonst ARASAAC).

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
Liest die vollständige Wunsch-Liste. **Konsumenten in V1:**
- der Eltern-Chat-Skill `wuensche-zeigen` (`wuensche-zeigen.md`, WZE) — Lese-Pfad.
- der Eltern-Chat-Skill `einkauf-zeigen` (`einkauf-zeigen.md`, EZG, #653) —
  Übersichts-Render + Mini-App-Öffnen-Button (lese-Pfad mit Filter).
- die Eltern-Mini-App `einkauf` (#653) — voller Liste-Render auf Phone.

Eigener API-Pfad `/api/v1/essen/<resource>` (BUD-1b).

**Antwort (JSON-Body):** `{ "wuensche": [ { "id": …, "label": …, "bild_ref":
…, "quelle": …, "klasse": …, "abgehakt": …, "abgehakt_von": …, "abgehakt_am":
…, "aus_gericht": …, "kategorie": …, "item_id": …, "erstellt_am": … }, … ] }`.
`item_id` (string) ist der eindeutige Katalog-Identifier des Lebensmittels oder
Gerichts (z. B. der Schlüssel in `katalog.json` / `gerichte.json`).
`klasse`/`abgehakt`/`abgehakt_von`/`abgehakt_am`/`aus_gericht` sind die V1-#653-
Felder aus ESSEN-4 — der Server liefert sie **immer** mit (Default-aufgefüllt
für Alt-Einträge gemäß ESSEN-4-Migrations-Regel).
Reihenfolge: `erstellt_am` aufsteigend (älteste zuerst).

**Query-Filter (V1, #653):**
- `?klasse=<wunsch|einkauf>` — filtert auf eine Klasse. **Implementation:**
  liest gezielt nur das passende File aus ESSEN-7 (`wuensche.json` für
  `klasse=wunsch`, `einkaufsliste.json` für `klasse=einkauf`) — kein
  Filter-Schritt nach dem Lesen, sondern Routing zum richtigen File.
- `?abgehakt=<true|false>` — filtert auf abgehakt-Status nach dem Lesen.
- Mehrere Filter sind UND-verknüpft.
- **Ohne `?klasse=`-Filter:** der Buddy liest **beide** Files (ESSEN-7),
  mergt sie und sortiert nach `erstellt_am` aufsteigend. Konsumenten,
  die nur eine Klasse brauchen (Display: `?klasse=wunsch`, Einkauf-
  Mini-App-Default: `?klasse=einkauf`), nutzen den Filter explizit für
  Effizienz und Klasse-Robustheit.

*Test-Implikation:* mit drei persistierten Wünschen liefert der Endpunkt
genau diese drei in chronologischer Reihenfolge; mit leerer Liste liefert er
`{ "wuensche": [] }` (200, nicht 404 — leer ist kein Fehler). Filter
`?klasse=einkauf` liefert nur die Einkauf-Einträge; `?klasse=wunsch&abgehakt=false`
liefert nur offene Wünsche. Unbekannter Filter-Wert → 400.

*Tickets:* #474, #653

### ESSEN-16 — `POST /api/v1/essen/wuensche` — Wunsch / Einkauf-Item hinzufügen
Legt einen neuen Eintrag an. **Konsumenten in V1:**
- die Display-View (Kind-Tap im Item-Grid, ESSEN-3, setzt `quelle=kind`,
  `klasse=wunsch`).
- der Eltern-Chat-Skill `einkauf-hinzufuegen` (`einkauf-hinzufuegen.md`, EIN,
  #653) — setzt `quelle=eltern`, `klasse=einkauf`, optional `aus_gericht` für
  die Übernahme-Geste (ESSEN-30).
- der Eltern-Mini-App-Quick-Add (#653) — setzt `quelle=eltern`,
  `klasse=einkauf`.

**Payload (JSON-Body):** `label` (string, nicht leer), `bild_ref` (ARASAAC-`id`,
string), `quelle` (`"kind"` oder `"eltern"`), `kategorie` (einer der vier Werte
aus ESSEN-9), `item_id` (string, nicht leer — eindeutiger Katalog-Identifier des
Lebensmittels oder Gerichts, z. B. der Schlüssel in `katalog.json` /
`gerichte.json`).
**V1 #653:** `klasse` (`"wunsch"` oder `"einkauf"`, Default `"wunsch"` wenn
fehlend — Rückwärtskompatibilität); `aus_gericht` (string, optional, nur
zulässig bei `klasse="einkauf"`) — Label des Wunsch-Gerichts, aus dem dieser
Eintrag via ESSEN-30 stammt.

**Fachliche Validierung im Buddy (vor jedem Schreiben):** alle Felder
erforderlich; `label` nicht leer; `quelle` und `kategorie` aus dem definierten
Satz; `bild_ref` muss eine ARASAAC-`id` sein, für die ein lokales PNG vorliegt
(ICONS-5); `item_id` Pflichtfeld, nicht leer, muss in einem der konsultierten
Kataloge existieren (ESSEN-13 Lebensmittel ODER ESSEN-14 Gerichte). Ungültige
Eingabe → **4xx, kein Schreiben** (kein Teil-Write). Die Prüfung liegt im
Buddy, nicht im Skill (BUD-2: der Buddy besitzt seine Daten).

**Ausnahme `frei:`-Präfix (Spec-Konsistenz mit EIN-4/ESSEN-31):** Eine `item_id`
mit Präfix `frei:` (case-insensitiv) ist OHNE Katalog-Match zulässig — das ist
der explizite Fallback-Pfad aus `einkauf-hinzufuegen.md` EIN-4 Schritt 3 und
aus dem Quick-Add der Mini App (ESSEN-31). Diese Items kollidieren per
Konstruktion nie mit Katalog-IDs (Präfix-Reservierung).

*Test-Implikation:* POST mit `item_id="frei:spritzkuchen"`, `kategorie=sonstiges`,
gültiger `bild_ref` → 201. POST mit `item_id="unbekannt:xyz"` (Präfix nicht
`frei:`, item_id nicht im Katalog) → 400 wie bisher.

**Duplikat-Schutz (BUD-2):** POST mit `item_id`, das bereits auf der aktiven
Wunschliste steht (Match über `item_id` UND derselbe `klasse`-Wert),
wird mit **409 Conflict** abgelehnt — kein doppelter Eintrag. Das garantiert
die ESSEN-28-Sperre Server-seitig, auch wenn ein Schreib-Pfad den Client-Guard
umgeht. Der Konsument darf 409 als „Item ist bereits auf der Liste"
interpretieren und benutzerfreundlich melden.

**V1 #653 — `klasse`-Achse beim Duplikat:** Klassen sind orthogonal — derselbe
`item_id` darf einmal als `klasse=wunsch` UND einmal als `klasse=einkauf` auf
der Liste stehen (Kind wünscht sich Mango, Eltern schreibt Mango als Einkauf —
beides ist gültig, kein 409). Match-Regel: `(item_id, klasse)`-Tupel.

**V1 #653 — Listen-Grenze (ESSEN-29):** Vor jedem Schreiben prüft der Buddy
die Listen-Grenze. Bei Überschreitung lehnt er **vollständig** ab (kein
Teil-Schreiben) — siehe ESSEN-29.

**Antwort:** `{ "id": "<quelle>:<n>" }` (ESSEN-5).

**Persistenz:** schreibt atomar in `essen/wuensche.json` (DCOMP-4), die neue
ID wird vom Quellen-Zähler vergeben. `item_id` wird mit-geschrieben als
Bestandteil jedes Wunsch-Eintrags. **V1 #653:** auch `klasse`, `abgehakt=false`,
optional `aus_gericht` werden persistiert; `abgehakt_von`/`abgehakt_am` bleiben
beim Schreiben über ESSEN-16 immer leer (gesetzt durch ESSEN-32 PATCH).

*Test-Implikation:* gültiger POST liefert eine neue `id` und macht den Wunsch
im nächsten GET sichtbar; ungültiger POST (leeres Label / unbekannte
`kategorie` / fehlende `bild_ref` / `item_id` unbekannt und kein `frei:`-Präfix) → 4xx, GET
unverändert; zwei POSTs mit identischer `item_id` UND derselbe `klasse` →
erster liefert 201, zweiter liefert 409 Conflict; zwei POSTs mit identischer
`item_id` und unterschiedlicher `klasse` → beide 201 (orthogonale Klassen).
POST mit `klasse=einkauf` + `aus_gericht="Lasagne"` → persistiert beide
Felder. POST mit `klasse=wunsch` + `aus_gericht="…"` → 400 (Kombination
unzulässig).

*Tickets:* #474, #653

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

**Payload (JSON-Body):** `label` (string, nicht leer) plus **genau eines**
der folgenden zwei Felder als Bild-Referenz:

- `bild_ref` (ARASAAC-`id` über die Icon-Such-API ICONS-7, vom GAN-Skill
  bereits aufgelöst) — Default-Pfad mit Pikto.
- `foto_ref` (Photo-Buddy-Medien-`id`) — Familien-Foto-Pfad (ESSEN-22 Pfad 1).
  Der GAN-Skill hat das Foto vorab über `POST /api/v1/photo/medien`
  hochgeladen und schickt die zurückgegebene Medien-ID hier mit.

Sind beide Felder gesetzt → 400 (eindeutig wählen). Keines gesetzt → 400.
`kategorie` ist implizit `gericht` und wird nicht gesendet.

**Fachliche Validierung im Buddy:** `label` nicht leer, kein Duplikat
(gleiches `label` existiert bereits → 409 Conflict, kein zweiter Eintrag).
Bei `bild_ref`: muss eine ARASAAC-`id` mit lokal vorliegendem PNG sein
(ICONS-5). Bei `foto_ref`: muss eine im Photo-Buddy existierende Medien-ID
sein (Buddy ruft `GET /api/v1/photo/medien/<id>` und prüft 200). Ungültig
in beiden Fällen → 4xx, kein Schreiben.

**V1 #653 — Zutaten-Feld:** Der Payload trägt **zusätzlich Pflichtfeld**
`zutaten` (Array): jede Zutat hat `label` (string, nicht leer), `kategorie`
(einer der drei Lebensmittel-Kategorien aus ESSEN-9: `obst_gemuese`, `brotbelag`,
`sonstiges` — `gericht` ist hier unzulässig), `bild_ref` (ARASAAC-`id`, vom GAN-
Skill via ICONS-7 aufgelöst). Reihenfolge der Zutaten wird beibehalten. Leeres
Array ist zulässig (Gericht ohne Zutaten — Eltern-Wahl, ESSEN-30 fängt das mit
Klartext-Hinweis statt Übernahme-Dialog ab).

**Antwort:** `{ "id": "<n>" }` (laufende Nummer im Gerichte-Katalog,
quellen-eindeutig analog ESSEN-5).

**Persistenz:** schreibt atomar in `essen/gerichte.json` (DCOMP-4). `zutaten`
wird mit-geschrieben.

*Test-Implikation:* gültiger POST mit `bild_ref` liefert eine neue `id` und
macht das Gericht in `GET /api/v1/essen/katalog` (Kategorie `gericht`)
sichtbar; doppeltes Anlegen mit demselben `label` → 409. **POST mit
`foto_ref` (Photo-Buddy-Medien-ID) statt `bild_ref` legt das Gericht mit
Foto-Pfad an — `GET /api/v1/essen/katalog` zeigt es mit `foto_ref` statt
`bild_ref`** (ESSEN-22 Pfad 1). **POST mit beiden Feldern → 400, POST mit
keinem → 400.** POST mit `zutaten: [{label: "Mozzarella",
kategorie: "brotbelag", bild_ref: "27136"}]` persistiert das Feld; das
nachfolgende GET zeigt es. POST mit `zutaten: [{kategorie: "gericht", …}]` →
400 (Kategorie für Zutat unzulässig).

*Tickets:* #474, #653

### ESSEN-19a — `PATCH /api/v1/essen/katalog/gerichte/<id>` — Gericht-Bild ändern

Aktualisiert die Bild-Referenz eines bestehenden Gerichts — Pendant zu
ESSEN-19 für das nachträgliche Setzen oder Wechseln des Familien-Fotos
(ESSEN-22 Pfad 2, Gericht-Ziel). **In V1.1 exposed** (interface-first).

**Konsument in V1.1:** der Eltern-Chat-Skill `essen_foto_setzen` (ESSEN-22
Pfad 2). Andere Schreibpfade auf bestehende Gerichte gibt es nicht.

**Payload (JSON-Body, alle Felder optional, sparse update analog ESSEN-32):**

- `foto_ref` (string, Photo-Buddy-Medien-`id`) — neues Familien-Foto. Wenn
  gesetzt, ersetzt der Buddy den bisherigen `bild_ref` / `foto_ref`. Buddy
  validiert die Medien-ID gegen Photo-Buddy
  (`GET /api/v1/photo/medien/<id>` → 200 erforderlich, sonst 400).
- `bild_ref` (string, ARASAAC-`id`) — zurück zum Pikto-Default. Wenn gesetzt,
  ersetzt der Buddy den bisherigen `foto_ref` / `bild_ref`. Validierung wie
  in ESSEN-19 (lokales PNG via ICONS-5).

**Fachliche Validierung:** ID muss existieren (sonst 404). `foto_ref` und
`bild_ref` gleichzeitig im Payload → 400 (eindeutig wählen, analog ESSEN-19).
Andere Felder (`label`, `zutaten`) sind **nicht** per PATCH änderbar — V1.1
beschränkt sich auf den Bild-Wechsel; Label/Zutaten ändern braucht eigene
Spec (offen). Unbekannte Felder im Payload → ignorieren
(Vorwärtskompatibilität, analog ESSEN-32).

**Antwort:** 200 mit dem aktualisierten Gericht-Eintrag (volle Form wie
GET-Element aus `/api/v1/essen/katalog`).

**Persistenz:** schreibt atomar in `essen/gerichte.json` (DCOMP-4, analog
ESSEN-19). Reload-on-Read greift automatisch (ESSEN-20).

*Test-Implikation:* PATCH `{foto_ref: "<medien-id>"}` auf bestehendes Gericht
→ 200, GET zeigt `foto_ref` gesetzt und `bild_ref` weg. PATCH
`{bild_ref: "<arasaac-id>"}` auf Foto-Gericht → 200, GET zeigt `bild_ref`
gesetzt und `foto_ref` weg. PATCH `{foto_ref: "X", bild_ref: "Y"}` → 400.
PATCH auf unbekannte Gericht-ID → 404. PATCH `{label: "Neu"}` → ignoriert
(Antwort hat `label` unverändert). PATCH mit `foto_ref`, dessen Medien-ID
im Photo-Buddy nicht existiert → 400.

*Tickets:* #531

### ESSEN-19b — `DELETE /api/v1/essen/katalog/gerichte/<id>` — Gericht löschen

Entfernt einen Gerichts-Eintrag aus dem dynamischen Katalog. **In V1.2
exposed** (Folge aus ESSEN-22 V1.2 Pfad 1, der `gericht-loeschen` als
Lösch-Pfad benennt).

**Konsument in V1.2:** der Eltern-Chat-Skill `gericht-loeschen`
(Drei-Phasen-Pattern, EC-10 „Drei-Phasen-Klausel").

**Pfad-Parameter:** `<id>` = die Gericht-ID aus `ESSEN-18`-Antwort.

**Foto-Kaskade (ESSEN-22 V1.2 Pfad 1).** Trägt das Gericht ein
`foto_ref`, löscht der Buddy das zugehörige Familien-Foto aus
`xbuddy-data/essen/fotos/<id>.<ext>` (ESSEN-22b) **synchron mit dem
Katalog-Eintrag**. Trägt das Gericht nur `bild_ref` (ARASAAC-Default),
passiert keine Foto-Aktion.

**Reihenfolge — „Katalog ist Wahrheit, Foto-Waise toleriert"**
(Watchdog-Folge zu PR #1068): Der Katalog-Lösch (atomar via Temp+Rename,
DCOMP-4) läuft **zuerst**. Scheitert er, bleibt das Gericht und nichts
ist geschehen. Erst danach läuft der Foto-Lösch als **best-effort**:
scheitert er (Disk-Fehler, Permission, etc.), bleibt ein Foto-Waise —
der Katalog-Lösch bleibt wirksam. Begründung: Der Katalog ist die
Wahrheit des Familien-Plans; ein verwaistes Foto im Datenverzeichnis
ist die mildere Asymmetrie als ein „Gericht ohne Bild im Katalog"
oder ein blockierender 500 bei tippfehlhaften Foto-Pfaden. Re-Run via
Aufräum-Skript ist möglich.

**Antwort:** 204 No Content bei Erfolg (auch im Foto-Waise-Fall —
Katalog ist Wahrheit). 404 bei unbekannter ID. **Kein 500 für
Foto-Lösch-Fehler** (Watchdog-Folge #1068).

**Idempotenz.** Wiederholter DELETE auf bereits gelöschte ID → 404 (kein
spezieller „bereits gelöscht"-Status — der Skill behandelt 404 als
„nicht da" identisch). EC-10-A2 ist **nicht** anwendbar — Lösch ist
mehrstufig (Drei-Phasen-Klausel).

**Persistenz:** Eintrag aus `essen/gerichte.json` raus, atomar
(DCOMP-4, analog ESSEN-19). Reload-on-Read greift automatisch
(ESSEN-20).

*Test-Implikation:* DELETE auf existierende ID mit `foto_ref` → 204,
GET liefert Gericht nicht mehr, Foto in `xbuddy-data/essen/fotos/` weg.
DELETE auf existierende ID mit `bild_ref` → 204, GET liefert Gericht
nicht mehr, keine Foto-Aktion. DELETE auf unbekannte ID → 404. DELETE
zweimal hintereinander auf dieselbe ID → erst 204, dann 404.
**Foto-Lösch-Fehler bei vorhandenem foto_ref** → 204 + Foto-Waise +
WARN-Log; Gericht ist im Katalog weg.

*Tickets:* #816

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

## 6a. Familien-Foto-Override (V1.2)

### ESSEN-22 — Familien-Foto je Item (Anlegen-mit-Foto ODER nachträglich setzen)

Die Familie kann je Katalog-Item ein **eigenes Foto** hinterlegen, das den
ARASAAC-Default am Display ersetzt (ESSEN-11). Es gibt **zwei Pfade** zum
selben Ziel — sie unterscheiden sich nur darin, ob das Foto schon beim
Anlegen des Items vorliegt oder erst später nachgereicht wird.

**Pfad 1 — Beim Anlegen mit Foto statt Pikto (GAN-Erweiterung).** Wenn Eltern
über `gericht-anlegen` (GAN) ein neues Gericht anlegen, können sie statt
eines ARASAAC-Piktos ein Foto mitschicken. Der GAN-Skill lädt das Foto vorab
über die **Essen-eigene Foto-API** (`POST /api/v1/essen/fotos`, V1.2) hoch
und ruft `POST /api/v1/essen/katalog/gerichte` (ESSEN-19) mit `foto_ref`
statt `bild_ref` auf. Das Gericht trägt damit von Beginn an die Foto-Referenz
im Katalog-Eintrag.

**Pfad 2 — Nachträglich für existierende Items (Skill `essen_foto_setzen`).**
Trägt ein Item heute schon einen ARASAAC-Default (oder wurde ohne Foto
angelegt), kann das Foto über den neuen Skill `essen_foto_setzen` nachgereicht
werden. Pattern analog FSE (`foto_senden_task`): Trigger ist ein Foto im
Privatchat oder Familien-Gruppe, der Skill ermittelt das Ziel-Item (siehe
Vor-Routing unten), schreibt die Foto-Referenz an die richtige Datenstelle
(Gericht vs. Basis-Item, siehe Datenmodell-Trennung), Confirm mit E-EC-7.
Existiert für das Item bereits ein Familien-Foto, wird es ersetzt (genau
ein Foto je Item).

**Vor-Routing am Bot-Eingang (LLM-Klassifikation auf Foto+Caption).** Schickt
die Familie ein Foto mit Caption in den Chat, klassifiziert das Eingangs-LLM
den Foto-Anstoß analog EC-22 (Anstoß-Vollständigkeit). Vier Fälle, alle
zweistufig (propose→confirm, EC-10 zweistufige Variante):

- **Item-Name in Caption + Match im Katalog** → `essen_foto_setzen`-Vorschlag
  („Foto für `<X>` setzen?").
- **Item-Name in Caption + KEIN Match im Katalog** (Name sieht nach Gericht
  aus, z. B. „Lasagne", existiert aber noch nicht) → Vorschlag „Willst du
  `<X>` als neues Gericht mit diesem Foto anlegen?" → Confirm leitet in den
  GAN-Pfad mit `foto_ref`.
- **Explizite Tag-Anweisung in Caption** (z. B. „hinterleg es bei
  essen/gerichte" oder „essen-foto") → expliziter `essen_foto_setzen`-Pfad,
  das Ziel-Item wird im nächsten Schritt geklärt.
- **Foto ohne erkennbaren Essens-Bezug** → kein Auto-Routing zu Essen,
  bestehender FSE-Pfad bleibt unverändert.

Das Vor-Routing ist deterministisch nur bei expliziter Tag-Anweisung; bei
Name-Match/Nicht-Match ist es LLM-vermittelte Klassifikation mit Vorschlag —
die Familie bestätigt immer, bevor geschrieben wird.

**Datenmodell-Trennung (Gerichte dynamisch, Basis-Items statisch).** Wo das
Foto-Verzeichnis lebt, hängt vom Item-Typ ab:

- **Gerichte** (dynamisch, `essen/gerichte.json`, ESSEN-14): `foto_ref` lebt
  direkt im Gericht-Eintrag. ESSEN-19 trägt das Feld als Alternative zu
  `bild_ref` (genau eines der beiden Pflicht).
- **Lebensmittel-Basis-Items** (statisch im Repo, ESSEN-12/ESSEN-13): die
  Repo-Datei `essen/katalog.default.json` wird NICHT mutiert — Override lebt
  per-Instanz in `essen/foto_overrides.json` (Schema:
  `{ "<item_id>": "<essen-foto-id>" }`). Die Datei folgt SVC-5
  (Per-Instanz-Daten unter `xbuddy-data/essen/foto_overrides.json`).

**Foto-Daten-Heimat im Essen-Buddy (V1.2, ESSEN-22b).** Die Foto-Bytes
selbst leben im Essens-Buddy unter `xbuddy-data/essen/fotos/` (Per-Instanz,
SVC-5), nicht im Photo-Buddy. Photo-Buddy ist Familien-Album-Bounded-
Context (Bilderrahmen) und hält ausschließlich Familien-Album-Inhalte;
Katalog-Item-Assets (Lasagne, Apfel-Override) sind ein anderer Bounded
Context und gehören in den jeweiligen Owner-Buddy (Lego-Trennung pro
Buddy, Anti-Pattern: ein Buddy hält fremde Sorten mit Flag/Tag/Owner-Feld).

`foto_ref` ist eine String-ID, die der Essens-Buddy vergibt und auflöst.
URL-Form: `/api/v1/essen/fotos/<id>` für Vollmedium, `.../thumbnail` für
Thumb.

**Essen-Foto-API (V1.2, ESSEN-22b):**

- `POST /api/v1/essen/fotos` (multipart/form-data, Form-Feld `medium`) —
  Ingest analog PHOTO-13. Antwort `{"id":<str>,"typ":<str>}`.
- `GET /api/v1/essen/fotos/<id>` — Vollmedium (JPEG/MP4).
- `GET /api/v1/essen/fotos/<id>/thumbnail` — Thumbnail (JPEG).
- `DELETE /api/v1/essen/fotos/<id>` — atomar entfernen (Vollmedium +
  Thumbnail + Index-Eintrag).

Index: `xbuddy-data/essen/fotos.json`. Foto-Verarbeitung (Normalize,
Thumbnail, atomar schreiben) über die geteilte Library
`tools/medien_store/` (siehe `conventions/medien-store.md`) — Code-Reuse
ohne Lego-Bruch.

**Display-Stil — Foto kreisförmig, Pikto-Konsistenz.** Familien-Fotos werden
im Display **kreisförmig ausgeschnitten** (CSS `border-radius: 50%` +
`object-fit: cover` auf der `<img>`-Element-Stelle, die heute den Pikto-Pfad
rendert). Damit fügen sich Fotos optisch in den Icon-Stil ein, ohne dass
serverseitig am Foto geschnitten oder freigestellt wird. Kein
Image-Processing, kein Cache-Bust am Backend — reiner CSS-Effekt.

**Display-Konsum (ESSEN-11-Override).** Pro Render-Cycle prüft
`essen/render.py` je Item in dieser Reihenfolge:

1. Gericht mit `foto_ref`-Feld gesetzt → Foto-URL aus Essens-Buddy
   (`/api/v1/essen/fotos/<id>`), kreisförmig stylen.
2. Lebensmittel-Item mit Eintrag in `foto_overrides.json` → Foto-URL aus
   Essens-Buddy (gleiche Mechanik), kreisförmig stylen.
3. Sonst → ARASAAC-Default-Pfad (ESSEN-11), quadratisch wie heute.

Der Essens-Buddy besitzt seine Foto-Daten selbst (APP-3 pro Bounded
Context). Photo-Buddy hält ausschließlich Familien-Album-Inhalte und
wird vom Essens-Display NICHT konsumiert.

**Lösch-Pfad.**

- **Gericht-Foto entfernen:** `foto_ref` aus dem Gericht-Eintrag entfernen
  (DELETE/Update-Pfad). Foto im Photo-Buddy bleibt bestehen (separater
  Lösch-Pfad), Display fällt beim nächsten Reload-on-Read auf den
  ARASAAC-Default zurück, sobald das Gericht wieder ein `bild_ref` bekommt
  oder gar nichts trägt.
- **Basis-Item-Override entfernen:** Eintrag aus `essen/foto_overrides.json`
  raus. Display fällt zurück auf ARASAAC.
- Ein eigener Essens-Foto-Lösch-Skill ist V1.1 nicht nötig — die zwei Pfade
  oben sind über die bestehende Eltern-Chat-Skills (`gericht-loeschen` für
  Gerichte, händische `foto_overrides.json`-Pflege für Basis-Items)
  ausreichend.

**Out-of-Scope V1.1** (jeweils eigenes Ticket, sobald gebraucht):

- **Echtes Freistellen** des Tellers (Hintergrund-Entfernung via ML-Modell
  wie `rembg`/`BackgroundMattingV2`) → V1.2-Welle, eigener Werft-Lauf
  (E-ESSEN-10). Modell-Bibliothek, CPU/GPU-Last und Latenz sind nicht
  triviale Trade-offs. Bis dahin macht der Kreis-Ausschnitt den visuellen
  Job: Fotos passen optisch zu den ARASAAC-Piktos.
- **Mehrere Fotos pro Item** (Karussell). V1.1 trägt genau eins.
- **OpenFoodFacts oder externe Foto-Datenbank** → bleibt OPEN-ESSEN-B,
  eigener Werft-Lauf (E-ESSEN-6).
- **Generisches Photo-Buddy-Tag-Schema** — entfällt. Lego-Trennung wird
  nicht über Tag/Flag/Owner-Felder im Photo-Buddy gelöst, sondern über
  eigene Daten-Heimat pro Buddy (V1.2). Wenn ein dritter Buddy
  Foto-Daten braucht (z.B. Hörspiel-Cover), hält er sie analog
  ESSEN-22b in seinem eigenen Verzeichnis und konsumiert
  `tools/medien_store/` (kein zentraler Foto-Service nötig).
- **Eltern-Chat-Skill für Override-Lösch auf Basis-Items** → solange die
  Pflege selten ist, reicht händische `foto_overrides.json`-Edit.

*Test-Implikationen:*

- **GAN-Pfad-Test:** Anlegen eines Gerichts „Lasagne" mit Foto-Anhang im
  Chat → Essen-Buddy-Foto-API hat ein Medium (`xbuddy-data/essen/fotos/`),
  `gerichte.json` trägt für „Lasagne" `foto_ref` (kein `bild_ref`).
  Photo-Buddy hat KEIN neues Medium.
- **essen_foto_setzen-Test (Gericht):** Foto für existierendes Gericht
  setzen → `foto_ref` im Gericht-Eintrag, alter `bild_ref` weg.
- **essen_foto_setzen-Test (Basis-Item):** Foto für „Apfel" setzen →
  Eintrag in `foto_overrides.json`, `katalog.default.json` unverändert.
- **Render-Test (Override):** Item mit `foto_ref` / Override rendert Foto
  kreisförmig statt ARASAAC.
- **Render-Test (Negativ):** Item ohne Familien-Foto rendert ARASAAC
  quadratisch wie heute.
- **Vor-Routing-Test (Match):** Foto-Anstoß „das ist eine Lasagne" mit
  „Lasagne" im Katalog → `essen_foto_setzen`-Vorschlag.
- **Vor-Routing-Test (Anlegen):** Foto-Anstoß „das ist eine Lasagne" ohne
  „Lasagne" im Katalog → GAN-mit-Foto-Vorschlag.
- **Lösch-Test:** `foto_ref` raus / Override raus → Render fällt auf
  ARASAAC zurück.

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
ESSEN-27 (Display-Lösch-Geste: Entfernen-Symbol ARASAAC 11751 sichtbar an
jeder `liste-eintrag`; Tap löst DELETE auf die richtige ID aus; Liste
rendert neu gemäß ESSEN-20) ·
ESSEN-28 (Render zeigt aktive Optik + disabled-Marker für Items, deren ID
in der Wunschliste vorkommt; Klick auf gesperrte Kachel löst KEINEN POST
aus; nach DELETE auf der Liste wird die Kachel beim nächsten Render wieder
aktivierbar).

*Tickets:* #474

### ESSEN-27 — Display-Lösch-Geste am Wunsch-Listen-Eintrag
Jede `liste-eintrag`-Kachel auf `/display/essen/wunsch` trägt **sichtbar
auf der Kachel** ein Entfernen-Symbol (ARASAAC ID **11751** — „entfernen /
herausnehmen", Gate-B-Wahl 2026-06-10; geliefert über die geteilte Icon-
Plattform ICONS-5: `/display/_shared/icons/arasaac/11751.png`).
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

*Test-Implikation:* der Render zeigt das Entfernen-Symbol (ARASAAC 11751) an
jeder `liste-eintrag`; eine Klick-Simulation auf das Symbol triggert genau
einen DELETE-Request mit der korrekten `data-wunsch-id`; nachfolgender GET
liefert die ID nicht mehr (Reload-on-Read).

*Tickets:* #532

### ESSEN-28 — Wunsch-Kachel-Sperre auf Liste-Lebenszyklus

Eine geklickte Quelle-Kachel auf `/display/essen/wunsch` (die Auswahl-Kacheln,
nicht der Liste-Bereich rechts) erhält sofort eine „aktiv"-Optik (grün-getoned,
Pattern analog `routine-card.done` aus `routine/static/routine.css:135-140`,
vgl. ESSEN-3 Zwei-Tap-Affordanzen). **Solange das Produkt/Gericht (strikt per `item_id`-Match gegen ESSEN-15 —
nicht per `bild_ref`, weil dieser über Katalog-Grenzen kollidieren kann, z. B.
zwei Lebensmittel mit gleichem Piktogramm) auf der aktiven Wunschliste steht**,
ist die Quelle-Kachel funktional und visuell deaktiviert: kein weiterer POST
auslösbar, kein doppelter Listeneintrag möglich. Sobald die Eltern den Eintrag von der Liste nehmen (ESSEN-17 DELETE
oder ESSEN-27 ×-Geste), kehrt die Kachel beim nächsten Render in den
Normal-Zustand zurück.

**Render-Vertrag:** Der Server schreibt an jede Quelle-Kachel, deren `item_id`
in der aktiven Wunschliste vorkommt, das Attribut `data-wunsch-aktiv="true"`
sowie die CSS-Klasse `.kachel-gesperrt`. Die Klasse `.kachel-gesperrt`
deaktiviert den Klick-Handler und setzt die grün-getoned-Optik (wiederverwendet
aus `.routine-card.done`, ESSEN-3-Anker). Kacheln ohne Treffer in der Liste
tragen kein `data-wunsch-aktiv`-Attribut und keine `.kachel-gesperrt`-Klasse.

**Quelle der Wahrheit:** Liste-Stand aus ESSEN-15 (`GET /api/v1/essen/wuensche`),
nicht clientseitig persistiert. Reload-on-Read (ESSEN-20) trägt den Zustand
über Reloads.

**Server-side Duplikat-Schutz:** Die „kein weiterer POST"-Garantie ist
*zusätzlich* server-seitig getragen (ESSEN-16 Duplikat-Schutz, 409 Conflict
bei wiederholter `item_id`). Damit hängt der Vertrag nicht am Client-Guard
allein — künftige Schreib-Pfade (Eltern-Chat-Schreib-Skill, OPEN-ESSEN-A)
erben die Garantie automatisch.

**Bewusst NICHT in V1:** Tageswechsel-Reset, Pro-Session-Sperre,
Bestätigungs-Dialog. Diese Optionen B/C aus #666 wurden zugunsten von Wahl A
(Liste-Lebenszyklus-Sperre) verworfen.

*Test-Implikation:* Render zeigt aktive Optik + `.kachel-gesperrt`-Marker für
Items, deren ID in der Wunschliste vorkommt; Klick auf gesperrte Kachel löst
KEINEN POST aus; nach DELETE auf der Liste (`DELETE /api/v1/essen/wuensche/<id>`,
ESSEN-17) wird die Kachel beim nächsten Render wieder aktivierbar (kein
`data-wunsch-aktiv`, keine `.kachel-gesperrt`-Klasse).

*Tickets:* #666

## 9. Eltern-Einkaufsliste (V1, #653)

Die Eltern-Einkaufsliste (Mama im Supermarkt) lebt **auf demselben Wunsch-
Datenmodell** wie die Display-Wunsch-Liste, getrennt nur über `klasse`
(ESSEN-4): `klasse=wunsch` für Display-/Kind-Pfad, `klasse=einkauf` für den
Eltern-Schreibpfad. Werkzeug-Wahl ist **Telegram Mini App** (kein pinned
Inline-Keyboard — Nic 2026-06-11, E-ESSEN-11).

### ESSEN-29 — Listen-Grenze und Komplett-Ablehnung beim Hinzufügen

Vor jedem `POST /api/v1/essen/wuensche` (ESSEN-16) prüft der Buddy die
Anzahl der **offenen** Einträge (`abgehakt=false`) gegen die Listen-
Grenze. Default: **100** offene Einträge **je File** (= je `klasse`,
ESSEN-7) — getrennte Grenzen pro Liste, weil Wunsch-Liste und Einkaufs-
Liste unterschiedliche UI-Belastung erzeugen. Override per
`essen/config.json::listen_grenze_wunsch` und `listen_grenze_einkauf`
(beide Default 100). Übergangs-Schlüssel `listen_grenze` (V1-Schärfung)
greift für beide Listen, wenn die spezifischen Overrides fehlen.

**Wenn** ein POST die Summe `offene_jetzt + 1` (oder `+N` bei
Batch-Eingabe via ESSEN-30 Übernahme) die Grenze **überschreiten** würde,
**dann** lehnt der Buddy den **gesamten** Vorgang mit **413 Payload Too Large**
ab (kein partielles Anlegen). Antwort-Body: `{ "error": "listen_grenze",
"offen_jetzt": <N>, "grenze": <N> }`. Der konsumierende Skill darf das in
eine Klartext-Antwort an Eltern übersetzen („Liste hat schon <N> offene
Items, mehr passt nicht — erst aufräumen").

**Begründung:** UI-Lesbarkeit (Mini App + Bot-Übersichts-Nachricht), nicht
Storage. Default 100 ist mit Reserve gewählt — der konsumierende Skill kann
früher warnen (z. B. ab 80) ohne Server-Änderung.

**Bewusst NICHT in V1:** Soft-Warnung im Server, Soft-Limit pro `klasse`,
Soft-Limit pro `quelle`. Eine harte Decke je Liste, keine differenzierte
Limit-Verwaltung.

*Test-Implikation:* `POST` mit `offene_jetzt = 99` und Batch-Size 1 → 201;
Batch-Size 2 → 413 mit Body wie oben; keine Persistenz. Override
`listen_grenze = 5` und Versuch eines POST über 5 offene Items → 413. Ein
abgehakter Eintrag zählt nicht zur Grenze (`abgehakt=true` ist ausgenommen).

*Tickets:* #653

### ESSEN-30 — Wunsch-Gericht-Übernahme mit Pro-Zutat-Auswahl

**Auslöser:** Eltern öffnet die Mini-App-View (ESSEN-31) und tippt einen
Eintrag mit `klasse=wunsch` UND `kategorie=gericht` (z. B. Lasagne) UND das
Gericht hat im Katalog mindestens eine Zutat (ESSEN-19 `zutaten`-Feld).

Statt direktem Abhaken öffnet die Mini App ein **Übernahme-Sheet** (Bottom-
Sheet) mit folgendem Inhalt:

- Titel: „🧒 Kinder wünschen sich <Gericht>"
- Pro Zutat eine Zeile mit Piktogramm, Label und Auswahl-Häkchen.
- **Smart-Default Auswahl:** alle Zutaten ausgewählt, **außer** die Zutat
  ist schon **offen** auf der Liste (Match `label`-case-insensitiv,
  unabhängig von `klasse`). Solche Zutaten sind initial ausgeschlossen mit
  Hinweis-Text „· schon drauf".
- Tap auf eine Zutat-Zeile toggelt die Auswahl (Eltern kann eine schon-
  drauf-Zutat wieder reinholen oder eine vorgewählte rausnehmen).
- Counter im Confirm-Button live: „✓ N Zutaten auf die Liste" / „Nichts
  dazunehmen" (disabled, wenn Auswahl leer UND keine schon-drauf-Zutaten).
- Drei-Wege-Wahl unten:
  - **„✓ N Zutaten auf die Liste"** → wandert in den Bestätigungs-Pfad
    (siehe unten).
  - **„Nur abhaken"** → kein Zutaten-Hinzufügen; das Wunsch-Gericht selbst
    wird auf `abgehakt=true` gesetzt (PATCH).
  - **„Abbrechen"** → Sheet schließt, nichts ändert sich.

**Bestätigungs-Pfad „Zutaten übernehmen":**

1. Für jede ausgewählte Zutat ein `POST /api/v1/essen/wuensche` mit
   `klasse=einkauf`, `quelle=eltern`, `aus_gericht=<Gericht-Label>`,
   `label`/`kategorie`/`bild_ref`/`item_id` aus dem Zutaten-Eintrag des
   Gerichts.
2. **Dedupe-Regel:** Wenn eine Zutat schon offen auf der Liste ist
   (`label`-Match) UND `aus_gericht` noch leer, wird KEIN neuer Eintrag
   angelegt, sondern der bestehende Eintrag um das `aus_gericht`-Feld
   ergänzt (PATCH `/api/v1/essen/wuensche/<id>`, ESSEN-32). Ist
   `aus_gericht` schon gesetzt: gar kein Effekt (Idempotent).
3. Das Wunsch-Gericht selbst wird `abgehakt=true` (PATCH).
4. Listen-Grenze ESSEN-29 greift auf die Gesamt-Übernahme: wenn die N
   Zutaten die Grenze sprengen würden, lehnt der Buddy den **gesamten**
   Übernahme-Vorgang ab (kein partielles Anlegen). Das Wunsch-Gericht
   bleibt offen, das Sheet schließt mit Klartext-Hinweis.

**Edge-Case „Gericht ohne Zutaten":** wenn `GET /api/v1/essen/katalog
/gerichte/<id>` ein leeres `zutaten`-Array liefert, öffnet die Mini App
**kein** Übernahme-Sheet — stattdessen Klartext-Hinweis „Lasagne hat
keine Zutaten im Katalog hinterlegt. Tap nochmal, um den Wunsch
abzuhaken." Zweiter Tap setzt `abgehakt=true`.

**Wenn** Eltern tippt 🧒-Gericht „Lasagne" (5 Zutaten, keine schon drauf),
wählt 4 aus, tippt „Auf die Liste", **dann** entstehen 4 neue Einträge
`klasse=einkauf`, `aus_gericht="Lasagne"`, Lasagne selbst hat
`abgehakt=true`. Die ausgelassene Zutat bleibt unberührt.

*Test-Implikation:* Mini-App-Tap auf 🧒-Gericht mit `zutaten=[a,b,c]` →
Sheet öffnet, alle drei vorausgewählt. UI-Test des Auswahl-Toggles.
Confirm-Pfad mit 2 ausgewählten Zutaten → 2 POSTs, Wunsch-Gericht PATCH
`abgehakt=true`. Dedupe-Test: Zutat „Mozzarella" ist schon offen → vorbe-
legter Toggle aus, bei Confirm PATCH auf bestehende ID statt POST. Limit-
Test: Übernahme würde Grenze sprengen → 413 für den Übernahme-Vorgang
(kein Zutaten-Eintrag, Wunsch-Gericht bleibt offen).

*Tickets:* #653

### ESSEN-31 — Eltern-Mini-App-View (Layout + Bild-Pfad)

Die Eltern-Mini-App-View für die Einkaufsliste rendert eine Liste aller
Einträge (egal welche `klasse`/`quelle`) als **Bring!-typische Card-Liste**
gruppiert nach `kategorie`, mit drei sichtbaren Quellen-Markern:

- **🧒** für `klasse=wunsch` (Kinder-/Display-Quelle).
- **📖** für `klasse=einkauf` mit gesetztem `aus_gericht` (Rezept-Zutat).
- **(kein Marker)** für `klasse=einkauf` ohne `aus_gericht` (Eltern
  explizit aufgeschrieben).

**Reihenfolge innerhalb einer Kategorie (nur offene Items):**
Wunsch zuerst → Rezept-Zutaten → Eltern-explizit. Die Kategorie-Sektionen
führen ausschließlich offene Items (`abgehakt=false`).

**Erledigt-Block am Listen-Ende:**
Erledigte Items (`abgehakt=true`) werden aus der Kategorie-Gruppierung
herausgezogen und in einer eigenen flachen Sektion `Erledigt · N` **am
Ende der gesamten Liste** gerendert (nach allen Kategorie-Sektionen, ohne
Kategorie-Untergruppe). Optik bleibt reduziert (ausgegraut, Häkchen grün
gefüllt). Sektion ist nicht eingeklappt — Eltern sehen, was schon erledigt
ist. Beim Rück-Toggle (`abgehakt=true` → `false`) rutscht das Item zurück
in seine Kategorie-Sektion an die übliche Position innerhalb der Reihen-
folge.

**Reihenfolge der Kategorien:**
1. **Wunsch-Gerichte** (Kategorie `gericht`, nur 🧒-Marker — Eltern-
   Einkauf-Items in `gericht` sind in V1 unzulässig, weil Gerichte
   gekocht und nicht eingekauft werden).
2. **Obst & Gemüse**.
3. **Brotbelag**.
4. **Sonstiges**.

**Sektion-Header je Kategorie** zeigt die Aufteilung der **offenen** Items:
`Obst & Gemüse · N` mit `+ 📖 R + 🧒 W`, wenn Rezept-Zutaten R bzw. Wunsch-
Items W unter den offenen vorhanden sind (Format-Beispiel `Sonstiges · 11
+ 📖 3 + 🧒 1`). Erledigte zählen nicht mit (sie liegen im Erledigt-Block
am Listen-Ende, dessen Header `Erledigt · N` die Gesamtzahl trägt).

**Bild-Pfad:** Mini App fordert die ARASAAC-PNGs **vom selben Host** unter
`/display/_shared/icons/arasaac/<bild_ref>.png` an (ICONS-5 + ROU-26,
Same-Origin-Lego, kein CORS). Lade-Fehler einzelner Bilder rendern Placeholder
(Bring!-Default-Stoff/Cart-Symbol), kein UI-Bruch. Wortlaut-Patch #1011.

**Tap-Routing pro Card:**
- `klasse=wunsch` + `kategorie=gericht` + Gericht hat Zutaten → ESSEN-30
  Übernahme-Sheet.
- `klasse=wunsch` + Gericht ohne Zutaten → Klartext-Sheet (siehe ESSEN-30).
- Alle anderen Karten → direkter `abgehakt`-Toggle (PATCH).

**Quick-Add direkt in der Mini App:** ➕-Button (Floating Action Button)
öffnet ein Bottom-Sheet mit Text-Input. Komma-/Semikolon-getrennt
mehrere Items in einem Rutsch. Per Default `kategorie=sonstiges`. Auto-
Match auf bekannte Items aus dem Katalog (ICONS-7-Such-API + Katalog-
Lookup über `label` case-insensitiv) setzt `kategorie` automatisch korrekt,
wenn ein eindeutiges Match existiert. Sonst bleibt `sonstiges`. Buddy-
seitig per ESSEN-16 angelegt mit `klasse=einkauf`.

**Auth:** Die Mini App lädt nur auf gültige Telegram-`initData`-Signatur
(HMAC mit Bot-Token, geprüft durch den `seiten`-Service / Buddy-Service —
Architektur-Frage in der Lego-Basis, MVP-Sammler-Ticket #678).

*Test-Implikation (Verhaltens-Probe-Liste, analog ROUTINE-20):* die
folgenden konkreten Proben gelten als Akzeptanz und werden als
Frontend-Verhaltens-Tests umgesetzt (Mechanik Code-Track-Sache — DOM-Attrappe
oder jsdom-Wrapper, siehe Code-Track-Folge-Ticket):

- **Render-Reihenfolge:** Render-Test mit gemischter Liste (1 Wunsch-Gericht +
  2 Rezept-Zutaten + 3 Eltern-Items + 1 erledigtes) → Mini App zeigt vier
  Kategorien (oder die nicht-leeren) in fester Reihenfolge (Wunsch-Gerichte,
  Obst & Gemüse, Brotbelag, Sonstiges), gefüllt **nur mit den offenen Items**.
  Sektion-Header trägt die Aufteilung der Offenen (`Sonstiges · 4 + 📖 1 +
  🧒 0`-Format). Das erledigte Item liegt nicht in seiner Kategorie, sondern
  in der eigenen flachen Sektion `Erledigt · 1` am Listen-Ende (mit
  ausgegrauter Optik + grünem Häkchen).
- **Quellen-Marker:** in jeder Card steht exakt **ein** Marker — `🧒` bei
  `klasse=wunsch`, `📖` bei `klasse=einkauf` mit gesetztem `aus_gericht`,
  **kein** Marker bei `klasse=einkauf` ohne `aus_gericht`.
- **Tap auf 🧒-Gericht-Card mit Zutaten** → öffnet Übernahme-Sheet (ESSEN-30),
  kein PATCH-fetch.
- **Tap auf Wunsch-Lebensmittel-Card** → genau **ein** `fetch`-Aufruf
  `PATCH /api/v1/essen/wuensche/<id>` mit Body `{abgehakt: true}` (bzw.
  `false` beim Rück-Toggle).
- **Quick-Add mit Komma-Liste** („Brot, Milch") → genau **zwei** `fetch`-
  Aufrufe `POST /api/v1/essen/wuensche` mit je `{label: "Brot", ...}` bzw.
  `{label: "Milch", ...}`. `kategorie` ist `sonstiges` als Default; mit
  bekannten Items im ICONS-7/Katalog-Match wird `kategorie` korrekt gesetzt.
- **Bild-Pfad:** alle gerenderten `<img>` haben `src`, der mit
  `/display/_shared/icons/arasaac/` beginnt und auf `.png` endet
  (Same-Origin-Lego, kein CORS, keine externen Hosts).
- **Bild-Lade-Fehler:** wenn `<img>` ein `error`-Event feuert, rendert das
  Mini-Frontend einen Placeholder (Bring!-Default-Stoff/Cart), das UI bricht
  nicht.

Diese Probe-Liste ist Bauplan für das jeweilige Frontend-Verhaltens-
Test-Modul (Skill-/Render-Layer, nicht Pixel-Layer).

*Tickets:* #653

### ESSEN-32 — `PATCH /api/v1/essen/wuensche/<id>` — Eintrag aktualisieren

Aktualisiert ein bestehendes Wunsch-/Einkaufs-Item. **In V1 exposed**
(interface-first). **Konsumenten:**
- die Eltern-Mini-App (Tap-Toggle → `abgehakt`).
- der Skill `einkauf-hinzufuegen` (ESSEN-30 Dedupe-Pfad → setzt `aus_gericht`
  auf bestehende Einträge).

**Payload (JSON-Body, alle Felder optional, sparse update):**
- `abgehakt` (bool) — neue Markierung. Wenn `true`, setzt der Buddy automatisch
  `abgehakt_von` (aus dem Eltern-/Familien-Auth) und `abgehakt_am` (jetzt-ISO).
  Wenn `false`, leert er beide.
- `aus_gericht` (string) — Quellen-Vermerk (nur wenn `klasse=einkauf`, sonst
  400).

**Fachliche Validierung:** ID muss existieren (sonst 404). Klassen-Felder
(`klasse`/`quelle`/`label`/`kategorie`/`item_id`/`bild_ref`) sind **nicht** per
PATCH änderbar — nur die Lebenszyklus-Felder. Unbekannte Felder im Payload →
ignorieren (nicht 400 — Vorwärtskompatibilität).

**Antwort:** 200 mit dem aktualisierten Eintrag (volle Form wie GET-Element).

*Test-Implikation:* PATCH `{abgehakt: true}` → 200, GET zeigt
`abgehakt=true`, `abgehakt_von`/`abgehakt_am` gesetzt. PATCH
`{abgehakt: false}` auf denselben Eintrag → leert `abgehakt_von`/
`abgehakt_am`. PATCH `{label: "X"}` → ignoriert (Antwort hat `label`
unverändert). PATCH auf unbekannte ID → 404. PATCH
`{aus_gericht: "Lasagne"}` auf Eintrag mit `klasse=wunsch` → 400.

*Tickets:* #653

### ESSEN-33 — Eltern-Mini-App als installierbare PWA (Phase-1-Mantel)

Die Eltern-Mini-App für die Einkaufsliste wird als **installierbare PWA**
ausgeliefert, damit Eltern sie per „Zum Home-Bildschirm hinzufügen" als
1-Tap-Icon auf iPhone und Android verankern können (Bring!-Benchmark). Sie
folgt `conventions/pwa.md` PWA-1..PWA-4 **analog** (n=1-Experiment einer
dritten Konsumenten-Klasse „Power-Flow-PWA unter `seiten/static/<flow>/`";
die Konvention selbst wird **nicht** in dieser Phase erweitert — siehe
Schluss-Note dieser Klausel).

**Pflicht-Dateien neben `essen-einkauf.html`** (analog `conventions/pwa.md`
PWA-1, PANEL-10):

- `essen-einkauf.html` — Einstiegspunkt; bindet `manifest.json` per
  `<link rel="manifest" href="./manifest.json">` ein und registriert
  `sw.js` als Service-Worker.
- `manifest.json` — Web App Manifest mit den PWA-2-Pflichtfeldern:
  `name`, `short_name`, `start_url: "./"`, `display: "fullscreen"`,
  `orientation`, `background_color`, `theme_color`, mindestens zwei Icons
  (192×192 + 512×512 PNG, davon mind. eines mit `purpose: "maskable"`).
- `sw.js` — Service-Worker, beim Laden im Document registriert, mit
  `fetch`-Handler (sonst verweigert Chrome den WebAPK-Install-Trigger).
- Icons: `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`.

**Wake-Lock + Fullscreen** (analog `conventions/pwa.md` PWA-3): die Seite
fordert beim Laden `navigator.wakeLock.request('screen')` an und holt ihn
bei jedem `visibilitychange`-Event nach. Fullscreen wird aus einem
abgeschlossenen Nutzer-Gesture (`touchend`/`click`) per
`requestFullscreen` angefordert. Best-effort: fehlt eine API oder schlägt
sie fehl, läuft die Seite weiter und protokolliert `console.warn` — kein
UI-Bruch.

**Out-of-Scope dieser Phase** (Setzungs-Update 2026-06-18, siehe #948
und Memory `project_xbuddy_pwa_first_power_flow.md`):
- Cookie-Auth-Andockung (`BrowserPlatform.ensureAuth` bleibt V1-Pragma
  `return true`; `/auth/pair`-Endpunkt + Cookie-Lib aus #948 wandern in
  Plan B).
- Konventions-Erweiterung von `conventions/pwa.md` um die dritte
  Konsumenten-Klasse — wandert in eigenes Folge-Ticket „nach
  Phase-1-Bewährung" (Trigger: 5-Tage-Realtest erfolgreich **und**
  n=2 routine-anpassen-PWA als zweites Beispiel gebaut; folgt der
  n=2-Regel aus Memory `feedback_berater_zwei_gebaute_beispiele.md`).

*Test-Implikation:* die folgenden Pfade liefern die ESSEN-34-vorgegebenen
Acceptance-Antworten. Visuelle Probe (Phase-1-Abschluss): auf iPhone
Safari und Android Chrome erscheint der „Zum Home-Bildschirm
hinzufügen"-Prompt; nach Install öffnet ein Tap das Icon randlos ohne
Browser-Chrome.

*Tickets:* #949 · *Verweis:* `conventions/pwa.md` (PWA-1..PWA-4 analog),
PANEL-10, ROU-23 (Asset-Routing-Vorbild).

### ESSEN-34 — Asset-Auslieferung am Mini-App-Pfad

Die PWA-Assets (Manifest, Service-Worker, Icons) werden vom **selben URL-
Pfad** wie `essen-einkauf.html` ausgeliefert, **nicht** unter dem
generischen `/seiten/static/`-Pfad. Das ist Pflicht für PWA-Mechanik:
relative Verweise (`./manifest.json`) müssen vom HTML aus auflösen,
Service-Worker-Scope wird automatisch auf das `sw.js`-Verzeichnis
beschränkt, und der WebAPK-Install-Trigger akzeptiert nur ein Manifest,
das ohne Cross-Origin-/Pfad-Sprung erreichbar ist (ROU-23-Vorbild).

Konkrete URL-Form (analog ROU-23 für Controller-PWAs):

Sowohl die Form ohne Trailing-Slash als auch die Form mit Trailing-Slash sind zulässig; die Trailing-Slash-Form ist die `start_url` der installierten PWA.

| Pfad | Antwort |
|---|---|
| `GET /seiten/essen/einkauf` | 200, `text/html`, Inhalt aus `essen-einkauf.html` |
| `GET /seiten/essen/einkauf/` | 200, `text/html` (PWA-Install start_url, ESSEN-33) |
| `GET /seiten/essen/einkauf/manifest.json` | 200, `application/manifest+json` |
| `GET /seiten/essen/einkauf/sw.js` | 200, `application/javascript` |
| `GET /seiten/essen/einkauf/icon-192.png` | 200, `image/png` |
| `GET /seiten/essen/einkauf/icon-512.png` | 200, `image/png` |
| `GET /seiten/essen/einkauf/icon-maskable-512.png` | 200, `image/png` |
| Pfad außerhalb des Mini-App-Wurzelverzeichnisses (Path-Traversal) | 404 |
| Nicht existierendes Asset im Mini-App-Verzeichnis | 404 |

Der Code-Track entscheidet, **wo** die Asset-Dateien physisch im Repo
liegen — die Spec verlangt nur, dass sie unter dem oben genannten
URL-Pfad erreichbar sind. Naheliegende Ablage (im Sinne der Lego-Trennung
und ROU-23-Analogie): unter `seiten/static/einkauf/` neben den Icons,
Flask-Route in `seiten/main.py` analog der bestehenden HTML-Route
`/seiten/essen/einkauf`. Path-Traversal-Schutz (`realpath`-Check)
zwingend, kein Dateizugriff jenseits des Mini-App-Wurzelverzeichnisses.

**Service-Worker-Scope:** Da `sw.js` unter `/seiten/essen/einkauf/sw.js`
liegt, kontrolliert die PWA per Default nur ihren eigenen
Mini-App-Namensraum `/seiten/essen/einkauf/` — nicht den ganzen
`/seiten/`-Prefix. Andere Mini-Apps (z. B. `mini-app-uebersicht`,
`routine-anpassen`) bleiben außerhalb des PWA-Caches.

*Tickets:* #949

### ESSEN-35 — Service-Worker-Cache-Strategie

Der Service-Worker cached **selektiv**:

- **Cache-first** für statische Mantel-Assets: `essen-einkauf.html`,
  `/seiten/static/essen-einkauf.js`, `/seiten/static/essen-einkauf.css`,
  `/seiten/static/platform.js`, `manifest.json`, alle Icons unter dem
  Mini-App-Pfad. Damit der Install-Trigger und kurze Netz-Aussetzer
  keinen White-Screen erzeugen und die App wie eine native Familien-App
  startet.
- **Pass-through** (network only) für API-Aufrufe: alles unter
  `/api/v1/essen/*` wird **nicht** gecached — Listen-Inhalte sind live,
  ein veralteter Cache-Snapshot wäre für Eltern beim Einkauf gefährlich
  (sie würden bereits eingekaufte Items erneut kaufen).
- **Network-first mit Cache-Fallback** für ARASAAC-Piktogramme unter
  `/display/_shared/icons/arasaac/<id>.png` (ICONS-5 + ROU-26, ESSEN-31):
  erst Netz probieren, bei Offline Cache verwenden, bei Cache-Miss
  Placeholder-Rendering durch die Render-Funktion (ESSEN-31 Bild-Lade-Fehler).

**Cache-Versionierung:** Der Service-Worker nutzt einen Cache-Namen mit
`build_id` (vgl. Memory `reference_mini_app_cache_buster.md`); bei jedem
Deploy invalidiert ein neuer `build_id` den alten Cache (`activate`-
Event löscht alte Cache-Namespaces). Damit greift der bestehende
Cache-Buster-Mechanismus (`?v={{ build_id }}` an Asset-URLs) auch im
Service-Worker, und Eltern sehen Iter-Änderungen ohne manuellen
„Hard-Reload".

*Test-Implikation:* nach Install-and-Reload (PWA gestartet, dann
offline) lädt `essen-einkauf.html` aus Cache; ein `GET
/api/v1/essen/wuensche` schlägt fehl (kein gecachter API-Response).
Nach Deploy mit neuer `build_id` invalidiert der Service-Worker den
alten Cache (`caches.keys()` enthält nach `activate` nur den neuen
Namespace).

*Tickets:* #949

### ESSEN-36 — MAD-5-Cleanup im Phase-1-PR (Hygiene, Auth-unabhängig)

Mit dem PWA-Mantel wird **auch** die MAD-5-Disziplin (`conventions/mini-
app-design.md` MAD-5) in `seiten/static/essen-einkauf.js` umgesetzt: alle
direkten Zugriffe auf `window.Telegram.WebApp.initData` (heute
`essen-einkauf.js:29-32, 68-70, 91-97, 125-130`) werden durch einen
`platform.authHeaders()`-Wrapper in `seiten/static/platform.js`
zentralisiert. Der Wrapper gibt heute `{Authorization: 'tma ' +
initData}` zurück; eine spätere Cookie-Pfad-Erweiterung (Plan B, #948)
kann die Funktion erweitern, ohne dass `essen-einkauf.js` erneut
angefasst wird.

**Begründung der Mit-Auslieferung:** MAD-5 ist eine Mini-App-Konvention,
die unabhängig von Cookie-Auth gilt — direkter `initData`-Zugriff ist
Lego-Bruch, weil künftige Auth-/Identity-Erweiterungen jedes Mini-App-JS
einzeln anfassen müssten. Der MAD-5-Cleanup wandert deshalb **nicht** mit
der Auth-Andockung in #948, sondern bleibt Teil von Phase-1 (Setzungs-
Update 2026-06-18, Klarstellung der MAD-5-Frage im prep-Verlauf).

**Stell-Probe:** nach dem Phase-1-PR enthält
`seiten/static/essen-einkauf.js` keinen direkten
`window.Telegram.WebApp.initData`-Zugriff mehr (Grep findet 0 Treffer);
alle API-Aufrufe nutzen `platform.authHeaders()` aus
`seiten/static/platform.js`.

*Tickets:* #949 · *Verweis:* `conventions/mini-app-design.md` MAD-5.

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
  - **TEIL-ERLEDIGT 2026-06-11 durch #653:** die zwei Einkaufs-Skills
    `einkauf-hinzufuegen` (EIN) und `einkauf-zeigen` (EZG) sind in
    `specs/platform/einkauf-hinzufuegen.md` und `specs/platform/einkauf-zeigen.md`
    spezifiziert. Sie tragen `klasse=einkauf`. Die drei Wunsch-Pflege-Skills
    (WHZ/WLO/WLE) bleiben offen, da sie `klasse=wunsch` pflegen.

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
  `brainstorm/idee-mvp/essen/mockups/variante-A-tabbed.html` (internes
  Deliberations-Artefakt, nicht Teil des public Repos). Spec ESSEN-2 /
  ESSEN-3 / ESSEN-8 / ESSEN-9 / E-ESSEN-7 entsprechend reconcilet.

- **OPEN-ESSEN-F — ARASAAC-Abdeckungsprüfung Lebensmittel-Domäne.** ERLEDIGT
  2026-06-09 (Werft-Lauf #474, vor Gate B): alle 20 Repo-Default-Items in den
  drei Lebensmittel-Kategorien (8 Obst&Gemüse · 6 Brotbelag · 6 Sonstiges)
  haben verifizierte ARASAAC-IDs mit CDN-Render-Beleg. Befund-Artefakt:
  `brainstorm/idee-mvp/essen/arasaac-probe/befund.md`. Repo-Default-Vorschlag:
  `brainstorm/idee-mvp/essen/mockups/katalog.default.json` (beides interne
  Deliberations-Artefakte, nicht Teil des public Repos). Spec ESSEN-12
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
unter `brainstorm/idee-mvp/essen/mockups/variante-A-tabbed.html` (internes
Deliberations-Artefakt, nicht Teil des public Repos).

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

### E-ESSEN-11 — Eltern-Einkaufsliste ist Mini App, nicht pinned Inline-Keyboard

*Datum:* 2026-06-11 · Die Eltern-Einkaufsliste in Telegram wird als
**Mini App** ausgeliefert (HTML/CSS/JS-Frontend mit Init-Data-Auth,
gehostet am selben Pi wie der Display-Service). **Verworfen:** pinned
Inline-Keyboard in der Familien-Gruppe als Lösungs-Form (Werft-Iteration
V1–V6 in `brainstorm/idee-mvp/essen-einkauf/mockups/`, internes
Deliberations-Artefakt, nicht Teil des public Repos — Mockup-
Konvergenz, aber durch Nic-Tiebreaker 2026-06-11 verworfen, weil
Werkzeug-Wahl die Lego-Konsistenz mit Routine-/Übersicht-Funktionen
bricht und ARASAAC-Bilder mit pinned Inline-Keyboard nicht möglich
sind — Telegram-API-Limit).

**Verworfene Form-Erkenntnisse leben weiter:**

- Drei Quellen-Marker 🧒 / 📖 / plain als visuelle Trennung (ESSEN-31).
- Hybrid-Layout (Wunsch-Lebensmittel in Kategorie, Wunsch-Gerichte oben,
  ESSEN-31).
- Wunsch-Gericht-Übernahme-Geste mit Zutaten-Dialog (ESSEN-30).
- Listen-Grenze als Robustheits-Klausel (ESSEN-29).

**Plattform-Ebene:** Telegram als MVP-Plattform, Matrix vertagt mit Trigger
(RAT-16, MVP-Sammler #678).

**Werft-Trail** (interne Deliberations-Artefakte, nicht Teil des public
Repos): F1-Rahmung in `brainstorm/idee-mvp/essen-einkauf/gate-a-
vorbereitung.md`, Mockup V7 als Gate-B-Wahl `brainstorm/idee-mvp/essen-
einkauf/mockups/telegram-mini-app-v7-chat-flow.html`. Das Schärfungs-Ergebnis
der Berater-Runde 2026-06-11 steht public in `decisions/RAT-16` (Nachtrag).

### E-ESSEN-12 — DB nach `klasse` aufbohren (zwei Files), nicht View-Filter

*Datum:* 2026-06-11 (Nic, Robustheits-Schärfung nach Werft-Abschluss) ·
Die Persistenz trennt strukturell nach `klasse`: `essen/wuensche.json`
für `klasse=wunsch`, `essen/einkaufsliste.json` für `klasse=einkauf`
(ESSEN-7). Der Display-View liest **nur** die Wunsch-Datei, die Einkauf-
Mini-App liest standardmäßig **nur** die Einkauf-Datei. Damit ist die
Korrektheit „Display rendert keine Eltern-Einkauf-Items" durch das
**DB-Schema** garantiert, nicht durch korrekte Filter-Anwendung im
Render-Code.

**Verworfen:**
- **Ein File `wuensche.json` mit `klasse`-Feld**, View filtert beim Read.
  Bricht bei Filter-Code-Drift (Bug-Risiko: ein vergessener
  `?klasse=wunsch`-Query, ein nicht-fingerprint-validierter Code-Pfad).
  Robustheit lebt im Anwendungs-Code, nicht im Datenmodell.
- **SQLite mit `klasse`-Column und Index.** Komplexitäts-Falle für eine
  Familien-3-Liste; JSON-Files + Last-Known-Good + atomares Schreiben
  reichen vollkommen. SQLite würde Migrations-, Backup-, und Korruptions-
  Strategien dazustellen, die wir heute nicht brauchen (Familien-3-Probe).

**Was die Trennung kostet:** GET ohne Klasse-Filter muss zwei Files
lesen und mergen — pro Request zwei Reload-on-Read-Operationen statt
einer. Bei Familien-3-Listen kein messbarer Performance-Effekt.

**ID-Eindeutigkeit:** der Quellen-Zähler (ESSEN-5) bleibt **global** über
beide Files (`essen/zaehler.json`), damit IDs nie zwischen den Files
kollidieren. PATCH/DELETE auf `<id>` suchen den Eintrag in beiden Files;
genau ein File enthält die ID, der Buddy weiß ohne expliziten Klasse-
Hinweis welches File zu modifizieren ist.

**Robustheits-Gewinn (Familien-3-Realität):** wenn eine der zwei Dateien
korrumpiert wird (Reboot mitten im atomaren Write, Disk-Voll, manuelles
Editieren), läuft der andere Pfad ungestört weiter. Last-Known-Good
(DCOMP-3) je File. Crash-Resilienz pro Klasse statt globaler Single-
Point-of-Failure.

**Werft-Trail:** Schärfung als Folge-Frage Nic 2026-06-11 nach dem ersten
Werft-Abschluss (Spec-PR #683 merged). Ratifizierung als Spec-Nachzug-PR
ohne weitere Berater-Runde — Robustheits-Klausel, kein Architektur-
Konflikt mit RAT-16 oder E-ESSEN-11.
