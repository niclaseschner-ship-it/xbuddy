/**
 * plan_einstellungen_dom.test.js — PLAN-1957 Verhaltens-Proben (#1957).
 *
 * 7 Tests via node --test, manuelle DOM-Attrappe (_dom_stub.js), kein jsdom, kein npm.
 *
 * Bug (#1957): Jede Aenderung in den Plan-Einstellungen (Icon, Kind, Default-Person,
 * Reorder, Loeschen, Neuanlegen) rendert die ganze Slot-Liste neu (rendereSlotListe).
 * Vor dem Fix schloss dieses Neu-Rendern JEDES geoeffnete Akkordeon ("Reiter") wieder,
 * weil kein Zustand darueber gefuehrt wurde, welcher Slot gerade offen war — der
 * Nutzer landete nach jeder Aenderung wieder am Anfang der Liste und musste den
 * Reiter neu waehlen.
 *
 * Fix: _offenerSlotSchluessel haelt den aktiven Reiter modul-weit, rendereSlotListe()
 * gibt ihm das "open"-Attribut zurueck, und der Reiter steht zusaetzlich im
 * URL-Hash (#slot-<schluessel>), damit Neuladen/"Zurueck" ebenfalls dort landen.
 *
 * Exportierte Symbole aus plan-einstellungen.js (siehe module.exports am Dateiende):
 *   slotSchluesselAusHash, hashFuerSlot — reine Hash-Helfer
 *   rendereSlotListe, setzeSlotIcon, setzeDefault, loescheSlot, legeSlotAn
 *   _testSetEditSlots, _testSetOffenerSlotSchluessel, _testGetOffenerSlotSchluessel
 *
 * DOM-Stub-Besonderheit: plan-einstellungen.js' bindeDelegation() dupliziert den
 * Container per cloneNode(true) + replaceChild, um alte Click-Listener loszuwerden
 * (kein anderes *_dom.test.js-Ziel braucht das) — _dom_stub.js wurde dafuer additiv
 * um cloneNode/replaceChild ergaenzt, ohne bestehendes Verhalten zu aendern.
 *
 * Weil bindeDelegation() den Container-Knoten bei jedem Aufruf gegen einen Klon
 * austauscht, muss jede Assertion den AKTUELL registrierten Knoten frisch per
 * document.getElementById() holen — eine zuvor gehaltene Referenz zeigt sonst auf
 * einen laengst ersetzten, veralteten Knoten.
 */

"use strict";

const { test }   = require("node:test");
const assert     = require("node:assert/strict");
const { makeDom, makeRoutedFetchSpy } = require("./_dom_stub.js");

// ── Modul laden ───────────────────────────────────────────────────────────────
// plan-einstellungen.js hat wie essen-einkauf.js eine selbstausfuehrende
// main()-IIFE, die beim require() sofort startet (Boot-Fetches laufen im
// Hintergrund weiter). Jeder Test setzt seinen eigenen Zustand ueber die
// exportierten _test*-Hilfsfunktionen, um vom Boot-Timing unabhaengig zu sein.

const doc = makeDom();

const body = doc.createElement("div");
const slotsContainer = doc.createElement("div");
slotsContainer.id = "slots-container";
body.appendChild(slotsContainer);
doc._registerEl("slots-container", slotsContainer);

const fetchSpy = makeRoutedFetchSpy([
  { match: /\/api\/v1\/familie\/personen/, json: { personen: [
    { id: "p1", name: "Mama", ring: "rot" },
    { id: "p2", name: "Papa", ring: "blau" },
  ] } },
  { match: /\/api\/v1\/plan\/slot-modell/, json: { slots: [] } },
  { match: /\/api\/v1\/plan\/defaults/, json: { defaults: {} } },
]);

global.document     = doc;
global.fetch        = fetchSpy;
global.setTimeout   = () => {};
global.clearTimeout = () => {};
global.confirm      = () => true;

global.window = {
  location: { hash: "", pathname: "/seiten/plan/einstellungen/", search: "" },
  history: {
    replaceState: (_state, _title, url) => {
      const hashIdx = url.indexOf("#");
      global.window.location.hash = hashIdx >= 0 ? url.slice(hashIdx) : "";
    },
  },
  scrollY:  0,
  scrollTo: () => {},
};

const plan = require("../static/plan-einstellungen.js");
const {
  slotSchluesselAusHash,
  hashFuerSlot,
  rendereSlotListe,
  setzeSlotIcon,
  setzeDefault,
  loescheSlot,
  legeSlotAn,
  _testSetEditSlots,
  _testSetOffenerSlotSchluessel,
  _testGetOffenerSlotSchluessel,
} = plan;

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────

function slot(schluessel, extra) {
  return Object.assign({
    schluessel,
    label:   null,
    art:     "verantwortlich",
    icon:    "1234",
    kind_id: null,
    reihenfolge: 0,
  }, extra || {});
}

/** Liest die aktuell registrierte Container-innerHTML — NIE die urspruengliche
 *  slotsContainer-Referenz nutzen, die wird von bindeDelegation() weggeklont. */
function containerHtml() {
  return doc.getElementById("slots-container").innerHTML;
}

function istSlotOffenImMarkup(html, schluessel) {
  const re = new RegExp('id="slot-' + schluessel + '"[^>]*\\bopen\\b');
  return re.test(html);
}

// ── Tests: reine Hash-Helfer ───────────────────────────────────────────────────

test("PLAN-1957: slotSchluesselAusHash liest den Slot-Schluessel aus dem Hash", () => {
  assert.equal(slotSchluesselAusHash("#slot-bring"), "bring");
  assert.equal(slotSchluesselAusHash("#slot-bett-emil"), "bett-emil");
  assert.equal(slotSchluesselAusHash(""), null);
  assert.equal(slotSchluesselAusHash("#andere-seite"), null);
  assert.equal(slotSchluesselAusHash(null), null);
});

test("PLAN-1957: hashFuerSlot baut den Hash-String fuer einen Slot", () => {
  assert.equal(hashFuerSlot("bring"), "#slot-bring");
  assert.equal(hashFuerSlot(null), "");
  assert.equal(hashFuerSlot(""), "");
});

// ── Tests: rendereSlotListe haelt den aktiven Reiter offen ─────────────────────

test("PLAN-1957: rendereSlotListe gibt nur dem aktiven Reiter das open-Attribut", () => {
  _testSetEditSlots([slot("bring"), slot("kochen")]);
  _testSetOffenerSlotSchluessel("kochen");

  rendereSlotListe();

  const html = containerHtml();
  assert.ok(istSlotOffenImMarkup(html, "kochen"), "kochen-Slot ist offen gerendert");
  assert.ok(!istSlotOffenImMarkup(html, "bring"), "bring-Slot bleibt zu");
});

// ── Regressions-Kern: eine Aenderung darf den aktiven Reiter NICHT schliessen ──

test("#1957: Icon-Aenderung an einem anderen Slot schliesst den aktiven Reiter nicht", () => {
  _testSetEditSlots([slot("bring"), slot("kochen")]);
  _testSetOffenerSlotSchluessel("kochen");
  rendereSlotListe();
  assert.ok(istSlotOffenImMarkup(containerHtml(), "kochen"), "Ausgangszustand: kochen offen");

  setzeSlotIcon("bring", "999"); // loest vollen Re-Render + bindeDelegation aus

  assert.ok(
    istSlotOffenImMarkup(containerHtml(), "kochen"),
    "kochen bleibt nach Icon-Aenderung an bring offen (vor dem Fix: alle Akkordeons schlossen)"
  );
});

test("#1957: Default-Person setzen laesst den aktiven Reiter offen", () => {
  _testSetEditSlots([slot("bring"), slot("kochen")]);
  _testSetOffenerSlotSchluessel("bring");
  rendereSlotListe();

  setzeDefault("bring", 0, "p1");

  assert.ok(
    istSlotOffenImMarkup(containerHtml(), "bring"),
    "bring bleibt nach Default-Personen-Wahl offen"
  );
});

test("#1957: neuer Slot wird sofort zum aktiven Reiter (offen + im URL-Hash)", () => {
  _testSetEditSlots([slot("bring")]);
  _testSetOffenerSlotSchluessel(null);
  global.window.location.hash = "";

  legeSlotAn("Abholen", "verantwortlich", "555");

  assert.equal(_testGetOffenerSlotSchluessel(), "abholen");
  assert.ok(istSlotOffenImMarkup(containerHtml(), "abholen"), "neuer Slot ist offen gerendert");
  assert.equal(global.window.location.hash, "#slot-abholen", "URL-Hash zeigt auf den neuen Slot");
});

test("#1957: Loeschen des offenen Slots raeumt Reiter-Zustand + Hash auf", () => {
  _testSetEditSlots([slot("bring"), slot("kochen")]);
  _testSetOffenerSlotSchluessel("bring");
  global.window.location.hash = "#slot-bring";

  loescheSlot("bring");

  assert.equal(_testGetOffenerSlotSchluessel(), null, "Reiter-Zustand geleert");
  assert.equal(global.window.location.hash, "", "Hash geleert");
  assert.ok(!containerHtml().includes('id="slot-bring"'), "bring ist aus der Liste verschwunden");
});
