# Eltern-Chat Onboarding — Spec     (ID-Präfix: ONB)

> Status: V1-MVP · Refs #33

Das KI-Anbieter-Onboarding bringt eine frische Eltern-Chat-Instanz vom Zustand
»kein KI-Zugang« in den Zustand »KI aktiv«. Es läuft, solange noch kein
Anbieter-Key vorliegt, in einem deterministischen, **hart-codierten** Modus —
denn ein Sprachmodell steht zu diesem Zeitpunkt per Definition noch nicht zur
Verfügung. Geführt wird im Chat: Einstieg in der Gruppe, Key-Eingabe im
Privatchat, Validierung, Speicherung. Mit dem Abschluss wird die Instanz
KI-aktiv und die Familien-Gruppe gebunden.

Diese Spec gehört zur Komponente `eltern-chat/` und baut auf
[`eltern-chat.md`](eltern-chat.md) auf — insbesondere EC-2 (Familien-Gruppe als
Berechtigung), EC-11 (KI-Anbieter je Instanz wählbar) und EC-15
(Konfigurationswerte).

**V1-Scope:** der Weg von »kein Anbieter-Key« zu »KI aktiv« — Onboarding-Modus,
Einstieg, Anbieter-Wahl, Key-Entgegennahme im Privatchat, Validierung,
persistente Speicherung, Bindung der Familien-Gruppe, Moduswechsel.

**Out-of-Scope V1** (jeweils eigenes Ticket, sobald gebraucht): weiteres
Onboarding (Familienmitglieder, Buddys, Geräte) · Wechsel oder Rotation eines
bereits eingerichteten Keys · eine Auswahl-Oberfläche für mehrere Anbieter über
den ersten hinaus.

## 1. Modus

### ONB-1 — Onboarding-Modus
Solange für die Instanz kein KI-Anbieter-Key vorliegt — weder über eine
Umgebungsvariable noch im Onboarding-Speicher (ONB-5) —, läuft sie im
**Onboarding-Modus**: Sie führt keine Katalog-Aufgaben aus und nutzt den
KI-Anbieter nicht für Gespräche — sie reagiert ausschließlich mit den
deterministischen, hart-codierten Nachrichten dieser Spec. Der einzige
Anbieter-Aufruf im Onboarding-Modus ist die Key-Validierung (ONB-4). Liegt ein
Key vor, ist der Onboarding-Modus inaktiv und es gelten die regulären
Anforderungen aus `eltern-chat.md` (EC-4 ff.).

*Tickets:* #33

## 2. Einstieg

### ONB-2 — Einstieg im Onboarding-Modus
Wird der Bot einer Telegram-Gruppe als Mitglied hinzugefügt, während die Instanz
im Onboarding-Modus ist, sendet er unaufgefordert eine hart-codierte
Einstiegs-Nachricht in diese Gruppe: dass er noch keinen KI-Zugang hat, welche
Anbieter zur Wahl stehen, und die Aufforderung, die Einrichtung im Privatchat
mit dem Bot fortzusetzen. Wird der Bot im Onboarding-Modus in einer Gruppe
ausdrücklich angesprochen (Erwähnung oder Antwort auf eine seiner Nachrichten),
sendet er dieselbe Einstiegs-Nachricht — wer den Hinzufügen-Moment verpasst hat,
kommt so trotzdem hinein.

*Tickets:* #33

## 3. Einrichtung

### ONB-3 — Key-Eingabe im Privatchat
Die Übermittlung des Anbieter-Keys erfolgt im Privatchat zwischen einem
Familienmitglied und dem Bot — nie in der Gruppe, damit der Key nicht für andere
Mitglieder sichtbar wird. Der Bot führt im Privatchat hart-codiert durch die
Anbieter-Wahl und nimmt den Key als Nachricht entgegen. Berechtigt zur Eingabe
ist, wer Mitglied der Gruppe ist, in der das Onboarding begonnen wurde — geprüft
live (analog EC-2).

*Tickets:* #33

### ONB-4 — Validierung vor Speicherung
Bevor ein eingegebener Key gespeichert wird, prüft das System ihn mit einem
minimalen Aufruf gegen den gewählten Anbieter. Schlägt der Aufruf fehl —
ungültiger Key oder Anbieter nicht erreichbar —, wird der Key nicht gespeichert,
die Instanz bleibt im Onboarding-Modus, und das System antwortet mit einem
klaren, hart-codierten Hinweis samt der Möglichkeit, es erneut zu versuchen.

*Tickets:* #33

### ONB-5 — Persistente Speicherung außerhalb des Repos
Ein validierter Key wird persistent gespeichert: je Instanz, in einer Datei
neben dem Code, per `.gitignore` aus dem Repo ausgeschlossen und mit
Dateirechten auf den Eigentümer beschränkt. Die Speicherung übersteht einen
Neustart — eine einmal eingerichtete Instanz durchläuft das Onboarding nicht
erneut.

*Tickets:* #33

### ONB-6 — Bindung der Familien-Gruppe
Mit dem erfolgreichen Abschluss des Onboardings wird die Gruppe, in der das
Onboarding begonnen wurde, als Familien-Gruppe der Instanz gebunden (EC-2) und
ebenfalls persistent gespeichert (ONB-5). Ist die Familien-Gruppe bereits per
Umgebungsvariable oder Konfigurationsdatei gesetzt, gilt diese vorrangig — das
Onboarding bindet dann keine abweichende Gruppe.

*Tickets:* #33

### ONB-7 — Moduswechsel in den KI-Modus
Nach erfolgreicher Validierung (ONB-4) und Speicherung (ONB-5) verlässt die
Instanz den Onboarding-Modus: ab dann gelten die regulären Eltern-Chat-
Anforderungen (EC-4 ff.). Das System bestätigt den Abschluss mit einer
hart-codierten Nachricht in der Familien-Gruppe.

*Tickets:* #33

### ONB-8 — Schutz des Keys
Das System spiegelt einen entgegengenommenen Key zu keinem Zeitpunkt im Klartext
zurück — weder in Bestätigungen noch in Fehlermeldungen noch in Logs.

*Tickets:* #33

## 4. Tests

### ONB-9 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec, die Code-Verhalten beschreibt, hat einen
automatisierten Test (analog EC-17). Der KI-Anbieter wird in diesen Tests durch
eine kontrollierte Doppelung ersetzt — insbesondere der Validierungs-Aufruf
(ONB-4) läuft so reproduzierbar und ohne Netz.

*Tickets:* #33

---

## Offene Punkte

- **OPEN-ONB-A — Mehrere Gruppen vor Abschluss.** Wird der Bot vor dem
  Onboarding-Abschluss mehreren Gruppen hinzugefügt, ist die Zuordnung
  mehrdeutig. V1: die zuletzt hinzugefügte Gruppe gilt als Onboarding-Gruppe;
  eine robustere Regel ist bei Bedarf nachzuziehen.

- **OPEN-ONB-B — Key-Wechsel & Anbieterwechsel nach dem Onboarding.** Wie ein
  bereits eingerichteter Key ersetzt oder der Anbieter gewechselt wird, ist
  nicht Teil von V1 — eigenes Ticket.

- **OPEN-ONB-C — Löschen der Key-Nachricht.** Ob der Bot die Privatchat-
  Nachricht mit dem Key nach dem Lesen löscht (Telegram-Verlauf), ist offen.

## Entscheidungen

### E-ONB-1 — Hart-codierter Onboarding-Modus, kein LLM
*Datum:* 2026-05-21

Das Onboarding läuft vollständig deterministisch ohne Sprachmodell.

**Verworfen:** eine Heuristik oder ein kleines Modell zum Deuten der
Nutzereingaben. Zum Zeitpunkt des Onboardings gibt es per Definition noch keinen
KI-Zugang — die ersten Schritte hart zu codieren ist kein Workaround, sondern
die einzige Möglichkeit. Entsprechend bleibt der Funktionsumfang im
Onboarding-Modus bewusst eng: feste Nachrichten, feste Abläufe.

### E-ONB-2 — Key-Eingabe im Privatchat
*Datum:* 2026-05-21

Der Anbieter-Key wird im 1:1-Privatchat mit dem Bot eingegeben, nicht in der
Familien-Gruppe.

**Verworfen:** Eingabe in der Gruppe mit anschließendem Löschen der Nachricht
durch den Bot. Der Key wäre kurzzeitig für alle Mitglieder sichtbar und bliebe
im Telegram-Verlauf der sendenden Person. Der Privatchat hält das Geheimnis von
Anfang an klein.

### E-ONB-3 — Onboarding bindet die Familien-Gruppe
*Datum:* 2026-05-21

Mit dem Onboarding-Abschluss wird die Onboarding-Gruppe als Familien-Gruppe
gebunden (ONB-6).

**Verworfen:** die Familien-Gruppe ausschließlich per Umgebungsvariable/
Konfiguration zu setzen. Dann wäre das Setup nicht allein per Chat vollständig —
es bliebe ein manueller Konfigurationsschritt, den das Onboarding gerade
abnehmen soll. Eine vorhandene Env-/Config-Bindung hat dennoch Vorrang (ONB-6),
damit ein bewusst gesetzter Wert nicht überschrieben wird.

### E-ONB-4 — Anbieter-Key persistent außerhalb des Repos
*Datum:* 2026-05-21

Der per Onboarding eingegebene Key wird in einer gitignorierten Per-Instanz-
Datei gespeichert, Dateirechte auf den Eigentümer beschränkt.

**Verworfen:** (1) den Key nur im Prozess-Speicher zu halten — ein Neustart
würde das Onboarding erzwingen; (2) die Ablage in der Gesprächs-Datenbank
(EC-16) — sie würde ein Geheimnis mit den Gesprächsdaten in einer Datei
vermischen. Dies ergänzt EC-15: der Anbieter-Key darf nun auch aus diesem
Onboarding-Speicher stammen, nicht nur aus einer Umgebungsvariablen — er liegt
weiterhin nie im Repo.

### E-ONB-5 — Bot-Token bleibt Env-konfiguriert
*Datum:* 2026-05-21

Das Onboarding richtet den **Anbieter-Key** ein, nicht den Telegram-Bot-Token.

Der Bot-Token kann nicht per Chat eingerichtet werden: ohne ihn gäbe es den Bot
und damit den Chat-Kanal überhaupt nicht (Henne-Ei). Er bleibt daher zwingend
über eine Umgebungsvariable gesetzt (EC-15). Das Onboarding setzt genau dort an,
wo ein Chat-Kanal bereits existiert, aber noch kein KI-Zugang.
