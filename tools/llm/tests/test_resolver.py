"""Tests für `tools.llm._resolver` — Slot-Parsing (LLMP-5)."""

import pytest

from tools.llm._resolver import parse_slot


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


def test_parse_slot_purpose_with_dashes():
    """Purpose darf weitere Bindestriche tragen — Vendor ist immer Segment 2."""
    caller, vendor, purpose = parse_slot("eltern-chat-anthropic-api-key")
    # ACHTUNG (Annahme): `eltern-chat-…` enthält selbst einen Bindestrich;
    # split('-')[0] ist `eltern`, [1] ist `chat`. Das ist die heutige
    # Slot-Form aus ZD-2 — der Parser nimmt vendor als zweites Segment.
    # Konsumenten, die diesen Konflikt vermeiden wollen, wählen einen Slot
    # ohne Bindestrich im Konsumenten-Teil (vgl. `kibuddy`, `hoerspiel`).
    # Dokumentiert hier, damit der Konflikt nicht still ist.
    assert caller == "eltern"
    assert vendor == "chat"
    assert purpose == "anthropic-api-key"


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
