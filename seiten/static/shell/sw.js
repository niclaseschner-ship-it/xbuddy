// sw.js — Service-Worker fuer Heim-Shell-PWA (SHELL-PWA).
//
// SHELL-PWA Cache-Strategie (SHELL-PWA-SW):
//   - network-first fuer Shell-HTML-Navigation (/shell/<panel_id>, navigate-Modus).
//     Online: neuer Code laed sofort; Cache-Put fuer Offline-Fallback.
//     Offline: caches.match als Fallback (Installierbarkeit gewahrt, keep_installable).
//   - cache-first fuer Static-Assets: manifest.json, sw.js, icon-*.png unter
//     /shell/<panel_id>/<asset>; heim-shell.css und platform.js unter
//     /api/v1/seiten/static/ — stabil bzw. per BUILD_ID versioniert.
//   - pass-through (network-only) fuer Panel-Iframes (/controller, /display)
//     und alles andere — die eingebetteten Surfaces haben eigene SWs.
//
// Scope: /shell/ (deckt alle Shell-Instanzen je panel_id).
// Server sendet Service-Worker-Allowed: /shell/ Header (shell_asset_view,
// seiten/main.py) damit der Scope die SW-Herkunft (/shell/<panel_id>/sw.js)
// ueberschreiten darf.
//
// Cache-Versionierung (reference_mini_app_cache_buster.md):
//   BUILD_ID-Platzhalter wird beim Ausliefern durch seiten/main.py ersetzt
//   (shell_asset_view). activate-Event loescht alte Cache-Namespaces.

'use strict';

// SW-BUILD-ID wird beim Ausliefern von seiten/main.py ersetzt.
// Default beim Lokal-Test: "0".
const BUILD_ID = '__BUILD_ID__';
const CACHE_NAME = 'shell-pwa-' + BUILD_ID;

// Mantel-Assets, die beim install-Event gecached werden (cache-first).
// Absolute Pfade — Shell lebt unter /shell/<panel_id> (ohne Trailing-Slash).
const MANTEL_ASSETS = [
  '/api/v1/seiten/static/heim-shell.css',
  '/api/v1/seiten/static/platform.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // addAll fail-fast verhindern: jedes Asset einzeln versuchen.
      Promise.all(
        MANTEL_ASSETS.map((url) =>
          cache.add(url).catch((e) => {
            // Mantel-Asset nicht erreichbar — best-effort.
            // eslint-disable-next-line no-console
            console.warn('[sw-shell] Mantel-Asset nicht gecached:', url, e);
          })
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Alle Cache-Namespaces, die nicht zu diesem BUILD_ID gehoeren, loeschen.
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('shell-pwa-') && k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Strategien ───────────────────────────────────────────────────────────────

/**
 * Erkennt Shell-HTML-Navigation: /shell/<panel_id> (die eigentliche HTML-Seite).
 *
 * Signale (OR-verknuepft, robust fuer alle Chromium-Versionen):
 *   1. request.mode === 'navigate'  — Browser-Navigation (Haupt-Dokument).
 *   2. Fallback: Pfad ist /shell/<panel_id> ohne zweites Segment (kein '/').
 *      Damit werden Manifest, SW, Icons (/shell/<pid>/<asset>) NICHT
 *      als HTML-Navigation gezaehlt.
 *
 * @param {URL} url
 * @param {Request} req
 * @returns {boolean}
 */
function isShellHtmlNavigation(url, req) {
  if (!url.pathname.startsWith('/shell/')) return false;
  if (req.mode === 'navigate') return true;
  // Fallback: kein weiteres Slash-Segment hinter /shell/ → HTML-Seite
  const afterShell = url.pathname.slice('/shell/'.length);
  return afterShell.length > 0 && !afterShell.includes('/');
}

/**
 * Erkennt statische Shell-Assets, die cache-first bedient werden:
 *   - /shell/<panel_id>/manifest.json, /sw.js, /icon-*.png (zweites Segment)
 *   - /api/v1/seiten/static/heim-shell*.css und platform.js
 *
 * @param {URL} url
 * @returns {boolean}
 */
function isShellStaticAsset(url) {
  if (url.pathname.startsWith('/shell/')) {
    // Zweites Segment vorhanden → Asset (nicht HTML-Seite)
    const afterShell = url.pathname.slice('/shell/'.length);
    return afterShell.includes('/');
  }
  if (url.pathname.startsWith('/api/v1/seiten/static/')) {
    return url.pathname.includes('heim-shell') ||
           url.pathname.includes('platform.js');
  }
  return false;
}

/**
 * Network-first mit Cache-Fallback (SHELL-PWA-SW, HTML-Navigation).
 *
 * Online: fetch → cache-put → return Response.
 * Offline/Fehler: caches.match (Offline-Fallback, keep_installable).
 *
 * @param {Request} req
 * @returns {Promise<Response>}
 */
function networkFirst(req) {
  return fetch(req).then((res) => {
    if (res && res.ok) {
      const copy = res.clone();
      caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
    }
    return res;
  }).catch(() => caches.match(req));
}

/**
 * Cache-first (Static-Assets).
 *
 * @param {Request} req
 * @returns {Promise<Response>}
 */
function cacheFirst(req) {
  return caches.match(req).then((cached) => {
    if (cached) return cached;
    return fetch(req).then((res) => {
      if (res && res.ok) {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    });
  });
}

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Nur GET — POST/PATCH/DELETE gehen direkt durch.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Cross-Origin nicht anfassen.
  if (url.origin !== self.location.origin) return;

  // SHELL-PWA stop_rule sw_scope: Panel- und Display-Iframes NICHT abfangen
  // (/controller, /display). Deren eigene Service-Worker sind zustaendig.
  if (url.pathname.startsWith('/controller/') ||
      url.pathname.startsWith('/display/')) {
    return; // pass-through (kein respondWith)
  }

  // Shell-HTML-Navigation → network-first (SHELL-PWA-SW: neuer Code sofort online,
  // Offline-Fallback erhalten → Installierbarkeit gewahrt, keep_installable).
  if (isShellHtmlNavigation(url, req)) {
    event.respondWith(networkFirst(req));
    return;
  }

  // Static-Assets (manifest, icons, CSS, platform.js) → cache-first.
  if (isShellStaticAsset(url)) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // Alles andere: pass-through.
});
