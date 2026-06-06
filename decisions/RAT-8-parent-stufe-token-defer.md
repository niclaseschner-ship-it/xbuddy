# RAT-8 — `data-stage="parent"`-Token-Block vertagt bis zur 2. Parent-App

- **Entschieden:** 2026-06-06 (Nic, direkt ratifiziert — Vertagung mit Trigger,
  kein berater-runde nötig). Ausgelöst im Werft-Lauf zur Wetter-Garderoben-
  Editor-Seite (#328), die erste eltern-seitige (parent) Oberfläche im System.
- **Betrifft:** `display/_shared/design/tokens.css` (DTOK-1), `conventions/design-tokens.md`
  (DTOK-4 Stufen-System); `specs/buddies/wetter.md` (OPEN-WETTER-K). Keystone-Ticket **#328**.

## Beschluss

Der `data-stage="parent"`-Stufen-Block im geteilten Token-Strang wird **jetzt nicht
definiert**. Der Strang trägt heute nur `reader` (Default) und `toddler`; die
parent-Stufe steht bislang nur als Absicht im Kopf-Kommentar. Die Wetter-Garderoben-
Editor-Seite (#328) fährt in V1.1 bewusst auf den **Basis-/Reader-Tokens** — das sieht
sauber aus (an Mockups belegt) und ist DTOK-5-konform (kein Hardcode).

## Warum

- **Eine Eltern-Oberfläche ist noch kein Muster.** Den parent-Stufen-Block an einem
  einzigen Vorkommen festzuklopfen riskiert, ihn an genau diese eine Seite
  überanzupassen. Stufen-Werte (Dichte, Schriftgröße, Nüchternheit) prägen **systemweit**
  alle künftigen Eltern-Seiten — die Entscheidung gehört in die Design-System-Spur, nicht
  improvisiert in einen Buddy-Ticket (Anti-Pattern „Overhead in Buddy-Struktur").
- Konsistent mit dem xbuddy-Prinzip „Konvention/Stufe entsteht am **2. Vorkommen** mit
  konkretem Schmerz, nicht antizipativ".

## Trigger (wann wird es beantwortet)

**Bei der zweiten Parent-App / eltern-seitigen Oberfläche** (Nic, 2026-06-06). Dann
liegen zwei echte Vorkommen vor; aus ihrem gemeinsamen Bedarf wird der
`data-stage="parent"`-Block definiert und beide docken an. Bis dahin: Basis-/Reader-Tokens.

## Status

Vertagt mit Trigger. `OPEN-WETTER-K` in `specs/buddies/wetter.md` verweist auf diesen
Record. Kein Folge-Ticket nötig, bis die 2. Parent-App auftaucht.
