// DC-16 — Service Worker für den Display-Client.
// Strategie: cache-first für Manifest und Icons (damit Install-Trigger
// und ein kurzer Netz-Aussetzer keinen White-Screen erzeugen),
// pass-through (network only) für alles andere.
// Kein Pre-Caching gerouteter Inhalte — die kommen aus dem iframe-Routing
// (DC-3) und gehören nicht in den SW-Cache (DC-16, PWA-1).

'use strict';

// #1455: Version-Bump räumt beim Deploy die alten Manifest/Icon-Caches
// (activate löscht alle Caches ≠ CACHE_NAME). Beim Ändern dieser Datei
// mitziehen — der no-store-Header (router) sorgt dafür, dass der Browser die
// neue sw.js frisch holt und den Bump sieht.
const CACHE_NAME = 'display-client-v3-1455';

// Nur die PWA-Pflicht-Assets werden gecacht — Manifest und Icons.
// Kein config.json (PWA-4: Display-Client trägt keine config.json).
// Kein Pre-Caching von Display-Inhalten (DC-3 / DC-16).
const CACHE_ASSETS = [
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CACHE_ASSETS))
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

// Cache-First für Manifest und Icons; pass-through für alles andere.
// Nur GET wird vom Worker behandelt — der SSE-Stream (DC-3) ist kein GET
// im fetch-Handler-Sinne, aber sicherheitshalber explizit ausgenommen.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  const filename = url.pathname.split('/').pop();
  const isCachedAsset = CACHE_ASSETS.some((a) => a.endsWith(filename));

  if (isCachedAsset) {
    // Cache-First: aus Cache liefern, Netz nur als Fallback.
    event.respondWith(
      caches.match(req).then((cached) => cached || fetch(req))
    );
  }
  // Alles andere: pass-through (kein event.respondWith → Browser-Standard).
});
