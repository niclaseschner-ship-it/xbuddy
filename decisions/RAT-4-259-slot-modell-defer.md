# RAT-4 — Plan-Buddy Slot-Modell familien-spezifisch: jetzt NICHT bauen (defer bis Familie-3-Trigger)

- **Entschieden:** 2026-06-02 (Berater-Verdikt, Slot-Modell-Runde),
  **ratifiziert** 2026-06-05 (Nic, „parken" beim `/arbeitstag-prep`).
- **Betrifft:** `plan/config.py`, `plan/render.py`, `plan/main.py`,
  `plan/templates/plan_kinder.html`; `specs/buddies/plan.md` (PLAN-7, E-PLAN-8,
  PLAN-30). Parkt **#259**.
- **Transkript (Evidenz):** `brainstorm/berater-runde/2026-06-02-2234-antiberater-259-slot-modell.md`
  → Vorschlag `20260602-222544-vorschlag-259-slot-modell.md`.

## Beschluss

Das familien-spezifische Slot-Modell (per-Slot-`cycle`-Filter, Kinder + beliebige
Petrantwortlichkeiten statt „nur Erwachsene") wird **jetzt nicht gebaut**. Ein
`cycle`-Feld ist **keine** bloße Präzisierung von E-PLAN-2, sondern verschiebt
**E-PLAN-8** (`specs/buddies/plan.md:609-642`): Familienroutinen bleiben Code,
Familie 2–4 per Repo-Fork, Generalisierung **erst bei belegten Triggern**. PLAN-7
(`plan.md:96-101`, „Nur Erwachsene im Cycle") bleibt unverändert.

## Warum

- **Kein belegter Familie-3-Trigger:** Solange Familie 3 hypothetisch ist, wäre
  `cycle` ein generalisiertes Familienroutinen-Regime ohne erfüllten E-PLAN-8-Trigger
  — Vorratsarchitektur (CLAUDE.md §6 „Lege nichts auf Vorrat an").
- **Blast-Radius > behauptet:** nicht „ein Feld + vier Stellen", sondern Slot-Modell/
  Parser/Defaults/Render/Template-JS/GET+PUT-API/DB-Migration/Contract-Tests — mit
  echten Bruchstellen (alte `plan.db`-Zuweisungen außerhalb des neuen Filters; PLAN-30
  als „Erwachsenen-Slot"-Vertrag würde still umgedeutet).

## Re-Litigation / Reopen nur bei erfülltem Trigger

Neu aufmachen nur, wenn **eines** belegt ist:
(a) ein **echter Familie-3-Fork**, bei dem >3 wiederkehrende Code-Stellen für
Kinder-/Misch-Zuweisung geändert werden müssen (E-PLAN-8-Trigger, `plan.md:627-632`),
**oder** (b) Nic zieht **E-PLAN-8 bewusst neu**. Dann gehört zur Lösung: PLAN-30 als
„assignment slots"-Contract-Test neu formuliert (+ Kind-Slot-Test) und `cycle`-Validierung
konsistent in Defaults, PUT, GET, UI-Cycle **und** DB-Altzeilen. Sonst: schließen mit
Verweis auf RAT-4.
