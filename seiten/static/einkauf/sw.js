// sw.js — Service-Worker fuer essen-einkauf-PWA (ESSEN-33..35).
//
// ESSEN-35 Cache-Strategie:
//   - cache-first fuer Mantel-Assets (HTML, JS, CSS, manifest, icons).
//   - pass-through (network-only) fuer /api/v1/essen/* — Listen-Inhalte
//     duerfen NIE veralten (Eltern wuerden sonst bereits Gekauftes erneut
//     in den Wagen legen).
//   - network-first mit Cache-Fallback fuer /_shared/icons/arasaac/*.png
//     bzw. /display/_shared/icons/arasaac/*.png (ARASAAC-Piktogramme,
//     ICONS-5).
//
// Cache-Versionierung (reference_mini_app_cache_buster.md):
//   CACHE_NAME enthaelt einen build_id-Platzhalter, den seiten/main.py beim
//   Ausliefern via String-Substitution ersetzt. So invalidiert ein neuer
//   build_id den alten Cache (activate-Event loescht alte Namespaces).

'use strict';

// SW-BUILD-ID wird beim Ausliefern von seiten/main.py ersetzt (siehe
// einkauf_asset_view + ESSEN-35). Default beim Lokal-Test: "0".
const BUILD_ID = '__BUILD_ID__';
const CACHE_NAME = 'einkauf-pwa-' + BUILD_ID;

// Mantel-Assets, die beim install-Event gecached werden (cache-first).
// Absolute Pfade — die Mini-App lebt unter mehreren URL-Praefixen
// (mit/ohne Trailing-Slash); relative Pfade waren bei ESSEN-31 ein
// 404-Bug (siehe MAD-6).
const MANTEL_ASSETS = [
  '/seiten/essen/einkauf',
  '/seiten/essen/einkauf/',
  '/seiten/essen/einkauf/manifest.json',
  '/seiten/essen/einkauf/icon-192.png',
  '/seiten/essen/einkauf/icon-512.png',
  '/seiten/essen/einkauf/icon-maskable-512.png',
  '/api/v1/seiten/static/essen-einkauf.js',
  '/api/v1/seiten/static/essen-einkauf.css',
  '/api/v1/seiten/static/platform.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      // addAll fail-fast verhindern: jedes Asset einzeln versuchen, damit ein
      // 404 (z.B. Cache-Buster-Variant auf JS) den Install nicht abbricht.
      Promise.all(
        MANTEL_ASSETS.map((url) =>
          cache.add(url).catch((e) => {
            // Mantel-Asset nicht erreichbar (z.B. Build-Drift) — best-effort.
            // Wir loggen leise, blockieren aber den Install nicht.
            // eslint-disable-next-line no-console
            console.warn('[sw] Mantel-Asset nicht gecached:', url, e);
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
          .filter((k) => k.startsWith('einkauf-pwa-') && k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Strategien ───────────────────────────────────────────────────────────────

function isApiCall(url) {
  // ESSEN-35: alle /api/v1/essen/*-Requests sind pass-through (network-only).
  return url.pathname.startsWith('/api/v1/essen/');
}

function isArasaacIcon(url) {
  // ESSEN-35: ARASAAC-Piktogramme network-first mit Cache-Fallback.
  return url.pathname.startsWith('/display/_shared/icons/arasaac/') ||
         url.pathname.startsWith('/_shared/icons/arasaac/');
}

function isMantelAsset(url) {
  // Mantel: HTML, JS, CSS, manifest, eigene Icons.
  if (url.pathname === '/seiten/essen/einkauf' ||
      url.pathname === '/seiten/essen/einkauf/') return true;
  if (url.pathname.startsWith('/seiten/essen/einkauf/')) return true;
  if (url.pathname.startsWith('/api/v1/seiten/static/')) {
    // Nur unsere drei Assets — andere Mini-Apps teilen das Verzeichnis.
    return url.pathname.includes('essen-einkauf') ||
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

function networkFirstWithCacheFallback(req) {
  return fetch(req).then((res) => {
    if (res && res.ok) {
      const copy = res.clone();
      caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
    }
    return res;
  }).catch(() => caches.match(req));
}

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // ESSEN-35: nur GET wird gecached. POST/PATCH/DELETE (z.B. abhaken) gehen
  // immer direkt durch — sonst Datenverlust nach Offline-Window.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Cross-Origin nicht anfassen — Telegram-WebView laedt z.T. Vendor-JS aus
  // telegram.org; das ist nicht unsere Sache.
  if (url.origin !== self.location.origin) return;

  if (isApiCall(url)) {
    // pass-through: Browser-Default-Fetch ohne SW-Eingriff.
    return;
  }

  if (isArasaacIcon(url)) {
    event.respondWith(networkFirstWithCacheFallback(req));
    return;
  }

  if (isMantelAsset(url)) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // Alles andere: pass-through (kein respondWith).
});
