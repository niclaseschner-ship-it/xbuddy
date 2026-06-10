"""Tests für den Mistral-Anbieter-Adapter — EC-11 / EC-17 / E-EC-11 (Refs #508).

EC-17: Test-Pflicht für Anbieter-Adapter. Keine Netz-Aufrufe — httpx wird durch
kontrollierte Doppelungen ersetzt.
"""

import json
import logging

import pytest
from providers import get_provider

# ============================================================
#  Hilfskonstrukte
# ============================================================

class _FakeHttpxResponse:
    """Doppelung einer httpx-Response."""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class _FakeHttpx:
    """Doppelung von httpx.post — zeichnet Aufrufe auf."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def post(self, url, *, headers, content, timeout):
        self.calls.append({
            "url": url,
            "headers": headers,
            "payload": json.loads(content),
        })
        return self._response


def _mistral_response(text="ok", tool_calls=None, usage=None):
    """Baut eine minimale Mistral-API-Antwort."""
    message = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    data = {
        "choices": [{"message": message, "finish_reason": "stop"}],
        "model": "mistral-medium-2508",
    }
    if usage is not None:
        data["usage"] = usage
    return data


def _build_provider_with(monkeypatch, response_body, status_code=200):
    """Baut einen MistralProvider, dessen httpx.post-Aufruf durch eine
    Doppelung ersetzt ist. Liefert (provider, fake_httpx)."""
    import providers.mistral as mistral_mod
    from providers.mistral import MistralProvider

    fake_httpx = _FakeHttpx(_FakeHttpxResponse(status_code, response_body))
    monkeypatch.setattr(mistral_mod.httpx, "post", fake_httpx.post)
    provider = MistralProvider(api_key="test-key", model="mistral-medium-2508")
    return provider, fake_httpx


def _empty_request():
    """Eine minimale GenerationRequest ohne Aufgaben."""
    from model import GenerationRequest, Message, TextBlock
    return GenerationRequest(
        system="Du bist ein Test-Bot.",
        messages=[Message(role="user", blocks=[TextBlock("hallo")])],
        task_defs=[])


def _request_with_tasks():
    """Eine GenerationRequest mit zwei Aufgaben."""
    from model import READ, GenerationRequest, Message, TaskDef, TextBlock
    return GenerationRequest(
        system="Du bist ein Test-Bot.",
        messages=[Message(role="user", blocks=[TextBlock("hallo")])],
        task_defs=[
            TaskDef(name="erste", description="Erste Aufgabe", kind=READ,
                    parameters={"type": "object", "properties": {}}),
            TaskDef(name="zweite", description="Zweite Aufgabe", kind=READ,
                    parameters={"type": "object", "properties": {}}),
        ])


# ============================================================
#  EC-11 — Factory
# ============================================================

def test_EC11_get_provider_mistral_liefert_mistral_provider():
    """EC-11: get_provider('mistral', ...) liefert einen MistralProvider."""
    from providers.mistral import MistralProvider
    provider = get_provider("mistral", api_key="test-key")
    assert isinstance(provider, MistralProvider)


def test_EC11_get_provider_unknown_raises():
    """EC-11: ein unbekannter Anbieter-Name wirft ValueError."""
    with pytest.raises(ValueError, match="unbekannter"):
        get_provider("gibt-es-nicht", api_key="egal")


def test_EC11_claude_branch_unverändert(monkeypatch):
    """AC2: der Claude-Pfad in providers/__init__.py bleibt unverändert —
    kein Verhaltens-Drift durch die Mistral-Ergänzung."""
    import providers.claude as claude_mod
    from providers.claude import ClaudeProvider

    class _FakeMessages:
        def create(self, **kwargs):
            class _R:
                usage = None
                def __init__(self):
                    self.content = []
            return _R()

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(claude_mod.anthropic, "Anthropic",
                        lambda api_key: _FakeClient())
    provider = get_provider("claude", api_key="test-key")
    assert isinstance(provider, ClaudeProvider)


# ============================================================
#  AC1 — generate() → GenerationResponse + ProviderUsage
# ============================================================

def test_AC1_generate_liefert_text(monkeypatch):
    """AC1: generate() liefert GenerationResponse mit dem Antwort-Text."""
    provider, _ = _build_provider_with(
        monkeypatch, _mistral_response(text="Hallo Welt"))

    result = provider.generate(_empty_request())
    assert result.text == "Hallo Welt"
    assert result.task_calls == []


def test_AC1_provider_usage_gefüllt(monkeypatch):
    """AC1 / EC-23: ProviderUsage wird aus der Mistral-`usage`-Antwort gebaut."""
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    provider, _ = _build_provider_with(
        monkeypatch, _mistral_response(text="ok", usage=usage))

    result = provider.generate(_empty_request())
    assert result.usage is not None
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 50
    assert result.usage.model_id == "mistral-medium-2508"


def test_AC1_provider_usage_fehlt_kein_crash(monkeypatch):
    """AC1: fehlt `usage` in der Antwort, bleibt result.usage None."""
    provider, _ = _build_provider_with(
        monkeypatch, _mistral_response(text="ok", usage=None))

    result = provider.generate(_empty_request())
    assert result.usage is None


# ============================================================
#  AC1 — ProviderError-Wrapping
# ============================================================

def test_AC1_provider_error_bei_http_fehler(monkeypatch):
    """AC1: ein HTTP-Fehler (4xx/5xx) wird als ProviderError verpackt."""
    from model import ProviderError
    provider, _ = _build_provider_with(
        monkeypatch,
        {"error": {"message": "Unauthorized"}},
        status_code=401)

    with pytest.raises(ProviderError) as exc_info:
        provider.generate(_empty_request())
    assert "401" in str(exc_info.value)


def test_AC1_provider_error_bei_netzwerkfehler(monkeypatch):
    """AC1: ein Netzwerkfehler (httpx.RequestError) wird als ProviderError verpackt."""
    import providers.mistral as mistral_mod
    from model import ProviderError

    def _fail(*args, **kwargs):
        raise mistral_mod.httpx.RequestError("Verbindung abgelehnt")

    monkeypatch.setattr(mistral_mod.httpx, "post", _fail)
    provider = mistral_mod.MistralProvider(api_key="test-key")

    with pytest.raises(ProviderError) as exc_info:
        provider.generate(_empty_request())
    assert "Netzwerkfehler" in str(exc_info.value)


# ============================================================
#  AC1 — Logging (E-EC-11 / LOG-4)
# ============================================================

def test_AC1_token_usage_logged_as_info(monkeypatch, caplog):
    """E-EC-11 / LOG-4: nach jedem Anbieter-Aufruf wird die Token-Nutzung als
    INFO-Zeile geschrieben — vier Counter + Modell in einer Zeile."""
    usage = {"prompt_tokens": 500, "completion_tokens": 80, "total_tokens": 580}
    provider, _ = _build_provider_with(
        monkeypatch, _mistral_response(text="ok", usage=usage))

    with caplog.at_level(logging.INFO, logger="providers.mistral"):
        provider.generate(_empty_request())

    records = [r for r in caplog.records
               if r.name == "providers.mistral" and "tokens" in r.message]
    assert len(records) == 1, "genau eine Token-Log-Zeile je Aufruf"
    msg = records[0].getMessage()
    assert "input=500" in msg
    assert "output=80" in msg
    assert "model=mistral-medium-2508" in msg


def test_AC1_token_log_fehlt_kein_crash(monkeypatch, caplog):
    """LOG-4: Antworten ohne `usage` crashen nicht und schreiben kein Token-Log."""
    provider, _ = _build_provider_with(
        monkeypatch, _mistral_response(text="ok", usage=None))

    with caplog.at_level(logging.INFO, logger="providers.mistral"):
        provider.generate(_empty_request())

    records = [r for r in caplog.records
               if r.name == "providers.mistral" and "tokens" in r.message]
    assert records == []


# ============================================================
#  AC1 — System-Prompt als eigene Nachricht
# ============================================================

def test_AC1_system_prompt_in_eigener_nachricht(monkeypatch):
    """Mistral-API-Konvention: System-Prompt wird als eigene `system`-Rolle
    in die Messages-Liste aufgenommen."""
    provider, fake = _build_provider_with(
        monkeypatch, _mistral_response(text="ok"))

    provider.generate(_empty_request())

    messages = fake.calls[0]["payload"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "Du bist ein Test-Bot."
    # Zweite Nachricht ist die User-Nachricht.
    assert messages[1]["role"] == "user"


# ============================================================
#  AC1 — Tool-Calls in Antwort
# ============================================================

def test_AC1_tool_calls_werden_gemappt(monkeypatch):
    """AC1: Tool-Calls in der Mistral-Antwort werden als TaskCallBlock zurückgegeben."""
    from model import TaskCallBlock
    tool_calls = [{
        "id": "call-42",
        "type": "function",
        "function": {
            "name": "termine_abfragen",
            "arguments": json.dumps({"ab": "heute"}),
        },
    }]
    provider, _ = _build_provider_with(
        monkeypatch, _mistral_response(text="", tool_calls=tool_calls))

    result = provider.generate(_empty_request())
    assert len(result.task_calls) == 1
    call = result.task_calls[0]
    assert isinstance(call, TaskCallBlock)
    assert call.call_id == "call-42"
    assert call.task == "termine_abfragen"
    assert call.arguments == {"ab": "heute"}


# ============================================================
#  AC1 — Tools werden in Mistral-Form übersetzt
# ============================================================

def test_AC1_tools_in_mistral_form(monkeypatch):
    """AC1: TaskDef-Werkzeuge werden in die Mistral-Tool-Form
    `{type: 'function', function: {...}}` übersetzt."""
    provider, fake = _build_provider_with(
        monkeypatch, _mistral_response(text="ok"))

    provider.generate(_request_with_tasks())

    tools = fake.calls[0]["payload"]["tools"]
    assert len(tools) == 2
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "erste"
    assert tools[1]["function"]["name"] == "zweite"


# ============================================================
#  AC3 — Pricing: Mistral-Modelle erkannt
# ============================================================

def test_AC3_pricing_mistral_medium_2508_erkannt():
    """AC3: mistral-medium-2508 ist in der Pricing-Tabelle und liefert
    Nicht-None-Werte."""
    from providers.pricing import estimate_cost
    cost_usd, cost_eur = estimate_cost("mistral-medium-2508",
                                       input_tokens=1_000_000,
                                       cached_input_tokens=0,
                                       output_tokens=1_000_000)
    assert cost_usd is not None
    assert cost_eur is not None
    # Mistral Medium: 1.5 input + 7.5 output = 9.0 USD / 1M Tokens je.
    assert cost_usd == pytest.approx(1.5 + 7.5)


def test_AC3_pricing_mistral_medium_3504_erkannt():
    """AC3: mistral-medium-3504 ist in der Pricing-Tabelle und liefert
    Nicht-None-Werte."""
    from providers.pricing import estimate_cost
    cost_usd, cost_eur = estimate_cost("mistral-medium-3504",
                                       input_tokens=1_000_000,
                                       cached_input_tokens=0,
                                       output_tokens=1_000_000)
    assert cost_usd is not None
    assert cost_eur is not None


def test_AC3_pricing_claude_modelle_unberührt():
    """AC3: Claude-Modelle sind nach wie vor erkannt — keine Regression."""
    from providers.pricing import estimate_cost
    cost_usd, _ = estimate_cost("claude-opus-4-7",
                                input_tokens=1_000_000,
                                cached_input_tokens=0,
                                output_tokens=1_000_000)
    assert cost_usd == pytest.approx(5.0 + 25.0)


# ============================================================
#  Befund 2 — mehrere TaskResultBlocks in einer User-Message
# ============================================================

def test_mehrere_task_result_blocks_werden_als_eigene_tool_nachrichten_serialisiert(
        monkeypatch):
    """Befund 2 / AC3: Bei mehreren TaskResultBlocks in einer User-Message liefert
    _to_mistral_message eine Liste mit je einer `role=tool`-Nachricht pro Block.
    Mistral erwartet pro tool_call_id eine eigene Nachricht — wird nur der erste
    Block serialisiert, kommt ein 400-Fehler oder eine Halluzination.

    Probe: zwei TaskResultBlocks → Payload enthält genau zwei `role=tool`-
    Nachrichten mit den richtigen tool_call_ids.
    """
    from model import GenerationRequest, Message, TaskResultBlock, TextBlock

    provider, fake = _build_provider_with(
        monkeypatch, _mistral_response(text="ok"))

    request = GenerationRequest(
        system="Test.",
        messages=[
            Message(role="assistant", blocks=[TextBlock("Ich rufe zwei Tools auf.")]),
            Message(role="user", blocks=[
                TaskResultBlock(call_id="call-a", content="Ergebnis A"),
                TaskResultBlock(call_id="call-b", content="Ergebnis B"),
            ]),
        ],
        task_defs=[],
    )
    provider.generate(request)

    messages = fake.calls[0]["payload"]["messages"]
    tool_messages = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_messages) == 2, (
        "Befund 2: beide TaskResultBlocks müssen als eigene tool-Nachrichten "
        "im Payload erscheinen — gefunden: %d" % len(tool_messages)
    )
    ids = {m["tool_call_id"] for m in tool_messages}
    assert ids == {"call-a", "call-b"}, (
        "Befund 2: tool_call_ids müssen call-a und call-b sein — gefunden: %r" % ids
    )
    contents = {m["tool_call_id"]: m["content"] for m in tool_messages}
    assert contents["call-a"] == "Ergebnis A"
    assert contents["call-b"] == "Ergebnis B"
