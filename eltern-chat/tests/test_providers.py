"""Tests für die Anbieter-Auswahl und den Claude-Adapter — EC-11 / E-EC-6
(Refs #27, #93, T1022/ECP-1).
"""

import logging

import pytest
from providers import get_provider, get_provider_class, iter_provider_classes

# ============================================================
#  ECP-1 — Provider-Self-Declaration: brand_vendor (T1022)
# ============================================================

def test_ECP1_claude_provider_has_brand_vendor():
    """ECP-1: ClaudeProvider trägt brand_vendor als Klassen-Attribut
    mit dem korrekten Slug (`anthropic`, ZD-2-Tabelle)."""
    from providers.claude import ClaudeProvider
    assert hasattr(ClaudeProvider, "brand_vendor")
    assert ClaudeProvider.brand_vendor == "anthropic"


def test_ECP1_mistral_provider_has_brand_vendor():
    """ECP-1: MistralProvider trägt brand_vendor als Klassen-Attribut
    mit dem korrekten Slug (`mistral`, ZD-2-Tabelle)."""
    from providers.mistral import MistralProvider
    assert hasattr(MistralProvider, "brand_vendor")
    assert MistralProvider.brand_vendor == "mistral"


def test_ECP1_brand_vendor_values_are_nonempty_strings():
    """ECP-1: brand_vendor ist ein nicht-leerer String bei allen registrierten
    Provider-Klassen — Drift-Sperre maschinell.

    Iteriert dynamisch über `iter_provider_classes()`, damit ein dritter Adapter
    ohne Anpassung dieser Datei in den Sweep einbezogen wird (AC6)."""
    checked = 0
    for cls in iter_provider_classes():
        assert isinstance(cls.brand_vendor, str), (
            "brand_vendor von %r ist kein String" % cls)
        assert cls.brand_vendor, (
            "brand_vendor von %r ist ein leerer String" % cls)
        checked += 1
    assert checked >= 2, "mindestens zwei Provider-Klassen müssen registriert sein"


def test_ECP1_vendor_slug_via_provider_class_claude():
    """ECP-1: Der Slug für `claude` geht über die Provider-Klasse, NICHT
    über eine harte Tabelle in onboarding_store. Ergebnis bleibt `anthropic`."""
    from onboarding_store import vendor_slug_for_adapter
    assert vendor_slug_for_adapter("claude") == "anthropic"


def test_ECP1_vendor_slug_via_provider_class_mistral():
    """ECP-1: Der Slug für `mistral` geht über die Provider-Klasse. Ergebnis
    bleibt `mistral`."""
    from onboarding_store import vendor_slug_for_adapter
    assert vendor_slug_for_adapter("mistral") == "mistral"


def test_ECP1_unknown_adapter_raises_from_get_provider_class():
    """ECP-1 / EC-11: get_provider_class wirft ValueError für unbekannte
    Adapter-Namen — kein stiller Fallback."""
    with pytest.raises(ValueError):
        get_provider_class("gibt-es-nicht")


def test_ECP1_stub_class_without_brand_vendor_raises_attribute_error():
    """ECP-1 Sentinel: eine Stub-Provider-Klasse ohne brand_vendor-Attribut
    produziert AttributeError beim Zugriff — kein stilles Versagen möglich.
    (Stub greift nicht in echte Provider ein.)"""

    class _StubProvider:
        pass

    with pytest.raises(AttributeError):
        _ = _StubProvider.brand_vendor


def test_EC_11_unknown_provider_raises():
    """Der Anbieter ist je Instanz wählbar — ein unbekannter Name ist ein
    Konfigurationsfehler, kein stiller Fallback."""
    with pytest.raises(ValueError):
        get_provider("gibt-es-nicht", api_key="egal")


# ============================================================
#  Claude-Adapter — Cache-Marker (#93 Item 1) + Token-Log (#93 Item 3)
# ============================================================

class _FakeUsage:
    """Doppelung des Anthropic-`usage`-Objekts (vier int-Counter)."""

    def __init__(self, input_tokens, cache_creation_input_tokens,
                 cache_read_input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.output_tokens = output_tokens


class _FakeContentBlock:
    """Doppelung eines Anthropic-Content-Blocks (Typ `text` reicht hier)."""

    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeAnthropicResponse:
    """Doppelung der Anthropic-Antwort: Content-Blöcke + `usage`."""

    def __init__(self, text="ok", usage=None):
        self.content = [_FakeContentBlock(text)]
        self.usage = usage


class _FakeMessages:
    """Doppelung des `client.messages`-Untermoduls: zeichnet kwargs auf."""

    def __init__(self, response):
        self._response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _build_provider_with(monkeypatch, response):
    """Baut einen ClaudeProvider, dessen `anthropic.Anthropic`-Client durch eine
    Doppelung ersetzt ist. Liefert (provider, fake_client)."""
    # Lazy-Import des Adapters; `providers/claude.py` importiert anthropic auf
    # Modul-Ebene — das SDK ist in requirements.txt, also vorhanden.
    import providers.claude as claude_mod
    from providers.claude import ClaudeProvider

    fake_client = _FakeClient(response)
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic",
                        lambda api_key: fake_client)
    provider = ClaudeProvider(api_key="test-key", model="claude-test")
    return provider, fake_client


def _empty_request():
    """Eine minimale GenerationRequest ohne Aufgaben."""
    from model import GenerationRequest, Message, TextBlock
    return GenerationRequest(
        system="Du bist ein Test-Bot.",
        messages=[Message(role="user", blocks=[TextBlock("hallo")])],
        task_defs=[])


def _request_with_tasks():
    """Eine GenerationRequest mit zwei Aufgaben — prüft das Markieren des
    letzten Aufgaben-Eintrags."""
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


def test_issue_93_cache_marker_sits_on_system_block(monkeypatch):
    """#93 Item 1: der Cache-Marker liegt am letzten `system`-Block — NICHT
    mehr als Top-Level-Kwarg. So trägt der Cache über Turns, weil der
    System-Prompt zwischen Turns stabil ist."""
    provider, fake = _build_provider_with(
        monkeypatch, _FakeAnthropicResponse(text="hi", usage=None))

    provider.generate(_empty_request())

    kwargs = fake.messages.kwargs
    # Top-Level-Kwarg darf nicht mehr gesetzt sein.
    assert "cache_control" not in kwargs, \
        "Top-Level cache_control darf nicht gesetzt sein (#93)"
    # `system` muss Listen-Form sein, mit cache_control am letzten Block.
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][-1].get("cache_control") == {"type": "ephemeral"}
    # Der Text bleibt erhalten.
    assert kwargs["system"][-1]["text"] == "Du bist ein Test-Bot."


def test_issue_93_cache_marker_sits_on_last_tool(monkeypatch):
    """#93 Item 1: der letzte Eintrag der `tools`-Liste trägt den Cache-Marker
    (Anthropic-Cache-Semantik markiert vorhergehende Tools implizit mit)."""
    provider, fake = _build_provider_with(
        monkeypatch, _FakeAnthropicResponse(text="hi", usage=None))

    provider.generate(_request_with_tasks())

    tools = fake.messages.kwargs["tools"]
    assert len(tools) == 2
    # Nur der letzte Eintrag wird explizit markiert.
    assert "cache_control" not in tools[0]
    assert tools[-1].get("cache_control") == {"type": "ephemeral"}
    # Andere Felder bleiben unangetastet.
    assert tools[-1]["name"] == "zweite"


def test_issue_93_token_usage_logged_as_info(monkeypatch, caplog):
    """#93 Item 3: nach jedem Anbieter-Aufruf wird die Token-Nutzung als
    INFO-Log-Zeile geschrieben — vier Counter + Modell, in einer Zeile."""
    usage = _FakeUsage(input_tokens=1234,
                       cache_creation_input_tokens=200,
                       cache_read_input_tokens=890,
                       output_tokens=156)
    provider, _ = _build_provider_with(
        monkeypatch, _FakeAnthropicResponse(text="ok", usage=usage))

    with caplog.at_level(logging.INFO, logger="providers.claude"):
        provider.generate(_empty_request())

    token_records = [r for r in caplog.records
                     if r.name == "providers.claude" and "tokens" in r.message]
    assert len(token_records) == 1, "genau eine Token-Log-Zeile je Aufruf"
    message = token_records[0].getMessage()
    assert "input=1234" in message
    assert "cache_create=200" in message
    assert "cache_read=890" in message
    assert "output=156" in message
    assert "model=claude-test" in message


def test_issue_93_token_log_handles_missing_usage(monkeypatch, caplog):
    """Anbieter-Antworten ohne `usage` (etwa zukünftige Adapter oder ein
    schmaler Test-Mock) dürfen nicht crashen — kein Token-Log, kein Fehler."""
    provider, _ = _build_provider_with(
        monkeypatch, _FakeAnthropicResponse(text="ok", usage=None))

    with caplog.at_level(logging.INFO, logger="providers.claude"):
        provider.generate(_empty_request())

    token_records = [r for r in caplog.records
                     if r.name == "providers.claude" and "tokens" in r.message]
    assert token_records == []


# ============================================================
#  #310 — reloadete History mappt paarig auf gültige Anthropic-Messages
# ============================================================

class _FakeToolUseBlock:
    """Doppelung eines Anthropic-`tool_use`-Content-Blocks."""

    def __init__(self, id, name, input):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input


def test_issue_310_reloaded_pair_maps_to_valid_anthropic_messages(tmp_path):
    """AC3: eine über die History persistierte + reloadete Tool-Paar-Sequenz
    mappt der Adapter auf gültige Anthropic-Messages — der tool_use trägt
    dieselbe id wie das tool_result als tool_use_id (kein 400-Muster)."""
    from history import History
    from model import Message, TaskCallBlock, TaskResultBlock, TextBlock
    from providers.claude import ClaudeProvider

    db = str(tmp_path / "c.db")
    hist = History(db)
    hist.append("chat-1", Message("user", [TextBlock("welche Termine?")]))
    hist.append("chat-1", Message("assistant", [
        TaskCallBlock(call_id="c-1", task="termine",
                      arguments={"ab": "heute"})]))
    hist.append("chat-1", Message("user", [
        TaskResultBlock(call_id="c-1", content="2 Termine", is_error=False)]))
    hist.append("chat-1", Message("assistant", [TextBlock("Du hast 2 Termine.")]))
    loaded = hist.load("chat-1", 20)
    hist.close()

    mapped = [ClaudeProvider._to_anthropic_message(m) for m in loaded]

    # assistant tool_use
    tool_use = mapped[1]["content"][-1]
    assert tool_use["type"] == "tool_use"
    assert tool_use["id"] == "c-1"
    assert tool_use["name"] == "termine"
    assert tool_use["input"] == {"ab": "heute"}
    # user tool_result — tool_use_id MUSS auf die id des tool_use zeigen.
    tool_result = mapped[2]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == tool_use["id"]
    assert tool_result["content"] == "2 Termine"
    assert tool_result["is_error"] is False


def test_issue_310_from_response_preserves_call_id(monkeypatch):
    """AC3-Vorbedingung: `_from_anthropic_response` überträgt die Anthropic-
    tool_use-`id` als `call_id` an den TaskCallBlock — sonst fänden Aufruf und
    späteres Ergebnis nach Reload nicht zusammen."""
    from model import TaskCallBlock

    resp = _FakeAnthropicResponse(text="", usage=None)
    resp.content = [_FakeToolUseBlock(id="c-42", name="termine",
                                      input={"ab": "morgen"})]
    provider, _ = _build_provider_with(monkeypatch, resp)

    result = provider.generate(_empty_request())
    assert len(result.task_calls) == 1
    call = result.task_calls[0]
    assert isinstance(call, TaskCallBlock)
    assert call.call_id == "c-42"
    assert call.task == "termine"
    assert call.arguments == {"ab": "morgen"}
