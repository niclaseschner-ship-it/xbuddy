# Apps — Konvention     (ID-Präfix: APP)

XBuddy besteht aus Apps (Plan-Buddy, Eltern-Chat, Wetter-Buddy, …). Sie
besitzen Daten, Funktion und Schnittstellen — keine Plattform-Logik, die
sich mehrere Apps teilen. Dieser Abschnitt beschreibt, wie eine App
gebaut wird.

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
