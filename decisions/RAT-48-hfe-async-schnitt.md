# RAT-48 — HFE-Async-Schnitt: nur `execute()` in den Thread, sonst nichts

**Status:** RATIFIZIERT 2026-06-19 (Nic „ok ich folge soweit deinen
empfehlungen … lass uns das implementieren, streng nach vorschrift erst mit
arbeitstag-prep skill ready machen")
**Betrifft:** `specs/platform/hoerspiel-folge-erzeugen.md` — **HFE-11**
(Job-Single-Slot pro Chat) und **HFE-12** (Restart-Verlust akzeptiert) neu,
E-HFE-4 in V1 (verworfen) / V1.1 (ratifiziert) / V2 (offen) gesplittet
**Bezug:** RAT-49 (Polling-Reader — dieselbe Sitzung, löst den Restschmerz,
den dieser Schnitt offen lässt); EC-10 (Bestätigungs-Gate, das den
Vorschlags-Pfad synchron hält)
**Ticket:** zum Zeitpunkt der Ratifizierung keines — bewusst über den
prep-Lifecycle in ein Ticket überführt statt direkt gebaut
**Entscheid-File:**
`brainstorm/berater-runde/2026-06-19-1505-RATIFIZIERT-hfe-async-schnitt.md`

## Problem

Die Vertonung einer Hörspielfolge lief **synchron im Polling-Loop** des
Eltern-Chats und blockierte ihn 1–5 Minuten. Solange nur eine Person den Bot
benutzte, war das unsichtbar. Ab dem Zeitpunkt, wo mehrere Familienmitglieder
im Privatchat-Modell schreiben, hängt die Anfrage des zweiten Elternteils
minutenlang — der Bot **wirkt kaputt**, obwohl er arbeitet.

## Betrachtete Alternativen

- **Vollform:** `execute()` **und** `propose()` in Background-Threads, alle
  geteilten Stores gelockt, Job-Registry plus Session-Eintrag,
  `is_async=True`. Acht Nähte. Vom Antiberater in vier Punkten gebrochen:
  - `propose()` async bricht das Bestätigungs-Gate (ein Stub-Vorschlag läge im
    Pending-Slot, bevor der echte existiert);
  - ein Session-Eintrag beansprucht den Privatchat und würde andere Fragen
    derselben Person in eine nutzlose Warteschlange routen;
  - `is_async=True` kollidiert mit den geplanten Task-Hooks;
  - Store-Locks sind **unnötig**, solange der Thread keine Stores schreibt —
    also erst gar keinen Thread bauen, der schreibt.
- **Persistenter Job-State über Neustarts** — als V2 vertagt, nicht verworfen.
  Der Restart-Verlust wird stattdessen zugegeben (siehe HFE-12).
- **Timeout 30 min statt 600 s** — als Gabel offen gehalten und von Nic mit
  600 s entschieden.

## Wie entschieden

Der Antiberater hat die Vollform nicht widerlegt, sondern **abgetragen**: jede
der vier Nähte, die er brach, war eine, die nur die Vollform brauchte. Was
übrig blieb, ist die Min-Variante — und die trägt genau den Schmerz, der
gemessen wurde.

Der load-bearing Satz: **`propose()` bleibt synchron.** 20–90 Sekunden Wartezeit
beim Vorschlag sind das kleinere Übel gegenüber 5 Minuten beim Bauen, und die
Synchronität ist es, die das Bestätigungs-Gate intakt hält. Der Restschmerz aus
diesen 20–90 Sekunden wurde nicht wegdiskutiert, sondern in dieselbe Sitzung
als eigene Runde gehängt — RAT-49.

Nic entschied vier Punkte einzeln: Min-Variante ja, Timeout 600 s,
Anker HFE-11/HFE-12, und die Form (Entscheid-Datei als primärer Anker, Spec nur
kurz nachgezogen).

## Ergebnis

- **Nur `execute()`** läuft in einem Daemon-Thread, **lokal im Task**. Kein
  Session-Eintrag, kein `is_async`-Vertrag, **kein Schreiben in geteilte Stores
  aus dem Thread** — das ist die Bedingung, unter der die Locks entfallen
  dürfen.
- **HFE-11 — Job-Single-Slot pro Chat:** maximal ein aktiver Bau je Chat,
  600 s Stuck-Schutz, bei Doppelstart eine „warte kurz"-Notiz statt eines
  zweiten Threads.
- **HFE-12 — Restart-Verlust akzeptiert:** ein Neustart während des Baus
  verliert den Job. Die Familie merkt es am Ausbleiben der Abschluss-Nachricht
  und startet neu. Persistenter Job-State bleibt V2.
- **Keine Konvention** bei n=1. Eine `job-worker`-Konvention ist
  Vertagungs-Kandidat für den zweiten Long-Running-Task — nicht auf Vorrat.

## Woran wir merken würden, dass es falsch war

- **Der Single-Slot ist zu eng,** wenn eine Familie regelmäßig zwei Folgen
  parallel bauen will. Dann ist HFE-11 der Ort, an dem nachgeschärft wird,
  nicht der Thread-Schnitt.
- **600 s sind zu kurz,** wenn ein legitimer Bau länger dauert und der
  Stuck-Schutz ihn abräumt. Die Runde hielt 30 min als Gegen-Option
  ausdrücklich offen; ein Mock-Experiment mit überlangem Lauf entscheidet.
- **HFE-12 ist eine bewusste Ehrlichkeits-Grenze:** der Job-Verlust ist kein
  Bug, sondern die dokumentierte Kehrseite dieser Sparsamkeit. Wer ihn
  reparieren will, öffnet V2 — das ist keine Re-Litigation.
- **Offen belassen:** die Abschluss-Nachricht trägt keinen Bezug auf die
  auslösende Nachricht. Das war Bestand vor der Runde und wurde bewusst nicht
  mitgezogen.
