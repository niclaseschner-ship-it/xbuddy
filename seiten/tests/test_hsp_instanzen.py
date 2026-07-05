"""HSP-43 / #1263 — Instanz-Liste im Hörspiel-Player-Template-Kontext (emil).

Löst `test_hsp49_instanz_liste.py` ab: seit #1263 ist emil als dritte Instanz
provisioniert (Backend-Deploy manuell, HSP-44). `_HSP_INSTANZEN` in seiten/main.py
ist die EINE autoritative seiten-lokale Kopie (kind_id+name, foto_url best-effort/
null); die Liste iteriert im Player-Template als window.__HSP_INSTANZEN__.

Anker: specs/buddies/hoerspiel.md HSP-43/HSP-49, conventions/ports.md PORT-2
(mia 5053, finn 5055, emil 5056).

Lauf: python3 -m pytest seiten/tests/test_hsp_instanzen.py -x -v
"""

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402


@pytest.fixture(autouse=True)
def reset_runtime():
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken-hsp43",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    yield
    seiten_main.runtime.pop("hoerspiel_player_template_dir", None)
    seiten_main.runtime.pop("hoerspiel_player_asset_dir", None)


@pytest.fixture
def client(tmp_path):
    player_html = tmp_path / "player.html"
    player_html.write_text(
        "<script>window.__HSP_INSTANZEN__ = {{ instanzen_json }};</script>",
        encoding="utf-8",
    )
    seiten_main.runtime["hoerspiel_player_template_dir"] = str(tmp_path)
    seiten_main.runtime["hoerspiel_player_asset_dir"] = str(tmp_path)
    return seiten_main.app.test_client()


def _lese_instanzen(client):
    resp = client.get("/seiten/hoerspiel/player")
    assert resp.status_code == 200, f"Unerwarteter Status: {resp.status_code}"
    body = resp.get_data(as_text=True)
    assert "window.__HSP_INSTANZEN__" in body
    start = body.index("window.__HSP_INSTANZEN__ =") + len("window.__HSP_INSTANZEN__ =")
    end = body.index(";", start)
    return json.loads(body[start:end].strip())


def test_instanz_liste_traegt_mia_finn_und_emil(client):
    """HSP-43 / #1263: window.__HSP_INSTANZEN__ enthält mia, finn UND emil."""
    kind_ids = {e["kind_id"] for e in _lese_instanzen(client)}
    assert "mia" in kind_ids
    assert "finn" in kind_ids
    assert "emil" in kind_ids, \
        f"emil muss ab #1263 in der Instanz-Liste sein: {kind_ids}"


def test_instanz_liste_genau_drei_eintraege(client):
    """#1263: provisioniert drei Instanzen (mia + finn + emil, PORT-2)."""
    instanzen = _lese_instanzen(client)
    assert len(instanzen) == 3, \
        f"Erwartet 3 Instanzen (mia+finn+emil), erhalten {len(instanzen)}: {instanzen}"


def test_instanz_liste_enthaelt_name_und_foto_url(client):
    """Jeder Eintrag trägt kind_id + name (nicht leer) + foto_url None (FAM-8)."""
    for entry in _lese_instanzen(client):
        assert "kind_id" in entry
        assert entry.get("name")
        assert "foto_url" in entry
        assert entry["foto_url"] is None


def test_hsp_instanzen_konstante_ist_autoritative_liste():
    """HSP-43: _HSP_INSTANZEN in seiten/main.py ist die eine autoritative Stelle
    und trägt mia, finn und emil (kind_id/name Strings, nicht leer)."""
    instanzen = seiten_main._HSP_INSTANZEN
    assert isinstance(instanzen, list)
    kind_ids = {e["kind_id"] for e in instanzen}
    assert {"mia", "finn", "emil"} <= kind_ids
    for entry in instanzen:
        assert isinstance(entry["kind_id"], str)
        assert entry["kind_id"]
        assert isinstance(entry["name"], str)
        assert entry["name"]
        # Scope-Grenze HSP-43: NUR kind_id/name/foto_url — nie port/origin/service.
        assert "port" not in entry
        assert "origin" not in entry
