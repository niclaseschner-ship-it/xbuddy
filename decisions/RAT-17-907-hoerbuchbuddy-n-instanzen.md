# RAT-17 — #907 Hörbuchbuddy: zwei explizite Instanzen Mia + Finn (handverdrahtet, keine Registry)

- **Entschieden:** 2026-06-15 (Architektur-Runde „Hörbuchbuddy-n-Instanzen",
  Berater + Codex-Antiberater, zwei Runden + Nach-R2-Verifikation per Live-Grep),
  **ratifiziert** 2026-06-15 (Nic: alle fünf Empfehlungen + Realitäts-Setzung).
- **Betrifft:** `specs/buddies/hoerspiel.md` (Mia → `<kind>`-Refactor, HSP-25/26
  mit `<kind_id>`-Owner, HSP-27 erweitert um `instance.json`-Schema, HSP-28a neu
  für zwei explizite Instanzen), `conventions/urls.md` (URL-3a dritte Zeile für
  HSP-25/26), `specs/platform/hoerspiel-folge-erzeugen.md` (HFE-3 `kind_id`-
  Lookup statt `MIA_ALTER`), `xbuddy-data/hoerspiel/<kind_id>/`-Daten-Layout,
  zweite systemd-Unit + zweiter Port + zweiter nginx-Origin + zweite Eltern-
  Chat-Origin. Keystone-Ticket **#907**; Sequenz-Tickets #908, #909, #910, #911,
  #912.
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/2026-06-15-2116-RATIFIZIERT-hoerbuchbuddy-n-instanzen.md`
  → Vorschlag `2026-06-15-2116-vorschlag-hoerbuchbuddy-n-instanzen.md`,
  Antiberater (Codex) `2026-06-15-2123-antiberater-hoerbuchbuddy-n-instanzen.md`.

## Beschluss

Der Hörbuchbuddy bekommt zwei explizite Instanzen Mia + Finn, **handverdrahtet**
über zwei systemd-Units, zwei Ports, zwei nginx-Origins und zwei Eltern-Chat-
Origins. **Keine** Instanz-Registry, **kein** Port-Offset-Algorithmus, **keine**
generische „Buddy-mit-n-Instanzen"-Konvention — die wäre antizipative
Generalisierung (n=1 für diese Klassen-Sorte, Routine + Kibuddy haben nur offene
Punkte für Per-Kind, nicht gebaut).

**Fünf konkrete Entscheidungen (ratifiziert):**

1. **Routing-Form (URL-3a):** Identität UNTER dem Klassen-Slug —
   `/api/v1/hoerspiel/<kind_id>/<resource>` und
   `/display/hoerspiel/<kind_id>/<view>`. Eingetragen als dritte URL-3a-Zeile
   neben ROU-20 und PANEL-2. Slug-Suffix-Form (`/display/hoerspiel-mia/…`)
   verworfen — sie würde BUD-1 (ein Buddy, ein stabiler Slug) brechen.
2. **Generik-Grad:** Option A handverdrahtet (Mia + Finn explizit überall),
   Option B (Registry mit erzeugtem Routing + Eltern-Chat-Auswahl) verworfen
   bis zur dritten Instanz oder zweiten Buddy-Klasse mit n Instanzen.
   **[AMENDIERT 2026-07-31 — Weg C, #1656]** Der Reaktivierungs-Trigger „dritte
   Instanz" **hat gefeuert** (emil ist live: `deploy/nginx/xbuddy-origin.conf`
   dritter Origin, `conventions/ports.md` Port 5056, `eltern-chat/config.py`
   `hoerspiel_url_origin_emil`). Die Wiederaufnahme ist aber **eng gescopet**:
   config-out betrifft **nur die read-only Instanz-LISTE + Klarnamen**, die heute
   4× dupliziert driften (belegt: `controller/app-panel/app.js:795` kennt emil
   NICHT, obwohl live) → EINE gitignored `instanzen.json` + generische
   `instanzen.example.json`, aus der die Backends **lesen**. Das von Option B
   verworfene **„erzeugte Routing"** (Port-Offset-Algorithmus, generierte
   nginx-Origins/systemd-Units/URL-Segmente) bleibt **verworfen** — Ports/Units/
   URL-Slugs bleiben **handverdrahtet**. Config-Guard als Vertrag: die Config
   **liest/zeigt**, generiert **nie** Routing/Ports (`conventions/instanzen.md`).
   Motiv: behobener Drift + „einfach adaptierbar für andere Familie" (Klon-Kosten
   senken, NICHT Multi-Tenancy — `apps.md:90` bleibt). Ratifiziert
   `brainstorm/berater-runde/20260731-0100-RATIFIZIERT-config-separation-weg-c.md`
   (Nic „ja b").
3. **Alter/Geburtsdatum NICHT in `familie.json`:** Entwicklungsstufe lebt in
   `xbuddy-data/hoerspiel/<kind_id>/instance.json` (z. B. `kognitiv_stufe`,
   `themen_je_alter`). Begründung **technisch belegt** (`familie/registry.py`
   `_parse_person`/`save` ignorieren unbekannte Felder → würden still beim
   nächsten FAA-Schreibvorgang verschwinden). FAM-3-Erweiterung um
   `geburtsdatum` ist eigene Runde, eigener zweiter Konsument.
4. **Migration SVC-5-konform:** `cp -a` Mia-Daten nach
   `xbuddy-data/hoerspiel/mia/`, Drop-In `20-data-path.conf` umstellen,
   Smoke-Test, **dann erst** Finn, **dann erst** alten Pfad entfernen.
   `mv`+Restic-Restore-Rollback verworfen — Restic ist Gürtel, nicht
   Rollback-Mechanismus.
5. **Bibel-V1 von Nic-Hand:** Kein LLM-Bible-Buddy-Flow in V1. Bible ist
   kreative Wurzel der Welt — Mia-Bibel hat Nic selbst aufgebaut, Finn-
   Bibel geht denselben Pfad. Bible-Buddy-Prompt-Flow ist V2-Verschönerung.

**Realitäts-Setzung (vorgelagerte Arbeiten, vom Antiberater aufgedeckt):**

- `hoerspiel/hoerspiel.service` existiert (Live-Grep bestätigt — Antiberater
  hatte falsch geraten, suchte im falschen Ordner). Aber: Service-Vorlage lag
  am Repo-Root (`xbuddy-hoerspiel.service`), brach BUD-1a wörtlich
  („Service-Vorlage neben dem Code"). Pattern-Bruch teilte sich mit Kibuddy
  (11 von 13 Buddies folgten der Konvention, 2 nicht). **Separater /watchdog-
  Befund**, kein Blocker hier — Finn-Service folgt dem bestehenden Pattern.
  **Aufgelöst durch #1014 (SVC-2-Move, 2026-06-21).**
- `deploy/hoerspiel/bootstrap.sh` ist Mia-hart — pro Instanz manuell
  initialisieren, **keine** Bootstrap-Petrallgemeinerung jetzt.
- Eltern-Chat-Skill `eltern-chat/skills/hoerspiel_folge_erzeugen.py:54`
  trägt `MIA_ALTER = 4` als Modul-Konstante (an drei Stellen verwendet).
  Spec selbst dokumentiert das als „V1 hart". Cross-Service-Schnitt: muss
  durch `kind_id`-Lookup ersetzt werden (#910).

**Bonus-Befund:** `HOERSPIEL_DATA_ROOT` ist heute schon ENV-parametrisiert
(`hoerspiel/config.py:32`, Drop-In `20-data-path.conf`). Migration im
Filesystem ist Drop-In-Switch + `cp -a`, **kein** Code-Change. URL-Pfad
`/display/hoerspiel/data/<sub>` ist zentral in `hoerspiel/album_manifest.py:16`
(`DISPLAY_DATA_PREFIX`) definiert — eine Funktion `f(kind_id)` reicht.

## Was die Runde explizit NICHT ratifiziert hat

- Konvention „Buddy-Klasse mit n Instanzen pro Pi" — braucht zweite gebaute
  Klasse mit n Instanzen (Kandidaten: Kibuddy, Routine — heute nur offene
  Punkte). Wiederaufnahme-Trigger: bei zweitem Buddy mit n Instanzen.
- Face-Pille-Konvention in `conventions/mini-app-design.md` (MAD) — n=0
  gebaute Beispiele für Petrantwortungs-Stempel-Variante; Eltern-Pille +
  Kinder-Pille (#911) werden erst n=1 bauen.
- FAM-3-Erweiterung um `geburtsdatum` — eigene Runde, zweiter Konsument nötig.
- Bootstrap-Generalisierung — n=1.

## Anti-Pattern-Check

- **Premature Generalization:** vermieden — keine Konvention vorab ratifiziert,
  Option A (handverdrahtet zwei) statt Registry.
- **Premature Mechanism (PW-37):** vermieden — URL-3a-Eintrag nutzt bestehende
  Konvention (ROU-20, PANEL-2 sind Präzedenz), keine neue Konvention erfunden.
- **Architecture Astronaut:** vermieden — die vier Andockpunkte (Port, URL,
  nginx, systemd) sind BUD-1a-Standard, keine neue Disziplin.
- **Industrie-Reflex (Multi-Tenancy-Service-Mehrmandanten):** vermieden —
  Hardware-Trennung pro Familie (apps.md:90) ist die anti-Reflex-Linie.

## Amendment 2026-07-31 — Weg C: Instanz-Liste + Klarnamen werden Config (#1656)

**Reaktivierungs-Trigger gefeuert.** Der in Pkt.2 gesetzte Wiederaufnahme-Trigger
„dritte Instanz" **hat gefeuert** — `emil` ist live: dritter nginx-Origin in
`deploy/nginx/xbuddy-origin.conf`, Port 5056 in `conventions/ports.md`,
`hoerspiel_url_origin_emil` in `eltern-chat/config.py`. Das ist eine
**lizenzierte** Wiederaufnahme (RAT-17 Pkt.2 nennt genau diesen Trigger), **keine
verbotene Re-Litigation**.

**Setzung (eng gescopet).** Die **read-only Instanz-LISTE + die Klarnamen** werden
aus dem Code in Config gehoben — sie driften heute 4× dupliziert
(`eltern-chat/tasks.py:43`, `seiten/main.py:1106`, `hoerspiel/config.py`,
`app.js`/`window.__HSP_INSTANZEN__`; belegt: `controller/app-panel/app.js` kennt
`emil` NICHT, obwohl live). Config-out geht in **eine gitignored
`instanzen.json`** (live) + eine getrackte generische **`instanzen.example.json`**,
aus der die Backends **lesen**.

**Technische Slugs BLEIBEN.** Kein Live-Rename von `mia`/`finn`/`emil` — sie
sind opake Strings, an nginx/systemd/URL/Cookie gekoppelt (atomar-oder-404). Der
Antiberater brach den Slug-Rename-Weg (C3) als Live-Betriebs-Bruch; er ist
verworfen.

**Config-Guard bekräftigt (Pkt.2, HART).** Die Config-Quelle **liest/zeigt** nur,
sie generiert **NIE** Ports/Routing/nginx/systemd. Der in Option B verworfene
Port-Offset-Algorithmus / das „erzeugte Routing" **bleibt verworfen**. `port` und
`origin` in der Datei sind **Lese-Spiegel** der handverdrahteten Realität
(`ports.md`/nginx bleiben SSoT für den Betrieb), kein Generator-Input.
Kill-Kriterium (übernommen aus der Runde): *„Config-Quelle will Ports/Routing
generieren → zurück."*

**C4-Anker (unverändert).** Config-out senkt Klon-Kosten für eine andere Familie,
ersetzt **NICHT** Ein-Pi-pro-Familie (`apps.md:90` /
`project_familie_2_3_eigener_bot`). RAT-4/Multi-Tenancy bleibt **zu**.

**Wo es landet.** Neue Konvention `conventions/instanzen-config.md`
(ID-Präfix `INST`, Config-nur-lesen als Vertrag) + `instanzen.example.json` /
`instanzen.json`. Backend-Migration folgt als **eigene Welle** nach Ratifikation.

**Evidenz.**
`brainstorm/berater-runde/20260731-0100-RATIFIZIERT-config-separation-weg-c.md`
(Nic „ja b", Antiberater-geprüft: C3 gebrochen, C2 gestärkt, C4-Anker gefixt).
Tickets: #1656 (Weg-C-Fundament), Part of #1309.
