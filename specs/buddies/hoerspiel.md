# Hörspiel-Buddy — Spec     (ID-Präfix: HSP)

> Status: V1 · Refs #729, #907 (Mehr-Instanz-Cut Mia + Finn, RAT-17), #1263 (dritte Instanz „Emil" Erwachsener, n≥3-Modell, HSP-28a reaktiviert)

## Problem & North-Star-Bezug

Jedes Kind in der Familie hat sein eigenes Hörspiel-Universum: Mia (4)
hört seit Monaten „Stigi, Malini & Vögelchen — Geschichten aus dem Garten
im Beispieltal", Finn bekommt mit V1 (RAT-17) seine eigene Welt. Folgen
wurden bisher lokal geschrieben und über das Handy eines Elternteils
abgespielt. Drei Probleme:

1. **Hardware-Knappheit:** Das Kind braucht Mamas oder Papas Handy, das
   oft anderswo gebraucht wird.
2. **Abbrüche:** Vorlesen bricht beim App-Wechsel ab, beim Anruf, beim
   Lock-Screen. Kein „weiter wo aufgehört".
3. **Keine Selbstbedienung:** Das Kind kann nicht eigenständig wählen,
   welche Folge es hören will, geschweige denn eine zuvor unterbrochene
   Stelle wiederfinden.

**North-Star-Bezug (constitution.md):** Das **Kind** wählt und steuert
das Hören selbst über eine Kachel-Oberfläche auf einem eigenen Gerät,
statt ein Elternteil mit dem Handy zu binden. Was die Eltern bisher
taten (Hörspiel auswählen, Wiedergabe starten, Stelle finden),
verschiebt sich vollständig zum Kind.

Der Hörspiel-Buddy ist eine eigenständige XBuddy-**App** mit einer
Display-View — der **Album-Übersicht und Player pro Kind** — und einer
App-eigenen **KI-Funktion**, die im Eltern-Chat-Skill (Familien-
Schnittstelle) neue Folgen erzeugt und vertont. Als App **besitzt** er
seine Daten (Welt-Bible, Folgen-Historie, Alben + Audio-Assets), seine
Funktion (LLM-gestützte Folgen-Erzeugung, TTS-Album-Bau, Resume-
Verwaltung) und stellt das Ergebnis über seine Display-View bereit
(HSP-1, APP-1).

Der Buddy läuft mit **mehreren expliziten Instanzen** (V1: Mia + Finn;
ab #1263 zusätzlich Emil als gleichrangige Erwachsenen-Instanz),
handverdrahtet je Instanz (eigene systemd-Unit, eigener Port, eigene
Origin-Pfade nach URL-3a). Eine **hörspiel-lokale Instanz-Liste** trägt
die Laufzeit-Iteration über die verdrahteten Instanzen (HSP-43); eine
generische „Buddy-mit-n-Instanzen"-Registry gibt es bewusst weiterhin
**nicht** (RAT-17 bleibt vertagt bis zur zweiten n-Instanz-Buddy-Klasse).
Details siehe HSP-28a und Abschnitt 14 (HSP-43..HSP-46).

**V1-Scope:** Single-Page-View `alben` (Kachel-Raster + Player auf einer
Canvas) · Album-Modell mit geordneten Tracks · Voice-Casting je Album über
zwei Azure-OpenAI-tts-hd-Voices `shimmer` (weich/weiblich) und `onyx`
(tief/männlich) · Pausen über expliziten Silence-Insert (kein `speed`-
Stretching) · Intro/Outro als vorsynthetisierte Shared-Assets je Voice (vier
feste MP3) · Track-Resume mit Rundung auf Track-Anfang · MediaSession-API
+ PWA `display:standalone` gegen Geräte-Schlaf · App-eigener **LLM-Adapter
mit Provider-Switch** (`claude` Default; weitere Provider als V2-Hook
über das kopierfähige Adapter-Pattern, V1 nur `claude`) ·
App-eigener **TTS-Adapter** (Azure OpenAI, Region `swedencentral`) · zwei
schreibende API-Endpoints für den Eltern-Chat-Skill (`POST /folgen-vorschlag`,
`POST /alben`) · Lese-Endpoints für Bible/Historie/Album-Liste/Manifest ·
Welt-Bible & Folgen-Historie als Per-Instanz-Domänendaten (BUD-2a) · ein
familienseitiger Beitrag: der Eltern-Chat-Skill `hoerspiel-folge-erzeugen`
(eigene Plattform-Spec `specs/platform/hoerspiel-folge-erzeugen.md`,
ID-Präfix HFE).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **OPEN-HSP-A** — Folgen-spezifisches Cover-Bild (V1: **einheitliches
  Serien-Cover** im 1:1-Format, von den Eltern austauschbar — der V2-Pfad
  ist ein Eltern-Chat-Skill „Cover austauschen" + per-Folge-Cover, der
  über das gleiche 1:1-Format-Schema landet, E-HSP-10).
- **OPEN-HSP-B** — Das Kind äußert per Sprache seinen Folgen-Wunsch im
  Eltern-Chat („Ich möchte eine Folge über Schnee"). Würde denselben
  V1-Endpoint `POST /folgen-vorschlag` bedienen — Trigger-Agnostik.
- **OPEN-HSP-C** — Bilder synchron zum Track-Inhalt (Bilderbuch-Modus).
  Braucht die Track-Granularität, die V1 schon legt.
- **OPEN-HSP-D** — Aussprache-Lexikon für Eigennamen (Stigi, Schmuggli,
  Beispieltal …) das die TTS-Vorlage vor der Synthese anwendet.
- **OPEN-HSP-E** — mehrere Hörspiel-Serien parallel (V1: eine Serie,
  „Stigi & Co.").
- **OPEN-HSP-F** — Premium-Voice-Upgrade zu ElevenLabs oder einer Custom-
  Neural-Voice für native deutsche Aussprache (V1 akzeptiert die leichte
  engl. R-Rollung von `shimmer`/`onyx`, HSP-23).
- **OPEN-HSP-G** — App auf einem kind-eigenen Gerät (V1 nimmt das
  geteilte Familien-Tablet im Browser an; ein eigenes Kind-Gerät ist
  Hardware-/Onboarding-Frage). Bei geteiltem Tablet steuert die Face-
  Pille (HSP-3a / #911) den Wechsel zwischen den beiden Hörspiel-
  Instanzen Mia ↔ Finn.
- **OPEN-HSP-H** — Concurrency-Lock am TTS-Adapter bei der heutigen 3-RPM-
  Quota; bei höherer Quota entfällt das.
- **OPEN-HSP-I** — Album-Sortierung in der Kachel-View (neuestes zuerst /
  Lieblings-Markierung / Resume-Album vorgezogen).
- **OPEN-HSP-J** — Anzahl-Begrenzung Kacheln (Scroll / Archiv / Filter).
- **OPEN-HSP-K** — Audio-Format MP3 96 kbps mono in V1; Opus später.
- **OPEN-HSP-L** — Asynchrone Generierung mit Benachrichtigung am Ende
  statt blockierender Synthese.
- **OPEN-HSP-M — ERLEDIGT #749 (2026-06-15).** Azure-/Anthropic-Schlüssel-
  Verwaltung läuft jetzt über die zentrale ZD-Library
  (`specs/platform/zugangsdaten.md`), Slot-Namen `hoerspiel-anthropic-api-key`
  und `hoerspiel-azure-openai-api-key`. Migration zweistufig analog ONB-5→ZD
  (#84 + #336): Welle A read-both/write-ZD, Welle B ENV-Fallback entfernt.
  Details in HSP-27.
- **OPEN-HSP-N** — Eltern-Chat-Skill „LLM-Provider für Hörspiel wechseln"
  (Inline-Befehl „wechsele mal auf mistral für hörbücher" patcht den
  Provider via `PATCH /api/v1/hoerspiel/<kind_id>/config`, HSP-19). V1 exposed den
  Endpoint, der Skill zieht in V2 nach.
- **OPEN-HSP-P** — Automatische `pikto-hauptbegriffe`-Befüllung beim
  Album-Bau per Heuristik oder LLM-Klassifikation (HSP-5a-V1 lässt das
  Feld leer; Migration über `pikto-mapping.json` ist V1-Pfad). V2.
- **OPEN-HSP-Q** — Setup-Skript für die Erst-Bestückung des
  Daten-Bereichs (V1 manuelle Copy-Paste-Migration, HSP-25a). V2.
- **OPEN-HSP-R** — `name`/`alter` der Hörspiel-Instanz aus `familie.json`
  per FK lesen (HSP-38 Soll-Form), ENV-Krücke `HOERSPIEL_KIND_NAME` /
  `HOERSPIEL_KIND_ALTER` (V1-Übergang seit T4 #910) ablösen. Trigger:
  familie_client für Hörspiel-Service angebunden — gehört zur Welle
  „Hörspiel besitzt seinen familie-FK".
- **OPEN-HSP-S** — Eltern-/Erwachsenen-Folgen aus der Kinder-View
  ausblenden (Zielgruppen-Sicht-Trennung). Nic-Idee 2026-07-03 (#1263),
  bewusst vertagt: erhöht die Komplexität (zusätzliche zu verwaltende
  Sichtbarkeits-Option) und ist erst mit der als vollwertiger Player
  gebauten Settings-App notwendig/leicht. Trigger: Settings-App-als-
  Player steht. Bis dahin gilt HSP-46 (keine Trennung).
  *(Marginalie 2026-07-03: der „vollwertige Player" wird mit HSP-47..55
  gebaut — die Sicht-Trennung selbst bleibt dennoch vertagt, da dieser Lauf
  Front-End-only ist und das Backend keinen Sichtbarkeits-Flag trägt.)*
- **OPEN-HSP-T** — Kind-Abweisung vor den Settings (V1: keine, nur Zahnrad,
  HSP-50). Spätere Erweiterung (Long-Press / PIN / Eltern-Frage), Nic-Setzung
  2026-07-03.
- **OPEN-HSP-U** — Tablet-`alben`-View (localStorage-Resume, HSP-23) auf den
  server-seitigen Resume-Stand (HSP-51) vereinheitlichen. Folge von OPEN-HSP-G;
  Tablet bleibt V1 unangetastet.
- **OPEN-HSP-V** — Reaktiviert OPEN-HSP-G teilweise: geteiltes Familien-Handy
  ✓ (HSP-47..55); per-Kind-eigenes-Gerät + geräteübergreifender Resume-Sync
  weiterhin offen.
- **OPEN-HSP-W** — Orchestrator-Deploy: `instance.json` je Instanz
  (mia/finn/emil) mit `serien_name`/`ton`/`perspektive` befüllen,
  damit die `Serie:`-Zeile im LLM-Prompt erscheint. Folge von T1336
  (DEFAULT_SERIEN_RAHMEN neutralisiert, HSP-45-Abschnitt). Trigger: Deploy-
  Runbook nach T1336-Merge.

---

## 1. Die App & ihre View

### HSP-1 — Hörspiel-Buddy ist eine App mit eigenem Besitz
Der Hörspiel-Buddy ist die XBuddy-App mit dem Buddy-Slug `hoerspiel`. Er
besitzt seine **Daten** (Welt-Bible, Folgen-Historie, Album-Manifeste +
Audio-Assets, Resume-State), seine **Funktion** (LLM-gestützte Folgen-
Erzeugung, TTS-Pipeline, Album-Sequencing, Resume-Verwaltung) und stellt
das Ergebnis über seine **Display-View** bereit (APP-1). Er stellt eine
API für den Eltern-Chat-Skill bereit (BUD-1b, HSP-17).

### HSP-2 — Single-Page-View `alben`, Splitscreen aus Kacheln + Player
Die Hör-View liegt unter `/display/hoerspiel/<kind_id>/alben` (BUD-1, URL-3a,
RAT-17, #965) — z. B. `/display/hoerspiel/mia/alben` oder
`/display/hoerspiel/finn/alben`. Sie ist **eine Canvas**: links das
Album-Kachel-Raster, rechts der Player als **immer sichtbare vertikale
Säule**. Kein Routing zu Sub-Seiten, keine Menüführung — statisches
Dashboard (HSP-3). Statische Assets unter
`/display/hoerspiel/static/<asset>` (URL-13); Audio- und Cover-Assets je
Album werden aus dem Daten-Bereich über Router-Pfade in derselben
Display-Origin ausgeliefert (HSP-21, HSP-26).

**Kachel-Raster (linke Spalte, ca. 65% Breite):**
- Bis zu **10 Folgen ohne Scrollen** sichtbar als 5×2-Raster (E-HSP-8).
- Sind mehr Folgen freigegeben, ersetzt die **letzte Kachel** das nächste
  Album durch eine **„Ältere Folgen"-Kachel** als Funktions-Slot
  (sichtbar als gestrichelte Border, ARASAAC-„mehr"-Pikto, Klick öffnet
  eine Archiv-Sicht — Archiv-View ist OPEN-HSP-J).
- Alle Cover-Slots in den Kacheln nutzen **dasselbe 1:1-Cover-Format**
  wie der Player-Cover (HSP-NEU Layout-Robustheit) — austauschbares Asset
  je Folge (V1: pro Serie einheitliches Default-Cover, OPEN-HSP-A).

**Player (rechte Spalte, ca. 35% Breite, immer sichtbar):**
- Cover groß oben (1:1, identisches Format zum Kachel-Cover).
- Album-Header (Nr + Voice + Titel).
- Track-Liste mittig (skaliert auf bis zu 10 Tracks via
  `grid-auto-rows: minmax(0, 1fr)` ohne Scroll).
- Now-Playing-Zeile (aktueller Track-Name mit Pikto-im-Text-Wortblock,
  HSP-NEU `pikto-hauptbegriff`).
- Controls am Boden (Prev / Play / Next).

**Player-Default-Zustand — „letzter Stand vor Pause":**
**Wenn** für ein Album ein Resume-State besteht (HSP-23) und die View neu
geladen wird, **dann** zeigt der Player diesen Stand: Album-Cover + Titel
+ Track-Position + ein **orange markierter „Weiter hören"-Play-Button**
(visuell vom grünen Standard-Play unterscheidbar). Klick startet die
Wiedergabe an genau dieser Stelle (HSP-23). **Wenn** kein Resume-State
existiert, **dann** zeigt der Player das zuletzt gespielte Album in
seinem Default-Anfang (Track 1).

**Resume-Sichtbarkeit auf der Kachel:** zusätzlich zeigt die zugehörige
Album-Kachel ein orange „Weiter"-Badge oben rechts und einen orangen
Resume-Rand. Ein eigener „Weiter hören"-Banner über dem Kachel-Raster
ist V1 **nicht** vorgesehen — der Resume-Stand lebt im Player rechts
(E-HSP-9, zieht E-HSP-4 nach).

*Test-Implikation:* GET `/display/hoerspiel/<kind_id>/alben` (z. B.
`/display/hoerspiel/mia/alben`) rendert
(a) mindestens eine Album-Kachel pro freigegebenem Album, oder genau 10
sichtbare Kachel-Slots inkl. „Ältere Folgen"-Slot bei mehr als 10
freigegebenen Alben, (b) den Player-Bereich mit dem letzten Stand
(Resume-Album bzw. Default-Anfang des zuletzt gespielten Albums) und
(c) bei vorhandenem Resume-State ein Resume-Badge auf der zugehörigen
Kachel + den orangen „Weiter hören"-Play-Button im Player.

### HSP-3 — Touch-Display, Kind-taugliche Bedienung (Kiosk)
Die View ist für ein Touch-/Kiosk-Display gebaut. **Statisches Dashboard,
keine Menüführung** — oberste Priorität für Kinder-Frontends (Nic-Standard
Werft 2026-06-12). Modus-Wechsel ist kein Navigationsakt; Kacheln und
Player leben gemeinsam auf einer Canvas (HSP-2). Maximale Bedien-
Affordanzen für die Altersklasse der gerade aktiven Instanz:

- Album-Kachel tippen → Player rechts wechselt auf dieses Album und
  Wiedergabe startet (siehe HSP-13).
- Player: großer Play/Pause-Knopf in der Mitte, große Vor/Zurück-Knöpfe
  links/rechts pro Track.
- Kein Wisch, kein Long-Press, kein Multi-Touch, kein Tastatur-Fokus.

Lautstärke wird **nicht** in der App geregelt — System-Lautstärke des
Gerätes reicht.

### HSP-3a — Face-Pille im Kinder-View für Instanz-Wechsel auf geteiltem Tablet
Auf dem geteilten Familien-Tablet (V1-Default, OPEN-HSP-G) trägt die
Kinder-View **oben rechts eine Face-Pille** (Ring + Foto + Name des
aktiven Kindes, gelesen aus `xbuddy-data/familie/familie.json` via
einem schlanken `familie_client` analog `plan/familie_client.py`).
Tap auf die Pille wechselt zur anderen Hörspiel-Instanz (Mia ↔ Finn)
per **vollständiger Navigation** auf die andere Kind-URL
(`/display/hoerspiel/mia/alben` ↔ `/display/hoerspiel/finn/alben`) —
kein State-Wechsel innerhalb derselben Seite, keine Resume-Marken-
Vermischung (localStorage-Namensräume sind URL-getrennt, HSP-23).
Auf einem kind-eigenen Gerät ohne Sharing kann die Pille entfallen
oder reine Anzeige sein.

**n≥3-Form — Cycle-Toggle (Nic-Setzung 2026-07-08, HSP-43/HSP-46, supersedes ENTSCHEID-1263 F2).**
Statt einer Pillen-Reihe der übrigen Instanzen zeigt die Pille immer das
**aktive Kind** (Ring + Foto + Name) mit einem „wechseln"-Hinweis.
Ein Tap führt per **vollständiger Navigation** zum **nächsten Kind im Ring**
(Ring-Reihenfolge aus `config.INSTANZEN`, wrap-around, z. B. mia→finn→emil→mia),
gefiltert auf im Familie-Snapshot vorhandene Personen (PLAN-20-Geist).
EINE Pille statt Reihe beseitigt den visuellen Widerspruch bei n≥3
(„zwei Knöpfe die sich widersprechen"). Die getrennte localStorage-
Namensräume-Semantik (HSP-23) ist unverändert: der Wechsel ist ein
echter URL-Wechsel, kein JS-State. (Nic-Setzung 2026-07-08 →
fix/hoerspiel-switcher-cycle, supersedes ENTSCHEID-1263 F2.)

**Bewusst keine Pille im Eltern-Mini-App-Header** (RAT-17 + #911 Nic-
Wahl Variante C, 2026-06-16): die Eltern-Mini-App ist URL-parametrisch
pro Kind (HSP-33-Form `<funnel>/seiten/hoerspiel/<kind_id>/eltern`),
der Wechsel zwischen Mia und Finn läuft über zwei Web-App-Menu-
Buttons im Telegram-Bot, nicht über ein UI-Element in der App. Damit
bleibt die Eltern-App single-tenant intern, und die Face-Pille-Form
hat n=1 gebautes Beispiel (Kinder-View) statt zwei mit unterschiedlicher
Semantik (Kinder = Instanz-Wechsel, Eltern = Petrantwortungs-Stempel-
Pendant aus Plan-Buddy). MAD-Konventions-Klausel für Face-Pille wartet
auf zweiten Konsumenten in der **gleichen** Semantik (n=2-Regel).

### HSP-4 — Visueller Stil aus dem geteilten Design-Token-Strang
Der visuelle Stil bindet an `display/_shared/design/tokens.css` (DTOK-1..5,
`conventions/design-tokens.md`); keine hartcodierten Farben/Maße im Buddy-
CSS. Die **Stage** (z. B. `toddler` für 4-Jährige mit `font-hand` Patrick
Hand für Body, `font-display` Caveat für Headlines) wird **nicht** im
Code festgelegt, sondern kommt aus der `instance.json` der aktiven
Hörspiel-Instanz (HSP-27, Feld `stage`). Schrift-Disziplin konsistent zu
Routine-/Wetter-/Plan-Buddy. Komponenten erden an die bestehende
Buddy-Card-Optik (Anker: `wetter/static/wetter.css` `.card`/`.card-label`)
und für **Pikto-im-Text-Wortblöcke** an das Routine-`.card-pikto`-Pattern
(`routine/static/routine.css` `.card-pikto`, kompakte Inline-Variante als
`.word-pikto`, HSP-4a).

### HSP-4a — Pikto-im-Text-Wortblock als geteiltes Komponenten-Muster
Wo Text einen ARASAAC-tragbaren Schlüsselbegriff enthält (Folgen-Titel
auf der Kachel, Track-Name im Player), rendert die View den Begriff als
**Inline-Wortblock** mit Pikto + Wort: kleine Pikto-Kachel (ARASAAC-PNG
über ICONS-5, geteilte Icon-Plattform) + Begriff in `font-display`,
gerahmt analog Routine `.card-pikto`. Mehrere Wortblöcke je Satz sind
zulässig; Folgen ohne tragbaren Begriff rendern ihren Titel pur (kein
Pikto-Zwang). Datenquelle: HSP-5a (Album-Manifest) und HSP-6a
(Track-Manifest).

### HSP-4b — Layout-Robustheit: raumfüllend, skaliert, kein Clipping
Das Dashboard ist **statisch und skaliert robust** mit dem verfügbaren
Platz (analog WETTER-25 für den Wetter-Buddy). Verbindliche Bauregeln
für die Implementierung — sonst zerbricht das Layout bei Modus- oder
Viewport-Wechseln:

- **Einheitliches 1:1 Cover-Format** in jedem Cover-Slot (Album-Kachel,
  Player-Cover, „Ältere Folgen"-Pikto-Slot): `aspect-ratio: 1`, gleicher
  Sky-Tint-Hintergrund, gleiches `object-fit: cover` — derselbe Asset-Pfad
  rendert in jedem Slot identisch.
- **Tile-Grid-Disziplin:** `grid-auto-rows: auto` (nicht `1fr`, sonst
  kollidiert die Reihe mit dem aspect-ratio des Covers); `min-width: 0` +
  `min-height: 0` auf jeder Grid-Zelle gegen Inhalts-Push.
- **Titel-Truncate:** Folgen-Titel zwei Zeilen mit `-webkit-line-clamp: 2`
  + `text-overflow: ellipsis` — bei langem Titel kürzt die View, das
  Layout bricht nicht.
- **Skalierende Schriftgrößen:** `clamp(min, vh-basiert, max)` für
  Titel- und Track-Schriftgrößen — anders als feste px-Werte überleben
  Schriftgrößen verschiedene Tablet-Auflösungen (Familien-Tablet, künftig
  ein kind-eigenes Gerät, OPEN-HSP-G).
- **Player-Track-Liste skaliert auf bis zu 10 Tracks:**
  `grid-auto-rows: minmax(0, 1fr)` im Player-Tracks-Container, sodass die
  Liste **ohne Scroll** zwischen 6 (Standard) und 10 Tracks (Maximum)
  trägt.
- **Kein Layout-Bruch beim Modus-Wechsel:** Tap auf eine Kachel ändert
  nur den Player-Inhalt, nicht das Kachel-Raster — Resume-Zustand,
  Player-Default und aktive Wiedergabe leben in einem stabilen Grid.

*Test-Implikation:* die Render-Tests prüfen die View bei zwei
Viewport-Größen (1920×1080 Familien-Tablet und z. B. 1280×800
Mini-Tablet) sowie mit 6 vs. 10 Tracks im aktiven Album — in beiden
Fällen müssen alle Cover-Slots quadratisch sein (gleicher visueller
Format-Schnitt), alle Folgen-Titel lesbar (kein Clip-Bruch), alle
Tracks ohne Scroll sichtbar.

---

## 2. Album-Modell und Track-Struktur

### HSP-5 — Ein Album entspricht einer Folge
Ein **Album** ist die Wiedergabe-Einheit, die eine Hörspiel-Folge abbildet.
Pflichtfelder im Manifest: stabile `id` (`folge-<nummer>`), `nummer` (int),
`titel` (string), `voice` (`shimmer` | `onyx`), `erstellt-am` (ISO-Datum),
`freigegeben` (bool, V1: nach Eltern-Freigabe immer `true`), `cover-asset`
(Pfad innerhalb des Display-Statik-Namensraums), `tracks` (geordnete Liste).
Format-Skizze: HSP-21.

### HSP-5a — Pikto-Hauptbegriffe im Folgen-Titel (optional)
Ein Album-Manifest **kann** ein Feld `pikto-hauptbegriffe` tragen — eine
geordnete Liste von Schlüsselwort-Pikto-Mappings für den Folgen-Titel:

```json
"pikto-hauptbegriffe": [
  {"wort": "Trübsee", "arasaac-id": 6022}
]
```

**Wenn** das Feld vorhanden ist, **dann** rendert die Album-Kachel den
Folgen-Titel mit Inline-Wortblöcken nach HSP-4a — die genannten Wörter
werden im Titel-Fließtext durch Pikto-Wortblöcke ersetzt. **Wenn** das
Feld fehlt oder leer ist, **dann** rendert die Kachel den Titel pur.

**V1-Befüllung:** Der Album-Builder befüllt das Feld in V1 **nicht
selbst** — V1 hat **keine eigene Pikto-Klassifikations-Logik**
(weder Heuristik noch LLM-Pass). Stattdessen:

1. **Neue Alben** (aus dem Eltern-Chat-Skill HFE-5 / `POST /alben`)
   landen mit dem Feld **leer** (`pikto-hauptbegriffe: []`) — die View
   rendert den Titel pur.
2. **Bestehende Folgen 14–22** (Migration) bekommen das Feld per Hand
   in einer einmaligen Befüllungs-Datei `hoerspiel/data/pikto-mapping.json`
   beim Setup — der Album-Builder liest sie beim Manifest-Schreiben und
   überträgt die Mappings in das Manifest.
3. **V2-Erweiterung:** automatische Befüllung per Heuristik oder
   LLM-Klassifikation kommt als eigenes Ticket, **nicht in V1**
   (OPEN-HSP-P).

### HSP-6 — Ein Album besteht aus geordneten Tracks
Ein Album hat eine geordnete Liste von Tracks. Der Track ist die
Wiedergabe-Einheit unter dem Album. Pflichtfelder je Track: stabile `id`,
`position` (int, ab 1), `dauer-sek` (int), `audio-asset` (Pfad),
`art` ∈ `intro` | `inhalt` | `outro`. `titel` ist optional und V1 nicht
zwingend in der View angezeigt.

**Wenn** ein Album geladen wird, **dann** sind seine Tracks deterministisch
in `position`-Reihenfolge sortiert.

### HSP-6a — Pikto-Hauptbegriffe im Track-Namen (optional)
Ein Track **kann** ein Feld `pikto-hauptbegriffe` tragen — analoge Form
wie HSP-5a (Liste von Schlüsselwort-Pikto-Mappings). Die Player-View
rendert die Track-Liste und den Now-Playing-Bereich mit Inline-Wortblöcken
nach HSP-4a. Fehlt das Feld, rendert die View den Track-Namen (oder die
Track-Position bei fehlendem `titel`) pur.

**V1-Befüllung:** analog HSP-5a — neue Tracks landen mit leerem Feld;
die Folgen-22-Migration (und ggf. ältere) kann Tracks per Hand in der
`pikto-mapping.json` mit Pikto-Mappings versorgen. V1-Album-Builder hat
**keine eigene Track-Klassifikations-Logik**.

### HSP-7 — Zielgröße eines Inhalts-Tracks: 3–4 Minuten
Inhalts-Tracks (`art = inhalt`) enthalten **3–4 Minuten** Audio. Die
Zerlegung schneidet an natürlichen Absatzgrenzen des Folgentextes, nicht
auf Zeit-Hartschnitten. Toleranz: akzeptierter Korridor 2,5 – 4,5 min,
weil Absatzgrenzen Vorrang haben (HSP-14).

### HSP-8 — Intro und Outro sind geteilte Serien-Assets
Der Intro-Reim (jede Folge wortgleich) und der Outro-Reim (jede Folge
wortgleich) werden **nicht pro Folge synthetisiert**. Sie sind vier feste
Asset-Dateien (je Voice ein Intro-MP3 und ein Outro-MP3), einmalig
vorab erstellt (HSP-22) und für alle Folgen wiederverwendet.

**Wenn** ein neues Album entsteht, **dann** referenziert es als Position-1-
Track die zur gewählten `voice` passende Intro-Datei und als Position-N-
Track die passende Outro-Datei. Diese Tracks sind im Album mit `art = intro`
bzw. `art = outro` markiert und kosten keine TTS-Gebühren bei der
Folgen-Produktion (E-HSP-2).

### HSP-9 — Track-Reihenfolge in einem Album
Pro Album: Position 1 ist Intro-Track, Positionen 2 bis N-1 sind Inhalts-
Tracks in Reihenfolge des Folgentextes, Position N ist Outro-Track.

---

## 3. LLM-Adapter (App-eigene Funktion, Provider-Switch)

> Die LLM-Funktion ist eine Funktion **dieser App** — keine Plattform-
> Fähigkeit. RAT-6 hält den Plattform-LLM-Gateway bis ab dem zweiten
> KI-Buddy zurück; HSP ist der erste KI-Buddy und legt das **konsistent
> kopierbare Pattern** (analog `eltern-chat/providers/`).

### HSP-10 — LLM-Adapter mit Provider-Switch
Der Hörspiel-Buddy ruft den LLM-Anbieter über ein **internes Provider-
Adapter-Modul** (`hoerspiel/providers/`) mit derselben Form wie
`eltern-chat/providers/`: ein abstrakter Basis-Adapter (`base.py`) und je
Provider eine konkrete Implementierung. **V1 liefert ausschließlich den
`claude`-Adapter** (`providers/base.py` + `providers/claude.py`). Das
Adapter-Pattern ist kopierfähig vorbereitet — ein zweiter Provider
landet in V2 als neue Datei (`providers/<name>.py`) hinter derselben
Basis-Schnittstelle, ohne Strukturänderung. **Mistral ist V2**
(OPEN-HSP-N): in V1 ist der Wert `mistral` für `llm_provider` **kein
gültiger Wert** — der Config-Loader (HSP-26) und `PATCH /config`
(HSP-17) lehnen unbekannte Provider mit HTTP 422 + Klartext-Hinweis ab.

**Wenn** der konfigurierte Provider (HSP-26) `claude` ist, **dann** wird
der Anthropic-SDK-Adapter genutzt mit dem im Provider-Default petrankerten
Modell-Pin (`claude-opus-4-7`) oder dem in der Config überschriebenen
Wert.

*Verworfen (E-HSP-3):* Plattform-LLM-Gateway in V1, weil HSP der erste KI-
Buddy ist und das Pattern erst beim zweiten Vorkommen ratifiziert wird
(RAT-6, „konsistent kopieren statt antizipativ generalisieren").

### HSP-11 — Folgen-Vorschlag als trigger-agnostische Funktion
Die Folgen-Erzeugung ist eine aufrufbare Funktion des Buddys. Eingang: eine
**Folgen-Idee** als Text (1–2 Sätze, vom Eltern-Chat-Skill geliefert).
Wirkung: lesender Zugriff auf Welt-Bible und Folgen-Historie (intern,
APP-3); ein LLM-Aufruf an den konfigurierten Provider mit dem System-
Prompt aus `hoerspiel/prompts/geschichtenbuddy.md` und Bible+Historie als
Kontext; **keine** Familien-Daten-Änderung (Historie wird erst beim
Album-Bau fortgeschrieben, HSP-15). Ausgang: ein **Vorschlag** mit Feldern
`titel` (string) und `text` (markdown, Absätze mit `\n\n` getrennt, erster
Absatz = Intro-Reim-Platzhalter wortgleich, zweiter Absatz = Titel-Block,
restliche Absätze = Story).

Die Funktion ist **trigger-agnostisch** (analog WZE-1): wer sie aufruft —
der Eltern-Chat-Skill in V1, ein Sprach-Trigger fürs Kind in V2
(OPEN-HSP-B), ein Cron-Job — ist nicht Teil ihres Vertrags. Schnittstelle:
HSP-17.

### HSP-12 — Prompt-Templates leben im Buddy-Code-Bereich
Die System-Prompts für die LLM-Aufrufe leben unter
`hoerspiel/prompts/<name>.md` im Code-Bereich (committet, nicht
gitignored). **V1**: `prompts/geschichtenbuddy.md` (System-Prompt für die
Folgen-Erzeugung). Das Template ist nicht familien-spezifisch — die
Bible darin ist Eingabe-Variable, nicht Inhalt der Vorlage. Die familien-
spezifische Welt-Bible ist Daten (HSP-14).

---

## 4. TTS-Adapter und Synthese (App-eigene Funktion)

### HSP-13 — TTS-Engine, Region, Voices
Der Synthese-Pfad nutzt **Azure OpenAI Service**, Modell `tts-hd`, deployed
in Region `swedencentral` (EU-Hosting, Microsoft-DPA). Eingabe-Text wird
laut Microsoft-Datenrichtlinie nicht für Modell-Training verwendet und
nicht persistiert. Der Buddy unterstützt für V1 zwei Voices:

- `shimmer` — weich, weiblich
- `onyx` — tief, männlich

Beim Album-Anstoß wählt der Skill (Eltern) die Voice. Die Wahl ist **pro
Album fix** (kein Mix innerhalb eines Albums in V1, E-HSP-1).

Die **Default-Voice** für neue Folgen ist familien-konfigurierbar via
`default_voice` in `hoerspiel.json` (HSP-27) und zur Laufzeit über die
Eltern-Mini-App (HSP-34) per `PATCH /api/v1/hoerspiel/<kind_id>/config` mit Body
`{"default_voice": "shimmer"|"onyx"}` setzbar. Der HFE-Skill liest die
Default-Voice für seine Vorschlag-Erzeugung weiter über `GET /config`
(HFE-4, unverändert).

### HSP-14 — Synthese-Architektur: Absatz-Calls mit strukturierten Pausen
Der Inhalt eines Albums wird in **Absatz-Calls** synthetisiert: pro
Story-Absatz ein einzelner TTS-Call mit `speed=1.0`, dazwischen Stille
als ffmpeg-Silence-Concat (siehe `hoerspiel/album_builder.py:169-211`).
Die Bündel-Heuristik unten bleibt für die **Track-Gruppierung** auf der
Manifest-Ebene relevant (mehrere Absatz-MP3s pro Track werden als ein
Track-MP3 zusammengeführt).

> **Drift-Reconcile 2026-06-15** (Refs #848 Werft): der vorige Spec-Text
> sagte „Bündel-Calls" (ein TTS-Call pro Bündel); der Code macht aber
> seit Anfang an Absatz-Calls. Die Spec ist auf den Code gehoben — die
> Bündel-Logik gilt jetzt nur noch für die Track-Gruppierung im
> Manifest, nicht für die Synthese-Granularität.

Bündel-Heuristik (für Track-Gruppierung): solange das
laufende Bündel < ~450 Wörter, nächsten Absatz dranhängen; bei ≥450
Wörtern Bündel abschließen. **Schnitte fallen immer auf Absatzgrenzen,
nie mitten in einen Satz.**

Pausen werden über **expliziten Silence-Insert** abgebildet, nicht über
den `speed`-Parameter der TTS-API. Die Werft-F1-Probe 2026-06-15
(`/tmp/werft-hoerspiel-probe/`, vergleichbarer Hörtest TTS-`speed` vs.
Browser-`playbackRate` auf identischem Text) hat bestätigt, dass eine
Tempo-Veränderung **am Wiedergabepfad** (Mini-App-`<audio>.playbackRate`,
HSP-34) deutlich besser klingt als am Synthese-Pfad. Tempo-Tuning lebt
darum ausschließlich auf der Mini-App-Wiedergabe-Seite, nicht in der
Synthese.

Standard-Pausen-Werte (familien-konfigurierbar, HSP-27):

| Pause | Daten-Konfig-Feld | Default | Wirkung |
|---|---|---|---|
| nach Intro-Track-Ende | (im Intro-Asset enthalten) | 1,2 s | fix |
| nach Titel-Absatz (`Folge N: <Titel>`) | `pause_titel_sek` | 1,8 s | bei nächster Generierung |
| zwischen Inhalts-Absätzen + am Bündel-Ende + vor Outro | `pause_absatz_sek` | 0,55 s | bei nächster Generierung |

`pause_absatz_sek` und `pause_titel_sek` sind familien-spezifisch via
`hoerspiel.json` und zur Laufzeit über die Eltern-Mini-App
(HSP-34) per `PATCH /config` setzbar (Range: `0.0–2.0` s bzw.
`0.5–3.0` s). Die Werte gelten bei der **nächsten Generierung** —
bereits gebaute Alben bleiben unverändert (Pausen sind im MP3
eingebrannt).

Der `speed`-Parameter der TTS-API wird **nicht** genutzt (immer 1.0,
Werft-F1-Probe 2026-06-15 bestätigt).

*Test-Implikation:* ein Folgentext mit fünf Absätzen (à 200 Wörter)
ergibt zwei Bündel-Tracks; eine Folge mit zwei Absätzen (à 600 Wörter)
ergibt zwei Bündel-Tracks. Die Bündel-Schnitt-Funktion ist deterministisch
und ohne Netz testbar.

### HSP-15 — Album-Bau als atomarer Vorgang
**Wenn** der Buddy einen `POST /api/v1/hoerspiel/<kind_id>/alben`-Aufruf erhält,
**dann** läuft folgender Vorgang in dieser Reihenfolge:

1. Album-Manifest anlegen (id, nummer, titel, voice, erstellt-am)
2. Intro-Track referenzieren (Shared-Asset-Pfad je Voice)
3. Story-Absätze in 3–4-min-Bündel gruppieren (HSP-14)
4. Pro Bündel einen Synthese-Call (Azure tts-hd, gewählte Voice, speed=1.0,
   response_format=mp3) → MP3 ablegen
5. Outro-Track referenzieren (Shared-Asset-Pfad je Voice)
6. Cover wählen (V1: Default-Cover, HSP-19)
7. Manifest finalisieren, `freigegeben` auf `true` setzen
8. **Folgen-Historie fortschreiben** (Side-Effekt, HSP-16)

V1-Vereinfachung: synchron mit Wartezeit-Hinweis im Response-Body
(Generierung dauert je nach Quota 1–5 min). Asynchrone Variante ist
OPEN-HSP-L.

*Test-Implikation:* der Album-Bau ist gegen einen kontrollierten Doppelten
(Mock-TTS-Adapter) ohne Netz testbar; das Manifest wird **atomar**
geschrieben (Temp-Datei + Rename), damit ein gleichzeitiger View-Read nie
ein halbes Manifest sieht. Der Resume-Test (HSP-24) hängt von Determinismus
des Album-Baus ab.

### HSP-16 — Folgen-Historie wird vom Buddy gepflegt
Die **Folgen-Historie** (`<data>/folgen-historie.md`) ist eine chronologisch
geordnete Markdown-Datei mit einem Eintrag je freigegebenem Album: Folgen-
Nummer, Titel, Erscheinungsdatum, eine 2–3-Satz-Synopse für den nächsten
LLM-Kontext, offene Erzählfäden.

**Wenn** ein Album über HSP-15 erfolgreich gebaut wurde, **dann** ergänzt
der Buddy die Folgen-Historie um den neuen Eintrag (atomarer Schreibpfad,
Append am Ende der Datei). Die Synopse wird im selben LLM-Provider-Aufruf
miterzeugt oder in einem zweiten kurzen Aufruf — Implementations-Detail.

*Test-Implikation:* ein Album-Bau ändert genau einen Datei-Inhalt
(`folgen-historie.md`) konsistent zum geschriebenen Manifest; ein
fehlgeschlagener Album-Bau lässt die Historie unverändert.

---

## 5. Schnittstellen (HTTP-API)

> V1 exponiert die volle API-Schnittstelle (Interface-first, Nic-Standard
> 2026-06-06). Die Skill-Integration (Familien-Schnittstelle, HFE) zieht
> nach; der V1-Abend-Test seedet über die API per `curl` (HSP-25).

### HSP-17 — API-Endpoints
Der Buddy stellt unter `/api/v1/hoerspiel/<kind_id>/<resource>` folgende
Endpoints bereit (BUD-1b, URL-3a, RAT-17, #965). Instanz-gebundene Endpoints
tragen `<kind_id>` als zweites URL-Segment; instanz-unabhängige
Shared-Asset-Endpoints verzichten darauf:

| Methode | Pfad | Zweck | Aufrufer |
|---|---|---|---|
| `GET` | `/api/v1/hoerspiel/<kind_id>/bible` | Welt-Bible als Markdown lesen | Skill (Folgen-Prompt) |
| `GET` | `/api/v1/hoerspiel/<kind_id>/folgen-historie` | Folgen-Historie als Markdown lesen | Skill, künftige Konsumenten |
| `GET` | `/api/v1/hoerspiel/<kind_id>/alben` | Alle freigegebenen Alben als JSON-Array | View, Skill |
| `GET` | `/api/v1/hoerspiel/<kind_id>/alben/<id>/manifest` | Album-Manifest als JSON | View, Skill |
| `POST` | `/api/v1/hoerspiel/<kind_id>/folgen-vorschlag` | Folgen-Idee → `{titel, text}` per LLM | Skill (HFE) |
| `POST` | `/api/v1/hoerspiel/<kind_id>/alben` | Album bauen (TTS-Pipeline + Historie-Update) | Skill (HFE) |
| `GET` | `/api/v1/hoerspiel/<kind_id>/config` | Aktive Eltern-Tuning-Konfig (Provider, Modell, Voice, Pausen, Tempo, verfügbare Modelle) | Mini-App (HSP-34), HFE-Skill |
| `PATCH` | `/api/v1/hoerspiel/<kind_id>/config` | Eltern-Tuning setzen | Mini-App (HSP-34) |
| `GET` | `/api/v1/hoerspiel/<kind_id>/themen` | Kuratierte Themen-Liste je Alter (aus `instance.json`, RAT-17 #965) | HFE-Skill (HFE-3) |
| `GET` | `/api/v1/hoerspiel/<kind_id>/alben/<id>/audio/<track>.mp3` | Audio-Track streamen (Range-Requests) | Mini-App-Player (HSP-35/37) |
| `GET` | `/api/v1/hoerspiel/<kind_id>/resume?album=<id>` | Resume-Stand lesen | Mini-App-Player (HSP-36) |
| `PUT` | `/api/v1/hoerspiel/<kind_id>/resume` | Resume-Stand setzen | Mini-App-Player (HSP-36) |
| `GET` | `/api/v1/hoerspiel/shared-assets/status` | Vorhanden je Voice (`shimmer.intro`, `shimmer.outro`, `onyx.intro`, `onyx.outro`) | Setup-Check, Skill |
| `POST` | `/api/v1/hoerspiel/shared-assets/rebuild` | Intro/Outro neu vorsynthetisieren | Setup-Aufruf (HSP-22) |

**`POST /folgen-vorschlag`** Body: `{idee: string}`. Response:
`{titel: string, text: string, folgen-nr-vorschlag: int}`. Kein Side-
Effekt auf Familien-Daten.

**`POST /alben`** Body: `{titel: string, text: string, voice: "shimmer"|"onyx", idee: string}`.
Response: `{album-id: string, manifest-pfad: string, dauer-sek-gesamt: int}`.
Side-Effekt: Album auf Disk + Folgen-Historie fortgeschrieben (HSP-16).
Idempotenz: ein erneuter Aufruf mit identischen Inhalt + Voice erkennt
das bereits gebaute Album über einen Hash und antwortet mit demselben
`album-id` ohne erneute TTS-Kosten.

**`GET /config`** Response (alle Felder Pflicht):
```json
{
  "llm_provider": "claude" | "mistral",
  "llm_model": "<id-aus-modelle_je_anbieter>",
  "default_voice": "shimmer" | "onyx",
  "pause_absatz_sek": 0.55,
  "pause_titel_sek": 1.8,
  "playback_tempo": 1.0,
  "anthropic_key_set": true,
  "mistral_key_set": true,
  "azure_key_set": true,
  "voices_verfuegbar": ["shimmer", "onyx"],
  "provider_verfuegbar": ["claude", "mistral"],
  "modelle_je_anbieter": {
    "claude":  [{"id": "claude-opus-4-7", "label": "Opus 4.7 (kreativ, langsamer, teurer)"}, ...],
    "mistral": [{"id": "mistral-large-2411", "label": "Large 2.1 (Frontier, kreativ)"}, ...]
  }
}
```

`provider_verfuegbar` enthält nur Provider mit gesetztem Key — die
Mini-App rendert ihr Anbieter-Dropdown daraus, sodass Provider ohne
Key gar nicht erst auswählbar sind. `modelle_je_anbieter` trägt die
**ratifizierten Modell-IDs** je Provider (HSP-27b).

**`PATCH /config`** Body (alle Felder optional; nur die genannten Felder werden gesetzt):
```json
{
  "llm_provider": "claude" | "mistral",
  "llm_model": "<id-aus-modelle_je_anbieter>",
  "default_voice": "shimmer" | "onyx",
  "pause_absatz_sek": 0.0-2.0,
  "pause_titel_sek": 0.5-3.0,
  "playback_tempo": 0.7-1.3
}
```

Wirkung: setzt die genannten Werte (Provider+Modell in `config.json`,
die übrigen vier in `hoerspiel.json`, beide atomar geschrieben). Gibt
die neue effektive Konfig zurück (gleiches Schema wie `GET /config`).

HTTP 422 bei: Range-Verletzung (`pause_*`, `playback_tempo`),
Whitelist-Verletzung (`llm_provider`, `default_voice`), unbekanntes
`llm_model` (nicht in `AVAILABLE_MODELS` des gesetzten Providers),
oder `llm_provider`-Wechsel ohne konfigurierten Key.

**`GET /themen?alter=<n>`** Response: `{"alter": 4, "themen": ["Mut beim
Probieren", "Streit vertragen", ...]}`. Quelle:
`hoerspiel.json.themen_je_alter[<alter>]` (HSP-27a). 404 wenn Alter
nicht gepflegt: `{"fehler": "Themen-Liste für Alter <n> nicht
gepflegt — Eltern können im Chat eigene Idee geben."}`.

**`GET /alben/<id>/audio/<track>.mp3`** liefert die rohen MP3-Bytes
des Tracks (HSP-37). Range-Requests Pflicht. `Content-Type: audio/mpeg`.
`Cache-Control: private, max-age=86400` (Album-MP3s sind immutable je
`album-id`).

**`GET /resume?album=<id>`** Response: `{"album": "<id>", "track":
<position>}` (Track-Anfang gerundet, HSP-23) wenn ein Stand existiert.
Wenn **kein Stand existiert**: 200 mit Default-Body `{"album": "<id>",
"track": 0, "status": "neu"}` — kein 404 (HSP-36-Update).

**`PUT /resume`** Body: `{"album": "<id>", "track": <position>}`.
Idempotent. Schreibt den Stand atomar.

### HSP-18 — Direkter Datei-Zugriff durch andere Apps ist verboten
Welt-Bible, Folgen-Historie, Album-Manifeste und Audio-Assets liegen im
Daten-Bereich des Buddys. Andere Apps und der Eltern-Chat-Skill greifen
**ausschließlich** über die HTTP-API zu (APP-3). Insbesondere liest der
Skill die Bible über `GET /bible`, nicht aus dem Dateisystem.

---

## 6. Kinder-View — Kacheln und Player

(Die Klauseln in diesem Abschnitt sprechen vom „Kind" als generischem
Akteur — V1 sind das Mia und Finn, jede Instanz mit ihrer eigenen
Album-Liste und Resume-Marke.)

### HSP-19 — Album-Kachel
Eine Kachel zeigt: das Cover-Asset des Albums (V1: festes Default-Cover
für die ganze Serie, OPEN-HSP-A), den Album-Titel als Text, und — falls
für dieses Album ein Resume-State existiert — eine sichtbare „Weiter
hören"-Markierung. Tap-Affordanz ist die gesamte Kachel.

### HSP-20 — Tap auf Kachel startet (oder setzt fort) das Album
**Wenn** das Kind auf eine Album-Kachel tippt, **dann**:

- Falls für dieses Album ein Resume-State existiert (HSP-23) und das
  Album noch nicht vollständig durchgehört wurde: Player startet am
  gespeicherten Track an der gespeicherten **Track-Anfangs**-Position
  (HSP-24).
- Sonst: Player startet bei Track 1 (Intro) ab Sekunde 0.

### HSP-21 — Player-Bedienung
Der Player zeigt:

- den aktuellen Album-Titel
- den aktuellen Track (Nummer / Gesamtanzahl)
- großen Play/Pause-Knopf in der Mitte
- großen „voriger Track"-Knopf links
- großen „nächster Track"-Knopf rechts
- Fortschrittsbalken des aktuellen Tracks (Anzeige, V1 nicht zwingend
  interaktiv)

**Wenn** das Kind auf „nächster Track" tippt, **dann** springt die
Wiedergabe sofort zum Anfang des nächsten Tracks im Album. Beim letzten
Track des Albums springt sie zum ersten Track desselben Albums zurück
(kein automatisches Verkettungswechseln zu einem anderen Album in V1).

**Wenn** das Kind auf „voriger Track" tippt, **dann** springt sie zum
Anfang des aktuellen Tracks zurück. Tippt sie nochmal innerhalb von 3 s,
springt sie zum vorherigen Track (klassisches Audio-Player-Muster).

### HSP-22 — Audio-Wiedergabe robust gegen Geräte-Schlaf
Die Wiedergabe verwendet die **MediaSession-API** des Browsers und ein
**PWA-Manifest** mit `display: standalone`, sodass:

- Lock-Screen-Kontrollen für Play/Pause erscheinen
- Audio nicht stoppt, wenn der Bildschirm schwarz wird
- Album-Titel und Track-Position auf dem Lock-Screen sichtbar sind

V1-Annahme: das Kind nutzt die App im Browser oder als „Zum Home-Bildschirm
hinzufügen"-PWA — bei zwei Instanzen je Kind eine eigene URL
(`/display/hoerspiel/mia/alben`, `/display/hoerspiel/finn/alben`).
Eigenes Kind-Gerät = OPEN-HSP-G.

**Audio-Ausgabe — lokal am App-Gerät (Audio-Ziel-Weiche SUPERSEDED 2026-07-27).**
Der Player in `alben.js` spielt Audio **immer lokal** im Kind-View ab (lokales
`<audio>`-Element, MediaSession, Wake-Lock). Die frühere `audio_ziel`-Weiche
(`display` vs. `panel`-Push an ein anderes Gerät) ist mit dem Ein-App-Default
aufgehoben — siehe §13 (SUPERSEDED). Code-Rückbau über #1471.

---

## 7. Resume-Verhalten

### HSP-23 — Resume-Marke pro Album, auf Track-Anfang gerundet
Pro Album wird **eine** Resume-Marke gehalten: `track-position` (int,
welcher Track gerade lief). **Innerhalb** eines Tracks wird die Offset-
Position bei Wiederaufnahme auf den **Track-Anfang** gerundet — das Kind
hört den unterbrochenen 3–4-Minuten-Block ab seiner letzten Schwelle, nicht
mitten im Satz. Track-Granularität ist die natürliche Wiederaufnahme-
Granularität (E-HSP-4).

V1 hält die Resume-Marke im Browser-`localStorage` pro Album. Ein Server-
seitiger Resume-State (Multi-User, Multi-Gerät-Sync) ist OPEN-HSP-G-Folge.
Da die zwei Instanzen Mia/Finn unter getrennten URLs leben, hat jede
ihren eigenen `localStorage`-Namensraum — kein Mischen über den Wechsel.

**Wenn** das Kind die View wieder aufruft und für ein Album ein Resume-
State besteht, **dann** zeigt die Kachel zusätzlich „Weiter hören" und der
Tap startet die Wiedergabe beim **Anfang** des unterbrochenen Tracks.

**Wenn** das Album zu Ende läuft (Outro abgespielt), **dann** wird die
Marke zurückgesetzt (= „fertig gehört").

### HSP-24 — Test-Determinismus: injizierbarer `now` für Rollover
Code-Pfade, die Datum/Zeit für Album-Sortierung, Resume-Rundung oder
Folgen-Historie-Einträge nutzen, lesen die Zeit über einen injizierbaren
Provider (`now`-Funktion), nie über die Wall-Clock tief im Code. Tests
setzen `now` deterministisch. (Vermeidet die Klasse von Bugs, bei denen
ein Rollover-Test beim Merge grün ist und Stunden später rot wird.)

---

## 8. Datenhaltung

### HSP-25 — Daten-Layout (mit `<kind_id>`-Owner-Achse, RAT-17)
Der Hörspiel-Buddy hält drei Klassen Daten im Per-Instanz-Daten-Bereich
**je Kind** (BUD-2a, gitignored über `hoerspiel/.gitignore` per BUD-2b).
Die `<kind_id>` (V1: `mia`, `finn` — FK in `xbuddy-data/familie/familie.json`)
ist die alleinige Owner-Achse:

```
xbuddy-data/hoerspiel/<kind_id>/
  instance.json                # Per-Instanz-Daten-Konfig (HSP-27)
  bible.md                     # Welt-Bible (kind-spezifisch)
  folgen-historie.md           # chronologische Synopsen aller Folgen
  alben/<album-id>/
    manifest.json              # Album-Manifest (HSP-26)
    audio/<track-id>.mp3       # Inhalts-Tracks
  shared-assets/
    intro_shimmer.mp3          # einmal vorsynthetisiert (HSP-22)
    outro_shimmer.mp3
    intro_onyx.mp3
    outro_onyx.mp3
    intro.txt                  # Quell-Text für Re-Build
    outro.txt
    cover-default.jpg          # Default-Serien-Cover, 1:1, mind. 1000×1000
  pikto-mapping.json           # Migration-Mappings für HSP-5a/HSP-6a
```

Der Filesystem-Daten-Pfad pro Instanz wird über die ENV-Variable
`HOERSPIEL_DATA_ROOT` (CONFIG-5) auf `xbuddy-data/hoerspiel/<kind_id>`
gesetzt — eine systemd-Drop-In-Datei pro Instanz, kein Code-Hardcode
(SVC-5, SVC-5a). Die `<kind_id>` ist außerdem als zweites URL-Segment
sichtbar (HSP-26, URL-3a-konform).

Die Welt-Bible ist der Musterfall der **Familie-3-Probe**: was sich je
Familie und je Kind ändert, ist Daten, nicht Code (E-HSP-5). Eine andere
Familie und ein anderes Kind haben eine andere Bible (andere Charaktere,
andere Welt) — dieselbe App.

**Datei-Format-Disziplin:**
- `bible.md` und `folgen-historie.md` sind **freie Markdown-Strings**
  ohne Schema — Buddy gibt sie 1:1 über `GET /bible` und
  `GET /folgen-historie` zurück. Der Skill nutzt sie als LLM-Kontext.
- `pikto-mapping.json` ist eine flache Tabelle für die Migration der
  Folgen 14–22 (HSP-5a-V1-Befüllung):
  ```json
  {
    "folge-22": {
      "album": [{"wort": "Trübsee", "arasaac-id": 6022}],
      "track-3": [{"wort": "Rucksack", "arasaac-id": 2475}],
      "track-4": [{"wort": "Bahnhof", "arasaac-id": 3099}]
    }
  }
  ```
  Der Album-Builder konsultiert sie beim Manifest-Schreiben für die
  jeweilige Folgen-ID und überträgt die Mappings als
  `pikto-hauptbegriffe` ins Manifest.
- `cover-default.jpg` ist das einheitliche Serien-Cover (HSP-4b
  Layout-Robustheit, E-HSP-10) — 1:1-Format ist verbindlich.

**Datei-Inhalte sind Domänendaten, kein Konfig** (BUD-2a, getrennt von
Runtime-Config HSP-27). Direkter Datei-Zugriff durch andere Apps ist
verboten (HSP-18, APP-3).

### HSP-25a — Erst-Bestückung der Domänen-Daten pro Kind-Instanz (V1, manuell)
Die Domänen-Daten (`bible.md`, `folgen-historie.md`, `pikto-mapping.json`,
`shared-assets/cover-default.jpg`, `shared-assets/intro.txt`,
`shared-assets/outro.txt`) werden in V1 **manuell pro Kind-Instanz**
beim Einrichten ins `xbuddy-data/hoerspiel/<kind_id>/`-Verzeichnis
gelegt — **kein automatisches Migration-Skript V1**, **keine** Bootstrap-
Generalisierung (Premature Generalization, RAT-17). Der bestehende
`deploy/hoerspiel/bootstrap.sh` ist Mia-spezifisch und wird **nicht**
generalisiert — Finn + spätere Instanzen werden manuell initialisiert.

Quell-Pfade für die **Mia-Instanz** (`xbuddy-data/hoerspiel/mia/…`):

- `bible.md` ← Inhalt aus
  `brainstorm/ideas/mia-hoerspiel-app/welt_und_charaktere.md`
- `folgen-historie.md` ← Inhalt aus
  `brainstorm/ideas/mia-hoerspiel-app/folgen_historie.md`
- `pikto-mapping.json` ← per Hand für die historischen Folgen 14–22
  (HSP-5a-V1)
- `shared-assets/cover-default.jpg` ← produziertes ChatGPT-Aquarell
  (Stigi-Stieglitz + Igel + Schmuggli-Amsel), aktuell als
  `xbuddy-data/photo/medien/foto-01.jpg` (1254×1254 px)
- `shared-assets/intro.txt`, `shared-assets/outro.txt` ← der Intro-Reim
  und Outro-Reim aus der Welt-Bible (sie sind in
  `welt_und_charaktere.md` als wortgleich markiert) — einmaliger
  Copy-Paste-Schritt durch den Hub-Owner als Quell-Text für die
  Vorsynthese (HSP-29)

Quell-Pfade für die **Finn-Instanz** (`xbuddy-data/hoerspiel/finn/…`):
Bibel + Folgen-Historie + Cover schreibt Nic per Hand (RAT-17
Entscheidung 5 — kein LLM-Bible-Buddy-Flow in V1). Folge-Ticket #912
trägt diesen Inhalts-Schritt; Service-Skelett (#909) legt nur die
Verzeichnis-Struktur an.

Ein automatisches Migrations-Werkzeug (Setup-Skript) ist V2-Material
(OPEN-HSP-Q).

**Bestehender Mia-Daten-Umzug (Single-Tenant → `<kind_id>=mia`)**
folgt SVC-5 wörtlich (Ticket #908): `cp -a` der Alt-Pfade nach
`xbuddy-data/hoerspiel/mia/`, Drop-In `20-data-path.conf` umstellen,
Smoke-Test, **dann erst** Alt-Pfad entfernen. Restic-Snapshot davor als
Gürtel, nicht als Rollback-Mechanismus.

### HSP-26 — Album-Manifest-Format (JSON, mit `<kind_id>`-tragenden URLs)
Jedes Album hat ein Manifest unter
`xbuddy-data/hoerspiel/<kind_id>/alben/<album-id>/manifest.json`. Die
`audio-asset`-/`cover-asset`-URLs tragen die `<kind_id>` als zweites
Segment im Display-Pfad (URL-3a-Form, RAT-17):

```json
{
  "id": "folge-22",
  "nummer": 22,
  "titel": "Schmuggli erzählt vom Trübsee",
  "voice": "shimmer",
  "erstellt-am": "2026-06-12",
  "freigegeben": true,
  "cover-asset": "/display/hoerspiel/mia/data/shared-assets/cover-default.jpg",
  "tracks": [
    {"id": "intro-shimmer", "position": 1, "art": "intro",
     "audio-asset": "/display/hoerspiel/mia/data/shared-assets/intro_shimmer.mp3",
     "dauer-sek": 18},
    {"id": "folge-22-track-02", "position": 2, "art": "inhalt",
     "audio-asset": "/display/hoerspiel/mia/data/alben/folge-22/audio/track-02.mp3",
     "dauer-sek": 215, "titel": null},
    {"id": "outro-shimmer", "position": "N", "art": "outro",
     "audio-asset": "/display/hoerspiel/mia/data/shared-assets/outro_shimmer.mp3",
     "dauer-sek": 22}
  ]
}
```

`audio-asset`-Pfade werden vom Buddy-Service über den Display-Namensraum
ausgeliefert (Route `GET /display/hoerspiel/<kind_id>/data/<sub>` mappt
auf den jeweiligen Daten-Bereich, nur freigegebene Album-IDs). Die
zentrale URL-Form lebt im Code als parametrische Funktion
`f(kind_id) → /display/hoerspiel/<kind_id>/data` (vorhanden als
`DISPLAY_DATA_PREFIX` in `hoerspiel/album_manifest.py`, im Zuge von
#908 auf `kind_id`-Argument umgestellt). Die Pfade sind absolute
View-URLs für das Frontend.

API-Pfade folgen analog der URL-3a-Form:
`/api/v1/hoerspiel/<kind_id>/<resource>` (z. B.
`/api/v1/hoerspiel/mia/alben`, `/api/v1/hoerspiel/finn/folgen-vorschlag`).

---

## 9. Konfiguration

### HSP-27 — Konfigurationswerte (Runtime + Per-Kind-Instanz)
Drei Konfig-Ebenen, klar getrennt nach Lebenszyklus (RAT-17):

- `hoerspiel/config.json` — **Runtime-Config** (Bind, Log, Provider,
  Modelle), via `tools/configloader.py` (CONFIG-1). Eine Datei pro
  Service-Prozess, gitignored über `hoerspiel/.gitignore`. ENV-Overrides
  folgen `HOERSPIEL_<KEY>` (BUD-2, CONFIG-5). Bei zwei Instanzen läuft
  dieselbe `config.json` zweimal mit unterschiedlichen ENV-Overrides
  (Port, Data-Root, Secrets-Slots).
- `xbuddy-data/hoerspiel/<kind_id>/instance.json` — **Per-Kind-Instanz-
  Daten-Konfig** (kind-spezifische Werte, je Instanz eigene Datei).
  Heimat aller Werte, die zwischen Mia und Finn unterschiedlich sind:
  Serien-Name, Voice-Default, kognitive Stufe, Themen-Liste je Alter,
  Cover-Pfad-Override. Alle diese Werte sind **instanz-eigen** — es gibt
  für sie **keinen** plattformweiten Code-Default (für `serien_name` gilt
  OPEN-HSP-W/-X: leer statt eines konkreten Serien-Namens). Der `serien_name`
  im folgenden Beispiel ist daher ein **instanz-spezifischer Platzhalter**,
  kein Default. Beispiel:
  ```json
  {
    "kind_id": "mia",
    "serien_name": "<serien-name-dieser-instanz>",
    "default_voice": "shimmer",
    "stage": "toddler",
    "kognitiv_stufe": "5-6",
    "themen_je_alter": { "4": [ "Mut beim Probieren", "…" ] },
    "pause_absatz_sek": 0.55,
    "pause_titel_sek": 1.8,
    "playback_tempo": 1.0
  }
  ```
  Das `kind_id`-Feld ist Pflicht und Wahrheits-Quelle für die Instanz —
  Code und Eltern-Chat-Skill (HFE) lesen Alter, Themen und kognitiv-
  Stufe **nur** aus dieser Datei, nicht aus Modul-Konstanten.
- `hoerspiel/hoerspiel.json` — **Legacy Single-Tenant-Daten-Konfig**
  (vor RAT-17 die einzige Daten-Konfig). Wird in Welle B (#908+#909) auf
  `instance.json` migriert; nach Migration ist die Datei leer oder
  entfernt.

**Geheimnisse** (Anthropic-Key, Azure-Key) landen **nie** in einer Datei
im Repo (CONFIG-3, CLAUDE.md §8). Sie wohnen im **zentralen
Zugangsdaten-Speicher** (`specs/platform/zugangsdaten.md` ZD-1..ZD-5),
abgelegt unter ZD-2-konformen Slot-Namen:

- `hoerspiel-anthropic-api-key` — Anthropic-LLM (wenn `llm_provider=claude`)
- `hoerspiel-mistral-api-key` — Mistral-LLM (wenn `llm_provider=mistral`, HSP-27b)
- `hoerspiel-azure-openai-api-key` — Azure-OpenAI-TTS (immer Pflicht)

Der Hörspiel-Buddy liest sie über die geteilte ZD-Library
(`from tools.zugangsdaten import …`, ZD-5) — kein direkter Datei-Zugriff,
keine zweite Geheimnis-Schicht. Damit ist OPEN-HSP-M (Plattform-weite
Verwaltung dieser Schlüssel) **abgeschlossen mit #749 (2026-06-15)**:
die ZD-Library war bereits Plattform-Wahrheit, Hörspiel war nur der
einzige Außenseiter mit ENV-Brücke (`tools/sync_hoerspiel_env.py`).

**Migration auf ZD (zweistufige Deprecation analog ONB-5→ZD,
Vorbild #84 + #336):**

- **Schritt 1 (#749 Welle A):** Hörspiel liest read-both — zuerst ZD-Slot,
  bei leerem Wert Fallback auf die alte ENV-Variable (`HOERSPIEL_ANTHROPIC_KEY`,
  `HOERSPIEL_AZURE_OPENAI_KEY`). Schreibt ausschließlich ZD (lazy
  one-time-Migration der ENV-Werte in den Store). `tools/sync_hoerspiel_env.py`
  bleibt für Übergangs-Konsumenten, gibt aber Deprecation-Warnung aus.
- **Schritt 2 (#749 Welle B):** ENV-Fallback entfernt; Hörspiel liest
  ausschließlich ZD. `tools/sync_hoerspiel_env.py` ist gelöscht.
  `HOERSPIEL_ANTHROPIC_KEY`/`HOERSPIEL_AZURE_OPENAI_KEY` werden in HSP-27
  nicht mehr genannt; nur die ZD-Slots bleiben.

| Name | Default | Datei-Schlüssel | Quelle |
|---|---|---|---|
| `listen_host` | `127.0.0.1` | `listen_host` | n/a (PORT-3) |
| `listen_port` | `5053` (HSP-28) | `listen_port` | n/a (PORT-2) |
| `log_level` | `INFO` | `log_level` | n/a |
| `llm_provider` | `claude` | `llm_provider` | Eltern (Mini-App PATCH, HSP-34) |
| `llm_model` | `claude-opus-4-7` | `llm_model` | Eltern (Mini-App PATCH, HSP-34) |
| Default-Voice | `shimmer` | `default_voice` | Eltern (Mini-App PATCH, HSP-34) |
| Pause nach Absatz | `0.55` | `pause_absatz_sek` | Eltern (Mini-App PATCH, HSP-34) |
| Pause nach Titel | `1.8` | `pause_titel_sek` | Eltern (Mini-App PATCH, HSP-34) |
| Playback-Tempo | `1.0` | `playback_tempo` | Eltern (Mini-App PATCH, HSP-34) |
| Themen je Alter | siehe HSP-27a | `themen_je_alter` | Familie (handgepflegt, V1 Alter 4) |
| Serien-Name | (leer, kein Code-Default — OPEN-HSP-W/-X) | `serien_name` | Instanz (`instance.json`, HSP-45) |
| Anthropic-Key | (Pflicht wenn `llm_provider=claude`) | — | ZD-Slot `hoerspiel-anthropic-api-key` (ZD-5); Welle-A-Übergang: ENV `HOERSPIEL_ANTHROPIC_KEY` als Fallback |
| Mistral-Key | (Pflicht wenn `llm_provider=mistral`) | — | ZD-Slot `hoerspiel-mistral-api-key` (ZD-5); ENV `HOERSPIEL_MISTRAL_KEY` als Fallback |
| Azure-Endpoint | (Pflicht) | `azure_openai_endpoint` | ENV `HOERSPIEL_AZURE_OPENAI_ENDPOINT` (kein Geheimnis, bleibt ENV) |
| Azure-Deployment | (Pflicht) | `azure_openai_deployment` | ENV `HOERSPIEL_AZURE_OPENAI_DEPLOYMENT` (kein Geheimnis, bleibt ENV) |
| Azure-Key | (Pflicht) | — | ZD-Slot `hoerspiel-azure-openai-api-key` (ZD-5); Welle-A-Übergang: ENV `HOERSPIEL_AZURE_OPENAI_KEY` als Fallback |

Werte fehlen → Code-Default greift mit Warnung, der Prozess startet weiter
(CONFIG-4), **außer** bei Pflicht-Geheimnissen: fehlt der für den aktiven
Provider nötige Key, antwortet der Buddy auf API-Aufrufe, die ihn brauchen,
mit HTTP 503 + Klartext-Hinweis (kein stilles Scheitern).

V1-Provider-Whitelist: `VALID_PROVIDERS = ("claude", "mistral")`
(`hoerspiel/config.py`). Andere Werte lehnt der Loader mit `ConfigError`
ab, den `PATCH /config` in HTTP 422 übersetzt.

### HSP-27a — Themen-Liste je Alter (V1-Initial-Bestand)

`instance.json.themen_je_alter` ist eine Map `alter → string[]` mit
kuratierten Themen-Vorschlägen für die HFE-Diskussion (HFE-3). V1 für
Mia (Alter 4) gepflegt; Finns Themen-Liste wird im Zuge von #912 von
Nic per Hand gesetzt. Erweiterung auf andere Alter ist Familien-Tätigkeit
(Edit der JSON pro Instanz), keine Code-Pflicht.

**V1-Bestand für `themen_je_alter["4"]`** (8 pädagogisch breit gestreute
Themen für eine 4-jährige Hörerin; Anker für die HFE-Diskussion, nicht
finale Folgen-Titel):

1. **Mut beim Probieren** — etwas Neues wagen, von der Angst zur Lust.
2. **Streit vertragen** — Konflikt mit dem Freund / der Schwester
   verstehen und auflösen.
3. **Selbst anziehen / aufräumen** — Selbstständigkeit im Alltag.
4. **Warten lernen** — Geduld haben, etwas freuen, bis es soweit ist.
5. **Gefühle erkennen und benennen** — Wut, Trauer, Eifersucht, Freude.
6. **Jahreszeiten erleben** — Wetter, Tiere, Farben durch das Jahr.
7. **Bitte und Danke** — Höflichkeit als gelebte Wertschätzung.
8. **Neue Sachen essen** — Skepsis gegen unbekannte Lebensmittel
   überwinden.

Die Liste ist familien-spezifisch in `hoerspiel.json` und damit zur
Laufzeit ohne Code-Änderung anpassbar. Über die HFE-Diskussion (HFE-3
erweitert) nehmen die Eltern ein Thema als Anker und führen die
Konkretisierung selbst durch („Mut beim Probieren" → „mit Schmuggli am
Eichelnberg" → konkrete Folge).

### HSP-27b — Modell-Listen-Quelle je LLM-Anbieter

Jeder LLM-Provider-Adapter (`hoerspiel/providers/claude.py`,
`hoerspiel/providers/mistral.py`) führt eine Modul-Konstante:

```python
AVAILABLE_MODELS: list[tuple[str, str]] = [
    ("<model-id>", "<UI-Display-Label>"),
    ...
]
```

`GET /config` aggregiert diese Listen zur `modelle_je_anbieter`-Antwort
(HSP-17). `PATCH /config` validiert `llm_model` gegen die Liste des
gesetzten Providers und antwortet HTTP 422 bei unbekanntem Wert.

**V1-Initial-Bestand:**

| Provider | Modell-ID | UI-Display-Label |
|---|---|---|
| claude  | `claude-opus-4-7`      | Opus 4.7 (kreativ, langsamer, teurer) |
| claude  | `claude-sonnet-4-6`    | Sonnet 4.6 (ausgewogen) |
| claude  | `claude-haiku-4-5`     | Haiku 4.5 (schnell, kompakt, günstig) |
| mistral | `mistral-large-2411`   | Large 2.1 (Frontier, kreativ) |
| mistral | `mistral-medium-2508`  | Medium 3.1 (ausgewogen, V1-Default Mistral) |
| mistral | `mistral-small-2503`   | Small 3.1 (schnell, günstig) |

Erweiterung um weitere Modelle = Tupel an `AVAILABLE_MODELS` anhängen,
keine Spec-Änderung nötig. Petraltete Modell-IDs werden aus der Liste
entfernt; ein in `config.json` persistiertes `llm_model` außerhalb der
Liste wird beim Start mit Warnung auf den Provider-Default
zurückgesetzt (CONFIG-4).

*F5-Abend-Test-Hinweis:* Mistral-La-Plateforme-Snapshot-IDs ändern
sich gelegentlich. Beim ersten Live-Lauf mit jeder ID einen
Folgen-Build durchführen — schlägt die ID 404 oder 422, ist sie aus
`AVAILABLE_MODELS` zu entfernen (kein Spec-Update nötig).

---

## 10. Service & Registrierung

### HSP-28 — Eigener Service, fester Port (Mia-Instanz)
Die Mia-Instanz läuft als eigener Prozess `xbuddy-hoerspiel.service`
(SVC-1..4, `Restart=on-failure`, Logs an stdout/stderr) und bindet nur an
`127.0.0.1` (PORT-3). Port **5053** (PORT-2, `xbuddy-hoerspiel`,
eingetragen in `conventions/ports.md`).

### HSP-28a — Mehr-Instanz-Realität: Mia + Finn + Emil handverdrahtet (RAT-17, reaktiviert #1263)

**Reaktivierungs-Vermerk (#1263, RATIFIZIERT 2026-07-03).** Der in der
V1-Fassung dieser Klausel gesetzte Wiederaufnahme-Trigger („wenn ein
drittes Kind … hinzukommt, wird der Cut neu beraten") ist **gefeuert**:
Emil kommt als dritte, gleichrangige Hörspiel-Instanz (Erwachsener)
hinzu. Nic-Verdikt: der Cut wird **hörspiel-lokal** über eine
**Instanz-Liste mit Laufzeit-Iteration** (HSP-43) aufgelöst — **keine**
generische RAT-17-Registry. (ENTSCHEID-1263 → Nic-Verdikt → „hörspiel-
lokale Liste = nur Runtime-Iteration, keine RAT-17-Registry".)

Der Buddy läuft mit **drei expliziten Hörspiel-Instanzen** Mia, Finn und
Emil. Diese sind **handverdrahtet** — kein Port-Offset-Algorithmus,
keine generische „Buddy-mit-n-Instanzen"-Konvention. Jede Instanz ist ein
eigener Eintrag an den bekannten Stellen (`conventions/ports.md`,
`conventions/urls.md`, `deploy/nginx/xbuddy-origin.conf`,
`eltern-chat/config.py`, `hoerspiel/views.json`); die vollständige
Pflicht-Checkliste je neuer Instanz steht in HSP-44.

| Instanz | systemd-Unit                       | Port | Daten-Pfad                          | Origin-Pfade (URL-3a)                                          |
|---------|------------------------------------|------|-------------------------------------|----------------------------------------------------------------|
| Mia   | `xbuddy-hoerspiel.service`         | 5053 | `xbuddy-data/hoerspiel/mia/`      | `/display/hoerspiel/mia/<view>` · `/api/v1/hoerspiel/mia/<resource>` |
| Finn    | `xbuddy-hoerspiel-finn.service`    | 5055 | `xbuddy-data/hoerspiel/finn/`       | `/display/hoerspiel/finn/<view>` · `/api/v1/hoerspiel/finn/<resource>`   |
| Emil  | `xbuddy-hoerspiel-emil.service`  | 5056 | `xbuddy-data/hoerspiel/emil/`     | `/display/hoerspiel/emil/<view>` · `/api/v1/hoerspiel/emil/<resource>` |

*(Port-Reconcile #1263: Finn real 5055 laut `conventions/ports.md:27`, nicht 5054; Emil 5056 als nächster freier aus dem PORT-2-Block.)*

**RAT-17-Registry bleibt vertagt.** Die Wiederaufnahme in #1263 hat den
Cut **hörspiel-lokal** aufgelöst (Instanz-Liste als Runtime-Iteration,
HSP-43), **nicht** als plattformweite Registry-Konvention. Eine
generische „Buddy-Klasse mit n Instanzen pro Pi"-Konvention braucht
weiterhin zwei gebaute Buddy-Klassen mit n Instanzen (n=2-Regel);
Hörspiel bleibt die erste. Erst eine zweite solche Klasse löst die
Registry-Beratung aus.

**Service-Vorlage-Ablage (Realitäts-Vermerk):** beide Hörspiel-Service-
Vorlagen lagen am Repo-Root (`xbuddy-hoerspiel.service`,
`xbuddy-hoerspiel-finn.service`) und wichen damit von BUD-1a ab
(„Service-Vorlage neben dem Code"). Mit Ticket #1014 (SVC-2-Move)
wurden sie nach `hoerspiel/hoerspiel.service` und
`hoerspiel/hoerspiel-finn.service` verschoben — Pattern-Bruch aufgelöst.

### HSP-29 — Vorsynthese der Shared-Assets als Setup-Schritt
Vor der ersten Folge in einer Familien-Instanz müssen die vier Shared-
Assets (Intro/Outro je Voice) erzeugt werden. Trigger: ein einmaliger
Aufruf `POST /api/v1/hoerspiel/shared-assets/rebuild` (HSP-17) oder ein
Setup-Script, das denselben Endpoint ruft. Kosten: 4 × ~50 Zeichen × Azure
tts-hd ≈ 1 Cent, einmalig. Die Quell-Texte (`intro.txt`, `outro.txt`)
liegen im Daten-Bereich — sie werden beim Setup aus der Welt-Bible
übernommen (HSP-25a), wo Intro- und Outro-Reim wortgleich markiert
vorliegen.

**Wenn** ein Album-Bau angefordert wird (HSP-15) und die für die gewählte
Voice nötigen Shared-Assets fehlen, **dann** lehnt der Endpoint mit
HTTP 412 + Klartext-Hinweis ab — kein stilles Scheitern, kein
Auto-Rebuild beim Album-Bau (Trennung der Petrantwortung).

### HSP-30 — Registrierung in der Plattform
Der Slug `hoerspiel` wird im Origin-Routing (URL-14) registriert, damit
`/display/hoerspiel/<kind_id>/alben` und `/api/v1/hoerspiel/<kind_id>/*`
über die Origin erreichbar sind (URL-3a, RAT-17, #965). V1-Instanzen:
`/display/hoerspiel/mia/alben`, `/display/hoerspiel/finn/alben`.
Diese Verkabelung ist **Integration**, nicht App-Eigentum
— Gegenstand des arbeitstag-Track-Schnitts (F4/F5).

**Familien-Schnittstelle-Beitrag (APP-4):** der Eltern-Chat-Skill
`hoerspiel-folge-erzeugen` lebt unter `eltern-chat/skills/` und wird vom
Hörspiel-Buddy-Owner gepflegt. Eigene Plattform-Spec
`specs/platform/hoerspiel-folge-erzeugen.md`, ID-Präfix `HFE-`. Inhaltlich:
dünner Telegram-Adapter, der `/<kind_id>/folgen-vorschlag` und
`/<kind_id>/alben` ruft, ohne eigenen LLM-Zugriff.

### HSP-31 — Kachel-Icon der Display-View
Pro Instanz trägt `hoerspiel/views.json` einen eigenen Eintrag mit
`kind_id`-tragender `pfad`-Form (URL-3a, RAT-17, #965). V1-Einträge:
`slug: "alben-mia"` → `pfad: "/display/hoerspiel/mia/alben"` und
`slug: "alben-finn"` → `pfad: "/display/hoerspiel/finn/alben"`.
**#1263:** ein dritter Eintrag `slug: "alben-emil"` →
`pfad: "/display/hoerspiel/emil/alben"` kommt hinzu (HSP-44-Checkliste
Punkt 4). Sein `zielgruppe`-Feld ist **deskriptiv** — es blendet die
Instanz nicht aus einer Ansicht aus (HSP-46).
Jeder Eintrag trägt `icons[]` mit dem Pfad **`arasaac/5915.png`**
(Kopfhörer-Piktogramm) relativ zur Icon-Basis
`/display/_shared/icons/` (BUD-4, PANEL-3, ICONS-5). Das Kachel-Icon ist
**kein** app-eigenes Asset (URL-13) und **kein** buddy-eigener
ARASAAC-Bezug. Die ARASAAC-ID 5915 ist im Werft-F3-Lauf 2026-06-12 als
Wortmarke-Pikto ratifiziert (passt zum Hörspiel-Begriff: Kopfhörer-
affordance ist für ein vier- oder fünfjähriges Kind sofort lesbar).

---

## 11. Tests

### HSP-32 — Automatisierte Tests je Anforderung (ohne Netz)
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test, ohne
Netz (LLM- und TTS-Aufrufe werden durch kontrollierte Doppelungen ersetzt,
analog WETTER-24). Mindest-Abdeckung:

- HSP-2 (Album-Kachel-Element je freigegebenem Album; Resume-Hinweis bei
  Resume-State)
- HSP-6/9 (Track-Reihenfolge in Position-Sortierung; erster `intro`,
  letzter `outro`)
- HSP-7/14 (Bündel-Schnitt-Funktion: 5×200-Wörter-Absätze → 2 Bündel; 2
  × 600-Wörter-Absätze → 2 Bündel; Schnitte fallen auf Absatzgrenzen)
- HSP-8 (Album referenziert Shared-Asset-Pfade je gewählter Voice; intro/
  outro nie pro Folge re-synthetisiert)
- HSP-15 (Album-Bau ist atomar; Manifest wird Temp+Rename geschrieben;
  Historie wird genau einmal je erfolgreichem Bau ergänzt; bei
  TTS-Fehler bleibt Historie unverändert)
- HSP-16 (Folgen-Historie wird vom Buddy fortgeschrieben)
- HSP-17 (alle API-Endpoints antworten erwartete JSON-Form; `POST /alben`
  ist idempotent über identischen Inhalt + Voice)
- HSP-19/20 (Tap-Sequenz: Kachel ohne Resume → Track 1 Sek 0; Kachel mit
  Resume → Resume-Track Sek 0)
- HSP-21 (Next/Prev-Verhalten; Doppel-Prev innerhalb 3 s → vorheriger
  Track)
- HSP-23/24 (Resume-Marke wird auf Track-Anfang gerundet; Test nutzt
  injizierten `now`)
- HSP-27 (fehlender Anthropic-Key bei `llm_provider=claude` → HTTP 503
  auf `/folgen-vorschlag`; `PATCH /config` mit `llm_provider=mistral`
  oder unbekanntem Provider → HTTP 422)
- HSP-29 (Album-Bau ohne vorhandene Shared-Assets für die gewählte Voice
  → HTTP 412; Auto-Rebuild findet **nicht** statt)

Läufe gegen echte Engines (Azure tts-hd, Anthropic, Mistral) sind opt-in
und nicht Teil der V1-Standard-Test-Suite.

---

## 12. Eltern-Mini-App (HSP-33..HSP-40) — SUPERSEDED durch Abschnitt 15

> **SUPERSEDED (Werft 2026-07-03, HSP-53).** Diese Telegram-Eltern-Mini-App
> (Tab-Form, `tma`-Auth) wird durch die **Hörspiel-Player-PWA** (Abschnitt 15,
> HSP-47..55, Cookie-Auth) abgelöst. HSP-33–40 bleiben als historischer Stand
> dokumentiert, sind aber **nicht** mehr die Soll-Form. Neue Arbeit gegen
> Abschnitt 15. Wiederverwendete Mechanik (Multi-Track-Player HSP-35, Resume
> HSP-36, Streaming HSP-37) lebt inhaltlich weiter, nur nicht mehr in der
> Telegram-Tab-Hülle.
>
> V1 nach Werft-Lauf 2026-06-15 (Refs #848). Vorbild für Wohnort und
> Auslieferung: Routine-Anpassen-Mini-App (#728, `<funnel>/seiten/routine/anpassen`).
> Auth-Pattern: `Authorization: tma <initData>`-Header analog #708.

### HSP-33 — Wohnort, Auslieferung, Auth, Tab-Form

Der Hörspiel-Buddy stellt eine Eltern-Mini-App bereit unter
`<funnel-domain>/seiten/hoerspiel/<kind_id>/eltern` (kind_id-tragend
nach RAT-17 / URL-3a, V1: `mia` oder `finn`), **gehostet vom seiten-
Service** (Pattern wie Routine-Anpassen). Eine **gemeinsame Code-
Basis** pro Instanz — die Mini-App liest die `<kind_id>` aus
`window.location.pathname` und reicht sie an alle API-Calls weiter
(`/api/v1/hoerspiel/<kind_id>/config`, `/api/v1/hoerspiel/<kind_id>/alben`,
…). **Keine** Face-Pille im Mini-App-Header, **kein** App-internes
Toggle (siehe HSP-3a-Begründung). Wohnort der View-Assets:

- `hoerspiel/templates/eltern.html`
- `hoerspiel/static/eltern.css`
- `hoerspiel/static/eltern.js`

**Bot-Menü-Buttons (Telegram-WebApp).** Im Eltern-Chat-Bot trägt das
persistente Menü pro Hörspiel-Instanz einen eigenen Web-App-Button mit
der jeweiligen kind-spezifischen URL. V1: zwei Einträge
(`📚 Hörspiel Mia` → `<funnel>/seiten/hoerspiel/mia/eltern`,
`📚 Hörspiel Finn` → `<funnel>/seiten/hoerspiel/finn/eltern`).
Konfiguration in `eltern-chat/config.py` als Liste; bei einem dritten
Kind wird ein weiterer Eintrag handverdrahtet ergänzt (Option A aus
RAT-17, keine Registry). Bot-Setup ruft die Telegram-API
`setChatMenuButton` einmalig je Eintrag — kein Per-Request-Roundtrip.

**Auth** nach `conventions/mini-app-design.md` MAD-7 und #708-Pattern:
alle HTML- und API-Routes prüfen den `Authorization: tma <initData>`-
Header über die geteilte `eltern-chat/init_data.py`-Library
(HMAC-SHA256-Validierung, Bot-Token via EnvironmentFile). Ungültig oder
fehlend → HTTP 401, kein Render, kein Daten-Leak. Telegram-User-ID aus
initData wird mit Familien-Registry (FAM-7/8) abgeglichen — nur
Familienmitglieder lesen und schreiben.

**Tab-Form:** zwei Tabs als Top-Tabs (Werft-Lauf Gate B 2026-06-15
Variante A) — zwei volle-Breite Tab-Buttons unter dem Buddy-Titel,
aktiver Tab unterstrichen. Das ist V1 das **erste Vorkommen** eines
Tab-Patterns in xbuddy-Mini-Apps (n=1); eine MAD-Konventions-Klausel
für Tabs wird bei zweitem Konsumenten via `/berater-runde` ratifiziert.

**Tab-Deeplink — URL-Hash-Steuerung (Werft-Folge 2026-06-15, Refs #848):**

Die Mini-App liest beim Laden das URL-Hash-Fragment der Funnel-URL:

- `<funnel>/seiten/hoerspiel/<kind_id>/eltern#einstellungen` → Tab
  „Einstellungen" aktiv (Default-Verhalten konsistent zum Tab-Default
  ohne Hash).
- `<funnel>/seiten/hoerspiel/<kind_id>/eltern#folgen` → Tab „Folgen"
  aktiv.
- Kein Hash oder unbekannter Hash → Default-Tab „Einstellungen".

`hoerspiel/static/eltern.js` registriert zusätzlich einen
`hashchange`-Listener, der den aktiven Tab live umschaltet, ohne die
Seite neu zu laden — Tap auf eine Inline-Link-URL aus dem Eltern-Chat
(z. B. `web_app`-Button mit anderem Hash) öffnet so den korrekten Tab
ohne Reload und ohne erneute `initData`-Validierung. Das Hash-Fragment
ist reiner Client-State (Browser sendet es nicht an den Server), die
Server-Routes (`GET /config`, `GET /alben`, `PATCH /config`, …) sind
hash-unabhängig.

n=1 für URL-Hash-Tab-Navigation in xbuddy-Mini-Apps — eine
MAD-Konventions-Klausel für Tab-Deeplinks wird bei zweitem Konsumenten
via `/berater-runde` ratifiziert (gemeinsam mit der Tab-Form-Klausel
oben). Heimat der Implementation: `hoerspiel/static/eltern.js`.

Konsumiert von `specs/platform/hoerspiel-oeffnen.md` HOE-5 (Skill setzt
den Hash passend zum Tab-Hint).

*Test-Implikation:* JS-Unit-Test (JSDOM, z. B. `hoerspiel/tests/test_eltern_js.py` oder
`hoerspiel/tests/eltern.test.js`) prüft: (1) `window.location.hash = "#folgen"` zur
Ladezeit setzt den Tab-Knopf für »Folgen« sichtbar in den Aktiv-Zustand (unterstrichen /
hervorgehobenes Element); (2) `hashchange`-Event mit anderem Hash-Wert schaltet den
aktiven Tab live um — der Listener löst dabei weder einen `fetch`-Call auf
`/api/v1/hoerspiel/*` noch ein `window.location.reload()` aus. Bind-Punkt für
Implementierungs-Track.

- **Reiter 1 „Einstellungen"** (HSP-34, Default beim Laden / bei Hash
  `#einstellungen`)
- **Reiter 2 „Folgen"** (HSP-35, bei Hash `#folgen`)

### HSP-34 — Reiter „Einstellungen"

Lädt die aktiven Werte aus `GET /config` (HSP-17). Fünf Steuer-Elemente
in einer vertikalen Karten-Liste (parent stage, MAD-andocked an
`display/_shared/design/tokens.css`):

| Element | Form | Wert-Range / Optionen | API-Feld |
|---|---|---|---|
| Playback-Tempo | Slider | 0.7–1.3 in 0.05-Schritten | `playback_tempo` |
| Pause nach Absatz | Slider | 0.0–2.0 s in 0.05-Schritten | `pause_absatz_sek` |
| Pause nach Titel | Slider | 0.5–3.0 s in 0.1-Schritten | `pause_titel_sek` |
| Stimme | 2-Kachel-Wahl | aus `voices_verfuegbar` | `default_voice` |
| LLM (Anbieter + Modell) | zwei abhängige Dropdowns | Anbieter aus `provider_verfuegbar`; Modell aus `modelle_je_anbieter[<anbieter>]` | `llm_provider` + `llm_model` |

**Hinweis-Block** über dem Speichern-Knopf:

> Pausen, Stimme und Anbieter+Modell wirken bei der **nächsten Folge** —
> Playback-Tempo gilt sofort, auch für bestehende Alben.

**Speichern-Knopf** unten sticky. Tap löst einen `PATCH /config` mit
**allen geänderten Feldern** aus. Bei Erfolg erscheint ein **Toast**
(MAD-Toast-Pattern):

> ✓ Gespeichert — Pausen, Stimme, Anbieter und Modell wirken ab der
> nächsten Folge.

(Werft-Lauf 2026-06-15 Nic-Klärung: ein gemeinsamer Toast, der die
„Wirkung-ab-nächster-Folge"-Information explizit trägt. Playback-
Tempo wirkt zwar sofort, der Toast benennt die verzögerte Mehrheit.)

Bei HTTP 422 vom Server zeigt die Mini-App den vom Server gelieferten
`fehler`-Klartext im Toast, in roter Tönung.

**Abhängiges Dropdown:** Wechsel des Anbieter-Dropdowns füllt das
Modell-Dropdown aus `modelle_je_anbieter[<neuer-anbieter>]` neu und
setzt es auf den ersten Eintrag (Provider-Default).

**Audio-Ausgabe-Schalter — entfällt (Audio-Ziel-Schalter SUPERSEDED 2026-07-27).**
Die sechste Einstellungs-Karten-Zeile („Audio-Ausgabe", 2-Kachel-Wahl
`display`/`panel`, Feld `audio_ziel`) und ihr Mia+Finn-UI-Kollaps entfallen mit
dem Ein-App-Default — Audio läuft immer lokal am App-Gerät (§13 SUPERSEDED).
Code-/UI-Rückbau über #1471.

### HSP-35 — Reiter „Folgen" (aggregierte Liste + Multi-Track-Player)

**#973 (2026-06-16) · RAT-17 Option A handverdrahtet. Wiederaufnahme-
Trigger „dritte Instanz" gefeuert (#1263, RATIFIZIERT 2026-07-03) →
Aggregation iteriert jetzt über die Instanz-Liste (HSP-43), nicht über
eine 2-Element-Konstante (`KIND_IDS_V1`):** Der Folgen-Tab lädt parallel
die Folgen **aller Instanzen** aus der Instanz-Liste (V1: Mia, Finn,
Emil — gleichrangig, kein `zielgruppe`-Filter, HSP-46), mergt sie und
sortiert nach `erstellt-am` desc (gleicher Datumswert: `nummer` desc als
Fallback).
Jede Folge trägt ihre `kind_id` im JS-State — Player öffnet
`/api/v1/hoerspiel/<folge.kind_id>/alben/<id>/manifest`, **nicht**
URL-KIND_ID. Settings-Tab (HSP-34) bleibt instance-getrennt und
verwendet weiterhin KIND_ID aus dem URL-Pfad.

Rendert als vertikale Kachel-Liste (MAD-2 Card-Pattern):

```
[cover 56×56] [Folge N · Titel]   [kind-avatar 28×28] [▶ ab Track X | (leer)]
                voice · datum
```

- **Kind-Avatar** links neben dem Resume-Badge: `<img
  src="/api/v1/familie/foto/<folge.kind_id>">` (FAM-8) — selber
  Mechanismus wie Face-Pille in `alben.html` (HSP-3a, T911 Vorbild).
  Fehler beim Laden der Avatar-URL → Bild versteckt, kein Abbruch.

Tap auf eine Kachel → öffnet den **Inline-Player** unten im selben
Reiter (kein Modal). Der Player nutzt das **Multi-Track-Modell** aus
HSP-6 (Intro · Inhalts-Tracks · Outro):

- HTML5 `<audio>`-Element pro **aktuellem Track**
- Audio-URL aus `audio-asset` im Manifest, ausgeliefert über
  `GET /api/v1/hoerspiel/<kind_id>/alben/<id>/audio/<track>.mp3` (HSP-37,
  Range-Requests Pflicht)
- `<audio>.playbackRate` aus aktivem `playback_tempo` (HSP-34); Wechsel
  des Tempo-Sliders aktualisiert den laufenden Player live
- Anzeige: Cover, Folgen-Titel, **Track-Anzeige** `Track X/Y · <Label>`
  (Label = "Intro" / "Outro" / Inhalts-Titel) inkl. Track-Dauer
- **Track-Liste** unter dem Player klappbar (`<details>`), aktiver
  Track hervorgehoben. Tap auf einen Track-Listen-Eintrag → springt
  direkt dorthin und startet die Wiedergabe
- **Track-Navigation:** `⏮ Track` / `Track ⏭` als eigene Buttons,
  disabled am ersten/letzten Track
- **Skip:** `−15 s` / `+15 s` getrennt von Track-Navigation
- **Auto-Play-Folge:** am Track-Ende lädt der Player automatisch den
  nächsten Track und startet die Wiedergabe; am Album-Ende (letzter
  Track beendet) wird der Wake-Lock freigegeben (HSP-39)
- **Wake-Lock**: bei Play-Tap `navigator.wakeLock.request('screen')`;
  bei manueller Pause + Verlassen-der-View + Album-Ende Release.
  Wake-Lock-Fehler (`'wakeLock' not in navigator`, Berechtigung
  verweigert) → Toast „Bildschirm bleibt nicht wach — Tablet manuell
  entsperren oder Telefon nicht weglegen", kein Abbruch der
  Wiedergabe

**Resume-Stand-Tap-Verhalten** (HSP-36): wenn ein Album einen Resume-
Stand hat, startet der Tap auf die Kachel **direkt beim Resume-Track**
(nicht beim Intro). Ohne Resume-Stand startet die Wiedergabe beim
Intro-Track. Resume-Read/Write-Calls nutzen `folge.kind_id` (nicht
URL-KIND_ID).

### HSP-36 — Resume-Stand auf Mini-App-Player erweitert

HSP-23 hält die Resume-Marke pro Album auf Track-Anfang gerundet
(existing). Der Mini-App-Player schreibt denselben Resume-Stand wie
die Kinder-View: bei jedem Track-Wechsel und bei jeder Pause-Tap-Aktion
ruft die Mini-App `PUT /resume` mit Album-ID + Track-Position (HSP-17).

**Konkurrenz-Schreiben** (Mini-App + Kinder-View gleichzeitig) ist
erlaubt — Last-Write-Wins auf Track-Anfang (Track-Position-Granularität,
nicht Sekunden-Position; ein Race auf derselben Position ist no-op).

**GET ohne vorhandenen Stand → 200 mit Default-Body, kein 404.**
Das Frontend fragt präventiv für jede Folge beim Settings-Open (`eltern.js`);
8x 404-Bursts sind unnötig laut und deuten fälschlich auf Fehler hin.
Antwort-Form: `{"album": "<id>", "track": 0, "status": "neu"}`. Der
Konsument erkennt an `status == "neu"` (oder `track == 0` ohne
persistierten Wert), dass noch kein Stand gesetzt wurde. GET ohne
`album`-Parameter liefert weiter 400.

### HSP-37 — Track-MP3-Streaming-Endpoint

`GET /api/v1/hoerspiel/<kind_id>/alben/<id>/audio/<track>.mp3` liefert die rohen
MP3-Bytes des Tracks:

- HTTP Range-Request-Support (`Range: bytes=N-M` Request → Status 206
  Partial Content + `Content-Range` Response)
- Auth-Check wie alle `/api/v1/hoerspiel/*` (HSP-33) **vor** der
  Range-Logik
- `Content-Type: audio/mpeg`
- `Cache-Control: private, max-age=86400` (Album-MP3s sind immutable
  je `album-id`, ein Tag Browser-Cache OK)

**Drift-Bemerkung zu HSP-18:** HSP-18 verbietet „direkter Datei-
Zugriff durch andere Apps — ausschließlich über HTTP-API". Die
Mini-App fällt **unter diese Regel** — sie greift NICHT auf Dateien
unter `/display/hoerspiel/data/...` zu, sondern ausschließlich über
diesen Audio-Endpoint (API-Naht, APP-3).

### HSP-38 — Themen-Liste-Endpoint (kind_id-tragend, RAT-17)

`GET /api/v1/hoerspiel/<kind_id>/themen` liefert die kuratierte
Themen-Liste der Instanz. Das Alter zieht der Buddy implizit aus seiner
`instance.json` (HSP-27, Feld `themen_je_alter` als Map mit dem
instance-eigenen Alters-Schlüssel). Der Aufruf-Pfad enthält **kein**
Alter — RAT-17 Entscheidung „Single Source of Truth pro Instanz" (vgl.
E-HFE-3): Alter lebt nur in instance.json, nicht doppelt im Aufruf.

```
200 {"kind_id": "mia", "name": "Mia", "alter": 4,
     "themen": ["Mut beim Probieren", "Streit vertragen", …]}
404 wenn kind_id unbekannt (kein hoerspiel-Pfad für diesen Wert)
422 wenn das Alter der Instanz nicht in
    instance.json.themen_je_alter gepflegt ist
```

Antwort-Felder: `kind_id` und `name` stammen aus `familie.json` (FK
über `instance.json.kind_id`), `alter` aus der instance.json-Themen-
Map-Schlüssel-Wahl (V1 ein Schlüssel je Instanz, z. B. „4" für Mia).
Die `name`-Mitlieferung erlaubt dem HFE-Skill personalisierte Tool-
Result-Texte („Vorschläge für \<Name> …", HFE-3).

Konsumenten V1: nur der HFE-Skill ruft diesen Endpoint (HFE-3
erweitert). Die Mini-App selbst zeigt **keine** Themen-Liste — die
Themen-Diskussion lebt im Eltern-Chat.

**Migration (Welle B, im Zuge von #910):** der alte Pfad
`GET /api/v1/hoerspiel/themen?alter=<n>` (Single-Tenant-Form vor
RAT-17) wird ersatzlos entfernt; HFE-3 + Tests gehen mit demselben PR
auf die neue Form. Kein Übergangs-Doppelpfad — die alte Route hat
genau einen Konsumenten (HFE-Skill, monorepo) und kann atomar gedreht
werden.

### HSP-39 — Auth-Klausel (Pflicht-Verhalten)

Eingehende Aufrufe:

1. HTML-Route `/seiten/hoerspiel/eltern` ohne `Authorization`-Header
   oder mit ungültiger initData-Signatur → HTTP 401 + Klartext
   „Bitte über den Familien-Bot öffnen" (kein Render).
2. API-Route `/api/v1/hoerspiel/*` ohne gültigen Header → HTTP 401.
3. Header gültig, aber Telegram-User-ID nicht in Familien-Registry
   (FAM-7/8) → HTTP 403 + Klartext „Nicht Familienmitglied".
4. Header gültig + Familienmitglied → Request läuft.

Bot-Token-Quelle: `eltern-chat/.env` (EC-Token-Sharing-Pattern), via
EnvironmentFile in den `xbuddy-hoerspiel.service`-Prozess gegeben.

### HSP-40 — Tests Eltern-Mini-App (Mock-Pflicht)

Pflicht-Tests (ohne Netz, ohne Telegram, ohne Mistral-/Anthropic-API):

- **HSP-33-Auth** — 401 ohne `Authorization`-Header; 401 mit
  manipulierter Signatur (HMAC schlägt fehl); 200 mit gültiger Signatur
  für Familienmitglied; 403 für validen aber Nicht-Familien-User.
- **HSP-34-`GET /config`** — Response trägt alle Pflicht-Felder
  inkl. `modelle_je_anbieter` mit beiden Providern.
- **HSP-34-`PATCH /config`** — Teilmenge der Felder ändert genau diese;
  Range-Verletzung (`playback_tempo=2.0`) → 422; unbekanntes
  `llm_model` → 422; `llm_provider=mistral` ohne `hoerspiel-mistral-api-key`
  → 422.
- **HSP-35/37-Audio** — Range-Request `bytes=0-1023` liefert 206 +
  passende ersten 1024 Bytes; ohne Range liefert 200 + voller
  Inhalt; Auth-Check vor Range-Logik (401 trumpft 206).
- **HSP-36-Resume** — Mini-App `PUT /resume` und Kinder-View-Update
  landen im selben Modell (gleiche Track-Position lesbar nach
  beiden Schreiben); ein zweites `PUT /resume` für dasselbe Album +
  Track-Position ist no-op.
- **HSP-38-Themen** — `GET /api/v1/hoerspiel/<kind_id>/themen` mit
  gepflegter `instance.json` liefert die 8 V1-Themen aus `themen_je_alter`
  (HSP-27a); unbekannter `kind_id` liefert **404**; ungepflegtes Alter
  (kein Eintrag in `themen_je_alter`) liefert **422**.
- **HSP-40-Themen-URL** — kein `?alter=`-Query-Parameter; `kind_id` trägt
  die Instanz-Identität als URL-Segment (`/api/v1/hoerspiel/<kind_id>/themen`,
  RAT-17 URL-3a-konform, #910).
- **HSP-35-Aggregation** — Parallele Lade-Pfade über alle V1-kind_ids
  aggregieren; Merge-Sort `erstellt-am` desc; jeder Listen-Eintrag trägt
  folge-eigene `kind_id`; Player-Klick öffnet `folge.kind_id`-Manifest
  (nicht URL-`kind_id`); einseitiger 404 produziert teilweise Liste +
  Warn-Banner pro fehlgeschlagener kind_id (`Promise.allSettled`, #975).
- **Mistral-Adapter** (`hoerspiel/providers/mistral.py`) gegen Mock-API:
  erfolgreiche Folgen-Erzeugung; HTTP-Fehler → `LLMError`; fehlender
  Key → `ConfigError`. Tests für jedes der drei V1-Modelle (`mistral-large-2411`,
  `mistral-medium-2508`, `mistral-small-2503`) — auch mit Mock,
  damit `AVAILABLE_MODELS`-Konstante nicht stillschweigend abweicht.

**Echter Smoke-Test** gegen Mistral-La-Plateforme / Anthropic läuft im
**F5-Abend-Test** (Nic-Tap in der Mini-App auf jeden Anbieter + jedes
Modell, mindestens einmal Folgen-Build pro Provider). Eine
Mistral-Modell-ID, die 404/422 antwortet, wird aus `AVAILABLE_MODELS`
entfernt (Konstante anpassen, kein Spec-Update — HSP-27b).

---

## 13. Audio-Ziel-Routing — SUPERSEDED (2026-07-27, Ein-App-Default)

**Das `audio_ziel`-Routing (HSP-41) und `/play-extern` (HSP-42) sind aufgehoben.**
Nic-Setzung 2026-07-27 (Option B): Der neue Default ist EINE App (Heim-Shell). Das
Gerät, auf dem die App läuft, ist die Audio-Ausgabe — es gibt keine Wiedergabe auf
einem *anderen* Gerät mehr. Die Zwei-Werte-Weiche `audio_ziel = "display" | "panel"`
und der Panel-Push (`POST /play-extern`, HSP-42) entfallen ersatzlos; Audio läuft
immer **lokal am App-Gerät**. `/play-extern` ist aus `main.py` entfernt (kein
Nicht-Test-Caller).

**`/audio-stream` (SSE) bleibt als PANEL-13-Infrastruktur erhalten — Producer ruht.**
`controller/app-panel/app.js:819-966` öffnet pro HSP-Instanz eine EventSource auf
`/api/v1/hoerspiel/<kind_id>/audio-stream` (Infrastruktur für Silent-Audio-Prime).
Dieser Endpoint ist nicht Teil der aufgehobenen `audio_ziel`-Weiche und wird daher
durch Option B nicht berührt. **Jedoch ist der einzige `audio_play`-Producer
(`/play-extern`) mit HSP-42 entfernt worden. `_audio_broadcast` ist aktuell
aufruferlos — der Stream sendet nur Heartbeats, keine `audio_play`-Events.**
Ein künftiger Trigger (#1471-Rückbau / HSP-44) klärt, ob und welcher neue Producer
`_audio_broadcast` speist.

Damit entfallen auch die zwei Folge-Klauseln zu HSP-41 (Audio-Ziel-Weiche in
`alben.js` und der Audio-Ziel-Schalter im Einstellungen-Reiter) — beide sind an
ihren Stellen als SUPERSEDED markiert. Der Code-/UI-Rückbau für `audio_ziel` und
`play-extern` erfolgt über #1471.

(Aufhebung der RATIFIZIERUNG 2026-06-17 „audio-output-routing" durch Nic-Setzung
2026-07-27 „Ein-App-Default, App-Gerät = Ausgabe".)

## 14. Mehr-Instanz-Modell (n≥3) — #1263

> RATIFIZIERT 2026-07-03 (#1263, ENTSCHEID-1263). Reaktiviert den in
> HSP-28a gesetzten Wiederaufnahme-Trigger: die dritte Instanz (Emil,
> Erwachsener) ist da. Der Cut wird **hörspiel-lokal** aufgelöst
> (Instanz-Liste als Runtime-Iteration), **nicht** als plattformweite
> RAT-17-Registry.

### HSP-43 — Hörspiel-lokale Instanz-Liste (Runtime-Iteration) mit Scope-Grenze
Der Buddy führt eine **hörspiel-lokale Instanz-Liste** der verdrahteten
Instanzen (V1: `mia`, `finn`, `emil`). Sie ersetzt die bisher
binären „Mia-oder-Finn"-Annahmen durch eine **Iteration über die
Liste** — überall dort, wo Code heute genau zwei Instanzen voraussetzt:
Partner-/„andere Instanz"-Bezug (Face-Pille HSP-3a), Folgen-Aggregation
(HSP-35 `KIND_IDS_V1`), HFE-Klassifikator-`enum` (`kind_id`-Auswahl),
Audio-Ziel-Kollaps-Keys (HSP-34).

**Wenn** eine View oder ein Skill „die anderen Instanzen" oder „alle
Instanzen" braucht, **dann** liest er sie aus der Instanz-Liste, nicht
aus einer 2-Element-Konstante.

**Scope-Grenze (verbindlich — der Guard gegen die RAT-17-Registry durch
die Hintertür).** Die Liste trägt **ausschließlich** Identität und
UI-/Runtime-Iterations-Felder bereits verdrahteter Instanzen
(`kind_id`, Anzeigename/Foto-FK über `familie.json`, `zielgruppe` als
**deskriptives** Feld nach HSP-46). Sie trägt **keine** Betriebs-
Andockpunkte: **kein** `port`, **kein** `origin`/`api_path`/
`display_path`, **kein** `service`, **kein** Datei-Pfad. Diese bleiben
in ihren Homes (`conventions/ports.md`, `conventions/urls.md`,
`deploy/nginx/xbuddy-origin.conf`, systemd-Unit). **Sobald** die Liste
eines dieser Felder bekäme oder nginx/eltern-chat daraus generiert
würden, **ist** sie die vertagte RAT-17-Registry — das ist der
Kill-/Verboten-Zustand dieser Klausel. RAT-17 bleibt vertagt bis zur
zweiten n-Instanz-Buddy-Klasse (n=2-Regel, HSP-28a).

(ENTSCHEID-1263 → F1 „hörspiel-lokale Instanz-Liste" + „Scope-Grenze" →
„nur UI-/Runtime-Iteration, keine Ports/Origins/Services".)

### HSP-44 — Provisioning-Checkliste je neuer Instanz (Pflicht-Cut)
Eine neue Hörspiel-Instanz ist **erst dann öffentlich erreichbar und
vollständig**, wenn **alle** folgenden Andockpunkte handverdrahtet
gesetzt sind (RAT-17 Option A, kein Generator). Die Liste ist die
Definition-of-Done für „Instanz X existiert":

1. **Port** — Eintrag in `conventions/ports.md` (nächster freier aus
   PORT-2-Block).
2. **Origin-Routing / nginx** — URL-14-Registrierung inkl. der
   **Audio-SSE-Exact-Location** mit `proxy_buffering off` für
   `/api/v1/hoerspiel/<kind_id>/audio-stream` (PANEL-13; Endpoint + Consumer-Infrastruktur erhalten — audio_ziel-Routing §13 SUPERSEDED, /audio-stream nicht; `audio_play`-Producer ruht bis #1471/HSP-44).
3. **systemd-Service** — eigene Unit `xbuddy-hoerspiel-<kind_id>.service`
   (SVC-1..4), Service-Vorlage neben dem Code (BUD-1a), inkl.
   ZD-Store-Pfad-Drop-In pro Service.
4. **views.json-Eintrag** — eigener Eintrag mit `kind_id`-tragender
   `pfad`-Form (HSP-31).
5. **eltern-chat-Verdrahtung** — Origin/Client-Map und Bot-Menü-Button
   (HSP-33), plus HFE-Tool-Schema-`kind_id`-Wert (die `enum`-Liste zieht
   aus der Instanz-Liste, HSP-43).
6. **`hoerspiel_oeffnen`-Launcher** — Instanz ist über den Launcher-Skill
   erreichbar (`specs/platform/hoerspiel-oeffnen.md`), nicht hart auf
   Mia.
7. **Daten-Bereich** — `xbuddy-data/hoerspiel/<kind_id>/instance.json`
   (+ bible, Shared-Assets) nach HSP-25/HSP-27.
8. **Tests** — instanz-tragende Tests fixieren nicht `mia`/`finn`
   literal, sondern iterieren über die Instanz-Liste (HSP-43).

(ENTSCHEID-1263 → F1 „der Cut ist GRÖSSER als 3 Stellen [BRICHT]" →
Pflicht-Checkliste.)

### HSP-45 — Erwachsenen-Instanz allein über Daten (kein App-UI-Alters-Achse)
Der Zielgruppen-Ton einer Instanz (kindlich für Mia/Finn, erwachsen
für Emil) lebt **ausschließlich in den Instanz-Daten**, nicht in einer
App-UI-Achse und nicht in Modul-Konstanten. Träger:

- **instance.json (HSP-27)** trägt die zielgruppen-tragenden Felder
  `zielgruppe` (z. B. `"kind"` | `"erwachsen"`), `ton`/`perspektive` und
  das instanz-eigene `alter` (bei Emil ein Erwachsenen-Wert). Diese
  Felder sind Daten, je Instanz gepflegt.
- **Story-Prompt parametrisiert (HSP-12).** Das Prompt-Template
  `prompts/geschichtenbuddy.md` enthält **keinen** hartkodierten
  Instanz-Namen, kein festes Alter, keinen festen Serien-Namen mehr.
  Name, Alter, Perspektive/Ton und Serien-Name werden als
  Eingabe-Variablen der aktiven Instanz durchgereicht.

**Name-Drift-Fix (Pflicht-Vorbedingung, behebt bestehenden Bug).** Heute
erreicht der Instanz-Name den Story-Prompt nicht: `geschichtenbuddy.md`
ist auf „Mia (4 Jahre)" hartkodiert, sodass die Finn-Instanz aktuell
im Mia-Rahmen erzählt. **Wenn** eine Folge erzeugt wird, **dann** trägt
der an den LLM gereichte Prompt Name/Alter/Perspektive der **aufrufenden
Instanz** (`kind_id`). Ohne diesen Fix erzählt auch Emil „Mia" — der
Fix ist Vorbedingung der dritten Instanz.

**Validierung (Zwei-Wege-Tür, das Tun ist das Experiment).** Je eine
Mia- und eine Emil-Folge erzeugen und lesen. **Kill-Kriterium:**
passt Ton/Länge/Sicherheitsrahmen bei einer Zielgruppe mit **einer**
gemeinsamen Prompt-Schale nicht, dann **getrennte Prompt-Vorlagen je
Zielgruppe** (weiter Daten-getrieben, weiterhin keine App-Achse).

*Test-Implikation:* eine für `kind_id=emil` erzeugte Folge nennt an
keiner Stelle den Namen einer anderen Instanz („Mia"/„Finn"); der
Prompt-Bau-Pfad ist ohne Netz gegen einen Mock-LLM testbar (Assertion
auf die durchgereichten Variablen).

(ENTSCHEID-1263 → Vorlauf „Name-Drift-Fix" + F3 „Erwachsener über Daten" +
Prompt-Frage „zielgruppe/ton-Felder, Experiment Pflicht".)

**OPEN-HSP-W (T1336, 2026-07-07) — DEFAULT_SERIEN_RAHMEN neutralisiert.**
Der Code-Default in `hoerspiel/llm_service.py` war Mia-spezifisch
(`"Stigi, Malini & Vögelchen …"`) — was für `finn` und jede weitere Instanz
ohne gesetzte `instance.json` zu einem Mia-Serien-Leak führte.
*Auflösung:* `DEFAULT_SERIEN_RAHMEN = ""` (leer); `_build_user_context`
lässt die `Serie:`-Zeile bei leerem `serien_name` weg (minimal-neutral).
Instanzen tragen ihren `serien_name` ausschließlich via `instance.json`;
der Orchestrator-Deploy (T1336) provisioniert die Datei-Werte für
`mia`/`finn`/`emil`. *Restschuld:* bis die Live-`instance.json` je
Instanz den `serien_name` trägt, erscheint keine `Serie:`-Zeile im Prompt
(Folgen bleiben generisch gerahmt, nicht falsch gerahmt).

**OPEN-HSP-X (T1382, 2026-07-07) — Display/`/config`-serien_name neutralisiert.**
Parallel zum LLM-Pfad (OPEN-HSP-W) trug auch der **zweite** `serien_name`-
Ausgabepfad — die Display-/Mini-App-Konfig-Antwort (`GET`/`PATCH /config`
→ `_build_config_response`, `hoerspiel/main.py:627`) — einen Mia-Default
(`hoerspiel/config.py` `DEFAULT_SERIEN_NAME = "Stigi & Co."`), sodass eine
Instanz ohne gesetzten `serien_name` „Stigi & Co." zurückspiegelte.
*Auflösung:* der Code-Default ist **entfernt** (kein `DEFAULT_SERIEN_NAME`
mehr); `_build_config_response` liefert `instance_cfg.serien_name` mit
Vorrang, `dcfg.serien_name` (PATCH-gesetzt) als Fallback, **neutral `""`**
wenn beides leer — dieselbe minimal-neutrale Regel wie OPEN-HSP-W im
LLM-Pfad. Damit tragen **beide** `serien_name`-Pfade (LLM + Display/config)
den Namen ausschließlich aus `instance.json`; kein Modul-Default leakt mehr.

### HSP-46 — Keine Zielgruppen-Sicht-Trennung (Nic-Setzung 2026-07-03)
Emil erscheint als **gleichrangige** dritte Instanz in derselben
Face-Pille (HSP-3a), derselben Folgen-Aggregation (HSP-35) und demselben
View-Bestand (HSP-31) wie Mia und Finn. Es gibt **keinen**
`zielgruppe`-Sichtbarkeits-Filter: das `zielgruppe`-Feld (HSP-45) ist
**deskriptiv** (steuert Ton über Daten), **nicht** ein Achsen-Feld, das
Instanzen aus einer Ansicht ausblendet. Kein App-UI-Element trennt
„Eltern-" von „Kinder-Folgen".

Die spätere Sicht-Trennung (Erwachsenen-Folgen aus der Kinder-View
ausblenden) ist **bewusst vertagt** als OPEN-HSP-S; Trigger ist die als
vollwertiger Player gebaute Settings-App. Bis dahin gilt HSP-46.

(ENTSCHEID-1263 → Nic-Verdikt Punkt 3 „KEINE Eltern/Kinder-Unterscheidung
— erstmal" + „Deferred Follow-up".)

---

## 15. Hörspiel-Player-PWA (Handy-first) — HSP-47..HSP-55

> Werft-Lauf 2026-07-03 (Gates A+B durch). Ersetzt Abschnitt 12 (Telegram-
> Eltern-Mini-App, HSP-33–40 → superseded). Realisiert die in HSP-46 /
> OPEN-HSP-S antizipierte **„als vollwertiger Player gebaute Settings-App"**.
> **Front-End-only** (Nic-Setzung): bildet den vorhandenen Backend-Stand ab,
> **kein** Folgen-/Kapitel-Builder-Delta. Fundament: `specs/platform/pwa-mantel-lib.md`
> (PWML-1..6). Mockups: `specs/mockups/hoerspiel-player/`. Bezug Epic #1265.

### HSP-47 — Wohnort, Auslieferung als PWA-Mantel-Kunde, Auth
Der Hörspiel-Player ist eine **installierbare PWA**, PWA-Mantel-Konsument
(PWML-1..4), registriert in `seiten/views.json` als `typ:pwa`
(`pfad`, `label`, `zielgruppe`, `pwa{manifest,start_url,service_worker}`).
Wohnort der View-Assets im Buddy-Bereich (`hoerspiel/templates/player.html`,
`hoerspiel/static/player.{css,js}`), gehostet vom **seiten-Service** wie die
anderen Eltern-PWAs.
**Auth:** Cookie-Pairing (`xbuddy_session`, AUTH-2 / RAT-18) — **nicht** `tma`.
Der **Kind-Umschalter ist kein Auth-Wechsel** (HSP-49): eine Eltern-Identität,
der Umschalter tauscht nur den **Inhalts-Kontext** (`<kind_id>`).

*Test-Implikation:* Manifest `display:standalone`, Service-Worker + Cache-Buster
über die Lib (PWML); ohne gültigen Cookie 401, kein Render.

### HSP-48 — Startfläche „Regal" + Mini-Player + voller Player (Gate-B-Wahl B)
Zwei Player-Ebenen, kein Tab-Chrome, kein Menü auf der Startfläche (HSP-3-Prinzip
„statisches Dashboard" für Kind-Frontends):

- **Startfläche = Folgen-Regal:** Kachel-Raster der Folgen des aktiven Kindes
  (2-spaltig, Hochkant), je Kachel Cover 1:1, Folgen-Nr, Titel, Resume-Badge
  (orange), Offline-Badge (HSP-54). Oben Umschalter-Pille (HSP-49) links +
  Zahnrad (HSP-50) rechts.
- **Sticky-Mini-Player** unten: Cover-Thumb + Titel + „Weiter hören"-Zeile +
  Play — immer sichtbar. Der Mini ist ein **globaler Now-Playing-Banner**: läuft
  eine Folge, zeigt er sie **über den Kind-Umschalter hinweg** (Cross-Kind, auch
  wenn das Regal eines anderen Kindes offen ist) und beschriftet sie mit dem
  **Eigentümer-Kind** der laufenden Folge (nicht dem gerade offenen Regal-Kind,
  HSP-49).
- **Voller Player** (eigener Screen) bei Tap auf eine Kachel **oder** den
  Mini-Player: großes Cover, Titel, großer Play/Pause + große ⏮/⏭, Fortschritt,
  Zurück-Pfeil — plus Kapitel-Liste (HSP-52). Das Kind-Label (`player-kid`)
  zeigt den **Eigentümer** der laufenden Folge (nicht das gerade offene Regal-Kind,
  Cross-Kind-Fall; HSP-49). Bedien-Regeln aus HSP-19/20/21
  (Tap startet/setzt fort; kein Wisch/Long-Press/Multi-Touch).

Layout-Robustheit analog HSP-4b (clamp, kein Clip, Cover 1:1). Design-Tokens
DTOK-1..5 + Kids-Palette (`--kids-*`), Kids-Schrift (`--kids-font-body` /
`--kids-font-display`), Stage aus `instance.json` (HSP-4).

*Test-Implikation:* GET der Player-Route rendert Regal-Kacheln des aktiven
Kindes + Mini-Player; die volle Player-Route rendert Controls + Kapitel-Liste.

### HSP-49 — Kind-Umschalter (Inhalts-Kontext) über die Instanz-Liste
Oben eine **Umschalter-Pille** (Foto+Name je Instanz aus `familie.json`, FAM-8,
Muster wie Face-Pille HSP-3a). Tap wechselt den aktiven `<kind_id>` → Regal +
Player laden das andere Instanz-Bündel (`/api/v1/hoerspiel/<kind_id>/…`).
Die Instanz-Auswahl **iteriert die hörspiel-lokale Instanz-Liste (HSP-43)** —
kein 2-Element-Hardcode; sie trägt V1 `mia`, `finn`, `emil`. `zielgruppe`
ist deskriptiv (HSP-46) — die Erwachsenen-Instanz (Emil, HSP-45) erscheint im
Umschalter wie jede andere. Modell = **Umschalter je Kontext**, NICHT die
aggregierte Cross-Kind-Liste des alten Folgen-Tabs (HSP-35). Resume-Namensräume
sind `<kind_id>`-getrennt. Läuft beim Kind-Wechsel noch ein Fremd-Album weiter,
bleibt `aktivKindId` stabil — Mini-Player und voller Player zeigen den Eigentümer
(nicht das neu gewählte Regal-Kind).

### HSP-50 — Settings als eigener Vollbild-Screen hinter Zahnrad
Ein **Zahnrad** oben rechts öffnet einen **eigenen Vollbild-Settings-Screen** mit
Zurück-Pfeil. Inhalt = die HSP-34-Regler: Playback-Tempo, Pause-Absatz,
Pause-Titel, Stimme, LLM Provider+Modell, Audio-Ziel. `PATCH /config`-Verhalten,
422-Toasts, abhängiges Modell-Dropdown, Wirkungs-Hinweis + Audio-Ziel-Kollaps
(alle Instanzen global) — **unverändert aus HSP-34** übernommen.

**Kein Kind-Sperrgriff in V1 (Nic-Setzung 2026-07-03).** Nur das Zahnrad, keine
Halte-/PIN-Hürde; **kein** Schloss-Symbol (würde eine nicht existierende Sperre
andeuten). Kind-Abweisung ist eine spätere Erweiterung (OPEN-HSP-T). Der
Eltern-Cookie (HSP-47) ist ohnehin die Auth-Membran.

### HSP-51 — Resume server-seitig, geräteübergreifend
Der Player nutzt das **server-seitige** Resume (`GET/PUT /resume`, HSP-17/36) —
Handy-Sessions teilen den Stand untereinander und potenziell mit dem Tablet.
Last-Write-Wins auf Track-Anfang (HSP-36). **V1:** der Player liest/schreibt
server-seitig; die Unifikation des Tablet-`alben`-Views (heute localStorage,
HSP-23) auf denselben Stand bleibt **OPEN-HSP-U** — Tablet unangetastet
(Nic-Setzung).

### HSP-52 — Kapitel-/Track-Wahl + Skip im Player („Untertitel")
Jede Folge ist in **Tracks** unterteilt (Intro · Inhalts-Kapitel · Outro,
HSP-6). Der volle Player (HSP-48) **muss** erlauben:
- **Kapitel-Liste** unter dem Player: alle Tracks als antippbare Liste, aktiver
  Track hervorgehoben. **Tap auf einen Track → springt direkt dorthin** und
  spielt ab (aus HSP-35 in den Kind-Player gezogen).
- **Track-Skip** ⏮ / ⏭ (voriger/nächster Track), am ersten/letzten Track
  disabled (HSP-21).
- **Feinsprung** −15 s / +15 s innerhalb des Tracks, getrennt von der
  Track-Navigation (HSP-35).
- Track-Anzeige `Track X/Y · <Label>`.

**Track-Label = vorhandener Backend-Stand.** Tracks tragen heute kein `titel`
(`titel: null`, HSP-6 optional). Label = aus `art` + `position` abgeleitet
(„Intro", „Kapitel 1..N", „Outro"); trägt ein Track ein echtes `titel`, zeigt
der Player dieses (+ optional Pikto-Wortblock HSP-6a). **Der Player erzeugt
keine Track-Namen** und fasst den Folgen-Bauer (HFE/`album_builder.py`) **nicht**
an — benannte Kapitel wären ein separates Backend-Thema, außerhalb dieses
Front-End-Laufs (Nic-Setzung 2026-07-03).

*Test-Implikation:* voller Player rendert die Track-Liste aus dem Manifest; Tap
auf Track i setzt `<audio>.src` auf dessen `audio-asset` und startet; ⏮/⏭ am
Rand disabled; −15/+15 s verschieben nur die Position im selben Track.

### HSP-53 — Ablösung der Telegram-Eltern-Mini-App (HSP-33–40)
Abschnitt 12 (HSP-33–40, Telegram-Tab-Form, `tma`-Auth, Hash-Deeplink) ist
**superseded**. Die Bot-Menü-Buttons zeigen künftig auf die **PWA**
(`setChatMenuButton`, `eltern-chat/config.py`). Die aggregierte Cross-Kind-
Folgen-Verwaltung (HSP-35) entfällt als Tab — Folgen-Zugriff läuft über den
Umschalter (HSP-49).

**Eltern-Chat-Skills nachziehen (Multi-App-Cluster, APP-1).** Die Skills, die
heute die alte Mini-App öffnen/verlinken, werden auf die PWA-Route angepasst —
Delta an ihren Skill-/Spec-Dateien im selben Paket (Skill-Specs same PR):
`eltern-chat/skills/hoerspiel_oeffnen.py` + `hoerspiel_oeffnen_task.py` +
`specs/platform/hoerspiel-oeffnen.md` (Tab-Hash entfällt, kein Tab-Modell mehr);
`eltern-chat/skills/seiten_uebersicht.py`; ggf.
`eltern-chat/skills/hoerspiel_folge_erzeugen.py` (Fertig-Link → PWA-URL). Weil
Eltern-Chat eine **andere App** ist, ist das ein **eigener Track** im F4-Schnitt,
gebündelt über einen Bundle-Hinweis.

### HSP-54 — Harter Offline-Cache der letzten N Folgen (Audio + Metadaten)
Der Player legt die **Audio-Tracks der N zuletzt freigegebenen Folgen** je
aktivem Kind **hart** in Cache Storage ab (Service-Worker, App-Hook PWML-5),
sodass sie **sofort und offline** abspielbar sind. Sicher, weil die MP3s je
`album-id` **immutable** sind (HSP-37, `Cache-Control: private, max-age=86400`).

- **Precache-Strategie (hart, nicht lazy):** beim Player-Laden (und bei neuer
  Folge) werden die Tracks der jüngsten N Folgen des aktiven Kindes vorgeladen —
  nicht erst beim Antippen. Cover-Assets analog.
- **Metadaten mit-cachen (HSP-54a):** die **Folgen-Liste**, die **Folgen-Manifeste**
  (Track-Auflösung, HSP-6) und die **Instanz-/Config-Daten** des aktiven Kindes
  werden **ebenfalls** hart gecacht. Ohne sie ist offline weder das Regal
  aufbaubar noch ein Track auflösbar — Metadaten-Cache ist damit
  *necessary-implementation* des „sofort und offline abspielbar", nicht optional.
- **Budget/Eviction:** N je Kind (Default **N=3**), LRU-Verdrängung. MP3 96 kbps
  mono ⇒ wenige MB je Folge. Metadaten sind klein und teilen den kind-getrennten
  Namensraum.
- **Switcher-bewusst:** Cache-Namensraum je `<kind_id>`.

**OPEN-HSP-W** — Precache-N-Wert (Default 3) + ob N/Budget Eltern-verstellbar in
die HSP-Config gehört oder fixe Konstante bleibt (Bau-Entscheidung).

*Test-Implikation:* nach Player-Load sind die Tracks der jüngsten N Folgen in
Cache Storage (kind-getrennt); Offline-Fetch eines gecachten Tracks liefert 200
aus dem Cache; die N+1-te Folge ist LRU-verdrängt. **HSP-54a:** offline sind
Folgen-Liste, Manifest und Config des aktiven Kindes aus dem Cache verfügbar
(Regal + Track-Auflösung funktionieren ohne Netz). Test-Referenzen petrankern
**HSP-54 / HSP-54a** (nicht eine frei erfundene AC-ID).

### HSP-55 — Tests
JS-Unit (JSDOM) + Render-Gate (RAT-24, `hoerspiel/player`-Pilot): Startfläche =
Regal + Mini-Player (kein Tab-Chrome); Umschalter iteriert die Instanz-Liste und
wechselt `kind_id`; Zahnrad öffnet Settings-Vollbild; Resume server-seitig
gelesen/geschrieben; Kapitel-Wahl + Skip (HSP-52); PWA-Manifest
`display:standalone` + MediaSession (HSP-22); harter Folgen-Cache offline
abspielbar (HSP-54).

## 16. Recherchierte Erwachsenen-Generierung (emil) — HSP-56..HSP-60

Die Erwachsenen-Instanz (emil, `zielgruppe:erwachsen`) generiert einen
**recherchierten Zwei-Host-Deep-Dive** (Dialog-Skript `KIM:`/`RUBEN:`). Ratifiziert
berater-runde 2026-07-05/06. **Recherche-Pivot (T1371, 2026-07-06):** der externe
Such-Provider (Tavily) ist **entfernt**; die Recherche läuft über das
**server-seitige `web_search`-Tool** desselben Anthropic-Vendors (LLMP-3 7.
Capability) — kein externer Such-Account, kein `tavily-api-key`-Slot, keine
Dritt-Cloud. Single-Voice-Wiedergabe ist bewusst V0 (kein Multi-Voice-TTS).

### HSP-56 — Zielgruppe-bewusster System-Prompt-Schnitt
Zwei Prompt-Dateien `geschichtenbuddy-kind.md` / `geschichtenbuddy-erwachsen.md`;
`_load_system_prompt(zielgruppe)` (`hoerspiel/llm_service.py`) wählt je Instanz. Die
Kind-Datei ist die **byte-gleiche Umbenennung** der heutigen (Golden/Diff-Guard —
mia/finn-Folgen bleiben identisch). Die Erwachsen-Datei **erlaubt düster** (emil
`ton`) und **erzwingt Dialog-Skript** (`KIM:`/`RUBEN:`) + META-Block statt narrativer
Story-Absätze.

### HSP-57 — Recherche-Vorschritt (Form B1: EIN web_search-Call, kein agentischer Loop)
Ein Recherche-Service als **Vorschritt** vor dem bestehenden Single-Shot. **Form B1
(T1371, ratifiziert 2026-07-05/06):** EIN `get_agent`-Call (`tools.llm`) mit
aktiviertem server-seitigem **`web_search`**-Tool bekommt AUSSCHLIESSLICH das `thema`
als User-Nachricht, sucht selbst und synthetisiert einen **Fakten+Quellen-Block** —
die Quellen werden aus den `web_search_tool_result`-Blöcken (`{url,title,page_age}`)
erfasst, der Zähler `suchen_pro_folge` aus `web_search_requests`. Der Block wird in den
`complete_structured`-Single-Shot gespeist; der Single-Shot-Vertrag bleibt
**unverändert**. Der frühere Zwei-Stufen-Pfad (Query-Gen → externe Such-API →
Distill, zwei Freitext-Calls + N HTTP-Suchen) ist damit **abgelöst**. Der voll-
agentische tool_use-Loop bleibt weiterhin **deferiert** (B1 ist ein einzelner
Vorschritt-Call, kein Mehr-Turn-Loop).

### HSP-58 — Erwachsen-Invariante + Datenabfluss-Klassifikation
Der Recherche-Vorschritt ist **hart an `zielgruppe:erwachsen` gebunden** (Config-
Invariante) — **nie** bei einer Kind-Instanz. Es fließen **ausschließlich
thema-abgeleitete Suchanfragen** ab, **keine Personen-/Familiendaten**
(Constitution §3). **Egress-Entschärfung (T1371):** die Suche läuft über das
server-seitige `web_search`-Tool **desselben Anthropic-Vendors**, der die Folge
ohnehin schreibt — **keine zusätzliche Dritt-Cloud, kein externer Such-Account,
kein `tavily-api-key`-Slot**. Der Vorschritt läuft nur, wenn der Slot-Vendor die
`web_search`-Capability deklariert (Anthropic ja, Mistral nein — sonst Degradation).
N-Suchen **hart gedeckelt** über `max_uses` am web_search-Tool (Vorschlag 3–5, an
`tiefe` gekoppelt). **Degradations-Pfad** bei fehlender Agent-Sicht / fehlender
`web_search`-Capability / Quota-/Netz-Fehler / leeren Treffern: Folge **ohne**
Recherche generieren + Log-Marker, kein harter Abbruch.

**V0-Rest-Kanal-Klausel (emil-Instanz, Nic-Setzung 2026-07-06):** Das `thema` ist
ein Freitext-Feld und kann PII tragen (Betreiber tippt z. B. Namen oder Ort ins Thema),
was ohne Scrub-Schritt ungefiltert in die `web_search`-Anfrage fließt. Für die
**emil-Instanz (V0)** ist dieses Risiko **bewusst akzeptiert**: NUR der Betreiber
(Nic) tippt Themen — kein Kind- oder Fremd-Input. Ein `thema`-Scrub/Ack-Schritt wird
**PFLICHT**, sobald Nicht-Betreiber-Recherche-Instanzen entstehen (neuer Buddy,
Familien-Multi-Tenancy o. ä.).

### HSP-59 — Anti-Slop als Self-Check im Single-Shot
Die Anti-Slop-Kriterien des Kits (Gedankenstrich-Stilmittel, unbelegte Zahl, doppelt
erklärter Begriff, „Hallo-und-willkommen"-Einstieg, Kim/Ruben durchgehend einig,
Weichspül-Landung) werden als **Self-Check in den Single-Shot-Prompt** gegossen — **0
Zusatz-Calls**. Die zweite Berater/Antiberater-Gate-Schleife (eigener Prüf-Pass) ist
**deferiert bis zu einem echten n=1-Slop-Schmerz**.

### HSP-60 — Betrieb + Persistierung
Log-Zähler `suchen_pro_folge` (= `web_search_requests`). Endpoint- **und**
nginx-`proxy_read_timeout` gegen die **gemessene** neue Oberlänge (web_search-Call
mit bis zu N Suchen + Single-Shot) abgleichen — messen, nicht schätzen. `VOICES` bleibt Single-Voice (`album_manifest.py:17`, V0 ok).
META-Block (`quellen[]`/`these`/`schnitt`/`begriffe_neu[]`) schreibt in
`folgen-historie.md` fort.

---

## Entscheidungen

### E-HSP-1 — TTS-Engine + Voices fixiert (Azure OpenAI tts-hd, shimmer/onyx)
*Datum:* 2026-06-11/12 · Brainstorm-Verifikation an Folge 22 in beiden
Voices, EU-DPA über `swedencentral`. Pausen über expliziten Silence-Insert,
nicht über `speed`-Parameter — `speed` erzeugt blechernen Klang
(post-hoc Time-Stretching). **Verworfen:** native deutsches Azure-Speech-
HD-de-DE (leicht schlechter), ElevenLabs (Budget-/EU-Pfad-Sprengung,
OPEN-HSP-F), `gpt-4o-mini-tts` (nicht in `swedencentral` deploybar),
`gpt-audio-mini` (Chat-Modell, Drift-Risiko beim Vorlesen).

### E-HSP-2 — Intro/Outro als geteilte Shared-Assets, vier feste Dateien
*Datum:* 2026-06-12 · Bei 16 Folgen/Monat spart das 16 × Intro+Outro-
Synthese-Zeit und -Kosten; über ein Jahr nicht trivial. Die Reime sind
jede Folge wortgleich; eine Re-Synthese wäre reine Verschwendung.
**Verworfen:** Intro/Outro pro Folge mitsynthetisieren.

### E-HSP-3 — Erster KI-Buddy baut direkt, kein Plattform-LLM-Gateway in V1
*Datum:* 2026-06-12 · RAT-6 milde Lesart: „konsistent kopieren statt
antizipativ generalisieren". HSP ist der erste KI-Buddy; ein Plattform-
LLM-Gateway wird bei n=1 nicht gebaut, sondern entsteht später, wenn das
direkte Pattern an zweiten/dritten KI-Buddies kopiert wurde und der
Generalisierungs-Schmerz belegt ist. HSP exposed das **provider-agnostische
Adapter-Pattern** analog `eltern-chat/providers/` (HSP-10) — damit
**ist** HSP die kopierfähige Vorlage. **Verworfen:** Plattform-Gateway
vor V1 (Premature Plattform).

### E-HSP-4 — Resume auf Track-Anfang, nicht auf Sekunde
*Datum:* 2026-06-12 · Brainstorm-Nic: „wir können einfacher zurückspringen
wenn das Kind nicht zu Ende gehört hat". Track ist die natürliche
Wiederaufnahme-Granularität (3–4 min, geschnitten an Absatzgrenzen).
Trade-off: das Kind hört 30–60 s nochmal — akzeptabel und gut (es erinnert
sich wieder an die Szene). Im Gegenzug ist die Persistenz extrem einfach:
Album-ID + Track-Position, keine Sekunden-Sync. **Verworfen:** Sekunden-
genaue Server-seitige Resume-Persistenz.

### E-HSP-5 — Welt-Bible und Folgen-Historie sind Per-Instanz-Daten
*Datum:* 2026-06-12 · Familie-3-Probe: was variiert je Familie, ist
Daten, nicht Code. Andere Familie = andere Welt = andere Bible. **Verworfen:**
Bible als hartcodiertes Markdown im Code-Bereich.

### E-HSP-6 — LLM-Adapter und Prompts leben in der App, nicht im Skill
*Datum:* 2026-06-12 (Werft-Lauf) · APP-1 verlangt App-Eigentum von Daten +
Funktion + Schnittstelle gemeinsam. Die Folgen-Erzeugungs-Funktion braucht
die Bible-Daten; sie gehört darum zur App, der die Daten gehören (HSP-1).
Trigger-Agnostik (HSP-11) erlaubt späteren Sprach-Trigger, Cron, CLI ohne
Duplikation. **Verworfen:** LLM-Aufruf im Eltern-Chat-Skill mit Bible-
Pull per API (würde Skill dick machen und APP-1 verletzen).

### E-HSP-7 — Eltern-Quality-Gate auf Text, nicht auf Audio (V1)
*Datum:* 2026-06-12 · Brainstorm-Nic: „Vorschau auf Text, nicht Audio,
das reicht für MVP". V1 zeigt den Folgentext im Eltern-Chat zur Freigabe;
die Vertonung läuft erst nach „Ja". Audio-Probehören ist offen für V2,
ist aber vermutlich nicht nötig. **Verworfen:** Audio-Probehör-Gate im
V1-Workflow (Synthese-Kosten und Wartezeit für ungenutzte Vorschau-
Audios).

### E-HSP-8 — Splitscreen-Layout, statisches Dashboard, 5×2-Raster mit Mehr-Slot
*Datum:* 2026-06-12 (Werft-Lauf F3, Gate B Nic) · Drei Architektur-
Achsen in einer Entscheidung:

- **Splitscreen Links/Rechts:** Kacheln links, Player rechts immer
  sichtbar als vertikale Säule. **Verworfen:** Bottom-Drawer
  (verdrängt das Kachel-Raster bei Wiedergabe, erfordert Modus-Wechsel,
  bricht das statische Dashboard).
- **Statisches Dashboard, keine Menüführung:** oberste Priorität für
  Kinder-Frontends. Tap auf Kachel ändert nur den Player-Inhalt, nicht
  die Navigation. **Verworfen:** Sub-Routes für Player oder Album-
  Details (wäre Navigations-Akt, gegen HSP-3-Statisch).
- **5×2-Raster mit Mehr-Kachel auf Position 10:** 10 Folgen ohne
  Scrollen sichtbar; bei mehr als 9 freigegebenen Alben übernimmt die
  10. Kachel die „Ältere Folgen"-Funktion. **Verworfen:** 4×3=12
  (sprengt Kachel-Größe in Splitscreen-Breite), Scrollen (Werft-Befund
  Nic „statisches Dashboard, keine Menüführung").

### E-HSP-9 — Resume-Stand lebt im Player rechts, kein eigener Banner
*Datum:* 2026-06-12 (Werft-Lauf F3, Gate B Nic) · Da der Player rechts
**immer sichtbar** ist (E-HSP-8), zeigt sein Default-Zustand bereits den
Resume-Stand mit orangem „Weiter hören"-Play-Button (HSP-2). Zusätzlich
trägt die Resume-Kachel ein orange „Weiter"-Badge. Ein eigener Resume-
Banner über dem Kachel-Raster wäre **Doppel-Information** und würde
Vertikal-Raum für eine Kachel-Reihe kosten. **Verworfen:** prominenter
„Weiter hören"-Banner als eigene Sektion (war iter-1/iter-2-Variante,
in F3 abgelöst).

### E-HSP-10 — Einheitliches 1:1 Cover-Format in allen Slots
*Datum:* 2026-06-12 (Werft-Lauf F3, Gate B Nic) · Album-Kachel-Cover,
Player-Cover und „Ältere Folgen"-Pikto-Slot nutzen **identisches
1:1-Format**: derselbe Asset-Pfad rendert in jedem Slot visuell gleich
(Aspect-Ratio, Hintergrund-Tint, Rahmen). Damit ist die Erzeugung von
Cover-Assets (V1 ein Default-Cover, V2 pro Folge OPEN-HSP-A) auf **ein
einziges Format-Ziel** standardisiert: quadratisch, mindestens
~1000×1000 px. **Verworfen:** unterschiedliche Aspect-Ratios je Slot
(würde verlangen, dass jedes Cover-Asset in mehreren Format-Varianten
existiert).

### E-HSP-11 — Pikto-im-Text-Wortblock als geteiltes Komponenten-Muster
*Datum:* 2026-06-12 (Werft-Lauf F3, Gate B Nic) · Der Inline-Pikto-
Wortblock (HSP-4a) ist eine kompakte Schwester-Variante zum Routine-
Buddy-`.card-pikto`-Pattern (Routine-Karten zeigen großen Pikto neben
Karte; HSP zeigt kleinen Pikto im Fließtext). Das Muster vereinheitlicht
die kindgerechte Verbindung von Wort und Pikto über Buddies hinweg und
ist datenseitig **optional pro Album/Track** (HSP-5a, HSP-6a) — Titel
ohne tragbaren Schlüsselbegriff rendern pur. **Verworfen:**
buddy-eigenes Komponenten-Muster ohne Routine-Erdung (würde
Geschwister-Drift produzieren). Eine plattformweite Konvention für die
Komponente entsteht — wenn überhaupt — beim 2.–3. Vorkommen
(Berater-Memory n=2-Regel).

### E-HSP-12 — Dritte Instanz (Emil): hörspiel-lokale Liste, Daten-Ton, keine Sicht-Trennung
*Datum:* 2026-07-03 (#1263, ENTSCHEID-1263) · Nic-Verdikt: Hörspiel ist
ein Familien-Ding, die Erwachsenen-Instanz ist dauerhaft gewollt (HSP-28a
reaktiviert). Der Mehr-Instanz-Cut wird **hörspiel-lokal** über eine
Runtime-Iterations-Liste gelöst (HSP-43), der Erwachsenen-Ton **rein über
Instanz-Daten** (HSP-45), und Emil erscheint **gleichrangig ohne
Zielgruppen-Sicht-Filter** (HSP-46). **Verworfen:** (a) generische
RAT-17-Registry mit Ports/Origins in der Liste — bleibt vertagt bis zur
zweiten n-Instanz-Buddy-Klasse (Premature Generalization); (b) App-UI-
Alters-/Zielgruppen-Achse — Einfachheit > Flexibilität, Ton gehört in
Daten; (c) sofortige Eltern-/Kinder-Sicht-Trennung — vertagt als
OPEN-HSP-S bis zur Settings-App-als-Player.

### E-HSP-13 — Face-Pille n≥3: Cycle-Toggle statt Reihe (Nic-Setzung 2026-07-08)
*Datum:* 2026-07-08 (fix/hoerspiel-switcher-cycle, #1406) ·
*Supersedes ENTSCHEID-1263 F2 „Face-Pille als Reihe bei n≥3".*
Nic-Verdikt: „zwei Knöpfe die sich widersprechen" — die additiven Pillen
der übrigen Instanzen (Finn + Emil) erzeugen aus Mias View einen
visuellen Widerspruch ohne klare Semantik. **Lösung: EIN Cycle-Toggle.**
Die Pille zeigt das **aktive Kind** (Ring + Foto + Name) und einen
„↔ wechseln"-Hinweis; Tap führt per vollständiger Navigation zur
**nächsten Instanz im Ring** (`config.INSTANZEN`-Reihenfolge, wrap-around,
z. B. mia→finn→emil→mia), gefiltert auf Registry-vorhandene Personen.
Muster: analog `nextKindId` in `hoerspiel/static/player.js`. Kein JS-State
(RAT-17 Option A), localStorage-Namensräume unverändert URL-getrennt (HSP-23).
**1-Instanz-Solo-Fall bleibt unverändert** (kein Wechsel-Link, `face-pille--solo`).

---

## Provenienz

Diese Spec entstand am 2026-06-12 aus einem zweitägigen Brainstorm
(2026-06-11/12) mit Nic. Werft-Input:
`brainstorm/ideas/mia-hoerspiel-app/spec_entwurf.md` (HSP-* IDs analog
übernommen), `workflow_album_modell.md` (Album-/Bündel-/Resume-Mechanik),
Welt-Bible und Folgen-Historie aus 20 Vorgänger-Folgen. Brainstorm-Retro:
`~/brainstorm/2026-06-12-retro.md` (TTS-Stack-Fixierungen, Anti-Pattern-
Audit). Erste produktive Folge (Folge 22) wurde in beiden Voices als
Klang-Exemplar gebaut und dient als Seed für den V1-Abend-Test (HSP-32).
