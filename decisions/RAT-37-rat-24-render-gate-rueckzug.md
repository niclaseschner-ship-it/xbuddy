# RAT-37 — RAT-24 zurückgezogen: das Render-Gate wird beerdigt, nicht repariert

- **Entschieden:** 2026-08-13 (Berater-Runde „Mechanik: lebend oder weg", als
  eigener Stempel aus dem Rückbau-Pass herausgezogen — ausdrücklich **nicht** als
  Nebenfolge eines Aufräum-Commits), **ratifiziert** 2026-08-13 (Nic).
- **Supersedes:** RAT-24 (Deterministisches Render-/Layout-Gate für Display-Views,
  ratifiziert 2026-06-26).
- **Betrifft:** `decisions/RAT-24-render-gate-display.md` (als zurückgezogen
  markieren), `tools/render-gate/` (entfällt), `lotse/commands/arbeitstag.md`
  (Gate-Aufruf + Beobachtungs-Zeilen-Pflicht im visuellen Self-Check entfällt),
  `decisions/INDEX.md`. Schließt xbuddy#1855 als gegenstandslos.
- **Anlass-Ticket:** xbuddy-prozess#99, Ball aus xbuddy-prozess#77.

## Problem

RAT-24 war ratifiziert, gebaut und lief im Bericht-Modus. Nach 48 Tagen war die
Bilanz:

- **Nie verdrahtet** bis 2026-08-07 — der Gate-Aufruf stand in keinem Skill; alle
  RAT-24-Trigger-Zähler (Flip-zu-Block, Rollout, KI-Schicht) standen auf null,
  nicht weil nichts geschah, sondern weil nie gemessen wurde.
- **Am 2026-08-07 verdrahtet** (Werkstatt-Lauf, `lotse@295db44`), samt
  Beobachtungs-Zeilen-Pflicht als Zähler.
- **Am 2026-08-12 wieder blind:** die Rück-Verriegelung der Auth zog alle **drei**
  Pilot-Ansichten hinter den Cookie; `tools/render-gate/check.js:117-135` öffnet
  je einen frischen Inkognito-Kontext ohne Cookie-Naht. 3 von 3 Ansichten liefern
  `request-fehler status:401`, der Harness misst danach die Geometrie der
  Re-Pair-Seite (xbuddy#1855).
- **Gemessene Nutzung insgesamt:** `0` von `97` Issue-/PR-Kommentaren seit der
  Verdrahtung tragen eine `render-gate:`-Beobachtungszeile.

Sechs Tage nach der Reparatur war das Werkzeug erneut tot — und gefunden hat das
kein Wächter, sondern zufällig eine Prüfung auf einem fremden Diff.

## Betrachtete Alternativen

- **Reparieren** (xbuddy#1855: Cookie-Naht per ENV oder `--cookie`-Argument).
  Technisch klein. Verworfen, weil das Werkzeug in sechs Wochen zweimal
  gestorben ist und in dieser Zeit **keine einzige** Beobachtung erzeugt hat: der
  Engpass ist nicht die fehlende Naht, sondern dass niemand es benutzt.
- **Weiter offen halten** und die Trigger irgendwann auswerten. Verworfen — das
  ist der Zustand, der schon 48 Tage gedauert hat und den xbuddy-prozess#77
  ausdrücklich als „versackt" protokolliert hat.
- **Als Nebenfolge im Aufräum-Commit löschen.** Vom Antiberater als **RISKANT**
  markiert und verworfen: ein Ledger-Rückzug ist Geschichte, kein Diff, und
  gehört unter einen eigenen Stempel. Genau deshalb dieser Record.

## Wie entschieden / gemessen

`0` von `97` Kommentaren (mechanisch gezählt über die Kommentar-API im Fenster ab
Verdrahtung) plus zwei stille Totalausfälle in sechs Wochen. Die Regel aus RAT-36
(F0) hätte das Werkzeug im Rückbau-Pass geschützt, weil RAT-24 eine Norm ist —
deshalb war der einzige zulässige Weg, **die Norm selbst** zurückzunehmen.

Nic-Setzung, wörtlich als Konsequenz akzeptiert: **der Augen-Check bleibt
subjektiv.**

## Ergebnis

**RAT-24 ist zurückgezogen.** Das deterministische Render-/Layout-Gate ist kein
Bestandteil der Arbeitsweise mehr; `tools/render-gate/` entfällt, der Aufruf im
visuellen Self-Check entfällt, xbuddy#1855 wird gegenstandslos geschlossen.

Der visuelle Self-Check per Screenshot über die Origin (Selbst-Ansehen des PNG vor
dem Nic-Test) **bleibt unberührt** — er ist älter als RAT-24 und war nie Teil
davon.

**Dies ist der erste zurückgezogene ratifizierte Entscheid des Projekts.** Bis
2026-08-13 gab es null Rückbau im Ledger. Der Wert dieses Records liegt deshalb
nicht nur im Render-Gate, sondern im Beleg, dass Rückzug überhaupt möglich ist.

### Woran wir merken würden, dass es falsch war

Fängt Nic innerhalb von 60 Tagen **zwei** Layout-/Render-Regressionen selbst, die
eine datenunabhängige Invariante (Konsolen-Fehler, 404, Element außerhalb des
Viewports, Text-Clipping) mechanisch gefunden hätte, ist der Rückzug widerlegt —
dann kommt das Thema als neuer Entscheid zurück, **nicht** als stilles
Wiederbeleben dieses Werkzeugs.
