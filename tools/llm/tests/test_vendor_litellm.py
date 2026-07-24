"""Vendor-Tests für `tools/llm/_vendor/litellm.py` (LLMP-4, LLMP-S12, #1433).

Belegt:
  - AC1: CAPABILITIES-frozenset am Modulkopf, deckt REQUIRED_CHAT ab.
  - AC2: E2E-Chat-Pfad `get_chat('kibuddy-litellm-api-key').complete_multiturn(...)`
    mit gemocktem `litellm.completion` → Text zurück + GENAU EINE JSONL-Zeile
    (caller=kibuddy, LLMP-S4 Tier-2-Projektion), Usage OpenAI→intern gemappt,
    cache_control-Marker auf dem System-Block (LiteLLM-Passthrough).
  - AC3: singleshot/agent werfen NotImplementedError mit Slot-2/3-Hinweis.

`litellm` ist NICHT installiert → das SDK wird als MagicMock über sys.modules
eingehängt und `litellm.completion` gemockt (Spiegel test_chat_jsonl_endtoend,
das `anthropic` mockt). KEIN echter litellm-Call.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tools.llm import public_api
from tools.llm._vendor import litellm as litellm_vendor

# ----------------------------------------------------------------------
#  Fakes: OpenAI-förmige LiteLLM-Response + gemocktes litellm-SDK
# ----------------------------------------------------------------------


def _make_fake_litellm_response(text: str, *, prompt_tokens: int = 100,
                                completion_tokens: int = 50,
                                cache_read: int = 0,
                                cache_creation: int = 0):
    """Baut eine OpenAI-förmige LiteLLM-Response (`.choices[0].message.content`
    + `.usage` mit prompt/completion_tokens; Anthropic-Cache-Zahlen additiv)."""
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    resp.usage.cache_read_input_tokens = cache_read
    resp.usage.cache_creation_input_tokens = cache_creation
    return resp


def _make_fake_litellm_sdk(response=None, *, side_effect=None):
    """Gemocktes `litellm`-SDK: `.completion` + `.exceptions.APIError`."""
    fake = MagicMock()
    # litellm.exceptions.APIError als Basisklasse für die ProviderError-Übersetzung.
    fake.exceptions.APIError = _FakeAPIError
    if side_effect is not None:
        fake.completion.side_effect = side_effect
    else:
        fake.completion.return_value = response
    return fake


class _FakeAPIError(Exception):
    """Steht für `litellm.exceptions.APIError` im Test."""


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    """Lenkt `tools.llm.telemetry` auf `tmp_path` um (Test-Naht)."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


# ----------------------------------------------------------------------
#  AC1 — CAPABILITIES
# ----------------------------------------------------------------------


def test_capabilities_is_frozenset():
    """AC1: CAPABILITIES ist am Modulkopf als frozenset deklariert (LLMP-4)."""
    assert isinstance(litellm_vendor.CAPABILITIES, frozenset)
    assert litellm_vendor.CAPABILITIES  # nicht leer


def test_capabilities_covers_required_chat():
    """AC1: CAPABILITIES deckt MINDESTENS REQUIRED_CHAT ab (get_chat boot-fähig)."""
    assert public_api.REQUIRED_CHAT <= litellm_vendor.CAPABILITIES


def test_default_model_is_haiku():
    """AC1/AC4: Vendor-Default bleibt `claude-haiku-4-5` (like-for-like)."""
    assert litellm_vendor.DEFAULT_MODEL == "claude-haiku-4-5"


def test_vendor_class_name_matches_resolver_convention():
    """AC1: Klasse heißt `LitellmVendor` (public_api._vendor_class-Konvention)."""
    assert hasattr(litellm_vendor, "LitellmVendor")
    assert litellm_vendor.LitellmVendor.name == "litellm"


# ----------------------------------------------------------------------
#  AC2 — E2E-Chat-Pfad über die Fassade
# ----------------------------------------------------------------------


def test_chat_call_writes_single_jsonl_entry(jsonl_path):
    """AC2: `get_chat('kibuddy-litellm-api-key').complete_multiturn(...)` liefert
    Text zurück und schreibt GENAU EINE JSONL-Zeile mit caller=kibuddy."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_fake_litellm_response(
            "Wasser ist H2O. Was denkst du?",
            prompt_tokens=1234,
            completion_tokens=567,
            cache_read=8901,
            cache_creation=234,
        )
    )

    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        text = chat.complete_multiturn(
            system="Du bist KIBuddy.",
            turns=[{"role": "user", "content": "Was ist Wasser?"}],
            user_message="Und woraus besteht es?",
        )

    assert "H2O" in text

    assert jsonl_path.exists(), "JSONL wurde nicht geschrieben"
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "kibuddy"
    assert parsed["slot"] == "kibuddy-litellm-api-key"
    # OpenAI-Usage (prompt/completion) → internes input/output-Schema.
    assert parsed["input_tokens"] == 1234
    assert parsed["output_tokens"] == 567
    assert parsed["cache_read_tokens"] == 8901
    assert parsed["cache_creation_tokens"] == 234
    assert parsed["model_id"] == "claude-haiku-4-5"
    # Pricing: bekanntes Modell → est_cost_eur gesetzt (Hand-Telemetrie).
    assert parsed["est_cost_eur"] is not None
    assert isinstance(parsed["wall_ms"], int)
    assert parsed["wall_ms"] >= 0


def test_chat_call_routes_model_and_api_key(jsonl_path):
    """AC2: litellm.completion bekommt model=claude-haiku-4-5, api_key und die
    OpenAI-Message-Form (System als eigene Message)."""
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))

    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-real"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        chat.complete_multiturn(
            system="S.",
            turns=[{"role": "user", "content": "Frage 1"}],
            user_message="Frage 2",
        )

    call = fake_litellm.completion.call_args
    assert call.kwargs["model"] == "claude-haiku-4-5"
    assert call.kwargs["api_key"] == "sk-real"
    messages = call.kwargs["messages"]
    # System als eigene erste Message (system_message_distinct).
    assert messages[0]["role"] == "system"
    # turns + user_message dahinter.
    assert messages[1] == {"role": "user", "content": "Frage 1"}
    assert messages[-1] == {"role": "user", "content": "Frage 2"}


def test_chat_call_sets_cache_control_on_system_block(jsonl_path):
    """AC2/LLMP-S1: cache_control:ephemeral sitzt auf dem System-Content-Block
    (LiteLLM-Anthropic-Prompt-Caching-Passthrough)."""
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))

    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        chat.complete_multiturn(system="Du bist KIBuddy.", turns=[], user_message="F?")

    call = fake_litellm.completion.call_args
    system_msg = call.kwargs["messages"][0]
    assert system_msg["role"] == "system"
    assert isinstance(system_msg["content"], list)
    assert system_msg["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert system_msg["content"][0]["text"] == "Du bist KIBuddy."


def test_chat_call_with_correlation_id(jsonl_path):
    """AC2/LLMP-S4: optionales correlation_id landet in der JSONL."""
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))

    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        chat.complete_multiturn(
            system="S.", turns=[], user_message="F?",
            correlation_id="chat-xyz789",
        )

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["correlation_id"] == "chat-xyz789"


def test_chat_api_error_propagates_as_provider_error_no_jsonl(jsonl_path):
    """AC2: litellm.exceptions.APIError → ProviderError; KEIN JSONL (Fehler vor
    _emit_telemetry)."""
    fake_litellm = _make_fake_litellm_sdk(side_effect=_FakeAPIError("Verbindung tot"))

    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import ProviderError, get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        with pytest.raises(ProviderError):
            chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    assert not jsonl_path.exists()


def test_chat_call_missing_usage_still_writes_jsonl(jsonl_path):
    """AC2-Defensive: Response ohne `usage` → JSONL-Eintrag mit Token-Counts 0
    (gleiche Defensive wie anthropic-Vendor)."""
    resp = MagicMock()
    message = MagicMock()
    message.content = "ok"
    choice = MagicMock()
    choice.message = message
    resp.choices = [choice]
    resp.usage = None
    fake_litellm = _make_fake_litellm_sdk(resp)

    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["input_tokens"] == 0
    assert parsed["output_tokens"] == 0


# ----------------------------------------------------------------------
#  AC3 — Slot 2/3 nicht implementiert
# ----------------------------------------------------------------------


def _make_vendor():
    """Baut eine LitellmVendor-Instanz mit gemocktem litellm-SDK."""
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("x"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        return litellm_vendor.LitellmVendor(api_key="sk-fake")


def test_singleshot_structured_not_implemented():
    """AC3: singleshot_structured wirft NotImplementedError mit Slot-Hinweis."""
    vendor = _make_vendor()
    with pytest.raises(NotImplementedError) as exc:
        vendor.singleshot_structured("s", "p", {})
    assert "Slot 2/3" in str(exc.value) or "#1316" in str(exc.value)


def test_singleshot_text_not_implemented():
    """AC3: singleshot_text wirft NotImplementedError."""
    vendor = _make_vendor()
    with pytest.raises(NotImplementedError):
        vendor.singleshot_text("s", "u")


def test_agent_step_not_implemented():
    """AC3: agent_step wirft NotImplementedError."""
    vendor = _make_vendor()
    with pytest.raises(NotImplementedError):
        vendor.agent_step("s", [], [])
