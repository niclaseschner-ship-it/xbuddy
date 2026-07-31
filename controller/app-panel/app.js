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
      // display_id ist bewusst nicht mehr hier (PANEL-8, Nic-Entscheid 2026-06-08 / #414):
      // der Panel-Code zieht display_id beim Bootstrap per ROU-32 vom Router.
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
    for (var k of ['key', 'app', 'view', 'label']) {
      if (typeof tile[k] !== 'string' || tile[k].length === 0) {
        return 'Pflichtfeld "' + k + '" fehlt oder ist kein String';
      }
    }
    // PANEL-3: icons muss ein nicht-leeres Array von Strings sein (≥1, max 3).
    if (!Array.isArray(tile.icons) || tile.icons.length === 0) {
      return 'Pflichtfeld "icons" fehlt oder ist kein Array (≥1 Eintrag erwartet)';
    }
    for (var i = 0; i < tile.icons.length; i++) {
      if (typeof tile.icons[i] !== 'string' || tile.icons[i].length === 0) {
        return '"icons[' + i + ']" ist kein nicht-leerer String';
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
    var m = /^\/display\/([^/?#]+)\/(.+?)(\?[^#]*)?$/.exec(url);
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
  //  PANEL-6 (#136) — Aus-Kachel: ARASAAC-Icon-Konstanté
  // ============================================================
  //
  // ARASAAC ID 8252 = „aus" (Wort→ID aus pictogram_cache.json, Stand 2026-06-02).
  // Pfad relativ zur Icon-Basis (ICONS-5, ROU-26). Wer das Aus-Symbol tauschen
  // will, ändert genau diese Konstante — kein Suchen im Code nötig.
  var AUS_ICON_PATH = 'arasaac/8252.png'; // PANEL-6: ARASAAC 8252='aus'; Aus-Symbol hier änderbar

  // ============================================================
  //  PANEL-3 (#136) — Icon-Basis-URL-Auflösung
  // ============================================================
  //
  // Baut die Icon-Basis für die zentrale ARASAAC-Bibliothek (ICONS-5, ROU-26).
  // Leerer router_url → same-origin (kein Prefix). Muster analog sendEvent
  // (router_url-Base-Auflösung aus dem Bootstrap, Z.514-518).

  function resolveIconBase(routerUrl) {
    var base = (typeof routerUrl === 'string' && routerUrl)
      ? routerUrl.replace(/\/+$/, '')
      : '';
    return base + '/display/_shared/icons/';
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
  //  PANEL-3/6 (#136) — Render-Funktionen (Library-Schicht)
  // ============================================================
  //
  // Parametrisiert: document + cfg/iconBaseStr als Argumente, keine globalen
  // Abhängigkeiten. Damit über Node via panelLib.makeTileElement(doc, …) testbar —
  // analoges Muster zu resolveIconBase (bereits in Library-Schicht).

  function makeTileElement(doc, tile, onTap, iconBaseStr) {
    var el = doc.createElement('button');
    el.type = 'button';
    el.className = 'tile';
    el.dataset.tileKey = tile.key;
    el.dataset.tileApp = tile.app;
    el.dataset.tileView = tile.view;
    // PANEL-3 (#136): icons[] — mehrere <img> nebeneinander im Icon-Slot.
    var iconSlot = doc.createElement('span');
    iconSlot.className = 'tile-icons';
    for (var i = 0; i < tile.icons.length; i++) {
      var img = doc.createElement('img');
      img.src = iconBaseStr + tile.icons[i];
      img.alt = '';
      img.className = 'tile-icon-img';
      // PANEL-6 (#136): Icon lädt nicht → Slot leeren; kein Broken-Image-Placeholder,
      // Kachel bleibt funktionsfähig (Label + Tap).
      img.onerror = function () { this.parentNode && this.parentNode.removeChild(this); };
      iconSlot.appendChild(img);
    }
    var label = doc.createElement('span');
    label.className = 'tile-label';
    label.textContent = tile.label;
    el.appendChild(iconSlot);
    el.appendChild(label);
    el.addEventListener('click', function () { onTap(tile); });
    return el;
  }

  function makeAusKachel(doc, onClear, iconBaseStr) {
    // PANEL-6 (#136): Aus-Kachel mit ARASAAC-Icon AUS_ICON_PATH (= „aus") aus der
    // zentralen Bibliothek (ICONS-5, ROU-26). Konstante AUS_ICON_PATH —
    // der eine Änder-Ort für das Aus-Symbol.
    var el = doc.createElement('button');
    el.type = 'button';
    el.className = 'tile tile-aus';
    el.dataset.tileKey = '__aus__';
    var iconSlot = doc.createElement('span');
    iconSlot.className = 'tile-icons';
    var img = doc.createElement('img');
    img.src = iconBaseStr + AUS_ICON_PATH;
    img.alt = '';
    img.className = 'tile-icon-img';
    // PANEL-6 (#136): Icon lädt nicht → Slot leeren; Kachel bleibt funktionsfähig.
    img.onerror = function () { this.parentNode && this.parentNode.removeChild(this); };
    iconSlot.appendChild(img);
    var label = doc.createElement('span');
    label.className = 'tile-label';
    label.textContent = 'Aus';
    el.appendChild(iconSlot);
    el.appendChild(label);
    el.addEventListener('click', function () { onClear(); });
    return el;
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

  function makeStreamHandlers(getTiles, onActive, onAlive) {
    function onMessage(ev) {
      var st = null;
      try { st = JSON.parse(ev.data); } catch (e) { return; }
      // Lebenszeichen für Watchdog — jedes data-Event (auch heartbeat).
      if (onAlive) onAlive();
      // Heartbeat-Events (ROU-22 2026-06-18) sind reine Lebenszeichen; KEIN
      // updateActiveMarker(null), sonst flackert die active-Klasse weg.
      if (st && st.type === 'heartbeat') return;
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
    // Die frühere zweite Probe gegen cfg.display_id entfällt (PANEL-8, #414):
    // display_id kommt nicht mehr aus config.json, sondern per ROU-32 vom Router.
    if (!cfg || !cfg.source_id) return 'source_id fehlt in config.json';
    var expected = 'app-panel:' + panelIdFromHtml;
    if (cfg.source_id !== expected) {
      return 'source_id "' + cfg.source_id + '" passt nicht zur Panel-Identität "'
        + expected + '" (data-panel-id aus dem HTML)';
    }
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
  //  PANEL-12 — Geometrie-Berechnung: scroll-freies Grid-Layout
  // ============================================================
  //
  // Berechnet Spalten- und Zeilenzahl für M Kacheln, sodass alle ins
  // Viewport passen (scrollHeight <= clientHeight, PANEL-12).
  //
  // Kandidaten-Suche: c = 1..M → rows = ceil(M/c).
  // Score minimiert Abweichung vom Ideal-Seitenverhältnis (0.92, etwas
  // weniger als 1:1 wegen Labels unter den Icons) und Grid-Füllgrad-Penalty
  // (leere Zellen in letzter Reihe).
  //
  // Mindestbreite von Kacheln (160px): wenn kein Kandidat passt (extrem
  // kleiner Viewport), schrumpfen Kacheln ohne Scroll — Mindestbreite
  // wird in diesem Fall ignoriert (Fallback = ganzer Viewport als eine Reihe).
  //
  // Exportiert für node-Tests (AC3: geändertes Seitenverhältnis → andere Spalten).

  var IDEAL_TILE_RATIO = 0.92;  // Breite/Höhe einer Kachel — etwas breiter als quadratisch
  var TILE_MIN_W = 160;         // Komfort-Mindestbreite; wird fallen gelassen wenn nötig
  var GRID_GAP = 12;            // px — muss mit #grid gap in style.css übereinstimmen
  var GRID_PAD = 16;            // px — muss mit #grid padding in style.css übereinstimmen

  function computeGridGeometry(M, vpW, vpH) {
    // M = Gesamtzahl Kacheln (sichtbare tiles.json + Aus-Kachel).
    // vpW, vpH = verfügbare Breite/Höhe für das Grid-Element.
    // Gibt zurück: { cols, rows } — kleinstes Score-Minimum.
    if (!M || M < 1) return { cols: 1, rows: 1 };

    var innerW = vpW - 2 * GRID_PAD;
    var innerH = vpH - 2 * GRID_PAD;

    var best = null;
    var bestScore = Infinity;

    for (var c = 1; c <= M; c++) {
      var rows = Math.ceil(M / c);
      // Kachelgröße bei diesem Layout
      var tileW = (innerW - (c - 1) * GRID_GAP) / c;
      var tileH = (innerH - (rows - 1) * GRID_GAP) / rows;
      // Mindestbreiten-Guard (Komfort-Garantie). Wenn kein Kandidat passt,
      // wird dieses Guard unten nach der Schleife aufgehoben.
      if (tileW < TILE_MIN_W) continue;
      // Score: |log(tatsächliches_ratio / ideal)| + Leerfeld-Penalty
      var actualRatio = tileW / tileH;
      var ratioPenalty = Math.abs(Math.log(actualRatio / IDEAL_TILE_RATIO));
      var emptyPenalty = ((c * rows - M) / M) * 1.5;
      var score = ratioPenalty + emptyPenalty;
      if (score < bestScore) {
        bestScore = score;
        best = { cols: c, rows: rows };
      }
    }

    if (!best) {
      // PANEL-12 Fallback: Mindestbreite ignorieren, kein Scroll.
      // Wähle c = 1..M, diesmal ohne Mindestbreiten-Guard.
      bestScore = Infinity;
      for (var c2 = 1; c2 <= M; c2++) {
        var rows2 = Math.ceil(M / c2);
        var tileW2 = (innerW - (c2 - 1) * GRID_GAP) / c2;
        var tileH2 = (innerH - (rows2 - 1) * GRID_GAP) / rows2;
        var actualRatio2 = tileW2 / tileH2;
        var ratioPenalty2 = Math.abs(Math.log(actualRatio2 / IDEAL_TILE_RATIO));
        var emptyPenalty2 = ((c2 * rows2 - M) / M) * 1.5;
        var score2 = ratioPenalty2 + emptyPenalty2;
        if (score2 < bestScore) {
          bestScore = score2;
          best = { cols: c2, rows: rows2 };
        }
      }
    }

    return best || { cols: Math.ceil(Math.sqrt(M)), rows: Math.ceil(M / Math.ceil(Math.sqrt(M))) };
  }

  // ============================================================
  //  PANEL-12 — Safe-Area-Insets lesen (CSS-Variable-Form)
  // ============================================================
  //
  // Liest die vier Safe-Area-Insets aus den CSS-Variablen, die style.css
  // via env() auf :root setzt. Fallback 0 wenn die Variable fehlt oder
  // nicht parsebar ist (Geräte ohne Notch, Node-Tests ohne CSS).
  // ctx ist optional: { doc } für Tests; im Browser entfällt der Parameter.

  function _parseInsetPx(str) {
    if (!str) return 0;
    var n = parseFloat(str);
    return isNaN(n) ? 0 : n;
  }

  function getViewportDimensions(ctx) {
    // ctx ist optional: { doc, win } für Tests; im Browser werden globale
    // document/window verwendet.
    var doc = (ctx && ctx.doc) ? ctx.doc : /* istanbul ignore next */ document;
    var win = (ctx && ctx.win) ? ctx.win : /* istanbul ignore next */ window;
    var style = doc.documentElement
      ? (doc.documentElement.computedStyle ||
         (typeof getComputedStyle !== 'undefined'
           ? getComputedStyle(doc.documentElement)
           : null))
      : null;
    // Falls kein echtes getComputedStyle vorhanden (Node-Test mit Stub),
    // lesen wir die CSS-Variable direkt aus dem documentElement.style
    // (das setzen Test-Stubs, falls sie Insets simulieren wollen).
    function readVar(name) {
      if (style && style.getPropertyValue) {
        return _parseInsetPx(style.getPropertyValue(name));
      }
      // Stub-Fallback: --safe-area-inset-* direkt am documentElement.style
      if (doc.documentElement && doc.documentElement.style
          && doc.documentElement.style[name] !== undefined) {
        return _parseInsetPx(doc.documentElement.style[name]);
      }
      return 0;
    }
    var insetTop    = readVar('--safe-area-inset-top');
    var insetBottom = readVar('--safe-area-inset-bottom');
    var insetLeft   = readVar('--safe-area-inset-left');
    var insetRight  = readVar('--safe-area-inset-right');
    return {
      vpW: win.innerWidth  - insetLeft  - insetRight,
      vpH: win.innerHeight - insetTop   - insetBottom,
    };
  }

  // ============================================================
  //  PANEL-12 — Grid-Geometrie auf das DOM-Grid anwenden
  // ============================================================
  //
  // Liest Anzahl der Kacheln aus dem Grid-Element, berechnet cols/rows
  // aus dem aktuellen Viewport (abzüglich Safe-Area-Insets) und setzt
  // grid-template-columns/-rows.
  // Wird beim Laden und bei resize aufgerufen (Bootstrap-IIFE).
  // ctx ist optional: {doc, win} für Tests; im Browser entfällt der Parameter
  // und die globalen document/window werden verwendet.

  function applyGridGeometry(ctx) {
    var doc = (ctx && ctx.doc) ? ctx.doc : /* istanbul ignore next */ document;
    var win = (ctx && ctx.win) ? ctx.win : /* istanbul ignore next */ window;
    var grid = doc.getElementById('grid');
    if (!grid) return;
    var M = grid.children.length;
    if (M < 1) return;
    // PANEL-12 Safe-Area: Insets abziehen, nicht padden.
    var dims = getViewportDimensions({ doc: doc, win: win });
    var vpW = dims.vpW;
    var vpH = dims.vpH;
    // #error-Banner abziehen, falls sichtbar
    var errEl = doc.getElementById('error');
    if (errEl && !errEl.classList.contains('hidden')) {
      vpH -= errEl.offsetHeight || 0;
    }
    var geom = computeGridGeometry(M, vpW, vpH);
    grid.style.gridTemplateColumns = 'repeat(' + geom.cols + ', 1fr)';
    grid.style.gridTemplateRows    = 'repeat(' + geom.rows + ', 1fr)';
    // PANEL-12: Grid-Höhe = vpH (Safe-Area-bereinigt) minus error-Banner;
    // overflow:hidden verhindert Scroll.
    grid.style.height = vpH + 'px';
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
    resolveIconBase: resolveIconBase,
    AUS_ICON_PATH: AUS_ICON_PATH,
    makeTileElement: makeTileElement,
    makeAusKachel: makeAusKachel,
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
    computeGridGeometry: computeGridGeometry,
    applyGridGeometry: applyGridGeometry,
    getViewportDimensions: getViewportDimensions,
    // Konstanten für Tests (AC3-Invarianten).
    GRID_GAP: GRID_GAP,
    GRID_PAD: GRID_PAD,
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

  // SHELL-4 / E2-Sender (T1519): ingest_url-Query-Param — wenn das Panel als
  // Iframe in der Heim-Shell läuft, setzt das Template
  // `?ingest_url=/shell/<panel_id>/events` in den Iframe-src. sendEvent postet
  // dann direkt an den seiten-Ingest statt an den Router (/api/v1/events).
  // Standalone-Panel (kein Param) verhält sich unverändert (AC2 Kein-Regress).
  var _ingestUrlFromParam = (typeof window !== 'undefined' && window.location && window.location.search)
    ? new URLSearchParams(window.location.search).get('ingest_url')
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
  //
  // Bootstrap delegiert vollständig an die Library-Funktionen (DRY).
  // Keine zweite Implementierung hier — nur DOM-Verdrahtung.

  function renderGrid(tiles, cfg, onTap, onClear) {
    var grid = document.getElementById('grid');
    if (!grid) return;
    grid.innerHTML = '';
    var visible = panelLib.visibleTiles(tiles);
    var base = panelLib.resolveIconBase(cfg && cfg.router_url);
    for (var i = 0; i < visible.length; i++) {
      var t = visible[i];
      grid.appendChild(panelLib.makeTileElement(document, t, function (tile) { onTap(tile); }, base));
    }
    // PANEL-6: eingebaute Aus-Kachel, immer letzte Position, nicht aus
    // tiles.json, nicht durch `sichtbar` beeinflussbar.
    grid.appendChild(panelLib.makeAusKachel(document, onClear, base));
  }

  // ============================================================
  //  PANEL-11 — Aktiv-Markierung aus SSE-Stream
  // ============================================================

  // PANEL-11 Watchdog-State — letzter Heartbeat/Event für display-Stream.
  var panel11LastSeen = 0;
  var panel11Stream = null;
  var panel11Args = null;  // {displayId, getTiles} für Reconnect

  function attachStream(displayId, getTiles) {
    if (typeof EventSource === 'undefined') return null;
    if (!displayId) return null;
    panel11Args = { displayId: displayId, getTiles: getTiles };
    var url = '/api/v1/displays/' + encodeURIComponent(displayId) + '/events';
    var es = new EventSource(url);
    var handlers = panelLib.makeStreamHandlers(
      getTiles,
      updateActiveMarker,
      function () { panel11LastSeen = Date.now(); }
    );
    es.addEventListener('message', handlers.onMessage);
    // Stream-Abbruch: nichts unternehmen (DC-6-Linie); EventSource-Reconnect
    // läuft Browser-seitig (DC-7). Watchdog unten reconnectet bei stillem Tod.
    es.onerror = handlers.onError;
    panel11LastSeen = Date.now();
    panel11Stream = es;
    return es;
  }

  // PANEL-11 Watchdog (analog HSP-Audio R6, 2026-06-18): bei stillem
  // Verbindungs-Tod auf Mobile-Browser feuert onerror nicht zuverlässig.
  // Prüfe alle 10s ob Heartbeat innerhalb 30s kam, sonst reconnect.
  var PANEL11_WATCHDOG_MS = 30000;
  setInterval(function () {
    if (document.visibilityState !== 'visible') return;
    if (!panel11Args || !panel11Stream) return;
    if (Date.now() - panel11LastSeen <= PANEL11_WATCHDOG_MS) return;
    console.warn('PANEL-11 SSE Watchdog: ' +
                 Math.round((Date.now() - panel11LastSeen) / 1000) +
                 's still — Reconnect.');
    try { panel11Stream.close(); } catch (e) {}
    panel11Stream = attachStream(panel11Args.displayId, panel11Args.getTiles);
  }, 10000);

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
  //  HSP-42 / PANEL-13 — Audio-Source-Push aus HSP-Services
  // ============================================================
  //
  // Pattern aus PANEL-11 (Z. 744+) wiederverwendet. Pro HSP-Instanz eine
  // EventSource zu /api/v1/hoerspiel/<kind_id>/audio-stream. Bei
  // audio_play-Event setzt das <audio id="hsp-audio">-Element die neue
  // Source und ruft play(). Sticky-Activation muss zuvor durch einen
  // Kachel-Tap gesetzt worden sein (primeSilentAudio).
  //
  // INST-1 (#1656): die Instanz-Liste kommt server-injiziert aus
  // instanzen.json (window.__HSP_INSTANZEN__, gesetzt in index.html via
  // render_app_panel_index) — statt hier hartkodiert (Drift-Fix: niclas
  // erscheint). Fehlt die Injektion (alter Cache / Standalone), fällt es auf
  // paula+neko zurück, damit die Audio-Streams nicht komplett tot sind.
  var HSP_KIND_IDS = (Array.isArray(window.__HSP_INSTANZEN__) &&
                      window.__HSP_INSTANZEN__.length)
    ? window.__HSP_INSTANZEN__.filter(function (s) { return typeof s === 'string' && s; })
    : ['paula', 'neko'];
  var hspStreams = {};
  // Letztes empfangenes SSE-Lebenszeichen je kind_id (Date.now()-Wert).
  // Wird bei jedem Server-Heartbeat (15s) und jedem audio_play-Event gesetzt.
  // Watchdog vergleicht gegen now() und reconnectet stillgewordene Verbindungen.
  var hspLastSeen = {};
  var HSP_HEARTBEAT_WATCHDOG_MS = 30000;  // 30s — Server-Heartbeat ist 15s

  function primeSilentAudio() {
    var a = document.getElementById('hsp-audio');
    if (!a) return;
    // Schon aktiv und nicht pausiert? Nichts tun (Empirie 2026-06-17 R6:
    // kurzer Loop hält Browser-Idle-Detection wach).
    if (a.src && !a.paused) return;
    a.src = './silent.mp3';
    a.loop = true;
    var p = a.play();
    if (p && typeof p.catch === 'function') {
      p.catch(function (err) {
        // Erst-Tap blockt mit NotAllowedError → das ist OK, der nächste
        // Kachel-Tap wird die Geste tragen.
        console.warn('silent-prime blockt:', err && err.name || err);
      });
    }
  }

  function showHspTapPrompt(queuedUrl) {
    var prompt = document.getElementById('hsp-tap-prompt');
    if (!prompt) return;
    prompt.style.display = 'flex';
    prompt.classList.remove('hidden');
    var handler = function () {
      var a = document.getElementById('hsp-audio');
      if (!a) return;
      a.pause();
      a.src = queuedUrl;
      a.loop = false;
      var p = a.play();
      if (p && typeof p.catch === 'function') {
        p.catch(function (err) {
          console.warn('manual play() failed:', err && err.name || err);
        });
      }
      prompt.style.display = 'none';
      prompt.classList.add('hidden');
      prompt.removeEventListener('click', handler);
    };
    prompt.addEventListener('click', handler);
  }

  function onHspAudioEvent(event) {
    if (!event || typeof event.type !== 'string') return;
    var a = document.getElementById('hsp-audio');
    if (!a) return;

    if (event.type === 'audio_play') {
      // Sauber-Reset gegen Source-Wechsel-Glitch (Codex-Pass-2-R2).
      a.pause();
      a.src = '';
      a.loop = false;
      a.src = event.audio_url;
      var p = a.play();
      if (p && typeof p.catch === 'function') {
        p.catch(function (err) {
          if (err && err.name === 'NotAllowedError') {
            // iOS-WebKit-Sticky-Activation hat eventuell ausgelaufen.
            showHspTapPrompt(event.audio_url);
          } else {
            console.warn('hsp-audio play() error:', err);
          }
        });
      }
      return;
    }

    if (event.type === 'audio_pause') {
      // Lokaler Pause-Button am Kinder-Display pausiert auch Panel-Audio.
      a.pause();
      return;
    }

    if (event.type === 'audio_resume') {
      // play() ohne src-Reset — laufender Track fortsetzen.
      var pr = a.play();
      if (pr && typeof pr.catch === 'function') {
        pr.catch(function (err) {
          if (err && err.name === 'NotAllowedError') {
            showHspTapPrompt(a.src);
          }
        });
      }
      return;
    }
  }

  function attachHspAudioStream(kindId) {
    if (typeof EventSource === 'undefined') return null;
    var url = '/api/v1/hoerspiel/' + encodeURIComponent(kindId) + '/audio-stream';
    var es = new EventSource(url);
    es.addEventListener('message', function (e) {
      // Jeder data-Event (auch Heartbeat) ist ein Lebenszeichen für den Watchdog.
      hspLastSeen[kindId] = Date.now();
      try {
        var data = JSON.parse(e.data);
        if (data && data.type === 'heartbeat') return;  // Heartbeat-only, kein audio
        onHspAudioEvent(data);
      } catch (err) {
        console.warn('hsp-audio-stream: parse-Fehler', err);
      }
    });
    es.onerror = function () {
      console.warn('hsp-audio-stream ' + kindId + ' error — Browser reconnectet (DC-7).');
    };
    // Initialer Lastseen-Stempel beim Öffnen, damit Watchdog nicht sofort feuert.
    hspLastSeen[kindId] = Date.now();
    return es;
  }

  function attachHspAudioStreams() {
    HSP_KIND_IDS.forEach(function (kindId) {
      if (hspStreams[kindId]) {
        try { hspStreams[kindId].close(); } catch (e) {}
      }
      hspStreams[kindId] = attachHspAudioStream(kindId);
    });
  }

  // Watchdog: prüft alle 10s ob jeder Stream innerhalb der letzten 30s ein
  // Lebenszeichen (Heartbeat oder Event) hatte. Server-Heartbeat ist 15s,
  // also sollten neue Events spätestens nach 15-20s ankommen. Wenn nichts
  // kam, ist die Verbindung still gestorben — neu öffnen.
  // Adressiert R6 aus Track E: Mobile-Browser kappen EventSource im
  // Hintergrund ohne onerror auszulösen.
  setInterval(function () {
    if (document.visibilityState !== 'visible') return;  // im Hintergrund sowieso egal
    var now = Date.now();
    HSP_KIND_IDS.forEach(function (kindId) {
      var seen = hspLastSeen[kindId] || 0;
      if (now - seen > HSP_HEARTBEAT_WATCHDOG_MS) {
        console.warn('hsp-audio-stream ' + kindId + ' Watchdog: ' +
                     Math.round((now - seen) / 1000) + 's still — Reconnect.');
        if (hspStreams[kindId]) {
          try { hspStreams[kindId].close(); } catch (e) {}
        }
        hspStreams[kindId] = attachHspAudioStream(kindId);
      }
    });
  }, 10000);

  // visibilitychange — EventSource wird auf iOS/Android im Hintergrund
  // pausiert (siehe display-client.md:101-108); beim Zurück-in-den-
  // Vordergrund neu öffnen.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      attachHspAudioStreams();
    }
  });

  // ============================================================
  //  PANEL-5 — Tap → POST /api/v1/events mit Retry
  // ============================================================

  function sendEvent(cfg, body) {
    // SHELL-4 / E2-Sender (T1519): wenn das Panel in der Heim-Shell-Iframe
    // läuft, steht _ingestUrlFromParam auf dem seiten-Ingest
    // (/shell/<panel_id>/events). Dann postet sendEvent dorthin direkt.
    // Standalone-Panel (kein ingest_url-Param): unverändertes Verhalten —
    // base + '/api/v1/events' → Router (AC2 Kein-Regress, Refs #128).
    var url;
    if (_ingestUrlFromParam) {
      url = _ingestUrlFromParam;
    } else {
      // Leerer router_url → same-origin (Browser nimmt die Origin der Seite).
      // Funktioniert für jeden Host (hub.local, IP, beliebiger DNS-Name) und
      // verhindert CORS-Blocks, wenn die Seite unter einem anderen Host
      // geladen wird als der hartkodierte Router-URL. Refs #128.
      var base = cfg.router_url ? cfg.router_url.replace(/\/+$/, '') : '';
      url = base + '/api/v1/events';
    }
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
    // PANEL-10 embedded-Ausnahme (SHELL-11): eingebettet in Shell-Iframe
    // (window.self !== window.top) → kein Panel-Eigen-Vollbild anhängen.
    // Standalone-Panel-Geräte (window.self === window.top) behalten PANEL-10 unverändert.
    if (window.self !== window.top) return;
    panelLib.attachFullscreenImpl({ doc: document });
  }

  // ============================================================
  //  Boot
  // ============================================================

  (async function boot() {
    var cfg = await loadConfig();
    var tiles = await loadTiles();
    renderGrid(tiles, cfg,
      function onTap(tile) {
        // PANEL-11 — Optimistisches lokales Update (Spec PANEL-11, Refs #959):
        // Markierung sofort auf getappte Kachel setzen, BEVOR der POST-Roundtrip
        // abgeschlossen ist. Stream bleibt die Wahrheit; bei Diskrepanz korrigiert
        // das nächste Stream-Ereignis.
        updateActiveMarker(tile);
        // PANEL-13 — Silent-Audio-Prime bei JEDEM Kachel-Tap (HSP-42 + Empirie
        // 2026-06-17). Browser-Sticky-Activation wird durch die User-Geste
        // gesetzt; spätere SSE-getriggerte Audio-Source-Updates spielen ohne
        // weitere Geste, weil die Tab-Session activated bleibt.
        primeSilentAudio();
        sendEvent(cfg, panelLib.makeTileSelected(cfg.source_id, tile));
      },
      function onClear() {
        // PANEL-11 — Optimistisches lokales Update (Spec PANEL-11, Refs #959):
        // Markierung sofort entfernen, BEVOR der POST-Roundtrip abgeschlossen ist.
        // Stream bleibt die Wahrheit; bei Diskrepanz korrigiert das nächste
        // Stream-Ereignis.
        updateActiveMarker(null);
        sendEvent(cfg, panelLib.makePanelCleared(cfg.source_id));
      });
    // PANEL-12: Geometrie nach Render berechnen, bei resize neu rechnen.
    panelLib.applyGridGeometry();
    window.addEventListener('resize', function () { panelLib.applyGridGeometry(); });
    attachWakeLock();
    attachFullscreenOnGesture();
    // HSP-42 — EventSource zu beiden HSP-Services für Audio-Source-Push.
    attachHspAudioStreams();
  })();

  // Service Worker (PANEL-10 PWA-Begleitdatei). Fehler still ignorieren.
  if ('serviceWorker' in navigator) {
    // #1455 — klebenden alten SW beim nächsten Load zwangs-ersetzen; Cookie
    // bleibt (separater Speicher). updateViaCache:'none' + update() ziehen die
    // neue sw.js sofort, controllerchange lädt beim SW-Wechsel EINMAL neu.
    var __hadController = !!navigator.serviceWorker.controller;
    var __reloaded = false;
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      if (!__hadController || __reloaded) return;
      __reloaded = true;
      window.location.reload();
    });
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('./sw.js', { updateViaCache: 'none' })
        .then(function (reg) { reg.update(); })
        .catch(function (err) {
          console.warn('SW-Registrierung fehlgeschlagen:', err);
        });
    });
  }
})();
