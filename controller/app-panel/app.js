// app.js — Panel-Logik der App-Panel-Seite (PANEL-1..11).
// PANEL-IDs verweisen auf specs/platform/app-panel.md.
// UMD-Wrapper: läuft im Browser (globalThis.panelLib) und in Node (require) —
// dieselbe Logik trägt index.html und reine Logik-Tests (PANEL-9).

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.panelLib = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ============================================================
  //  Defaults (CLAUDE.md §6 — Code-Defaults als Fallback, Daten in config.json)
  // ============================================================

  function configDefaults() {
    return {
      source_id:  'app-panel:demo',
      display_id: 'display:demo',
      router_url: '',
      // PANEL-5: Retry-Backoffs als Daten (CLAUDE.md §6 — Tuning extern).
      // Default = FIG-12-Pattern; config.json darf überschreiben.
      backoffs:   [200, 1000, 5000],
    };
  }

  // ============================================================
  //  PANEL-6 — Event-Bau
  // ============================================================

  function nowIso() {
    return new Date().toISOString();
  }

  function makeTileSelected(sourceId, tile) {
    // PANEL-6: Pflichtfelder source_id, ts, type + Descriptor app/view (+ query)
    var ev = {
      source_id: sourceId,
      ts:        nowIso(),
      type:      'tile_selected',
      app:       tile.app,
      view:      tile.view,
    };
    if (tile.query && typeof tile.query === 'object'
        && !Array.isArray(tile.query)) {
      ev.query = tile.query;
    }
    return ev;
  }

  function makePanelCleared(sourceId) {
    return {
      source_id: sourceId,
      ts:        nowIso(),
      type:      'panel_cleared',
    };
  }

  // ============================================================
  //  PANEL-7 — Descriptor-Validierung der tiles.json
  // ============================================================

  function isFlatPrimitive(v) {
    if (v === null || v === undefined) return false;
    if (typeof v === 'boolean') return false;
    return typeof v === 'string' || typeof v === 'number';
  }

  function validateTile(tile) {
    // PANEL-3 Pflichtfelder + PANEL-7 flacher Descriptor.
    if (!tile || typeof tile !== 'object') return 'tile ist kein Objekt';
    for (var k of ['key', 'app', 'view', 'label', 'icon']) {
      if (typeof tile[k] !== 'string' || tile[k].length === 0) {
        return 'Pflichtfeld "' + k + '" fehlt oder ist kein String';
      }
    }
    if (typeof tile.sichtbar !== 'boolean') {
      return 'sichtbar muss boolean sein';
    }
    if (tile.query !== undefined) {
      if (tile.query === null || typeof tile.query !== 'object'
          || Array.isArray(tile.query)) {
        return 'query muss ein flaches Objekt sein';
      }
      for (var qk in tile.query) {
        if (!Object.prototype.hasOwnProperty.call(tile.query, qk)) continue;
        if (!isFlatPrimitive(tile.query[qk])) {
          return 'query.' + qk + ' muss String oder Zahl sein '
               + '(keine verschachtelten Objekte/Listen)';
        }
      }
    }
    return null;
  }

  // ============================================================
  //  PANEL-11 — Stream-Payload-URL gegen Kachel-Konvention matchen
  // ============================================================
  //
  // Konvention (ROU-24 / URL-2): /display/<app>/<view>[?<query>].
  // Match auf flache Felder — Pfad-Segmente und alle Query-Paare gleich.

  function parseDisplayUrl(url) {
    if (typeof url !== 'string') return null;
    var m = /^\/display\/([^/?#]+)\/([^/?#]+)(\?.*)?$/.exec(url);
    if (!m) return null;
    var query = null;
    if (m[3]) {
      query = {};
      var qs = m[3].slice(1);
      if (qs.length > 0) {
        var pairs = qs.split('&');
        for (var i = 0; i < pairs.length; i++) {
          var eq = pairs[i].indexOf('=');
          if (eq < 0) continue;
          var k = decodeURIComponent(pairs[i].slice(0, eq));
          var v = decodeURIComponent(pairs[i].slice(eq + 1));
          query[k] = v;
        }
      }
    }
    return { app: m[1], view: m[2], query: query };
  }

  function tileMatchesUrl(tile, url) {
    var parsed = parseDisplayUrl(url);
    if (!parsed) return false;
    if (parsed.app !== tile.app) return false;
    if (parsed.view !== tile.view) return false;
    var tq = tile.query || null;
    var pq = parsed.query || null;
    // Beide Seiten: null vs. leeres Objekt zählt gleich.
    var tEmpty = !tq || Object.keys(tq).length === 0;
    var pEmpty = !pq || Object.keys(pq).length === 0;
    if (tEmpty && pEmpty) return true;
    if (tEmpty !== pEmpty) return false;
    var tk = Object.keys(tq).sort();
    var pk = Object.keys(pq).sort();
    if (tk.length !== pk.length) return false;
    for (var i = 0; i < tk.length; i++) {
      if (tk[i] !== pk[i]) return false;
      // Lockerer Stringvergleich — query kann aus tiles.json Zahlen tragen,
      // die per URL als String zurückkommen.
      if (String(tq[tk[i]]) !== String(pq[pk[i]])) return false;
    }
    return true;
  }

  function findActiveTile(tiles, payloadUrl) {
    if (!Array.isArray(tiles) || !payloadUrl) return null;
    for (var i = 0; i < tiles.length; i++) {
      if (tileMatchesUrl(tiles[i], payloadUrl)) return tiles[i];
    }
    return null;
  }

  // ============================================================
  //  PANEL-5 — POST mit Retry (FIG-12-Pattern, Backoff 200/1000/5000)
  // ============================================================

  // Code-Default-Fallback. SSoT für den Live-Wert ist `backoffs` in
  // config.json bzw. configDefaults() — diese Konstante existiert nur als
  // Sicherheitsnetz, falls postWithRetry ohne explizite Backoffs aufgerufen
  // wird (Tests, Legacy). CLAUDE.md §6 „Daten vs. Code".
  var BACKOFFS = [200, 1000, 5000];

  function postWithRetry(opts) {
    // opts: { fetchImpl, setTimeoutImpl, url, body, onSuccess, onDrop, backoffs? }
    var backoffs = Array.isArray(opts.backoffs) ? opts.backoffs : BACKOFFS;
    var attempt = 0;
    function fire() {
      opts.fetchImpl(opts.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(opts.body),
        keepalive: true,
      }).then(function (r) {
        if (r && r.ok) {
          if (opts.onSuccess) opts.onSuccess();
          return;
        }
        retry('HTTP ' + (r && r.status));
      }).catch(function (err) {
        retry(err && err.message || 'network');
      });
    }
    function retry(reason) {
      if (attempt >= backoffs.length) {
        if (opts.onDrop) opts.onDrop(reason);
        return;
      }
      var delay = backoffs[attempt];
      attempt += 1;
      opts.setTimeoutImpl(fire, delay);
    }
    fire();
  }

  // ============================================================
  //  PANEL-3/4/6 — Tile-Liste fürs Rendering vorbereiten
  // ============================================================
  //
  // Reine Liste der sichtbar:true-Kacheln in der Original-Reihenfolge. Die
  // eingebaute Aus-Kachel hängt der Renderer separat dran (PANEL-6) — nicht
  // in tiles.json, nicht über `sichtbar` steuerbar.

  function visibleTiles(tiles) {
    if (!Array.isArray(tiles)) return [];
    var out = [];
    for (var i = 0; i < tiles.length; i++) {
      if (tiles[i] && tiles[i].sichtbar === true) out.push(tiles[i]);
    }
    return out;
  }

  // ============================================================
  //  PANEL-11 — Stream-Handler-Fabrik (testbare Logik)
  // ============================================================
  //
  // Trennt die reine Logik (welche Kachel ist aktiv?) von der DOM-Anbindung
  // im Bootstrap. Ein Aufrufer übergibt `getTiles` und einen `onActive`-
  // Callback (Marker-Update). `onerror` ist ein No-Op: bei Stream-Abbruch
  // bleibt die letzte Markierung (DC-6); der Browser führt den
  // EventSource-Standard-Reconnect (DC-7) selbst.

  function makeStreamHandlers(getTiles, onActive) {
    function onMessage(ev) {
      var st = null;
      try { st = JSON.parse(ev.data); } catch (e) { return; }
      var payloadUrl = (st && st.payload && st.payload.url) || null;
      var active = findActiveTile(getTiles(), payloadUrl);
      onActive(active);
    }
    function onError() {
      // No-Op (DC-6): letzte Markierung bleibt, Browser reconnected (DC-7).
    }
    return { onMessage: onMessage, onError: onError };
  }

  // ============================================================
  //  PANEL-8 — Konsistenz-Check der Instanz-Konfiguration
  // ============================================================

  function checkConfigConsistency(cfg, panelIdFromHtml) {
    // PANEL-8: source_id im config.json muss zur data-panel-id im HTML passen
    // (Form `app-panel:<panelIdFromHtml>`). Diskrepanz = sichtbarer Fehler.
    if (!cfg || !cfg.source_id) return 'source_id fehlt in config.json';
    var expected = 'app-panel:' + panelIdFromHtml;
    if (cfg.source_id !== expected) {
      return 'source_id "' + cfg.source_id + '" passt nicht zur Panel-Identität "'
        + expected + '" (data-panel-id aus dem HTML)';
    }
    if (!cfg.display_id) return 'display_id fehlt in config.json';
    return null;
  }

  // ============================================================
  //  PANEL-10 — Wake-Lock und Vollbild als testbare Fabriken
  // ============================================================
  //
  // Bootstrap reicht echte `document` und `navigator` rein; Tests übergeben
  // Stub-Objekte und beobachten echte Aufrufe statt Quelltext-Pattern.

  function attachWakeLockImpl(opts) {
    // opts: { doc, nav }
    var doc = opts.doc;
    var nav = opts.nav;
    var lock = null;
    function request() {
      if (!nav || !('wakeLock' in nav) || !nav.wakeLock) return;
      try {
        var p = nav.wakeLock.request('screen');
        if (p && p.then) {
          p.then(function (l) { lock = l; }, function () {});
        }
      } catch (e) { /* still */ }
    }
    function onVisibility() {
      if (doc && doc.visibilityState === 'visible') request();
    }
    if (doc && doc.addEventListener) {
      doc.addEventListener('visibilitychange', onVisibility);
    }
    request();
    // Test-Hook: aktueller Lock + Trigger für visibilitychange.
    return { requestNow: request, onVisibility: onVisibility,
             getLock: function () { return lock; } };
  }

  function attachFullscreenImpl(opts) {
    // opts: { doc }
    var doc = opts.doc;
    function tryFullscreen() {
      if (!doc) return;
      // Guard: schon im Vollbild → nichts tun (PANEL-10).
      if (doc.fullscreenElement || doc.webkitFullscreenElement) return;
      var el = doc.documentElement;
      if (!el) return;
      var req = el.requestFullscreen || el.webkitRequestFullscreen;
      if (!req) return;
      try {
        var p = req.call(el);
        if (p && p.catch) p.catch(function () {});
      } catch (e) { /* still — Fehler dürfen die Seite nicht abreißen */ }
    }
    if (doc && doc.addEventListener) {
      doc.addEventListener('touchend', tryFullscreen, { passive: true });
      doc.addEventListener('click', tryFullscreen);
    }
    return { tryFullscreen: tryFullscreen };
  }

  // ============================================================
  //  API
  // ============================================================

  return {
    configDefaults: configDefaults,
    nowIso: nowIso,
    makeTileSelected: makeTileSelected,
    makePanelCleared: makePanelCleared,
    validateTile: validateTile,
    parseDisplayUrl: parseDisplayUrl,
    tileMatchesUrl: tileMatchesUrl,
    findActiveTile: findActiveTile,
    visibleTiles: visibleTiles,
    BACKOFFS: BACKOFFS,
    postWithRetry: postWithRetry,
    checkConfigConsistency: checkConfigConsistency,
    makeStreamHandlers: makeStreamHandlers,
    attachWakeLockImpl: attachWakeLockImpl,
    attachFullscreenImpl: attachFullscreenImpl,
  };
});


// ============================================================
//  Bootstrap (nur im Browser)
// ============================================================
//
// Wird in Node ignoriert, weil `document` nicht existiert. Logik oben ist
// pur und testbar; hier nur DOM-Verdrahtung.

(function () {
  'use strict';
  if (typeof document === 'undefined') return;  // Node-Tests ignorieren

  var panelLib = (typeof module === 'object' && module.exports)
    ? module.exports
    : (typeof globalThis !== 'undefined' ? globalThis.panelLib : null);
  if (!panelLib) return;

  // PANEL-2: Identität liest sich aus dem data-panel-id am body, das der
  // Router beim Ausliefern eingesetzt hat.
  var panelIdFromHtml = (document.body && document.body.dataset)
    ? document.body.dataset.panelId
    : null;

  function showError(msg) {
    var el = document.getElementById('error');
    if (!el) { console.error(msg); return; }
    el.textContent = msg;
    el.classList.remove('hidden');
  }

  // ============================================================
  //  PANEL-8 — config.json laden (PWA-4: pwaShared.loadPwaConfig)
  // ============================================================
  //
  // Bootstrap-Schicht: pwaShared.loadPwaConfig übernimmt Fetch, Merge und
  // stummen Fallback (CONFIG-4). Danach prüft checkConfigConsistency die
  // Kopplung source_id ↔ data-panel-id und macht Diskrepanzen im UI sichtbar.
  //
  // PANEL-8 (Diskrepanz source_id): wird als sichtbarer Fehler im UI
  // gezeigt (Spec-Vorgabe), das Panel läuft aber weiter. Begründung: ein
  // Panel mit falscher source_id schadet nicht (Router verwirft Events
  // mit unbekannter source_id), und ein harter Abbruch wäre eine
  // Spec-Verschärfung jenseits der „sichtbarer Fehler"-Forderung.

  function loadConfig() {
    return pwaShared.loadPwaConfig({
      defaults: panelLib.configDefaults(),
      onWarn: function () { console.warn.apply(console, arguments); },
    }).then(function (cfg) {
      if (panelIdFromHtml) {
        var err = panelLib.checkConfigConsistency(cfg, panelIdFromHtml);
        if (err) showError('Konfigurations-Fehler: ' + err);
      }
      return cfg;
    });
  }

  async function loadTiles() {
    try {
      var res = await fetch('./tiles.json', { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      var list = (data && data.tiles) || [];
      // Validierung — eine ungültige Kachel wirft die Seite nicht ab; sie
      // wird ausgelassen und der Fehler ist im UI sichtbar.
      var ok = [];
      for (var i = 0; i < list.length; i++) {
        var err = panelLib.validateTile(list[i]);
        if (err) {
          showError('tiles.json[' + i + ']: ' + err);
          continue;
        }
        ok.push(list[i]);
      }
      return ok;
    } catch (err) {
      console.warn('tiles.json konnte nicht geladen werden:', err);
      return [];
    }
  }

  // ============================================================
  //  Rendering (PANEL-3, PANEL-4, PANEL-6 Aus-Kachel)
  // ============================================================

  function renderGrid(tiles, onTap, onClear) {
    var grid = document.getElementById('grid');
    if (!grid) return;
    grid.innerHTML = '';
    var visible = panelLib.visibleTiles(tiles);
    for (var i = 0; i < visible.length; i++) {
      var t = visible[i];
      grid.appendChild(makeTileElement(t, function (tile) { onTap(tile); }));
    }
    // PANEL-6: eingebaute Aus-Kachel, immer letzte Position, nicht aus
    // tiles.json, nicht durch `sichtbar` beeinflussbar.
    grid.appendChild(makeAusKachel(onClear));
  }

  function makeTileElement(tile, onTap) {
    var el = document.createElement('button');
    el.type = 'button';
    el.className = 'tile';
    el.dataset.tileKey = tile.key;
    el.dataset.tileApp = tile.app;
    el.dataset.tileView = tile.view;
    var icon = document.createElement('img');
    icon.src = tile.icon;
    icon.alt = '';
    icon.className = 'tile-icon';
    var label = document.createElement('span');
    label.className = 'tile-label';
    label.textContent = tile.label;
    el.appendChild(icon);
    el.appendChild(label);
    el.addEventListener('click', function () { onTap(tile); });
    return el;
  }

  function makeAusKachel(onClear) {
    var el = document.createElement('button');
    el.type = 'button';
    el.className = 'tile tile-aus';
    el.dataset.tileKey = '__aus__';
    var icon = document.createElement('span');
    icon.className = 'tile-icon';
    icon.innerHTML = '<svg viewBox="0 0 64 64" aria-hidden="true">'
      + '<circle cx="32" cy="32" r="22" fill="none" stroke="#888" stroke-width="4"/>'
      + '<line x1="32" y1="14" x2="32" y2="32" stroke="#888" stroke-width="4" stroke-linecap="round"/>'
      + '</svg>';
    var label = document.createElement('span');
    label.className = 'tile-label';
    label.textContent = 'Aus';
    el.appendChild(icon);
    el.appendChild(label);
    el.addEventListener('click', function () { onClear(); });
    return el;
  }

  // ============================================================
  //  PANEL-11 — Aktiv-Markierung aus SSE-Stream
  // ============================================================

  function attachStream(displayId, getTiles) {
    if (typeof EventSource === 'undefined') return null;
    if (!displayId) return null;
    var url = '/api/v1/displays/' + encodeURIComponent(displayId) + '/events';
    var es = new EventSource(url);
    var handlers = panelLib.makeStreamHandlers(getTiles, updateActiveMarker);
    es.addEventListener('message', handlers.onMessage);
    // Stream-Abbruch: nichts unternehmen (DC-6-Linie); EventSource-Reconnect
    // läuft Browser-seitig (DC-7). Expliziter Handler dokumentiert die
    // Absicht — kein updateActiveMarker(null), kein Reset der active-Klasse.
    es.onerror = handlers.onError;
    return es;
  }

  function updateActiveMarker(activeTile) {
    var els = document.querySelectorAll('#grid .tile');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var key = el.dataset.tileKey;
      if (activeTile && key === activeTile.key) {
        el.classList.add('active');
      } else {
        el.classList.remove('active');
      }
    }
  }

  // ============================================================
  //  PANEL-5 — Tap → POST /api/v1/events mit Retry
  // ============================================================

  function sendEvent(cfg, body) {
    // Leerer router_url → same-origin (Browser nimmt die Origin der Seite).
    // Funktioniert für jeden Host (hub.local, IP, beliebiger DNS-Name) und
    // verhindert CORS-Blocks, wenn die Seite unter einem anderen Host
    // geladen wird als der hartkodierte Router-URL. Refs #128.
    var base = cfg.router_url ? cfg.router_url.replace(/\/+$/, '') : '';
    var url = base + '/api/v1/events';
    panelLib.postWithRetry({
      fetchImpl: function (u, init) { return fetch(u, init); },
      setTimeoutImpl: function (fn, ms) { setTimeout(fn, ms); },
      url: url,
      body: body,
      // PANEL-5 / Tuning extern: Backoffs aus config.json, sonst Code-Default.
      backoffs: cfg.backoffs,
      onSuccess: function () { /* still */ },
      onDrop: function (reason) {
        console.warn('Event-Drop nach Retry-Schema:', reason, body);
      },
    });
  }

  // ============================================================
  //  PANEL-10 — Wake-Lock + Vollbild beim ersten Gesture (DC-11-Pattern)
  // ============================================================

  function attachWakeLock() {
    panelLib.attachWakeLockImpl({ doc: document, nav: navigator });
  }

  function attachFullscreenOnGesture() {
    panelLib.attachFullscreenImpl({ doc: document });
  }

  // ============================================================
  //  Boot
  // ============================================================

  (async function boot() {
    var cfg = await loadConfig();
    var tiles = await loadTiles();
    renderGrid(tiles,
      function onTap(tile) {
        sendEvent(cfg, panelLib.makeTileSelected(cfg.source_id, tile));
      },
      function onClear() {
        sendEvent(cfg, panelLib.makePanelCleared(cfg.source_id));
      });
    attachWakeLock();
    attachFullscreenOnGesture();
    attachStream(cfg.display_id, function () { return tiles; });
  })();

  // Service Worker (PANEL-10 PWA-Begleitdatei). Fehler still ignorieren.
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('./sw.js').catch(function (err) {
        console.warn('SW-Registrierung fehlgeschlagen:', err);
      });
    });
  }
})();
