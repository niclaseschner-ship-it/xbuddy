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

*Tickets:* #27

### EC-7 — Ehrliche Grenze
Kann das System eine Anfrage nicht erfüllen — sie liegt außerhalb seiner
Aufgaben, oder eine Voraussetzung fehlt — sagt es das klar und nennt, was es
stattdessen tun kann. Es gibt keine erfundenen Fähigkeiten und keine
vorgetäuschten Ergebnisse. Das System führt keine Aufgabe aus, die nicht durch
eine definierte Aufgabe (Abschnitt 3) gedeckt ist.

*Tickets:* #27

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
Eine Aufgabe, die nur Information liefert und keine Familien-Daten verändert,
führt das System ohne Zwischenschritt aus und antwortet mit dem Ergebnis.

*Tickets:* #27

### EC-10 — Schreibende Aufgaben nur nach Bestätigung
Bevor eine Aufgabe ausgeführt wird, die Familien-Daten verändert, legt das
System einen strukturierten Vorschlag vor — was genau geschehen würde — und
führt die Aufgabe erst aus, nachdem ein Familienmitglied sie ausdrücklich
bestätigt hat. Ohne Bestätigung geschieht keine Veränderung. Die Bestätigung
ist eindeutig einem konkreten Vorschlag zugeordnet, auch wenn dazwischen andere
Nachrichten eingehen.

*Tickets:* #27

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
KI-Anbieter ausschließlich, was dafür nötig ist: den Anfrage-Inhalt (Text,
geteilte Bilder) und den Gesprächskontext (EC-6). Darüber hinausgehende
Familien-Daten werden nicht übermittelt. Diese Daten verlassen die
Geräte-Ebene der Familie; V1 übermittelt sie ohne Anonymisierung — siehe
Entscheidung E-EC-9 und Offener Punkt OPEN-EC-A.

*Tickets:* #27

### EC-14 — Anbieter nicht erreichbar
Schlägt der Aufruf des KI-Anbieters fehl oder bleibt aus, antwortet das System
dem Familienmitglied mit einem klaren Hinweis, dass die Anfrage gerade nicht
bearbeitet werden konnte, und bricht sauber ab. Es entsteht keine halbfertige
Aufgabe und keine stumme Nicht-Antwort.

*Tickets:* #27

## 5. Konfiguration

### EC-15 — Konfigurationswerte
Das System wird je Instanz über Konfigurationswerte eingerichtet. Der Bot-Token
wird ausschließlich über eine Umgebungsvariable gesetzt. Der Anbieter-API-Key
und die Familien-Gruppen-Chat-ID kommen aus Umgebungsvariable/Konfiguration oder
werden per Onboarding gesetzt (siehe
[`eltern-chat-onboarding.md`](eltern-chat-onboarding.md)); fehlt der
Anbieter-API-Key auf beiden Wegen, läuft die Instanz im Onboarding-Modus
(ONB-1). Geheimnisse liegen nie in einer Datei im Repo (CLAUDE.md §8). Priorität
je Wert: **Umgebungsvariable > Konfigurationsdatei > Onboarding-Speicher >
Default**.

| Wert                     | Default                 | Quelle                            |
|--------------------------|-------------------------|-----------------------------------|
| Telegram-Bot-Token       | (Pflicht, kein Default) | Env                               |
| Anbieter-API-Key         | (kein Default)          | Env · Onboarding (ONB-5)          |
| Familien-Gruppen-Chat-ID | (kein Default)          | Env · Config · Onboarding (ONB-6) |
| KI-Anbieter              | `claude`                | Env · Config                      |
| Anbieter-Modell          | Anbieter-Default        | Env · Config                      |
| Gesprächskontext-Tiefe   | letzte 20 Nachrichten   | Env · Config                      |

Werte, die nur als Code-Konstante existieren — ohne Override-Pfad — sind
Spec-Verletzung (CLAUDE.md §6 Daten vs. Code).

*Tickets:* #27 · #33

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
*Datum:* 2026-05-21

V1 übermittelt Anfrage-Inhalte ohne Anonymisierung an den KI-Anbieter (EC-13).

Dies ist eine **bewusste, dokumentierte Abweichung** vom Qualitätsattribut
Privacy der Constitution (§3, »Anonymisierungs-Layer vor Verlassen der
Geräte-Ebene«). Sie ist befristet auf die Prototyp-/Bewertungsphase und
abgesichert durch die ausdrückliche Einwilligung der Test-Familien. Begründung:
Zuerst muss sich zeigen, welcher Anbieter taugt und wie der Datenfluss
tatsächlich aussieht — ein Anonymisierungs-Layer davor wäre Bau ohne belegte
Grundlage. Die Aktivierung ist als OPEN-EC-A festgehalten und bleibt eine
Voraussetzung für den Regelbetrieb über die Testphase hinaus.
