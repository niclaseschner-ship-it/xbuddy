// sw.js — Service-Worker fuer Heim-Shell-PWA (SHELL-PWA).
//
// SHELL-PWA Cache-Strategie:
//   - cache-first fuer Shell-Mantel-Assets (HTML, CSS, manifest, icons).
//   - pass-through (network-only) fuer Panel-Iframes (/controller, /display)
//     und API-Calls — die eingebetteten Surfaces haben eigene SWs.
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

function isShellMantel(url) {
  // Shell-HTML und Shell-Assets (CSS, manifest, icons) cachen.
  if (url.pathname.startsWith('/shell/')) return true;
  // Eigene CSS/JS-Assets unter /api/v1/seiten/static/ cachen.
  if (url.pathname.startsWith('/api/v1/seiten/static/')) {
    return url.pathname.includes('heim-shell') ||
           url.pathname.includes('platform.js');
  }
  return false;
}

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

  if (isShellMantel(url)) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // Alles andere: pass-through.
});
