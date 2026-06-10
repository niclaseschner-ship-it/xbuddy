# Eltern-Chat — Spec     (ID-Präfix: EC)

> Status: V1-MVP · Refs #27

Der Eltern-Chat ist der konversationelle Kanal zwischen Eltern und XBuddy: ein
LLM-Agent, der in einer Telegram-Familien-Gruppe Eltern-Aufgaben übernimmt.
Eltern stellen Anfragen in natürlicher Sprache; der Agent versteht sie und
führt Aufgaben aus einem definierten Katalog aus. Aufgaben, die Familien-Daten
verändern, werden erst nach ausdrücklicher Bestätigung ausgeführt;
sicherheitskritische Schritte entscheidet nicht das Sprachmodell.

**V1-Scope:** Das Gespräch selbst — verstehen, antworten, Kontext halten —, der
Aufgaben-Katalog als Erweiterungspunkt, die Bestätigung schreibender Aufgaben
und ein je Instanz konfigurierbarer KI-Anbieter. Kanal ist Telegram;
Berechtigung ist die Mitgliedschaft in der Familien-Gruppe.

**Out-of-Scope V1** (jeweils eigenes Ticket, sobald gebraucht): die einzelnen
Aufgaben des Katalogs (je eigene Spec) · OAuth-Kalender-Onboarding · der
Anonymisierungs-Layer vor dem KI-Anbieter · Rollen zwischen Familienmitgliedern
(Eltern vs. Kind) · weitere KI-Anbieter und weitere Messenger-Kanäle über den
ersten hinaus.

## 1. Reichweite

### EC-1 — Eine Instanz bedient genau eine Familie
Eine laufende Eltern-Chat-Instanz bedient genau eine Familie über genau einen
Bot. Die Instanz läuft auf dem Hub der Familie — in V1 ein Pi; dieselbe
Software läuft unverändert auf einem Server. Es gibt keinen
familienübergreifenden Bezeichner und keinen Datenpfad, über den eine Instanz
Daten einer anderen Familie liest oder verändert. Der Familienkontext ist
implizit: Anfragen und Aufgaben beziehen sich immer auf die Familie dieser
Instanz.

*Tickets:* #27

### EC-2 — Familien-Gruppe als Berechtigung
Die Instanz ist auf genau eine Telegram-Gruppe konfiguriert — die
Familien-Gruppe (siehe EC-15). Berechtigt ist, wer Mitglied dieser Gruppe ist.
Das System bearbeitet eine eingehende Nachricht genau dann, wenn ihr Absender
im Moment der Nachricht Mitglied der Familien-Gruppe ist; Nachrichten anderer
Absender werden ohne Antwort ignoriert. Wer die Gruppe verlässt oder entfernt
wird, verliert die Berechtigung ohne Verzögerung. Die Gruppen-Mitgliedschaft
ist die alleinige Quelle der Berechtigung — keine separate Anmeldung, keine
zweite Liste.

*Tickets:* #27

### EC-3 — Gruppe und Privatchat gleichwertig
Ein berechtigtes Familienmitglied erreicht den Bot sowohl in der
Familien-Gruppe als auch in einem Privatchat mit dem Bot. Beide Wege werden
gleichwertig bedient — dieselben Anfragen, dieselben Aufgaben. V1 unterscheidet
keine Rollen zwischen Familienmitgliedern (siehe Offene Punkte).

*Tickets:* #27

### EC-18 — Familien-Gruppe übersteht eine Supergruppen-Migration
Telegram wandelt eine reguläre Gruppe ohne Zutun der Familie in eine
Supergruppe um — etwa beim Aktivieren bestimmter Funktionen oder beim
Überschreiten einer Mitgliederzahl. Dabei wechselt die Chat-ID der Gruppe
dauerhaft; die alte ID ist danach ungültig. Wird die in EC-2 gebundene
Familien-Gruppe so migriert, zieht die Instanz die Bindung selbsttätig nach:
Sie übernimmt die neue Supergruppen-ID, speichert sie persistent (ONB-5) und
bedient die Gruppe ohne Unterbrechung weiter — ohne Neustart und ohne
manuellen Eingriff. Wird bereits die Onboarding-Gruppe vor dem Abschluss
migriert, gilt dasselbe — gebunden wird dann die nachgezogene ID (ONB-6).

Telegram meldet die Migration auf zwei Wegen, die das System beide auswertet:
(1) eine Dienst-Nachricht in der bisherigen Gruppe trägt die neue ID; (2) ein
Mitgliedschafts-Aufruf gegen die alte ID schlägt fehl und nennt die neue ID
mit. Weg (2) ist die Absicherung, falls die Dienst-Nachricht verpasst wurde —
ein solcher Fehler darf nicht als fehlende Berechtigung (EC-2) gewertet werden,
sondern löst die Nachführung aus.

Ist die Familien-Gruppe per Umgebungsvariable oder Konfiguration fest gebunden,
wird eine Migration protokolliert, aber die gesetzte ID nicht überschrieben —
ein bewusst gesetzter Wert hat Vorrang (analog ONB-6), seine Pflege liegt dann
bei der Betreiberin.

*Tickets:* #45

### EC-19 — Empfangs-Voraussetzung beim Start geprüft
Damit Telegram der Instanz die Nachrichten ihrer Familien-Gruppe zustellt, muss
der Bot in dieser Gruppe Administrator sein oder sein Privacy-Modus deaktiviert
sein; andernfalls erhält er dort nur Kommandos und Antworten auf eigene
Nachrichten, nicht aber eine bloße Erwähnung (vgl. EC-5). Beim Start prüft die
Instanz, ob diese Voraussetzung für die gebundene Familien-Gruppe erfüllt ist,
und schreibt, wenn nicht, eine eindeutige Warnung ins Log. So wird ein »der Bot
schweigt in der Gruppe« sofort als Betriebs- und nicht als Code-Problem
erkennbar. Liegt noch keine Familien-Gruppe vor (Onboarding-Modus, ONB-1),
greift die Prüfung nicht.

*Tickets:* #45

## 2. Gespräch

### EC-4 — Natürlichsprachliche Anfrage
Ein Familienmitglied richtet seine Anfrage an den Bot in natürlicher Sprache —
als Text, als geteiltes Bild oder beides; keine Befehlssyntax, keine Menüs. Das
System deutet die Anfrage und reagiert: mit dem Ergebnis einer Aufgabe
(Abschnitt 3), mit einer gezielten Rückfrage bei unvollständiger oder
mehrdeutiger Anfrage, oder mit einer ehrlichen Grenze (EC-7).

*Tickets:* #27

### EC-5 — Wann das System reagiert
In einem Privatchat bezieht sich jede Nachricht auf den Bot — das System
reagiert auf jede. In der Familien-Gruppe reagiert das System nur, wenn es
ausdrücklich angesprochen wird (Erwähnung des Bots oder Antwort auf eine seiner
Nachrichten). Normale Familienkommunikation in der Gruppe löst keine Reaktion
aus.

Die Erwähnung wird unabhängig von Groß-/Kleinschreibung erkannt: Telegram-
Usernames sind case-insensitiv — der Bot gilt also auch dann als angesprochen,
wenn sein Name anders geschrieben wird als offiziell geführt. Damit Telegram
dem Bot Gruppennachrichten überhaupt zustellt, muss sein Privacy-Modus
deaktiviert sein oder der Bot in der Gruppe Administrator sein: bei aktivem
Privacy-Modus erhält der Bot nur Kommandos und Antworten auf seine Nachrichten
— eine bloße @-Erwähnung erreicht ihn nicht. Diese Betriebs-Voraussetzung gilt
damit auch für EC-5 (siehe ONB-2).

*Tickets:* #27

### EC-6 — Gesprächskontext, über Neustart hinweg
Das System hält den Verlauf eines Gesprächs, sodass eine Anfrage sich auf
Vorheriges beziehen kann (»und den Termin auch noch«, »das Bild von eben«). Der
Kontext ist pro Telegram-Chat getrennt: die Familien-Gruppe ist ein Gespräch,
jeder Privatchat ein eigenes — sie teilen keinen Verlauf. Der Verlauf wird
dauerhaft gespeichert und übersteht einen Neustart der Instanz. Wie weit er
zurückreicht, ist konfigurierbar (EC-15).

**Persistierung von Tool-Turns (#310).** Tool-Turn-Paare — ein
`tool_use`-Block (Assistant) und das zugehörige `tool_result`
(User) — werden vollständig und paarweise in der Gesprächs-Datenbank (EC-16)
gespeichert. Sie überstehen einen Neustart der Instanz: Das Modell sieht nach
einem Neustart denselben Kontext wie vor dem Abbruch; kein halbes Paar wird beim
depth-Schnitt in das Modell-Fenster gereicht, da Anthropic solche
Nachrichten ablehnt. Das depth-Fenster (EC-15) zählt Einzelnachrichten —
jeder Tool-Turn (Aufruf wie Ergebnis) zählt je 1 (Begründung für den
erhöhten Default: EC-15).

Abdeckende Tests: `eltern-chat/tests/test_history.py` (Persistenz, Paar-Schutz
am depth-Schnitt), `eltern-chat/tests/test_main_history_transcript.py`
(Orchestrierungs-Seite: vollständiges Tool-Transkript im Kontext nach einem
Durchlauf).

**Wortlaut persistierter tool_result-Quittungen (#331).** Eine persistierte
`tool_result`-Quittung, die einen vorgelegten Vorschlag bestätigt, darf NICHT
suggerieren, der Vorgang sei bereits erledigt oder warte nur auf eine externe
Bestätigung — sonst verdrängt sie bei einem erneuten „ja" den Werkzeug-Aufruf:
Das Modell hält die Aufgabe schon für in Bearbeitung und wartet statt zu
handeln. Sie macht stattdessen klar: Das Werkzeug ist erneut aufzurufen. Der
Wortlaut ist per Aufgaben-Name parametrisiert, damit das Modell erkennt,
welches Werkzeug gemeint ist (`_proposal_pending`-Quittung, parametrisiert
mit dem Aufgaben-Namen).

*Tickets:* #27 · #310 · #331

### EC-7 — Ehrliche Grenze
Kann das System eine Anfrage nicht erfüllen — sie liegt außerhalb seiner
Aufgaben, oder eine Voraussetzung fehlt — sagt es das klar und nennt, was es
stattdessen tun kann. Es gibt keine erfundenen Fähigkeiten und keine
vorgetäuschten Ergebnisse. Das System führt keine Aufgabe aus, die nicht durch
eine definierte Aufgabe (Abschnitt 3) gedeckt ist.

*Tickets:* #27

### EC-22 — Gezielt fragen statt Varianten ausbreiten
Bei Anfragen, deren passende Antwort vom Kontext abhängt (z. B. Anleitungen
mit Geräte-Varianten), fragt das System einmal kurz nach dem fehlenden Kontext
und liefert dann gezielt — statt mehrere Varianten gleichzeitig auszubreiten.
Wenn das System eine angefragte Tatsache nicht sicher kennt, sagt es das offen,
statt einen plausiblen Pfad zu raten. (Verschärft EC-7; betrifft die Antwort
*innerhalb* der Katalog-Grenze.)

Erkennt das System nachträglich, dass es einen Holzweg eingeschlagen hat
(z. B. einen Schritt vorgeschlagen, der am Gerät nachweislich nicht
funktioniert), entschuldigt es sich kurz und macht mit dem nun bekannten
Stand weiter — keine stille Korrektur, kein erneutes Ausbreiten aller
Möglichkeiten.

**Was sich für die Familie ändert** — Beispiel: Zertifikat installieren.

- Ohne EC-22: Mama bittet den Bot um die Zertifikat-Anleitung. Der Bot
  schickt einen Block mit allen vier OS-Varianten (Windows, Android, iOS,
  macOS). Mama muss erst durchlesen, welcher Abschnitt für ihr iPhone gilt
  — auf einem 6"-Display, neben Familien-Gruppen-Nachrichten.
- Mit EC-22: Der Bot fragt einmal kurz: »Welches Gerät — Android-Handy,
  iPhone/iPad, Windows-PC oder Mac?« Mama tippt »iPhone«. Der Bot schickt
  nur den iOS-Abschnitt — kein Suchen, kein Scrollen.

Begründung: Eltern müssen das nicht selbst leisten — die gezielte Rückfrage
ist Sekunden, das Suchen im falschen Abschnitt ist Reibung jeder Familie
ohne Geräte-Detail.

*Tickets:* #95

### EC-30 — Welt-Wissen für allgemeine Hilfs-Anfragen, XBuddy-Zustand bleibt Katalog-only
Für **allgemeine Wissensfragen** ohne XBuddy-Bezug — technische Anleitungen,
Sach-Fragen, Erklärungen — nutzt das System das trainierte Welt-Wissen des
KI-Anbieters und antwortet direkt. Beispiele: „Wie installiere ich ein CA-
Zertifikat auf einem alten iPhone?", „Was bedeutet HTTPS?", „Wie funktioniert
Tailscale?". Solche Antworten erfordern keinen Tool-Aufruf.

**Trennlinie**: Aussagen über **XBuddy-Zustand** — Familien-Mitglieder,
Kalender-Inhalte, Berechtigungen, Buddy-Daten (Routinen, Plan-Aktivitäten,
Wünsche, Termine, Fotos, Seiten-Übersicht) — gehen *immer* durch eine
Katalog-Aufgabe (EC-8) und niemals aus dem Welt-Wissen des Modells. Eine
Anfrage „wer hat morgen Geburtstag?" oder „wann ist Pauls nächster Termin?"
wird durch eine Katalog-Aufgabe beantwortet, nicht aus Welt-Wissen. Eine
Anfrage „wie installiere ich ein Zertifikat?" darf direkt aus Welt-Wissen.

EC-7 (Ehrliche Grenze) bleibt für **System-Fähigkeiten** in Kraft: das System
spielt keine XBuddy-Aufgaben vor, die es nicht hat. Welt-Wissens-Antworten
sind **keine** erfundenen Fähigkeiten — sie sind Hilfs-Information aus dem
Anbieter-Modell, das nach EC-11/EC-12 ohnehin Teil des Systems ist. Der
Unterschied ist hart: erfunden ist eine *behauptete eigene Operation*
(„Ich habe für dich Termin X angelegt") ohne tatsächlichen Schreibakt;
Welt-Wissen ist *geteiltes Hilfs-Wissen* aus dem Modell — keine Behauptung
einer eigenen Operation.

EC-22 (Gezielt fragen statt Varianten ausbreiten) bleibt unberührt: auch bei
Welt-Wissens-Antworten mit Geräte-Varianten fragt das System einmal nach dem
fehlenden Kontext und liefert dann gezielt — keine Varianten-Schauspiele.

**Was sich für die Familie ändert** — Beispiel: CA-Zertifikat-Installation
auf einem alten iPhone (iOS 12 statt iOS 14).

- Ohne EC-30: Mama fragt „und für altes iPhone?". Bot antwortet „ich habe
  nur die Anleitung für neuere iPhones vor mir" — obwohl der KI-Anbieter
  die Antwort kennt. Mama muss extern nachfragen.
- Mit EC-30: Bot antwortet direkt aus Welt-Wissen mit den iOS-12-Schritten,
  nachdem er ggf. einmal nach Geräte-Details gefragt hat (EC-22).

*Tickets:* #624

### EC-23 — Telemetrie an Bot-Antworten

Wenn eine Bot-Antwort durch mindestens einen Provider-Call entstanden ist,
sieht die Familie am Ende der Antwort eine kompakte Telemetrie: Gesamt-
Laufzeit dieses Turns, Token-Verbrauch und geschätzte Kosten in Euro. Bei
Antworten ohne Provider-Call (z. B. EC-7-Bestätigungswort-Quittung)
entfällt die Annotation. Persistenz pro Provider-Call (Modell,
Token-Aufteilung, Wall-Clock, Kosten, Zeitpunkt (`created_at`),
Verknüpfung Chat+Turn) — V2 aggregierte Sicht. V1: an, nicht abschaltbar.

Die Telemetrie ist Diagnose-Werkzeug für die Bewertungsphase: sie macht
sichtbar, wo Latenz und Kosten anfallen, statt blind an der Wahrnehmung zu
optimieren. Der Suffix erscheint nur in der gesendeten Nachricht — er wird
NICHT in den Gesprächsverlauf (EC-6) aufgenommen, damit Folge-Turns die
Telemetrie nicht als »Bot-Wortlaut« mitschleppen.

*Tickets:* #268

### EC-25 — Typing-Indikator vor Bot-Nachrichten in mehrstufigen Schreib-Aufgaben

Während der Bot eine mehrstufige Schreib-Aufgabe (EC-20) im Privatchat abwickelt,
sendet er vor jeder eigenen Nachricht in diesem Privatchat den Telegram-Typing-
Indikator (`sendChatAction`, `action=typing`). Das gilt für alle Nachrichten
innerhalb der Session: Rückfragen zu Pflicht-Feldern, der strukturierte Vorschlag
(EC-10) und — wenn die Aufgabe abgeschlossen ist — die Abschluss-Quittung.

Der Typing-Indikator ist **Best-Effort-Komfort** und kein Sicherheits-Gate:

- Schlägt der `sendChatAction`-Aufruf fehl (Netzwerk-Fehler, Telegram-Rate-Limit
  oder beliebiger HTTP-Fehler), läuft die Aufgabe **ohne Unterbrechung weiter** —
  kein Abbruch, keine Fehler-Antwort an die Familie.
- Der Typing-Indikator blockiert den Aufgaben-Fortschritt nicht; er wird
  Fire-and-Forget vor der eigentlichen Sende-Operation abgesetzt.

**Was sich für die Familie ändert.** Ohne EC-25 sieht die Familie nach dem
Absenden ihres Bestätigungswortes oder einer Rückfragen-Antwort zunächst Stille
— je nach Verarbeitungsdauer mehrere Sekunden, ohne Signal, dass der Bot noch
aktiv ist. Mit EC-25 erscheint sofort das „tippt gerade"-Signal im Privatchat,
bevor die Bot-Antwort kommt. Das reduziert Verwirrung bei längeren
Provider-Calls (EC-14, EC-11), ohne die Latenz zu verändern.

Code-Verweise, die heute den Typing-Indikator an EC-14 koppeln, werden auf EC-25
umgezeigt — das ist Aufgabe der Code-Tracks, nicht dieser Spec.

*Tickets:* #284

### EC-26 — Telegram-Transport blockiert die familienseitige Antwort nicht durch tote Netzpfade

Der Verbindungsaufbau zur Telegram-Bot-API ist zeitlich gebunden und blockiert die familienseitige Antwort nicht: ein nicht erreichbarer Netzpfad scheitert schnell, statt einen Turn zu blockieren. Der Connect-Timeout ist vom Read-Timeout getrennt — Lese-Operationen (Long-Poll `getUpdates`) dürfen lange laufen, der Verbindungsaufbau jedoch nicht.

Die Regel gilt für alle Calls desselben Clients — Long-Poll, Berechtigungsprüfung (`getChatMember`), Typing-Indikator (EC-25), Versand —, weil sie über denselben Transport laufen. Sie ergänzt EC-25: dort ist der Typing-Indikator als „blockiert nicht" gefordert; EC-26 entfernt die Stall-Ursache am Transport selbst.

Umsetzung: siehe E-EC-12.

*Tickets:* #287, #294, #299, #300, #301

### EC-27 — Telegram-Formatierung: `parse_mode=HTML` opt-in pro Nachricht

Der Telegram-Transport (`eltern-chat/telegram.py`) sendet Bot-Nachrichten
**standardmäßig ohne `parse_mode`** — der Bestand bleibt unverändert
Klartext. Damit bleiben statische Bot-Texte mit syntaktisch HTML-ähnlichen
Zeichen funktionsfähig (Beispiel: `eltern-chat/skills/geraet_anlegen.py`
fragt nach „Format: `<breite>x<höhe>`" — im HTML-Modus würde Telegram das
unbekannte Tag `<breite>` ablehnen und die Nachricht verwerfen).

Ein Skill, der **strukturierte Listen zum Kopieren** vorlegen will (z. B.
`termine-aus-bild.md` TAB-7 Sammel-Vorschlag und TAB-8.1 Sentinel-Lückenform),
**aktiviert HTML pro Nachricht** durch ein optionales Argument
`parse_mode="HTML"` an der `send_message`-API. Diese Wahl ist
**Skill-Verantwortung**: der Skill muss in dieser Nachricht alle dynamischen
Werte HTML-escapen (siehe unten) — sonst zerstört er die eigene Nachricht.

**HTML-Escape-Pflicht beim Opt-in:** Sobald ein Skill `parse_mode="HTML"`
setzt, escaped er jeden dynamischen Wert (Termin-Titel, Personen-Namen,
LLM-Output, zurückgespiegelte Familien-Eingaben) vor dem Einsetzen in die
Nachricht — `<` → `&lt;`, `>` → `&gt;`, `&` → `&amp;`. Der konkrete
Escape-Helper lebt im Code; die Spec normiert das **Soll** (Escape findet
statt, an EINER Stelle, vor dem Einsetzen — keine doppelte Escape, kein
vergessenes Escape). Statische, vom Code formulierte Klartext-Wrapper im
HTML-Pfad bleiben unangetastet, weil sie als Konstanten kontrolliert sind.

Skills, die **nicht** HTML aktivieren (= der heutige Bestand), brauchen
nichts zu ändern — sie senden weiter Klartext, kein Escape-Risiko, kein
Bestandsbruch. Eine spätere Migration von Bestands-Texten auf HTML
(z. B. um konsistent Monospace zu setzen) wäre ein eigenes Ticket mit
Audit aller heutigen statischen Bot-Texte auf Telegram-relevante Zeichen.

Eingehende Familien-Nachrichten bleiben in allen Fällen **Klartext**.

Diese Regel ergänzt EC-12 (anbieter-unabhängige Regeln): die HTML-Linie
gilt unabhängig vom konfigurierten KI-Anbieter, weil sie reine
Telegram-Transport-Schicht ist.

*Tickets:* #475 (TAB Erst-Konsument; opt-in pro Nachricht)

### EC-28 — Skill-seitiges Typing-Indikator-Renewal für synchrone Buddy-Bulk-Calls

Ruft ein Eltern-Chat-Skill synchron einen anderen Buddy (HTTP-Service via
`conventions/data-components.md` DCOMP-1 / `conventions/apps.md` APP-3)
auf und dauert dieser Aufruf länger als rund 5 Sekunden — die
Sichtbarkeitsdauer des Telegram-Typing-Indikators —, erneuert das Skill
den Indikator **selbst** periodisch, solange der Buddy-Call läuft. Konkret:
ein **Best-Effort-Hintergrund-Thread** sendet alle 4 Sekunden
`sendChatAction(typing)` in den jeweiligen Chat (Familien-Gruppe oder
Privatchat, je nachdem wo die Aufgabe gerade läuft).

Fehler des Renewal-Calls (Netzwerk-Fehler, Telegram-Rate-Limit, beliebiger
HTTP-Fehler) brechen den Buddy-Call **nicht** ab — kein Abbruch der
Aufgabe, keine Fehler-Antwort an die Familie. Das Renewal ist
Komfort-Signal, nicht Sicherheits-Gate.

Begründung der Skill-Seitigkeit: der angerufene Buddy (z. B. Plan-Buddy
bei `termine-aus-bild.md` TAB-9 PLAN-33 Bulk-PUT) ist ein HTTP-Service
hinter `conventions/apps.md` APP-3 — er kennt den Telegram-Chat des
Aufrufers nicht und darf ihn nicht kennen (DCOMP-1 einseitige
Abhängigkeit). Der Typing-Indikator gehört zum Eltern-Chat-Transport;
ihn dort zu halten, wo das Wissen um den Chat liegt, ist die einzige
Option, die die Komponenten-Grenze respektiert.

Diese Regel ist die Bulk-/Buddy-Analogie zu EC-14 Absatz 2 (Renewal für
Provider-Calls) — derselbe Mechanismus, anderer Konsument: dort der
KI-Anbieter, hier ein anderer Buddy. Die EC-25-Linie (Typing als
Komfort-Signal vor Bot-Nachrichten in mehrstufigen Schreib-Aufgaben)
bleibt unberührt — EC-28 deckt die Lücke **während** eines synchronen
Buddy-Calls, EC-25 die Lücke **vor** jeder Bot-Sende-Operation.

*Tickets:* #475

### EC-29 — Eine Stimme im Agent-Turn

Im Agent-Loop des Eltern-Chats hat ein Turn **eine einzige Stimme**: das LLM
formuliert die Bot-Nachricht und postet sie als einzigen Schreibakt in den
Telegram-Chat. Eine Katalog-Aufgabe (EC-8), die das LLM während der
Tool-Use-Phase aufruft, **postet während ihrer Ausführung nicht selbst** —
weder direkt über die Telegram-API noch über eine von ihr gerufene
trigger-agnostische Funktion. Sie returnt stattdessen einen
**User-tauglichen Antwort-Text als Tool-Result**; das LLM verarbeitet
diesen Text in seiner nachfolgenden Antwort-Generierung zur Bot-Nachricht.
Ziel ist eine flüssige, nach echtem Mensch klingende Antwort: das LLM
**kennt** das Ergebnis (aus dem Tool-Result) und **formuliert** es —
statt dass zwei Sprecher (Skill-Stimme + LLM-Stimme) im selben Turn in
denselben Chat schreiben.

**Geltungsbereich.** Diese Regel gilt für jede Aufgabe, deren Code im
Rahmen eines Agent-Tool-Calls läuft — `ReadTask.run()` (TASK-3) ebenso wie
die `propose()`-Hälfte einer `WriteTask` (TASK-4) und die
trigger-agnostischen Funktionen, die von dort gerufen werden. Sie gilt
**nicht** für `WriteTask.execute()` nach erfolgter Bestätigung (EC-10) und
nicht für Privatchat-Worker-Threads asynchroner schreibender Aufgaben
(TASK-5/SESS) — diese laufen außerhalb des Agent-Loops und sind nicht im
selben Turn-Frame wie das LLM.

**Tool-Result-Vertrag.** Das Tool-Result ist ein einzelnes Feld, das nur
den Agent-Loop erreicht; die Familie sieht es nie direkt. Die Aufgabe darf
darin neben dem User-tauglichen Antwort-Text auch Agent-Steuer-Hinweise
unterbringen (z. B. die Inventar-Liste in `seiten-registry.md` SREG-5b
Runde 1) — Trennung in „User-sichtbar" vs. „nur Agent" ist nicht Teil des
V1-Vertrags. Solange das LLM den Antwort-Text in seiner Bot-Nachricht
trägt, ist die Eine-Stimme-Eigenschaft erfüllt.

**Provider-Down.** Was bei Ausfall des KI-Anbieters mit dem Tool-Result
geschieht, regelt EC-14 (ehrlicher Abbruch). Ein Framework-Fallback, der
den Tool-Result-Text bei Provider-Fehler direkt sendet, ist **nicht** V1
und wird erst angegangen, wenn die Provider-Down-Frequenz das rechtfertigt
(OPEN-EC-A-Anker, Backlog).

**Datei-Anhänge — Skill sendet die Datei, LLM postet den Text.** Wo eine
Aufgabe ein Nicht-Text-Artefakt ausliefert (Datei via
`tg.send_document`, Bild via `tg.send_photo`), bleibt der **Anhangs-
Versand** Skill-Verantwortung — das LLM hat keine Datei-Sende-Mechanik.
Der **gesamte Text-Teil** (Caption, Anleitung, Begleittext) wandert in den
Tool-Result; das LLM formuliert daraus die Bot-Nachricht und postet sie.
Heute betrifft das `ca-verteilung.md` (CAV) — Zertifikatsdatei vom Skill,
hart-codierte OS-Anleitung im Tool-Result.

**Trust-kritische Texte — Wortwörtlich-Disziplin.** Wenn ein Tool-Result
einen Text enthält, der **wortwörtlich** an die Familie gehen muss
(Sicherheits-Eigenschaft, nicht Stil — z. B. CAV-5 OS-Installations-
Schritte: eine vom LLM nachformulierte Schritt-Folge kann einen
Trust-Schritt auslassen und das Zertifikat unbrauchbar machen), trägt die
Aufgaben-`description` eine **Wortwörtlich-Klausel** für das LLM: „Diesen
Text wortwörtlich in deine Antwort übernehmen, nicht umformulieren oder
kürzen; kurze Einleitungs-/Schluss-Bemerkungen sind erlaubt." Die
Wortwörtlich-Disziplin gehört in den Skill-Bauplan (`conventions/tasks.md`
TASK-10), nicht in eine namentliche EC-29-Ausnahme — sie ist Mechanik,
keine Ausnahme.

**Helper-Grenzen.** Eine Aufgabe, die ihre Telegram-Sendung in einen Helper
auslagert (z. B. `WuenscheZeigenTask.run()` ruft `wuensche_zeigen()`), darf
diesen Helper aus dem Agent-Loop heraus nicht senden lassen. Die
Aufruf-Phase entscheidet, nicht die Modul-Grenze. Wie das in Code und Tests
gesichert wird (Watchdog-Lint mit Aufruf-Graph oder verbindlicher Test),
regelt `conventions/tasks.md` TASK-10 — nicht diese Spec.

*Tickets:* #551

## 3. Aufgaben

### EC-8 — Aufgaben-Katalog
Das System führt ausschließlich Aufgaben aus einem definierten Katalog aus.
Jede Aufgabe ist in einer eigenen, reviewten Spec festgelegt — mit stabiler
Bezeichnung und festgelegten Eingaben (Text und/oder Bild). Diese Spec
definiert nur den Rahmen, nicht die einzelnen Aufgaben. Eine Anfrage, die
keiner Katalog-Aufgabe entspricht, wird nicht »kreativ« gelöst, sondern führt
zu einer ehrlichen Grenze (EC-7). Aufgaben werden additiv ergänzt; der
bestehende Katalog bleibt unberührt.

*Tickets:* #27

### EC-9 — Lesende Aufgaben laufen direkt
Eine Aufgabe, die nur Information liefert und keine Familien-Daten
verändert, führt das System ohne Zwischenschritt aus. Sie returnt das
Ergebnis als User-tauglichen Antwort-Text an den Agent-Loop, der daraus
die Bot-Nachricht formuliert (EC-29 — eine Stimme im Agent-Turn). Liefert
die Aufgabe ein Nicht-Text-Artefakt (Datei, Bild), sendet der Skill den
Anhang technisch direkt (EC-29 Datei-Anhang-Klausel); der gesamte
Text-Teil wandert in den Tool-Result und kommt aus der LLM-Stimme.

*Tickets:* #27, #63, #551

### EC-10 — Schreibende Aufgaben nur nach Bestätigung
Bevor eine Aufgabe ausgeführt wird, die Familien-Daten verändert, legt das
System einen strukturierten Vorschlag vor — was genau geschehen würde — und
führt die Aufgabe erst aus, nachdem ein Familienmitglied sie ausdrücklich
bestätigt hat. Ohne Bestätigung geschieht keine Veränderung. Die Bestätigung
ist eindeutig einem konkreten Vorschlag zugeordnet, auch wenn dazwischen andere
Nachrichten eingehen.

**Ein-Schritt-Bestätigung bei vollständigem Anstoß.** Liefert der Anstoß
bereits alle für die Schreib-Aufgabe nötigen Felder (d. h. keine Rückfrage
nach Pflicht-Feldern mehr nötig), kombiniert der Bot Daten-Übersicht und
Bestätigungs-Frage zu **einer** Nachricht: er legt den strukturierten Vorschlag
(„was genau geschehen würde") direkt vor und fordert in derselben Nachricht
das Bestätigungswort (E-EC-7). Laufen keine Rückfragen zum Auflösen der Pflicht-
Felder, entfällt eine zusätzliche Zwischennachricht. Das Schreib-Gate selbst
(Ausführung erst nach ausdrücklicher Bestätigung) bleibt vollständig erhalten —
keine Änderung an der Sicherheits-Garantie.

**Zweistufige Variante als Fallback.** Ist der Anstoß unvollständig (mindestens
ein Pflicht-Feld fehlt oder ist mehrdeutig), fragt der Bot erst gezielt nach
(EC-22) und legt den strukturierten Vorschlag erst vor, sobald alle Pflicht-
Felder geklärt sind. Das ist der bisherige Pfad.

Diese Verfeinerung gilt global für alle schreibenden Aufgaben (TES, FAA, GAA,
KAV und künftige Aufgaben desselben Musters).

Die Vor-Bestätigung mehrstufiger schreibender Aufgaben (EC-20) benennt den Ort
der nächsten Schritte kontextabhängig: in der Familien-Gruppe gestartet →
Verweis auf Privatchat; bereits im Privatchat gestartet → kein
Ortswechsel-Hinweis. Der Wortlaut suggeriert keinen Ortswechsel, wenn keiner
stattfindet.

**Modell-sichtbare
Repräsentation eines vorgelegten Vorschlags.** Die dem Modell sichtbare
Repräsentation eines vorgelegten Schreib-Vorschlags (der synthetische
`tool_result`-Inhalt, der das `tool_use` im persistierten Verlauf paart, #310)
macht klar, dass das WERKZEUG die Aufgabe ausführt — einschließlich des
Schritt-für-Schritt-Dialogs (Auswahl aus den jeweiligen Registries/Listen) —
und bei erneutem Wunsch erneut aufzurufen ist. Sie darf NICHT so lesen, als sei
der Vorgang bereits im Gange oder erledigt, und NICHT als „erst nach
Bestätigung ausführen" formuliert sein — beides veranlasst das Modell, auf ein
externes „Ja" zu warten, statt das Werkzeug bei erneutem Anlauf erneut
aufzurufen. Der Text ist per Aufgaben-Name parametrisiert, damit das Modell
erkennt, WELCHES Werkzeug erneut aufzurufen ist. Das deterministische
Schreib-Gate (Ausführung erst nach Bestätigung, `confirm.py`) bleibt davon
unberührt — es wird im Code erzwungen, nicht über diesen Text.

*Tickets:* #27 · #266 · #278 · #331

### EC-20 — Mehrstufige Aufgaben überfluten die Familien-Gruppe nicht

Eine schreibende Aufgabe, die mehrere Antworten der Familie braucht — Familie
anlegen, Gerät anlegen, Kalender verbinden, künftig Controller einrichten —
führt der Bot im **Privatchat** mit dem anfragenden Familienmitglied weiter.
Die Familien-Gruppe sieht nur den Anstoß und das Ergebnis — nicht
Foto-Uploads, Eingaben, Zwischennachfragen. Der Bot behält den Gesprächsfaden
dieses Privatchats, auch wenn dazwischen andere Anfragen aus der Gruppe
kommen. Antwortet die Familie 30 Minuten lang nicht, beendet der Bot die
Aufgabe stumm; sie kann jederzeit neu gestartet werden.

**Was sich für die Familie ändert** — Beispiel: Schul-Termine erfassen.

- Ohne EC-20: Mama bittet den Bot in der Familien-Gruppe, die Schul-Termine
  vom Foto des Schulplans zu übernehmen. Der Bot fragt im selben Gruppen-Chat
  nach dem Foto — Mama lädt es dort hoch, neben den Nachrichten der Kinder.
  Papa schreibt parallel etwas anderes, der Bot mischt beide Fäden. Der
  Schulplan liegt jetzt für alle Familienmitglieder sichtbar im Verlauf der
  Gruppe.
- Mit EC-20: Mama startet die Aufgabe in der Familien-Gruppe. Der Bot
  antwortet öffentlich nur kurz: »Okay Mama, ich frage dich gleich im
  Privatchat.« Im 1:1-Chat zwischen Mama und Bot folgen Foto-Upload, Rückfrage
  zu unklaren Terminen, Korrekturen. In der Familien-Gruppe erscheint
  später nur: »Schul-Termine erfasst — 5 neue Termine im Wochenplan.«

Begründung: Privatsphäre und Bedienkomfort. Eltern sollen weder unter
Beobachtung der Kinder Token oder Foto hochladen müssen, noch sich ihren
Gesprächsfaden vom nächsten Gruppen-Wortbeitrag zerreißen lassen.

*Tickets:* #130 (PrivateChatSession-Refactor) — Umsetzung als gemeinsame
Session-Klasse statt drei kopierter Worker-Loops.

### EC-21 — Änderungen wirken sofort und ehrlich

Wenn eine bestätigte schreibende Aufgabe abgeschlossen ist, **wirkt** die
Änderung sofort auf die abhängigen Buddies — neue Kalender-Termine erscheinen
beim nächsten Öffnen des Wochenplans, ein neu angelegtes Gerät beim nächsten
Erkennungsvorgang. Niemand muss den Bot, das Tablet oder den Pi neu starten,
nichts „aktualisieren" tippen. Klappt diese Übernahme im Ausnahmefall nicht,
sagt der Bot in einer Nachricht klar, was zu tun ist — kein stiller
Schwebezustand zwischen „Aufgabe durch" und „Wirkung sichtbar".

**Was sich für die Familie ändert** — Beispiel: Kalender verbinden.

- Ohne EC-21: Mama verbindet ihren Google-Kalender per Bot. Der Bot meldet
  »Kalender verbunden«. Mama tippt am Display auf den Wochenplan — die neuen
  Termine sind nicht da. Sie fragt sich, ob es geklappt hat. In Wirklichkeit
  läuft der Plan-Buddy mit seinem alten Cache weiter; erst ein Pi-Neustart
  würde ihn dazu bringen, den neuen Kalender zu lesen. Niemand sagt ihr das.
- Mit EC-21: Mama verbindet ihren Google-Kalender per Bot. Sobald sie »passt«
  sagt, antwortet der Bot »Kalender verbunden — neue Termine sind jetzt im
  Wochenplan sichtbar.« Sie tippt aufs Display, die Termine sind da. Hakt es
  ausnahmsweise (Plan-Buddy gerade abgestürzt), schreibt der Bot konkret:
  »Plan-Buddy hat die Änderung evtl. noch nicht geladen — bitte einmal das
  Display neu öffnen.«

Begründung: Vertrauen kommt von sofortiger sichtbarer Wirkung. Eine
Familie, die nach einer Aufgabe vor einem unveränderten Display steht und
nicht weiß, ob es geklappt hat, glaubt dem System nicht mehr.

*Tickets:* #140 (Skill-Service-Reload) — Umsetzung als Reload-Aufruf vom
Skill an die konsumierenden Buddies.

## 4. KI-Anbieter & Datensicherheit

### EC-11 — KI-Anbieter je Instanz wählbar
Welcher KI-Anbieter die Anfragen einer Familie verarbeitet, ist je Instanz
konfigurierbar (siehe EC-15). Der Wechsel des Anbieters ist eine reine
Konfigurations-Änderung — er erfordert keine Änderung am übrigen Verhalten oder
Aufbau des Systems.

*Tickets:* #27

### EC-12 — Anbieter-unabhängige Regeln
Die regelhaften Eigenschaften des Systems gelten unabhängig vom konfigurierten
Anbieter: die Berechtigungsprüfung (EC-2), die Katalog-Grenze (EC-8) und die
Bestätigung schreibender Aufgaben (EC-10) hängen nicht von der Ausgabe des
Sprachmodells ab. Ein Anbieterwechsel kann die Qualität der Erkennung und die
Formulierung der Antworten verändern — nicht aber diese Regeln.

*Tickets:* #27

### EC-13 — Datenübermittlung an den KI-Anbieter
Zur Bearbeitung einer Anfrage übermittelt das System dem konfigurierten
KI-Anbieter ausschließlich, was dafür nötig ist:

1. den Anfrage-Inhalt (Text, geteilte Bilder),
2. den Gesprächskontext (EC-6) und
3. die **Tool-Result-Texte** der im Turn ausgeführten Katalog-Aufgaben —
   weil das LLM die Bot-Antwort daraus formuliert (EC-29 — eine Stimme im
   Agent-Turn). Diese Tool-Result-Texte enthalten je nach Aufgabe
   Wunschlisten-Einträge (`wuensche-zeigen.md`), Termin-Titel und
   Personen-Bezüge (`termine-erfragen.md`), Seiten-Inventar-Labels und
   Synonyme (`seiten-registry.md`) und vergleichbare Familien-Daten der
   anrufenden Buddy-App.

Darüber hinausgehende Familien-Daten werden nicht übermittelt. Alle drei
Kategorien verlassen die Geräte-Ebene der Familie; V1 übermittelt sie ohne
Anonymisierung — siehe Entscheidung E-EC-9 und Offener Punkt OPEN-EC-A.

Die Erweiterung um Kategorie 3 (Tool-Result-Texte) folgt aus dem
Eine-Stimme-Pattern (EC-29) und ist eine **ehrliche V1-Linie**, kein
Sicherheits-Versprechen für die Familien-Beta: V1 läuft mit Nic und
Testfeld; vor einer Familien-Beta ist die Privacy-Lage neu zu bewerten.
Die langfristige Sicherung liegt im **Anonymisierungs-Layer** und in der
**Datenverarbeitung in Deutschland** (OPEN-EC-A, Backlog) — beide bleiben
verbindliche Ziele, nicht V1-Bestandteil.

*Tickets:* #27, #551

### EC-14 — Anbieter nicht erreichbar
Schlägt der Aufruf des KI-Anbieters fehl oder bleibt aus, antwortet das System
dem Familienmitglied mit einem klaren Hinweis, dass die Anfrage gerade nicht
bearbeitet werden konnte, und bricht sauber ab. Es entsteht keine halbfertige
Aufgabe und keine stumme Nicht-Antwort.

Dauert ein Provider-Call länger als rund 5 Sekunden — die Sichtbarkeitsdauer
des Telegram-Typing-Indikators —, erneuert das System den Indikator
periodisch, solange der Call läuft, damit die Familie nicht vor scheinbarer
Stille sitzt. Das Renewal ist **Best-Effort**: es läuft in einem
Hintergrund-Thread; Fehler des Renewal-Calls brechen den Turn nicht ab. Siehe
auch EC-25 (Typing-Indikator als Komfort-Signal vor Bot-Nachrichten).

*Tickets:* #27 · #274

## 5. Konfiguration

### EC-15 — Konfigurationswerte
Das System wird je Instanz über Konfigurationswerte eingerichtet. Der Bot-Token
wird ausschließlich über eine Umgebungsvariable gesetzt. Der Anbieter-API-Key
und die Familien-Gruppen-Chat-ID kommen aus Umgebungsvariable/Konfiguration oder
werden per Onboarding gesetzt (siehe
[`eltern-chat-onboarding.md`](eltern-chat-onboarding.md)); fehlt der
Anbieter-API-Key auf beiden Wegen, läuft die Instanz im Onboarding-Modus
(ONB-1). Geheimnisse liegen nie in einer Datei im Repo (CLAUDE.md §8).

Die nicht-geheimen Werte leben in der Per-Instanz-Datei
`eltern-chat/config.json` (gitignored). Auflösung, Datei-Schlüssel, ENV-
Form und Priorität folgen der gemeinsamen Konvention CONFIG-5 (siehe
`conventions/config.md`); diese Tabelle nennt nur die Werte selbst
mit Default. Geheimnisse (Bot-Token, Anbieter-API-Key) und das Sperr-
Verhalten der Familien-Gruppe (ENV/Datei sperren, Onboarding-Bindung
nicht — ONB-6) sind Komponenten-spezifisch und liegen daneben.

| Name                       | Default                                     | Datei-Schlüssel         | Gesetzt durch (Onboarding-Schritt)             |
|----------------------------|---------------------------------------------|-------------------------|------------------------------------------------|
| Telegram-Bot-Token         | (Pflicht, kein Default)                     | — (nur ENV, Geheimnis)  | manuell beim Deployment (Geheimnis, CLAUDE.md §8) |
| Anbieter-API-Key           | (kein Default → Onboarding-Modus)           | — (nur ENV/Store, Geheimnis) | ONB-5 (Onboarding-Speicher)               |
| Familien-Gruppen-Chat-ID   | leer (→ ONB-6 bindet)                       | `family_group_chat_id`  | ONB-6 (Onboarding-Speicher; ENV/Datei sperren) |
| KI-Anbieter                | `claude`                                    | `provider`              | n/a (Default reicht)                           |
| Anbieter-Modell            | leer (→ Anbieter-Default)                   | `provider_model`        | n/a (Default reicht)                           |
| Gesprächskontext-Tiefe     | `40`                                        | `context_depth`         | n/a (Default reicht)                           |
| CA-Pfad                    | `../tools/ca/out/rootCA.pem`                | `ca_pem_path`           | n/a (Default reicht beim Standard-Layout)      |
| Familien-Origin (FAA, #215) | `http://127.0.0.1:5010`                    | `familie_origin_url`    | n/a (Default reicht beim Standard-Layout)      |
| Geraete-Origin (GAA, #215) | `http://127.0.0.1:5040`                     | `geraete_origin_url`    | n/a (Default reicht beim Standard-Layout)      |
| Panel-Origin (PAA, #183)   | `http://127.0.0.1:5041`                     | `panel_origin_url`      | n/a (Default reicht beim Standard-Layout)      |
| Plan-Origin (EC-21, #215)  | `http://127.0.0.1:5020`                     | `plan_origin_url`       | n/a (Default reicht beim Standard-Layout)      |
| Routine-Origin (RZS, #343) | `http://127.0.0.1:5050`                     | `routine_origin_url`    | n/a (Default reicht beim Standard-Layout)      |
| Photo-Origin (FSE, #393)   | `http://127.0.0.1:5051`                     | `photo_origin_url`      | n/a (Default reicht beim Standard-Layout)      |
| Icon-Such-Origin (RPS/ICONS-7, #354) | `http://127.0.0.1:5000` (Router)  | `icon_origin_url`       | n/a (Default reicht beim Standard-Layout)      |
| Seiten-Registry-Origin (SREG, #347) | `http://127.0.0.1:5042`            | `seiten_origin_url`     | n/a (Default reicht beim Standard-Layout)      |
| Display-URL-Origin (GAA-3.7) | leer (Bot gibt nur `/display/<id>` aus)   | `display_url_origin`    | — (offen, OPEN-EC-Origin; **Vorbedingung für SREG-5**) |
| Log-Level (LOG-1/LOG-4)    | `INFO`                                      | `log_level`             | n/a (Default reicht; Dev-Override per ENV/CLI) |

**Semantik von `context_depth`.** Der Wert zählt **Einzelnachrichten** — jeder
Tool-Turn (Aufruf und Ergebnis) zählt je 1, kein Gesprächsrunden-Paar. Seit
#310 (Tool-Turn-Persistenz) sind persistierte Tool-Turns dauerhaft Teil des
Verlaufs und verdünnen das sichtbare Gesprächsfenster. Der Default 40
kompensiert das (vorher: 20). Instanz-Betreiber können den Wert über
`ELTERNCHAT_CONTEXT_DEPTH` oder `context_depth` in der Konfigurationsdatei
überschreiben.

Werte, die nur als Code-Konstante existieren — ohne Override-Pfad — sind
Spec-Verletzung (CLAUDE.md §6 Daten vs. Code).

CLI-Flags sind `--config`, `--db`, `--store` als Test-Werkzeug, plus
`--log-level` als Dev-Override für LOG-4 (gleiches Vehikel wie bei
Router/Plan, vgl. `conventions/logging.md`).

Bot-Token (`ELTERNCHAT_BOT_TOKEN`) und Anbieter-API-Key
(`ELTERNCHAT_PROVIDER_API_KEY`, optional) sind Geheimnisse und stehen
in der EnvironmentFile des systemd-Service (`__XBUDDY_DATA__/eltern-chat/.env`,
SVC-5), nicht in `config.json` — der Loader berührt sie nie (CONFIG-3). Die
Familien-Gruppen-Chat-ID darf in `config.json` stehen (kein Geheimnis) oder im
Onboarding-Speicher (`onboarding-store.json`, ONB-6).

Auftrag #215 hat den FAA-/GAA-Schreibweg auf HTTP umgestellt (DCOMP-1):
statt eines `family_registry_path`/`geraete_registry_path` (Datei-Pfade)
zeigen `familie_origin_url`/`geraete_origin_url` heute auf die HTTP-API
der Familien-/Geraete-Komponente. Auftrag #348 hat den KAV-Schreibweg
ebenfalls auf HTTP migriert (PLAN-32): `plan_json_path` ist entfernt,
KAV schreibt die `kalender_id` ausschließlich via HTTP-PUT an den
Plan-Buddy (`/api/v1/plan/admin/kalender`).

*Tickets:* #27 · #33 · #179 · #215 · #312 · #348

### EC-16 — Gesprächs-Datenbank als Per-Instanz-Datei
Der dauerhafte Gesprächsverlauf (EC-6) liegt als Datei neben dem Code, je
Instanz separat verwaltet und per `.gitignore` aus dem Repo ausgeschlossen
(analog `routing.json`, ROU-18 in [`router.md`](router.md)). Fehlt die Datei
beim Start, legt das System sie leer an, statt abzubrechen — eine frische
Instanz ist ohne Vorarbeit lauffähig.

*Tickets:* #27

## 6. Tests

### EC-17 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec, die Code-Verhalten beschreibt, hat einen
automatisierten Test, der sie prüft (CLAUDE.md §6). Diese Verhaltens-Tests
laufen reproduzierbar und ohne Netz: Der KI-Anbieter wird durch eine
kontrollierte Doppelung ersetzt — nur so lassen sich die Regeln aus EC-12
(Berechtigung, Katalog-Grenze, Bestätigung) auch gegen fehlerhafte oder
absichtlich abwegige Modell-Ausgaben prüfen.

Daneben sind Läufe gegen einen **echten Anbieter** ausdrücklich vorgesehen, um
die Erkennungsqualität zu bewerten (etwa Termin-Erkennung aus Fotos,
Anbieter-Vergleich). Solche Läufe sind von der reproduzierbaren Suite getrennt,
brauchen einen API-Schlüssel und sind opt-in — sie sind kein verpflichtender
Bestandteil eines Standard-Durchlaufs.

*Tickets:* #27

---

## Offene Punkte

- **OPEN-EC-A — Anonymisierung.** V1 übermittelt Anfrage-Daten ohne
  Anonymisierung an den KI-Anbieter (EC-13, E-EC-9). Wann und wie ein
  Anonymisierungs-Schritt aktiviert wird — Pseudonymisierung von Namen und
  Orten vor dem Anbieter-Aufruf —, ist offen. Das Qualitätsattribut Privacy
  der Constitution (§3) verlangt ihn; die Umsetzung ist ein eigenes Ticket.

- **OPEN-EC-B — Rollen & Berechtigungen.** V1 unterscheidet keine Rollen —
  jedes Familienmitglied ist gleichgestellt (EC-3). Telegram liefert eine
  natürliche Quelle: Gruppen-Admin-Status (= Eltern) vs. normales Mitglied
  (= Kind). Eine spätere Sicherheits-Iteration kann darauf aufsetzen, etwa
  sensible oder schreibende Aufgaben nur für Admins.

- **OPEN-EC-Origin — Display-URL-Origin im Onboarding setzen.** EC-15
  führt `display_url_origin` als Per-Instanz-Wert (GAA-3.7). Für die
  Familien-Anlage muss er gesetzt sein, damit ausgeteilte Display-URLs
  direkt aufs Tablet getippt werden können. Heute wird er manuell beim
  Deployment in `eltern-chat/config.json` eingetragen — ein eigener
  Onboarding-Schritt, der ihn aus der Bot-Konfiguration zieht (Origin
  des HTTPS-Servers, auf dem der Bot läuft), ist offen.

- **OPEN-EC-LOG-STRUCT — LOG-Konvention für strukturierte Event-Nachrichten.**
  Zwei Stellen in Eltern-Chat schreiben Log-Nachrichten mit `event=… key=value`-
  Inhalt im `message`-Teil (EC-23-Telemetrie, E-EC-2-Pickup-Latenz). Das
  LOG-Format (LOG-1) regelt die Zeile; für den internen Aufbau von
  `message` bei strukturierten Events gibt es noch keine eigene
  Konvention. Sobald ein dritter strukturierter Event-Logger entsteht,
  ist eine LOG-Konvention (`event=key=value`) fällig. Heute zwei Vorkommen
  — kein Vorrat anlegen (CLAUDE.md §6).

---

## Entscheidungen

Architektur-Entscheidungen aus der Konzept-Session (Chat 2026-05-21),
festgehalten an der Spec, weil sie nicht aus dem Code ableitbar sind und für
Folge-Tickets load-bearing bleiben.

### E-EC-1 — Per-Familie-Deployment, host-agnostisch
*Datum:* 2026-05-21

Eine Instanz bedient genau eine Familie über einen eigenen Bot. Sie läuft auf
dem Hub der Familie — Pi (V1) oder Server, identische Software 1:1, kein
separater Cloud-Aufbau.

**Verworfen:** ein zentraler Multi-Tenant-Bot für alle Familien. Der hätte
familienübergreifende Bezeichner, Einladungs-Token und Deep-Links gebraucht,
um Chat-Identitäten Kunden zuzuordnen. Per-Familie bringt Mandantentrennung
durch Konstruktion — Privacy by construction — und passt zum Hub-Modell der
Constitution.

### E-EC-2 — Telegram als initialer Kanal
*Datum:* 2026-05-21

**Verworfen:** SMS, WhatsApp Business API, eine eigene Web-App. Telegram
gewinnt, weil die Bot-API trivial ist (einfacher Token, kein OAuth-Setup),
Polling ohne öffentlichen Webhook reicht, und Familien mit Smartphone Telegram
typischerweise schon haben. Der Kanal liegt hinter einer dünnen Adapter-Grenze
(siehe E-EC-6-Muster), damit weitere Kanäle später andocken können — ohne sie
auf Vorrat zu spezifizieren.

**Verfeinerung Polling-Backoff (#294):** Der `poll_loop` verwendet bei
aufeinanderfolgenden leeren oder fehlgeschlagenen `getUpdates`-Aufrufen
einen exponentiellen Backoff: Startverzögerung 1 s, Faktor 2, Cap 5 s.
Nach einem Update wird die Backoff-Pause auf 0 zurückgesetzt. Der
Long-Poll-`timeout`-Parameter für den Telegram-Server (standardmäßig 30 s)
ist davon getrennt — er steuert, wie lange Telegram auf neue Updates wartet,
bevor es eine leere Liste zurückgibt; die Backoff-Pause liegt danach und
betrifft nur den Abstand zum nächsten Poll-Aufruf bei Leerlauf/Fehler.

**Verfeinerung Pickup-Latenz-Logging (#294):** Der `poll_loop` misst
für jeden empfangenen Update-Batch die Latenz zwischen `getUpdates`-Rückkehr
(t0) und der Fertigstellung der Verarbeitung (t1) und schreibt sie pro Batch
als `INFO`-Eintrag gemäß LOG-1-Zeilenformat (`%(asctime)s %(levelname)s %(message)s`);
der `message`-Teil enthält strukturierten Inhalt im `event=… key=value`-Stil:
`poll event=pickup_latency count=N latency_ms=X`. Das ist die
**familienseitige Long-Poll-Pickup-Latenz** — von Telegrams Update-Lieferung
bis zum Ende unserer Verarbeitung — und ist bewusst von der
EC-23-Provider-Latenz (innerhalb eines Turns) abgegrenzt: EC-23 misst, wie
lange der LLM-Anbieter braucht; diese Metrik misst, wie schnell das System
auf ein eintreffendes Update reagiert.

### E-EC-3 — Berechtigung über Gruppen-Mitgliedschaft, live geprüft
*Datum:* 2026-05-21

Berechtigt ist, wer Mitglied der Familien-Gruppe ist; geprüft wird die
Mitgliedschaft je eingehender Nachricht live.

**Verworfen:** eine Config-Allowlist von Telegram-IDs — sie wäre eine zweite
Wahrheitsquelle neben der Gruppe und würde divergieren (CLAUDE.md §6). Ein
lokaler Mitglieder-Cache mit Austritts-Events liefert dieselbe Garantie ohne
API-Aufruf je Nachricht; er ist als spätere Optimierung vermerkt, nicht V1 —
für eine einzelne Familie ist der Aufruf je Nachricht vernachlässigbar. Die
Telegram-Bot-API erlaubt ohnehin keinen Abruf der vollständigen
Mitgliederliste, nur die Einzelprüfung eines Nutzers.

### E-EC-4 — Agent-zentriert, Sicherheits-Gates deterministisch
*Datum:* 2026-05-21

Ein einziger LLM-Agent führt den gesamten Dialog und wählt Aufgaben. Er
entscheidet aber keine sicherheitskritischen Schritte: Berechtigungsprüfung
(EC-2) und Bestätigung schreibender Aufgaben (EC-10) liegen außerhalb des
Agent-Loops — der Agent kann sie nicht umgehen, weil er sie nie aufruft.

**Verworfen:** zwei Extreme. Das eine — der LLM steuert auch Auth und
Bestätigung — wurde verworfen, weil ein halluzinierter Satz keine Berechtigung
erteilen oder eine Datenänderung auslösen darf. Das andere — ein separater
deterministischer Wizard neben dem Agenten — wurde verworfen, weil es den
Eltern zwei Bedien-Modelle zumutet. Lösung: ein Agent, Gates als Konstruktion.

### E-EC-5 — Eigener dünner Agent-Loop, kein Framework
*Datum:* 2026-05-21

Der Tool-Calling-Loop (Anfrage → Anbieter → Aufgabe ausführen → zurück) wird
selbst geschrieben.

**Verworfen:** ein Agent-Framework (LangChain o. ä.). Ein Framework bringt
seine eigene Anbieter-Abstraktion und sein eigenes Tool-Format mit und würde
genau die Austauschbarkeit untergraben, die EC-11/EC-12 fordern. Der Loop ist
klein genug, dass die Eigenleistung günstiger ist als die Fremdbindung
(CLAUDE.md §6, »nichts auf Vorrat«).

### E-EC-6 — KI-Anbieter hinter Adapter mit kanonischem Modell; V1 = Claude
*Datum:* 2026-05-21

Der Agent-Kern arbeitet ausschließlich mit einem kanonischen, anbieter-neutralen
Modell (Nachrichten, Aufgaben-Definitionen, Aufgaben-Aufrufe, Bilder). Ein
dünner Adapter je Anbieter übersetzt zwischen diesem Modell und der konkreten
Anbieter-API.

Dies ist das *Ergebnis* der Anforderungen EC-11 und EC-12. Die *Anforderung*
dahinter: Familien gewichten Datensicherheit unterschiedlich — die eine
akzeptiert Verarbeitung außerhalb der EU, die andere verlangt einen
EU-Anbieter oder lokale Verarbeitung. Der Adapter macht den Anbieterwechsel zu
einer Konfigurations-Änderung. V1 liefert den Claude-Adapter — beste
Erkennungsqualität für die Bewertungsphase; weitere Adapter (etwa Mistral)
folgen additiv, ohne auf Vorrat spezifiziert zu werden. Dasselbe Adapter/Kern-
Muster nutzt der Router (E-ROU-1).

### E-EC-7 — Bestätigung schreibender Aufgaben per Bestätigungswort
*Datum:* 2026-05-21

Die ausdrückliche Bestätigung aus EC-10 erfolgt als **Nachricht** an den Bot: ein
👍 oder eines aus einer festen Liste von Bestätigungswörtern, gerichtet auf den
konkreten Vorschlag — als Antwort auf die Vorschlags-Nachricht, oder, wenn im Chat
genau ein Vorschlag offen ist, auch ohne Antwortbezug. Die Liste ist fest
definiert: `👍` (auch mit Hautton-Modifikator), `✅`, `ok`, `okay`, `k`, `jo`,
`ja`, `japp`, `jepp`, `passt`, `mach`, `machen`, `go`, `gogogo`, `los` — Vergleich
case-insensitiv, ganzes Wort (keine Teilstring-Treffer).

Der Abgleich ist **deterministisch und liegt außerhalb des Agent-Loops** (E-EC-4):
Das Sprachmodell interpretiert die Zustimmung nicht. Sonst könnte ein
halluziniertes »Ja« eine Datenänderung auslösen — genau das schließt EC-12 aus.
Eine Nachricht, die keinem Bestätigungswort entspricht, ist keine Bestätigung; sie
wird als normale Anfrage an den Agenten behandelt und der offene Vorschlag bleibt
unbestätigt.

**Verworfen:** (1) 👍 als *Reaktion* statt als Nachricht — ein Bot empfängt
Reaktions-Updates in einer Gruppe nur als Administrator; das würde Gruppen-Admin-
Status des Bots erzwingen, was nicht für jede Familien-Gruppe gewollt ist.
(2) Inline-Buttons — funktional gleichwertig, aber die Nachricht-Variante ist
leichtgewichtiger und kanal-unabhängiger. (3) Freie LLM-Interpretation der
Zustimmung — bricht E-EC-4/EC-12.

### E-EC-8 — Gesprächsverlauf persistent ab V1
*Datum:* 2026-05-21

Der Gesprächsverlauf wird ab V1 dauerhaft in einer SQLite-Datei gehalten
(EC-16) und übersteht einen Neustart.

**Verworfen:** den Verlauf nur im Prozess-Speicher zu halten, wie der Router
seinen State (ROU-10). Ein nach einem Pi-Neustart abgerissenes Gespräch ist
für die Familie spürbar störender als ein verlorener Display-State; die
Persistenz ist mit SQLite günstig genug, um sie nicht zu vertagen.

### E-EC-9 — V1 ohne Anonymisierung
*Datum:* 2026-05-21 · *Schärfung 2026-06-09 (#485):* Bilder explizit eingeschlossen

V1 übermittelt **Anfrage-Inhalte einschließlich Bildern** (Text, Foto-Anhänge,
mitgesendete Aushang-Bilder im TAB-Skill, `termine-aus-bild.md`) ohne
Anonymisierung an den KI-Anbieter (EC-13). Die Klausel deckt damit auch
Bild-Daten ab — die 2026-06-09-Schärfung (#485) macht explizit, was vorher
nur als „Anfrage-Inhalte" textuell offen war.

Dies ist eine **bewusste, dokumentierte Abweichung** vom Qualitätsattribut
Privacy der Constitution (§3, »Anonymisierungs-Layer vor Verlassen der
Geräte-Ebene«). Sie ist befristet auf die Prototyp-/Bewertungsphase und
abgesichert durch die ausdrückliche Einwilligung der Test-Familien. Begründung:
Zuerst muss sich zeigen, welcher Anbieter taugt und wie der Datenfluss
tatsächlich aussieht — ein Anonymisierungs-Layer davor wäre Bau ohne belegte
Grundlage. Die Aktivierung ist als OPEN-EC-A festgehalten und bleibt eine
Voraussetzung für den Regelbetrieb über die Testphase hinaus.

**Ende der Bewertungsphase (Trigger):** Nic schließt OPEN-EC-A bewusst — das
ist der einzige Trigger. Ein messbarer Auto-Trigger (z. B. „nach N Monaten"
oder „bei erster Nicht-Test-Familie") ist **bewusst verworfen**: der
Anonymisierungs-Pfad steht und fällt mit der Anbieter-Wahl (OPEN-EC-A
abhängig vom getroffenen Multimodal-Anbieter — siehe `termine-aus-bild.md`
E-TAB-6 und #486 zu TAB-V2-Privacy), und ein Zeit-/Familien-Trigger ohne
gelöste Anbieter-Frage würde die Bewertungsphase abbrechen, bevor die
Grundlage für den Anonymisierungs-Layer da ist. Der Halt-Punkt für eine
Re-Bewertung dieses Triggers ist deshalb der OPEN-EC-A-Schluss durch Nic.

### E-EC-10 — Supergruppen-Migration wird automatisch nachgezogen
*Datum:* 2026-05-22

Migriert Telegram die Familien-Gruppe zu einer Supergruppe, zieht die Instanz
die geänderte Chat-ID selbsttätig nach (EC-18), statt sie als Betreiber-Aufgabe
zu behandeln.

**Verworfen:** die ID nach einer Migration von Hand in Konfiguration oder
Onboarding-Speicher nachzutragen. XBuddy läuft pro Familie auf einem eigenen
Hub (E-EC-1), oft ohne technische Betreuung. Eine Migration ist ein
unangekündigtes Telegram-Ereignis; bliebe sie unbehandelt, fiele der Bot ohne
für die Familie erkennbaren Grund und ohne Weg zurück aus. Das automatische
Nachziehen ist daher kein Komfort, sondern Voraussetzung für den unbetreuten
Per-Familie-Betrieb. Eine bewusst per Env/Config gesetzte Bindung bleibt
ausgenommen — dort hat der explizit gesetzte Wert Vorrang (EC-18).

Diese Entscheidung stammt aus dem #33-Live-Test (2026-05-22): die Gruppe der
Test-Familie migrierte währenddessen, der Bot fiel mit einer toten Chat-ID aus.

### E-EC-11 — Telemetrie-Wrapper im Agenten, Pricing-Tabelle als Konstante
*Datum:* 2026-05-30

Ein Wrapper um `provider.generate(...)` in `eltern-chat/agent.py` misst die
Wall-Clock per `time.monotonic()` und liest die Token-Counts aus dem Provider-
Response (anbieter-neutrales `ProviderUsage`-Feld). Die Pricing-Tabelle steht
als Konstante in `eltern-chat/providers/pricing.py` pro Modell-ID
`(input_per_million, cached_input_per_million, output_per_million)` in USD;
der EUR-Wechselkurs ist eine feste Konstante `1.0` (V1-Vereinfachung). Die
Persistenz liegt in `conversations.db` in einer eigenen Tabelle
`provider_calls`, verknüpft über `turn_id` und `chat_id`. Der Suffix
`— ⏱ X.Xs · 🪙 X.Xk tok · ≈ X.XXX €` wird in der Orchestrierung an die
gesendete Bot-Antwort angehängt — Aggregation pro Turn (Summe aller Provider-
Calls in `run_turn`), nicht pro Einzel-Call.

**Verworfen:** (1) eine Live-EUR/USD-Rate von einem Wechselkurs-Dienst — die
Telemetrie ist Diagnose-Werkzeug für die Bewertungsphase; eine schwankende
Rate wäre Bau ohne belegte Notwendigkeit, ein weiterer Außenabhängigkeit.
Eine spätere Iteration kann hier ohne Schnittstellen-Bruch eine echte Rate
einziehen. (2) Annotation pro Einzel-Call statt pro Turn — der Familie hilft
die Gesamt-Wartezeit eines Turns, nicht die Aufschlüsselung in Tool-Loop-
Schritte. Die Per-Call-Aufschlüsselung lebt in der DB (V2 aggregierte Sicht).
(3) Suffix in den Verlauf persistieren — das hätte den Bot-Wortlaut um
Diagnose-Daten kontaminiert; Folge-Turns würden den Suffix als »Bot sagt« in
den Anbieter-Kontext mitnehmen. Der Suffix kommt deshalb NUR an die
Telegram-Sendung (siehe EC-23).

### E-EC-12 — IPv4 für den Telegram-Transport (intermittentes IPv6-Blackhole)
*Datum:* 2026-06-01

Gemessen (/arbeitstag 2026-06-01, instrumentierte Probe, 110 Verbindungsversuche zu `api.telegram.org`): 10 von 110 (≈9 %) liefen über IPv6 in den 35-s-Socket-Timeout (TimeoutError beim TCP-Connect), danach verband IPv4 in 0,0 s. DNS, TLS, Send, Recv durchweg <0,2 s — einziger langsamer Schritt war der IPv6-Connect. Der Hub löst `api.telegram.org` IPv6-zuerst auf (Tailscale-MagicDNS), der native IPv6-Egress ist zeitweise tot. Das zeigte sich der Familie als „eingefrorener" Bot: zufällig fehlendes „tippt" und Antwort-Latenz bis über eine Minute, obwohl der KI-Anbieter durchweg in Sekunden antwortete.

**Entscheidung:** Der Telegram-Client verbindet über IPv4.

**Verworfen:**
- *IPv6 auf dem Pi abschalten / `/etc/gai.conf`* — Familie-1-Hack: gälte nur für unseren Pi; jede Familie hätte das Problem neu auf ihrem Heim-Router. Robustheit gehört in den Code, der bei jeder Familie gleich greift (Familie-3-Probe).
- *Dual-Stack mit kurzem Connect-Timeout + Fallback* — behält IPv6, kostet aber weiter ~3 s in ~9 % der Fälle, ohne dass IPv6 für einen ausgehenden Client zu einer großen, dual-stack-fähigen API einen konkreten Vorteil bringt.
- *Happy Eyeballs (RFC 8305, paralleler v6/v4-Connect)* — korrekt, aber für einen Heim-Bot zu einer bekannten API Über-Engineering.

IPv4 ist für einen ausgehenden Client zu Telegram der universell zuverlässige Pfad; IPv6' Vorteile (Adressraum, eingehende Erreichbarkeit ohne NAT) greifen hier nicht.

**Offen/Folge:** Trifft derselbe Blackhole später einen anderen ausgehenden Pfad (Plan→Google-Kalender, Anbieter-LLM — heute nicht beobachtet), wird eine komponentenübergreifende Transport-Bauregel in `conventions/` erwogen — nicht auf Vorrat.
