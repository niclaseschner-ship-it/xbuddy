# XBuddy nginx — die eine HTTPS-Origin

`xbuddy-origin.conf` ist die nginx-Reverse-Proxy-Konfiguration für die
**eine HTTPS-Origin** einer XBuddy-Instanz (#36).

Hintergrund: `conventions/urls.md` — **URL-11** (HTTPS für alle
Endpunkte), **URL-12** (eine Origin, Routing allein über das Pfad-Prefix)
und **URL-1** (die vier Top-Level-Prefixe).

## Was die Config tut

nginx terminiert TLS auf **Port 8443** mit dem **Tailscale-LE-Zertifikat**
(`tailscale cert`, erneuert durch `xbuddy-cert-renew.timer`, #1458) und
reverse-proxyt jede Anfrage nach Pfad-Prefix an die getrennten
Komponenten-Prozesse. Die Komponenten bleiben eigenständige Prozesse
hinter dem Proxy — same-origin nach außen, getrennt nach innen.

> **self-signed (make-ca.sh) abgelöst (#1458):** Das frühere Dev-CA-Zertifikat
> unter `/etc/xbuddy/tls/` wird nicht mehr verwendet. Stattdessen greift nginx
> auf das von Tailscale ausgestellte Let's-Encrypt-Cert zurück, das ohne CA-
> Install auf den Endgeräten gültig ist.

## Routing-Tabelle

| Pfad-Prefix | Upstream | Port |
|---|---|---|
| `/display/_shared/icons/*` | statisch aus icon-root (`alias`, ICONS-5, #135) | — (Dateisystem) |
| `/display/plan/*` | Plan-Buddy (`plan/main.py`) | `127.0.0.1:5020` |
| `/api/v1/plan/*` | Plan-Buddy (`plan/main.py`) | `127.0.0.1:5020` |
| `/display/_shared/design/*`, `/display/_shared/icons/*` | Seiten-Registry (`seiten/main.py`) | `127.0.0.1:5042` |
| `/controller/app-panel/*`, `/controller/_shared/*` | Seiten-Registry (`seiten/main.py`) | `127.0.0.1:5042` |
| `/api/v1/icons/suche`, `/api/v1/seiten*` | Seiten-Registry (`seiten/main.py`) | `127.0.0.1:5042` |
| alles andere | — | `404` (URL-1) |

> **RAT-31 (#1568):** Der Router-Prozess (`router/main.py`, `127.0.0.1:5000`)
> ist abgerissen. Es gibt keine allgemeinen `/display/`-, `/controller/`-,
> `/api/v1/`-Fallbacks und keinen SSE-Stream `/api/v1/displays/<id>/events`
> mehr — die verbleibenden Sub-Pfade sind alle spezifisch an Buddies bzw. die
> Seiten-Registry geroutet. Die maßgebliche Routing-Tabelle steht in
> `specs/../conventions/urls.md` (URL-14) und im Header von `xbuddy-origin.conf`.

Die spezifischen Buddy-/Seiten-Prefixe stehen vor allgemeineren Prefixen;
nginx wählt bei Prefix-`location` den längsten Treffer, sodass z. B.
`/display/plan/woche` an den Plan-Buddy geht.

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

1. **LE-Zertifikat holen** (Tailscale muss laufen, FQDN bekannt):

   ```bash
   FQDN="buddyboard.taile235cf.ts.net"   # Instanz-FQDN anpassen
   sudo mkdir -p /var/lib/tailscale/certs
   sudo tailscale cert \
       --cert-file /var/lib/tailscale/certs/${FQDN}.crt \
       --key-file  /var/lib/tailscale/certs/${FQDN}.key \
       ${FQDN}
   sudo chmod 640 /var/lib/tailscale/certs/${FQDN}.key
   sudo chown root:www-data /var/lib/tailscale/certs/${FQDN}.key
   ```

   Das Cert ist 90 Tage gültig; der Renewal-Timer (Schritt 2) erneuert es
   automatisch, sobald weniger als 30 Tage Restlaufzeit verbleiben.

2. **Renewal-Timer installieren** (einmalig, läuft dann täglich):

   ```bash
   FQDN="buddyboard.taile235cf.ts.net"   # Instanz-FQDN anpassen

   # Units ins System kopieren und FQDN-Platzhalter ersetzen
   sudo cp deploy/nginx/xbuddy-cert-renew.service /etc/systemd/system/
   sudo cp deploy/nginx/xbuddy-cert-renew.timer   /etc/systemd/system/
   sudo sed -i "s/__XBUDDY_TAILSCALE_FQDN__/${FQDN}/g" \
       /etc/systemd/system/xbuddy-cert-renew.service

   sudo systemctl daemon-reload
   sudo systemctl enable --now xbuddy-cert-renew.timer

   # Sofort-Test (optional):
   sudo systemctl start xbuddy-cert-renew.service
   sudo systemctl status xbuddy-cert-renew.service
   ```

3. **Config installieren** und nginx neu laden — über das Deploy-Skript
   `install.sh` (#164):

   ```bash
   FQDN="buddyboard.taile235cf.ts.net"   # Instanz-FQDN anpassen

   # Live-FQDN merken (aus laufender Conf, falls schon deployed):
   # FQDN=$(grep -oP '[\w.-]+\.ts\.net' /etc/nginx/conf.d/xbuddy-origin.conf | head -1)

   ./deploy/nginx/install.sh

   # Platzhalter ersetzen (sed-Fill-Schritt, STOP-DEPLOY-WARNUNG in conf):
   sudo sed -i "s/__XBUDDY_TAILSCALE_FQDN__/${FQDN}/g" \
       /etc/nginx/conf.d/xbuddy-origin.conf

   sudo nginx -t && sudo systemctl reload nginx
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

4. **Komponenten-Prozesse** laufen lassen — z. B. Seiten-Registry auf
   `127.0.0.1:5042`, Plan-Buddy auf `127.0.0.1:5020` (die Default-Ports; bei
   abweichender Konfiguration die `upstream`-Blöcke der Config anpassen). Der
   frühere Router (`:5000`) ist mit RAT-31 (#1568) entfallen. Alle binden
   nur auf `127.0.0.1` — von außen ist allein die Origin auf `:8443`
   erreichbar.

`nginx -t` braucht Root-Rechte und prüft auch, ob die referenzierten
Zertifikats-Dateien existieren — daher erst nach Schritt 1 ausführbar.

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
