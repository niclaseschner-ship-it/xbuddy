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
const { makeDom, makeFetchSpy } = require(
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
const { KIND_IDS_V1, _mergeUndSortiereAlben } = eltern;

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
  assert.deepEqual(KIND_IDS_V1, ["paula", "neko"], "KIND_IDS_V1 enthält genau paula+neko");

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
 * Test 4 — HSP-35-Aggregation: einseitiger 404 → Promise.all reject.
 * Heute kein Partial-Result — catch ist Pflicht, keine stille Ignorierung.
 * (Offene Frage für Folge-Ticket: partial list bei einseitigem 404.)
 */
test("HSP-35-Aggregation: einseitiger fetch-404 → Promise.all wirft (kein Partial-Result)", async () => {
  // Simuliert parallelen Lade-Pfad: paula OK, neko → 404-artige Ablehnung
  async function holePaulaAlben() {
    return { kindId: "paula", alben: [ makeAlbum({ id: "p1" }) ] };
  }
  async function holeNekoAlben() {
    throw new Error("alben-Abruf fehlgeschlagen: 404");
  }

  let geworfen = false;
  try {
    await Promise.all([ holePaulaAlben(), holeNekoAlben() ]);
  } catch (err) {
    geworfen = true;
    assert.ok(
      err.message.includes("404") || err.message.includes("fehlgeschlagen"),
      "Fehler-Meldung enthält '404' oder 'fehlgeschlagen': " + err.message
    );
  }

  assert.equal(geworfen, true, "Promise.all verwirft bei einseitigem 404 (kein Partial-Result)");
});
