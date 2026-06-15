"""KIBuddy — LLM-Service (KIBUDDY-14/15/16).

Orchestriert den LLM-Provider mit Session-Memory (Mehrturn, KIBUDDY-16).
System-Prompt aus Per-Instanz-Datei, je Call frisch gelesen (KIBUDDY-15).
"""

import logging
import os

from . import data_io
from .providers.base import LLMProvider, ProviderError
from .session_memory import SessionMemory

logger = logging.getLogger(__name__)

__all__ = ["LLMServiceError", "ProviderError", "beantworte_frage"]

HERE = os.path.dirname(os.path.abspath(__file__))

# Default-Prompt: kindgerecht, sokratisch, 2–4 Sätze (KIBUDDY-15).
DEFAULT_SYSTEM_PROMPT = """\
Du bist KIBuddy, ein freundlicher Wissens-Buddy für Kinder zwischen 4 und 7 Jahren.
Beantworte die Frage des Kindes kindgerecht, neugierig-ermutigend und sokratisch:
Gib zuerst eine klare Antwort (1–2 Sätze), dann stelle eine Rückfrage oder eine
kleine Denk-Anregung, die das Kind weiterdenken lässt.

Regeln:
- Maximal 3–4 kurze Sätze insgesamt.
- Einfache Wörter; keine Fremdwörter ohne Erklärung.
- Nie erschrecken, nie überfordern.
- Antworte immer auf Deutsch.
- Nie das Kind korrigieren, immer wertschätzen.
"""


class LLMServiceError(Exception):
    """LLM-Antwort konnte nicht verarbeitet werden."""


def _load_prompt(data_root: str) -> str:
    """Liest den System-Prompt je Call frisch (KIBUDDY-15, Invalidierungsstrategie)."""
    path = data_io.prompt_path(data_root)
    text = data_io.read_text_or_empty(path)
    if text.strip():
        return text
    logger.info("llm-service: kein Prompt unter %s — Default wird benutzt", path)
    return DEFAULT_SYSTEM_PROMPT


def beantworte_frage(
    *,
    frage_text: str,
    data_root: str,
    memory: SessionMemory,
    llm: LLMProvider,
) -> str:
    """Schickt die Kind-Frage (mit Mehrturn-History) an den LLM (KIBUDDY-14/16).

    Liest den System-Prompt je Call frisch (KIBUDDY-15).
    Schreibt User-Turn + Assistant-Turn in memory.
    Gibt den Antwort-Text zurück. Wirft ProviderError bei Anbieter-Fehler.
    """
    system = _load_prompt(data_root)
    turns = memory.turns()
    logger.info("llm-service: frage='%s' history_len=%d", frage_text[:60], len(turns))

    antwort = llm.complete_multiturn(
        system=system,
        turns=turns,
        user_message=frage_text,
    )

    # Turn-History aktualisieren (KIBUDDY-16).
    memory.append_user(frage_text)
    memory.append_assistant(antwort)

    logger.info("llm-service: antwort='%s'", antwort[:80])
    return antwort
