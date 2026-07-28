"""get_agent — max_tokens-Durchreichung (T1129, AC1).

Spiegel von `test_singleshot.py:119-163` für die Agent-Sicht: prüft, dass
`get_agent(slot, max_tokens=N)` den Wert an den Vendor durchreicht und dass
`get_agent(slot)` ohne Argument den Vendor-DEFAULT_MAX_TOKENS unverändert lässt.

Mock-Naht identisch zu `test_singleshot.py` und `test_agent_step.py`:
`patch.dict(sys.modules, {"anthropic": fake})` + `resolve_api_key`-Stub.
Mistral-Pfad läuft über den litellm-Motor (`eltern-chat-litellm-eu-api-key`),
der Hand-Vendor `_vendor/mistral.py` ist entfernt (#1536).
"""

import sys
from unittest.mock import MagicMock, patch


def _fake_anthropic():
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception
    return fake, client


def _fake_litellm():
    """Gemocktes litellm-SDK für den litellm-Motor-Pfad (Spiegel test_vendor_litellm)."""
    fake = MagicMock()
    fake.exceptions.APIError = Exception
    return fake


# ----------------------------------------------------------------------
#  max_tokens-Durchreichung (T1129)
# ----------------------------------------------------------------------


def test_get_agent_passes_max_tokens_to_vendor_anthropic():
    """get_agent(slot, max_tokens=4096) reicht max_tokens an den Anthropic-Vendor
    durch — vendor.max_tokens == 4096 (AC1)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        ag = get_agent(slot="eltern-chat-anthropic-api-key", max_tokens=4096)
    assert ag._vendor.max_tokens == 4096


def test_get_agent_without_max_tokens_keeps_vendor_default_anthropic():
    """get_agent(slot) ohne max_tokens → Vendor-DEFAULT_MAX_TOKENS=2048 unverändert (AC1,
    rückwärtskompatibel — `get_agent(slot)` bleibt unverändert)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        from tools.llm._vendor.anthropic import DEFAULT_MAX_TOKENS
        ag = get_agent(slot="eltern-chat-anthropic-api-key")
    assert ag._vendor.max_tokens == DEFAULT_MAX_TOKENS


def test_get_agent_passes_max_tokens_to_vendor_litellm_mistral():
    """get_agent(slot, max_tokens=4096) reicht max_tokens an den litellm-Vendor
    durch — vendor.max_tokens == 4096 (AC1, Mistral-via-litellm-Pfad, #1536).
    Slot ist `eltern-chat-litellm-eu-api-key` (litellm_slot_for_provider)."""
    fake_litellm = _fake_litellm()
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_agent
        ag = get_agent(slot="eltern-chat-litellm-eu-api-key", max_tokens=4096)
    assert ag._vendor.max_tokens == 4096


def test_get_agent_without_max_tokens_keeps_vendor_default_litellm():
    """get_agent(slot) ohne max_tokens → litellm-Vendor-DEFAULT_MAX_TOKENS unverändert (AC1,
    #1536: Mistral läuft über litellm-Motor, kein Hand-Vendor mehr)."""
    fake_litellm = _fake_litellm()
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_agent
        from tools.llm._vendor.litellm import DEFAULT_MAX_TOKENS as LITELLM_DEFAULT_MAX_TOKENS
        ag = get_agent(slot="eltern-chat-litellm-eu-api-key")
    assert ag._vendor.max_tokens == LITELLM_DEFAULT_MAX_TOKENS
