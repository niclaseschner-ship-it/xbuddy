// sw.js — Service Worker für das App-Panel (PANEL-10 PWA-Begleitdatei).
// Strategie netzwerk-bevorzugt mit Cache-Fallback — identisch zur
// Figuren-Erkennung (FIG-24 / #23): online stets die frische Version,
// offline aus dem Cache. Der Cache trägt eine minimale App-Shell, damit
// auch ein frisch installiertes Panel nach kurzem Offline-Moment lädt.

'use strict';

const CACHE_NAME = 'app-panel-v1';

const STATIC_ASSETS = [
  './',
  './index.html',
  '../_shared/config.js',
  './app.js',
  './style.css',
  './manifest.json',
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

function networkFirst(req, isNavigation) {
  return fetch(req).then((res) => {
    const copy = res.clone();
    caches.open(CACHE_NAME).then((c) => c.put(req, copy));
    return res;
  }).catch(() =>
    caches.match(req).then((cached) =>
      cached || (isNavigation ? caches.match('./index.html') : undefined)
    )
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;  // Router-POST nie cachen
  event.respondWith(networkFirst(req, req.mode === 'navigate'));
});
