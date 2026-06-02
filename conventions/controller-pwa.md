# Controller-PWA — Konvention     (ID-Präfix: PWA)

Controller-Seiten (Figuren-Erkennung auf dem Phone, App-Panel auf dem
Tablet) werden als **installierbare Web-Apps** unter `controller/` auf
Familien-Geräten ausgeliefert. Diese Konvention legt fest, welche
Dateien und welches Verhalten jede solche Seite mitbringen muss — damit
ein installierter Controller wie eine Familien-App wirkt und nicht wie
ein Browser-Tab.

Heimat in den Komponenten: `figuren-erkennung.md` FIG-24/FIG-26,
`app-panel.md` PANEL-10.

Der Display-Client (`specs/platform/display-client.md` DC-11) ist eine
eigene PWA-Anwendung mit reduziertem Pflichten-Set — er teilt das
Manifest-`display: fullscreen` und das Wake-Lock+Fullscreen-Gesture-
Muster aus PWA-2/PWA-3, kennt aber kein `sw.js` und keine
`config.json`. Er ist daher **nicht** durch diese Konvention gedeckt.

### PWA-1 — Pflicht-Dateien neben dem Seiten-Code
Eine Controller-PWA liefert im selben Verzeichnis wie `index.html`
folgende Dateien aus:

- `index.html` — Einstiegspunkt; bindet `manifest.json` per
  `<link rel="manifest" href="./manifest.json">` ein.
- `manifest.json` — Web App Manifest (PWA-2).
- `sw.js` — minimaler Service Worker, beim Laden registriert; cached
  die Asset-Liste beim Install-Event, damit die Seite nach dem ersten
  Laden offline funktioniert.
- `config.json` — Per-Instanz-Konfiguration (PWA-4), gitignored.

Selbsttragend: keine externen Asset-Quellen (kein CDN, keine
Drittpartei-Domain). Alles, was die Seite braucht, liegt im
Verzeichnis und wird mit ausgeliefert.

### PWA-2 — Pflicht-Felder im Manifest
Das `manifest.json` deklariert mindestens:

- `name`, `short_name`, `start_url: "./"`
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
eine Familien-App.

### PWA-4 — Config-Lade-Konvention
Beim Laden der Seite wird `./config.json` per `fetch` geholt und auf
die Code-Defaults angewendet (Defaults-Merge). URL-Parameter
überschreiben standardmäßig `config.json`. Standard-Reihenfolge:
**Defaults → config.json → URL-Parameter**.

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

Implementierungs-Naht: `controller/_shared/config.js` (`pwaShared.loadPwaConfig`).
