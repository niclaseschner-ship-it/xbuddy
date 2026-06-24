"""Mistral-Vendor (T1085, LLMP-S11) — ohne Netz.

(a) `get_agent("eltern-chat-mistral-api-key")` bootet ohne LLMCapabilityError
    (cache_control NICHT mehr Boot-Minimum, R0-Patch).
(b) Cap-Boot-Fail bleibt scharf bei echt fehlender Required-Cap.
(c) `.step(...)` gegen gemocktes httpx.post: text+tool_calls, tools→function-Form,
    image→image_url.
(d) JSONL-Telemetrie caller=eltern-chat.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


def _mistral_response(*, text="", tool_calls=None, prompt_tokens=80, completion_tokens=20):
    """Baut eine Mistral-Chat-Completions-JSON-Antwort."""
    message = {"content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def _fake_httpx(response_json, *, status_code=200):
    fake = MagicMock()
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = response_json
    resp.text = json.dumps(response_json)
    fake.post.return_value = resp
    fake.RequestError = Exception
    return fake


TOOLS = [{
    "name": "wetter",
    "description": "Liefert das aktuelle Wetter.",
    "input_schema": {
        "type": "object",
        "properties": {"ort": {"type": "string"}},
        "required": ["ort"],
    },
}]


def test_get_agent_mistral_boots_without_capability_error():
    """(a) Mistral-Slot bootet die Agent-Sicht ohne LLMCapabilityError —
    Mistral hat kein cache_control, aber das ist seit R0 nicht mehr nötig."""
    with patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="eltern-chat-mistral-api-key")
    assert agent.name == "agent"
    assert agent.model == "mistral-medium-2508"


def test_get_agent_mistral_cap_boot_fail_stays_sharp(monkeypatch):
    """(b) Wird einer Required-Cap (system_message_distinct) entzogen, bricht
    der Boot mit LLMCapabilityError — Cap-Gate bleibt scharf."""
    from tools.llm import _vendor
    from tools.llm._types import LLMCapabilityError
    mistral_mod = _vendor.mistral
    reduced = frozenset(mistral_mod.CAPABILITIES - {"system_message_distinct"})
    monkeypatch.setattr(mistral_mod, "CAPABILITIES", reduced)

    with patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_agent
        with pytest.raises(LLMCapabilityError):
            get_agent(slot="eltern-chat-mistral-api-key")


def test_step_translates_and_parses(jsonl_path):
    """(c) `.step(...)` gegen gemocktes httpx.post: text+tool_calls geparst,
    tools→function-Form, image→image_url; (d) JSONL caller=eltern-chat."""
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "wetter", "arguments": json.dumps({"ort": "Berlin"})},
    }
    fake_httpx = _fake_httpx(_mistral_response(text="Ich schaue.", tool_calls=[tool_call]))

    image_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "Wetter in Berlin?"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "ZZZ"}},
        ],
    }

    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="eltern-chat-mistral-api-key")
        out = agent.step(
            system="Du bist ein Assistent.",
            messages=[image_msg],
            tools=TOOLS,
            correlation_id="turn-9",
        )

    # Parse-Ergebnis (neutrale Form).
    assert out["text"] == "Ich schaue."
    assert out["tool_calls"] == [{"id": "call-1", "name": "wetter", "input": {"ort": "Berlin"}}]
    assert out["usage"] == {"prompt_tokens": 80, "completion_tokens": 20}

    # Payload-Übersetzung prüfen: genau ein POST.
    assert fake_httpx.post.call_count == 1
    sent = json.loads(fake_httpx.post.call_args.kwargs["content"])
    # System als eigene system-Message (system_message_distinct).
    assert sent["messages"][0] == {"role": "system", "content": "Du bist ein Assistent."}
    # tools → Mistral-function-Form.
    assert sent["tools"][0]["type"] == "function"
    assert sent["tools"][0]["function"]["name"] == "wetter"
    assert sent["tools"][0]["function"]["parameters"] == TOOLS[0]["input_schema"]
    # image → image_url (data-URL).
    user_content = sent["messages"][1]["content"]
    image_part = next(p for p in user_content if p["type"] == "image_url")
    assert image_part["image_url"]["url"] == "data:image/png;base64,ZZZ"

    # (d) JSONL: ein Eintrag, caller=eltern-chat, est_cost_eur gesetzt.
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "eltern-chat"
    assert parsed["slot"] == "eltern-chat-mistral-api-key"
    assert parsed["model_id"] == "mistral-medium-2508"
    assert parsed["input_tokens"] == 80
    assert parsed["output_tokens"] == 20
    assert parsed["cache_read_tokens"] == 0
    assert parsed["est_cost_eur"] is not None


def test_agent_run_loops_over_step(jsonl_path):
    """agent_run nutzt agent_step pro Iteration und führt den Tool-Loop:
    erster POST → tool_call, zweiter POST → finaler Text."""
    tool_call = {
        "id": "call-1",
        "type": "function",
        "function": {"name": "wetter", "arguments": json.dumps({"ort": "Berlin"})},
    }
    resp1 = _mistral_response(text="", tool_calls=[tool_call])
    resp2 = _mistral_response(text="In Berlin 21 Grad.")

    fake_httpx = MagicMock()
    fake_httpx.RequestError = Exception
    r1, r2 = MagicMock(), MagicMock()
    for r, data in ((r1, resp1), (r2, resp2)):
        r.status_code = 200
        r.json.return_value = data
        r.text = json.dumps(data)
    fake_httpx.post.side_effect = [r1, r2]

    seen = []

    def tool_runner(name, args):
        seen.append((name, args))
        return "21 Grad"

    with patch.dict(sys.modules, {"httpx": fake_httpx}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="eltern-chat-mistral-api-key")
        result = agent.run(
            system="S",
            messages=[{"role": "user", "content": "Wetter?"}],
            tools=TOOLS,
            tool_runner=tool_runner,
        )

    assert fake_httpx.post.call_count == 2
    assert seen == [("wetter", {"ort": "Berlin"})]
    assert result["text"] == "In Berlin 21 Grad."
    # Zweiter POST trägt assistant-tool_calls + tool-Result-Message.
    sent2 = json.loads(fake_httpx.post.call_args_list[1].kwargs["content"])
    roles = [m["role"] for m in sent2["messages"]]
    assert "assistant" in roles
    assert "tool" in roles
    # Zwei JSONL-Einträge (ein Telemetrie-Schreiben pro Create).
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
