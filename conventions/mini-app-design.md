# Mini-App-Design — Konvention     (ID-Präfix: MAD)

> **Status: First Occurrence (essen-einkauf, T653 #688).** Diese Datei dokumentiert
> das Mini-App-Pattern aus dem ersten gebauten Konsument. Sie ist **noch nicht
> verbindlich** — die Verbindlichkeit entsteht beim **zweiten** Mini-App-Konsument
> (Lego-Probe: dann wird die Konvention ratifiziert oder verworfen, je nachdem,
> ob das Pattern trägt).
>
> Bis dahin: Subagenten, die eine neue Mini App bauen, **lesen** diese Datei als
> Vorlage und folgen dem Pattern bewusst — Abweichungen markieren und begründen,
> damit die Ratifizierung später ehrlich entscheidet.

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

### MAD-6 — Asset-Pfade: `/api/v1/seiten/static/<datei>` für JS/CSS,
       `/display/_shared/icons/arasaac/<id>.png` für Piktogramme

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

### MAD-7 — Authentifizierung: `initData` aus JS-Property, nicht aus URL-Query

**Telegram fügt `initData` NICHT automatisch in die URL ein** — sie steht nur
als `window.Telegram.WebApp.initData` (JS-Property) bereit. Server-Routes
dürfen `initData` NICHT als Query-Param vom HTML-Render-Pfad erwarten.

**Pattern (V1 + V1.x):**

- **V1 (essen-einkauf):** HTML-Route lädt **ohne Auth**. JS macht API-Calls
  ohne Auth. Schutz: Buddy auf `127.0.0.1` gebunden, nginx Same-Host-Routing
  über Tailscale-Funnel mit Per-Node-Cert. Akzeptabel solange jeder
  Konsumenten-Buddy 127.0.0.1-bound bleibt.
- **V1.x (geplant):** JS liest `window.Telegram.WebApp.initData`, sendet bei
  jedem API-Call als `Authorization: tma <initData>`-Header. Server validiert
  via `eltern-chat/init_data.py` (HMAC-SHA256, Bot-Token aus
  `EnvironmentFile`).

**Spec-Anker:** `specs/buddies/essen.md` ESSEN-31 sagt „lädt nur auf gültige
Telegram-initData-Signatur" — das ist V1.x-Ziel, V1 ist Vereinfachung mit
Folge-Ticket.

*Tickets:* #653 (V1-Vereinfachung), Folge-Ticket „Mini-App-Auth-Header" (offen)

---

### MAD-8 — Direkt-Modus für schmerzlose Schreib-Aufgaben (E-EIN-1-Lehre)

Wenn die Schreib-Wirkung **schmerzlos rückgängig** ist (z. B. Listen-Item per
Tap entfernbar), läuft die Bot-Aufgabe im **Direkt-Modus** (E-EIN-1), nicht im
EC-10-propose→confirm-Pattern. Im `WriteTask`-Framework via
`auto_confirm = True` (siehe `tasks.py`).

```python
class EinkaufHinzufuegenTask(WriteTask):
    auto_confirm = True   # E-EIN-1
```

**Gilt nicht** für Aufgaben mit Verlust-Risiko (Familie anlegen, Routine
ändern, Plan-Punkte setzen) — die behalten propose→confirm.

*Test-Implikation:* Bot-Antwort kommt direkt, kein „Vorschlag — soll ich das
tun?"-Bubble dazwischen.

*Tickets:* #653 (Live-Fix-Lehre)

---

### MAD-9 — Token-Sharing für Mini-App-Konsumenten

Konsumierende Buddys (heute: seiten-Service für Init-Data-Auth) lesen den
Telegram-Bot-Token **aus dem eltern-chat-Eigentum** via
`EnvironmentFile=__XBUDDY_DATA__/eltern-chat/.env` (#684 Token-Sharing,
deploy/systemd/README.md). **Niemals Token duplizieren** in service-eigene
`.env`-Dateien — Eigentum bleibt klar.

**ENV-Naming:** Wenn der konsumierende Service ein anderes ENV-Naming erwartet
als `ELTERNCHAT_BOT_TOKEN`, **Code-Anpassung am Konsumenten** (z. B.
`os.environ.get("TELEGRAM_BOT_TOKEN")` plus Fallback auf
`ELTERNCHAT_BOT_TOKEN`) statt Alias-Eintrag im .env. Letzteres ist
Pi-Drift-Risiko (Live-Fix 2026-06-12 hat das gezeigt).

*Tickets:* #684 (Token-Sharing), #653 (Konsumenten-Anpassung Folge-Ticket)

---

## Anti-Pattern (was wir NICHT tun)

- Eigene Farb-Werte erfinden, statt DTOK-Tokens zu referenzieren.
- Hardcoded `px`/`rem` in Card-Klassen statt Skalierungs-Variable.
- `onerror`-Fallback-Bilder mit verschachteltem HTML-Escape (essen-einkauf
  2026-06-12-Bug).
- `localStorage`-Persistenz für Dirty-State.
- Direkter `window.Telegram.WebApp.*`-Zugriff in Mini-App-Code.
- Server-Route, die `initData` als Query-Param erwartet.
- Token-Duplikat in service-eigener `.env`.

---

## Ratifizierungs-Trigger (Status-Übergang First Occurrence → Convention)

Diese Datei wird zur **ratifizierten Konvention**, wenn:

- Eine **zweite Mini App** gebaut wird (Lego-Probe Linse 5): zeigt sich, dass
  das Pattern trägt → ratifizieren (Status entfernen, MAD-IDs als verbindlich
  zitieren).
- Falls das Pattern **nicht trägt** (zweite Mini App braucht andere Form):
  Anti-Pattern aus dem ersten Lauf dokumentieren, MAD restrukturieren oder
  verwerfen.

Bis dahin: jeder neue Mini-App-Track liest diese Datei, übernimmt das Pattern
bewusst und meldet im Handoff, wo abgewichen wurde.

---

## Refs

- `conventions/design-tokens.md` (DTOK) — Display-Tokens, von Mini-Apps geerbt
- `decisions/RAT-16-telegram-mvp-matrix-vertagt.md` — Plattform-Wahl,
  Vendor-Adapter-Disziplin als Pflicht
- `specs/buddies/essen.md` ESSEN-31 — erster Mini-App-Konsument
- `specs/platform/einkauf-zeigen.md` EZG-6 — `web_app`-Inline-Button, Auth-Anker
- gh issue #653 (Combine-PR #688) — Bau-Erfahrung
- gh issue #684 (Combine-PR #687) — Lego-Basis (platform.js, init_data,
  Funnel, Token-Sharing)
