# KIBuddy — Spec     (ID-Präfix: KIBUDDY)

> Status: V1 · Refs #819

## Problem & North-Star-Bezug

Kinder (4–7 J) haben eine Wissensfrage und keinen Weg, sie selbst zu stellen
— der heutige Pfad führt über Eltern, deren Handy oder den Familien-Computer.
Der KIBuddy gibt dem Kind **selbst** eine Frage-Antwort-Schnittstelle: es
spricht die Frage, sieht die Antwort als **Text mit Icon-unter-Wort** auf dem
Display und hört sie parallel als Sprache. So verschiebt sich „eine Frage
beantwortet bekommen" vom Elternteil zum Kind (North Star) und wird
gleichzeitig **lese-vorbereitend** — das Kind „liest mit", bevor es lesen kann.

Der KIBuddy ist eine eigenständige XBuddy-**App** mit einer Display-View — der
**Frage-View** — und einer App-eigenen **KI-Funktion** (eigener Prompt,
eigener LLM-Adapter, eigene STT/TTS-Anbindung). Als App **besitzt** er seine
Daten (Prompt, Voice, Provider-Config, Aufnahme-Quelle), seine Funktion
(STT → LLM → Icon-Render → TTS) und stellt das Ergebnis über seine Display-View
bereit (KIBUDDY-1, APP-1).

**Vorläufer-Kontext (nicht-Spec-bindend):** Eine Vorläufer-App `kibuddy` läuft
auf dem BuddyBoard (Pre-XBuddy), Port 5006, OpenAI-direkt mit `whisper-1` /
`gpt-4o-mini` / `tts-1-hd`. Aus deren Pictogram-Cache ist die heutige zentrale
Icon-Wurzel (ICONS-3) geseedet. Diese Spec **migriert** den KIBuddy nach xbuddy
mit einem frischen Schnitt — sie ist **keine** Code-Migration, sondern ein
greenfield-Neu-Bau im xbuddy-Stil.

**V1-Scope:** Single-Page-View `frage` · **Push-to-Talk-Aufnahme am Display**
mit Messenger-Style-UX (Tap+Hold ODER Tap-und-Slide-to-Lock; visuelles
Feedback im Drück-Moment; Pegel-Balken **rechts neben Mikro ab Druck-Beginn**;
Slide-Hinweis grafisch als Pfeil → Schloss aus zentraler Icon-Bibliothek) ·
STT über Azure-OpenAI Whisper · LLM-Adapter `claude` mit Provider-Switch
(V2-Hook, V1 nur `claude`) · **Mehrturn-Konversations-Kontext in Session-
Memory** am Service (KIBUDDY-16, Reset über Reset-Knopf KIBUDDY-29) · TTS
über Azure-OpenAI TTS-HD mit Stimme **`onyx`** und Geschwindigkeit **`0.9`**
(bewusst etwas langsamer als Hörspiel-Buddy für Kinder-Verständnis, KIBUDDY-20) ·
Antwort-Render **Wort-für-Wort** mit Icon **nur für Inhaltswörter** (Nomen,
Vollverben, Adjektive; Funktionswörter nur als Text — KIBUDDY-17 Filter) ·
**Chat-Verlauf** als scrollender Container in der View (Seite scrollt nicht,
KIBUDDY-19) · **UI-Icons aus zentraler Icon-Bibliothek** (Mikro/Mülleimer/
Schloss/Pfeil — KIBUDDY-30) · Antwort-Render mit Icon
darunter aus zentraler Icon-Bibliothek (ICONS-5/ICONS-7) — Wörter ohne Treffer
nur als Text · Prompt aus Per-Instanz-Daten, **zur Laufzeit lese- und
schreibbar** über `GET`/`PUT /api/v1/kibuddy/prompt` (KIBUDDY-15,
KIBUDDY-24) · **zwei** App-eigene Eltern-Chat-Skills:
`aufnahme-quelle-setzen` (KAQS, `specs/platform/kibuddy-aufnahme-quelle-setzen.md`)
zum Umschalten der Aufnahme-Quelle (Display ↔ Panel) und
`kibuddy-prompt-anpassen` (KPA, `specs/platform/kibuddy-prompt-anpassen.md`)
zum sokratisch-geführten Verbessern des System-Prompts mit Diff-Vorschau
und Bestätigung.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **OPEN-KIBUDDY-A** — **Panel-Mikro-Pfad** (Aufnahme am Tablet/Panel, Rendern am
  Display): braucht eine Audio-Brücke vom Controller-Gerät zum Display-Service
  (Cross-Device-Streaming) — die in den Werft-Grenzen markierte „nie
  durchgelaufene" APP-4-Strecke. V1 macht den Schalter nur aus „display" → andere
  Werte werden als unkonfiguriert behandelt (KIBUDDY-22).
- **OPEN-KIBUDDY-B** — **Custom-Wake-Wort, teachbar**: ein Wake-Wort, das die
  Familie selbst trainiert (Porcupine-Custom-Wake-Word-Training). V1 hat
  überhaupt kein Wake-Wort, sondern reine Push-to-Talk-UX (KIBUDDY-7).
- **OPEN-KIBUDDY-C** — **Continuous-Wake-Word-Listening** (Porcupine.js
  on-device oder vergleichbares): kontinuierliches Hören, Trigger bei Wake-Wort
  ohne Knopf-Druck. Privacy-kritisch (Kinderzimmer) — eigene Berater-Runde
  fällig vor V2-Spec.
- **OPEN-KIBUDDY-D** — **LLM-Provider-Wechsel im Eltern-Chat** (analog
  OPEN-HSP-N): Inline-Befehl „wechsele kibuddy auf openai" patcht via
  `PATCH /api/v1/kibuddy/config`. V1 exposed den Endpoint nicht; Provider-
  Wechsel passiert über Config-Datei.
- **OPEN-KIBUDDY-E** — **Frage-/Antwort-Historie** für Eltern-Einsicht und
  Sokratisches Mitdenken über mehrere Runden hinweg. V1 ist zustandslos pro
  Frage (keine Konversations-Memory zwischen Fragen).
- **OPEN-KIBUDDY-F** — **Azure-Key-Verwaltung in der Plattform-Schicht** (analog
  OPEN-HSP-M): heute per-App-ENV nach CONFIG-1/CONFIG-3, Plattform-Layer ist
  ein Lego-Punkt der KIBuddy-getriggerten Berater-Runde (RAT-6-„LLM-Gateway").
- **OPEN-KIBUDDY-G** — **Antwort-Cache** (idempotente Fragen → gemerkte
  Antwort): Kostensenkung + Resilienz. V1 ruft je Frage frisch.
- **OPEN-KIBUDDY-H** — **Persistenter Verlauf über View-Reload** und
  Eltern-Einsicht: V1 hat Mehrturn-Konversation in Session-Memory am
  Service (KIBUDDY-16), aber **nicht** persistent auf Platte. View-Reload
  oder Service-Neustart löscht den Verlauf. V2-Pfad bedient Eltern-
  Einsicht und „weiter wo wir aufgehört haben"-Resume.
- **OPEN-KIBUDDY-I** — **Lemmatisierung/Stemmer für Buzzword-Icon-Lookup**:
  V1 verlässt sich darauf, dass der LLM-Output (`buzzwords[3]` aus T865-Refactor)
  bereits Grundform-Wörter liefert (System-Prompt fordert „Substantiv/Verb/
  Adjektiv im Singular"). Wenn der LLM doch flektiert (z. B. „Häuser" statt
  „Haus") trifft ICONS-7 das Lemma ggf. nicht — Lemma-Schicht im Backend
  ist V2.

---

## 1. Die App & ihre View

### KIBUDDY-1 — KIBuddy ist eine App mit eigenem Besitz
Der KIBuddy ist die XBuddy-App mit dem Buddy-Slug `kibuddy`. Er besitzt
seine **Daten** (Prompt, Voice-Wahl, Provider-Config, Aufnahme-Quelle,
KIBUDDY-21), seine **Funktion** (STT → LLM → Icon-Wort-Render → TTS,
Abschnitte 4–8) und stellt das Ergebnis über seine **Display-View**
bereit (APP-1). Er stellt eine API für den Eltern-Chat-Skill bereit
(BUD-1b, KIBUDDY-23).

### KIBUDDY-2 — Single-Page-View `frage`
Die View liegt unter `/display/kibuddy/frage` (BUD-1, URL-2) und ist **eine
Canvas** mit drei Zonen: oben ein neutraler Header-Bereich (Stand „bereit"
oder „antworte gerade"), Mitte die Antwort-Anzeige (Text + Icons), unten ein
großer **Push-to-Talk-Knopf**. Kein Routing zu Sub-Seiten, keine
Menüführung — statische Frage-Anzeige (KIBUDDY-3). Statische Assets unter
`/display/kibuddy/static/<asset>` (URL-13); Icon-PNGs kommen aus
`/display/_shared/icons/arasaac/<id>.png` (ICONS-5), **nicht** aus einem
buddy-eigenen Cache (Greenfield-Schnitt, ablöst den Pre-xbuddy-Vorläufer).

### KIBUDDY-3 — Touch-Bedienung, zwei Aktionen
Die View ist für ein Touch-/Kiosk-Display gebaut. Es gibt **zwei** Bedien-
Aktionen für das Kind:
1. Der **Push-to-Talk-Knopf** zum Sprechen einer Frage (KIBUDDY-7).
2. Der **Reset-Knopf** im Header zum Löschen der Konversation und des
   LLM-Token-Kontexts (KIBUDDY-29).
Kein Hover, keine Settings, kein anderer Verlauf.

### KIBUDDY-4 — Initial-Zustand
Wenn die View neu geladen wird oder die letzte Frage länger als die
**Inaktivitäts-Schwelle** (KIBUDDY-21, Default 60 s) zurückliegt, **dann**
zeigt die View den **Initial-Zustand**: Header neutral („Drück mich, wenn
du eine Frage hast"), Antwort-Bereich leer, Push-to-Talk-Knopf gross zentral.

*Test-Implikation:* GET `/display/kibuddy/frage` rendert (a) den Push-to-
Talk-Knopf, (b) den neutralen Header-Text, (c) keinen Antwort-Inhalt.

## 2. Audio-Aufnahme — Push-to-Talk-UX (Messenger-Style)

### KIBUDDY-5 — Aufnahme-Quelle V1 ist das Display selbst — Hardware-agnostisch
V1 nimmt das Audio **am Display-Gerät** auf, im Browser des Display-Clients
(DC-2) — **unabhängig vom Hardware-Typ des Display-Geräts** (Pi-Kiosk-Chromium,
Tablet-Browser, PWA-Standalone, Monitor-Browser). Der Browser holt das Mikro
über `navigator.mediaDevices.getUserMedia({audio: true})` (browser-nativ,
secure-context-pflichtig — siehe URL-11 Selfsigned/Tailnet-Funnel). Die
Aufnahme-Quelle ist in der App-Config einstellbar (`aufnahme-quelle:
display|panel`, KIBUDDY-21); V1 implementiert **nur** `display`. Der Wert
`panel` ist konfigurierbar, aber die Renderlogik fällt dann auf einen Hinweis
„Panel-Mikro V2" zurück (KIBUDDY-22). Vollständiger Panel-Pfad ist
OPEN-KIBUDDY-A.

**Pi-Display-Disziplin:** KIBuddy-Code enthält **keinen Pi-Sonder-Pfad** —
weder Hardware-Erkennung noch Pi-spezifische Audio-Adapter. Wenn der Pi-
Chromium-Kiosk Mikro-Zugang braucht (USB-Mikro, ALSA, sonst), passiert das
**außerhalb** des KIBuddy-Codes über einen **Pi-Display-Adapter** (Komponente
neben dem Display-Client, nicht hier spezifiziert — KIBuddy bleibt für den
Browser eine reine Web-View). Falls auf Pi der `getUserMedia`-Pfad scheitert
(Permission-Block, Mikro-Treiber, Self-Signed-Cert-Issue), ist das ein
**Pi-Display-Adapter-Ticket**, kein KIBuddy-Ticket.

### KIBUDDY-6 — Mikro-Erlaubnis und Fallback bei Verweigerung
Beim ersten Druck auf den Push-to-Talk-Knopf fordert die View die Mikro-
Erlaubnis über die Browser-Standard-Permission an. **Wenn** die Erlaubnis
verweigert oder per Browser-Setting blockiert ist, **dann** zeigt die View
einen freundlichen Hinweis-Bereich („Ich darf gerade nicht zuhören") mit
einem Eltern-tauglichen Hinweis zur Erlaubnis-Erteilung, der **kein Kind
verstehen muss** (Constitution: nicht-invasiv). Kein Modal, kein
blockierendes Overlay — die View bleibt benutzbar (Re-Versuch durch
erneuten Knopf-Druck).

### KIBUDDY-7 — Push-to-Talk in Messenger-Bedienform
Der Push-to-Talk-Knopf ist die einzige Bedien-Aktion (KIBUDDY-3) und folgt
einem Messenger-Bedienschema:

**Eingabe-Modus A — Tap-and-Hold:**
- **Wenn** das Kind den Knopf drückt und gedrückt hält, **dann** beginnt die
  Aufnahme **sofort** mit dem Druck-Beginn und endet **mit dem Loslassen**.
- Während des Haltens läuft eine sichtbare Pegel-Anzeige (KIBUDDY-9).

**Eingabe-Modus B — Tap-und-Slide-to-Lock:**
- **Wenn** das Kind den Knopf drückt und **nach oben** über eine
  **Schwellen-Distanz** (KIBUDDY-21, Default **30 px** — T864-AC1: war 80) hinaus zieht, **dann**
  „rastet" die Aufnahme **ein**: sie läuft auch nach dem Loslassen weiter.
- Im eingerasteten Zustand ersetzt ein **Stopp-Knopf** an der Slide-Ziel-
  Position den Push-to-Talk-Knopf (KIBUDDY-8 Visual).
- **Wenn** der Stopp-Knopf gedrückt wird, **dann** endet die Aufnahme.

**Beide Modi haben dieselbe Wirkung:** das aufgenommene Audio wird nach
Aufnahme-Ende sofort an den STT-Endpunkt (KIBUDDY-24) gepostet.

**VAD-Auto-Stop im Lock-Modus:** Im Lock-Modus erkennt das System
Sprech-Pausen automatisch via RMS-Pegel-Threshold und beendet die
Aufnahme bei `vad.stille-sek` Stille (KIBUDDY-21); manueller Stopp-Knopf
bleibt Override.

**Lock-Auslösung:** Lock-Modus kann ausgelöst werden via (a) Slide nach oben
über `LOCK_DISTANZ_PX` (30 px) ODER (b) Long-Hold: nach
`vad.long-hold-lock-sek` (Default 3.0 s) automatisch ohne Slide-Geste.
(T864-AC1/AC2)

**Mindest-Aufnahme-Dauer:** Aufnahmen kürzer als `aufnahme.min-sek`
(Default 0.5 s) werden verworfen — kein STT-Aufruf, kein LLM-Aufruf.
Sichtbare Hinweis-Bubble „Bitte sprich etwas lauter und länger" für 4 s.
(T864-AC3)

**Wenn** die Aufnahme länger als die **Maximum-Aufnahme-Dauer** (KIBUDDY-21,
Default 30 s) läuft, **dann** endet sie automatisch und wird normal
verarbeitet (Kinder-Resilienz, keine Endlos-Aufnahme).

### KIBUDDY-8 — Visuelles Feedback im Druck-Moment (sofort, nicht erst beim Aufnahme-Start)
Im **Moment des Drucks** (vor dem Beginn der Aufnahme-Pegel-Anzeige) zeigt
der Knopf ein **sofortiges visuelles Echo**: Skalierung leicht vergrößert
(`transform: scale(1.06)`) plus farbliche Aktiv-Markierung (Token
`--color-accent-active` oder gleichwertig im DTOK-Strang). Dieser Echo-Schritt
ist eigenständig von KIBUDDY-9 — er muss schon dann sichtbar sein, wenn die
Mikro-Erlaubnis noch geprüft wird oder das Audio-Stream-Setup läuft (Wirkung:
„ich sehe, du drückst mich"). Verzögerungs-Obergrenze: **<50 ms** zwischen
Touch-Down und Echo (perception threshold).

### KIBUDDY-9 — Pegel-Anzeige: symmetrisch um den zentral mittigen Knopf, ab Druck-Beginn
**Wenn** die Aufnahme aktiv ist (sowohl Tap-Hold als auch Lock-Modus), **dann**
zeigt die View eine **horizontale Balken-Pegel-Visualisierung** gespeist aus
dem `AudioContext`-AnalyserNode der laufenden Aufnahme. Position: **symmetrisch
links UND rechts des zentral mittigen Mikro-/Stopp-Knopfes** in derselben
Mikro-Zone. Der **Knopf bleibt fest in der Mitte der Mikro-Zone** —
unabhängig davon, ob die Pegel-Balken sichtbar sind oder nicht. Der Pegel
verdrängt den Knopf NICHT aus der Mitte. **Nicht** im Chat-/Antwort-Bereich.

Sichtbarkeit: **ab dem Druck-Beginn** (gleichzeitig mit dem Echo aus
KIBUDDY-8), **nicht erst** beim Lock-Übergang. Visuelles Ziel: dem Kind zeigen
„ich höre dich gerade", ohne den Chat-Verlauf zu verdecken.

### KIBUDDY-10 — Slide-to-Lock-Hinweis: V1 ENTFERNT
**V1-Setzung (2026-06-15 Nic-Live-Befund #3):** Der Slide-to-Lock-Hinweis
ist in V1 **komplett entfernt** — der Pfeil-Glyph ragte ins Chat-Fenster
und war im Weg. Long-Hold-Auto-Lock (KIBUDDY-7 / T864-AC2: nach 3 s im
recording-State automatisch einrasten) ersetzt das visuelle Slide-Feedback;
Eltern erklären den Slide-Lock-Mechanismus dem Kind verbal.

Historie der Reduktion:
- ursprünglich: Pfeil `↑` + Schloss-Pikto (ARASAAC 3261)
- 2026-06-15 erster Schritt: Schloss-Pikto ausgeblendet (Pikto im Weg)
- 2026-06-15 zweiter Schritt: kompletter Hinweis entfernt (Pfeil ragte in Chat)

Folge-V2-Möglichkeiten (OPEN): wenn der Hinweis später wieder erwünscht
ist, gehört er **außerhalb** des Chat-Fensters (z. B. seitlich neben dem
PTT-Knopf), nicht darüber.

### KIBUDDY-11 — Aufnahme-Abbruch durch Slide-nach-Unten
**Wenn** das Kind während des Tap-Hold-Modus den Finger **nach unten** über
die **Abbruch-Distanz** (KIBUDDY-21, Default 60 px — T864-AC1 proportional zu Lock-Distanz) hinaus zieht, **dann**
wird die Aufnahme **verworfen** (kein POST an STT). Visuell signalisiert
durch eine **Mülleimer-Marke** an der Slide-Ziel-Position. Default-WhatsApp/
Telegram-Konvention. Im Lock-Modus existiert dieser Pfad nicht (dort ist der
Stopp-Knopf das Ende).

## 3. STT — Sprache zu Text

### KIBUDDY-12 — STT über OpenAI-API direkt oder Azure-OpenAI Whisper, Provider-Switch analog KIBUDDY-14
Der KIBuddy hat einen **App-eigenen STT-Adapter**, der das aufgenommene Audio
(WebM/Opus oder vom Browser geliefertes Container-Format) transkribiert und
den Transkript-Text zurückgibt. Sprache `de` als Default; Sprache ist
Config (KIBUDDY-21). Zwei STT-Anbieter-Pfade stehen zur Wahl (`stt_provider`,
KIBUDDY-21):

- **`openai`** (V1-Default): **OpenAI-API direkt** mit `whisper-1`. Kinderstimmen-
  Qualität in der Vorläufer-App (Port 5006, Pre-xbuddy) belegt — dieser Pfad
  war dort produktiv und hat sich bewährt. ENV: `OPENAI_API_KEY`.
- **`azure_openai`**: Azure-OpenAI Whisper in der Region `swedencentral`
  (gleicher Region-Standard wie HSP-19/HSP-23). ENV: `AZURE_OPENAI_ENDPOINT`
  + `AZURE_OPENAI_API_KEY`.

Der Adapter-Schnitt folgt dem LLM-Provider-Switch (KIBUDDY-14): ein konkreter
STT-Adapter implementiert `transkribiere(audio_bytes, filename)` und wirft
`STTError` bei Anbieter-Fehler. `stt_service.py` ist provider-agnostisch.

### KIBUDDY-12-H — Whisper-Stille-Halluzinationen werden gefiltert (#952)
Whisper-Trainings-Daten enthielten viele YouTube-DE-Untertitel mit
Bauch-Klauseln. Bei stillem oder sehr kurzem Audio liefert Whisper statt
eines leeren Strings eine dieser Phrasen — z. B. „Untertitelung des
ZDF, 2020", „Untertitel im Auftrag von Funk", „Untertitel der
Amara.org-Community", „Vielen Dank fürs Zuschauen", „Music". Diese
Halluzinationen würden als echte Frage ans LLM gehen und KIBuddy zu
Phantom-Antworten verleiten.

`stt_service.ist_stille_halluzination(text)` prüft zwei Klassen:

1. **Exakter Match** (normalisiert) gegen eine Liste bekannter
   Komplett-Phrasen.
2. **Substring-Match** auf eindeutige Indikatoren („untertitelung",
   „im Auftrag des ZDF", „im Auftrag von Funk", „amara.org",
   „stephanie geiges"), die ein Kind (4–7) nicht selbst formuliert.

Der Frage-Endpunkt ruft den Filter direkt nach `transkribiere()` auf
und liefert bei Halluzinations-Treffer denselben Fehler-Pfad wie bei
leerem Transkript: NDJSON `{"event":"error","stage":"stt",
"detail":"transkript leer — konnte die Frage nicht verstehen"}`. Das
Frontend zeigt den existierenden `mikro-fehler`-Hint
(„Ich darf gerade nicht zuhören.") und resettet die Eingabe — kein
LLM-Call, keine Phantom-Antwort.

**Bewusste Engstelle:** Substring „zdf" oder „funk" allein filtert
NICHT — Kinder-Fragen wie „Was ist das ZDF?" oder „Was ist Funk?"
gehen normal durch. Nur Phrasen, die Kinder nie verwenden
(„im Auftrag", „Untertitelung", „Amara.org"), lösen den Filter aus.

### KIBUDDY-13 — Streaming-Reveal: STT-Phase synchron, LLM+TTS-Phase progressiv
V1 verarbeitet eine Frage als **NDJSON-Chunked-Stream**: die View postet das
Audio per `POST /api/v1/kibuddy/frage` (KIBUDDY-24) und liest die Response
als ReadableStream.

**Stage 1 (kind):** STT läuft synchron im ersten Chunk. Sobald das Transkript
vorliegt (~1–2 s), liefert der Server sofort die erste NDJSON-Zeile
`{"event":"kind","transkript":"...","transkript_words":[...]}`. Das Frontend
rendert die Kind-Bubble direkt daraus — ohne auf LLM zu warten.

**Stage 2 (buddy):** LLM + TTS laufen danach. Wenn fertig, sendet der Server
die zweite NDJSON-Zeile `{"event":"buddy","text":"...","buzzwords":[...],"tts_audio_url":"..."}`.
Das Frontend rendert die Buddy-Bubble (Text + Buzzword-Block, KIBUDDY-17) und spielt TTS-Audio ab.

**Lade-Bubble:** bleibt sichtbar zwischen Stage 1 und Stage 2, verschwindet
erst nach Stage 2 (oder bei Fehler-Event).

Wort-für-Wort-Render innerhalb einer Bubble ist V2-Pfad (Wort für Wort mit
Scroll-Effekt); V1 rendert jede Bubble komplett nach Empfang des Events.

## 4. LLM — Antwort-Generierung

### KIBUDDY-14 — Eigener LLM-Adapter mit Provider-Switch
Der KIBuddy hat einen **App-eigenen LLM-Adapter** mit Provider-Switch
analog HSP-19 (Hörspiel-Buddy). V1 implementiert **nur** `claude` als
Provider (Modell-Wahl in Config, Default `claude-haiku-4-5` oder
`claude-sonnet-4-6` — Kosten/Latenz-Abwägung, Nic entscheidet). Der
Provider-Switch ist als Code-Pfad **vorhanden**, weitere Provider werden
nicht antizipiert (CLAUDE.md §6 — keine Vorrat-Abstraktion); zweiter
Provider entsteht erst bei OPEN-KIBUDDY-D / OPEN-KIBUDDY-F-Trigger.

### KIBUDDY-15 — Prompt aus Per-Instanz-Daten, lese- und schreibbar zur Laufzeit
Der System-Prompt liegt als Per-Instanz-Datei (`/home/buddy/xbuddy-data/
kibuddy/prompt.txt` o. ä.) und wird beim Service-Start eingelesen.
Default-Prompt ist der bestehende Pre-xbuddy-KIBuddy-Prompt (Sokratisch,
kindgerecht, „2–4 Sätze pro Antwort"). Der Prompt ist **kein** Code, er
ist Per-Instanz-Daten (analog Welt-Bible des Hörspiel-Buddy, HSP-25a).

**Laufzeit-Lese-/Schreibzugriff:** Der Prompt ist über die HTTP-API
zu lesen (`GET /api/v1/kibuddy/prompt`) und zu schreiben (`PUT
/api/v1/kibuddy/prompt`), siehe KIBUDDY-24. Eine Schreibwirkung
ist **sofort wirksam** — der nächste LLM-Aufruf nutzt den neuen
Prompt. Es ist keine Service-Reload nötig (der Dateiinhalt wird je
LLM-Call frisch gelesen oder ein In-Memory-Cache wird auf PUT
invalidiert; die Implementation entscheidet die Form, der Vertrag ist
„nächster Call → neuer Prompt"). Der Schreibpfad wird vom
Eltern-Chat-Skill `kibuddy-prompt-anpassen` (KPA, KIBUDDY-23) bedient.

**Datei-Schutz:** Atomare Schreibung (Write-to-temp + Rename) gegen
halbe Dateien bei Fehlschlag (analog FAA-Schreibvorgängen). Vor jedem
PUT wird die alte Version als `prompt.txt.bak` gesichert (genau eine
Generation, je PUT überschrieben — Last-Known-Good für Notfall-Rollback
per `cp`).

### KIBUDDY-16 — Konversations-Kontext V1: Mehrturn mit Session-Memory
V1 fährt einen **fortlaufenden Mehrturn-Dialog**: je neuer Kind-Frage sendet
der Buddy den System-Prompt + **die vollständige Turn-Historie** der laufenden
Session (Kind-Frage + Buddy-Antwort, abwechselnd) + die neue Kind-Frage an
den LLM. Die Sokratische Prompt-Struktur lebt damit über mehrere Runden
hinweg (Vermutungs-Frage → Kind-Antwort → Wertschätzung + Erklärung → neue
Vermutungs-Frage), wie es der Prompt ohnehin vorsieht.

**Speicherort:** Session-Memory am Service (im RAM, je View-Session via
Browser-Cookie/SSE-Connection-ID), **nicht** persistent auf Platte. Bei
Service-Neustart oder Browser-Tab-Schließen geht der Kontext verloren —
das ist V1-akzeptiert (Privacy: kein Kinderzimmer-Audit-Log).

**Reset:** der Reset-Knopf (KIBUDDY-29) löscht den aktuellen Session-Kontext
komplett — sowohl die im Chat-Verlauf sichtbaren Turns als auch die
LLM-Token-Historie.

**Persistenter Verlauf** über View-Reload, Eltern-Einsicht oder per-Familien-
Profile bleibt OPEN (siehe OPEN-Liste).

## 5. Antwort-Render — Text + 3 Buzzword-Icons am Ende

### KIBUDDY-17 — Render-Schicht: Antwort-Text + 3 Buzzword-Icons am Ende

**Refactored 2026-06-15 (T865, Nic-Live-Befund Mikro-Test #3):**
Wort-für-Wort-Filter wurde durch LLM-generierte Buzzwords ersetzt.
Begründung: Wort-für-Wort-Filter traf oft nicht die Konzept-Bedeutung;
Verben wurden fälschlich als Funktionswörter ausgefiltert; LLM kann
pädagogisch passendere Buzzwords wählen als ein statischer Wortklassen-Filter.

**LLM liefert JSON-Output (System-Prompt-Pflicht):**
Der System-Prompt enthält eine JSON-Ausgabe-Anweisung, die das LLM zwingt,
ausschliesslich ein JSON-Objekt zurückzugeben:
```json
{
  "antwort": "<deine Antwort, vollständige Sätze, 2-4 Sätze>",
  "buzzwords": ["<wort1>", "<wort2>", "<wort3>"]
}
```
Genau 3 Buzzwords, jedes ein einzelnes deutsches Wort (Substantiv/Verb/Adjektiv),
lowercase, ohne Sonderzeichen. Kein Text ausserhalb des JSON.

**Backend-Parse + Fallback:** `parse_kibuddy_response()` in `llm_service.py`
extrahiert `antwort` und `buzzwords` aus dem JSON. Bei ungültigem JSON:
raw-Text als `antwort`, leere `buzzwords`-Liste.

**Render in der Buddy-Bubble:**
1. Antwort-Text als zusammenhängender Absatz (`<p class="buddy-antwort-text">`).
2. Direkt danach ein **Buzzword-Block** (`<div class="buzzword-block">`):
   drei Karten nebeneinander, je mit ARASAAC-Pikto aus ICONS-7-Lookup
   (`fetchIcon(wort)`) und Wort-Label darunter (`<div class="buzzword-label">`).

**Icon-Lookup:** 3 parallele ICONS-7-Requests (`Promise.all`) — deutlich
weniger Traffic als der frühere Wort-für-Wort-Lookup (0–15+ Requests).
Miss (kein ICONS-7-Treffer) → nur Wort-Label, kein Icon-Slot (kein Crash).

**Out-of-Scope V1:** animierte Buzzword-Reveal, alternative Icon-Quellen,
Buzzword-Konfiguration durch Eltern. Folge-Tickets bei Bedarf.

### KIBUDDY-18 — Icon-Lookup für Buzzwords ist „ehrlich-Single-Wort"
V1 sucht reinen Substring-Match über ICONS-7 mit jedem der drei vom LLM
gelieferten Buzzwords (KIBUDDY-17). Wörter mit Flexion treffen
**bewusst** nicht das Lemma — Lemmatisierungs-Schicht ist OPEN-KIBUDDY-I.

**Hinweis nach T865-Refactor (2026-06-15):** Da der System-Prompt explizit
Grundform-Buzzwords fordert (Substantiv/Verb/Adjektiv im Singular), greift
diese Klausel in der Praxis selten — der LLM liefert typisch schon
lemma-nahe Buzzwords. Bleibt als Vertragsklarstellung für die Fälle, wo
der LLM doch flektiert. Sichtbare Folge: eines der drei Buzzwords kann
kein Icon haben (`fetchIcon(buzzword)` gibt null zurück → nur Label
gerendert, kein `<img>`).

### KIBUDDY-19 — Chat-Verlauf-Container, Scroll innen, Reset löscht alles
Der Chat-Verlauf lebt in einem **eigenen scrollenden Container** in der
Mitte der View — die **Seite selbst scrollt nicht** (`html, body {
overflow: hidden }`), nur der Chat-Container (`.chat { overflow-y: auto }`).
Jeder Turn besteht aus:
- einer **Kind-Bubble** (rechts ausgerichtet) und
- einer **Buddy-Bubble** (links ausgerichtet).

**Kind-Bubble — V1 Option C (T865): text-only.**
Rendert das STT-Transkript als reinen Text-Absatz (`<p class="kind-frage-text">`).
KEIN Wort-für-Wort-Render mit Icons (Begründung: das Kind hat die Frage gerade
selbst gesagt — Icons bei der Antwort genügen für die Lese-Vorbereitung).
`transkript_words[]` wird vom Backend als Diagnose-Feld weiter geliefert,
aber das Frontend ignoriert es.

**Buddy-Bubble:** Antwort-Text als Absatz + 3-Buzzword-Block am Ende (KIBUDDY-17).

**Beide Bubbles** tragen den **Vorlese-Knopf** (KIBUDDY-31).

Neuer Turn am Ende, alte Turns scrollen nach oben weg. Der Container scrollt
auf neuen Turn automatisch nach unten (`scrollTop = scrollHeight`).

**Bei Inaktivität >= Inaktivitäts-Schwelle (KIBUDDY-21, Default 60 s)**
ohne Bedien-Aktion **bleibt** der Chat sichtbar (Eltern können nachlesen);
der Header-Status fällt aber auf „bereit" zurück und der Buddy schläft
audio-mäßig (keine TTS-Wiederholung). Reset passiert **nur** über den
Reset-Knopf (KIBUDDY-29), nicht über Timer — das Kind soll seinen
Konversations-Verlauf nicht unter den Fingern verlieren.

## 6. TTS — Antwort vorlesen

### KIBUDDY-20 — TTS über Azure-OpenAI TTS-HD, Provider-Konfig wie Hörspiel, Voice-/Speed-Wahl bewusst anders
Der KIBuddy hat einen **App-eigenen TTS-Adapter** analog HSP-13/HSP-15.
**Provider-Konfig identisch zum Hörspiel-Buddy:** Azure-OpenAI in der Region
`swedencentral` (HSP-13), Modell `tts-1-hd`.

**Voice-Wahl V1 — `onyx` als Default:** tief, männlich (HSP-13). Andere
Stimmen über Config änderbar (`shimmer`, `echo`, `fable`, `onyx`, `alloy`,
`nova` — OpenAI-TTS-HD-Set, KIBUDDY-21).

**Geschwindigkeit V1 — `speed = 0.9`, bewusste Abweichung vom Hörspiel-Stil:**
Hörspiel setzt `speed = 1.0` und vermeidet bewusst Time-Stretching (HSP-15
„post-hoc Time-Stretching erzeugt Artefakte"). KIBuddy weicht in V1 davon
ab: ein etwas langsamerer Vortrag (`0.9`) ist für Wissens-Antworten an
Kinder eine **Verständnis-Hilfe** und überwiegt die hörbare leichte Audio-
Artefakt-Erzeugung der TTS-API. Sichtbar wahrnehmbare Artefakte gehen in
einen Config-Override (Familie kann auf `1.0` zurück), nicht in ein
Codepfad-Sondergetue.

Die Synthese läuft **synchron** im selben Request wie LLM (KIBUDDY-13).
Das fertige Audio wird in einem **TTS-Audio-Cache** abgelegt (Disk unter
`<data>/audio/<id>.mp3`, `<id>` = SHA-Hash über `(text, stimme, speed)`,
also content-adressiert und automatisch dedupliziert). Die Frage-Response
liefert nur die URL `/api/v1/kibuddy/audio/<id>.mp3` (siehe KIBUDDY-24).
Der Cache ist **nicht persistent** über Service-Neustart hinaus (analog
KIBUDDY-16 Session-Memory): beim systemd-Start wird das Verzeichnis
geleert. Bei Reset (KIBUDDY-29) werden ebenfalls alle Cache-Einträge
gelöscht. LRU/TTL ist V2 (OPEN-KIBUDDY-K). Der Client spielt das Audio
direkt nach Empfang über `<audio src="…">` ab — **synchron zum Render-
Beginn** der Text-Antwort (parallel, nicht nacheinander; das Kind sieht
den Text aufgebaut werden und hört gleichzeitig die Stimme).

**Lego-Punkt:** der TTS-Adapter trägt **denselben Provider-Schnitt** wie
der Hörspiel-Buddy-TTS-Adapter (HSP-13). Die Wiederholung ist V1-bewusst
kopierend (RAT-6 „kopieren statt generalisieren bis 2.–3. Beitrag"); der
**Trigger** für eine gemeinsame TTS-Adapter-Schicht ist mit diesem Buddy
erreicht und Gegenstand einer **Folge-Berater-Runde** nach der Werft (Werft-
Annahme 3: Berater-Runde **nach** V1-Bau). Die Speed-Abweichung ist die
**erste belegte Voice-Konfig-Variation zwischen zwei Buddies** — sie hilft,
in der Berater-Runde den richtigen Generalisierungs-Schnitt zu legen
(Provider-Layer ja, Voice/Speed bleibt App-Sache).

## 7. Konfiguration & Datenhaltung

### KIBUDDY-21 — Konfigurations-Werte mit Default und Override
| Feld | Default | Wirkung | Override |
|---|---|---|---|
| `prompt-pfad` | `<data>/prompt.txt` | System-Prompt-Datei | `KIBUDDY_PROMPT_PATH` ENV oder Config |
| `prompt.max-bytes` | `50000` | Max-Größe für PUT /prompt (KIBUDDY-24) | Config |
| `llm.provider` | `claude` | LLM-Provider | Config; V1 nur `claude` |
| `llm.modell` | `claude-haiku-4-5` | Modell-Wahl | Config |
| `stt.provider` | `openai` | STT-Anbieter-Wahl (`openai` oder `azure_openai`, KIBUDDY-12). Code-Identifier: `stt_provider`. | Config; ENV `KIBUDDY_STT_PROVIDER` |
| `stt.modell` | `whisper-1` | Whisper-Modell-Variante | Config |
| `stt.sprache` | `de` | STT-Sprache | Config |
| `tts.stimme` | `onyx` | TTS-Voice | Config |
| `tts.modell` | `tts-1-hd` | TTS-Modell | Config |
| `tts.speed` | `0.9` | TTS-Geschwindigkeit (KIBUDDY-20) | Config |
| `aufnahme-quelle` | `display` | Wo nehmen wir auf | KAQS-Skill (KIBUDDY-23), Eltern-Chat |
| `aufnahme.max-sek` | `30` | Max. Aufnahme-Dauer | Config |
| `aufnahme.inaktivitaet-sek` | `60` | Header-Schlaf-Schwelle (Chat bleibt) | Config |
| `ui-icons` | `<data>/ui-icons.json` | UI-Icon-ID-Mapping (KIBUDDY-30) | Config |
| `ui.lock-hinweis-ms` | `800` | Slide-Hinweis erscheint nach | Config |
| `vad.stille-sek` | `1.5` | VAD-Stille-Schwelle (Sekunden) im Lock-Modus | Config |
| `vad.threshold-db` | `-50` | VAD-Pegel-Schwelle (dB) — unter Schwelle = Stille | Config |
| `vad.long-hold-lock-sek` | `3.0` | Auto-Lock nach langem Halten (KIBUDDY-7/T864-AC2) | Config |
| `aufnahme.min-sek` | `0.5` | Mindest-Aufnahme-Dauer — kürzere Aufnahmen verwerfen (KIBUDDY-7/T864-AC3) | Config |
| `azure.openai-endpoint` | (ENV-Pflicht) | Azure-OpenAI-Endpunkt | `AZURE_OPENAI_ENDPOINT` |
| `azure.openai-key` | (ENV-Pflicht) | Azure-OpenAI-Key | `AZURE_OPENAI_API_KEY` |
| `anthropic.api-key` | (ENV-Pflicht) | Anthropic-Key für `claude` | `ANTHROPIC_API_KEY` + ZD-Slot `kibuddy-anthropic-api-key` (seit T1082, LLMP-5) |

**Migrations-Notiz T1082:** KIBuddy ruft den LLM-Provider seit T1082 über
`tools.llm.get_chat(slot="kibuddy-anthropic-api-key")`. Der ZD-Slot wird
durch `tools/sync_kibuddy_env.py` aus der KEY_FALLBACKS-Quelle gespiegelt
(`_sync_llm_slots()`, additiv-rückrollbar). Pflicht-Schritt bei Deploy +
nach jedem Update der Zugangsdaten: `python3 tools/sync_kibuddy_env.py`
laufen (analog `sync_hoerspiel_env.py`).

Per-Instanz-Daten leben unter `/home/buddy/xbuddy-data/kibuddy/` (analog
SVC-5 / RAT-14b1): `prompt.txt`, `config.json`. **Keine** Familien-
spezifischen Daten — KIBuddy ist familien-agnostisch in V1 (eine Familie,
ein Prompt; per-Familien-Profile sind OPEN-KIBUDDY-J im Backlog, nicht
in der V1-Out-of-Scope-Liste explizit zu markieren).

### KIBUDDY-22 — Aufnahme-Quelle `panel` ist V1 nicht implementiert
**Wenn** `aufnahme-quelle` auf `panel` steht, **dann** zeigt die View einen
Hinweis-Bereich („Mikro am Panel — V2-Funktion") statt des Push-to-Talk-
Knopfs und stellt den Knopf nicht bereit. Klare Fail-Closed-Semantik: keine
stille Halb-Funktion. Vollständiger Panel-Pfad ist OPEN-KIBUDDY-A.

## 8. Familien-Schnittstelle — Zwei Eltern-Chat-Skills

### KIBUDDY-23 — Familien-Schnittstelle-Beitrag (APP-4)
Der KIBuddy stellt **zwei** Eltern-Chat-Skills bereit:

1. **`aufnahme-quelle-setzen`** (eigene Plattform-Spec
   `specs/platform/kibuddy-aufnahme-quelle-setzen.md`, ID-Präfix KAQS).
   Wirkung: ein Elternteil ändert per Chat-Befehl die Aufnahme-Quelle
   zwischen `display` und `panel` (KIBUDDY-21). Schreibpfad: `PUT
   /api/v1/kibuddy/config` mit `{aufnahme-quelle: "display"|"panel"}`.
2. **`kibuddy-prompt-anpassen`** (eigene Plattform-Spec
   `specs/platform/kibuddy-prompt-anpassen.md`, ID-Präfix KPA). Wirkung:
   ein Elternteil verfeinert per **sokratischem Mehrturn-Dialog** mit dem
   Bot den System-Prompt des KIBuddys (KIBUDDY-15), sieht eine **Diff-
   Vorschau** und schreibt nach Bestätigung den neuen Prompt. Lesepfad:
   `GET /api/v1/kibuddy/prompt`, Schreibpfad: `PUT
   /api/v1/kibuddy/prompt`.

Beide Skills aktivieren sich über den bestehenden TASK-7-`build_catalog`-
Pfad (analog RZS-5).

Note V1-Akzeptanz KAQS: weil `panel` heute kein implementierter Aufnahme-
Pfad ist (KIBUDDY-22), ist der Skill in V1 **funktional eingeschränkt** —
er kann zwar `panel` setzen, aber die View bleibt im Hinweis-Zustand. Das
ist eine bewusste **Interface-first-Auslage**: die Spec exposed jetzt die
volle API-Schnittstelle, der Konsum-Pfad zieht in V2 nach (Werft-Disziplin
Interface-first).

## 9. HTTP-Schnittstelle

### KIBUDDY-24 — Endpoint-Übersicht
| Methode | Pfad | Beschreibung | Konsumenten |
|---|---|---|---|
| `GET` | `/display/kibuddy/frage` | Frage-View | Display-Client |
| `POST` | `/api/v1/kibuddy/frage` | Audio rein → Text+Audio raus | Frage-View (clientseitig) |
| `GET` | `/api/v1/kibuddy/audio/<id>.mp3` | MP3-Datei aus TTS-Audio-Cache (Cache-Mechanik in KIBUDDY-20) | Frage-View (Vorlese-Knopf, KIBUDDY-31) |
| `POST` | `/api/v1/kibuddy/vorlesen` | Text-zu-TTS für Vorlese-Knopf (KIBUDDY-31) | Frage-View (clientseitig) |
| `POST` | `/api/v1/kibuddy/reset` | Session-Konversation + Audio-Cache löschen (KIBUDDY-29) | Frage-View (clientseitig) |
| `GET` | `/api/v1/kibuddy/config` | Aktuelle Config (ohne Keys) | KAQS-Skill, Diagnose |
| `PUT` | `/api/v1/kibuddy/config` | Aufnahme-Quelle setzen | KAQS-Skill |
| `GET` | `/api/v1/kibuddy/prompt` | Aktuellen System-Prompt lesen (KIBUDDY-15) | KPA-Skill, Diagnose |
| `PUT` | `/api/v1/kibuddy/prompt` | Neuen System-Prompt schreiben (KIBUDDY-15) | KPA-Skill |

**POST `/api/v1/kibuddy/frage`** — Multipart-Form mit `audio` (Browser-
Container, WebM/Opus oder MP4). Response: `Content-Type: application/x-ndjson`,
`Transfer-Encoding: chunked`, **zwei NDJSON-Zeilen** (KIBUDDY-13):

```
{"event":"kind","transkript":"<STT-Erkennung>","transkript_words":[]}
{"event":"buddy","text":"<LLM-Antwort>","buzzwords":["<w1>","<w2>","<w3>"],"tts_audio_url":"/api/v1/kibuddy/audio/<id>.mp3"|null}
```

**Stage 1 — kind-Event** (sofort nach STT, vor LLM-Aufruf):
- `transkript`: STT-Erkennung als Fließtext.
- `transkript_words`: Diagnose-Feld, bleibt im Schema erhalten. V1 liefert
  eine leere Liste — Wortklassen-Tokenisierung entfällt (T865). Frontend
  ignoriert das Feld (Kind-Bubble text-only, KIBUDDY-19).

**Stage 2 — buddy-Event** (nach LLM+TTS):
- `text`: LLM-Antwort als Fließtext (aus JSON-Antwort des LLM geparst).
- `buzzwords`: string-Liste mit max. 3 Buzzwords (aus JSON-Antwort des LLM,
  sanitisiert durch `validate_buzzwords()`). Bei LLM-Fallback: leere Liste.
- `tts_audio_url`: URL oder `null` bei TTS-Fehler.
- `words[]` entfällt (T865 Buzzword-Refactor).

Bei STT-Fehler (vor Stage 1): kein `kind`-Event, stattdessen einzeilige
Fehler-Response `{"event":"error","stage":"stt","detail":"..."}` (HTTP 200,
Stream-Level-Fehler — Client prüft `event`-Feld).

Bei LLM-Fehler (nach Stage 1): `kind`-Event wurde bereits gesendet; es folgt
`{"event":"error","stage":"llm","detail":"..."}` — Kind-Bubble ist sichtbar,
Buddy-Bubble fehlt.

Bei TTS-Fehler: Stage-2-Zeile trägt `tts_audio_url: null` (Resilienz —
Kind sieht zumindest die Text-Antwort).

URL-Form ermöglicht Browser-Cache + Replay über KIBUDDY-31
ohne JS-State-Bloat im Chat-Verlauf (KIBUDDY-19); analog Hörspiel-Folgen-URLs.

**PUT `/api/v1/kibuddy/config`** — JSON-Body, schreibt das spezifizierte
Feld in die Per-Instanz-`config.json`. V1 akzeptiert nur das Feld
`aufnahme-quelle`. Andere Felder werden **abgelehnt** (HTTP 400) — die
volle Config-Schreibung ist V2 (OPEN-KIBUDDY-D).

**GET `/api/v1/kibuddy/prompt`** — Response: JSON `{ "prompt": "<voller
Prompt-Text>", "byte-laenge": <int>, "geaendert-am": "<ISO-Zeitstempel
der letzten Schreibung>" }`. Liefert immer den **aktuell wirksamen**
Prompt (was beim nächsten LLM-Call benutzt wird). Read-only.

**PUT `/api/v1/kibuddy/prompt`** — JSON-Body `{ "prompt": "<neuer
Prompt-Text>" }`. Wirkung: atomare Datei-Schreibung der
`prompt.txt` (Write-to-temp + Rename), die bisherige Version wandert
nach `prompt.txt.bak` (eine Generation, je PUT überschrieben — Last-
Known-Good, KIBUDDY-15). **Validierung:** der Prompt-Text muss
nicht-leer sein (`len(text.strip()) > 0`) und unter der
**Maximum-Prompt-Länge** liegen (Default 50 000 Bytes, KIBUDDY-21).
Andere Felder im Body werden ignoriert. Response: JSON
`{ "ok": true, "byte-laenge": <int>, "bisherige-laenge": <int> }`.
Fehler-Pfade: HTTP 400 bei leerem oder zu langem Prompt; HTTP 500
bei Schreibfehler (Disk voll, Permission) — dann bleibt der **alte
Prompt** wirksam (kein halbtoter Zustand). Idempotenz: PUT mit
identischem Text ist erlaubt und wirkt als Touch (Backup-Datei wird
trotzdem aktualisiert, Last-Known-Good ist immer der vorletzte
Stand).

## 10. Registrierung & Auslieferung

### KIBUDDY-25 — Slug, Port, URL-Eintrag
- **Slug:** `kibuddy` (BUD-1).
- **Port:** **5054** (nächste freie Nummer im Reserve-Block PORT-2, mit
  Eintrag in `conventions/ports.md`).
- **Service:** `xbuddy-kibuddy` (BUD-1a, SVC-1/SVC-2/SVC-3/SVC-4).
- **URL-Tabelle:** `/display/kibuddy/` → `127.0.0.1:5054` in
  `conventions/urls.md` URL-14.
- **Seiten-Registry:** `views.json`-Manifest neben dem Code (BUD-3,
  SREG-4) mit Eintrag für die `frage`-View. Variant-Felder leer (V1 keine
  Stage-Varianten).

### KIBUDDY-26 — Greenfield-Schnitt, kein Code-Reuse von Pre-xbuddy, kein Pi-Sondercode
Die V1-Implementierung wird **frisch** geschrieben — keine Code-Übernahme
aus `/home/buddy/apps/kibuddy/`. Daten-Übernahme (Prompt-Text) erfolgt
**manuell** per Copy beim Setup (analog HSP-25a-V1). Der laufende Pre-
xbuddy-KIBuddy bleibt zunächst **parallel aktiv**; Abschalten passiert
nach erfolgreichem xbuddy-V1-Test in einem separaten Folge-Ticket
(out-of-scope dieser Spec).

**Kein Pi-Sondercode** (Disziplin zu KIBUDDY-5): der KIBuddy-Code kennt
keinen Pi-Pfad, keine Hardware-Erkennung, keine ALSA-Anbindung. Wenn der
Pi-Chromium-Kiosk Mikro-Zugang über `getUserMedia` nicht direkt liefert,
wird das durch einen **Pi-Display-Adapter** außerhalb des KIBuddy-Code
adressiert (eigenes Ticket im Pi-Display-Bereich, nicht hier).

### KIBUDDY-29 — Reset-Knopf für Konversation + Token-Kontext
Die View trägt einen **deutlich sichtbaren Reset-Knopf** im Header (oben
rechts). Visuelles Element: ein **Mülleimer-Piktogramm** aus der zentralen
Icon-Bibliothek (KIBUDDY-30) plus die Aufschrift „Neue Frage".

**Klick auf Reset:**
- löscht alle sichtbaren Chat-Turns im View-Container,
- löscht den Session-Memory-Konversations-Kontext am Service (KIBUDDY-16) —
  die nächste Kind-Frage geht **ohne Turn-Historie** an den LLM,
- löscht den TTS-Audio-Cache (alle Audio-Dateien aus bisherigen Turns werden
  gelöscht; die `tts_audio_url`-Links aus dem Browser-Cache werden damit
  invalidiert, KIBUDDY-31),
- fällt visuell in den Initial-Zustand zurück (KIBUDDY-4): leerer
  Chat-Container, neutraler Header.

Der Reset-Knopf ist **immer sichtbar**, auch im Initial-Zustand (für
Konsistenz; ist dort funktional ein No-Op).

### KIBUDDY-30 — UI-Icons aus zentraler Icon-Bibliothek (ICONS-5)
Alle in der View benutzten UI-Icons — **Mikrofon-Knopf**, **Stopp-Symbol-
Variante** (Mikro + Stopp-Quadrat), **Mülleimer** (im Reset-Knopf und im
Cancel-Hinweis KIBUDDY-11), **Vorlese-Symbol** (in jeder Bubble,
KIBUDDY-31) — laden ihre Grafik aus der **zentralen Icon-Bibliothek** über
`/display/_shared/icons/arasaac/<id>.png` (ICONS-5). Kein Inline-SVG, keine
Emoji, keine Icon-Webfont. Begründung: Konsistenz mit dem Antwort-Render
(KIBUDDY-17), eine einzige Asset-Quelle, austauschbar ohne Code-Änderung.

**Render-Disziplin:** Piktogramme werden in **voller ARASAAC-Farbe**
gerendert, nicht als monochromer Schatten (kein CSS-`filter:
brightness(0) invert(1)`). Knopf-Hintergründe sind entsprechend hell genug
gewählt (Default-PTT-Knopf: weiß, forest-grüner Rand), damit das farbige
Piktogramm vollständig sichtbar bleibt.

**V1-IDs (Default-Setup, Nic-Wahl an F3-Gate-B):**
| Funktion | ARASAAC-ID | Cache-Wort |
|---|---|---|
| Mikrofon (PTT-Knopf) | `37404` | mikrophon |
| Mülleimer (Reset-Knopf, Cancel-Hinweis) | `2498` | mülleimer/papierkorb |
| Vorlesen-Replay (Vorlese-Knopf je Bubble) | `38221` | play-taste |

**Pfeil + Schloss im Slide-Lock-Hinweis (KIBUDDY-10):**
- Der **Pfeil** ist ein Unicode-Pfeil-Glyph (`↑`), **kein** ARASAAC-
  Piktogramm — Richtungsanzeige, nicht Symbol-Inhalt. ARASAAC-Eintrag
  `5471` (Pfeil) ist **nicht** Teil des V1-UI-Icon-Sets.
- Das **Schloss-Piktogramm** (ARASAAC `3261`) war ursprünglich Teil des
  V1-Sets, ist seit 2026-06-15 **ausgeblendet** (Nic-Live-Befund: im Weg,
  Eltern erklären Slide-to-Lock verbal). Siehe KIBUDDY-10.

Die IDs sind als Per-Instanz-Config einstellbar (`ui-icons.json`); andere
Familien-Stile (z. B. Custom-Illustrationen einer Plattform-Asset-Erweiterung)
können einzelne IDs überschreiben, ohne Code-Änderung. V2-Pfad bleibt offen.

### KIBUDDY-31 — Vorlese-Knopf je Bubble (TTS-Replay)
**Jede Chat-Bubble** (Kind- wie Buddy-Bubble) trägt einen **Vorlese-Knopf**
mit dem Play-Taste-Piktogramm aus KIBUDDY-30 in voller ARASAAC-Farbe.

**Position:** **unten rechts neben der Bubble** — symmetrisch auf der
„Außenseite" jedes Turns: rechts neben der Buddy-Bubble (linksbündig), links
neben der Kind-Bubble (rechtsbündig). Der Knopf liegt baseline-bündig mit
der Unterkante der Bubble und ist Teil einer eigenen `bubble-row`-Flexbox
neben der `meta`-Zeile.

**Größe:** so groß wie die Wort-Render-Icons (Default 44px Icon-Bildhöhe,
60px runder Außenrahmen mit weißem Hintergrund und 2px Rand). Tippbar mit
dickem Kinderfinger; kein „Mini-Knopf".

**Klick auf Vorlese-Knopf:**
- **Buddy-Bubble:** spielt das TTS-Audio-Cache-Replay ab. Der Browser lädt
  die `tts_audio_url` (Endpoint `GET /api/v1/kibuddy/audio/<id>.mp3`,
  KIBUDDY-24) nach. Wenn das Audio nicht mehr auf dem Server liegt (z. B.
  nach Reset über KIBUDDY-29 oder bei Fehler), synthetisiert der Backend
  per Request `POST /api/v1/kibuddy/vorlesen` mit dem Bubble-Text neu
  (Stimme `onyx`, Speed `0.9` aus KIBUDDY-21). Fallback-Form ermöglicht
  Replay auch ohne Session-State-Speicher.
- **Kind-Bubble:** liest den **STT-Transkript-Text der Kind-Frage** mit
  derselben TTS-Pipeline vor (Stimme `onyx`, Speed `0.9`). Das gibt dem
  Kind eine Rückmeldung, was der Buddy verstanden hat — pädagogisch
  wertvoll bei undeutlicher Aussprache.

**Idempotent:** mehrfacher Klick spielt das Audio jeweils erneut ab; keine
parallelen Audio-Streams (laufendes Audio wird zuerst gestoppt).

### KIBUDDY-27 — PWA-Manifest für Tablet-Display (analog HSP)
Die Frage-View liefert ein **PWA-Manifest** mit `display: standalone`
(analog Hörspiel-Buddy HSP-Standalone-Pattern). Auf einem Tablet als
Display-Client ist die View damit als „zum Home-Bildschirm hinzufügen"-
PWA installierbar; Browser-Adressleiste und Tabs verschwinden, das
Geräte-Display geht später schlafen (Mikro-Erlaubnis bleibt im PWA-Scope).

## 11. Tests

### KIBUDDY-28 — Test-Anker
- **Mikro-Mock:** STT/LLM/TTS-Adapter haben Mock-Implementierungen für
  Tests ohne Netz (analog HSP-Mock-TTS-Adapter).
- **Render-Test:** gegen eine feste Antwort-Text + festen Icon-Cache wird
  die Wort-für-Wort-Tokenisierung + Icon-Lookup-Logik getestet. Treffer-
  und Miss-Wörter müssen identische Baseline-Alignments haben (KIBUDDY-17
  Punkt 5).
- **UX-Test:** Push-to-Talk-Knopf-Verhalten (Tap-Hold, Lock, Abbruch,
  Echo-Latenz <50 ms) wird über Playwright-/Cypress-Browser-Tests
  abgedeckt. Headless-Mikro-Permission via Browser-Flag (`--use-fake-ui-
  for-media-stream`).
- **Latenz-Determinismus:** die Inaktivitäts-Schwelle, Lock-Hinweis-Schwelle
  und Aufnahme-Maximum-Dauer kommen aus Config — kein hartcodiertes Wall-
  Clock im Code (Test-Determinismus-Lesson aus den Werft-Grenzen).

## 12. Offene Punkte (vorläufig — Werft-Gate-A-Klärung)

- **OPEN-KIBUDDY-A** — Panel-Mikro-Pfad (Audio-Brücke Panel → Display-Render).
  Eigenes Ticket nach V1-Stabilisierung.
- **OPEN-KIBUDDY-B** — Custom-Wake-Wort, teachbar.
- **OPEN-KIBUDDY-C** — Continuous-Wake-Word-Listening (Privacy-Berater-
  Runde fällig).
- **OPEN-KIBUDDY-D** — LLM-Provider-Wechsel im Eltern-Chat (analog HSP-N).
- **OPEN-KIBUDDY-E** — Frage-Historie für Eltern-Einsicht.
- **OPEN-KIBUDDY-F** — Azure-Key + LLM-Config in Plattform-Schicht
  zentralisieren (RAT-6-„LLM-Gateway"-Trigger). **Nic-Auftrag in dieser
  Werft (2026-06-15):** als Folge-Ticket zur Berater-Runde nach V1-Bau
  vorbereiten. KIBuddy V1 fährt mit per-App-ENV. *(geschlossen via
  [RAT-20](../../decisions/RAT-20-llm-gateway-ist-lib.md), 2026-06-21:
  LLM-Provider-Schicht als Lib `tools/llm/` ratifiziert mit Migrations-
  Reihenfolge **KIBuddy zuerst** → hoerspiel → eltern-chat; Verhalten in
  `specs/platform/llm-providers.md`, Bauregeln in
  `conventions/llm-providers.md` LLMP-1..LLMP-5. Migration ist eigene
  Werft, nicht Teil von RAT-20.)*
- **OPEN-KIBUDDY-G** — Antwort-Cache für idempotente Fragen.
- **OPEN-KIBUDDY-H** — Mehrturn-Konversations-Kontext (Sokratisch über
  mehrere Runden hinweg).
- **OPEN-KIBUDDY-I** — Lemmatisierung im Icon-Lookup.
- **OPEN-KIBUDDY-J** — Per-Familien-Profile (verschiedene Prompts/Voices
  je Kind).

---
