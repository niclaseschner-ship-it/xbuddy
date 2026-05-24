"""Tests für den Onboarding-Speicher — ONB-5 (Refs #33, #100)."""

import os
import stat

from onboarding_store import OnboardingStore


def test_ONB_5_missing_file_loads_empty(tmp_path):
    assert OnboardingStore(str(tmp_path / "none.json")).load() == {}


def test_ONB_5_save_and_load_roundtrip(tmp_path):
    store = OnboardingStore(str(tmp_path / "s.json"))
    store.save(provider_api_key="sk-x", family_group_chat_id="-100")
    loaded = store.load()
    assert loaded["provider_api_key"] == "sk-x"
    assert loaded["family_group_chat_id"] == "-100"


def test_ONB_5_save_merges_with_existing(tmp_path):
    store = OnboardingStore(str(tmp_path / "s.json"))
    store.save(provider_api_key="sk-x")
    store.save(family_group_chat_id="-100")   # der Key bleibt erhalten
    loaded = store.load()
    assert loaded["provider_api_key"] == "sk-x"
    assert loaded["family_group_chat_id"] == "-100"


def test_ONB_5_persists_across_instances(tmp_path):
    """Eine eingerichtete Instanz übersteht einen Neustart."""
    path = str(tmp_path / "s.json")
    OnboardingStore(path).save(provider_api_key="sk-x")
    assert OnboardingStore(path).load()["provider_api_key"] == "sk-x"


def test_ONB_5_file_is_owner_only(tmp_path):
    """Der Speicher enthält ein Geheimnis — Dateirechte 0600."""
    path = str(tmp_path / "s.json")
    OnboardingStore(path).save(provider_api_key="sk-x")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_ONB_5_corrupt_file_loads_empty(tmp_path):
    bad = tmp_path / "s.json"
    bad.write_text("{kein valides json")
    assert OnboardingStore(str(bad)).load() == {}


def test_ONB_5_file_is_created_with_owner_only_even_under_permissive_umask(tmp_path, monkeypatch):
    """ONB-5/#100: Die Datei wird *race-frei* mit 0600 angelegt.

    Setzt umask auf 0o000 (alle Rechte erlaubt) und entschärft `os.chmod` zu
    einer No-Op — damit bleibt nur sichtbar, mit welchen Rechten die Datei
    *angelegt* wurde, nicht was nachträglich draufkorrigiert wurde. Race-freier
    Code (`os.open` mit explizitem Modus) erzwingt 0o600 schon bei Anlage und
    besteht den Test; ein nicht-race-freier Code (`open(..., "w")` mit nach-
    träglichem `os.chmod`) würde die Datei mit 0o666 sichtbar lassen und
    durchfallen.
    """
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(os, "chmod", lambda *args, **kwargs: None)
    old_umask = os.umask(0o000)
    try:
        OnboardingStore(path).save(provider_api_key="sk-x")
        # Ohne os.chmod-Korrektur muss die Datei bereits mit 0o600 angelegt sein.
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    finally:
        os.umask(old_umask)
