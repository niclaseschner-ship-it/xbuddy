/**
 * routine-anpassen.js — Eltern-Anpassen-Mini-App Frontend-Logik.
 *
 * ROUTINE-20: Zwei Sektionen "Routine-Punkte" + "Zeiten". Cards: ARASAAC
 *             links, Label Mitte, 🌅 für einmalig + Lösch-Affordanz rechts.
 *             Inline-Add je Sektion (kein FAB, ROUTINE-23 Abweichung von MAD-3).
 * ROUTINE-21: Bottom-Sheet mit Label-Input, dauerhaft/nur-heute-Toggle,
 *             Icon-Picker (ICONS-7 debounced 250ms).
 * MAD-5 (brainstorm-Vorlage, NICHT ratifiziert): kein direkter WebApp-Aufruf —
 *        alles ueber getPlatform() (platform.js).
 * MAD-6 (brainstorm-Vorlage, NICHT ratifiziert): ARASAAC-Pfad
 *        /display/_shared/icons/arasaac/<id>.png.
 * MAD-7 (brainstorm-Vorlage, NICHT ratifiziert): HTML-Route lädt ohne Auth in V1
 *        (127.0.0.1-bound, Tailscale-Funnel).
 */

/* global getPlatform */

// ── Konstanten ────────────────────────────────────────────────────────────────

// ROUTINE-20: Anker-Piktogramme hartcodiert (V1.1-Lego-Schuld — DRY-Verletzung:
// gleiche IDs stehen in routine/templates/morgen.html:84-104).
// TODO V1.1-Cleanup: in shared-Quelle ziehen (z.B. routine/anker_default.py),
// Mini-App-Frontend + Display-Template lesen daraus. Eigenes Lego-Cleanup-Ticket.
const ANKER_AUFSTEHEN_ID = "8152";
const ANKER_ANZIEHEN_ID  = "6627";
const ANKER_LOSGEHEN_ID  = "8142";

// V1.1: feste Anker-Liste (ROUTINE-20 drei Felder).
// typ "anker" = Aufstehen/Losgehen (gesperrt, kein Drag, kein Delete).
// typ "vorlauf" = Anziehen (editierbar als Minuten-Vorlauf).
const ZEIT_ANKER = [
  {
    id:         "aufstehen",
    label:      "Aufstehen",
    piktogramm: ANKER_AUFSTEHEN_ID,
    typ:        "anker",
    einheit:    "uhr",
    schreibKey: "aufstehzeit",
    locked:     true,
  },
  {
    id:         "anziehen",
    label:      "Anziehen",
    piktogramm: ANKER_ANZIEHEN_ID,
    typ:        "vorlauf",
    einheit:    "min",
    schreibKey: "anzieh_vorlauf_min",
    bezug:      "Min vor Losgehen",
    locked:     false,
  },
  {
    id:         "losgehen",
    label:      "Losgehen",
    piktogramm: ANKER_LOSGEHEN_ID,
    typ:        "anker",
    einheit:    "uhr",
    schreibKey: "abfahrtszeit",
    locked:     true,
  },
];

// ── State ─────────────────────────────────────────────────────────────────────

// Server-Stand beim Laden (zum Diff-Vergleich für MainButton-Aktivierung)
let _serverItemsDefault = [];     // [{id, label, piktogramm}]
let _serverItemsEinmalig = [];    // [{id, label, piktogramm}]
let _serverConfig = {};           // {aufstehzeit, anzieh_vorlauf_min, abfahrtszeit}

// Editor-Stand (mutierbarer Zustand)
let _editItems = [];              // [{id, label, piktogramm, quelle}]
let _editConfig = {};             // Kopie von _serverConfig, mutierbarer Stand

// Icon-Picker (ROUTINE-21)
let _pickerSelectedId = null;     // aktuell gewählte ARASAAC-ID im Bottom-Sheet
let _debounceTimer = null;        // für 250ms-Debounce (ROUTINE-21a)

// ── Einstiegspunkt ────────────────────────────────────────────────────────────

(async function main() {
  // AC7/RAT-16/MAD-5 (brainstorm-Vorlage, NICHT ratifiziert): keine direkten WebApp-Aufrufe — nur platform.* erlaubt
  const platform = getPlatform();
  await platform.ready();

  // MainButton initial deaktiviert (ROUTINE-20: nur aktiv bei Diff)
  platform.setMainButton("Speichern", onSpeichern, { enabled: false });

  await ladeUndRendere();
})();

// ── API-Calls ─────────────────────────────────────────────────────────────────

/**
 * Lädt die aktuelle Routine-Punkte-Liste (GET /api/v1/routine/items).
 * Antwort: {default: [{id, label, piktogramm}], einmalig_heute: [...]}
 */
async function holeItems() {
  const resp = await fetch("/api/v1/routine/items");
  if (!resp.ok) throw new Error("items-Abruf fehlgeschlagen: " + resp.status);
  return resp.json();
}

/**
 * Lädt die aktuellen Zeitkonfigurationen (GET /api/v1/routine/config).
 * Antwort: {aufstehzeit, anzieh_vorlauf_min, abfahrtszeit}
 */
async function holeConfig() {
  const resp = await fetch("/api/v1/routine/config");
  if (!resp.ok) throw new Error("config-Abruf fehlgeschlagen: " + resp.status);
  return resp.json();
}

/**
 * Legt einen neuen Routine-Punkt an (POST /api/v1/routine/items).
 * Antwort: {id: ...}
 */
async function postItem(payload) {
  const resp = await fetch("/api/v1/routine/items", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });
  return resp;
}

/**
 * Entfernt einen Routine-Punkt (DELETE /api/v1/routine/items/<id>).
 */
async function deleteItem(id) {
  const resp = await fetch(
    "/api/v1/routine/items/" + encodeURIComponent(id),
    { method: "DELETE" }
  );
  return resp;
}

/**
 * Ersetzt die geordnete default-Liste (PUT /api/v1/routine/items).
 * Payload: {items: ["id1", "id2", ...]}
 */
async function putItems(items) {
  const resp = await fetch("/api/v1/routine/items", {
    method:  "PUT",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ items }),
  });
  return resp;
}

/**
 * Schreibt Zeit-Konfiguration (PUT /api/v1/routine/config).
 * Payload: {aufstehzeit?, anzieh_vorlauf_min?, abfahrtszeit?}
 */
async function putConfig(payload) {
  const resp = await fetch("/api/v1/routine/config", {
    method:  "PUT",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });
  return resp;
}

/**
 * Sucht ARASAAC-Icons (GET /api/v1/icons/suche?q=<term>&max=12).
 * ROUTINE-21a / ICONS-7.
 */
async function sucheIcons(q) {
  const resp = await fetch(
    "/api/v1/icons/suche?q=" + encodeURIComponent(q) + "&max=12"
  );
  if (!resp.ok) return [];
  const data = await resp.json();
  return data.treffer || data.results || data || [];
}

// ── Render ────────────────────────────────────────────────────────────────────

async function ladeUndRendere() {
  try {
    const [itemsDaten, configDaten] = await Promise.all([holeItems(), holeConfig()]);

    _serverItemsDefault  = itemsDaten.default        || [];
    _serverItemsEinmalig = itemsDaten.einmalig_heute || [];
    _serverConfig        = { ...configDaten };

    // Editor-Stand initialisieren
    _editItems  = [
      ..._serverItemsDefault.map(i => ({ ...i, quelle: "default" })),
      ..._serverItemsEinmalig.map(i => ({ ...i, quelle: "einmalig" })),
    ];
    _editConfig = { ..._serverConfig };

    rendereInhalt();
  } catch (err) {
    const container = document.getElementById("routine-inhalt");
    container.innerHTML =
      '<p class="lade-hinweis">Konnte nicht geladen werden. Bitte nochmal versuchen.</p>';
    console.error("routine-anpassen: Ladefehler", err);
  }
}

/**
 * Rendert den gesamten Editor-Inhalt (beide Sektionen).
 * ROUTINE-20: Sektion "Routine-Punkte" + Sektion "Zeiten".
 */
function rendereInhalt() {
  const container = document.getElementById("routine-inhalt");

  const fragmente = [];

  // Sektion 1: Routine-Punkte
  fragmente.push(
    '<div class="sektion-header">' +
      '<span class="sektion-titel">Routine-Punkte</span>' +
      '<span class="sektion-subtitel">Halten &amp; ziehen zum Sortieren</span>' +
    '</div>'
  );

  for (const item of _editItems) {
    fragmente.push(rendereItemCard(item));
  }

  // Inline-Add am Ende der Items-Sektion (ROUTINE-23: kein FAB)
  fragmente.push(
    '<button class="add-row" id="items-add-btn" type="button">' +
      '＋ Routine-Punkt hinzufügen' +
    '</button>'
  );

  // Sektion 2: Zeiten
  fragmente.push(
    '<div class="sektion-header" style="margin-top:28px;">' +
      '<span class="sektion-titel">Zeiten</span>' +
      '<span class="sektion-subtitel">gleiche Piktogramme wie am Display</span>' +
    '</div>'
  );

  for (const anker of ZEIT_ANKER) {
    fragmente.push(rendereZeitCard(anker));
  }

  // V2-Add-Button: deaktiviert, visuell sichtbar (ROUTINE-20 V2-Aufbohrpunkt)
  fragmente.push(
    '<button class="add-row" disabled type="button">' +
      '＋ Zwischen-Anker hinzufügen — V2 (#726)' +
    '</button>' +
    '<p class="v2-hinweis">V1.1: Aufstehen und Losgehen sind fest · V2 macht das Dazwischen dynamisch</p>'
  );

  container.innerHTML = fragmente.join("");

  // Event-Handler anbinden
  document.getElementById("items-add-btn")
    .addEventListener("click", () => oeffneHinzufuegenSheet());

  // Drag-and-Drop für default-Items vorbereiten
  _bindeDragAndDrop();

  // Zeit-Inputs: oninput → Dirty-State
  for (const anker of ZEIT_ANKER) {
    const inputEl = document.getElementById("zeitinput-" + anker.id);
    if (inputEl) {
      inputEl.addEventListener("input", () => {
        _editConfig[anker.schreibKey] = _parseZeitInput(inputEl, anker);
        _aktualisiereMainButton();
      });
    }
  }

  // Lösch-Buttons für Items
  container.addEventListener("click", (e) => {
    const btn = e.target.closest(".del-btn[data-item-id]");
    if (!btn) return;
    const id = btn.dataset.itemId;
    _loescheItemLokal(id);
  });
}

/**
 * Rendert eine Item-Card (MAD-2-Pattern, ROUTINE-20).
 * Drag-Handle links, Bild, Label Mitte, 🌅-Marker für einmalig, Lösch-Knopf.
 */
function rendereItemCard(item) {
  const istEinmalig = item.quelle === "einmalig";
  const bildSrc = "/display/_shared/icons/arasaac/" + encodeURIComponent(item.piktogramm) + ".png";

  const dragHtml = istEinmalig
    ? '<div class="drag-handle schloss" title="Einmalig-Punkte sind nicht sortierbar" aria-hidden="true">≡</div>'
    : '<div class="drag-handle" data-drag-id="' + esc(item.id) + '" title="Halten &amp; ziehen zum Sortieren" aria-hidden="true">≡</div>';

  const markerHtml = istEinmalig
    ? '<span class="item-marker" aria-label="Einmalig (nur heute)" title="Einmalig (nur heute)">🌅</span>'
    : '<span class="item-marker"></span>';

  const delHtml = '<button class="del-btn" data-item-id="' + esc(item.id) + '" ' +
    'aria-label="' + esc(item.label) + ' entfernen" title="Entfernen">×</button>';

  return (
    '<div class="item-card' + (istEinmalig ? " einmalig" : "") + '" ' +
         'data-item-id="' + esc(item.id) + '" ' +
         'data-quelle="' + esc(item.quelle) + '">' +
      dragHtml +
      '<img class="item-bild" src="' + esc(bildSrc) + '" alt="" loading="lazy">' +
      '<span class="item-label">' + esc(item.label) + '</span>' +
      markerHtml +
      delHtml +
    '</div>'
  );
}

/**
 * Rendert eine Zeit-Anker-Card (ROUTINE-20: Schloss für Aufstehen + Losgehen).
 */
function rendereZeitCard(anker) {
  const bildSrc = "/display/_shared/icons/arasaac/" + encodeURIComponent(anker.piktogramm) + ".png";

  const dragHtml = anker.locked
    ? '<div class="drag-handle schloss" title="Fester Anker — unverrückbar" aria-hidden="true">🔒</div>'
    : '<div class="drag-handle schloss" title="Zeiten nicht sortierbar in V1" aria-hidden="true">≡</div>';

  // Zeit-Input je nach Einheit
  const serverWert = _editConfig[anker.schreibKey];
  let inputHtml;
  if (anker.einheit === "uhr") {
    const wert = typeof serverWert === "string" ? serverWert : "07:00";
    inputHtml =
      '<div class="zeit-feld-gruppe">' +
        '<input type="time" class="zeit-input zeit-input-uhr" ' +
               'id="zeitinput-' + esc(anker.id) + '" ' +
               'value="' + esc(wert) + '" ' +
               'aria-label="' + esc(anker.label) + '">' +
      '</div>';
  } else {
    // Minuten (anzieh_vorlauf_min)
    const wert = typeof serverWert === "number" ? serverWert : 10;
    inputHtml =
      '<div class="zeit-feld-gruppe">' +
        '<input type="number" class="zeit-input zeit-input-min" ' +
               'id="zeitinput-' + esc(anker.id) + '" ' +
               'value="' + esc(String(wert)) + '" ' +
               'min="0" max="120" ' +
               'aria-label="' + esc(anker.label) + ' in Minuten">' +
        '<span class="zeit-einheit">' + esc(anker.bezug || "Min") + '</span>' +
      '</div>';
  }

  // Kein Lösch-Knopf für Zeit-Anker (nur Platzhalter)
  const delHtml = '<div class="del-placeholder"></div>';

  return (
    '<div class="item-card' + (anker.locked ? " gesperrt" : "") + '" ' +
         'data-anker-id="' + esc(anker.id) + '">' +
      dragHtml +
      '<img class="item-bild" src="' + esc(bildSrc) + '" alt="" loading="lazy">' +
      '<span class="item-label">' + esc(anker.label) + '</span>' +
      inputHtml +
      delHtml +
    '</div>'
  );
}

// ── Editor-State (lokal) ──────────────────────────────────────────────────────

/**
 * Löscht ein Item lokal aus dem Edit-State (kein Server-Call hier).
 * Der Server-Call passiert beim Save (ROUTINE-20 Save-Pfad).
 */
function _loescheItemLokal(id) {
  _editItems = _editItems.filter(i => i.id !== id);
  rendereInhalt();
  _aktualisiereMainButton();
}

/**
 * Verarbeitet einen Zeit-Input-Wert in den richtigen Typ.
 */
function _parseZeitInput(inputEl, anker) {
  if (anker.einheit === "uhr") {
    return inputEl.value || (anker.id === "losgehen" ? "08:30" : "07:00");
  }
  const n = parseInt(inputEl.value, 10);
  return isNaN(n) || n < 0 ? 10 : n;
}

// ── Drag-and-Drop (default-Items) ─────────────────────────────────────────────

/**
 * T728 Bug-2: Pointer-Events Drag-and-Drop für default-Items.
 * Nutzt setPointerCapture + pointermove + elementFromPoint statt pointerover,
 * damit Drag in Telegram-Mini-App (wo touch events durch scroll blockiert werden)
 * zuverlässig funktioniert. touch-action: none auf dem Handle (CSS).
 * Nur default-Items sind bewegbar (einmalig rutscht ans Ende, ROUTINE-20).
 */
function _bindeDragAndDrop() {
  const container = document.getElementById("routine-inhalt");

  container.querySelectorAll(".drag-handle[data-drag-id]").forEach(handle => {
    const card = handle.closest(".item-card");
    if (!card) return;

    let draggingId = null;
    let dragOverId = null;

    handle.addEventListener("pointerdown", (e) => {
      draggingId = card.dataset.itemId;
      dragOverId = null;
      card.style.opacity = "0.5";
      // setPointerCapture: handle bekommt alle pointer-Events auch wenn Finger wandert
      handle.setPointerCapture(e.pointerId);
      e.preventDefault();
    });

    handle.addEventListener("pointermove", (e) => {
      if (!draggingId) return;
      // Pointer-Capture bedeutet, handle bekommt die Events — wir müssen elementFromPoint nutzen
      // um zu sehen, über welcher Card wir uns befinden
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (!el) return;
      const overCard = el.closest(".item-card[data-item-id]");
      if (!overCard) return;
      const overId = overCard.dataset.itemId;
      const overItem = _editItems.find(i => i.id === overId);
      if (!overItem || overItem.quelle !== "default") return;
      if (overId !== draggingId) {
        dragOverId = overId;
        // Visuelles Feedback: alle Cards zurücksetzen, dann Target markieren
        container.querySelectorAll(".item-card[data-item-id]").forEach(c => {
          c.style.outline = "";
        });
        overCard.style.outline = "2px solid var(--accent)";
      }
    });

    handle.addEventListener("pointerup", () => {
      if (!draggingId) return;
      if (dragOverId && dragOverId !== draggingId) {
        _bewegeItem(draggingId, dragOverId);
      } else {
        // Kein gültiges Drop-Ziel: nur Opacity zurücksetzen
        card.style.opacity = "";
        container.querySelectorAll(".item-card[data-item-id]").forEach(c => {
          c.style.outline = "";
        });
      }
      draggingId = null;
      dragOverId = null;
    });

    handle.addEventListener("pointercancel", () => {
      card.style.opacity = "";
      container.querySelectorAll(".item-card[data-item-id]").forEach(c => {
        c.style.outline = "";
      });
      draggingId = null;
      dragOverId = null;
    });
  });
}

/**
 * Verschiebt draggingId vor/nach targetId in der default-Liste.
 */
function _bewegeItem(draggingId, targetId) {
  const draggingItem = _editItems.find(i => i.id === draggingId);
  if (!draggingItem || draggingItem.quelle !== "default") return;

  const targetItem = _editItems.find(i => i.id === targetId);
  if (!targetItem || targetItem.quelle !== "default") return;

  const defaultItems = _editItems.filter(i => i.quelle === "default");
  const restItems    = _editItems.filter(i => i.quelle !== "default");

  const fromIdx = defaultItems.findIndex(i => i.id === draggingId);
  const toIdx   = defaultItems.findIndex(i => i.id === targetId);

  if (fromIdx === -1 || toIdx === -1) return;

  defaultItems.splice(fromIdx, 1);
  defaultItems.splice(toIdx, 0, draggingItem);

  _editItems = [...defaultItems, ...restItems];
  rendereInhalt();
  _aktualisiereMainButton();
}

// ── Diff + MainButton ─────────────────────────────────────────────────────────

/**
 * Vergleicht Editor-Stand mit Server-Stand; aktiviert MainButton bei Diff.
 * ROUTINE-20: "Speichern" nur aktiv wenn diff.
 */
function _aktualisiereMainButton() {
  const platform = getPlatform();
  const hatDiff = _hatDiff();
  platform.setMainButton("Speichern", onSpeichern, { enabled: hatDiff });
}

/**
 * Prüft ob der aktuelle Editor-Stand vom Server-Stand abweicht.
 */
function _hatDiff() {
  // Items-Diff: gelöschte oder neu hinzugefügte oder Reihenfolge geändert
  const editDefault = _editItems.filter(i => i.quelle === "default");

  if (editDefault.length !== _serverItemsDefault.length) return true;

  for (let i = 0; i < editDefault.length; i++) {
    if (editDefault[i].id !== _serverItemsDefault[i].id) return true;
  }

  // Einmalig gelöscht?
  const editEinmaligIds = new Set(
    _editItems.filter(i => i.quelle === "einmalig").map(i => i.id)
  );
  for (const item of _serverItemsEinmalig) {
    if (!editEinmaligIds.has(item.id)) return true;
  }

  // Config-Diff (ROUTINE-20: Zeiten)
  for (const anker of ZEIT_ANKER) {
    const key = anker.schreibKey;
    if (String(_editConfig[key]) !== String(_serverConfig[key])) return true;
  }

  return false;
}

// ── Save-Pfad (ROUTINE-20) ────────────────────────────────────────────────────

/**
 * Speichert alle Änderungen.
 * ROUTINE-20 Save-Pfad: bis zu 3 sequentielle Requests.
 * Schlägt ein Schritt fehl (4xx), wird ehrlich abgebrochen — kein Rollback.
 */
async function onSpeichern() {
  const platform = getPlatform();
  platform.setMainButton("Speichern", onSpeichern, { enabled: false });

  try {
    // Schritt 1: Gelöschte IDs sammeln + DELETE je ID
    // Bug-8-Fix: gelöschte IDs explizit sammeln, damit PUT-Schritt sie sicher ausschließt.
    const editDefaultIds = new Set(
      _editItems.filter(i => i.quelle === "default").map(i => i.id)
    );
    const editEinmaligIds = new Set(
      _editItems.filter(i => i.quelle === "einmalig").map(i => i.id)
    );

    // Bug-8-Fix: Set der in diesem Save-Lauf gelöschten IDs (für PUT-Filter).
    const geloeschteIds = new Set();

    for (const item of _serverItemsDefault) {
      if (!editDefaultIds.has(item.id)) {
        const resp = await deleteItem(item.id);
        if (!resp.ok) {
          const msg = await _fehlerText(resp, "Löschen von '" + item.label + "'");
          zeigeToast(msg);
          return;
        }
        geloeschteIds.add(item.id);
      }
    }
    for (const item of _serverItemsEinmalig) {
      if (!editEinmaligIds.has(item.id)) {
        const resp = await deleteItem(item.id);
        if (!resp.ok) {
          const msg = await _fehlerText(resp, "Löschen von '" + item.label + "'");
          zeigeToast(msg);
          return;
        }
        geloeschteIds.add(item.id);
      }
    }

    // Schritt 2: Reihenfolge / neue default-Items (PUT /api/v1/routine/items)
    // Bug-8-Fix: PUT-Array explizit ohne gelöschte IDs bauen.
    // Server validiert: alle PUT-IDs müssen nach dem DELETE-Schritt existieren.
    const neueDefaultIds = _editItems
      .filter(i => i.quelle === "default" && !geloeschteIds.has(i.id))
      .map(i => i.id);

    const reihenfolgeGeaendert = (
      neueDefaultIds.length !== _serverItemsDefault.length ||
      neueDefaultIds.some((id, idx) => id !== (_serverItemsDefault[idx] || {}).id)
    );

    // Reihenfolge-Update: neue Items kommen bereits via Bottom-Sheet-POST an
    // den Server — dieser Pfad ist nur für Reihenfolge-Updates zuständig.
    if (reihenfolgeGeaendert && neueDefaultIds.length > 0) {
      const resp = await putItems(neueDefaultIds);
      if (!resp.ok) {
        const msg = await _fehlerText(resp, "Reihenfolge speichern");
        zeigeToast(msg);
        return;
      }
    }

    // Schritt 3: Geänderte Zeiten (PUT /api/v1/routine/config, nur abweichende Keys)
    const configDiff = {};
    for (const anker of ZEIT_ANKER) {
      const key = anker.schreibKey;
      if (String(_editConfig[key]) !== String(_serverConfig[key])) {
        configDiff[key] = _editConfig[key];
      }
    }

    if (Object.keys(configDiff).length > 0) {
      const resp = await putConfig(configDiff);
      if (!resp.ok) {
        const msg = await _fehlerText(resp, "Zeiten speichern");
        zeigeToast(msg);
        return;
      }
    }

    // Erfolg: Server-Stand aktualisieren und neu laden
    zeigeToast("Gespeichert ✓");
    await ladeUndRendere();

  } catch (err) {
    zeigeToast("Buddy nicht erreichbar — versuch's gleich nochmal.");
    console.error("routine-anpassen: Speichern Fehler", err);
    _aktualisiereMainButton();
  }
}

/**
 * Extrahiert Fehlertext aus einer fehlgeschlagenen Response.
 */
async function _fehlerText(resp, kontext) {
  try {
    const body = await resp.json();
    const detail = body.error || body.detail || "";
    return (kontext || "Fehler") + ": " + (detail || resp.status);
  } catch (_) {
    return (kontext || "Fehler") + ": " + resp.status;
  }
}

// ── Hinzufügen-Bottom-Sheet (ROUTINE-21) ──────────────────────────────────────

/**
 * T728 Bug-3: Öffnet das Hinzufügen-Bottom-Sheet für einen neuen Routine-Punkt.
 * ROUTINE-21: Label-Input, dauerhaft/nur-heute-Toggle, Icon-Picker mit ICONS-7.
 *
 * Bug-3-Fix: Sheet-HTML wird NUR EINMAL gerendert. Toggle-Klick aktualisiert
 * nur die CSS-Klassen der Toggle-Buttons (kein innerHTML-Ersetzen → kein Focus-Loss).
 * Label-Input bleibt <input type=text> (einzeilig), max 40 Zeichen (ROUTINE-21).
 * Auto-Suche rendert nur #picker-galerie neu, nie das gesamte Sheet.
 */
function oeffneHinzufuegenSheet() {
  _pickerSelectedId = null;
  let quelleAuswahl = "default"; // Default: dauerhaft (ROUTINE-21)

  const inhalt = document.getElementById("sheet-inhalt");

  // Sheet-HTML einmalig aufbauen (T728 Bug-3: kein _renderSheet()-Re-Render)
  inhalt.innerHTML =
    '<p class="sheet-titel">Neuen Punkt anlegen</p>' +

    // Label-Input (ROUTINE-21: einzeilig <input type=text>, max 40 Zeichen)
    '<div class="sheet-field">' +
      '<label for="sheet-label">Text</label>' +
      '<input type="text" class="sheet-input" id="sheet-label" ' +
             'placeholder="z. B. Turnbeutel" maxlength="40" autocomplete="off">' +
    '</div>' +

    // dauerhaft / nur heute Toggle (ROUTINE-21)
    '<div class="sheet-field">' +
      '<label>Wann gilt der Punkt?</label>' +
      '<div class="toggle-quelle">' +
        '<button type="button" id="tog-default" class="active">' +
          '📅 dauerhaft' +
        '</button>' +
        '<button type="button" id="tog-einmalig">' +
          '🌅 nur heute' +
        '</button>' +
      '</div>' +
    '</div>' +

    // Icon-Picker (ROUTINE-21a/21b/21c/21d)
    '<div class="sheet-field">' +
      '<label>Piktogramm <span style="color:var(--ink-soft);font-weight:400;">— per Tap wählen</span></label>' +
      // ROUTINE-21b: manuelle Suchleiste immer sichtbar
      '<div class="picker-search-wrap">' +
        '<input type="text" class="picker-search-input" id="picker-suche" ' +
               'placeholder="Anderes Wort suchen …" autocomplete="off">' +
      '</div>' +
      '<div id="picker-galerie" class="picker-galerie">' +
        '<div class="picker-leer">Tippe einen Begriff in das Feld oben.</div>' +
      '</div>' +
    '</div>' +

    // Buttons
    '<div class="sheet-btn-gruppe">' +
      '<button type="button" class="sheet-btn sheet-btn-ghost" id="sheet-abbrechen">Abbrechen</button>' +
      '<button type="button" class="sheet-btn sheet-btn-primary" id="sheet-anlegen" disabled>' +
        'Anlegen' +
      '</button>' +
    '</div>';

  // Toggle-Handler: NUR Klassen wechseln, KEIN innerHTML-Re-Render (T728 Bug-3)
  inhalt.querySelector("#tog-default").addEventListener("click", () => {
    quelleAuswahl = "default";
    inhalt.querySelector("#tog-default").classList.add("active");
    inhalt.querySelector("#tog-einmalig").classList.remove("active");
  });
  inhalt.querySelector("#tog-einmalig").addEventListener("click", () => {
    quelleAuswahl = "einmalig";
    inhalt.querySelector("#tog-einmalig").classList.add("active");
    inhalt.querySelector("#tog-default").classList.remove("active");
  });

  // Label-Input: debounced ICONS-7 Auto-Suche (ROUTINE-21a)
  // T728 Bug-3: nur Galerie neu rendern, nicht das ganze Sheet
  const labelInput = inhalt.querySelector("#sheet-label");
  labelInput.addEventListener("input", () => {
    const q = labelInput.value.trim();
    clearTimeout(_debounceTimer);
    _aktualisiereAnlegenBtn();
    if (q.length >= 1) {
      _debounceTimer = setTimeout(() => _sucheUndRendereIcons(q), 250);
    } else {
      const galerieEl = document.getElementById("picker-galerie");
      if (galerieEl) {
        galerieEl.innerHTML =
          '<div class="picker-leer">Tippe einen Begriff in das Feld oben.</div>';
      }
    }
  });

  // ROUTINE-21b: manuelle Suchleiste
  const pickerSuche = inhalt.querySelector("#picker-suche");
  pickerSuche.addEventListener("input", () => {
    const q = pickerSuche.value.trim();
    clearTimeout(_debounceTimer);
    if (q.length >= 1) {
      _debounceTimer = setTimeout(() => _sucheUndRendereIcons(q), 250);
    }
  });

  // Abbrechen
  inhalt.querySelector("#sheet-abbrechen").addEventListener("click", schliesseSheet);

  // Anlegen (ROUTINE-21d: disabled ohne Pikto-Wahl)
  inhalt.querySelector("#sheet-anlegen").addEventListener("click", async () => {
    const label = labelInput.value.trim();
    if (!label || !_pickerSelectedId) return;

    await _legeItemAn(label, quelleAuswahl, _pickerSelectedId);
  });

  // Nach Render: Label fokussieren
  setTimeout(() => labelInput && labelInput.focus(), 60);

  oeffneSheetOverlay();
}

/**
 * Lädt ICONS-7 und rendert die Galerie.
 * ROUTINE-21a/21c.
 */
async function _sucheUndRendereIcons(q) {
  const galerieEl = document.getElementById("picker-galerie");
  if (!galerieEl) return;

  galerieEl.innerHTML = '<div class="picker-leer">Suche …</div>';

  try {
    const treffer = await sucheIcons(q);

    if (!treffer || treffer.length === 0) {
      // ROUTINE-21c: Null-Treffer-Klartext
      galerieEl.innerHTML =
        '<div class="picker-leer">Nichts gefunden für <strong>' + esc(q) +
        '</strong>.<br>Versuch ein anderes Wort.</div>';

      // Fokus auf manuelle Suchleiste (ROUTINE-21c)
      const pickerSuche = document.getElementById("picker-suche");
      if (pickerSuche) setTimeout(() => pickerSuche.focus(), 60);

      _pickerSelectedId = null;
      _aktualisiereAnlegenBtn();
      return;
    }

    // Galerie rendern (ROUTINE-21: 3-Spalten-Grid)
    const grid = document.createElement("div");
    grid.className = "icon-grid";

    for (const treffer_item of treffer) {
      const id  = treffer_item.id || treffer_item.arasaac_id || treffer_item;
      const url = "/display/_shared/icons/arasaac/" + encodeURIComponent(String(id)) + ".png";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "icon-grid-btn" + (_pickerSelectedId === String(id) ? " selected" : "");
      btn.innerHTML = '<img src="' + esc(url) + '" alt="" loading="lazy">';
      btn.addEventListener("click", () => {
        // Deselect alle
        grid.querySelectorAll(".icon-grid-btn").forEach(b => b.classList.remove("selected"));
        btn.classList.add("selected");
        _pickerSelectedId = String(id);
        _aktualisiereAnlegenBtn();
      });
      grid.appendChild(btn);
    }

    galerieEl.innerHTML = "";
    galerieEl.appendChild(grid);

  } catch (err) {
    galerieEl.innerHTML =
      '<div class="picker-leer">Icon-Suche nicht erreichbar.</div>';
    console.error("routine-anpassen: Icon-Suche Fehler", err);
  }
}

/**
 * Aktiviert/deaktiviert den Anlegen-Button je nach Pikto-Wahl.
 * ROUTINE-21d: Save disabled ohne Pikto-Wahl.
 */
function _aktualisiereAnlegenBtn() {
  const btn = document.getElementById("sheet-anlegen");
  if (!btn) return;
  const labelInput = document.getElementById("sheet-label");
  const hatLabel   = labelInput && labelInput.value.trim().length > 0;
  btn.disabled = !(hatLabel && _pickerSelectedId);
}

/**
 * Legt einen neuen Punkt an via POST /api/v1/routine/items.
 * Erfolg: Bottom-Sheet schließen, Liste neu laden.
 * 4xx: ehrliche Fehlermeldung im Sheet, kein Schließen (ROUTINE-21d).
 */
async function _legeItemAn(label, quelle, piktogramm) {
  const payload = { label, piktogramm, quelle };

  try {
    const resp = await postItem(payload);

    if (!resp.ok) {
      const msg = await _fehlerText(resp, "Punkt anlegen");
      // 4xx: Meldung im Sheet, kein Schließen (ROUTINE-21d)
      const titelEl = document.querySelector(".sheet-titel");
      if (titelEl) {
        titelEl.textContent = "";
        titelEl.innerHTML =
          '<span style="color:var(--danger)">' + esc(msg) + '</span>';
      }
      return;
    }

    // Erfolg: Sheet schließen + neu laden
    schliesseSheet();
    await ladeUndRendere();
    zeigeToast("Punkt hinzugefügt");

  } catch (err) {
    zeigeToast("Punkt anlegen: Buddy nicht erreichbar.");
    console.error("routine-anpassen: postItem Fehler", err);
  }
}

// ── Sheet-Overlay ─────────────────────────────────────────────────────────────

/**
 * T728 Bug-7: Beim Öffnen des Bottom-Sheets MainButton vollständig verstecken,
 * damit er die Sheet-Buttons nicht überdeckt.
 * platform.hideMainButton() ruft Telegram-WebApp btn.hide() bzw. DOM display:none.
 * setMainButton(enabled:false) allein reicht nicht — Button bleibt sichtbar (Bug-7).
 */
function oeffneSheetOverlay() {
  const overlay = document.getElementById("sheet-overlay");
  overlay.hidden = false;

  // T728 Bug-7: MainButton während Sheet vollständig verstecken (MAD-5-konform via platform)
  const platform = getPlatform();
  platform.hideMainButton();

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) schliesseSheet();
  }, { once: true });
}

/**
 * T728 Bug-7: Beim Schließen des Sheets MainButton wieder anzeigen und
 * Diff-State aktualisieren (aktiv wenn Diff vorhanden, ROUTINE-20).
 */
function schliesseSheet() {
  const overlay = document.getElementById("sheet-overlay");
  overlay.hidden = true;
  document.getElementById("sheet-inhalt").innerHTML = "";
  _pickerSelectedId = null;
  clearTimeout(_debounceTimer);

  // T728 Bug-7: MainButton wieder anzeigen, dann Diff-State aktualisieren
  const platform = getPlatform();
  platform.showMainButton();
  _aktualisiereMainButton();
}

// ── Hilfs-Funktionen ──────────────────────────────────────────────────────────

/**
 * HTML-Escaping (XSS-Schutz).
 */
function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function zeigeToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.classList.add("visible");
  setTimeout(() => toast.classList.remove("visible"), 3000);
}

// ── Exports (für Tests, wenn als Modul geladen) ───────────────────────────────

if (typeof module !== "undefined" && module.exports) {
  module.exports = { esc, ANKER_AUFSTEHEN_ID, ANKER_ANZIEHEN_ID, ANKER_LOSGEHEN_ID, ZEIT_ANKER };
}
