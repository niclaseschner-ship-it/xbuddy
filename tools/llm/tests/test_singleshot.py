"""get_singleshot — Modell-Durchreichung + forced-tool end-to-end (T1084, LLMP-S11).

Ohne Netz: Anthropic über einen Fake-SDK-Client, Mistral über gemocktes
httpx.post. Spiegel test_spike_stufe1_fixtures (Anthropic) +
test_vendor_mistral (Mistral).

- get_singleshot(slot, model="claude-opus-4-7") reicht model an den Vendor durch
  (vendor.model == opus).
- get_singleshot(slot) ohne model → Vendor-DEFAULT_MODEL.
- Anthropic- + Mistral-Pfad: forced tool_use end-to-end gegen Fake-Client /
  Fake-httpx → Schema-konformes dict.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


SCHEMA = {
    "type": "object",
    "properties": {
        "titel": {"type": "string"},
        "folgen-nr-vorschlag": {"type": "integer"},
        "text": {"type": "string"},
    },
    "required": ["titel", "folgen-nr-vorschlag", "text"],
}
ERGEBNIS = {
    "titel": "Die Höhle der Mutigen",
    "folgen-nr-vorschlag": 5,
    "text": "Folge 5: Die Höhle der Mutigen.\n\nStigi flog ins Dunkle.",
}


# ----------------------------------------------------------------------
#  Anthropic-Fakes (Spiegel test_spike_stufe1_fixtures)
# ----------------------------------------------------------------------

def _anthropic_tool_use_block(name, payload):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = payload
    return block


def _anthropic_response(blocks):
    resp = MagicMock()
    resp.content = blocks
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 30
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
#  Modell-Durchreichung
# ----------------------------------------------------------------------

def test_get_singleshot_passes_model_to_vendor():
    """get_singleshot(slot, model) reicht das Modell an den Vendor durch —
    opus-4-7 bleibt erhalten (Modell-Erhalt-Entscheid T1084)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key",
                            model="claude-opus-4-7")
    assert ss.model == "claude-opus-4-7"


def test_get_singleshot_without_model_uses_vendor_default():
    """get_singleshot(slot) ohne model → Vendor-DEFAULT_MODEL (rückwärtskompatibel,
    test_spike_stufe1_fixtures bleibt grün)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        from tools.llm._vendor.anthropic import DEFAULT_MODEL
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key")
    assert ss.model == DEFAULT_MODEL


# ----------------------------------------------------------------------
#  forced-tool end-to-end
# ----------------------------------------------------------------------

def test_anthropic_singleshot_forced_tool_end_to_end(jsonl_path):
    """Anthropic-Pfad: forced tool_use → Schema-konformes dict; benannte
    tool_choice; Modell opus durchgereicht."""
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response(
        [_anthropic_tool_use_block("folgen_vorschlag", ERGEBNIS)]
    )

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key",
                            model="claude-opus-4-7")
        out = ss.complete_structured(
            system="Du erfindest Folgen.",
            prompt="Erfinde eine Folge.",
            schema=SCHEMA,
            tool_name="folgen_vorschlag",
        )

    assert out == ERGEBNIS
    call = client.messages.create.call_args
    assert call.kwargs["model"] == "claude-opus-4-7"
    assert call.kwargs["tool_choice"] == {"type": "tool", "name": "folgen_vorschlag"}
    assert call.kwargs["tools"][0]["input_schema"] == SCHEMA
    # Telemetrie: caller=hoerspiel.
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "hoerspiel"
    assert parsed["model_id"] == "claude-opus-4-7"


def test_mistral_singleshot_forced_tool_end_to_end(jsonl_path):
    """Mistral-Pfad: forced (benannte) tool_choice → Schema-konformes dict
    end-to-end gegen Fake-httpx."""
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "folgen_vorschlag", "arguments": json.dumps(ERGEBNIS)},
    }
    response_json = {
        "choices": [{"message": {"content": "", "tool_calls": [tool_call]}}],
        "usage": {"prompt_tokens": 90, "completion_tokens": 25},
    }
    fake_httpx = _fake_httpx(response_json)

    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-mistral-api-key",
                            model="mistral-large-2411")
        out = ss.complete_structured(
            system="Du erfindest Folgen.",
            prompt="Erfinde eine Folge.",
            schema=SCHEMA,
            tool_name="folgen_vorschlag",
        )

    assert out == ERGEBNIS
    sent = json.loads(fake_httpx.post.call_args.kwargs["content"])
    assert sent["model"] == "mistral-large-2411"
    assert sent["tool_choice"] == {"type": "function",
                                   "function": {"name": "folgen_vorschlag"}}
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "hoerspiel"
