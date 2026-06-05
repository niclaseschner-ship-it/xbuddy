"""Tests für die HTTP-API der Geräte-Registry (GER-13/14/15, #212).

Lauf: python3 -m pytest geraete/tests/test_main.py -v

Die Suite läuft ohne Netz: keine echten HTTP-Aufrufe, der Endpoint wird
über den Flask-Testclient geprüft — analog familie/tests/test_familie.py.
"""

import json
import os
import sys
import threading

import pytest

# geraete/ ist ein Paket — Repo-Wurzel auf den Importpfad, damit
# `from geraete import …` funktioniert. Analog familie/tests/.
_GERAETE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_GERAETE_DIR)
sys.path.insert(0, _REPO_ROOT)

from geraete import main as geraete_main  # noqa: E402
from geraete import registry as registry_mod  # noqa: E402

# ============================================================
#  Demo-Daten + Fixtures
# ============================================================

DEMO_GERAETE = {
    "geraete": [
        {
            "id": "tablet-elias-01",
            "typ": "tablet",
            "name": "Tablet Elias",
            "aufloesung": {"w": 2560, "h": 1600},
            "os": "android",
            "verwendung": "beides",
            "status": "aktiv",
        },
        {
            "id": "pi-display-flur-01",
            "typ": "pi-display",
            "name": "Pi-Display Flur",
            "aufloesung": {"w": 1920, "h": 1080},
            "os": "linux",
            "verwendung": "display",
            "status": "aktiv",
        },
    ],
}


@pytest.fixture
def demo_instanz(tmp_path):
    """Schreibt DEMO_GERAETE in eine Datei und liefert den Pfad."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")
    return str(p)


@pytest.fixture
def read_client(demo_instanz):
    """Flask-Testclient im Lese-Modus: kein `registry_path`, In-Memory.

    Für reine Lese-Tests reicht es, das in-memory-Objekt zu setzen — der
    Schreib-Pfad (POST) ist hier nicht relevant und liefert 503 (Test-
    Modus, dokumentiertes Verhalten).
    """
    reg = registry_mod.load(demo_instanz)
    geraete_main.configure(reg)  # kein registry_path
    geraete_main.app.testing = True
    return geraete_main.app.test_client()


@pytest.fixture
def write_client(demo_instanz):
    """Flask-Testclient im Schreib-Modus: `registry_path` ist gesetzt, damit
    die POST-Endpunkte auf Disk schreiben (GER-15)."""
    reg = registry_mod.load(demo_instanz)
    geraete_main.configure(reg, registry_path=demo_instanz)
    geraete_main.app.testing = True
    return geraete_main.app.test_client(), demo_instanz


# ============================================================
#  GER-13 — GET /api/v1/geraete/ (Lese-Schnittstelle Liste)
# ============================================================

def test_GER_13_get_returns_all_devices(read_client):
    """GET liefert alle Geräte aus der Registry als JSON-Array."""
    r = read_client.get("/api/v1/geraete/")
    assert r.status_code == 200
    daten = r.get_json()
    assert isinstance(daten, list)
    ids = {g["id"] for g in daten}
    assert ids == {"tablet-elias-01", "pi-display-flur-01"}


def test_GER_13_get_includes_all_ger3_fields(read_client):
    """Jeder Eintrag trägt die GER-3-Pflichtfelder."""
    r = read_client.get("/api/v1/geraete/")
    daten = r.get_json()
    tablet = next(g for g in daten if g["id"] == "tablet-elias-01")
    for feld in ("id", "typ", "name", "aufloesung", "os", "verwendung", "status"):
        assert feld in tablet, "Feld %r fehlt" % feld
    assert tablet["aufloesung"] == {"w": 2560, "h": 1600}


# ============================================================
#  GER-14 — GET /api/v1/geraete/<id> (Einzelnes Gerät)
# ============================================================

def test_GER_14_get_known_id_returns_device(read_client):
    """GET mit bekannter `display_id` liefert das passende Gerät."""
    r = read_client.get("/api/v1/geraete/pi-display-flur-01")
    assert r.status_code == 200
    g = r.get_json()
    assert g["id"] == "pi-display-flur-01"
    assert g["typ"] == "pi-display"


def test_GER_14_get_unknown_id_returns_404_with_json_error(read_client):
    """Unbekannte `display_id` → 404 mit JSON-Fehler, kein 500."""
    r = read_client.get("/api/v1/geraete/tablet-nichtda-99")
    assert r.status_code == 404
    body = r.get_json()
    assert "error" in body


# ============================================================
#  GER-15 — POST /api/v1/geraete/ (Anlegen)
# ============================================================

def test_GER_15_post_with_valid_body_returns_200_with_ident1_id(write_client):
    """POST `{typ, name, aufloesung, os, verwendung}` → 200 + IDENT-1-`id`."""
    client, _ = write_client
    r = client.post("/api/v1/geraete/", json={
        "typ": "tablet", "name": "Tablet Wohnzimmer",
        "aufloesung": {"w": 1280, "h": 800},
        "os": "android", "verwendung": "display",
    })
    assert r.status_code == 200
    body = r.get_json()
    # IDENT-1-Form: `<typ>-<slug>-<nn>` mit Slug aus Namen.
    assert body["id"] == "tablet-tablet-wohnzimmer-01"
    assert body["typ"] == "tablet"
    assert body["status"] == "aktiv"  # Default
    assert body["aufloesung"] == {"w": 1280, "h": 800}


def test_GER_15_post_persists_atomically_to_registry(write_client):
    """Nach POST steht das Gerät in `geraete.json` und ist über GET lesbar."""
    client, registry_path = write_client
    r = client.post("/api/v1/geraete/", json={
        "typ": "monitor", "name": "Buero",
        "aufloesung": {"w": 3840, "h": 2160},
        "os": "linux", "verwendung": "display",
    })
    assert r.status_code == 200
    neue_id = r.get_json()["id"]
    # Datei direkt prüfen — Persistenz auf Disk (DCOMP-4).
    daten = json.loads(open(registry_path).read())
    assert any(g["id"] == neue_id for g in daten["geraete"])
    # Bestand byte-konsistent (DEMO zwei Geräte + neue → drei).
    r_get = client.get("/api/v1/geraete/")
    ids = {g["id"] for g in r_get.get_json()}
    assert {"tablet-elias-01", "pi-display-flur-01", neue_id} == ids


def test_GER_15_post_without_typ_returns_400(write_client):
    """POST ohne `typ` → 400 mit JSON-Fehler, Registry unverändert."""
    client, registry_path = write_client
    vorher = open(registry_path).read()
    r = client.post("/api/v1/geraete/", json={
        "name": "X", "aufloesung": {"w": 1, "h": 1},
        "os": "linux", "verwendung": "display",
    })
    assert r.status_code == 400
    assert "error" in r.get_json()
    assert open(registry_path).read() == vorher


def test_GER_15_post_without_name_returns_400(write_client):
    """POST ohne `name` → 400."""
    client, _ = write_client
    r = client.post("/api/v1/geraete/", json={
        "typ": "tablet", "aufloesung": {"w": 1, "h": 1},
        "os": "linux", "verwendung": "display",
    })
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_GER_15_post_with_unknown_typ_returns_400(write_client):
    """`typ` außerhalb GER-2 → 400."""
    client, _ = write_client
    r = client.post("/api/v1/geraete/", json={
        "typ": "drohne", "name": "X",
        "aufloesung": {"w": 1, "h": 1},
        "os": "linux", "verwendung": "display",
    })
    assert r.status_code == 400


def test_GER_15_post_with_bad_aufloesung_returns_400(write_client):
    """`aufloesung` ohne `{w,h}` mit positiven Ganzzahlen → 400 (nicht 500)."""
    client, _ = write_client
    r = client.post("/api/v1/geraete/", json={
        "typ": "tablet", "name": "X",
        "aufloesung": "1280x800",  # String statt {w,h}
        "os": "linux", "verwendung": "display",
    })
    assert r.status_code == 400


def test_GER_15_post_with_unknown_os_returns_400(write_client):
    """`os` außerhalb GER-3 → 400."""
    client, _ = write_client
    r = client.post("/api/v1/geraete/", json={
        "typ": "tablet", "name": "X",
        "aufloesung": {"w": 1, "h": 1},
        "os": "windows-phone", "verwendung": "display",
    })
    assert r.status_code == 400


def test_GER_15_post_without_registry_path_returns_503(demo_instanz):
    """Test-Modus (configure ohne `registry_path`) → POST liefert 503."""
    reg = registry_mod.load(demo_instanz)
    geraete_main.configure(reg)  # kein registry_path → In-Memory
    geraete_main.app.testing = True
    client = geraete_main.app.test_client()
    r = client.post("/api/v1/geraete/", json={
        "typ": "tablet", "name": "X",
        "aufloesung": {"w": 1, "h": 1},
        "os": "linux", "verwendung": "display",
    })
    assert r.status_code == 503
    assert "error" in r.get_json()


def test_GER_15_slug_collision_increments_nn(write_client):
    """Zweimal denselben Namen+Typ anlegen → `-01`, `-02` (GER-7)."""
    client, _ = write_client
    r1 = client.post("/api/v1/geraete/", json={
        "typ": "monitor", "name": "Buero",
        "aufloesung": {"w": 1, "h": 1},
        "os": "linux", "verwendung": "display",
    })
    r2 = client.post("/api/v1/geraete/", json={
        "typ": "monitor", "name": "Buero",
        "aufloesung": {"w": 1, "h": 1},
        "os": "linux", "verwendung": "display",
    })
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json()["id"] == "monitor-buero-01"
    assert r2.get_json()["id"] == "monitor-buero-02"


def test_GER_15_parallel_posts_yield_two_distinct_ids(write_client):
    """Parallele POSTs (verschiedene Threads) führen zu zwei verschiedenen
    `display_id`s — der `_write_lock` verhindert verlorengehende Updates.
    Beide Einträge müssen in der Registry stehen (DCOMP-4 atomar)."""
    client, registry_path = write_client
    ergebnisse = []
    barrier = threading.Barrier(2)

    def post_einmal():
        barrier.wait()
        r = client.post("/api/v1/geraete/", json={
            "typ": "tablet", "name": "Lina",
            "aufloesung": {"w": 1, "h": 1},
            "os": "android", "verwendung": "display",
        })
        ergebnisse.append(r.get_json()["id"])

    t1 = threading.Thread(target=post_einmal)
    t2 = threading.Thread(target=post_einmal)
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert len(ergebnisse) == 2
    assert ergebnisse[0] != ergebnisse[1]
    # Beide Einträge stehen in der Registry — kein Lost Update.
    daten = json.loads(open(registry_path).read())
    alle_ids = {g["id"] for g in daten["geraete"]}
    assert ergebnisse[0] in alle_ids
    assert ergebnisse[1] in alle_ids
