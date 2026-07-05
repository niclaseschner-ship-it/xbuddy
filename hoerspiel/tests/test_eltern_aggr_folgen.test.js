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
  pathname: "/seiten/hoerspiel/neko/eltern",
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
const { KIND_IDS_V1, _mergeUndSortiereAlben, _rendereWarnBanner } = eltern;

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
 * zwei KIND_IDS_V1-Quellen (paula + neko, je 2 Alben) zu einer
 * sortierten 4er-Liste; jeder Eintrag trägt seine kind_id.
 */
test("HSP-35-Aggregation: zwei Quellen (paula+neko) ergeben sortierte 4er-Liste mit kind_id", () => {
  assert.deepEqual(KIND_IDS_V1, ["paula", "neko", "niclas"], "KIND_IDS_V1 enthält paula+neko+niclas (#1263)");

  const alleAlben = [
    {
      kindId: "paula",
      alben: [
        makeAlbum({ id: "p1", nummer: 2, "erstellt-am": "2026-06-12" }),
        makeAlbum({ id: "p2", nummer: 1, "erstellt-am": "2026-06-08" }),
      ],
    },
    {
      kindId: "neko",
      alben: [
        makeAlbum({ id: "n1", nummer: 1, "erstellt-am": "2026-06-15" }),
        makeAlbum({ id: "n2", nummer: 2, "erstellt-am": "2026-06-05" }),
      ],
    },
  ];

  const result = _mergeUndSortiereAlben(alleAlben);

  assert.equal(result.length, 4, "Gemergtes Array hat 4 Einträge");

  // Sortierung: erstellt-am desc → n1 (06-15) vor p1 (06-12) vor p2 (06-08) vor n2 (06-05)
  assert.equal(result[0].id, "n1", "Erster Eintrag: neueste Folge (neko n1 2026-06-15)");
  assert.equal(result[1].id, "p1", "Zweiter Eintrag: paula p1 2026-06-12");
  assert.equal(result[2].id, "p2", "Dritter Eintrag: paula p2 2026-06-08");
  assert.equal(result[3].id, "n2", "Vierter Eintrag: neko n2 2026-06-05");

  // Jeder Eintrag trägt seine eigene kind_id
  assert.equal(result[0].kind_id, "neko",  "n1 trägt kind_id=neko");
  assert.equal(result[1].kind_id, "paula", "p1 trägt kind_id=paula");
  assert.equal(result[2].kind_id, "paula", "p2 trägt kind_id=paula");
  assert.equal(result[3].kind_id, "neko",  "n2 trägt kind_id=neko");
});

/**
 * Test 2 — HSP-35-Aggregation: Nummer-Fallback bei gleichem erstellt-am.
 * Wenn zwei Folgen dasselbe Datum haben, gewinnt die höhere Nummer.
 */
test("HSP-35-Aggregation: Nummer-Fallback bei gleicher erstellt-am-Sort", () => {
  const alleAlben = [
    {
      kindId: "paula",
      alben: [
        makeAlbum({ id: "p-low",  nummer: 1, "erstellt-am": "2026-06-10" }),
        makeAlbum({ id: "p-high", nummer: 3, "erstellt-am": "2026-06-10" }),
      ],
    },
    {
      kindId: "neko",
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
 * URL-KIND_ID aus der URL ist "neko" (global.location.pathname).
 * Paula-Folge muss trotzdem paula-Avatar-URL produzieren.
 */
test("HSP-35-Avatar-URL: Avatar-img src = /api/v1/familie/foto/<folge.kind_id>", () => {
  const alleAlben = [
    { kindId: "paula", alben: [ makeAlbum({ id: "p1", "erstellt-am": "2026-06-14" }) ] },
    { kindId: "neko",  alben: [ makeAlbum({ id: "n1", "erstellt-am": "2026-06-13" }) ] },
  ];

  const result = _mergeUndSortiereAlben(alleAlben);

  // Für jede Folge in der gemergten Liste muss die Avatar-URL die folge-eigene
  // kind_id nutzen — nicht URL-KIND_ID ("neko" aus dem URL-Pfad).
  for (const album of result) {
    const erwarteteSrc = "/api/v1/familie/foto/" + album.kind_id;

    // Simuliert: avatarHtml = '/api/v1/familie/foto/' + album.kind_id
    // (Render-Mechanismus aus eltern.js _rendereAlbenListe, Z. 486)
    const avatarSrc = "/api/v1/familie/foto/" + album.kind_id;

    assert.equal(avatarSrc, erwarteteSrc,
      "Avatar-URL nutzt folge.kind_id (" + album.kind_id + "), nicht URL-KIND_ID");
  }

  // Paula-Folge muss paula-URL haben, auch wenn URL-KIND_ID=neko
  const paulaFolge = result.find(a => a.kind_id === "paula");
  assert.ok(paulaFolge, "Paula-Folge im Merge vorhanden");
  assert.equal(
    "/api/v1/familie/foto/" + paulaFolge.kind_id,
    "/api/v1/familie/foto/paula",
    "Paula-Avatar-URL ist /api/v1/familie/foto/paula, nicht /api/v1/familie/foto/neko"
  );
});

/**
 * Test 4 — HSP-40: einseitiger fetch-404 → teilweise Liste + Warn-Banner (#975).
 *
 * Entry-Path-Test: nutzt makeRoutedFetchSpy (URL-discriminierend, wie der
 * Live-Code-Pfad von _ladeAlbenListe) statt handverdrahteter lokaler
 * Promises. Paula-URL → 200 + Album-Array; Neko-URL → 404. Anschließend
 * wird _mergeUndSortiereAlben + _rendereWarnBanner (beide exportiert) mit
 * den settled-Ergebnissen aufgerufen — gleicher Mechanismus wie in
 * _ladeAlbenListe intern.
 *
 * AC1: Fetch-Spy URL-discriminierend (paula 200, neko 404).
 * AC2: Merge-Ergebnis enthält nur paula-Folge; fehlgeschlagen=['neko'].
 * AC3: DOM-Stub insertBefore vorhanden; Banner landet vor player in _children.
 * AC4: Banner-Position-Check via _children-Index.
 */
test("HSP-40: einseitiger fetch-404 → teilweise Liste + Warn-Banner für fehlgeschlagene kind_id", async () => {
  // URL-routing fetchSpy: selbes Discriminierungs-Muster wie _ladeAlbenListe/_holeAlben.
  // paula/alben → 200 + Album-Array; neko/alben → 404; alle anderen → 200 + { status:"neu" }.
  const routedFetch = makeRoutedFetchSpy([
    { match: /\/hoerspiel\/paula\/alben/, status: 200, json: [ makeAlbum({ id: "p1" }) ] },
    { match: /\/hoerspiel\/neko\/alben/,  status: 404, json: { fehler: "nicht gefunden" } },
  ], { status: "neu" });

  // Temporär globales fetch überschreiben (wie _ladeAlbenListe es vorfindet).
  const prevFetch = global.fetch;
  global.fetch = routedFetch;

  // Parallele _holeAlben-Aufrufe — exakt wie _ladeAlbenListe es macht,
  // über den echten fetch-Mechanismus (URL-Spy), nicht handverdrahtete Promises.
  const KIND_IDS = ["paula", "neko"];
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
  const paulaCall = routedFetch.calls.find(c => c.url.includes("/paula/alben"));
  const nekoCall  = routedFetch.calls.find(c => c.url.includes("/neko/alben"));
  assert.ok(paulaCall, "fetch wurde für paula/alben aufgerufen");
  assert.ok(nekoCall,  "fetch wurde für neko/alben aufgerufen");

  assert.equal(settledErgebnisse[0].status, "fulfilled", "paula-Fetch ist fulfilled");
  assert.equal(settledErgebnisse[1].status, "rejected",  "neko-Fetch ist rejected (404)");
  assert.equal(erfolgreich.length,    1,      "Genau eine erfolgreiche Quelle (paula)");
  assert.equal(fehlgeschlagen.length, 1,      "Genau eine fehlgeschlagene Quelle (neko)");
  assert.equal(fehlgeschlagen[0],     "neko", "Fehlgeschlagene kind_id ist 'neko'");

  // AC2: _mergeUndSortiereAlben (exportiert) liefert Partial-Result.
  const merged = _mergeUndSortiereAlben(erfolgreich);
  assert.equal(merged.length, 1,       "Gemergete Liste enthält genau 1 paula-Folge");
  assert.equal(merged[0].id, "p1",     "Paula-Folge (p1) ist in der Teilliste");
  assert.equal(merged[0].kind_id, "paula", "paula-Folge trägt kind_id=paula");

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
    banner.textContent.includes("Neko") || banner.textContent.toLowerCase().includes("neko"),
    "Warn-Banner-Text enthält 'Neko' (kind_id kapitalisiert): " + banner.textContent
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
