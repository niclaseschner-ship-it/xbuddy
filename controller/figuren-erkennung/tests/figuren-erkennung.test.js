// Tests für die Figuren-Erkennung — Verhalten je FIG-ID.
// Lauf: node --test tests/ (von controller/figuren-erkennung/ aus)

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const fig = require('../figlib.js');

// ===========================================================
//  Hilfsfunktionen für die Tests
// ===========================================================

function rotateAround(c, deg, pt) {
  const r = deg * Math.PI / 180;
  const dx = pt.x - c.x, dy = pt.y - c.y;
  return {
    id: pt.id,
    x: c.x + dx * Math.cos(r) - dy * Math.sin(r),
    y: c.y + dx * Math.sin(r) + dy * Math.cos(r),
  };
}

function makeTriangleA() {
  return [
    { id: 1, x: 0,   y: 0 },
    { id: 2, x: 100, y: 0 },
    { id: 3, x: 0,   y: 50 },
  ];
}

function descriptorOf(pts) {
  return fig.descriptor(pts[0], pts[1], pts[2]);
}

function trianglesWithDescriptor(desc) {
  // Konstruiert Punkte mit den gewünschten Seitenlängen-Verhältnissen.
  // longest = 100, others = desc[0]*100, desc[1]*100.
  const longest = 100;
  const a = desc[0] * longest;
  const b = desc[1] * longest;
  // p0 = origin, p1 auf x-Achse bei longest, p2 berechnet
  const x2 = (longest * longest + a * a - b * b) / (2 * longest);
  const y2 = Math.sqrt(Math.max(0, a * a - x2 * x2));
  return [
    { id: 1, x: 0,        y: 0  },
    { id: 2, x: longest,  y: 0  },
    { id: 3, x: x2,       y: y2 },
  ];
}

// ===========================================================
//  Geometrie (Bausteine — abhängig für FIG-3/5/6/7)
// ===========================================================

test('FIG-3 — Descriptor ist rotations-invariant', () => {
  const tri = makeTriangleA();
  const d1 = descriptorOf(tri);
  const c = fig.centroid(tri);
  const rotated = tri.map(p => rotateAround(c, 47.3, p));
  const d2 = descriptorOf(rotated);
  for (let i = 0; i < 3; i++) {
    assert.ok(Math.abs(d1[i] - d2[i]) < 1e-9,
      `Descriptor-Komponente ${i} unterscheidet sich: ${d1[i]} vs ${d2[i]}`);
  }
});

test('FIG-3 — Descriptor ist translations-invariant', () => {
  const tri = makeTriangleA();
  const d1 = descriptorOf(tri);
  const moved = tri.map(p => ({ id: p.id, x: p.x + 500, y: p.y - 300 }));
  const d2 = descriptorOf(moved);
  for (let i = 0; i < 3; i++) {
    assert.ok(Math.abs(d1[i] - d2[i]) < 1e-9);
  }
});

test('FIG-3 — Descriptor-Letztwert ist immer 1.0', () => {
  const tri = makeTriangleA();
  const d = descriptorOf(tri);
  assert.strictEqual(d[2], 1.0);
});

// ===========================================================
//  FIG-4 / FIG-5 — Registry + Identifikation
// ===========================================================

test('FIG-4 — Default-Registry enthält ≥ 1 Test-Eintrag', () => {
  const cfg = fig.configDefaults();
  const keys = Object.keys(cfg.registry);
  assert.ok(keys.length >= 1, 'Registry muss mindestens eine Figur enthalten');
});

test('FIG-5 — Identifikation findet passenden Eintrag unter Toleranz', () => {
  const registry = { A: [0.50, 0.70, 1.0], B: [0.85, 0.92, 1.0] };
  assert.strictEqual(fig.identify([0.50, 0.70, 1.0], registry, 0.05), 'A');
  assert.strictEqual(fig.identify([0.85, 0.92, 1.0], registry, 0.05), 'B');
});

test('FIG-5 — L1-Mittel-Distanz wird verwendet (mittelt 3 Komponenten)', () => {
  const d = fig.patternDist([0.5, 0.7, 1.0], [0.5, 0.7, 1.0]);
  assert.strictEqual(d, 0);
  const d2 = fig.patternDist([0.5, 0.7, 1.0], [0.5, 0.7, 0.7]);
  assert.ok(Math.abs(d2 - 0.1) < 1e-9, `erwartet ≈0.1, bekommen ${d2}`);
});

test('FIG-5 — Match außerhalb der Toleranz liefert null', () => {
  const registry = { A: [0.50, 0.70, 1.0] };
  assert.strictEqual(fig.identify([0.20, 0.40, 1.0], registry, 0.05), null);
});

// ===========================================================
//  FIG-6 — Kumulativer Winkel
// ===========================================================

test('FIG-6 — Cum startet bei figure_detected mit angle: 0', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  const events = fig.feedTouches(session, tri, 0);
  const det = events.find(e => e.type === 'figure_detected');
  assert.ok(det, 'figure_detected nicht emittiert');
  assert.strictEqual(det.angle, 0);
  assert.strictEqual(det.figure_id, 'A');
});

test('FIG-6 — Cum akkumuliert während ununterbrochenem 3-Punkt-Kontakt', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    angle_update_min_delta_deg: 0.01,
    angle_update_max_hz: 1000,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  const c = fig.centroid(tri);
  fig.feedTouches(session, tri.map(p => rotateAround(c, 15, p)), 10);
  fig.feedTouches(session, tri.map(p => rotateAround(c, 30, p)), 20);
  assert.ok(Math.abs(session.cumulativeAngle - 30) < 0.5,
    `cum erwartet ≈30°, bekommen ${session.cumulativeAngle}`);
});

test('FIG-6 — Touch-Verlust + Wieder-Auflegen WEIT entfernt → match scheitert, cum bleibt 0', () => {
  // Trade-off-Begründung (siehe Spec, E-FIG-3 + Real-Test 2026-05-20):
  // Bei kapazitivem Flackern bleibt lastFramePoints stehen, damit die
  // räumliche Zuordnung beim nächsten 3-Punkt-Frame Continuity oder
  // Re-Placement unterscheiden kann. Re-Placement ist hier definiert
  // als „Punkte weit jenseits match_distance_px" — dann scheitert das
  // Matching und der Akku wird re-ankert ohne Beitrag.
  const session = fig.createSession({
    figure_present_ms: 0,
    angle_update_min_delta_deg: 0.01,
    angle_update_max_hz: 1000,
    match_distance_px: 60,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  // Touch-Verlust
  fig.feedTouches(session, [], 10);
  assert.strictEqual(session.cumulativeAngle, 0);
  // Weit entferntes Wieder-Auflegen — match_distance überschritten
  const farAway = tri.map(p => ({ id: p.id + 100, x: p.x + 500, y: p.y + 500 }));
  fig.feedTouches(session, farAway, 20);
  assert.strictEqual(session.lastMatchOk, 'fail');
  assert.strictEqual(session.cumulativeAngle, 0);
});

test('FIG-6 — Cum kann über 360° hinausgehen', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    angle_update_min_delta_deg: 0.01,
    angle_update_max_hz: 1000,
    match_distance_px: 1000,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  const c = fig.centroid(tri);
  for (let i = 1; i <= 50; i++) {
    const angle = i * 10;
    fig.feedTouches(session, tri.map(p => rotateAround(c, angle, p)), i * 10);
  }
  // 50 * 10° = 500° gesamt
  assert.ok(session.cumulativeAngle > 360,
    `cum erwartet > 360°, bekommen ${session.cumulativeAngle}`);
});

// ===========================================================
//  FIG-7 — Räumliche Punkt-Verfolgung
// ===========================================================

test('FIG-7 — matchPoints ordnet nächste Nachbarn zu', () => {
  const prev = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 50, y: 50 }];
  const curr = [{ x: 5, y: 3 }, { x: 105, y: 2 }, { x: 55, y: 48 }];
  const m = fig.matchPoints(prev, curr, 60);
  assert.ok(m);
  assert.strictEqual(m.length, 3);
});

test('FIG-7 — matchPoints scheitert bei zu großer Verschiebung', () => {
  const prev = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 50, y: 50 }];
  const curr = [{ x: 500, y: 500 }, { x: 600, y: 500 }, { x: 550, y: 550 }];
  assert.strictEqual(fig.matchPoints(prev, curr, 60), null);
});

test('FIG-7 — Reine Translation erzeugt ≈0° Rotation-Delta', () => {
  const prev = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 50, y: 50 }];
  const curr = prev.map(p => ({ x: p.x + 10, y: p.y + 5 }));
  const m = fig.matchPoints(prev, curr, 60);
  assert.ok(Math.abs(fig.frameRotationDelta(m)) < 0.01);
});

test('FIG-7 — Rotation um Schwerpunkt liefert korrekten Delta', () => {
  const tri = makeTriangleA();
  const c = fig.centroid(tri);
  const rotated = tri.map(p => rotateAround(c, 30, p));
  const m = fig.matchPoints(tri, rotated, 60);
  const delta = fig.frameRotationDelta(m);
  assert.ok(Math.abs(delta - 30) < 0.5,
    `Delta erwartet ≈30°, bekommen ${delta}`);
});

// ===========================================================
//  FIG-1 + FIG-2 — Hysterese und 3-Punkt-Bedingung
// ===========================================================

test('FIG-1 — Weniger als 3 Punkte führt nie zu figurePresent', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  fig.feedTouches(session, [{ id: 1, x: 0, y: 0 }, { id: 2, x: 100, y: 0 }], 0);
  fig.feedTouches(session, [{ id: 1, x: 0, y: 0 }, { id: 2, x: 100, y: 0 }], 500);
  assert.strictEqual(session.figurePresent, false);
});

test('FIG-2 — Figur erst nach 150 ms stabiler 3-Punkt-Auflage präsent', () => {
  const session = fig.createSession({
    figure_present_ms: 150,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  assert.strictEqual(session.figurePresent, false);
  fig.feedTouches(session, tri, 100);
  assert.strictEqual(session.figurePresent, false);
  fig.feedTouches(session, tri, 160);
  assert.strictEqual(session.figurePresent, true);
});

test('FIG-2 — Kein Auto-Exit bei Touch-Verlust', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  assert.strictEqual(session.figurePresent, true);
  // Touches komplett weg für lange Zeit — Session läuft weiter
  fig.feedTouches(session, [], 10_000);
  assert.strictEqual(session.figurePresent, true);
  assert.strictEqual(session.identifiedFigureId, 'A');
});

// ===========================================================
//  FIG-8 — Session-Ende-Button im Schwerpunkt
// ===========================================================

test('FIG-8 — Button liegt mittig auf dem Centroid mit Radius ≥ max(d(centroid, vertex)) + Padding', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    button_padding_px: 30,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  assert.ok(session.buttonCircle);
  const c = fig.centroid(tri);
  assert.ok(Math.abs(session.buttonCircle.x - c.x) < 1e-9);
  assert.ok(Math.abs(session.buttonCircle.y - c.y) < 1e-9);
  const maxR = Math.max(...tri.map(p => fig.dist(p, c)));
  assert.ok(session.buttonCircle.r >= maxR + 30 - 1e-9);
});

test('FIG-8 — Button-Position bleibt bei Touch-Verlust eingefroren', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  const beforeBtn = { ...session.buttonCircle };
  fig.feedTouches(session, [], 10);
  assert.deepStrictEqual(session.buttonCircle, beforeBtn);
});

test('FIG-8 — Single-Touch innerhalb Button ≥ tap_dwell_ms beendet Session', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    tap_dwell_ms: 100,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  fig.feedTouches(session, [], 5);   // Figur abgehoben
  const c = session.buttonCircle;
  // Single-Touch im Button
  fig.feedTouches(session, [{ id: 99, x: c.x, y: c.y }], 10);
  assert.strictEqual(session.figurePresent, true, 'dwell läuft noch');
  const evs = fig.feedTouches(session, [{ id: 99, x: c.x, y: c.y }], 120);
  const ended = evs.find(e => e.type === 'session_ended');
  assert.ok(ended, 'session_ended nicht emittiert');
  assert.strictEqual(ended.reason, 'user_button');
  assert.strictEqual(session.figurePresent, false);
});

test('FIG-8 — Single-Touch außerhalb Button beendet Session NICHT', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    tap_dwell_ms: 100,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  fig.feedTouches(session, [], 5);
  // Single-Touch weit außerhalb
  fig.feedTouches(session, [{ id: 99, x: 9999, y: 9999 }], 10);
  fig.feedTouches(session, [{ id: 99, x: 9999, y: 9999 }], 200);
  assert.strictEqual(session.figurePresent, true);
});

// ===========================================================
//  FIG-9 / FIG-10 — Transport + Event-Schema
// ===========================================================

test('FIG-10 — Alle Events tragen source_id, ts und type', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    tap_dwell_ms: 50,
    source_id: 'phone:test-x',
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  const evs = fig.feedTouches(session, tri, 0);
  assert.ok(evs.length >= 1);
  for (const ev of evs) {
    assert.strictEqual(ev.source_id, 'phone:test-x');
    assert.ok(typeof ev.ts === 'string' && ev.ts.length > 0);
    assert.ok(['figure_detected', 'angle_update', 'session_ended'].includes(ev.type));
  }
});

test('FIG-10 — figure_detected trägt figure_id und angle:0', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  const evs = fig.feedTouches(session, tri, 0);
  const det = evs.find(e => e.type === 'figure_detected');
  assert.ok(det);
  assert.strictEqual(det.figure_id, 'A');
  assert.strictEqual(det.angle, 0);
});

test('FIG-10 — session_ended trägt figure_id und reason: user_button', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    tap_dwell_ms: 50,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  fig.feedTouches(session, [], 5);
  const c = session.buttonCircle;
  fig.feedTouches(session, [{ id: 99, x: c.x, y: c.y }], 10);
  const evs = fig.feedTouches(session, [{ id: 99, x: c.x, y: c.y }], 100);
  const ended = evs.find(e => e.type === 'session_ended');
  assert.ok(ended);
  assert.strictEqual(ended.figure_id, 'A');
  assert.strictEqual(ended.reason, 'user_button');
});

// ===========================================================
//  FIG-11 — Sende-Logik (Throttle + Dead-Zone + Swap)
// ===========================================================

test('FIG-11 — angle_update gedrosselt auf 10 Hz (Min-Intervall 100 ms)', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    angle_update_max_hz: 10,
    angle_update_min_delta_deg: 0.01,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  const c = fig.centroid(tri);
  let updates = 0;
  // 20 Frames in 200 ms (100 Hz Input). Erwartung: ≤3 angle_updates (Throttle).
  for (let i = 1; i <= 20; i++) {
    const evs = fig.feedTouches(session, tri.map(p => rotateAround(c, i * 2, p)), i * 10);
    updates += evs.filter(e => e.type === 'angle_update').length;
  }
  assert.ok(updates <= 3, `Erwartet ≤3 Updates, bekommen ${updates}`);
});

test('FIG-11 — angle_update unter Dead-Zone (< 3°) wird unterdrückt', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    angle_update_max_hz: 1000,
    angle_update_min_delta_deg: 3,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  const c = fig.centroid(tri);
  // 1° → nicht senden
  const e1 = fig.feedTouches(session, tri.map(p => rotateAround(c, 1, p)), 10);
  assert.strictEqual(e1.filter(e => e.type === 'angle_update').length, 0);
  // jetzt 5° → senden
  const e2 = fig.feedTouches(session, tri.map(p => rotateAround(c, 5, p)), 20);
  assert.strictEqual(e2.filter(e => e.type === 'angle_update').length, 1);
});

test('FIG-11 — Wechsel auf andere identifizierte Figur sendet figure_detected', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    pattern_tolerance: 0.02,
    registry: { A: [0.50, 0.70, 1.0], B: [0.85, 0.92, 1.0] },
  });
  const triA = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, triA, 0);
  assert.strictEqual(session.identifiedFigureId, 'A');
  const triB = trianglesWithDescriptor([0.85, 0.92, 1.0]);
  const evs = fig.feedTouches(session, triB, 5);
  const detB = evs.find(e => e.type === 'figure_detected' && e.figure_id === 'B');
  assert.ok(detB, 'figure_detected für B nicht emittiert');
  assert.strictEqual(session.identifiedFigureId, 'B');
});

test('FIG-11 — Kein Event bei lautlosem Touch-Verlust', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  const evs = fig.feedTouches(session, [], 50);
  assert.strictEqual(evs.length, 0);
});

// ===========================================================
//  FIG-17 — Konfigurations-Defaults
// ===========================================================

test('FIG-17 — Default-Konfiguration liefert erwartete Werte', () => {
  const cfg = fig.configDefaults();
  assert.strictEqual(cfg.source_id, 'phone:test-1');
  assert.strictEqual(cfg.router_url, '');
  assert.strictEqual(cfg.figure_present_ms, 150);
  assert.strictEqual(cfg.pattern_tolerance, 0.05);
  assert.strictEqual(cfg.match_distance_px, 60);
  assert.strictEqual(cfg.tap_dwell_ms, 100);
  assert.strictEqual(cfg.angle_update_max_hz, 10);
  assert.strictEqual(cfg.angle_update_min_delta_deg, 3);
  assert.ok(typeof cfg.registry === 'object');
});

test('FIG-17 — source_id aus Config wird im Event verwendet (#6)', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    source_id: 'phone:wohnzimmer',
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  const evs = fig.feedTouches(session, tri, 0);
  assert.strictEqual(evs[0].source_id, 'phone:wohnzimmer');
});

// ===========================================================
//  FIG-13, FIG-14, FIG-15, FIG-16, FIG-18, FIG-19 — HTML-Smoke
// ===========================================================

const HTML_PATH = path.join(__dirname, '..', 'index.html');
const HTML = fs.readFileSync(HTML_PATH, 'utf8');

test('FIG-13 — HTML enthält Zielfeld mit Beschriftung', () => {
  assert.match(HTML, /id="zielfeld"[^>]*>[^<]*Figur hier auflegen/);
});

test('FIG-13 — Zielfeld bekommt CSS-Klasse "hidden" zum Verstecken', () => {
  assert.match(HTML, /#zielfeld\.hidden\s*\{[^}]*display:\s*none/);
});

test('FIG-14 — HTML hat Raw-Datendarstellungs-Element', () => {
  assert.match(HTML, /id="raw"/);
});

test('FIG-15 — Header enthält source_id-Platzhalter', () => {
  assert.match(HTML, /id="sid"/);
  assert.match(HTML, /Figuren-Erkennung[\s\S]*V1-Test/);
});

test('FIG-16 — Footer enthält Felder Letzter POST / Letzter Fehler / Events 60 s', () => {
  assert.match(HTML, /id="last-ok"/);
  assert.match(HTML, /id="last-err"/);
  assert.match(HTML, /id="counts"/);
});

test('FIG-18 — Portrait-Warnung im Markup mit @media (orientation: portrait)', () => {
  assert.match(HTML, /id="portrait"/);
  assert.match(HTML, /@media\s*\(\s*orientation:\s*portrait\s*\)/);
});

test('FIG-19 — Selbsttragend: keine externen Script-/Link-Quellen', () => {
  const scriptSrcs = [...HTML.matchAll(/<script[^>]*\bsrc="([^"]+)"/g)].map(m => m[1]);
  const linkHrefs  = [...HTML.matchAll(/<link[^>]*\bhref="([^"]+)"/g)].map(m => m[1]);
  for (const src of scriptSrcs) {
    assert.ok(src === './figlib.js' || src === 'figlib.js',
      `Unerwartete script src: "${src}" — nur sibling figlib.js erlaubt`);
  }
  for (const href of linkHrefs) {
    assert.ok(!href.includes('://'),
      `Unerwartete externe href: "${href}"`);
  }
});

test('FIG-19 — figlib.js liegt im selben Verzeichnis wie index.html', () => {
  const figlibPath = path.join(__dirname, '..', 'figlib.js');
  assert.ok(fs.existsSync(figlibPath), 'figlib.js fehlt');
});

// ===========================================================
//  FIG-9 / FIG-12 — Transport (HTML-Smoke)
// ===========================================================

test('FIG-9 — HTML enthält POST an <router_url>/event mit JSON-Header', () => {
  assert.match(HTML, /\.replace\(\/\\\/\+\$\/, ''\) \+ '\/event'/);
  assert.match(HTML, /method:\s*'POST'/);
  assert.match(HTML, /'Content-Type':\s*'application\/json'/);
});

test('FIG-12 — HTML enthält Retry-Backoffs 200/1000/5000 ms', () => {
  assert.match(HTML, /BACKOFFS\s*=\s*\[\s*200\s*,\s*1000\s*,\s*5000\s*\]/);
  assert.match(HTML, /postWithRetry/);
});

test('FIG-12 — HTML enthält keine Persistenz-Pufferung', () => {
  // Negativ-Probe: kein localStorage-Schreiben für ausstehende Events
  const persistencePattern = /localStorage\.setItem\([^)]*event/i;
  assert.ok(!persistencePattern.test(HTML),
    'HTML sollte keine Event-Persistenz haben (FIG-12: kein Puffer)');
});

// ===========================================================
//  FIG-8 — Centroid-Button wandert mit der Figur
// ===========================================================

test('FIG-8 — Button-Center folgt der Figur bei kontinuierlicher Translation', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  const c1 = { ...session.buttonCircle };
  // Verschiebe alle Punkte um (50, 30)
  const moved = tri.map(p => ({ id: p.id, x: p.x + 50, y: p.y + 30 }));
  fig.feedTouches(session, moved, 10);
  const c2 = session.buttonCircle;
  assert.ok(Math.abs((c2.x - c1.x) - 50) < 1e-6);
  assert.ok(Math.abs((c2.y - c1.y) - 30) < 1e-6);
});

// ===========================================================
//  FIG-6 / FIG-7 — Continuity-Fix (Re-Test 2026-05-20)
//  Bug: vor Fix wurde lastFramePoints bei n<3 auf null gesetzt;
//  kapazitives Flackern führte zu Re-Anker jeden Frame und cum
//  blieb dauerhaft bei 0. Neue Semantik: lastFramePoints bleibt
//  stehen, räumliches Matching auf dem nächsten 3-Punkt-Frame
//  entscheidet (Continuity vs. Re-Placement).
// ===========================================================

test('FIG-6/7 — lastFramePoints bleibt bei n<3 erhalten (Continuity über kurzen Touch-Verlust)', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  assert.ok(session.lastFramePoints, 'lastFramePoints muss nach figure_detected gesetzt sein');
  const snapshotBefore = session.lastFramePoints.map(p => ({ ...p }));

  // Touch-Verlust — Akku pausiert, aber lastFramePoints bleibt stehen
  fig.feedTouches(session, [], 10);
  assert.deepStrictEqual(session.lastFramePoints, snapshotBefore,
    'lastFramePoints darf bei n<3 NICHT auf null gesetzt werden');
  assert.strictEqual(session.cumulativeAngle, 0);
});

test('FIG-6/7 — Touch-Verlust + Rückkehr an dieselbe Stelle: match: ok, kein spurioses Delta', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    angle_update_min_delta_deg: 0.001,
    angle_update_max_hz: 1000,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  // Touch-Verlust für einen Moment
  fig.feedTouches(session, [], 10);
  // Selbe Figur an derselben Position wiederkommt (neue Touch-Identifier)
  const sameSpot = tri.map(p => ({ id: p.id + 100, x: p.x, y: p.y }));
  fig.feedTouches(session, sameSpot, 20);
  // matchPoints sollte erfolgreich sein, Delta ≈ 0, cum unverändert
  assert.strictEqual(session.lastMatchOk, 'ok');
  assert.ok(Math.abs(session.lastFrameDelta) < 0.01,
    `Delta erwartet ≈ 0, bekommen ${session.lastFrameDelta}`);
  assert.ok(Math.abs(session.cumulativeAngle) < 0.01);
});

test('FIG-14 — Diagnose-State (lastFrameDelta, lastMatchOk) wird gesetzt', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    angle_update_min_delta_deg: 0.001,
    angle_update_max_hz: 1000,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  // Vor figure_detected: keine Diagnose-Werte
  assert.strictEqual(session.lastMatchOk, null);
  assert.strictEqual(session.lastFrameDelta, 0);

  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  // Erster 3-Punkt-Frame nach figure_detected: re-anker, kein Delta
  assert.strictEqual(session.lastMatchOk, 'reanchor');
  assert.strictEqual(session.lastFrameDelta, 0);

  // Echte Rotation: match ok, Δ ≈ 30°
  const c = fig.centroid(tri);
  fig.feedTouches(session, tri.map(p => rotateAround(c, 30, p)), 10);
  assert.strictEqual(session.lastMatchOk, 'ok');
  assert.ok(Math.abs(session.lastFrameDelta - 30) < 0.5,
    `lastFrameDelta erwartet ≈ 30°, bekommen ${session.lastFrameDelta}`);
});

test('FIG-7 — match: fail wird gesetzt, wenn Punkte zu weit springen', () => {
  const session = fig.createSession({
    figure_present_ms: 0,
    match_distance_px: 20,
    registry: { A: [0.50, 0.70, 1.0] },
  });
  const tri = trianglesWithDescriptor([0.50, 0.70, 1.0]);
  fig.feedTouches(session, tri, 0);
  // Punkte massiv versetzen — über match_distance hinaus
  const farAway = tri.map(p => ({ id: p.id, x: p.x + 500, y: p.y + 500 }));
  fig.feedTouches(session, farAway, 10);
  assert.strictEqual(session.lastMatchOk, 'fail');
  assert.strictEqual(session.lastFrameDelta, 0);
  // Re-Anker → cum unverändert
  assert.strictEqual(session.cumulativeAngle, 0);
});

// ===========================================================
//  Periodischer Tick — HTML-Smoke
//  Bug-Fix nach Realtest 2026-05-20: ohne setInterval(50ms)
//  greift die 150-ms-Eintritts-Hysterese (FIG-2) nicht, wenn
//  die Figur stillsteht und keine touchmove-Events fließen.
// ===========================================================

test('FIG-2 / FIG-14 — index.html enthält periodischen Tick für State-Machine', () => {
  assert.match(HTML, /setInterval\([\s\S]*?figLib\.feedTouches/,
    'index.html muss feedTouches periodisch aufrufen, sonst greift FIG-2-Hysterese nicht bei stillstehender Figur');
});
