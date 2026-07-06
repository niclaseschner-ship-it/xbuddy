"""Tests für `tools.llm._vendor.anthropic` — CAPABILITIES-Frozenset (LLMP-4)."""

from tools.llm._vendor import anthropic as anthropic_vendor


def test_capabilities_is_frozenset():
    """LLMP-4 Watchdog: `CAPABILITIES` ist ein `frozenset` am Modulkopf."""
    assert isinstance(anthropic_vendor.CAPABILITIES, frozenset)


def test_capabilities_contains_seven_ratified_capabilities():
    """LLMP-3: Anthropic deklariert alle sieben ratifizierten Capabilities
    (die sechs V1 + `web_search`, T1371 additiv)."""
    expected = frozenset({
        "tool_use",
        "multi_turn_assistant_prefill",
        "structured_output",
        "cache_control",
        "multimodal_input",
        "system_message_distinct",
        "web_search",
    })
    assert expected == anthropic_vendor.CAPABILITIES


def test_vendor_class_named_anthropic_vendor():
    """LLMP-4 Bauregel: Klasse heißt `<Vendor>Vendor`."""
    assert hasattr(anthropic_vendor, "AnthropicVendor")
