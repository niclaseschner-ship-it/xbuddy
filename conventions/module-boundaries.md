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

- `wetter/` existiert noch nicht im Repo (PR #137, Wetter-Integration,
  offen) — es gibt nichts zu scannen; der Linter erfasst es daher nicht.
  Sobald #137 landet, wird `wetter` in `root_packages` aufgenommen.

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
`familie | geraete | plan | router` als unabhängige Mittelschicht).

### MOD-2 — Services sind voneinander unabhängig
`familie`, `geraete`, `plan` und `router` importieren keinen
Python-Code voneinander. Wer Daten einer anderen Komponente braucht,
ruft sie über HTTP (DCOMP-1), nicht per Import.

import-linter-Contract `independence` über die vier Service-Module.

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

## eltern-chat und der Bindestrich

`eltern-chat` ist wegen des Bindestrichs kein importierbares
Python-Paket (kein `__init__.py`, paketloses `main.py`; siehe
`pytest.ini`, Refs #52). grimp scannt das Verzeichnis trotzdem vom
Dateisystem — die Module heißen `eltern-chat.*` —, sodass `eltern-chat`
als `source_modules`/`forbidden_modules` in Contracts erfassbar bleibt,
**ohne** Rename. Empirisch verifiziert mit import-linter 2.11 / grimp
3.14 (Refs #123).
