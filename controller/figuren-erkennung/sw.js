// FIG-24 — Service Worker für die Figuren-Erkennung.
// Strategie: netzwerk-bevorzugt mit Cache-Fallback. Online wird stets die
// frische Version geliefert (Deploy sofort sichtbar), offline aus dem Cache
// (FIG-19-Offline-Zusicherung). Der Install-Event füllt den Cache vorab,
// damit Offline schon nach dem ersten Laden trägt.

'use strict';

const CACHE_NAME = 'figuren-erkennung-v1';

const STATIC_ASSETS = [
  './',
  './index.html',
  '../_shared/config.js',
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

// Netzwerk-bevorzugt: frische Antwort holen + Cache aktualisieren; bei
// Netzwerk-Fehler aus dem Cache liefern. Für Navigationen fällt der Fallback
// zusätzlich auf die App-Shell (./index.html) zurück.
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
  // Nur GET wird vom Worker behandelt — Router-Events (FIG-9) sind POST
  // und laufen damit ohnehin direkt ans Netz.
  if (req.method !== 'GET') return;

  // Alle GET-Requests netzwerk-bevorzugt — index.html, figlib.js, Icons,
  // config.json. Damit ist ein Deploy beim nächsten Laden sofort sichtbar;
  // der Cache ist reiner Offline-Fallback (FIG-24).
  event.respondWith(networkFirst(req, req.mode === 'navigate'));
});
