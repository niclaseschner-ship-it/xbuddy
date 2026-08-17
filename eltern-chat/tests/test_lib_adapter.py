"""LibAgentAdapter — eltern-chat-Chat-Agent über `tools.llm` (T1085, #1463).

Deckt den `generate(GenerationRequest) -> GenerationResponse`-Vertrag des
Lib-Adapters ab: kanonisch → neutrale (Anthropic-shaped) Wire-Form, die
LiteLLM-OpenAI-usage → ProviderUsage (SQLite-Pfad EC-23), die JSONL-
Doppelschreibung der Lib (caller=eltern-chat, correlation_id=turn_id), die
anbieter-benannte litellm-Slot-Wahl (LLMP-S13: claude→eltern-chat-litellm-claude,
mistral→eltern-chat-litellm-eu), ProviderError-Mapping (tools.llm → model) und
das effektive Modell.

Seit #1463 (LLMP-S13) fährt der eltern-chat-Agent über den litellm-Motor. Die
Mock-Naht ist darum das `litellm`-SDK (nicht mehr anthropic/httpx): es wird über
`patch.dict(sys.modules, {"litellm": …})` als MagicMock eingehängt (kein Netz),
`tools.llm.public_api.resolve_api_key` wird gestubt (kein echter Key nötig).
`XBUDDY_DATA_DIR` lenkt die JSONL-Datei auf `tmp_path`.

AC3 (#1463): `test_mistral_provider_prefixes_model_at_litellm` beweist an der
litellm-Grenze — NICHT weggemockt —, dass provider=mistral ein `mistral/`-
präfixiertes Modell an `litellm.completion` gibt (die Naht, die #1452 live erst
brach).
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
#  Fakes — LiteLLM-SDK (OpenAI-förmige ModelResponse)
# ----------------------------------------------------------------------


class _FakeAPIError(Exception):
    """Steht für `litellm.exceptions.APIError` im Test."""


_NO_USAGE = object()


def _litellm_usage(*, prompt_tokens=120, completion_tokens=40, cache_read=5,
                   cache_creation=7):
    """LiteLLM-OpenAI-Usage: `prompt_tokens`/`completion_tokens` (+ Anthropic-Cache-
    Passthrough). `input_tokens`/`output_tokens` fehlen bewusst (None), damit der
    Adapter-getattr-Zweig auf die OpenAI-Namen zurückfällt (echte LiteLLM-Usage-
    Objekte tragen die Anthropic-Namen nicht)."""
    u = MagicMock()
    u.input_tokens = None
    u.output_tokens = None
    u.prompt_tokens = prompt_tokens
    u.completion_tokens = completion_tokens
    u.cache_read_input_tokens = cache_read
    u.cache_creation_input_tokens = cache_creation
    return u


def _tool_call(name, arguments_json, call_id="tc-1"):
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments_json
    return tc


def _litellm_response(text, *, tool_calls=None, usage=_NO_USAGE):
    """OpenAI-förmige LiteLLM-`ModelResponse`: `.choices[0].message.content`
    (+ `.tool_calls`) und `.usage` (getattr-Zugriff wie im litellm-Vendor)."""
    message = MagicMock()
    message.content = text
    message.tool_calls = tool_calls or []
    choice = MagicMock()
    choice.message = message

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = _litellm_usage() if usage is _NO_USAGE else usage
    return resp


def _fake_litellm(response=None, *, side_effect=None):
    """Gemocktes `litellm`-SDK: `.completion` + `.exceptions.APIError`."""
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
#  Claude-Pfad (litellm-Motor, Claude-Slot)
# ----------------------------------------------------------------------


def test_claude_slot_and_effective_model_opus(jsonl_path):
    """provider='claude' wählt Slot eltern-chat-litellm-claude-api-key (LLMP-S13);
    leeres provider_model → effektives Modell claude-opus-5 (Vendor-Default,
    T1807; blank an litellm — litellm erkennt Claude ohne Präfix)."""
    fake = _fake_litellm(_litellm_response("Hallo."))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    # Effektives Modell = opus-5 (blank, kein Präfix für Claude).
    assert fake.completion.call_args.kwargs["model"] == "claude-opus-5"
    # Slot landet im JSONL als anbieter-benannter litellm-Claude-Slot.
    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert line["slot"] == "eltern-chat-litellm-claude-api-key"
    assert line["caller"] == "eltern-chat"


def test_claude_tool_use_roundtrip_and_usage(jsonl_path):
    """tool_use-Antwort → TaskCallBlock; LiteLLM-usage (prompt/completion + cache)
    → ProviderUsage (SQLite-Pfad EC-23). Plus: Doppelschreibung — usage gefüllt
    UND ein JSONL-Eintrag mit correlation_id=turn_id."""
    fake = _fake_litellm(_litellm_response(
        "Ich schaue.",
        tool_calls=[_tool_call("wetter", '{"ort": "Berlin"}', call_id="call-7")],
    ))

    with patch.dict(sys.modules, {"litellm": fake}), \
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

    # EC-23 SQLite-Pfad: usage gefüllt aus LiteLLM-Objekt (cache-Felder gemappt).
    assert resp.usage is not None
    assert resp.usage.input_tokens == 120
    assert resp.usage.output_tokens == 40
    assert resp.usage.cache_read_tokens == 5
    assert resp.usage.cache_creation_tokens == 7
    assert resp.usage.model_id == "claude-opus-5"

    # JSONL-Doppelschreibung mit correlation_id=turn_id.
    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert line["correlation_id"] == "turn-42"
    assert line["input_tokens"] == 120
    assert line["model_id"] == "claude-opus-5"


def test_claude_image_and_tool_result_to_wire(jsonl_path):
    """ImageBlock → OpenAI image_url-part; TaskResultBlock mit is_error →
    {"role":"tool", …, "[FEHLER] …"} in der litellm-Wire-Form."""
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
    # System als eigene erste Message (system_message_distinct), dann der User-Turn.
    assert sent[0]["role"] == "system"
    # ImageBlock → OpenAI image_url-content-part.
    img_parts = sent[1]["content"]
    img = next(p for p in img_parts if p.get("type") == "image_url")
    assert img["image_url"]["url"] == "data:image/png;base64,AAAA"
    # TaskResultBlock mit is_error → tool-Nachricht mit [FEHLER]-Prefix.
    tool_msg = next(m for m in sent if m.get("role") == "tool")
    assert tool_msg["tool_call_id"] == "call-1"
    assert tool_msg["content"] == "[FEHLER] Sensor offline"


def test_claude_explicit_provider_model_overrides_default(jsonl_path):
    """Konfiguriertes provider_model schlägt den Anbieter-Default (Verhalten
    erhalten: provider_model durchgereicht, blank für Claude)."""
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


# ----------------------------------------------------------------------
#  Mistral-Pfad (litellm-Motor, EU-Slot, mistral/-Präfix — AC2 + AC3)
# ----------------------------------------------------------------------


def test_mistral_slot_usage_and_default_model(jsonl_path):
    """provider='mistral' wählt Slot eltern-chat-litellm-eu-api-key (LLMP-S13,
    anbieter-benannt, purpose OHNE Vendor-Slug); LiteLLM-usage → ProviderUsage;
    leeres provider_model → mistral-medium-2508 (Alt-Adapter-Default)."""
    fake = _fake_litellm(_litellm_response(
        "Servus.",
        tool_calls=[_tool_call("wetter", '{"ort": "Wien"}', call_id="mc-1")],
        usage=_litellm_usage(prompt_tokens=200, completion_tokens=30,
                             cache_read=0, cache_creation=0),
    ))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-mistral"):
        adapter = LibAgentAdapter(provider="mistral", provider_model="")
        resp = adapter.generate(_request(
            [Message(role="user", blocks=[TextBlock("Wetter?")])],
            correlation_id="turn-99"))

    # tool_call → kanonischer TaskCallBlock (Args geparst).
    assert resp.text == "Servus."
    assert resp.task_calls[0].task == "wetter"
    assert resp.task_calls[0].arguments == {"ort": "Wien"}

    # usage → ProviderUsage (cache=0, model_id = blanker Mistral-Default —
    # `_model` bleibt blank; das Präfix ergänzt nur die litellm-Grenze).
    assert resp.usage is not None
    assert resp.usage.input_tokens == 200
    assert resp.usage.output_tokens == 30
    assert resp.usage.cache_read_tokens == 0
    assert resp.usage.cache_creation_tokens == 0
    assert resp.usage.model_id == "mistral-medium-2508"

    # JSONL: caller=eltern-chat, Slot = anbieter-benannter EU-litellm-Slot.
    line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert line["caller"] == "eltern-chat"
    assert line["slot"] == "eltern-chat-litellm-eu-api-key"
    assert line["correlation_id"] == "turn-99"


def test_mistral_provider_prefixes_model_at_litellm(jsonl_path):
    """AC3 (#1463): provider=mistral gibt ein `mistral/`-präfixiertes Modell an
    `litellm.completion` — die Naht, die #1452 live erst brach (`LLM Provider NOT
    provided`). Diese Grenze wird NICHT weggemockt: `litellm.completion` selbst
    ist der Mock, und wir lesen sein `model`-kwarg."""
    fake = _fake_litellm(_litellm_response("Ok."))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-mistral"):
        adapter = LibAgentAdapter(provider="mistral", provider_model="")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    # Blanker Default `mistral-medium-2508` → zentral zu `mistral/…` normalisiert.
    assert fake.completion.call_args.kwargs["model"] == "mistral/mistral-medium-2508"


def test_mistral_explicit_model_also_prefixed(jsonl_path):
    """AC3: auch ein explizit konfiguriertes blankes Mistral-Modell wird an der
    litellm-Grenze präfixiert (die Normalisierung greift auf dem Modellnamen,
    nicht nur auf dem Default)."""
    fake = _fake_litellm(_litellm_response("Ok."))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-mistral"):
        adapter = LibAgentAdapter(provider="mistral", provider_model="mistral-large-2411")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    assert fake.completion.call_args.kwargs["model"] == "mistral/mistral-large-2411"


# ----------------------------------------------------------------------
#  max_tokens-Durchreichung (T1129)
# ----------------------------------------------------------------------


def test_lib_adapter_passes_max_tokens_8192_to_vendor(jsonl_path):
    """LibAgentAdapter reicht max_tokens=8192 an den litellm-Motor durch —
    completion wird mit max_tokens=8192 gerufen. Angehoben von 4096 (T1807,
    gemessen: claude-opus-5 lässt auf diesem `tool_choice`="auto"-Pfad
    automatisches Thinking zu, das denselben Topf wie der Antworttext teilt)."""
    fake = _fake_litellm(_litellm_response("Ok."))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    assert fake.completion.call_args.kwargs["max_tokens"] == 8192


def test_missing_usage_yields_none(jsonl_path):
    """Fehlt usage in der Lib-Antwort → GenerationResponse.usage None (wie
    claude.py: dann hängt _call_provider keinen ProviderCall an)."""
    fake = _fake_litellm(_litellm_response("Ok.", usage=None))

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        adapter = LibAgentAdapter(provider="claude", provider_model="")
        resp = adapter.generate(_request([Message(role="user", blocks=[TextBlock("Hi")])]))

    assert resp.usage is None
