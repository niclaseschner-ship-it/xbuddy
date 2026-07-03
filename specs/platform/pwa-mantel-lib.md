# PWA-Mantel-Lib — Spec     (ID-Präfix: PWML)

> Fundament-Track der Hörspiel-Player-Werft (2026-07-03). Baut die zentrale
> Code-Lib, die die ratifizierte Konvention `conventions/pwa-mantel.md`
> (PWAM-1..6, RAT 2026-07-01) implementiert. Erster sauberer Konsument =
> Hörspiel-Player-PWA (`specs/buddies/hoerspiel.md` HSP-47). Bezug: Epic #1265.

## Problem & North-Star-Bezug

Die vier heutigen PWA-Mantel-Konsumenten (einkauf, plan, heim-shell, connector)
tragen ihre Installations-Klempnerei als **Copy-Paste**: `seiten/main.py` trägt
dieselbe `build_id`-Ableitung dreifach (`_current_build_id`, `_plan_einst_build_id`,
`_shell_build_id`) und dieselbe `__BUILD_ID__`-Substitution im Service-Worker
dreifach (`_read_*_with_build_id`). PWAM-5 fordert eine **zentrale Registry +
Lib** („ein neuer Mantel wird registriert, nicht geforkt") — der Code tut es
noch nicht. Ein fünfter Konsument (der neue Hörspiel-Player) würde die
Duplizierung ein viertes Mal rollen. Diese Spec baut die Lib **einmal**, mit dem
Player als erstem Kunden.

**North-Star:** Einfachheit (Constitution Nr. 2) — eine Quelle für Manifest,
Service-Worker und Cache-Buster statt n Kopien.

## Scope-Grenze (verbindlich)

**In Scope:** die Lib + Deduplizierung der Server-Helfer in `seiten/main.py` +
der Player als erster Konsument über die Lib.

**Außerhalb Scope (→ Epic #1265 Folge):** die **Voll-Migration** der vier
Bestands-Konsumenten (einkauf, plan, heim-shell, connector) auf die Lib, inkl.
der bekannten connector-Drift (SVG- statt PNG-Icons PWAM-2, statisches
`BUILD='v1'` statt Server-Substitution PWAM-3). Die Bestands-Konsumenten bleiben
unverändert lauffähig; ihre Umstellung ist ein eigener Bau-Track im Epic. Diese
Spec **darf** die drei duplizierten Server-Helfer auf die Lib umstellen (das ist
reversibel und vom Konventions-Bau-Sequenz-Hinweis gedeckt), **muss** aber die
Bestands-Konsumenten dabei byte-verhaltensgleich lassen.

## Anforderungen

### PWML-1 — Zentrale Manifest-Erzeugung aus Registry
Die Lib (`seiten/pwa_mantel.py` o. ä.) stellt eine Funktion bereit, die aus
einem **Registry-Eintrag** (`component → config`, PWAM-5) das Web-App-Manifest-
JSON erzeugt: `name`, `short_name`, `start_url`, `display`, `scope`, `theme_color`,
`background_color` und **Icons 192/512 + maskable als PNG** (PWAM-2). Die
manifest-tragenden Felder sind **Per-App-Daten aus der Registry**, nicht im Code
hartkodiert.

**Wenn** ein Konsument-Eintrag ein SVG-Icon oder ein fehlendes 192/512/maskable-
PNG trägt, **dann** ist das ein **Boot-/Test-Fehler** (PWAM-2-Konformität), kein
stiller Durchlass.

### PWML-2 — Ein Service-Worker-Skelett mit zwei Config-Knöpfen
Alle Mäntel teilen **ein** `sw.js`-Skelett (PWAM-3). Genau **zwei** load-bearing
Config-Werte kommen aus der Registry: `HTML_CACHE_MODE` (Shell cacht HTML nicht,
connector schon) und `STOP_PREFIXES` (Pfade, die der Mantel-SW ignoriert, weil
eigene SWs zuständig sind — z. B. `/controller/`, `/display/`). Der Build-Marker
wird **server-seitig** als `__BUILD_ID__` substituiert — **kein** statisches
`const BUILD = 'v1'`.

### PWML-3 — `build_id` aus einem Source-SET (Multi-Source)
`build_id` = `max(mtime)` über ein **Set** von Quell-Dateien je Komponente
(PWAM-4), nicht über eine Einzeldatei. Gilt **sowohl** für die HTML-Route
**als auch** für die Service-Worker-Route (schließt die offene PWAM-4-Lücke, in
der die SW-Route noch Single-File-`build_id` nutzte).

**Wenn** eine der Quell-Dateien im Set sich ändert, **dann** ändert sich der
`build_id` und der Cache wird invalidiert.

### PWML-4 — Server-Helfer dedupliziert, Player als erster Konsument
Die drei duplizierten `build_id`-Helfer und die drei `__BUILD_ID__`-Substitutions-
Helfer in `seiten/main.py` werden durch **je einen** Lib-Aufruf ersetzt. Die
Bestands-Konsumenten (einkauf, plan, heim-shell, connector) bleiben dabei
**verhaltensgleich**. Der **Hörspiel-Player** (HSP-47) wird über die Lib
registriert und ausgeliefert — nicht durch eine vierte Kopie.

### PWML-5 — App-spezifischer Runtime-Cache-Hook (optional)
Das `sw.js`-Skelett lässt eine **optionale** app-spezifische Runtime-Cache-
Erweiterung zu (Hook/Import), ohne dass die App das Skelett forken muss —
Voraussetzung für den harten Folgen-Audio-Cache des Players (HSP-54). Der Hook
ist **optional**: Konsumenten ohne Erweiterung sind unberührt, die zwei
load-bearing Knöpfe (PWML-2) bleiben die einzigen Pflicht-Schalter. n=1 (Player)
— **keine** Vorrats-Generalisierung der Erweiterungs-Form.

### PWML-6 — Tests (ohne Netz)
- Registry-Eintrag → Manifest-JSON: Pflichtfelder gesetzt, Icons sind PNG in
  192/512/maskable (PWML-1).
- SW-Skelett-Rendering mit `HTML_CACHE_MODE`/`STOP_PREFIXES` deterministisch,
  `__BUILD_ID__` substituiert (PWML-2).
- `build_id` reagiert auf mtime **jeder** Datei im Source-Set, HTML- und
  SW-Route (PWML-3).
- Bestands-Konsumenten-Snapshot (einkauf/plan) vor↔nach Dedup byte-gleich
  (PWML-4).

## Entscheidungen

### E-PWML-1 — Lib statt vierte Kopie, aber keine Zwangs-Migration
Der Player triggert den Lib-Bau (n=„jetzt sinnvoll", Nic 2026-07-03: „erst Lib,
Player als 1. Kunde"). Die Bestands-Konsumenten migrieren **nicht** zwingend in
diesem Track — das hält den Blast-Radius klein und respektiert, dass die
Voll-Vereinheitlichung Epic-#1265-Arbeit ist (`conventions/pwa-mantel.md:32-36`
„Code-Konsolidierung ist ein Folge-Bau-Track").

### E-PWML-2 — Registry-Heimat = `seiten/views.json` erweitern
Kein zweiter Registry-Ort. `typ:pwa`-Einträge in `seiten/views.json` tragen
bereits `pwa{manifest,start_url,service_worker}` — die Lib liest daraus. (Falls
sich das im Bau als untragbar erweist, ist ein separater `pwa-registry.json`
der dokumentierte Fallback — Bau-Entscheidung.)

## Provenienz
Werft-Lauf 2026-07-03 (Hörspiel-Player-PWA), Fundament-Track A. Gate A/B durch.
Implementiert `conventions/pwa-mantel.md` (PWAM-1..6). Erster Konsument
`specs/buddies/hoerspiel.md` HSP-47. Bezug Epic #1265.
