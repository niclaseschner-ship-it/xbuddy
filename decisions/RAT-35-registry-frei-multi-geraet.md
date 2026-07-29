# RAT-35 — Registry-freie Multi-Geräte-Shell: n anonyme Geräte parallel (Amendment RAT-31/RAT-29)

**Status:** RATIFIZIERT 2026-07-29 (Nic-Setzung)
**Amendment zu:** RAT-31 (ein Gerät für immer, Wirbelsäulen-Abriss) / RAT-29 (ein Gerät = ein Ziel)
**Epic:** #1339 (RAT-31-Abriss) · **Bezug:** #1546 (Bau ①), #1574 (Auflösung ②), #1575/#1565 (Auth ③), #1218
**Entscheid-File:** `brainstorm/berater-runde/20260729-1230-RATIFIZIERT-registry-frei-multi-geraet.md`

## Setzung
Der Nordstern „**ein Gerät für immer**" (RAT-31/RAT-29) wird ergänzt zu
**n anonyme Geräte parallel, registry-frei**. Pi-Kiosk **und** Tablet laufen
gleichzeitig; die PWA installiert sich auf beliebigem Gerät und läuft robust in
der richtigen Größe. Auslöser: „nur die Pi läuft, das Tablet geht nicht wegen
Auflösung" — reale Multi-Geräte-Nutzung.

## Harte Invariante — registry-frei
Die Geräte müssen dem System **NICHT** zentral bekannt sein. Die abgerissene
Multi-Geräte-Routing-Wirbelsäule (`geraete/`-Registry, Fanout, `display_id`-
Bindung) **bleibt tot** — der Unterschied zu vor-RAT-31 ist genau, dass **kein**
Geräte-Register zurückkehrt. „Key per `panel_id`" ist damit **ausgeschlossen**
(setzt bekannte Panels voraus); der Isolations-Schlüssel ist ephemer und
geräte-anonym.

## Drei Fäden (Berater-Runde 2026-07-29)
1. **State-Isolation — Mechanismus B (MACH ES).** Der prozess-globale
   `_shell_state` (seiten/main.py) wird ein Dict `sid → {state, subscribers}`,
   gekeyt per ephemerer client-`crypto.randomUUID()` (`sid`, pro Shell-Dokument,
   nicht persistiert, GC bei leerem Subscriber-Set). Broadcast nur an dieselbe
   `sid`. **SHELL-4-Spec bleibt** (additives Keying). **Verworfen A**
   (client-seitig postMessage): sauberer + löste #1542 gratis, aber SHELL-4/5-
   Spec-Umschrift + Gabelung der geteilten `app-panel`-Lego-Sorte. B = kleinstes
   Delta (Constitution: Einfachheit > Flexibilität), spiegelt das ROU-22-Muster
   mit ephemerem statt bekanntem Key; A-Migration bleibt offen. Bau #1546.
   **Kill-Kriterium:** wächst nach Reconnect die EventSource-Zahl (Geister-`sid`)
   → `sid` pro *Tab* (`sessionStorage`) statt pro *Verbindung*. Abnahme =
   SHELL-4-Zwei-Shell-Probe (heim-shell.md manuelle_probe).
2. **Auflösung.** Buddy-Views responsiv statt fixe 1920/1080; toter
   `--kiosk-w`-Token weg, `plan_kinder.html` fluid. Führt #1218 (ratifiziert
   2026-07-03 „breit responsiv") aus. Bau #1574. RAT-24-Render-Gate als Netz.
3. **Registry-freie Auth.** = RAT-31 E6c (#1565): `/auth/pair` Kind/Eltern aus
   **Pairing-Token** statt `geraete.json`, `paired_at`/Tracking sterben. Plus
   Deploy: `ELTERNCHAT_BOT_TOKEN`-EnvironmentFile für photo/wetter/plan (#1575,
   foto-500).

## Reversibilität
Amendment = Ein-Wege-Tür (Nordstern-Setzung, entschieden). Mechanismus B =
Zwei-Wege-Tür (Dict-Swap im selben Modul, A-Migration offen). Runde leicht
gefahren (R1-read → R2-propose → gezielter Sanity-Grep; kein Voll-Pingpong).

## Was unberührt bleibt
RAT-31 (Wirbelsäulen-Abriss), RAT-18/27/32 (Cookie-only-hart-Auth — nicht
aufweichen), SHELL-5 (Iframe-`src`-Swap). Antiberater=Opus-Fallback (Codex-Limit).
