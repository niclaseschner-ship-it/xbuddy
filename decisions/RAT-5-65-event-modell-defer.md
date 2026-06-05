# RAT-5 — Router generisches Event-Modell: jetzt NICHT speccen (defer bis echter 3. Controller)

- **Entschieden:** 2026-06-02 (Berater-Verdikt, Event-Modell-Runde),
  **ratifiziert** 2026-06-05 (Nic, „parken" beim `/arbeitstag-prep`).
- **Betrifft:** `router/main.py`; `specs/platform/router.md` (ROU-2, ROU-9, ROU-24,
  E-ROU-8, ROU-27/28-Entwurf), `specs/platform/app-panel.md` (E-PANEL-5). Parkt **#65**.
- **Transkript (Evidenz):** `brainstorm/berater-runde/2026-06-02-2228-antiberater-65-event-modell.md`
  → Vorschlag `20260602-222544-vorschlag-65-event-modell.md`.

## Beschluss

#65 schreibt **jetzt keine** generische Event-Modell-Spec (keine ratifizierten
ROU-27/ROU-28). Begründung doppelt:

1. **Der Routing-Kern ist bereits descriptor-agnostisch** — `lookup` matcht nur
   `source_id` + Feld-Gleichheit, ohne `figure_id`/`bucket` zu kennen
   (`router/main.py:54-68`); ROU-2 sagt dasselbe (`router.md:40-54`). Die zwei
   Apply-Pfade (Phone via ROU-9, Panel via ROU-24) sind per **E-ROU-8**
   (`router.md:739-770`) **bewusst** getrennt, kein E-ROU-1-Bruch. Es gibt also
   nichts „zu entkoppeln", solange kein dritter Controller einen dritten Pfad erzwingt.
2. **Figuren-Erkennung ist aktuell nicht Teil des MVP.** Der figuren-basierte
   Controller, von dessen Descriptor #65 generalisieren will, ist im aktuellen MVP
   nicht aktiv — die Generalisierung hat damit keinen Zugzwang.

## Warum nicht „kostet fast nichts, jetzt in die Spec"

CLAUDE.md §6 verbietet spekulative Specs „für später"; weitere Controller-Adapter
sind im Router ausdrücklich out-of-scope mit eigenem Ticket bei Bedarf
(`router.md:16-20`). ROU-27 mit `display_ids:[...]` würde zudem das **bewusst
verworfene** E-PANEL-5 („ein Panel = genau ein Display", Singular `display_id`,
`app-panel.md:517-530`) wieder aufreißen.

## Re-Litigation / Reopen nur bei erfülltem Trigger

Neu aufmachen erst, wenn ein **echter dritter Controller-Typ** andockt und beim
20-Minuten-Papier-Trace (`source_id` + Descriptor in `routing.json.entries` +
Adapter) **einen dritten `apply_*`-Pfad erzwingt**. Hält der dritte Controller ohne
neue Apply-Strategie, ist #65 widerlegt. Falls dann gespecct wird: ROU-27 muss
E-PANEL-5 (Display-Kardinalität pro Adapter) explizit schützen, und `type → Adapter`
braucht eine Event-Type-Namespace-Konvention. Sonst: schließen mit Verweis auf RAT-5.
