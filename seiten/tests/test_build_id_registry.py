"""Tests fuer T1284 — build_id-Ableiter via PWAM-5-Registry (build_id_for).

Spec-Anker: T1284 AC1/AC2, conventions/pwa-mantel.md PWAM-4/5.

Deckt:
  AC1 — _mini_app_build_id delegiert an pwa_mantel.build_id_for(component, ...)
         via _MINI_APP_JS_TO_COMPONENT (Aequivalenz-Check + Entry-Path-Probe).
  AC1 — heim_shell-Route verwendet build_id_for("shell", ...) statt inline
         getmtime (Entry-Path-Probe).

Lauf: python3 -m pytest seiten/tests/test_build_id_registry.py -x -v
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402  # isort:skip
from seiten import pwa_mantel  # noqa: E402  # isort:skip


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch):
    """Setzt runtime-Dict zurueck (analog test_t1229_build_id_platform_js.py)."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken-t1284",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    monkeypatch.setattr(seiten_main, "hole_panels", list)
    monkeypatch.setattr(seiten_main, "hole_geraete", list)


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — _mini_app_build_id delegiert via Registry ──────────────────────────

def test_mini_app_build_id_routing_tabelle_vollstaendig():
    """AC1: _MINI_APP_JS_TO_COMPONENT enthaelt alle 4 Mini-App-Komponenten."""
    mapping = seiten_main._MINI_APP_JS_TO_COMPONENT
    expected = {
        "essen-einkauf.js":       "einkauf",
        "plan-einstellungen.js":  "plan",
        "mini-app-uebersicht.js": "mini-app-uebersicht",
        "routine-anpassen.js":    "routine",
    }
    for js_name, component in expected.items():
        assert js_name in mapping, \
            f"{js_name!r} fehlt in _MINI_APP_JS_TO_COMPONENT (T1284-AC1)"
        assert mapping[js_name] == component, \
            f"_MINI_APP_JS_TO_COMPONENT[{js_name!r}] = {mapping[js_name]!r}, " \
            f"erwartet {component!r}"
    # Alle Registry-Eintraege muessen in pwa_mantel.REGISTRY vorhanden sein
    for _js_name, component in mapping.items():
        assert component in pwa_mantel.REGISTRY, \
            f"Komponente {component!r} (aus _MINI_APP_JS_TO_COMPONENT) " \
            f"nicht in pwa_mantel.REGISTRY — convention_needed (PWAM-5)"


def test_mini_app_build_id_aequivalent_zu_build_id_for(monkeypatch):
    """AC1: _mini_app_build_id('essen-einkauf.js') == build_id_for('einkauf', static_dir).

    Stellt sicher, dass _mini_app_build_id die PWAM-5-Registry als Single-Source
    nutzt (T1284-AC1), nicht mehr inline getmtime.
    """
    static_dir = os.path.join(_SEITEN_DIR, "static")

    def fake_getmtime(path):
        if path.endswith("essen-einkauf.js"):
            return 400.0
        if path.endswith("platform.js"):
            return 200.0
        raise OSError(f"unerwarteter Pfad: {path}")

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)

    result_helper = seiten_main._mini_app_build_id("essen-einkauf.js")
    result_registry = pwa_mantel.build_id_for("einkauf", static_dir)

    assert result_helper == result_registry, (
        f"_mini_app_build_id und build_id_for('einkauf') weichen ab: "
        f"{result_helper!r} != {result_registry!r} (T1284-AC1)"
    )
    assert result_helper == "400", (
        f"Erwartet '400' (essen-einkauf.js neuer), erhalten {result_helper!r}"
    )


def test_mini_app_build_id_platform_bump_via_registry(monkeypatch):
    """AC1: platform.js-Bump via Registry-Source-Set sichtbar in _mini_app_build_id.

    Bestaetigt, dass build_id_source_set aus REGISTRY['einkauf'] platform.js
    einschliesst — kein hartkodierter Pfad mehr im Helfer.
    """
    def fake_getmtime_platform_neuer(path):
        if path.endswith("essen-einkauf.js"):
            return 300.0
        if path.endswith("platform.js"):
            return 999.0   # platform.js klar neuer
        raise OSError(path)

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime_platform_neuer)

    result = seiten_main._mini_app_build_id("essen-einkauf.js")
    assert result == "999", (
        f"platform.js-Bump (999) nicht sichtbar: {result!r} "
        "(PWAM-5-Registry-Source-Set nicht aktiv)"
    )


# ── AC1 — heim_shell Entry-Path-Probe (kein inline getmtime mehr) ─────────────

def test_heim_shell_build_id_nutzt_shell_registry(monkeypatch, client):
    """AC1 Entry-Path-Probe: GET /shell/<panel_id> — build_id aus REGISTRY['shell'].

    heim-shell.css-Bump setzt neuen ?v=<build_id> in HTML. Die Route darf kein
    inline getmtime mehr enthalten — build_id kommt jetzt aus
    pwa_mantel.build_id_for('shell', static_dir) (T1284-AC1).
    """
    static_dir = os.path.join(_SEITEN_DIR, "static")

    def fake_getmtime(path):
        if path == os.path.join(static_dir, "heim-shell.css"):
            return 777.0
        return 1.0

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)
    monkeypatch.setattr(seiten_main, "_lookup_display_id", lambda panel_id: None)

    resp = client.get("/shell/testpanel")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "?v=777" in body, (
        "?v=777 (heim-shell.css-mtime via REGISTRY['shell']) fehlt in HTML — "
        "T1284-AC1 Entry-Path-Probe heim_shell"
    )
