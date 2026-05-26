# Specs

`specs/` ist die **Quelle der Wahrheit** für das Soll-Verhalten von XBuddy —
**lebende Specs**: Sie beschreiben, wie das System sich *heute* verhalten
soll, nicht was wann geändert wurde (das steht in Tickets/PRs).

## Die eine Regel

> **Verhalten ändern = Spec im selben PR ändern.**

Code und Spec wandern zusammen, im selben Branch, im selben Review. Mehr
braucht es nicht, um die Spec synchron zu halten.

## Aufbau

- `constitution.md` — übergeordnete Prinzipien, selten geändert.
- Eine Spec-Datei je **Fähigkeit mit eigenem Verhaltens-Vertrag** —
  `buddies/<name>.md` (was die Familie erlebt) bzw. `platform/<name>.md`
  (geteilte Software-Fähigkeit wie Messaging, Rendering).
- `../conventions/` — paralleles Genre für das *Wie* (Bauregeln,
  einheitliche Form). Specs zitieren Konventions-IDs (z. B. „folgt
  IDENT-1"), beschreiben selbst kein „Wie".

Gegliedert wird nach **Verhalten**, nicht nach Code-Modulen und nicht nach
Hardware. Eine Datei entsteht **erst**, wenn ein Ticket die Fähigkeit
berührt — nichts auf Vorrat.

## Eine Anforderung schreiben

Jede Anforderung hat eine **stabile ID** (Präfix + laufende Nummer) und einen
testbaren Satz — am besten im Wenn/Dann-Stil:

```markdown
# Kalender — Spec     (ID-Präfix: KAL)

### KAL-1 — Wochenansicht
Das System zeigt die Termine der laufenden Woche als Tagesspalten.

### KAL-2 — Heute hervorheben
Wenn der angezeigte Tag der heutige ist, hebt das System ihn farblich ab.
```

IDs werden nie neu vergeben und nie umnummeriert. Ein Ticket nennt die IDs,
die es umsetzt — das ist der Link zwischen Ticket, Spec und Code.
