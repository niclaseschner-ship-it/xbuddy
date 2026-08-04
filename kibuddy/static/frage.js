/**
 * KIBuddy Frage-View — frage.js
 *
 * Abgedeckte Spec-Punkte:
 *   KIBUDDY-5..11  Push-to-Talk (Tap-Hold, Slide-Lock, Slide-Cancel, Pegel)
 *   KIBUDDY-13     NDJSON-Stream-Reader: Stage 1 (kind) sofort, Stage 2 (buddy) nach LLM+TTS
 *   KIBUDDY-17     Buzzword-Render: 3 Buzzwords vom LLM, clientseitiger ICONS-7-Lookup (T865)
 *   KIBUDDY-19     Chat-Verlauf, Auto-Scroll, Reset
 *   KIBUDDY-24     NDJSON-Stream-Response (zwei Events: kind + buddy)
 *   KIBUDDY-29     Reset-Knopf
 *   KIBUDDY-30     UI-Icons aus /display/_shared/icons/arasaac/<id>.png
 *   KIBUDDY-31     Vorlese-Knopf je Bubble
 *
 * Konfig-Konstanten (spiegeln KIBUDDY-21 Defaults):
 */

const CFG = {
  LOCK_DISTANZ_PX:   30,    // Slide-up → Lock (T864: war 80 — jetzt erreichbar)
  ABBRUCH_DISTANZ_PX: 60,   // Slide-down → Cancel (T864: war 100, proportional)
  LOCK_HINWEIS_MS:   800,   // ms bis Slide-Hinweis erscheint
  MAX_AUFNAHME_MS:   30000, // 30 s
  ICON_ARASAAC_BASE: "/display/_shared/icons/arasaac/",
  ICON_SUCHE_BASE:   "/api/v1/icons/suche",
};

// VAD-Konfig aus Server-Render (KIBUDDY-21/AC3); Fallback auf Defaults
const _serverCfg = (typeof window !== "undefined" && window.KIBUDDY_CFG) || {};
const VAD_STILLE_MS    = ((_serverCfg.vad_stille_sek  != null) ? _serverCfg.vad_stille_sek  : 1.5) * 1000;
const VAD_THRESHOLD_DB = (_serverCfg.vad_threshold_db != null) ? _serverCfg.vad_threshold_db : -50.0;

// Neue Cfg-Felder (T864: Long-Hold-Auto-Lock + Mindest-Aufnahme-Dauer)
const cfg = {
  vad_long_hold_lock_sek: (_serverCfg.vad_long_hold_lock_sek != null) ? _serverCfg.vad_long_hold_lock_sek : 3.0,
  aufnahme_min_sek:       (_serverCfg.aufnahme_min_sek       != null) ? _serverCfg.aufnahme_min_sek       : 0.5,
};

// ============================================================
//  DOM-Refs
// ============================================================

const $chat          = document.getElementById("chat");
const $headerStatus  = document.getElementById("header-status");
const $btnReset      = document.getElementById("btn-reset");
const $btnPtt        = document.getElementById("btn-ptt");
const $pttImg        = document.getElementById("ptt-img");
const $pegelLinks    = [
  document.getElementById("pl5"),
  document.getElementById("pl4"),
  document.getElementById("pl3"),
  document.getElementById("pl2"),
  document.getElementById("pl1"),
]; // von aussen nach innen (pl5 = äußerster)
const $pegelRechts   = [
  document.getElementById("pr1"),
  document.getElementById("pr2"),
  document.getElementById("pr3"),
  document.getElementById("pr4"),
  document.getElementById("pr5"),
]; // von innen nach aussen
const $lockHinweis   = document.getElementById("lock-hinweis");
const $cancelHinweis = document.getElementById("cancel-hinweis");
const $stoppRow      = document.getElementById("stopp-row");
const $btnStopp      = document.getElementById("btn-stopp");
const $mikroFehler   = document.getElementById("mikro-fehler");

// ============================================================
//  Zustand
// ============================================================

let mediaRecorder = null;
let audioStream   = null;
let audioCtx      = null;
let analyser      = null;
let rafId         = null;

/** PTT-Zustand: 'idle' | 'recording' | 'locked' */
let pttState = "idle";

/** Startpunkt für Slide-Berechnung */
let touchStartY = null;
let lockHinweisTimer = null;
let maxAufnahmeTimer = null;
/** T864: Long-Hold-Auto-Lock-Timer (AC2) */
let longHoldLockTimer = null;
/** T864: Aufnahme-Start-Zeitpunkt für Mindest-Dauer-Prüfung (AC3) */
let aufnahmeStartMs = null;

// ============================================================
//  Audio-Kontext + Pegel (KIBUDDY-9)
// ============================================================

function startPegel(stream) {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 256;
  const source = audioCtx.createMediaStreamSource(stream);
  source.connect(analyser);

  const buf = new Float32Array(analyser.frequencyBinCount);

  function tick() {
    if (!analyser) return;
    analyser.getFloatTimeDomainData(buf);
    // RMS-Berechnung
    let sumSq = 0;
    for (let i = 0; i < buf.length; i++) sumSq += buf[i] * buf[i];
    const rms = Math.sqrt(sumSq / buf.length);
    // Skalierung 0..72px (max-height der Balken)
    const basis = Math.min(72, Math.round(rms * 400));

    // Symmetrisch variierend (benachbarte Balken leicht unterschiedlich)
    const heights = [
      Math.max(4, Math.round(basis * 0.55)),
      Math.max(4, Math.round(basis * 0.75)),
      Math.max(4, Math.round(basis * 1.0)),
      Math.max(4, Math.round(basis * 0.75)),
      Math.max(4, Math.round(basis * 0.55)),
    ];

    // Links (aussen→innen = pl5..pl1) und rechts (innen→aussen = pr1..pr5)
    $pegelLinks.forEach((el, i) => el.style.height = heights[i] + "px");
    $pegelRechts.forEach((el, i) => el.style.height = heights[i] + "px");

    rafId = requestAnimationFrame(tick);
  }
  rafId = requestAnimationFrame(tick);
}

function stopPegel() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  analyser = null;
  // Balken zurücksetzen
  $pegelLinks.forEach(el => el.style.height = "8px");
  $pegelRechts.forEach(el => el.style.height = "8px");
}

// ============================================================
//  VAD — Voice Activity Detection im Lock-Modus (KIBUDDY-7/AC3)
// ============================================================

/** Zeitpunkt, ab dem Stille unter Threshold anhält (ms, performance.now()) */
let vadStilleStart = null;
/** RAF-ID für VAD-Loop (getrennt von Pegel-rafId) */
let vadRafId = null;

/**
 * Berechnet RMS-dB aus AnalyserNode-Float32-Puffer.
 * Gibt -Infinity wenn der Puffer leer ist.
 */
function _computeRmsDb(analyserNode) {
  const buf = new Float32Array(analyserNode.frequencyBinCount);
  analyserNode.getFloatTimeDomainData(buf);
  let sumSq = 0;
  for (let i = 0; i < buf.length; i++) sumSq += buf[i] * buf[i];
  const rms = Math.sqrt(sumSq / buf.length);
  if (rms === 0) return -Infinity;
  return 20 * Math.log10(rms);
}

/**
 * VAD-Loop: läuft nur im Lock-Modus.
 * Erkennt Stille (dB < VAD_THRESHOLD_DB) über VAD_STILLE_MS hinaus
 * und ruft dann automatisch stopUndSende(false) auf (AC3).
 * Manueller Stopp-Knopf bleibt Override (KIBUDDY-7).
 */
function vadLoop() {
  if (pttState !== "locked") {
    vadRafId = null;
    vadStilleStart = null;
    return;
  }
  if (!analyser) {
    // Analyser noch nicht bereit — kurz warten
    vadRafId = requestAnimationFrame(vadLoop);
    return;
  }

  const db = _computeRmsDb(analyser);

  if (db < VAD_THRESHOLD_DB) {
    // Stille erkannt
    if (vadStilleStart === null) {
      vadStilleStart = performance.now();
    } else if (performance.now() - vadStilleStart >= VAD_STILLE_MS) {
      // Stille-Schwelle überschritten → Auto-Stop
      vadRafId = null;
      vadStilleStart = null;
      stopUndSende(false);
      return;
    }
  } else {
    // Sprache erkannt — Stille-Timer zurücksetzen
    vadStilleStart = null;
  }

  vadRafId = requestAnimationFrame(vadLoop);
}

/** Stoppt den VAD-Loop (beim Verlassen des Lock-Modus). */
function stopVad() {
  if (vadRafId !== null) {
    cancelAnimationFrame(vadRafId);
    vadRafId = null;
  }
  vadStilleStart = null;
}

// ============================================================
//  MediaRecorder (KIBUDDY-5/7)
// ============================================================

/**
 * Fordert Mikro-Erlaubnis an und startet Aufnahme.
 * Gibt Promise<{recorder, stream}> zurück.
 * KIBUDDY-6: Bei Verweigerung → Hinweis anzeigen, kein Crash.
 */
async function mikro_start() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    $mikroFehler.hidden = true;
  } catch (_err) {
    // KIBUDDY-6: freundlicher Hinweis, kein Modal, kein Retry-Loop
    $mikroFehler.hidden = false;
    return null;
  }

  // MIME-Type: WebM/Opus als Default, MP4 als Safari-Fallback
  const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : MediaRecorder.isTypeSupported("audio/mp4")
    ? "audio/mp4"
    : "";

  const options = mimeType ? { mimeType } : {};
  const recorder = new MediaRecorder(stream, options);
  return { recorder, stream };
}

/**
 * Stoppt Aufnahme und sendet Audio an /api/v1/kibuddy/frage.
 * Liest NDJSON-Stream: Stage 1 (event=kind) → Kind-Bubble sofort,
 * Stage 2 (event=buddy) → Buddy-Bubble + TTS-Audio nach LLM+TTS.
 * Lade-Bubble bleibt sichtbar zwischen Stage 1 und Stage 2 (KIBUDDY-13/24).
 * chunks: Blob-Parts der Aufnahme.
 * mimeType: MIME-Typ des Recorders.
 */
async function send_aufnahme(chunks, mimeType) {
  if (!chunks || chunks.length === 0) return;

  const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
  const formData = new FormData();
  const ext = mimeType && mimeType.includes("mp4") ? "mp4" : "webm";
  formData.append("audio", blob, `aufnahme.${ext}`);

  setHeaderStatus("Ich denke nach…");

  // Lade-Bubble in Chat einhaengen waehrend Stream laeuft (KIBUDDY-8/AC1)
  const ladeBubbleRow = document.createElement("div");
  ladeBubbleRow.className = "bubble-row buddy";
  const ladeBubble = document.createElement("div");
  ladeBubble.className = "bubble bubble-laden";
  ladeBubble.setAttribute("aria-label", "Ich arbeite…");
  ladeBubble.innerHTML = '<span class="lade-dots"><span></span><span></span><span></span></span>';
  ladeBubbleRow.appendChild(ladeBubble);
  $chat.appendChild(ladeBubbleRow);
  $chat.scrollTop = $chat.scrollHeight;

  // Turn-Container wird beim ersten Stage-1-Event (kind) erzeugt und im DOM verankert,
  // damit Kind-Bubble und spaetere Buddy-Bubble im selben .turn-Div landen.
  let turnEl = null;

  try {
    const resp = await fetch("/api/v1/kibuddy/frage", {
      method: "POST",
      body: formData,
    });

    if (!resp.ok) {
      // HTTP-Fehler vor Stream (z. B. 400/503 bei fehlenden Keys/audio)
      const body = await resp.json().catch(() => ({}));
      const msg = body.fehler || ("Fehler " + resp.status);
      ladeBubbleRow.remove();
      appendFehlerBubble(msg);
      return;
    }

    // NDJSON-Stream-Reader (KIBUDDY-13/24)
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let lineEnd;
      while ((lineEnd = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, lineEnd);
        buffer = buffer.slice(lineEnd + 1);
        if (!line.trim()) continue;

        let event;
        try {
          event = JSON.parse(line);
        } catch (_e) {
          continue; // kaputte Zeile ignorieren
        }

        if (event.event === "kind") {
          // Stage 1: Kind-Bubble sofort rendern (KIBUDDY-13/19)
          turnEl = document.createElement("div");
          turnEl.className = "turn";
          $chat.appendChild(turnEl);
          await renderKindBubble(turnEl, event.transkript, event.transkript_words);
          $chat.scrollTop = $chat.scrollHeight;
          // Lade-Bubble bleibt sichtbar bis Stage 2 kommt

        } else if (event.event === "buddy") {
          // Stage 2: Lade-Bubble weg, Buddy-Bubble in denselben Turn (KIBUDDY-13/19)
          ladeBubbleRow.remove();
          if (!turnEl) {
            // Defensiv: Stage 1 fehlte (sollte nicht vorkommen) — neuen Turn anlegen
            turnEl = document.createElement("div");
            turnEl.className = "turn";
            $chat.appendChild(turnEl);
          }
          await renderBuddyBubble(turnEl, event.text, event.buzzwords, event.tts_audio_url);
          $chat.scrollTop = $chat.scrollHeight;

          if (event.tts_audio_url) {
            playAudio(event.tts_audio_url);
          }

        } else if (event.event === "error") {
          // Fehler-Event aus dem Stream
          ladeBubbleRow.remove();
          appendFehlerBubble(event.detail || "Unbekannter Fehler");
          return;
        }
      }
    }

  } catch (err) {
    ladeBubbleRow.remove();
    appendFehlerBubble("Netzwerk-Fehler: " + err.message);
  } finally {
    setHeaderStatus("Dr\xFCck mich, wenn du eine Frage hast");
  }
}

/**
 * Rendert Kind-Bubble (Stage 1) in den uebergebenen Turn-Container.
 * KIBUDDY-19/Option-C (T865): text-only, kein Icon-Render.
 * transkript_words[] wird vom Backend als Diagnose-Feld geliefert, aber hier ignoriert.
 */
async function renderKindBubble(turnEl, transkript, transkript_words) {
  const kindRow = document.createElement("div");
  kindRow.className = "bubble-row kind";

  const kindBubble = document.createElement("div");
  kindBubble.className = "bubble kind-bubble";

  // Option C (T865): Kind-Bubble text-only (KIBUDDY-19).
  const p = document.createElement("p");
  p.className = "kind-frage-text";
  p.textContent = transkript || "";
  kindBubble.appendChild(p);

  // Vorlese-Knopf Kind (KIBUDDY-31)
  const vorlKind = buildVorlBtn(() => vorleseText(transkript));
  kindRow.appendChild(vorlKind);
  kindRow.appendChild(kindBubble);
  turnEl.appendChild(kindRow);
}

/**
 * Rendert Buddy-Bubble (Stage 2) in den uebergebenen Turn-Container.
 * T865/KIBUDDY-17: Text als Absatz + Buzzword-Block am Ende.
 * text: LLM-Antwort (Fließtext).
 * buzzwords: string[] mit 3 Buzzwords vom LLM.
 * tts_audio_url: URL oder null.
 */
async function renderBuddyBubble(turnEl, text, buzzwords, tts_audio_url) {
  const buddyRow = document.createElement("div");
  buddyRow.className = "bubble-row buddy";

  const buddyBubble = document.createElement("div");
  buddyBubble.className = "bubble buddy-bubble";

  // Antwort-Text als zusammenhängender Absatz (T865/KIBUDDY-17)
  const p = document.createElement("p");
  p.className = "buddy-antwort-text";
  p.textContent = text || "";
  buddyBubble.appendChild(p);

  // Buzzword-Block am Ende (T865/KIBUDDY-17 — 3 Icons via ICONS-7-Lookup)
  if (Array.isArray(buzzwords) && buzzwords.length > 0) {
    const buzzBlock = await buildBuzzwordBlock(buzzwords);
    buddyBubble.appendChild(buzzBlock);
  }

  // Vorlese-Knopf Buddy (KIBUDDY-31)
  const antwortObj = { text, tts_audio_url };
  const vorlBuddy = buildVorlBtn(() => vorleseBubble(antwortObj));
  buddyRow.appendChild(buddyBubble);
  buddyRow.appendChild(vorlBuddy);
  turnEl.appendChild(buddyRow);
}

// ============================================================
//  Chat-Render (KIBUDDY-17/19/31, T865 Buzzword-Render)
// ============================================================
// renderKindBubble() und renderBuddyBubble() sind Teil von send_aufnahme() (KIBUDDY-13/24).

/**
 * Baut den Buzzword-Block mit 3 Icon-Karten (T865/KIBUDDY-17).
 * Parallel ICONS-7-Lookup fuer alle Buzzwords (Promise.all).
 * buzzwords: string[] — max 3 Wörter vom LLM.
 * Gibt ein <div class="buzzword-block"> zurück (Icons werden async eingefügt).
 */
async function buildBuzzwordBlock(buzzwords) {
  const block = document.createElement("div");
  block.className = "buzzword-block";

  // Parallel fetch (KIBUDDY-17 "parallel, kein Wort-für-Wort-Serial")
  const iconUrls = await Promise.all(buzzwords.map(w => fetchIcon(w)));

  buzzwords.forEach((wort, i) => {
    const item = document.createElement("div");
    item.className = "buzzword-item";

    const icoUrl = iconUrls[i];
    if (icoUrl) {
      const img = document.createElement("img");
      img.src = icoUrl;
      img.alt = wort;
      img.loading = "lazy";
      // Live-Befund 2026-06-15: bei broken-image zeigt der Browser sein
      // Default-Fragezeichen-Icon — entfernen statt verwirrend anzeigen.
      img.onerror = () => img.remove();
      // KIBUDDY-30: Vollfarbe, KEIN filter
      item.appendChild(img);
    }

    const lbl = document.createElement("div");
    lbl.className = "buzzword-label";
    lbl.textContent = wort;
    item.appendChild(lbl);

    block.appendChild(item);
  });

  return block;
}

/**
 * Holt ersten Icon-Treffer für ein Wort (KIBUDDY-17/ICONS-7).
 * Gibt URL-String zurück oder null bei Miss / Fetch-Fehler.
 */
async function fetchIcon(wort) {
  const normiert = wort.toLowerCase().replace(/[.!?,;:]+$/, "");
  if (!normiert) return null;
  try {
    const url = `${CFG.ICON_SUCHE_BASE}?q=${encodeURIComponent(normiert)}&max=1`;
    const resp = await fetch(url);
    if (!resp.ok) return null;
    const liste = await resp.json();
    if (!Array.isArray(liste) || liste.length === 0) return null;
    return liste[0].url || null;
  } catch (_err) {
    return null; // KIBUDDY-17: kein Crash bei Lookup-Fail
  }
}

/**
 * Baut Vorlese-Knopf (KIBUDDY-31).
 * onClick: Callback-Funktion.
 */
function buildVorlBtn(onClick) {
  const btn = document.createElement("button");
  btn.className = "btn-vorlese";
  btn.setAttribute("aria-label", "Vorlesen");
  btn.setAttribute("title", "Vorlesen");
  btn.setAttribute("type", "button");

  const img = document.createElement("img");
  img.src = `${CFG.ICON_ARASAAC_BASE}38221.png`; // KIBUDDY-30: ID 38221
  img.alt = "Vorlesen";
  img.width = 44;
  img.height = 44;
  btn.appendChild(img);

  btn.addEventListener("click", onClick);
  return btn;
}

// ============================================================
//  Audio-Playback (KIBUDDY-20/31)
// ============================================================

let laufenderAudio = null;

function playAudio(url) {
  // Laufendes Audio zuerst stoppen (KIBUDDY-31 "idempotent")
  if (laufenderAudio) {
    laufenderAudio.pause();
    laufenderAudio = null;
  }
  const a = new Audio(url);
  laufenderAudio = a;
  a.play().catch(() => {
    // Auto-Play kann von Browser geblockt werden — kein Crash
    laufenderAudio = null;
  });
  a.addEventListener("ended", () => { laufenderAudio = null; });
  a.addEventListener("error", () => { laufenderAudio = null; });
}

/**
 * Zeigt dezenten Inline-Fehler-Hinweis statt alert() (FIX4, KIBUDDY-30).
 * Legt einen temporären Hinweis-Span in der ptt-zone ab.
 */
function _zeigeTtsFehler() {
  const existierend = document.getElementById("tts-fehler-hinweis");
  if (existierend) return; // bereits sichtbar
  const hinweis = document.createElement("span");
  hinweis.id = "tts-fehler-hinweis";
  hinweis.className = "tts-fehler-hinweis";
  hinweis.textContent = "Vorlesen geht gerade nicht";
  document.getElementById("ptt-zone").appendChild(hinweis);
  setTimeout(() => hinweis.remove(), 4000);
}

/**
 * KIBUDDY-31: Vorlese-Knopf Buddy-Bubble.
 * Versucht tts_audio_url; bei 404 → POST /vorlesen mit text.
 */
async function vorleseBubble(antwort) {
  if (laufenderAudio) {
    laufenderAudio.pause();
    laufenderAudio = null;
  }

  if (antwort.tts_audio_url) {
    // Versuche direkte URL
    const a = new Audio(antwort.tts_audio_url);
    laufenderAudio = a;
    a.play().catch(async () => {
      // 404 oder Netz-Fehler → Fallback POST /vorlesen
      laufenderAudio = null;
      await vorleseFallback(antwort.text);
    });
    a.addEventListener("ended", () => { laufenderAudio = null; });
    a.addEventListener("error", async () => {
      laufenderAudio = null;
      await vorleseFallback(antwort.text);
    });
  } else {
    // tts_audio_url: null → Fallback oder Inline-Hinweis (FIX4)
    if (antwort.text) {
      await vorleseFallback(antwort.text);
    } else {
      _zeigeTtsFehler();
    }
  }
}

/**
 * KIBUDDY-31 Fallback: POST /vorlesen → MP3-URL → abspielen.
 */
async function vorleseFallback(text) {
  if (!text) { _zeigeTtsFehler(); return; }
  try {
    const resp = await fetch("/api/v1/kibuddy/vorlesen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) {
      _zeigeTtsFehler();
      return;
    }
    const body = await resp.json();
    if (body.tts_audio_url) {
      playAudio(body.tts_audio_url);
    }
  } catch (_err) {
    _zeigeTtsFehler();
  }
}

/**
 * KIBUDDY-31: Vorlese-Knopf Kind-Bubble → transkript vorlesen.
 */
async function vorleseText(text) {
  if (!text) return;
  await vorleseFallback(text);
}

// ============================================================
//  Fehler-Bubble
// ============================================================

function appendFehlerBubble(msg) {
  const turn = document.createElement("div");
  turn.className = "turn";
  const row = document.createElement("div");
  row.className = "bubble-row buddy";
  const bubble = document.createElement("div");
  bubble.className = "bubble buddy-bubble";
  bubble.style.background = "#fef3c7";
  bubble.style.border = "2px solid #f6a800";
  bubble.textContent = "Hoppla! " + msg;
  row.appendChild(bubble);
  turn.appendChild(row);
  $chat.appendChild(turn);
  $chat.scrollTop = $chat.scrollHeight;
}

/**
 * T864-AC3: Dezente Hinweis-Bubble wenn Aufnahme zu kurz war.
 * Entfernt sich nach 4s automatisch.
 */
function appendKurzAufnahmeHinweis() {
  const div = document.createElement("div");
  div.className = "bubble bubble-hinweis";
  div.textContent = "Bitte sprich etwas lauter und l\xE4nger";
  $chat.appendChild(div);
  $chat.scrollTop = $chat.scrollHeight;
  setTimeout(() => div.remove(), 4000);
}

// ============================================================
//  Reset (KIBUDDY-29)
// ============================================================

async function doReset() {
  // Chat-Container leeren
  while ($chat.firstChild) $chat.removeChild($chat.firstChild);
  setHeaderStatus("Drück mich, wenn du eine Frage hast");

  // Server-Reset (KIBUDDY-16 Session-Memory + Audio-Cache)
  try {
    await fetch("/api/v1/kibuddy/reset", { method: "POST" });
  } catch (_err) {
    // Netz-Fehler beim Reset ist nicht kritisch für die View
  }
}

// ============================================================
//  Push-to-Talk UX (KIBUDDY-7..11)
// ============================================================

let aufnahmeChunks = [];
let aufnahmeMimeType = "";

/** Startet Aufnahme: Audio anfordern, Recorder starten, Pegel starten */
async function startAufnahme() {
  if (pttState !== "idle") return;

  const result = await mikro_start();
  if (!result) return; // Mikro verweigert — Hinweis bereits angezeigt (KIBUDDY-6)

  const { recorder, stream } = result;
  mediaRecorder = recorder;
  audioStream = stream;
  aufnahmeChunks = [];
  aufnahmeMimeType = recorder.mimeType || "audio/webm";

  recorder.addEventListener("dataavailable", evt => {
    if (evt.data && evt.data.size > 0) aufnahmeChunks.push(evt.data);
  });

  recorder.start(100); // alle 100ms ein Chunk
  pttState = "recording";
  aufnahmeStartMs = performance.now(); // T864-AC3: Mindest-Dauer-Messung

  // KIBUDDY-8: sofortiges Echo
  $btnPtt.classList.add("aktiv");
  startPegel(stream);
  setHeaderStatus("Ich h\xF6re zu…");

  // KIBUDDY-10 V1 ENTFERNT (2026-06-15): Lock-Hinweis-Element existiert nicht
  // mehr im DOM. Timer-Block bleibt no-op für Backward-Compat der Restlogik.
  lockHinweisTimer = setTimeout(() => {
    if (pttState === "recording" && $lockHinweis) {
      $lockHinweis.hidden = false;
    }
  }, CFG.LOCK_HINWEIS_MS);

  // KIBUDDY-7: Max-Aufnahme-Dauer
  maxAufnahmeTimer = setTimeout(() => {
    if (pttState === "recording" || pttState === "locked") {
      stopUndSende(false);
    }
  }, CFG.MAX_AUFNAHME_MS);

  // T864-AC2: Long-Hold-Auto-Lock nach cfg.vad_long_hold_lock_sek
  longHoldLockTimer = setTimeout(() => {
    if (pttState === "recording") {
      einrastenLock();
    }
  }, cfg.vad_long_hold_lock_sek * 1000);
}

/** Stoppt Recorder (ohne zu senden) */
function stopRecorder() {
  if (lockHinweisTimer) { clearTimeout(lockHinweisTimer); lockHinweisTimer = null; }
  if (maxAufnahmeTimer) { clearTimeout(maxAufnahmeTimer); maxAufnahmeTimer = null; }
  if (longHoldLockTimer) { clearTimeout(longHoldLockTimer); longHoldLockTimer = null; } // T864-AC2
  if ($lockHinweis) $lockHinweis.hidden = true;  // KIBUDDY-10 V1 entfernt: Element kann null sein
  $cancelHinweis.hidden = true;
  stopVad();
  stopPegel();
  $btnPtt.classList.remove("aktiv", "locked");
  $stoppRow.hidden = true;
  $btnPtt.parentElement.hidden = false; // mikro-row zeigen

  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  if (audioStream) {
    audioStream.getTracks().forEach(t => t.stop());
    audioStream = null;
  }
  mediaRecorder = null;
  pttState = "idle";
}

/**
 * Stoppt Aufnahme und sendet (wenn !abbruch).
 * KIBUDDY-11: Bei abbruch=true kein POST.
 * T864-AC3: Mindest-Aufnahme-Dauer-Filter.
 */
async function stopUndSende(abbruch) {
  if (pttState === "idle") return;

  // T864-AC3: Dauer messen vor stopRecorder (der setzt pttState → idle)
  const dauerSek = aufnahmeStartMs !== null
    ? (performance.now() - aufnahmeStartMs) / 1000
    : Infinity;

  const chunks = aufnahmeChunks.slice();
  const mime   = aufnahmeMimeType;
  stopRecorder();

  if (abbruch) {
    setHeaderStatus("Dr\xFCck mich, wenn du eine Frage hast");
    return;
  }

  // T864-AC3: Aufnahme zu kurz → verwerfen, Hinweis zeigen
  if (dauerSek < cfg.aufnahme_min_sek) {
    appendKurzAufnahmeHinweis();
    setHeaderStatus("Dr\xFCck mich, wenn du eine Frage hast");
    return;
  }

  await send_aufnahme(chunks, mime);
}

/** Wechsel in Lock-Modus (KIBUDDY-7 Modus B + T864-AC2 Long-Hold) */
function einrastenLock() {
  if (pttState !== "recording") return;
  pttState = "locked";
  if ($lockHinweis) $lockHinweis.hidden = true;  // KIBUDDY-10 V1 entfernt
  if (lockHinweisTimer) { clearTimeout(lockHinweisTimer); lockHinweisTimer = null; }
  if (longHoldLockTimer) { clearTimeout(longHoldLockTimer); longHoldLockTimer = null; } // T864-AC2
  $btnPtt.classList.add("locked");
  // Stopp-Knopf zeigen (KIBUDDY-7 "Stopp-Knopf an Slide-Ziel")
  $stoppRow.hidden = false;
  setHeaderStatus("Aufnahme l\xE4uft… Stopp dr\xFCcken zum Senden");
  // VAD starten (KIBUDDY-7/AC3): Auto-Stop bei Stille im Lock-Modus
  vadStilleStart = null;
  vadRafId = requestAnimationFrame(vadLoop);
}

function setHeaderStatus(text) {
  $headerStatus.textContent = text;
}

// ============================================================
//  Touch + Mouse-Events für PTT (KIBUDDY-7/8/10/11)
// ============================================================

function onPttDown(evt) {
  evt.preventDefault();
  touchStartY = evt.touches ? evt.touches[0].clientY : evt.clientY;
  startAufnahme();
}

function onPttMove(evt) {
  if (pttState === "locked") return; // im Lock-Modus kein Move-Handler
  if (pttState !== "recording") return;
  evt.preventDefault();

  const y = evt.touches ? evt.touches[0].clientY : evt.clientY;
  const delta = touchStartY - y; // positiv = nach oben

  if (delta >= CFG.LOCK_DISTANZ_PX) {
    // KIBUDDY-7: Slide nach oben → Lock
    einrastenLock();
    return;
  }

  if (-delta >= CFG.ABBRUCH_DISTANZ_PX) {
    // KIBUDDY-11: Slide nach unten → Cancel
    $cancelHinweis.hidden = false;
    // Abbbruch ausführen wenn genug nach unten
    stopUndSende(true);
    return;
  }

  // Scroll-Cancel-Hinweis zeigen wenn >= 30px nach unten
  $cancelHinweis.hidden = (-delta < 30);
}

function onPttUp(evt) {
  if (pttState === "locked") return; // Stopp-Knopf ist zuständig
  if (pttState !== "recording") return;
  evt.preventDefault();
  $cancelHinweis.hidden = true;
  stopUndSende(false);
}

// Touch-Events (KIBUDDY-7: Touch-first für Display)
$btnPtt.addEventListener("touchstart", onPttDown, { passive: false });
$btnPtt.addEventListener("touchmove",  onPttMove,  { passive: false });
$btnPtt.addEventListener("touchend",   onPttUp,    { passive: false });
$btnPtt.addEventListener("touchcancel", () => stopUndSende(true), { passive: false });

// Mouse-Events (für Desktop-Browser / Entwicklung)
$btnPtt.addEventListener("mousedown", onPttDown);
document.addEventListener("mousemove", evt => {
  if (pttState === "recording") onPttMove(evt);
});
document.addEventListener("mouseup", evt => {
  if (pttState === "recording") onPttUp(evt);
});

// Stopp-Knopf (Lock-Modus) — KIBUDDY-7 Modus B
$btnStopp.addEventListener("click", () => {
  if (pttState === "locked") stopUndSende(false);
});
$btnStopp.addEventListener("touchend", evt => {
  evt.preventDefault();
  if (pttState === "locked") stopUndSende(false);
}, { passive: false });

// ============================================================
//  Reset-Knopf (KIBUDDY-29)
// ============================================================

$btnReset.addEventListener("click", doReset);
$btnReset.addEventListener("touchend", evt => {
  evt.preventDefault();
  doReset();
}, { passive: false });

// ============================================================
//  Init
// ============================================================

// Initial-Zustand (KIBUDDY-4): leerer Chat, neutraler Header
setHeaderStatus("Dr\xFCck mich, wenn du eine Frage hast");
