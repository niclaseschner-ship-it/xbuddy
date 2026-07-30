# Eltern-Chat Onboarding — Spec     (ID-Präfix: ONB)

> Status: V1 + V2 · Refs #33, #639

Das KI-Anbieter-Onboarding bringt eine frische Eltern-Chat-Instanz vom Zustand
»kein KI-Zugang« in den Zustand »KI aktiv«. Es läuft, solange noch kein
Anbieter-Key vorliegt, in einem deterministischen, **hart-codierten** Modus —
denn ein Sprachmodell steht zu diesem Zeitpunkt per Definition noch nicht zur
Verfügung. Geführt wird im Chat: Einstieg in der Gruppe, Key-Eingabe im
Privatchat, Validierung, Speicherung. Mit dem Abschluss wird die Instanz
KI-aktiv und die Familien-Gruppe gebunden.

V2 (Refs #639) öffnet die Anbieter-Wahl: Die Einstiegs- und Privatchat-Texte
listen die verfügbaren KI-Anbieter (heute Claude + Mistral) statt einer hart-
codierten Anbieter-Festlegung; eine bereits eingerichtete Instanz kann den
Anbieter über einen eigenen Eltern-Chat-Skill wechseln, ohne den Pi anfassen
zu müssen. Das Pattern bleibt deterministisch hart-codiert (E-ONB-7).

Diese Spec gehört zur Komponente `eltern-chat/` und baut auf
[`eltern-chat.md`](eltern-chat.md) auf — insbesondere EC-2 (Familien-Gruppe als
Berechtigung), EC-8 (Aufgaben-Katalog — Heimat des Wechsel-Skills), EC-11
(KI-Anbieter je Instanz wählbar) und EC-15 (Konfigurationswerte).

**V1-Scope:** der Weg von »kein Anbieter-Key« zu »KI aktiv« — Onboarding-Modus,
Einstieg, Anbieter-Wahl (V2), Key-Entgegennahme im Privatchat, Validierung,
persistente Speicherung, Bindung der Familien-Gruppe, Moduswechsel.

**V2-Scope (Refs #639):** Anbieter-Wahl-Dialog im Initial-Onboarding (ONB-10)
+ Anbieter-Wechsel-Skill nach dem Onboarding (ONB-11..ONB-12). Schließt
OPEN-ONB-B (alter Out-of-Scope-Punkt).

**Weiter Out-of-Scope** (jeweils eigenes Ticket, sobald gebraucht): weiteres
Onboarding (Familienmitglieder, Buddys, Geräte) · Rotation eines Keys ohne
Anbieterwechsel · Anbieter-Hinzufügen/-Entfernen aus der zentralen Liste
durch die Familie (heute Repo-Edit).

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
mit dem Bot fortzusetzen.

Im Onboarding-Modus bleibt der Bot in der Gruppe nie stumm: solange noch kein
Schlüssel vorliegt, beantwortet er **jede** Gruppennachricht mit derselben
Einstiegs-Nachricht — nicht nur die ausdrückliche Ansprache. Der Erstkontakt
darf nicht an der Erwähnungs-Erkennung hängen: wer den Hinzufügen-Moment
verpasst hat oder den Bot nicht exakt erwähnt, bekommt die Anleitung trotzdem
(E-ONB-6). Erst mit dem Abschluss des Onboardings (ONB-7) gilt wieder EC-5 —
dann reagiert der Bot in der Gruppe nur noch auf ausdrückliche Ansprache. Im
Privatchat wird weiterhin jede Nachricht beantwortet (ONB-3).

Damit der Bot Gruppennachrichten überhaupt empfängt, muss der Telegram-
Privacy-Modus des Bots deaktiviert sein (BotFather → `/setprivacy` →
*Disable*; die Änderung wirkt für eine bestehende Gruppe erst, nachdem der Bot
dort erneut hinzugefügt wurde) — alternativ genügt es, den Bot in der Gruppe
zum Administrator zu machen, dann empfängt er unabhängig vom Privacy-Modus alle
Nachrichten. Bei aktivem Privacy-Modus stellt Telegram dem Bot nur Kommandos
und Antworten auf seine Nachrichten zu; eine schlichte Nachricht und auch eine
bloße @-Erwähnung erreichen ihn dann nicht. Das ist eine Betriebs-Voraussetzung
der Instanz, kein Code-Verhalten, und daher ohne eigenen Test (ONB-9).

*Tickets:* #33

## 3. Einrichtung

### ONB-3 — Key-Eingabe im Privatchat
Die Übermittlung des Anbieter-Keys erfolgt im Privatchat zwischen einem
Familienmitglied und dem Bot — nie in der Gruppe, damit der Key nicht für andere
Mitglieder sichtbar wird. Der Bot führt im Privatchat hart-codiert durch die
Anbieter-Wahl und nimmt den Key als Nachricht entgegen. Berechtigt zur Eingabe
ist, wer Mitglied der Gruppe ist, in der das Onboarding begonnen wurde — geprüft
live (analog EC-2).

Die Privatchat-Konversation folgt dem Session-Muster aus
`conventions/privatchat-session.md` (SESS-1 Worker-Form, SESS-2
Zwischenzustand nur im Speicher, SESS-3 30-Minuten-Timeout, SESS-4
Re-Prompt bei nicht-passender Eingabe) — eine Privatnachricht, die
erkennbar keine Schlüssel-Eingabe ist (Begrüßung, Frage, Foto), wird
nach SESS-4 nicht als ungültig gewertet, sondern mit der Anleitung
re-prompted.

*Tickets:* #33

### ONB-4 — Validierung durch probeweises Speichern
Das System validiert einen eingegebenen Key, indem es ihn **probeweise
speichert** — in den litellm-Motor-Slot des gewählten Anbieters
(`eltern-chat-litellm-<purpose>-api-key`) — und ihn dann **über den Motor**
mit einem minimalen Aufruf prüft. Gültig: der Key bleibt im Slot stehen und ist
damit gespeichert (der separate Speicherschritt ONB-5 verschmilzt mit der
Validierung). Ungültig — falscher Key oder Anbieter nicht erreichbar —: der
probeweise geschriebene Slot wird **wieder gelöscht**, die Instanz bleibt im
Onboarding-Modus, und das System antwortet mit einem klaren, hart-codierten
Hinweis samt der Möglichkeit, es erneut zu versuchen.

Der Grund für »probeweise speichern → über den Motor validieren → bei Fehler
löschen« (statt »erst testen, dann speichern«): der Motor liest den Key
ausschließlich aus dem Slot (ein Motor-Weg, RAT-20); ein Ad-hoc-Key ohne Slot
ließe sich nicht über den Motor pingen. Das Crash-Fenster zwischen Schreiben
und Löschen-bei-ungültig ist durch den Boot-Check gegen present-but-invalid
(SVC-7, leerer Slot zählt als nicht präsent) und das Überschreiben beim
nächsten Onboarding abgedeckt (lokaler Ein-Nutzer-Pi, 0600).

*Tickets:* #33, #1510

### ONB-5 — Persistente Speicherung außerhalb des Repos
Ein validierter Key und die gebundene Familien-Gruppe (ONB-6) werden persistent
gespeichert: je Instanz, außerhalb des Repos, mit Dateirechten auf den
Eigentümer beschränkt (`0600`). Seit #84 liegen diese Werte im zentralen
Zugangsdaten-Speicher der Instanz (`zugangsdaten.md`, ZD-1: ein Speicher je
Instanz) — als benannte Zugangsdaten (ZD-2). Es gibt damit nicht mehr zwei
nebeneinanderliegende Geheimnis-Dateien. Die Speicherung übersteht einen
Neustart — eine einmal eingerichtete Instanz durchläuft das Onboarding nicht
erneut.

Gelesen und geschrieben wird ausschließlich im zentralen Speicher; dessen
`0600`-Rechte und atomares Schreiben gelten nach `zugangsdaten.md` ZD-3 /
DCOMP-4. Die Zwei-Schritt-Deprecation (CLAUDE.md §6) ist mit #336 (Schritt 2)
abgeschlossen — die Alt-Klasse und die Alt-Datei sind entfernt.

*Tickets:* #33, #100, #84, #336

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

### ONB-10 — Anbieter-Wahl-Dialog im Initial-Onboarding (V2)
Statt einer hart-codierten Anbieter-Festlegung listet die Einstiegs-Nachricht
(ONB-2) die verfügbaren KI-Anbieter auf — heute Claude und Mistral. Im
Privatchat-Dialog (ONB-3) fragt der Bot **zuerst** nach dem gewünschten
Anbieter, dann nach dem Key.

Die Anbieter-Liste lebt als zentrale Konstante im Code (`ANBIETER_LISTE` im
Wechsel-Skill); je Anbieter trägt sie: Name, Anzeige-Beschreibung. Der
Validierungs-Ping (ONB-4) läuft seit #1510 nicht mehr über einen Hand-Vendor-
Adapter, sondern über den geteilten Motor (`tools.llm`, litellm-Slot des
Anbieters). Eine zusätzliche Anbieter-Aufnahme ist heute Repo-Edit; eine
Familien-seitige
Aufnahme/Entfernung ist Out-of-Scope.

Die Privatchat-Konversation folgt weiterhin dem Session-Muster aus
`conventions/privatchat-session.md` (SESS-1..4); eine Antwort, die keine der
verfügbaren Optionen trifft, wird per SESS-4 re-prompted (analog ONB-3).

**Verworfen:** eine LLM-gestützte Anbieter-Beratung (z. B. „welcher Anbieter
passt zu eurer Privacy-Linie?"). Der Onboarding-Modus bleibt deterministisch
hart-codiert (E-ONB-1) — die Anbieter-Wahl ist genau zwei Eingabe-Schritte,
ohne LLM-Beteiligung möglich und so robust gegen Fehl-Deutung.

*Tickets:* #639

## 4. Anbieter-Wechsel

### ONB-11 — Anbieter-Wechsel-Skill `anbieter_wechseln` (V2)
Eine bereits eingerichtete Instanz bietet im Eltern-Chat-Katalog (EC-8) den
Skill `anbieter_wechseln` an. Trigger ist eine natürliche User-Aufforderung
in Familien-Gruppe oder Privatchat (z. B. „LLM wechseln", „Anbieter ändern",
„auf Mistral umstellen", „wechsel zu claude"). Berechtigt ist jedes
Familien-Mitglied (EC-2).

Der Skill führt im **Privatchat** (E-ONB-2 / ONB-3) durch — zwei Pfade
je nach Slot-Befund (`zugangsdaten.md` ZD-2 Multi-Slot-Schema):

**Pfad A — Bekannter Anbieter (kein Re-Key).** Liegt für den
gewählten Anbieter bereits ein Key im litellm-Slot (z. B.
`eltern-chat-litellm-claude-api-key`, #1510), wird der aktive Vendor in der
Konfiguration umgeschaltet, **ohne** den Key erneut zu erfragen. Der
Wechsel ist deterministisch und sofort: keine Eingabe, kein
Validierungs-Ping (der Key hat schon einmal funktioniert; ein erneutes
Ping wäre Reibung ohne Nutzen). Quittung in der Familien-Gruppe:
„KI-Anbieter ist jetzt X." Wer den **aktuell aktiven** Anbieter erneut
wählt, bekommt die harte Same-Provider-Quittung („Du nutzt diesen
Anbieter bereits — nichts geändert.").

**Pfad B — Neuer Anbieter (Re-Key-Sequenz).** Ist der litellm-Slot des
gewählten Anbieters noch leer, läuft die Initial-Sequenz:

1. Wahl des neuen Anbieters aus der zentralen Liste (ONB-10).
2. Eingabe des neuen Keys (analog ONB-3 — Privatchat, Schutz vor
   Gruppen-Sichtbarkeit).
3. Validierung nach ONB-4: der Key wird **probeweise** in den litellm-Slot des
   neuen Anbieters geschrieben und **über den Motor** validiert; bei Fehler wird
   der Slot wieder gelöscht.
4. Der validierte Key liegt damit bereits im Slot (der Schreibschritt
   verschmilzt mit der Validierung, ONB-12) — es folgt nur noch die
   Aktiv-Vendor-Umschaltung in der Konfiguration (`provider-name`-Slot).
5. Bestätigung in der Familien-Gruppe analog ONB-7 — der Key wird nicht
   zurückgespiegelt (ONB-8).

**Pfad-Wahl deterministisch ohne LLM.** Der Skill prüft den litellm-Slot-Befund
des gewählten Anbieters (truthy-Check über die ZD-Library); das LLM
entscheidet nicht zwischen Pfad A und Pfad B.

Der Skill nutzt das Schreib-Aufgaben-Pattern aus EC-10 (propose→confirm) nicht
zwingend — die deterministische Privatchat-Sequenz mit Validierungs-Ping als
Schluss-Gate ist sicherer als ein konversationaler Bestätigungs-Schritt (analog
E-ONB-1-Gedanke: kein LLM im Wechsel-Akt).

**Verworfen:** (a) Anbieter-Wechsel direkt in der Familien-Gruppe oder mit
Sichtbarkeit für andere Mitglieder — derselbe Grund wie E-ONB-2 für das
Initial-Onboarding. (b) Bekannten Anbieter trotzdem re-keyen, „für den
Fall, dass der alte Key abgelaufen ist" — Reibung ohne Nutzen; abgelaufener
Key meldet sich beim nächsten Provider-Call mit Auth-Fehler, dann läuft die
Re-Key-Sequenz von dort. (c) LLM lässt die Pfad-Wahl entscheiden — bricht
E-EC-4 und E-ONB-1.

*Tickets:* #639, #663 (Multi-Slot-Erweiterung + Pfad A)

### ONB-12 — Atomares Ersetzen beim Anbieter-Wechsel
Bei einem Anbieter-Wechsel (ONB-11) ersetzt das System den Eintrag im
zentralen Zugangsdaten-Speicher (`zugangsdaten.md` ZD-1..3) **atomar**
(Temp-Datei + `os.replace`, DCOMP-4). Der alte Eintrag wird erst dann
überschrieben, wenn:

(a) der Validierungs-Ping (ONB-4) gegen den neuen Anbieter erfolgreich war,
    UND
(b) der atomare Schreibvorgang vollständig durchgelaufen ist.

Bricht (a) ab — ungültiger Key oder neuer Anbieter nicht erreichbar —, bleibt
der alte Anbieter aktiv und der alte Eintrag byte-gleich; der Skill antwortet
mit einem klaren, hart-codierten Hinweis samt Möglichkeit, es erneut zu
versuchen (analog ONB-4 im Initial-Onboarding).

Bricht (b) ab — Datei-Permissions, Plattenplatz —, bleibt der alte Eintrag
byte-gleich; der Skill meldet einen klaren System-Fehler, die laufende
Instanz wird **nicht** unterbrochen.

Race-Schutz: parallele Skill-Aufrufe (zwei Familien-Mitglieder wechseln
gleichzeitig) sind über die atomare `os.replace`-Naht der ZD-Schicht
geschützt; das letzte erfolgreich validierte Schreiben gewinnt, die andere
Sitzung erhält einen Versuch-erneut-Hinweis.

*Tickets:* #639

## 5. Tests

### ONB-9 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec, die Code-Verhalten beschreibt, hat einen
automatisierten Test (analog EC-17). Der KI-Anbieter wird in diesen Tests durch
eine kontrollierte Doppelung ersetzt — insbesondere der Validierungs-Aufruf
(ONB-4) läuft so reproduzierbar und ohne Netz.

*Tickets:* #33

### ONB-13 — Tests für ONB-10..ONB-12 (V2)
Analog ONB-9, mit kontrollierter Doppelung **beider** Anbieter-Adapter
(Claude + Mistral als V2-Bestand). Pflicht-Pfade:

- ONB-10: der Wahl-Dialog im Initial-Onboarding bietet alle in der zentralen
  Liste eingetragenen Anbieter an, re-prompt bei nicht-passender Antwort
  (SESS-4).
- ONB-11 Pfad A (bekannter Anbieter, kein Re-Key): vorbefüllte ZD-Slots
  für Anthropic UND Mistral; Skill wechselt zwischen ihnen ohne
  Key-Eingabe, ohne Validierungs-Ping. Quittung in der Familien-Gruppe
  enthält den neuen Vendor-Namen.
- ONB-11 Pfad B (neuer Anbieter, Re-Key): Slot für Mistral fehlt, Skill
  durchläuft die volle ONB-3/ONB-4-Sequenz (Privatchat-Eingabe,
  Validierungs-Ping, atomares Schreiben, Aktiv-Vendor-Umschaltung,
  Familien-Gruppe-Quittung).
- ONB-11 Same-Provider-Quittung: wer den aktuell aktiven Anbieter erneut
  wählt, bekommt eine deterministische Quittung; nichts wird geändert.
- ONB-11 Multi-Slot-Migration (Welle A): vorbefüllter Single-Slot
  `eltern-chat-provider-api-key` (Legacy-Form) + aktiver `provider=claude`
  → Skill liest vendor-spezifischen Slot `eltern-chat-anthropic-api-key`,
  schreibt in diesen vendor-spezifischen Slot. Single-Slot bleibt vorerst
  lesbar (Fallback bei Lücken), wird aber nicht mehr beschrieben.
- ONB-12 Validierungs-Fehler: Pfad-B-Wechsel-Versuch mit ungültigem Key →
  neuer vendor-spezifischer Slot wird NICHT geschrieben, alter Anbieter
  bleibt aktiv.
- ONB-12 Schreib-Fehler: provozierter Schreibfehler beim Schreiben des
  neuen Slots → kein Slot-Schreiben, alter Anbieter bleibt aktiv,
  laufende Instanz nicht unterbrochen.
- ONB-8-Schutz im Wechsel-Skill: weder alter noch neuer Key im Klartext in
  Bestätigungen, Fehlermeldungen oder Logs (gilt für beide Pfade).

*Tickets:* #639, #663 (Pfad-A + Multi-Slot-Migration-Tests)

---

## Offene Punkte

- **OPEN-ONB-A — Mehrere Gruppen vor Abschluss.** Wird der Bot vor dem
  Onboarding-Abschluss mehreren Gruppen hinzugefügt, ist die Zuordnung
  mehrdeutig. V1: die zuletzt hinzugefügte Gruppe gilt als Onboarding-Gruppe;
  eine robustere Regel ist bei Bedarf nachzuziehen.

- ~~**OPEN-ONB-B** — Key-Wechsel & Anbieterwechsel nach dem Onboarding.~~
  **Geschlossen 2026-06-10 durch ONB-11/ONB-12 (V2, Refs #639).** Der
  Anbieter-Wechsel ist als Skill `anbieter_wechseln` im Eltern-Chat-Katalog
  spezifiziert; ein reiner Key-Rotations-Pfad ohne Anbieterwechsel ist
  weiterhin Out-of-Scope (eigenes Ticket bei Bedarf).

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
*Datum:* 2026-05-21 · **Abgelöst durch ZD (#84, abgeschlossen #336)**

> **Abgelöst:** Der eigene Onboarding-Speicher (Per-Instanz-Datei neben dem
> Code) ist durch den zentralen Zugangsdaten-Speicher ersetzt — siehe ONB-5 und
> `zugangsdaten.md` (ZD-1, OPEN-ZD-B). Die Zwei-Schritt-Deprecation ist
> abgeschlossen: Schritt 1 (#84, read-both / write-ZD, lazy-Migration) und
> Schritt 2 (#336, Alt-Klasse/-Datei entfernt). Die Entscheidung selbst — Key
> außerhalb des Repos, nicht im Prozess-Speicher, nicht in der
> Gesprächs-Datenbank — bleibt gültig.

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
und damit den Chat-Kanal überhaupt nicht (Henne-Ei). Er ist daher über eine
Umgebungsvariable gesetzt (EC-15) — siehe die Ergänzung unten zur zusätzlichen
Auflösung aus dem zentralen Zugangsdaten-Store. Das Onboarding setzt genau dort
an, wo ein Chat-Kanal bereits existiert, aber noch kein KI-Zugang.

**Ergänzung 2026-07-27 (Nic-Setzung — zentraler Store als Zusatz-Quelle, Env als Fallback).**
Der Bot-Token **darf zusätzlich aus dem zentralen Zugangsdaten-Store** aufgelöst
werden (Konsistenz mit der Setzung »Secrets zentral aus der Datenbank«, analog
zum kibuddy-Bot-Token nach #1440). Die Auflösung ist **additiv und rückrollbar**:

- Bevorzugte Quelle ist der Store-Slot (anbieter-/dienst-benannt, siehe
  zugangsdaten.md).
- **Die Umgebungsvariable (EC-15) bleibt der garantierte Fallback** und löst das
  Henne-Ei-Problem weiterhin: kann der Store nicht gelesen werden (z. B. beim
  Erst-Boot, bevor er befüllt ist), greift zwingend die Env-Variable. Damit
  bleibt der Bot immer startfähig.

Der Token liegt weiterhin **nie im Repo**. Diese Ergänzung hebt die frühere
»zwingend nur Env«-Formulierung additiv auf, ohne die Startfähigkeit zu gefährden.

### E-ONB-6 — Im Onboarding-Modus auf jede Gruppennachricht antworten
*Datum:* 2026-05-22

Im Onboarding-Modus antwortet der Bot auf jede Gruppennachricht mit der
Einstiegs-Nachricht, nicht nur auf ausdrückliche Ansprache.

**Verworfen:** die Reaktion wie im KI-Modus an die ausdrückliche Ansprache
(EC-5) zu koppeln. Der Live-Test zeigte: hängt der Erstkontakt an der
Erwähnungs-Erkennung, genügt eine einzige Fehlerquelle — falsche Schreibweise,
nicht erkanntes Entity, aktiver Privacy-Modus —, damit der Bot stumm bleibt und
das Onboarding nicht in Gang kommt. Da der Bot im Onboarding-Modus ohnehin nur
eine einzige, feste Nachricht kennt, ist »immer antworten« hier unkritisch und
macht den Einstieg robust. Mit dem Abschluss (ONB-7) endet dieser Modus, und
EC-5 greift wieder.

### E-ONB-7 — Anbieter-Wechsel bleibt hart-codiert wie der Initial-Modus
*Datum:* 2026-06-10

Der Anbieter-Wechsel-Skill (ONB-11) führt deterministisch und ohne LLM-
Beteiligung an der Wechsel-Entscheidung — analog E-ONB-1 für den Initial-
Onboarding-Modus.

**Verworfen:** das laufende LLM (also den Anbieter, den die Familie gerade
verlässt) den Wechsel-Dialog formulieren zu lassen. Zwei Gründe:

1. **Anbieter-Unabhängigkeit der Wechsel-Naht** — der Wechsel-Akt darf nicht
   davon abhängen, wie gesprächsfähig oder gewillt der scheidende Anbieter
   gerade ist. Wenn die Familie wechselt, weil der alte Anbieter Probleme
   macht (Latenz, Erreichbarkeit, Rechnungsstreit), darf der Wechsel-Skill
   genau diesen alten Anbieter nicht als Gespräch-Voraussetzung tragen.
2. **Sicherheits-Gates deterministisch** (E-EC-4-Geist) — die kritische
   Schreib-Operation auf den Zugangsdaten-Speicher (ONB-12) bleibt
   maschinell prüfbar; eine LLM-formulierte Bestätigungssequenz wäre eine
   schwächere Form als ein Validierungs-Ping mit anschließendem atomarem
   Ersetzen.

Hart-codierte Nachrichten + Validierungs-Ping reichen, sind kleiner und
robuster.
