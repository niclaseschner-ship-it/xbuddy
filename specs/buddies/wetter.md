# Wetter-Buddy — Spec     (ID-Präfix: WETTER)

> Status: V1 · Refs #137

## Problem & North-Star-Bezug

Eltern müssen morgens für die Kinder die Wetter-App öffnen und übersetzen, was sie
anziehen sollen. Die Kinder gehen in den **Waldkindergarten** (8:00–13:00, ganzen
Tag draußen). Der Wetter-Buddy gibt dem Kind **selbst** Zugang zu dem, was es
braucht: Wie warm wird es? Regnet es, und wie viel? Was muss ich anziehen, was ist
optional? Besonders wichtig: das Kind sieht **selbst, wann Sonnencreme gebraucht
wird**. Das verschiebt eine Aufgabe vom Elternteil zum Kind (North Star) und gibt
ihm Freiraum, in einem gewissen Rahmen selbst zu entscheiden.

Der Wetter-Buddy ist eine eigenständige XBuddy-**App** mit einer Display-View —
einem **Diptychon** aus Wetter-Karte („Wie ist das Wetter heute?") und
Anziehen-Karte („Was zieh ich an?"). Als App **besitzt** er seine Daten (Ort und
Garderoben-Regeln) und seine Funktion (die Wetter-Anbindung) und stellt das
Ergebnis über die View bereit (WETTER-1, APP-1).

**V1-Scope:** Single-Page-View `heute` als Diptychon · Mitwachsen-Stufe
`toddler` (3–6 J, noch nicht lesend) als einzige V1-Stufe · zwei Tageszeiten
(Morgens + Mittags) gleichzeitig · Abend-Rollover auf morgen · Wetter-Metriken als
Bilder statt Zahlen · kindgerechte Darstellung **ohne sichtbaren UV-Wert**
(Sonnencreme als abgeleitete Ja/Nein-Empfehlung) · Empfehlung nach **gefühlter
Temperatur** · Garderoben-Regeln (inkl. Mützen- und Regen-/Matsch-Logik) und Ort
als Per-Instanz-Daten · zweistufige Iconografie (Lucide/ARASAAC) mit Attribution ·
Anbindung an Open-Meteo · **keine** API für andere Apps · eigener Service ·
**raumfüllende Darstellung mit einheitlicher Schriftgröße** (Lesbarkeit, WETTER-25).

**Out-of-Scope V1** (je eigenes Ticket): die `reader`-Stufe (OPEN-WETTER-A) · eine
Lese-API `/api/v1/wetter/` für andere Apps (OPEN-WETTER-B) · Mehrtages-Vorhersage
und mehrere Orte (OPEN-WETTER-C) · jegliche Interaktion *(V1.1 ergänzt die
eltern-seitige Garderoben-Editor-Seite, §10 — eine Eltern-Oberfläche, kein
Kiosk-View)* · Anbieter-Cache / Offline-Last-Known-Good
(OPEN-WETTER-E) · Controller-Trigger / Erreichbarkeit jenseits Dauer-Kiosk (F4/F5).

## 1. Die App & ihre View

### WETTER-1 — Wetter-Buddy ist eine App mit eigenem Besitz
Der Wetter-Buddy ist die XBuddy-App mit dem Buddy-Slug `wetter`. Er besitzt seine
**Daten** (Ort und Garderoben-Regeln, WETTER-21), seine **Funktion** (die
Wetter-Anbindung, Abschnitt 5) und stellt das Ergebnis über seine **Display-View**
bereit (APP-1). Der Ort liegt mangels Ort-Feld in der Familien-Registry (FAM-3)
als App-eigene Config. V1 exponiert **keine** API für andere Apps (E-WETTER-3).

### WETTER-2 — Single-Page-View `heute`, Diptychon
Die View liegt unter `/display/wetter/heute` (URL-2, URL-7) und ist eine
**einzige Canvas** — kein Routing, kein Tab, kein Toggle, keine Settings. Sie zeigt
zwei nebeneinanderliegende Karten: links die **Wetter-Karte** (Abschnitt 3),
rechts die **Anziehen-Karte** (Abschnitt 4).

### WETTER-3 — Statisch, keine Interaktion (Kiosk)
Die View ist für ein Touch-/Kiosk-Display gebaut und **vollständig statisch**:
kein Hover, kein Aufklappen, keine Bedien-Elemente. V1 nimmt einen Dauer-Kiosk an;
wie das Kind die View sonst erreicht (Controller-Trigger), ist F4/F5-Integration.

### WETTER-4 — Mitwachsen-Stufe als URL-Parameter
Die Stufe ist ein Query-Parameter `?stage=toddler|reader` (URL-8; Muster wie
PLAN-3). **V1 implementiert nur `toddler`** (Default ohne Parameter; 3–6 J,
noch nicht lesend — die Zielgruppe Waldkindergarten). Eine `reader`-Stufe für
ältere, lesende Kinder ist die geplante Mitwachsen-Achse, aber V1-Out-of-Scope
(OPEN-WETTER-A, E-WETTER-4).

## 2. Zeit-Modell

### WETTER-5 — Zwei Tageszeiten, gleichzeitig sichtbar
Die View zeigt **zwei Tageszeiten desselben Tages gleichzeitig**: **Morgens**
(Richtwert 08:00) und **Mittags** (Richtwert 12:00) — orientiert am
Waldkindergarten-Tag (8:00–13:00). Die Tageszeit-Uhrzeiten sind konfigurierbar
(WETTER-21). Beide sind immer sichtbar; kein Umschalten.

### WETTER-6 — Tages-Rollover am Abend
Tagsüber zeigt der Kiosk **heute**. Ab einer konfigurierbaren **Abend-Uhrzeit**
(Default z. B. 17:00, WETTER-21) springt die Anzeige auf **morgen** — damit man
abends die Kleidung für den nächsten Tag herauslegen kann.

## 3. Wetter-Karte (links)

### WETTER-7 — Wetter-Hero als greifbare Wetter-Szene (eigene Bibliothek)
Oben in der Wetter-Karte steht eine große, kindlich greifbare **Wetter-Szene** — ein Haus mit dem heutigen Himmel/Wetter — aus der **app-eigenen Wetter-Szenen-Bibliothek** (E-WETTER-11), dazu der Kurztext `desc`. Die Szene ist **kein ARASAAC-Piktogramm**: für den Wetter-Zustand bietet ARASAAC keine konsistente, über alle Lagen wiederverwendbare Szenen-Reihe (F3-Recherche). Die neutrale Zustands-Kategorie `kind` (WETTER-16) wählt die Szenen-Variante (sonnig, heiter, bewölkt, Regen, Schnee, Gewitter, Sturm). ARASAAC-Piktogramme über ICONS-5 (WETTER-18) gelten für **Inhalts-Symbole** (Kleidung, Metriken), nicht für den Wetter-Zustands-Hero.

### WETTER-8 — Temperatur: eltern-lesbare Zahl + visuell im Spektrum
Die Karte zeigt die **gefühlte Temperatur** (`feelsLike`) als Zahl — bewusst auch für Eltern lesbar — und ordnet sie visuell im Temperatur-Spektrum ein (WETTER-9). Maßgeblich für Kleidung (WETTER-12/14) und Spektrum ist die **gefühlte** Temperatur, nicht die reine Lufttemperatur (das Kind ist ganztags draußen, Wind kühlt). Ein separates Hero-Gesichts-Symbol gibt es nicht; die temperatur-repräsentierenden Marker sitzen am Spektrum (WETTER-9).

### WETTER-9 — Temperatur-Spektrum
Ein Gradient-Balken zeigt das **gesamte mögliche Temperatur-Spektrum** (z. B. üblich
−5 bis 35°) mit der **heute erwarteten Spanne** (`low`–`high`) **hervorgehoben**.
Entlang des Balkens sitzen **temperatur-repräsentierende Marker** (kein Stimmungs-Rating): Schneeflocke (kalt), ein neutrales Gesicht (mild), Sonne (warm), Schweiß/Hitze (heiß), an ihren Temperaturpositionen. Die
Skala ist Bild, nicht nackte Zahl (WETTER-10).

### WETTER-10 — Drei Metrik-Karten, als Bilder statt Zahlen
Unter dem Hero stehen drei Metrik-Karten, jede als **Symbol/Bild** statt als nackte
Zahl: **Regen** (Eimer-Symbol, Menge aus `rainProb`/`rainAmount`), **Wind**
(Gauge-Symbol, `wind`), **Sonnencreme** (Ja/Nein, WETTER-11).

### WETTER-11 — Sonnencreme abgeleitet; UV bleibt unsichtbar
Die Sonnencreme-Karte zeigt einen **Backend-entschiedenen Ja/Nein-Wert**, abgeleitet
aus dem UV-Index (`uv` gegen die Schwelle aus WETTER-21 → `sunscreen`). Dem Kind
wird **weder die UV-Zahl noch das UV-Label gezeigt** — nur die fertige Empfehlung
„Sonnencreme: Ja/Nein" (E-WETTER-2). Das ist die im Problem hervorgehobene Fähigkeit:
das Kind sieht selbst, wann Sonnencreme nötig ist.

## 4. Anziehen-Karte (rechts)

### WETTER-12 — Zwei Outfit-Blöcke: Morgens + Mittags, je eigenständig
Die Karte zeigt **zwei Outfit-Blöcke** desselben Tages untereinander: **Morgens**
und **Mittags**, beide gleichzeitig sichtbar. Jeder Block wird **eigenständig** aus
der gefühlten Temperatur und dem Wetter *seiner* Tageszeit gerechnet — zwei
getrennte Outfits, nicht aufeinander aufbauend (E-WETTER-10).

Die zwei Blöcke beantworten **zwei unterschiedliche Fragen** des Familien-Alltags:

- **Morgens = Pack-Sicht — „Was nehmen die Kinder mit?"** Wenn die Tür zugeht,
  muss alles dabei sein, was über den Tag nötig wird: Regenjacke auch wenn es
  jetzt trocken ist, T-Shirt auch wenn es jetzt 8 °C hat, Sonnencreme/Cappy auch
  wenn die Sonne erst nachmittags durchkommt. Der Morgens-Block rechnet daher
  gegen ein **Tages-Worst-Case-Wetter**: die Schwellen jeder Garderoben-Regel
  sehen das ungünstigste Tagesmaß je Achse (max für Regen/UV/Wind, min UND max
  für die gefühlte Temperatur — siehe WETTER-16).
- **Mittags = Trage-Sicht — „Was passt jetzt zur Lage?"** Bis Mittag wissen die
  Eltern, was die Kinder draußen ausgezogen oder draußen gelassen haben, und
  die Mittags-Sicht hilft bei der zweiten Anpassung. Der Mittags-Block rechnet
  daher gegen den **Slot-Wert** seiner Tageszeit (Open-Meteo-Stunden-Wert ≈ 13
  Uhr, WETTER-5).

Der Regel-Mechanismus (WETTER-14) bleibt identisch — gleiche Schwellen-Form,
gleiches „erste passende gewinnt"; nur die **Wetter-Daten**, die in die Regel
einlaufen, sind je Tageszeit semantisch andere Sichten. Die Konsequenz für die
Empfehlung: Der Morgens-Block kann mehr empfehlen als der Mittags-Block (z. B.
Regenjacke morgens, kein Regen mittags) — das ist Feature, nicht Inkonsistenz.

*Test-Implikation:* an einem Tag mit trockenem Morgen (rainProb morgens-Slot
≈ 0 %) und Regen am Nachmittag (rainProb 17-Uhr ≈ 80 %, Tages-Max 80 %)
liefert der Morgens-Block die Regenjacke (über eine Regel mit
`rain_prob_min ≥ 60 %`, gegen das Tages-Max), der Mittags-Block (Slot 13 Uhr
trocken) tut es nicht.

*Tickets:* #335 · #667 (Pack-/Trage-Sicht für Morgens vs. Mittags)

### WETTER-13 — Aufbau eines Outfit-Blocks
Jeder Block zeigt ein **Pflicht-Set** („MIT"), ein **Optional-Set** („WENN DU
MAGST") und einen kurzen **Hinweistext**. Die Kleidungsstücke sind
ARASAAC-Piktogramme (WETTER-18).

### WETTER-14 — Garderoben-Regeln (Per-Instanz-Daten)
Das Outfit je Tageszeit wird aus den **Garderoben-Regeln** der Familie (Config,
WETTER-21, E-WETTER-5) abgeleitet. Eine Regel bildet eine **Wetterbedingung**
(gefühlte-Temp-Band, Regen, Wind, Sonne) auf ein **Kleidungs-Set** (Teile als
pflicht/optional + Hinweis) ab. Die Regeln sind geordnet; die **erste passende**
Regel gewinnt. Trifft keine zu, zeigt der Block ein **Fallback-Set** (nie leer, nie
ein Fehler vor dem Kind). Die Regeln sind Per-Instanz-Daten, kein Code — eine
Familie passt sie an, ohne Python anzufassen.

### WETTER-15 — Mützen-Logik und Regen-/Matsch-Logik
Zwei für den Waldkindergarten zentrale Regel-Familien sind Teil von WETTER-14:
- **Mützen-Logik:** warm → Cappy/Sonnenmütze; kalt → Wintermütze (Bommel).
- **Regen-/Matsch-Logik:** aus `rainProb`/`rainAmount` → Regenjacke, Matschhose,
  Gummistiefel (pflicht/optional je nach Regenmenge).

Beide Familien profitieren vom **Pack-/Trage-Spalt** (WETTER-12): morgens werden
sie gegen das Tages-Worst-Case-Wetter ausgewertet (Regenjacke mitnehmen, obwohl
es morgens trocken ist; Sonnencreme dabei, weil mittags UV ≥ 3 wird), mittags
gegen die Slot-Lage. Es braucht **keine** „ganztägig-Regen"-Sonderregel und
keinen zweiten Match-Modus — die Sicht selbst trägt die Aggregation.

## 5. Wetter-Anbindung (App-eigene Funktion)

> Die Anbindung ist eine Funktion **dieser App** — keine Plattform-Fähigkeit. V1
> erreicht keine andere App sie (keine API).

### WETTER-16 — Wetter lesen, anbieter-neutrales Modell
Für den konfigurierten Ort liefert die Anbindung das Wetter je Tageszeit (Morgens,
Mittags) und übersetzt die Anbieter-Antwort in ein **anbieter-neutrales Modell**.
Felder mindestens: `desc`, `kind` (neutrale Zustands-Kategorie für WETTER-7), `temp`,
`feelsLike`, `low`, `high`, `wind`, `rainProb`, `rainAmount`, `uv`, `uvLabel`,
`sunscreen` (abgeleiteter Boolean, WETTER-11). Rohfelder, die V1 nicht braucht,
werden nicht durchgereicht (CLAUDE.md §6). V1-Anbieter ist Open-Meteo (kein
API-Key); der Anbieter ist hinter dem Modell austauschbar. *(In der Quell-Vorarbeit
heißen die View-Daten `WB_WEATHER`/`WB_OUTFITS` — Implementierungsdetail, nicht Spec.)*

**Befüllung je Tageszeit (Pack-/Trage-Sicht, WETTER-12):**

- **Mittags-Tageswetter** wird mit dem **Slot-Wert** befüllt — die Anbieter-Antwort
  zur Mittags-Probestunde (Open-Meteo ≈ 13 Uhr, WETTER-5). Felder spiegeln den
  Stunden-Stand 1:1.
- **Morgens-Tageswetter** wird mit **Tages-Worst-Case-Aggregaten** befüllt — der
  ungünstigste Stunden-Wert je Achse, gerechnet über den gesamten Tag. Konkret:
  - `rainProb` ← `max` über alle Stunden des Tages (ungünstigste Regen-Wahrscheinlichkeit)
  - `rainAmount` ← `max` über alle Stunden (größte stündliche Regenmenge)
  - `wind` ← `max` über alle Stunden
  - `uv` ← `max` über alle Stunden (höchster UV-Index → `sunscreen` per
    WETTER-11-Schwelle gegen das Tages-Maximum)
  - `feelsLike` trägt im Morgens-Tageswetter **zwei Werte**: `feelsLike` selbst
    = `min` über den Tag (kältester Moment, für „Pulli mitnehmen"-Schwellen wie
    `feels_min`); zusätzlich ein zweites Feld `feelsLike_max` = `max` über den
    Tag (heißester Moment, für „T-Shirt mitnehmen"-Schwellen wie `feels_max`).
    Die Garderoben-Regel-Auswertung wertet `feels_min` der Regel gegen
    `feelsLike` (= Tages-Min) und `feels_max` der Regel gegen `feelsLike_max`
    (= Tages-Max) aus. Im Mittags-Tageswetter ist `feelsLike_max` gleich
    `feelsLike` (der Slot-Wert) — eine Regel sieht denselben Wert.
  - `temp`, `low`, `high` bleiben Tages-Spanne wie bisher (sie sind Anzeige-Daten
    für WETTER-9, nicht Regel-Schwellen — keine Verhaltensänderung).

Die Befüllungsregel ist die **einzige** semantische Differenz der zwei
Tageszeiten — die `Tageswetter`-Form und die Regel-Auswertung sind identisch.

### WETTER-17 — Anbieter nicht erreichbar → neutraler Zustand
Ist der Anbieter nicht erreichbar oder fehlt der Ort, wirft die App keinen
unbehandelten Fehler: der Kiosk zeigt einen **neutralen Zustand** (kein Fehler, kein
leerer Bildschirm vor dem Kind) und bleibt an — protokolliert (analog PLAN-20). Ein
Anbieter-Cache / Last-Known-Good ist V1-Out-of-Scope (OPEN-WETTER-E).

## 6. Iconografie & Gestaltung

### WETTER-18 — Zweistufige Iconografie, Piktogramme über die geteilte Icon-Plattform
**Lucide** für UI-Verben/funktionale Symbole, **ARASAAC-Piktogramme** für Inhalte
(Wetterzustand, Kleidung, Temperatur-Köpfe). **Kein Emoji**; **keine Mischung**
beider Quellen innerhalb einer Komponente. Die ARASAAC-Piktogramme werden **über
die zentrale Icon-Plattform** bezogen — read-only unter der geteilten URL
`/display/_shared/icons/arasaac/<id>.png` (`icons.md` **ICONS-5**, ausgeliefert vom
Router ROU-26) — **kein buddy-eigener ARASAAC-Bezug** (sonst zweiter Icon-Pfad,
CLAUDE.md §6 / Lego). Die `kind`-Kategorie (WETTER-16) und die Kleidungsstücke
bilden auf numerische ARASAAC-IDs ab.
Diese ICONS-5-Anbindung gilt für **Inhalts-Piktogramme** (Kleidung, Metrik-Symbole). Der **Wetter-Zustands-Hero** ist davon ausgenommen — er ist die app-eigene Wetter-Szene (WETTER-7, E-WETTER-11).

### WETTER-19 — ARASAAC-Attribution-Footer
Jede Instanz der View trägt einen **ARASAAC-Attribution-Footer** (ARASAAC / Sergio
Palao) — das ist View-Verhalten des Wetter-Buddys. Die **Lizenz- und NC-Frage**
(CC BY-NC-SA, kommerzielle Nutzung) wird **nicht hier** entschieden, sondern liegt
zentral in `icons.md` **ICONS-6**; diese Spec verweist nur darauf (CLAUDE.md §6,
kein dupliziertes Lizenz-Urteil).

### WETTER-20 — Visueller Stil aus dem xbuddy Design System *(Design System folgt)*
Der visuelle Stil bindet an das **xbuddy Design System**, das als Ganzes **separat**
geliefert wird (OPEN-WETTER-H). Bis dahin werden hier **keine konkreten Stilwerte**
(Farben, Maße, Schriften, Token-Quelle) festgeklopft. Verbindlich ist nur die
Bauregel: **keine hartcodierten Farben/Maße im Buddy-CSS**, alle Stilwerte als Token
(Quelle = das nachgelieferte Design System). (E-WETTER-6.)

### WETTER-25 — Raumfüllende Darstellung, einheitliche Schriftgröße, Lesbarkeit
Symbole und Karten **nutzen den vorhandenen Platz** — sie verteilen sich über die
gesamte Kiosk-Fläche, statt klein in einer Ecke zu sitzen; das Board ist immer gut
gefüllt. Wo Text vorkommt, gilt **eine einheitliche Schriftgröße über das gesamte
Board** — keine konkurrierenden Textgrößen. Leitlinie: **gute Lesbarkeit aus
Kiosk-Distanz** und volle Platznutzung. Die konkreten Werte (Schriftgröße,
Abstände, Skalierung) kommen mit dem Design System (WETTER-20, OPEN-WETTER-H);
diese Regel legt das **Prinzip** fest, nicht die Pixel.

## 7. Konfiguration

### WETTER-21 — Konfigurationswerte
Zwei Per-Instanz-Dateien neben dem Code (CONFIG-1), beide gitignored:

- `wetter/wetter.json` — **Daten-Konfig.** Format: `wetter/wetter.example.json`.
- `wetter/config.json` — **Runtime-Konfig** (Bind, Log), via `tools/configloader.py`.

| Name                 | Default                  | Datei-Schlüssel    | Gesetzt durch |
|----------------------|--------------------------|--------------------|---------------|
| Ort                  | (Pflicht, kein Default)  | `ort`              | Familie (V1 in Datei) |
| Garderoben-Regeln    | Beispiel-Set im Example  | `wardrobe`         | Familie (V1 in Datei) |
| Sonnencreme-Schwelle | UV-Schwelle (OPEN-WETTER-G) | `sunscreen_uv`  | n/a (Default reicht) |
| Tageszeit Morgens    | `08:00`                  | `zeit_morgens`     | n/a |
| Tageszeit Mittags    | `12:00`                  | `zeit_mittags`     | n/a |
| Abend-Rollover-Zeit  | `17:00`                  | `rollover_abend`   | n/a |
| Listen-Host          | `127.0.0.1`              | `listen_host`      | n/a |
| Listen-Port          | (PORT-2, WETTER-22)      | `listen_port`      | n/a |
| Log-Level            | `INFO`                   | `log_level`        | n/a |

Ort und Garderoben-Regeln sind der Musterfall der **Familie-3-Probe**: was sich je
Familie ändert, ist Config, nicht Code (E-WETTER-5). Anders als beim Plan-Buddy
(E-PLAN-8) ist beim Wetter nichts familienspezifisch hartcodiert.

## 8. Service & Registrierung

### WETTER-22 — Eigener Service, fester Port
Der Wetter-Buddy läuft als eigener Prozess `xbuddy-wetter.service` (SVC-1..4,
Service-Datei im Repo, `Restart=on-failure`, Logs an stdout/stderr) und bindet nur
an `127.0.0.1` (PORT-3). Port **5030** (PORT-2, `xbuddy-wetter`, belegt in
`conventions/ports.md`).

### WETTER-23 — Registrierung in der Plattform
Der Slug `wetter` wird im Origin-Routing (URL-14) registriert, damit
`/display/wetter/heute` über die Origin erreichbar ist. Diese Verkabelung ist
**Integration**, nicht App-Eigentum — Gegenstand des arbeitstag-Track-Schnitts
(F4/F5). **Familien-Schnittstelle-Beitrag (APP-4): die eltern-seitige
Garderoben-Editor-Seite** (§10, WETTER-26 ff.) — eine im Heimnetz/Tailscale
erreichbare Web-Seite, über die die Familie die Garderoben-Regeln selbst pflegt
(**kein** Eltern-Chat-Schreibweg; der Eltern-Chat liefert später nur den Link,
eigenes Ticket). Der **Ort** wird in V1.1 weiter per Datei gesetzt (WETTER-32).
**Entkoppelt vom Installations-Mechanismus #296** (Zugang = Netz-Grenze, WETTER-31),
nicht daran gated.

## 9. Tests

### WETTER-24 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test (CLAUDE.md §6),
reproduzierbar und **ohne Netz** — der Anbieter-Zugriff wird durch eine
kontrollierte Doppelung ersetzt (analog PLAN-29). Mindest-Abdeckung: WETTER-2 (beide
Karten auf einer Canvas) · WETTER-4 (`toddler` Default, `reader` V1 nicht
implementiert) · WETTER-6 (vor Abend-Zeit → heute; danach → morgen) · WETTER-7
(Hero rendert die Wetter-Szene, KEIN ARASAAC-Hero-Piktogramm) · WETTER-8
(gefühlte Temp erscheint als Zahl in der Ausgabe) · WETTER-8/14 (Outfit aus
`feelsLike`) · WETTER-9 (temperatur-repräsentierende Marker im Spektrum vorhanden) ·
WETTER-11 (UV-Zahl/-Label nicht in der Ausgabe; `sunscreen`-Boolean steuert die
Karte) · WETTER-12 (beide Tageszeit-Blöcke gerendert, unabhängig gerechnet) ·
WETTER-14/15 (erste passende Regel gewinnt; keine Regel → Fallback; Mützen-Logik
warm/kalt; Regen-Logik aus `rainAmount`) · WETTER-16 (Rohantwort → neutrales Modell,
je Tageszeit) · WETTER-17 (Anbieter nicht erreichbar → neutraler Zustand, View
funktioniert). Läufe gegen den echten Anbieter sind opt-in.

## 10. Eltern-Garderoben-Editor (V1.1)

> V1.1-Erweiterung: die erste **eltern-seitige** (parent) Oberfläche des
> Wetter-Buddys. Grundlage **RAT-2** (`decisions/RAT-2-328-garderoben-regelmatrix.md`),
> Keystone #328.

### WETTER-26 — Eltern-seitige Editor-Seite für die Garderoben-Regeln *(umgesetzt #328)*
Die Familie pflegt die Garderoben-Regeln (WETTER-14, `wardrobe` in `wetter.json`)
selbst über eine eltern-seitige Web-Seite im Wetter-Buddy — der familienseitige
Beitrag des Buddys (APP-4, löst RAT-2). Die Seite **zeigt UND editiert** die
Regelmatrix im Handy-Browser; Speichern läuft über einen **internen Save-Handler
der Seite** (POST innerhalb der Buddy-Grenze, schreibt `wetter.json`) + Reload-on-Read
(DCOMP-2) — der Kiosk übernimmt **ohne Restart**. **Keine API für andere Apps**
(BUD-1b: kein Konsument → keine API; WETTER-1/E-WETTER-3 bleiben gültig). Die Seite
ist **kein Kiosk-View und nicht kindgerichtet** — eine Eltern-Oberfläche, **von
WETTER-25 ausgenommen** (Scrollen und Menüführung erlaubt). **Hochkant am Handy ist
Default und V1.1-Zielzustand.** Kein Live-Wetter, nicht das Heute-Outfit — nur die
Regel-Config.

### WETTER-27 — Anzeige der Matrix (Übersicht + Fokus) *(umgesetzt #328)*
Die View folgt dem Muster **Übersicht + Fokus**: eine kompakte Liste aller Regeln
**in ihrer Reihenfolge** (erste passende gewinnt, WETTER-14; je Eintrag Bedingung +
Outfit-Vorschau) und ein **fokussierter Einzel-Regel-Editor** beim Antippen. Im
Fokus sichtbar: die Bedingungs-Schwellen **read-only zur Orientierung**
(gefühlte-Temp-Band, Regen, Wind, Sonne), das Pflicht-Set, das Optional-Set, der
Hinweis — plus das `fallback`-Set. Die „Schwelle fest"-Markierung ist ein
**Lucide-Icon, kein Emoji** (WETTER-18). Kleidungs-Piktogramme über die geteilte
Icon-Plattform (ICONS-5). Stil/Pixel kommen aus den Tokens.

### WETTER-28 — Bearbeiten: nur die Kleidungs-Sets *(umgesetzt #328)*
Editierbar in V1.1 sind **ausschließlich die Kleidungs-Sets** (Pflicht/Optional) je
Regel und des Fallbacks: Stücke **hinzufügen / entfernen / tauschen** aus der
kuratierten Palette (WETTER-29). **Read-only** bleiben: die **Schwellen** der
Bedingung, der **Hinweistext** sowie **Anzahl und Reihenfolge** der Regeln.
Speichern sendet die geänderte Matrix an den internen Save-Handler (WETTER-26).

### WETTER-29 — Kuratierte Kleidungs-Palette *(umgesetzt #328; Palette-Update #361)*
Kleidungsstücke werden **aus einer kuratierten Liste** vorgegebener Stücke
(`{name, pikto}`) gewählt — die Familie tippt **keine** ARASAAC-ID. Die Palette
wird mit dem Buddy ausgeliefert (durch einen Entwickler erweiterbar) und zeigt ihre
Icons über ICONS-5. **V1.1-Palette (18 Stücke, ARASAAC-IDs):** Regenjacke `4927` ·
Matschhose `24276` · Gummistiefel `2287` · Wanderschuhe `4580` · Halbschuhe `2621` ·
Winterjacke `25804` · Jacke `2319` · Pullover `2436` · T-Shirt `2309` · Lange Hose `2565` ·
Kurze Hose `13638` · Wintermütze `2412` · Cappy `2411` · Sonnenhut `2572` ·
Handschuhe `2415` · Schal `2290` · Sonnenbrille `3330` · Sandalen `2556`. Die
Palette-IDs müssen im Instanz-Icon-Store (`/display/_shared/icons/arasaac/<id>.png`,
ICONS-5) vorliegen. NC-Lizenzfrage zentral bei `icons.md` ICONS-6.

### WETTER-30 — Schreib-Validierung schützt die Kinder-View *(umgesetzt #328)*
Eine gespeicherte Matrix ist gültig, wenn **jede Pflicht-Zelle nicht leer** ist
(jede Regel **und** das Fallback) und **jedes Pikto aus der kuratierten Palette**
stammt (WETTER-29). **Optional-Sets dürfen leer sein.** Schwellen werden nicht
geprüft (nicht editierbar, WETTER-28). Geschrieben wird **atomar** (Temp-Datei +
Rename), damit ein gleichzeitiger Kiosk-Read nie eine halbe Datei sieht. Ungültiges
Speichern → Fehler, `wetter.json` **unverändert**, Kiosk unberührt. Gültiges
Speichern wird über DCOMP-2 ohne Restart sichtbar.

### WETTER-31 — Zugang: Heimnetz/Tailscale, keine Zusatzsicherung *(umgesetzt #328)*
Die Seite braucht **kein Login und kein Token** (RAT-2): Bedrohungsmodell = „Leute
im Haushalt", das Netz ist die Vertrauensgrenze. Leitplanke: die Edit-Seite/-Handler
darf **nicht über einen ins Internet exponierten Pfad** erreichbar sein
(LAN/Tailscale-Interface, kein Port-Forwarding).

### WETTER-32 — Ort in V1.1 nicht editierbar *(umgesetzt #328)*
Der Editor pflegt **nur die Garderobe**. Der Ort (`ort` in `wetter.json`) bleibt
Datei-gesetzt und ist ein **eigenes Folge-Ticket** (Nic, 2026-06-06).

### WETTER-33 — Tests je Anforderung (ohne Netz) *(umgesetzt #328)*
Automatisierte Tests, reproduzierbar **ohne Netz** (der Editor berührt Open-Meteo
nicht): Anzeige liefert die Matrix · gültiges Speichern schreibt + wird per Reload
sichtbar · ungültiges Speichern wird abgelehnt und lässt `wetter.json` unverändert
(leeres Pflicht-Set · Pikto außerhalb der Palette · veränderte Anzahl/Reihenfolge) ·
atomarer Schreibpfad.

---

## Offene Punkte

- **OPEN-WETTER-A — `reader`-Stufe.** V1 implementiert nur `toddler` (WETTER-4).
  Die `reader`-Stufe (ältere, lesende Kinder) ist die geplante Mitwachsen-Achse,
  aber ohne belegten V1-Bedarf vertagt (E-WETTER-4).
- **OPEN-WETTER-B — Lese-API für andere Apps.** Kein Konsument → keine
  `/api/v1/wetter/` in V1 (E-WETTER-3).
- **OPEN-WETTER-C — Mehrtages-Vorhersage & mehrere Orte.** V1 kennt heute/morgen
  (Rollover, WETTER-6) und einen Ort.
- **OPEN-WETTER-D — Port-Nummer. ERLEDIGT:** Port **5030** ist in `conventions/ports.md` (PORT-2) als `xbuddy-wetter` belegt (#137 — Wetter-Buddy-Integration).
- **OPEN-WETTER-E — Anbieter-Cache / Offline.** V1 zeigt bei Ausfall einen neutralen
  Zustand (WETTER-17); Last-Known-Good (Qualitätsattribut 4) später.
- **OPEN-WETTER-F — Lizenz/NC: zentral in ICONS-6 geführt.** Die ARASAAC-NC-Klausel
  vs. kommerzielles Produkt wird in `icons.md` ICONS-6 behandelt, nicht hier — dieser
  Punkt ist nur ein Verweis, kein wetter-eigener offener Punkt.
- **OPEN-WETTER-G — Sonnencreme-Schwelle.** Ab welchem UV-Wert „Ja" — Config
  (`sunscreen_uv`) mit sinnvollem Default; familienspezifisch oder fix ist offen.
- **OPEN-WETTER-H — Design-System-Reichweite. ENTSCHIEDEN (#323, Nic 2026-06-03):**
  `display/_shared/design/tokens.css` (v2.0) ist das repo-weite Fundament
  für alle Buddys. `plan/static/design/tokens.css` (v1.0) ist abgelöst (#323).
  Konvention: [`conventions/design-tokens.md`](../../conventions/design-tokens.md).
  Andockpunkt via `/display/_shared/` (DTOK-2) ist Schritt-2-Arbeit (#323).
- **OPEN-WETTER-I — AMENDIERT 2026-08-01** (#1715, Nic „Einheitlichkeit ist mir wichtiger", berater-runde): Die Editor-Seite zieht in den **einheitlichen Eltern-Seiten-Namespace** `/seiten/wetter/regeln` (seiten-gehostete Mini-App wie einkauf/hörspiel/plan/routine, ESB-1.a) — Server-Template → JS-Shell, Datenrouten `GET/POST /api/v1/wetter/regeln` in **AUTH-3** (Cookie-hart), REGISTRY-Eintrag + Mantel aus seiten. Der bisherige `/display/wetter/regeln`-Namespace **entfällt**. Trade bewusst akzeptiert: Symmetrie vor Service-Kohäsion; der Schreib-Pfad wird cross-service (Kill-Kriterium: Pi-Spike Install+POST-Save+Kiosk grün). *(Ursprung #328/2026-06-06, URL-2-Drift #594: Editor im eigenen wetter-Display-Namespace `/display/wetter/regeln` — durch die ESB-1.a-Einheitlichkeit überholt.)*
- **OPEN-WETTER-K — `data-stage="parent"`-Token-Block. VERTAGT (RAT-8, Nic
  2026-06-06):** im geteilten Token-Strang noch nicht definiert (nur reader/toddler);
  V1.1 fährt auf Basis-/Reader-Tokens. Der parent-Stufen-Block wird **bei der 2.
  Parent-App** definiert (`decisions/RAT-8-parent-stufe-token-defer.md`).

---

## Entscheidungen

### E-WETTER-1 — Wetter-Buddy ist eine App: besitzt Daten, Funktion, View
*Datum:* 2026-06-02 · App-Muster (Constitution „App-Eigentümerschaft", APP-1,
Erstanwendung E-PLAN-1). Besitzt Ort + Garderoben-Regeln (Daten) und die
Wetter-Anbindung (Funktion); stellt das Ergebnis über die Display-View bereit.

### E-WETTER-2 — UV bleibt unsichtbar; Sonnencreme wird abgeleitet gezeigt
*Datum:* 2026-06-02 · Aus #137 („kein UV vors Kind") und Nics Spec-Übersicht
(„Sonnencreme als Backend-entschiedener Boolean"). Modell trägt `uv`/`uvLabel`
(für die Ableitung), die View zeigt nur die Ja/Nein-Empfehlung. **Verworfen:**
UV-Zahl/-Label vors Kind.

### E-WETTER-3 — V1 ohne API für andere Apps
*Datum:* 2026-06-02 · Kein Konsument; die „Was zieh ich an"-Logik ist
wetter-intern. API ohne Konsument wäre Vorrat (§6) und Heim-Server-Overhead.
Kommt als eigenes Ticket bei Bedarf (OPEN-WETTER-B). **Verworfen:** Lese-API auf
Vorrat.

### E-WETTER-4 — V1 nur `toddler`-Stufe; stage-Achse existiert
*Datum:* 2026-06-02 · Zielgruppe Waldkindergarten (3–6 J, noch nicht lesend) → V1
ist die `toddler`-Stufe. Die Mitwachsen-Achse ist als `?stage=`-Parameter
angelegt, aber V1 baut nur `toddler`. **Verworfen:** `reader` jetzt mitzubauen
(ohne belegten Bedarf Vorrat, §6).

### E-WETTER-5 — Ort und Garderoben-Regeln sind Per-Instanz-Daten, nicht Code
*Datum:* 2026-06-02 · Beide ändern sich je Familie → Config (§6, Familie-3-Probe).
Anders als beim Plan-Buddy (E-PLAN-8) ist beim Wetter nichts familienspezifisch
hartcodiert. **Verworfen:** Garderoben-Regeln als Python-Dict.

### E-WETTER-6 — Visueller Stil aus dem zentralen Design System (separat geliefert)
*Datum:* 2026-06-02 · Wetter bindet an das xbuddy Design System, das als Ganzes
nachgeliefert wird (OPEN-WETTER-H) — nicht an den handgezeichneten Plan-Kids-Look
(plan-spezifischer 1:1-Wireframe-Handoff, E-PLAN-5). Bis zur Lieferung keine
festen Stilwerte; nur die Token-Bauregel gilt. **Verworfen:** jetzt Stilwerte
festklopfen oder den Plan-Kids-Look kopieren.

### E-WETTER-7 — Zweistufige Iconografie über die geteilte Icon-Plattform (Kleidung/Metriken)
*Datum:* 2026-06-02 · Lucide für UI, ARASAAC für Inhalte, kein Emoji, keine
Mischung je Komponente (WETTER-18). ARASAAC/ICONS-5-Anbindung gilt für
**Inhalts-Piktogramme** (Kleidung, Metrik-Symbole) — ARASAAC-Piktogramme werden
über die zentrale Icon-Plattform bezogen (ICONS-5, geteilte URL), **nicht**
buddy-eigen — sonst entstünde ein zweiter Icon-Pfad (CLAUDE.md §6, Lego-Prinzip).
**Wetter-Zustand = eigene Szene** (E-WETTER-11): der Wetter-Zustands-Hero ist
ausdrücklich von dieser ICONS-5-Anbindung ausgenommen. Der Attribution-Footer ist
View-Verhalten (WETTER-19); die Lizenz/NC-Frage liegt zentral in ICONS-6, hier
nur referenziert. **Verworfen:** eigener ARASAAC-Bezug und ein eigenes Lizenz-Urteil
im Wetter-Buddy (wäre Geschwister-Drift gegen die bestehende `icons.md`).

### E-WETTER-8 — Empfehlung und Gesicht nach gefühlter Temperatur
*Datum:* 2026-06-02 · Outfit und Temperatur-Gesicht richten sich nach `feelsLike`,
nicht `temp` — das Kind ist ganztags draußen, Wind kühlt. **Verworfen:** reine
Lufttemperatur als Treiber (Wind flösse dann nur über die Wind-Metrik ein).

### E-WETTER-9 — Abend-Rollover auf morgen
*Datum:* 2026-06-02 · Der Dauer-Kiosk zeigt tagsüber heute, ab einer
konfigurierbaren Abend-Uhrzeit morgen (WETTER-6) — passend zum Familien-Ablauf
(abends Kleidung herauslegen). **Verworfen:** immer nur heute zu zeigen.

### E-WETTER-10 — Zwei getrennte Outfits statt Zwiebellook
*Datum:* 2026-06-02 · Morgens- und Mittags-Block werden je eigenständig gerechnet
(WETTER-12), nicht als eine aufeinander aufbauende Schicht-Empfehlung.
**Verworfen:** Zwiebellook („mittags eine Schicht ausziehen") als ein
zusammenhängendes Outfit.

### E-WETTER-11 — Eigene Wetter-Szenen-Bibliothek für den Zustands-Hero
*Datum:* 2026-06-02 · Der Wetter-Zustand wird als greifbare, kindlich vorstellbare Szene (Haus + Himmel) aus einer **app-eigenen Bibliothek** dargestellt, nicht über ARASAAC. Grund: F3-Recherche zeigte, dass ARASAAC nur Einzel-Wettersymbole hat, **keine konsistente Szenen-/Haus-Reihe** über alle Wetterlagen. Eine eigene Szene ist konsistent (gleiche Haus-Silhouette, nur Himmel wechselt) und orientiert das Kind an seinem Zuhause. Die ICONS-5-Anbindung (E-WETTER-7) bleibt für Kleidung/Metriken. **Verworfen:** den Wetter-Zustand über ARASAAC-Einzelsymbole zu zeigen. Abgrenzung zur frühen ICONS-Drift: kein versehentlicher zweiter Icon-Pfad, sondern eine bewusste eigene Asset-Klasse (Szenen ≠ Piktogramme).

### E-WETTER-12 — Garderoben-Pflege über eine eltern-seitige Editor-Seite (V1.1)
*Datum:* 2026-06-06 · Werft-Lauf #328, Gates A/B/C (Nic). Grundlage **RAT-2**
(Link/Editor statt PNG/Chat-Schreibdialog) und **RAT-8** (parent-Token vertagt).
Die Familie pflegt die Garderoben-Regeln über eine eltern-seitige Web-Seite
(WETTER-26 ff.), nicht über einen Eltern-Chat-Schreibdialog. **Interner Save-Handler,
keine API** — kein Fremd-Konsument (BUD-1b; E-WETTER-3 bleibt gültig). V1.1 editiert
**nur die Kleidungs-Sets** über eine kuratierte Palette (Schwellen/Reihenfolge fest,
WETTER-28); Zugang = Heimnetz/Tailscale-Grenze ohne Zusatzsicherung (WETTER-31).
**Verworfen:** PNG-Render via headless chromium, mehrstufiger Chat-Schreibdialog
(beide in RAT-2 abgelöst), sowie eine REST-API auf Vorrat.
