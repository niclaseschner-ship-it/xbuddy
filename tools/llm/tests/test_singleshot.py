"""get_singleshot — Modell-Durchreichung + forced-tool end-to-end (T1084, LLMP-S11).

Ohne Netz: Anthropic über einen Fake-SDK-Client, Mistral über gemocktes
litellm-SDK (Motor-Weg, #1536 — Hand-Vendor `_vendor/mistral.py` entfernt).
Spiegel test_spike_stufe1_fixtures (Anthropic) + test_vendor_litellm (litellm).

- get_singleshot(slot, model="claude-opus-4-7") reicht model an den Vendor durch
  (vendor.model == opus).
- get_singleshot(slot) ohne model → Vendor-DEFAULT_MODEL.
- Anthropic- + litellm-Mistral-Pfad: forced tool_use end-to-end gegen Fake-Client /
  Fake-litellm → Schema-konformes dict.
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
#  litellm-Fakes (Spiegel test_vendor_litellm — Mistral via Motor-Weg, #1536)
# ----------------------------------------------------------------------

def _make_litellm_tool_call(name, payload):
    tc = MagicMock()
    tc.id = "call-lit-1"
    fn = MagicMock()
    fn.name = name
    fn.arguments = json.dumps(payload)
    tc.function = fn
    return tc


def _make_litellm_singleshot_response(*, tool_name=None, payload=None):
    """OpenAI-förmige LiteLLM-ModelResponse für singleshot_structured."""
    message = MagicMock()
    message.content = ""
    if tool_name and payload is not None:
        message.tool_calls = [_make_litellm_tool_call(tool_name, payload)]
    else:
        message.tool_calls = []
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = 90
    resp.usage.completion_tokens = 25
    resp.usage.cache_read_input_tokens = 0
    resp.usage.cache_creation_input_tokens = 0
    return resp


def _fake_litellm(response=None):
    """Gemocktes litellm-SDK für den litellm-Motor-Pfad."""
    fake = MagicMock()
    fake.exceptions.APIError = Exception
    if response is not None:
        fake.completion.return_value = response
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
#  max_tokens-Durchreichung (T1084)
# ----------------------------------------------------------------------

def test_get_singleshot_passes_max_tokens_to_vendor_anthropic():
    """get_singleshot(slot, max_tokens=8192) reicht max_tokens an den Anthropic-Vendor
    durch — vendor.max_tokens == 8192 (AC1)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key", max_tokens=8192)
    assert ss._vendor.max_tokens == 8192


def test_get_singleshot_without_max_tokens_keeps_vendor_default_anthropic():
    """get_singleshot(slot) ohne max_tokens → Vendor-DEFAULT_MAX_TOKENS=2048 unverändert (AC1)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        from tools.llm._vendor.anthropic import DEFAULT_MAX_TOKENS
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key")
    assert ss._vendor.max_tokens == DEFAULT_MAX_TOKENS


def test_get_singleshot_passes_max_tokens_to_vendor_litellm_mistral():
    """get_singleshot(slot, max_tokens=4096) reicht max_tokens an den litellm-Vendor
    durch — vendor.max_tokens == 4096 (AC1, Mistral-via-litellm-Pfad, #1536).
    Slot ist `hoerspiel-litellm-eu-api-key` (litellm_slot_for_provider)."""
    fake_lit = _fake_litellm()
    with patch.dict(sys.modules, {"litellm": fake_lit}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-litellm-eu-api-key", max_tokens=4096)
    assert ss._vendor.max_tokens == 4096


def test_get_singleshot_without_max_tokens_keeps_vendor_default_litellm():
    """get_singleshot(slot) ohne max_tokens → litellm-Vendor-DEFAULT_MAX_TOKENS unverändert
    (AC1, #1536: Mistral läuft über litellm-Motor, kein Hand-Vendor mehr)."""
    fake_lit = _fake_litellm()
    with patch.dict(sys.modules, {"litellm": fake_lit}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_singleshot
        from tools.llm._vendor.litellm import DEFAULT_MAX_TOKENS as LITELLM_DEFAULT_MAX_TOKENS
        ss = get_singleshot(slot="hoerspiel-litellm-eu-api-key")
    assert ss._vendor.max_tokens == LITELLM_DEFAULT_MAX_TOKENS


def test_anthropic_singleshot_max_tokens_in_create_call(jsonl_path):
    """Anthropic: max_tokens=8192 landet in messages.create (AC1 — _create verwendet vendor.max_tokens)."""
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response(
        [_anthropic_tool_use_block("ergebnis", ERGEBNIS)]
    )

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key",
                            model="claude-opus-4-7", max_tokens=8192)
        ss.complete_structured(
            system="S", prompt="P", schema=SCHEMA, tool_name="ergebnis",
        )

    call = client.messages.create.call_args
    assert call.kwargs["max_tokens"] == 8192


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
    """Mistral-via-litellm-Pfad: forced (benannte) tool_choice → Schema-konformes dict
    end-to-end gegen Fake-litellm-SDK (#1536 — Hand-Vendor entfernt, Motor-Weg).
    Slot ist `hoerspiel-litellm-eu-api-key`; Modell `mistral-large-2411` bekommt
    das `mistral/`-Präfix (LLMP-S13/normalize_model)."""
    lit_response = _make_litellm_singleshot_response(
        tool_name="folgen_vorschlag", payload=ERGEBNIS,
    )
    fake_lit = _fake_litellm(lit_response)

    with patch.dict(sys.modules, {"litellm": fake_lit}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-litellm-eu-api-key",
                            model="mistral-large-2411")
        out = ss.complete_structured(
            system="Du erfindest Folgen.",
            prompt="Erfinde eine Folge.",
            schema=SCHEMA,
            tool_name="folgen_vorschlag",
        )

    assert out == ERGEBNIS
    # LLMP-S13: normalize_model hat das `mistral/`-Präfix ergänzt.
    assert fake_lit.completion.call_args.kwargs["model"] == "mistral/mistral-large-2411"
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "hoerspiel"
