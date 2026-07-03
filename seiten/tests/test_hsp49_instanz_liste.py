"""Tests fuer HSP-49 — Instanz-Liste im Hörspiel-Player-Template-Kontext.

AC-A2: hoerspiel_player_view rendert player.html mit einer iterierbaren
Instanz-Liste (paula, neko) als window.__HSP_INSTANZEN__ (kind_id+name,
foto_url best-effort/null); niclas nicht enthalten; Liste an EINER
autoritativen Stelle (_HSP_INSTANZEN in seiten/main.py).

Anker: specs/buddies/hoerspiel.md HSP-49/HSP-43, conventions/ports.md PORT-2

Lauf: python3 -m pytest seiten/tests/test_hsp49_instanz_liste.py -x -v
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
    """App konfigurieren + runtime nach dem Test saeubern (Naht-Schluessel)."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken-hsp49",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    yield
    # Naht-Schlussel entfernen, damit nachfolgende Tests nicht beeinflusst werden.
    seiten_main.runtime.pop("hoerspiel_player_template_dir", None)
    seiten_main.runtime.pop("hoerspiel_player_asset_dir", None)


@pytest.fixture
def client(tmp_path):
    """Flask-Test-Client mit monkeygepatechtem Template-Verzeichnis.

    Legt eine minimale player.html an, die window.__HSP_INSTANZEN__ ausgibt,
    und registriert sie ueber die Test-Naht runtime['hoerspiel_player_template_dir'].
    Track B liefert die echte player.html; hier genuegt ein Minimal-Stub.
    """
    player_html = tmp_path / "player.html"
    player_html.write_text(
        "<script>window.__HSP_INSTANZEN__ = {{ instanzen_json }};</script>",
        encoding="utf-8",
    )
    seiten_main.runtime["hoerspiel_player_template_dir"] = str(tmp_path)
    # Asset-Dir ebenfalls auf tmp_path zeigen, damit build_id-Lookup nicht failt.
    seiten_main.runtime["hoerspiel_player_asset_dir"] = str(tmp_path)
    return seiten_main.app.test_client()


# ── AC-A2: Instanz-Liste im gerendertem HTML ──────────────────────────────────

def test_instanz_liste_traegt_paula_und_neko(client):
    """AC-A2: GET /seiten/hoerspiel/player — gerendertes HTML enthaelt
    window.__HSP_INSTANZEN__ mit genau paula+neko (kind_id), kein niclas."""
    resp = client.get("/seiten/hoerspiel/player")
    assert resp.status_code == 200, f"Unerwarteter Status: {resp.status_code}"
    body = resp.get_data(as_text=True)
    assert "window.__HSP_INSTANZEN__" in body, \
        "__HSP_INSTANZEN__ fehlt im gerendertem HTML"

    # JSON aus dem gerendertem Markup extrahieren und parsen.
    # Template: window.__HSP_INSTANZEN__ = <blob>;
    start = body.index("window.__HSP_INSTANZEN__ =") + len("window.__HSP_INSTANZEN__ =")
    end = body.index(";", start)
    blob = body[start:end].strip()
    instanzen = json.loads(blob)

    kind_ids = [e["kind_id"] for e in instanzen]
    assert "paula" in kind_ids, f"paula fehlt in Instanz-Liste: {kind_ids}"
    assert "neko"  in kind_ids, f"neko fehlt in Instanz-Liste: {kind_ids}"
    assert "niclas" not in kind_ids, \
        f"niclas darf nicht in Instanz-Liste sein (#1263 deferred): {kind_ids}"


def test_instanz_liste_enthaelt_name_und_foto_url(client):
    """AC-A2: Jede Instanz hat die Pflicht-Felder kind_id, name, foto_url.
    foto_url ist null (kein familie-Foto-Zugang, stop_rule kein_familie_client)."""
    resp = client.get("/seiten/hoerspiel/player")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    start = body.index("window.__HSP_INSTANZEN__ =") + len("window.__HSP_INSTANZEN__ =")
    end = body.index(";", start)
    instanzen = json.loads(body[start:end].strip())

    for entry in instanzen:
        assert "kind_id"   in entry, f"Feld kind_id fehlt: {entry}"
        assert "name"      in entry, f"Feld name fehlt: {entry}"
        assert "foto_url"  in entry, f"Feld foto_url fehlt: {entry}"
        assert entry["name"], f"name darf nicht leer sein: {entry}"

    # foto_url null: kein neuer familie-Client gebaut (stop_rule kein_familie_client).
    for entry in instanzen:
        assert entry["foto_url"] is None, \
            f"foto_url muss None sein (FAM-8 deferred): {entry}"


def test_instanz_liste_genau_zwei_eintraege(client):
    """AC-A2: V1 provisioniert exakt zwei Instanzen (paula + neko, PORT-2)."""
    resp = client.get("/seiten/hoerspiel/player")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    start = body.index("window.__HSP_INSTANZEN__ =") + len("window.__HSP_INSTANZEN__ =")
    end = body.index(";", start)
    instanzen = json.loads(body[start:end].strip())
    assert len(instanzen) == 2, \
        f"Erwartet 2 Instanzen (paula+neko), erhalten {len(instanzen)}: {instanzen}"


# ── Konstanten-Probe (eine autoritative Stelle) ───────────────────────────────

def test_hsp_instanzen_konstante_ist_autoritative_liste():
    """HSP-43: _HSP_INSTANZEN in seiten/main.py ist die eine autoritative Stelle.
    Alle kind_id-Werte muessen Strings sein, keine leeren Namen."""
    instanzen = seiten_main._HSP_INSTANZEN
    assert isinstance(instanzen, list)
    assert len(instanzen) >= 1
    kind_ids = {e["kind_id"] for e in instanzen}
    assert "paula" in kind_ids
    assert "neko"  in kind_ids
    assert "niclas" not in kind_ids
    for entry in instanzen:
        assert isinstance(entry["kind_id"], str)
        assert entry["kind_id"]
        assert isinstance(entry["name"], str)
        assert entry["name"]
