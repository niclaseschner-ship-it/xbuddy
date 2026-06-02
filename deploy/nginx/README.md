# XBuddy nginx — die eine HTTPS-Origin

`xbuddy-origin.conf` ist die nginx-Reverse-Proxy-Konfiguration für die
**eine HTTPS-Origin** einer XBuddy-Instanz (#36).

Hintergrund: `conventions/urls.md` — **URL-11** (HTTPS für alle
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
| `/display/_shared/icons/*` | statisch aus icon-root (`alias`, ICONS-5, #135) | — (Dateisystem) |
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

`/display/_shared/icons/*` ist kein Upstream-Proxy, sondern wird per
nginx-`alias` direkt aus der **icon-root** ausgeliefert (zentrale
ARASAAC-Icon-Bibliothek, `specs/platform/icons.md` ICONS-5, #135). Die
icon-root ist Per-Instanz-Daten außerhalb des Repos (Default
`/home/buddy/apps/icons/`, ICONS-2) und wird vor dem Serving einmalig
befüllt — siehe „Icon-Bibliothek seeden" unten. Weicht der icon-root-Pfad
ab, den `alias` in `xbuddy-origin.conf` entsprechend anpassen.

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

3. **Config installieren** und nginx neu laden — über das Deploy-Skript
   `install.sh` (#164):

   ```bash
   ./deploy/nginx/install.sh
   ```

   Das Skript ist explizit, idempotent und reload-sicher:

   - Quelle: `deploy/nginx/xbuddy-origin.conf` (Repo).
   - Ziel: `/etc/nginx/conf.d/xbuddy-origin.conf` (überschreibbar per
     `XBUDDY_NGINX_DEST=…` für Tests).
   - Sind Quelle und Ziel identisch, beendet sich das Skript mit Exit 0
     („nichts zu tun") — Reruns sind ungefährlich.
   - Bei jedem echten Wechsel wird vor dem `cp` ein Backup
     `xbuddy-origin.conf.bak` neben dem Ziel angelegt.
   - Anschließend prüft das Skript per `sudo nginx -t`. **Schlägt die
     Validierung fehl, wird das Backup automatisch zurückgespielt** und
     nginx bleibt unverändert; bei Erst-Installation entfällt das Backup
     und die kaputte Ziel-Datei wird entfernt.
   - Bei erfolgreicher Validierung folgt `sudo systemctl reload nginx`.

   Das Skript braucht `sudo` (für `cp`, `nginx -t`, `systemctl reload`).

4. **Komponenten-Prozesse** laufen lassen — Router auf `127.0.0.1:5000`,
   Plan-Buddy auf `127.0.0.1:5020` (die Default-Ports; bei abweichender
   Konfiguration die `upstream`-Blöcke der Config anpassen). Beide binden
   nur auf `127.0.0.1` — von außen ist allein die Origin auf `:8443`
   erreichbar.

5. **Root-CA auf den Geräten** der Familie installieren, damit Browser
   dem Server-Cert vertrauen (siehe `tools/ca/README.md`).

`nginx -t` braucht Root-Rechte und prüft auch, ob die referenzierten
Zertifikats-Dateien existieren — daher erst nach Schritt 2 ausführbar.

## Icon-Bibliothek seeden (Ops — durch Nic)

Bevor `/display/_shared/icons/*` Bilder liefert, muss die icon-root
einmalig befüllt werden (`specs/platform/icons.md` ICONS-4). Das Seed-Skript
kopiert die ARASAAC-PNGs und das Wort→ID-Mapping aus dem vorhandenen
KIBuddy-Cache in die icon-root (idempotent, kein Re-Fetch):

```bash
./deploy/icons/seed-icon-library.sh            # Default-icon-root /home/buddy/apps/icons/
./deploy/icons/seed-icon-library.sh /pfad/zur/icon-root   # abweichender Ort
```

Der `alias` in `xbuddy-origin.conf` muss auf denselben icon-root zeigen.
Die ~176 MB Assets liegen außerhalb des Repos (Per-Instanz-Daten, ICONS-2).
