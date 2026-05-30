"""Tests für den Telemetrie-Wrapper in agent.run_turn — EC-23/E-EC-11
(Refs #268).

Geprüft wird:
- erfolgreicher Provider-Call → ProviderCall mit Token-Counts + Wall-Clock
- mehrere Provider-Calls (Tool-Loop) → aggregiert
- ProviderError → Stub-Call + err.telemetry gesetzt
- alter Provider ohne Usage → ProviderCall mit Counts=0 (kein Crash)
"""

import time

import pytest

import agent
from fakes import FakeProvider, FakeReadTask, task_call_response, text_response
from model import (GenerationResponse, Message, ProviderError, ProviderUsage,
                   TextBlock)
from tasks import Catalog, TurnContext


_TURN = TurnContext(chat_id=42)


def _user(text="eine Anfrage"):
    return Message("user", [TextBlock(text)])


def _response_with_usage(text="ok", input_tokens=100, output_tokens=200,
                        cache_read=10, cache_creation=5,
                        model_id="claude-opus-4-7"):
    return GenerationResponse(
        text=text, task_calls=[],
        usage=ProviderUsage(
            input_tokens=input_tokens, output_tokens=output_tokens,
            cache_read_tokens=cache_read, cache_creation_tokens=cache_creation,
            model_id=model_id))


# --- erfolgreicher Single-Call -------------------------------------------

def test_single_provider_call_recorded_in_telemetry():
    """Ein Provider-Call → genau ein ProviderCall in AgentResult.telemetry,
    mit den Token-Counts aus der Usage."""
    provider = FakeProvider([_response_with_usage(
        text="Antwort.", input_tokens=300, output_tokens=400,
        cache_read=20, cache_creation=10, model_id="claude-opus-4-7")])

    result = agent.run_turn([], _user(), provider, Catalog(), _TURN)

    assert result.telemetry is not None
    assert result.telemetry.has_calls()
    assert len(result.telemetry.calls) == 1
    c = result.telemetry.calls[0]
    assert c.model_id == "claude-opus-4-7"
    assert c.input_tokens == 300
    assert c.output_tokens == 400
    assert c.cache_read_tokens == 20
    assert c.cache_creation_tokens == 10
    # Wall-Clock ist gemessen — >= 0, sehr klein.
    assert c.wall_ms >= 0


def test_wall_clock_is_measured_per_call():
    """Der Wrapper misst Wall-Clock mit time.monotonic. Ein langsamer Provider
    führt zu einer entsprechend größeren wall_ms."""

    class SlowProvider:
        def generate(self, request):
            time.sleep(0.05)
            return _response_with_usage()

    result = agent.run_turn([], _user(), SlowProvider(), Catalog(), _TURN)
    assert result.telemetry.calls[0].wall_ms >= 50


# --- Tool-Loop (mehrere Provider-Calls) ----------------------------------

def test_tool_loop_aggregates_multiple_calls():
    """Ein Tool-Use-Loop ruft den Provider mehrfach — die Telemetrie sammelt
    alle Calls (Aggregation pro Turn, EC-23)."""
    read = FakeReadTask(name="info_lesen", result="22 Grad.")
    catalog = Catalog()
    catalog.register(read)
    # Zwei Runden: erst Tool-Call, dann Text.
    resp1 = GenerationResponse(
        text="", task_calls=[task_call_response("info_lesen").task_calls[0]],
        usage=ProviderUsage(input_tokens=100, output_tokens=50,
                            cache_read_tokens=0, cache_creation_tokens=0,
                            model_id="claude-opus-4-7"))
    resp2 = _response_with_usage(text="22 Grad.",
                                 input_tokens=200, output_tokens=80)
    provider = FakeProvider([resp1, resp2])

    result = agent.run_turn([], _user("wetter?"), provider, catalog, _TURN)

    assert len(result.telemetry.calls) == 2
    # Aggregation summiert.
    assert result.telemetry.total_tokens() == 100 + 50 + 200 + 80


# --- ProviderError → Stub-Call + err.telemetry ---------------------------

def test_provider_error_attaches_stub_call_and_telemetry():
    """R3: bei ProviderError hängt der Wrapper einen Stub-Call (tokens=0,
    est_cost=None, wall_ms gemessen) an die Telemetrie, setzt
    err.telemetry und wirft weiter."""
    provider = FakeProvider([ProviderError("Zeitüberschreitung")])

    with pytest.raises(ProviderError) as excinfo:
        agent.run_turn([], _user(), provider, Catalog(), _TURN)

    err = excinfo.value
    assert err.telemetry is not None
    assert err.telemetry.has_calls()
    assert len(err.telemetry.calls) == 1
    stub = err.telemetry.calls[0]
    assert stub.input_tokens == 0
    assert stub.output_tokens == 0
    assert stub.est_cost_usd is None
    assert stub.est_cost_eur is None


def test_provider_error_stub_records_model_id_when_known():
    """Der Stub-Call trägt die Modell-ID des Anbieters — die spätere Diagnose
    kann so unterscheiden, welcher Anbieter ausgefallen ist."""

    class ProviderWithModel:
        _model = "claude-haiku-4-5"

        def generate(self, request):
            raise ProviderError("503")

    with pytest.raises(ProviderError) as excinfo:
        agent.run_turn([], _user(), ProviderWithModel(), Catalog(), _TURN)

    assert excinfo.value.telemetry.calls[0].model_id == "claude-haiku-4-5"


# --- Adapter ohne Usage (alter Mock) -------------------------------------

def test_response_without_usage_records_no_call():
    """Ein älterer Provider/Mock liefert kein `usage` (siehe FakeProvider in
    bestehenden Tests). Der Wrapper schreibt dann KEINEN ProviderCall —
    sonst läge ein nichtssagender »tokens=0, est_cost=None«-Eintrag in
    der DB und der Suffix wäre Format-Geräusche. Reale ClaudeProvider-
    Antworten haben immer Usage; nur Test-Doppelungen treffen diesen Pfad.
    Bestehende Orchestrierungs-Tests bleiben so unverändert grün."""
    provider = FakeProvider([text_response("Antwort.")])
    result = agent.run_turn([], _user(), provider, Catalog(), _TURN)
    assert result.telemetry is not None
    assert not result.telemetry.has_calls()


# --- Proposal-Pfad: Telemetrie auch hier ---------------------------------

def test_proposal_path_carries_telemetry():
    """Ein Vorschlag (schreibende Aufgabe) entsteht aus mind. einem
    Provider-Call. Die Telemetrie kommt mit AgentResult mit, damit die
    Orchestrierung sie persistieren und den Suffix anhängen kann."""
    from fakes import FakeWriteTask
    write = FakeWriteTask(name="termin_eintragen", summary="Termin",
                          result="erledigt")
    catalog = Catalog()
    catalog.register(write)
    resp = GenerationResponse(
        text="", task_calls=[task_call_response("termin_eintragen").task_calls[0]],
        usage=ProviderUsage(input_tokens=150, output_tokens=20,
                            cache_read_tokens=0, cache_creation_tokens=0,
                            model_id="claude-opus-4-7"))
    provider = FakeProvider([resp])

    result = agent.run_turn([], _user("eintragen?"), provider, catalog, _TURN)

    assert result.proposal is not None
    assert result.telemetry is not None
    assert len(result.telemetry.calls) == 1
