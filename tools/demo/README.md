# Demo-Modus (#1725)

Ein **populiertes System für Screenshots / Onboarding / Demo-Material** — ohne die
gitignored Live-Daten der echten Familie anzufassen und ohne getrackte Dateien zu
verschmutzen.

## Prinzip

- Die getrackten Seeds (`*.example.json`, generische **Familie Sonntag** seit #1719)
  sind der Demo-Datensatz.
- `seed_demo.sh` kopiert sie in ein **gitignored Wegwerf-Dir** `xbuddy-data-demo/`.
- Eine **Demo-Instanz** läuft gegen dieses Dir — auf **alternativen Ports**, damit
  die Live-Services (die echte Familie) unberührt bleiben.

## Schritte

```bash
# 1. Wegwerf-Dir aus den Seeds befüllen (fasst Live nie an):
tools/demo/seed_demo.sh

# 2. Die ENV-Exports für den Demo-Run ausgeben lassen:
tools/demo/seed_demo.sh --env
#    → zeigt export INSTANZEN_CONFIG_FILE=… / PLAN_CONFIG_FILE=… etc.

# 3. Einen (oder mehrere) Buddy-Service gegen das Demo-Dir starten, auf einem
#    ALTERNATIVEN Port (nicht dem Live-Port), z. B. plan:
XBUDDY_DEMO_DIR=$PWD/xbuddy-data-demo \
  PLAN_CONFIG_FILE=$PWD/xbuddy-data-demo/plan/plan.json \
  python3 plan/main.py --port 5150     # Live-plan bleibt auf seinem Port

# 4. Screenshots ziehen: http://127.0.0.1:5150/... zeigt die Familie-Sonntag-Daten.
```

## Sicherheit

- `seed_demo.sh` schreibt **ausschließlich** nach `xbuddy-data-demo/` und startet
  **keine** systemd-Services. `/home/buddy/xbuddy-data/` (die echte Familie) wird
  **nie** berührt.
- Der Demo-Run läuft **separat** (eigene Ports, eigene ENV). Nie die Live-systemd-
  Units gegen die Demo-Daten umbiegen.
- `xbuddy-data-demo/` ist in `.gitignore` — es landet nie im Repo.

## Umfang

`seed_demo.sh` liefert die **Seed-Population** (der sichere, wiederverwendbare
Kern) + die ENV-Vorlage. Ein Ein-Kommando-Launcher, der die **ganze** Flotte auf
einem Alt-Port-Offset hochzieht (inkl. nginx-Routing für die Display-Views), ist
ein optionaler Folge-Ausbau — pro Buddy reicht der obige Einzel-Start für
Screenshots.
