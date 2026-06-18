// sw.js — Service Worker für das App-Panel (PANEL-10 PWA-Begleitdatei).
// Strategie netzwerk-bevorzugt mit Cache-Fallback — identisch zur
// Figuren-Erkennung (FIG-24 / #23): online stets die frische Version,
// offline aus dem Cache. Der Cache trägt eine minimale App-Shell, damit
// auch ein frisch installiertes Panel nach kurzem Offline-Moment lädt.

'use strict';

// HSP-42 / PANEL-13: silent.mp3 + neue app.js-Größe → Cache-Bust durch
// Versions-Bump. v5: + PANEL-11-Watchdog für displays-SSE.
const CACHE_NAME = 'app-panel-v5-panel11-watchdog';

const STATIC_ASSETS = [
  './',
  './index.html',
  '/controller/_shared/config.js',
  './app.js',
  './style.css',
  './manifest.json',
  // HSP-42 / PANEL-13 — Silent-MP3 für Sticky-Activation-Prime. Precachen,
  // damit der Prime auch beim ersten Tap zuverlässig spielt.
  './silent.mp3',
  // E-PANEL-6: Token-CSS precachen — gecachter Fall bleibt gestylt auch ohne WAN.
  // CDN-Schrift fällt dann auf System-Font-Stack (--font-sans) zurück.
  '/display/_shared/design/tokens.css',
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
