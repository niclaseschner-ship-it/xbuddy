# Geräte-Registry

V1-Implementierung der Spec [`specs/platform/geraete.md`](../specs/platform/geraete.md). Refs #105.

Die zentrale Liste der Geräte einer Familie — Tablets, Handys, Monitore und
das Pi-Display — mit stabiler `display_id`, Typ, Auflösung, OS, Verwendung
(`display`/`controller`/`beides`) und Status (`aktiv`/`inaktiv`). Eine Instanz
beschreibt genau eine Familie (GER-1). Die Registry besitzt diese Daten und
stellt sie über eine Schnittstelle bereit (GER-5/GER-6); Konsumenten (Router
ROU-18, Display-Client DC-1, CA-Verteilung #82) sind Nutzer, kein eigenes
Geräte-Modell.

## V1-Scope

Genau **Geräte-Identität** — die Datei (GER-4), die Lese-Schnittstelle
(GER-5), die race-freie Schreib-Schnittstelle (GER-6), die `display_id`-
Vergabe (GER-7). Out-of-Scope: Editor über UI/Eltern-Chat (OPEN-GER-A),
Health-Monitoring (OPEN-GER-B), Telemetrie (OPEN-GER-C). Die Anbindung der
Konsumenten (Router, Display-Client, CA-Verteilung) und die Eltern-Chat-
Funktion „Gerät anlegen" (GAA, #106) wandern in eigene Tickets — diese
Lieferung ist nur die Registry selbst.

## Public-API

```python
from geraete import (
    Geraet, Registry, RegistryError,
    TYPEN, VERWENDUNGEN, OS_WERTE, STATUS_WERTE,
    load, save, neue_id, slugify,
)

reg = load("geraete/geraete.json")          # GER-4: leer + Warnung, wenn die Datei fehlt
reg.get("tablet-elias-01")                  # GER-5: ein Gerät je id; None bei unbekannt
reg.list_all()                              # GER-5: alle Geräte (aktiv + inaktiv)
reg.list_by_verwendung("display")           # GER-5: display + "beides"
neu_id = neue_id(reg, "tablet", "Wohnzimmer")  # GER-7: kollisionsfrei `<typ>-<slug>-<nn>`
reg.add(Geraet(neu_id, "tablet", "Tablet Wohnzimmer",
               {"w": 2560, "h": 1600}, "android", "display", "aktiv"))
reg.update("tablet-elias-01", name="Tablet Elias (Schreibtisch)")  # GER-6
reg.deactivate("tablet-elias-01")           # GER-6: setzt status auf inaktiv
save(reg, "geraete/geraete.json")           # GER-6: atomar, 0600
```

Konsumenten importieren **nur** aus `geraete` (Paket-Public-API), nicht aus
`geraete.registry` — einseitige Abhängigkeiten (CLAUDE.md §6).

## Daten je Instanz

`geraete.json` liegt neben dem Code, ist per Repo-`.gitignore` ausgeschlossen
und trägt Eigentümer-Rechte 0600 — analog `tools/zugangsdaten/zugangsdaten.json`
(ZD-3) und `eltern-chat/onboarding-store.json` (ONB-5). `geraete.example.json`
in diesem Verzeichnis dokumentiert das Format.

V1 wird die Datei manuell gepflegt oder über die Schreib-Schnittstelle aus
Konsumenten (Eltern-Chat „Gerät anlegen" GAA, #106) ergänzt. Ein UI ist
ausdrücklich Out-of-Scope (OPEN-GER-A).

## Konfiguration (GER-9)

Familienspezifische Werte leben in `geraete.json`. Der Pfad zur Registry-
Datei selbst kann nicht in der Datei stehen und bleibt deshalb Env/CLI:

| Wert            | Default                         | Quelle                                            |
|-----------------|---------------------------------|---------------------------------------------------|
| Registry-Datei  | `geraete.json` neben dem Code   | Env (`GERAETE_REGISTRY`) · CLI (`--geraete`)      |

V1 löst die Pfad-Konvention erst auf, sobald ein Konsument sie braucht —
hier liegt nur die `load(path)` / `save(registry, path)`-Schnittstelle. Die
Konsumenten-Tickets bringen den ENV-/CLI-Lader analog `familie/main.py` mit.

## `display_id`-Schema (GER-7)

```
<typ>-<slug>-<nn>
```

- `<typ>` aus `TYPEN` (`tablet`, `handy`, `monitor`, `pi-display`)
- `<slug>` Kleinbuchstaben, Bindestrich-getrennt, ohne Sonderzeichen
  (Umlaute → `ae`/`oe`/`ue`/`ss`); aus `name` über `slugify(name)`
- `<nn>` zweistellig, je `<typ>-<slug>`-Kombination beginnend bei `01`;
  `neue_id(registry, typ, name)` sucht den nächsten freien Wert

Eine einmal vergebene `id` wird nie neu vergeben — auch nicht für deaktivierte
Geräte (`is_aktiv()=False`). Die Identität bleibt stabil (URL-8 sinngemäß).

## Dateien

- `registry.py` — Geräte-Modell (GER-3), Validierung, Laden (GER-4),
  Lese-Schnittstelle (GER-5), Schreib-Schnittstelle (GER-6), `neue_id`/`slugify`
  (GER-7).
- `__init__.py` — Public-API (was Konsumenten importieren).
- `geraete.example.json` — Format der Registry-Datei.
- `tests/test_registry.py` — ein Test je GER-Requirement (GER-10).

## Tests

```bash
python3 -m pytest geraete/tests/ -v
```

Ohne Netz, ohne externes Setup — `tmp_path` als Sandbox. Race-frei wird
demonstriert über zwei Aspekte: (a) `save` legt die Temp-Datei mit `os.open`
und 0600 an, gefolgt von `os.replace` (atomarer Rename); (b) ein simulierter
Schreib-Abbruch hinterlässt weder eine halbe Zieldatei noch eine verwaiste
Temp-Datei.
