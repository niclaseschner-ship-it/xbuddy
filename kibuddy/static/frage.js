/**
 * KIBuddy Frage-View — frage.js
 *
 * Abgedeckte Spec-Punkte:
 *   KIBUDDY-5..11  Push-to-Talk (Tap-Hold, Slide-Lock, Slide-Cancel, Pegel)
 *   KIBUDDY-17     Wort-für-Wort-Render, clientseitiger Icon-Lookup (ICONS-7)
 *   KIBUDDY-19     Chat-Verlauf, Auto-Scroll, Reset
 *   KIBUDDY-29     Reset-Knopf
 *   KIBUDDY-30     UI-Icons aus /display/_shared/icons/arasaac/<id>.png
 *   KIBUDDY-31     Vorlese-Knopf je Bubble
 *
 * Konfig-Konstanten (spiegeln KIBUDDY-21 Defaults):
 */

const CFG = {
  LOCK_DISTANZ_PX:   80,    // Slide-up → Lock
  ABBRUCH_DISTANZ_PX: 100,  // Slide-down → Cancel
  LOCK_HINWEIS_MS:   800,   // ms bis Slide-Hinweis erscheint
  MAX_AUFNAHME_MS:   30000, // 30 s
  ICON_ARASAAC_BASE: "/display/_shared/icons/arasaac/",
  ICON_SUCHE_BASE:   "/api/v1/icons/suche",
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
const $ladehinweis   = document.getElementById("ladehinweis");
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
  $ladehinweis.hidden = false;

  let antwort;
  try {
    const resp = await fetch("/api/v1/kibuddy/frage", {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      const msg = body.fehler || `Fehler ${resp.status}`;
      appendFehlerBubble(msg);
      return;
    }
    antwort = await resp.json();
  } catch (err) {
    appendFehlerBubble("Netzwerk-Fehler: " + err.message);
    return;
  } finally {
    $ladehinweis.hidden = true;
    setHeaderStatus("Drück mich, wenn du eine Frage hast");
  }

  await renderTurn(antwort);
}

// ============================================================
//  Chat-Render (KIBUDDY-17/19/31)
// ============================================================

/**
 * Rendert einen Turn: Kind-Bubble + Buddy-Bubble.
 * antwort: { text, transkript, transkript_words, words, tts_audio_url }
 */
async function renderTurn(antwort) {
  const turn = document.createElement("div");
  turn.className = "turn";

  // Kind-Bubble (KIBUDDY-19: wort-für-wort nach KIBUDDY-17, analog Buddy-Bubble)
  const kindRow = document.createElement("div");
  kindRow.className = "bubble-row kind";

  const kindBubble = document.createElement("div");
  kindBubble.className = "bubble kind-bubble";

  if (Array.isArray(antwort.transkript_words) && antwort.transkript_words.length > 0) {
    const kindWortRender = await buildWortRender(antwort.transkript_words);
    kindBubble.appendChild(kindWortRender);
  } else if (antwort.transkript) {
    // Fallback: transkript-Text (nur wenn transkript_words fehlt — ältere Backend-Version)
    const fallback = document.createElement("span");
    fallback.textContent = antwort.transkript;
    kindBubble.appendChild(fallback);
  }

  // Vorlese-Knopf Kind (KIBUDDY-31)
  const vorlKind = buildVorlBtn(() => vorleseText(antwort.transkript));
  kindRow.appendChild(vorlKind);
  kindRow.appendChild(kindBubble);

  // Buddy-Bubble (KIBUDDY-17)
  const buddyRow = document.createElement("div");
  buddyRow.className = "bubble-row buddy";

  const buddyBubble = document.createElement("div");
  buddyBubble.className = "bubble buddy-bubble";

  // Text-Zeile
  const textZeile = document.createElement("p");
  textZeile.style.margin = "0 0 8px 0";
  textZeile.textContent = antwort.text || "";
  buddyBubble.appendChild(textZeile);

  // Wort-Icon-Render (KIBUDDY-17)
  if (Array.isArray(antwort.words) && antwort.words.length > 0) {
    const wortRender = await buildWortRender(antwort.words);
    buddyBubble.appendChild(wortRender);
  }

  // Vorlese-Knopf Buddy (KIBUDDY-31)
  const vorlBuddy = buildVorlBtn(() => vorleseBubble(antwort));
  buddyRow.appendChild(buddyBubble);
  buddyRow.appendChild(vorlBuddy);

  turn.appendChild(kindRow);
  turn.appendChild(buddyRow);
  $chat.appendChild(turn);

  // Auto-Scroll nach unten (KIBUDDY-19)
  $chat.scrollTop = $chat.scrollHeight;

  // TTS auto-play nach User-Geste (KIBUDDY-20)
  if (antwort.tts_audio_url) {
    playAudio(antwort.tts_audio_url);
  }
}

/**
 * Baut das Wort-für-Wort Render-Element (KIBUDDY-17).
 * Für Inhaltswörter: parallel fetch /api/v1/icons/suche → Icon darunter.
 * Für Funktionswörter: nur Text ohne Icon-Slot.
 */
async function buildWortRender(words) {
  const container = document.createElement("div");
  container.className = "wort-render";

  // Inhaltswörter parallel fetchen (KIBUDDY-17 Schritt 4)
  const inhaltIndizes = words
    .map((w, i) => (w.is_inhaltswort ? i : -1))
    .filter(i => i >= 0);

  // Promise.all parallel fetch (KIBUDDY-17 "parallel, kein Wort-für-Wort-Serial")
  const iconResults = await Promise.all(
    inhaltIndizes.map(idx => fetchIcon(words[idx].text))
  );
  const iconMap = {};
  inhaltIndizes.forEach((idx, pos) => {
    iconMap[idx] = iconResults[pos]; // null wenn kein Treffer
  });

  words.forEach((wort, idx) => {
    const text = wort.text || "";
    if (!text) return;

    // Prüfe ob Satzzeichen am Ende (KIBUDDY-17 Punkt 7)
    const satzzeichen = text.match(/[.!?,;:]$/);
    const wortKern = satzzeichen ? text.slice(0, -1) : text;

    if (wort.is_inhaltswort) {
      // Inhaltswort-Slot (KIBUDDY-17 Punkt 5/6)
      const slot = document.createElement("div");
      slot.className = "wort-slot";

      const icoReserve = document.createElement("div");
      icoReserve.className = "icon-reserve";

      const icoUrl = iconMap[idx];
      if (icoUrl) {
        const img = document.createElement("img");
        img.src = icoUrl;
        img.alt = wortKern;
        img.loading = "lazy";
        // KIBUDDY-30: Vollfarbe, KEIN filter
        icoReserve.appendChild(img);
      }
      slot.appendChild(icoReserve);

      const wortText = document.createElement("span");
      wortText.className = "wort-text";
      wortText.textContent = wortKern;
      slot.appendChild(wortText);

      if (satzzeichen) {
        const sz = document.createElement("span");
        sz.className = "wort-satz";
        sz.textContent = satzzeichen[0];
        container.appendChild(slot);
        container.appendChild(sz);
      } else {
        container.appendChild(slot);
      }

    } else {
      // Funktionswort — nur Text, kein Icon-Slot (KIBUDDY-17 Punkt 6a)
      const span = document.createElement("span");
      span.className = "wort-funk";
      span.textContent = text;
      container.appendChild(span);
    }
  });

  return container;
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
 * Legt einen temporären Hinweis-Span in #ladehinweis-Bereich.
 */
function _zeigeTtsFehler() {
  const existierend = document.getElementById("tts-fehler-hinweis");
  if (existierend) return; // bereits sichtbar
  const hinweis = document.createElement("span");
  hinweis.id = "tts-fehler-hinweis";
  hinweis.className = "tts-fehler-hinweis";
  hinweis.textContent = "Vorlesen geht gerade nicht";
  $ladehinweis.parentElement.appendChild(hinweis);
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

  // KIBUDDY-8: sofortiges Echo
  $btnPtt.classList.add("aktiv");
  startPegel(stream);
  setHeaderStatus("Ich h\xF6re zu…");

  // KIBUDDY-10: Lock-Hinweis nach 800ms
  lockHinweisTimer = setTimeout(() => {
    if (pttState === "recording") {
      $lockHinweis.hidden = false;
    }
  }, CFG.LOCK_HINWEIS_MS);

  // KIBUDDY-7: Max-Aufnahme-Dauer
  maxAufnahmeTimer = setTimeout(() => {
    if (pttState === "recording" || pttState === "locked") {
      stopUndSende(false);
    }
  }, CFG.MAX_AUFNAHME_MS);
}

/** Stoppt Recorder (ohne zu senden) */
function stopRecorder() {
  if (lockHinweisTimer) { clearTimeout(lockHinweisTimer); lockHinweisTimer = null; }
  if (maxAufnahmeTimer) { clearTimeout(maxAufnahmeTimer); maxAufnahmeTimer = null; }
  $lockHinweis.hidden = true;
  $cancelHinweis.hidden = true;
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
 */
async function stopUndSende(abbruch) {
  if (pttState === "idle") return;

  const chunks = aufnahmeChunks.slice();
  const mime   = aufnahmeMimeType;
  stopRecorder();

  if (abbruch) {
    setHeaderStatus("Drück mich, wenn du eine Frage hast");
    return;
  }
  await send_aufnahme(chunks, mime);
}

/** Wechsel in Lock-Modus (KIBUDDY-7 Modus B) */
function einrastenLock() {
  if (pttState !== "recording") return;
  pttState = "locked";
  $lockHinweis.hidden = true;
  if (lockHinweisTimer) { clearTimeout(lockHinweisTimer); lockHinweisTimer = null; }
  $btnPtt.classList.add("locked");
  // Stopp-Knopf zeigen (KIBUDDY-7 "Stopp-Knopf an Slide-Ziel")
  $stoppRow.hidden = false;
  setHeaderStatus("Aufnahme l\xE4uft… Stopp dr\xFCcken zum Senden");
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
