"""Hörspiel-Buddy — LLM-Service (HSP-11/HSP-16).

Zwei Funktionen, beide einen LLM-Call:

  - `erzeuge_folgen_vorschlag` — System-Prompt `geschichtenbuddy.md` +
    Bible + Folgen-Historie als Kontext, Vorschau aus Idee.
  - `erzeuge_synopse` — kurzer LLM-Pass für den Historie-Eintrag (Q2 vom
    Orchestrator: zweiter LLM-Call nach erfolgreicher TTS-Pipeline).

Beide Funktionen lassen den Provider als Argument hineinreichen. Der Caller
(main.py / album_builder) hält den Provider; hier kein Modell-Pin.
"""

import logging
import os
from typing import Any

from .providers.base import LLMProvider

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_GESCHICHTENBUDDY = os.path.join(HERE, "prompts", "geschichtenbuddy.md")

# HSP-45 / #1263 — Name-Drift-Fix (REGRESSION-GUARD).
# geschichtenbuddy.md ist entkernt (kein „Mia (4 Jahre)", kein fixer Serien-Name):
# die Instanz-Rahmung reicht `_build_user_context` als „# Instanz-Kontext"-Block
# nach. Diese transitionalen Defaults IM CODE (nicht im Prompt-Template) fangen den
# Fall ab, dass instance.json (mia/finn) die Felder noch NICHT trägt — so bleiben
# mia/finn byte-gleich zur alten, fest verdrahteten Serien-Rahmung, bis die Daten
# gepflegt sind. Sobald instance.json serien_name/ton/perspektive setzt, gewinnt die
# Instanz (emil trägt seine eigene Rahmung, kein Mia/Finn-Leak).
DEFAULT_SERIEN_RAHMEN = (
    "Stigi, Malini & Vögelchen — Geschichten aus dem Garten im Mustertal")
DEFAULT_TON = "warmherzig, ruhig, kindgerecht; kurze Sätze, konkrete Bilder"
DEFAULT_PERSPEKTIVE = "auktorial, nah bei den Figuren"


# Strukturiertes Antwort-Schema für HSP-11. Anthropic tool_use erzwingt
# wohlgeformte Felder — vermeidet Quoting-Bugs in `text` (wörtliche Rede).
FOLGEN_TOOL_NAME = "folgen_vorschlag"
FOLGEN_TOOL_DESCRIPTION = (
    "Übergibt den fertig geschriebenen Folgen-Vorschlag an den "
    "Hörspiel-Buddy. Wird vom Buddy parsebar gemacht — antworte "
    "ausschließlich über diesen Tool-Call."
)
FOLGEN_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "titel": {
            "type": "string",
            "description": "Der Folgen-Titel ohne 'Folge <N>: '-Präfix",
        },
        "folgen-nr-vorschlag": {
            "type": "integer",
            "description": "Vorgeschlagene fortlaufende Nummer (>0)",
        },
        "text": {
            "type": "string",
            "description": (
                "Vollständiger Folgentext als Markdown, Absätze durch "
                "doppelten Zeilenumbruch getrennt. Erster Absatz ist "
                "der Titel-Absatz 'Folge <N>: <Titel>.'. Danach die "
                "Story-Absätze."
            ),
        },
    },
    "required": ["titel", "folgen-nr-vorschlag", "text"],
}


class LLMServiceError(Exception):
    """LLM-Antwort konnte nicht in die erwartete Form übersetzt werden."""


def _load_system_prompt() -> str:
    with open(PROMPT_GESCHICHTENBUDDY, encoding="utf-8") as f:
        return f.read()


def _build_user_context(idee: str, bible: str, historie: str,
                        naechste_nummer: int, *,
                        name: str = "", alter: "int | None" = None,
                        ton: str = "", perspektive: str = "",
                        serien_name: str = "") -> str:
    """Baut den User-Kontext (HSP-11) inkl. Instanz-Rahmung (HSP-45).

    Der „# Instanz-Kontext"-Block ersetzt die früher im Template hartkodierten
    Angaben (Kind-Name, Alter, Serien-Name) — so nennt eine emil-Folge nie
    Mia/Finn und eine mia-Folge trägt Mia + den Serien-Namen (#1263).
    Die Idee-Rückfall-Zeile ist instanz-neutral (kein „überrasche Mia" mehr).
    """
    name = (name or "").strip()
    serien_name = (serien_name or "").strip() or DEFAULT_SERIEN_RAHMEN
    ton = (ton or "").strip() or DEFAULT_TON
    perspektive = (perspektive or "").strip() or DEFAULT_PERSPEKTIVE

    kontext = ["# Instanz-Kontext (verbindlich)", "Serie: %s" % serien_name]
    if name:
        wer = "%s (%d Jahre)" % (name, alter) if alter else name
        kontext.append("Für: %s" % wer)
    kontext.append("Ton: %s" % ton)
    kontext.append("Perspektive: %s" % perspektive)

    idee_rueckfall = ("(keine spezifische Idee — überrasche mit einer neuen "
                      "Folge, die zur Serie und zur Historie passt.)")

    parts = [
        *kontext,
        "",
        "# Folgen-Idee (vom Elternteil)",
        idee.strip() or idee_rueckfall,
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


def erzeuge_folgen_vorschlag(*, idee: str, bible: str, historie: str,
                             naechste_nummer: int,
                             llm: LLMProvider,
                             name: str = "", alter: "int | None" = None,
                             ton: str = "", perspektive: str = "",
                             serien_name: str = "") -> dict[str, Any]:
    """Holt einen Folgen-Vorschlag vom konfigurierten Provider (HSP-11).

    Returns dict mit Schlüsseln `titel`, `text`, `folgen-nr-vorschlag` —
    genau die Form, die `POST /folgen-vorschlag` als Response zurückgibt
    (HSP-17). Pflichtfelder fehlen → `LLMServiceError`.

    name/alter/ton/perspektive/serien_name (HSP-45, #1263): Instanz-Rahmung der
    AKTIVEN Instanz (aus `config.load_instance`). Fehlen sie (Alt-Aufrufer /
    ungefüllte instance.json), greifen die transitionalen Defaults — mia/finn
    bleiben byte-gleich zur alten Rahmung.
    """
    system = _load_system_prompt()
    user = _build_user_context(
        idee, bible, historie, naechste_nummer,
        name=name, alter=alter, ton=ton, perspektive=perspektive,
        serien_name=serien_name)
    data = llm.complete_structured(
        system, user,
        tool_name=FOLGEN_TOOL_NAME,
        tool_description=FOLGEN_TOOL_DESCRIPTION,
        input_schema=FOLGEN_INPUT_SCHEMA,
    )

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
