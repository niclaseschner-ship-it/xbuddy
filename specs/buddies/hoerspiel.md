# Hörspiel-Buddy — Spec     (ID-Präfix: HSP)

> Status: V1 · Refs #729

## Problem & North-Star-Bezug

Mia (4) hört seit Monaten ihre eigene Hörspiel-Serie „Stigi, Malini &
Vögelchen — Geschichten aus dem Garten im Mustertal" — Folgen werden lokal
geschrieben und über das Handy eines Elternteils abgespielt. Drei Probleme:

1. **Hardware-Knappheit:** Sie braucht Mamas oder Papas Handy, das oft
   anderswo gebraucht wird.
2. **Abbrüche:** Vorlesen bricht beim App-Wechsel ab, beim Anruf, beim
   Lock-Screen. Kein „weiter wo aufgehört".
3. **Keine Selbstbedienung:** Sie kann nicht eigenständig wählen, welche
   Folge sie hören will, geschweige denn eine zuvor unterbrochene Stelle
   wiederfinden.

**North-Star-Bezug (constitution.md):** Mia **wählt und steuert das
Hören selbst** über eine Kachel-Oberfläche auf einem eigenen Gerät, statt
ein Elternteil mit dem Handy zu binden. Was die Eltern bisher taten
(Hörspiel auswählen, Wiedergabe starten, Stelle finden), verschiebt sich
vollständig zum Kind.

Der Hörspiel-Buddy ist eine eigenständige XBuddy-**App** mit einer Display-
View — der **Album-Übersicht und Player für Mia** — und einer App-eigenen
**KI-Funktion**, die im Eltern-Chat-Skill (Familien-Schnittstelle) neue
Folgen erzeugt und vertont. Als App **besitzt** er seine Daten (Welt-Bible,
Folgen-Historie, Alben + Audio-Assets), seine Funktion (LLM-gestützte
Folgen-Erzeugung, TTS-Album-Bau, Resume-Verwaltung) und stellt das Ergebnis
über seine Display-View bereit (HSP-1, APP-1).

**V1-Scope:** Single-Page-View `alben` (Kachel-Raster + Player auf einer
Canvas) · Album-Modell mit geordneten Tracks · Voice-Casting je Album über
zwei Azure-OpenAI-tts-hd-Voices `shimmer` (weich/weiblich) und `onyx`
(tief/männlich) · Pausen über expliziten Silence-Insert (kein `speed`-
Stretching) · Intro/Outro als vorsynthetisierte Shared-Assets je Voice (vier
feste MP3) · Track-Resume mit Rundung auf Track-Anfang · MediaSession-API
+ PWA `display:standalone` gegen Geräte-Schlaf · App-eigener **LLM-Adapter
mit Provider-Switch** (`claude` Default; `mistral` als V2-Hook, V1 Stub) ·
App-eigener **TTS-Adapter** (Azure OpenAI, Region `swedencentral`) · zwei
schreibende API-Endpoints für den Eltern-Chat-Skill (`POST /folgen-vorschlag`,
`POST /alben`) · Lese-Endpoints für Bible/Historie/Album-Liste/Manifest ·
Welt-Bible & Folgen-Historie als Per-Instanz-Domänendaten (BUD-2a) · ein
familienseitiger Beitrag: der Eltern-Chat-Skill `hoerspiel-folge-erzeugen`
(eigene Plattform-Spec `specs/platform/hoerspiel-folge-erzeugen.md`,
ID-Präfix HFE).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **OPEN-HSP-A** — Folgen-spezifisches Cover-Bild (V1: festes Serien-Cover,
  optional Folgentitel-Text auf Default-Hintergrund).
- **OPEN-HSP-B** — Mia äußert per Sprache ihren Folgen-Wunsch im Eltern-
  Chat („Ich möchte eine Folge über Schnee"). Würde denselben V1-Endpoint
  `POST /folgen-vorschlag` bedienen — Trigger-Agnostik.
- **OPEN-HSP-C** — Bilder synchron zum Track-Inhalt (Bilderbuch-Modus).
  Braucht die Track-Granularität, die V1 schon legt.
- **OPEN-HSP-D** — Aussprache-Lexikon für Eigennamen (Stigi, Schmuggli,
  Mustertal …) das die TTS-Vorlage vor der Synthese anwendet.
- **OPEN-HSP-E** — mehrere Hörspiel-Serien parallel (V1: eine Serie,
  „Stigi & Co.").
- **OPEN-HSP-F** — Premium-Voice-Upgrade zu ElevenLabs oder einer Custom-
  Neural-Voice für native deutsche Aussprache (V1 akzeptiert die leichte
  engl. R-Rollung von `shimmer`/`onyx`, HSP-23).
- **OPEN-HSP-G** — App auf Mias eigenem Gerät (V1 nimmt Familien-Tablet
  im Browser an; eigenes Gerät ist Hardware-/Onboarding-Frage).
- **OPEN-HSP-H** — Concurrency-Lock am TTS-Adapter bei der heutigen 3-RPM-
  Quota; bei höherer Quota entfällt das.
- **OPEN-HSP-I** — Album-Sortierung in der Kachel-View (neuestes zuerst /
  Lieblings-Markierung / Resume-Album vorgezogen).
- **OPEN-HSP-J** — Anzahl-Begrenzung Kacheln (Scroll / Archiv / Filter).
- **OPEN-HSP-K** — Audio-Format MP3 96 kbps mono in V1; Opus später.
- **OPEN-HSP-L** — Asynchrone Generierung mit Benachrichtigung am Ende
  statt blockierender Synthese.
- **OPEN-HSP-M** — Azure-/Anthropic-Schlüssel-Verwaltung in der Plattform-
  Schicht (heute per-App-ENV nach CONFIG-1/CONFIG-3, siehe HSP-26). Folge-
  Ticket im Werft-Lauf 2026-06-12 angelegt.
- **OPEN-HSP-N** — Eltern-Chat-Skill „LLM-Provider für Hörspiel wechseln"
  (Inline-Befehl „wechsele mal auf mistral für hörbücher" patcht den
  Provider via `PATCH /api/v1/hoerspiel/config`, HSP-19). V1 exposed den
  Endpoint, der Skill zieht in V2 nach.

---

## 1. Die App & ihre View

### HSP-1 — Hörspiel-Buddy ist eine App mit eigenem Besitz
Der Hörspiel-Buddy ist die XBuddy-App mit dem Buddy-Slug `hoerspiel`. Er
besitzt seine **Daten** (Welt-Bible, Folgen-Historie, Album-Manifeste +
Audio-Assets, Resume-State), seine **Funktion** (LLM-gestützte Folgen-
Erzeugung, TTS-Pipeline, Album-Sequencing, Resume-Verwaltung) und stellt
das Ergebnis über seine **Display-View** bereit (APP-1). Er stellt eine
API für den Eltern-Chat-Skill bereit (BUD-1b, HSP-17).

### HSP-2 — Single-Page-View `alben`, Kacheln + Player auf einer Canvas
Die Hör-View liegt unter `/display/hoerspiel/alben` (BUD-1, URL-2) und ist
**eine Canvas**: oben Album-Kacheln, unten der Player wenn ein Album
spielt. Kein Routing zu Sub-Seiten. Statische Assets unter
`/display/hoerspiel/static/<asset>` (URL-13); Audio- und Cover-Assets je
Album werden aus dem Daten-Bereich über Router-Pfade in derselben
Display-Origin ausgeliefert (HSP-21).

**Wenn** die View aufgerufen wird, **dann** rendert sie alle freigegebenen
Alben als Kachel-Raster und — falls Mia ein Album zuletzt unterbrochen
hatte — einen prominenten „Weiter hören"-Hinweis auf dieses Album.

*Test-Implikation:* GET `/display/hoerspiel/alben` rendert mindestens ein
Album-Kachel-Element pro freigegebenem Album; bei vorhandenem Resume-State
zusätzlich einen Hinweis-Block für das unterbrochene Album.

### HSP-3 — Touch-Display, Mia-taugliche Bedienung (Kiosk)
Die View ist für ein Touch-/Kiosk-Display gebaut. Maximale Bedien-
Affordanzen für eine Vierjährige:

- Album-Kachel tippen → Wiedergabe startet (siehe HSP-13)
- Player: großer Play/Pause-Knopf in der Mitte, große Vor/Zurück-Knöpfe
  links/rechts pro Track
- Kein Wisch, kein Long-Press, kein Multi-Touch, kein Tastatur-Fokus

Lautstärke wird **nicht** in der App geregelt — System-Lautstärke des
Gerätes reicht.

### HSP-4 — Visueller Stil aus dem geteilten Design-Token-Strang
Der visuelle Stil bindet an `display/_shared/design/tokens.css` (DTOK-1..5,
`conventions/design-tokens.md`); keine hartcodierten Farben/Maße im Buddy-
CSS. Komponenten erden an die bestehende Buddy-Card-Optik (Anker:
`wetter/static/wetter.css` `.card`/`.card-label`).

---

## 2. Album-Modell und Track-Struktur

### HSP-5 — Ein Album entspricht einer Folge
Ein **Album** ist die Wiedergabe-Einheit, die eine Hörspiel-Folge abbildet.
Pflichtfelder im Manifest: stabile `id` (`folge-<nummer>`), `nummer` (int),
`titel` (string), `voice` (`shimmer` | `onyx`), `erstellt-am` (ISO-Datum),
`freigegeben` (bool, V1: nach Eltern-Freigabe immer `true`), `cover-asset`
(Pfad innerhalb des Display-Statik-Namensraums), `tracks` (geordnete Liste).
Format-Skizze: HSP-21.

### HSP-6 — Ein Album besteht aus geordneten Tracks
Ein Album hat eine geordnete Liste von Tracks. Der Track ist die
Wiedergabe-Einheit unter dem Album. Pflichtfelder je Track: stabile `id`,
`position` (int, ab 1), `dauer-sek` (int), `audio-asset` (Pfad),
`art` ∈ `intro` | `inhalt` | `outro`. `titel` ist optional und V1 nicht
zwingend in der View angezeigt.

**Wenn** ein Album geladen wird, **dann** sind seine Tracks deterministisch
in `position`-Reihenfolge sortiert.

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
Provider eine konkrete Implementierung. **V1 implementiert nur den
`claude`-Adapter**; der `mistral`-Adapter existiert in V1 als
nicht-funktionaler Stub mit identischer Signatur und löst bei Auswahl ohne
gesetzten Mistral-Key eine sichtbare Fehlermeldung aus, kein stilles
Scheitern (HSP-11).

**Wenn** der konfigurierte Provider (HSP-26) `claude` ist, **dann** wird
der Anthropic-SDK-Adapter genutzt mit dem im Provider-Default petrankerten
Modell-Pin (`claude-opus-4-7`) oder dem in der Config überschriebenen
Wert; **wenn** `mistral`, **dann** der Mistral-Adapter (V2-funktional).

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
der Eltern-Chat-Skill in V1, ein Sprach-Trigger für Mia in V2
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

### HSP-14 — Synthese-Architektur: Bündel-Calls mit strukturierten Pausen
Der Inhalt eines Albums wird in **Absatz-Bündeln** synthetisiert (nicht
pro Absatz, nicht als ein einziger Call). Bündel-Heuristik: solange das
laufende Bündel < ~450 Wörter, nächsten Absatz dranhängen; bei ≥450
Wörtern Bündel abschließen. **Schnitte fallen immer auf Absatzgrenzen,
nie mitten in einen Satz.**

Pausen werden über **expliziten Silence-Insert** abgebildet, nicht über
den `speed`-Parameter der TTS-API (post-hoc Time-Stretching erzeugt
blechernen Klang, HSP-23):

- nach Intro-Track-Ende: 1,2 s (im Intro-Asset enthalten)
- nach Titel-Absatz (erster Inhalts-Absatz mit Folgennummer): 1,8 s
- zwischen normalen Inhalts-Absätzen: 0,55 s
- vor Outro-Track-Beginn: 0,55 s

Der `speed`-Parameter wird **nicht** genutzt (immer 1.0).

*Test-Implikation:* ein Folgentext mit fünf Absätzen (à 200 Wörter)
ergibt zwei Bündel-Calls; eine Folge mit zwei Absätzen (à 600 Wörter)
ergibt zwei Bündel-Calls. Die Bündel-Schnitt-Funktion ist deterministisch
und ohne Netz testbar.

### HSP-15 — Album-Bau als atomarer Vorgang
**Wenn** der Buddy einen `POST /api/v1/hoerspiel/alben`-Aufruf erhält,
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
Der Buddy stellt unter `/api/v1/hoerspiel/<resource>` folgende Endpoints
bereit (BUD-1b, URL-4):

| Methode | Pfad | Zweck | Aufrufer |
|---|---|---|---|
| `GET` | `/api/v1/hoerspiel/bible` | Welt-Bible als Markdown lesen | Skill (Folgen-Prompt) |
| `GET` | `/api/v1/hoerspiel/folgen-historie` | Folgen-Historie als Markdown lesen | Skill, künftige Konsumenten |
| `GET` | `/api/v1/hoerspiel/alben` | Alle freigegebenen Alben als JSON-Array | View, Skill |
| `GET` | `/api/v1/hoerspiel/alben/<id>/manifest` | Album-Manifest als JSON | View, Skill |
| `POST` | `/api/v1/hoerspiel/folgen-vorschlag` | Folgen-Idee → `{titel, text}` per LLM | Skill (HFE) |
| `POST` | `/api/v1/hoerspiel/alben` | Album bauen (TTS-Pipeline + Historie-Update) | Skill (HFE) |
| `GET` | `/api/v1/hoerspiel/config` | Aktive Provider/Modell-Konfig lesen | Skill (V2-Provider-Wechsel, OPEN-HSP-N) |
| `PATCH` | `/api/v1/hoerspiel/config` | Provider/Modell zur Laufzeit umschalten | Skill (V2-Provider-Wechsel) |
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

**`PATCH /config`** Body: `{llm_provider?: "claude"|"mistral", llm_model?: string}`.
Wirkung: setzt die Werte in der Per-Instanz-Runtime-Config (HSP-26) und
gibt die neue effektive Konfig zurück. **Wenn** der gesetzte Provider
keinen API-Key konfiguriert hat, **dann** lehnt der Endpoint mit HTTP 422
und Klartext-Hinweis ab — Provider-Switch ohne Key-Voraussetzung wird
nie aktiv.

### HSP-18 — Direkter Datei-Zugriff durch andere Apps ist verboten
Welt-Bible, Folgen-Historie, Album-Manifeste und Audio-Assets liegen im
Daten-Bereich des Buddys. Andere Apps und der Eltern-Chat-Skill greifen
**ausschließlich** über die HTTP-API zu (APP-3). Insbesondere liest der
Skill die Bible über `GET /bible`, nicht aus dem Dateisystem.

---

## 6. Mia-View — Kacheln und Player

### HSP-19 — Album-Kachel
Eine Kachel zeigt: das Cover-Asset des Albums (V1: festes Default-Cover
für die ganze Serie, OPEN-HSP-A), den Album-Titel als Text, und — falls
für dieses Album ein Resume-State existiert — eine sichtbare „Weiter
hören"-Markierung. Tap-Affordanz ist die gesamte Kachel.

### HSP-20 — Tap auf Kachel startet (oder setzt fort) das Album
**Wenn** Mia auf eine Album-Kachel tippt, **dann**:

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

**Wenn** Mia auf „nächster Track" tippt, **dann** springt die Wiedergabe
sofort zum Anfang des nächsten Tracks im Album. Beim letzten Track des
Albums springt sie zum ersten Track desselben Albums zurück (kein
automatisches Verkettungswechseln zu einem anderen Album in V1).

**Wenn** Mia auf „voriger Track" tippt, **dann** springt sie zum Anfang
des aktuellen Tracks zurück. Tippt sie nochmal innerhalb von 3 s, springt
sie zum vorherigen Track (klassisches Audio-Player-Muster).

### HSP-22 — Audio-Wiedergabe robust gegen Geräte-Schlaf
Die Wiedergabe verwendet die **MediaSession-API** des Browsers und ein
**PWA-Manifest** mit `display: standalone`, sodass:

- Lock-Screen-Kontrollen für Play/Pause erscheinen
- Audio nicht stoppt, wenn der Bildschirm schwarz wird
- Album-Titel und Track-Position auf dem Lock-Screen sichtbar sind

V1-Annahme: Mia nutzt die App im Browser oder als „Zum Home-Bildschirm
hinzufügen"-PWA. Eigenes Gerät = OPEN-HSP-G.

---

## 7. Resume-Verhalten

### HSP-23 — Resume-Marke pro Album, auf Track-Anfang gerundet
Pro Album wird **eine** Resume-Marke gehalten: `track-position` (int,
welcher Track gerade lief). **Innerhalb** eines Tracks wird die Offset-
Position bei Wiederaufnahme auf den **Track-Anfang** gerundet — Mia
hört den unterbrochenen 3–4-Minuten-Block ab seiner letzten Schwelle, nicht
mitten im Satz. Track-Granularität ist die natürliche Wiederaufnahme-
Granularität (E-HSP-4).

V1 hält die Resume-Marke im Browser-`localStorage` pro Album. Ein Server-
seitiger Resume-State (Multi-User, Multi-Gerät-Sync) ist OPEN-HSP-G-Folge.

**Wenn** Mia die View wieder aufruft und für ein Album ein Resume-State
besteht, **dann** zeigt die Kachel zusätzlich „Weiter hören" und der Tap
startet die Wiedergabe beim **Anfang** des unterbrochenen Tracks.

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

### HSP-25 — Daten-Layout
Der Hörspiel-Buddy hält drei Klassen Daten im Per-Instanz-Daten-Bereich
(BUD-2a, gitignored über `hoerspiel/.gitignore` per BUD-2b):

```
hoerspiel/data/
  bible.md                     # Welt-Bible (familien-spezifisch)
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
    cover-default.png          # Default-Serien-Cover (OPEN-HSP-A)
```

Die Welt-Bible ist der Musterfall der **Familie-3-Probe**: was sich je
Familie ändert, ist Daten, nicht Code (E-HSP-5). Eine andere Familie hätte
eine andere Bible (andere Charaktere, andere Welt) — dieselbe App.

**Datei-Inhalte sind Domänendaten, kein Konfig** (BUD-2a, getrennt von
Runtime-Config HSP-27). Direkter Datei-Zugriff durch andere Apps ist
verboten (HSP-18, APP-3).

### HSP-26 — Album-Manifest-Format (JSON)
Jedes Album hat ein Manifest `data/alben/<album-id>/manifest.json`:

```json
{
  "id": "folge-22",
  "nummer": 22,
  "titel": "Schmuggli erzählt vom Trübsee",
  "voice": "shimmer",
  "erstellt-am": "2026-06-12",
  "freigegeben": true,
  "cover-asset": "/display/hoerspiel/static/cover-default.png",
  "tracks": [
    {"id": "intro-shimmer", "position": 1, "art": "intro",
     "audio-asset": "/display/hoerspiel/data/shared-assets/intro_shimmer.mp3",
     "dauer-sek": 18},
    {"id": "folge-22-track-02", "position": 2, "art": "inhalt",
     "audio-asset": "/display/hoerspiel/data/alben/folge-22/audio/track-02.mp3",
     "dauer-sek": 215, "titel": null},
    {"id": "outro-shimmer", "position": "N", "art": "outro",
     "audio-asset": "/display/hoerspiel/data/shared-assets/outro_shimmer.mp3",
     "dauer-sek": 22}
  ]
}
```

`audio-asset`-Pfade werden vom Buddy-Service über den Display-Namensraum
ausgeliefert (Route `GET /display/hoerspiel/data/<sub>` mappt auf den
Daten-Bereich, nur freigegebene Album-IDs). Die Pfade sind absolute
View-URLs für das Frontend.

---

## 9. Konfiguration

### HSP-27 — Konfigurationswerte
Zwei Per-Instanz-Dateien neben dem Code (BUD-2, BUD-2a, beide gitignored
über `hoerspiel/.gitignore`):

- `hoerspiel/config.json` — **Runtime-Config** (Bind, Log, Provider,
  Modelle), via `tools/configloader.py` (CONFIG-1). ENV-Overrides folgen
  `HOERSPIEL_<KEY>` (BUD-2, CONFIG-5).
- `hoerspiel/hoerspiel.json` — **Daten-Konfig** (Default-Voice,
  Serien-Name; familien-spezifisch).

**Geheimnisse** (Anthropic-Key, Azure-Key) landen **nie** in einer Datei
im Repo (CONFIG-3, CLAUDE.md §8). Sie kommen ausschließlich aus
Umgebungsvariablen, gesetzt im systemd-Service oder einer ENV-Datei
außerhalb des Repos. Die zentrale Geheimnis-Verwaltung pro Familien-
Instanz folgt heute dem **EC-15-Pattern des Eltern-Chats** (ENV-Variable,
ggf. Onboarding-Store) — keine zweite, parallele Secret-Schicht für den
Hörspiel-Buddy. Eine plattformweite Verwaltung dieser Schlüssel ist
OPEN-HSP-M.

| Name | Default | Datei-Schlüssel | Quelle |
|---|---|---|---|
| `listen_host` | `127.0.0.1` | `listen_host` | n/a (PORT-3) |
| `listen_port` | `5053` (HSP-28) | `listen_port` | n/a (PORT-2) |
| `log_level` | `INFO` | `log_level` | n/a |
| `llm_provider` | `claude` | `llm_provider` | Eltern (PATCH-Endpoint, V2-Skill) |
| `llm_model` | `claude-opus-4-7` | `llm_model` | Eltern (PATCH-Endpoint) |
| Default-Voice | `shimmer` | `default_voice` | Eltern (Hörspiel-Konfig) |
| Serien-Name | `Stigi & Co.` | `serien_name` | Familie (Daten-Konfig) |
| Anthropic-Key | (Pflicht wenn `llm_provider=claude`) | — | ENV `HOERSPIEL_ANTHROPIC_KEY` (CONFIG-3) |
| Mistral-Key | (Pflicht wenn `llm_provider=mistral`) | — | ENV `HOERSPIEL_MISTRAL_KEY` (CONFIG-3) |
| Azure-Endpoint | (Pflicht) | `azure_openai_endpoint` | ENV `HOERSPIEL_AZURE_OPENAI_ENDPOINT` |
| Azure-Deployment | (Pflicht) | `azure_openai_deployment` | ENV `HOERSPIEL_AZURE_OPENAI_DEPLOYMENT` |
| Azure-Key | (Pflicht) | — | ENV `HOERSPIEL_AZURE_OPENAI_KEY` (CONFIG-3) |

Werte fehlen → Code-Default greift mit Warnung, der Prozess startet weiter
(CONFIG-4), **außer** bei Pflicht-Geheimnissen: fehlt der für den aktiven
Provider nötige Key, antwortet der Buddy auf API-Aufrufe, die ihn brauchen,
mit HTTP 503 + Klartext-Hinweis (kein stilles Scheitern).

---

## 10. Service & Registrierung

### HSP-28 — Eigener Service, fester Port
Der Hörspiel-Buddy läuft als eigener Prozess `xbuddy-hoerspiel.service`
(SVC-1..4, `Restart=on-failure`, Logs an stdout/stderr) und bindet nur an
`127.0.0.1` (PORT-3). Port **5053** (PORT-2, `xbuddy-hoerspiel`, einzutragen
in `conventions/ports.md`).

### HSP-29 — Vorsynthese der Shared-Assets als Setup-Schritt
Vor der ersten Folge in einer Familien-Instanz müssen die vier Shared-
Assets (Intro/Outro je Voice) erzeugt werden. Trigger: ein einmaliger
Aufruf `POST /api/v1/hoerspiel/shared-assets/rebuild` (HSP-17) oder ein
Setup-Script, das denselben Endpoint ruft. Kosten: 4 × ~50 Zeichen × Azure
tts-hd ≈ 1 Cent, einmalig. Die Quell-Texte (`intro.txt`, `outro.txt`)
liegen im Daten-Bereich.

**Wenn** ein Album-Bau angefordert wird (HSP-15) und die für die gewählte
Voice nötigen Shared-Assets fehlen, **dann** lehnt der Endpoint mit
HTTP 412 + Klartext-Hinweis ab — kein stilles Scheitern, kein
Auto-Rebuild beim Album-Bau (Trennung der Petrantwortung).

### HSP-30 — Registrierung in der Plattform
Der Slug `hoerspiel` wird im Origin-Routing (URL-14) registriert, damit
`/display/hoerspiel/alben` und `/api/v1/hoerspiel/*` über die Origin
erreichbar sind. Diese Verkabelung ist **Integration**, nicht App-Eigentum
— Gegenstand des arbeitstag-Track-Schnitts (F4/F5).

**Familien-Schnittstelle-Beitrag (APP-4):** der Eltern-Chat-Skill
`hoerspiel-folge-erzeugen` lebt unter `eltern-chat/skills/` und wird vom
Hörspiel-Buddy-Owner gepflegt. Eigene Plattform-Spec
`specs/platform/hoerspiel-folge-erzeugen.md`, ID-Präfix `HFE-`. Inhaltlich:
dünner Telegram-Adapter, der `/folgen-vorschlag` und `/alben` ruft, ohne
eigenen LLM-Zugriff.

### HSP-31 — Kachel-Icon der Display-View
Der `views.json`-Eintrag der View `alben` trägt `icons[]` mit ein bis drei
Pfaden relativ zur Icon-Basis `/display/_shared/icons/` (BUD-4, PANEL-3,
ICONS-5). V1 nutzt ein passendes ARASAAC-Piktogramm aus dem Instanz-Icon-
Store; das Kachel-Icon ist **kein** app-eigenes Asset (URL-13) und **kein**
buddy-eigener ARASAAC-Bezug.

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
  auf `/folgen-vorschlag`; fehlender Mistral-Key bei `llm_provider=mistral`
  ebenso)
- HSP-29 (Album-Bau ohne vorhandene Shared-Assets für die gewählte Voice
  → HTTP 412; Auto-Rebuild findet **nicht** statt)

Läufe gegen echte Engines (Azure tts-hd, Anthropic) sind opt-in und nicht
Teil der V1-Standard-Test-Suite.

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
wenn Mia nicht zu Ende gehört hat". Track ist die natürliche
Wiederaufnahme-Granularität (3–4 min, geschnitten an Absatzgrenzen).
Trade-off: Mia hört 30–60 s nochmal — akzeptabel und gut (sie erinnert
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
