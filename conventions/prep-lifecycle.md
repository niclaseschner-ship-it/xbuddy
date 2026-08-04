# Prep-Lifecycle — Konvention     (ID-Präfix: PREP)

Wie ein Ticket im prep-Lebenszyklus (von `status:spec` über das Reife-Urteil bis
`status:ready`) **mechanisch** reift — nicht „der Skill denkt dran". Diese
Konvention verankert die PW-26-Ratifizierung (xbuddy-prozess#26, 2026-06-09) im
Code-Repo. Maschinell durchgesetzt durch `~/.claude/hooks/status_rollback_guard.py`;
Bauregeln hier, Implementations-Anker am Ende.

Diese Konvention setzt RECON-1/RECON-2/RECON-3 (`reconcile.md`) voraus — `main`-
Verriegelung, Spec-PR-Ausgang über `closes-guard`, Action-getriebener `status:*`-
Lebenszyklus. PREP regelt, **wie ein Ticket reif wird, bevor `status:ready`
gesetzt werden darf**; RECON regelt, **wie der Stempel mechanisch in den Lifecycle
greift**.

## PREP-1 — Spec-vor-Karte als Sequenz-Vorbedingung

Eine Stempel-Karte (Reife-Vorlage an Nic) existiert **nur**, wenn die zitierte
Requirement-ID bindend auf `origin/main` liegt. Es gibt keinen Pfad, in dem
ein Spec-PR-Merge an den Stempel gekoppelt ist („Falls Spec-PR: zuerst mergen,
dann Label" ist abgeschafft).

Drei Karten-Klassen existieren in der Karte-zu-Nic-Schicht (PREP-10 Form, PW-Karten-Form-Reform RATIFIZIERT 2026-06-21):

1. **Stempel-Karte** — Spec liegt auf `origin/main`. Nic stempelt oder lehnt.
   Aktion: `[stempeln]` `[parken]`.
2. **Wahl-Karte** — zwei Sub-Klassen, syntaktisch unterscheidbar via
   Header-Marker:
   - **🔱 ARCH-WAHL** — Architektur-Wahl (`architecture_class: wahl`). Nic
     wählt eine Variante VOR dem Spec-Merge; Skill mergt dann den Spec-PR mit
     der gewählten Variante; in der nächsten Charge erscheint die Stempel-
     Karte. Wahl-Karten produzieren **kein** `prep_verdict`-Comment
     (mechanische Unterscheidbarkeit gegen versehentlichen Stempel,
     PW-30-Hook-Sperre). Aktion: `[A]` `[B]` `[C]` `[halt: berater-runde]`.
   - **⚠️ KOORD-WAHL** — Koordinations-Wahl. Subsumiert zwei Bestands-Fälle:
     - **Cross-Spec-Koord** (PREP-6 Komponente 2): Spec-Pfad wird parallel von
       einem `status:in-progress`-Ticket konsumiert; Nic entscheidet Reihenfolge.
     - **Rollback-Koord** (PREP-7 nicht-triviale Variante): Folge-Merges
       berühren die Spec-Datei; Nic wählt zwischen Folge-Reverts und Vorwärts-
       Fix.
     Aktion: variantenabhängig (`[Reihenfolge OK]` `[umkehren]` `[parken]`
     bzw. `[a]` `[b]` `[parken]`).
3. **Schließen-Karte** — Ticket-Schluss-Vorlage: `dup` von #MM /
   `erledigt durch <commit>` / `überholt`. Stempel-artige Form, führt nach
   Nic-OK `gh issue close` aus (kein `status:*`-Labelwechsel — RECON-3
   bindet nur Status-Lifecycle, vgl. `reconcile.md:39-61` Geltungsbereich).
   Aktion: `[schließen]` `[parken]`. Karten-Form trägt einen Mini-Beleg
   (Grund + Anker auf duplizierendes Ticket / Commit).

Grund: drei dokumentierte Belegfälle am 2026-06-09 (Vormittag, Nachmittag,
Abend — drei verschiedene `/arbeitstag-prep`-Läufe, drei Nic-Korrekturen
„spec ist deine Aufgabe"), trotz expliziter „Pflicht-Klausel" im Skill-Text
seit dem Vormittag. PW-22-Wurzelbefund („Text-Pflicht trägt nicht") 1:1
angewandt: die Mechanik ist Sequenz-Vorbedingung, nicht weitere Disziplin.

## PREP-2 — `architecture_class` als Pflicht-Achse des prep_verdict

Der `xbuddy-watchdog-prep`-Agent setzt `architecture_class` für jedes Ticket
auf einen der zwei Werte:

- **`nachzeichnen`** — der Spec-Inhalt ist aus Constitution + RAT-Bestand
  ableitbar (Wortlaut-Schärfung, Mechanik-Klausel für WAS/WIE-Spalt, Refactor-
  Spec für gebauten Pfad, Drift-Fix gegen vorhandene Spec). Skill darf den
  Spec-PR autonom schreiben und mergen.
- **`wahl`** — Issue-Body trägt A/B-Optionen; OPEN-*-Spec ohne entscheidbaren
  Pfad; RAT-Konflikt-Verdacht; `eine_frage_an_nic` mit Architektur-Charakter;
  neuer Buddy/Schnittstelle; Privacy- oder Familien-Setup-Frage. Skill darf den
  Spec-PR **nicht** autonom mergen.

**Default bei Unsicherheit: `wahl`.** Codex-Bruch 2 (PW-26): autonomes
Mergen einer gewählten Variante wäre Vorgriff vor Nic-Ratifizierung
(`decisions/README.md` — Berater-Runde → Nic ratifiziert → DANN RAT + Spec-PR).
RAT-11-Disziplin („im Zweifel nie Richtung `spec-gemergt` raten") 1:1 hier
übertragen.

## PREP-3 — Strukturierte `reif_*`-Felder im prep_verdict

Achse REIF wird durch fünf flache Felder im YAML-Block des prep_verdict-Comments
getragen, **nicht** durch einen Freitext-`reif_evidence`-String:

```yaml
axes:
  reif: spec-gemergt | spec-fehlt | keine-spec-noetig
  reif_spec_path: "specs/<...>.md | conventions/<...>.md | null"
  reif_requirement_id: "<ID, z. B. ROU-15 oder SVC-5> | null"
  reif_definition_line: <int> | null
  reif_section_heading: "<wörtlich der Heading-String> | null"
  reif_binding: true | false | null
```

`specs/` und `conventions/` sind als `reif_spec_path` **gleichberechtigt** —
Requirements leben in beiden Genres (z. B. `SVC-5` in `conventions/services.md`,
`ROU-15` in `specs/buddies/routine.md`).

Grund: Codex-Bruch 1 (PW-26) — der naive `grep "<ID>"` ist RAT-11-widrig, weil
er den Abschnittskontext (`## Offene Punkte` / `ENTWURF` / `OPEN-*`-Präfix)
nicht prüft. Strukturierte Felder erlauben dem Hook die semantische Probe.

## PREP-4 — Zwei Sub-Klassen bei `keine-spec-noetig`

- **Drift-gegen-Spec**: Watchdog-Befund „Code weicht von bindender Spec ab"
  (z. B. `routine.py:142` bricht `ROU-15`). `reif_*`-Felder zeigen auf die
  gedriftete Spec-Stelle wie bei `spec-gemergt`; zusätzlich Pflicht-Feld
  `drift_target` mit Datei:Zeile der Code-Drift. Stempel-Karte zeigt eine
  DRIFT-Zeile zusätzlich zum SPEC-DIFF.

- **Reines Chore** (Dead-Code, Format, Type-Hint): keine Spec-ID zitierbar.
  `reif_*`-Felder bleiben `null`; stattdessen Pflicht-Feld `chore_evidence`
  mit Datei:Zeile + Convention/CLAUDE.md-Verweis (z. B. `routine.py:88
  ungenutzter _legacy_handler — CLAUDE.md §6 'Kein toter Code'`). Hook prüft,
  dass die Datei auf `origin/main` existiert.

Beides ist Stempel-fähig ohne Spec-PR. Sind beide Felder gefüllt, ist das
ein Verdikt-Bug — Hook deniert.

## PREP-5 — `verdict_repo_sha` immutable, `stamp_repo_sha` separat

`verdict_repo_sha` wird vom `xbuddy-watchdog-prep`-Agent im Prep-Moment gesetzt
(`git rev-parse origin/main`) und ist **immutable**. Der Skill darf den Wert
beim Stempeln **nicht** ersetzen. Für den Stempel-Moment existiert ein zweites
Feld `stamp_repo_sha` (vom Skill gesetzt) — semantisch getrennt.

Hash-Marker (`<!-- prep_verdict v1 issue:NR sha:HASH -->`) umfasst bei
PW-26-Schema (`architecture_class:` im Verdikt-Body) zusätzlich
`verdict_repo_sha` und `architecture_class`:

- **PW-26-Schema**: `sha256(json({verdict, axes, verdict_repo_sha,
  architecture_class}, sort_keys=True))[:16]`.
- **Legacy PW-30-Schema** (vor PW-26): `sha256(json({verdict, axes},
  sort_keys=True))[:16]`. Bestand-kompatibel.

Grund: Codex-Bruch 4 (PW-26) — vor PW-26 deckte der Hash nur `{verdict, axes}`,
sodass ein altes Verdikt mit frischem `verdict_repo_sha` „gewaschen" werden
konnte. Mit dem erweiterten Hash invalidiert jeder SHA-Tausch den Marker
mechanisch.

## PREP-6 — Hook-Sperren beim Stempel und beim Spec-PR-Merge

`~/.claude/hooks/status_rollback_guard.py` implementiert vier Sperren:

1. **Beim `gh issue edit … --add-label status:ready`** (Stempel oder
   prep-Release-forward):
   - prep_verdict-Comment am Ticket Pflicht (PW-30, `VERDICT_MARKER_RE`).
   - Hash-Probe: Marker-SHA muss zum Body passen (PREP-5).
   - Drift-Probe: `specs/`/`decisions/` zwischen `verdict_repo_sha` und
     aktuellem `origin/main` müssen unverändert sein.
   - Spec-Binding-Probe (`check_spec_binding`): semantisch über die fünf
     `reif_*`-Felder + Heading-Negativfilter (`## Offene Punkte` / `ENTWURF` /
     `OPEN-*`) + `git show <verdict_repo_sha>:<reif_spec_path>`-Existenzprobe
     der Requirement-ID. Bei `keine-spec-noetig` mit `chore_evidence`:
     Datei-Existenz auf `verdict_repo_sha`.

2. **Beim `gh pr merge` auf einem `spec/<nr>-…`-Branch**:
   - `architecture_class: wahl` ohne `arch_choice`-Marker am Issue
     (`<!-- arch_choice v1 issue:<nr> choice:A -->`) → deny. Codex-Bruch 2.
   - Cross-Spec-Probe (`check_spec_path_exclusive`): einer der PR-Pfade wird
     als `reif_spec_path` in einem anderen offenen `status:in-progress`-Ticket
     zitiert → deny mit Hinweis auf das konfligierende Ticket. Codex-Bruch 3.

3. **Bei `gh issue edit … --add-label status:spec-in-progress`** (prep-Claim,
   PW-33): Skip-Marker-Pflicht. Nur dieser Übergang ist via Skip erlaubt.

4. **Bei `gh issue edit … --remove-label status:spec-in-progress
   --add-label status:spec`** (prep-Release-back): Skip-Marker-Pflicht.

Andere `status:*`-Mutationen per Shell sind durch RECON-3 ohnehin verboten —
der Hook deniert sie unabhängig vom Skip-Marker, weil die parsierten
Label-Mutationen nicht den vier dokumentierten Pfaden entsprechen.

## PREP-7 — Rollback-Pfad bei autonom gemergter Fehl-Spec

Sagt Nic beim Stempel `zurück: Spec falsch` (Fehler in einer vom Skill autonom
gemergten Spec, `nachzeichnen`-Klasse), läuft der Rollback in zwei Pfaden:

- **Trivial** (keine Folge-Merges auf der betroffenen Spec-Datei zwischen
  `spec_merge_sha` und `origin/main`): `git revert -m 1 <spec_merge_sha>` als
  neuer Spec-PR (`Refs #<nr>`, Label `type:docs` falls `conventions/`),
  closes-guard greift über den Spec-Ausgang. Label zurück auf `status:spec`
  per dokumentiertem Skip-Pfad.

- **Nicht trivial** (Folge-Merges berühren die Spec-Datei): Skill produziert
  `rollback-koord`-Karte; Nic wählt zwischen Folge-Reverts und Vorwärts-Fix.
  Skill landet keinen der zwei autonom — diese Klasse ist Architektur-Wahl,
  die nicht aus RAT ableitbar ist.

Beim Rollback wird zusätzlich ein Comment am Issue gepostet (durabler Mess-
Anker für die Reopen-Probe):

```
<!-- prep_rollback v1 issue:<nr> spec_pr:<x> rollback_pr:<y> reason:"<text>" -->
```

## PREP-8 — `conventions/`-Touch ist konservativ in `wahl`

Spec-PRs, die `conventions/`-Dateien ändern, fallen per Default in
`architecture_class: wahl` — auch wenn der Inhalt klein wirkt. Grund: eine
Konvention bindet quer mehrere Komponenten; ein autonomer Merge ohne Nic-
Wahl kann Cross-Spec-Drift in `status:in-progress`-Tickets erzeugen, bevor
der Watchdog dort eingreifen würde.

Ausnahme: Verdikt trägt `convention_low_blast_radius: true` (z. B. reine
Wortlaut-Schärfung an einer Klausel, die in keinem offenen Ticket zitiert
wird). Empirisch zu prüfen, nicht Heuristik.

## PREP-9 — Reopen-Bedingungen für diese Konvention

Die PW-26-Mechanik wird **nicht** stillschweigend erweitert. Reopen-Trigger
(als neue `/berater-runde`-Anlass):

1. **Klassifikator-False-`nachzeichnen`**: autonom gemergter Spec war
   Architektur-Wahl ohne Nic-Wort → Trigger-Liste enger ziehen.
2. **Rollback-Quote >20%** in 14 Tagen ab Ratifizierung (Mess-Skript
   xbuddy-prozess#34) → Vor-Validierungs-Stufe vor autonomem Merge erwägen.
3. **`conventions/`-Touch-Vorfall** ohne explizite
   `convention_low_blast_radius`-Markierung → PREP-8 verschärfen.
4. **Karten-Form-Welle-2-Schwellen reißen** (PREP-11 Welle-1-Beobachtung,
   gemessen via xbuddy-prozess#69): `preflight_missing > 10%`, **oder**
   `over_14_lines > 20%`, **oder** `followup_pain ≥ 62%` (alte Baseline aus
   29-Sample-Messung 2026-06-21) → neue `/berater-runde` entscheidet zwischen
   mechanischem Hook und Pre-Flight-Form-Überarbeitung (siehe PREP-11
   Welle-2-Ausgang). **Ausgesetzt bei `rendered_card_total = 0`** (PW-86-RATIFIZIERT
   2026-07-06): läuft ein Prep-Lauf rein über Koordinations-Override (keine
   HTML-Karte gerendert), ist der leere Form-Nenner kein Qualitäts-Signal — der
   Schwellen-Riss ist dann ein Mess-Artefakt, kein berater-runden-Auslöser.

## PREP-10 — Karten-Form v5 (Pflicht-Felder, Ampel-Stempel)

**Geltung:** Karten, die `/arbeitstag-prep` rendert. Andere Skills
(`/arbeitstag`, `/werft`) übernehmen PREP-10/11 erst nach **eigener**
Ratifikation mit Belegfall (Verbot vorzeitiger Generalisierung — Memory
`feedback_berater_zwei_gebaute_beispiele`, RAT-7 Skill-Convention-Defer).


Karten zu Nic sind kurz und ampel-first. Pflicht-Felder pro Klasse (Templates
und Beispiele im Skill `~/.claude/commands/arbeitstag-prep.md`):

**Stempel-Karte** (~9 Substanz-Zeilen):
- `TREIBER` (Quelle + Befund, kanonische Form unten)
- `EMPFEHLUNG` (ein Wort: `stempeln`)
- `RISIKO` (Ampel + Wort + Schaden × Wahrscheinlichkeit)
- `VERTRAUTHEIT` (Ampel + Wort, Begründung mit `n=…` bei LEGO)
- `WIRKUNG` (ein Satz)
- `KONTEXT` (ein Satz)
- Aktions-Zeile + `Belege:` (Datei:Zeile-Anker, max 3)

**Wahl-Karte** (~9 Substanz-Zeilen):
- `TREIBER`, `EMPFEHLUNG` (ein Wort: `A` / `B` / `C`)
- `KERNFRAGE` (ein Satz)
- 2–3 Varianten als Halbsätze: `<Kurzname>  <Mechanik> — <Trade-Off>`
  Empfohlene Variante mit `← empfohlen` markiert
- Aktions-Zeile

**Schließen-Karte** (~5 Substanz-Zeilen):
- `TREIBER`, `EMPFEHLUNG` (`schließen — <Grund>`)
- `WIRKUNG` (warum kein Bau nötig)
- Aktions-Zeile + `Belege:` (RECON-3-Anker: `#MM`-PR oder commit-sha)

### Ampel-Stempel

**Risiko** (Schaden × Wahrscheinlichkeit):

| Stempel | Schaden × Wahrscheinlichkeit |
|---|---|
| 🟢 niedrig | klein · selten |
| 🟡 mittel | klein · oft  ODER  groß · selten |
| 🟠 hoch | groß · oft  ODER  irreversibel · selten |
| 🔴 kritisch | irreversibel · oft — Empfehlung `stempeln` verboten, wird zur WAHL-Karte (machen-mit-Mitigation vs. nicht) |

**Vertrautheit**:

| Stempel | Bedeutung |
|---|---|
| 🟢 LEGO | Sorte existiert n≥2, Convention trägt |
| 🟡 NEU-MISCHUNG | bekannte Stücke neu komponiert |
| 🟠 EXPERIMENT | neue Mechanik, brauchen Probe |
| 🔴 OFFEN | wir wissen nicht wie — /berater-runde nötig |

**Schwellen xbuddy-konkret:**
- „irreversibel" = Daten-Verlust ohne Backup.
- „oft" = ≥1× pro Familien-Tag.
- „selten" = ≤1× pro Familien-Woche.

### TREIBER-Form (kanonische Quellen)

- `Nic <Datum>: <Stichwort>`
- `Watchdog Linse-<N> (<Linsen-Name>): <Befund>`
- `Werft #<idee>: <Stichwort>`
- `Live-Bug #<nr> (<Kanal>): <Beobachtung>`
- `Lego-Offensive: <Sorte> n=<N> erreicht`
- `Folge aus #<vorigem-Ticket>: <Stichwort>`

### Sprachregel Wahl-Karte

Trade-Off in Freitext, **Konsequenz statt Mechanik**. Keine Spec-IDs im
Variante-Text (nur in Belegen). Form: „wird teuer ab 3. Buddy", nicht
„ROU-34 zeigt auf ROU-12".

Grund: Roh-Daten-Analyse 2026-06-21 (1075+263 Nic-Inputs ausgewertet, 62%
Folge-Schmerz im 29-Sample der kurzen Stempel-Bestätigungen). Alte
Karten-Form (33 Zeilen, SPEC-DIFF inline, EMPFEHLUNG in Zeile 20+)
produzierte blindes „ok" mit nachfolgender Korrektur. v5 macht die
Entscheidungsachsen in den ersten drei Zeilen sichtbar.

### Render-Medium der v5-Karten (Chat ODER HTML-Browser-Loop)

Die v5-**Felder** (TREIBER/EMPFEHLUNG/RISIKO/VERTRAUTHEIT/WIRKUNG/KONTEXT +
Ampel-Stempel) sind **medien-agnostisch**: sie definieren *was* eine Karte
trägt, nicht *wo* sie erscheint. Der PREP-10-Feld-Vertrag bleibt davon
**unberührt** — er gilt unverändert in jedem Render-Medium.
(ENTSCHEID-File Paket-Sektion „Konvergiert" → HTML ist Render-Medium über den
v5-Feldern; PREP-10 unberührt)

Zulässige Render-Medien:

- **Chat** (Default unter der Schwelle): Karten als Text im Nic-Block, einzeln.
- **HTML-Browser-Karten-Loop** (DEFAULT **ab N≥7 Karten** pro Prep-Lauf): ein
  ephemeres Operator-Tool rendert den Stapel als Browser-Karten; Nic gibt pro
  Karte ein explizites Verdikt (Radio). Mechanik in `arbeitstag-prep.md`.
  (ENTSCHEID-File Paket-Sektion „Zweit-Gabel" → gethresholdeter Default ab N≥7;
  darunter Chat-Default)

Die Schwelle ist gethresholdet, weil der belegte Nutzen aus großen Stapeln
kommt (30+-Karten-Läufe); für kleine Stapel kämen Server/Port/Browser ohne
Beleg dazu (gegen Einfachheit, `constitution.md`). Unterhalb N≥7 ist Chat der
Default; der HTML-Weg ist dort allenfalls Nic-Wahl pro Lauf.

**Pflicht im HTML-Modus — Vollständigkeit:** Das HTML-Template rendert **ALLE**
Karten-Klassen (Stempel, Wahl 🔱 ARCH-WAHL / ⚠️ KOORD-WAHL, Schließen) inkl.
**Stempel-Ampel** (Risiko + Vertrautheit, beide Achsen sichtbar). Eine
Render-Form, die eine Klasse oder die Ampel unterschlägt, ist nicht zulässig —
sie würde die in den ersten drei Zeilen sichtbaren Entscheidungsachsen, die der
Sinn von v5 sind, gerade im neuen Medium verlieren.
(ENTSCHEID-File Paket-Sektion „Konvergiert" → Template rendert ALLE
Karten-Klassen inkl. Stempel-Ampel + grüner Render-Test)

**Mess-Naht im HTML-Modus (Pflicht):** Das Mess-Skript
`tools/card_form_quote.py` liest Issue-Body + Comments (PREP-11
„Mess-Pflicht"). Rendert der Loop die Karten nur im Browser, fehlen dem Skript
der `card_pre_flight v1`-Marker (→ `preflight_missing`-False-Positive), der
Karten-Header + Aktionszeile (→ `over_14_lines` misst nichts) und Nics
Antwort (→ leeres `followup_pain`-Fenster). Deshalb postet der Skill im
HTML-Modus **pro Karte einen durablen Issue-Comment** in der vom Skript
gelesenen **Form**: erste Zeile der `card_pre_flight v1`-Marker, darunter die
textuelle Karte mit `#<nr>`-Header und `→ [Aktion]`-Zeile. `followup_pain`
misst die **späteren Korrektur-Comments nach** dem Marker (Folge-Schmerz auf
Stempel-Karten), **nicht** Nics Submit-Verdikt selbst — Marker und Verdikt
dürfen nicht in einem Comment kollabieren. So messen alle drei Metriken
(`preflight_missing` / `over_14_lines` / `followup_pain`) korrekt und ein
Audit-Trail entsteht. Der Browser ist die Anzeige, der Issue-Comment bleibt
die durable Wahrheit (SSoT = GitHub-Issue, unverändert).
(ENTSCHEID-File Paket-Sektion „Konvergiert" → HTML-Modus postet pro Karte einen
durablen Issue-Comment → card_form_quote misst alle drei Metriken korrekt)

## PREP-11 — „Karte zu Nic ist FERTIG" + Pre-Flight-Disziplin

### FERTIG-Disziplin (Erweiterung von PREP-1)

Karten zu Nic enthalten **keine** Action `[zurück: was fehlt]`. Wäre eine
Karte zurückzuschicken (Spec dünn, Substanz nicht da, Belege fehlen), geht
sie **gar nicht** zu Nic — der Skill schärft im Koord-Block nach:

- bei `architecture_class: nachzeichnen`: Spec-PR autonom schreiben (siehe
  PW-26-Pfad in `arbeitstag-prep.md` Koord-Block),
- bei dünner Substanz: zweite Charge mit gefülltem Verdikt,
- bei fehlenden Belegen: Bestands-Grep + Anker holen.

Der Nic-Block kennt nur die drei in PREP-1 genannten Karten-Klassen, jede
mit klarer Aktion ohne Rückspiel.

### Pre-Flight-Block (Schreib-Reflex am Issue)

Vor jeder Karte rendert der Skill einen HTML-Kommentar als
Selbstreflexion am Issue:

```
<!-- card_pre_flight v1 issue:<nr> kind:stempel|wahl|schliessen -->
- [x] Spec liegt auf main (origin/main:<sha>)                                  [stempel]
- [x] Bestand-Grep gemacht — keine offene Karte zum gleichen Thema
- [x] RAT/Memory durchgesehen — keine ratifizierte Klausel wird übergangen
- [x] Risiko in zwei Achsen einzeln bewertet, dann Gesamtnote                  [stempel]
- [x] Vertrautheit bewertet (bei LEGO: Geschwister gezählt n=…)                [stempel]
- [x] Empfehlung folgt aus den Achsen, keine Improvisation
- [x] Karte ist FERTIG — kein „zurück" implizit
- [x] Jede Variante ist baubar (eigener Spec-Pfad denkbar)                     [wahl]
- [x] Trade-Off pro Variante in einfachen Worten (Konsequenz, kein ID-Jargon)  [wahl]
<!-- /card_pre_flight -->
```

### Welle 1 ohne mechanischen Hook (befristet)

Pre-Flight-Block ist heute Schreib-Reflex des Skills, **kein** Hook-Check.
Das weicht bewusst von der „mechanisch, nicht 'Skill denkt dran'"-Auslegung
oben ab (Nic-Setzung 2026-06-21: „Disziplin appellieren statt mechanisch
prüfen"). Befristet, weil:

- Die Karten-Form-Welle erzwingt selbst Selbstreflexion (kurze Karten,
  TREIBER mit konkretem Befund, Ampel-Bewertung — wenn das gemacht wird,
  ist die Disziplin Folge der Arbeit).
- Die Bestands-Hooks (PW-26 Spec-Binding bei Stempel,
  `check_spec_path_exclusive` beim Spec-Merge) bleiben unverändert scharf —
  der mechanische Boden ist nicht ausgehebelt.

### Mess-Pflicht in Welle 1

Mess-Skript `tools/card_form_quote.py` (xbuddy-prozess#69) zählt pro
Prep-Lauf:

- `preflight_missing` — Karten ohne `card_pre_flight v1`-Marker
- `over_14_lines` — Karten > 14 Zeilen
- `followup_pain` — Folge-Korrektur-Rate auf Stempel-Karten (gleiche
  Methodik wie die 18/29-Sample-Messung 2026-06-21)

Output: einzeilige Bilanz, von /arbeitstag-prep am Ende jeder Retro
abrufbar (`cards=N preflight_missing=X over_14_lines=Y followup_pain=Z%`).

**Getrennte Nenner** (PW-86-RATIFIZIERT 2026-07-06, `brainstorm/berater-runde/20260706-154616-RATIFIZIERT-pw86-prep11-messnaht.md` Paket-Sektion „Die gedrehte Form"): Der bisherige gemeinsame Nenner (alle `status:ready`-Tickets im Fenster) verdünnt die **Form**-Metriken bis zur Bedeutungslosigkeit — Tickets, die **ohne Karten-Render** ready wurden (Werft-Stempel mit `werft_verdict`, Koordinations-Override mit direktem `prep_verdict`), haben nie eine gerenderte Karte und dürfen die Kartenform nicht mitzählen (Bug-Beleg 2026-07-06: 0 gerenderte Karten unter 16 ready-Tickets → Formmetriken maßen Rauschen). Daher:
- `rendered_card_total` = im Prep-Lauf zu Nic gerenderte Karten (getragen vom `card_pre_flight v1`-Marker). **`over_14_lines` und `followup_pain`** messen die Qualität *dieser* Karten und teilen durch `rendered_card_total`; `followup_pain` zählt nur auf Karten mit `card_pre_flight`.
- **`preflight_missing` bleibt semantisch unverändert** (Karten *ohne* `card_pre_flight` — ratifiziert: entdünnen, nicht abschalten). Es darf **nicht** über `rendered_card_total` laufen (Zähler und Nenner wären disjunkt → strukturell 0, der Trigger-4-Falsifikator stürbe still). Sein Fehlalarm im reinen Override-Betrieb wird stattdessen über die **Trigger-4-Aussetzung bei `rendered_card_total = 0`** gefangen. **Offen (Bau xbuddy#1359):** ein Nenner, der marker-lose *gerenderte* Karten von nie-gerenderten Nicht-Kartenpfad-Tickets trennt — der Marker allein kann beide nicht unterscheiden; die Nenner-Regel für `preflight_missing` im Misch-Lauf klärt das Bau-Ticket empirisch. (Bau: xbuddy#1359.)

- `gate_provenance_missing` — **neue Audit-/Canary-Metrik, kein PREP-11-Form-Ersatz**: offene `status:ready`-Tickets ohne `card_pre_flight` **oder** `prep_verdict` **oder** `werft_verdict` (Nenner `ready_total`). Sie ist der Observability-Zwilling zu RECON-3s Create-Kanten-Guard (`prep-reconcile.yml`, PW-85): `> 0` heißt, ein Ticket erreichte die Bau-Membran **ohne** Gate-Provenienz — ein Guard-/UI-Bypass-Fund, keine Kartenform-Aussage. Erwartung bei aktivem Guard: `= 0`. (Bau: xbuddy#1359.)

### Welle-2-Auslöser (Hook ODER Form-Überarbeitung)

Nach 7 Tagen oder ~50 Karten ab Skill-Edit-Landung, falls **eine** der
Schwellen reißt:

- `preflight_missing > 10%`, **oder**
- `over_14_lines > 20%`, **oder**
- `followup_pain ≥ 62%` (alte Baseline aus 29-Sample-Messung 2026-06-21).

→ Welle 2 hat **zwei** legitime Ausgänge — die Entscheidung trifft eine
neue `/berater-runde` anhand der gerissenen Schwelle:

- **mechanischer Hook** (`card_form_guard.py` o. ä.) prüft Form-Regeln vor
  jedem Karten-Render — Standardpfad, wenn `preflight_missing` reißt
  (Disziplin schleift) oder `over_14_lines` reißt (Form-Disziplin schleift).
- **Pre-Flight-Form-Überarbeitung** — wenn `followup_pain` trotz erfüllter
  Form reißt, ist die Pre-Flight-Checkliste selbst nicht trennscharf genug
  (Hook am falschen Ort). Dann Form schärfen, Hook nicht ziehen.

Wortlaut-Schärfung beider Pfade in der nächsten Runde, wenn Welle 2 ansteht.

### Mess-Ausfall-Pfad

Solange `tools/card_form_quote.py` (xbuddy-prozess#69) noch nicht
gelandet ist, schreibt der `/arbeitstag-prep`-Retro die Bilanz-Zeile als
`measurement_unavailable`. Die 7-Tage/~50-Karten-Uhr für Welle 2 startet
erst mit der **ersten messbaren Bilanz** — nicht mit dem Skill-Edit-Merge.
So kann die Reform nicht „stillschweigend laufen" ohne Falsifikator.

## PREP-12 — Maturation-Berater-Mechanik (Antiberater-Floor)

**Geltung:** prep-interne Berater-Läufe — die Reifung eines Tickets bis
Stempelreife im Koordinations-Block (Wahl-Reifung, OPEN-*-Auflösung,
Nachschärfung nach `halt: berater-runde`). NICHT die eigenständige
`/berater-runde` auf Nic-Anlass — die behält ihre eigene Mechanik.

### Kodifizierte Mechanik statt improvisierter Direkt-Spawns

Jeder Maturation-Berater-Lauf fährt die **benannten** Teile der
berater-runde-Mechanik — und nur diese:

- **Subagent-Header** (`contract_kind`-Block + `mode:`, PW-31-konform),
- **R1-Lese-Disziplin** (Bestandskarte vor Lösungs-Vokabular),
- **BRICHT/RISKANT-Semantik** für Antiberater-Funde,
- **Runden-Deckel** (kein unbegrenztes Pingpong).

**KEINE automatische ENTSCHEID-/RAT-Landung pro Fund** — die gibt es nur bei
echter Architektur-Entscheidung. Improvisierte Direkt-Spawns (Berater „mal
eben" ohne Header/Deckel) sind abgeschafft.
(ENTSCHEID pw84-antiberater-pflicht-prep, Sektion „Entscheidung — MACH ES" →
keine improvisierten Direkt-Spawns; Sektion „Was sich ändert / Trade-off" →
benannte berater-runde-Teile, Codex-RISKANT-2 gepatcht — keine automatische
ENTSCHEID-/RAT-Landung für jeden Fund)

### Antiberater-Floor (Pflicht in JEDER Runde)

Ein **Codex-Sanity-Pass läuft in JEDER Maturation-Berater-Runde** — nie mehr
optional. Der Codex-Aufruf trägt immer eine **Crawl-Schranke** (explizite
Anker-Liste + max N Calls, sonst Repo-Crawl-Timeout). Läuft stattdessen der
Opus-Fallback, wird er **als schwächer gekennzeichnet** (gleiche
Modell-Familie, Echo-Risiko).
(ENTSCHEID pw84-antiberater-pflicht-prep, Sektion „Entscheidung — MACH ES" →
Codex-Sanity-Pass in JEDER Maturation-Berater-Runde; Sektion „Was sich ändert /
Trade-off" → Crawl-Schranke Pflicht, Opus-Fallback als schwächer kennzeichnen)

### Eskalation auf Voll-Pingpong (konditional, nicht Default)

Das teure Voll-Pingpong (mehrere Berater↔Antiberater-Iterationen) nur bei:

- **(a)** der Berater-Entwurf öffnet eine ratifizierte Entscheidung neu,
- **(b)** eine neue Spec-ID wird geprägt,
- **(c)** prep-Risiko-Ampel 🔴 ODER `architecture_class: wahl` mit
  irreversibler Bewertung.

(ENTSCHEID pw84-antiberater-pflicht-prep, Sektion „Was sich ändert /
Trade-off" → Eskalation nur bei (a)–(c); Codex-BRICHT-3 gepatcht —
`risk_class` ist arbeitstag-Vokabular, prep hat es nicht)

### Mess-Pflicht in Welle 1 (befristet)

Pro Maturation-Lauf postet der Skill einen durablen Marker als Issue-Comment
oder Retro-Zeile:

```
antiberater_sanity: ran|skipped · engine: codex|opus-fallback · finding: none|riskant|bricht · latency_sec: <n>
```

Ohne Messspur ist das Kill-Kriterium nicht auswertbar.
(ENTSCHEID pw84-antiberater-pflicht-prep, Sektion „Was sich ändert /
Trade-off" → Messspur pro Maturation-Lauf, Codex-BRICHT-2 gepatcht)

### Kill-Kriterium (Welle-1-Ausgang)

Nach 6 GEMESSENEN Maturation-Läufen: 0× BRICHT und 0× substanzielles RISKANT
bei klar störender Latenz → Floor zurück auf die konditionalen Trigger
(a)–(c) (Revert der Klausel-Zeile).
(ENTSCHEID pw84-antiberater-pflicht-prep, Sektion „Kill-Kriterium" → 6
gemessene Läufe, 0× BRICHT und 0× substanzielles RISKANT)

### Ehrlichkeit zur Datenlage

Der Beleg ist EIN korrelierter Lauf (Maturation-Strecke 2026-07-03→05: 3 von
4 über-reichte Berater-Entwürfe ohne Gegenkopf; n=1–2 unabhängig). Deshalb
ist der Floor eine befristete Welle-1-Regel mit Messspur — **kein Hook**.
(ENTSCHEID pw84-antiberater-pflicht-prep, Sektion „Was sich ändert /
Trade-off" → Ehrlichkeit zur Datenlage, n=1–2)

## Warum tool-erzwungen statt Prosa

Vor PW-26 lebte die Spec-PR-Pflicht im Koord-Block als „Pflicht, nicht
Optional"-Klausel im Skill-Text (`arbeitstag-prep.md` Z. 55 ab 2026-06-09).
Trotzdem fiel sie am selben Tag dreimal durch — n=3 dokumentierte Belegfälle
zeigen, dass Text-Pflicht unter Last übersprungen wird, auch nach mehreren
Memory-Updates und Skill-Edits. Die `status_rollback_guard.py`-Hook-Sperre
ist der mechanische Ersatz: ohne grüne Probe kein Stempel, ohne grüne
Cross-Spec/Wahl-Probe kein Spec-Merge.

## Implementations-Anker

Die Konvention beschreibt die Bauregel; die Implementation lebt im
Skill-Harness — SSoT im public Repo `lotse` (`~/repos/lotse`, RAT-23 Stufe 2),
Laufzeit-Deploy-Ziel `~/.claude/`:

- `lotse/commands/arbeitstag-prep.md` (deployt nach
  `~/.claude/commands/arbeitstag-prep.md`) — Skill-Sequenz, Karten-Render,
  Maturation-Berater-Mechanik (PREP-12)
- `lotse/agents/watchdog-prep.md` (deployt nach `~/.claude/agents/`)
  — Verdikt-Schema (PREP-2/3/4/5)
- `lotse/hooks/status_rollback_guard.py` (deployt nach `~/.claude/hooks/`)
  — vier Hook-Sperren (PREP-6)

Spur:

- PW-26 RATIFIZIERT: `brainstorm/berater-runde/20260609-195710-RATIFIZIERT-pw26-spec-vor-karte.md`
- xbuddy-prozess#26 — Original-Ticket
- xbuddy-prozess#33 — RECON-3-1 Skip-Pfad-Klarstellung (Folge-Ticket, vertagt)
- xbuddy-prozess#34 — Mess-Skript für Rollback-Quote (Folge-Ticket, vertagt)
- Karten-Form-Reform RATIFIZIERT 2026-06-21: `brainstorm/berater-runde/20260621-1700-RATIFIZIERT-karten-form-reform-prep.md` — PREP-10 + PREP-11 + Erweiterung PREP-1 um KOORD-WAHL + Schließen-Karte
- xbuddy-prozess#69 — Mess-Skript `tools/card_form_quote.py` (Welle-1-Beobachtung)
- PW-84 Antiberater-Floor RATIFIZIERT 2026-07-05: `brainstorm/berater-runde/20260705-2145-RATIFIZIERT-pw84-antiberater-pflicht-prep.md` — PREP-12 Maturation-Berater-Mechanik (xbuddy-prozess#84)
