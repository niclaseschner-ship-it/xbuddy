"""Tests für die Seiten-Registry-HTTP-Schnittstelle (SREG-3, #347, #366).

Lauf: python3 -m pytest seiten/tests/ -v

Die Suite läuft ohne Netz: die Snapshot-Holer (`hole_panels`/`hole_geraete`,
DCOMP-1) werden gestubbt — kein echter HTTP-Aufruf. Der Endpoint wird über den
Flask-Testclient geprüft (analog panel/tests/, geraete/tests/). Die Manifest-
Sorten kommen aus einem tmp-Dir-Root, NICHT aus echten Buddy-Manifesten.

Entry-Path-Probe (AC-E1): GET /api/v1/seiten → seiten/main.py → inventar.json.
"""

import json
import os
import stat
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402


def _schreibe_manifest(root, app_slug, views, ist_controller=False):
    d = os.path.join(root, "controller", app_slug) if ist_controller \
        else os.path.join(root, app_slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "views.json"), "w", encoding="utf-8") as f:
        json.dump({"views": views}, f)


def _view(slug, pfad, zielgruppe="kind"):
    return {
        "slug": slug, "pfad": pfad, "label": "Label %s" % slug,
        "synonyme": [slug], "zeigt": "Zeigt %s." % slug, "zielgruppe": zielgruppe,
    }


@pytest.fixture
def manifest_root(tmp_path):
    root = str(tmp_path / "repo")
    _schreibe_manifest(root, "plan", [_view("woche", "/display/plan/woche")])
    _schreibe_manifest(root, "wetter",
                       [_view("regeln", "/display/wetter/regeln", "eltern")])
    return root


@pytest.fixture
def client(manifest_root, tmp_path, monkeypatch):
    """Flask-Testclient mit gestubbten Snapshot-Holern + tmp inventar.json.

    Default-Stub: beide Snapshots erreichbar und leer ([]). Einzelne Tests
    überschreiben die Stubs für Ausfall (None) oder gefüllte Snapshots.
    """
    inventar_path = str(tmp_path / "inventar.json")
    monkeypatch.setattr(seiten_main, "hole_panels", list)
    monkeypatch.setattr(seiten_main, "hole_geraete", list)
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30)
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    c._inventar_path = inventar_path
    return c


def test_get_seiten_liefert_manifest_sorten(client):
    # AC-E1 / SREG-3: GET /api/v1/seiten serviert das Inventar.
    resp = client.get("/api/v1/seiten")
    assert resp.status_code == 200
    inv = resp.get_json()
    pfade = {e["pfad"] for e in inv["eintraege"]}
    assert "/display/plan/woche" in pfade
    assert "/display/wetter/regeln" in pfade


def test_get_seiten_persistiert_inventar_json_0600(client):
    # DCOMP-4: inventar.json wird atomar mit 0600 geschrieben.
    client.get("/api/v1/seiten")
    path = client._inventar_path
    assert os.path.exists(path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    with open(path, encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["eintraege"]


def test_get_seiten_kein_upstream_im_request_pfad(client, monkeypatch):
    # SREG-3: nach dem ersten Bau (TTL frisch) löst ein zweiter GET KEINEN
    # weiteren Snapshot-Holer-Aufruf aus — er serviert aus inventar.json.
    client.get("/api/v1/seiten")  # baut einmal

    aufrufe = {"n": 0}

    def _zaehl_panels():
        aufrufe["n"] += 1
        return []

    monkeypatch.setattr(seiten_main, "hole_panels", _zaehl_panels)
    client.get("/api/v1/seiten")  # TTL noch frisch → kein Rebuild
    assert aufrufe["n"] == 0, "GET im Request-Pfad darf keinen Upstream-Call auslösen"


def test_kaltstart_snapshot_pending_nie_leer(manifest_root, tmp_path, monkeypatch):
    # SREG-3 Kaltstart: kein inventar.json + Snapshot-Holer scheitern (None).
    inventar_path = str(tmp_path / "inventar.json")
    monkeypatch.setattr(seiten_main, "hole_panels", lambda: None)
    monkeypatch.setattr(seiten_main, "hole_geraete", lambda: None)
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30)
    c = seiten_main.app.test_client()
    inv = c.get("/api/v1/seiten").get_json()
    assert inv["eintraege"], "Antwort nie leer (Manifest-Sorten tragen sie)"
    assert "panel" in inv["snapshot_pending"]
    assert "display-client" in inv["snapshot_pending"]


def test_ttl_rebuild_holt_neuen_snapshot(manifest_root, tmp_path, monkeypatch):
    # SREG-3 Aktualität: nach Ablauf der TTL holt der nächste GET frisch — ein
    # zwischenzeitlich angelegtes Panel erscheint binnen TTL.
    inventar_path = str(tmp_path / "inventar.json")
    panels_state = {"liste": []}
    monkeypatch.setattr(seiten_main, "hole_panels", lambda: list(panels_state["liste"]))
    monkeypatch.setattr(seiten_main, "hole_geraete", list)
    # TTL=0 → jeder Request baut neu (deterministisch testbar ohne sleep).
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=0)
    c = seiten_main.app.test_client()

    inv0 = c.get("/api/v1/seiten").get_json()
    assert not any(e["typ"] == "panel" for e in inv0["eintraege"])

    panels_state["liste"] = [{"panel_id": "neu-01"}]
    inv1 = c.get("/api/v1/seiten").get_json()
    assert any(e.get("instanz") == "neu-01" for e in inv1["eintraege"])


def test_snapshot_ausfall_stale_statt_leer(manifest_root, tmp_path, monkeypatch):
    # SREG-3: Panel-Snapshot war da, fällt dann aus → stale:true, nicht gekürzt.
    inventar_path = str(tmp_path / "inventar.json")
    panel_state = {"wert": [{"panel_id": "kueche-01"}]}
    monkeypatch.setattr(seiten_main, "hole_panels", lambda: panel_state["wert"])
    monkeypatch.setattr(seiten_main, "hole_geraete", list)
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=0)
    c = seiten_main.app.test_client()

    c.get("/api/v1/seiten")  # erfolgreicher Panel-Snapshot
    panel_state["wert"] = None  # Holer scheitert jetzt
    monkeypatch.setattr(seiten_main, "hole_panels", lambda: None)
    inv = c.get("/api/v1/seiten").get_json()
    panel_e = [e for e in inv["eintraege"] if e["typ"] == "panel"]
    assert panel_e
    assert panel_e[0]["stale"] is True
