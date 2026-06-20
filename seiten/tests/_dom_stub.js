/**
 * _dom_stub.js — Minimale DOM-Attrappe + fetch-Spy für node --test.
 *
 * Kein jsdom, kein npm, kein package.json — vanilla Node.
 * Vorbild: controller/app-panel/tests/test_app_panel.py _DOM_STUB.
 */

"use strict";

/**
 * Baut eine minimale document-Attrappe.
 * Unterstützt: createElement, getElementById, querySelectorAll,
 * appendChild, addEventListener, dataset, classList, innerHTML (get/set).
 *
 * innerHTML-Setter parst keine HTML-Tags, sammelt aber den gesetzten
 * String-Wert — Tests prüfen enthaltene Teilstrings darauf.
 */
function makeDom() {
  // Registry: id → Element
  const _elementsById = {};

  function makeEl(tag) {
    const el = {
      _tag:      tag,
      _children: [],
      _listeners: {},
      _innerHTML: "",
      type:      "",
      className: "",
      textContent: "",
      disabled:  false,
      hidden:    false,
      value:     "",
      src:       "",
      alt:       "",
      href:      "",
      id:        "",
      onerror:   null,
      style:     {},
      dataset:   {},
      classList: {
        _classes: new Set(),
        add:    function(...cs) { cs.forEach(c => this._classes.add(c)); },
        remove: function(...cs) { cs.forEach(c => this._classes.delete(c)); },
        contains: function(c)  { return this._classes.has(c); },
        toggle: function(c)    {
          if (this._classes.has(c)) { this._classes.delete(c); return false; }
          this._classes.add(c); return true;
        },
      },
    };

    Object.defineProperty(el, "innerHTML", {
      get: function() { return el._innerHTML; },
      set: function(html) {
        el._innerHTML = html;
        el._children = [];
      },
    });

    el.appendChild = function(c) {
      c.parentNode = el;
      el._children.push(c);
      return c;
    };

    el.insertBefore = function(newNode, refNode) {
      newNode.parentNode = el;
      const idx = refNode ? el._children.indexOf(refNode) : -1;
      if (idx >= 0) {
        el._children.splice(idx, 0, newNode);
      } else {
        el._children.push(newNode);
      }
      return newNode;
    };

    el.removeChild = function(c) {
      el._children = el._children.filter(x => x !== c);
    };

    el.addEventListener = function(ev, cb, opts) {
      if (!el._listeners[ev]) el._listeners[ev] = [];
      el._listeners[ev].push({ cb, opts });
    };

    el.removeEventListener = function(ev, cb) {
      if (!el._listeners[ev]) return;
      el._listeners[ev] = el._listeners[ev].filter(e => e.cb !== cb);
    };

    el.querySelectorAll = function(sel) {
      // Minimale Implementierung: gibt Kinder mit passendem data-Attribut oder Klasse zurück.
      // Für Test-Zwecke genügt das; echtes CSS-Selector-Parsing ist hier nicht nötig.
      return [];
    };

    el.querySelector = function(sel) {
      // Schaut in innerHTML-String nach id="<sel>" Pattern
      const idMatch = sel.match(/^#(.+)$/);
      if (idMatch) return _elementsById[idMatch[1]] || null;
      const clsMatch = sel.match(/^\.(.+)$/);
      if (clsMatch) {
        return el._children.find(c => c.classList && c.classList._classes.has(clsMatch[1])) || null;
      }
      return null;
    };

    el.closest = function(sel) {
      return null;
    };

    el.focus = function() {};
    el.blur  = function() {};
    el.click = function() {
      const cbs = (el._listeners["click"] || []);
      cbs.forEach(e => e.cb({ target: el, preventDefault: () => {} }));
    };

    el._fire = function(eventName, eventObj = {}) {
      const cbs = el._listeners[eventName] || [];
      cbs.forEach(e => e.cb({ target: el, ...eventObj, preventDefault: () => {} }));
    };

    return el;
  }

  // Öffentliche document-Attrappe
  const doc = {
    _elementsById,
    _body: makeEl("body"),

    createElement: function(tag) {
      return makeEl(tag);
    },

    getElementById: function(id) {
      return _elementsById[id] || null;
    },

    _registerEl: function(id, el) {
      _elementsById[id] = el;
      return el;
    },

    querySelectorAll: function(sel) {
      return [];
    },

    querySelector: function(sel) {
      const idMatch = sel.match(/^#(.+)$/);
      if (idMatch) return _elementsById[idMatch[1]] || null;
      return null;
    },

    addEventListener: function() {},

    get body() { return this._body; },
    visibilityState: "visible",
    fullscreenElement: null,
    documentElement: makeEl("html"),
  };

  return doc;
}

/**
 * Baut einen fetch-Spy.
 *
 * Rückgabe: async-Funktion, die als globales `fetch` eingesetzt werden kann.
 * spy.calls: Array von {url, method, body} — jeder Aufruf wird gesammelt.
 * spy.mockJson(data): legt JSON-Antwort für den nächsten Aufruf fest.
 * spy.mockStatus(status): legt HTTP-Status für den nächsten Aufruf fest.
 * spy.reset(): leert calls + Mocks.
 */
function makeFetchSpy(defaultJson = {}) {
  const calls = [];
  let _mockJson   = defaultJson;
  let _mockStatus = 200;

  const spy = async function(url, options = {}) {
    const body = options.body !== undefined ? options.body : undefined;
    calls.push({
      url,
      method: options.method || "GET",
      body,
    });

    const status = _mockStatus;
    const json   = _mockJson;

    return {
      ok:     status >= 200 && status < 300,
      status,
      json:   async () => (typeof json === "function" ? json() : JSON.parse(JSON.stringify(json))),
      text:   async () => JSON.stringify(json),
    };
  };

  spy.calls = calls;

  spy.mockJson = function(data) {
    _mockJson = data;
  };

  spy.mockStatus = function(status) {
    _mockStatus = status;
  };

  spy.reset = function() {
    calls.length = 0;
    _mockJson   = defaultJson;
    _mockStatus = 200;
  };

  return spy;
}

/**
 * Baut einen URL-routing fetch-Spy.
 *
 * routes: Array von { match: string|RegExp, status?: number, json: any }
 *   match — wird als RegExp gegen die URL geprüft (string → neuer RegExp)
 *   status — HTTP-Status (default 200)
 *   json   — Rückgabe-Payload für resp.json()
 *
 * Fällt keine Route, gibt status 200 + defaultJson zurück.
 * spy.calls: Array von {url, method, body}.
 */
function makeRoutedFetchSpy(routes = [], defaultJson = {}) {
  const calls = [];

  const spy = async function(url, options = {}) {
    const body = options.body !== undefined ? options.body : undefined;
    calls.push({ url, method: options.method || "GET", body });

    for (const route of routes) {
      const re = route.match instanceof RegExp
        ? route.match
        : new RegExp(String(route.match));
      if (re.test(url)) {
        const status = route.status !== undefined ? route.status : 200;
        const json   = route.json;
        return {
          ok:     status >= 200 && status < 300,
          status,
          json:   async () => (typeof json === "function" ? json() : JSON.parse(JSON.stringify(json))),
          text:   async () => JSON.stringify(json),
        };
      }
    }

    const status = 200;
    return {
      ok:   true,
      status,
      json: async () => JSON.parse(JSON.stringify(defaultJson)),
      text: async () => JSON.stringify(defaultJson),
    };
  };

  spy.calls = calls;
  return spy;
}

module.exports = { makeDom, makeFetchSpy, makeRoutedFetchSpy };
