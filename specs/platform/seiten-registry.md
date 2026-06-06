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

- **Aufbau des Inventars:** Der Service liest beim Start und periodisch (bzw.
  on-demand mit kurzem TTL) die Manifeste (Platte) + Panel-/Geräte-Snapshots und
  schreibt `inventar.json` (atomar, DCOMP-4).
- **`GET /api/v1/seiten`** (URL-4, eigene URL-14-Zeile) serviert **immer aus
  `inventar.json`** — **keine** Upstream-Calls im Request-Pfad, Laufzeitbudget
  **< 50 ms**. Ein langsamer/defekter Buddy blockiert die Auskunft nie.
- **Fehlermodell (Last-Known-Good, analog ROU-27):** Manifest-Sorten (a/b/c)
  sind immer vollständig (Platte). Für (d/e) gilt bei Timeout/500 eines
  Upstreams: der **letzte erfolgreiche Teil-Snapshot** bleibt erhalten und wird
  als `stale: true` markiert — **nie** eine leere/falsch-gekürzte Liste,
  DCOMP-3.

## SREG-4 — Eintrags-Schema
Jeder Eintrag in `inventar.json` trägt:

| Feld | Pflicht | Bedeutung |
|------|---------|-----------|
| `key` | ja | stabiler Slug (IDENT-1), z. B. `wetter-regeln` — für die KI-Auflösung; nie neu vergeben |
| `quelle` | ja | Sorte `a..e` bzw. `app`/`controller`/`panel`/`display` |
| `app` / `instanz` | ja | App-Slug (a–c) bzw. Instanz-ID (d/e) |
| `pfad` | ja | View-Pfad, z. B. `/display/wetter/regeln` — **nicht** die volle URL |
| `label` + `synonyme[]` | ja | deutsch, für „wo stelle ich X ein" (KI-Auflösung) |
| `varianten[]` | nein | endliche bekannte Varianten (`slug`, `query`, `label`) |
| `zeigt` | ja | 1 Satz, was die Seite zeigt |
| `zielgruppe` | ja | `kind` / `eltern` — **deskriptiv**, KEIN Berechtigungs-Gate (SREG-6) |

Die **volle URL wird nicht gespeichert** — sie entsteht erst beim Konsumenten
aus `display_url_origin + pfad` (URL-12: eine Origin; der Pfad ist die Wahrheit,
die Origin ist Per-Instanz-Deployment).

## SREG-5 — Skill `seiten_finden` (Lese-Klasse)
Eltern-Chat-READ-Skill (RAT-6 Lese-Klasse, kein Schreibdialog), trigger-
agnostische Funktion analog `termine-erfragen.md` (TER). Zwei Modi:
- **„gib mir den Link zu X"** — die KI matcht die Frage gegen `label`/`synonyme`
  der Einträge; bei Mehrdeutigkeit gezielte Rückfrage (EC-22-Muster).
- **„liste alle Seiten" / „alle Seiten von Buddy Y"** — gefilterte Liste.

Der Link wird aus `display_url_origin` + `pfad` gebildet (GAA-3.7-Muster, wie
`panel_anlegen` die Controller-URL bildet). Der Skill liest die Registry über
`GET /api/v1/seiten` (Origin = ein neues `seiten_origin_url`, EC-15).

## SREG-6 — Auth/Exposure: der Kanal ist das Gate, keine Rolle
V1 kennt **keine Rollen** (EC-3). Die Berechtigung ist die **Netzgrenze**
(RAT-2) **plus der Kanal**: `seiten_finden` läuft **nur im Eltern-Chat**, einem
eltern-seitigen Kanal, zu dem Kinder keinen Zugang haben (Nic-Entscheid
2026-06-06). Damit kann „liste alle Seiten" einem Kind **nicht** versehentlich
den schreibenden Eltern-Editor (`/display/wetter/regeln`) zeigen — die
schützende Grenze ist der Kanal, nicht ein Sichtbarkeits-Flag.
**Annahme (gültigkeitskritisch):** die Eltern-Chat-/Familien-Gruppe hat **keine
Kind-Mitglieder**. Kippt das je, ist die Exposure-Frage neu zu stellen (dann
wäre ein `intern`-Flag oder eine echte Rolle fällig) — bis dahin **kein**
Flag/Rollen-Vorbau (CLAUDE.md §6). `zielgruppe` bleibt rein deskriptiv.

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
- **Schnelle, nie-leere Antwort:** `GET /api/v1/seiten` antwortet aus
  `inventar.json` ohne Upstream-Call; bei Panel-/Geräte-Snapshot-Ausfall
  `stale: true` statt leerer/gekürzter Liste (SREG-3).
- **Varianten:** ein Eintrag mit `varianten[]` löst sowohl Default als auch
  Variante auf; `?ab=<datum>` erzeugt keinen Eintrag (SREG-1).
- **(e)-Filter:** Geräte-Snapshot mit `controller`/`display`/`beides`/`inaktiv`
  → nur `display|beides` & `aktiv` erscheinen (SREG-1).
- **Skill-Auflösung:** „Link zum Garderoben-Editor" → `/display/wetter/regeln`
  mit `display_url_origin` zur vollen URL; Mehrdeutigkeit → Rückfrage (SREG-5).
- **Kanal-Gate:** `seiten_finden` ist nur im Eltern-Chat registriert (SREG-6).

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
