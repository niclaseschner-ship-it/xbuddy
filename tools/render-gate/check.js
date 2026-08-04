#!/usr/bin/env node
/**
 * check.js — Entry-Point des Render-Gates (RAT-24, #1160).
 *
 * Faehrt System-Chromium headless ueber puppeteer-core gegen die nginx-
 * Live-Origin (:8443, self-signed), prueft Tier-A-Invarianten plus optionalen
 * Tier-B-Kollisionsvertrag und gibt einen DETERMINISTISCHEN Bericht aus.
 *
 * Modus: BERICHT (RAT-24). Exit-Code ist im MVP IMMER 0 — auch bei Befunden.
 * Der Report ist das Produkt; der Flip-zu-Block kommt erst nach dem Fenster-
 * Trigger (#1160 Folge). Einzige Nicht-0-Exits: Harness-Bedienfehler
 * (unbekannte View, Browser startet nicht).
 *
 * Aufruf:
 *   node check.js <view-key>        z. B. node check.js plan/woche
 *   node check.js --all             alle Views aus views.json
 *   node check.js <view-key> --json nur JSON (fuer 3-Laeufe-Diff)
 *
 * Sprache: Deutsch.
 */

"use strict";

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import puppeteer from "puppeteer-core";
import {
  wireEvents,
  rectSignatureFn,
  domInvariantsFn,
  collisionContractFn,
} from "./invariants.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CHROMIUM_PATH = "/usr/bin/chromium";

// ─────────────────────────────────────────────────────────────────────────────
// CLI-Parsing
// ─────────────────────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = argv.slice(2);
  const opts = { all: false, json: false, view: null };
  for (const a of args) {
    if (a === "--all") opts.all = true;
    else if (a === "--json") opts.json = true;
    else if (a.startsWith("--")) { /* unbekanntes Flag ignorieren */ }
    else if (!opts.view) opts.view = a;
  }
  return opts;
}

// ─────────────────────────────────────────────────────────────────────────────
// Konfig laden
// ─────────────────────────────────────────────────────────────────────────────

function loadJson(relPath) {
  return JSON.parse(readFileSync(join(__dirname, relPath), "utf-8"));
}

// ─────────────────────────────────────────────────────────────────────────────
// Default-Wait: fonts.ready + Network-Idle + zwei stabile Rect-Snapshots
// ─────────────────────────────────────────────────────────────────────────────

async function defaultWait(page) {
  // 1) Web-Fonts geladen
  try {
    await page.evaluate(() => document.fonts.ready.then(() => true));
  } catch { /* document.fonts evtl. nicht da — kein Hard-Fail */ }

  // 2) Network-Idle (best effort; Timeout darf nicht haengen lassen)
  try {
    await page.waitForNetworkIdle({ idleTime: 500, timeout: 8000 });
  } catch { /* idle nie erreicht (z. B. Polling) — weiter zu den Snapshots */ }

  // 3) Zwei stabile Rect-Snapshots (gegen halb-hydrierte Frames)
  let prev = null;
  for (let i = 0; i < 12; i++) {
    const snap = await page.evaluate(rectSignatureFn);
    if (prev !== null && snap === prev) return true;
    prev = snap;
    await sleep(250);
  }
  return false; // nie stabil — Messung zaehlt trotzdem, wird im Report vermerkt
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ─────────────────────────────────────────────────────────────────────────────
// Deterministische Sortierung + Dedupe
// ─────────────────────────────────────────────────────────────────────────────

function dedupeSort(findings) {
  const seen = new Set();
  const out = [];
  for (const f of findings) {
    const key = [f.typ, f.selektor, f.detail, f.messwert].join("");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(f);
  }
  out.sort((x, y) => {
    const kx = [x.typ, x.selektor, x.detail, x.messwert].join("");
    const ky = [y.typ, y.selektor, y.detail, y.messwert].join("");
    return kx < ky ? -1 : kx > ky ? 1 : 0;
  });
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// Eine View pruefen
// ─────────────────────────────────────────────────────────────────────────────

async function checkView(browser, key, viewCfg, viewport) {
  // Eigener (Incognito-)Browser-Kontext pro View: kein Cache-/Cookie-Bleed
  // zwischen Views. So liefert eine View IM EINZEL-Lauf denselben Report wie
  // unter --all (z. B. die favicon-404-Negativ-Cache haengt sonst an der
  // Reihenfolge). Fallback auf das Default-Profil, falls die API fehlt.
  let context = null;
  let page;
  if (typeof browser.createBrowserContext === "function") {
    context = await browser.createBrowserContext();
    page = await context.newPage();
  } else if (typeof browser.createIncognitoBrowserContext === "function") {
    context = await browser.createIncognitoBrowserContext();
    page = await context.newPage();
  } else {
    page = await browser.newPage();
  }
  await page.setViewport({ width: viewport.width, height: viewport.height });

  const eventFindings = wireEvents(page);
  const result = {
    view: key,
    url: viewCfg.url,
    viewport: viewport.width + "x" + viewport.height,
    stabil: null,
    erreichbar: true,
    befunde: [],
  };

  try {
    const resp = await page.goto(viewCfg.url, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    if (resp && resp.status() >= 400) {
      result.befunde.push({
        typ: "request-fehler",
        selektor: "-",
        detail: viewCfg.url + " (Haupt-Dokument)",
        messwert: "status:" + resp.status(),
      });
    }
  } catch (err) {
    result.erreichbar = false;
    result.befunde.push({
      typ: "navigation-fehler",
      selektor: "-",
      detail: viewCfg.url + " | " + String(err && err.message ? err.message : err),
      messwert: "goto_fehlgeschlagen",
    });
    result.befunde = dedupeSort(result.befunde.concat(eventFindings));
    await page.close();
    if (context) await context.close();
    return result;
  }

  result.stabil = await defaultWait(page);

  // Tier-A DOM/Geometrie im Browser-Kontext.
  // opts.checkUnderfill: nur bei responsiven Views (viewCfg.responsive === true,
  // DC-18). Fixe Views (Letterbox) erhalten keinen underfill-Befund.
  const domOpts = { checkUnderfill: !!viewCfg.responsive };
  const domFindings = await page.evaluate(domInvariantsFn, viewport, domOpts);

  // Tier-B Kollisionsvertrag (falls vorhanden)
  let tierBFindings = [];
  if (viewCfg.contract) {
    const contract = loadJson(viewCfg.contract);
    tierBFindings = await page.evaluate(collisionContractFn, contract);
  }

  result.befunde = dedupeSort(
    result.befunde.concat(eventFindings, domFindings, tierBFindings)
  );

  if (result.stabil === false) {
    result.befunde.unshift({
      typ: "wait-instabil",
      selektor: "-",
      detail: "Rect-Snapshots wurden im Zeitfenster nie identisch (halb-hydriert?)",
      messwert: "stabil:false",
    });
  }

  await page.close();
  if (context) await context.close();
  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// Report-Rendering (menschenlesbar)
// ─────────────────────────────────────────────────────────────────────────────

function renderHuman(results) {
  const lines = [];
  lines.push("═══ Render-Gate — Bericht (RAT-24, #1160) ═══");
  for (const r of results) {
    lines.push("");
    lines.push("View: " + r.view + "  |  Viewport: " + r.viewport);
    lines.push("URL:  " + r.url);
    if (r.stabil === false) lines.push("Hinweis: Frame nie stabil (siehe wait-instabil).");
    if (r.befunde.length === 0) {
      lines.push("0 Befunde — view: " + r.view + ", viewport: " + r.viewport + ", url: " + r.url);
    } else {
      lines.push(r.befunde.length + " Befund(e):");
      for (const f of r.befunde) {
        lines.push("  - [" + f.typ + "] " + f.selektor +
                   "  ·  " + f.detail + "  ·  " + f.messwert);
      }
    }
  }
  const total = results.reduce((n, r) => n + r.befunde.length, 0);
  lines.push("");
  lines.push("─── Summe: " + total + " Befund(e) ueber " + results.length + " View(s) ───");
  return lines.join("\n");
}

// ─────────────────────────────────────────────────────────────────────────────
// main
// ─────────────────────────────────────────────────────────────────────────────

async function main() {
  const opts = parseArgs(process.argv);
  const cfg = loadJson("views.json");
  const viewport = cfg.viewport || { width: 1920, height: 1080 };

  // Jeder View-Eintrag hat einen relativen path; hier einmalig zur
  // voll-qualifizierten Ziel-URL aufloesen, damit der Rest des Harness
  // viewCfg.url unveraendert benutzen kann.
  const origin = cfg.origin || "";
  for (const viewCfg of Object.values(cfg.views)) {
    viewCfg.url = origin + viewCfg.path;
  }

  let keys;
  if (opts.all) {
    keys = Object.keys(cfg.views);
  } else if (opts.view && cfg.views[opts.view]) {
    keys = [opts.view];
  } else {
    process.stderr.write(
      "Unbekannte oder fehlende View. Verfuegbar:\n  " +
      Object.keys(cfg.views).join("\n  ") +
      "\nAufruf: node check.js <view-key> | --all [--json]\n"
    );
    process.exit(2);
  }

  let browser;
  try {
    browser = await puppeteer.launch({
      executablePath: CHROMIUM_PATH,
      headless: "new",
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
      acceptInsecureCerts: true,      // self-signed Origin (:8443)
      ignoreHTTPSErrors: true,        // Alias aelterer puppeteer-Versionen
    });
  } catch (err) {
    process.stderr.write(
      "Chromium-Start fehlgeschlagen (" + CHROMIUM_PATH + "): " +
      String(err && err.message ? err.message : err) + "\n"
    );
    process.exit(3);
  }

  const results = [];
  try {
    for (const key of keys) {
      const viewCfg = cfg.views[key];
      // Per-View-Viewport (AC2, #1322): viewCfg.viewport ueberschreibt den
      // globalen Default. Fallback: globaler viewport aus views.json (1920x1080).
      const effectiveViewport = viewCfg.viewport || viewport;
      const r = await checkView(browser, key, viewCfg, effectiveViewport);
      results.push(r);
    }
  } finally {
    await browser.close();
  }

  // Report-Objekt (deterministisch, keine Timestamps)
  const report = {
    gate: "render-gate",
    ratifiziert: "RAT-24",
    viewport: viewport.width + "x" + viewport.height,
    summe_befunde: results.reduce((n, r) => n + r.befunde.length, 0),
    views: results,
  };

  if (opts.json) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  } else {
    process.stdout.write(renderHuman(results) + "\n\n");
    process.stdout.write("─── JSON ───\n");
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  }

  // Bericht-Modus: Exit 0 auch bei Befunden (RAT-24).
  process.exit(0);
}

main().catch((err) => {
  process.stderr.write("Unerwarteter Fehler: " + (err && err.stack ? err.stack : err) + "\n");
  process.exit(1);
});
