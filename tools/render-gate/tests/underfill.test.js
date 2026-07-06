#!/usr/bin/env node
/**
 * underfill.test.js — Unit-Test der Underfill-Fuellinvariante (#1322).
 *
 * Synthetische Rects, kein Browser/Puppeteer noetig. Die Logik spiegelt
 * invariants.js domInvariantsFn Abschnitt 6 exakt wider. Wird in der
 * Self-Gate-Phase als "node-Unit der Invariante" ausgefuehrt.
 *
 * Aufruf: node tests/underfill.test.js
 */

"use strict";

// ─────────────────────────────────────────────────────────────────────────────
// Isolierte Underfill-Logik (spiegelt domInvariantsFn § 6 exakt)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Prueft eine synthetische Body-Bounding-Box gegen ein Viewport.
 * Gibt ein Array von Befunden zurueck (wie domInvariantsFn).
 *
 * @param {{ width: number, height: number }} bodyRect  Gemessene Body-Box
 * @param {{ width: number, height: number }} viewport  Viewport-Dimensionen
 * @returns {{ typ: string, selektor: string, detail: string, messwert: string }[]}
 */
function checkUnderfill(bodyRect, viewport) {
  const W = viewport.width;
  const H = viewport.height;
  const FILL_EPS = 0.05;

  const unterW = W - bodyRect.width;
  const unterH = H - bodyRect.height;

  if (unterW > W * FILL_EPS || unterH > H * FILL_EPS) {
    return [{
      typ: "underfill",
      selektor: "body",
      detail: "Content-Bounding-Box kleiner als Viewport " + W + "x" + H +
              " (DC-18: Fuellung erwartet)",
      messwert: "leerband_breite:" + Math.round(Math.max(0, unterW)) +
                "px,leerband_hoehe:" + Math.round(Math.max(0, unterH)) + "px",
    }];
  }
  return [];
}

// ─────────────────────────────────────────────────────────────────────────────
// Test-Faelle
// ─────────────────────────────────────────────────────────────────────────────

const TESTS = [
  // ── Sollte KEIN underfill liefern ─────────────────────────────────────────
  {
    name: "Exakte Passung 1920x1200 (essen/wunsch DC-18)",
    bodyRect: { width: 1920, height: 1200 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: false,
  },
  {
    name: "Exakte Passung 1920x1080 (fixed views)",
    bodyRect: { width: 1920, height: 1080 },
    viewport: { width: 1920, height: 1080 },
    expectUnderfill: false,
  },
  {
    name: "Innerhalb Toleranz: 1px Leerband (Sub-Pixel-Toleranz)",
    bodyRect: { width: 1919, height: 1199 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: false,
  },
  {
    name: "Innerhalb Toleranz: 4,9% Leerband (knapp unter Schwelle)",
    // 4.9% von 1200 = 58.8px → unterH = 58 → kein Befund
    bodyRect: { width: 1920, height: 1142 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: false,
  },
  {
    name: "Scroll-Container-Szenario: Body fuellt Viewport, Listeninhalt kuerzer",
    // Body = 1920x1200 (scroll-Container selbst fuellt), Listeninhalt irrelevant
    bodyRect: { width: 1920, height: 1200 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: false,
  },
  // ── Sollte underfill liefern ───────────────────────────────────────────────
  {
    name: "Hoehen-Leerband: Body nur 700px bei Viewport 1200px",
    bodyRect: { width: 1920, height: 700 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: true,
  },
  {
    name: "Breiten-Leerband: Body nur 800px bei Viewport 1920px",
    bodyRect: { width: 800, height: 1200 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: true,
  },
  {
    name: "Beide Dimensionen unterschritten",
    bodyRect: { width: 900, height: 600 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: true,
  },
  {
    name: "Genau an Schwelle: 5% Leerband Hoehe (Grenzfall — soll Befund)",
    // 5% von 1200 = 60px → unterH = 60 → 60 > 1200*0.05=60 → NICHT (>), kein Befund
    // Also: 61px → Befund
    bodyRect: { width: 1920, height: 1139 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: true,
  },
  {
    name: "Leerband durch falschen Viewport (fixed view bei falschem Viewport)",
    // Haette check.js nicht den per-View-Viewport genutzt: 1080 statt 1200
    // Body = 1080px, viewport irrtuemlch = 1200px → underfill erkannt
    bodyRect: { width: 1920, height: 1080 },
    viewport: { width: 1920, height: 1200 },
    expectUnderfill: true,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Ausfuehren
// ─────────────────────────────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

for (const tc of TESTS) {
  const findings = checkUnderfill(tc.bodyRect, tc.viewport);
  const gotUnderfill = findings.some((f) => f.typ === "underfill");
  const ok = gotUnderfill === tc.expectUnderfill;

  const mark = ok ? "OK" : "FAIL";
  const detail = ok
    ? ""
    : " | erwartet underfill=" + tc.expectUnderfill + ", erhalten=" + gotUnderfill +
      (findings.length ? " (" + findings[0].messwert + ")" : "");

  process.stdout.write("[" + mark + "] " + tc.name + detail + "\n");

  if (ok) passed++;
  else failed++;
}

process.stdout.write("\n── Ergebnis: " + passed + " bestanden, " + failed + " fehlgeschlagen ──\n");

if (failed > 0) {
  process.exit(1);
}
