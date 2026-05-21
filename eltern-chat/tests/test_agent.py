"""Tests für den Agent-Loop — EC-4/EC-7/EC-8/EC-9/EC-10/EC-12/EC-13/EC-14,
E-EC-4/E-EC-5 (Refs #27).

Der KI-Anbieter ist eine kontrollierte Doppelung (EC-17); geprüft wird das
Verhalten auch gegen absichtlich abwegige Modell-Ausgaben (EC-12).
"""

import pytest

import agent
from conftest import FakeProvider, FakeReadTask, FakeWriteTask, task_call_response, text_response
from model import GenerationResponse, Message, ProviderError, TaskCallBlock, TaskResultBlock, TextBlock
from tasks import Catalog


def _user(text="eine Anfrage"):
    return Message("user", [TextBlock(text)])


def _catalog(*tasks):
    cat = Catalog()
    for t in tasks:
        cat.register(t)
    return cat


# -- EC-4: natürlichsprachliche Anfrage, einfache Antwort --------

def test_EC_4_plain_answer_without_task():
    provider = FakeProvider([text_response("Hallo, wie kann ich helfen?")])
    result = agent.run_turn([], _user(), provider, Catalog())
    assert result.reply_text == "Hallo, wie kann ich helfen?"
    assert result.proposal is None


# -- EC-9: lesende Aufgabe läuft direkt --------------------------

def test_EC_9_read_task_runs_and_result_flows_back():
    read = FakeReadTask(name="info_lesen", result="Es sind 22 Grad.")
    provider = FakeProvider([
        task_call_response("info_lesen", arguments={"ort": "Berlin"}),
        text_response("In Berlin sind es 22 Grad."),
    ])
    result = agent.run_turn([], _user(), provider, _catalog(read))
    # Aufgabe wurde direkt ausgeführt (EC-9) ...
    assert read.run_calls == [{"ort": "Berlin"}]
    # ... das Ergebnis wurde dem Anbieter zurückgespeist ...
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert isinstance(fed_back, TaskResultBlock)
    assert fed_back.content == "Es sind 22 Grad."
    assert fed_back.is_error is False
    # ... und am Ende steht eine fertige Antwort.
    assert result.reply_text == "In Berlin sind es 22 Grad."


def test_EC_9_failing_read_task_is_reported_not_raised():
    read = FakeReadTask(name="info_lesen", result=RuntimeError("Quelle weg"))
    provider = FakeProvider([
        task_call_response("info_lesen"),
        text_response("Das hat leider nicht geklappt."),
    ])
    result = agent.run_turn([], _user(), provider, _catalog(read))
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert fed_back.is_error is True
    assert result.reply_text == "Das hat leider nicht geklappt."


# -- EC-10: schreibende Aufgabe nur nach Bestätigung -------------

def test_EC_10_write_task_yields_proposal_and_is_not_executed():
    write = FakeWriteTask(name="daten_setzen", summary="Termin am Montag eintragen")
    provider = FakeProvider([
        task_call_response("daten_setzen", arguments={"tag": "Montag"})])
    result = agent.run_turn([], _user(), provider, _catalog(write))
    # Es entsteht ein Vorschlag ...
    assert result.proposal is not None
    assert result.proposal.summary == "Termin am Montag eintragen"
    assert result.pending_call.task == "daten_setzen"
    assert result.pending_call.arguments == {"tag": "Montag"}
    # ... propose wurde aufgerufen, execute NICHT (keine Veränderung ohne Bestätigung).
    assert write.propose_calls == [{"tag": "Montag"}]
    assert write.execute_calls == []


def test_EC_12_write_task_not_executed_even_if_model_claims_done():
    """EC-12: gegen abwegige Modell-Ausgabe — das Modell behauptet, die Aufgabe
    sei schon erledigt; ausgeführt wird trotzdem nichts ohne Bestätigung."""
    write = FakeWriteTask(name="daten_setzen")
    provider = FakeProvider([GenerationResponse(
        text="Ich habe das schon erledigt!",
        task_calls=[TaskCallBlock("c1", "daten_setzen", {})])])
    result = agent.run_turn([], _user(), provider, _catalog(write))
    assert result.proposal is not None
    assert write.execute_calls == []


def test_EC_10_failing_propose_is_reported_not_raised():
    write = FakeWriteTask(name="daten_setzen", propose_error=ValueError("Eingabe fehlt"))
    provider = FakeProvider([
        task_call_response("daten_setzen"),
        text_response("Dafür brauche ich noch mehr Angaben."),
    ])
    result = agent.run_turn([], _user(), provider, _catalog(write))
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert fed_back.is_error is True
    assert result.reply_text == "Dafür brauche ich noch mehr Angaben."


# -- EC-7/EC-8/EC-12: Katalog-Grenze gegen abwegige Modell-Ausgabe --

def test_EC_8_unknown_task_is_not_executed_and_reported():
    """EC-8/EC-12: ruft das Modell eine Aufgabe auf, die nicht im Katalog ist,
    wird sie nicht »kreativ« gelöst — die Grenze hängt nicht von der Ausgabe ab."""
    provider = FakeProvider([
        task_call_response("zaubere_geld_herbei"),
        text_response("Das kann ich leider nicht."),
    ])
    result = agent.run_turn([], _user(), provider, Catalog())
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert isinstance(fed_back, TaskResultBlock)
    assert fed_back.is_error is True
    assert "nicht im Katalog" in fed_back.content
    assert result.reply_text == "Das kann ich leider nicht."


def test_EC_7_honest_limit_when_no_task_fits():
    """EC-7: liegt eine Anfrage außerhalb der Aufgaben, antwortet der Agent
    schlicht mit Text — ohne erfundene Fähigkeiten."""
    provider = FakeProvider([text_response("Das gehört nicht zu meinen Aufgaben.")])
    result = agent.run_turn([], _user(), provider, Catalog())
    assert result.reply_text == "Das gehört nicht zu meinen Aufgaben."


# -- EC-13: nur Anfrage-Inhalt + Kontext gehen an den Anbieter ---

def test_EC_13_provider_receives_only_request_and_context():
    history = [Message("user", [TextBlock("frühere Anfrage")]),
               Message("assistant", [TextBlock("frühere Antwort")])]
    user = _user("neue Anfrage")
    provider = FakeProvider([text_response("ok")])
    agent.run_turn(history, user, provider, Catalog())
    sent = provider.requests[0]
    # genau Verlauf + neue Anfrage, nichts darüber hinaus
    assert sent.messages == history + [user]


# -- EC-14: Anbieter nicht erreichbar ----------------------------

def test_EC_14_provider_error_propagates():
    provider = FakeProvider([ProviderError("Zeitüberschreitung")])
    with pytest.raises(ProviderError):
        agent.run_turn([], _user(), provider, Catalog())


# -- E-EC-5: der Loop bricht sauber ab statt endlos zu schleifen --

def test_E_EC_5_loop_stops_at_iteration_limit():
    read = FakeReadTask(name="info_lesen")
    # Der Anbieter ruft in jeder Runde wieder eine Aufgabe auf.
    provider = FakeProvider([task_call_response("info_lesen") for _ in range(2)])
    result = agent.run_turn([], _user(), provider, _catalog(read), max_iterations=2)
    assert result.proposal is None
    assert result.reply_text is not None   # sauberer Abbruch-Hinweis
