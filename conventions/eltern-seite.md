# Eltern-Seite — Baseline-Konvention (ESB)

Ratifiziert 2026-07-31 (Nic „jede Seite ist PWA und öffentlich geschützt durch
Cookie und jede Seite kann im Eltern-Chat erfragt werden … Substanz schaffen").
Zweck: **eine einheitliche Linie** für alle eltern-facing Seiten, gegen den
Wildwuchs (Audit 2026-07-31). Diese Konvention **erfindet nichts** — sie ist eine
**Klammer**, die vier schon ratifizierte Eigenschaften zu einer verbindlichen
Checkliste pro Eltern-Seite bündelt. Sie referenziert die Quell-Konventionen,
dupliziert sie nicht.

**Geltung:** jede eltern-facing Seite/View (`zielgruppe: eltern`). NICHT für
Kind-/Kiosk-Ansichten (Kind-Tablet-Vollbild, Display-Renderer) — die sind die
Gegen-Sorte (siehe ESB-4).

Der `xbuddy-architecture-watchdog` prüft jede neue/geänderte Eltern-Seite gegen
ESB-1..4.

## ESB-1 — Jede Eltern-Seite ist ein PWA-Mantel

Eine Eltern-Seite ist ein installierbarer PWAM-Mantel: Registry-Eintrag in
`seiten/pwa_mantel.py` (PWAM-1), Manifest (PWAM-2) + geteiltes `sw.js` (PWAM-3) +
`build_id`-Cache-Buster-Route (PWAM-4), **registriert statt geforkt** (PWAM-5).
Referenz: `conventions/pwa-mantel.md` PWAM-1..6. „Nur `build_id_source_set`
ohne manifest/sw" ist **kein** Mantel und verletzt ESB-1.

## ESB-2 — Die Datenrouten einer Eltern-Seite sind Cookie-hart (AUTH-3)

Die `/api/v1/<buddy>/*`-Datenrouten, die eine Eltern-Seite liest/schreibt, stehen
verbindlich in der **AUTH-3-Liste** und tragen den HART-Decorator (Cookie ODER
`tma`, 401 ohne). Referenz: `specs/platform/auth.md` AUTH-3 (+ AUTH-3.a Soft→Hard-
Leiter). Das HTML-Skelett darf AUTH-6-public bleiben (MAD-7: `ensureAuth()` im
JS) — die Härtung sitzt auf den Datenrouten, nicht der Shell. ESB-2 macht die
bisher **fallweise** Wanderung einer Route in AUTH-3 zur **Regel**: neue
Eltern-Seite ⇒ ihre Datenrouten gehören in AUTH-3.

## ESB-3 — Jede Eltern-Seite ist im Eltern-Chat erfragbar

Eine Eltern-Seite trägt einen `views.json`-Eintrag mit `zielgruppe: eltern`,
damit der Aggregator sie in die SREG-12-Übersichtsseite zieht und der
`seiten_uebersicht`-Skill (SREG-5) sie surfacen kann. Referenz:
`specs/platform/seiten-registry.md` SREG-4/5/12. Der Chat verweist auf die
**Übersichtsseite**, macht **kein** Pro-Panel-Matching (PBE-2-Pivot bleibt).

**Heimat-Sub-Regel (killt den Wildwuchs):** die eltern-Seite eines Buddys wohnt
in **`<buddy>/views.json`** (nicht zentral in `seiten/views.json`), mit **einem**
`typ` pro Seite. Doppel-Einträge mit divergentem `typ` (Audit-Befund einkauf)
und Fremd-Heimat (plan in seiten statt plan) sind verboten.

## ESB-4 — Nicht-Kinder-Ansichten sind scrollbar

Jede Eltern-Ansicht ist vertikal **scrollbar** (Nic-Setzung: „alle nicht Kinder
views sind scrollbar"). Der Gegenpol ist **PANEL-12** (`conventions/app-panel.md`
/ `controller/app-panel/style.css` `overflow:hidden`) — das gilt **nur** für die
Kiosk-/Kind-Vollbild-Sorte (feste Größe). Wo dieselbe Komponente in beiden Sorten
läuft (app-panel als Kiosk **und** als Eltern-Übersicht), MUSS die Scroll-Regel
nach Sorte getrennt sein: Kiosk fest (PANEL-12), Eltern-Viewport scrollbar. Eine
Eltern-Seite mit `overflow:hidden` verletzt ESB-4.

## Abgrenzung / Ledger

Additive Klammer, keine Re-Litigation: PWAM-1..6, AUTH-3, SREG-4/5/12, PANEL-12
und der MAD-7-Public-HTML-/SREG-5-Pivot bleiben unverändert gültig — ESB
referenziert sie nur gebündelt. Bau/Umsetzung: das Eltern-Seiten-Baseline-Epic
(#1665 ESB-PWA / #1661 ESB-CHAT / #1662 ESB-SCROLL + Manifest-Heimat + hoerspiel-
eltern als Kinder).
