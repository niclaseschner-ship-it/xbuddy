"""Tests für die Panel-Registry (PREG-3..15, #58).

Lauf: python3 -m pytest panel/tests/ -v

Die Registry ist eine reine tiles/config/panel_id-Registry (RAT-31 E6a):
keine Display-Bindung, keine Router-Kopplung. Der Endpoint wird über den
Flask-Testclient geprüft.
"""

import json
import os
import sys
import threading

import pytest

# panel/ ist ein Paket — Repo-Wurzel auf den Importpfad, damit
# `from panel import …` funktioniert.
_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main  # noqa: E402
from panel import registry as registry_mod  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

# AUTH-11 (#1834): `GET /api/v1/panels/`, `GET /api/v1/panels/<id>` und
# `POST /api/v1/panels/` tragen den Dual-Gate — deren Testclients hier
# brauchen einen gültigen Session-Cookie. `.../config.json`/`.../tiles.json`
# bleiben ungegated (Watchdog-Befund 2026-08-11/12: laufen live über den
# PREG-9-Proxy in seiten ohne Cookie, panel/main.py::get_panel_config) — der
# Cookie schadet ihnen nicht, ist für sie aber nicht die Bedingung.
_BOT_TOKEN = "123456:ABCdef_panel_test_token"

# ============================================================
#  Demo-Daten + Fixtures
# ============================================================

DEMO_PANELS = {
    "panels": [
        {
            "panel_id": "kueche-01",
            "source_id": "app-panel:kueche-01",
            "config": {"source_id": "app-panel:kueche-01", "backoffs": [200]},
            "tiles": {"tiles": [
                {"key": "a", "app": "plan", "view": "woche",
                 "label": "Plan", "icons": ["arasaac/32488.png"],
                 "sichtbar": True},
            ]},
        },
        {
            "panel_id": "flur-01",
            "source_id": "app-panel:flur-01",
            "config": {"source_id": "app-panel:flur-01"},
            "tiles": {"tiles": []},
        },
    ],
}


@pytest.fixture
def demo_instanz(tmp_path):
    p = tmp_path / "panels.json"
    p.write_text(json.dumps(DEMO_PANELS), encoding="utf-8")
    return str(p)


@pytest.fixture
def read_client(demo_instanz):
    """Lese-Modus: kein `registry_path`, In-Memory. POST liefert hier 503.

    AUTH-11 (#1834): der Client trägt einen gültigen Session-Cookie für die
    gegateten Routen (`GET /api/v1/panels/`, `.../<id>`) — additiv, ändert
    keine bestehende Zusicherung; für die weiterhin ungegateten
    `.../config.json`/`.../tiles.json` (s. Kommentar oben) ist er wirkungslos."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    client = panel_main.app.test_client()
    client.set_cookie(sc.COOKIE_NAME, sc.sign_session("op", _BOT_TOKEN))
    return client


@pytest.fixture
def write_client(demo_instanz):
    """Schreib-Modus: `registry_path` gesetzt, POST schreibt auf Disk (PREG-15).

    AUTH-11 (#1834): der Client trägt einen gültigen Session-Cookie — nötig
    für `POST /api/v1/panels/` (literal `mode="hard"`, AUTH-3.a) und die
    gegateten Lese-Routen (additiv, ändert keine bestehende Zusicherung)."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, registry_path=demo_instanz, bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    client = panel_main.app.test_client()
    client.set_cookie(sc.COOKIE_NAME, sc.sign_session("op", _BOT_TOKEN))
    return client, demo_instanz


# ============================================================
#  PREG-4 — Datenhaltung: Laden, fehlende Datei, 0600
# ============================================================

def test_healthz_gibt_200(read_client):
    """SVC-1: GET /healthz liefert immer 200 + ok."""
    resp = read_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_PREG_4_missing_file_warns_and_empty(tmp_path):
    """Fehlende panels.json → leere Registry, kein Crash."""
    reg = registry_mod.load(str(tmp_path / "gibtsnicht.json"))
    assert reg.list_all() == []


def test_PREG_4_loads_all_preg3_fields(demo_instanz):
    """Datei mit Panels → alle PREG-3-Felder geladen."""
    reg = registry_mod.load(demo_instanz)
    p = reg.get("kueche-01")
    d = p.to_dict()
    for feld in ("panel_id", "source_id", "config", "tiles"):
        assert feld in d, "Feld %r fehlt" % feld
    assert d["source_id"] == "app-panel:kueche-01"


def test_PREG_4_save_sets_0600(tmp_path):
    """Schreiben setzt 0600 (familienprivat)."""
    reg = registry_mod.load(str(tmp_path / "x.json"))
    path = str(tmp_path / "panels.json")
    registry_mod.save(reg, path)
    assert registry_mod.is_owner_only(path)


# ============================================================
#  PREG-5 — getrennte Schreib-Rechte für config und tiles
# ============================================================

def test_PREG_5_tile_change_leaves_config_byte_identical(write_client):
    """Eine simulierte Tile-Änderung (OPEN-PREG-A-Vorgriff) berührt `config`
    byte-gleich nicht — die Felder haben getrennte Lebenszyklen."""
    _, path = write_client
    reg = registry_mod.load(path)
    p = reg.get("kueche-01")
    config_vorher = json.dumps(p.config, sort_keys=True)
    # Nur tiles ändern, config unangetastet (das Modell hält sie getrennt).
    neu = registry_mod.Panel(
        panel_id=p.panel_id,
        config=p.config, tiles={"tiles": [{"key": "neu", "app": "wetter",
                                           "view": "now", "label": "W",
                                           "icons": ["arasaac/1.png"],
                                           "sichtbar": True}]})
    assert json.dumps(neu.config, sort_keys=True) == config_vorher


def test_PREG_5_create_sets_both_fields(write_client):
    """Eine Anlage (PREG-15) setzt beide Felder config + tiles.
    Config enthält das Identitätsfeld source_id (server-autoritativ, PREG-15) + Tuning."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "wohnzimmer",
        "config": {"backoffs": [1]}, "tiles": {"tiles": []}})
    assert r.status_code == 200
    body = r.get_json()
    # Tuning-Feld bleibt erhalten; source_id ist server-gesetzt.
    assert body["config"]["backoffs"] == [1]
    assert body["config"]["source_id"] == "app-panel:%s" % body["panel_id"]
    assert body["tiles"] == {"tiles": []}


# ============================================================
#  PREG-6 — panel_id-Vergabe (IDENT-1, <slug>-<nn>)
# ============================================================

def test_PREG_6_panel_id_follows_slug_nn(write_client):
    """`panel_id` folgt IDENT-1/`<slug>-<nn>`; source_id abgeleitet."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={"slug": "Mama iPhone Spielen"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["panel_id"] == "mama-iphone-spielen-01"
    assert body["source_id"] == "app-panel:mama-iphone-spielen-01"


def test_PREG_6_existing_panel_id_not_reassigned(write_client):
    """Eine bereits vergebene panel_id wird nicht erneut vergeben — zwei
    Anlagen mit gleichem slug ergeben `<slug>-01` und `<slug>-02`."""
    client, _ = write_client
    r1 = client.post("/api/v1/panels/", json={"slug": "buero"})
    r2 = client.post("/api/v1/panels/", json={"slug": "buero"})
    assert r1.get_json()["panel_id"] == "buero-01"
    assert r2.get_json()["panel_id"] == "buero-02"


# ============================================================
#  PREG-13 — GET /api/v1/panels/ (alle Instanzen)
# ============================================================

def test_PREG_13_get_returns_all_panels(read_client):
    """GET liefert alle Panels als JSON-Array."""
    r = read_client.get("/api/v1/panels/")
    assert r.status_code == 200
    daten = r.get_json()
    assert isinstance(daten, list)
    ids = {p["panel_id"] for p in daten}
    assert ids == {"kueche-01", "flur-01"}


# ============================================================
#  PREG-14 — GET /api/v1/panels/<id> + config.json/tiles.json
# ============================================================

def test_PREG_14_get_known_id_returns_panel(read_client):
    """GET mit bekannter panel_id liefert die passende Instanz."""
    r = read_client.get("/api/v1/panels/kueche-01")
    assert r.status_code == 200
    assert r.get_json()["panel_id"] == "kueche-01"


def test_PREG_14_get_unknown_id_returns_404(read_client):
    """Unbekannte panel_id → 404 mit JSON-Fehler."""
    r = read_client.get("/api/v1/panels/gibtsnicht-99")
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_PREG_14_config_json_view(read_client):
    """`/config.json` liefert das config-Feld als eigenständiges Dokument."""
    r = read_client.get("/api/v1/panels/kueche-01/config.json")
    assert r.status_code == 200
    assert r.get_json() == {"source_id": "app-panel:kueche-01",
                            "backoffs": [200]}


def test_PREG_14_tiles_json_view(read_client):
    """`/tiles.json` liefert das tiles-Feld als eigenständiges Dokument."""
    r = read_client.get("/api/v1/panels/kueche-01/tiles.json")
    assert r.status_code == 200
    body = r.get_json()
    assert "tiles" in body and body["tiles"][0]["key"] == "a"


def test_PREG_14_config_json_unknown_id_404(read_client):
    """Unbekannte panel_id auch bei der Serving-Sicht → 404."""
    r = read_client.get("/api/v1/panels/gibtsnicht-99/config.json")
    assert r.status_code == 404


# ============================================================
#  PREG-15 — POST /api/v1/panels/ (Anlegen)
# ============================================================

def test_PREG_15_post_valid_returns_200_and_persists(write_client):
    """POST mit gültigem Body → 200 + IDENT-1-panel_id, atomar persistiert."""
    client, path = write_client
    r = client.post("/api/v1/panels/", json={"slug": "neu"})
    assert r.status_code == 200
    pid = r.get_json()["panel_id"]
    daten = json.loads(open(path).read())
    assert any(p["panel_id"] == pid for p in daten["panels"])
    # Über GET sichtbar (Reload-on-Read).
    r_get = client.get("/api/v1/panels/")
    ids = {p["panel_id"] for p in r_get.get_json()}
    assert {"kueche-01", "flur-01", pid} == ids


def test_PREG_15_post_without_slug_returns_400(write_client):
    """POST ohne slug → 400."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={"config": {}})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_PREG_15_post_nested_query_in_tiles_returns_400(write_client):
    """Verschachteltes `query` in `tiles` (entgegen PANEL-7) → 400."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "neu",
        "tiles": {"tiles": [{"key": "x", "app": "plan", "view": "w",
                             "query": {"verschachtelt": {"tief": 1}},
                             "label": "X", "icons": ["a.png"],
                             "sichtbar": True}]}})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_PREG_15_post_without_registry_path_returns_503(demo_instanz):
    """Test-Modus (configure ohne registry_path) → POST liefert 503.

    AUTH-11 (#1834): gültiger Cookie nötig, damit der Request überhaupt am
    Gate vorbeikommt und die 503-Aussage (kein registry_path) geprüft wird."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, bot_token=_BOT_TOKEN)  # kein registry_path
    panel_main.app.testing = True
    client = panel_main.app.test_client()
    client.set_cookie(sc.COOKIE_NAME, sc.sign_session("op", _BOT_TOKEN))
    r = client.post("/api/v1/panels/", json={"slug": "neu"})
    assert r.status_code == 503
    assert "error" in r.get_json()


def test_PREG_15_parallel_posts_yield_two_distinct_ids(write_client):
    """Parallele POSTs (verschiedene Threads) → zwei verschiedene panel_ids,
    beide persistiert — der `_write_lock` verhindert verlorengehende Updates."""
    client, path = write_client
    ergebnisse = []
    barrier = threading.Barrier(2)

    def post_einmal():
        barrier.wait()
        r = client.post("/api/v1/panels/", json={"slug": "parallel"})
        ergebnisse.append(r.get_json()["panel_id"])

    t1 = threading.Thread(target=post_einmal)
    t2 = threading.Thread(target=post_einmal)
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert len(ergebnisse) == 2
    assert ergebnisse[0] != ergebnisse[1]
    daten = json.loads(open(path).read())
    alle = {p["panel_id"] for p in daten["panels"]}
    assert ergebnisse[0] in alle
    assert ergebnisse[1] in alle


# ============================================================
#  PREG-15 — server-autoritativer config-Aufbau (Nic-Entscheid 2026-06-03)
#  source_id immer server-gesetzt, Tuning bleibt erhalten
# ============================================================

def test_PREG_15_post_without_config_has_identity_fields(write_client):
    """POST ohne config → config enthält source_id (server-gesetzt).
    Nie mehr das leere Objekt {} — das verletzte PANEL-8 (Pflichtfelder)."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={"slug": "identitaet"})
    assert r.status_code == 200
    body = r.get_json()
    panel_id = body["panel_id"]
    cfg = body["config"]
    # source_id ist server-gesetzt (PREG-15, PANEL-8).
    assert cfg["source_id"] == "app-panel:%s" % panel_id


def test_PREG_15_tuning_preserved_identity_server_set(write_client):
    """POST mit Tuning-config (backoffs) → Tuning bleibt, source_id
    server-gesetzt (überschreibt ggf. falsch mitgegebene source_id)."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "tuning",
        "config": {
            "backoffs": [100, 200, 400],
            # Aufrufer liefert falsche source_id — Server überschreibt.
            "source_id": "app-panel:FALSCH",
        }})
    assert r.status_code == 200
    body = r.get_json()
    panel_id = body["panel_id"]
    cfg = body["config"]
    # Tuning bleibt erhalten.
    assert cfg["backoffs"] == [100, 200, 400]
    # source_id ist server-gesetzt — Aufrufer-Wert überschrieben.
    assert cfg["source_id"] == "app-panel:%s" % panel_id


def test_PREG_15_panel8_consistency_source_id_matches_panel_id(write_client):
    """PANEL-8-Konsistenz — config.source_id == app-panel:<panel_id>
    für jede angelegte Panel-Instanz."""
    client, _ = write_client
    for slug in ("alpha", "beta"):
        r = client.post("/api/v1/panels/", json={"slug": slug})
        assert r.status_code == 200
        body = r.get_json()
        erwartet = "app-panel:%s" % body["panel_id"]
        assert body["config"]["source_id"] == erwartet, (
            "PANEL-8-Konsistenz verletzt für panel_id=%r" % body["panel_id"])
