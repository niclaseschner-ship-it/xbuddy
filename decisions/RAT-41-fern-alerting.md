# RAT-41 — Fern-Alerting: `/healthz`-Poller mit Timer, Alarm in einen Owner-Kanal

**Status:** RATIFIZIERT 2026-07-30 (Nic: „jetzt designen" + Kanal-Wahl „b")
**Betrifft:** Poller-Service + systemd-Timer, `conventions/services.md` (SVC-8
Heartbeat-Überwachung), Zugangsdaten-Slot für den Owner-Chat
**Bezug:** #1630 (`/healthz`-Rollout, gebaut), RAT-36 (Verdikt-Pass über
Gegenmechaniken)
**Ticket:** #1623 (Tracker) · Kinder #1646 (Poller), #1647 (Deploy-Trigger)
**Entscheid-File:**
`brainstorm/berater-runde/20260730-2300-RATIFIZIERT-fern-alerting.md`

## Problem

Der Betrieb ist unbeaufsichtigt und soll fremd-betreibbar werden. Bis dahin merkte
ein Mensch einen toten Dienst dadurch, dass eine App nicht ging. Es gab keinen Weg,
auf dem das System selbst sagt „ich bin kaputt" — und für eine fremde Familie ist
„du merkst es, wenn es nicht geht" keine Betriebsantwort.

## Betrachtete Alternativen

- **Alarm in die Familien-Gruppe.** Verworfen von Nic (Wahl „b"): Betriebs-Rauschen
  gehört nicht in den Familien-Kanal. Das ist die einzige Ein-Wege-nahe Achse der
  Entscheidung (Privacy), und sie wurde bewusst in Richtung eines getrennten
  Owner-/Master-Slots aufgelöst.
- **Nur Liveness prüfen (TCP-connect).** Zu schwach: ein hängender Dienst nimmt die
  Verbindung an und antwortet nie. Deshalb **zwei** Timeouts — connect (tot) und read
  (hängend).
- **Deep-Checks pro Dienst** (Kern-Funktion statt HTTP-Status). Nicht jetzt: gehört
  zur Ausbaustufe, siehe Kill-Kriterium.
- **Den Deploy-Auto-Trigger mitbauen.** Bewusst ausgegliedert — ein schreibender
  Deploy-Automat ist nicht dieselbe Sorte wie ein read-only Poller, und die
  bestehende Deploy-Mechanik trennt die beiden bereits.

## Wie entschieden

Die Runde konnte auf zwei Vorleistungen aufsetzen, die den Bau billig machten: die
`/healthz`-Endpunkte waren gerade gebaut (#1630), und für die Form „reine
`decide()`-Funktion + dünne I/O-Schale, als oneshot-Service mit Timer" gab es bereits
zwei Präzedenzfälle im Repo. Deshalb kein neues Muster, sondern ein Klon eines
vorhandenen Gerüsts.

Der Sende-Weg wurde nicht neu gebaut, sondern der bestehende Telegram-Client
wiederverwendet.

## Ergebnis

- **Ein oneshot-Poller-Service + systemd-Timer**, der die gebauten
  `/healthz`-Endpunkte mit **connect-Timeout** (tot = kein TCP) und
  **read-Timeout** (hängend = accept, aber kein 200 in N Sekunden) probt und bei rot
  eine Telegram-Nachricht sendet.
- **Alarm-Ziel = separater Owner-/Master-Chat-Slot** (privater Betriebskanal), nicht
  die Familien-Gruppe. Neuer Zugangsdaten-Slot.
- **Zielmenge:** die Dienste mit `/healthz`; die damals noch endpunktlosen Dienste
  sind als benannter Randfall geführt, nicht stillschweigend ausgelassen.
- **Deploy-Auto-Trigger als eigenes Ticket** (#1647).

## Woran wir merken würden, dass es falsch war

- **Ausbau-Trigger:** reicht `healthz` = 200 nicht, um „hängend" von „ok" zu trennen
  (Dienst antwortet 200, Kernfunktion ist tot), muss eine Deep-Check-Achse nachgerüstet
  werden. Der read-Timeout-Ansatz bleibt dabei die Basis.
- **Rückbau:** Poller + Timer sind klein und rückbaubar (Zwei-Wege-Tür).

## Nachtrag 2026-08-13/17 — was aus dem Gerüst wurde

Zwei Dinge haben sich seit der Runde geändert und gehören zur Ehrlichkeit dieses
Records:

- **Das geklonte Gerüst existiert nicht mehr.** RAT-36 hat `deploy/runner/`
  vollständig entfernt (Skript, Unit, README, Test) — die Vorlage, an der sich diese
  Runde orientierte, ist weg. Das berührt den Poller nicht; es heißt nur, dass die
  Formulierung „klont das Gerüst" heute nicht mehr auf eine Datei im Repo zeigt.
- **Der Poller selbst lebt.** RAT-36 hat ihn im Verdikt-Pass geprüft und als
  *verdrahtet* gestempelt, mit Ende-zu-Ende verifiziertem Alarmweg — er ist einer der
  wenigen geprüften Fälle, in denen die Gegenmechanik nicht nur deklariert war.
