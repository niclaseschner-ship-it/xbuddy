"""Hörspiel-Buddy — Recherche-Vorschritt (HSP-57/HSP-58).

Ein **Vorschritt** vor dem bestehenden Single-Shot der Folgen-Erzeugung: er
liefert einen **Fakten+Quellen-Block**, der in den `complete_structured`-Single-
Shot (`llm_service.py`) gespeist wird. Der Single-Shot-Vertrag bleibt
**unverändert** (HSP-57). `get_agent` (agentischer tool_use-Loop) ist bewusst
deferiert.

Ablauf (drei Schritte, zwei LLM-Freitext-Calls + N Tavily-Suchen):

  1. **Query-Gen** (`llm.complete`) — erzeugt aus dem **thema** N Suchanfragen.
  2. **Suche** (`TavilyClient.suche`) — N externe Suchen (hart gedeckelt).
  3. **Distill** (`llm.complete`) — verdichtet die Treffer zu einem Fakten+
     Quellen-Block.

## HSP-58 — Datenabfluss-Invariante (SICHERHEITSKRITISCH)
Der **einzige** inhaltliche Input dieses Service ist das `thema`. Bible,
Historie, Personen-/Familiennamen fließen hier **nicht** ein und können darum
auch nicht in die an Tavily gesendete Suchanfrage geraten (Constitution §3 /
RAT-26). Der Query-Gen-Prompt bekommt ausschließlich das `thema`.

## Degradation (HSP-58)
Fehlt der Tavily-Key oder ist die Such-Cloud nicht erreichbar / Quota
erschöpft, liefert `recherchiere()` ein Ergebnis mit `degraded=True` und
**leerem** Block — die Folge wird dann **ohne** Recherche generiert. Kein
harter Abbruch; ein Log-Marker hält den Fall fest.
"""

import logging
import re
from dataclasses import dataclass, field

from .tavily_client import TavilyError

# Aufzählungs-/Nummern-Präfix am Zeilenanfang ("1. ", "1) ", "- ", "* ", "• ").
_LIST_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")

logger = logging.getLogger(__name__)

# HSP-58: N-Suchen hart gedeckelt (Vorschlag 3–5, an `tiefe` gekoppelt).
# Untere/obere Schranke sind HART — jeder abgeleitete N wird in [MIN, MAX]
# geklemmt, egal was Query-Gen liefert oder welche `tiefe` gewählt ist.
MIN_SUCHEN = 3
MAX_SUCHEN = 5

# Kopplung `tiefe` → N (innerhalb [MIN_SUCHEN, MAX_SUCHEN]). Unbekannte/leere
# `tiefe` fällt auf den mittleren Wert; das Ergebnis wird zusätzlich geklemmt.
_TIEFE_ZU_N = {
    "flach": 3,
    "mittel": 4,
    "tief": 5,
}
_DEFAULT_N = 4


def _n_fuer_tiefe(tiefe: str) -> int:
    n = _TIEFE_ZU_N.get((tiefe or "").strip().lower(), _DEFAULT_N)
    return max(MIN_SUCHEN, min(MAX_SUCHEN, n))


@dataclass
class RechercheErgebnis:
    """Ergebnis des Recherche-Vorschritts (HSP-57).

    - `block` — der Fakten+Quellen-Block (Markdown) für den Single-Shot; leer
      bei Degradation oder wenn keine Treffer.
    - `quellen` — die genutzten Quellen-URLs (für den META-Block, HSP-60).
    - `suchen_count` — Zähler `suchen_pro_folge` (HSP-60).
    - `degraded` — True, wenn ohne Recherche generiert wird (HSP-58).
    """

    block: str = ""
    quellen: list = field(default_factory=list)
    suchen_count: int = 0
    degraded: bool = False


QUERY_GEN_PROMPT = """\
Du bist ein Recherche-Assistent. Du bekommst ein THEMA für einen erwachsenen
Podcast-Deep-Dive und formulierst daraus %(min)d–%(max)d präzise, sachliche
Web-Suchanfragen, die belastbare Fakten, Studien und Hintergründe zum THEMA
finden.

Regeln:
- Jede Suchanfrage steht in einer eigenen Zeile, ohne Nummerierung, ohne
  Aufzählungszeichen.
- Nur sachliche, thema-bezogene Suchbegriffe. Keine Namen von Privatpersonen,
  keine Familien- oder Kontext-Daten erfinden — arbeite ausschließlich mit dem
  THEMA.
- Antworte NUR mit den Suchanfragen, eine pro Zeile, sonst nichts.
"""

DISTILL_PROMPT = """\
Du bekommst Web-Suchtreffer (Titel, URL, Auszug) zu einem Thema. Verdichte sie
zu einem kompakten Fakten+Quellen-Block für einen Podcast-Autor.

Form:
- Zuerst die belastbaren Fakten als knappe Stichpunkte (jeweils eine Zeile,
  beginnend mit „- "). Nur, was durch die Treffer gedeckt ist; keine Zahl und
  keine Behauptung dazuerfinden.
- Danach eine Zeile „Quellen:" gefolgt von den genutzten URLs, je eine pro
  Zeile.

Antworte NUR mit diesem Block, ohne Vorrede.
"""


def _parse_queries(raw: str, n: int) -> list:
    """Parst die Query-Gen-Freitext-Antwort zu maximal `n` Suchanfragen.

    Robustheit: leere Zeilen raus, Aufzählungs-/Nummern-Präfixe strippen,
    Duplikate raus, HART auf `n` deckeln (HSP-58 — nie mehr Suchen als N).
    """
    queries = []
    seen = set()
    for zeile in (raw or "").splitlines():
        # Aufzählungs-/Nummern-Präfixe entfernen (falls das Modell sie doch setzt).
        q = _LIST_PREFIX.sub("", zeile).strip()
        if not q or q.lower() in seen:
            continue
        seen.add(q.lower())
        queries.append(q)
        if len(queries) >= n:
            break
    return queries


def _format_block(fakten_text: str, quellen: list) -> str:
    """Baut den Fakten+Quellen-Block, den `llm_service` in den Single-Shot speist."""
    teile = ["# Recherche (Fakten & Quellen)", "", fakten_text.strip()]
    if quellen:
        teile.append("")
        teile.append("Quellen:")
        teile.extend("- %s" % u for u in quellen)
    return "\n".join(teile).strip()


def recherchiere(*, thema: str, llm, tavily, tiefe: str = "mittel"
                 ) -> RechercheErgebnis:
    """Führt den Recherche-Vorschritt aus (HSP-57).

    `thema` ist der EINZIGE inhaltliche Input (HSP-58 — kein Bible/Historie/
    Namen). `llm` ist ein `LLMProvider` mit `.complete(system, user) -> str`
    (Freitext, HSP-16-Naht) für Query-Gen + Distill. `tavily` ist der
    `TavilyClient` (oder eine Test-Doppelung mit `.suche(query)`).

    Degradation (HSP-58): fehlender Key / Netz-/Quota-Fehler → `degraded=True`,
    leerer Block, kein Abbruch.
    """
    thema = (thema or "").strip()
    if not thema:
        logger.info("recherche: leeres thema — ohne Recherche (degradiert)")
        return RechercheErgebnis(degraded=True)

    if tavily is None:
        logger.warning(
            "recherche: kein Tavily-Client (Key fehlt?) — Folge ohne Recherche "
            "(degradiert, HSP-58)")
        return RechercheErgebnis(degraded=True)

    n = _n_fuer_tiefe(tiefe)

    # Schritt 1: Query-Gen — NUR das thema als Input (HSP-58).
    query_system = QUERY_GEN_PROMPT % {"min": MIN_SUCHEN, "max": MAX_SUCHEN}
    try:
        roh_queries = llm.complete(query_system, thema)
    except Exception as e:  # Query-Gen-Fehler darf nicht abreißen (Degradation)
        logger.warning("recherche: Query-Gen fehlgeschlagen (%s) — degradiert", e)
        return RechercheErgebnis(degraded=True)

    queries = _parse_queries(roh_queries, n)
    if not queries:
        logger.warning("recherche: keine Suchanfragen erzeugt — degradiert")
        return RechercheErgebnis(degraded=True)

    # Schritt 2: N Suchen (hart auf `n` gedeckelt durch _parse_queries).
    treffer = []
    quellen = []
    suchen_count = 0
    for q in queries:
        try:
            ergebnisse = tavily.suche(q)
        except TavilyError as e:
            # HSP-58: Degradation — Netz/Quota/Key-Fehler reißt NICHT ab.
            logger.warning(
                "recherche: Tavily-Suche fehlgeschlagen (%s) — Folge ohne "
                "Recherche (degradiert)", e)
            return RechercheErgebnis(degraded=True, suchen_count=suchen_count)
        suchen_count += 1
        for r in ergebnisse:
            treffer.append(r)
            if r.get("url") and r["url"] not in quellen:
                quellen.append(r["url"])

    if not treffer:
        logger.info("recherche: keine Treffer (suchen=%d) — ohne Recherche",
                    suchen_count)
        return RechercheErgebnis(suchen_count=suchen_count, degraded=True)

    # Schritt 3: Distill (Freitext) → Fakten+Quellen-Block.
    treffer_text = "\n\n".join(
        "Titel: %s\nURL: %s\nAuszug: %s" % (t["title"], t["url"], t["content"])
        for t in treffer)
    try:
        fakten = llm.complete(DISTILL_PROMPT, treffer_text)
    except Exception as e:  # Distill-Fehler darf nicht abreißen (Degradation)
        logger.warning("recherche: Distill fehlgeschlagen (%s) — degradiert", e)
        return RechercheErgebnis(suchen_count=suchen_count, degraded=True)

    block = _format_block(fakten, quellen)
    logger.info("recherche: suchen_pro_folge=%d, quellen=%d",
                suchen_count, len(quellen))
    return RechercheErgebnis(
        block=block, quellen=quellen, suchen_count=suchen_count, degraded=False)
