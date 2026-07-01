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
      return;
    }

    // Zuletzt an die View übergebener Zustand: Inhalts-URL oder null
    // (Ruhe-Zustand); undefined, solange noch nichts kam. Ein unveränderter
    // Zustand löst keinen erneuten Wechsel aus — kein Reload (DC-2).
    var current;

    var source = new EventSourceImpl(streamUrl(displayId));

    // DC-3 / DC-4 / DC-5 — der Zustand beim Verbinden und jede folgende
    // Änderung kommen als SSE-Nachricht. Der Inhalt wird innerhalb des
    // laufenden Clients gewechselt (DC-2) — der Client lädt sich nicht neu.
    source.onmessage = function (ev) {
      var stateObj;
      try { stateObj = JSON.parse(ev.data); } catch (e) { return; }
      // Heartbeat-Events (ROU-22 2026-06-18) sind reine Lebenszeichen für
      // EventSource — KEINE Zustands-Änderung. Ohne diesen Skip würde der
      // Display-Client bei jedem 15-s-Heartbeat auf DC-5 (schwarz) flippen,
      // weil heartbeat-Events kein payload.url tragen.
      if (stateObj && stateObj.type === 'heartbeat') return;
      var next = contentUrl(stateObj);   // Inhalts-URL oder null (Ruhe-Zustand)
      if (next === current) return;      // unveränderter Zustand: kein Reload
      current = next;
      if (next) view.showContent(next);
      else view.showIdle();              // DC-5 — schwarzer Ruhe-Zustand
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
  }

  // ============================================================
  //  DC-12 — Skalierungs-Adapter (pure Berechnung)
  // ============================================================
  //
  // Pure Funktion: gibt den proportionalen Skalierungs-Faktor zurück, mit
  // dem ein iframe der Größe designW×designH per CSS-transform in ein
  // viewportW×viewportH-Viewport eingepasst wird. Der Inhalt wird so groß
  // wie möglich, ohne Verzerrung und ohne Überlauf — verbleibender Raum
  // ist Letterbox/Pillarbox und trägt im View-Zustand die Standard-
  // Hintergrundfarbe (#F5F1E8, --bg), entkoppelt von DC-5 (#000000,
  // Ruhe-Zustand; dann ist der Adapter-Container versteckt).
  //
  //     s = min(viewport.w / design.w, viewport.h / design.h)
  //
  // Defaults design = 1920×1080 (DC-15 — heutiger Plan-Buddy-Standard,
  // V1 einziger Konsument). Konsumenten-spezifische Design-Auflösung ist
  // V2 / OPEN-DC-C.
  function computeScale(viewportW, viewportH, designW, designH) {
    var dW = designW || 1920;
    var dH = designH || 1080;
    if (!isFinite(viewportW) || !isFinite(viewportH)) return 0;
    if (viewportW <= 0 || viewportH <= 0) return 0;
    if (dW <= 0 || dH <= 0) return 0;
    return Math.min(viewportW / dW, viewportH / dH);
  }

  // applyScale — wendet den Skalierungs-Faktor (computeScale) auf ein
  // iframe an. Reine DOM-Anwendung, damit die Pure-Function-Logik
  // (computeScale) ohne DOM testbar bleibt (DC-10). `transform-origin`
  // wird auf `center` gesetzt: die Skalierung passiert um den Mittelpunkt
  // des iframe-Layouts, sodass die Letterbox/Pillarbox symmetrisch um den
  // Inhalt verteilt ist (DC-12). Die Zentrierung im Viewport übernimmt
  // der umgebende Container per Flexbox (siehe index.html). Re-Aufruf
  // wechselt nur die `transform`-Eigenschaft, nicht die iframe.src — der
  // gerouteten Inhalt behält seinen Zustand (DC-14 / DC-2).
  function applyScale(iframeEl, viewportW, viewportH, designW, designH) {
    var s = computeScale(viewportW, viewportH, designW, designH);
    iframeEl.style.transformOrigin = 'center';
    iframeEl.style.transform = 'scale(' + s + ')';
    return s;
  }

  // ============================================================
  //  DC-11 — Wakelock-Helper
  // ============================================================
  //
  // Pattern aus FIG-26 (controller/figuren-erkennung): fordere den Lock
  // beim Laden an UND nach jedem Sichtbarkeits-Wechsel auf `visible`
  // (das System gibt den Lock beim Verdecken frei). Fehlt die API, ist
  // das kein Fehler — der Client läuft weiter (self-healing).
  function attachWakeLock(doc, nav) {
    var lock = null;
    function request() {
      if (!nav || !('wakeLock' in nav)) return;
      try {
        var p = nav.wakeLock.request('screen');
        if (p && p.then) p.then(function (l) { lock = l; }, function () {});
      } catch (e) { /* still */ }
    }
    doc.addEventListener('visibilitychange', function () {
      if (doc.visibilityState === 'visible') request();
    });
    request();
  }

  // ============================================================
  //  DC-11 — Fullscreen-Hook auf erstem User-Gesture
  // ============================================================
  //
  // requestFullscreen() braucht ein abgeschlossenes User-Gesture
  // (touchend/click), nicht touchstart. Guard ist der echte
  // Vollbild-Status — verlässt der Nutzer den Vollbild, holt ihn der
  // nächste Tap zurück (self-healing). Fehlt die API oder schlägt der
  // Aufruf fehl, ist das kein Fehler — der Client läuft weiter.
  function attachFullscreenOnGesture(doc) {
    function tryFullscreen() {
      if (doc.fullscreenElement || doc.webkitFullscreenElement) return;
      var el = doc.documentElement;
      var req = el.requestFullscreen || el.webkitRequestFullscreen;
      if (!req) return;
      try {
        var p = req.call(el);
        if (p && p.catch) p.catch(function () {});
      } catch (e) { /* still */ }
    }
    doc.addEventListener('touchend', tryFullscreen, { passive: true });
    doc.addEventListener('click', tryFullscreen);
  }

  // contentUrl bleibt intern — nur createClient nutzt es.
  return {
    parseDisplayId: parseDisplayId,
    streamUrl: streamUrl,
    createClient: createClient,
    computeScale: computeScale,
    applyScale: applyScale,
    attachWakeLock: attachWakeLock,
    attachFullscreenOnGesture: attachFullscreenOnGesture,
  };
});
