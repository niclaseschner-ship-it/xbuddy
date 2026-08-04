# Photo-Buddy — Spec     (ID-Präfix: PHOTO)

> Status: V1 (Entwurf, Gate A freigegeben Nic 2026-06-06) · Slug `photo`

## Problem & North-Star-Bezug

Kinder haben keinen eigenen, selbstbestimmten Zugang zu ihren wichtigsten
Familienfotos — Eltern müssen das Handy zücken und durchwischen. Der Photo-Buddy
gibt dem Kind einen **digitalen Bilderrahmen, den es selbst bedient**: Fotos (und
kurze Videos) laufen automatisch durch, das Kind kann blättern, anhalten und in
einer Übersicht ein bestimmtes Bild suchen. Eltern füttern die Bibliothek
**niedrigschwellig über den Eltern-Chat** (Foto/Video schicken → erscheint).

North Star: eine Eltern-Aufgabe (Fotos zeigen) wandert zum Kind; das Kind bekommt
selbstbestimmten Zugang zu seinen eigenen Erinnerungen, im Rahmen, den die Eltern
durch die Auswahl der Bilder setzen. Als App **besitzt** der Photo-Buddy seine
**Daten** (die Medien-Library), seine **Funktion** (Ingest, Normalisierung,
Durchlauf) und stellt das Ergebnis über die **Display-View** bereit (APP-1).

**V1-Scope:** Single-Page-View `rahmen` (helle DS-Linen-Stage, ein Medium als
gerahmte Karte zentriert) · Auto-Durchlauf mit konfigurierbarem Intervall · **interaktiv**:
Pfeile prev/next + Pause/Play + Übersichts-Modus (scrollbares Thumbnail-Grid, Tap →
zurück aufs Medium) · eigene **Familien-Library** auf der Pi · Fotos **und kurze
Videos** · **volle API interface-first** (Ingest multipart + Liste + Einzelmedium +
Thumbnail + Löschen) · defensive Normalisierung (HEIC→JPEG, HEVC/MOV→MP4/H.264) +
Thumbnail/Poster-Frame beim Ingest · Sortier-Achsen als Config (Richtung ×
Stempel-Quelle) · optionales Auto-Delete (TTL) · Pi-lokal, kein Cloud-Egress.

**Out-of-Scope V1** (je eigenes Ticket): der **Eltern-Chat-Ingest-Skill selbst**
(nachgezogen, ruft die hier exponierte API — **DIE NAHT**, OPEN-PHOTO-A) ·
Eltern-Chat-Konfiguration von Sortierung/TTL (OPEN-PHOTO-B) · Per-Kind-Libraries /
figure_id-Routing (OPEN-PHOTO-C) · Google-Photos / externe Bibliotheken-Sync
(OPEN-PHOTO-D) · Ton in der Slideshow (OPEN-PHOTO-K).

## 1. Die App & ihre View

### PHOTO-1 — Photo-Buddy ist eine App mit eigenem Besitz
Der Photo-Buddy ist die XBuddy-App mit dem Buddy-Slug `photo`. Er besitzt seine
**Daten** (die Medien-Library, PHOTO-7), seine **Funktion** (Ingest und
Normalisierung Abschnitt 4, Durchlauf Abschnitt 1) und stellt das Ergebnis über
seine **Display-View** bereit (APP-1).

### PHOTO-2 — Single-Page-View `rahmen`, helle DS-Linen-Stage
Die View liegt unter `/display/photo/rahmen` (URL-2, URL-7) und ist eine einzige
Canvas mit **maximalem Fokus auf dem Medium**: heller DS-Linen-Hintergrund (`--bg`),
das Medium als **gerahmte Karte** (Surface, weiche Rundung + Schatten) zentriert,
minimale Bedien-Elemente (PHOTO-4). Kein Tab, kein Settings-Panel, **keine
Bildunterschrift, kein Zähler** (Gate B, E-PHOTO-11).

### PHOTO-3 — Auto-Durchlauf
Die Medien wechseln in einem **konfigurierbaren Intervall** (PHOTO-19)
automatisch. Ist das aktuelle Medium ein Video, läuft es **stumm** ab (PHOTO-6)
und der Durchlauf blättert nach Video-Ende weiter; das Intervall wirkt als
Obergrenze (langes Video wird vom Cap nicht hart abgeschnitten — V1 begrenzt die
Video-Dauer ohnehin, PHOTO-19/OPEN-PHOTO-J).

### PHOTO-4 — Navigation: interaktiv (Abgrenzung zum statischen Kiosk)
Die View trägt **bewusste Bedien-Elemente**: Pfeil **links/rechts** blättert
zum vorigen/nächsten Medium (Wrap-around am Anfang/Ende), ein **Pause/Play**-Toggle
hält den Durchlauf an und startet ihn wieder. Damit ist der Photo-Buddy
**interaktiv** — anders als der statische Wetter-/Plan-Kiosk (WETTER-3) — weil das
Kind sein eigenes Anschauen selbst steuern soll (E-PHOTO-4).

### PHOTO-5 — Übersichts-Modus: scrollbares Thumbnail-Grid
Ein Button öffnet im selben View ein **scrollbares Thumbnail-Grid** aller Medien
(PHOTO-9). Ein Tap auf ein Thumbnail kehrt in die Einzelansicht **auf genau dieses
Medium** zurück. Im Übersichts-Modus **pausiert der Durchlauf**. Video-Thumbnails
tragen ein **Play-Icon-Overlay**, damit Bewegtbild erkennbar ist. Der
Übersichts-Modus ist ein **In-View-Zustand** (kein Seiten-Reload; der
Slideshow-Zustand bleibt erhalten, E-PHOTO-10).

### PHOTO-6 — Video stumm in der Slideshow; leere Library → neutraler Zustand
Videos laufen in der Slideshow **stumm** (Browser-Autoplay-sicher; Ton ist
V1-Out-of-Scope, OPEN-PHOTO-K). Ist die Library leer oder ein Medium nicht ladbar,
zeigt die View einen **neutralen Zustand** (freundlicher Platzhalter „Noch keine
Fotos") — nie ein roher Fehler oder ein leerer Schirm ohne Hinweis vor dem
Kind (analog WETTER-17/PLAN-20), und bleibt an.

## 2. Datenhaltung & Library

### PHOTO-7 — Eigene Medien-Library (Per-Instanz-Daten)
Die Library liegt in einem **Verzeichnis neben dem Code** (gitignored, Muster
FAM-9) mit einem Index `library.json`. Je Medium trägt der Index mindestens:
`id`, Dateiname (normalisiert), `typ` (`foto` | `video`), **Hinzufüge-Stempel**,
**Aufnahme-Stempel** (aus EXIF/Container-Metadaten, falls vorhanden) und — bei
Video — `dauer`. Die Library ist Per-Instanz-Daten, kein Code.

### PHOTO-8 — Defensive Normalisierung beim Ingest
Eingehende Medien werden in ein **web-anzeigbares Format** überführt:
**Foto → JPEG**, **Video → MP4/H.264**. Die Normalisierung ist *verify-and-convert-
if-needed*: bereits web-taugliche Eingaben (Telegram-Kompressions-Pfad, der Fotos
serverseitig zu JPEG und Videos zu MP4 re-encodiert) werden **erkannt und
durchgereicht**; nur Originalformate aus dem „als Datei/Dokument"-Pfad (iPhone
**HEIC** / **HEVC/MOV**) werden konvertiert (E-PHOTO-9). Das **Aufnahmedatum**
(EXIF beim Foto, Container-Metadaten beim Video) wird **vor** der Konvertierung
extrahiert und im Index gespeichert (PHOTO-7), bevor es verloren geht.

### PHOTO-9 — Thumbnail / Poster-Frame beim Ingest
Für den Übersichts-Modus (PHOTO-5) wird beim Ingest ein **Thumbnail** erzeugt:
bei Fotos ein verkleinertes Bild, bei Videos ein **Poster-Frame** (repräsentativer
Einzelframe). Das Thumbnail wird neben dem Vollmedium abgelegt.

### PHOTO-10 — Atomares Schreiben
Vollmedium + Thumbnail + Index-Eintrag werden **zusammen atomar** geschrieben
(DCOMP-4, Muster FAM-11/FAM-13): scheitert ein Teilschritt, bleibt **weder** ein
halb geschriebenes Medium **noch** ein verwaister Index-Eintrag zurück. Löschen
(PHOTO-16) entfernt die drei Teile genauso atomar.

## 3. Reihenfolge & Auto-Delete (Config / Familie-3-Probe)

### PHOTO-11 — Durchlauf-Reihenfolge konfigurierbar
Die Reihenfolge ist über zwei Achsen konfigurierbar (PHOTO-19): **Richtung**
(`neueste-zuerst` | `älteste-zuerst`) × **Stempel-Quelle** (`hinzugefügt` |
`aufgenommen`). Fehlt bei `aufgenommen` der EXIF-/Container-Stempel, fällt das
Medium auf den **Hinzufüge-Stempel** zurück. **Default: `neueste-zuerst` nach
`hinzugefügt`** (E-PHOTO-8). Die Reihenfolge ist der Musterfall der
Familie-3-Probe: was sich je Familie ändert, ist Config, nicht Code.

### PHOTO-12 — Auto-Delete nach TTL (optional, Default AUS)
Ist eine **TTL** (X Tage) gesetzt, entfernt der Photo-Buddy Medien, die länger als
X Tage **am Hinzufüge-Stempel** in der Library sind — Datei + Thumbnail + Index
(PHOTO-10/16). **Default ist AUS** (keine TTL → nie automatisch löschen,
E-PHOTO-6). Die Zeitquelle ist ein **injizierbares `now`** (Test-Determinismus,
PHOTO-23) — nie eine Wall-Clock tief im Code.

## 4. Schnittstelle API (interface-first)

> Die API ist V1-Bestandteil (E-PHOTO-2): die **Read-API** hat die Display-View
> als Konsument, die **Write-API** den committeten — nur nachgezogenen —
> Eltern-Chat-Ingest-Skill (OPEN-PHOTO-A). Kein Vorrat im Sinne von E-WETTER-3.
> Pfade folgen URL-4 (`/api/v1/<resource>`, Collection Plural).

### PHOTO-13 — Ingest: Medium aufnehmen
`POST /api/v1/photo/medien` nimmt ein Foto **oder ein kurzes Video** als
`multipart/form-data` (Form-Feld `medium`) entgegen — **Muster FAM-13**. Wirkung:
das Medium wird normalisiert (PHOTO-8), ein Thumbnail/Poster-Frame erzeugt
(PHOTO-9) und alles atomar (PHOTO-10) in die Library geschrieben. Antwort:
`{"id": ..., "typ": ...}`. **Dies ist der Endpunkt, den der spätere
Eltern-Chat-Ingest-Skill über das kanonische HTTP-`tool_use`-Modell ruft (RAT-3,
keine MCP-Schicht).** Überschreitet ein Video die konfigurierte Maximaldauer/-größe
(PHOTO-19/OPEN-PHOTO-J), wird es mit einem klaren Fehler abgelehnt.

Photo-Buddy ist Familien-Album-Bounded-Context und hält ausschließlich
Familien-Album-Inhalte. Fremde Foto-Sorten (z.B. Essens-Katalog-Assets) gehören
in den jeweiligen Owner-Buddy (siehe `conventions/medien-store.md` und
ESSEN-22 V1.2). Das in T799 vorübergehend eingeführte `in_library`-Feld
entfällt mit V1.2 — der Lego-Schnitt erfolgt jetzt über Daten-Eigentum
pro Buddy, nicht über Flag-Unterscheidung im Photo-Buddy.

### PHOTO-14 — Liste: Library-Metadaten
`GET /api/v1/photo/medien` liefert die Library-Metadaten (IDs, `typ`, Stempel,
`dauer`) **geordnet nach PHOTO-11** — die Datenquelle der View.

### PHOTO-15 — Einzelmedium & Thumbnail
`GET /api/v1/photo/medien/<id>` liefert das Vollmedium (JPEG oder MP4) mit
korrektem `Content-Type`; `GET /api/v1/photo/medien/<id>/thumbnail` liefert das
Thumbnail/den Poster-Frame (Muster FAM-8).

### PHOTO-16 — Löschen
`DELETE /api/v1/photo/medien/<id>` entfernt Vollmedium + Thumbnail + Index-Eintrag
atomar (PHOTO-10). Intern von Auto-Delete (PHOTO-12) genutzt, extern für Pflege
exponiert.

## 5. Iconografie & Gestaltung

### PHOTO-17 — Schlichte Fokus-UI, feste Bedien-Anordnung
Maximaler Fokus auf dem Medium: heller DS-Linen-Hintergrund, gerahmtes Medium
zentriert. Bedien-Elemente als **funktionale Symbole** (Lucide — UI-Verben über
Lucide, analog WETTER-18; **kein ARASAAC**, da reine Bedien-Verben, **kein Emoji**),
**kindgerecht große** Touch-Targets, **feste Anordnung** (Gate B, E-PHOTO-11):
**Pfeile prev/next mittig an den Seiten**, **Übersicht/Grid oben-rechts**,
**Pause/Play unten-rechts**. Keine Bildunterschrift.

### PHOTO-18 — Visueller Stil aus dem geteilten Design System
Der Stil bindet an das geteilte Design System
(`display/_shared/design/tokens.css`, `conventions/design-tokens.md` DTOK-1..5):
**keine hartcodierten Farben** in der View; Stilwerte als Token (Layout-`px` ok).
Die View ist **voll DS-konform** — heller Linen-Hintergrund, Medium als Surface-Karte
mit DS-Radius/Schatten (Gate B, E-PHOTO-11); **kein reines Schwarz/Weiß** (DS-Regel
tokens.css). Gegen die bestehende Buddy-Card geerdet
(`wetter/static/wetter.css` `.card`).

## 6. Konfiguration

### PHOTO-19 — Konfigurationswerte
Zwei Per-Instanz-Dateien neben dem Code (CONFIG-1), beide gitignored:

- `photo/photo.json` — **Daten-/Verhaltens-Konfig.** Format: `photo/photo.example.json`.
- `photo/config.json` — **Runtime-Konfig** (Bind, Log), via `tools/configloader.py`.

| Name                  | Default              | Datei-Schlüssel       | Gesetzt durch |
|-----------------------|----------------------|-----------------------|---------------|
| Durchlauf-Intervall   | `8s`                 | `intervall_s`         | n/a |
| Sortier-Richtung      | `neueste-zuerst`     | `sortier_richtung`    | Familie (V1 in Datei) |
| Stempel-Quelle        | `hinzugefügt`        | `stempel_quelle`      | Familie (V1 in Datei) |
| Auto-Delete-TTL       | `aus` (keine TTL)    | `auto_delete_tage`    | Familie (V1 in Datei) |
| Max. Video-Dauer      | `60s` (OPEN-PHOTO-J) | `video_max_s`         | n/a |
| Library-Verzeichnis   | `medien/` neben Code | `library_verzeichnis` | n/a (Default reicht) |
| Listen-Host           | `127.0.0.1`          | `listen_host`         | n/a |
| Listen-Port           | `5051` (PHOTO-20)    | `listen_port`         | n/a |
| Log-Level             | `INFO`               | `log_level`           | n/a |

Sortierung und TTL sind der Familie-3-Fall (Config, nicht Code, E-PHOTO-8). V1
setzt sie per Datei; der **Eltern-Chat-Konfig-Pfad** („später konfigurierbar")
ist nachgezogen (OPEN-PHOTO-B).

## 7. Service & Registrierung

### PHOTO-20 — Eigener Service, fester Port
Der Photo-Buddy läuft als eigener Prozess `xbuddy-photo.service` (SVC-1..4,
Service-Datei im Repo, `Restart=on-failure`, Logs an stdout/stderr) und bindet nur
an `127.0.0.1` (PORT-3). Port **5051** (PORT-2, erster freier im Block 5050–5099 —
**5050 ist vom Routine-Buddy belegt**, ROUTINE-15/#335; zu belegen als
`xbuddy-photo` in `conventions/ports.md`).

### PHOTO-21 — Registrierung in der Plattform
Der Slug `photo` wird im Origin-Routing (URL-14) registriert: `/display/photo/`
(Display-View) und `/api/v1/photo/` (Backend). Diese Verkabelung ist
**Integration**, nicht App-Eigentum — Gegenstand des arbeitstag-Track-Schnitts
(F4/F5).

### PHOTO-22 — Familien-Schnittstelle-Beitrag (APP-4)
V1 **exponiert** den Ingest-Endpunkt (PHOTO-13), **baut aber den
Eltern-Chat-Ingest-Skill nicht** — der ist nachgezogen (OPEN-PHOTO-A, DIE NAHT).
Damit berührt der Photo-Buddy den offenen App-Installations-Mechanismus (#296)
**nur über die spätere Skill-Anbindung, nicht über die hier gebaute API** — das ist
die interface-first-Entschärfung (E-PHOTO-2). *Hinweis:* Der Photo-Buddy ist der
**erste Buddy mit einem Eltern-Chat-Schreibpfad-Beitrag**; die Naht (OPEN-PHOTO-A)
ist nie zuvor durch den Bau-Prozess gelaufen — beim Anschluss nicht als gelöst
behandeln.

## 8. Tests

### PHOTO-23 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test (CLAUDE.md §6),
reproduzierbar und **ohne Netz**. Mindest-Abdeckung: PHOTO-8 (HEIC→JPEG und
HEVC/MOV→MP4 konvertiert; bereits web-taugliche Eingabe wird durchgereicht;
Aufnahmedatum extrahiert) · PHOTO-9 (Thumbnail bei Foto, Poster-Frame bei Video) ·
PHOTO-10 (Teil-Fehler beim Ingest → weder Medium noch Index-Eintrag) · PHOTO-11
(alle vier Richtung×Stempel-Kombinationen; fehlender Aufnahme-Stempel → Fallback
auf Hinzufüge-Stempel) · PHOTO-12 (Auto-Delete mit injiziertem `now`: vor TTL
bleibt, nach TTL entfernt; Default AUS löscht nie) · PHOTO-5 (Übersicht →
Einzelansicht kehrt auf dasselbe Medium zurück) · PHOTO-6 (leere Library →
neutraler Zustand) · PHOTO-13 (Video über Maximaldauer → Ablehnung). Läufe gegen
echte Telegram-/Geräte-Eingänge sind nicht Teil der automatisierten Suite.

---

## Offene Punkte

- **OPEN-PHOTO-A — Eltern-Chat-Ingest-Skill (DIE NAHT).** Nachgezogenes Ticket:
  ein Eltern-Chat-Skill nimmt ein in der Familien-Gruppe gesendetes Foto/Video
  entgegen und ruft PHOTO-13 über das kanonische HTTP-`tool_use`-Modell (RAT-3).
  Hängt am App-Installations-Mechanismus (#296, geschlossen/aufgelöst). **Werft-Grenze:
  der erste Buddy mit Eltern-Chat-Schreibpfad — hier bricht der Bau-Prozess am
  ehesten, nicht als gelöst behandeln.** Spec/Ticket: `platform/foto-senden.md`
  (FSE), #393.
- **OPEN-PHOTO-B — Eltern-Chat-Konfiguration** (Sortierung/TTL „später
  konfigurierbar"): nachgezogen, voraussichtlich analog RAT-2 (Link zu einer
  eltern-seitigen, mobil-tauglichen Web-Seite). V1 = Config-Datei (PHOTO-19).
- **OPEN-PHOTO-C — Per-Kind-Libraries / figure_id-Routing.** V1 ist eine
  Familien-Library (E-PHOTO-5); Per-Kind hängt an den routing-Defaults pro Figur
  (#83) und kommt später.
- **OPEN-PHOTO-D — Google Photos / externe Bibliotheken-Sync.** Vision-Endausbau
  (direkter Link zu einer externen Bibliothek), später.
- **OPEN-PHOTO-E — Bild-/Video-Verarbeitungs-Libs.** Foto: Pillow + pillow-heif
  (HEIC-Decode). Video: **`ffmpeg`** (Transcode HEVC/MOV→MP4 + Poster-Frame) —
  **schwerere Pi-Abhängigkeit**, fürs Bau-Ticket einplanen.
- **OPEN-PHOTO-F — Geteilter Upload-/Atomic-Write-Helfer.** Der multipart-Ingest +
  atomare Schreiben sind das 2. Vorkommen nach FAM-13 → Beobachtung für die
  Prozess-Werkstatt (conventions/ bei konkretem Schmerz), **kein V1-Blocker**.
- **OPEN-PHOTO-G — Foto-Stage-Look. ERLEDIGT (Gate B, Nic 2026-06-06):** gewählt ist
  die **helle DS-Linen-Stage „Linen Frame"** (Medium als gerahmte Karte), **nicht**
  Schwarz — voll DS-konform, kein Ausnahme-Vermerk nötig (E-PHOTO-11).
- **OPEN-PHOTO-H — Library-Kapazität / Pi-Speicher.** Keine harte Grenze in V1;
  Auto-Delete (PHOTO-12) ist das Ventil. Max-Anzahl/-Größe als späterer
  Tuning-Wert, falls Schmerz auftritt.
- **OPEN-PHOTO-J — Schwelle „kurzes Video".** Dauer/Größe als Config
  (`video_max_s`, Vorschlag-Default 60 s, PHOTO-19); finaler Wert nach erstem
  echten Gebrauch.
- **OPEN-PHOTO-K — Ton in der Slideshow.** V1 spielt Videos stumm (PHOTO-6,
  Autoplay-sicher). Ton (z. B. Unmute bei Kind-Interaktion) ist später/Config.

---

## Entscheidungen

### E-PHOTO-1 — Photo-Buddy ist eine App: besitzt Daten, Funktion, View
*Datum:* 2026-06-06 · App-Muster (APP-1, wie E-PLAN-1 / E-WETTER-1). Besitzt die
Medien-Library (Daten) und Ingest/Normalisierung/Durchlauf (Funktion); stellt das
Ergebnis über die Display-View bereit.

### E-PHOTO-2 — Interface-first: volle API in V1, Eltern-Chat-Skill nachgezogen
*Datum:* 2026-06-06 (Nic, Werft-Standard) · V1 exponiert die volle
Medien-API inkl. Ingest (PHOTO-13); die Eltern-Chat-Integration, die sie ruft,
wird nachgezogen. Der Contract ist die Architektur-Entscheidung und kommt nach
vorn; das Telegram-Plumbing nach hinten. Entschärft die APP-4-/Schreibpfad-Strecke
(#296). **Verworfen:** Ingest-API erst mit dem Eltern-Chat-Skill zusammen bauen
(hätte den n=0-Schreibpfad direkt an den ersten Build gebunden).

### E-PHOTO-3 — Ingest folgt dem Familie-Foto-Muster
*Datum:* 2026-06-06 · `POST .../medien` als `multipart/form-data` mit atomarem
Schreiben spiegelt das bereits ratifizierte Familie-Profilfoto-Muster (FAM-13,
DCOMP-4) — **kein zweiter Upload-Stil**. Ob ein geteilter Upload-Helfer
extrahiert wird, ist Prozess-Werkstatt (OPEN-PHOTO-F). **Verworfen:** eine eigene,
abweichende Upload-Mechanik.

### E-PHOTO-4 — Interaktiver Buddy (bewusste Bedien-Elemente)
*Datum:* 2026-06-06 · Pfeile/Pause/Übersicht (PHOTO-4/5) machen den Photo-Buddy
**interaktiv** — anders als der statische Wetter-/Plan-Kiosk (WETTER-3). Grund:
das Kind soll sein eigenes Anschauen selbst steuern (Selbstbestimmung, North Star).
**Verworfen:** reiner Auto-Durchlauf ohne Bedienung.

### E-PHOTO-5 — Eine Familien-Library in V1
*Datum:* 2026-06-06 (Nic) · Alle Kinder sehen dieselbe Library. Einfachster
Schnitt, passt zu „Buddy hat eigene Bibliothek" (singular). Per-Kind-Trennung
später als Config/Routing (OPEN-PHOTO-C). **Verworfen:** Per-Kind-Libraries in V1
(zöge figure_id-Routing #83 und „welches Medium für wen"-Logik in den ersten Bau).

### E-PHOTO-6 — Auto-Delete Default AUS, opt-in per TTL
*Datum:* 2026-06-06 (Nic) · Löschen ist ein Feature, kein Standardverhalten —
Default behält alles; eine Familie schaltet die TTL bewusst ein (PHOTO-12). TTL am
Hinzufüge-Stempel, injizierbares `now`. **Verworfen:** Default-TTL (würde
ungefragt Erinnerungen löschen).

### E-PHOTO-7 — Defensive Normalisierung beim Ingest, nicht bei der Anzeige
*Datum:* 2026-06-06 · Konvertierung HEIC→JPEG / HEVC-MOV→MP4 passiert **einmal
beim Ingest** (PHOTO-8), nicht bei jeder Anzeige — die View bleibt billig und
browser-kompatibel. **Verworfen:** rohe Originale speichern und im Browser
konvertieren (geht für HEIC/HEVC nicht zuverlässig).

### E-PHOTO-8 — Sortier-Achsen als Config; Default neueste-zuerst nach Hinzufüge
*Datum:* 2026-06-06 (Nic) · Richtung × Stempel-Quelle sind Familie-3-Config
(PHOTO-11); Default `neueste-zuerst`/`hinzugefügt`. EXIF fehlt → Fallback
Hinzufüge-Stempel. **Verworfen:** feste Sortierung im Code.

### E-PHOTO-9 — Telegram normalisiert nur den Kompressions-Pfad → defensiv bleiben
*Datum:* 2026-06-06 · Telegram re-encodiert Medien, die **als Foto/Video**
gesendet werden, serverseitig (Foto→JPEG, Video→MP4) — aber der **„als
Datei/Dokument"-Pfad** (Originalqualität) umgeht das und liefert iPhone-HEIC bzw.
HEVC/MOV. Der Photo-Buddy verlässt sich daher **nicht** auf Telegram, sondern
normalisiert defensiv (PHOTO-8); im Kompressions-Pfad ist das ein billiger
Pass-through. *Quelle:* Telegram Bot API / API-Limit-Analyse (Foto→JPEG q≈82),
HEVC→MP4-Transcode beim Video-Versand; Live-Recherche 2026-06-06. **Verworfen:**
annehmen, dass Telegram immer schon normalisiert hat.

### E-PHOTO-10 — Übersicht als In-View-Zustand, kein Reload
*Datum:* 2026-06-06 (Nic) · Der Übersichts-Modus (PHOTO-5) ist ein clientseitiger
Zustand derselben View — kein Seiten-Reload, der Slideshow-Zustand bleibt erhalten.
**Verworfen:** Übersicht als eigene URL-View (verlöre den Durchlauf-Zustand).

### E-PHOTO-11 — Foto-Stage: helle DS-Linen-„Galeriewand", nicht Schwarz
*Datum:* 2026-06-06 (Nic, Gate B) · Drei Stage-Richtungen wurden als gerenderte
1920×1080-Mockups verglichen (Warm-Dark, Pure Black, Linen Frame). Gewählt:
**Linen Frame** — heller DS-Linen-Hintergrund (`--bg`), Medium als **gerahmte
Surface-Karte** (weiche Rundung + Schatten), Bedien-Elemente fest angeordnet
(Pfeile mittig seitlich, Grid oben-rechts, Pause unten-rechts), **keine
Bildunterschrift, kein Zähler**. Grund: voll DS-konform (DS-Regel „never pure
black", tokens.css) und warm/Montessori-treu für ein Kinderprodukt. **Verworfen:**
Pure Black (stärkster Fokus, aber DS-Ausnahme und kühl) und Warm-Dark
(DS-konformer Kompromiss, aber dunkle Stage unnötig, da der Linen-Rahmen das Foto
ausreichend trägt). Löst OPEN-PHOTO-G.
