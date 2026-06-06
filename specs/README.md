# Specs

`specs/` ist die **Quelle der Wahrheit** für das Soll-Verhalten von XBuddy —
**lebende Specs**: Sie beschreiben, wie das System sich *heute* verhalten
soll, nicht was wann geändert wurde (das steht in Tickets/PRs).

## Die eine Regel

> **Verhalten ändern = Spec im selben PR ändern.**

Code und Spec wandern zusammen, im selben Branch, im selben Review. Mehr
braucht es nicht, um die Spec synchron zu halten.

## Aufbau

- `constitution.md` — übergeordnete Prinzipien, selten geändert.
- Eine Spec-Datei je **Fähigkeit mit eigenem Verhaltens-Vertrag** —
  `buddies/<name>.md` oder `platform/<name>.md` — Ordnerwahl nach APP-6
  (`conventions/apps.md`).
- `../conventions/` — paralleles Genre für das *Wie* (Bauregeln,
  einheitliche Form). Specs zitieren Konventions-IDs (z. B. „folgt
  IDENT-1"), beschreiben selbst kein „Wie".

<!-- Buddy-Spec — Gliederungs-Checkliste (optional, kein Pflichtrahmen)

   Eine Buddy-Spec ist vollständig, wenn sie View-Verhalten und Tests
   abdeckt. Die folgenden Punkte sind eine Checkliste zum Durchdenken —
   keine Pflichtüberschriften. Was nicht zutrifft, wird weggelassen;
   eine leere Sektion ist ein Fehler (CLAUDE.md §6: nichts auf Vorrat).

   - App & ihre Views: welche Display-Views existieren, Slug, URL-Schema
   - Datenhaltung: was die App besitzt, wo es liegt, welches Format
   - Schnittstellen Display: Routing-Einträge, URL-Parameter, Varianten
   - Schnittstellen API: HTTP-Endpunkte für andere Apps/Plattform
   - Konfiguration: Werte mit Default und Override-Pfad
   - Registrierung: Slug-Eintrag, Familien-Schnittstelle-Beitrag (APP-4)
-->

Gegliedert wird nach **Verhalten**, nicht nach Code-Modulen und nicht nach
Hardware. Eine Datei entsteht **erst**, wenn ein Ticket die Fähigkeit
berührt — nichts auf Vorrat.

## Eine Anforderung schreiben

Jede Anforderung hat eine **stabile ID** (Präfix + laufende Nummer) und einen
testbaren Satz — am besten im Wenn/Dann-Stil:

```markdown
# Kalender — Spec     (ID-Präfix: KAL)

### KAL-1 — Wochenansicht
Das System zeigt die Termine der laufenden Woche als Tagesspalten.

### KAL-2 — Heute hervorheben
Wenn der angezeigte Tag der heutige ist, hebt das System ihn farblich ab.
```

IDs werden nie neu vergeben und nie umnummeriert. Ein Ticket nennt die IDs,
die es umsetzt — das ist der Link zwischen Ticket, Spec und Code.

## Bindend vs. vorläufig

Specs mischen **beschlossene** Requirements mit **noch offenen** Punkten im
selben Dokument. Diese Regel sagt, was davon Bau-Auftrag ist.

**Default: bindend.** Jedes Requirement (eigene `##`- oder `###`-Überschrift mit
ID, oder Listen-Eintrag unter einer normalen Überschrift) ist verbindlich — egal
auf welcher Überschriften-Ebene. Eine Requirement als eigene `## ICONS-1`-
Überschrift ist genauso bindend wie eine unter `## 1. Die App`.

**Ausnahme: vorläufig — nur wenn markiert.** Ein Punkt ist *nicht* bindend, wenn
er entweder
- unter einer Überschrift `## Offene Punkte` steht, **oder**
- unter einer Überschrift mit dem Wort `ENTWURF` steht.

Nur diese beiden Marker entwerten. Fehlt der Marker, gilt der Default (bindend).

**Abschnittskontext schlägt Präfix.** `OPEN-*` ist die Namens-Konvention für
einen offenen oder skizzierten Punkt — aber das Präfix allein entscheidet nichts.
Maßgeblich ist, *wo* der Eintrag steht:
- `OPEN-*` unter `## Offene Punkte`/`ENTWURF` → vorläufig.
- `OPEN-*` unter einer ratifizierten oder normalen Überschrift (z. B.
  `## Ratifizierte Entscheidungen`) → der zugehörige **Beschluss** ist ratifiziert
  (Provenienz). Das vollständige, bau-bindende Requirement entsteht aber erst,
  wenn der Inhalt als reguläre Requirement in einen normalen Abschnitt überführt
  ist.
- **Für den Prep:** Ein Ticket, das nur ein `OPEN-*` zitiert, ist *nicht*
  automatisch baufertig. Im Zweifel Nic fragen.

`E-*` (Entscheidungs-/Rationale-Eintrag) ist **kein** Skizzen-Präfix wie `OPEN-*`:
Er hält die *Begründung* hinter einer Requirement fest und folgt der
Abschnitts-Regel — unter `## Entscheidungen` (oder anderer normaler Überschrift)
**bindend/ratifiziert**, unter `ENTWURF` vorläufig wie alles dort.

**Erledigte/entschiedene Einträge.** Es gibt kein Pflicht-Schlüsselwort für
Erledigung; in der Praxis stehen Marker wie `ENTSCHIEDEN <Datum>`, `ERLEDIGT
(#PR)` oder `abgeschlossen`. Ein erledigter Punkt **kann** beim nächsten Berühren
der Spec in eine reguläre Requirement überführt werden; bis dahin bleibt der
Eintrag mit seinem Erledigt-/Entscheidungs-Marker als Provenienz stehen.
Überführung ist Empfehlung, kein Automatismus.
