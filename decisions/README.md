# decisions/ — Ratifizierte Entscheidungen (Overhead-Spur)

Hier liegen die **ratifizierten Architektur-/Design-Entscheidungen** von XBuddy:
das *Ergebnis* einer Beratung, nicht die Beratung selbst.

Diese Spur ist **Overhead** — die „wie wir entscheiden"-Schicht, bewusst getrennt
von der aktiven Buddy-/Produkt-Struktur (`specs/`, `eltern-chat/`, `plan/`, …).
Sie liegt im Code-Repo, weil eine Entscheidung die Specs regiert, die sie betrifft,
und same-repo deterministisch lesbar sein muss (WORKFLOW.md — `prep-reconcile`).

## Entscheidung vs. Deliberation — zwei Naturen, zwei Heimaten

| | Was | Wo |
|---|---|---|
| **Entscheidung** (durable, regiert eine Spec) | der ratifizierte Beschluss + das Warum | **hier** (`decisions/`) |
| **Deliberation** (datiert, explorativ, laut) | Berater-Vorschlag, Antiberater-Bericht, Logs, verworfene Varianten | `brainstorm/berater-runde/` (Schwester-Spielplatz, **nicht** Teil dieses Repos) |

Gearbeitet wird **außerhalb** dieses Repos (brainstorm). Das Ergebnis wandert hierher
wie ein gemergtes Artefakt. Die volle Deliberation bleibt als Evidenz in brainstorm —
sie wird **verlinkt, nicht kopiert** (CLAUDE.md §6). Jeder Record ist selbsttragend für
„was + warum"; der brainstorm-Link führt zur tiefen Beweisspur.

## Aufbau

- **`INDEX.md`** — die SSoT-Liste: jede Entscheidung eine Zeile, stabile ID (`RAT-N`),
  1-Satz-Beschluss, was sie betrifft, Link zum Record. Das ist der Anker, gegen den
  die prep-Maschine den Re-Litigations-Check fährt („ist das schon entschieden?").
- **`RAT-<N>-<slug>.md`** — pro Entscheidung ein kurzer, selbsttragender Record:
  Beschluss · Warum (knapp) · was es betrifft · Link zum brainstorm-Transkript.

Bewusst **kein schwerer ADR-Apparat** — XBuddy entscheidet Nic-in-Minuten, nicht
Team-Konsens über Monate. Kurz halten.

**Form eines Records:** die vier Glieder — Problem → betrachtete Alternativen →
wie entschieden/gemessen → Ergebnis. Sie stehen als eine Quelle im Methoden-Repo
(`lotse/contracts/entscheidung.md`) und gelten für RAT-Records, Prozess-Tickets
und größere Ticket-Begründungen gleichermaßen; hier nicht duplizieren. „Kurz
halten" heißt: alle vier Glieder, jedes knapp — nicht: Glieder weglassen.

## Eine neue Entscheidung eintragen

1. Berater-Runde in brainstorm laufen lassen (Vorschlag + Antiberater), Nic ratifiziert.
2. Kurzen `RAT-<N>-<slug>.md` hier anlegen (Beschluss + Warum + Betrifft + Transkript-Link).
3. Zeile in `INDEX.md` ergänzen.
4. Betroffene Specs in eigenen Spec-PRs nachziehen (Spec-Halt, je Checkpoint).
