/**
 * eltern.js — Hörspiel-Eltern-Mini-App Frontend-Logik.
 *
 * HSP-33: Tab-Hash-Reader + hashchange-Listener. Zwei Tabs: Einstellungen / Folgen.
 * HSP-34: Reiter Einstellungen (5 Steuer-Elemente + Speichern + Toast).
 * HSP-35: Reiter Folgen — aggregierte Liste über alle V1-kind_ids (paula+neko),
 *          sortiert nach erstellt-am desc. Avatar (FAM-8) pro Eintrag.
 *          Player öffnet folge.kind_id-Manifest, nicht URL-KIND_ID. (#973)
 *          Wake-Lock, Auto-Play nächster Track, Resume-Stand.
 * MAD-5 (ratifiziert): kein direktes window.Telegram.WebApp.* — nur platform.* erlaubt.
 * MAD-7 (ratifiziert): Authorization: tma <initData>-Header bei jedem fetch().
 * T970 / HSP-26 / URL-3a: kind_id aus location.pathname → Settings-Tab kind_id-tragend.
 */

/* global getPlatform */

// ── KIND_ID aus URL (HSP-26, URL-3a, T970) ──────────────────────────────────
// Pattern: /seiten/hoerspiel/<kind_id>/eltern → kind_id ist Segment 3 (0-basiert).
// Fallback: 'paula' für Dev/Standalone (nie im Produktivbetrieb wirksam).
// Settings-Tab (HSP-34) nutzt KIND_ID weiterhin für /config-Endpoint.
const KIND_ID = (() => {
  const m = location.pathname.match(/^\/seiten\/hoerspiel\/([^/]+)\/eltern/);
  return m ? m[1] : 'paula';
})();

// ── KIND_IDS_V1: Instanz-Liste aus window.__HSP_INSTANZEN__ (INST-1, #1670) ──
// Treibt Folgen-Tab-Aggregation. Quelle: server-injizierter Blob (seiten-View,
// analog player.js HSP-49). Kein Hardcode mehr — letzte HSP-Slug-Kopie entfernt.
// Shape: window.__HSP_INSTANZEN__ = [{kind_id, name, foto_url}] (volle Objekte,
// gleiche Form wie player.js); eltern.js braucht nur Slugs → .map(e=>e.kind_id).
// Fallback ["paula","neko","niclas"] greift wenn Injektion fehlt (Dev/Standalone).
const KIND_IDS_V1 = (
  Array.isArray(window.__HSP_INSTANZEN__) && window.__HSP_INSTANZEN__.length > 0
    ? window.__HSP_INSTANZEN__.map(e => e.kind_id)
    : ["paula", "neko", "niclas"]
);

// ── MAD-7 Auth-Header ────────────────────────────────────────────────────────
// initData aus Telegram-WebApp — bei jedem fetch()-Call als Header gesendet.
const _initData = window.Telegram?.WebApp?.initData ?? "";

// ── State ────────────────────────────────────────────────────────────────────
let _serverConfig = {};        // Letzter Stand von GET /config
let _editConfig = {};          // Edit-Kopie für Diff-Prüfung
let _albenListe = [];          // Cache GET /alben
let _aktivesAlbum = null;      // {manifest: {...}, ...}
let _aktiverTrackIdx = 0;      // Index in manifest.tracks[]
let _audio = null;             // HTMLAudioElement
let _wakeLock = null;          // WakeLockSentinel | null
let _trackListeOffen = false;  // Toggle-Zustand

// ── Einstiegspunkt ───────────────────────────────────────────────────────────
(async function main() {
  const platform = getPlatform();
  await platform.ready();

  // MAD-11: JS-Side-Auth-Probe (HTML-Route ist public — Skeleton lädt ohne Auth,
  // hier prüft JS, ob valide initData für die API-Aufrufe vorliegt).
  if (!(await platform.ensureAuth())) {
    document.body.innerHTML = '<div style="padding:2rem;text-align:center;font-family:system-ui;color:#666;font-size:1rem">Bitte über den Familien-Bot öffnen (initData fehlt oder ist ungültig).</div>';
    return;
  }

  // HSP-33: Tab beim Laden aus URL-Hash bestimmen (Default: einstellungen).
  _wechselZuTab(_leseHashTab());

  // hashchange-Listener (HSP-33): Tab ohne Seiten-Reload wechseln.
  window.addEventListener("hashchange", () => {
    _wechselZuTab(_leseHashTab());
  });

  // Einstellungen sofort laden (Default-Tab).
  await _ladeEinstellungen();

  // Tab-Button-Click-Handler.
  document.getElementById("tab-einstellungen").addEventListener("click", () => {
    _setzeHash("einstellungen");
  });
  document.getElementById("tab-folgen").addEventListener("click", async () => {
    _setzeHash("folgen");
    if (_albenListe.length === 0) {
      await _ladeAlbenListe();
    }
  });
})();

// ── Hash-Helpers (HSP-33) ────────────────────────────────────────────────────

/**
 * Liest das aktuelle URL-Hash-Fragment und gibt den Tab-Key zurück.
 * Unbekannter oder fehlender Hash → "einstellungen" (Default).
 */
function _leseHashTab() {
  const hash = (window.location.hash || "").replace(/^#/, "").toLowerCase().trim();
  return hash === "folgen" ? "folgen" : "einstellungen";
}

/**
 * Setzt das Hash-Fragment der URL (löst hashchange aus).
 */
function _setzeHash(tab) {
  window.location.hash = tab;
}

/**
 * Schaltet das UI auf den angegebenen Tab um.
 * @param {"einstellungen"|"folgen"} tab
 */
function _wechselZuTab(tab) {
  const panels = { einstellungen: "panel-einstellungen", folgen: "panel-folgen" };
  const tabs = { einstellungen: "tab-einstellungen", folgen: "tab-folgen" };

  for (const [key, panelId] of Object.entries(panels)) {
    const panel = document.getElementById(panelId);
    const btn = document.getElementById(tabs[key]);
    const aktiv = (key === tab);
    if (panel) panel.hidden = !aktiv;
    if (btn) btn.setAttribute("aria-selected", aktiv ? "true" : "false");
  }
}

// ── API-Calls ────────────────────────────────────────────────────────────────

function _authHeader() {
  return { "Authorization": "tma " + _initData };
}

async function _holeConfig() {
  const resp = await fetch("/api/v1/hoerspiel/" + KIND_ID + "/config", {
    headers: _authHeader(),
  });
  if (!resp.ok) throw new Error("config-Abruf fehlgeschlagen: " + resp.status);
  return resp.json();
}

async function _patchConfig(patch) {
  const resp = await fetch("/api/v1/hoerspiel/" + KIND_ID + "/config", {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ..._authHeader() },
    body: JSON.stringify(patch),
  });
  return resp;
}

// HSP-34 — parallele PATCH-Helfer über alle V1-Kinder (KIND_IDS_V1).
// _holeBeideConfigs entfernt (#1491, war nach audio_ziel-Rückbau #1471 aufruferlos).

async function _patchBeideConfigs(patch) {
  const results = await Promise.allSettled(
    KIND_IDS_V1.map(kindId =>
      fetch("/api/v1/hoerspiel/" + kindId + "/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ..._authHeader() },
        body: JSON.stringify(patch),
      }).then(async r => ({ ok: r.ok, status: r.status,
                            body: await r.json().catch(() => ({})) }))
    )
  );
  const map = {};
  KIND_IDS_V1.forEach((kindId, i) => {
    const r = results[i];
    map[kindId] = (r.status === "fulfilled") ? r.value
                                              : { ok: false, status: 0, body: { fehler: String(r.reason) } };
  });
  return map;
}

async function _holeAlben(kindId) {
  const resp = await fetch("/api/v1/hoerspiel/" + kindId + "/alben", {
    headers: _authHeader(),
  });
  if (!resp.ok) throw new Error("alben-Abruf fehlgeschlagen: " + resp.status);
  return resp.json();
}

async function _holeManifest(kindId, albumId) {
  const resp = await fetch(
    "/api/v1/hoerspiel/" + kindId + "/alben/" + encodeURIComponent(albumId) + "/manifest", {
    headers: _authHeader(),
  });
  if (!resp.ok) throw new Error("manifest-Abruf fehlgeschlagen: " + resp.status);
  return resp.json();
}

async function _holeResume(kindId, albumId) {
  const resp = await fetch(
    "/api/v1/hoerspiel/" + kindId + "/resume?album=" + encodeURIComponent(albumId), {
    headers: _authHeader(),
  });
  if (!resp.ok) return null;
  const data = await resp.json();
  // Backend gibt status: "neu" zurück wenn kein Stand existiert (HSP-36); Aufrufer behandelt das als null.
  if (data.status === 'neu') return null;
  return data;
}

async function _setzeResume(kindId, albumId, trackPos) {
  await fetch("/api/v1/hoerspiel/" + kindId + "/resume", {
    method: "PUT",
    headers: { "Content-Type": "application/json", ..._authHeader() },
    body: JSON.stringify({ album: albumId, track: trackPos }),
  });
}

// ── Reiter Einstellungen (HSP-34) ────────────────────────────────────────────

/** Kind-Name für Anzeige (Capitalize der kind_id, HSP-43 generisch). */
function _kindName(kindId) {
  return String(kindId || "").charAt(0).toUpperCase() + String(kindId || "").slice(1);
}

async function _ladeEinstellungen() {
  const container = document.getElementById("panel-einstellungen");
  try {
    const config = await _holeConfig();
    _serverConfig = config;
    _editConfig = { ...config };

    _rendereEinstellungen(container, config);
  } catch (err) {
    container.innerHTML = '<p class="lade-hinweis">Einstellungen konnten nicht geladen werden.</p>';
    console.error("eltern.js: Einstellungen Ladefehler", err);
  }
}

function _rendereEinstellungen(container, config) {
  // Edit-State aus aktuellem Config initialisieren.
  _editConfig = {
    playback_tempo: config.playback_tempo ?? 1.0,
    pause_absatz_sek: config.pause_absatz_sek ?? 0.55,
    pause_titel_sek: config.pause_titel_sek ?? 1.8,
    default_voice: config.default_voice ?? "shimmer",
    llm_provider: config.llm_provider ?? "claude",
    llm_model: config.llm_model ?? "",
  };

  const providerVerfuegbar = config.provider_verfuegbar || [];
  const modelleJeAnbieter = config.modelle_je_anbieter || {};
  const voicesVerfuegbar = config.voices_verfuegbar || ["shimmer", "onyx"];

  // Voice-Kacheln HTML
  const voiceKachelnHtml = voicesVerfuegbar.map(v => {
    const pressed = (v === _editConfig.default_voice) ? "true" : "false";
    const label = v === "shimmer" ? "Shimmer (weich)" : v === "onyx" ? "Onyx (tief)" : esc(v);
    return '<button type="button" class="voice-kachel" data-voice="' + esc(v) + '" ' +
           'aria-pressed="' + pressed + '">' + label + '</button>';
  }).join("");

  // Anbieter-Dropdown
  const anbieterOptions = providerVerfuegbar.map(p => {
    const sel = (p === _editConfig.llm_provider) ? " selected" : "";
    return '<option value="' + esc(p) + '"' + sel + '>' + esc(p) + '</option>';
  }).join("");

  // Modell-Dropdown (passend zu aktivem Anbieter)
  const modelleDesAnbieters = modelleJeAnbieter[_editConfig.llm_provider] || [];
  const modellOptions = modelleDesAnbieters.map(m => {
    const sel = (m.id === _editConfig.llm_model) ? " selected" : "";
    return '<option value="' + esc(m.id) + '"' + sel + '>' + esc(m.label) + '</option>';
  }).join("");

  container.innerHTML =
    // Playback-Tempo (0.7–1.3, Schritt 0.05)
    '<div class="einstellung-karte">' +
      '<div class="einstellung-label">Playback-Tempo</div>' +
      '<div class="einstellung-wert">Wiedergabe-Geschwindigkeit beim Kind</div>' +
      '<input type="range" class="einstellung-slider" id="slider-tempo" ' +
             'min="0.7" max="1.3" step="0.05" value="' + esc(String(_editConfig.playback_tempo)) + '">' +
      '<div class="slider-wert" id="wert-tempo">' + esc(String(_editConfig.playback_tempo)) + '×</div>' +
    '</div>' +

    // Pause nach Absatz (0.0–2.0, Schritt 0.05)
    '<div class="einstellung-karte">' +
      '<div class="einstellung-label">Pause nach Absatz</div>' +
      '<div class="einstellung-wert">Stille zwischen Inhalts-Absätzen (s)</div>' +
      '<input type="range" class="einstellung-slider" id="slider-absatz" ' +
             'min="0.0" max="2.0" step="0.05" value="' + esc(String(_editConfig.pause_absatz_sek)) + '">' +
      '<div class="slider-wert" id="wert-absatz">' + esc(String(_editConfig.pause_absatz_sek)) + ' s</div>' +
    '</div>' +

    // Pause nach Titel (0.5–3.0, Schritt 0.1)
    '<div class="einstellung-karte">' +
      '<div class="einstellung-label">Pause nach Titel</div>' +
      '<div class="einstellung-wert">Stille nach Folgen-Titel-Absatz (s)</div>' +
      '<input type="range" class="einstellung-slider" id="slider-titel" ' +
             'min="0.5" max="3.0" step="0.1" value="' + esc(String(_editConfig.pause_titel_sek)) + '">' +
      '<div class="slider-wert" id="wert-titel">' + esc(String(_editConfig.pause_titel_sek)) + ' s</div>' +
    '</div>' +

    // Stimme (2-Kachel-Wahl)
    '<div class="einstellung-karte">' +
      '<div class="einstellung-label">Stimme</div>' +
      '<div class="voice-kacheln" id="voice-kacheln">' + voiceKachelnHtml + '</div>' +
    '</div>' +

    // LLM (Anbieter + Modell)
    (providerVerfuegbar.length > 0 ?
    '<div class="einstellung-karte">' +
      '<div class="einstellung-label">LLM-Anbieter</div>' +
      '<select class="einstellung-select" id="select-anbieter">' + anbieterOptions + '</select>' +
      '<div class="einstellung-label" style="margin-top:10px;">Modell</div>' +
      '<select class="einstellung-select" id="select-modell">' + modellOptions + '</select>' +
    '</div>'
    : "") +

    // Hinweis-Block
    '<p class="einstellung-hinweis">Pausen, Stimme und Anbieter+Modell wirken bei der ' +
    '<strong>nächsten Folge</strong> — Playback-Tempo wirkt <strong>sofort</strong>, ' +
    'auch für bestehende Alben.</p>' +

    // Sticky Speichern-Knopf
    '<div class="speichern-footer">' +
      '<button type="button" class="speichern-btn" id="speichern-btn" disabled>Speichern</button>' +
    '</div>';

  // ── Event-Handler ─────────────────────────────────────────────────────────

  // Sliders
  const sliderTempo = document.getElementById("slider-tempo");
  const wertTempo = document.getElementById("wert-tempo");
  sliderTempo && sliderTempo.addEventListener("input", () => {
    const v = parseFloat(sliderTempo.value);
    _editConfig.playback_tempo = v;
    wertTempo.textContent = v.toFixed(2) + "×";
    // Playback-Tempo wirkt sofort auf laufenden Player.
    if (_audio) _audio.playbackRate = v;
    _aktualisiereSpeichernBtn();
  });

  const sliderAbsatz = document.getElementById("slider-absatz");
  const wertAbsatz = document.getElementById("wert-absatz");
  sliderAbsatz && sliderAbsatz.addEventListener("input", () => {
    const v = parseFloat(sliderAbsatz.value);
    _editConfig.pause_absatz_sek = v;
    wertAbsatz.textContent = v.toFixed(2) + " s";
    _aktualisiereSpeichernBtn();
  });

  const sliderTitel = document.getElementById("slider-titel");
  const wertTitel = document.getElementById("wert-titel");
  sliderTitel && sliderTitel.addEventListener("input", () => {
    const v = parseFloat(sliderTitel.value);
    _editConfig.pause_titel_sek = v;
    wertTitel.textContent = v.toFixed(2) + " s";
    _aktualisiereSpeichernBtn();
  });

  // Voice-Kacheln
  const voiceContainer = document.getElementById("voice-kacheln");
  voiceContainer && voiceContainer.addEventListener("click", (e) => {
    const btn = e.target.closest(".voice-kachel[data-voice]");
    if (!btn) return;
    _editConfig.default_voice = btn.dataset.voice;
    voiceContainer.querySelectorAll(".voice-kachel").forEach(b => {
      b.setAttribute("aria-pressed", b.dataset.voice === _editConfig.default_voice ? "true" : "false");
    });
    _aktualisiereSpeichernBtn();
  });

  // Anbieter-Dropdown → Modell-Dropdown neu befüllen
  const selectAnbieter = document.getElementById("select-anbieter");
  selectAnbieter && selectAnbieter.addEventListener("change", () => {
    const neuerAnbieter = selectAnbieter.value;
    _editConfig.llm_provider = neuerAnbieter;
    const modelle = modelleJeAnbieter[neuerAnbieter] || [];
    const selectModell = document.getElementById("select-modell");
    if (selectModell) {
      selectModell.innerHTML = modelle.map(m =>
        '<option value="' + esc(m.id) + '">' + esc(m.label) + '</option>'
      ).join("");
      _editConfig.llm_model = modelle.length > 0 ? modelle[0].id : "";
      selectModell.value = _editConfig.llm_model;
    }
    _aktualisiereSpeichernBtn();
  });

  const selectModell = document.getElementById("select-modell");
  selectModell && selectModell.addEventListener("change", () => {
    _editConfig.llm_model = selectModell.value;
    _aktualisiereSpeichernBtn();
  });

  // Speichern-Knopf
  const speichernBtn = document.getElementById("speichern-btn");
  speichernBtn && speichernBtn.addEventListener("click", _onSpeichern);
}

function _aktualisiereSpeichernBtn() {
  const btn = document.getElementById("speichern-btn");
  if (!btn) return;
  btn.disabled = !_hatDiff();
}

function _hatDiff() {
  const felder = ["playback_tempo", "pause_absatz_sek", "pause_titel_sek",
                  "default_voice", "llm_provider", "llm_model"];
  for (const k of felder) {
    if (String(_editConfig[k]) !== String(_serverConfig[k])) return true;
  }
  return false;
}

async function _onSpeichern() {
  const btn = document.getElementById("speichern-btn");
  if (btn) btn.disabled = true;

  // Nur geänderte Felder senden.
  const patchEinzeln = {};
  const felder = ["playback_tempo", "pause_absatz_sek", "pause_titel_sek",
                  "default_voice", "llm_provider", "llm_model"];
  for (const k of felder) {
    if (String(_editConfig[k]) !== String(_serverConfig[k])) {
      patchEinzeln[k] = _editConfig[k];
    }
  }

  try {
    if (Object.keys(patchEinzeln).length > 0) {
      const resp = await _patchConfig(patchEinzeln);
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        const msg = (body.fehler || body.error || ("Fehler " + resp.status));
        zeigeToast(msg, true);
        if (btn) btn.disabled = false;
        return;
      }
      const neueConfig = await resp.json();
      _serverConfig = neueConfig;
      _editConfig = { ...neueConfig };
    }

    zeigeToast("✓ Gespeichert — Playback-Tempo wirkt sofort, Stimme/Pausen/Modell ab nächster Folge.");
    if (btn) btn.disabled = true;
  } catch (err) {
    zeigeToast("Buddy nicht erreichbar — versuch es gleich nochmal.", true);
    if (btn) btn.disabled = false;
    console.error("eltern.js: Speichern-Fehler", err);
  }
}

// ── Reiter Folgen (HSP-35, #973) ────────────────────────────────────────────
// Aggregiert über alle V1-Kinder (KIND_IDS_V1). Jede Folge trägt ihre
// eigene kind_id im JS-State; Player öffnet folge.kind_id-Manifest.

/**
 * Mergt und sortiert Alben-Arrays aller KIND_IDS_V1 nach erstellt-am desc.
 * Jedes Album bekommt eine `kind_id`-Property für spätere API-Calls.
 * @param {Array<{kindId: string, alben: Array}>} alleAlben
 * @returns {Array} Gemergtes, sortiertes Array
 */
function _mergeUndSortiereAlben(alleAlben) {
  const merged = [];
  for (const { kindId, alben } of alleAlben) {
    for (const album of alben) {
      merged.push({ ...album, kind_id: kindId });
    }
  }
  // Sortierung: erstellt-am desc (neueste zuerst), dann nummer desc als Fallback.
  merged.sort((a, b) => {
    const da = a["erstellt-am"] || "";
    const db = b["erstellt-am"] || "";
    if (da > db) return -1;
    if (da < db) return 1;
    return (b.nummer || 0) - (a.nummer || 0);
  });
  return merged;
}

async function _ladeAlbenListe() {
  const container = document.getElementById("panel-folgen");
  const player = document.getElementById("folgen-player");
  const ladeHinweis = document.getElementById("folgen-ladehinweis");
  if (ladeHinweis) ladeHinweis.textContent = "Folgen werden geladen …";

  // HSP-35 / #975: Promise.allSettled — einseitiger 404 ergibt Partial-Result,
  // nicht komplette Liste leer. Fehlgeschlagene kind_ids → Warn-Banner (HSP-40).
  const settledErgebnisse = await Promise.allSettled(
    KIND_IDS_V1.map(async (kindId) => {
      const alben = await _holeAlben(kindId);
      return { kindId, alben };
    })
  );

  const erfolgreich = [];
  const fehlgeschlagen = [];
  settledErgebnisse.forEach((result, i) => {
    if (result.status === "fulfilled") {
      erfolgreich.push(result.value);
    } else {
      fehlgeschlagen.push(KIND_IDS_V1[i]);
      console.warn("eltern.js: Alben-Fetch für " + KIND_IDS_V1[i] + " fehlgeschlagen:", result.reason);
    }
  });

  _albenListe = _mergeUndSortiereAlben(erfolgreich);

  if (_albenListe.length === 0 && fehlgeschlagen.length === 0) {
    if (ladeHinweis) ladeHinweis.textContent = "Noch keine Folgen vorhanden.";
    return;
  }

  if (_albenListe.length === 0 && fehlgeschlagen.length > 0) {
    if (ladeHinweis) ladeHinweis.textContent = "Folgen konnten nicht geladen werden.";
    _rendereWarnBanner(container, player, fehlgeschlagen);
    return;
  }

  if (ladeHinweis) ladeHinweis.hidden = true;

  // Resume-Stände für alle Alben laden (parallel, je folge.kind_id).
  const resumeMap = {};
  await Promise.all(_albenListe.map(async (album) => {
    const r = await _holeResume(album.kind_id, album.id).catch(() => null);
    if (r) resumeMap[album.id] = r.track;
  }));

  _rendereAlbenListe(container, player, resumeMap);

  // HSP-40: Warn-Banner für fehlgeschlagene kind_ids am Listen-Ende.
  if (fehlgeschlagen.length > 0) {
    _rendereWarnBanner(container, player, fehlgeschlagen);
  }
}

/**
 * Fügt pro fehlgeschlagener kind_id einen Warn-Banner in den Folgen-Container ein.
 * HSP-40: "einseitiger 404 produziert teilweise Liste + Warn-Banner pro fehlgeschlagener kind_id".
 * @param {Element} container
 * @param {Element|null} player
 * @param {string[]} fehlgeschlageneKindIds
 */
function _rendereWarnBanner(container, player, fehlgeschlageneKindIds) {
  // Bestehende Warn-Banner entfernen (idempotent bei erneutem Aufruf).
  container.querySelectorAll(".album-warn-banner").forEach(b => b.remove());

  for (const kindId of fehlgeschlageneKindIds) {
    const banner = document.createElement("div");
    banner.className = "album-warn-banner";
    banner.textContent = kindId.charAt(0).toUpperCase() + kindId.slice(1) + "-Folgen aktuell nicht verfügbar";
    if (player && typeof container.insertBefore === "function") {
      container.insertBefore(banner, player);
    } else {
      container.appendChild(banner);
    }
  }
}

function _rendereAlbenListe(container, player, resumeMap) {
  // Bestehende Kacheln entfernen (aber player-div behalten).
  const alteKacheln = container.querySelectorAll(".album-kachel");
  alteKacheln.forEach(k => k.remove());

  // Kacheln einfügen vor dem Player.
  const insertTarget = player || null;

  for (const album of _albenListe) {
    const hatResume = Boolean(resumeMap[album.id]);
    const resumeHtml = hatResume
      ? '<span class="album-resume-badge">▶ ab Track ' + esc(String(resumeMap[album.id])) + '</span>'
      : "";

    // HSP-35 / #973: Kind-Avatar (FAM-8) pro Eintrag — selber URL-Mechanismus
    // wie Face-Pille in alben.html (HSP-3a, T911 Vorbild).
    // album.kind_id ist durch _mergeUndSortiereAlben garantiert gesetzt.
    const avatarHtml =
      '<img class="album-kind-avatar" src="' +
        esc("/api/v1/familie/foto/" + album.kind_id) +
        '" alt="' + esc(album.kind_id) + '" loading="lazy" ' +
        'onerror="this.style.display=\'none\'">';

    const kachelEl = document.createElement("div");
    kachelEl.className = "album-kachel";
    kachelEl.dataset.albumId = album.id;
    kachelEl.dataset.kindId = album.kind_id;
    kachelEl.innerHTML =
      '<img class="album-cover" src="' +
        esc(album["cover-asset"] || "") +
        '" alt="" loading="lazy" ' +
        'onerror="this.style.display=\'none\'">' +
      '<div class="album-info">' +
        '<div class="album-titel">Folge ' + esc(String(album.nummer || "")) + ' · ' + esc(album.titel || "") + '</div>' +
        '<div class="album-meta">' + esc(album.voice || "") + ' · ' + esc(album["erstellt-am"] || "") + '</div>' +
      '</div>' +
      avatarHtml +
      resumeHtml;

    kachelEl.addEventListener("click", () => {
      // #973: Player öffnet folge.kind_id-Manifest, nicht URL-KIND_ID.
      _oeffneAlbum(album.kind_id, album.id, resumeMap[album.id] || null);
    });

    if (insertTarget) {
      container.insertBefore(kachelEl, insertTarget);
    } else {
      container.appendChild(kachelEl);
    }
  }

  if (player) player.hidden = false;
}

async function _oeffneAlbum(kindId, albumId, resumeTrackPos) {
  // Aktive Kachel markieren.
  document.querySelectorAll(".album-kachel").forEach(k => {
    k.classList.toggle("aktiv", k.dataset.albumId === albumId && k.dataset.kindId === kindId);
  });

  // Audio stoppen.
  _stoppeAudio();

  try {
    // #973: Manifest via folge.kind_id, nicht URL-KIND_ID.
    const manifest = await _holeManifest(kindId, albumId);
    // kind_id im Manifest-State sichern für Resume-Writes.
    manifest._kind_id = kindId;
    _aktivesAlbum = manifest;

    // Start-Track: Resume-Position oder Track 0 (Intro).
    const tracks = (manifest.tracks || []).slice().sort(
      (a, b) => (a.position || 0) - (b.position || 0));
    let startIdx = 0;
    if (resumeTrackPos != null) {
      const idx = tracks.findIndex(t => t.position === resumeTrackPos);
      if (idx >= 0) startIdx = idx;
    }
    _aktiverTrackIdx = startIdx;
    _renderePlayer(manifest, tracks, startIdx);
  } catch (err) {
    zeigeToast("Folge konnte nicht geladen werden.", true);
    console.error("eltern.js: Album öffnen Fehler", err);
  }
}

function _renderePlayer(manifest, tracks, startTrackIdx) {
  const player = document.getElementById("folgen-player");
  if (!player) return;

  const track = tracks[startTrackIdx];
  const albumId = manifest.id;
  const titelText = "Folge " + (manifest.nummer || "") + " · " + (manifest.titel || "");
  const trackLabel = _trackLabel(track);
  const trackAnzeige = "Track " + (startTrackIdx + 1) + "/" + tracks.length + " · " + trackLabel;

  // Track-Liste HTML
  const trackListeHtml = tracks.map((t, i) => {
    const aktiv = i === startTrackIdx;
    return '<li class="track-zeile' + (aktiv ? " aktiv" : "") + '" data-track-idx="' + i + '">' +
      'Track ' + (i + 1) + " · " + esc(_trackLabel(t)) +
    '</li>';
  }).join("");

  player.innerHTML =
    '<div class="player-kopf">' +
      '<img class="player-cover" src="' +
        esc(manifest["cover-asset"] || "") + '" alt="" loading="lazy" ' +
        'onerror="this.style.display=\'none\'">' +
      '<div class="player-info">' +
        '<div class="player-titel">' + esc(titelText) + '</div>' +
        '<div class="player-track-anzeige" id="player-track-anzeige">' + esc(trackAnzeige) + '</div>' +
      '</div>' +
    '</div>' +

    '<div class="player-controls">' +
      '<button type="button" class="player-btn" id="btn-prev" title="Vorheriger Track"' +
        (startTrackIdx === 0 ? " disabled" : "") + '>⏮</button>' +
      '<button type="button" class="player-btn player-btn-play" id="btn-play" title="Play/Pause">▶</button>' +
      '<button type="button" class="player-btn" id="btn-next" title="Nächster Track"' +
        (startTrackIdx >= tracks.length - 1 ? " disabled" : "") + '>⏭</button>' +
    '</div>' +

    '<div class="player-controls" style="justify-content:center;gap:16px;">' +
      '<button type="button" class="player-btn" id="btn-minus15" title="−15 s">−15s</button>' +
      '<button type="button" class="player-btn" id="btn-plus15" title="+15 s">+15s</button>' +
    '</div>' +

    '<button type="button" class="track-liste-toggle" id="toggle-trackliste">Track-Liste anzeigen ▾</button>' +
    '<ul class="track-liste" id="track-liste" hidden>' + trackListeHtml + '</ul>' +
    '<p class="wake-lock-hinweis" id="wake-lock-hinweis"></p>';

  // ── Player Event-Handler ──────────────────────────────────────────────────

  document.getElementById("btn-play").addEventListener("click", _togglePlay);
  document.getElementById("btn-prev").addEventListener("click", () => _navigiereTrack(-1));
  document.getElementById("btn-next").addEventListener("click", () => _navigiereTrack(1));
  document.getElementById("btn-minus15").addEventListener("click", () => {
    if (_audio) _audio.currentTime = Math.max(0, _audio.currentTime - 15);
  });
  document.getElementById("btn-plus15").addEventListener("click", () => {
    if (_audio) {
      if (_audio.duration) _audio.currentTime = Math.min(_audio.duration, _audio.currentTime + 15);
    }
  });

  const toggleBtn = document.getElementById("toggle-trackliste");
  const trackListeEl = document.getElementById("track-liste");
  toggleBtn && toggleBtn.addEventListener("click", () => {
    _trackListeOffen = !_trackListeOffen;
    trackListeEl.hidden = !_trackListeOffen;
    toggleBtn.textContent = _trackListeOffen ? "Track-Liste verstecken ▴" : "Track-Liste anzeigen ▾";
  });

  // Klick auf Track-Zeile.
  trackListeEl && trackListeEl.addEventListener("click", (e) => {
    const zeile = e.target.closest(".track-zeile[data-track-idx]");
    if (!zeile) return;
    const idx = parseInt(zeile.dataset.trackIdx, 10);
    _ladeTrack(manifest, tracks, idx);
  });

  // Audio laden.
  _ladeTrack(manifest, tracks, startTrackIdx, false);
}

function _trackLabel(track) {
  if (!track) return "";
  if (track.art === "intro") return "Intro";
  if (track.art === "outro") return "Outro";
  return track.titel || ("Inhalts-Track " + track.position);
}

function _ladeTrack(manifest, tracks, idx, autoplay = false) {
  const track = tracks[idx];
  if (!track) return;

  _aktiverTrackIdx = idx;

  // Audio-URL direkt aus Manifest (Live-Fix 2026-06-16): HSP-37
  // (/api/v1/hoerspiel/alben/<id>/audio/<track>.mp3) ist heute nicht implementiert
  // bzw. die Pfad-Konstruktion via split/pop traf den Server-Mount nicht
  // (Shared-Assets liegen in /shared-assets/, Inhalt-Tracks unter /alben/<id>/audio/).
  // Manifest liefert die exakte URL bereits — nutzen ohne Umweg.
  const audioUrl = track["audio-asset"] || "";

  // Altes Audio-Element entfernen.
  if (_audio) {
    _audio.pause();
    _audio.src = "";
    _audio = null;
  }

  _audio = new Audio(audioUrl);
  _audio.playbackRate = _editConfig.playback_tempo || _serverConfig.playback_tempo || 1.0;

  _audio.addEventListener("ended", () => {
    // Auto-Play nächster Track (HSP-35).
    if (idx < tracks.length - 1) {
      _ladeTrack(manifest, tracks, idx + 1, true);
    } else {
      // Album-Ende: Wake-Lock freigeben.
      _freigebenWakeLock();
    }
  });

  // Resume-Stand schreiben bei Track-Start (HSP-36).
  // manifest._kind_id ist durch _oeffneAlbum garantiert gesetzt (#973).
  _audio.addEventListener("play", () => {
    _setzeResume(manifest._kind_id || KIND_ID, manifest.id, track.position);
  });

  // UI aktualisieren.
  _aktualisierePlayerUI(manifest, tracks, idx);

  if (autoplay) {
    _audio.play().then(() => {
      _setzePlayBtn(true);
      _anfordernWakeLock();
    }).catch(err => {
      console.warn("eltern.js: Auto-Play Fehler", err);
      _setzePlayBtn(false);
    });
  }
}

async function _togglePlay() {
  if (!_audio) return;
  if (_audio.paused) {
    try {
      await _audio.play();
      _setzePlayBtn(true);
      await _anfordernWakeLock();
    } catch (err) {
      console.warn("eltern.js: Play Fehler", err);
    }
  } else {
    _audio.pause();
    _setzePlayBtn(false);
    await _freigebenWakeLock();
  }
}

function _setzePlayBtn(spielend) {
  const btn = document.getElementById("btn-play");
  if (btn) btn.textContent = spielend ? "⏸" : "▶";
}

function _navigiereTrack(delta) {
  const manifest = _aktivesAlbum;
  if (!manifest) return;
  const tracks = (manifest.tracks || []).slice().sort(
    (a, b) => (a.position || 0) - (b.position || 0));
  const neuerIdx = _aktiverTrackIdx + delta;
  if (neuerIdx < 0 || neuerIdx >= tracks.length) return;
  _ladeTrack(manifest, tracks, neuerIdx, true);
}

function _aktualisierePlayerUI(manifest, tracks, idx) {
  const track = tracks[idx];
  const trackAnzeige = "Track " + (idx + 1) + "/" + tracks.length + " · " + _trackLabel(track);

  const anzeigeEl = document.getElementById("player-track-anzeige");
  if (anzeigeEl) anzeigeEl.textContent = trackAnzeige;

  const prevBtn = document.getElementById("btn-prev");
  const nextBtn = document.getElementById("btn-next");
  if (prevBtn) prevBtn.disabled = (idx === 0);
  if (nextBtn) nextBtn.disabled = (idx >= tracks.length - 1);

  // Track-Zeilen markieren.
  document.querySelectorAll(".track-zeile[data-track-idx]").forEach((z) => {
    z.classList.toggle("aktiv", parseInt(z.dataset.trackIdx, 10) === idx);
  });
}

function _stoppeAudio() {
  if (_audio) {
    _audio.pause();
    _audio.src = "";
    _audio = null;
  }
  _setzePlayBtn(false);
  _freigebenWakeLock();
}

// ── Wake-Lock (HSP-35) ───────────────────────────────────────────────────────

async function _anfordernWakeLock() {
  if (!("wakeLock" in navigator)) {
    _zeigeWakeLockHinweis("Bildschirm bleibt nicht wach — Tablet manuell entsperren.");
    return;
  }
  try {
    if (_wakeLock) return;
    _wakeLock = await navigator.wakeLock.request("screen");
    _wakeLock.addEventListener("release", () => { _wakeLock = null; });
    _zeigeWakeLockHinweis("");
  } catch (err) {
    _zeigeWakeLockHinweis("Bildschirm bleibt nicht wach — Tablet manuell entsperren oder Telefon nicht weglegen.");
    console.warn("eltern.js: Wake-Lock Fehler", err);
  }
}

async function _freigebenWakeLock() {
  if (_wakeLock) {
    try { await _wakeLock.release(); } catch (_) {}
    _wakeLock = null;
  }
}

function _zeigeWakeLockHinweis(text) {
  const el = document.getElementById("wake-lock-hinweis");
  if (el) el.textContent = text;
}

// ── Toast ────────────────────────────────────────────────────────────────────

let _toastTimer = null;

function zeigeToast(msg, fehler = false) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.className = "toast sichtbar" + (fehler ? " fehler" : "");
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    toast.classList.remove("sichtbar", "fehler");
  }, 4000);
}

// ── Hilfs-Funktionen ─────────────────────────────────────────────────────────

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

// ── Exports (für Tests) ──────────────────────────────────────────────────────
if (typeof module !== "undefined" && module.exports) {
  module.exports = { esc, _leseHashTab, zeigeToast, KIND_ID, KIND_IDS_V1, _mergeUndSortiereAlben, _rendereWarnBanner, _patchBeideConfigs };
}
