/**
 * render_parity_dom.test.js — #1210 Parity-Guard, MAU-DOM-Proben (node --test).
 *
 * Beweist auf der Node-headless-DOM-Attrappe (kein jsdom, kein npm):
 *   - Die DUMME Mini-App-View rendert je bekanntem Roh-Typ eine Karte aus dem
 *     Kontrakt (Item-Menge, nicht Pixel).
 *   - Der deklarative audience-Filter greift: Mini-App-Karten in buddy_gruppen
 *     (audience nur "uebersicht") werden uebersprungen; die dedizierte
 *     mini_apps-Sektion rendert sie.
 *   - URL-WERTE kommen aus dem Kontrakt (card.urls / shell_urls), NICHT aus
 *     window.location — die fruehere Drift-Quelle ist weg.
 *
 * Lauf: node --test seiten/tests/render_parity_dom.test.js
 */

"use strict";

const { test } = require("node:test");
const assert   = require("node:assert/strict");
const { sammleKarten } = require("./render_parity_probe.js");

const HEIM = "https://heim.test";
const TAIL = "https://tail.test";

// Repraesentativer Kontrakt (Form von render.baue_layout), der jeden von der
// MAU gerenderten Roh-Typ abdeckt.
function _kontrakt() {
  const bothAudience = ["uebersicht", "mini-app-uebersicht"];
  const karte = (typ, key, pfad, extra) => Object.assign({
    key, typ, label: "L-" + key, pfad, icon: "/i/" + key + ".png",
    urls: { heim: HEIM + pfad, tailscale: TAIL + pfad },
    web_app_url: "", funnel_url: "", audience: bothAudience.slice(),
  }, extra || {});

  return {
    mini_apps: [
      Object.assign(karte("mini-app", "essen/einkauf", "/seiten/essen/einkauf"), {
        web_app_url: "https://t.me/xbuddybot/einkauf",
        funnel_url: "https://funnel.test/seiten/essen/einkauf",
        audience: ["uebersicht"],
      }),
    ],
    hero_paare: [],
    buddy_gruppen: [
      { app: "wetter", anzahl: 1, karten: [karte("display", "wetter/heute", "/display/wetter/heute")] },
      { app: "regeln", anzahl: 1, karten: [karte("controller", "regeln/x", "/controller/regeln/x")] },
      { app: "instanz", anzahl: 1, karten: [karte("display-client", "display-solo", "/display/solo")] },
      { app: "eltern-x", anzahl: 1, karten: [karte("eltern", "elt/x", "/eltern/x")] },
      // Mini-App-Karte, die AUCH in den Buddy-Gruppen steht (Grossbild rendert
      // sie hier). audience nur "uebersicht" → die MAU MUSS sie hier ueberspringen.
      { app: "essen", anzahl: 1, karten: [
        Object.assign(karte("mini-app", "essen/einkauf", "/seiten/essen/einkauf"),
          { audience: ["uebersicht"] }),
      ] },
    ],
    snapshot_pending: [], heim_origin: HEIM, tailscale_origin: TAIL,
  };
}

test("MAU rendert je bekanntem Roh-Typ mindestens eine Karte", () => {
  const cards = sammleKarten(_kontrakt());
  const typen = new Set(cards.map((c) => c.typ));
  for (const erwartet of ["mini-app", "eltern", "display", "controller"]) {
    assert.ok(typen.has(erwartet), "Roh-Typ fehlt in MAU-Render: " + erwartet);
  }
});

test("audience-Filter: Mini-App aus buddy_gruppen wird uebersprungen, mini_apps-Sektion rendert sie", () => {
  const cards = sammleKarten(_kontrakt());
  const miniAppKarten = cards.filter((c) => c.typ === "mini-app");
  // Genau EINE Mini-App-Karte (aus mini_apps) — die buddy_gruppen-Kopie ist
  // per audience gefiltert; sonst waeren es zwei.
  assert.equal(miniAppKarten.length, 1, "Mini-App darf nicht doppelt rendern (audience-Filter)");
  assert.equal(miniAppKarten[0].url, "https://t.me/xbuddybot/einkauf",
    "Mini-App-Karte traegt den t.me-Deep-Link aus mini_apps (nicht die pfad-URL)");
});

test("URL-Werte kommen aus dem Kontrakt (Heim + Tailscale), nicht aus window.location", () => {
  const cards = sammleKarten(_kontrakt());
  const urls = new Set(cards.map((c) => c.url));
  assert.ok(urls.has(HEIM + "/display/wetter/heute"), "Heim-URL aus Kontrakt fehlt");
  assert.ok(urls.has(TAIL + "/display/wetter/heute"), "Tailscale-URL aus Kontrakt fehlt");
  // SHELL-10: Shell-URLs kamen aus hero_paare panels (display-client/panel), die in RAT-31 E3 entfernt wurden
});

test("Teeth-Probe: fehlt ein Typ im Kontrakt, fehlt er auch im MAU-Render (kein Blind-Gruen)", () => {
  const k = _kontrakt();
  // Simuliert einen Renderer/Kontrakt, der den controller-Typ verliert.
  k.buddy_gruppen = k.buddy_gruppen.filter((g) => g.app !== "regeln");
  const typen = new Set(sammleKarten(k).map((c) => c.typ));
  assert.ok(!typen.has("controller"),
    "Guard waere blind, wenn controller trotz Entfernung noch auftauchte");
});
