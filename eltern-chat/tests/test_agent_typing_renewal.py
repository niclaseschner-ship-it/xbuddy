"""Tests für den Typing-Renewal-Thread — Issue #165.

Prüft die drei Akzeptanzkriterien:
  AC1: Bei einem >5 s dauernden provider.generate liegt mindestens ein zweites
       send_chat_action('typing') zwischen Start und Ende.
  AC2: Thread-Fehler (z. B. TelegramError) brechen den Turn NICHT ab.
  AC3: Thread terminiert nach generate-Return (kein Leak, kein post-Reply-typing).
"""

import time
import threading

import pytest

import agent
from fakes import FakeProvider, text_response
from model import Message, TextBlock
from tasks import Catalog, TurnContext
from telegram import TelegramError


_TURN = TurnContext(chat_id=42)


def _user(text="eine Anfrage"):
    return Message("user", [TextBlock(text)])


# -- AC1: zweites chat_action während langem Provider-Call --------------

def test_AC1_renewal_fires_during_slow_provider_call():
    """AC1: Dauert provider.generate > RENEWAL_INTERVAL, löst der Renewal-Thread
    mindestens einen weiteren send_chat_action-Aufruf aus.

    Mechanismus: FakeProvider schläft länger als das Renewal-Intervall — der
    Hintergrund-Thread ruft den Renewer in dieser Zeit mindestens einmal auf.
    """
    renewal_calls = []

    # Intervall auf 0.1 s kürzen — sonst würde der Test 4 s dauern.
    original = agent._TYPING_RENEWAL_INTERVAL
    agent._TYPING_RENEWAL_INTERVAL = 0.1

    class SlowProvider:
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            time.sleep(0.35)   # drei Renewal-Zyklen à 0.1 s abwarten
            from model import GenerationResponse
            return GenerationResponse(text="Fertig.", task_calls=[])

    provider = SlowProvider()

    try:
        result = agent.run_turn(
            [], _user(), provider, Catalog(), _TURN,
            chat_action_renewer=lambda: renewal_calls.append("typing"))
    finally:
        agent._TYPING_RENEWAL_INTERVAL = original

    assert result.reply_text == "Fertig."
    # Mindestens ein Renewal-Aufruf zwischen Start und Ende.
    assert len(renewal_calls) >= 1, (
        "Erwartet mindestens 1 Renewal-Aufruf, erhalten: %d" % len(renewal_calls))


# -- AC2: Renewer-Fehler bricht den Turn nicht ab -----------------------

def test_AC2_renewer_telegram_error_does_not_abort_turn():
    """AC2: Wirft der Renewer TelegramError, läuft der Turn trotzdem durch.

    Der Renewal-Thread schluckt Exceptions (Komfort, kein Gate).
    """
    original = agent._TYPING_RENEWAL_INTERVAL
    agent._TYPING_RENEWAL_INTERVAL = 0.05

    class SlowProvider:
        def generate(self, _request):
            time.sleep(0.2)
            from model import GenerationResponse
            return GenerationResponse(text="Antwort trotz Fehler.", task_calls=[])

    def failing_renewer():
        raise TelegramError("sendChatAction fehlgeschlagen: Netz weg")

    try:
        result = agent.run_turn(
            [], _user(), SlowProvider(), Catalog(), _TURN,
            chat_action_renewer=failing_renewer)
    finally:
        agent._TYPING_RENEWAL_INTERVAL = original

    # Der Turn liefert trotz Renewer-Fehler eine Antwort.
    assert result.reply_text == "Antwort trotz Fehler."


def test_AC2_renewer_arbitrary_exception_does_not_abort_turn():
    """AC2: Auch ein RuntimeError im Renewer bricht den Turn nicht ab."""
    original = agent._TYPING_RENEWAL_INTERVAL
    agent._TYPING_RENEWAL_INTERVAL = 0.05

    class SlowProvider:
        def generate(self, _request):
            time.sleep(0.15)
            from model import GenerationResponse
            return GenerationResponse(text="ok", task_calls=[])

    call_count = [0]

    def flaky_renewer():
        call_count[0] += 1
        raise RuntimeError("Test-Ausnahme")

    try:
        result = agent.run_turn(
            [], _user(), SlowProvider(), Catalog(), _TURN,
            chat_action_renewer=flaky_renewer)
    finally:
        agent._TYPING_RENEWAL_INTERVAL = original

    assert result.reply_text == "ok"
    # Renewer wurde tatsächlich aufgerufen (und hat geworfen), Turn lief durch.
    assert call_count[0] >= 1


# -- AC3: Thread terminiert nach generate-Return (kein Leak) ------------

def test_AC3_renewal_thread_stops_after_generate_returns():
    """AC3: Nach generate-Return kommen keine weiteren Renewal-Aufrufe mehr.

    Prüfmethode: Renewal-Calls NACH der Antwort werden in einer zweiten Liste
    aufgezeichnet. Nach einer kurzen Wartezeit muss diese Liste leer sein.
    """
    original = agent._TYPING_RENEWAL_INTERVAL
    agent._TYPING_RENEWAL_INTERVAL = 0.05

    generate_returned = threading.Event()
    post_return_calls = []

    def renewer():
        if generate_returned.is_set():
            post_return_calls.append("post-return-typing")

    class SlowProvider:
        def generate(self, _request):
            time.sleep(0.15)
            from model import GenerationResponse
            return GenerationResponse(text="fertig", task_calls=[])

    try:
        result = agent.run_turn(
            [], _user(), SlowProvider(), Catalog(), _TURN,
            chat_action_renewer=renewer)
        # Jetzt ist generate zurückgekehrt — Event setzen.
        generate_returned.set()
        # Etwas warten: wäre der Thread noch aktiv, käme jetzt ein Aufruf.
        time.sleep(0.2)
    finally:
        agent._TYPING_RENEWAL_INTERVAL = original

    assert result.reply_text == "fertig"
    assert post_return_calls == [], (
        "Renewal-Thread rief nach generate-Return noch %d Mal an"
        % len(post_return_calls))


# -- Kombinationstest: before_provider_call + chat_action_renewer -------

def test_both_hooks_can_be_active_simultaneously():
    """before_provider_call und chat_action_renewer sind unabhängig — beide
    können gleichzeitig gesetzt sein, ohne sich gegenseitig zu stören."""
    original = agent._TYPING_RENEWAL_INTERVAL
    agent._TYPING_RENEWAL_INTERVAL = 0.05

    before_calls = []
    renewal_calls = []

    class SlowProvider:
        def generate(self, _request):
            time.sleep(0.15)
            from model import GenerationResponse
            return GenerationResponse(text="ok", task_calls=[])

    try:
        result = agent.run_turn(
            [], _user(), SlowProvider(), Catalog(), _TURN,
            before_provider_call=lambda: before_calls.append("before"),
            chat_action_renewer=lambda: renewal_calls.append("renewal"))
    finally:
        agent._TYPING_RENEWAL_INTERVAL = original

    assert result.reply_text == "ok"
    assert before_calls == ["before"]   # genau einmal vor dem Provider-Call
    assert len(renewal_calls) >= 1      # mindestens ein Renewal während des Calls


# -- Keine Regression: ohne Renewer läuft der Loop unverändert ----------

def test_no_renewer_run_turn_works_as_before():
    """Regression: ohne `chat_action_renewer` verhält sich run_turn identisch
    zu vor Issue #165 — kein Thread, kein Overhead."""
    provider = FakeProvider([text_response("Hallo!")])
    result = agent.run_turn([], _user(), provider, Catalog(), _TURN)
    assert result.reply_text == "Hallo!"
    assert result.proposal is None
