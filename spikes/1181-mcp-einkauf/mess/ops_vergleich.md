# Ops-Schritte: HTTP-Dauerdienst vs. stdio (AC-3)

Konkrete Betriebsschritte für die zwei MCP-Transporte, gemessen/gebaut im Spike.

## stdio (pro-Aufruf gespawnter Prozess)

1. eltern-chat (MCP-Client) startet pro Turn (oder pro Sitzung) einen
   `python run_stdio.py`-Kindprozess.
2. MCP-Handshake über die stdin/stdout-Pipes: `initialize` → `list_tools`.
3. Tool-Call(s) über dieselbe Pipe.
4. Prozess-Teardown nach dem Turn (bzw. Sitzungsende).

**Gemessen:** Spawn → erster nutzbarer Tool-Call = **Median 559 ms**
(min 549, max 600; N=7). Diese ~0,56 s landen als Latenz VOR jeder
Buddy-Antwort, wenn pro Turn gespawnt wird.

**Ops-Eigenschaften:**
- Kein Dauerdienst, kein Port, kein systemd-Unit, kein Healthcheck nötig.
- Keine Boot-Race-Klasse (vgl. nginx-443-Race) — der Prozess existiert nur
  während des Turns.
- Lebenszyklus = Kind des eltern-chat-Prozesses; stirbt automatisch mit.
- Kosten: Spawn-Latenz JEDES MALS + Peak-RSS-Spitze (~57 MB) während des Turns.

## HTTP/SSE (streamable-http) — Dauerdienst

1. systemd-Unit (analog essen.service) startet `python run_http.py` auf
   127.0.0.1:5191 dauerhaft.
2. ENV/Drop-In je Instanz (Port, ESSEN_ORIGIN_URL) — analog der
   ZD-Store-Drop-In-Pflicht pro Service (feedback_zd_store_dropin_pro_service).
3. eltern-chat hält MCP-HTTP-Sessions, Tool-Calls pro Turn ohne Spawn.
4. Nach Merge/Code-Änderung: `systemctl restart` Pflicht
   (feedback_service_restart_nach_merge) — MCP-Server lädt Code nicht hot.
5. Boot-Reihenfolge / Port-Binding härten (vgl.
   feedback_nginx_443_race_mit_tailscale_funnel) — neuer Listener im
   Boot-Rennen.

**Gemessen:** idle-RSS Median **55,7 MB**, permanent resident (auch ohne Last).

**Ops-Eigenschaften:**
- Kein Spawn pro Turn → niedrige Per-Call-Latenz.
- Aber: permanenter RAM-Block + ein weiterer Dauerdienst pro Buddy, der
  überwacht, neugestartet, geboot-geordnet und Drop-In-konfiguriert werden muss.
- Ein zusätzlicher Port pro Buddy in conventions/ports.md (PORT-2-Pflege).

## Fazit Ops

| Achse | stdio (pro Turn) | HTTP-Dauerdienst |
|---|---|---|
| Per-Call-Latenz | +559 ms Spawn | ~0 (Session offen) |
| RAM | transient ~57 MB-Spitze | permanent ~56 MB/Buddy |
| systemd/Port/Healthcheck/Restart | nein | ja, pro Buddy |
| Boot-Race-Risiko | nein | ja |
| Drop-In/Port-Pflege | nein | ja, pro Buddy |

Beide Formen sind echter Mehraufwand gegenüber dem Direkt-Adapter (0 Prozesse,
0 Ports, 0 Spawn). stdio verschiebt die Kosten in die Latenz, HTTP in den
permanenten RAM + Ops-Fläche.
