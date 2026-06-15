"""KIBuddy — LLM-Service (KIBUDDY-14/15/16, T865 Buzzword-Refactor).

Orchestriert den LLM-Provider mit Session-Memory (Mehrturn, KIBUDDY-16).
System-Prompt aus Per-Instanz-Datei, je Call frisch gelesen (KIBUDDY-15).

T865: LLM-Antwort ist JSON {antwort, buzzwords:[3]}.
parse_kibuddy_response() extrahiert beides; Fallback bei ungültigem JSON.
"""

import json
import logging
import os

from . import data_io
from .icon_render import validate_buzzwords
from .providers.base import LLMProvider, ProviderError
from .session_memory import SessionMemory

logger = logging.getLogger(__name__)

__all__ = ["LLMServiceError", "ProviderError", "beantworte_frage"]

HERE = os.path.dirname(os.path.abspath(__file__))

# Default-Prompt: kindgerecht, sokratisch, 2–4 Sätze (KIBUDDY-15).
# JSON-Ausgabe-Anweisung wird beim Zusammenbau angehängt (T865, AC1).
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

# JSON-Ausgabe-Anweisung wird an jeden System-Prompt angehängt (T865, AC1-System-Prompt-JSON).
_JSON_OUTPUT_ANWEISUNG = """\

AUSGABE-FORMAT (Pflicht): Antworte AUSSCHLIESSLICH als JSON in genau dieser Form:
{
  "antwort": "<deine Antwort, vollständige Sätze, 2-4 Sätze>",
  "buzzwords": ["<wort1>", "<wort2>", "<wort3>"]
}

Genau 3 Buzzwords. Jedes ist EIN deutsches Wort (Substantiv/Verb/Adjektiv im Singular),
das ein zentrales Konzept deiner Antwort trägt. Lowercase, ohne Sonderzeichen.
Kein Text außerhalb des JSON.
"""


class LLMServiceError(Exception):
    """LLM-Antwort konnte nicht verarbeitet werden."""


def _load_prompt(data_root: str) -> str:
    """Liest den System-Prompt je Call frisch (KIBUDDY-15, Invalidierungsstrategie).

    Hängt die JSON-Ausgabe-Anweisung an (T865).
    """
    path = data_io.prompt_path(data_root)
    text = data_io.read_text_or_empty(path)
    base = text.strip() if text.strip() else DEFAULT_SYSTEM_PROMPT
    return base + _JSON_OUTPUT_ANWEISUNG


def parse_kibuddy_response(raw: str) -> dict:
    """Parst JSON-Antwort des LLM (T865, AC1).

    Erwartet {"antwort": "...", "buzzwords": ["x","y","z"]}.
    Robustheit: entfernt Markdown-Code-Fences wenn vorhanden.
    Fallback bei ungültigem JSON: raw als antwort, buzzwords leer.
    """
    text = raw.strip()
    # Markdown-Fence entfernen (manche Modelle wrappen JSON in ```json ... ```)
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
        antwort = str(data.get("antwort", "")).strip()
        buzzwords_raw = data.get("buzzwords", []) or []
        buzzwords = validate_buzzwords(buzzwords_raw)
        return {"antwort": antwort, "buzzwords": buzzwords}
    except (json.JSONDecodeError, AttributeError, ValueError):
        logger.warning("llm-service: LLM lieferte kein valides JSON — Fallback auf raw")
        return {"antwort": raw, "buzzwords": []}


def beantworte_frage(
    *,
    frage_text: str,
    data_root: str,
    memory: SessionMemory,
    llm: LLMProvider,
) -> dict:
    """Schickt die Kind-Frage (mit Mehrturn-History) an den LLM (KIBUDDY-14/16).

    Liest den System-Prompt je Call frisch (KIBUDDY-15).
    Schreibt User-Turn + Assistant-Turn in memory.
    Gibt {"antwort": str, "buzzwords": list[str]} zurück.
    Wirft ProviderError bei Anbieter-Fehler.

    T865: LLM antwortet als JSON; parse_kibuddy_response() extrahiert Felder.
    Memory speichert nur den Antwort-Text (nicht das JSON-Wrapper).
    """
    system = _load_prompt(data_root)
    turns = memory.turns()
    logger.info("llm-service: frage='%s' history_len=%d", frage_text[:60], len(turns))

    raw_response = llm.complete_multiturn(
        system=system,
        turns=turns,
        user_message=frage_text,
    )

    parsed = parse_kibuddy_response(raw_response)
    antwort_text = parsed["antwort"]
    buzzwords = parsed["buzzwords"]

    # Turn-History aktualisiert mit dem Antwort-Text (nicht dem JSON-Wrapper).
    memory.append_user(frage_text)
    memory.append_assistant(antwort_text)

    logger.info(
        "llm-service: antwort='%s' buzzwords=%r",
        antwort_text[:80],
        buzzwords,
    )
    return {"antwort": antwort_text, "buzzwords": buzzwords}
