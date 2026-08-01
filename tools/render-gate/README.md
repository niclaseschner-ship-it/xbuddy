# render-gate — Deterministisches Render-/Layout-Gate (RAT-24, #1160)

Berichtender `puppeteer-core`-Harness, der **auf dem Pi** System-Chromium headless
gegen die **nginx-Live-Origin** (`:8443`, self-signed) faehrt, **Tier-A-Invarianten**
(datenunabhaengig) plus optionale **Tier-B-Kollisionsvertraege** prueft und einen
**deterministischen Bericht** ausgibt.

**Modus: Bericht, nicht blockierend.** Exit-Code ist im MVP **immer 0** — auch bei
Befunden. Der Report ist das Produkt. Der Flip-zu-Block kommt erst nach dem
RAT-24-Fenster-Trigger (≥1 echte Regression gefangen UND 0 Fehlblocks). Einzige
Nicht-0-Exits sind Harness-Bedienfehler (unbekannte View → 2; Chromium startet
nicht → 3; unerwarteter Fehler → 1).

Quelle: `decisions/RAT-24-render-gate-display.md`. Keine Spec (Tooling-Genre),
keine Convention (n=1; Tier-B-Hochzug erst beim 2. Buddy mit Kollisionsvertrag).

## Voraussetzungen

- System-Chromium unter `/usr/bin/chromium` (getestet: Chromium 147).
- Node ≥ 20 (getestet: v20.20.2).
- Die Live-Origin muss erreichbar sein. Annahme: `https://192.168.0.78:8443`
  (lokale Pi-IP, NIE `buddyboard.local`/`localhost`). Self-signed-Cert wird via
  `acceptInsecureCerts` akzeptiert.

## Installation (offline-reproduzierbar)

```bash
cd tools/render-gate
npm ci          # zieht nur puppeteer-core (~54 MB JS), KEINEN Browser-Download
```

`puppeteer-core` (NICHT `puppeteer`) laedt bewusst **keinen** Browser herunter —
wir fahren das bereits installierte System-Chromium. Ein evtl. vorhandenes
`~/.cache/puppeteer` stammt aus unabhaengiger Arbeit und wird **nicht** benutzt.

## Aufruf

```bash
node check.js plan/woche          # eine View
node check.js plan/woche-klein
node check.js kibuddy/frage
node check.js --all               # alle Views aus views.json
node check.js plan/woche --json   # nur JSON (z. B. fuer 3-Laeufe-Diff)

npm run check -- plan/woche       # via npm-Script
npm run check:all
```

Ausgabe: menschenlesbare Zusammenfassung **plus** ein deterministischer
JSON-Block (mit `--json` nur JSON). Pro View entweder ≥1 Befund
(`[typ] selektor · detail · messwert`) oder explizit
`0 Befunde — view: <key>, viewport: 1920x1080, url: <origin>`. Die Befundliste
ist **dedupliziert und stabil sortiert** (keine Timestamps, keine Timing-Werte),
damit drei Laeufe identische Reports liefern.

## Tier-A-Invarianten (datenunabhaengig, jede View)

| Typ | Befund |
|-----|--------|
| `konsolen-fehler` | jede `console.error` |
| `seiten-fehler` | uncaught exception/rejection (`pageerror`) |
| `request-fehler` | fehlgeschlagene Requests (`requestfailed`) + Responses mit Status ≥ 400 (Assets/API/Fonts) |
| `broken-img` | sichtbares `<img>` mit `naturalWidth === 0` |
| `viewport-overflow` | sichtbares Element ragt rechts/unten ueber den Viewport |
| `root-overflow` | `scrollWidth/Height > clientWidth/Height` an `html`/`body` |
| `null-groesse` | sichtbares Content-Element (`<img>` ODER Text-Blatt) mit Breite **oder** Hoehe 0 |
| `text-clipping` | Text-Blatt mit `text-overflow:ellipsis`/`overflow:hidden` und `scrollWidth > clientWidth` |

Zusatz-Typen: `navigation-fehler` (View nicht erreichbar), `wait-instabil`
(Frame wurde im Zeitfenster nie stabil).

**Sichtbarkeits-Filter (Pflicht, RAT-24):** `[hidden]`, `display:none`,
`visibility:hidden/collapse`, `<script>`, `<template>`, `<style>`/Head-Tags und
SVG-`<defs>` (samt Nachfahren) zaehlen als legitim unsichtbar und erzeugen
**keinen** Befund. KIBuddys `hidden`-Startzustaende (`mikro-fehler`,
`cancel-hinweis`, `stopp-row`) fallen damit korrekt heraus.

**Default-Wait vor jeder Messung** (gegen Flakiness halb-hydrierter Frames):
`document.fonts.ready` + Network-Idle (`waitForNetworkIdle`) + **zwei stabile
Rect-Snapshots** (alle Bounding-Boxen werden zweimal mit kurzem Abstand gemessen;
erst bei Identitaet gilt der Frame als fertig).

### Bewusst ausgeschlossene Nicht-Befunde

- **`/favicon.ico` 404:** Chromium fragt das Favicon selbsttaetig an, auch wenn die
  View kein `<link rel="icon">` deklariert. Diese Anfrage feuert asynchron **nach**
  dem load-Event; ihr Eintreffen vor dem Schliessen der Seite ist zeitlich nicht
  deterministisch. Kein View-Asset → ausgeschlossen (`isBrowserAutoRequest` in
  `invariants.js`). Echte 404 auf von der View **deklarierte** Assets bleiben.
- **Generische `Failed to load resource`-`console.error`:** Chromium echo't jeden
  Subresource-Fehler zusaetzlich auf die Konsole — ohne URL. Das ist ein Duplikat
  des Netzwerk-Fehlers, den die `response`/`requestfailed`-Handler bereits **mit**
  URL fassen. Wird darum nicht doppelt gezaehlt. Echte JS-`console.error`-Aufrufe
  der Seite (eigener Text) bleiben Befunde.

### Bekannte/erwartete Befunde (kein Harness-Bug)

- **`text-clipping` auf `.pill-label`** in `plan/woche`: die Termin-Pillen kuerzen
  lange Labels **per Design** mit Ellipsis. Diese Befunde sind daten-abhaengig
  (Termin-Texte). Eine Per-View-Allowlist fuer bewusst-ellipsierte Selektoren ist
  ein Folge-Thema (nicht im MVP-Scope).

## Tier-B-Kollisionsvertrag (optional, pro View)

Eine View kann in `views.json` einen `contract` referenzieren (siehe
`contracts/plan-woche.json`). Ein Vertrag listet **Selektor-Paare**, deren
gerenderte Bounding-Boxen sich **nicht ueberlappen** duerfen. Verletzung →
`kollision-vertrag`-Befund. Fehlt ein Selektor im DOM, ist auch das ein Befund
(`selektor_fehlt`) — der Vertrag bezieht sich dann auf nicht (mehr) vorhandenes
Markup.

**Wichtig (RAT-24):** Vertraege beschreiben nur Nachbarschafts-Invarianten
(„A und B ueberlappen nicht"). Sie duerfen **niemals** View-Geometrie-Konstanten
(z. B. plans `GEOMETRIE_*`) hartcodieren — das waere ein Einbacken / eine
Ein-Wege-Tuer.

### Einen Tier-B-Vertrag pro View ergaenzen

1. Lege `contracts/<view>.json` an:
   ```json
   {
     "view": "<key>",
     "toleranz_px": 1.0,
     "paare": [
       { "a": ".selektor-a", "b": ".selektor-b", "note": "warum sie sich nicht beruehren duerfen" }
     ]
   }
   ```
   Jeder Selektor muss auf **genau ein** sichtbares Element zeigen (das Gate nimmt
   den ersten `querySelector`-Treffer). Selektoren aus dem **echten** gerenderten
   DOM ableiten, nicht aus Annahmen.
2. Trage in `views.json` unter der View `"contract": "contracts/<view>.json"` ein.
3. Probelauf: `node check.js <view>` — erscheint `selektor_fehlt`, passt der
   Selektor nicht aufs Markup.

## Dateien

- `check.js` — Entry-Point (CLI, Browser-Start, Default-Wait, Report).
- `invariants.js` — Tier-A-Checks (Browser-Kontext + puppeteer-Events) und
  Tier-B-Kollisionspruefung.
- `views.json` — Pilot-Registry (Origin, Viewport, View-URLs, Vertrags-Bezug).
- `contracts/plan-woche.json` — Tier-B-Pilot-Vertrag.
