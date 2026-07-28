"""get_completion — Freitext-Singleshot, beide Vendoren (#1131, LLMP-S1).

Ohne Netz: Anthropic über einen Fake-SDK-Client, Mistral über gemocktes
litellm-SDK (Motor-Weg, #1536 — Hand-Vendor `_vendor/mistral.py` entfernt).
Spiegel `test_singleshot` (get_singleshot), aber für die vierte Sicht: kein
Tool, kein Schema, ein Vendor-Call, Freitext-String zurück.

- get_completion(slot, model=…) reicht model an den Vendor durch.
- get_completion(slot) ohne model → Vendor-DEFAULT_MODEL.
- Required-Set NUR system_message_distinct → bootet auf Claude UND Mistral
  (kein cache_control-Boot-Fail auf dem litellm-Slot).
- max_tokens-Durchreichung (T1084-Parität) auf beiden Vendoren.
- Anthropic- + litellm-Mistral-Pfad: Freitext end-to-end (kein tool_choice im Payload).
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


SYNOPSE = "Stigi findet den Trübsee und lernt, dass Mut ansteckend ist."


# ----------------------------------------------------------------------
#  Anthropic-Fakes (Spiegel test_singleshot)
# ----------------------------------------------------------------------

def _anthropic_text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _anthropic_response(blocks):
    resp = MagicMock()
    resp.content = blocks
    usage = MagicMock()
    usage.input_tokens = 120
    usage.output_tokens = 40
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    resp.usage = usage
    return resp


def _fake_anthropic():
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception
    return fake, client


# ----------------------------------------------------------------------
#  litellm-Fakes (Spiegel test_vendor_litellm — Mistral via Motor-Weg, #1536)
# ----------------------------------------------------------------------

def _fake_litellm(text=""):
    """Gemocktes litellm-SDK: `.completion` liefert OpenAI-förmige Response."""
    message = MagicMock()
    message.content = text
    message.tool_calls = []
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = 110
    resp.usage.completion_tokens = 35
    resp.usage.cache_read_input_tokens = 0
    resp.usage.cache_creation_input_tokens = 0
    fake = MagicMock()
    fake.exceptions.APIError = Exception
    fake.completion.return_value = resp
    return fake


# ----------------------------------------------------------------------
#  Boot: Required-Set trägt beide Vendoren
# ----------------------------------------------------------------------

def test_get_completion_boots_on_anthropic():
    """Anthropic-Slot bootet (system_message_distinct in CAPABILITIES)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key")
    assert comp.name == "completion"


def test_get_completion_boots_on_litellm_mistral():
    """litellm-Mistral-Slot bootet — Required-Set OHNE cache_control (LLMP-S9), sonst
    wäre die Sicht boot-fatal (#1131). Slot ist `hoerspiel-litellm-eu-api-key`
    (litellm_slot_for_provider — #1536, Hand-Vendor entfernt)."""
    fake_lit = _fake_litellm()
    with patch.dict(sys.modules, {"litellm": fake_lit}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-litellm-eu-api-key")
    assert comp.name == "completion"


# ----------------------------------------------------------------------
#  Modell- + max_tokens-Durchreichung
# ----------------------------------------------------------------------

def test_get_completion_passes_model_to_vendor():
    """get_completion(slot, model) reicht das Modell an den Vendor durch."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key",
                              model="claude-opus-4-7")
    assert comp.model == "claude-opus-4-7"


def test_get_completion_without_model_uses_vendor_default():
    """get_completion(slot) ohne model → Vendor-DEFAULT_MODEL."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        from tools.llm._vendor.anthropic import DEFAULT_MODEL
        comp = get_completion(slot="hoerspiel-anthropic-api-key")
    assert comp.model == DEFAULT_MODEL


def test_get_completion_passes_max_tokens_anthropic():
    """get_completion(slot, max_tokens=8192) → vendor.max_tokens == 8192 (AC3)."""
    fake_anthropic, _client = _fake_anthropic()
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key", max_tokens=8192)
    assert comp._vendor.max_tokens == 8192


def test_get_completion_passes_max_tokens_litellm_mistral():
    """get_completion(slot, max_tokens=4096) → litellm vendor.max_tokens == 4096 (AC3,
    #1536: Mistral läuft über litellm-Motor, slot=hoerspiel-litellm-eu-api-key)."""
    fake_lit = _fake_litellm()
    with patch.dict(sys.modules, {"litellm": fake_lit}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-litellm-eu-api-key", max_tokens=4096)
    assert comp._vendor.max_tokens == 4096


# ----------------------------------------------------------------------
#  Freitext end-to-end — kein Tool/Schema im Payload
# ----------------------------------------------------------------------

def test_anthropic_completion_freitext_end_to_end(jsonl_path):
    """Anthropic: .complete(system, user) → Freitext-String; KEIN tools/
    tool_choice im create-Call; max_tokens durchgereicht; Telemetrie geschrieben."""
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response(
        [_anthropic_text_block(SYNOPSE)]
    )

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key",
                              model="claude-opus-4-7", max_tokens=8192)
        out = comp.complete(system="Fasse zusammen.", user="Der Folgentext …")

    assert out == SYNOPSE
    call = client.messages.create.call_args
    assert call.kwargs["model"] == "claude-opus-4-7"
    assert call.kwargs["max_tokens"] == 8192
    # Freitext-Singleshot: KEIN Tool, KEIN tool_choice (Abgrenzung zu get_singleshot).
    assert "tools" not in call.kwargs
    assert "tool_choice" not in call.kwargs
    # system_message_distinct: der System-Prompt liegt getrennt in `system`.
    assert call.kwargs["system"][0]["text"] == "Fasse zusammen."
    # Telemetrie: caller=hoerspiel.
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "hoerspiel"
    assert parsed["model_id"] == "claude-opus-4-7"


def test_mistral_completion_freitext_end_to_end(jsonl_path):
    """Mistral-via-litellm: .complete(system, user) → Freitext-String;
    KEIN tool_choice; Telemetrie geschrieben; LLMP-S13: `mistral/`-Präfix am Modell.
    (#1536 — Hand-Vendor entfernt, Motor-Weg über hoerspiel-litellm-eu-api-key)."""
    fake_lit = _fake_litellm(text=SYNOPSE)

    with patch.dict(sys.modules, {"litellm": fake_lit}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-litellm-eu-api-key",
                              model="mistral-large-2411")
        out = comp.complete(system="Fasse zusammen.", user="Der Folgentext …")

    assert out == SYNOPSE
    # LLMP-S13: normalize_model hat `mistral/`-Präfix ergänzt.
    assert fake_lit.completion.call_args.kwargs["model"] == "mistral/mistral-large-2411"
    # Freitext-Singleshot: KEIN tool_choice (LiteLLM-Vendor lässt es weg wenn kein Tool).
    call_kwargs = fake_lit.completion.call_args.kwargs
    assert "tool_choice" not in call_kwargs or call_kwargs.get("tool_choice") is None
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "hoerspiel"


def test_anthropic_completion_api_error_maps_to_provider_error():
    """Anthropic-APIError → tools.llm ProviderError (via _create, wie
    singleshot_structured)."""
    from tools.llm import ProviderError
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.side_effect = fake_anthropic.APIError("boom")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_completion
        comp = get_completion(slot="hoerspiel-anthropic-api-key")
        with pytest.raises(ProviderError):
            comp.complete(system="S", user="U")
