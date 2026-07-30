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
— je nach Petrarbeitungsdauer mehrere Sekunden, ohne Signal, dass der Bot noch
aktiv ist. Mit EC-25 erscheint sofort das „tippt gerade"-Signal im Privatchat,
bevor die Bot-Antwort kommt. Das reduziert Verwirrung bei längeren
Provider-Calls (EC-14, EC-11), ohne die Latenz zu verändern.

Code-Verweise, die heute den Typing-Indikator an EC-14 koppeln, werden auf EC-25
umgezeigt — das ist Aufgabe der Code-Tracks, nicht dieser Spec.

**Quer-Verweis EC-39 (2026-06-19; ENTSCHEID-File Paket-Sektion „R2-Paket →
B) Spec-Patch-Skizze" → EC-N3-Klausel;
`brainstorm/berater-runde/2026-06-19-1545-RATIFIZIERT-polling-reader-typing.md`):**
EC-25 deckt Typing **innerhalb** einer mehrstufigen Schreib-Aufgabe ab
(Session-intern, nach Auth, im Agent-Loop). EC-39 ergänzt das **Sofort-
Typing bei Empfang** — gesendet vom Polling-Reader direkt nach
`getUpdates`, **vor** der Auth- und Agent-Petrarbeitung — gilt ebenfalls
nur für Privatchats. Beide Pfade können parallel laufen
(Telegram-`sendChatAction` ist idempotent).

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
**Skill-Petrantwortung**: der Skill muss in dieser Nachricht alle dynamischen
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
**User-tauglichen Antwort-Text als Tool-Result**; das LLM petrarbeitet
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
Versand** Skill-Petrantwortung — das LLM hat keine Datei-Sende-Mechanik.
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

**A2-Klausel — Sofort-Write + Quittung + Undo-Wort (enger Default).**
Für eine eng umrissene Klasse schreibender Aufgaben tritt der Default
**Sofort-Write + Quittung + Undo-Wort** an die Stelle des Vorab-Confirm-
Pfads. Die Klausel gilt **nur** für Schreibakte, die alle drei
folgenden Bedingungen erfüllen:

1. Der Schreibakt **legt eine Ressource mit stabiler ID an** (nicht:
   ändert einen vorhandenen Wert, nicht: löscht eine Reihe).
2. Der **Inverse** des Schreibakts ist ein **idempotentes `DELETE`**
   auf genau diese ID — der Skill hat einen erreichbaren Inverse-
   Aufruf an der Buddy-API (vgl. TASK-9).
3. Der Skill **weist den Inverse-Aufruf vor erstem Live-Einsatz** im
   Test nach (**Pre-Flight-Check**): ein Test legt eine Ressource an,
   ruft das Inverse-`DELETE` auf, prüft die Bestätigung der API. Ohne
   diesen Test darf der Skill nicht im Sofort-Write-Default laufen.

**Konkret freigegeben unter A2:** `einkauf_hinzufuegen`,
`foto_senden`. **A2-Kandidat (zweistufig bis Plan-Buddy-DELETE
landet):** `termin_eintragen` — Bedingung 2 (idempotentes DELETE auf
die Termin-ID) ist mangels Plan-Buddy-DELETE-Endpunkt noch nicht
erfüllt (`specs/platform/termin-eintragen.md:44-47`); der Skill läuft
daher `propose`/`execute`-zweistufig bis der Delete-Track landet.
Alle anderen schreibenden Aufgaben bleiben **bei der zweistufigen
Variante** (Vorab-Confirm, unten). **Explizit ausgenommen vom
A2-Default** bleiben die Klasse-E-Auth-Loops `anbieter_wechseln` und
`kalender_verbinden` — ihr eigener Abschluss-Gate-Pfad ist gewollt
und wird durch A2 nicht ersetzt.

**Undo-Wort-Disziplin — letzter Schreibakt, Versiegelung durch
Folge-Anfrage.** Das Undo-Wort gilt **nur auf den letzten Schreibakt
im selben Chat-Faden**. Die **nächste inhaltlich folgende Anfrage
versiegelt** den vorherigen Schreibakt — nur ein dazwischengeschobenes
explizites Undo greift noch.

**Undo-Wort + Quittungs-Anleitung — eindeutig statt breit.** Das
Undo-Wort ist konstant **`falsch`** — ein einziges, nicht polysemes
Wort. Alltags-Ablehnungen wie `nein` sind **ausgeschlossen**, damit
kein beiläufiges Nein einen Schreibakt kippt. Die A2-Quittung
**enthält das Undo-Wort explizit und nennt den Effekt** in einem
Satz, z. B.: „Ich habe X eingetragen. Wenn das ein Missverständnis
war, sag einfach `falsch`, ich mach es dann rückgängig." Die Familie
erlernt das Undo-Wort durch den ersten Schreibakt; eine separate
Bedienungs-Doku ist nicht nötig. Die konkrete Formulierung der
Anleitung darf der Skill wählen (Stimme passt zum Skill), das
Undo-Wort selbst und seine sichtbare Nennung in derselben Quittung
sind verbindlich.

**Quittung trägt geparste Schlüssel-Werte prominent zuerst** —
nicht den Roh-Text des Anstoßes. Welche Werte prominent sind, hängt
vom Skill ab (Termin: Datum + Uhrzeit; Einkauf: Item-Name; Foto: was
gespeichert wurde) — die einzelne Skill-Spec kann ihre Form
schärfen. Die Quittung ist die Wahrheit für die Familie; ein
dahinterliegender Schreibakt, der nicht in der Quittung steht,
existiert für sie nicht.

**Undo-Bindung ist deterministisch, nicht LLM-gewählt.** Das
Undo-Wort wird **vor dem Agenten** an einen persistenten
**A2-Receipt-Datensatz** gebunden — das LLM entscheidet **nicht** über
Ziel oder Ressource des Undo. Der konkrete Vor-Agent-Hook ist
Code-Track-Sache und nicht Teil dieser Spec; die Spec normiert nur
das Soll (Undo bindet auf den persistierten letzten erfolgreichen
Schreibakt der A2-Klasse, nicht auf eine LLM-Interpretation des
Verlaufs).

**A2-Receipt — der Kassenbon (#841, 2026-06-15).** Pro erfolgreichem
A2-Schreibakt schreibt das Framework einen **persistenten Datensatz**
(`a2_receipts` in derselben SQLite-Datei wie EC-35-`task_events` —
`conversations.db`) mit:

- **`task_name`** — Skill-Name (`einkauf_hinzufuegen`, `foto_senden`, …)
- **`chat_id`** — Chat-Faden, in dem die Quittung gilt
- **`resource_id`** — die konkrete Ressourcen-ID, die durch den
  Inverse-Aufruf rückgängig gemacht werden kann
- **`inverse_call`** — strukturierter Verweis auf den Inverse
  (Buddy-Endpunkt + Pfad-Parameter), den der Vor-Agent-Hook
  deterministisch ausführen kann
- **`committed_at`** — Zeitpunkt des erfolgreichen Schreibakts
- **`expires_at`** — NULL für rein-interne Schreibakte (gilt bis
  Versiegelung); gesetzter Zeitstempel für Schreibakte gegen
  **externe APIs** (siehe „Intern vs. extern" unten)
- **`sealed_at`** — NULL, solange `falsch` noch greift; gesetzt bei
  Versiegelung (siehe übernächster Absatz)

Ein A2-Schreibakt mit **mehreren** Ressourcen (Multi-Item — z. B.
`einkauf_hinzufuegen` mit drei Items) schreibt **eine Receipt-Zeile
pro Ressource**. `falsch` ruft dann **alle** zugehörigen
Inverse-Aufrufe; der Bot quittiert, was tatsächlich rückgängig wurde
(zweistufig, ehrlich: „Brot und Milch wieder weg, Joghurt klemmt —
bitte manuell prüfen", EC-7).

**Versiegelung — wann der Kassenbon nicht mehr eingelöst wird.** Die
nächste **inhaltlich folgende Anfrage** in demselben Chat-Faden
versiegelt alle unversiegelten Receipt-Zeilen des Vor-Schreibakts
(setzt `sealed_at`). `falsch` greift dann nur noch auf den **neuen**
letzten Schreibakt — die alten Bons sind „verbraucht" und können
nicht mehr per `falsch` angefasst werden. Das ist die mechanische
Form der Versiegelungs-Klausel oben.

**Intern vs. extern — Lebensdauer-Differenzierung pro Schreib-Ziel
(#841, 2026-06-15).** Die **Customer-Journey-Wortlaute sind identisch
für alle A2-Skills** („Wenn falsch, sag »falsch«"); die mechanische
Lebensdauer des Receipts ist aber an das Schreib-Ziel gekoppelt:

- **Intern (xbuddy-eigener Buddy als Konsument, `conventions/apps.md`
  APP-3):** `expires_at = NULL`. Der Bon gilt bis zur Versiegelung
  durch die nächste inhaltlich folgende Anfrage. Begründung: Niemand
  außer xbuddy selbst kann die Ressource zwischenzeitlich verändern;
  ein DELETE auf die im Bon gespeicherte ID ist deterministisch
  korrekt. Beispiele heute: `foto_senden` (Photo-Buddy intern),
  `einkauf_hinzufuegen` (Essens-Buddy intern).

- **Extern (Konsument schreibt seinerseits gegen einen Drittanbieter —
  Plan-Buddy gegen Google Calendar / iCal; künftige Buddies gegen
  externe APIs):** `expires_at = committed_at + Default-Fenster`
  (V1: **5 Min**, später Config-tunable bei n=2-Schmerz). Nach Ablauf
  greift `falsch` **nicht mehr** — der Bot quittiert mit EC-7-Form:
  „Eintrag ist schon eine Weile her — bitte direkt an der Quelle
  (Kalender, …) korrigieren." Begründung: Externe Aktoren können den
  Schreibakt zwischenzeitlich verändert oder verschoben haben (User
  am Smartphone öffnet Google Calendar manuell); ein DELETE auf die
  gespeicherte ID kann dann **die User-Korrektur zerstören**, statt
  den ursprünglichen Akt rückgängig zu machen. Das kurze Fenster
  begrenzt die Wahrscheinlichkeit dieser Race auf das Minimum, ohne
  die Customer-Journey zu brechen. Beispiele heute: `termin_eintragen`
  (Plan-Buddy → externer Kalender-Provider).

**Ambiguitäts-Quittung bei nicht-eindeutigem DELETE (#841, 2026-06-15).**
Liefert der Inverse-Aufruf einen **unklaren Erfolg** — HTTP 404
(Ressource bei externer Quelle schon weg), HTTP-Konflikt (Ressource
verändert), Provider-Fehler ohne klare Zustands-Bestätigung —
quittiert der Bot **ehrlich** (EC-7-Linie): „Konnte den Eintrag nicht
zweifelsfrei zurücknehmen — bitte selbst an der Quelle prüfen."
Schreibakt selbst gilt dann als nicht-eindeutig-rückgenommen; der
Receipt-Eintrag wird **trotzdem** mit `sealed_at` versiegelt (kein
zweiter `falsch`-Versuch auf denselben Bon). Nur ein sauberer 200 OK
(oder Provider-Äquivalent) erlaubt die positive Quittung „Termin
wieder weg." Das gilt für **intern und extern**, fällt mechanisch
aber nur bei externen Schreibakten realistisch an.

**Wer schreibt einen Bon — wer nicht.** Nur A2-Skills mit
**erreichbarem Inverse** (Bedingung 2 der A2-Klausel: stabile ID +
idempotentes DELETE) schreiben einen Receipt-Eintrag. Hat ein Skill
keinen Inverse-Vertrag heute, liegt das entweder am **Konsumenten**
(Plan-Buddy hat noch keinen DELETE-Endpunkt für Termine —
`specs/platform/termin-eintragen.md:44-47`, Folge-Track beim
Plan-Buddy ergänzt das, damit `termin_eintragen` mit
`expires_at = +5 Min` als externer Schreibakt im A2-Receipt-Pfad
läuft) oder an der Skill-Eigenschaft selbst (TASK-9-Pattern, kein
DELETE-Verlangen). Skills ohne Inverse trägt **kein** `falsch`-Wort
in der Quittung; die Familie korrigiert über die zweistufige
Variante (Confirm vor Schreib, EC-2X Welle 3).

**Statistik-Nebennutzen (kein V1-Feature).** Das Receipt-Datenmodell
zusammen mit EC-35-`task_events` ermöglicht später Auswertungen
(Call-Dauer pro Skill, Häufigkeit, Fehlerraten, Undo-Quote pro Skill).
V1 baut **keine** Auswertungs-Schnittstelle; die Spec petrankert nur,
dass das Schema diese Auswertung **erlaubt**, ohne sie zu erzwingen.
Eine konkrete Statistik-Funktion entsteht erst beim ersten Vorkommen
mit belegtem Bedarf (CLAUDE.md §6).

*Test-Implikation:* ein A2-Schreibakt mit drei Ressourcen schreibt
drei Receipt-Zeilen mit identischer `committed_at` und denselben
`task_name`/`chat_id`-Werten; eine **Folge-Anfrage** im selben Chat
setzt `sealed_at` auf alle drei. `falsch` **nach** der Folge-Anfrage
greift auf die Receipt-Zeilen der Folge-Anfrage, nicht der alten.

*Tickets:* #841 (A2-Receipt-Naht + Multi-Item-Migration +
Pre-Flight-Tests) · #721 (deterministischer Undo-Hook bindet an
`a2_receipts` statt `task_events`).

**Zweistufige Variante als Default für alles andere.** Liefert der
Anstoß einer **nicht-A2**-Schreibaufgabe alle Pflicht-Felder, kombiniert
der Bot Daten-Übersicht und Bestätigungs-Frage zu **einer** Nachricht
und fordert in derselben Nachricht das Bestätigungswort (E-EC-7) —
das ist die bisherige Ein-Schritt-Bestätigung, aber nun für die
zweistufige Variante reserviert. Ist der Anstoß unvollständig
(mindestens ein Pflicht-Feld fehlt oder ist mehrdeutig), fragt der
Bot erst gezielt nach (EC-22) und legt den strukturierten Vorschlag
erst vor, sobald alle Pflicht-Felder geklärt sind. Das Schreib-Gate
selbst (Ausführung erst nach ausdrücklicher Bestätigung) bleibt
vollständig erhalten — keine Änderung an der Sicherheits-Garantie für
nicht-A2-Aufgaben.

Die zweistufige Variante gilt für alle schreibenden Aufgaben außerhalb
der A2-Klasse (FAA, GAA, KAV — Klasse E mit eigenem Abschluss-Gate —,
TES außerhalb des A2-Falls und künftige Aufgaben desselben Musters).

**Single-Slot-Pending-Politik in der zweistufigen Variante.** Pro
Chat-Faden hält der `PendingStore` zu jeder Zeit **genau einen**
offenen Vorschlag der zweistufigen Variante. Trifft ein neuer
zweistufiger Vorschlag ein, während ein älterer noch unbestätigt
ist, **verdrängt** der neue den alten — der alte gilt als verfallen,
ohne Schreibakt. Der Bot quittiert die Verdrängung in einem Satz mit
den geparsten Schlüssel-Werten beider Vorschläge, z. B.: „Vorschlag
‚Tafel-Geburtstag Mi 19 Uhr' verfällt — neuer Vorschlag
‚Geburtstag Sa 14 Uhr' wartet auf `ja` oder `falsch`." Damit ist
die Bestätigung **immer eindeutig genau einem Vorschlag zugeordnet**:
wer „ja" sagt, bestätigt den jüngsten und einzigen aktiven Vorschlag.

A2-Aufgaben (Sofort-Write + Quittung + Undo-Wort) sind von dieser
Politik nicht betroffen — sie legen direkt eine Ressource an und
versiegeln den vorigen Schreibakt durch die nächste inhaltliche
Anfrage.

**Verworfen:** (a) **Latest-wins** bei „ja" ohne Reply (jüngster
Pending gewinnt) — bricht die EC-10-Garantie „eindeutig einem
konkreten Vorschlag zugeordnet"; (b) **Agent-Gate** (Agent darf
keinen zweiten Vorschlag produzieren, solange einer pendet) — koppelt
die Mechanik an LLM-Compliance und blockt die Familie an einem
unbeantworteten Stapel; (c) **Stapel mit ID-Markierung in der
Bestätigung** — überfrachtet die Bot-Nachricht und verlangt von der
Familie, Vorschlags-IDs zu zitieren.

*Was sich für die Familie ändert.* Bei A2-Aufgaben antwortet der Bot
auf einen vollständigen Anstoß („Mittwoch 19 Uhr Pauls
Geburtstagsfeier") direkt mit der Quittung — der Termin steht. Ein
nachgeschobenes „doch nicht" innerhalb desselben Fadens kippt ihn.
Die nächste inhaltlich folgende Anfrage versiegelt die Quittung; danach
greift „doch nicht" nicht mehr. Bei allen anderen Schreibakten bleibt
die Vorab-Bestätigung wie bisher.

**Begründung — Trade-off.** Vorab-Confirm ist konservativ sicher, fühlt
sich bei vollständigem Anstoß aber wie ein unnötiger Zwischenschritt
an. Die enge A2-Klausel (One-Shot + stabile ID + idempotentes DELETE +
Pre-Flight) macht den Sofort-Write riskoarm, weil das Rückgängigmachen
durch Konstruktion möglich ist — und auf genau diese Klasse begrenzt.

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
Bestätigung ausführen" formuliert sein — beides petranlasst das Modell, auf ein
externes „Ja" zu warten, statt das Werkzeug bei erneutem Anlauf erneut
aufzurufen. Der Text ist per Aufgaben-Name parametrisiert, damit das Modell
erkennt, WELCHES Werkzeug erneut aufzurufen ist. Das deterministische
Schreib-Gate (Ausführung erst nach Bestätigung, `confirm.py`) bleibt davon
unberührt — es wird im Code erzwungen, nicht über diesen Text.

**Drei-Phasen-Klausel — Lese vor Schreib (Multi-Item-Lösch und ähnliche
mehrstufige Auswahl-Skills, V1.2 2026-06-21).** Für Skills, die vor dem
Schreib-/Lösch-Akt eine Auswahl aus einer dynamischen Liste verlangen
(`gericht-loeschen` als n=1), gilt ein erweiterter Vorab-Confirm-Pfad in
drei Phasen:

1. **Lese-Phase.** Skill ruft die GET-API des Buddys, holt die aktuelle
   Liste (Items mit ID + Name), präsentiert sie der Familie **nummeriert**.
2. **Auswahl-Phase.** Familie antwortet in **Freitext** — Ordnungszahlen
   („5 und 7"), Item-Namen („spaghetti und lasagne") oder Mischformen
   („die erste und die Lasagne") sind alle erlaubt. Der Skill sendet
   Liste + Freitext-Antwort an das LLM, das eine **strukturierte
   ID-Liste** als JSON-Array zurückgibt. Bei Ambiguität (zwei
   gleichnamige Items) fragt der Skill nach.
3. **Schreib-Phase.** Skill legt einen strukturierten Vorschlag mit den
   ausgewählten Items vor und ruft den Inverse-`DELETE` (bzw. analogen
   Schreibakt) erst nach Bestätigung. Die A2-Klausel greift hier **nicht**
   — die Auswahl-Phase ist per Definition mehrstufig, kein Sofort-Write.

**Auswahl-Vertrag mit dem LLM:** Eingabe = nummerierte Liste + Freitext.
Ausgabe = JSON-Array von Item-IDs (`["id1", "id7"]`). Die Bindung läuft
ausschließlich über IDs aus der Eingabe-Liste — eine ID, die nicht in
der Eingabe war, ist ein Fehler (Skill fragt nach), damit Namens-Drift
oder LLM-Halluzination den Schreib-Vertrag nicht brechen.

*Pattern-Vorbild* für künftige Multi-Item-Lösch-Skills
(`termin-loeschen`, `plan-aktivitaet-loeschen`). Wenn n=2 erreicht ist,
wandert die Klausel in eine eigene Convention.

*Tickets:* #27 · #266 · #278 · #331 · #816 (Drei-Phasen, n=1
`gericht-loeschen`) · #TBD-A2 (Deterministischer
Undo-Hook + `task_events`-Bindung), #TBD-A2-Pre-Flight (Pre-Flight-Test
des Inverse-Aufrufs für `termin_eintragen`, `einkauf_hinzufuegen`,
`foto_senden`)

### EC-20 — Mehrstufige Aufgaben überfluten die Familien-Gruppe nicht

Eine schreibende Aufgabe, die mehrere Antworten der Familie braucht — Familie
anlegen, Gerät anlegen, Kalender verbinden, künftig Controller einrichten —
führt der Bot im **Privatchat** mit dem anfragenden Familienmitglied weiter.
Die Familien-Gruppe sieht nur den Anstoß und das Ergebnis — nicht
Foto-Uploads, Eingaben, Zwischennachfragen. Der Bot behält den Gesprächsfaden
dieses Privatchats, auch wenn dazwischen andere Anfragen aus der Gruppe
kommen.

**Phasen-Klausel — Timeout-Reaktion hängt von der Phase ab.** Das
Session-Timeout (~30 Minuten ohne Familien-Antwort, technisch
`next_message() is None`) reagiert phasenabhängig:

- **In den Vor-Schreib-Phasen** — Pflichtfeld-Klärung, propose-Phase,
  Confirm-Phase: der Bot **sendet eine User-Quittung** an die Familie:
  „Hab dich aus den Augen verloren — wenn du noch willst, sag's
  nochmal." Keine stillen Aborts mehr. Die Familie weiß, dass der
  Faden hier endet, und kann ihn neu anstoßen.
- **Nach erfolgreichem Schreibakt** — die Aufräum-Phase ab dem
  Quittungs-Send (auch wenn Post-Execute-Hooks noch laufen, siehe
  TASK-6): der Bot **schweigt**. Die A2-Quittung (oder die
  Abschluss-Quittung des Confirm-Pfads) ist die User-sichtbare
  Wahrheit; eine zusätzliche „aus den Augen verloren"-Nachricht
  nach erfolgreicher Schreibung wäre irreführend.

**Umsetzungs-Anker.** `PrivateChatSession` bekommt einen
**phasenbewussten** Timeout-Helper, der dem Skill je nach Phase die
richtige Reaktion auf das Timeout liefert. Der konkrete Helper-Name,
seine Signatur und die Migrations-Welle der heute existierenden
Skills (FAA, GAA, KAV, TES, PAA, künftig Controller) sind
**Code-Track-Sache** — die Spec spezifiziert das Soll (Quittung vor
Schreibakt, Schweigen nach Schreibakt), nicht die Mechanik.

Die Aufgabe kann jederzeit neu gestartet werden — sowohl nach einer
Vor-Schreib-Quittung als auch nach einer Aufräum-Phase, in der die
Schreibung bereits erfolgreich war (für eine zweite Anlage gilt
EC-10 erneut).

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
Session-Klasse statt drei kopierter Worker-Loops; #TBD-A6 (Phasen-Helper
in `PrivateChatSession` + Migration der sechs Skills).

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
Welcher KI-Anbieter die Anfragen einer Familie petrarbeitet, ist je Instanz
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
**Datenpetrarbeitung in Deutschland** (OPEN-EC-A, Backlog) — beide bleiben
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
[`eltern-chat-onboarding.md`](eltern-chat-onboarding.md)); fehlt für den
aktiven Anbieter ein API-Key auf beiden Wegen, läuft die Instanz im
Onboarding-Modus (ONB-1). Geheimnisse liegen nie in einer Datei im Repo
(CLAUDE.md §8).

**Multi-Vendor-Slot-Adressierung (#663).** Der Anbieter-API-Key wird im
zentralen Zugangsdaten-Speicher unter dem vendor-spezifischen Slot
`eltern-chat-<vendor>-api-key` abgelegt (`zugangsdaten.md` ZD-2 Multi-Slot-
Schema). Der `provider`-Wert in der Konfiguration entscheidet, welchen
Slot der Eltern-Chat zur Laufzeit liest. Ein Wechsel des aktiven Anbieters
auf einen bereits eingerichteten Vendor (vorhandener Slot) braucht keinen
Re-Key (ONB-11 Pfad A); ein erster Wechsel auf einen neuen Vendor läuft
die Re-Key-Sequenz (ONB-11 Pfad B). Der vendor-spezifische Slot
(`eltern-chat-<vendor>-api-key`) ist der Laufzeit-Standard seit Welle A.
Der Single-Slot `eltern-chat-provider-api-key` bleibt als Legacy-Fallback
für alte Instanzen lesbar; Welle B wird ihn entfernen.

Die nicht-geheimen Werte leben in der Per-Instanz-Datei
`eltern-chat/config.json` (gitignored). Auflösung, Datei-Schlüssel, ENV-
Form und Priorität folgen der gemeinsamen Konvention CONFIG-5 (siehe
`conventions/config.md`); diese Tabelle nennt nur die Werte selbst
mit Default. Geheimnisse (Bot-Token, Anbieter-API-Key) und das Sperr-
Verhalten der Familien-Gruppe (ENV/Datei sperren, Onboarding-Bindung
nicht — ONB-6) sind Komponenten-spezifisch und liegen daneben.

| Name                       | Default                                     | Datei-Schlüssel         | Gesetzt durch (Onboarding-Schritt)             |
|----------------------------|---------------------------------------------|-------------------------|------------------------------------------------|
| Telegram-Bot-Token         | (Pflicht, kein Default)                     | — (nur ENV/Store `eltern-chat-bot-token`, Geheimnis) | manuell beim Deployment (Geheimnis, CLAUDE.md §8) |
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
| Icon-Such-Origin (RPS/ICONS-7, #354) | `http://127.0.0.1:5042` (Seiten-Registry, seit RAT-31/#1568) | `icon_origin_url`       | n/a (Default reicht beim Standard-Layout)      |
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

## 7. UI-Pattern (Chat ↔ WebApp)

Diese drei Punkte (EC-33, EC-34, EC-35) entstehen aus der ratifizierten
Berater-Runde vom 2026-06-12 (Eltern-Chat UI-Pattern). Sie regeln, wann
eine Aufgabe als WebApp statt als Chat-Dialog läuft (EC-33), wie
Chat-Skills auf WebApp-Pendants anderer Skills hinweisen (EC-34) und
welche Telemetrie das stützt (EC-35). Ohne diese Linie driften die
heute 24 Eltern-Chat-Skills UI-uneinheitlich weiter (Confirm-Form,
Tool-Result-Vertrag, Medien-Wahl).

### EC-33 — UI-Medien-Schwelle: Chat oder WebApp

Ob eine Aufgabe als **Chat-Dialog** oder als **WebApp** (Mini-App im
Telegram-Sinne, siehe `conventions/mini-app-design.md`) läuft,
entscheidet eine **deterministische Schwelle pro Anstoß**:

- **Pro Anstoß ≥5 Einzelwerte** ODER **≥2 Spalten/Achsen** in einer
  Bearbeitung → **WebApp**.
- Sonst → **Chat**.

Die Schwelle ist ablesbar am Anstoß selbst (Anzahl Werte, Anzahl
Achsen) — sie braucht keine Telemetrie und keine Modell-Interpretation.

**Häufigkeit ist KEIN Schwellen-Kriterium.** Sie ist ausschließlich
Bau-Priorisierungs-Signal: was die Familie wöchentlich anfasst, wird
zuerst gebaut. Welche Aufgabe heute als WebApp existiert, sagt nichts
über die Schwelle für eine andere Aufgabe.

**Sonderfall Geheimnis/Identität.** Wo eine Aufgabe ein Geheimnis
verteilt oder eine Identität nachweist (heute: CA-Verteilung,
`specs/platform/ca-verteilung.md` CAV-4) bleibt sie **Skill-direkt** —
kein LLM-Pass über den Tool-Result, kein WebApp-Pendant. Der
Sonderfall geht der EC-33-Schwelle vor.

**Anwendungs-Liste (Stand heute):**

- **WebApp-Kandidaten** (≥5 Werte oder ≥2 Achsen pro Anstoß):
  `routine_punkte_setzen` (Voll-Liste), `plan_aktivitaeten_setzen`,
  `wuensche_zeigen` + Edit, `seiten_uebersicht` (Geräte-Review),
  `termine_aus_bild` (Bulk-Review).
- **Chat-Aufgaben** (unter der Schwelle):
  `einkauf_hinzufuegen` (1 Item pro Anstoß), `termin_eintragen`
  (1 Termin pro Anstoß), `familie_anlegen`, `geraet_anlegen`,
  `kalender_verbinden`, `anbieter_wechseln`, `panel_anlegen`.

**Was sich für die Familie ändert.** Eine zwölfteilige Morgenroutine
gleichzeitig anzupassen ist im Chat zäh (zwölf Rückfragen oder ein
unleserlicher Sammel-Block); in einer WebApp mit Cards steht alles
auf einmal vor der Familie. Einen einzelnen Termin im Chat
eintragen — Vollständig-Anstoß, Quittung, fertig — ist umgekehrt
schneller als jedes UI-Öffnen.

**Begründung — Trade-off.** Eine Häufigkeits-Schwelle (z. B. ≥1×/Woche
in den letzten drei Wochen) wurde verworfen: sie schließt seltene,
aber dichte Pflege aus (Routine zum Schuljahreswechsel) und braucht
mindestens drei Wochen Telemetrie, bevor sie überhaupt anwendbar ist.
Die Komplexitäts-Schwelle ist sofort und für jeden Anstoß ablesbar.

*Tickets:* #TBD-A1 (Routine-Mockup-Probe A7.1 als
Werft-Track-Ergebnis in `idee-mvp/routine-anpassen/`)

### EC-34 — Cross-Skill-Empfehlung als Text-Footer

Wenn ein **Chat-Skill** seine Quittung schickt und es einen **anderen
Skill** mit WebApp-Pendant gibt, der die Aufgabe (oder eine
naheliegende Folge-Aufgabe) besser kann, hängt das LLM eine **schmale
Footer-Zeile mit Text-URL** an. Das LLM **formuliert** den Footer
selbst — keine feste Suffix-Konstante, keine Skill-direkte Sende-Form.

**Trigger** für den Footer (mindestens einer muss zutreffen):

1. **Plural-Hinweise im Anstoß** — explizite Mengen-Hinweise wie „und
   gleich noch …", „die ganze Liste", „alle Termine".
2. **≥3 Aufrufe desselben Skills** in derselben Familie in der
   laufenden Woche — Quelle ist die `task_events`-Tabelle (EC-35).

**Cross-Skill, nicht Eigen-App.** EC-34 ist die Footer-Form für eine
**WebApp eines anderen Skills**. Ein Skill, dessen **eigene**
Mini-App geöffnet werden soll (z. B. `einkauf_zeigen` → seine eigene
Einkaufs-Mini-App), nutzt **nicht** den EC-34-Footer, sondern den
**MAD-Launcher** (`conventions/mini-app-design.md` MAD-7 + MAD-10).
Damit bleibt die Auth-Linie (`initData`) sauber an Telegrams
Launch-Pfad gebunden, und EC-34 hat keine Sonderfälle für eigene
Apps.

**Was sich für die Familie ändert.** Mama trägt einen einzelnen
Einkauf nach („Brot und Tomaten für morgen"); der Bot quittiert, und
darunter steht eine Zeile: „Wenn du gleich die ganze Woche planen
willst — hier ist die Einkaufs-App: <URL>." Sie tippt, oder sie
ignoriert. Keine zusätzliche Bot-Nachricht, kein Modus-Wechsel.

**Begründung — Trade-off.** Ein fester Suffix („Tipp: WebApp …") wäre
maschinell zuverlässig, klingt aber bei jeder Wiederholung wie
Werbung. Die LLM-Formulierung passt den Footer an Anstoß und Frequenz
an — der Preis ist, dass das LLM ihn auch weglassen kann, wenn es
ihn als unpassend liest. Das ist gewollt: ein nicht gesendeter Footer
ist besser als ein nervender.

*Tickets:* #TBD-A4a (Footer-Formulierungs-Klausel in den
betroffenen Skill-Descriptions; Frequenz-Trigger gegen EC-35 lesen)

### EC-35 — Skill-Nutzungs-Telemetrie via `task_events`-Tabelle

Die Skill-Aufrufzählung läuft über eine **eigene `task_events`-
Tabelle** in derselben Eltern-Chat-SQLite (EC-16) — **nicht** über
EC-23 (Provider-Calls). EC-23 zählt Provider-Calls für Telemetrie an
der Bot-Antwort; EC-35 zählt erfolgreiche Nutzer-Turns pro Skill für
Bau-Priorisierung und EC-34-Frequenz-Trigger. Beide Tabellen
existieren parallel, jede mit ihrem eigenen Zweck.

**Gezählt werden erfolgreiche Nutzer-Turns**, nicht Tool-Loops. Ein
Turn, in dem das LLM `seiten_uebersicht` zweimal aufruft (z. B. zur
Filterung und dann zur Detail-Sicht), zählt als **ein** Event. Der
Anker ist „die Familie hat einmal diesen Skill genutzt", nicht „das
LLM hat einmal getoolt".

**Felder mindestens:**

- `task_name` — der Name der Katalog-Aufgabe (z. B.
  `einkauf_hinzufuegen`, `seiten_uebersicht`).
- `chat_id` — der Telegram-Chat, in dem der Turn lief (Familien-Gruppe
  oder Privatchat).
- `created_at` — Zeitstempel des Turn-Endes.
- `outcome` — `success`, `abort` oder `error` (Skill ist
  durchgelaufen / Familie hat abgebrochen / Skill hat einen Fehler
  geliefert).

**Verwendungs-Anker:**

- **EC-34 Frequenz-Trigger** — „≥3 Aufrufe diese Woche" liest
  `task_events` per `task_name` + `chat_id` + `created_at`.
- **Bau-Priorisierung A7.2** — die Werft entscheidet anhand der
  rollenden Aufruf-Häufigkeit pro Familie, welche WebApp zuerst
  gebaut wird (nicht: welche überhaupt eine WebApp bekommt — das ist
  EC-33).

**Nicht für EC-33 verwendet.** Die EC-33-Schwelle (Komplexität pro
Anstoß) ist deterministisch und braucht **keine** Telemetrie. Bricht
EC-35, bricht EC-33 nicht.

**Begründung — Trade-off.** Die Aufrufzählung über EC-23 wäre
Mit-Nutzung eines bestehenden Persistenz-Pfads, würde aber zwei
unterschiedliche Konzepte (Provider-Calls vs. Nutzer-Turns)
vermischen — EC-23 hat keinen `task_name`, und ein Tool-Loop mit
zwei Provider-Calls für eine Nutzer-Aktion würde doppelt zählen. Die
eigene Tabelle ist ein bewusst kleiner Aufpreis.

*Tickets:* #TBD-Q1 (Code-Track `task_events`-Tabelle in
`conversations.db`)

### EC-36 — Korrektur-Dialog: nach `falsch` führt der Bot durch die Korrektur

**Heutiger Schmerz (Bug #662, TAB-Live-Probe 2026-06-10):** Eine
Familie sagt „nein, aber X war anders" — der Bot interpretiert das
als **Komplett-Ablehnung**, wirft den Schreibakt weg, ohne nach der
Korrektur zu fragen. Die Familie muss von vorn beginnen. Die alten
Vereinfachungs-Klauseln in den Skill-Specs (`termine-aus-bild.md`
Z. 282–288 + `termin-eintragen.md` TES-7 Z. 237–243 +
`familie-anlegen.md` FAA-7-Vereinfachungs-Linie) hatten das bewusst
so gesetzt („inhaltliche Korrektur = neuer Aufruf"); für die
Familien-Sprache ist das aber Frust-Loop.

EC-36 hebt diese Vereinfachung **für alle A2- und Klasse-C-Pfade**
auf. **Klasse-E** (Privatchat-Auth-Loops FAA/GAA/KAV/PAA/AWE) bleibt
explizit **außerhalb** (eigener Abschluss-Gate-Pfad mit FAA-7-eigener
Vereinfachung — Auth-Identität braucht klare Schritt-für-Schritt-
Folge, kein Patch-Re-Propose).

**Customer Journey (identisch über alle in-scope Skill-Pfade):**

```
Bot:  [A2:]   X eingetragen. Wenn falsch, »falsch«.
      [C:]   Soll ich X tun? Sag »falsch«, wenn nicht passt.
Du:   falsch.
Bot:  [A2:]  Ok, rückgängig.  (oder Ambiguitäts-Quittung, siehe EC-10 A2)
      [C:]   Ok, Vorschlag verworfen.
      Was war falsch, wie soll ich's machen?
Du:   bitte alle Termine einen Tag nach vorne   /  Nudeln mit Tomatensoße  /  nur XY
Bot:  Verstanden. Neuer Vorschlag: Y. Soll ich das tun?
Du:   Ja, passt.
Bot:  Eingetragen.
```

**Wortlaut-Pflicht pro Pfad-Sorte:**

- **A2** (Sofort-Write + Receipt-`falsch`): „Ok, rückgängig." nach
  saubererem Inverse-Aufruf; Ambiguitäts-Quittung nach EC-10 A2 bei
  unklarem Inverse; **„Was war falsch?"** ist die Folge-Frage des
  Bots NACH der Quittung in beiden Fällen.
- **Klasse-C** (propose→confirm): „Ok, Vorschlag verworfen." nach
  `falsch` vor dem `ja`; **„Was war falsch?"** ist die Folge-Frage.
- Beide Pfade führen denselben Korrektur-Dialog (s.u.).

**Mehrere Iterationen erlaubt.** Schritt 5 → User sagt wieder
`falsch` → Bot fragt nochmal nach Korrektur → neuer Vorschlag →
rekursiv bis User `ja` sagt. **Keine harte Iterations-Grenze in V1**;
ein Folge-Ticket fügt eine Grenze hinzu, falls Familien sich in der
Schleife verlieren (Messung über EC-35 `task_events`-Korrektur-Tiefe
ist möglich, V1 baut sie nicht).

**LLM darf Rückfragen stellen** im Korrektur-State, wenn die
Korrektur unklar ist. Beispiel: User: „bitte alle Termine einen Tag
nach vorne" → Bot: „den 12. auch, oder nur die ab Mittwoch?" → User:
„nur die ab Mittwoch" → Bot baut Vorschlag. Rückfragen-Pfad ist nicht
auf eine Runde begrenzt; der LLM klärt so lange, bis ein sauberer
Patch vorliegt, dann erst der propose-Schritt.

**Cross-Skill-Exit ist erlaubt.** Sagt der User in der Korrektur-
Phase einen Auftrag, der zu einem **anderen Skill** gehört (z. B.
nach Termin-Eintragung `falsch` → „eigentlich kein Termin, lieber
als Plan-Aktivität setzen"), ist das eine neue Absicht. Der alte
Korrektur-State wird **versiegelt** (mechanisch wie EC-10
Folge-Anfrage), der neue Skill läuft durch seinen normalen Confirm-
oder A2-Pfad. M2c-Skill-Identitäts-Erzwingung würde die Familie hier
falsch sperren — explizit verworfen.

**Erzwungenes Confirm-Gate für Re-Propose nach A2.** Auch wenn der
**Original-Pfad A2 war**, läuft der gepatchte Re-Aufruf
**immer durch das zweistufige Confirm-Gate** (EC-10 zweistufige
Variante). Begründung: Das Vertrauen aus der A2-Klausel war auf den
ursprünglichen Anstoß bezogen; nach `falsch` ist es verbraucht.
Beispiel: Termin per A2 eingetragen → `falsch` → rückgängig → User
sagt „Donnerstag 17 statt 16" → Bot **fragt zurück** „Sport am Do
17:00 — eintragen?" → User: „ja" → eingetragen (jetzt mit neuem
Receipt, gilt wieder das A2-`falsch`).

**Mechanik (kein Spec-Inhalt, nur Bezug):** Der Korrektur-Dialog
sitzt auf den Welle-2-Lego-Steinen: Vor-Agent-Hook für `falsch` (vgl.
#721 + EC-10 A2 Undo-Bindung), Pending-Korrektur-State im
Confirm-State-Carrier (`PendingStore` für Klasse-C, Worker-Session
für gemischte Skills — Carrier bleiben getrennt nach Welle-2-Pivot),
LLM-Tool-Loop nutzt für Re-Propose denselben Skill mit gepatchten
Args. Konkrete Implementierung im Code-Track #844.

**Test-Implikation:**

1. **Klasse-C-Pfad:** `gericht_anlegen` propose → User `falsch` →
   Bot fragt „Was war falsch?" → User „Nudeln mit Tomatensoße" →
   Bot propose mit gepatchtem Label → User `ja` → Schreibakt grün.
2. **A2-Pfad:** `einkauf_hinzufuegen` Sofort-Write von „Brot" → User
   `falsch` → Bot löscht und fragt „Was war falsch?" → User „eigentlich
   Brötchen" → Bot **propose** mit „Brötchen" (Confirm-Gate erzwungen,
   nicht direkt geschrieben) → User `ja` → Schreibakt grün.
3. **Cross-Skill-Exit:** `termin_eintragen` propose → `falsch` → User
   „lieber als Plan-Aktivität" → Bot startet `plan_aktivitaeten_setzen`,
   alter Korrektur-State wird versiegelt.
4. **Mehrere Iterationen:** Klasse-C propose → `falsch` → Patch →
   propose → `falsch` → erneut Patch → propose → `ja` → grün.

*Tickets:* #843 (diese Spec), #844 (Code-Track Korrektur-Hook),
#662 (Original-Bug TAB ja-mit-Korrektur — wird durch diese Klausel
gelöst).

### EC-37 — Reader/Processor-Polling-Topologie

**RATIFIZIERT 2026-06-19** (ENTSCHEID-File Paket-Sektion „R2-Paket → A) Naht-Liste";
`brainstorm/berater-runde/2026-06-19-1545-RATIFIZIERT-polling-reader-typing.md`).

Der Telegram-Long-Poll-Lesepfad (`getUpdates`) läuft in einem Daemon-Thread
(`name="poll-reader"`), getrennt von der Update-Petrarbeitung (`dispatch`).
Reader und Processor sind durch **zwei** Queues verbunden — eine
Hand-off-Queue für Updates und eine ACK-Queue für Done-Signale:

- **Hand-off-Queue:** `queue.Queue(maxsize=1)` für `(t0, update_id, update)`.
- **ACK-Queue:** `queue.Queue(maxsize=1)` für `update_id` als Done-Signal
  vom Processor zurück zum Reader.
- **Reader-Schleife:** ruft `tg_reader.get_updates(offset, timeout=30)`,
  nimmt **ein** Update aus dem Batch, schickt **vor** Hand-off ein
  `sendChatAction(chat_id, "typing")` (EC-39) und füllt `open_chat_ids`,
  dann `handoff.put((t0, update_id, update))` (blockiert bis Processor
  entnimmt), dann **`ack.get()` (blockiert bis Processor Done meldet)**,
  dann `offset = update_id + 1` und nächstes `get_updates`. Erst nach
  dem ACK steigt der Offset — Telegram bestätigt das Update erst, wenn
  der Processor seine Petrarbeitung abgeschlossen hat.
- **Processor (Hauptthread):** `(t0, update_id, update) = handoff.get()`,
  dann `dispatch(update, ctx)` (kann beliebig lange laufen, z. B. HFE.
  propose() 20–90 s), dann `open_chat_ids.discard(chat_id)`, dann
  `ack.put(update_id)`.
- **TelegramClient-Form:** zwei `TelegramClient`-Instanzen mit gleichem
  Token aber getrennten `_opener` — `tg_reader` für `get_updates` und
  Sofort-Typing, `tg_main` für alles übrige (Bot-Antworten, Renewer,
  Skills). Stateless HTTP-POST; keine Telegram-Session-Semantik gebrochen.
- **`open_chat_ids`:** geteilte `set[int]`, **eine** `threading.RLock`-
  Instanz in `main()` erzeugt und an Reader, Processor und Renewer
  übergeben. Tolerante Race: Processor entfernt sofort beim `dispatch`-
  Return; Renewer sendet im worst case einen `typing` zuviel (Telegram-
  Client überschreibt das mit der nächsten Bot-Antwort).
- **E-EC-2-Backoff** wandert in den Reader; Semantik unverändert.

Die Trennung stellt sicher, dass eine länger laufende Petrarbeitung
(z. B. HFE.propose() 20–90 s, EC-14-Fehlerfall) das Lesen der nächsten
eingehenden Nachricht nicht blockiert — und insbesondere die familien-
seitige Sichtbarkeit (EC-25 / EC-39) während laufender Schreibaufgaben
nicht stillstellt.

*Test-Implikation:*
- `test_reader_waits_for_ack_before_offset_advance`: Mock-`get_updates`
  liefert U1 und U2; Mock-`dispatch` blockiert 60 s auf U1; Reader hat
  U1 in die Hand-off-Queue gelegt, wartet auf ACK; Hand-off-Queue ist
  leer aber **kein** zweites `get_updates(offset)` wird gerufen, weil
  Reader im `ack.get()` blockiert. Nach Processor-`ack.put(U1.id)` läuft
  Reader weiter und ruft `get_updates(offset = U1.id + 1)`.
- `test_at_least_once_on_processor_crash`: Reader hat U1 abgegeben, U1
  ist noch nicht ACKed; SIGKILL auf Processor. Bot-Restart liefert U1
  erneut, weil offset nie über U1.id hinaus erhöht wurde.
- Pickup-Latenz-Tupel-Wrapper bleibt EC-23-konform.

*Tickets:* (folgt mit `/arbeitstag-prep`).

### EC-38 — At-least-once-Update-Petrarbeitung

**RATIFIZIERT 2026-06-19** (ENTSCHEID-File Paket-Sektion „R2-Paket → B)
Spec-Patch-Skizze" → EC-N2-Klausel;
`brainstorm/berater-runde/2026-06-19-1545-RATIFIZIERT-polling-reader-typing.md`).

Der Long-Poll-Offset (`getUpdates`-`offset`) wird erst nach der
beobachteten Petrarbeitung erhöht. Konkret: der Reader bestätigt ein
Update bei Telegram (= nächster `getUpdates(offset+1)`) **erst, nachdem**
der Processor seine Petrarbeitung abgeschlossen UND ein Done-Signal über
die ACK-Queue (EC-37) zurück an den Reader gemeldet hat. Bounded
Hand-off-Queue (Slot 1) plus explizites ACK pro Update — der Reader
blockiert in `ack.get()` zwischen Hand-off und Offset-Erhöhung.

**Konsequenz:** Bei einem Pi-/Heimserver-Crash zwischen Reader-Empfang
und Processor-Konsum liefert Telegram das Update beim Restart erneut
(Telegram retent ungelesene Updates 24 h). Das Risiko sind doppelte
Petrarbeitungen *innerhalb* der 24-h-Retention bei sofortigem Restart —
bewertet als kleiner als der heutige Update-Verlust durch In-RAM-Burst-
Petrarbeitung im sequenziellen `poll_loop`.

**Akzeptanz-Begründung (Codex-Brüche in beiden Pässen):** Eine
optimistische Variante hätte mehrere Updates in einer unbounded Queue
puffern und den Offset sofort erhöhen können — dann wäre Telegrams
24-h-Retention bei Crash wertlos und Lenas Nachricht ginge verloren.
Eine bloß-bounded-Variante (`Queue(maxsize=1)` ohne explizites ACK)
hätte einen subtilen Edge-Case offengelassen: Processor entnimmt U1
(Slot frei), Reader legt U2 ab und erhöht Offset auf U2+1 — bei Crash
während U2-dispatch wäre U2 verloren. Das explizite ACK-Signal (EC-37)
schließt diesen Edge-Case sauber. xbuddy-Schreibakte sind über
Bestätigungs-Gate (EC-10) plus A2-Receipt-Inverse idempotent genug,
dass at-least-once die richtige Wahl ist.

*Test-Implikation:* siehe EC-37 `test_at_least_once_on_processor_crash`.

*Tickets:* (folgt mit `/arbeitstag-prep`).

### EC-39 — Sofort-Typing-Indikator bei Privatchat-Empfang

**RATIFIZIERT 2026-06-19** (ENTSCHEID-File Paket-Sektion „R2-Paket → B)
Spec-Patch-Skizze" → EC-N3-Klausel;
`brainstorm/berater-runde/2026-06-19-1545-RATIFIZIERT-polling-reader-typing.md`).

Erhält der Reader (EC-37) ein Telegram-`message`-Update mit
`chat.type == "private"`, sendet er **Fire-and-Forget**
`tg_reader.send_chat_action(chat_id, "typing")` direkt nach dem Empfang —
vor Auth-Check, vor Agent-Loop, vor jeder Bot-Antwort. Ein paralleler
**`_TypingRenewer`**-Daemon-Thread erneuert den Indikator alle **4 s**
(gemeinsame Intervall-Konstante mit EC-28 / `skills/typing_indicator.py:28-31`
— *eine* Wahrheit), solange das Update in der Hand-off-Queue steht oder
der Processor es petrarbeitet (`chat_id` in `open_chat_ids`).

**Gilt nur für Privatchats.** Familien-Gruppe bleibt vom Sofort-Typing
**ausgenommen** — EC-25 (Privatchat-only-Norm für mehrstufige Schreib-
Aufgaben) und die Tests `test_familie_anlegen_task.py:471-482` und
`test_termin_eintragen_task.py:375-382` verriegeln das Verhalten für
Skill-Sessions; **EC-39 braucht eigene Reader-Tests** (siehe Test-
Implikation unten).
`my_chat_member`- und Gruppen-Updates haben kein `message.chat.type ==
"private"` → Reader filtert sie automatisch raus.

**Privacy-Trade-off (bewusst akzeptiert):** EC-39 sendet Typing **vor**
dem Auth-Check (`is_authorized`-Gruppenmitgliedschafts-Prüfung,
`authz.py:20`). Ein Privatchat-Sender, der nicht (mehr) Mitglied der
Familien-Gruppe ist, sieht ein „tippt"-Signal, obwohl der Bot ihm später
keine Nachricht zurücksendet (EC-2 ignoriert ihn). Das ist ein kleines
Aktivitäts-Leak. Akzeptanz-Begründung: (a) Intra-Familie-1 ist Privatchat
zwischen Bot und bekannten Familienmitgliedern — fremder Spammer findet
den Bot-Token selten; (b) Inter-Familie-Trennung läuft via eigener
Bot-Instanz pro Familie (Multi-Tenancy-Setzung 2026-06-15,
`project_familie_2_3_eigener_bot.md`); (c) der UX-Gewinn (Lena sieht
„beschäftigt" statt 90 s Stille) wiegt das Aktivitäts-Leak auf.
Falls dieses Trade-off später kippt: EC-39 nach Auth verschieben =
Sofort-Typing erst nach Live-Mitgliedschaftsprüfung (`is_authorized`-
Call im Reader pro Update). Heute aufgeschoben.

**Best-Effort:** Fehler beim `sendChatAction` (Telegram-Rate-Limit,
HTTP-Fehler) unterbrechen die Petrarbeitung nicht; sie werden geschluckt
und geloggt.

**Wirkung für die Familie:** Während Nic eine Hörspiel-Folge anstößt
(HFE.propose() 20–90 s, Polling-Loop blockiert für `dispatch`) sieht
Lena binnen 1–2 s nach ihrer Nachricht einen Typing-Indikator
(„Bot tippt"), der durch den Renewer alle 4 s erneuert wird, bis ihr
Update petrarbeitet ist und der Bot antwortet. Statt 90 s Stille:
durchgehendes „beschäftigt"-Signal. Quer-Verweis: EC-25 deckt Typing
**innerhalb** der mehrstufigen Schreib-Aufgabe ab (nach Auth, im
Agent-Loop); EC-39 ergänzt das **vor** der Auth.

**Konventions-Aufschub:** Mit `_TypingRenewer` entsteht das **dritte**
Renewer-Beispiel im Repo (`agent.py:_TypingRenewal` und
`skills/typing_indicator.py:TypingRenewal` sind n=1 und n=2). Eine
`conventions/typing-renewal.md` wird **nach Bau** in einer eigenen
`/berater-runde` ratifiziert (Memory
`feedback_berater_zwei_gebaute_beispiele.md`: Konventionen nicht
antizipativ).

*Test-Implikation (Reader-spezifisch, EC-25-Tests reichen nicht):*
- `test_reader_typing_for_private_message`: Mock-Update mit
  `chat.type == "private"` → `tg_reader.send_chat_action(chat_id, "typing")`
  feuert genau einmal vor Hand-off.
- `test_reader_typing_skipped_for_group`: Mock-Update mit
  `chat.type == "group"` oder `"supergroup"` → kein `send_chat_action`.
- `test_reader_typing_skipped_for_my_chat_member`: Update ohne `message`-
  Feld (`my_chat_member`) → kein `send_chat_action`.
- `test_renewer_ticks_every_4s`: Mock-Zeit, `open_chat_ids = {chat_id}`,
  Renewer schickt alle 4 s `send_chat_action`; nach `discard(chat_id)`
  hört er auf.
- `test_send_chat_action_failure_is_swallowed`: `send_chat_action` wirft
  Exception → Reader-Loop läuft weiter, Update wird trotzdem an Processor
  übergeben.

*Tickets:* (folgt mit `/arbeitstag-prep`).

### EC-40 — Mini-App-Skill-Familie: synchrones Trigger-Vokabular

**RATIFIZIERT 2026-06-22** (Refs #1075 — Mistral-Routing-Regression nach
Anbieter-Wechsel zeigte App-spezifische Trigger-Listen als zu eng).

Skills, die eine Mini-App via Telegram-Inline-Button öffnen (heute fünf
Skills: `einkauf_zeigen` EZG, `hoerspiel_oeffnen` HOE,
`routine_anpassen_oeffnen` RAO, `seiten_uebersicht` MAU,
`wetter_regeln_oeffnen` WRO — alle mit
`web_app_url`-Inline-Button im Tool-Result, TASK-10c Form (b)), teilen
ein gemeinsames **Trigger-Vokabular**, damit das LLM die Familie
geschlossen routet — auch über Anbieter-Wechsel hinweg. Das Vokabular
besteht aus zwei Achsen, die kombinatorisch wirken:

**Achse A — Aktions-Vokabular (familien-weit, identisch über alle fünf
Skills):**

> *settings, einstellungen, anpassen, bearbeiten, ändern, öffnen,
> zeigen, schicken, geben, app, mini-app, löschen, umsortieren,
> sortieren, hinzufügen* — plus Varianten in den natürlichen
> Beuge-/Frage-Formen („gib mir die …", „schick mir die …", „zeig
> mir die …").

**Achse B — App-Bezeichnungen (pro Skill in seiner Spec gelistet — die
Bezeichnungen pro App sind dort die einzige Wahrheit, EC-40 schreibt
sie nicht selbst):**

- `EZG`: Einkaufsliste-Bezeichnungen aus EZG-3.
- `HOE`: Hörspiel-/Hörbuch-Bezeichnungen aus HOE-3.
- `RAO`: Routine-Bezeichnungen aus RAO-3.
- `MAU`: Mini-App-Übersicht-Bezeichnungen aus MAU-10.
- `WRO`: Wetter-Regeln-Bezeichnungen aus WRO-3.

**Mechanik.** Jeder der fünf Skill-Spec-Trigger-Abschnitte trägt die
identische **Disziplin-Klausel**: „Der Skill feuert auch, wenn die
Eltern-Nachricht eine Aktion aus Achse A mit einer App-Bezeichnung aus
Achse B kombiniert — auch ohne ein in der App-spezifischen Phrasen-
Liste genanntes Verb. Beispiele: »gib mir die <X> settings«, »schick
mir die <X> einstellungen«, »<X> app öffnen«, »<X>-Optionen«."

**Begründung.** Vor Mistral-Switch (Claude) hat das LLM auch ohne
explizite Achsen-Kreuzungs-Phrase robust geroutet (Claude robuster
gegenüber generischen Settings-Triggern). Nach Mistral-Switch
(`mistral-medium-2508`) zeigten Familien-Live-Repros (Refs #1075,
conversations.db chat 0000000000, seq 600/602/604 am 2026-06-22):
„Schick mir die Hörbuch settings", „Schick mir die settings", „Gib
mir die Routine settings" wurden **nicht** zu Tool-Calls, sondern
halluzinierten Markdown-Knöpfen im Antwort-Text (siehe EC-41). EC-40
schließt diese Routing-Lücke **anbieter-unabhängig** über das
Skill-Description-Vokabular — EC-12-konform.

**Implementations-Pfad.** Tool-`description` der fünf Skills (im
Eltern-Chat-`tasks.py`-Aufruf via `build_catalog`, indirekt über
`*_task.py:description=(…)`) trägt am Ende eine identische
Disziplin-Klausel mit der App-spezifischen Achse-B-Liste. Welche
Variante des Klausel-Wortlauts gilt, normiert `conventions/tasks.md`
TASK-10 (Skill-Beschreibungs-Bauplan); diese Spec normiert das
**Soll**: Vokabular synchron, Achsen sauber getrennt, keine
App-spezifische Aktion in einer anderen App-Liste verstecken.

**Geltungsbereich.** Skills, die KEINEN `web_app_url`-Inline-Button
zurückgeben (z. B. `routine_zeiten_setzen` RZS, `termin_eintragen`),
sind **nicht** in der Mini-App-Skill-Familie und damit nicht
EC-40-bindend — die Abgrenzungen pro Skill-Spec (z. B. RAO-3 →
RZS-Grenze, EZG-3 → WZE-Grenze, HOE-3 → HFE-Grenze) bleiben
unverändert. Wächst eine neue Mini-App in die Familie (n=5,
beispielsweise ein Plan/Wochenplan-Buddy mit Eltern-Chat-Anschluss),
trägt sie EC-40 ab Werft-Lauf.

**Trigger-Heimat (Negativ-Geltung, Soll-Norm, Refs #1105).** Das
positive Trigger-Vokabular der EC-40-Familie **gehört allein in die
Tool-`description`** (Implementations-Pfad oben) und **darf nicht
zusätzlich** als ausgeschriebene Phrasen-Liste im `SYSTEM_PROMPT` von
`eltern-chat/agent.py` gepflegt werden. Für die Familie trägt der
System-Prompt ausschließlich **Negativ-/Verweis-Routing**: eine
beiläufige Settings-**Inhalts-/Änderungs**-Bitte (Voice/Modell/Tempo)
beantwortet der Agent sprachlich ohne Tool-Call — die **Direkt-Settings-
*Link*-Bitte** bleibt davon unberührt ein positiver Tool-Trigger in der
`description` (z. B. HOE via E-HOE-2). Zwei gepflegte Heimaten desselben
Vokabulars driften sonst auseinander (Live-Schmerz #1105: identische
HOE-Settings-Phrasen standen sowohl im `agent.py`-System-Prompt als auch
in der Tool-`description`). Die **Umsetzung** dieser Norm — Entfernen der
verbliebenen HOE-Positiv-Dopplung aus dem System-Prompt — erfolgt über
**#1105**; bis dahin ist die Code-Dopplung der dokumentierte
Soll-Verstoß, den #1105 schließt.

*Tickets:* #1075, #1105

### EC-41 — Mini-App-Knöpfe entstehen ausschließlich über Skill-Aufrufe

**RATIFIZIERT 2026-06-22** (Refs #1075 — Markdown-Knopf-Halluzination
unter `mistral-medium-2508`).

Das LLM darf in seinen Bot-Texten **niemals** einen Web-App-Knopf
oder einen Mini-App-Link als Markdown-Text formulieren — weder als
`[**…**]`-Pseudo-Knopf, noch als Klartext-URL, noch als sprachliches
Verspechen („Knopf unten", „klick auf den Button", „der Knopf öffnet
…"), das keinen gleichzeitigen Tool-Call dieses Knopfes ausgelöst hat.
Telegram rendert Markdown im Standard-Pfad (EC-27 ohne opt-in) nicht
als Inline-Knopf — die Familie sieht literalen Text, der Knopf fehlt,
das Versprechen läuft ins Leere.

**Mechanik.** Ein Mini-App-Knopf kommt im Eltern-Chat ausschließlich
zustande, wenn ein Skill der EC-40-Familie aufgerufen wird und sein
Tool-Result-Dict ein `presentation: {inline_button: {label,
web_app_url}}` enthält (TASK-10c Form (b)). Der Skill liefert den
Knopf-Mechanismus; das LLM formuliert nur den Text-Teil (EC-29 „Eine
Stimme"). Will das LLM einen Knopf anbieten, ruft es das passende
Skill auf — nicht den Knopf in Prosa imitieren.

**Geltungsbereich.** Diese Regel bindet jeden Agent-Turn des
Eltern-Chats — sowohl die direkte LLM-Antwort als auch die
Tool-Result-Petrarbeitung. Sie ist **unabhängig vom KI-Anbieter**
(EC-12) und damit auch bei künftigem Anbieter-Wechsel bindend.
Tool-`description`-Texte der EC-40-Familie tragen die Regel als
expliziten Negativ-Hinweis („keinen Markdown-Knopf in der Antwort
schreiben — der Button kommt automatisch über den Tool-Call"), damit
sie auch im Tool-Routing-Kontext sichtbar ist. Eine vorhandene
App-spezifische Schärfung (heute HOE: E-HOE-2-Schärfung Refs #1048
„»Knopf unten« oder »Button« NICHT versprechen") ist mit EC-41 auf
die ganze Mini-App-Familie gehoben — die HOE-Klausel bleibt als
App-spezifischer Reflex bestehen, ist aber redundant zu EC-41 und
gilt mechanisch über EC-41 auch für EZG / RAO / MAU.

**Begründung.** Live-Repro 2026-06-22 (Refs #1075,
conversations.db chat 0000000000, seq 601/603/605): unter
`mistral-medium-2508` halluzinierte der Agent statt eines Tool-Calls
literale Markdown-Knöpfe in den Antwort-Text — z. B. *„👉 **Öffne
die App mit diesem Knopf:** [**Routine-Anpassen-Mini-App öffnen**]"*.
Telegram zeigte den literalen Text, kein klickbarer Knopf, kein
Mini-App-Aufruf möglich. Die App-spezifische E-HOE-2-Klausel war im
HOE-Block des System-Prompts versteckt und wurde vom Anbieter
übergangen. EC-41 hebt die Regel auf Top-Level-Geltung — anbieter-
unabhängig, Skill-Familie-übergreifend.

**Abgrenzung zu EC-27 (HTML-opt-in).** EC-27 regelt die *Telegram-
Transport-Schicht* (HTML-Rendering pro Nachricht, nur für Skills, die
strukturierte Listen brauchen). EC-41 regelt die *LLM-Antwort-
Disziplin* (kein Pseudo-Knopf in Prosa) — auch in HTML-Nachrichten.
EC-41 verbietet keine echten Links im Text, wenn sie thematisch
gehören (z. B. eine externe Anleitung); es verbietet die Imitation
eines Inline-Knopfes durch Markdown-/HTML-Text, ohne dass der
zugehörige Skill ausgelöst wurde.

*Tickets:* #1075

### EC-42 — `anzeige_copy`: kuratierte eltern-taugliche Anzeige-Copy einer Aufgabe

Eine Katalog-Aufgabe (EC-8) **darf** ein optionales Feld `anzeige_copy`
tragen: einen kurzen, eltern-tauglichen Ein-Satz-Text, der die Fähigkeit
in der Familien-Sprache beschreibt (z. B. „Ich kann dir die Einkaufsliste
öffnen"). Er steht neben — nicht statt — der `description`, die
Router-/Trigger-Vokabular **für das LLM** trägt (EC-40) und für Eltern
ungeeignet ist.

**Optional/lazy — Fallback auf `description`.** Fehlt `anzeige_copy`,
fällt jeder Leser auf `description` zurück. Kein Skill **muss** das Feld
setzen; ohne Deklaration ändert sich am bisherigen Verhalten nichts.

**Reines Anzeige-Attribut.** `anzeige_copy` ist **kein** Trigger und trägt
**keine** Berechtigungs- oder Sichtbarkeits-Semantik. Es steuert **nicht**,
ob eine Aufgabe im Katalog liegt, wer sie aufrufen darf oder ob das LLM sie
auslöst — es liefert ausschließlich den Text, den ein Anzeige-Leser
darstellt.

**Leser heute (n=2):** `faehigkeiten_zeigen` (EC-43) und der
Onboarding-Teaser (`eltern-chat-onboarding.md`, #1104). Zwei Leser
rechtfertigen das Feld. Eine **committete Manifest-Registry**, ein
**Drift-Test** oder eine **Capability-Karten-Generierung** sind bewusst
**nicht** Teil davon — deferred, bis ein dritter Leser oder echter
Drift-Schmerz am Feld auftritt (capability-cluster-ENTSCHEID Landung 3,
NOCH NICHT).

**Deklarations-Ort (Bau).** Das Feld ist ein Klassenattribut auf der
`Task`-Basis (analog `is_async`/`auto_confirm`/`post_execute_hooks`) —
Default: nicht gesetzt. Der Bau-Andockpunkt steht in `conventions/tasks.md`
TASK-11; diese Spec normt das **Soll** des Feldes, nicht das Wie.

Test-Anker: eltern-chat/tests/test_tasks.py::test_ec42_anzeige_copy_default_none_und_gesetzt

### EC-43 — `faehigkeiten_zeigen`: Selbstauskunft aus dem Live-Katalog

„Fähigkeiten zeigen" ist eine aufrufbare **lesende Funktion** (EC-9), die
auf die Frage »Was kannst du?« antwortet. **Eingang:** die Telegram-Chat-
Identität und die User-ID des Aufrufers. **Wirkung:** **keine**
Familien-Daten-Änderung; die Funktion liest den EC-8-Katalog selbst.
**Ausgang:** ein User-tauglicher Antwort-Text als Tool-Result mit der
Fähigkeitsliste.

**Quelle ist der live registrierte Katalog (EC-8) — die eine Wahrheit.**
Der Skill zählt die tatsächlich registrierten Katalog-Aufgaben auf (sich
selbst ausgenommen) und rendert je Aufgabe `anzeige_copy`; fehlt es, den
`description`-Fallback (EC-42). Dadurch kann die Antwort **keine** Fähigkeit
behaupten, die nicht im Katalog liegt (EC-7 — Ehrliche Grenze), und **keine**
registrierte übergehen. Die Fähigkeits-Fakten stammen aus dem Katalog, nicht
aus dem Modell-Welt-Wissen (EC-30-Trennlinie).

**Deterministischer Inhalt, eine Stimme (EC-29).** Der Skill liefert die
Liste als **deterministisch strukturierten** Tool-Result-Text; das LLM
formuliert daraus die Bot-Nachricht im bestehenden Persona-Ton. Es gibt
**keinen** neuen LLM-Freitext-Pfad, der Fähigkeiten frei formuliert oder
zusammenstellt — nur der Ton kommt vom Modell, die Fähigkeits-Fakten sind
Katalog-Wahrheit. Das hält das EC-7-Halluzinations-Risiko draußen (ein frei
generierter Fähigkeits-Text könnte eine nicht vorhandene Fähigkeit
versprechen).

**Eltern-Chat ist Eltern-only (Setzung Nic 2026-07-01).** Der Skill listet
schlicht die Eltern-Fähigkeiten. Es gibt **keinen** Rollen-Filter und
**kein** `sichtbar_fuer`-Feld; eine Kinder-/Eltern-Sicht-Unterscheidung
entfällt vollständig.

**Berechtigung: Eltern.** Nur für Telegram-User mit Familien-Mitgliedschaft
aufrufbar (analog EZG-2/HOE-2). Nicht-Mitglieder erhalten Klartext-Ablehnung
über den geteilten `BerechtigungError` (`conventions/tasks.md` TASK-10).

**SREG-5-Leitplanke (#1028).** Der Skill nennt **keine** konkrete Seite und
**keine** Mini-App-URL. Er beschreibt Fähigkeiten; für »wo sehe ich X«
verweist er sprachlich auf die Seiten-Übersicht-Fähigkeit
(`seiten_uebersicht`), die selbst als Fähigkeit in der Liste steht — nicht
auf einzelne Seiten-Adressen.

**Skelett-Anker.** Der Skill folgt der Katalog-Aufgaben-Konvention:
Skill-Datei `eltern-chat/skills/faehigkeiten_zeigen_task.py`
(`ReadTask` mit `run`, `conventions/tasks.md` TASK-1/TASK-3), registriert in
`build_catalog` (TASK-7), sprachlos im Agent-Loop (TASK-10/EC-29). Die
Katalog-Referenz reicht `build_catalog` in den Task hinein; der Katalog ist
zur Anfrage-Zeit vollständig registriert (die Registrierungs-Reihenfolge ist
irrelevant, weil `run()` erst zur Laufzeit läuft). Das ist ein
**n=1-Selbstlese-Pfad** — **keine** neue Konvention (kein Vorrat,
CLAUDE.md §6).

Test-Anker: eltern-chat/tests/skills/test_faehigkeiten_zeigen.py::test_ec43_listet_katalog_anzeige_copy_mit_description_fallback

*Tickets:* #1102 (Refs #1164)

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
für jedes petrarbeitete Update die Latenz zwischen `getUpdates`-Rückkehr
(t0) und der Fertigstellung der Petrarbeitung (t1) und schreibt sie pro Update
als `INFO`-Eintrag gemäß LOG-1-Zeilenformat (`%(asctime)s %(levelname)s %(message)s`);
der `message`-Teil enthält strukturierten Inhalt im `event=… key=value`-Stil:
`poll event=pickup_latency count=1 latency_ms=X`. `count=1` ist fix, weil
durch den Reader/Processor-Split der Processor stets ein Update pro
Loop-Durchlauf sieht (Per-Update-Log statt Per-Batch). Das ist die
**familienseitige Long-Poll-Pickup-Latenz** — von Telegrams Update-Lieferung
bis zum Ende unserer Petrarbeitung — und ist bewusst von der
EC-23-Provider-Latenz (innerhalb eines Turns) abgegrenzt: EC-23 misst, wie
lange der LLM-Anbieter braucht; diese Metrik misst, wie schnell das System
auf ein eintreffendes Update reagiert.

**Quer-Verweis EC-37/38 (2026-06-19; ENTSCHEID-File Paket-Sektion
„R2-Paket → A) Naht-Liste" und „R2-Paket → B) Spec-Patch-Skizze";
`brainstorm/berater-runde/2026-06-19-1545-RATIFIZIERT-polling-reader-typing.md`):**
Der `poll_loop` wird ab 2026-06-19 in einen Reader-Daemon-Thread
(`getUpdates` + Sofort-Typing + Hand-off) und einen Processor-
Hauptthread (Hand-off-Consume + `dispatch`) geteilt. Der 30-s-Long-Poll-
Timeout und die Backoff-Verfeinerung oben bleiben unverändert.
Pickup-Latenz wird als Wrapper-Tupel `(t0, update_id, update)` durch die
Hand-off-Mechanik gereicht (Reader misst t0, Processor misst t1); die
`update_id` im Tupel ist der ACK-Korrelations-Schlüssel, der Reader und
Processor bei der At-least-once-Quittierung (EC-38) verknüpft. Logformat
unverändert. Details: EC-37 (Reader/Processor-Split), EC-38 (At-least-
once).

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
akzeptiert Petrarbeitung außerhalb der EU, die andere verlangt einen
EU-Anbieter oder lokale Petrarbeitung. Der Adapter macht den Anbieterwechsel zu
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

**Ablehnungs-Wortliste (Pendant zu CONFIRM_WORDS).** In der
zweistufigen Variante (EC-10) leert eine ausdrückliche **Ablehnung**
den `PendingStore` ohne Schreibakt — der offene Vorschlag verfällt.
Die Liste ist fest definiert: `nein`, `nicht`, `nö`, `nope`,
`vergiss es`, `lass mal`, `abbrechen`, `cancel`, `doch nicht` —
Vergleich case-insensitiv, ganzes Wort/ganzer Ausdruck (keine
Teilstring-Treffer). Der Bot quittiert mit einem Satz in der Stimme
des jeweiligen Skills (z. B.: „ok, Vorschlag verworfen."). Der
Abgleich ist analog zur Bestätigung **deterministisch** und liegt
außerhalb des Agent-Loops — keine LLM-Interpretation.

Die Liste ist bewusst eng (eindeutige Ablehnungs-Marker, keine
ambivalenten Phrasen wie „mal sehen", „später"). A2-Schreibakte
sind nicht betroffen — sie kennen das Undo-Wort `falsch` (EC-10
A2-Klausel).

**Verworfen:** (a) **LLM-Interpretation der Ablehnung** — bricht
E-EC-4/EC-12; (b) **dieselbe Wortliste wie das A2-Undo (`falsch`)**
— mischt zwei unterschiedliche Mechaniken (Vorschlag verwerfen vs.
ausgeführten Schreibakt rückgängig machen); (c) **`nein` als
einziges Wort** — Familien nutzen viele Ablehnungs-Wendungen, eine
zu enge Liste produziert „keine Ablehnung erkannt"-Schmerz.

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

### E-EC-9-V2 — Regelbetrieb-Privacy: Hybrid-Egress statt Voll-Anonymisierung
*Datum:* 2026-07-06 · *löst OPEN-EC-A für den Regelbetrieb* (RATIFIZIERT berater-runde 2026-07-05, Nic-Verdikt „a")

E-EC-9 („V1 ohne Anonymisierung") war auf die Prototyp-/Bewertungsphase befristet.
Für den Regelbetrieb gilt: **kein** Voll-Anonymisierungs-Layer (der würde die
Erkennungsqualität aus E-EC-6 zerstören), sondern **gezielte Feld-Redaction** —
konkrete PII (Adresse, Telefon) wird dort entfernt, wo der Agent sie zur Aufgabe
nicht braucht — **plus EU-Region-Routing** als Egress-Hook in `tools/llm`, vor dem
Verlassen der Geräte-Ebene (erfüllt Constitution §3, die unverändert bleibt).

**Nicht nur `tools/llm`:** es gibt **≥3 Egress-Fronten** — Chat/Foto (über
`tools/llm`), sowie STT und TTS (`kibuddy/tts`, `hoerspiel/tts`, STT-Pfad), die
ebenfalls Familientext senden und je einen eigenen Region-/Redaction-Entscheid
brauchen. Bild-PII (Gesichter, Aushang-Klarnamen) bleibt vom Text-Redaction-Pfad
unberührt und ist ein eigener Punkt.

**Lösch-/Export-Pfad — Granularität `chat_id` (Familie), nicht `kind_id`**
(Nic-Setzung 2026-07-06): „Familie löschen/exportieren" läuft über die
SVC-5-Wurzel `xbuddy-data/` (eltern-chat-SQLite `history.py` auf `chat_id`,
TTS-Cache, `provider_calls.jsonl`) **inklusive der B2-Backup-Löschkette**.
Empirisch belegt löschbar: restic `forget --prune` räumt den B2-Bucket täglich
erfolgreich, **kein wirksames Object-Lock** — die Familie wird also **sofort
mitgelöscht**, nicht erst nach Retention-Ablauf. `kind_id`-Granularität ist
bewusst **nicht** vorgebaut (`history.py` kennt nur `chat_id`; eine Nachrüstung
wäre eine teure Datenmodell-Migration ohne belegten Bedarf).

**Ein-Wege-Commit erst nach drei Pflicht-Spikes** (diese Setzung ist die
Richtung, nicht der fertige Bau): (1) **Quali-Spike** — gezielte Redaction auf
realer Konversation ohne Erkennungs-Einbruch; (2) **Region/AVV-Spike** — ist ein
realer sensibler Fluss EU-routbar und ein AVV beschaffbar; (3)
**kind-Achsen-Inventar** der xbuddy-data-Dirs. Retention-Fristen (Chat-Historie +
`provider_calls.jsonl`) bleiben OPEN bis zum Spike.


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
