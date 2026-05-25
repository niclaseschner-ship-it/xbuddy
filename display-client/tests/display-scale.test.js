// Tests des Skalierungs-Adapters — Verhalten je DC-ID (DC-10).
// Lauf: node --test tests/  (von display-client/ aus)
//
// Der Adapter rechnet pure: aus viewport- und design-Pixel-Maßen folgt
// ein proportionaler Skalierungs-Faktor. computeScale braucht keinen DOM
// und keinen Browser — der Test prüft die Berechnung direkt. Die
// DOM-Anwendung (applyScale) wird mit einem minimalen DOM-Stub geprüft;
// echte Browser-Engine-Tests (visibility, fullscreen, resize) sind ohne
// headless-Browser-Engine nicht abbildbar und gehören in den manuellen
// Vertikale-Scheibe-Check (#107, #108).

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

const disp = require('../displib.js');

// ============================================================
//  DC-12 — Skalierungs-Berechnung (proportional, min)
// ============================================================

test('DC-12 — Pi-Display 1920×1080: scale 1.0 (identisch zur Design-Auflösung)', () => {
  assert.equal(disp.computeScale(1920, 1080, 1920, 1080), 1.0);
});

test('DC-12 — Tablet 1280×800: scale 0.667 (Breite limitiert, Letterbox oben/unten)', () => {
  // min(1280/1920, 800/1080) = min(0.6667, 0.7407) = 0.6667 — Breite limitiert
  const s = disp.computeScale(1280, 800, 1920, 1080);
  assert.ok(Math.abs(s - 0.6666666666666666) < 1e-9, 'scale=' + s);
});

test('DC-12 — Querformat-Monitor 2560×1440: scale 1.333 (Breite limitiert)', () => {
  // min(2560/1920, 1440/1080) = min(1.3333, 1.3333) = 1.3333 — beide gleich
  const s = disp.computeScale(2560, 1440, 1920, 1080);
  assert.ok(Math.abs(s - 1.3333333333333333) < 1e-9, 'scale=' + s);
});

test('DC-12 — Hochformat-Handy 800×1280: kleiner Faktor, viel Letterbox', () => {
  // min(800/1920, 1280/1080) = min(0.4167, 1.1852) = 0.4167 — Breite limitiert
  const s = disp.computeScale(800, 1280, 1920, 1080);
  assert.ok(Math.abs(s - (800 / 1920)) < 1e-9, 'scale=' + s);
  // Hochformat-Fall: skalierter Inhalt belegt nur ~33% der Höhe — viel
  // schwarzer Rand. Bewusst akzeptiert: Hochformat ist keine Display-
  // Aufstellung (Spec #107 Aspect-Ratio-Verhalten).
  assert.ok(s < 0.5);
});

test('DC-12 — Höhe limitiert (sehr breites Viewport): scale folgt der Höhe', () => {
  // 4000×600: min(4000/1920, 600/1080) = min(2.083, 0.5555) = 0.5555 — Höhe limitiert
  const s = disp.computeScale(4000, 600, 1920, 1080);
  assert.ok(Math.abs(s - (600 / 1080)) < 1e-9, 'scale=' + s);
});

// ============================================================
//  DC-15 — Default-Design-Auflösung 1920×1080
// ============================================================

test('DC-15 — Default-Design-Auflösung 1920×1080 (V1: hartcodiert)', () => {
  // Ohne explizite Design-Maße muss dasselbe Ergebnis wie mit 1920×1080
  // herauskommen — DC-15 hartcodiert, einziger V1-Konsument Plan-Buddy.
  assert.equal(disp.computeScale(1920, 1080), 1.0);
  assert.equal(
    disp.computeScale(1280, 800),
    disp.computeScale(1280, 800, 1920, 1080));
});

// ============================================================
//  Robustheit der Pure-Function (defensive Werte)
// ============================================================

test('computeScale — nicht-positive oder ungültige Maße liefern 0 (sicherer Fallback)', () => {
  assert.equal(disp.computeScale(0, 1080), 0);
  assert.equal(disp.computeScale(1920, 0), 0);
  assert.equal(disp.computeScale(-1, 1080), 0);
  assert.equal(disp.computeScale(NaN, 1080), 0);
  assert.equal(disp.computeScale(Infinity, 1080), 0);
});

// ============================================================
//  DC-12 — DOM-Anwendung: applyScale setzt transform proportional
// ============================================================
//
// Minimaler iframe-Stub: nur `style`, kein DOM. applyScale setzt
// `transform` und `transformOrigin` — mehr testet diese Schicht nicht;
// die Berechnung selbst wird oben mit computeScale geprüft.

function fakeIframe() {
  return { style: {} };
}

test('DC-12 — applyScale schreibt transform=scale(s) und transform-origin=center', () => {
  const el = fakeIframe();
  const s = disp.applyScale(el, 1280, 800);
  assert.equal(el.style.transformOrigin, 'center');
  assert.equal(el.style.transform, 'scale(' + (1280 / 1920) + ')');
  assert.ok(Math.abs(s - (1280 / 1920)) < 1e-9);
});

test('DC-12 — applyScale auf 1.0 bei nativ aufgelöstem Display (1920×1080)', () => {
  const el = fakeIframe();
  disp.applyScale(el, 1920, 1080);
  assert.equal(el.style.transform, 'scale(1)');
});

// Bug #115 (Display-Adapter zentriert) — Regression-Schutz:
// `transform-origin` MUSS `center` sein, nicht `top left`. Sonst zöge
// die Skalierung den sichtbaren Inhalt in die obere linke Ecke der
// Layout-Box, weil CSS-Transformen die Layout-Größe nicht ändern und
// die umgebende Flex-Zentrierung weiterhin am unskalierten Element
// angreift — siehe DC-12, Erklärungs-Absatz. Echte Browser-Engine-
// Pixel-Position ist ohne headless-Browser nicht abbildbar; der Test
// prüft den CSS-Mechanismus (transform-origin), aus dem die zentrierte
// Position folgt.
test('#115 — transform-origin=center bei jedem Viewport (Letterbox symmetrisch)', () => {
  const cases = [
    [1920, 1200],  // Tablet 1920×1200 — Reproduktions-Fall aus #115
    [1280, 800],   // 16:10-Tablet
    [2560, 1440],  // 16:9-Monitor
    [800, 1280],   // Hochformat
  ];
  for (const [w, h] of cases) {
    const el = fakeIframe();
    disp.applyScale(el, w, h);
    assert.equal(el.style.transformOrigin, 'center', 'viewport=' + w + 'x' + h);
  }
});

// ============================================================
//  DC-14 — Re-Skalierung ändert nur transform, nicht src
// ============================================================
//
// Hier indirekt geprüft: applyScale fasst nur `style` an. Eine Re-Aufruf-
// Kette darf keine andere Eigenschaft des iframe-Stubs verändern — sonst
// würde der gerouteten Inhalt seinen Zustand verlieren (DC-2). Der
// echte Browser-Resize-Listener ist in index.html verdrahtet.

test('DC-14 — wiederholter applyScale fasst nur transform an, keine src/Attribute', () => {
  const el = { style: {}, src: 'http://example.test/plan' };
  disp.applyScale(el, 1280, 800);
  disp.applyScale(el, 1920, 1080);
  disp.applyScale(el, 800, 1280);
  assert.equal(el.src, 'http://example.test/plan');   // unverändert (DC-2)
  assert.equal(el.style.transform, 'scale(' + (800 / 1920) + ')');
});

// ============================================================
//  DC-11 — Wakelock-Hook: no-op-fähig, doppelt-anfordern bei visibility
// ============================================================
//
// Browser-API navigator.wakeLock ist im Node-Test nicht verfügbar. Wir
// testen mit einem Stub-doc/Stub-nav, dass:
//  - request() ohne wakeLock-API kein Fehler wirft;
//  - der visibilitychange-Listener registriert wird;
//  - mit Stub-API request() beim Laden UND nach visibilitychange='visible'
//    aufgerufen wird (Spec DC-11: erneutes Anfordern, weil System bei
//    Verdecken freigibt).

function fakeDoc(initialVisibility) {
  const listeners = {};
  return {
    visibilityState: initialVisibility || 'visible',
    documentElement: {},
    addEventListener(type, fn) {
      (listeners[type] = listeners[type] || []).push(fn);
    },
    fire(type) { for (const fn of (listeners[type] || [])) fn({}); },
    listeners,
  };
}

test('DC-11 — attachWakeLock ohne navigator.wakeLock wirft nicht', () => {
  const doc = fakeDoc();
  assert.doesNotThrow(() => disp.attachWakeLock(doc, {}));
  assert.doesNotThrow(() => disp.attachWakeLock(doc, null));
});

test('DC-11 — attachWakeLock fordert beim Laden und nach visibilitychange→visible an', () => {
  const doc = fakeDoc('visible');
  let requests = 0;
  const nav = {
    wakeLock: { request: function () { requests++; return Promise.resolve({}); } }
  };
  disp.attachWakeLock(doc, nav);
  assert.equal(requests, 1, 'initial request beim Laden');
  doc.fire('visibilitychange');
  assert.equal(requests, 2, 'erneuter request nach visibilitychange→visible');
});

test('DC-11 — attachWakeLock fordert nicht an, wenn das Dokument nicht sichtbar ist', () => {
  const doc = fakeDoc('hidden');
  let requests = 0;
  const nav = {
    wakeLock: { request: function () { requests++; return Promise.resolve({}); } }
  };
  disp.attachWakeLock(doc, nav);
  // initial request läuft trotzdem (Browser-Lock-Anforderung; System
  // verweigert ggf., der Client lebt damit). visibilitychange→hidden
  // löst keinen erneuten request aus.
  const before = requests;
  doc.fire('visibilitychange');
  assert.equal(requests, before, 'kein erneuter request bei hidden');
});

// ============================================================
//  DC-11 — Fullscreen-Hook auf erstem Gesture
// ============================================================
//
// requestFullscreen() braucht ein User-Gesture. Spec: beim ersten
// touchend/click versuchen; Guard ist der echte Vollbild-Status —
// verlässt der Nutzer den Vollbild, holt ihn der nächste Tap zurück
// (self-healing). Fehlt die API, ist das kein Fehler.

test('DC-11 — attachFullscreenOnGesture registriert touchend + click', () => {
  const doc = fakeDoc();
  doc.documentElement = {};
  disp.attachFullscreenOnGesture(doc);
  assert.ok((doc.listeners['touchend'] || []).length === 1);
  assert.ok((doc.listeners['click']    || []).length === 1);
});

test('DC-11 — ohne requestFullscreen-API wirft der Tap-Handler nicht', () => {
  const doc = fakeDoc();
  doc.documentElement = {};                  // keine requestFullscreen-Methode
  disp.attachFullscreenOnGesture(doc);
  assert.doesNotThrow(() => doc.fire('click'));
  assert.doesNotThrow(() => doc.fire('touchend'));
});

test('DC-11 — bereits im Vollbild: kein erneuter requestFullscreen', () => {
  const doc = fakeDoc();
  let calls = 0;
  doc.documentElement = {
    requestFullscreen: function () { calls++; return Promise.resolve(); }
  };
  doc.fullscreenElement = doc.documentElement;   // schon im Vollbild
  disp.attachFullscreenOnGesture(doc);
  doc.fire('click');
  assert.equal(calls, 0);
});

test('DC-11 — nicht im Vollbild + Tap: requestFullscreen wird aufgerufen', () => {
  const doc = fakeDoc();
  let calls = 0;
  doc.documentElement = {
    requestFullscreen: function () { calls++; return Promise.resolve(); }
  };
  disp.attachFullscreenOnGesture(doc);
  doc.fire('touchend');
  assert.equal(calls, 1);
  // self-healing: nach Verlassen des Vollbilds holt der nächste Tap ihn
  // zurück. fullscreenElement bleibt null, also feuert der nächste click
  // erneut requestFullscreen.
  doc.fire('click');
  assert.equal(calls, 2);
});

test('DC-11 — requestFullscreen-Promise-Reject wirft nicht synchron', () => {
  const doc = fakeDoc();
  doc.documentElement = {
    requestFullscreen: function () { return Promise.reject(new Error('nope')); }
  };
  disp.attachFullscreenOnGesture(doc);
  assert.doesNotThrow(() => doc.fire('click'));
});
