# Mini-App-Übersicht — Spec     (ID-Präfix: MAU)

> Status: V1 · Refs #678 (Werft-Sammler, Funktion 3 „Übersicht"), RAT-16,
> `conventions/mini-app-design.md` (MAD-1..10 ratifiziert 2026-06-15 / #708-Folge),
> SREG-12 (Vorgänger-View im Browser), SREG-14 (Mini-App-Sorte im Manifest), #708
> (Auth-Header — wird in dieser V1 mitgehärtet)

Die Mini-App-Übersicht ist die **Telegram-Mini-App-Variante** der Eltern-
Übersicht: ein WebView, der vom Familien-Bot per `web_app`-Inline-Button
geöffnet wird und das vollständige Inventar (Mini-Apps + Buddy-Seiten)
als Kachel-Liste rendert. (Geräte-Paare-Sektion entfernt RAT-31 E3 #1496.) Tap auf eine Buddy-Seiten-Karte
öffnet die URL im System-Browser des Handys (`WebApp.openLink`); Tap auf
eine Mini-App-Karte startet die Ziel-Mini-App im selben WebView-Overlay.

**Vorgänger-View `SREG-12`** bleibt unverändert als **Tablet-Browser-Pfad**
für den Einrichtungs-Use-Case (Direkt-Zugriff am Pi-Tablet, kein Telegram
vorausgesetzt). Beide Views ziehen aus derselben Aggregator-Wahrheit
(`baue_inventar` in `seiten/aggregator.py`) — keine Doppel-Wahrheit, keine
Doppel-Pflege.

**Klassen-Einordnung:** Mini-App-Konsument **#4** nach essen-einkauf (#653,
n=1), routine-anpassen (#728, n=2 → MAD-Ratifizierungs-Trigger) und
Hörspiel-Eltern-Mini-App (#848, n=3, n=1 für Tabs). Folgt der ratifizierten
**MAD-Konvention** (`conventions/mini-app-design.md`).

## MAU-1 — Mini-App-Übersicht ist eine Telegram-Mini-App

Die View lebt unter `/api/v1/seiten/mini-app-uebersicht` (analog SREG-12 als
HTML-Schwester-Pfad zur Registry, URL-4-Konsistenz) im seiten-Service. Sie
trägt das Mini-App-Form-Faktor (MAD-1..7): `platform.js`-Wrapper, DTOK-
Tokens + MAD-Skalierungs-Parameter, MAD-2-Card-Liste-Layout, MAD-7
Auth via `initData`-Header.

*Test (Live):* `curl -H "Authorization: tma <gültige-initData>"
https://buddyboard.<tailscale-id>.ts.net/api/v1/seiten/mini-app-uebersicht`
antwortet 200 + HTML. Ohne Header → 401.

## MAU-2 — Inventar-Quelle ist der Aggregator (keine Doppel-Liste)

Die Mini-App-Übersicht ruft `GET /api/v1/seiten` (SREG-1 Inventar) und
rendert das Ergebnis client-seitig. Sie hält **keine** eigene Mini-App-
Liste im Code. Mini-Apps tauchen im Inventar auf, weil die Buddies
(essen, routine, seiten) sie in ihren `views.json` als `typ: "mini-app"`
deklarieren (SREG-14).

*Test (Code):* `grep -nE 'essen-einkauf|routine-anpassen' seiten/templates/
mini-app-uebersicht.html seiten/static/mini-app-uebersicht.js` = 0 Treffer
(keine hardcoded Mini-App-Liste).

## MAU-3 — Auth: initData-Header von Anfang an (#708 mitgehärtet)

V1 erzwingt `Authorization: tma <initData>` an der Mini-App-Übersicht-
Route selbst UND an `GET /api/v1/seiten` (Inventar-API). Validierung über
die existierende Lib `eltern-chat/init_data.py` (HMAC-SHA256, Bot-Token
via `EnvironmentFile=__XBUDDY_DATA__/eltern-chat/.env`, MAD-9
Token-Sharing). Ohne / ungültiger initData → 401, kein HTML-Render.

**Synchron-Härtung:** Mit dem Implementierungs-Track wandern
`essen-einkauf` und `routine-anpassen` gleichzeitig auf V1.x — alle drei
Mini-Apps lesen `initData` von der JS-Property und senden sie als Header
(MAD-7 V1.x). Damit schließt diese Werft #708.

*Test (Unit):* mock initData → 200; abgelaufenes initData → 401;
fehlender Header → 401.

## MAU-4 — Layout: zwei Accordion-Sektionen, default geschlossen

> **RAT-31 E3 (#1496):** Die ursprüngliche Sektion 2 „Geräte-Paare"
> (`typ: display-client` + `verknuepft_mit_panels`, Hero-Box-Pattern)
> wurde entfernt. Der Code (`rendereGeraetePaare`, `_hero_paare`) ist
> weg; seiten-registry.md SREG-12 dokumentiert den Rückbau.

Die Mini-App-Übersicht rendert zwei `<details>`-Accordion-Sektionen
**von oben nach unten**, **alle initial collapsed** (Gate-B-Wahl
2026-06-15: „erst alles eingeklappt und ich klappe dann aus für die
Details"):

1. **📱 Mini Telegram Apps** — `typ: "mini-app"` aus dem Inventar.
   Karten mit Icon + Label + Kurzbeschreibung + **„▶︎ Öffnen"**-Tap-
   Affordanz. Tap → öffnet die Ziel-Mini-App (siehe MAU-5).
2. **📄 Buddy-Seiten** — read-only Eltern-Views, gruppiert nach `app`-
   Slug (Buddy-Gruppen analog SREG-12). URL-Karten tragen **„🔗 Öffnen"**
   und **„📋 Kopieren"** (siehe MAU-6); **kein** direkter Tap-Wechsel
   (Buddy-Seiten sind keine Mini-Apps).

**Accordion-Mechanik:** `<details>` ohne `open`-Attribut. Tap auf
`<summary>` toggelt. Chevron-Indikator rotiert beim Öffnen. Standard-
Browser-Verhalten, kein JavaScript-Toggle nötig.

**Sortierung innerhalb Sektionen:**
- Mini-Apps: Manifest-Discovery-Reihenfolge (analog Sorten a/b/c im
  Aggregator).
- Buddy-Seiten: Buddy-Gruppen nach Karten-Anzahl absteigend, dann
  alphabetisch (analog SREG-12).

**MAD-1 Skalierungs-Parameter:** `--item-scale` zentral, Card-Maße per
`calc()` abgeleitet. **MAD-2 Item-Card:** Bild · Text · Aktion.

## MAU-5 — Mini-App-zu-Mini-App-Navigation

Tap auf eine Mini-App-Karte → die Ziel-Mini-App ersetzt den WebView-
Inhalt. **Mechanik V1:**

- **Default-Pfad:** Tap löst `WebApp.openTelegramLink(t_me_url)` aus
  (`web_app_url` aus Manifest), Telegram wechselt im selben Overlay.
- **Fallback:** Wenn der Direkt-Wechsel scheitert,
  `window.location.href = funnel_url` (Komposition aus Funnel-Domain
  + Mini-App-Pfad).

**Out-of-Scope V1:** sauberer `platform.openMiniApp()`-Wrapper. Wenn V1
zeigt, dass `t_me`-Direktlink-Wechsel stabil funktioniert, zieht MAD-10
als Konvention nach (Ratifizierungs-Berater-Runde, nicht in dieser
Werft).

*Test (Live):* von Mini-App-Übersicht in `routine-anpassen` wechseln,
Telegram-Back-Geste zurück zur Übersicht, weiter zu `essen-einkauf`.

## MAU-6 — URL-Karten: 🔗 Öffnen + 📋 Kopieren (Setup-Hilfe)

> **RAT-31 E3 (#1496):** Gilt nur noch für Buddy-Seiten. Die ursprüngliche
> Geräte-Paare-Anwendung (Hero-Box mit Display + Panel-Karten) ist entfernt.

Karten mit URL (Buddy-Seiten) bieten zwei Buttons. Tap
auf die Karte selbst löst **keine** Default-Aktion aus — der Eltern
wählt bewusst Öffnen oder Kopieren:

- **🔗 Öffnen** → `WebApp.openLink(url, {tryBrowser: 'chrome'})`.
  Öffnet den System-Browser am Eltern-Handy. URL ist dort in der
  Adresszeile sichtbar — Eltern kann sie weiterleiten an das Pi-Tablet
  (Chrome-Sync, AirDrop, Browser-Verlauf am Tablet eingeben).
  **Garantiert verfügbar** (Telegram-Mini-App-API offiziell).
- **📋 Kopieren** → Best-Effort `document.execCommand('copy')` mit
  unsichtbarer `<textarea>`. Bei Erfolg: Toast „Link kopiert". Bei
  Fehler: Toast „Kopieren ging nicht — öffne im Browser" + automatischer
  Fallback auf `openLink`. **Nicht garantiert** in Telegram-Mini-App
  (`navigator.clipboard.writeText` ist mit `NotAllowedError` gesperrt;
  `execCommand` ist deprecated aber praktisch häufig erfolgreich).

**Kein `<a href="...">`-Tag** für die URL-Anzeige selbst (Long-Press-
Browser-Menü ist in Telegram-WebView plattformabhängig und unzuverlässig,
siehe `reference_telegram_mini_app_clipboard.md`). URL als Mono-Text
gerendert, Buttons übernehmen die Geste.

## MAU-7 — Visuelle Heimat: fest hell (kein Theme-Override)

Die Mini-App-Übersicht rendert mit **festem hellem Hintergrund**
(`#f4f5f7`) und festem Text-Kontrast — sie **bindet NICHT** an die
Telegram-Theme-CSS-Variablen (`--tg-theme-bg-color` etc.). Begründung
Gate B 2026-06-15: Setup-Hilfe-Tauglichkeit (URL-Karten lesbar, Toast
sichtbar) und Konsistenz mit der SREG-12-Tablet-Browser-Schwester sind
wichtiger als Telegram-Dark-Mode-Spiegelung. Eltern erleben die
Übersicht in beiden Heimaten (Telegram-Mini-App + Tablet-Browser) als
optisch identisch.

**Verhältnis zu MAD:** Die ratifizierte MAD-Konvention
(`conventions/mini-app-design.md`) regelt Theme-Andocken **nicht
explizit** als Pflicht — sie verlangt nur, dass Mini-Apps keine eigenen
Farb-/Maß-Werte erfinden, sondern DTOK-Tokens nutzen (`conventions/
design-tokens.md`). MAU folgt der DTOK-Andock-Disziplin (siehe MAD-
Datei-Header), nutzt aber feste DTOK-Werte statt Telegram-Theme-
Variablen. Keine Konvention wird verletzt; die Abweichung ist
dokumentiert und View-spezifisch begründet.

## MAU-8 — Lade-Verhalten + Fehler-Modi

- **Inventar-Load:** `fetch('/api/v1/seiten', {headers: {Authorization:
  'tma ' + Telegram.WebApp.initData}})`. Wartet auf Antwort, dann
  Render.
- **Loading-State:** Skeleton-Card-Sektion (drei leere geschlossene
  Accordions als Platzhalter), damit der WebView nicht weiß-flackert.
- **Fehler 401:** „Bitte App neu öffnen — Auth abgelaufen" + Button
  „Schließen" (`WebApp.close()`).
- **Fehler 5xx / Netz:** „Inventar nicht erreichbar." + Retry-Button.
- **Snapshot-Pending:** wenn Inventar-Antwort `snapshot_pending: [...]`
  enthält, Banner „Geräte/Panels werden gerade nachgeladen" (analog
  SREG-12 `banner-snapshot`).

## MAU-9 — Familie-3-Probe

Was variiert je Familie:
- Bot-Token, Bot-Username (Mini-App-URL `t.me/<bot>/<app_short_name>`).
- Funnel-Domain (`*.<tailscale-id>.ts.net` ist familienspezifisch).
- Familien-Display-/Panel-/Mini-App-Bestand.

Alles Konfig, kein Code. Mini-App-Übersicht ist familien-agnostisch.

Aus `familie.json` (FAM-Spec) wird die Familien-Bot-URL gezogen
(Familien-Buddy-Konvention). Funnel-Domain aus seiten-Konfig (analog
n=1/n=2).

## MAU-10 — Skill `seiten_uebersicht` wird `web_app`-Launcher

Der Eltern-Chat-Skill `eltern-chat/skills/seiten_uebersicht.py` wird auf
das `einkauf_zeigen` / `routine_anpassen_oeffnen`-Stil-Anker umgebaut:
statt eines Text-Links liefert er eine kompakte Bot-Nachricht („Hier
ist die Übersicht aller Seiten und Apps:") + `web_app`-Inline-Button
**„🏠 xbuddy öffnen"** mit der Mini-App-Übersicht-URL als
`web_app_url`. Detail siehe SREG-5 Pivot (`seiten-registry.md`).

**MAU-10 App-Bezeichnungen (EC-40 Achse B):** Mini-Apps · App-Übersicht
· alle Apps · Übersicht · Seiten.

**MAU-10 EC-40-Familien-Trigger.** Zusätzlich zu den heute via Bot-Menü-
Pfad selten formulierten Direkt-Anfragen feuert MAU bei jeder Kombination
aus dem Aktions-Vokabular EC-40 Achse A und einer MAU-Bezeichnung aus
Achse B — Beispiele: „zeig mir alle Mini-Apps", „App-Übersicht öffnen",
„welche Apps gibt es?", „Seiten zeigen", „Übersicht öffnen". Das LLM
formuliert in keinem Fall einen Mini-App-Knopf als Markdown-Text in
seiner Antwort (EC-41 — der Knopf entsteht über den Tool-Call, nicht
in Prosa).

---

## E-MAU-1 — Verworfene Architektur-Alternativen

- **(β) `klasse`-Feld statt neuer `typ`-Wert SREG-14:** verworfen
  (Nic 2026-06-15), weil zwei Achsen für eine Form-Wahl. Mini-App ist
  strukturell anderer Form-Faktor (initData-Pflicht, web_app-Launcher),
  eigener `typ` rechtfertigt sich. Render-Schicht filtert sauberer.
- **V1 ohne initData (wie n=1/n=2):** verworfen (Nic 2026-06-15), weil
  #708 als MVP-Block hochgestuft 2026-06-12 — Tailscale Funnel macht
  den Pi öffentlich. Mini-App-Übersicht V1.x härtet die zwei Vorgänger-
  Mini-Apps gleich mit, statt #708 als nachgelagerte separate Aufgabe
  zu führen.
- **SREG-12 ablösen:** verworfen, weil Pi-Tablet kein Telegram → der
  Setup-Pfad „URL direkt am Tablet anklicken" geht nur über
  Browser-View. SREG-12 bleibt parallel.
- **Eigene Mini-App-Liste im MAU-Code hardcoden:** verworfen, weil
  n=2-Lego-Bruch (Wartung divergiert sofort, sobald der 3. Buddy eine
  Mini-App baut). Schema-Erweiterung SREG-14 ist der Lego-Bau.
- **Tap-direkt auf URL-Karten als Default-Aktion:** verworfen
  (Gate B 2026-06-15), weil URL-Karten zwei strukturell verschiedene
  Aktionen tragen (Öffnen vs. Kopieren). Karte-als-Ganzes-Tap würde
  eine Aktion bevorzugen und die andere verstecken. Zwei explizite
  Buttons sind klarer.
- **Telegram-Theme-Bindung (`--tg-theme-*` an DTOK-Variablen):** verworfen
  für MAU (Gate B 2026-06-15) — siehe MAU-7. Setup-Tauglichkeit +
  Konsistenz zu SREG-12 sind wichtiger als Dark-Mode-Spiegelung. MAD
  verlangt das nicht — DTOK-Werte sind die Andockstelle, Theme-Variablen
  sind nur eine mögliche Quelle.

## Refs

- `seiten/aggregator.py:98-122` (`discover_manifests` — Lego-Anmelde-
  Mechanik).
- `seiten/templates/uebersicht.html` (SREG-12 V2 — Vorlage Layout,
  Hero-Box-Pattern).
- `seiten/templates/{essen-einkauf,routine-anpassen}.html` (Mini-App-
  Vorbilder).
- `seiten/static/platform.js` (MAD-5 Wrapper — wird um `openLink`/
  `copyText` erweitert).
- `eltern-chat/init_data.py` (HMAC-Validierung — wird produktiv
  genutzt).
- `eltern-chat/skills/{einkauf_zeigen,routine_anpassen_oeffnen}.py`
  (Skill-Vorbilder für SREG-5-Pivot).
- `conventions/mini-app-design.md` (MAD-1..10, ratifiziert 2026-06-15).
- `conventions/design-tokens.md` (DTOK — Andockstelle).
- #708 (Mini-App-Auth — wird mit dieser Werft geschlossen).
- #684 (Lego-Basis — CLOSED, MAD-5 platform.js).
- #653 (essen-einkauf — CLOSED, n=1).
- #728 (routine-anpassen — CLOSED, n=2, MAD-Ratifizierungs-Trigger).
- #848 (Hörspiel-Eltern-Mini-App — CLOSED, n=3).
