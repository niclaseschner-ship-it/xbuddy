/**
 * mini-app-uebersicht.js — MAU-Mini-App-Frontend (DUMME VIEW, #1210).
 *
 * #1210 (Daten-SSoT): Diese Datei holt den EINEN angereicherten Layout-Kontrakt
 * von GET /api/v1/seiten/layout (render.baue_layout) und RENDERT NUR. Sie
 * gruppiert/anreichert NICHTS mehr lokal — die Buddy-Gruppen und die
 * Origin-URLs kommen fertig aus dem Server (dieselbe Ableitung, die der
 * Jinja-Pfad /uebersicht rendert). So koennen die zwei Oberflaechen nicht
 * mehr driften. Abweichende Sichten filtern DEKLARATIV ueber das
 * `audience`-Feld je Karte.
 *
 * RAT-31 E3 (#1496): rendereGeraetePaare entfernt (Sorten d/e weg;
 * hero_paare ist immer [] im Kontrakt).
 *
 * MAU-4: zwei Accordion-Sektionen (mini_apps, buddy_gruppen).
 * MAU-5: Mini-App-Kachel-Tap → t.me-Deep-Link via openTelegramLink; Fallback funnel.
 * MAU-6: URL-Karten — Oeffnen via platform.openLink; Kopieren via platform.copyText + Toast.
 * MAU-8: Loading-State, 401-Fehler, 5xx-Fehler, snapshot_pending-Banner.
 * MAD-5: kein direktes Telegram.WebApp (ausser openTelegramLink/close) — alles ueber platform.js.
 * MAD-7: initData aus Telegram.WebApp.initData als Authorization-Header bei API-Call.
 */

"use strict";

// Deklarative Audience-Tokens (Spiegel zu seiten/render.py AUDIENCE_*).
const AUDIENCE_MINI_APP = "mini-app-uebersicht";

// Fallback-Icons je (Roh-)Typ, wenn der Eintrag kein icons[] traegt.
const _TYP_FALLBACK_EMOJI = {
  "display":         "📺",
  "display-client":  "📺",
  "panel":           "📱",
  "eltern":          "📄",
  "controller":      "🎛️",
  "mini-app":        "🟦",
  "shell":           "🖥️",
};

// Menschenlesbares Typ-Badge je Roh-Typ (nur Praesentation).
const _TYP_BADGE = {
  "display":         "Display",
  "display-client":  "Display-Client",
  "panel":           "Panel",
  "eltern":          "Eltern",
  "controller":      "Controller",
  "mini-app":        "Mini-App",
  "shell":           "Shell",
};

/**
 * Loest den Icon-Verweis einer Kontrakt-Karte auf.
 * baue_layout liefert `icon` bereits fertig (ARASAAC-Pfad oder Fallback-PNG).
 */
function _iconRef(card) {
  return (card && card.icon) || null;
}

/**
 * Baut eine URL-Karte (MAU-6): Icon + Label + Typ-Badge + URL-Mono + Oeffnen/Kopieren.
 * `rawTyp` (Kontrakt-`typ`) + `url` landen als data-Attribute — der Parity-Guard
 * (render_parity_dom.test.js) liest sie zur Mengen-/URL-Wert-Pruefung aus.
 * t.me/-URLs oeffnen via openTelegramLink (Mini-App-zu-Mini-App im Overlay).
 */
function _bauUrlKarte(platform, zeigeToast, label, typBadge, url, iconRef, rawTyp) {
  const karte = _doc().createElement("div");
  karte.className = "url-karte";
  karte.dataset.kartenTyp = rawTyp || "";
  karte.dataset.url = url || "";

  const kopfzeile = _doc().createElement("div");
  kopfzeile.className = "url-karte-kopfzeile";

  if (iconRef) {
    const ikon = _doc().createElement("img");
    ikon.className = "url-karte-icon";
    ikon.src = iconRef;
    ikon.alt = "";
    ikon.loading = "lazy";
    kopfzeile.appendChild(ikon);
  } else if (_TYP_FALLBACK_EMOJI[rawTyp]) {
    const ikonText = _doc().createElement("span");
    ikonText.className = "url-karte-icon-fallback";
    ikonText.textContent = _TYP_FALLBACK_EMOJI[rawTyp];
    ikonText.setAttribute("aria-hidden", "true");
    kopfzeile.appendChild(ikonText);
  }

  const labelEl = _doc().createElement("span");
  labelEl.className = "url-karte-label";
  labelEl.textContent = label;

  const typEl = _doc().createElement("span");
  typEl.className = "url-karte-typ";
  typEl.textContent = typBadge;

  kopfzeile.appendChild(labelEl);
  kopfzeile.appendChild(typEl);

  const urlEl = _doc().createElement("code");
  urlEl.className = "url-mono";
  urlEl.textContent = url;

  const btnGruppe = _doc().createElement("div");
  btnGruppe.className = "url-btn-gruppe";

  const _istTelegramDeepLink = url && url.indexOf("https://t.me/") === 0;

  const btnOeffnen = _doc().createElement("button");
  btnOeffnen.className = "url-btn url-btn-primary";
  btnOeffnen.textContent = "🔗 Oeffnen";
  btnOeffnen.setAttribute("aria-label", "Oeffnen: " + url);
  btnOeffnen.addEventListener("click", () => {
    if (_istTelegramDeepLink) {
      try {
        window.Telegram.WebApp.openTelegramLink(url);
        return;
      } catch (e) {
        // Fallback unten
      }
    }
    platform.openLink(url);
  });

  const btnKopieren = _doc().createElement("button");
  btnKopieren.className = "url-btn";
  btnKopieren.textContent = "📋 Kopieren";
  btnKopieren.setAttribute("aria-label", "URL kopieren: " + url);
  btnKopieren.addEventListener("click", () => {
    const ok = platform.copyText(url);
    if (ok) {
      zeigeToast("Link kopiert", false);
    } else {
      zeigeToast("Kopieren ging nicht — oeffne im Browser", true);
      platform.openLink(url);
    }
  });

  btnGruppe.appendChild(btnOeffnen);
  btnGruppe.appendChild(btnKopieren);

  karte.appendChild(kopfzeile);
  karte.appendChild(urlEl);
  karte.appendChild(btnGruppe);
  return karte;
}

/**
 * Emittiert je vorhandener Origin (Heim + Tailscale) eine URL-Karte fuer eine
 * Kontrakt-Karte. Beide Origins kommen fertig aus dem Kontrakt (card.urls) —
 * KEINE lokale URL-Bildung mehr (fruehere Drift-Quelle: window.location.origin).
 * Das spiegelt die Grossbild-Uebersicht (SREG-12: beide kopierbaren URLs).
 */
function _emitViewKarten(platform, zeigeToast, container, card, opts) {
  const o = opts || {};
  const label = o.label || card.label || "";
  const rawTyp = o.rawTyp || card.typ || "";
  const badge = o.badge || _TYP_BADGE[rawTyp] || "Seite";
  const iconRef = _iconRef(card);
  const urls = card.urls || {};
  if (urls.heim) {
    container.appendChild(_bauUrlKarte(
      platform, zeigeToast, label, badge, urls.heim, iconRef, rawTyp));
  }
  if (urls.tailscale) {
    container.appendChild(_bauUrlKarte(
      platform, zeigeToast, label, badge, urls.tailscale, iconRef, rawTyp));
  }
}

// ── Sektion 1: Mini Telegram Apps (MAU-4 Punkt 1) ───────────────────────────

/**
 * DUMM: rendert die vom Server vorberechnete mini_apps-Liste (SREG-14).
 * URL = web_app_url (t.me-Deep-Link) mit Fallback funnel_url.
 */
function rendereMinApps(platform, zeigeToast, container, miniApps) {
  if (!miniApps || !miniApps.length) {
    const leer = _doc().createElement("p");
    leer.className = "leer-hinweis";
    leer.textContent = "Keine Mini-Apps gefunden.";
    container.appendChild(leer);
    return;
  }
  for (const app of miniApps) {
    const url = app.web_app_url || app.funnel_url || "";
    container.appendChild(_bauUrlKarte(
      platform, zeigeToast, app.label, "Mini-App", url, _iconRef(app), app.typ));
  }
}

// ── Sektion 2: Buddy-Seiten (MAU-4 Punkt 2) ─────────────────────────────────

/**
 * DUMM: rendert die vom Server vorgruppierten buddy_gruppen
 * (render.py::_buddy_gruppen). KEINE lokale Gruppierung/Sortierung mehr.
 * Deklarativer Audience-Filter: Karten, deren `audience` diese Oberflaeche
 * nicht enthaelt (z.B. Mini-Apps — die stehen in Sektion 1), werden
 * uebersprungen. Das ersetzt geforkten Ableitungscode (#1210 / SREG-15).
 */
function rendereBuddySeiten(platform, zeigeToast, container, buddyGruppen) {
  const sichtbar = [];
  for (const gruppe of (buddyGruppen || [])) {
    const karten = (gruppe.karten || []).filter(_sichtbarHier);
    if (karten.length) sichtbar.push({ gruppe, karten });
  }

  if (!sichtbar.length) {
    const leer = _doc().createElement("p");
    leer.className = "leer-hinweis";
    leer.textContent = "Keine Buddy-Seiten gefunden.";
    container.appendChild(leer);
    return;
  }

  for (const { gruppe, karten } of sichtbar) {
    const gruppeEl = _doc().createElement("div");
    gruppeEl.className = "buddy-gruppe";

    const gruppeLabel = _doc().createElement("div");
    gruppeLabel.className = "buddy-gruppe-label";
    gruppeLabel.textContent = gruppe.app;
    gruppeEl.appendChild(gruppeLabel);

    const kartenContainer = _doc().createElement("div");
    kartenContainer.className = "buddy-gruppe-karten";
    for (const card of karten) {
      _emitViewKarten(platform, zeigeToast, kartenContainer, card, {});
    }
    gruppeEl.appendChild(kartenContainer);
    container.appendChild(gruppeEl);
  }
}

/** Deklarativer Audience-Test: rendert diese Oberflaeche (mini-app) die Karte? */
function _sichtbarHier(card) {
  const audience = card && card.audience;
  // Ohne audience-Feld: konservativ rendern (Rueckwaerts-Kompatibilitaet).
  if (!Array.isArray(audience)) return true;
  return audience.indexOf(AUDIENCE_MINI_APP) !== -1;
}

// ── document-Zugriff (Test-Naht) ────────────────────────────────────────────
// _bauUrlKarte & Co. greifen ueber _doc() auf document zu, damit der Node-Test
// (kein globales document im require-Moment noetig) es spaet aufloest.
function _doc() {
  return (typeof document !== "undefined") ? document : global.document;
}

// ════════════════════════════════════════════════════════════════════════════
//  IIFE — Browser-Bootstrap (im Node-Test via module.exports uebersprungen)
// ════════════════════════════════════════════════════════════════════════════

async function boot() {
  const platform = getPlatform();
  await platform.ready();

  // MAD-11: JS-Side-Auth-Probe (HTML-Route public — Skeleton laedt ohne Auth).
  if (!(await platform.ensureAuth())) {
    document.body.innerHTML = '<div style="padding:2rem;text-align:center;font-family:system-ui;color:#666;font-size:1rem">Bitte über den Familien-Bot öffnen (initData fehlt oder ist ungültig).</div>';
    return;
  }

  // RAT-31 E3 (#1496): sec-geraete-paare entfernt (hero_paare immer []).
  const secMiniApps    = document.getElementById("sec-mini-apps");
  const secBuddySeiten = document.getElementById("sec-buddy-seiten");
  const hauptInhalt    = document.getElementById("uebersicht-inhalt");
  const fehlerBanner   = document.getElementById("fehler-banner");
  const fehlerText     = document.getElementById("fehler-text");
  const btnSchliessen  = document.getElementById("btn-schliessen");
  const btnRetry       = document.getElementById("btn-retry");
  const snapshotBanner = document.getElementById("snapshot-banner");
  const toast          = document.getElementById("toast");

  let _toastTimer = null;
  function zeigeToast(text, istFehler) {
    toast.textContent = text;
    toast.className = "toast" + (istFehler ? " toast-fehler" : "");
    requestAnimationFrame(() => { toast.classList.add("sichtbar"); });
    if (_toastTimer) clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => { toast.classList.remove("sichtbar"); }, 2800);
  }

  function _getInitData() {
    try {
      return (window.Telegram && window.Telegram.WebApp)
        ? window.Telegram.WebApp.initData || ""
        : "";
    } catch (e) {
      return "";
    }
  }

  // #1210: EINE Quelle — der angereicherte Layout-Kontrakt (SSoT).
  async function ladeLayout() {
    const initData = _getInitData();
    const headers = initData ? { "Authorization": "tma " + initData } : {};
    const resp = await fetch("/api/v1/seiten/layout", { headers });
    if (resp.status === 401) {
      throw Object.assign(new Error("auth"), { code: 401 });
    }
    if (!resp.ok) {
      throw Object.assign(new Error("netz"), { code: resp.status });
    }
    return resp.json();
  }

  function zeigeFehler(code) {
    if (code === 401) {
      fehlerText.textContent = "Bitte App neu oeffnen — Auth abgelaufen.";
      btnSchliessen.hidden = false;
      btnRetry.hidden = true;
      btnSchliessen.onclick = () => {
        try { window.Telegram.WebApp.close(); } catch (e) { window.close(); }
      };
    } else {
      fehlerText.textContent = "Uebersicht nicht erreichbar.";
      btnSchliessen.hidden = true;
      btnRetry.hidden = false;
      btnRetry.onclick = () => {
        fehlerBanner.hidden = true;
        if (hauptInhalt) {
          hauptInhalt.innerHTML = "<p class=\"lade-hinweis\">Uebersicht wird geladen …</p>";
        }
        startLaden();
      };
    }
    fehlerBanner.hidden = false;
  }

  function rendereLayout(layout) {
    if ((layout.snapshot_pending || []).length > 0) {
      snapshotBanner.hidden = false;
    }
    const body1 = secMiniApps.querySelector(".accordion-body");
    body1.innerHTML = "";
    rendereMinApps(platform, zeigeToast, body1, layout.mini_apps || []);

    // RAT-31 E3 (#1496): Geraete-Paare-Sektion entfernt (hero_paare immer []).
    const body3 = secBuddySeiten.querySelector(".accordion-body");
    body3.innerHTML = "";
    rendereBuddySeiten(platform, zeigeToast, body3, layout.buddy_gruppen || []);
  }

  async function startLaden() {
    try {
      const layout = await ladeLayout();
      rendereLayout(layout);
    } catch (err) {
      zeigeFehler(err.code || 0);
    }
  }

  await startLaden();
}

// Browser: sofort booten. Node-Test: nur die reinen Renderer exportieren.
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    rendereMinApps,
    rendereBuddySeiten,
    _bauUrlKarte,
    _emitViewKarten,
    _sichtbarHier,
    AUDIENCE_MINI_APP,
  };
} else {
  boot();
}
