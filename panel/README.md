# Panel-Registry

V1-Implementierung der Spec [`specs/platform/panel-registry.md`](../specs/platform/panel-registry.md). Refs #58.

Die zentrale Liste der App-Panel-Instanzen einer Familie — je Instanz stabile
`panel_id`, abgeleitete `source_id` (`app-panel:<panel_id>`), Display-Bindung
(`display_id`), Router-Origin (`router_url`, leer = same-origin) und die
getrennten Felder `config` (Tuning, PANEL-8) und `tiles` (Daten, PANEL-3). Eine
Instanz beschreibt genau eine Familie (PREG-1). Die Registry besitzt diese
Daten und stellt sie über eine HTTP-Schnittstelle bereit (PREG-13/14/15);
Konsumenten (Router PREG-9, Panel-Seite) sind Nutzer, kein eigenes Panel-Modell.

Schwester-Modell der Geräte-Registry ([`geraete/`](../geraete/), GER): eigener
Daten-Service, Per-Instanz-Datei, atomares Schreiben, Reload-on-Read,
Last-Known-Good. Der einzige Cross-Component-Teil ist die Display-Validierung
beim Anlegen (PREG-7).

## V1-Scope

Genau **Panel-Identität + Anlage**: die Datei (PREG-4), die Lese-Schnittstelle
(PREG-13/14, inkl. der `config.json`/`tiles.json`-Sichten), die race-freie
Schreib-Schnittstelle mit Display-Validierung (PREG-15/7), die `panel_id`-
Vergabe (PREG-6). Out-of-Scope (Welle 2): Kopieren/Löschen/Tile-Editing
(OPEN-PREG-A), Reconcile-Pfad (OPEN-PREG-B), Eltern-Chat-Skill (OPEN-PREG-C),
Tile-Sets/`geraet_id` (OPEN-PREG-D). Die Router-Anbindung (Proxy + Cache,
PREG-9/10) ist Track B — der `router.md`-Satellit.

## HTTP-API

| Methode | Pfad                                  | Requirement | Bedeutung |
|---------|---------------------------------------|-------------|-----------|
| GET     | `/api/v1/panels/`                     | PREG-13     | alle Panel-Instanzen als JSON-Array |
| GET     | `/api/v1/panels/<panel_id>`           | PREG-14     | ein Panel; unbekannt → 404 |
| GET     | `/api/v1/panels/<panel_id>/config.json` | PREG-14   | `config`-Feld als eigenständiges Dokument (Router proxyt, PREG-9) |
| GET     | `/api/v1/panels/<panel_id>/tiles.json`  | PREG-14   | `tiles`-Feld als eigenständiges Dokument (Router proxyt, PREG-9) |
| POST    | `/api/v1/panels/`                     | PREG-15     | Panel anlegen, atomar; Display-Validierung (PREG-7) |

`POST` erwartet `{slug, display_id, router_url?, config?, tiles?}` und liefert
die angelegte Instanz inkl. vom Server vergebener `panel_id` (PREG-6) und
abgeleitetem `source_id`. Fehlerfälle: fehlendes Pflichtfeld oder `display_id`
in der Geräte-Registry unbekannt (PREG-7) oder verschachteltes `query` in
`tiles` (PANEL-7) → **400**; Geräte-Registry nicht erreichbar oder Disk-
Schreibfehler → **503** (panels.json bleibt unverändert).

Konsumenten reden ausschließlich über HTTP, nicht über `import` (DCOMP-1).

## Daten je Instanz

`panels.json` liegt neben dem Code, ist per Repo-`.gitignore` ausgeschlossen und
trägt Eigentümer-Rechte 0600 — analog `geraete/geraete.json` (GER-4) und
`tools/zugangsdaten/zugangsdaten.json` (ZD-3). `panels.example.json` in diesem
Verzeichnis dokumentiert das Format. Fehlt die Datei beim Start, läuft der
Service mit leerer Panel-Liste weiter (PREG-4, kein Crash).

## `panel_id`-Schema (PREG-6, IDENT-1)

```
<slug>-<nn>
```

- `<slug>` Kleinbuchstaben, Bindestrich-getrennt, ohne Sonderzeichen
  (Umlaute → `ae`/`oe`/`ue`/`ss`); aus dem POST-`slug` über `slugify(slug)`.
  Anders als die `display_id` (GER-7) trägt die `panel_id` **kein** Typ-Präfix.
- `<nn>` zweistellig, je `<slug>` beginnend bei `01`; `neue_id(registry, slug)`
  sucht den nächsten freien Wert. „Zwei Controller fürs selbe iPhone" werden so
  `kueche-01`/`kueche-02`.

Eine einmal vergebene `panel_id` wird nie neu vergeben — die Identität bleibt
stabil (sie ist das `<id>`-Segment in `/controller/app-panel/<id>`, PANEL-2).

## Konfiguration (PREG-11)

Familienspezifische Werte (die Panels) leben in `panels.json`. Pfad und
Nachbar-Service-Adressen bleiben Env/CLI:

| Wert                 | Default                       | Quelle                                        |
|----------------------|-------------------------------|-----------------------------------------------|
| Registry-Datei       | `panels.json` neben dem Code  | Env (`PANELS_REGISTRY`) · CLI (`--panels`)    |
| Geräte-Registry-URL  | `http://127.0.0.1:5040`       | Env (`GERAETE_URL`) · CLI (`--geraete-url`)   |

Host/Port/Log-Level laufen über den gemeinsamen `tools.configloader` (CONFIG-1,
Datei `panel/config.json` + ENV `PANEL_LISTEN_*`). Der Loopback-Port ist fest
**5041** (PORT-2 Plattform-Port, kein Buddy-Reserveblock 5050-5099).

## Dateien

- `registry.py` — Panel-Modell (PREG-3), Validierung, Laden (PREG-4),
  Lese-/Schreib-Schnittstelle, `neue_id`/`slugify` (PREG-6).
- `main.py` — Flask-App (PREG-13/14/15), Display-Validierung (PREG-7),
  Entrypoint (PREG-11).
- `__init__.py` — Public-API (was Konsumenten importieren).
- `panels.example.json` — Format der Registry-Datei.
- `panel.service` — systemd-Unit (SVC-1/2/3/4, Port 5041).
- `tests/test_panel.py` — ein Test je verhaltenstragendem PREG-Requirement (PREG-12).

## Tests

```bash
python3 -m pytest panel/tests/ -v
```

Ohne Netz: die Geräte-Registry wird gestubbt (`display_existiert` ersetzt),
`tmp_path` ist die Disk-Sandbox.
