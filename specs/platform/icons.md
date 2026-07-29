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
| `icon-root` | `/home/buddy/apps/icons/` | Arg `$1` oder ENV `ICON_ROOT` beim Seed (ICONS-4); seiten-Config `--icon-root` / ENV `ICON_ROOT` beim Serving (ICONS-5, `router.md` ROU-26, `seiten-registry.md` SREG-18, RAT-31 E6f-B #1586) | Instanz-Betreiber (Ops) beim Ausrollen |

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
- Die Auslieferung übernimmt seit **RAT-31 E6f-B (#1586)** der
  **seiten-Service** als read-only-Asset-Pfad (`router.md` ROU-26,
  `seiten-registry.md` SREG-18) — ein Zwilling zu `/controller/_shared/`
  (ROU-23). Vorher war der Router der Host; Router-Code ist toter Zwilling
  bis #1568.

Anders als `controller/_shared/` (Helper-**Code** im Repo) zeigt dieser
Pfad auf die Per-Instanz-Icon-Wurzel (ICONS-2) außerhalb des Repos. Der
**seiten-Service** liefert diesen Prefix aus dem `icon-root` aus (`router.md`
ROU-26, `seiten-registry.md` SREG-18) — read-only, mit demselben
Path-Traversal-Schutz wie ROU-23. Er läuft als User `buddy` und liest die
icon-root problemlos; ein erster Versuch, die Wurzel per statischem nginx-`alias`
auszuliefern, scheiterte an der `0700`-Home-Permission (nginx = `www-data` ≠
`buddy`) und lieferte 404 (#135). In der Origin-Routing-Tabelle (URL-14) hat
`/display/_shared/icons/` einen **eigenen** spezifischen nginx-Block VOR dem
allgemeinen `/display/`→Router-Eintrag — Reihenfolge dokumentiert in
`deploy/nginx/xbuddy-origin.conf`.

`<id>` ist eine numerische ARASAAC-ID (ICONS-1). Andere `<source>` als
`arasaac` gibt es heute nicht; weitere Quellen kämen als
`/display/_shared/icons/<source>/<id>.<ext>` dazu.

## ICONS-6 — Lizenz

Die ARASAAC-Piktogramme stehen unter **CC BY-NC-SA**. Die NC-Klausel
(nicht-kommerziell) ist für ein kommerzielles XBuddy-Produkt **offen** und
muss vor einer kommerziellen Nutzung geklärt werden (vgl.
`xbuddy-knowledge/CONTEXT.md` zur Produktrichtung). Diese Spec dokumentiert
die Lizenz; sie entscheidet die kommerzielle Frage nicht.

## ICONS-7 — Stichwort-Suche über den lokalen Wort→ID-Cache

Konsumenten, die von einem **deutschen Stichwort** zu Piktogramm-Kandidaten
kommen wollen (z. B. der Routine-Punkte-Skill #354/RPS, ein späterer
Onboarding-Schritt — der Konsum-Fall, den ICONS-3 schon nennt), suchen über den
**schon vorhandenen** `pictogram_cache.json` (ICONS-3, Wort→ID): **read-only,
lokal, kein ARASAAC-Re-Fetch** — konsistent mit ICONS-4 („nichts auf Vorrat",
CLAUDE.md §6). Der Cache trägt einen breiten deutschen Wortschatz (Größenordnung
~15 000 Wörter auf ~10 000 IDs), die zugehörigen PNGs liegen lokal (ICONS-1) —
die Suche kommt damit **ohne Netz** aus und umgeht das Pi-IPv6-Egress-Blackhole.

`GET /api/v1/icons/suche?q=<stichwort>&max=<n>` liefert eine Liste **Kandidaten**
als JSON — `[{ "id": <arasaac-id>, "url": "/display/_shared/icons/arasaac/<id>.png" }]`:

- Gematcht wird `q` gegen die deutschen Wörter des Cache (Teilwort, case-
  insensitiv). Mehrere Wörter auf dieselbe ID ergeben **einen** Kandidaten
  (ID-dedupliziert).
- **Mehrwort-Eingabe (Whitespace in `q`):** der Cache-Match läuft pro Wort
  einzeln (Whitespace-Split, Tokens werden getrimmt, leere Tokens fallen raus).
  Treffer werden mit **OR-Logik** vereint und primär nach **`token_hits`**
  (Anzahl matchender Tokens) sortiert, sekundär nach Match-Score-Qualität
  (siehe Match-Score-Tabelle unten). Beispiel: `q=Brot schmieren` listet IDs,
  die sowohl „Brot" als auch „schmieren" matchen (`token_hits=2`), VOR IDs,
  die nur eines der beiden matchen (`token_hits=1`).
  Begründung: Eltern tippt 2–3-Wort-Routine-Punkte („Rucksack packen",
  „Brot schmieren") — Single-Wort-Substring-Match liefert systematisch null
  Treffer, weil die Kombinationen so im Cache nicht stehen.
- Zurückgegeben werden **nur** IDs, deren PNG in der icon-root vorliegt (ICONS-5)
  — jeder Kandidat rendert garantiert; IDs ohne lokales PNG fallen raus.
- `max` begrenzt die Trefferzahl. Default ist `3` (passend zum
  „3-Vorschläge"-Muster des RPS-Skills). Werte größer **`50`** werden still auf
  `50` geklemmt — Familienbot-Resilienz gegen versehentliches `?max=999999`.
  Nicht-numerische Werte (z. B. `?max=abc`) fallen still auf den Default zurück,
  kein 400. **Weitere** Vorschläge holt der Konsument durch eine **verfeinerte
  Anfrage** (anderes Stichwort/Synonym), nicht durch Paginierung — der Endpunkt
  bleibt zustandslos.
- Kein Treffer → **leere Liste**, kein Fehler.

**Match-Score (2026-06-15 Refactor, ICONS-7):**

Pro Token wird jedes Cache-Wort gegen den Token gescort:

| Stufe | Bedingung | Score |
|---|---|---|
| Exact match | Wort == Token (case-insensitiv) | 1000 |
| Prefix | Wort startet mit Token | 400 + Längen-Bonus |
| Word-Boundary mid-string | Wort enthält Space/Bindestrich + Token | 100 + Längen-Bonus |
| Reine Substring | Token kommt irgendwo im Wort vor | 1 + Längen-Bonus |
| Kein Match | Token nicht im Wort enthalten | 0 (ausgeschlossen) |

Längen-Bonus: `100 / len(Wort)` (bei Prefix) bzw. `50 / len(Wort)` (bei
Word-Boundary) und `1 / len(Wort)` (Substring) — kürzere Wörter ranken höher
(einfacher = bessere ARASAAC-Treffer; lange Multi-Wort-Konstrukte sind nicht
der typische Konsument-Treffer). Beispiel: q=Mensch → „menschen" (Prefix, 8
Zeichen, Score ≈ 412.5) gewinnt vor „mensch ärgere dich nicht" (Prefix, 26
Zeichen, Score ≈ 403.8) und vor „marsmensch" (Substring, Score ≈ 1.1).

**Multi-Token-Queries: Coverage schlägt Qualität.** Sortier-Reihenfolge ist
`(-token_hits, -score, first_seen)`. Wer mehr Tokens matcht (`token_hits`)
gewinnt immer — ein 2-Token-Substring-Treffer (token_hits=2) rankt vor einem
1-Token-Exact-Treffer (token_hits=1). Innerhalb derselben `token_hits`-Stufe
sortiert der additive Match-Score (Qualität: exact/prefix/word-boundary/substring).
Tiebreaker: erste Vorkommen-Reihenfolge im Cache (first_seen).

Read-only, keine Schreibwirkung, kein externer Call. Ausgeliefert vom
**seiten-Service** seit RAT-31 E6f-B (#1586) — der die icon-root ohnehin
besitzt (ROU-31 / SREG-18) — **kein** eigener Dienst.

**Konsumenten-Konsequenz (Mehrwort).** Frontend-Konsumenten, die heute einen
JS-Wort-Split-Workaround tragen (z. B. `seiten/static/routine-anpassen.js`
Iter-8-Pragma vor dieser Spec-Schärfung), **bauen den Workaround zurück**, sobald
das Backend liefert — der ehrliche-Ganzwort-Aufruf reicht dann (ROUTINE-21a:
„Frontend schickt ganzen Eingabe-Text"). Skill-Konsumenten (PAS, GAN) und
künftige Mini-Apps konsumieren das Mehrwort-Verhalten automatisch, ohne
eigene Klausel.

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
