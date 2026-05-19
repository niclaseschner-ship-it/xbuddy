# Specs — Modell & Konventionen

`specs/` ist die **Quelle der Wahrheit** für das Soll-Verhalten von XBuddy.
Es sind **lebende Specs**: Sie beschreiben, wie das System sich *heute*
verhalten soll — nicht, was wann geändert wurde (das steht in Tickets/PRs).

## Aufbau

- `constitution.md` — übergeordnete Prinzipien, selten geändert.
- `system.md` — Ökosystem-Architektur, Zusammenspiel der Bausteine.
- `<komponente>.md` — eine lebende Spec je Ökosystem-Baustein
  (`display`, `controller`, `hub`) bzw. je Buddy unter `buddies/`.

Eine neue Komponente bekommt **erst dann** eine Datei, wenn es echte
Anforderungen dafür gibt — keine leeren Stubs.

## Anforderungen & IDs

Jede Anforderung hat eine **stabile ID**: Präfix der Komponente + laufende
Nummer, z. B. `DISP-1`, `CAL-3`. IDs werden **nie neu vergeben und nie
umnummeriert** — eine entfernte Anforderung hinterlässt eine Lücke.

Formuliert wird in **EARS** (Easy Approach to Requirements Syntax):

| Muster | Form |
|---|---|
| Immer | „Das System tut X." |
| Ereignis | „Wenn ‹Trigger›, tut das System X." |
| Zustand | „Solange ‹Zustand›, tut das System X." |
| Optional | „Wo ‹Funktion vorhanden›, tut das System X." |
| Unerwünscht | „Wenn ‹unerwünschte Bedingung›, tut das System X." |

EARS zwingt dazu, Trigger und Bedingungen explizit zu machen — die Anforderung
wird testbar.

## Verhältnis zu Tickets

Ein Ticket ist ein **Inkrement**, kein eigener Spec-Container:

1. Braucht das Ticket neue/geänderte Anforderungen → **zuerst** die
   Komponenten-Spec anpassen, IDs vergeben, reviewen.
2. **Dann** implementieren — gegen genau diese IDs.
3. Erfüllte Anforderung wird in der Spec mit der Ticket-`#` annotiert.

So zeigt die Spec jederzeit den Soll-Zustand, und jede Anforderung ist
rückverfolgbar bis zu Ticket und Code. Kein Code, bevor die Anforderung in
der Spec steht.

Vorlage für eine neue Komponenten-Spec: `_TEMPLATE.md`.
