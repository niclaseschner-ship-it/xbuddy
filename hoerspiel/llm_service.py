"""Hörspiel-Buddy — LLM-Service (HSP-11/HSP-16/HSP-56..60).

Zwei Funktionen, beide einen LLM-Call:

  - `erzeuge_folgen_vorschlag` — zielgruppe-bewusster System-Prompt
    (`geschichtenbuddy-kind.md` / `geschichtenbuddy-erwachsen.md`, HSP-56) +
    Bible + Folgen-Historie als Kontext, Vorschau aus Idee. Für
    `zielgruppe:erwachsen` läuft ein **Recherche-Vorschritt** (HSP-57) vor dem
    Single-Shot; der Single-Shot-Vertrag (`complete_structured`) bleibt
    unverändert.
  - `erzeuge_synopse` — kurzer LLM-Pass für den Historie-Eintrag (Q2 vom
    Orchestrator: zweiter LLM-Call nach erfolgreicher TTS-Pipeline).

Beide Funktionen lassen den Provider als Argument hineinreichen. Der Caller
(main.py / album_builder) hält den Provider; hier kein Modell-Pin.
"""

import logging
import os
from typing import Any

from . import research_service
from .providers.base import LLMProvider

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
# HSP-56: zwei zielgruppe-bewusste Prompt-Dateien. Die Kind-Datei ist die
# byte-gleiche Umbenennung der früheren `geschichtenbuddy.md` (Golden/Diff-Guard
# — mia/finn-Folgen bleiben identisch).
PROMPT_KIND = os.path.join(HERE, "prompts", "geschichtenbuddy-kind.md")
PROMPT_ERWACHSEN = os.path.join(HERE, "prompts", "geschichtenbuddy-erwachsen.md")
# Rückwärtskompatibler Alias — Alt-Referenzen auf die Kind-Datei (Default).
PROMPT_GESCHICHTENBUDDY = PROMPT_KIND

ZIELGRUPPE_ERWACHSEN = "erwachsen"

# HSP-45 / #1263 / T1336 — Serien-Rahmung instanz-neutral (REGRESSION-GUARD).
# geschichtenbuddy-kind.md ist entkernt (kein „Mia (4 Jahre)", kein fixer Serien-Name):
# die Instanz-Rahmung reicht `_build_user_context` als „# Instanz-Kontext"-Block nach.
# T1336: DEFAULT_SERIEN_RAHMEN ist jetzt leer — `_build_user_context` lässt die
# „Serie:"-Zeile bei leerem serien_name weg (minimal-neutral, kein Mia-Leak für finn).
# Instanzen (mia/finn/emil) tragen ihren serien_name ausschließlich via instance.json;
# der Orchestrator (T1336-Deploy) provisioniert die Datei-Werte.
DEFAULT_SERIEN_RAHMEN = ""  # instanz-neutral seit T1336 (kein Mia-Leak)
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

# HSP-56/HSP-60: die Erwachsen-Variante ERGÄNZT das Kind-Schema um den
# strukturierten META-Block (`these`/`schnitt`/`quellen[]`/`begriffe_neu[]`).
# Das Kind-Schema (`FOLGEN_INPUT_SCHEMA`) bleibt BYTE-GLEICH — der Kind-Pfad
# sieht nie das `meta`-Feld (mia/finn unverändert). Nur der erwachsen-Pfad
# reicht dieses Schema in `complete_structured`.
_META_SCHEMA = {
    "type": "object",
    "properties": {
        "these": {
            "type": "string",
            "description": "Zentrale These der Folge in einem Satz.",
        },
        "schnitt": {
            "type": "string",
            "description": "Inhaltlicher Bogen/Schnitt der Folge (1–2 Sätze).",
        },
        "quellen": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Genutzte Quellen (URLs) aus dem Recherche-Block.",
        },
        "begriffe_neu": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Neu eingeführte Fachbegriffe für spätere Folgen.",
        },
    },
    "required": ["these", "schnitt", "quellen", "begriffe_neu"],
}
FOLGEN_INPUT_SCHEMA_ERWACHSEN = {
    "type": "object",
    "properties": {
        **FOLGEN_INPUT_SCHEMA["properties"],
        "meta": _META_SCHEMA,
    },
    "required": [*FOLGEN_INPUT_SCHEMA["required"], "meta"],
}


class LLMServiceError(Exception):
    """LLM-Antwort konnte nicht in die erwartete Form übersetzt werden."""


def _load_system_prompt(zielgruppe: str = "kind") -> str:
    """Lädt den zielgruppe-bewussten System-Prompt (HSP-56).

    `zielgruppe:erwachsen` → `geschichtenbuddy-erwachsen.md` (Dialog-Skript +
    düster + META); alles andere (Default `kind`) → `geschichtenbuddy-kind.md`
    (byte-gleiche Umbenennung der alten Datei — mia/finn unverändert).
    """
    pfad = (PROMPT_ERWACHSEN
            if (zielgruppe or "").strip().lower() == ZIELGRUPPE_ERWACHSEN
            else PROMPT_KIND)
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def _build_user_context(idee: str, bible: str, historie: str,
                        naechste_nummer: int, *,
                        name: str = "", alter: "int | None" = None,
                        ton: str = "", perspektive: str = "",
                        serien_name: str = "",
                        recherche_block: str = "") -> str:
    """Baut den User-Kontext (HSP-11) inkl. Instanz-Rahmung (HSP-45).

    Der „# Instanz-Kontext"-Block ersetzt die früher im Template hartkodierten
    Angaben (Kind-Name, Alter, Serien-Name) — so nennt eine emil-Folge nie
    Leerer serien_name → keine „Serie:"-Zeile (DEFAULT_SERIEN_RAHMEN='' neutral, T1336/OPEN-HSP-W).
    Die Idee-Rückfall-Zeile ist instanz-neutral; kein fester Mia-/Serien-Default.

    `recherche_block` (HSP-57): der Fakten+Quellen-Block des Recherche-
    Vorschritts. Leer (Kind-Pfad / Degradation) → der Kontext ist BYTE-GLEICH
    zur früheren Form (kein Anhang), sonst wird der Block am Ende angefügt.
    """
    name = (name or "").strip()
    # T1336: serien_name leer → „Serie:"-Zeile entfällt (minimal-neutral, kein Mia-Leak).
    # Instanz muss serien_name via instance.json setzen; DEFAULT_SERIEN_RAHMEN = "" (neutral).
    serien_name = (serien_name or "").strip()
    ton = (ton or "").strip() or DEFAULT_TON
    perspektive = (perspektive or "").strip() or DEFAULT_PERSPEKTIVE

    kontext = ["# Instanz-Kontext (verbindlich)"]
    if serien_name:
        kontext.append("Serie: %s" % serien_name)
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
    # HSP-57: Recherche-Block NUR anhängen, wenn vorhanden — sonst bleibt der
    # Kind-Kontext byte-gleich zur Alt-Form (Golden-Guard).
    if recherche_block.strip():
        parts.extend(["", recherche_block.strip()])
    return "\n".join(parts)


def _default_agent(llm):
    """Holt die `get_agent`-Sicht für den Recherche-Vorschritt vom Provider.

    Form B1 (T1371): die Recherche läuft über EINEN `get_agent`-Call mit
    server-seitigem `web_search` — kein externer Such-Client, kein ZD-Slot mehr.
    Der `LibSingleshotAdapter` (Produktiv-Pfad) baut die Agent-Sicht aus
    demselben Slot/Modell wie den Single-Shot (`recherche_agent()`). Trägt der
    Provider die Methode nicht (Alt-/Test-Doppelung), liefert die Funktion None
    → der Recherche-Vorschritt degradiert (HSP-58).
    """
    fn = getattr(llm, "recherche_agent", None)
    if not callable(fn):
        return None
    return fn()


def _extrahiere_meta(data: dict) -> dict:
    """Zieht den META-Block (HSP-60) defensiv aus der LLM-Antwort.

    Fehlt `meta` oder ist es keine Map, liefert die Funktion einen leeren,
    wohlgeformten META-Block — der Folgen-Pfad reißt an fehlendem META NICHT
    ab (die Folge selbst ist wertvoller als der Historie-Zusatz).
    """
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    quellen = meta.get("quellen")
    begriffe = meta.get("begriffe_neu")
    return {
        "these": str(meta.get("these") or "").strip(),
        "schnitt": str(meta.get("schnitt") or "").strip(),
        "quellen": [str(q).strip() for q in quellen if str(q).strip()]
                   if isinstance(quellen, list) else [],
        "begriffe_neu": [str(b).strip() for b in begriffe if str(b).strip()]
                        if isinstance(begriffe, list) else [],
    }


def format_meta_historie(meta: dict) -> str:
    """Formatiert den META-Block (HSP-60) zur Fortschreibung in folgen-historie.md.

    Liefert einen Markdown-Zusatz (These/Schnitt/Quellen/neue Begriffe), den der
    Historie-Schreiber (`album_builder`) an den Folgen-Eintrag anhängt. Leerer
    META-Block → leerer String (kein Anhang).

    HINWEIS (Whitelist): die tatsächliche Verdrahtung in `album_builder._format_
    historie_entry` liegt AUSSERHALB des T1340-Schreib-Whitelists — dieser
    Formatierer ist die in-scope Naht; die Verdrahtung ist Folge-Schritt.
    """
    if not meta:
        return ""
    zeilen = []
    if meta.get("these"):
        zeilen.append("*These:* %s" % meta["these"])
    if meta.get("schnitt"):
        zeilen.append("*Schnitt:* %s" % meta["schnitt"])
    if meta.get("begriffe_neu"):
        zeilen.append("*Neue Begriffe:* %s" % ", ".join(meta["begriffe_neu"]))
    if meta.get("quellen"):
        zeilen.append("*Quellen:*")
        zeilen.extend("- %s" % q for q in meta["quellen"])
    return "\n".join(zeilen).strip()


def erzeuge_folgen_vorschlag(*, idee: str, bible: str, historie: str,
                             naechste_nummer: int,
                             llm: LLMProvider,
                             name: str = "", alter: "int | None" = None,
                             ton: str = "", perspektive: str = "",
                             serien_name: str = "",
                             zielgruppe: str = "kind",
                             tiefe: str = "mittel",
                             agent=None,
                             recherche=research_service) -> dict[str, Any]:
    """Holt einen Folgen-Vorschlag vom konfigurierten Provider (HSP-11/HSP-56..58).

    Returns dict mit Schlüsseln `titel`, `text`, `folgen-nr-vorschlag` —
    genau die Form, die `POST /folgen-vorschlag` als Response zurückgibt
    (HSP-17). Für `zielgruppe:erwachsen` zusätzlich `meta` (HSP-60).
    Pflichtfelder fehlen → `LLMServiceError`.

    name/alter/ton/perspektive/serien_name (HSP-45, #1263): Instanz-Rahmung der
    AKTIVEN Instanz (aus `config.load_instance`). Fehlen sie (Alt-Aufrufer /
    ungefüllte instance.json), greifen die transitionalen Defaults — mia/finn
    bleiben byte-gleich zur alten Rahmung.

    zielgruppe (HSP-56): wählt den System-Prompt (kind/erwachsen). Nur bei
    `erwachsen` läuft der Recherche-Vorschritt (HSP-57/58).

    HSP-58-Invariante (HART): Der Recherche-Vorschritt läuft AUSSCHLIESSLICH bei
    `zielgruppe:erwachsen` — NIE bei einer Kind-Instanz. Er bekommt als Input
    NUR das `idee`/`thema` — NIE `bible`/`historie`/`name`; so können keine
    Familien-Daten in die web_search-Anfrage geraten (Constitution §3 / RAT-26).

    agent/recherche: Test-Nähte (Doppelung der `get_agent`-Sicht bzw. des
    Recherche-Service); im Produktiv-Pfad holt die Funktion die Agent-Sicht (mit
    server-seitigem `web_search`, Form B1/T1371) lazy vom Provider — Degradation,
    wenn der Provider keine Agent-Sicht trägt oder der Slot-Vendor kein
    `web_search` deklariert.
    """
    ist_erwachsen = (zielgruppe or "").strip().lower() == ZIELGRUPPE_ERWACHSEN
    system = _load_system_prompt(zielgruppe)

    # HSP-57/58: Recherche-Vorschritt NUR für erwachsen. Der Vorschritt bekommt
    # AUSSCHLIESSLICH `idee` als thema — kein bible/historie/name (Datenabfluss-
    # Invariante). Form B1 (T1371): EIN get_agent-Call mit server-seitigem
    # web_search. Degradation (keine Agent-Sicht / kein web_search / Fehler)
    # → leerer Block.
    recherche_block = ""
    if ist_erwachsen:
        rech_agent = agent if agent is not None else _default_agent(llm)
        ergebnis = recherche.recherchiere(
            thema=idee, agent=rech_agent, tiefe=tiefe)
        recherche_block = ergebnis.block
        logger.info(
            "recherche-vorschritt: suchen_pro_folge=%d, degraded=%s",
            ergebnis.suchen_count, ergebnis.degraded)

    user = _build_user_context(
        idee, bible, historie, naechste_nummer,
        name=name, alter=alter, ton=ton, perspektive=perspektive,
        serien_name=serien_name, recherche_block=recherche_block)

    schema = FOLGEN_INPUT_SCHEMA_ERWACHSEN if ist_erwachsen else FOLGEN_INPUT_SCHEMA
    data = llm.complete_structured(
        system, user,
        tool_name=FOLGEN_TOOL_NAME,
        tool_description=FOLGEN_TOOL_DESCRIPTION,
        input_schema=schema,
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
    vorschlag = {
        "titel": str(titel).strip(),
        "text": str(text).strip(),
        "folgen-nr-vorschlag": nr_int,
    }
    if ist_erwachsen:
        vorschlag["meta"] = _extrahiere_meta(data)
    return vorschlag


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
