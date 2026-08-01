"""PWA-Mantel-Lib (PWAM-1..5) — zentrale build_id-Ableitung, sw.js-Substitution
und Konsumenten-Registry.

Konvention: conventions/pwa-mantel.md (RATIFIZIERT 2026-07-01, #1215).

Diese Lib zieht die n-fach kopierte Cache-Buster-Mechanik der Mantel-PWAs
(einkauf, plan, connector, shell + die Mini-App-HTML-Routen) in eine Quelle:

  - `build_id_from_mtimes(paths)` — PWAM-4: build_id = höchste mtime eines
    deklarierten Datei-**Sets** (nicht Single-Path). OSError → "0".
  - `read_sw_with_build_id(sw_path, build_id)` — PWAM-4: ersetzt den
    `__BUILD_ID__`-Platzhalter im ausgelieferten Service-Worker. PFAD-basiert
    (R2), damit der realpath-Traversal-Guard + die `runtime[..._asset_dir]`-
    Override-Naht in den Routen (seiten/main.py) erhalten bleiben.
  - `REGISTRY` / `build_id_for(component, base_dir)` — PWAM-5: die *echten*
    Unterschiede als Daten; ein 5. Mantel wird registriert, nicht geforkt.

`os.path.getmtime` wird IN dieser Lib aufgerufen (Test-Seam:
`pwa_mantel.os.path.getmtime` monkeypatchen).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

# ── PWAM-4 — build_id als Source-Set + sw.js-Substitution ────────────────────

def build_id_from_mtimes(paths: list[str]) -> str:
    """build_id = str(int(max(mtime über `paths`))). OSError → "0" (PWAM-4).

    Ein **Set** von Pfaden, kein Single-Path: ein Bump irgendeiner Quelle
    (z. B. platform.js) invalidiert den Cache. Fällt eine Datei weg → "0"
    (Fallback wie zuvor bei den kopierten Ableitern).
    """
    try:
        return str(int(max(os.path.getmtime(p) for p in paths)))
    except OSError:
        return "0"


def read_sw_with_build_id(sw_path: str, build_id: str) -> str:
    """Liest den Service-Worker unter `sw_path`, ersetzt `__BUILD_ID__` durch
    `build_id` und gibt den String zurück (PWAM-4).

    PFAD-basiert (Entscheidung R2): der Aufrufer hat den realpath bereits gegen
    seinen Traversal-Guard + Asset-Root-Override geprüft; diese Lib substituiert
    nur den Platzhalter und trifft KEINE Pfad-Entscheidung.
    """
    with open(sw_path, encoding="utf-8") as fh:
        content = fh.read()
    return content.replace("__BUILD_ID__", build_id)


# ── PWAM-5 — component → config-Registry (registriert, nicht geforkt) ────────

@dataclass(frozen=True)
class MantelConfig:
    """PWAM-5-Config eines Mantel-Konsumenten.

    AKTIV konsumiert in Track #1266:
      - `build_id_source_set` (PWAM-4): über `build_id_for()` der Cache-Buster
        für die SW-/HTML-Auslieferung. Bei einkauf/plan/connector/shell treibt
        es direkt die jeweilige Route; mau/routine tragen es als Daten für die
        generische Mini-App-HTML-Route + den Folgetrack.

    Alle übrigen Felder tragen den vollen PWAM-5-Bauplan (Manifest PWAM-2 +
    Service-Worker PWAM-3) als **Daten**. Sie haben in DIESEM Track noch keinen
    Code-Konsumenten (Routen/Manifest-JSON werden nicht angefasst) und werden
    im Manifest-/Skelett-Share-Folgetrack konsumiert — Registry statt Fork.
    """

    # PWAM-4 — aktiv konsumiert (build_id_for)
    build_id_source_set: tuple[str, ...]
    # T1603: optionale Template-Quellen (Dateinamen relativ zu <base_dir>/../templates/).
    # build_id_for() berechnet max(mtime) über build_id_source_set + template_source_set
    # gemeinsam, sodass eine reine HTML-Template-Änderung die build_id bumpt.
    template_source_set: tuple[str, ...] = ()

    # ── ab hier: konsumiert im Manifest-/Skelett-Share-Folgetrack ──
    name: str | None = None                    # PWAM-2 Manifest-Name
    start_url: str | None = None               # PWAM-2 absoluter Präfix (= scope)
    icons: tuple[str, ...] = ()                # PWAM-2 Icon-Set (PNG 192/512/maskable)
    display: str | None = None                 # PWAM-2 fullscreen|standalone
    html_cache_mode: str | None = None         # PWAM-3 HTML_CACHE_MODE (cache-first|network-first|network-only)
    stop_prefixes: tuple[str, ...] = ()        # PWAM-3 STOP_PREFIXES (SW lässt durch)
    sw_script_route: str | None = None         # PWAM-3 Route, unter der der SW liegt
    sw_scope: str | None = None                # PWAM-3 Scope (muss start_url umfassen)
    short_name: str | None = None              # PWML-1 Manifest short_name (Home-Screen)
    theme_color: str | None = None             # PWML-1 Manifest theme_color (Per-App-Daten)
    background_color: str | None = None        # PWML-1 Manifest background_color (Per-App)


# ── PWML-1 — Manifest-Erzeugung aus Registry-Eintrag ─────────────────────────

def _icon_entries(cfg: MantelConfig) -> list[dict]:
    """Baut die Manifest-`icons`-Liste aus `cfg.icons` (Dateinamen) + start_url.

    PWAM-2-Konformität ist ein HARTER Test-/Boot-Fehler (PWML-1): jedes Icon muss
    ein PNG sein, und das Set muss 192/512 (purpose any) **und** ein maskable-Icon
    tragen. SVG oder ein fehlendes Pflicht-Format → ValueError (kein stiller
    Durchlass).

    `purpose`/`sizes` werden aus dem Dateinamen abgeleitet (Konvention
    `icon-<n>.png` bzw. `icon-maskable-<n>.png`, wie bei einkauf/plan).
    """
    base = (cfg.start_url or "").rstrip("/")
    entries: list[dict] = []
    for fname in cfg.icons:
        if not fname.lower().endswith(".png"):
            raise ValueError(
                f"PWAM-2: Icon {fname!r} ist kein PNG — SVG/fremd nicht erlaubt "
                "(PWML-1 Boot-/Test-Fehler)."
            )
        m = re.search(r"(\d+)", fname)
        if not m:
            raise ValueError(f"PWAM-2: Icon {fname!r} trägt keine Größe im Namen.")
        size = f"{m.group(1)}x{m.group(1)}"
        purpose = "maskable" if "maskable" in fname.lower() else "any"
        entries.append({
            "src": f"{base}/{fname}",
            "sizes": size,
            "type": "image/png",
            "purpose": purpose,
        })
    any_sizes = {e["sizes"] for e in entries if e["purpose"] == "any"}
    if "192x192" not in any_sizes or "512x512" not in any_sizes:
        raise ValueError(
            "PWAM-2: Icon-Set braucht 192x192 UND 512x512 (purpose any) "
            "(PWML-1 Boot-/Test-Fehler)."
        )
    if not any(e["purpose"] == "maskable" for e in entries):
        raise ValueError(
            "PWAM-2: Icon-Set braucht ein maskable-Icon (PWML-1 Boot-/Test-Fehler)."
        )
    return entries


def build_manifest(cfg: MantelConfig) -> dict:
    """Erzeugt das Web-App-Manifest-JSON (als dict) aus einem Registry-Eintrag
    (PWML-1). Alle manifest-tragenden Felder sind **Per-App-Daten aus der
    Registry**, nichts ist im Code hartkodiert.

    Pflicht-Felder (PWML-1): name, short_name, start_url, display, scope,
    theme_color, background_color, icons (PNG 192/512/maskable, PWAM-2).
    Fehlt eines der Per-App-Daten → ValueError (Konformitäts-Gate).
    """
    fehlend = [
        feld for feld, wert in (
            ("name", cfg.name),
            ("start_url", cfg.start_url),
            ("display", cfg.display),
            ("theme_color", cfg.theme_color),
            ("background_color", cfg.background_color),
        ) if not wert
    ]
    if fehlend:
        raise ValueError(
            f"PWML-1: Registry-Eintrag ohne Pflicht-Manifest-Daten: {fehlend}"
        )
    scope = cfg.sw_scope or cfg.start_url
    return {
        "name": cfg.name,
        "short_name": cfg.short_name or cfg.name,
        "start_url": cfg.start_url,
        "scope": scope,
        "display": cfg.display,
        "orientation": "portrait",
        "background_color": cfg.background_color,
        "theme_color": cfg.theme_color,
        "lang": "de",
        "icons": _icon_entries(cfg),
    }


# ── PWML-2 — Ein Service-Worker-Skelett, zwei load-bearing Config-Knöpfe ──────

# Genau ZWEI Config-Knöpfe kommen aus der Registry (PWML-2 / PWAM-3):
# HTML_CACHE_MODE + STOP_PREFIXES. Der Build-Marker `__BUILD_ID__` wird
# server-seitig substituiert (kein statisches `const BUILD='v1'`). PWML-5:
# genau EINE optionale Runtime-Cache-Naht (`runtimeCacheResponse`), n=1 (Player),
# ohne Precache-Logik — Track B / HSP-54 klinkt sich hier ein.
_SW_SKELETON = """// sw.js — PWA-Mantel-Skelett (PWML-2 / PWAM-3), generiert von
// seiten/pwa_mantel.render_sw() für Konsument %%COMPONENT%%.
//
// Genau ZWEI load-bearing Config-Knöpfe (aus pwa_mantel.REGISTRY):
//   HTML_CACHE_MODE — cacht der Mantel-SW die HTML-Shell?
//                     'cache-first'   — Cache schlägt zuerst zu (Offline + schnell)
//                     'network-first' — Netz zuerst, Cache-Fallback bei Netz-Fehler
//                                       (HTML immer frisch, Offline-Fallback erhalten)
//                     'network-only'  — immer Netz (kein HTML-Cache)
//   STOP_PREFIXES   — Pfade, die der Mantel-SW UNBERÜHRT durchlässt (eigene SWs /
//                     Streaming-Daten, die nie veralten dürfen).
// __BUILD_ID__ wird beim Ausliefern von seiten/main.py substituiert (PWML-2).

'use strict';

const BUILD_ID = '__BUILD_ID__';
const CACHE_NAME = '%%COMPONENT%%-pwa-' + BUILD_ID;

// ── PWML-2 Knopf 1 ──
const HTML_CACHE_MODE = '%%HTML_CACHE_MODE%%';
// ── PWML-2 Knopf 2 ──
const STOP_PREFIXES = %%STOP_PREFIXES%%;

const SCOPE = '%%SCOPE%%';
const START_URL = '%%START_URL%%';

self.addEventListener('install', (event) => {
  // Mantel-Skelett precached nur die Shell (start_url); App-Assets kommen
  // network-first dazu. Best-effort — ein Fehler blockiert den Install nicht.
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.add(START_URL).catch(() => {})
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Alle Cache-Namespaces dieses Konsumenten mit fremdem BUILD_ID löschen.
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('%%COMPONENT%%-pwa-') && k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

function isStopped(url) {
  // STOP_PREFIXES: unberührt durchlassen (Streaming/API/fremde SWs).
  return STOP_PREFIXES.some((p) => url.pathname.startsWith(p));
}

function inScope(url) {
  return url.pathname === START_URL || url.pathname.startsWith(SCOPE);
}

function cacheFirst(req) {
  return caches.match(req).then((cached) => {
    if (cached) return cached;
    return fetch(req).then((res) => {
      if (res && res.ok) {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    });
  });
}

function networkFirst(req) {
  // Netz zuerst — HTML immer frisch; bei Netz-Fehler Cache-Fallback (Offline).
  return fetch(req).then((res) => {
    if (res && res.ok) {
      const copy = res.clone();
      caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
    }
    return res;
  }).catch(() => caches.match(req).then((cached) => cached || Response.error()));
}

// ── PWML-5 — optionale App-Runtime-Cache-Naht (n=1, HSP-54) ──
// Default: kein Eingriff (null). Track B kann diese Funktion via zusätzlichem
// importScripts()/Zuweisung überschreiben, um z. B. Folgen-Audio zu cachen —
// OHNE das Skelett zu forken. Hier bewusst KEINE Precache-/Strategie-Logik.
self.runtimeCacheResponse = self.runtimeCacheResponse || null;

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (isStopped(url)) return;  // pass-through

  // PWML-5-Naht: App-spezifisches Runtime-Caching zuerst (falls eingehängt).
  if (typeof self.runtimeCacheResponse === 'function') {
    const handled = self.runtimeCacheResponse(event, url);
    if (handled) { event.respondWith(handled); return; }
  }

  // Mantel-Shell: HTML_CACHE_MODE entscheidet, ob der Mantel HTML/Assets cacht.
  if (HTML_CACHE_MODE === 'cache-first' && inScope(url)) {
    event.respondWith(cacheFirst(req));
    return;
  }
  if (HTML_CACHE_MODE === 'network-first' && inScope(url)) {
    // Netz zuerst — HTML ist immer frisch; offline fällt auf Cache zurück.
    event.respondWith(networkFirst(req));
    return;
  }
  // network-only / außerhalb Scope: pass-through (kein respondWith).
});
"""


def render_sw(component: str, build_id: str | None = None) -> str:
    """Rendert das sw.js-Skelett (PWML-2) für `component` aus REGISTRY.

    Nur die zwei load-bearing Knöpfe (HTML_CACHE_MODE, STOP_PREFIXES) + Scope-
    Daten des Konsumenten werden eingesetzt. `__BUILD_ID__` bleibt Platzhalter,
    solange `build_id` None ist (server-seitige Substitution beim Ausliefern);
    ist `build_id` gesetzt, wird er direkt substituiert.

    NUR neuer Player-Pfad: einkauf/plan behalten ihre committed sw.js
    (byte-frozen) — dieser Renderer erzeugt deren SW NICHT (E-PWML-1).
    """
    cfg = REGISTRY[component]
    js = (
        _SW_SKELETON
        .replace("%%COMPONENT%%", component)
        .replace("%%HTML_CACHE_MODE%%", cfg.html_cache_mode or "network-only")
        .replace("%%STOP_PREFIXES%%", json.dumps(list(cfg.stop_prefixes)))
        .replace("%%SCOPE%%", cfg.sw_scope or cfg.start_url or "/")
        .replace("%%START_URL%%", cfg.start_url or "/")
    )
    if build_id is not None:
        js = js.replace("__BUILD_ID__", build_id)
    return js


# Registrierte Konsumenten (conventions/pwa-mantel.md PWAM-1-Tabelle).
# build_id_source_set: Dateinamen relativ zum jeweiligen Asset-Root (der
# Aufrufer liefert den Root an build_id_for — connector ist Override-aware).
REGISTRY: dict[str, MantelConfig] = {
    # ── Voll-Mäntel (manifest.json + sw.js auf Platte) ──
    "einkauf": MantelConfig(
        build_id_source_set=("essen-einkauf.js", "platform.js"),
        name="XBuddy Einkaufsliste",
        start_url="/seiten/essen/einkauf/",
        icons=("icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        display="fullscreen",
        # network-first: HTML frisch vom Server (Stale-Cache-Härtung #1455);
        # Offline-Fallback bleibt über den Cache erhalten.
        html_cache_mode="network-first",
        stop_prefixes=(),
        sw_script_route="/seiten/essen/einkauf/sw.js",
        sw_scope="/seiten/essen/einkauf/",
    ),
    "plan": MantelConfig(
        build_id_source_set=("plan-einstellungen.js", "platform.js"),
        name="Plan-Einstellungen · XBuddy",
        start_url="/seiten/plan/einstellungen/",
        icons=("icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        display="fullscreen",
        # network-first: HTML frisch vom Server (Stale-Cache-Härtung #1455);
        # Offline-Fallback bleibt über den Cache erhalten.
        html_cache_mode="network-first",
        stop_prefixes=(),
        sw_script_route="/seiten/plan/einstellungen/sw.js",
        sw_scope="/seiten/plan/einstellungen/",
    ),
    "connector": MantelConfig(
        # PWAM-4: build_id trackt alle precachten MANTEL_ASSETS (sw.js, style.css,
        # Icons) — ändert sich einer, bumpt build_id → SW wechselt Cache-Namespace.
        # Logos (SVG unter logos/) sind bewusst ausgelassen: selten geändert, kein
        # eigener PWAM-Install-Pfad. index.html bleibt Anker für den HTML-Buster.
        # (T1365-Befund-2: Vorbehalt erledigt.)
        build_id_source_set=("index.html", "style.css",
                             "icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        name="Connector · KI-Anbieter · XBuddy",
        start_url="/api/v1/seiten/connector/",
        # PWAM-2: connector fährt File-Manifest (manifest.json auf Platte ist SSoT);
        # build_manifest() wird NICHT aufgerufen. icons spiegelt das manifest.json
        # für Registry-Konsistenz — nicht der generative Pfad wie bei einkauf/plan.
        # (T1365-Befund-3: PNG-Angleich erledigt.)
        icons=("icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        display="standalone",
        html_cache_mode="network-only",        # PWAM-3: server-Aggregat nie cache-first
        stop_prefixes=(),
        # PWAM-3: SW liegt unter /static/ (Flask-static-Prefix); Browser registriert
        # via sw_scope mit Service-Worker-Allowed-Header (connector_sw_view, main.py).
        # (T1365-Befund-1: sw_script_route auf realen Serve-Pfad gezogen.)
        sw_script_route="/api/v1/seiten/static/connector/sw.js",
        sw_scope="/api/v1/seiten/connector/",
    ),
    "shell": MantelConfig(
        # T1603: build_id aus ALLEN Shell-Assets — CSS + platform.js + sw.js
        # (static/) + heim-shell.html (templates/ via template_source_set).
        # Jede Änderung an Shell-Logik/Style/Template bumpt die build_id und
        # macht den SW-Byte-Fingerprint ungültig → Browser zieht neuen SW.
        build_id_source_set=("heim-shell.css", "platform.js", "shell/sw.js"),
        template_source_set=("heim-shell.html",),
        name="Heim-Shell · XBuddy",
        start_url="/shell/<panel_id>",         # dynamisch je panel_id (PWAM-5 offene Frage 3)
        icons=("icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        display="fullscreen",
        # network-first: HTML immer frisch vom Server (stale-Cache-Fix, T1448);
        # bei Netz-Fehler greift Cache-Fallback (Offline bleibt nutzbar).
        html_cache_mode="network-first",
        stop_prefixes=("/controller/", "/display/"),  # PWAM-3: Panel-Iframes durchlassen
        sw_script_route="/shell/<panel_id>/sw.js",
        sw_scope="/shell/",
    ),
    # ── Mini-Apps ohne installierbaren Mantel (kein manifest.json/sw.js auf
    #    Platte). Sie tragen NUR build_id_source_set (HTML-Cache-Buster, T1229);
    #    Manifest-/SW-Felder bleiben None — kein Fork, keine Vorrats-Route. ──
    "mini-app-uebersicht": MantelConfig(
        build_id_source_set=("mini-app-uebersicht.js", "platform.js"),
    ),
    # ── ROUTINE-20/23 (T1665) — vollstaendiger Voll-Mantel via Lib (PWAM-5) ──
    #    Manifest via build_manifest(), sw.js via render_sw() — kein manifest.json/
    #    sw.js auf Platte. Icons aus seiten/static/routine/ (V1-Platzhalter aus plan,
    #    eigenes Motiv als Mini-Folge). Auth: tma (MAD-7).
    "routine": MantelConfig(
        build_id_source_set=("routine-anpassen.js", "platform.js"),
        name="Morgenroutine anpassen · XBuddy",
        short_name="Routine",
        start_url="/seiten/routine/anpassen/",
        icons=("icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        display="fullscreen",
        theme_color="#47503C",
        background_color="#F5F1E8",
        # network-first: HTML frisch vom Server (Stale-Cache-Haertung analog plan);
        # Offline-Fallback bleibt ueber den Cache erhalten.
        html_cache_mode="network-first",
        stop_prefixes=(),
        sw_script_route="/seiten/routine/anpassen/sw.js",
        sw_scope="/seiten/routine/anpassen/",
    ),
    # ── Hörspiel-Eltern (T1681 / ESB-1) — eltern-facing PWA-Mantel ──
    #    Eigenstaendiger Mantel NEBEN hoerspiel-player (Kind-Sorte).
    #    Route: /seiten/hoerspiel/<kind_id>/eltern (per-kind_id).
    #    Manifest via build_manifest(), sw.js via render_sw() — kein Platte-Fork.
    #    Icons: wiederverwendet aus hoerspiel/static/ (192/512/maskable, Motiv-Folge offen).
    #    start_url/scope kanonisch ohne kind_id-Segment: der Mantel gilt fuer alle
    #    Eltern-Instanzen — eltern.js laedt kind_id aus location.pathname.
    #    Auth: HTML-Shell public (MAD-7); Datenrouten AUTH-3-hart (@require_init_data, ESB-2).
    "hoerspiel-eltern": MantelConfig(
        build_id_source_set=("eltern.js", "eltern.css"),
        name="Hörspiel verwalten · XBuddy",
        short_name="Hörspiel",
        start_url="/seiten/hoerspiel/mia/eltern",
        icons=("icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        display="fullscreen",
        theme_color="#47503C",
        background_color="#F5F1E8",
        # network-first: HTML frisch vom Server (Stale-Cache-Haertung analog routine/plan);
        # Offline-Fallback bleibt ueber den Cache erhalten.
        html_cache_mode="network-first",
        stop_prefixes=("/api/v1/hoerspiel/",),
        sw_script_route="/seiten/hoerspiel/mia/eltern/sw.js",
        sw_scope="/seiten/hoerspiel/",
    ),
    # ── Hörspiel-Player (HSP-47) — erster Voll-Konsument ÜBER die Lib ──
    #    Manifest via build_manifest(), sw.js via render_sw() (kein sw.js/
    #    manifest.json auf Platte). Assets (player.{css,js} + Icons) liefert
    #    der hoerspiel-Buddy aus hoerspiel/static/, gehostet vom seiten-Service.
    "hoerspiel-player": MantelConfig(
        build_id_source_set=("player.js", "player.css"),
        name="Hörspiel-Player",
        short_name="Hörspiel",
        start_url="/seiten/hoerspiel/player",
        icons=("icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        display="standalone",
        theme_color="#47503C",
        background_color="#F5F1E8",
        # HTML-Shell offline-fähig (installierbarer Player); die Folgen-Daten +
        # Audio kommen über /api/v1/hoerspiel/ und bleiben UNBERÜHRT (STOP) —
        # nie veralten, und der harte Audio-Cache (HSP-54) hängt an der PWML-5-
        # Naht, nicht am Mantel.
        html_cache_mode="cache-first",
        stop_prefixes=("/api/v1/hoerspiel/",),
        sw_script_route="/seiten/hoerspiel/player/sw.js",
        sw_scope="/seiten/hoerspiel/player",
    ),
}


def build_id_for(component: str, base_dir: str) -> str:
    """Löst das `build_id_source_set` eines Konsumenten (PWAM-4/5) gegen
    `base_dir` zu absoluten Pfaden auf und liefert die build_id.

    Die Registry trägt nur Dateinamen; `base_dir` kommt vom Aufrufer, damit die
    Test-/Override-Naht (`runtime[..._asset_dir]`, z. B. connector) erhalten
    bleibt. Das ist die „(component)"-Ebene aus PWAM-4 — die eigentliche
    mtime-Rechnung passiert in `build_id_from_mtimes`.

    T1603: `template_source_set` (Dateinamen relativ zu `<base_dir>/../templates/`)
    wird ebenfalls in die max(mtime)-Rechnung einbezogen. Ändert sich eine
    Template-Datei ohne zugehörige Static-Datei, bumpt build_id trotzdem.
    """
    cfg = REGISTRY[component]
    paths = [os.path.join(base_dir, name) for name in cfg.build_id_source_set]
    if cfg.template_source_set:
        templates_dir = os.path.join(os.path.dirname(base_dir), "templates")
        paths += [os.path.join(templates_dir, name) for name in cfg.template_source_set]
    return build_id_from_mtimes(paths)
