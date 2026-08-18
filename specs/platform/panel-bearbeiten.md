# Panel bearbeiten — Spec     (ID-Präfix: PBE)

Die **eltern-seitige Settings-Seite**, mit der Eltern die Kacheln **einer
Panel-Instanz** verschieben, ausblenden, entfernen und hinzufügen — die
Home-Screen-Settings-Metapher vom Handy. Der Eltern-Chat liefert auf Nachfrage
einen **Link** auf die System-Übersichtsseite (SREG-12) — kein mehrstufiger
Chat-Dialog. (Wie die Editor-Karte dort erscheint, ist seit RAT-31 E3 offen:
der frühere Weg „je Panel eine Karte an seinem gepaarten Display" ist abgerissen,
siehe den Vermerk an PBE-2.) Folgt dem Muster RAT-2/#328
(Garderoben-Editor): der **Daten-Eigentümer-Service** (hier der panel-Service,
:5041) liefert seine eigene Editor-Seite, die **zeigt UND editiert**; Auth = der
same-origin-Cookie der seiten-Shell (PBE-3 — die frühere Formulierung
„Heimnetz/Tailscale-Grenze" ist mit der Nic-Setzung vom 2026-07-31 ersetzt).

Diese Fähigkeit löst **OPEN-PREG-A** (`panel-registry.md`) auf — den dort
vorgesehenen „späteren Tile-Schreiber". Sie ändert ausschließlich `tiles`, nie
`config` (PREG-5, E-PANEL-3).

**Datenmodell-Erdung (Bestand):** Eine Panel-Instanz trägt `tiles` getrennt von
`config` mit getrennten Schreibrechten (PREG-3, PREG-5). Eine Kachel hat
`key`/`app`/`view`/`query?`/`label`/`icons[]`/`sichtbar` (PANEL-3); `key` ist
stabil und identifiziert eine Kachel über Listenpositionen hinweg. Die
Listen-Reihenfolge in `tiles.json` **ist** die Anzeige-Reihenfolge (PANEL-3).

---

## 1. Editor-Seite & Auslieferung

### PBE-1 — Eine Editor-Seite je Panel-Instanz
Der panel-Service liefert je Panel-Instanz eine Editor-Seite aus. Die Seite
zeigt die Kacheln **dieser** Instanz in ihrer aktuellen `tiles.json`-Reihenfolge
und erlaubt das Bearbeiten (PBE-5..7). Die Seite ist an die `panel_id` gebunden
(PREG-3) — sie editiert nie eine andere Instanz.

**Mobil-hochkant + Geräte-Safe-Area:** Die Seite ist eine eltern-seitige
Mobil-Oberfläche (kein Kiosk-View), Scrollen erlaubt. Sie respektiert die
**Geräte-Safe-Area oben** (iPhone-Notch-/Lautsprecher-tote-Zone): der Kopf liegt
unterhalb von `env(safe-area-inset-top)` (Seite mit `viewport-fit=cover`,
Inhalts-Padding `max(<basis>, env(safe-area-inset-top))`), damit Titel/Aktionen
nie unter dem Notch verschwinden. *Eigentest:* bei gesetztem
`safe-area-inset-top` beginnt der Seitenkopf unterhalb der Inset-Höhe.

*Wenn* die Seite für `panel_id` X aufgerufen wird, *dann* lädt sie die Kacheln
aus der `tiles`-Sicht genau dieser Instanz (PREG-14) und zeigt sie in
Listen-Reihenfolge.

### PBE-2 — Deterministische Editor-URL je Panel-Instanz, auffindbar über #347

> **[TEILWEISE ÜBERHOLT 2026-07-27 durch RAT-31 E3 (#1496)]**
> Der **Auffind-Weg** dieser Klausel existiert nicht mehr. Was unten über die
> Seiten-Registry, die Sorte-d-Einträge und die Hero-Sektion „Geräte-Paare"
> steht, ist abgerissen:
>
> - `specs/platform/seiten-registry.md` **SREG-11**: „Panel-Editor-Einträge
>   existieren nicht mehr"; **SREG-12**: „~~Editor-Eintrag je Panel (d/e)~~ —
>   entfernt RAT-31 E3".
> - Im Code ist `hero_paare` immer `[]` (`seiten/render.py`), festgenagelt in
>   zwei Tests.
> - „**neben dem gepaarten Display**" ist zusätzlich gegenstandslos: RAT-31 §2
>   listet die Panel-zu-Display-Bindung unter *stirbt*. Es gibt kein Paar mehr.
>
> **Was gültig bleibt:** die deterministische URL selbst
> (`/controller/app-panel/<panel_id>/bearbeiten`) — der Editor lebt und ist
> erreichbar, er ist nur nicht mehr auffindbar. Und der Satz „der Chat macht
> **kein** Pro-Panel-Matching": den bestätigt ESB-3
> (`conventions/eltern-seite.md`, RAT-42 vom 2026-07-31, also **nach** RAT-31).
>
> **Warum dieser Vermerk hier steht:** `seiten-registry.md` hält bereits fest,
> dass dieser Konsumenten-Pfad nicht mehr relevant ist — aber PBE-2 selbst wusste
> nichts davon. Am 2026-08-18 hat ein Bau-Track (#1906) genau deshalb eine
> abgerissene Sektion gebaut bekommen sollen; die Reifung hatte korrekt
> „ledger: sauber" gemeldet, weil der Rückzug als **Spec-Text** lebt und nicht
> als Entscheid-Klausel. Ein Grep über `decisions/` findet ihn strukturell nicht.
>
> **Der Ersatz-Weg** (Editor-Karte in der Buddy-Gruppe `app-panel`, ohne
> Hero-Sektion) ist offen — siehe #1906 und SREG-12 Layout Punkt 3.

Die Editor-Seite (PBE-1) wird unter einer **deterministisch aus der `panel_id`
abgeleiteten URL** ausgeliefert: `/controller/app-panel/<panel_id>/bearbeiten`
(Sub-Pfad der Panel-Display-URL `/controller/app-panel/<panel_id>`, PANEL-2;
vom Router zum panel-Service proxyt). Die URL ist stabil und direkt aufrufbar.

Sie ist über die System-weite Seiten-Registry (#347, SREG) auffindbar, **je
Panel-Instanz ein eigener Editor-Link**. Der Weg zum Link für Eltern: der
Eltern-Chat-Skill `seiten_uebersicht` (SREG-5, Pivot 2026-06-07) liefert auf
Nachfrage einen Link zur Übersichtsseite (SREG-12); dort steht je Panel-
Instanz eine Editor-Karte **direkt neben dem gepaarten Display in der
Hero-Sektion „Geräte-Paare"** (SREG-12-Layout), mit Copy-Button für die volle
Editor-URL (Heimnetz/Tailscale). Der Chat selbst macht **kein** Pro-Panel-
Matching mehr — die Pro-Panel-Auflösung passiert auf der Übersichtsseite
(Volltextsuche gegen `label`/`synonyme`), nicht im Chat.

*Wenn* eine Familie mehrere Panel-Instanzen hat (PREG-2), *dann* hat **jede**
Instanz ihre eigene, aus ihrer `panel_id` abgeleitete Editor-URL, und die
Registry führt **je Instanz** (Sorte d) deren Editor-URL als auffindbaren Eintrag.

> **Registry-seitige Anforderung in #387 (hart, hart verlinkt):** Dass die
> Seiten-Registry den per-Panel-Editor-Link aus dem Panel-Snapshot (Sorte d)
> ableitet und ausliefert, ist als **hartes Requirement** im Ticket #387
> spezifiziert (gemeinsame seiten-registry-/Manifest-Erweiterung, die #330
> konsumiert). #330 und #387 werden **in einer Session zusammen** gebaut.

### PBE-3 — Auth = same-origin-Cookie der seiten-Shell (AUTH-3)
Der Schreib-Endpunkt (PBE-4) ist über den **same-origin-Cookie-Pfad der
seiten-Shell** gesichert — dieselbe AUTH-2/AUTH-3-Cookie-Grenze, in die der
RAT-31-Ein-Gerät-Modus den Panel-Editor re-homed hat. `PUT /api/v1/panels/<panel_id>/tiles`
steht in der **AUTH-3-Liste** (`specs/platform/auth.md` → panel Schreib-Endpunkt)
und trägt den Factory-Auth-Decorator wie jeder AUTH-3-Buddy; fehlende/ungültige
Identität → `401`. (Nic-Setzung 2026-07-31, #1400 → „a": die alte reine
Heimnetz/Tailscale-Grenze und die tote #1389-„7b-Dual-Gate"-Prämisse sind ersetzt;
Kanal/Netz allein ist **nicht** mehr das Gate für den Write.)

Der **Lesepfad bleibt außerhalb AUTH-3**: die Display-Render-/Registry-Reads
(`GET /api/v1/panels/<panel_id>/tiles`, `.../config.json`, PREG-9-Proxy) werden
**nicht** cookie-gegatet — das Panel-Display ist ein cookieloses Kiosk-Gerät; ein
app-seitiges Gaten würde den Display-Fetch erschlagen (belegter #1338-Bruch). Ihre
Funnel-Exposition bleibt die separate AUTH-7-Frage.

**[ÜBERHOLT 2026-08-11 — Nic-Setzung, Prüfung am Live-Stand]** Die
Cookielos-Prämisse oben gilt nicht mehr. `specs/platform/auth.md` AUTH-11
(2026-08-11, #1805) schließt Geräte-Ausnahmen ausdrücklich aus: „Jedes
Gerät, das xbuddy konsumiert, trägt ein `xbuddy_session`-Cookie; der
Pi-Kiosk wird per `pair-kiosk.sh` gepairt (RAT-32). 'Das Gerät kann kein
Cookie' ist deshalb kein zulässiger Ausnahme-Grund." Der Live-Stand
bestätigt das für genau dieses Gerät: `/shell/<panel_id>` — die Heim-Shell,
die Hauptfläche desselben Kiosk-Geräts — trägt den Dual-Gate, und `seiten`
läuft mit `XBUDDY_AUTH_MODE=hard`
(`/etc/systemd/system/xbuddy-seiten.service.d/40-auth-mode.conf`); ein
Gerät ohne gültigen Cookie bekäme dort `401`, die Anzeige läuft aber. Das
Gerät trägt also einen gültigen Cookie — „cookieloses Kiosk-Gerät"
beschreibt den Stand vor der RAT-32-Pairing-Mechanik, nicht den heutigen.
Bei Widerspruch zwischen diesem Absatz und AUTH-11 sticht AUTH-11 (dort die
konkrete Ausnahme-Tabelle, in der diese Lesepfade nicht stehen). Der Absatz
oben bleibt als Entscheidungs-Geschichte stehen: er erklärt, warum die
Lese-Endpunkte am 2026-07-31 (#1400) bewusst ausgeklammert wurden.

---

## 2. Schreib-Endpunkt

### PBE-4 — `PUT /api/v1/panels/<panel_id>/tiles`
Der panel-Service nimmt unter `PUT /api/v1/panels/<panel_id>/tiles` die
vollständige, neue `tiles`-Liste der Instanz entgegen und schreibt sie.

- **Explizites Speichern, ein PUT der vollen Liste** (Design-Reconcile, Gate B):
  die Seite sammelt Verschieben/Ausblenden/Entfernen/Hinzufügen **lokal** und
  schreibt sie als **eine** vollständige `tiles`-Liste beim Tippen auf
  **Speichern** (ein atomarer Schreibvorgang, ein Reload — PBE-10). **Verwerfen**
  verwirft die lokalen Änderungen **ohne** Schreibvorgang. Kein Auto-Save je
  Einzelaktion (kein Flackern, kein PUT-Sturm).
- **Nur `tiles`, nie `config`** (PREG-5, E-PANEL-3): der Endpunkt berührt das
  `config`-Feld der Instanz nicht.
- **Atomar** (DCOMP-4: Temp-Datei + `os.replace`): ein zeitgleicher Lesezugriff
  (PREG-9-Proxy, Display-Render) sieht nie eine halb geschriebene Liste. Der
  Display übernimmt den neuen Stand per reload-on-read (DCOMP-2) **plus** das
  aktive Reload-Signal (PBE-10).
- **Last-Write-Wins** (Nic 2026-06-07): kein Versions-/ETag-Token. Zwei
  zeitgleiche Schreiber → der spätere gewinnt, atomar. (Realistisch für eine
  Familie; optimistic concurrency wäre Vorbau.)
- **Validierung vor Schreiben** (PBE-11): ungültige Liste → **422** mit
  Begründung, `tiles.json` **byte-unverändert**. Kein Schreibziel/Instanz
  unbekannt → **404**. Schreibfehler am Dateisystem → **500** mit JSON-Fehler
  (Geist von GER-6/DCOMP-4).
- **Auth: same-origin-Cookie hart (AUTH-3, PBE-3)** — der Schreib-Endpunkt trägt
  den Factory-Auth-Decorator der seiten-Shell (`make_require_dual_gate(mode="hard")`,
  #1625-Factory, #1400) und steht in der **AUTH-3-Liste** (`auth.md` → panel
  Schreib-Endpunkt, via #1731) wie jeder AUTH-3-Buddy. Gültiger Session-Cookie
  (gekoppeltes Gerät, dieselbe AUTH-2/AUTH-3-Cookie-Grenze) → `200` **+ Rolling-
  Refresh**; fehlende/ungültige Identität → **`401`** (kein Schreibvorgang). Der
  Bot-Token (Cookie-Signatur-Key) kommt per-Instanz aus `ELTERNCHAT_BOT_TOKEN`
  (systemd-Drop-In). **Kanal/Netz allein ist nicht das Gate** (Nic-Setzung „a"
  2026-07-31, #1400 → „a": die tote #1389-„7b-Dual-Gate"/funnel-Erreichbarkeits-
  Prämisse ist ersetzt). Nur der Schreib-Endpunkt ist gegated; die Lese-
  `tiles.json`/`config.json` bleiben **außerhalb AUTH-3** (cookieloses Kiosk-
  Display, PBE-3 — **[ÜBERHOLT 2026-08-11 — Nic-Setzung, siehe PBE-3-Absatz
  unten]**: das Gerät trägt seit RAT-32 einen gültigen Cookie, AUTH-11
  schließt Geräte-Ausnahmen aus) — ihre Funnel-Exposition ist die separate
  AUTH-7-Frage.

*Wenn* der Endpunkt eine gültige `tiles`-Liste für eine existierende Instanz
erhält, *dann* liegt nach der Antwort `200` der neue Stand atomar in der
`tiles.json` genau dieser Instanz und das Reload-Signal (PBE-10) ist gesendet.

---

## 3. Bearbeiten-Operationen

### PBE-5 — Verschieben (Reihenfolge)
Die Seite erlaubt das Umordnen der Kacheln. Die gespeicherte
Listen-Reihenfolge **ist** die Anzeige-Reihenfolge im Panel (PANEL-3). Das
Verschieben ändert nur die Reihenfolge, nicht Inhalt oder `key` einer Kachel.

### PBE-6 — Ausblenden und Entfernen (zwei getrennte Aktionen, Nic 2026-06-07)
Die Seite bietet je Kachel **zwei** Aktionen:
- **Ausblenden/Einblenden** — setzt das `sichtbar`-Flag (PANEL-4) auf
  `false`/`true`. Die Kachel bleibt in `tiles.json`, wird im Panel aber nicht
  gerendert. **Reversibel.**
- **Entfernen** — löscht den Kachel-Eintrag **hart** aus `tiles.json`. Nicht
  reversibel (Wiederherstellen = neu hinzufügen, PBE-7).

*Wenn* eine Kachel ausgeblendet wird, *dann* bleibt ihr Eintrag (inkl. `key`,
`sichtbar:false`) erhalten; *wenn* sie entfernt wird, *dann* verschwindet ihr
Eintrag vollständig.

### PBE-7 — Hinzufügen aus der Seiten-Registry
Die Seite erlaubt das Hinzufügen einer Kachel aus einer Auswahl-Liste. Quelle
der Auswahl ist `GET /api/v1/seiten` (#347), **gefiltert auf Display-Views
(Sorte a)** — die einzige Sorte, die ein Panel-Tile targeten kann (PANEL-7
Descriptor `{app, view}`).

- **Varianten als eigene Listeneinträge** (Nic 2026-06-07): eine View mit
  endlichen Varianten (z. B. „Wochenplan" + „Wochenplan Kleinkind",
  SREG-1/`varianten[]`) erscheint als **getrennte, direkt wählbare** Einträge,
  je mit eigenem `icons[]`.
- **`icons[]` aus dem Manifest-Icon-Contract (#387):** die hinzugefügte Kachel
  übernimmt `icons[]` (und ggf. die Varianten-`icons[]`) aus dem
  Registry-Eintrag — **keine** Icon-Wahl/-Ableitung in dieser Seite. Das ist
  der interface-first-Konsum des in #387 ratifizierten Contracts.
- **`query` als flaches Objekt** (PANEL-7): die hinzugefügte Varianten-Kachel
  übernimmt `query` als Objekt aus dem Registry-Eintrag (#387 normalisiert das
  Manifest auf Objekt-Form).
- **`key` wird beim Hinzufügen vergeben** — stabil und eindeutig innerhalb der
  `tiles.json` (PANEL-3), z. B. aus `app` + laufendem Index.
- **`sichtbar: true`** für neu hinzugefügte Kacheln.

*Wenn* Eltern einen Listeneintrag hinzufügen, *dann* entsteht eine
PANEL-3-gültige Kachel (`key`/`app`/`view`/`query?`/`label`/`icons[]`/`sichtbar`)
am Ende der Liste, deren Anzeige-Felder unverändert aus dem Registry-Eintrag
stammen.

> **Sequenz-Abhängigkeit:** PBE-7 (Hinzufügen) konsumiert den #387-Icon-Contract.
> Bis #387 die `icons[]` in die Registry-Einträge bringt, ist der Add-Flow nicht
> vollständig baubar. **Verschieben/Ausblenden/Entfernen (PBE-5/6) hängen NICHT
> an #387** — sie operieren auf bestehenden Kacheln. Der Track-Schnitt (F4) darf
> das nutzen.

### PBE-8 — Die Aus-Kachel ist nicht editierbar
Die „Aus-Kachel" (PANEL-6) wird von der Panel-Seite zur Laufzeit eingefügt und
ist **kein** `tiles.json`-Eintrag. Der Editor zeigt sie **nicht** als
editierbare Kachel an und kann sie nicht verschieben/ausblenden/entfernen.

### PBE-9 — Leerer Zustand erlaubt
Eltern dürfen alle Kacheln entfernen/ausblenden. Eine leere bzw. vollständig
ausgeblendete `tiles.json` ist gültig — die Panel-Seite rendert dann nur die
eingefügte Aus-Kachel (PANEL-6: auch bei leerer `tiles.json` letzte Position).

---

## 4. Live-Reload

### PBE-10 — Display übernimmt die Änderung ohne manuellen Reload
Nach einem erfolgreichen Schreibvorgang (PBE-4) übernimmt das laufende Panel am
Display die neue Kachel-Liste **ohne manuellen Seiten-Reload**, über den
**bestehenden Display-Event-Stream** (SSE, `GET /api/v1/displays/<display_id>/events`,
heute in `controller/app-panel/app.js`).

- Ein neues Stream-Ereignis signalisiert „Kacheln geändert" für die betroffene
  `display_id` (die Instanz kennt ihr `display_id`, PREG-3). Das Panel re-holt
  daraufhin `tiles.json` und rendert das Gitter neu (`loadTiles` + Re-Render),
  ohne Vollreload.
- **Schranke (testbar):** das Display zeigt die Änderung **binnen 5 Sekunden**
  nach der `200`-Antwort des Schreibvorgangs.
- **Ausfall-Toleranz:** bricht der Stream, fällt das Panel auf reload-on-read
  (DCOMP-2) beim nächsten ohnehin stattfindenden Laden zurück — kein Crash, die
  Änderung ist nicht verloren (sie liegt persistent in `tiles.json`).

*Wenn* der Schreibvorgang `200` liefert und der Stream der `display_id` aktiv
ist, *dann* zeigt das Panel die geänderte Kachel-Liste binnen 5 s.

**Mechanik des Stream-Ereignisses (verbindlich):** Nach einem erfolgreichen
Tile-Schreibvorgang (PBE-4) sendet der Panel-Editor an den Router
`POST /api/v1/router/admin/panels/<display_id>/tiles-changed` (leerer Body).
Der Router-Endpoint ruft daraufhin in seinem Prozess `publish(display_id, …)`
(`router/main.py`) auf, was das Stream-Ereignis an alle SSE-Abonnenten dieses
Displays verteilt. Begründung der Lego-Wahl: das Panel hat keinen eigenen
SSE-Kanal — Displays abonnieren beim Router (ROU-22). Der Router ist die
einzige Stream-Naht. Das Signal „Tiles geändert" entsteht am Panel-Editor (er
schreibt `tiles.json`), die SSE-Veröffentlichung gehört zum Router. Der mit
T446 gebaute Sender (`panel/main.py`) bleibt; der bisher fehlende
Empfänger-Endpoint wird im Router gebaut — ersetzt das verworfene #448
(`router/admin/tiles-changed`-Sackgasse ohne `publish`-Aufruf). Ein
Beobachtungs-Pfad „Router watcht `panels.json`-Snapshot" ist bewusst verworfen
(neuer Watcher-Mechanismus ohne bestehende Naht; CLAUDE.md §6 — keine Vorrats-
Mechanik).

---

## 5. Validierung & Tests

### PBE-11 — Validierung der geschriebenen Liste
Vor dem Schreiben (PBE-4) prüft der Service die `tiles`-Liste gegen PANEL-3:
jeder Eintrag hat die Pflichtfelder (`key`/`app`/`view`/`label`/`icons[]`/`sichtbar`),
`key` ist eindeutig innerhalb der Liste, `icons[]` hat ≥1 und ≤3 Pfade relativ
zu `/display/_shared/icons/` (PANEL-3/ICONS-5), `query` — falls vorhanden — ist
ein **flaches Objekt** (PANEL-7, `_validate_query_flat`). Verletzung → 422, Datei
unverändert (PBE-4).

### PBE-12 — Tests
Die Fähigkeit ist abgedeckt durch Tests für: Reorder erhält `key`s (PBE-5);
Ausblenden vs. Entfernen (PBE-6); Add erzeugt PANEL-3-gültige Kachel inkl.
Varianten-`query`-Objekt (PBE-7/11); Aus-Kachel nicht editierbar (PBE-8); leerer
Zustand gültig (PBE-9); 422 lässt `tiles.json` byte-unverändert (PBE-4/11);
404 bei unbekannter Instanz (PBE-4). Der Reload-Pfad (PBE-10) wird gegen ein
injizierbares Stream-/Zeit-Double getestet, nicht gegen Wall-Clock.

---

## Offene Punkte

- **OPEN-PBE-B — Add-Liste-Übersichtlichkeit / Kategorisierung.** Wird die
  Add-Auswahl (PBE-7) bei wachsender View-Zahl unübersichtlich, ist eine
  Kategorisierung zu erwägen — derselbe `OPEN-SREG-Kategorie`-Punkt aus #387.
  Heute (≤ ~6 Views) flach ausreichend; nicht auf Vorrat bauen.
