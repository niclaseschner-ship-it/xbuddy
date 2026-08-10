"""Tests fuer T1229 — build_id bezieht platform.js-mtime ein.

Spec-Anker: T1229 AC1/AC2/AC3.

Deckt:
  AC1 — Registry-Mechanismus (pwa_mantel.build_id_for) existiert und berechnet
         build_id = max(mtime(primary_js), mtime(platform.js)).
         T1284: _mini_app_build_id Adapter retired; Tests pruefen build_id_for direkt
         und via Entry-Path (GET-Routen). Kommentar: Grep->Verhalten (#1284).
  AC2 — Neuere platform.js-mtime bumpt den build_id einer Route (vorher stabil).
  AC3 — Alle 4 platform.js-ladenden Routen liefern build_id via build_id_for;
         Entry-Path-Probe per GET. hoerspiel/heim-shell ausserhalb des Scope.

Lauf: python3 -m pytest seiten/tests/test_t1229_build_id_platform_js.py -x -v
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
    """Setzt runtime-Dict zurueck (analog test_mini_app_uebersicht.py)."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken-t1229",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — Registry-Mechanismus existiert + korrekte Logik ────────────────────

def test_ac1_helper_existiert():
    """AC1 (T1284): Registry-Mechanismus fuer build_id existiert.

    pwa_mantel.build_id_for ist callable, REGISTRY enthaelt alle 4 Mini-App-
    Komponenten. T1284: _mini_app_build_id Adapter retired — Pruefung direkt
    auf Registry (Grep->Verhalten, #1284).
    """
    assert callable(pwa_mantel.build_id_for), \
        "pwa_mantel.build_id_for fehlt oder nicht callable (T1229/T1284 AC1)"
    for component in ["einkauf", "plan", "mini-app-uebersicht", "routine"]:
        assert component in pwa_mantel.REGISTRY, \
            f"Komponente {component!r} fehlt in pwa_mantel.REGISTRY (T1229/T1284 AC1)"


def test_ac1_primary_gewinnt_wenn_neuer(monkeypatch):
    """AC1: Wenn primary_js neuer als platform.js → build_id = mtime(primary_js)."""
    primary_mtime = 1000.9
    platform_mtime = 500.1

    static_dir = os.path.join(_SEITEN_DIR, "static")

    def fake_getmtime(path):
        if path == os.path.join(static_dir, "essen-einkauf.js"):
            return primary_mtime
        if path.endswith(".css"):
            return 1.0   # T1813: im Quell-Set, nie das Maximum
        if path == os.path.join(static_dir, "platform.js"):
            return platform_mtime
        raise OSError(f"unerwarteter Pfad im Test: {path}")

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)
    result = pwa_mantel.build_id_for("einkauf", static_dir)
    assert result == str(int(primary_mtime)), \
        f"Erwartet {int(primary_mtime)!r}, erhalten {result!r} — primary_js sollte gewinnen"


def test_ac1_platform_gewinnt_wenn_neuer(monkeypatch):
    """AC1: Wenn platform.js neuer als primary_js → build_id = mtime(platform.js)."""
    primary_mtime = 500.1
    platform_mtime = 1000.9

    static_dir = os.path.join(_SEITEN_DIR, "static")

    def fake_getmtime(path):
        if path == os.path.join(static_dir, "mini-app-uebersicht.js"):
            return primary_mtime
        if path.endswith(".css"):
            return 1.0   # T1813: im Quell-Set, nie das Maximum
        if path == os.path.join(static_dir, "platform.js"):
            return platform_mtime
        raise OSError(f"unerwarteter Pfad im Test: {path}")

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)
    result = pwa_mantel.build_id_for("mini-app-uebersicht", static_dir)
    assert result == str(int(platform_mtime)), \
        f"Erwartet {int(platform_mtime)!r}, erhalten {result!r} — platform.js sollte gewinnen"


def test_ac1_oserror_fallback(monkeypatch):
    """AC1: OSError → Fallback 0 (analog _current_build_id / _plan_einst_build_id)."""
    monkeypatch.setattr(
        pwa_mantel.os.path,
        "getmtime",
        lambda _: (_ for _ in ()).throw(OSError("nicht gefunden")),
    )
    static_dir = os.path.join(_SEITEN_DIR, "static")
    result = pwa_mantel.build_id_for("einkauf", static_dir)
    assert result == "0", f"Erwartet '0', erhalten {result!r}"


# ── AC2 — platform.js-Bump aendert build_id (vorher stabil) ──────────────────

def test_ac2_platform_bump_aendert_build_id(monkeypatch):
    """AC2 (T1229): platform.js mit neuerer mtime → build_id aendert sich.

    Szenario:
      1. primary=300, platform=100 → build_id = "300" (primary gewinnt, stabil)
      2. platform auf 500 gebumpt → build_id = "500" (platform gewinnt jetzt)
    """
    static_dir = os.path.join(_SEITEN_DIR, "static")

    # Phase 1: primary neuer
    def getmtime_phase1(path):
        if path == os.path.join(static_dir, "routine-anpassen.js"):
            return 300.0
        if path == os.path.join(static_dir, "platform.js"):
            return 100.0
        if path.endswith(".css"):
            return 1.0  # T1813: im Quell-Set, nie das Maximum
        raise OSError(path)

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", getmtime_phase1)
    build_id_phase1 = pwa_mantel.build_id_for("routine", static_dir)
    assert build_id_phase1 == "300", \
        f"Phase 1: Erwartet '300', erhalten {build_id_phase1!r}"

    # Phase 2: platform.js gebumpt (neuer als primary)
    def getmtime_phase2(path):
        if path == os.path.join(static_dir, "routine-anpassen.js"):
            return 300.0
        if path == os.path.join(static_dir, "platform.js"):
            return 500.0  # platform.js-Bump
        if path.endswith(".css"):
            return 1.0  # T1813: im Quell-Set, nie das Maximum
        raise OSError(path)

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", getmtime_phase2)
    build_id_phase2 = pwa_mantel.build_id_for("routine", static_dir)
    assert build_id_phase2 == "500", \
        f"Phase 2: Erwartet '500' (platform.js-Bump), erhalten {build_id_phase2!r}"

    assert build_id_phase1 != build_id_phase2, \
        "build_id hat sich nach platform.js-Bump nicht geaendert (T1229 AC2 verletzt)"


def test_ac2_platform_bump_sichtbar_in_route_html(monkeypatch, client):
    """AC2: platform.js-Bump setzt neuen ?v=<build_id> in gerendertem HTML der Route.

    Entry-Path-Probe (T1229): GET Mini-App-Route → build_id in HTML spiegelt
    platform.js-mtime wenn diese neuer ist.
    """
    static_dir = os.path.join(_SEITEN_DIR, "static")

    # platform.js ist der neueste Stand
    def fake_getmtime(path):
        if path == os.path.join(static_dir, "mini-app-uebersicht.js"):
            return 200.0
        if path == os.path.join(static_dir, "platform.js"):
            return 999.0  # platform.js klar neuer
        # Andere getmtime-Aufrufe (z.B. SW-Helfer) duerfen passieren
        return 1.0

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)
    resp = client.get("/api/v1/seiten/mini-app-uebersicht")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "?v=999" in body, \
        "?v=999 (platform.js-mtime) fehlt in HTML — T1229 AC2 / entry_path_probe"


# ── AC3 — Alle vier Routen nutzen build_id_for; Scope-Check ───────────────────

def test_ac3_vier_routen_nutzen_helper(monkeypatch, client):
    """AC3 (T1229 → T1284): Alle vier Routen beziehen build_id aus build_id_for.

    T1284: _mini_app_build_id Adapter retired; Routen rufen build_id_for direkt.
    Verhaltenscheck: Sentinel-mtime → jede Route muss ?v=<sentinel> im HTML ausgeben.
    Kommentar: Grep->Verhalten (#1284, Adapter retired).
    """
    sentinel_mtime = 12345.0
    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", lambda _: sentinel_mtime)

    static_dir = os.path.join(_SEITEN_DIR, "static")

    routes_und_komponenten = [
        ("/seiten/essen/einkauf",              "einkauf"),
        ("/seiten/plan/einstellungen",         "plan"),
        ("/api/v1/seiten/mini-app-uebersicht", "mini-app-uebersicht"),
        ("/seiten/routine/anpassen",           "routine"),
    ]

    for url, component in routes_und_komponenten:
        expected = pwa_mantel.build_id_for(component, static_dir)
        resp = client.get(url)
        assert resp.status_code == 200, \
            f"Route {url!r} gab {resp.status_code} zurueck (erwartet 200)"
        body = resp.get_data(as_text=True)
        assert f"?v={expected}" in body, (
            f"?v={expected!r} fehlt in HTML von {url!r} (component={component!r}) — "
            f"T1229 AC3 / T1284 (Grep->Verhalten, Adapter retired, #1284)"
        )


def test_ac3_hoerspiel_und_shell_nicht_umgebaut():
    """AC3: Scope-Check — hoerspiel eltern.js und heim-shell ausserhalb der vier
    Mini-App-Komponenten. Kein scope_breach: nur seiten/main.py + seiten/tests/ geaendert.

    T1284: Adapter retired. Statischer Check: build_id_for wird NICHT mit
    'eltern'/'heim-shell'-Komponenten fuer die vier Mini-App-Routen aufgerufen.
    """
    main_path = os.path.join(_SEITEN_DIR, "main.py")
    with open(main_path, encoding="utf-8") as fh:
        inhalt = fh.read()

    # hoerspiel eltern-Route nutzt eigene Logik — kein 'eltern'-Eintrag als Mini-App-Komponente
    assert 'build_id_for("eltern' not in inhalt, \
        "build_id_for mit 'eltern'-Komponente gefunden — out_of_scope (T1229 AC3)"

    # heim-shell.css ist in REGISTRY['shell'], nicht als Mini-App-HTML-Route umgebaut
    assert 'build_id_for("heim-shell' not in inhalt, \
        "build_id_for('heim-shell...') gefunden — Scope-Verletzung (T1229 AC3)"
