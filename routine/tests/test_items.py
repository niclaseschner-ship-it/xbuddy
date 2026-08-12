"""Routine-Buddy — Tests für Items-API (ROUTINE-14, #354).

Abdeckung:
  AC1  POST /api/v1/routine/items mit quelle=default + label + piktogramm
       fügt Item zu routine.json hinzu; ID stabil (ROUTINE-5)
  AC2  POST /api/v1/routine/items mit quelle=einmalig schreibt in einmalig-Store;
       ID-Präfix einmalig:; heute lesbar, nach Tageswechsel automatisch weg (ROUTINE-6)
  AC3  PUT /api/v1/routine/items/<id> ändert label/piktogramm;
       DELETE entfernt Item (default + einmalig)
  AC4  ROUTINE-19 max-8: POST liefert HTTP 400 + ehrlichen Fehler wenn >=8 Items
  AC5  Self-Gate (pytest grün inkl. test_items.py, hier implizit)

Alle Tests laufen OHNE Netz.
"""

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import items as items_mod    # noqa: E402  # isort:skip
from routine import main as main_mod      # noqa: E402  # isort:skip
from routine.tests._test_auth import (   # noqa: E402  # isort:skip
    TEST_BOT_TOKEN,
    patch_client_auth,
)
from routine.tests.conftest import mit_session_cookie  # noqa: E402  # isort:skip


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def items_client(tmp_path):
    """Flask-Test-Client + data_path + store_path für Items-API-Tests."""
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": [
            {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626", "quelle": "default"},
            {"id": "zaehne", "label": "Zähne putzen", "piktogramm": "2326", "quelle": "default"},
        ],
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")
    cfg = config_mod.resolve_data(str(data_file))
    main_mod.configure(cfg, data_path=str(data_file), store_path=store_path,
                       bot_token=TEST_BOT_TOKEN, init_data_config={"max_age_seconds": 86400})
    client = mit_session_cookie(patch_client_auth(main_mod.app.test_client()))
    return str(data_file), store_path, client


@pytest.fixture
def volle_liste_client(tmp_path):
    """Flask-Test-Client mit genau 8 default-Items (für ROUTINE-19-Klemme)."""
    items_8 = [
        {"id": "item%d" % i, "label": "Item %d" % i, "piktogramm": str(1000 + i), "quelle": "default"}
        for i in range(8)
    ]
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": items_8,
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")
    cfg = config_mod.resolve_data(str(data_file))
    main_mod.configure(cfg, data_path=str(data_file), store_path=store_path,
                       bot_token=TEST_BOT_TOKEN, init_data_config={"max_age_seconds": 86400})
    return str(data_file), store_path, patch_client_auth(main_mod.app.test_client())


# ============================================================
#  AC1 — POST quelle=default fügt in routine.json hinzu
# ============================================================

def test_ac1_post_default_item_persistiert_in_json(items_client):
    """AC1: POST quelle=default schreibt neues Item in routine.json."""
    data_path, _, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "Turnbeutel", "piktogramm": "9999"},
                       content_type="application/json")
    assert resp.status_code == 201
    body = json.loads(resp.data)
    assert "id" in body
    new_id = body["id"]

    # In routine.json nachweisen
    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    ids = [item["id"] for item in gespeichert["items"]]
    assert new_id in ids, "Neue default-ID %r muss in routine.json stehen" % new_id


def test_ac1_post_default_id_stabil_und_kein_einmalig_praefix(items_client):
    """AC1/ROUTINE-5: default-ID trägt kein 'einmalig:'-Präfix."""
    _, _, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "Hausaufgaben", "piktogramm": "1234"},
                       content_type="application/json")
    assert resp.status_code == 201
    new_id = json.loads(resp.data)["id"]
    assert not new_id.startswith("einmalig:"), \
        "default-ID darf nicht mit 'einmalig:' beginnen (ROUTINE-5)"


def test_ac1_post_default_id_stabil_aus_label(items_client):
    """AC1/ROUTINE-5: default-ID wird aus Label erzeugt (slug, stabil)."""
    _, _, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "Zähne putzen extra", "piktogramm": "2326"},
                       content_type="application/json")
    assert resp.status_code == 201
    new_id = json.loads(resp.data)["id"]
    assert new_id, "ID muss gesetzt sein"
    # ID enthält nur sichere Zeichen
    import re
    assert re.fullmatch(r"[a-z0-9-]+", new_id), \
        "default-ID soll nur Kleinbuchstaben, Ziffern und Bindestriche enthalten"


def test_ac1_post_default_id_keine_kollision_mit_vorhandener(items_client):
    """AC1/ROUTINE-5: doppelter Slug → eindeutige ID (z.B. zaehne-2)."""
    _, _, client = items_client
    # "zaehne" ist bereits in der Fixture-Liste
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "Zähne", "piktogramm": "2326"},
                       content_type="application/json")
    assert resp.status_code == 201
    new_id = json.loads(resp.data)["id"]
    assert new_id != "zaehne", \
        "ID-Kollision mit vorhandener 'zaehne'-ID — muss eindeutig sein (ROUTINE-5)"


def test_ac1_post_default_reload_on_read_sichtbar(items_client):
    """AC1: neues default-Item ist per Reload-on-Read auf /display/routine/morgen sichtbar."""
    _, _, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "Sportsachen", "piktogramm": "5555"},
                       content_type="application/json")
    assert resp.status_code == 201

    # View neu laden — neues Label muss sichtbar sein
    view_resp = client.get("/display/routine/morgen")
    assert view_resp.status_code == 200
    body = view_resp.get_data(as_text=True)
    assert "Sportsachen" in body, \
        "Neues default-Item 'Sportsachen' muss nach POST per Reload-on-Read sichtbar sein"


# ============================================================
#  AC2 — POST quelle=einmalig schreibt in Store; ID-Präfix einmalig:
# ============================================================

def test_ac2_post_einmalig_item_id_praefix(items_client):
    """AC2/ROUTINE-5: einmalig-Item trägt 'einmalig:'-Präfix in der ID."""
    _, _, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "Turnbeutel", "piktogramm": "8888"},
                       content_type="application/json")
    assert resp.status_code == 201
    new_id = json.loads(resp.data)["id"]
    assert new_id.startswith("einmalig:"), \
        "einmalig-ID muss mit 'einmalig:' beginnen (ROUTINE-5), war: %r" % new_id


def test_ac2_post_einmalig_nicht_in_routine_json(items_client):
    """AC2: einmalig-Item landet NICHT in routine.json, sondern im Store."""
    data_path, _, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "Schachbrett", "piktogramm": "7777"},
                       content_type="application/json")
    assert resp.status_code == 201

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    labels = [item.get("label") for item in gespeichert.get("items", [])]
    assert "Schachbrett" not in labels, \
        "einmalig-Item darf nicht in routine.json stehen (ROUTINE-8)"


def test_ac2_post_einmalig_in_store_heute(items_client):
    """AC2: einmalig-Item ist im Store unter heutigem Tag gespeichert."""
    _, store_path, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "Gitarre", "piktogramm": "6666"},
                       content_type="application/json")
    assert resp.status_code == 201
    new_id = json.loads(resp.data)["id"]

    # Direkt im Store prüfen
    with open(store_path, encoding="utf-8") as f:
        store = json.load(f)
    einmalig = store.get("tag", {}).get("einmalig", [])
    ids_im_store = [e.get("id") for e in einmalig]
    assert new_id in ids_im_store, \
        "einmalig-ID %r muss im Store stehen" % new_id


def test_ac2_post_einmalig_heute_lesbar_auf_view(items_client):
    """AC2: einmalig-Item ist heute auf /display/routine/morgen sichtbar."""
    _, _, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "Schwimmsachen", "piktogramm": "4321"},
                       content_type="application/json")
    assert resp.status_code == 201

    view_resp = client.get("/display/routine/morgen")
    assert view_resp.status_code == 200
    body = view_resp.get_data(as_text=True)
    assert "Schwimmsachen" in body, \
        "einmalig-Item 'Schwimmsachen' muss heute auf /display/routine/morgen sichtbar sein"


def test_ac2_einmalig_tageswechsel_automatisch_weg(items_client):
    """AC2/ROUTINE-6: einmalig-Item nach Tageswechsel automatisch weg."""
    _, store_path, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "Vergängliches", "piktogramm": "1111"},
                       content_type="application/json")
    assert resp.status_code == 201

    # Store mit gestriger Datum manipulieren (Tageswechsel simulieren)
    import datetime as dt_mod
    with open(store_path, encoding="utf-8") as f:
        store = json.load(f)
    gestern = (dt_mod.date.today() - dt_mod.timedelta(days=1)).isoformat()
    store["tag"]["datum"] = gestern
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(store, f)

    # Nach Tageswechsel: load_einmalig_heute muss leere Liste liefern
    einmalig_nach_wechsel = items_mod.load_einmalig_heute(store_path, "Europe/Berlin")
    assert einmalig_nach_wechsel == [], \
        "Nach Tageswechsel müssen einmalig-Items automatisch weg sein (ROUTINE-6)"


def test_ac2_einmalig_id_keine_kollision_mit_default(items_client):
    """AC2/ROUTINE-5: einmalig:-Präfix kollidiert nie mit default-IDs."""
    _, _, client = items_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "Frühstück", "piktogramm": "4626"},
                       content_type="application/json")
    assert resp.status_code == 201
    new_id = json.loads(resp.data)["id"]
    # ID beginnt mit einmalig: — kann nie mit default-ID 'fruehstueck' kollidieren
    assert new_id.startswith("einmalig:"), \
        "einmalig-Item mit gleich lautendem Label muss 'einmalig:'-Präfix tragen"
    assert new_id != "fruehstueck", \
        "einmalig-Item darf nicht dieselbe ID wie default-Item haben (ROUTINE-5)"


# ============================================================
#  AC3 — PUT (Bulk-Replace) und DELETE
# ============================================================

def test_ac3_delete_default_item(items_client):
    """AC3: DELETE /api/v1/routine/items/<id> entfernt default-Item aus routine.json."""
    data_path, _, client = items_client
    resp = client.delete("/api/v1/routine/items/fruehstueck")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body.get("id") == "fruehstueck"

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    ids = [item["id"] for item in gespeichert["items"]]
    assert "fruehstueck" not in ids, \
        "'fruehstueck' muss nach DELETE aus routine.json entfernt sein"


def test_ac3_delete_einmalig_item(items_client):
    """AC3: DELETE /api/v1/routine/items/<id> entfernt einmalig-Item aus Store."""
    _, store_path, client = items_client
    # Erst anlegen
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "Löschen-Test", "piktogramm": "9998"},
                       content_type="application/json")
    assert resp.status_code == 201
    new_id = json.loads(resp.data)["id"]

    # Dann löschen
    del_resp = client.delete("/api/v1/routine/items/%s" % new_id)
    assert del_resp.status_code == 200
    assert json.loads(del_resp.data)["id"] == new_id

    # Aus Store verschwunden
    einmalig = items_mod.load_einmalig_heute(store_path, "Europe/Berlin")
    ids_im_store = [e.get("id") for e in einmalig]
    assert new_id not in ids_im_store, \
        "einmalig-ID %r muss nach DELETE aus Store entfernt sein" % new_id


def test_ac3_delete_nicht_vorhandene_id_gibt_404(items_client):
    """AC3: DELETE auf nicht vorhandene ID → 404."""
    _, _, client = items_client
    resp = client.delete("/api/v1/routine/items/NICHTEXISTENT")
    assert resp.status_code == 404


def test_ac3_put_ersetzt_default_liste(items_client):
    """AC3: PUT /api/v1/routine/items ersetzt die default-Liste (Reihenfolge)."""
    data_path, _, client = items_client
    neue_liste = [
        {"id": "rucksack", "label": "Rucksack", "piktogramm": "2475"},
        {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626"},
    ]
    resp = client.put("/api/v1/routine/items",
                      json=neue_liste,
                      content_type="application/json")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body.get("count") == 2

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    ids = [item["id"] for item in gespeichert["items"]]
    assert ids == ["rucksack", "fruehstueck"], \
        "PUT muss die genaue Reihenfolge der neuen Liste persistieren"


def test_ac3_put_leere_liste_entfernt_alle_items(items_client):
    """AC3: PUT mit leerer Liste → alle default-Items entfernt."""
    data_path, _, client = items_client
    resp = client.put("/api/v1/routine/items",
                      json=[],
                      content_type="application/json")
    assert resp.status_code == 200

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    assert gespeichert["items"] == []


def test_ac3_put_bewahrt_nicht_items_felder(items_client):
    """AC3: PUT überschreibt nur items, nicht z.B. abfahrtszeit."""
    data_path, _, client = items_client
    neue_liste = [{"id": "rucksack", "label": "Rucksack", "piktogramm": "2475"}]
    client.put("/api/v1/routine/items", json=neue_liste,
               content_type="application/json")

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    assert "abfahrtszeit" in gespeichert, \
        "PUT darf abfahrtszeit nicht aus routine.json entfernen"


def test_ac3_put_reload_on_read_sichtbar(items_client):
    """AC3: nach PUT ist die neue Reihenfolge auf /display/routine/morgen sichtbar."""
    _, _, client = items_client
    neue_liste = [
        {"id": "zaehne", "label": "Zähne putzen", "piktogramm": "2326"},
        {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626"},
    ]
    client.put("/api/v1/routine/items", json=neue_liste,
               content_type="application/json")

    view_resp = client.get("/display/routine/morgen")
    assert view_resp.status_code == 200
    body = view_resp.get_data(as_text=True)
    # Beide Labels sichtbar
    assert "Zähne putzen" in body
    assert "Frühstück" in body


# ============================================================
#  AC4 — ROUTINE-19 max-8 Klemme
# ============================================================

def test_ac4_post_bei_acht_items_gibt_400(volle_liste_client):
    """AC4/ROUTINE-19: POST bei 8 vorhandenen Items → 400 + ehrlicher Fehler."""
    _, _, client = volle_liste_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "Überflüssig", "piktogramm": "9999"},
                       content_type="application/json")
    assert resp.status_code == 400, \
        "ROUTINE-19: POST bei >=8 Items muss 400 zurückgeben"
    body = json.loads(resp.data)
    assert "error" in body, "400-Antwort muss einen 'error'-Schlüssel enthalten"
    # Ehrlicher Fehler: enthält Hinweis auf max. Punkte
    assert "8" in body["error"] or "maximal" in body["error"].lower() or \
           "Maximal" in body["error"], \
           "Fehlermeldung soll Hinweis auf Maximal-8-Klemme enthalten (ROUTINE-19)"


def test_ac4_post_einmalig_bei_acht_gibt_400(volle_liste_client):
    """AC4/ROUTINE-19: POST quelle=einmalig bei 8 vorhandenen Items → 400."""
    _, _, client = volle_liste_client
    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "einmalig", "label": "Einmaliger Überschuss", "piktogramm": "1"},
                       content_type="application/json")
    assert resp.status_code == 400


def test_ac4_post_kein_schreiben_bei_klemme(volle_liste_client):
    """AC4/ROUTINE-19: kein Teil-Write wenn Klemme greift."""
    data_path, _, client = volle_liste_client
    with open(data_path, encoding="utf-8") as f:
        vorher_items = json.load(f)["items"]

    client.post("/api/v1/routine/items",
                json={"quelle": "default", "label": "Kein Write", "piktogramm": "9999"},
                content_type="application/json")

    with open(data_path, encoding="utf-8") as f:
        nachher_items = json.load(f)["items"]
    assert len(nachher_items) == len(vorher_items), \
        "Bei ROUTINE-19-Klemme darf kein Item in routine.json geschrieben werden"


def test_ac4_put_mit_mehr_als_8_gibt_400(items_client):
    """AC4/ROUTINE-19: PUT mit >8 Items → 400, kein Schreiben."""
    _, _, client = items_client
    zu_viele = [
        {"id": "item%d" % i, "label": "Item %d" % i, "piktogramm": "1000"}
        for i in range(9)
    ]
    resp = client.put("/api/v1/routine/items", json=zu_viele,
                      content_type="application/json")
    assert resp.status_code == 400


def test_ac4_grenzfall_post_bei_sieben_items_gibt_201_und_datei_hat_acht(tmp_path):
    """AC4 Happy-Path-Grenzfall: POST mit 7 vorhandenen Items → 201 + Datei hat danach 8 Items."""
    items_7 = [
        {"id": "item%d" % i, "label": "Item %d" % i, "piktogramm": str(1000 + i), "quelle": "default"}
        for i in range(7)
    ]
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": items_7,
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")
    import routine.config as _cfg
    import routine.main as _main
    cfg = _cfg.resolve_data(str(data_file))
    _main.configure(cfg, data_path=str(data_file), store_path=store_path,
                    bot_token=TEST_BOT_TOKEN, init_data_config={"max_age_seconds": 86400})
    client = patch_client_auth(_main.app.test_client())

    resp = client.post("/api/v1/routine/items",
                       json={"quelle": "default", "label": "Achter Punkt", "piktogramm": "9999"},
                       content_type="application/json")
    assert resp.status_code == 201, \
        "POST bei 7 Items muss 201 liefern — Grenzfall noch unter Klemme (ROUTINE-19)"

    with open(str(data_file), encoding="utf-8") as f:
        gespeichert = json.load(f)
    assert len(gespeichert["items"]) == 8, \
        "Nach POST mit 7 vorhandenen Items muss die Datei genau 8 Items enthalten"


def test_ac4_grenzfall_put_mit_acht_items_gibt_200(tmp_path):
    """AC4 Happy-Path-Grenzfall: PUT mit Liste der Länge 8 → 200 (genau an der Grenze)."""
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": [],
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")
    import routine.config as _cfg
    import routine.main as _main
    cfg = _cfg.resolve_data(str(data_file))
    _main.configure(cfg, data_path=str(data_file), store_path=store_path,
                    bot_token=TEST_BOT_TOKEN, init_data_config={"max_age_seconds": 86400})
    client = patch_client_auth(_main.app.test_client())

    genau_acht = [
        {"id": "item%d" % i, "label": "Item %d" % i, "piktogramm": str(1000 + i)}
        for i in range(8)
    ]
    resp = client.put("/api/v1/routine/items",
                      json=genau_acht,
                      content_type="application/json")
    assert resp.status_code == 200, \
        "PUT mit genau 8 Items muss 200 liefern — Grenzfall erlaubt (ROUTINE-19)"


# ============================================================
#  Validierungs-Einheit (items_mod direkt)
# ============================================================

def test_items_add_item_leeres_label_wirft_error(tmp_path):
    """ItemsError bei leerem Label."""
    data_path = str(tmp_path / "routine.json")
    store_path = str(tmp_path / "store.json")
    with pytest.raises(items_mod.ItemsError, match="label"):
        items_mod.add_item(data_path, store_path, "default", "", "4626")


def test_items_add_item_ungueltiger_quelle_wirft_error(tmp_path):
    """ItemsError bei ungültigem quelle-Wert."""
    data_path = str(tmp_path / "routine.json")
    store_path = str(tmp_path / "store.json")
    with pytest.raises(items_mod.ItemsError, match="quelle"):
        items_mod.add_item(data_path, store_path, "bedingt", "Test", "4626")


def test_items_delete_nicht_vorhandene_id_wirft_error(tmp_path):
    """ItemsError wenn ID nicht gefunden."""
    data_path = str(tmp_path / "routine.json")
    store_path = str(tmp_path / "store.json")
    with pytest.raises(items_mod.ItemsError, match="nicht gefunden"):
        items_mod.delete_item(data_path, store_path, "NICHTEXISTENT")


def test_items_replace_duplikat_ids_wirft_error(tmp_path):
    """ItemsError bei doppelten IDs in replace_default_items."""
    data_path = str(tmp_path / "routine.json")
    duplikat_liste = [
        {"id": "test", "label": "Test 1", "piktogramm": "1"},
        {"id": "test", "label": "Test 2", "piktogramm": "2"},
    ]
    with pytest.raises(items_mod.ItemsError, match="doppelte"):
        items_mod.replace_default_items(data_path, duplikat_liste)


def test_items_add_default_atomares_schreiben(tmp_path):
    """AC1/DCOMP-4: add_item schreibt atomar — Zieldatei nach Aufruf gültig lesbar."""
    data_path = str(tmp_path / "routine.json")
    store_path = str(tmp_path / "store.json")
    import pathlib
    pathlib.Path(data_path).write_text(json.dumps({"items": []}))

    items_mod.add_item(data_path, store_path, "default", "AtomTest", "9999")

    with open(data_path, encoding="utf-8") as f:
        inhalt = json.load(f)
    assert any(i.get("label") == "AtomTest" for i in inhalt["items"])


def test_load_einmalig_heute_ist_public(tmp_path):
    """AC2-Public: load_einmalig_heute ist ohne Underscore-Präfix aufrufbar (Befund 3)."""
    store_path = str(tmp_path / "store.json")
    # Funktion direkt ohne Underscore aufrufen — kein AttributeError erlaubt
    result = items_mod.load_einmalig_heute(store_path, "Europe/Berlin")
    assert result == [], "load_einmalig_heute ohne Store → leere Liste (kein Fehler)"
    # Altes privates API darf nicht mehr existieren
    assert not hasattr(items_mod, "_load_einmalig_heute"), \
        "_load_einmalig_heute darf nicht mehr als privates Attribut existieren (Befund 3)"


def test_items_einmalig_prafix_kollidiert_nie_mit_default(tmp_path):
    """ROUTINE-5: einmalig:-Präfix garantiert Nicht-Kollision mit default-IDs."""
    data_path = str(tmp_path / "routine.json")
    store_path = str(tmp_path / "store.json")
    import pathlib
    pathlib.Path(data_path).write_text(json.dumps({"items": [
        {"id": "turnbeutel", "label": "Turnbeutel", "piktogramm": "1", "quelle": "default"},
    ]}))

    result = items_mod.add_item(data_path, store_path, "einmalig", "Turnbeutel", "1")
    assert result["id"].startswith("einmalig:"), \
        "einmalig-Item muss 'einmalig:'-Präfix tragen — kollidiert nicht mit 'turnbeutel'"
    assert result["id"] != "turnbeutel"


# ============================================================
#  Entry-Path-Probe (write_proof Einheit)
# ============================================================

def test_write_proof_default_pfad(tmp_path):
    """Entry-Path-Probe: add_item(default) schreibt nachweislich in data_path.

    before: Datei ohne den neuen Eintrag.
    after: Datei enthält neues Item mit 'probe'-Label.
    """
    data_path = str(tmp_path / "routine.json")
    store_path = str(tmp_path / "store.json")
    import pathlib
    pathlib.Path(data_path).write_text(json.dumps({"items": []}))

    before_size = pathlib.Path(data_path).stat().st_size
    items_mod.add_item(data_path, store_path, "default", "probe", "arasaac/2484")
    after_content = pathlib.Path(data_path).read_text()

    assert "probe" in after_content, \
        "write_proof data_path: 'probe' muss in routine.json stehen"
    after_size = pathlib.Path(data_path).stat().st_size
    assert after_size > before_size, \
        "write_proof data_path: Datei muss nach Schreiben größer sein"


def test_write_proof_store_pfad(tmp_path):
    """Entry-Path-Probe: add_item(einmalig) schreibt nachweislich in store_path.

    before: store_path nicht vorhanden.
    after: store_path existiert und enthält das neue einmalig-Item.
    """
    data_path = str(tmp_path / "routine.json")
    store_path = str(tmp_path / "einmalig_store.json")
    import pathlib
    pathlib.Path(data_path).write_text(json.dumps({"items": []}))

    assert not pathlib.Path(store_path).exists(), "Store sollte vor Schreiben nicht existieren"
    items_mod.add_item(data_path, store_path, "einmalig", "probe-einmalig", "arasaac/2484")
    after_content = pathlib.Path(store_path).read_text()

    assert "probe-einmalig" in after_content, \
        "write_proof store_path: 'probe-einmalig' muss in routine_store.json stehen"


# ============================================================
#  V2 AC1 — zeit-Sub-Block-Validierung (ROUTINE-24, ROUTINE-25)
# ============================================================

import pytest  # noqa: E402  # isort:skip — V2-Block am Ende


class TestV2ZeitBlockValidierung:
    """ROUTINE-24/25: drei zulässige zeit-Block-Formen, ungültig → ItemsError."""

    def test_v2_zeit_none_passiert(self):
        """zeit=None → kein Fehler, kein zeit-Feld im Item."""
        assert items_mod._validate_zeit_block("x", None) is None

    def test_v2_zeit_anker_minimal_kanonisiert(self):
        out = items_mod._validate_zeit_block(
            "x", {"typ": "anker", "uhrzeit": "07:30"})
        assert out == {"typ": "anker", "uhrzeit": "07:30", "locked": False}

    def test_v2_zeit_anker_locked_durchgereicht(self):
        out = items_mod._validate_zeit_block(
            "x", {"typ": "anker", "uhrzeit": "08:00", "locked": True})
        assert out["locked"] is True

    def test_v2_zeit_anker_uhrzeit_fehlt_4xx(self):
        with pytest.raises(items_mod.ItemsError, match="uhrzeit"):
            items_mod._validate_zeit_block("x", {"typ": "anker"})

    def test_v2_zeit_anker_uhrzeit_format_kaputt_4xx(self):
        """Kein HH:MM-Pattern → 4xx mit HH:MM-Hinweis."""
        with pytest.raises(items_mod.ItemsError, match="HH:MM"):
            items_mod._validate_zeit_block(
                "x", {"typ": "anker", "uhrzeit": "halbsieben"})

    def test_v2_zeit_anker_uhrzeit_24h_overflow_4xx(self):
        """Stunden außerhalb 00–23 → 4xx mit Stunden-Hinweis (regex passt, aber Bereich nein)."""
        with pytest.raises(items_mod.ItemsError, match="Stunden"):
            items_mod._validate_zeit_block(
                "x", {"typ": "anker", "uhrzeit": "25:00"})

    def test_v2_zeit_vorlauf_minimal_kanonisiert(self):
        out = items_mod._validate_zeit_block(
            "x", {"typ": "vorlauf", "minuten": 10})
        assert out == {"typ": "vorlauf", "minuten": 10, "bezug": "vorheriger_anker"}

    def test_v2_zeit_vorlauf_minuten_negativ_4xx(self):
        with pytest.raises(items_mod.ItemsError, match="≥ 0"):
            items_mod._validate_zeit_block(
                "x", {"typ": "vorlauf", "minuten": -5})

    def test_v2_zeit_vorlauf_minuten_kein_int_4xx(self):
        with pytest.raises(items_mod.ItemsError, match="Integer"):
            items_mod._validate_zeit_block(
                "x", {"typ": "vorlauf", "minuten": "fuenf"})

    def test_v2_zeit_typ_unbekannt_4xx(self):
        with pytest.raises(items_mod.ItemsError, match="anker"):
            items_mod._validate_zeit_block(
                "x", {"typ": "unsinn", "uhrzeit": "07:00"})

    def test_v2_zeit_kein_dict_4xx(self):
        with pytest.raises(items_mod.ItemsError, match="Objekt"):
            items_mod._validate_zeit_block("x", "07:00")

    def test_v2_zeit_bezug_unbekannt_4xx(self):
        # ROUTINE-24 erlaubt jetzt vorheriger_anker UND naechster_anker (#1070).
        # Ungültig bleibt jeder andere Wert.
        with pytest.raises(items_mod.ItemsError, match="bezug"):
            items_mod._validate_zeit_block(
                "x", {"typ": "vorlauf", "minuten": 5, "bezug": "irgendwas_anderes"})

    def test_v2_zeit_bezug_naechster_anker_gueltig(self):
        # Nic-Setzung 2026-06-22 #1070: naechster_anker = V1-Anziehen-Semantik.
        normalized = items_mod._validate_zeit_block(
            "x", {"typ": "vorlauf", "minuten": 5, "bezug": "naechster_anker"})
        assert normalized == {"typ": "vorlauf", "minuten": 5, "bezug": "naechster_anker"}


# ============================================================
#  V2 AC1 — API-Pfade akzeptieren zeit-Block (ROUTINE-25)
# ============================================================


class TestV2ApiZeitBlock:
    """ROUTINE-25: PUT /items + POST /items akzeptieren zeit; ungültig → 4xx."""

    def test_v2_put_items_mit_zeit_persistiert(self, items_client):
        """PUT mit zeit-Block schreibt zeit in routine.json."""
        data_path, _, client = items_client
        neue = [
            {"id": "auf", "label": "Aufstehen", "piktogramm": "8152",
             "zeit": {"typ": "anker", "uhrzeit": "07:00", "locked": True}},
            {"id": "zaehne", "label": "Zähne", "piktogramm": "2326",
             "zeit": {"typ": "vorlauf", "minuten": 5,
                      "bezug": "vorheriger_anker"}},
        ]
        resp = client.put("/api/v1/routine/items", json=neue,
                          content_type="application/json")
        assert resp.status_code == 200

        with open(data_path, encoding="utf-8") as f:
            gespeichert = json.load(f)
        assert gespeichert["items"][0]["zeit"]["uhrzeit"] == "07:00"
        assert gespeichert["items"][1]["zeit"]["minuten"] == 5

    def test_v2_put_items_mit_kaputtem_zeit_4xx(self, items_client):
        """PUT mit ungültigem zeit-Block → 400, kein Schreiben."""
        _, _, client = items_client
        neue = [
            {"id": "kaputt", "label": "K", "piktogramm": "1",
             "zeit": {"typ": "anker"}},  # uhrzeit fehlt
        ]
        resp = client.put("/api/v1/routine/items", json=neue,
                          content_type="application/json")
        assert resp.status_code == 400

    def test_v2_post_item_mit_zeit_persistiert(self, items_client):
        data_path, _, client = items_client
        resp = client.post(
            "/api/v1/routine/items",
            json={"quelle": "default", "label": "Schuhe", "piktogramm": "1234",
                  "zeit": {"typ": "vorlauf", "minuten": 5,
                           "bezug": "vorheriger_anker"}},
            content_type="application/json",
        )
        assert resp.status_code == 201
        new_id = json.loads(resp.data)["id"]

        with open(data_path, encoding="utf-8") as f:
            gespeichert = json.load(f)
        match = [i for i in gespeichert["items"] if i["id"] == new_id]
        assert match
        assert match[0]["zeit"]["minuten"] == 5

    def test_v2_post_item_mit_kaputtem_zeit_4xx(self, items_client):
        _, _, client = items_client
        resp = client.post(
            "/api/v1/routine/items",
            json={"quelle": "default", "label": "K", "piktogramm": "1",
                  "zeit": {"typ": "vorlauf", "minuten": -3}},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_v2_get_items_liefert_zeit_block(self, items_client):
        """GET /items liefert zeit-Block in der Antwort (Mini-App-Konsum)."""
        _, _, client = items_client
        # Erst V2-Item per PUT setzen
        client.put("/api/v1/routine/items", json=[
            {"id": "auf", "label": "Aufstehen", "piktogramm": "8152",
             "zeit": {"typ": "anker", "uhrzeit": "07:00", "locked": True}},
        ], content_type="application/json")

        resp = client.get("/api/v1/routine/items")
        assert resp.status_code == 200
        body = json.loads(resp.data)
        # Migration kann Synth-Anker ergänzen — find item 'auf'
        auf_items = [i for i in body["default"] if i["id"] == "auf"]
        assert auf_items, "ID 'auf' muss in GET-Antwort sein"
        assert auf_items[0]["zeit"]["uhrzeit"] == "07:00"
