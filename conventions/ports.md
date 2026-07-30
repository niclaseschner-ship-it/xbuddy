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
| 5000 | Router (ENTFALLEN, RAT-31 E6f #1568 — Service-Teardown im Deploy) | xbuddy-router |
| 5010 | Familien-Registry | xbuddy-familie |
| 5020 | Plan-Buddy | xbuddy-plan |
| 5030 | Wetter-Buddy | xbuddy-wetter |
| 5040 | Geräte-Registry (ENTFALLEN, RAT-31 E6 — Service-Teardown) | xbuddy-geraete |
| 5041 | Panel-Registry | xbuddy-panel |
| 5042 | Seiten-Registry | xbuddy-seiten |
| 5050 | Routine-Buddy | xbuddy-routine |
| 5051 | Photo-Buddy | xbuddy-photo |
| 5052 | Essens-Buddy | xbuddy-essen |
| 5053 | Hörspiel-Buddy | xbuddy-hoerspiel |
| 5054 | KI-Buddy | xbuddy-kibuddy |
| 5055 | Hörspiel-Buddy (Neko) | xbuddy-hoerspiel-neko |
| 5056 | Hörspiel-Buddy (niclas) | xbuddy-hoerspiel-niclas |
| 5057-5099 | für neue Buddys reserviert | — |

### PORT-3 — Komponenten binden nur an 127.0.0.1, nie an 0.0.0.0
Komponenten binden ihren HTTP-Server an `127.0.0.1`, nicht an `0.0.0.0`.
Öffentlich gemacht werden sie ausschließlich durch den Reverse-Proxy
(nginx-Origin). Wer extern erreichbar sein muss, sagt das im Routing,
nicht durch direktes Lauschen.
