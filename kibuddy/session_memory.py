"""KIBuddy — Session-Memory (KIBUDDY-16).

Mehrturn-Konversations-Kontext IN-MEMORY am Service.
NICHT persistent auf Platte (stop_rule: persistente_session_memory_verboten).

Eine einzige globale Session für V1 (kein Cookie/Session-ID-Routing).
Reset löscht die gesamte Turn-Historie.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SessionMemory:
    """In-Memory-Turn-Historie für den KIBuddy (KIBUDDY-16).

    Hält abwechselnd user/assistant-Turns. Bei Reset wird die Liste geleert.
    """

    def __init__(self) -> None:
        self._turns: list[dict[str, Any]] = []

    def turns(self) -> list[dict[str, Any]]:
        """Gibt die aktuelle Turn-Liste zurück (read-only Kopie für den LLM-Call)."""
        return list(self._turns)

    def append_user(self, text: str) -> None:
        """Fügt einen User-Turn (Kind-Frage) hinzu."""
        self._turns.append({"role": "user", "content": text})

    def append_assistant(self, text: str) -> None:
        """Fügt einen Assistant-Turn (Buddy-Antwort) hinzu."""
        self._turns.append({"role": "assistant", "content": text})

    def reset(self) -> None:
        """Löscht die gesamte Turn-Historie (KIBUDDY-16 Reset-Semantik)."""
        count = len(self._turns)
        self._turns.clear()
        logger.info("session-memory: reset, %d turns gelöscht", count)

    def __len__(self) -> int:
        return len(self._turns)
