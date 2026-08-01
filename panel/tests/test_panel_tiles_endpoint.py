"""Tests für PBE-4: PUT /api/v1/panels/<panel_id>/tiles (#330).

Abgedeckt:
  test_pbe4_valid_put_writes_atomically            — Happy-Path + Hash-Check vor/nach
  test_pbe4_invalid_list_returns_422_unchanged     — Byte-Unverändert bei Validierungsfehler
  test_pbe4_unknown_panel_id_returns_404           — 404 für unbekannte panel_id
  test_pbe4_config_field_not_touched               — PREG-5: config unberührt
  test_pbe4_empty_tiles_list_is_valid              — PBE-9: leere Liste erlaubt
  test_pbe4_key_collision_returns_422              — PANEL-3: doppelter key → 422
  test_pbe4_icons_empty_returns_422                — PANEL-3: leere icons[] → 422
  test_pbe4_icons_too_many_returns_422             — PANEL-3: icons[] > 3 → 422
  test_pbe4_sichtbar_not_bool_returns_422          — PANEL-4: sichtbar kein boolean → 422
  test_pbe4_nested_query_returns_422               — PANEL-7: verschachteltes query → 422
  test_pbe4_no_registry_path_returns_503           — Test-Modus ohne registry_path → 503
  test_pbe4_other_panels_preserved                 — andere Panels bleiben erhalten
  test_pbe4_last_write_wins_zwei_sequentielle_puts — PBE-4: zweiter PUT gewinnt vollständig

Lauf: python3 -m pytest panel/tests/ -v
"""

import hashlib
import json
import os
import sys

import pytest

_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main  # noqa: E402
from panel import registry as registry_mod  # noqa: E402

# ============================================================
#  Demo-Daten + Fixtures
# ============================================================

DEMO_PANELS = {
    "panels": [
        {
            "panel_id": "kueche-01",
            "source_id": "app-panel:kueche-01",
            "config": {
                "source_id": "app-panel:kueche-01",
                "backoffs": [200, 1000, 5000],
            },
            "tiles": {
                "tiles": [
                    {
                        "key": "wochenplan",
                        "app": "plan",
                        "view": "woche",
                        "label": "Wochenplan",
                        "icons": ["arasaac/32488.png"],
                        "sichtbar": True,
                    }
                ]
            },
        },
        {
            "panel_id": "flur-01",
            "source_id": "app-panel:flur-01",
            "config": {"source_id": "app-panel:flur-01"},
            "tiles": {"tiles": []},
        },
    ]
}

GUELTIGE_TILES = {
    "tiles": [
        {
            "key": "wetter",
            "app": "wetter",
            "view": "now",
            "label": "Wetter",
            "icons": ["arasaac/32488.png"],
            "sichtbar": True,
        },
        {
            "key": "plan",
            "app": "plan",
            "view": "woche",
            "label": "Wochenplan",
            "icons": ["arasaac/1.png", "arasaac/2484.png"],
            "sichtbar": False,
        },
    ]
}


@pytest.fixture
def demo_instanz(tmp_path):
    p = tmp_path / "panels.json"
    p.write_text(json.dumps(DEMO_PANELS), encoding="utf-8")
    return str(p)


# AUTH-7b (#1400): der PUT-Endpoint ist hart cookie-gated. Die Schreib-Tests
# fahren mit gültigem Session-Cookie (gekoppeltes Gerät); die Auth-Tests unten
# prüfen 401 ohne Cookie separat.
_BOT_TOKEN = "123456:ABCdef_paneltesttoken"


@pytest.fixture
def write_client(demo_instanz):
    """Schreib-Modus: registry_path gesetzt, mit gültigem AUTH-7b-Cookie."""
    from tools.initdata import session_cookie as _sc
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, registry_path=demo_instanz, bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    client = panel_main.app.test_client()
    client.set_cookie(_sc.COOKIE_NAME, _sc.sign_session("op", _BOT_TOKEN))
    return client, demo_instanz


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
#  AC1 — Happy-Path: gültige tiles-Liste schreiben + 200
# ============================================================

def test_pbe4_valid_put_writes_atomically(write_client):
    """PUT mit gültiger tiles-Liste → 200; neuer Inhalt liegt in panels.json."""
    client, path = write_client

    hash_vorher = _sha256(path)
    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=GUELTIGE_TILES,
                   content_type="application/json")
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body.get("ok") is True
    assert body.get("panel_id") == "kueche-01"

    # Datei wurde geschrieben (Hash hat sich geändert).
    hash_nachher = _sha256(path)
    assert hash_vorher != hash_nachher, "panels.json unverändert — Schreiben ist nicht erfolgt"

    # Neuer tiles-Inhalt steht in panels.json.
    daten = _read_json(path)
    panel = next(p for p in daten["panels"] if p["panel_id"] == "kueche-01")
    keys = {t["key"] for t in panel["tiles"]["tiles"]}
    assert keys == {"wetter", "plan"}


def test_pbe4_get_after_put_reflects_new_tiles(write_client):
    """Nach erfolgreichem PUT liefert GET /tiles.json den neuen Stand (DCOMP-2)."""
    client, _ = write_client
    r_put = client.put("/api/v1/panels/kueche-01/tiles",
                       json=GUELTIGE_TILES,
                       content_type="application/json")
    assert r_put.status_code == 200

    r_get = client.get("/api/v1/panels/kueche-01/tiles.json")
    assert r_get.status_code == 200
    tiles = r_get.get_json()["tiles"]
    keys = {t["key"] for t in tiles}
    assert keys == {"wetter", "plan"}


# ============================================================
#  AC2 — PBE-11: ungültige Liste → 422 + Datei byte-unverändert
# ============================================================

def test_pbe4_invalid_list_returns_422_unchanged(write_client):
    """Ungültige tiles-Liste (fehlendes Pflichtfeld) → 422; panels.json byte-gleich."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    ungueltig = {
        "tiles": [
            # 'sichtbar' fehlt, 'icons' fehlt
            {"key": "x", "app": "plan", "view": "woche", "label": "X"}
        ]
    }
    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=ungueltig,
                   content_type="application/json")
    assert r.status_code == 422
    assert "error" in r.get_json()

    # Datei byte-unverändert (PBE-4: Validierung vor Schreiben).
    assert _read_bytes(path) == inhalt_vorher, (
        "panels.json wurde trotz Validierungsfehler geschrieben (PBE-11 verletzt)")


def test_pbe4_invalid_body_not_object_returns_422(write_client):
    """Body der kein tiles-Objekt ist → 422."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=["statt", "objekt"],
                   content_type="application/json")
    assert r.status_code == 422
    assert _read_bytes(path) == inhalt_vorher


def test_pbe4_missing_tiles_field_returns_422(write_client):
    """Objekt ohne 'tiles'-Feld → 422."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json={"kein_tiles": []},
                   content_type="application/json")
    assert r.status_code == 422
    assert _read_bytes(path) == inhalt_vorher


# ============================================================
#  AC3 — 404 bei unbekannter panel_id
# ============================================================

def test_pbe4_unknown_panel_id_returns_404(write_client):
    """Unbekannte panel_id → 404 mit JSON-Fehler; panels.json unverändert."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    r = client.put("/api/v1/panels/gibtsnicht-99/tiles",
                   json=GUELTIGE_TILES,
                   content_type="application/json")
    assert r.status_code == 404
    assert "error" in r.get_json()
    assert _read_bytes(path) == inhalt_vorher


# ============================================================
#  AC4 — PREG-5: config-Feld unberührt
# ============================================================

def test_pbe4_config_field_not_touched(write_client):
    """PUT /tiles verändert das config-Feld der Instanz nicht (PREG-5)."""
    client, path = write_client

    # config vor dem PUT festhalten.
    reg_vorher = registry_mod.load(path)
    config_vorher = json.dumps(reg_vorher.get("kueche-01").config, sort_keys=True)

    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=GUELTIGE_TILES,
                   content_type="application/json")
    assert r.status_code == 200

    # config nach dem PUT lesen und vergleichen.
    reg_nachher = registry_mod.load(path)
    config_nachher = json.dumps(reg_nachher.get("kueche-01").config, sort_keys=True)
    assert config_vorher == config_nachher, (
        "config wurde durch PUT /tiles verändert (PREG-5 verletzt)")


# ============================================================
#  AC6 — Validierungs-Detailproben (PBE-11)
# ============================================================

def test_pbe4_empty_tiles_list_is_valid(write_client):
    """Leere tiles-Liste ist gültig — Eltern dürfen alle Kacheln entfernen (PBE-9)."""
    client, _ = write_client
    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json={"tiles": []},
                   content_type="application/json")
    assert r.status_code == 200


def test_pbe4_key_collision_returns_422(write_client):
    """Doppelter key in der Liste → 422 (PANEL-3: key eindeutig)."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    doppelter_key = {
        "tiles": [
            {"key": "x", "app": "plan", "view": "woche",
             "label": "A", "icons": ["a.png"], "sichtbar": True},
            {"key": "x", "app": "wetter", "view": "now",
             "label": "B", "icons": ["b.png"], "sichtbar": True},
        ]
    }
    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=doppelter_key, content_type="application/json")
    assert r.status_code == 422
    assert "error" in r.get_json()
    assert _read_bytes(path) == inhalt_vorher


def test_pbe4_icons_empty_returns_422(write_client):
    """Leere icons[] → 422 (PANEL-3: ≥1 Icon)."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json={"tiles": [{"key": "x", "app": "plan", "view": "woche",
                                    "label": "X", "icons": [],
                                    "sichtbar": True}]},
                   content_type="application/json")
    assert r.status_code == 422
    assert _read_bytes(path) == inhalt_vorher


def test_pbe4_icons_too_many_returns_422(write_client):
    """icons[] mit 4 Einträgen → 422 (PANEL-3: max 3)."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json={"tiles": [{"key": "x", "app": "plan", "view": "woche",
                                    "label": "X",
                                    "icons": ["a.png", "b.png", "c.png", "d.png"],
                                    "sichtbar": True}]},
                   content_type="application/json")
    assert r.status_code == 422
    assert _read_bytes(path) == inhalt_vorher


def test_pbe4_sichtbar_not_bool_returns_422(write_client):
    """sichtbar als String statt boolean → 422 (PANEL-4)."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json={"tiles": [{"key": "x", "app": "plan", "view": "woche",
                                    "label": "X", "icons": ["a.png"],
                                    "sichtbar": "true"}]},
                   content_type="application/json")
    assert r.status_code == 422
    assert _read_bytes(path) == inhalt_vorher


def test_pbe4_nested_query_returns_422(write_client):
    """Verschachteltes query-Objekt → 422 (PANEL-7)."""
    client, path = write_client
    inhalt_vorher = _read_bytes(path)

    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json={"tiles": [{"key": "x", "app": "plan", "view": "woche",
                                    "label": "X", "icons": ["a.png"],
                                    "sichtbar": True,
                                    "query": {"tief": {"noch": "tiefer"}}}]},
                   content_type="application/json")
    assert r.status_code == 422
    assert _read_bytes(path) == inhalt_vorher


def test_pbe4_flat_query_is_valid(write_client):
    """Flaches query-Objekt (Strings/Zahlen) ist gültig (PANEL-7)."""
    client, _ = write_client
    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json={"tiles": [{"key": "x", "app": "plan", "view": "woche",
                                    "label": "X", "icons": ["a.png"],
                                    "sichtbar": True,
                                    "query": {"ansicht": "klein", "alter": 4}}]},
                   content_type="application/json")
    assert r.status_code == 200


def test_pbe4_no_registry_path_returns_503(demo_instanz):
    """Test-Modus ohne registry_path → 503 (kein Schreiben möglich). Mit gültigem
    AUTH-7b-Cookie, damit das Gate (401) passiert und der 503-Pfad geprüft wird."""
    from tools.initdata import session_cookie as _sc
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, bot_token=_BOT_TOKEN)   # kein registry_path
    panel_main.app.testing = True
    client = panel_main.app.test_client()
    client.set_cookie(_sc.COOKIE_NAME, _sc.sign_session("op", _BOT_TOKEN))
    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=GUELTIGE_TILES, content_type="application/json")
    assert r.status_code == 503


def test_pbe4_other_panels_preserved(write_client):
    """PUT für kueche-01 lässt flur-01 unverändert — kein Write-Verlust."""
    client, path = write_client

    # tiles von flur-01 vor dem PUT festhalten.
    reg_vorher = registry_mod.load(path)
    flur_tiles_vorher = json.dumps(reg_vorher.get("flur-01").tiles, sort_keys=True)

    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=GUELTIGE_TILES, content_type="application/json")
    assert r.status_code == 200

    reg_nachher = registry_mod.load(path)
    flur_tiles_nachher = json.dumps(reg_nachher.get("flur-01").tiles, sort_keys=True)
    assert flur_tiles_vorher == flur_tiles_nachher, (
        "tiles von flur-01 wurden durch PUT auf kueche-01 verändert")


# ============================================================
#  AC5-Ersatz — PBE-4: Last-Write-Wins (zwei sequentielle PUTs)
# ============================================================

ZWEITE_TILES = {
    "tiles": [
        {
            "key": "kalender",
            "app": "kalender",
            "view": "monat",
            "label": "Kalender",
            "icons": ["arasaac/9999.png"],
            "sichtbar": True,
        }
    ]
}


def test_pbe4_last_write_wins_zwei_sequentielle_puts(write_client):
    """PBE-4 Last-Write-Wins: zwei sequentielle PUTs auf dieselbe panel_id mit
    verschiedenen tiles-Listen — der zweite gewinnt vollständig, kein Misch-Stand.
    Atomarität bleibt (Hash nach zweitem PUT == Hash der zweiten gespeicherten Liste).
    """
    client, path = write_client

    # Erster PUT mit GUELTIGE_TILES (wetter + plan).
    r1 = client.put("/api/v1/panels/kueche-01/tiles",
                    json=GUELTIGE_TILES,
                    content_type="application/json")
    assert r1.status_code == 200, r1.get_data(as_text=True)

    hash_nach_erstem = _sha256(path)

    # Zweiter PUT mit ZWEITE_TILES (kalender).
    r2 = client.put("/api/v1/panels/kueche-01/tiles",
                    json=ZWEITE_TILES,
                    content_type="application/json")
    assert r2.status_code == 200, r2.get_data(as_text=True)

    hash_nach_zweitem = _sha256(path)
    assert hash_nach_erstem != hash_nach_zweitem, (
        "panels.json nach zweitem PUT unverändert — zweiter PUT hat nicht geschrieben")

    # panels.json enthält genau die Liste des zweiten PUTs — kein Misch-Stand.
    daten = _read_json(path)
    panel = next(p for p in daten["panels"] if p["panel_id"] == "kueche-01")
    keys = {t["key"] for t in panel["tiles"]["tiles"]}
    assert keys == {"kalender"}, (
        "Misch-Stand nach zweitem PUT: erwartet {kalender}, gefunden %r" % keys)

    # Erster-PUT-Kacheln dürfen nicht mehr vorhanden sein.
    assert "wetter" not in keys, "wetter aus erstem PUT noch im Ergebnis (Misch-Stand)"
    assert "plan" not in keys, "plan aus erstem PUT noch im Ergebnis (Misch-Stand)"


# ============================================================
#  AUTH-7b (#1400 / #1389) — PBE-4 WRITE hart cookie-gated
# ============================================================
def test_pbe4_ohne_cookie_ist_401(demo_instanz):
    """AUTH-7b / AUTH-3.a (#1400): PUT ohne gültigen Session-Cookie → 401.
    WRITE ist hart ab Tag 0, keine Observe-Grace."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, registry_path=demo_instanz, bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    client = panel_main.app.test_client()  # KEIN Cookie
    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=GUELTIGE_TILES, content_type="application/json")
    assert r.status_code == 401


def test_pbe4_mit_gueltigem_cookie_ist_200(write_client):
    """AUTH-7b (#1400): PUT mit gültigem Session-Cookie (gekoppeltes Gerät)
    passiert das Gate → 200. Der write_client-Fixture trägt den Cookie."""
    client, _ = write_client
    r = client.put("/api/v1/panels/kueche-01/tiles",
                   json=GUELTIGE_TILES, content_type="application/json")
    assert r.status_code == 200
