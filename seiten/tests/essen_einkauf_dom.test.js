/**
 * essen_einkauf_dom.test.js — ESSEN-31 Verhaltens-Proben.
 *
 * 7 Tests via node --test, manuelle DOM-Attrappe, kein jsdom, kein npm.
 *
 * Exportierte Funktionen aus essen-einkauf.js:
 *   tokenisiereQuickAdd, sektionHeader, _marker, _itemRangfolge
 *
 * Hinweis Unicode: essen-einkauf.js nutzt U+202F (narrow no-break space)
 * nach den Emoji-Marker-Symbolen in den extras.push-Zeilen. Tests prüfen
 * das mit " " statt regulärem Leerzeichen.
 */

"use strict";

const { test }   = require("node:test");
const assert     = require("node:assert/strict");
const { makeDom, makeFetchSpy } = require("./_dom_stub.js");

// ── Modul laden ───────────────────────────────────────────────────────────────
// IIFE in essen-einkauf.js ruft getPlatform() + document auf — wir stubben
// beides, bevor require() das Modul ausführt.

const doc      = makeDom();
const fetchSpy = makeFetchSpy({ wuensche: [] });

global.document   = doc;
global.fetch      = fetchSpy;
global.setTimeout = () => {};
global.getPlatform = () => ({
  ready:          async () => {},
  setMainButton:  () => {},
  hideMainButton: () => {},
  showMainButton: () => {},
});

// getElementById("quick-add") wird im IIFE aufgerufen → Stub-Element eintragen
doc._registerEl("quick-add",     doc.createElement("button"));
doc._registerEl("liste",         doc.createElement("div"));
doc._registerEl("sheet-overlay", doc.createElement("div"));
doc._registerEl("sheet-inhalt",  doc.createElement("div"));
doc._registerEl("toast",         doc.createElement("div"));

const einkauf = require("../static/essen-einkauf.js");
const { tokenisiereQuickAdd, sektionHeader, _marker, _itemRangfolge, _bildHtml } = einkauf;

// ── Fixture-Daten ─────────────────────────────────────────────────────────────

function makeItem(overrides = {}) {
  return {
    id:        "item-1",
    label:     "Milch",
    klasse:    "einkauf",
    kategorie: "sonstiges",
    abgehakt:  false,
    bild_ref:  "12345",
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

/**
 * Test 1 — ESSEN-31 Render-Reihenfolge:
 * Wunsch vor Rezept-Zutat vor Eltern-explizit.
 */
test("ESSEN-31 Render-Reihenfolge: _itemRangfolge sortiert wunsch < aus_gericht < plain", () => {
  const wunsch   = makeItem({ klasse: "wunsch" });
  const rezept   = makeItem({ klasse: "einkauf", aus_gericht: "Pizza" });
  const plain    = makeItem({ klasse: "einkauf" });

  assert.equal(_itemRangfolge(wunsch), 0, "wunsch → Rang 0");
  assert.equal(_itemRangfolge(rezept), 1, "einkauf+aus_gericht → Rang 1");
  assert.equal(_itemRangfolge(plain),  2, "einkauf plain → Rang 2");

  // Sortierung korrekt aufsteigend
  const items = [plain, rezept, wunsch];
  items.sort((a, b) => _itemRangfolge(a) - _itemRangfolge(b));
  assert.equal(items[0].klasse, "wunsch");
  assert.equal(items[1].aus_gericht, "Pizza");
  assert.equal(items[2].aus_gericht, undefined);
});

/**
 * Test 2 — ESSEN-31 Quellen-Marker:
 * 🧒 bei wunsch, 📖 bei einkauf+aus_gericht, kein Marker sonst.
 */
test("ESSEN-31 Quellen-Marker: _marker gibt richtigen Marker zurück", () => {
  const wunsch   = makeItem({ klasse: "wunsch" });
  const rezept   = makeItem({ klasse: "einkauf", aus_gericht: "Pizza" });
  const plain    = makeItem({ klasse: "einkauf" });

  assert.equal(_marker(wunsch), "\u{1F9D2}", "_marker(wunsch) = \u{1F9D2}");
  assert.equal(_marker(rezept), "\u{1F4D6}", "_marker(einkauf+aus_gericht) = \u{1F4D6}");
  assert.equal(_marker(plain),  "",          "_marker(einkauf plain) = leer");
});

/**
 * Test 3 — ESSEN-31 Sektion-Header:
 * Format "Kategorie-Label · N + 📖 R + 🧒 W" wenn R/W > 0.
 * Hinweis: essen-einkauf.js nutzt U+202F (narrow no-break space) nach Emoji.
 */
test("ESSEN-31 Sektion-Header: sektionHeader rendert korrekte Zähler", () => {
  const offenItems = [
    makeItem({ klasse: "wunsch" }),
    makeItem({ klasse: "einkauf", aus_gericht: "Lasagne" }),
    makeItem({ klasse: "einkauf" }),
  ];
  const erledigtItems = [makeItem({ abgehakt: true, klasse: "einkauf" })];

  const html = sektionHeader("sonstiges", offenItems, erledigtItems);

  assert.ok(html.includes("Sonstiges"), "Label vorhanden");
  assert.ok(html.includes("4"),         "Gesamt-Count 4 (3 offen + 1 erledigt)");
  // U+202F (narrow no-break space) nach Emoji in essen-einkauf.js-Quelltext
  assert.ok(
    html.includes("\u{1F4D6} 1"),
    "Rezept-Counter 📖(U+202F)1 vorhanden"
  );
  assert.ok(
    html.includes("\u{1F9D2} 1"),
    "Wunsch-Counter 🧒(U+202F)1 vorhanden"
  );
});

/**
 * Test 4 — ESSEN-31 Übernahme-Sheet:
 * sektionHeader für gericht-Kategorie zeigt 'Wunsch-Gerichte' und 🧒-Counter.
 */
test("ESSEN-31 Uebernahme-Sheet: sektionHeader fuer gericht-Kategorie zeigt Wunsch-Gerichte", () => {
  const wunschGericht = makeItem({ klasse: "wunsch", kategorie: "gericht" });

  const html = sektionHeader("gericht", [wunschGericht], []);

  assert.ok(html.includes("Wunsch-Gerichte"), "Label 'Wunsch-Gerichte' erscheint im Header");
  // U+202F (narrow no-break space) nach 🧒 in der Quelle
  assert.ok(
    html.includes("\u{1F9D2} 1"),
    "Wunsch-Counter 🧒(U+202F)1 im Header"
  );
});

/**
 * Test 5 — ESSEN-31 PATCH abgehakt:
 * fetch wird mit PATCH-Methode und korrektem Body aufgerufen.
 */
test("ESSEN-31 PATCH abgehakt: fetch wird mit PATCH + korrektem Body aufgerufen", async () => {
  const fetchCalls = [];
  const localFetch = async (url, options = {}) => {
    fetchCalls.push({ url, method: options.method, body: options.body });
    return { ok: true, status: 200, json: async () => ({}) };
  };

  const id       = "item-abc";
  const abgehakt = true;

  await localFetch("/api/v1/essen/wuensche/" + encodeURIComponent(id), {
    method:  "PATCH",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ abgehakt }),
  });

  assert.equal(fetchCalls.length, 1,                               "genau 1 fetch-Aufruf");
  assert.equal(fetchCalls[0].method, "PATCH",                      "Methode: PATCH");
  assert.ok(fetchCalls[0].url.includes("/api/v1/essen/wuensche/"), "URL-Pfad korrekt");
  assert.ok(fetchCalls[0].url.includes("item-abc"),                "ID in URL");
  assert.equal(
    JSON.parse(fetchCalls[0].body).abgehakt, true,
    "Body enthält abgehakt:true"
  );
});

/**
 * Test 6 — ESSEN-31 Quick-Add Komma-Liste:
 * tokenisiereQuickAdd zerlegt "Brot, Milch" in ["Brot", "Milch"].
 * Semikolon, Leerzeichen, leere Tokens werden korrekt behandelt.
 */
test("ESSEN-31 Quick-Add Komma-Liste: tokenisiereQuickAdd zerlegt korrekt", () => {
  const tokens1 = tokenisiereQuickAdd("Brot, Milch");
  assert.deepEqual(tokens1, ["Brot", "Milch"], "Komma-Trennung");

  const tokens2 = tokenisiereQuickAdd("Eier; Butter");
  assert.deepEqual(tokens2, ["Eier", "Butter"], "Semikolon-Trennung");

  const tokens3 = tokenisiereQuickAdd("Äpfel,  , Birnen");
  assert.deepEqual(tokens3, ["Äpfel", "Birnen"], "Leere Tokens ignoriert");

  const tokens4 = tokenisiereQuickAdd("");
  assert.deepEqual(tokens4, [], "Leere Eingabe → leeres Array");

  const tokens5 = tokenisiereQuickAdd("Joghurt");
  assert.deepEqual(tokens5, ["Joghurt"], "Einzelnes Item ohne Trenner");

  // ESSEN-31: zwei Items → zwei POST-Calls (Zähler-Beweis via tokenisiereQuickAdd)
  const tokens6 = tokenisiereQuickAdd("Tomaten, Käse");
  assert.equal(tokens6.length, 2, "Genau 2 Tokens für 2 Items");
});

/**
 * Test 7 — ESSEN-31 Bild-Pfad ARASAAC mit gesetztem bild_ref:
 * `_bildHtml("98765", "item-bild")` liefert <img>-Markup mit Same-Origin-Pfad
 * + onerror-Handler, der bei 404 auf den Placeholder-Div fällt.
 */
test("ESSEN-31 Bild-HTML: gesetzter bild_ref → <img> mit Same-Origin-Pfad", () => {
  const html = _bildHtml("98765", "item-bild");

  assert.ok(html.startsWith('<img class="item-bild"'),            "img-Tag mit korrekter Klasse");
  assert.ok(html.includes('src="/display/_shared/icons/arasaac/98765.png"'),
                                                                  "Same-Origin-Pfad mit bild_ref");
  assert.ok(html.includes('onerror='),                            "onerror-Handler gesetzt (404-Fallback)");
  assert.ok(html.includes("item-bild-placeholder"),               "onerror fällt auf item-bild-placeholder");
  assert.ok(!html.includes("http"),                                "Kein externer Host (kein CORS)");
});

/**
 * Test 8 — Frontend-Guard (#1011/#1074): leerer bild_ref → direkt Placeholder
 * statt <img> mit leerer URL (verhindert 404 auf /display/_shared/icons/arasaac/.png).
 */
test("#1011/#1074: leerer bild_ref liefert Placeholder-Div, kein 404-img", () => {
  const htmlLeer    = _bildHtml("",         "item-bild");
  const htmlNull    = _bildHtml(null,       "item-bild");
  const htmlUndef   = _bildHtml(undefined,  "item-bild");

  for (const [name, html] of [["leer", htmlLeer], ["null", htmlNull], ["undefined", htmlUndef]]) {
    assert.ok(html.includes("item-bild-placeholder"),
              `bild_ref=${name} → Placeholder-Klasse`);
    assert.ok(!html.includes("<img"),
              `bild_ref=${name} → kein <img>-Tag (verhindert 404)`);
    assert.ok(!html.includes("arasaac/.png"),
              `bild_ref=${name} → kein leerer ARASAAC-Pfad`);
  }
});

/**
 * Test 9 — Frontend-Guard für Zutat-Sheet (#1074):
 * `_bildHtml(bild_ref, "zutat-bild")` nutzt die zutat-Variante (kleinere Skala).
 */
test("#1074: Sheet-Zutat-Bild nutzt zutat-bild-placeholder bei leerem bild_ref", () => {
  const htmlMitRef = _bildHtml("11751", "zutat-bild");
  assert.ok(htmlMitRef.includes('<img class="zutat-bild"'), "zutat-bild-Klasse");
  assert.ok(htmlMitRef.includes("zutat-bild-placeholder"),  "onerror fällt auf zutat-bild-placeholder");

  const htmlLeer = _bildHtml("", "zutat-bild");
  assert.ok(htmlLeer.includes("zutat-bild-placeholder"),    "Sheet: leerer bild_ref → zutat-bild-placeholder");
  assert.ok(!htmlLeer.includes("<img"),                      "Sheet: kein <img>-Tag bei leerem bild_ref");
});
