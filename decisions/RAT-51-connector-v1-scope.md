# RAT-51 — Connector-Übersicht V1: sehen und umschalten ja, Geheimnisse schreiben nein

**Status:** RATIFIZIERT 2026-06-25 (Nic)
**Betrifft:** `specs/platform/connector.md` (V1-Schnitt der Seite)
**Bezug:** RAT-2 (Netz-Grenze als Auth — gilt für **Regeln**, ausdrücklich
nicht für API-Schlüssel); RAT-18 (Auth-Strategie); die
Zugangsdaten-Bibliothek (ratifiziert Library-ohne-HTTP); der bestehende
Anbieter-Wechsel-Dialog im Eltern-Chat
**Ticket:** #1086 (Bau) · #948 (Auth-Härtung, Folge-Treiber) · #1030
(Hot-Swap) · #1131 (Telemetrie)
**Entscheid-File:**
`brainstorm/berater-runde/20260625-1145-RATIFIZIERT-connector-v1-scope.md`

## Problem

Die Connector-Seite sollte in einem Zug alles können: Anbieter sehen,
Verbrauch zeigen, Schlüssel eintragen und live umschalten. Die **Lese-Hälfte**
war baureif, die **Schreib-Hälfte** doppelt blockiert — es gab keine
Auth-Klasse für sensible schreibende HTTP-Routen, und der Live-Wechsel hing an
einem eigenen Ticket.

## Betrachtete Alternativen

- **Volle Vision sofort** (HTTP-Schreibpfad für Geheimnisse + Live-Switch).
  Blockiert, siehe oben.
- **„Die Seite ist nur lokal erreichbar, das Netz ist die Auth."** Das war die
  naheliegende Rettung und wurde vom Antiberater **zweifach gebrochen**:
  1. Der Fernzugang war zum Zeitpunkt der Runde **default-exponiert**, nicht
     default-verweigert. Eine *getestete* Verweigerungs-Regel ist damit
     Vorbedingung, nicht Nebensache — und sie existierte nicht.
  2. Die Zugangsdaten-Bibliothek ist ratifiziert **ohne HTTP-Oberfläche**, und
     der Schlüssel-Wechsel hat bereits einen *schärferen* Weg (bestätigende
     Person + Validierungs-Ping + atomarer Tausch). Eine reine Netz-Grenze wäre
     eine Aufweichung, kein Fortschritt. Die RAT-2-Analogie trägt nicht:
     RAT-2 regelt Garderoben-Regeln, nicht API-Schlüssel.
- **Anbieter-Wechsel über den Hilfs-Slot** statt über den echten Config-Wert.
  Verworfen — es gibt den echten Wert, der Hilfs-Slot ist eine zweite Wahrheit.
- **In-Page-Editor jetzt bauen und einfach nicht verlinken.** Nicht ernsthaft
  verteidigt; ein gebauter Schreibpfad ist ein Schreibpfad.

## Wie entschieden

Nic setzte zunächst die Netz-Grenzen-Form, der Antiberater brach sie an den
zwei Punkten oben, und der Beschluss übernahm **beide Brüche**, statt sie
wegzuwiegen. Was hielt, blieb drin: der Anbieter-Wechsel über Config-Wert plus
Neustart ist unbedenklich und kam in V1.

Die Schlüssel-Verwaltung wurde nicht gestrichen, sondern **umgeleitet**: als
Deep-Link in den bestehenden Chat-Dialog, der die scharfe Mechanik schon hat.
Damit verliert V1 keine Fähigkeit — sie wohnt nur dort, wo die Absicherung
bereits existiert.

Eine Design-Setzung von Nic gehört dazu: der spätere In-Page-Editor wird im
Layout **schon platziert**, aber ausgegraut mit „kommt in V2". Die Lücke ist
sichtbar statt vergessen.

## Ergebnis — V1

1. **Read-only Sicht** — Inventar, Live-Status, Verbrauch/Kosten je
   Anbieter/Buddy/Modell, aggregiert aus dem vorhandenen Aufruf-Protokoll.
2. **Anbieter-Wechsel** über das Schreiben des **echten** Config-Werts plus
   Service-Neustart.
3. **Schlüssel anlegen/tauschen** über **Deep-Link in den bestehenden
   Chat-Dialog** — **kein** HTTP-Schreibpfad für Geheimnisse in V1.
4. **Layout denkt V2 mit**, ausgegraut.

**Reversibilität:** V1 ist überwiegend Zwei-Wege-Tür. Die Ein-Wege-Tür (der
HTTP-Schreibpfad) ist bewusst vertagt.

## Die Vorbedingungen für V2 — in dieser Reihenfolge

Der Beschluss hat eine Nebenwirkung, die wichtiger ist als die Seite selbst:
er benennt die Connector-Seite als **ersten konkreten Treiber** für die
Auth-Härtung. Vorher war „Auth-Schmerz" ein abstrakter Trigger; hier hängt ein
konkretes Feature daran.

1. **Auth-Klasse für sensible lokale Schreib-Routen** klären (#948).
2. **Getestete Verweigerungs-Regel** für den Fernzugang, mit Test im
   Deploy-Verzeichnis.
3. **Spec-Patch:** HTTP-Schreibpfad für Zugangsdaten (Bibliothek → lokaler
   Editor) mit Slot-Allowlist und Validierungs-Ping, kein Klartext-Echo — und
   der zugehörige Grundsatz-Entscheid, dass die Netz-Grenze für API-Schlüssel
   *nicht* reicht.
4. **Hot-Swap** (#1030) für den Wechsel ohne Neustart — optional, V1 lebt mit
   Neustart.

## Woran wir merken würden, dass es falsch war

- **Kill-Kriterium V1:** ein Vollscan des Aufruf-Protokolls bremst die Seite,
  sobald die Datei groß wird. Probe: synthetische Protokolle im
  100-MB-/1-GB-Bereich auf der Zielhardware; die Seite muss im Latenzbudget
  bleiben. Ausweg: Zeitfenster-Tail mit „unvollständig"-Markierung oder ein
  Aggregat-Cache.
- **Der Deep-Link-Umweg ist zu unbequem,** wenn Eltern für jeden
  Schlüssel-Tausch die Oberfläche wechseln müssen. Das ist der erwartete
  Zug-Druck Richtung V2 — und genau der soll durch die Auth-Härtung laufen,
  nicht an ihr vorbei.
