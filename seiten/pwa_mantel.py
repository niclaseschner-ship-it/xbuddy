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

import os
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

    # ── ab hier: konsumiert im Manifest-/Skelett-Share-Folgetrack ──
    name: str | None = None                    # PWAM-2 Manifest-Name
    start_url: str | None = None               # PWAM-2 absoluter Präfix (= scope)
    icons: tuple[str, ...] = ()                # PWAM-2 Icon-Set (PNG 192/512/maskable)
    display: str | None = None                 # PWAM-2 fullscreen|standalone
    html_cache_mode: str | None = None         # PWAM-3 HTML_CACHE_MODE
    stop_prefixes: tuple[str, ...] = ()        # PWAM-3 STOP_PREFIXES (SW lässt durch)
    sw_script_route: str | None = None         # PWAM-3 Route, unter der der SW liegt
    sw_scope: str | None = None                # PWAM-3 Scope (muss start_url umfassen)


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
        html_cache_mode="cache-first",
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
        html_cache_mode="cache-first",
        stop_prefixes=(),
        sw_script_route="/seiten/plan/einstellungen/sw.js",
        sw_scope="/seiten/plan/einstellungen/",
    ),
    "connector": MantelConfig(
        # KEIN style.css — Vorbehalt (PWAM-4 offene Frage 2, Set final erst
        # nach Install-/Diff-Probe im connector-Angleich-Folgetrack).
        build_id_source_set=("index.html",),
        name="Connector · KI-Anbieter · XBuddy",
        start_url="/api/v1/seiten/connector/",
        icons=(),                              # PWAM-2: SVG-Drift → PNG-Angleich (Folgetrack)
        display="standalone",
        html_cache_mode="network-only",        # PWAM-3: server-Aggregat nie cache-first
        stop_prefixes=(),
        # PWAM-3 Angleichungs-Ziel: live liefert connector den SW heute noch
        # unter /api/v1/seiten/static/connector/sw.js (Scope-Bruch) — der Fix
        # gehört in den connector-Angleich-Folgetrack, nicht in #1266.
        sw_script_route="/api/v1/seiten/connector/sw.js",
        sw_scope="/api/v1/seiten/connector/",
    ),
    "shell": MantelConfig(
        build_id_source_set=("heim-shell.css",),
        name="Heim-Shell · XBuddy",
        start_url="/shell/<panel_id>",         # dynamisch je panel_id (PWAM-5 offene Frage 3)
        icons=("icon-192.png", "icon-512.png", "icon-maskable-512.png"),
        display="fullscreen",
        html_cache_mode="cache-first",
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
    "routine": MantelConfig(
        build_id_source_set=("routine-anpassen.js", "platform.js"),
    ),
}


def build_id_for(component: str, base_dir: str) -> str:
    """Löst das `build_id_source_set` eines Konsumenten (PWAM-4/5) gegen
    `base_dir` zu absoluten Pfaden auf und liefert die build_id.

    Die Registry trägt nur Dateinamen; `base_dir` kommt vom Aufrufer, damit die
    Test-/Override-Naht (`runtime[..._asset_dir]`, z. B. connector) erhalten
    bleibt. Das ist die „(component)"-Ebene aus PWAM-4 — die eigentliche
    mtime-Rechnung passiert in `build_id_from_mtimes`.
    """
    cfg = REGISTRY[component]
    paths = [os.path.join(base_dir, name) for name in cfg.build_id_source_set]
    return build_id_from_mtimes(paths)
