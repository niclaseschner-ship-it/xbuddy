"""Hörspiel-Buddy — Recherche-Vorschritt (HSP-57/HSP-58).

Ein **Vorschritt** vor dem bestehenden Single-Shot der Folgen-Erzeugung: er
liefert einen **Fakten+Quellen-Block**, der in den `complete_structured`-Single-
Shot (`llm_service.py`) gespeist wird. Der Single-Shot-Vertrag bleibt
**unverändert** (HSP-57).

## Form B1 (T1371, ratifiziert 2026-07-05/06; T1511-Motor-Umstellung)
Die Recherche läuft über **EINEN** `get_agent`-Call (`tools.llm`) mit aktiviertem
server-seitigem **`web_search`**-Tool (Anthropic-Infra) — **kein** externer
Such-Provider, **kein** neuer ZD-Slot. Der Agent sucht selbst und synthetisiert
zitierte Fakten zum `thema`; wir sammeln daraus den Fakten+Quellen-Block. Der
frühere Tavily-Pfad (Query-Gen → externe Such-Cloud → Distill, zwei Freitext-
Calls + N HTTP-Suchen) ist damit **entfernt** — die Recherche fließt an denselben
Anthropic-Vendor wie die Generierung, keine Dritt-Cloud.

Seit T1511 (#1316 Abriss-3, Weg A) läuft der `web_search`-Call über den
**litellm-Motor** statt über den handgepflegten anthropic-Vendor: der native
`web_search`-Server-Tool-Block wird durch litellm zum Anthropic-Backend
durchgereicht, die Zitat-Detailtiefe (url/title/page_age) + der Such-Zähler
kommen über `provider_specific_fields.web_search_results` /
`usage.server_tool_use.web_search_requests` zurück (litellm-Standardfunktion,
in `_vendor/litellm.py:agent_step` gemappt). Der Recherche-Service baut den
nativen Tool-Block selbst (kein Hand-Vendor-Import mehr) und reicht ihn ins
`tools`-Array; der `.step()`-Output-Vertrag (`web_search`/`web_search_requests`)
ist unverändert (Parität über das Golden-Set belegt, tools/llm/eval).

## HSP-58 — Datenabfluss-Invariante (SICHERHEITSKRITISCH)
Der **einzige** inhaltliche Input dieses Service ist das `thema`. Bible,
Historie, Personen-/Familiennamen fließen hier **nicht** ein und können darum
auch nicht in die web_search-Anfrage geraten (Constitution §3). Der `web_search`-
Call bekommt ausschließlich das `thema` als User-Nachricht; die Suchen laufen
gegen denselben anthropic-Key wie die Folge selbst (keine zusätzliche
Egress-Fläche gegenüber der ohnehin genutzten Generierung).

## Degradation (HSP-58)
Fehlt die Agent-Sicht, deklariert der Slot-Vendor kein `web_search`, oder
liefert der Call keine Suchergebnisse / einen Fehler, liefert `recherchiere()`
ein Ergebnis mit `degraded=True` und **leerem** Block — die Folge wird dann
**ohne** Recherche generiert. Kein harter Abbruch; ein Log-Marker hält den Fall
fest.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# HSP-58: N-Suchen hart gedeckelt (Vorschlag 3–5, an `tiefe` gekoppelt). Der
# Wert wird als `max_uses` an das web_search-Tool gereicht — die Anthropic-Infra
# führt NIE mehr als `max_uses` Suchen aus (harte obere Schranke der Egress-Menge).
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

# LLMP-3 7. Capability: nur ein Slot-Vendor, der `web_search` deklariert
# (litellm→Anthropic-Backend), trägt den Recherche-Vorschritt. Fehlt sie
# (Mistral-Slot), degradiert der Vorschritt sauber (kein Silent-Send eines
# unbekannten Tools).
WEB_SEARCH_CAPABILITY = "web_search"

# T1511 (#1316 Abriss-3, Weg A): das server-seitige web_search-Tool wird als
# Eintrag im `tools`-Array deklariert (kein Client-tool_use). Version
# `web_search_20260209` (Opus 4.8/4.7/4.6 + Sonnet 4.6). Der Service baut den
# Eintrag selbst (früher: `_vendor.anthropic.web_search_tool`, dieser Hand-Vendor
# ist mit T1511 gelöscht) und reicht ihn ins `tools`-Array; litellm reicht den
# nativen Block zum Anthropic-Backend durch (`agent_step` erkennt Server-Tools am
# `type`-Feld und übersetzt sie NICHT in Function-Tools). `max_uses` deckelt die
# Anzahl der Suchen HART (HSP-58 — N-Suchen gedeckelt).
WEB_SEARCH_TOOL_TYPE = "web_search_20260209"
WEB_SEARCH_TOOL_NAME = "web_search"


def _web_search_tool(*, max_uses: int) -> dict:
    """Baut den nativen `web_search`-Server-Tool-Eintrag fürs `tools`-Array (T1511).

    Reiner Dict (keine SDK-Typ-Abhängigkeit); litellm reicht ihn ins Anthropic-
    Backend durch. `max_uses` klemmt die Egress-Menge hart (HSP-58); der Konsument
    reicht bereits einen geklemmten Wert (`_n_fuer_tiefe`).
    """
    return {
        "type": WEB_SEARCH_TOOL_TYPE,
        "name": WEB_SEARCH_TOOL_NAME,
        "max_uses": max_uses,
    }


def _n_fuer_tiefe(tiefe: str) -> int:
    n = _TIEFE_ZU_N.get((tiefe or "").strip().lower(), _DEFAULT_N)
    return max(MIN_SUCHEN, min(MAX_SUCHEN, n))


@dataclass
class RechercheErgebnis:
    """Ergebnis des Recherche-Vorschritts (HSP-57).

    - `block` — der Fakten+Quellen-Block (Markdown) für den Single-Shot; leer
      bei Degradation oder wenn keine Treffer.
    - `quellen` — die genutzten Quellen-URLs (für den META-Block, HSP-60).
    - `suchen_count` — Zähler `suchen_pro_folge` (HSP-60) = Anzahl der von der
      web_search-Infra ausgeführten Suchen (`web_search_requests`).
    - `degraded` — True, wenn ohne Recherche generiert wird (HSP-58).
    """

    block: str = ""
    quellen: list = field(default_factory=list)
    suchen_count: int = 0
    degraded: bool = False


# Der System-Prompt für den web_search-Call. Er bekommt AUSSCHLIESSLICH das
# `thema` als User-Nachricht (HSP-58) — Bible/Historie/Namen sind dem Service
# strukturell nicht übergeben.
RESEARCH_SYSTEM_PROMPT = """\
Du bist ein Recherche-Assistent für einen erwachsenen Podcast-Deep-Dive. Du
bekommst ein THEMA und recherchierst mit dem Web-Suche-Werkzeug belastbare
Fakten, Studien und Hintergründe dazu.

Regeln:
- Nutze die Web-Suche für aktuelle, belegbare Fakten zum THEMA.
- Antworte mit knappen Fakten-Stichpunkten (jeweils eine Zeile, beginnend mit
  „- "). Nur, was durch die Suchtreffer gedeckt ist; keine Zahl und keine
  Behauptung dazuerfinden.
- Arbeite ausschließlich mit dem THEMA. Erfinde keine Namen von Privatpersonen,
  keine Familien- oder Kontext-Daten.
- Gib KEINE eigene Quellen-Liste aus — die Quellen werden separat erfasst.
"""


def _format_block(fakten_text: str, quellen: list) -> str:
    """Baut den Fakten+Quellen-Block, den `llm_service` in den Single-Shot speist."""
    teile = ["# Recherche (Fakten & Quellen)", "", fakten_text.strip()]
    if quellen:
        teile.append("")
        teile.append("Quellen:")
        teile.extend("- %s" % u for u in quellen)
    return "\n".join(teile).strip()


def recherchiere(*, thema: str, agent, tiefe: str = "mittel"
                 ) -> RechercheErgebnis:
    """Führt den Recherche-Vorschritt über web_search aus (HSP-57, Form B1).

    `thema` ist der EINZIGE inhaltliche Input (HSP-58 — kein Bible/Historie/
    Namen). `agent` ist eine `tools.llm`-`get_agent`-Sicht (mit `.step(system,
    messages, tools)` und `.capabilities`); im Test eine Doppelung. `tiefe`
    koppelt an `max_uses` (N-Suchen hart gedeckelt).

    Degradation (HSP-58): leeres thema / keine Agent-Sicht / Slot-Vendor ohne
    `web_search` / Call-Fehler / keine Suchergebnisse → `degraded=True`, leerer
    Block, kein Abbruch.
    """
    thema = (thema or "").strip()
    if not thema:
        logger.info("recherche: leeres thema — ohne Recherche (degradiert)")
        return RechercheErgebnis(degraded=True)

    if agent is None:
        logger.warning(
            "recherche: keine Agent-Sicht (Slot/Key fehlt?) — Folge ohne "
            "Recherche (degradiert, HSP-58)")
        return RechercheErgebnis(degraded=True)

    # HSP-58 / LLMP-3: das opt-in web_search-Tool NUR aktivieren, wenn der
    # Slot-Vendor die Capability deklariert (Anthropic ja, Mistral nein). Sonst
    # degradieren — kein Silent-Send eines dem Vendor unbekannten Server-Tools.
    caps = getattr(agent, "capabilities", frozenset())
    if WEB_SEARCH_CAPABILITY not in caps:
        logger.warning(
            "recherche: Slot-Vendor deklariert kein '%s' — Folge ohne Recherche "
            "(degradiert, HSP-58)", WEB_SEARCH_CAPABILITY)
        return RechercheErgebnis(degraded=True)

    n = _n_fuer_tiefe(tiefe)

    # T1511: der Konsument baut den nativen web_search-Server-Tool-Eintrag selbst
    # und reicht ihn ins tools-Array (max_uses deckelt die Suchen hart). litellm
    # reicht den Block zum Anthropic-Backend durch; kein Hand-Vendor-Import mehr.
    tools = [_web_search_tool(max_uses=n)]
    try:
        out = agent.step(
            system=RESEARCH_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": thema}],
            tools=tools,
        )
    except Exception as e:  # web_search-/Provider-Fehler reißt NICHT ab (Degradation)
        logger.warning("recherche: web_search-Call fehlgeschlagen (%s) — degradiert", e)
        return RechercheErgebnis(degraded=True)

    quellen_roh = out.get("web_search") or []
    suchen_count = int(out.get("web_search_requests") or 0)
    quellen = [q["url"] for q in quellen_roh if isinstance(q, dict) and q.get("url")]
    fakten = (out.get("text") or "").strip()

    if not quellen or not fakten:
        # HSP-58: web_search leer / kein Fakten-Text → keine belegte Recherche.
        logger.info(
            "recherche: keine belegten Treffer (suchen=%d, quellen=%d) — ohne "
            "Recherche (degradiert)", suchen_count, len(quellen))
        return RechercheErgebnis(suchen_count=suchen_count, degraded=True)

    block = _format_block(fakten, quellen)
    logger.info("recherche: suchen_pro_folge=%d, quellen=%d",
                suchen_count, len(quellen))
    return RechercheErgebnis(
        block=block, quellen=quellen, suchen_count=suchen_count, degraded=False)
