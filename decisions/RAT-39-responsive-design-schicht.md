# RAT-39 — Aspekt-echte responsive Design-Schicht: Reflow löst den Uniform-Scale ab

**Status:** RATIFIZIERT 2026-07-30 (Nic: „a — ablösen, rollback geht ja immer,
probieren")
**Betrifft:** `specs/platform/heim-shell.md` (SHELL-8, SHELL-12), die Buddy-Views
(CSS), `display/_shared/design/tokens.css`
**Bezug:** RAT-35 Faden ② (Auflösung responsiv), #1218 (ratifizierte Richtung
„breit responsiv"), RAT-31/RAT-29 (Shell-Welt)
**Ticket:** #1594 (Epic) · Bezug #1595 (Uniform-Scale), #1541, #1574
**Entscheid-File:**
`brainstorm/berater-runde/20260730-1700-RATIFIZIERT-responsive-design-schicht.md`

## Problem

Die Familien-Oberfläche war auf 1920 gebaut und wurde auf kleineren Geräten
**uniform herunterskaliert** (`--shell-scale = innerWidth/1920`, `.shell-fit`
`transform: scale()`). Das bricht nichts — aber es schrumpft Text und Touch-Ziele
mit, statt das Layout umzubrechen. Ein Tablet bekommt damit kein tablet-taugliches
Layout, sondern ein verkleinertes Kiosk-Layout.

Die Bestandsaufnahme fand zusätzlich eine Ehrlichkeits-Lücke: der Render-Vertrag in
der Spec sagte „Render auf 1920×1200" (SHELL-8), während der real gebaute
Device-Fit-Scale nur als Code-Kommentar existierte und in keiner Spec stand.

## Betrachtete Alternativen

- **Uniform-Scale behalten und nur nachjustieren.** Verworfen von Nic („ablösen") —
  Skalieren ist kein Reflow; die Ursache bleibt das pro View eingebackene
  Layout-Fixum.
- **Zentrale Layout-Tokens statt per-View-Arbeit.** Vom Befund entkräftet: das
  Fixum sitzt **pro View**, nicht zentral (`tokens.css` war zu dem Zeitpunkt schon
  `--kiosk-w`-frei, der Token hatte null Konsumenten).
- **Big-Bang über alle Views.** Verworfen zugunsten einer Tracer-Reihenfolge, damit
  eine brechende View einzeln zurückgerollt werden kann.

## Wie entschieden

Geerdet an einer Bestandskarte statt an einer Vermutung. Sie ergab drei Dinge, die
die Entscheidung tragen:

1. **Container-Queries sind keine grüne Wiese** — zwei gebaute Referenzen existierten
   bereits (`routine/static/routine.css:134-299`, `controller/app-panel/style.css:94`),
   inklusive verifizierter Browser-Unterstützung auf dem Pi. Die Design-Schicht war
   damit ein *Ausrollen* eines belegten Musters, kein Experiment.
2. **Die Per-View-Reife war stark uneinheitlich** — photo/wetter/essen weitgehend
   fluid, routine fertig bis auf den Rahmen, während plan/kibuddy/hoerspiel feste
   Pixel-Fonts und null Container trugen. Das gab die Reihenfolge vor.
3. **Der Shell-Split war ohnehin schon fluid**; fix waren nur die Rail-Breite und die
   1920er `.shell-fit`-Fläche.

**Diese Runde wurde bewusst leicht gefahren: kein Antiberater, kein voller
R2-Pingpong.** Begründung im Protokoll: Zwei-Wege-Tür pro View (CSS, rollback
jederzeit) plus ein billiger Prüf-Pass pro migrierter View. Das ist eine bewusste
Verdünnung der Methode und hier als solche vermerkt, nicht kaschiert.

## Ergebnis

- **Echter Reflow ersetzt den Uniform-Scale.** Container-Query-Design-Schicht pro
  View nach dem Vorbild der zwei gebauten Referenzen, token-getriebenes Sizing.
  Rail und `.shell-fit`-Fläche werden fluid.
- **Reihenfolge:** die noch-fixen Views zuerst als Tracer — kibuddy (am wenigsten
  migriert) als erster Bau, dann hoerspiel und das plan-Innenleben; routine nur noch
  der Rahmen-Deckel. Shell als eigener Schritt.
- **Render-Vertrag umgeschrieben:** SHELL-8 heißt heute *„Render ohne feste
  Zielauflösung"*; der Device-Fit-Scale ist als **SHELL-12** spezifiziert — explizit
  als Übergang, der ersatzlos entfällt, sobald alle Ansichten nach SHELL-8
  mitwachsen. Damit ist die Code-vs-Spec-Lücke geschlossen.
- **Formalisierung als Konvention** war vorgesehen (Container-Query-Design-Schicht
  als Muster) und ist **nicht geschehen** — es gibt bis heute keine
  Responsive-Convention in `conventions/`. Das Muster lebt in den gebauten Views.

**Stand der Ausführung:** der kibuddy-Tracer ist gebaut (`kibuddy/static/frage.css`,
`container-type: size` + `cq`-Einheiten, T1619).

## Woran wir merken würden, dass es falsch war

Das im Protokoll benannte Kill-Kriterium war *„RAT-24-Render-Gate pro migrierter
View; bricht eine View → diese View zurück, Rest bleibt"*.

**Dieses Netz existiert nicht mehr:** RAT-24 ist mit RAT-37 (2026-08-13)
zurückgezogen, das Render-Gate ist beerdigt. Die Entscheidung selbst ist davon
unberührt — betroffen ist nur ihr Prüfmittel. Was bleibt: die Migration ist pro View
eine Zwei-Wege-Tür, und der Rückfall ist die View einzeln zu reverten. Der Nachweis
„bricht nichts" ist seither subjektiver Augen-Check, wie RAT-37 es für das ganze
Projekt in Kauf nimmt.
