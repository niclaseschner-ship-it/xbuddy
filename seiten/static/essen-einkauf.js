/**
 * essen-einkauf.js — Eltern-Mini-App-View Frontend-Logik.
 *
 * ESSEN-31: Bring!-Card-Liste, Sektion-Header, Quellen-Marker, Tap-Routing.
 * ESSEN-30: Wunsch-Gericht-Übernahme-Sheet (Bottom-Sheet mit Zutat-Auswahl).
 * EZG-6:    Mini-App-URL /seiten/essen/einkauf — Auth via seiten-Service.
 * AC7/RAT-16: Kein direkter WebApp-Aufruf — alles ueber getPlatform() (platform.js).
 */

/* global getPlatform */

// ── Konstanten ────────────────────────────────────────────────────────────────

const KATEGORIE_REIHENFOLGE = ["gericht", "obst_gemuese", "brotbelag", "sonstiges"];

const KATEGORIE_LABEL = {
  gericht:      "Wunsch-Gerichte",
  obst_gemuese: "Obst & Gemüse",
  brotbelag:    "Brotbelag",
  sonstiges:    "Sonstiges",
};

// ESSEN-31: Marker je Klasse/aus_gericht
const MARKER_WUNSCH = "🧒";
const MARKER_REZEPT = "📖";

// ── MAD-7 Auth-Header ─────────────────────────────────────────────────────────

// initData aus Telegram-WebApp (MAD-7): bei jedem fetch()-Call als
// Authorization: tma <initData>-Header gesendet. Leer außerhalb Telegram
// (Test-Browser) → Server antwortet mit 401.
const _initData = window.Telegram?.WebApp?.initData ?? "";

// ── State ─────────────────────────────────────────────────────────────────────

// Alle offenen + erledigten Items (letzte geladene Liste)
let _liste = [];

// Für ESSEN-30-Zweiter-Tap-Logik (Gericht ohne Zutaten)
const _gerichtOhneTapStatus = new Map(); // item.id → "erstertap"|undefined

// ── Einstiegspunkt ────────────────────────────────────────────────────────────

(async function main() {
  // AC7/RAT-16: keine direkten WebApp-Aufrufe — nur platform.* erlaubt (platform.js)
  const platform = getPlatform();
  await platform.ready();

  // MAD-11: JS-Side-Auth-Probe (HTML-Route ist public — Skeleton lädt ohne Auth,
  // hier prüft JS, ob valide initData für die API-Aufrufe vorliegt).
  if (!(await platform.ensureAuth())) {
    document.body.innerHTML = '<div style="padding:2rem;text-align:center;font-family:system-ui;color:#666;font-size:1rem">Bitte über den Familien-Bot öffnen (initData fehlt oder ist ungültig).</div>';
    return;
  }

  await ladeUndRendere();

  document.getElementById("quick-add").addEventListener("click", oeffneQuickAddSheet);
})();

// ── API-Calls ─────────────────────────────────────────────────────────────────

/**
 * Lädt die vollständige Einkaufsliste (beide Klassen, alle abgehakt-Zustände).
 * Nutzt relativen Pfad — nginx routet /api/v1/essen/... zum essen-Buddy (Port 5052).
 */
async function holeListe() {
  const resp = await fetch("/api/v1/essen/wuensche", {
    headers: _initData ? { "Authorization": "tma " + _initData } : {},
  });
  if (!resp.ok) {
    throw new Error("Liste-Abruf fehlgeschlagen: " + resp.status);
  }
  return (await resp.json()).wuensche;
}

/**
 * Lädt den Katalog für Quick-Add-Auto-Match (ESSEN-31).
 */
async function holeKatalog() {
  const resp = await fetch("/api/v1/essen/katalog", {
    headers: _initData ? { "Authorization": "tma " + _initData } : {},
  });
  if (!resp.ok) return { kategorien: {} };
  return resp.json();
}

/**
 * Setzt abgehakt-Toggle via PATCH (ESSEN-32, ESSEN-31 Tap-Routing).
 */
async function patchAbgehakt(id, abgehakt) {
  const resp = await fetch("/api/v1/essen/wuensche/" + encodeURIComponent(id), {
    method:  "PATCH",
    headers: _initData
      ? { "Content-Type": "application/json", "Authorization": "tma " + _initData }
      : { "Content-Type": "application/json" },
    body:    JSON.stringify({ abgehakt }),
  });
  if (!resp.ok) {
    throw new Error("PATCH abgehakt fehlgeschlagen: " + resp.status);
  }
  return resp.json();
}

/**
 * Ergänzt aus_gericht auf bestehendem Eintrag (ESSEN-30 Dedupe-Pfad).
 */
async function patchAusGericht(id, ausGericht) {
  const resp = await fetch("/api/v1/essen/wuensche/" + encodeURIComponent(id), {
    method:  "PATCH",
    headers: _initData
      ? { "Content-Type": "application/json", "Authorization": "tma " + _initData }
      : { "Content-Type": "application/json" },
    body:    JSON.stringify({ aus_gericht: ausGericht }),
  });
  if (!resp.ok) {
    throw new Error("PATCH aus_gericht fehlgeschlagen: " + resp.status);
  }
  return resp.json();
}

/**
 * Legt neues Item an (ESSEN-16).
 */
async function postItem(payload) {
  const resp = await fetch("/api/v1/essen/wuensche", {
    method:  "POST",
    headers: _initData
      ? { "Content-Type": "application/json", "Authorization": "tma " + _initData }
      : { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });
  return resp; // Aufrufer prüft Status selbst (409 ist erwartet bei Dedupe)
}

// ── Render ────────────────────────────────────────────────────────────────────

async function ladeUndRendere() {
  try {
    _liste = await holeListe();
    rendereListe(_liste);
  } catch (err) {
    const container = document.getElementById("liste");
    container.innerHTML = '<p class="lade-hinweis">Liste konnte nicht geladen werden. Bitte nochmal versuchen.</p>';
    console.error("essen-einkauf: Liste-Abruf Fehler", err);
  }
}

/**
 * Rendert die vollständige Bring!-Card-Liste gruppiert nach Kategorie.
 * ESSEN-31: Reihenfolge gericht > obst_gemuese > brotbelag > sonstiges.
 * Kategorie-Sektionen führen ausschließlich offene Items; erledigte Items
 * werden in einer eigenen flachen "Erledigt · N"-Sektion am Listen-Ende
 * gerendert (ohne Kategorie-Untergruppe).
 */
function rendereListe(items) {
  const container = document.getElementById("liste");

  if (!items || items.length === 0) {
    container.innerHTML = '<p class="leer-hinweis">Einkaufsliste ist leer.</p>';
    return;
  }

  // Pre-Split: offeneGruppen (kategorie → offen[]) + erledigtFlach (flach)
  const offeneGruppen = {}; // kategorie → offen[]
  const erledigtFlach = []; // alle erledigten Items, flach
  for (const item of items) {
    const kat = item.kategorie || "sonstiges";
    if (item.abgehakt) {
      erledigtFlach.push(item);
    } else {
      if (!offeneGruppen[kat]) offeneGruppen[kat] = [];
      offeneGruppen[kat].push(item);
    }
  }

  // Innerhalb "offen": Reihenfolge wunsch → aus_gericht → einkauf ohne aus_gericht
  for (const kat of Object.keys(offeneGruppen)) {
    offeneGruppen[kat].sort((a, b) => {
      return _itemRangfolge(a) - _itemRangfolge(b);
    });
  }

  const fragmente = [];

  // Kategorie-Sektionen mit nur offenen Items
  for (const kat of KATEGORIE_REIHENFOLGE) {
    const offenItems = offeneGruppen[kat];
    if (!offenItems || offenItems.length === 0) continue;

    // Sektion-Header (ESSEN-31: "Sonstiges · 11 + 📖 3 + 🧒 1" — nur Offene zählen)
    fragmente.push(sektionHeader(kat, offenItems));

    for (const item of offenItems) {
      fragmente.push(renderCard(item));
    }
  }

  // Erledigt-Block am Listen-Ende (ESSEN-31)
  if (erledigtFlach.length > 0) {
    fragmente.push(erledigtSektionHeader(erledigtFlach.length));
    for (const item of erledigtFlach) {
      fragmente.push(renderCard(item));
    }
  }

  container.innerHTML = fragmente.join("");

  // Event-Delegation auf Cards
  container.addEventListener("click", onCardKlick, { once: false });
}

function _itemRangfolge(item) {
  if (item.klasse === "wunsch") return 0;
  if (item.klasse === "einkauf" && item.aus_gericht) return 1;
  return 2;
}

/**
 * Baut den Sektion-Header-HTML für eine Kategorie.
 * ESSEN-31: "Obst & Gemüse · N + 📖 R + 🧒 W" — nur offene Items zählen.
 */
function sektionHeader(kat, offenItems) {
  const titel = KATEGORIE_LABEL[kat] || kat;
  const nOffen = offenItems.length;
  const nRezept = offenItems.filter(i => i.klasse === "einkauf" && i.aus_gericht).length;
  const nWunsch = offenItems.filter(i => i.klasse === "wunsch").length;

  let counter = String(nOffen);
  const extras = [];
  if (nRezept > 0) extras.push("📖 " + nRezept);
  if (nWunsch > 0) extras.push("🧒 " + nWunsch);
  if (extras.length > 0) counter += " + " + extras.join(" + ");

  return (
    '<div class="sektion-header">' +
      '<span class="sektion-titel">' + esc(titel) + '</span>' +
      '<span class="sektion-counter">· ' + esc(counter) + '</span>' +
    '</div>'
  );
}

/**
 * Baut den Sektion-Header-HTML für den Erledigt-Block.
 * ESSEN-31: "Erledigt · N" — flache Sektion am Listen-Ende, keine Kategorie-Untergruppe.
 */
function erledigtSektionHeader(n) {
  return (
    '<div class="sektion-header erledigt-sektion-header">' +
      '<span class="sektion-titel">Erledigt</span>' +
      '<span class="sektion-counter">· ' + esc(String(n)) + '</span>' +
    '</div>'
  );
}

/**
 * Baut eine einzelne Item-Card.
 * ESSEN-31: Marker (🧒 / 📖 / kein), Bild, Label, Abhak-Check.
 */
function renderCard(item) {
  const erledigt = item.abgehakt ? " erledigt" : "";
  const marker = _marker(item);
  const bildSrc = "/display/_shared/icons/arasaac/" + encodeURIComponent(item.bild_ref) + ".png";

  // data-* für Event-Handler
  const dataId      = 'data-item-id="' + esc(item.id) + '"';
  const dataKlasse  = 'data-klasse="' + esc(item.klasse || "wunsch") + '"';
  const dataKat     = 'data-kategorie="' + esc(item.kategorie || "sonstiges") + '"';
  const dataAbge    = 'data-abgehakt="' + (item.abgehakt ? "true" : "false") + '"';

  const checkIcon = item.abgehakt ? "✓" : "";

  return (
    '<div class="item-card' + erledigt + '" ' +
         dataId + ' ' + dataKlasse + ' ' + dataKat + ' ' + dataAbge + '>' +
      '<img class="item-bild" src="' + esc(bildSrc) + '" alt="" loading="lazy">' +
      '<div class="item-text">' +
        '<span class="item-label">' + esc(item.label) + '</span>' +
      '</div>' +
      (marker ? '<span class="item-marker" aria-hidden="true">' + marker + '</span>' : '') +
      '<div class="item-check" aria-label="' + (item.abgehakt ? "Erledigt" : "Offen") + '">' +
        esc(checkIcon) +
      '</div>' +
    '</div>'
  );
}

/**
 * ESSEN-31: Quellen-Marker je Item.
 */
function _marker(item) {
  if (item.klasse === "wunsch") return MARKER_WUNSCH;
  if (item.klasse === "einkauf" && item.aus_gericht) return MARKER_REZEPT;
  return "";
}

// ── Tap-Routing (ESSEN-31) ────────────────────────────────────────────────────

/**
 * Delegierter Klick-Handler auf #liste.
 *
 * ESSEN-31 Tap-Routing:
 *   klasse=wunsch + kategorie=gericht + hat Zutaten → ESSEN-30 Übernahme-Sheet
 *   klasse=wunsch + kategorie=gericht ohne Zutaten  → Klartext-Sheet, zweiter Tap → abhaken
 *   alle anderen Karten                             → direkter abgehakt-Toggle via PATCH
 */
async function onCardKlick(evt) {
  const card = evt.target.closest(".item-card");
  if (!card) return;

  const id       = card.dataset.itemId;
  const klasse   = card.dataset.klasse;
  const kategorie = card.dataset.kategorie;
  const abgehakt = card.dataset.abgehakt === "true";

  if (!id) return;

  // Item aus State suchen
  const item = _liste.find(i => i.id === id);
  if (!item) return;

  // ESSEN-31 Tap-Routing
  if (klasse === "wunsch" && kategorie === "gericht") {
    await onTapWunschGericht(item);
  } else {
    // Direkter abgehakt-Toggle (alle anderen Cards)
    await toggleAbgehakt(item);
  }
}

/**
 * Tap auf 🧒-Gericht.
 * ESSEN-31 / ESSEN-30: Übernahme-Sheet wenn Zutaten vorhanden, sonst Klartext.
 */
async function onTapWunschGericht(item) {
  // Gerichte-Detail aus Katalog holen um Zutaten zu kennen
  let gerichte = [];
  try {
    const katalog = await holeKatalog();
    gerichte = katalog.kategorien?.gericht || [];
  } catch (_) {
    // kein Katalog → Klartext-Pfad
  }

  const gerichtKatalogEintrag = gerichte.find(
    g => g.label?.toLowerCase() === item.label?.toLowerCase() ||
         g.id === item.item_id
  );

  const zutaten = gerichtKatalogEintrag?.zutaten || [];

  if (zutaten.length === 0) {
    // Klartext-Pfad: zweiter Tap zum Abhaken (ESSEN-30 Edge-Case)
    await _gerichtOhneTapFlow(item);
  } else {
    // ESSEN-30 Übernahme-Sheet
    oeffneUebernahmeSheet(item, zutaten);
  }
}

/**
 * Gericht ohne Zutaten: erster Tap → Hinweis-Sheet, zweiter Tap → abgehakt=true.
 */
async function _gerichtOhneTapFlow(item) {
  if (_gerichtOhneTapStatus.get(item.id) === "erstertap") {
    // Zweiter Tap: abhaken
    _gerichtOhneTapStatus.delete(item.id);
    await toggleAbgehakt(item);
    return;
  }

  // Erster Tap: Info-Sheet öffnen
  _gerichtOhneTapStatus.set(item.id, "erstertap");

  const inhalt = document.getElementById("sheet-inhalt");
  inhalt.innerHTML =
    '<p class="sheet-titel">🧒 ' + esc(item.label) + '</p>' +
    '<p style="color:var(--ink-soft);margin-bottom:16px;font-size:0.95rem;">' +
      'Für dieses Gericht sind noch keine Zutaten hinterlegt.<br>' +
      'Tippe nochmal, um den Wunsch als erledigt zu markieren.' +
    '</p>' +
    '<div class="sheet-btn-gruppe">' +
      '<button class="sheet-btn sheet-btn-secondary" id="sheet-schliessen">Abbrechen</button>' +
    '</div>';

  document.getElementById("sheet-schliessen").addEventListener("click", schliesseSheet);
  oeffneSheetOverlay();
}

/**
 * Direkter abgehakt-Toggle (für alle Nicht-Gericht-Karten + Gerichte ohne Zutaten).
 */
async function toggleAbgehakt(item) {
  try {
    await patchAbgehakt(item.id, !item.abgehakt);
    await ladeUndRendere();
  } catch (err) {
    zeigeToast("Fehler beim Aktualisieren. Bitte nochmal.");
    console.error("toggleAbgehakt:", err);
  }
}

// ── Übernahme-Sheet (ESSEN-30) ────────────────────────────────────────────────

/**
 * Öffnet das Übernahme-Sheet für ein Wunsch-Gericht mit Zutaten.
 * ESSEN-30: Smart-Default, Live-Counter, Drei-Wege-Wahl.
 */
function oeffneUebernahmeSheet(gericht, zutaten) {
  // Smart-Default: alle ausgewählt außer die, die schon offen auf der Liste sind
  // (Match label case-insensitiv, unabhängig von klasse — ESSEN-30)
  const offeneLabels = new Set(
    _liste
      .filter(i => !i.abgehakt)
      .map(i => i.label.toLowerCase().trim())
  );

  // Zustand je Zutat: { zutat, ausgewaehlt, schonDrauf }
  const zutatStatus = zutaten.map(z => {
    const schonDrauf = offeneLabels.has(z.label.toLowerCase().trim());
    return { zutat: z, ausgewaehlt: !schonDrauf, schonDrauf };
  });

  function _renderSheet() {
    const inhalt = document.getElementById("sheet-inhalt");
    const nAusgewaehlt = zutatStatus.filter(s => s.ausgewaehlt).length;

    const zeilen = zutatStatus.map((s, idx) => {
      const bildSrc = "/display/_shared/icons/arasaac/" + encodeURIComponent(s.zutat.bild_ref) + ".png";
      const ausgewaehltKlasse = s.ausgewaehlt ? " ausgewaehlt" : "";
      const check = s.ausgewaehlt ? "✓" : "";
      const hinweis = s.schonDrauf ? '<span class="zutat-hinweis"> · schon drauf</span>' : "";

      return (
        '<div class="zutat-zeile' + ausgewaehltKlasse + '" data-zutat-idx="' + idx + '">' +
          '<img class="zutat-bild" src="' + esc(bildSrc) + '" alt="" loading="lazy">' +
          '<span class="zutat-label">' + esc(s.zutat.label) + hinweis + '</span>' +
          '<div class="zutat-check">' + esc(check) + '</div>' +
        '</div>'
      );
    }).join("");

    let bestaetigBtnLabel;
    if (nAusgewaehlt === 0) {
      bestaetigBtnLabel = "Nichts dazunehmen";
    } else {
      bestaetigBtnLabel = "✓ " + nAusgewaehlt + " Zutat" + (nAusgewaehlt !== 1 ? "en" : "") + " auf die Liste";
    }

    const nurAbhakenDisabled = ""; // immer möglich

    inhalt.innerHTML =
      '<p class="sheet-titel">🧒 Kinder wünschen sich ' + esc(gericht.label) + '</p>' +
      zeilen +
      '<div class="sheet-btn-gruppe">' +
        '<button class="sheet-btn sheet-btn-primary" id="sheet-bestaetigen"' +
          (nAusgewaehlt === 0 ? ' disabled' : '') + '>' +
          esc(bestaetigBtnLabel) +
        '</button>' +
        '<button class="sheet-btn sheet-btn-secondary" id="sheet-nur-abhaken">Nur abhaken</button>' +
        '<button class="sheet-btn sheet-btn-ghost" id="sheet-abbrechen">Abbrechen</button>' +
      '</div>';

    // Zutat-Toggle
    inhalt.querySelectorAll(".zutat-zeile").forEach(zeile => {
      zeile.addEventListener("click", () => {
        const idx = parseInt(zeile.dataset.zutatIdx, 10);
        zutatStatus[idx].ausgewaehlt = !zutatStatus[idx].ausgewaehlt;
        _renderSheet(); // neu rendern mit aktualisiertem State
      });
    });

    // Bestätigen-Button (ESSEN-30 Bestätigungs-Pfad)
    const bestBtn = inhalt.querySelector("#sheet-bestaetigen");
    if (bestBtn && !bestBtn.disabled) {
      bestBtn.addEventListener("click", async () => {
        schliesseSheet();
        await _uebernahmePfad(gericht, zutatStatus);
      });
    }

    // Nur abhaken
    inhalt.querySelector("#sheet-nur-abhaken").addEventListener("click", async () => {
      schliesseSheet();
      await toggleAbgehakt(gericht);
    });

    // Abbrechen
    inhalt.querySelector("#sheet-abbrechen").addEventListener("click", schliesseSheet);
  }

  _renderSheet();
  oeffneSheetOverlay();
}

/**
 * ESSEN-30 Bestätigungs-Pfad: N POSTs + optionale PATCHes + abgehakt=true auf Gericht.
 *
 * Dedupe-Regel (ESSEN-30):
 *   - Zutat schon offen auf Liste (label-Match) UND aus_gericht noch leer
 *     → PATCH aus_gericht auf bestehende ID statt POST.
 *   - aus_gericht schon gesetzt → idempotent, gar kein Effekt.
 */
async function _uebernahmePfad(gericht, zutatStatus) {
  const ausgewaehlt = zutatStatus.filter(s => s.ausgewaehlt);
  const offeneItems = _liste.filter(i => !i.abgehakt);

  let fehler = 0;

  for (const s of ausgewaehlt) {
    const z = s.zutat;
    const zLabelNorm = z.label.toLowerCase().trim();

    // Dedupe: bestehendes Item mit gleichem Label suchen
    const vorhandenes = offeneItems.find(
      i => i.label.toLowerCase().trim() === zLabelNorm
    );

    if (vorhandenes) {
      if (!vorhandenes.aus_gericht) {
        // PATCH aus_gericht auf bestehendes Item (ESSEN-30 Dedupe)
        try {
          await patchAusGericht(vorhandenes.id, gericht.label);
        } catch (err) {
          fehler++;
          console.error("uebernahmePfad PATCH aus_gericht Fehler:", err);
        }
      }
      // aus_gericht schon gesetzt → idempotent, gar kein Effekt
      continue;
    }

    // Neu anlegen (ESSEN-30 POST)
    const payload = {
      label:      z.label,
      bild_ref:   z.bild_ref,
      quelle:     "eltern",
      klasse:     "einkauf",
      kategorie:  z.kategorie,
      item_id:    z.id || z.label,
      aus_gericht: gericht.label,
    };
    const resp = await postItem(payload);
    if (!resp.ok && resp.status !== 409) {
      fehler++;
      console.error("uebernahmePfad POST Fehler:", resp.status);
    }
  }

  // Wunsch-Gericht auf abgehakt=true (ESSEN-30 Schritt 3)
  try {
    await patchAbgehakt(gericht.id, true);
  } catch (err) {
    console.error("uebernahmePfad abgehakt Fehler:", err);
  }

  if (fehler > 0) {
    zeigeToast(fehler + " Zutat(en) konnten nicht hinzugefügt werden.");
  }

  await ladeUndRendere();
}

// ── Quick-Add Sheet (ESSEN-31) ────────────────────────────────────────────────

/**
 * Quick-Add-Bottom-Sheet öffnen.
 * ESSEN-31: Komma-/Semikolon-getrennte Items, Auto-Match auf Katalog.
 */
async function oeffneQuickAddSheet() {
  // Katalog für Auto-Match vorladen
  let katalogItems = [];
  try {
    const katalog = await holeKatalog();
    for (const kat of Object.values(katalog.kategorien || {})) {
      katalogItems = katalogItems.concat(kat);
    }
  } catch (_) {
    // kein Katalog → kein Auto-Match, Fallback auf sonstiges
  }

  const inhalt = document.getElementById("sheet-inhalt");
  inhalt.innerHTML =
    '<p class="sheet-titel">➕ Schnell hinzufügen</p>' +
    '<input type="text" class="quick-add-input" id="quick-add-text" ' +
           'placeholder="Milch, Butter; Eier" autocomplete="off" autofocus>' +
    '<p class="quick-add-hinweis">Mehrere Items mit Komma oder Semikolon trennen.</p>' +
    '<div class="sheet-btn-gruppe">' +
      '<button class="sheet-btn sheet-btn-primary" id="quick-add-btn">Auf die Liste</button>' +
      '<button class="sheet-btn sheet-btn-ghost" id="quick-add-abbrechen">Abbrechen</button>' +
    '</div>';

  document.getElementById("quick-add-btn").addEventListener("click", async () => {
    const eingabe = document.getElementById("quick-add-text").value;
    const tokens = tokenisiereQuickAdd(eingabe);
    if (tokens.length === 0) return;

    schliesseSheet();
    await _quickAddSenden(tokens, katalogItems);
  });

  document.getElementById("quick-add-abbrechen").addEventListener("click", schliesseSheet);

  // Enter-Taste im Input
  document.getElementById("quick-add-text").addEventListener("keydown", e => {
    if (e.key === "Enter") document.getElementById("quick-add-btn").click();
  });

  oeffneSheetOverlay();
  // Focus auf Input nach kurzer Verzögerung (Sheet-Animation)
  setTimeout(() => document.getElementById("quick-add-text")?.focus(), 80);
}

/**
 * Zerlegt Quick-Add-Eingabe in Token-Array.
 * ESSEN-31: Komma und Semikolon als Trennzeichen; leere Tokens ignoriert.
 */
function tokenisiereQuickAdd(eingabe) {
  return (eingabe || "")
    .split(/[,;]+/)
    .map(s => s.trim())
    .filter(s => s.length > 0);
}

/**
 * Sendet Quick-Add-Items als POSTs.
 * ESSEN-31: Auto-Match auf Katalog (label case-insensitiv).
 */
async function _quickAddSenden(tokens, katalogItems) {
  let fehler = 0;

  for (const token of tokens) {
    // Auto-Match: Katalog-Item mit gleichem Label finden (case-insensitiv)
    const match = katalogItems.find(
      ki => ki.label?.toLowerCase().trim() === token.toLowerCase().trim()
    );

    const payload = {
      label:     match ? match.label : token,
      bild_ref:  match ? match.bild_ref : "0",  // 0 = ARASAAC-Placeholder
      quelle:    "eltern",
      klasse:    "einkauf",
      kategorie: match ? match.kategorie : "sonstiges",
      item_id:   match ? (match.id || token) : token,
    };

    const resp = await postItem(payload);
    if (!resp.ok && resp.status !== 409) {
      fehler++;
      console.error("quickAdd POST Fehler:", resp.status, token);
    }
  }

  if (fehler > 0) {
    zeigeToast(fehler + " Item(s) konnten nicht hinzugefügt werden.");
  }

  await ladeUndRendere();
}

// ── Sheet-Overlay ─────────────────────────────────────────────────────────────

function oeffneSheetOverlay() {
  const overlay = document.getElementById("sheet-overlay");
  overlay.hidden = false;

  // Overlay-Klick schließt Sheet
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) schliesseSheet();
  }, { once: true });
}

function schliesseSheet() {
  const overlay = document.getElementById("sheet-overlay");
  overlay.hidden = true;
  const inhalt = document.getElementById("sheet-inhalt");
  inhalt.innerHTML = "";
}

// ── Hilfs-Funktionen ──────────────────────────────────────────────────────────

/**
 * HTML-Escaping (verhindert XSS aus API-Daten).
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
  module.exports = { tokenisiereQuickAdd, sektionHeader, erledigtSektionHeader, _marker, _itemRangfolge };
}
