// controller/_shared/config.js — PWA-4-konformer Config-Lader.
// Wird von Controller-PWAs eingebunden, bevor der PWA-spezifische Code läuft.
// Refs: conventions/controller-pwa.md PWA-4.
//
// Lade-Reihenfolge (PWA-4):
//   Code-Defaults → config.json → URL-Parameter
//
// Schnittstelle:
//   loadPwaConfig(opts) → Promise<config>
//
//   opts.defaults    — Pflicht. Objekt mit Code-Defaults (z. B. aus configDefaults()).
//   opts.urlParams   — Optional. URLSearchParams-Objekt für URL-Parameter-Overlay.
//                      Wird übergeben, kann null/undefined sein → kein URL-Overlay.
//   opts.applyUrlParams — Optional. Funktion (base, qs) → overrides.
//                      Erlaubt der PWA, die URL-Params typsicher zu mappen
//                      (Zahlen parsen, Keys benennen). Fehlt sie, werden
//                      keine URL-Parameter gemappt (nur config.json-Merge).
//   opts.onWarn      — Optional. Callback (msg, err) für stille Warn-Meldungen.
//                      Fehlt sie: console.warn.
//
// Verhalten bei fehlendem/kaputter config.json (PWA-4):
//   Stumm auf Defaults zurückfallen; Fehler via onWarn protokollieren.
//   Die Seite bleibt funktionsfähig.

(function (root) {
  'use strict';

  function loadPwaConfig(opts) {
    var defaults  = opts.defaults || {};
    var warn      = opts.onWarn   || function () { console.warn.apply(console, arguments); };
    var qs        = opts.urlParams || null;
    var applyUrl  = opts.applyUrlParams || null;

    return Promise.resolve()
      .then(function () {
        return fetch('./config.json', { cache: 'no-store' });
      })
      .then(function (res) {
        if (!res || !res.ok) throw new Error('HTTP ' + (res && res.status));
        return res.json();
      })
      .then(function (fileCfg) {
        // Schritt 1+2: Defaults + config.json
        var merged = Object.assign({}, defaults, fileCfg);
        // Schritt 3: URL-Parameter-Overlay (nur wenn applyUrlParams übergeben)
        if (qs && applyUrl) {
          var urlOverrides = applyUrl(merged, qs);
          if (urlOverrides && typeof urlOverrides === 'object') {
            merged = Object.assign({}, merged, urlOverrides);
          }
        }
        return merged;
      })
      .catch(function (err) {
        // PWA-4: fehlt/kaputt → stumm auf Defaults, warn.
        warn('config.json konnte nicht geladen werden — fallback auf Defaults:', err);
        var base = Object.assign({}, defaults);
        if (qs && applyUrl) {
          var urlOverrides = applyUrl(base, qs);
          if (urlOverrides && typeof urlOverrides === 'object') {
            base = Object.assign({}, base, urlOverrides);
          }
        }
        return base;
      });
  }

  // Export: Browser → globalThis.pwaShared; Node (Tests) → module.exports.
  var api = { loadPwaConfig: loadPwaConfig };
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.pwaShared = api;
  }

})(typeof globalThis !== 'undefined' ? globalThis : this);
