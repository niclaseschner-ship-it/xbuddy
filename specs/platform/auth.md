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
- **panel (Schreib-Endpunkt):** `PUT /api/v1/panels/<panel_id>/tiles` (der
  Panel-Editor-Write, PBE-4). Nic-Setzung 2026-07-31 (#1400 → „a"): der Write
  wird über **denselben same-origin-Cookie-Pfad wie die seiten-Shell** gesichert,
  in die der RAT-31-Ein-Gerät-Modus den Editor re-homed hat — nicht mehr über die
  reine Heimnetz-Grenze (die tote #1389-„7b-Dual-Gate"-Prämisse ist ersetzt). Der
  panel-Service ist heute decorator-frei (auth.md AUTH-Decorator-Lib); der Bau
  trägt den Factory-Decorator wie bei jedem AUTH-3-Buddy nach.
  **READ bleibt außerhalb AUTH-3:** die Display-/Registry-Lesepfade
  (`GET /api/v1/panels/<panel_id>/tiles`, `.../config.json`, PREG-13/14/15) werden
  **nicht** mitgegatet — das Panel-Display ist ein cookieloses Kiosk-Gerät (wie die
  `/display/…`-Renderer unten); ihr app-seitiges Gaten würde den Display-Fetch
  erschlagen (belegter #1338-Bruch). Ihre Funnel-Exposition bleibt die separate
  AUTH-7-Frage.

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

**[ÜBERHOLT 2026-08-11 — Nic-Setzung, siehe AUTH-11]** Zwei Stellen oben in
dieser Sektion tragen dieselbe Prämisse fort, die AUTH-11 ausdrücklich
ausschließt. Erstens der **panel (Schreib-Endpunkt)**-Bullet: „das
Panel-Display ist ein cookieloses Kiosk-Gerät" (Begründung für die
ausgeklammerten Lesepfade `GET /api/v1/panels/<panel_id>/tiles`,
`.../config.json`, PREG-13/14/15) ist genau der Geräte-Ausnahme-Grund, den
AUTH-11 verbietet („Jedes Gerät, das xbuddy konsumiert, trägt ein
`xbuddy_session`-Cookie … 'Das Gerät kann kein Cookie' ist deshalb kein
zulässiger Ausnahme-Grund") — dieselbe Prämisse, bereits zweimal in
`panel-bearbeiten.md` (PBE-3, PBE-4) markiert. Zweitens die namentliche
Aussage zu `/display/photo/rahmen`, `/display/kibuddy/frage` und
`/display/plan/woche`: sie blieben „außerhalb AUTH-3 — ihre
Funnel-Exposition ist die separate AUTH-7-Frage (Phase 4, V1 nicht
ratifiziert)". Das gilt für die Gate-Frage nicht mehr — dieselbe Buddy-
Renderer-Klasse (AUTH-4-Markierung oben, `/display/<buddy>/*`) bekommt einen
Auth-Decorator (Nic-Setzung 2026-08-11, umgesetzt in #1805 über fünf
parallele Bau-Stücke). Die AUTH-7-Phase-4-nginx-Map bleibt eine zusätzliche
Ingress-Schicht, kein Ersatz für den Decorator — beide Panel-Lesepfade und
die drei genannten `/display/…`-Routen tragen künftig einen Decorator, statt
über diese Sektion als Geräte- oder Sammel-Ausnahme zu laufen.

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

**[ÜBERHOLT 2026-08-11 — Nic-Setzung, Prüfung am Live-Stand]** Die Ausklammerung
oben ist erledigt und gilt nicht mehr. Der Abriss ist durch: `router/` und
`geraete/` sind aus dem Repo gelöscht und ihre Dienste inaktiv, von `display/`
steht nur noch `display/_shared` (die Asset-Ausnahmen aus AUTH-11). Zwei der
genannten Dienste waren **nie** Abriss-Ziele und laufen weiter:

- **`panel`** — RAT-31 §2 sagt ausdrücklich „Kachel-Kuratierung … bleibt";
  nur die `display_id`-Bindung und der Router-Proxy sterben, nicht der Dienst.
- **`wetter`** — in RAT-31 nirgends genannt, ein regulärer Buddy.

`hoerspiel` fiel bereits per RAT-32-Amendment vom 2026-07-30 heraus; `familie`
ist extern per nginx-403 dicht (#1638). Damit gilt für alle verbliebenen
Dienste ohne Ausnahme **AUTH-11**: was echten Inhalt ausliefert, sitzt hinter
dem Cookie. Nic 2026-08-11: „Wenn kein Abriss mehr kommt, dann muss alles, was
wirklich Content hat, hinter dem Cookie sein."


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

**[ÜBERHOLT 2026-08-11 — Nic-Setzung, siehe AUTH-11]** Diese Liste
beschreibt weiterhin, welche Routen historisch als Public-Assets eingeordnet
wurden — für die Gate-Frage ist sie seit AUTH-11 aber nicht mehr die Quelle
der Wahrheit. AUTH-11 verlangt für jede Route in der Flask-URL-Map entweder
einen Auth-Decorator oder einen namentlichen Eintrag in AUTH-11s eigener
Ausnahme-Tabelle; eine Nennung allein hier reicht dafür nicht mehr. Konkret
tragen `/api/v1/diag`, `/api/v1/icons/suche`, die Hörspiel-Audio-Route
(`/api/v1/hoerspiel/<kind_id>/alben/<id>/audio/<track>.mp3`) und
`/api/v1/hoerspiel/<kind_id>/shared-assets/status` künftig einen Decorator —
sie stehen in keiner AUTH-11-Ausnahme-Zeile und sind damit nicht länger
AUTH-4-öffentlich. **Wo diese Liste und AUTH-11s Ausnahme-Tabelle sich für
eine Route widersprechen, sticht AUTH-11** (Nic 2026-08-11: „alle Adressen,
also wirklich alle, sind mit einem Cookie geschützt … Nur wer Cookie hat,
sieht irgendwas."). Von den übrigen Zeilen dieser Liste stehen
`/shell/<panel_id>/manifest.json`, `/shell/<panel_id>/icon-*.png` und
`/display/_shared/*` namentlich in AUTH-11s Ausnahme-Tabelle; die alten
`/display/<id>`-Router-Routen sind mit dem Router-Tod (RAT-31 E6f) bereits
entfallen. **`/display/<buddy>/*` — die Buddy-Renderer-Views selbst (zwölf
`@app.route`-Vorkommen in sieben Services plus deren sieben implizite
Static-Endpunkte) — steht in keiner AUTH-11-Ausnahme-Zeile und ist damit
offen: sie bekommen einen Auth-Decorator** (Nic-Setzung 2026-08-11,
umgesetzt in #1805 über fünf parallele Bau-Stücke). Das ist unabhängig von
AUTH-7: die dort erst mit Phase 4 scharfe nginx-Map ist eine zusätzliche
Ingress-Schicht, kein Ersatz für den Decorator — ein Bau-PR braucht beides,
nicht eines statt des anderen. Diese Liste bleibt als Entscheidungs-
Geschichte stehen, welche Routen wann als inhaltlich öffentlich eingestuft
wurden.

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
[RAT-40](../../decisions/RAT-40-auth-decorator-lib.md),
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
# audio-stream, seiten, seiten/uebersicht: Trigger 2026-08-12 gefeuert → jetzt
# gegatet (audio-stream + seiten: AUTH-3 HART via #1833/#1832; seiten/uebersicht:
# AUTH-7b DUAL via #1832) — Zeilen entfernt, #1863
# routine/{items,config} + hoerspiel/{config,alben,alben/<id>/manifest,resume,themen,folgen-vorschlag}: Phase-2/3-Trigger 2026-07-30 gefeuert → jetzt in AUTH-3 (Bau #1639/#1640)
/api/v1/seiten/mini-app-uebersicht            (Trigger: Phase 2/3)
/api/v1/panels/*                              (Trigger: Phase 4 Panel-Mini-App)
/api/v1/panels/<id>/tiles*                    (Trigger: Phase 4)
/api/v1/geraete/*                             (Trigger: Geräte-Editor-Mini-App)
# router/panels/<src>, displays/<id>/events, displays/<id>/state: Routen existieren
# in keiner URL-Map mehr (RAT-31-Router-Tod) — Zeilen entfernt, #1863
```

**Zehn ungegatete Telegram-Shell-Routen — Auth-11-Anlass (#1805).** AUTH-11
verlangt für jede ungegatete Route entweder einen Decorator oder eine
namentliche Ausnahme; für diese zehn ist **keins von beiden** angemessen,
weil `require_dual_gate` cookie-only prüft und unbelegt ist, ob der
Telegram-WebView beim HTML-Initial-Load überhaupt einen `xbuddy_session`-
Cookie mitschickt (MAD-11, `conventions/mini-app-design.md`, hält fest: der
WebView schickt beim HTML-Initial-Load keinen `Authorization`-Header — JS
prüft erst beim Mount via `ensureAuth()`/`init-data/validate`). Ein Gate auf
Verdacht risikiert, den Anmelde-Pfad selbst zu brechen — deshalb Schuldstand
statt Ausnahme, mit eigenem Auflösungs-Trigger:

```
/seiten/essen/einkauf                         (Trigger: #1859 Cookie-Probe)
/seiten/essen/einkauf/                        (Trigger: #1859 Cookie-Probe)
/seiten/plan/einstellungen                    (Trigger: #1859 Cookie-Probe)
/seiten/plan/einstellungen/                   (Trigger: #1859 Cookie-Probe)
/seiten/routine/anpassen                      (Trigger: #1859 Cookie-Probe)
/seiten/routine/anpassen/                     (Trigger: #1859 Cookie-Probe)
/seiten/wetter/regeln                         (Trigger: #1859 Cookie-Probe)
/seiten/wetter/regeln/                        (Trigger: #1859 Cookie-Probe)
/seiten/hoerspiel/<kind_id>/eltern            (Trigger: #1859 Cookie-Probe)
/api/v1/seiten/mini-app-uebersicht            (Trigger: #1859 Cookie-Probe)
```

**Trigger #1859:** Nic tippt den Telegram-Button auf einem gepairten
Elterngerät an und belegt live, ob der WebView den `xbuddy_session`-Cookie
mitschickt. Trägt er ihn, wandern alle zehn Routen mit dem Factory-Decorator
nach AUTH-3 (derselbe same-origin-Cookie-Pfad wie die übrigen
Eltern-Mini-Apps); trägt er ihn nicht, braucht es eine eigene Auth-Lösung
für den Telegram-Fall, bevor sie gaten können. Bis dahin sind sie hier
geführt, nicht in AUTH-11s Ausnahme-Tabelle — eine Ausnahme wäre eine
Entscheidung, dies ist eine offene Frage mit Verfallsdatum.

**Fünf ungegatete panel-Routen — PREG-9-Proxy ohne Identität (#1834).**
`seiten` proxyt Panel-Lesepfad und Editor-Seite mit einem nackten
`urllib.request.Request(url, method="GET")` **ohne Header** an den
panel-Service (`_proxy_panel_view` und `_proxy_panel_bearbeiten`,
`seiten/main.py`) — der Proxy-Aufrufer ist ein Python-Prozess, kein Gerät,
und trägt deshalb strukturell keinen Cookie. Der ÜBERHOLT-Marker, der die
„cookieloses Kiosk-Gerät"-Prämisse in AUTH-3/`panel-bearbeiten.md`
widerlegt, trägt hier **nicht**: er widerlegt nur die Geräte-Prämisse, nicht
den fehlenden Identitäts-Transport am Proxy-Hop selbst. Ein Gate auf den
fünf `panel`-Routen unten würde dem Proxy `401` liefern; für die
Lesepfade fängt `_proxy_panel_view` das als „Service nicht erreichbar" ab
und fällt auf den LKG-/Code-Default zurück — der Kiosk zeigte ein leeres
Panel, ohne sichtbar zu scheitern (Watchdog-Live-Reproduktion: `config.json`
und `tiles.json` antworteten `200` mit leerem Body statt `401`); für die
drei `bearbeiten*`-Routen liefert `_proxy_panel_bearbeiten` `502` (kein LKG).
Das ist wörtlich der in PBE-3 benannte #1338-Bruch, nur am Proxy-Hop statt
am Gerät.

```
/api/v1/panels/<panel_id>/config.json         (Trigger: #1854 Proxy-Abschaffung)
/api/v1/panels/<panel_id>/tiles.json          (Trigger: #1854 Proxy-Abschaffung)
/controller/app-panel/<panel_id>/bearbeiten       (Trigger: #1854 Proxy-Abschaffung)
/controller/app-panel/<panel_id>/bearbeiten.js    (Trigger: #1854 Proxy-Abschaffung)
/controller/app-panel/<panel_id>/bearbeiten.css   (Trigger: #1854 Proxy-Abschaffung)
```

**Trigger #1854:** Nic-Entscheid 2026-08-12 — der PREG-9-Proxy soll
**abgeschafft** werden („was wir nicht mehr brauchen sollte weg"),
abgesichert durch eine Berater-Runde. Der Trigger ist deshalb die
Abschaffung selbst, nicht „Proxy trägt Cookie": eine Identität am
Proxy-Hop nachzurüsten wäre eine zweite, konkurrierende Lösung für ein
Bauteil, das ohnehin wegsoll. Fällt der Proxy, laufen die fünf Routen
entweder direkt gegen den panel-Service (dann mit Factory-Decorator wie
jede AUTH-3-Route) oder der Aufruf entfällt mit dem Proxy selbst. Bis dahin
sind sie hier geführt, nicht in AUTH-11s Ausnahme-Tabelle — eine Ausnahme
wäre eine Entscheidung, dies ist eine offene Frage mit Verfallsdatum.

> **[GEÄNDERT 2026-08-17 — Nic-Verdikt zu #1854, HTML-Karte Wahl `b`/`a`]**
> Der Absatz darüber ist **überholt**. Nic hat am 2026-08-17 die Gegenrichtung
> gewählt: der Proxy-Hop **bleibt** und weist sich als **er selbst** aus
> (benannte Dienst-Naht), statt abgeschafft zu werden. Damit ist der Trigger
> nicht mehr „Proxy-Abschaffung", sondern **AUTH-12** (unten). Die am
> 2026-08-12 zur Absicherung der Abschaffung verlangte Berater-Runde entfällt
> mit der Abschaffung selbst; sie hat nie stattgefunden.
>
> **Der Umfang ist kleiner als die Liste oben suggeriert.** Live über die echte
> Origin ohne Cookie gemessen (2026-08-17): `config.json` und `tiles.json`
> antworten **`200` mit echtem Body**, die drei `bearbeiten*`-Routen
> **`401`** — nginx routet erstere direkt an `panel:5041` vorbei am Proxy
> (`deploy/nginx/xbuddy-origin.conf:382`), letztere über den gegateten
> `seiten`-Block (`:519`). Am Dienst selbst (`127.0.0.1:5041`) sind weiterhin
> **alle fünf** ungegatet: die Schuld besteht formal für fünf, extern dringend
> für zwei. Dazu ein Existenz-Orakel (unbekannte `panel_id` → `404`, bekannte
> → `200`).

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

### AUTH-11 — Rück-Verriegelung: der Code ist der Ausgangspunkt, nicht die Liste

AUTH-9 prüft in **eine** Richtung: trägt jede *gelistete* Route ihren
Decorator? Eine Route, die in keiner Liste steht, ist für AUTH-9 unsichtbar
und damit ungeprüft ungeschützt. AUTH-11 dreht die Richtung um.

**Regel.** Jede Route, die in der Flask-URL-Map eines xbuddy-Services
existiert, trägt entweder einen Auth-Decorator — oder sie steht namentlich
in der Ausnahme-Liste dieser Klausel. Eine Route mit weder noch macht den
Test rot. Die Prüfung geht vom **Code** aus (URL-Map), nicht von der Spec.

**Der Marker ist der Nachweis, nicht die bloße Existenz eines Decorators.**
Der Test prüft nicht die Decorator-*Form* (jeder `functools.wraps`-Wrapper
trägt ein `__wrapped__`-Attribut — auch ein Caching- oder Logging-Decorator;
das wäre ein mögliches Falsch-Positiv), sondern ein explizites Attribut
(`auth_gate.AUTH_MARKER`, `tools/initdata/auth_gate.py`), das die drei
Decorator-Factories (`make_require_init_data`, `make_require_soft_gate`,
`make_require_dual_gate`) am fertigen Wrapper setzen — sowie
`markiere_auth_klasse()` für Inline-Gates (AUTH-2-INLINE, unten). Was der
Marker leistet: er unterscheidet einen Auth-Decorator zuverlässig von jedem
beliebigen anderen Wrapper. Was er **nicht** leistet: er beweist nicht, dass
tatsächlich gegatet wird. Bei den drei Factories folgt das aus der Mechanik
— der Marker wird erst gesetzt, nachdem der fertige Wrapper steht, wer ihn
trägt, hat zwingend auch dessen Gate-Logik. Beim handgesetzten
`markiere_auth_klasse()` folgt das **nicht**: die Funktion setzt nur das
Attribut und gibt die View unverändert zurück, ohne sie zu umhüllen — der
Marker ist reine Deklaration, kein Gate. Deshalb braucht jede so markierte
Route eine eigene, abschließende Liste (AUTH-2-INLINE, unten) statt dem
Marker allein zu vertrauen.

**Sammel-Einträge zählen nicht.** Ein Wildcard-Eintrag wie
`/display/<buddy>/*` (AUTH-4) oder `/api/v1/panels/*` (AUTH-6) erfüllt
AUTH-11 **nicht**. Jede konkrete Route wird einzeln geführt. Begründung:
ein Sammel-Eintrag verdeckt genau die Routen, die niemand bedacht hat —
unter `/display/<buddy>/*` lag ein schreibender Endpunkt, ohne dass es
auffiel.

**Keine Geräte-Ausnahmen.** Jedes Gerät, das xbuddy konsumiert, trägt ein
`xbuddy_session`-Cookie; der Pi-Kiosk wird per `pair-kiosk.sh` gepairt
(RAT-32). „Das Gerät kann kein Cookie" ist deshalb kein zulässiger
Ausnahme-Grund.

**Vorrang vor AUTH-3 und AUTH-4.** AUTH-3 und AUTH-4 führen Routen normativ
als von der Gate-Pflicht ausgenommen bzw. als „antwortet ohne
Identitätsprüfung" — für die Gate-Frage gilt das nur noch, soweit die Route
auch in dieser Klausel namentlich ausgenommen ist. Wo AUTH-3 oder AUTH-4 und
diese Klausel für dieselbe Route unterschiedliche Antworten geben, **sticht
AUTH-11**. Eine Route, die AUTH-3 von der Gate-Pflicht ausklammert oder die
AUTH-4 als öffentlich führt, aber hier in der Ausnahme-Tabelle nicht
namentlich steht, trägt einen Decorator (siehe AUTH-3- bzw.
AUTH-4-Markierung dort für die betroffenen Zeilen).

**Zulässige Ausnahmen — abschließend.** Nur strukturelle Gründe, bei denen
das Gate das System selbst bräche. Jede Zeile trägt ihren Grund:

| Route | Grund |
|---|---|
| `/healthz` (je Service), `/version` | Die Überwachung fragt vor jeder Anmeldung. Nicht per Cookie, sondern am Ingress auf Loopback/Tailnet einschränken. |
| `/auth/pair` | Die Adresse, an der das Cookie ausgestellt wird. Hinter dem Cookie unerreichbar. |
| `/shell/<panel_id>/manifest.json` | Ohne öffentliches Manifest installiert sich keine PWA. RAT-32 führt die Manifest-Publicness als Nicht-Verhandelbares. |
| `/shell/<panel_id>/sw.js` | **[ÜBERHOLT — Code-Gegenprobe]** Keine Ausnahme (mehr): der Endpunkt trägt `@require_dual_gate(mode="hard")` (`seiten/main.py:1955`, Kommentar „sw.js bleibt gated") und ist hart gegated; `test_shell_sw_js_bleibt_gated_ohne_quelle` (`tests/test_dual_gate_7b.py:248`) verriegelt das. Die Begründung „lädt vor Session" trifft auf diese Route nicht zu — sie trifft auf die Zeile unten. |
| `/api/v1/seiten/static/connector/sw.js` | Der Browser lädt diesen Service-Worker, bevor eine Session existiert — anders als `/shell/<panel_id>/sw.js` oben (dort inzwischen gegated) ist diese Route tatsächlich ungegatet. Eigene Zeile, weil die Klausel Sammel-Einträge ausschließt — auch eine Auslassungs-Ellipse ist keiner. |
| `/shell/<panel_id>/<path:asset>` | Der WebAPK-Installer holt die Manifest-Icons **credential-los** — mit Gate schlägt die Installation fehl (#1437). |
| `/controller/_shared/<path:asset>` | Der Service-Worker legt diese Dateien im Precache ab, **bevor** ein Cookie existiert (ROU-23). |
| `/display/_shared/design/<path:asset>`, `/display/_shared/icons/<path:asset>` | 7b-Public-Ausnahme aus AUTH-7: die Views laden Design-Tokens und Icons als Asset; mit Gate bleiben sie leer. Seit dem Router-Tod von `seiten` ausgeliefert (RAT-31 E6f, #1568). |
| `/api/v1/seiten/static/<path:filename>` | Flasks impliziter Static-Endpoint (`static_url_path`, `seiten/main.py:330`) liefert das JS jeder Mini-App aus — genau das Skript, das den `tma`-Header überhaupt erst erzeugt. AUTH-4 führt den Pfad nur als Sammel-Eintrag (`/api/v1/seiten/static/*`); diese Zeile macht ihn namentlich. |
| `/api/v1/init-data/validate` | Nur per POST erreichbar. Die Adresse, an der die Identität geprüft wird (`seiten/main.py:536`). Sie validiert selbst per HMAC (AUTH-4) und kann folglich nicht hinter dem Ergebnis ihrer eigenen Prüfung liegen. |
| `/display/kibuddy/static/manifest.webmanifest` | `kibuddy/templates/frage.html:15` lädt das Manifest ohne `crossorigin="use-credentials"` — per Fetch-Spec credential-los. Gegatet bekäme ein gepairtes Gerät bei jedem Laden 401 auf sein Manifest; keine Installation (gleiche Klasse wie `/shell/<panel_id>/manifest.json`). |
| `/display/kibuddy/static/icons/icon-192.png` | Vom Manifest referenziertes Icon (`kibuddy/static/manifest.webmanifest`); der WebAPK-Installer holt Manifest-Icons **credential-los** — mit Gate schlägt die Installation fehl (gleiche Klasse wie `/shell/<panel_id>/<path:asset>`, #1437). |
| `/display/kibuddy/static/icons/icon-512.png` | Zweites vom Manifest referenziertes Icon, gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/essen/einkauf/manifest.json` | Ausgeliefert über den ungegateten `einkauf_asset_view` (`seiten/main.py:780`); Icon-Set aus `REGISTRY["einkauf"].icons` (`seiten/pwa_mantel.py:357`). Browser holt PWA-Manifeste credential-los (Fetch-Spec, dokumentiert analog `seiten/main.py:1084`) — gegatet bekäme ein gepairtes Gerät bei jedem Laden 401, keine Installation. |
| `/seiten/essen/einkauf/icon-192.png` | Vom Manifest referenziertes Icon (`REGISTRY["einkauf"].icons`, `seiten/pwa_mantel.py:357`); WebAPK-Installer holt Icons credential-los — gleiche Klasse wie `/shell/<panel_id>/<path:asset>` (#1437). |
| `/seiten/essen/einkauf/icon-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/essen/einkauf/icon-maskable-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/plan/einstellungen/manifest.json` | Ausgeliefert über den ungegateten `plan_einstellungen_asset_view` (`seiten/main.py:864`); Icon-Set aus `REGISTRY["plan"].icons` (`seiten/pwa_mantel.py:370`). Gleiche Begründung wie `/seiten/essen/einkauf/manifest.json` oben. |
| `/seiten/plan/einstellungen/icon-192.png` | Vom Manifest referenziertes Icon (`REGISTRY["plan"].icons`, `seiten/pwa_mantel.py:370`); gleiche Begründung wie `/seiten/essen/einkauf/icon-192.png` oben. |
| `/seiten/plan/einstellungen/icon-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/plan/einstellungen/icon-maskable-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/routine/anpassen/manifest.json` | Ausgeliefert über den ungegateten `routine_anpassen_asset_view` (`seiten/main.py:1118`); Icon-Set aus `REGISTRY["routine"].icons` (`seiten/pwa_mantel.py:436`). SW + Manifest sind „technisch-public … Browser-Fetch credential-los wie bei plan" (`seiten/main.py:1084`). |
| `/seiten/routine/anpassen/icon-192.png` | Vom Manifest referenziertes Icon (`REGISTRY["routine"].icons`, `seiten/pwa_mantel.py:436`); gleiche Begründung wie `/seiten/essen/einkauf/icon-192.png` oben. |
| `/seiten/routine/anpassen/icon-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/routine/anpassen/icon-maskable-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/wetter/regeln/manifest.json` | Ausgeliefert über den ungegateten `wetter_regeln_asset_view` (`seiten/main.py:1172`); Icon-Set aus `REGISTRY["wetter-regeln"].icons` (`seiten/pwa_mantel.py:455`). Gleiche Begründung wie `/seiten/essen/einkauf/manifest.json` oben. |
| `/seiten/wetter/regeln/icon-192.png` | Vom Manifest referenziertes Icon (`REGISTRY["wetter-regeln"].icons`, `seiten/pwa_mantel.py:455`); gleiche Begründung wie `/seiten/essen/einkauf/icon-192.png` oben. |
| `/seiten/wetter/regeln/icon-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/wetter/regeln/icon-maskable-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/wetter/regeln/wetter-regeln.css` | Einziges Nicht-Manifest-/Nicht-Icon-Asset, das eine der fünf Eltern-Shells über die gegatete `<path:asset>`-Route lädt (`seiten/templates/wetter-regeln.html:11`; `wetter_regeln_asset_view`, `seiten/main.py:1387`) — die anderen vier ziehen ihr CSS/JS aus dem ungegateten impliziten Static (AUTH-11-Ausnahme). Die Shell selbst steht als AUTH-6-Schuldstand offen (Trigger #1859); bliebe das Stylesheet gegatet, lüde die Fläche als unformatiertes HTML — Shell und Pflicht-Asset müssen dieselbe Auth-Antwort geben. |
| `/seiten/hoerspiel/<kind_id>/eltern/manifest.json` | Ausgeliefert über den ungegateten `hoerspiel_eltern_asset_view` (`seiten/main.py:1285`); Icon-Set aus `REGISTRY["hoerspiel-eltern"].icons` (`seiten/pwa_mantel.py:477`). „SW/manifest: credential-los" (`seiten/main.py:1204`, `:1293`). |
| `/seiten/hoerspiel/<kind_id>/eltern/icon-192.png` | Vom Manifest referenziertes Icon (`REGISTRY["hoerspiel-eltern"].icons`, `seiten/pwa_mantel.py:477`); gleiche Begründung wie `/seiten/essen/einkauf/icon-192.png` oben. |
| `/seiten/hoerspiel/<kind_id>/eltern/icon-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/seiten/hoerspiel/<kind_id>/eltern/icon-maskable-512.png` | Gleiche Begründung wie `icon-192.png` oben. |
| `/display/hoerspiel/static/manifest.webmanifest` | Seit #1858 über eine dedizierte Route ausgeliefert (`hoerspiel/main.py:534`), NICHT über den generischen (jetzt gegateten) Static-Endpoint. `hoerspiel/templates/alben.html:12` lädt das Manifest ohne `crossorigin="use-credentials"` — credential-los per Fetch-Spec, gleiche Klasse wie die `kibuddy`-Zeilen oben. Die drei PNG-Icons unter `/display/hoerspiel/static/` bleiben ungenutzt hinter dem generischen Static-Gate (kein Template/JS referenziert sie; das Manifest zeigt auf `/display/_shared/icons/arasaac/5915.png`, bereits ratifizierte Ausnahme) — sie brauchen keine eigene Zeile. |

Die Asset-Zeilen oben (Manifest, Service-Worker, Icon-/Design-Assets sowie
die beiden Bootstrap-Zeilen `/api/v1/seiten/static/<path:filename>` und
`/api/v1/init-data/validate`) sind dieselbe technische Klasse: Dateien oder
Bootstrap-Endpunkte, die ein Browser/Installer/Service-Worker **bevor** ein
Cookie existieren kann laden oder aufrufen muss. Sie tragen keine
Familiendaten. Verriegelt ist davon bereits ein Teil: `/display/_shared/*`
durch `test_display_shared_bleibt_public_ungegatet`
(`tests/test_auth_decorator_coverage.py:333`), `/shell/<panel_id>/manifest.json`
durch `test_shell_manifest_public_gibt_200_ohne_gate`
(`tests/test_dual_gate_7b.py:134`) und `/shell/<panel_id>/<path:asset>` für
den Icon-Fall durch `test_shell_icon_public_ohne_quelle_gibt_200`
(`tests/test_dual_gate_7b.py:232`) sowie
`test_shell_icon_512_public_ohne_quelle_gibt_200`
(`tests/test_dual_gate_7b.py:261`) — für diese Zeilen zeichnet die Tabelle
den ratifizierten, bereits getesteten Bestand nach. Für die übrigen Zeilen
dieser Tabelle, einschließlich der beiden zuletzt ergänzten, liegt noch kein
eigener Test vor; die Verriegelungs-Aussage gilt für sie **nicht**. Die
Test-Implementierung dafür ist Aufgabe des Bau-PRs (siehe unten).

Die Liste erweitert man **nur per Spec-Änderung**, nie im Test-Code — sonst
wandert die Ausnahme aus der Sicht heraus.

**AUTH-2-INLINE — vierte Beweisform (handgesetzter Inline-Gate).**
Auth-Decorator und die Ausnahme-Tabelle oben sind zwei Erklärungen,
AUTH-6-Schuldstand eine dritte. Eine vierte Klasse deckt Routen, die
**weder** einen Auth-Decorator tragen **noch** öffentlich sind: der Gate
liegt handgeschrieben im Funktionskörper selbst, ohne geteilten Decorator —
weil es bei n=1 keinen Konsumenten gibt, der einen geteilten Decorator
rechtfertigt (AUTH-2 oben, #1292). Ohne eigene, abschließende, namentliche
Liste wäre so eine Route für AUTH-11 unsichtbar erklärt, obwohl sie nie
geprüft wurde — genau die Lücke, die AUTH-11 schließen soll, an neuer
Stelle wieder offen.

**Abschließende Liste — heute genau zwei, beide AUTH-2 (#1292):**

```
/seiten/hoerspiel/player
/seiten/hoerspiel/player/<path:asset>
```

Der Hörspiel-Player ist eine live benutzte Browser-PWA ohne tma-Pfad; der
Cookie-Gate liegt inline in `hoerspiel_player_view` / `hoerspiel_player_asset_view`
(`seiten/main.py`) statt hinter einem geteilten Decorator, weil er bei n=1
keinen rechtfertigte. Eine **dritte** Inline-Route kostet einen gereviewten
Spec-PR wie jede Ausnahme — der Code allein trägt sie nicht automatisch in
diese Liste ein, das ist ihr ganzer Zweck. Die Nennung hier ersetzt auch
keinen Gate: der eigentliche Beleg sind die Verhaltenstests
(`test_html_kein_cookie_gibt_401`, `test_manifest_kein_cookie_gibt_401`,
`test_sw_kein_cookie_gibt_401`, `seiten/tests/test_hoerspiel_player.py:58,71,77`),
die 401 ohne Cookie tatsächlich beobachten — nicht die Namensnennung.

**Messbasis ist die URL-Map, nicht der Quelltext.** Der Test liest
`app.url_map`, nicht die `@route`-Dekorationen. Beides deckt sich nicht:
Flasks implizite `static`-Endpunkte und Catch-all-Auslieferer stehen in der
URL-Map, ohne als Dekoration sichtbar zu sein. Wer nur den Quelltext zählt,
übersieht sie — genau die Klasse Lücke, die AUTH-11 schließen soll.

**Begründung.** Am 2026-08-11 waren 66 von 131 Routen ohne Decorator, davon
vier schreibend; erreichbar war unter anderem das Profil eines Kindes und
ein unauthentifizierter Rebuild-Trigger. Keine dieser Routen war „falsch
klassifiziert" — sie waren nirgends klassifiziert. AUTH-9 konnte das
konstruktionsbedingt nicht sehen.

Die Test-Implementierung ist Aufgabe des Bau-PRs; die Klausel ist
Verhaltens-Spec.

*Tickets:* #1805

### AUTH-12 — Benannte Dienst-Naht: der vermittelnde Dienst weist sich als er selbst aus

> **Nic-Verdikt 2026-08-17 (#1854, HTML-Karte).** Wörtlich: „Der vermittelnde
> Dienst weist sich als er selbst aus, nicht als der Nutzer." Ersetzt den
> AUTH-6-Trigger „Proxy-Abschaffung" für die fünf `panel`-Routen.

Ruft ein xbuddy-Dienst im Auftrag eines angemeldeten Elternteils einen anderen
xbuddy-Dienst, trägt der Aufruf eine **Dienst-Identität** — nicht die
weitergereichte Nutzer-Anmeldung. Die aufgerufene Route akzeptiert damit zwei
Zugangs-Klassen: die Nutzer-Anmeldung (AUTH-3) **oder** eine gültige
Dienst-Identität. Begrifflich ist das dieselbe Trennung, die AUTH-5 schon
benennt („Backend-Prozess-Identität … nicht User-Identität") — AUTH-12 macht
sie **transportierbar**, statt sie aus der Quell-Adresse zu erraten.

**Die Quell-Adresse ist als Nachweis untauglich, und das ist der Kern dieser
Klausel.** nginx reicht `/api/v1/panels/` **direkt** an `panel:5041` weiter
(`deploy/nginx/xbuddy-origin.conf:382`), ohne Herkunfts-Kennzeichnung. Der
Dienst sieht externen Verkehr dort mit einer Loopback-Quelle — **ununterscheidbar
von einem echten Backend-Aufruf**. Wer diese Routen mit einem
AUTH-5-Loopback-Bypass „absichert", öffnet sie damit für jeden von außen. Das
ist derselbe Fehler wie „`curl` auf `127.0.0.1` ist grün, also ist die Route
sicher": der Weg Browser → nginx → Dienst ist **nie** Loopback im Sinne von
AUTH-5, auch wenn er so aussieht.

Daraus folgen drei Anforderungen an den Nachweis:

1. **Er wird im Aufruf mitgeführt**, nicht aus der Verbindung abgeleitet.
2. **Er ist von außen nicht setzbar** — ein Aufruf, der ihn mitbringt, ohne aus
   einem xbuddy-Dienst zu stammen, wird abgewiesen. Ein Nachweis, den ein
   Browser selbst anhängen kann, ist keiner.
3. **Er benennt den aufrufenden Dienst**, damit im Protokoll steht, *wer*
   gerufen hat. Ein anonymer „ist intern"-Schalter erfüllt AUTH-12 nicht.

**Nicht Teil dieser Klausel** ist die konkrete Bauform (geteiltes Geheimnis,
signierter Kurzzeit-Nachweis, eigener Loopback-Kanal, den nginx nicht erreicht).
Sie wird im Bau entschieden und dort begründet; AUTH-12 legt nur fest, was der
Nachweis leisten muss.

**Verhältnis zu RAT-32.** RAT-32 („alles, was Inhalt hat, hinter dem Cookie")
bleibt unberührt: AUTH-12 macht keine Route öffentlich, sondern ergänzt eine
zweite, ebenfalls geprüfte Zugangs-Klasse für Dienst-zu-Dienst-Verkehr. RAT-32
nimmt AUTH-5-Loopback ausdrücklich aus — AUTH-12 ist dessen fälschungssichere
Fassung für Wege, die über nginx erreichbar sind.

*Tickets:* #1854

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
