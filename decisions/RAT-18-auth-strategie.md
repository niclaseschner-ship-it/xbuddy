# RAT-18 — Auth-Strategie: Cookie als Standard, MAD-7 im Auslaufen, phasenweise Migration

- **Entschieden:** 2026-06-16 (Berater-Runde „Auth-Strategie für 5 Endgeräte-
  Klassen", Berater + Codex-Antiberater, zwei Runden + Variante-B-Entscheid),
  **ratifiziert** 2026-06-16 (Nic-Verdikt E1–E4 plus übergeordneter Setzung
  „PWA-First für Power-Flows").
- **Betrifft:** `specs/platform/auth.md` (neu, AUTH-1..AUTH-9),
  `conventions/mini-app-design.md` MAD-7 („im Auslaufen"-Markierung),
  `specs/platform/geraet-anlegen.md` GAA-3.8 (Pairing-Schritt),
  `specs/platform/geraete.md` GER-3 (`paired_at`-Feld),
  `decisions/INDEX.md` (RAT-18-Eintrag). Keystone-Ticket **#948**;
  Folge-Ticket **#949** (PWA-Phase-1, `blocked` durch #948).
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/2026-06-16-1123-RATIFIZIERT-auth-strategie-5-klassen.md`
  → Vorschlag-R1 `20260616-111026-vorschlag-auth-strategie-5-klassen.md`,
  Antiberater-Codex `2026-06-16-1111-antiberater-auth-strategie-5-klassen.md`,
  Vorschlag-R2 inline im ENTSCHEID-File.
  Gekoppelte Runde: Power-Flow-Distribution
  `2026-06-16-1245-RATIFIZIERT-power-flow-distribution.md` (RAT-19, folgt
  nach Phase-1-Bewährung).

## Beschluss

xbuddy nutzt **Cookie-Auth (`xbuddy_session`, HMAC mit Bot-Token als
Sign-Key) als Standard-Auth-Mechanismus** für Mini-App-Datenrouten.
**MAD-7** (`Authorization: tma <initData>`) bleibt **additiv akzeptiert**
(Mini-Apps brechen nicht), wird aber als „**im Auslaufen**" markiert und
schrittweise mit jeder Power-Flow-Migration zurückgebaut. Phase 6 (vollständige
Ablösung) tritt ein, wenn AUTH-6-Backlog leer ist.

**Die Sorten-Grenze** ist Routen-Präfix, nicht User-Rolle: Pfad-1 Mini-App-
Daten (AUTH-3), Pfad-2 Public-Assets (AUTH-4), Pfad-3 Loopback Server-zu-Server
(AUTH-5), Pfad-4 Backlog dokumentiert offen (AUTH-6). Display-Renderer-Klasse
(AUTH-7) ist als Phase-4-Vorbereitung skizziert, nicht V1-bindend.

**Mini-Apps bleiben PUBLIC bis migriert.** Heutiger Zustand seit #708-Rollback
(2026-06-15, Commit `dd8f5a2`): alle Mini-App-APIs sind offen, `@require_init_data`
ist im Bestand definiert, aber an null Routen angehängt (kosmetisch). Die
Migration löst diesen Zustand flow-für-flow auf.

**Fünf konkrete Entscheidungen (ratifiziert):**

1. **Endpoint-Liste statt Prefix-Regel (AUTH-3).** Phase 1 enthält nur
   essen-einkauf-API-Routen (`/api/v1/essen/wuensche*`, `/katalog*`, `/fotos*`).
   Weitere Power-Flows werden phasenweise ergänzt. Eine neue Mini-App-Route
   ist Spec-Änderung, kein Config-Wert. Begründung: `/api/v1/<buddy>/*`
   mischt Datenrouten, Assets und Server-zu-Server — pauschale
   Prefix-Härtung würde Bot-Skills brechen.
   [Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
   → E1 „Endpoint-Liste statt Prefix"]

2. **Cookie-Auth via Pairing (AUTH-2 + GAA-3.8).** Eltern legt Gerät an im
   Eltern-Chat (GAA), Bot postet Pairing-Link, User öffnet auf Zielgerät,
   Backend setzt `xbuddy_session`-Cookie (90 Tage rolling). Gleicher
   HMAC-Sign-Key wie initData (Bot-Token), keine zweite Geheimnis-Quelle.
   Gilt für **alle** User-Endgeräte mit Telegram (Eltern-Phones/Tablets/Laptops
   und Kind-Tablet — Setzung 2026-06-12).
   [Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
   → E2 „Eltern-Browser-direkt via Cookie"; Memory
   `project_xbuddy_telegram_endgerate_pflicht`]

3. **AUTH-5 Loopback-Bypass formalisiert.** Eltern-Chat-Skill ruft intern;
   Identität läuft über Heim-Pi-Loopback (`127.0.0.1`). AUTH-5 ist
   Konvention, nicht Implementierungs-Zufall.
   [Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
   → E4 „Loopback-Bypass formalisieren"]

4. **AUTH-6 als dokumentierter Schuldstand.** Alle noch-nicht-migrierten
   Routen leben hier mit Pflicht-Defer-Trigger. Watchdog-Hook bei neuen
   Mini-App-PRs verlangt Einordnung in AUTH-3/4/5/6.
   [Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
   → E3 „AUTH-6 Backlog akzeptieren"]

5. **AUTH-9 Decorator-Verriegelung.** Test prüft maschinell, dass jede
   AUTH-3-Route den Decorator wirklich im Source trägt. Ohne diesen Test
   bleibt die Spec kosmetisch (Belegfall vor 2026-06-16).
   [Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Pflicht-Patches"
   → Patch C „Test-Hook auf Decorator-Anwendung"]

**Übergeordnete Setzung (ratifiziert):** MAD-7 wird nicht gehärtet, sondern
läuft schrittweise aus. Cookie-Auth wird Standard-Mechanismus für migrierte
Routen. Mini-Apps bleiben dokumentiert PUBLIC bis flow-für-flow migriert.
[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
→ Übergeordnete Setzung „Mini-App-Pfad wird NICHT gehärtet"]

## Verworfene Alternativen

- **Mini-App-Pfad härten (Variante A im R2-Vorschlag).** Verworfen, weil
  der UI-Mehrwert der nahtlosen Mini-App-im-Chat-Erfahrung durch den
  PWA-First-Pivot (RAT-19, separat) für tägliche Power-Flows ohnehin
  reduziert wird; doppelter Auth-Bau ohne sichtbaren Familien-Nutzen.
  Nic-Diskussion: „würde der Stoßrichtung zustimmen wenn auth in telegram
  schon gelöst wäre, ist aber nicht. Also müssen wir beides bauen ohne
  ersichtlichen Mehrwert im UI" — Variante B (Cookie als Standard,
  Mini-App-Pfad PUBLIC bis migriert) gewinnt.

- **Funnel-FQDN als Pflicht.** Verworfen in der parallelen Power-Flow-Runde
  (`conventions/urls.md` URL-11 + `specs/platform/ca-verteilung.md`
  CAV-2/CAV-5 erlauben lokal-CA-Pfad; Funnel-only wäre Cloud-Reflex).

- **Display-Renderer-Klasse als V1-Bestandteil (AUTH-7 hart).** Verworfen
  als Phase-4-Vorbereitung. Pi-Display und Kind-Tablet bleiben V1 wie
  heute (LAN-Trust faktisch, nicht ratifiziert); ratifizierte nginx-Map
  kommt mit der Display-Renderer-Migration.

- **Blanket-Allowlist auf `/display/*`.** Codex-Bruch: `/display/_shared/`
  ist Mini-App-Asset-Pfad über Funnel; pauschale Allowlist würde Mini-App-
  Icons brechen. Statt dessen explizite `^~ /display/<buddy>/` und
  `^~ /display/_shared/`-Ausnahmen vor dem Renderer-Match (Skizze AUTH-7,
  Phase-4-Detail).

## Verträglichkeit mit bestehenden RATs

- **RAT-16 (Telegram-MVP).** Verträglich. Telegram bleibt Bot-Plattform;
  die Mini-App-Distribution wird durch RAT-19 (Power-Flow-PWA) ergänzt,
  nicht ersetzt. Vendor-Adapter-Disziplin (`platform.js`-Wrapper) bleibt
  bindend.
- **RAT-8 (parent-Stufe-Token-Defer).** Unverändert — Token-Stufen lebten
  in `tokens.css`, nicht in der Auth-Schicht.
- **RAT-17 (Hörbuchbuddy n=2-Instanzen).** Unverändert — hörspiel-Routen
  sind in AUTH-6 bis zur Phase-3-Migration.

## Konsequenzen

- **Phase 1 (jetzt, #948):** Cookie-Lib (`eltern-chat/session.py`),
  `/auth/pair`-Endpoint, GAA-3.8 Pairing-Schritt, `paired_at`-Feld in
  `geraete.json`, `require_init_data` akzeptiert Cookie zusätzlich,
  AUTH-3 hart auf essen-einkauf, AUTH-9-Test, AUTH-5-Loopback-Bypass.
- **Phase 2 (#949 nach Bewährung):** PWA-Bau essen-einkauf (separat in
  RAT-19 ratifiziert).
- **Phase 3–5:** routine, hörspiel, Display-Renderer, AUTH-6-Abarbeitung
  je eigene Tickets, je Phase-Trigger.
- **Phase 6:** MAD-7 endgültig aus `conventions/mini-app-design.md`
  entfernen, wenn AUTH-6 leer ist und kein Bot-Skill mehr web_app-Buttons
  mit initData-Pfad postet.

## Belegfall

#708 (Mini-App-Auth-Härtung) wurde 2026-06-15 zurückgerollt, weil das
Kind-Tablet kein `initData` hat → `401`. Heutiger Zustand: alle Mini-Apps
PUBLIC. RAT-18 ratifiziert den Pfad, der diesen Zustand auflöst:
PWA + Cookie statt MAD-7-Härtung.
