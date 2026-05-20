# Figuren-Erkennung — Spec     (ID-Präfix: FIG)

> Status: V1-Kern · Refs #1

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
Die Seite erkennt eine Figur, sobald drei stabile Touchpunkte auf dem Display
anliegen. Zwei oder weniger Punkte zählen nicht als Figur.

### FIG-2 — Drei-Punkt-Hysterese
Eine Figur gilt als **präsent**, wenn drei stabile Punkte für mindestens
150 ms anliegen. Sie gilt als **abwesend**, wenn weniger als drei Punkte
für mindestens 400 ms anliegen. In der 400-ms-Übergangsphase werden auch
zwei Punkte als Fortsetzung gezählt (Ausnahme-Toleranz für losen
Sockel-Kontakt).

### FIG-3 — Pattern-Descriptor
Aus den drei Touchpunkten berechnet die Seite einen rotations- und
translations-invarianten Descriptor: die normalisierten, sortierten
Seitenlängen des Dreiecks. Der Descriptor identifiziert das Muster
unabhängig davon, wo und wie die Figur auf dem Display liegt.

### FIG-4 — Demo-Registry (V1)
Eine fest in der Seite hinterlegte Liste von Patterns mit zugehörigen
`figure_id`. Für V1 reichen ein bis zwei Test-Einträge. Toleranzschwelle
für Pattern-Matching konfigurierbar (Default ±5 % auf den normalisierten
Seitenlängen). Diese Registry wandert später in einen zentralen Dienst
(siehe OPEN-FIG-B).

### FIG-5 — Identifikation
Sobald ein Pattern als „präsent" gilt (FIG-2) und mit einem Eintrag in der
Registry innerhalb der Toleranz übereinstimmt, gilt die Figur als
**identifiziert** mit dieser `figure_id`. Kein Match innerhalb der Toleranz
→ Figur gilt als „unbekannt"; kein Event nach außen.

### FIG-6 — Winkel
Aktueller Roh-Winkel der Figur, berechnet aus dem Vektor zwischen
Pattern-Schwerpunkt und dem Touchpunkt mit niedrigster Touch-`id`, gegen
die Bildschirm-Horizontale. Wertebereich 0–360°. Der Winkel ist
**ungefiltert** und **unquantisiert** — Hysterese und Stufen-Logik leben im
Router.

### FIG-7 — Rotation vs. Translation
Verschiebung des gesamten Pattern-Schwerpunkts ohne Drehung der Geometrie
zueinander ändert den Winkel nicht. Die Seite unterscheidet Rotation
(Punkte rotieren um gemeinsamen Schwerpunkt) und Translation (Schwerpunkt
verschiebt sich, relative Lage bleibt) durch kontinuierliche Verfolgung
der einzelnen Touchpunkte.

### FIG-8 — 1-Finger-Tap → Session-Ende
Erscheint genau ein Touchpunkt für mindestens 100 ms, während keine Figur
als präsent gilt, löst das ein Session-Ende für die zuletzt identifizierte
Figur aus. Während eine Figur präsent ist, werden zusätzliche einzelne
Finger ignoriert.

## 2. Events an den Router

### FIG-9 — Transport
Events gehen per HTTP POST an `<router_url>/event`, JSON-Body,
`Content-Type: application/json`.

### FIG-10 — Event-Schema
Drei Event-Typen, alle als Zustands-Aussage (idempotent):

```json
// Beim ersten sicheren Erkennen einer Figur — und bei Wechsel
// auf eine andere identifizierte Figur ohne vorheriges Session-Ende
{ "src": "<controller_id>", "ts": "<iso8601>",
  "type": "figure_detected",
  "figure_id": "<string>", "angle": 0 }

// Während die Figur präsent ist, gedrosselt
{ "src": "<controller_id>", "ts": "<iso8601>",
  "type": "angle_update",
  "figure_id": "<string>", "angle": 0 }

// Bei 1-Finger-Tap nach Session
{ "src": "<controller_id>", "ts": "<iso8601>",
  "type": "session_ended",
  "figure_id": "<string>", "reason": "user_tap" }
```

`angle` ist ein Wert zwischen 0 und 360.

### FIG-11 — Sende-Logik
- `figure_detected`: bei jedem Übergang „keine identifizierte Figur" →
  „identifizierte Figur", inklusive Wechsel auf eine andere `figure_id`.
  Der Router schließt daraus implizit auf einen Ersatz.
- `angle_update`: gedrosselt auf maximal **10 Hz** und nur, wenn der Winkel
  sich um mindestens **3°** gegenüber dem zuletzt gesendeten Wert
  verändert hat.
- `session_ended`: einmalig bei FIG-8.

Wenn eine identifizierte Figur „abwesend" wird (FIG-2), ohne dass FIG-8
ausgelöst hat, sendet die Seite **kein** Event — der Router hält den
letzten State, bis ein neues `figure_detected` oder ein `session_ended`
kommt.

### FIG-12 — Retry
Bei fehlgeschlagenem POST: bis zu **3 Wiederholungen** mit Backoff
200 ms / 1 s / 5 s. Danach Drop. Kein Persistenz-Puffer.

## 3. Visualisierung (V1-Test-Layout)

Solange die Seite standalone testbar ist und nicht in eine Buddy-URL
eingebettet wird, ist die Visualisierung Teil der Seite selbst. Diese
Anforderungen entfallen, sobald die Komponente in echte Buddy-URLs
eingebettet wird.

### FIG-13 — Zielfeld
Mittig auf der Seite ein gut sichtbares, gestricheltes Rechteck mit
Beschriftung **„Figur hier auflegen"**.

### FIG-14 — Roh-Datendarstellung
Live aktualisiert auf jeden Touch-Event:

- Liste der aktuellen Touchpunkte: `Punkt N: x=… y=…`
- Aktuell berechneter Winkel (sofern ≥ 2 Punkte)
- Aktuell erkannte `figure_id` oder „— unbekannt —"

### FIG-15 — Header
Banner oben: **„FIGUREN-ERKENNUNG · V1-TEST · `<controller_id>`"**.

### FIG-16 — Footer
- Letzter erfolgreicher POST + letzter Fehlschlag mit Zeitstempel
- Counter Events der letzten 60 s, aufgeschlüsselt nach Typ

## 4. Konfiguration

### FIG-17 — Konfigurationswerte
Statisch in der Seite (JS-Konstanten) oder als URL-Parameter überschreibbar:

| Parameter | Default |
|---|---|
| `controller_id` | URL-Parameter `?controller=<id>`; sonst `test_controller` |
| `router_url` | URL-Parameter `?router=<url>`; sonst leer → Events nur in `console.log` |
| `figure_present_ms` | 150 |
| `figure_absent_ms` | 400 |
| `pattern_tolerance` | 0.05 |
| `tap_dwell_ms` | 100 |
| `angle_update_max_hz` | 10 |
| `angle_update_min_delta_deg` | 3 |

## 5. HTML-Anforderungen

### FIG-18 — Querformat angenommen
Die Seite geht von Querformat-Layout aus (~640–900 px Breite,
~360–430 px Höhe). Sie sperrt selbst keine Rotation — das übernimmt später
die Controller-Runtime. Für V1-Tests im normalen Browser muss der Tester
das Phone im Querformat halten.

### FIG-19 — Selbsttragend
Keine externen Asset-Quellen. Layout über Inline-CSS, JS ohne externe
Bibliotheken.

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

Architektur-Entscheidungen aus der Session 2026-05-19, festgehalten an der
Spec, weil sie nicht aus dem Code ableitbar sind und für Folge-Tickets
load-bearing bleiben.

### E-FIG-1 — Logik in der Seite, nicht im Router
*Datum:* 2026-05-19

Frühe Variante: Controller streamt rohe Touch-Snapshots (30 Hz) an den
Router; Router rechnet alles (Erkennung, Winkel, Hysterese). **Verworfen**
wegen Skalierungsbedenken: bei mehreren parallel aktiven Controllern
entstehen schnell ≥100 Req/s nur an Telemetrie, und der Router müsste pro
Stream einen Tracker laufen lassen.

Stattdessen: die Seite erkennt Figur + Winkel lokal und sendet **nur
semantische Events**. Resultat ~1 Event/s während aktiver Drehung, Null im
Ruhezustand. Winkel-Hysterese und Quantisierung bleiben Router-seitig (pro
Buddy/Szene konfigurierbar) — diese Logik lebt aber nicht in dieser Spec.

### E-FIG-2 — Relative Winkelreferenz
*Datum:* 2026-05-19

Frühe Variante: absolute „Vorderseite" der Figur (Pfeil am Sockel) als
0°-Referenz. Erforderte rotations-asymmetrisches Muster, sonst kollidiert
0° mit 360°. **Verworfen** — Asymmetrie wäre eine harte Anforderung an das
Figuren-Design.

Stattdessen: Auflegen = Referenz (initialer Roh-Winkel). Die Seite verfolgt
nur Drehung relativ zum Anfangszustand. Symmetrie der Figur ist egal, weil
über die Zeit nachverfolgt wird, nicht aus dem Standbild abgeleitet.

### E-FIG-3 — Kein „Figur weg"-Event
*Datum:* 2026-05-19

Kapazitiv lässt sich „Figur abgehoben" nicht von „Figur losgelassen"
unterscheiden — sobald keine Erdung mehr besteht, verschwinden die
Touchpunkte. **Konsequenz:** Session endet ausschließlich über das aktive
1-Finger-Tap-Signal (FIG-8) oder das Erkennen einer anderen Figur.

Falls die Figur kommentarlos liegen bleibt, läuft das Display im letzten
Zustand weiter — der Router hält den State, bis ein neues Ereignis kommt.
Das ist by-design (siehe auch [Constitution: Qualitätsattribute, „Nicht-
invasiv"](../constitution.md)).

### E-FIG-4 — Eine HTML-Seite je Controller-Typ, nicht eine Runtime mit Plugins
*Datum:* 2026-05-19

Ein Handy-Controller zeigt je nach Szene eine von wenigen HTML-Seiten
(Eltern-Buttons, Kinder-Buttons, Figuren-Erkennung, …). Die alternative
Architektur — eine generische Controller-Runtime, in die Module gesteckt
werden — wurde verworfen, weil sie ohne klaren Mehrwert eine weitere
Indirection-Schicht bringt. Jede Controller-Variante ist einfach eine
eigene URL mit eigener Spec.
