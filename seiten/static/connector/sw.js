// sw.js — Service-Worker fuer die Connector-PWA (CONN-8).
//
// Spiegel von seiten/static/plan/sw.js (PLAN-35). Wird als statisches Asset
// unter /api/v1/seiten/static/connector/sw.js ausgeliefert (Flask-static) —
// daher KEINE Server-Substitution der Cache-Version; sie steht als Konstante
// BUILD (bumpen, wenn der Mantel sich aendert).
//
// Cache-Strategie:
//   - cache-first fuer statische Mantel-Assets (style.css, manifest, Logos).
//   - pass-through (network-only) fuer die HTML-Shell /api/v1/seiten/connector/ —
//     sie traegt das server-gerenderte Aggregat (CONN-8) und darf NIE petralten.

'use strict';

const BUILD = 'v1';
const CACHE_NAME = 'connector-pwa-' + BUILD;

// Statische Mantel-Assets (cache-first). Die HTML-Shell ist bewusst NICHT dabei.
const MANTEL_ASSETS = [
  '/api/v1/seiten/static/connector/manifest.json',
  '/api/v1/seiten/static/connector/style.css',
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

  // Shell + alles andere: pass-through (network-only — Aggregat nie petralten).
});
