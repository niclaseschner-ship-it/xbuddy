# RAT-44 — Bestätigung erkennen, Erfolg nicht behaupten: zwei Schichten gegen die falsche Vollzugsmeldung

**Status:** RATIFIZIERT 2026-08-01 (Nic „machen wir das", nach Root-Cause-Beweis)
**Betrifft:** `specs/platform/eltern-chat.md` — E-EC-7 (Nachschärfung) und **E-EC-13**
(neu)
**Bezug:** #1050 (Folgen-Verlust härten); E-EC-4 / EC-41 (Post-LLM-Naht als
Präzedenz); das 2026 verworfene Agent-Gate
**Ticket:** #1118 (reopen), Refs #1050
**Entscheid-File:**
`brainstorm/berater-runde/20260801-RATIFIZIERT-ENTSCHEID-hfe-confirm-ehrlichkeit.md`
(Antiberater = **Opus-Fallback**, Codex am Usage-Limit, im Protokoll ausdrücklich
als schwächer markiert)

## Problem

Live-Fall: ein Elternteil bestätigte einen Vertonungs-Vorschlag mit *„Ja mach"*. Das
wurde **nicht** als Bestätigung erkannt, also lief nie eine Ausführung — und der Bot
meldete trotzdem, die Folge sei fertig und in der App. Zwei unabhängige Fehler auf
einem Turn: die Bestätigung wurde verschluckt, und der Ausbleib-Zustand wurde als
Erfolg berichtet.

Der zweite ist der gefährlichere. Ein Assistent, der Vollzug behauptet, den es nicht
gab, ist nicht nur unbequem — er zerstört die Grundlage, auf der eine Familie ihm
irgendetwas glaubt.

## Wie die Ursache belegt wurde

Bevor irgendetwas entschieden wurde, wurde die Ursache festgenagelt statt geraten:

- Der exakte Erfolgs-Text aus dem Live-Chat existiert **nirgends im Code** — es gibt
  keine Nachrichten-Vorlage, die ihn erzeugt. Also **Halluzination des Modells**,
  keine mechanisch gesendete Bestätigung.
- Die Nachricht nannte eine Dauer, die nur in der *Vorschlags*-Nachricht steht; die
  echte Ausführungs-Nachricht nennt eine andere. Das Modell hat aus dem Kontext
  abgeschrieben, nicht aus einem Ergebnis berichtet.

Das schloss den bequemen Verdacht („irgendeine Bubble hat gefeuert") aus und
verschob die Frage von *welcher Code-Pfad war es* zu *wie hindern wir das Modell
daran, das zu behaupten*.

## Betrachtete Alternativen

- **Nur die Bestätigungs-Erkennung reparieren.** Zu wenig: die Erkennung wird immer
  Lücken haben; die Falschmeldung darf nicht davon abhängen, dass die Erkennung
  vollständig ist.
- **Ein zweiter Prompt-Hinweis im Agent-Loop.** Vom Antiberater **gebrochen** — der
  Hinweis existiert bereits („Aufgabe NICHT ausgeführt") und wurde vom Modell
  ignoriert. Genau das *ist* die Regression. Ein weiterer Hinweis koppelt an dieselbe
  versagende Achse: LLM-Compliance.
- **Ein Re-propose-blockierendes Agent-Gate.** Bereits 2026 verworfen (blockt die
  Familie am Stapel) und wird hier **nicht** wieder aufgemacht. Der gewählte
  Post-Filter blockt nichts — er zensiert eine Falschaussage. Das ist die Grenze, an
  der die Runde ausdrücklich prüfte, ob sie eine verworfene Achse durch die
  Hintertür reöffnet: tut sie nicht.
- **Weite Füllwort-Liste bei der Bestätigungs-Erkennung.** Verworfen, siehe unten —
  eine zu weite Liste zerbricht die Ablehnungs-Erkennung.

## Ergebnis — zwei Schichten, beide auf Rang 1 (Zuverlässigkeit)

Kein Fork, sondern zwei unabhängige Fixe desselben Bugs. **B ist die eigentliche
Garantie; A senkt nur, wie oft B einspringen muss.**

**Schicht A — Bestätigungs-Erkennung aufweiten (E-EC-7-Nachschärfung).** Token-weise:
Bestätigung, wenn *alle* Tokens entweder ein Bestätigungswort oder ein enger Füller
sind — und **kein** Wort und keine Phrase aus der bestehenden Ablehnungsliste trifft
(**Ablehnung gewinnt**). Der Füller-Satz ist bewusst eng: mehrere naheliegende
Kandidaten sind **ausgeschlossen**, weil sie die mehrwörtigen Ablehnungs-Phrasen
zerbrechen würden — ein Fund der zweiten Runde, den der Antiberater übersehen hatte,
weil er die Ablehnungsliste nicht mitgelesen hatte.

**Schicht B — deterministischer Post-LLM-Ehrlichkeits-Filter (E-EC-13).** An der
bestehenden Naht *nach* dem Antworttext und *vor* dem Senden: solange ein
unbestätigter schreibender Vorschlag offen ist, wird der Text gegen eine enge
Erfolgs-Wortliste geprüft und bei Treffer durch einen festen Hinweis **ersetzt**.
Endet der Text auf „?", greift der Filter nicht (legitime Rückfrage). Der einzige Weg
zu einer Erfolgsmeldung bleibt der ausgeführte Pfad hinter der deterministischen
Bestätigung.

Entscheidend ist der Ort: **außerhalb des Agent-Loops**. Nur dort ist der Filter
modell-unabhängig — und genau daran war die Loop-interne Variante gescheitert.

## Woran wir merken würden, dass es falsch war

- **A:** ein Fixture lässt eine Ablehnungs-Phrase als Bestätigung durch, oder eine
  benachbarte Schleife, die Nicht-Bestätigung als Abbruch nutzt, endet nicht mehr
  sauber → Füller-Satz weiter kürzen, im Grenzfall auf leer.
- **B:** ein legitimer Re-Vorschlag wird zensiert → Frage-Ausnahme oder Wortliste
  enger. Vor dem Commit als Stub-Experiment gefahren: ein Modell, das bei offenem
  Vorschlag Erfolg behauptet, muss den Ersatztext senden **und** darf die Ausführung
  nicht angestoßen haben; ein Text, der auf „?" endet, muss unverändert durchgehen.
- **Ein-Wege-nah:** B ist eine Rang-1-Garantie über jeden Antworttext. Wer sie
  aufweicht, muss denselben Beweis führen wie diese Runde — mit Live-Beleg, nicht
  mit einer Vermutung über Modell-Verhalten.
