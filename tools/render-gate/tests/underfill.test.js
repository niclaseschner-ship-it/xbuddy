#!/usr/bin/env node
/**
 * underfill.test.js — Test der Underfill-Fuellinvariante (#1322, AC1+AC2).
 *
 * Faehrt die ECHTE domInvariantsFn aus invariants.js via puppeteer-core gegen
 * synthetische HTML-Seiten (page.setContent). Keine Handkopie der Logik.
 *
 * Aufruf: node tests/underfill.test.js
 */

import puppeteer from "puppeteer-core";
import { domInvariantsFn } from "../invariants.js";

const CHROMIUM_PATH = "/usr/bin/chromium";

// ─────────────────────────────────────────────────────────────────────────────
// Hilfsfunktion: synthetische Seite laden + domInvariantsFn ausfuehren
// ─────────────────────────────────────────────────────────────────────────────

async function runInvariantsOnHtml(page, html, viewport, opts) {
  await page.setViewport({ width: viewport.width, height: viewport.height });
  await page.setContent(html, { waitUntil: "load" });
  return page.evaluate(domInvariantsFn, viewport, opts);
}

// ─────────────────────────────────────────────────────────────────────────────
// Test-Faelle
// ─────────────────────────────────────────────────────────────────────────────

// (a) Kurzer zentrierter Body — underfill erwartet (responsive View, AC1)
const CASE_A = {
  name: "(a) kurzer Body 400x300 in 1920x1200 Viewport → underfill",
  html: `<!DOCTYPE html><html><head><style>
    html, body { margin: 0; padding: 0; }
    body { width: 400px; height: 300px; background: blue; }
  </style></head><body><p>kurzer Inhalt</p></body></html>`,
  viewport: { width: 1920, height: 1200 },
  opts: { checkUnderfill: true },
  expectUnderfill: true,
};

// (b) Full-bleed Body — kein underfill erwartet (responsive View, AC1)
const CASE_B = {
  name: "(b) full-bleed 100vw x 100vh → kein underfill",
  html: `<!DOCTYPE html><html><head><style>
    html, body { margin: 0; padding: 0; width: 100vw; height: 100vh; }
    body { background: green; }
  </style></head><body><p>volle Flaeche</p></body></html>`,
  viewport: { width: 1920, height: 1200 },
  opts: { checkUnderfill: true },
  expectUnderfill: false,
};

// (c) Scroll-Container: Body fuellt Viewport, Listen-Inhalt kuerzer → kein underfill
// Der Body hat 100vw x 100vh (responsive); darin ein overflow-y:auto Container
// mit nur 200px kurzem Inhalt. Body-Rect selbst fuellt → kein underfill.
const CASE_C = {
  name: "(c) scroll-container: body fuellt, Listen-Inhalt kuerzer → kein underfill",
  html: `<!DOCTYPE html><html><head><style>
    html, body { margin: 0; padding: 0; width: 100vw; height: 100vh; }
    body { background: #eee; }
    .liste { overflow-y: auto; height: 100vh; }
    .liste-inhalt { height: 200px; background: #ccc; }
  </style></head><body>
    <div class="liste"><div class="liste-inhalt">nur 200px Inhalt</div></div>
  </body></html>`,
  viewport: { width: 1920, height: 1200 },
  opts: { checkUnderfill: true },
  expectUnderfill: false,
};

// (d) Fixe View (checkUnderfill: false): gleicher kurzer Body wie (a),
// aber kein underfill-Befund weil opts.checkUnderfill === false (DC-18-Gate, AC2)
const CASE_D = {
  name: "(d) fixe View (checkUnderfill:false): kurzer Body → KEIN underfill-Befund",
  html: CASE_A.html,
  viewport: { width: 1920, height: 1080 },
  opts: { checkUnderfill: false },
  expectUnderfill: false,
};

const CASES = [CASE_A, CASE_B, CASE_C, CASE_D];

// ─────────────────────────────────────────────────────────────────────────────
// Ausfuehren
// ─────────────────────────────────────────────────────────────────────────────

let browser;
let passed = 0;
let failed = 0;

try {
  browser = await puppeteer.launch({
    executablePath: CHROMIUM_PATH,
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage();

  for (const tc of CASES) {
    let findings;
    try {
      findings = await runInvariantsOnHtml(page, tc.html, tc.viewport, tc.opts);
    } catch (err) {
      process.stdout.write("[FAIL] " + tc.name + " | Fehler: " + String(err && err.message ? err.message : err) + "\n");
      failed++;
      continue;
    }

    const gotUnderfill = findings.some((f) => f.typ === "underfill");
    const ok = gotUnderfill === tc.expectUnderfill;

    const mark = ok ? "OK" : "FAIL";
    const detail = ok
      ? ""
      : " | erwartet underfill=" + tc.expectUnderfill + ", erhalten=" + gotUnderfill +
        (findings.length ? " [" + findings.map((f) => f.typ + ":" + f.messwert).join(", ") + "]" : "");

    process.stdout.write("[" + mark + "] " + tc.name + detail + "\n");

    if (ok) passed++;
    else failed++;
  }

  await page.close();
} finally {
  if (browser) await browser.close();
}

process.stdout.write("\n── Ergebnis: " + passed + " bestanden, " + failed + " fehlgeschlagen ──\n");
process.stdout.write("   Echte domInvariantsFn aus invariants.js evaluiert via puppeteer-core/Chromium.\n");

if (failed > 0) {
  process.exit(1);
}
