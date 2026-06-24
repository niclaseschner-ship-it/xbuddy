"""Tests für `tools.llm._resolver` — Slot-Parsing (LLMP-5).

Der Parser löst den Vendor per Lookup gegen `_vendor/<vendor>.py`-Module
auf — nicht per Positions-Annahme. Damit dürfen Konsumenten-Namen
Bindestriche enthalten (`eltern-chat`); ein Slot mit unbekanntem Vendor
wirft `LLMCapabilityError` (LLMP-S3), nicht `ModuleNotFoundError`.
"""

import sys
import types

import pytest

from tools.llm import LLMCapabilityError
from tools.llm._resolver import parse_slot


def _install_fake_vendor(name: str):
    """Hängt ein leeres Fake-Vendor-Modul unter `tools.llm._vendor.<name>`."""
    module = types.ModuleType("tools.llm._vendor.%s" % name)
    module.CAPABILITIES = frozenset()
    sys.modules["tools.llm._vendor.%s" % name] = module
    return module


def _cleanup_fake(name: str):
    sys.modules.pop("tools.llm._vendor.%s" % name, None)


def test_parse_slot_kibuddy_anthropic():
    """LLMP-5: `kibuddy-anthropic-api-key` → (kibuddy, anthropic, api-key)."""
    caller, vendor, purpose = parse_slot("kibuddy-anthropic-api-key")
    assert caller == "kibuddy"
    assert vendor == "anthropic"
    assert purpose == "api-key"


def test_parse_slot_hoerspiel_anthropic():
    """LLMP-5: gleicher Schnitt für hoerspiel."""
    caller, vendor, purpose = parse_slot("hoerspiel-anthropic-api-key")
    assert caller == "hoerspiel"
    assert vendor == "anthropic"
    assert purpose == "api-key"


def test_parse_slot_bindestrich_caller():
    """Fix-1/AC1: bindestrichiger Konsument wie `eltern-chat` löst korrekt auf.

    Vorher (T1082-S1): naiver split('-') ergab fälschlich
    caller='eltern', vendor='chat'. Mit Vendor-Lookup gegen vorhandene
    `_vendor/<vendor>.py`-Module ist `anthropic` das erkennbare Vendor-
    Segment; alles davor ist caller, alles danach purpose.
    """
    caller, vendor, purpose = parse_slot("eltern-chat-anthropic-api-key")
    assert caller == "eltern-chat"
    assert vendor == "anthropic"
    assert purpose == "api-key"


def test_parse_slot_unknown_vendor_raises():
    """Fix-1/AC2: unbekannter Vendor → `LLMCapabilityError` (nicht ModuleNotFoundError).

    `cohere` ist heute nicht implementiert. Statt eines unklaren
    `ModuleNotFoundError: tools.llm._vendor.cohere` beim späteren Import
    wirft der Parser direkt einen ehrlichen `LLMCapabilityError` mit der
    Liste der bekannten Vendoren (LLMP-S3).
    """
    with pytest.raises(LLMCapabilityError) as exc_info:
        parse_slot("hoerspiel-cohere-api-key")
    msg = str(exc_info.value)
    assert "cohere" in msg or "kein bekanntes Vendor-Segment" in msg
    assert "anthropic" in msg  # bekannte Vendoren werden gelistet


def test_parse_slot_unknown_vendor_kibuddy_raises():
    """Variante: bekannter Konsument, unbekannter Vendor."""
    with pytest.raises(LLMCapabilityError) as exc_info:
        parse_slot("kibuddy-unknown-api-key")
    assert "unknown" in str(exc_info.value) or "kein bekanntes Vendor-Segment" in str(exc_info.value)


def test_parse_slot_two_segments_raises():
    """Zwei Segmente reichen nicht — Konvention verlangt drei."""
    with pytest.raises(ValueError, match="LLMP-5"):
        parse_slot("kibuddy-anthropic")


def test_parse_slot_empty_raises():
    """Leerer Slot ist ein klarer Konfigurationsfehler."""
    with pytest.raises(ValueError, match="nicht-leerer String"):
        parse_slot("")


def test_parse_slot_none_raises():
    """`None` ist kein gültiger Slot."""
    with pytest.raises(ValueError, match="nicht-leerer String"):
        parse_slot(None)  # type: ignore[arg-type]


def test_parse_slot_ambiguous_two_known_vendors_raises():
    """Wenn zwei Segmente auf bekannte Vendoren matchen → mehrdeutig.

    Eintrag eines zweiten Vendor-Moduls (Fake `acme`) mit einem Slot, der
    `acme-anthropic-api-key` formt (caller=acme matcht, vendor-Position
    ist mehrdeutig). Der Parser darf hier nicht stillschweigend einen
    auswählen, sondern muss den Konflikt sichtbar machen.
    """
    _install_fake_vendor("acme")
    try:
        with pytest.raises(LLMCapabilityError, match="mehrdeutig"):
            parse_slot("acme-anthropic-api-key")
    finally:
        _cleanup_fake("acme")


def test_parse_slot_caller_only_raises():
    """Slot ohne purpose-Teil (Vendor am Ende) → ValueError."""
    with pytest.raises(ValueError, match="leeren purpose-Teil"):
        parse_slot("kibuddy-foo-anthropic")


def test_parse_slot_vendor_only_raises():
    """Slot ohne caller-Teil (Vendor am Anfang) → ValueError."""
    with pytest.raises(ValueError, match="leeren caller-Teil"):
        parse_slot("anthropic-foo-bar")
