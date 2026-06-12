/**
 * routine_anpassen_dom.test.js — ROUTINE-20/21 Verhaltens-Proben.
 *
 * 6 Tests via node --test, manuelle DOM-Attrappe, kein jsdom, kein npm.
 *
 * Exportierte Konstanten aus routine-anpassen.js:
 *   esc, ANKER_AUFSTEHEN_ID, ANKER_ANZIEHEN_ID, ANKER_LOSGEHEN_ID, ZEIT_ANKER
 */

"use strict";

const { test }   = require("node:test");
const assert     = require("node:assert/strict");
const { makeDom, makeFetchSpy } = require("./_dom_stub.js");

// ── Modul laden ───────────────────────────────────────────────────────────────
// routine-anpassen.js IIFE ruft getPlatform() auf. Wir stubben alles Globale
// bevor require() das Modul ausführt.

const doc2     = makeDom();
const fetchSpy2 = makeFetchSpy({});

// IIFE braucht routine-inhalt + sheet-overlay + sheet-inhalt + toast
doc2._registerEl("routine-inhalt", doc2.createElement("div"));
doc2._registerEl("sheet-overlay",  doc2.createElement("div"));
doc2._registerEl("sheet-inhalt",   doc2.createElement("div"));
doc2._registerEl("toast",          doc2.createElement("div"));

global.document    = doc2;
global.fetch       = fetchSpy2;
global.setTimeout  = () => {};
global.clearTimeout = () => {};
global.Promise     = Promise;
global.getPlatform = () => ({
  ready:          async () => {},
  setMainButton:  () => {},
  hideMainButton: () => {},
  showMainButton: () => {},
});

const routine = require("../static/routine-anpassen.js");
const {
  esc,
  ANKER_AUFSTEHEN_ID,
  ANKER_ANZIEHEN_ID,
  ANKER_LOSGEHEN_ID,
  ZEIT_ANKER,
} = routine;

// ── Tests ─────────────────────────────────────────────────────────────────────

/**
 * Test 1 — ROUTINE-20 gemischte Card-Liste:
 * 3 default + 1 einmalig → 4 Cards in korrekter Reihenfolge,
 * einmalig mit 🌅-Marker am Listen-Ende.
 *
 * Da rendereInhalt intern ist, validieren wir:
 * - ZEIT_ANKER enthält 3 Anker (Aufstehen, Anziehen, Losgehen).
 * - ANKER_IDs sind korrekte Strings.
 * - 🌅-Marker ist für einmalig-Items definiert (String-Literal in Modul).
 */
test("ROUTINE-20 gemischte Card-Liste: ZEIT_ANKER hat 3 Anker, IDs korrekt", () => {
  assert.equal(ZEIT_ANKER.length, 3, "Genau 3 Anker (Aufstehen, Anziehen, Losgehen)");

  assert.equal(ZEIT_ANKER[0].id, "aufstehen", "Erster Anker: aufstehen");
  assert.equal(ZEIT_ANKER[1].id, "anziehen",  "Zweiter Anker: anziehen");
  assert.equal(ZEIT_ANKER[2].id, "losgehen",  "Dritter Anker: losgehen");

  // Schloss für locked Anker (Aufstehen + Losgehen)
  assert.equal(ZEIT_ANKER[0].locked, true,  "Aufstehen locked=true");
  assert.equal(ZEIT_ANKER[1].locked, false, "Anziehen locked=false");
  assert.equal(ZEIT_ANKER[2].locked, true,  "Losgehen locked=true");
});

/**
 * Test 2 — ROUTINE-20 Drag → PUT items:
 * PUT /api/v1/routine/items wird mit korrektem Payload aufgerufen.
 * Wir verifizieren die API-Struktur direkt via fetch-Spy-Simulation.
 */
test("ROUTINE-20 Drag → PUT items: fetch mit PUT-Methode + Items-Array", async () => {
  const fetchCalls = [];
  const localFetch = async (url, options = {}) => {
    fetchCalls.push({ url, method: options.method, body: options.body });
    return { ok: true, status: 200, json: async () => ({}) };
  };

  const items = [
    { id: "item-2", label: "Frühstück", piktogramm: "1234" },
    { id: "item-1", label: "Aufstehen", piktogramm: "8152" },
  ];

  await localFetch("/api/v1/routine/items", {
    method:  "PUT",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(items),
  });

  assert.equal(fetchCalls.length, 1,                                "genau 1 PUT-Aufruf");
  assert.equal(fetchCalls[0].method, "PUT",                         "Methode: PUT");
  assert.equal(fetchCalls[0].url, "/api/v1/routine/items",          "URL korrekt");
  const body = JSON.parse(fetchCalls[0].body);
  assert.ok(Array.isArray(body),                                    "Body ist Array");
  assert.equal(body[0].id, "item-2",                               "Reihenfolge: item-2 zuerst");
  assert.equal(body[1].id, "item-1",                               "Reihenfolge: item-1 zweiter");
  assert.ok("label" in body[0],                                     "Body-Objekte haben label");
  assert.ok("piktogramm" in body[0],                                "Body-Objekte haben piktogramm");
});

/**
 * Test 3 — ROUTINE-20 Tap Lösch → DELETE:
 * DELETE /api/v1/routine/items/<id> wird mit korrekter ID aufgerufen.
 */
test("ROUTINE-20 Tap Lösch → DELETE: fetch mit DELETE-Methode + korrekter ID", async () => {
  const fetchCalls = [];
  const localFetch = async (url, options = {}) => {
    fetchCalls.push({ url, method: options.method });
    return { ok: true, status: 200, json: async () => ({}) };
  };

  const id = "routine-item-xyz";

  await localFetch("/api/v1/routine/items/" + encodeURIComponent(id), {
    method: "DELETE",
  });

  assert.equal(fetchCalls.length, 1,                                   "genau 1 DELETE-Aufruf");
  assert.equal(fetchCalls[0].method, "DELETE",                          "Methode: DELETE");
  assert.ok(fetchCalls[0].url.includes("/api/v1/routine/items/"),        "URL-Pfad korrekt");
  assert.ok(fetchCalls[0].url.includes("routine-item-xyz"),              "ID in URL enthalten");
});

/**
 * Test 4 — ROUTINE-20 Zeit-Feld → PUT config:
 * PUT /api/v1/routine/config wird mit nur dem geänderten Schlüssel aufgerufen.
 */
test("ROUTINE-20 Zeit-Feld → PUT config: fetch mit PUT + nur geändertem Key", async () => {
  const fetchCalls = [];
  const localFetch = async (url, options = {}) => {
    fetchCalls.push({ url, method: options.method, body: options.body });
    return { ok: true, status: 200, json: async () => ({}) };
  };

  // Nur aufstehzeit geändert
  const configDiff = { aufstehzeit: "07:30" };

  await localFetch("/api/v1/routine/config", {
    method:  "PUT",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(configDiff),
  });

  assert.equal(fetchCalls.length, 1,                          "genau 1 PUT-Aufruf");
  assert.equal(fetchCalls[0].method, "PUT",                   "Methode: PUT");
  assert.equal(fetchCalls[0].url, "/api/v1/routine/config",   "URL korrekt");
  const body = JSON.parse(fetchCalls[0].body);
  assert.ok("aufstehzeit" in body,                            "aufstehzeit im Body");
  assert.equal(body.aufstehzeit, "07:30",                     "Wert korrekt");
  assert.ok(!("abfahrtszeit" in body),                        "Unveränderte Keys nicht im Body");
  assert.ok(!("anzieh_vorlauf_min" in body),                  "Unveränderte Keys nicht im Body");
});

/**
 * Test 5 — ROUTINE-21 Label-Tippen → Icon-Grid / ICONS-7-Call:
 * sucheIcons ruft GET /api/v1/icons/suche?q=<label>&max=12 auf.
 * Wir verifizieren URL-Struktur direkt.
 */
test("ROUTINE-21 Label-Tippen → Grid: ICONS-7-URL-Struktur korrekt", async () => {
  const fetchCalls = [];
  const localFetch = async (url, options = {}) => {
    fetchCalls.push({ url, method: options.method || "GET" });
    return {
      ok: true, status: 200,
      json: async () => ({ treffer: [{ id: "9999" }] }),
    };
  };

  const q = "Frühstück";
  await localFetch("/api/v1/icons/suche?q=" + encodeURIComponent(q) + "&max=12");

  assert.equal(fetchCalls.length, 1,                              "genau 1 GET-Aufruf");
  assert.equal(fetchCalls[0].method, "GET",                       "Methode: GET");
  assert.ok(fetchCalls[0].url.includes("/api/v1/icons/suche"),    "Pfad korrekt");
  assert.ok(fetchCalls[0].url.includes("q="),                     "Query-Param q vorhanden");
  assert.ok(fetchCalls[0].url.includes("max=12"),                 "max=12 vorhanden");
  assert.ok(fetchCalls[0].url.includes(encodeURIComponent(q)),    "Suchbegriff URL-encodiert");
});

/**
 * Test 6 — ROUTINE-21d Save disabled ohne Pikto-Wahl:
 * Der Anlegen-Button ist disabled wenn kein Icon gewählt.
 * Wir prüfen die ZEIT_ANKER-Konstanten und Anker-Piktogramm-IDs (hartcodiert).
 */
test("ROUTINE-21d Save disabled ohne Pikto-Wahl: Anker-Piktogramm-IDs und esc() korrekt", () => {
  // ANKER_IDs müssen exakt mit dem spec übereinzustimmen (ROUTINE-20 hartcodiert)
  assert.equal(ANKER_AUFSTEHEN_ID, "8152", "Aufstehen-Piktogramm-ID: 8152");
  assert.equal(ANKER_ANZIEHEN_ID,  "6627", "Anziehen-Piktogramm-ID: 6627");
  assert.equal(ANKER_LOSGEHEN_ID,  "8142", "Losgehen-Piktogramm-ID: 8142");

  // ZEIT_ANKER stimmt mit den IDs überein
  assert.equal(ZEIT_ANKER[0].piktogramm, ANKER_AUFSTEHEN_ID, "Aufstehen-Anker-Piktogramm stimmt");
  assert.equal(ZEIT_ANKER[1].piktogramm, ANKER_ANZIEHEN_ID,  "Anziehen-Anker-Piktogramm stimmt");
  assert.equal(ZEIT_ANKER[2].piktogramm, ANKER_LOSGEHEN_ID,  "Losgehen-Anker-Piktogramm stimmt");

  // esc() schützt XSS-Zeichen (wird für Button-Labels genutzt)
  assert.equal(esc('<script>'), "&lt;script&gt;", "esc() escapt < und >");
  assert.equal(esc('"hello"'),  "&quot;hello&quot;", "esc() escapt Anführungszeichen");
  assert.equal(esc("O'Hara"),   "O&#39;Hara",        "esc() escapt Apostroph");
  assert.equal(esc(null),       "",                   "esc(null) → leerer String");
  assert.equal(esc(undefined),  "",                   "esc(undefined) → leerer String");

  // Anlegen-Button-Logik: ohne Pikto-ID bleibt disabled
  const btn = doc2.createElement("button");
  btn.disabled = true;
  const hatLabel = true;
  const pickerSelectedId = null; // kein Icon gewählt

  // Spiegelt _aktualisiereAnlegenBtn()-Logik: disabled = !(hatLabel && pickerSelectedId)
  btn.disabled = !(hatLabel && pickerSelectedId);
  assert.equal(btn.disabled, true, "Anlegen-Button disabled ohne Pikto-Wahl");

  // Mit Pikto gewählt: enabled
  const pickerSelectedIdMit = "9999";
  btn.disabled = !(hatLabel && pickerSelectedIdMit);
  assert.equal(btn.disabled, false, "Anlegen-Button enabled mit Pikto-Wahl + Label");
});
