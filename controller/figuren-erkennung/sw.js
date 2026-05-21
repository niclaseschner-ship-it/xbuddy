// FIG-24 — Service Worker für die Figuren-Erkennung.
// Cached die statischen Asset-Dateien beim Install, liefert sie offline aus
// (Cache-First). config.json bleibt netzwerk-bevorzugt mit Cache-Fallback,
// weil sie per-Instanz-Daten ist (FIG-23).

'use strict';

const CACHE_NAME = 'figuren-erkennung-v1';

const STATIC_ASSETS = [
  './',
  './index.html',
  './figlib.js',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Router-Events (FIG-9) gehen immer ans Netz, nie aus dem Cache.
  if (url.pathname.endsWith('/event')) return;

  // config.json (FIG-23): netzwerk-bevorzugt, Cache als Fallback.
  if (url.pathname.endsWith('/config.json')) {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // Alles andere: cache-first für die in STATIC_ASSETS gelisteten Dateien.
  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req))
  );
});
