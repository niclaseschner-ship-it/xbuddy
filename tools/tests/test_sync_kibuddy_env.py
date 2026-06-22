"""Tests für `tools/sync_kibuddy_env.py` — LLM-Slot-Spiegel (T1082-S2 Fix 2).

Belegt, dass nach `_sync_llm_slots(...)` der LLMP-5-Slot
`kibuddy-anthropic-api-key` mit demselben Wert wie der Bestand
`kibuddy-llm-provider-api-key` in der zugangsdaten.json liegt. Der
Bestand bleibt erhalten — beide Slots leben parallel (additiv-
rückrollbar, LLMP-S8).
"""

import json

import pytest

from tools.sync_kibuddy_env import _sync_llm_slots


def _read_zd(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def zd_file(tmp_path):
    """ZD-Datei mit Bestand-Key und ohne neuen Slot."""
    zd = tmp_path / "zugangsdaten.json"
    zd.write_text(json.dumps({
        "kibuddy-llm-provider-api-key": "sk-bestand-123",
        "kibuddy-azure-openai-endpoint": "https://x.openai.azure.com/",
    }), encoding="utf-8")
    return zd


def test_sync_creates_llm_slot_mirror_from_bestand(zd_file):
    """Fix-2/AC3: neuer Slot `kibuddy-anthropic-api-key` entsteht parallel
    zum Bestand `kibuddy-llm-provider-api-key` mit identischem Wert."""
    written = _sync_llm_slots(str(zd_file))
    assert written == [("kibuddy-anthropic-api-key", "kibuddy-llm-provider-api-key")]

    data = _read_zd(zd_file)
    # Beide Slots existieren, gleicher Wert (parallele Migration).
    assert data["kibuddy-anthropic-api-key"] == "sk-bestand-123"
    assert data["kibuddy-llm-provider-api-key"] == "sk-bestand-123"
    # Andere Keys bleiben unangetastet.
    assert data["kibuddy-azure-openai-endpoint"] == "https://x.openai.azure.com/"


def test_sync_idempotent_second_run_writes_nothing(zd_file):
    """Zweiter Aufruf darf keine Doppel-Schreibung verursachen."""
    _sync_llm_slots(str(zd_file))
    written = _sync_llm_slots(str(zd_file))
    assert written == []


def test_sync_falls_back_to_hoerspiel_when_kibuddy_missing(tmp_path):
    """Wenn der kibuddy-Bestand fehlt, greift der hoerspiel-Fallback (wie KEY_FALLBACKS)."""
    zd = tmp_path / "zugangsdaten.json"
    zd.write_text(json.dumps({
        "hoerspiel-llm-provider-api-key": "sk-hoer-456",
    }), encoding="utf-8")

    written = _sync_llm_slots(str(zd))
    assert written == [("kibuddy-anthropic-api-key", "hoerspiel-llm-provider-api-key")]

    data = _read_zd(zd)
    assert data["kibuddy-anthropic-api-key"] == "sk-hoer-456"


def test_sync_does_nothing_when_no_source_present(tmp_path):
    """Ohne Quell-Slot wird nichts geschrieben (kein Crash, kein leerer Slot)."""
    zd = tmp_path / "zugangsdaten.json"
    zd.write_text(json.dumps({"irgendwas-anderes": "x"}), encoding="utf-8")

    written = _sync_llm_slots(str(zd))
    assert written == []

    data = _read_zd(zd)
    assert "kibuddy-anthropic-api-key" not in data


def test_sync_updates_when_source_changes(tmp_path):
    """Wenn sich der Quell-Wert ändert, wird der Spiegel-Slot mitgezogen."""
    zd = tmp_path / "zugangsdaten.json"
    zd.write_text(json.dumps({
        "kibuddy-llm-provider-api-key": "sk-alt",
        "kibuddy-anthropic-api-key": "sk-alt",
    }), encoding="utf-8")
    # Quelle ändert sich extern.
    data = _read_zd(zd)
    data["kibuddy-llm-provider-api-key"] = "sk-neu"
    zd.write_text(json.dumps(data), encoding="utf-8")

    written = _sync_llm_slots(str(zd))
    assert written == [("kibuddy-anthropic-api-key", "kibuddy-llm-provider-api-key")]

    data_after = _read_zd(zd)
    assert data_after["kibuddy-anthropic-api-key"] == "sk-neu"
