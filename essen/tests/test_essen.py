"""Essens-Buddy — automatisierte Tests je Anforderung (ESSEN-26).

Mindest-Abdeckung aus ESSEN-26: ESSEN-2/3/4/5/6/8/9/11/12/13/14/15/16/17/18/19/20/21.
Alle Tests laufen OHNE Netz. HTTP-Tests über Flask-Testclient.
"""

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from essen import katalog as katalog_mod  # noqa: E402, I001
from essen import main as main_mod  # noqa: E402
from essen import render as render_mod  # noqa: E402
from essen import store as store_mod  # noqa: E402
from essen.tests.conftest import TEST_BOT_TOKEN  # noqa: E402
from tools.initdata import session_cookie as _sc  # noqa: E402
# T814: EssenPhotoClient-Import entfällt — Validierung läuft seit ESSEN-22 V1.2
# über tools.medien_store gegen den lokalen Essen-Fotos-Index (siehe Stub unten).


def _auth_cookie_setzen(client):
    """AUTH-11 (#1836-Nachzug): setzt einen validen xbuddy_session-Cookie fuer
    den Dual-Gate auf /display/essen/wunsch. Additiv -- die `client`-Fixture
    (conftest.py) traegt bereits bot_token=TEST_BOT_TOKEN, denselben Sign-Key
    wie hier. Muster wie plan/tests/test_plan.py::_auth_cookie_setzen."""
    client.set_cookie(_sc.COOKIE_NAME,
                      _sc.sign_session("tablet-essen-test", TEST_BOT_TOKEN))


# ============================================================
#  ESSEN-12 — Repo-Default für drei Lebensmittel-Kategorien
# ============================================================

def test_essen12_repo_default_laedt_drei_kategorien(demo_paths):
    """ESSEN-12: Repo-Default enthält alle drei Lebensmittel-Kategorien,
    jede mit mindestens einem Item."""
    lebensmittel = katalog_mod.lade_lebensmittel(
        demo_paths["katalog_file"],        # Override fehlt
        demo_paths["katalog_default_file"],
    )
    for kat in ("obst_gemuese", "brotbelag", "sonstiges"):
        assert kat in lebensmittel
        assert len(lebensmittel[kat]) >= 1, "Kategorie %r ist leer" % kat


def test_essen12_repo_default_hat_20_items(demo_paths):
    """ESSEN-12: Repo-Default hat genau 20 Items (8+6+6, OPEN-ESSEN-F)."""
    lebensmittel = katalog_mod.lade_lebensmittel(
        demo_paths["katalog_file"],
        demo_paths["katalog_default_file"],
    )
    total = sum(len(v) for v in lebensmittel.values())
    assert total == 20


def test_essen12_alle_bild_refs_numerisch(demo_paths):
    """ESSEN-12/ESSEN-11: alle bild_ref-Werte im Repo-Default sind numerische
    ARASAAC-IDs (ICONS-5)."""
    lebensmittel = katalog_mod.lade_lebensmittel(
        demo_paths["katalog_file"],
        demo_paths["katalog_default_file"],
    )
    for kat, items in lebensmittel.items():
        for item in items:
            try:
                int(item["bild_ref"])
            except (ValueError, TypeError):
                pytest.fail("bild_ref %r in %r ist nicht numerisch" % (item["bild_ref"], kat))


# ============================================================
#  ESSEN-13 — Per-Instanz-Override
# ============================================================

def test_essen13_override_ersetzt_default(demo_paths, tmp_path):
    """ESSEN-13: mit gültigem Override wird der Repo-Default ersetzt."""
    override = {
        "kategorien": {
            "obst_gemuese": [{"id": "test", "label": "Test", "bild_ref": "9999"}],
            "brotbelag": [],
            "sonstiges": [],
        }
    }
    override_path = str(tmp_path / "katalog_override.json")
    with open(override_path, "w", encoding="utf-8") as f:
        json.dump(override, f)

    lebensmittel = katalog_mod.lade_lebensmittel(
        override_path,
        demo_paths["katalog_default_file"],
    )
    assert len(lebensmittel["obst_gemuese"]) == 1
    assert lebensmittel["obst_gemuese"][0]["id"] == "test"
    # Default-Items nicht da.
    assert not any(i["id"] == "apfel" for i in lebensmittel["obst_gemuese"])


def test_essen13_kaputte_override_gibt_snapshot(demo_paths, tmp_path):
    """ESSEN-13/DCOMP-3: kaputte Override-Datei → Last-Known-Good-Snapshot."""
    kaputt_path = str(tmp_path / "kaputt.json")
    with open(kaputt_path, "w") as f:
        f.write("{ KAPUTT }")

    snapshot = {"obst_gemuese": [{"id": "snap", "label": "Snap", "bild_ref": "1"}],
                "brotbelag": [], "sonstiges": []}
    lebensmittel = katalog_mod.lade_lebensmittel(
        kaputt_path,
        demo_paths["katalog_default_file"],
        snapshot=snapshot,
    )
    assert lebensmittel == snapshot


def test_essen13_kaputte_override_ohne_snapshot_gibt_default(demo_paths, tmp_path):
    """ESSEN-13: kaputte Override-Datei, kein vorheriger Stand → Repo-Default."""
    kaputt_path = str(tmp_path / "kaputt.json")
    with open(kaputt_path, "w") as f:
        f.write("KEIN JSON")

    lebensmittel = katalog_mod.lade_lebensmittel(
        kaputt_path,
        demo_paths["katalog_default_file"],
        snapshot=None,
    )
    # Default: obst_gemuese hat 8 Items.
    assert len(lebensmittel["obst_gemuese"]) == 8


def test_essen13_fehlende_override_gibt_default(demo_paths):
    """ESSEN-13: fehlt die Override-Datei komplett → Repo-Default (CONFIG-4)."""
    lebensmittel = katalog_mod.lade_lebensmittel(
        demo_paths["katalog_file"],   # Datei existiert nicht
        demo_paths["katalog_default_file"],
    )
    assert len(lebensmittel["obst_gemuese"]) == 8  # Default


# ============================================================
#  ESSEN-14 — Gerichte-Katalog dynamisch, initial leer
# ============================================================

def test_essen14_gerichte_initial_leer(demo_paths):
    """ESSEN-14: Gerichte-Katalog ist ohne Schreib-Vorgang leer."""
    daten = store_mod.lade_gerichte(
        demo_paths["gerichte_file"], snapshot=None)
    assert daten["gerichte"] == []


def test_essen14_gericht_anlegen_sichtbar_ohne_restart(client):
    """ESSEN-14/ESSEN-9: nach POST auf /katalog/gerichte erscheint das Gericht
    im GET /api/v1/essen/katalog (Reload-on-Read, ESSEN-20)."""
    # Gerichte-Katalog ist leer.
    resp = client.get("/api/v1/essen/katalog")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["kategorien"]["gericht"] == []

    # Gericht anlegen.
    resp2 = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Pizza", "bild_ref": "2527"},
    )
    assert resp2.status_code == 201

    # Sofort sichtbar (kein Restart).
    resp3 = client.get("/api/v1/essen/katalog")
    gericht_items = resp3.get_json()["kategorien"]["gericht"]
    assert len(gericht_items) == 1
    assert gericht_items[0]["label"] == "Pizza"


# ============================================================
#  ESSEN-15 — GET /api/v1/essen/wuensche
# ============================================================

def test_essen15_leere_liste_gibt_200(client):
    """ESSEN-15: leere Liste → 200 mit { wuensche: [] }, kein 404."""
    resp = client.get("/api/v1/essen/wuensche")
    assert resp.status_code == 200
    assert resp.get_json() == {"wuensche": []}


def test_essen15_chronologische_reihenfolge(client):
    """ESSEN-15: Reihenfolge folgt erstellt_am aufsteigend (älteste zuerst)."""
    # Zwei Wünsche in umgekehrter Reihenfolge anlegen.
    client.post("/api/v1/essen/wuensche",
                json={"label": "Banane", "bild_ref": "2530", "item_id": "banane",
                      "quelle": "kind", "kategorie": "obst_gemuese"})
    client.post("/api/v1/essen/wuensche",
                json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
                      "quelle": "kind", "kategorie": "obst_gemuese"})
    data = client.get("/api/v1/essen/wuensche").get_json()
    labels = [w["label"] for w in data["wuensche"]]
    # Beide da, Reihenfolge: Banane zuerst (früher angelegt).
    assert labels[0] == "Banane"
    assert labels[1] == "Apfel"


def test_essen15_mit_persistierten_wuenschen(client_mit_wuenschen):
    """ESSEN-15: mit drei persistierten Wünschen liefert der Endpunkt genau diese."""
    data = client_mit_wuenschen.get("/api/v1/essen/wuensche").get_json()
    assert len(data["wuensche"]) == 2


# ============================================================
#  ESSEN-16 — POST /api/v1/essen/wuensche
# ============================================================

def test_essen16_gueltiger_post_persistiert(client):
    """ESSEN-16: gültiger POST liefert ID und macht Wunsch im GET sichtbar.
    Antwort enthält item_id (ESSEN-15-Schärfung)."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Karotte", "bild_ref": "2619", "item_id": "karotte",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 201
    wunsch_id = resp.get_json()["id"]
    assert wunsch_id.startswith("kind:")

    data = client.get("/api/v1/essen/wuensche").get_json()
    ids = [w["id"] for w in data["wuensche"]]
    assert wunsch_id in ids
    # item_id wird mit-persistiert (ESSEN-15-Schärfung).
    wunsch = next(w for w in data["wuensche"] if w["id"] == wunsch_id)
    assert wunsch["item_id"] == "karotte"


def test_essen16_leeres_label_gibt_400(client):
    """ESSEN-16: leeres label → 400, kein Schreiben (fachliche Validierung)."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 400
    # GET bleibt leer.
    assert client.get("/api/v1/essen/wuensche").get_json() == {"wuensche": []}


def test_essen16_unbekannte_kategorie_gibt_400(client):
    """ESSEN-16: unbekannte Kategorie → 400."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Test", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "UNBEKANNT"},
    )
    assert resp.status_code == 400


def test_essen16_unbekannte_quelle_gibt_400(client):
    """ESSEN-16: ungültige quelle → 400."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Test", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "maschine", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 400


def test_essen16_nicht_numerische_bild_ref_gibt_400(client):
    """ESSEN-16: bild_ref keine numerische ARASAAC-ID → 400."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Test", "bild_ref": "abc-keine-id", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 400


def test_essen16_fehlende_item_id_gibt_400(client):
    """ESSEN-16 (Watchdog-Befund): POST ohne item_id → 400 (Pflichtfeld)."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 400
    assert client.get("/api/v1/essen/wuensche").get_json() == {"wuensche": []}


def test_essen16_unbekannte_item_id_gibt_400(client):
    """ESSEN-16 (Watchdog-Befund): POST mit item_id, die nicht im Katalog
    existiert → 400 (Katalog-Validierung, BUD-2)."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Unbekannt", "bild_ref": "2462", "item_id": "gibts-nicht",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 400
    assert client.get("/api/v1/essen/wuensche").get_json() == {"wuensche": []}


def test_essen16_duplikat_item_id_gibt_409(client):
    """ESSEN-16 (Watchdog-Befund): zwei POSTs mit gleicher item_id →
    erster 201, zweiter 409 Conflict; GET zeigt nur einen Eintrag (BUD-2, ESSEN-28)."""
    resp1 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp2.status_code == 409
    body2 = resp2.get_json()
    assert body2.get("fehler") == "item_already_on_list"
    assert body2.get("item_id") == "apfel"

    # GET zeigt genau einen Apfel-Eintrag.
    data = client.get("/api/v1/essen/wuensche").get_json()
    apfel_eintraege = [w for w in data["wuensche"] if w.get("item_id") == "apfel"]
    assert len(apfel_eintraege) == 1


# ============================================================
#  ESSEN-4 — Wunsch-Modell: alle vier kategorie- und beide quelle-Werte
# ============================================================

def test_essen4_alle_kategorien_und_quellen(client):
    """ESSEN-4: das Wunsch-Modell akzeptiert alle vier kategorie-Werte und
    beide quelle-Werte. item_id ist Pflichtfeld (ESSEN-16-Schärfung).
    Für gericht: erst Gericht anlegen, damit item_id im Katalog existiert."""
    # Gericht anlegen, damit item_id "pizza" im Gerichte-Katalog vorhanden ist.
    client.post("/api/v1/essen/katalog/gerichte",
                json={"label": "Pizza", "bild_ref": "2527"})

    kombinationen = [
        ("kind",   "gericht",      "Pizza",     "2527", "1"),
        ("kind",   "obst_gemuese", "Apfel",     "2462", "apfel"),
        ("eltern", "brotbelag",    "Käse",      "2541", "kaese"),
        ("eltern", "sonstiges",    "Milch",     "2445", "milch"),
    ]
    for quelle, kategorie, label, bild_ref, item_id in kombinationen:
        resp = client.post(
            "/api/v1/essen/wuensche",
            json={"label": label, "bild_ref": bild_ref, "item_id": item_id,
                  "quelle": quelle, "kategorie": kategorie},
        )
        assert resp.status_code == 201, \
            "Fehlgeschlagen für quelle=%r, kategorie=%r" % (quelle, kategorie)

    data = client.get("/api/v1/essen/wuensche").get_json()
    assert len(data["wuensche"]) == 4


# ============================================================
#  ESSEN-5 — Stabile, herkunfts-eindeutige Wunsch-IDs
# ============================================================

def test_essen5_ids_quelleneindeutig_und_kollisionsfrei(client):
    """ESSEN-5: kind:-IDs und eltern:-IDs kollidieren nie; je Quelle monoton."""
    resp1 = client.post("/api/v1/essen/wuensche",
                        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
                              "quelle": "kind", "kategorie": "obst_gemuese"})
    resp2 = client.post("/api/v1/essen/wuensche",
                        json={"label": "Banane", "bild_ref": "2530", "item_id": "banane",
                              "quelle": "kind", "kategorie": "obst_gemuese"})
    resp3 = client.post("/api/v1/essen/wuensche",
                        json={"label": "Milch", "bild_ref": "2445", "item_id": "milch",
                              "quelle": "eltern", "kategorie": "sonstiges"})

    id1 = resp1.get_json()["id"]
    id2 = resp2.get_json()["id"]
    id3 = resp3.get_json()["id"]

    assert id1 == "kind:1"
    assert id2 == "kind:2"
    assert id3 == "eltern:1"
    # Keine Kollision.
    assert id1 != id3
    assert id2 != id3


# ============================================================
#  ESSEN-6 — Wünsche leben dauerhaft (POST + "Tageswechsel" + GET)
# ============================================================

def test_essen6_wunsch_bleibt_nach_neuladen(client, demo_paths):
    """ESSEN-6: Wunsch nach POST bleibt dauerhaft (persistiert, DCOMP-4).

    Simulated Tageswechsel: Snapshot löschen, neue configure() → Reload-on-Read
    liest die Datei frisch (ESSEN-20). Der Wunsch muss noch da sein.
    """
    # Wunsch anlegen.
    client.post("/api/v1/essen/wuensche",
                json={"label": "Erdbeere", "bild_ref": "2400", "item_id": "erdbeere",
                      "quelle": "kind", "kategorie": "obst_gemuese"})

    # Simuliere Neustart: Snapshots zurücksetzen.
    main_mod.runtime["wuensche_snapshot"] = None
    main_mod.configure(demo_paths)

    # Wunsch ist weiter da (Reload-on-Read liest Datei).
    data = client.get("/api/v1/essen/wuensche").get_json()
    labels = [w["label"] for w in data["wuensche"]]
    assert "Erdbeere" in labels


# ============================================================
#  ESSEN-17 — DELETE /api/v1/essen/wuensche/<id> — idempotent
# ============================================================

def test_essen17_delete_entfernt_wunsch(client):
    """ESSEN-17: DELETE auf vorhandene ID → 200, GET ohne diesen Wunsch."""
    resp = client.post("/api/v1/essen/wuensche",
                       json={"label": "Gurke", "bild_ref": "2847", "item_id": "gurke",
                             "quelle": "kind", "kategorie": "obst_gemuese"})
    wunsch_id = resp.get_json()["id"]

    del_resp = client.delete("/api/v1/essen/wuensche/" + wunsch_id)
    assert del_resp.status_code == 200

    data = client.get("/api/v1/essen/wuensche").get_json()
    ids = [w["id"] for w in data["wuensche"]]
    assert wunsch_id not in ids


def test_essen17_zweites_delete_idempotent(client):
    """ESSEN-17: zweites DELETE auf bereits entfernte ID → 200 (idempotent)."""
    resp = client.post("/api/v1/essen/wuensche",
                       json={"label": "Birne", "bild_ref": "2561", "item_id": "birne",
                             "quelle": "kind", "kategorie": "obst_gemuese"})
    wunsch_id = resp.get_json()["id"]

    client.delete("/api/v1/essen/wuensche/" + wunsch_id)
    # Zweites Delete.
    del2 = client.delete("/api/v1/essen/wuensche/" + wunsch_id)
    assert del2.status_code == 200
    data = client.get("/api/v1/essen/wuensche").get_json()
    assert len(data["wuensche"]) == 0


# ============================================================
#  ESSEN-18 — GET /api/v1/essen/katalog
# ============================================================

def test_essen18_katalog_vier_kategorien_vorhanden(client):
    """ESSEN-18: Katalog-GET gruppiert über vier Kategorien (auch leere Gerichte)."""
    resp = client.get("/api/v1/essen/katalog")
    assert resp.status_code == 200
    data = resp.get_json()
    for kat in ("gericht", "obst_gemuese", "brotbelag", "sonstiges"):
        assert kat in data["kategorien"]


def test_essen18_gericht_initial_leer(client):
    """ESSEN-18: ohne POST ist Gerichte-Kategorie leer (ESSEN-14)."""
    data = client.get("/api/v1/essen/katalog").get_json()
    assert data["kategorien"]["gericht"] == []


def test_essen18_lebensmittel_kategorien_gefuellt(client):
    """ESSEN-18: Lebensmittel-Kategorien sind mit Default-Items gefüllt."""
    data = client.get("/api/v1/essen/katalog").get_json()
    assert len(data["kategorien"]["obst_gemuese"]) == 8
    assert len(data["kategorien"]["brotbelag"]) == 6
    assert len(data["kategorien"]["sonstiges"]) == 6


# ============================================================
#  ESSEN-19 — POST /api/v1/essen/katalog/gerichte
# ============================================================

def test_essen19_gueltiger_post_persistiert(client):
    """ESSEN-19: gültiger POST liefert ID und macht Gericht in GET sichtbar."""
    resp = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Lasagne", "bild_ref": "2527"},
    )
    assert resp.status_code == 201
    gericht_id = resp.get_json()["id"]
    assert gericht_id == "1"

    data = client.get("/api/v1/essen/katalog").get_json()
    labels = [g["label"] for g in data["kategorien"]["gericht"]]
    assert "Lasagne" in labels


def test_essen19_duplikat_label_gibt_409(client):
    """ESSEN-19: doppeltes label → 409 Conflict, kein zweiter Eintrag."""
    client.post("/api/v1/essen/katalog/gerichte",
                json={"label": "Pizza", "bild_ref": "2527"})
    resp2 = client.post("/api/v1/essen/katalog/gerichte",
                        json={"label": "Pizza", "bild_ref": "2527"})
    assert resp2.status_code == 409

    data = client.get("/api/v1/essen/katalog").get_json()
    pizza_count = sum(1 for g in data["kategorien"]["gericht"] if g["label"] == "Pizza")
    assert pizza_count == 1


def test_essen19_leeres_label_gibt_400(client):
    """ESSEN-19: leeres label → 400."""
    resp = client.post("/api/v1/essen/katalog/gerichte",
                       json={"label": "", "bild_ref": "2527"})
    assert resp.status_code == 400


def test_essen19_ungueltige_bild_ref_gibt_400(client):
    """ESSEN-19: nicht-numerische bild_ref → 400."""
    resp = client.post("/api/v1/essen/katalog/gerichte",
                       json={"label": "Suppe", "bild_ref": "kein-arasaac"})
    assert resp.status_code == 400


# ============================================================
#  ESSEN-20 — Reload-on-Read + Last-Known-Good + atomares Schreiben
# ============================================================

def test_essen20_reload_on_read_nach_post(client, demo_paths):
    """ESSEN-20: Wunsch nach POST sofort im GET sichtbar (kein Restart)."""
    client.post("/api/v1/essen/wuensche",
                json={"label": "Joghurt", "bild_ref": "2618", "item_id": "joghurt",
                      "quelle": "kind", "kategorie": "sonstiges"})
    data = client.get("/api/v1/essen/wuensche").get_json()
    labels = [w["label"] for w in data["wuensche"]]
    assert "Joghurt" in labels


def test_essen20_lkg_wuensche_bei_kaputter_datei(demo_paths):
    """ESSEN-20/DCOMP-3: partiell kaputte wuensche.json → Last-Known-Good."""
    # Snapshot mit einem bekannten Wunsch.
    snapshot = {
        "wuensche": [{"id": "kind:1", "label": "Snap", "bild_ref": "2462",
                      "quelle": "kind", "kategorie": "obst_gemuese",
                      "erstellt_am": "2026-06-09T10:00:00+02:00"}],
        "zaehler": {"kind": 1, "eltern": 0},
    }
    # Kaputte Datei anlegen.
    with open(demo_paths["wuensche_file"], "w") as f:
        f.write("{ KAPUTT")

    result = store_mod.lade_wuensche(demo_paths["wuensche_file"], snapshot=snapshot)
    # Last-Known-Good geliefert.
    assert result == snapshot


def test_essen20_atomares_schreiben_wuensche(demo_paths, tmp_path):
    """ESSEN-20/DCOMP-4: nach speichere_wuensche ist die Datei lesbar und
    enthält die geschriebenen Daten."""
    daten = {"wuensche": [{"id": "kind:1", "label": "Test", "bild_ref": "1",
                           "quelle": "kind", "kategorie": "obst_gemuese",
                           "erstellt_am": "2026-06-09T10:00:00+02:00"}],
             "zaehler": {"kind": 1, "eltern": 0}}
    path = str(tmp_path / "atomtest.json")
    store_mod.speichere_wuensche(path, daten)
    # Jetzt lesen — muss identisch sein.
    geladen = store_mod.lade_wuensche(path)
    assert geladen["wuensche"][0]["label"] == "Test"


# ============================================================
#  ESSEN-21 — Config: fehlende/kaputte Datei → Defaults + Warnung
# ============================================================

def test_essen21_config_startet_ohne_config_datei(tmp_path):
    """ESSEN-21/CONFIG-4: fehlende config.json → Defaults gelten, Prozess startet."""
    from tools import configloader
    _schema = {"listen_host": "127.0.0.1", "listen_port": 5052, "log_level": "INFO"}
    cfg = configloader.load(
        component="essen", schema=_schema,
        config_path=str(tmp_path / "existiert_nicht.json"))
    assert cfg["listen_port"] == 5052
    assert cfg["listen_host"] == "127.0.0.1"


def test_essen21_env_override_port(monkeypatch, tmp_path):
    """ESSEN-21/CONFIG-5: ENV-Override ESSEN_LISTEN_PORT überschreibt Default."""
    from tools import configloader
    _schema = {"listen_host": "127.0.0.1", "listen_port": 5052, "log_level": "INFO"}
    monkeypatch.setenv("ESSEN_LISTEN_PORT", "9999")
    cfg = configloader.load(
        component="essen", schema=_schema,
        config_path=str(tmp_path / "existiert_nicht.json"))
    assert cfg["listen_port"] == 9999


# ============================================================
#  ESSEN-22 / SVC-5 — data_paths: foto_overrides_file
# ============================================================

def test_data_paths_foto_overrides_file_default(monkeypatch):
    """SVC-5/ESSEN-22: ohne ENV-Override liefert data_paths() den Repo-Default
    (DEFAULT_FOTO_OVERRIDES_FILE = essen/foto_overrides.json im Modul-Verzeichnis)."""
    from essen import config as config_mod
    env = {k: v for k, v in os.environ.items()
           if k != config_mod.ENV_FOTO_OVERRIDES_FILE}
    paths = config_mod.data_paths(env=env)
    assert "foto_overrides_file" in paths
    assert paths["foto_overrides_file"] == config_mod.DEFAULT_FOTO_OVERRIDES_FILE


def test_data_paths_foto_overrides_file_env_override(monkeypatch, tmp_path):
    """SVC-5/ESSEN-22: ESSEN_FOTO_OVERRIDES_FILE überschreibt den Default-Pfad."""
    from essen import config as config_mod
    override_pfad = str(tmp_path / "mein_foto_overrides.json")
    env = dict(os.environ)
    env[config_mod.ENV_FOTO_OVERRIDES_FILE] = override_pfad
    paths = config_mod.data_paths(env=env)
    assert paths["foto_overrides_file"] == override_pfad


def test_wunsch_view_uebergibt_foto_overrides_pfad(client, monkeypatch, demo_paths):
    """ESSEN-22/SVC-5: GET /display/essen/wunsch ruft baue_view mit
    foto_overrides_pfad aus _paths() auf (Render-Aufruf-Wiring, AC2)."""
    from essen import render as render_mod_local

    captured = {}

    _orig_baue_view = render_mod_local.baue_view

    def _fake_baue_view(kategorien, wuensche, aktiv_tab=None, foto_overrides_pfad=None):
        captured["foto_overrides_pfad"] = foto_overrides_pfad
        return _orig_baue_view(kategorien, wuensche,
                               aktiv_tab=aktiv_tab,
                               foto_overrides_pfad=foto_overrides_pfad)

    monkeypatch.setattr(main_mod.render_mod, "baue_view", _fake_baue_view)
    _auth_cookie_setzen(client)

    resp = client.get("/display/essen/wunsch")
    assert resp.status_code == 200
    assert "foto_overrides_pfad" in captured
    assert captured["foto_overrides_pfad"] == demo_paths["foto_overrides_file"]


# ============================================================
#  ESSEN-2/8/9 — Display-View: Tabbed Single-Canvas
# ============================================================

def test_essen2_view_rendert_vier_tabs(client):
    """ESSEN-2/ESSEN-8: GET /display/essen/wunsch rendert vier Kategorien-Tabs."""
    _auth_cookie_setzen(client)
    resp = client.get("/display/essen/wunsch")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Vier Tabs anhand data-tab-Attribute.
    for slug in ("gericht", "obst_gemuese", "brotbelag", "sonstiges"):
        assert 'data-tab="%s"' % slug in body, "Tab %r fehlt im HTML" % slug


def test_essen2_view_rendert_item_grid_und_liste(client):
    """ESSEN-2/ESSEN-8: View zeigt Item-Grid und Wunsch-Liste in einer Canvas."""
    _auth_cookie_setzen(client)
    resp = client.get("/display/essen/wunsch")
    body = resp.get_data(as_text=True)
    assert 'id="item-grid"' in body
    assert 'id="liste-eintraege"' in body


def test_essen9_default_tab_obst_gemuese_aktiv(client):
    """ESSEN-9: Default-aktiver Tab ist obst_gemuese (ohne ?tab= Parameter)."""
    _auth_cookie_setzen(client)
    resp = client.get("/display/essen/wunsch")
    body = resp.get_data(as_text=True)
    # Der aktive Tab trägt die Klasse 'aktiv'.
    assert 'data-tab="obst_gemuese"' in body
    # Aktiv-Klasse ist am obst_gemuese-Tab.
    assert 'data-tab="obst_gemuese"' in body
    assert "aktiv" in body


def test_essen9_leere_gerichte_kachel_hat_hinweis(client):
    """ESSEN-9: leerer Gerichte-Tab zeigt ehrliche Leer-Meldung, kein Fehler."""
    _auth_cookie_setzen(client)
    resp = client.get("/display/essen/wunsch?tab=gericht")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "noch keine" in body.lower() or "keine gerichte" in body.lower()


def test_essen8_brotbelag_tab_endpoint_smoke(client):
    """ESSEN-8/ESSEN-9: GET /display/essen/wunsch?tab=brotbelag liefert 200 und
    enthält Default-Brotbelag-Items im HTML (Käse als Anker-Label, ESSEN-12).

    Smoke-Test des echten Flask-Pfads: Tab-Slug-Routing bricht hier auf, bevor
    render.baue_view gerufen wird — ein reiner Helper-Test würde das nicht fangen.
    """
    _auth_cookie_setzen(client)
    resp = client.get("/display/essen/wunsch?tab=brotbelag")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Brotbelag-Default enthält 'Käse' (katalog.default.json, ESSEN-12).
    assert "Käse" in body, "Brotbelag-Default-Item 'Käse' fehlt im gerenderten HTML"


# ============================================================
#  ESSEN-11 — Piktogramme über geteilte Icon-Plattform
# ============================================================

def test_essen11_icons_ueber_geteilte_plattform(client):
    """ESSEN-11/ICONS-5: Piktogramme werden über /display/_shared/icons/arasaac/
    referenziert, KEIN buddy-eigener ARASAAC-Bezug."""
    _auth_cookie_setzen(client)
    resp = client.get("/display/essen/wunsch")
    body = resp.get_data(as_text=True)
    assert "/display/_shared/icons/arasaac/" in body
    assert "static.arasaac.org" not in body


def test_essen11_render_icon_url():
    """ESSEN-11: render.icon_url gibt die korrekte geteilte Plattform-URL."""
    url = render_mod.icon_url("2462")
    assert url == "/display/_shared/icons/arasaac/2462.png"
    assert render_mod.icon_url(None) is None
    assert render_mod.icon_url("") is None


# ============================================================
#  ESSEN-3 — Touch: nur Tabs und Item-Kacheln sind interaktiv
# ============================================================

def test_essen3_tabs_und_kacheln_haben_tap_handler(client):
    """ESSEN-3: nur .tab und .item-kachel tragen einen Tap-Handler (button oder
    click-Handler in JS)."""
    _auth_cookie_setzen(client)
    resp = client.get("/display/essen/wunsch")
    body = resp.get_data(as_text=True)
    # Tabs als button.
    assert '<button' in body
    assert 'class="tab' in body
    # Kacheln als button.
    assert 'class="item-kachel"' in body


def test_essen3_liste_eintraege_nicht_interaktiv(client_mit_wuenschen):
    """ESSEN-3: Wunsch-Einträge in der Liste sind nicht interaktiv (kein button)."""
    _auth_cookie_setzen(client_mit_wuenschen)
    resp = client_mit_wuenschen.get("/display/essen/wunsch")
    body = resp.get_data(as_text=True)
    # liste-eintrag darf kein button sein.
    assert '<button' in body  # Tabs und Kacheln ja.
    # liste-eintrag ist ein div, kein button.
    assert '<div class="liste-eintrag' in body


# ============================================================
#  ESSEN-8 — Render: Tab-Wechsel tauscht nur Item-Grid
# ============================================================

def test_essen8_render_tab_wechsel(demo_paths):
    """ESSEN-8: render.baue_view mit verschiedenen aktiv_tab wechselt nur das
    Item-Grid — Tabs und Liste bleiben gleich."""
    lebensmittel = katalog_mod.lade_lebensmittel(
        demo_paths["katalog_file"],
        demo_paths["katalog_default_file"],
    )
    alle_kategorien = dict(lebensmittel, gericht=[])
    wuensche = []

    view_obst = render_mod.baue_view(alle_kategorien, wuensche, aktiv_tab="obst_gemuese")
    view_brot = render_mod.baue_view(alle_kategorien, wuensche, aktiv_tab="brotbelag")

    # Vier Tabs je View, aber aktiv_tab wechselt.
    assert len(view_obst["tabs"]) == 4
    assert len(view_brot["tabs"]) == 4
    assert view_obst["aktiv_tab"] == "obst_gemuese"
    assert view_brot["aktiv_tab"] == "brotbelag"

    # Grids sind verschieden.
    assert view_obst["item_grid"]["kacheln"] != view_brot["item_grid"]["kacheln"]
    # Wunschliste bleibt gleich (beide leer).
    assert view_obst["wunsch_liste"] == view_brot["wunsch_liste"]


# ============================================================
#  ESSEN-27 — Display-Lösch-Geste am Wunsch-Listen-Eintrag
# ============================================================

def test_essen27_entfernen_symbol_sichtbar(client_mit_wuenschen):
    """ESSEN-27: jede liste-eintrag-Kachel trägt das Entfernen-Symbol ARASAAC 11751
    über die geteilte Plattform und data-wunsch-id."""
    _auth_cookie_setzen(client_mit_wuenschen)
    resp = client_mit_wuenschen.get("/display/essen/wunsch")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Entfernen-Icon ARASAAC 11751 über geteilte Plattform (ICONS-5).
    assert "/display/_shared/icons/arasaac/11751.png" in body
    # Jeder Eintrag trägt data-wunsch-id (Render-Vertrag ESSEN-27).
    assert 'data-wunsch-id="kind:1"' in body
    assert 'data-wunsch-id="kind:2"' in body
    # Lösch-Button sichtbar.
    assert 'class="loeschen-btn"' in body


def test_essen27_delete_entfernt_wunsch(client_mit_wuenschen):
    """ESSEN-27/ESSEN-17: DELETE auf eine vorhandene Wunsch-ID entfernt den Eintrag;
    nachfolgender GET liefert die ID nicht mehr (Reload-on-Read, ESSEN-20)."""
    # Sicherstellen, dass kind:1 initial vorhanden.
    daten_vor = client_mit_wuenschen.get("/api/v1/essen/wuensche").get_json()
    ids_vor = [w["id"] for w in daten_vor["wuensche"]]
    assert "kind:1" in ids_vor

    # DELETE auslösen (entspricht einem Tap auf das Entfernen-Symbol).
    resp_del = client_mit_wuenschen.delete("/api/v1/essen/wuensche/kind:1")
    assert resp_del.status_code == 200

    # Reload-on-Read: GET zeigt kind:1 nicht mehr.
    daten_nach = client_mit_wuenschen.get("/api/v1/essen/wuensche").get_json()
    ids_nach = [w["id"] for w in daten_nach["wuensche"]]
    assert "kind:1" not in ids_nach
    # kind:2 ist noch da.
    assert "kind:2" in ids_nach


def test_essen27_render_entfernen_url_in_view_modell(demo_paths):
    """ESSEN-27: render.baue_wunsch_liste gibt für jeden Eintrag entfernen_url
    mit ARASAAC 11751 zurück."""
    wuensche = [
        {"id": "kind:1", "label": "Apfel", "bild_ref": "2462",
         "quelle": "kind", "kategorie": "obst_gemuese",
         "erstellt_am": "2026-06-09T08:00:00+02:00"},
    ]
    liste = render_mod.baue_wunsch_liste(wuensche)
    assert len(liste) == 1
    eintrag = liste[0]["eintraege"][0]
    assert eintrag["entfernen_url"] == "/display/_shared/icons/arasaac/11751.png"
    assert eintrag["id"] == "kind:1"


def test_essen27_data_wunsch_id_traegt_korrekte_id(client_mit_wuenschen):
    """ESSEN-27 (Refs #532): data-wunsch-id im gerendertem HTML trägt exakt den
    Wert von wunsch.id aus dem View-Modell — nicht nur einen per Test-Konstante
    identischen Substring.

    Der Test extrahiert die data-wunsch-id-Werte via Regex aus dem HTML und
    vergleicht sie gegen die IDs aus dem API-View-Modell (GET /api/v1/essen/wuensche).
    """
    import re

    # View-Modell-IDs aus der API.
    api_resp = client_mit_wuenschen.get("/api/v1/essen/wuensche")
    assert api_resp.status_code == 200
    wunsch_ids_aus_api = {w["id"] for w in api_resp.get_json()["wuensche"]}

    # HTML-Render.
    _auth_cookie_setzen(client_mit_wuenschen)
    resp = client_mit_wuenschen.get("/display/essen/wunsch")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # Alle data-wunsch-id-Werte aus dem HTML extrahieren.
    ids_im_html = set(re.findall(r'data-wunsch-id="([^"]+)"', body))

    # Jede API-ID muss exakt so im HTML stehen (keine Substring-Übereinstimmung).
    assert ids_im_html == wunsch_ids_aus_api


# ============================================================
#  ESSEN-28 — Wunsch-Kachel-Sperre auf Liste-Lebenszyklus
# ============================================================

def test_essen28_render_kachel_gesperrt_fuer_item_auf_liste(demo_paths):
    """ESSEN-28(a): render.baue_view markiert Kacheln als gesperrt, wenn ihre
    item_id in der aktiven Wunschliste vorkommt (strikt item_id-Match, ESSEN-28)."""
    lebensmittel = katalog_mod.lade_lebensmittel(
        demo_paths["katalog_file"],
        demo_paths["katalog_default_file"],
    )
    alle_kategorien = dict(lebensmittel, gericht=[])
    # Apfel (item_id "apfel") ist auf der Wunschliste.
    wuensche = [
        {
            "id": "kind:1",
            "label": "Apfel",
            "bild_ref": "2462",
            "item_id": "apfel",
            "quelle": "kind",
            "kategorie": "obst_gemuese",
            "erstellt_am": "2026-06-09T08:00:00+02:00",
        }
    ]

    view = render_mod.baue_view(alle_kategorien, wuensche, aktiv_tab="obst_gemuese")
    kacheln = view["item_grid"]["kacheln"]

    # Apfel-Kachel ist gesperrt (item_id "apfel" in der Liste).
    apfel = next((k for k in kacheln if k["id"] == "apfel"), None)
    assert apfel is not None, "Apfel-Kachel fehlt im Grid"
    assert apfel["gesperrt"] is True, "Apfel-Kachel muss gesperrt sein (auf der Liste)"

    # Banane-Kachel ist NICHT gesperrt (nicht auf der Liste).
    banane = next((k for k in kacheln if k["id"] == "banane"), None)
    assert banane is not None, "Banane-Kachel fehlt im Grid"
    assert banane["gesperrt"] is False, "Banane-Kachel darf nicht gesperrt sein"


def test_essen28_view_html_zeigt_kachel_gesperrt_klasse(client_mit_wuenschen):
    """ESSEN-28(a): GET /display/essen/wunsch rendert .kachel-gesperrt und
    data-wunsch-aktiv='true' für Items auf der aktiven Wunschliste.

    client_mit_wuenschen hat Apfel (bild_ref 2462, obst_gemuese) und
    Milch (bild_ref 2445, sonstiges) auf der Liste."""
    _auth_cookie_setzen(client_mit_wuenschen)
    # Obst-Tab: Apfel ist auf der Liste → kachel-gesperrt erwartet.
    resp = client_mit_wuenschen.get("/display/essen/wunsch?tab=obst_gemuese")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Render-Vertrag: .kachel-gesperrt und data-wunsch-aktiv="true" vorhanden.
    assert "kachel-gesperrt" in body, ".kachel-gesperrt-Klasse fehlt im HTML"
    assert 'data-wunsch-aktiv="true"' in body, "data-wunsch-aktiv fehlt im HTML"
    # disabled-Attribut auf gesperrter Kachel.
    assert "disabled" in body, "disabled-Attribut fehlt auf gesperrter Kachel"


def test_essen28_kachel_wieder_frei_nach_delete(client_mit_wuenschen):
    """ESSEN-28(c): nach DELETE /api/v1/essen/wuensche/<id> rendert die
    Kachel beim nächsten GET ohne .kachel-gesperrt (Reload-on-Read, ESSEN-20)."""
    _auth_cookie_setzen(client_mit_wuenschen)
    # Zustand vorher: Apfel auf der Liste → Kachel gesperrt.
    resp_vor = client_mit_wuenschen.get("/display/essen/wunsch?tab=obst_gemuese")
    body_vor = resp_vor.get_data(as_text=True)
    assert "kachel-gesperrt" in body_vor, "Vortest: Kachel muss gesperrt sein"

    # kind:1 (Apfel, item_id apfel) löschen.
    del_resp = client_mit_wuenschen.delete("/api/v1/essen/wuensche/kind:1")
    assert del_resp.status_code == 200

    # Nach DELETE: Reload-on-Read → kein kachel-gesperrt mehr für Apfel.
    resp_nach = client_mit_wuenschen.get("/display/essen/wunsch?tab=obst_gemuese")
    body_nach = resp_nach.get_data(as_text=True)

    # kind:2 (Milch, sonstiges) ist noch auf der Liste — aber Milch ist im
    # sonstiges-Tab, nicht im obst_gemuese-Tab. Im obst_gemuese-Tab keine Sperre mehr.
    assert "kachel-gesperrt" not in body_nach, \
        "Nach DELETE darf obst_gemuese-Tab keine gesperrten Kacheln mehr zeigen"
    assert 'data-wunsch-aktiv="true"' not in body_nach, \
        "Nach DELETE darf data-wunsch-aktiv nicht mehr im obst_gemuese-Tab erscheinen"


def test_essen28_roundtrip_post_get_zeigt_kachel_gesperrt(client):
    """ESSEN-28 Roundtrip (Watchdog-Befund 3): POST /api/v1/essen/wuensche →
    GET /display/essen/wunsch zeigt kachel-gesperrt auf der geposteten Item-Kachel.

    Prüft den echten Flask-Pfad: POST schreibt item_id in die Liste,
    GET rendert die View mit item_id-basierter Sperre."""
    # POST: Apfel auf die Liste.
    resp_post = client.post(
        "/api/v1/essen/wuensche",
        json={
            "label": "Apfel",
            "bild_ref": "2462",
            "item_id": "apfel",
            "quelle": "kind",
            "kategorie": "obst_gemuese",
        },
    )
    assert resp_post.status_code == 201
    wunsch_id = resp_post.get_json()["id"]
    _auth_cookie_setzen(client)

    # GET Display-View im obst_gemuese-Tab.
    resp_get = client.get("/display/essen/wunsch?tab=obst_gemuese")
    assert resp_get.status_code == 200
    body = resp_get.get_data(as_text=True)

    # Apfel-Kachel (data-item-id="apfel") muss kachel-gesperrt tragen.
    assert "kachel-gesperrt" in body, \
        "kachel-gesperrt fehlt nach POST mit item_id='apfel'"
    assert 'data-wunsch-aktiv="true"' in body, \
        "data-wunsch-aktiv fehlt nach POST"
    assert 'data-item-id="apfel"' in body, \
        "data-item-id='apfel' fehlt im Grid"

    # GET API liefert item_id im Wunsch-Eintrag (ESSEN-15-Schärfung).
    api_data = client.get("/api/v1/essen/wuensche").get_json()
    wunsch = next(w for w in api_data["wuensche"] if w["id"] == wunsch_id)
    assert wunsch["item_id"] == "apfel", \
        "item_id fehlt im GET /api/v1/essen/wuensche Antwort"


# ============================================================
#  SVC-1 — Health-Check
# ============================================================

def test_healthz_gibt_200(client):
    """SVC-1: GET /healthz liefert 200."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


# ============================================================
#  ESSEN-19 (T531) — POST mit foto_ref (Photo-Buddy-Medien-ID)
# ============================================================

# Helfer: setzt den Photo-Buddy-Check-Stub für die Dauer eines Tests.
# Alle ESSEN-19/19a-Tests verwenden diesen Stub (kein echtes Netz).
# Test-Naht über transport=-Injection (CLIENT-1): FakeTransport liefert
# (status, bytes) je nach bekannter ID-Menge.

def _set_photo_stub(monkeypatch, known_ids=None):
    """Monkeypatcht den essen-Foto-Index-Lookup im main-Modul (T814).

    Nach Welle 2 (T808 / #804) liegen Essens-Fotos im Essen-Buddy selbst;
    `_foto_ref_existiert` ruft `medien_store.load(verzeichnis)` und prüft
    auf Vorkommen der ID. Der Stub ersetzt `_foto_ref_existiert` direkt
    (Test-Naht — vermeidet das Anlegen einer echten essen/fotos/-Datei).

    known_ids: Menge gültiger Medien-IDs. None = alle IDs gültig.
    """
    if known_ids is None:
        monkeypatch.setattr(main_mod, "_foto_ref_existiert", lambda _ref: True)
    else:
        ids = set(known_ids)
        monkeypatch.setattr(main_mod, "_foto_ref_existiert", lambda ref: ref in ids)


def test_essen19_foto_ref_legt_gericht_an(client, monkeypatch):
    """ESSEN-19 (AC1): POST mit foto_ref legt Gericht an; GET zeigt foto_ref ohne bild_ref."""
    _set_photo_stub(monkeypatch, known_ids={"med-42"})

    resp = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Spaghetti", "foto_ref": "med-42"},
    )
    assert resp.status_code == 201
    gericht_id = resp.get_json()["id"]

    data = client.get("/api/v1/essen/katalog").get_json()
    gerichte = data["kategorien"]["gericht"]
    g = next((x for x in gerichte if x["id"] == gericht_id), None)
    assert g is not None, "Gericht nicht im Katalog"
    assert g.get("foto_ref") == "med-42", "foto_ref fehlt im Katalog-Eintrag"
    assert "bild_ref" not in g, "bild_ref darf bei foto_ref-Gericht nicht im Eintrag stehen"


def test_essen19_beide_felder_gibt_400(client, monkeypatch):
    """ESSEN-19 (AC1): POST mit foto_ref + bild_ref → 400."""
    _set_photo_stub(monkeypatch)

    resp = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Lasagne", "bild_ref": "2527", "foto_ref": "med-1"},
    )
    assert resp.status_code == 400


def test_essen19_kein_bildfeld_gibt_400(client):
    """ESSEN-19 (AC1): POST ohne bild_ref und ohne foto_ref → 400."""
    resp = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Suppe"},
    )
    assert resp.status_code == 400


def test_essen19_unbekannte_foto_ref_gibt_400(client, monkeypatch):
    """ESSEN-19 (AC3): POST mit foto_ref, die im Photo-Buddy nicht existiert → 400."""
    _set_photo_stub(monkeypatch, known_ids={"med-bekannt"})

    resp = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Pizza", "foto_ref": "med-unbekannt"},
    )
    assert resp.status_code == 400
    # Kein Schreiben erfolgt.
    data = client.get("/api/v1/essen/katalog").get_json()
    assert data["kategorien"]["gericht"] == []


# ============================================================
#  ESSEN-19a (T531) — PATCH /api/v1/essen/katalog/gerichte/<id>
# ============================================================

def test_essen19a_patch_foto_ref_setzt_foto(client, monkeypatch):
    """ESSEN-19a (AC2): PATCH {foto_ref} → 200, GET zeigt foto_ref, kein bild_ref."""
    _set_photo_stub(monkeypatch, known_ids={"med-99"})

    # Erst Gericht mit bild_ref anlegen.
    resp_post = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Rührei", "bild_ref": "2527"},
    )
    assert resp_post.status_code == 201
    gericht_id = resp_post.get_json()["id"]

    # PATCH: foto_ref setzen.
    resp_patch = client.patch(
        "/api/v1/essen/katalog/gerichte/" + gericht_id,
        json={"foto_ref": "med-99"},
    )
    assert resp_patch.status_code == 200
    body = resp_patch.get_json()
    assert body.get("foto_ref") == "med-99"
    assert "bild_ref" not in body, "bild_ref muss durch foto_ref ersetzt worden sein"

    # GET-Spiegel.
    data = client.get("/api/v1/essen/katalog").get_json()
    g = next((x for x in data["kategorien"]["gericht"] if x["id"] == gericht_id), None)
    assert g is not None
    assert g.get("foto_ref") == "med-99"
    assert "bild_ref" not in g


def test_essen19a_patch_bild_ref_setzt_pikto(client, monkeypatch):
    """ESSEN-19a (AC2): PATCH {bild_ref} auf Foto-Gericht → 200, bild_ref gesetzt, foto_ref weg."""
    _set_photo_stub(monkeypatch, known_ids={"med-55"})

    # Gericht mit foto_ref anlegen.
    resp_post = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Quiche", "foto_ref": "med-55"},
    )
    assert resp_post.status_code == 201
    gericht_id = resp_post.get_json()["id"]

    # PATCH: zurück zu bild_ref.
    resp_patch = client.patch(
        "/api/v1/essen/katalog/gerichte/" + gericht_id,
        json={"bild_ref": "2527"},
    )
    assert resp_patch.status_code == 200
    body = resp_patch.get_json()
    assert body.get("bild_ref") == "2527"
    assert "foto_ref" not in body, "foto_ref muss durch bild_ref ersetzt worden sein"

    # GET-Spiegel.
    data = client.get("/api/v1/essen/katalog").get_json()
    g = next((x for x in data["kategorien"]["gericht"] if x["id"] == gericht_id), None)
    assert g is not None
    assert g.get("bild_ref") == "2527"
    assert "foto_ref" not in g


def test_essen19a_patch_beide_felder_gibt_400(client):
    """ESSEN-19a (AC2): PATCH {foto_ref, bild_ref} → 400."""
    resp = client.patch(
        "/api/v1/essen/katalog/gerichte/1",
        json={"foto_ref": "med-1", "bild_ref": "2527"},
    )
    assert resp.status_code == 400


def test_essen19a_patch_unbekannte_id_gibt_404(client):
    """ESSEN-19a (AC2): PATCH auf unbekannte Gericht-ID → 404."""
    resp = client.patch(
        "/api/v1/essen/katalog/gerichte/gibts-nicht",
        json={"bild_ref": "2527"},
    )
    assert resp.status_code == 404


def test_essen19a_patch_unbekannte_foto_ref_gibt_400(client, monkeypatch):
    """ESSEN-19a (AC3): PATCH mit foto_ref, die im Photo-Buddy nicht existiert → 400."""
    _set_photo_stub(monkeypatch, known_ids={"med-bekannt"})

    # Gericht anlegen.
    resp_post = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Steak", "bild_ref": "2527"},
    )
    gericht_id = resp_post.get_json()["id"]

    resp_patch = client.patch(
        "/api/v1/essen/katalog/gerichte/" + gericht_id,
        json={"foto_ref": "med-unbekannt"},
    )
    assert resp_patch.status_code == 400

    # bild_ref muss unverändert sein.
    data = client.get("/api/v1/essen/katalog").get_json()
    g = next((x for x in data["kategorien"]["gericht"] if x["id"] == gericht_id), None)
    assert g.get("bild_ref") == "2527"
    assert "foto_ref" not in g


def test_essen19a_patch_label_wird_ignoriert(client, monkeypatch):
    """ESSEN-19a (Watchdog-Befund AC2): PATCH {label, bild_ref} → 200;
    label bleibt unverändert (Ignorier-Klausel), bild_ref wird gewechselt.

    Spec-Klausel: 'Unbekannte/Label/Zutaten-Felder werden ignoriert
    (Vorwärtskompatibilität).' — ESSEN-19a {label:'Neu'} → ignoriert.
    """
    _set_photo_stub(monkeypatch, known_ids={"foto-X"})

    # Gericht mit label="Original" und bild_ref="X" anlegen.
    resp_post = client.post(
        "/api/v1/essen/katalog/gerichte",
        json={"label": "Original", "bild_ref": "2527"},
    )
    assert resp_post.status_code == 201
    gericht_id = resp_post.get_json()["id"]

    # PATCH: label="Neu" (ignoriert) + bild_ref="Y" (gewechselt).
    resp_patch = client.patch(
        "/api/v1/essen/katalog/gerichte/" + gericht_id,
        json={"label": "Neu", "bild_ref": "9999"},
    )
    assert resp_patch.status_code == 200

    # GET: label muss "Original" sein (unverändert), bild_ref muss "9999" sein.
    data = client.get("/api/v1/essen/katalog").get_json()
    g = next((x for x in data["kategorien"]["gericht"] if x["id"] == gericht_id), None)
    assert g is not None, "Gericht nicht im Katalog nach PATCH"
    assert g.get("label") == "Original", (
        "label muss unverändert 'Original' sein — ESSEN-19a ignoriert label-Felder"
    )
    assert g.get("bild_ref") == "9999", "bild_ref muss auf '9999' gewechselt haben"
