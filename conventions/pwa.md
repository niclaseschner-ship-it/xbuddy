# PWA — Konvention     (ID-Präfix: PWA)

XBuddy hat zwei Geräte-Klassen, die als **installierbare Web-Apps** auf
Familien-Geräten landen sollen — damit sie wie Familien-Apps wirken und
nicht wie Browser-Tabs:

- **Controller-PWAs** unter `controller/<app>/` — Figuren-Erkennung auf
  dem Phone (`figuren-erkennung.md` FIG-24/FIG-26), App-Panel auf dem
  Tablet (`app-panel.md` PANEL-10).
- **Display-Client** unter `display/<id>/` — der Renderer auf
  BuddyBoards/Tablets/Monitoren (`display-client.md` DC-11/DC-16).

Diese Konvention legt die **Mindest-Naht** fest, die beide Konsumenten
erfüllen, damit der Browser einen echten WebAPK-Install-Pfad anbietet
(Manifest gültig, Service-Worker registriert, `start_url` getroffen) und
das Gerät im laufenden Betrieb wie ein Display/eine App auftritt
(Vollbild, Bildschirm wach). Klauseln mit Konsumenten-spezifischem
Inhalt (z. B. `config.json`-Lade-Pfad) sind unten ausdrücklich
zugeordnet — nicht jede Klausel gilt für jeden Konsumenten gleich.

### PWA-1 — Pflicht-Dateien neben dem Seiten-Code
Eine PWA liefert im selben Verzeichnis wie `index.html` mindestens:

- `index.html` — Einstiegspunkt; bindet `manifest.json` per
  `<link rel="manifest" href="./manifest.json">` ein und registriert
  `sw.js` als Service-Worker.
- `manifest.json` — Web App Manifest (PWA-2).
- `sw.js` — Service-Worker, beim Laden im Document registriert. Cache-
  Strategie ist Konsumenten-Sache (s. u.); Pflicht ist nur, dass der
  Worker existiert und einen `fetch`-Handler trägt — sonst verweigert
  Chrome den WebAPK-Install-Trigger.
- Mindestens zwei Icons (Form: PWA-2).

**Cache-Strategie je Konsument:**

- **Controller-PWAs:** der Service-Worker cached die Asset-Liste beim
  Install-Event, damit die Seite nach dem ersten Laden offline
  funktioniert. Komponenten-spezifische Strategien (z. B.
  netzwerk-bevorzugt mit Cache-Fallback bei der Figuren-Erkennung,
  FIG-24) ergänzen die Mindest-Naht in der jeweiligen Spec.
- **Display-Client:** **cache-first** für Manifest und Icons (damit
  Install-Trigger und kurzer Netz-Aussetzer keinen White-Screen
  erzeugen), **pass-through** (network only) für alles andere. **Kein**
  Pre-Caching der Display-Inhalte — die kommen aus dem iframe-Routing
  (DC-3) und gehören nicht in den SW-Cache. Form siehe
  `display-client.md` DC-16.

Selbsttragend: keine externen Asset-Quellen (kein CDN, keine
Drittpartei-Domain). Alles, was die Seite zum Starten und Installieren
braucht, liegt im Verzeichnis und wird mit ausgeliefert. (Verfeinerung
zur Selbstgenügsamkeit: PWA-4.)

### PWA-2 — Pflicht-Felder im Manifest
Das `manifest.json` deklariert mindestens:

- `name`, `short_name`, `start_url: "./"` — relativ zur Einstiegs-URL,
  damit der installierte WebAPK vom Vollbild-Einstieg startet und nicht
  aus einem verkürzten Pfad.
- `display: "fullscreen"` (nicht `"standalone"`) — die installierte
  PWA startet randlos ohne System-Statusleiste, **bevor** eine erste
  Nutzer-Geste erfolgt. Browser ohne `fullscreen`-Unterstützung
  fallen über die Manifest-Fallback-Kette automatisch auf
  `standalone` zurück.
- `orientation`, `background_color`, `theme_color` passend zum
  UI-Stil der Seite.
- Mindestens **zwei Icons**: `192 × 192` und `512 × 512` PNG, im
  selben Verzeichnis. Mindestens ein Icon trägt `purpose: "maskable"`,
  damit Android-Launcher die Form korrekt zuschneiden.

### PWA-3 — Wake-Lock + Fullscreen-API beim ersten User-Gesture
Der Seiten-Code übernimmt selbst zwei Geräte-Aufgaben, unabhängig von
der Auslieferungsform (normale URL, Home-Screen-Verknüpfung,
PWA-Install):

- **Wake-Lock:** Die Seite fordert beim Laden
  `navigator.wakeLock.request('screen')` an und fordert ihn bei jedem
  `visibilitychange` zurück auf `visible` erneut an — das System gibt
  den Lock beim Verdecken der Seite frei.
- **Fullscreen:** Aus einem **abgeschlossenen** Nutzer-Gesture
  (`touchend` oder `click` — Chromium gewährt die für
  `requestFullscreen` nötige „transient activation" nicht bei
  `touchstart`) fordert die Seite per Fullscreen-API
  (`requestFullscreen`) den Vollbild-Modus an. Solange die Seite
  nicht im Vollbild ist, löst jeder Tap einen neuen Versuch aus;
  verlässt der Nutzer den Vollbild, holt ihn der nächste Tap zurück
  (self-healing).
- **Best-effort:** Fehlt eine der APIs oder schlägt sie fehl, läuft
  die Seite weiter und protokolliert `console.warn` — keine
  Fehlermeldung an den Nutzer, kein Blockieren der eigentlichen
  Funktion.

Begründung: Tablet- und Phone-Browser zeigen sonst die URL-Leiste,
und der Bildschirm geht nach ~30 s aus — das Gerät wirkt nicht wie
eine Familien-App / kein Display.

### PWA-4 — Selbstgenügsamkeit & Config-Lade-Konvention
**Selbstgenügsamkeit (gilt für beide Konsumenten):** Eine PWA bringt
alle Assets, die sie zum Starten und Installieren braucht, im eigenen
Verzeichnis mit. **Keine externe `config.json`-Quelle, kein externer
Konfig-Dienst, kein CDN-Asset, das den Start blockiert.** Was die
Konvention nicht selbst trägt, gehört in den Code als Default.

**Config-Lade-Konvention (Controller-PWAs):** Beim Laden der Seite
wird `./config.json` per `fetch` geholt und auf die Code-Defaults
angewendet (Defaults-Merge). URL-Parameter überschreiben standardmäßig
`config.json`. Standard-Reihenfolge: **Defaults → config.json →
URL-Parameter**.

**Ausnahme App-Panel:** Das App-Panel (`app-panel.md`, PANEL-8)
verwendet bewusst **kein URL-Parameter-Overlay** — Konfiguration
ausschließlich über `config.json`. Begründung: V1, feste Tablets,
kein wechselnder Kontext pro Seitenaufruf. Ein URL-Overlay ist
nachrüstbar, sobald der Onboarding-Skill es braucht. Die
Figuren-Erkennung und andere Controller-Typen behalten das
URL-Overlay unverändert. *(#251)*

Existiert die Datei nicht oder ist sie nicht parsebar, fällt die
Seite **stumm** auf die Defaults zurück und protokolliert den Fehler
in `console.warn`. Die Seite bleibt funktionsfähig — wichtig für
das Repo-Default-Setup ohne Live-Werte (vgl. CONFIG-4).

Pro Controller-Instanz wird `config.json` separat verwaltet (nicht
alle Instanzen im Repo, sondern beim Deployment der jeweiligen URL
erzeugt); ein `config.example.json` dokumentiert das Format.

Implementierungs-Naht (Controller-PWAs): `controller/_shared/config.js`
(`pwaShared.loadPwaConfig`). Der Helper-Pfad `/controller/_shared/` ist
PWA-übergreifend für Controller-PWAs (siehe `router.md` ROU-23-Tabelle).

**Display-Client trägt keine `config.json`:** Der Display-Client zieht
seinen Inhalt über den Router-Stream (DC-3/DC-4) und braucht keine
per-Instanz-Datei neben dem Code — er bleibt damit strikt
selbstgenügsam im Verzeichnis und nutzt die Code-Defaults direkt.

---

**Erweiterungs-Anker — nicht auf Vorrat prägen.** Wenn ein konkretes
Buddy-Feature **Mikro- oder Kamera-Zugriff** auf einem PWA-Konsumenten
fordert (z. B. TAB-Voice, Foto-direkt-vom-Tablet, Live-Kamera-Erkennung),
wird die PWA-Konvention um Klauseln zu `getUserMedia()`, Berechtigungs-
Prompt-Verhalten und Fehler-Pfad erweitert. Das ist als Folge-Ticket
#552 (PWA-Konventions-Erweiterung für Medien — Mikro/Kamera/getUserMedia)
gerahmt — die Klauseln werden **erst** beim ersten konsumierenden
Feature scharfgeschaltet und hier eingefügt. Bis dahin: keine
PWA-N-Reservierung auf Vorrat (CLAUDE.md §6, `conventions/README.md`
„Nichts auf Vorrat").
