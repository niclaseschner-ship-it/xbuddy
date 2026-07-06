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


def test_get_agent_uses_explicit_model_not_default(jsonl_path):
    """`get_agent(slot, model="claude-opus-4-7")` reicht das Modell an den Vendor
    durch — der Create nutzt es statt des Vendor-DEFAULT_MODEL (T1085-Durchreich,
    eltern-chat-Verhalten erhalten)."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _response([_text_block("Hallo.")])

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="eltern-chat-anthropic-api-key", model="claude-opus-4-7")
        agent.step(system="S", messages=[{"role": "user", "content": "Hi"}], tools=TOOLS)

    assert client.messages.create.call_args.kwargs["model"] == "claude-opus-4-7"
    # Leeres Modell (Default) nutzt weiter den Vendor-DEFAULT_MODEL — Regress-Schutz.
    client.messages.create.reset_mock()
    client.messages.create.return_value = _response([_text_block("Hallo.")])
    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent_default = get_agent(slot="eltern-chat-anthropic-api-key")
        agent_default.step(system="S", messages=[{"role": "user", "content": "Hi"}], tools=TOOLS)
    from tools.llm._vendor.anthropic import DEFAULT_MODEL
    assert client.messages.create.call_args.kwargs["model"] == DEFAULT_MODEL


def _web_search_result_item(url, title, page_age=None):
    it = MagicMock()
    it.type = "web_search_result"
    it.url = url
    it.title = title
    it.page_age = page_age
    return it


def _web_search_result_block(items):
    b = MagicMock()
    b.type = "web_search_tool_result"
    b.content = items
    return b


# T1371: server-seitiges web_search-Tool (Anthropic-Infra) als tools-Array-Eintrag.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}


def test_step_extracts_web_search_results_and_count(jsonl_path):
    """T1371: `.step(...)` extrahiert additiv `web_search` (url/title/page_age)
    + `web_search_requests` (Anzahl der web_search_tool_result-Blöcke)."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _response([
        _web_search_result_block([
            _web_search_result_item("https://a/1", "Erste Quelle", "2 days"),
            _web_search_result_item("https://a/1", "Dup-URL", None),  # dedup
            _web_search_result_item("https://a/2", "Zweite Quelle"),
        ]),
        _text_block("- Fakt A (belegt)\n- Fakt B (belegt)"),
    ])

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="hoerspiel-anthropic-api-key")
        out = agent.step(
            system="Recherchiere.",
            messages=[{"role": "user", "content": "Quantencomputing Risiken"}],
            tools=[WEB_SEARCH_TOOL],
        )

    assert out["text"] == "- Fakt A (belegt)\n- Fakt B (belegt)"
    assert out["web_search_requests"] == 1
    assert out["web_search"] == [
        {"url": "https://a/1", "title": "Erste Quelle", "page_age": "2 days"},
        {"url": "https://a/2", "title": "Zweite Quelle", "page_age": None},
    ]


def test_step_server_tool_gets_no_cache_marker(jsonl_path):
    """T1371: der web_search-Server-Tool-Eintrag (`type`-Feld) bekommt KEINEN
    ephemeral-Cache-Marker (er ist keine Client-Tool-Definition)."""
    fake, client = _fake_anthropic()
    client.messages.create.return_value = _response([_text_block("- Fakt.")])

    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="hoerspiel-anthropic-api-key")
        agent.step(system="S", messages=[{"role": "user", "content": "x"}],
                   tools=[WEB_SEARCH_TOOL])

    sent_tools = client.messages.create.call_args.kwargs["tools"]
    assert "cache_control" not in sent_tools[-1]
    assert sent_tools[-1]["type"] == "web_search_20260209"


def test_get_agent_facade_exposes_web_search_capability(jsonl_path):
    """T1371: die get_agent-Fassade legt die Vendor-CAPABILITIES offen (opt-in
    Gate für den Rufer) — Anthropic deklariert `web_search`."""
    fake, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="hoerspiel-anthropic-api-key")
    assert "web_search" in agent.capabilities


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
