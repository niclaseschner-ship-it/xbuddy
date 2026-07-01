# Heim-Shell — Spec     (ID-Präfix: SHELL)

> Status: V1-Pilot · Refs #1182
> Architektur ratifiziert via /berater-runde 2026-06-30 (siehe RAT-25).
> Deliberation: `brainstorm/berater-runde/20260630-151000-RATIFIZIERT-pwa-shell-paula.md`
> Gate-B-Mockups: `specs/mockups/heim-shell/`

Die Heim-Shell ist ein **dünner Split-Layout-Container**, der auf **einem**
Familien-Gerät die heute getrennten Flächen co-loziert: **Panel-Kachel-Nav
links, geroutete Buddy-View rechts**. Sie ist **kein neuer Routing-Kern** —
sie bettet zwei bestehende, vom Router ausgelieferte Flächen als Iframes ein
und überlässt ihnen ihre eigene Mechanik. Tile-Tap läuft unverändert
`tile_selected` (PANEL-6) → Router → SSE (ROU-22) → Render im Display-Client.

**V1-Pilot-Scope:** EIN Testgerät (Paula-Tablet `tablet-tablet-paula-01`,
1920×1200), **LAN-only** (kein Funnel). Einstieg über `panel_id`; `display_id`
per Router-Lookup (ROU-32). Reversibel: Rückbau = Shell-Route weg, Tablet zeigt
wieder auf den klassischen Display-Client.

**Out-of-Scope V1** (jeweils eigenes Ticket, sobald gebraucht): produktiver
RAT-19-Phase-4-Rollout (Auth scharf, siehe SHELL-6) · zweites Shell-Gerät
(GER-`beides`-Co-Location-Modell, `geraete.md:60` / `seiten-registry.md:39` —
explizit als Schuld notiert) · RAT-24-Teil-Pane-Render-Vertrag · jede
antizipative Shell-Konvention (n=1).

---

## 1. Einstieg & Auflösung

### SHELL-1 — Einstieg über `panel_id`
Das System liefert die Shell unter `GET /shell/<panel_id>` als HTML-Antwort
aus. `panel_id` ist das load-bearing Segment (analog PANEL-2 / PREG-2). Eine
unbekannte `panel_id` führt zu einem sichtbaren Fehler (kein Raten, kein
stiller Fallback). Verortung: `seiten/`-Service (`seiten/static/` +
`platform.js`); nginx routet `/shell/` zum seiten-Service.
Test-Anker: seiten/tests/test_heim_shell.py::test_shell1_route_html

### SHELL-2 — `display_id` per Router-Lookup, keine Reverse-Inferenz
Die Shell ermittelt das Ziel-Display **ausschließlich** über den
Panel→Display-Lookup `GET /api/v1/router/panels/app-panel:<panel_id>` (ROU-32,
`router/main.py:671`) und nimmt `display_id` aus dessen Antwort. Es gibt
**keine** Reverse-Inferenz „ein Display → genau ein Panel" (mehrere Panels
dürfen ein Display steuern, `panel-registry.md` PREG-2 / `:55`). Liefert der
Lookup kein `display_id` (unbekanntes Panel / kein gebundenes Display), zeigt
die Shell einen sichtbaren Fehler und bettet **kein** rechtes Pane ein.
Test-Anker: seiten/tests/test_heim_shell.py::test_shell2_lookup_display_id

### SHELL-9 — IDs aus Daten, kein Hardcode (n=1)
Weder `panel_id` noch `display_id` noch Geräte-IDs stehen im Shell-Code. Die
`panel_id` kommt aus der URL, das `display_id` aus ROU-32; die konkreten
Pilot-IDs (`paulas-panel-01`, `tablet-tablet-paula-01`) leben in den
Registry-Daten (xbuddy-data, GER-4 / PREG). Was je Familie variiert, ist
Config/Daten, nicht Code (Familie-3-Probe).
Test-Anker: seiten/tests/test_heim_shell.py::test_shell9_keine_hardcode_ids

## 2. Layout & Einbettung

### SHELL-3 — Split-Layout mit zwei Iframes, Rail 280px
Die Shell rendert ein zweispaltiges Layout: links eine **Nav-Rail** mit einem
Iframe auf `/controller/app-panel/<panel_id>` (`router/main.py:1368`), rechts
ein **Buddy-Pane** mit einem Iframe auf `/display/<display_id>`
(`router/main.py:880`). Beide Iframes füllen ihre Spalte (`width:100%;
height:100%`). Die linke Rail hat eine **feste Breite von 280px** (Gate B
2026-06-30); das Buddy-Pane füllt den Rest (auf 1920×1200 → 1637px).
Bei dieser Rail-Breite legt das Panel seine Kacheln **selbst einspaltig**
aus — das Panel berechnet die Grid-Geometrie adaptiv aus seiner eigenen
Iframe-Breite (PANEL-12 / `app.js::computeGridGeometry`, 1 Spalte ab ≤ ~360px).
Die Shell setzt nur die Rail-Breite; das Panel bleibt **unverändert** (kein
1-Spalten-Modus nachzurüsten, Leitplanke „Panel unangetastet" gewahrt).
Test-Anker: seiten/tests/test_heim_shell.py::test_shell3_zwei_iframes_src

### SHELL-4 — Keine Stream-Fusion, kein Shell-Zustand
Die Shell hält **keine** eigene `EventSource` und **keinen** Display-Zustand.
Die beiden eingebetteten Views behalten je ihre **unabhängige** EventSource
(Panel `app.js:757`, Display-Client `displib.js:62`); der zustandslose
Router-Stream (ROU-22) bleibt gewahrt. Es gibt **keine** Cross-Iframe-Nachricht
und keine Stream-Fusion: ein Tile-Tap läuft unverändert über den Router, der
neue Display-Zustand erreicht das rechte Pane allein über dessen eigene
EventSource.
nicht_automatisiert: Live-SSE-Verhalten zweier Browser-EventSources hinter
nginx-Proxy · manuelle_probe: Shell öffnen, 50 Tile-Taps + Display-iframe-Reload
+ Netz-Cut/-Wiederkehr; Active-Tile bleibt konsistent, keine Doppel-Reloads,
EventSource-Zahl wächst nach Reconnects nicht (Kill-Kriterium).

### SHELL-5 — Rechtes Pane ist reiner Iframe, keine Codekopie
Das Buddy-Pane bettet den bestehenden Display-Client per Iframe ein. Es wird
**keine** Display-Client-Logik (displib.js, DC-Render, DC-7-Reconnect) in die
Shell kopiert oder nachgebaut.
Test-Anker: seiten/tests/test_heim_shell.py::test_shell5_kein_displib_import

### SHELL-8 — Render auf 1920×1200
Bei Rail 280px rendert die Shell auf 1920×1200 ohne Overflow, ohne
Text-Clipping und mit bedienbaren primären Touch-Zielen in beiden Panes
(Panel-Tiles 280×115px, einspaltig).
nicht_automatisiert: physische Render-/Touch-Wirkung auf dem Tablet ·
manuelle_probe: Render-Gate-Screenshot 1920×1200 mit Rail 280px gegen
Live-Daten (Kill bei Overflow/Clipping/unbedienbar). Gate-B-Beleg:
`specs/mockups/heim-shell/`.

### SHELL-12 — Resume-Reload nach Device-Sleep (Clock-Drift + Connectivity-Gate, Refs #1239, #1245)
Im installierten PWA-Standalone-Kontext lädt die Shell nach einem Tablet-Sleep
(Bildschirm aus/an ohne Passwort-Unlock) die Seite **nicht** automatisch neu —
die eingebetteten Iframes verlieren dadurch ihre SSE-/Event-Verbindungen still
(Panel-Routing dead, Display-State eingefroren). Die Shell erkennt Device-Sleep
und lädt sich **vollständig** via `window.location.reload()` neu (exakt der
manuelle Reload, der bei Nic funktioniert).

**Wake gegen WLAN-Reconnect gehärtet (#1245):** Android friert/killt den
PWA-Prozess im Sleep **inklusive WLAN**. Ein direkter Reload beim Wake rennt
gegen den WLAN-Reconnect: die netz-abhängigen Iframes (`/controller`,
`/display`) und das network-first Shell-HTML laufen ins Leere/hängen → mal lädt
es, mal nicht, und **nicht alle Kacheln**. Deshalb wird beim Wake **nicht direkt
reloadet**, sondern erst auf echtes Netz gewartet.

**Mechanik (Inline-Script in `seiten/templates/heim-shell.html`):**
1. **Clock-Drift-Detektor (primär, event-unabhängig):** `setInterval(fn, 2000ms)`
   merkt `_lastTick = Date.now()`. Bei jedem Tick: wenn
   `(Date.now() - _lastTick) > CLOCK_DRIFT_THRESHOLD_MS` (10 000 ms) → Prozess
   war eingefroren / Device schlief → Wake erkannt →
   `waitForConnectivityThenReload()`. Der Interval-Callback läuft nach dem Wake
   garantiert wieder, deshalb feuert das unabhängig von Browser-Events.
2. `visibilitychange → hidden`: Zeitstempel merken (`_hiddenAt = Date.now()`).
   `visibilitychange → visible`: Wenn Verdeckungsdauer > `RESUME_RELOAD_THRESHOLD_MS`
   (3 000 ms) → `waitForConnectivityThenReload()`. Bei kurzer Verdeckung
   (< Schwelle) **kein** Reload (kein visueller Flash).
3. `pageshow` mit `event.persisted = true` (bfcache-Restore) →
   `waitForConnectivityThenReload()`.
4. **`online`-Event + Flap-Guard:** `offline`-Listener setzt
   `_offlineSince = Date.now()`; `online`-Handler ruft
   `waitForConnectivityThenReload()` **nur**, wenn
   `_offlineSince !== null && (Date.now() - _offlineSince) > RESUME_RELOAD_THRESHOLD_MS`
   (3 000 ms, dieselbe Konstante wie Trigger 2). Danach `_offlineSince = null`.
   Kurze WLAN-Aussetzer auf Heim-WLAN (< 3 s) lösen **keinen** sichtbaren Flash
   am Dauer-Display aus. Echter Sleep-Disconnect (Gerät + WLAN weg) läuft lang
   genug → Reload. Der `online`-Trigger bildet die **primäre** Fresh-Process-Naht
   (Gerät schläft, WLAN weg, Prozess-Neustart → `online` feuert zuverlässig).
5. **Iframe-onerror (OS-Kill-dann-Relaunch, best-effort):** Die same-origin
   Iframes (`.rail iframe`, `.buddy iframe`) werden beim initialen Load mit einem
   `error`-Listener beobachtet. Lädt eine ins Leere (frischer Prozess-Neustart,
   Netz noch weg, **kein** Clock-Drift aktiv) → `waitForConnectivityThenReload()`.
   **Hinweis:** Browser feuern `error` auf Iframes bei Netz-/HTTP-Fehlern
   **unzuverlässig** — dieser Trigger ist **best-effort**. Der `online`-Trigger (4)
   ist die primäre Naht für den Fresh-Process-Wake-Pfad.

**`waitForConnectivityThenReload()`:** probt eine leichtgewichtige, sicher
vorhandene same-origin URL (`/api/v1/seiten/static/heim-shell.css`) via
`fetch(url + '?ping=' + Date.now(), {method:'HEAD', cache:'no-store'})`.
- `res.ok` → `_reloading`-Guard setzen + `window.location.reload()`.
- Fehler / `!ok` → `setTimeout(…, 2000ms)`-Retry bis Netz da, mit
  Versuchs-Cap (`PROBE_MAX_ATTEMPTS`, danach aufgeben — kein Endlos-Loop).
Nach erfolgreichem Reload startet der Kontext frisch (`_lastTick`/`_reloading`
neu). Gemeinsamer `_reloading`-Guard **und** `_probing`-Guard verhindern
Mehrfach-Reload bzw. Parallel-Probe-Schleifen bei gleichzeitigem Feuern
mehrerer Trigger.

**Reload = `window.location.reload()`** (ganze Shell, kein iframe.src-Trick —
gleiche URL wäre No-Op im Browser-Cache).

**Diagnose:** knappe `console.log('[shell-wake] …')` an den Kernpunkten (drift
erkannt, probe ok/fehler, reload) für späteres `chrome://inspect`-Remote-Debug.
**Kein** sichtbares UI-Overlay (Familien-Display).

**Panel/Display-Code unangetastet** (SHELL-4-Leitplanke): Der Fix ist
ausschließlich shell-seitig; `controller/app-panel/**` und `display-client/**`
bleiben unverändert.

Test-Anker: seiten/tests/test_heim_shell.py::test_shell12_resume_reload_script
            seiten/tests/test_heim_shell.py::test_shell12_clock_drift_und_guard
            seiten/tests/test_heim_shell.py::test_shell12_connectivity_gated_reload
            seiten/tests/test_heim_shell.py::test_shell12_online_und_iframe_error_trigger

### SHELL-11 — Shell besitzt den Vollbild; eingebettete Iframes unterdrücken Eigen-Vollbild
Die Shell ist der Vollbild-Besitzer: beim ersten Nutzer-Gesture (touchend/click)
fordert die Shell `requestFullscreen` auf `document.documentElement` der **Shell**
an (analog FIG-26, DC-11). Self-healing-Guard: tritt der Nutzer aus dem Vollbild,
holt ihn der nächste Tap zurück. **Beide** eingebetteten Iframes unterdrücken bei
`window.self !== window.top` ihren Eigen-Vollbild-Listener:

- **Panel-Iframe (PANEL-10):** Guard in
  `controller/app-panel/app.js::attachFullscreenOnGesture`.
  Standalone Panel-Geräte (self === top) behalten PANEL-10 unverändert.
- **Display-Client-Iframe (DC-11 embedded-Ausnahme):** Guard an der
  Konsument-Aufrufstelle in `display-client/index.html` vor
  `dispLib.attachFullscreenOnGesture`. `displib.js`-Lib unangetastet.
  Standalone Display-Geräte (self === top) behalten DC-11 unverändert.

Umsetzung: Inline-Script in `seiten/templates/heim-shell.html` (SHELL-11-Block)
+ Guards an beiden Konsument-Aufrufstellen.
Test-Anker: seiten/tests/test_heim_shell.py::test_shell11_panel_embedded_guard,
             seiten/tests/test_heim_shell.py::test_shell11_display_client_embedded_guard,
             seiten/tests/test_heim_shell.py::test_shell11_shell_fullscreen_script

## 3. Audio-Seiteneffekt

### SHELL-7 — Panel-Audio-Prime überlebt die Einbettung
Der Silent-Audio-Prime des Panels (PANEL-13, `app-panel.md:230`, `app.js:913`)
ist ein Seiteneffekt des Tile-Tap und etabliert die Sticky-Activation für
spätere HSP-Audio-Wiedergabe. Die Einbettung als Iframe darf diese
User-Gesten-getragene Activation **nicht** brechen: der Tap im linken Iframe
trägt weiterhin die Browser-Geste.
nicht_automatisiert: Browser-Autoplay-Policy in eingebettetem Iframe ·
manuelle_probe: Shell öffnen, HSP-Kachel tippen, prüfen dass Audio später ohne
zusätzliche Geste startet (Autoplay-Test, Kill-Kriterium).

## 4. Auth — Ein-Wege-Kante (LAN-only-Riegel)

### SHELL-6 — LAN-only, AUTH-7 nicht ausgelöst
Die Shell ist ein bewusst eingehegter **LAN-only-Pilot**, **kein**
RAT-19-Phase-4-Rollout. `auth.md` bindet die Panel-/Display-Routen
(`/api/v1/displays/<id>/events`, `/controller/app-panel/*`) an Phase 4 → AUTH-7
(`auth.md:245`, `:338`). Solange der Pilot **LAN-only** bleibt (kein Funnel),
wird der Phase-4-Trigger **nicht** ausgelöst. Shell-URL **und**
Display-Event-Stream dürfen **nicht** über den Funnel erreichbar sein (nur
Heim-LAN/Tailnet). Sobald ein zweites Gerät oder produktive Nutzung geplant
ist: **erst AUTH-7 scharfziehen** (#948 bleibt Plan B / Auth-Schmerz-Trigger).
nicht_automatisiert: Funnel-Erreichbarkeit (externe Realwelt, Hairpin-Falle —
NIE vom Pi testen) · manuelle_probe (Pre-Merge-Experiment): von einem
**externen** Client (nicht Pi, Hairpin täuscht) `curl https://<funnel-fqdn>/shell/<panel_id>`
und `.../api/v1/displays/<id>/events` → muss scheitern/4xx; von Heim-LAN/Tailnet → 200.

## 5. Registrierung & Schnittstelle

### SHELL-10 — Shell-URL in der Eltern-Seiten-Übersicht
Die Shell-URL ist in der Eltern-Seiten-Übersicht auffindbar — primär in der
**MAU-Mini-App** (`/api/v1/seiten/mini-app-uebersicht`, Eltern öffnen sie als
Telegram-Mini-App), zusätzlich in der HTML-Seite (`/api/v1/seiten/uebersicht`,
Hero-Sektion SREG-12, `seiten-registry.md:30`). Konkret: je Panel des
Geräte-Paars zeigen beide Übersichten **zusätzlich** eine Shell-URL
`/shell/<panel_id>` in der SREG-12-Form **zwei kopierbare URLs** (Heimnetz +
Tailscale). Die URL wird aus `panel_id` abgeleitet — **kein** GER-`beides`-
Co-Location-Modell nötig (das bleibt Folge-Aufgabe, `seiten-registry.md:39`).

**Datenpfad MAU:** `GET /api/v1/seiten` reichert Panel-Einträge server-seitig
mit `shell_urls: {heim, tailscale}` an (aus `panel_id` + konfigurierten Origins,
`seiten/main.py::get_seiten`); `mini-app-uebersicht.js` rendert sie als
URL-Karten je Geräte-Paar. Kein JS-Hardcode der panel_id — abgeleitet aus dem
`instanz`-Feld (SREG-4), Origins aus dem Runtime-Dict (SREG-7).

Installierbarkeit als PWA (WebAPK) erfolgt über ein Shell-Manifest je
`panel_id` (analog PWA-1); für den Pilot ist `start_url = /shell/paulas-panel-01`.
Test-Anker (MAU): seiten/tests/test_mini_app_uebersicht.py::test_shell10_mau_panel_eintrag_hat_shell_urls
Test-Anker (HTML): seiten/tests/test_heim_shell.py::test_shell10_url_in_uebersicht

---

## 6. PWA-Mantel (SHELL-PWA, #1212)

### SHELL-PWA — Installierbare PWA analog essen-einkauf (ESSEN-33..35)

Die Heim-Shell ist eine vollwertig installierbare PWA (WebAPK-Kandidat auf
Android). Der Mantel spiegelt das essen-einkauf-Muster 1:1 (ESSEN-33..35).

**Manifest** (`GET /shell/<panel_id>/manifest.json`, dynamisch je `panel_id`):
- `display: "fullscreen"` — Vollbild ohne Browser-Chrome (WebAPK-Standard).
- `scope: "/shell/"` — deckt alle Shell-Instanzen; SW-Scope passt.
- `icons`: 192×192 any, 512×512 any, 512×512 maskable — je unter
  `/shell/<panel_id>/icon-*.png` (aus `seiten/static/shell/`, Assets von
  essen-einkauf wiederverwendet für den Pilot).
- `start_url: "/shell/<panel_id>"` — PWA-Open nach Install öffnet genau
  dieses Panel.

**Service-Worker** (`seiten/static/shell/sw.js`, Scope `/shell/`, SHELL-PWA-SW):

| Anfrage-Typ | Erkennungs-Signal | Strategie |
|---|---|---|
| Shell-HTML-Seite `/shell/<panel_id>` | `request.mode === 'navigate'` ODER kein zweites Pfad-Segment | **network-first mit Timeout** (`Promise.race([fetch, ~2000ms]`) → cache-put; Timeout/Offline: `caches.match`) |
| Static-Assets: manifest.json, sw.js, icon-*.png (`/shell/<panel_id>/<asset>`), heim-shell.css, platform.js | zweites Segment vorhanden / `heim-shell`·`platform.js` unter `/api/v1/seiten/static/` | **cache-first** |
| Panel-/Display-Iframes (`/controller/`, `/display/`) | Präfix-Match | **pass-through** (kein `respondWith`) |

**Rationale network-first für HTML** (#1241): Shell-HTML enthält den Seiten-Code
selbst (Inline-Scripts, Template). Bei cache-first erscheinen Änderungen am
Tablet erst nach manuellem Site-Data-Löschen (stale HTML im Cache). Network-first
lädt online immer den neuesten Code; der Cache-Put stellt offline Fallback
sicher — Installierbarkeit (keep_installable, WebAPK) bleibt gewahrt.
**Übergang:** einmaliges Site-Data-Löschen zum Aktivieren des neuen SW;
danach greifen alle Updates sofort.

**Timeout-Härtung (#1245):** Beim Tablet-Wake ist das WLAN oft noch nicht
zurück. Ein reines network-first fetch würde dann am lahmen Netz hängen und die
Shell weiß lassen. Deshalb rennt die HTML-Navigation gegen ein
`~2000ms`-Timeout (`Promise.race([fetch, timeout])`); antwortet das Netz nicht
rechtzeitig → `caches.match(req)` (Cache zeigt sofort, der SHELL-12-Connectivity-
Probe holt danach frisch nach). Der bestehende Cache-Fallback bei echtem
Netzfehler bleibt; Static-Assets/`cacheFirst` sind unverändert. Der Offline-
Fallback (keep_installable) bleibt gewahrt.

- BUILD_ID-Platzhalter wird beim Ausliefern durch `shell_asset_view` ersetzt
  (Cache-Versionierung analog ESSEN-35).
- Auslieferung: `/shell/<panel_id>/sw.js` mit `Service-Worker-Allowed: /shell/`
  Header (Scope-Erweiterung über SW-Datei-Pfad hinaus).

Test-Anker: seiten/tests/test_heim_shell.py::test_shell_pwa_sw_html_network_first,
            seiten/tests/test_heim_shell.py::test_shell_pwa_sw_assets_cache_first,
            seiten/tests/test_heim_shell.py::test_shell_pwa_sw_html_timeout

**Asset-Route** (`shell_asset_view`, `seiten/main.py`):
- `GET /shell/<panel_id>/<asset>` liefert sw.js + icon-*.png aus
  `seiten/static/shell/` mit Path-Traversal-Schutz (analog ESSEN-34).
- `manifest.json` wird von `heim_shell_manifest` bedient (spezifischere
  Flask-Route), nicht von dieser Asset-Route.
- Test-Naht: `runtime["shell_asset_dir"]` überschreibbar (analog einkauf).

**Kachel-Scaling** (`seiten/static/heim-shell.css` + `controller/app-panel/style.css`, SHELL-PWA AC3):
- `.rail iframe` rendert **nativ** (`width:100%; height:100%`) — der alte
  `scale(0.5)/200%`-Hack ist entfernt (Nic 2026-06-30, T1224).
- Kachel-Inhalt (Icon + Label) skaliert **kachel-relativ** via Container-Query:
  `.tile { container-type: size }` in `controller/app-panel/style.css`; Icon-/
  Label-Größe in `cqmin`-Einheiten — robust skalierend je verfügbarem Platz,
  unabhängig vom Viewport.
- `controller/app-panel/app.js` (PANEL-12-Grid-Geometrie/JS) bleibt **unverändert**
  (stop_rule gilt weiter für app.js). Panel-CSS (`style.css`) darf für die
  kachel-relative Inhalts-Skalierung angefasst werden — die frühere Schranke
  „`controller/app-panel/**` unberührt" gilt nur noch für app.js, nicht style.css
  (Nic-angewiesen T1224).

Test-Anker:
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac1_icons_nicht_leer
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac1_display_fullscreen
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac1_scope
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac2_sw_route
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac2_sw_build_id_ersetzt
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac2_icon_routes
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac2_html_registriert_sw
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac3_rail_iframe_nativ
  seiten/tests/test_heim_shell.py::test_shell_pwa_ac3_panel_unangetastet

---

## Offene Schuld (sichtbar, nicht jetzt)
- **GER-`beides`-Co-Location:** ein Gerät, das dauerhaft Panel UND Display
  trägt, „riecht nach `beides`" im GER-Modell (`geraete.md:60`); SREG nennt
  physische Co-Location als Folge-Aufgabe (`seiten-registry.md:39`).
  **Trigger: 2. Shell-Gerät.**
- **RAT-24-Teil-Pane-Vertrag:** Render-Gate deckt heute nur Voll-Viewport-
  Display-Views; Shell-Teil-Pane-Vertrag offen (Folge-Frage).

## Familie-3-Probe
Was variiert je Familie → **Daten/Config** (panel_id, display_id, Geräte-
Registry in xbuddy-data), nicht Code (SHELL-9). ✔

## Konventions-Aktivierung
Keine. n=1, LAN-only — **keine** antizipative Shell-Konvention (Leitplanke
#1182, RAT-25). `conventions/` entsteht erst beim 2. Vorkommen mit konkretem
Schmerz.
