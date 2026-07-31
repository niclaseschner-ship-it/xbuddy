"""Tests für die Hörspiel-Player-PWA (HSP-47) — Track A / #1272.

Deckt den seiten-Service-Anteil (Route + Lib-Auslieferung), NICHT das
Player-Frontend (Track B, hoerspiel/**). Der End-to-End-HTML-Render gegen die
echte hoerspiel/templates/player.html ist der Deploy-Gate NACH Track-B-Merge,
nicht hier — deshalb wird die HTML-Route hier nur auf Registrierung geprüft.

  AC1  — Player als 7. REGISTRY-Eintrag + build_manifest (Manifest über die Lib).
  AC2r — seiten-Route (public) liefert Manifest (display:standalone, PNG-Icons)
         + sw.js (__BUILD_ID__ substituiert, 2 Knöpfe); 404-Guard für fremde Assets.

Anker: specs/platform/pwa-mantel-lib.md PWML-1/2, conventions/pwa-mantel.md
PWAM-2/3.

Lauf: python3 -m pytest seiten/tests/test_hoerspiel_player_pwa.py -x -v
"""

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import pwa_mantel  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_COMPONENT = "hoerspiel-player"
_MANIFEST_URL = "/seiten/hoerspiel/player/manifest.json"
_SW_URL = "/seiten/hoerspiel/player/sw.js"
_HTML_URL = "/seiten/hoerspiel/player"

_TEST_BOT_TOKEN = "testtoken-t1272"
_VALID_COOKIE = sc.sign_session("tablet-player-t1272", _TEST_BOT_TOKEN)


@pytest.fixture(autouse=True)
def reset_runtime():
    """seiten-App test-konfigurieren (analog test_pwa_mantel.py)."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token=_TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    return


@pytest.fixture
def client():
    """Test-Client mit vorgesetztem gültigem Cookie (AUTH-2, #1292)."""
    c = seiten_main.app.test_client()
    c.set_cookie(sc.COOKIE_NAME, _VALID_COOKIE)
    return c


# ── AC1 — Registry + build_manifest (Lib-Ebene) ──────────────────────────────

def test_player_ist_siebter_registry_eintrag():
    """AC1: hoerspiel-player ist in pwa_mantel.REGISTRY (8. Eintrag nach T1681 / hoerspiel-eltern)."""
    assert _COMPONENT in pwa_mantel.REGISTRY
    assert len(pwa_mantel.REGISTRY) == 8
    cfg = pwa_mantel.REGISTRY[_COMPONENT]
    assert cfg.build_id_source_set  # PWML-3


def test_build_manifest_display_standalone_und_png_icons():
    """AC1/AC2r: build_manifest liefert display:standalone + NUR PNG-Icons
    (PWML-1 / PWAM-2), mit 192/512/maskable."""
    manifest = pwa_mantel.build_manifest(pwa_mantel.REGISTRY[_COMPONENT])
    assert manifest["display"] == "standalone"
    assert manifest["name"] == "Hörspiel-Player"
    assert manifest["start_url"] == "/seiten/hoerspiel/player"
    icons = manifest["icons"]
    assert icons, "Manifest ohne Icons (PWAM-2)"
    for ic in icons:
        assert ic["type"] == "image/png", f"Nicht-PNG-Icon: {ic}"
        assert ic["src"].endswith(".png")
    sizes_any = {ic["sizes"] for ic in icons if ic["purpose"] == "any"}
    assert {"192x192", "512x512"} <= sizes_any
    assert any(ic["purpose"] == "maskable" for ic in icons)


def test_build_manifest_lehnt_svg_icon_ab():
    """PWML-1 Konformitäts-Gate: SVG-Icon → ValueError (kein stiller Durchlass)."""
    from dataclasses import replace
    kaputt = replace(pwa_mantel.REGISTRY[_COMPONENT], icons=("icon.svg",))
    with pytest.raises(ValueError, match="PWAM-2"):
        pwa_mantel.build_manifest(kaputt)


# ── AC2r — seiten-Route + Asset-Auslieferung ─────────────────────────────────

def test_html_route_registriert():
    """AC2r: die public HTML-Route existiert im url_map (End-to-End-Render =
    Deploy-Gate nach Track B, hier nur Registrierung)."""
    regeln = {r.rule for r in seiten_main.app.url_map.iter_rules()}
    assert _HTML_URL in regeln
    assert "/seiten/hoerspiel/player/<path:asset>" in regeln


def test_manifest_route_liefert_standalone_png(client):
    """AC2r: GET manifest.json → display:standalone + PNG-Icons (application/
    manifest+json), über die Lib erzeugt (kein manifest.json auf Platte)."""
    resp = client.get(_MANIFEST_URL)
    assert resp.status_code == 200
    assert "manifest" in resp.headers["Content-Type"]
    data = json.loads(resp.get_data(as_text=True))
    assert data["display"] == "standalone"
    assert all(ic["type"] == "image/png" for ic in data["icons"])


def test_sw_route_substituiert_build_id_und_traegt_zwei_knoepfe(client):
    """AC2r: GET sw.js → __BUILD_ID__ substituiert + genau die zwei
    load-bearing Config-Knöpfe HTML_CACHE_MODE + STOP_PREFIXES (PWML-2)."""
    resp = client.get(_SW_URL)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "__BUILD_ID__" not in body, "Platzhalter nicht substituiert (PWML-2)"
    assert "const BUILD_ID = '" in body
    # Die zwei Knöpfe aus der Registry.
    assert "const HTML_CACHE_MODE = 'cache-first';" in body
    assert "const STOP_PREFIXES = [\"/api/v1/hoerspiel/\"];" in body
    # PWML-5-Naht vorhanden, aber keine Precache-Logik.
    assert "runtimeCacheResponse" in body
    # no-store, damit der Browser den Worker fresh holt.
    assert "no-store" in resp.headers.get("Cache-Control", "")


def test_unbekanntes_asset_gibt_404(client):
    """AC2r: 404-Guard — ein unbekanntes/fremdes Asset → 404 (nicht 200/500)."""
    resp = client.get("/seiten/hoerspiel/player/gibt-es-nicht.txt")
    assert resp.status_code == 404


def test_traversal_guard_gibt_404(client):
    """AC2r: Path-Traversal über das Asset-Verzeichnis hinaus → 404."""
    resp = client.get("/seiten/hoerspiel/player/..%2f..%2fmain.py")
    assert resp.status_code == 404


# ── AC-T1 (T1320) — Service-Worker-Allowed-Header-Naht (GAP-1 Root-Cause) ───

def test_sw_route_service_worker_allowed_header(client):
    """AC-T1 (T1320): GET /seiten/hoerspiel/player/sw.js setzt den Header
    Service-Worker-Allowed: /seiten/hoerspiel/player.

    Root-Cause-Naht fuer GAP-1 (Watchdog #1320): Ohne diesen Header kann der
    SW seinen Scope /seiten/hoerspiel/player (OHNE abschliessenden Slash) NICHT
    deklarieren — das Dokument bleibt uncontrolled, alle Offline-Promises fallen
    aus. Ein stiller Refactor, der den Header entfernt, soll hier scheitern.

    Anker: seiten/main.py (Z.1064) + hoerspiel/templates/player.html (Z.138).
    Praezedenz-Muster: test_heim_shell.py::test_shell_pwa_ac2_sw_route (SHELL-PWA AC2).
    """
    resp = client.get(_SW_URL)
    assert resp.status_code == 200, "sw.js-Route muss 200 liefern"
    allowed = resp.headers.get("Service-Worker-Allowed", "")
    assert allowed == "/seiten/hoerspiel/player", (
        "Service-Worker-Allowed muss exakt '/seiten/hoerspiel/player' sein — "
        "SW-Scope darf sonst nie das Dokument /seiten/hoerspiel/player decken (GAP-1)."
    )
