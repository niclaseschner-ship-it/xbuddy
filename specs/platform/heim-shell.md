# Heim-Shell — Spec     (ID-Präfix: SHELL)

> ⚠️ **ZIEL-ZUSTAND geändert durch RAT-31 (2026-07-27) — Wirbelsäule-Abriss.**
> Nic-Setzung „ein Gerät für immer, Boote verbrennen": Die Heim-Shell wird
> **self-contained** — linke Panel-Nav + rechtes Buddy-Pane + Tile-Tap + Live-
> Refresh laufen alle **same-origin über `seiten/`**. Der Router-Fanout stirbt.
> Damit sind **überholt** und werden in den RAT-31-Etappen (Epic #1339) umgebaut:
> SHELL-1 „vom Router ausgelieferte Iframes", SHELL-2 „`display_id` per ROU-32-
> Router-Lookup", die Mechanik „`tile_selected` → Router → SSE → Display-Client"
> (wird same-device SSE über `seiten/`), sowie jeder `router/`-/`display-client/`-
> Verweis. Panel `tiles`+Editor bleiben (re-home same-origin); Kind/Eltern-Redirect
> aus dem Pairing-Token statt `geraete.json`. Die Per-Requirement-Umschreibung
> erfolgt in den Etappen #1495 (E2 SSE-Erbe), #1498 (E6 Dienst-Abriss) und #1499
> (E7 Spec-Cleanup). Bis dahin ist **RAT-31 der bindende Ziel-Zustand**, nicht der
> unten stehende Pilot-Text. Governance: `decisions/RAT-31-wirbelsaeule-abriss.md`.
>
> Status: V1-Pilot (RAT-25) → Ziel-Default (RAT-29) → self-contained (RAT-31) · Refs #1182 #1339
> Architektur ratifiziert via /berater-runde 2026-06-30 (siehe RAT-25), fortgeschrieben RAT-29/RAT-31.
> Deliberation: `brainstorm/berater-runde/20260630-151000-RATIFIZIERT-pwa-shell-mia.md`,
> `brainstorm/berater-runde/20260727-144443-RATIFIZIERT-wirbelsaeule-abriss.md`
> Gate-B-Mockups: `specs/mockups/heim-shell/`

Die Heim-Shell ist ein **dünner Split-Layout-Container**, der auf **einem**
Familien-Gerät die heute getrennten Flächen co-loziert: **Panel-Kachel-Nav
links, gerouteter Buddy-View rechts**. Sie ist **kein neuer Routing-Kern** —
der Live-Refresh läuft same-origin über `seiten/` (SHELL-4, RAT-31 E2); der
frühere Router-Fanout und der `display_id`-Lookup (SHELL-2) sind entfernt.

**V1-Pilot-Scope:** EIN Testgerät (Mia-Tablet `tablet-tablet-mia-01`,
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

### SHELL-2 — ~~`display_id` per Router-Lookup~~ — **OBSOLET (RAT-31 E6f-C, #1588)**
> **RAT-31 E6f-C (2026-07-29, #1588):** SHELL-2 (`_lookup_display_id` / ROU-32-
> Router-Lookup) ist entfernt. Das rechte Buddy-Pane bekommt seinen `src` per
> SSE-getriebenem `iframe.src`-Swap (SHELL-4) — ein `display_id`-Lookup entfällt
> (ein Gerät = ein Ziel, RAT-31). `seiten/main.py::_lookup_display_id` ist
> gelöscht; `--router-url` / `router_url` runtime-Slot entfernt (#1588).
> Tests `test_shell2_lookup_real_url` / `test_shell2_lookup_gibt_none_bei_404`
> gelöscht. Gedeckt durch: `decisions/RAT-31-wirbelsaeule-abriss.md`.

### SHELL-9 — IDs aus Daten, kein Hardcode (n=1)
Weder `panel_id` noch Geräte-IDs stehen im Shell-Code. Die `panel_id` kommt
aus der URL; `display_id` wird nicht mehr nachgeschlagen (SHELL-2 obsolet,
RAT-31 E6f-C). Die konkreten Pilot-IDs (`mias-panel-01`) leben in den
Registry-Daten (xbuddy-data, GER-4 / PREG). Was je Familie variiert, ist
Config/Daten, nicht Code (Familie-3-Probe).
Test-Anker: seiten/tests/test_heim_shell.py::test_shell9_keine_hardcode_ids

## 2. Layout & Einbettung

### SHELL-3 — Split-Layout mit zwei Iframes, Rail 280px
> **RAT-31 E2 (2026-07-27, #1495):** Die linke Rail bleibt der Panel-Nav-Iframe
> auf `/controller/app-panel/<panel_id>` (re-home same-origin, Panel `tiles`+
> Editor bleiben). Das **rechte Buddy-Pane** ist jetzt ein Content-Iframe **ohne
> statischen `src`** — sein Inhalt kommt per SSE-getriebenem `iframe.src`-Swap
> aus dem seiten-seitigen Stream (SHELL-4). Der frühere statische Iframe auf
> `/display/<display_id>` (Router-ausgeliefert) und der ROU-32-`display_id`-Lookup
> (SHELL-2) sind damit überholt — ein Gerät = ein Ziel, kein `display_id`-Match.

> **RAT-31 E6b (#1564) — Rail-src wirklich same-origin von seiten:** Der
> Rail-Iframe `/controller/app-panel/<panel_id>/` wird seit #1564 vom **seiten-
> Service selbst** ausgeliefert (seiten-registry.md SREG-17, app-panel.md
> PANEL-2) — nicht mehr vom Router. Damit ist die „re-home same-origin"-Absicht
> aus E2 eingelöst: Shell (`/shell/`) und Rail (`/controller/app-panel/`) kommen
> aus einem Service, ein Origin, ein Auth-Gate. nginx routet
> `/controller/app-panel/` an `xbuddy_seiten` (vor dem allgemeinen
> `/controller/`-Router-Block).

Die Shell rendert ein zweispaltiges Layout: links eine **Nav-Rail** mit einem
Iframe auf `/controller/app-panel/<panel_id>`, rechts ein **Buddy-Pane** mit
einem Content-Iframe (`id="buddy-pane"`, `src` per SHELL-4-Swap gesetzt). Beide
Iframes füllen ihre Spalte (`width:100%; height:100%`). Die linke Rail hat eine
**feste Breite von 280px** (Gate B 2026-06-30); das Buddy-Pane füllt den Rest
(auf 1920×1200 → 1637px). Bei dieser Rail-Breite legt das Panel seine Kacheln
**selbst einspaltig** aus — das Panel berechnet die Grid-Geometrie adaptiv aus
seiner eigenen Iframe-Breite (PANEL-12 / `app.js::computeGridGeometry`, 1 Spalte
ab ≤ ~360px). Die Shell setzt nur die Rail-Breite; das Panel bleibt
**unverändert** (kein 1-Spalten-Modus nachzurüsten, Leitplanke „Panel
unangetastet" gewahrt).
Test-Anker: seiten/tests/test_heim_shell.py::test_shell3_zwei_iframes

### SHELL-4 — Same-device Live-Refresh: seiten-seitiger SSE-Stream + Ingest
> **RAT-31 E2 (2026-07-27, #1495) — enacted den E0-Banner:** Der Live-Refresh
> läuft jetzt **same-origin über `seiten/`**, nicht mehr über den Router-Fanout.
> Der frühere Satz „die Shell hält keine eigene EventSource / ein Tile-Tap läuft
> über den Router" ist damit **abgelöst**. `router/` und `display-client/`
> bleiben bis E5/E6 (#1498) am Leben und werden hier **nicht** gelöscht — E2
> verpflanzt nur.

> **RAT-35 (2026-07-29) — Amendment zu RAT-31 (n anonyme Geräte, registry-frei):**
> Der Nordstern „ein Gerät für immer" wird ergänzt zu **n anonyme Geräte parallel,
> registry-frei**. Damit wird das unten stehende „**ein** prozess-weiter
> Shell-Zustand … **eine** Subscriber-Menge (ein Gerät = ein Ziel)" **abgelöst**:
> der Zustand wird **pro ephemerer Verbindungs-ID gekeyt** (Mechanismus B, Berater-
> Runde `brainstorm/berater-runde/20260729-1230-RATIFIZIERT-registry-frei-multi-geraet.md`).
> Der Client erzeugt pro Shell-Dokument eine anonyme `crypto.randomUUID()` (`sid`,
> geräte-anonym — **kein** `panel_id`- oder Geräte-Registry-Key, RAT-31-Invariante
> gewahrt), sendet sie beim SSE-Connect (Query-Param) **und** bei jedem
> `tile_selected`/`panel_cleared`. Das Backend hält ein Dict `sid → {state,
> subscribers}` (nicht persistiert, GC bei leerem Subscriber-Set nach Disconnect)
> statt des globalen `_shell_state`. Broadcast geht nur an die Subscriber
> **derselben** `sid` — zwei offene Shells (Pi + Tablet) cross-triggern sich nicht
> mehr. Der Satz „Mehrere offene Shell-Tabs teilen sich denselben Stream" (unten)
> gilt damit nur noch **pro `sid`**. SHELL-5 (Iframe-`src`-Swap) unverändert.
> **Kill-Kriterium:** wächst nach Reconnect die EventSource-Zahl (Geister-`sid`),
> wird die `sid` pro *Tab* (`sessionStorage`) statt pro *Verbindung* gehalten. Bau #1546.

Das `seiten/`-Backend hält den Live-Refresh selbst: **ein prozess-weiter
Shell-Zustand** (kein `display_id`-Dict — ein Gerät = ein Ziel) und **eine**
Subscriber-Menge. Zwei Nähte:

- **SSE-Zustands-Stream** `GET /shell/<panel_id>/events` (`text/event-stream`,
  `Cache-Control: no-cache`, dual-gated wie `/shell/<panel_id>`): liefert den
  aktuellen Zustand beim Verbinden, danach jede Änderung. Heartbeats sind
  data-Events `{"type":"heartbeat"}` (Mobile-EventSource-Lebenszeichen, R6). Der
  Stream hängt an **keinem** `routing.json`-Lookup (Analog ROU-22, ohne den
  `display_id`-Key).
- **Ingest** `POST /shell/<panel_id>/events` (dual-gated): nimmt `tile_selected`
  (Pflicht `app`, `view`; optional flaches `query`, PANEL-7) und `panel_cleared`
  (Ruhe-Zustand). Validierung analog `router adapt_app_panel`. Die `payload.url`
  wird per Konvention `render.build_panel_url` gebaut (`/display/<app>/<view>
  [?<sortiertes query>]`, byte-gleich zum Router — kein Render-Drift) und an den
  SSE-Stream publiziert. **Kein** `source_id`/`display_id`-Match, **kein**
  router-Hop. Die linke Panel-Nav postet bei leerem `router_url` an die Origin
  der Seite (`app.js:985`, #128) → die Nav bleibt **unverändert**.

Das rechte Pane hat eine **eigene** `EventSource` auf `/shell/<panel_id>/events`
(`withCredentials` für den same-origin `xbuddy_session`-Cookie, vgl.
`displib.js:62` #1423) und swappt `iframe.src` aus `payload.url` (Heartbeat-Skip,
unverändert-kein-Reload-Guard DC-2). Mehrere offene Shell-Tabs teilen sich per
Ein-Gerät-Setzung denselben Stream.
Test-Anker: seiten/tests/test_shell_sse.py::test_ac1_sse_liefert_initialen_state,
seiten/tests/test_shell_sse.py::test_ac2_ingest_publiziert_an_offenen_stream,
seiten/tests/test_shell_sse.py::test_ac3_smoke_tap_links_refresh_rechts_ohne_router
nicht_automatisiert: Live-SSE-Verhalten hinter nginx-Proxy · manuelle_probe:
Shell öffnen, 50 Tile-Taps + Netz-Cut/-Wiederkehr; Active-Tile bleibt konsistent,
keine Doppel-Reloads, EventSource-Zahl wächst nach Reconnects nicht (Kill-Kriterium).

### SHELL-5 — Rechtes Pane swappt nur `iframe.src`, keine Codekopie
> **RAT-31 E2 (2026-07-27, #1495):** Das rechte Pane bettet keinen fremden
> Display-Client-Iframe mehr ein — es swappt den `src` seines eigenen
> Content-Iframe (same-origin). Der Empfänger im Shell-Template zeichnet nur den
> ~30-Zeilen-SSE→`iframe.src`-Swap nach (SHELL-4).

Es wird **keine** Display-Client-Datei (`displib.js`) importiert und **keine**
DC-Render-/DC-7-Reconnect-Logik nachgebaut. Der Empfänger beschränkt sich auf:
`EventSource` öffnen, Heartbeats überspringen, bei geändertem `payload.url` den
`iframe.src` setzen (DC-2 unverändert-kein-Reload). Der native Browser-Reconnect
der `EventSource` (SSE-Standard) trägt die Wiederverbindung.
Test-Anker: seiten/tests/test_heim_shell.py::test_shell5_kein_displib_import,
seiten/tests/test_heim_shell.py::test_shell4_pane_ohne_statischen_src

### SHELL-8 — Render auf 1920×1200
Bei Rail 280px rendert die Shell auf 1920×1200 ohne Overflow, ohne
Text-Clipping und mit bedienbaren primären Touch-Zielen in beiden Panes
(Panel-Tiles 280×115px, einspaltig).
nicht_automatisiert: physische Render-/Touch-Wirkung auf dem Tablet ·
manuelle_probe: Render-Gate-Screenshot 1920×1200 mit Rail 280px gegen
Live-Daten (Kill bei Overflow/Clipping/unbedienbar). Gate-B-Beleg:
`specs/mockups/heim-shell/`.

### SHELL-11 — Shell besitzt den Vollbild; eingebettete Iframes unterdrücken Eigen-Vollbild
Die Shell ist der Vollbild-Besitzer: beim ersten Nutzer-Gesture (touchend/click)
fordert die Shell `requestFullscreen` auf `document.documentElement` der **Shell**
an (analog FIG-26, DC-11). Self-healing-Guard: tritt der Nutzer aus dem Vollbild,
holt ihn der nächste Tap zurück. Der eingebettete Panel-Iframe unterdrückt bei
`window.self !== window.top` seinen Eigen-Vollbild-Listener:

- **Panel-Iframe (PANEL-10):** Guard in
  `controller/app-panel/app.js::attachFullscreenOnGesture`.
  Standalone Panel-Geräte (self === top) behalten PANEL-10 unverändert.

> **RAT-31 E6f-C (2026-07-29, #1588):** Der Display-Client-Iframe (DC-11 embedded-
> Ausnahme, `display-client/index.html`) ist gelöscht — das rechte Buddy-Pane ist
> ein leerer Content-Iframe (kein DC-Embed mehr). Bullet und Test-Anker entfernt.

Umsetzung: Inline-Script in `seiten/templates/heim-shell.html` (SHELL-11-Block)
+ Guard an der Panel-Konsument-Aufrufstelle.
Test-Anker: seiten/tests/test_heim_shell.py::test_shell11_panel_embedded_guard,
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

### SHELL-6.a — Funnel-Cookie-Rollout löst den LAN-only-Riegel ab (RAT-27 (RATIFIZIERT 2026-07-07))

> **RAT-27 (RATIFIZIERT 2026-07-07) — noch nicht ratifiziert** (#1388, Epic #1338; zur
> Nic-Ratifizierung). Bindewirkung erst mit RAT-27. **Bis dahin gilt SHELL-6
> unverändert** (LAN-only-Riegel scharf, Funnel verboten).

RAT-25 wird durch den Auth-Funnel-Rollout **superseded, nicht getötet**: der
LAN-only-Riegel war die bewusst eingehegte **Ein-Wege-Kante** des Pilots
(RAT-25 „eine Ein-Wege-Kante = Auth"), solange AUTH-7 nur eine unratifizierte
IP-Skizze war. Mit der AUTH-7-Ratifizierung (7a/7b-Gabel, RAT-27) fällt genau
diese Kante — der Grund für den Riegel (kein sicherer Funnel-Pfad) existiert
dann nicht mehr.

- **Die Heim-Shell darf über den Funnel laufen** — als AUTH-7b-Konsument:
  `/shell/<panel_id>` und `/api/v1/displays/<id>/events` sind über den Funnel
  erreichbar, **gated durch den Dual-Gate** (Cookie ODER Operator-IP,
  `auth.md` AUTH-7). Ein User-Gerät mit `xbuddy_session`-Cookie erreicht die
  Shell extern; ein cookie-loser fremder Funnel-Client bekommt `401`.
- **Heim-LAN bleibt Fallback, kein Funnel-Zwang.** Der schnellste Weg im Haus
  ist weiter der LAN-Direktzugang (`display_url_origin_heim`); der
  Operator-Pi trägt die Shell weiterhin über die 7a-IP-Allowlist **ohne**
  Cookie. Der Funnel-Weg ist **additiv** für externe User-Geräte, nicht die
  einzige erlaubte Origin (`seiten-registry.md` SREG-7:
  heim/tailscale/funnel).

**Was RAT-25 behält:** die gesamte Split-Layout-/Iframe-/Zwei-EventSource-
Architektur (SHELL-1..SHELL-11) bleibt unverändert — SHELL-6.a berührt
**nur** die Auth-/Exposure-Kante, nicht den Renderer-Kern. Der
Pre-Merge-Funnel-Test (SHELL-6, externer Client) kehrt sich um: nach RAT-27
muss `curl https://<funnel-fqdn>/shell/<panel_id>` **mit** gültigem Cookie
`200` liefern und **ohne** Cookie/Operator-IP `401` — statt pauschal `4xx`.

*Tickets:* #1388, #1338

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
`panel_id` (analog PWA-1); für den Pilot ist `start_url = /shell/mias-panel-01`.
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

**Service-Worker** (`seiten/static/shell/sw.js`, Scope `/shell/`):
- Shell-HTML (`/shell/<panel_id>`) wird **network-first** behandelt (T1448
  stale-Cache-Fix): Netz zuerst, Cache-Fallback bei Netz-Fehler. Stellt sicher,
  dass die HTML-Shell nach einem Deploy immer frisch geladen wird; Offline bleibt
  durch den Cache-Fallback nutzbar. 5xx-Antworten werden nicht gecacht.
- Statische Mantel-Assets (`heim-shell.css`, `platform.js`) werden cache-first
  behandelt — sie sind BUILD_ID-versioniert und invalidieren über `CACHE_NAME`.
- Panel-/Display-Iframes (`/controller/`, `/display/`) werden **nicht** abgefangen
  — deren eigene SWs sind zuständig (stop_rule sw_scope).
- BUILD_ID-Platzhalter wird beim Ausliefern durch `shell_asset_view` ersetzt
  (Cache-Versionierung analog ESSEN-35).
- Auslieferung: `/shell/<panel_id>/sw.js` mit `Service-Worker-Allowed: /shell/`
  Header (Scope-Erweiterung über SW-Datei-Pfad hinaus).

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
