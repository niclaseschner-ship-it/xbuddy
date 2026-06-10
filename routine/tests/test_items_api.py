"""Tests für GET /api/v1/routine/items (ROUTINE-14, V1.2, #469).

AC1: GET /api/v1/routine/items liefert {"default": [{id, label, piktogramm}, ...],
     "einmalig_heute": [...]}. Test prüft mit Mock-Daten-Konfig.
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import main as main_mod      # noqa: E402  # isort:skip


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def items_get_client(tmp_path):
    """Flask-Test-Client + data_path + store_path für GET /items-Tests."""
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": [
            {"id": "anziehen", "label": "Anziehen", "piktogramm": "👕", "quelle": "default"},
            {"id": "fruehstueck", "label": "Frühstücken", "piktogramm": "🍞", "quelle": "default"},
            {"id": "zaehne-putzen", "label": "Zähne putzen", "piktogramm": "🪥", "quelle": "default"},
        ],
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")
    cfg = config_mod.resolve_data(str(data_file))
    main_mod.configure(cfg, data_path=str(data_file), store_path=store_path)
    return str(data_file), store_path, main_mod.app.test_client()


@pytest.fixture
def items_get_client_mit_einmalig(tmp_path):
    """Flask-Test-Client mit default-Items und einmalig-Items für heute."""
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": [
            {"id": "anziehen", "label": "Anziehen", "piktogramm": "👕", "quelle": "default"},
            {"id": "zaehne-putzen", "label": "Zähne putzen", "piktogramm": "🪥", "quelle": "default"},
        ],
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")

    # einmalig-Item für heute in den Store schreiben
    heute = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
    store_data = {
        "tag": {
            "datum": heute,
            "abgehakt": {},
            "einmalig": [
                {"id": "einmalig:turnbeutel-mit", "label": "Turnbeutel", "piktogramm": "🎒"},
            ],
        }
    }
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(store_data, f)

    cfg = config_mod.resolve_data(str(data_file))
    main_mod.configure(cfg, data_path=str(data_file), store_path=store_path)
    return str(data_file), store_path, main_mod.app.test_client()


# ============================================================
#  AC1 — GET /api/v1/routine/items: Form und Felder
# ============================================================

def test_AC1_get_items_status_200(items_get_client):
    """AC1: GET /api/v1/routine/items → HTTP 200."""
    _, _, client = items_get_client
    resp = client.get("/api/v1/routine/items")
    assert resp.status_code == 200


def test_AC1_get_items_hat_default_und_einmalig_felder(items_get_client):
    """AC1: Antwort enthält 'default' und 'einmalig_heute' (ROUTINE-14, V1.2)."""
    _, _, client = items_get_client
    resp = client.get("/api/v1/routine/items")
    daten = json.loads(resp.data)
    assert "default" in daten, "Antwort muss 'default'-Schlüssel haben"
    assert "einmalig_heute" in daten, "Antwort muss 'einmalig_heute'-Schlüssel haben"


def test_AC1_get_items_default_enthaelt_drei_items(items_get_client):
    """AC1: default enthält 3 Items aus der Konfig."""
    _, _, client = items_get_client
    resp = client.get("/api/v1/routine/items")
    daten = json.loads(resp.data)
    assert len(daten["default"]) == 3


def test_AC1_get_items_default_felder_id_label_piktogramm(items_get_client):
    """AC1: Jedes default-Item hat id, label, piktogramm (ROUTINE-14, V1.2)."""
    _, _, client = items_get_client
    resp = client.get("/api/v1/routine/items")
    daten = json.loads(resp.data)
    for item in daten["default"]:
        assert "id" in item, "default-Item braucht 'id'"
        assert "label" in item, "default-Item braucht 'label'"
        assert "piktogramm" in item, "default-Item braucht 'piktogramm'"


def test_AC1_get_items_default_werte_korrekt(items_get_client):
    """AC1: default-Items enthalten die richtigen id/label/piktogramm-Werte."""
    _, _, client = items_get_client
    resp = client.get("/api/v1/routine/items")
    daten = json.loads(resp.data)
    ids = [item["id"] for item in daten["default"]]
    assert "anziehen" in ids
    assert "fruehstueck" in ids
    assert "zaehne-putzen" in ids

    label_map = {item["id"]: item["label"] for item in daten["default"]}
    assert label_map["anziehen"] == "Anziehen"
    assert label_map["zaehne-putzen"] == "Zähne putzen"


def test_AC1_get_items_einmalig_leer_wenn_kein_store(items_get_client):
    """AC1: einmalig_heute ist leer wenn kein einmalig-Item im Store."""
    _, _, client = items_get_client
    resp = client.get("/api/v1/routine/items")
    daten = json.loads(resp.data)
    assert daten["einmalig_heute"] == []


def test_AC1_get_items_einmalig_gefuellt(items_get_client_mit_einmalig):
    """AC1: einmalig_heute enthält Item aus dem Tages-Store (ROUTINE-8)."""
    _, _, client = items_get_client_mit_einmalig
    resp = client.get("/api/v1/routine/items")
    daten = json.loads(resp.data)
    assert len(daten["einmalig_heute"]) == 1
    item = daten["einmalig_heute"][0]
    assert item["id"] == "einmalig:turnbeutel-mit"
    assert item["label"] == "Turnbeutel"


def test_AC1_get_items_einmalig_felder_id_label_piktogramm(items_get_client_mit_einmalig):
    """AC1: einmalig_heute-Items haben id, label, piktogramm."""
    _, _, client = items_get_client_mit_einmalig
    resp = client.get("/api/v1/routine/items")
    daten = json.loads(resp.data)
    for item in daten["einmalig_heute"]:
        assert "id" in item
        assert "label" in item
        assert "piktogramm" in item


def test_AC1_get_items_reload_on_read(tmp_path):
    """AC1 / DCOMP-3: GET /items liest per-Request frisch aus routine.json.

    Wenn routine.json nach configure() geändert wird, muss die nächste
    GET-Antwort den neuen Stand enthalten — kein Request-übergreifender Cache.
    """
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": [
            {"id": "item-a", "label": "Item A", "piktogramm": "A", "quelle": "default"},
        ],
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")
    cfg = config_mod.resolve_data(str(data_file))
    main_mod.configure(cfg, data_path=str(data_file), store_path=store_path)
    client = main_mod.app.test_client()

    resp1 = client.get("/api/v1/routine/items")
    daten1 = json.loads(resp1.data)
    assert len(daten1["default"]) == 1
    assert daten1["default"][0]["id"] == "item-a"

    # routine.json mit neuem Item überschreiben (wie PUT /config schreiben würde)
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": [
            {"id": "item-a", "label": "Item A", "piktogramm": "A", "quelle": "default"},
            {"id": "item-b", "label": "Item B", "piktogramm": "B", "quelle": "default"},
        ],
        "zeit_referenzen": {"an": False, "paare": []},
    }))

    resp2 = client.get("/api/v1/routine/items")
    daten2 = json.loads(resp2.data)
    # Reload-on-Read: muss jetzt 2 Items liefern
    assert len(daten2["default"]) == 2
    ids = [item["id"] for item in daten2["default"]]
    assert "item-b" in ids
