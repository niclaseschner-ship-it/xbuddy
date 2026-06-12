# Eltern-Chat-Skill Bauplan (Lego-Karte)

> Wegweiser, kein Normativ-Speicher. Alle Norm-Aussagen leben in den
> zitierten Quellen.

Die 24 Eltern-Chat-Skills (Stand 2026-06-12) zerfallen in fünf
Klassen mit unterschiedlichen Bauplänen. Wer einen neuen Skill baut
oder einen bestehenden anfasst, **liest in der für seine Klasse
genannten Reihenfolge** — und folgt von dort den verlinkten
ID-Ankern. Diese Datei vergibt **keine eigenen** Norm-IDs (kein
`ECS-N`-Präfix); sie ist Indexseite, nicht zweite Wahrheit.

Grund für die Karte: Ohne sie lebt ein Skill-Autor heute in drei
Dateien gleichzeitig (`specs/platform/eltern-chat.md`,
`conventions/tasks.md`, `conventions/mini-app-design.md`) und muss
sich die richtige Lese-Reihenfolge je nach Klasse selbst
zusammensuchen. Die Klassen-Tabelle löst das.

## Skill-Klassen

| Klasse | Was sie ist | Beispiele heute |
|---|---|---|
| **A** | Pure Read — Tool-Result als Text-String, keine Daten-Änderung, kein Anhang | `seiten_uebersicht` (Übersicht), `termine_erfragen`, `wuensche_zeigen` (Lese-Pfad) |
| **B** | Read mit Anhang oder Button — Datei via Skill **oder** strukturiertes Präsentations-Ergebnis | `ca_verteilung` (Datei-Anhang), `einkauf_zeigen` (WebApp-Button, nach Migration auf TASK-10c Form b) |
| **C** | Kanonisch `propose` → `confirm` — schreibend mit Vorab-Bestätigung (EC-10 zweistufige Variante) | `routine_punkte_setzen`, `gericht_anlegen`, `panel_anlegen` (vor A2-Migration: alle schreibenden außer Klasse-D) |
| **D** | Sofort-Write (A2-Klausel) — One-Shot + stabile ID + idempotentes DELETE + Pre-Flight | `termin_eintragen`, `einkauf_hinzufuegen`, `foto_senden` |
| **E** | Mehrstufige Privatchat-Dialoge / Auth-Loops — eigener Abschluss-Gate-Pfad, **kein** A2-Default | `familie_anlegen`, `geraet_anlegen`, `kalender_verbinden`, `anbieter_wechseln`, `panel_anlegen` |

## Reihenfolge pro Klasse

Was lese ich zuerst, wenn ich einen Skill dieser Klasse baue oder
anfasse? Drei Zeilen pro Klasse.

### Klasse A — Pure Read

1. `specs/platform/eltern-chat.md` **EC-29** (Eine Stimme im
   Agent-Turn) — der Skill ist im Agent-Loop sprachlos, returnt
   einen User-tauglichen Text-String.
2. `conventions/tasks.md` **TASK-3** (`ReadTask` mit `run`) — die
   Klassen-Form; **TASK-10** (Lesende Aufgabe ist sprachlos im
   Agent-Loop) für die Helper-Grenze.
3. `conventions/tasks.md` **TASK-10c Form (a)** — reiner String als
   zulässige Rückgabe.

### Klasse B — Read mit Anhang oder Button

1. `specs/platform/eltern-chat.md` **EC-29** „Datei-Anhang-Klausel"
   (Skill sendet die Datei, LLM postet den Text).
2. `conventions/tasks.md` **TASK-10** „Datei-Anhänge"-Absatz und
   **TASK-10b** (ID-Wahl-Album per ICONS-7-Helper) für den
   Bilder-Album-Sonderfall; **TASK-10c Form (b)** oder **Form (c)** —
   strukturiertes Präsentations-Ergebnis (Form b) für Button/
   WebApp-Aufsatz; Form (c) für reinen Datei-Anhang.
3. `conventions/mini-app-design.md` **MAD-7** und **MAD-10** — wenn
   der Aufsatz eine eigene Mini-App ist, geht der Launcher hier
   durch (capability-gesteuert: Inline-Button oder `t.me`-Direktlink).

### Klasse C — kanonisch propose → confirm

1. `specs/platform/eltern-chat.md` **EC-10** „zweistufige Variante"
   (Vorab-Confirm bleibt Default für alles außerhalb A2/E) und
   **EC-22** (gezielt nach Pflicht-Feldern fragen).
2. `conventions/tasks.md` **TASK-4** (`WriteTask` mit `propose` +
   `execute`) und **TASK-6** (`post_execute_hooks` für
   `EC-21`-Reload-Aufrufe).
3. `conventions/tasks.md` **TASK-7** (Registrierung in
   `build_catalog`) und **TASK-10** (im Agent-Loop sprachlos:
   `propose()` returnt einen String; `execute()` darf nach Confirm
   selbst senden).

### Klasse D — Sofort-Write (A2-Klausel)

1. `specs/platform/eltern-chat.md` **EC-10 A2-Klausel** (Sofort-Write
   + Quittung + Undo-Wort als enger Default) — die drei Bedingungen
   (stabile ID, idempotentes DELETE, Pre-Flight-Check) müssen alle
   erfüllt sein.
2. `conventions/tasks.md` **TASK-9** (Sofort-Schreib-Aufgabe;
   verschärfte Form für A2 in der TASK-9-Verweis-Klausel) und
   **TASK-3** (Klassen-Form ist `ReadTask` mit Schreib-Wirkung).
3. `specs/platform/eltern-chat.md` **EC-34** (Cross-Skill-Footer,
   wenn ein WebApp-Pendant eines anderen Skills hilft) und
   **EC-35** (Frequenz-Trigger lesen aus `task_events`).

### Klasse E — Mehrstufige Privatchat-Dialoge / Auth-Loops

1. `specs/platform/eltern-chat.md` **EC-20** (Privatchat-Pfad,
   Phasen-Klausel: Vor-Schreib-Quittung, Aufräum-Phase schweigt)
   und **EC-10** zweistufige Variante (A2 gilt **nicht** für
   Klasse E).
2. `conventions/tasks.md` **TASK-5** (`is_async`, Worker-Thread-
   Pattern) und **TASK-7** (Session-Map-Verkabelung, Lego-Falle).
3. `conventions/privatchat-session.md` (SESS) und die jeweilige
   Skill-Spec (`specs/platform/familie-anlegen.md`,
   `geraet-anlegen.md`, `kalender-verbinden.md`,
   `panel-anlegen.md`, ggf. `zugangsdaten.md`).

## Bestehende Skills pro Klasse — wo finde ich Code-Beispiele

Diese Tabelle ist Bestandsaufnahme zum Stichtag 2026-06-12, kein
Norm-Vertrag. Sie zeigt, wo der Bauplan einer Klasse als gebauter
Skill nachgelesen werden kann.

| Klasse | Bestehende Skills (Module unter `eltern-chat/skills/`) |
|---|---|
| **A** | `seiten_uebersicht`, `termine_erfragen`, `wuensche_zeigen` (Lese-Pfad), `ca_verteilung` (Lese-Hälfte) |
| **B** | `ca_verteilung` (Datei-Anhang via Skill), `einkauf_zeigen` (Button-Aufsatz; nach TASK-10c Form-(b)-Migration), RPS/GAN/PAS (Bilder-Album via TASK-10b) |
| **C** | `routine_punkte_setzen`, `gericht_anlegen`, `plan_aktivitaeten_setzen`, weitere schreibende mit Vorab-Confirm |
| **D** | `termin_eintragen`, `einkauf_hinzufuegen`, `foto_senden` (die drei A2-freigegebenen Skills) |
| **E** | `familie_anlegen`, `geraet_anlegen`, `kalender_verbinden`, `anbieter_wechseln`, `panel_anlegen` |

Welche Skills nach EC-33 als WebApp-Pendant entstehen (z. B.
Routine-Mini-App, Wünsche-Edit-App), gehört nicht in diese Tabelle —
sie sind ein eigenes Genre (Mini-App), siehe
`conventions/mini-app-design.md`.

## Wegweiser-Kasten

> **Diese Karte ist Indexseite.** Wenn du normative Aussagen suchst,
> bist du hier falsch — gehe in die Quelle:
>
> - **Verhalten der Familie** (was sie sieht, wie das Gate sichert) →
>   `specs/platform/eltern-chat.md` (EC-IDs)
> - **Wie ein Skill gebaut wird** (Klassen, Rückgabe-Formen, Tests) →
>   `conventions/tasks.md` (TASK-IDs)
> - **Wie eine Mini-App gebaut wird** (UI, Launcher,
>   Schreibverhalten) → `conventions/mini-app-design.md` (MAD-IDs)
> - **Wie eine Privatchat-Session aufgebaut ist** (Worker, Phasen) →
>   `conventions/privatchat-session.md` (SESS-IDs)
> - **Wie Skills datenseitig andere Buddies ansprechen** →
>   `conventions/data-components.md` (DCOMP-IDs) und
>   `conventions/apps.md` (APP-IDs)
>
> Eine Norm-Aussage in dieser Karte ist ein Fehler — bitte melden,
> nicht zitieren.
