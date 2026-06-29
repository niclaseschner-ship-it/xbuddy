"""LibAgentAdapter — eltern-chat-Chat-Agent über `tools.llm` (T1085, PR2).

Deckt den `generate(GenerationRequest) -> GenerationResponse`-Vertrag des
Lib-Adapters ab: kanonisch → neutrale (Anthropic-shaped) Wire-Form, beide
usage-Formen → ProviderUsage (SQLite-Pfad EC-23), die JSONL-Doppelschreibung der
Lib (caller=eltern-chat, correlation_id=turn_id), Slot-Wahl (claude→anthropic),
ProviderError-Mapping (tools.llm → model) und das effektive Modell.

Mock-Naht: das Vendor-SDK wird über `patch.dict(sys.modules, {"anthropic": …})`
bzw. `{"httpx": …}` ersetzt (kein Netz), `tools.llm.public_api.resolve_api_key`
wird gestubt (kein echter Key nötig). `XBUDDY_DATA_DIR` lenkt die JSONL-Datei
auf `tmp_path` (die autouse-conftest-Fixture isoliert nur den ZD-Store).
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from model import (
    GenerationRequest,
    ImageBlock,
    Message,
    ProviderError,
    TaskCallBlock,
    TaskResultBlock,
    TextBlock,
)
from providers.lib_adapter import LibAgentAdapter

# ----------------------------------------------------------------------
#  Fakes — Anthropic-SDK (RAW-usage) + Mistral-HTTP (dict-usage)
# ----------------------------------------------------------------------


def _anthropic_usage(*, input_tokens=120, output_tokens=40, cache_read=5, cache_creation=7):
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.cache_read_input_tokens = cache_read
    u.cache_creation_input_tokens = cache_creation
    return u


def _text_block(text):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_use_block(name, input_obj, call_id="tu-1"):
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_obj
    b.id = call_id
    return b


_NO_USAGE = object()


def _anthropic_response(blocks, usage=_NO_USAGE):
    resp = MagicMock()
    resp.content = blocks
    # `usage=None` heißt explizit "Antwort ohne usage"; Default = RAW-usage-Mock.
    resp.usage = _anthropic_usage() if usage is _NO_USAGE else usage
    return resp


def _fake_anthropic():
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception
    return fake, client


def _fake_httpx(response_json, status_code=200):
    fake = MagicMock()
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = response_json
    resp.text = json.dumps(response_json)
    fake.post.return_value = resp

    class _RequestError(Exception):
        pass

    fake.RequestError = _RequestError
    return fake


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


_TASK_DEFS = [
    type("FakeTaskDef", (), {
        "name": "wetter",
        "description": "Liefert das aktuelle Wetter.",
        "parameters": {"type": "object", "properties": {"ort": {"type": "string"}}},
    })(),
]


def _request(messages, *, system="Du bist ein Assistent.", correlation_id="turn-xyz"):
    return GenerationRequest(
        system=system, messages=messages, task_defs=_TASK_DEFS,
        correlation_id=correlation_id)


# ----------------------------------------------------------------------
#  Claude-Pfad (anthropic-Vendor, RAW-usage)
# ----------------------------------------------------------------------


def test_claude_slot_and_effective_model_opus(jsonl_path):
    """provider='claude' wählt Slot eltern-chat-anthropic-api-key; leeres
    provider_model → effektives Modell claude-opus-4-7 (Alt-Adapter-Default)."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response([_text_block("Hallo.")])

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    # Effektives Modell = opus-4-7 (nicht der Vendor-Haiku-Default).
    assert client.messages.create.call_args.kwargs["model"] == "claude-opus-4-7"
    # Slot landet im JSONL als eltern-chat-anthropic-api-key.
    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert line["slot"] == "eltern-chat-anthropic-api-key"
    assert line["caller"] == "eltern-chat"


def test_claude_tool_use_roundtrip_and_raw_usage(jsonl_path):
    """tool_use-Antwort → TaskCallBlock; RAW-usage (Anthropic) → ProviderUsage
    (SQLite-Pfad EC-23). Plus: Doppelschreibung — usage gefüllt UND ein JSONL-
    Eintrag mit correlation_id=turn_id."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response([
        _text_block("Ich schaue."),
        _tool_use_block("wetter", {"ort": "Berlin"}, call_id="call-7"),
    ])

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        resp = adapter.generate(_request(
            [Message(role="user", blocks=[TextBlock("Wetter?")])],
            correlation_id="turn-42"))

    # tool_use → kanonischer TaskCallBlock.
    assert resp.text == "Ich schaue."
    assert len(resp.task_calls) == 1
    assert isinstance(resp.task_calls[0], TaskCallBlock)
    assert resp.task_calls[0].call_id == "call-7"
    assert resp.task_calls[0].task == "wetter"
    assert resp.task_calls[0].arguments == {"ort": "Berlin"}

    # EC-23 SQLite-Pfad: usage gefüllt aus RAW-Objekt (cache-Felder gemappt).
    assert resp.usage is not None
    assert resp.usage.input_tokens == 120
    assert resp.usage.output_tokens == 40
    assert resp.usage.cache_read_tokens == 5
    assert resp.usage.cache_creation_tokens == 7
    assert resp.usage.model_id == "claude-opus-4-7"

    # JSONL-Doppelschreibung mit correlation_id=turn_id.
    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert line["correlation_id"] == "turn-42"
    assert line["input_tokens"] == 120
    assert line["model_id"] == "claude-opus-4-7"


def test_claude_image_and_tool_result_to_wire(jsonl_path):
    """ImageBlock → {type:image,source:base64,…}; TaskResultBlock mit is_error
    → {type:tool_result,tool_use_id,content,is_error} in der Wire-Form."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response([_text_block("Ein Hund.")])

    messages = [
        Message(role="user", blocks=[
            TextBlock("Was ist das?"),
            ImageBlock(media_type="image/png", data_b64="AAAA"),
        ]),
        Message(role="user", blocks=[
            TaskResultBlock(call_id="call-1", content="Sensor offline", is_error=True),
        ]),
    ]

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request(messages))

    sent = client.messages.create.call_args.kwargs["messages"]
    # ImageBlock → neutrale image-Wire-Form (unverändert durchgereicht).
    img = sent[0]["content"][1]
    assert img["type"] == "image"
    assert img["source"] == {"type": "base64", "media_type": "image/png", "data": "AAAA"}
    # TaskResultBlock mit is_error → tool_result-Wire-Form.
    tr = sent[1]["content"][0]
    assert tr["type"] == "tool_result"
    assert tr["tool_use_id"] == "call-1"
    assert tr["content"] == "Sensor offline"
    assert tr["is_error"] is True


def test_claude_explicit_provider_model_overrides_default(jsonl_path):
    """Konfiguriertes provider_model schlägt den Anbieter-Default (Verhalten
    erhalten: provider_model durchgereicht)."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response([_text_block("Ok.")])

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="claude-sonnet-4-5")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    assert client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-5"


def test_lib_provider_error_maps_to_model_provider_error(jsonl_path):
    """tools.llm.ProviderError aus dem .step()-Call → model.ProviderError
    (run_turn._call_provider fängt model.ProviderError, EC-14)."""
    fake, client = _fake_anthropic()
    # APIError = Exception (siehe _fake_anthropic) → der Vendor übersetzt sie
    # in tools.llm.ProviderError; der Adapter mappt weiter auf model.ProviderError.
    client.messages.create.side_effect = fake.APIError("boom")

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        with pytest.raises(ProviderError):
            adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))


# ----------------------------------------------------------------------
#  Mistral-Pfad (mistral-Vendor, dict-usage)
# ----------------------------------------------------------------------


def test_mistral_slot_dict_usage_and_default_model(jsonl_path):
    """provider='mistral' wählt Slot eltern-chat-mistral-api-key; dict-usage
    (prompt_/completion_tokens) → ProviderUsage; leeres provider_model →
    mistral-medium-2508 (Alt-Adapter-Default)."""
    response_json = {
        "choices": [{"message": {"content": "Servus.", "tool_calls": [
            {"id": "mc-1", "type": "function",
             "function": {"name": "wetter", "arguments": "{\"ort\": \"Wien\"}"}},
        ]}}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 30},
    }
    fake_httpx = _fake_httpx(response_json)

    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-mistral"):
        adapter = LibAgentAdapter(provider="mistral", provider_model="")
        resp = adapter.generate(_request(
            [Message(role="user", blocks=[TextBlock("Wetter?")])],
            correlation_id="turn-99"))

    # tool_call → kanonischer TaskCallBlock (Args geparst).
    assert resp.text == "Servus."
    assert resp.task_calls[0].task == "wetter"
    assert resp.task_calls[0].arguments == {"ort": "Wien"}

    # dict-usage → ProviderUsage (cache=0, model_id = Mistral-Default).
    assert resp.usage is not None
    assert resp.usage.input_tokens == 200
    assert resp.usage.output_tokens == 30
    assert resp.usage.cache_read_tokens == 0
    assert resp.usage.cache_creation_tokens == 0
    assert resp.usage.model_id == "mistral-medium-2508"

    # Payload nutzt das effektive Default-Modell.
    sent_payload = json.loads(fake_httpx.post.call_args.kwargs["content"])
    assert sent_payload["model"] == "mistral-medium-2508"

    # JSONL: caller=eltern-chat, Slot=mistral, correlation_id=turn_id.
    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert line["caller"] == "eltern-chat"
    assert line["slot"] == "eltern-chat-mistral-api-key"
    assert line["correlation_id"] == "turn-99"


# ----------------------------------------------------------------------
#  max_tokens-Durchreichung (T1129)
# ----------------------------------------------------------------------


def test_lib_adapter_passes_max_tokens_4096_to_vendor(jsonl_path):
    """LibAgentAdapter reicht max_tokens=4096 (Alt-Wert claude.py:32) an den
    Anthropic-Vendor durch — messages.create wird mit max_tokens=4096 gerufen (AC2)."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response([_text_block("Ok.")])

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    # Alt-treuer Wert 4096 muss im Create-Call landen (nicht 2048 Lib-Default).
    assert client.messages.create.call_args.kwargs["max_tokens"] == 4096


def test_missing_usage_yields_none(jsonl_path):
    """Fehlt usage in der Lib-Antwort → GenerationResponse.usage None (wie
    claude.py: dann hängt _call_provider keinen ProviderCall an)."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response(
        [_text_block("Ok.")], usage=None)

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        resp = adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    assert resp.usage is None
