"""Tests für die Seiten-Registry-HTTP-Schnittstelle (SREG-3, #347, #366).

RAT-31 E3 (#1496): hole_panels/hole_geraete entfernt; Snapshots gibt es nicht mehr.
Die Suite läuft ohne Netz: Manifest-Sorten kommen aus einem tmp-Dir-Root.
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
def client(manifest_root, tmp_path):
    """Flask-Testclient mit tmp inventar.json.

    RAT-31 E3 (#1496): keine Snapshot-Holer-Stubs mehr nötig.
    """
    inventar_path = str(tmp_path / "inventar.json")
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30)
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    c._inventar_path = inventar_path
    return c


def test_healthz_gibt_200(client):
    """SVC-1: GET /healthz liefert immer 200 + ok."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


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


def test_get_seiten_kein_rebuild_innerhalb_ttl(client):
    # SREG-3: nach dem ersten Bau (TTL frisch) löst ein zweiter GET KEINEN
    # weiteren rebuild() aus — er serviert aus inventar.json.
    client.get("/api/v1/seiten")  # baut einmal

    rebuild_aufrufe = {"n": 0}
    orig_rebuild = seiten_main.rebuild

    def _zaehle_rebuild():
        rebuild_aufrufe["n"] += 1
        return orig_rebuild()

    import unittest.mock as mock
    with mock.patch.object(seiten_main, "rebuild", side_effect=_zaehle_rebuild):
        client.get("/api/v1/seiten")  # TTL noch frisch → kein Rebuild
    assert rebuild_aufrufe["n"] == 0, "GET im Request-Pfad darf keinen Rebuild auslösen"


def test_kaltstart_snapshot_pending_leer(manifest_root, tmp_path):
    # RAT-31 E3 (#1496): Kaltstart liefert eintraege + snapshot_pending==[].
    inventar_path = str(tmp_path / "inventar.json")
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30)
    c = seiten_main.app.test_client()
    inv = c.get("/api/v1/seiten").get_json()
    assert inv["eintraege"], "Antwort nie leer (Manifest-Sorten tragen sie)"
    assert inv["snapshot_pending"] == [], "snapshot_pending muss leere Liste sein"


def test_ttl_rebuild_holt_neue_manifeste(manifest_root, tmp_path):
    # SREG-3 Aktualität: nach Ablauf der TTL holt der nächste GET frisch —
    # ein zwischenzeitlich angelegtes Manifest erscheint binnen TTL.
    # TTL=0 → jeder Request baut neu (deterministisch testbar ohne sleep).
    inventar_path = str(tmp_path / "inventar.json")
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=0)
    c = seiten_main.app.test_client()

    inv0 = c.get("/api/v1/seiten").get_json()
    pfade0 = {e["pfad"] for e in inv0["eintraege"]}
    assert "/display/plan/woche" in pfade0

    # Neues Manifest hinzufügen
    _schreibe_manifest(manifest_root, "neu-buddy",
                       [_view("start", "/display/neu-buddy/start")])
    inv1 = c.get("/api/v1/seiten").get_json()
    pfade1 = {e["pfad"] for e in inv1["eintraege"]}
    assert "/display/neu-buddy/start" in pfade1
