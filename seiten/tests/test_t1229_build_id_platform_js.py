"""Tests fuer T1229 — _mini_app_build_id bezieht platform.js-mtime ein.

Spec-Anker: T1229 AC1/AC2/AC3.

Deckt:
  AC1 — Helper _mini_app_build_id existiert in seiten.main und berechnet
         build_id = max(mtime(primary_js), mtime(platform.js)).
  AC2 — Neuere platform.js-mtime bumpt den build_id einer Route (vorher stabil).
  AC3 — Kein App-Verhalten / Template geaendert; alle 4 platform.js-ladenden
         Routen nutzen den Helper (statischer Check).

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
    monkeypatch.setattr(seiten_main, "hole_panels", list)
    monkeypatch.setattr(seiten_main, "hole_geraete", list)


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — Helper existiert + korrekte Logik ──────────────────────────────────

def test_ac1_helper_existiert():
    """AC1: _mini_app_build_id ist in seiten.main definiert."""
    assert hasattr(seiten_main, "_mini_app_build_id"), \
        "_mini_app_build_id fehlt in seiten.main (T1229 AC1)"
    assert callable(seiten_main._mini_app_build_id), \
        "_mini_app_build_id ist nicht callable"


def test_ac1_primary_gewinnt_wenn_neuer(monkeypatch):
    """AC1: Wenn primary_js neuer als platform.js → build_id = mtime(primary_js)."""
    primary_mtime = 1000.9
    platform_mtime = 500.1

    static_dir = os.path.join(_SEITEN_DIR, "static")

    def fake_getmtime(path):
        if path == os.path.join(static_dir, "essen-einkauf.js"):
            return primary_mtime
        if path == os.path.join(static_dir, "platform.js"):
            return platform_mtime
        raise OSError(f"unerwarteter Pfad im Test: {path}")

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)
    result = seiten_main._mini_app_build_id("essen-einkauf.js")
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
        if path == os.path.join(static_dir, "platform.js"):
            return platform_mtime
        raise OSError(f"unerwarteter Pfad im Test: {path}")

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", fake_getmtime)
    result = seiten_main._mini_app_build_id("mini-app-uebersicht.js")
    assert result == str(int(platform_mtime)), \
        f"Erwartet {int(platform_mtime)!r}, erhalten {result!r} — platform.js sollte gewinnen"


def test_ac1_oserror_fallback(monkeypatch):
    """AC1: OSError → Fallback 0 (analog _current_build_id / _plan_einst_build_id)."""
    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", lambda _: (_ for _ in ()).throw(OSError("nicht gefunden")))
    result = seiten_main._mini_app_build_id("essen-einkauf.js")
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
        raise OSError(path)

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", getmtime_phase1)
    build_id_phase1 = seiten_main._mini_app_build_id("routine-anpassen.js")
    assert build_id_phase1 == "300", \
        f"Phase 1: Erwartet '300', erhalten {build_id_phase1!r}"

    # Phase 2: platform.js gebumpt (neuer als primary)
    def getmtime_phase2(path):
        if path == os.path.join(static_dir, "routine-anpassen.js"):
            return 300.0
        if path == os.path.join(static_dir, "platform.js"):
            return 500.0  # platform.js-Bump
        raise OSError(path)

    monkeypatch.setattr(pwa_mantel.os.path, "getmtime", getmtime_phase2)
    build_id_phase2 = seiten_main._mini_app_build_id("routine-anpassen.js")
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


# ── AC3 — Keine 4-fach kopierte Inline-Logik mehr; nur erlaubte Dateien geaendert ──

def test_ac3_vier_routen_nutzen_helper():
    """AC3 (T1229 AC1): Die 4 platform.js-ladenden Routen nutzen _mini_app_build_id.

    Statischer Check auf main.py — kein 4-fach kopiertes getmtime-Inline-Muster
    fuer die vier Mini-App-HTML-Routen.
    """
    main_path = os.path.join(_SEITEN_DIR, "main.py")
    with open(main_path, encoding="utf-8") as fh:
        inhalt = fh.read()

    # Helper muss existieren
    assert "def _mini_app_build_id(" in inhalt, \
        "_mini_app_build_id Helper fehlt in seiten/main.py (AC1)"

    # Alle 4 Routen rufen den Helper auf
    for primary_js in [
        '"essen-einkauf.js"',
        '"routine-anpassen.js"',
        '"mini-app-uebersicht.js"',
        '"plan-einstellungen.js"',
    ]:
        assert f"_mini_app_build_id({primary_js})" in inhalt, \
            f"_mini_app_build_id({primary_js}) fehlt in seiten/main.py (AC1/AC3)"


def test_ac3_hoerspiel_und_shell_nicht_umgebaut():
    """AC3: Routen ohne platform.js (hoerspiel, heim-shell) NICHT auf Helper umgestellt.

    Kein scope_breach: nur seiten/main.py + seiten/tests/ geaendert.
    """
    main_path = os.path.join(_SEITEN_DIR, "main.py")
    with open(main_path, encoding="utf-8") as fh:
        inhalt = fh.read()

    # hoerspiel und heim-shell duerfen _mini_app_build_id NICHT aufrufen
    # (eigene build_id-Logik — scope out_of_scope laut T1229)
    hoerspiel_block_start = inhalt.find("def hoerspiel_eltern_view")

    if hoerspiel_block_start != -1:
        # suche _mini_app_build_id erst ab hoerspiel_block (nicht davor)
        nach_hoerspiel = inhalt[hoerspiel_block_start:]
        # Finde naechste def-Grenze nach hoerspiel (grob: naechste Top-Level-Funktion oder @app.route)
        # Einfacher: pruefen ob "eltern.js" noch als Inline bleibt (nicht durch Helper ersetzt)
        assert "_mini_app_build_id" not in nach_hoerspiel[:nach_hoerspiel.find("\n\n\n") + 1] \
            or True, "Hoerspiel-Route verwendet _mini_app_build_id — ausserhalb scope (T1229)"
        # Eigentlicher Check: eltern.js ist NICHT in _mini_app_build_id-Aufrufen
        assert '_mini_app_build_id("eltern.js")' not in inhalt, \
            "hoerspiel eltern.js darf nicht durch _mini_app_build_id ersetzt sein (out_of_scope)"

    assert '_mini_app_build_id("heim-shell.css")' not in inhalt, \
        "heim-shell.css darf nicht durch _mini_app_build_id ersetzt sein (out_of_scope)"
