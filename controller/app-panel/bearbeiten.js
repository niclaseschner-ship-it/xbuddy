// bearbeiten.js — Editor-Seite für Panel-Kacheln (PBE-1..11, T452).
// PBE-IDs verweisen auf specs/platform/panel-bearbeiten.md.
// UMD-Wrapper: läuft im Browser (globalThis.editorLib) und in Node (require) —
// dieselbe Logik trägt bearbeiten.html und reine Logik-Tests (PBE-12 / AC6).

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.editorLib = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // ============================================================
  //  PBE-5/PBE-6/PBE-7 — Pure Operationen auf der tiles-Liste
  // ============================================================
  //
  // Alle Editier-Operationen sind reine Funktionen: sie nehmen ein tiles-Array
  // und liefern ein neues Array zurück (kein in-place-mutate). So bleibt die
  // Render-Schicht einfach (Re-render aus dem aktuellen State) und die Logik
  // testbar (Node-Tests via run_node).
  //
  // PBE-4 Sammelmodus: alle Operationen passieren LOKAL; erst Speichern schickt
  // den vollen PUT (kein PUT-Sturm, kein Flackern).

  function deepCopyTile(t) {
    // Shallow-Copy reicht — query ist flach (PANEL-7), icons[] sind Strings.
    var copy = {
      key: t.key, app: t.app, view: t.view,
      label: t.label,
      icons: t.icons ? t.icons.slice() : [],
      sichtbar: t.sichtbar === true,
    };
    if (t.query && typeof t.query === 'object' && !Array.isArray(t.query)) {
      copy.query = {};
      for (var qk in t.query) {
        if (Object.prototype.hasOwnProperty.call(t.query, qk)) {
          copy.query[qk] = t.query[qk];
        }
      }
    }
    return copy;
  }

  function cloneTiles(tiles) {
    if (!Array.isArray(tiles)) return [];
    var out = [];
    for (var i = 0; i < tiles.length; i++) out.push(deepCopyTile(tiles[i]));
    return out;
  }

  function indexOfKey(tiles, key) {
    for (var i = 0; i < tiles.length; i++) {
      if (tiles[i] && tiles[i].key === key) return i;
    }
    return -1;
  }

  // PBE-5: Verschieben — Reihenfolge ändern, sonst nichts.
  function moveTile(tiles, key, direction) {
    var out = cloneTiles(tiles);
    var i = indexOfKey(out, key);
    if (i < 0) return out;
    var j = i + (direction === 'up' ? -1 : +1);
    if (j < 0 || j >= out.length) return out;
    var tmp = out[i]; out[i] = out[j]; out[j] = tmp;
    return out;
  }

  function moveTileTo(tiles, key, newIndex) {
    // Frei plazieren (für Drag/Drop). newIndex außerhalb → ans Ende.
    var out = cloneTiles(tiles);
    var i = indexOfKey(out, key);
    if (i < 0) return out;
    var item = out.splice(i, 1)[0];
    if (newIndex < 0) newIndex = 0;
    if (newIndex > out.length) newIndex = out.length;
    out.splice(newIndex, 0, item);
    return out;
  }

  // PBE-6: Ausblenden (sichtbar=false, reversibel).
  function toggleVisibility(tiles, key) {
    var out = cloneTiles(tiles);
    var i = indexOfKey(out, key);
    if (i < 0) return out;
    out[i].sichtbar = !(out[i].sichtbar === true);
    return out;
  }

  // PBE-6: Entfernen (hart aus tiles).
  function removeTile(tiles, key) {
    var out = cloneTiles(tiles);
    var i = indexOfKey(out, key);
    if (i < 0) return out;
    out.splice(i, 1);
    return out;
  }

  // ============================================================
  //  PBE-7 — Hinzufügen aus der Seiten-Registry (Sorte a + Varianten)
  // ============================================================
  //
  // Eine Display-View kann endliche bekannte Varianten haben (SREG-1 / BUD-4).
  // Jede Variante wird ein eigenständiger Listeneintrag — getrennt wählbar.

  function flattenRegistryEntry(entry) {
    // Aus einem SREG-Eintrag (Sorte a) eine Liste add-bereiter „Listeneinträge"
    // bauen: Default + alle Varianten. Jeder Eintrag hat den Schlüssel-Satz
    // {app, view, label, icons, query?, slug?}.
    if (!entry || typeof entry !== 'object') return [];
    if (entry.typ && entry.typ !== 'display') return [];
    var pfad = entry.pfad || '';
    var m = /^\/display\/([^/?#]+)\/([^/?#]+)/.exec(pfad);
    if (!m) return [];
    var app = m[1], view = m[2];
    var icons = Array.isArray(entry.icons) ? entry.icons.slice() : [];

    var out = [];
    // Default-Eintrag (kein query).
    out.push({
      app: app, view: view, label: entry.label || (app + '/' + view),
      icons: icons.slice(), slug: null,
    });
    // Varianten (SREG-1 / BUD-4): {slug, query, label, icons?}.
    if (Array.isArray(entry.varianten)) {
      for (var i = 0; i < entry.varianten.length; i++) {
        var v = entry.varianten[i] || {};
        var vIcons = Array.isArray(v.icons) && v.icons.length > 0
          ? v.icons.slice() : icons.slice();
        var add = {
          app: app, view: view,
          label: v.label || (entry.label || (app + '/' + view)),
          icons: vIcons,
          slug: v.slug || null,
        };
        if (v.query && typeof v.query === 'object' && !Array.isArray(v.query)) {
          add.query = {};
          for (var qk in v.query) {
            if (Object.prototype.hasOwnProperty.call(v.query, qk)) {
              add.query[qk] = v.query[qk];
            }
          }
        }
        out.push(add);
      }
    }
    return out;
  }

  function buildAddCandidates(inventarSeiten) {
    // Filter auf Sorte a (Display-Views) und alle Varianten flach ziehen.
    if (!Array.isArray(inventarSeiten)) return [];
    var out = [];
    for (var i = 0; i < inventarSeiten.length; i++) {
      var sub = flattenRegistryEntry(inventarSeiten[i]);
      for (var j = 0; j < sub.length; j++) out.push(sub[j]);
    }
    return out;
  }

  function makeKeyFromCandidate(cand, existingKeys) {
    // PBE-7: key wird beim Hinzufügen vergeben — stabil und eindeutig.
    // Konvention: `<app>-<view>[-<slug>][-<n>]`, n hochgezählt bei Kollision.
    var base = cand.app + '-' + cand.view;
    if (cand.slug) base += '-' + cand.slug;
    if (existingKeys.indexOf(base) < 0) return base;
    var n = 2;
    while (existingKeys.indexOf(base + '-' + n) >= 0) n++;
    return base + '-' + n;
  }

  function addCandidate(tiles, cand) {
    // PBE-7: Erzeugt eine PANEL-3-gültige Kachel am ENDE der Liste, sichtbar:true.
    var out = cloneTiles(tiles);
    var existingKeys = out.map(function (t) { return t.key; });
    var newKey = makeKeyFromCandidate(cand, existingKeys);
    var tile = {
      key: newKey,
      app: cand.app, view: cand.view,
      label: cand.label,
      icons: cand.icons.slice(),
      sichtbar: true,
    };
    if (cand.query && typeof cand.query === 'object' && !Array.isArray(cand.query)
        && Object.keys(cand.query).length > 0) {
      tile.query = {};
      for (var qk in cand.query) {
        if (Object.prototype.hasOwnProperty.call(cand.query, qk)) {
          tile.query[qk] = cand.query[qk];
        }
      }
    }
    out.push(tile);
    return out;
  }

  // ============================================================
  //  Dirty-Check (für Speichern/Verwerfen-Disabled-Logik)
  // ============================================================
  //
  // Strukturelle Gleichheit über die Felder, die der PUT trägt. Reihenfolge
  // zählt (PBE-5). JSON-Stringify ist hier ausreichend, weil tiles flach sind.

  function tilesAreEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
  }

  // ============================================================
  //  PBE-4 — Speichern: vollständige Liste per PUT
  // ============================================================
  //
  // Reine Funktion: nimmt fetch-Impl + URL + Liste, schickt den PUT, ruft
  // onSuccess(200) / onValidationError(422) / onError(sonst) zurück.
  // PBE-11 422-Pfad: Response-JSON enthält .error — Aufrufer zeigt sie an.

  function saveTiles(opts) {
    // opts: { fetchImpl, url, tiles, onSuccess, onValidationError, onError }
    var body = JSON.stringify({ tiles: opts.tiles });
    return opts.fetchImpl(opts.url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    }).then(function (r) {
      if (r && r.status === 200) {
        if (opts.onSuccess) opts.onSuccess();
        return;
      }
      if (r && r.status === 422) {
        // PBE-11: Begründung aus JSON ziehen, falls vorhanden.
        return r.json().then(function (j) {
          var msg = (j && j.error) || 'Validierungs-Fehler (422)';
          if (opts.onValidationError) opts.onValidationError(msg);
        }, function () {
          if (opts.onValidationError) opts.onValidationError('Validierungs-Fehler (422)');
        });
      }
      var statusMsg = 'HTTP ' + (r && r.status);
      if (opts.onError) opts.onError(statusMsg);
    }).catch(function (err) {
      if (opts.onError) opts.onError((err && err.message) || 'Netzwerk-Fehler');
    });
  }

  // ============================================================
  //  PBE-8 — Aus-Kachel wird im Editor NICHT angezeigt
  // ============================================================
  //
  // Die Aus-Kachel ist kein tiles.json-Eintrag (PANEL-6). Sie wird von der
  // Display-Seite zur Laufzeit eingefügt. Der Editor zeigt nur, was in
  // tiles.json steht — die Aus-Kachel taucht damit von selbst nicht auf.
  // Diese Funktion ist ein Eigentest-Helfer: schützt vor versehentlichem
  // Aufnehmen einer Aus-Pseudo-Kachel via key __aus__.

  function isAusKachelMarker(tile) {
    if (!tile || typeof tile !== 'object') return false;
    return tile.key === '__aus__';
  }

  function stripAusKachel(tiles) {
    if (!Array.isArray(tiles)) return [];
    return tiles.filter(function (t) { return !isAusKachelMarker(t); });
  }

  // ============================================================
  //  API
  // ============================================================

  return {
    cloneTiles: cloneTiles,
    deepCopyTile: deepCopyTile,
    indexOfKey: indexOfKey,
    moveTile: moveTile,
    moveTileTo: moveTileTo,
    toggleVisibility: toggleVisibility,
    removeTile: removeTile,
    flattenRegistryEntry: flattenRegistryEntry,
    buildAddCandidates: buildAddCandidates,
    makeKeyFromCandidate: makeKeyFromCandidate,
    addCandidate: addCandidate,
    tilesAreEqual: tilesAreEqual,
    saveTiles: saveTiles,
    isAusKachelMarker: isAusKachelMarker,
    stripAusKachel: stripAusKachel,
  };
});


// ============================================================
//  Bootstrap (nur im Browser)
// ============================================================
//
// Wird in Node ignoriert, weil document/window nicht existieren. Die Logik
// oben ist pur und testbar; hier nur DOM-Verdrahtung.

(function () {
  'use strict';
  if (typeof document === 'undefined') return;

  var editorLib = (typeof module === 'object' && module.exports)
    ? module.exports
    : (typeof globalThis !== 'undefined' ? globalThis.editorLib : null);
  if (!editorLib) return;

  // PBE-1: Panel-Identität vom <body>-data-Attribut.
  var panelId = (document.body && document.body.dataset)
    ? document.body.dataset.panelId
    : null;

  // Editor-State (lokal — PBE-4 Sammelmodus).
  var initialTiles = [];   // letzter persistenter Stand (für Verwerfen).
  var currentTiles = [];   // aktuelle Bearbeitungs-Liste.
  var addCandidates = [];  // Inventar für PBE-7-Picker.

  // ============================================================
  //  Status- und Fehler-Anzeigen
  // ============================================================

  function showError(msg) {
    var el = document.getElementById('error');
    if (!el) { console.error(msg); return; }
    el.textContent = msg;
    el.classList.remove('hidden');
  }

  function clearError() {
    var el = document.getElementById('error');
    if (el) { el.textContent = ''; el.classList.add('hidden'); }
  }

  function showStatus(msg) {
    var el = document.getElementById('status');
    if (!el) return;
    el.textContent = msg;
    el.classList.remove('hidden');
    setTimeout(function () { el.classList.add('hidden'); }, 3000);
  }

  // ============================================================
  //  Initial-Load der tiles für diese Panel-Instanz
  // ============================================================

  function tilesEndpoint() {
    return '/api/v1/panels/' + encodeURIComponent(panelId) + '/tiles.json';
  }

  function loadInitial() {
    return fetch(tilesEndpoint(), { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (data) {
      var raw = (data && data.tiles) || [];
      // PBE-8 Defense-in-Depth: __aus__-Marker, falls je in tiles.json gelandet,
      // wird vom Editor nicht angezeigt.
      initialTiles = editorLib.stripAusKachel(raw);
      currentTiles = editorLib.cloneTiles(initialTiles);
      renderAll();
    }).catch(function (err) {
      showError('Kacheln konnten nicht geladen werden: ' + (err.message || err));
      initialTiles = [];
      currentTiles = [];
      renderAll();
    });
  }

  // ============================================================
  //  PBE-7 — Add-Inventar aus /api/v1/seiten ziehen (Sorte a + Varianten)
  // ============================================================

  function loadAddInventar() {
    return fetch('/api/v1/seiten', { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (data) {
      // SREG-3: /api/v1/seiten liefert {eintraege: [...], snapshot_pending: [...]}.
      // Wir lesen genau den eintraege-Schlüssel — kein Fallback aufs ganze
      // Objekt (truthy-Objekt würde sonst durch buildAddCandidates als []
      // herausfallen und „Keine Display-Views" anzeigen, obwohl welche da sind).
      var list = (data && Array.isArray(data.eintraege)) ? data.eintraege : [];
      addCandidates = editorLib.buildAddCandidates(list);
    }).catch(function (err) {
      console.warn('Add-Inventar konnte nicht geladen werden:', err);
      addCandidates = [];
    });
  }

  // ============================================================
  //  Rendering
  // ============================================================

  function tileIconHtml(tile) {
    var slot = document.createElement('span');
    slot.className = 'tile-icons';
    var icons = Array.isArray(tile.icons) ? tile.icons : [];
    for (var i = 0; i < icons.length; i++) {
      var img = document.createElement('img');
      img.src = '/display/_shared/icons/' + icons[i];
      img.alt = '';
      img.className = 'tile-icon-img';
      img.onerror = function () {
        this.parentNode && this.parentNode.removeChild(this);
      };
      slot.appendChild(img);
    }
    return slot;
  }

  function renderTileRow(tile, index, total) {
    var li = document.createElement('li');
    li.className = 'tile-row' + (tile.sichtbar === false ? ' tile-row-hidden' : '');
    li.draggable = true;
    li.dataset.tileKey = tile.key;

    // Drag-Handle.
    var handle = document.createElement('span');
    handle.className = 'drag-handle';
    handle.setAttribute('aria-hidden', 'true');
    handle.textContent = '☰';
    li.appendChild(handle);

    li.appendChild(tileIconHtml(tile));

    var label = document.createElement('span');
    label.className = 'tile-label';
    label.textContent = tile.label || '';
    li.appendChild(label);

    var status = document.createElement('span');
    status.className = 'tile-state';
    status.textContent = tile.sichtbar === false ? 'ausgeblendet' : 'sichtbar';
    li.appendChild(status);

    // Aktionen.
    var actions = document.createElement('div');
    actions.className = 'tile-actions';

    var upBtn = document.createElement('button');
    upBtn.type = 'button';
    upBtn.className = 'btn btn-icon';
    upBtn.textContent = '↑';
    upBtn.setAttribute('aria-label', 'Nach oben');
    upBtn.disabled = index === 0;
    upBtn.addEventListener('click', function () {
      currentTiles = editorLib.moveTile(currentTiles, tile.key, 'up');
      renderAll();
    });
    actions.appendChild(upBtn);

    var downBtn = document.createElement('button');
    downBtn.type = 'button';
    downBtn.className = 'btn btn-icon';
    downBtn.textContent = '↓';
    downBtn.setAttribute('aria-label', 'Nach unten');
    downBtn.disabled = index === total - 1;
    downBtn.addEventListener('click', function () {
      currentTiles = editorLib.moveTile(currentTiles, tile.key, 'down');
      renderAll();
    });
    actions.appendChild(downBtn);

    var hideBtn = document.createElement('button');
    hideBtn.type = 'button';
    hideBtn.className = 'btn btn-secondary';
    hideBtn.textContent = tile.sichtbar === false ? 'Einblenden' : 'Ausblenden';
    hideBtn.addEventListener('click', function () {
      currentTiles = editorLib.toggleVisibility(currentTiles, tile.key);
      renderAll();
    });
    actions.appendChild(hideBtn);

    var rmBtn = document.createElement('button');
    rmBtn.type = 'button';
    rmBtn.className = 'btn btn-danger';
    rmBtn.textContent = 'Entfernen';
    rmBtn.addEventListener('click', function () {
      currentTiles = editorLib.removeTile(currentTiles, tile.key);
      renderAll();
    });
    actions.appendChild(rmBtn);

    li.appendChild(actions);

    // Drag & Drop — HTML5 mit minimalem Touch-Polyfill (Reorder, PBE-5).
    li.addEventListener('dragstart', function (ev) {
      ev.dataTransfer.effectAllowed = 'move';
      ev.dataTransfer.setData('text/plain', tile.key);
      li.classList.add('dragging');
    });
    li.addEventListener('dragend', function () {
      li.classList.remove('dragging');
    });
    li.addEventListener('dragover', function (ev) {
      ev.preventDefault();
      ev.dataTransfer.dropEffect = 'move';
    });
    li.addEventListener('drop', function (ev) {
      ev.preventDefault();
      var srcKey = ev.dataTransfer.getData('text/plain');
      if (!srcKey || srcKey === tile.key) return;
      currentTiles = editorLib.moveTileTo(
        currentTiles, srcKey, editorLib.indexOfKey(currentTiles, tile.key));
      renderAll();
    });

    return li;
  }

  function renderTileList() {
    var list = document.getElementById('tile-list');
    var emptyHint = document.getElementById('empty-hint');
    if (!list) return;
    list.innerHTML = '';
    var tiles = currentTiles;
    // PBE-9: leerer Zustand ist erlaubt — Hinweis-Text zeigen.
    if (tiles.length === 0) {
      if (emptyHint) emptyHint.classList.remove('hidden');
      return;
    }
    if (emptyHint) emptyHint.classList.add('hidden');
    for (var i = 0; i < tiles.length; i++) {
      list.appendChild(renderTileRow(tiles[i], i, tiles.length));
    }
  }

  function renderButtons() {
    var dirty = !editorLib.tilesAreEqual(initialTiles, currentTiles);
    var saveBtn = document.getElementById('btn-save');
    var discardBtn = document.getElementById('btn-discard');
    if (saveBtn) saveBtn.disabled = !dirty;
    if (discardBtn) discardBtn.disabled = !dirty;
  }

  function renderAll() {
    renderTileList();
    renderButtons();
  }

  // ============================================================
  //  PBE-7 Add-Dialog
  // ============================================================

  function renderAddDialog() {
    var dlg = document.getElementById('add-dialog');
    var list = document.getElementById('add-list');
    var empty = document.getElementById('add-empty');
    if (!dlg || !list) return;
    list.innerHTML = '';
    if (addCandidates.length === 0) {
      if (empty) empty.classList.remove('hidden');
    } else {
      if (empty) empty.classList.add('hidden');
      for (var i = 0; i < addCandidates.length; i++) {
        (function (cand) {
          var li = document.createElement('li');
          li.className = 'add-row-item';
          var icons = document.createElement('span');
          icons.className = 'tile-icons';
          for (var j = 0; j < (cand.icons || []).length; j++) {
            var img = document.createElement('img');
            img.src = '/display/_shared/icons/' + cand.icons[j];
            img.alt = '';
            img.className = 'tile-icon-img';
            img.onerror = function () {
              this.parentNode && this.parentNode.removeChild(this);
            };
            icons.appendChild(img);
          }
          li.appendChild(icons);
          var label = document.createElement('span');
          label.className = 'tile-label';
          label.textContent = cand.label;
          li.appendChild(label);
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'btn btn-primary';
          btn.textContent = 'Hinzufügen';
          btn.addEventListener('click', function () {
            currentTiles = editorLib.addCandidate(currentTiles, cand);
            closeAddDialog();
            renderAll();
          });
          li.appendChild(btn);
          list.appendChild(li);
        })(addCandidates[i]);
      }
    }
    dlg.classList.remove('hidden');
  }

  function closeAddDialog() {
    var dlg = document.getElementById('add-dialog');
    if (dlg) dlg.classList.add('hidden');
  }

  // ============================================================
  //  Speichern + Verwerfen
  // ============================================================

  function doSave() {
    clearError();
    var saveBtn = document.getElementById('btn-save');
    var discardBtn = document.getElementById('btn-discard');
    if (saveBtn) saveBtn.disabled = true;
    if (discardBtn) discardBtn.disabled = true;

    editorLib.saveTiles({
      fetchImpl: function (u, init) { return fetch(u, init); },
      url: '/api/v1/panels/' + encodeURIComponent(panelId) + '/tiles',
      tiles: currentTiles,
      onSuccess: function () {
        showStatus('Gespeichert.');
        initialTiles = editorLib.cloneTiles(currentTiles);
        renderButtons();
      },
      onValidationError: function (msg) {
        // PBE-11: Fehler-Message aus dem 422 anzeigen.
        showError('Speichern abgelehnt (422): ' + msg);
        renderButtons();
      },
      onError: function (msg) {
        showError('Speichern fehlgeschlagen: ' + msg);
        renderButtons();
      },
    });
  }

  function doDiscard() {
    currentTiles = editorLib.cloneTiles(initialTiles);
    clearError();
    renderAll();
  }

  // ============================================================
  //  Boot
  // ============================================================

  document.addEventListener('DOMContentLoaded', function () {
    var saveBtn = document.getElementById('btn-save');
    var discardBtn = document.getElementById('btn-discard');
    var addBtn = document.getElementById('btn-add');
    var addCancel = document.getElementById('btn-add-cancel');
    if (saveBtn) saveBtn.addEventListener('click', doSave);
    if (discardBtn) discardBtn.addEventListener('click', doDiscard);
    if (addBtn) addBtn.addEventListener('click', function () {
      loadAddInventar().then(renderAddDialog);
    });
    if (addCancel) addCancel.addEventListener('click', closeAddDialog);

    loadInitial();
  });
})();
