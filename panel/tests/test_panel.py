"""Tests für die Panel-Registry (PREG-3..15, #58).

Lauf: python3 -m pytest panel/tests/ -v

Die Suite läuft ohne Netz (PREG-12): die Display-Validierung gegen die
Geräte-Registry (PREG-7) wird gestubbt — `panel.main.display_existiert` wird
durch ein Test-Double ersetzt, kein echter HTTP-Aufruf. Der Endpoint wird über
den Flask-Testclient geprüft (analog geraete/tests/test_main.py).
"""

import json
import os
import sys
import threading

import pytest

# panel/ ist ein Paket — Repo-Wurzel auf den Importpfad, damit
# `from panel import …` funktioniert. Analog geraete/tests/.
_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main          # noqa: E402
from panel import registry as registry_mod    # noqa: E402

# Die echte Display-Validierung VOR jedem Stub festhalten — ein Test prüft die
# URL-Bildung der echten Funktion (PREG-7), während der autouse-Stub sonst
# `display_existiert` ersetzt.
_ECHTES_display_existiert = panel_main.display_existiert


# ============================================================
#  Demo-Daten + Fixtures
# ============================================================

DEMO_PANELS = {
    "panels": [
        {
            "panel_id": "kueche-01",
            "source_id": "app-panel:kueche-01",
            "display_id": "pi-display-flur-01",
            "router_url": "",
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
            "display_id": "tablet-elias-01",
            "router_url": "https://hub.local:8443",
            "config": {"source_id": "app-panel:flur-01"},
            "tiles": {"tiles": []},
        },
    ],
}

# Displays, die die gestubbte Geräte-Registry kennt (PREG-7).
BEKANNTE_DISPLAYS = {"pi-display-flur-01", "tablet-elias-01"}


@pytest.fixture(autouse=True)
def stub_geraete(monkeypatch):
    """PREG-12: Geräte-Registry stubben — kein Netz.

    Default-Stub: kennt `BEKANNTE_DISPLAYS`, alles andere unbekannt. Einzelne
    Tests überschreiben das (unbekanntes Display, Registry nicht erreichbar).
    """
    def fake(display_id):
        return display_id in BEKANNTE_DISPLAYS
    monkeypatch.setattr(panel_main, "display_existiert", fake)


@pytest.fixture
def demo_instanz(tmp_path):
    p = tmp_path / "panels.json"
    p.write_text(json.dumps(DEMO_PANELS), encoding="utf-8")
    return str(p)


@pytest.fixture
def read_client(demo_instanz):
    """Lese-Modus: kein `registry_path`, In-Memory. POST liefert hier 503."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg)
    panel_main.app.testing = True
    return panel_main.app.test_client()


@pytest.fixture
def write_client(demo_instanz):
    """Schreib-Modus: `registry_path` gesetzt, POST schreibt auf Disk (PREG-15)."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, registry_path=demo_instanz)
    panel_main.app.testing = True
    return panel_main.app.test_client(), demo_instanz


# ============================================================
#  PREG-4 — Datenhaltung: Laden, fehlende Datei, 0600
# ============================================================

def test_PREG_4_missing_file_warns_and_empty(tmp_path):
    """Fehlende panels.json → leere Registry, kein Crash."""
    reg = registry_mod.load(str(tmp_path / "gibtsnicht.json"))
    assert reg.list_all() == []


def test_PREG_4_loads_all_preg3_fields(demo_instanz):
    """Datei mit Panels → alle PREG-3-Felder geladen."""
    reg = registry_mod.load(demo_instanz)
    p = reg.get("kueche-01")
    d = p.to_dict()
    for feld in ("panel_id", "source_id", "display_id", "router_url",
                 "config", "tiles"):
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
        panel_id=p.panel_id, display_id=p.display_id,
        config=p.config, tiles={"tiles": [{"key": "neu", "app": "wetter",
                                           "view": "now", "label": "W",
                                           "icons": ["arasaac/1.png"],
                                           "sichtbar": True}]},
        router_url=p.router_url)
    assert json.dumps(neu.config, sort_keys=True) == config_vorher


def test_PREG_5_create_sets_both_fields(write_client):
    """Eine Anlage (PREG-15) setzt beide Felder config + tiles."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "wohnzimmer", "display_id": "tablet-elias-01",
        "config": {"backoffs": [1]}, "tiles": {"tiles": []}})
    assert r.status_code == 200
    body = r.get_json()
    assert body["config"] == {"backoffs": [1]}
    assert body["tiles"] == {"tiles": []}


# ============================================================
#  PREG-6 — panel_id-Vergabe (IDENT-1, <slug>-<nn>)
# ============================================================

def test_PREG_6_panel_id_follows_slug_nn(write_client):
    """`panel_id` folgt IDENT-1/`<slug>-<nn>`; source_id abgeleitet."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "Mama iPhone Spielen", "display_id": "tablet-elias-01"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["panel_id"] == "mama-iphone-spielen-01"
    assert body["source_id"] == "app-panel:mama-iphone-spielen-01"


def test_PREG_6_existing_panel_id_not_reassigned(write_client):
    """Eine bereits vergebene panel_id wird nicht erneut vergeben — zwei
    Anlagen mit gleichem slug ergeben `<slug>-01` und `<slug>-02`."""
    client, _ = write_client
    r1 = client.post("/api/v1/panels/", json={
        "slug": "buero", "display_id": "tablet-elias-01"})
    r2 = client.post("/api/v1/panels/", json={
        "slug": "buero", "display_id": "tablet-elias-01"})
    assert r1.get_json()["panel_id"] == "buero-01"
    assert r2.get_json()["panel_id"] == "buero-02"


# ============================================================
#  PREG-7 — Display-Validierung gegen die Geräte-Registry
# ============================================================

def test_PREG_7_known_display_succeeds(write_client):
    """Anlage mit bekanntem display_id (gestubbt) gelingt."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "neu", "display_id": "pi-display-flur-01"})
    assert r.status_code == 200


def test_PREG_7_unknown_display_returns_400(write_client):
    """Unbekanntes display_id → 400, Registry unverändert."""
    client, path = write_client
    vorher = open(path).read()
    r = client.post("/api/v1/panels/", json={
        "slug": "neu", "display_id": "tablet-gibtsnicht-99"})
    assert r.status_code == 400
    assert "error" in r.get_json()
    assert open(path).read() == vorher


def test_PREG_7_geraete_unreachable_returns_503(write_client, monkeypatch):
    """Geräte-Registry nicht erreichbar → 503 (kein stilles Durchwinken)."""
    client, path = write_client
    vorher = open(path).read()

    def explode(display_id):
        raise panel_main._GeraeteUnreachable("connection refused")
    monkeypatch.setattr(panel_main, "display_existiert", explode)

    r = client.post("/api/v1/panels/", json={
        "slug": "neu", "display_id": "pi-display-flur-01"})
    assert r.status_code == 503
    assert "error" in r.get_json()
    assert open(path).read() == vorher


def test_PREG_7_validates_against_geraete_not_known_displays(monkeypatch):
    """Validiert über die GER-14-URL der Geräte-Registry, nicht gegen
    known_displays/routing.json — geprüft an der echten HTTP-URL-Bildung.

    Dieser Test prüft die ECHTE `display_existiert` (nicht den autouse-Stub):
    er stubbt eine Ebene tiefer (`urllib.request.urlopen`), um die gebildete
    GER-14-URL zu sehen.
    """
    aufgerufene_urls = []

    class FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(url, timeout=None):
        aufgerufene_urls.append(url)
        return FakeResp()

    monkeypatch.setattr(panel_main.urllib.request, "urlopen", fake_urlopen)
    panel_main.runtime["geraete_url"] = "http://127.0.0.1:5040"
    # Die echte Funktion aufrufen (nicht den autouse-Stub) — sie bildet die
    # GER-14-URL und ruft das gestubbte urlopen.
    assert _ECHTES_display_existiert("pi-display-flur-01") is True
    assert aufgerufene_urls == [
        "http://127.0.0.1:5040/api/v1/geraete/pi-display-flur-01"]


# ============================================================
#  PREG-8 — router_url-Semantik: leer = same-origin
# ============================================================

def test_PREG_8_missing_router_url_stored_empty(write_client):
    """Fehlender router_url wird als same-origin (leer) gespeichert und über
    die API leer zurückgegeben — kein Default-Host eingesetzt."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "same-origin", "display_id": "tablet-elias-01"})
    assert r.status_code == 200
    assert r.get_json()["router_url"] == ""


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
    r = client.post("/api/v1/panels/", json={
        "slug": "neu", "display_id": "pi-display-flur-01"})
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
    r = client.post("/api/v1/panels/", json={"display_id": "pi-display-flur-01"})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_PREG_15_post_without_display_id_returns_400(write_client):
    """POST ohne display_id → 400."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={"slug": "neu"})
    assert r.status_code == 400


def test_PREG_15_post_nested_query_in_tiles_returns_400(write_client):
    """Verschachteltes `query` in `tiles` (entgegen PANEL-7) → 400."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "neu", "display_id": "pi-display-flur-01",
        "tiles": {"tiles": [{"key": "x", "app": "plan", "view": "w",
                             "query": {"verschachtelt": {"tief": 1}},
                             "label": "X", "icons": ["a.png"],
                             "sichtbar": True}]}})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_PREG_15_post_without_registry_path_returns_503(demo_instanz):
    """Test-Modus (configure ohne registry_path) → POST liefert 503."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg)  # kein registry_path
    panel_main.app.testing = True
    client = panel_main.app.test_client()
    r = client.post("/api/v1/panels/", json={
        "slug": "neu", "display_id": "pi-display-flur-01"})
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
        r = client.post("/api/v1/panels/", json={
            "slug": "parallel", "display_id": "tablet-elias-01"})
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
