# RAT-25 — Heim-Shell: RAT-19-Phase-4-Pilot vorgezogen, LAN-only eingehegt, AUTH-7 NICHT ausgelöst

**Ratifiziert:** 2026-06-30 (Nic) · **Ticket:** #1182 · **Werft-Lauf**

## Beschluss
Ein Familien-Gerät trägt Panel UND Buddy-View als **dünne PWA-Shell**
(Panel-Kachel-Nav links, geroutete Buddy-View rechts), gebaut als
**Split-Layout-Container um zwei bestehende Iframes** — **kein neuer
Routing-Kern**. Tile-Tap läuft unverändert `tile_selected` → Router → SSE →
Render. Verortung `seiten/static/` + `platform.js`. Pilot: **Mia-Tablet**
(`tablet-tablet-mia-01`, 1920×1200), **LAN-only**.

Konkrete Form (Antiberater-Patches eingebacken):
- **Einstieg über `panel_id`** (`/shell/<panel_id>`), `display_id` per
  Router-Lookup (ROU-32). Keine Reverse-Inferenz „ein Display → ein Panel".
- **Zwei unabhängige `EventSource`** akzeptiert, **keine** Stream-Fusion
  (ROU-22 zustandslos).
- **Rechtes Pane = iframe**, keine Display-Client-Codekopie.
- **Rail 280px** (Gate B 2026-06-30): das Panel reflowt seine Kacheln **selbst**
  einspaltig (PANEL-12 `computeGridGeometry`) — **Panel bleibt unverändert**.
- **n=1 (nur Mia), keine antizipative Shell-Konvention.** IDs aus Daten.

## Warum
- **Gewinn:** ein Gerät statt zwei; bestehende Routing-/Render-Mechanik komplett
  wiederverwendet (ROU-1/PANEL-1/DC-9 intakt). **Zwei-Wege-Tür** im Kern
  (Rückbau = Shell-Route weg).
- **Eine Ein-Wege-Kante = Auth.** `auth.md` (AUTH-6/AUTH-7, :245/:338) bindet
  die Panel-/Display-Routen an **Phase 4**. Dieser Pilot ist **kein**
  Phase-4-Rollout, sondern ein vorgezogener, **LAN-only eingehegter** Pilot:
  solange kein Funnel, wird der Phase-4-Trigger **nicht** ausgelöst (AUTH-7
  bleibt vorbereitet, nicht scharf). Pre-Merge-Experiment belegt: Shell-URL +
  Display-Event-Stream sind nicht über den Funnel erreichbar.
- **2. Gerät / produktive Nutzung ⇒ erst AUTH-7 scharfziehen** (#948 bleibt
  Plan B / Auth-Schmerz-Trigger). Dieser Record hält die Phasen-Reihenfolge
  sichtbar, damit niemand den Pilot als Phase-4-Rollout liest.

## Offene Schuld (sichtbar, nicht jetzt)
- **GER-`beides`-Co-Location** (`geraete.md:60` / `seiten-registry.md:39`) —
  Trigger: 2. Shell-Gerät.
- **RAT-24-Teil-Pane-Render-Vertrag** offen (Render-Gate deckt heute nur
  Voll-Viewport-Views).

## Betrifft
`specs/platform/heim-shell.md` (SHELL, neu) · `specs/mockups/heim-shell/`
(Gate-B-Beleg) · Bezug RAT-18 / RAT-19 / AUTH-6 / AUTH-7 / #948 · #1182 (Keystone)

## Transkript
- Vorschlag: `brainstorm/berater-runde/20260630-150651-vorschlag-pwa-shell-mia.md`
- Antiberater (Codex): `brainstorm/berater-runde/2026-06-30-1507-antiberater-pwa-shell-mia.md`
- Ratifikation: `brainstorm/berater-runde/20260630-151000-RATIFIZIERT-pwa-shell-mia.md`
