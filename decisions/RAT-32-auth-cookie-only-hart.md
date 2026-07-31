# RAT-32 — Auth Cookie-only-hart: AUTH-7a Operator-IP entfällt, Flip via ENV-Naht (Amendment RAT-27)

**Status:** RATIFIZIERT 2026-07-27 (Nic-Setzung „direkt-heute")
**Amendment zu:** RAT-27 (Dual-Gate „Cookie ODER Operator-IP")
**Epic:** #1338 (Auth-Härtung) · **Bezug:** #1389/#1413 (Enforcement), #1427/#1430 (Hard-Flip-Revert), RAT-31 (Wirbelsäule-Abriss / #1339)
**Entscheid-File:** `brainstorm/berater-runde/20260727-160000-RATIFIZIERT-auth-cookie-hart-flip.md`

## Setzung
Die Funnel-exponierten **7b-Renderer** werden **Cookie-only-hart**; die
**Operator-IP-Alternative (AUTH-7a) entfällt**. Auslöser: der Pi-Kiosk wurde auf
den öffentlichen Funnel + `xbuddy_session`-Cookie umgestellt (headless-Pairing
via `buddyboard-core/deploy/pi-display/pair-kiosk.sh`); Nic sieht keine
Notwendigkeit für die Operator-IP-Route mehr.

## Was gilt
- **Cookie ist der einzige nicht-Loopback-Zugangspfad.** `ist_operator_ip`
  grantet keinen Zugang mehr (bleibt nur fürs Observe-Log).
- **Unberührt:** AUTH-5 Loopback-Bypass (Server-zu-Server); tma/initData
  (Eltern-Mini-Apps essen/plan/photo/routine/kibuddy — „Cookie-only" meint die
  7b-Renderer, NICHT das Streichen von tma).
- **Flip via ENV-Naht** `XBUDDY_AUTH_MODE=observe|hard` (Default `observe` →
  verhaltensneutraler Deploy). Flip/Rückroll = ENV+restart = echte
  Zwei-Wege-Tür — KEIN Code-Revert (Lehre aus #1427→#1430: der Hard-Flip war
  hartkodiert, der Revert ein Code-Diff).
- **Scope:** seiten `/shell`(+sw) und router `/display` · `/controller` ·
  `/api/v1/displays/<id>/events`. Die decorator-freien Services
  (wetter/familie/geraete/panel/hoerspiel) bleiben **ausgeklammert** — Multi-
  Geräte-Wirbelsäule, mit RAT-31-Abriss (Epic #1339) geschnitten statt hier
  decorator-nachgerüstet. **[AMENDIERT 2026-07-30]** hoerspiel fällt aus dieser
  Ausklammerung **heraus**: der Hörspiel-Player ist eine **lebende PWA**
  (iOS+Android bestätigt) mit gebautem Player-Cookie (#1292), kein sterbender
  Wirbelsäulen-Teil — die „stirbt"-Annahme war überholt (Nic „Cookie wie alle
  anderen", 2026-07-30). Seine Datenrouten migrieren regulär AUTH-6→AUTH-3
  (HART-Cookie, Phase 3, #1640). Ausgeklammert bleiben nur
  wetter/familie/geraete/panel (echte RAT-31-Abriss-Ziele; familie zusätzlich
  extern per nginx-403 abgeschaltet, #1638).

## Rollout (Nic: aggressiv, Schmerz reaktiv auffangen)
Kein Vollprävention-Gate. Zwei Nicht-Verhandelbare bleiben (sicher-bekannte
Brüche, kein Overhead): (1) die ENV-Naht (macht das reaktive Auffangen billig);
(2) die PWA-Manifest-Publicness (Shell-Manifest ist bereits ungegatet, Display-
Manifest ist Legacy-Vor-Shell). Der Code-Merge ist verhaltensneutral (Default
`observe`); der eigentliche Flip = `XBUDDY_AUTH_MODE=hard` auf den Services +
restart, nachdem die aktive Flotte gepairt ist.

## Kill-Kriterium
Ein gepairtes Gerät bekommt nach dem Flip `401` → ENV sofort zurück auf
`observe` (RAT-27-Kill wörtlich). Offen: iOS-ITP-Cookie-Überleben (#948,
~8-Tage-iPhone-Test) → bei Bruch Re-Pair-Nudge (AUTH-8 V2 tg://), nicht
Cookie-Lebensdauer nachjustieren.

## Wo es landet
`specs/platform/auth.md` (AUTH-3.a Amendment-Block, AUTH-7a-Streichung);
`router/main.py` + `seiten/main.py` (Decorator: Operator-IP-Branch entfernt,
`_AUTH_MODE` ENV-Naht); `decisions/INDEX.md`.
