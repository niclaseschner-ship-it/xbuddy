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

| Achse | Wo | Werte |
|---|---|---|
| Soll-Verhalten | `specs/` | Anforderungen mit IDs (`DISP-1` …) |
| Lebenszyklus | Issue-State | `open` / `closed` |
| Workflow-Position | Projects-Board, Feld **Status** | Todo · Spec · In Progress · In Review · Done |
| Art | Label `type:*` | `feature`, `bug`, `chore`, `docs` |
| Ökosystem-Baustein | Label `area:*` | `display`, `controller`, `hub`, `buddy`, `infra` |
| Priorität | Label `priority:*` | `high`, `medium`, `low` |
| Blockiert | Label `blocked` | wartet auf etwas anderes |

Faustregel: **Labels = Eigenschaften** (ändern sich selten), **Status-Feld =
Position im Fluss** (ändert sich ständig). Status läuft nicht über Labels.

## Lebenslauf eines Tickets

```
Todo         Ticket angelegt (Template): grobe Idee + North-Star-Bezug
  │
Spec         betroffene Komponenten-Spec öffnen, Anforderung(en) als
  │          Requirement-IDs formulieren/ändern, als kleinen PR reviewen
  │          ──── Checkpoint: kein Code, bevor das durch ist ────
In Progress  Branch + Implementierung gegen genau diese IDs
  │
In Review    PR offen, verlinkt das Issue mit "Closes #nr"
  │
Done         gemerged; Requirement-IDs in der Spec mit Ticket-# annotiert
```

`blocked`-Label setzen, wenn etwas wartet. Schließen ohne Umsetzung →
Grund `not planned`.

## Ein Ticket anlegen

**New issue** → Vorlage *Feature* oder *Bug*. Das Feature-Template fragt nach
der betroffenen Spec-Datei und den Requirement-IDs. Nach dem Anlegen:
`area:`- und `priority:`-Label setzen, aufs **XBuddy**-Board ziehen (Status
*Todo*).

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
