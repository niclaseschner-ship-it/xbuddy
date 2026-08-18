# RAT-50 — Test-Anker pro Requirement („Hebel 0"): eine Spec-Form-Regel statt einer vierten Kontrollschicht

**Status:** RATIFIZIERT 2026-06-21 (Nic, „langfristige Option" = Pfad B)
**Betrifft:** `specs/README.md`, Abschnitt „Test-Anker pro Requirement
(Hebel 0)" — gilt für **jede** Spec-Datei in diesem Repo
**Bezug:** die Spec-Form-Regeln daneben (stabile IDs, keine Umnummerierung);
`specs/buddies/kibuddy.md` (Sammel-Anker-Form, bleibt gültig)
**Ticket:** die auslösenden Tickets liegen im Prozess-Repo
(`xbuddy-prozess#42`, `#59`, `#64`) — **hier** steht nur der Teil, der eine
xbuddy-Spec-Regel geworden ist
**Entscheid-File:**
`brainstorm/berater-runde/2026-06-21-1620-RATIFIZIERT-werft-bauer-drift.md`
(Pfad B, Schritt 2)

## Problem

Wiederkehrender Befund über drei Vorgänge: **was ein Vorbereitungs-Schritt
nicht ausdrücklich benennt, vergisst der Bauende.** Der naheliegende Reflex war
eine weitere Pflichtsektion im Übergabe-Formular — die vierte mechanische
Schicht über demselben Problem.

Die Runde stellte die Frage anders: Wenn drei Kontrollschichten den Drift nicht
verhindert haben, warum sollte die vierte es tun? Der eigentliche Befund lag
eine Ebene tiefer — **die Spec selbst sagte nirgends, woran ein Requirement
geprüft wird.** Solange das fehlt, kann jede Übergabe formal vollständig sein
und die Prüfbarkeit trotzdem verloren gehen.

## Betrachtete Alternativen

- **Pfad A — Pflichtsektion sofort erzwingen** (drei Achsen im
  Übergabe-Formular, Hook-Mechanik dazu). Verworfen als *Premature Mechanism*:
  eine Mechanik ohne Empirie darüber, welche Achsen wirklich fehlen.
  Ehrlicher Gegenfall aus der Runde selbst: *„Pfad B kauft Empirie, aber der
  Drift schmerzt jetzt."* Die Replik war, dass die vorhandene Mechanik nur
  **ungenutzt**, nicht kaputt war.
- **Pfad B — gestuft** (erst die vorhandene Mechanik scharf benutzen, dann die
  Spec-Form-Regel, dann bei Trigger enger schneiden). Gewählt.
- **Für die Form-Regel selbst: nur `nicht_automatisiert: <grund>`** als
  Ausnahme-Marker (Antiberater-Minimalform). **Verschärft**, weil ein Grund
  allein „komplex" und „später" durchgehen lässt — daher zusätzlich
  `manuelle_probe:` mit konkretem Befehl oder Klick-Pfad als Pflicht.

## Wie entschieden

Ein Argument der ersten Fassung war schlicht **faktisch falsch** (die
Behauptung, alle Verzweigungen der bestehenden Mechanik seien binär) und wurde
vom Antiberater an Datei:Zeile widerlegt. Der Lean für Pfad B blieb trotzdem —
er stand auf zwei anderen Säulen (Premature Mechanism, Empirie vor
Generalisierung), nicht auf der widerlegten.

Für die Form-Regel wurde ein **Experiment vor der Ratifizierung** verlangt: sie
probeweise auf drei bestehende Requirements anwenden — eines mit vorhandenem
automatisiertem Test, eines klar nicht automatisierbar, eines Grenzfall. Kann
ein Reviewer eindeutig entscheiden? Wenn nein, fällt die Regel.

Der Trigger für die dritte Stufe wurde an eine **beobachtbare Markierung**
gebunden (ein Vorbereitungs-Lauf, der ein Mockup erzeugt und den Pfad dazu
setzt) plus ein Kalender-Datum als Rückfall — mit der ausdrücklichen Klausel:
läuft keiner der beiden an, gibt es eine **explizite Wiedervorlage**, kein
stilles Verfallen.

## Ergebnis — die Form-Regel in `specs/README.md`

Jedes Requirement mit **Code-Verhalten** trägt zusätzlich entweder

- `Test-Anker: <test-id-oder-pfad>` — Verweis auf den automatisierten Test, der
  es prüft, **oder**
- `nicht_automatisiert: <grund> · manuelle_probe: <konkreter Befehl/Klick-Pfad>`
  — zulässig **nur**, wenn das Verhalten nachweislich nicht codeförmig prüfbar
  ist (externe Realwelt: Hardware-Audio, Sandbox-Verhalten fremder Plattformen,
  Browser-Sensor-Berechtigungen, Zertifikats-Rotation).

Beide Marker stehen **am Requirement**, nicht in einer Sammel-Sektion. Drei
Formen sind ausdrücklich geregelt:

- **Doppel-Form erlaubt** — mockbare Schicht *und* Realwelt-Probe dürfen
  nebeneinander stehen; das schärft die Realität, statt sie zu vereinfachen.
- **Pure-Daten-Artefakte** (Asset-Pfade, Konfig-Konstanten, Registry-Einträge)
  sind **keine** Code-Verhalten-Requirements und brauchen keinen Marker — sie
  fallen unter die Form-Tests ihrer konsumierenden Konvention.
- **Bestehende Sammel-Anker bleiben gültig.** Die Regel ist additiv pro
  Requirement, nicht ersetzend.

**Reject-Formen:** `nicht_automatisiert:` ohne `manuelle_probe:`; ein
`Test-Anker:`, der auf einen nicht existierenden Test zeigt; ein
Code-Verhalten-Requirement ganz ohne Marker.

## Woran wir merken würden, dass es falsch war

- **Zu eng:** ein tatsächlich nicht automatisierbares Requirement wird
  fälschlich abgelehnt → Reviewer-Friktion. Das Drei-Requirements-Experiment
  war genau dagegen die Sicherung.
- **Zu weit:** `nicht_automatisiert:` etabliert sich als Standard-Ausweg. Genau
  deshalb ist `manuelle_probe:` Pflicht und nicht optional.
- **Anker rosten.** Ein `Test-Anker:` überlebt eine Umbenennung nicht von
  selbst. Die Runde sah dafür einen periodischen Grep vor — ohne den ist die
  Regel nach ein paar Monaten Dekoration.
- **Nicht hier entschieden:** die gestufte Vorbereitungs-Mechanik (Schritte 1
  und 3 der Runde) ist Prozess-Repo-Sache. Wer sie sucht, findet sie unter
  `xbuddy-prozess#42/#59/#64`, nicht in diesem Ledger.
