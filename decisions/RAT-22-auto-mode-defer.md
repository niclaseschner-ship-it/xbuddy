# RAT-22 — Auto-Mode = Defer (Halt-Befund parken, keine Regel-Aufweichung)

**Entschieden:** 2026-06-24 (Nic)
**Status:** RATIFIZIERT (berater-runde leicht gefahren — R1 + Antiberater Opus-Fallback wegen Codex-Timeout, Zwei-Wege-Tür außer P2)
**Betrifft:** `~/.claude/commands/arbeitstag.md` (Watchdog-Gate-Halt-Regel, „ERREICHBAR BLEIBEN", PEP).
**Anlass:** xbuddy-prozess#71 (PW-71 — Auto-Mode-Pragmatik-Carve-outs).
**Deliberation:** `brainstorm/berater-runde/20260624-1531-RATIFIZIERT-pw71-auto-mode-defer.md`.

## Beschluss (1 Satz)

Im autonomen Nachtlauf werden die harten Halt-/Dispatch-Regeln **nicht aufgeweicht**;
„Auto-Mode" wird als **Defer-Haltung** definiert — ein Watchdog-`strukturell`-Halt
parkt den Track (`blocked`/`Auflösung: nic`), statt ihn selbst zu fixen oder Nic zu
wecken, und PEP („du codest nicht") bleibt absolut (auch Einzeiler = Dispatch).

## Kontext / Problem

- **n=2-Schmerz:** 2026-06-22-Nachtlauf überfuhr `strukturell → Halt` mit „klarem
  Fix-Pfad" (funktionierte); session2 wich bei Kleinst-Fix auf Orchestrator-Self-Edit
  aus (1× Syntax-Bug). Beide GRENZFALL — „ging gut", aber Regel-Ambiguität.
- **R1-Befunde:** „Auto-Mode" ist **kein** Skill-verankerter Modus (n=0); die Halt-Regel
  ist hart-ohne-Auslegung; der Watchdog liefert nur `Vorschlag: ein Satz Richtung — kein
  Code`; „strukturell aber durchwinkbar" ist verboten; PEP hat n=0 Ausnahmen.
- **Reframe:** Die „Carve-out"-Prämisse von PW-71 war falsch — der Nachtlauf-Override war
  regelwidrig. Es fehlte eine definierte **Auflösung** des Halt-Befunds im Nic-unerreichbar-Fall.

## Entscheidung im Detail (Inline-Klauseln, keine neue Sektion)

### A. Defer an der Watchdog-Gate-Regel
- Watchdog-`strukturell`/`strukturelles Risiko` im autonomen Lauf → Track `blocked` +
  Blocker-Zeile `Auflösung: nic` (bestehender PW-13-Pfad), andere Tracks laufen weiter,
  Befund in Morgen-Vorlage. **Kein Self-Fix.**
- **Ehrlichkeits-Pflicht (Antiberater-Fang):** Hängen die übrigen offenen Tracks transitiv
  am geparkten, ist der Lauf effektiv zu Ende — die Vorlage sagt das, statt Fortschritt
  vorzutäuschen. Deckt auch `api_mode: sequential` (nur ein Track läuft).

### B. Erreichbarkeits-Annahme benennen
- „ERREICHBAR BLEIBEN" setzt Nic-Erreichbarkeit voraus; im Nachtlauf nicht gegeben → eine
  Zeile, die auf die Defer-Klausel verweist. Keine zweite Halt-Beschreibungs-Sektion
  (Spec-Drift-Vermeidung).

### C. PEP absolut, Kleinst-Fix = Dispatch
- Auch Einzeiler / „direkter Fix nach Live-Test im selben arbeitstag" → schneller
  Haiku-Dispatch, nie Orchestrator-Self-Edit. PEP ist eine **Erreichbarkeits**-Regel; ein
  „≤N Zeilen"-Carve-out griffe genau diese Begründung an.

## Kill-/Reopen-Trigger
- Strukturell-Track erscheint morgens **gemergt** statt `blocked` → Regel griff nicht (A).
- Haiku-Dispatch bei Einzeilern bremst messbar → eng begrenzter Orchestrator-Edit-Carve-out
  neu verhandeln (C).
- Defer-Deadlock häuft sich (Scheibe zu seriell) → Abhängigkeits-Vorprüfung beim Planen
  nachschärfen.
