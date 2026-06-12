"""Hörspiel-Buddy — LLM-Service (HSP-11/HSP-16).

Zwei Funktionen, beide einen LLM-Call:

  - `erzeuge_folgen_vorschlag` — System-Prompt `geschichtenbuddy.md` +
    Bible + Folgen-Historie als Kontext, Vorschau aus Idee.
  - `erzeuge_synopse` — kurzer LLM-Pass für den Historie-Eintrag (Q2 vom
    Orchestrator: zweiter LLM-Call nach erfolgreicher TTS-Pipeline).

Beide Funktionen lassen den Provider als Argument hineinreichen. Der Caller
(main.py / album_builder) hält den Provider; hier kein Modell-Pin.
"""

import json
import logging
import os
import re
from typing import Any

from .providers.base import LLMProvider

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_GESCHICHTENBUDDY = os.path.join(HERE, "prompts", "geschichtenbuddy.md")


class LLMServiceError(Exception):
    """LLM-Antwort konnte nicht in die erwartete Form übersetzt werden."""


def _load_system_prompt() -> str:
    with open(PROMPT_GESCHICHTENBUDDY, encoding="utf-8") as f:
        return f.read()


def _build_user_context(idee: str, bible: str, historie: str,
                        naechste_nummer: int) -> str:
    parts = [
        "# Folgen-Idee (vom Elternteil)",
        idee.strip() or "(keine spezifische Idee — überrasche Paula.)",
        "",
        "# Vorschlag für die Folgen-Nummer",
        "%d (fortlaufend zur Historie)" % naechste_nummer,
        "",
        "# Welt-Bible",
        bible.strip() or "(keine Bible hinterlegt)",
        "",
        "# Folgen-Historie (chronologisch)",
        historie.strip() or "(noch keine Historie)",
    ]
    return "\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    """Pickt das erste JSON-Objekt aus der LLM-Antwort.

    Akzeptiert mit/ohne Code-Fences. Tolerant gegen kleinere Drift im LLM-
    Output — wirft `LLMServiceError`, wenn kein parsebares Objekt findbar
    ist.
    """
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fallback: erstes { ... } finden
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise LLMServiceError("LLM-Antwort enthält kein JSON-Objekt")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMServiceError("LLM-JSON nicht parsebar: %s" % e) from e


def erzeuge_folgen_vorschlag(*, idee: str, bible: str, historie: str,
                             naechste_nummer: int,
                             llm: LLMProvider) -> dict[str, Any]:
    """Holt einen Folgen-Vorschlag vom konfigurierten Provider (HSP-11).

    Returns dict mit Schlüsseln `titel`, `text`, `folgen-nr-vorschlag` —
    genau die Form, die `POST /folgen-vorschlag` als Response zurückgibt
    (HSP-17). Pflichtfelder fehlen → `LLMServiceError`.
    """
    system = _load_system_prompt()
    user = _build_user_context(idee, bible, historie, naechste_nummer)
    raw = llm.complete(system, user)
    data = _extract_json(raw)

    titel = data.get("titel")
    text = data.get("text")
    nr = data.get("folgen-nr-vorschlag", data.get("folgen_nr_vorschlag"))
    if not titel or not text or nr is None:
        raise LLMServiceError(
            "LLM-Vorschlag fehlt Pflichtfeld (titel/text/folgen-nr-vorschlag)")
    try:
        nr_int = int(nr)
    except (TypeError, ValueError) as e:
        raise LLMServiceError("folgen-nr-vorschlag keine Zahl: %r" % nr) from e
    return {
        "titel": str(titel).strip(),
        "text": str(text).strip(),
        "folgen-nr-vorschlag": nr_int,
    }


SYNOPSE_PROMPT = """\
Du fasst eine gerade fertig gestellte Hörspiel-Folge in 2–3 Sätzen zusammen,
für die Folgen-Historie. Ein Satz nennt das Thema, ein Satz benennt die
zentrale Wende oder Erkenntnis, optional ein Satz zu einem offenen
Erzählfaden für spätere Folgen. Keine Wertung, kein Spoiler-Warnung —
direkter Bericht. Antworte ausschließlich mit der Synopse als Fließtext,
ohne Anführungszeichen, ohne Code-Fences.
"""


def erzeuge_synopse(*, titel: str, text: str, llm: LLMProvider) -> str:
    """Zweiter LLM-Call: Synopse für den Historie-Eintrag (HSP-16, Q2)."""
    user = "# Titel\n%s\n\n# Folgentext\n%s" % (titel.strip(), text.strip())
    raw = llm.complete(SYNOPSE_PROMPT, user)
    return raw.strip()
