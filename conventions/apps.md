# Apps — Konvention     (ID-Präfix: APP)

XBuddy besteht aus Apps (Plan-Buddy, Wetter-Buddy, …). Sie besitzen
Daten, Funktion und Schnittstellen — keine Plattform-Logik, die sich
mehrere Apps teilen. Dieser Abschnitt beschreibt, wie eine App gebaut
wird. Der Eltern-Chat ist keine App, sondern die heutige V1-Inkarnation
der Familien-Schnittstelle (Plattform-Bereich, siehe
`specs/constitution.md`); APP-5 grenzt das ab.

### APP-1 — Eine App besitzt Daten, Funktion und Schnittstelle
Jede XBuddy-App besitzt ihre eigenen Daten, ihre eigene Funktion und
stellt beides über Schnittstellen bereit. Andere XBuddy-Apps sind
**Nutzer** dieser Schnittstellen, nicht Mit-Eigentümer.

Klare Eigentümerschaft hält Abhängigkeiten einseitig (CLAUDE.md §6).
Eine Funktion mit zwei Eigentümern driftet auseinander.

### APP-2 — Eine App-Fähigkeit existiert genau dann, wenn die App installiert ist
Konsumenten dürfen die Schnittstelle einer App nur nutzen, wenn die App
selbst installiert ist. Fehlt die App, fehlt die Fähigkeit — der
Konsument antwortet entsprechend, statt mit gemockten Werten zu arbeiten.

Aus Sicht eines Eltern-Chat-Skills heißt das: „Termin eintragen" gibt es
nur, wenn der Plan-Buddy installiert ist.

### APP-3 — Andere Apps sprechen eine App nur über deren Schnittstelle an
Andere Apps lesen und schreiben den Daten-Bereich einer fremden App
ausschließlich über die spezifizierte HTTP-Schnittstelle. Direkter
Datei-Zugriff auf den Daten-Bereich einer fremden App ist verboten.

Konsumenten mit eigenem In-Memory-State (z. B. Plan-Buddy-Reader)
sehen Direkt-Schreibvorgänge nicht; die Schnittstelle ist der Vertrag,
der Konsistenz garantiert (Refs #140, EC-21).

### APP-4 — Familienseitige Beiträge: Wohnort und Pflege (Verortung, nicht Mechanik)

Eine App, die etwas in der Familien-Schnittstelle anbietet (Aufgabe im
Eltern-Chat, V1: Skill-Adapter), liefert diesen Beitrag nicht durch
Cross-Komponenten-Imports. Der Skill-Adapter wohnt physisch in der
Familien-Schnittstelle (heute `eltern-chat/skills/`); gepflegt wird er
vom App-Eigentümer als Code-Review-Vertrag (der App-Owner reviewt
Änderungen an seinem Skill-Adapter mit, auch wenn die Datei nicht in
seiner App liegt).

**Diese Konvention legt nur den Wohnort und die Pflege fest, nicht den
operativen Lego-Anschluss.** Der heutige Installations- und
Aktivierungs-Mechanismus fehlt als spezifizierter Prozess; bis er
existiert, müssen Apps für ihren familienseitigen Beitrag den
Eltern-Chat-Mittelpunkt punktuell mit anfassen. Das ist ein bekanntes
offenes Problem (siehe #296 — App-Installations-Prozess für
Familien-Schnittstelle fehlt), keine Soll-Architektur. Welche Form
der Installations-/Aktivierungs-Mechanismus annehmen wird (Skill,
Plattform-Funktion, Registry-Eintrag, anderes), ist nicht entschieden.

### APP-5 — Die Familien-Schnittstelle ist Plattform-Bereich, kein App-Eigentümer

Die Familien-Schnittstelle (heute: Eltern-Chat) besitzt das Gespräch,
das Routing zu den App-Fähigkeiten sowie plattform-eigene Daten
(Gesprächsverlauf, Gruppen-Bindung, Onboarding-Speicher) — aber keine
Domänen-Daten der Apps. Eine Aufgabe wie „Termin eintragen" ist nicht
im Eigentum der Familien-Schnittstelle, sondern der zuständigen App
(Plan-Buddy); die Familien-Schnittstelle führt den Dialog (siehe E-EC-4
`specs/platform/eltern-chat.md`), die App führt das fachliche Gate
(siehe z. B. TES-7 `specs/platform/termin-eintragen.md`).

APP-1 bis APP-4 gelten für Apps; die Familien-Schnittstelle ist davon
ausgenommen, weil sie keine App-Funktion besitzt. Ihre eigene Spec ist
`specs/platform/eltern-chat.md`.
