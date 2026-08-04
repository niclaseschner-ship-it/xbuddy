"""KIBuddy — Session-Memory (KIBUDDY-16).

Mehrturn-Konversations-Kontext IN-MEMORY am Service.
NICHT persistent auf Platte (stop_rule: persistente_session_memory_verboten).

Sessions sind pro Browser-Cookie (kibuddy_sid HttpOnly, SameSite=Lax).
SessionRegistry hält eine Map sid → SessionMemory.
Reset löscht NUR die Session des Aufrufers (die eigene sid).
Audio-Cache bleibt global (per content-Hash dedupliziert, OPEN-KIBUDDY-K).

# OPEN: Session-TTL/Cleanup — veraltete Sessions werden derzeit nicht
# automatisch bereinigt. Wird in OPEN-KIBUDDY-K adressiert.
"""

import logging
import secrets
from typing import Any

logger = logging.getLogger(__name__)

SID_COOKIE = "kibuddy_sid"


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


class SessionRegistry:
    """Hält eine Map sid → SessionMemory (KIBUDDY-16 Cookie-Session).

    Jeder Browser bekommt beim ersten /frage-Request einen kibuddy_sid-Cookie.
    /reset löscht nur die Session des Aufrufers, nicht alle Sessions.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionMemory] = {}

    def get_or_create(self, sid: str) -> SessionMemory:
        """Gibt die SessionMemory für sid zurück, legt sie an wenn nicht vorhanden."""
        if sid not in self._sessions:
            self._sessions[sid] = SessionMemory()
            logger.debug("session-registry: neue session angelegt sid=%s", sid[:8])
        return self._sessions[sid]

    def delete(self, sid: str) -> None:
        """Löscht die Session-Entry für sid (bei /reset)."""
        if sid in self._sessions:
            del self._sessions[sid]
            logger.info("session-registry: session gelöscht sid=%s", sid[:8])

    def new_sid(self) -> str:
        """Erzeugt eine neue, eindeutige Session-ID."""
        return secrets.token_urlsafe(16)

    def __len__(self) -> int:
        return len(self._sessions)
