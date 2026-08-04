# RAT-11 — Prep-Reife-Gate: vorläufige Specs (OPEN-*/Skizzen) sind nie `spec-gemergt`

- **Entschieden:** 2026-06-06 (Berater-Runde „Prep-Reife-Check stempelt
  Offene-Punkte/OPEN-*-Skizzen fälschlich als reif", Vorschlag + Antiberater/Codex,
  zwei Brech-Runden + Antiberater-Pass auf den Spec-Text), **ratifiziert**
  2026-06-06 (Nic — Baustein 1+2 „umsetzen", Baustein 3 „Text zeigen, dann Gate").
- **Anlass:** Belegfall #343 (Routine-Eltern-Chat-Schreib-Skill) lief fast als
  `status:ready` raus, obwohl die bindende Spec für das Deliverable nur als Skizze
  `OPEN-ROUTINE-B` unter `## Offene Punkte` existierte (routine.md:418). Drei
  Prep-Schichten hatten den Konflikt vorliegen und übersahen ihn (REIF-Grep,
  LEDGER, Orchestrator-Disziplin).
- **Betrifft:** `specs/README.md` („Bindend vs. vorläufig"), `decisions/README.md`
  (Blocker gehört NICHT in `decisions/`), Prozess-Tooling
  `~/.claude/agents/xbuddy-watchdog-prep.md` + `~/.claude/commands/arbeitstag-prep.md`
  (Overhead-Spur, kein Produkt-Code). Belegfall #343.
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/20260606-202804-ENTSCHEID-prep-spec-skizze-gate.md`
  → Vorschlag `20260606-202804-vorschlag-prep-spec-skizze-gate.md`,
  Antiberater `2026-06-06-2028-antiberater-prep-spec-skizze-gate.md`,
  Spec-Text-Pass `2026-06-06-2043-antiberater-prep-readmetext.md`.

## Beschluss

**Reife einer Requirement ist semantisch, nicht syntaktisch.** Eine zitierte
Spec-ID gilt nur dann als bindend-gemergt (`spec-gemergt`), wenn sie eine
**Definitionszeile** hat UND **nicht** in einem vorläufigen Abschnitt steht.
Vorläufig (= nie `spec-gemergt`) ist ein Punkt, der

1. unter `## Offene Punkte` steht, **oder**
2. unter einer Überschrift mit dem Wort `ENTWURF` steht, **oder**
3. eine `OPEN-*`-ID trägt (Namens-Konvention für skizzierte Schnittstelle).

Abschnittskontext schlägt das Präfix: ein `OPEN-*` unter einer ratifizierten
Überschrift trägt einen ratifizierten **Beschluss** (Provenienz), das bindende
Requirement entsteht aber erst nach Überführung in einen normalen Abschnitt — für
den Prep heißt das `needs-nic`, nicht automatisch baufertig. Im Zweifel **nie**
Richtung `spec-gemergt` raten.

Der **negative Filter** (Punkte 1–2, Heading-String-Match) ist mechanisch; die
Grenze „vollständiges Requirement vs. bloßer Beschluss" bei ratifizierten `OPEN-*`
bleibt Urteil (deshalb „Nic fragen"). Vollständiger Determinismus wäre nur über
ein Statusfeld pro Requirement + Altlasten-Migration zu haben — als Premature
Generalization für ein Familien-Projekt **verworfen** (Vokabular-Sweep belegte:
`## Offene Punkte` ×21, genau ein `ENTWURF`, Marker konsistent → Hybrid reicht).

**Veränderliche Ticket-Blocker leben als GitHub-Label `blocked`, nicht als
Nähe-Grep in `decisions/`.** Begründung: ein RAT, der mehrere Tickets gemeinsam
nennt (RAT-6 nennt #341/#343/#340, nur #343 „geblockt"), würde Mitgenannte falsch
blocken; `decisions/` ist für *durable* Beschlüsse, ein Blocker ist *veränderlich*
(nach Auflösung wäre der Satz stale). Der Prep-RECONCILE fragt Labels.

## Was sich konkret ändert

- `specs/README.md`: neuer Abschnitt „Bindend vs. vorläufig" (dieser PR).
- `xbuddy-watchdog-prep`: REIF prüft Definitionszeile + negativen Filter statt
  nacktem ID-Grep; RECONCILE liest `blocked`-Label + Inline-Erledigt-Marker;
  LEDGER warnt, wenn ein RAT das Ticket als „geblockt" führt; neues YAML-Feld
  `blocked`; Ableitungsregel um Blocker erweitert.
- `arbeitstag-prep`: Karten-Ehrlichkeit (SPEC-DIFF nur aus bindendem Requirement;
  Skizzen-Zitat = rote Karte), Blocker-Zeile, Stempel-Pfad-Schutz (kein Stempel
  bei `spec-fehlt` ohne gemergten Spec-PR; conditional Stempel = verifizieren-dann-
  berichten; kein neuer Scope beim Stempeln).

## Falsifikation

Widerlegt, sobald ein gebautes/bindendes Requirement existiert, das diese Regel
fälschlich als vorläufig (oder umgekehrt) einstuft. Geprüft: ICONS-1…6 (`##`-Reqs)
und ratifizierte OPEN-PAA-B…E waren die Gegenbeispiele des Antiberaters; die Regel
in dieser Fassung fängt beide. Sweep: jedes `ENTWURF` steht in einer Überschrift
(kein Datei-Level-Marker) → Heading-Filter ist gegen den IST-Bestand vollständig.
