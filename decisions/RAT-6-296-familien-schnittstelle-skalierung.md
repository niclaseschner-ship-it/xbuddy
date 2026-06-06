# RAT-6 — Familien-Schnittstelle skalieren (#296): drei Eimer, Generik vertagt mit Trigger

- **Entschieden:** 2026-06-05 (Berater-Runde „Familien-Schnittstelle skalieren",
  Vorschlag + Antiberater/Codex), **ratifiziert** 2026-06-05 (Nic, vier Punkte +
  Verfeinerung). Landung als Record: 2026-06-06 (`/arbeitstag-prep`, #342).
- **Betrifft:** `conventions/apps.md` (APP-3/APP-4), `conventions/tasks.md`,
  `specs/buddies/plan.md` (E-PLAN-1, Routine-Module), `specs/buddies/routine.md`,
  `specs/platform/kalender-verbinden.md` (KAV-V1-Provisorium). Keystone **#296**;
  abgeleitete Tickets: **#341** (Kalender-FS-Write→Plan-API), **#343**
  (OPEN-ROUTINE-B, geblockt), **#340** (tasks.md-Hygiene).
- **Transkript (Evidenz):** `brainstorm/berater-runde/20260605-231748-RATIFIZIERT-familien-schnittstelle-skalierung.md`
  → Vorschlag `20260605-231209-vorschlag-familien-schnittstelle-skalierung.md`,
  Antiberater `2026-06-05-2313-antiberater-familien-schnittstelle-skalierung.md`.

## Beschluss

Buddy-Beiträge an die Familien-Schnittstelle werden **jetzt nicht generalisiert**.
Konsistent kopieren statt eine generische Mechanik bauen; die Generik wird **mit
Trigger vertagt**. Zur Sortierung gelten heute **drei Eimer**:

1. **CONFIG** (Werte synchron setzen) → künftig generischer schema-Skill.
   **Verfrüht:** 0 gebaute Config-Buddies, braucht zentralen Tool-Arg-Validator
   (`agent.py` validiert heute nicht), `strict:true`, Publish-Mechanismus (APP-4).
2. **AUSSEN-ZUGANG** (echte Protokoll-Abläufe: Google-OAuth, KI-API) →
   Plattform-Dienste. Der einzige **heutige** Bruch ist eng und konkret: KAV
   schreibt `kalender_id` direkt in `plan/plan.json` (Cross-Service-FS-Write,
   von der Spec selbst als V1-Provisorium markiert) → durch **Plan-API** ersetzen
   (#341). Eigentum bleibt Plan (E-PLAN-1), **nicht** re-litigieren; KAV bleibt
   der OAuth-Privatchat-Trigger, Plan importiert **keine** Telegram-Logik.
3. **PROZEDUR** (mehrstufiger SESS-Worker) → bleibt bespoke Copy + Konvention.
   Seit #264/SESS-5 ist SESS schon Lego (`_SESSION_SORTS`); der fachliche Ablauf
   ist genuin pro Beitrag verschieden. **Routine landet hier** und wird als Copy
   des `termin_eintragen`-Musters gebaut (#343).

### Nic-Verfeinerung — langfristig zwei, nicht drei
CONFIG und PROZEDUR sind **nicht trennscharf**: auch eine PROZEDUR sammelt im
Gespräch Felder und schreibt das Ergebnis — ein Feld vs. fünf ist ein **Gradient,
keine Kategorie**. Das langfristige Bau-Ziel sind **zwei** Klassen:
- **(A) SAMMELN-UND-SCHREIBEN** — eine **einheitliche** konversationelle Mechanik
  (Schema + fachliche Prüfung durch die Buddy-API + kontext-geführtes Nachfragen +
  Bestätigung). Deckt „einfache Config" UND die `termin_eintragen`-Klasse ab.
  Das ist Nics generische-Skill-Vision, vergrößert.
- **(B) EXTERNE-WELT-ZUGANG** — echte Protokoll-Abläufe (OAuth, KI-API) →
  Plattform-Dienste.

Die drei Eimer bleiben als **Sortier-Hilfe heute**; das **Bau-Ziel** ist (A) + (B).
„Copy-jetzt" ist die Brücke: Routine als `termin_eintragen`-Copy liefert den
**zweiten Datenpunkt**, an dem die einheitliche Mechanik (A) sauber entworfen wird.

## Warum

- **Kein belegter Generik-Bedarf:** 0 gebaute Config-Buddies; eine Mechanik jetzt
  wäre Vorratsarchitektur (CLAUDE.md §6). Break-even der einheitlichen Mechanik
  liegt beim 2.–3. Sammeln-und-Schreiben-Beitrag — Routine ist der zweite.
- **Generik-zu-früh ist der #298-Fehler in neuem Gewand:** Routine generisch zu
  bauen, obwohl sie genuin PROZEDUR ist, würde wieder einfangen wollen, was Ablauf
  ist (vgl. App-Installation Manifest+Factory NO-GO, #298).
- **Der Kalender-Cut ist eng:** kein „Eigentum entscheiden" (ist entschieden,
  E-PLAN-1), nur „V1-FS-Write durch Plan-API ersetzen".

## Re-Litigation / Reopen nur bei erfülltem Trigger

Vertagt **mit Trigger** — neu aufmachen nur, wenn belegt:
- **Einheitliche Sammeln-und-Schreiben-Mechanik (A):** ab dem 2.–3. echten
  Sammeln-und-Schreiben-Beitrag (Routine = der zweite Datenpunkt).
- **Generischer Config-Skill:** ab dem 3. echten flachen Config-Buddy. Davor das
  billige `python -c`-Harness-Experiment (Schema → Claude-Gather mit absichtlich
  kaputten Tool-Args, Fake-Provider) fahren, das belegt, ob ein generischer Skill
  ohne eigenen Validator trägt.
- **LLM-Gateway (Plattform-Dienst B):** ab KIBuddy (2. Konsument).
- **Kalender-Multi-Provider (Plattform-Dienst B):** ab belegtem Apple/CalDAV-Bedarf.

Sonst: bei jeder neu aufkommenden „bauen wir jetzt die generische Mechanik?"-Frage
hier prüfen und mit Verweis auf RAT-6 schließen.
