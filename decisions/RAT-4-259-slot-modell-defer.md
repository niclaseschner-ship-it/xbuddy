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
Verantwortlichkeiten statt „nur Erwachsene") wird **jetzt nicht gebaut**. Ein
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

## Auflösung 2026-06-22 — Trigger (b) eingelöst

Nic zog E-PLAN-8 bewusst neu, neues Argument: eine **Settings-Mini-App** für Slot-/Default-/Wochentag-Konfiguration ist absehbar nötig. Wenn das Slot-Modell **nach** der App parametrisiert wird, wandert die App-Implementierung mit — die Folgeinvestition macht das Aufschieben teurer als das Bauen.

**Substantielle Vereinfachung gegenüber 2026-06-02:** **Toggle-All statt Whitelist** — alle Personen aus `familie.json` togglebar, keine Slot-spezifische „wer darf hier stehen"-Whitelist. Das entschärft die 06-02-Komplexitäts-Knochen mechanisch (keine „unzulässig gewordenen Alt-Zuweisungen", keine Slot-Whitelist-Validierung, PLAN-30-Vertragstest vereinfacht zu „Person existiert in familie.json").

**Drei-Phasen-Schnitt:** P1 Slot-Modell + Layout + Icon-Migration + PLAN-24-Strip → P2 Eltern-Einstellungs-Seite (Wetter-RAT-2-Muster) → P3 Chat-Skill (geparkt, doppelt-bedingt auf Eltern-Chat-Anschluss + RAT-6-(A)-Trigger).

**RAT-4-Drei-Spec-Pflichten gelöst:**
- (a) Icon-Externalisierung — durch #445 (PLAN-28) erledigt; ARASAAC-Migration in P1 nachgezogen
- (b) Regel für unzulässig gewordene Alt-Zuweisungen — durch Toggle-All gegenstandslos
- (c) PLAN-30 als „Zuweisungs-Slots" — durch Toggle-All vereinfacht (Wertebereich `person_id` erweitert, API-Form stabil)

**Voller Entscheid:** `brainstorm/berater-runde/20260622-091210-RATIFIZIERT-plan-rearch.md`
**Ticket-Verankerung:** #259 (Comment 2026-06-22)
**Status RAT-4:** **AUFGELÖST** durch Berater-Runde 2026-06-22 + P1-Lieferung.
