# Ticket-Workflow

Wie in diesem Repo Features und Bugs erfasst, bearbeitet und dokumentiert
werden. XBuddy arbeitet **spec-driven**: die `specs/` sind die Quelle der
Wahrheit, ein Ticket ist ein Inkrement dagegen.

## Grundprinzip

`specs/` beschreibt, wie XBuddy sich verhalten *soll* — lebende Specs mit
Anforderungen, die stabile IDs tragen (`DISP-1`, `CAL-3` …). Ein Ticket
bringt eine Handvoll dieser Anforderungen in den Code.

**Kein Code, bevor die Anforderung als Requirement-ID in der Spec steht und
reviewt ist.** Spec und Code wandern zusammen — so driftet die Spec nicht
von der Realität weg. Details zum Spec-Modell: `specs/README.md`.

## Wo was lebt

GitHub Issues sind die Datenbank — alles läuft über Labels, voll API-steuerbar.
Kein Project-Board nötig.

| Achse | Wo | Werte |
|---|---|---|
| Soll-Verhalten | `specs/` | Anforderungen mit IDs (`DISP-1` …) |
| Lebenszyklus | Issue-State | `open` / `closed` (closed ≙ Done) |
| Workflow-Position | Label `status:*` | `spec`, `ready`, `in-progress`, `in-review` |
| Art | Label `type:*` | `feature`, `bug`, `chore`, `docs` |
| Ökosystem-Baustein | Label `area:*` | `display`, `controller`, `hub`, `buddy`, `infra` |
| Priorität | Label `priority:*` | `high`, `medium`, `low` |
| Blockiert | Label `blocked` | wartet auf etwas anderes |

Faustregel: **alle Eigenschaften und die Workflow-Position sind Labels**.
Eine Eigenschaft pro Achse — kein Issue trägt zwei `status:*` gleichzeitig.

## Lebenslauf eines Tickets

```
status:spec        Ticket angelegt; Spec-PR offen oder ausstehend
  │                ──── Checkpoint: kein Code, bevor Spec gemerged ist ────
status:ready       Spec reviewt und gemerged; Implementation darf starten
  │                (einziger MANUELLER Übergang — das Handoff-Signal)
status:in-progress Implementierungs-PR offen (Closes #nr)
  │                automatisch gesetzt durch ticket-status-flow Action
status:in-review   PR markiert ready-for-review
  │                automatisch gesetzt durch ticket-status-flow Action
closed             PR gemerged → Issue auto-closed durch "Closes #nr"
```

Bei Ticket-Erstellung wird `status:spec` automatisch durch die
`ticket-defaults`-Action gesetzt. `blocked`-Label setzen, wenn etwas wartet.
Schließen ohne Umsetzung → Grund `not planned`.

## Ein Ticket anlegen

**New issue** → Vorlage *Feature* oder *Bug*. Das Feature-Template fragt nach
der betroffenen Spec-Datei und den Requirement-IDs. Nach dem Anlegen:
`area:`- und `priority:`-Label setzen. `status:spec` wird automatisch
vergeben.

## Handoff an Implementierer

Sobald der Spec-PR gemerged ist, setzt der Spec-Autor (oder Reviewer) das
Label um:

```bash
gh issue edit <nr> --remove-label "status:spec" --add-label "status:ready"
```

Das ist der **einzige manuelle Status-Übergang**. Implementierer finden
übernehmbare Tickets via:

```bash
gh issue list --label "status:ready" --state open
```

Sobald sie einen Impl-PR mit `Closes #<nr>` öffnen, übernimmt die
`ticket-status-flow`-Action den Rest automatisch.

## Branch, Commit, PR

Die Ticket-Nummer ist der rote Faden:

- **Branch:** `feature/<nr>-kurzbeschreibung` bzw. `fix/<nr>-…`
- **Commit:** Bezug im Text, z. B. `Kalender: Wochenansicht CAL-3 (#12)`
- **PR:** Beschreibung verlinkt das Issue mit `Closes #12` — das Issue
  schließt sich beim Merge automatisch.
- Spec-Änderung und Implementierung dürfen getrennte PRs sein — die Spec
  zuerst.

## Definition of Done

Ein Issue ist erst `Done`, wenn:

- [ ] alle im Ticket genannten Requirement-IDs in der Spec stehen und erfüllt sind
- [ ] diese IDs in der Spec mit der Ticket-`#` annotiert sind
- [ ] der Code im Default-Branch gemerged ist
- [ ] gegen die `constitution.md` geprüft (North Star, Qualitätsattribute)
