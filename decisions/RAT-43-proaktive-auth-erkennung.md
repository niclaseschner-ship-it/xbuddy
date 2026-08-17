# RAT-43 — Proaktives Pairing-Angebot im Eltern-Chat: fragen statt wissen

**Status:** RATIFIZIERT 2026-07-31 (Nic „das ist ok", nach einer Zwischenrunde zum
Antiberater-Bruch)
**Betrifft:** `specs/platform/eltern-chat.md` (EC-44), der System-Prompt des
Eltern-Chat-Agenten, zwei Skill-Descriptions
**Bezug:** RAT-31 E6c / RAT-35 (registry-frei, `paired_at` bewusst abgerissen),
RAT-18/27/32 (Cookie-Auth — der Flow selbst bleibt unangetastet), AUTH-8
(401 → Re-Pair, reaktiv)
**Ticket:** #1338 (Epic Auth-Härtung) · komplementär zur Pairing-Mechanik (#948)
**Entscheid-File:**
`brainstorm/berater-runde/20260731-205948-RATIFIZIERT-ENTSCHEID-1338-proaktive-auth-erkennung.md`
(Antiberater = **Opus-Fallback**, Codex am Usage-Limit)

## Problem

Die Auth-Mechanik ist gebaut, aber sie ist **reaktiv**: ein Gerät bekommt 401 und
der Mensch muss von selbst darauf kommen, dass er ein Pairing braucht. Nic
2026-07-31: der Bot soll das selbst erkennen — wenn jemand ein Problem meldet oder
eine App nutzen will, soll er nachfragen und das Pairing anbieten.

## Betrachtete Alternativen — eine echte Gabel

- **A · sprach-getriggert (gewählt).** Der Bot erkennt aus der Nutzer-Sprache den
  möglichen Auth-Bedarf, fragt nach und bietet den bestehenden Pairing-Link an —
  **ohne den Status zu kennen**. Berührt nur den System-Prompt und zwei
  Skill-Beschreibungen. Zwei-Wege-Tür.
- **B · status-wissend.** Der Bot kennt den Pairing-Status pro Person/Gerät und fragt
  gezielt. **Verworfen** — das setzt genau das Feld voraus (`paired_at` pro Gerät),
  das RAT-31 E6c bewusst abgerissen hat, und würde damit die registry-freie
  Invariante von RAT-31/RAT-35 re-litigieren. Wer B will, braucht eine eigene Runde
  **gegen** RAT-31, keinen normalen Folgeschritt.

**Der stärkste Fall für B** ist im Protokoll festgehalten, nicht weggelassen: „auf
Verdacht fragen" nervt, wenn der Cookie längst da ist. Die Gegenmaßnahme in A ist
Zurückhaltung — nur bei Einrichtungs-/Problem-Absicht anbieten, nicht in jedem Turn.

## Wie entschieden

Drei Gründe für A, in dieser Reihenfolge: Reversibilität (A ist eine Zwei-Wege-Tür,
B eine Ein-Wege-Tür **plus** Re-Litigation eines ratifizierten Beschlusses); A deckt
Nics eigenes Wort — er sagte *abfragen*, also fragen, nicht wissen; und
Constitution-Einfachheit.

Der Antiberater brach die erste Fassung an einer Stelle: der Nudge könnte über einen
Skill laufen, der ohne Erwachsenen-Gate einen Pairing-Link ausstellt — ein Kind
hätte sich damit selbst einen Zugang minten können. Dafür lagen zwei Patch-Wege vor
(Nudge über den harmlosen Skill führen, oder den anderen Skill gaten).

**Nic löste den Bruch ohne Patch auf:** der Eltern-Chat ist nur für Eltern. Es gibt
keinen Kind-Pfad in diesen Kanal, also kann kein Kind den Nudge auslösen — das Gate
wäre eine Mechanik gegen einen Fall, den die Kanal-Grenze bereits ausschließt.

## Ergebnis

- **Weiche A.** Ein Absatz im System-Prompt plus zwei Halbsätze in
  Skill-Beschreibungen. **Kein neuer Skill, kein neuer Mechanismus, kein
  `paired_at`.**
- Gelandet als **EC-44** in `specs/platform/eltern-chat.md` (die Runde hatte noch
  eine andere Nummer vorgemerkt; belegt ist die tatsächlich vergebene).
- **Konservativer Start:** nur auf App-Einrichtungs-Signale, nicht auf die breite
  Problem-Signalklasse.

## Woran wir merken würden, dass es falsch war

- **Signalklasse zu breit.** Als RISKANT protokolliert: „geht nicht" überlappt mit
  ganz anderen Ursachen (Stream-Freeze, 500er). Wenn der Bot bei diesen Fällen
  Pairing anbietet, ist die Erkennung falsch justiert → enger stellen, nicht mehr
  Mechanik bauen.
- **Falsch-positive Nudges** bei längst gepairten Nutzern → Anlass, die
  Zurückhaltung zu verschärfen. Es ist **kein** Anlass, B nachzuziehen; B bleibt eine
  eigene Runde gegen RAT-31.
- **Bekannte Scope-Grenze:** ohne Rückkanal von echten App-Fehlern in den Chat
  (deferred) kann Proaktivität nur auf **getippte** Signale reagieren, nie auf einen
  tatsächlich beobachteten 401.
