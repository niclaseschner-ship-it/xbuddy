"""Routine-Buddy — Routing-Tests für Items-API (ROUTINE-14, #354).

Prüft, dass die drei neuen Endpunkte
  POST   /api/v1/routine/items
  PUT    /api/v1/routine/items
  DELETE /api/v1/routine/items/<id>

in der Flask-App registriert sind und erreichbar (nicht 404/405), sowie
dass existierende Endpunkte unberührt bleiben.

Alle Tests laufen OHNE Netz.
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import main as main_mod      # noqa: E402  # isort:skip
from routine.tests._test_auth import (   # noqa: E402  # isort:skip
    TEST_BOT_TOKEN,
    patch_client_auth,
)
from routine.tests.conftest import mit_session_cookie  # noqa: E402  # isort:skip


# ============================================================
#  Fixtures
# ============================================================

def _make_client(tmp_path):
    """Erzeugt einen Flask-Test-Client mit vollständiger Pfad-Konfiguration."""
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": [
            {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626", "quelle": "default"},
        ],
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")
    cfg = config_mod.resolve_data(str(data_file))
    main_mod.configure(cfg, data_path=str(data_file), store_path=store_path,
                       bot_token=TEST_BOT_TOKEN, init_data_config={"max_age_seconds": 86400})
    client = mit_session_cookie(patch_client_auth(main_mod.app.test_client()))
    return str(data_file), store_path, client


# ============================================================
#  POST /api/v1/routine/items — Registrierung
# ============================================================

def test_routing_post_items_registriert(tmp_path):
    """POST /api/v1/routine/items ist registriert — kein 404/405."""
    _, _, client = _make_client(tmp_path)
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "Routing-Test", "piktogramm": "9"},
                       content_type="application/json")
    assert resp.status_code != 404, "POST /api/v1/routine/items darf kein 404 zurückgeben"
    assert resp.status_code != 405, "POST /api/v1/routine/items darf kein 405 zurückgeben"


def test_routing_post_items_ergibt_201_bei_gueltigem_body(tmp_path):
    """POST /api/v1/routine/items mit gültigem Body → 201 + {"id": ...}."""
    _, _, client = _make_client(tmp_path)
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "RoutingItem", "piktogramm": "8"},
                       content_type="application/json")
    assert resp.status_code == 201
    body = json.loads(resp.data)
    assert "id" in body


def test_routing_post_items_400_bei_leerem_label(tmp_path):
    """POST /api/v1/routine/items ohne label → 400 (Validierung, ROUTINE-14)."""
    _, _, client = _make_client(tmp_path)
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "", "piktogramm": "4"},
                       content_type="application/json")
    assert resp.status_code == 400


def test_routing_post_items_400_bei_kein_json_body(tmp_path):
    """POST /api/v1/routine/items ohne JSON-Body → 400."""
    _, _, client = _make_client(tmp_path)
    resp = client.post("/api/v1/routine/items",
                       data="kein json",
                       content_type="text/plain")
    assert resp.status_code == 400


# ============================================================
#  PUT /api/v1/routine/items — Registrierung
# ============================================================

def test_routing_put_items_registriert(tmp_path):
    """PUT /api/v1/routine/items ist registriert — kein 404/405."""
    _, _, client = _make_client(tmp_path)
    resp = client.put("/api/v1/routine/items",
                      json=[{"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626"}],
                      content_type="application/json")
    assert resp.status_code != 404, "PUT /api/v1/routine/items darf kein 404 zurückgeben"
    assert resp.status_code != 405, "PUT /api/v1/routine/items darf kein 405 zurückgeben"


def test_routing_put_items_200_bei_gueltigem_body(tmp_path):
    """PUT /api/v1/routine/items mit gültigem Array → 200 + {"count": ...}."""
    _, _, client = _make_client(tmp_path)
    resp = client.put("/api/v1/routine/items",
                      json=[{"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626"}],
                      content_type="application/json")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert "count" in body


def test_routing_put_items_400_bei_kein_array(tmp_path):
    """PUT /api/v1/routine/items mit Objekt statt Array → 400."""
    _, _, client = _make_client(tmp_path)
    resp = client.put("/api/v1/routine/items",
                      json={"id": "fruehstueck"},
                      content_type="application/json")
    assert resp.status_code == 400


# ============================================================
#  DELETE /api/v1/routine/items/<id> — Registrierung
# ============================================================

def test_routing_delete_items_registriert(tmp_path):
    """DELETE /api/v1/routine/items/<id> ist registriert — kein 404 (Route) bei vorhandener ID."""
    _, _, client = _make_client(tmp_path)
    # 'fruehstueck' ist in der Fixture vorhanden — 200 erwartet
    resp = client.delete("/api/v1/routine/items/fruehstueck")
    assert resp.status_code == 200


def test_routing_delete_items_404_bei_unbekannter_id(tmp_path):
    """DELETE /api/v1/routine/items/<id> mit unbekannter ID → 404 (ID nicht gefunden)."""
    _, _, client = _make_client(tmp_path)
    resp = client.delete("/api/v1/routine/items/NICHTEXISTENT")
    assert resp.status_code == 404


def test_routing_delete_items_405_bei_put_methode(tmp_path):
    """DELETE-Endpunkt akzeptiert nur DELETE — nicht POST/GET."""
    _, _, client = _make_client(tmp_path)
    resp = client.post("/api/v1/routine/items/fruehstueck")
    assert resp.status_code == 405, \
        "POST auf DELETE-Endpunkt muss 405 Method Not Allowed zurückgeben"


# ============================================================
#  Bestehende Endpunkte unberührt
# ============================================================

def test_routing_bestehende_config_api_erreichbar(tmp_path):
    """PUT /api/v1/routine/config ist weiterhin erreichbar (ROUTINE-14, #343)."""
    _, _, client = _make_client(tmp_path)
    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "08:00"},
                      content_type="application/json")
    assert resp.status_code == 200


def test_routing_bestehende_display_view_erreichbar(tmp_path):
    """GET /display/routine/morgen ist weiterhin erreichbar (ROUTINE-2)."""
    _, _, client = _make_client(tmp_path)
    resp = client.get("/display/routine/morgen")
    assert resp.status_code == 200


def test_routing_items_path_kein_konflikt_mit_config(tmp_path):
    """/api/v1/routine/items und /api/v1/routine/config kollidieren nicht."""
    _, _, client = _make_client(tmp_path)
    # config schreibbar
    r1 = client.put("/api/v1/routine/config",
                    json={"abfahrtszeit": "07:30"},
                    content_type="application/json")
    assert r1.status_code == 200

    # items schreibbar
    r2 = client.post("/api/v1/routine/items",
                     json={"quelle": "default", "label": "Parallel", "piktogramm": "1"},
                     content_type="application/json")
    assert r2.status_code == 201


# ============================================================
#  Entry-Path über Flask-Test-Client (nicht isolierte Funktion)
# ============================================================

def test_routing_entry_path_post_trifft_flask_handler(tmp_path):
    """AC_ENTRY: POST /api/v1/routine/items trifft routine/main.py-Handler.

    Beleg: Flask test_client → HTTP 201 + {"id": ...} (nicht direkt items_mod).
    """
    _, _, client = _make_client(tmp_path)
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "EntryPathTest", "piktogramm": "7"},
                       content_type="application/json")
    assert resp.status_code == 201
    assert "id" in json.loads(resp.data)


def test_routing_entry_path_delete_trifft_flask_handler(tmp_path):
    """AC_ENTRY: DELETE /api/v1/routine/items/<id> trifft routine/main.py-Handler."""
    _, _, client = _make_client(tmp_path)
    resp = client.delete("/api/v1/routine/items/fruehstueck")
    assert resp.status_code == 200
    assert json.loads(resp.data)["id"] == "fruehstueck"


def test_routing_entry_path_put_trifft_flask_handler(tmp_path):
    """AC_ENTRY: PUT /api/v1/routine/items trifft routine/main.py-Handler."""
    _, _, client = _make_client(tmp_path)
    resp = client.put("/api/v1/routine/items",
                      json=[{"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626"}],
                      content_type="application/json")
    assert resp.status_code == 200
    assert json.loads(resp.data)["count"] == 1


# ============================================================
#  ROUTINE-6 Live-View — einmalig-Punkt nach Tageswechsel weg
# ============================================================

def test_routine6_einmalig_nach_tageswechsel_nicht_im_html(tmp_path):
    """ROUTINE-6: GET /display/routine/morgen nach Tageswechsel — einmalig-Punkt NICHT im HTML.

    Live-View-Pfad: Store enthält einmalig-Item mit gestriger Datum.
    Nach Tageswechsel darf das Label nicht mehr im HTML auftauchen.
    """
    import datetime as dt_mod
    _data_file, store_path, client = _make_client(tmp_path)

    # Einmalig-Item anlegen (heute)
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "NurHeute", "piktogramm": "5555"},
                       content_type="application/json")
    assert resp.status_code == 201

    # View heute: Label muss sichtbar sein
    view_heute = client.get("/display/routine/morgen")
    assert view_heute.status_code == 200
    assert "NurHeute" in view_heute.get_data(as_text=True), \
        "einmalig-Item 'NurHeute' muss heute auf der View sichtbar sein"

    # Store-Datum auf gestern setzen (Tageswechsel simulieren)
    gestern = (dt_mod.date.today() - dt_mod.timedelta(days=1)).isoformat()
    with open(store_path, encoding="utf-8") as f:
        store = json.load(f)
    store["tag"]["datum"] = gestern
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(store, f)

    # View nach Tageswechsel: Label darf NICHT mehr sichtbar sein (ROUTINE-6)
    view_morgen = client.get("/display/routine/morgen")
    assert view_morgen.status_code == 200
    assert "NurHeute" not in view_morgen.get_data(as_text=True), \
        "Nach Tageswechsel darf einmalig-Punkt 'NurHeute' nicht mehr im HTML erscheinen (ROUTINE-6)"
