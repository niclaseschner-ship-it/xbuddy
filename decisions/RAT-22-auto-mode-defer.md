# RAT-22 — Auto-Mode = Defer, keine Regel-Aufweichung

- **Entschieden:** 2026-06-24 (Nic „ok"), **ratifiziert** 2026-06-24
  (Berater-Runde PW-71, Berater + Antiberater **Opus-Fallback** — Codex lief in
  Repo-Crawl-Timeout, daher schwächer/Echo-Risiko).
- **Reversibilität:** Zwei-Wege-Tür (Doku/Prozess) — außer P2 als Ein-Wege-Tür
  (eine durchgewunkene Strukturell-Drift ist gemergt und nicht rückholbar).
- **Anlass:** xbuddy-prozess#71 — Auto-Mode-Pragmatik-Carve-outs: im autonomen
  Nachtlauf überfährt der Orchestrator zwei harte arbeitstag.md-Regeln
  (Watchdog-`strukturell` → Halt; „du codest nicht selbst").
- **Betrifft:** `~/.claude/commands/arbeitstag.md` (Defer-Klausel an der
  Watchdog-Gate-Regel `strukturelles Risiko`, Erreichbarkeits-Zeile bei „ERREICHBAR
  BLEIBEN", PEP-Kleinst-Fix-Klausel — **Inline-Klauseln, keine neue Sektion**),
  `decisions/INDEX.md`.
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/20260624-1531-RATIFIZIERT-pw71-auto-mode-defer.md`
  → Vorschlag `20260624-153106-vorschlag-pw71-auto-mode-defer.md`,
  Antiberater (Opus-Fallback) `a097abf025e64aef0`.

## Beschluss

Die „Carve-out"-Prämisse war falsch. R1 zeigte: „Auto-Mode" ist **kein**
Skill-verankerter Modus (n=0), die Halt-Regel ist hart-ohne-Auslegung, der
Watchdog liefert nur einen Richtungssatz (kein Code), „strukturell aber durchwinkbar"
ist verboten. Lösung: **Regeln bleiben hart, Auto-Mode wird als Defer-Haltung
definiert** — als Inline-Klauseln, keine neue Sektion (Doppel-Beschreibung des
Halt-Verhaltens wäre Spec-Drift-Klasse).

1. **P2 — Halt-Regel (Defer):** Watchdog-`strukturell` im autonomen Lauf → Track
   `blocked` + `Auflösung: nic`, andere laufen weiter, Befund in Morgen-Vorlage.
   Kein Self-Fix. **Ehrlichkeits-Pflicht:** hängen die Rest-Tracks transitiv am
   geparkten, ist der Lauf effektiv zu Ende — die Vorlage sagt das (deckt auch
   `api_mode: sequential`).
2. **P1 — Erreichbarkeit:** Eine Zeile bei „ERREICHBAR BLEIBEN" — die
   Nic-Erreichbarkeits-Annahme gilt nachts nicht; Halt = Parken statt
   Sofort-Antwort. Keine eigene Sektion.
3. **P3 — PEP absolut:** Auch Einzeiler/Live-Test-Fix → Haiku-Dispatch, nie
   Self-Edit. PEP ist eine Erreichbarkeits-Regel (auch ein Einzeiler ist eine
   Tool-Schleife) — ein „≤N Zeilen"-Carve-out griffe genau die Begründung an.

## Kill-Kriterien (laufen mit)

- **P2:** Strukturell-Track taucht morgens **gemergt** statt `blocked` auf → Regel
  griff nicht.
- **P3:** Haiku-Dispatch bei Einzeilern bremst messbar → eng begrenzter Carve-out
  neu verhandeln.
