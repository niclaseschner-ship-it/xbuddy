/**
 * test_alben_js.test.js — KIND_ID-Fallback-Regressionstest für alben.js.
 *
 * AC3 / T1027 (Lego-Konsistenz): Prüft positiv
 * (/display/hoerspiel/neko/alben → KIND_ID==='neko')
 * und negativ (Standalone-Dev-URL fällt auf 'paula').
 *
 * Testet die IIFE-Logik aus alben.js Z. 8-11 (HSP-26, URL-3a).
 * Analog zu test_eltern_js.test.js, andere URL-Pattern.
 *
 * Kein jsdom, kein npm — vanilla node:test.
 */

"use strict";

const { test } = require("node:test");
const assert   = require("node:assert/strict");
const path     = require("node:path");
const { makeDom, makeFetchSpy } = require(
  path.join(__dirname, "../../seiten/tests/_dom_stub.js")
);

// ── Hilfsfunktion: KIND_ID-Extraktion isoliert testen ────────────────────────
// Spiegelt die IIFE-Logik aus alben.js Z. 9 1:1, ohne Seiten-Effekte durch
// einen require()-Call (der z.B. DOMContentLoaded-Listener registrieren würde).

function extractKindId(pathname) {
  const m = pathname.match(/^\/display\/hoerspiel\/([^/]+)\/alben/);
  return m ? m[1] : 'paula';
}

// ── Tests ─────────────────────────────────────────────────────────────────────

/**
 * Test 1 (positiv) — /display/hoerspiel/neko/alben → KIND_ID === 'neko'
 *
 * URL-3a / HSP-26: kind_id aus pathname-Segment 3 (0-basiert, nach erstem Slash).
 */
test("alben.js KIND_ID: /display/hoerspiel/neko/alben → 'neko'", () => {
  const result = extractKindId("/display/hoerspiel/neko/alben");
  assert.equal(result, "neko", (
    "KIND_ID muss 'neko' sein für Pfad '/display/hoerspiel/neko/alben' " +
    "(HSP-26, URL-3a). Tatsächlicher Wert: " + result
  ));
});

/**
 * Test 2 (positiv) — /display/hoerspiel/paula/alben → KIND_ID === 'paula'
 *
 * Symmetrietest für den Standard-Fall (paula-Instanz).
 */
test("alben.js KIND_ID: /display/hoerspiel/paula/alben → 'paula'", () => {
  const result = extractKindId("/display/hoerspiel/paula/alben");
  assert.equal(result, "paula", (
    "KIND_ID muss 'paula' sein für Pfad '/display/hoerspiel/paula/alben'. " +
    "Tatsächlicher Wert: " + result
  ));
});

/**
 * Test 3 (negativ / Fallback) — Dev-Standalone-URLs fallen auf 'paula'
 *
 * Wenn alben.js direkt oder über einen einfachen HTTP-Server ohne den
 * /display/hoerspiel/<kind_id>/alben-Pfad aufgerufen wird, muss der
 * Fallback 'paula' greifen (Z. 10: "Fallback: 'paula' für Dev/Standalone").
 */
test("alben.js KIND_ID: Dev-Standalone-URL (kein Match) → Fallback 'paula'", () => {
  const result1 = extractKindId("/alben");
  assert.equal(result1, "paula", "Pfad '/alben' soll auf Fallback 'paula' treffen");

  const result2 = extractKindId("/display/hoerspiel/alben");
  assert.equal(result2, "paula", "Pfad '/display/hoerspiel/alben' (ohne kind_id) soll auf Fallback 'paula' treffen");

  const result3 = extractKindId("/");
  assert.equal(result3, "paula", "Root-Pfad '/' soll auf Fallback 'paula' treffen");
});

/**
 * Test 4 — exportiertes KIND_ID-Modul-Binding mit location.pathname='neko'
 *
 * Prüft das tatsächliche alben.js-Modul: wenn location.pathname='/display/hoerspiel/neko/alben'
 * beim Laden gesetzt ist, muss das exportierte KIND_ID 'neko' sein (AC4/T1027).
 */
test("alben.js exports: KIND_ID === 'neko' wenn pathname = /display/hoerspiel/neko/alben", () => {
  const doc      = makeDom();
  const fetchSpy = makeFetchSpy({});

  // Stubs VOR require() setzen (IIFE + DOMContentLoaded-Listener laufen beim Laden)
  global.location = {
    pathname: "/display/hoerspiel/neko/alben",
    hash:     "",
  };
  global.window = {
    location:         global.location,
    addEventListener: () => {},
  };
  global.document   = doc;
  global.fetch      = fetchSpy;
  global.localStorage = {
    getItem:    () => null,
    setItem:    () => {},
    removeItem: () => {},
  };
  global.Audio = function() {
    return {
      src: "", playbackRate: 1.0, paused: true, muted: false,
      pause: () => {}, play: async () => {},
      addEventListener: () => {}, removeEventListener: () => {},
    };
  };
  global.navigator = {
    mediaSession: {
      setActionHandler: () => {},
      metadata: null,
      playbackState: "none",
    },
  };
  global.MediaMetadata = function(data) { return data; };
  global.setTimeout   = () => {};
  global.clearTimeout = () => {};
  global.Promise      = Promise;

  // Modul-Cache leeren (KIND_ID wird beim Laden evaluiert)
  const modulePath = require.resolve(path.join(__dirname, "../static/alben.js"));
  delete require.cache[modulePath];
  const alben = require(path.join(__dirname, "../static/alben.js"));

  assert.equal(alben.KIND_ID, "neko", (
    "Exportiertes KIND_ID muss 'neko' sein wenn location.pathname='/display/hoerspiel/neko/alben'. " +
    "Tatsächlicher Wert: " + alben.KIND_ID
  ));
});
