# RAT-7 — Keine `conventions/skills.md` auf Vorrat: beobachten bis 3+ gleichartige Skills mit Drift-Schmerz

- **Entschieden:** 2026-05-31 (Berater-Runde „Lego-Vertrag skalierbar", Codex
  als Antiberater), **ratifiziert** 2026-06-06 (Nic, `/arbeitstag-prep` — „RAT
  notiz und dann schließen").
- **Betrifft:** `conventions/` (eine potenzielle `conventions/skills.md`),
  `conventions/README.md` (3.-Vorkommen-Modell), `CLAUDE.md` §6 („Lege nichts
  auf Vorrat an"), `specs/constitution.md` (Lego-Prinzip, Linse 5). Schließt
  **#297**.
- **Transkript (Evidenz):** `brainstorm/berater-runde/2026-05-31-1949-antiberater-lego-vertrag-skalierbar.md`
  (`[RISKANT]`-Befund mit Skill-Sorten-Tabelle) → Vorschlag
  `20260531-vorschlag-lego-vertrag-skalierbar.md`.

## Beschluss

Es wird **jetzt keine** generische `conventions/skills.md` geschrieben. Die
sechs bestehenden Skill-Adapter (CAV, FAA, GAA, KAV, TER, TES) erfüllen das
3.-Vorkommen-Kriterium **nicht** — sie sind nicht dieselbe Sorte: TER ist
lesend/antwortet selbst; TES/FAA sind async-WriteTasks mit Privatchat-Session;
KAV ist async-WriteTask **mit Reload-Hooks**; CAV/GAA sind weitere Mischformen.
Eine Convention darüber wäre **Convention-Theater** (pro Klausel passt nur die
Hälfte ohne Ausnahme rein) und verletzt das Lego-Prinzip (Linse 5: ein neues
Exemplar muss mechanisch andocken).

## Warum

- **3.-Vorkommen heißt gleichartige Sorte, nicht bloß Anzahl** (`conventions/README.md`):
  sechs verschiedene Sorten rechtfertigen keine gemeinsame Bauregel.
- **Auf Vorrat = Wildwuchs** (CLAUDE.md §6): die Lösung wartet auf konkreten
  Schmerz (Drift, Wiederholung, schwierige Erweiterung), nicht auf Antizipation.

## Re-Litigation / Reopen nur bei erfülltem Trigger

Eine Skill-Convention (dann via `/berater-runde` für das konkret nachgewiesene
Muster) wird erst geschrieben, wenn **eines** belegt ist:
- **3+ ReadTasks** mit identischem `PrivateChatSession`-Pattern, **oder**
- **3+ WriteTasks** mit identischem Reload-Hook-Mechanismus, **oder**
- **3+ Skills**, die in Tonfall/Quittungs-Format **messbar** voneinander driften,
  ohne Begründung.

Bis dahin: keine `skills.md`. Taucht die Frage neu auf, hier prüfen und mit
Verweis auf RAT-7 schließen.
