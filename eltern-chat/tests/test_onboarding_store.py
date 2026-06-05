"""Tests für den Onboarding-Speicher — ONB-5 (Refs #33, #100) und die
ZD-Migration #84 (OPEN-ZD-B, Schritt 1: read-both/write-ZD, lazy-Migration).

Der Onboarding-Speicher liest und schreibt seit #84 über den zentralen
Zugangsdaten-Speicher (`tools.zugangsdaten`, ZD-1). Die Tests injizieren eine
isolierte `Zugangsdaten`-Instanz, damit sie sowohl den ZD-Inhalt als auch das
Verhalten der einmaligen Migration der Alt-Datei direkt prüfen können.
"""

import json
import os
import stat

from onboarding_store import (
    MIGRATED_SUFFIX,
    ZD_NAME_FAMILY_GROUP,
    ZD_NAME_PROVIDER_API_KEY,
    OnboardingStore,
)

from tools.zugangsdaten import Zugangsdaten


def _zd(tmp_path):
    """Frischer, isolierter zentraler Speicher für einen Test."""
    return Zugangsdaten(str(tmp_path / "zd.json"))


def _write_alt(path, **werte):
    """Legt eine Alt-Onboarding-Datei (Klartext-JSON) mit den Werten an."""
    with open(path, "w") as f:
        json.dump(werte, f)


# -- ONB-5 / #84 AC1: Schreiben landet nur im zentralen ZD-Speicher ----

def test_ONB_5_save_writes_only_to_zd(tmp_path):
    """save() schreibt beide Werte als benannte ZD-Einträge — und legt KEINE
    Alt-Onboarding-Datei mehr an (kein Klartext-Key in onboarding-store.json)."""
    alt = str(tmp_path / "onboarding-store.json")
    zd = _zd(tmp_path)
    OnboardingStore(alt, zd=zd).save(provider_api_key="sk-x", family_group_chat_id="-100")

    assert zd.get(ZD_NAME_PROVIDER_API_KEY) == "sk-x"
    assert zd.get(ZD_NAME_FAMILY_GROUP) == "-100"
    assert not os.path.exists(alt)


def test_ONB_5_save_and_load_roundtrip(tmp_path):
    store = OnboardingStore(str(tmp_path / "s.json"), zd=_zd(tmp_path))
    store.save(provider_api_key="sk-x", family_group_chat_id="-100")
    loaded = store.load()
    assert loaded["provider_api_key"] == "sk-x"
    assert loaded["family_group_chat_id"] == "-100"


def test_ONB_5_save_merges_with_existing(tmp_path):
    zd = _zd(tmp_path)
    store = OnboardingStore(str(tmp_path / "s.json"), zd=zd)
    store.save(provider_api_key="sk-x")
    store.save(family_group_chat_id="-100")   # der erste Wert bleibt erhalten
    loaded = store.load()
    assert loaded["provider_api_key"] == "sk-x"
    assert loaded["family_group_chat_id"] == "-100"


def test_ONB_5_file_is_owner_only(tmp_path):
    """Der zentrale Speicher enthält ein Geheimnis — Dateirechte 0600 (ZD-3)."""
    zd_path = str(tmp_path / "zd.json")
    OnboardingStore(str(tmp_path / "s.json"), zd=Zugangsdaten(zd_path)).save(
        provider_api_key="sk-x")
    assert stat.S_IMODE(os.stat(zd_path).st_mode) == 0o600


# -- #84 AC1: read-both — ZD bevorzugt, Alt-Datei als Fallback --------

def test_84_read_only_zd(tmp_path):
    """Liegt ein Wert nur im ZD-Speicher, kommt er aus load() zurück."""
    zd = _zd(tmp_path)
    zd.set(ZD_NAME_PROVIDER_API_KEY, "sk-zd")
    loaded = OnboardingStore(str(tmp_path / "none.json"), zd=zd).load()
    assert loaded["provider_api_key"] == "sk-zd"


def test_84_read_fallback_to_alt_before_migration_marker(tmp_path):
    """Liegt ein Wert nur in der Alt-Datei, liefert load() ihn (Fallback) —
    die Migration zieht ihn dabei in den ZD-Speicher."""
    alt = str(tmp_path / "old.json")
    _write_alt(alt, provider_api_key="sk-alt")
    zd = _zd(tmp_path)
    loaded = OnboardingStore(alt, zd=zd).load()
    assert loaded["provider_api_key"] == "sk-alt"
    assert zd.get(ZD_NAME_PROVIDER_API_KEY) == "sk-alt"


# -- #84 AC2: lazy-Migration einmalig + .migrated-Marker --------------

def test_84_migration_moves_alt_into_zd_and_renames(tmp_path):
    """Beim ersten load() wandern die Alt-Werte in den ZD-Speicher und die
    Alt-Datei wird zu <pfad>.migrated umbenannt (lazy-on-load)."""
    alt = str(tmp_path / "old.json")
    _write_alt(alt, provider_api_key="sk-alt", family_group_chat_id="-100")
    zd = _zd(tmp_path)

    OnboardingStore(alt, zd=zd).load()

    assert zd.get(ZD_NAME_PROVIDER_API_KEY) == "sk-alt"
    assert zd.get(ZD_NAME_FAMILY_GROUP) == "-100"
    assert not os.path.exists(alt)
    assert os.path.exists(alt + MIGRATED_SUFFIX)


def test_84_migration_is_idempotent(tmp_path):
    """Ein zweites load() ist ein No-Op (Marker existiert) und stürzt nicht ab —
    auch ohne Alt-Datei."""
    alt = str(tmp_path / "old.json")
    _write_alt(alt, provider_api_key="sk-alt")
    zd = _zd(tmp_path)
    store = OnboardingStore(alt, zd=zd)
    store.load()
    # Zweiter Lauf: Marker da, Alt-Datei weg — nichts kippt, Wert bleibt.
    loaded = store.load()
    assert loaded["provider_api_key"] == "sk-alt"


def test_84_no_alt_file_no_marker(tmp_path):
    """Frische Instanz ohne Alt-Datei: load() liefert leeren Speicher und legt
    KEINEN .migrated-Marker an (es gibt nichts zu migrieren)."""
    alt = str(tmp_path / "old.json")
    store = OnboardingStore(alt, zd=_zd(tmp_path))
    assert store.load() == {}
    assert not os.path.exists(alt + MIGRATED_SUFFIX)


# -- #84 AC1: ZD gewinnt — vorhandener ZD-Wert wird nicht überschrieben --

def test_84_zd_value_wins_over_alt_on_migration(tmp_path):
    """Steht ein Wert bereits im ZD-Speicher, überschreibt die Alt-Datei ihn bei
    der Migration NICHT (ZD ist die jüngere Wahrheit)."""
    alt = str(tmp_path / "old.json")
    _write_alt(alt, provider_api_key="sk-alt")
    zd = _zd(tmp_path)
    zd.set(ZD_NAME_PROVIDER_API_KEY, "sk-neu")

    loaded = OnboardingStore(alt, zd=zd).load()

    assert zd.get(ZD_NAME_PROVIDER_API_KEY) == "sk-neu"
    assert loaded["provider_api_key"] == "sk-neu"


def test_84_missing_file_loads_empty(tmp_path):
    assert OnboardingStore(str(tmp_path / "none.json"), zd=_zd(tmp_path)).load() == {}


def test_ONB_5_corrupt_alt_file_loads_empty(tmp_path):
    """Eine kaputte Alt-Datei reißt das Laden nicht ab — leerer Speicher, und es
    wird nichts in den ZD-Speicher geschoben."""
    bad = str(tmp_path / "old.json")
    with open(bad, "w") as f:
        f.write("{kein valides json")
    zd = _zd(tmp_path)
    assert OnboardingStore(bad, zd=zd).load() == {}
    assert zd.names() == []


def test_ONB_5_persists_across_instances(tmp_path):
    """Eine eingerichtete Instanz übersteht einen Neustart — der Wert liegt im
    geteilten ZD-Speicher, eine zweite Store-Instanz liest ihn."""
    zd_path = str(tmp_path / "zd.json")
    OnboardingStore(str(tmp_path / "s.json"), zd=Zugangsdaten(zd_path)).save(
        provider_api_key="sk-x")
    assert OnboardingStore(
        str(tmp_path / "s.json"), zd=Zugangsdaten(zd_path)).load()["provider_api_key"] == "sk-x"
