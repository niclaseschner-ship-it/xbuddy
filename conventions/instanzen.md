# Instanzen — Konvention (Config-Separation, Weg C)

Ratifiziert 2026-07-31 (`brainstorm/berater-runde/20260731-0100-RATIFIZIERT-config-separation-weg-c.md`, Nic „ja b"; RAT-17-Amendment). Zweck: die pro-Instanz individualisierten Werte (Kinder/Hörspiel-Instanzen: Slug, Port, Origin, Klarname) leben in **einer gelesenen Config**, nicht mehrfach hart im Code. Damit ist der öffentliche Snapshot klarnamen-frei by construction und der bisherige Drift (dieselbe Liste 4× dupliziert) verschwindet.

## INST-1 — Eine Quelle: `instanzen.json` (live, gitignored) + `instanzen.example.json` (getrackt, generisch)

Die Live-Wahrheit steht in `instanzen.json` (neben `familie.json`, **gitignored** — trägt Klarnamen). Der getrackte Default `instanzen.example.json` trägt **generische** Beispiel-Instanzen (`kind1`/`kind2`) und dient als Schema + Fallback. Klarnamen (`display_name`, Mail) stehen in **keiner getrackten Datei** außer den `*.example.json`-Generika.

## INST-2 — Format

Jede Instanz ist ein Objekt mit mindestens:
- `slug` — technischer, stabiler Schlüssel (live `mia`/`finn`/`emil`; im getrackten Example + im Public-Snapshot `kind1`/`kind2`). BUD-1 (ein stabiler Slug) bleibt gewahrt.
- `port` — der bestehende, **handverdrahtete** Port (Wert steht in der Config, wird NICHT berechnet).
- `origin` — der bestehende nginx-Origin (Wert, nicht generiert).
- `display_name` — der menschliche Klarname (nur live/generisch, nie im getrackten Code).

## INST-3 — Config-Guard (load-bearing, RAT-17-Amendment)

Die Config wird **gelesen und angezeigt**, sie **generiert nichts**. Verboten: aus der Config Ports **berechnen** (Port-Offset-Algorithmus), nginx-Origins / systemd-Unit-Namen / URL-Segmente **erzeugen** oder Routing **ableiten**. Diese bleiben **handverdrahtet** (Ports in `ports.md`, Units als Dateien, URL-Slugs in `urls.md`) — RAT-17 hat „erzeugtes Routing" verworfen, und das bleibt. Die Config trägt die *Werte*, nicht die *Erzeugung*. (Prüfbar: kein arithmetischer Port-Ausdruck / kein f-String-gebauter Unit-/Origin-Name aus einem Config-Feld.)

## INST-4 — Konsumenten lesen aus der einen Quelle

Kein pro-Komponente hartkodierter Instanz-Listen-Klon mehr. Die Instanz-Liste kommt aus INST-1 bei: `hoerspiel/config.py` (Default-Instanz), `eltern-chat/tasks.py` (`HOERSPIEL_INSTANZEN`), `eltern-chat/config.py` (Origin-Map), `seiten/main.py` (`_HSP_INSTANZEN`). Das Frontend `controller/app-panel/app.js` (`HSP_KIND_IDS`) bekommt die Liste **server-injiziert** (Muster `window.__HSP_INSTANZEN__`), nicht als eigene hartkodierte Kopie.

## INST-5 — Slugs bleiben, Klarnamen wandern

Der technische Slug im Code/URL/Unit wird **nicht** umbenannt (ein Live-Rename bräche nginx+systemd+Kiosk-Tiles+Cookie-Origin atomar — Antiberater-Befund). Der einzige Leak ist die **Klarnamen-Zuordnung**, und die ist per INST-1 gitignored. Für das öffentliche Repo neutralisiert der Mirror-Bau (#1170, Baustein 2) den bloßen Slug **nur in der Snapshot-Kopie** (`git archive`), nicht im Live-Code.
