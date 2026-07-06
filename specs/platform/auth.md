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
weise hinzu (Reihenfolge im RAT-18 petrankert).

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

  **Rolling-Refresh (Auffrischung über die PWA):** jede AUTH-3-Route mit valider
  Cookie-Quelle setzt den Cookie mit frischem 90-Tage-`exp` neu (`Set-Cookie` auf
  der Antwort). Damit rollt **jeder PWA-Start** den Cookie vor; aktiv genutzte
  Geräte laufen faktisch nie ab. Bei fehlendem/abgelaufenem Cookie greift die
  AUTH-8-Re-Pair-Seite (401). **Persistenz-Validierung im echten Betrieb — kein
  Vor-Gate (Nic-Setzung 2026-07-06):** die iOS-Persistenz wird an einer **bereits
  installierten Live-PWA** (Hörspiel-Player, auf Familien-iOS+Android in täglicher
  Nutzung) beobachtet, **nicht** in einem vorgeschalteten 8-Tage-Labortest. Der
  Rolling-Refresh (jeder App-Start rollt vor) + die AUTH-8-Seite fangen einen
  etwaigen ITP-Drop ab; fällt der Cookie in echter Nutzung wiederholt, ist das das
  Signal für einen Re-Pair-Nudge (AUTH-8 V2, `tg://`-Deep-Link). Gebaut wird ohne
  Wartezeit, getestet wird durch Benutzen.
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
gegen den Bot-State (Token via Bot-Skill aus GAA-3.8 generiert), setzt bei
Erfolg den Cookie `xbuddy_session` und redirected den Browser auf die in
der Pairing-Anfrage hinterlegte Ziel-URL (`/display/<id>` für Display-
Verwendung, Mini-App-Start-URL für Controller-Verwendung).

Bei ungültigem oder abgelaufenem Token antwortet der Endpoint `400` mit
einer Anweisung, einen neuen Pairing-Link im Bot anzufordern.

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

Die **method-explizite** Endliste (GET/POST/PATCH/DELETE je Pfad) enumeriert der
**#1321-Bau** gegen die realen Routen; der AUTH-9-Copetrage-Test
(`tests/test_auth_decorator_copetrage.py`) verifiziert, dass **jede** gelistete
Route den Auth-Decorator trägt. Die `/display/…`-Renderer-Routen
(`/display/photo/rahmen`, `/display/kibuddy/frage`, `/display/plan/woche`) bleiben
**außerhalb** AUTH-3 — ihre Funnel-Exposition ist die separate AUTH-7-Frage
(Phase 4, V1 nicht ratifiziert). `/healthz` (SVC-6) bleibt unauthentifiziert.

**Bau-Gate:** der Rollout wartet auf das Cookie-iPhone-Persistenz-Gate (AUTH-2).
#1292 (Player-Cookie/401) wird NICHT vorgezogen (Phasen-Reihenfolge unten).

Jede Zeile ist eine eindeutige Flask-Route mit konkretem URL-Pfad und HTTP-
Methode — keine Sammel-Zeilen mehr (eine Zeile pro tatsächlich registrierter
Route, sonst kann der AUTH-9-Test den Decorator-Anwendungs-Stand nicht
eindeutig prüfen).

Weitere Routen kommen mit jeder Power-Flow-Migration (Phase 2: routine,
Phase 3: hörspiel-eltern). Bis dahin sind sie in AUTH-6 dokumentiert.

**#1321-Endliste (method-explizit, photo/kibuddy/plan).** Der #1321-Bau
enumeriert die oben klassifizierten Routen byte-gleich gegen die realen
`@app.route`-Strings; der AUTH-9-Copetrage-Test parst diesen Fence mit:

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

**Mechanik:** Der Loopback-Bypass lebt **im jeweiligen Buddy-Decorator**
(`essen/main.py`, `routine/main.py`, …), nicht in einer geteilten Lib —
heute kopiert je Buddy. AUTH-9 prüft, dass jede AUTH-3-Route den Decorator
trägt; eine Konsistenz-Prüfung des Loopback-Bypass-Verhaltens (alle Buddys
verhalten sich gleich) ist Aufgabe einer geteilten Helper-Lib
(`eltern-chat/init_data.py` als Heimat-Kandidat), deren Auslagerung erst
beim n=3-Verbrauch (Codex-Kriterium aus `conventions/README.md`)
ratifiziert wird. **Phase 1** kopiert das Verhalten je Buddy-Decorator
konsistent; **n=3-Trigger** (z. B. `routine/main.py` + `hoerspiel/main.py`
folgen) löst die Lib-Auslagerung aus.

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
/api/v1/routine/items                         (Trigger: Phase 2 routine-anpassen-PWA)
/api/v1/routine/config                        (Trigger: Phase 2)
/api/v1/hoerspiel/<kind_id>/config            (Trigger: Phase 3 hörspiel-eltern-PWA)
/api/v1/hoerspiel/<kind_id>/alben             (Trigger: Phase 3)
/api/v1/hoerspiel/<kind_id>/alben/<id>/manifest  (Trigger: Phase 3)
/api/v1/hoerspiel/<kind_id>/resume            (Trigger: Phase 3)
/api/v1/hoerspiel/<kind_id>/themen            (Trigger: Phase 3)
/api/v1/hoerspiel/<kind_id>/folgen-vorschlag  (Trigger: Phase 3)
/api/v1/hoerspiel/<kind_id>/play-extern       (Trigger: Phase 4 HSP-Audio-Routing — HSP-42)
/api/v1/hoerspiel/<kind_id>/audio-stream      (Trigger: Phase 4 HSP-Audio-Routing — HSP-42, SSE-Push an Panel-PWA)
/api/v1/seiten                                (Trigger: Phase 2/3, mini-app-uebersicht-Migration)
/api/v1/seiten/uebersicht                     (Trigger: Phase 2/3)
/api/v1/seiten/mini-app-uebersicht            (Trigger: Phase 2/3)
/api/v1/familie/personen*                     (Trigger: Familien-Personen-Editor-Mini-App)
/api/v1/familie/foto/*                        (Trigger: Familien-Foto-Mini-App)
/api/v1/panels/*                              (Trigger: Phase 4 Panel-Mini-App)
/api/v1/panels/<id>/tiles*                    (Trigger: Phase 4)
/api/v1/geraete/*                             (Trigger: Geräte-Editor-Mini-App)
/api/v1/router/panels/<src>                   (Trigger: Phase 4 Display-Renderer)
/api/v1/displays/<id>/events                  (Trigger: Phase 4)
/api/v1/displays/<id>/state                   (Trigger: Phase 4)
```

Phase 6 (vollständige Migration) löst AUTH-6 auf. Solange Einträge in
AUTH-6 stehen, ist MAD-7 in `conventions/mini-app-design.md` mit dem
Auslaufens-Hinweis aktiv.

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Nic-Verdikte 2026-06-16"
→ E3 AUTH-6-Backlog als „dokumentierter Schuldstand" mit Pflicht-Defer-Tag]

*Tickets:* #948

### AUTH-7 — Display-Renderer (Phase-4-Vorbereitung, NICHT V1)

> **Hinweis:** AUTH-7 ist V1 nicht ratifiziert. Die Klausel steht hier als
> Vorbereitung für Phase 4 (Kind-Tablet + Pi-Display) und gewinnt
> Bindewirkung erst, wenn der entsprechende Phase-4-Track läuft.

**Skizze:** Display-Renderer-Routen (`/display/<display_id>` und `/api/v1/displays/<id>/events`)
sind LAN/Tailnet-only — nginx prüft Quell-IP gegen `192.168.0.0/16`,
`10.0.0.0/8`, `100.64.0.0/10` (Tailnet). Funnel-Anfragen (Host
`*.ts.net`) auf Display-Routen → `403`. Die nginx-Konfiguration trägt
zwei Ausnahmen vor dem Renderer-Match: `^~ /display/_shared/`
(Mini-App-Icons) und `^~ /display/<buddy>/` (Buddy-Views) — beide bleiben
öffentlich über Funnel.

Für Phase 4 wird AUTH-7 in eine Voll-Klausel ausgebaut. Bis dahin: Display-
Renderer-Routen sind in AUTH-6 als PUBLIC dokumentiert.

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „R2-Patches"
→ Patch B nginx-Map mit Buddy-Asset-Ausnahmen]

*Tickets:* #948

## 4. Auth-Verlust-Behandlung

### AUTH-8 — 401 rendert Anweisungsseite, nicht rohen Fehler

Antwortet eine AUTH-3-Route mit `401`, rendert das Backend eine HTML-Seite
mit Anweisung an den User, nicht einen rohen Status-Code. Die Seite enthält
mindestens:

- Geräte-Name (aus `geraete.json`, falls die Quell-URL eine `display_id`
  trägt; sonst neutraler Hinweis).
- Anweisung: „Dieses Gerät muss neu verbunden werden. Öffne im Familien-
  Bot den Befehl `/gerät_neu_pairen <display_id>` und folge dem Link auf
  diesem Gerät."

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

Ein Test (`tests/test_auth_decorator_copetrage.py`) parst die AUTH-3-Liste
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

## Offene Fragen

(Keine offenen Punkte in V1 — alle Klauseln haben Paket-Quelle im ENTSCHEID-
File. Phase-4-AUTH-7-Details werden bei Trigger eigene Berater-Runde.)
