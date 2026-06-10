"""Tests für PBE-10 AC1: router_tiles_changed() nach PBE-4-Erfolg (#450).

Abgedeckt:
  test_pbe10_tiles_changed_called_after_successful_put
    — nach 200-Antwort von PUT /tiles wird router_tiles_changed(display_id)
      genau einmal mit der korrekten display_id aufgerufen.
  test_pbe10_tiles_changed_called_with_correct_display_id
    — display_id kommt aus der Panel-Registry (PREG-3), nicht aus der URL.
  test_pbe10_router_unreachable_does_not_crash_no_5xx
    — bei _RouterUnreachable bleibt die 200-Antwort erhalten (graceful,
      DCOMP-2-Fallback ungebrochen, kein Crash, kein 5xx).
  test_pbe10_tiles_changed_not_called_on_404
    — bei unbekannter panel_id (404) wird router_tiles_changed NICHT aufgerufen.
  test_pbe10_tiles_changed_not_called_on_422
    — bei Validierungsfehler (422) wird router_tiles_changed NICHT aufgerufen.

AC4-Latenz (PBE-10): lokaler Round-Trip << 5 s — router_tiles_changed()
sendet einen HTTP-POST an den Router (timeout=5 s); bei erreichbarem
Loopback-Router ist die Latenz typischerweise < 10 ms.

Lauf: python -m pytest panel/tests/test_tiles_changed.py -v
"""

import json
import os
import sys

import pytest

_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main  # noqa: E402
from panel import registry as registry_mod  # noqa: E402

# ============================================================
#  Demo-Daten
# ============================================================

DEMO_PANELS = {
    "panels": [
        {
            "panel_id": "kueche-01",
            "source_id": "app-panel:kueche-01",
            "display_id": "pi-display-flur-01",
            "router_url": "",
            "config": {
                "source_id": "app-panel:kueche-01",
                "display_id": "pi-display-flur-01",
                "router_url": "",
                "backoffs": [200, 1000, 5000],
            },
            "tiles": {
                "tiles": [
                    {
                        "key": "wochenplan",
                        "app": "plan",
                        "view": "woche",
                        "label": "Wochenplan",
                        "icons": ["arasaac/32488.png"],
                        "sichtbar": True,
                    }
                ]
            },
        },
        {
            "panel_id": "flur-01",
            "source_id": "app-panel:flur-01",
            "display_id": "tablet-elias-01",
            "router_url": "",
            "config": {"source_id": "app-panel:flur-01"},
            "tiles": {"tiles": []},
        },
    ]
}

GUELTIGE_TILES = {
    "tiles": [
        {
            "key": "neu",
            "app": "plan",
            "view": "woche",
            "label": "Neu",
            "icons": ["arasaac/32488.png"],
            "sichtbar": True,
        }
    ]
}


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def stub_externe_dienste(monkeypatch):
    """PREG-12: Geräte-Registry + Router-Upsert stubben — kein Netz."""
    monkeypatch.setattr(panel_main, "display_existiert", lambda d: True)
    monkeypatch.setattr(panel_main, "router_panels_upsert", lambda s, d: True)


@pytest.fixture
def demo_instanz(tmp_path):
    p = tmp_path / "panels.json"
    p.write_text(json.dumps(DEMO_PANELS), encoding="utf-8")
    return str(p)


@pytest.fixture
def write_client(demo_instanz, monkeypatch):
    """Schreib-Modus: registry_path gesetzt; router_tiles_changed gestubbt."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, registry_path=demo_instanz, router_url="http://127.0.0.1:9999")
    panel_main.app.testing = True
    return panel_main.app.test_client(), demo_instanz


# ============================================================
#  AC1 — router_tiles_changed() nach erfolgreichem PBE-4-Schreibvorgang
# ============================================================

def test_pbe10_tiles_changed_called_after_successful_put(write_client, monkeypatch):
    """Nach 200-Antwort von PUT /tiles wird router_tiles_changed() genau einmal
    aufgerufen — das SSE-Publish-Signal für PBE-10 wird ausgelöst."""
    client, _path = write_client
    calls = []
    monkeypatch.setattr(panel_main, "router_tiles_changed", lambda did: calls.append(did))

    r = client.put(
        "/api/v1/panels/kueche-01/tiles",
        data=json.dumps(GUELTIGE_TILES),
        content_type="application/json",
    )
    assert r.status_code == 200, r.get_json()
    assert len(calls) == 1, (
        "router_tiles_changed() muss genau einmal aufgerufen werden, "
        f"wurde aber {len(calls)}× aufgerufen."
    )


def test_pbe10_tiles_changed_called_with_correct_display_id(write_client, monkeypatch):
    """router_tiles_changed() erhält die display_id der Panel-Instanz (PREG-3),
    nicht irgendeinen anderen Wert."""
    client, _path = write_client
    calls = []
    monkeypatch.setattr(panel_main, "router_tiles_changed", lambda did: calls.append(did))

    r = client.put(
        "/api/v1/panels/kueche-01/tiles",
        data=json.dumps(GUELTIGE_TILES),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert calls == ["pi-display-flur-01"], (
        f"Erwartete display_id='pi-display-flur-01', bekam: {calls}"
    )


def test_pbe10_tiles_changed_called_with_correct_display_id_second_panel(
    write_client, monkeypatch
):
    """display_id ist panel-spezifisch — zweites Panel liefert seine eigene display_id."""
    client, _path = write_client
    calls = []
    monkeypatch.setattr(panel_main, "router_tiles_changed", lambda did: calls.append(did))

    r = client.put(
        "/api/v1/panels/flur-01/tiles",
        data=json.dumps({"tiles": []}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert calls == ["tablet-elias-01"], (
        f"Erwartete display_id='tablet-elias-01', bekam: {calls}"
    )


# ============================================================
#  AC1 — graceful bei _RouterUnreachable (DCOMP-2 Fallback)
# ============================================================

def test_pbe10_router_unreachable_does_not_crash_no_5xx(write_client, monkeypatch):
    """Wenn router_tiles_changed() eine _RouterUnreachable-Exception wirft,
    bleibt die HTTP-Antwort 200 OK — kein Crash, kein 5xx.
    DCOMP-2 reload-on-read bleibt ungebrochener Fallback (PBE-10 Ausfall-Toleranz)."""
    client, _path = write_client

    def raise_unreachable(did):
        raise panel_main._RouterUnreachable("Test: Router nicht erreichbar")

    monkeypatch.setattr(panel_main, "router_tiles_changed", raise_unreachable)

    r = client.put(
        "/api/v1/panels/kueche-01/tiles",
        data=json.dumps(GUELTIGE_TILES),
        content_type="application/json",
    )
    assert r.status_code == 200, (
        f"Bei _RouterUnreachable muss 200 zurückgegeben werden (DCOMP-2 Fallback), "
        f"bekam: {r.status_code}"
    )
    body = r.get_json()
    assert body.get("ok") is True


# ============================================================
#  AC1 — kein Aufruf bei Fehler-Pfaden (404, 422)
# ============================================================

def test_pbe10_tiles_changed_not_called_on_404(write_client, monkeypatch):
    """Bei unbekannter panel_id (404) wird router_tiles_changed() NICHT aufgerufen —
    nur ein erfolgreicher Schreibvorgang löst das Signal aus."""
    client, _path = write_client
    calls = []
    monkeypatch.setattr(panel_main, "router_tiles_changed", lambda did: calls.append(did))

    r = client.put(
        "/api/v1/panels/unbekannte-id/tiles",
        data=json.dumps(GUELTIGE_TILES),
        content_type="application/json",
    )
    assert r.status_code == 404
    assert calls == [], f"router_tiles_changed darf bei 404 nicht aufgerufen werden, bekam: {calls}"


def test_pbe10_tiles_changed_not_called_on_422(write_client, monkeypatch):
    """Bei Validierungsfehler (422) wird router_tiles_changed() NICHT aufgerufen."""
    client, _path = write_client
    calls = []
    monkeypatch.setattr(panel_main, "router_tiles_changed", lambda did: calls.append(did))

    ungueltig = {"tiles": [{"key": "x", "app": "plan", "icons": []}]}  # leere icons → 422
    r = client.put(
        "/api/v1/panels/kueche-01/tiles",
        data=json.dumps(ungueltig),
        content_type="application/json",
    )
    assert r.status_code == 422
    assert calls == [], f"router_tiles_changed darf bei 422 nicht aufgerufen werden, bekam: {calls}"
