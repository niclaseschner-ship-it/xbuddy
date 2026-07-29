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
    ZD_NAME_PROVIDER_NAME,
    OnboardingStore,
    vendor_slug_for_adapter,
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


# -- #1537: load() liest nur noch den Single-Slot -----------------------
# Der vendor-spezifische Slot-Read + die Lazy-Migration (T663 Welle A) sind mit
# #1537 entfernt: nach #1510 setzt kein produktiver Aufrufer mehr provider_name,
# und der Laufzeit-Key kommt über den litellm-Slot (nicht die alten vendor-Slots).

def test_load_reads_only_single_slot_ignoring_vendor_slot(tmp_path):
    """#1537: load() liest ausschließlich den Single-Slot — ein gesetzter
    vendor-Slot (`eltern-chat-anthropic-api-key`) wird NICHT mehr gelesen."""
    zd = _zd(tmp_path)
    zd.set(zd_name_provider_api_key("claude"), "sk-ant-vendor-key")   # ignoriert
    # Kein Single-Slot gesetzt → kein provider-Key im Ergebnis.
    loaded = OnboardingStore(zd=zd).load()
    assert "provider_api_key" not in loaded, (
        "#1537: vendor-Slot darf nicht mehr gelesen werden — nur Single-Slot")


def test_load_does_not_write_vendor_slot(tmp_path):
    """#1537: load() ist wieder rein lesend — die alte Lazy-Migration
    (Single→vendor) ist weg, ein gefüllter Single-Slot löst KEINEN Schreib aus."""
    zd = _zd(tmp_path)
    zd.set(ZD_NAME_PROVIDER_API_KEY, "sk-single")
    OnboardingStore(zd=zd).load()
    assert zd.get(zd_name_provider_api_key("claude")) is None, (
        "#1537: load() darf keinen vendor-Slot mehr schreiben (Lazy-Migration weg)")


def test_zd_name_provider_api_key_helper():
    """Helper baut den Slot-Namen aus dem Adapter-Namen, mappt aber auf den
    Brand-Vendor (T663 Welle A / Watchdog B2): `claude` → Anthropic-Slot, NICHT
    Claude-Slot. ZD-2-Tabelle (`specs/platform/zugangsdaten.md`) ist bindend."""
    assert zd_name_provider_api_key("claude") == "eltern-chat-anthropic-api-key"
    assert zd_name_provider_api_key("mistral") == "eltern-chat-mistral-api-key"


def test_zd_name_provider_api_key_rejects_empty():
    """Helper wirft auf leeren Adapter-Namen."""
    import pytest
    with pytest.raises(ValueError, match="adapter_name"):
        zd_name_provider_api_key("")


# -- T663 Welle A: Adapter→Vendor-Mapping (Watchdog B2) ------------------

def test_vendor_slug_for_adapter_claude_to_anthropic():
    """T663 Welle A / Watchdog B2: `cfg.provider` ist der Adapter-Name
    (`claude`), aber der Slot heißt nach dem Brand-Vendor (`anthropic` —
    ZD-2-Tabelle). Mapping `claude → anthropic` ist bindend."""
    assert vendor_slug_for_adapter("claude") == "anthropic"


def test_vendor_slug_for_adapter_mistral_passthrough():
    """Adapter-Name = Brand-Vendor für Mistral → 1:1-Mapping."""
    assert vendor_slug_for_adapter("mistral") == "mistral"


def test_vendor_slug_for_adapter_unknown_passthrough():
    """Unbekannter Adapter wird 1:1 zurückgegeben (Pragmatik für künftige
    Adapter, deren Adapter-Name = Brand-Vendor). Der Passthrough erfolgt,
    wenn der Adapter nicht in der `_ADAPTER_BRAND_VENDOR`-Map enthalten ist
    (#1510, T1022)."""
    assert vendor_slug_for_adapter("openai") == "openai"
    assert vendor_slug_for_adapter("azure-openai") == "azure-openai"


def test_vendor_slug_for_adapter_rejects_empty():
    import pytest
    with pytest.raises(ValueError, match="adapter_name"):
        vendor_slug_for_adapter("")


# -- ECP-1 (#1537): Drift-Sperre Adapter-Map ↔ ZD-2-Tabelle -------------

def test_ECP_1_adapter_map_is_single_source_of_truth():
    """ECP-1-Drift-Sperre (#1537): jeder Eintrag der `_ADAPTER_BRAND_VENDOR`-Map
    hat einen nicht-leeren String-Slug, und der daraus abgeleitete ZD-Slot-Name
    (`eltern-chat-<brand_vendor>-api-key`) steht wörtlich in der ZD-2-Tabelle
    (`specs/platform/zugangsdaten.md`). Sperrt Drift zwischen der Map und der
    Spec-Tabelle — die Map ist die eine Wahrheitsquelle."""
    import os

    from onboarding_store import _ADAPTER_BRAND_VENDOR

    # ZD-2-Tabelle (Repo-Root/specs/platform/zugangsdaten.md) einlesen. Der Test
    # liegt in eltern-chat/tests/ → drei Ebenen hoch zum Repo-Root.
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", ".."))
    zd_spec = os.path.join(repo_root, "specs", "platform", "zugangsdaten.md")
    with open(zd_spec, encoding="utf-8") as fh:
        zd_text = fh.read()

    assert _ADAPTER_BRAND_VENDOR, "Adapter-Map darf nicht leer sein"
    for adapter_name, vendor in _ADAPTER_BRAND_VENDOR.items():
        assert isinstance(vendor, str), (
            "ECP-1: Brand-Vendor-Slug für %r muss ein String sein" % adapter_name)
        assert vendor, (
            "ECP-1: Brand-Vendor-Slug für %r darf nicht leer sein" % adapter_name)
        # Abgeleiteter Slug muss über den Helper konsistent sein.
        assert vendor_slug_for_adapter(adapter_name) == vendor
        slot = zd_name_provider_api_key(adapter_name)
        assert slot == "eltern-chat-%s-api-key" % vendor
        assert slot in zd_text, (
            "ECP-1: ZD-Slot %r (aus Adapter %r) fehlt in der ZD-2-Tabelle "
            "specs/platform/zugangsdaten.md — Map und Spec sind gedriftet"
            % (slot, adapter_name))


def test_zd_name_provider_name_constant_is_centralized():
    """Watchdog B4: ZD_NAME_PROVIDER_NAME lebt zentral in onboarding_store —
    der Skill importiert die Konstante, statt sie selbst zu führen. Wert
    bleibt stabil (ZD-2)."""
    assert ZD_NAME_PROVIDER_NAME == "eltern-chat-provider-name"
