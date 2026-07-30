"""Tests für routine/main.py — Store-Pfad-Override via ENV (SVC-5 / CONFIG-5 / AC3)
und HTTP-Smoke-Tests für die morgen-Route (ROUTINE-28 Welle A, T726).

Lauf: pytest routine/tests/ -v
"""

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import main as main_mod      # noqa: E402  # isort:skip
from routine.tests._test_auth import TEST_BOT_TOKEN, patch_client_auth  # noqa: E402  # isort:skip


# ============================================================
#  _store_path — Auflösungs-Reihenfolge (AC3)
# ============================================================

def test_AC3_store_path_default_without_env(monkeypatch):
    """Ohne ENV und ohne runtime["store_path"] → DEFAULT_STORE_FILE."""
    monkeypatch.delenv(config_mod.ENV_STORE_FILE, raising=False)
    main_mod.runtime["store_path"] = None
    assert main_mod._store_path() == config_mod.DEFAULT_STORE_FILE


def test_AC3_store_path_env_override(monkeypatch, tmp_path):
    """ROUTINE_STORE_FILE in ENV → überschreibt Default (SVC-5 / CONFIG-5)."""
    override = str(tmp_path / "env_store.json")
    monkeypatch.setenv(config_mod.ENV_STORE_FILE, override)
    main_mod.runtime["store_path"] = None
    assert main_mod._store_path() == override


def test_AC3_store_path_runtime_beats_env(monkeypatch, tmp_path):
    """runtime['store_path'] (Test-Naht) schlägt ENV — höchste Priorität."""
    runtime_val = str(tmp_path / "runtime_store.json")
    env_val = str(tmp_path / "env_store.json")
    monkeypatch.setenv(config_mod.ENV_STORE_FILE, env_val)
    main_mod.runtime["store_path"] = runtime_val
    try:
        assert main_mod._store_path() == runtime_val
    finally:
        main_mod.runtime["store_path"] = None


def test_AC3_store_reads_from_env_path(monkeypatch, tmp_path, demo_config):
    """Abhak-Zustand wird aus dem ENV-Override-Pfad gelesen und geschrieben."""
    store_file = tmp_path / "custom_store.json"
    # Store mit bekanntem Zustand vorbelegen
    store_file.write_text(json.dumps({"2099-01-01": ["fruehstueck"]}))

    monkeypatch.setenv(config_mod.ENV_STORE_FILE, str(store_file))
    main_mod.runtime["store_path"] = None
    main_mod.configure(demo_config)  # data_path=None, store_path=None → ENV greift

    loaded = main_mod._load_store()
    assert "2099-01-01" in loaded


# ============================================================
#  V2 AC5 — PUT /config: Deprecation-Hinweis (ROUTINE-25)
# ============================================================

def test_healthz_gibt_200(client):
    """SVC-1: GET /healthz liefert immer 200 + ok."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_v2_ac5_put_config_setzt_deprecation_header(client, tmp_path, demo_config):
    """V2 AC5: PUT /api/v1/routine/config bleibt funktionsfähig (200),
    setzt aber X-Deprecation-Header und deprecated:true im JSON-Body
    (ROUTINE-25)."""
    import json
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45", "aufstehzeit": "07:00",
        "anzieh_vorlauf_min": 8, "zeitzone": "Europe/Berlin",
        "items": [], "zeit_referenzen": {"an": False, "paare": []},
    }))
    main_mod.configure(demo_config, data_path=str(data_file))

    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "08:00"},
                      content_type="application/json")
    assert resp.status_code == 200
    # Header gesetzt
    assert resp.headers.get("X-Deprecation"), \
        "PUT /config muss X-Deprecation-Header setzen (ROUTINE-25)"
    assert "routine/items" in resp.headers.get("X-Deprecation", ""), \
        "X-Deprecation muss auf V2-Pfad /items hinweisen"
    # JSON deprecated:true
    body = json.loads(resp.data)
    assert body.get("ok") is True
    assert body.get("deprecated") is True, \
        "PUT /config muss JSON deprecated:true tragen (ROUTINE-25)"


# ============================================================
#  T726 AC7 — HTTP-Smoke: GET /display/routine/morgen mit V1-Config
# ============================================================

_V1_ROUTINE = {
    "aufstehzeit": "07:00",
    "abfahrtszeit": "07:45",
    "anzieh_vorlauf_min": 5,
    "zeitzone": "Europe/Berlin",
    "items": [
        {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626", "quelle": "default"},
    ],
    "zeit_referenzen": {"an": False, "paare": []},
}


@pytest.fixture
def v1_client(tmp_path):
    """Flask-Test-Client mit reiner V1-Konfig (keine locked-Anker in items[]).

    Kein data_path gesetzt → _current_config() liefert in-memory-Snapshot.
    Damit prüft der Test: morgen-Route ruft migriere_v1_anker() auf und
    der HTML-Output enthält die synthetisierten Anker-Labels und -Uhrzeiten.
    """
    data_file = tmp_path / "routine_v1.json"
    data_file.write_text(json.dumps(_V1_ROUTINE))
    cfg = config_mod.resolve_data(str(data_file))
    store_file = str(tmp_path / "store_v1.json")
    main_mod.configure(cfg, store_path=store_file, bot_token=TEST_BOT_TOKEN)
    return patch_client_auth(main_mod.app.test_client())


def test_ac7_http_smoke_morgen_v1_migration(v1_client):
    """AC7: GET /display/routine/morgen mit V1-routine.json liefert HTML mit
    synthetisierten Ankern (Aufstehen/Losgehen) und deren Uhrzeiten (ROUTINE-28 Welle A).

    Regression-Schutz: jemand, der migriere_v1_anker() aus der morgen-Route entfernt,
    bricht diesen Test — isolierte Unit-Tests in test_migration_v2.py/test_render.py
    bleiben dabei grün (HTTP-Pfad blieb blind, T726 Watchdog-Befund B1).
    """
    resp = v1_client.get("/display/routine/morgen")
    assert resp.status_code == 200, f"morgen-Route antwortete {resp.status_code}"
    html = resp.data.decode("utf-8")

    # Synth-Anker-Labels müssen im HTML auftauchen (als card-item-label und/oder zeit-pin-label)
    assert "Aufstehen" in html, \
        "HTML muss Synth-Anker-Label 'Aufstehen' enthalten (migriere_v1_anker() muss greifen)"
    assert "Losgehen" in html, \
        "HTML muss Synth-Anker-Label 'Losgehen' enthalten (migriere_v1_anker() muss greifen)"

    # Anker-Uhrzeiten aus V1-Feldern (aufstehzeit=07:00, abfahrtszeit=07:45)
    assert "07:00" in html, \
        "HTML muss aufstehzeit '07:00' enthalten (Synth-Anker aus V1-Feld)"
    assert "07:45" in html, \
        "HTML muss abfahrtszeit '07:45' enthalten (Synth-Anker aus V1-Feld)"

    # T1070 (Nic-Setzung 2026-06-22): Anziehen-Vorlauf mit bezug=naechster_anker.
    # V1-routine.json hat anzieh_vorlauf_min=5 → Anziehen-Pin zeigt 07:45 - 5 = 07:40
    # (ROUTINE-9 V1-Sema: `abfahrtszeit − anzieh_vorlauf_min`).
    # Watchdog-B3: AC7-HTTP-Smoke deckt jetzt auch Anziehen-Pfad ab.
    assert "Anziehen" in html, \
        "HTML muss Synth-Anziehen-Label enthalten (Welle-B Anziehen-Vorlauf-Item)"
    assert "07:40" in html, \
        "HTML muss Anziehen-Vorlauf-Uhrzeit '07:40' (abfahrtszeit 07:45 − vorlauf 5) " \
        "enthalten (bezug=naechster_anker, Nic-Setzung 2026-06-22 #1070)"
