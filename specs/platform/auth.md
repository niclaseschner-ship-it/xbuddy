# Auth-Strategie — Spec     (ID-Präfix: AUTH)

> Status: V1 (Phase 1, essen-einkauf-Scope) · Refs #948
> Provenanz: `brainstorm/berater-runde/2026-06-16-1123-RATIFIZIERT-auth-strategie-5-klassen.md`
> Decision-Record: `decisions/RAT-18-auth-strategie.md`

Die Auth-Spec trägt die Sorten-Grenze für API-Zugriffe in xbuddy. Sie
definiert, **wer mit welchem Token-Typ welche Route ansprechen darf**, und
verteilt die Routen auf vier Klassen (Pfad-1 Mini-App-Daten, Pfad-2 Public-
Assets, Pfad-3 Loopback-Server-zu-Server, Pfad-4 Backlog). Die Spec ist
**Verhalten**, nicht Implementierung: der konkrete HMAC-Code lebt in den
Service-Modulen und ist über die Klauseln hier verriegelt.

**V1-Scope (Phase 1):** AUTH-1..AUTH-6 + AUTH-8 + AUTH-9. AUTH-3-Liste
enthält **nur essen-einkauf-Routen**. Weitere Power-Flows wandern phasen-
weise hinzu (Reihenfolge im RAT-18 verankert).

**Out-of-Scope V1** (eigene Phase, sobald gebraucht): AUTH-7 (Display-
Renderer nginx-Map, Phase 4) · AUTH-8-V2-Deep-Link · Cookie-Revoke-Liste ·
Multi-Device-Listing · Matrix-Adapter (RAT-16-Trigger nicht erreicht).

## 1. Sorten-Grenze

### AUTH-1 — Routen-Präfix-Grenze, nicht User-Rolle

Die Auth-Mechanik trennt API-Zugriffe nach **Routen-Sorte**, nicht nach
User-Rolle:

| Pfad | Routen | Identität | Mechanik |
|---|---|---|---|
| Pfad-1 — Mini-App-Daten | `/api/v1/<buddy>/...`-Datenrouten (AUTH-3-Liste) | identifizierter Familien-User | Cookie ODER `tma`-Header (AUTH-2) |
| Pfad-2 — Public-Assets | Asset-/Bootstrap-Routen (AUTH-4-Liste) | keine | keine |
| Pfad-3 — Loopback Server-zu-Server | Eltern-Chat-Skill ruft intern (AUTH-5-Liste) | Backend-Prozess | Quell-IP `127.0.0.1` |
| Pfad-4 — Backlog / dokumentiert offen | alle noch-nicht-migrierten Routen (AUTH-6) | — | keine (PUBLIC) |

**Reichweite der Klassen:** Pfad-1 (AUTH-3) trägt **alle User-Endgeräte mit
Telegram** — Eltern-Phones, Eltern-Tablets, Eltern-Laptops und **Kind-
Tablet** (Setzung 2026-06-12: jedes User-Endgerät hat Telegram installiert,
Onboarding ohne Telegram findet nicht statt). Jedes dieser Geräte
durchläuft GAA-3.8 (`specs/platform/geraet-anlegen.md`) und bekommt einen
`xbuddy_session`-Cookie über den Pairing-Link.

**Pi-Display ist explizit kein User-Endgerät** — es ist ein HDMI-Stick im
Wohnzimmer, ohne Telegram, mit eigenem Operator-Pfad (SSH-Setup,
`url.conf`-Pflege). Die Display-Renderer-Klasse für Pi-Display (Pfad-2 der
R2-Analyse) ist V1 nicht ratifiziert; sie kommt in Phase 4 als AUTH-7.

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Konvergenz auf Stoßrichtung"
→ Sorten-Grenze-Tabelle; Memory `project_xbuddy_telegram_endgerate_pflicht`
→ „Alle User-Endgeräte haben Telegram, Pi-Sticks bekommen separaten
einfacheren Operator-Pfad"]

*Tickets:* #948

## 2. Identitätsquelle

### AUTH-2 — Cookie oder tma-Header, additive Akzeptanz

Eine API-Route der AUTH-3-Liste antwortet `200`, wenn **eine** der beiden
Identitätsquellen valide ist:

- **Cookie `xbuddy_session`** — HMAC-SHA256 über `user_id + exp`, Sign-Key
  ist der Bot-Token (kein zweites Geheimnis). **`HttpOnly`, `Secure` (HTTPS-Only),
  `SameSite=Lax`**, 90 Tage **rolling**. Bezug der Cookie: Pairing-Endpoint
  (AUTH-2.a) nach Geräte-Anlage (`geraet-anlegen.md` GAA-3.8).

  **`HttpOnly` ist Pflicht — Sicherheit UND iOS-Persistenz.** Der Cookie wird
  ausschließlich server-seitig per `Set-Cookie`-Header gesetzt (nie per JS). Das
  hält ihn (a) XSS-unlesbar und (b) außerhalb der Safari-ITP-Deckelung, die nur
  *client-seitige* (`document.cookie`) Cookies auf 7 Tage — bzw. 24 h bei
  Link-Decoration (der `?token=`-Query aus dem Telegram-Pairing-Link) — begrenzt.
  Server-gesetzte `HttpOnly`-First-Party-Cookies halten bis zum Browser-Cap
  (~400 Tage), sofern PWA und `/auth/pair` auf **derselben Funnel-FQDN** liegen
  (echte First-Party). `SameSite=Lax` ist nötig, damit der Cookie die
  Top-Level-Redirect-Navigation aus dem Pairing-Link überlebt.

  **Rolling-Refresh (Auffrischung über die PWA):** jede Route mit valider
  Cookie-Quelle — AUTH-3-Routen (über den `require_init_data`-Decorator) **und**
  AUTH-2-Cookie-only-Routen (Hörspiel-Player als iOS-Persistenz-Vehikel, #1292,
  Nic-Option-B 2026-07-07) — setzt den Cookie mit frischem 90-Tage-`exp` neu
  (`Set-Cookie` auf der Antwort). Damit rollt **jeder PWA-Start** den Cookie vor;
  aktiv genutzte Geräte laufen faktisch nie ab. Bei fehlendem/abgelaufenem Cookie greift die
  AUTH-8-Re-Pair-Seite (401). **Persistenz-Validierung im echten Betrieb — kein
  Vor-Gate (Nic-Setzung 2026-07-06):** die iOS-Persistenz wird an einer **bereits
  installierten Live-PWA** (Hörspiel-Player, auf Familien-iOS+Android in täglicher
  Nutzung) beobachtet, **nicht** in einem vorgeschalteten 8-Tage-Labortest. Der
  Rolling-Refresh (jeder App-Start rollt vor) + die AUTH-8-Seite fangen einen
  etwaigen ITP-Drop ab; fällt der Cookie in echter Nutzung wiederholt, ist das das
  Signal für einen Re-Pair-Nudge (AUTH-8 V2, `tg://`-Deep-Link). Gebaut wird ohne
  Wartezeit, getestet wird durch Benutzen.

  **OQ-1 — Kiosk-Dauerbetrieb Rolling-Refresh-Heartbeat (#1390):** Kiosk-Geräte
  (Display-Client `/display/<display_id>/`) laufen 24/7 ohne Nutzer-Interaktion.
  Die SSE-Verbindung (`/api/v1/displays/<display_id>/events`) ist eine einzige
  long-lived HTTP-Antwort — das `Set-Cookie` beim initialen Connect rollt den Cookie
  **nicht** täglich vor. Ohne Gegenmaßnahme könnte der Cookie nach 90 Tagen ablaufen
  und der Kiosk sieht die AUTH-8-Seite (silent break über Nacht). **Lösung:** der
  Display-Client (`display-client/index.html`) sendet einmal täglich (86 400 s)
  einen authentifizierten HEAD-Request an `location.href` (`/display/<display_id>/`).
  Diese Route trägt `require_dual_gate(mode='observe')` — bei validem Cookie setzt
  der Decorator ein frisches `Set-Cookie` (Rolling-Refresh). Keine neue Route nötig:
  der bestehende authentifizierte Traffic reicht. Best-Effort (kein UI-Bruch bei
  Netzfehler; Fetch-API-Check vor setInterval). Refs #1390.
- **Header `Authorization: tma <initData>`** — wie `conventions/mini-app-design.md`
  MAD-7 beschrieben, HMAC-Validierung über `eltern-chat/init_data.py`.

Beide Quellen sind **gleichberechtigt** und werden vom selben Decorator
geprüft. Fehlt beides oder ist beides ungültig, antwortet die Route `401`
mit AUTH-8-Anweisungsseite. Die Reihenfolge der Prüfung ist Implementierungs-
Detail; der Vertrag ist „eine valide Quelle reicht".

Die additive Akzeptanz ist **bewusst** so gewählt: Mini-Apps im Telegram-
WebView bleiben funktional (initData-Pfad), neue Power-Flow-PWAs nutzen den
Cookie-Pfad. MAD-7 läuft schrittweise aus (Phase 6: vollständige Ablösung
durch Cookie, wenn AUTH-6 leer ist).

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Konvergenz auf Stoßrichtung"
→ „Pfad-1 — User-API"-Definition und Cookie-Mechanik; Nic-Verdikt-Sektion
→ E2-Zusatz „MAD-7 obsolet, kein initData-Hardening"]

#### AUTH-2.a — Pairing-Endpoint `/auth/pair`

Der Endpoint `GET /auth/pair?token=<X>` prüft den 15-Minuten-Pairing-Token
(HMAC mit dem Bot-Token, aus dem Bot-Skill GAA-3.8 generiert), setzt bei
Erfolg den Cookie `xbuddy_session` und redirected **neutral** auf die
Geräte-/URL-Übersichtsseite `/api/v1/seiten/uebersicht` (SREG-12).

**RAT-31 E6c (Nic-Setzung 2026-07-29, #1565) — neutraler Redirect für alle,
korrigiert die frühere verwendungs-abhängige Ableitung:** Der Endpoint liest
**keine** geraete.json mehr (die Registry ist tot, `geraete.md` ENTFALLEN),
schreibt **kein** `paired_at` und leitet **kein** verwendungs-abhängiges Ziel
ab. Es gibt keinen rollen-tragenden Token. Alle Geräte landen auf der
Übersicht; die Rolle (Kinder-Display vs. Elterngerät) wählt das Elternteil
**beim PWA-Installieren am Gerät**, nicht der Server. Der frühere
verwendungs-abhängige `/display/<id>`-Redirect (Nic-Setzung 2026-07-27, #1372)
ist damit aufgehoben.

Bei ungültigem oder abgelaufenem Token antwortet der Endpoint `400` mit
einer Anweisung, einen neuen Pairing-Link im Bot anzufordern.

**Familien-Geräte — Link auf Funnel-FQDN, kein Zertifikat (#1380):** Der
nachgeschickte Pairing-Link (`geraet-anlegen.md` GAA-3.9,
`cookie_nachschicken`) zeigt auf die **Funnel-FQDN** (PWA, LE-Cert), NICHT
auf `:8443` — so brauchen Familien-Geräte kein Zertifikat, nur den
`xbuddy_session`-Cookie (AUTH-2, First-Party auf derselben Origin). Die
Cert-Verteilung bleibt dem `:8443`-Operator-Pfad vorbehalten. **Geräte-
Autorisierung für alle Erwachsenen der Familie (CNS-2, #1401):** einen
frischen Pairing-Link für ein bestehendes Gerät dürfen alle Erwachsenen
(`art=erwachsene` in der Familien-Registry) anfordern — strenger als die
Familien-Gruppen-Mitgliedschaft (Kinder ausgeschlossen), weil der Link ein
Credential ist. Die Erwachsenen-Liste wird live vom Familie-Service geholt;
ist er nicht erreichbar, lehnt die Aufgabe defensiv ab (fail-closed). [Nic-
Setzung 2026-07-07, #1380 — ursprünglich Master-ID-only; auf alle Erwachsenen
erweitert #1401 — Bezug #948]

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „R2-Patches"
→ Patch B Pairing-Cookie-Mechanik]

*Tickets:* #948

## 3. Klassifikation der Routen

### AUTH-3 — Mini-App-Datenrouten, hart geschützt

Eine Route in der AUTH-3-Liste antwortet `401` bei fehlender oder ungültiger
Identitätsquelle (AUTH-2). Die Liste ist **explizit** — kein Prefix-Match,
sondern ein eindeutiges Verzeichnis. Eine neue Mini-App-Datenroute wird
durch Spec-Änderung in dieser Liste ergänzt (kein Implementierungs-Detail).

**V1-Liste (Phase 1, essen-einkauf):**

```
/api/v1/essen/wuensche                        (GET)
/api/v1/essen/wuensche                        (POST)
/api/v1/essen/wuensche/<wunsch_id>            (PATCH)
/api/v1/essen/wuensche/<wunsch_id>            (DELETE)
/api/v1/essen/katalog                         (GET)
/api/v1/essen/katalog/gerichte                (POST)
/api/v1/essen/katalog/gerichte/<gericht_id>   (PATCH)
/api/v1/essen/katalog/gerichte/<gericht_id>   (DELETE)
/api/v1/essen/fotos                           (POST)
/api/v1/essen/fotos/<medium_id>               (GET)
/api/v1/essen/fotos/<medium_id>               (DELETE)
/api/v1/essen/fotos/<medium_id>/thumbnail     (GET)
```

**Phase-1-Nachtrag — Trigger gefeuert (2026-07-06, Nic-Setzung).** Der
Audit-Funnel-Befund (#1338: `/api/v1/photo/*`, `/api/v1/kibuddy/*` und
`/api/v1/plan/*` extern über den Funnel erreichbar — Fotos abruf-/löschbar, Plan
schreibbar, KiBuddy-Prompt überschreibbar) IST der in AUTH-6 geforderte
„belegte Auth-Schmerz". Damit werden neu in AUTH-3 (hart geschützt) klassifiziert:

- **photo:** `/api/v1/photo/medien`, `/api/v1/photo/medien/<medium_id>`,
  `/api/v1/photo/medien/<medium_id>/thumbnail`
- **kibuddy:** `/api/v1/kibuddy/config`, `/api/v1/kibuddy/frage`,
  `/api/v1/kibuddy/prompt`, `/api/v1/kibuddy/reset`, `/api/v1/kibuddy/vorlesen`,
  `/api/v1/kibuddy/audio/<datei>`
- **plan:** die `/api/v1/plan/*`-Routen (aus AUTH-6 hierher gewandert):
  `admin/aktivitaeten[/<art>]`, `admin/kalender`, `admin/reload`, `aktivitaet`,
  `aktivitaeten`, `defaults`, `slot-modell`, `termine[/bulk]`, `zuteilung`.
- **routine:** die `/api/v1/routine/*`-Datenrouten (aus AUTH-6 hierher gewandert,
  **Phase-2-Trigger gefeuert 2026-07-30**, Bau #1639): `config`, `items`.
- **hoerspiel:** die `/api/v1/hoerspiel/<kind_id>/*`-Datenrouten (aus AUTH-6
  hierher gewandert, **Phase-3-Trigger gefeuert 2026-07-30**, Bau #1640):
  `config`, `alben`, `alben/<id>/manifest`, `resume`, `themen`,
  `folgen-vorschlag`. (`audio-stream` bleibt AUTH-6/Phase-4.)

Die **method-explizite** Endliste (GET/POST/PATCH/DELETE je Pfad) enumeriert der
**#1321-Bau** gegen die realen Routen; der AUTH-9-Coverage-Test
(`tests/test_auth_decorator_coverage.py`) verifiziert, dass **jede** gelistete
Route den Auth-Decorator trägt. Die `/display/…`-Renderer-Routen
(`/display/photo/rahmen`, `/display/kibuddy/frage`, `/display/plan/woche`) bleiben
**außerhalb** AUTH-3 — ihre Funnel-Exposition ist die separate AUTH-7-Frage
(Phase 4, V1 nicht ratifiziert). `/healthz` (SVC-6) bleibt unauthentifiziert.

**Bau-Gate:** der Rollout wartet auf das Cookie-iPhone-Persistenz-Gate (AUTH-2).
#1292 (Player-Cookie/401) ist gebaut (2026-07-07, HSP-47 AUTH-2 Cookie-only).

Jede Zeile ist eine eindeutige Flask-Route mit konkretem URL-Pfad und HTTP-
Methode — keine Sammel-Zeilen mehr (eine Zeile pro tatsächlich registrierter
Route, sonst kann der AUTH-9-Test den Decorator-Anwendungs-Stand nicht
eindeutig prüfen).

Die Phase-2- (routine) und Phase-3-Migration (hörspiel-eltern) sind **2026-07-30
gefeuert** — ihre Datenrouten stehen jetzt oben in AUTH-3 (Bau #1639/#1640), der
hoerspiel-Player-Cookie ist gebaut (#1292). Weitere Routen kommen mit künftigen
Power-Flow-Migrationen; bis dahin sind sie in AUTH-6 dokumentiert.

**#1321-Endliste (method-explizit, photo/kibuddy/plan).** Der #1321-Bau
enumeriert die oben klassifizierten Routen byte-gleich gegen die realen
`@app.route`-Strings; der AUTH-9-Coverage-Test parst diesen Fence mit:

```
/api/v1/photo/medien                          (POST)
/api/v1/photo/medien                          (GET)
/api/v1/photo/medien/<medium_id>              (GET)
/api/v1/photo/medien/<medium_id>/thumbnail    (GET)
/api/v1/photo/medien/<medium_id>              (DELETE)
/api/v1/kibuddy/frage                         (POST)
/api/v1/kibuddy/vorlesen                      (POST)
/api/v1/kibuddy/reset                         (POST)
/api/v1/kibuddy/config                        (GET)
/api/v1/kibuddy/config                        (PUT)
/api/v1/kibuddy/prompt                        (GET)
/api/v1/kibuddy/prompt                        (PUT)
/api/v1/kibuddy/audio/<path:audio_filename>   (GET)
/api/v1/plan/zuteilung                        (GET)
/api/v1/plan/zuteilung                        (PUT)
/api/v1/plan/aktivitaet                       (PUT)
/api/v1/plan/aktivitaet                       (DELETE)
/api/v1/plan/termine                          (GET)
/api/v1/plan/termine                          (PUT)
/api/v1/plan/termine/bulk                     (POST)
/api/v1/plan/aktivitaeten                     (GET)
/api/v1/plan/defaults                         (GET)
/api/v1/plan/defaults                         (PUT)
/api/v1/plan/slot-modell                      (GET)
/api/v1/plan/slot-modell                      (PUT)
/api/v1/plan/admin/reload                     (POST)
/api/v1/plan/admin/kalender                   (PUT)
/api/v1/plan/admin/aktivitaeten               (POST)
/api/v1/plan/admin/aktivitaeten/<art>         (DELETE)
```

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
→ E1 „V1-Scope eng — nur essen-einkauf-API-Routen"]

*Tickets:* #948, #1321

### AUTH-3.a — Soft→Hard-Observe-Leiter beim Route-Rollout (RAT-27 (RATIFIZIERT 2026-07-07))

> **RAT-27 (RATIFIZIERT 2026-07-07).** Diese Klausel wurde mit RAT-27 (#1388,
> Epic #1338) ratifiziert und ist bindend. Der Rollout folgt der Phasen-Tabelle
> (Abschnitt 6).

Wenn eine bisher PUBLIC-Route (AUTH-6) neu unter den Auth-Decorator gezogen
wird, ist der Übergang **route-granular** und **nicht** für alle Routen
symmetrisch. Es gibt zwei Kanten:

- **READ-Routen (GET, idempotent, keine Zustands-Änderung):** dürfen eine
  **Observe/Log-only-Grace** durchlaufen. In dieser Phase prüft der Decorator
  die Identitätsquelle (AUTH-2), **loggt** das Ergebnis (valide Quelle
  vorhanden?), gibt aber **weiter `200` zurück** —
  kein `401`. Sinn: der Rollout beobachtet an echten Requests, ob die
  gepairten Geräte tatsächlich die Cookie/tma-Quelle mitschicken, **bevor**
  er hart zumacht und ein still fehlgepairtes Gerät aussperrt.
- **WRITE-Routen (POST/PUT/PATCH/DELETE) — und die #1321-Flächen
  (photo/kibuddy/plan) unabhängig von der Methode — bleiben HART ab Tag 0.**
  Keine Grace, kein Observe-Fenster: fehlende/ungültige Quelle → `401`
  (AUTH-8). Die #1321-Routen sind **live bereits geschlossen** (#1321 CLOSED,
  extern über den Funnel hart) — die Observe-Leiter darf sie **nicht**
  regressieren, sonst öffnet sie eine schon geschlossene Datenroute wieder.
  Eine schreibende Route ohne Auth ist eine offene Schreib-Fläche; die gibt
  es in keiner Grace-Phase.

**Flip-Gate (Observe → Hard) je READ-Route:** die Route wechselt von
Observe auf Hart, wenn das Observe-Log über ein Beobachtungsfenster **keine**
valide-Quelle-fehlt-Treffer mehr für erwartete Geräte zeigt (sauberes Log).
(RAT-31 E6c, #1565: das frühere Zusatzkriterium „anvisierte Geräte tragen
einen `paired_at`-Zeitstempel" entfällt — die geraete-Registry ist tot, es
gibt kein `paired_at` mehr; das saubere Observe-Log ist der alleinige
Flip-Beleg.) Der Flip ist eine **Zwei-Wege-Tür** pro Route
(Decorator-Modus umschalten, sofort zurückrollbar) — nicht eine
Alles-oder-nichts-Schleuse.

**Kill-Kriterium:** liefert eine READ-Route nach dem Flip einem gepairten
Gerät, das vorher `200` (Observe) bekam, ein `401`, wird die Route sofort auf
Observe zurückgeschaltet und das Observe-Log auf das fehlgepairte Gerät hin
untersucht. Eine WRITE-/#1321-Route, die je `200` ohne valide Quelle liefert,
ist ein Regressions-Bug (nie beabsichtigt).

> **Amendment RAT-32 (RATIFIZIERT 2026-07-27, Nic-Setzung „direkt-heute").**
> Der Dual-Gate wird **Cookie-only-hart** — **AUTH-7a (Operator-IP) entfällt**
> als Zugangs-Alternative. Der Cookie ist der einzige nicht-Loopback-Pfad; der
> **Loopback-Bypass (AUTH-5)** und die **tma/initData-Quelle** (Eltern-Mini-Apps
> essen/plan/photo/routine/kibuddy) bleiben **unberührt** — „Cookie-only" meint
> die 7b-Renderer, NICHT das Streichen von tma. Der Observe→Hard-Flip läuft
> nicht mehr über einen Code-Diff (vgl. #1427 → #1430-Revert), sondern über die
> **ENV-Naht `XBUDDY_AUTH_MODE=observe|hard`** (Default `observe` →
> verhaltensneutraler Deploy; Flip/Rückroll = ENV+restart, echte Zwei-Wege-Tür,
> #1430-Lehre). Scope: die 7b-Renderer (seiten `/shell`, router
> `/display` · `/controller` · `/api/v1/displays/<id>/events`). Die
> decorator-freien Services (wetter/familie/geraete/panel/hoerspiel) bleiben
> **ausgeklammert** — sie sind die Multi-Geräte-Wirbelsäule (RAT-31-Abriss,
> Epic #1339), dort geschnitten statt hier decorator-nachgerüstet.
> [Quelle: `brainstorm/berater-runde/20260727-160000-RATIFIZIERT-auth-cookie-hart-flip.md`]

[Quelle: Rollout-Plan Auth-Funnel #1388 (Epic #1338) + Absicherung, zur
RAT-27-Ratifizierung; Bezug RATIFIZIERT-1338-auth-flow (#1321 hart, live
geschlossen)]

*Tickets:* #1388, #1338

### AUTH-2 (Cookie-only) — Hörspiel-Player-PWA

Routen, die **ausschließlich den Session-Cookie** akzeptieren — kein tma-Header
(Player ist eine Browser-PWA, kein Telegram-Mini-App), kein Loopback-Bypass
(browser-only Route, keine internen Server-Caller). Ein ungültiger oder fehlender
`xbuddy_session`-Cookie → `401`, kein Render. Der Gate lebt **inline** in der
View-Funktion (kein geteilter Decorator, da n=1 — AUTH-9-Coverage-Test gilt
**nicht** für diese Routen).

**V1-Liste (#1292, gebaut 2026-07-07):**

```
/seiten/hoerspiel/player                      (GET) — HTML-Shell
/seiten/hoerspiel/player/<path:asset>         (GET) — manifest.json, sw.js, player.{css,js}, Icons
```

[Quelle: HSP-47 Spec + #1292 Player-Cookie-401; auth.md AUTH-2 Cookie-Mechanik]

*Tickets:* #1292

### AUTH-4 — Public-Assets, kein Decorator

Eine Route in der AUTH-4-Liste antwortet ohne Identitätsprüfung. Sie liefert
Assets oder Bootstrap-Daten, die ein Browser **vor** der Identifikation
laden muss (typisch: JS/CSS einer Mini-App, der den Auth-Bootstrap überhaupt
erst startet).

**V1-Liste:**

```
/api/v1/seiten/static/*                       (Mini-App-Assets)
/api/v1/init-data/validate                    (Bootstrap; prüft selbst)
/api/v1/hoerspiel/<kind_id>/alben/<id>/audio/<track>.mp3   (Kind-Tablet-Player)
/api/v1/hoerspiel/<kind_id>/shared-assets/status   (Diagnose)
/api/v1/icons/suche                           (Asset-Suche)
/api/v1/diag                                  (Diagnose)
/display/_shared/*                            (Mini-App-Icons, MAD-6)
/display/<buddy>/*                            (Buddy-Views)
/shell/<panel_id>/manifest.json               (PWA-Manifest; credential-los per Fetch-Spec, T1448)
/shell/<panel_id>/icon-*.png                  (PWA-Icons; WebAPK-Installer holt credential-los, T1448)
```

Eine Route gehört in AUTH-4, wenn sie **inhaltlich öffentlich** ist — der
Zugriffsschutz lebt nicht in der Route selbst, sondern in der Tatsache, dass
nichts Familienprivates über sie ausgegeben wird.

**V1-Klarstellung zu `/display/_shared/*` und `/display/<buddy>/*`:** Diese
beiden Pfade sind V1 **ohne nginx-Schutz** im Funnel-Pfad öffentlich — die
nginx-Map mit den Ausnahmen `^~ /display/_shared/` und `^~ /display/<buddy>/`
vor dem Renderer-Match lebt erst in AUTH-7 und gewinnt Bindewirkung mit
Phase 4. Bis dahin sind sie de facto offen, sind aber AUTH-4-konform
(inhaltlich öffentlich: Icons, Buddy-Renderer-Views).

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „R2-Patches"
→ Patch A Endpoint-Liste AUTH-4 + Patch B nginx-Map (Phase 4)]

*Tickets:* #948

### AUTH-5 — Loopback Server-zu-Server-Bypass

Eine Route in der AUTH-5-Liste antwortet `200` ohne Identitätsprüfung, wenn
die Quell-IP `127.0.0.1` oder `::1` ist. Sinn: Eltern-Chat-Skill und andere
Backend-Komponenten rufen Mini-App-APIs intern (z. B. `PUT
/api/v1/routine/config` aus dem Eltern-Chat-Konfig-Skill); Identität ist
hier Backend-Prozess-Identität via Heim-Pi-Loopback, nicht User-Identität.

**Mechanik:** Der Loopback-Bypass lebte historisch **je Buddy-Decorator**
kopiert (`essen/main.py`, `routine/main.py`, …). Der n=3-Verbrauch ist
**erreicht und die Lib-Auslagerung ratifiziert** (Berater-Runde 2026-07-30,
`brainstorm/berater-runde/20260730-1900-RATIFIZIERT-auth-decorator-lib.md`,
Antiberater-geprüft): Heimat ist **`tools/initdata/auth_gate.py`** als Factory
(nicht `eltern-chat/init_data.py`, der frühere Kandidat) — siehe Abschnitt
*AUTH-Decorator-Lib* unten. AUTH-9 prüft weiterhin, dass jede AUTH-3-Route den
Decorator trägt; die schrittweise Migration je Buddy (#1383) hält AUTH-9 pro
Schritt grün. **n=3 eingelöst (2026-07-31):** Die Lib-Auslagerung ist vollzogen — alle
AUTH-3/AUTH-5-Buddies tragen den Decorator aus der Factory
`tools/initdata/auth_gate.py`; keine buddy-eigene `require_*`-Definition
existiert mehr in `*/main.py`. Ledger-Spur: #1626 (essen/kibuddy/photo/plan),
#1628 (seiten-dual), #1639 (routine), #1640 (hoerspiel), #1655 (SOFT-Cleanup).
**Kill-Kriterium erfüllt (verifiziert 2026-07-31):**
`grep -rn "def require_init_data\|def require_mini_app_auth\|def require_dual_gate" --include=main.py`
= 0 Treffer auf origin/main.

### AUTH-Decorator-Lib (ratifiziert 2026-07-30, Bau via #1383)

Der duplizierte Flask-Auth-Wrapper wird als **Factory** in
`tools/initdata/auth_gate.py` konsolidiert (die schon bestehende
Auth-Vendor-rein-Heimat mit `ist_operator_ip`/`hat_gueltigen_cookie`). Die
Bausteine (`session_cookie.py`, `init_data.py`) liegen schon geteilt; nur die
Flask-Verdrahtung (request/`g`/`make_response` + AUTH-8-401) war 6-7× kopiert.

**Zwei Factories** (HART + dual). Die früher geplante SOFT-Variante **entfiel
2026-07-30** (Nic-Setzung „Cookie wie alle anderen"): sie hätte nur routine +
hoerspiel getragen, die aber auf HART-Cookie migrieren (SOFT-Pass-through stoppt
den PII-Leak gar nicht — er bedient die Route ohne Header trotzdem). Damit hat
die SOFT-Factory keinen Konsumenten:

- `make_require_init_data(*, get_bot_token, get_familie_client,
  get_init_data_config, auth_401)` — **HART** (Loopback → Cookie+Rolling-Refresh
  → tma-Header → 401). Konsumenten: essen/kibuddy/photo/plan + (per Phase-2/3-
  Migration, #1639/#1640) routine + hoerspiel.
- `make_require_dual_gate(...)` — **AUTH-7b** (Cookie ODER Operator-IP,
  observe/hard). Konsument: seiten.

Die Pro-Buddy-Laufzeit kommt als **Getter-Closures** rein (kein `g`-Context,
keine Registrierung, Import strikt Buddy→Lib). Der `auth_401`-Renderer ist ein
eigener Injektionspunkt, weil 401-HTML-Text und 403-Shape buddy-variant sind.
Der plan-Slot-Sonderfall (`auth_familie_client` statt `familie_client`) löst
sich, weil plans Getter den Slot bereits kapselt — **kein** repo-weites Rename.

**Migration Buddy-für-Buddy** (bisectbar): photo → essen → kibuddy → plan (HART)
→ seiten (dual). routine + hoerspiel migrieren mit ihrem Phase-2/3-Cookie-Schritt
(#1639/#1640) auf dieselbe HART-Factory. Pro Schritt AUTH-9-Test grün +
real-route-Smoke (401-HTML byte-gleich). `test_auth_decorator_coverage.py` ist um
routine + hoerspiel zu erweitern (heute in keiner MODULE_MAP).
✓ eingelöst 2026-07-31 — vollständige Migration abgeschlossen (#1626/#1628/#1639/#1640/#1655);
`test_auth_decorator_coverage.py` deckt jetzt alle MODULE_MAP-Einträge ab.

Der Decorator-Code (egal in welchem Buddy) prüft zuerst — **verbindlich und
load-bearing** — BEIDE Bedingungen zusammen:

```python
if (not request.headers.get("X-Forwarded-For")
        and request.remote_addr in ("127.0.0.1", "::1")):
    g.init_data = None
    return fn(*args, **kwargs)   # AUTH-5-Pass-through
```

Der `X-Forwarded-For`-Ausschluss ist **kein optionaler Zusatz**, sondern das
Herz des Bypass: nginx setzt bei JEDER von außen kommenden Anfrage
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`
(`deploy/nginx/xbuddy-origin.conf`), während `remote_addr` gegenüber dem Buddy
immer `127.0.0.1` ist (nginx proxyt lokal). Ein Browser-Request von außen sieht
für den Buddy also aus wie Loopback — nur das Fehlen von `X-Forwarded-For`
unterscheidet einen echten Server-zu-Server-Call (Eltern-Chat → Buddy, kein
Proxy dazwischen) von einem durchgereichten Fremd-Request. Wer beim n=3-Kopieren
in einen neuen Buddy-Decorator nur `remote_addr` prüft und den
`X-Forwarded-For`-Ausschluss weglässt, reißt ein Auth-Bypass-Loch: dann käme
JEDER externe Request am Cookie/tma-Check vorbei. Trifft die Doppel-Bedingung
zu, läuft die Route ohne Identifikation durch; `g.init_data` ist `None`.

**V1-Liste:**

```
/api/v1/events                                (Eltern-Chat → Router)
/api/v1/hoerspiel/<kind_id>/shared-assets/rebuild   (admin)
/api/v1/<komponente>/admin/*                  (nginx-404 für extern, xbuddy-origin.conf)
```

Server-zu-Server-Routen, die NICHT in AUTH-5 stehen, sind keine — sie
gehören entweder in AUTH-3 (mit Loopback-Bypass als Sonderfall) oder werden
neu klassifiziert.

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
→ E4 Loopback-Bypass formalisieren]

*Tickets:* #948

### AUTH-6 — Backlog, dokumentierter Schuldstand

Eine Route in AUTH-6 ist heute **PUBLIC** (kein Decorator, keine Identitäts-
Prüfung). Sie steht hier explizit, damit der Schuldstand sichtbar und
nachverfolgbar bleibt — nicht versteckt.

Jeder AUTH-6-Eintrag trägt einen **Defer-Trigger**: das Ereignis, bei dem
die Route in AUTH-3 (oder AUTH-4 / AUTH-5) wandert. Ohne Trigger gehört der
Eintrag nicht in AUTH-6, sondern in eine der ratifizierten Klassen.

**V1-Stand:**

```
/api/v1/hoerspiel/<kind_id>/audio-stream      (Trigger: Phase 4 HSP-Audio-Routing — PANEL-13-Naht; Infrastruktur erhalten (app-panel/app.js:819-966), audio_play-Producer ruht bis #1471/HSP-44)
# routine/{items,config} + hoerspiel/{config,alben,alben/<id>/manifest,resume,themen,folgen-vorschlag}: Phase-2/3-Trigger 2026-07-30 gefeuert → jetzt in AUTH-3 (Bau #1639/#1640)
/api/v1/seiten                                (Trigger: Phase 2/3, mini-app-uebersicht-Migration)
/api/v1/seiten/uebersicht                     (Trigger: Phase 2/3)
/api/v1/seiten/mini-app-uebersicht            (Trigger: Phase 2/3)
/api/v1/panels/*                              (Trigger: Phase 4 Panel-Mini-App)
/api/v1/panels/<id>/tiles*                    (Trigger: Phase 4)
/api/v1/geraete/*                             (Trigger: Geräte-Editor-Mini-App)
/api/v1/router/panels/<src>                   (Trigger: Phase 4 Display-Renderer)
/api/v1/displays/<id>/events                  (Trigger: Phase 4)
/api/v1/displays/<id>/state                   (Trigger: Phase 4)
```

**familie-Datenrouten sind KEIN AUTH-6-Migrations-Backlog (RAT-32-Amendment, #1638).**
`/api/v1/familie/personen*` und `/api/v1/familie/foto/*` tragen keinen Defer-Trigger
mehr: `familie` ist ein RAT-31-Abriss-Ziel — es kommt keine extern erreichbare
Familien-Editor-Mini-App. Statt Migration nach AUTH-3 werden diese Routen **extern
permanent per nginx-403 abgeschaltet** (Funnel → `403`); intern (Loopback/Kiosk)
bleiben sie erreichbar. Damit gehören sie nicht in die AUTH-6-Backlog-Liste (die nur
Routen mit Defer-Trigger führt, s. o.). Ratifiziert: RAT-32-Amendment 2026-07-30
(`decisions/RAT-32-auth-cookie-only-hart.md`, nennt #1638) unter RAT-31.

Phase 6 (vollständige Migration) löst AUTH-6 auf. Solange Einträge in
AUTH-6 stehen, ist MAD-7 in `conventions/mini-app-design.md` mit dem
Auslaufens-Hinweis aktiv.

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
→ E3 AUTH-6-Backlog als „dokumentierter Schuldstand" mit Pflicht-Defer-Tag]

*Tickets:* #948

### AUTH-7 — Display-/Shell-Renderer: zwei Zugangs-Klassen (RAT-27 (RATIFIZIERT 2026-07-07))

> **RAT-27 (RATIFIZIERT 2026-07-07).** Diese Klausel ersetzt die frühere V1-Skizze
> (nur-IP-Allowlist) und gabelt AUTH-7 in **7a Operator-Pi** und **7b User-Shell
> (Cookie)**. Sie wurde mit RAT-27 (#1388, Epic #1338) ratifiziert und ist
> bindend. Die Display-/Shell-Renderer-Routen folgen AUTH-6 (Phase-4-offen);
> `heim-shell.md` SHELL-6 hält den LAN-only-Riegel bis zur Phase-4-Umsetzung.

Die frühere Skizze kannte nur **eine** Zugangs-Klasse (nginx-IP-Allowlist,
Funnel → `403`). Der Rollout braucht **zwei**, weil zwei verschiedene
Konsumenten dieselben Renderer-Routen ansprechen:

1. **7a — Operator-Pi (headless, kein User in der Hand).** Der Pi-Stick im
   Wohnzimmer hat kein Telegram, keinen Cookie, keinen Pairing-Pfad
   (`geraet-anlegen.md` GAA-3.8-Operator-Pfad; Cookie-UX-Flow (d),
   `ENTSCHEID-OFFEN-948-cookie-verteilung-ux`). Er wird über **Quell-IP**
   identifiziert: nginx lässt die Renderer-Routen aus dem Heim-LAN/Tailnet
   (`192.168.0.0/16`, `10.0.0.0/8`, `100.64.0.0/10`) durch — das ist Bestand
   aus der alten Skizze. **Zusatz:** die heute unter AUTH-4 PUBLIC laufenden
   `/display/<buddy>/*`-Buddy-Views (auth.md AUTH-4 V1-Klarstellung) werden
   als **explizite Operator-Ausnahme** hier geführt — sie bleiben für den
   headless Renderer erreichbar, ohne Cookie.

2. **7b — User-Shell (Cookie).** Familien-User-Geräte (Eltern-Handy/-Tablet/
   -Laptop, Kind-Tablet als Klasse A) erreichen die Shell **über den Funnel**
   mit `xbuddy_session`-Cookie (AUTH-2) — genau der Pfad, den die Heim-Shell
   für den produktiven Rollout braucht (RAT-25-Ablösung, `heim-shell.md`
   SHELL-6). 7b umfasst:

   ```
   /shell/<panel_id>                             (GET, HTML-Shell, seiten-served)
   /shell/<panel_id>/events                       (SSE-Event-Stream, seiten-served)
   /controller/*                                  (Panel-Controller-Apps, seiten-served)
   ```

   > **RAT-31-Nachzug (E6f, Router-Tod).** Der eigenständige Display-Router
   > (`router/main.py`) ist gelöscht. Die 7b-Renderer-Routen werden jetzt **von
   > seiten** (`seiten/main.py`) ausgeliefert, tragen dort denselben Dual-Gate.
   > Der alte `/api/v1/displays/<display_id>/events`-SSE-Fanout (Router-Hop) ist
   > **ersatzlos entfallen**; der Shell-SSE-Stream läuft same-origin als
   > `/shell/<panel_id>/events` (kein Router-Hop). Die früher hier gelisteten
   > `/display/<id>`-Renderer-Routen sind mit dem Router entfallen; nur die
   > public `/display/_shared/*`-Assets (7b-Public-Ausnahme, unten) leben auf
   > seiten weiter.

**Einheitlicher Eltern-Auth-Pfad (RAT-27 Nic-Bedingung).** 7b ist NICHT auf die
Heim-Shell begrenzt: Cookie-über-Funnel ist **derselbe** Auth-Pfad wie AUTH-3 für
die Eltern-**PWA-Mini-Apps** (essen-einkauf u. a., #948). Damit gilt EIN Modell für
alle Eltern-Geräte — *Eltern-Gerät → Funnel → `xbuddy_session`-Cookie* — für die
**aktuellen und zukünftigen** Eltern-PWA-Mini-Apps (AUTH-3-Datenrouten) **und** die
Shell/Display-Renderer (7b). Eine neue Eltern-PWA-Mini-App dockt ohne Sonder-Auth
an denselben Cookie-Pfad an (kein zweites Auth-Modell).

**Priorität + Auslauf (RAT-27 Nic-Setzung).** Primär ist das **User-Gerät
(Handy/Tablet) per Cookie**; der **7a-Operator-Pi ist Auslaufmodell** (aktuell ein
Familien-Kiosk-Sonderfall). Die 7a-IP-Allowlist wird gepflegt, solange der Pi-Kiosk
existiert, ist aber **kein Ausbau-Ziel** — die cookie-losen Pi-Buddy-/Display-Routen
bleiben vorerst über den Operator-IP-Pfad erreichbar und werden **nachträglich**
gelöst, sobald der Pi ersetzt ist.

**Dual-Gate (Cookie ODER Operator-IP) — verbindlich.** Die 7b-Routen prüfen
**beide** Quellen additiv: eine Anfrage ist berechtigt, wenn **entweder** ein
valider `xbuddy_session`-Cookie vorliegt (User-Gerät über Funnel) **oder** die
Quell-IP in der 7a-Operator-Allowlist liegt (headless Pi im LAN/Tailnet).
**Ohne dieses ODER würde das cookie-lose Pi-Kiosk beim Öffnen einer
7b-Route `401` bekommen** — der Operator-Pi rendert `/display/<id>` und
`/controller/*` ohne je einen Cookie besessen zu haben. Der Dual-Gate ist
das Herz von AUTH-7: Cookie deckt die User-Geräte, IP deckt den Operator,
und nur wer **keins von beiden** hat (fremder Funnel-Client ohne Cookie),
wird `401` (AUTH-8).

**7b-Public-Ausnahmen (Pflicht, sonst 401-Schleife für Ungepairte).** Zwei
Flächen müssen **public über den Funnel** erreichbar bleiben, auch ohne
Cookie und ohne Operator-IP:

- **die AUTH-8-Re-Pair-Anweisungsseite** — ein ungepairtes Gerät bekommt sonst
  `401` auf die Re-Pair-Seite selbst und sitzt in einer Schleife fest;
- **`/display/_shared/*`** (Mini-App-Icons, MAD-6) — inhaltlich öffentlich
  (AUTH-4), von den 7b-Renderer-Views als Asset geladen; hinter den Dual-Gate
  gezogen würde es die Views brechen.

**Bau-Notiz (nicht Spec-Kern, für #1388-Track):** der AUTH-9-Coverage-Test
(`tests/test_auth_decorator_coverage.py`) muss um die 7b-Routen erweitert
werden, sobald 7b gebaut wird — sonst landet der Dual-Gate-Decorator still an
**null** Routen (der Zustand, gegen den AUTH-9 überhaupt existiert). 7a bleibt
eine nginx-/IP-Sache und ist **nicht** über den Python-Decorator-Test
prüfbar; für 7a ist die Verriegelung ein nginx-Conf-Test bzw. das
SHELL-6-Pre-Merge-Funnel-Experiment.

**Reversibilität:** Der Dual-Gate ist route-granular (Decorator pro Route =
Zwei-Wege-Tür, billig zurückzurollen). Die **Origin-/Exposure-Entscheidung**
(Shell über Funnel statt nur LAN) ist die Ein-Wege-Kante — sie hängt an der
RAT-27-Ratifizierung und am SHELL-6-Funnel-Experiment (externer Client, nicht
vom Pi — Hairpin-Falle).

[Quelle: Rollout-Plan Auth-Funnel #1388 (Epic #1338) + Absicherung, zur
RAT-27-Ratifizierung; Bezug alte AUTH-7-Skizze (nginx-Map), RAT-25
(Heim-Shell-LAN-only), Cookie-UX-Flow ENTSCHEID-OFFEN-948]

*Tickets:* #948, #1388, #1338

## 4. Auth-Verlust-Behandlung

### AUTH-8 — 401 rendert Anweisungsseite, nicht rohen Fehler

Antwortet eine AUTH-3-Route mit `401`, rendert das Backend eine HTML-Seite
mit Anweisung an den User, nicht einen rohen Status-Code. Die Seite enthält
mindestens:

- Geräte-Name (neutraler Hinweis; kein geraete.json-Lookup mehr — RAT-31 E6c).
- Anweisung: „Dieses Gerät muss neu verbunden werden. Frag den
  Familien-Chatbot einfach nach einem neuen Cookie für dein Gerät — dann
  geht es wieder. Oder pair im Chat ein neues Gerät."

**V1** ist eine reine Text-Anweisungsseite. **V2** ergänzt einen `tg://`-
Deep-Link (`tg://resolve?domain=<bot>&start=neu_pairen_<display_id>`), der
Telegram öffnet und den Bot-Skill direkt anspringt; der Bot fragt nur
Bestätigung und postet den neuen Pairing-Link.

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Konsequenz Phase 1"
→ „401-Anweisungsseite mit Display-/Geräte-Name + Bot-Command-Hinweis";
Chat-Verfeinerung 2026-06-16 V1-/V2-Aufstockung]

*Tickets:* #948

## 5. Verriegelung

### AUTH-9 — Decorator-Anwendung maschinell verriegelt

Ein Test (`tests/test_auth_decorator_coverage.py`) parst die AUTH-3-Liste
aus dieser Spec und prüft per AST des jeweiligen Service-Moduls
(`essen/main.py`, später `routine/main.py`, `hoerspiel/main.py`, …), dass
**jede** in AUTH-3 gelistete Route den Auth-Decorator (`@require_init_data`
oder seine Cookie-Variante) im Source trägt. Fehlt der Decorator an einer
Route, ist der Test rot.

**Begründung:** Ohne diesen Test landet eine AUTH-3-Liste in der Spec, der
Decorator hängt aber an null Routen — der Zustand vor 2026-06-16. Der Test
ist die Membran zwischen Spec-Wahrheit und Code-Wahrheit.

Die Test-Implementierung ist Aufgabe des Phase-1-Bau-PRs; die Klausel selbst
ist Verhaltens-Spec.

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „R2-Patches"
→ Patch C „Test-Hook auf Decorator-Anwendung verriegeln"]

*Tickets:* #948

## 6. Reihenfolge der Phasen

Die Spec wird **phasenweise** ausgebaut, je Power-Flow eine Phase:

| Phase | Inhalt | Trigger |
|---|---|---|
| Phase 1 | essen-einkauf (AUTH-3-Liste V1) + Cookie-Lib + `/auth/pair` + GAA-3.8 + AUTH-9 | jetzt (#948) |
| Phase 2 | routine-anpassen-PWA → AUTH-3 erweitert um routine-Routen | nach Phase-1-Bewährung |
| Phase 3 | hörspiel-eltern-PWA → AUTH-3 erweitert um hörspiel-Routen | nach Phase-2-Bewährung |
| Phase 4 | Panels + Display-Renderer → AUTH-7 aktiviert + nginx-Map live | wenn Phase 3 produktiv |
| Phase 5 | AUTH-6-Bestand abarbeiten (Plan, Familie, Geräte) | wenn Phase 4 produktiv |
| Phase 6 | MAD-7 endgültig löschen | wenn AUTH-6 leer |

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Konsequenz Phase 1"
→ Reihenfolge der Folge-Phasen]

## 7. Operative Abläufe

### PWA-Reinstall über Funnel-Origin (Familien-User-Geräte, #1390)

Wenn ein Familien-Gerät (Eltern-Phone/-Tablet, Kind-Tablet) die PWA neu
installieren muss (z. B. nach Geräte-Reset oder Cookie-Verlust), ist der
Ablauf über die **Funnel-FQDN** (SREG-7 `display_url_origin_funnel`):

1. **Neuen Pairing-Link anfordern** — Elternteil schreibt dem Familien-Bot
   `[Cookie nachschicken für <Gerätename>]`; der Bot antwortet per Privatchat
   mit einem frischen 15-Minuten-Link auf die Funnel-FQDN
   (`https://<funnel-fqdn>/auth/pair?token=<X>`).
2. **Link auf dem Zielgerät öffnen** — Browser (nicht ein anderes Gerät) öffnet
   den Link; `/auth/pair` prüft das Token, setzt den `xbuddy_session`-Cookie
   (HttpOnly, First-Party auf der Funnel-FQDN) und leitet auf die Ziel-URL
   (Shell oder Mini-App-Start) weiter. **Same-Origin-Pflicht:** PWA und
   `/auth/pair` müssen unter derselben Funnel-FQDN laufen; wechselt die
   Origin, sitzt der Cookie im falschen Jar (AUTH-2 iOS-Persistenz-Bedingung).
3. **PWA (re-)installieren** — Browser zeigt „Zum Startbildschirm hinzufügen"
   (iOS: Teilen → Zum Startbildschirm; Android: ⋮ → App installieren). Die PWA
   wird von der Funnel-FQDN installiert und damit First-Party auf dieser Origin.
4. **Verifizieren** — PWA öffnen → Auth-3-Route antwortet `200` (kein 401-Banner).
   Kiosk-Heartbeat (OQ-1) sorgt ab diesem Zeitpunkt täglich für Rolling-Refresh.

**Nicht nötig:** Zertifikat-Install auf dem Gerät (Funnel hat LE-Cert). Der
Pairing-Link ist 15 Minuten gültig; läuft er ab, erneut Schritt 1 auslösen.

*Tickets:* #1390, #948

## 8. User-Endgerät-Flow (Nic-Setzung 2026-07-25, #1338)

### AUTH-10 — Telegram-Deep-Link-Pairing ist der einzige Auth-Pfad für User-Endgeräte

> **ENTSCHIEDEN 2026-07-25 (Nic-Setzung, #1338).** Dies ist kein offener
> Entscheid — der Flow ist ratifiziert und wird hier festgeschrieben.
> Refs: RAT-32 (Cookie-only-hart, 2026-07-27), RAT-27 (Dual-Gate-Basis,
> 2026-07-07), #1338 (Auth-Härtungs-Epic), #1458 (Funnel-Origin).

Jedes **User-Endgerät** (Eltern-Phone, Eltern-Tablet, Eltern-Laptop,
Kind-Tablet) durchläuft **exakt einen** Auth-Pfad:

1. **Pairing-Link über Telegram-Bot anfordern** — das Elternteil schreibt
   dem Familien-Bot (oder nutzt den Geräte-Anlage-Flow `geraet-anlegen.md`
   GAA-3.8); der Bot antwortet mit einem 15-Minuten-Link auf die
   Funnel-FQDN: `https://<funnel-fqdn>/auth/pair?token=<X>`.
2. **Link auf dem Ziel-Gerät öffnen** — Browser öffnet den Link; der
   `/auth/pair`-Endpoint (AUTH-2.a) prüft das Token, setzt den
   `xbuddy_session`-Cookie (HttpOnly, Secure, SameSite=Lax, 90 Tage
   rolling, AUTH-2) und leitet **neutral** auf die Übersichtsseite
   `/api/v1/seiten/uebersicht` weiter (RAT-31 E6c, #1565 — kein
   verwendungs-abhängiges Ziel mehr, die Rolle wählt die Familie beim
   PWA-Install).
3. **Danach: Cookie ist die Identität.** Jeder folgende Zugriff auf
   AUTH-3-Routen oder 7b-Renderer-Routen verwendet den `xbuddy_session`-Cookie
   (RAT-32 Cookie-only-hart); `tma`/`initData` bleibt parallel gültig für
   Telegram-Mini-App-Kontexte (AUTH-2, additiv).

**Telegram ist Voraussetzung — kein alternativer Onboarding-Pfad.**
Kein User-Endgerät erhält Zugang ohne vorherigen Telegram-Pairing-Schritt.
Es gibt keinen alternativen User-Onboarding-Pfad (kein
QR-Code-only-Onboarding, kein lokales Passwort, kein Zertifikat-Install als
User-Auth). Onboarding ohne Telegram findet nicht statt (Setzung 2026-06-12,
Memory `project_xbuddy_telegram_endgerate_pflicht`).

[Quelle: Nic-Setzung 2026-07-25 (#1338); auth.md AUTH-2.a (Pairing-Endpoint);
AUTH-1 Pfad-1-Reichweite; RAT-32 Cookie-only-hart (2026-07-27);
`project_xbuddy_telegram_endgerate_pflicht` Memory.]

*Tickets:* #1338, #1469

### AUTH-10.a — Pi/Operator-Sticks: bewusste Ausnahme vom Telegram-Pfad

**Der Pi-Kiosk (und andere headless Operator-Sticks) ist kein User-Endgerät**
— er wird NICHT über Telegram gekoppelt. Er ist ein HDMI-Stick im Wohnzimmer
ohne interaktive Telegram-Bedienung.

**Post-RAT-32-Stand (2026-07-27):** Der Pi ist auf Cookie umgestellt
(headless-Pairing via `buddyboard-core/deploy/pi-display/pair-kiosk.sh`) und
verwendet ebenfalls den `xbuddy_session`-Cookie — aber über den
**Operator-Pfad**, nicht den Telegram-User-Pfad:

- **Operator-Pairing:** `pair-kiosk.sh` (SSH-Zugang auf den Pi, Oper-Ebene)
  generiert direkt einen Pairing-Token und ruft `/auth/pair` lokal auf — kein
  Telegram-Bot-Interaktion, kein User-Schritt.
- **Kein Telegram installiert, kein Telegram-Pairing** — die
  GAA-3.8-Sequenz (Familien-Bot → Privatchat-Link → Gerät öffnet Link) gilt
  für User-Endgeräte, **nicht** für den Pi.
- **AUTH-7a entfällt (RAT-32):** Die frühere Operator-IP-Alternative (Auth
  ohne Cookie über Quell-IP im Heim-LAN) ist gestrichen; AUTH-7a ist nicht
  mehr als Zugangs-Alternative aktiv. Der Pi kommt heute — wie User-Endgeräte
  — ausschließlich per Cookie in die 7b-Renderer-Routen.
- **AUTH-5 Loopback-Bypass bleibt unberührt** (Server-zu-Server, nicht
  Operator-Pi-Zugang).

**Warum explizit hier:** Der Telegram-Pfad (AUTH-10) ist normativ für
User-Endgeräte. Die Pi/Operator-Ausnahme ist **keine Lücke**, sondern eine
bewusste Klasse: headless Hardware, die kein menschliches Telegram-Konto hat,
braucht einen Operator-Werkzeug-Pfad. Die Klasse ist geschlossen — neue
Familien-Kiosk-Sticks folgen demselben Operator-Pfad (pair-kiosk.sh-Muster),
nicht dem User-Telegram-Pfad.

[Quelle: RAT-32 (Cookie-only-hart, AUTH-7a-Streichung, headless-Pairing via
pair-kiosk.sh, 2026-07-27); AUTH-1 „Pi-Display ist explizit kein
User-Endgerät — Operator-Pfad"; AUTH-7 7a-Auslaufmodell-Notiz; #1338 Epic.]

*Tickets:* #1338, #1469

## Offene Fragen

(Keine offenen Punkte in V1 — alle Klauseln haben Paket-Quelle im ENTSCHEID-
File. Phase-4-AUTH-7-Details werden bei Trigger eigene Berater-Runde.)
