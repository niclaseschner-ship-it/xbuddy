# RAT-29 — Heim-Shell als Ziel-Default: Zwei-Geräte-Modell wird durch Shell auf einem Gerät ersetzt

**Datum:** 2026-07-24 · **Ratifiziert:** Nic-Setzung 2026-07-24 · **Refs:** #1182, #1409 · **Supersedes:** RAT-25 (Pilot-Scope) · **Extends:** RAT-27

## Kontext — warum der Pilot nicht mehr Pilot bleibt

RAT-25 (2026-06-30) ratifizierte die Heim-Shell bewusst als **LAN-only-Pilot** (n=1, Mia-Tablet) — eingehegt, reversibel, keine Konvention. Leitbild damals: Pilot zuerst, strategischer Rollout erst nach Auth-Härtung.

RAT-27 (2026-07-07) hob den LAN-only-Riegel via Auth-Funnel (AUTH-7b) auf: die Shell ist jetzt extern erreichbar für Geräte mit `xbuddy_session`-Cookie.

**Nic-Setzung 2026-07-24** (#1409-Kommentar): Die Heim-Shell ist die neue PWA, die Panel und Display in einer URL vereint. Sie wird zum **neuen Default** — ein Gerät reicht, zwei sind nicht mehr nötig. Was „nach und nach abgebaut" wird, ist das **Zwei-Geräte-Modell**, nicht die Apps.

## Entscheidung

### 1. Heim-Shell = strategischer Ziel-Zustand (Pilot → Default)

`/shell/<panel_id>` ist der primäre Einstiegspunkt für Familien-Geräte. Ein Gerät, das Panel und Buddy braucht, wird langfristig über die Shell bedient. Die Split-Layout-Architektur (SHELL-1..SHELL-11, RAT-25) bleibt vollständig unverändert — RAT-29 ändert den Scope, nicht den technischen Kern.

### 2. Zwei-Geräte-Modell entfällt als Normalfall

Das bisherige Modell: **Gerät 1** zeigt das Panel (Controller), **Gerät 2** zeigt den Display-Client (Buddy-View). Die Shell ersetzt das: **ein Gerät** zeigt beides — Panel-Nav links, Buddy-View rechts.

**Alle Apps bleiben vollständig erhalten.** essen-einkauf, plan, hoerspiel-player, connector, routine und alle weiteren Views existieren unverändert als Buddy-Views im rechten Pane der Shell. Keine App, keine Route, keine Funktionalität entfällt. Was entfällt ist der **separate Display-Klient auf einem zweiten Gerät** als Normalfall für Familien-Geräte — nicht die Apps selbst.

### 3. Shell wird REGISTRY-First-Class-Eintrag

`REGISTRY["shell"]` in `pwa_mantel.py` ist kein Spezialfall (PWAM-5 Frage 3, #1409), sondern der **Primary-Eintrag**. Dynamisches Manifest per `panel_id` ist Shell-Spezifik — sie rechtfertigt einen eigenen Code-Zweig in `build_manifest()`, aber keinen Kommentar „Ausnahme-Handler". Shell ist der primäre Installationspunkt und muss als First-Class in der REGISTRY stehen.

Konkret: `REGISTRY["shell"]` trägt alle Standard-Felder (`name`, `sw_scope`, etc.); `build_manifest()` bekommt einen `panel_id`-Ast für die dynamische `start_url`. Die „PWAM-5-Ausnahme-Marker"-Lösung (Option B der Wahl-Karte) entfällt mit dieser Setzung.

### 4. Reihenfolge

1. **Auth scharf** — #1389 (Auth-Enforcement) + #1390 (Onboarding-Rollout), beide `status:ready`, nächster Arbeitstag. Ohne AUTH-7b funktioniert der Funnel-Zugang zur Shell nicht.
2. **Shell-Rollout** — nach #1389/#1390 auf alle Familien-Geräte (AUTH-7b aktiv); Shell-URL in MAU-Mini-App als Primär-Link (SHELL-10).
3. **Zwei-Geräte-Ablösung** — sobald Shell auf einem Gerät stabil läuft, entfällt der zweite Display-Klient als Pflicht; kein Stichtag, kein Ticket erzwingen.

### 5. Konvention (n=2-Trigger bleibt)

`conventions/heim-shell.md` entsteht erst beim zweiten Shell-Gerät oder der zweiten Familie. Bis dahin bleibt die Spec in `specs/platform/heim-shell.md` mit diesem Nordstern.

## Nicht-Implikationen

- **Alle Apps bleiben** — essen-einkauf, plan, hoerspiel-player, connector, routine etc. sind vollständig erhalten als Buddy-Views. Keine Route, keine Funktionalität, kein Ticket für „App X abbauen".
- **Architektur unverändert** — Split-Layout, zwei Iframes, kein neuer Routing-Kern, keine Stream-Fusion (SHELL-4). RAT-25 bleibt maßgeblich für den technischen Kern.
- **Auth-Modell unverändert** — RAT-27 gilt weiter: EIN Cookie über alle Familien-PWAs; Dual-Gate (Cookie ODER Operator-IP). Shell ist AUTH-7b-Konsument.
- **GER-`beides`-Schuld bleibt offen** — Co-Location-Modell (2. Shell-Gerät) ist Folge-Aufgabe (Trigger: 2. Gerät).

## Kill-Kriterium

Familien-Geräte zeigen konsistent schlechtere UX mit der Shell als mit dem klassischen Display-Client (Lag > 200ms, Audio-Glitch, Split-Layout-Verlust) → Shell bleibt additiv, kein Pflichtweg; klassisches Zwei-Geräte-Modell bleibt parallel nutzbar.

## Belege

Nic-Setzung 2026-07-24 (#1409-Kommentar, arbeitstag-prep Lauf, Klarstellung „die einzelnen apps bleiben natürlich alle erhalten"). RAT-25 (Pilot-Architektur). RAT-27 (Auth-Funnel-Rollout, AUTH-7b). specs/platform/heim-shell.md (SHELL-1..SHELL-11). pwa_mantel.py REGISTRY (7 Einträge). conventions/pwa-mantel.md (PWAM-5 Frage 3).

Refs #1182 #1409 #1338 #1339
