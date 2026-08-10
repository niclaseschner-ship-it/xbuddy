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

## Provenienz-Zeilen und `brainstorm/`-Pfade

Ältere Specs tragen `Quelle:`/`Provenanz:`-Zeilen mit Pfaden nach
`brainstorm/berater-runde/…` — das ist das **private Deliberations-Archiv**
dieses Projekts (Schwester-Repo, nicht Teil dieses Repos; siehe
`../decisions/README.md`, Zwei-Naturen-Modell). Diese Pfade lösen sich für
Außenstehende bewusst nicht auf: Die Entscheidung selbst ist durable in
`../decisions/` (RAT-Records) dokumentiert, der tote Pfad ist nur die
historische Evidenz-Spur (Dateiname = Datum + Status + Thema). **Für neue
Einträge gilt: nur der public Anker** — `Governance: decisions/RAT-<n>` —
der Deliberations-Link lebt ausschließlich im RAT-Record selbst.

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

### Test-Anker pro Requirement (Hebel 0)

Jede Requirement mit **Code-Verhalten** trägt zusätzlich entweder
- `Test-Anker: <test-id-oder-pfad>` — Verweis auf den automatisierten Test, der
  die Requirement prüft, **oder**
- `nicht_automatisiert: <grund> · manuelle_probe: <konkreter Befehl/Klick-Pfad>`
  — **nur** zulässig wenn das Verhalten nachweislich nicht codeförmig prüfbar
  ist (Externe Realwelt: Hardware-Audio, Telegram-Sandbox-Verhalten,
  Browser-Sensor-Permission, LE-Cert-Rotation).

```markdown
### HSP-2 — Plattform-Basis
Der Hörspiel-Buddy lebt unter `hoerspiel/` ... (Verhaltens-Text)
Test-Anker: hoerspiel/tests/test_album.py::test_hsp2_album_struktur

### KIBUDDY-12 — STT über OpenAI-API oder Azure-Whisper
... (Verhaltens-Text)
Test-Anker: kibuddy/tests/test_stt_adapter.py::test_kibuddy12_mock_whisper
nicht_automatisiert: echte Whisper-Latenz und Akzent-Toleranz — externer STT
manuelle_probe: KIBuddy-Display öffnen, Push-to-Talk halten, "Wie ist das Wetter?" sprechen, Transkript binnen 2s
```

**Doppel-Form erlaubt:** wenn ein Requirement sowohl eine mockbare Schicht
(Mock-Test) als auch eine nicht-automatisierbare Realwelt-Probe hat, dürfen beide
Anker nebeneinander stehen — schärft die Realität statt zu vereinfachen.

**Pure-Daten-Artefakte (keine Hebel-0-Requirements).** Asset-Pfade,
Konfig-Konstanten, View-/Registry-Einträge sind **keine Code-Verhalten-
Requirements** im Sinn dieser Regel. Sie fallen unter ihre konsumierende
Convention (URL-13, PANEL-3, ICONS-5 etc.), deren Form-Tests die
Existenz/Form-Korrektheit prüfen. Solche Requirements brauchen **keinen**
`Test-Anker:`- oder `nicht_automatisiert:`-Marker am Requirement selbst.

**Reject-Form (Form-Drift):**
- `nicht_automatisiert:` ohne `manuelle_probe:` — der Grund allein lässt
  „komplex" oder „später" durchgehen; die manuelle Probe zwingt zur konkreten
  Verifikation.
- `Test-Anker:` zeigt auf nicht-existenten Test — Anker rostet, falls
  Renaming/Umzug nicht nachgezogen wird; Watchdog grept periodisch.
- Code-Verhalten-Requirement ohne einen der beiden Marker — Form-Drift.

**Bestehende Sammel-Anker bleiben gültig.** Lokale Test-Anker-Sektionen wie
`### KIBUDDY-28 — Test-Anker` (Sammel-Sektion unter `## Tests`) sind weiterhin
zulässig als Spec-Wahl. Die Hebel-0-Form-Regel ist **additiv pro Requirement**,
nicht ersetzend.

Diese Klausel ist ratifiziert in
`brainstorm/berater-runde/2026-06-21-1620-RATIFIZIERT-werft-bauer-drift.md`
(Pfad B Schritt 2).

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

**Abschnittskontext schlägt Präfix.** `OPEN-*` ist die ID-Form für einen offenen
oder skizzierten Punkt (`conventions/identifiers.md` IDENT-3) — aber das Präfix
allein entscheidet nichts. Maßgeblich ist, *wo* der Eintrag steht:
- `OPEN-*` unter `## Offene Punkte`/`ENTWURF` → vorläufig.
- `OPEN-*` unter einer ratifizierten oder normalen Überschrift (z. B.
  `## Ratifizierte Entscheidungen`) → der zugehörige **Beschluss** ist ratifiziert
  (Provenienz). Das vollständige, bau-bindende Requirement entsteht aber erst,
  wenn der Inhalt als reguläre Requirement in einen normalen Abschnitt überführt
  ist.
- **Für den Prep:** Ein Ticket, das nur ein `OPEN-*` zitiert, ist *nicht*
  automatisch baufertig. Im Zweifel Nic fragen.

`E-*` (Entscheidungs-/Rationale-Eintrag, ID-Form `conventions/identifiers.md`
IDENT-4) ist **kein** Skizzen-Präfix wie `OPEN-*`:
Er hält die *Begründung* hinter einer Requirement fest und folgt der
Abschnitts-Regel — unter `## Entscheidungen` (oder anderer normaler Überschrift)
**bindend/ratifiziert**, unter `ENTWURF` vorläufig wie alles dort.

**Erledigte/entschiedene Einträge.** Es gibt kein Pflicht-Schlüsselwort für
Erledigung; in der Praxis stehen Marker wie `ENTSCHIEDEN <Datum>`, `ERLEDIGT
(#PR)` oder `abgeschlossen`. Ein erledigter Punkt **kann** beim nächsten Berühren
der Spec in eine reguläre Requirement überführt werden; bis dahin bleibt der
Eintrag mit seinem Erledigt-/Entscheidungs-Marker als Provenienz stehen.
Überführung ist Empfehlung, kein Automatismus.
