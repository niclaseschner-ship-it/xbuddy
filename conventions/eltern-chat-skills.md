# Eltern-Chat-Skill Bauplan (Lego-Karte)

> Wegweiser, kein Normativ-Speicher. Alle Norm-Aussagen leben in den
> zitierten Quellen.

Die Eltern-Chat-Skills (Stand 2026-07-03) werden hier nach **Fähigkeiten**
beschrieben, nicht nach exklusiven Klassen. Wer einen neuen Skill baut
oder einen bestehenden anfasst, liest sein **Fähigkeits-Profil** in der
Tabelle ab und folgt der Lese-Reihenfolge der Bauplan-Anker, die zu den
„ja"-Spalten gehören. Diese Datei vergibt **keine eigenen** Norm-IDs
(kein `ECS-N`-Präfix); sie ist Indexseite, nicht zweite Wahrheit.

Grund für die Karte: Ohne sie lebt ein Skill-Autor in mehreren Dateien
gleichzeitig (`specs/platform/eltern-chat.md`, `conventions/tasks.md`,
`conventions/mini-app-design.md`, `conventions/privatchat-session.md`).
Die Karte gibt jedem Skill ein eindeutiges Profil.

**Pivot von Klassen-Tabelle zur Capability-Karte (#842, 2026-06-15).**
Die ursprüngliche A/B/C/D/E-Klassen-Tabelle war drift-anfällig — z. B.
stand `panel_anlegen` gleichzeitig in Klasse C und Klasse E, weil seine
A2-Eignung von der Anfrage abhing (Confirm-Phase + Auth-Loop). Die
Capability-Karte beschreibt **orthogonale Fähigkeiten** statt exklusive
Klassen; Skills mit gemischtem Profil (z. B. `termin_eintragen`, das
mal A2-direkt, mal Worker-Confirm läuft) fallen ohne Doppelnennung rein.
Die alten Klassen-Buchstaben werden als **Spalten-Gruppen** beibehalten,
damit Bestands-Verweise lesbar bleiben (Klasse A = pure-Read, Klasse C =
zweistufig-Confirm, Klasse D = A2-Sofort-Write, Klasse E = Auth-Loop).

## Capability-Karte

Sechs Fähigkeits-Achsen pro Skill:

| # | Achse | Werte | Heimat-Bauplan |
|---|---|---|---|
| **1** | **Schreibt Daten?** | nein / ja | TASK-3 (lesend) / TASK-4 (zweistufig) / TASK-9 (sofort) |
| **2** | **Schreib-Pfad** | — / zweistufig (EC-10 Confirm) / sofort (EC-10 A2) | TASK-4 / TASK-9 + A2-Klausel |
| **3** | **Anstoß-Vollständigkeit** | One-Shot (alle Pflicht-Felder im Anstoß) / Mehrstufig (Worker fragt nach) | TASK-3/4 / TASK-5 + SESS |
| **4** | **Ressourcen-Anzahl pro Akt** | — / 1 / N | EC-10 A2 Receipt-Multi-Item |
| **5** | **Inverse-Vertrag** | — / kein / idempotentes DELETE pro Ressource | EC-10 A2 Bedingung 2 |
| **6** | **Präsentations-Form** | reiner String / Anhang + String / Button-/WebApp-Aufsatz | TASK-10c Form (a)/(b)/(c) |

**Zwei Skills können dasselbe Profil haben** und teilen den Bauplan;
zwei Profile mit unterschiedlicher Belegung sind unterschiedliche Skills.

## Heutige Skills nach Profil (Stand 2026-07-03)

| Skill | (1) schreibt | (2) Schreib-Pfad | (3) Anstoß | (4) Ressourcen | (5) Inverse | (6) Form | Alt-Klasse |
|---|---|---|---|---|---|---|---|
| `seiten_uebersicht` | nein | — | One-Shot | — | — | Button-Aufsatz | B |
| `termine_erfragen` | nein | — | One-Shot | — | — | String | A |
| `wuensche_zeigen` | nein | — | One-Shot | — | — | String | A |
| `routine_punkte_lesen` | nein | — | One-Shot | — | — | String | A |
| `essen_katalog_lesen` | nein | — | One-Shot | — | — | String | A |
| `faehigkeiten_zeigen` | nein | — | One-Shot | — | — | String | A |
| `ca_verteilen` | nein | — | One-Shot | — | — | Anhang + String | B |
| `einkauf_zeigen` | nein | — | One-Shot | — | — | Button-Aufsatz | B |
| `routine_anpassen_oeffnen` | nein | — | One-Shot | — | — | Button-Aufsatz | B |
| `hoerspiel_oeffnen` | nein | — | One-Shot | — | — | Button-Aufsatz | B |
| `wetter_regeln_oeffnen` | nein | — | One-Shot | — | — | Button-Aufsatz | B |
| `gericht_anlegen` | ja | zweistufig | One-Shot oder Mehrstufig | 1 | kein | String | C |
| `plan_aktivitaeten_setzen` | ja | zweistufig | One-Shot oder Mehrstufig | 1 | kein | String | C |
| `routine_punkte_setzen` | ja | zweistufig | One-Shot oder Mehrstufig | 1 | kein | String | C |
| `routine_zeiten_setzen` | ja | zweistufig | One-Shot | 1 | kein | String | C |
| `hoerspiel_folge_erzeugen` | ja | zweistufig | One-Shot | 1 | kein | String | C |
| `essen_foto_setzen` | ja | zweistufig | One-Shot | 1 | kein | String | C |
| `gericht_loeschen` | ja | zweistufig (Drei-Phasen-Klausel) | Mehrstufig (3 Phasen: liste → auswaehlen → loeschen) | N | DELETE da | String | C |
| `kibuddy_aufnahme_quelle_setzen` | ja | zweistufig | One-Shot | 1 | kein | String | C |
| `kibuddy_prompt_anpassen` | ja | zweistufig | One-Shot oder Mehrstufig (sokratischer Dialog, KPA-4) | 1 | kein | String | C |
| `foto_senden` | ja | **sofort (A2)** | One-Shot | 1 | DELETE da | String | D |
| `einkauf_hinzufuegen` | ja | **sofort (A2)** | One-Shot | N | DELETE da | String | D |
| `termin_eintragen` | ja | **sofort (A2)** oder **zweistufig** je Anstoß | **gemischt**: One-Shot oder Mehrstufig | 1 | **kein** (Plan-Buddy hat keinen DELETE — `specs/platform/termin-eintragen.md:44-47`) | String | D + E |
| `familie_anlegen` | ja | Auth-Loop | Mehrstufig (Worker) | 1 | — (Profil-Identität) | String | E |
| `geraet_anlegen` | ja | Auth-Loop | Mehrstufig (Worker) | 1 | — | String | E |
| `kalender_verbinden` | ja | Auth-Loop | Mehrstufig (Worker) | 1 | — | String | E |
| `anbieter_wechseln` | ja | Auth-Loop | Mehrstufig (Worker) | 1 | — | String | E |
| `panel_anlegen` | ja | zweistufig + Worker-Identität | Mehrstufig (Worker) | 1 | — | String | C + E |
| `termine_aus_bild` | ja | **Mehrfach** (Worker-Sammler) | Mehrstufig (Worker) | N | **kein** (Plan-Buddy DELETE-Lücke) | String | E (mit Sammel-Eigenschaft) |

### Was die Karte über Drift-Befunde sagt

- **`termin_eintragen` (Alt-Klassen D + E):** ist im Profil GEMISCHT. Bei vollständigem Anstoß A2-direkt, bei unvollständigem Worker-Confirm. **Spec-Bruch:** EC-10:480 listet TES als A2-freigegeben, A2-Bedingung 2 (idempotentes DELETE) ist mangels Plan-Buddy-DELETE-Endpunkt mechanisch **nicht** erfüllt (Profil-Achse 5 = „kein"). Folge-Klärung: entweder Plan-Buddy DELETE bauen (eigenes Folge-Ticket) oder TES vollständig auf zweistufig migrieren — die Capability-Karte zeigt beide Pfade ohne TES in zwei Klassen zu doppeln.
- **`panel_anlegen` (Alt-Klassen C + E):** schreibt einen Panel-Eintrag (zweistufig-Confirm) UND führt eine Auth-Identitäts-Etablierung (Worker). Profil-Achse 3 zeigt Mehrstufig, Profil-Achse 6 = String. Kein Klassen-Doppel mehr.
- **`einkauf_hinzufuegen` (Alt-Klasse D, A2 mit Multi-Item):** Profil-Achse 4 = N (mehrere Ressourcen pro Schreibakt). EC-10-Receipt-Naht (#841 Welle 2) muss Multi-Item-Inverse tragen.
- **`termine_aus_bild` (Alt-Klasse E mit Sammel-Eigenschaft):** Worker-Sammler mit Mehrfach-Ressourcen, ohne DELETE. Profil zeigt: weder reines A2 noch reine Klasse-E. Korrektur-Pfad für TAB läuft in Welle 3 über Welle-3-Korrektur-Dialog vor dem `ja`, nicht über Receipt-`falsch` danach.

## Reihenfolge pro Profil-Cluster

Die Capability-Karte zerlegt Skills in orthogonale Fähigkeiten — der
Lese-Pfad für den **Bauplan** folgt aber natürlichen Profil-Clustern.
Die folgenden Cluster decken alle heutigen Skills ab; ein Skill mit
gemischtem Profil liest **beide** zugehörigen Cluster (z. B.
`termin_eintragen`: Cluster D für den A2-Pfad + Cluster E für den
Worker-Fallback). Die alten Klassen-Buchstaben (A/B/C/D/E) bleiben
als Cluster-Namen, weil viele Bestands-Verweise sie zitieren.

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
   erfüllt sein. **EC-10 A2-Receipt** („Kassenbon"): pro erfolgreichem
   Schreibakt eine `a2_receipts`-Zeile pro Ressource (Multi-Item:
   N Zeilen); Versiegelung durch Folge-Anfrage; nur Skills mit
   erreichbarem Inverse schreiben Bons.
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

## Bestehende Skills pro Cluster — wo finde ich Code-Beispiele

Diese Bestandsaufnahme bleibt erhalten als Code-Nachschlag (kein
Norm-Vertrag). Die **vollständige Profil-Belegung pro Skill** steht
oben in der Capability-Karte; diese Tabelle nennt nur die Skills, in
deren Modul man die Cluster-Bauformen am klarsten gebaut sieht.

| Cluster | Bestehende Skills (Module unter `eltern-chat/skills/`) |
|---|---|
| **A** Pure-Read | `faehigkeiten_zeigen`, `termine_erfragen`, `wuensche_zeigen`, `routine_punkte_lesen`, `essen_katalog_lesen` |
| **B** Read + Aufsatz | `ca_verteilen` (Datei-Anhang), `einkauf_zeigen` (Button-Aufsatz, TASK-10c Form-b), `routine_anpassen_oeffnen` (Türöffner-Skill, TASK-10c Form-b), `seiten_uebersicht` (Button-Aufsatz, TASK-10c Form-b), `hoerspiel_oeffnen` (Button-Aufsatz, TASK-10c Form-b), `wetter_regeln_oeffnen` (Button-Aufsatz, TASK-10c Form-b) |
| **C** zweistufig-Confirm | `routine_punkte_setzen`, `gericht_anlegen`, `plan_aktivitaeten_setzen`, `routine_zeiten_setzen`, `hoerspiel_folge_erzeugen`, `essen_foto_setzen`, `gericht_loeschen`, `kibuddy_aufnahme_quelle_setzen`, `kibuddy_prompt_anpassen` |
| **D** A2-Sofort-Write | `foto_senden` (Single-Item), `einkauf_hinzufuegen` (Multi-Item — Receipt mit N Zeilen) |
| **C+E** zweistufig + Auth-Identität | `panel_anlegen` (Confirm + Worker-Identität) |
| **E** Auth-Loop (Worker) | `familie_anlegen`, `geraet_anlegen`, `kalender_verbinden`, `anbieter_wechseln` |
| **D oder C, je Anstoß** (Mixed) | `termin_eintragen` (A2 bei vollständigem Anstoß, zweistufig + Worker sonst — kein DELETE-Vertrag, deshalb heute **nicht** im A2-Default trotz EC-10:480-Listing) |
| **Sammler-Worker (N Ressourcen, kein DELETE)** | `termine_aus_bild` (Mehrfach-Termine, Korrektur über Welle-3-Korrektur-Dialog vor `ja`) |

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
