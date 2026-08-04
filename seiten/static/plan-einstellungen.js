// plan-einstellungen.js — Plan-P2 Eltern-Einstellungs-PWA (PLAN-35).
//
// AC-PUBLIC: KEINE Telegram-Auth. Seite ist PUBLIC (PLAN-35 Auth: auth.md AUTH-6).
// Alle API-Calls gehen ohne Auth-Header ab — der Browser-Pfad liefert leere Auth.
//
// Spec-Anker: specs/buddies/plan.md PLAN-35 (PWA-Mantel), PLAN-36 (Defaults-API),
//             PLAN-37 (Slot-Modell-API). Icons: ICONS-1.
//
// APIs:
//   GET  /api/v1/plan/defaults    → { defaults: { slot_key: { "0": person_id|null, … } } }
//   PUT  /api/v1/plan/defaults    ← { defaults: … }
//   GET  /api/v1/plan/slot-modell → { slots: [ { schluessel, label, art, icon, kind } ] }
//   PUT  /api/v1/plan/slot-modell ← { slots: [ … ] }  (Feld: kind, nicht kind_id)
//   GET  /api/v1/familie/personen → { personen: [ { id, name, ring, … } ] }
//   GET  /api/v1/familie/foto/<id> → Foto-Datei (FAM-8)
//   GET  /api/v1/icons/suche?q=…&max=12 → { treffer: [ { id, … } ] }

'use strict';

// ── Zustand ───────────────────────────────────────────────────────────────────

/** @type {Array<{id:string, name:string, ring:string}>} */
let _personen = [];

/** @type {Array<{schluessel:string, label:string, art:string, icon:string, kind_id:string|null, reihenfolge:number}>} */
let _serverSlots = [];
/** @type {Array} bearbeiteter Klon */
let _editSlots = [];

/** Defaults vom Server: { slot_key: { "0": person_id|null, … } } */
let _serverDefaults = {};
/** bearbeiteter Klon */
let _editDefaults = {};

/** Welches Sheet ist gerade offen? */
let _aktuellesSheet = null;
/** Callback-Kontext fuer Sheet-Ergebnis */
let _sheetKontext = null;

/** Debounce-Timer fuer Icon-Suche */
let _debounceTimer = null;

/** Aktuell gewahlte Icon-ID im Picker */
let _pickerIconId = null;

const TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

// ── XSS-Schutz ───────────────────────────────────────────────────────────────

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── API-Calls (kein Auth-Header — PUBLIC, PLAN-35) ────────────────────────────

async function ladePersonen() {
  const resp = await fetch("/api/v1/familie/personen");
  if (!resp.ok) throw new Error("Personen laden fehlgeschlagen: " + resp.status);
  const data = await resp.json();
  return data.personen || data || [];
}

async function ladeSlotModell() {
  const resp = await fetch("/api/v1/plan/slot-modell");
  if (!resp.ok) throw new Error("Slot-Modell laden fehlgeschlagen: " + resp.status);
  const data = await resp.json();
  // API liefert "kind" (PLAN-37) — intern als kind_id verwenden (API-Rand-Mapping)
  return (data.slots || []).map((s) => ({ ...s, kind_id: s.kind ?? null }));
}

async function ladeDefaults() {
  const resp = await fetch("/api/v1/plan/defaults");
  if (!resp.ok) throw new Error("Defaults laden fehlgeschlagen: " + resp.status);
  const data = await resp.json();
  return data.defaults || {};
}

async function speichereSlotModell(slots) {
  const resp = await fetch("/api/v1/plan/slot-modell", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slots }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || "Slot-Modell speichern fehlgeschlagen: " + resp.status);
  }
  return resp.json();
}

async function speichereDefaults(defaults) {
  const resp = await fetch("/api/v1/plan/defaults", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ defaults }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || "Defaults speichern fehlgeschlagen: " + resp.status);
  }
  return resp.json();
}

/**
 * ROU-31: Icon-Suche ohne Auth-Header.
 * GET /api/v1/icons/suche?q=…&max=12
 */
async function sucheIcons(q) {
  const resp = await fetch(
    "/api/v1/icons/suche?q=" + encodeURIComponent(q) + "&max=12"
  );
  if (!resp.ok) return [];
  const data = await resp.json();
  return data.treffer || data.results || data || [];
}

// ── Label-Fallback (AC2) ──────────────────────────────────────────────────────

/**
 * Gibt einen sinnvollen Anzeige-Namen fuer einen Slot zurueck.
 * Falls slot.label gesetzt, wird es verwendet. Andernfalls Fallback aus schluessel + kind.
 * Fallback-Regeln:
 *   bring  → "Bringen"
 *   pick   → "Holen"
 *   cook   → "Kochen"
 *   bed1/bed2 → "Bett <Kind>"
 *   act1/act2 → "Termine <Kind>"
 *   default: schluessel (erster Buchstabe gross)
 */
function slotLabel(slot) {
  if (slot.label) return slot.label;
  const key = slot.schluessel || "";
  const kindPerson = slot.kind_id ? personById(slot.kind_id) : null;
  const kindName = kindPerson ? kindPerson.name : "";
  if (key === "bring") return "Bringen";
  if (key === "pick") return "Holen";
  if (key === "cook") return "Kochen";
  if (/^bed\d*$/.test(key)) return "Bett" + (kindName ? " " + kindName : "");
  if (/^act\d*$/.test(key)) return "Termine" + (kindName ? " " + kindName : "");
  return key ? (key[0].toUpperCase() + key.slice(1)) : key;
}

// ── Render-Helfer ─────────────────────────────────────────────────────────────

function personById(id) {
  return _personen.find((p) => p.id === id) || null;
}

function ringHtml(personId, cls) {
  const ringCls = cls || "ring";
  if (!personId) {
    return '<span class="' + esc(ringCls) + ' leer" aria-label="leer">×</span>';
  }
  const p = personById(personId);
  if (!p) {
    return '<span class="' + esc(ringCls) + ' leer" title="unbekannt">?</span>';
  }
  return (
    '<img class="' + esc(ringCls) + ' ring-' + esc(p.ring || "gray") + '"' +
    ' src="/api/v1/familie/foto/' + esc(p.id) + '"' +
    ' alt="' + esc(p.name) + '" title="' + esc(p.name) + '" loading="lazy">'
  );
}

function badgeHtml(art) {
  if (art === "verantwortlich") {
    return '<span class="badge verantwortlich">verantwortlich</span>';
  }
  return '<span class="badge kalender">kalender-read</span>';
}

function arasaacUrl(iconId) {
  return "/display/_shared/icons/arasaac/" + encodeURIComponent(String(iconId)) + ".png";
}

// ── Slot-Liste rendern ────────────────────────────────────────────────────────

function rendereSlotListe() {
  const container = document.getElementById("slots-container");
  if (!container) return;

  if (_editSlots.length === 0) {
    container.innerHTML = '<p class="lade-hinweis">Noch keine Slots definiert.</p>';
    return;
  }

  container.innerHTML = _editSlots.map((slot, idx) => {
    const istErste = idx === 0;
    const istLetzte = idx === _editSlots.length - 1;
    const hochDisabled = istErste ? " disabled" : "";
    const runterDisabled = istLetzte ? " disabled" : "";
    const anzeigeName = slotLabel(slot);

    return (
      '<details class="slot" id="slot-' + esc(slot.schluessel) + '">' +
        '<summary>' +
          '<div class="pfeile">' +
            '<button type="button" class="pfeil pfeil-hoch" data-slot-key="' + esc(slot.schluessel) + '"' +
              hochDisabled + ' aria-label="' + esc(anzeigeName) + ' nach oben">▲</button>' +
            '<button type="button" class="pfeil pfeil-runter" data-slot-key="' + esc(slot.schluessel) + '"' +
              runterDisabled + ' aria-label="' + esc(anzeigeName) + ' nach unten">▼</button>' +
          '</div>' +
          '<img class="slot-icon" src="' + esc(arasaacUrl(slot.icon)) + '" alt="" loading="lazy">' +
          '<span class="label">' + esc(anzeigeName) + '</span>' +
          '<span class="meta">' + badgeHtml(slot.art) + '<span class="chev">▶</span></span>' +
        '</summary>' +
        slotBodyHtml(slot) +
      '</details>'
    );
  }).join("");
}

function slotBodyHtml(slot) {
  if (slot.art === "verantwortlich") {
    return verantwortlichBodyHtml(slot);
  }
  return kalenderReadBodyHtml(slot);
}

function verantwortlichBodyHtml(slot) {
  const defaults = _editDefaults[slot.schluessel] || {};
  const anzeigeName = slotLabel(slot);

  const tagereihe = TAGE.map((tagName, i) => {
    const personId = defaults[String(i)] || null;
    return (
      '<div class="tag' + (i >= 5 ? ' we' : '') + '">' +
        '<span class="tagname">' + esc(tagName) + '</span>' +
        '<button type="button" class="person-tag-btn" ' +
          'data-slot-key="' + esc(slot.schluessel) + '" data-tag-idx="' + i + '" ' +
          'aria-label="Person fuer ' + esc(tagName) + ' in ' + esc(anzeigeName) + ' waehlen">' +
          ringHtml(personId, "ring sm") +
        '</button>' +
      '</div>'
    );
  }).join("");

  const kind = slot.kind_id ? personById(slot.kind_id) : null;

  return (
    '<div class="slot-body">' +
      '<div class="feldzeile">' +
        '<span class="feldname">Name</span>' +
        '<input type="text" class="slot-label-input" data-slot-key="' + esc(slot.schluessel) + '"' +
          ' value="' + esc(slot.label || "") + '"' +
          ' placeholder="' + esc(anzeigeName) + '"' +
          ' aria-label="Name des Slots">' +
      '</div>' +
      '<div class="feldzeile">' +
        '<span class="feldname">Piktogramm</span>' +
        '<img class="slot-icon" src="' + esc(arasaacUrl(slot.icon)) + '" alt="" loading="lazy">' +
        '<button type="button" class="btn sm btn-icon-aendern" data-slot-key="' + esc(slot.schluessel) + '">ändern</button>' +
      '</div>' +
      '<div class="feldzeile">' +
        '<span class="feldname">Kind im Rail</span>' +
        (kind
          ? ringHtml(kind.id, "ring") + '<span>' + esc(kind.name) + '</span>'
          : '<span style="color:#8a857c;font-size:14px">keins</span>') +
        '<button type="button" class="btn sm btn-kind-waehlen" data-slot-key="' + esc(slot.schluessel) + '">ändern</button>' +
      '</div>' +
      '<div class="feldzeile" style="align-items:flex-start">' +
        '<span class="feldname">Wer macht\'s</span>' +
        '<div class="tagereihe">' + tagereihe + '</div>' +
      '</div>' +
      '<div class="save-leiste">' +
        '<button type="button" class="btn danger btn-slot-loeschen" data-slot-key="' + esc(slot.schluessel) + '">Slot löschen</button>' +
      '</div>' +
    '</div>'
  );
}

function kalenderReadBodyHtml(slot) {
  const kind = slot.kind_id ? personById(slot.kind_id) : null;
  const anzeigeName = slotLabel(slot);

  return (
    '<div class="slot-body">' +
      '<div class="feldzeile">' +
        '<span class="feldname">Name</span>' +
        '<input type="text" class="slot-label-input" data-slot-key="' + esc(slot.schluessel) + '"' +
          ' value="' + esc(slot.label || "") + '"' +
          ' placeholder="' + esc(anzeigeName) + '"' +
          ' aria-label="Name des Slots">' +
      '</div>' +
      '<div class="feldzeile">' +
        '<span class="feldname">Piktogramm</span>' +
        '<img class="slot-icon" src="' + esc(arasaacUrl(slot.icon)) + '" alt="" loading="lazy">' +
        '<button type="button" class="btn sm btn-icon-aendern" data-slot-key="' + esc(slot.schluessel) + '">ändern</button>' +
      '</div>' +
      '<div class="feldzeile">' +
        '<span class="feldname">Kind</span>' +
        (kind ? ringHtml(kind.id, "ring") + '<span>' + esc(kind.name) + '</span>' : '<span style="color:#8a857c">— kein Kind</span>') +
        '<button type="button" class="btn sm btn-kind-waehlen" data-slot-key="' + esc(slot.schluessel) + '">ändern</button>' +
      '</div>' +
      '<div class="feldzeile">' +
        '<span class="feldname">Filter</span>' +
        '<span style="font-size:14px;color:#6b6760">' +
          (kind
            ? 'Termine mit „<b style="color:#1e1a14">' + esc(kind.name) + '</b>" im Titel (read-only aus Kalender).'
            : 'Kind wählen, um den Kalender-Filter zu setzen.') +
        '</span>' +
      '</div>' +
      '<div class="save-leiste">' +
        '<button type="button" class="btn danger btn-slot-loeschen" data-slot-key="' + esc(slot.schluessel) + '">Slot löschen</button>' +
      '</div>' +
    '</div>'
  );
}

// ── Sheet: Icon-Picker ────────────────────────────────────────────────────────

function oeffneIconPicker(slotKey, callback) {
  _aktuellesSheet = "icon";
  _sheetKontext = { slotKey, callback };
  _pickerIconId = null;

  const overlay = document.getElementById("sheet-icon");
  const input = document.getElementById("icon-suche");
  const grid = document.getElementById("icon-grid");

  input.value = "";
  grid.innerHTML = '<p class="lade-hinweis">Suchbegriff eingeben …</p>';
  overlay.removeAttribute("hidden");

  // Fokus nach kurzer Verzögerung (Sheet-Animation)
  setTimeout(() => input && input.focus(), 60);
}

function schliesseIconPicker() {
  document.getElementById("sheet-icon").setAttribute("hidden", "");
  _aktuellesSheet = null;
  _pickerIconId = null;
  clearTimeout(_debounceTimer);
}

function rendereIconGrid(treffer) {
  const grid = document.getElementById("icon-grid");
  if (!treffer || treffer.length === 0) {
    grid.innerHTML = '<p class="lade-hinweis">Keine Treffer — anderes Wort probieren.</p>';
    return;
  }
  grid.innerHTML = treffer.map((t) => {
    const id = t.id || t.arasaac_id || t;
    const url = arasaacUrl(id);
    const gewaehlt = _pickerIconId === String(id) ? " gewaehlt" : "";
    return (
      '<button type="button" class="icon-pick-btn' + gewaehlt + '" data-icon-id="' + esc(String(id)) + '">' +
        '<img src="' + esc(url) + '" alt="" loading="lazy">' +
      '</button>'
    );
  }).join("");
}

async function sucheUndRendereIcons(q) {
  const grid = document.getElementById("icon-grid");
  const suchToken = q;
  grid.innerHTML = '<p class="lade-hinweis">Suche …</p>';

  try {
    const treffer = await sucheIcons(q);
    // Race-Schutz: wenn Input inzwischen anders, verwerfen
    const aktuellerWert = (document.getElementById("icon-suche") || {}).value;
    if (aktuellerWert !== undefined && aktuellerWert.trim() !== suchToken) return;

    rendereIconGrid(treffer);
  } catch (err) {
    grid.innerHTML = '<p class="lade-hinweis">Icon-Suche nicht erreichbar.</p>';
    console.error("plan-einstellungen: Icon-Suche Fehler", err);
  }
}

// ── Sheet: Personen-Picker ────────────────────────────────────────────────────

function oeffnePersonenPicker(titel, slotKey, tagIdx, aktuellePersonId, callback) {
  _aktuellesSheet = "person";
  _sheetKontext = { slotKey, tagIdx, callback };

  const overlay = document.getElementById("sheet-person");
  const titelEl = document.getElementById("person-titel");
  titelEl.textContent = titel;

  const grid = document.getElementById("person-grid");
  // Leer-Option
  let html = (
    '<div class="person" data-person-id="">' +
      '<span class="ring leer">×</span>' +
      '<span>leer</span>' +
    '</div>'
  );
  html += _personen.map((p) => {
    const gewaehlt = p.id === aktuellePersonId ? " gewaehlt" : "";
    return (
      '<div class="person' + gewaehlt + '" data-person-id="' + esc(p.id) + '">' +
        '<img class="ring ring-' + esc(p.ring || "gray") + '"' +
        ' src="/api/v1/familie/foto/' + esc(p.id) + '"' +
        ' alt="' + esc(p.name) + '" loading="lazy">' +
        '<span>' + esc(p.name) + '</span>' +
      '</div>'
    );
  }).join("");

  grid.innerHTML = html;
  overlay.removeAttribute("hidden");
}

function schliessePersonenPicker() {
  document.getElementById("sheet-person").setAttribute("hidden", "");
  _aktuellesSheet = null;
}

// ── Sheet: Typ-Wahl (neuer Slot) ──────────────────────────────────────────────

function oeffneTypWahl() {
  _aktuellesSheet = "typ";
  const overlay = document.getElementById("sheet-typ");
  // Reset: erste Option aktiv
  overlay.querySelectorAll(".typ-wahl .opt").forEach((o, i) => {
    o.classList.toggle("aktiv", i === 0);
  });
  overlay.removeAttribute("hidden");
}

function schliesseTypWahl() {
  document.getElementById("sheet-typ").setAttribute("hidden", "");
  _aktuellesSheet = null;
}

// ── Sheet: Neuer-Slot-Label ────────────────────────────────────────────────────

/** Öffnet Label-Eingabe-Sheet nach Typ-Wahl */
function oeffneNeuSlotSheet(art) {
  _aktuellesSheet = "neu-slot";
  _sheetKontext = { art };
  _pickerIconId = null;

  const overlay = document.getElementById("sheet-neu-slot");
  const input = overlay.querySelector(".neu-label-input");
  const iconSuche = overlay.querySelector(".neu-icon-suche");
  const iconGrid = overlay.querySelector(".icon-grid");

  input.value = "";
  if (iconSuche) iconSuche.value = "";
  iconGrid.innerHTML = '<p class="lade-hinweis">Suchbegriff oben eingeben …</p>';
  overlay.querySelector(".neu-slot-anlegen").disabled = true;
  overlay.removeAttribute("hidden");

  setTimeout(() => input && input.focus(), 60);
}

function schliesseNeuSlotSheet() {
  const overlay = document.getElementById("sheet-neu-slot");
  const iconSuche = overlay ? overlay.querySelector(".neu-icon-suche") : null;
  if (iconSuche) iconSuche.value = "";
  overlay.setAttribute("hidden", "");
  _aktuellesSheet = null;
  _pickerIconId = null;
  clearTimeout(_debounceTimer);
}

function aktualisiereAnlegenBtn() {
  const overlay = document.getElementById("sheet-neu-slot");
  if (!overlay) return;
  const label = (overlay.querySelector(".neu-label-input") || {}).value || "";
  // _pickerIconId muss vorhanden UND ein echter Wert sein (kein "null"/"undefined"/leer).
  const iconOk = !!(_pickerIconId && _pickerIconId !== "null" && _pickerIconId !== "undefined" && _pickerIconId.trim() !== "");
  overlay.querySelector(".neu-slot-anlegen").disabled = !(label.trim() && iconOk);
}

// ── Slot-Operationen ─────────────────────────────────────────────────────────

function bewegeSlot(schluessel, richtung) {
  const idx = _editSlots.findIndex((s) => s.schluessel === schluessel);
  if (idx === -1) return;
  if (richtung === "hoch" && idx === 0) return;
  if (richtung === "runter" && idx === _editSlots.length - 1) return;

  const partner = richtung === "hoch" ? idx - 1 : idx + 1;
  [_editSlots[idx], _editSlots[partner]] = [_editSlots[partner], _editSlots[idx]];
  rendereSlotListe();
  bindeDelegation();
  aktualisiereSpeichernBtn();
}

function loescheSlot(schluessel) {
  if (!confirm('Slot „' + schluessel + '" wirklich löschen?')) return;
  _editSlots = _editSlots.filter((s) => s.schluessel !== schluessel);
  // Auch aus Defaults entfernen
  delete _editDefaults[schluessel];
  rendereSlotListe();
  bindeDelegation();
  aktualisiereSpeichernBtn();
}

function setzeSlotIcon(schluessel, iconId) {
  const slot = _editSlots.find((s) => s.schluessel === schluessel);
  if (!slot) return;
  if (!iconId || iconId === "null" || iconId === "undefined") {
    console.error("plan-einstellungen: setzeSlotIcon: ungueltige iconId", iconId);
    return;
  }
  slot.icon = String(iconId);
  rendereSlotListe();
  bindeDelegation();
  aktualisiereSpeichernBtn();
}

function setzeSlotLabel(schluessel, neuesLabel) {
  const slot = _editSlots.find((s) => s.schluessel === schluessel);
  if (!slot) return;
  // Leerer String → null (Fallback greift dann in slotLabel())
  slot.label = neuesLabel.trim() || null;
  // Kein Re-Render (Input bleibt fokussiert), aber Speichern-Knopf aktualisieren
  aktualisiereSpeichernBtn();
}

function setzeSlotKind(schluessel, personId) {
  const slot = _editSlots.find((s) => s.schluessel === schluessel);
  if (!slot) return;
  slot.kind_id = personId || null;
  rendereSlotListe();
  bindeDelegation();
  aktualisiereSpeichernBtn();
}

function setzeDefault(slotKey, tagIdx, personId) {
  if (!_editDefaults[slotKey]) _editDefaults[slotKey] = {};
  _editDefaults[slotKey][String(tagIdx)] = personId || null;
  rendereSlotListe();
  bindeDelegation();
  aktualisiereSpeichernBtn();
}

function legeSlotAn(label, art, iconId) {
  // Defensiv-Guard: iconId muss ein echter Wert sein (nie "null"/"undefined"/leer).
  // Der Anlegen-Button ist disabled bis _pickerIconId gesetzt ist (aktualisiereAnlegenBtn),
  // aber diese Pruefung ist ein zusaetzlicher Sicherheits-Zaun (PLAN-1139-FIX1).
  if (!iconId || String(iconId) === "null" || String(iconId) === "undefined" || String(iconId).trim() === "") {
    console.error("plan-einstellungen: legeSlotAn: iconId ist nicht gesetzt — Anlegen abgebrochen", { label, art, iconId });
    return;
  }

  // Schlüssel: slugify + dedup
  const basisKey = label.toLowerCase()
    .replace(/[äöüß]/g, (c) => ({ ä: "ae", ö: "oe", ü: "ue", ß: "ss" }[c]))
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
  let key = basisKey || "slot";
  let i = 2;
  while (_editSlots.some((s) => s.schluessel === key)) {
    key = basisKey + "-" + i++;
  }

  const neuerSlot = {
    schluessel: key,
    label,
    art,
    icon: String(iconId),
    kind_id: null,
    reihenfolge: _editSlots.length,
  };
  _editSlots.push(neuerSlot);
  rendereSlotListe();
  bindeDelegation();
  aktualisiereSpeichernBtn();

  // Accordion öffnen
  setTimeout(() => {
    const el = document.getElementById("slot-" + key);
    if (el) el.open = true;
  }, 50);
}

// ── Speichern ─────────────────────────────────────────────────────────────────

function aktualisiereSpeichernBtn() {
  const btn = document.getElementById("speichern-btn");
  if (!btn) return;
  const hatDiff = hatAenderungen();
  btn.disabled = !hatDiff;
}

function hatAenderungen() {
  // Slot-Liste geändert?
  if (_editSlots.length !== _serverSlots.length) return true;
  for (let i = 0; i < _editSlots.length; i++) {
    const e = _editSlots[i];
    const s = _serverSlots[i];
    if (e.schluessel !== s.schluessel) return true;
    if (e.label !== s.label) return true;
    if (e.art !== s.art) return true;
    if (String(e.icon) !== String(s.icon)) return true;
    if ((e.kind_id || null) !== (s.kind_id || null)) return true;
  }

  // Defaults geändert?
  const slotsVon = Object.keys(_editDefaults);
  const slotsVor = Object.keys(_serverDefaults);
  if (slotsVon.length !== slotsVor.length) return true;
  for (const k of slotsVon) {
    if (!_serverDefaults[k]) return true;
    for (let i = 0; i < 7; i++) {
      const idx = String(i);
      const editVal = (_editDefaults[k][idx] || null);
      const servVal = (_serverDefaults[k][idx] || null);
      if (editVal !== servVal) return true;
    }
  }
  return false;
}

async function onSpeichern() {
  const btn = document.getElementById("speichern-btn");
  const statusEl = document.getElementById("speichern-status");
  if (!btn || btn.disabled) return;

  btn.disabled = true;
  if (statusEl) statusEl.textContent = "Speichert …";

  try {
    // Slots mit korrekter Reihenfolge (Index = Reihenfolge)
    // API erwartet "kind" (PLAN-37, Backend-Schema plan/config.py Slot.kind) — intern kind_id
    const slotsPayload = _editSlots.map((s, i) => ({
      schluessel: s.schluessel,
      label: s.label,
      art: s.art,
      icon: String(s.icon),
      kind: s.kind_id || null,
      reihenfolge: i,
    }));

    // Sequenziell, NICHT parallel: beide PUTs sind Read-Modify-Write auf dieselbe
    // plan.json (Backend threaded) — parallel racen sie und überschreiben sich
    // gegenseitig (PLAN-1139 Save-Race). Erst Slot-Modell, dann Defaults.
    await speichereSlotModell(slotsPayload);
    await speichereDefaults(_editDefaults);

    // Server-Stand aktualisieren
    _serverSlots = _editSlots.map((s) => ({ ...s }));
    _serverDefaults = JSON.parse(JSON.stringify(_editDefaults));

    if (statusEl) {
      statusEl.textContent = "Gespeichert ✓";
      setTimeout(() => { if (statusEl) statusEl.textContent = ""; }, 2000);
    }
  } catch (err) {
    console.error("plan-einstellungen: Speichern fehlgeschlagen", err);
    if (statusEl) statusEl.textContent = "Fehler: " + err.message;
    btn.disabled = false;
    return;
  }

  aktualisiereSpeichernBtn();
}

// ── Klick-Delegation ─────────────────────────────────────────────────────────

function bindeDelegation() {
  // Slot-Container-Delegation (Reorder, Icon, Kind, Default-Tag, Löschen)
  const container = document.getElementById("slots-container");
  if (!container) return;

  // Existierende Handler entfernen (replace mit Clone)
  const fresh = container.cloneNode(true);
  container.parentNode.replaceChild(fresh, container);

  // Neu binden
  const c = document.getElementById("slots-container");

  // Label-Input: change-Event fuer bestehende Slots (AC3)
  c.addEventListener("change", (e) => {
    const labelInput = e.target.closest(".slot-label-input");
    if (labelInput) {
      setzeSlotLabel(labelInput.dataset.slotKey, labelInput.value);
    }
  });

  c.addEventListener("click", (e) => {
    // ▲ Reorder
    const hochBtn = e.target.closest(".pfeil-hoch");
    if (hochBtn) {
      bewegeSlot(hochBtn.dataset.slotKey, "hoch");
      return;
    }
    // ▼ Reorder
    const runterBtn = e.target.closest(".pfeil-runter");
    if (runterBtn) {
      bewegeSlot(runterBtn.dataset.slotKey, "runter");
      return;
    }
    // Icon ändern
    const iconBtn = e.target.closest(".btn-icon-aendern");
    if (iconBtn) {
      e.preventDefault();
      e.stopPropagation();
      const slotKey = iconBtn.dataset.slotKey;
      oeffneIconPicker(slotKey, (iconId) => {
        setzeSlotIcon(slotKey, iconId);
      });
      return;
    }
    // Kind wählen
    const kindBtn = e.target.closest(".btn-kind-waehlen");
    if (kindBtn) {
      e.preventDefault();
      e.stopPropagation();
      const slotKey = kindBtn.dataset.slotKey;
      const slot = _editSlots.find((s) => s.schluessel === slotKey);
      const aktuelleId = slot ? (slot.kind_id || null) : null;
      oeffnePersonenPicker(
        "Kind im Rail wählen",
        slotKey,
        null,
        aktuelleId,
        (personId) => setzeSlotKind(slotKey, personId)
      );
      return;
    }
    // Default-Tag-Knopf
    const tagBtn = e.target.closest(".person-tag-btn");
    if (tagBtn) {
      e.preventDefault();
      e.stopPropagation();
      const slotKey = tagBtn.dataset.slotKey;
      const tagIdx = parseInt(tagBtn.dataset.tagIdx, 10);
      const aktuelleId = (_editDefaults[slotKey] || {})[String(tagIdx)] || null;
      oeffnePersonenPicker(
        "Person für " + TAGE[tagIdx] + " wählen",
        slotKey,
        tagIdx,
        aktuelleId,
        (personId) => setzeDefault(slotKey, tagIdx, personId)
      );
      return;
    }
    // Slot löschen
    const loeschBtn = e.target.closest(".btn-slot-loeschen");
    if (loeschBtn) {
      loescheSlot(loeschBtn.dataset.slotKey);
      return;
    }
  });
}

// ── Initialisierung ───────────────────────────────────────────────────────────

async function ladeUndRendere() {
  const container = document.getElementById("slots-container");
  if (container) {
    container.innerHTML = '<p class="lade-hinweis">Wird geladen …</p>';
  }

  try {
    const [personen, slots, defaults] = await Promise.all([
      ladePersonen(),
      ladeSlotModell(),
      ladeDefaults(),
    ]);

    _personen = personen;
    _serverSlots = slots.map((s) => ({ ...s }));
    _editSlots = slots.map((s) => ({ ...s }));
    _serverDefaults = JSON.parse(JSON.stringify(defaults));
    _editDefaults = JSON.parse(JSON.stringify(defaults));

    rendereSlotListe();
    bindeDelegation();
    aktualisiereSpeichernBtn();
  } catch (err) {
    if (container) {
      container.innerHTML = '<p class="fehler-hinweis">Fehler beim Laden: ' + esc(err.message) + '</p>';
    }
    console.error("plan-einstellungen: Ladefehler", err);
  }
}

// ── IIFE: Einmaliger Boot ─────────────────────────────────────────────────────

(async function main() {
  // ── Speichern-Knopf ──────────────────────────────────────────────────────
  const speichernBtn = document.getElementById("speichern-btn");
  if (speichernBtn) {
    speichernBtn.addEventListener("click", onSpeichern);
  }

  // ── + Slot-Hinzufügen ─────────────────────────────────────────────────────
  const addBtn = document.getElementById("slot-add-btn");
  if (addBtn) {
    addBtn.addEventListener("click", () => oeffneTypWahl());
  }

  // ── Typ-Wahl-Sheet ────────────────────────────────────────────────────────
  const typSheet = document.getElementById("sheet-typ");
  if (typSheet) {
    typSheet.addEventListener("click", (e) => {
      // Overlay-Click → schließen
      if (e.target === typSheet) { schliesseTypWahl(); return; }
      // Opt-Wahl
      const opt = e.target.closest(".typ-wahl .opt");
      if (opt) {
        typSheet.querySelectorAll(".typ-wahl .opt").forEach((o) => o.classList.remove("aktiv"));
        opt.classList.add("aktiv");
        return;
      }
      // Abbrechen
      if (e.target.closest(".typ-wahl-abbrechen")) { schliesseTypWahl(); return; }
      // Weiter
      if (e.target.closest(".typ-wahl-weiter")) {
        const aktiveOpt = typSheet.querySelector(".typ-wahl .opt.aktiv");
        const art = aktiveOpt && aktiveOpt.dataset.art ? aktiveOpt.dataset.art : "verantwortlich";
        schliesseTypWahl();
        oeffneNeuSlotSheet(art);
      }
    });
  }

  // ── Neuer-Slot-Sheet ──────────────────────────────────────────────────────
  const neuSlotSheet = document.getElementById("sheet-neu-slot");
  if (neuSlotSheet) {
    const labelInput = neuSlotSheet.querySelector(".neu-label-input");
    const iconSucheInput = neuSlotSheet.querySelector(".neu-icon-suche");
    const iconGridEl = neuSlotSheet.querySelector(".icon-grid");

    /**
     * Sucht Icons und rendert das Grid im Neu-Slot-Sheet.
     * AC1: Entkoppelt von labelInput — freigetippter Suchbegriff moeglich.
     */
    async function sucheUndRendereNeuSlotIcons(q, tokenInput) {
      const token = q;
      iconGridEl.innerHTML = '<p class="lade-hinweis">Suche …</p>';
      try {
        const treffer = await sucheIcons(q);
        // Race-Schutz: nur rendern wenn der Input-Wert noch derselbe ist
        if (tokenInput && tokenInput.value.trim() !== token) return;
        if (!treffer || treffer.length === 0) {
          iconGridEl.innerHTML = '<p class="lade-hinweis">Nichts gefunden — anderes Wort probieren.</p>';
          _pickerIconId = null;
          aktualisiereAnlegenBtn();
          return;
        }
        iconGridEl.innerHTML = treffer.map((t) => {
          const id = t.id || t.arasaac_id || t;
          const gewaehlt = _pickerIconId === String(id) ? " gewaehlt" : "";
          return (
            '<button type="button" class="neu-icon-btn' + gewaehlt + '" data-icon-id="' + esc(String(id)) + '">' +
              '<img src="' + esc(arasaacUrl(id)) + '" alt="" loading="lazy">' +
            '</button>'
          );
        }).join("");
      } catch (err) {
        iconGridEl.innerHTML = '<p class="lade-hinweis">Icon-Suche nicht erreichbar.</p>';
      }
    }

    if (labelInput) {
      // AC1: Label-Input loest Best-Match-Suche aus, SOFERN Suche-Input leer ist.
      // Falls Benutzer bereits im Suche-Input was tippt, dominiert der Suche-Input.
      labelInput.addEventListener("input", () => {
        clearTimeout(_debounceTimer);
        aktualisiereAnlegenBtn();
        const q = labelInput.value.trim();
        const suchQ = iconSucheInput ? iconSucheInput.value.trim() : "";
        // Nur Auto-Suche aus Label wenn Suche-Feld leer
        if (suchQ.length === 0) {
          if (q.length >= 1) {
            _debounceTimer = setTimeout(() => sucheUndRendereNeuSlotIcons(q, labelInput), 250);
          } else {
            iconGridEl.innerHTML = '<p class="lade-hinweis">Suchbegriff oben eingeben …</p>';
          }
        }
      });
      labelInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); labelInput.blur(); }
      });
    }

    // AC1: Freies Suchfeld — überschreibt die Label-basierte Auto-Suche
    if (iconSucheInput) {
      iconSucheInput.addEventListener("input", () => {
        clearTimeout(_debounceTimer);
        const q = iconSucheInput.value.trim();
        if (q.length >= 1) {
          _debounceTimer = setTimeout(() => sucheUndRendereNeuSlotIcons(q, iconSucheInput), 250);
        } else {
          // Suche-Feld geleert → Fallback auf Label-Auto-Suche
          const labelQ = labelInput ? labelInput.value.trim() : "";
          if (labelQ.length >= 1) {
            _debounceTimer = setTimeout(() => sucheUndRendereNeuSlotIcons(labelQ, null), 250);
          } else {
            iconGridEl.innerHTML = '<p class="lade-hinweis">Suchbegriff oben eingeben …</p>';
          }
        }
      });
      iconSucheInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); iconSucheInput.blur(); }
      });
    }

    // Icon-Klick im Neu-Slot-Sheet
    if (iconGridEl) {
      iconGridEl.addEventListener("click", (e) => {
        const btn = e.target.closest(".neu-icon-btn");
        if (!btn) return;
        const rawId = btn.dataset.iconId;
        // Defensiv-Guard: leere/null-artige dataset-Werte nicht als Icon-ID akzeptieren (PLAN-1139-FIX1).
        if (!rawId || rawId === "null" || rawId === "undefined" || rawId.trim() === "") return;
        iconGridEl.querySelectorAll(".neu-icon-btn").forEach((b) => b.classList.remove("gewaehlt"));
        btn.classList.add("gewaehlt");
        _pickerIconId = rawId;
        aktualisiereAnlegenBtn();
      });
    }

    neuSlotSheet.addEventListener("click", (e) => {
      if (e.target === neuSlotSheet) { schliesseNeuSlotSheet(); return; }
      if (e.target.closest(".neu-slot-abbrechen")) { schliesseNeuSlotSheet(); return; }
      if (e.target.closest(".neu-slot-anlegen")) {
        if (!labelInput || !_pickerIconId) return;
        const label = labelInput.value.trim();
        if (!label) return;
        const art = (_sheetKontext && _sheetKontext.art) || "verantwortlich";
        const iconId = _pickerIconId;      // FIX PLAN-1139: vor dem Schließen sichern (schliesseNeuSlotSheet nullt _pickerIconId)
        schliesseNeuSlotSheet();
        legeSlotAn(label, art, iconId);
      }
    });
  }

  // ── Icon-Picker-Sheet (für bestehende Slots) ──────────────────────────────
  const iconSheet = document.getElementById("sheet-icon");
  if (iconSheet) {
    const iconSuche = document.getElementById("icon-suche");
    const iconGrid = document.getElementById("icon-grid");

    if (iconSuche) {
      iconSuche.addEventListener("input", () => {
        clearTimeout(_debounceTimer);
        const q = iconSuche.value.trim();
        if (q.length >= 1) {
          _debounceTimer = setTimeout(() => sucheUndRendereIcons(q), 250);
        } else {
          iconGrid.innerHTML = '<p class="lade-hinweis">Suchbegriff eingeben …</p>';
        }
      });
      iconSuche.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); iconSuche.blur(); }
      });
    }

    if (iconGrid) {
      iconGrid.addEventListener("click", (e) => {
        const btn = e.target.closest(".icon-pick-btn");
        if (!btn) return;
        iconGrid.querySelectorAll(".icon-pick-btn").forEach((b) => b.classList.remove("gewaehlt"));
        btn.classList.add("gewaehlt");
        const iconId = btn.dataset.iconId;     // FIX PLAN-1139: vor dem Schließen sichern
        _pickerIconId = iconId;
        // Icon direkt übernehmen + Sheet schließen
        const kontext = _sheetKontext;
        schliesseIconPicker();
        if (kontext && kontext.callback) kontext.callback(iconId);
      });
    }

    iconSheet.addEventListener("click", (e) => {
      if (e.target === iconSheet) schliesseIconPicker();
    });
  }

  // ── Personen-Picker-Sheet ─────────────────────────────────────────────────
  const personSheet = document.getElementById("sheet-person");
  if (personSheet) {
    const personGrid = document.getElementById("person-grid");
    if (personGrid) {
      personGrid.addEventListener("click", (e) => {
        const person = e.target.closest(".person");
        if (!person) return;
        const personId = person.dataset.personId || null;
        const kontext = _sheetKontext;
        schliessePersonenPicker();
        if (kontext && kontext.callback) kontext.callback(personId);
      });
    }
    personSheet.addEventListener("click", (e) => {
      if (e.target === personSheet) schliessePersonenPicker();
    });
  }

  // ── Daten laden ───────────────────────────────────────────────────────────
  await ladeUndRendere();
})();
