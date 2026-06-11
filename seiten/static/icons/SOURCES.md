# Sourcing-Tabelle für `seiten/static/icons/<typ>.png`

Diese Datei dokumentiert die Quelle und Lizenz jedes Bilds in diesem
Verzeichnis. Sie ist Pflicht-Bestandteil nach `specs/platform/seiten-registry.md`
SREG-12 V1.1 — **Bilder ohne SOURCES.md-Eintrag dürfen nicht committet
werden** (Pre-Merge-Probe).

Form je Eintrag:

- **Datei**: Datei-Name relativ zu diesem Verzeichnis
- **Quelle**: `arasaac:<id>` (für ARASAAC-Cache-Wurzel) ODER `eigen` (für
  selbst gezeichnete/gekaufte Datei mit Lizenz)
- **Cache-Wort**: Cache-Such-Wort, mit dem die ARASAAC-ID gefunden wurde
  (nur für `arasaac:*`)
- **Lizenz**: `CC BY-NC-SA` für ARASAAC, sonst die konkrete Lizenz mit
  Quell-URL
- **Hinzugefügt**: ISO-Datum (YYYY-MM-DD)

## Bestand

| Datei | Quelle | Cache-Wort | Lizenz | Hinzugefügt | Anmerkung |
|---|---|---|---|---|---|
| `controller.png` | `arasaac:11299` | „fernbedienung" | CC BY-NC-SA | 2026-06-11 | Symbol Fernbedienung — passt zur Sorte b/c (Controller). Initial-Bild war bereits aus ARASAAC, ID rekonstruiert. |
| `panel.png` | `arasaac:9165` | „tablet" | CC BY-NC-SA | 2026-06-11 | 2026-06-11 #585: ersetzt — alte Datei war byte-identisch zu controller.png (md5 bf92fa01b25aaaed49971153f44df5e1, Initial-Setup-Fehler). Neues Bild ist ARASAAC ID 9165 (md5 1a2ae639d3c8801e32bd7e70c06886c6, 500×500). |
| `eltern.png` | `arasaac:35060` | „eltern" | CC BY-NC-SA | 2026-06-11 | Symbol Eltern — passt zur Sorte b (Eltern-Settings). Initial-Bild aus ARASAAC, ID rekonstruiert. |
| `display-client.png` | `eigen` | — | siehe Anmerkung | 2026-06-11 | 8 KB-PNG, deutlich kleiner als die ARASAAC-Standardform (12-14 KB) → vermutlich custom/anders sourced. **Quelle bei Gelegenheit recherchieren oder durch eine ARASAAC-ID ersetzen** (z. B. `bildschirm:2910` für die generische Display-Variante). Heute mit Hinweis dokumentiert, keine Lizenz-Klärung blockiert. |

## ARASAAC-Cache-Verweis

Wer eine ARASAAC-ID nachschlagen oder ersetzen will, nutzt den lokalen Cache:

- ID-Dateien: `/home/buddy/apps/icons/arasaac/<id>.png`
- Wort→ID-Lookup-JSON: `/home/buddy/apps/icons/pictogram_cache.json`

Die ID ist eine Integer-Zahl (kein Padding) — siehe
`specs/platform/icons.md` ICONS-5 für die Cache-Wurzel-Form.

## Pflege

- Beim Hinzufügen eines neuen Fallback-Bilds: Zeile in der Bestand-Tabelle
  ergänzen, dann committen.
- Beim Ersetzen eines Bilds: Datums-Spalte fortschreiben, Anmerkung mit
  Hinweis (z. B. „ersetzt 2026-06-XX, alte ARASAAC-ID war …").
- Bei Quell-/Lizenz-Wechsel des Bestands (z. B. ARASAAC-Lizenz-Änderung):
  alle betroffenen Zeilen aktualisieren, im Commit dokumentieren.

Refs SREG-12 V1.1, #585.
