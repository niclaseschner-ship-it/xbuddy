# Tailscale Funnel — Mini-App-Public-Hosting

Tailscale Funnel macht Loopback-Services öffentlich über `<tailnet-name>.ts.net`.
Genutzt für die Mini-App-URL (RAT-16, EZG-6, #684 Baustein 4).

## Beta-Risiko

Tailscale Funnel ist **Beta** (Stand 2026-06). Verfügbarkeit nicht garantiert.
Fallback: Cloudflare Tunnel — separates Ticket bei Bedarf.

## Voraussetzungen

- Tailscale-Account mit Funnel-Feature aktiviert.
- Pi `rpi-2712` als Tailscale-Node angemeldet.
- BotFather-Domain-Setup: `/setdomain <tailnet>.ts.net` als Mini-App-Domain.

## CLI

Seiten-Service (Mini-App-Frontend + API, Port 5042, Funnel-Port 8443):

```bash
sudo tailscale funnel --bg --https=8443 localhost:5042
```

Essens-Buddy (PATCH-Endpoint für Mini-App, Port 5052, Funnel-Port 8444 — optional separater Port,
per Instanz konfigurierbar):

```bash
sudo tailscale funnel --bg --https=8444 localhost:5052
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

Wenn der Funnel nach Reboot nicht mehr aktiv ist: `--bg`-Flag prüfen — es
persistiert die Konfiguration über Reboots. Ohne `--bg` ist der Funnel nur
für die laufende Session aktiv.

## BotFather

```
/setdomain <tailnet>.ts.net
```

Akzeptiert die `*.ts.net`-Domain (Stand 2026-06; falls Telegram irgendwann
`.ts.net` blockt → Cloudflare-Tunnel-Fallback als separates Ticket).

## Hinweise zu Port-Belegung

Die Funnel-Ports (8443, 8444) sind öffentliche HTTPS-Ports auf dem
`<tailnet>.ts.net`-Hostname. Sie sind unabhängig vom nginx-Origin-Port `:8443`
im Heimnetz — Tailscale Funnel terminiert TLS selbst und leitet auf den
lokalen Loopback-Port weiter.

Portbelegung im Repo: `conventions/ports.md`.
