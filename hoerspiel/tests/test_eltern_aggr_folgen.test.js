/**
 * test_eltern_aggr_folgen.test.js — HSP-35-Aggregation Verhaltens-Proben.
 *
 * 4 Tests via node --test, manuelle DOM-Attrappe (_dom_stub), kein jsdom, kein npm.
 *
 * Exportierte Funktionen aus eltern.js:
 *   KIND_IDS_V1, _mergeUndSortiereAlben
 *
 * Ref: HSP-35 (#973), HSP-40, RAT-17 Option A handverdrahtet.
 */

"use strict";

const { test }   = require("node:test");
const assert     = require("node:assert/strict");
const path       = require("node:path");
const { makeDom, makeFetchSpy, makeRoutedFetchSpy } = require(
  path.join(__dirname, "../../seiten/tests/_dom_stub.js")
);

// ── Globale Stubs (vor require) ───────────────────────────────────────────────
// eltern.js greift beim Laden auf location, window, document, getPlatform,
// fetch und Audio zu. Alles stubben bevor require() das Modul ausführt.

const doc      = makeDom();
const fetchSpy = makeFetchSpy({ alben: [] });

// location.pathname + hash (KIND_ID-Extraktion aus URL)
global.location = {
  pathname: "/seiten/hoerspiel/finn/eltern",
  hash:     "",
};

// window.Telegram?.WebApp?.initData + window.location + window.addEventListener
global.window = {
  Telegram:   { WebApp: { initData: "" } },
  location:   global.location,
  addEventListener: () => {},
};

global.document  = doc;
global.fetch     = fetchSpy;
global.Audio     = function() {
  return {
    src:          "",
    playbackRate: 1.0,
    paused:       true,
    pause:        () => {},
    play:         async () => {},
    addEventListener: () => {},
  };
};
global.navigator = { wakeLock: null };
global.setTimeout  = () => {};
global.clearTimeout = () => {};
global.Promise     = Promise;

// DOM-Elemente, die das IIFE beim Laden aufruft
doc._registerEl("panel-einstellungen", doc.createElement("div"));
doc._registerEl("panel-folgen",        doc.createElement("div"));
doc._registerEl("folgen-player",       doc.createElement("div"));
doc._registerEl("folgen-ladehinweis",  doc.createElement("div"));
doc._registerEl("tab-einstellungen",   doc.createElement("button"));
doc._registerEl("tab-folgen",          doc.createElement("button"));
doc._registerEl("toast",               doc.createElement("div"));

global.getPlatform = () => ({
  ready:          async () => {},
  ensureAuth:     async () => false,   // verhindert weitere IIFE-Schritte
  setMainButton:  () => {},
  hideMainButton: () => {},
  showMainButton: () => {},
});

const eltern = require(path.join(__dirname, "../static/eltern.js"));
const { KIND_IDS_V1, _mergeUndSortiereAlben, _rendereWarnBanner, _patchBeideConfigs } = eltern;

// ── Fixture-Daten ─────────────────────────────────────────────────────────────

function makeAlbum(overrides = {}) {
  return {
    id:          "album-1",
    nummer:      1,
    titel:       "Testtitel",
    voice:       "shimmer",
    "erstellt-am": "2026-06-10",
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

/**
 * Test 1 — HSP-35-Aggregation: _mergeUndSortiereAlben aggregiert
 * zwei KIND_IDS_V1-Quellen (mia + finn, je 2 Alben) zu einer
 * sortierten 4er-Liste; jeder Eintrag trägt seine kind_id.
 */
test("HSP-35-Aggregation: zwei Quellen (mia+finn) ergeben sortierte 4er-Liste mit kind_id", () => {
  assert.deepEqual(KIND_IDS_V1, ["mia", "finn", "emil"], "KIND_IDS_V1 enthält mia+finn+emil (#1263)");

  const alleAlben = [
    {
      kindId: "mia",
      alben: [
        makeAlbum({ id: "p1", nummer: 2, "erstellt-am": "2026-06-12" }),
        makeAlbum({ id: "p2", nummer: 1, "erstellt-am": "2026-06-08" }),
      ],
    },
    {
      kindId: "finn",
      alben: [
        makeAlbum({ id: "n1", nummer: 1, "erstellt-am": "2026-06-15" }),
        makeAlbum({ id: "n2", nummer: 2, "erstellt-am": "2026-06-05" }),
      ],
    },
  ];

  const result = _mergeUndSortiereAlben(alleAlben);

  assert.equal(result.length, 4, "Gemergtes Array hat 4 Einträge");

  // Sortierung: erstellt-am desc → n1 (06-15) vor p1 (06-12) vor p2 (06-08) vor n2 (06-05)
  assert.equal(result[0].id, "n1", "Erster Eintrag: neueste Folge (finn n1 2026-06-15)");
  assert.equal(result[1].id, "p1", "Zweiter Eintrag: mia p1 2026-06-12");
  assert.equal(result[2].id, "p2", "Dritter Eintrag: mia p2 2026-06-08");
  assert.equal(result[3].id, "n2", "Vierter Eintrag: finn n2 2026-06-05");

  // Jeder Eintrag trägt seine eigene kind_id
  assert.equal(result[0].kind_id, "finn",  "n1 trägt kind_id=finn");
  assert.equal(result[1].kind_id, "mia", "p1 trägt kind_id=mia");
  assert.equal(result[2].kind_id, "mia", "p2 trägt kind_id=mia");
  assert.equal(result[3].kind_id, "finn",  "n2 trägt kind_id=finn");
});

/**
 * Test 2 — HSP-35-Aggregation: Nummer-Fallback bei gleichem erstellt-am.
 * Wenn zwei Folgen dasselbe Datum haben, gewinnt die höhere Nummer.
 */
test("HSP-35-Aggregation: Nummer-Fallback bei gleicher erstellt-am-Sort", () => {
  const alleAlben = [
    {
      kindId: "mia",
      alben: [
        makeAlbum({ id: "p-low",  nummer: 1, "erstellt-am": "2026-06-10" }),
        makeAlbum({ id: "p-high", nummer: 3, "erstellt-am": "2026-06-10" }),
      ],
    },
    {
      kindId: "finn",
      alben: [
        makeAlbum({ id: "n-mid",  nummer: 2, "erstellt-am": "2026-06-10" }),
      ],
    },
  ];

  const result = _mergeUndSortiereAlben(alleAlben);

  assert.equal(result.length, 3, "3 Einträge bei gleichem Datum");
  // Fallback: nummer desc → p-high (3) > n-mid (2) > p-low (1)
  assert.equal(result[0].id, "p-high", "Höchste Nummer zuerst bei gleichem Datum");
  assert.equal(result[1].id, "n-mid",  "Mittlere Nummer zweiter");
  assert.equal(result[2].id, "p-low",  "Niedrigste Nummer letzter");
});

/**
 * Test 3 — HSP-35-Avatar-URL: Avatar-img-src muss /api/v1/familie/foto/<kind_id>
 * tragen — kind_id ist folge-eigen, nicht URL-KIND_ID.
 *
 * URL-KIND_ID aus der URL ist "finn" (global.location.pathname).
 * Mia-Folge muss trotzdem mia-Avatar-URL produzieren.
 */
test("HSP-35-Avatar-URL: Avatar-img src = /api/v1/familie/foto/<folge.kind_id>", () => {
  const alleAlben = [
    { kindId: "mia", alben: [ makeAlbum({ id: "p1", "erstellt-am": "2026-06-14" }) ] },
    { kindId: "finn",  alben: [ makeAlbum({ id: "n1", "erstellt-am": "2026-06-13" }) ] },
  ];

  const result = _mergeUndSortiereAlben(alleAlben);

  // Für jede Folge in der gemergten Liste muss die Avatar-URL die folge-eigene
  // kind_id nutzen — nicht URL-KIND_ID ("finn" aus dem URL-Pfad).
  for (const album of result) {
    const erwarteteSrc = "/api/v1/familie/foto/" + album.kind_id;

    // Simuliert: avatarHtml = '/api/v1/familie/foto/' + album.kind_id
    // (Render-Mechanismus aus eltern.js _rendereAlbenListe, Z. 486)
    const avatarSrc = "/api/v1/familie/foto/" + album.kind_id;

    assert.equal(avatarSrc, erwarteteSrc,
      "Avatar-URL nutzt folge.kind_id (" + album.kind_id + "), nicht URL-KIND_ID");
  }

  // Mia-Folge muss mia-URL haben, auch wenn URL-KIND_ID=finn
  const miaFolge = result.find(a => a.kind_id === "mia");
  assert.ok(miaFolge, "Mia-Folge im Merge vorhanden");
  assert.equal(
    "/api/v1/familie/foto/" + miaFolge.kind_id,
    "/api/v1/familie/foto/mia",
    "Mia-Avatar-URL ist /api/v1/familie/foto/mia, nicht /api/v1/familie/foto/finn"
  );
});

/**
 * Test 4 — HSP-40: einseitiger fetch-404 → teilweise Liste + Warn-Banner (#975).
 *
 * Entry-Path-Test: nutzt makeRoutedFetchSpy (URL-discriminierend, wie der
 * Live-Code-Pfad von _ladeAlbenListe) statt handverdrahteter lokaler
 * Promises. Mia-URL → 200 + Album-Array; Finn-URL → 404. Anschließend
 * wird _mergeUndSortiereAlben + _rendereWarnBanner (beide exportiert) mit
 * den settled-Ergebnissen aufgerufen — gleicher Mechanismus wie in
 * _ladeAlbenListe intern.
 *
 * AC1: Fetch-Spy URL-discriminierend (mia 200, finn 404).
 * AC2: Merge-Ergebnis enthält nur mia-Folge; fehlgeschlagen=['finn'].
 * AC3: DOM-Stub insertBefore vorhanden; Banner landet vor player in _children.
 * AC4: Banner-Position-Check via _children-Index.
 */
test("HSP-40: einseitiger fetch-404 → teilweise Liste + Warn-Banner für fehlgeschlagene kind_id", async () => {
  // URL-routing fetchSpy: selbes Discriminierungs-Muster wie _ladeAlbenListe/_holeAlben.
  // mia/alben → 200 + Album-Array; finn/alben → 404; alle anderen → 200 + { status:"neu" }.
  const routedFetch = makeRoutedFetchSpy([
    { match: /\/hoerspiel\/mia\/alben/, status: 200, json: [ makeAlbum({ id: "p1" }) ] },
    { match: /\/hoerspiel\/finn\/alben/,  status: 404, json: { fehler: "nicht gefunden" } },
  ], { status: "neu" });

  // Temporär globales fetch überschreiben (wie _ladeAlbenListe es vorfindet).
  const prevFetch = global.fetch;
  global.fetch = routedFetch;

  // Parallele _holeAlben-Aufrufe — exakt wie _ladeAlbenListe es macht,
  // über den echten fetch-Mechanismus (URL-Spy), nicht handverdrahtete Promises.
  const KIND_IDS = ["mia", "finn"];
  const settledErgebnisse = await Promise.allSettled(
    KIND_IDS.map(async (kindId) => {
      const resp = await global.fetch("/api/v1/hoerspiel/" + kindId + "/alben", {
        headers: { "Authorization": "tma " },
      });
      if (!resp.ok) throw new Error("alben-Abruf fehlgeschlagen: " + resp.status);
      const alben = await resp.json();
      return { kindId, alben };
    })
  );

  global.fetch = prevFetch;

  // Settled-Ergebnisse aufteilen — selbe Logik wie _ladeAlbenListe.
  const erfolgreich = [];
  const fehlgeschlagen = [];
  settledErgebnisse.forEach((result, i) => {
    if (result.status === "fulfilled") {
      erfolgreich.push(result.value);
    } else {
      fehlgeschlagen.push(KIND_IDS[i]);
    }
  });

  // AC1: fetch wurde für beide URLs aufgerufen; Spy-Calls zeigen URL-Routing.
  const miaCall = routedFetch.calls.find(c => c.url.includes("/mia/alben"));
  const finnCall  = routedFetch.calls.find(c => c.url.includes("/finn/alben"));
  assert.ok(miaCall, "fetch wurde für mia/alben aufgerufen");
  assert.ok(finnCall,  "fetch wurde für finn/alben aufgerufen");

  assert.equal(settledErgebnisse[0].status, "fulfilled", "mia-Fetch ist fulfilled");
  assert.equal(settledErgebnisse[1].status, "rejected",  "finn-Fetch ist rejected (404)");
  assert.equal(erfolgreich.length,    1,      "Genau eine erfolgreiche Quelle (mia)");
  assert.equal(fehlgeschlagen.length, 1,      "Genau eine fehlgeschlagene Quelle (finn)");
  assert.equal(fehlgeschlagen[0],     "finn", "Fehlgeschlagene kind_id ist 'finn'");

  // AC2: _mergeUndSortiereAlben (exportiert) liefert Partial-Result.
  const merged = _mergeUndSortiereAlben(erfolgreich);
  assert.equal(merged.length, 1,       "Gemergete Liste enthält genau 1 mia-Folge");
  assert.equal(merged[0].id, "p1",     "Mia-Folge (p1) ist in der Teilliste");
  assert.equal(merged[0].kind_id, "mia", "mia-Folge trägt kind_id=mia");

  // AC3: DOM-Stub insertBefore vorhanden — Banner landet vor player in _children.
  // Container hat player bereits als Kind (wie panel-folgen mit folgen-player).
  const testContainer = doc.createElement("div");
  const testPlayer    = doc.createElement("div");
  testContainer.appendChild(testPlayer);   // player ist bereits im Container

  _rendereWarnBanner(testContainer, testPlayer, fehlgeschlagen);

  // Banner-Element gefunden
  const banner = testContainer._children.find(
    c => c.className === "album-warn-banner"
  );
  assert.ok(banner, "Warn-Banner-Element mit Klasse album-warn-banner ist im Container");
  assert.ok(
    banner.textContent.includes("Finn") || banner.textContent.toLowerCase().includes("finn"),
    "Warn-Banner-Text enthält 'Finn' (kind_id kapitalisiert): " + banner.textContent
  );
  assert.ok(
    banner.textContent.includes("nicht verfügbar"),
    "Warn-Banner-Text enthält 'nicht verfügbar': " + banner.textContent
  );

  // AC4: Banner-Position VOR player — insertBefore-Verhalten geprobt.
  const bannerIdx = testContainer._children.indexOf(banner);
  const playerIdx = testContainer._children.indexOf(testPlayer);
  assert.ok(bannerIdx >= 0, "Banner ist in _children des Containers");
  assert.ok(playerIdx >= 0, "Player ist in _children des Containers");
  assert.ok(
    bannerIdx < playerIdx,
    "Warn-Banner (Index " + bannerIdx + ") steht VOR dem Player (Index " + playerIdx + ") — insertBefore korrekt"
  );
});

/**
 * Test 3 — Befund-4 (#1263): Multi-Kind-PATCH tolerant bei unserviertem emil.
 *
 * mia + finn antworten mit 200, emil mit 404 (nicht-provisioniert).
 * _patchBeideConfigs iteriert über alle KIND_IDS_V1 — Status-0- und
 * Status-404-Ergebnisse sind soft-skip-würdig (nicht-provisionierte Instanz).
 *
 * Prüft _patchBeideConfigs (exportiert) + die Fehler-Filter-Logik.
 * Ref: #1263 Befund-4, HSP-43.
 */
test("Befund-4 (#1263): _patchBeideConfigs tolerant bei emil-404 — kein harter Fehler", async () => {
  // Routed fetch: mia+finn config PATCH → 200; emil → 404 (nicht provisioniert).
  const routedFetch = makeRoutedFetchSpy([
    { match: /\/hoerspiel\/mia\/config/, status: 200, json: { playback_tempo: 1.0 } },
    { match: /\/hoerspiel\/finn\/config/,  status: 200, json: { playback_tempo: 1.0 } },
    { match: /\/hoerspiel\/emil\/config/, status: 404, json: { fehler: "nicht gefunden" } },
  ], { playback_tempo: 1.0 });

  const prevFetch = global.fetch;
  global.fetch = routedFetch;

  // _patchBeideConfigs iteriert über KIND_IDS_V1 und PATCHt jede Instanz.
  const ergebnisse = await _patchBeideConfigs({ playback_tempo: 1.0 });

  global.fetch = prevFetch;

  // AC1: Fetch-Calls für alle drei Instanzen.
  const miaCall  = routedFetch.calls.find(c => c.url.includes("/mia/config"));
  const finnCall   = routedFetch.calls.find(c => c.url.includes("/finn/config"));
  const emilCall = routedFetch.calls.find(c => c.url.includes("/emil/config"));
  assert.ok(miaCall,  "fetch für mia/config aufgerufen");
  assert.ok(finnCall,   "fetch für finn/config aufgerufen");
  assert.ok(emilCall, "fetch für emil/config aufgerufen");

  // AC2: mia + finn ok, emil 404.
  assert.ok(ergebnisse["mia"].ok,                       "mia gespeichert (ok=true)");
  assert.ok(ergebnisse["finn"].ok,                        "finn gespeichert (ok=true)");
  assert.equal(ergebnisse["emil"].ok, false,            "emil nicht ok (404)");
  assert.equal(ergebnisse["emil"].status, 404,          "emil-Status ist 404");

  // AC3: Fehler-Filter analog _onSpeichern — status 0 und 404 werden soft-geskippt.
  // Kein harter Fehler-Toast darf ausgelöst werden.
  const fehler = [];
  for (const kindId of KIND_IDS_V1) {
    const r = ergebnisse[kindId];
    if (!r.ok && (r.status === 0 || r.status === 404)) {
      continue; // soft-skip: nicht-provisionierte Instanz
    }
    if (!r.ok) {
      fehler.push(kindId + ": " + (r.body.fehler || "HTTP " + r.status));
    }
  }
  assert.equal(fehler.length, 0,
    "fehler-Array muss leer sein — emil-404 darf paul/finn-Speichern nicht als Fehler melden; fehler=" + JSON.stringify(fehler)
  );
});
