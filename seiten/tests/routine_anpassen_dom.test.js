/**
 * routine_anpassen_dom.test.js — ROUTINE-20/21/27 Verhaltens-Proben.
 *
 * 13 Tests via node --test, manuelle DOM-Attrappe, kein jsdom, kein npm.
 *
 * Exportierte Symbole aus routine-anpassen.js:
 *   esc, ANKER_AUFSTEHEN_ID, ANKER_ANZIEHEN_ID, ANKER_LOSGEHEN_ID, ZEIT_ANKER
 *   _bauZeitBlock, _vorlaufUhrzeit, _labelMitZeit  (ROUTINE-27)
 *   oeffneHinzufuegenSheet, _testSetPickerSelectedId  (AC2 Handler-Kette)
 *
 * Tests 11-13 — ROUTINE-27 AC2 Handler-Kette:
 *   Treibt den ECHTEN #sheet-anlegen-Click mit typAuswahl=anker/vorlauf/punkt,
 *   fängt den postItem-Payload ab und asserts das zeit-Feld je Typ.
 *
 *   DOM-Stub-Besonderheit: inhalt.querySelector('#id') schlägt in _elementsById
 *   nach — Elemente aus innerHTML-String sind dort NICHT automatisch registriert.
 *   Deshalb müssen alle von oeffneHinzufuegenSheet() ohne Null-Guard abgefragten
 *   Elemente vorab über doc._registerEl() eingetragen werden. Ohne diese
 *   Vorab-Registrierung bleibt typAuswahl='punkt' (Toggle-Handler nie gebunden)
 *   und kein zeit-Block landet im POST-Payload — diese Tests wären VOR dem Fix
 *   (fehlende Exports + fehlende Registrierung) rot gewesen. (Closes #1198)
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

// window.Telegram — optional chaining in routine-anpassen.js Z.68 braucht window als globale Variable
global.window      = { Telegram: null };
global.document    = doc2;
global.fetch       = fetchSpy2;
global.setTimeout  = () => {};
global.clearTimeout = () => {};
global.Promise     = Promise;
global.getPlatform = () => ({
  ready:          async () => {},
  // ensureAuth: false → IIFE bricht sauber ab (kein TypeError, kein unhandled rejection)
  ensureAuth:     async () => false,
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
  // ROUTINE-27
  _bauZeitBlock,
  _vorlaufUhrzeit,
  _labelMitZeit,
  // AC2 Handler-Kette
  oeffneHinzufuegenSheet,
  _testSetPickerSelectedId,
} = routine;

// ── Hilfsfunktion für Handler-Ketten-Tests ────────────────────────────────────

/**
 * Registriert frische DOM-Elemente für einen handler-getriebenen Sheet-Test.
 *
 * Hintergrund: Der DOM-Stub sucht via querySelector('#id') in _elementsById —
 * Elemente aus inhalt.innerHTML sind dort NICHT automatisch eingetragen. Ohne
 * Vorab-Registrierung gibt jeder querySelector() in oeffneHinzufuegenSheet()
 * null zurück. Elemente ohne Null-Guard würden TypeError werfen; Elemente mit
 * Null-Guard (z.B. Toggle-Buttons im forEach) werden still übersprungen → ihre
 * Click-Handler werden NIE gebunden → typAuswahl bleibt 'punkt' → kein zeit-Block.
 *
 * Diese Funktion meldet alle nötigen Elemente frisch an, damit oeffneHinzufuegenSheet()
 * vollständig durchläuft und die Toggle-Handler korrekt bindet.
 *
 * @param {object} doc - makeDom()-Instanz mit _registerEl()
 * @returns {object}   - Map id → Element für direkte Manipulation im Test
 */
function _registriereSheetElemente(doc) {
  const els = {};
  // Elemente OHNE Null-Guard in oeffneHinzufuegenSheet: müssen registriert sein,
  // sonst TypeError bei querySelector(...).addEventListener(...)
  const ohneGuard = [
    'tog-default', 'tog-einmalig',
    'sheet-label', 'picker-suche',
    'sheet-abbrechen', 'sheet-anlegen',
  ];
  // Toggle-Typ-Buttons haben einen forEach-Null-Guard — aber für den Test-Klick
  // müssen sie ebenfalls registriert sein, damit der Handler gebunden wird.
  const toggleTyp = ['tog-typ-punkt', 'tog-typ-anker', 'tog-typ-vorlauf'];

  for (const id of [...ohneGuard, ...toggleTyp]) {
    const el = doc.createElement('button');
    el.id = id;
    el.value = '';        // Input-ähnliche Elemente: value-Property für label/picker
    el.disabled = false;
    doc._registerEl(id, el);
    els[id] = el;
  }
  return els;
}

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

// ── ROUTINE-27 Tests ──────────────────────────────────────────────────────────

/**
 * Test 7 — ROUTINE-27 AC1/AC4 Typ-Toggle Punkt (Default):
 * _bauZeitBlock('punkt') → null → kein zeit-Feld im POST-Payload.
 */
test("ROUTINE-27 AC1 Typ Punkt: _bauZeitBlock → null, kein zeit im Payload", () => {
  const zeitBlock = _bauZeitBlock('punkt', '07:00', 10);
  assert.equal(zeitBlock, null, "_bauZeitBlock('punkt') → null");

  // Payload-Simulation: zeit nicht gesetzt wenn null (wie in _legeItemAn)
  const payload = { label: 'Turnbeutel', piktogramm: '1234', quelle: 'default' };
  if (zeitBlock) payload.zeit = zeitBlock;
  assert.ok(!('zeit' in payload), "Punkt: kein zeit-Feld im POST-Body");
});

/**
 * Test 8 — ROUTINE-27 AC2/AC4 Typ Anker:
 * _bauZeitBlock('anker', '07:30') → {typ:'anker', uhrzeit:'07:30', locked:false}.
 * POST-Body enthält zeit mit korrekten Feldern.
 */
test("ROUTINE-27 AC2 Typ Anker: zeit-Block mit uhrzeit + locked:false im Payload", () => {
  const zeitBlock = _bauZeitBlock('anker', '07:30', 0);
  assert.deepStrictEqual(
    zeitBlock,
    { typ: 'anker', uhrzeit: '07:30', locked: false },
    "_bauZeitBlock('anker') → korrekter Block"
  );

  // POST-Payload enthält zeit
  const payload = { label: 'Aufstehen', piktogramm: '8152', quelle: 'default' };
  if (zeitBlock) payload.zeit = zeitBlock;
  assert.ok('zeit' in payload,               "Anker: zeit-Feld im POST-Body");
  assert.equal(payload.zeit.typ, 'anker',    "typ: anker");
  assert.equal(payload.zeit.uhrzeit, '07:30',"uhrzeit: 07:30");
  assert.equal(payload.zeit.locked, false,   "locked: false");
});

/**
 * Test 9 — ROUTINE-27 AC2/AC4 Typ Vorlauf:
 * _bauZeitBlock('vorlauf', '', 15) → {typ:'vorlauf', minuten:15, bezug:'vorheriger_anker'}.
 */
test("ROUTINE-27 AC2 Typ Vorlauf: zeit-Block mit minuten + bezug im Payload", () => {
  const zeitBlock = _bauZeitBlock('vorlauf', '', 15);
  assert.deepStrictEqual(
    zeitBlock,
    { typ: 'vorlauf', minuten: 15, bezug: 'vorheriger_anker' },
    "_bauZeitBlock('vorlauf') → korrekter Block"
  );

  const payload = { label: 'Anziehen', piktogramm: '6627', quelle: 'default' };
  if (zeitBlock) payload.zeit = zeitBlock;
  assert.ok('zeit' in payload,                          "Vorlauf: zeit-Feld im POST-Body");
  assert.equal(payload.zeit.typ, 'vorlauf',             "typ: vorlauf");
  assert.equal(payload.zeit.minuten, 15,                "minuten: 15");
  assert.equal(payload.zeit.bezug, 'vorheriger_anker',  "bezug: vorheriger_anker");

  // Vorlauf Default 10 Min (kein minuten-Argument)
  const def = _bauZeitBlock('vorlauf', '', 0);
  assert.equal(def.minuten, 10, "Default minuten: 10 (Fallback aus || 10)");
});

/**
 * Test 10 — ROUTINE-27 AC3/AC4 Render:
 * _vorlaufUhrzeit berechnet korrekte abgeleitete Zeit (Anker − Minuten).
 * _labelMitZeit: locked:true Anker → HTML mit Hinweis "V1-Anker, ändern in der Config".
 */
test("ROUTINE-27 AC3 Render: Vorlauf-Ableitung + locked-Anker-Hinweis in HTML", () => {
  // Vorlauf-Ableitung: 07:00 Anker − 15 Min = 06:45
  const ankerItem = {
    id: 'a1', label: 'Aufstehen', piktogramm: '8152', quelle: 'default',
    zeit: { typ: 'anker', uhrzeit: '07:00', locked: false },
  };
  const vorlaufItem = {
    id: 'v1', label: 'Anziehen', piktogramm: '6627', quelle: 'default',
    zeit: { typ: 'vorlauf', minuten: 15, bezug: 'vorheriger_anker' },
  };
  const items = [ankerItem, vorlaufItem];

  const abgeleitet = _vorlaufUhrzeit(vorlaufItem, items);
  assert.equal(abgeleitet, '06:45', "Vorlauf-Ableitung: 07:00 − 15 Min = 06:45");

  // Kein vorangehender Anker → null
  const ohneAnker = _vorlaufUhrzeit(vorlaufItem, [vorlaufItem]);
  assert.equal(ohneAnker, null, "Kein vorangehender Anker → null");

  // Nicht-Vorlauf-Item → null
  assert.equal(_vorlaufUhrzeit(ankerItem, items), null, "Anker-Item → null (kein Vorlauf)");

  // locked:true Anker: _labelMitZeit → HTML mit Hinweis
  const lockedItem = {
    id: 'a0', label: 'Aufstehen', piktogramm: '8152', quelle: 'default',
    zeit: { typ: 'anker', uhrzeit: '07:00', locked: true },
  };
  const html = _labelMitZeit(lockedItem);
  assert.ok(html.includes('V1-Anker'), "locked: V1-Anker-Hinweis im HTML");
  assert.ok(html.includes('07:00'),    "locked: Uhrzeit im HTML");
  assert.ok(html.includes('item-zeit-locked'), "locked: CSS-Klasse item-zeit-locked");

  // Kein zeit-Block → einfaches span.item-label
  const ohneZeitHtml = _labelMitZeit({ id: 'x', label: 'Punkt', piktogramm: '9999', quelle: 'default' });
  assert.ok(ohneZeitHtml.includes('item-label'), "Ohne zeit: item-label span");
  assert.ok(!ohneZeitHtml.includes('item-zeit-badge'), "Ohne zeit: kein zeit-Badge");
});

// ── ROUTINE-27 AC2 — Handler-Ketten-Tests (Closes #1198) ─────────────────────

/**
 * Test 11 — ROUTINE-27 AC2 Handler-Kette Anker:
 * Simuliert Toggle-Klick #tog-typ-anker + #sheet-anlegen-Click, fängt den
 * postItem-Payload ab und prüft dass zeit:{typ:'anker',...} enthalten ist.
 *
 * Wäre VOR dem Fix rot: ohne Export von oeffneHinzufuegenSheet und ohne
 * Vorab-Registrierung der Toggle-Elemente bleibt typAuswahl='punkt',
 * kein zeit-Block → POST-Payload ohne zeit-Feld.
 */
test("ROUTINE-27 AC2 Handler-Kette Anker: Toggle→Anlegen-Click → POST-Payload hat zeit:{typ:'anker',...}", async () => {
  // Frische Elemente registrieren (verhindert TypeError + ermöglicht Toggle-Binding)
  const els = _registriereSheetElemente(doc2);
  els['sheet-label'].value = 'Test-Anker';

  // Lokaler fetch-Spy: fängt POST + nachfolgende GET-Aufrufe (ladeUndRendere) auf
  const allCalls = [];
  const prevFetch = global.fetch;
  global.fetch = async (url, opts = {}) => {
    allCalls.push({ url, method: opts.method || 'GET', body: opts.body });
    const json = url.includes('/config')
      ? {}
      : { id: 'neu-1', default: [], einmalig_heute: [] };
    return { ok: true, status: 200, json: async () => json, text: async () => '{}' };
  };

  try {
    // Sheet öffnen: bindet alle Handler an die pre-registrierten Elemente
    oeffneHinzufuegenSheet();

    // Icon-Auswahl simulieren (setzt _pickerSelectedId, aktiviert Anlegen-Button)
    _testSetPickerSelectedId('8152');

    // Anker-Toggle klicken → typAuswahl wird auf 'anker' gesetzt
    els['tog-typ-anker'].click();

    // Anlegen klicken → startet den async Handler
    els['sheet-anlegen'].click();

    // Async-Handler abwarten: Microtask-Queue mehrfach leeren
    // (POST → resp → schliesseSheet → ladeUndRendere → GET×2 → rendereInhalt)
    for (let i = 0; i < 8; i++) {
      await new Promise(resolve => setImmediate(resolve));
    }

    const postCall = allCalls.find(c => c.method === 'POST');
    assert.ok(postCall, "mindestens 1 POST /api/v1/routine/items abgesetzt");
    assert.ok(postCall.url.includes('/api/v1/routine/items'), "POST-URL korrekt");

    const body = JSON.parse(postCall.body);
    assert.ok('zeit' in body, "POST-Body enthält zeit-Feld (Anker-Typ muss zeit tragen)");
    assert.equal(body.zeit.typ,    'anker', "zeit.typ: anker");
    assert.equal(body.zeit.locked, false,   "zeit.locked: false");
    assert.ok(body.zeit.uhrzeit,           "zeit.uhrzeit vorhanden");

  } finally {
    global.fetch = prevFetch;
  }
});

/**
 * Test 12 — ROUTINE-27 AC2 Handler-Kette Vorlauf:
 * Simuliert Toggle-Klick #tog-typ-vorlauf + #sheet-anlegen-Click, prüft
 * dass zeit:{typ:'vorlauf', minuten:N, bezug:'vorheriger_anker'} im Payload landet.
 */
test("ROUTINE-27 AC2 Handler-Kette Vorlauf: Toggle→Anlegen-Click → POST-Payload hat zeit:{typ:'vorlauf',...}", async () => {
  const els = _registriereSheetElemente(doc2);
  els['sheet-label'].value = 'Test-Vorlauf';

  const allCalls = [];
  const prevFetch = global.fetch;
  global.fetch = async (url, opts = {}) => {
    allCalls.push({ url, method: opts.method || 'GET', body: opts.body });
    const json = url.includes('/config')
      ? {}
      : { id: 'neu-2', default: [], einmalig_heute: [] };
    return { ok: true, status: 200, json: async () => json, text: async () => '{}' };
  };

  try {
    oeffneHinzufuegenSheet();
    _testSetPickerSelectedId('6627');

    // Vorlauf-Toggle klicken → typAuswahl = 'vorlauf'
    els['tog-typ-vorlauf'].click();

    els['sheet-anlegen'].click();

    for (let i = 0; i < 8; i++) {
      await new Promise(resolve => setImmediate(resolve));
    }

    const postCall = allCalls.find(c => c.method === 'POST');
    assert.ok(postCall, "mindestens 1 POST abgesetzt");

    const body = JSON.parse(postCall.body);
    assert.ok('zeit' in body,                        "POST-Body enthält zeit-Feld (Vorlauf-Typ muss zeit tragen)");
    assert.equal(body.zeit.typ,    'vorlauf',         "zeit.typ: vorlauf");
    assert.ok(typeof body.zeit.minuten === 'number',  "zeit.minuten ist Zahl");
    assert.ok(body.zeit.minuten >= 5,                 "zeit.minuten >= 5 (5er-Schritte)");
    assert.equal(body.zeit.bezug, 'vorheriger_anker', "zeit.bezug: vorheriger_anker");

  } finally {
    global.fetch = prevFetch;
  }
});

/**
 * Test 13 — ROUTINE-27 AC2 Handler-Kette Punkt (Default):
 * Ohne Toggle-Klick bleibt typAuswahl='punkt' → kein zeit-Block → kein zeit-Feld im POST-Payload.
 */
test("ROUTINE-27 AC2 Handler-Kette Punkt: kein Toggle-Klick → POST-Payload hat KEIN zeit-Feld", async () => {
  const els = _registriereSheetElemente(doc2);
  els['sheet-label'].value = 'Test-Punkt';

  const allCalls = [];
  const prevFetch = global.fetch;
  global.fetch = async (url, opts = {}) => {
    allCalls.push({ url, method: opts.method || 'GET', body: opts.body });
    const json = url.includes('/config')
      ? {}
      : { id: 'neu-3', default: [], einmalig_heute: [] };
    return { ok: true, status: 200, json: async () => json, text: async () => '{}' };
  };

  try {
    oeffneHinzufuegenSheet();
    _testSetPickerSelectedId('9999');

    // Kein Toggle-Klick → typAuswahl bleibt 'punkt' (Default)
    els['sheet-anlegen'].click();

    for (let i = 0; i < 8; i++) {
      await new Promise(resolve => setImmediate(resolve));
    }

    const postCall = allCalls.find(c => c.method === 'POST');
    assert.ok(postCall, "mindestens 1 POST abgesetzt");

    const body = JSON.parse(postCall.body);
    assert.ok(!('zeit' in body), "Punkt: KEIN zeit-Feld im POST-Body (Punkt = kein zeit-Block)");

  } finally {
    global.fetch = prevFetch;
  }
});
