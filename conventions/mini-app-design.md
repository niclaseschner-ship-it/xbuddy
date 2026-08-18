# Mini-App-Design — Konvention     (ID-Präfix: MAD)

> **Status: ratifiziert beim 2. Mini-App-Konsumenten 2026-06-15 (#708).** Diese
> Konvention war zwischen Juni 2026 als „First Occurrence" in
> `brainstorm/conventions-vorab/mini-app-design-erstes-vorkommen.md` geparkt und
> trägt jetzt die bindenden MAD-IDs für alle Mini-App-Konsumenten. Erster Anwender:
> essen-einkauf (#653, Combine-PR #688). Zweiter Anwender, der die Ratifizierung
> auslöst: routine-anpassen-Mini-App (#728, Combine-PR Spec #717/#731). Auth-
> Härtung über alle Mini-Apps: #708-Folge-Strecke.

## Andocken an DTOK

Mini-Apps **erfinden keine eigenen Farb-/Maß-Werte**. Sie andocken am
geteilten Design-Token-Strang aus `conventions/design-tokens.md` (DTOK-1:
`display/_shared/design/tokens.css`), soweit das Token-Schema passt. Wo der
Telegram-Mini-App-Context **andere** Werte braucht (Touch-Phone statt
Kiosk-Display, native Telegram-Theme-Variablen), gilt MAD ergänzend zu DTOK,
nicht gegen es.

---

### MAD-1 — Skalierungs-Parameter als zentrales Tuning-Idiom

Jede Mini-App-Card-Liste (oder vergleichbare Listen-UI) trägt **eine einzige
CSS-Custom-Property als Tuning-Parameter**, von der alle Maße ableitend per
`calc(...)` berechnet werden. Default als Kommentar dokumentiert.

```css
:root {
  /* --item-scale: zentraler Multiplikator. 1.0 = Original,
     <1 = kompakter, >1 = größer. Tunen = nur diese Zahl ändern. */
  --item-scale:        0.67;
  --item-min-height:   calc(60px * var(--item-scale));
  --item-bild-size:    calc(44px * var(--item-scale));
  --item-check-size:   calc(28px * var(--item-scale));
  --item-padding-y:    calc(10px * var(--item-scale));
  --item-padding-x:    calc(12px * var(--item-scale));
  --item-gap:          calc(12px * var(--item-scale));
  --item-label-size:   calc(1rem * var(--item-scale));
}
```

**Wenn** ein Maß sich beim Skalieren mitziehen soll, **dann** lebt es als
abgeleitete Variable und ist im CSS via `var(--…)` referenziert — niemals als
hartcodierter `px`/`rem`-Wert in der Card-Klasse.

*Test-Implikation:* Setze `--item-scale: 0.5` testweise — die Card-Liste muss
proportional schrumpfen, kein Element bleibt zurück. Setze auf `1.5` —
proportional wachsen, kein Element wird ungelenk.

*Tickets:* #653 (essen-einkauf, erstes Vorkommen)

---

### MAD-2 — Card-Liste-Layout: Bild · Text · (Marker) · Aktion

Mini-App-Card-Listen folgen dem **Bring!-Pattern**: pro Eintrag eine flache
Card mit (links) Piktogramm, (mitte, flex) Label-Text, (rechts) optional ein
Quellen-/Status-Marker, (ganz rechts) ein Tap-Affordanz-Element (Häkchen,
Toggle).

```html
<div class="item-card" data-...>
  <img class="item-bild" src="..." alt="" loading="lazy">
  <div class="item-text">
    <span class="item-label">…</span>
  </div>
  <span class="item-marker">🧒</span>            <!-- optional -->
  <div class="item-check">✓</div>
</div>
```

- **Image:** `loading="lazy"`, `alt=""` (leer wenn Label das Bild bereits
  beschreibt — sonst beschreibend).
- **Kein `onerror`-Fallback-Bild**: wenn das Bild 404 gibt, zeigt der Browser
  sein Default-Symbol. Ein eigenes Fallback-Emoji-Bild bringt keinen Mehrwert
  und neigt zu HTML-Escape-Bugs (essen-einkauf-Erfahrung 2026-06-12).
- **Erledigt-Optik:** `.item-card.erledigt` setzt `opacity` und
  `text-decoration: line-through` — kein eigenes Layout.
- **Touch-Target:** `min-height` über `--item-min-height` (Skalierungs-Default
  hält ≥ 40px, ab `--item-scale: 0.5` wird's hart).

*Tickets:* #653

---

### MAD-3 — Floating Action Button (FAB) für die primäre Hinzufügen-Geste

Die primäre „Element hinzufügen"-Geste lebt als **FAB** am unteren Bildrand:

```css
.fab {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: var(--fab-size, 56px);
  height: var(--fab-size, 56px);
  border-radius: 50%;
  background: var(--fab-bg, var(--accent));
  /* ... */
}
```

Nur **eine** primäre Aktion pro View. Mehrere Aktionen via Bottom-Sheet, nicht
mehrere FABs. Position `right` (rechtshänder-Daumen) — wenn der erste Test
zeigt, dass linkshändige Nutzer dominieren, links erlauben.

*Tickets:* #653

---

### MAD-4 — Bottom-Sheet-Pattern für Auswahl + Eingabe

Modale Auswahl, Mehrfach-Eingabe und Quick-Add laufen als **Bottom-Sheet**,
nicht als Vollbild-Dialog:

```html
<div id="sheet-overlay" class="sheet-overlay" hidden aria-modal="true" role="dialog">
  <div id="sheet" class="sheet">
    <div id="sheet-inhalt" class="sheet-inhalt"></div>
  </div>
</div>
```

- **`role="dialog"`**, **`aria-modal="true"`**, **`hidden`** Default.
- Overlay-Hintergrund: `var(--sheet-overlay)` (CSS-Token).
- Tap außerhalb der Sheet schließt sie (Standard-Bring!-Verhalten).
- Inhalt: JS-rendered, kein Server-Round-Trip pro Sheet-Öffnung.

*Tickets:* #653

---

### MAD-5 — Vendor-Disziplin: `platform.js`-Wrapper

Mini-App-Frontends **dürfen kein direktes Telegram-Vokabular** verwenden — kein
`window.Telegram.WebApp.*`, kein `reply_markup`-JSON, kein `inline_keyboard`.
Alle Plattform-Abhängigkeiten laufen über den `platform.js`-Wrapper
(`seiten/static/platform.js`, RAT-16-Adapter-Disziplin im Frontend).

```javascript
import { getPlatform } from "/api/v1/seiten/static/platform.js";
const platform = getPlatform();
await platform.ready();
const user = platform.getCurrentUser();   // {id, first_name} oder null
platform.setMainButton(label, onClick);
platform.enableClosingConfirmation();
platform.onSave(callback);
```

**Anti-Pattern:**
- `localStorage` für Dirty-State (Telegram-native `enableClosingConfirmation`
  reicht).
- `window.Telegram.WebApp.MainButton.show()` direkt — geht über
  `platform.setMainButton`.

*Test-Implikation:* `grep -c "Telegram.WebApp" mini-app.js = 0` außerhalb der
`platform.js`-Detection.

*Tickets:* #684 (Track D), #653

---

### MAD-6 — Asset-Pfade: `/api/v1/seiten/static/<datei>` für JS/CSS, `/display/_shared/icons/arasaac/<id>.png` für Piktogramme

Statische Mini-App-Assets liegen im seiten-Service:

- CSS/JS: `/api/v1/seiten/static/<datei>` (Flask `static_url_path` ist
  `/api/v1/seiten/static`). nginx-Origin routet `/api/v1/seiten/` zum
  seiten-Service. **Kein `/seiten/static/`-Pfad** — auch wenn er natürlicher
  aussieht, das war ein 404-Bug in essen-einkauf (2026-06-12).
- Piktogramme: `/display/_shared/icons/arasaac/<bild_ref>.png` — Same-Origin,
  vom Router serviert (ROU-26, ICONS-5). **Kein `/_shared/icons/...`** ohne
  `/display/`-Präfix.

*Tickets:* #653 (Live-Fix-Lehre)

---

### MAD-7 — Authentifizierung: `Authorization: tma <initData>`-Header (im Auslaufen seit 2026-06-16)

> **Status:** Im Auslaufen seit 2026-06-16. Cookie-Auth (`xbuddy_session`)
> aus `specs/platform/auth.md` AUTH-2 ist neuer Standard; `tma`-Header bleibt
> **additiv akzeptiert** (Mini-Apps brechen nicht), wird aber pro Power-Flow-
> Migration zurückgebaut. Endgültige Ablösung in Phase 6 (RAT-18,
> AUTH-6 leer). [Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion
> „Nic-Verdikte 2026-06-16" → übergeordnete Setzung „MAD-7 obsolet"]

**Telegram fügt `initData` NICHT automatisch in die URL ein** — sie steht nur
als `window.Telegram.WebApp.initData` (JS-Property) bereit. Server-Routes
dürfen `initData` NICHT als Query-Param vom HTML-Render-Pfad erwarten.

**Übergangs-Default für bestehende Mini-Apps** (ratifiziert 2026-06-15 mit dem
2. Konsumenten, im Auslaufen seit RAT-18 2026-06-16):

- JS liest `window.Telegram.WebApp.initData` aus der Telegram-Property.
- JS sendet bei **jedem** API-Call den Header `Authorization: tma <initData>`.
- Server-seitig validiert eine zentrale Middleware (heute
  `eltern-chat/init_data.py`, HMAC-SHA256 gegen Bot-Token aus
  `EnvironmentFile` — Token-Heimat siehe `conventions/apps.md` APP-7) den
  Header. Antwort bei ungültigem Header: 401, kein Body.

**Pro Backend-Instanz ein Bot-Token** (Multi-Tenancy via Hardware-Trennung,
Nic-Setzung 2026-06-15): jede Familie hat eigene Pi-Hardware, eigenen Bot,
eigenen Bot-Token. Keine Familie-Auswahl-Logik in der Header-Validierung;
keine `familie_id`-Routing-Schicht in der URL.

**V1-Übergang (essen-einkauf, #653):** Die Mini-App essen-einkauf lief in V1
ohne Header-Auth, weil der Buddy auf `127.0.0.1` gebunden war und nginx
Same-Host-Routing über Tailscale-Funnel mit Per-Node-Cert die de-facto-Auth
übernahm. Diese V1-Vereinfachung war akzeptabel bis zum 2. Mini-App-
Konsumenten — **mit Familie 3 / mehreren Mini-Apps gleichzeitig wird sie
abgelöst**. Folge-Strecke #708: bestehende essen-einkauf-Routen werden auf
Header-Auth migriert.

**Start-Wege liefern beide `initData`:**

- **Inline-`web_app`-Button** im Chat — heutiger essen-einkauf-Pfad.
- **`t.me`-Direktlink** als Text-Footer (z. B. „kannst auch die ganze Liste
  in der App bearbeiten: https://t.me/<bot>/<app>") — Telegram-Doku Stand
  2026-04-03 bestätigt: Direktlink-Start setzt ebenfalls `initData`.

Beide Wege sind gleichberechtigte Launcher-Capabilities; die Auswahl steuert
MAD-10.

**Spec-Anker:** `specs/buddies/essen.md` ESSEN-31 („lädt nur auf gültige
Telegram-initData-Signatur") + `specs/platform/einkauf-zeigen.md` EZG-6 +
`specs/platform/routine-anpassen-oeffnen.md` RAO-6.

*Tickets:* #653 (V1-Vereinfachung), #708 (Header-Auth-Härtung), #728
(routine-anpassen, 2. Konsument als Ratifizierungs-Trigger)

---

### MAD-8 — VERSCHOBEN seit 2026-06-12

MAD-8 (Direkt-Modus für schmerzlose Schreib-Aufgaben) ist **kein UI-Bau-Pattern**,
sondern **Familien-Verhalten** und gehört damit in die Eltern-Chat-Spec, nicht
in eine UI-Convention. Per Beraterrunde-RATIFIZIERT-elternchat-ui-pattern
(2026-06-12) wandert die Regel in `specs/platform/eltern-chat.md` EC-10
(A2-Klausel: Sofort-Write + Quittung + Undo nur für One-Shot-Ressourcen mit
stabiler ID + idempotentem DELETE + Pre-Flight-Check).

Code-Mechanik (`auto_confirm = True` im `WriteTask`-Framework, siehe
`tasks.py`) bleibt; der **normative Anker** ist jetzt EC-10 statt MAD-8.

**Begründung:** `conventions/README.md` trennt Verhaltens-Regeln (Spec) von
UI-Bau-Patterns (Convention). Vorherige MAD-Inkarnation mischte beides; der
Genre-Drift wurde beim Antiberater-Codex-Pass aufgedeckt.

*Tickets:* Ratifizierung `decisions/RAT-47` (Punkt 5)

---

### MAD-9 — VERSCHOBEN seit 2026-06-15 nach `conventions/apps.md` APP-7

MAD-9 (Token-Sharing für Mini-App-Konsumenten) ist **Deployment-Mechanik**,
kein UI-Bau-Pattern. Die Heimat wurde mit #708 (2026-06-15) auf
`conventions/apps.md` APP-7 (Token-Sharing-EnvironmentFile-Klausel im
App-Installations-Mechanismus) festgelegt. MAD-7 referenziert APP-7 als
Token-Heimat; in dieser Konvention wird MAD-9 nicht mehr inhaltlich
ausgeführt.

*Tickets:* #684 (Token-Sharing), #708 (Verortung in apps.md APP-7),
Ratifizierung `decisions/RAT-47` (Punkt 5)

---

### MAD-10 — Launcher-Capability für Mini-App-Start

Eine Mini-App wird **nicht direkt** per `web_app`-Button oder `t.me`-Direktlink
in Skill-Code aufgerufen, sondern über einen **transportseitigen Launcher**:

```python
platform.openMiniApp(app_id, *, launcher_hint=None)
```

Der Launcher wählt je nach **Capability** des Transports zwischen:

- **Inline-`web_app`-Button** im Chat — wenn der Skill seine eigene Mini-App
  als primären Aufrufweg anbietet (heute essen-einkauf-Pfad).
- **`t.me`-Direktlink** als Text-Footer — wenn der Aufruf als
  Cross-Skill-Empfehlung kommt (siehe `specs/platform/eltern-chat.md`
  EC-34) oder wenn die Transport-Capability keine Inline-Buttons unterstützt.

**Beide Wege liefern `initData`** (siehe MAD-7); MAD-10 erzwingt keine
Bevorzugung, sondern macht die Wahl Capability-getrieben.

**Begründung:** Die Auth-Fähigkeit ist die Grenze, nicht der Aufrufweg.
RAT-16-Vendor-Adapter-Disziplin verlangt, dass Skills nicht direkt
`web_app` oder `t.me`-URLs konstruieren — sondern den Adapter rufen.
Zukünftige Nicht-Telegram-Adapter (Element-Widget, PWA) implementieren
dieselbe Launcher-Schnittstelle mit eigenen Capabilities.

*Tickets:* Ratifizierung `decisions/RAT-47`
(Punkt 4 — A4b); #708 (Server-`initData`-Validierung schließen)

---

## Anti-Pattern (was wir NICHT tun)

- Eigene Farb-Werte erfinden, statt DTOK-Tokens zu referenzieren.
- Hardcoded `px`/`rem` in Card-Klassen statt Skalierungs-Variable.
- `onerror`-Fallback-Bilder mit verschachteltem HTML-Escape (essen-einkauf
  2026-06-12-Bug).
- `localStorage`-Persistenz für Dirty-State.
- Direkter `window.Telegram.WebApp.*`-Zugriff in Mini-App-Code.
- Server-Route, die `initData` als Query-Param erwartet.
- Token-Duplikat in service-eigener `.env` (siehe `apps.md` APP-7).
- `familie_id`-Routing-Schicht in Mini-App-URLs (Multi-Tenancy via
  Hardware-Trennung, nicht Software-Mandantentrennung).

---

## Refs

- `conventions/design-tokens.md` (DTOK) — Display-Tokens, von Mini-Apps geerbt
- `conventions/apps.md` APP-7 — Token-Sharing-EnvironmentFile-Klausel (MAD-9-Heimat)
- `decisions/RAT-16-telegram-mvp-matrix-vertagt.md` — Plattform-Wahl,
  Vendor-Adapter-Disziplin als Pflicht
- `specs/buddies/essen.md` ESSEN-31 — erster Mini-App-Konsument
- `specs/platform/einkauf-zeigen.md` EZG-6 — `web_app`-Inline-Button, Auth-Anker
- `specs/platform/routine-anpassen-oeffnen.md` RAO-6 — Routine-Anpassen-Mini-App
- gh issue #653 (Combine-PR #688) — Bau-Erfahrung 1. Konsument
- gh issue #684 (Combine-PR #687) — Lego-Basis (platform.js, init_data,
  Funnel, Token-Sharing)
- gh issue #728 — routine-anpassen (2. Konsument, Ratifizierungs-Trigger)
- gh issue #708 — Mini-App-Auth-Header-Härtung

---

### MAD-11 — JS-Side-Auth-Probe (`ensureAuth`) für HTML-Render-Routen

**Live-Befund 2026-06-15 (#708-Folge):** Telegram-WebView sendet beim
HTML-Initial-Load **keinen** `Authorization`-Header. `initData` ist nur als
`window.Telegram.WebApp.initData` (JS-Property) verfügbar — Header-Auth-Check
auf der HTML-Render-Route ist Telegram-spezifisch nicht durchführbar.

**Bindendes Pattern (ratifiziert mit n=4 Konsumenten — essen, routine,
hoerspiel, mini-app-uebersicht):**

1. **HTML-Render-Route ist public** — lädt das Mini-App-Skeleton ohne
   Authorization-Header (kein Daten-Leak, nur leeres Gerüst).
2. **JS macht beim Mount** `await platform.ensureAuth()`:
   - Sendet `POST /api/v1/init-data/validate` mit
     `Authorization: tma <initData>`-Header.
   - Bei 200 (`{user_id, family_member: true}`): JS lädt Daten via API.
   - Bei 401/403 oder Netzfehler: JS sperrt das DOM mit Klartext-Hinweis
     („Bitte über den Familien-Bot öffnen.").
3. **API-Routen aller Buddies** (`/api/v1/<buddy>/*`) bleiben hart
   auth-geschützt (`require_init_data`-Decorator, MAD-7) — Daten-Schutz
   lebt auf der API, nicht auf dem HTML-Render.

**Wohnort:** Helper `ensureAuth(opts)` in `seiten/static/platform.js`
(Lego-Brille: bestehender Platform-Wrapper als Single-Source-of-Truth für
Telegram-Web-API-Calls). Validate-Endpoint in `seiten/main.py`
(`/api/v1/init-data/validate`, POST) als zentrale Naht.

**Begründung der Architektur-Spaltung:** HTML-Render-Auth ist Telegram-spec'd
nicht durchführbar; API-Auth bleibt scharf. Skeleton-only-HTML ist kein
Sicherheits-Regress, weil keine Daten im HTML — alle Daten kommen via
authentifizierte API-Calls.

**Berater-Runden-Lehre für künftige Plattform-Specs:** Realitäts-Check der
Client-/Browser-Mechanik gegen das ratifizierte Auth-Pattern ist Pflicht-
Linse — nicht nur Backend-Architektur (HMAC, Header-Schema). Track-C-Subagent
hatte MAD-7 wörtlich umgesetzt, die Telegram-WebView-Realität schlug live
durch.

*Tickets:* #708 (Auth-Härtung), #896 (V2-Fix mit MAD-11-Ratifizierung)
