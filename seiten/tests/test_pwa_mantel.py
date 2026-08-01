"""Tests fuer die PWA-Mantel-Lib (seiten/pwa_mantel.py) — Track #1266.

Konvention: conventions/pwa-mantel.md (PWAM-4/PWAM-5).

Deckt:
  T-LIB-UNIT      — build_id_from_mtimes (max, str(int), OSError→"0"),
                    read_sw_with_build_id (Platzhalter-Ersatz), REGISTRY-Keys.
  T-SW-SOURCESET  — AC3 / Kill-Kriterium: platform.js-Bump invalidiert die
                    einkauf- UND plan-SW-Auslieferung (nicht nur die HTML-Route).
  T-BYTE-DIFF-GATE— AC4 Aequivalenz-Gate: ausgelieferter SW == committed sw.js
                    modulo build_id (KEINE Skelett-Regenerierung — die ist ein
                    deferter Folgetrack, PWAM-4 Sequenz-Hinweis).

Lauf: python3 -m pytest seiten/tests/test_pwa_mantel.py -x -v
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
_STATIC_DIR = os.path.join(_SEITEN_DIR, "static")

sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import pwa_mantel  # noqa: E402

_EINKAUF_SW = "/seiten/essen/einkauf/sw.js"
_PLAN_SW = "/seiten/plan/einstellungen/sw.js"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch):
    """runtime-Dict zuruecksetzen (analog test_essen_einkauf_pwa.py)."""
    rt_snapshot = {
        "bot_token":        seiten_main.runtime.get("bot_token"),
        "init_data_config": seiten_main.runtime.get("init_data_config"),
        "familie_client":   seiten_main.runtime.get("familie_client"),
        "inventar_path":    seiten_main.runtime.get("inventar_path"),
    }
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken-t1266",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    yield
    for key, val in rt_snapshot.items():
        seiten_main.runtime[key] = val


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── T-LIB-UNIT — build_id_from_mtimes ────────────────────────────────────────

def test_build_id_max_gewinnt(monkeypatch):
    """build_id = str(int(max(mtime))) — die spaeteste mtime gewinnt."""
    mtimes = {"/a": 100.9, "/b": 500.1, "/c": 300.0}
    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", lambda p: mtimes[p])
    assert pwa_mantel.build_id_from_mtimes(["/a", "/b", "/c"]) == "500"


def test_build_id_str_int_schneidet_ab(monkeypatch):
    """str(int(...)) — Nachkommastellen werden abgeschnitten, kein Runden."""
    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", lambda _p: 1234.987)
    assert pwa_mantel.build_id_from_mtimes(["/x"]) == "1234"


def test_build_id_oserror_fallback(monkeypatch):
    """Fehlende Datei (OSError) → Fallback "0"."""
    def boom(_p):
        raise OSError("nicht da")
    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", boom)
    assert pwa_mantel.build_id_from_mtimes(["/weg"]) == "0"


# ── T-LIB-UNIT — read_sw_with_build_id ───────────────────────────────────────

def test_read_sw_ersetzt_platzhalter(tmp_path):
    """__BUILD_ID__ wird durch den build_id-Wert ersetzt (pfad-basiert, R2)."""
    sw = tmp_path / "sw.js"
    sw.write_text("const BUILD_ID = '__BUILD_ID__';\n// rest\n", encoding="utf-8")
    out = pwa_mantel.read_sw_with_build_id(str(sw), "4242")
    assert out == "const BUILD_ID = '4242';\n// rest\n"
    assert "__BUILD_ID__" not in out


# ── T-LIB-UNIT — REGISTRY ────────────────────────────────────────────────────

def test_registry_hat_sechs_keys_mit_source_set():
    """PWAM-5: die 9 registrierten Konsumenten, jeder mit build_id_source_set
    (6 Bestand + hoerspiel-player + hoerspiel-eltern + wetter-regeln #1715/ESB-1.a)."""
    assert set(pwa_mantel.REGISTRY) == {
        "einkauf", "plan", "connector", "shell",
        "mini-app-uebersicht", "routine", "hoerspiel-player", "hoerspiel-eltern",
        "wetter-regeln",
    }
    for name, cfg in pwa_mantel.REGISTRY.items():
        assert cfg.build_id_source_set, \
            f"{name}: build_id_source_set ist leer (PWAM-4)"


def test_registry_shell_html_cache_mode_network_first():
    """T1448/AC1: shell-Eintrag traegt html_cache_mode='network-first' (stale-Cache-Fix).

    network-first: Browser holt HTML immer frisch vom Server; Cache dient nur als
    Offline-Fallback. Verhindert das Kleben von stale-Cache trotz Deploy.
    """
    cfg = pwa_mantel.REGISTRY["shell"]
    assert cfg.html_cache_mode == "network-first", (
        "REGISTRY['shell'].html_cache_mode muss 'network-first' sein (T1448-AC1), "
        f"ist: {cfg.html_cache_mode!r}"
    )


def test_render_sw_shell_enthaelt_network_first_logik():
    """T1448/AC1: render_sw('shell') erzeugt SW-JS mit networkFirst-Funktion und -Zweig.

    Belegt, dass das SW-Skelett den network-first-Modus tatsaechlich implementiert
    (nicht nur als Konstante traegt), und dass der Fetch-Handler den Zweig nutzt.
    """
    js = pwa_mantel.render_sw("shell", build_id="test-nf")
    assert "HTML_CACHE_MODE = 'network-first'" in js, (
        "SW muss HTML_CACHE_MODE='network-first' tragen (T1448-AC1)"
    )
    assert "function networkFirst" in js, (
        "SW muss networkFirst-Funktion enthalten (T1448-AC1)"
    )
    assert "HTML_CACHE_MODE === 'network-first'" in js, (
        "Fetch-Handler muss network-first-Zweig enthalten (T1448-AC1)"
    )
    # cache-first darf fuer shell NICHT als Fetch-Strategie greifen
    # (die Funktion cacheFirst existiert weiter fuer andere Konsumenten, das ist OK;
    #  aber der Zweig 'cache-first' && inScope darf nicht die alleinige Strategie sein)
    assert "HTML_CACHE_MODE === 'network-first' && inScope" in js, (
        "network-first-Zweig muss im Fetch-Handler via inScope abgesichert sein (T1448-AC1)"
    )


def test_registry_einkauf_plan_tragen_platform_js():
    """PWAM-4-Kern: einkauf/plan-Source-Set enthaelt platform.js (SW-Fix-Basis)."""
    assert "platform.js" in pwa_mantel.REGISTRY["einkauf"].build_id_source_set
    assert "essen-einkauf.js" in pwa_mantel.REGISTRY["einkauf"].build_id_source_set
    assert "platform.js" in pwa_mantel.REGISTRY["plan"].build_id_source_set
    assert "plan-einstellungen.js" in pwa_mantel.REGISTRY["plan"].build_id_source_set
    # connector traegt style.css + Icons im build_id_source_set (T1365-Angleich,
    # PWAM-4 Vorbehalt erledigt — dies ist der connector-Angleich-Folgetrack).
    assert "style.css" in pwa_mantel.REGISTRY["connector"].build_id_source_set
    assert "icon-192.png" in pwa_mantel.REGISTRY["connector"].build_id_source_set


def test_build_id_for_loest_source_set_gegen_base_dir_auf(monkeypatch):
    """build_id_for resolved die Registry-Dateinamen gegen base_dir und
    delegiert an build_id_from_mtimes (die (component)-Ebene aus PWAM-4)."""
    erwartet = {
        os.path.join("/root", "essen-einkauf.js"): 300.0,
        os.path.join("/root", "platform.js"): 900.0,
    }
    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", lambda p: erwartet[p])
    assert pwa_mantel.build_id_for("einkauf", "/root") == "900"


# ── T-SW-SOURCESET — AC3 / Kill-Kriterium (ueber die SW-ROUTE) ───────────────

def test_sw_sourceset_platform_bump_invalidiert_einkauf_und_plan(monkeypatch, client):
    """AC3: platform.js-Bump aendert den CACHE_NAME der einkauf- UND plan-SW-
    Auslieferung — der Beweis, dass der SW-build_id am Source-Set haengt, nicht
    nur die HTML-Route (T1229 fixte nur HTML). conventions/pwa-mantel.md PWAM-4.

    Der ausgelieferte SW traegt `const BUILD_ID = '<id>';` +
    `const CACHE_NAME = '<prefix>-pwa-' + BUILD_ID;` — der effektive Cache-Name
    ist also <prefix>-pwa-<id>.
    """
    einkauf_js = os.path.join(_STATIC_DIR, "essen-einkauf.js")
    plan_js = os.path.join(_STATIC_DIR, "plan-einstellungen.js")
    platform_js = os.path.join(_STATIC_DIR, "platform.js")

    # Phase 1: primaries neuer (300) als platform.js (100).
    def getmtime_phase1(path):
        if path in (einkauf_js, plan_js):
            return 300.0
        if path == platform_js:
            return 100.0
        return 1.0

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", getmtime_phase1)
    einkauf_p1 = client.get(_EINKAUF_SW).get_data(as_text=True)
    plan_p1 = client.get(_PLAN_SW).get_data(as_text=True)

    assert "const BUILD_ID = '300';" in einkauf_p1
    assert "'einkauf-pwa-' + BUILD_ID" in einkauf_p1
    assert "const BUILD_ID = '300';" in plan_p1
    assert "'plan-einstellungen-pwa-' + BUILD_ID" in plan_p1

    # Phase 2: platform.js gebumpt (500) — jetzt neuer als beide primaries.
    def getmtime_phase2(path):
        if path in (einkauf_js, plan_js):
            return 300.0
        if path == platform_js:
            return 500.0  # platform.js-Bump
        return 1.0

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", getmtime_phase2)
    einkauf_p2 = client.get(_EINKAUF_SW).get_data(as_text=True)
    plan_p2 = client.get(_PLAN_SW).get_data(as_text=True)

    assert "const BUILD_ID = '500';" in einkauf_p2, \
        "einkauf-SW reagiert NICHT auf platform.js-Bump (AC3-Kill-Kriterium verletzt)"
    assert "const BUILD_ID = '500';" in plan_p2, \
        "plan-SW reagiert NICHT auf platform.js-Bump (AC3-Kill-Kriterium verletzt)"
    assert einkauf_p1 != einkauf_p2
    assert plan_p1 != plan_p2


# ── T-BYTE-DIFF-GATE — AC4 Aequivalenz-Gate (NICHT Skelett-Regenerierung) ─────

@pytest.mark.parametrize(("route", "committed_rel"), [
    (_EINKAUF_SW, os.path.join("einkauf", "sw.js")),
    (_PLAN_SW, os.path.join("plan", "sw.js")),
])
def test_byte_diff_gate_served_gleich_committed_modulo_build_id(
        monkeypatch, client, route, committed_rel):
    """AC4: der ausgelieferte SW ist byte-ident zur committed sw.js — bis auf den
    ersetzten __BUILD_ID__-Platzhalter. Belegt: die Zentralisierung aendert KEIN
    Byte am SW ausser dem Cache-Buster.

    ABGRENZUNG: Das ist das Aequivalenz-Gate, NICHT die Skelett-Regenerierung
    (einkauf/generated == committed). Der echte Sharing-Beweis mit static/-Write
    ist ein deferter Folgetrack (PWAM-4 Sequenz-Hinweis).
    """
    # Determin. build_id: getmtime konstant → keine Race, exakter Erwartungswert.
    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", lambda _p: 12345.6)

    with open(os.path.join(_STATIC_DIR, committed_rel), encoding="utf-8") as fh:
        committed = fh.read()
    served = client.get(route).get_data(as_text=True)

    assert "__BUILD_ID__" not in served, "Platzhalter wurde nicht ersetzt"
    assert served == committed.replace("__BUILD_ID__", "12345"), \
        "Ausgelieferter SW weicht ueber den build_id hinaus von der committed sw.js ab"
