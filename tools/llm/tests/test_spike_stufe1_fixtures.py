"""Spike-Stufe-1-Fixtures (LLMP-S7): drei Sichten gegen denselben
`_vendor/anthropic.py`, ohne Netz, ohne Familien-Verkehr.

Belegt die Lego-Wiederholbarkeit der Vendor-Kern-These (LLMP-S1/LLMP-S7):
ein Vendor-File trägt Agent-Tool-Loop, Structured-Singleshot und Multi-Turn-
Chat. Mock-Naht identisch zu `test_chat_jsonl_endtoend.py`
(`patch.dict(sys.modules, {"anthropic": fake})` + `resolve_api_key`-Stub).

WICHTIG (Spike-Kill, AC4): dieser Lauf belegt FUNKTIONALE Wiederholbarkeit.
Das LOC-Kill-Kriterium (>30% Wachstum von `_vendor/anthropic.py`) ist im
Handoff separat gemessen und ausgelöst — die Tests sind grün, aber der
Vertrag ist NICHT merge-ready (siehe Handoff `loc_baseline_223_actual_now`).
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# ----------------------------------------------------------------------
#  Mock-Helfer — SDK-ähnliche Responses mit .type/.text bzw. tool_use
# ----------------------------------------------------------------------


def _usage(*, input_tokens=100, output_tokens=50, cache_read=0, cache_creation=0):
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
    """Lenkt `tools.llm.telemetry` auf `tmp_path` (Test-Naht, wie End-to-End)."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


# ----------------------------------------------------------------------
#  Fixture 1 — Agent-Tool-Loop (eltern-chat-ähnlich)
# ----------------------------------------------------------------------


def test_fixture1_agent_tool_loop_mid_turn_continuation(jsonl_path):
    """LLMP-S7 Fixture 1: `get_agent(...).run(...)` mit Tool-Definition,
    simuliertem `tool_use`-Block, Tool-Result-Rückgabe und zweitem Call
    (Mid-Turn-Continuation, multi_turn_assistant_prefill)."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception

    # Erster Call → tool_use, zweiter Call → finaler Text (side_effect-Sequenz).
    resp_tooluse = _response([_tool_use_block("wetter", {"ort": "Berlin"})])
    resp_final = _response([_text_block("In Berlin sind es 21 Grad.")])
    fake_client.messages.create.side_effect = [resp_tooluse, resp_final]

    tools = [{
        "name": "wetter",
        "description": "Liefert das aktuelle Wetter.",
        "input_schema": {
            "type": "object",
            "properties": {"ort": {"type": "string"}},
            "required": ["ort"],
        },
    }]

    seen = []

    def tool_runner(name, args):
        seen.append((name, args))
        return "21 Grad, sonnig"

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent(slot="eltern-chat-anthropic-api-key")
        result = agent.run(
            system="Du bist ein hilfreicher Assistent.",
            messages=[{"role": "user", "content": "Wie ist das Wetter in Berlin?"}],
            tools=tools,
            tool_runner=tool_runner,
            correlation_id="turn-xyz",
        )

    # Mid-Turn-Continuation: genau zwei Vendor-Calls.
    assert fake_client.messages.create.call_count == 2
    # tool_runner wurde mit Name + geparstem Input gerufen.
    assert seen == [("wetter", {"ort": "Berlin"})]
    # Finaler Text aus dem zweiten Call.
    assert result["text"] == "In Berlin sind es 21 Grad."

    # Zweiter Call trägt den Verlauf: assistant tool_use + user tool_result.
    second_call = fake_client.messages.create.call_args_list[1]
    convo = second_call.kwargs["messages"]
    roles = [m["role"] for m in convo]
    assert roles == ["user", "assistant", "user"]
    assert convo[1]["content"][0]["type"] == "tool_use"
    assert convo[2]["content"][0]["type"] == "tool_result"
    assert convo[2]["content"][0]["tool_use_id"] == "tu-1"
    # cache_control auf System + letztem Tool (Required: cache_control).
    assert second_call.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert second_call.kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}

    # Telemetrie: ein JSONL-Eintrag pro Vendor-Call (LLMP-S4) → zwei Zeilen.
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "eltern-chat"
    assert parsed["slot"] == "eltern-chat-anthropic-api-key"
    assert parsed["correlation_id"] == "turn-xyz"


# ----------------------------------------------------------------------
#  Fixture 2 — Structured-Singleshot (hoerspiel-ähnlich)
# ----------------------------------------------------------------------


def test_fixture2_structured_singleshot_forced_tool_use(jsonl_path):
    """LLMP-S7 Fixture 2: `get_singleshot(...).complete_structured(schema,
    prompt)` forced via tool_use, parst Schema-konformes Objekt
    {titel, untertitel, intro_kuerzel}."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception

    schema = {
        "type": "object",
        "properties": {
            "titel": {"type": "string"},
            "untertitel": {"type": "string"},
            "intro_kuerzel": {"type": "string"},
        },
        "required": ["titel", "untertitel", "intro_kuerzel"],
    }
    ergebnis = {
        "titel": "Die Höhle der Mutigen",
        "untertitel": "Eine Reise ins Dunkle",
        "intro_kuerzel": "HM01",
    }
    fake_client.messages.create.return_value = _response([
        _tool_use_block("ergebnis", ergebnis),
    ])

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key")
        out = ss.complete_structured(
            system="Du erfindest Hörspiel-Folgen.",
            prompt="Erfinde eine Folge über eine Höhle.",
            schema=schema,
        )

    # Schema-konformes Objekt aus dem tool_use-Block.
    assert out == ergebnis
    assert set(out.keys()) == {"titel", "untertitel", "intro_kuerzel"}

    # Forced tool_use: tool_choice gesetzt + input_schema durchgereicht.
    call = fake_client.messages.create.call_args
    assert call.kwargs["tool_choice"] == {"type": "tool", "name": "ergebnis"}
    assert call.kwargs["tools"][0]["input_schema"] == schema
    # Required: system_message_distinct + cache_control.
    assert call.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}

    # Telemetrie: genau ein Eintrag, caller=hoerspiel.
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "hoerspiel"
    assert parsed["slot"] == "hoerspiel-anthropic-api-key"


# ----------------------------------------------------------------------
#  Fixture 3 — Multi-Turn-Chat (kibuddy-ähnlich, Regression)
# ----------------------------------------------------------------------


def test_fixture3_multiturn_chat_regression(jsonl_path):
    """LLMP-S7 Fixture 3: `get_chat(...).complete_multiturn(...)` als
    Regression gegen dieselbe Vendor-Datei (System-Prompt + 3-Turn-History)."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _response([
        _text_block("Wasser besteht aus H2O. Was denkst du?"),
    ])

    history = [
        {"role": "user", "content": "Was ist Wasser?"},
        {"role": "assistant", "content": "Eine Flüssigkeit."},
        {"role": "user", "content": "Und chemisch?"},
    ]

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        text = chat.complete_multiturn(
            system="Du bist KIBuddy.",
            turns=history,
            user_message="Erklär es nochmal.",
        )

    assert "H2O" in text

    # System-Block mit cache_control + History durchgereicht.
    call = fake_client.messages.create.call_args
    assert call.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert len(call.kwargs["messages"]) == len(history) + 1

    # Telemetrie: genau ein Eintrag, caller=kibuddy.
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "kibuddy"
    assert parsed["slot"] == "kibuddy-anthropic-api-key"
