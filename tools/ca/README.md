# XBuddy CA-Werkzeug

`make-ca.sh` erzeugt die lokale **Root-CA** einer XBuddy-Instanz und ein
davon signiertes **Server-Zertifikat** für die eine HTTPS-Origin (#36).

Hintergrund: `conventions/urls.md` — **URL-11** (HTTPS für alle
Endpunkte) und **URL-12** (eine Origin). Jede Instanz trägt genau ein
Server-Zertifikat; die Geräte der Familie vertrauen einmalig der Root-CA.

## Was das Skript erzeugt

| Datei | Zweck | Geheim? |
|---|---|---|
| `rootCA.pem` | Root-CA-Zertifikat — Trust-Anker, auf die Geräte verteilen | nein |
| `rootCA-key.pem` | Root-CA-Schlüssel — signiert Server-Certs | **ja** |
| `server-cert.pem` | Server-Zertifikat — für nginx `ssl_certificate` | nein |
| `server-key.pem` | Server-Schlüssel — für nginx `ssl_certificate_key` | **ja** |

Laufzeiten (Defaults): Root-CA **3650 Tage** (~10 Jahre), Server-Cert
**825 Tage** (von Browsern akzeptierte Obergrenze). Beides per Flag
überschreibbar.

## Geheimnisse — niemals ins Repo

Die `*-key.pem` sind Per-Instanz-Geheimnisse (CLAUDE.md §8). Nur dieses
Skript ist versioniert. Der Default-Ausgabe-Ordner `tools/ca/out/` ist per
`.gitignore` ausgeschlossen — beim Ablegen in einen anderen Ordner darauf
achten, dass auch dieser nicht versioniert wird.

## Ausführen

```bash
# Default-SAN (localhost + xbuddy-hub.local + 127.0.0.1):
tools/ca/make-ca.sh

# Pi mit fester LAN-IP — die SAN-Liste muss alle Adressen tragen, unter
# denen die Origin erreichbar ist:
tools/ca/make-ca.sh --san "DNS:xbuddy-hub.local,IP:192.168.0.78"
```

Alle Optionen: `tools/ca/make-ca.sh --help`.

Das Skript ist **idempotent** für die Root-CA: ein erneuter Lauf verwendet
eine vorhandene `rootCA*.pem` wieder (ausgerollte Geräte-Trust-Anker bleiben
gültig) und stellt nur das Server-Cert neu aus. Eine neue CA bekommt man,
indem man `rootCA*.pem` löscht oder einen leeren `--out`-Ordner nutzt.

## SAN — Subject Alternative Names

Browser prüfen den Host gegen die SAN-Liste, nicht gegen den CN. Die Liste
muss **jede** Adresse enthalten, unter der die Origin erreichbar ist —
DNS-Name(n) und/oder IP. Format: komma-getrennt aus `DNS:<name>` und
`IP:<addr>`, z. B. `--san "DNS:xbuddy-hub.local,IP:192.168.0.78"`.

## Auf den Geräten vertrauen

`rootCA.pem` muss auf jedem Gerät der Familie als vertrauenswürdige CA
installiert werden, damit Browser dem Server-Cert vertrauen (Secure
Context für Kamera, Service-Worker, PWA — URL-11). Das ist ein
Ops-/Onboarding-Schritt und kein Teil dieses Skripts.

## Test

```bash
python3 -m pytest tools/ca/tests/ -v
```

Der Test ruft das Skript in einem Tempdir auf und belegt mit
`openssl verify`, dass die Kette stimmt — er schreibt nie ins Repo.
