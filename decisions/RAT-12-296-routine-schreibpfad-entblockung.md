# RAT-12 — #343 Routine-Schreibpfad (Zeiten) von #296 entblockt: Aktivierung über den TASK-7-Pfad

- **Entschieden:** 2026-06-06 (Cluster-Architektur-Runde „Eltern-Chat-Schreib-/
  Abfrage-Mechanik", Vorschlag + Codex-Antiberater), **ratifiziert** 2026-06-06
  (Nic, Verdikt A: „#343-Entblockung: JA, entblocken via RAT").
- **Betrifft:** `specs/buddies/routine.md` (ROUTINE-14 härten, OPEN-ROUTINE-B,
  ROUTINE-16), `decisions/RAT-6-296-familien-schnittstelle-skalierung.md`
  (hebt die „geblockt"-Markierung in Zeile 10 auf), `conventions/tasks.md`
  (TASK-7 ist die zitierte Aktivierungsheimat), `specs/platform/routine-zeiten-setzen.md`
  (neue RZS-Skill-Spec). Keystone-Ticket **#343** (OPEN-ROUTINE-B, Teil 1 =
  Zeiten); abgespalten: **#354** (Routine-Punkte, OPEN-ROUTINE-A).
- **Transkript (Evidenz):** `brainstorm/berater-runde/20260606-203107-RATIFIZIERT-elternchat-skill-cluster.md`
  (Verdikt A) → Vorschlag `20260606-203107-vorschlag-elternchat-skill-cluster.md`,
  Antiberater `2026-06-06-2031-antiberater-elternchat-skill-cluster.md`.

## Beschluss

Der Routine-Schreibpfad **Teil 1 (Zeiten setzen, `PUT /api/v1/routine/config`)**
ist **NICHT von #296 abhängig** und wird über den bestehenden TASK-7-Pfad
aktiviert — `build_catalog` registriert den Eltern-Chat-Skill, genau wie
`panel_anlegen` (PAA) bereits live ohne #296 läuft. Die in RAT-6 (Zeile 10)
gesetzte Markierung „#343 (OPEN-ROUTINE-B, geblockt)" wird **aufgehoben**, und
die #296-Klauseln in `specs/buddies/routine.md` (OPEN-ROUTINE-B :421-422 und
ROUTINE-16 :366-367) werden **im selben PR** gestrichen und durch den
TASK-7-Pfad-Verweis + RAT-12 ersetzt — sonst bleibt der Widerspruch ein
täglicher prep-Wiedergänger.

**Überführung statt Skizze (RAT-11-konform):** ROUTINE-14 wird für den
Zeiten-Endpunkt von einer entworfenen Schnittstelle zu einer **bindenden
Definitionszeile** gehärtet. Das ist genau die in RAT-11 (Prep-Reife-Gate)
verlangte Überführung eines `OPEN-*`/Skizzen-Eintrags in ein gemergtes
Requirement — erst danach ist Teil 1 baufertig/stempelbar. RAT-11 (Provenienz)
und RAT-12 (Überführung) greifen ineinander.

**Scope der Entblockung — eng:** entblockt wird **nur der Aktivierungs-
Mechanismus** des Schreibpfads (Skill-Registrierung über `build_catalog` /
TASK-7 statt App-Installations-Mechanismus #296). Die übrigen #296-Themen
bleiben **unberührt** — insbesondere App-Installation per Manifest+Factory, die
per #298-Tracer-Test als **NO-GO** gilt (Memory „App-Installation
Manifest+Factory = NO-GO"). RAT-12 baut diesen Mechanismus nicht neu.

**Kein TASK-8.** Der gemeinsame Schreib-Skill-Vertrag bleibt vertagt
(RAT-7-Defer bekräftigt, Verdikt D der Runde): die ungebauten Schreib-Skills
sind keine drei gleichartigen Exemplare mit Drift-Schmerz; Drift-Schutz
übernimmt die bestehende TASK-7. Der einheitliche Vertrag (RAT-6-Mechanik A,
„Sammeln-und-Schreiben") entsteht erst nach dem 2.–3. *gebauten* Schreib-Skill.

## Warum

- **TASK-7 sagt es bereits:** `conventions/tasks.md` benennt `build_catalog`
  ausdrücklich als heutige V1-Heimat der Aktivierung, **bis** der in `apps.md`
  (APP-4) beschriebene Installations-/Aktivierungs-Mechanismus existiert (#296).
  „Bis #296" heißt **baubar ohne #296**, nicht „blockiert durch #296".
- **Live-Beleg:** `panel_anlegen` (PAA) ist eine async-Schreib-Aufgabe, die
  exakt über diesen Pfad registriert ist (`eltern-chat/tasks.py`) und seit
  2026-06-05 live läuft (Memory „Panel-Registry Welle 1+2 live") — ohne #296.
  Routine ist dieselbe Sorte (PROZEDUR, RAT-6 Eimer 3, Routine ausdrücklich als
  Copy von `termin_eintragen` benannt, RAT-6 Zeile 33).
- **Heutiger Selbst-Widerspruch (das eigentliche Problem):** RAT-6 markiert #343
  als „geblockt" (RAT-6 Zeile 10) und `routine.md:421-422` / `routine.md:366-367`
  hängen den Schreibpfad an #296 — während TASK-7 ihn als baubar beschreibt. Drei
  SSoT-Dokumente widersprechen sich. RAT-12 löst den Widerspruch zugunsten des
  TASK-7-Pfads auf.

## Re-Litigation / Reopen nur bei erfülltem Trigger

- **App-Installations-Mechanismus (#296, APP-4):** bleibt offen und ist hiervon
  unberührt; entblockt ist nur die Aktivierung *des Routine-Schreib-Skills*. Wenn
  #296 später einen generischen Aktivierungs-Mechanismus liefert, migriert der
  Routine-Skill additiv dorthin (TASK-7 versteinert `build_catalog` nicht).
- **Einheitlicher Schreib-Vertrag (TASK-8 / RAT-6-Mechanik A):** wie RAT-6/RAT-7
  — erst ab dem 2.–3. gebauten Sammeln-und-Schreiben-Skill. Routine (Teil 1) ist
  der zweite Datenpunkt; nach seinem Bau ist die Mechanik-A-Frage neu zu prüfen.
- Sonst: bei jeder neu aufkommenden „ist der Routine-Schreibpfad an #296
  geblockt?"-Frage hier prüfen und mit Verweis auf RAT-12 schließen.
