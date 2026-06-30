/**
 * platform_dom.test.js — TelegramPlatform.ready() + BrowserPlatform.ready() Proben.
 *
 * 3 Tests via node --test, kein jsdom, kein npm.
 *
 * AC1: TelegramPlatform.ready() ruft expand() + disableVerticalSwipes() (beide vorhanden).
 * AC2: disableVerticalSwipes fehlt → kein Crash (Feature-Guard Bot API 7.7+).
 * AC3: BrowserPlatform.ready() unberuehrt — kein expand/disableVerticalSwipes-Aufruf.
 */

"use strict";

const { test } = require("node:test");
const assert   = require("node:assert/strict");

// platform.js greift nur in getPlatform() auf window zu; Klassen-Konstruktoren
// und ready() brauchen keine globalen DOM-Variablen — kein Global-Setup noetig.

const { TelegramPlatform, BrowserPlatform } = require("../static/platform.js");

// ── Tests ─────────────────────────────────────────────────────────────────────

/**
 * Fall A — AC1: TelegramPlatform.ready() ruft expand() UND disableVerticalSwipes()
 * wenn beide Methoden auf dem WebApp-Stub vorhanden sind.
 */
test("TelegramPlatform.ready(): ruft expand() + disableVerticalSwipes() wenn beide vorhanden", async () => {
  let readyCalled = false;
  let expandCalled = false;
  let dvsCalled = false;

  const stubWa = {
    ready:                  () => { readyCalled = true; },
    expand:                 () => { expandCalled = true; },
    disableVerticalSwipes:  () => { dvsCalled = true; },
  };

  const platform = new TelegramPlatform(stubWa);
  await platform.ready();

  assert.equal(readyCalled,  true, "WebApp.ready() aufgerufen");
  assert.equal(expandCalled, true, "WebApp.expand() aufgerufen");
  assert.equal(dvsCalled,    true, "WebApp.disableVerticalSwipes() aufgerufen");
});

/**
 * Fall B — AC2: disableVerticalSwipes fehlt auf dem Stub (Bot API < 7.7) →
 * Feature-Guard greift, kein Crash, expand() wird trotzdem aufgerufen.
 */
test("TelegramPlatform.ready(): kein Crash wenn disableVerticalSwipes fehlt", async () => {
  let expandCalled = false;

  const stubWa = {
    ready:   () => {},
    expand:  () => { expandCalled = true; },
    // disableVerticalSwipes absichtlich nicht vorhanden — simuliert aeltere Clients
  };

  const platform = new TelegramPlatform(stubWa);

  // Wirft keinen Fehler — wenn es doch werfen wuerde, schlaegt der Test fehl.
  await platform.ready();

  assert.equal(expandCalled, true, "expand() trotzdem aufgerufen (Feature-Guard laesst expand durch)");
  assert.equal(typeof stubWa.disableVerticalSwipes, "undefined", "Stub hat kein disableVerticalSwipes — Guard hat gewirkt");
});

/**
 * Fall C — AC3: BrowserPlatform.ready() bleibt unveraendert — kein Aufruf
 * von expand() oder disableVerticalSwipes() (kein WebApp-Objekt vorhanden).
 */
test("BrowserPlatform.ready(): ruft weder expand() noch disableVerticalSwipes()", async () => {
  const platform = new BrowserPlatform();

  // Kein Crash und kein TypeError — BrowserPlatform.ready() ist ein leerer async-Block.
  await platform.ready();

  // Verifizieren: Kein _wa gesetzt (BrowserPlatform hat keinen WebApp-Wrapper).
  assert.equal(platform._wa, undefined, "BrowserPlatform hat kein _wa (kein Telegram-Wrapper)");
});
