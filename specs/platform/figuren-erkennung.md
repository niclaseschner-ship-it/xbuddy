# Figuren-Erkennung — Spec     (ID-Präfix: FIG)

> ⚠️ **ENTFALLEN durch RAT-31 E6f (#1568), 2026-07-29.**
> `controller/figuren-erkennung/` ist gelöscht. Der Phone-Controller-Prototyp
> sendete Events an den Router (`router.md`, ebenfalls ENTFALLEN); mit dem
> Router-Abriss und dem Ein-Gerät-Heim-Display (Heim-Shell PWA, `heim-shell.md`)
> gibt es keinen Konsumenten mehr. Diese Spec bleibt als historischer Anker
> erhalten.
> Governance: `decisions/RAT-31-wirbelsaeule-abriss.md`, Epic #1339.
>
> Status: V1 (ENTFALLEN) · Refs #1 #6 #1568

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

*Tickets:* #1, #11

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
Touchpunkt (`touches.size === 1`) für mindestens `tap_dwell_ms` (siehe
FIG-17) gehalten, sendet die Seite `session_ended` mit
`reason: "user_button"` und schließt die Session (`figurePresent` und
`identifiedFigureId` werden zurückgesetzt, der Button verschwindet).
Ein einzelner Touchpunkt **außerhalb** der Kreisfläche löst nichts aus.

Außerhalb einer aktiven Session ist der Button nicht sichtbar.

*Tickets:* #1, #13

### FIG-20 — Bucket-Quantisierung
Der kumulative Winkel (FIG-6) wird in `n_buckets` gleich breite Sektoren
à `bucket_size_deg` quantisiert. Der **aktuelle Bucket** ist
`floor(mod360(cum) / bucket_size_deg) mod n_buckets` und liegt im
geschlossenen Intervall `[0, n_buckets)`. Quantisierung passiert in der
Seite (figlib), nicht im Router — siehe E-FIG-7.

Default-Konfiguration (FIG-17): `n_buckets = 4`, `bucket_size_deg = 90`.
Die Werte müssen konsistent sein (`n_buckets * bucket_size_deg = 360`);
ist nur `n_buckets` gesetzt, wird `bucket_size_deg` als `360 / n_buckets`
abgeleitet.

*Tickets:* #11

### FIG-21 — Hysterese an Bucket-Grenzen
Der Wechsel auf einen Nachbar-Bucket findet erst statt, wenn der
kumulative Winkel die Bucket-Grenze um mindestens `bucket_hysteresis_deg`
überschreitet. Solange der Wert in der Hysterese-Zone um die Grenze
schwankt, bleibt der Bucket auf seinem letzten Wert stehen.

Konkret: gegeben aktueller Bucket `b` mit Mitte `m_b = (b + 0.5) *
bucket_size_deg`, wechselt der Bucket erst, wenn
`|mod360(cum) − m_b| > bucket_size_deg/2 + bucket_hysteresis_deg` mod-
korrekt um die 360°-Grenze gemessen. Default: `bucket_hysteresis_deg = 5`.

Bei Wechsel: neuer Bucket = der Sektor, in den der kumulative Winkel
jetzt fällt (unabhängig von der Richtung der Drehung). Damit kann ein
großer Sprung mehr als einen Bucket auf einmal überspringen — gewollt.

*Tickets:* #11

### FIG-22 — Initial-Bucket beim figure_detected
Beim `figure_detected` startet der kumulative Winkel bei 0 (FIG-6). Der
zugehörige Initial-Bucket ist deterministisch der Bucket, in den
`cum = 0` fällt — bei Default-Geometrie also Bucket **0** (Sektor
0°–90°). Der Wert wird im `figure_detected`-Event als `bucket: 0`
mitgesendet (FIG-10).

*Tickets:* #11

## 2. Events an den Router

### FIG-9 — Transport
Events gehen per HTTP POST an `<router_url>/api/v1/events`, JSON-Body,
`Content-Type: application/json`. Der Pfad `/api/v1/events` folgt der
URL-Konvention (siehe `conventions/urls.md`, URL-4) und ist die Gegenseite von
ROU-3 in `router.md`.

*Tickets:* #1, #24

### FIG-10 — Event-Schema
Drei Event-Typen, alle als Zustands-Aussage (idempotent). **Pflichtfelder
auf allen drei Event-Typen:** `source_id`, `ts`, `type`. Weitere Felder
sind event-spezifisch:

```json
// Beim ersten sicheren Erkennen einer Figur — und bei Wechsel auf eine
// andere identifizierte Figur ohne vorheriges Session-Ende
{ "source_id": "phone:test-1", "ts": "<iso8601>",
  "type": "figure_detected",
  "figure_id": "<string>", "angle": 0, "bucket": 0 }

// Während die Figur präsent ist, gedrosselt; angle ist die kumulierte
// Rotation seit figure_detected (siehe FIG-6, FIG-11), bucket ist der
// quantisierte und hysteretisch geglättete Sektor (siehe FIG-20/21)
{ "source_id": "phone:test-1", "ts": "<iso8601>",
  "type": "angle_update",
  "figure_id": "<string>", "angle": <float>, "bucket": <int> }

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

*Tickets:* #1, #6, #11

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
Retry- und Drop-Verhalten der Phone-Events folgt der Event-Transport-
Konvention `conventions/event-transport.md` (EVT-1 Retry-Backoff,
EVT-2 Drop nach N Versuchen, kein Persistenz-Puffer).

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
Live aktualisiert auf jeden Touch-Event und auf den periodischen Tick
(siehe Implementierung):

- Liste der aktuellen Touchpunkte: `Punkt N: x=… y=…`
- Aktueller Pattern-Descriptor `d` (sofern ≥ 3 Punkte)
- Aktueller Schwerpunkt `zent` (Pixel-Koordinaten)
- Status der räumlichen Punkt-Zuordnung des letzten Frames:
  `match: ok | fail | reanchor`
- Per-Frame-Winkeldelta `Δ` (Roh-Wert pro Tick, vor Akkumulation)
- Aktueller kumulativer Winkel `cum` (Session-Akku, FIG-6)
- Aktuell erkannte `figure_id` oder „— unbekannt —" (im Status-Block)

`match`, `Δ` und `zent` sind Diagnose-Felder, die die Funktionsweise der
räumlichen Punkt-Verfolgung (FIG-7) und der kumulativen Akkumulation
(FIG-6) am laufenden System sichtbar machen. Beim Real-Test 2026-05-20
waren sie der Schlüssel, um Bug-Ursachen vom korrekten Verhalten zu
unterscheiden.

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
Defaults stehen als JS-Konstanten in `figlib.js` und folgen der
Konfigurations-Konvention CONFIG-2: jeder Wert hat einen Default und einen
Datei-Schlüssel in `config.json` (FIG-23, im selben Verzeichnis wie die
Seite). Der Onboarding-Schritt, der einen Wert produktiv setzt, ist heute
noch nicht definiert — Phone-Controller werden in V1 manuell beim
Deployment befüllt; ein Eltern-Chat-Schritt für Phone-Controller-Setup
ist ein offener Punkt (siehe OPEN-FIG-D).

Dev-Override per URL-Parameter ist möglich (CONFIG-1: ENV/CLI/URL sind
Dev-Werkzeuge, nicht produktive Familien-Form) — Liste am Ende der Spec
unter „Dev-Anhang". Priorität bleibt **URL > config.json > Defaults**.

| Name                         | Default                          | Datei-Schlüssel              | gesetzt durch (Onboarding-Schritt) |
|------------------------------|----------------------------------|------------------------------|------------------------------------|
| `source_id`                  | `phone:test-1`                   | `source_id`                  | — (offen, OPEN-FIG-D)              |
| `router_url`                 | leer → Events nur in `console.log` | `router_url`               | — (offen, OPEN-FIG-D)              |
| `figure_present_ms`          | 150                              | `figure_present_ms`          | —                                  |
| `pattern_tolerance`          | 0.05                             | `pattern_tolerance`          | —                                  |
| `match_distance_px`          | 60                               | `match_distance_px`          | —                                  |
| `tap_dwell_ms`               | 30                               | `tap_dwell_ms`               | —                                  |
| `button_padding_px`          | 30                               | `button_padding_px`          | —                                  |
| `angle_update_max_hz`        | 10                               | `angle_update_max_hz`        | —                                  |
| `angle_update_min_delta_deg` | 3                                | `angle_update_min_delta_deg` | —                                  |
| `n_buckets`                  | 4                                | `n_buckets`                  | —                                  |
| `bucket_size_deg`            | 90 (abgeleitet aus `n_buckets`)  | `bucket_size_deg`            | —                                  |
| `bucket_hysteresis_deg`      | 5                                | `bucket_hysteresis_deg`      | —                                  |

`source_id` wird in jedes Event geschrieben (FIG-10). `match_distance_px`
ist die Schwelle für die räumliche Punkt-Zuordnung (FIG-7).
`button_padding_px` ist das „kleine Padding" aus FIG-8, das auf den Radius
des Centroid-Buttons addiert wird (Default 30 px → Button etwas größer als
die reine Standfläche der Figur).

`n_buckets`, `bucket_size_deg` und `bucket_hysteresis_deg` steuern die
Bucket-Quantisierung (FIG-20) und die Grenz-Hysterese (FIG-21). Wird nur
`n_buckets` gesetzt, ist `bucket_size_deg = 360 / n_buckets`.

`tap_dwell_ms` ist die Mindest-Halte-Zeit für den Session-Ende-Button
(FIG-8). Default 30 ms — kurz genug für einen natürlichen Tap,
lang genug um Streifkontakte zu filtern (siehe E-FIG-8).

*Tickets:* #1, #6, #9, #11, #13

### FIG-23 — Instanz-Konfiguration über `config.json`
Beim Laden der Seite wird `./config.json` per `fetch` geladen und auf die
Defaults aus FIG-17 angewendet. Damit liegen pro-Instanz-Werte
(`source_id`, `router_url`, Tuning-Werte, Registry) **als Daten neben
dem Code** — `figlib.js` bleibt reine Logik und ist über alle
Controller-Instanzen identisch.

**Format:** JSON-Objekt mit denselben Schlüsseln wie `configDefaults()`.
Nicht gesetzte Schlüssel bleiben auf dem Default. Beispiel:

```json
{
  "source_id": "phone:wohnzimmer",
  "router_url": "https://hub.local",
  "pattern_tolerance": 0.04,
  "match_distance_px": 200,
  "n_buckets": 4,
  "bucket_hysteresis_deg": 5,
  "registry": {
    "gelbes-e": [0.650, 0.956, 1.0]
  }
}
```

**Fehlerfälle:** folgen `conventions/config.md` CONFIG-4 (fehlende oder
kaputte Datei → Defaults + Warnung, Prozess startet weiter).

**Priorität:** URL-Parameter (siehe FIG-17) überschreiben weiterhin
auch `config.json`. Reihenfolge: `Defaults` → `config.json` → URL.

**Selbsttragend (FIG-19):** Die Datei liegt im selben Verzeichnis wie
`index.html` und `figlib.js` und wird mit ausgeliefert. Pro Controller-
Instanz wird sie separat verwaltet (nicht alle Instanzen im Repo,
sondern beim Deployment der jeweiligen URL erzeugt).

**Kopplung zum Router:** `router_url` ist die Origin des Routers
(Schema + Host[:Port], **ohne Pfad**) — `figlib.js` hängt den Endpunkt
`/api/v1/events` selbst an (FIG-9). `source_id` muss mit dem
`source_id`-Wert eines Eintrags der Routing-Tabelle (ROU-18)
übereinstimmen, sonst greift kein Match (ROU-9).

*Tickets:* #11, #72

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
Inline-CSS, der begleitenden JS-Datei `figlib.js` und optional einer
Instanz-Konfiguration `config.json` (FIG-23) — alles im selben
Verzeichnis, zusammen ausgeliefert, nach erstem Laden offline-fähig.
Die PWA-Begleitdateien (FIG-24) zählen ebenfalls zum selbsttragenden
Auslieferungspaket.

*Tickets:* #1, #11, #18

### FIG-24 — Auslieferung als installierbare PWA
Die Seite wird zusätzlich zur reinen URL-Nutzung als installierbare
Web-App ausgeliefert. PWA ist **eine** Auslieferungsform unter mehreren
denkbaren (z. B. eingebettet in eine künftige Buddy-Runtime) — die
aktuell verfolgte. Pflicht-Dateien, Manifest-Pflichtfelder und die
Config-Lade-Reihenfolge folgen der PWA-Konvention
`conventions/pwa.md` (PWA-1 bis PWA-4) — Controller-Klauseln.

Komponentenspezifische Ergänzungen über die Konvention hinaus:

- Manifest-Feld `orientation: "landscape"` (Querformat passt zur
  Phone-Auflage-Geometrie, FIG-18); `background_color`/`theme_color`
  passen zum dunklen UI-Stil aus dem FIG-15-Abschnitt.
- **Auslieferungs-Strategie des Service Workers: netzwerk-bevorzugt mit
  Cache-Fallback** für alle GET-Requests. Ist das Netz erreichbar, liefert
  der Worker die frische Version und aktualisiert den Cache; ist es nicht
  erreichbar, liefert er aus dem Cache. Damit ist ein Deployment beim
  nächsten Laden **sofort sichtbar** — eine reine Cache-First-Strategie
  würde alte Stände bis zum Cache-Bruch ausliefern und jeden Deploy
  verschlucken. PWA-1 nennt nur den Install-Cache; die Liefer-Strategie
  ist Phone-spezifisch.
- `config.json` (FIG-23) folgt derselben Netzwerk-bevorzugt-Regel — sie
  ist per-Instanz-Daten und darf sich pro Deployment ändern.
- Router-Events (POST) laufen nie über den Worker-Cache.

*Tickets:* #18, #23, #26

### FIG-25 — Vollbild im installierten Zustand
Wird die Seite über das Manifest aus FIG-24 als App installiert (iPadOS
"Zum Home-Bildschirm", Android/Chrome "Installieren"), läuft sie ohne
Browser-Chrome (keine Adressleiste, keine Tab-Bar) im Vollbild. Die
bereits vorhandenen Apple-Web-App-Meta-Tags (`apple-mobile-web-app-capable`,
`apple-mobile-web-app-status-bar-style`, `viewport-fit=cover`) bleiben
erhalten und ergänzen das Manifest für iPadOS, das den Anzeigemodus
nicht über das Manifest-`display`-Feld, sondern über diese Tags
interpretiert.

*Tickets:* #18, #26

### FIG-26 — Vollbild + Wach-Halten per Tap
Wake-Lock-Anforderung und Fullscreen-API beim ersten User-Gesture
folgen der PWA-Konvention `conventions/pwa.md` PWA-3 (best-effort,
kein Blockieren bei fehlender API).

FIG-26 ergänzt FIG-24/25: die PWA-Auslieferung bleibt für den
Eigengeräte-Fall gültig, FIG-26 macht Vollbild und Display-an aber
auch ohne Installation verfügbar — relevant für ein dediziertes
Tablet, das die Seite einfach als URL bzw. Home-Screen-Verknüpfung
öffnet.

*Tickets:* #20

---

## Offene Punkte

- **OPEN-FIG-B** — Wie kommt eine neue Figur in die Registry
  (Onboarding-Flow)? V1 fest verdrahtet, V2 als eigene Spec. Wo lebt die
  zentrale Registry langfristig — Hub, Cloud, eigener Service?
- **OPEN-FIG-C** — Konkreter Test-Endpoint für POSTs in V1: Router-Stub,
  Echo-Server oder reine `console.log`? Entscheidung beim
  Implementierungs-Ticket.
- **OPEN-FIG-D** — Onboarding-Schritt für Phone-Controller-Setup. Die
  CONFIG-2-Tabelle in FIG-17 hat heute keine Onboarding-Schritte für
  `source_id` und `router_url` — Phone-Controller werden in V1 manuell
  beim Deployment befüllt. Sobald Phone-Controller über den Eltern-Chat
  eingerichtet werden können (analog der Funktions-Spec
  `familie-anlegen.md`), bekommt jede Zeile der FIG-17-Tabelle einen
  konkreten Schritt-Namen.

---

## Dev-Anhang — URL-Parameter (Dev-Override)

Nach CONFIG-1 sind URL-Parameter ein **Dev-Override**, nicht die
produktive Familien-Form. Die folgenden Parameter überschreiben für
die laufende Seiten-Session die Werte aus `config.json` (FIG-23) bzw.
die Code-Defaults:

| URL-Param         | überschreibt                 |
|-------------------|------------------------------|
| `?source=<id>`    | `source_id`                  |
| `?router=<url>`   | `router_url`                 |
| `?tol=<float>`    | `pattern_tolerance`          |
| `?rate=<int>`     | `angle_update_max_hz`        |
| `?dead=<float>`   | `angle_update_min_delta_deg` |

Priorität: **URL > config.json > Defaults**.

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

### E-FIG-6 — Descriptor (FIG-3) durch Realtest bestätigt
*Datum:* 2026-05-20 (Ticket #9)

Frühere offene Frage (OPEN-FIG-A): Sind „normalisierte sortierte
Seitenlängen" (FIG-3) als Pattern-Descriptor robust genug, oder braucht
es einen reicheren Deskriptor (z. B. Innenwinkel zusätzlich)?

Der Real-Test am echten Phone 2026-05-20 hat das mit echten 3-Bump-
Figuren bestätigt: Identifikation funktioniert stabil, der Descriptor
ist im aktuellen Demo-Set ausreichend trennscharf. Ein reicherer
Deskriptor wird nicht eingeführt. Sollten in Zukunft Figuren mit
zueinander symmetrischen oder nahezu identischen Form-Verhältnissen
hinzukommen, wird das punktuell mit einem neuen Ticket erneut bewertet.

### E-FIG-7 — Bucket-Quantisierung in der Seite, nicht im Router
*Datum:* 2026-05-20 (Ticket #11)

E-FIG-1 hat die semantische Reduktion (rohe Touch-Snapshots → semantische
Events) klar in die Seite gelegt, ließ aber explizit offen, wo
**Winkel-Hysterese und Quantisierung** stattfinden — Router-seitig „pro
Buddy/Szene konfigurierbar" war damals der Zielzustand.

Die folgende Session hat das umgekehrt: Quantisierung und
Grenz-Hysterese gehören in dieselbe Schicht wie der kumulative Winkel.

**Begründung:**

1. Die Phone-Seite kennt den kumulativen Winkel ohnehin und kann die
   Bucket-Logik mit einer Handvoll Zeilen mitführen — der Router müsste
   denselben Zustand zweimal halten (Akku + letzter Bucket pro Session).
2. Das Event-Schema (FIG-10) trägt jetzt `bucket` als integrales Feld;
   wer das Event konsumiert, muss nicht selbst Hysterese rechnen. Damit
   wird der Router zu einem reinen Dispatcher: 1:1-Mapping von
   `(figure_id, bucket)` auf Szene/View, ohne eigene Stufenlogik
   (Ticket #5 ROU-6).
3. Beim Test 2026-05-20 hat sich gezeigt, dass die Geometrie der
   Quantisierung (4 × 90° vs. n × m°) eine Eigenschaft des
   **Controllers** ist — sie hängt an der physischen Drehgeometrie der
   Figur, nicht am Display, das das Ergebnis später anzeigt.

Folgewirkung: Ticket #5 hat ROU-7/ROU-8 (Router-seitige Hysterese und
Quantisierung) gestrichen; OPEN-ROU-A entfällt.

### E-FIG-8 — Tap-Dwell statt Tap-Release (Bug #13)
*Datum:* 2026-05-20 (Ticket #13)

Real-Test 2026-05-20: Der Centroid-Button (FIG-8) reagierte nicht auf
natürliche Taps. Ursache: `tap_dwell_ms` lag bei 100 ms; ein normaler
Tap dauert oft nur 50–80 ms. Der Touch verschwand bevor die
Dwell-Schwelle erreicht war — strikt spec-konform, aber UX-kaputt.

Drei Optionen waren in der Diskussion:

| Variante | Mechanik |
|---|---|
| **A** | `tap_dwell_ms`-Default von 100 auf 30 ms senken |
| **B** | Auf `touchend` innerhalb des Kreises feuern, unabhängig von der Halte-Zeit |
| **C** | Visuelles Feedback (Fortschritts-Ring) während Dwell |

**Gewählt: A.** Begründung: B würde die Mechanik aufweichen — bei zwei
nahezu gleichzeitigen Touches (eine Hand am Display, dann zweite) wäre
ein versehentliches `touchend` ohne klare Absicht im Kreis möglich.
A bleibt bei "halten = Absicht", aber kurz genug für einen natürlichen
Tap. C ist eine UX-Verbesserung, kein Bugfix — separates Ticket wenn
gewünscht.

30 ms wurde gewählt, weil der periodische Tick alle 50 ms läuft —
mindestens ein Tick passt zuverlässig in 30 ms hinein, sobald der
Touch beim ersten Tick erfasst ist. 100 ms war für die Original-
Spec-Sicherheit „kein Streifkontakt" gewählt, ist aber bei einem
Button, der durch die Figur physisch verdeckt liegt (FIG-8) unnötig
defensiv: ein Versehen ist schon durch die räumliche Verdeckung
ausgeschlossen.
