/**
 * render_parity_probe.js — #1210 Parity-Guard, MAU-Seite (Node-headless-DOM).
 *
 * Rendert die DUMME Mini-App-View (mini-app-uebersicht.js) ueber einen
 * Layout-Kontrakt (render.baue_layout-Ausgabe) auf der minimalen DOM-Attrappe
 * (_dom_stub.js — kein jsdom, kein npm) und sammelt je gerenderter Karte
 * { typ, url } aus den data-Attributen ein.
 *
 * Zwei Nutzungen:
 *   1. Als Modul: `sammleKarten(layout)` → [{typ, url}, …].
 *   2. Als CLI (von test_render_parity.py aufgerufen):
 *        node render_parity_probe.js <layout.json>
 *      liest den Kontrakt, druckt {cards:[…]} als JSON auf stdout.
 *
 * KEIN Screenshot, keine Pixel — nur die Item-Menge + URL-Werte (RAT-24-Schicht).
 */

"use strict";

const { makeDom } = require("./_dom_stub.js");

// document muss VOR dem require der View existieren (die View loest es via
// _doc() erst zur Render-Zeit auf, aber sicher ist sicher).
if (typeof global.document === "undefined") {
  global.document = makeDom();
}

const mau = require("../static/mini-app-uebersicht.js");

// Rekursiver Baum-Walk ueber die appendChild-Kinder der DOM-Attrappe.
function _walk(el, out) {
  const kids = (el && el._children) || [];
  for (const kind of kids) {
    if (kind.dataset && kind.dataset.kartenTyp) {
      out.push({ typ: kind.dataset.kartenTyp, url: kind.dataset.url || "" });
    }
    _walk(kind, out);
  }
}

/**
 * Rendert alle drei MAU-Sektionen ueber den Kontrakt und sammelt die Karten.
 * @param {object} layout - render.baue_layout-Ausgabe.
 * @returns {Array<{typ:string,url:string}>}
 */
function sammleKarten(layout) {
  const doc = makeDom();
  global.document = doc;

  const platform = {
    openLink: () => {},
    copyText: () => true,
  };
  const zeigeToast = () => {};

  const c1 = doc.createElement("div");
  mau.rendereMinApps(platform, zeigeToast, c1, layout.mini_apps || []);

  const c2 = doc.createElement("div");
  mau.rendereGeraetePaare(platform, zeigeToast, c2, layout.hero_paare || []);

  const c3 = doc.createElement("div");
  mau.rendereBuddySeiten(platform, zeigeToast, c3, layout.buddy_gruppen || []);

  const cards = [];
  [c1, c2, c3].forEach((c) => _walk(c, cards));
  return cards;
}

module.exports = { sammleKarten };

// CLI-Modus: von test_render_parity.py aufgerufen.
if (require.main === module) {
  const fs = require("fs");
  const pfad = process.argv[2];
  if (!pfad) {
    process.stderr.write("usage: node render_parity_probe.js <layout.json>\n");
    process.exit(2);
  }
  const layout = JSON.parse(fs.readFileSync(pfad, "utf-8"));
  const cards = sammleKarten(layout);
  process.stdout.write(JSON.stringify({ cards }));
}
