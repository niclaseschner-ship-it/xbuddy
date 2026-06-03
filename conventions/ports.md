# Loopback-Ports — Konvention     (ID-Präfix: PORT)

XBuddy-Komponenten kommunizieren intern über lokale HTTP-Ports auf dem
Hub. Eine zentrale Vergabe schützt vor Kollisionen, macht das System
diagnostizierbar und ist Single Source für die Reverse-Proxy-Konfiguration.

### PORT-1 — Loopback-Block ist 5000-5099, je Komponente eine feste Nummer
XBuddy-Komponenten belegen Ports im Block **5000-5099**. Jede Komponente
hat eine **feste** Nummer; die Vergabe steht im Katalog (PORT-2) — nicht
in einer Service-Datei oder im Code als wahre Quelle.

### PORT-2 — Port-Katalog steht in dieser Konvention
| Port | Komponente | Service-Name (SVC-1) |
|---|---|---|
| 5000 | Router | xbuddy-router |
| 5010 | Familien-Registry | xbuddy-familie |
| 5020 | Plan-Buddy | xbuddy-plan |
| 5030 | Wetter-Buddy | xbuddy-wetter |
| 5040 | Geräte-Registry | xbuddy-geraete |
| 5050-5099 | für neue Buddys reserviert | — |

### PORT-3 — Komponenten binden nur an 127.0.0.1, nie an 0.0.0.0
Komponenten binden ihren HTTP-Server an `127.0.0.1`, nicht an `0.0.0.0`.
Öffentlich gemacht werden sie ausschließlich durch den Reverse-Proxy
(nginx-Origin). Wer extern erreichbar sein muss, sagt das im Routing,
nicht durch direktes Lauschen.
