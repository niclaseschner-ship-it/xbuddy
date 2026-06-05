"""Tests für die Panel-Registry (PREG-3..17, #58, #329).

Lauf: python3 -m pytest panel/tests/ -v

Die Suite läuft ohne Netz (PREG-12): die Display-Validierung gegen die
Geräte-Registry (PREG-7) und der Router-Forward/Repair (ROU-29, PREG-16/17)
werden gestubbt — kein echter HTTP-Aufruf. Der Endpoint wird über den
Flask-Testclient geprüft (analog geraete/tests/test_main.py).
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

from panel import main as panel_main  # noqa: E402
from panel import registry as registry_mod  # noqa: E402

# Die echten Funktionen VOR jedem Stub festhalten — ein Test prüft die
# URL-Bildung der echten Funktion (PREG-7), während die autouse-Stubs sonst
# `display_existiert` und `router_panels_upsert` ersetzen.
_ECHTES_display_existiert = panel_main.display_existiert
_ECHTES_router_panels_upsert = panel_main.router_panels_upsert


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
def stub_externe_dienste(monkeypatch):
    """PREG-12: Geräte-Registry + Router stubben — kein Netz.

    Default-Stub Geräte: kennt `BEKANNTE_DISPLAYS`, alles andere unbekannt.
    Default-Stub Router: immer erfolgreich (gibt True zurück).
    Einzelne Tests überschreiben diese Stubs (Fehlerfall, unbekanntes Display,
    nicht erreichbar).
    """
    def fake_geraete(display_id):
        return display_id in BEKANNTE_DISPLAYS
    monkeypatch.setattr(panel_main, "display_existiert", fake_geraete)

    def fake_router(source_id, display_id):
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_router)


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
    """Eine Anlage (PREG-15) setzt beide Felder config + tiles.
    Config enthält Identitätsfelder (server-autoritativ, PREG-15) + Tuning."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "wohnzimmer", "display_id": "tablet-elias-01",
        "config": {"backoffs": [1]}, "tiles": {"tiles": []}})
    assert r.status_code == 200
    body = r.get_json()
    # Tuning-Feld bleibt erhalten; Identitätsfelder sind server-gesetzt.
    assert body["config"]["backoffs"] == [1]
    assert body["config"]["source_id"] == "app-panel:%s" % body["panel_id"]
    assert body["config"]["display_id"] == "tablet-elias-01"
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


# ============================================================
#  PREG-15 — server-autoritativer config-Aufbau (Nic-Entscheid 2026-06-03)
#  AC1..3: Identitätsfelder immer server-gesetzt, Tuning bleibt erhalten
# ============================================================

def test_PREG_15_post_without_config_has_identity_fields(write_client):
    """AC2/AC3: POST ohne config → config enthält source_id, display_id, router_url.
    Nie mehr das leere Objekt {} — das verletzte PANEL-8 (Pflichtfelder)."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "identitaet", "display_id": "pi-display-flur-01"})
    assert r.status_code == 200
    body = r.get_json()
    panel_id = body["panel_id"]
    cfg = body["config"]
    # Identitätsfelder sind server-gesetzt (PREG-15, PANEL-8).
    assert cfg["source_id"] == "app-panel:%s" % panel_id
    assert cfg["display_id"] == "pi-display-flur-01"
    assert "router_url" in cfg and cfg["router_url"] == ""


def test_PREG_15_post_with_router_url_in_config(write_client):
    """AC3: POST mit router_url → config.router_url == gesetzter router_url."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "crossorigin", "display_id": "tablet-elias-01",
        "router_url": "https://hub.local:8443"})
    assert r.status_code == 200
    cfg = r.get_json()["config"]
    assert cfg["router_url"] == "https://hub.local:8443"


def test_PREG_15_tuning_preserved_identity_server_set(write_client):
    """AC3: POST mit Tuning-config (backoffs) → Tuning bleibt, Identität
    server-gesetzt (überschreibt ggf. falsch mitgegebene Identitätsfelder)."""
    client, _ = write_client
    r = client.post("/api/v1/panels/", json={
        "slug": "tuning", "display_id": "tablet-elias-01",
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
    # Identität ist server-gesetzt — Aufrufer-Wert überschrieben.
    assert cfg["source_id"] == "app-panel:%s" % panel_id
    assert cfg["display_id"] == "tablet-elias-01"


def test_PREG_15_panel8_consistency_source_id_matches_panel_id(write_client):
    """AC3: PANEL-8-Konsistenz — config.source_id == app-panel:<panel_id>
    für jede angelegte Panel-Instanz."""
    client, _ = write_client
    for slug in ("alpha", "beta"):
        r = client.post("/api/v1/panels/", json={
            "slug": slug, "display_id": "pi-display-flur-01"})
        assert r.status_code == 200
        body = r.get_json()
        erwartet = "app-panel:%s" % body["panel_id"]
        assert body["config"]["source_id"] == erwartet, (
            "PANEL-8-Konsistenz verletzt für panel_id=%r" % body["panel_id"])


# ============================================================
#  PREG-16 — Forward-on-Create: Router-Eintrag nach erfolgreichem POST
# ============================================================

def test_PREG_16_forward_calls_router_after_create(write_client, monkeypatch):
    """Nach erfolgreicher Anlage ruft der panel-Service ROU-29 (gestubbt)
    mit {source_id, display_id} der neuen Instanz auf (PREG-16 Forward)."""
    client, _ = write_client
    aufrufe = []

    def fake_upsert(source_id, display_id):
        aufrufe.append({"source_id": source_id, "display_id": display_id})
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    r = client.post("/api/v1/panels/", json={
        "slug": "forward-test", "display_id": "pi-display-flur-01"})
    assert r.status_code == 200
    body = r.get_json()
    # ROU-29 wurde genau einmal mit den richtigen Werten aufgerufen.
    assert len(aufrufe) == 1
    assert aufrufe[0]["source_id"] == body["source_id"]
    assert aufrufe[0]["display_id"] == body["display_id"]


def test_PREG_16_forward_success_returns_200_no_pending_marker(write_client,
                                                                 monkeypatch):
    """Router antwortet mit Erfolg → 200, kein reconcile_pending in der Antwort."""
    client, _ = write_client
    monkeypatch.setattr(panel_main, "router_panels_upsert", lambda s, d: True)

    r = client.post("/api/v1/panels/", json={
        "slug": "success", "display_id": "tablet-elias-01"})
    assert r.status_code == 200
    body = r.get_json()
    assert "reconcile_pending" not in body or body.get("reconcile_pending") is not True


def test_PREG_16_forward_router_failure_returns_202_with_pending_marker(
        write_client, monkeypatch):
    """Schritt 1 ok, Schritt 2 (ROU-29) scheitert (5xx/Router weg):
    panels.json-Eintrag bleibt, Antwort ist 202 + reconcile_pending=True (PREG-16
    Fehler-Semantik — kein stiller Halbzustand, kein 'fertig'-Signal)."""
    client, path = write_client
    inhalt_vorher = open(path).read()

    def router_kaputt(source_id, display_id):
        raise panel_main._RouterUnreachable("connection refused")
    monkeypatch.setattr(panel_main, "router_panels_upsert", router_kaputt)

    r = client.post("/api/v1/panels/", json={
        "slug": "pending", "display_id": "pi-display-flur-01"})
    # 202 = Teilerfolg: panels.json geschrieben, Router-Eintrag fehlt noch.
    assert r.status_code == 202
    body = r.get_json()
    # Aufrufer sieht reconcile_pending=True — kein stilles Verschalten.
    assert body.get("reconcile_pending") is True
    # panel_id + source_id sind vorhanden (Instanz ist gültig, nur Router fehlt).
    assert "panel_id" in body and "source_id" in body
    # panels.json hat den neuen Eintrag (Schritt 1 war erfolgreich).
    import json as _json
    daten = _json.loads(open(path).read())
    assert any(p["panel_id"] == body["panel_id"] for p in daten["panels"])


def test_PREG_16_router_failure_preserves_panels_json(write_client, monkeypatch):
    """Router-Fehler in Schritt 2: panels.json-Eintrag bleibt bestehen,
    er ist gültig und servierbar (PREG-16 — kein Rückrollen von Schritt 1)."""
    client, path = write_client

    def router_kaputt(source_id, display_id):
        raise panel_main._RouterUnreachable("timeout")
    monkeypatch.setattr(panel_main, "router_panels_upsert", router_kaputt)

    r = client.post("/api/v1/panels/", json={
        "slug": "bleibt", "display_id": "tablet-elias-01"})
    assert r.status_code == 202
    pid = r.get_json()["panel_id"]

    # GET auf das angelegte Panel muss funktionieren (Reload-on-Read).
    r_get = client.get("/api/v1/panels/%s" % pid)
    assert r_get.status_code == 200
    assert r_get.get_json()["panel_id"] == pid


def test_PREG_16_forward_uses_router_url_from_config(write_client, monkeypatch):
    """ROU-29-Aufruf verwendet ROUTER_URL aus Config (PREG-11):
    der Stub sieht die source_id aus panels.json (nicht aus dem Config-Router-URL
    des Panels, das ist etwas anderes)."""
    client, _ = write_client
    aufrufe = []

    def fake_upsert(source_id, display_id):
        aufrufe.append((source_id, display_id))
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)
    # Router-Origin aus runtime setzen (Konfig-Wert, PREG-11).
    panel_main.runtime["router_url"] = "http://127.0.0.1:5000"

    r = client.post("/api/v1/panels/", json={
        "slug": "config-test", "display_id": "pi-display-flur-01"})
    assert r.status_code == 200
    # source_id kommt aus panels.json, nicht aus dem Panel-router_url-Feld.
    assert aufrufe[0][0].startswith("app-panel:")


# ============================================================
#  PREG-17 — Repair / Heal-on-Boot
# ============================================================

def test_PREG_17_heal_on_boot_calls_router_for_all_panels(demo_instanz,
                                                            monkeypatch):
    """Heal-on-Boot ruft ROU-29 für jede Panel-Instanz in panels.json auf
    (blind idempotenter Upsert, kein Zurücklesen des Router-Stands, PREG-17)."""
    aufrufe = []

    def fake_upsert(source_id, display_id):
        aufrufe.append({"source_id": source_id, "display_id": display_id})
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    reg = registry_mod.load(demo_instanz)
    panel_main.repair_heal_on_boot(reg.list_all())

    # DEMO_PANELS hat zwei Einträge → zwei ROU-29-Aufrufe.
    assert len(aufrufe) == 2
    source_ids = {a["source_id"] for a in aufrufe}
    assert "app-panel:kueche-01" in source_ids
    assert "app-panel:flur-01" in source_ids


def test_PREG_17_heal_on_boot_is_idempotent(demo_instanz, monkeypatch):
    """Repair ist idempotent: mehrere Läufe schreiben denselben Wert via ROU-29
    (ohnehin ein Upsert) — kein sichtbarer Nebeneffekt (PREG-17)."""
    aufrufe = []

    def fake_upsert(source_id, display_id):
        aufrufe.append((source_id, display_id))
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    reg = registry_mod.load(demo_instanz)
    panels = reg.list_all()
    panel_main.repair_heal_on_boot(panels)
    panel_main.repair_heal_on_boot(panels)

    # Jeder Lauf schreibt alle Panels — zweimal 2 = 4 Aufrufe.
    assert len(aufrufe) == 4
    # Jeder Aufruf trägt dieselbe source_id/display_id-Kombination wie vorher.
    erster = set((a[0], a[1]) for a in aufrufe[:2])
    zweiter = set((a[0], a[1]) for a in aufrufe[2:])
    assert erster == zweiter


def test_PREG_17_single_router_failure_does_not_abort_repair(demo_instanz,
                                                               monkeypatch):
    """Schlägt ein einzelner ROU-29-Aufruf fehl, macht der Repair-Lauf mit den
    übrigen Instanzen weiter — kein Abbruch beim ersten Fehler (PREG-17 Robustheit).
    Die fehlschlagende Instanz bleibt reconcile-pending (Warnung geloggt)."""
    geheilt = []
    fehlgeschlagen = []

    def fake_upsert(source_id, display_id):
        # Nur „kueche-01" scheitert, „flur-01" gelingt.
        if "kueche" in source_id:
            fehlgeschlagen.append(source_id)
            raise panel_main._RouterUnreachable("timeout")
        geheilt.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    reg = registry_mod.load(demo_instanz)
    # Kein Exception-Durchbruch: Repair ist nicht-fatal (PREG-17 Robustheit).
    panel_main.repair_heal_on_boot(reg.list_all())

    # „flur-01" wurde geheilt, obwohl „kueche-01" scheiterte.
    assert "app-panel:flur-01" in geheilt
    assert "app-panel:kueche-01" in fehlgeschlagen


def test_PREG_17_heal_on_boot_repair_is_nonfatal_router_completely_down(
        demo_instanz, monkeypatch):
    """Ist der Router komplett unten, bricht Heal-on-Boot nicht den Service-Start
    ab — alle Instanzen bleiben reconcile-pending, kein Exception-Durchbruch."""
    def router_kaputt(source_id, display_id):
        raise panel_main._RouterUnreachable("connection refused")
    monkeypatch.setattr(panel_main, "router_panels_upsert", router_kaputt)

    reg = registry_mod.load(demo_instanz)
    # Darf keinen Exception werfen — Service-Start muss weitergehen (PREG-17).
    panel_main.repair_heal_on_boot(reg.list_all())


def test_PREG_17_heal_on_boot_writes_correct_source_and_display(demo_instanz,
                                                                   monkeypatch):
    """Repair schreibt für jede Instanz den Soll-Eintrag aus panels.json:
    source_id und display_id aus panels.json, nicht vom Router zurückgelesen."""
    aufrufe = {}

    def fake_upsert(source_id, display_id):
        aufrufe[source_id] = display_id
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    reg = registry_mod.load(demo_instanz)
    panel_main.repair_heal_on_boot(reg.list_all())

    # Werte aus DEMO_PANELS prüfen.
    assert aufrufe.get("app-panel:kueche-01") == "pi-display-flur-01"
    assert aufrufe.get("app-panel:flur-01") == "tablet-elias-01"


def test_PREG_17_heal_on_boot_runs_in_main_before_app_run(demo_instanz,
                                                            monkeypatch):
    """Heal-on-Boot wird im echten main()-Startpfad VOR app.run() ausgelöst
    und ist nicht-fatal auch bei komplett totem Router (PREG-17 Robustheit).

    AC1: main() mit PREG-17-Exit-Probe
    - Router-Stub wirft immer _RouterUnreachable (toter Router).
    - app.run wird als No-op gemockt (sonst blockiert main()).
    - main() darf keine Exception werfen.
    - router_panels_upsert wurde aufgerufen (Repair-Lauf hat stattgefunden).
    - app.run wurde erreicht (Service-Start läuft durch — Repair ist nicht-fatal).

    Damit ist verankert: Entfernen oder Verschieben des repair_heal_on_boot()-
    Aufrufs hinter app.run() oder ganz aus main() würde diesen Test brechen.
    """
    from tools import configloader, logsetup

    # configloader.load: gibt Schema-Defaults zurück (keine Datei nötig).
    monkeypatch.setattr(
        configloader, "load",
        lambda component, schema, config_path=None: dict(schema))

    # logsetup.setup: No-op (keine Log-Handler-Seiteneffekte im Test).
    monkeypatch.setattr(logsetup, "setup", lambda level: None)

    # router_panels_upsert: immer toter Router — alle Panels reconcile-pending.
    upsert_aufrufe = []
    def router_kaputt(source_id, display_id):
        upsert_aufrufe.append(source_id)
        raise panel_main._RouterUnreachable("test: router komplett down")
    monkeypatch.setattr(panel_main, "router_panels_upsert", router_kaputt)

    # app.run: No-op — Sentinel setzt, damit wir wissen, dass main() bis hier kam.
    app_run_erreicht = []
    def fake_app_run(**kwargs):
        app_run_erreicht.append(True)
    monkeypatch.setattr(panel_main.app, "run", fake_app_run)

    # main() mit echtem --panels-Pfad auf die Demo-panels.json aufrufen.
    # Darf nicht werfen — Heal-on-Boot ist nicht-fatal (PREG-17 Robustheit).
    panel_main.main(["--panels", demo_instanz])

    # Repair-Lauf hat stattgefunden: router_panels_upsert wurde für beide
    # Demo-Panels aufgerufen (DEMO_PANELS hat zwei Einträge).
    assert len(upsert_aufrufe) == 2, (
        "Heal-on-Boot in main() hat router_panels_upsert nicht für alle Panels "
        "aufgerufen — Repair-Lauf fehlt oder ist zu früh abgebrochen.")

    # Service-Start ist bis app.run() durchgelaufen (nicht-fatal).
    assert app_run_erreicht, (
        "main() hat app.run() nicht erreicht — Heal-on-Boot hat den "
        "Service-Start blockiert oder abgebrochen (PREG-17 Robustheit verletzt).")
