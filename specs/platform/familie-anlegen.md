# Familie anlegen — Spec     (ID-Präfix: FAA)

> Status: V1 · Refs #60

Damit eine Familie ihre Mitglieder in die Registry (`familie.md` FAM-6) bekommt,
ohne die Datei von Hand zu pflegen, definiert diese Spec **Familie anlegen als
aufrufbare Funktion**: Aufgerufen, führt sie ein Familienmitglied im
Privatchat durch die Anlage **einer** Person und ergänzt die Person nach
Bestätigung in `familie.json`. Die Funktion ist **trigger-agnostisch**
(E-FAA-1): wer sie aufruft — der Onboarding-Flow, ein konversationeller Aufruf
über den Eltern-Chat (`eltern-chat.md` EC-8) oder ein Slash-Aufruf — ist nicht
Teil ihres Vertrags.

**V1-Scope:** die Anlage **einer oder mehrerer** Personen je Aufruf
(„noch jemand?"-Schleife, FAA-9) · die Konversation läuft im Privatchat mit
dem Aufrufer (analog `eltern-chat-onboarding.md` ONB-3) · deterministisch,
ohne LLM, hart-codierter Ablauf · Schreiben pro Person erst nach
Bestätigungswort (`eltern-chat.md` E-EC-7) · nur Familienmitglieder im Sinne
von `familie.md` FAM-2 (Erwachsene und Kinder).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): Ändern und Löschen
bereits angelegter Personen (E-FAA-2) · weitere Personen, die keine
Familienmitglieder sind (E-FAA-3; `familie.md` OPEN-FAM-A) · die Einbettung
in den Onboarding-Flow (eigene additive Spec, eigener PR) · eine
LLM-fähige konversationelle Trigger-Schicht jenseits der EC-8-Aufgabe
(FAA-12 deckt den V1-Trigger; eine spätere, freier formulierte Auslöse-
Konvention ist eigene Spec).

## 1. Die Funktion

### FAA-1 — Aufruf-Schnittstelle
Die Funktion ist eine klar abgegrenzte, **aufrufbare Funktion** mit definierter
Schnittstelle. **Eingang:** der Telegram-Privatchat des Aufrufers (Chat-ID
und Telegram-User-ID), die ID der gebundenen Familien-Gruppe (`eltern-chat.md`
EC-2) und ein Zugriff auf die Familien-Registry über deren Schnittstellen
(`familie.md` FAM-7 lesen, FAM-11 schreiben). Familienspezifische Werte
(Foto-Verzeichnis, Profilbild-Max-Kante) holt die Funktion über die
Registry-Schnittstelle aus den Settings (`familie.md` FAM-9), **nicht** als
separate Aufruf-Parameter — der Aufrufer muss diese Werte nicht duplizieren,
und die Funktion sieht immer den Stand der Familie, die sie gerade bedient.
**Wirkung:** nach erfolgreichem Durchlauf sind **eine oder mehrere** neue
Personen in der Registry ergänzt (jede Person für sich bestätigt und atomar
über FAM-11 geschrieben, FAA-7/FAA-8) und — falls der Aufrufer pro Person
ein Foto geschickt hat — die Bilddateien im Foto-Verzeichnis (FAM-9) abgelegt.
**Ausgang:** ein Ergebnis-Signal an den Aufrufer mit der Liste der vergebenen
`id`s der angelegten Personen (kann leer sein, wenn der Aufrufer die erste
Anlage abgebrochen hat). Die Funktion kennt ihren Aufrufer nicht — sie weiß
nicht, ob ein Onboarding-Flow, ein konversationeller Aufruf oder ein anderer
Auslöser sie gestartet hat (E-FAA-1).

*Tickets:* #60

### FAA-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-Mitgliedschaft,
analog `eltern-chat.md` EC-2. Ist er es nicht, bricht die Funktion mit einem
ablehnenden Ergebnis-Signal ab und schreibt nichts. Die Prüfung liegt **bei
der Funktion**, nicht beim Aufrufer — sonst hinge die Berechtigungslogik am
Trigger und die Funktion verlöre ihre Trigger-Agnostik (E-FAA-1).

*Tickets:* #60

## 2. Konversation

### FAA-3 — Datenerfassung in fester Reihenfolge
Die Funktion erfragt die Daten einer Person im Privatchat in dieser
Reihenfolge — ein Wechsel der Reihenfolge ist eine Spec-Änderung, kein
Implementierungs-Detail:

1. **Art** (Pflicht): Erwachsene oder Kind (`familie.md` FAM-2). Die Antwort
   muss erkennbar auf eine der beiden Arten zeigen; sonst wird die Frage
   wiederholt.
2. **Name** (Pflicht): Anzeigename (`familie.md` FAM-3 `name`). Nicht-leer;
   sonst wird die Frage wiederholt.
3. **Profilfoto** (optional): als Telegram-Foto-Nachricht oder explizit
   übersprungen. Format und Speicherort siehe FAA-6.
4. **Ring-Farbe** (Pflicht): die Funktion schlägt eine Farbe vor (FAA-4); der
   Aufrufer übernimmt sie oder übersteuert sie mit einem Wort aus der Palette
   `familie.md` FAM-4 (`blue, orange, green, red, purple, teal, gray`). Ein
   Wort außerhalb der Palette wird abgelehnt und die Frage wiederholt.
5. **E-Mail** (optional, nur bei Art „Erwachsene"; bei Kindern entfällt der
   Schritt, `familie.md` FAM-3): syntaktisch gültige E-Mail-Adresse oder
   explizit übersprungen.
6. **Telegram-ID** (optional, beide Arten): eine Zahl oder explizit
   übersprungen. Die Funktion bietet die Telegram-User-ID des Aufrufers als
   Default an, wenn der Aufrufer signalisiert, dass die anzulegende Person er
   selbst ist (etwa über ein „ich"-Signal in der Konversation — der konkrete
   Wortlaut ist Implementierungs-Detail). Eine eingetragene `telegram_id`
   muss eine Telegram-User-ID sein und darf nicht bereits einer anderen Person
   in `familie.json` zugeordnet sein (FAA-10).

Pflicht-Schritte ohne gültige Antwort wiederholen die Frage. Optionale
Schritte können übersprungen werden, indem der Aufrufer ein erkennbares
Überspring-Signal sendet — der konkrete Wortlaut ist Implementierungs-Detail.

*Tickets:* #60

### FAA-4 — Ring-Farbe vorschlagen, Aufrufer kann übersteuern
Die Funktion schlägt für die neue Person die nächste freie Farbe aus der
Palette `familie.md` FAM-4 in der dortigen Reihenfolge vor — eine Farbe gilt
als belegt, wenn sie bereits einer Person in `familie.json` zugeordnet ist.
`gray` bleibt in der Vorschlags-Reihenfolge zuletzt, weil `familie.md` FAM-4
es als Farbe „ohne feste Zuordnung" führt. Der Aufrufer kann den Vorschlag mit
einem Palette-Wort übersteuern; die Funktion akzeptiert nur Worte aus der
Palette. Sind alle Farben der Palette belegt, fällt der Vorschlag auf `gray`
zurück (mehr Personen als Farben ist eine Spec-Änderung — siehe `familie.md`
FAM-4).

*Tickets:* #60

### FAA-5 — ID-Vergabe durch den Server
Die `id` (`familie.md` FAM-3 Pflicht, „stabil") vergibt der Server (FAM-12);
Form und Kollisionsvermeidung folgen IDENT-1. Der Aufrufer sieht und wählt
sie nicht. Die `id` wird nach dem Schreiben (FAA-8) nicht mehr geändert.

*Tickets:* #60

### FAA-6 — Profilbild-Annahme
Ein Foto wird über Telegram **entweder** als Foto-Nachricht **oder** als
Datei-Anhang mit Bild-MIME entgegengenommen. Akzeptierte MIME-Typen sind
`image/jpeg` und `image/png`; andere Anhänge weist die Funktion ab (FAA-10).
Diese Lockerung gegenüber „nur Foto-Nachricht" ist gewollt, weil einige Geräte
(z. B. iOS, je nach Workflow) Bilder als Dokument-Anhang versenden — der
Aufrufer soll nicht an der Anhang-Form scheitern.

Die Funktion lädt die Bilddatei aus dem Telegram-Update herunter und sendet
sie via FAM-13 (Multipart-Upload) an die Familie-Komponente. Speicherort und
Dateiname werden serverseitig entschieden (Server-Logik FAM-13). Bei einer
Telegram-Foto-Nachricht wählt die Funktion unter den angebotenen Größen die
größte, deren längste Kante den Tuning-Wert „Profilbild-Max-Kante" aus
`familie.md` FAM-9 nicht überschreitet. Bei einem Datei-Anhang nimmt die
Funktion die Datei wie gesandt und prüft die Kantenlänge gegen denselben
Tuning-Wert (FAA-10).

Hat der Aufrufer das Foto übersprungen, entfällt der FAM-13-Aufruf — `foto`
bleibt ungesetzt (`familie.md` FAM-5 lässt das ausdrücklich zu).

*Tickets:* #60

### FAA-7 — Zusammenfassung und Bestätigungswort
Vor dem Schreiben fasst die Funktion alle erfassten Felder im Privatchat
zusammen und fordert eine Bestätigung nach dem Pattern aus `eltern-chat.md`
E-EC-7. Erst eine erkannte Bestätigung schaltet das Schreiben (FAA-8) frei.
Antwortet der Aufrufer nicht bestätigend (z. B. `nein`, `abbrechen` oder eine
inhaltliche Korrektur), wird **nicht** geschrieben — die Funktion endet ohne
Wirkung auf `familie.json`. Die Spec klopft den Wortlaut der
Zusammenfassungs- und Abbruch-Nachrichten nicht fest; das ist
Implementierungs-Detail.

*Tickets:* #60

## 3. Schreiben

### FAA-8 — Anlegen über zwei HTTP-Calls (Person + Foto)
Nach Bestätigung (FAA-7) legt die Funktion die Person über FAM-12 an; der
Server vergibt dabei die `id` (FAA-5). Hat der Aufrufer ein Foto gesendet,
folgt danach ein separater Foto-Upload über FAM-13. Person und Foto sind seit
C4 zwei getrennte HTTP-Calls — der Ablauf ist damit **nicht** atomar über
beide hinweg. Schlägt FAM-13 fehl, bleibt die Person in der Registry bestehen
(Foto fehlt). Die Funktion loggt das und meldet dem Aufrufer Erfolg-mit-Hinweis
(„Person angelegt, Foto konnte nicht hochgeladen werden").

*Tickets:* #60

## 4. Lebenszyklus

### FAA-9 — Mehr-Personen-Schleife; Privatchat-Session

**(a) „Noch jemand?"-Schleife.** Nach erfolgreichem Bestätigen (FAA-7) und
Schreiben (FAA-8) **einer** Person fragt die Funktion im Privatchat, ob eine
weitere Person angelegt werden soll. Eine Bestätigung nach `eltern-chat.md`
E-EC-7 führt zurück zu FAA-3 Schritt 1 (Art) für die nächste Person; eine
nicht-bestätigende Antwort beendet die Funktion und liefert das Ergebnis-Signal
(FAA-1) mit der Liste aller in diesem Aufruf angelegten `id`s. Jede Person
durchläuft FAA-3..8 in voller Länge — kein gemeinsamer Zustand zwischen
Personen außer der Tatsache, dass `familie.json` zwischen den Personen jeweils
um die zuletzt bestätigte Person gewachsen ist (FAA-8 atomar je Person).

**(b) Privatchat-Session.** Die Konversation folgt dem Session-Muster aus
`conventions/privatchat-session.md` (SESS-1..SESS-4). Folge für FAA: stürzt
der Prozess während eines laufenden Aufrufs ab oder wird er neu gestartet,
ist der Funktions-Aufruf beendet, die Anlage der aktuell laufenden Person
verloren und die Schleife (a) wird nicht fortgesetzt (SESS-2). Bereits durch
FAA-8 in `familie.json` geschriebene Personen aus diesem oder früheren
Aufrufen bleiben unberührt.

*Tickets:* #60

### FAA-10 — Fehlerfälle
Die Funktion reagiert auf erkennbare Eingabe- und Umweltfehler, ohne den
Aufrufer im Stich zu lassen und ohne fehlerhafte Daten zu schreiben:

- **Anhang ohne Bild-MIME** (Dokument oder anderer MIME außerhalb
  `image/jpeg` / `image/png`): die Funktion weist den Anhang ab und bietet
  erneut die Schritt-3-Frage an.
- **Foto zu groß** (Telegram-Foto: alle angebotenen Größen überschreiten den
  FAM-9-Tuning-Wert „Profilbild-Max-Kante"; oder Datei-Anhang: längste Kante
  überschreitet diesen Wert): die Funktion weist das Foto ab und bietet
  erneut die Schritt-3-Frage an.
- **Name leer oder nur Whitespace:** die Funktion wiederholt die Namens-Frage.
- **Ring-Farbe außerhalb der Palette:** die Funktion wiederholt die
  Farb-Frage.
- **Telegram-ID schon vergeben** (eine andere Person in `familie.json` hat
  diese `telegram_id` bereits): die Funktion weist die ID ab und bietet
  erneut die Schritt-6-Frage an — eine Telegram-ID bildet **eine** Person ab
  (`familie.md` FAM-3).
- **Disk-Schreibfehler** (FAA-8 schlägt fehl, z. B. Disk voll oder
  Schreibrecht entzogen): die Funktion signalisiert den Misserfolg an den
  Aufrufer und schreibt weder die Person noch das Foto endgültig (vgl.
  FAA-8 letzter Satz).

Die Spec klopft den Wortlaut der Fehler-Nachrichten **nicht** fest — das ist
Implementierungs-Detail.

*Tickets:* #60

## 5. Trigger

### FAA-12 — Trigger als Eltern-Chat-Aufgabe (V1)
Solange die Konvention für eine LLM-fähige, freier formulierte konversationelle
Trigger-Schicht noch nicht spezifiziert ist, läuft der V1-Trigger der Funktion
als **Aufgabe im Aufgaben-Katalog des Eltern-Chats** (`eltern-chat.md` EC-8) —
dasselbe Muster wie für die CA-Verteilung (`ca-verteilung.md` CAV-6). Die
Aufgabe nimmt das Auslöse-Wort eines Familien-Gruppen-Mitglieds entgegen, ruft
die Funktion (FAA-1) im **Privatchat** des Aufrufers auf (analog
`eltern-chat-onboarding.md` ONB-3 — der Anlage-Dialog gehört nicht in die
Familien-Gruppe) und liefert das Ergebnis-Signal (FAA-1) an den Aufrufer
zurück.

Die Aufgabe ist **schreibend** (EC-10, `WriteTask`): über die Funktion landen
neue Personen in `familie.json`. Das EC-10-Bestätigungs-Gate vor dem
Aufgaben-Start ist redundant mit FAA-7 (das jede einzelne Person bestätigen
lässt), aber Pattern-treu — die Spec macht hier keine Ausnahme.

Die Berechtigung der Aufgabe deckt sich mit FAA-2 (Live-Mitgliedschaft in der
Familien-Gruppe): die Aufgabe leitet die Live-Prüfung an die Funktion durch,
die ihre eigene Gate-Logik behält und der Trigger-Agnostik (E-FAA-1) nicht
unterläuft. Die Aufgabe ist additiv im Sinne von EC-8 — der bestehende Katalog
bleibt unberührt.

*Tickets:* #60

## 6. Tests

### FAA-11 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec mit Code-Verhalten hat einen automatisierten Test
(analog `familie.md` FAM-10 und `eltern-chat-onboarding.md` ONB-9),
reproduzierbar und ohne Netz — Telegram wird durch eine kontrollierte
Doppelung ersetzt. Mindest-Abdeckung:

- **FAA-1** — Aufruf mit minimalem Eingang gibt nach Durchlauf das
  Ergebnis-Signal mit der Liste der vergebenen `id`s zurück (eine `id` bei
  einer Person, mehrere `id`s bei einer Mehr-Personen-Schleife); Aufruf mit
  sofortigem Abbruch der ersten Person (FAA-7) gibt eine leere Liste zurück.
- **FAA-2** — Aufruf eines Nicht-Familien-Mitglieds wird abgelehnt;
  `familie.json` bleibt unverändert.
- **FAA-3** — Reihenfolge der Fragen wird eingehalten; eine leere Antwort auf
  einen Pflicht-Schritt wiederholt die Frage; bei Art „Kind" wird die
  E-Mail-Frage übersprungen; bei „ich"-Signal in Schritt 6 wird die
  Telegram-User-ID des Aufrufers als Default vorgeschlagen.
- **FAA-4** — Vorschlag ist die erste freie Palette-Farbe; Override mit
  Palette-Wort wird übernommen; Wort außerhalb der Palette wird abgelehnt.
- **FAA-5** — Slug aus Namen wird vergeben; Kollision führt zu `-2`-Suffix.
- **FAA-6** — Telegram-Foto-Nachricht landet als `<id>.jpg`, PNG-Datei-Anhang
  als `<id>.png` im Foto-Verzeichnis; Auswahl unter den Telegram-Größen
  respektiert die FAM-9-Max-Kante; ein Datei-Anhang über der Max-Kante wird
  abgewiesen; ein Datei-Anhang ohne Bild-MIME wird abgewiesen; übersprungenes
  Foto lässt `foto` in `familie.json` ungesetzt.
- **FAA-7** — Bestätigungswort nach E-EC-7 schaltet das Schreiben frei; eine
  nicht-bestätigende Antwort schreibt nicht.
- **FAA-8** — neue Person wird additiv ergänzt, bestehende Personen bleiben
  bytegleich; ein simulierter Schreibfehler hinterlässt weder Eintrag noch
  Foto.
- **FAA-9** — nach Bestätigung einer Person fragt die Funktion „noch
  jemand?"; eine Bestätigung führt zur nächsten Personen-Anlage mit FAA-3
  Schritt 1, eine nicht-bestätigende Antwort beendet die Funktion mit der
  Liste der angelegten `id`s; ein während des Ablaufs verlorener
  Prozess-Zustand beendet die Funktion, bereits committete Personen aus
  diesem oder früheren Aufrufen bleiben in `familie.json`.
- **FAA-10** — die fünf in FAA-10 genannten Fehlerklassen führen zu den dort
  beschriebenen Reaktionen, ohne `familie.json` zu mutieren.
- **FAA-12** — die EC-8-Aufgabe wird vom Catalog gefunden und ist als
  `WriteTask` registriert; sie ruft FAA mit den korrekten Parametern auf
  (Privatchat-Chat-ID und User-ID des Aufrufers, gebundene Familien-Gruppe,
  Registry-Pfad) und reicht das Ergebnis-Signal an den Aufrufer zurück; ein
  Aufruf aus dem Familien-Gruppen-Chat adressiert die Anlage im Privatchat,
  nicht in der Gruppe.

*Tickets:* #60

---

## Offene Punkte

- **OPEN-FAA-A — Konversationeller Aufruf über den Eltern-Chat-Katalog.**
  *Erfüllt durch FAA-12 (V1: EC-8-Aufgabe).* Der Bedarf, ein Familienmitglied
  per Satz im laufenden Betrieb nachzutragen, ist heute belegt; die V1-Form
  ist die EC-8-Aufgabe (siehe FAA-12 + E-FAA-4). Offen bleibt eine spätere,
  LLM-fähige konversationelle Trigger-Schicht, die ohne den festen
  Aufgaben-Namen auskommt — eigene Spec, sobald sie sich einer Konvention für
  freier formulierte Auslöser hängen kann. FAA selbst ist trigger-agnostisch
  (E-FAA-1) und ändert sich dafür nicht.

## Entscheidungen

### E-FAA-1 — Funktion ist trigger-agnostisch
*Datum:* 2026-05-23

„Familie anlegen" wird als eigenständige, **trigger-agnostische** Funktion
definiert — nicht als fest verdrahteter Schritt eines Onboarding-Ablaufs. Die
Funktion kennt ihren Aufrufer nicht; ihr Vertrag ist FAA-1.

**Verworfen:** die Anlage direkt in den Onboarding-Flow zu verdrahten. Dann
wäre sie nur über den Flow erreichbar, nicht einzeln testbar, und jeder
spätere Aufrufer (konversationeller Aufruf, separater Slash-Aufruf, ein
Display-Onboarding) müsste die Anlage-Logik kopieren oder den
Onboarding-Code aufschwellen lassen. Das ist dasselbe Eigentümer/Nutzer-
Muster wie in `ca-verteilung.md` E-CAV-1 und `plan.md` E-PLAN-1. Die
Einbettung in den Onboarding-Flow ist eine eigene additive Spec, eigener PR.

### E-FAA-2 — V1 nur Anlegen
*Datum:* 2026-05-23

V1 deckt ausschließlich das **Anlegen** einer Person ab. Ändern (Foto
austauschen, Mail nachtragen, Farbe wechseln) und Löschen sind eigene
Funktionen, eigene Tickets, eigene Specs.

**Verworfen:** Ändern und Löschen in dieselbe Funktion zu legen. „Nichts auf
Vorrat" (CLAUDE.md §6) — es gibt heute keinen belegten V1-Bedarf für
Ändern/Löschen über den Chat-Kanal; `familie.md` FAM-6 lässt Datei-Edit
weiterhin zu („V1: Datei von Hand pflegen"). Eine Anlege-Funktion hat zudem
einen anderen Bestätigungs- und Identitäts-Pfad als eine Änderungs-Funktion
(welche bestehende Person ist gemeint, welche Felder dürfen welche Aufrufer
ändern); diese Fragen wollen wir nicht in der Anlage-Spec vorwegnehmen.

### E-FAA-3 — Nur Familienmitglieder
*Datum:* 2026-05-23

V1 legt ausschließlich Familienmitglieder im Sinne von `familie.md` FAM-2 an
(Erwachsene und Kinder). Weitere Personen (`familie.md` OPEN-FAM-A:
Babysitter, Spielfreunde, Großeltern) sind ausgeklammert.

**Verworfen:** schon jetzt einen zweiten Personen-Typ in der Konversation
anzubieten. `familie.md` OPEN-FAM-A markiert „weitere Personen" ausdrücklich
als nicht-V1, ohne belegten Bedarf — „Nichts auf Vorrat" (CLAUDE.md §6).
Sobald OPEN-FAM-A geklärt ist, ergänzt die FAA-Spec einen zweiten
Personen-Typ; die Konversations-Struktur (FAA-3) ist dafür offen.

### E-FAA-4 — Trigger der V1-Anbindung: eine Eltern-Chat-Aufgabe
*Datum:* 2026-05-24

Solange eine LLM-fähige konversationelle Trigger-Konvention noch nicht
spezifiziert ist (vgl. OPEN-FAA-A), ist der V1-Trigger der Funktion eine
**Aufgabe im Aufgaben-Katalog des Eltern-Chats** (FAA-12, EC-8) — analog
`ca-verteilung.md` E-CAV-3.

**Verworfen:** (1) den Trigger direkt in den Onboarding-Flow oder einen
Slash-Befehl zu verdrahten — beides bricht E-FAA-1 (Trigger-Agnostik) und
macht die Funktion abhängig von einer einzelnen Aufrufer-Spur. (2) eine
eigene, freiere natürlichsprachige Trigger-Schicht jetzt schon — diese
Konvention fehlt noch, sie ist eine eigene Spec, und die EC-8-Aufgabe liefert
zwischenzeitlich denselben Effekt ohne Tippbefehl. Eine spätere Erweiterung
nimmt die Aufgabe nicht weg, sondern setzt einen zweiten Aufrufer neben sie
— die Funktion (FAA-1) bleibt unverändert.

---

## Querverweise

- `familie.md` FAM-2 (zwei Arten von Personen), FAM-3 (Personen-Eigenschaften),
  FAM-4 (Ring-Palette), FAM-5 (Profilfoto optional), FAM-6 (Registry-Datei
  mit Personen + Settings), FAM-7 (Lese-Schnittstelle), FAM-9
  (Konfigurationswerte inkl. Profilbild-Max-Kante, aus Registry-Settings),
  FAM-10 (Tests), FAM-11 (Schreib-Schnittstelle).
- `eltern-chat.md` EC-2 (Berechtigung über Gruppen-Mitgliedschaft), EC-8
  (Aufgaben-Katalog — Heimat von FAA-12), EC-9 (lesende Aufgaben), EC-10
  (schreibende Aufgaben nur nach Bestätigung — Pattern der FAA-12-Aufgabe),
  E-EC-7 (Bestätigungswort-Pattern).
- `eltern-chat-onboarding.md` ONB-3 (Privatchat als Eingabekanal), ONB-9
  (Test-Doppelung für Telegram), E-ONB-1 (deterministischer Ablauf ohne LLM).
- `ca-verteilung.md` CAV-1 (Funktions-Muster), E-CAV-1 (Onboarding-Funktionen
  sind trigger-agnostisch).
