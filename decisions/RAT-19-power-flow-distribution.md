# RAT-19 — Power-Flow-Distribution: PWA-Default (Variante B)

- **Entschieden:** 2026-06-16 (Nic-Verdikt „Variante B"), **ratifiziert** 2026-06-16
  (Berater-Runde „Distributions-Form für Power-Flows", zwei Runden + Codex-Pass),
  **gekoppelt** mit dem Auth-ENTSCHEID 2026-06-16 (→ RAT-18, Cookie-Auth-Standard).
- **Scope-Hinweis (Staging):** Dieser Record hält die **ratifizierte strategische
  Setzung**. Die **formale Konventions-Festschreibung** (`conventions/pwa.md` um
  einen Power-Flow-PWA-Typ erweitern) ist laut Entscheid selbst auf **Phase 6 / n=2**
  vertagt („RAT-19 ratifizieren wenn n=2 PWA-Power-Flows stehen"). Bis dahin ist die
  Setzung bindend, das Convention-Pattern aber noch nicht generalisiert.
- **Reversibilität:** strategischer Pivot, pro Flow schrittweise + reversibel
  (Mini-App soft-stirbt, wird nicht hart abgeschaltet).
- **Anlass:** Welche Distributions-Form für Power-Flows (einkaufsliste,
  routine-anpassen, hörspiel-eltern)? Mini-App vs. PWA vs. Hybrid — der
  Bring!-Benchmark (1-Tap-Home-Icon) ist aus der Telegram-Mini-App nicht erreichbar.
- **Betrifft:** `seiten/static/einkauf/` (`manifest.json` + `sw.js`),
  `platform.js` (`authHeaders()` einführen, `BrowserPlatform.ensureAuth` auf
  Cookie-Pfad), `conventions/pwa.md` (Power-Flow-PWA-Typ — **vertagt** auf n=2);
  gekoppelt an RAT-18 (Auth-Standard); #949 (PWA-Phase-1, blocked).
- **Transkript (Evidenz):**
  `brainstorm/berater-runde/2026-06-16-1245-RATIFIZIERT-power-flow-distribution.md`
  → Vorschlag-R1 `20260616-123133-vorschlag-power-flow-distribution.md`,
  Antiberater `2026-06-16-1232-antiberater-power-flow-distribution.md`,
  Vorschlag-R2 `20260616-r2-vorschlag-power-flow-distribution.md`.

## Beschluss

**Variante B:** PWA wird **Default für Power-Flows** (Flows mit Bring!-Druck,
einkaufsliste primär); die Mini-App wird **NICHT gehärtet** und bleibt public, bis
sie pro Flow migriert ist. Eine HTML/JS-Codebasis, **zwei Distributions-Pfade** über
die `getPlatform()`-Adapter-Naht (Pro-Flow-Hybrid). Schrittweiser Rollout, startend
bei essen-einkauf; nach Bewährung Rest nachziehen.

**Pflicht-Reihenfolge:** Auth-Phase-1 (Cookie-Lib + GAA-Pairing-Schritt +
AUTH-3-Liste essen-einkauf) MUSS **vor** PWA-Phase-1 stehen.

**Phasen:**
1. essen-einkauf-PWA (MAD-5-Cleanup `platform.authHeaders()`, `manifest.json`+`sw.js`,
   Cookie-`ensureAuth`, Bot postet zusätzlich `url`-Button; 5-Tage-Realtest iPhone +
   Android, beide Install-Pfade Funnel-FQDN UND lokal-CA gleichrangig messen).
2. routine-anpassen-PWA. 3. hörspiel-eltern-PWA. 4. Panels + Display-Renderer.
5. RAT-19 als **Konvention** ratifizieren, wenn n=2 PWA-Power-Flows stehen.
6. `conventions/pwa.md` um Power-Flow-PWA-Typ erweitern, wenn das Pattern sich
   gefestigt hat.

## Verträglichkeit

RAT-16 (Telegram-MVP) bleibt gültig — Telegram bleibt Bot-Plattform; die
Mini-App-Distribution wird durch die Power-Flow-PWA **ergänzt, nicht ersetzt**.
Vendor-Adapter-Disziplin (`platform.js`-Wrapper, MAD-5) bleibt bindend.

---

## Nachtrag 2026-07-01 — der Landeplatz ist reversiert (→ RAT-52)

Dieser Record vertagte die **Konventions-Festschreibung** auf n=2 und legte
dabei auch schon den Ort fest: `conventions/pwa.md` um einen
Power-Flow-PWA-Typ erweitern.

Der Trigger trat bei **n=4** ein (#1215). Die Runde dazu hat die
Ortsfestlegung **bewusst und sichtbar reversiert**: der Mantel bekam eine
**eigene** Datei `conventions/pwa-mantel.md` (PWAM-1..6), `conventions/pwa.md`
bleibt die Kiosk-/Geräte-Sorte. Nic überstimmte dabei zusätzlich den
Berater-Lean „zwei getrennte Sorten" zugunsten einer zentralen Bibliothek, die
die Drift **entfernt** statt sie zu dokumentieren.

Die strategische Setzung dieses Records (PWA als Default für Power-Flows,
Auth-Phase vor PWA-Phase, schrittweiser Rollout) bleibt unberührt. Nur der
Satz „landet als Typ in `conventions/pwa.md`" gilt nicht mehr.

**Siehe:** [RAT-52](RAT-52-pwa-mantel-unify.md).
