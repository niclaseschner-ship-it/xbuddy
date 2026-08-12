// Geteilte Daten-Schicht für die Hörspiel-Player-Mockups.
// Lädt die LIVE-Snapshots (mia-alben.json / finn-alben.json / manifest)
// per fetch (über den Mockup-HTTP-Server, relative Pfade — Werft #532).
window.HSP = (function () {
  const COVER = "./assets/cover-default.jpg";
  const state = { kind: "mia", data: { mia: [], finn: [] }, manifest: null };

  // Umschalter-Kinder — Foto liefert 404 (FAM-8 real in der App),
  // Mockup nutzt Initialen-Fallback, Ring-Farbe je Kind.
  const KINDER = {
    mia: { name: "Mia", initiale: "M", ring: "var(--kids-ring-orange, #E58E3F)" },
    finn:  { name: "Finn",  initiale: "F", ring: "#7E6BB0" },
  };

  async function load() {
    const [p, n, m] = await Promise.all([
      fetch("./assets/mia-alben.json").then((r) => r.json()),
      fetch("./assets/finn-alben.json").then((r) => r.json()),
      fetch("./assets/mia-latest-manifest.json").then((r) => r.json()),
    ]);
    // Sortierung: neueste Folge zuerst (Mockup-Default; OPEN-HSP-I offen).
    const byNumDesc = (a, b) => b.nummer - a.nummer;
    state.data.mia = p.sort(byNumDesc);
    state.data.finn = n.sort(byNumDesc);
    state.manifest = m;
    return state;
  }

  // Anreicherung fürs Mockup: das jüngste Album ist "im Player / Resume",
  // die 3 jüngsten sind "hart offline gecached" (HSP-49, N=3).
  function enrich(list) {
    return list.map((al, i) => ({
      ...al,
      cover: COVER,
      cached: i < 3,          // jüngste 3 → Offline-Cache-Badge
      resume: i === 0 ? { track: 2, von: 6 } : null, // jüngste → "Weiter hören"
    }));
  }

  function current() { return state.kind; }
  function kinder() { return KINDER; }
  function alben() { return enrich(state.data[state.kind]); }
  function manifest() { return state.manifest; }
  function setKind(k) { state.kind = k; }

  // Inline-SVG-Icons (Controls sind keine Inhalts-Piktos → SVG statt ARASAAC).
  const ICONS = {
    play:  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>',
    prev:  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>',
    next:  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 6h2v12h-2zM6 18l8.5-6L6 6z"/></svg>',
    gear:  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 8a4 4 0 100 8 4 4 0 000-8zm8.9 4a7 7 0 00-.1-1l2-1.6-2-3.4-2.4 1a7 7 0 00-1.7-1L14.5 2h-5l-.4 2.5a7 7 0 00-1.7 1l-2.4-1-2 3.4L3 9a7 7 0 000 2l-2 1.6 2 3.4 2.4-1a7 7 0 001.7 1L9.5 22h5l.4-2.5a7 7 0 001.7-1l2.4 1 2-3.4-2-1.6c.1-.3.1-.7.1-1z"/></svg>',
    lock:  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a5 5 0 00-5 5v3H6a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2v-8a2 2 0 00-2-2h-1V7a5 5 0 00-5-5zm3 8H9V7a3 3 0 016 0z"/></svg>',
    dl:    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10l3.5-3.5L17 11l-5 5-5-5 1.5-1.5L12 13V3zM5 19h14v2H5z"/></svg>',
  };

  return { load, current, kinder, alben, manifest, setKind, COVER, ICONS };
})();
