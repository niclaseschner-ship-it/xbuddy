"""get_agent — max_tokens-Durchreichung (T1129, AC1).

Spiegel von `test_singleshot.py:119-163` für die Agent-Sicht: prüft, dass
`get_agent(slot, max_tokens=N)` den Wert an den Vendor durchreicht und dass
`get_agent(slot)` ohne Argument den Vendor-DEFAULT_MAX_TOKENS unverändert lässt.

Mock-Naht identisch zu `test_singleshot.py` und `test_agent_step.py`:
`patch.dict(sys.modules, {"anthropic": fake})` + `resolve_api_key`-Stub.
"""

import sys
from unittest.mock import MagicMock, patch


def _fake_anthropic():
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception
    return fake, client


def _fake_httpx(response_json, *, status_code=200):
    import json
    fake = MagicMock()
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = response_json
    resp.text = json.dumps(response_json)
    fake.post.return_value = resp
    fake.RequestError = Exception
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


def test_get_agent_passes_max_tokens_to_vendor_mistral():
    """get_agent(slot, max_tokens=4096) reicht max_tokens an den Mistral-Vendor
    durch — vendor.max_tokens == 4096 (AC1, Mistral-Pfad)."""
    fake_httpx = _fake_httpx({})
    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_agent
        ag = get_agent(slot="eltern-chat-mistral-api-key", max_tokens=4096)
    assert ag._vendor.max_tokens == 4096


def test_get_agent_without_max_tokens_keeps_vendor_default_mistral():
    """get_agent(slot) ohne max_tokens → Mistral-Vendor-DEFAULT_MAX_TOKENS=4096 (AC1)."""
    fake_httpx = _fake_httpx({})
    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_agent
        from tools.llm._vendor.mistral import DEFAULT_MAX_TOKENS as MISTRAL_DEFAULT_MAX_TOKENS
        ag = get_agent(slot="eltern-chat-mistral-api-key")
    assert ag._vendor.max_tokens == MISTRAL_DEFAULT_MAX_TOKENS
