<!--
Reihenfolge laut WORKFLOW.md: erst Spec-PR (Refs #), dann Impl-PR (Closes #).
Nur Impl-PRs lösen die Status-Übergänge in der ticket-status-flow Action aus.
-->

## PR-Art

- [ ] **Spec-PR** — schärft `specs/`, schließt KEIN Issue. Referenz: `Refs #<nr>`
- [ ] **Implementierungs-PR** — setzt Requirement-IDs im Code um. Referenz: `Closes #<nr>`

## Bezug

<!-- Closes #<nr>  ODER  Refs #<nr> -->

## Spec & Requirements

- Betroffene Spec: `specs/...`
- Umgesetzte (Impl-PR) bzw. neue/geänderte (Spec-PR) Requirement-IDs:
  - `XXX-N` — Kurztitel
  -

## Definition of Done

- [ ] alle genannten Requirement-IDs stehen in der Spec und sind erfüllt
- [ ] diese IDs in der Spec mit Ticket-`#` annotiert
- [ ] Verhalten ändert sich → automatisierter Test mitgeliefert
- [ ] gegen `specs/constitution.md` geprüft (North Star, Qualitätsattribute)
- [ ] keine Doku-Duplikate erzeugt, keine Inhalte zwischen Dokumenten kopiert
- [ ] PR ist klein und fokussiert (ein Thema)

## Notizen
