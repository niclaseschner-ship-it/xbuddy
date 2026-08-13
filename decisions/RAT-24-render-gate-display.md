# RAT-24 — Deterministisches Render-/Layout-Gate für Display-Views

> ## ⛔ ZURÜCKGEZOGEN am 2026-08-13 durch [RAT-37](RAT-37-rat-24-render-gate-rueckzug.md)
>
> Dieser Entscheid gilt **nicht mehr**. Das Render-Gate ist beerdigt, nicht
> repariert: 48 Tage nie verdrahtet, dann sechs Tage nach der Verdrahtung erneut
> blind (Auth-Rück-Verriegelung, 3/3 Pilot-Ansichten 401). Gemessene Nutzung
> **0 von 97** Kommentaren. Der Screenshot-Self-Check über die Origin bleibt
> unberührt — er ist älter als RAT-24 und war nie Teil davon.
>
> Der Text unten bleibt als Geschichte stehen. **Nicht als geltende Regel lesen.**

- **Entschieden:** 2026-06-26 (Berater-Runde „Deterministisch-hartes Layout-Gate
  für Display-Views", Berater + Codex-Antiberater, eine Runde mit READY-FOR-PROPOSE-
  Vorstufe + Antiberater-Pass), **ratifiziert** 2026-06-26 (Nic, drei Stempel:
  Engine, Modus, #1112-Verhältnis).
- **Betrifft:** net-neuer Test-/Automations-Harness im xbuddy-Repo (eigenes
  Tool-Verzeichnis, z. B. `tools/render-gate/`, mit tool-lokalem `package.json`);
  Andockpunkt `~/.claude/commands/arbeitstag.md` (Prozess-Artefakt **außerhalb**
  des Repos); `decisions/INDEX.md`. **Keine Convention** (n=1; Tier-B-Hochzug erst
  beim 2. Buddy mit Kollisionsvertrag). Bau-Ticket #1160 (Keystone). Supersedes
  `xbuddy-prozess#40` (NOT_PLANNED). Komplement: #1112 (statischer
  CSS↔Python-Konstanten-Lint). Außerhalb Scope: #1146 (Klasse #4).
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/2026-06-26-1805-RATIFIZIERT-render-gate-display.md`
  → Vorschlag `20260626-175619-vorschlag-render-gate-display.md`,
  Antiberater (Codex) `2026-06-26-1801-antiberater-render-gate-display.md`.

## Beschluss

Display-Views bekommen ein deterministisch-hartes, mechanisches Render-/Layout-Gate,
das **auf dem Pi gegen die Live-Origin** läuft und den subjektiven Augen-Check ablöst.
Form:

- **Engine:** `puppeteer-core` auf System-Chromium (`/usr/bin/chromium`),
  tool-lokales `package.json`+Lockfile, kein Browser-Download. Tiebreaker
  **Einfachheit** (Constitution-Qualitätsattribut Nr. 2 — *nicht* Offline Nr. 4,
  die ist Laufzeit-Eigenschaft des familien-sichtbaren XBuddy, nicht des Dev-Harness).
- **Tier-A** (datenunabhängig, jede View, null-config): Konsolen-/Seiten-Fehler,
  fehlgeschlagene Asset-Requests/404, Broken-Img, Element-aus-Viewport/Overflow-Clip,
  Null-Größe-Elemente *sichtbarkeits-gefiltert*, Text-Ellipsis-Clipping.
- **Tier-B** (optional, pro View): EIN Kollisionsvertrag (Selektor-Paare) für die
  Pilot-View. Das Gate darf View-Geometrie-Konstanten (z. B. plans `GEOMETRIE_*`)
  **nie hartcodieren** (= Einbacken, Ein-Wege-Tür, explizit vermieden).
- **Default-Wait** vor jeder Messung: `document.fonts.ready` + Network-Idle + zwei
  stabile Rect-Snapshots (gegen Flakiness halb-hydrierter Frames).
- **Modus:** Bericht (nicht-blockierend) als `arbeitstag`-Validierungsphase, mit
  **Flip-zu-Block-Trigger** (≥1 echte Regression gefangen UND 0 Fehlblocks über ein
  Fenster). Kein Tag-1-Block (#40 starb an falscher Zuversicht).
- **Piloten:** `plan/woche` (server-Jinja) + `hoerspiel/*/alben` ODER `kibuddy/frage`
  (echter Client-Render — NICHT `wetter/heute`, das ist server-gerendert).
  ~~`woche-klein`-Variante explizit mitmessen.~~ *(Amendment 2026-07-03: `plan/woche-klein` per Render-Paritäts-Entscheid 2026-07-01 / #1235 entfernt; Mess-Auftrag entfällt.)*
- **KI-Vision-Schicht 2:** NOCH NICHT (Trigger: Gate live + ≥2 echte visuelle
  Regressionen, die nachweislich keine deterministische Invariante sind). Schicht 1
  bleibt deterministisch-unverhandelbar.

## Reversibilität & Kill-Kriterien

Zwei-Wege-Tür, mittlerer Blast Radius (Bericht-Modus folgenlos rückbaubar; das Tun
ist das Experiment). Rollout auf die restlichen ~7 Views erst, wenn der MVP gegen die
zwei Piloten besteht: Erstlauf erzeugt ≥1 Befundtyp oder dokumentiert „0 + View-Liste
+ Viewport"; **3 Läufe hintereinander identisch** (sonst kein Rollout); KIBuddy-`hidden`-
Startzustand ohne Fehlbefund; frischer Pi-Checkout `npm ci` + ein Headless-Aufruf ohne
Browser-Download.

## Abgrenzung

Bewusst NICHT in Scope: Pixel-Visual-Regression/Golden-PNG, programmatischer
WCAG-Kontrast (MVP), net-neuer blockierender CI-Workflow (erst nach Flip-Trigger),
zentrales Invarianten-Manifest (erst n=2), #4/#5/#6 (Termin-Vollständigkeit /
A-B-Konsistenz / Mechanik-Toggle). Heute existiert KEIN echtes Render-Testing (nur
Pure-Logik + DOM-Stub ohne CSS-Engine + manuell) und KEIN CI-Test-Gate — das Gate ist
neue Infrastruktur.
