// sw.js — Service-Worker fuer plan-einstellungen-PWA (PLAN-35).
//
// Cache-Strategie:
//   - cache-first fuer Mantel-Assets (HTML, JS, CSS, manifest, icons).
//   - pass-through (network-only) fuer /api/v1/plan/* und /api/v1/familie/* —
//     Einstellungs-Daten duerfen NIE veralten.
//   - network-first mit Cache-Fallback fuer /_shared/icons/arasaac/*.png
//     bzw. /display/_shared/icons/arasaac/*.png (ARASAAC-Piktogramme, ICONS-5).
//
// Cache-Versionierung (reference_mini_app_cache_buster.md):
//   CACHE_NAME enthaelt einen build_id-Platzhalter, den seiten/main.py beim
//   Ausliefern via String-Substitution ersetzt. So invalidiert ein neuer
//   build_id den alten Cache (activate-Event loescht alte Namespaces).

'use strict';

// SW-BUILD-ID wird beim Ausliefern von seiten/main.py ersetzt (analog ESSEN-35).
const BUILD_ID = '__BUILD_ID__';
const CACHE_NAME = 'plan-einstellungen-pwa-' + BUILD_ID;

// Mantel-Assets, die beim install-Event gecached werden (cache-first).
const MANTEL_ASSETS = [
  '/seiten/plan/einstellungen',
  '/seiten/plan/einstellungen/',
  '/seiten/plan/einstellungen/manifest.json',
  '/seiten/plan/einstellungen/icon-192.png',
  '/seiten/plan/einstellungen/icon-512.png',
  '/seiten/plan/einstellungen/icon-maskable-512.png',
  '/api/v1/seiten/static/plan-einstellungen.js',
  '/api/v1/seiten/static/plan-einstellungen.css',
  '/api/v1/seiten/static/platform.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        MANTEL_ASSETS.map((url) =>
          cache.add(url).catch((e) => {
            // best-effort: Fehler beim Cachen blockieren den Install nicht.
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
          .filter((k) => k.startsWith('plan-einstellungen-pwa-') && k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Strategien ───────────────────────────────────────────────────────────────

function isApiCall(url) {
  // /api/v1/plan/* und /api/v1/familie/* — pass-through (network-only).
  return url.pathname.startsWith('/api/v1/plan/') ||
         url.pathname.startsWith('/api/v1/familie/') ||
         url.pathname.startsWith('/api/v1/icons/');
}

function isArasaacIcon(url) {
  // ARASAAC-Piktogramme network-first mit Cache-Fallback.
  return url.pathname.startsWith('/display/_shared/icons/arasaac/') ||
         url.pathname.startsWith('/_shared/icons/arasaac/');
}

function isMantelAsset(url) {
  // Mantel: HTML, JS, CSS, manifest, eigene Icons.
  if (url.pathname === '/seiten/plan/einstellungen' ||
      url.pathname === '/seiten/plan/einstellungen/') return true;
  if (url.pathname.startsWith('/seiten/plan/einstellungen/')) return true;
  if (url.pathname.startsWith('/api/v1/seiten/static/')) {
    // Nur unsere drei Assets — andere Mini-Apps teilen das Verzeichnis.
    return url.pathname.includes('plan-einstellungen') ||
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

  // Nur GET wird gecached. POST/PUT/PATCH/DELETE gehen immer direkt durch.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Cross-Origin nicht anfassen.
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
