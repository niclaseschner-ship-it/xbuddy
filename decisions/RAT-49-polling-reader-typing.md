# RAT-49 — Polling-Reader-Thread + Sofort-Typing: der Bot sieht wieder zu, während er denkt

**Status:** RATIFIZIERT 2026-06-19 (Nic, im selben Turn wie RAT-48)
**Betrifft:** `specs/platform/eltern-chat.md` — **EC-37**
(Reader/Processor-Polling-Topologie), **EC-38** (At-least-once-Verarbeitung),
**EC-39** (Sofort-Typing bei Privatchat-Empfang); Quer-Verweise in EC-25 und
E-EC-2 (Long-Poll-Timeout bleibt 30 s)
**Bezug:** RAT-48 (Vorgänger-Runde derselben Sitzung — schließt die
Bau-Blockade, dieser Beschluss den Rest); EC-25 (Privatchat-Grenze, durch
Bestand-Tests verriegelt)
**Ticket:** zum Zeitpunkt der Ratifizierung keines — über den prep-Lifecycle
überführt
**Entscheid-File:**
`brainstorm/berater-runde/2026-06-19-1545-RATIFIZIERT-polling-reader-typing.md`

## Problem

RAT-48 nahm die 1–5-Minuten-Blockade weg, aber nicht die restlichen 20–90
Sekunden: solange der Vorschlags-Pfad synchron läuft, ruft der Bot in dieser
Zeit `getUpdates` **nicht** — er kann die Nachricht eines anderen
Familienmitglieds nicht einmal *sehen*, geschweige denn darauf reagieren. Für
die absendende Person sind das anderthalb Minuten vollkommene Stille.

## Betrachtete Alternativen

- **Long-Poll-Timeout von 30 s auf 4 s senken.** Verkürzt die Blindzeit, kostet
  aber dauerhaft mehr Requests und löst das Problem nicht — bei 90 s Arbeit ist
  der Loop trotzdem blind. Verworfen, E-EC-2 bleibt bei 30 s.
- **Bulk-Prefetch im Reader** (mehrere Updates auf Vorrat holen). Vom
  Antiberater **gebrochen**: der Reader bestätigt Updates bei Telegram, bevor
  der Processor sie verarbeitet hat — ein Absturz verliert dann eine Nachricht,
  die heute überlebt. Die Robustheit war vorher besser als nach dem
  „Fortschritt".
- **Typing-Erneuerung aus demselben Loop.** Hält den Indikator nicht über einen
  30-Sekunden-Long-Poll. Eigener Thread.
- **Eine `TelegramClient`-Instanz für Reader und Processor**, abgesichert durch
  einen Thread-Safety-Docstring. Verworfen: das Versprechen war nicht belegt.
  Zwei Instanzen mit demselben Token kosten nichts und brauchen keinen neuen
  Vertrag.
- **Sofort-Typing auf jedem eingehenden Chat.** Verletzt die Privatchat-Grenze
  (EC-25), die durch Bestand-Tests verriegelt ist. Gefiltert.

## Wie entschieden

Die erste Fassung wurde in vier Punkten gebrochen und in derselben Runde
gepatcht — der wichtigste Patch entstand aber erst im **zweiten** Durchgang:
eine einzelne begrenzte Übergabe-Warteschlange reicht **nicht**, weil der
Processor den Platz schon beim Entnehmen freigibt, nicht erst nach der
Verarbeitung. Zwischen Entnahme und Fertigstellung liegt genau das Fenster, in
dem ein Absturz die Nachricht verliert.

Die Lösung ist deshalb **zwei** Warteschlangen mit je einem Platz: eine für die
Übergabe, eine für die Fertig-Quittung. Der Reader rückt den Offset erst vor,
nachdem der Processor quittiert hat. Das ist der Unterschied zwischen „sieht
nach Sicherheit aus" und „ist sicher" — und er wurde nur gefunden, weil ein
zweiter Pass über die eigene Korrektur lief.

Der Preis steht offen im Beschluss: **At-least-once**. Ein Absturz zwischen
Empfang und Verarbeitung führt dazu, dass Telegram das Update nach dem Neustart
erneut liefert. Nic hat das akzeptiert, mit Begründung: die schreibenden Akte
sind über das Bestätigungs-Gate und die Quittungs-Mechanik abgesichert.

## Ergebnis

- **EC-37 — Reader/Processor-Topologie:** `getUpdates` läuft in einem
  Daemon-Thread, getrennt vom Verarbeiten. Übergabe über eine begrenzte
  Warteschlange mit einem Platz plus explizite Fertig-Quittung.
- **EC-38 — At-least-once:** der Offset wird erst **nach** dem Konsum erhöht.
  Doppelte Verarbeitung nach einem Absturz ist das bewusst akzeptierte Risiko.
- **EC-39 — Sofort-Typing bei Privatchat-Empfang:** der Reader schickt den
  Typing-Indikator direkt nach Empfang, ein eigener Erneuerungs-Thread hält ihn.
  **Nur Privatchat** — die Familien-Gruppe ist ausgenommen (EC-25). Der
  Privacy-Trade-off (Typing kommt *vor* der Berechtigungs-Prüfung) steht
  ausdrücklich in EC-39, statt still zu passieren.
- **Zwei Client-Instanzen**, gleicher Token, getrennte Verbindungen. Kein
  Refactor, kein neuer Vertrag im Code.
- **Keine Konvention jetzt:** mit diesem Bau existiert die dritte
  Typing-Erneuerungs-Schleife. Eine Konvention dafür wurde ausdrücklich **nach**
  den Bau vertagt, nicht mit ihm zusammen beschlossen.

## Woran wir merken würden, dass es falsch war

- **At-least-once beißt,** sobald ein schreibender Pfad entsteht, der **nicht**
  hinter dem Bestätigungs-Gate liegt. Dann trägt die Begründung für EC-38 nicht
  mehr und der Offset-Zeitpunkt muss neu verhandelt werden.
- **Die Ein-Platz-Übergabe ist der Durchsatz-Deckel.** Sie ist Absicht (sie
  *ist* die Crash-Robustheit), aber wenn der Bot je mehrere Turns wirklich
  parallel bedienen soll, ist genau diese Klausel die Stelle, die fällt.
- **EC-39 ist die Privacy-Kante:** wer den Indikator je über den Privatchat
  hinaus ausdehnt, hebelt die durch Tests verriegelte Gruppen-Grenze aus. Die
  Tests sind dort der Wächter, nicht der Text.
