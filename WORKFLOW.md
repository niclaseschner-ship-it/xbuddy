# Ticket-Workflow

Wie in diesem Repo Features und Bugs erfasst, bearbeitet und dokumentiert
werden. XBuddy arbeitet **spec-driven**: die `specs/` sind die Quelle der
Wahrheit, ein Ticket ist ein Inkrement dagegen.

> **Anker statt Zeile (PW-23, 2026-06-09):** Wo Skills, Hooks oder Memories auf
> diese Datei verweisen, nutzen sie `WORKFLOW.md#<anchor-id>` statt
> `WORKFLOW.md:<zeile>`. Anker sind explizite `<a id="..."></a>`-Marker unter
> Headings — standard Markdown, per `grep` findbar. Wer verweist, setzt den Anker.

## Grundprinzip

`specs/` beschreibt, wie XBuddy sich verhalten *soll* — lebende Specs mit
Anforderungen, die stabile IDs tragen (`DISP-1`, `CAL-3` …). Ein Ticket
bringt eine Handvoll dieser Anforderungen in den Code.

`conventions/` ist das parallele Doku-Genre für **Bauregeln**, die mehrere
Komponenten gemeinsam tragen (`IDENT-1`, `SVC-1`, `LOG-4` …) — Genre seit
2026-05-26. Konvention beschreibt *wie etwas gebaut wird*, Spec *was eine
Komponente tut*. Konventions-Änderungen folgen demselben Spec-Halt-Reflex
wie Spec-Änderungen (siehe CLAUDE.md §7).

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
| Blockiert | Label `blocked` | wartet auf etwas anderes (siehe Blocker-Zeile) |

Faustregel: **alle Eigenschaften und die Workflow-Position sind Labels**.
Eine Eigenschaft pro Achse — kein Issue trägt zwei `status:*` gleichzeitig.

**Blocker-Zeile (PW-13).** Ein `blocked`-Ticket trägt im Body eine Zeile, die den
**aktuell nächsten** Blocker klassifiziert:

```
Blocker: <wer/was> — Auflösung: agent-prüfbar | nic
```

`agent-prüfbar` = der Agent kann die Auflösung selbst feststellen (PR/Issue gemergt,
Buddy-V1 live, Zähl-Trigger erreicht). `nic` = braucht eine Nic-Entscheidung/Freigabe/
externe Handlung. Das ist **Daten** (ändert sich der Blocker, ändert sich die Zeile),
kein zweites Label — die Achse beschreibt den nächsten Blocker, nicht eine permanente
Ticket-Eigenschaft. Ein eigenes `needs-nic`-**Label** ist bewusst **vertagt** (heute
leere Queue); Reopen-Trigger: häufige mid-build Architektur-Halts, die nie durch den
`/arbeitstag-prep` laufen und so nur per Board-Filter sichtbar wären.

## Lebenslauf eines Tickets
<a id="lifecycle"></a>

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
<a id="handoff"></a>

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

### Der Stempel ist die Membran
<a id="stempel-membran"></a>

`status:ready` trennt zwei Prozesse sauber:

- **`/arbeitstag-prep`** reift Tickets (`status:spec` → `status:ready`): Spec
  schärfen, Substanz prüfen, gegen frische Merges und das Ledger abgleichen,
  Nic entscheiden lassen, **dann** stempeln. Unreife Tickets sind sein Revier.
- **`/arbeitstag`** implementiert — und nimmt **ausschließlich `status:ready`**
  (`gh issue list --label "status:ready" --state open`). Es reift keine Tickets
  mehr selbst; was nicht gestempelt ist, gehört in den prep, nicht in den
  arbeitstag.

Damit der Stempel das tragen kann, muss er verlässlich sein:

- **Mensch/Reviewer setzt ihn** nach Verdikt — nicht automatisch aus einem
  Label-Reflex.
- Die **`prep-reconcile`-Action** validiert jeden `status:ready`-Stempel
  mechanisch: ein **geschlossenes** Issue darf ihn nie tragen (Arbeit erledigt
  oder verworfen) → die Action entfernt ihn wieder und kommentiert. Das fängt
  den häufigsten Fehler: einem längst gemergten Ticket versehentlich den Stempel
  zu geben.
- Inhaltliche Reife (genug Substanz? re-litigiert es eine schon ratifizierte
  Entscheidung?) bleibt Agent-Urteil (`watchdog-prep`) + Nic — das kann keine
  Action entscheiden.

Ratifizierte Architektur-/Design-Entscheidungen liegen in
[`decisions/`](decisions/INDEX.md) — dort prüft der prep, ob eine Frage schon
entschieden ist, bevor sie neu beraten wird.

## Branch, Commit, PR

Die Ticket-Nummer ist der rote Faden:

- **Branch:** `feature/<nr>-kurzbeschreibung` bzw. `fix/<nr>-…`
- **Commit:** Bezug im Text, z. B. `Kalender: Wochenansicht CAL-3 (#12)`
- **PR:** Beschreibung verlinkt das Issue mit `Closes #12` — das Issue
  schließt sich beim Merge automatisch.
- Spec-Änderung und Implementierung dürfen getrennte PRs sein — die Spec
  zuerst.

### `main` ist verriegelt (RAT-9/RAT-10, conventions/reconcile.md)

- **Direkter Push auf `main` ist physisch unmöglich** (GitHub-Ruleset). Code
  kommt **nur** über einen gemergten PR — auch Spec-, Doku- und Infra-Änderungen,
  auch die Werft. Kein lokaler `--ff-only`-Merge mehr.
- **Der Bot merget selbst** (0 Pflicht-Reviewer): PR auf **Auto-Merge** setzen
  (`gh pr merge <nr> --auto --merge --delete-branch`) → GitHub merget den Moment,
  in dem der required Check `closes-guard` grün ist. Kein manueller Merge-Schritt.
- **`closes-guard`** verlangt genau einen Ausgang: `Closes #` (Impl) ·
  `Refs #` (Spec) · Label `no-ticket` (bewusste, seltene ticketlose Infra).
- **Status-Labels fasst nur die Action an**, nie ein Agent per Shell
  (RECON-3) — `ticket-status-flow.yml` setzt sie fail-loud auf PR-Events.

## Definition of Done

Ein Issue ist erst `Done`, wenn:

- [ ] alle im Ticket genannten Requirement-IDs in der Spec stehen und erfüllt sind
- [ ] diese IDs in der Spec mit der Ticket-`#` annotiert sind
- [ ] der Code im Default-Branch gemerged ist
- [ ] gegen die `constitution.md` geprüft (North Star, Qualitätsattribute)
