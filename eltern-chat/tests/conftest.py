"""Gemeinsame Test-Doppelungen für die Eltern-Chat-Suite (EC-17, Refs #27).

Die Tests laufen reproduzierbar und ohne Netz: der KI-Anbieter und der
Telegram-Kanal sind durch kontrollierte Doppelungen ersetzt.
"""

import os
import sys
from dataclasses import dataclass

# eltern-chat/ (eine Ebene über tests/) auf den Importpfad legen.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model import GenerationResponse, TaskCallBlock          # noqa: E402
from tasks import Proposal, ReadTask, WriteTask              # noqa: E402
from telegram import IncomingMessage                         # noqa: E402


@dataclass
class BotAdded:
    """Test-Marker: der Bot wurde einer Gruppe hinzugefügt (ONB-2)."""
    chat_id: object


class FakeProvider:
    """Kontrollierte Doppelung des KI-Anbieters (EC-17).

    Gibt skriptierte `GenerationResponse`-Objekte der Reihe nach zurück; ein
    skriptiertes Exception-Objekt wird stattdessen geworfen.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        assert self._responses, "FakeProvider: keine weitere Antwort skriptiert"
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeReadTask(ReadTask):
    """Eine lesende Test-Aufgabe (EC-9)."""

    def __init__(self, name="info_lesen", result="Ergebnis"):
        super().__init__(name, "Test-Lese-Aufgabe",
                         {"type": "object", "properties": {}})
        self._result = result
        self.run_calls = []

    def run(self, arguments):
        self.run_calls.append(arguments)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeWriteTask(WriteTask):
    """Eine schreibende Test-Aufgabe (EC-10)."""

    def __init__(self, name="daten_setzen", summary="Test-Änderung",
                 result="erledigt", propose_error=None):
        super().__init__(name, "Test-Schreib-Aufgabe",
                         {"type": "object", "properties": {}})
        self._summary = summary
        self._result = result
        self._propose_error = propose_error
        self.propose_calls = []
        self.execute_calls = []

    def propose(self, arguments):
        self.propose_calls.append(arguments)
        if self._propose_error is not None:
            raise self._propose_error
        return Proposal(self._summary)

    def execute(self, arguments):
        self.execute_calls.append(arguments)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeTelegram:
    """Kontrollierte Doppelung des Telegram-Kanals (EC-17)."""

    def __init__(self, members=None):
        # members: dict user_id -> Telegram-getChatMember-Antwort
        self._members = dict(members or {})
        self.sent = []
        self._next_id = 5000

    def extract_message(self, update, bot_username):
        # Tests reichen ein IncomingMessage direkt herein; andere Marker
        # (z. B. BotAdded) sind keine Nachricht.
        return update if isinstance(update, IncomingMessage) else None

    def extract_bot_added(self, update):
        # ONB-2: Tests reichen einen BotAdded-Marker herein.
        return update.chat_id if isinstance(update, BotAdded) else None

    def get_chat_member(self, chat_id, user_id):
        return self._members.get(user_id)

    def send_message(self, chat_id, text, reply_to_message_id=None):
        self._next_id += 1
        self.sent.append({"chat_id": chat_id, "text": text,
                          "reply_to": reply_to_message_id,
                          "message_id": self._next_id})
        return {"message_id": self._next_id}


def make_message(text="hallo", **kw):
    """IncomingMessage mit sinnvollen Defaults für Orchestrierungs-Tests."""
    defaults = dict(
        update_id=1, chat_id=42, chat_type="private", message_id=100,
        from_user_id=7, from_user_name="elternteil", text=text, images=[],
        reply_to_message_id=None, reply_to_from_bot=False, mentions_bot=False)
    defaults.update(kw)
    return IncomingMessage(**defaults)


def text_response(text):
    """Eine Anbieter-Antwort ohne Aufgaben-Aufruf."""
    return GenerationResponse(text=text, task_calls=[])


def task_call_response(task, arguments=None, text="", call_id="call-1"):
    """Eine Anbieter-Antwort, die genau eine Aufgabe aufruft."""
    return GenerationResponse(
        text=text,
        task_calls=[TaskCallBlock(call_id=call_id, task=task,
                                  arguments=arguments or {})])
