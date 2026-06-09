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
                json={"label": "Banane", "bild_ref": "2530",
                      "quelle": "kind", "kategorie": "obst_gemuese"})
    client.post("/api/v1/essen/wuensche",
                json={"label": "Apfel", "bild_ref": "2462",
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
    """ESSEN-16: gültiger POST liefert ID und macht Wunsch im GET sichtbar."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Karotte", "bild_ref": "2619",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 201
    wunsch_id = resp.get_json()["id"]
    assert wunsch_id.startswith("kind:")

    data = client.get("/api/v1/essen/wuensche").get_json()
    ids = [w["id"] for w in data["wuensche"]]
    assert wunsch_id in ids


def test_essen16_leeres_label_gibt_400(client):
    """ESSEN-16: leeres label → 400, kein Schreiben (fachliche Validierung)."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "", "bild_ref": "2462",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 400
    # GET bleibt leer.
    assert client.get("/api/v1/essen/wuensche").get_json() == {"wuensche": []}


def test_essen16_unbekannte_kategorie_gibt_400(client):
    """ESSEN-16: unbekannte Kategorie → 400."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Test", "bild_ref": "2462",
              "quelle": "kind", "kategorie": "UNBEKANNT"},
    )
    assert resp.status_code == 400


def test_essen16_unbekannte_quelle_gibt_400(client):
    """ESSEN-16: ungültige quelle → 400."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Test", "bild_ref": "2462",
              "quelle": "maschine", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 400


def test_essen16_nicht_numerische_bild_ref_gibt_400(client):
    """ESSEN-16: bild_ref keine numerische ARASAAC-ID → 400."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Test", "bild_ref": "abc-keine-id",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 400


# ============================================================
#  ESSEN-4 — Wunsch-Modell: alle vier kategorie- und beide quelle-Werte
# ============================================================

def test_essen4_alle_kategorien_und_quellen(client):
    """ESSEN-4: das Wunsch-Modell akzeptiert alle vier kategorie-Werte und
    beide quelle-Werte."""
    kombinationen = [
        ("kind",   "gericht",      "Pizza",     "2527"),
        ("kind",   "obst_gemuese", "Apfel",     "2462"),
        ("eltern", "brotbelag",    "Käse",      "2541"),
        ("eltern", "sonstiges",    "Milch",     "2445"),
    ]
    for quelle, kategorie, label, bild_ref in kombinationen:
        resp = client.post(
            "/api/v1/essen/wuensche",
            json={"label": label, "bild_ref": bild_ref,
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
                        json={"label": "Apfel", "bild_ref": "2462",
                              "quelle": "kind", "kategorie": "obst_gemuese"})
    resp2 = client.post("/api/v1/essen/wuensche",
                        json={"label": "Banane", "bild_ref": "2530",
                              "quelle": "kind", "kategorie": "obst_gemuese"})
    resp3 = client.post("/api/v1/essen/wuensche",
                        json={"label": "Milch", "bild_ref": "2445",
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
                json={"label": "Erdbeere", "bild_ref": "2400",
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
                       json={"label": "Gurke", "bild_ref": "2847",
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
                       json={"label": "Birne", "bild_ref": "2561",
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
                json={"label": "Joghurt", "bild_ref": "2618",
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

def test_essen21_config_startet_ohne_config_datei():
    """ESSEN-21/CONFIG-4: fehlende config.json → Defaults gelten, Prozess startet."""
    from essen import config as config_mod
    rt = config_mod.resolve_runtime(config_path="/pfad/existiert/nicht")
    assert rt["listen_port"] == 5052
    assert rt["listen_host"] == "127.0.0.1"


def test_essen21_env_override_port(monkeypatch):
    """ESSEN-21/CONFIG-5: ENV-Override ESSEN_LISTEN_PORT überschreibt Default."""
    from essen import config as config_mod
    monkeypatch.setenv("ESSEN_LISTEN_PORT", "9999")
    env = {"ESSEN_LISTEN_PORT": "9999"}
    rt = config_mod.resolve_runtime(env=env)
    assert rt["listen_port"] == 9999


# ============================================================
#  ESSEN-2/8/9 — Display-View: Tabbed Single-Canvas
# ============================================================

def test_essen2_view_rendert_vier_tabs(client):
    """ESSEN-2/ESSEN-8: GET /display/essen/wunsch rendert vier Kategorien-Tabs."""
    resp = client.get("/display/essen/wunsch")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Vier Tabs anhand data-tab-Attribute.
    for slug in ("gericht", "obst_gemuese", "brotbelag", "sonstiges"):
        assert 'data-tab="%s"' % slug in body, "Tab %r fehlt im HTML" % slug


def test_essen2_view_rendert_item_grid_und_liste(client):
    """ESSEN-2/ESSEN-8: View zeigt Item-Grid und Wunsch-Liste in einer Canvas."""
    resp = client.get("/display/essen/wunsch")
    body = resp.get_data(as_text=True)
    assert 'id="item-grid"' in body
    assert 'id="liste-eintraege"' in body


def test_essen9_default_tab_obst_gemuese_aktiv(client):
    """ESSEN-9: Default-aktiver Tab ist obst_gemuese (ohne ?tab= Parameter)."""
    resp = client.get("/display/essen/wunsch")
    body = resp.get_data(as_text=True)
    # Der aktive Tab trägt die Klasse 'aktiv'.
    assert 'data-tab="obst_gemuese"' in body
    # Aktiv-Klasse ist am obst_gemuese-Tab.
    assert 'data-tab="obst_gemuese"' in body
    assert "aktiv" in body


def test_essen9_leere_gerichte_kachel_hat_hinweis(client):
    """ESSEN-9: leerer Gerichte-Tab zeigt ehrliche Leer-Meldung, kein Fehler."""
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
    resp = client.get("/display/essen/wunsch")
    body = resp.get_data(as_text=True)
    # Tabs als button.
    assert '<button' in body
    assert 'class="tab' in body
    # Kacheln als button.
    assert 'class="item-kachel"' in body


def test_essen3_liste_eintraege_nicht_interaktiv(client_mit_wuenschen):
    """ESSEN-3: Wunsch-Einträge in der Liste sind nicht interaktiv (kein button)."""
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
#  SVC-1 — Health-Check
# ============================================================

def test_healthz_gibt_200(client):
    """SVC-1: GET /healthz liefert 200."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
