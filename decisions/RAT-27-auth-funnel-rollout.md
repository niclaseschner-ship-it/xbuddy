# RAT-27 — Auth-Funnel-Rollout: AUTH-7 gegabelt (7a/7b), AUTH-3.a Observe-READ, Funnel-Origin, RAT-25 supersede

**Datum:** 2026-07-07 · **Ratifiziert:** Nic (RAT-27) · **Epic:** #1338 · **Ticket:** #1388 · **Spec-PR:** #1391

## Entscheid
Familien-**User**-Geräte (Handy/Tablet) erreichen die volle Familien-UI **cert-frei über den Funnel per Cookie**. LAN-only (RAT-25) wird **abgelöst** (heim-LAN bleibt Fallback, kein Funnel-Zwang). Vorbedingung erfüllt: **Gate-0 grün** (Funnel trägt HTTP/2 + SSE + Audio, 2026-07-07 extern gemessen).

- **AUTH-7 gegabelt:** 7a Operator-Pi (IP-Allowlist, **Auslaufmodell**) · **7b User-Shell (Cookie)** über Funnel. **Dual-Gate: Cookie ODER Operator-IP** (sonst 401t das cookie-lose Pi-Kiosk). 7b umfasst `/shell`, `/display/<id>`, `/controller/*`, `/api/v1/displays/<id>/events`. 7b-Public-Ausnahmen: AUTH-8-Re-Pair-Seite + `/display/_shared/*`.
- **AUTH-3.a — Observe→Hard-Leiter:** Observe/Log-only-Grace **nur READ**; WRITE + die #1321-Flächen (photo/kibuddy/plan) **hart ab Tag 0** (nicht regressieren — #1321 CLOSED/live). Flip-Kriterium (Nic): **sauberes Observe-Log + `paired_at`** (kein festes Zeit-Minimum).
- **Origin:** SREG-7 dritter Schlüssel `display_url_origin_funnel`; Pairing-Redirect same-origin/relativ.

## Nic-Bedingungen (bindend)
1. **Einheitlicher Eltern-Auth-Pfad:** das Cookie-über-Funnel-Modell deckt **alle aktuellen UND zukünftigen** Eltern-PWA-Mini-Apps (essen-einkauf u. a., AUTH-3) **und** die Shell (7b) ab — EIN Modell, kein Sonder-Auth pro App.
2. **Pi ist Auslaufmodell** (1 Familien-Kiosk-Sonderfall) → Priorität ist der User-Cookie-Pfad (Handy/Tablet); die cookie-losen Pi-Buddy-Views bleiben vorerst Operator-erreichbar, nachträglich zu lösen.
3. Observe-Flip = sauberes Log + `paired_at`.

## Bezug / löst ab
Supersede-Teil von **RAT-25** (Heim-Shell LAN-only → Funnel-Cookie erlaubt). Baut auf RAT-18 (Cookie-Standard), #948/#1292/#1321 (Mini-App-Cookie-Auth gemergt). Bau: #1389 (Enforcement) + #1390 (Rollout). AUTH-9-Coverage-Test um 7b-Routen erweitern.
