# Geräte-Registry — Spec     (ID-Präfix: GER)

> ⚠️ **ENTFALLEN durch RAT-31 E6c (#1565), 2026-07-29.**
> Die Geräte-Registry (`geraete/`-Service, `geraete.json`, `GeraeteClient`)
> ist gelöscht. Es gibt **kein** Registry-Tracking der Geräte einer Familie
> mehr, keine gespeicherte Geräte-Identität/Verwendung/`paired_at`-Zuordnung.
> Das Setup ist fest **ein Gerät** (Heim-Shell); „Gerät koppeln" mintet nur
> noch einen Pairing-Link (`geraet-anlegen.md`), die Rolle (Kinder-Display vs.
> Elterngerät) wählt die Familie beim PWA-Installieren. Diese Spec beschreibt
> einen **nicht mehr lebenden Zustand**; sie bleibt als historischer Anker
> erhalten. Governance: `decisions/RAT-31-wirbelsaeule-abriss.md`, Epic #1339.
>
> Status: V1 (ENTFALLEN) · Refs #105 #1565

Die Geräte-Registry ist die **zentrale** Liste der Geräte einer Familie —
Tablets, Handys, Monitore und das Pi-Display. Sie ist die eine Quelle für
„welche Geräte gehören zu dieser Familie" und liefert je Gerät stabile
Identität, Typ, Auflösung, OS, Verwendungszweck und Status. Sie besitzt
diese Daten und stellt sie über eine Schnittstelle bereit; andere
Komponenten sind ihre Nutzer.

**V1-Scope:** Genau **Geräte-Identität** — die Geräte, je Gerät die
Eigenschaften aus GER-3. Die Geräte-Liste als Per-Instanz-Datei, eine
Lese- und eine Schreib-Schnittstelle, über die Konsumenten Geräte-Daten
abrufen und ergänzen.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): Geräte über
UI oder Eltern-Chat-Editor ändern oder löschen (V1: Datei + Schreib-
Schnittstelle, Anlage über GAA #106 — OPEN-GER-A) · Health-Monitoring /
Heartbeat (V1: `status` manuell gesetzt — OPEN-GER-B) · Telemetrie über
tatsächliche Nutzung (OPEN-GER-C).

## 1. Reichweite

### GER-1 — Eine Instanz, eine Geräte-Registry
Die Registry einer Instanz beschreibt genau die Geräte einer Familie —
der Familie des Hubs, auf dem die Instanz läuft. Es gibt keinen familien-
übergreifenden Bezeichner und keinen Cross-Familie-Zugriff. Konsistent
mit `familie.md` FAM-1 und `eltern-chat.md` EC-1.

*Tickets:* #105

### GER-2 — Geräte-Typen V1
Die Registry kennt vier Geräte-Typen:

| Typ          | Bedeutung                                                     |
|--------------|---------------------------------------------------------------|
| `tablet`     | Tragbares Touch-Display (Familien-Tablet, Plan-Buddy-Display) |
| `handy`      | Smartphone eines Familienmitglieds (üblicherweise Controller) |
| `monitor`    | Stationärer Bildschirm (z. B. an einem PC), wird als Display angesteuert |
| `pi-display` | Das am Hub-Pi direkt angeschlossene Display (Kiosk-Chromium)  |

Die Liste ist endlich; ein weiterer Geräte-Typ ist eine Spec-Änderung
(neue Zeile + eigenes Ticket), kein Config-Wert.

*Tickets:* #105

## 2. Geräte-Modell

### GER-3 — Eigenschaften eines Geräts
Jedes Gerät trägt:

| Feld          | Pflicht  | Werte                                                                | Bedeutung |
|---------------|----------|----------------------------------------------------------------------|-----------|
| `id`          | Pflicht  | stabile `display_id` (GER-7)                                          | Stabiler, eindeutiger Bezeichner. Wird nie neu vergeben. Dieselbe `id`, die Konsumenten (Router, Display-Client) referenzieren. |
| `typ`         | Pflicht  | einer aus GER-2                                                       | Geräte-Typ. |
| `name`        | Pflicht  | freier String                                                         | Anzeigename für Menschen (z. B. „Tablet Wohnzimmer"). |
| `aufloesung`  | Pflicht  | `{ "w": <int>, "h": <int> }` in Pixeln                                | Physische bzw. logische Bildschirm-Auflösung. Konsumenten skalieren darauf (z. B. Display-Client-Aspect-Adapter aus #107). |
| `os`          | Pflicht  | einer aus `android`/`ios`/`windows`/`macos`/`linux`/`unbekannt`       | Betriebssystem-Familie. Quelle für die CA-Anleitung pro Gerät (#82). |
| `verwendung`  | Pflicht  | einer aus `display`/`controller`/`beides`                             | Wofür wird das Gerät genutzt. |
| `status`      | Pflicht  | einer aus `aktiv`/`inaktiv`                                           | Soll-Zustand: ist das Gerät in Betrieb. V1 manuell gesetzt (OPEN-GER-B). |
| `paired_at`   | Optional | ISO-8601-Timestamp oder `null`                                        | Zeitpunkt des Auth-Pairings (Browser-Cookie gesetzt). `null` bei Anlage; wird vom `/auth/pair`-Endpoint (`specs/platform/auth.md` AUTH-2.a) gesetzt, sobald ein Browser den Pairing-Link öffnet und den `xbuddy_session`-Cookie annimmt. Quelle der Befüllung: GAA-3.8 (`specs/platform/geraet-anlegen.md`). [Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Konsequenz Phase 1" → „`paired_at`-Feld"] |

Die Geräte sind **Daten** und stehen vollständig in der Datei aus GER-4 —
nicht im Code (CLAUDE.md §6).

*Tickets:* #105

## 3. Datenhaltung & Schnittstelle

### GER-4 — Registry als Per-Instanz-Datei
Die Geräte-Liste liegt als JSON-Datei `geraete.json` neben dem Code, je
Instanz separat gepflegt und per `.gitignore` aus dem Repo ausgeschlossen
— analog `familie.json` (`familie.md` FAM-6) und `routing.json`
(`router.md` ROU-18). Die Datei trägt Eigentümer-Rechte `0600` und hebt
damit das Muster der Geheimnis-Datei (`zugangsdaten.md` ZD-3,
`eltern-chat-onboarding.md` ONB-5 / #103) für die Geräte-Daten auf — auch
wenn die Geräte-Felder keine Geheimnisse sind, sind sie familienprivat und
sollen denselben Eigentümer-Schutz haben. Eine `geraete.example.json`
dokumentiert das Format (kommt mit dem Impl-PR).

Fehlt die Datei beim Start, protokolliert das System eine Warnung und
läuft mit leerer Geräte-Liste weiter, statt abzubrechen (symmetrisch zu
FAM-6 / ROU-18). Konsumenten, deren Antwort von einem unbekannten Gerät
abhängt, behandeln das im eigenen Kontext (z. B. Display-Client zeigt
nach DC-8 einen Einrichtungs-Hinweis).

*Tickets:* #105

### GER-5 — Lese-Schnittstelle
Die Registry stellt die Geräte-Daten (GER-3) über eine Schnittstelle
bereit:

- ein Gerät je `id` holen,
- alle Geräte der Familie listen,
- nach `verwendung` filtern (Liste aller Display-Geräte / Controller-
  Geräte / „beides"-Geräte).

Konsumenten (Router, Display-Client, CA-Verteilung — GER-8) lesen die
Geräte-Daten **nur** über diese Schnittstelle, nicht über eigenen
Zugriff auf die Registry-Datei (CLAUDE.md §6: einseitige Abhängigkeiten —
die Registry besitzt die Daten, andere sind Nutzer). Analog `familie.md`
FAM-7. Schreiben erfolgt symmetrisch über GER-6.

*Tickets:* #105

### GER-6 — Schreib-Schnittstelle
Konsumenten legen Geräte an, ändern bestehende Felder oder deaktivieren
ein Gerät (`status` auf `inaktiv`) **nur** über die Schreib-Schnittstelle
der Registry, nicht über eigenen Zugriff auf die Registry-Datei —
symmetrisch zur Lese-Seite (GER-5) und im Sinne von CLAUDE.md §6 (die
Registry besitzt die Daten). Bestehende Geräte bleiben unberührt, außer
der Aufrufer ändert sie explizit. Beim Schreiben werden die Dateirechte
aus GER-4 (`0600`) durchgesetzt.

Schreibvorgänge sind **atomar** nach
[`conventions/data-components.md`](../../conventions/data-components.md)
**DCOMP-4** (Temp-Datei + Rename im Zielverzeichnis, sodass ein zeitgleicher
Lesezugriff nie eine halb geschriebene Datei sieht). Die Konvention ist
die eine Quelle für das Muster — diese Spec wiederholt es nicht mehr.

Schreib-Konsumenten in V1: `geraet-anlegen.md` (GAA, #106 — die Eltern-
Chat-Funktion „Gerät anlegen") und manuelle Datei-Pflege. Über HTTP ist
die Schreib-Schnittstelle als POST-Endpunkt erreichbar (GER-15) —
Konsumenten greifen nicht mehr über `import geraete` zu, sondern über
HTTP (DCOMP-1).

*Tickets:* #105, #212

### GER-7 — `display_id`-Vergabe
Die `id` eines Geräts ist seine **`display_id`** — derselbe Bezeichner,
über den Router (ROU-9/ROU-18) und Display-Client (DC-1) das Gerät heute
schon adressieren. Die `id` folgt IDENT-1
(`<typ>-<slug>-<nn>`, stabil, nicht neu vergeben).

Geräte-spezifisch zur allgemeinen Regel:

- `<typ>` ist genau einer aus GER-2 (`tablet`, `handy`, `monitor`,
  `pi-display`) — kein anderer Wert.
- `<slug>` ist kleingeschrieben, Bindestrich-getrennt, ohne
  Sonderzeichen (URL-6 sinngemäß — die `display_id` taucht in
  Display-URLs auf, vgl. ROU-20).
- `<nn>` beginnt je (Typ + Slug)-Kombination bei `01`.
- Kollisionsfreiheit prüft die Registry **je Familie** — eine `id`,
  die in dieser Instanz schon existiert, wird nicht erneut vergeben.

Beispiele: `tablet-elias-01`, `tablet-wohnzimmer-01`, `handy-mama-01`,
`pi-display-flur-01`.

*Tickets:* #105

### GER-8 — Konsumenten
Diese Spec benennt die heutigen Konsumenten der Registry. Die jeweiligen
Konsumenten-Specs ändern sich durch diesen PR nicht — sie ziehen ihre
Anbindung in eigenen Tickets nach:

- **Router** (`router.md`): `routing.json` (ROU-18) referenziert nur
  noch `display_id`s, die in der Registry stehen. Die Pflege der
  `display_id`s wandert damit aus „Strings in `routing.json`" in die
  Registry.
- **Display-Client** (`display-client.md`): Holt die Auflösung seines
  Geräts aus der Registry (per `display_id`, DC-1) und skaliert
  entsprechend (z. B. der Aspect-Adapter aus #107).
- **CA-Verteilung** (`ca-verteilung.md`, #82, geliefert via #95/#150/#106):
  Das Zielgerät (und sein `os`) kommt **pro Aufgabe vom Eltern-Chat-Agenten** —
  der Bot fragt „welches Gerät?" (EC-22) und übergibt es an
  `verteile_ca(…, geraet)`; CAV wählt den passenden OS-Anleitungsblock
  (CAV-5, hart-codiert). CAV liest die Registry **nicht** direkt (Modul-Grenze:
  CA-Verteilung wohnt im Eltern-Chat, greift nicht in die Geräte-Komponente).
  Die Registry bleibt SSoT dafür, *welche* Geräte existieren (GER-4); eine
  spätere Vorbelegung des Geräts aus der Registry wäre eine Optimierung ohne
  heutigen Schmerz (geparkt).

*Tickets:* #105

## 4. HTTP-API

### GER-13 — `GET /api/v1/geraete/` liefert alle Geräte
Die Geräte-Registry stellt ihre Lese-Schnittstelle (GER-5) als HTTP-
Endpunkt bereit: `GET /api/v1/geraete/` liefert alle Geräte der Familie
als JSON-Array — je Gerät die GER-3-Felder, in der Reihenfolge der
Registry-Datei (aktive UND inaktive Geräte; Konsumenten filtern, GER-5).
Der Endpunkt ist über die eine Origin erreichbar (`conventions/urls.md`
URL-14): nginx routet `/api/v1/geraete/` auf den Geräte-Prozess
(`xbuddy-geraete`, PORT-2 = 5040). Konsumenten reden ausschließlich über
HTTP, nicht über `import geraete` (`conventions/data-components.md`
DCOMP-1).

*Tickets:* #212

### GER-14 — `GET /api/v1/geraete/<id>` liefert ein Gerät je `display_id`
`GET /api/v1/geraete/<display_id>` liefert die GER-3-Felder genau eines
Geräts als JSON. Unbekannte `display_id`: 404 mit JSON-Fehler
`{"error": "unbekannte id"}` — kein 500, kein Stack-Trace.

Jeder Lesevorgang liest die Registry-Datei **frisch von Disk** (DCOMP-2
Reload-on-Read), damit Cross-Service-Schreibvorgänge (z. B. die GAA-
Skill-Anlage, #106) ohne Service-Restart sichtbar werden.

*Tickets:* #212

### GER-15 — `POST /api/v1/geraete/` legt ein Gerät an
`POST /api/v1/geraete/` mit JSON-Body
`{typ, name, aufloesung, os, verwendung, status?}` legt ein neues Gerät
an und liefert das angelegte Gerät als JSON inkl. vergebener
`display_id`.

- Pflichtfelder: `typ` (GER-2), `name` (nicht leer), `aufloesung`
  (`{w, h}` mit positiven Ganzzahlen, GER-3), `os` (GER-3), `verwendung`
  (GER-3).
- Optional: `status` (Default `aktiv`, GER-3).
- Die `display_id` vergibt der Server kollisionsfrei nach GER-7
  (`<typ>-<slug>-<nn>`, IDENT-1) — der Client liefert sie **nicht**.

Validierungsfehler (fehlendes Pflichtfeld, Wert außerhalb der GER-3-
Mengen) sind **400** mit JSON-Fehler. Disk-Schreibfehler (Datei nicht
schreibbar, DCOMP-4-Pfad scheitert) sind **503** mit JSON-Fehler — in
beiden Fällen bleibt die Registry-Datei unverändert.

Parallele POSTs werden serialisiert (Read-Modify-Write hinter einem
Schreib-Lock), damit zwei Threads zwei **verschiedene** `display_id`s
bekommen und beide Einträge in der Registry landen — kein verlorengehendes
Update. Geschrieben wird atomar nach DCOMP-4 (siehe GER-6).

*Tickets:* #212

## 5. Konfiguration

### GER-9 — Konfigurationswerte
Familienspezifische Werte leben in `geraete.json` (GER-4). Der Pfad zur
Registry-Datei selbst kann nicht in der Datei stehen und bleibt deshalb
Env/CLI. Die Tabelle folgt der Konfigurations-Konvention
[`conventions/config.md`](../../conventions/config.md) CONFIG-2: jeder
Wert hat einen Default und eine Quelle.

| Wert            | Default                       | Quelle                                            |
|-----------------|-------------------------------|---------------------------------------------------|
| Registry-Datei  | `geraete.json` neben dem Code | Env (`GERAETE_REGISTRY`) · CLI (`--geraete`)      |

*Tickets:* #105

## 6. Tests

### GER-10 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), ohne Netz. Mindest-Abdeckung:

- **GER-4** — fehlende Datei → Warnung, leere Geräte-Liste, kein Crash;
  Datei mit Geräten → alle Felder aus GER-3 geladen; Schreiben setzt
  `0600`.
- **GER-5** — Holen einer Person je `id`; unbekannte `id` liefert
  „nicht gefunden"; alle Geräte listen; Filter nach `verwendung`
  liefert nur die passenden Geräte.
- **GER-6** — atomares Schreiben: bestehende Geräte byte-gleich nach
  Schreiben eines neuen Geräts; simulierter Schreib-Abbruch hinterlässt
  keine halbe Datei; Deaktivieren ändert nur `status`.
- **GER-7** — Schema-Prüfung folgt IDENT-1. Geräte-spezifisch: `<typ>` ist genau
  einer aus GER-2 (kein anderer Wert); Kollisionsfreiheit prüft je
  Familie — eine in dieser Instanz bereits vergebene `id` wird nicht
  erneut vergeben; eine einmal vergebene `id` wird nicht neu vergeben.
- **GER-13** — `GET /api/v1/geraete/` liefert alle Geräte als JSON-Array
  (aktiv + inaktiv, GER-5).
- **GER-14** — `GET /api/v1/geraete/<id>` liefert das passende Gerät;
  unbekannte `id` ist 404.
- **GER-15** — POST mit gültigem Body liefert 200 + IDENT-1-`display_id`
  und persistiert atomar; POST ohne `name`/`typ`/Pflichtfeld ist 400;
  POST ohne konfigurierten Registry-Pfad (Test-Modus) ist 503; parallele
  POSTs ergeben zwei verschiedene `display_id`s (beide persistiert).

*Tickets:* #105, #212

---

## Offene Punkte

- **OPEN-GER-A — Geräte über UI/Eltern-Chat-Editor ändern oder löschen.**
  V1 hat die Schreib-Schnittstelle (GER-6) und die Anlage über die
  Eltern-Chat-Funktion `geraet-anlegen.md` (GAA, #106). Ein Editor —
  bestehende Geräte umbenennen, Auflösung korrigieren, ein Gerät hart
  löschen statt nur deaktivieren — ist V1 nicht spezifiziert. Korrekturen
  laufen V1 über manuelle Datei-Pflege. Kein V1-Bedarf belegt.

- **OPEN-GER-B — Health-Monitoring / Heartbeat.** Das Feld `status`
  (GER-3) wird V1 manuell gesetzt. Ob die Registry automatisch erkennt,
  dass ein Display seit einer Stunde keinen Stream-Reconnect mehr
  hatte, und dann `status` auf `inaktiv` setzt, ist offen — das wäre
  eine echte zweite Petrantwortung (Beobachtung statt nur Identität).
  Erst spezifizieren, wenn ein konkreter Schmerz auftaucht.

- **OPEN-GER-C — Telemetrie über tatsächliche Nutzung.** Welches Gerät
  wurde zuletzt wann benutzt, welche Inhalte hat es gezeigt — V1 nicht
  geführt. Sobald die Registry Nutzung kennt, ist sie kein reines
  Identitäts-Modell mehr; eigene Spec, sobald Bedarf belegt ist.

---

## Bezug

- **Analog-Vorlage:** `familie.md` (FAM-Registry-Pattern — Per-Instanz-
  Datei, Lese- und Schreib-Schnittstelle, atomares Schreiben).
- **Konsumenten:** `router.md` ROU-18 (`routing.json` referenziert
  `display_id`s); `display-client.md` DC-1 (`display_id` als Identität);
  `ca-verteilung.md` (#82, KI-generierte CA-Anleitung pro `os`).
- **Schreib-Pattern:** `zugangsdaten.md` ZD-3 (gitignorierte `0600`-
  Datei, atomares Schreiben).
- **Bestehender Ticket-Aufschlag:** #82 (Geräteprofil-CA) — wird auf
  diese Registry umgestellt, kein eigenes Geräte-Modell mehr.
- **Hängt an:** nichts. Andere Tickets hängen an dieser Spec
  (insbesondere #106 „Gerät anlegen", #82 „CA-Anleitung pro Gerät").
