/**
 * invariants.js — Tier-A-Invarianten + Tier-B-Kollisionsvertrag fuer das
 * Render-Gate (RAT-24, #1160).
 *
 * Zwei Sorten Checks:
 *
 *  1. Browser-Kontext-Checks (DOM/Geometrie): als SELBST-ENTHALTENE Funktionen
 *     geschrieben, die per `page.evaluate()` in die Seite serialisiert werden.
 *     Sie duerfen KEINE Modul-Symbole referenzieren (Closure geht beim
 *     Serialisieren verloren) — alle Helfer leben deshalb INNERHALB der Funktion.
 *
 *  2. Node-Kontext-Checks (Konsole/Requests): ueber puppeteer-Events
 *     (`console`, `pageerror`, `requestfailed`, `response`), via wireEvents().
 *
 * Befund-Form (ueberall identisch, deterministisch sortierbar):
 *   { typ, selektor, detail, messwert }
 * - typ:      kurzer Maschinen-Schluessel (z. B. "viewport-overflow")
 * - selektor: CSS-aehnlicher Pfad zum Element ODER "-" (Konsole/Seite)
 * - detail:   menschlicher Kontext (URL, Text, Paar-Notiz …)
 * - messwert: der gemessene Zahlen-/Status-Wert als String (nie nackt im Text)
 *
 * Sprache: Deutsch. Keine volatilen Werte (Timing, Zaehler) in Befunde —
 * sonst brechen die "3 Laeufe identisch"-Kill-Kriterien.
 */

"use strict";

// ─────────────────────────────────────────────────────────────────────────────
// Node-seitige Event-Verdrahtung (Tier-A: Konsole + Requests)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Haengt die Tier-A-Event-Sammler an die Page. Befunde landen im
 * zurueckgegebenen Array `findings` (wird vom Aufrufer ausgewertet).
 *
 * Gesammelt wird:
 *  - console.error  → typ "konsolen-fehler"
 *  - pageerror      → typ "seiten-fehler"  (uncaught exception/rejection)
 *  - requestfailed  → typ "request-fehler"
 *  - response >=400 → typ "request-fehler"
 *
 * Volatile Felder (Timing) werden bewusst NICHT aufgenommen.
 */
export function wireEvents(page) {
  const findings = [];

  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    // Chromium emittiert fuer JEDEN fehlgeschlagenen Subresource ein generisches
    // "Failed to load resource: ... <status>" — das ist ein redundantes Echo des
    // Netzwerk-Fehlers, den die response/requestfailed-Handler bereits MIT der
    // echten URL fassen. Nicht doppelt zaehlen (sonst URL-loser Rausch-Befund).
    if (/^Failed to load resource/i.test(text)) return;
    findings.push({
      typ: "konsolen-fehler",
      selektor: "-",
      detail: oneLine(text),
      messwert: "console.error",
    });
  });

  page.on("pageerror", (err) => {
    findings.push({
      typ: "seiten-fehler",
      selektor: "-",
      detail: oneLine(String(err && err.message ? err.message : err)),
      messwert: "pageerror",
    });
  });

  page.on("requestfailed", (req) => {
    if (isBrowserAutoRequest(req.url())) return;
    const f = req.failure();
    findings.push({
      typ: "request-fehler",
      selektor: "-",
      detail: oneLine(req.url()),
      messwert: "requestfailed:" + (f && f.errorText ? f.errorText : "unbekannt"),
    });
  });

  page.on("response", (resp) => {
    const status = resp.status();
    if (status < 400) return;
    if (isBrowserAutoRequest(resp.url())) return;
    findings.push({
      typ: "request-fehler",
      selektor: "-",
      detail: oneLine(resp.url()),
      messwert: "status:" + status,
    });
  });

  return findings;
}

/**
 * Browser-Auto-Requests, die KEIN View-Asset sind: /favicon.ico fragt Chromium
 * selbsttaetig an, auch wenn die Seite kein <link rel="icon"> deklariert. Diese
 * Anfrage feuert asynchron NACH dem load-Event — ihr Eintreffen vor page.close()
 * ist zeitlich nicht deterministisch. Bewusst ausgeschlossen (RAT-24: Befund auf
 * Assets, die die VIEW referenziert). Echte 404 auf deklarierte Assets bleiben.
 */
function isBrowserAutoRequest(url) {
  try {
    return new URL(url).pathname === "/favicon.ico";
  } catch {
    return /\/favicon\.ico(\?|$)/.test(url);
  }
}

function oneLine(s) {
  return String(s).replace(/\s+/g, " ").trim().slice(0, 300);
}

// ─────────────────────────────────────────────────────────────────────────────
// Browser-Kontext: Rect-Signatur fuer den Default-Wait (zwei stabile Snapshots)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Selbst-enthaltene Browser-Funktion: liefert eine gerundete Signatur aller
 * Element-Bounding-Boxen als String. Zwei identische Signaturen kurz
 * hintereinander = Frame gilt als "fertig" (gegen halb-hydrierte Frames).
 */
export function rectSignatureFn() {
  const els = document.querySelectorAll("*");
  const parts = [];
  for (const el of els) {
    const r = el.getBoundingClientRect();
    parts.push(
      Math.round(r.left) + "," + Math.round(r.top) + "," +
      Math.round(r.width) + "," + Math.round(r.height)
    );
  }
  return parts.join("|");
}

// ─────────────────────────────────────────────────────────────────────────────
// Browser-Kontext: Tier-A DOM-/Geometrie-Invarianten
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Selbst-enthaltene Browser-Funktion. Gibt ein Array von Befunden zurueck.
 * Argumente:
 *   `viewport` = { width, height }
 *   `opts`     = { checkUnderfill: boolean }  (optional, default: kein underfill)
 *
 * Geprueft (datenunabhaengig):
 *  - broken-img:        sichtbares <img> mit naturalWidth===0
 *  - viewport-overflow: sichtbares Element ragt rechts/unten ueber den Viewport
 *  - root-overflow:     scrollWidth/Height > clientWidth/Height am Wurzel/Body
 *  - null-groesse:      sichtbares Content-Element (img / Text-Blatt) mit Breite
 *                       ODER Hoehe 0
 *  - text-clipping:     Text-Knoten mit ellipsis/overflow:hidden, scrollWidth >
 *                       clientWidth
 *  - underfill:         Body-Bounding-Box deutlich KLEINER als Viewport
 *                       (Leerband/Letterbox, DC-18-Vertragsbruch).
 *                       Nur bei responsiven Views (opts.checkUnderfill === true,
 *                       DC-18). Fixe Views (Letterbox DC-12/DC-15) erhalten
 *                       keinen underfill-Befund.
 *                       Toleranz 5 % je Dimension. Scroll-Container-Inhalt
 *                       (z. B. .liste-eintraege overflow-y:auto) zaehlt nicht
 *                       ein — geprueft wird der Body-Rect, nicht tiefere Kinder.
 *
 * Sichtbarkeits-Filter (Pflicht, RAT-24): [hidden], display:none,
 * visibility:hidden/collapse, <script>, <template>, SVG <defs> (und deren
 * Nachfahren) zaehlen als legitim unsichtbar und erzeugen KEINEN Befund.
 * KIBuddys hidden-Startzustaende fallen damit heraus.
 */
export function domInvariantsFn(viewport, opts) {
  const W = viewport.width;
  const H = viewport.height;
  const EPS = 1.0; // px-Toleranz gegen Sub-Pixel-/Border-Rundung
  const findings = [];

  // ── kurzer, deterministischer CSS-Pfad zum Element ─────────────────────────
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "-";
    const segs = [];
    let node = el;
    let depth = 0;
    while (node && node.nodeType === 1 && depth < 5) {
      let seg = node.tagName.toLowerCase();
      if (node.id) {
        seg += "#" + node.id;
        segs.unshift(seg);
        break;
      }
      const cls = (node.getAttribute("class") || "")
        .trim().split(/\s+/).filter(Boolean)[0];
      if (cls) seg += "." + cls;
      // nth-of-type fuer Eindeutigkeit unter gleichen Geschwistern
      const parent = node.parentNode;
      if (parent && parent.nodeType === 1) {
        let n = 1;
        let sib = node;
        while ((sib = sib.previousElementSibling)) {
          if (sib.tagName === node.tagName) n++;
        }
        seg += ":nth-of-type(" + n + ")";
      }
      segs.unshift(seg);
      node = node.parentNode;
      depth++;
    }
    return segs.join(">");
  }

  // ── Sichtbarkeits-Filter ───────────────────────────────────────────────────
  function isLegitInvisibleTag(el) {
    const tag = el.tagName.toLowerCase();
    return tag === "script" || tag === "template" || tag === "defs" ||
           tag === "style" || tag === "head" || tag === "meta" ||
           tag === "link" || tag === "title";
  }

  function isVisible(el) {
    if (isLegitInvisibleTag(el)) return false;
    // Nachfahre eines <defs> oder [hidden] / display:none — Client-Rects leer
    if (el.closest && el.closest("defs")) return false;
    if (el.closest && el.closest("[hidden]")) return false;
    const cs = window.getComputedStyle(el);
    if (cs.display === "none") return false;
    if (cs.visibility === "hidden" || cs.visibility === "collapse") return false;
    // nicht im Render-Tree (deckt display:none-Vorfahren ab)
    if (el.getClientRects().length === 0) return false;
    return true;
  }

  const all = Array.from(document.querySelectorAll("*"));

  // ── 1) Broken-Img ──────────────────────────────────────────────────────────
  for (const el of all) {
    if (el.tagName.toLowerCase() !== "img") continue;
    if (!isVisible(el)) continue;
    if (el.naturalWidth === 0) {
      findings.push({
        typ: "broken-img",
        selektor: cssPath(el),
        detail: oneLineB(el.getAttribute("src") || "(kein src)"),
        messwert: "naturalWidth:0",
      });
    }
  }

  // ── 2) Viewport-Overflow (Element-aus-Viewport) ────────────────────────────
  for (const el of all) {
    if (!isVisible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    const overR = r.right - W;
    const overB = r.bottom - H;
    if (overR > EPS || overB > EPS) {
      findings.push({
        typ: "viewport-overflow",
        selektor: cssPath(el),
        detail: "Box rechts/unten ueber Viewport " + W + "x" + H,
        messwert: "ueber_rechts:" + Math.round(Math.max(0, overR)) +
                  "px,ueber_unten:" + Math.round(Math.max(0, overB)) + "px",
      });
    }
  }

  // ── 3) Root-/Container-Overflow-Clip ───────────────────────────────────────
  for (const el of [document.documentElement, document.body]) {
    if (!el) continue;
    const ow = el.scrollWidth - el.clientWidth;
    const oh = el.scrollHeight - el.clientHeight;
    if (ow > EPS || oh > EPS) {
      findings.push({
        typ: "root-overflow",
        selektor: cssPath(el),
        detail: "scrollWidth/Height > clientWidth/Height",
        messwert: "overflow_x:" + Math.round(Math.max(0, ow)) +
                  "px,overflow_y:" + Math.round(Math.max(0, oh)) + "px",
      });
    }
  }

  // ── 4) Null-Groesse (Content-Element, das sichtbar sein SOLL) ──────────────
  // Restriktiv gegen Fehlbefunde: nur <img> ODER Blatt-Element mit eigenem,
  // nicht-leerem Text. Struktur-Spacer (leere Wrapper) bleiben aussen vor.
  for (const el of all) {
    if (!isVisible(el)) continue;
    const tag = el.tagName.toLowerCase();
    const isImg = tag === "img";
    const isTextLeaf = el.children.length === 0 &&
      (el.textContent || "").trim().length > 0;
    if (!isImg && !isTextLeaf) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) {
      findings.push({
        typ: "null-groesse",
        selektor: cssPath(el),
        detail: isImg
          ? oneLineB("img:" + (el.getAttribute("src") || "(kein src)"))
          : oneLineB("text:" + (el.textContent || "").trim()),
        messwert: "breite:" + Math.round(r.width) +
                  "px,hoehe:" + Math.round(r.height) + "px",
      });
    }
  }

  // ── 5) Text-Ellipsis-Clipping ──────────────────────────────────────────────
  for (const el of all) {
    if (!isVisible(el)) continue;
    if (el.children.length !== 0) continue;            // nur Text-Blaetter
    if ((el.textContent || "").trim().length === 0) continue;
    const cs = window.getComputedStyle(el);
    const ellipsis = cs.textOverflow === "ellipsis";
    const clipped = cs.overflowX === "hidden" || cs.overflow === "hidden";
    if (!ellipsis && !clipped) continue;
    const over = el.scrollWidth - el.clientWidth;
    if (over > EPS) {
      findings.push({
        typ: "text-clipping",
        selektor: cssPath(el),
        detail: oneLineB((el.textContent || "").trim()),
        messwert: "abgeschnitten:" + Math.round(over) + "px",
      });
    }
  }

  // ── 6) Underfill (Fuellinvariante — Leerband / Content deutlich < Viewport) ─
  // DC-18: Responsive Views muessen das Viewport vollstaendig fuellen
  // (display-client.md DC-18). Bleibt die Body-Bounding-Box deutlich kleiner als
  // das Viewport, liegt ein Leerband (Letterbox) vor — Vertragsbruch.
  //
  // Gate: Nur wenn opts.checkUnderfill === true (d. h. die View ist als
  // responsiv / fit=viewport markiert). Fixe Views (Letterbox DC-12/DC-15)
  // duerfen einen kleineren Body haben — kein underfill-Befund dort.
  //
  // Strategie: document.body.getBoundingClientRect(). Scroll-Container wie
  // .liste-eintraege (overflow-y:auto) werden NICHT einzeln geprueft — ihr
  // Inhalt darf kuerzer sein als der Scroll-Bereich; der Body-Rect zaehlt.
  //
  // Toleranz: FILL_EPS = 5 % je Viewport-Dimension (deckt Sub-Pixel, Borders,
  // marginale Padding ab; faengt echtes Leerband >=5 % sicher).
  if (opts && opts.checkUnderfill) {
    const FILL_EPS = 0.05;
    const bodyEl = document.body;
    if (bodyEl) {
      const br = bodyEl.getBoundingClientRect();
      const unterW = W - br.width;
      const unterH = H - br.height;
      if (unterW > W * FILL_EPS || unterH > H * FILL_EPS) {
        findings.push({
          typ: "underfill",
          selektor: cssPath(bodyEl),
          detail: "Content-Bounding-Box kleiner als Viewport " + W + "x" + H +
                  " (DC-18: Fuellung erwartet)",
          messwert: "leerband_breite:" + Math.round(Math.max(0, unterW)) +
                    "px,leerband_hoehe:" + Math.round(Math.max(0, unterH)) + "px",
        });
      }
    }
  }

  function oneLineB(s) {
    return String(s).replace(/\s+/g, " ").trim().slice(0, 160);
  }

  return findings;
}

// ─────────────────────────────────────────────────────────────────────────────
// Browser-Kontext: Tier-B Kollisionsvertrag
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Selbst-enthaltene Browser-Funktion. Prueft Selektor-Paare auf
 * Bounding-Box-Ueberlappung. Jeder Selektor muss auf >=1 Element zeigen; es
 * zaehlt der erste Treffer. Fehlt ein Selektor, ist das selbst ein Befund
 * (Vertrag bezieht sich auf nicht vorhandenes Markup → echte Regression-Quelle).
 *
 * Argument: { paare: [{a,b,note}], toleranz_px }
 */
export function collisionContractFn(contract) {
  const tol = typeof contract.toleranz_px === "number" ? contract.toleranz_px : 1.0;
  const findings = [];

  function vis(el) {
    if (!el) return false;
    const cs = window.getComputedStyle(el);
    if (cs.display === "none") return false;
    if (cs.visibility === "hidden" || cs.visibility === "collapse") return false;
    if (el.getClientRects().length === 0) return false;
    return true;
  }

  for (const paar of contract.paare || []) {
    const elA = document.querySelector(paar.a);
    const elB = document.querySelector(paar.b);

    if (!elA || !elB) {
      findings.push({
        typ: "kollision-vertrag",
        selektor: paar.a + " <> " + paar.b,
        detail: (paar.note || "") + " | Selektor fehlt: " +
                (!elA ? paar.a : "") + (!elA && !elB ? " + " : "") +
                (!elB ? paar.b : ""),
        messwert: "selektor_fehlt",
      });
      continue;
    }
    if (!vis(elA) || !vis(elB)) {
      // Beide unsichtbar zu pruefen ist sinnlos; nicht als Kollision werten.
      continue;
    }

    const a = elA.getBoundingClientRect();
    const b = elB.getBoundingClientRect();
    const ovX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const ovY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ovX > tol && ovY > tol) {
      findings.push({
        typ: "kollision-vertrag",
        selektor: paar.a + " <> " + paar.b,
        detail: paar.note || "",
        messwert: "ueberlappung:" + Math.round(ovX) + "x" + Math.round(ovY) + "px",
      });
    }
  }

  return findings;
}
