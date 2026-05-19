# Ticket-Workflow

Wie in diesem Repo Features und Bugs erfasst, bearbeitet und dokumentiert
werden. Bewusst schlank gehalten — Solo-Arbeit, ein Repo.

## Wo was lebt

| Achse | Wo | Werte |
|---|---|---|
| Lebenszyklus | Issue-State | `open` / `closed` |
| Workflow-Position | Projects-Board, Feld **Status** | Todo · In Progress · In Review · Done |
| Art | Label `type:*` | `feature`, `bug`, `chore`, `docs` |
| Ökosystem-Baustein | Label `area:*` | `display`, `controller`, `hub`, `buddy`, `infra` |
| Priorität | Label `priority:*` | `high`, `medium`, `low` |
| Blockiert | Label `blocked` | wartet auf etwas anderes |

Faustregel: **Labels = Eigenschaften** (mehrere gleichzeitig, ändern sich
selten). **Status-Feld = Position im Fluss** (genau einer, ändert sich
ständig). Status wird *nicht* über Labels geführt.

## Lebenslauf eines Tickets

```
Idee → Issue anlegen (Template) → Status: Todo
   → Branch → Commits → Status: In Progress
      → PR offen → Status: In Review
         → PR gemerged → Issue schließt sich → Status: Done
```

Status-Sonderfälle: `blocked`-Label setzen, wenn etwas wartet;
beim Schließen ohne Umsetzung `not planned` als Grund wählen.

## Ein Ticket anlegen

Über **New issue** → Vorlage *Feature* oder *Bug* wählen. Das Feature-Template
verlangt Beschreibung, North-Star-Bezug und **Akzeptanzkriterien** — ein
Ticket ohne Akzeptanzkriterien ist nicht fertig beschrieben.

Nach dem Anlegen: `area:`- und `priority:`-Label setzen, Ticket aufs
Projects-Board ziehen.

## Branch, Commit, PR

Die Ticket-Nummer ist der rote Faden:

- **Branch:** `feature/<nr>-kurzbeschreibung` bzw. `fix/<nr>-…`
- **Commit:** Bezug im Text, z. B. `Kalender-Buddy: Wochenansicht (#12)`
- **PR:** Beschreibung verlinkt das Issue mit `Closes #12` — dann schließt
  sich das Issue beim Merge automatisch.

## Definition of Done

Ein Issue ist erst `Done`, wenn:

- [ ] alle Akzeptanzkriterien erfüllt sind
- [ ] der Code im Default-Branch gemerged ist
- [ ] das Feature gegen das North-Star-Prinzip geprüft ist
      (verschiebt es eine Aufgabe vom Elternteil zum Kind?)
