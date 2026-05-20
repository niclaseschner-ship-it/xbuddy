# Figuren-Erkennung — Spec     (ID-Präfix: FIG)

> Status: V1-Kern · Refs #1, #6 · Implementiert in #7

Wiederverwendbare HTML/JS-Seite, die auf einem im Querformat liegenden
Handy-Display physische Buddy-Figuren am Drei-Punkt-Touch-Muster erkennt,
ihre Drehung verfolgt und semantische Events an den Router sendet.

**V1-Scope:** Standalone Test-Seite mit fest hinterlegter Demo-Registry.
Später wird die Seite als Baustein in per-Kind individualisierte Buddy-URLs
eingebettet.

**Out-of-Scope:** Controller-Runtime / Kiosk-Hülle, Button-Panel-Seiten,
Router-seitige Winkel-Hysterese und Quantisierung, Scene-Dispatch, zentraler
Muster-Registry-Service, Onboarding-Flow für neue Figuren. Diese Bausteine
bekommen je eigene Specs, sobald ein Ticket sie berührt.

## 1. Erkennung

### FIG-1 — Drei-Punkt-Pattern
Die Seite erkennt eine Figur, sobald drei stabile Touchpunkte auf dem
Display anliegen. Zwei oder weniger Punkte zählen nicht als Figur.

*Tickets:* #1

### FIG-2 — Drei-Punkt-Hysterese (nur Eintritt)
Eine Figur gilt als **präsent**, sobald drei stabile Punkte für mindestens
150 ms anliegen. Die Präsenz hält fortan unverändert an — kapazitiv
erkannte Touch-Verluste (Hand abgehoben, Aussetzer, Figur losgelassen aber
liegen geblieben) **enden die Session nicht**. Eine Session endet nur durch
(a) den Session-Ende-Button (FIG-8) oder (b) das Erkennen einer anderen
Figur (FIG-11).

*Tickets:* #1

### FIG-3 — Pattern-Descriptor
Aus den drei Touchpunkten berechnet die Seite einen rotations- und
translations-invarianten Descriptor: die normalisierten, sortierten
Seitenlängen des Dreiecks. Der Descriptor identifiziert das Muster
unabhängig davon, wo und wie die Figur auf dem Display liegt.

*Tickets:* #1

### FIG-4 — Demo-Registry (V1)
Eine fest in der Seite hinterlegte Liste von Patterns mit zugehörigen
`figure_id`. Für V1 reichen ein bis zwei Test-Einträge mit klar trennbaren
Descriptor-Werten. Toleranzschwelle für Pattern-Matching konfigurierbar
(Default ±5 % auf den normalisierten Seitenlängen). Diese Registry wandert
später in einen zentralen Dienst (siehe OPEN-FIG-B).

*Tickets:* #1

### FIG-5 — Identifikation
Sobald ein Pattern als „präsent" gilt (FIG-2) und mit einem Eintrag in der
Registry innerhalb der Toleranz übereinstimmt, gilt die Figur als
**identifiziert** mit dieser `figure_id`. Kein Match innerhalb der
Toleranz → Figur gilt als „unbekannt"; kein Event nach außen.

Vergleichs-Metrik: L1-Mittel-Distanz über die drei
Descriptor-Komponenten.

*Tickets:* #1

### FIG-6 — Winkel (kumuliert während Kontakt)
Der gemeldete Winkel ist die **kumulative Rotation** seit dem
`figure_detected` der aktuellen Session. Nur Drehungen, die **während
gleichzeitigem 3-Punkt-Kontakt** der Figur erfolgen, fließen in den Wert
ein. Touch-Verluste (n < 3) und Re-Akquise bei Wieder-Auflegen tragen
**nichts** bei.

Initial bei `figure_detected`: 0°. Wertebereich offen — kann nach
mehrfachen Drehungen über ±360° hinausgehen. Ungefiltert und unquantisiert
— Hysterese und Stufen-Logik laufen Router-seitig.

*Tickets:* #1

### FIG-7 — Räumliche Punkt-Verfolgung
Zwischen zwei aufeinanderfolgenden 3-Punkt-Frames werden die Punkte
**räumlich** einander zugeordnet (nächster Nachbar), unabhängig von
wechselnden Touch-Identifiern. Begründung: kapazitive Sensoren produzieren
häufig ID-Flackern bei stabiler physischer Auflage; ID-basiertes Tracking
ist deshalb nicht robust genug.

Pro Punktepaar wird der Winkel um den jeweiligen Schwerpunkt berechnet,
die drei Pro-Punkt-Deltas werden gemittelt. Reine Translation (alle drei
Punkte verschieben sich identisch ohne Drehung) erzeugt damit per
Konstruktion kein Winkel-Delta.

Liegen die nächste-Nachbar-Distanzen jenseits einer Schwelle
(`match_distance_px`, Default 60 px), gilt die Zuordnung als gescheitert
(Kontakt-Bruch); der Akku wird re-ankert ohne Beitrag.

*Tickets:* #1

### FIG-8 — Session-Ende per Button im Figur-Schwerpunkt
Die Seite zeigt während einer aktiven Session einen kreisförmigen Button
**„Session beenden"** an der Position des aktuellen 3-Punkt-Schwerpunkts.
Sein Radius entspricht mindestens dem Abstand vom Schwerpunkt zum am
weitesten entfernten Touch-Punkt der Figur (plus kleines Padding) — der
Button überdeckt damit die Figur-Standfläche.

Mit jedem 3-Punkt-Frame werden Position und Größe neu berechnet. Bei
Touch-Verlust (n < 3) bleibt der Button an der **zuletzt bekannten**
Position und Größe stehen.

**Wirkung:** Solange die Figur physisch auf dem Display sitzt, deckt sie
den Button-Bereich vollständig ab — er ist unerreichbar, ein Versehen
praktisch ausgeschlossen. Erst wenn der Benutzer die Figur **abhebt**, wird
die Button-Fläche frei.

**Auslöser:** Wird innerhalb der Button-Kreisfläche ein einzelner
Touchpunkt (`touches.size === 1`) für mindestens 100 ms gehalten, sendet
die Seite `session_ended` mit `reason: "user_button"` und schließt die
Session (`figurePresent` und `identifiedFigureId` werden zurückgesetzt,
der Button verschwindet). Ein einzelner Touchpunkt **außerhalb** der
Kreisfläche löst nichts aus.

Außerhalb einer aktiven Session ist der Button nicht sichtbar.

*Tickets:* #1

## 2. Events an den Router

### FIG-9 — Transport
Events gehen per HTTP POST an `<router_url>/event`, JSON-Body,
`Content-Type: application/json`.

*Tickets:* #1

### FIG-10 — Event-Schema
Drei Event-Typen, alle als Zustands-Aussage (idempotent). **Pflichtfelder
auf allen drei Event-Typen:** `source_id`, `ts`, `type`. Weitere Felder
sind event-spezifisch:

```json
// Beim ersten sicheren Erkennen einer Figur — und bei Wechsel auf eine
// andere identifizierte Figur ohne vorheriges Session-Ende
{ "source_id": "phone:test-1", "ts": "<iso8601>",
  "type": "figure_detected",
  "figure_id": "<string>", "angle": 0 }

// Während die Figur präsent ist, gedrosselt; angle ist die kumulierte
// Rotation seit figure_detected (siehe FIG-6, FIG-11)
{ "source_id": "phone:test-1", "ts": "<iso8601>",
  "type": "angle_update",
  "figure_id": "<string>", "angle": <float> }

// Beim Druck auf den Session-Ende-Button (FIG-8)
{ "source_id": "phone:test-1", "ts": "<iso8601>",
  "type": "session_ended",
  "figure_id": "<string>", "reason": "user_button" }
```

`source_id` identifiziert die Controller-Instanz; Wert konfigurierbar
(FIG-17). Format-Konvention: `<typ>:<instanz>` (z. B. `phone:test-1`,
später `nfc:reader-kueche`, `telegram:nic`). V1: reine
Konfigurations-Konstante, keine zentrale Vergabe (siehe Ticket #6).

`angle` ist Float in Grad und kann nach mehrfachen Drehungen über ±360°
hinausgehen.

*Tickets:* #1, #6

### FIG-11 — Sende-Logik (kumulativer Winkel)
- `figure_detected`: bei Übergang „keine identifizierte Figur" →
  „identifizierte Figur", inklusive Wechsel auf eine andere `figure_id`.
  `angle: 0` (Session-Start).
- `angle_update`: gedrosselt auf maximal **10 Hz** und nur, wenn der
  **kumulative** Winkel sich um ≥ **3°** gegenüber dem zuletzt gesendeten
  Wert verändert hat.
- `session_ended`: einmalig beim Button-Druck (FIG-8) mit
  `reason: "user_button"`.

Wenn die 3-Punkt-Auflage temporär verloren geht (Hand abgehoben), sendet
die Seite **kein** Event — die Session läuft weiter, der Akku pausiert.

*Tickets:* #1

### FIG-12 — Retry
Bei fehlgeschlagenem POST: bis zu **3 Wiederholungen** mit Backoff
200 ms / 1 s / 5 s. Danach Drop. Kein Persistenz-Puffer.

*Tickets:* #1

## 3. Visualisierung (V1-Test-Layout)

Solange die Seite standalone testbar ist und nicht in eine Buddy-URL
eingebettet wird, ist die Visualisierung Teil der Seite selbst. Diese
Anforderungen entfallen, sobald die Komponente in echte Buddy-URLs
eingebettet wird.

### FIG-13 — Zielfeld
Mittig auf der Seite ein gut sichtbares, gestricheltes Rechteck mit
Beschriftung **„Figur hier auflegen"**. **Während einer aktiven Session
ist das Zielfeld ausgeblendet** — der Session-Ende-Button (FIG-8)
übernimmt die zentrale Stelle der Anzeige.

*Tickets:* #1

### FIG-14 — Roh-Datendarstellung
Live aktualisiert auf jeden Touch-Event:

- Liste der aktuellen Touchpunkte: `Punkt N: x=… y=…`
- Aktueller Pattern-Descriptor (sofern ≥ 3 Punkte)
- Aktuell erkannte `figure_id` oder „— unbekannt —"
- Aktueller kumulativer Winkel (Session-Akku)

*Tickets:* #1

### FIG-15 — Header
Banner oben: **„FIGUREN-ERKENNUNG · V1-TEST · `<source_id>`"**.

*Tickets:* #1, #6

### FIG-16 — Footer
- Letzter erfolgreicher POST + letzter Fehlschlag mit Zeitstempel
- Counter Events der letzten 60 s, aufgeschlüsselt nach Typ

*Tickets:* #1

## 4. Konfiguration

### FIG-17 — Konfigurationswerte
Statisch in der Seite (JS-Konstanten) oder als URL-Parameter überschreibbar:

| Parameter                    | URL-Param         | Default                                  |
|------------------------------|-------------------|------------------------------------------|
| `source_id`                  | `?source=<id>`    | `phone:test-1`                           |
| `router_url`                 | `?router=<url>`   | leer → Events nur in `console.log`       |
| `figure_present_ms`          | —                 | 150                                      |
| `pattern_tolerance`          | `?tol=<float>`    | 0.05                                     |
| `match_distance_px`          | —                 | 60                                       |
| `tap_dwell_ms`               | —                 | 100                                      |
| `angle_update_max_hz`        | `?rate=<int>`     | 10                                       |
| `angle_update_min_delta_deg` | `?dead=<float>`   | 3                                        |

`source_id` wird in jedes Event geschrieben (FIG-10). `match_distance_px`
ist die Schwelle für die räumliche Punkt-Zuordnung (FIG-7).

*Tickets:* #1, #6

## 5. HTML-Anforderungen

### FIG-18 — Querformat angenommen
Die Seite geht von Querformat-Layout aus (~640–900 px Breite,
~360–430 px Höhe). Sie sperrt selbst keine Rotation — das übernimmt
später die Controller-Runtime. Für V1-Tests im normalen Browser muss der
Tester das Phone im Querformat halten.

*Tickets:* #1

### FIG-19 — Selbsttragend
Keine externen Asset-Quellen (kein CDN, keine Drittpartei-Domain, keine
externen Libraries). Die Seite besteht aus einer HTML-Datei mit
Inline-CSS und einer begleitenden JS-Datei `figlib.js` im selben
Verzeichnis. Beide werden zusammen ausgeliefert, nach erstem Laden
offline-fähig.

*Tickets:* #1

---

## Offene Punkte

- **OPEN-FIG-A** — Sind „normalisierte sortierte Seitenlängen" (FIG-3) als
  Pattern-Descriptor robust genug, oder braucht es einen reicheren
  Deskriptor (z. B. Innenwinkel zusätzlich)? Real-Test mit echten Figuren
  auf echtem Phone entscheidet.
- **OPEN-FIG-B** — Wie kommt eine neue Figur in die Registry
  (Onboarding-Flow)? V1 fest verdrahtet, V2 als eigene Spec. Wo lebt die
  zentrale Registry langfristig — Hub, Cloud, eigener Service?
- **OPEN-FIG-C** — Konkreter Test-Endpoint für POSTs in V1: Router-Stub,
  Echo-Server oder reine `console.log`? Entscheidung beim
  Implementierungs-Ticket.

---

## Entscheidungen

Architektur-Entscheidungen aus der Konzept- und Test-Session, festgehalten
an der Spec, weil sie nicht aus dem Code ableitbar sind und für
Folge-Tickets load-bearing bleiben.

### E-FIG-1 — Logik in der Seite, nicht im Router
*Datum:* 2026-05-19

Frühe Variante: Controller streamt rohe Touch-Snapshots (30 Hz) an den
Router; Router rechnet alles (Erkennung, Winkel, Hysterese). **Verworfen**
wegen Skalierungsbedenken: bei mehreren parallel aktiven Controllern
entstehen schnell ≥100 Req/s nur an Telemetrie, und der Router müsste pro
Stream einen Tracker laufen lassen.

Stattdessen: die Seite erkennt Figur + Winkel lokal und sendet **nur
semantische Events**. Resultat ~1 Event/s während aktiver Drehung, Null
im Ruhezustand. Winkel-Hysterese und Quantisierung bleiben Router-seitig
(pro Buddy/Szene konfigurierbar) — diese Logik lebt aber nicht in dieser
Spec.

### E-FIG-2 — Kumulativer Winkel statt absolutem Anker
*Datum:* 2026-05-20

Frühe Variante: Roh-Winkel ist die Orientierung des Vektors
Pattern-Schwerpunkt → Touchpunkt mit niedrigster Touch-id, absolut in
[0, 360°). **Verworfen** in der Test-Session: zwei Probleme,

1. Beim Lift-and-Place werden neue Touch-Identifier vergeben — die
   „niedrigste id" zeigt plötzlich auf einen anderen physischen Bump.
   Der gemeldete Winkel springt, obwohl die Figur identisch liegt.
2. Auch bei stabilen Identifiern ist der instantane Anker-Winkel
   sensor-noisy.

Stattdessen: kumulativer Winkel, der nur **während ununterbrochenem
3-Punkt-Kontakt** Delta-Werte aufaddiert. Lift-and-Place trägt nichts
bei; Drehung in der Luft ebenfalls nicht. Robust gegen ID-Flackern,
weil Pro-Punkt-Deltas räumlich gemittelt werden (FIG-7).

### E-FIG-3 — Session-Ende nur explizit über Centroid-Button
*Datum:* 2026-05-20 (Update von 2026-05-19)

Kapazitiv lässt sich „Figur abgehoben" nicht von „Figur losgelassen"
unterscheiden — beim Loslassen verschwindet die Erdung, alle Touchpunkte
fallen weg, obwohl die Figur physisch noch auf dem Display sitzt.
**Konsequenz:** Touch-Verlust beendet die Session **nicht**. Eine Session
endet ausschließlich durch
(a) den ausdrücklichen **Session-Ende-Button im Figur-Schwerpunkt**
(FIG-8) oder
(b) das Erkennen einer anderen Figur (FIG-11).

Eine ältere Variante mit „1-Finger-Tap → Session-Ende" wurde verworfen,
weil sie dieselbe Mehrdeutigkeit hatte: jeder versehentliche Hand-Kontakt
würde die Session schließen. Der Button im Figur-Schwerpunkt mit
Figur-Größe ist ein unverwechselbares, vom Benutzer gewolltes Signal —
physisch durch die Figur verdeckt, nur nach Abheben erreichbar.

### E-FIG-4 — Eine HTML-Seite je Controller-Typ, nicht eine Runtime mit Plugins
*Datum:* 2026-05-19

Ein Handy-Controller zeigt je nach Szene eine von wenigen HTML-Seiten
(Eltern-Buttons, Kinder-Buttons, Figuren-Erkennung, …). Die alternative
Architektur — eine generische Controller-Runtime, in die Module gesteckt
werden — wurde verworfen, weil sie ohne klaren Mehrwert eine weitere
Indirection-Schicht bringt. Jede Controller-Variante ist einfach eine
eigene URL mit eigener Spec.

### E-FIG-5 — `source_id` als Pflichtfeld von Anfang an
*Datum:* 2026-05-20

`source_id` ist ab V1 Pflichtfeld in allen Event-Typen (siehe Ticket #6).
**Begründung:** Sobald ein zweiter Controller-Typ (NFC, Telegram, …) oder
ein zweites Phone dazukommt, ist die Quelle der Schlüssel jeder
Routing-Entscheidung im Router. Nachträgliches Einführen würde Phone-Code
und Router-Code je zweimal anfassen lassen — und der Router müsste zwei
Schema-Versionen parallel halten. Jetzt mitziehen kostet wenige Zeilen.
