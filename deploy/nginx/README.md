# XBuddy nginx — die eine HTTPS-Origin

`xbuddy-origin.conf` ist die nginx-Reverse-Proxy-Konfiguration für die
**eine HTTPS-Origin** einer XBuddy-Instanz (#36).

Hintergrund: `specs/platform/urls.md` — **URL-11** (HTTPS für alle
Endpunkte), **URL-12** (eine Origin, Routing allein über das Pfad-Prefix)
und **URL-1** (die vier Top-Level-Prefixe).

## Was die Config tut

nginx terminiert TLS auf **Port 8443** mit dem CA-signierten
Server-Zertifikat (`tools/ca/make-ca.sh`) und reverse-proxyt jede Anfrage
nach Pfad-Prefix an die getrennten Komponenten-Prozesse. Die Komponenten
bleiben eigenständige Prozesse hinter dem Proxy — same-origin nach außen,
getrennt nach innen.

## Routing-Tabelle

| Pfad-Prefix | Upstream | Port |
|---|---|---|
| `/display/plan/*` | Plan-Buddy (`plan/main.py`) | `127.0.0.1:5020` |
| `/api/v1/plan/*` | Plan-Buddy (`plan/main.py`) | `127.0.0.1:5020` |
| `/display/*` | Router (`router/main.py`) | `127.0.0.1:5000` |
| `/controller/*` | Router (`router/main.py`) | `127.0.0.1:5000` |
| `/api/v1/*` | Router (`router/main.py`) | `127.0.0.1:5000` |
| `/health` | Router (`router/main.py`) | `127.0.0.1:5000` |
| `/version` | Router (`router/main.py`) | `127.0.0.1:5000` |
| alles andere | — | `404` (URL-1: nur die vier Prefixe) |

Die spezifischen Plan-Prefixe stehen vor den allgemeinen Router-Prefixen;
nginx wählt bei Prefix-`location` den längsten Treffer, sodass z. B.
`/display/plan/woche` an den Plan-Buddy und `/display/wohnzimmer` an den
Router geht.

Die Buddy-Vhosts auf den `:51NN`-Ports und `:5150` sind **Brücken** und
bewusst **nicht** Teil dieser Origin.

## Ausrollen auf der Pi (Ops — durch Nic)

Die folgenden Schritte führt der Instanz-Betreiber aus; sie sind kein Teil
des Repos.

1. **Server-Zertifikat erzeugen** (falls noch nicht geschehen):

   ```bash
   tools/ca/make-ca.sh --san "DNS:xbuddy-hub.local,IP:<pi-lan-ip>"
   ```

2. **Zertifikat + Schlüssel ablegen**, am Ort, auf den die Config zeigt:

   ```bash
   sudo mkdir -p /etc/xbuddy/tls
   sudo cp tools/ca/out/server-cert.pem /etc/xbuddy/tls/
   sudo cp tools/ca/out/server-key.pem  /etc/xbuddy/tls/
   sudo chmod 600 /etc/xbuddy/tls/server-key.pem
   ```

   Weichen die Ablage-Pfade ab, die beiden `ssl_certificate*`-Zeilen in
   `xbuddy-origin.conf` entsprechend anpassen.

3. **Config installieren** und nginx neu laden:

   ```bash
   sudo cp deploy/nginx/xbuddy-origin.conf /etc/nginx/conf.d/
   sudo nginx -t            # Syntax + Zertifikats-Pfade prüfen
   sudo systemctl reload nginx
   ```

4. **Komponenten-Prozesse** laufen lassen — Router auf `127.0.0.1:5000`,
   Plan-Buddy auf `127.0.0.1:5020` (die Default-Ports; bei abweichender
   Konfiguration die `upstream`-Blöcke der Config anpassen). Beide binden
   nur auf `127.0.0.1` — von außen ist allein die Origin auf `:8443`
   erreichbar.

5. **Root-CA auf den Geräten** der Familie installieren, damit Browser
   dem Server-Cert vertrauen (siehe `tools/ca/README.md`).

`nginx -t` braucht Root-Rechte und prüft auch, ob die referenzierten
Zertifikats-Dateien existieren — daher erst nach Schritt 2 ausführbar.
