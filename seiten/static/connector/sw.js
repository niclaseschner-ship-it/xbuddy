// sw.js — Service-Worker fuer die Connector-PWA (CONN-8).
//
// Cache-Strategie:
//   - cache-first fuer statische Mantel-Assets (style.css, manifest, Logos, Icons).
//   - pass-through (network-only) fuer die HTML-Shell /api/v1/seiten/connector/ —
//     sie traegt das server-gerenderte Aggregat (CONN-8) und darf NIE veralten.
//
// Cache-Versionierung (PWAM-4 / reference_mini_app_cache_buster.md):
//   __BUILD_ID__ wird beim Ausliefern via connector_sw_view (seiten/main.py)
//   durch den aktuellen build_id-Wert ersetzt. Das invalidiert den alten Cache
//   (activate-Event loescht fremde Namespaces).

'use strict';

// BUILD_ID-Platzhalter — wird beim Ausliefern von seiten/main.py substituiert
// (connector_sw_view, read_sw_with_build_id, PWAM-4). Default beim Lokal-Test: "0".
const BUILD_ID = '__BUILD_ID__';
const CACHE_NAME = 'connector-pwa-' + BUILD_ID;

// Statische Mantel-Assets (cache-first). Die HTML-Shell ist bewusst NICHT dabei.
const MANTEL_ASSETS = [
  '/api/v1/seiten/static/connector/manifest.json',
  '/api/v1/seiten/static/connector/style.css',
  '/api/v1/seiten/static/connector/icon-192.png',
  '/api/v1/seiten/static/connector/icon-512.png',
  '/api/v1/seiten/static/connector/icon-maskable-512.png',
  '/api/v1/seiten/static/connector/logos/anthropic.svg',
  '/api/v1/seiten/static/connector/logos/mistral.svg',
  '/api/v1/seiten/static/connector/logos/azure.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        MANTEL_ASSETS.map((url) =>
          cache.add(url).catch((e) => {
            console.warn('[sw] Mantel-Asset nicht gecached:', url, e);
          })
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('connector-pwa-') && k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

function isStaticMantel(url) {
  return url.pathname.startsWith('/api/v1/seiten/static/connector/');
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

  // Nur GET wird gecached. POST/PUT/PATCH/DELETE gehen immer direkt durch.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Cross-Origin nicht anfassen.
  if (url.origin !== self.location.origin) return;

  if (isStaticMantel(url)) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // HTML-Shell + alles andere: pass-through (network-only — Aggregat nie veralten).
});
