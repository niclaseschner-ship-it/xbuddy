"""End-to-End-Test für KIBuddy-Migration (AC5, LLMP-S4, LLMP-S8).

Belegt, dass ein `get_chat(...).complete_multiturn(...)`-Call mit gemocktem
anthropic-SDK genau **einen** JSONL-Eintrag in `var/llm/provider_calls.jsonl`
schreibt — und zwar mit `caller="kibuddy"` (Tier-2-Projektion). Damit ist die
KIBuddy-Spike-Stufe-2-Vorprobe für T1082 in den Tests petrankert (LLMP-S7
Stufe-1-Fixture 3 „Multi-Turn-Chat").
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest


def _make_fake_anthropic_response(text: str, *, input_tokens: int = 100,
                                   output_tokens: int = 50,
                                   cache_read: int = 0,
                                   cache_creation: int = 0):
    """Baut eine SDK-ähnliche Response mit Text-Block + Usage-Counts."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    resp = MagicMock()
    resp.content = [block]
    resp.usage = MagicMock()
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    resp.usage.cache_read_input_tokens = cache_read
    resp.usage.cache_creation_input_tokens = cache_creation
    return resp


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    """Lenkt `tools.llm.telemetry` auf `tmp_path` um (Test-Naht)."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


def test_kibuddy_chat_call_writes_jsonl_entry(jsonl_path):
    """AC5: Ein `get_chat().complete_multiturn(...)`-Call schreibt einen
    JSONL-Eintrag mit `caller="kibuddy"` (LLMP-S4 Tier-2-Projektion)."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_anthropic_response(
        "Wasser ist H2O. Was denkst du?",
        input_tokens=1234,
        output_tokens=567,
        cache_read=8901,
        cache_creation=234,
    )

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        text = chat.complete_multiturn(
            system="Du bist KIBuddy.",
            turns=[{"role": "user", "content": "Was ist Wasser?"}],
            user_message="Und woraus besteht es?",
        )

    assert "H2O" in text

    # AC5: genau eine Zeile JSONL mit caller=kibuddy.
    assert jsonl_path.exists(), "JSONL wurde nicht geschrieben"
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "kibuddy"
    assert parsed["slot"] == "kibuddy-anthropic-api-key"
    assert parsed["input_tokens"] == 1234
    assert parsed["output_tokens"] == 567
    assert parsed["cache_read_tokens"] == 8901
    assert parsed["cache_creation_tokens"] == 234
    # Pricing: bekanntes Modell → est_cost_eur ist gesetzt.
    assert parsed["est_cost_eur"] is not None
    assert parsed["model_id"] == "claude-haiku-4-5"
    # `wall_ms` ist ein Integer und nicht negativ (gemockter Call → typisch sehr klein).
    assert isinstance(parsed["wall_ms"], int)
    assert parsed["wall_ms"] >= 0


def test_kibuddy_chat_call_with_correlation_id(jsonl_path):
    """LLMP-S4: optionales `correlation_id` (Caller-Sache, z. B. kibuddy=chat_id)
    landet im JSONL."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_anthropic_response("ok")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        chat.complete_multiturn(
            system="S.", turns=[], user_message="F?",
            correlation_id="chat-abc123",
        )

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["correlation_id"] == "chat-abc123"


def test_kibuddy_chat_passes_cache_control_on_system(jsonl_path):
    """LLMP-S1 `get_chat` Required: `cache_control` auf System-Block
    (Goldstandard `eltern-chat/providers/claude.py`-Pattern)."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_anthropic_response("ok")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        chat.complete_multiturn(system="Du bist KIBuddy.", turns=[], user_message="F?")

    call = fake_client.messages.create.call_args
    system_blocks = call.kwargs["system"]
    assert isinstance(system_blocks, list)
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_kibuddy_chat_provider_error_propagates_and_no_jsonl(jsonl_path):
    """SDK-Fehler → `ProviderError`; KEIN JSONL-Eintrag (Telemetrie nur bei Erfolg)."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = ValueError  # Simulator-Klasse
    fake_client.messages.create.side_effect = ValueError("Verbindung getrennt")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import ProviderError, get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        with pytest.raises(ProviderError):
            chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    # Bei Fehler vor `_emit_telemetry` → kein JSONL.
    assert not jsonl_path.exists()
