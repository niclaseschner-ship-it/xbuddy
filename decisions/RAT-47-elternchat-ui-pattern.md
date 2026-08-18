# RAT-47 — Eltern-Chat-UI-Pattern: neun Achsen auf einmal, und die Schwelle Chat vs. WebApp

**Status:** RATIFIZIERT 2026-06-12 (Nic „Paket als Ganzes ja")
**Betrifft:** `specs/platform/eltern-chat.md` (EC-33, EC-34, EC-35;
EC-10-Umschrift; EC-20-Umschrift), `conventions/tasks.md` (TASK-9, TASK-10c),
`conventions/mini-app-design.md` (MAD-7-Öffnung, MAD-10 neu, MAD-8/MAD-9
verschoben), `conventions/apps.md` (APP-7 als neue Token-Heimat),
`conventions/eltern-chat-skills.md` (neu, reine Lego-Karte)
**Bezug:** RAT-16 (Vendor-Adapter-Disziplin — trägt die Launcher-Form);
RAT-44 (spätere Nachschärfung am selben Bestätigungs-Thema)
**Ticket:** kein Implementierungs-Ticket — die Runde erzeugte
Konventions-/Spec-Arbeit; die sechs Folge-Tracks (Phasen-Helper, Undo-Hook,
`presentation`-Übersetzung, `initData`-Server-Validierung, `task_events`,
Mockup-Probe) wurden danach einzeln geöffnet
**Entscheid-File:**
`brainstorm/berater-runde/20260612-093034-RATIFIZIERT-elternchat-ui-pattern.md`

## Problem

24 Eltern-Chat-Skills waren UI-uneinheitlich — in der Bestätigungs-Form, im
Tool-Result-Vertrag, im Abbruch-Verhalten und darin, wann überhaupt eine WebApp
statt Chat benutzt wird. Ein Skill-Autor lebte in **drei Dateien gleichzeitig**
(EC-Spec, TASK-Convention, MAD-Convention) und fand nirgends die
Reihenfolge, in der er sie lesen soll.

Der Zeitpunkt war kein Zufall: parallel lief ein Werft-Track mit drei Mockups,
also gab es eine lebende Probe für die eigentlich harte Frage — **wann ist eine
Aufgabe Chat und wann WebApp**.

## Betrachtete Alternativen

Die Runde lief über drei Vorschlags-Fassungen und einen Antiberater-Pass; die
Alternativen stehen deshalb **pro Achse**, nicht als eine große Gabel:

- **Schwelle nach Häufigkeit** (wie oft wird ein Skill gerufen) — verworfen
  zugunsten von **Volumen pro Anstoß**. Häufigkeit ist Telemetrie und war zum
  Entscheidungszeitpunkt nicht messbar; das Volumen ist pro Anstoß
  deterministisch ablesbar. Häufigkeit bleibt als *Bau-Priorität*, nicht als
  Schwelle.
- **Sofort-Write + Undo als neuer Default für alle Schreibakte** — vom
  Antiberater **gebrochen** an einem konkreten Gegenbeispiel (Listen-Skill:
  10→20→30 Einträge, ein Undo überschreibt die falsche Version). Eingeengt auf
  drei Bedingungen (siehe Ergebnis).
- **Eine neue Konventions-Datei mit eigenen Norm-Punkten für Skills
  (`ECS-N`)** — vom Antiberater als **Genre-Bruch** gebrochen: sie hätte eine
  dritte Wahrheit neben Spec und TASK-Convention erzeugt. Umgebaut zur reinen
  Lego-Karte ohne eigene Norm-Punkte.
- **Direkter `t.me`-Link vs. Inline-`web_app`-Button als *die* richtige Form**
  — aufgelöst durch einen Doku-Fund des Antiberaters: **beide Wege liefern
  `initData`**. Damit ist die Frage keine Norm mehr, sondern eine
  Capability-Wahl des Transports.
- **Skill-Aufrufzählung über die bestehende Provider-Call-Telemetrie** —
  verworfen: die zählt Tool-Loops, nicht Nutzer-Turns. Eigene Tabelle.

## Wie entschieden

Neun orthogonale Punkte, jeder mit eigenem „bricht wenn falsch"-Satz, und ein
Verdikt-Schema, das **pro Punkt** ja/nein zuließ — genau damit ein einzelner
strittiger Punkt nicht das ganze Paket blockiert. Nic nahm das Paket als Ganzes
an.

Zwei Dinge sind an dieser Runde bemerkenswert und gehören in den Record, weil
sie sonst verloren gehen:

**Die ID-Kollision.** Beim Schreiben fiel auf, dass die vorgesehene Nummer
EC-30 seit Monaten belegt war. `conventions/README.md` verbietet
Umnummerierung, also wurden die drei neuen Punkte als **EC-33, EC-34, EC-35**
geschrieben; EC-31/32 blieben leer. Wer das Protokoll liest, findet dort noch
die alten Nummern — die Zuordnung steht im Protokoll und hier.

**Die Auflage bei A4b.** Der Direktlink-Weg durfte **erst ausgespielt werden,
nachdem die Server-seitige `initData`-Validierung geschlossen ist**. Das war
zum Entscheidungszeitpunkt nachweislich nicht der Fall und wurde als eigenes
Folge-Ticket geführt, statt die Klausel „gilt ab jetzt" zu schreiben.

## Ergebnis

- **EC-33 — UI-Medien-Schwelle:** pro Anstoß ≥5 Einzelwerte **oder** ≥2
  Spalten/Achsen → WebApp, sonst Chat. Geheimnis/Auth bleibt Skill-direkt.
- **EC-10-Umschrift:** Sofort-Write + Quittung + Undo-Wort **nur** für
  Schreibakte, die (i) eine Ressource mit stabiler ID anlegen, (ii) deren
  Inverse ein idempotentes DELETE auf diese ID ist, und (iii) bei denen der
  Skill den Inverse-Aufruf **vor dem ersten Live-Einsatz** im Test nachweist.
  Alles andere bleibt Vorab-Bestätigung. Formalisiert in `TASK-9`.
- **TASK-10c:** drei zulässige Tool-Result-Formen (String · `{text,
  presentation}` · Datei + Caption); **das Framework sendet**, der Skill nie
  selbst — die vorher existierende Skill-eigene Doppelversand-Form ist
  verboten.
- **EC-34** (Cross-Skill-Empfehlung als Text-Footer) und **MAD-10**
  (Launcher-Capability: der Skill ruft `openMiniApp(...)`, der Transport wählt
  Inline-Button oder Direktlink). MAD-7 wurde dafür geöffnet.
- **MAD-8** (Schreibverhalten) wandert nach EC-10, **MAD-9**
  (Token-Deployment) nach `conventions/apps.md` APP-7 — beides
  Genre-Korrekturen, nicht Inhalts-Änderungen.
- **EC-20-Umschrift:** Session-Timeout ist **phasenbewusst** — vor dem
  Schreibakt eine Quittung an die Familie, nach erfolgreichem Schreibakt stumm
  (die Schreib-Quittung ist dann die Wahrheit).
- **EC-35:** Skill-Nutzungszählung über eine eigene `task_events`-Tabelle,
  gezählt werden erfolgreiche Nutzer-Turns. Ausdrücklich **nur** Voraussetzung
  für die Bau-Priorität, nicht für die Schwelle.
- **`conventions/eltern-chat-skills.md`** entsteht als reiner Wegweiser:
  Tabelle „Skill-Klasse → welche Spec + Convention + in welcher Reihenfolge
  lesen", **keine eigenen Norm-Punkte**.

## Woran wir merken würden, dass es falsch war

- **EC-10-Umschrift:** wenn der Pre-Flight-Nachweis (iii) in der Testpraxis
  nicht durchgehalten wird, rutscht ein Skill mit kaputtem DELETE in den
  Sofort-Write-Default. Reversibel — Spec zurück auf Vorab-Bestätigung.
- **EC-33:** eine WebApp für „eine Spalte, viele Items" wäre über-engineered.
  Die Mockup-Probe war genau dafür der Gegen-Test.
- **MAD-Ratifizierung:** die Runde verlangte **pro Regel zwei gleichartige
  Belegfälle**. Weicht der nächste Mini-App-Konsument in mehreren Punkten ab,
  ist nicht die Regel falsch, sondern die Ratifizierung falsch geschnitten —
  dann fällt MAD auf First-Occurrence zurück.
- **Undo-Halluzination** war das schärfste Risiko: ein Modell, das ein
  Undo-Wort auf den falschen Datensatz bezieht. Gelöst über einen
  deterministischen Hook **vor** dem Agenten — das Modell entscheidet nie über
  das Ziel. Dieselbe Bauart-Lehre („außerhalb des Agent-Loops, sonst hängt die
  Garantie an LLM-Compliance") trägt später RAT-44.
