"""Vendor-Tests für `tools/llm/_vendor/litellm.py` (LLMP-4, LLMP-S12, #1433).

Belegt:
  - AC1: CAPABILITIES-frozenset am Modulkopf, deckt REQUIRED_CHAT ab.
  - AC2: E2E-Chat-Pfad `get_chat('kibuddy-litellm-api-key').complete_multiturn(...)`
    mit gemocktem `litellm.completion` → Text zurück + GENAU EINE JSONL-Zeile
    (caller=kibuddy, LLMP-S4 Tier-2-Projektion), Usage OpenAI→intern gemappt,
    cache_control-Marker auf dem System-Block (LiteLLM-Passthrough).
  - AC3: agent_step ist migriert (Slot 2, #1452) — Wire-Übersetzung, Parse,
    is_error-Prefix, JSONL, Loop-E2E. Slot 3 (#1454): singleshot_structured
    (forced tool_choice named form) + singleshot_text (Freitext) migriert,
    CAPABILITIES ⊇ REQUIRED_SINGLESHOT/COMPLETION.

`litellm` ist NICHT installiert → das SDK wird als MagicMock über sys.modules
eingehängt und `litellm.completion` gemockt (Spiegel test_chat_jsonl_endtoend,
das `anthropic` mockt). KEIN echter litellm-Call.
"""

import json
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from tools.llm import (
    LLM_TIMEOUT_LONGFORM_SECONDS,
    LLM_TIMEOUT_SECONDS,
    LLMTimeoutError,
    ProviderError,
    public_api,
)
from tools.llm._vendor import litellm as litellm_vendor

# ----------------------------------------------------------------------
#  Fakes: OpenAI-förmige LiteLLM-Response + gemocktes litellm-SDK
# ----------------------------------------------------------------------


def _make_fake_litellm_response(text: str, *, prompt_tokens: int = 100,
                                completion_tokens: int = 50,
                                cache_read: int = 0,
                                cache_creation: int = 0,
                                response_cost: float | None = None):
    """Baut eine OpenAI-förmige LiteLLM-Response (`.choices[0].message.content`
    + `.usage` mit prompt/completion_tokens; Anthropic-Cache-Zahlen additiv).

    `response_cost` (USD) wird als `_hidden_params`-dict mitgegeben wenn gesetzt
    — Naht #1635: `_litellm_response_cost_eur` liest es zuerst.
    """
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
    # _hidden_params als echtes dict (kein MagicMock) → Naht liest ihn korrekt.
    resp._hidden_params = {"response_cost": response_cost} if response_cost is not None else {}
    return resp


def _make_fake_litellm_sdk(response=None, *, side_effect=None,
                            completion_cost_return: float | None = None):
    """Gemocktes `litellm`-SDK: `.completion` + `.exceptions.APIError` + `.completion_cost`.

    `completion_cost_return` steuert den Fallback-Pfad von `_litellm_response_cost_eur`
    (#1635) — None (default) lässt `completion_cost()` einen TypeError werfen
    (wie ein echter MagicMock ohne Return-Wert-Konfiguration würde), 0.0 testet
    den 0-Pfad, > 0 testet den Fallback-Erfolg-Pfad.
    """
    fake = MagicMock()
    # litellm.exceptions.APIError als Basisklasse für die ProviderError-Übersetzung.
    fake.exceptions.APIError = _FakeAPIError
    # #1784: `litellm.exceptions.Timeout` als eigene, von APIError UNABHÄNGIGE
    # Klasse — genau wie im echten SDK (dort erbt Timeout von
    # openai.APITimeoutError, nicht von litellm.exceptions.APIError). Damit
    # beweist der Timeout-Test, dass der Vendor ihn eigens fängt und nicht
    # zufällig über den APIError-Zweig einsammelt.
    fake.exceptions.Timeout = _FakeTimeout
    if side_effect is not None:
        fake.completion.side_effect = side_effect
    else:
        fake.completion.return_value = response
    # completion_cost-Fallback: None → wirft TypeError (unerwartet), sonst float.
    if completion_cost_return is None:
        fake.completion_cost.side_effect = TypeError("mock: kein completion_cost")
    else:
        fake.completion_cost.return_value = completion_cost_return
    return fake


class _FakeAPIError(Exception):
    """Steht für `litellm.exceptions.APIError` im Test."""


class _FakeTimeout(Exception):
    """Steht für `litellm.exceptions.Timeout` im Test (#1784).

    BEWUSST keine Subklasse von `_FakeAPIError` — spiegelt die echte
    SDK-Hierarchie (litellm-Timeout erbt von `openai.APITimeoutError`, nicht von
    `litellm.exceptions.APIError`). Ein Vendor, der nur `except APIError` fährt,
    lässt ihn durch; genau das prüfen die Tests unten.
    """


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
            response_cost=0.01,  # LiteLLM-native Kosten (USD, Naht #1635)
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
    # Pricing: LiteLLM-native response_cost=0.01 USD → 0.01 * 0.92 EUR (#1635).
    assert parsed["est_cost_eur"] is not None
    assert parsed["est_cost_eur"] == pytest.approx(0.01 * 0.92)
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


# ----------------------------------------------------------------------
#  Slot 3 (#1454) — singleshot_structured + singleshot_text
# ----------------------------------------------------------------------


def _make_singleshot_response(*, tool_calls=None, content=None,
                              prompt_tokens=100, completion_tokens=50):
    """OpenAI-förmige LiteLLM-ModelResponse für singleshot: `.choices[0].message`
    mit `.tool_calls[i].function.{name, arguments}` (structured) bzw. `.content`
    (text)."""
    message = MagicMock()
    message.content = content
    tc_objs = []
    for tc in tool_calls or []:
        tc_obj = MagicMock()
        tc_obj.id = tc.get("id", "")
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
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    resp.usage.cache_read_input_tokens = 0
    resp.usage.cache_creation_input_tokens = 0
    return resp


def test_capabilities_covers_required_singleshot_and_completion():
    """AC1: CAPABILITIES deckt REQUIRED_SINGLESHOT (structured_output +
    system_message_distinct) UND REQUIRED_COMPLETION ab."""
    assert public_api.REQUIRED_SINGLESHOT <= litellm_vendor.CAPABILITIES
    assert public_api.REQUIRED_COMPLETION <= litellm_vendor.CAPABILITIES
    assert "structured_output" in litellm_vendor.CAPABILITIES


def test_capabilities_includes_multimodal_input():
    """AC1 (#1509): CAPABILITIES enthält `multimodal_input` — Voraussetzung für
    den images-Pfad in singleshot_structured und das Cap-Gate in
    public_api._SingleshotFacade (LLMP-3/LLMP-S11)."""
    assert "multimodal_input" in litellm_vendor.CAPABILITIES


def test_singleshot_structured_parses_tool_call():
    """AC2: forced tool_use → geparstes dict aus function.arguments (getattr)."""
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis",
                     "arguments": '{"titel": "T", "text": "X"}'}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        out = vendor.singleshot_structured(
            "SYS", "PROMPT", {"type": "object"},
            caller="hoerspiel", slot="hoerspiel-litellm-claude-api-key")
    assert out == {"titel": "T", "text": "X"}


def test_singleshot_structured_forces_named_tool_choice():
    """AC2: der Payload trägt die BENANNTE tool_choice-Form + das EINE Tool
    (system als eigene Message, KEIN cache_control auf Singleshot)."""
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "folge",
                     "arguments": '{"n": 1}'}],
    ))
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.singleshot_structured(
            "Du bist Autor.", "Schreib Folge 1.", schema,
            caller="hoerspiel", slot="hoerspiel-litellm-claude-api-key",
            tool_name="folge", tool_description="Eine Folge.")
    call = fake_litellm.completion.call_args
    assert call.kwargs["tool_choice"] == {
        "type": "function", "function": {"name": "folge"}}
    tools = call.kwargs["tools"]
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "folge"
    assert tools[0]["function"]["parameters"] == schema
    sent = call.kwargs["messages"]
    assert sent[0]["role"] == "system"
    # Singleshot: KEIN cache_control-Marker (Ein-Turn, Spiegel mistral).
    assert sent[0]["content"] == "Du bist Autor."
    assert sent[1] == {"role": "user", "content": "Schreib Folge 1."}


def test_singleshot_structured_bad_json_yields_empty_dict():
    """AC2-Defensive: kaputtes arguments-JSON → {} (kein Crash)."""
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis", "arguments": "{kaputt"}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        out = vendor.singleshot_structured(
            "S", "P", {}, caller="hoerspiel",
            slot="hoerspiel-litellm-claude-api-key")
    assert out == {}


def test_singleshot_structured_no_matching_tool_raises():
    """AC2: kein tool_call mit name==tool_name → ProviderError (Spiegel mistral)."""
    from tools.llm import ProviderError
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "anderes", "arguments": "{}"}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        with pytest.raises(ProviderError):
            vendor.singleshot_structured(
                "S", "P", {}, caller="hoerspiel",
                slot="hoerspiel-litellm-claude-api-key", tool_name="ergebnis")


def test_singleshot_structured_writes_single_jsonl(jsonl_path):
    """AC2/AC4: genau EINE JSONL-Zeile (LLMP-S4), caller/slot durchgereicht."""
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis", "arguments": '{"ok": 1}'}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.singleshot_structured(
            "S", "P", {}, caller="hoerspiel",
            slot="hoerspiel-litellm-claude-api-key")
    lines = jsonl_path.read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["caller"] == "hoerspiel"
    assert rec["slot"] == "hoerspiel-litellm-claude-api-key"


def test_singleshot_structured_api_error_propagates():
    """AC4: litellm-APIError → ProviderError (analog chat/agent)."""
    from tools.llm import ProviderError
    fake_litellm = _make_fake_litellm_sdk(side_effect=_FakeAPIError("tot"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        with pytest.raises(ProviderError):
            vendor.singleshot_structured(
                "S", "P", {}, caller="hoerspiel",
                slot="hoerspiel-litellm-claude-api-key")


def test_singleshot_text_returns_content():
    """AC2: Freitext-Singleshot → str aus .choices[0].message.content."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_singleshot_response(content="  Eine Synopse.  "))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        out = vendor.singleshot_text(
            "SYS", "USER", caller="hoerspiel",
            slot="hoerspiel-litellm-claude-api-key")
    assert out == "Eine Synopse."


def test_singleshot_text_no_tools_in_payload():
    """AC2: Completion-Payload trägt KEIN tools/tool_choice (Freitext)."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_singleshot_response(content="ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.singleshot_text(
            "SYS", "USER", caller="hoerspiel",
            slot="hoerspiel-litellm-claude-api-key")
    call = fake_litellm.completion.call_args
    assert "tools" not in call.kwargs
    assert "tool_choice" not in call.kwargs
    sent = call.kwargs["messages"]
    assert sent == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


def test_singleshot_text_writes_single_jsonl(jsonl_path):
    """AC2/AC4: Completion schreibt genau EINE JSONL-Zeile (LLMP-S4)."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_singleshot_response(content="ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.singleshot_text(
            "S", "U", caller="hoerspiel",
            slot="hoerspiel-litellm-claude-api-key")
    lines = jsonl_path.read_text().strip().splitlines()
    assert len(lines) == 1


def test_singleshot_text_api_error_propagates():
    """AC4: completion-APIError → ProviderError."""
    from tools.llm import ProviderError
    fake_litellm = _make_fake_litellm_sdk(side_effect=_FakeAPIError("tot"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        with pytest.raises(ProviderError):
            vendor.singleshot_text(
                "S", "U", caller="hoerspiel",
                slot="hoerspiel-litellm-claude-api-key")


def test_singleshot_structured_images_reicht_bildblock_durch():
    """AC1 (#1509, multimodal_input): `images=[{bytes, media_type}]` → user-Content
    ist eine OpenAI-Vision-Liste [image_url-Block, text-Block]; base64-Kodierung
    geschieht IM Vendor. Text-Pfad (`images=None`) bleibt str-Content."""
    import base64 as b64_mod
    raw = b"\x89PNG-rohbytes"
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis",
                     "arguments": '{"termine": []}'}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.singleshot_structured(
            "SYS", "Extrahiere Termine.",
            {"type": "object"},
            caller="eltern-chat",
            slot="eltern-chat-litellm-foto-analyse-api-key",
            images=[{"bytes": raw, "media_type": "image/png"}],
        )

    call = fake_litellm.completion.call_args
    messages = call.kwargs["messages"]
    user_content = messages[-1]["content"]
    assert isinstance(user_content, list), "user-Content soll Liste bei images sein"
    assert len(user_content) == 2
    image_block, text_block = user_content
    assert image_block["type"] == "image_url"
    expected_url = "data:image/png;base64,%s" % b64_mod.standard_b64encode(raw).decode("ascii")
    assert image_block["image_url"]["url"] == expected_url
    assert text_block["type"] == "text"
    assert text_block["text"] == "Extrahiere Termine."


def test_singleshot_structured_images_none_ist_textpfad():
    """AC1 (#1509): `images=None` → user-Content ist der reine prompt-String
    (Regression-frei für den Text-Pfad, KEIN image_url-Block)."""
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis", "arguments": '{"a": 1}'}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.singleshot_structured(
            "SYS", "PROMPT", {"type": "object"},
            caller="hoerspiel", slot="hoerspiel-litellm-claude-api-key",
        )
    call = fake_litellm.completion.call_args
    user_content = call.kwargs["messages"][-1]["content"]
    assert user_content == "PROMPT"
    assert isinstance(user_content, str)


def test_singleshot_structured_images_max_tokens_erhalten(jsonl_path):
    """AC3 Migrations-Disziplin (#1509, hoerspiel-502-Lektion): max_tokens wird
    durchgereicht — kein stilles Trunkieren bei langen Ausgaben. Hier mit 4096
    (Token-Budget des Foto-Pfads, _MAX_TOKENS in foto_analyse.py)."""
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis", "arguments": '{"ok": 1}'}],
        # Simuliere reale Ausgabe-Länge nahe dem Token-Budget (Migrations-Beweis).
        completion_tokens=3800,
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        ss = public_api.get_singleshot(
            slot="eltern-chat-litellm-foto-analyse-api-key",
            model="claude-opus-4-7",
            max_tokens=4096,
        )
        ss.complete_structured("SYS", "PROMPT", {"type": "object"})

    call = fake_litellm.completion.call_args
    assert call.kwargs["max_tokens"] == 4096
    # Telemetrie spiegelt reale Ausgabe-Länge (Regressions-Sicherheit).
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["output_tokens"] == 3800


def test_get_singleshot_facade_boot_and_call_via_litellm(jsonl_path):
    """AC2/AC4: Boot über die get_singleshot-Fassade gegen einen litellm-Slot —
    Capability-Gate grün (structured_output deklariert), E2E-Parse."""
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis", "arguments": '{"a": 1}'}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        ss = public_api.get_singleshot(slot="hoerspiel-litellm-claude-api-key")
        out = ss.complete_structured("S", "P", {"type": "object"})
    assert out == {"a": 1}


def test_get_completion_facade_boot_and_call_via_litellm(jsonl_path):
    """AC2/AC4: Boot über die get_completion-Fassade gegen einen litellm-Slot."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_singleshot_response(content="Synopse."))
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        comp = public_api.get_completion(slot="hoerspiel-litellm-claude-api-key")
        out = comp.complete("S", "U")
    assert out == "Synopse."


# ----------------------------------------------------------------------
#  LLMP-S13 (#1463) — zentrale mistral/-Präfix-Normalisierung an _build_vendor
# ----------------------------------------------------------------------


def test_litellm_slot_prefixes_bare_mistral_model(jsonl_path):
    """LLMP-S13/AC1: ein blankes Mistral-Modell auf einem litellm-Slot bekommt
    das `mistral/`-Präfix ZENTRAL an `_build_vendor` (vor den get_*-Sichten) —
    `litellm.completion` sieht `mistral/mistral-medium-2508` (die #1452-Naht)."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_singleshot_response(content="ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        comp = public_api.get_completion(
            slot="hoerspiel-litellm-eu-api-key", model="mistral-medium-2508")
        comp.complete("S", "U")
    assert fake_litellm.completion.call_args.kwargs["model"] == "mistral/mistral-medium-2508"


def test_litellm_slot_leaves_claude_model_bare(jsonl_path):
    """LLMP-S13/AC1: ein Claude-Modell auf einem litellm-Slot bleibt blank —
    litellm erkennt es am Namen, kein doppeltes/falsches Präfix."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_singleshot_response(content="ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        comp = public_api.get_completion(
            slot="hoerspiel-litellm-claude-api-key", model="claude-opus-4-7")
        comp.complete("S", "U")
    assert fake_litellm.completion.call_args.kwargs["model"] == "claude-opus-4-7"


# ----------------------------------------------------------------------
#  Slot 2 (#1452) — agent_step: Wire-Übersetzung + Parse + Loop-E2E
# ----------------------------------------------------------------------


def _make_agent_response(text, *, tool_calls=None, prompt_tokens=100,
                         completion_tokens=50):
    """OpenAI-förmige LiteLLM-ModelResponse für agent_step: `.choices[0].message`
    mit `.content` + `.tool_calls[i].{id, function.{name, arguments}}`."""
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
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    resp.usage.cache_read_input_tokens = 0
    resp.usage.cache_creation_input_tokens = 0
    return resp


def test_agent_step_capabilities_covers_required_agent():
    """AC1: CAPABILITIES deckt REQUIRED_AGENT ab (tool_use dabei),
    web_search NICHT deklariert (out of scope)."""
    assert public_api.REQUIRED_AGENT <= litellm_vendor.CAPABILITIES
    assert "tool_use" in litellm_vendor.CAPABILITIES
    assert "web_search" not in litellm_vendor.CAPABILITIES


def test_agent_step_parses_text_only():
    """AC2: reine Text-Antwort → neutrale Form, tool_calls leer, web_search leer/0."""
    fake_litellm = _make_fake_litellm_sdk(_make_agent_response("Hallo Welt."))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        out = vendor.agent_step("S.", [{"role": "user", "content": "Hi"}], [],
                                caller="eltern-chat", slot="eltern-chat-litellm-api-key")
    assert out["text"] == "Hallo Welt."
    assert out["tool_calls"] == []
    assert out["web_search"] == []
    assert out["web_search_requests"] == 0


def test_agent_step_parses_tool_call():
    """AC2: tool_call → {id,name,input}; arguments-JSON defensiv geparst."""
    fake_litellm = _make_fake_litellm_sdk(_make_agent_response(
        "Ich schaue.",
        tool_calls=[{"id": "call-7", "name": "wetter",
                     "arguments": '{"ort": "Berlin"}'}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        out = vendor.agent_step(
            "S.", [{"role": "user", "content": "Wetter?"}],
            [{"name": "wetter", "description": "Wetter.",
              "input_schema": {"type": "object"}}],
            caller="eltern-chat", slot="eltern-chat-litellm-api-key")
    assert out["text"] == "Ich schaue."
    assert out["tool_calls"] == [
        {"id": "call-7", "name": "wetter", "input": {"ort": "Berlin"}}
    ]


def test_agent_step_bad_arguments_json_yields_empty_input():
    """AC2-Defensive: kaputtes arguments-JSON → input {} (kein Crash)."""
    fake_litellm = _make_fake_litellm_sdk(_make_agent_response(
        "", tool_calls=[{"id": "c1", "name": "t", "arguments": "{nicht-json"}],
    ))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        out = vendor.agent_step("S.", [], [], caller="eltern-chat",
                                slot="eltern-chat-litellm-api-key")
    assert out["tool_calls"][0]["input"] == {}


def test_agent_step_wire_in_translation_and_cache_control():
    """AC2/AC4: neutrale Anthropic-shaped messages IN → OpenAI-Form; System als
    eigene Message mit cache_control:ephemeral; tools → function-Form."""
    fake_litellm = _make_fake_litellm_sdk(_make_agent_response("ok"))
    messages = [
        {"role": "user", "content": "Wetter?"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Ich schaue."},
            {"type": "tool_use", "id": "call-1", "name": "wetter",
             "input": {"ort": "Berlin"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call-1",
             "content": "18 Grad", "is_error": False},
        ]},
    ]
    tools = [{"name": "wetter", "description": "Wetter.",
              "input_schema": {"type": "object", "properties": {}}}]
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.agent_step("Du bist Assistent.", messages, tools,
                          caller="eltern-chat", slot="eltern-chat-litellm-api-key")

    call = fake_litellm.completion.call_args
    sent = call.kwargs["messages"]
    # System als eigene erste Message mit cache_control.
    assert sent[0]["role"] == "system"
    assert sent[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent[0]["content"][0]["text"] == "Du bist Assistent."
    # user-String bleibt String.
    assert sent[1] == {"role": "user", "content": "Wetter?"}
    # assistant tool_use → OpenAI tool_calls, arguments JSON-serialisiert.
    assistant = sent[2]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "call-1"
    assert assistant["tool_calls"][0]["type"] == "function"
    assert assistant["tool_calls"][0]["function"]["name"] == "wetter"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"ort": "Berlin"}
    # tool_result → eigene tool-Message mit tool_call_id.
    tool_msg = sent[3]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call-1"
    assert tool_msg["content"] == "18 Grad"
    # tools → OpenAI function-Form.
    assert call.kwargs["tools"][0]["type"] == "function"
    assert call.kwargs["tools"][0]["function"]["name"] == "wetter"


def test_agent_step_tool_result_is_error_prefix():
    """AC2: is_error=True am tool_result → '[FEHLER] '-Prefix im content
    (mistral-Parität)."""
    fake_litellm = _make_fake_litellm_sdk(_make_agent_response("ok"))
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "c1",
         "content": "Sensor offline", "is_error": True},
    ]}]
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.agent_step("S.", messages, [], caller="eltern-chat",
                          slot="eltern-chat-litellm-api-key")
    sent = fake_litellm.completion.call_args.kwargs["messages"]
    tool_msg = sent[-1]
    assert tool_msg["role"] == "tool"
    assert tool_msg["content"] == "[FEHLER] Sensor offline"


def test_agent_step_writes_single_jsonl(jsonl_path):
    """AC2: agent_step emittiert GENAU EINE JSONL-Zeile (LLMP-S4), Usage
    OpenAI→intern gemappt."""
    fake_litellm = _make_fake_litellm_sdk(_make_agent_response(
        "ok", prompt_tokens=321, completion_tokens=12))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        vendor.agent_step("S.", [{"role": "user", "content": "Hi"}], [],
                          caller="eltern-chat", slot="eltern-chat-litellm-api-key",
                          correlation_id="turn-abc")
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "eltern-chat"
    assert parsed["input_tokens"] == 321
    assert parsed["output_tokens"] == 12
    assert parsed["correlation_id"] == "turn-abc"


def test_agent_step_api_error_propagates():
    """AC2: litellm.exceptions.APIError → ProviderError."""
    fake_litellm = _make_fake_litellm_sdk(side_effect=_FakeAPIError("tot"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        from tools.llm import ProviderError
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        with pytest.raises(ProviderError):
            vendor.agent_step("S.", [], [], caller="eltern-chat",
                              slot="eltern-chat-litellm-api-key")


def test_agent_run_loop_e2e_with_tool_runner():
    """AC2: agent_run (VendorBase-Loop) über litellm-agent_step — erst tool_call,
    dann tool_runner-Ergebnis, dann finale Text-Antwort."""
    resp_tool = _make_agent_response(
        "", tool_calls=[{"id": "c1", "name": "wetter",
                         "arguments": '{"ort": "Berlin"}'}])
    resp_final = _make_agent_response("Es sind 18 Grad in Berlin.")
    fake_litellm = _make_fake_litellm_sdk()
    fake_litellm.completion.side_effect = [resp_tool, resp_final]

    calls = []

    def tool_runner(name, args):
        calls.append((name, args))
        return "18 Grad"

    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
        out = vendor.agent_run(
            "Du bist Assistent.",
            [{"role": "user", "content": "Wetter in Berlin?"}],
            [{"name": "wetter", "description": "Wetter.",
              "input_schema": {"type": "object"}}],
            caller="eltern-chat", slot="eltern-chat-litellm-api-key",
            tool_runner=tool_runner,
        )

    assert out["text"] == "Es sind 18 Grad in Berlin."
    assert calls == [("wetter", {"ort": "Berlin"})]
    # Zwei litellm-Calls: tool-Turn + finaler Turn.
    assert fake_litellm.completion.call_count == 2
    # Zweiter Call trägt die zurückgespiegelte assistant-tool_use + tool-Message.
    second_messages = fake_litellm.completion.call_args_list[1].kwargs["messages"]
    roles = [m["role"] for m in second_messages]
    assert "assistant" in roles
    assert "tool" in roles


# ----------------------------------------------------------------------
#  T1410 — Audio: CAPABILITIES + speech() + transcription() (LLMP-S6/RAT-28)
# ----------------------------------------------------------------------


def test_capabilities_covers_audio():
    """AC1: CAPABILITIES deckt REQUIRED_SPEECH + REQUIRED_TRANSCRIPTION ab."""
    assert public_api.REQUIRED_SPEECH <= litellm_vendor.CAPABILITIES
    assert public_api.REQUIRED_TRANSCRIPTION <= litellm_vendor.CAPABILITIES


def _make_audio_sdk(*, speech_return=None, transcription_return=None,
                    speech_side_effect=None, transcription_side_effect=None):
    """Gemocktes litellm-SDK mit .speech + .transcription.

    `completion_cost` wirft TypeError — Audio-Responses haben keine Token-Kosten
    im LiteLLM-Sinne, d. h. `_litellm_response_cost_eur` soll None zurückgeben
    (Audio-Ausnahme-Pfad LLMP-S6, #1635).
    """
    fake = MagicMock()
    fake.exceptions.APIError = _FakeAPIError
    fake.exceptions.Timeout = _FakeTimeout  # #1784, siehe _make_fake_litellm_sdk
    if speech_side_effect is not None:
        fake.speech.side_effect = speech_side_effect
    else:
        fake.speech.return_value = speech_return
    if transcription_side_effect is not None:
        fake.transcription.side_effect = transcription_side_effect
    else:
        fake.transcription.return_value = transcription_return
    # Audio: completion_cost soll None liefern → Fallback-Pfad gibt None zurück.
    fake.completion_cost.side_effect = TypeError("audio: kein completion_cost")
    return fake


def test_get_speech_facade_boot_and_call(jsonl_path):
    """AC2: get_speech('kibuddy-litellm-tts-key').synth(...) → Bytes + GENAU EINE
    JSONL-Zeile mit modality=tts (LLMP-S6)."""
    speech_resp = MagicMock()
    speech_resp.content = b"ID3-mp3-bytes"
    fake = _make_audio_sdk(speech_return=speech_resp)

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_speech
        speech = get_speech(slot="kibuddy-litellm-tts-key", model="azure/tts-1-hd")
        out = speech.synth("Hallo Kind", voice="onyx", speed=0.9)

    assert out == b"ID3-mp3-bytes"
    call = fake.speech.call_args
    assert call.kwargs["model"] == "azure/tts-1-hd"
    assert call.kwargs["voice"] == "onyx"
    assert call.kwargs["input"] == "Hallo Kind"
    assert call.kwargs["speed"] == 0.9
    assert call.kwargs["response_format"] == "mp3"
    assert call.kwargs["api_key"] == "sk-fake"

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["modality"] == "tts"
    assert parsed["caller"] == "kibuddy"
    assert parsed["slot"] == "kibuddy-litellm-tts-key"
    assert parsed["model_id"] == "azure/tts-1-hd"
    assert parsed["input_tokens"] == 0
    assert parsed["output_tokens"] == 0
    assert parsed["est_cost_eur"] is None


def test_speech_byte_extractor_read_and_raw():
    """AC1: der Byte-Extraktor deckt .content, .read() und raw bytes ab."""
    vendor = _make_vendor()
    # .read()-Stream-Form
    stream = MagicMock(spec=["read"])
    stream.read.return_value = b"via-read"
    assert vendor._extract_audio_bytes(stream) == b"via-read"
    # raw bytes
    assert vendor._extract_audio_bytes(b"raw") == b"raw"
    # unerwartete Form → ProviderError
    from tools.llm import ProviderError
    with pytest.raises(ProviderError):
        vendor._extract_audio_bytes(object())


def test_get_transcription_facade_boot_and_call(jsonl_path):
    """AC2: get_transcription(...).transcribe(...) → Text + GENAU EINE JSONL-Zeile
    mit modality=stt; file trägt .name (Format-Ableitung); language durchgereicht."""
    trans_resp = MagicMock()
    trans_resp.text = "Warum ist der Himmel blau?"
    fake = _make_audio_sdk(transcription_return=trans_resp)

    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_transcription
        stt = get_transcription(slot="kibuddy-litellm-stt-key", model="azure/whisper-1")
        text = stt.transcribe(b"mp3-bytes", filename="audio.mp3", language="de")

    assert text == "Warum ist der Himmel blau?"
    call = fake.transcription.call_args
    assert call.kwargs["model"] == "azure/whisper-1"
    assert call.kwargs["language"] == "de"
    assert call.kwargs["api_key"] == "sk-fake"
    audio_file = call.kwargs["file"]
    assert getattr(audio_file, "name", None) == "audio.mp3"

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["modality"] == "stt"
    assert parsed["caller"] == "kibuddy"
    assert parsed["slot"] == "kibuddy-litellm-stt-key"
    assert parsed["model_id"] == "azure/whisper-1"


def test_transcription_api_error_propagates_no_jsonl(jsonl_path):
    """AC2: transcription-APIError → ProviderError; KEIN JSONL (Fehler vor Telemetrie)."""
    fake = _make_audio_sdk(transcription_side_effect=_FakeAPIError("tot"))
    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import ProviderError, get_transcription
        stt = get_transcription(slot="kibuddy-litellm-stt-key")
        with pytest.raises(ProviderError):
            stt.transcribe(b"x", filename="audio.mp3")
    assert not jsonl_path.exists()


def test_speech_api_error_propagates_no_jsonl(jsonl_path):
    """AC2: speech-APIError → ProviderError; KEIN JSONL."""
    fake = _make_audio_sdk(speech_side_effect=_FakeAPIError("tot"))
    with patch.dict(sys.modules, {"litellm": fake}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import ProviderError, get_speech
        speech = get_speech(slot="kibuddy-litellm-tts-key")
        with pytest.raises(ProviderError):
            speech.synth("t", voice="onyx")
    assert not jsonl_path.exists()


# ----------------------------------------------------------------------
#  #1635 — Kosten-Naht auf LiteLLM-native (response_cost)
# ----------------------------------------------------------------------


def test_litellm_response_cost_eur_primary_hidden_params():
    """#1635: response._hidden_params={"response_cost":0.01} USD → 0.01*0.92 EUR."""
    from tools.llm._vendor.litellm import _litellm_response_cost_eur

    resp = MagicMock()
    resp._hidden_params = {"response_cost": 0.01}

    fake_sdk = MagicMock()
    result = _litellm_response_cost_eur(resp, fake_sdk)

    assert result == pytest.approx(0.01 * 0.92)
    # completion_cost wurde NICHT gerufen (Primary-Pfad reichte)
    fake_sdk.completion_cost.assert_not_called()


def test_litellm_response_cost_eur_fallback_completion_cost():
    """#1635: response_cost None → Fallback completion_cost(0.005 USD) → 0.005*0.92 EUR."""
    from tools.llm._vendor.litellm import _litellm_response_cost_eur

    resp = MagicMock()
    resp._hidden_params = {}  # kein response_cost → Fallback

    fake_sdk = MagicMock()
    fake_sdk.completion_cost.return_value = 0.005

    result = _litellm_response_cost_eur(resp, fake_sdk)

    assert result == pytest.approx(0.005 * 0.92)
    fake_sdk.completion_cost.assert_called_once_with(completion_response=resp)


def test_litellm_response_cost_eur_none_when_both_unavailable():
    """#1635: response_cost None UND completion_cost wirft → None (Audio-Pfad)."""
    from tools.llm._vendor.litellm import _litellm_response_cost_eur

    resp = MagicMock()
    resp._hidden_params = {}

    fake_sdk = MagicMock()
    fake_sdk.completion_cost.side_effect = TypeError("audio: kein cost")

    result = _litellm_response_cost_eur(resp, fake_sdk)

    assert result is None


def test_litellm_response_cost_eur_none_response():
    """#1635: response=None → None (Audio ohne Response-Objekt, sicherer Guard)."""
    from tools.llm._vendor.litellm import _litellm_response_cost_eur

    result = _litellm_response_cost_eur(None, MagicMock())
    assert result is None


def test_emit_telemetry_uses_response_cost_naht(jsonl_path):
    """#1635: _emit_telemetry liest response_cost aus _hidden_params (nicht pricing.compute_eur)."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_fake_litellm_response(
            "ok",
            prompt_tokens=200,
            completion_tokens=100,
            response_cost=0.02,  # 0.02 USD → 0.02 * 0.92 EUR
        )
    )
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["est_cost_eur"] == pytest.approx(0.02 * 0.92)


def test_emit_telemetry_fallback_completion_cost(jsonl_path):
    """#1635: response_cost fehlt → Fallback completion_cost → EUR in JSONL."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_fake_litellm_response("ok"),  # kein response_cost
        completion_cost_return=0.003,       # completion_cost-Fallback: 0.003 USD
    )
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["est_cost_eur"] == pytest.approx(0.003 * 0.92)


def test_emit_telemetry_none_when_no_cost(jsonl_path):
    """#1635: response_cost None + completion_cost wirft → est_cost_eur=null in JSONL."""
    fake_litellm = _make_fake_litellm_sdk(
        _make_fake_litellm_response("ok"),  # kein response_cost
        # completion_cost_return=None → TypeError (Default in _make_fake_litellm_sdk)
    )
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["est_cost_eur"] is None


# ----------------------------------------------------------------------
#  T1784 — Zeit-Budgets: alle Call-Sites, zentrale Konfiguration,
#  hängender Anbieter
# ----------------------------------------------------------------------


def _make_haengendes_sdk(*, hang_sekunden: float):
    """Fake-SDK, das einen hängenden Anbieter simuliert (#1784).

    `completion` blockiert `hang_sekunden` lang — aber nur so lange, wie das
    mitgeschickte `timeout`-Budget erlaubt; danach fliegt `_FakeTimeout`, genau
    wie der echte HTTP-Client unter litellm es tut.

    Ein Vendor, der KEIN `timeout` mitschickt, blockiert hier die vollen
    `hang_sekunden` — das ist der Zustand vor #1784 (litellm-Default 600 s). Der
    Test unten scheitert dann an der Zeit-Assertion statt stillschweigend grün
    zu bleiben.
    """
    def haengen(*_args, timeout=None, **_kwargs):
        if timeout is None:
            time.sleep(hang_sekunden)
            return _make_fake_litellm_response("zu spaet")
        budget = min(float(timeout), hang_sekunden)
        time.sleep(budget)
        if budget < hang_sekunden:
            raise _FakeTimeout(
                "Provider antwortete nicht innerhalb von %.2fs" % budget)
        return _make_fake_litellm_response("gerade noch")

    return _make_fake_litellm_sdk(side_effect=haengen)


def test_default_timeout_ist_das_zentrale_budget():
    """T1784-AC2: der Vendor zieht sein Budget aus EINER Stelle
    (`_types.LLM_TIMEOUT_SECONDS`), nicht aus einer Vendor-Konstante."""
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
    assert vendor.timeout == LLM_TIMEOUT_SECONDS
    # Der interaktive Default ist ENDLICH und deutlich unter litellms 600 s.
    assert 0 < LLM_TIMEOUT_SECONDS < 60


def test_konstruktor_timeout_gewinnt_gegen_default():
    """T1784-AC2/CLIENT-2: `timeout=` am Konstruktor ist der Override — so holt
    hoerspiel sein Langtext-Budget, ohne den Chat-Default aufzuweichen."""
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(
            api_key="sk-fake", timeout=LLM_TIMEOUT_LONGFORM_SECONDS)
    assert vendor.timeout == LLM_TIMEOUT_LONGFORM_SECONDS
    assert LLM_TIMEOUT_LONGFORM_SECONDS > LLM_TIMEOUT_SECONDS


def test_env_ueberschreibt_default_budget(monkeypatch):
    """T1784-AC2: ENV `XBUDDY_LLM_TIMEOUT_SECONDS` ist der Not-Hebel am Pi."""
    monkeypatch.setenv("XBUDDY_LLM_TIMEOUT_SECONDS", "7.5")
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
    assert vendor.timeout == 7.5


@pytest.mark.parametrize("roher_wert", ["", "abc", "0", "-5"])
def test_krumme_env_faellt_auf_default_zurueck(monkeypatch, roher_wert):
    """T1784: eine unbrauchbare ENV darf den Familien-Chat nicht am Boot
    hindern — sie wird geloggt-ignoriert, der Code-Default gilt."""
    monkeypatch.setenv("XBUDDY_LLM_TIMEOUT_SECONDS", roher_wert)
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        vendor = litellm_vendor.LitellmVendor(api_key="sk-fake")
    assert vendor.timeout == LLM_TIMEOUT_SECONDS


def test_timeout_null_am_konstruktor_wird_abgelehnt():
    """T1784: „kein Timeout" darf nicht über ein 0-Argument zurückkommen — das
    ist genau der Zustand, den #1784 beseitigt."""
    fake_litellm = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         pytest.raises(ValueError, match="timeout"):
        litellm_vendor.LitellmVendor(api_key="sk-fake", timeout=0)


def test_alle_sechs_sichten_schicken_das_timeout_mit(jsonl_path):
    """T1784-AC1: JEDE Call-Site des Vendors trägt ein explizites Timeout — es
    gibt keinen Pfad mehr, auf dem litellms 600-s-Default gilt.

    Deckt alle sechs SDK-Call-Sites ab: chat_multiturn, agent_step,
    singleshot_structured, singleshot_text, speech, transcription.
    """
    budget = 12.5

    # 1) chat_multiturn
    fake = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))
    with patch.dict(sys.modules, {"litellm": fake}):
        litellm_vendor.LitellmVendor(
            api_key="sk-fake", timeout=budget).chat_multiturn(
                "S.", [], "F?", caller="kibuddy", slot="kibuddy-litellm-api-key")
    assert fake.completion.call_args.kwargs["timeout"] == budget

    # 2) agent_step
    fake = _make_fake_litellm_sdk(_make_agent_response(text="ok"))
    with patch.dict(sys.modules, {"litellm": fake}):
        litellm_vendor.LitellmVendor(
            api_key="sk-fake", timeout=budget).agent_step(
                system="S.", messages=[{"role": "user", "content": "F?"}],
                tools=[], caller="eltern-chat",
                slot="eltern-chat-litellm-api-key")
    assert fake.completion.call_args.kwargs["timeout"] == budget

    # 3) singleshot_structured
    fake = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis", "arguments": "{}"}]))
    with patch.dict(sys.modules, {"litellm": fake}):
        litellm_vendor.LitellmVendor(
            api_key="sk-fake", timeout=budget).singleshot_structured(
                "S", "P", {}, caller="hoerspiel",
                slot="hoerspiel-litellm-claude-api-key")
    assert fake.completion.call_args.kwargs["timeout"] == budget

    # 4) singleshot_text
    fake = _make_fake_litellm_sdk(_make_fake_litellm_response("ok"))
    with patch.dict(sys.modules, {"litellm": fake}):
        litellm_vendor.LitellmVendor(
            api_key="sk-fake", timeout=budget).singleshot_text(
                "S", "U", caller="hoerspiel",
                slot="hoerspiel-litellm-claude-api-key")
    assert fake.completion.call_args.kwargs["timeout"] == budget

    # 5) speech
    speech_resp = MagicMock()
    speech_resp.content = b"ID3-mp3-bytes"
    fake = _make_audio_sdk(speech_return=speech_resp)
    with patch.dict(sys.modules, {"litellm": fake}):
        litellm_vendor.LitellmVendor(
            api_key="sk-fake", timeout=budget).speech(
                "Hallo.", voice="alloy", caller="kibuddy",
                slot="kibuddy-litellm-tts-key")
    assert fake.speech.call_args.kwargs["timeout"] == budget

    # 6) transcription
    stt_resp = MagicMock()
    stt_resp.text = "Hallo."
    fake = _make_audio_sdk(transcription_return=stt_resp)
    with patch.dict(sys.modules, {"litellm": fake}):
        litellm_vendor.LitellmVendor(
            api_key="sk-fake", timeout=budget).transcription(
                b"AUDIO", caller="kibuddy", slot="kibuddy-litellm-stt-key")
    assert fake.transcription.call_args.kwargs["timeout"] == budget


def test_timeout_wird_zu_llm_timeout_error_mit_deutscher_meldung(jsonl_path):
    """T1784-AC3: ein SDK-Timeout kommt als `LLMTimeoutError` heraus — Subklasse
    von `ProviderError`, damit der eltern-chat-EC-14-Pfad ihn ohne Code-Änderung
    als `_PROVIDER_DOWN` behandelt — mit deutschem Klartext statt SDK-Interna.

    Belegt zugleich, dass der Vendor den Timeout EIGENS fängt: `_FakeTimeout` ist
    KEINE Subklasse von `_FakeAPIError` (Spiegel der echten SDK-Hierarchie); ein
    reines `except APIError` würde ihn durchlassen.
    """
    fake_litellm = _make_fake_litellm_sdk(side_effect=_FakeTimeout("read timeout"))
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-litellm-api-key")
        with pytest.raises(LLMTimeoutError) as excinfo:
            chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    fehler = excinfo.value
    # Konsumenten-Vertrag: wer heute ProviderError fängt, fängt auch das.
    assert isinstance(fehler, ProviderError)
    # Familientauglich: deutscher Satz, keine SDK-Interna, kein Stacktrace.
    text = str(fehler)
    assert "KI-Dienst" in text
    assert "noch einmal" in text
    assert "read timeout" not in text
    assert "Traceback" not in text
    # Kein Telemetrie-Eintrag: der Fehler fliegt VOR _emit_telemetry.
    assert not jsonl_path.exists()


def test_haengender_provider_kommt_im_budget_mit_definiertem_fehler(jsonl_path):
    """T1784-AC4: DER Beweis-Test. Ein Anbieter, der 30 s hängen WÜRDE, gibt den
    Aufrufer-Thread innerhalb des Budgets mit einem definierten Fehler frei.

    Das ist der Schaden aus #1784 im Kleinen: der Call läuft im Worker-Thread,
    der die `PrivateChatSession` hält (eltern-chat/tasks.py) — hängt er, hängt
    der Chat-Turn der Familie. Budget hier 0,3 s statt 30 s, damit der Test
    schnell ist; die Mechanik ist dieselbe.
    """
    budget = 0.3
    hang = 30.0
    fake_litellm = _make_haengendes_sdk(hang_sekunden=hang)

    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_agent
        agent = get_agent("eltern-chat-litellm-api-key", timeout=budget)
        start = time.monotonic()
        with pytest.raises(LLMTimeoutError):
            agent.step(
                system="S.",
                messages=[{"role": "user", "content": "F?"}],
                tools=[],
            )
        dauer = time.monotonic() - start

    # Innerhalb des Budgets zurück — nicht nach `hang` Sekunden und schon gar
    # nicht nach litellms 600-s-Default. Der Puffer ist Scheduling-Rauschen.
    assert dauer < budget + 2.0, (
        "Aufruf brauchte %.2fs bei einem Budget von %.2fs — das Timeout greift "
        "nicht" % (dauer, budget))
    assert dauer < hang
    # Und das Budget kam wirklich am SDK an (kein Zufalls-Abbruch).
    assert fake_litellm.completion.call_args.kwargs["timeout"] == budget


def test_langtext_budget_kommt_am_sdk_an(jsonl_path):
    """T1784: hoerspiels Langtext-Pfad reicht sein größeres Budget bis ans SDK
    durch (`get_singleshot(..., timeout=…)` → Vendor → `completion`).

    Ohne diese Naht müsste der zentrale Default auf 420 s aufgeweicht werden —
    und der Familien-Chat wäre wieder minutenlang blockierbar.
    """
    fake_litellm = _make_fake_litellm_sdk(_make_singleshot_response(
        tool_calls=[{"id": "c1", "name": "ergebnis", "arguments": '{"t": 1}'}]))
    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        ss = public_api.get_singleshot(
            "hoerspiel-litellm-claude-api-key",
            timeout=LLM_TIMEOUT_LONGFORM_SECONDS)
        ss.complete_structured("S", "P", {})

    assert (fake_litellm.completion.call_args.kwargs["timeout"]
            == LLM_TIMEOUT_LONGFORM_SECONDS)
