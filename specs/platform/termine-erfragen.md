# Termine erfragen — Spec     (ID-Präfix: TER)

> Status: V1 · Refs #143

Damit ein Elternteil die anstehenden Familien-Termine im Eltern-Chat abfragen
kann, ohne den Wochenplan am Display öffnen oder selbst in den Google-Kalender
schauen zu müssen, definiert diese Spec **Termine erfragen als aufrufbare
Funktion**: Aufgerufen, liest sie die Termine eines Zeitraums aus dem
Familien-Kalender — als Konsument der Plan-Buddy-Termin-Schnittstelle
(`plan.md` PLAN-22) — und antwortet dem Familienmitglied im Eltern-Chat mit
einer lesbaren Zusammenfassung. Es ist eine **lesende** Aufgabe (EC-9): die
Funktion verändert keine Familien-Daten, daher kein Bestätigungs-Gate. Die
Funktion ist **trigger-agnostisch** (E-TER-1 analog `ca-verteilung.md`
E-CAV-1, `kalender-verbinden.md` E-KAV-1, `familie-anlegen.md` E-FAA-1): wer
sie aufruft — eine Eltern-Chat-Aufgabe, ein späteres anderes Interface — ist
nicht Teil ihres Vertrags.

**V1-Scope:** das Erfragen von Familien-Terminen über den Eltern-Chat-Bot ·
die Funktion als trigger-agnostischer Konsument der Plan-Buddy-Termin-
Schnittstelle (`plan.md` PLAN-22, `GET /api/v1/plan/termine`) · ein
hart-codiertes Datums-Vokabular für den Zeitraum (TER-4) mit Default
„heute + 7 Tage" · die Antwort als hart-codierte, tagesgruppierte
Text-Zusammenfassung in dem Chat, in dem die Frage gestellt wurde (Gruppe
oder Privatchat) · der Trigger als Eltern-Chat-Aufgabe (EC-8, analog
`ca-verteilung.md` CAV-6 / `familie-anlegen.md` FAA-12).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Termine setzen** — separate Funktion `termine-setzen` (ID-Präfix TES),
  Schreibe-Task mit Bestätigungs-Gate (EC-10), Ticket #144.
- **Termine aus Foto eines Plans erfassen** — eigene Funktion (TAB),
  Schreibe-Task auf Bild-Eingabe, separates Ticket.
- **Wiederkehrende Termin-Regeln pflegen** — die Anbindung löst
  wiederkehrende Termine in Einzel-Vorkommen auf (`plan.md` PLAN-17); ein
  Pflegen der Regeln (RRULE) ist nicht V1.
- **Stichwort-/Personen-/Filter-Suche** über die Zeitraum-Auswahl hinaus
  („zeig mir alle Klettern-Termine", „nur Termine von Papa") — V1 liefert
  den Zeitraum vollständig; eine Filter-Schicht braucht ein eigenes Ticket,
  sobald belegter Schmerz da ist.
- **Eigener Cache** in dieser Funktion — die Plan-Buddy-Schnittstelle ist
  die einzige Wahrheits-Quelle (APP-3, CLAUDE.md §6), jeder Aufruf geht
  frisch dorthin.
- **Plan-Buddy-Fehlbedienung-Reparatur** — fällt die Termin-Schnittstelle
  aus (PLAN-23), antwortet diese Funktion ehrlich (TER-7); eine eigene
  Diagnose oder Self-Healing-Logik liegt nicht in dieser Spec.

## 1. Die Funktion

### TER-1 — Termine erfragen ist eine aufrufbare Funktion
Termine erfragen ist eine klar abgegrenzte, **aufrufbare Funktion** mit
definierter Schnittstelle. **Eingang:** die Telegram-Chat-Identität, in der
der Aufruf entstand (Gruppen-Chat-ID oder Privatchat-ID des Aufrufers —
Berechtigungs-Verortung, nicht Sende-Ziel), die Telegram-User-ID des
Aufrufers (für die Berechtigung TER-2), sowie ein Zeitraum als Start-Tag
(ISO-Datum) und Tagesanzahl (TER-4). **Wirkung:** die Funktion verändert
**keine** Familien-Daten; sie liest aus der Plan-Buddy-Termin-Schnittstelle
(TER-5). **Ausgang:** ein **User-tauglicher Antwort-Text** als
Tool-Result-String an den Aufrufer (EC-29). Der Aufrufer — im V1-Trigger
die Eltern-Chat-Aufgabe — gibt diesen Text als Tool-Result an den
Agent-Loop zurück, das LLM formuliert die Bot-Nachricht und postet sie als
einzigen Schreibakt des Turns (EC-29). Der Tool-Result-Text trägt je nach
Fall die tagesgruppierte Termin-Liste (TER-9), die „leerer Zeitraum"-
Meldung (TER-8) oder die Nicht-erreichbar-Meldung (TER-7); der
**Berechtigungs-Bruch** (TER-2) löst eine Berechtigungs-Exception aus,
sodass der Agent-Loop den Fehler-Tool-Result-Block schreibt (`agent.py`
Fehlerpfad) und das LLM in der Antwort schweigt — die Funktion postet in
keinem Pfad selbst.

*Tickets:* #143, #551

### TER-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-
Mitgliedschaft, analog `eltern-chat.md` EC-2, `familie-anlegen.md` FAA-2 und
`kalender-verbinden.md` KAV-2. Ist er es nicht, wirft die Funktion eine
Berechtigungs-Exception (`BerechtigungError`, siehe #564,
`eltern-chat/skills/_errors.py`) und postet keine Antwort. Die Prüfung liegt
**bei der Funktion**, nicht beim Aufrufer — sonst hinge die
Berechtigungslogik am Trigger und die Funktion verlöre ihre Trigger-Agnostik
(E-TER-1).

*Tickets:* #143

## 2. Eingabe-Verstehen

### TER-3 — Antwort dort, wo die Frage kam (über das LLM)
Die Bot-Nachricht erscheint im selben Telegram-Chat, aus dem die Frage
kam. In der Familien-Gruppe (`eltern-chat.md` EC-3, EC-5) erscheint sie in
der Gruppe; im Privatchat erscheint sie im Privatchat. Das Senden übernimmt
der Agent-Loop: die Funktion returnt den Antwort-Text als Tool-Result, das
LLM trägt ihn in die Bot-Nachricht und postet ihn im laufenden Chat
(EC-29). Eine Termin-Frage ist **lesend** (EC-9) und die Antwort enthält
nur Termine, die der Familien-Kalender ohnehin allen Familienmitgliedern
zeigt — eine Privatchat-Pflicht analog `kalender-verbinden.md` KAV-3 ist
deshalb **nicht** nötig. Eine Privatchat-Session-Mechanik
(`conventions/privatchat-session.md` SESS-1..SESS-4) entfällt aus
demselben Grund: die Funktion führt keinen mehrstufigen Dialog, sie
beantwortet eine einzelne Frage.

*Tickets:* #143, #551

### TER-4 — Datums-Vokabular und Default
Die Funktion erkennt einen Zeitraum aus dem Anfrage-Text. Welcher
Zeitraum-Ausdruck zu welchem `(start, tage)`-Paar führt, ist hart-codiert
und kommt **nicht** vom LLM-Anbieter — sonst hinge die Datums-Auflösung an
der Anbieter-Wahl (analog `eltern-chat.md` EC-12, anbieter-unabhängige
Regeln).

Soll-Abdeckung (Mindest-Vokabular):

- **„heute"** → `start=heute`, `tage=1`.
- **„morgen"** → `start=heute+1`, `tage=1`.
- **„diese Woche"** → `start=heute`, `tage=` bis einschließlich des
  nächsten Sonntags (ISO-Wochenende), maximal 7.
- **„nächste Woche"** → `start=` nächster Montag (ISO-Wochenanfang),
  `tage=7`.
- **„die nächsten N Tage"** (1 ≤ N ≤ 31) → `start=heute`, `tage=N`.
- **explizites Kalenderdatum** (`DD.MM.` / `DD.MM.JJJJ` / „am D. \<Monat\>",
  z. B. „3.6.", „am 3. Juni") → `start=<dieses Datum>`, `tage=1`.
  **Jahres-Inferenz** ohne Jahresangabe: es gilt das **laufende Jahr**. Liegt
  das so bestimmte Datum **in der Vergangenheit** (< heute), löst die Funktion
  eine **gezielte Rückfrage** aus („Du meinst nächstes Jahr, oder?") statt
  blind das Folgejahr oder den Default anzunehmen — `eltern-chat.md` EC-22.
  Datumsbereiche („vom–bis", „am Wochenende") bleiben **Out-of-Scope V1**.
- **Default** (keine erkennbare Zeitangabe oder Anfragetext „was steht
  an", „welche Termine") → `start=heute`, `tage=7` (eine ganze Woche, Wochenstart s. u.).

Eine Anfrage mit einem **mehrdeutigen** Datums-Ausdruck (z. B. „nächsten
Freitag", wenn unklar ist, ob diese oder nächste Woche) löst eine **gezielte
Rückfrage** aus, statt blind zu raten — `eltern-chat.md` EC-22. Die Spec
normiert das **Soll** (welche Ausdrücke erkannt sein müssen, welcher Default
gilt); der konkrete Wortlaut der Rückfragen lebt im Code als hart-codierter
String.

Wochenstart-Anker für „diese/nächste Woche" und Default ist **Montag**, analog
`plan.md` PLAN-28 (`wochenstart: 0`).

*Tickets:* #143, #309

## 3. Konsumenten-Vertrag

### TER-5 — Termine aus der Plan-Buddy-Termin-Schnittstelle (PLAN-22)
Die Funktion holt die Termine ausschließlich über die Plan-Buddy-Termin-
Schnittstelle aus `plan.md` PLAN-22:

- **Methode:** `GET`.
- **Pfad:** `/api/v1/plan/termine` (URL-4-konform, Plural-Resource).
- **Query-Parameter:** `ab=<iso-datum>` (Start-Tag, der aus TER-4 ermittelte
  `start`) und `tage=<n>` (Anzahl Tage, der aus TER-4 ermittelte `tage`).
- **Antwort:** eine JSON-Liste von normalisierten Event-Objekten gemäß
  `plan.md` PLAN-17 (Felder: stabile `id`, `titel`, `beginn`, `ende`,
  `ganztags`, `person`); die Personen-Auflösung folgt PLAN-19.
- **Origin:** der konfigurierte Plan-Buddy-Origin (Loopback-Port aus
  `conventions/ports.md` PORT-2 bzw. eine per Eltern-Chat-Konfiguration
  übersteuerbare Origin-URL, siehe `eltern-chat.md` EC-15 `plan_origin_url`).

Die Funktion ruft den Google-Kalender **nicht direkt** auf — Termine fließen
ausschließlich über die Plan-Buddy-Schnittstelle (`plan.md` PLAN-22,
einseitige Abhängigkeit, `conventions/apps.md` APP-3). Die Funktion hält
**keinen eigenen Cache** der Antwort — jeder Aufruf geht frisch an
PLAN-22 (CLAUDE.md §6, keine zweite Wahrheit).

*Tickets:* #143

### TER-6 — Personen-Auflösung bleibt beim Plan-Buddy
Die Personen-Zuordnung eines Termins (`person`-Feld der PLAN-22-Antwort)
ist bereits durch den Plan-Buddy gemäß `plan.md` PLAN-19 aufgelöst
(Titel-Treffer schlägt Creator-E-Mail). Diese Funktion **verwendet** das
Feld, **interpretiert** es aber nicht neu — sie greift nicht selbst auf die
Familien-Registry zu (`familie.md`), um eine zweite Auflösung zu probieren.
Ist das Feld leer, bleibt der Termin in der Antwort ohne Personen-Bezug;
die Funktion fingiert keinen.

*Tickets:* #143

## 4. Fehler- und Leer-Pfade

### TER-7 — Plan-Buddy nicht erreichbar oder Schnittstelle nicht da
Erreicht die Funktion die Plan-Buddy-Termin-Schnittstelle nicht
(Verbindung schlägt fehl, HTTP-Status ≠ 200, Antwort nicht parsbar) oder
ist der Plan-Buddy gar nicht installiert (`plan.md` PLAN-23,
`conventions/apps.md` APP-2), **returnt einen hart-codierten, ehrlichen
Antwort-Text als Tool-Result** — sie erfindet keine Termine
(`eltern-chat.md` EC-7, EC-22). Der Tool-Result-Text benennt die fehlende
Fähigkeit in der Sprache der Familie („Der Wochenplan ist gerade nicht
erreichbar — ich kann gerade keine Termine zeigen, bitte gleich nochmal
probieren"); der konkrete Wortlaut lebt im Code, die Spec normiert das
Soll (Existenz einer Antwort + keine Halluzination + kein stiller Abbruch).
Das Posten der Bot-Nachricht erfolgt über den Agent-Loop (EC-29) — die
Funktion sendet auch im Fehlerpfad nicht selbst.

*Tickets:* #143, #551

### TER-8 — Leerer Zeitraum
Liefert die Plan-Buddy-Schnittstelle für den ermittelten Zeitraum eine
leere Liste, returnt die Funktion einen **hart-codierten Tool-Result-Text**
(„keine Termine in diesem Zeitraum"). Ein leerer Kalender ist kein Fehler —
der Tool-Result macht das explizit, damit das LLM (EC-29) eine ehrliche
Bot-Antwort formuliert und das Familienmitglied nicht „der Bot schweigt"
interpretiert.

*Tickets:* #143, #551

## 5. Ausgabe

### TER-9 — Tagesgruppierte, lesbare Antwort
Die Funktion **baut** die Termin-Liste hart-codiert: **nach Tagen
gruppiert** in chronologischer Reihenfolge. Pro Tag erscheint ein
Tages-Kopf (Wochentag + Datum, Sprache deutsch analog
`conventions/urls.md` URL-7) und darunter je Termin **eine Zeile** mit —
falls vorhanden — Beginn-Uhrzeit, Titel und Personen-Bezug (aus `person`,
TER-6); ganztägige Termine tragen den Hinweis „ganztägig" statt einer
Uhrzeit. Mehrtages-Termine (`plan.md` PLAN-14) erscheinen **genau einmal**
unter dem Tages-Kopf ihres ersten Tages im erfragten Zeitraum, mit Hinweis
auf die Spanne — nicht je Tag wiederholt; die Mehrtages-Gruppierung
erkennt die Funktion an der stabilen `id` (PLAN-17/PLAN-14).

Der konkrete Wortlaut (Tages-Kopf-Format, Trennzeichen, Zeit-Format) lebt
im Code als hart-codierter String; die Spec normiert das **Soll** (welche
Felder, welche Reihenfolge, eine Zeile je Termin, keine Wiederholung von
Mehrtages-Spannen). **Dieser hart-codierte Listen-Block ist
trust-/anbieter-kritisch** — `eltern-chat.md` EC-12 (anbieter-unabhängige
Regeln); die Anbieter-Wahl darf das Erscheinungsbild der Termin-Liste
nicht ändern. Die Funktion liefert den Block als Tool-Result an den
Agent-Loop; die `description` der Aufgabe trägt die Wortwörtlich-Klausel
(EC-29 / `conventions/tasks.md` TASK-10), sodass das LLM den Listen-Block
**wortwörtlich** in seine Bot-Antwort übernimmt (keine Umsortierung, keine
Umformulierung, keine ausgelassenen Termine). Kurze Einleitungs- oder
Schluss-Bemerkungen vom LLM sind erlaubt; der Block selbst ist
unveränderlich.

*Tickets:* #143, #551

## 6. Trigger

### TER-10 — Trigger als Eltern-Chat-Aufgabe (V1)
Solange noch kein anderer Aufrufer existiert, läuft der V1-Trigger der
Funktion als **Aufgabe im Aufgaben-Katalog des Eltern-Chats**
(`eltern-chat.md` EC-8) — analog `ca-verteilung.md` CAV-6,
`familie-anlegen.md` FAA-12 und `kalender-verbinden.md` KAV-Trigger-Linie.
Versteht der Eltern-Chat-Agent die natürlichsprachige Bitte eines
Familienmitglieds („was steht diese Woche an?", „welche Termine haben wir
morgen?"), ruft er die Funktion auf — die Familie muss keinen Tippbefehl
lernen. Es ist eine **lesende** Aufgabe (EC-9): die Funktion läuft ohne
Bestätigungs-Zwischenschritt und **returnt das Ergebnis (TER-9) als
Tool-Result an den Agent-Loop** — das LLM postet die Bot-Nachricht
(EC-29). Die Berechtigung läuft über die reguläre Eltern-Chat-Ansprache-
und Mitgliedschaftsprüfung (`eltern-chat.md` EC-2, EC-5). Aufgabe wie ein
späterer anderer Aufrufer sind nur Nutzer derselben Funktion (TER-1); der
Funktions-Vertrag ändert sich nicht (E-TER-1).

*Tickets:* #143, #551

## 7. Tests

### TER-11 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec mit Code-Verhalten hat einen automatisierten
Test (CLAUDE.md §6), reproduzierbar und **ohne Netz** — Telegram und die
Plan-Buddy-Termin-Schnittstelle werden durch kontrollierte Doppelungen
ersetzt, analog `eltern-chat.md` EC-17, `kalender-verbinden.md` KAV-10,
`plan.md` PLAN-29. Mindest-Abdeckung:

- **TER-1** — Aufruf mit minimalem Eingang (Chat-ID, User-ID,
  Anfrage-Text) returnt einen User-tauglichen Tool-Result-Text.
- **TER-2** — ein Nicht-Familien-Mitglied löst einen Berechtigungs-Bruch
  aus: die Funktion wirft `BerechtigungError` (Funktion sendet nichts und
  liefert kein Result).
- **TER-3** — die Bot-Nachricht landet im selben Chat-Typ wie die Frage
  (Gruppen-Anfrage → Gruppen-Antwort, Privatchat-Anfrage → Privatchat-
  Antwort); die Funktion selbst sendet keine Telegram-Nachricht
  (`FakeTelegram.sent == []` für den Funktions-Frame), das LLM-Reply
  trägt sie (EC-29).
- **TER-4** — jeder Eintrag des Mindest-Vokabulars („heute", „morgen",
  „diese Woche", „nächste Woche", „die nächsten N Tage" für drei
  Beispiel-N, Default-Pfad) löst den dokumentierten `(start, tage)`-
  Aufruf an PLAN-22 aus; ein mehrdeutiger Datums-Ausdruck löst eine
  Rückfrage aus statt eines blinden Aufrufs (EC-22-Verweis-Test).
- **TER-5** — der HTTP-Aufruf an die Plan-Buddy-Schnittstelle nutzt
  Methode `GET`, Pfad `/api/v1/plan/termine` und die Query-Parameter
  `ab=<iso>&tage=<n>`; die Funktion hält keinen Cache (zweiter Aufruf
  mit geänderter Doppelung sieht den neuen Stand).
- **TER-6** — das `person`-Feld der PLAN-22-Antwort wird übernommen,
  nicht durch eine zweite Auflösung ersetzt; ein leeres `person`-Feld
  führt zu einem Termin ohne Personen-Bezug, nicht zu einer fingierten
  Zuordnung.
- **TER-7** — eine fehlschlagende Plan-Buddy-Antwort (Verbindung tot,
  HTTP 5xx, nicht-parsbare Antwort) returnt die hart-codierte Ehrlich-Antwort
  als Tool-Result; ein „Plan-Buddy nicht installiert"-Szenario verhält sich
  identisch (PLAN-23, APP-2).
- **TER-8** — eine leere PLAN-22-Antwort returnt die hart-codierte
  „keine Termine"-Antwort als Tool-Result.
- **TER-9** — der Tool-Result-Listen-Block gruppiert nach Tag in
  chronologischer Reihenfolge; eine Mehrtages-Spanne (gleiche `id` über
  mehrere Tage, PLAN-14) erscheint genau einmal mit Spannen-Hinweis;
  ganztägige Termine tragen „ganztägig" statt einer Uhrzeit; der
  Listen-Block ist deterministisch hart-codiert (EC-12); zusätzlich:
  die `description` der Aufgabe trägt die Wortwörtlich-Klausel
  (EC-29 / TASK-10), und ein End-to-End-Test belegt, dass die finale
  Bot-Nachricht den Listen-Block 1:1 enthält.
- **TER-10** — die EC-8-Aufgabe wird vom Aufgaben-Katalog gefunden und
  ist als **lesende** Aufgabe markiert (EC-9, kein Bestätigungs-Gate).
- **TASK-10/EC-29** — kein `tg.send_*`-Aufruf im Funktions-Frame
  (Aufruf-Graph oder positiver Routing-Test über die Helper-Grenze).

Läufe gegen den **echten** Plan-Buddy bzw. den echten Google-Kalender
sind opt-in und nicht Teil des Standard-Durchlaufs (analog
`eltern-chat.md` EC-17, `plan.md` PLAN-29).

*Tickets:* #143, #551

---

## Offene Punkte

- **OPEN-TER-A — Personen-bezogene Frage („was hat Mila diese Woche?").**
  V1 liefert den vollen Zeitraum und überlässt das Filtern dem Leser. Eine
  spätere Filter-Schicht (Personen-, Stichwort-, Aktivitäts-Filter) auf
  derselben PLAN-22-Antwort ist denkbar — gehört in ein eigenes Ticket,
  sobald belegter Schmerz da ist (eine Familie fragt es wiederholt und
  scrollt durch lange Zeiträume).

- **OPEN-TER-B — Personen-Anzeige in der Antwort.** TER-9 nennt einen
  „Personen-Bezug" je Termin, lässt aber offen, **wie** die Person in der
  Text-Antwort erscheint: Name aus der Familien-Registry (`familie.md`
  FAM-3), das Foto-im-Ring (`familie.md` FAM-4, im Chat nicht sinnvoll
  darstellbar), oder nur die rohe Personen-`id`. Entscheidung vertagt bis
  zum ersten realen Lauf — der Plan-Buddy liefert heute die `id`; die
  Funktion könnte sie über die Familie-Schnittstelle (`familie.md` FAM-7)
  zu einem Namen auflösen, was aber einen zusätzlichen Cross-Service-
  Aufruf wäre. Folge-Ticket sobald die Antwort ohne Namen zu nichtssagend
  wird.

- ~~**OPEN-TER-C — Konkrete Datumsangaben jenseits des Vokabulars.**~~
  Geschlossen durch #309: TER-4 deckt nun `DD.MM.` / `DD.MM.JJJJ` /
  „am D. Monat" als explizite Punkt-Anfragen ab (`start=<datum>, tage=1`),
  inklusive Jahres-Inferenz und Rückfrage bei vergangenem jahrlosen Datum.

---

## Entscheidungen

### E-TER-1 — Funktion ist trigger-agnostisch
*Datum:* 2026-05-29

Termine erfragen wird als eigenständige, trigger-agnostische **Funktion**
definiert — nicht als fest verdrahteter Eltern-Chat-Aufgaben-Schritt. Die
Funktion kennt ihren Aufrufer nicht; ihr Vertrag ist TER-1.

**Verworfen:** die Aufgabe direkt im Eltern-Chat-Skill-Code zu
implementieren, ohne sie als Funktion abzugrenzen. Wäre die Aufgabe ein
fester Skill-Bestandteil, müsste sie für jeden weiteren Aufrufer (ein
Display-Widget, ein anderer Bot-Kanal) neu geschrieben werden — die
Trigger-Agnostik ist die Wiederverwendungs-Garantie. Dasselbe
Eigentümer/Nutzer-Muster gilt für `ca-verteilung.md` (E-CAV-1),
`familie-anlegen.md` (E-FAA-1) und `kalender-verbinden.md` (E-KAV-1).

### E-TER-2 — Konsument der Plan-Buddy-Schnittstelle, kein Direkt-Zugriff
*Datum:* 2026-05-29

Termine werden **ausschließlich** über die Plan-Buddy-Termin-Schnittstelle
gelesen (`plan.md` PLAN-22) — kein eigener Google-Kalender-Adapter in
dieser Funktion, kein direkter Datei-Zugriff auf Plan-Daten.

**Begründung.** Der Plan-Buddy besitzt den Familien-Kalender
(`plan.md` E-PLAN-1, `specs/constitution.md` „App-Eigentümerschaft").
Eine zweite Google-Anbindung in dieser Funktion wäre eine zweite
Wahrheit (CLAUDE.md §6) — Token-Refresh, Event-Modell, Personen-
Auflösung würden auseinanderdriften. Der Konsumenten-Pfad über PLAN-22
ist genau die einseitige Abhängigkeit, die `conventions/apps.md` APP-3
einfordert.

**Verworfen:** ein eigener Cache in dieser Funktion. Cache würde nach
Plan-Buddy-Änderungen veraltete Termine zeigen — derselbe stale-cache-
Schaden, den `conventions/data-components.md` DCOMP-2 für interne
Lese-Pfade verhindert. Ein Aufruf je Frage ist günstig genug; eine
Cache-Schicht braucht belegten Performance-Schmerz, nicht Antizipation
(CLAUDE.md §6).

### E-TER-3 — Antwort dort, wo die Frage kam (keine Privatchat-Pflicht)
*Datum:* 2026-05-29

Die Antwort wird im selben Chat gepostet, in dem die Frage kam (TER-3).
Eine Privatchat-Pflicht analog `kalender-verbinden.md` KAV-3 wird
**nicht** etabliert.

**Begründung.** Termine im Familien-Kalender sind ohnehin
familien-öffentlich — sie erscheinen für jedes Familienmitglied auf
demselben Display (`plan.md` PLAN-13, PLAN-21). Eine Termin-Liste in der
Familien-Gruppe leakt nichts, was die Familie nicht ohnehin teilt. Das
Privatchat-Muster der Konvention (`conventions/privatchat-session.md`
SESS-1..SESS-4) trägt die Sensitivität von Geheimnissen
(`eltern-chat-onboarding.md` ONB-3 Anbieter-Key,
`kalender-verbinden.md` KAV-5 OAuth-Code,
`familie-anlegen.md` FAA-12 Foto-Upload) — Termine sind nicht in dieser
Klasse.

**Verworfen:** alle Termin-Antworten zwangsweise in den Privatchat zu
schieben (analog EC-20). EC-20 sichert mehrstufige Aufgaben gegen
Gruppen-Überflutung ab — diese Funktion ist einstufig (eine Frage, eine
Antwort) und braucht den Schutz nicht. Die zusätzliche Reibung
(Privatchat öffnen, dort die Antwort lesen) wäre Komfort-Verlust ohne
Privacy-Gewinn.

---

## Querverweise

- `eltern-chat.md` EC-2 (Familien-Gruppe als Berechtigung — TER-2),
  EC-3/EC-5 (Gruppe und Privatchat gleichwertig, Ansprache-Logik —
  TER-3/TER-10), EC-7 (ehrliche Grenze — TER-7), EC-8 (Aufgaben-Katalog —
  Heimat des V1-Triggers TER-10), EC-9 (lesende Aufgaben laufen direkt —
  TER-10), EC-12 (anbieter-unabhängige Regeln — TER-4, TER-9), EC-17
  (Tests ohne Netz — TER-11), EC-22 (gezielt fragen statt Varianten —
  TER-4 mehrdeutige Datums-Ausdrücke).
- `ca-verteilung.md` CAV-1 (Funktions-Muster — E-TER-1), CAV-6
  (EC-9-Lese-Aufgabe als V1-Trigger — Pattern-Vorbild für TER-10),
  E-CAV-1 (trigger-agnostische Funktion — E-TER-1).
- `kalender-verbinden.md` KAV-1 (Aufruf-Schnittstelle — Vorbild für
  TER-1), KAV-2 (Live-Berechtigungs-Prüfung — Vorbild für TER-2),
  KAV-3 (Privatchat-Pflicht — bewusst **nicht** übernommen, E-TER-3),
  E-KAV-1 (Trigger-Agnostik — E-TER-1).
- `familie-anlegen.md` FAA-1 (Aufruf-Schnittstelle — TER-1), FAA-2
  (Live-Berechtigungs-Prüfung — TER-2), FAA-12 (EC-8-Aufgabe als
  V1-Trigger — Pattern-Vorbild für TER-10), E-FAA-1 (Trigger-Agnostik —
  E-TER-1).
- `plan.md` PLAN-15 (ein Familien-Kalender — TER-5 Konsumenten-Vertrag),
  PLAN-17 (normalisiertes Event-Modell — TER-5, TER-9), PLAN-19
  (Personen-Auflösung im Plan-Buddy — TER-6), PLAN-14 (Mehrtages-Termine
  als Spanne über stabile `id` — TER-9), PLAN-22 (Termin-Schnittstelle
  `/api/v1/plan/termine` — TER-5 Konsumenten-Vertrag), PLAN-23 (App-
  Existenz-Bindung — TER-7), E-PLAN-1 (App besitzt Funktion und
  Schnittstelle — E-TER-2), E-PLAN-6 (Kalender-Anbindung gehört der
  Plan-Buddy-App — E-TER-2).
- `familie.md` FAM-2 (Familienmitglieder — Berechtigungs-Grundlage für
  TER-2 über `eltern-chat.md` EC-2), FAM-3/FAM-7 (Personen-Identität
  und Lese-API — OPEN-TER-B).
- `conventions/apps.md` APP-1 (App besitzt Daten + Funktion +
  Schnittstelle — E-TER-2-Anker), APP-2 (App-Fähigkeit existiert nur,
  wenn die App installiert ist — TER-7), APP-3 (Andere Apps sprechen
  eine App nur über deren Schnittstelle an — TER-5, E-TER-2).
- `conventions/urls.md` URL-4 (API-Pfade — `/api/v1/plan/termine`-Form
  TER-5), URL-7 (Sprache — TER-9 deutsche Wochentage).
- `conventions/ports.md` PORT-2 (Loopback-Port-Katalog — Plan-Buddy-
  Origin TER-5).
- `conventions/data-components.md` DCOMP-2 (Reload-on-Read — TER-5
  Cache-Verbot folgt derselben Linie), DCOMP-1 (Komponenten reden über
  HTTP — TER-5).
- `conventions/privatchat-session.md` SESS-1..SESS-4 (Privatchat-Session
  — bewusst **nicht** einschlägig für diese Funktion, E-TER-3).
- `specs/constitution.md` (App-Eigentümerschaft — E-TER-2-Anker).
