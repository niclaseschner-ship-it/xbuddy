# Modul-Grenzen — Konvention     (ID-Präfix: MOD)

XBuddy-Komponenten laufen als getrennte Prozesse (SVC-1) und hängen
einseitig voneinander ab: keine Zyklen, eine explizite Public-API je
Modul (CLAUDE.md §6, „klare Modul-Grenzen, einseitige Abhängigkeiten").
Diese Konvention schreibt das **maschinell prüfbar** fest — als
import-linter-Contracts in `.importlinter`, die `make lint` und die CI
bei jedem PR ausführen.

## Das Layer-Modell

Drei Schichten, Abhängigkeiten fließen nur abwärts:

```
   eltern-chat                  (oben — orchestriert, ruft Skills)
   ───────────────────────────
   familie · geraete · plan · router   (Mitte — Services, unabhängig)
   ───────────────────────────
   tools/                       (unten — geteilte Library, kein Prozess)
```

- **tools/** (`configloader`, `logsetup`, `zugangsdaten/`) ist die
  unterste Schicht: prozesslose Bibliothek, importiert nichts darüber
  (DCOMP-1).
- Die **Services** in der Mitte importieren nur abwärts in `tools/` und
  sind untereinander unabhängig — Service↔Service läuft über HTTP
  (urllib), nicht über Python-Import (DCOMP-1).
- **eltern-chat** liegt oben: es darf `tools/` nutzen, wird aber von
  keiner anderen Komponente importiert.

## Was der Linter NICHT prüft

import-linter erfasst ausschließlich **Python-Importe**. Die
Service↔Service-Kommunikation über HTTP (DCOMP-1) ist kein Import und
damit hier nicht maschinell prüfbar — diese Kante bleibt eine
Konvention.

**Scan-Reichweite und Ausnahmen:**

- `wetter/` ist ein vollwertiges Buddy-Modul (analog `plan/`); Code liegt auf
  main (#137 — Wetter-Buddy-Integration). `wetter` wird wie `plan` in
  `root_packages` erfasst und unterliegt denselben Layer-Contracts (MOD-1..5).

- **Paket-interne Tests** (z. B. `familie/tests/`, `tools/tests/`) liegen
  innerhalb der `root_packages` und werden von grimp mit-gescannt. Sie
  halten dieselben Grenzen ein und müssen das auch — ein Test, der die
  Architektur verletzt, ist selbst ein Befund.

- **Top-Level-`tests/`** (z. B. `tests/tools/test_zugangsdaten.py`) liegt
  *außerhalb* der `root_packages` und wird von grimp **nicht erfasst**.
  Dort lebt bewusst Whitebox-Introspektionstest ZD-9, der
  `tools.zugangsdaten.store` und `tools.zugangsdaten.config` direkt
  importiert — das ist kein Produktiv-Pfad und daher legitim ausgenommen.
  Diese Ausnahme ist explizit, nicht versehentlich.

## Die Contracts als Bauregeln

### MOD-1 — Layer-Modell: eltern-chat → Services → tools
Abhängigkeiten fließen nur abwärts: `eltern-chat` darf die Services und
`tools/` importieren, die Services dürfen `tools/` importieren, `tools/`
importiert nichts darüber. Keine Schicht greift nach oben.

import-linter-Contract `layers` (Reihenfolge oben→unten;
alle Service-Module als unabhängige Mittelschicht; deren aktuelles
Verzeichnis unter `root_packages` in `.importlinter` erfasst).

### MOD-2 — Services sind voneinander unabhängig
Alle Service-Module importieren keinen Python-Code voneinander. Wer Daten
einer anderen Komponente braucht, ruft sie über HTTP (DCOMP-1), nicht per
Import. Das aktuelle Verzeichnis aller Service-Module unter `root_packages`
wird in `.importlinter` erfasst (s. Linter-Scan-Reichweite oben).

import-linter-Contract `independence` über alle Service-Module.

### MOD-3 — tools importiert keine Komponente darüber
`tools/` ist die unterste Schicht und importiert weder `eltern-chat`
noch einen der Services. Sonst entstünde ein Zyklus (Service → tools →
Service) und `tools/` wäre nicht mehr eigenständig nutzbar.

import-linter-Contract `forbidden` (source `tools`, forbidden alle
Komponenten).

### MOD-4 — eltern-chat wird von keiner Komponente importiert
`eltern-chat` ist die oberste Schicht. Kein Service und kein `tools/`-
Modul importiert daraus — der Orchestrator kennt seine Bausteine, nicht
umgekehrt.

import-linter-Contract `forbidden` (source alle Komponenten außer
eltern-chat, forbidden `eltern-chat`).

### MOD-5 — zugangsdaten nur über die Public-API
Andere Komponenten importieren aus `tools.zugangsdaten` **nur** das
Paket selbst (`from tools.zugangsdaten import …`), nie aus internen
Pfaden `tools.zugangsdaten.store` oder `tools.zugangsdaten.config`. Das
ist die maschinelle Absicherung von ZD-5 („geteiltes Modul als einziger
Zugang"); die Public-API steht im `__all__` von
`tools/zugangsdaten/__init__.py`.

import-linter-Contract `forbidden` mit `allow_indirect_imports = True`,
damit die legitime Re-Export-Kette des Pakets selbst (`__init__` →
`.store`/`.config`) nicht fälschlich als Verstoß gilt; gefangen werden
nur **direkte** Importe der internen Module von außen.

### MOD-6 — keine sys.path-Manipulation auf fremdes eltern-chat
Keine Komponente außerhalb von `eltern-chat/` macht `sys.path.insert`
oder `sys.path.append` auf das `eltern-chat/`-Verzeichnis. Das umginge
MOD-4 (eltern-chat wird von keiner Komponente importiert), weil
import-linter sys.path-Manipulation nicht prüft — statische Imports
lösen wegen des Bindestrichs nach top-level (`import init_data` statt
`from eltern-chat import init_data`), nicht in den eltern-chat-Namespace.
Empirisch belegt: `lint-imports` läuft trotz dieser Imports sauber durch.

Eltern-chat-eigene Stellen (in `eltern-chat/` selbst, z.B. Test-conftests
mit `_ELTERN_CHAT = os.path.dirname(__file__)`) sind KEIN MOD-4-Bruch
und vom Gate ausgenommen.

Maschinelle Durchsetzung über einen zweiten CI-Step in
`.github/workflows/lint-imports.yml`: zweistufiger Datei-Check (Datei
enthält `sys.path.`-Manipulation UND String `"eltern-chat"`/`'eltern-chat'`
irgendwo) + Eigen-Verzeichnis-Filter (`eltern-chat/*` übersprungen) +
Bestand-Allowlist + Veraltete-Allowlist-Check (Allowlist-Einträge ohne
aktuellen Match müssen entfernt werden — zwingt Sanierungs-PRs zum
gleichzeitigen Allowlist-Update). Der zweistufige Datei-Check fängt
auch Drift-Pfade, die ein zeilen-basierter Grep verfehlt: Single-Quote-
Strings, `sys.path += [...]`-Augmented-Assignment, neutrale Variablen-
Namen mit String-Definition in vorheriger Zeile.

**Bestandsausnahme (Allowlist im CI-Workflow):** seit T1015 leer.
Cluster-A-Option-B (ratifiziert 2026-06-18-1720 watchdog-meta-cluster) hat
`eltern-chat/init_data.py` nach `tools/initdata/` gehoben und einen
gemeinsamen `tools/familie_client.py` eingeführt; die vier Service-`main.py`
(essen, hoerspiel, routine, seiten) importieren jetzt aus `tools.initdata`
statt per sys.path-Hack aus eltern-chat. Die vier `seiten/tests/test_*.py`
ziehen die Lib ebenfalls aus `tools.initdata` und brauchen keinen
eltern-chat-Insert mehr. Die Allowlist im CI-Workflow ist auf den leeren
String reduziert; jeder neue sys.path-Insert auf eltern-chat wird vom Gate
sofort gefangen.

**Scope-Grenze:** MOD-6 greift heute nur auf `eltern-chat`-Insert. Wenn
ein anderes sys.path-Cross-Component-Pattern auftaucht (Insert auf
andere Service-Verzeichnisse), ist das n=2 → eigene Berater-Runde,
MOD-6 erweitern. Keine antizipative Generalisierung.

## eltern-chat und der Bindestrich

`eltern-chat` ist wegen des Bindestrichs kein importierbares
Python-Paket (kein `__init__.py`, paketloses `main.py`; siehe
`pytest.ini`, Refs #52). grimp scannt das Verzeichnis trotzdem vom
Dateisystem — die Module heißen `eltern-chat.*` —, sodass `eltern-chat`
als `source_modules`/`forbidden_modules` in Contracts erfassbar bleibt,
**ohne** Rename. Empirisch verifiziert mit import-linter 2.11 / grimp
3.14 (Refs #123).
