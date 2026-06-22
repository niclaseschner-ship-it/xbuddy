"""Tests für `tools.llm.public_api` — Capability-Boot-Fail (LLMP-S3, LLMP-S11).

Deckt LLMP-S1 (drei Sichten existieren) und LLMP-S3 (Mismatch wirft
`LLMCapabilityError` beim Boot — jede Sicht separat).
"""

import sys
import types
from unittest.mock import patch

import pytest

from tools.llm import LLMCapabilityError, get_agent, get_chat, get_singleshot


def _install_fake_vendor(name: str, capabilities: frozenset, klass_attrs: dict | None = None):
    """Hängt ein Fake-Vendor-Modul unter `tools.llm._vendor.<name>` in sys.modules."""
    module = types.ModuleType("tools.llm._vendor.%s" % name)
    module.CAPABILITIES = capabilities

    # Klasse `<Name>Vendor` nach Convention aus `_vendor_class`.
    class FakeVendor:
        model = "fake-model"

        def __init__(self, *, api_key):
            self.api_key = api_key

        def chat_multiturn(self, *, system, turns, user_message, caller, slot, correlation_id=None):
            return "fake-chat-answer"

    if klass_attrs:
        for k, v in klass_attrs.items():
            setattr(FakeVendor, k, v)
    setattr(module, name.capitalize() + "Vendor", FakeVendor)
    sys.modules["tools.llm._vendor.%s" % name] = module
    return module


def _cleanup_fake(name: str):
    sys.modules.pop("tools.llm._vendor.%s" % name, None)


@pytest.fixture
def fake_full_vendor():
    """Vendor mit allen sechs Capabilities — alle Sichten passieren den Boot."""
    name = "fakefull"
    _install_fake_vendor(name, frozenset({
        "tool_use",
        "multi_turn_assistant_prefill",
        "structured_output",
        "cache_control",
        "multimodal_input",
        "system_message_distinct",
    }))
    yield name
    _cleanup_fake(name)


@pytest.fixture
def fake_reduced_vendor():
    """Vendor ohne `cache_control` — bricht `get_chat`/`get_agent` (LLMP-3)."""
    name = "fakereduced"
    _install_fake_vendor(name, frozenset({
        "multi_turn_assistant_prefill",
        "structured_output",
        "system_message_distinct",
    }))
    yield name
    _cleanup_fake(name)


# ----------------------------------------------------------------------
#  LLMP-S1 — drei Sichten existieren und sind sicht-spezifisch
# ----------------------------------------------------------------------


def test_public_api_exports_three_sichten():
    """LLMP-S1/AC1: `get_agent`, `get_singleshot`, `get_chat` sind importierbar."""
    # Re-Import als End-to-End-Probe für `from tools.llm import …`.
    from tools.llm import get_agent as ga
    from tools.llm import get_chat as gc
    from tools.llm import get_singleshot as gs
    assert callable(ga)
    assert callable(gc)
    assert callable(gs)


def test_chat_facade_returns_chat_object_with_complete_multiturn(fake_full_vendor):
    """LLMP-S1: `get_chat` liefert ein Objekt mit `complete_multiturn`."""
    with patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        chat = get_chat("kibuddy-%s-api-key" % fake_full_vendor)
    assert hasattr(chat, "complete_multiturn")
    assert chat.name == "chat"


def test_singleshot_facade_returns_singleshot_object(fake_full_vendor):
    """LLMP-S1: `get_singleshot` liefert ein Objekt mit `complete_structured`."""
    with patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        ss = get_singleshot("hoerspiel-%s-api-key" % fake_full_vendor)
    assert hasattr(ss, "complete_structured")
    assert ss.name == "singleshot"


def test_agent_facade_returns_agent_object(fake_full_vendor):
    """LLMP-S1: `get_agent` liefert ein Objekt mit `run`."""
    with patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        ag = get_agent("elternchat-%s-api-key" % fake_full_vendor)
    assert hasattr(ag, "run")
    assert ag.name == "agent"


# ----------------------------------------------------------------------
#  LLMP-S3 — Capability-Mismatch beim Boot wirft LLMCapabilityError
# ----------------------------------------------------------------------


def test_capability_mismatch_chat_raises_at_boot(fake_reduced_vendor):
    """LLMP-S3/AC3: `get_chat` ohne `cache_control` → Boot-Fail."""
    with patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"), \
         pytest.raises(LLMCapabilityError) as exc_info:
        get_chat("kibuddy-%s-api-key" % fake_reduced_vendor)
    assert "cache_control" in str(exc_info.value)
    assert "get_chat" in str(exc_info.value)


def test_capability_mismatch_agent_raises_at_boot(fake_reduced_vendor):
    """LLMP-S3/AC3: `get_agent` ohne `tool_use` → Boot-Fail."""
    with patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"), \
         pytest.raises(LLMCapabilityError) as exc_info:
        get_agent("elternchat-%s-api-key" % fake_reduced_vendor)
    assert "tool_use" in str(exc_info.value)
    assert "get_agent" in str(exc_info.value)


def test_capability_mismatch_singleshot_raises_at_boot():
    """LLMP-S3/AC3: `get_singleshot` ohne `structured_output` → Boot-Fail."""
    name = "fakeminimal"
    _install_fake_vendor(name, frozenset({"system_message_distinct"}))
    try:
        with patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"), \
             pytest.raises(LLMCapabilityError) as exc_info:
            get_singleshot("hoerspiel-%s-api-key" % name)
        assert "structured_output" in str(exc_info.value)
        assert "get_singleshot" in str(exc_info.value)
    finally:
        _cleanup_fake(name)


def test_vendor_without_capabilities_raises(fake_full_vendor):
    """LLMP-4 Watchdog: Vendor-Modul ohne `CAPABILITIES`-Frozenset → Boot-Fail."""
    name = "fakenocaps"
    module = types.ModuleType("tools.llm._vendor.%s" % name)
    # Bewusst KEINE CAPABILITIES-Konstante. Klasse trotzdem da, damit der
    # Lade-Pfad nicht vorher schon scheitert.

    class FakeVendor:
        def __init__(self, *, api_key):
            pass
    module.FakenocapsVendor = FakeVendor
    sys.modules["tools.llm._vendor.%s" % name] = module
    try:
        with patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"), \
             pytest.raises(LLMCapabilityError) as exc_info:
            get_chat("kibuddy-%s-api-key" % name)
        assert "CAPABILITIES" in str(exc_info.value)
    finally:
        _cleanup_fake(name)


def test_missing_api_key_raises_at_boot(fake_full_vendor):
    """LLMP-5/ZD-5: kein API-Key im Speicher → Boot-Fail (nicht erst zur Laufzeit)."""
    with patch("tools.llm.public_api.resolve_api_key", return_value=None), \
         pytest.raises(LLMCapabilityError) as exc_info:
        get_chat("kibuddy-%s-api-key" % fake_full_vendor)
    assert "Slot" in str(exc_info.value) or "api-key" in str(exc_info.value).lower()
