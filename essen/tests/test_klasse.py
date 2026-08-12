"""Essens-Buddy — Tests für klasse-Trennung, Listen-Grenze, PATCH (V1 #653).

Mindest-Abdeckung gemäss T653-F-Contract:
- AC1 — neue Felder im Wunsch-Modell + Migration Alt-Einträge ohne klasse.
- AC2 — POST-Routing nach klasse (ESSEN-7/ESSEN-16) + Quellen-Zähler global.
- AC3 — GET-Filter ?klasse= und ?abgehakt= (ESSEN-15).
- AC4 — Listen-Grenze je File (ESSEN-29).
- AC5 — PATCH-Endpoint (ESSEN-32): sparse update für abgehakt + aus_gericht.
- AC6 — Duplikat-Regel orthogonal zu klasse (ESSEN-16).

Plus Migrations-Tests gemäss Stop-Rule `migration_breakt_alt`:
- Alt-Format wuensche.json mit zaehler-Schlüssel im File wird gelesen.
- Alt-Eintrag ohne klasse wird als klasse='wunsch', abgehakt=false gelesen.
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from essen import main as main_mod  # noqa: E402
from essen import store as store_mod  # noqa: E402
from essen.tests.conftest import TEST_BOT_TOKEN  # noqa: E402
from tools.initdata import session_cookie as _sc  # noqa: E402


def _auth_cookie_setzen(client):
    """AUTH-11 (#1836-Nachzug): setzt einen validen xbuddy_session-Cookie fuer
    den Dual-Gate auf /display/essen/wunsch. Additiv -- die `client`-Fixture
    (conftest.py) traegt bereits bot_token=TEST_BOT_TOKEN, denselben Sign-Key
    wie hier. Muster wie plan/tests/test_plan.py::_auth_cookie_setzen."""
    client.set_cookie(_sc.COOKIE_NAME,
                      _sc.sign_session("tablet-essen-test", TEST_BOT_TOKEN))


# ============================================================
#  Migration (ESSEN-7, ESSEN-4 Migrations-Regel) — Stop-Rule
# ============================================================

def test_alt_wuensche_format_wird_gelesen(demo_paths):
    """Stop-Rule `migration_breakt_alt`: Alt-`wuensche.json` mit `zaehler`-
    Schlüssel im selben File wird korrekt gelesen, keine Daten verloren."""
    alt_format = {
        "wuensche": [
            {
                "id": "kind:1", "label": "Apfel", "bild_ref": "2462",
                "item_id": "apfel", "quelle": "kind",
                "kategorie": "obst_gemuese",
                "erstellt_am": "2026-06-09T10:00:00+02:00",
            },
        ],
        "zaehler": {"kind": 1, "eltern": 0},
    }
    with open(demo_paths["wuensche_file"], "w", encoding="utf-8") as f:
        json.dump(alt_format, f)

    daten = store_mod.lade_wuensche(demo_paths["wuensche_file"])
    # Wuensche-Inhalt erhalten.
    assert len(daten["wuensche"]) == 1
    assert daten["wuensche"][0]["label"] == "Apfel"
    # Migration: Zähler wird durchgereicht (zum Heben nach zaehler.json).
    assert daten.get("zaehler") == {"kind": 1, "eltern": 0}


def test_alt_eintrag_ohne_klasse_wird_wunsch(demo_paths):
    """AC1 / ESSEN-4 Migrations-Regel: Alt-Eintrag ohne `klasse`-Feld →
    Reader füllt `klasse='wunsch'`, `abgehakt=false`."""
    alt_eintrag = {
        "wuensche": [
            {
                "id": "kind:1", "label": "Apfel", "bild_ref": "2462",
                "item_id": "apfel", "quelle": "kind",
                "kategorie": "obst_gemuese",
                "erstellt_am": "2026-06-09T10:00:00+02:00",
            },
        ],
    }
    with open(demo_paths["wuensche_file"], "w", encoding="utf-8") as f:
        json.dump(alt_eintrag, f)

    daten = store_mod.lade_wuensche(demo_paths["wuensche_file"])
    w = daten["wuensche"][0]
    assert w["klasse"] == "wunsch"
    assert w["abgehakt"] is False


def test_migrations_hub_zaehler_aus_wuensche_nach_zaehler_file(client_mit_wuenschen,
                                                                demo_paths):
    """ESSEN-7 Migration: nach dem ersten GET nach Alt-Format-Read wird
    `zaehler` aus wuensche.json nach zaehler.json gehoben — beim nächsten
    POST nutzt der Buddy den Zähler aus zaehler.json."""
    # Initial: wuensche.json hat Alt-Format mit zaehler.
    # client_mit_wuenschen tut den Reset bereits. Ein GET triggert die
    # Migration über _lade_wuensche_frisch.
    resp = client_mit_wuenschen.get("/api/v1/essen/wuensche?klasse=wunsch")
    assert resp.status_code == 200

    # zaehler.json existiert nun (Migration ausgeführt).
    assert os.path.exists(demo_paths["zaehler_file"]), \
        "zaehler.json muss nach Migration existieren"
    with open(demo_paths["zaehler_file"], encoding="utf-8") as f:
        stand = json.load(f)
    assert stand == {"kind": 2, "eltern": 0}


# ============================================================
#  AC2 — POST-Routing nach klasse, IDs kollidieren nicht
# ============================================================

def test_ac2_post_wunsch_landet_in_wuensche_file(client, demo_paths):
    """AC2: POST mit klasse='wunsch' schreibt nach wuensche.json."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert resp.status_code == 201
    assert os.path.exists(demo_paths["wuensche_file"])
    with open(demo_paths["wuensche_file"], encoding="utf-8") as f:
        daten = json.load(f)
    assert len(daten["wuensche"]) == 1
    assert daten["wuensche"][0]["klasse"] == "wunsch"
    # einkaufsliste.json darf NICHT angelegt worden sein.
    assert not os.path.exists(demo_paths["einkaufsliste_file"])


def test_ac2_post_einkauf_landet_in_einkaufsliste_file(client, demo_paths):
    """AC2: POST mit klasse='einkauf' schreibt nach einkaufsliste.json."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Milch", "bild_ref": "2445", "item_id": "milch",
              "quelle": "eltern", "kategorie": "sonstiges",
              "klasse": "einkauf"},
    )
    assert resp.status_code == 201
    assert os.path.exists(demo_paths["einkaufsliste_file"])
    with open(demo_paths["einkaufsliste_file"], encoding="utf-8") as f:
        daten = json.load(f)
    assert len(daten["wuensche"]) == 1
    assert daten["wuensche"][0]["klasse"] == "einkauf"


def test_ac2_zaehler_klasse_uebergreifend(client, demo_paths):
    """AC2 / ESSEN-5: globaler Quellen-Zähler in zaehler.json ist
    klasse-übergreifend monoton steigend. IDs kollidieren nicht zwischen
    den zwei Klasse-Files."""
    # eltern:1 → klasse=wunsch (apfel ist im Lebensmittel-Katalog).
    r1 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "eltern", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    # eltern:2 → klasse=einkauf
    r2 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Milch", "bild_ref": "2445", "item_id": "milch",
              "quelle": "eltern", "kategorie": "sonstiges",
              "klasse": "einkauf"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.get_json()["id"] == "eltern:1"
    assert r2.get_json()["id"] == "eltern:2"
    # Kein Kollisions-Konflikt zwischen Files.
    assert r1.get_json()["id"] != r2.get_json()["id"]


def test_ac2_post_default_klasse_ist_wunsch(client):
    """AC2/ESSEN-4: POST ohne `klasse` setzt Default `klasse='wunsch'`
    (Rückwärtskompat)."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese"},
    )
    assert resp.status_code == 201
    data = client.get("/api/v1/essen/wuensche").get_json()
    assert data["wuensche"][0]["klasse"] == "wunsch"


def test_ac2_post_einkauf_mit_aus_gericht_persistiert(client):
    """AC2/ESSEN-4/ESSEN-30: POST mit klasse='einkauf' + aus_gericht
    persistiert das Feld; GET liefert es zurück."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Mozzarella", "bild_ref": "2445",
              "item_id": "milch",  # nutzen wir als Stellvertreter-item_id
              "quelle": "eltern", "kategorie": "sonstiges",
              "klasse": "einkauf", "aus_gericht": "Lasagne"},
    )
    assert resp.status_code == 201
    data = client.get("/api/v1/essen/wuensche?klasse=einkauf").get_json()
    assert data["wuensche"][0]["aus_gericht"] == "Lasagne"


def test_ac2_aus_gericht_bei_klasse_wunsch_400(client):
    """ESSEN-16: aus_gericht ist NUR bei klasse='einkauf' zulässig."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch", "aus_gericht": "Lasagne"},
    )
    assert resp.status_code == 400


def test_ac2_ungueltige_klasse_gibt_400(client):
    """ESSEN-16: unbekannter klasse-Wert → 400."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "UNBEKANNT"},
    )
    assert resp.status_code == 400


# ============================================================
#  AC3 — GET-Filter ?klasse= und ?abgehakt= (ESSEN-15)
# ============================================================

def test_ac3_get_ohne_filter_merged_beide_files(client):
    """AC3: GET ohne Filter merge-t beide Files sortiert nach erstellt_am."""
    # Wunsch + Einkauf anlegen.
    client.post("/api/v1/essen/wuensche",
                json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
                      "quelle": "kind", "kategorie": "obst_gemuese",
                      "klasse": "wunsch"})
    client.post("/api/v1/essen/wuensche",
                json={"label": "Milch", "bild_ref": "2445", "item_id": "milch",
                      "quelle": "eltern", "kategorie": "sonstiges",
                      "klasse": "einkauf"})
    data = client.get("/api/v1/essen/wuensche").get_json()
    assert len(data["wuensche"]) == 2
    klassen = {w["klasse"] for w in data["wuensche"]}
    assert klassen == {"wunsch", "einkauf"}


def test_ac3_get_klasse_wunsch_nur_aus_wuensche_file(client):
    """AC3: GET ?klasse=wunsch liest nur wuensche.json."""
    client.post("/api/v1/essen/wuensche",
                json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
                      "quelle": "kind", "kategorie": "obst_gemuese",
                      "klasse": "wunsch"})
    client.post("/api/v1/essen/wuensche",
                json={"label": "Milch", "bild_ref": "2445", "item_id": "milch",
                      "quelle": "eltern", "kategorie": "sonstiges",
                      "klasse": "einkauf"})
    data = client.get("/api/v1/essen/wuensche?klasse=wunsch").get_json()
    assert len(data["wuensche"]) == 1
    assert data["wuensche"][0]["klasse"] == "wunsch"
    assert data["wuensche"][0]["label"] == "Apfel"


def test_ac3_get_klasse_einkauf_nur_aus_einkaufsliste_file(client):
    """AC3: GET ?klasse=einkauf liest nur einkaufsliste.json."""
    client.post("/api/v1/essen/wuensche",
                json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
                      "quelle": "kind", "kategorie": "obst_gemuese",
                      "klasse": "wunsch"})
    client.post("/api/v1/essen/wuensche",
                json={"label": "Milch", "bild_ref": "2445", "item_id": "milch",
                      "quelle": "eltern", "kategorie": "sonstiges",
                      "klasse": "einkauf"})
    data = client.get("/api/v1/essen/wuensche?klasse=einkauf").get_json()
    assert len(data["wuensche"]) == 1
    assert data["wuensche"][0]["klasse"] == "einkauf"
    assert data["wuensche"][0]["label"] == "Milch"


def test_ac3_get_abgehakt_filter_und_verknuepft(client):
    """AC3/ESSEN-15: GET ?klasse=wunsch&abgehakt=false liefert nur offene Wünsche."""
    # Zwei Wuensche anlegen.
    r1 = client.post("/api/v1/essen/wuensche",
                     json={"label": "Apfel", "bild_ref": "2462",
                           "item_id": "apfel",
                           "quelle": "kind", "kategorie": "obst_gemuese",
                           "klasse": "wunsch"})
    r2 = client.post("/api/v1/essen/wuensche",
                     json={"label": "Banane", "bild_ref": "2530",
                           "item_id": "banane",
                           "quelle": "kind", "kategorie": "obst_gemuese",
                           "klasse": "wunsch"})
    # r1 abhaken.
    id1 = r1.get_json()["id"]
    client.patch("/api/v1/essen/wuensche/" + id1,
                 json={"abgehakt": True})

    # abgehakt=false: nur Banane.
    data_offen = client.get(
        "/api/v1/essen/wuensche?klasse=wunsch&abgehakt=false").get_json()
    assert len(data_offen["wuensche"]) == 1
    assert data_offen["wuensche"][0]["id"] == r2.get_json()["id"]

    # abgehakt=true: nur Apfel.
    data_abgehakt = client.get(
        "/api/v1/essen/wuensche?klasse=wunsch&abgehakt=true").get_json()
    assert len(data_abgehakt["wuensche"]) == 1
    assert data_abgehakt["wuensche"][0]["id"] == id1


def test_ac3_get_ungueltige_klasse_filter_gibt_400(client):
    """ESSEN-15: unbekannter klasse-Filter-Wert → 400."""
    resp = client.get("/api/v1/essen/wuensche?klasse=KAPUTT")
    assert resp.status_code == 400


def test_ac3_get_ungueltiger_abgehakt_filter_gibt_400(client):
    """ESSEN-15: unbekannter abgehakt-Filter-Wert → 400."""
    resp = client.get("/api/v1/essen/wuensche?abgehakt=KAPUTT")
    assert resp.status_code == 400


# ============================================================
#  AC4 — Listen-Grenze je File (ESSEN-29)
# ============================================================

def test_ac4_listen_grenze_99_plus_1_gibt_201(client, demo_paths):
    """AC4/ESSEN-29: bei 99 offenen Einträgen ist der nächste POST noch erlaubt."""
    # Override: Default ist 100 — wir wollen aber gezielt 99 offene Einträge
    # mit Test-Geschwindigkeit. Wir setzen die Grenze auf 100 (Default) und
    # legen 99 Einträge direkt im File an (Bypass POST-Performance).
    p = demo_paths
    bestand = {
        "wuensche": [
            {
                "id": "kind:%d" % i, "label": "Item%d" % i, "bild_ref": "2462",
                "item_id": "apfel-%d" % i, "quelle": "kind",
                "kategorie": "obst_gemuese", "klasse": "wunsch",
                "abgehakt": False,
                "erstellt_am": "2026-06-09T08:00:%02d+02:00" % (i % 60),
            }
            for i in range(1, 100)
        ],
    }
    with open(p["wuensche_file"], "w", encoding="utf-8") as f:
        json.dump(bestand, f)
    # Zähler auf 99 setzen.
    with open(p["zaehler_file"], "w", encoding="utf-8") as f:
        json.dump({"kind": 99, "eltern": 0}, f)
    # Snapshot zurücksetzen, damit reload greift.
    main_mod.runtime["wuensche_snapshot"] = None
    main_mod.runtime["zaehler_snapshot"] = None

    # Nächster POST (99 + 1 = 100, Grenze 100) ist erlaubt.
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert resp.status_code == 201, "99 + 1 = 100 muss noch passen"


def test_ac4_listen_grenze_99_plus_2_gibt_413(client, demo_paths):
    """AC4/ESSEN-29: 99 offene + 2 weitere POSTs → zweiter ist 413 mit Body."""
    p = demo_paths
    bestand = {
        "wuensche": [
            {
                "id": "kind:%d" % i, "label": "Item%d" % i, "bild_ref": "2462",
                "item_id": "apfel-%d" % i, "quelle": "kind",
                "kategorie": "obst_gemuese", "klasse": "wunsch",
                "abgehakt": False,
                "erstellt_am": "2026-06-09T08:00:%02d+02:00" % (i % 60),
            }
            for i in range(1, 100)
        ],
    }
    with open(p["wuensche_file"], "w", encoding="utf-8") as f:
        json.dump(bestand, f)
    with open(p["zaehler_file"], "w", encoding="utf-8") as f:
        json.dump({"kind": 99, "eltern": 0}, f)
    main_mod.runtime["wuensche_snapshot"] = None
    main_mod.runtime["zaehler_snapshot"] = None

    # Erster POST → 201 (99 + 1 = 100, Grenze 100).
    r1 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r1.status_code == 201

    # Zweiter POST → 413, jetzt sind wir bei 100 offenen + 1 weiterer = 101.
    r2 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Banane", "bild_ref": "2530", "item_id": "banane",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r2.status_code == 413
    body = r2.get_json()
    assert body["error"] == "listen_grenze"
    assert body["offen_jetzt"] == 100
    assert body["grenze"] == 100


def test_ac4_listen_grenze_override_uebergangs_schluessel(client, demo_paths):
    """AC4/ESSEN-29: Übergangs-Schlüssel `listen_grenze` greift für beide Listen."""
    # Konfiguration ändern: listen_grenze = 1.
    main_mod.configure(demo_paths, listen_grenze=1)

    # Erster POST (0 + 1 = 1, Grenze 1) → 201.
    r1 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r1.status_code == 201

    # Zweiter POST → 413.
    r2 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Banane", "bild_ref": "2530", "item_id": "banane",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r2.status_code == 413
    body = r2.get_json()
    assert body["error"] == "listen_grenze"
    assert body["grenze"] == 1


def test_ac4_listen_grenze_wunsch_und_einkauf_getrennt(client, demo_paths):
    """AC4/ESSEN-29: spezifische Overrides — Wunsch-Grenze 1, Einkauf-Grenze 1.
    Ein Wunsch + ein Einkauf liegen gleichzeitig drin, beide sind exakt voll."""
    main_mod.configure(demo_paths, listen_grenze_wunsch=1, listen_grenze_einkauf=1)

    # 1 Wunsch — OK.
    r1 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r1.status_code == 201

    # 1 Einkauf — OK (separate Grenze).
    r2 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Milch", "bild_ref": "2445", "item_id": "milch",
              "quelle": "eltern", "kategorie": "sonstiges",
              "klasse": "einkauf"},
    )
    assert r2.status_code == 201

    # Zweiter Wunsch → 413.
    r3 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Banane", "bild_ref": "2530", "item_id": "banane",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r3.status_code == 413

    # Zweiter Einkauf → 413.
    r4 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Karotte", "bild_ref": "2619", "item_id": "karotte",
              "quelle": "eltern", "kategorie": "obst_gemuese",
              "klasse": "einkauf"},
    )
    assert r4.status_code == 413


def test_ac4_abgehakte_eintraege_zaehlen_nicht_zur_grenze(client, demo_paths):
    """ESSEN-29: ein abgehakter Eintrag zählt nicht zur Grenze."""
    main_mod.configure(demo_paths, listen_grenze=1)

    # 1 Wunsch.
    r1 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r1.status_code == 201
    id1 = r1.get_json()["id"]

    # Abhaken.
    client.patch("/api/v1/essen/wuensche/" + id1, json={"abgehakt": True})

    # Nächster Wunsch — der erste zählt nicht mehr → 201.
    r2 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Banane", "bild_ref": "2530", "item_id": "banane",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r2.status_code == 201


# ============================================================
#  AC5 — PATCH-Endpoint (ESSEN-32)
# ============================================================

def test_ac5_patch_abgehakt_true_setzt_von_und_am(client):
    """AC5/ESSEN-32: PATCH {abgehakt: true} → 200, abgehakt_von + abgehakt_am gesetzt."""
    r = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    wid = r.get_json()["id"]

    p = client.patch("/api/v1/essen/wuensche/" + wid, json={"abgehakt": True})
    assert p.status_code == 200
    body = p.get_json()
    assert body["abgehakt"] is True
    assert body.get("abgehakt_von")  # gesetzt
    assert body.get("abgehakt_am")   # gesetzt

    # GET zeigt es ebenfalls.
    data = client.get("/api/v1/essen/wuensche").get_json()
    w = next(x for x in data["wuensche"] if x["id"] == wid)
    assert w["abgehakt"] is True
    assert w["abgehakt_von"]
    assert w["abgehakt_am"]


def test_ac5_patch_abgehakt_false_leert_von_und_am(client):
    """AC5/ESSEN-32: PATCH {abgehakt: false} leert abgehakt_von + abgehakt_am."""
    r = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    wid = r.get_json()["id"]

    client.patch("/api/v1/essen/wuensche/" + wid, json={"abgehakt": True})
    p2 = client.patch("/api/v1/essen/wuensche/" + wid, json={"abgehakt": False})
    assert p2.status_code == 200
    body = p2.get_json()
    assert body["abgehakt"] is False
    assert "abgehakt_von" not in body
    assert "abgehakt_am"  not in body


def test_ac5_patch_aus_gericht_bei_wunsch_gibt_400(client):
    """AC5/ESSEN-32: PATCH {aus_gericht: …} auf Eintrag mit klasse=wunsch → 400."""
    r = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    wid = r.get_json()["id"]

    p = client.patch(
        "/api/v1/essen/wuensche/" + wid,
        json={"aus_gericht": "Lasagne"},
    )
    assert p.status_code == 400


def test_ac5_patch_aus_gericht_bei_einkauf_persistiert(client):
    """AC5/ESSEN-32: PATCH {aus_gericht: "X"} auf klasse=einkauf-Eintrag persistiert."""
    r = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Mozzarella", "bild_ref": "2445", "item_id": "milch",
              "quelle": "eltern", "kategorie": "sonstiges",
              "klasse": "einkauf"},
    )
    wid = r.get_json()["id"]

    p = client.patch(
        "/api/v1/essen/wuensche/" + wid,
        json={"aus_gericht": "Lasagne"},
    )
    assert p.status_code == 200
    assert p.get_json()["aus_gericht"] == "Lasagne"

    data = client.get("/api/v1/essen/wuensche?klasse=einkauf").get_json()
    w = next(x for x in data["wuensche"] if x["id"] == wid)
    assert w["aus_gericht"] == "Lasagne"


def test_ac5_patch_unbekannte_id_gibt_404(client):
    """AC5/ESSEN-32: PATCH auf unbekannte ID → 404."""
    p = client.patch("/api/v1/essen/wuensche/kind:9999", json={"abgehakt": True})
    assert p.status_code == 404


def test_ac5_patch_klassen_feld_ist_ignoriert(client):
    """AC5/ESSEN-32: Klassen-Felder (label/kategorie/…) sind NICHT änderbar.
    Unbekannte/nicht-änderbare Felder werden ignoriert (Vorwärtskompat)."""
    r = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    wid = r.get_json()["id"]

    p = client.patch(
        "/api/v1/essen/wuensche/" + wid,
        json={"label": "GEHACKT", "klasse": "einkauf",
              "kategorie": "brotbelag", "future_field": "x"},
    )
    # Spec ESSEN-32: Unbekannte Felder ignorieren — kein 400.
    assert p.status_code == 200
    body = p.get_json()
    assert body["label"]      == "Apfel"
    assert body["klasse"]     == "wunsch"
    assert body["kategorie"]  == "obst_gemuese"


# ============================================================
#  AC6 — Duplikat-Regel orthogonal zu klasse (ESSEN-16)
# ============================================================

def test_ac6_gleicher_item_id_in_beiden_klassen_erlaubt(client):
    """AC6/ESSEN-16: gleicher item_id darf einmal je klasse offen sein.

    Kind wünscht Mango (klasse=wunsch), Eltern schreibt Mango als Einkauf
    (klasse=einkauf) — beides ist gültig, kein 409.
    """
    # 'apfel' kommt im Lebensmittel-Katalog vor (item_id-Validierung muss
    # weiter klappen).
    r1 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    r2 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "eltern", "kategorie": "obst_gemuese",
              "klasse": "einkauf"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201, \
        "Gleicher item_id in unterschiedlichen klassen muss erlaubt sein"

    data = client.get("/api/v1/essen/wuensche").get_json()
    assert len(data["wuensche"]) == 2


def test_ac6_gleicher_item_id_und_klasse_gibt_409(client):
    """AC6/ESSEN-16: gleicher item_id und gleiche klasse offen → 409."""
    r1 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    r2 = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Apfel", "bild_ref": "2462", "item_id": "apfel",
              "quelle": "kind", "kategorie": "obst_gemuese",
              "klasse": "wunsch"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 409


# ============================================================
#  ESSEN-7 / ESSEN-8 — Display-View rendert nur klasse=wunsch
# ============================================================

def test_display_view_zeigt_keine_einkauf_items(client):
    """ESSEN-8: Display-View filtert auf klasse=wunsch (Doppel-Robustheit).
    Eltern-Einkauf-Items sind im Kinder-Display NIE sichtbar."""
    # Einkauf-Item anlegen.
    client.post(
        "/api/v1/essen/wuensche",
        json={"label": "MoZzReLLa-Einkauf", "bild_ref": "2445",
              "item_id": "milch",
              "quelle": "eltern", "kategorie": "sonstiges",
              "klasse": "einkauf"},
    )
    _auth_cookie_setzen(client)
    resp = client.get("/display/essen/wunsch")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Das Einkauf-Label darf NICHT im Display-View auftauchen.
    assert "MoZzReLLa-Einkauf" not in body


# ============================================================
#  ESSEN-17 DELETE über beide Files
# ============================================================

def test_delete_findet_eintrag_in_einkaufsliste(client, demo_paths):
    """ESSEN-17: DELETE findet einen Eintrag auch wenn er in einkaufsliste.json liegt."""
    r = client.post(
        "/api/v1/essen/wuensche",
        json={"label": "Milch", "bild_ref": "2445", "item_id": "milch",
              "quelle": "eltern", "kategorie": "sonstiges",
              "klasse": "einkauf"},
    )
    wid = r.get_json()["id"]

    d = client.delete("/api/v1/essen/wuensche/" + wid)
    assert d.status_code == 200

    # Datei prüfen — Einkaufsliste ist leer.
    with open(demo_paths["einkaufsliste_file"], encoding="utf-8") as f:
        daten = json.load(f)
    assert daten["wuensche"] == []


# ============================================================
#  ESSEN-16-Ausnahme: frei:-Präfix ohne Katalog-Match (AC1_code)
# ============================================================

def test_essen_16_frei_praefix_zulaessig(client):
    """AC1_code / ESSEN-16-Ausnahme: item_id mit Präfix 'frei:' ist OHNE
    Katalog-Match zulässig (EIN-4/ESSEN-31-Konsistenz). Erwartet 201."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={
            "label": "Spritzkuchen",
            "bild_ref": "2462",          # numerische ARASAAC-ID (valide)
            "item_id": "frei:spritzkuchen",
            "quelle": "eltern",
            "kategorie": "sonstiges",
            "klasse": "einkauf",
        },
    )
    assert resp.status_code == 201, (
        "frei:-Präfix-item_id muss ohne Katalog-Match akzeptiert werden "
        "(ESSEN-16-Ausnahme, EIN-4/ESSEN-31)"
    )
    data = resp.get_json()
    assert "id" in data


def test_essen_16_unbekannt_item_id_400(client):
    """AC1_code / ESSEN-16: item_id ohne 'frei:'-Präfix, die nicht im Katalog
    existiert, wird mit 400 abgelehnt — Katalog-Match-Pflicht bleibt erhalten."""
    resp = client.post(
        "/api/v1/essen/wuensche",
        json={
            "label": "Unbekannt",
            "bild_ref": "2462",
            "item_id": "unbekannt:xyz",   # kein frei:-Präfix, kein Katalog-Eintrag
            "quelle": "eltern",
            "kategorie": "sonstiges",
            "klasse": "einkauf",
        },
    )
    assert resp.status_code == 400, (
        "item_id ohne frei:-Präfix und ohne Katalog-Eintrag muss 400 liefern"
    )
    body = resp.get_json()
    assert "fehler" in body
