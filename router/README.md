# Router

V1-Implementierung der Spec [`specs/platform/router.md`](../specs/platform/router.md). Refs #5.

## Start

```bash
# Minimal (lokal, HTTP, mit routing.json im Arbeitsverzeichnis)
python3 router/main.py

# Mit Pfaden, Bind auf 0.0.0.0, HTTPS (Pi-Dev-Setup)
python3 router/main.py \
  --routing /tmp/xbuddy-serve/router/routing.json \
  --config  /tmp/xbuddy-serve/router/config.json \
  --host 0.0.0.0 --port 5000 \
  --cert /tmp/xbuddy-serve/cert.pem \
  --key  /tmp/xbuddy-serve/key.pem
```

`config.json` ist die Wahrheit (CONFIG-1), ENV ist Dev-Override (`ROUTER_LISTEN_HOST`, `ROUTER_LISTEN_PORT`, `ROUTER_LOG_LEVEL`), CLI ist Test-Werkzeug, Defaults sind Fallback (ROU-15).

## Endpunkte

| Endpunkt | Zweck | Spec |
|---|---|---|
| `POST /api/v1/events` | Controller-Events entgegennehmen | ROU-3 |
| `GET /api/v1/displays/<id>/state` | aktuellen State holen | ROU-12 |
| `GET /api/v1/displays/<id>/events` | SSE-Zustands-Stream für ein Display | ROU-22 |
| `GET /api/v1/diag` | Debug-HTML, alle Displays | ROU-14 |
| `GET /display/<id>` | Display-Client ausliefern (E-DC-3) | ROU-20 |

## Dateien

- `main.py` — Service, Adapter, Routing-Kern. Eine Datei für V1, später bei Bedarf aufsplitten.
- `routing.example.json` — Format der M:N-Tabelle. `routing.json` selbst ist per Repo-`.gitignore` ausgeschlossen — pro Deployment separat.
- `config.example.json` — Format der Tuning-Datei.

## Reload-on-Read

`routing.json` wird pro Lookup frisch von Disk gelesen (Reload-on-Read, [DCOMP-2](../conventions/data-components.md)). Schreibt ein Skill die Datei, sieht der nächste Event-Lookup den neuen Stand ohne Service-Restart und ohne Admin-Reload-Aufruf. Der Admin-Reload-Endpoint (`POST /api/v1/router/admin/reload`, #140) bleibt als expliziter Reload-Marker erhalten, ist für die Sichtbarkeit aber nicht mehr nötig.

## Tests

```bash
python3 -m pytest router/tests/ -v
```
