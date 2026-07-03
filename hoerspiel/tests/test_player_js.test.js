/**
 * test_player_js.test.js — Player-Frontend (T1272-B, HSP-48..55).
 *
 * Vanilla node:test, kein jsdom/npm. player.js registriert init() nur wenn
 * `document` existiert — im Test ist document undefined, das require() ist also
 * seiteneffektfrei und exponiert die reinen Helfer + Cache-/API-Logik.
 *
 * Node 20 liefert global Response/Blob/fetch — die HSP-54-Cache-Tests laufen
 * gegen echte Response-Objekte in einer FakeCache-Attrappe.
 *
 * Deckt AC-B1 (Regal/Player/Skip/Tap), AC-B2 (Umschalter/Settings-PATCH),
 * AC-B3 (Resume GET/PUT, Offline-Cache N=3+LRU, MediaSession, PWA-Icons).
 */

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

const P = require(path.join(__dirname, '../static/player.js'));

/* ── Attrappen ──────────────────────────────────────────────────── */

// Cache-Storage-Attrappe: match/put/delete/keys über eine Map.
class FakeCache {
  constructor() { this.store = new Map(); }
  async match(url) { return this.store.has(url) ? this.store.get(url) : undefined; }
  async put(url, resp) { this.store.set(url, resp); }
  async delete(url) { return this.store.delete(url); }
  async keys() { return [...this.store.keys()].map(u => ({ url: u })); }
}

// fetch-Spy mit routen-abhängiger Antwort.
function makeFetch(router) {
  const calls = [];
  const fn = async (url, opts = {}) => {
    calls.push({ url, method: opts.method || 'GET', body: opts.body });
    const res = router(url, opts) || {};
    const status = res.status || 200;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => res.json !== undefined ? res.json : {},
      blob: async () => new Blob([res.body || 'x']),
    };
  };
  fn.calls = calls;
  return fn;
}

/* ══ AC-B1/B2: reine Helfer ═════════════════════════════════════ */

test('initialKindId: ?kind= gewinnt, sonst 1. Eintrag, sonst paula (HSP-49)', () => {
  const liste = [{ kind_id: 'paula' }, { kind_id: 'neko' }, { kind_id: 'mila' }];
  assert.equal(P.initialKindId(liste, '?kind=neko'), 'neko');
  assert.equal(P.initialKindId(liste, '?kind=unbekannt'), 'paula'); // nicht in Liste → 1.
  assert.equal(P.initialKindId(liste, ''), 'paula');
  assert.equal(P.initialKindId([], ''), 'paula'); // Fallback Standalone
});

test('nextKindId iteriert die Liste (kein 2-Hardcode, HSP-49)', () => {
  const liste = [{ kind_id: 'paula' }, { kind_id: 'neko' }, { kind_id: 'mila' }];
  assert.equal(P.nextKindId(liste, 'paula'), 'neko');
  assert.equal(P.nextKindId(liste, 'neko'), 'mila');
  assert.equal(P.nextKindId(liste, 'mila'), 'paula'); // wrap
});

test('trackLabel: titel > art+position (Player erfindet keine Namen, HSP-52)', () => {
  assert.equal(P.trackLabel({ art: 'intro' }, 0), 'Intro');
  assert.equal(P.trackLabel({ art: 'outro' }, 3), 'Outro');
  assert.equal(P.trackLabel({ art: 'inhalt' }, 2), 'Kapitel 2');
  assert.equal(P.trackLabel({ art: 'inhalt', titel: 'Am See' }, 2), 'Am See');
});

test('skipDisabled: ⏮ am ersten, ⏭ am letzten Track disabled (HSP-52)', () => {
  assert.deepEqual(P.skipDisabled(0, 6), { prev: true, next: false });
  assert.deepEqual(P.skipDisabled(3, 6), { prev: false, next: false });
  assert.deepEqual(P.skipDisabled(5, 6), { prev: false, next: true });
});

test('resumeStartIdx: Resume-Position → Track-Index, kein Treffer → 0 (HSP-51)', () => {
  const tracks = [{ position: 1 }, { position: 2 }, { position: 3 }];
  assert.equal(P.resumeStartIdx(tracks, 3), 2);
  assert.equal(P.resumeStartIdx(tracks, null), 0);
  assert.equal(P.resumeStartIdx(tracks, 99), 0);
});

test('audioCacheName: kind-getrennter Namensraum (HSP-54)', () => {
  assert.equal(P.audioCacheName('paula', '7'), 'hoerspiel-audio-paula-v7');
  assert.notEqual(P.audioCacheName('paula', '7'), P.audioCacheName('neko', '7'));
});

/* ══ AC-B1: HTML-Bausteine ══════════════════════════════════════ */

test('kachelHtml: Regal-Kachel trägt Folgen-Nr + Titel + Badges (HSP-48)', () => {
  const a = { id: 'folge-22', nummer: 22, titel: 'Der Körper-Feier-Tag', 'cover-asset': '/c.jpg' };
  const html = P.kachelHtml(a, { resume: true, cached: true });
  assert.match(html, /Folge 22/);
  assert.match(html, /Der Körper-Feier-Tag/);
  assert.match(html, /data-album-id="folge-22"/);
  assert.match(html, /badge resume/);
  assert.match(html, /badge cached/);
  // ohne Flags keine Badges
  const html2 = P.kachelHtml(a, {});
  assert.doesNotMatch(html2, /badge resume/);
});

test('chapterRowsHtml: alle Tracks, aktiver hervorgehoben (HSP-52)', () => {
  const tracks = [
    { position: 1, art: 'intro' },
    { position: 2, art: 'inhalt', 'dauer-sek': 215 },
    { position: 3, art: 'outro' },
  ];
  const html = P.chapterRowsHtml(tracks, 1);
  const rows = html.match(/class="chrow/g) || [];
  assert.equal(rows.length, 3);
  assert.match(html, /chrow active/);          // aktiver Track markiert
  assert.match(html, /data-track-idx="1"/);
  assert.match(html, /3:35/);                  // 215s → mm:ss
});

test('trackAnzeige: "Track X/Y · Label" (HSP-52)', () => {
  const tracks = [{ position: 1, art: 'intro' }, { position: 2, art: 'inhalt' }];
  assert.equal(P.trackAnzeige(tracks, 0), 'Track 1/2 · Intro');
  assert.equal(P.trackAnzeige(tracks, 1), 'Track 2/2 · Kapitel 1');
});

/* ══ AC-B3: Offline-Cache N=3 + LRU (HSP-54) ════════════════════ */

function albumMitManifest(n) {
  return {
    album: { id: 'folge-' + n, nummer: n, 'cover-asset': '/cover-' + n + '.jpg' },
    manifest: {
      tracks: [
        { position: 1, art: 'intro', 'audio-asset': '/audio/' + n + '/t1.mp3' },
        { position: 2, art: 'inhalt', 'audio-asset': '/audio/' + n + '/t2.mp3' },
      ],
    },
  };
}

test('precacheFolgen: jüngste N=3 hart im Cache, Track-URLs präsent (HSP-54, AC-B3)', async () => {
  const cache = new FakeCache();
  const fetchFn = makeFetch(() => ({ status: 200, body: 'MP3' }));
  // jüngste zuerst
  const liste = [albumMitManifest(22), albumMitManifest(21), albumMitManifest(20), albumMitManifest(19)];
  const lru = await P.precacheFolgen(cache, liste, P.CACHE_N, fetchFn);

  assert.equal(lru.length, 3, 'genau N=3 Folgen im kind-Namensraum');
  assert.deepEqual(lru, ['folge-22', 'folge-21', 'folge-20'], 'jüngste zuerst, 19 nicht mitgenommen');
  // Track-Audio-Assets der jüngsten 3 sind im Cache
  assert.ok(await cache.match('/audio/22/t2.mp3'), 'Track der Folge 22 gecacht');
  assert.ok(await cache.match('/audio/20/t1.mp3'), 'Track der Folge 20 gecacht');
  assert.ok(await cache.match('/cover-22.jpg'), 'Cover mitgecacht');
});

test('LRU: (N+1)-tes Album räumt die älteste Folge (HSP-54, AC-B3)', async () => {
  const cache = new FakeCache();
  const fetchFn = makeFetch(() => ({ status: 200, body: 'MP3' }));
  const liste = [albumMitManifest(22), albumMitManifest(21), albumMitManifest(20)];
  await P.precacheFolgen(cache, liste, P.CACHE_N, fetchFn);

  // 4. Album (folge-23) auf Abruf — folge-20 (LRU-Schlusslicht) muss weichen.
  const a4 = albumMitManifest(23);
  const lru = await P.precacheAlbum(cache, a4.album, a4.manifest, P.CACHE_N, fetchFn);

  assert.equal(lru.length, 3, 'Cap bleibt N=3');
  assert.equal(lru[0], 'folge-23', 'neuestes vorne');
  assert.ok(!lru.includes('folge-20'), 'älteste Folge aus LRU verdrängt');
  assert.equal(await cache.match('/audio/20/t1.mp3'), undefined, 'Tracks der verdrängten Folge gelöscht');
  assert.equal(await cache.match('/cover-20.jpg'), undefined, 'Cover der verdrängten Folge gelöscht');
  assert.ok(await cache.match('/audio/23/t1.mp3'), 'neue Folge gecacht');
});

test('resolveTrackSrc: Cache-Treffer → Object-URL(blob), Miss → Netz-URL (HSP-54, AC-B1)', async () => {
  const cache = new FakeCache();
  await cache.put('/audio/hit.mp3', new Response('MP3'));

  const savedURL = global.URL;
  global.URL = { createObjectURL: (b) => 'blob:mock/' + (b && b.size != null ? b.size : 'x') };
  try {
    const trefferSrc = await P.resolveTrackSrc(cache, '/audio/hit.mp3');
    assert.match(trefferSrc, /^blob:mock\//, 'Treffer wird als Blob-Object-URL gespielt');

    const missSrc = await P.resolveTrackSrc(cache, '/audio/miss.mp3');
    assert.equal(missSrc, '/audio/miss.mp3', 'Miss fällt auf die Netz-URL zurück');
  } finally {
    global.URL = savedURL;
  }
});

/* ══ AC-B3: Resume server-seitig (HSP-51) ═══════════════════════ */

test('apiResumeGet: status "neu" → null, sonst {album,track} (HSP-51)', async () => {
  const saved = global.fetch;
  try {
    global.fetch = makeFetch((url) =>
      url.includes('album=leer')
        ? { json: { album: 'leer', track: 0, status: 'neu' } }
        : { json: { album: 'folge-22', track: 3 } });
    assert.equal(await P.apiResumeGet('paula', 'leer'), null);
    const r = await P.apiResumeGet('paula', 'folge-22');
    assert.deepEqual(r, { album: 'folge-22', track: 3 });
  } finally { global.fetch = saved; }
});

test('apiResumeSet: PUT mit {album,track} an kind-getrennte Route (HSP-51)', async () => {
  const saved = global.fetch;
  try {
    const f = makeFetch(() => ({ json: { album: 'folge-22', track: 2 } }));
    global.fetch = f;
    await P.apiResumeSet('neko', 'folge-22', 2);
    const call = f.calls[0];
    assert.match(call.url, /\/api\/v1\/hoerspiel\/neko\/resume$/);
    assert.equal(call.method, 'PUT');
    assert.deepEqual(JSON.parse(call.body), { album: 'folge-22', track: 2 });
  } finally { global.fetch = saved; }
});

/* ══ AC-B2: Settings-PATCH + 422 (HSP-34) ═══════════════════════ */

test('apiConfigPatch: 422 liefert ok:false + Fehler-Body (Toast-Pfad, HSP-34)', async () => {
  const saved = global.fetch;
  try {
    global.fetch = makeFetch(() => ({ status: 422, json: { fehler: 'llm_model unbekannt' } }));
    const res = await P.apiConfigPatch('paula', { llm_model: 'x' });
    assert.equal(res.ok, false);
    assert.equal(res.status, 422);
    assert.equal(res.body.fehler, 'llm_model unbekannt');
  } finally { global.fetch = saved; }
});

test('apiAlben: baut kind-Route, gibt Array (HSP-48)', async () => {
  const saved = global.fetch;
  try {
    const f = makeFetch(() => ({ json: [{ id: 'folge-1' }] }));
    global.fetch = f;
    const alben = await P.apiAlben('mila');
    assert.match(f.calls[0].url, /\/api\/v1\/hoerspiel\/mila\/alben$/);
    assert.equal(alben.length, 1);
    // KEIN Auth-Header (AUTH-6, public)
    assert.equal(f.calls[0].method, 'GET');
  } finally { global.fetch = saved; }
});

/* ══ AC-B3: MediaSession (HSP-22) ═══════════════════════════════ */

test('setupMediaSession: registriert play/pause/prev/next (HSP-22)', () => {
  const gesetzt = {};
  const savedNav = global.navigator;
  try {
    global.navigator = {
      mediaSession: { setActionHandler: (k, fn) => { gesetzt[k] = fn; } },
    };
    const ok = P.setupMediaSession({ play: () => 'p', pause: () => 'q', prev: () => 'r', next: () => 's' });
    assert.equal(ok, true);
    assert.deepEqual(Object.keys(gesetzt).sort(), ['nexttrack', 'pause', 'play', 'previoustrack']);
    assert.equal(gesetzt.play(), 'p');
  } finally { global.navigator = savedNav; }
});

/* ══ AC-B3: PWA-Icons valide (HSP-55) ═══════════════════════════ */

test('PWA-Icons: 3 valide PNGs in korrekten Größen (HSP-55)', () => {
  const cases = [
    ['icon-192.png', 192],
    ['icon-512.png', 512],
    ['icon-maskable-512.png', 512],
  ];
  const SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  for (const [name, size] of cases) {
    const buf = fs.readFileSync(path.join(__dirname, '../static/', name));
    assert.ok(buf.subarray(0, 8).equals(SIG), name + ' hat gültige PNG-Signatur');
    // IHDR: Breite/Höhe als big-endian uint32 ab Offset 16/20
    const w = buf.readUInt32BE(16);
    const h = buf.readUInt32BE(20);
    assert.equal(w, size, name + ' Breite');
    assert.equal(h, size, name + ' Höhe');
  }
});
