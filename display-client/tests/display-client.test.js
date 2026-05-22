// Tests des Display-Clients — Verhalten je DC-ID (DC-10).
// Lauf: node --test tests/  (von display-client/ aus)
//
// Der Router wird durch eine kontrollierte Doppelung ersetzt: FakeEventSource
// simuliert den SSE-Zustands-Stream — aktueller Zustand beim Verbinden,
// Zustandsänderungen, Abbruch + Wiederverbindung, unbekannte display_id. So
// ist das Client-Verhalten ohne laufenden Router reproduzierbar prüfbar.

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

const disp = require('../displib.js');

// ============================================================
//  Doppelung: SSE-Stream-Stub statt laufendem Router
// ============================================================

class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.readyState = FakeEventSource.CONNECTING;
    this.onmessage = null;
    this.onerror = null;
    this.onopen = null;
    FakeEventSource.instances.push(this);
  }
  // Testhelfer — simulieren, was Router-Stream bzw. Browser tun:
  emitState(stateObj) {              // Router sendet einen Display-Zustand
    this.readyState = FakeEventSource.OPEN;
    if (this.onmessage) this.onmessage({ data: JSON.stringify(stateObj) });
  }
  dropTransient() {                  // Netz weg — Browser verbindet wieder
    this.readyState = FakeEventSource.CONNECTING;
    if (this.onerror) this.onerror({});
  }
  dropPermanent() {                  // ROU-22 404 — Abbruch ohne Reconnect
    this.readyState = FakeEventSource.CLOSED;
    if (this.onerror) this.onerror({});
  }
}
FakeEventSource.CONNECTING = 0;
FakeEventSource.OPEN = 1;
FakeEventSource.CLOSED = 2;

function spyView() {
  const calls = [];
  return {
    calls,
    showContent(url) { calls.push(['content', url]); },
    showIdle()       { calls.push(['idle']); },
    showSetup(id)    { calls.push(['setup', id]); },
  };
}

function setup(pathname) {
  FakeEventSource.instances = [];
  const view = spyView();
  const client = disp.createClient({ pathname, view, EventSourceImpl: FakeEventSource });
  return { view, client, es: FakeEventSource.instances[0] };
}

// Display-States im ROU-10-Format.
const STATE_A = {
  source_id: 'phone:test-1', descriptor: { figure_id: 'rotes-a', bucket: 0 },
  payload: { url: 'http://example.test/klein' }, since: '2026-05-22T10:00:00Z',
};
const STATE_B = {
  source_id: 'phone:test-1', descriptor: { figure_id: 'rotes-a', bucket: 1 },
  payload: { url: 'http://example.test/gross' }, since: '2026-05-22T10:01:00Z',
};

// ============================================================
//  DC-1 — Stabile Identität aus der Einstiegs-URL
// ============================================================

test('DC-1 — display_id wird aus dem Pfad /display/<id> gelesen', () => {
  assert.equal(disp.parseDisplayId('/display/wohnzimmer'), 'wohnzimmer');
  assert.equal(disp.parseDisplayId('/display/default'), 'default');
});

test('DC-1 — id wird URL-dekodiert, Query und Hash ignoriert', () => {
  assert.equal(disp.parseDisplayId('/display/mein%20display'), 'mein display');
  assert.equal(disp.parseDisplayId('/display/default?reload=1'), 'default');
  assert.equal(disp.parseDisplayId('/display/default#x'), 'default');
});

test('DC-1 — dieselbe URL ergibt dieselbe Identität (stabil)', () => {
  assert.equal(disp.parseDisplayId('/display/flur'), disp.parseDisplayId('/display/flur'));
});

// ============================================================
//  DC-2 — Persistenter Client
// ============================================================

test('DC-2 — eine Stream-Verbindung trägt mehrere Inhaltswechsel', () => {
  const { es } = setup('/display/default');
  es.emitState(STATE_A);
  es.emitState(STATE_B);
  assert.equal(FakeEventSource.instances.length, 1);
});

test('DC-2 — unveränderter Zustand löst keinen erneuten Wechsel aus (kein Reload)', () => {
  const { view, es } = setup('/display/default');
  es.emitState(STATE_A);
  es.emitState(STATE_A);
  assert.deepEqual(view.calls, [['content', 'http://example.test/klein']]);
});

// ============================================================
//  DC-3 / DC-4 — Gerouteten Inhalt anzeigen und wechseln
// ============================================================

test('DC-3 — zeigt beim Verbinden den gerouteten Inhalt', () => {
  const { view, es } = setup('/display/default');
  es.emitState(STATE_A);
  assert.deepEqual(view.calls, [['content', 'http://example.test/klein']]);
});

test('DC-4 — Inhaltswechsel über ein Folge-Ereignis des Streams', () => {
  const { view, es } = setup('/display/default');
  es.emitState(STATE_A);
  es.emitState(STATE_B);
  assert.deepEqual(view.calls, [
    ['content', 'http://example.test/klein'],
    ['content', 'http://example.test/gross'],
  ]);
});

// ============================================================
//  DC-5 — Schwarzer Ruhe-Zustand ohne Inhalt
// ============================================================

test('DC-5 — null-Zustand führt zum Ruhe-Zustand', () => {
  const { view, es } = setup('/display/default');
  es.emitState(null);
  assert.deepEqual(view.calls, [['idle']]);
});

test('DC-5 — Wechsel von Inhalt zurück in den Ruhe-Zustand', () => {
  const { view, es } = setup('/display/default');
  es.emitState(STATE_A);
  es.emitState(null);
  assert.deepEqual(view.calls, [
    ['content', 'http://example.test/klein'],
    ['idle'],
  ]);
});

// ============================================================
//  DC-6 — Inhalt bleibt bei Störung stehen
// ============================================================

test('DC-6 — transiente Störung lässt den letzten Inhalt stehen', () => {
  const { view, es } = setup('/display/default');
  es.emitState(STATE_A);
  es.dropTransient();
  // Keine weitere View-Änderung: kein Ruhe-Zustand, kein Hinweis, keine
  // Fehlerseite — der letzte Inhalt bleibt unangetastet.
  assert.deepEqual(view.calls, [['content', 'http://example.test/klein']]);
});

// ============================================================
//  DC-7 — Wiederverbindung & Aufholen
// ============================================================

test('DC-7 — Wiederverbindung holt einen verpassten Inhaltswechsel auf', () => {
  const { view, es } = setup('/display/default');
  es.emitState(STATE_A);
  es.dropTransient();                 // Browser verbindet selbsttätig wieder
  es.emitState(STATE_B);              // Stream liefert den aktuellen Zustand erneut
  assert.deepEqual(view.calls, [
    ['content', 'http://example.test/klein'],
    ['content', 'http://example.test/gross'],
  ]);
});

// ============================================================
//  DC-8 — Unbekannte oder fehlende Identität
// ============================================================

test('DC-8 — unbekannte display_id (Stream-404) zeigt den Einrichtungs-Hinweis', () => {
  const { view, es } = setup('/display/unbekannt');
  es.dropPermanent();                 // ROU-22 404 → EventSource CLOSED
  assert.deepEqual(view.calls, [['setup', 'unbekannt']]);
});

test('DC-8 — fehlende display_id zeigt den Hinweis und öffnet keinen Stream', () => {
  const { view, client } = setup('/display/');
  assert.deepEqual(view.calls, [['setup', null]]);
  assert.equal(client.source, null);
  assert.equal(FakeEventSource.instances.length, 0);
});

test('DC-8 — eine transiente Störung löst keinen Einrichtungs-Hinweis aus', () => {
  const { view, es } = setup('/display/default');
  es.dropTransient();
  assert.deepEqual(view.calls, []);   // Browser reconnectet — kein Hinweis
});

// ============================================================
//  DC-9 — Keine Geräte-Konfiguration
// ============================================================

test('DC-9 — Stream-URL ist relativ: same-origin, keine Router-Adresse', () => {
  const u = disp.streamUrl('default');
  assert.equal(u, '/api/v1/displays/default/events');
  assert.ok(u.startsWith('/'));
  assert.ok(!/^[a-z]+:\/\//.test(u));
});
