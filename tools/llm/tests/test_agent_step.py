"""Single-Turn-`agent_step` (T1085, LLMP-S11): Anthropic-`.step(...)` liefert
text+tool_calls+usage OHNE Tools auszuführen, setzt 2× ephemeral, schreibt EINEN
JSONL-Eintrag. Plus: `agent_run` mit dict-`tool_runner` setzt is_error auf den
tool_result-Block (additive Härtung, ohne test_fixture1 zu brechen).

Mock-Naht identisch zu `test_spike_stufe1_fixtures.py`
(`patch.dict(sys.modules, {"anthropic": fake})` + `resolve_api_key`-Stub).
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest


def _usage(*, input_tokens=120, output_tokens=40, cache_read=0, cache_creation=0):
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


def _response(blocks):
    resp = MagicMock()
    resp.content = blocks
    resp.usage = _usage()
    return resp


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


def _fake_anthropic():
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception
    return fake, client


TOOLS = [{
    "name": "wetter",
    "description": "Liefert das aktuelle Wetter.",
    "input_schema": {
        "type": "object",
        "properties": {"ort": {"type": "string"}},
        "required": ["ort"],
    },
}]


def test_step_single_turn_parses_without_running_tools(jsonl_path):
    """`.step(...)` macht EINEN Create, parst text+tool_calls+usage und führt
    KEINE Tools aus (kein tool_runner-Argument); 2× ephemeral; ein JSONL."""
    fake, client = _fake_anthropic()
    # Antwort mit Text UND tool_use — step soll beides parsen, nichts ausführen.
    client.messages.create.return_value = _response([
        _text_block("Ich schaue nach."),
        _tool_use_block("wetter", {"ort": "Berlin"}),
    ])

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="eltern-chat-anthropic-api-key")
        out = agent.step(
            system="Du bist ein Assistent.",
            messages=[{"role": "user", "content": "Wetter in Berlin?"}],
            tools=TOOLS,
            correlation_id="turn-1",
        )

    # Genau ein Create (kein interner Loop).
    assert client.messages.create.call_count == 1
    assert out["text"] == "Ich schaue nach."
    assert out["tool_calls"] == [{"id": "tu-1", "name": "wetter", "input": {"ort": "Berlin"}}]
    assert out["usage"] is not None
    assert out["usage"].input_tokens == 120

    # 2× ephemeral: System-Block + letzter Tool.
    call = client.messages.create.call_args
    assert call.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call.kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}

    # Ein JSONL-Eintrag, caller=eltern-chat.
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "eltern-chat"
    assert parsed["slot"] == "eltern-chat-anthropic-api-key"
    assert parsed["correlation_id"] == "turn-1"


def test_step_passes_image_block_through_unmodified(jsonl_path):
    """Bild-Input: `messages` mit image-Block wird unverändert durchgereicht
    (nicht gestrippt)."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _response([_text_block("Ein Hund.")])

    image_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "Was ist das?"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
        ],
    }

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="eltern-chat-anthropic-api-key")
        agent.step(system="S", messages=[image_msg], tools=TOOLS)

    sent = client.messages.create.call_args.kwargs["messages"]
    assert sent[0]["content"][1]["type"] == "image"
    assert sent[0]["content"][1]["source"]["data"] == "AAAA"


def test_agent_run_sets_is_error_on_tool_result_block(jsonl_path):
    """`agent_run` mit dict-tool_runner {content, is_error} setzt is_error auf
    den tool_result-Block; String-Runner bleibt rückwärtskompatibel (kein Flag)."""
    fake, client = _fake_anthropic()
    resp_tooluse = _response([_tool_use_block("wetter", {"ort": "Berlin"})])
    resp_final = _response([_text_block("Fertig.")])
    client.messages.create.side_effect = [resp_tooluse, resp_final]

    def tool_runner(name, args):
        return {"content": "Sensor offline", "is_error": True}

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="eltern-chat-anthropic-api-key")
        agent.run(
            system="S",
            messages=[{"role": "user", "content": "Wetter?"}],
            tools=TOOLS,
            tool_runner=tool_runner,
        )

    second_call = client.messages.create.call_args_list[1]
    tool_result = second_call.kwargs["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["content"] == "Sensor offline"
    assert tool_result["is_error"] is True
