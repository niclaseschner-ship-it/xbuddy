/* ══════════════════════════════════════════════════════════════════════════
   Hörspiel-Buddy — View `alben`  (HSP-2/3/4/4a/4b/19/20/21/22/23)
   Vanilla JS, kein Framework. Alle Daten aus GET /api/v1/hoerspiel/alben;
   Fallback auf Mock-Manifest bei Netz-Fehler (Entry-Path-Probe).
   ══════════════════════════════════════════════════════════════════════════ */

'use strict';

/* ── MOCK-DATEN (Entry-Path-Probe: Browser-Verifizierung ohne Backend) ──────
   MOCK_ALBEN: Listen-Form (Summary, ohne tracks) — wie GET /alben liefert.
   MOCK_MANIFESTE: id → Manifest mit tracks — wie GET /alben/<id>/manifest.
   HSP-17: Liste und Manifest sind bewusst getrennt (Befund 2+3).            */
const MOCK_ALBEN = [
  {
    id: 'folge-22',
    nummer: 22,
    titel: 'Schmuggli erzählt vom Trübsee',
    voice: 'shimmer',
    'erstellt-am': '2026-06-12',
    'cover-asset': '/display/hoerspiel/static/cover-default.png',
    'pikto-hauptbegriffe': [
      { wort: 'Trübsee', 'arasaac-id': 6022 }
    ]
  },
  {
    id: 'folge-21',
    nummer: 21,
    titel: 'Stigi und der Regenbogen',
    voice: 'onyx',
    'erstellt-am': '2026-06-01',
    'cover-asset': '/display/hoerspiel/static/cover-default.png',
    'pikto-hauptbegriffe': []
  },
  {
    id: 'folge-20',
    nummer: 20,
    titel: 'Vögelchen lernt fliegen',
    voice: 'shimmer',
    'erstellt-am': '2026-05-20',
    'cover-asset': '/display/hoerspiel/static/cover-default.png',
    'pikto-hauptbegriffe': [
      { wort: 'fliegen', 'arasaac-id': 2887 }
    ]
  }
];

const MOCK_MANIFESTE = {
  'folge-22': {
    id: 'folge-22', nummer: 22,
    titel: 'Schmuggli erzählt vom Trübsee',
    voice: 'shimmer', 'erstellt-am': '2026-06-12',
    'cover-asset': '/display/hoerspiel/static/cover-default.png',
    'pikto-hauptbegriffe': [{ wort: 'Trübsee', 'arasaac-id': 6022 }],
    tracks: [
      { id: 'intro-shimmer', position: 1, art: 'intro',
        'audio-asset': '/display/hoerspiel/data/shared-assets/intro_shimmer.mp3',
        'dauer-sek': 18, titel: 'Intro' },
      { id: 'folge-22-track-02', position: 2, art: 'inhalt',
        'audio-asset': '/display/hoerspiel/data/alben/folge-22/audio/track-02.mp3',
        'dauer-sek': 215, titel: 'Der Weg zum See' },
      { id: 'folge-22-track-03', position: 3, art: 'inhalt',
        'audio-asset': '/display/hoerspiel/data/alben/folge-22/audio/track-03.mp3',
        'dauer-sek': 200, titel: 'Am Trübsee-Ufer',
        'pikto-hauptbegriffe': [{ wort: 'See', 'arasaac-id': 5199 }] },
      { id: 'outro-shimmer', position: 4, art: 'outro',
        'audio-asset': '/display/hoerspiel/data/shared-assets/outro_shimmer.mp3',
        'dauer-sek': 20, titel: 'Outro' }
    ]
  },
  'folge-21': {
    id: 'folge-21', nummer: 21,
    titel: 'Stigi und der Regenbogen',
    voice: 'onyx', 'erstellt-am': '2026-06-01',
    'cover-asset': '/display/hoerspiel/static/cover-default.png',
    'pikto-hauptbegriffe': [],
    tracks: [
      { id: 'intro-onyx', position: 1, art: 'intro',
        'audio-asset': '/display/hoerspiel/data/shared-assets/intro_onyx.mp3',
        'dauer-sek': 18, titel: 'Intro' },
      { id: 'folge-21-track-02', position: 2, art: 'inhalt',
        'audio-asset': '/display/hoerspiel/data/alben/folge-21/audio/track-02.mp3',
        'dauer-sek': 210, titel: 'Der Regen beginnt' },
      { id: 'folge-21-track-03', position: 3, art: 'inhalt',
        'audio-asset': '/display/hoerspiel/data/alben/folge-21/audio/track-03.mp3',
        'dauer-sek': 195, titel: 'Malini findet die Farben' },
      { id: 'outro-onyx', position: 4, art: 'outro',
        'audio-asset': '/display/hoerspiel/data/shared-assets/outro_onyx.mp3',
        'dauer-sek': 20, titel: 'Outro' }
    ]
  },
  'folge-20': {
    id: 'folge-20', nummer: 20,
    titel: 'Vögelchen lernt fliegen',
    voice: 'shimmer', 'erstellt-am': '2026-05-20',
    'cover-asset': '/display/hoerspiel/static/cover-default.png',
    'pikto-hauptbegriffe': [{ wort: 'fliegen', 'arasaac-id': 2887 }],
    tracks: [
      { id: 'intro-shimmer', position: 1, art: 'intro',
        'audio-asset': '/display/hoerspiel/data/shared-assets/intro_shimmer.mp3',
        'dauer-sek': 18, titel: 'Intro' },
      { id: 'folge-20-track-02', position: 2, art: 'inhalt',
        'audio-asset': '/display/hoerspiel/data/alben/folge-20/audio/track-02.mp3',
        'dauer-sek': 220, titel: 'Der erste Versuch' },
      { id: 'folge-20-track-03', position: 3, art: 'inhalt',
        'audio-asset': '/display/hoerspiel/data/alben/folge-20/audio/track-03.mp3',
        'dauer-sek': 205, titel: 'Hoch über dem Garten' },
      { id: 'outro-shimmer', position: 4, art: 'outro',
        'audio-asset': '/display/hoerspiel/data/shared-assets/outro_shimmer.mp3',
        'dauer-sek': 20, titel: 'Outro' }
    ]
  }
};

/* ARASAAC-Icon-Basis (ICONS-5, DTOK-1) */
const ICON_BASE = '/display/_shared/icons/';
/* ARASAAC-5915: Kopfhörer — „Ältere Folgen"-Mehr-Slot */
const MEHR_SLOT_PIKTO = `${ICON_BASE}arasaac/5915.png`;

/* localStorage-Schlüssel für Resume-State (HSP-23) */
const RESUME_PREFIX = 'hoerspiel-resume-';
/* localStorage-Schlüssel für zuletzt gespieltes Album */
const LAST_ALBUM_KEY = 'hoerspiel-last-album';

/* ── APP-STATE ────────────────────────────────────────────────────────────── */
let state = {
  alben: [],            /* alle freigegebenen Alben, sortiert nach nummer desc */
  aktiv: null,          /* aktives Album-Objekt (mit tracks nach Manifest-Laden) */
  aktiv_track: 0,       /* Track-Index (0-basiert) im aktiven Album */
  playing: false,
  is_resume: false,     /* orange Play-Button */
  audio: null,          /* HTMLAudioElement */
  prev_tap_ts: 0,       /* für Doppel-Prev-Erkennung (HSP-21) */
  manifestCache: {}     /* id → Manifest-Objekt mit tracks (Befund 3, HSP-17) */
};

/* ── DOM-REFS ────────────────────────────────────────────────────────────── */
const dom = {
  grid:           () => document.getElementById('kacheln-grid'),
  player:         () => document.getElementById('player'),
  cover:          () => document.getElementById('player-cover'),
  albumNr:        () => document.getElementById('player-album-nr'),
  albumTitel:     () => document.getElementById('player-album-titel'),
  tracks:         () => document.getElementById('player-tracks'),
  nowPlaying:     () => document.getElementById('player-now-playing'),
  progress:       () => document.getElementById('player-progress-fill'),
  btnPlay:        () => document.getElementById('ctrl-play'),
  btnPrev:        () => document.getElementById('ctrl-prev'),
  btnNext:        () => document.getElementById('ctrl-next')
};

/* ── RESUME-STATE (HSP-23) ───────────────────────────────────────────────── */
function resumeGet(albumId) {
  try {
    const raw = localStorage.getItem(RESUME_PREFIX + albumId);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function resumeSet(albumId, trackPos) {
  try {
    localStorage.setItem(RESUME_PREFIX + albumId, JSON.stringify({ track: trackPos }));
  } catch { /* storage voll — still fail */ }
}

function resumeClear(albumId) {
  try { localStorage.removeItem(RESUME_PREFIX + albumId); } catch { /* noop */ }
}

function lastAlbumSet(albumId) {
  try { localStorage.setItem(LAST_ALBUM_KEY, albumId); } catch { /* noop */ }
}

function lastAlbumGet() {
  try { return localStorage.getItem(LAST_ALBUM_KEY); } catch { return null; }
}

/* ── PIKTO-WORTBLOCK (HSP-4a/E-HSP-11: Inline .word-pikto) ─────────────── */
/**
 * Erzeugt aus einem Titel-String und einer Liste von Pikto-Mappings
 * ein DocumentFragment mit ggf. ersetzten Wortblöcken.
 * @param {string} text
 * @param {Array<{wort: string, 'arasaac-id': number}>} mappings
 * @returns {DocumentFragment}
 */
function renderPiktoText(text, mappings) {
  const frag = document.createDocumentFragment();
  if (!mappings || mappings.length === 0) {
    frag.appendChild(document.createTextNode(text));
    return frag;
  }

  /* Baue ein Regex, das alle Wörter matcht (case-insensitive) */
  const escaped = mappings.map(m =>
    m.wort.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  );
  const re = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(re);

  parts.forEach(part => {
    const mapping = mappings.find(m =>
      m.wort.toLowerCase() === part.toLowerCase()
    );
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
    } else {
      frag.appendChild(document.createTextNode(part));
    }
  });
  return frag;
}

/* ── KACHELN RENDERN (HSP-19/E-HSP-8/E-HSP-10) ──────────────────────────── */
function renderKacheln(alben, resumeAlbumId) {
  const grid = dom.grid();
  grid.innerHTML = '';

  /* HSP-2/E-HSP-8: Bis 10 Slots, bei >9 Alben → Slot 10 = „Ältere Folgen" */
  const MAX_KACHELN = 10;
  const hatMehr = alben.length > MAX_KACHELN;
  /* Sichtbare Alben: entweder alle (≤10) oder die neuesten 9 + Mehr-Slot */
  const sichtbar = hatMehr ? alben.slice(0, MAX_KACHELN - 1) : alben;

  sichtbar.forEach(album => {
    const kachel = buildKachel(album, resumeAlbumId);
    grid.appendChild(kachel);
  });

  if (hatMehr) {
    grid.appendChild(buildMehrSlot());
  }
}

function buildKachel(album, resumeAlbumId) {
  const hasResume = album.id === resumeAlbumId && resumeGet(album.id) !== null;
  const div = document.createElement('div');
  div.className = 'card kachel' + (hasResume ? ' resume' : '');
  div.setAttribute('role', 'listitem');
  div.setAttribute('tabindex', '0');
  div.setAttribute('aria-label', album.titel);
  div.dataset.albumId = album.id;

  /* Resume-Badge (HSP-2/23) */
  const badge = document.createElement('span');
  badge.className = 'resume-badge';
  badge.textContent = 'Weiter';
  div.appendChild(badge);

  /* Cover 1:1 (E-HSP-10) */
  const coverWrap = document.createElement('div');
  coverWrap.className = 'kachel-cover-wrap';
  const img = document.createElement('img');
  img.className = 'kachel-cover';
  img.src = album['cover-asset'] || '';
  img.alt = '';
  img.setAttribute('aria-hidden', 'true');
  img.loading = 'lazy';
  coverWrap.appendChild(img);
  div.appendChild(coverWrap);

  /* Body mit Titel (HSP-4a: ggf. Pikto-Wortblöcke) */
  const body = document.createElement('div');
  body.className = 'kachel-body';

  const titel = document.createElement('div');
  titel.className = 'kachel-titel';
  const piktos = album['pikto-hauptbegriffe'] || [];
  titel.appendChild(renderPiktoText(album.titel, piktos));
  body.appendChild(titel);
  div.appendChild(body);

  /* Tap → Album laden + abspielen (HSP-20) */
  div.addEventListener('click', () => tapKachel(album));
  div.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      tapKachel(album);
    }
  });

  return div;
}

function buildMehrSlot() {
  const div = document.createElement('div');
  div.className = 'card kachel mehr-slot';
  div.setAttribute('role', 'listitem');
  div.setAttribute('tabindex', '0');
  div.setAttribute('aria-label', 'Ältere Folgen');

  const coverWrap = document.createElement('div');
  coverWrap.className = 'kachel-cover-wrap';
  const img = document.createElement('img');
  img.src = MEHR_SLOT_PIKTO;
  img.alt = 'Ältere Folgen';
  img.loading = 'lazy';
  coverWrap.appendChild(img);
  div.appendChild(coverWrap);

  const body = document.createElement('div');
  body.className = 'kachel-body';
  const titel = document.createElement('div');
  titel.className = 'kachel-titel';
  titel.textContent = 'Ältere Folgen';
  body.appendChild(titel);
  div.appendChild(body);

  /* Archiv-View ist OPEN-HSP-J — V1: kein Tap-Handler nötig */
  return div;
}

/* ── PLAYER RENDERN (HSP-21) ─────────────────────────────────────────────── */
function renderPlayer(album, trackIdx, isResume) {
  const tracks = sortedTracks(album);
  const track = tracks[trackIdx] || tracks[0];

  /* Cover */
  const cover = dom.cover();
  cover.src = album['cover-asset'] || '';
  cover.alt = album.titel;

  /* Album-Header */
  dom.albumNr().textContent = `Folge ${album.nummer} · ${album.voice}`;
  dom.albumTitel().textContent = '';
  const titelPiktos = album['pikto-hauptbegriffe'] || [];
  dom.albumTitel().appendChild(renderPiktoText(album.titel, titelPiktos));

  /* Track-Liste */
  const ul = dom.tracks();
  ul.innerHTML = '';
  tracks.forEach((t, i) => {
    const li = document.createElement('li');
    li.className = 'track-item' + (i === trackIdx ? ' active' : '');
    li.setAttribute('role', 'listitem');
    li.dataset.trackIdx = i;

    const pos = document.createElement('span');
    pos.className = 'track-pos';
    pos.textContent = t.position;
    li.appendChild(pos);

    const label = document.createElement('span');
    label.className = 'track-label';
    const trackPiktos = t['pikto-hauptbegriffe'] || [];
    const trackLabel = t.titel || `Track ${t.position}`;
    label.appendChild(renderPiktoText(trackLabel, trackPiktos));
    li.appendChild(label);

    li.addEventListener('click', () => {
      state.aktiv_track = i;
      playTrack(album, i);
    });
    ul.appendChild(li);
  });

  /* Now-Playing */
  const np = dom.nowPlaying();
  np.textContent = '';
  const trackPiktos = track['pikto-hauptbegriffe'] || [];
  const trackLabel = track.titel || `Track ${track.position}`;
  np.appendChild(renderPiktoText(trackLabel, trackPiktos));

  /* Play-Button: orange bei Resume (HSP-2/23) */
  const btnPlay = dom.btnPlay();
  if (isResume) {
    btnPlay.classList.add('resume');
    btnPlay.setAttribute('aria-label', 'Weiter hören');
    btnPlay.title = 'Weiter hören';
  } else {
    btnPlay.classList.remove('resume');
    btnPlay.setAttribute('aria-label', state.playing ? 'Pause' : 'Abspielen');
    btnPlay.title = state.playing ? 'Pause' : 'Abspielen';
  }

  /* Play/Pause-Icons */
  syncPlayPauseIcons();

  /* Progress reset */
  dom.progress().style.width = '0%';
}

function syncPlayPauseIcons() {
  const btn = dom.btnPlay();
  const iconPlay = btn.querySelector('.icon-play');
  const iconPause = btn.querySelector('.icon-pause');
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

/* ── KACHEL-TAP (HSP-20) ─────────────────────────────────────────────────── */
async function tapKachel(album) {
  /* aktive Kachel markieren */
  document.querySelectorAll('.kachel').forEach(k =>
    k.classList.toggle('active', k.dataset.albumId === album.id)
  );

  /* HSP-17 / Befund 3: tracks kommen aus dem Manifest-Endpoint, nicht der Liste. */
  const manifest = await loadAlbumManifest(album.id);
  const albumMitTracks = manifest ? { ...album, tracks: manifest.tracks } : album;

  const resume = resumeGet(album.id);
  if (resume && resume.track != null) {
    /* HSP-20: Resume-State → starte am Track-Anfang des gemerkten Tracks */
    const tracks = sortedTracks(albumMitTracks);
    const idx = tracks.findIndex(t => t.position === resume.track);
    const trackIdx = idx >= 0 ? idx : 0;
    state.aktiv = albumMitTracks;
    state.aktiv_track = trackIdx;
    state.is_resume = true;
    renderPlayer(albumMitTracks, trackIdx, true);
    playTrack(albumMitTracks, trackIdx);
  } else {
    /* HSP-20: kein Resume → Track 1 ab Sekunde 0 */
    state.aktiv = albumMitTracks;
    state.aktiv_track = 0;
    state.is_resume = false;
    renderPlayer(albumMitTracks, 0, false);
    playTrack(albumMitTracks, 0);
  }
  lastAlbumSet(album.id);
}

/* ── AUDIO-WIEDERGABE (HSP-21/22/23) ─────────────────────────────────────── */
function playTrack(album, trackIdx) {
  const tracks = sortedTracks(album);
  const track = tracks[trackIdx];
  if (!track) return;

  /* Bestehendes Audio stoppen */
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
      dom.progress().style.width =
        ((audio.currentTime / audio.duration) * 100).toFixed(1) + '%';
    }
    /* Resume-Marke speichern (auf Track-Position, HSP-23) */
    resumeSet(album.id, track.position);
  });

  audio.addEventListener('ended', () => {
    const isLast = trackIdx >= tracks.length - 1;
    if (isLast) {
      /* HSP-23: Album vollständig → Marke löschen */
      resumeClear(album.id);
      /* HSP-21: Letzter Track → zurück zu Track 1 (kein Auto-Wechsel zum nächsten Album V1) */
      state.aktiv_track = 0;
      state.playing = false;
      renderPlayer(album, 0, false);
      updateMediaSession(album, tracks[0]);
      /* Kachel-Resume-Badge entfernen */
      document.querySelectorAll(`.kachel[data-album-id="${album.id}"]`).forEach(k =>
        k.classList.remove('resume')
      );
      document.querySelectorAll(`.kachel[data-album-id="${album.id}"] .resume-badge`).forEach(b =>
        b.style.display = 'none'
      );
    } else {
      /* Nächster Track */
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

  /* Track-Liste-Aktiv-Zeile aktualisieren */
  document.querySelectorAll('.track-item').forEach((li, i) =>
    li.classList.toggle('active', i === trackIdx)
  );

  /* Now-Playing */
  const np = dom.nowPlaying();
  np.textContent = '';
  const trackPiktos = track['pikto-hauptbegriffe'] || [];
  const trackLabel = track.titel || `Track ${track.position}`;
  np.appendChild(renderPiktoText(trackLabel, trackPiktos));

  /* Resume-State: nach erstem echten Play nicht mehr orange */
  state.is_resume = false;
  dom.btnPlay().classList.remove('resume');
  dom.btnPlay().setAttribute('aria-label', 'Pause');

  syncPlayPauseIcons();
  updateMediaSession(album, track);
  audio.play().catch(() => { /* Autoplay blockiert → still fail */ });
}

/* ── PLAY/PAUSE (HSP-21) ─────────────────────────────────────────────────── */
function togglePlayPause() {
  if (!state.aktiv) return;
  if (!state.audio || state.audio.ended) {
    playTrack(state.aktiv, state.aktiv_track);
    return;
  }
  if (state.playing) {
    state.audio.pause();
  } else {
    state.audio.play().catch(() => {});
  }
}

/* ── PREV-TRACK (HSP-21: Doppel-Tap innerhalb 3s → vorheriger Track) ────── */
function prevTrack() {
  if (!state.aktiv) return;
  const now = Date.now();
  const isDouble = (now - state.prev_tap_ts) < 3000;
  state.prev_tap_ts = now;

  const tracks = sortedTracks(state.aktiv);
  if (isDouble && state.aktiv_track > 0) {
    /* Doppel-Tap → wirklich vorheriger Track */
    state.aktiv_track -= 1;
    playTrack(state.aktiv, state.aktiv_track);
  } else {
    /* Einzel-Tap → Anfang des aktuellen Tracks */
    if (state.audio) {
      state.audio.currentTime = 0;
      if (!state.playing) state.audio.play().catch(() => {});
    } else {
      playTrack(state.aktiv, state.aktiv_track);
    }
  }
}

/* ── NEXT-TRACK (HSP-21) ─────────────────────────────────────────────────── */
function nextTrack() {
  if (!state.aktiv) return;
  const tracks = sortedTracks(state.aktiv);
  if (state.aktiv_track < tracks.length - 1) {
    state.aktiv_track += 1;
    playTrack(state.aktiv, state.aktiv_track);
  } else {
    /* Letzter Track: zurück zu Track 1 (HSP-21) */
    state.aktiv_track = 0;
    playTrack(state.aktiv, 0);
  }
}

/* ── MEDIASESSION-API (HSP-22) ───────────────────────────────────────────── */
function setupMediaSession() {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.setActionHandler('play', () => {
    if (state.audio) state.audio.play().catch(() => {});
  });
  navigator.mediaSession.setActionHandler('pause', () => {
    if (state.audio) state.audio.pause();
  });
  navigator.mediaSession.setActionHandler('previoustrack', prevTrack);
  navigator.mediaSession.setActionHandler('nexttrack', nextTrack);
}

function updateMediaSession(album, track) {
  if (!('mediaSession' in navigator)) return;
  const trackLabel = (track && track.titel) ? track.titel : `Track ${track ? track.position : 1}`;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: trackLabel,
    artist: album.voice === 'shimmer' ? 'Stigi & Co. (shimmer)' : 'Stigi & Co. (onyx)',
    album: `Folge ${album.nummer}: ${album.titel}`,
    artwork: album['cover-asset']
      ? [{ src: album['cover-asset'], sizes: '512x512', type: 'image/png' }]
      : []
  });
  navigator.mediaSession.playbackState = state.playing ? 'playing' : 'paused';
}

/* ── PLAYER-DEFAULT-ZUSTAND (HSP-2/23) ──────────────────────────────────── */
/**
 * Beim Start: prüfe auf Resume-State → orange Play + Kachel-Badge.
 * Wenn kein Resume → zuletzt gespieltes Album laden; wenn gar nichts → erstes Album.
 * HSP-17 / Befund 3: Manifest (mit tracks) vor renderPlayer nachladen.
 */
async function initPlayerDefault(alben) {
  if (alben.length === 0) return;

  /* Suche Album mit Resume-State */
  let resumeAlbum = null;
  let resumeTrackIdx = 0;
  for (const album of alben) {
    const r = resumeGet(album.id);
    if (r && r.track != null) {
      resumeAlbum = album;
      break;
    }
  }

  if (resumeAlbum) {
    /* Manifest nachladen, damit tracks verfügbar sind */
    const manifest = await loadAlbumManifest(resumeAlbum.id);
    const albumMitTracks = manifest ? { ...resumeAlbum, tracks: manifest.tracks } : resumeAlbum;
    const tracks = sortedTracks(albumMitTracks);
    const r = resumeGet(resumeAlbum.id);
    const idx = r ? tracks.findIndex(t => t.position === r.track) : -1;
    resumeTrackIdx = idx >= 0 ? idx : 0;

    state.aktiv = albumMitTracks;
    state.aktiv_track = resumeTrackIdx;
    state.is_resume = true;
    renderPlayer(albumMitTracks, resumeTrackIdx, true);
    renderKacheln(alben, resumeAlbum.id);
    /* Aktive Kachel markieren */
    setTimeout(() => {
      const kachel = document.querySelector(`.kachel[data-album-id="${resumeAlbum.id}"]`);
      if (kachel) kachel.classList.add('active');
    }, 0);
    return;
  }

  /* Kein Resume: zuletzt gespieltes Album oder erstes Album */
  const lastId = lastAlbumGet();
  const defaultAlbum = (lastId && alben.find(a => a.id === lastId)) || alben[0];

  /* Manifest nachladen, damit tracks verfügbar sind */
  const manifest = await loadAlbumManifest(defaultAlbum.id);
  const defaultMitTracks = manifest ? { ...defaultAlbum, tracks: manifest.tracks } : defaultAlbum;

  state.aktiv = defaultMitTracks;
  state.aktiv_track = 0;
  state.is_resume = false;
  renderPlayer(defaultMitTracks, 0, false);
  renderKacheln(alben, null);
  setTimeout(() => {
    const kachel = document.querySelector(`.kachel[data-album-id="${defaultAlbum.id}"]`);
    if (kachel) kachel.classList.add('active');
  }, 0);
}

/* ── DATEN LADEN (aus API oder Mock) ────────────────────────────────────── */
async function loadAlben() {
  try {
    const res = await fetch('/api/v1/hoerspiel/alben');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    /* Fallback auf Mock-Listen-Daten (Entry-Path-Probe) */
    return MOCK_ALBEN;
  }
}

/* HSP-17 / Befund 3: Manifest mit tracks nachladen (Liste hat keine tracks).
   Ergebnis wird per Album-ID gecacht — pro Session nur ein Fetch pro Album. */
async function loadAlbumManifest(albumId) {
  if (state.manifestCache[albumId]) return state.manifestCache[albumId];
  try {
    const res = await fetch('/api/v1/hoerspiel/alben/' + albumId + '/manifest');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const manifest = await res.json();
    state.manifestCache[albumId] = manifest;
    return manifest;
  } catch {
    /* Fallback auf Mock-Manifest (Entry-Path-Probe) */
    const mock = MOCK_MANIFESTE[albumId] || null;
    if (mock) state.manifestCache[albumId] = mock;
    return mock;
  }
}

/* ── CONTROLS VERDRAHTEN ─────────────────────────────────────────────────── */
function bindControls() {
  dom.btnPlay().addEventListener('click', togglePlayPause);
  dom.btnPrev().addEventListener('click', prevTrack);
  dom.btnNext().addEventListener('click', nextTrack);
}

/* ── INIT ────────────────────────────────────────────────────────────────── */
async function init() {
  setupMediaSession();
  bindControls();

  const raw = await loadAlben();
  /* Backend filtert bereits auf freigegebene Alben (HSP-5) — kein JS-Filter
     nötig. a.freigegeben wäre undefined in der Listen-Form → falsy → leere
     Liste (Befund 2). Absteigend nach nummer sortieren. */
  state.alben = [...raw].sort((a, b) => b.nummer - a.nummer);

  await initPlayerDefault(state.alben);
}

document.addEventListener('DOMContentLoaded', init);
