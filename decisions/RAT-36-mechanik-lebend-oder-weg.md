# RAT-36 — Mechanik: lebend oder weg (einmaliger Rückbau-Pass)

- **Entschieden:** 2026-08-13 (Berater-Runde „Mechanik: lebend oder weg", Berater
  R1 `mode: read` → Nic-Gabelwahl → Berater `mode: propose` → **Codex**-Antiberater
  (2 BRICHT, 2 RISKANT, 1 HÄLT) → R2 frischer Spawn), **ratifiziert** 2026-08-13
  (Nic, drei Stempel: Wächter einschalten · RAT-24 zurückziehen · Stempel-Guard
  einhängen).
- **Betrifft:** `decisions/INDEX.md`; die in der Tabelle unten benannten Mechaniken;
  `conventions/services.md` (zwei Textkorrekturen). **Keine Convention** (n=1 —
  einmalig angewandte Sortierung, kein stehendes Regelwerk).
- **Anlass-Ticket:** xbuddy-prozess#99. **Spur:**
  `~/brainstorm/berater-runde/20260813-1310-ENTSCHEID-mechanik-lebend-oder-weg.md`.

## Problem

Von 18 Gegenmechaniken mit geprüfter Aufrufkette waren **acht folgenlos (44 %)** —
und niemand hatte sie 44 bis 57 Tage lang vermisst. Zugleich fragte Nic, ob der
Reflex „Bruch gefunden → Mechanik dagegen bauen" selbst das Problem sei
(*„bauen wir nur balkone stimmt die grundlogik dahinter"*).

Gemessen: die **Bau**-Rate fällt seit Juni um Faktor 2 relativ zum Produkt-Output
(6,2 % → 3,2 % → 2,9 % Mechanik je Commit). Es gab bis zu diesem Entscheid
**null Rückbau**: keine zurückgezogene Ratifizierung, keine gelöschte Konvention
in der gesamten Projekthistorie. Die Bau-Logik stimmt; die **Halte**-Logik fehlte.

## Betrachtete Alternativen

- **A — Detektions-Lücke schließen:** eine Schicht bauen, die das Schweigen einer
  gestorbenen Mechanik bemerkt (Heartbeat je Mechanik, Alterswarner,
  Wirksamkeits-Pflicht). Deckt alle acht Fälle. **Verworfen von Nic**: kollidiert
  mit dem Entschlackungs-Beschluss (xbuddy-prozess#96, −25 %, 2026-08-10) und mit
  dem Scope-Kill des membran-gate-Entscheids vom 2026-07-03 („sobald ein Fix eine
  generische Convention/Framework-Feld einführt → zurück").
- **B — Bestands-Lücke schließen:** zurückbauen statt detektieren. **Gewählt.**
- **Nichts ändern:** ernsthaft geprüft. Verworfen, weil zwei Schichten der
  Nic-Stempel-Membran zum Entscheidungszeitpunkt gleichzeitig offen lagen.
- **Erster Entwurf der Sortier-Regel** (F1 „hat sie je gelebt" zuerst):
  vom Antiberater falsifiziert — siehe „Wie entschieden".

## Wie entschieden / gemessen

Nic wählte die Lesart, nachdem R1 **ECHTE-GABEL-IM-ANLASS** verdiktet hatte: die
Belege stützten A und B gleich gut, und der Constitution-Rang brach den
Gleichstand nicht (Zuverlässigkeit und Einfachheit sind **benachbart**, und es ist
die Produkt-Verfassung, nicht die der Arbeitsweise).

Der Antiberater (Codex) brach den ersten Entwurf an zwei Stellen:

1. **`service_health_poller` als „nie gelebt → weg"** — `conventions/services.md`
   (SVC-8) verlangt die Heartbeat-Überwachung für Bot-Services ohne HTTP und
   benennt genau diesen Poller als lesende Instanz. Löschen hätte eine
   ratifizierte Betriebsanforderung still zur Lüge gemacht. **Ein-Wege-Tür.**
2. **„neun fehlende Ledger-Zeilen"** — nachgemessen 35 Records / 35 Index-Zeilen,
   **keine Lücke**. Die Zahl war falsch; der Patch hätte den Ledger beschädigt.

Beides führte auf **einen** Konstruktionsfehler: die Frage nach der Lebendigkeit
stand vor der Frage nach der Norm. Damit konnte „nie installiert" eine
Ratifizierung schlagen.

## Ergebnis — die Sortier-Regel, F0 zuerst

> **F0 — Trägt sie eine ratifizierte Norm?** Grep in genau drei Orten:
> `decisions/RAT-*.md`, `conventions/*.md`, `specs/*.md`. **Nur diese zählen.**
> Skill-Prosa, READMEs und Ticket-Text sind kein Norm-Anspruch (die gehören nach F3).
> **Ja → sie kann in diesem Pass nicht sterben.** Sie verlässt den Trichter und
> landet auf einem von zwei Nic-Stempeln: (a) Norm bleibt → verdrahten/reparieren,
> oder (b) Nic zieht die Norm per Supersede-Record zurück — erst danach fällt die
> Mechanik, in einem eigenen Schritt.
>
> **F1 — Todes-Commit bekannt, Tod war Nebenwirkung?** → Bug, reparieren.
> **F2 — Hat sie je gelebt?** Nein → weg.
> **F3 — Behauptet ein *lebendes* Artefakt ihre Wirkung?** Nein → weg, ersatzlos.
> Ja → im selben Commit: (a) leben lassen + Registrierung, oder (b) Anspruch
> mitstreichen + Mechanik weg. **Anspruch stehenlassen und Mechanik tot lassen
> ist verboten** — der Zwischenzustand „deklariert, aber nicht lebend" ist
> abgeschafft, ohne dass ihn irgendetwas misst.
>
> **Sperre gegen F3(a):** Liegt die Registrierung **außerhalb des Repos**
> (Profil-`settings.json`, Pi-Unit), ist „verdrahten" nur zulässig, wenn Nic die
> Mechanik ausdrücklich als tragend benennt.

**F0 ist terminal** — nach ihm gibt es keinen Pfad mehr von „nicht installiert"
nach „gelöscht". Das ist der strukturelle Verschluss des Bruchs, kein Warnhinweis.

**F1 vor F2** ist ebenfalls neu: „lebt nicht" und „ist kaputt" waren bei sieben
Fundstellen dieselbe Beobachtung (ein Suchen-und-Ersetzen im Public-Scrub). Die
billigere Frage muss zuerst kommen, sonst wird ein Ein-Zeilen-Bug als Ballast
entsorgt.

### Angewandte Verdikte

| Mechanik | F0 | Verdikt |
|---|---|---|
| `status_rollback_guard.py` | ja (`reconcile.md:66`, `prep-lifecycle.md:3,136`) | **verdrahtet** im aktiven Profil (Nic-Stempel) |
| `service_health_poller.py` + Timer | ja (SVC-8) | **verdrahtet**, Alarmweg Ende-zu-Ende verifiziert (Nic-Stempel) |
| `verdict_check` / `prep-reconcile.yml:61` | ja (`reconcile.md:64,66`) | reparieren (Scrub-Platzhalter) |
| `tools/card_form_quote.py:51` | ja (`prep-lifecycle.md:336,404,419,444`) | reparieren |
| `deploy/restart_pending_log.py:39,42` | ja (`services.md:135`) | reparieren |
| `tools/render-gate/check.js` | ja (RAT-24) | **RAT-24 zurückgezogen** (Nic-Stempel) → RAT-37 |
| `handoff_check.py` | nein (nur Prosa) | weg + 5 Anspruchs-Stellen im selben Commit |
| `lotse/hooks/restart_pending_log.py` (Hook-Rolle) | nein | weg; Norm-Text auf die lebende Kopie umschreiben |
| `runner_health.py` + Unit | nein (`services.md:140` ist Scope-Abgrenzung) | weg + Halbsatz mitstreichen |
| `decisions/INDEX.md` | — | **aus dem Scope** (35/35, keine Lücke) |

**Bilanz: zwei Löschungen, drei Reparaturen, zwei Verdrahtungen, ein Ledger-Rückzug
— und eine Fehlmessung zurückgenommen.** Von neun Punkten war exakt **einer**
echter Ballast. Das ist das ehrliche Ergebnis und zugleich die Antwort auf die
Ausgangsfrage: **wir haben weniger Ballast als vermutet und mehr kaputte
Verdrahtung.**

### Woran wir merken würden, dass es falsch war

- **K1 — Grep-Grenze bei systemd.** „Nie gelebt" ist aus dem Repo nicht beweisbar.
  Taucht für eine unter F2 gelöschte Mechanik nachträglich ein Live-Beleg auf
  (journalctl-Spur, Unit im Backup, Nic sagt „die lief mal"), wird der
  Lösch-Commit revertet und der Fall ab F0 neu gefahren.
- **K2 — RAT-24.** Ohne Nics Supersede-Stempel wäre `tools/render-gate/` stehen
  geblieben; der Pass wartet nicht auf ihn und ersetzt ihn nicht. *(Stempel kam.)*
- **K3 — F0 blockiert alles.** Zeigt sich, dass „ratifizierte Norm" so inflationär
  vergeben ist, dass F0 jeden Rückbau verhindert, ist das Problem die Norm-Vergabe
  — dann Constitution-Frage, keine Aufräum-Frage.
- **K4 — die abgewählte Lesart.** Wird beim nächsten `/prozesswerkstatt`-Lauf
  erneut eine tote Mechanik nur **zufällig** gefunden, hat Lesart A ihren Beleg
  und die Gabel wird neu aufgemacht.

## Verhältnis zu xbuddy-prozess#96

Zweiter Pass, disjunkte Dateimenge: #96 räumt Skill-**Prosa**, RAT-36 räumt
**Mechanik**. RAT-36 darf in Skill-Prosa **ausschließlich** die Anspruchs-Zeile
der Mechanik streichen, die es löscht; diese Zeilen zählen auf #96s −25 % ein.
Der #96-Pilot `arbeitstag-prep.md` ist kollisionsfrei, weil der Stempel-Guard auf
*verdrahten* landet.

---

## Nachtrag 2026-08-17 — zwei Verdikte nachgezogen (#1885)

Die Verdikt-Tabelle oben stand vier Tage unausgeführt. Beide offenen Zeilen sind
jetzt erledigt, eine davon **gegen** ihr ursprüngliches Verdikt.

### `deploy/restart_pending_log.py:39,42` — „reparieren" ist widerlegt

Das Verdikt lautete *reparieren* (Scrub-Platzhalter im Regex). Es beruhte auf
einer Fundstelle ohne Aufrufkette. Bei der Arbeit an #1839 unabhängig
nachgemessen:

- Die **verdrahtete** Fassung ist `~/.claude/hooks/restart_pending_log.py` — dort
  steht kein Platzhalter, sie ist über `LOTSE_PROJECT_REPO` parametrisiert.
- Der einzige Konsument `deploy/update.sh:64` importiert ausschließlich
  `load_mapping` und `services_for_paths` — **nie** `XBUDDY_REMOTE_RE`, also nie
  den beanstandeten Regex.
- `conventions/services.md:154` benennt bereits die lebende Kopie.

Die Repo-Datei ist ein Duplikat aus der Framework-Migration, das niemand als Hook
lädt. Es gibt nichts zu reparieren; der Regex kann nie matchen, weil er nie
aufgerufen wird. Die Zeile bleibt als Geschichte stehen — mit dieser Korrektur
daneben.

**Die Lehre gehört zum Eintrag:** eine Datei zu lesen belegt nicht, dass sie läuft.
Zu jeder Behauptung „Mechanik X ist tot" gehört die Aufrufkette, nicht nur der
Fundort. Genau dieser Fehler steckte im ursprünglichen Verdikt.

### `runner_health.py` + Unit — „weg" ist ausgeführt

Entfernt wurde das **ganze** Verzeichnis `deploy/runner/` (5 versionierte
Dateien), nicht nur Skript und Unit: README, Test und Unit-Vorlagen existierten
ausschließlich, um diese eine Mechanik zu bedienen. Skript und Unit zu löschen
und die README stehenzulassen wäre exakt der Zustand, den dieser Entscheid
verbietet.

Zwei Befunde, die beim Ausführen dazukamen und das Verdikt stützen:

- Die README zielt auf den Läufer `pi5-buddy`. Den gibt es nicht mehr — der
  einzige registrierte Läufer ist inzwischen `win-wsl-buddy`. Die Mechanik hätte
  also selbst dann nichts bewirkt, wenn sie verdrahtet gewesen wäre.
- Sie trägt zusätzlich Scrub-Platzhalter (`<your-org>`), gehört also in dieselbe
  Klasse wie die Funde aus #1839.

`pytest.ini` verlor die Zeile `deploy/runner/tests` mit — ohne sie bricht der
Lauf an einem Pfad, den es nicht mehr gibt.

**Der Halbsatz in `conventions/services.md`,** den das Verdikt mitstreichen
wollte, existiert dort nicht (mehr): ein `grep` auf „runner" über die Datei ist
leer. Nichts zu tun.

---

## Fußnote 2026-08-17 — was „35/35" gemessen hat, und was nicht

Die zurückgenommene Fehlmessung oben („neun fehlende Ledger-Zeilen") wurde mit
**35 Records / 35 Index-Zeilen** widerlegt. Das war korrekt und bleibt stehen —
aber es misst die **innere** Konsistenz des Ledgers: hat jeder Record eine Zeile.

Es misst **nicht** die Frage, die daneben liegt: hat jede ratifizierte Runde einen
Record. Die Antwort darauf war *nein*. Elf Runden aus dem Fenster 2026-07-30 bis
08-01 lagen zum Zeitpunkt dieses Passes ausschließlich im nicht-öffentlichen
Notizverzeichnis; zwei öffentliche Dateien verlinkten dorthin. Für den
vorgeschriebenen Re-Litigations-Grep über `decisions/` waren sie unsichtbar —
mit einem belegten Folgefall (ein Ticket schlug einen Weg vor, den ein
ratifizierter Beschluss verworfen hatte). Nachgeholt mit #1782 (RAT-38..RAT-44 +
Nachträge an RAT-17).

**Die Lehre ist dieselbe wie im Nachtrag darüber, eine Ebene höher:** ein
konsistenter Ledger ist nicht dasselbe wie ein vollständiger. „35/35" beantwortet
„stimmt die Liste mit sich selbst überein", nicht „steht alles drin".
