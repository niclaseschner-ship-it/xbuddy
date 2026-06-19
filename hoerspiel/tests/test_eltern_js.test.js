/**
 * test_eltern_js.test.js — KIND_ID-Fallback-Regressionstest für eltern.js.
 *
 * AC3 / T1027: Prüft positiv (/seiten/hoerspiel/neko/eltern → KIND_ID==='neko')
 * und negativ (Standalone-Dev-URL fällt auf 'paula').
 *
 * Testet die IIFE-Logik aus eltern.js Z. 21-24 (HSP-26, URL-3a, T970).
 *
 * Kein jsdom, kein npm — vanilla node:test (analog test_eltern_aggr_folgen.test.js).
 */

"use strict";

const { test } = require("node:test");
const assert   = require("node:assert/strict");
const path     = require("node:path");
const { makeDom, makeFetchSpy } = require(
  path.join(__dirname, "../../seiten/tests/_dom_stub.js")
);

// ── Hilfsfunktion: KIND_ID-Extraktion isoliert testen ────────────────────────
// Wir testen die IIFE-Logik direkt ohne erneutes require() von eltern.js —
// das verhindert Seiteneffekte durch globales location.pathname beim Modul-Load.
// Die Regexp-Logik aus eltern.js Z. 22 wird 1:1 hier gespiegelt.

function extractKindId(pathname) {
  const m = pathname.match(/^\/seiten\/hoerspiel\/([^/]+)\/eltern/);
  return m ? m[1] : 'paula';
}

// ── Tests ─────────────────────────────────────────────────────────────────────

/**
 * Test 1 (positiv) — /seiten/hoerspiel/neko/eltern → KIND_ID === 'neko'
 *
 * URL-3a / T970: kind_id wird aus pathname-Segment 3 (0-basiert) extrahiert.
 * Prüft, dass ein Neko-URL-Pfad korrekt zu kind_id='neko' führt.
 */
test("eltern.js KIND_ID: /seiten/hoerspiel/neko/eltern → 'neko'", () => {
  const result = extractKindId("/seiten/hoerspiel/neko/eltern");
  assert.equal(result, "neko", (
    "KIND_ID muss 'neko' sein für Pfad '/seiten/hoerspiel/neko/eltern' " +
    "(HSP-26, URL-3a, T970). Tatsächlicher Wert: " + result
  ));
});

/**
 * Test 2 (positiv) — /seiten/hoerspiel/paula/eltern → KIND_ID === 'paula'
 *
 * Symmetrietest: paula-Instanz muss aus URL ebenfalls korrekt erkannt werden.
 */
test("eltern.js KIND_ID: /seiten/hoerspiel/paula/eltern → 'paula'", () => {
  const result = extractKindId("/seiten/hoerspiel/paula/eltern");
  assert.equal(result, "paula", (
    "KIND_ID muss 'paula' sein für Pfad '/seiten/hoerspiel/paula/eltern'. " +
    "Tatsächlicher Wert: " + result
  ));
});

/**
 * Test 3 (negativ / Fallback) — Standalone-Dev-URL fällt auf 'paula'
 *
 * Entwicklerlokal: eltern.js wird direkt als Datei oder über einen einfachen
 * HTTP-Server ohne den /seiten/hoerspiel/<kind_id>/eltern-Pfad geöffnet.
 * Das IIFE muss dann auf den Fallback 'paula' zurückfallen (Z. 23, "nie im
 * Produktivbetrieb wirksam").
 */
test("eltern.js KIND_ID: Dev-Standalone-URL (kein Match) → Fallback 'paula'", () => {
  // Typischer Dev-Pfad: /eltern oder /hoerspiel/eltern (kein kind_id-Segment)
  const result1 = extractKindId("/eltern");
  assert.equal(result1, "paula", "Pfad '/eltern' soll auf Fallback 'paula' treffen");

  const result2 = extractKindId("/hoerspiel/eltern");
  assert.equal(result2, "paula", "Pfad '/hoerspiel/eltern' soll auf Fallback 'paula' treffen");

  const result3 = extractKindId("/");
  assert.equal(result3, "paula", "Root-Pfad '/' soll auf Fallback 'paula' treffen");
});

/**
 * Test 4 — exportiertes KIND_ID-Modul-Binding mit location.pathname='neko'
 *
 * Prüft das tatsächliche eltern.js-Modul: wenn location.pathname='/seiten/hoerspiel/neko/eltern'
 * beim Laden gesetzt ist, muss das exportierte KIND_ID 'neko' sein.
 */
test("eltern.js exports: KIND_ID === 'neko' wenn pathname = /seiten/hoerspiel/neko/eltern", () => {
  // Stubs müssen VOR require() gesetzt werden (IIFE läuft beim Laden)
  const doc      = makeDom();
  const fetchSpy = makeFetchSpy({ alben: [] });

  // pathname auf neko setzen
  global.location = {
    pathname: "/seiten/hoerspiel/neko/eltern",
    hash:     "",
  };
  global.window = {
    Telegram:         { WebApp: { initData: "" } },
    location:         global.location,
    addEventListener: () => {},
  };
  global.document  = doc;
  global.fetch     = fetchSpy;
  global.Audio     = function() {
    return {
      src: "", playbackRate: 1.0, paused: true,
      pause: () => {}, play: async () => {},
      addEventListener: () => {},
    };
  };
  global.navigator    = { wakeLock: null };
  global.setTimeout   = () => {};
  global.clearTimeout = () => {};
  global.Promise      = Promise;

  // DOM-Elemente registrieren (IIFE benötigt einige davon)
  doc._registerEl("panel-einstellungen", doc.createElement("div"));
  doc._registerEl("panel-folgen",        doc.createElement("div"));
  doc._registerEl("folgen-player",       doc.createElement("div"));
  doc._registerEl("folgen-ladehinweis",  doc.createElement("div"));
  doc._registerEl("tab-einstellungen",   doc.createElement("button"));
  doc._registerEl("tab-folgen",          doc.createElement("button"));
  doc._registerEl("toast",               doc.createElement("div"));

  global.getPlatform = () => ({
    ready:          async () => {},
    ensureAuth:     async () => false,
    setMainButton:  () => {},
    hideMainButton: () => {},
    showMainButton: () => {},
  });

  // Modul-Cache leeren damit KIND_ID neu evaluiert wird
  const modulePath = require.resolve(path.join(__dirname, "../static/eltern.js"));
  delete require.cache[modulePath];
  const eltern = require(path.join(__dirname, "../static/eltern.js"));

  assert.equal(eltern.KIND_ID, "neko", (
    "Exportiertes KIND_ID muss 'neko' sein wenn location.pathname='/seiten/hoerspiel/neko/eltern'. " +
    "Tatsächlicher Wert: " + eltern.KIND_ID
  ));
});
