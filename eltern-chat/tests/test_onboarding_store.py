"""Tests für den Onboarding-Speicher — ONB-5 (Refs #33, #100, #84, #336).

Der Onboarding-Speicher liest und schreibt seit #84/#336 ausschließlich über den
zentralen Zugangsdaten-Speicher (`tools.zugangsdaten`, ZD-1). Die Tests
injizieren eine isolierte `Zugangsdaten`-Instanz, damit sie den ZD-Inhalt direkt
prüfen können.
"""

import os
import stat

from onboarding_store import (
    ZD_NAME_FAMILY_GROUP,
    ZD_NAME_PROVIDER_API_KEY,
    OnboardingStore,
    zd_name_provider_api_key,
)

from tools.zugangsdaten import Zugangsdaten


def _zd(tmp_path):
    """Frischer, isolierter zentraler Speicher für einen Test."""
    return Zugangsdaten(str(tmp_path / "zd.json"))


# -- ONB-5 / #84 AC1: Schreiben landet nur im zentralen ZD-Speicher ----

def test_ONB_5_save_writes_only_to_zd(tmp_path):
    """save() schreibt beide Werte als benannte ZD-Einträge — keine eigene
    Onboarding-Datei mehr (#336, ZD-only)."""
    zd = _zd(tmp_path)
    OnboardingStore(zd=zd).save(provider_api_key="sk-x", family_group_chat_id="-100")

    assert zd.get(ZD_NAME_PROVIDER_API_KEY) == "sk-x"
    assert zd.get(ZD_NAME_FAMILY_GROUP) == "-100"


def test_ONB_5_save_and_load_roundtrip(tmp_path):
    store = OnboardingStore(zd=_zd(tmp_path))
    store.save(provider_api_key="sk-x", family_group_chat_id="-100")
    loaded = store.load()
    assert loaded["provider_api_key"] == "sk-x"
    assert loaded["family_group_chat_id"] == "-100"


def test_ONB_5_save_merges_with_existing(tmp_path):
    zd = _zd(tmp_path)
    store = OnboardingStore(zd=zd)
    store.save(provider_api_key="sk-x")
    store.save(family_group_chat_id="-100")   # der erste Wert bleibt erhalten
    loaded = store.load()
    assert loaded["provider_api_key"] == "sk-x"
    assert loaded["family_group_chat_id"] == "-100"


def test_ONB_5_file_is_owner_only(tmp_path):
    """Der zentrale Speicher enthält ein Geheimnis — Dateirechte 0600 (ZD-3)."""
    zd_path = str(tmp_path / "zd.json")
    OnboardingStore(zd=Zugangsdaten(zd_path)).save(provider_api_key="sk-x")
    assert stat.S_IMODE(os.stat(zd_path).st_mode) == 0o600


# -- #84 AC1: Lesen direkt aus dem ZD-Speicher (#336, kein Fallback mehr) --

def test_ONB_5_read_from_zd(tmp_path):
    """Liegt ein Wert im ZD-Speicher, kommt er aus load() zurück."""
    zd = _zd(tmp_path)
    zd.set(ZD_NAME_PROVIDER_API_KEY, "sk-zd")
    loaded = OnboardingStore(zd=zd).load()
    assert loaded["provider_api_key"] == "sk-zd"


def test_ONB_5_missing_value_absent_from_result(tmp_path):
    """Fehlt ein Wert im ZD-Speicher, taucht sein Schlüssel im Ergebnis nicht auf."""
    assert OnboardingStore(zd=_zd(tmp_path)).load() == {}


def test_ONB_5_partial_values(tmp_path):
    """Nur ein Wert gesetzt → nur dieser Schlüssel im Ergebnis."""
    zd = _zd(tmp_path)
    zd.set(ZD_NAME_PROVIDER_API_KEY, "sk-only")
    loaded = OnboardingStore(zd=zd).load()
    assert loaded == {"provider_api_key": "sk-only"}


def test_ONB_5_persists_across_instances(tmp_path):
    """Eine eingerichtete Instanz übersteht einen Neustart — der Wert liegt im
    geteilten ZD-Speicher, eine zweite Store-Instanz liest ihn."""
    zd_path = str(tmp_path / "zd.json")
    OnboardingStore(zd=Zugangsdaten(zd_path)).save(provider_api_key="sk-x")
    assert OnboardingStore(
        zd=Zugangsdaten(zd_path)).load()["provider_api_key"] == "sk-x"


# -- T663 Welle A: load(provider_name=...) read-both ---------------------

def test_load_reads_vendor_slot_first(tmp_path):
    """T663 Welle A: load(provider_name='claude') liest vendor-Slot zuerst
    (`eltern-chat-claude-api-key`), nicht den Single-Slot."""
    zd = _zd(tmp_path)
    zd.set(zd_name_provider_api_key("claude"), "sk-ant-vendor-key")
    zd.set(ZD_NAME_PROVIDER_API_KEY, "sk-ant-single-slot-key")   # darf NICHT gewinnen
    loaded = OnboardingStore(zd=zd).load(provider_name="claude")
    assert loaded["provider_api_key"] == "sk-ant-vendor-key", (
        "Welle A: vendor-Slot muss vor Single-Slot kommen")


def test_load_falls_back_to_single_slot(tmp_path):
    """T663 Welle A: vendor-Slot leer/fehlend → Fallback auf Single-Slot
    (Welle B entfernt diesen Pfad später)."""
    zd = _zd(tmp_path)
    # Nur Single-Slot gesetzt — kein vendor-Slot.
    zd.set(ZD_NAME_PROVIDER_API_KEY, "sk-mistral-single-only")
    loaded = OnboardingStore(zd=zd).load(provider_name="mistral")
    assert loaded["provider_api_key"] == "sk-mistral-single-only", (
        "Welle A: Fallback auf Single-Slot wenn vendor-Slot leer")


def test_load_falls_back_when_vendor_slot_empty_string(tmp_path):
    """R8 truthy-Check: leerer String im vendor-Slot zählt als nicht gesetzt
    und triggert Fallback auf Single-Slot."""
    zd = _zd(tmp_path)
    zd.set(zd_name_provider_api_key("claude"), "")   # leer → truthy-False
    zd.set(ZD_NAME_PROVIDER_API_KEY, "sk-single-wins")
    loaded = OnboardingStore(zd=zd).load(provider_name="claude")
    assert loaded["provider_api_key"] == "sk-single-wins", (
        "R8: leerer vendor-Slot muss Fallback auslösen, nicht als Wert gelten")


def test_load_default_no_provider_name_unchanged(tmp_path):
    """Default-Verhalten: load() ohne provider_name liest weiterhin nur den
    Single-Slot (kein Bruch für config.py-Bootstrap)."""
    zd = _zd(tmp_path)
    zd.set(zd_name_provider_api_key("claude"), "sk-ant-vendor-key")   # da, aber ignoriert
    # Kein Single-Slot gesetzt → kein provider-Key im Ergebnis.
    loaded = OnboardingStore(zd=zd).load()
    assert "provider_api_key" not in loaded, (
        "Default-Verhalten: ohne provider_name darf der vendor-Slot NICHT "
        "gelesen werden — sonst Bruch für config.py-Bootstrap")


def test_zd_name_provider_api_key_helper():
    """Helper baut den Slot-Namen aus dem Vendor-Slug (SD1)."""
    assert zd_name_provider_api_key("claude") == "eltern-chat-claude-api-key"
    assert zd_name_provider_api_key("mistral") == "eltern-chat-mistral-api-key"


def test_zd_name_provider_api_key_rejects_empty():
    """Helper wirft auf leeren Vendor-Namen."""
    import pytest
    with pytest.raises(ValueError, match="vendor"):
        zd_name_provider_api_key("")
