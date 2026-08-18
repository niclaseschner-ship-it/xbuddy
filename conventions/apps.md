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

### APP-7 — Token-Sharing-EnvironmentFile (Mini-App-Auth-Token-Heimat)

Konsumierende Buddys, die Telegram-Mini-Apps mit
`Authorization: tma <initData>`-Header validieren (siehe
`conventions/mini-app-design.md` MAD-7), brauchen Zugriff auf den
Telegram-Bot-Token. Der Token wohnt **ausschließlich** im
Eltern-Chat-Eigentum (`__XBUDDY_DATA__/eltern-chat/.env`); andere Buddys
lesen ihn als systemd-`EnvironmentFile=` aus genau dieser Datei.

```
# Beispiel: seiten/seiten.service (oder essen/essen.service, …)
EnvironmentFile=__XBUDDY_DATA__/eltern-chat/.env
```

**Niemals Token duplizieren** in service-eigene `.env`-Dateien — Pi-Drift-
Risiko (essen-einkauf-Live-Fix 2026-06-12: ENV-Naming-Drift zwischen Kopien
führte zu stiller Auth-Falschnegative). Wenn der Konsument einen anderen
ENV-Variablen-Namen erwartet, **Code anpassen** statt Alias-Eintrag in der
`.env` — die `.env` bleibt einzige Wahrheit.

**Pro Backend-Instanz ein Bot-Token** (Multi-Tenancy via Hardware-Trennung,
Nic-Setzung 2026-06-15): jede Familie hat eigene Pi-Hardware, eigenen Bot,
eigenen Token. Keine `BOT_TOKEN_FAMILIE_<id>`-Suffix-Mechanik im Code; die
Familie ist die Pi-Instanz.

**Begründung:** Token-Duplikation in zwei `.env`-Dateien ist eine bekannte
Drift-Quelle (ein Update an einer Stelle, vergessen an der anderen → eine
Mini-App authentifiziert weiter, eine 401). EnvironmentFile-Sharing
zentralisiert die Token-Heimat, ohne den Konsumenten-Buddys Zugriff auf
andere Eltern-Chat-Secrets zu geben (`EnvironmentFile=` lädt nur Variablen,
nicht ganze Dateien).

**Verworfen:** (a) Token in zentrale Geheimnis-Datenbank
(`tools/zugangsdaten/`) verschieben — der Bot-Token ist Eltern-Chat-eigene
Identität, nicht familien-übergreifender Vendor-Key (das ist `zugangsdaten.md`
Eigentum); (b) eigene `secrets/`-Datei pro Buddy mit Sync-Mechanismus —
EnvironmentFile-Sharing ist die einfachere systemd-native Lösung.

*Tickets:* #684 (Token-Sharing-Mechanik), #708 (Verortung als APP-7),
Ratifizierung `decisions/RAT-47` (Punkt 5)

### APP-6 — Spec-Datei-Verortung: buddies/ vs. platform/

Eine Fähigkeit mit eigener **Display-View** für die Familie wird unter
`specs/buddies/<name>.md` spezifiziert. Eine Fähigkeit **ohne** eigene
Display-View — z. B. Router, Familien-/Geräte-Registry, Eltern-Chat (Telegram-getriggert)
— wird unter `specs/platform/<name>.md` spezifiziert.

Diese Heuristik ergänzt APP-5 (Plattform-Bereich vs. App-Eigentümer) um die
konkrete Datei-Verortung: APP-5 grenzt inhaltlich ab, was Plattform-Bereich ist
und was App; APP-6 übersetzt das in die Ordnerwahl für die Spec-Datei.
