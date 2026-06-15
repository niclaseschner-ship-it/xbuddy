"""Test-Suite für kibuddy/providers/claude.py (KIBUDDY-14, KIBUDDY-28)."""

from unittest.mock import MagicMock, patch

import pytest

from kibuddy.providers.base import ProviderError


def _make_fake_block(text_content: str):
    block = MagicMock()
    block.type = "text"
    block.text = text_content
    return block


def _make_fake_response(text: str):
    resp = MagicMock()
    resp.content = [_make_fake_block(text)]
    return resp


def test_claude_complete_multiturn_happy_path():
    """KIBUDDY-14: complete_multiturn baut Nachrichten-Liste korrekt auf."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception

    fake_client.messages.create.return_value = _make_fake_response(
        "Wasser besteht aus H2O-Molekülen. Was denkst du, warum das wichtig ist?"
    )

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        from kibuddy.providers.claude import ClaudeProvider

        provider = ClaudeProvider(api_key="test-key", model="claude-haiku-4-5")
        result = provider.complete_multiturn(
            system="Du bist KIBuddy.",
            turns=[
                {"role": "user", "content": "Was ist Wasser?"},
                {"role": "assistant", "content": "Wasser ist eine Flüssigkeit."},
            ],
            user_message="Und woraus besteht es?",
        )

    assert "H2O" in result
    # Nachrichten-Liste: 2 History-Turns + 1 neue Frage = 3.
    call_args = fake_client.messages.create.call_args
    messages = call_args.kwargs["messages"]
    assert len(messages) == 3
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Und woraus besteht es?"


def test_claude_complete_multiturn_empty_history():
    """Ohne History wird genau 1 Message gesendet."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_response("Antwort.")

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        from kibuddy.providers.claude import ClaudeProvider

        provider = ClaudeProvider(api_key="test-key")
        provider.complete_multiturn("System.", [], "Frage?")

    messages = fake_client.messages.create.call_args.kwargs["messages"]
    assert len(messages) == 1


def test_claude_provider_error_on_api_error():
    """APIError → ProviderError."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = ValueError  # Simulator

    fake_client.messages.create.side_effect = ValueError("Verbindung getrennt")

    with patch.dict("sys.modules", {"anthropic": fake_anthropic}):
        from kibuddy.providers.claude import ClaudeProvider

        provider = ClaudeProvider(api_key="test-key")
        with pytest.raises(ProviderError):
            provider.complete_multiturn("S.", [], "F?")
