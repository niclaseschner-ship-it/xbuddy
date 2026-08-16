"""KIBuddy — LLM-Service (KIBUDDY-14/15/16, T865 Buzzword-Refactor).

Orchestriert den LLM-Provider mit Session-Memory (Mehrturn, KIBUDDY-16).
System-Prompt aus Per-Instanz-Datei, je Call frisch gelesen (KIBUDDY-15).

T865: LLM-Antwort ist JSON {antwort, buzzwords:[3]}.
parse_kibuddy_response() extrahiert beides; Fallback bei ungültigem JSON.
"""

import json
import logging
import os

from tools.llm import LLMProvider
from tools.llm import ProviderError as _LLMProviderError  # LLMP-S8 Migration (T1082)

from . import data_io
from .icon_render import validate_buzzwords

# LLMP-S8 additiv-rückrollbar: alter `kibuddy.providers.base.ProviderError` bleibt
# stehen (forbidden_files), und Tests (`FakeLLM` in conftest) werfen ihn weiter.
# Bis der Alt-Pfad nach Spike-Stufe-1-Erfolg gelöscht wird, deckt ein Tuple beide
# Klassen — `except ProviderError` fängt dann egal, welche Klasse fliegt.
from .providers.base import ProviderError as _LegacyProviderError
from .session_memory import SessionMemory

# Tuple, kein Type-Alias: gültig in `except` (CPython 3.13) und kompatibel mit
# `raise` aus beiden Welten. Solange beide Klassen leben, ist das die naht-
# minimale Übergangsform.
ProviderError = (_LLMProviderError, _LegacyProviderError)

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
# Verschärft 2026-06-15 nach Live-Befund: Claude lieferte Prosa-Text + JSON-Fence
# parallel; Parser fiel in Fallback. Anweisung hammert jetzt explizit
# "nur JSON, kein Text davor".
_JSON_OUTPUT_ANWEISUNG = """\

AUSGABE-FORMAT (PFLICHT — KEINE AUSNAHME):

Deine Antwort MUSS mit dem Zeichen `{` beginnen und mit `}` enden.
Kein Text davor, kein Text danach, keine Markdown-Code-Fences (```), keine Erklärung.
Sonst kann das System deine Antwort nicht anzeigen.

Format:
{"antwort": "<deine Antwort, vollständige Sätze, 2-4 Sätze>", "buzzwords": ["<wort1>", "<wort2>", "<wort3>"]}

Genau 3 Buzzwords. Jedes ist EIN deutsches Wort (Substantiv/Verb/Adjektiv im Singular),
das ein zentrales Konzept deiner Antwort trägt. Lowercase, ohne Sonderzeichen.

Beispiel-Korrekt:
{"antwort": "Ein Apfel ist eine Frucht. Hast du heute schon einen gegessen?", "buzzwords": ["apfel", "frucht", "essen"]}

Beispiel-FALSCH (führt zu Anzeigefehler):
Ein Apfel ist eine Frucht.
```json
{"antwort": "Ein Apfel ist eine Frucht.", "buzzwords": ["apfel"]}
```
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


def _extract_json_object(text: str) -> str | None:
    """Sucht den ersten {...}-Block im Text mit balancierten Klammern.

    Robustheit gegen LLM-Output mit Prosa-Vorlauf, Markdown-Fences oder
    Trailing-Text (Live-Befund 2026-06-15: Claude lieferte Antwort als
    Prosa + ```json-Fence; Parser fiel in Fallback).

    Greift: ```json {...} ```, "Prosa {...}", "{...} Prosa", "{...}".
    Returns: JSON-String oder None wenn kein Block gefunden.
    """
    # Suche erste '{', dann zähle Klammern-Balance bis zur schließenden.
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_kibuddy_response(raw: str) -> dict:
    """Parst JSON-Antwort des LLM (T865, AC1; verschärft 2026-06-15).

    Erwartet {"antwort": "...", "buzzwords": ["x","y","z"]}.

    Robustheit (Live-Befund 2026-06-15): LLM liefert manchmal Prosa-Text
    PLUS JSON-Fence parallel ("Das ist der Baum... ```json {...} ```").
    Parser extrahiert deshalb erst den ersten balancierten {...}-Block
    aus dem raw-Text und parst nur den. Fallback bei totalem Fehl-Output:
    raw als antwort, buzzwords leer (defensiv).
    """
    text = raw.strip()
    # 1. Versuch: direkter JSON-Parse (idealer Fall, System-Prompt-konform)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # 2. Versuch: balancierten {...}-Block im Text suchen (gegen Prosa-Vorlauf/Fence)
        json_block = _extract_json_object(text)
        if json_block is None:
            logger.warning(
                "llm-service: kein JSON-Block im LLM-Output gefunden — Fallback (len=%d)",
                len(raw),
            )
            return {"antwort": raw, "buzzwords": []}
        try:
            data = json.loads(json_block)
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "llm-service: extrahierter JSON-Block nicht parsbar — Fallback (len=%d)",
                len(json_block),
            )
            return {"antwort": raw, "buzzwords": []}

    if not isinstance(data, dict):
        logger.warning("llm-service: JSON ist kein Object — Fallback")
        return {"antwort": raw, "buzzwords": []}

    antwort = str(data.get("antwort", "")).strip()
    buzzwords_raw = data.get("buzzwords", []) or []
    buzzwords = validate_buzzwords(buzzwords_raw)
    return {"antwort": antwort, "buzzwords": buzzwords}


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
    # LOG-3: Kind-Frage ist Kind-Sprachinhalt — nicht auf INFO. history_len
    # bleibt (Diagnose: mit wie viel Kontext lief der Call?); der Wortlaut
    # selbst ist nur auf DEBUG erreichbar (LOG-2-Override-Bahn).
    logger.info("llm-service: frage erhalten (%d Zeichen) history_len=%d",
                len(frage_text), len(turns))
    logger.debug("llm-service: frage='%s'", frage_text[:60])

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

    # LOG-3: Antwort-Wortlaut UND die daraus extrahierten Buzzwords sind
    # Kind-Sprachinhalt (die Buzzwords sind woertliche Themen-Woerter aus dem
    # Gespraech) — nicht auf INFO. Laengen/Anzahl bleiben als Diagnose-Signal;
    # der Inhalt selbst ist nur auf DEBUG erreichbar (LOG-2-Override-Bahn).
    logger.info(
        "llm-service: antwort erhalten (%d Zeichen) buzzwords=%d",
        len(antwort_text),
        len(buzzwords),
    )
    logger.debug(
        "llm-service: antwort='%s' buzzwords=%r",
        antwort_text[:80],
        buzzwords,
    )
    return {"antwort": antwort_text, "buzzwords": buzzwords}
