# Tailscale Funnel — Mini-App-Public-Hosting

Tailscale Funnel macht Loopback-Services öffentlich über `<tailnet-name>.ts.net`.
Genutzt für die Mini-App-URL (RAT-16, EZG-6, #684 Baustein 4).

**Funnel ≠ VPN.** Besucher der `*.ts.net`-URL brauchen **keinen** Tailscale-
Account — Funnel exponiert den Loopback-Service ins öffentliche Internet
(Tailscale-Cloud-CDN routet die Anfrage zum Pi-Tunnel und liefert sie an den
lokalen Loopback-Port aus). Tailscale-Voraussetzung gilt **nur** für den Pi
selbst (Hosting-Seite).

## Beta-Risiko

Tailscale Funnel ist **Beta** (Stand 2026-06). Verfügbarkeit nicht garantiert.
Fallback: Cloudflare Tunnel — separates Ticket bei Bedarf (#709 Folge-Punkt).

## Voraussetzungen

- Pi (`rpi-2712` / `buddyboard`) ist Tailscale-Node.
- Tailscale **Funnel-Feature** für den Pi-Node aktiviert (einmaliger
  Browser-Klick im Admin: `https://login.tailscale.com/f/funnel?node=<node-id>`).
- Die `node-id` zeigt der erste fehlschlagende `tailscale funnel`-Aufruf an.

**Kein BotFather-Setup nötig** für `web_app`-Inline-Buttons: die Mini-App-URL
wird vom Bot als `web_app: {url: ...}`-Feld im Inline-Keyboard mitgegeben,
Telegram öffnet sie direkt im Mini-App-Viewer. `/setdomain` ist für das
Telegram-Login-Widget (OAuth), `/newapp` ist optional für offizielle App-
Registrierung — beides nicht zwingend.

## CLI

Telegram akzeptiert nur Standard-HTTPS-Port **443** für `web_app`-Mini-App-URLs.
Auf demselben Pi-Node ist nur **ein** Funnel auf 443 möglich; mehrere Services
hinter einer URL gehen über einen Reverse-Proxy (z. B. nginx).

**Empfohlenes Setup (Pi-bewährt 2026-06-12):** Funnel auf 443 leitet zu nginx
auf 8443 weiter (`https+insecure`, Self-Cert-Pass-Through), nginx routet nach
Pfad-Prefix zu den verschiedenen Buddys (`/seiten/...`, `/api/v1/essen/...`,
`/display/_shared/...`).

```bash
sudo tailscale funnel --bg --https=443 https+insecure://localhost:8443
```

`--bg` persistiert die Funnel-Konfiguration über Reboots.

Direktes Forwarden zu einem einzelnen Buddy (für Test-Aufbauten ohne nginx-
Routing):

```bash
sudo tailscale funnel --bg --https=443 localhost:5042   # seiten-Service direkt
```

Status prüfen:

```bash
sudo tailscale funnel status
```

## Reboot-Test (Akzeptanz für #684)

1. Pi neu starten: `sudo reboot`.
2. Warten bis Pi wieder erreichbar (ggf. `ping rpi-2712` oder Tailscale-Status).
3. **Mobilfunk** (nicht Heim-WLAN — sonst nutzt das Phone den direkten LAN-Pfad)
   → Funnel-URL aufrufen.
4. Mini-App-Endpunkt muss laden ohne erneute Funnel-Aktivierung.

Wenn der Funnel nach Reboot nicht mehr aktiv ist: `--bg`-Flag prüfen.

## Hinweise zu Port-Belegung

Funnel-Port (443 extern) ist der **öffentliche HTTPS-Port** auf
`<tailnet>.ts.net`. Er ist unabhängig vom nginx-Origin-Port `:8443`
im Heimnetz — Tailscale Funnel terminiert TLS in der Cloud und leitet auf
den lokalen Loopback-Port weiter.

Portbelegung im Repo: `conventions/ports.md`.

## Sicherheits-Hinweis

Funnel macht den Service **public im Internet**, ohne Tailscale-Voraussetzung
beim Besucher. Konsumierende Services müssen **eigene Auth** mitbringen —
z. B. Telegram-`initData`-HMAC-Validierung für die Mini App (Folge-Ticket
#708 hebt das von V1-Vereinfachung auf MVP-Pflicht).
