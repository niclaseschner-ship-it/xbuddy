/* HSP-2/3/4/4a/4b/19-23 — Werft-Iter-3 (Gate-B) Mia-View. */

'use strict';

/* ── KIND_ID aus URL (HSP-26, URL-3a) ────────────────────────────────
   Pattern: /display/hoerspiel/<kind_id>/alben → kind_id ist Segment 3
   (0-basiert nach dem ersten Slash). Fallback: 'mia' für Dev/Standalone. */
const KIND_ID = (() => {
  const m = location.pathname.match(/^\/display\/hoerspiel\/([^/]+)\/alben/);
  return m ? m[1] : 'mia';
})();

/* ── MOCK-DATEN (Entry-Path-Probe ohne Backend) ──────────────────────
   MOCK_ALBEN: Listen-Form (Summary, ohne tracks).
   MOCK_MANIFESTE: id → Manifest mit tracks (HSP-17 Liste-vs-Manifest).
   Mock-URLs tragen KIND_ID damit Finn-Demo nicht mia-spezifische Pfade zeigt. */
const COVER_DEFAULT = `/display/hoerspiel/${KIND_ID}/data/shared-assets/cover-default.jpg`;

const MOCK_ALBEN = [
  {
    id: 'folge-22', nummer: 22,
    titel: 'Schmuggli erzählt vom Trübsee',
    voice: 'shimmer', 'erstellt-am': '2026-06-12',
    'cover-asset': COVER_DEFAULT,
    'pikto-hauptbegriffe': [{ wort: 'Trübsee', 'arasaac-id': 6022 }]
  },
  {
    id: 'folge-21', nummer: 21,
    titel: 'Stigi und der Regenbogen',
    voice: 'onyx', 'erstellt-am': '2026-06-01',
    'cover-asset': COVER_DEFAULT,
    'pikto-hauptbegriffe': []
  },
  {
    id: 'folge-20', nummer: 20,
    titel: 'Vögelchen lernt fliegen',
    voice: 'shimmer', 'erstellt-am': '2026-05-20',
    'cover-asset': COVER_DEFAULT,
    'pikto-hauptbegriffe': [{ wort: 'fliegen', 'arasaac-id': 2887 }]
  }
];

const MOCK_MANIFESTE = {
  'folge-22': {
    id: 'folge-22', nummer: 22,
    titel: 'Schmuggli erzählt vom Trübsee',
    voice: 'shimmer', 'erstellt-am': '2026-06-12',
    'cover-asset': COVER_DEFAULT,
    'pikto-hauptbegriffe': [{ wort: 'Trübsee', 'arasaac-id': 6022 }],
    tracks: [
      { id: 'intro-shimmer', position: 1, art: 'intro',
        'audio-asset': `/display/hoerspiel/${KIND_ID}/data/shared-assets/intro_shimmer.mp3`,
        'dauer-sek': 18 },
      { id: 'folge-22-track-02', position: 2, art: 'inhalt',
        'audio-asset': `/display/hoerspiel/${KIND_ID}/data/alben/folge-22/audio/track-02.mp3`,
        'dauer-sek': 215, titel: 'Der Weg zum See' },
      { id: 'folge-22-track-03', position: 3, art: 'inhalt',
        'audio-asset': `/display/hoerspiel/${KIND_ID}/data/alben/folge-22/audio/track-03.mp3`,
        'dauer-sek': 200, titel: 'Am Trübsee-Ufer',
        'pikto-hauptbegriffe': [{ wort: 'See', 'arasaac-id': 5199 }] },
      { id: 'outro-shimmer', position: 4, art: 'outro',
        'audio-asset': `/display/hoerspiel/${KIND_ID}/data/shared-assets/outro_shimmer.mp3`,
        'dauer-sek': 20 }
    ]
  }
};

const ICON_BASE = '/display/_shared/icons/';
const MEHR_SLOT_PIKTO = `${ICON_BASE}arasaac/5508.png`;
const RESUME_PREFIX = 'hoerspiel-resume-';
const LAST_ALBUM_KEY = 'hoerspiel-last-album';

let state = {
  alben: [],
  aktiv: null,
  aktiv_track: 0,
  playing: false,
  is_resume: false,
  audio: null,
  prev_tap_ts: 0,
  manifestCache: {},
};

const dom = {
  grid:         () => document.getElementById('kacheln-grid'),
  player:       () => document.getElementById('player'),
  coverImg:     () => document.getElementById('player-cover-img'),
  albumNr:      () => document.getElementById('player-album-nr'),
  albumTitle:   () => document.getElementById('player-album-title'),
  tracksList:   () => document.getElementById('player-tracks-list'),
  nowLabel:     () => document.getElementById('player-now-label'),
  nowText:      () => document.getElementById('player-now-text'),
  progress:     () => document.getElementById('player-progress-fill'),
  btnPlay:      () => document.getElementById('ctrl-play'),
  btnPrev:      () => document.getElementById('ctrl-prev'),
  btnNext:      () => document.getElementById('ctrl-next'),
  topbarSub:    () => document.getElementById('topbar-sub')
};

/* ── RESUME-STATE (HSP-23) ───────────────────────────────────────── */
function resumeGet(albumId) {
  try {
    const raw = localStorage.getItem(RESUME_PREFIX + albumId);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}
function resumeSet(albumId, trackPos) {
  try { localStorage.setItem(RESUME_PREFIX + albumId, JSON.stringify({ track: trackPos })); } catch {}
}
function resumeClear(albumId) {
  try { localStorage.removeItem(RESUME_PREFIX + albumId); } catch {}
}
function lastAlbumSet(albumId) {
  try { localStorage.setItem(LAST_ALBUM_KEY, albumId); } catch {}
}
function lastAlbumGet() {
  try { return localStorage.getItem(LAST_ALBUM_KEY); } catch { return null; }
}

/* ── PIKTO-WORTBLOCK (HSP-4a/E-HSP-11) ───────────────────────────── */
function renderPiktoText(text, mappings) {
  const frag = document.createDocumentFragment();
  if (!mappings || mappings.length === 0) {
    frag.appendChild(document.createTextNode(text));
    return frag;
  }
  const escaped = mappings.map(m => m.wort.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const re = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(re);
  parts.forEach(part => {
    const mapping = mappings.find(m => m.wort.toLowerCase() === part.toLowerCase());
    if (mapping) {
      const span = document.createElement('span');
      span.className = 'word-pikto';
      const img = document.createElement('img');
      img.src = `${ICON_BASE}arasaac/${mapping['arasaac-id']}.png`;
      img.alt = '';
      img.setAttribute('aria-hidden', 'true');
      const wort = document.createElement('span');
      wort.textContent = part;
      span.appendChild(img);
      span.appendChild(wort);
      frag.appendChild(span);
    } else if (part) {
      frag.appendChild(document.createTextNode(part));
    }
  });
  return frag;
}

/* ── KACHEL-RENDER (HSP-19/E-HSP-8/E-HSP-10) ─────────────────────── */
function renderKacheln(alben, resumeAlbumId, activeAlbumId) {
  const grid = dom.grid();
  grid.innerHTML = '';
  const MAX_KACHELN = 10;
  const hatMehr = alben.length > MAX_KACHELN;
  const sichtbar = hatMehr ? alben.slice(0, MAX_KACHELN - 1) : alben;
  sichtbar.forEach(album => grid.appendChild(buildKachel(album, resumeAlbumId, activeAlbumId)));
  if (hatMehr) {
    grid.appendChild(buildMehrSlot(alben.length - (MAX_KACHELN - 1)));
  }
}

function buildKachel(album, resumeAlbumId, activeAlbumId) {
  const hasResume = album.id === resumeAlbumId && resumeGet(album.id) !== null;
  const isActive = album.id === activeAlbumId;
  const div = document.createElement('div');
  div.className = 'tile' + (hasResume ? ' is-resume' : '') + (isActive ? ' is-playing' : '');
  div.setAttribute('role', 'listitem');
  div.setAttribute('tabindex', '0');
  div.setAttribute('aria-label', album.titel);
  div.dataset.albumId = album.id;

  if (hasResume) {
    const badge = document.createElement('div');
    badge.className = 'tile-badge';
    badge.textContent = 'Weiter';
    div.appendChild(badge);
  }

  const coverWrap = document.createElement('div');
  coverWrap.className = 'tile-cover';
  const img = document.createElement('img');
  img.src = album['cover-asset'] || COVER_DEFAULT;
  img.alt = '';
  img.setAttribute('aria-hidden', 'true');
  img.loading = 'lazy';
  coverWrap.appendChild(img);
  div.appendChild(coverWrap);

  const nr = document.createElement('div');
  nr.className = 'tile-nr';
  nr.textContent = `Folge ${album.nummer}`;
  div.appendChild(nr);

  const titel = document.createElement('div');
  titel.className = 'tile-title';
  titel.appendChild(renderPiktoText(album.titel, album['pikto-hauptbegriffe'] || []));
  div.appendChild(titel);

  div.addEventListener('click', () => tapKachel(album));
  div.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); tapKachel(album); }
  });
  return div;
}

function buildMehrSlot(count) {
  const div = document.createElement('div');
  div.className = 'tile is-more';
  div.setAttribute('role', 'listitem');
  div.setAttribute('aria-label', 'Ältere Folgen');

  const piktoWrap = document.createElement('div');
  piktoWrap.className = 'more-pikto';
  const img = document.createElement('img');
  img.src = MEHR_SLOT_PIKTO;
  img.alt = '';
  img.setAttribute('aria-hidden', 'true');
  piktoWrap.appendChild(img);
  div.appendChild(piktoWrap);

  const label = document.createElement('div');
  label.className = 'more-label';
  label.textContent = 'Ältere Folgen';
  div.appendChild(label);

  const sub = document.createElement('div');
  sub.className = 'more-sub';
  sub.textContent = `${count} weitere`;
  div.appendChild(sub);
  return div;
}

/* ── TRACK-LABEL-DEFAULT (Intro/Outro mit Reim-Hinweis) ──────────── */
function trackLabel(track) {
  if (track.titel) return track.titel;
  if (track.art === 'intro') return 'Intro-Reim';
  if (track.art === 'outro') return 'Outro-Reim';
  return `Track ${track.position}`;
}

/* ── PLAYER-RENDER (HSP-21) ──────────────────────────────────────── */
function renderPlayer(album, trackIdx, isResume) {
  const tracks = sortedTracks(album);
  const track = tracks[trackIdx] || tracks[0];

  dom.coverImg().src = album['cover-asset'] || COVER_DEFAULT;
  dom.coverImg().alt = album.titel;

  dom.albumNr().textContent = `Folge ${album.nummer} · Voice: ${album.voice}`;
  dom.albumTitle().textContent = '';
  dom.albumTitle().appendChild(renderPiktoText(album.titel, album['pikto-hauptbegriffe'] || []));

  const ul = dom.tracksList();
  ul.innerHTML = '';
  tracks.forEach((t, i) => {
    const li = document.createElement('div');
    li.className = 'player-track' +
      (i === trackIdx ? ' is-active' : '') +
      (t.art === 'intro' ? ' intro' : '') +
      (t.art === 'outro' ? ' outro' : '');
    li.setAttribute('role', 'listitem');
    li.dataset.trackIdx = i;

    const pos = document.createElement('div');
    pos.className = 'pos';
    pos.textContent = t.position;
    li.appendChild(pos);

    const name = document.createElement('div');
    name.className = 'name';
    name.appendChild(renderPiktoText(trackLabel(t), t['pikto-hauptbegriffe'] || []));
    li.appendChild(name);

    li.addEventListener('click', () => {
      state.aktiv_track = i;
      playTrack(album, i);
    });
    ul.appendChild(li);
  });

  dom.nowLabel().textContent = `Track ${track.position} von ${tracks.length}` +
    (isResume ? ' · zuletzt gehört' : '');
  dom.nowText().textContent = '';
  dom.nowText().appendChild(renderPiktoText(trackLabel(track), track['pikto-hauptbegriffe'] || []));

  const btnPlay = dom.btnPlay();
  if (isResume) {
    btnPlay.classList.add('is-resume');
    btnPlay.setAttribute('aria-label', 'Weiter hören');
    btnPlay.title = `Weiter hören (Folge ${album.nummer} Track ${track.position})`;
  } else {
    btnPlay.classList.remove('is-resume');
    btnPlay.setAttribute('aria-label', state.playing ? 'Pause' : 'Abspielen');
    btnPlay.title = state.playing ? 'Pause' : 'Abspielen';
  }
  syncPlayPauseIcons();
  dom.progress().style.width = '0%';
}

function syncPlayPauseIcons() {
  const btn = dom.btnPlay();
  const iconPlay = btn.querySelector('.icon-play');
  const iconPause = btn.querySelector('.icon-pause');
  if (!iconPlay || !iconPause) return;
  if (state.playing) {
    iconPlay.hidden = true;
    iconPause.removeAttribute('hidden');
  } else {
    iconPlay.removeAttribute('hidden');
    iconPause.hidden = true;
  }
}

function sortedTracks(album) {
  return [...(album.tracks || [])].sort((a, b) => a.position - b.position);
}

/* ── KACHEL-TAP (HSP-20) ─────────────────────────────────────────── */
async function tapKachel(album) {
  const manifest = await loadAlbumManifest(album.id);
  const albumMitTracks = manifest ? { ...album, ...manifest } : album;

  const resume = resumeGet(album.id);
  let trackIdx = 0;
  let isResume = false;
  if (resume && resume.track != null) {
    const tracks = sortedTracks(albumMitTracks);
    const idx = tracks.findIndex(t => t.position === resume.track);
    trackIdx = idx >= 0 ? idx : 0;
    isResume = true;
  }

  state.aktiv = albumMitTracks;
  state.aktiv_track = trackIdx;
  state.is_resume = isResume;
  renderKacheln(state.alben, isResume ? album.id : null, album.id);
  renderPlayer(albumMitTracks, trackIdx, isResume);
  playTrack(albumMitTracks, trackIdx);
  lastAlbumSet(album.id);
}

/* ── AUDIO-WIEDERGABE (HSP-21/22/23) ────────────────────────────── */
function playTrack(album, trackIdx) {
  const tracks = sortedTracks(album);
  const track = tracks[trackIdx];
  if (!track) return;

  if (state.audio) {
    state.audio.pause();
    state.audio.src = '';
  }

  const audio = new Audio(track['audio-asset']);
  state.audio = audio;
  state.playing = true;
  state.aktiv = album;
  state.aktiv_track = trackIdx;

  audio.addEventListener('timeupdate', () => {
    if (audio.duration > 0) {
      dom.progress().style.width = ((audio.currentTime / audio.duration) * 100).toFixed(1) + '%';
    }
    resumeSet(album.id, track.position);
  });

  audio.addEventListener('ended', () => {
    const isLast = trackIdx >= tracks.length - 1;
    if (isLast) {
      resumeClear(album.id);
      state.aktiv_track = 0;
      state.playing = false;
      renderPlayer(album, 0, false);
      updateMediaSession(album, tracks[0]);
      renderKacheln(state.alben, null, album.id);
    } else {
      state.aktiv_track = trackIdx + 1;
      playTrack(album, trackIdx + 1);
    }
  });

  audio.addEventListener('play', () => {
    state.playing = true;
    syncPlayPauseIcons();
    updateMediaSession(album, track);
  });

  audio.addEventListener('pause', () => {
    state.playing = false;
    syncPlayPauseIcons();
  });

  document.querySelectorAll('.player-track').forEach((li, i) =>
    li.classList.toggle('is-active', i === trackIdx)
  );

  dom.nowLabel().textContent = `Track ${track.position} von ${tracks.length}`;
  dom.nowText().textContent = '';
  dom.nowText().appendChild(renderPiktoText(trackLabel(track), track['pikto-hauptbegriffe'] || []));

  state.is_resume = false;
  dom.btnPlay().classList.remove('is-resume');
  dom.btnPlay().setAttribute('aria-label', 'Pause');

  syncPlayPauseIcons();
  updateMediaSession(album, track);
  audio.play().catch(() => {});
}

/* ── PLAY/PAUSE / PREV / NEXT (HSP-21) ───────────────────────────── */
function togglePlayPause() {
  if (!state.aktiv) return;
  if (!state.audio || state.audio.ended) {
    playTrack(state.aktiv, state.aktiv_track);
    return;
  }
  if (state.playing) state.audio.pause();
  else state.audio.play().catch(() => {});
}

function prevTrack() {
  if (!state.aktiv) return;
  const now = Date.now();
  const isDouble = (now - state.prev_tap_ts) < 3000;
  state.prev_tap_ts = now;

  if (isDouble && state.aktiv_track > 0) {
    state.aktiv_track -= 1;
    playTrack(state.aktiv, state.aktiv_track);
  } else {
    if (state.audio) {
      state.audio.currentTime = 0;
      if (!state.playing) state.audio.play().catch(() => {});
    } else {
      playTrack(state.aktiv, state.aktiv_track);
    }
  }
}

function nextTrack() {
  if (!state.aktiv) return;
  const tracks = sortedTracks(state.aktiv);
  if (state.aktiv_track < tracks.length - 1) {
    state.aktiv_track += 1;
    playTrack(state.aktiv, state.aktiv_track);
  } else {
    state.aktiv_track = 0;
    playTrack(state.aktiv, 0);
  }
}

/* ── MEDIASESSION (HSP-22) ───────────────────────────────────────── */
function setupMediaSession() {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.setActionHandler('play',          () => { if (state.audio) state.audio.play().catch(() => {}); });
  navigator.mediaSession.setActionHandler('pause',         () => { if (state.audio) state.audio.pause(); });
  navigator.mediaSession.setActionHandler('previoustrack', prevTrack);
  navigator.mediaSession.setActionHandler('nexttrack',     nextTrack);
}

function updateMediaSession(album, track) {
  if (!('mediaSession' in navigator)) return;
  const lbl = trackLabel(track);
  navigator.mediaSession.metadata = new MediaMetadata({
    title: lbl,
    artist: album.voice === 'shimmer' ? 'Stigi & Co. (shimmer)' : 'Stigi & Co. (onyx)',
    album: `Folge ${album.nummer}: ${album.titel}`,
    artwork: album['cover-asset'] ? [{ src: album['cover-asset'], sizes: '512x512', type: 'image/jpeg' }] : []
  });
  navigator.mediaSession.playbackState = state.playing ? 'playing' : 'paused';
}

/* ── PLAYER-DEFAULT-ZUSTAND (HSP-2/23) ───────────────────────────── */
async function initPlayerDefault(alben) {
  if (alben.length === 0) {
    renderKacheln([], null, null);
    return;
  }

  let resumeAlbum = null;
  for (const album of alben) {
    if (resumeGet(album.id)?.track != null) { resumeAlbum = album; break; }
  }

  if (resumeAlbum) {
    const manifest = await loadAlbumManifest(resumeAlbum.id);
    const albumMitTracks = manifest ? { ...resumeAlbum, ...manifest } : resumeAlbum;
    const tracks = sortedTracks(albumMitTracks);
    const r = resumeGet(resumeAlbum.id);
    const idx = tracks.findIndex(t => t.position === r.track);
    state.aktiv = albumMitTracks;
    state.aktiv_track = idx >= 0 ? idx : 0;
    state.is_resume = true;
    renderKacheln(alben, resumeAlbum.id, resumeAlbum.id);
    renderPlayer(albumMitTracks, state.aktiv_track, true);
    return;
  }

  const lastId = lastAlbumGet();
  const defaultAlbum = (lastId && alben.find(a => a.id === lastId)) || alben[0];
  const manifest = await loadAlbumManifest(defaultAlbum.id);
  const defaultMitTracks = manifest ? { ...defaultAlbum, ...manifest } : defaultAlbum;

  state.aktiv = defaultMitTracks;
  state.aktiv_track = 0;
  state.is_resume = false;
  renderKacheln(alben, null, defaultAlbum.id);
  renderPlayer(defaultMitTracks, 0, false);
}

/* ── DATEN LADEN ─────────────────────────────────────────────────── */
async function loadAlben() {
  try {
    const res = await fetch(`/api/v1/hoerspiel/${KIND_ID}/alben`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) return data;
    return data || [];
  } catch {
    return MOCK_ALBEN;
  }
}

async function loadAlbumManifest(albumId) {
  if (state.manifestCache[albumId]) return state.manifestCache[albumId];
  try {
    const res = await fetch(`/api/v1/hoerspiel/${KIND_ID}/alben/${albumId}/manifest`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const manifest = await res.json();
    state.manifestCache[albumId] = manifest;
    return manifest;
  } catch {
    const mock = MOCK_MANIFESTE[albumId] || null;
    if (mock) state.manifestCache[albumId] = mock;
    return mock;
  }
}

/* ── CONTROLS + INIT ─────────────────────────────────────────────── */
function bindControls() {
  dom.btnPlay().addEventListener('click', togglePlayPause);
  dom.btnPrev().addEventListener('click', prevTrack);
  dom.btnNext().addEventListener('click', nextTrack);
}

async function init() {
  setupMediaSession();
  bindControls();
  const raw = await loadAlben();
  state.alben = [...raw].sort((a, b) => b.nummer - a.nummer);
  await initPlayerDefault(state.alben);
}

document.addEventListener('DOMContentLoaded', init);

// ── Exports (für Tests, T1027/AC4) ──────────────────────────────────────────
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { KIND_ID };
}
