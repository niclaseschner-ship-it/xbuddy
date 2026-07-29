# Seiten-Registry — Spec     (ID-Präfix: SREG)

> ⚠️ **ZIEL-ZUSTAND geändert durch RAT-31 (2026-07-27) — Wirbelsäule-Abriss.**
> Setup ist fest **ein Gerät** (Heim-Shell). Damit entfallen die Multi-Geräte-
> Annahmen: die Übersicht (`/api/v1/seiten/uebersicht`, SREG-12) zieht ihre
> Kachel-Daten künftig aus den **committeten Buddy-View-Manifesten** statt aus
> den `panel/`- und `geraete/`-Registry-Snapshots, und das „Geräte-Paar"-Box-
> Modell (SREG-12) kollabiert auf ein Gerät. Der Aggregator-Umbau (E3, #1496)
> ist erfolgt; die `geraete/`-Registry ist mit **RAT-31 E6c (#1565)** gelöscht
> (`geraete.md` ENTFALLEN). Bis zum vollen Spec-Cleanup (#1499, E7) ist **RAT-31
> der bindende Ziel-Zustand**. Governance:
> `decisions/RAT-31-wirbelsaeule-abriss.md`, Epic #1339.
>
> Status: V1-Entwurf · Refs #347 #1339 · ratifiziert RAT-13 (berater-runde 2026-06-06), fortgeschrieben RAT-31
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

**V1-Scope (RAT-31 E3 Stand, #1496):** das Inventar der Manifest-Sorten a/b/c/f/g
(SREG-1) · Aggregator-Service `xbuddy-seiten` mit gecachtem `inventar.json`
(SREG-3) · eine **gerenderte Eltern-Übersichts-Seite** unter
`/api/v1/seiten/uebersicht` mit kopierbaren URLs je Eintrag (Heimnetz +
Funnel) · ein **Trigger-Skill `seiten_uebersicht`** im Eltern-Chat, der nur
diesen einen Link liefert (SREG-5 — Pivot). **Out-of-Scope V1:** das
Schreiben/Ausblenden einzelner Seiten über die Registry (sie ist rein lesend);
App-Discovery „was ist installierbar" (das ist #325, eigene Linie, SREG-8);
KI-Matching gegen `label`/`synonyme` im Chat (durch SREG-12-Seite +
Volltextsuche abgelöst). **RAT-31 E3 (#1496) entfernt:** Sorten d (Panel-Instanz)
und e (Display-Client), `panel_eintraege()`, `display_client_eintraege()`, alle
Verknüpfungs-Felder (`verknuepft_mit_display`/`verknuepft_mit_panels`/
`verknuepft_mit_panel`), `snapshot_pending`-Mechanismus (bleibt als `[]` in
der Antwort für Rückwärtskompatibilität).

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

**Fünf Sorten** aufrufbarer Seiten (RAT-31 E3: d/e entfernt), ein gemeinsames
Eintrags-Schema (SREG-4):

| Sorte | Beispiel | instanz-spezifisch | Wahrheitsquelle |
|-------|----------|--------------------|-----------------|
| (a) Display-View (Kind) | `/display/plan/woche` | nein | Buddy-Manifest (BUD-3) |
| (b) Eltern-/Settings-View | `/display/wetter/regeln`, `/api/v1/seiten/uebersicht` | nein | Buddy- **oder Platform-Service-Manifest** (BUD-3 analog: `<komponente>/views.json`) |
| (c) Controller-App | `/controller/figuren-erkennung/` | nein | Controller-Manifest (BUD-3) |
| ~~(d) Panel-Instanz~~ | ~~`/controller/app-panel/<panel_id>`~~ | ~~**ja**~~ | ~~`panels.json`-Snapshot (PREG)~~ — **entfernt RAT-31 E3 (#1496)** |
| ~~(e) Display-Client~~ | ~~`/display/<display_id>`~~ | ~~**ja**~~ | ~~Geräte-Registry-Snapshot (GER)~~ — **entfernt RAT-31 E3 (#1496)** |
| (f) Homescreen-PWA | `/seiten/plan/einstellungen` | nein | Buddy- **oder Platform-Service-Manifest** (`views.json`, typ: "pwa"); Form SREG-15 |
| (g) Mini-App (Telegram) | `/seiten/mini-app-uebersicht` | nein | Buddy- **oder Platform-Service-Manifest** (`views.json`, typ: "mini-app"); Form SREG-14 |

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

**RAT-31 E3 (#1496):** Die instanz-spezifischen Sorten (d)(e) — Panel-Instanz
(PREG-Snapshot) und Display-Client (GER-Snapshot) — sind entfernt. Der
Aggregator kennt nur noch die drei Manifest-Sorten a/b/c (plus f/g) und liefert
`snapshot_pending: []` für Rückwärtskompatibilität.

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
- **RAT-31 E3 (#1496) — kein Snapshot-Fehlermodell mehr:** Sorten (d/e) und
  der zugehörige Last-Known-Good-Mechanismus (`stale: true`, `snapshot_pending`)
  sind entfernt. Die Antwort enthält `snapshot_pending: []` für
  Rückwärtskompatibilität (externe Konsumenten lesen das Feld, ignorieren es).

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
| ~~`verknuepft_mit_display`~~ | ~~abgeleitet (Sorte d)~~ | **entfernt RAT-31 E3 (#1496)** — Sorte d existiert nicht mehr. |
| ~~`verknuepft_mit_panels[]`~~ | ~~abgeleitet (Sorte e)~~ | **entfernt RAT-31 E3 (#1496)** — Sorte e existiert nicht mehr. |
| ~~`verknuepft_mit_panel`~~ | ~~abgeleitet (Sorte b, SREG-11)~~ | **entfernt RAT-31 E3 (#1496)** — SREG-11 Panel-Editor-Einträge existieren nicht mehr. |

Die manifest-gelieferten Felder sind genau die BUD-3-Felder (`conventions/buddies.md`).
Die **volle URL wird nicht gespeichert** — sie entsteht erst beim Konsumenten
aus `display_url_origin + pfad` (URL-12: eine Origin; der Pfad ist die
Wahrheit, die Origin ist Per-Instanz-Deployment).

**RAT-31 E3 (#1496):** Sorten d/e existieren nicht mehr; die drei
`verknuepft_mit_*`-Felder sind entfernt. Alle Einträge kommen aus Manifesten
(Sorten a/b/c/f/g).

## SREG-5 — Skill `seiten_uebersicht` (Trigger, `web_app`-Launcher)

> **Pivot 2026-06-15 (Werft #678 → MAU):** Skill liefert nicht länger einen
> Text-Link auf SREG-12, sondern eine kompakte Bot-Nachricht +
> `web_app`-Inline-Button auf die Mini-App-Übersicht (MAU-1). Konsistent zu
> `einkauf_zeigen` (EZG-7) und `routine_anpassen_oeffnen` (RAO-6). Die alte
> Text-Link-Variante entfällt — Telegram ist der einzige Adapter (RAT-16),
> und alle berechtigten Eltern haben Telegram am Eltern-Endgerät
> (Setzung 2026-06-12 `project_xbuddy_telegram_endgerate_pflicht`).

Eltern-Chat-Skill — eine **lesende, trigger-agnostische** Funktion
(EC-9-Muster). **Nur EIN Modus**, kein KI-Matching, keine Rückfrage-Logik:
erkennt eine Frage-Familie wie „zeig mir alle Seiten", „welche Apps gibt
es", „Link zur Übersicht", „xbuddy öffnen" → returnt **einen** Tool-Result
mit kompakter Bot-Text-Antwort + Mini-App-`web_app`-Inline-Button. Das LLM
postet die Nachricht als einzigen Schreibakt des Turns (EC-29 — eine
Stimme im Agent-Turn). Die Pro-View-Auflösung („welche genau?") passiert
**in der Mini-App** per Karten-Liste, nicht im Chat — das hält den Chat
schlank und die Wartung in EINER View.

**Bot-Antwort-Form:**

- Text: kurze Begrüßung („Hier ist die Übersicht aller Seiten und Apps:").
- Inline-Button: Label **„🏠 xbuddy öffnen"**, `web_app: {url:
  <mau_url>}`, wobei `<mau_url>` aus seiten-Konfig (`mini_app_url`-
  Schlüssel analog EZG/RAO) gezogen wird.
- Berechtigung wie EZG-2: nur Telegram-User mit Status `Eltern`.

Der Skill ruft `GET /api/v1/seiten` **nicht** selbst auf — die Mini-App-
Übersicht (MAU-2) ist der einzige Konsument der Registry.

**Pivot-Begründung (Werft #678, Nic 2026-06-15):** Die Verlagerung vom
Text-Link-Skill auf den `web_app`-Launcher folgt dem Pattern der zwei
gebauten Mini-App-Launcher-Skills (`einkauf_zeigen` EZG-7,
`routine_anpassen_oeffnen` RAO-6) — Eltern erleben für alle Übersichts-/
Editier-Wege denselben einen Tap-Knopf-Stil im Chat. Die Komplexität wandert
aus dem Skill in die Mini-App-Übersicht (MAU), die das Inventar visuell
trägt; der Skill bleibt ein dünner Launcher.

*Tickets:* #467 (SREG-12), #551, #678 (Pivot)

## SREG-5b — Opt-in-Direktantwort (Sekundärpfad nach SREG-5)

> **Deprecated 2026-06-15 (Werft #678):** Mit dem SREG-5-Pivot auf den
> Mini-App-Launcher entfällt die Notwendigkeit der Opt-in-Direktantwort —
> die Mini-App-Übersicht selbst (MAU) ist der „eine Tap zu allen Seiten
> und Apps". SREG-5b-Code-Mechanik bleibt vorerst stehen (kein Entfern-
> Auftrag dieser Werft), wird aber im Implementierungs-Track inaktiv
> geschaltet (Skill antwortet ausschließlich mit dem Launcher-Button,
> kein Opt-in-Folge-Dialog). Reopen nur, wenn ein neuer Use-Case
> Direkt-Auflösung im Chat verlangt.


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

## SREG-7 — Display-URL-Origins: Funnel-only (seit #1458)

> **Nic-Setzung 2026-07-25 (#1458, enacted):** Self-signed-Tailnet-IP-Origins
> werden aufgegeben. Alle Geräte erreichen die Shell über den Funnel-FQDN
> (`buddyboard.demo-tailnet.ts.net`) mit LE-Zertifikat + Cookie. Die
> `display_url_origin_tailscale`-Slot wurde entfernt.

| Config-Schlüssel | Bedeutung | Default |
|---|---|---|
| `display_url_origin_heim` | Heimnetz-Origin für den Operator-Pi (LAN-Direktzugang, IP-Trust, kein Cookie; Bot-Default für SREG-5, tritt an die Stelle des bestehenden `display_url_origin`, GAA-3.7) | leer |
| `display_url_origin_funnel` | Funnel-FQDN-Origin (LE-Cert, extern erreichbar; für Familien-**User-Geräte** über den Funnel, AUTH-7b) — **RAT-27 (RATIFIZIERT 2026-07-07)** | leer |

**`display_url_origin_tailscale` entfernt** (Slot existiert nicht mehr in
`eltern-chat/config.py` nach #1458). `SEITEN_TAILSCALE_ORIGIN` wird in
`seiten/main.py` nicht mehr gelesen (`resolved_config` setzt den Wert immer
auf Leer-String). `tailscale_origin` bleibt als Parameter in `seiten/render.py`
und `configure()` für Rückwärtskompatibilität, wird aber ignoriert —
`urls.tailscale` ist in jeder Karte immer `None`, `tailscale_banner` ist immer
`True`. ENV-Variable `SEITEN_TAILSCALE_ORIGIN` am Pi kann Nic beim nächsten
Deploy-Aufräumen entfernen (kein Effekt mehr).

**V1-Pflicht:** `display_url_origin_heim` muss gesetzt sein, sonst kann der
SREG-5-Skill keinen tippbaren Link liefern und die SREG-12-Seite hat keine
„Heim"-Spalte. Fehlt `display_url_origin_funnel`, ist der externe
User-Geräte-Zugang nicht angeboten (kein Auto-Fallback — falsche Origin =
Cookie im falschen Jar + nicht-erreichbarer Link).

**Funnel-FQDN mit LE-Zertifikat** (`buddyboard.demo-tailnet.ts.net`-Muster,
`reference_tailscale_buddyboard`), über die **Familien-User-Geräte** die
Shell/Views erreichen (AUTH-7b). Der **Pairing-Redirect** (`/auth/pair`,
AUTH-2.a) muss **same-origin/relativ** bleiben — landet der
Cookie-Setz-Redirect auf einer anderen Origin als der aufrufenden PWA, sitzt
der `HttpOnly`-First-Party-Cookie im falschen Jar (AUTH-2 iOS-Persistenz-
Bedingung: PWA **und** `/auth/pair` auf **derselben** Funnel-FQDN).

**Zuordnung Gerät → Origin:** Operator-Pi (AUTH-7a) nutzt heim (LAN-IP-Trust,
kein Cookie); Familien-User-Geräte (AUTH-7b) bekommen ausschließlich die
Funnel-Origin.

**Migration des existierenden `display_url_origin`** (`eltern-chat/config.py`,
GAA-3.7): Doppel-Akzeptanz bleibt — `display_url_origin_heim` hat Vorrang,
fällt auf `display_url_origin` zurück. Folge-Aufräum via separatem Ticket.

**OPEN-EC-Origin** (eltern-chat.md EC-15) bleibt der Auflöse-Track für den
Onboarding-/Config-Schritt, der diese Werte aus der Hub-Auslieferung zieht.

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
- **Kaltstart:** kein `inventar.json` + Buddy-Prozesse aus → `GET` liefert die
  Manifest-Sorten (a/b/c/f/g) vollständig; Antwort gültig und **nie leer**
  (SREG-3). `snapshot_pending: []` für Rückwärtskompatibilität.
- **Kaputtes Manifest:** ein `views.json` mit JSON-/Pflichtfeld-Fehler → wird
  übersprungen (Warnung), das übrige Inventar bleibt vollständig (SREG-3/DCOMP-3).
- **Aktualität/TTL:** ein während des Betriebs neu committetes Manifest
  erscheint **binnen TTL** in `GET /api/v1/seiten` (SREG-3).
- **Schnelle, nie-leere Antwort:** `GET /api/v1/seiten` antwortet aus
  `inventar.json` ohne Upstream-Call; Antwort nie leer (SREG-3).
  ~~`stale: true` bei Snapshot-Ausfall~~ — entfernt RAT-31 E3 (#1496).
- **Varianten:** ein Eintrag mit `varianten[]` löst sowohl Default als auch
  Variante auf; `?ab=<datum>` erzeugt keinen Eintrag (SREG-1).
- **Icon-Durchreichung + Schalter:** ein Sorte-a-Manifest mit `icons[]`
  (+ `varianten[].icons[]`) erscheint byte-gleich im Eintrag; bei
  `icons_erforderlich=false` bleibt eine View ohne `icons[]` gelistet (Warnung),
  bei `icons_erforderlich=true` wird genau diese View übersprungen (Rest bleibt);
  Sorten b/c/f/g tragen kein `icons`-Feld (SREG-10). ~~d/e~~ — entfernt RAT-31 E3.
- ~~**Editor-Eintrag je Panel** (d/e, SREG-11)~~ — **entfernt RAT-31 E3 (#1496)**.
- ~~**(e)-Filter** (Geräte-Snapshot)~~ — **entfernt RAT-31 E3 (#1496)**.
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
  JSON-only. Manifest-Sorten a/b/c/f/g nach Buddy/App gruppiert (SREG-12).
  ~~Hero-Sektion „Geräte-Paare"~~ — **entfernt RAT-31 E3 (#1496)**.
- ~~**Geräte-Paar Aggregator** (d/e + Verknüpfungs-Felder)~~ — **entfernt RAT-31 E3 (#1496)**.
- ~~**Paar-Hero rendert (V2 nach Gate B)**~~ — **entfernt RAT-31 E3 (#1496)**.
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
- **Volltextsuche (Karten-Match):** Eingabe „garderobe" filtert Karten auf
  passende Einträge (Match gegen `label`/`synonyme`/`zeigt`) — clientseitig,
  keine Server-Roundtrip (SREG-12).
- **Volltextsuche (Buddy-Header-Match):** Eingabe „wetter" matcht den
  Gruppen-Header und macht **alle** Karten der Wetter-Gruppe sichtbar
  (Kontext-Erhalt), auch wenn einzelne Karten den Suchbegriff im
  `label`/`synonyme` nicht tragen würden (SREG-12).
- ~~**Hero-Paar-Kontext-Erhalt**~~ — **entfernt RAT-31 E3 (#1496)** (keine Hero-Boxen mehr).
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
**nur von Display-Views (Sorte a)** (BUD-4). Die Sorten b/c/f/g tragen
**kein** `icons` — das Feld **fehlt** (nicht `null`).
**RAT-31 E3 (#1496):** Sorten d/e entfernt; ihr Icon-Fehlen ist damit nicht
mehr relevant.

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
löst — alle bestehenden Varianten sind vollständig gebackfillt. **Verworfen:** Variante folgt demselben `icons_erforderlich`-
Schalter (Weg B aus #440) — Vorrats-Mechanik ohne Trigger.

## SREG-11 — Editor-Eintrag je Panel-Instanz (**entfernt RAT-31 E3, #1496**)

> **RAT-31 E3 (#1496) — entfernt.** Sorte d (Panel-Instanz) und die abgeleiteten
> Panel-Editor-Einträge existieren nicht mehr. `panel_eintraege()` ist aus dem
> Aggregator entfernt. Der zugehörige Test-Block (SREG-11-Tests) ist entfernt.
> Konsumenten-Pfad `specs/platform/panel-bearbeiten.md` PBE-2 ist durch
> RAT-31 nicht mehr relevant.

## SREG-12 — Gerenderte Eltern-Übersichts-Seite (HTML, neben der Registry-API)

> **Werft #678-Klarstellung 2026-06-15:** SREG-12 bleibt **als Tablet-
> Browser-View** für den Einrichtungs-Use-Case (Direkt-Zugriff am Pi-Tablet,
> das kein Telegram hat). Die Telegram-Mini-App-Variante derselben Übersicht
> ist MAU (`specs/platform/mini-app-uebersicht.md`). Beide Views ziehen aus
> demselben Aggregator-Inventar (`seiten/aggregator.py` `baue_inventar`) —
> kein Doppel-Wahrheit, keine Doppel-Pflege. Kein Spec-Delta am Layout/
> Render von SREG-12 in dieser Werft.

Die V1-Antwort auf „wo finde ich die Seiten" ist **eine eigene HTML-Seite** im
seiten-Service. Sie listet das gesamte Inventar aus `inventar.json` (SREG-3)
auf, und ist für **Eltern am Handy** gebaut (Tablet/Phone, Daumen-bedienbar).
Sie ist die **alternative Darstellung** der Registry — Daten liegen in
`/api/v1/seiten` (JSON), Rendering unter `/api/v1/seiten/uebersicht` (HTML).
Eine Datenquelle, zwei Darstellungen.

**RAT-31 E3 (#1496) — Hauptzweck geändert:** Die Hero-Sektion „Geräte-Paare"
(ursprünglicher Hauptzweck der Seite) ist entfernt — sie setzte Sorten d/e
voraus, die durch RAT-31 E3 wegfallen. **Neuer Hauptzweck:** Inventar aller
aufrufbaren Manifest-Seiten (Sorten a/b/c/f/g) auf einen Blick, nach
Buddy/App gruppiert, mit kopierbaren URLs. Volltextsuche filtert live.

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

**Layout (RAT-31 E3, #1496 — manifest-only):**

1. **Suchfeld** (Volltextsuche, clientseitig, filtert alle Sektionen live).
2. ~~**Hero-Sektion „Geräte-Paare"**~~ — **entfernt RAT-31 E3 (#1496).**
   Setzte Sorten d/e mit Verknüpfungs-Feldern voraus; diese existieren nicht
   mehr. `hero_paare` ist immer `[]` im Layout-Kontrakt (Rückwärtskompatibilität).
3. **Sektion „Andere Seiten"**, nach **Buddy/App gruppiert**:
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
   - ~~Snapshot-Sorten (d/e) ohne `app`-Feld in Sammelgruppe „instanz"~~ —
     **entfernt RAT-31 E3 (#1496)** (Sorten d/e existieren nicht mehr).
   - **Typ-Filter-Chips** „Alle · Anzeigen · Eltern · Controller" wirken über
     Karten hinweg; Buddy-Gruppen, deren Karten alle ausgefiltert sind, werden
     ebenfalls ausgeblendet.
   - Reihenfolge der Buddy-Gruppen: Anzahl Karten absteigend, dann
     alphabetisch.

**Mockup-Referenz für Gate B:** statische HTML-Mockups gegen Live-Inventar
(`/api/v1/seiten` + `panels.json`) wurden 2026-06-08 erzeugt, drei Varianten
gerendert (V1 Zwei-Spalten, V2 gemeinsame Box, V3 Verbinder-Chip). Nic-Wahl:
V2. Die hier spezifizierten Layout-Pflichten entsprechen V2-Reconcile.

**Inhalt je Karte (Pflicht):** `label` · `zeigt` (1 Satz) · `icons[]` (oder
Fallback, s. u.) · `typ`-Badge · **kopierbare URLs** mit Copy-Button (Funnel-only
seit #1458, Nic-Setzung 2026-07-25):
- **„Heim"** = `display_url_origin_heim` + `pfad` (SREG-7)
- **„Funnel"** = `display_url_origin_funnel` + `pfad` (SREG-7, RAT-27) — *wenn* Wert konfiguriert

~~**„Tailscale"** = `display_url_origin_tailscale` + `pfad`~~ — **entfernt (#1458)**:
self-signed Tailnet-IP-Origins werden nicht mehr angeboten. Die Tailscale-Spalte
wird nie gerendert; ein Banner-Hinweis am Seitenkopf ist dauerhaft aktiv
(`tailscale_banner = True`).

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
**Kontext-Erhalt:**
- ~~Hero-Paar-Box-Erhalt~~ — **entfernt RAT-31 E3 (#1496)** (keine Hero-Boxen).
- **Buddy-Gruppe expandiert komplett**, wenn der Suchbegriff im Gruppen-
  Header (`app`-Slug) trifft (z. B. „wetter" zeigt **alle** Wetter-Views in
  der Gruppe); andernfalls werden Karten gefiltert und die Gruppe wird nur
  ausgeblendet, wenn keine Karte mehr passt.

**Icon-Fallback** (SREG-4-Lücke: Sorten b/c/f/g tragen meist kein `icons[]`):
- Sorte b/c/f/g (Eltern-Settings, Controller, PWA, Mini-App): generisches
  Default-Piktogramm aus `seiten/static/icons/<typ>.png`.
  ~~Sorte d/e~~ — **entfernt RAT-31 E3 (#1496)**.
- *Nicht* den `icons_erforderlich`-Schalter (SREG-10) bemühen — der gehört zum
  Aggregator-Manifest-Bau, nicht zur Anzeige-Schicht.

**SREG-12 V1.1 — Sourcing-Regel für `seiten/static/icons/<typ>.png`-Fallback-
Piktogramme** (Refs #585, ratifiziert 2026-06-11 nach Berater-/Antiberater-
Runde):

Die Fallback-Piktogramme in `seiten/static/icons/<typ>.png` werden nach
folgender Regel beschafft und dokumentiert:

- **Primäre Quelle (a)**: eine konkrete **ARASAAC-ID**, die zur gemeinten
  Typ-Semantik passt (z. B. `9165` „tablet" für `panel`, `11299`
  „fernbedienung" für `controller`). Die ID wird in
  `seiten/static/icons/SOURCES.md` notiert (Datei-Name, ARASAAC-ID,
  Cache-Wort, Datum). Das Bild wird **einmalig** aus der ARASAAC-Cache-Wurzel
  kopiert und committet — anders als bei der ICONS-Plattform (Per-Instanz-
  Cache, ICONS-2) ist der Asset hier **Repo-Static**. Es gibt **keine**
  „ICONS-Pipeline analog" — die zwei Klassen teilen nichts strukturell außer
  dem Wort „PNG".
- **Sekundäre Quelle (b)**: eine eigene Datei (gezeichnet, gekauft, gefunden)
  mit dokumentierter Lizenz. Die Lizenz wird in
  `seiten/static/icons/SOURCES.md` mit Quell-URL, Lizenz-Typ und Datum
  notiert. **Bilder ohne SOURCES.md-Eintrag dürfen nicht committet werden**
  (Pre-Merge-Probe).

**Verworfen:**

- Verzeichnis als PWA-Manifest-Icon-Heimat nutzen — siehe PWA-1
  (`conventions/pwa.md:21-51`): PWA-Manifest-Icons (PWA-2: 192/512/maskable)
  liegen pro PWA-Verzeichnis, nicht zentral. SREG-12-Fallbacks und PWA-Install-
  Icons sind zwei verschiedene Asset-Klassen (Berater-Runde 2026-06-10,
  Antiberater-Hash-Probe: alle Bytes verschieden).
- Eine zweite **externe Bild-Plattform** als systematische Hauptquelle
  (z. B. Noun Project, FontAwesome) — würde einen eigenen Werft-Lauf
  brauchen (E-ESSEN-6-Analog: extern = Werft-Pflicht).
- Lizenz-Information nur im PR-Body — read-only Geschichte, kein Fakt am
  Ort. Quelle/Lizenz/Datum lebt in `SOURCES.md` neben den Bildern selbst
  (CLAUDE.md §6: „Kein Fakt ohne Quellennachweis", am Ort des Fakts).

**Offen (Per-Instanz-Override für Familien-Branding):** Heute kein Override-
Pfad — alle Familien bekommen dieselben Repo-statischen Fallback-Bilder. Wenn
eine Familie eigenes Branding für ihre Seiten-Übersicht-Karten will, ist das
V2 (eigenes Ticket). Heute Vorrat-frei verworfen (CLAUDE.md §6 / RAT-7).

**NC-Klausel-Frage** (ARASAAC-CC-BY-NC-SA, ICONS-6): Für Repo-statische
Auslieferung an Familien-Tablets ist die Frage „nicht-kommerziell" anders
geschnitten als für Per-Familie-Cache (ICONS-Plattform). Die Frage bleibt
offen wie ICONS-6 sie für die Plattform offen lässt — vor kommerzieller
Nutzung beider Klassen muss sie geklärt werden. Hier kein zusätzlicher Schnitt.

*Tickets:* #585

**Datenquelle:** ausschließlich `GET /api/v1/seiten` aus dem **eigenen Service**
(in-process oder localhost-Loop, kein externes Netz). Die Seite ist eine
**Templating-Schicht über `inventar.json`** — keine eigenen Daten, keine zweite
Wahrheit (CLAUDE.md §6). Aktualität folgt SREG-3 (TTL ≤ 30 s).

**Auth/Exposure:** erbt SREG-6 — EC-2-Mitgliedschaft + Netzgrenze, kein
zusätzliches Auth-Gate, kein `intern`-Flag.

**Vertikale Scheibe (Abend-Test, RAT-31 E3):**
1. Eltern öffnen `<heim-origin>/api/v1/seiten/uebersicht` am Handy.
2. **Ohne Suche/Filter** sehen sie die Buddy-Gruppen aller Manifest-Seiten
   (Sorten a/b/c/f/g), nach App gruppiert mit kopierbaren Heim- und Funnel-URLs.
   ~~Geräte-Paar-Boxen~~ — entfernt RAT-31 E3 (#1496).
3. Klick auf Copy-Button „Heim" → URL in Zwischenablage → im Browser öffnen.
4. Suche „wetter" expandiert die `wetter`-Buddy-Gruppe (alle Views der
   `app: wetter` werden sichtbar — `heute` + `regeln`); andere Buddy-Gruppen
   blenden aus.
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

## SREG-14 — Mini-App-Sorte in `views.json` (typ: mini-app)

> Werft #678 (Funktion 3): neue Sorte für Mini-App-Manifest-Einträge. Vorher
> waren Mini-Apps nicht im Inventar führbar — die zwei gebauten Mini-Apps
> (essen-einkauf #653, routine-anpassen #728) lebten als Templates ohne
> Manifest-Eintrag. Mit SREG-14 melden sich Mini-Apps wie Buddy-Views
> (Lego-Mechanik SREG-2: `<root>/<app>/views.json` glob), das Inventar
> wird die EINE Wahrheit für SREG-12 und MAU.

Mini-Apps sind Eltern-Form-Faktor mit `initData`-Auth (`Authorization: tma
<initData>`-Header, **MAD-7** ratifiziert in `conventions/mini-app-design.md`)
und Telegram-WebView-Launcher. Sie werden in Buddy-`views.json` als **neuer
Sorten-Eintrag** deklariert — analog zu Sorten a/b/c, aber mit eigener
Form-Pflicht:

```json
{
  "slug": "einkauf",
  "typ": "mini-app",
  "pfad": "/api/v1/seiten/essen-einkauf",
  "label": "Einkaufsliste bearbeiten",
  "synonyme": ["einkaufen", "liste pflegen"],
  "zeigt": "Einkaufsliste bearbeiten — abhaken, hinzufügen, Wünsche übernehmen.",
  "zielgruppe": "eltern",
  "web_app": {
    "bot_env_var": "ELTERNCHAT_BOT_USERNAME",
    "app_short_name": "einkauf",
    "icons": ["arasaac/28339.png"]
  }
}
```

**Pflicht-Felder bei `typ: "mini-app"`:**

- `slug`, `pfad` (HTML-Render-Route), `label`, `synonyme`, `zeigt`.
- `zielgruppe = "eltern"` — Mini-Apps adressieren immer Eltern; kein
  anderer Wert erlaubt V1 (Validation-Error sonst).
- `web_app.bot_env_var`: Name der ENV-Variable, aus der der Aggregator
  den Bot-Username zieht (familien-spezifisch, geteiltes
  `EnvironmentFile=__XBUDDY_DATA__/eltern-chat/.env` analog MAD-9
  Token-Sharing).
- `web_app.app_short_name`: Telegram-Botfather-konfigurierter App-
  Short-Name (z. B. `einkauf`, `routine`, `uebersicht`).
- `web_app.icons[]`: Piktogramm-Liste analog Sorte a (SREG-10).

**Vom Aggregator abgeleitet (`_typ_for_view` Sonderfall):**

- `typ = "mini-app"` — **explizit aus dem Manifest**, nicht aus
  `zielgruppe` abgeleitet (Sonderfall in `_typ_for_view`; neue
  Konstante `TYP_MINI_APP = "mini-app"`).
- `web_app_url = https://t.me/${bot_username}/${app_short_name}` —
  komponiert beim Inventar-Bau, NICHT im Manifest gespeichert
  (URL-12-Disziplin: eine Origin, Konsument komponiert).
- `funnel_url = https://${funnel_domain}${pfad}` — Direkt-URL als
  Fallback für `window.location.href`-Wechsel (MAU-5).

**Schema-Validierung (`tools/views_manifest.py`):**

- `typ == "mini-app"` ohne `web_app.bot_env_var` ODER `app_short_name`
  → `ManifestError` (per-View-Skip, SREG-13).
- `typ == "mini-app"` mit `zielgruppe != "eltern"` → `ManifestError`.

**Migrations-Liste (im selben Spec-PR-Folge-Implementierungs-Track):**

Folgende `views.json`-Dateien werden im Implementierungs-Track gepatcht
(siehe MAU-Übergabe-Ticket Tracks A):

- `essen/views.json` — Eintrag für `essen-einkauf` Mini-App ergänzen.
- `routine/views.json` — Eintrag für `routine-anpassen` Mini-App
  ergänzen.
- `seiten/views.json` — Eintrag für `mini-app-uebersicht` (Selbst-
  Eintrag).
- `hoerspiel/views.json` — Eintrag für die `hoerspiel-eltern` Mini-App
  (Werft-Folge #848, Hörspiel-Eltern-Mini-App nach HSP-33). Vorlage:

  Pro Instanz ein eigener Eintrag mit kind_id-tragender `pfad`-Form
  (URL-3a, RAT-17, #965). V1: zwei Einträge:

  ```json
  {
    "slug": "eltern-mia",
    "typ": "mini-app",
    "pfad": "/seiten/hoerspiel/mia/eltern",
    "label": "Hörspiel pflegen (Mia)",
    "synonyme": [
      "hoerspiel-einstellungen",
      "voice ändern",
      "folge hören",
      "tempo",
      "mistral",
      "claude"
    ],
    "zeigt": "Hörspiel-Tuning (Voice, LLM-Anbieter/Modell, Tempo, Pausen) und Album-Galerie mit Multi-Track-Player für Mias Instanz.",
    "zielgruppe": "eltern",
    "web_app": {
      "bot_env_var": "ELTERNCHAT_BOT_USERNAME",
      "app_short_name": "hoerspiel",
      "icons": ["arasaac/5915.png"]
    }
  }
  ```

  (analog für Finn: `slug: "eltern-finn"`, `pfad: "/seiten/hoerspiel/finn/eltern"`,
  `label: "Hörspiel pflegen (Finn)"`).

  Begründung der Feld-Wahlen: Werft #848 ratifiziert die Eltern-Mini-App
  als HSP-33-Wohnort; #911 (2026-06-16) setzt Variante C — URL-parametrisch
  mit `<kind_id>` als zweitem Pfad-Segment (RAT-17). Botfather-`app_short_name`-
  Lego-Brille (`einkauf`, `routine`, `uebersicht` → single-word, kein
  Bindestrich) → `app_short_name = "hoerspiel"`.

  **Migration kind_id-Form (hoerspiel `alben`-Slug, #965):**
  Die ursprüngliche Absprache (`slug: "alben"`, `pfad: "/display/hoerspiel/alben"`,
  „bleibt unverändert") ist durch RAT-17 und den Mehr-Instanz-Cut obsolet.
  Die reale `hoerspiel/views.json` trägt seit #907/#908 zwei per-kind_id-Einträge:
  `slug: "alben-mia"` (pfad `/display/hoerspiel/mia/alben`) und
  `slug: "alben-finn"` (pfad `/display/hoerspiel/finn/alben`).
  Der Singular-Eintrag `slug: "alben"` mit Pfad `/display/hoerspiel/alben`
  **existiert nicht mehr** — er wurde durch die zwei kind_id-Einträge ersetzt.
  Diese Spec-Änderung ratifiziert den tatsächlichen Stand (#965).

Bestehende Einträge (essen `wunsch`, routine `morgen`, seiten
`uebersicht`) bleiben unverändert — Mini-App-Einträge kommen **neben** sie.
Hoerspiel-Einträge sind seit RAT-17 / #965 kind_id-getrennt
(`alben-mia`, `alben-finn`, `eltern-mia`, `eltern-finn`).

*Test (Aggregator):* `views.json` mit `typ: mini-app` → Eintrag im
Inventar mit `typ: "mini-app"`, `web_app_url` und `funnel_url` korrekt
komponiert. Fehlendes `app_short_name` → `ManifestError` + Eintrag
übersprungen (SREG-13), übrige Views des Manifests bleiben.

*Tickets:* #678 (Werft-Sammler), MAU-1..MAU-10 (Konsument), #708
(Auth-Härtung in derselben Werft mitgehärtet)

## SREG-15 — Homescreen-PWA-Sorte in `views.json` (typ: "pwa")

> ENTSCHEID-File 20260625-074425 Paket-Sektion „Call 1 (Sorte)" → typ:"pwa" jetzt
> ratifizieren, P2 als Schablone, BEWUSST MINIMAL + explizit erweiterbar.
> Erste Nutzung: Plan-Buddy Eltern-Einstellungs-Seite (PLAN-35).

Eine **Homescreen-PWA** ist ein Eltern-Formfaktor, der als installierbare
Web-App auf dem Home-Screen lebt (Manifest + Service-Worker) — **kein**
Telegram-WebView, **kein** `initData`. Sie wird in `views.json` als neuer
Sorten-Eintrag deklariert, analog zu den Sorten a/c und zur Mini-App-Sorte
(SREG-14), aber mit eigener Form-Pflicht.

**BEWUSST MINIMAL (Nic-Setzung 2026-06-25):** Diese Sorte trägt heute genau das,
was P2 braucht — Manifest/Service-Worker-Andockung und einen Auth-Slot. Sie ist
**explizit erweiterbar**: kommende typ:"pwa"-Exemplare (Wellen-Anfang, nicht n=1)
dürfen weitere Pflichtfelder zuziehen, ohne falsche Vorgriffe rausoperieren zu
müssen.

```json
{
  "slug": "einstellungen",
  "typ": "pwa",
  "pfad": "/seiten/plan/einstellungen",
  "label": "Plan-Einstellungen",
  "synonyme": ["petrantwortlichkeiten", "wer macht was"],
  "zeigt": "Default-Petrantwortlichkeiten je Slot und Wochentag setzen.",
  "zielgruppe": "eltern",
  "pwa": {
    "manifest": "/seiten/static/plan/manifest.json",
    "start_url": "/seiten/plan/einstellungen",
    "service_worker": "/seiten/static/plan/sw.js"
  },
  "auth": "public"
}
```

**Pflicht-Felder bei `typ: "pwa"`:**
- `slug`, `pfad` (HTML-Render-Route), `label`, `synonyme`, `zeigt`.
- `zielgruppe` — frei wählbar (`eltern` oder `kind`); **kein** Berechtigungs-Gate
  (SREG-6, deskriptiv). Anders als die Mini-App-Sorte (SREG-14), die auf `eltern`
  festgenagelt ist.
- `pwa.manifest` — Pfad zum Web-App-Manifest.
- `pwa.start_url` — Einstiegs-URL der installierten PWA.
- `pwa.service_worker` — Pfad zum Service-Worker.
- `auth` — Auth-Slot, Wertebereich **`"public"` | `"cookie"`** (Geräte-Cookie-
  Pairing nach AUTH-3, falls/wenn gehärtet). **`initData` ist hier NICHT zulässig**
  (das ist die Mini-App-Welt). V1 (P2): `"public"`.

**Abgrenzung — was diese Sorte NICHT ist:**
- **≠ `typ: "mini-app"` (SREG-14):** Mini-Apps laufen im Telegram-WebView mit
  `initData`-Auth und einem `web_app`-Block (Bot-Username, Botfather-Short-Name).
  Eine Homescreen-PWA hat **keinen** `web_app`-Block und **kein** `initData`.
- **≠ Eltern-/Settings-View (Sorte b):** Sorte b ist eine server-gerenderte
  HTML-View ohne installierbaren Mantel (kein Manifest/Service-Worker). Eine
  typ:"pwa" trägt den Homescreen-Mantel und ist installierbar.

**Vom Aggregator abgeleitet:**
- `typ = "pwa"` — **explizit aus dem Manifest**, nicht aus `zielgruppe` abgeleitet
  (Sonderfall analog SREG-14; neue Konstante, z. B. `TYP_PWA = "pwa"`).

*Tickets:* #1126 (Refs #259)

## SREG-16 — Ein Layout-Kontrakt (`/layout`) für alle Übersichts-/Registry-Oberflächen

> **Berater-Runde 2026-07-06 (#1210, RATIFIZIERT):** Anlass war der
> wiederkehrende Zwei-Sichten-Render-Drift (#1208 SHELL-10 landete nur in einer
> Oberfläche; #920 „MAU-UI-Drift"). Die Fang-Mechanik ist der Paritäts-Guard
> (SREG-9-Familie); SREG-16 ist die zugehörige **Struktur-Regel**, die den Drift
> an der Wurzel unmöglich macht statt ihn nur zu melden.

**Es gibt genau EINE Ableitung des angereicherten Layout-Baums:**
`render.baue_layout(inventar, heim_origin, tailscale_origin)`. Sie liefert die
Hero-Paare (Display↔Panel↔Editor↔Shell-URLs, SREG-11/SHELL-10), die
Buddy-Gruppen, die dedizierte Mini-App-Sektion (SREG-14), die Origin-URLs
(SREG-7) und die Icon-Auflösung (SREG-10) — fertig gruppiert und angereichert.

**Regel:**
- **Jede** familienseitige Übersichts-/Registry-Oberfläche konsumiert **diesen
  einen Kontrakt.** Der Server-Jinja-Pfad (`/api/v1/seiten/uebersicht`, SREG-12)
  rendert ihn direkt; die Telegram-Mini-App (MAU) holt ihn als JSON über
  **`GET /api/v1/seiten/layout`** und rendert **dumm** (nur Darstellung).
- **Keine Oberfläche re-derived Gruppierung/Anreicherung lokal.** Der frühere
  clientseitige MAU-Ableitungscode (Hero-Gruppierung, Editor-/Shell-Lookup,
  lokale URL-Bildung aus `window.location`) ist gelöscht — genau dort entstand
  der Drift.
- **Abweichende Sichten filtern deklarativ** über ein **`audience`-Feld je
  Karte** (`render.py` `AUDIENCE_UEBERSICHT` / `AUDIENCE_MINI_APP`), **nie per
  geforktem Ableitungscode.** Beispiel: Mini-Apps erscheinen in der Grossbild-
  Übersicht als gewöhnliche Buddy-Karte (pfad-URL), in der Mini-App aber in der
  dedizierten `mini_apps`-Sektion mit Telegram-Deep-Link — dieselbe Ableitung,
  zwei deklarativ gefilterte Sichten. Das ist die **einzige** legitime
  Sicht-Asymmetrie (Berater-Constraint 4); sie wird über `audience` gesteuert,
  nicht über einen zweiten Gruppierungs-Zweig.

**`/layout` ist ein Daten-Endpunkt, kein View** — Geschwister zu
`GET /api/v1/seiten` (SREG-3). Er listet sich darum **nicht** in `views.json`
(Ausnahme im Manifest-Eigentest, analog zum Inventar-Endpunkt selbst).

**Durchsetzung:** registry-abgeleiteter Paritäts-Guard (`test_render_parity.py`
+ `render_parity_dom.test.js`). Die erwartete Typ-Menge wird aus den
`TYP_*`-Konstanten des Aggregators (SREG-4/14) **aufgezählt**, nicht
handgepflegt — ein neuer Eintrags-Typ, der nur in einem Render-Pfad landet, wird
ROT (kein #1208-Blindfleck durch eine statische Liste).

*Tickets:* #1210 (Refs #1208, #920, #608) · Prozess-Wurzel xbuddy-prozess#80

## SREG-17 — App-Panel-Serving in seiten (verlagert vom Router, RAT-31 E6b)

> **RAT-31 E6b (#1564):** Das Servieren der App-Panel-Instanz-Views wird vom
> Router (ROU-24/ROU-27/PBE-1/PBE-2) nach seiten verlagert, damit `/shell/<id>`
> (SHELL-1) und der Rail-Iframe `/controller/app-panel/<id>/` (SHELL-3)
> **same-origin aus EINEM Service** kommen — kein Cross-Origin-Cookie-Jar, ein
> Auth-Gate, ein Deploy-Ort. Der Router-Serving-Code lebt bis zum Abriss #1568
> als toter Zwilling weiter (siehe router.md ROU-24/ROU-27-Marker); **produktiv
> serviert seiten** (nginx-Split `/controller/app-panel/` → `xbuddy_seiten`, vor
> dem allgemeinen `/controller/`-Router-Block).

**seiten serviert `GET /controller/app-panel/<panel_id>/` (HTML + Assets) und
proxyt die datentragenden Sichten an den panel-Service (127.0.0.1:5041):**

- `GET /controller/app-panel/<id>/` → `index.html` mit `__PANEL_ID__`- und
  `__BUILD_ID__`-Substitution (PANEL-2 / IDENT-5 / PANEL-14). Ohne Trailing-Slash
  → `301` auf `/<id>/` (relative Asset-Pfade, HTTP-Directory-Disambiguation).
- `config.json` / `tiles.json` → **Proxy** an `panel(5041)/api/v1/panels/<id>/<sicht>`
  mit **Last-Known-Good-Cache + Code-Default-Fallback** (`{}` bzw. `[]`,
  ROU-27-Verhalten 1:1, PANEL-8 stiller Fallback — kein Crash bei
  panel-Service-Ausfall).
- `bearbeiten` / `bearbeiten.js` / `bearbeiten.css` → **Proxy** an
  `panel(5041)/controller/app-panel/<id>/<sicht>` — **kein LKG**, `404`/`502`
  werden durchgereicht (PBE-1 / PBE-2).
- `sw.js` → Statik mit `__BUILD_ID__`-Substitution + `no-cache`-Headern (PANEL-14).
- alle übrigen Assets → Statik aus `controller/app-panel/` (die Datei-Ablage
  bleibt physisch am Ort) mit realpath-Traversal-Schutz.

**DCOMP-1 (Pflicht):** seiten liest die `panels.json` **nie** direkt und
importiert **nicht** `panel` — config/tiles kommen ausschliesslich über HTTP vom
panel-Service. Der panel-Service-Origin ist ein seiten-Runtime-Wert
(`--panel-service-url` / ENV `PANEL_SERVICE_URL`, Default `http://127.0.0.1:5041`).

**Auth:** die drei Routen tragen `require_dual_gate(mode=_AUTH_MODE)` — identisch
zum Router-Schalter (`XBUDDY_AUTH_MODE`, initial `observe`), damit die
Verlagerung das Auth-Verhalten nicht ändert (AUTH-7b / RAT-32).

**Durchsetzung:** `seiten/tests/test_app_panel_serving.py` (Serving-200,
config/tiles-Proxy + LKG-Fallback + Code-Default, bearbeiten-404-Passthrough,
sw.js-build_id, Traversal-404, DCOMP-1-kein-panel-Import).

*Tickets:* #1564 (Refs RAT-31, DCOMP-1; Router-Abriss #1568)

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
