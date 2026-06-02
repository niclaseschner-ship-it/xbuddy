# Icon-Bibliothek — Spec     (ID-Präfix: ICONS)

Eine zentrale, geteilte Bibliothek von ARASAAC-Piktogrammen für die ganze
Instanz. Heute zieht KIBuddy seine Piktogramme aus einem eigenen Cache; das
App-Panel (`app-panel.md`, #136) braucht dieselben Grafiken für seine
Kacheln. Statt jeder App einen eigenen Vorrat zu geben, liefert die
Plattform **eine** Icon-Wurzel, die alle Apps read-only über eine stabile
URL nutzen. Die Bibliothek besitzt keine Familien-Logik — sie ist reine
Asset-Auslieferung.

Die Assets selbst sind **Per-Instanz-Daten**, nicht Code: sie sind groß
(~176 MB, 13 779 PNGs — gemessen am vorhandenen KIBuddy-Cache
`/home/buddy/apps/kibuddy/static/pictograms/`, Stand 2026-06-02) und liegen
daher außerhalb von git, an einem konfigurierbaren Ort (analog zum
Server-Zertifikat, das auch außerhalb des Repos lebt — `conventions/urls.md`
URL-11). Das Repo liefert nur die Konvention, das Seed-Skript und die
Serving-Konfiguration.

## ICONS-1 — Ordner-Konvention der Icon-Wurzel

Die Icon-Wurzel (`icon-root`) ist ein Verzeichnis mit je einem Unterordner
pro Bildquelle. Für ARASAAC gilt:

```
<icon-root>/
  arasaac/
    <id>.png          # ein PNG je ARASAAC-Piktogramm-ID
  pictogram_cache.json # Wort→ID-Mapping (siehe ICONS-3)
```

Eine Datei heißt `<id>.png`, wobei `<id>` die numerische ARASAAC-Piktogramm-ID
ist (z. B. `2239.png`). Die Quelle steckt im Unterordner-Namen (`arasaac/`),
damit später weitere Quellen ohne ID-Kollision danebenstehen können.

## ICONS-2 — icon-root ist per-Instanz konfigurierbar, nicht im git

Der Pfad der Icon-Wurzel ist pro Instanz konfigurierbar; Default ist
`/home/buddy/apps/icons/`. Die Wurzel und ihr Inhalt liegen **nicht** im
Repo (kein PNG, kein `pictogram_cache.json` wird committet) — sie ist
Per-Instanz-Daten wie das Server-Zertifikat (`conventions/urls.md` URL-11)
oder die `config.json` einer Komponente (`conventions/config.md` CONFIG-1).

| Wert | Default | Override | gesetzt durch |
|---|---|---|---|
| `icon-root` | `/home/buddy/apps/icons/` | Arg `$1` oder ENV `ICON_ROOT` beim Seed (ICONS-4); Router-Config `icon_root` beim Serving (ICONS-5, `router.md` ROU-26) | Instanz-Betreiber (Ops) beim Ausrollen |

## ICONS-3 — Wort→ID-Mapping wandert mit

Neben den PNGs liegt `pictogram_cache.json` in der Icon-Wurzel: ein
JSON-Objekt, das deutsche Wörter auf ARASAAC-IDs abbildet
(`{ "biene": 2239, … }`). Es stammt aus dem vorhandenen KIBuddy-Cache
(`/home/buddy/apps/kibuddy/pictogram_cache.json`) und wird vom Seed-Skript
(ICONS-4) mit den PNGs zusammen in die Wurzel gelegt. Konsumenten, die von
einem Wort zur Grafik kommen wollen (z. B. ein späterer Onboarding-Schritt,
der eine Kachel benennt), lesen dieses Mapping und bauen daraus die
Asset-URL (ICONS-5).

## ICONS-4 — Seed aus dem vorhandenen KIBuddy-Cache, idempotent

Das Seed-Skript `deploy/icons/seed-icon-library.sh` befüllt die Icon-Wurzel
aus dem **vorhandenen** KIBuddy-Cache — es kopiert die PNGs nach
`<icon-root>/arasaac/` und `pictogram_cache.json` in die Wurzel. Es holt
**nichts** von ARASAAC nach (kein Re-Fetch). Das Skript ist idempotent:
bereits vorhandene Zieldateien werden übersprungen, ein erneuter Lauf
kopiert nur Fehlendes.

Die Quelle (KIBuddy-Cache) und das Ziel (`icon-root`) sind per Arg/ENV
überschreibbar; Defaults sind der KIBuddy-Cache-Pfad bzw.
`/home/buddy/apps/icons/` (ICONS-2). Das Skript fasst **keinen**
KIBuddy-Code an — nur dessen Asset-Dateien.

Fehlende IDs später von `api.arasaac.org` nachzuladen ist bewusst **nicht**
implementiert (nichts auf Vorrat, CLAUDE.md §6); das Skript dokumentiert in
seinem Kopf, wie man eine einzelne ID bei Bedarf manuell nachzieht.

## ICONS-5 — Read-only-Auslieferung unter einer stabilen URL

Die Icon-Wurzel wird **read-only** unter einem stabilen Pfad ausgeliefert:

```
GET /display/_shared/icons/arasaac/<id>.png  →  200, image/png
```

Begründung der URL-Wahl:

- Sie sitzt unter dem Top-Level-Prefix `/display/` (`conventions/urls.md`
  URL-1) — kein neuer Top-Level-Pfad.
- Das Segment `_shared` folgt dem in `conventions/urls.md` URL-16
  definierten Namensraum für geteilte Display-Assets: Assets, die keinem
  einzelnen Buddy gehören, liegen unter `/display/_shared/<sache>/`.
  Die Icon-Bibliothek gehört keiner einzelnen App, daher `_shared` statt
  eines Buddy-Slugs (für buddy-eigene Assets gilt URL-13).
- Die Auslieferung übernimmt der **Router** als read-only-Asset-Pfad
  (`router.md` ROU-26) — ein Zwilling zu `/controller/_shared/` (ROU-23).

Anders als `controller/_shared/` (Helper-**Code** im Repo) zeigt dieser
Pfad auf die Per-Instanz-Icon-Wurzel (ICONS-2) außerhalb des Repos. Der
**Router** liefert diesen Prefix aus dem `icon-root` aus (`router.md`
ROU-26) — read-only, mit demselben Path-Traversal-Schutz wie ROU-23. Er
läuft als User `buddy` und liest die icon-root problemlos; ein erster
Versuch, die Wurzel per statischem nginx-`alias` auszuliefern, scheiterte
an der `0700`-Home-Permission (nginx = `www-data` ≠ `buddy`) und lieferte
404 (#135). In der Origin-Routing-Tabelle (URL-14) fällt
`/display/_shared/icons/` an den allgemeinen `/display/`→Router-Eintrag —
kein eigener statischer nginx-Block. Die konkrete Origin-Konfiguration
liegt in `deploy/nginx/xbuddy-origin.conf`.

`<id>` ist eine numerische ARASAAC-ID (ICONS-1). Andere `<source>` als
`arasaac` gibt es heute nicht; weitere Quellen kämen als
`/display/_shared/icons/<source>/<id>.<ext>` dazu.

## ICONS-6 — Lizenz

Die ARASAAC-Piktogramme stehen unter **CC BY-NC-SA**. Die NC-Klausel
(nicht-kommerziell) ist für ein kommerzielles XBuddy-Produkt **offen** und
muss vor einer kommerziellen Nutzung geklärt werden (vgl.
`xbuddy-knowledge/CONTEXT.md` zur Produktrichtung). Diese Spec dokumentiert
die Lizenz; sie entscheidet die kommerzielle Frage nicht.

## Folge-Punkt — KIBuddy-Migration

KIBuddy liest seine Piktogramme heute aus seinem eigenen Cache
(`/home/buddy/apps/kibuddy/static/pictograms/`). Dass KIBuddy künftig die
**zentrale** Icon-Wurzel (ICONS-2) statt des eigenen Caches liest, ist ein
**eigener Folge-PR** — nicht Teil dieser Spec. Bis dahin existieren beide
Kopien parallel; die zentrale Wurzel wird aus dem KIBuddy-Cache geseedet
(ICONS-4), nicht umgekehrt.

## Konsumenten

- **App-Panel** (`app-panel.md`, #136): bezieht Kachel-Grafiken über die
  URL aus ICONS-5. Erster Konsument der zentralen Bibliothek.
- **KIBuddy**: heute eigener Cache, Migration als Folge-PR (s. o.).
