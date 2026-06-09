// Tests für controller/_shared/config.js — pwaShared.loadPwaConfig.
// Lauf: node --test tests/ (von controller/_shared/ aus)
// Refs: conventions/pwa.md PWA-4, CONFIG-4 (stiller Fallback).

'use strict';

const { test } = require('node:test');
const assert   = require('node:assert/strict');

const pwaShared = require('../config.js');

// ===========================================================
//  Hilfsfunktion: simuliertes fetch-Stub
// ===========================================================

function withFetch(stub, fn) {
  const orig = global.fetch;
  global.fetch = stub;
  return Promise.resolve().then(fn).finally(() => { global.fetch = orig; });
}

// ===========================================================
//  CONFIG-1 / PWA-4 — Defaults-Merge
// ===========================================================

test('CONFIG-1 — leere config.json → Defaults greifen vollständig', async () => {
  await withFetch(
    async () => ({ ok: true, json: async () => ({}) }),
    async () => {
      const cfg = await pwaShared.loadPwaConfig({
        defaults: { foo: 'bar', num: 42 },
      });
      assert.strictEqual(cfg.foo, 'bar');
      assert.strictEqual(cfg.num, 42);
    }
  );
});

test('CONFIG-1 — config.json-Werte überschreiben Defaults', async () => {
  await withFetch(
    async () => ({ ok: true, json: async () => ({ foo: 'from-file' }) }),
    async () => {
      const cfg = await pwaShared.loadPwaConfig({
        defaults: { foo: 'default', extra: 'kept' },
      });
      assert.strictEqual(cfg.foo, 'from-file');
      assert.strictEqual(cfg.extra, 'kept');
    }
  );
});

// ===========================================================
//  CONFIG-2 / PWA-4 — URL-Overlay
// ===========================================================

test('CONFIG-2 — URL-Parameter überschreiben config.json-Wert', async () => {
  await withFetch(
    async () => ({ ok: true, json: async () => ({ router_url: 'http://from-file' }) }),
    async () => {
      const cfg = await pwaShared.loadPwaConfig({
        defaults: { router_url: 'http://default' },
        urlParams: new URLSearchParams('router_url=http%3A%2F%2Ffrom-url'),
        applyUrlParams: (base, qs) => {
          const v = qs.get('router_url');
          return v ? { router_url: v } : {};
        },
      });
      assert.strictEqual(cfg.router_url, 'http://from-url',
        'URL-Parameter muss Vorrang vor config.json haben');
    }
  );
});

test('CONFIG-2 — fehlendes applyUrlParams → URL-Params werden ignoriert', async () => {
  await withFetch(
    async () => ({ ok: true, json: async () => ({ foo: 'file' }) }),
    async () => {
      const cfg = await pwaShared.loadPwaConfig({
        defaults: { foo: 'default' },
        urlParams: new URLSearchParams('foo=url-value'),
        // kein applyUrlParams
      });
      assert.strictEqual(cfg.foo, 'file',
        'Ohne applyUrlParams darf kein URL-Overlay stattfinden');
    }
  );
});

// ===========================================================
//  CONFIG-4 / PWA-4 — stiller Fallback bei fetch-Fehler
// ===========================================================

test('CONFIG-4 — fetch-Fehler → kein Werfen, Defaults greifen', async () => {
  await withFetch(
    async () => { throw new Error('network error'); },
    async () => {
      const cfg = await pwaShared.loadPwaConfig({
        defaults: { foo: 'fallback' },
        onWarn: () => {},  // Warn-Callback still schalten
      });
      assert.strictEqual(cfg.foo, 'fallback',
        'Fetch-Fehler darf die Konfiguration nicht zum Absturz bringen');
    }
  );
});

test('CONFIG-4 — HTTP-Fehler (404) → kein Werfen, Defaults greifen', async () => {
  await withFetch(
    async () => ({ ok: false, status: 404, json: async () => ({}) }),
    async () => {
      const cfg = await pwaShared.loadPwaConfig({
        defaults: { bar: 'safe' },
        onWarn: () => {},
      });
      assert.strictEqual(cfg.bar, 'safe');
    }
  );
});

test('CONFIG-4 — stiller Fallback: onWarn-Callback wird aufgerufen', async () => {
  let warnCalled = false;
  await withFetch(
    async () => { throw new Error('offline'); },
    async () => {
      await pwaShared.loadPwaConfig({
        defaults: {},
        onWarn: () => { warnCalled = true; },
      });
      assert.ok(warnCalled,
        'onWarn muss bei fehlendem config.json aufgerufen werden (PWA-4 / CONFIG-4)');
    }
  );
});

test('CONFIG-4 — URL-Overlay greift auch im Fehlerfall', async () => {
  await withFetch(
    async () => { throw new Error('offline'); },
    async () => {
      const cfg = await pwaShared.loadPwaConfig({
        defaults: { router_url: 'http://default' },
        urlParams: new URLSearchParams('router_url=http%3A%2F%2Furl-override'),
        applyUrlParams: (base, qs) => {
          const v = qs.get('router_url');
          return v ? { router_url: v } : {};
        },
        onWarn: () => {},
      });
      assert.strictEqual(cfg.router_url, 'http://url-override',
        'URL-Overlay muss auch beim Fallback-Pfad angewendet werden');
    }
  );
});
