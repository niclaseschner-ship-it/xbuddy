# XBuddy — Constitution

> Die übergeordneten Prinzipien. Jede Komponenten-Spec und jedes Ticket
> ordnet sich dem unter. Ändert sich selten — Änderungen hier sind bewusste
> Richtungsentscheidungen, keine Detailarbeit.

## North Star

XBuddy ist erfolgreich, wenn ein Kind etwas selbst tun kann, wofür es vorher
ein Elternteil gebraucht hätte. Jede Anforderung misst sich daran:
verschiebt sie eine Aufgabe vom Elternteil zum Kind?

## Mitwachsen

Gleicher Inhalt, gleiche Daten — adressatengerecht übersetzt. Eine
Dreijährige, ein Zehnjähriger und die Eltern bekommen je die Aufbereitung,
die sie in ihrer aktuellen Entwicklung brauchen.

## Familien-Schnittstelle

Konfiguration und Auskunft für die Familie laufen über einen
plattform-eigenen, konversationellen Bereich in der Sprache der Familie —
nicht über eine zweite Settings-Welt, die Familien erst lernen müssten.
Heute ist diese Schnittstelle der Eltern-Chat; das Prinzip ist
kanal-unabhängig.

Die Familien-Schnittstelle ist Plattform-Bereich, nicht App: sie besitzt
das Gespräch, das Routing zu den Fähigkeiten der Apps und plattform-eigene
Daten (z. B. Gesprächsverlauf, Gruppen-Bindung, Onboarding-Speicher) —
aber keine Domänen-Daten der Apps. Die Fähigkeiten, die sie ausliefert
(Termin eintragen, Familie anlegen, Gerät anlegen …), gehören den
jeweiligen Apps; jede neue App, die etwas familienseitig Konfigurierbares
oder Abfragbares hat, trägt diese Beiträge über den Installations-Vorgang
der App in die Familien-Schnittstelle ein. Operative Ausformulierung:
`conventions/apps.md`.

Apps dürfen ergänzende, app-eigene Bedien-Oberflächen anbieten, wo das
Medium passt — etwa Direkt-Klick am Display oder visuelles Editieren
dichter Daten. Die Familien-Schnittstelle bleibt der eine Ort, an dem die
Familie das System in ihrer Sprache *anspricht*; sie ist nicht der
einzige Ort, an dem die Familie es *bedient*.

Der Maßstab ist nicht „Funktion verfügbar machen", sondern „Familie
entlasten". Onboarding-Reibung ist erlaubt, solange ihr eine spürbare
Entlastung unmittelbar folgt.

## Qualitätsattribute (in Prioritätsreihenfolge)

1. **Zuverlässigkeit** — funktioniert, wenn es gebraucht wird.
2. **Einfachheit** — die Familie wählt die Tiefe ihrer Einbindung;
   technik-affine Familien können tieferen Eingriff bekommen, technik-ferne
   werden vom Default getragen. Tiefe der Bedienbarkeit, kein
   Engagement-Stufenmodell.
3. **Privacy & Datensicherheit** — Verarbeitung in Deutschland,
   Anonymisierungs-Layer vor Verlassen der Geräte-Ebene.
4. **Offline-Fähigkeit** — mit Hub läuft XBuddy ohne Internet.
5. **Nicht-invasiv** — kein Engagement-Design, keine Pushes.

## App-Eigentümerschaft

XBuddy besteht aus Apps, die einander nutzen, nicht gemeinsam besitzen.
Jede App besitzt ihre Daten, ihre Funktion und ihre Schnittstelle —
Konsumenten sind Nutzer, nicht Mit-Eigentümer. Eine App-Fähigkeit
existiert für ihre Konsumenten genau dann, wenn die App installiert ist
(Plan-Buddy fehlt → der Eltern-Chat kann keine Termine eintragen).

Konsequenz für Plattform-Specs: was zwei Apps brauchen, wird *nicht*
automatisch zur Plattform-Fähigkeit, solange eine App es als Eigentum
trägt. Die Plattform ist Verbindung (Routing, Identität, Auth), nicht
Funktion.

Operative Ausformulierung: `conventions/apps.md` (Präfix APP).

## Anti-Goals

Kein Lernprodukt · kein Spielzeug · kein Datenhändler · kein
Überwachungstool · kein Wartungsaufwand · kein Engagement-Design für die
Familie (Dauerbenachrichtigung, Sucht-Schleifen, Aktivierungs-Funnel) ·
keine Bevormundung („wir wissen besser, was eine Familie braucht").

---

> **Quelle der Wahrheit für diese Prinzipien:** `xbuddy-knowledge/CONTEXT.md`.
> Diese Constitution ist die operative Kurzfassung neben den Specs — bei
> Änderungen in `CONTEXT.md` (§1, §4, §5) hier nachziehen.

Aufbau der Specs: `specs/README.md`.
