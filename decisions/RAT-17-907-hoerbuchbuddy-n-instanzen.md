# RAT-17 — #907 Hörbuchbuddy: zwei explizite Instanzen Paula + Neko (handverdrahtet, keine Registry)

- **Entschieden:** 2026-06-15 (Architektur-Runde „Hörbuchbuddy-n-Instanzen",
  Berater + Codex-Antiberater, zwei Runden + Nach-R2-Verifikation per Live-Grep),
  **ratifiziert** 2026-06-15 (Nic: alle fünf Empfehlungen + Realitäts-Setzung).
- **Betrifft:** `specs/buddies/hoerspiel.md` (Paula → `<kind>`-Refactor, HSP-25/26
  mit `<kind_id>`-Owner, HSP-27 erweitert um `instance.json`-Schema, HSP-28a neu
  für zwei explizite Instanzen), `conventions/urls.md` (URL-3a dritte Zeile für
  HSP-25/26), `specs/platform/hoerspiel-folge-erzeugen.md` (HFE-3 `kind_id`-
  Lookup statt `PAULA_ALTER`), `xbuddy-data/hoerspiel/<kind_id>/`-Daten-Layout,
  zweite systemd-Unit + zweiter Port + zweiter nginx-Origin + zweite Eltern-
  Chat-Origin. Keystone-Ticket **#907**; Sequenz-Tickets #908, #909, #910, #911,
  #912.
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/2026-06-15-2116-RATIFIZIERT-hoerbuchbuddy-n-instanzen.md`
  → Vorschlag `2026-06-15-2116-vorschlag-hoerbuchbuddy-n-instanzen.md`,
  Antiberater (Codex) `2026-06-15-2123-antiberater-hoerbuchbuddy-n-instanzen.md`.

## Beschluss

Der Hörbuchbuddy bekommt zwei explizite Instanzen Paula + Neko, **handverdrahtet**
über zwei systemd-Units, zwei Ports, zwei nginx-Origins und zwei Eltern-Chat-
Origins. **Keine** Instanz-Registry, **kein** Port-Offset-Algorithmus, **keine**
generische „Buddy-mit-n-Instanzen"-Konvention — die wäre antizipative
Generalisierung (n=1 für diese Klassen-Sorte, Routine + Kibuddy haben nur offene
Punkte für Per-Kind, nicht gebaut).

**Fünf konkrete Entscheidungen (ratifiziert):**

1. **Routing-Form (URL-3a):** Identität UNTER dem Klassen-Slug —
   `/api/v1/hoerspiel/<kind_id>/<resource>` und
   `/display/hoerspiel/<kind_id>/<view>`. Eingetragen als dritte URL-3a-Zeile
   neben ROU-20 und PANEL-2. Slug-Suffix-Form (`/display/hoerspiel-paula/…`)
   verworfen — sie würde BUD-1 (ein Buddy, ein stabiler Slug) brechen.
2. **Generik-Grad:** Option A handverdrahtet (Paula + Neko explizit überall),
   Option B (Registry mit erzeugtem Routing + Eltern-Chat-Auswahl) verworfen
   bis zur dritten Instanz oder zweiten Buddy-Klasse mit n Instanzen.
3. **Alter/Geburtsdatum NICHT in `familie.json`:** Entwicklungsstufe lebt in
   `xbuddy-data/hoerspiel/<kind_id>/instance.json` (z. B. `kognitiv_stufe`,
   `themen_je_alter`). Begründung **technisch belegt** (`familie/registry.py`
   `_parse_person`/`save` ignorieren unbekannte Felder → würden still beim
   nächsten FAA-Schreibvorgang verschwinden). FAM-3-Erweiterung um
   `geburtsdatum` ist eigene Runde, eigener zweiter Konsument.
4. **Migration SVC-5-konform:** `cp -a` Paula-Daten nach
   `xbuddy-data/hoerspiel/paula/`, Drop-In `20-data-path.conf` umstellen,
   Smoke-Test, **dann erst** Neko, **dann erst** alten Pfad entfernen.
   `mv`+Restic-Restore-Rollback verworfen — Restic ist Gürtel, nicht
   Rollback-Mechanismus.
5. **Bibel-V1 von Nic-Hand:** Kein LLM-Bible-Buddy-Flow in V1. Bible ist
   kreative Wurzel der Welt — Paula-Bibel hat Nic selbst aufgebaut, Neko-
   Bibel geht denselben Pfad. Bible-Buddy-Prompt-Flow ist V2-Verschönerung.

**Realitäts-Setzung (vorgelagerte Arbeiten, vom Antiberater aufgedeckt):**

- `hoerspiel/hoerspiel.service` existiert (Live-Grep bestätigt — Antiberater
  hatte falsch geraten, suchte im falschen Ordner). Aber: Service-Vorlage liegt
  am Repo-Root (`xbuddy-hoerspiel.service`), bricht BUD-1a wörtlich
  („Service-Vorlage neben dem Code"). Pattern-Bruch teilt sich mit Kibuddy
  (11 von 13 Buddies folgen der Konvention, 2 nicht). **Separater /watchdog-
  Befund**, kein Blocker hier — Neko-Service folgt dem bestehenden Pattern.
- `deploy/hoerspiel/bootstrap.sh` ist Paula-hart — pro Instanz manuell
  initialisieren, **keine** Bootstrap-Verallgemeinerung jetzt.
- Eltern-Chat-Skill `eltern-chat/skills/hoerspiel_folge_erzeugen.py:54`
  trägt `PAULA_ALTER = 4` als Modul-Konstante (an drei Stellen verwendet).
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
  gebaute Beispiele für Verantwortungs-Stempel-Variante; Eltern-Pille +
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
