/**
 * player.js — Hörspiel-Player-PWA (HSP-48..55, Variante B "Regal").
 *
 * Ein Front-End, das per window.__HSP_INSTANZEN__ (HSP-49, Track-A2-Injektion)
 * zwischen mehreren Kind-Instanzen umschaltet. Auth = PUBLIC (AUTH-6): KEIN
 * Authorization:tma / initData-Header — die HSP-Datenrouten sind öffentlich.
 *
 * Screens (SPA, kein Reload):
 *   - Regal        (HSP-48): 2-spaltiges Kachel-Raster + Sticky-Mini-Player.
 *   - Voller Player(HSP-52): großes Cover, Play/Skip, −15/+15s, Kapitel-Liste.
 *   - Settings     (HSP-34/50): Regler + PATCH /config, kein Schloss/PIN.
 *
 * Offline-Cache (HSP-54): Page-Context Cache API. Beim Laden + Kind-Wechsel
 *   werden die Audio-Tracks (+Cover) der jüngsten N=3 Folgen je aktivem Kind
 *   HART precacht (nicht lazy), LRU-Eviction je kind-Namensraum. Wiedergabe:
 *   caches.match(trackUrl) → Treffer → URL.createObjectURL(blob), sonst Netz.
 *   MP3 immutable (HSP-37) → kein Revalidate nötig.
 *
 * Bedienung: reines Tippen (HSP-19..21) — kein Wisch/Long-Press/Multi-Touch.
 *
 * Testbarkeit: die reinen Helfer, die Cache-API-Logik und die API-Wrapper
 *   sind über module.exports exponiert (vanilla node:test, kein jsdom/npm).
 */

'use strict';

/* ══════════════════════════════════════════════════════════════════
   KONSTANTEN
   ══════════════════════════════════════════════════════════════════ */

const CACHE_N = 3;                       // HSP-54: jüngste N=3 Folgen je Kind
const LRU_KEY = '/__hsp_lru__';          // Meta-Eintrag: LRU-Reihenfolge (Album-IDs)
const ALBUM_META_PREFIX = '/__hsp_album__/';  // Meta-Eintrag pro Album: {urls:[]}

// GAP-2 (#1320): Write-Through-Metadaten-Cache. Eigener Schlüssel-Namensraum
// im kind-Cache — von der Audio-LRU (evictAlbum) NIE angetastet, weil evictAlbum
// nur meta.urls (echte Audio-/Cover-URLs) + ALBUM_META_PREFIX-Keys löscht.
// Ohne diesen Cache wirft apiAlben offline → leeres Regal (HSP-54-Enabler).
const META_ALBEN_KEY = '/__hsp_alben__';           // gecachte Alben-Liste
const META_MANIFEST_PREFIX = '/__hsp_manifest__/'; // gecachtes Manifest pro Album
const META_CONFIG_KEY = '/__hsp_config__';         // gecachte Kind-Config

function _buildId() {
  return (typeof window !== 'undefined' && window.__HSP_BUILD_ID__) || 'dev';
}

/* ══════════════════════════════════════════════════════════════════
   REINE HELFER (exportiert, HSP-49/52)
   ══════════════════════════════════════════════════════════════════ */

/** Liste der Kind-Instanzen aus dem server-injizierten Fenster-Objekt (HSP-49). */
function instanzen() {
  if (typeof window !== 'undefined' && Array.isArray(window.__HSP_INSTANZEN__)) {
    return window.__HSP_INSTANZEN__;
  }
  return [];
}

/**
 * Aktives Kind beim Laden bestimmen (HSP-49): ?kind=<id> falls in der Liste,
 * sonst 1. Eintrag, sonst Fallback 'mia' (Dev/Standalone).
 * @param {Array} liste  window.__HSP_INSTANZEN__
 * @param {string} search  location.search (z.B. "?kind=finn")
 */
function initialKindId(liste, search) {
  const ids = (liste || []).map(i => i && i.kind_id).filter(Boolean);
  const m = (search || '').match(/[?&]kind=([^&]+)/);
  if (m) {
    const wunsch = decodeURIComponent(m[1]);
    if (ids.includes(wunsch)) return wunsch;
  }
  return ids.length > 0 ? ids[0] : 'mia';
}

/** Nächstes Kind im Ring (Umschalter iteriert die Liste, kein 2-Hardcode). */
function nextKindId(liste, currentId) {
  const ids = (liste || []).map(i => i && i.kind_id).filter(Boolean);
  if (ids.length === 0) return currentId;
  const idx = ids.indexOf(currentId);
  return ids[(idx + 1) % ids.length];
}

/** Instanz-Objekt zu einer kind_id (name/foto_url). */
function instanzFuer(liste, kindId) {
  return (liste || []).find(i => i && i.kind_id === kindId) || { kind_id: kindId, name: kindId, foto_url: null };
}

/** Initialen für den Default-Avatar (foto_url ist V1 null → Pille zeigt Initiale). */
function initialen(name) {
  const s = String(name || '').trim();
  return s ? s[0].toUpperCase() : '?';
}

/**
 * Kapitel-Label (HSP-52): der Player erzeugt KEINE eigenen Track-Namen —
 * er nutzt track.titel falls vorhanden, sonst art+position (Intro/Kapitel N/Outro).
 * @param {object} track  {art:'intro'|'inhalt'|'outro', titel?}
 * @param {number} kapNr  laufende Kapitel-Nummer (nur inhalt-Tracks zählen)
 */
function trackLabel(track, kapNr) {
  if (!track) return '';
  if (track.titel) return track.titel;
  if (track.art === 'intro') return 'Intro';
  if (track.art === 'outro') return 'Outro';
  return 'Kapitel ' + kapNr;
}

/**
 * ⏮/⏭-Deaktivierung an den Rändern (HSP-52): am ersten Track prev disabled,
 * am letzten next disabled.
 */
function skipDisabled(idx, len) {
  return { prev: idx <= 0, next: idx >= len - 1 };
}

/**
 * Auto-Advance-Entscheidung beim `ended` (EIN Element + vorgelöster Blob, #1306).
 *   'swap' — die Quelle des nächsten Tracks (trackIdx+1) ist vorab aufgelöst
 *            → synchron src+play am SELBEN ton-autorisierten Element (kein Netz-Fetch,
 *              iOS-Ton bleibt, weil dasselbe per Geste aktivierte Element weiterspielt).
 *   'load' — Vorauflösung fehlt/passt nicht → Fallback über ladeTrack (mit await, Vordergrund).
 *   'stop' — letzter Track → Wiedergabe endet.
 */
function planNext(trackIdx, len, preloadedIdx) {
  if (trackIdx >= len - 1) return 'stop';
  if (preloadedIdx === trackIdx + 1) return 'swap';
  return 'load';
}

/** Tracks stabil nach position sortieren. */
function sortTracks(tracks) {
  return [...(tracks || [])].sort((a, b) => (a.position || 0) - (b.position || 0));
}

/** Start-Index aus Resume-Track-Position (HSP-51); kein Treffer → 0. */
function resumeStartIdx(tracks, resumeTrackPos) {
  if (resumeTrackPos == null) return 0;
  const idx = sortTracks(tracks).findIndex(t => t.position === resumeTrackPos);
  return idx >= 0 ? idx : 0;
}

/** kind-getrennter Cache-Namensraum (HSP-54). */
function audioCacheName(kindId, buildId) {
  return 'hoerspiel-audio-' + kindId + '-v' + buildId;
}

/** mm:ss-Formatierung. */
function fmtZeit(sek) {
  if (!sek && sek !== 0) return '';
  const s = Math.max(0, Math.floor(sek));
  const m = Math.floor(s / 60);
  return m + ':' + String(s % 60).padStart(2, '0');
}

/** HTML-Escaping (XSS-Schutz bei innerHTML-Rendering). */
function esc(str) {
  return String(str == null ? '' : str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/* ══════════════════════════════════════════════════════════════════
   OFFLINE-CACHE — Page-Context Cache API (HSP-54)
   ══════════════════════════════════════════════════════════════════ */

async function _readJson(cache, key) {
  try {
    const r = await cache.match(key);
    if (!r) return null;
    return await r.json();
  } catch (e) { return null; }
}

function _jsonResponse(obj) {
  return new Response(JSON.stringify(obj), { headers: { 'Content-Type': 'application/json' } });
}

async function _writeJson(cache, key, obj) {
  await cache.put(key, _jsonResponse(obj));
}

/** Löscht alle URLs eines Albums + seinen Meta-Eintrag (LRU-Eviction). */
async function evictAlbum(cache, albumId) {
  const meta = await _readJson(cache, ALBUM_META_PREFIX + albumId);
  if (meta && Array.isArray(meta.urls)) {
    for (const u of meta.urls) { await cache.delete(u); }
  }
  await cache.delete(ALBUM_META_PREFIX + albumId);
}

/** URLs eines Albums = Cover + alle Track-Audio-Assets (HSP-54). */
function albumUrls(album, manifest) {
  const urls = [];
  if (album && album['cover-asset']) urls.push(album['cover-asset']);
  for (const t of ((manifest && manifest.tracks) || [])) {
    if (t['audio-asset']) urls.push(t['audio-asset']);
  }
  return urls;
}

/**
 * HART precacht EIN Album und hält den kind-Namensraum auf N Folgen (LRU).
 * Beim (N+1)-ten Album wird die am längsten nicht angefasste Folge geräumt.
 * Gibt die neue LRU-Liste (jüngste zuerst) zurück.
 */
async function precacheAlbum(cache, album, manifest, N, fetchFn) {
  fetchFn = fetchFn || (typeof fetch !== 'undefined' ? fetch : null);
  const urls = albumUrls(album, manifest);
  for (const u of urls) {
    if (await cache.match(u)) continue;   // schon da (immutable MP3, HSP-37)
    if (!fetchFn) continue;
    try {
      const r = await fetchFn(u);
      if (r && r.ok) await cache.put(u, r);
    } catch (e) { /* offline / Netzfehler → Track bleibt eben nur online spielbar */ }
  }
  await _writeJson(cache, ALBUM_META_PREFIX + album.id, { urls });

  let lru = (await _readJson(cache, LRU_KEY)) || [];
  lru = [album.id, ...lru.filter(id => id !== album.id)];
  while (lru.length > N) {
    await evictAlbum(cache, lru.pop());
  }
  await _writeJson(cache, LRU_KEY, lru);
  return lru;
}

/**
 * HART precacht die jüngsten N Folgen (HSP-54) — Reihenfolge: neueste zuerst.
 * @param {Array<{album,manifest}>} albenMitManifest  bereits jüngste-zuerst sortiert
 */
async function precacheFolgen(cache, albenMitManifest, N, fetchFn) {
  let lru = null;
  // Rückwärts einspeisen, damit die jüngste Folge am Ende die frischeste
  // LRU-Position (vorne) belegt.
  const teil = (albenMitManifest || []).slice(0, N).reverse();
  for (const e of teil) {
    lru = await precacheAlbum(cache, e.album, e.manifest, N, fetchFn);
  }
  return lru || (await _readJson(cache, LRU_KEY)) || [];
}

/**
 * Wiedergabe-Quelle auflösen (HSP-54): Cache-Treffer → Blob-Object-URL,
 * sonst die Netz-URL direkt.
 */
async function resolveTrackSrc(cache, url) {
  try {
    if (cache) {
      const hit = await cache.match(url);
      if (hit) {
        const blob = await hit.blob();
        if (typeof URL !== 'undefined' && URL.createObjectURL) {
          return URL.createObjectURL(blob);
        }
      }
    }
  } catch (e) { /* Fallback aufs Netz */ }
  return url;
}

/** Ist ein Album (nach Cover-Präsenz) offline verfügbar? Für das Offline-Badge. */
async function istGecacht(cache, album) {
  if (!cache || !album) return false;
  try {
    return !!(await cache.match(ALBUM_META_PREFIX + album.id));
  } catch (e) { return false; }
}

/* ══════════════════════════════════════════════════════════════════
   API-WRAPPER (public, HSP-48..52) — KEIN Auth-Header (AUTH-6)
   ══════════════════════════════════════════════════════════════════ */

function _base(kindId) { return '/api/v1/hoerspiel/' + encodeURIComponent(kindId); }

/**
 * GAP-2 (#1320): Metadaten-Cache des Kindes on-demand öffnen (kind-Namensraum,
 * gleiche Cache wie Audio). init() ruft apiConfigGet VOR ladeKind (das S.cache
 * öffnet), darum öffnen die Wrapper ihren Cache selbst statt S.cache zu nutzen.
 * Degradiert lautlos zu null wenn caches nicht verfügbar (SSR/Test/kein SW).
 */
async function _metaCache(kindId) {
  if (typeof caches === 'undefined' || !caches || !caches.open) return null;
  try { return await caches.open(audioCacheName(kindId, _buildId())); }
  catch (e) { return null; }
}

/**
 * Network-first mit Write-Through + Offline-cache-fallback (GAP-2).
 * Online: fetch → transform → in den Metadaten-Cache schreiben → zurück.
 * Offline/Fehler: aus dem Cache lesen; nichts gecacht → ursprünglichen Fehler
 * werfen (Aufrufer-Verträge in ladeKind/init bleiben erhalten).
 * opts: { fetch, cache } — Test-Nähte; sonst globales fetch + _metaCache.
 */
async function _networkFirstJson(url, key, kindId, errLabel, opts, transform) {
  opts = opts || {};
  const fetchFn = opts.fetch || (typeof fetch !== 'undefined' ? fetch : null);
  const cache = opts.cache !== undefined ? opts.cache : await _metaCache(kindId);
  try {
    if (!fetchFn) throw new Error(errLabel + ' kein fetch');
    const r = await fetchFn(url);
    if (!r.ok) throw new Error(errLabel + ' ' + r.status);
    const data = await r.json();
    const out = transform ? transform(data) : data;
    if (cache) { try { await _writeJson(cache, key, out); } catch (e) { /* Cache best-effort */ } }
    return out;
  } catch (e) {
    if (cache) {
      const cached = await _readJson(cache, key);
      if (cached !== null && cached !== undefined) return cached;
    }
    throw e;
  }
}

async function apiAlben(kindId, opts) {
  return _networkFirstJson(
    _base(kindId) + '/alben', META_ALBEN_KEY, kindId, 'alben', opts,
    (data) => (Array.isArray(data) ? data : []));
}

async function apiManifest(kindId, albumId, opts) {
  return _networkFirstJson(
    _base(kindId) + '/alben/' + encodeURIComponent(albumId) + '/manifest',
    META_MANIFEST_PREFIX + albumId, kindId, 'manifest', opts, null);
}

/** Resume server-seitig lesen (HSP-51); status:'neu' → null (kein Stand). */
async function apiResumeGet(kindId, albumId) {
  const r = await fetch(_base(kindId) + '/resume?album=' + encodeURIComponent(albumId));
  if (!r.ok) return null;
  const data = await r.json();
  if (data && data.status === 'neu') return null;
  return data;
}

/** Resume server-seitig setzen (HSP-51). */
async function apiResumeSet(kindId, albumId, trackPos) {
  await fetch(_base(kindId) + '/resume', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ album: albumId, track: trackPos }),
  });
}

async function apiConfigGet(kindId, opts) {
  return _networkFirstJson(
    _base(kindId) + '/config', META_CONFIG_KEY, kindId, 'config', opts, null);
}

/** Config PATCH (HSP-34). Gibt {ok,status,body} — Aufrufer toastet 422. */
async function apiConfigPatch(kindId, patch) {
  const r = await fetch(_base(kindId) + '/config', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  const body = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, body };
}

/* ══════════════════════════════════════════════════════════════════
   HTML-BAUSTEINE (rein, testbar)
   ══════════════════════════════════════════════════════════════════ */

/** Regal-Kachel (HSP-48). flags: {resume, cached}. */
function kachelHtml(album, flags) {
  flags = flags || {};
  const cover = esc(album['cover-asset'] || '');
  return '<button class="tile' + (flags.resume ? ' res' : '') + '" type="button"' +
    ' data-album-id="' + esc(album.id) + '" aria-label="' + esc(album.titel) + '">' +
    '<span class="cw">' +
      '<img class="cover" src="' + cover + '" alt="" onerror="this.style.visibility=\'hidden\'">' +
      '<span class="num">Folge ' + esc(album.nummer) + '</span>' +
      (flags.resume ? '<span class="b badge resume">Weiter</span>' : '') +
      (flags.cached ? '<span class="b badge cached">offline</span>' : '') +
    '</span>' +
    '<span class="t">' + esc(album.titel) + '</span>' +
  '</button>';
}

/** Kapitel-Zeilen (HSP-52): antippbar, aktiver hervorgehoben. */
function chapterRowsHtml(tracks, activeIdx) {
  const sorted = sortTracks(tracks);
  let kap = 0;
  return sorted.map((t, i) => {
    if (t.art === 'inhalt') kap++;
    const dur = t['dauer-sek'] ? fmtZeit(t['dauer-sek']) : '—';
    return '<button class="chrow' + (i === activeIdx ? ' active' : '') + '" type="button"' +
      ' data-track-idx="' + i + '" role="listitem">' +
      '<span class="cidx">' + (i + 1) + '</span>' +
      '<span class="cname">' + esc(trackLabel(t, kap)) + '</span>' +
      '<span class="cdur">' + esc(dur) + '</span>' +
    '</button>';
  }).join('');
}

/** Track-Anzeige "Track X/Y · Label" (HSP-52). */
function trackAnzeige(tracks, idx) {
  const sorted = sortTracks(tracks);
  let kap = 0;
  for (let i = 0; i <= idx && i < sorted.length; i++) {
    if (sorted[i].art === 'inhalt') kap++;
  }
  const t = sorted[idx];
  return 'Track ' + (idx + 1) + '/' + sorted.length + ' · ' + trackLabel(t, kap);
}

/**
 * Welches Kind wird im player-kid-Label (voller Player) angezeigt?
 * Läuft ein Fremd-Album (aktivKindId != kindId), zeigt das Label den Eigentümer.
 * Bei eigenem Album oder leerem aktivKindId bleibt das Regal-Kind.
 * Rein/testbar (AC1, HSP-48/49).
 */
function labelKindId(kindId, aktivKindId) {
  return (aktivKindId && aktivKindId !== kindId) ? aktivKindId : kindId;
}

/**
 * Now-Playing-Entscheidung für den Mini-Player (Bug 1/2, HSP-48). Rein/testbar.
 * Läuft gerade ein Album (aktivAlbum + Audio vorhanden), ist der Mini der GLOBALE
 * Now-Playing-Banner ("was läuft gerade") — unabhängig vom angezeigten Kind-Regal.
 * Sonst mode:'resume' → Aufrufer fällt auf die resume-basierte Kind-Logik zurück.
 * @returns {{mode:'now',cover,title,sub,albumId}|{mode:'resume'}}
 */
function miniNowPlaying(aktivAlbum, hasAudio, playing, trackIdx, tracks) {
  if (aktivAlbum && hasAudio) {
    return {
      mode: 'now',
      cover: aktivAlbum['cover-asset'] || '',
      title: aktivAlbum.titel || '',
      sub: playing ? 'Spielt gerade' : ('Weiter hören · Folge ' + aktivAlbum.nummer),
      albumId: aktivAlbum.id,
    };
  }
  return { mode: 'resume' };
}

/**
 * Tap-Guard (Bug 3, HSP-52): Ist das getippte Album genau das gerade laufende
 * (aktivAlbum + lebendes Audio)? Dann NICHT neu laden — nur den Player zeigen,
 * Wiedergabe läuft ungestört weiter.
 */
function istLaufendesAlbum(aktivAlbum, hasAudio, albumId) {
  return !!(aktivAlbum && hasAudio && aktivAlbum.id === albumId);
}

/* ══════════════════════════════════════════════════════════════════
   MEDIASESSION (HSP-22) — Muster aus alben.js:512-529
   ══════════════════════════════════════════════════════════════════ */

function setupMediaSession(handlers) {
  if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return false;
  navigator.mediaSession.setActionHandler('play', handlers.play);
  navigator.mediaSession.setActionHandler('pause', handlers.pause);
  navigator.mediaSession.setActionHandler('previoustrack', handlers.prev);
  navigator.mediaSession.setActionHandler('nexttrack', handlers.next);
  return true;
}

function updateMediaSession(album, track, playing) {
  if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return;
  if (typeof MediaMetadata === 'undefined') return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: track && track.titel ? track.titel : (album ? 'Folge ' + album.nummer : ''),
    artist: album && album.voice ? 'Stigi & Co. (' + album.voice + ')' : 'Stigi & Co.',
    album: album ? ('Folge ' + album.nummer + ': ' + album.titel) : '',
    artwork: album && album['cover-asset']
      ? [{ src: album['cover-asset'], sizes: '512x512', type: 'image/jpeg' }] : [],
  });
  navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
}

/* ══════════════════════════════════════════════════════════════════
   BROWSER-LAUFZEIT (SPA-Wiring) — nur im DOM aktiv
   ══════════════════════════════════════════════════════════════════ */

const S = {
  liste: [],
  kindId: 'mia',
  alben: [],
  cache: null,
  aktivAlbum: null,      // {..album, tracks:[]}
  aktivKindId: null,     // Kind, dem das laufende Album gehört (bleibt beim Kind-Toggle stabil)
  tracks: [],
  trackIdx: 0,
  audio: null,           // EINZIGES, ton-autorisiertes Audio-Element (#1306, iOS-Ton)
  preloadedIdx: null,    // Track-Index, dessen Quelle vorab aufgelöst ist
  preloadedSrc: null,    // vorab aufgelöste Object-URL (oder Netz-URL) des nächsten Tracks
  playing: false,
  cfg: {},
  cfgEdit: {},
};

function $(id) { return document.getElementById(id); }

function zeigeScreen(name) {
  ['regal', 'player', 'settings'].forEach(n => {
    const el = $('screen-' + n);
    if (el) el.classList.toggle('aktiv', n === name);
  });
}

function toast(msg, fehler) {
  const el = $('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'toast sichtbar' + (fehler ? ' fehler' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.className = 'toast'; }, 4000);
}

/* ── Regal ──────────────────────────────────────────────────────── */

async function ladeKind(kindId) {
  S.kindId = kindId;
  const inst = instanzFuer(S.liste, kindId);
  // Pille
  const face = $('pille-face');
  if (face) {
    face.textContent = '';
    if (inst.foto_url) {
      const img = document.createElement('img');
      img.src = inst.foto_url; img.alt = '';
      face.appendChild(img);
    } else {
      face.textContent = initialen(inst.name);
    }
  }
  if ($('pille-name')) $('pille-name').textContent = inst.name;
  if ($('pille-swap')) $('pille-swap').style.display = S.liste.length > 1 ? '' : 'none';
  if ($('regal-label')) $('regal-label').textContent = inst.name + 's Folgen';
  if ($('settings-sub')) $('settings-sub').textContent = inst.name + ' · für Eltern';

  // Cache-Namensraum je Kind (HSP-54)
  if (typeof caches !== 'undefined') {
    try { S.cache = await caches.open(audioCacheName(kindId, _buildId())); }
    catch (e) { S.cache = null; }
  }

  // Alben laden (jüngste zuerst)
  let alben = [];
  try { alben = await apiAlben(kindId); }
  catch (e) { toast(inst.name + 's Folgen konnten nicht geladen werden.', true); }
  S.alben = alben.slice().sort((a, b) => (b.nummer || 0) - (a.nummer || 0));

  await rendereRegal();
  await syncMini();  // Bug 1/2: läuft was → Now-Playing-Banner, sonst resume-basiert
  hartPrecache();   // HSP-54: jüngste N=3 hart precachen (fire-and-forget)
}

async function rendereRegal() {
  const grid = $('grid');
  if (!grid) return;
  if (S.alben.length === 0) {
    grid.innerHTML = '<div class="leer-hinweis">Noch keine Folgen da.<br>Neue Folgen entstehen im Eltern-Chat.</div>';
    return;
  }
  // Resume- + Offline-Flags parallel ermitteln.
  const flags = await Promise.all(S.alben.map(async (a) => {
    const r = await apiResumeGet(S.kindId, a.id).catch(() => null);
    const cached = await istGecacht(S.cache, a);
    return { resume: !!(r && r.track != null), cached };
  }));
  grid.innerHTML = S.alben.map((a, i) => kachelHtml(a, flags[i])).join('');
  grid.querySelectorAll('.tile[data-album-id]').forEach(el => {
    el.addEventListener('click', () => oeffneAlbum(el.dataset.albumId));
  });
}

/**
 * Setzt das src eines Cover-<img> mit Fallback: bei Ladefehler (offline/404)
 * wird das Element versteckt (kein kaputtes Bild-Icon). Vor dem Setzen wird
 * visibility zurückgesetzt, damit ein späteres erfolgreiches Cover wieder
 * erscheint (Kind-Wechsel, anderes Album). Analog Regal-Kachel (player.js:373).
 */
function _setCoverSrc(el, src) {
  el.style.visibility = '';
  el.onerror = function () { el.style.visibility = 'hidden'; };
  el.src = src;
}

async function initMini() {
  const mini = $('mini');
  if (!mini) return;
  // Jüngste Folge mit Resume-Stand → Mini-Player.
  for (const a of S.alben) {
    const r = await apiResumeGet(S.kindId, a.id).catch(() => null);
    if (r && r.track != null) {
      const mc = $('mini-cover'); if (mc) _setCoverSrc(mc, a['cover-asset'] || '');
      if ($('mini-title')) $('mini-title').textContent = a.titel;
      if ($('mini-sub')) $('mini-sub').textContent = 'Weiter hören · Folge ' + a.nummer;
      mini.classList.remove('hidden');
      mini.onclick = () => oeffneAlbum(a.id);
      return;
    }
  }
  mini.classList.add('hidden');
}

/**
 * Mini-Player als "was läuft gerade" rendern (Bug 1/2, HSP-48).
 * Sichtbar sobald ein Album aktiv/geladen ist — GLOBAL, unabhängig vom gerade
 * angezeigten Kind-Regal. Tap öffnet den vollen Player OHNE Reload (Bug 3).
 * Läuft nichts → resume-basierter Fallback fürs aktive Kind (initMini).
 */
function syncMini() {
  const mini = $('mini');
  if (!mini) return;
  const m = miniNowPlaying(S.aktivAlbum, !!S.audio, S.playing, S.trackIdx, S.tracks);
  if (m.mode === 'now') {
    const mc = $('mini-cover'); if (mc) _setCoverSrc(mc, m.cover);
    if ($('mini-title')) $('mini-title').textContent = m.title;
    if ($('mini-sub')) $('mini-sub').textContent = m.sub;
    mini.classList.remove('hidden');
    mini.onclick = () => oeffneAlbum(m.albumId);
    return;
  }
  return initMini();  // nichts läuft → resume-basiert (async)
}

function hartPrecache() {
  if (!S.cache) return;
  const jung = S.alben.slice(0, CACHE_N);
  Promise.all(jung.map(async (a) => {
    try { return { album: a, manifest: await apiManifest(S.kindId, a.id) }; }
    catch (e) { return null; }
  })).then(list => {
    const gut = list.filter(Boolean);
    if (gut.length) precacheFolgen(S.cache, gut, CACHE_N).catch(() => {});
  }).catch(() => {});
}

/* ── Voller Player (HSP-52) ─────────────────────────────────────── */

async function oeffneAlbum(albumId) {
  // Bug 3: läuft dieses Album schon (Tap auf Mini/Kachel des Now-Playing)?
  // → NUR den Player zeigen, Audio NICHT neu laden — Wiedergabe läuft weiter.
  if (istLaufendesAlbum(S.aktivAlbum, S.audio, albumId)) {
    renderedPlayer(false);
    zeigeScreen('player');
    syncMini();
    return;
  }

  const album = S.alben.find(a => a.id === albumId);
  if (!album) return;
  let manifest;
  try { manifest = await apiManifest(S.kindId, albumId); }
  catch (e) { toast('Folge konnte nicht geladen werden.', true); return; }

  S.aktivAlbum = Object.assign({}, album, manifest);
  S.aktivKindId = S.kindId;   // Kind merken → Resume-Writes bleiben nach Kind-Toggle korrekt
  S.tracks = sortTracks(manifest.tracks || []);

  const resume = await apiResumeGet(S.kindId, albumId).catch(() => null);
  S.trackIdx = resumeStartIdx(S.tracks, resume ? resume.track : null);

  // Auf Abruf sicherstellen, dass diese (evtl. ältere) Folge gecacht ist (LRU).
  if (S.cache) precacheAlbum(S.cache, album, manifest, CACHE_N).catch(() => {});

  renderedPlayer(!!(resume && resume.track != null));
  zeigeScreen('player');
  await ladeTrack(S.trackIdx, false);
}

function renderedPlayer(istResume) {
  const inst = instanzFuer(S.liste, labelKindId(S.kindId, S.aktivKindId));
  if ($('player-kid')) $('player-kid').textContent = inst.name;
  const pc = $('player-cover'); if (pc) _setCoverSrc(pc, S.aktivAlbum['cover-asset'] || '');
  if ($('player-title')) $('player-title').textContent = S.aktivAlbum.titel || '';
  if ($('player-meta')) {
    $('player-meta').textContent = 'Folge ' + S.aktivAlbum.nummer + ' · ' +
      S.tracks.length + ' Kapitel · Stimme ' + (S.aktivAlbum.voice || '—');
  }
  const badge = $('player-nowbadge');
  if (badge) {
    if (istResume) { badge.textContent = 'Weiter · ' + trackAnzeige(S.tracks, S.trackIdx); badge.classList.remove('hidden'); }
    else { badge.classList.add('hidden'); }
  }
  const chap = $('player-chapters');
  if (chap) {
    chap.innerHTML = chapterRowsHtml(S.tracks, S.trackIdx);
    chap.querySelectorAll('.chrow[data-track-idx]').forEach(el => {
      el.addEventListener('click', () => ladeTrack(parseInt(el.dataset.trackIdx, 10), true));
    });
  }
  aktualisiereRandDisabled();
}

function aktualisiereRandDisabled() {
  const d = skipDisabled(S.trackIdx, S.tracks.length);
  if ($('player-prev')) $('player-prev').disabled = d.prev;
  if ($('player-next')) $('player-next').disabled = d.next;
  if ($('player-prevkap')) $('player-prevkap').disabled = d.prev;
  if ($('player-nextkap')) $('player-nextkap').disabled = d.next;
}

/**
 * Quelle an EIN Element hängen und die alte Blob-Object-URL freigeben (#1304).
 * resolveTrackSrc erzeugt pro Aufruf eine frische createObjectURL — ohne Revoke
 * leckt jeder Track-Wechsel einen Blob. Wir merken die zuletzt gesetzte Blob-URL
 * je Element (el._objUrl) und geben sie beim nächsten Wechsel frei.
 */
function setAudioSrc(el, src) {
  if (!el) return;
  if (el._objUrl && el._objUrl !== src) {
    try { if (typeof URL !== 'undefined' && URL.revokeObjectURL) URL.revokeObjectURL(el._objUrl); }
    catch (e) { /* revoke best effort */ }
    el._objUrl = null;
  }
  el.src = src;
  if (typeof src === 'string' && src.indexOf('blob:') === 0) el._objUrl = src;
}

/** Lockscreen-Scrubber (HSP-22) mit der aktuellen aktiven Element-Dauer, best effort. */
function updatePositionState() {
  try {
    const a = S.audio;
    if (a && typeof navigator !== 'undefined' && navigator.mediaSession &&
        navigator.mediaSession.setPositionState && isFinite(a.duration) && a.duration > 0) {
      navigator.mediaSession.setPositionState({
        duration: a.duration,
        playbackRate: a.playbackRate || 1,
        position: Math.min(a.currentTime || 0, a.duration),
      });
    }
  } catch (e) { /* setPositionState nicht überall verfügbar */ }
}

/* Handler-Fabrik für das EINE Audio-Element (#1306). Kein ev.target-Guard nötig,
   weil es nur ein ton-produzierendes Element gibt — Doppelfeuer ist strukturell
   ausgeschlossen. Listener werden trotzdem genau einmal angehängt (ensureAudio). */
function _onTimeupdate() {
  const audio = S.audio;
  if (audio && audio.duration > 0) {
    const pct = (audio.currentTime / audio.duration * 100).toFixed(1) + '%';
    if ($('player-fill')) $('player-fill').style.width = pct;
    if ($('mini-fill')) $('mini-fill').style.width = pct;
    updatePositionState();
  }
}
function _onPlay() {
  S.playing = true; syncPlayIcon();
  const track = S.tracks[S.trackIdx];
  if (S.aktivAlbum && track) {
    // Resume-Write ans EIGENTÜMER-Kind (nicht ans evtl. umgeschaltete S.kindId).
    apiResumeSet(S.aktivKindId || S.kindId, S.aktivAlbum.id, track.position).catch(() => {});
    updateMediaSession(S.aktivAlbum, track, true);
  }
  syncMini();
}
function _onPause() {
  S.playing = false; syncPlayIcon(); syncMini();
}
function _onEnded() {
  const plan = planNext(S.trackIdx, S.tracks.length, S.preloadedIdx);
  if (plan === 'swap') swapToNext();
  else if (plan === 'load') ladeTrack(S.trackIdx + 1, true);   // Vorauflösung fehlt → Vordergrund-Fallback
  else { S.playing = false; syncPlayIcon(); syncMini(); }      // letzter Track
}

function _attachAudioListeners(el) {
  el.addEventListener('timeupdate', _onTimeupdate);
  el.addEventListener('play', _onPlay);
  el.addEventListener('pause', _onPause);
  el.addEventListener('ended', _onEnded);
}

/**
 * EIN persistentes, ton-autorisiertes Audio-Element (#1306, HSP-22).
 * iOS-Safari-PWA gibt Ton NUR vom ursprünglich per User-Geste aktivierten Element
 * aus — ein geswapptes zweites Element läuft, ist aber stumm. Darum genau EIN
 * Element über die gesamte Wiedergabe. Listener werden EINMALIG angehängt.
 */
function ensureAudio() {
  if (S.audio) return S.audio;
  if (typeof Audio === 'undefined') return null;
  S.audio = new Audio();
  _attachAudioListeners(S.audio);
  return S.audio;
}

/**
 * Nächsten Track als Blob-Object-URL VORAUSLÖSEN (#1306, #1308) — KEIN zweites Element.
 * Während der aktuelle Track spielt: resolveTrackSrc prüft den Cache (HSP-54).
 *   Cache-Treffer → Blob-Object-URL direkt.
 *   Cache-Miss  → resolveTrackSrc gibt die Netz-URL zurück (kein Fetch dort);
 *                 preloadNext fetcht den Track selbst (fetch→blob→objectURL),
 *                 damit S.preloadedSrc immer eine Blob-Object-URL ist und
 *                 swapToNext netzfrei bleibt. Kein Cache-Write (HSP-54-Budget).
 * Eine noch nicht verbrauchte, veraltete Vorauflösung wird revoked (Leak-Härtung).
 * @param {number}   idx       Track-Index in S.tracks
 * @param {Function} [_fetchFn] Test-Nähe: fetch-Ersatz; sonst globales fetch
 */
async function preloadNext(idx, _fetchFn) {
  if (idx < 0 || idx >= S.tracks.length) { _revokePreload(); S.preloadedIdx = null; return; }
  const track = S.tracks[idx];
  const url = track['audio-asset'];
  let src = await resolveTrackSrc(S.cache, url);   // async VORAB (während Wiedergabe)

  // Cache-Miss: resolveTrackSrc gibt die Netz-URL zurück (kein Fetch dort).
  // Hier vorab fetchen → Blob → Object-URL, damit swapToNext immer netzfrei bleibt.
  if (src === url) {
    try {
      const doFetch = _fetchFn || (typeof fetch !== 'undefined' ? fetch : null);
      if (doFetch && typeof URL !== 'undefined' && URL.createObjectURL) {
        const resp = await doFetch(url);
        if (resp.ok) {
          const blob = await resp.blob();
          src = URL.createObjectURL(blob);
          // Kein Cache-Write: S.preloadedSrc (blob:-URL) reicht für netzfreies swapToNext.
          // Ein Write-Through ohne Album-Meta/LRU_KEY würde HSP-54-Budget-Waisen erzeugen.
        }
      }
    } catch (e) { /* Netz nicht erreichbar → Fallback bleibt Netz-URL */ }
  }

  if (S.preloadedSrc !== src) _revokePreload();   // alte, nicht verbrauchte Vorauflösung freigeben
  S.preloadedSrc = src;
  S.preloadedIdx = idx;
}

/** Noch nicht ans Element übergebene Vorauflösungs-Blob-URL freigeben (#1306). */
function _revokePreload() {
  const s = S.preloadedSrc;
  if (typeof s === 'string' && s.indexOf('blob:') === 0) {
    try { if (typeof URL !== 'undefined' && URL.revokeObjectURL) URL.revokeObjectURL(s); }
    catch (e) { /* revoke best effort */ }
  }
  S.preloadedSrc = null;
}

/**
 * SWAP-Pfad des Auto-Advance (#1306): SYNCHRON die vorgelöste Quelle am SELBEN
 * ton-autorisierten Element setzen und abspielen — KEIN await vor play(), damit
 * der play()-Aufruf am Media-`ended`-Event hängt (Hintergrund-Autoplay-Erlaubnis)
 * und iOS den Ton behält (selbes per-Geste-aktiviertes Element). MediaSession
 * bleibt über den Übergang 'playing'.
 */
function swapToNext() {
  const src = S.preloadedSrc;
  if (src == null) { ladeTrack(S.trackIdx + 1, true); return; }   // Vorauflösung fehlt → Fallback
  const nextIdx = S.trackIdx + 1;
  const track = S.tracks[nextIdx];

  // SYNCHRON am selben Element: src (revoked die alte Track-Blob-URL, trackt die neue) + play().
  setAudioSrc(S.audio, src);
  S.audio.playbackRate = S.cfg.playback_tempo || 1.0;
  // Vorauflösung ist verbraucht — gehört jetzt S.audio._objUrl; nicht doppelt revoken.
  S.preloadedSrc = null;
  S.preloadedIdx = null;
  S.trackIdx = nextIdx;

  // MediaSession-Hold: Metadata neu, playbackState bleibt 'playing' (kein Paused-Flackern).
  updateMediaSession(S.aktivAlbum, track, true);
  try { if (S.audio.play) S.audio.play(); } catch (e) { /* Hintergrund/iOS kann ablehnen */ }

  // Kapitel-Hervorhebung + Rand-Disabled.
  const chap = $('player-chapters');
  if (chap) chap.querySelectorAll('.chrow').forEach((el, i) => el.classList.toggle('active', i === S.trackIdx));
  aktualisiereRandDisabled();
  syncMini();
  updatePositionState();

  // Übernächsten Track vorab auflösen.
  preloadNext(S.trackIdx + 1);
}

/**
 * Autoritativer Lade-Pfad für Kapitel-Tap/⏮⏭/Direktsprung/Resume (#1306).
 * Setzt Quelle + play() am EINEN Element und löst danach den nächsten Track vorab
 * auf (S.preloadedSrc), damit das folgende `ended` wieder synchron swappen kann.
 */
async function ladeTrack(idx, autoplay) {
  if (idx < 0 || idx >= S.tracks.length) return;
  S.trackIdx = idx;
  const track = S.tracks[idx];

  const audio = ensureAudio();
  if (!audio) return;
  const src = await resolveTrackSrc(S.cache, track['audio-asset']);
  setAudioSrc(S.audio, src);
  S.audio.playbackRate = S.cfg.playback_tempo || 1.0;

  // Kapitel-Hervorhebung + Rand-Disabled aktualisieren.
  const chap = $('player-chapters');
  if (chap) {
    chap.querySelectorAll('.chrow').forEach((el, i) => el.classList.toggle('active', i === idx));
  }
  aktualisiereRandDisabled();
  updateMediaSession(S.aktivAlbum, track, autoplay);
  syncMini();

  if (autoplay) { try { await S.audio.play(); } catch (e) {} }

  // Puffer fürs nächste `ended` warm halten (auch bei manueller Navigation).
  preloadNext(idx + 1);
}

function syncPlayIcon() {
  const p = document.querySelector('#player-play .ico-play');
  const q = document.querySelector('#player-play .ico-pause');
  if (p) p.classList.toggle('hidden', S.playing);
  if (q) q.classList.toggle('hidden', !S.playing);
}

function togglePlay() {
  if (!S.audio) { ladeTrack(S.trackIdx, true); return; }
  if (S.playing) S.audio.pause();
  else S.audio.play().catch(() => {});
}

/* ── Settings (HSP-34/50) ───────────────────────────────────────── */

async function oeffneSettings() {
  zeigeScreen('settings');
  const list = $('settings-list');
  if (!list) return;
  list.innerHTML = '<div class="leer-hinweis">Lädt …</div>';
  let cfg;
  try { cfg = await apiConfigGet(S.kindId); }
  catch (e) { list.innerHTML = '<div class="leer-hinweis">Einstellungen konnten nicht geladen werden.</div>'; return; }
  S.cfg = cfg;
  S.cfgEdit = {
    playback_tempo: cfg.playback_tempo ?? 1.0,
    pause_absatz_sek: cfg.pause_absatz_sek ?? 0.55,
    pause_titel_sek: cfg.pause_titel_sek ?? 1.8,
    default_voice: cfg.default_voice ?? 'shimmer',
    llm_provider: cfg.llm_provider ?? 'claude',
    llm_model: cfg.llm_model ?? '',
  };
  rendereSettings(cfg);
}

function rendereSettings(cfg) {
  const list = $('settings-list');
  const voices = cfg.voices_verfuegbar || ['shimmer', 'onyx'];
  const provider = cfg.provider_verfuegbar || [];
  const modelle = cfg.modelle_je_anbieter || {};
  const e = S.cfgEdit;

  const voiceChips = voices.map(v =>
    '<button class="chip' + (v === e.default_voice ? ' on' : '') + '" type="button" data-voice="' + esc(v) + '">' +
    esc(v.charAt(0).toUpperCase() + v.slice(1)) + '</button>').join('');
  const provOpts = provider.map(p =>
    '<option value="' + esc(p) + '"' + (p === e.llm_provider ? ' selected' : '') + '>' + esc(p) + '</option>').join('');
  const modOpts = (modelle[e.llm_provider] || []).map(m =>
    '<option value="' + esc(m.id) + '"' + (m.id === e.llm_model ? ' selected' : '') + '>' + esc(m.label) + '</option>').join('');

  list.innerHTML =
    '<div class="setcard"><div class="lab">Playback-Tempo <span class="val" id="v-tempo">' + Number(e.playback_tempo).toFixed(2) + '×</span></div>' +
      '<input type="range" id="s-tempo" min="0.7" max="1.3" step="0.05" value="' + esc(e.playback_tempo) + '"></div>' +
    '<div class="setcard"><div class="lab">Pause nach Absatz <span class="val" id="v-absatz">' + Number(e.pause_absatz_sek).toFixed(2) + ' s</span></div>' +
      '<input type="range" id="s-absatz" min="0" max="2" step="0.05" value="' + esc(e.pause_absatz_sek) + '"></div>' +
    '<div class="setcard"><div class="lab">Pause nach Titel <span class="val" id="v-titel">' + Number(e.pause_titel_sek).toFixed(1) + ' s</span></div>' +
      '<input type="range" id="s-titel" min="0.5" max="3" step="0.1" value="' + esc(e.pause_titel_sek) + '"></div>' +
    '<div class="setcard"><div class="lab">Stimme</div><div class="twochip" id="voice-chips">' + voiceChips + '</div></div>' +
    (provider.length ?
      '<div class="setcard"><div class="lab">Vorlese-KI <span class="val">Anbieter + Modell</span></div>' +
        '<select id="s-provider">' + provOpts + '</select>' +
        '<select id="s-model" style="margin-top:10px">' + modOpts + '</select></div>' : '');

  const markDirty = () => { if ($('settings-save')) $('settings-save').disabled = false; };
  const bindSlider = (id, valId, feld, suffix, digits) => {
    const s = $(id);
    if (!s) return;
    s.addEventListener('input', () => {
      const v = parseFloat(s.value);
      S.cfgEdit[feld] = v;
      if ($(valId)) $(valId).textContent = v.toFixed(digits) + suffix;
      markDirty();
    });
  };
  bindSlider('s-tempo', 'v-tempo', 'playback_tempo', '×', 2);
  bindSlider('s-absatz', 'v-absatz', 'pause_absatz_sek', ' s', 2);
  bindSlider('s-titel', 'v-titel', 'pause_titel_sek', ' s', 1);

  const vc = $('voice-chips');
  if (vc) vc.addEventListener('click', ev => {
    const b = ev.target.closest('.chip[data-voice]'); if (!b) return;
    S.cfgEdit.default_voice = b.dataset.voice;
    vc.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c.dataset.voice === b.dataset.voice));
    markDirty();
  });
  const sp = $('s-provider');
  if (sp) sp.addEventListener('change', () => {
    S.cfgEdit.llm_provider = sp.value;
    const opts = (modelle[sp.value] || []);
    if ($('s-model')) {
      $('s-model').innerHTML = opts.map(m => '<option value="' + esc(m.id) + '">' + esc(m.label) + '</option>').join('');
      S.cfgEdit.llm_model = opts.length ? opts[0].id : '';
    }
    markDirty();
  });
  const sm = $('s-model');
  if (sm) sm.addEventListener('change', () => { S.cfgEdit.llm_model = sm.value; markDirty(); });
  if ($('settings-save')) $('settings-save').disabled = true;
}

async function speichereSettings() {
  const btn = $('settings-save');
  if (btn) btn.disabled = true;
  const felder = ['playback_tempo', 'pause_absatz_sek', 'pause_titel_sek', 'default_voice', 'llm_provider', 'llm_model'];
  const patch = {};
  for (const k of felder) {
    if (String(S.cfgEdit[k]) !== String(S.cfg[k])) patch[k] = S.cfgEdit[k];
  }
  if (Object.keys(patch).length === 0) return;
  const res = await apiConfigPatch(S.kindId, patch);
  if (!res.ok) {
    const msg = res.body && (res.body.fehler || res.body.error) || ('Fehler ' + res.status);
    toast(msg, true);           // 422 → Toast (HSP-34)
    if (btn) btn.disabled = false;
    return;
  }
  S.cfg = res.body;
  if (patch.playback_tempo != null) {
    // Tempo am EINEN Element; der nächste Swap übernimmt es via S.cfg.playback_tempo (#1306).
    if (S.audio) S.audio.playbackRate = patch.playback_tempo;
  }
  toast('✓ Gespeichert.');
}

/* ── Init ───────────────────────────────────────────────────────── */

function bindStatisch() {
  const on = (id, ev, fn) => { const el = $(id); if (el) el.addEventListener(ev, fn); };
  on('pille', 'click', () => ladeKind(nextKindId(S.liste, S.kindId)));
  on('btn-settings', 'click', oeffneSettings);
  on('settings-back', 'click', () => { zeigeScreen('regal'); syncMini(); });
  on('settings-save', 'click', speichereSettings);
  on('player-back', 'click', () => { zeigeScreen('regal'); syncMini(); });
  on('player-play', 'click', togglePlay);
  on('player-prev', 'click', () => ladeTrack(S.trackIdx - 1, true));
  on('player-next', 'click', () => ladeTrack(S.trackIdx + 1, true));
  on('player-prevkap', 'click', () => ladeTrack(S.trackIdx - 1, true));
  on('player-nextkap', 'click', () => ladeTrack(S.trackIdx + 1, true));
  on('player-minus15', 'click', () => { if (S.audio) S.audio.currentTime = Math.max(0, S.audio.currentTime - 15); });
  on('player-plus15', 'click', () => { if (S.audio && S.audio.duration) S.audio.currentTime = Math.min(S.audio.duration, S.audio.currentTime + 15); });

  setupMediaSession({
    play: () => { if (S.audio) S.audio.play().catch(() => {}); },
    pause: () => { if (S.audio) S.audio.pause(); },
    prev: () => ladeTrack(S.trackIdx - 1, true),
    next: () => ladeTrack(S.trackIdx + 1, true),
  });
}

async function init() {
  S.liste = instanzen();
  bindStatisch();
  const kindId = initialKindId(S.liste, typeof location !== 'undefined' ? location.search : '');
  // Config des aktiven Kindes vorab für playback_tempo.
  try { S.cfg = await apiConfigGet(kindId); } catch (e) { S.cfg = {}; }
  await ladeKind(kindId);
}

if (typeof document !== 'undefined' && document.addEventListener) {
  document.addEventListener('DOMContentLoaded', init);
}

/* ══════════════════════════════════════════════════════════════════
   EXPORTS (node:test — kein jsdom/npm)
   ══════════════════════════════════════════════════════════════════ */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    // reine Helfer
    instanzen, initialKindId, nextKindId, instanzFuer, initialen,
    trackLabel, skipDisabled, planNext, sortTracks, resumeStartIdx, audioCacheName, fmtZeit, esc,
    // Cache-API (HSP-54)
    CACHE_N, LRU_KEY, ALBUM_META_PREFIX, albumUrls,
    precacheAlbum, precacheFolgen, evictAlbum, resolveTrackSrc, istGecacht,
    // Metadaten-Write-Through-Cache (GAP-2, #1320)
    META_ALBEN_KEY, META_MANIFEST_PREFIX, META_CONFIG_KEY,
    // API-Wrapper
    apiAlben, apiManifest, apiResumeGet, apiResumeSet, apiConfigGet, apiConfigPatch,
    // HTML-Bausteine
    kachelHtml, chapterRowsHtml, trackAnzeige,
    // MediaSession
    setupMediaSession, updateMediaSession,
    // Player-Verhalten (Bug 1..4, T1272-B-BUGFIX) — rein + Test-Seams
    miniNowPlaying, istLaufendesAlbum, ensureAudio, labelKindId,
    // Doppel-Puffer / Hintergrund-Auto-Advance (#1304) — rein + Test-Seams
    preloadNext, _S: S,
    // Cover-Fallback (T1272-COV)
    _setCoverSrc,
  };
}
