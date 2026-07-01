"""get_completion — Freitext-Singleshot, beide Vendoren (#1131, LLMP-S1).

Ohne Netz: Anthropic über einen Fake-SDK-Client, Mistral über gemocktes
httpx.post. Spiegel `test_singleshot` (get_singleshot), aber für die vierte
Sicht: kein Tool, kein Schema, ein Vendor-Call, Freitext-String zurück.

- get_completion(slot, model=…) reicht model an den Vendor durch.
- get_completion(slot) ohne model → Vendor-DEFAULT_MODEL.
- Required-Set NUR system_message_distinct → bootet auf Claude UND Mistral
  (kein cache_control-Boot-Fail auf dem Mistral-Slot).
- max_tokens-Durchreichung (T1084-Parität) auf beiden Vendoren.
- Anthropic- + Mistral-Pfad: Freitext end-to-end (kein tool_choice im Payload).
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


SYNOPSE = "Stigi findet den Trübsee und lernt, dass Mut ansteckend ist."


# ----------------------------------------------------------------------
#  Anthropic-Fakes (Spiegel test_singleshot)
# ----------------------------------------------------------------------

def _anthropic_text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _anthropic_response(blocks):
    resp = MagicMock()
    resp.content = blocks
    usage = MagicMock()
    usage.input_tokens = 120
    usage.output_tokens = 40
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    resp.usage = usage
    return resp


def _fake_anthropic():
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception
    return fake, client


# ----------------------------------------------------------------------
#  Mistral-Fakes (Spiegel test_vendor_mistral)
# ----------------------------------------------------------------------

def _fake_httpx(response_json, *, status_code=200):
    fake = MagicMock()
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = response_json
    resp.text = json.dumps(response_json)
    fake.post.return_value = resp
    fake.RequestError = Exception
    return fake


# ----------------------------------------------------------------------
#  Boot: Required-Set trägt beide Vendoren
# ----------------------------------------------------------------------

def test_get_completion_boots_on_anthropic():
    """Anthropic-Slot bootet (system_message_distinct in CAPABILITIES)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key")
    assert comp.name == "completion"


def test_get_completion_boots_on_mistral():
    """Mistral-Slot bootet — Required-Set OHNE cache_control (LLMP-S9), sonst
    wäre die Sicht auf Mistral boot-fatal (#1131)."""
    fake_httpx = _fake_httpx({})
    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-mistral-api-key")
    assert comp.name == "completion"


# ----------------------------------------------------------------------
#  Modell- + max_tokens-Durchreichung
# ----------------------------------------------------------------------

def test_get_completion_passes_model_to_vendor():
    """get_completion(slot, model) reicht das Modell an den Vendor durch."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key",
                              model="claude-opus-4-7")
    assert comp.model == "claude-opus-4-7"


def test_get_completion_without_model_uses_vendor_default():
    """get_completion(slot) ohne model → Vendor-DEFAULT_MODEL."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        from tools.llm._vendor.anthropic import DEFAULT_MODEL
        comp = get_completion(slot="hoerspiel-anthropic-api-key")
    assert comp.model == DEFAULT_MODEL


def test_get_completion_passes_max_tokens_anthropic():
    """get_completion(slot, max_tokens=8192) → vendor.max_tokens == 8192 (AC3)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key", max_tokens=8192)
    assert comp._vendor.max_tokens == 8192


def test_get_completion_passes_max_tokens_mistral():
    """get_completion(slot, max_tokens=4096) → Mistral vendor.max_tokens == 4096 (AC3)."""
    fake_httpx = _fake_httpx({})
    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-mistral-api-key", max_tokens=4096)
    assert comp._vendor.max_tokens == 4096


# ----------------------------------------------------------------------
#  Freitext end-to-end — kein Tool/Schema im Payload
# ----------------------------------------------------------------------

def test_anthropic_completion_freitext_end_to_end(jsonl_path):
    """Anthropic: .complete(system, user) → Freitext-String; KEIN tools/
    tool_choice im create-Call; max_tokens durchgereicht; Telemetrie geschrieben."""
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response(
        [_anthropic_text_block(SYNOPSE)]
    )

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key",
                              model="claude-opus-4-7", max_tokens=8192)
        out = comp.complete(system="Fasse zusammen.", user="Der Folgentext …")

    assert out == SYNOPSE
    call = client.messages.create.call_args
    assert call.kwargs["model"] == "claude-opus-4-7"
    assert call.kwargs["max_tokens"] == 8192
    # Freitext-Singleshot: KEIN Tool, KEIN tool_choice (Abgrenzung zu get_singleshot).
    assert "tools" not in call.kwargs
    assert "tool_choice" not in call.kwargs
    # system_message_distinct: der System-Prompt liegt getrennt in `system`.
    assert call.kwargs["system"][0]["text"] == "Fasse zusammen."
    # Telemetrie: caller=hoerspiel.
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "hoerspiel"
    assert parsed["model_id"] == "claude-opus-4-7"


def test_mistral_completion_freitext_end_to_end(jsonl_path):
    """Mistral: .complete(system, user) → Freitext-String aus message.content;
    KEIN tools/tool_choice im Payload; Telemetrie geschrieben."""
    response_json = {
        "choices": [{"message": {"content": SYNOPSE}}],
        "usage": {"prompt_tokens": 110, "completion_tokens": 35},
    }
    fake_httpx = _fake_httpx(response_json)

    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-mistral-api-key",
                              model="mistral-large-2411")
        out = comp.complete(system="Fasse zusammen.", user="Der Folgentext …")

    assert out == SYNOPSE
    sent = json.loads(fake_httpx.post.call_args.kwargs["content"])
    assert sent["model"] == "mistral-large-2411"
    # Freitext-Singleshot: KEIN Tool, KEIN tool_choice.
    assert "tools" not in sent
    assert "tool_choice" not in sent
    # system_message_distinct: eigener system-Message-Eintrag.
    assert sent["messages"][0] == {"role": "system", "content": "Fasse zusammen."}
    assert sent["messages"][1] == {"role": "user", "content": "Der Folgentext …"}
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "hoerspiel"


def test_anthropic_completion_api_error_maps_to_provider_error():
    """Anthropic-APIError → tools.llm ProviderError (via _create, wie
    singleshot_structured)."""
    from tools.llm import ProviderError
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.side_effect = fake_anthropic.APIError("boom")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key")
        with pytest.raises(ProviderError):
            comp.complete(system="S", user="U")
