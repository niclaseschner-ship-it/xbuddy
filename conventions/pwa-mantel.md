# PWA-Mantel — Konvention     (ID-Präfix: PWAM)

*Status: RATIFIZIERT 2026-07-01 (Nic-Gate + Codex Pass-2, #1215). Quelle der
Ratifizierung: `berater-runde/20260701-164714-RATIFIZIERT-1215-pwa-mantel-unify.md`
(Nic-Verdikt „Unify-Override"). Jede Klausel trägt ihren Herleitungs-Anker
inline als `ENTSCHEID → <Sektion> → <Stichwort>`.*

XBuddy verpackt mehrere Eltern-Power-Flows als **installierbare Web-Apps** —
nicht als Browser-Tabs. Diese „Mantel"-PWAs (Einkaufsliste, Plan-Einstellungen,
Heim-Shell, Connector) haben denselben Bauplan: ein `manifest.json`, ein
`sw.js` mit Cache-Buster, und eine Server-Route, die den Cache-Namen beim
Ausliefern mit einer `build_id` versieht. Sie wurden n-fach per Copy-Paste
gebaut und sind zu ~80 % durch **Drift und Per-App-Daten** auseinandergelaufen,
nicht durch echte Sorten-Unterschiede.

**Kern-Setzung (Nic 2026-07-01, Unify-Override):** Die Mantel-PWAs werden
**vereinheitlicht** — eine zentrale Lib (Manifest-Bauplan + `sw.js`-Skelett +
`build_id`-Helfer) + eine kleine Config-Registry, die nur die *echten*
Unterschiede als Daten trägt. Die Divergenz wird **entfernt**, nicht
dokumentiert. Ein fünftes Exemplar wird **registriert, nicht geforkt**.
`ENTSCHEID → "NIC-VERDIKT 2026-07-01" → vereinheitlichen (zentrale Lib)`.

> **Reversierung von RAT-19 — bewusst und sichtbar.** RAT-19 hatte die
> Konventions-Festschreibung des Power-Flow-PWA-Musters nach `conventions/pwa.md`
> vertagt (Landeplatz-Setzung). Diese eigene Datei reversiert diese
> Landeplatz-Wahl bewusst: Die Mantel-Sorte teilt mit der Kiosk-/Geräte-Install-
> Sorte (`conventions/pwa.md`, PWA-1..4) nur die Install-Naht und *widerspricht*
> ihr sonst (siehe PWAM-2). Ein File = eine Sorte. `pwa.md` bleibt für die
> Kiosk-Sorte unverändert. `ENTSCHEID → "Entscheidung — MACH ES" → eigene Datei,
> reversiert RAT-19 bewusst`.

**Diese Konvention ist eine Bauregel, die maschinell durchgesetzt werden darf**
(vgl. `conventions/README.md`): sobald die zentrale Lib steht, prüft der
Watchdog neue/geänderte Mantel-PWAs gegen PWAM-1..6. Die **Code-Konsolidierung**
(Lib bauen, die vier Konsumenten migrieren, connector-Bugs fixen) ist ein
**Folge-Bau-Track**, kein Teil dieses Doku-Entwurfs.

---

### PWAM-1 — Was ein Mantel ist + Konsumenten-Registry

Ein **Mantel** ist eine installierbare PWA, die einen server-gerenderten oder
JS-getragenen Eltern-Power-Flow in eine App-Hülle verpackt: ein `index.html`,
ein `manifest.json` (PWAM-2), ein `sw.js` (PWAM-3) und eine Asset-Route mit
`build_id`-Cache-Buster (PWAM-4). `ENTSCHEID → "Wo es landet (Genre + IDs)" →
PWAM-1 Mantel-Definition`.

**Registrierte Konsumenten (n=5 real, Stand T1665):**

| Konsument | manifest | sw.js | Cache-Buster-Route | Spec |
|---|---|---|---|---|
| einkauf | `seiten/static/einkauf/manifest.json` | `seiten/static/einkauf/sw.js` | `einkauf_asset_view` `seiten/main.py:607` | ESSEN-33/34/35 |
| plan | `seiten/static/plan/manifest.json` | `seiten/static/plan/sw.js` | `plan_einstellungen_asset_view` `seiten/main.py:722` | PLAN-35 |
| heim-shell | DYNAMISCH `heim_shell_manifest` `seiten/main.py:1015` | `seiten/static/shell/sw.js` | `shell_asset_view` `seiten/main.py:1107` | SHELL-PWA |
| connector | `seiten/static/connector/manifest.json` | `seiten/static/connector/sw.js` | **fehlt** (statisch `BUILD='v1'` sw.js:15) | CONN-8 |
| routine | LIB `build_manifest()` via `routine_anpassen_asset_view` | LIB `render_sw()` via `routine_anpassen_asset_view` | `/seiten/routine/anpassen/<asset>` `seiten/main.py` | ROUTINE-20/23 (T1665) |

**connector ist ein registrierter, aber noch nicht voll-konformer Mantel.** Er
zählt erst **nach der Install-Probe** als voll konform — bis dahin trägt er drei
offene Angleichungen: Icon-Form (PWAM-2), statischer `BUILD='v1'`-Cache-Buster
(PWAM-3) **und** ein SW-Scope-/Route-Bruch, bei dem das SW-Skript nicht unter der
`start_url` liegt (PWAM-3, SW-Scope-Mandat). Registrierung ≠ Konformität: der
5.-Mantel-Registriert-statt-Forkt-Anspruch (PWAM-5) gilt, die Install-Probe im
Folge-Bau ist die Abnahme. `Pass-2-Report → [BRICHT] Connector-SW-Scope
(2026-07-01-2046-antiberater-1215-pwa-mantel-pass2.md:11-17)`.

**Abgrenzung zur Kiosk-Sorte (`conventions/pwa.md`, PWA-1..4):** Die dort
geregelten Controller-PWAs und der Display-Client sind eine **andere Sorte**
(Geräte-Vollbild-Install, Wake-Lock, `config.json`-Selbstgenügsamkeit). Diese
Konvention **cross-referenziert** PWA-1 (`conventions/pwa.md:21-32`) für das
Grund-Prinzip „installierbare Web-App mit Manifest + SW + Icons", **dupliziert
es aber nicht** und überschreibt die manteltypischen Felder (PWAM-2). Kein
Genre-Doppel. `ENTSCHEID → "Entscheidung — MACH ES" → Ein File = eine Sorte,
Cross-Ref PWA-1`.

**Mantel-intern gibt es genau EINE Sorte** — der Berater-Lean „zwei Sorten
(Geräte-Surface / Content-Utility)" ist durch das Nic-Verdikt überstimmt: die
Unterschiede sind Daten und zwei benannte Konfigurationsknöpfe (PWAM-3), keine
zweite Bauart. `ENTSCHEID → "NIC-VERDIKT 2026-07-01" → keine zwei Sorten`.

### PWAM-2 — Manifest-Bauplan (Per-App-Daten aus der Registry)

Das `manifest.json` jedes Mantels wird aus der Registry (PWAM-5) gebaut. Diese
Felder sind **Per-App-Daten**, keine Sorten-Unterschiede:

- `name`, `short_name`, `description` — Registry-String.
- `start_url` / `scope` — **absoluter Präfix** des Konsumenten (nicht `"./"`).
  Belegt: einkauf `"/seiten/essen/einkauf/"`, plan `"/seiten/plan/einstellungen/"`,
  connector `"/api/v1/seiten/connector/"` (connector/manifest.json:5-6). Dies
  ist die bewusste **Abweichung von PWA-2** (`conventions/pwa.md:56` fordert
  `"./"`) — Mantel-Routen sind absolut gemountet. `ENTSCHEID → "NIC-VERDIKT
  2026-07-01" → start_url = Registry-Param`.
- `orientation`, `background_color`, `theme_color`, `lang` — Registry-String.

**Ein deklarierter Param:**

- `display` — `"fullscreen"` **oder** `"standalone"`, als **einzelnes
  Registry-Feld** deklariert. Belegt: einkauf/plan `fullscreen`
  (einkauf/manifest.json:7), connector `standalone`
  (connector/manifest.json:7). Auch dies weicht bewusst von PWA-2
  (`conventions/pwa.md:59`, fordert `fullscreen`) ab — der Mantel darf pro App
  wählen. `ENTSCHEID → "NIC-VERDIKT 2026-07-01" → display fullscreen/standalone
  = 1 Param`.

**Icon-Standard (Mandat, kein Param): PNG 192×192 + 512×512 + maskable-512.**
Belegt als bereits gelebte Norm bei einkauf (einkauf/manifest.json: `icon-192.png`,
`icon-512.png`, `icon-maskable-512.png`) und plan (analog). **Der connector ist
Drift, nicht Sorte:** sein Manifest nutzt zweimal dieselbe SVG
(`anthropic.svg`) mit `sizes:"any"` (connector/manifest.json:12-24) — das ist
**kein** zweites Icon-Profil, sondern ein WebAPK-Install-Risiko.
**Angleichungs-Mandat:** connector auf PNG 192/512/maskable ziehen; der
WebAPK-Install auf Ziel-Chrome/Android ist der Beleg (Install-Probe im
Folge-Bau, bevor connector als voll konformer Mantel zählt). `ENTSCHEID →
"Codex-Patches" → Patch B Icon-Form (connector-SVG ist Drift)`.

### PWAM-3 — `sw.js`-Skelett (EIN geteiltes) + zwei echte Config-Knöpfe

Alle Mäntel teilen **ein** `sw.js`-Skelett (install → precache; activate →
alte Cache-Namespaces räumen; fetch → Dispatch cache-first / network-first).
Belegt byte-nah zwischen einkauf (einkauf/sw.js:21-22) und plan (plan/sw.js:18-19)
— identische Struktur, nur App-Name + Cache-Präfix unterscheiden sich.

**Genau zwei load-bearing Config-Knöpfe** (der Rest ist Daten):

- `HTML_CACHE_MODE` — steuert, ob die HTML-Shell gecached wird. Der **connector
  cached HTML bewusst NICHT** (network-only pass-through, connector/sw.js:10-11):
  sein server-gerendertes Aggregat (CONN-8) darf nie veralten. Ohne diesen Knopf
  würde connector-HTML versehentlich cache-first.
- `STOP_PREFIXES` — Pfad-Präfixe, die der SW **nicht** abfängt. Die **heim-shell**
  lässt `/controller/` und `/display/` als Panel-Iframe-Requests durch
  (shell/sw.js:100-104); deren eigene Service-Worker sind zuständig. Ohne diesen
  Knopf fängt der Shell-SW Iframe-Requests ab.

`ENTSCHEID → "NIC-VERDIKT 2026-07-01" → 2 Knöpfe: HTML_CACHE_MODE, STOP_PREFIXES`
und `ENTSCHEID → "Codex-Patches" → Verschärfung C (echte Config-Felder)`.

**Weitere Config-Felder als Daten** (kein Sorten-Unterschied): `CACHE_NAMESPACE_PREFIX`
(App-Namespace für die zu räumenden Caches, belegt einkauf/sw.js:66
`startsWith('einkauf-pwa-')`) und `ARASAAC` (network-first-Behandlung der
Piktogramm-Assets, wo genutzt).

**Statisch manuell-gebumpte `CACHE_NAME`-Konstante ist VERBOTEN.** Der Cache-Name
muss die vom Server substituierte `build_id` tragen (PWAM-4), Skelett hält
`const BUILD_ID = '__BUILD_ID__'` (einkauf/sw.js:21). Der connector verletzt das
mit `const BUILD = 'v1'` (connector/sw.js:15) — eine Konstante, die niemand
bumpt, sodass der connector-SW-Cache **nie invalidiert**. **Angleichungs-Mandat:**
connector auf `__BUILD_ID__`-Server-Substitution ziehen (fixt den realen
Cache-Buster-Bug). `ENTSCHEID → "NIC-VERDIKT 2026-07-01" → connector BUILD='v1'
statisch = Cache-Buster-Bug → build_id`.

**SW muss unter einem `start_url`-umfassenden Scope ausgeliefert werden** (zwei
Registry-Felder, PWAM-5: `sw_script_route` + `sw_scope`). Ein SW steuert nur
Requests innerhalb seines Registrierungs-Scopes, und der Default-Scope ist der
Pfad, unter dem das Skript liegt. Die Geschwister registrieren ihren SW im
App-Pfad mit korrektem Scope: einkauf (`seiten/templates/essen-einkauf.html:54-61`),
plan (`seiten/templates/plan-einstellungen.html:118-123`), shell explizit über
`Service-Worker-Allowed`-Header (`seiten/templates/heim-shell.html:68-78` +
`seiten/main.py:1138-1146`). **Der connector bricht das:** er registriert den SW
unter `/api/v1/seiten/static/connector/sw.js`
(`seiten/static/connector/index.html:146-151`), während `start_url`/`scope`
`/api/v1/seiten/connector/` sind (`seiten/static/connector/manifest.json:5-6`) —
das Skript liegt **nicht** unter der `start_url`, der Default-Scope umfasst sie
nicht, der SW kontrolliert die App-Seite gar nicht. **Angleichungs-Mandat:**
connector-SW über eine eigene `connector_asset_view`-Route mit
`build_id`-Substitution unter `/api/v1/seiten/connector/sw.js` (oder äquivalent
via `Service-Worker-Allowed` auf den `start_url`-Scope) ausliefern. `ENTSCHEID →
"NIC-VERDIKT 2026-07-01" → connector angleichen (Drift, keine Sorte)` +
`Pass-2-Report → [BRICHT] Connector-SW-Scope
(2026-07-01-2046-antiberater-1215-pwa-mantel-pass2.md:11-17)`.

### PWAM-4 — `build_id`-Helfer als Source-**Set**, nicht Single-Path

Die `build_id` ist die höchste Änderungszeit eines **deklarierten Datei-Sets**,
nicht einer einzelnen Datei:

    build_id_from_mtimes(paths: list[str]) -> str   # = max(mtime über paths), OSError→"0"

**Warum ein Set, nicht ein Pfad:** Der geltende Mini-App-HTML-Helfer ist bereits
`max(mtime(primary_js), mtime(platform.js))` (`_mini_app_build_id`,
`seiten/main.py:588-603`) — Test-Anker T1229
(`seiten/tests/test_t1229_build_id_platform_js.py`) verlangt, dass ein
`platform.js`-Bump die **HTML**-Route invalidiert. Ein Single-`source_path`-Helfer
würde diesen richtigen Multi-Source-Zuschnitt zerstören. Pro Konsument steht das
Source-Set als **Registry-Daten** (PWAM-5): einkauf/plan `[primary_js,
platform.js]`, shell `[heim-shell.css]`, connector `[index.html, style.css]`
(nach Install-/Diff-Probe). `ENTSCHEID → "Codex-Patches" → Patch A (build_id ist
ein Source-SET)`.

**Pflicht-Kill-Kriterium: der SW-`build_id` MUSS auf `build_id_from_mtimes([…
inkl. platform.js])` migriert werden — nicht nur der HTML-`build_id`.** Heute ist
genau das die offene Lücke: die **SW**-Auslieferung nutzt bei einkauf
`_current_build_id()` = nur `essen-einkauf.js` (`seiten/main.py:579-583`,
Serve-Pfad `637-638`) und bei plan `_plan_einst_build_id()` = nur
`plan-einstellungen.js` (`seiten/main.py:679-683`, Serve-Pfad `747-748`). #1229
fixte ausschließlich den **HTML**-Pfad (`_mini_app_build_id`,
`seiten/main.py:588-603`), **nicht** den SW. Damit trägt der installierte SW bei
reinem `platform.js`-Bump denselben `CACHE_NAME` und servt/precached alte Assets.
Der Ratifizierungs-Record fordert aber ausdrücklich neuen Cache-Namen bei
`platform.js`-Bump (`berater-runde/20260701-164714-RATIFIZIERT-1215-pwa-mantel-unify.md:37-41`).
**Test-Gate VOR dem Skelett-Sharing** (heute NICHT abgedeckt — T1229 prüft nur
HTML, `seiten/tests/test_t1229_build_id_platform_js.py`): „`platform.js`-mtime
neuer ⇒ `GET /seiten/essen/einkauf/sw.js` **und** `GET /seiten/plan/einstellungen/sw.js`
tragen den neuen `CACHE_NAME`". Muss rot/grün zeigen; sonst ist PWAM-4 nur für
HTML belegt, nicht für SW-Invalidierung. `ENTSCHEID → "Codex-Patches" → Patch A
(build_id ist ein Source-SET)` + `Pass-2-Report → [RISKANT] SW-Cache-Buster
(2026-07-01-2046-antiberater-1215-pwa-mantel-pass2.md:19-25)`.

**Ein Server-Helfer `read_sw_with_build_id(component)`** ersetzt die drei
byte-identischen 3-Zeiler `content.replace("__BUILD_ID__", build_id)`:
`_read_sw_with_build_id` (`seiten/main.py:567`), `_read_plan_sw_with_build_id`
(`seiten/main.py:688`), `_read_shell_sw_with_build_id` (`seiten/main.py:1099`).
Sie kollabieren in einen. Ebenso kollabieren die near-identischen
`build_id`-Ableiter (`_current_build_id` `seiten/main.py:579`, `_mini_app_build_id`
`seiten/main.py:588`, `_plan_einst_build_id` `seiten/main.py:679`,
`_connector_build_id` `seiten/main.py:790`, `_shell_build_id`
`seiten/main.py:1090`) in `build_id_from_mtimes` + Registry-Source-Set — wobei
der SW-Serve-Pfad denselben Multi-Source-`build_id` bekommt wie die HTML-Route
(s. Kill-Kriterium). `ENTSCHEID → "Was sich ändert / Trade-off" → Helfer-Trio
kollabiert`.

> **Sequenz-Hinweis (Zwei-Wege-Tür-Anteil):** Die reine Server-Helfer-Dedup ist
> reversibel und kann sofort im Folge-Bau erfolgen; das Skelett-Sharing wird
> byte-diff-gesichert (einkauf+plan generiert == committed, modulo `build_id`),
> dann connector (Drift-Fix), dann shell (dynamisches Manifest, meiste Vorsicht).
> Der SW-`build_id`-Test (oben) ist Vorbedingung des ersten Schritts.
> `ENTSCHEID → "Sequenzierung" → Server-Helfer sofort, Skelett gestaffelt`.

### PWAM-5 — `component → config`-Registry (5. Mantel registriert, nicht forkt)

Eine zentrale Registry bildet jeden Konsumenten auf seine Config ab. Ein neuer
Mantel wird durch einen **Registry-Eintrag** hinzugefügt, nicht durch Kopieren
von Manifest/SW/Route. Felder pro Eintrag:

- **Manifest (PWAM-2):** `name`, `short_name`, `description`, `start_url`/`scope`
  (absolut), `display` (`fullscreen`|`standalone`), `orientation`,
  `background_color`, `theme_color`, `lang`, Icon-Set (PNG-Standard).
- **Service-Worker (PWAM-3):** `HTML_CACHE_MODE`, `STOP_PREFIXES`,
  `CACHE_NAMESPACE_PREFIX`, `ARASAAC`, Precache-Asset-Liste, **`sw_script_route`**
  (Route, unter der der SW ausgeliefert wird) und **`sw_scope`** (Scope, den er
  steuern soll — muss die `start_url` umfassen). Diese zwei Felder tragen den
  connector-Scope-Fix als Mantel-Daten statt als Sonderfall.
- **Cache-Buster (PWAM-4):** `build_id_source_set` (Liste von Pfaden, inkl.
  `platform.js` bei einkauf/plan — gilt für HTML- **und** SW-Route, s. PWAM-4).

`ENTSCHEID → "Wo es landet (Genre + IDs)" → PWAM-5 component→config-Registry`
und `ENTSCHEID → "NIC-VERDIKT 2026-07-01" → kleine Config-Registry`.

### PWAM-6 — Scroll-/Viewport-Baseline (`mini-app-base.css`), opt-in pro geprüfter App

Eine zentrale `mini-app-base.css` liefert einen **uniformen Scroll-Root** — statt
den Scroll-Container pro App hand zu rollen. Baseline:

    html, body { min-height: 100dvh; }
    body { overflow-x: hidden; overscroll-behavior: contain; }

**Warum:** Die Scroll-Root-Behandlung driftet heute pro Datei. `mini-app-uebersicht.css:31-34`
und `routine-anpassen.css:36-39` setzen `html { overflow-x: hidden; max-width: 100% }`;
`essen-einkauf.css` setzt gar keine `html`-Regel und beginnt direkt mit `body`
(essen-einkauf.css:43). `overscroll-behavior: contain` ist mehrfach hand-gerollt
(uebersicht:43, routine:48, einkauf:48). Keine `mini-app-base.css` existiert
heute — jede App trägt ihre eigene Variante. Die Baseline zieht das in **eine**
Quelle. `ENTSCHEID → "NIC-VERDIKT 2026-07-01" → PWAM-6 Scroll-Baseline
(mini-app-base.css, im selben Stein)`.

**Geltungsbereich: opt-in pro App, nicht „alle Mini-Apps" pauschal.** Eine
Blanket-Einbindung würde bewusste Spezialflächen regressieren:
- **heim-shell** will bewusst `html, body { height: 100%; overflow: hidden }`
  (`seiten/static/heim-shell.css:7-13`, SHELL-8: kein Overflow auf 1920×1200) —
  das **Gegenteil** eines `100dvh`-Scroll-Roots.
- **connector** hat gewollten horizontalen Tabellen-Scroll
  (`seiten/static/connector/style.css:349-350`, `684-685`) —
  `overflow-x: hidden` global würde ihn abschneiden.
- **plan** zentriert `html, body` auf `max-width: 760px`
  (`seiten/static/plan-einstellungen.css:7-20`) — eine bewusste eigene
  Viewport-Form.

Deshalb: `mini-app-base.css` wird **pro App aufgenommen, erst nach
Screenshot-/Scroll-Probe** (mobil + desktop): kein neuer Horizontal-Scroll, keine
abgeschnittenen Bottom-Sheets, Shell bleibt 100%-Viewport ohne Body-Scroll. Die
Probe ist das Kill-Kriterium pro App. `ENTSCHEID → "NIC-VERDIKT 2026-07-01" →
PWAM-6 Scroll-Baseline (mini-app-base.css, im selben Stein)` +
`Pass-2-Report → [RISKANT] PWAM-6 zu breit
(2026-07-01-2046-antiberater-1215-pwa-mantel-pass2.md:27-33)`.

**Belegter Fall (das, was jetzt tatsächlich angleicht):** uebersicht/routine
(kein einheitlicher Scroll-Root) auf die Base ziehen. **hoerspiel ist schon
konform** — `hoerspiel/static/eltern.css:24-29` setzt bereits `body { min-height:
100dvh }`; es braucht keine Angleichung und ist damit kein Bruchbeleg. Der
Geltungsbereich ist also die belegte Scroll-Root-Divergenz, nicht jede
Mini-App-Fläche.

---

## Offene Fragen

1. **AUFGELÖST (Pass-2) — Scroll-Symptom ist gegript, nur am falschen Ort
   gesucht (PWAM-6).** Die Ratifizierung nannte „hoerspiel-100dvh". Der Beleg
   liegt in `hoerspiel/static/eltern.css:24-29` (`body { min-height: 100dvh }`),
   nicht in `seiten/static/` — hoerspiel ist damit **bereits konform** und kein
   Bruchbeleg. Der belegte, angleichbare Fall ist die Scroll-Root-Divergenz
   uebersicht/routine (kein einheitlicher Root) gegen die geteilte Base. PWAM-6
   ist entsprechend als opt-in-pro-App umformuliert (s. o.); die pauschale
   „alle Mini-Apps"-Setzung ist zurückgenommen.

2. **connector-`build_id_source_set` + SW-Route stehen zusammen unter Vorbehalt
   (PWAM-4/PWAM-3).** Das Set `[index.html, style.css]` ist erst nach der
   Install-/Cache-Probe final; heute nutzt connector `mtime(index.html)` für die
   HTML-Route (`_connector_build_id`, `seiten/main.py:790`), aber **gar keine**
   Substitution im SW und liefert den SW unter einem Scope aus, der die
   `start_url` nicht umfasst (PWAM-3, SW-Scope-Mandat). Der Folge-Bau bestimmt
   Set **und** `sw_script_route`/`sw_scope` gemeinsam; die WebAPK-Install-Probe
   ist die Abnahme.

3. **heim-shell dynamisches Manifest (PWAM-2/5) — RAT-29 entschieden.**
   `heim_shell_manifest` (`seiten/main.py:1015`) baut das Manifest per `panel_id`
   zur Laufzeit. **RAT-29 (2026-07-24)** hat die offene Frage aufgelöst:
   `REGISTRY["shell"]` ist ein **First-Class-Eintrag** (kein Spezialfall-Kommentar).
   `build_manifest()` bekommt einen `panel_id`-Ast für die dynamische `start_url`;
   alle anderen PWAM-5-Felder (`name`, `sw_scope` etc.) trägt der Registry-Eintrag
   statisch. `ENTSCHEID → "Kill-Kriterium" → shell ist REGISTRY-First-Class,
   panel_id-Ast in build_manifest()`. Refs #1409.
