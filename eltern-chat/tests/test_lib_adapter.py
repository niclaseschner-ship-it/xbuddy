"""LibAgentAdapter — eltern-chat-Chat-Agent über `tools.llm` (T1085 / #1452).

Deckt den `generate(GenerationRequest) -> GenerationResponse`-Vertrag des
Lib-Adapters ab: kanonisch → neutrale (Anthropic-shaped) Wire-Form → OpenAI
(im litellm-Vendor), die neutrale Antwort → kanonisch, usage → ProviderUsage
(SQLite-Pfad EC-23), die JSONL-Doppelschreibung der Lib (caller=eltern-chat,
correlation_id=turn_id), Slot-Wahl und ProviderError-Mapping (tools.llm →
model).

Slot 2 (#1449/#1452): der Agent-Pfad fährt jetzt fest über den litellm-Motor
(Slot `eltern-chat-litellm-api-key`), NICHT mehr über den brand-spezifischen
`eltern-chat-<vendor>-api-key`. Das effektive Modell bleibt `claude-opus-4-7`
(Alt-Default, EC-15). Darum wird hier das `litellm`-SDK gemockt (nicht mehr
`anthropic`/`httpx`).

Mock-Naht: das litellm-SDK wird über `patch.dict(sys.modules, {"litellm": …})`
ersetzt (kein Netz), `tools.llm.public_api.resolve_api_key` wird gestubt
(kein echter Key nötig). `XBUDDY_DATA_DIR` lenkt die JSONL-Datei auf `tmp_path`
(die autouse-conftest-Fixture isoliert nur den ZD-Store).
"""

import json
import sys
from types import SimpleNamespace
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
#  Fakes — LiteLLM-SDK (OpenAI-förmige ModelResponse)
# ----------------------------------------------------------------------


class _FakeAPIError(Exception):
    """Steht für `litellm.exceptions.APIError` im Test."""


def _litellm_usage(*, prompt_tokens=120, completion_tokens=40,
                   cache_read=5, cache_creation=7):
    # SimpleNamespace (nicht MagicMock): so trägt das Usage-Objekt AUSSCHLIESSLICH
    # die OpenAI-förmigen Felder (prompt/completion), KEIN auto-attributiertes
    # `input_tokens` — der Adapter-getattr-Fallback (input_tokens → prompt_tokens)
    # wird damit real geprüft (Spiegel des echten LiteLLM-Pydantic-Usage-Objekts).
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )


_NO_USAGE = object()


def _litellm_response(text, *, tool_calls=None, usage=_NO_USAGE):
    """OpenAI-förmige LiteLLM-ModelResponse: `.choices[0].message` mit
    `.content` + `.tool_calls[i].{id, function.{name, arguments}}`."""
    message = MagicMock()
    message.content = text
    tc_objs = []
    for tc in tool_calls or []:
        tc_obj = MagicMock()
        tc_obj.id = tc["id"]
        fn = MagicMock()
        fn.name = tc["name"]
        fn.arguments = tc["arguments"]
        tc_obj.function = fn
        tc_objs.append(tc_obj)
    message.tool_calls = tc_objs
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = _litellm_usage() if usage is _NO_USAGE else usage
    return resp


def _fake_litellm(response=None, *, side_effect=None):
    fake = MagicMock()
    fake.exceptions.APIError = _FakeAPIError
    if side_effect is not None:
        fake.completion.side_effect = side_effect
    else:
        fake.completion.return_value = response
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
#  Slot + effektives Modell (litellm-Motor, #1452)
# ----------------------------------------------------------------------


def test_slot_is_litellm_and_effective_model_opus(jsonl_path):
    """provider='claude' fährt jetzt fest über Slot eltern-chat-litellm-api-key;
    leeres provider_model → effektives Modell claude-opus-4-7 (Alt-Default)."""
    fake = _fake_litellm(_litellm_response("Hallo."))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    # Effektives Modell = opus-4-7 (LiteLLM routet auf Anthropic).
    assert fake.completion.call_args.kwargs["model"] == "claude-opus-4-7"
    # Slot landet im JSONL als eltern-chat-litellm-api-key.
    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert line["slot"] == "eltern-chat-litellm-api-key"
    assert line["caller"] == "eltern-chat"


def test_tool_use_roundtrip_and_usage(jsonl_path):
    """tool_call-Antwort → TaskCallBlock; LiteLLM-usage (prompt/completion +
    Cache) → ProviderUsage (SQLite-Pfad EC-23). Plus: Doppelschreibung — usage
    gefüllt UND ein JSONL-Eintrag mit correlation_id=turn_id."""
    fake = _fake_litellm(_litellm_response(
        "Ich schaue.",
        tool_calls=[{"id": "call-7", "name": "wetter",
                     "arguments": '{"ort": "Berlin"}'}],
    ))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        resp = adapter.generate(_request(
            [Message(role="user", blocks=[TextBlock("Wetter?")])],
            correlation_id="turn-42"))

    # tool_call → kanonischer TaskCallBlock.
    assert resp.text == "Ich schaue."
    assert len(resp.task_calls) == 1
    assert isinstance(resp.task_calls[0], TaskCallBlock)
    assert resp.task_calls[0].call_id == "call-7"
    assert resp.task_calls[0].task == "wetter"
    assert resp.task_calls[0].arguments == {"ort": "Berlin"}

    # EC-23 SQLite-Pfad: usage aus dem LiteLLM-RAW-Objekt (prompt/completion +
    # Cache-Felder gemappt).
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


def test_image_and_tool_result_to_wire(jsonl_path):
    """ImageBlock → OpenAI image_url data-URL; TaskResultBlock mit is_error
    → {role:tool, tool_call_id, content:'[FEHLER] …'} in der OpenAI-Wire-Form."""
    fake = _fake_litellm(_litellm_response("Ein Hund."))

    messages = [
        Message(role="user", blocks=[
            TextBlock("Was ist das?"),
            ImageBlock(media_type="image/png", data_b64="AAAA"),
        ]),
        Message(role="user", blocks=[
            TaskResultBlock(call_id="call-1", content="Sensor offline", is_error=True),
        ]),
    ]

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request(messages))

    sent = fake.completion.call_args.kwargs["messages"]
    # sent[0] ist die System-Message (cache_control). Danach die User-Blöcke.
    assert sent[0]["role"] == "system"
    # ImageBlock → OpenAI image_url data-URL (text + image als content-parts).
    user_parts = sent[1]["content"]
    img = next(p for p in user_parts if p.get("type") == "image_url")
    assert img["image_url"]["url"] == "data:image/png;base64,AAAA"
    # TaskResultBlock mit is_error → tool-Message mit [FEHLER]-Prefix.
    tr = sent[2]
    assert tr["role"] == "tool"
    assert tr["tool_call_id"] == "call-1"
    assert tr["content"] == "[FEHLER] Sensor offline"


def test_explicit_provider_model_overrides_default(jsonl_path):
    """Konfiguriertes provider_model schlägt den Anbieter-Default (durchgereicht
    an die Lib → litellm.completion)."""
    fake = _fake_litellm(_litellm_response("Ok."))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="claude-sonnet-4-5")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    assert fake.completion.call_args.kwargs["model"] == "claude-sonnet-4-5"


def test_lib_provider_error_maps_to_model_provider_error(jsonl_path):
    """tools.llm.ProviderError aus dem .step()-Call → model.ProviderError
    (run_turn._call_provider fängt model.ProviderError, EC-14)."""
    fake = _fake_litellm(side_effect=_FakeAPIError("boom"))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        with pytest.raises(ProviderError):
            adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))


def test_cache_control_on_system_block(jsonl_path):
    """AC4: der System-Prompt trägt cache_control:ephemeral als eigene
    OpenAI-Message (Kosten-Parität zum Alt-eltern-chat-Pfad)."""
    fake = _fake_litellm(_litellm_response("Ok."))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request(
            [Message(role="user", blocks=[TextBlock("Hi")])],
            system="Du bist ein Assistent."))

    system_msg = fake.completion.call_args.kwargs["messages"][0]
    assert system_msg["role"] == "system"
    assert system_msg["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert system_msg["content"][0]["text"] == "Du bist ein Assistent."


# ----------------------------------------------------------------------
#  max_tokens-Durchreichung (T1129)
# ----------------------------------------------------------------------


def test_lib_adapter_passes_max_tokens_4096_to_vendor(jsonl_path):
    """LibAgentAdapter reicht max_tokens=4096 (Alt-Wert claude.py:32) an den
    litellm-Vendor durch — litellm.completion wird mit max_tokens=4096 gerufen."""
    fake = _fake_litellm(_litellm_response("Ok."))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    assert fake.completion.call_args.kwargs["max_tokens"] == 4096


def test_missing_usage_yields_none(jsonl_path):
    """Fehlt usage in der Lib-Antwort → GenerationResponse.usage None (wie
    claude.py: dann hängt _call_provider keinen ProviderCall an)."""
    fake = _fake_litellm(_litellm_response("Ok.", usage=None))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        resp = adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    assert resp.usage is None
