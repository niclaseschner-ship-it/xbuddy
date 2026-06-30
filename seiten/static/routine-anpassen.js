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

// ── MAD-7 Auth-Header ─────────────────────────────────────────────────────────

// initData aus Telegram-WebApp (MAD-7): bei jedem fetch()-Call als
// Authorization: tma <initData>-Header gesendet. Leer außerhalb Telegram
// (Test-Browser) → Server antwortet mit 401.
const _initData = window.Telegram?.WebApp?.initData ?? "";

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

// T728 Bug-9: Sheet-Offen-Flag — _aktualisiereMainButton() macht nichts wenn Sheet offen ist,
// damit platform.hideMainButton() nicht durch indirekte setMainButton-Aufrufe überschrieben wird.
let _sheetOffen = false;

// ── Einstiegspunkt ────────────────────────────────────────────────────────────

(async function main() {
  // AC7/RAT-16/MAD-5 (brainstorm-Vorlage, NICHT ratifiziert): keine direkten WebApp-Aufrufe — nur platform.* erlaubt
  const platform = getPlatform();
  await platform.ready();

  // MAD-11: JS-Side-Auth-Probe (HTML-Route ist public — Skeleton lädt ohne Auth,
  // hier prüft JS, ob valide initData für die API-Aufrufe vorliegt).
  if (!(await platform.ensureAuth())) {
    document.body.innerHTML = '<div style="padding:2rem;text-align:center;font-family:system-ui;color:#666;font-size:1rem">Bitte über den Familien-Bot öffnen (initData fehlt oder ist ungültig).</div>';
    return;
  }

  // MainButton initial deaktiviert (ROUTINE-20: nur aktiv bei Diff)
  platform.setMainButton("Speichern", onSpeichern, { enabled: false });

  // T728 Bug-12: Listener NUR EINMAL binden (Event-Delegation — rendereInhalt darf
  // KEINE addEventListener-Calls mehr enthalten, sonst kumulativer Listener-Leak).
  const container = document.getElementById("routine-inhalt");

  // Klick-Delegation: Pfeile + Lösch-Buttons + Add-Button
  container.addEventListener("click", (e) => {
    // Pfeil-Buttons (▲/▼) — T728 Bug-10
    const pfeil = e.target.closest(".pfeil-hoch[data-pfeil-id], .pfeil-runter[data-pfeil-id]");
    if (pfeil) {
      const id       = pfeil.dataset.pfeilId;
      const richtung = pfeil.classList.contains("pfeil-hoch") ? "hoch" : "runter";
      _bewegeItemPerPfeil(id, richtung);
      return;
    }
    // Lösch-Buttons
    const del = e.target.closest(".del-btn[data-item-id]");
    if (del) {
      _loescheItemLokal(del.dataset.itemId);
      return;
    }
    // Inline-Add-Button (ROUTINE-23)
    const add = e.target.closest("#items-add-btn");
    if (add) {
      oeffneHinzufuegenSheet();
      return;
    }
  });

  // Input-Delegation: Zeit-Inputs
  container.addEventListener("input", (e) => {
    const zeitInput = e.target.closest(".zeit-input");
    if (!zeitInput) return;
    // Anker-ID aus dem Input-Element-ID "zeitinput-<ankerId>" lesen
    const ankerId = zeitInput.id.replace(/^zeitinput-/, "");
    const anker   = ZEIT_ANKER.find(a => a.id === ankerId);
    if (!anker) return;
    _editConfig[anker.schreibKey] = _parseZeitInput(zeitInput, anker);
    _aktualisiereMainButton();
  });

  await ladeUndRendere();
})();

// ── API-Calls ─────────────────────────────────────────────────────────────────

/**
 * Lädt die aktuelle Routine-Punkte-Liste (GET /api/v1/routine/items).
 * Antwort: {default: [{id, label, piktogramm}], einmalig_heute: [...]}
 */
async function holeItems() {
  const resp = await fetch("/api/v1/routine/items", {
    headers: _initData ? { "Authorization": "tma " + _initData } : {},
  });
  if (!resp.ok) throw new Error("items-Abruf fehlgeschlagen: " + resp.status);
  return resp.json();
}

/**
 * Lädt die aktuellen Zeitkonfigurationen (GET /api/v1/routine/config).
 * Antwort: {aufstehzeit, anzieh_vorlauf_min, abfahrtszeit}
 */
async function holeConfig() {
  const resp = await fetch("/api/v1/routine/config", {
    headers: _initData ? { "Authorization": "tma " + _initData } : {},
  });
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
    headers: _initData
      ? { "Content-Type": "application/json", "Authorization": "tma " + _initData }
      : { "Content-Type": "application/json" },
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
    { method: "DELETE", headers: _initData ? { "Authorization": "tma " + _initData } : {} }
  );
  return resp;
}

/**
 * Ersetzt die geordnete default-Liste (PUT /api/v1/routine/items).
 * T728 Iter-11 Bug-25 Fix: Spec-Drift Spec sagt {items:[ids]}, Backend
 * (routine/main.py PUT-Handler #354) erwartet aber direkt eine Liste von
 * {id, label, piktogramm}-Objects. Pragma: Frontend folgt Backend (sofort
 * grün), Spec-Update als Folge-Ticket.
 *
 * Payload: [{id, label, piktogramm}, ...]
 */
async function putItems(itemsAsObjects) {
  const resp = await fetch("/api/v1/routine/items", {
    method:  "PUT",
    headers: _initData
      ? { "Content-Type": "application/json", "Authorization": "tma " + _initData }
      : { "Content-Type": "application/json" },
    body:    JSON.stringify(itemsAsObjects),
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
    headers: _initData
      ? { "Content-Type": "application/json", "Authorization": "tma " + _initData }
      : { "Content-Type": "application/json" },
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
    "/api/v1/icons/suche?q=" + encodeURIComponent(q) + "&max=12",
    { headers: _initData ? { "Authorization": "tma " + _initData } : {} }
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
      '<span class="sektion-subtitel">▲ ▼ zum Sortieren</span>' +
    '</div>'
  );

  // T728 Bug-10: Pfeil-Buttons statt Drag-Handle — Telegram-Touch-konflikt-frei.
  // Einmalig-Items sind nicht sortierbar und bekommen keine Pfeile.
  const defaultItems = _editItems.filter(i => i.quelle === "default");
  for (let i = 0; i < _editItems.length; i++) {
    const item = _editItems[i];
    const istDefault = item.quelle === "default";
    const defaultIndex = istDefault ? defaultItems.indexOf(item) : -1;
    const istErste = istDefault && defaultIndex === 0;
    const istLetzte = istDefault && defaultIndex === defaultItems.length - 1;
    fragmente.push(rendereItemCard(item, istErste, istLetzte));
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

  // T728 Bug-12: Nur innerHTML-Reset hier — alle Listener-Bindungen sitzen einmalig im IIFE-Block.
  container.innerHTML = fragmente.join("");
}

/**
 * Rendert eine Item-Card (MAD-2-Pattern, ROUTINE-20).
 * T728 Bug-10: Drag-Handle ersetzt durch ▲/▼ Pfeil-Buttons (Telegram-Touch-konflikt-frei).
 * Bild, Label Mitte, 🌅-Marker für einmalig, Lösch-Knopf.
 *
 * @param {object} item        - Item-Objekt {id, label, piktogramm, quelle}
 * @param {boolean} istErste   - true wenn erste default-Card (▲ disabled)
 * @param {boolean} istLetzte  - true wenn letzte default-Card (▼ disabled)
 */
function rendereItemCard(item, istErste, istLetzte) {
  const istEinmalig = item.quelle === "einmalig";
  const bildSrc = "/display/_shared/icons/arasaac/" + encodeURIComponent(item.piktogramm) + ".png";

  // T728 Bug-10: Pfeil-Buttons statt Drag-Handle.
  // Einmalig-Items sind nicht sortierbar → kein Pfeil, nur Platzhalter.
  let pfeilHtml;
  if (istEinmalig) {
    pfeilHtml = '<div class="pfeil-gruppe pfeil-leer" aria-hidden="true"></div>';
  } else {
    const hochDisabled = istErste ? " disabled" : "";
    const runterDisabled = istLetzte ? " disabled" : "";
    pfeilHtml =
      '<div class="pfeil-gruppe">' +
        '<button type="button" class="pfeil-hoch" data-pfeil-id="' + esc(item.id) + '"' +
          hochDisabled +
          ' aria-label="' + esc(item.label) + ' nach oben">▲</button>' +
        '<button type="button" class="pfeil-runter" data-pfeil-id="' + esc(item.id) + '"' +
          runterDisabled +
          ' aria-label="' + esc(item.label) + ' nach unten">▼</button>' +
      '</div>';
  }

  const markerHtml = istEinmalig
    ? '<span class="item-marker" aria-label="Einmalig (nur heute)" title="Einmalig (nur heute)">🌅</span>'
    : '<span class="item-marker"></span>';

  const delHtml = '<button class="del-btn" data-item-id="' + esc(item.id) + '" ' +
    'aria-label="' + esc(item.label) + ' entfernen" title="Entfernen">×</button>';

  // ROUTINE-27: Label-Block mit optionalem Zeit-Badge
  const labelHtml = _labelMitZeit(item);

  return (
    '<div class="item-card' + (istEinmalig ? " einmalig" : "") + '" ' +
         'data-item-id="' + esc(item.id) + '" ' +
         'data-quelle="' + esc(item.quelle) + '">' +
      pfeilHtml +
      '<img class="item-bild" src="' + esc(bildSrc) + '" alt="" loading="lazy">' +
      labelHtml +
      markerHtml +
      delHtml +
    '</div>'
  );
}

/**
 * Rendert eine Zeit-Anker-Card (ROUTINE-20 / T728 Bug-13: Schloss für feste Anker).
 * locked=true (Aufstehen, Losgehen): 🔒-Schloss-Symbol — klar kein Sortier-Ziel.
 * locked=false (Anziehen): leerer Platzhalter — kein Pfeil, kein Schloss in V1.
 * V2 (#726): Zwischen-Anker dynamisch → Pfeile dann aktivieren.
 */
function rendereZeitCard(anker) {
  const bildSrc = "/display/_shared/icons/arasaac/" + encodeURIComponent(anker.piktogramm) + ".png";

  // T728 Bug-13: Schloss für locked (Aufstehen/Losgehen), leerer Platzhalter für nicht-locked (Anziehen).
  // KEIN Pfeil in Zeit-Cards in V1 — V2 (#726) spezifiziert den Pfeil-Pfad.
  // data-v2-hint="#726" und aria-label "Hoch (V1 nicht verfügbar)" bleiben als Marker für V2-Aktivierung.
  let pfeilHtml;
  if (anker.locked) {
    // Schloss-Symbol kommuniziert klar: dieser Anker ist fix, nicht verschiebbar.
    pfeilHtml =
      '<div class="pfeil-gruppe anker-schloss" data-v2-hint="#726" ' +
           'aria-label="Hoch (V1 nicht verfügbar)">' +
        '<span class="schloss-symbol" aria-hidden="true">🔒</span>' +
      '</div>';
  } else {
    // Anziehen (vorlauf): kein Pfeil, kein Schloss in V1 — leerer Platzhalter.
    pfeilHtml = '<div class="pfeil-gruppe pfeil-leer" aria-hidden="true"></div>';
  }

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
      pfeilHtml +
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

// ── Pfeil-Sortierung (default-Items) ─────────────────────────────────────────

/**
 * T728 Bug-10: Tauscht ein default-Item per ▲/▼ Pfeil-Button.
 * Einmalig-Items am Ende bleiben unberührt (keine Pfeile, nie sortierbar).
 *
 * @param {string} id        - ID des zu verschiebenden Items
 * @param {string} richtung  - "hoch" oder "runter"
 */
function _bewegeItemPerPfeil(id, richtung) {
  const defaultItems = _editItems.filter(i => i.quelle === "default");
  const restItems    = _editItems.filter(i => i.quelle !== "default");

  const idx = defaultItems.findIndex(i => i.id === id);
  if (idx === -1) return;

  if (richtung === "hoch") {
    if (idx === 0) return; // bereits oben
    // Tausch mit Vorgänger
    [defaultItems[idx - 1], defaultItems[idx]] = [defaultItems[idx], defaultItems[idx - 1]];
  } else {
    if (idx === defaultItems.length - 1) return; // bereits unten
    // Tausch mit Nachfolger
    [defaultItems[idx], defaultItems[idx + 1]] = [defaultItems[idx + 1], defaultItems[idx]];
  }

  _editItems = [...defaultItems, ...restItems];
  rendereInhalt();
  _aktualisiereMainButton();
}

// ── Diff + MainButton ─────────────────────────────────────────────────────────

/**
 * Vergleicht Editor-Stand mit Server-Stand; aktiviert MainButton bei Diff.
 * ROUTINE-20: "Speichern" nur aktiv wenn diff.
 * T728 Bug-9: Guard — macht nichts wenn Sheet offen ist, damit platform.hideMainButton()
 * nicht durch indirekte setMainButton()-Aufrufe (z.B. aus Pikto-Picker) überschrieben wird.
 */
function _aktualisiereMainButton() {
  if (_sheetOffen) return; // T728 Bug-9: Sheet-Offen-Guard
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
    // T728 Iter-11 Bug-25 Fix: Backend erwartet Liste von {id, label, piktogramm}-Objects
    // (Spec-Drift zu ROUTINE-20 — Folge-Ticket für Spec-Update).
    const neueDefaultItems = _editItems
      .filter(i => i.quelle === "default" && !geloeschteIds.has(i.id))
      .map(i => ({ id: i.id, label: i.label, piktogramm: i.piktogramm }));

    const reihenfolgeGeaendert = (
      neueDefaultItems.length !== _serverItemsDefault.length ||
      neueDefaultItems.some((it, idx) => it.id !== (_serverItemsDefault[idx] || {}).id)
    );

    // Reihenfolge-Update: neue Items kommen bereits via Bottom-Sheet-POST an
    // den Server — dieser Pfad ist nur für Reihenfolge-Updates zuständig.
    if (reihenfolgeGeaendert && neueDefaultItems.length > 0) {
      const resp = await putItems(neueDefaultItems);
      if (!resp.ok) {
        // T728 Iter-11 Bug-24: freundlicher Fehler statt rohem Server-Text.
        zeigeToast("Konnte Reihenfolge nicht speichern — versuch's gleich nochmal.");
        const msg = await _fehlerText(resp, "Reihenfolge speichern");
        console.error("routine-anpassen: PUT items fail —", msg);
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
  let typAuswahl    = "punkt";   // ROUTINE-27: Default Punkt = kein zeit-Block

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

    // Typ-Toggle (ROUTINE-27): Punkt / Anker / Vorlauf
    '<div class="sheet-field">' +
      '<label>Typ</label>' +
      '<div class="toggle-typ">' +
        '<button type="button" id="tog-typ-punkt" class="active">· Punkt</button>' +
        '<button type="button" id="tog-typ-anker">⏰ Anker</button>' +
        '<button type="button" id="tog-typ-vorlauf">⏱ Vorlauf</button>' +
      '</div>' +
    '</div>' +

    // Zeit-Eingabe konditionell (ROUTINE-27): sichtbar je nach Typ-Toggle, kein Re-Render (T728 Bug-3)
    '<div id="zeit-eingabe-section" hidden>' +
      '<div id="anker-eingabe" class="sheet-field" hidden>' +
        '<label for="sheet-uhrzeit">Uhrzeit</label>' +
        '<input type="time" class="sheet-input" id="sheet-uhrzeit" value="07:00">' +
      '</div>' +
      '<div id="vorlauf-eingabe" class="sheet-field" hidden>' +
        '<label>Minuten Vorlauf</label>' +
        '<div class="vorlauf-stepper">' +
          '<button type="button" class="vorlauf-step-btn" id="vorlauf-minus" ' +
                 'aria-label="Weniger">−</button>' +
          '<input type="number" class="sheet-input vorlauf-input" id="sheet-vorlauf-min" ' +
                 'value="10" min="5" max="120" step="5" readonly ' +
                 'aria-label="Vorlauf in Minuten">' +
          '<button type="button" class="vorlauf-step-btn" id="vorlauf-plus" ' +
                 'aria-label="Mehr">+</button>' +
        '</div>' +
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

  // Typ-Toggle-Handler (ROUTINE-27: Punkt/Anker/Vorlauf, kein Re-Render, T728 Bug-3)
  function _aktualisiereZeitEingabe() {
    const sectionEl = inhalt.querySelector('#zeit-eingabe-section');
    const ankerEl   = inhalt.querySelector('#anker-eingabe');
    const vorlaufEl = inhalt.querySelector('#vorlauf-eingabe');
    if (sectionEl)  sectionEl.hidden = typAuswahl === 'punkt';
    if (ankerEl)    ankerEl.hidden   = typAuswahl !== 'anker';
    if (vorlaufEl)  vorlaufEl.hidden = typAuswahl !== 'vorlauf';
  }
  [['#tog-typ-punkt', 'punkt'], ['#tog-typ-anker', 'anker'], ['#tog-typ-vorlauf', 'vorlauf']].forEach(([id, typ]) => {
    const btn = inhalt.querySelector(id);
    if (!btn) return;
    btn.addEventListener('click', () => {
      typAuswahl = typ;
      ['#tog-typ-punkt', '#tog-typ-anker', '#tog-typ-vorlauf'].forEach(bid => {
        const b = inhalt.querySelector(bid);
        if (b) b.classList.remove('active');
      });
      btn.classList.add('active');
      _aktualisiereZeitEingabe();
    });
  });
  // Vorlauf-Stepper: −5 / +5 Minuten (ROUTINE-27, 5er-Schritte, Default 10)
  const vorlaufMinusBtn = inhalt.querySelector('#vorlauf-minus');
  const vorlaufPlusBtn  = inhalt.querySelector('#vorlauf-plus');
  if (vorlaufMinusBtn) {
    vorlaufMinusBtn.addEventListener('click', () => {
      const inp = inhalt.querySelector('#sheet-vorlauf-min');
      if (inp) inp.value = String(Math.max(5, (parseInt(inp.value, 10) || 10) - 5));
    });
  }
  if (vorlaufPlusBtn) {
    vorlaufPlusBtn.addEventListener('click', () => {
      const inp = inhalt.querySelector('#sheet-vorlauf-min');
      if (inp) inp.value = String(Math.min(120, (parseInt(inp.value, 10) || 10) + 5));
    });
  }

  // Label-Input: debounced ICONS-7 Auto-Suche (ROUTINE-21a)
  // T728 Bug-3: nur Galerie neu rendern, nicht das ganze Sheet
  const labelInput = inhalt.querySelector("#sheet-label");
  labelInput.addEventListener("input", () => {
    const q = labelInput.value.trim();
    clearTimeout(_debounceTimer);
    _aktualisiereAnlegenBtn();
    if (q.length >= 1) {
      _debounceTimer = setTimeout(() => _sucheUndRendereIcons(q, "auto"), 250);
    } else {
      const galerieEl = document.getElementById("picker-galerie");
      if (galerieEl) {
        galerieEl.innerHTML =
          '<div class="picker-leer">Tippe einen Begriff in das Feld oben.</div>';
      }
    }
  });

  // T728 Bug-19: Enter im Label-Input → blur() → Tastatur schließt sich
  labelInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      labelInput.blur();
    }
  });

  // ROUTINE-21b: manuelle Suchleiste
  const pickerSuche = inhalt.querySelector("#picker-suche");
  pickerSuche.addEventListener("input", () => {
    const q = pickerSuche.value.trim();
    clearTimeout(_debounceTimer);
    if (q.length >= 1) {
      _debounceTimer = setTimeout(() => _sucheUndRendereIcons(q, "manual"), 250);
    }
  });

  // T728 Bug-19: Enter in manueller Suchleiste → Suche triggern + blur()
  pickerSuche.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const q = pickerSuche.value.trim();
      if (q.length >= 1) {
        clearTimeout(_debounceTimer);
        _sucheUndRendereIcons(q, "manual");
      }
      pickerSuche.blur();
    }
  });

  // Abbrechen
  inhalt.querySelector("#sheet-abbrechen").addEventListener("click", schliesseSheet);

  // Anlegen (ROUTINE-21d: disabled ohne Pikto-Wahl; ROUTINE-27: zeit-Block je Typ)
  inhalt.querySelector("#sheet-anlegen").addEventListener("click", async () => {
    const label = labelInput.value.trim();
    if (!label || !_pickerSelectedId) return;

    // ROUTINE-27: zeit-Block aus Typ-Toggle und Eingabe-Feldern aufbauen
    const uhrzeitEl = inhalt.querySelector('#sheet-uhrzeit');
    const vorlaufEl = inhalt.querySelector('#sheet-vorlauf-min');
    const zeitBlock = _bauZeitBlock(
      typAuswahl,
      uhrzeitEl ? uhrzeitEl.value : '07:00',
      vorlaufEl ? (parseInt(vorlaufEl.value, 10) || 10) : 10,
    );

    await _legeItemAn(label, quelleAuswahl, _pickerSelectedId, zeitBlock);
  });

  // Nach Render: Label fokussieren
  setTimeout(() => labelInput && labelInput.focus(), 60);

  oeffneSheetOverlay();
}

/**
 * Lädt ICONS-7 und rendert die Galerie.
 * ROUTINE-21a/21c.
 * ICONS-7: Backend übernimmt Mehrwort-Tokenisierung + OR-Score-Sortierung.
 *   Frontend schickt ganzen Eingabe-Text (ROUTINE-21a); kein Wort-Split-Workaround.
 * @param {string} q      - Suchbegriff (auch Mehrwort)
 * @param {string} [_src] - Quelle ("auto"|"manual"), nur für interne Nutzung
 */
async function _sucheUndRendereIcons(q, _src) {
  const galerieEl = document.getElementById("picker-galerie");
  if (!galerieEl) return;

  // Race-Schutz: aktuellen Token merken (q ist unveränderlich im Closure)
  const suchToken = q;

  galerieEl.innerHTML = '<div class="picker-leer">Suche …</div>';

  try {
    const treffer = await sucheIcons(q);

    // Race-Schutz: falls Nutzer weitertippt, alten Render verwerfen.
    // T728 Iter-9 Bug-Fix: das richtige Input-Element je nach Quelle prüfen —
    // vorher griff der Auto-Pfad fälschlich auf #picker-suche (manuelle Suchleiste,
    // leer) statt #sheet-label → Auto-Suche aus Label-Input wurde immer verworfen.
    const inputId = _src === "manual" ? "picker-suche" : "sheet-label";
    const aktuellerInput = document.getElementById(inputId);
    const aktuellerWert = aktuellerInput ? aktuellerInput.value.trim() : suchToken;
    if (aktuellerWert !== suchToken) return;

    if (!treffer || treffer.length === 0) {
      // ROUTINE-21c: Null-Treffer-Klartext
      galerieEl.innerHTML =
        '<div class="picker-leer">Nichts gefunden für <strong>' + esc(q) +
        '</strong> — versuch ein anderes Wort.</div>';

      _pickerSelectedId = null;
      _aktualisiereAnlegenBtn();
      return;
    }

    // Galerie rendern (ROUTINE-21: 3-Spalten-Grid)
    _rendereIconGrid(galerieEl, treffer);

  } catch (err) {
    galerieEl.innerHTML =
      '<div class="picker-leer">Icon-Suche nicht erreichbar.</div>';
    console.error("routine-anpassen: Icon-Suche Fehler", err);
  }
}

/**
 * Rendert Icon-Treffer als Grid in galerieEl.
 * Intern genutzt von _sucheUndRendereIcons.
 * @param {HTMLElement} galerieEl  - Container-Element
 * @param {Array}       treffer    - Array von Treffer-Objekten ({id|arasaac_id} oder String)
 */
function _rendereIconGrid(galerieEl, treffer) {
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

  galerieEl.appendChild(grid);
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
async function _legeItemAn(label, quelle, piktogramm, zeitBlock) {
  // ROUTINE-27: zeit-Block optional — nur anhängen wenn nicht null (Typ Anker/Vorlauf)
  const payload = { label, piktogramm, quelle };
  if (zeitBlock) payload.zeit = zeitBlock;

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
 * T728 Bug-9: _sheetOffen=true VOR hideMainButton() setzen, damit kein paralleler
 * _aktualisiereMainButton()-Aufruf den hide-Zustand sofort wieder überschreibt.
 */
function oeffneSheetOverlay() {
  const overlay = document.getElementById("sheet-overlay");
  overlay.hidden = false;

  // T728 Bug-9: Flag setzen bevor hideMainButton() — verhindert Override durch
  // indirekte _aktualisiereMainButton()-Aufrufe (z.B. aus Pikto-Picker).
  _sheetOffen = true;

  // T728 Bug-7: MainButton während Sheet vollständig verstecken (MAD-5-konform via platform)
  const platform = getPlatform();
  platform.hideMainButton();

  // T728 Bug-11 (Belt-Belt-Suspender): dreifaches Hide — sofort (oben) + Microtask + 50ms.
  // BrowserPlatform: setMainButton() setzt display:block — ein gecachter/verzögerter JS-Aufruf
  // kann den hide-Zustand überschreiben. Drei Ebenen absichern das.
  Promise.resolve().then(() => { if (_sheetOffen) platform.hideMainButton(); });
  setTimeout(() => { if (_sheetOffen) platform.hideMainButton(); }, 50);

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) schliesseSheet();
  }, { once: true });
}

/**
 * T728 Bug-7: Beim Schließen des Sheets MainButton wieder anzeigen und
 * Diff-State aktualisieren (aktiv wenn Diff vorhanden, ROUTINE-20).
 * T728 Bug-9: _sheetOffen=false VOR _aktualisiereMainButton() setzen, damit
 * der Guard-Check in _aktualisiereMainButton() nicht greift.
 */
function schliesseSheet() {
  const overlay = document.getElementById("sheet-overlay");
  overlay.hidden = true;
  document.getElementById("sheet-inhalt").innerHTML = "";
  _pickerSelectedId = null;
  clearTimeout(_debounceTimer);

  // T728 Bug-9: Flag zurücksetzen bevor _aktualisiereMainButton() — damit Guard nicht greift.
  _sheetOffen = false;

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

// ── ROUTINE-27 — Typ-Toggle Hilfsfunktionen ───────────────────────────────────

/**
 * ROUTINE-27: Baut den zeit-Block für den POST /api/v1/routine/items Payload.
 * Punkt (Default): kein zeit-Block (null).
 * Anker: {typ:'anker', uhrzeit:HH:MM, locked:false}.
 * Vorlauf: {typ:'vorlauf', minuten:N, bezug:'vorheriger_anker'}.
 *
 * @param {string} typ      - 'punkt' | 'anker' | 'vorlauf'
 * @param {string} uhrzeit  - HH:MM-String (nur für typ='anker')
 * @param {number} minuten  - Ganzzahl (5er-Schritte, Default 10; nur für typ='vorlauf')
 * @returns {object|null}   - zeit-Block oder null für Punkt
 */
function _bauZeitBlock(typ, uhrzeit, minuten) {
  if (typ === 'anker') {
    return { typ: 'anker', uhrzeit: uhrzeit || '07:00', locked: false };
  }
  if (typ === 'vorlauf') {
    return { typ: 'vorlauf', minuten: minuten || 10, bezug: 'vorheriger_anker' };
  }
  // typ === 'punkt' (Default) → kein zeit-Block
  return null;
}

/**
 * ROUTINE-27: Berechnet die abgeleitete Uhrzeit eines Vorlauf-Items.
 * Sucht rückwärts in items nach dem letzten vorangehenden Anker und
 * subtrahiert dessen minuten-Wert.
 *
 * @param {object} item   - Item mit item.zeit.typ='vorlauf'
 * @param {Array}  items  - Gesamte Items-Liste (_editItems) für Kontext
 * @returns {string|null} - "HH:MM" oder null wenn kein vorangehender Anker
 */
function _vorlaufUhrzeit(item, items) {
  if (!item.zeit || item.zeit.typ !== 'vorlauf') return null;
  const idx = items.indexOf(item);
  let ankerUhrzeit = null;
  for (let i = idx - 1; i >= 0; i--) {
    const z = items[i].zeit;
    if (z && z.typ === 'anker' && z.uhrzeit) {
      ankerUhrzeit = z.uhrzeit;
      break;
    }
  }
  if (!ankerUhrzeit) return null;
  const parts = ankerUhrzeit.split(':');
  const totalMin = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) - (item.zeit.minuten || 0);
  if (totalMin < 0) return null;
  const rH = String(Math.floor(totalMin / 60)).padStart(2, '0');
  const rM = String(totalMin % 60).padStart(2, '0');
  return rH + ':' + rM;
}

/**
 * ROUTINE-27: Label-HTML mit optionalem Zeit-Badge für Item-Cards.
 * Ohne zeit-Block: <span class="item-label">.
 * Mit zeit-Block:  <div class="item-label-gruppe"> mit Badge-Sub-Zeile.
 * locked=true Anker: Badge mit Hinweis "V1-Anker, ändern in der Config" (ROUTINE-27).
 *
 * @param {object} item - Item-Objekt {id, label, piktogramm, quelle, zeit?}
 * @returns {string} - HTML-String
 */
function _labelMitZeit(item) {
  if (!item.zeit) {
    return '<span class="item-label">' + esc(item.label) + '</span>';
  }
  const z = item.zeit;
  let badgeHtml = '';
  if (z.typ === 'anker') {
    if (z.locked) {
      // locked=true: read-only mit Hinweis (ROUTINE-27; Migration auf editierbar in ROUTINE-28)
      badgeHtml =
        '<span class="item-zeit-badge item-zeit-locked">' +
          '🔒 ' + esc(z.uhrzeit || '') + ' · V1-Anker, ändern in der Config' +
        '</span>';
    } else {
      badgeHtml = '<span class="item-zeit-badge">⏰ ' + esc(z.uhrzeit || '') + '</span>';
    }
  } else if (z.typ === 'vorlauf') {
    const abgeleitet = _vorlaufUhrzeit(item, _editItems);
    const minStr = z.minuten != null
      ? '−' + esc(String(z.minuten)) + ' Min'
      : '− Min';
    badgeHtml =
      '<span class="item-zeit-badge">⏱ ' +
        (abgeleitet ? esc(abgeleitet) + ' (' + minStr + ')' : minStr) +
      '</span>';
  }
  return (
    '<div class="item-label-gruppe">' +
      '<span class="item-label">' + esc(item.label) + '</span>' +
      badgeHtml +
    '</div>'
  );
}

// ── Exports (für Tests, wenn als Modul geladen) ───────────────────────────────

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    esc,
    ANKER_AUFSTEHEN_ID, ANKER_ANZIEHEN_ID, ANKER_LOSGEHEN_ID, ZEIT_ANKER,
    // ROUTINE-27
    _bauZeitBlock, _vorlaufUhrzeit, _labelMitZeit,
    // Handler-Kette (AC2: Handler-getriebene DOM-Tests — Glue-Abdeckung)
    oeffneHinzufuegenSheet,
    // Testhelfer: setzt _pickerSelectedId von außen (simuliert Icon-Wahl)
    _testSetPickerSelectedId: (id) => { _pickerSelectedId = id; },
  };
}
