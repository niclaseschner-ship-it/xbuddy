// displib.js — Logik des Display-Clients, frei von DOM und Netzwerk.
// DC-IDs verweisen auf specs/platform/display-client.md.
// UMD-Wrapper: läuft im Browser (globalThis.dispLib) und in Node (require) —
// dieselbe Logik trägt index.html und die Tests (DC-10).

(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.dispLib = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // DC-1 — display_id aus der Einstiegs-URL /display/<id> ziehen.
  // Liefert die id oder null, wenn der Pfad keine hergibt (dann DC-8).
  function parseDisplayId(pathname) {
    var m = /^\/display\/([^/?#]+)/.exec(pathname || '');
    if (!m) return null;
    var raw = m[1];
    try { raw = decodeURIComponent(raw); } catch (e) { /* roh lassen */ }
    return raw || null;
  }

  // E-DC-3 — Stream-URL relativ angeben: gleiche Herkunft wie der Router,
  // der den Client ausliefert. Damit braucht der Client keine Router-Adresse
  // als Konfigurationswert (DC-9).
  function streamUrl(displayId) {
    return '/api/v1/displays/' + encodeURIComponent(displayId) + '/events';
  }

  // Inhalt aus einem Display-State (ROU-10) ziehen: payload.url oder null.
  function contentUrl(stateObj) {
    if (stateObj && stateObj.payload && typeof stateObj.payload.url === 'string') {
      return stateObj.payload.url;
    }
    return null;
  }

  // createClient — verbindet den SSE-Stream des Routers mit einer View.
  //   opts.pathname        Einstiegs-URL-Pfad (DC-1)
  //   opts.view            { showContent(url), showIdle(), showSetup(id) }
  //   opts.EventSourceImpl Konstruktor wie window.EventSource; in den Tests
  //                        durch eine Stream-Doppelung ersetzt (DC-10).
  function createClient(opts) {
    var view = opts.view;
    var EventSourceImpl = opts.EventSourceImpl;
    var displayId = parseDisplayId(opts.pathname);

    // DC-8 — keine display_id: Gerät nicht eingerichtet. Kein Stream, nur
    // der Einrichtungs-Hinweis.
    if (!displayId) {
      view.showSetup(null);
      return { displayId: null, source: null };
    }

    // Zuletzt gezeigte Inhalts-URL — ein unveränderter Zustand löst damit
    // keinen erneuten Wechsel aus (kein Reload, DC-2).
    var lastUrl = null;

    var source = new EventSourceImpl(streamUrl(displayId));

    // DC-3 / DC-4 — der Zustand beim Verbinden und jede folgende Änderung
    // kommen als SSE-Nachricht. Der Inhalt wird innerhalb des laufenden
    // Clients gewechselt (DC-2) — der Client lädt sich dafür nicht neu.
    source.onmessage = function (ev) {
      var stateObj;
      try { stateObj = JSON.parse(ev.data); } catch (e) { return; }
      var url = contentUrl(stateObj);
      if (url) {
        if (url !== lastUrl) {
          lastUrl = url;
          view.showContent(url);
        }
      } else {
        // DC-5 — kein Inhalt zugeordnet (State null): schwarzer Ruhe-Zustand.
        lastUrl = null;
        view.showIdle();
      }
    };

    // onerror — zwei Fälle, am readyState unterschieden:
    source.onerror = function () {
      if (source.readyState === EventSourceImpl.CLOSED) {
        // Stream endgültig zu. ROU-22 antwortet bei unbekannter display_id
        // mit 404; EventSource bricht dann ohne Wiederverbindung ab. DC-8:
        // Einrichtungs-Hinweis, der die display_id benennt.
        view.showSetup(displayId);
      }
      // readyState CONNECTING: transiente Störung. Der Browser verbindet
      // selbsttätig wieder (DC-7, SSE-Standard). DC-6: der zuletzt gezeigte
      // Inhalt bleibt stehen — also nichts tun.
    };

    return { displayId: displayId, source: source };
  }

  return {
    parseDisplayId: parseDisplayId,
    streamUrl: streamUrl,
    contentUrl: contentUrl,
    createClient: createClient,
  };
});
