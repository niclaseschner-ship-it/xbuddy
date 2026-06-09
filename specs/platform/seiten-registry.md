# Seiten-Registry — Spec     (ID-Präfix: SREG)

> Status: V1-Entwurf · Refs #347 · ratifiziert RAT-13 (berater-runde 2026-06-06)
> Pivot + SREG-12-Ratifizierung 2026-06-08 (Werft + Berater-Runde,
> ENTSCHEID `brainstorm/berater-runde/20260608-RATIFIZIERT-seiten-uebersicht-platform-genre.md`)
> SREG-12 Gate B (Design-Wahl) 2026-06-08: Variante „gemeinsame Box pro
> Geräte-Paar" gewählt; Reconcile in dieser Spec-Revision nachgezogen.

Damit ein Elternteil im Eltern-Chat **jede angelegte Seite des XBuddy-Systems
per Link erreichen** kann, definiert diese Spec die **Seiten-Registry**: ein
Inventar **aller aufrufbaren View-Einstiegspunkte** (Display-Views, Eltern-/
Settings-Seiten, Controller-Apps, Panel-Instanzen, Display-Clients) und eine
**gerenderte Eltern-Übersichts-Seite**, deren Hauptzweck ist, **welcher
Panel-Controller welches Display steuert** auf einen Blick zu zeigen
(Geräte-Paare ganz oben), und je Eintrag zwei kopierbare URLs (Heimnetz +
Tailscale) bereitzustellen. Der Eltern-Chat liefert nur **einen** Link — auf
diese Übersichtsseite. Pro-View-Auflösung passiert auf der Seite per
Volltextsuche, nicht im Chat (Pivot 2026-06-07, ersetzt das ursprüngliche
KI-Matching gegen `label`/`synonyme`).

Die Registry ist **vollständig per Konstruktion und ausfallfest**: ihre Wahrheit
sind committete Manifeste auf der Platte (nicht laufende Prozesse), und sie wird
aus den schon existierenden Quellen **aggregiert**, nicht handgepflegt
(CLAUDE.md §6 — kopiere nie zwischen Dokumenten; eine handgepflegte Zweitliste
war schon falsch, bevor sie existierte: #347 nannte den überholten Pfad
`/display/wetter/garderobe` statt `/display/wetter/regeln`).

**V1-Scope:** das Inventar aller fünf Seiten-Sorten (SREG-1) · Aggregator-
Service `xbuddy-seiten` mit gecachtem `inventar.json` (SREG-3) · eine
**gerenderte Eltern-Übersichts-Seite** unter `/api/v1/seiten/uebersicht` mit
**Geräte-Paaren als Hero-Sektion am Seitenkopf** (Display als Anker, daran
Panel-Editor-Karten — Verknüpfung aus PREG, SREG-12) und je Eintrag **zwei
kopierbare URLs** (Heimnetz + Tailscale) · ein **Trigger-Skill
`seiten_uebersicht`** im Eltern-Chat, der nur diesen einen Link liefert
(SREG-5 — Pivot). **Out-of-Scope V1:** das Schreiben/Ausblenden einzelner
Seiten über die Registry (sie ist rein lesend); App-Discovery „was ist
installierbar" (das ist #325, eigene Linie, SREG-8); KI-Matching gegen
`label`/`synonyme` im Chat (durch SREG-12-Seite + Volltextsuche abgelöst);
Co-Lokations-Verknüpfung („Panel und Display laufen auf demselben Hardware-
Gerät", würde GER-Erweiterung verlangen — Folge-Aufgabe).

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
| (b) Eltern-/Settings-View | `/display/wetter/regeln`, `/api/v1/seiten/uebersicht` | nein | Buddy- **oder Platform-Service-Manifest** (BUD-3 analog: `<komponente>/views.json`) |
| (c) Controller-App | `/controller/figuren-erkennung/` | nein | Controller-Manifest (BUD-3) |
| (d) Panel-Instanz | `/controller/app-panel/<panel_id>` | **ja** | `panels.json`-Snapshot (PREG) |
| (e) Display-Client | `/display/<display_id>` | **ja** | Geräte-Registry-Snapshot (GER), gefiltert |

Sorte (b) deckt zwei Eigentümer-Klassen:
- **Buddy-Eigentümer**: eine Eltern-Settings-View, die zu einem Familien-Buddy
  gehört, lebt unter `/display/<buddy>/<view>` (URL-2, BUD-1a). Beispiel:
  `/display/wetter/regeln` (Garderoben-Editor, #328).
- **Platform-Service-Eigentümer**: eine View, die ein Platform-Service selbst
  ausliefert (RAT-1-Muster: eigener Prozess, eigener Port), lebt **neben** der
  API des Service unter `/api/v1/<service>/<view>` (URL-4, ROU-14-Präzedenz:
  `/api/v1/diag` als HTML im Router). Beispiel: SREG-12 unter
  `/api/v1/seiten/uebersicht`. Die View ist eine **alternative Darstellung der
  Registry-Daten** — sie wohnt darum am Service, der die Daten hält.

Filter für (e): nur Geräte mit `verwendung ∈ {display, beides}` **und**
`status = aktiv` (`geraete.md` GER-Modell) — ein reines Controller-Gerät ist
keine Display-Seite, ein stillgelegtes Tablet kein nutzbarer Link.

**Verknüpfung Panel ↔ Display** ist bereits in PREG hinterlegt: jeder
Panel-Eintrag trägt pflichtmäßig `display_id` (PREG-Tabelle, E-PANEL-5: „genau
eines"). Der Aggregator reicht diese Verknüpfung am SREG-4-Eintrag durch
(Sorte d: `verknuepft_mit_display`; Sorte e: per Reverse-Lookup
`verknuepft_mit_panels[]` — mehrere Panels können dasselbe Display steuern,
PREG-Beispiel „Mama-iPhone" + „Papa-iPhone" auf Wohnzimmer-Display).

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

**Platform-Services führen ihr eigenes `views.json` analog BUD-3**, wenn sie
selbst eine HTML-View anbieten (Sorte b mit Platform-Eigentümer, SREG-1). Heute
ein Vorkommen: `seiten/views.json` listet die Übersichts-Seite SREG-12
(`/api/v1/seiten/uebersicht`). Der Aggregator unterscheidet beim Einlesen nicht
zwischen Buddy- und Platform-Manifesten — beide tragen das gleiche BUD-3-
Schema. Die Selbst-Aufnahme („die Übersicht listet sich selbst") fällt damit
aus der Manifest-Wahrheit, **kein** handgepflegter Sonderfall im
Aggregator-Code.

Die instanz-spezifischen Sorten (d)(e) kommen aus den **Snapshots** der schon
bestehenden Registries (Panel-Registry PREG, Geräte-Registry GER), nicht aus
einer dritten Wahrheit (CLAUDE.md §6). Die Panel↔Display-Verknüpfung
(SREG-1) wird ebenfalls aus PREG geliefert (`panels.json` Pflichtfeld
`display_id`), nicht aus einer dritten Quelle erfunden.

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
| `verknuepft_mit_display` | **abgeleitet** (Sorte d) | `display_id` aus PREG `panels.json` (Pflichtfeld, E-PANEL-5). Trägt **nur** Sorte (d) — die Panel-Instanz, der eigentliche Steuerer. Leer/fehlend bei (a)(b)(c)(e). |
| `verknuepft_mit_panels[]` | **abgeleitet** (Sorte e) | Liste der `panel_id`s, die dieses Display steuern (Reverse-Lookup über PREG-Snapshot). Trägt **nur** Sorte (e). Leer (`[]`), wenn kein Panel auf dieses Display zeigt. |
| `verknuepft_mit_panel` | **abgeleitet** (Sorte b, Panel-Editor-Eintrag SREG-11) | `panel_id` aus dem Editor-Pfad-Segment `/controller/app-panel/<panel_id>/bearbeiten`. Trägt nur der Editor-Eintrag — verbindet den Editor mit seiner Panel-Instanz, sodass die SREG-12-Hero den Editor visuell an der Panel-Instanz andocken kann (Display ↔ Panel ↔ Editor-Kette). Leer bei allen anderen (b)-Einträgen. |

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

## SREG-5 — Skill `seiten_uebersicht` (Trigger, ein Link)
Eltern-Chat-Skill — eine **lesende, trigger-agnostische** Funktion (EC-9-Muster).
**Nur EIN Modus**, kein KI-Matching, keine Rückfrage-Logik: erkennt eine
Frage-Familie wie „zeig mir alle Seiten", „welche Seiten gibt es", „Link zur
Garderoben-Seite", „wo stelle ich X ein", „Link zum Küchen-Panel-Editor" →
antwortet mit **einem** Link auf die gerenderte Übersichtsseite (SREG-12). Die
Pro-View-Auflösung („welchen genau?") passiert auf der Seite per Volltextsuche
gegen `label`/`synonyme`/`zeigt` (SREG-12), nicht im Chat — das hält den Chat
schlank und die Wartung in EINER Seite.

Der Link wird gebildet als `display_url_origin_heim` + `/api/v1/seiten/uebersicht`
(SREG-12). Heimnetz-Variante ist der Default, weil der Eltern-Chat im
Heimnetz/Tailscale-Kontext läuft und Eltern „am Familien-Tablet" landen sollen;
die Tailscale-Variante ist auf der Seite selbst kopierbar (SREG-12).

Der Skill ruft `GET /api/v1/seiten` **nicht** mehr selbst auf — die
Übersichtsseite ist sein einziger Konsument der Registry.

**Pivot-Begründung (Nic, /arbeitstag-prep 2026-06-07):** Der vorherige Modus
„gib mir den Link zu X" mit KI-Matching gegen `label`/`synonyme` und
Mehrdeutigkeits-Rückfrage ist **ersetzt** durch die gerenderte Seite +
Volltextsuche. Die Komplexität wandert aus dem KI-Skill in eine Seite, die
einfach zu warten ist. PBE-2 („je Panel direkter Editor-Link aus dem
Eltern-Chat") wird durch SREG-12 mit-bedient: der Editor-Eintrag erscheint als
eigene Karte direkt am gepaarten Display (SREG-12 Hero-Sektion „Geräte-Paare"),
kopierbar — der „direkte Link je Panel" ist weiterhin in einem Tipp
erreichbar, nur einen Tipp später als ein eigener Chat-Skill und konsistent
für **alle** Eintrags-Sorten.

## SREG-5b — Opt-in-Direktantwort (Sekundärpfad nach SREG-5)
Nach der Default-Antwort (SREG-5 Übersichtslink) **bietet der Bot in derselben
Nachricht** an, die spezifisch angefragte Seite **direkt im Chat** zu schicken:

> Hier ist die Übersicht aller Seiten: `<heim-origin>/api/v1/seiten/uebersicht`
> Soll ich dir die passende Seite stattdessen direkt hier schicken?

*Wenn* der Elternteil in der Folgeantwort opt-in bestätigt („ja", „direkt",
„bitte", o. ä.), *dann* führt der Skill **dann erst** Pro-View-KI-Matching aus
(gegen `label`/`synonyme`/`zeigt` der Registry-Einträge — also genau das, was
SREG-5 ursprünglich als Primärverhalten hatte und durch den Pivot 2026-06-07
verworfen wurde) und antwortet mit der vollen URL der passendsten View. Bei
Mehrdeutigkeit: eine gezielte Rückfrage im EC-22-Muster („Meintest du die
Wetter-heute-Anzeige oder den Garderoben-Editor?"), dann Auflösung.

**Mechanik des Pro-View-KI-Matchings (verbindlich, Weg-2-Pivot 2026-06-09):**
Der Skill arbeitet in zwei Runden mit dem LLM:

1. **Runde 1 (Inventar-Übergabe):** Der Skill ruft `seiten_client.inventar()`
   und gibt die Liste der Registry-Einträge (pro Eintrag: `label` + `key` +
   `synonyme` + `zeigt`) als **Tool-Result** an den Agent-Loop zurück. **Kein
   Bot-Post in dieser Runde** — die Antwort wird im Agent-Kontext petrarbeitet.

2. **Runde 2 (LLM-Wahl):** Das LLM wählt aus dem in Runde 1 übergebenen
   Inventar das passende Element und ruft den Skill erneut mit
   `aktion=match` und dem **exakten `label` oder `key` aus dem Inventar**
   auf. Bei Mehrdeutigkeit formuliert das LLM eine EC-22-Rückfrage selbst
   („Meintest du die Wetter-heute-Anzeige oder den Garderoben-Editor?"),
   oder nutzt einen separaten `mehrdeutig`-Eingang.

3. **URL-Build:** Der Skill macht ein **deterministisches Lookup** auf das
   vom LLM übergebene `label`/`key` gegen die Registry-Einträge und bildet
   die URL über `display_url_origin_heim` + `pfad` (SREG-4).

**Kein lokales Substring-Match auf User-Begriffe.** Das war der frühere
Bug #488: User-Verben wie „zeig" wurden fehl-priorisiert, weil der Skill
direkt auf die User-Anfrage Substring-Match machte. Mit dem Weg-2-Pivot ist
das LLM der einzige Ranker **für die User-Anfrage** (es sieht das Inventar
und wählt sinngebend); der anschließende lokale Lookup arbeitet auf einem
**vom LLM disziplinierten Wert** (exaktes `label` oder `key` aus dem
übergebenen Inventar) und ist deshalb deterministisch sicher — Substring-
oder Identitäts-Match auf einem bekannten Inventar-Wert kann keine
User-Verben mehr fehl-priorisieren.

*Wenn* der Elternteil opt-out signalisiert (z. B. „nein", „passt", „nichts")
oder keine Folgeantwort innerhalb des EC-15-Depth-Fensters kommt, *dann*
endet der Dialog still — kein wiederholtes Nachfragen.

**Begründung der zweistufigen Architektur (Nic, 2026-06-08):** der
KI-Matching-Aufwand entfällt im Default-Fall — die Übersicht trägt den
Selbstbedienungs-Pfad. Eltern, die schnell **eine** Antwort im Chat wollen,
ohne den Browser-Tab zu wechseln, bekommen sie auf einen Folge-Tipp — der
Bot ist im Opt-in-Pfad „Familien-Assistent" und im Default-Pfad nur „URL-
Lieferant". So bleibt die Architektur sparsam (Komplexität nur dort, wo der
Elternteil sie aktiv anfordert), gleichzeitig wird PBE-2-Eltern-UX nicht
geschwächt.

**Implementiert in:** eltern-chat-Code (siehe #476 — eigenes Ticket, mit
#467 (SREG-12) in einem /arbeitstag-Lauf gemeinsam gebaut).

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

## SREG-7 — Vorbedingung: zwei Display-URL-Origins (Heimnetz + Tailscale)
Familien greifen über **zwei Wege** auf XBuddy zu: lokales Heimnetz (z. B.
`https://xbuddy-hub.local:8443`) und Tailscale (z. B.
`https://xbuddy-hub.tailnet-xxxx.ts.net`). Damit eine angebotene URL **wirklich
am Handy funktioniert**, müssen beide Origins als Config-Werte gesetzt sein:

| Config-Schlüssel | Bedeutung | Default |
|---|---|---|
| `display_url_origin_heim` | Heimnetz-Origin (Bot-Default für SREG-5; tritt an die Stelle des bestehenden `display_url_origin`, GAA-3.7) | leer |
| `display_url_origin_tailscale` | Tailscale-Origin (zusätzlich auf SREG-12-Seite kopierbar) | leer |

**V1-Pflicht:** `display_url_origin_heim` muss gesetzt sein, sonst kann der
SREG-5-Skill keinen tippbaren Link liefern und die SREG-12-Seite hat keine
„Heim"-Spalte. **`display_url_origin_tailscale` ist V1-Soll** — fehlt sie,
zeigt SREG-12 nur die Heim-Spalte mit explizitem Banner-Hinweis statt zweier
Spalten, die Seite bleibt nutzbar. Kein Auto-Fallback auf Heim als Tailscale
(falsche Origin = nicht-erreichbarer Link).

**Migration des existierenden `display_url_origin`** (`eltern-chat/config.py:85`,
GAA-3.7): wird in einem **eigenen Folge-Ticket der Implementierung** zu
`display_url_origin_heim` umbenannt — **nicht** im Spec-PR. Tests in
eltern-chat akzeptieren während der Migration beide Namen.

**OPEN-EC-Origin** (eltern-chat.md EC-15) bleibt der Auflöse-Track für den
Onboarding-/Config-Schritt, der diese Werte aus der Hub-Auslieferung zieht;
SREG-7-V1 erweitert ihn um die zweite Origin.

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
- **Trigger-Skill:** Frage-Familien-Treffer („zeig mir alle Seiten" / „Link zur
  Garderoben-Seite" / „Link zum Küchen-Panel-Editor") → Skill antwortet mit
  **genau einer URL** = `display_url_origin_heim` + `/api/v1/seiten/uebersicht`
  (SREG-5). Kein KI-Matching gegen Pro-View-Labels; der Skill ruft
  `GET /api/v1/seiten` nicht selbst auf.
- **Übersichts-Seite rendert:** `GET /api/v1/seiten/uebersicht` antwortet mit
  HTML (`Content-Type: text/html`); `GET /api/v1/seiten` (ohne Sub-Pfad) bleibt
  JSON-only. Hero-Sektion „Geräte-Paare" am Seitenkopf, darunter die übrigen
  Sorten nach Buddy/App gruppiert (SREG-12).
- **Geräte-Paar Aggregator:** Im Inventar trägt ein Panel-Sorte-(d)-Eintrag
  `verknuepft_mit_display: <display_id>` (Wert kommt aus `panels.json`), ein
  Sorte-(e)-Eintrag `verknuepft_mit_panels: [<panel_id>, …]` (Reverse-Lookup),
  ein Panel-Editor-Eintrag (Sorte b, SREG-11) `verknuepft_mit_panel:
  <panel_id>` (abgeleitet aus Pfad-Segment). Zwei Panels auf demselben Display
  → ein (e)-Eintrag mit zwei `panel_id` in `verknuepft_mit_panels[]` (SREG-1).
- **Paar-Hero rendert (V2 nach Gate B):** Ein Display mit
  `verknuepft_mit_panels: [p1]` erscheint in der Hero-Sektion als gemeinsame
  Box (Header `📺 <display_id>` + „wird gesteuert von 1 Panel") mit
  Display-Karte oben und Panel-Karte für `p1` als Hauptkarte unten, der Editor
  als Anhang **innerhalb** der Panel-Karte; `[p1, p2]` rendert die Box mit
  zwei Panel-Karten im Grid (je mit Editor-Anhang); `[]` (kein Panel)
  erscheint nicht im Hero, sondern unten in der „instanz"-Buddy-Gruppe.
- **Buddy-Gruppen-Aggregator:** Sekundäre Karten werden nach `app`-Feld
  gruppiert; pro Gruppe ein gemeinsamer Rahmen mit Slug-Header. Varianten
  (`varianten[]`) rendern als eigene Geschwister-Karten in derselben Gruppe
  (gleicher `app`-Slug, Pfad mit `query`-Anhängung). Reihenfolge: Anzahl
  Karten absteigend, dann alphabetisch (SREG-12).
- **Variant-Rendering:** ein Eintrag mit `varianten[]` rendert genau N+1
  Karten in seiner Buddy-Gruppe (Default + N Varianten), je mit eigener
  URL-Anhängung und eigenem Label; die `icons[]` der Variante (falls
  vorhanden) überschreiben die Eintrags-Icons nur für die Variant-Karte
  (SREG-1, SREG-12).
- **Übersicht-Selbstbezug:** die Übersichts-Seite selbst erscheint als
  Sorte-(b)-Eintrag mit Platform-Eigentümer (`app: seiten`, `pfad:
  /api/v1/seiten/uebersicht`, `zielgruppe: eltern`) im Inventar — Quelle
  `seiten/views.json` (SREG-12 / BUD-3-analog).
- **Copy & Long-Press:** Copy-Button schreibt die volle URL in die
  Zwischenablage; eine Smoketest-Assertion sichert, dass die `<a>`-Elemente
  natives Text-Selektieren erlauben (kein `user-select: none` auf Link-Text)
  (SREG-12).
- **Volltextsuche (Karten-Match):** Eingabe „garderobe" filtert sowohl
  Paar-Hero als auch sekundäre Karten auf passende Einträge (Match gegen
  `label`/`synonyme`/`zeigt`) — clientseitig, keine Server-Roundtrip
  (SREG-12).
- **Volltextsuche (Buddy-Header-Match):** Eingabe „wetter" matcht den
  Gruppen-Header und macht **alle** Karten der Wetter-Gruppe sichtbar
  (Kontext-Erhalt), auch wenn einzelne Karten den Suchbegriff im
  `label`/`synonyme` nicht tragen würden (SREG-12).
- **Hero-Paar-Kontext-Erhalt:** Eingabe „bearbeiten" matcht einen
  Editor-Anhang in der Paar-Box; die ganze Paar-Box (inkl. Display-Karte
  und anderer Panel-Karten) bleibt sichtbar, weil Treffer innerhalb der Box
  die Box als ganze gegen Ausblendung schützt (SREG-12).
- **Manifest⇔Route-Bindung für Platform-Service:** Eigentest in
  `seiten/views.json` ⇔ `seiten/main.py` analog BUD-3 — der `pfad`
  `/api/v1/seiten/uebersicht` muss eine echte Flask-Route mit HTML-Antwort
  haben (SREG-12).
- **Auth:** SREG-5-Skill erbt EC-2 (Mitglied berechtigt, Gruppe+Privatchat);
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

**Varianten-Härte ist sofort total (verbindlich, #440).** Eine Variante
(`varianten[]`-Eintrag) ist ein **vollständiger Sub-Manifest-Eintrag** —
ihre `icons[]` und ihre `query`-Form sind unbedingt Pflicht, sobald die
View Sorte a ist. Der Migrations-Schalter `icons_erforderlich` greift
**nicht** auf Varianten-Ebene; eine Variante ohne `icons[]` fällt **mit
dem ganzen Manifest** durch (`ManifestError` → Aggregator skippt das
Manifest, nicht die einzelne Variante). Begründung: Varianten kommen erst
ins Repo, wenn sie bewusst angelegt werden (keine implizite Existenz wie
ein noch-nicht-backfilled-`icons[]` an einer alten View); ein nachträglich
gestaffeltes Einführen für Varianten würde Vorrats-Mechanik bedeuten
(CLAUDE.md §6 „nichts auf Vorrat"), die heute keinen konkreten Schmerz
löst — alle bestehenden Varianten (plan/woche-klein) sind vollständig
gebackfillt. **Verworfen:** Variante folgt demselben `icons_erforderlich`-
Schalter (Weg B aus #440) — Vorrats-Mechanik ohne Trigger.

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
mit distinktem `key` und `pfad`. Beide tragen `verknuepft_mit_display`
(SREG-4) — die SREG-12-Hero-Sektion gruppiert sie am gemeinsamen Display-Anker.

Konsument: `specs/platform/panel-bearbeiten.md` PBE-2 (#330). Der frühere
Konsumenten-Pfad „Eltern-Chat liefert je Panel direkt den Editor-Link" wird
durch SREG-12 mit-bedient: der Editor-Eintrag liegt auf der Übersichtsseite
direkt neben dem gepaarten Display, kopierbar — ein Tipp mehr als der
ehemalige Direkt-Link aus dem Chat, dafür konsistent für alle Eintrags-Sorten
und ohne KI-Matching im Skill.

## SREG-12 — Gerenderte Eltern-Übersichts-Seite (HTML, neben der Registry-API)
Die V1-Antwort auf „wo finde ich die Seiten" ist **eine eigene HTML-Seite** im
seiten-Service. Sie listet das gesamte Inventar aus `inventar.json` (SREG-3)
auf, und ist für **Eltern am Handy** gebaut (Tablet/Phone, Daumen-bedienbar).
Sie ist die **alternative Darstellung** der Registry — Daten liegen in
`/api/v1/seiten` (JSON), Rendering unter `/api/v1/seiten/uebersicht` (HTML).
Eine Datenquelle, zwei Darstellungen.

**Hauptzweck = Geräte-Paare auf einen Blick.** Eltern öffnen die Seite primär,
um zu sehen, **welcher Panel-Controller welches Display steuert** — z. B. „mit
welchem Panel bediene ich gerade das Wohnzimmer-Display?". Das Paar steht
deshalb in einer **Hero-Sektion am Seitenkopf**, prominent und ohne Suche
auffindbar; die übrigen Sorten kommen darunter als sekundäre Liste.

**Route / Manifest / Sorte:**
- Pfad: **`/api/v1/seiten/uebersicht`** — neben der Registry-API unter URL-4
  (`/api/v1/<resource>/<aggregat>`), Konsistenz mit ROU-14 (`/api/v1/diag` als
  HTML-Aggregat im Router). Ausgeliefert vom selben Service `xbuddy-seiten`,
  der auch `GET /api/v1/seiten` antwortet — kein neuer Port; der nginx-Eintrag
  für `/api/v1/seiten` muss die Sub-Pfade mit abdecken (Deploy-Detail).
- Eintrag (SREG-1 Sorte b mit Platform-Eigentümer): Quelle ist ein neues
  **`seiten/views.json`** (BUD-3-Schema), das die Übersichts-Seite mit
  `pfad: /api/v1/seiten/uebersicht`, `app: seiten`, `slug: uebersicht`,
  `label: "Alle Seiten"`, `zielgruppe: "eltern"` listet. Die Übersicht listet
  sich darüber **selbst** — kein handgepflegter Sonderfall im Aggregator.

**Layout (V1, von oben nach unten — nach Gate B Wahl 2026-06-08
„gemeinsame Box pro Geräte-Paar"):**

1. **Suchfeld** (Volltextsuche, clientseitig, filtert alle Sektionen live).
2. **Hero-Sektion „Geräte-Paare"** (Hauptzweck):
   - Für jeden Display-Client mit `verknuepft_mit_panels: [<panel_id>, …]`
     (mindestens ein Eintrag) wird **eine gemeinsame Box** pro Paar gerendert
     — eine umschließende Container-Karte mit Header und visuell klarer
     Außengrenze (Box-Rahmen + abgesetzter Hintergrund), die als
     zusammengehörige Einheit lesbar ist:
     - **Header der Box**: Display-Identifier prominent (`📺 <display_id>`)
       + Sub-Zeile „wird gesteuert von N Panel(s)".
     - **Display-Karte oben** in der Box (Display-Pfad + zwei kopierbare URLs).
     - **Visueller Trenner** („↑ Display · Panel-Controller ↓") als
       Hierarchie-Marker.
     - **Panel-Controller-Karten unten** in der Box, als Grid (je Panel-
       Instanz eine Hauptkarte). Die Panel-Instanz (Sorte d,
       `/controller/app-panel/<panel_id>`) ist die Hauptkarte — der eigentliche
       Steuerer — **nicht** der Editor.
     - **Editor-Anhang** an jeder Panel-Karte (gestrichelter Trenner +
       gepunkteter linker Rand): „✏ Bearbeiten" mit den beiden Editor-URLs
       (Heim/Tailscale). Der Editor ist **visuell innerhalb** der Panel-Karte
       als Sub-Element angedockt, nicht als separate Geschwister-Karte —
       damit die Hierarchie Display ↔ Panel ↔ Editor sichtbar wird.
       Datenquelle: `verknuepft_mit_panel` am Editor-Eintrag (SREG-4).
   - Reihenfolge: Displays alphabetisch nach `display_id`.
   - *Wenn* kein Display ein gekoppeltes Panel hat (Kaltstart, oder keine
     Panels angelegt), *dann* fehlt der Hero-Block; ein Hinweis „Noch keine
     Geräte-Paare angelegt" reicht — keine leere Box.
3. **Sekundäre Sektion „Andere Seiten"**, nach **Buddy/App gruppiert**:
   - Pro `app`-Slug (= BUD-1-Buddy oder Platform-Service mit
     `seiten/views.json`) wird **eine gemeinsame Buddy-Gruppe** gerendert
     — Rahmen mit Header (Slug im Monospace mit führendem `/`, Anzahl Views
     als Sub-Hinweis), Karten als Grid innerhalb des Rahmens.
   - **Varianten** (`varianten[]` an einem Eintrag) erscheinen als
     **Geschwister-Karten** innerhalb derselben Buddy-Gruppe — eine eigene
     Karte je Variante mit eigenem `label`, eigenem `icons[]` (falls in der
     Variante überschrieben, sonst Eintrags-Icons), vollem `pfad` + `query`-
     Anhängung (z. B. `/display/plan/woche?ansicht=klein`). Visuelle
     Variant-Markierung: gestrichelter linker Rand + „Variante"-Tag im Titel.
   - **Snapshot-Sorten (d/e) ohne `app`-Feld** werden in einer Sammelplatz-
     Gruppe „instanz" gerendert, falls sie nicht im Hero (= ungepaart) sind.
   - **Typ-Filter-Chips** „Alle · Anzeigen · Eltern · Controller · Panels ·
     Displays" wirken über Karten hinweg; Buddy-Gruppen, deren Karten alle
     ausgefiltert sind, werden ebenfalls ausgeblendet.
   - Reihenfolge der Buddy-Gruppen: Anzahl Karten absteigend, dann
     alphabetisch.

**Mockup-Referenz für Gate B:** statische HTML-Mockups gegen Live-Inventar
(`/api/v1/seiten` + `panels.json`) wurden 2026-06-08 erzeugt, drei Varianten
gerendert (V1 Zwei-Spalten, V2 gemeinsame Box, V3 Verbinder-Chip). Nic-Wahl:
V2. Die hier spezifizierten Layout-Pflichten entsprechen V2-Reconcile.

**Inhalt je Karte (Pflicht):** `label` · `zeigt` (1 Satz) · `icons[]` (oder
Fallback, s. u.) · `typ`-Badge · **zwei kopierbare URLs** mit Copy-Button:
- **„Heim"** = `display_url_origin_heim` + `pfad` (SREG-7)
- **„Tailscale"** = `display_url_origin_tailscale` + `pfad` (SREG-7)

*Wenn* `display_url_origin_tailscale` leer ist, *dann* wird die Tailscale-Spalte
**weggelassen** und ein einmaliger Banner-Hinweis am Seitenkopf erklärt, dass
nur die Heim-Variante verfügbar ist.

**Varianten:** ein Eintrag mit `varianten[]` (SREG-1) rendert **je Variante eine
eigene Karte** mit der vollständigen `query`-Anhängung am Pfad (z. B.
`/display/plan/woche?ansicht=klein`); die Default-View bleibt ihre eigene Karte.

**Kopier-Mechanik:** Copy-Button je URL (Click → Zwischenablage, kurzer
Erfolgs-Toast). Langes-Drücken am Handy auf den Link-Text muss zusätzlich
**funktionieren** (nativer Browser-Kontextmenüpfad „Link kopieren") — das
verbietet `pointer-events: none`/`user-select: none` auf den `<a>`-Inhalten.
Beide Pfade (Copy-Button **und** Long-Press) sind explizite V1-Anforderung,
damit Eltern die für sie gewohnte Geste nutzen können.

**Suche:** Volltextsuche (clientseitig) gegen `label`, `synonyme[]`, `zeigt` —
ein Eingabefeld am Seitenkopf, Live-Filter. Suche wirkt auf alle Sektionen.
**Kontext-Erhalt** an zwei Stellen:
- **Hero-Paar-Box bleibt sichtbar**, wenn entweder das Display, eine
  Panel-Instanz **oder** ein Editor-Anhang in der Box den Suchbegriff trifft
  — sonst verliert man die Paar-Information.
- **Buddy-Gruppe expandiert komplett**, wenn der Suchbegriff im Gruppen-
  Header (`app`-Slug) trifft (z. B. „wetter" zeigt **alle** Wetter-Views in
  der Gruppe); andernfalls werden Karten gefiltert und die Gruppe wird nur
  ausgeblendet, wenn keine Karte mehr passt.

**Icon-Fallback** (SREG-4-Lücke: Sorten b/c/d/e tragen meist kein `icons[]`):
- Sorte b/c (Eltern-Settings, Controller): generisches Default-Piktogramm aus
  `seiten/static/icons/<typ>.png` (kleine B-Liste in der Implementierung).
- Sorte d/e (Panel-Instanz, Display-Client): Default-Piktogramm + die `key`
  als Untertitel der Karte (Panel-/Display-ID).
- *Nicht* den `icons_erforderlich`-Schalter (SREG-10) bemühen — der gehört zum
  Aggregator-Manifest-Bau, nicht zur Anzeige-Schicht.

**Datenquelle:** ausschließlich `GET /api/v1/seiten` aus dem **eigenen Service**
(in-process oder localhost-Loop, kein externes Netz). Die Seite ist eine
**Templating-Schicht über `inventar.json`** — keine eigenen Daten, keine zweite
Wahrheit (CLAUDE.md §6). Aktualität folgt SREG-3 (TTL ≤ 30 s).

**Auth/Exposure:** erbt SREG-6 — EC-2-Mitgliedschaft + Netzgrenze, kein
zusätzliches Auth-Gate, kein `intern`-Flag.

**Vertikale Scheibe (Abend-Test):**
1. Eltern öffnen `<heim-origin>/api/v1/seiten/uebersicht` am Handy.
2. **Ohne Suche/Filter** sehen sie sofort die Geräte-Paar-Boxen am
   Seitenkopf: eine Box pro Display, mit Header „📺 <display_id> · wird
   gesteuert von N Panel(s)", Display-Karte oben in der Box, darunter die
   Panel-Controller-Karten als Grid; an jeder Panel-Karte ein angedockter
   „✏ Bearbeiten"-Anhang mit zwei Editor-URLs (Heim/Tailscale).
3. Klick auf Copy-Button „Tailscale" am Editor-Anhang einer Panel-Karte →
   URL in Zwischenablage → in einen anderen Browser-Tab am Laptop einfügen
   → die `/controller/app-panel/<panel_id>/bearbeiten`-Seite öffnet sich.
4. Suche „wetter" expandiert die `wetter`-Buddy-Gruppe in der sekundären
   Sektion (alle Views der `app: wetter` werden sichtbar — `heute` +
   `regeln`); andere Buddy-Gruppen blenden aus; gepaarte Geräte-Paar-Boxen
   im Hero ohne Wetter-Bezug verschwinden ebenfalls.
5. Suche „kleinkind" zeigt nur die Plan-Variant-Karte
   `/display/plan/woche?ansicht=klein` in der `plan`-Buddy-Gruppe; die
   Default-Wochenplan-Karte daneben verschwindet (Variant-Match unabhängig
   vom Default).

**Pfad-Stabilität:** `/api/v1/seiten/uebersicht` ist mit der Ratifizierung
2026-06-08 nach URL-8 dauerhaft.

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
  eine App-Discovery-Petrantwortung + nochmal ein Fehler-/Snapshot-Modell. Der
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

### E-SREG-1.b — Verworfene URL-Genres für SREG-12 (Berater-Runde 2026-06-08)
Die Frage „wo wohnt die Übersichtsseite" lief durch eine Berater-Runde mit
Codex-Antiberater. ENTSCHEID:
`brainstorm/berater-runde/20260608-RATIFIZIERT-seiten-uebersicht-platform-genre.md`.
Verworfen:
- **A — `/display/_shared/eltern/seiten/uebersicht`**: mischt Adressat (Eltern)
  mit Eigentümer (Platform-Service); URL-16 ist read-only Asset-Genre.
- **A' — `/display/_shared/_ui/seiten`**: bricht URL-6 (Underscore-Verbot
  außer für den bestehenden Sonderfall `_shared`); vergiftet URL-16
  (read-only Asset-Genre); braucht ohnehin nginx-Block, weil `xbuddy-seiten`
  separater Prozess.
- **B / B' — neues Top-Level `/platform/<service>/<view>`**: würde URL-1
  (drei Top-Level: `/display/`, `/controller/`, `/api/v1/`) bei n=1 erweitern
  und eine neue Konvention auf Vorrat anlegen (CLAUDE.md §6 verbietet das).
- **C — „Platform-Buddy"-Klasse PBUD-* mit eigenem Manifest-Genre**: Manifest-
  Schicht analog BUD-3 für eine einzige Seite ist Architecture Astronaut.
- **D-pur — `/api/v1/seiten` mit Content-Negotiation (HTML/JSON je Accept-Header)**:
  Tools/Telegram-Vorschau/curl sehen je nach Accept-Header anderes, UX-Reibung
  bei Eltern. Außerdem versteckt es den Sortenunterschied „HTML-Schwesterview"
  unter einer Identitäts-URL.
- **E — `/controller/seiten/uebersicht`**: `/controller/` ist URL-11
  „Controller-Aktion", nicht „Platform-Admin"; bricht das Genre-Versprechen.

Ratifiziert: **D' — `/api/v1/seiten/uebersicht` als HTML-Schwester** zu
`/api/v1/seiten` (JSON). Begründung Nic: „view ist eine alternative Darstellung
der Registry, also sollte neben der Registry wohnen". Präzedenz ROU-14
(`/api/v1/diag` HTML im Router unter URL-4 als „Diagnose zählt zum
Hub-Backend"), analog: „Übersicht zählt zum Seiten-Registry-Backend".

Verworfene Verknüpfungs-Mechaniken:
- **Co-Lokations-Verknüpfung als V1** („Panel + Display laufen auf demselben
  Hardware-Gerät"): heute kein Schema-Halt — GER trägt keine `panel_id`-Rück-
  Referenz. **Folge-Aufgabe**, nicht V1; bis dahin trägt die logische
  Verknüpfung (PREG `display_id`, SREG-4 `verknuepft_mit_display`) den
  Eltern-Nutzen voll.
- **Hardcoden statischer Paare** (statische Paar-Liste neben `seiten/`):
  verworfen, weil unnötig — PREG-Pflichtfeld `display_id` trägt die
  Information bereits. Hardcoden wäre eine handgepflegte Zweitliste
  (CLAUDE.md §6 verboten).
