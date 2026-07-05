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

/* ══ T1272-B-BUGFIX: Player-Verhalten (Bug 1..4) ════════════════ */

test('miniNowPlaying: läuft was → Now-Playing-Banner (global), sonst resume-Fallback (Bug 1/2, AC-BF1)', () => {
  const album = { id: 'folge-22', nummer: 22, titel: 'Der See', 'cover-asset': '/c.jpg' };
  // Spielt gerade → "Spielt gerade", Now-Playing-Cover/Titel/Album-id.
  const spielt = P.miniNowPlaying(album, true, true, 1, [{}, {}]);
  assert.equal(spielt.mode, 'now');
  assert.equal(spielt.title, 'Der See');
  assert.equal(spielt.cover, '/c.jpg');
  assert.equal(spielt.sub, 'Spielt gerade');
  assert.equal(spielt.albumId, 'folge-22');
  // Album geladen, aber pausiert → "Weiter hören · Folge N".
  const pausiert = P.miniNowPlaying(album, true, false, 1, [{}, {}]);
  assert.equal(pausiert.mode, 'now');
  assert.equal(pausiert.sub, 'Weiter hören · Folge 22');
  // Kein Audio / kein aktives Album → resume-basierter Fallback.
  assert.equal(P.miniNowPlaying(album, false, false, 0, []).mode, 'resume');
  assert.equal(P.miniNowPlaying(null, true, false, 0, []).mode, 'resume');
});

test('istLaufendesAlbum: Tap-Guard nur beim gerade laufenden Album (Bug 3, AC-BF2)', () => {
  const album = { id: 'folge-22' };
  // Selbes Album + lebendes Audio → Guard greift (kein Reload).
  assert.equal(P.istLaufendesAlbum(album, {}, 'folge-22'), true);
  // Anderes Album → normal laden.
  assert.equal(P.istLaufendesAlbum(album, {}, 'folge-21'), false);
  // Kein Audio (nichts läuft) → normal laden.
  assert.equal(P.istLaufendesAlbum(album, null, 'folge-22'), false);
  // Kein aktives Album → normal laden.
  assert.equal(P.istLaufendesAlbum(null, {}, 'folge-22'), false);
});

// Audio-Element-Attrappe für den Doppel-Puffer: sammelt Listener je Instanz,
// erlaubt fn(ev) manuell zu feuern (ev.target-Guard testen).
function makeAudioMock() {
  const instances = [];
  const Ctor = function () {
    this.playbackRate = 1;
    this.currentTime = 0;
    this.duration = 0;
    this.src = '';
    this.preload = '';
    this._listeners = {};
    this.played = 0;
    this.loaded = 0;
    this.addEventListener = (typ, fn) => { (this._listeners[typ] = this._listeners[typ] || []).push(fn); };
    this.play = () => { this.played++; return Promise.resolve(); };
    this.load = () => { this.loaded++; };
    this.fire = (typ, target) => (this._listeners[typ] || []).forEach(fn => fn({ target: target || this }));
    instances.push(this);
  };
  Ctor.instances = instances;
  return Ctor;
}

test('ensureAudio: ZWEI persistente Elemente (aktiv+idle), Listener je Element EINMALIG (#1304, AC-BG1)', () => {
  const savedAudio = global.Audio;
  const A = makeAudioMock();
  global.Audio = A;
  P._S.audio = null; P._S.audioIdle = null;   // sauberer Startzustand
  try {
    P.ensureAudio();
    const a2 = P.ensureAudio();   // idempotent
    assert.equal(A.instances.length, 2, 'genau zwei Elemente (Doppel-Puffer), kein Neubau beim 2. Aufruf');
    assert.equal(P._S.audio, a2, 'aktiver Element-Handle stabil');
    assert.ok(P._S.audioIdle && P._S.audio !== P._S.audioIdle, 'idle ist ein separates Element');
    for (const el of A.instances) {
      for (const typ of ['timeupdate', 'play', 'pause', 'ended']) {
        assert.equal((el._listeners[typ] || []).length, 1, typ + '-Listener je Element genau einmal');
      }
    }
  } finally {
    global.Audio = savedAudio;
    P._S.audio = null; P._S.audioIdle = null;
  }
});

test('planNext: swap wenn nächster gepuffert, load bei Mismatch, stop am letzten Track (#1304, AC-BG1)', () => {
  // trackIdx 0, len 3, preloaded 1 → nächster liegt im idle-Element → swap
  assert.equal(P.planNext(0, 3, 1), 'swap');
  // preloaded passt nicht (null oder falscher Index) → Fallback ladeTrack
  assert.equal(P.planNext(0, 3, null), 'load');
  assert.equal(P.planNext(0, 3, 2), 'load');
  // letzter Track → Wiedergabe endet, egal was gepuffert ist
  assert.equal(P.planNext(2, 3, 3), 'stop');
  assert.equal(P.planNext(2, 3, null), 'stop');
});

test('preloadNext: puffert nächsten Track ins idle-Element (src+load+preloadedIdx), out-of-range null (#1304, AC-BG1)', async () => {
  const savedAudio = global.Audio;
  const A = makeAudioMock();
  global.Audio = A;
  P._S.audio = null; P._S.audioIdle = null;
  P._S.cache = null;   // Miss → resolveTrackSrc gibt die Netz-URL
  P._S.cfg = { playback_tempo: 1.1 };
  P._S.tracks = [
    { position: 1, 'audio-asset': '/audio/t1.mp3' },
    { position: 2, 'audio-asset': '/audio/t2.mp3' },
  ];
  try {
    P.ensureAudio();
    const idle = P._S.audioIdle;
    await P.preloadNext(1);
    assert.equal(idle.src, '/audio/t2.mp3', 'idle-Element bekommt die nächste Quelle');
    assert.equal(idle.preload, 'auto', 'preload=auto für Hintergrund-Puffern');
    assert.equal(idle.loaded, 1, 'load() angestoßen');
    assert.equal(idle.playbackRate, 1.1, 'Tempo auch aufs idle-Element');
    assert.equal(P._S.preloadedIdx, 1, 'preloadedIdx gesetzt → planNext kann swappen');
    // out of range (letzter Track hat keinen Nachfolger) → kein Puffer
    await P.preloadNext(2);
    assert.equal(P._S.preloadedIdx, null, 'kein Nachfolger → preloadedIdx zurückgesetzt');
  } finally {
    global.Audio = savedAudio;
    P._S.audio = null; P._S.audioIdle = null;
    P._S.cache = null; P._S.tracks = []; P._S.trackIdx = 0; P._S.preloadedIdx = null; P._S.cfg = {};
  }
});

test('ended-Guard: nur das AKTIVE Element advanct; idle-ended ist ein No-Op (#1304, AC-BG1, kein_doppelfeuer)', () => {
  const savedAudio = global.Audio;
  const A = makeAudioMock();
  global.Audio = A;
  P._S.audio = null; P._S.audioIdle = null;
  P._S.tracks = [{ position: 1 }, { position: 2 }, { position: 3 }];
  P._S.trackIdx = 0;
  P._S.preloadedIdx = 1;      // nächster ist gepuffert → aktives ended würde swappen
  P._S.aktivAlbum = null;     // updateMediaSession/Resume no-op ohne navigator
  P._S.cache = null; P._S.cfg = {};
  try {
    P.ensureAudio();
    const idle = P._S.audioIdle;
    // idle feuert 'ended' → Guard (ev.target !== S.audio) blockt → KEIN Advance.
    idle.fire('ended', idle);
    assert.equal(P._S.trackIdx, 0, 'idle-ended verändert den Track-Index NICHT (Anti-Doppelfeuer)');
  } finally {
    global.Audio = savedAudio;
    P._S.audio = null; P._S.audioIdle = null;
    P._S.tracks = []; P._S.trackIdx = 0; P._S.preloadedIdx = null; P._S.aktivAlbum = null; P._S.cache = null;
  }
});

test('ended-swap: aktives ended swappt SYNCHRON ans gepufferte idle-Element + hält MediaSession playing (#1304, AC-BG2)', () => {
  const savedAudio = global.Audio;
  const savedNav = global.navigator;
  const A = makeAudioMock();
  global.Audio = A;
  const msCalls = { playbackState: [], metadata: 0 };
  global.navigator = {
    mediaSession: {
      get playbackState() { return this._ps; },
      set playbackState(v) { this._ps = v; msCalls.playbackState.push(v); },
      set metadata(v) { msCalls.metadata++; },
      setActionHandler() {},
      setPositionState() {},
    },
  };
  global.MediaMetadata = function (o) { Object.assign(this, o); };
  const savedDoc = global.document;
  global.document = { getElementById: () => null, querySelector: () => null };  // DOM-Zugriffe im Swap sind No-Ops
  P._S.audio = null; P._S.audioIdle = null;
  P._S.tracks = [{ position: 1 }, { position: 2 }, { position: 3 }];
  P._S.trackIdx = 0;
  P._S.preloadedIdx = 1;
  P._S.aktivAlbum = { id: 'folge-22', nummer: 22, titel: 'Der See' };
  P._S.aktivKindId = 'paula'; P._S.kindId = 'paula';
  P._S.cache = null; P._S.cfg = { playback_tempo: 1.0 };
  const savedFetch = global.fetch;
  global.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
  try {
    P.ensureAudio();
    const aktivVorher = P._S.audio;
    const idleVorher = P._S.audioIdle;
    // aktives Element feuert 'ended' → planNext=swap → synchroner Swap.
    aktivVorher.fire('ended', aktivVorher);
    assert.equal(P._S.trackIdx, 1, 'Track advanct auf den vorgepufferten Index');
    assert.equal(P._S.audio, idleVorher, 'idle-Element ist jetzt aktiv (Rollen getauscht)');
    assert.equal(P._S.audioIdle, aktivVorher, 'altes aktives Element ist jetzt idle');
    assert.equal(idleVorher.played, 1, 'play() SYNCHRON am schon-gepufferten Element (kein await)');
    assert.ok(msCalls.metadata >= 1, 'MediaSession-Metadata für den neuen Track gesetzt');
    assert.ok(!msCalls.playbackState.includes('paused'), 'playbackState im Swap NIE auf paused gekippt');
    assert.equal(global.navigator.mediaSession.playbackState, 'playing', 'playbackState über den Swap gehalten');
  } finally {
    global.Audio = savedAudio;
    global.navigator = savedNav;
    global.fetch = savedFetch;
    global.document = savedDoc;
    delete global.MediaMetadata;
    P._S.audio = null; P._S.audioIdle = null;
    P._S.tracks = []; P._S.trackIdx = 0; P._S.preloadedIdx = null; P._S.aktivAlbum = null;
    P._S.aktivKindId = null; P._S.cache = null; P._S.cfg = {};
  }
});

/* ══ AC-B3: PWA-Icons valide (HSP-55) ═══════════════════════════ */

/* ══ HSP-55: Entry-Path — Player-HTML verlinkt die seiten-Player-Route ══ */

test('player.html: Manifest+SW+Shell-Assets über /seiten/hoerspiel/player, kein Kiosk-Präfix (HSP-47/55)', () => {
  // Roh-Template als String lesen — {{ build_id }}-Platzhalter sind hier ok
  // (kein Jinja-Render nötig, wir prüfen nur die Entry-Path-Verdrahtung).
  const html = fs.readFileSync(
    path.join(__dirname, '../templates/player.html'), 'utf8');

  // (a) Manifest zeigt auf die seiten-Player-Route (nicht aufs alte Kiosk-Manifest).
  assert.match(html, /<link\s+rel="manifest"\s+href="\/seiten\/hoerspiel\/player\/manifest\.json"/,
    'Manifest-Link → /seiten/hoerspiel/player/manifest.json');

  // (b) Service-Worker wird registriert (installierbare PWA) — seiten-Route.
  assert.match(html, /serviceWorker\.register\(\s*['"]\/seiten\/hoerspiel\/player\/sw\.js['"]/,
    'SW-Registrierung auf /seiten/hoerspiel/player/sw.js');

  // (c) KEINE Shell-Assets mehr über den Kiosk-Buddy (HSP-47 „seiten-gehostet").
  assert.doesNotMatch(html, /\/display\/hoerspiel\/static\//,
    'kein /display/hoerspiel/static/-Asset-Ref mehr');

  // Shell-Assets (css/js/icon) laufen über die seiten-Player-Route.
  assert.match(html, /href="\/seiten\/hoerspiel\/player\/player\.css/, 'player.css seiten-gehostet');
  assert.match(html, /src="\/seiten\/hoerspiel\/player\/player\.js/, 'player.js seiten-gehostet');
  assert.match(html, /href="\/seiten\/hoerspiel\/player\/icon-192\.png"/, 'Icon seiten-gehostet');
});

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
