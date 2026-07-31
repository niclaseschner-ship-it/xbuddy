"""Tests fuer T1284 — build_id-Ableiter via PWAM-5-Registry (build_id_for).

Spec-Anker: T1284 AC1/AC2, conventions/pwa-mantel.md PWAM-4/5.

Deckt:
  AC1 — Alle vier Mini-App-Komponenten sind in pwa_mantel.REGISTRY eingetragen
         (Routing-Vollstaendigkeit). T1284-S2: _mini_app_build_id-Adapter retired;
         Aequivalenz-Checks pruefen build_id_for direkt.
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
from tools.initdata import session_cookie as _sc  # noqa: E402  # isort:skip


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


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — Registry-Vollstaendigkeit + build_id_for-Logik ─────────────────────

def test_mini_app_build_id_routing_tabelle_vollstaendig():
    """AC1: Alle vier Mini-App-Komponenten sind in pwa_mantel.REGISTRY eingetragen.

    T1284-S2: _mini_app_build_id-Adapter retired; _MINI_APP_JS_TO_COMPONENT entfernt.
    Pruefung jetzt direkt auf REGISTRY (Single-Source). PWAM-5-Konvention.
    """
    expected_components = {
        "einkauf":              "essen-einkauf.js",
        "plan":                 "plan-einstellungen.js",
        "mini-app-uebersicht":  "mini-app-uebersicht.js",
        "routine":              "routine-anpassen.js",
    }
    for component, primary_js in expected_components.items():
        assert component in pwa_mantel.REGISTRY, \
            f"Komponente {component!r} fehlt in pwa_mantel.REGISTRY (T1284-AC1 PWAM-5)"
        source_set = pwa_mantel.REGISTRY[component].build_id_source_set
        assert primary_js in source_set, \
            f"pwa_mantel.REGISTRY[{component!r}].build_id_source_set enthaelt {primary_js!r} nicht"
        assert "platform.js" in source_set, \
            f"pwa_mantel.REGISTRY[{component!r}].build_id_source_set enthaelt 'platform.js' nicht"


def test_mini_app_build_id_aequivalent_zu_build_id_for(monkeypatch):
    """AC1: build_id_for('einkauf', static_dir) == max(mtime(essen-einkauf.js), mtime(platform.js)).

    T1284-S2: Adapter retired. Test prueft build_id_for direkt — stellt sicher,
    dass PWAM-5-Registry als Single-Source genutzt wird (kein inline getmtime).
    """
    static_dir = os.path.join(_SEITEN_DIR, "static")

    def fake_getmtime(path):
        if path.endswith("essen-einkauf.js"):
            return 400.0
        if path.endswith("platform.js"):
            return 200.0
        raise OSError(f"unerwarteter Pfad: {path}")

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)

    result = pwa_mantel.build_id_for("einkauf", static_dir)

    assert result == "400", (
        f"Erwartet '400' (essen-einkauf.js neuer), erhalten {result!r} (T1284-AC1)"
    )


def test_mini_app_build_id_platform_bump_via_registry(monkeypatch):
    """AC1: platform.js-Bump via Registry-Source-Set sichtbar in build_id_for.

    Bestaetigt, dass build_id_source_set aus REGISTRY['einkauf'] platform.js
    einschliesst — kein hartkodierter Pfad. T1284-S2: Adapter retired.
    """
    static_dir = os.path.join(_SEITEN_DIR, "static")

    def fake_getmtime_platform_neuer(path):
        if path.endswith("essen-einkauf.js"):
            return 300.0
        if path.endswith("platform.js"):
            return 999.0   # platform.js klar neuer
        raise OSError(path)

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime_platform_neuer)

    result = pwa_mantel.build_id_for("einkauf", static_dir)
    assert result == "999", (
        f"platform.js-Bump (999) nicht sichtbar: {result!r} "
        "(PWAM-5-Registry-Source-Set nicht aktiv, T1284-AC1)"
    )


# ── AC1 — heim_shell Entry-Path-Probe (kein inline getmtime mehr) ─────────────

def test_heim_shell_build_id_nutzt_shell_registry(monkeypatch, client):
    """AC1 Entry-Path-Probe: GET /shell/<panel_id> — build_id aus REGISTRY['shell'].

    heim-shell.css-Bump setzt neuen ?v=<build_id> in HTML. Die Route darf kein
    inline getmtime mehr enthalten — build_id kommt jetzt aus
    pwa_mantel.build_id_for('shell', static_dir) (T1284-AC1).
    T1448: /shell/ ist hard enforced — Operator-IP als Auth-Quelle (opt-in).
    """
    static_dir = os.path.join(_SEITEN_DIR, "static")

    def fake_getmtime(path):
        if path == os.path.join(static_dir, "heim-shell.css"):
            return 777.0
        return 1.0

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)

    # RAT-32: /shell/ ist Cookie-only-hart (Operator-IP gestrichen) — via Cookie auth.
    client.set_cookie(_sc.COOKIE_NAME, _sc.sign_session("testpanel-display", "testtoken-t1284"))
    resp = client.get("/shell/testpanel")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "?v=777" in body, (
        "?v=777 (heim-shell.css-mtime via REGISTRY['shell']) fehlt in HTML — "
        "T1284-AC1 Entry-Path-Probe heim_shell"
    )


# ── T1603 — Shell-build_id aus ALLEN Shell-Assets (CSS + template + JS) ───────

def test_shell_build_id_aendert_sich_bei_html_template_bump(monkeypatch):
    """T1603: shell-build_id bumpt, wenn heim-shell.html (template) neuer ist als CSS.

    Beweist, dass build_id_for('shell', static_dir) die Template-mtime
    (template_source_set=('heim-shell.html',)) einbezieht — eine reine
    HTML-Template-Änderung ohne CSS-Änderung erzeugt eine neue build_id.
    """
    static_dir = os.path.join(_SEITEN_DIR, "static")
    templates_dir = os.path.join(_SEITEN_DIR, "templates")

    def fake_getmtime(path):
        # heim-shell.html hat die höchste mtime — nur die soll die build_id bestimmen.
        if path == os.path.join(templates_dir, "heim-shell.html"):
            return 9999.0
        return 1.0  # alle anderen Quellen (CSS, platform.js, sw.js) sind älter

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)

    result = pwa_mantel.build_id_for("shell", static_dir)

    assert result == "9999", (
        f"T1603: heim-shell.html-Bump (9999) nicht in shell-build_id sichtbar: {result!r}. "
        "REGISTRY['shell'].template_source_set muss 'heim-shell.html' enthalten und "
        "build_id_for() muss Template-mtimes einbeziehen."
    )


def test_shell_registry_enthaelt_alle_shell_quellen():
    """T1603: REGISTRY['shell'] deklariert build_id_source_set + template_source_set vollständig.

    Prueft, dass die drei statischen Quellen (CSS, platform.js, SW-Datei) und die
    Template-Quelle (heim-shell.html) alle eingetragen sind — kein stilles Auslassen.
    """
    cfg = pwa_mantel.REGISTRY["shell"]
    assert "heim-shell.css" in cfg.build_id_source_set, (
        "T1603: 'heim-shell.css' fehlt in REGISTRY['shell'].build_id_source_set"
    )
    assert "platform.js" in cfg.build_id_source_set, (
        "T1603: 'platform.js' fehlt in REGISTRY['shell'].build_id_source_set"
    )
    assert "shell/sw.js" in cfg.build_id_source_set, (
        "T1603: 'shell/sw.js' fehlt in REGISTRY['shell'].build_id_source_set"
    )
    assert "heim-shell.html" in cfg.template_source_set, (
        "T1603: 'heim-shell.html' fehlt in REGISTRY['shell'].template_source_set"
    )
