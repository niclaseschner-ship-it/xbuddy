# Seiten-Registry — Spec     (ID-Präfix: SREG)

> Status: V1-Entwurf · Refs #347 · ratifiziert RAT-13 (berater-runde 2026-06-06)

Damit ein Elternteil im Eltern-Chat **jede angelegte Seite des XBuddy-Systems
per Link erreichen** kann („gib mir den Link zum Garderoben-Editor", „welche
Seiten gibt es?"), definiert diese Spec die **Seiten-Registry**: ein Inventar
**aller aufrufbaren View-Einstiegspunkte** (Display-Views, Eltern-/Settings-
Seiten, Controller-Apps, Panel-Instanzen, Display-Clients) und einen
Lese-Skill, der eine Frage gegen dieses Inventar auflöst.

Die Registry ist **vollständig per Konstruktion und ausfallfest**: ihre Wahrheit
sind committete Manifeste auf der Platte (nicht laufende Prozesse), und sie wird
aus den schon existierenden Quellen **aggregiert**, nicht handgepflegt
(CLAUDE.md §6 — kopiere nie zwischen Dokumenten; eine handgepflegte Zweitliste
war schon falsch, bevor sie existierte: #347 nannte den überholten Pfad
`/display/wetter/garderobe` statt `/display/wetter/regeln`).

**V1-Scope:** das Inventar aller fünf Seiten-Sorten (SREG-1) · Aggregator-
Service `xbuddy-seiten` mit gecachtem `inventar.json` (SREG-3) · der Lese-/
Auflist-Skill `seiten_finden` im Eltern-Chat (SREG-6). **Out-of-Scope V1:** das
Schreiben/Ausblenden einzelner Seiten über die Registry (sie ist rein lesend —
ein Schreibrecht wäre ein eigener Mechanismus); App-Discovery „was ist
installierbar" (das ist #325, eigene Linie, SREG-8).

---

## SREG-1 — Was ein Eintrag ist: kanonischer View-Einstiegspunkt
Ein Registry-Eintrag ist **ein kanonischer, menschen-aufrufbarer View-
Einstiegspunkt mit HTML-Antwort** — nicht „jede mögliche URL". Konkret:

- **Kanonisch, nicht jede URL.** Freie/unendliche Query-Parameter (z. B.
  `/display/plan/woche?ab=<datum>`, PLAN-4) erzeugen **keinen** eigenen Eintrag.
- **Endliche, bekannte Varianten** einer View (z. B. PLAN-3 Default +
  `?ansicht=klein`) stehen als `varianten[]` an **einem** Eintrag (je `slug`,
  `query`, `label`), damit „die Wochenansicht" und „die Kleinkind-Wochenansicht"
  beide auflösbar sind, ohne dass freie Filter die Registry sprengen.

**Fünf Sorten** aufrufbarer Seiten, ein gemeinsames Eintrags-Schema (SREG-4):

| Sorte | Beispiel | instanz-spezifisch | Wahrheitsquelle |
|-------|----------|--------------------|-----------------|
| (a) Display-View (Kind) | `/display/plan/woche` | nein | Buddy-Manifest (BUD-3) |
| (b) Eltern-/Settings-View | `/display/wetter/regeln` | nein | Buddy-Manifest (BUD-3) |
| (c) Controller-App | `/controller/figuren-erkennung/` | nein | Controller-Manifest (BUD-3) |
| (d) Panel-Instanz | `/controller/app-panel/<panel_id>` | **ja** | `panels.json`-Snapshot (PREG) |
| (e) Display-Client | `/display/<display_id>` | **ja** | Geräte-Registry-Snapshot (GER), gefiltert |

Filter für (e): nur Geräte mit `verwendung ∈ {display, beides}` **und**
`status = aktiv` (`geraete.md` GER-Modell) — ein reines Controller-Gerät ist
keine Display-Seite, ein stillgelegtes Tablet kein nutzbarer Link.

## SREG-2 — Wahrheit aus committeten Manifesten, nicht aus laufenden Prozessen
Die Sorten (a)(b)(c) kommen aus dem **committeten `views.json`-Manifest** jeder
Komponente (BUD-3, `conventions/buddies.md`) — es liegt im Repo neben dem Code,
also ist eine angelegte Seite **auch dann gelistet, wenn ihr Prozess gerade aus
ist** (Pi-Neustart, abgestürzter Dienst). Das ist der Grund, warum die Wahrheit
**nicht** per Live-HTTP-Abfrage der Buddys gezogen wird: „was nicht läuft,
antwortet nicht" würde eine angelegte Seite aus dem Inventar fallen lassen und
die Zuverlässigkeit (CONTEXT.md, oberste Priorität) verletzen. Zusätzlich hat
der Wetter-Buddy bewusst **keine** API (BUD-1b, E-WETTER-3) — er wäre live gar
nicht abfragbar; sein Manifest auf der Platte ist die einzige tragfähige Quelle.

Die instanz-spezifischen Sorten (d)(e) kommen aus den **Snapshots** der schon
bestehenden Registries (Panel-Registry PREG, Geräte-Registry GER), nicht aus
einer dritten Wahrheit (CLAUDE.md §6).

## SREG-3 — Aggregator-Service `xbuddy-seiten` mit gecachtem Inventar
Die Registry läuft als **eigener schlanker Plattform-Service** `xbuddy-seiten`
(PORT-2: `5042`), **nicht** im Router — sie hat **eigene geschriebene Daten**
(`inventar.json`, der aggregierte Snapshot), womit das eigene-Service-Muster
gerechtfertigt ist (RAT-1, analog Panel-Registry); der Router bleibt reines
Routing.

- **Aufbau + Aktualität (TTL):** Der Service hält `inventar.json` und baut es neu,
  sobald es älter als ein **TTL** ist (Default `30 s`, Config-Wert) — on-demand
  beim nächsten Request oder periodisch. Daraus folgt eine **beschränkte
  Staleness**: eine neu angelegte Seite (Panel/Display) erscheint **garantiert
  binnen TTL** in `GET /api/v1/seiten`. Schreiben atomar (DCOMP-4).
- **`GET /api/v1/seiten`** (URL-4, eigene URL-14-Zeile) serviert **immer aus
  `inventar.json`** — **keine** Upstream-Calls im Request-Pfad, Laufzeitbudget
  **< 50 ms**. Ein langsamer/defekter Buddy blockiert die Auskunft nie.
- **Manifeste = Platte, immer verfügbar (auch Kaltstart):** Die Sorten (a/b/c)
  kommen aus committeten `views.json`-Manifesten im Deployment — lesbar **auch
  beim Kaltstart** (frisches Deployment, gelöschtes `inventar.json`, alle
  Buddy-Prozesse aus). Beim ersten Start baut der Service `inventar.json` sofort
  aus ihnen. Ein **kaputtes/schema-inkompatibles Einzel-Manifest** wird mit
  Warnung **übersprungen** (DCOMP-3 — JSON-/Pflichtfeld-Fehler), das übrige
  Inventar bleibt vollständig; nie fällt das ganze Inventar wegen eines
  Manifests.
- **Snapshot-Sorten (d/e) Fehlermodell (Last-Known-Good, ROU-27):** bei
  Timeout/500/nicht-laufendem Upstream bleibt der **letzte erfolgreiche
  Teil-Snapshot** erhalten, markiert `stale: true`. **Kaltstart ohne je
  erfolgreichen Snapshot** (Panel-/Geräte-Service noch nie erreicht): die Sorte
  fehlt mit explizitem `snapshot_pending: true` in der Antwort — die Antwort ist
  trotzdem **gültig und nie leer** (die Manifest-Sorten tragen sie) und
  blockiert nicht. Nie eine leere/falsch-gekürzte Liste.

## SREG-4 — Eintrags-Schema (Manifest-Feld vs. abgeleitet)
Jeder Eintrag in `inventar.json`. Klar getrennt, was die Quelle (BUD-3-Manifest
bzw. PREG/GER-Snapshot) **liefert** und was der Aggregator **ableitet** — so
kann ein Externer aus einem Manifest deterministisch einen Eintrag erzeugen:

| Feld | Herkunft | Bedeutung |
|------|----------|-----------|
| `key` | **abgeleitet** | `<app\|instanz>-<slug>`, stabil (IDENT-1) — für die KI-Auflösung; deterministisch aus app+slug, nie frei vergeben |
| `typ` | **abgeleitet** | genau EINE Wertemenge: `display` \| `eltern` \| `controller` \| `panel` \| `display-client` (aus Sorte a–e + `zielgruppe` bestimmt) |
| `app` / `instanz` | **abgeleitet** | App-Slug (a–c, = Manifest-Besitzer) bzw. Instanz-ID (d/e, = Snapshot-Schlüssel) |
| `pfad` | Manifest/Snapshot | View-Pfad, z. B. `/display/wetter/regeln` — **nicht** die volle URL |
| `label` + `synonyme[]` | Manifest | deutsch, für „wo stelle ich X ein" (KI-Auflösung) |
| `icons[]` | Manifest (nur Sorte a) | volle Kachel-Icon-Liste der Display-View (BUD-4); 1:1 durchgereicht (SREG-10). Fehlt bei b/c (keine Kacheln) und bei Snapshot-Sorten d/e. |
| `varianten[]` | Manifest (opt.) | endliche bekannte Varianten (`slug`, `query` **als flaches Objekt**, `label`, eigenes `icons[]` falls abweichend; BUD-4) |
| `zeigt` | Manifest | 1 Satz, was die Seite zeigt |
| `zielgruppe` | Manifest | `kind` / `eltern` — **deskriptiv**, KEIN Berechtigungs-Gate (SREG-6) |

Die manifest-gelieferten Felder sind genau die BUD-3-Felder (`conventions/buddies.md`).
Die Snapshot-Sorten (d/e) tragen im **heutigen PREG/GER-Schema kein
menschenlesbares Label** (`panels.json`: `panel_id`/`source_id`/`router_url`,
PREG-3; Geräte-Modell: `id`/`typ`/`verwendung`/`status` — kein Anzeige-Name):
ihr `pfad` kommt aus der Instanz-ID (`panel_id` → `/controller/app-panel/<id>`,
`display_id` → `/display/<id>`), ihr `label` wird **aus der Instanz-ID
abgeleitet** (z. B. „Panel <panel_id>"); `synonyme`/`varianten`/`zeigt`
entfallen für (d/e). Ein reicheres Anzeige-Label für Panels/Displays bräuchte
ein PREG/GER-Namensfeld → **Folge-Aufgabe, nicht V1**: in V1 greift die freie
Text-Auflösung (SREG-5) voll für die Manifest-Sorten a–c; (d/e) sind auflistbar
und per ID/abgeleitetem Label adressierbar. Die **volle URL wird nicht
gespeichert** — sie entsteht erst beim Konsumenten aus `display_url_origin +
pfad` (URL-12: eine Origin; der Pfad ist die Wahrheit, die Origin ist
Per-Instanz-Deployment).

## SREG-5 — Skill `seiten_finden` (lesende Aufgabe)
Eltern-Chat-READ-Skill — eine **lesende Aufgabe** (EC-9; Muster wie TER-10
`termine-erfragen.md`), kein Schreibdialog, trigger-agnostische Funktion. Zwei
Modi:
- **„gib mir den Link zu X"** — die KI matcht die Frage gegen `label`/`synonyme`
  der Einträge; bei Mehrdeutigkeit gezielte Rückfrage (EC-22-Muster).
- **„liste alle Seiten" / „alle Seiten von Buddy Y"** — gefilterte Liste.

Der Link wird aus `display_url_origin` + `pfad` gebildet (GAA-3.7-Muster, wie
`panel_anlegen` die Controller-URL bildet). Der Skill liest die Registry über
`GET /api/v1/seiten` (Origin = ein neues `seiten_origin_url`, EC-15).

## SREG-6 — Auth/Exposure: EC-2-Mitgliedschaft + Netzgrenze, keine Rolle
V1 kennt **keine Rollen** (EC-3); berechtigt ist jedes **Familien-Gruppen-
Mitglied** (EC-2), in Gruppe **und** Privatchat gleichwertig. `seiten_finden`
erbt diese Berechtigung — es gibt **kein** zusätzliches Auth-Gate und **kein**
`intern`-Flag (kein Rollen-Vorbau, CLAUDE.md §6); `zielgruppe` bleibt rein
deskriptiv.

Dass „liste alle Seiten" keinem Kind den schreibenden Eltern-Editor
(`/display/wetter/regeln`) zeigt, ruht damit auf einer **operativen Annahme,
nicht auf Code**: die Familien-Gruppe besteht aus Eltern, Kinder sind **keine
Mitglieder** (Nic-Entscheid 2026-06-06 — der Eltern-Chat ist der eltern-seitige
Kanal). Das ist eine **bewusst akzeptierte V1-Grenze**, kein code-erzwungenes
Gate: würde ein Kind Mitglied der Familien-Gruppe, wäre es nach EC-2 berechtigt.
**Reopen-Trigger:** sobald Kinder in der Familien-Gruppe vorgesehen sind (oder
ein eigener Kinder-Chat entsteht), ist die Exposure-Frage neu zu stellen — dann
wird ein `intern`-Flag oder eine echte Rolle fällig. Bis dahin nicht auf Vorrat.

## SREG-7 — Vorbedingung: `display_url_origin` (OPEN-EC-Origin)
Ohne gesetztes `display_url_origin` (heute leer per Default, `eltern-chat.md`
EC-15 / OPEN-EC-Origin) gibt der Bot nur den nackten `pfad` aus — kein
tippbarer Link, kein Familien-Nutzen. **OPEN-EC-Origin ist damit ein Blocker für
SREG-5** und muss vor der V1-Implementierung gelöst sein (ein Onboarding-/
Config-Schritt, der `display_url_origin` aus der Origin des Bot-Hosts zieht).

## SREG-8 — Verhältnis zu #325 (App-Discovery): getrennt, teilt das Format
#325 enumeriert **anlegbare Apps** (was *kann* in eine Panel-Kachel — schreibend,
an den Installations-Mechanismus #296 gekoppelt). Die Seiten-Registry enumeriert
**bereits aufrufbare URLs** (lesend). Sie bleiben **getrennt** — Zusammenlegen
würde den leichten Lese-Skill an das vertagte #296-Thema ketten. Sie **teilen
aber das `views.json`-Format**: das BUD-3-Manifest ist die Datenquelle, aus der
#325 später seine „verfügbaren Apps + Views" zieht — kein zweiter App-Katalog.

## SREG-9 — Automatisierte Tests je Anforderung
- **Vollständigkeit-bei-Ausfall:** Buddy-Prozess gestoppt → seine Manifest-Seiten
  bleiben in `GET /api/v1/seiten` gelistet (SREG-2).
- **Kaltstart:** kein `inventar.json` + Panel-/Geräte-Service aus + Buddy-Prozesse
  aus → `GET` liefert die Manifest-Sorten (a/b/c) vollständig, (d/e) mit
  `snapshot_pending: true`; Antwort gültig und **nie leer** (SREG-3).
- **Kaputtes Manifest:** ein `views.json` mit JSON-/Pflichtfeld-Fehler → wird
  übersprungen (Warnung), das übrige Inventar bleibt vollständig (SREG-3/DCOMP-3).
- **Aktualität/TTL:** ein während des Betriebs neu angelegtes Panel erscheint
  **binnen TTL** in `GET /api/v1/seiten` (SREG-3).
- **Schnelle, nie-leere Antwort:** `GET /api/v1/seiten` antwortet aus
  `inventar.json` ohne Upstream-Call; bei Panel-/Geräte-Snapshot-Ausfall
  `stale: true` statt leerer/gekürzter Liste (SREG-3).
- **Varianten:** ein Eintrag mit `varianten[]` löst sowohl Default als auch
  Variante auf; `?ab=<datum>` erzeugt keinen Eintrag (SREG-1).
- **Icon-Durchreichung + Schalter:** ein Sorte-a-Manifest mit `icons[]`
  (+ `varianten[].icons[]`) erscheint byte-gleich im Eintrag; bei
  `icons_erforderlich=false` bleibt eine View ohne `icons[]` gelistet (Warnung),
  bei `icons_erforderlich=true` wird genau diese View übersprungen (Rest bleibt);
  Sorten b/c/d/e tragen kein `icons`-Feld (SREG-10).
- **Editor-Eintrag je Panel:** Snapshot mit N Panel-Instanzen → **2N**
  Panel-Einträge (N Panel-Seiten + N Editor-Einträge), je distinkter `key`/`pfad`,
  Editor-`pfad` = `/controller/app-panel/<panel_id>/bearbeiten` (SREG-11).
- **(e)-Filter:** Geräte-Snapshot mit `controller`/`display`/`beides`/`inaktiv`
  → nur `display|beides` & `aktiv` erscheinen (SREG-1).
- **Manifest⇔Route-Bindung:** je Buddy der BUD-3-Eigentest (kanonische
  HTML-GET-Route ⇔ Eintrag; Alias-/POST-Routen ausgenommen; Controller gegen
  Slug-Existenz) — `conventions/buddies.md` BUD-3.
- **Skill-Auflösung:** „Link zum Garderoben-Editor" → `/display/wetter/regeln`
  mit `display_url_origin` zur vollen URL; Mehrdeutigkeit → Rückfrage (SREG-5).
- **Auth:** `seiten_finden` erbt EC-2 (Mitglied berechtigt, Gruppe+Privatchat);
  die „keine Kind-Mitglieder"-Annahme (SREG-6) ist **operativ, nicht
  automatisiert testbar** — sie ist eine bewusste V1-Grenze, kein Code-Gate.

## SREG-10 — Icon-Durchreichung (nur Display-Views, Sorte a) + Durchsetzungs-Schalter
Der Aggregator übernimmt `icons[]` (BUD-4) und `varianten[].icons[]` **1:1** aus
dem Manifest in den `inventar.json`-Eintrag — wie er `varianten` durchreicht
(SREG-2), **ohne** zu komponieren oder abzuleiten. Im SREG-4-Schema ist `icons`
ein **manifest-geliefertes** Feld (Herkunft = Manifest, analog `label`), getragen
**nur von Display-Views (Sorte a)** (BUD-4). Die Sorten b/c und die
Snapshot-Sorten d/e tragen **kein** `icons` — das Feld **fehlt** (nicht `null`).

**Durchsetzung über den Schalter `icons_erforderlich`** (Aggregator-Config,
Default `false`) — das ist der **maschinenlesbare Phasenwechsel** der gestaffelten
Einführung, kein vager „nach dem Backfill":
- `icons_erforderlich = false` (Migration): ein **fehlendes** `icons[]` an einer
  Sorte-a-View → **Warnung, kein Skip**; der Eintrag bleibt gelistet (ohne
  `icons`). So reißt die Feld-Einführung keine gültigen Views aus dem Inventar
  (SREG-3/DCOMP-3).
- `icons_erforderlich = true` (nach Backfill, vom Härtungs-PR umgelegt): ein
  fehlendes `icons[]` an einer Sorte-a-View → **per-View-Skip** (nur diese View,
  nicht das ganze Manifest — die per-View-Skip-Granularität wird in SREG-13
  bindend); Warnung protokolliert.

*Wenn* `icons_erforderlich=false` und `icons[]` fehlt, *dann* bleibt der Eintrag
gelistet (Warnung); *wenn* `icons_erforderlich=true` und `icons[]` fehlt, *dann*
wird genau diese View übersprungen, der Rest des Manifests bleibt. Beide Modi sind
mit einer Manifest-Fixture testbar.

## SREG-11 — Editor-Eintrag je Panel-Instanz (zusätzlich zur Panel-Seite)
Für jede Panel-Instanz (Snapshot-Sorte d) erzeugt der Aggregator **einen
zusätzlichen, abgeleiteten Eintrag** für deren Editor-Seite — **neben** dem
bestehenden Panel-Seiten-Eintrag (Sorte d), der unverändert bleibt. Felder des
Editor-Eintrags (alle deterministisch aus der `panel_id`, kein neues PREG-Feld):

| SREG-4-Feld | Wert des Editor-Eintrags |
|------|------|
| `pfad` | `/controller/app-panel/<panel_id>/bearbeiten` (PBE-2) |
| `key` | `<panel_id>-bearbeiten` — **distinkt** vom Panel-Seiten-`key` (`<panel_id>`), keine Kollision |
| `typ` | `eltern` (eltern-seitige Settings-View) |
| `label` | abgeleitet, z. B. „Panel `<panel_id>` bearbeiten" |
| `icons`/`varianten`/`zeigt`/`synonyme` | entfallen (wie bei Sorte d, SREG-4) |

*Wenn* die Registry N Panel-Instanzen kennt, *dann* enthält das Inventar **2N**
Panel-bezogene Einträge: N Panel-Seiten (Sorte d) **und** N Editor-Einträge, je
mit distinktem `key` und `pfad`. Der `seiten_finden`-Skill (SREG-5) liefert so je
Panel einen eigenen Editor-Link, ohne die Panel-Seite zu überschreiben.

Konsument: `specs/platform/panel-bearbeiten.md` PBE-2 (#330).

## SREG-13 — Per-View-Skip statt per-Manifest-Skip bei Schema-Fehler

Beim Aggregator-Lauf (SREG-3) gilt: Ein einzelner View-Eintrag, der das
SREG-4-Schema verletzt, wird **isoliert übersprungen und protokolliert** — die
übrigen Views desselben Manifests bleiben im Inventar. Dies hebt die
Skip-Granularität von „Manifest" auf „View" und schützt mehrwertige Manifeste
(z. B. `wetter/views.json` mit `heute` (kind) und `regeln` (eltern) im selben
Dokument) davor, dass ein einzelner Schema-Fehler das ganze Manifest aus
`GET /api/v1/seiten` wirft (CONTEXT.md Zuverlässigkeit: ein Fehler darf nicht
mehr werfen als nötig).

Greift sowohl bei JSON-Schema-Fehler einer einzelnen View **als auch** beim
Pflicht-Modus von SREG-10 (`icons_erforderlich=true`, fehlendes `icons[]` an
einer Sorte-a-View): die Skip-Granularität ist immer per-View.

**Eskalations-Hierarchie:** Eine ganze Manifest-Datei wird weiterhin
übersprungen, wenn sie nicht lesbar/parsebar ist (SREG-3) — erst wenn das
Manifest geparst ist, greift die View-Granularität. SREG-3 (Datei/Manifest)
schlägt vor SREG-13 (View). Damit ist die Reihenfolge eindeutig:
Datei-Skip > View-Skip > Eintrag-bleibt-gelistet.

*Wenn* `wetter/views.json` `heute` (gültig) + `regeln` (Schema-Fehler) trägt,
*dann* erscheint `heute` weiterhin in `GET /api/v1/seiten`; `regeln` fehlt
mit Warnung im Aggregator-Log.

*Test-Implikation:* Manifest mit einer kaputten + einer gültigen View → die
gültige bleibt im Inventar; eine `icons_erforderlich=true`-Probe mit einer
Sorte-a-View ohne `icons[]` in einem mehrwertigen Manifest → genau diese View
wird übersprungen, der Rest bleibt.

**Enabler für #347-Icon-Pflicht-Härtungsstufe:** Solange der Skip
per-Manifest war, hätte ein einziges noch-nicht-gebackfilltes View-Icon ein
ganzes Multi-View-Manifest gekippt — der `icons_erforderlich=true`-Schalter
wäre damit erst sicher umlegbar gewesen, nachdem absolut JEDES Manifest
backgefillt war. Mit SREG-13 ist der Schalter graduell umlegbar.

*Tickets:* #388

## Offene Punkte

### OPEN-SREG-Kategorie — Kategorisierung der Seiten-/Add-Liste
Wird die per `GET /api/v1/seiten` gelieferte Liste (insb. die Panel-Add-Auswahl,
#330 PBE-7) bei wachsender View-Zahl unübersichtlich, ist ein `kategorie`-Feld am
Eintrag zu erwägen. Heute (≤ ~6 Views) flach ausreichend — **nicht auf Vorrat**
(CLAUDE.md §6). Reopen-Trigger: Add-Liste > ~10 Einträge oder Eltern-Feedback
Unübersichtlichkeit.

---

## E-SREG-1 — Verworfene Alternativen
- **Pull-Aggregation live aus den Buddy-Prozessen** — verworfen: „was nicht
  läuft, antwortet nicht" lässt angelegte Seiten bei Ausfall aus dem Inventar
  fallen (Zuverlässigkeits-Bruch, CONTEXT.md); Wetter hat zudem keine API
  (BUD-1b). Wahrheit ist die committete Platte (SREG-2).
- **Aggregator im Router** statt eigenem Service — verworfen: machte aus Routing
  eine App-Discovery-Verantwortung + nochmal ein Fehler-/Snapshot-Modell. Der
  eigene Service ist gerechtfertigt, weil er eigene geschriebene Daten hat
  (`inventar.json`, RAT-1).
- **`views.json` als gitignoretes Per-Instanz-Config-Feld** — verworfen: Config
  darf fehlen (CONFIG-4) → Registry leer trotz laufender Route; und es wäre eine
  dritte Darstellung. Stattdessen committetes Manifest + Eigentest Route⇔Manifest
  (BUD-3).
- **`intern`-Flag / Rollensystem für Exposure** — verworfen: der Kanal
  (Eltern-Chat, parent-only) ist das Gate (SREG-6); ein Flag wäre Vorbau.
- **Mit #325 zu EINEM App-/Seiten-Katalog zusammenlegen** — verworfen: koppelt
  Lese-Skill an das vertagte #296-Installations-Thema (SREG-8).
