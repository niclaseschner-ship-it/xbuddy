# Zugangsdaten-Speicher

V1-Implementierung der Spec [`specs/platform/zugangsdaten.md`](../../specs/platform/zugangsdaten.md). Refs #37, #211.

Der **eine** Per-Instanz-Speicher für die Geheimnisse einer XBuddy-Instanz —
KI-Anbieter-Key, Google-OAuth-Token und was später dazukommt. Statt dass jede
Komponente ihre eigene Geheimnis-Datei führt, lesen und schreiben alle über
dieses geteilte Modul (ZD-5).

Library im `tools/`-Genre (DCOMP-1, #211), nicht eine eigene Komponente —
analog [`tools/configloader.py`](../configloader.py) und
[`tools/logsetup.py`](../logsetup.py): kein eigener Prozess, kein Service,
kein HTTP-Endpoint (E-ZD-3).

## Nutzung

```python
from tools.zugangsdaten import Zugangsdaten, resolve_store_path

speicher = Zugangsdaten(resolve_store_path())   # Pfad nach ZD-8 aufgelöst

# Holen — None (oder ein eigener Default), wenn der Name nicht gesetzt ist.
key = speicher.get("ki-anbieter-key")
key = speicher.get("ki-anbieter-key", default="")

# Setzen — legt die Speicher-Datei bei Bedarf mit Rechten 0600 an.
speicher.set("ki-anbieter-key", "sk-...")
```

Eine Komponente importiert **nur** aus dem Paket `tools.zugangsdaten`, nie aus
internen Pfaden — und greift nie selbst auf die Datei zu (ZD-5, CLAUDE.md §6).

Ob eine Umgebungsvariable Vorrang vor dem Speicher hat, entscheidet die
aufrufende Komponente (typisch: Env > Speicher > Default, `eltern-chat.md`
EC-15). Der Speicher erzwingt **keine** Auflösungs-Reihenfolge — er liefert nur
die persistente Schicht (ZD-7).

## Speicher-Datei

| Aspekt | Verhalten | Spec |
|---|---|---|
| Ein Speicher je Instanz | genau eine Datei, hält die Geheimnisse aller Komponenten | ZD-1 |
| Benannte Werte | Paar aus stabilem Namen und Wert; keine feste Namensliste | ZD-2 |
| Dateirechte | `0600` — nur der Eigentümer liest/schreibt; beim Schreiben erzwungen | ZD-3 |
| Fehlende Datei | gilt als leerer Speicher, kein Fehler; reines Lesen legt nichts an | ZD-4 |
| Kaputte Datei | gilt als leerer Speicher, Warnung ohne Inhalt | ZD-4 / ZD-6 |
| Kein Klartext-Echo | Werte erscheinen nie in Log, Antwort oder Fehlermeldung | ZD-6 |

Die Datei ist pro Instanz separat und per Repo-`.gitignore` ausgeschlossen —
ein Geheimnis kann nie ins Repo gelangen (ZD-3, CLAUDE.md §8). V1 hält die
Werte im Klartext in der `0600`-Datei; eine Verschlüsselung im Ruhezustand ist
bewusst out-of-scope (OPEN-ZD-A, E-ZD-2).

## Konfiguration (ZD-8)

| Wert | Default | Override |
|---|---|---|
| Speicher-Datei | `tools/zugangsdaten/zugangsdaten.json` (neben dem Code) | `$ZUGANGSDATEN_STORE_FILE` · CLI `--zugangsdaten-file` |

Priorität: CLI > Env > Default. Eine Komponente, die den Speicher nutzt, kann
das Flag über `add_cli_argument(parser)` an ihren eigenen `ArgumentParser`
hängen.

## Dateien

- `store.py` — das geteilte Lese-/Schreib-Modul (ZD-5), Klasse `Zugangsdaten`.
- `config.py` — Pfad-Auflösung der Speicher-Datei (ZD-8).
- `__init__.py` — Public-API; Komponenten importieren nur hierüber.
- `zugangsdaten.example.json` — Format der Speicher-Datei. `zugangsdaten.json`
  selbst ist per Repo-`.gitignore` ausgeschlossen — pro Instanz separat.

## Tests

```bash
python3 -m pytest tests/tools/test_zugangsdaten.py -v
```

Tests liegen in `tests/tools/test_zugangsdaten.py` (analog
`tests/tools/test_configloader.py`). Ein Test je ZD-Requirement mit
Code-Verhalten (ZD-9), ohne Netz — der Speicher ist ein lokales Modul, kein
Dienst (E-ZD-3).
