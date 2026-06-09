# Wünsche zeigen — Spec     (ID-Präfix: WZE)

> Status: V1 · Refs #474

Damit ein Elternteil die aktuellen Essens-/Einkaufs-Wünsche der Familie im
Eltern-Chat abfragen kann, ohne am Display nachzusehen, definiert diese Spec
**Wünsche zeigen als aufrufbare Funktion**: Aufgerufen, liest sie die
Wunsch-Liste aus dem Essens-Buddy — als Konsument der
Essens-Buddy-Wünsche-Schnittstelle (`essen.md` ESSEN-15) — und antwortet dem
Familienmitglied im Eltern-Chat mit einer kategorisierten Zusammenfassung.

Es ist eine **lesende** Aufgabe (EC-9): die Funktion verändert keine
Familien-Daten, daher kein Bestätigungs-Gate. Die Funktion ist
**trigger-agnostisch** (E-WZE-1 analog `termine-erfragen.md` E-TER-1): wer sie
aufruft — eine Eltern-Chat-Aufgabe, ein späteres anderes Interface — ist nicht
Teil ihres Vertrags.

**V1-Scope:** das Erfragen der vollständigen Wunsch-Liste über den
Eltern-Chat-Bot · die Funktion als trigger-agnostischer Konsument der
Essens-Buddy-Wünsche-Schnittstelle (`essen.md` ESSEN-15, `GET
/api/v1/essen/wuensche`) · die Antwort als hart-codierte, kategorie-gruppierte
Text-Zusammenfassung in dem Chat, in dem die Frage gestellt wurde (Gruppe oder
Privatchat) · der Trigger als Eltern-Chat-Aufgabe (EC-8, analog
`termine-erfragen.md` TER-9).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Filter-Anfragen** („zeig nur Obst", „zeig nur die heutigen Wünsche") —
  V1 liefert immer die ganze Liste; Filter braucht ein eigenes Ticket, wenn
  belegter Schmerz da ist.
- **Wunsch-Pflege im selben Skill** (löschen, leeren, hinzufügen) — sind
  schreibende Aufgaben mit propose→confirm und gehören in eigene Skill-Specs
  (OPEN-ESSEN-A in `essen.md`).
- **Stichwort-/Personen-Suche** über die Liste — V1 hat keine Personen-Schicht
  (E-ESSEN-8); Filterung wäre vorzeitig.
- **Eigener Cache** in dieser Funktion — die Essens-Buddy-Schnittstelle ist
  die einzige Wahrheits-Quelle (APP-3, CLAUDE.md §6), jeder Aufruf geht frisch
  dorthin.

---

## WZE-1 — Wünsche zeigen ist eine aufrufbare Funktion
„Wünsche zeigen" ist eine klar abgegrenzte, **aufrufbare Funktion** mit
definierter Schnittstelle. **Eingang:** die Telegram-Chat-Identität, in der die
Antwort landet (Gruppen-Chat-ID oder Privatchat-ID des Aufrufers), und die
Telegram-User-ID des Aufrufers (für die Berechtigung WZE-2). **Wirkung:** die
Funktion verändert **keine** Familien-Daten; sie liest aus der
Essens-Buddy-Wünsche-Schnittstelle (WZE-4). **Ausgang:** ein Ergebnis-Signal an
den Aufrufer — „beantwortet" (die Antwort wurde im genannten Chat gepostet),
„abgelehnt" (Berechtigung fehlt, WZE-2), „leer" (keine Wünsche in der Liste —
Antwort wurde dennoch gepostet, mit klarem Hinweis, WZE-6) oder
„nicht_erreichbar" (Essens-Buddy nicht da oder Schnittstelle scheitert, WZE-7).
Die Funktion kennt ihren Aufrufer nicht (E-WZE-1).

Skill-Modul: `eltern-chat/skills/wuensche_zeigen.py` (Funktion) +
`wuensche_zeigen_task.py` (Trigger), analog der TER-Linie.

*Tickets:* #474

## WZE-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-Mitgliedschaft,
analog `eltern-chat.md` EC-2 und `termine-erfragen.md` TER-2. Ist er es nicht,
bricht die Funktion mit „abgelehnt" ab und postet keine Antwort. Die Prüfung
liegt **bei der Funktion**, nicht beim Aufrufer — sonst hinge die
Berechtigungslogik am Trigger und die Funktion verlöre ihre Trigger-Agnostik
(E-WZE-1).

*Tickets:* #474

## WZE-3 — Antwort dort, wo die Frage kam
Die Antwort wird in **demselben** Telegram-Chat gepostet, aus dem die Frage
kam — Gruppen-Chat oder Privatchat, analog `eltern-chat.md` EC-3 und
`termine-erfragen.md` TER-3. Der Aufrufer übergibt die Chat-Identität als Teil
des Funktions-Eingangs (WZE-1).

*Tickets:* #474

## WZE-4 — Lesen über die Essens-Buddy-Schnittstelle
Die Funktion liest die Wünsche **ausschließlich** über die Essens-Buddy-
Wünsche-Schnittstelle (`essen.md` ESSEN-15, `GET /api/v1/essen/wuensche`),
nie über Datei-Zugriff (APP-3). Der HTTP-Client folgt dem geteilten
HTTP-Client-Pattern (`conventions/http-client.md` CLIENT-1) mit Origin
`essen_origin_url` (EC-15, neuer Origin-Eintrag mit diesem Spec-PR).

*Test-Implikation:* der Skill kontaktiert nur `essen_origin_url`, nie das
Dateisystem; mit einem Transport-Stub für `GET /api/v1/essen/wuensche`
liefert er deterministische Tests ohne echten Buddy-Prozess.

*Tickets:* #474

## WZE-5 — Antwort-Format: kategorie-gruppiert, kurze Lesbarkeit
Die Antwort listet die Wünsche **gruppiert nach Kategorie** (`gericht`,
`obst_gemuese`, `brotbelag`, `sonstiges`, in dieser festen Reihenfolge —
Gerichte zuerst, weil sie typischerweise die zentrale Mahlzeit-Planung
betreffen). Innerhalb einer Kategorie ist die Reihenfolge chronologisch
(`erstellt_am` aufsteigend). Jeder Wunsch erscheint als eine Zeile mit dem
`label`; Quelle (`kind` / `eltern`) wird nicht im Text mitgeschrieben, weil sie
in V1 wenig Interpretations-Wert hat (E-ESSEN-8).

Beispiel-Format (Telegram-Plain-Text, keine Markdown-Spezifik):

```
Wünsche:

Gerichte:
- Lasagne
- Pancakes

Obst & Gemüse:
- Apfel
- Karotten

Brotbelag:
- (keine)

Sonstiges:
- Milch
- Kakao
```

Leere Kategorien werden mit `- (keine)` markiert, damit klar ist, dass die
Kategorie existiert und gefragt wurde. Komplett leere Liste → siehe WZE-6.

*Test-Implikation:* eine Liste mit Wünschen aus drei der vier Kategorien
rendert in genau dieser Sortier-Reihenfolge; die vierte (leere) Kategorie
trägt `- (keine)`.

*Tickets:* #474

## WZE-6 — Leere Liste: ehrliche Meldung statt leerer Antwort
Liefert der Essens-Buddy eine leere Wunsch-Liste (`{ "wuensche": [] }`),
postet die Funktion eine **ehrliche** Meldung („Aktuell sind keine Wünsche in
der Liste."), keine kategorisierte Tabelle mit vier `(keine)`-Zeilen — leer
ist leer. Das Ergebnis-Signal an den Aufrufer ist „leer" (WZE-1).

*Test-Implikation:* mit einer leeren Wunsch-Liste-Antwort des Buddys postet
der Skill genau diese eine Zeile, nicht das Kategorie-Schema aus WZE-5.

*Tickets:* #474

## WZE-7 — Essens-Buddy nicht erreichbar: ehrliche Grenze
Scheitert der Aufruf von `GET /api/v1/essen/wuensche` (Connection-Fehler,
Timeout, 5xx vom Buddy), postet die Funktion eine **ehrliche** Grenze („Die
Wunsch-Liste ist gerade nicht erreichbar, bitte später nochmal versuchen.")
und liefert dem Aufrufer das Signal „nicht_erreichbar" (WZE-1, EC-7). Die
Funktion **erfindet keine Wünsche** und hält **keinen eigenen Cache** vor
(APP-3, Out-of-Scope V1).

*Test-Implikation:* mit einem Transport-Stub, der einen Verbindungsfehler
wirft, postet der Skill die Nicht-erreichbar-Meldung und liefert das passende
Signal; er macht keinen zweiten Aufruf, keine Annahmen.

*Tickets:* #474

## WZE-8 — Registrierung (TASK-7) und Tests
Der Skill wird in `build_catalog` registriert (TASK-7), hinter einem Guard auf
**zwei** Abhängigkeiten — `essen_origin_url` und `family_group_chat_id_getter`.
Fehlt eine, erscheint die Aufgabe **nicht** im Katalog (TASK-7-Guard-Pattern
analog TER, RPS).

Pflicht-Tests (EC-17, analog TER-Test-Set):

- Katalog enthält „Wünsche zeigen" **genau dann**, wenn beide Abhängigkeiten
  gesetzt sind (Guard).
- Nicht-Mitglied (`is_member_fn` → false) → „abgelehnt", **kein** API-Aufruf
  (WZE-2).
- Happy-Path: drei Wünsche aus zwei Kategorien → Skill ruft
  `GET /api/v1/essen/wuensche` (Transport-Stub, CLIENT-1) → postet
  kategorie-gruppierte Zusammenfassung im Eingangs-Chat (WZE-3/WZE-5).
- Leere Liste → Skill postet die WZE-6-Meldung, Signal „leer".
- Transport-Fehler → Skill postet die WZE-7-Meldung, Signal
  „nicht_erreichbar", kein Cache, kein Retry.
- APP-3: der Skill ruft die API, nicht die Datei (kein direkter
  `essen/wuensche.json`-Zugriff).

*Tickets:* #474

---

## E-WZE-1 — Trigger-agnostische Funktion (Pattern aus TER, CAV, KAV, FAA)
*Datum:* 2026-06-09 · Die Funktion kennt ihren Aufrufer nicht, sie kennt nur
ihren Eingang und ihre Wirkung — derselbe Vertrag wie
`termine-erfragen.md` E-TER-1, `ca-verteilung.md` E-CAV-1,
`kalender-verbinden.md` E-KAV-1, `familie-anlegen.md` E-FAA-1. Das hält die
Funktion austauschbar und prüfbar; ein anderes Interface (z. B. eine Web-Seite
oder ein zweiter Messenger) könnte sie genauso aufrufen, ohne dass die
Funktion das wüsste. **Verworfen:** Trigger-Logik (Telegram-Kommando-Parsing,
Privatchat-Session) in die Funktion zu ziehen — würde die TER/RPS-Linie
brechen und einen vierten Andock-Pfad aufmachen.

## E-WZE-2 — Kategorie-feste Sortier-Reihenfolge, nicht alphabetisch
*Datum:* 2026-06-09 · Die feste Reihenfolge (Gerichte → Obst&Gemüse →
Brotbelag → Sonstiges) folgt dem **Wert** für den Eltern-Kontext, nicht der
alphabetischen Ordnung: Gerichte zuerst, weil sie die zentrale
Mahlzeit-Entscheidung tragen; danach die Lebensmittel-Kategorien in
Einkaufs-typischer Reihenfolge. **Verworfen:** alphabetische Sortierung (würde
„Brotbelag" vor „Gerichte" stellen und die Mahlzeit-zentrale Lese-Ordnung
brechen).
