"""HSP-56..60 — Recherchierte Erwachsenen-Generierung (T1340/T1371).

Belegt den zielgruppe-bewussten Prompt-Schnitt (HSP-56), den Recherche-
Vorschritt über server-seitiges `web_search` (HSP-57, Form B1/T1371), die HARTE
Datenabfluss-Invariante (HSP-58), den Anti-Slop-Self-Check + META-Block
(HSP-59/HSP-60).

T1371-Pivot: der externe Tavily-Client ist entfernt. Die Recherche läuft über
EINEN `get_agent`-Call mit aktiviertem `web_search` (Anthropic-Infra). Die Tests
doppeln die Agent-Sicht (`FakeAgent`) — KEIN Live-Netz. Die Payload-Inspektion
(AC3c) prüft, dass NUR das thema an web_search geht, NIE Bible/Historie/Personen.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from hoerspiel import llm_service, research_service  # noqa: E402
from hoerspiel.providers.base import LLMProvider  # noqa: E402

# ============================================================
#  Doppelungen (kein Netz, kein Live-LLM)
# ============================================================

class FakeLLM(LLMProvider):
    """Deckt den Single-Shot (`complete_structured`, HSP-11). Der Recherche-
    Vorschritt läuft NICHT mehr über diesen Provider, sondern über `agent`
    (get_agent-Sicht mit web_search) — hier separat gedoppelt (`FakeAgent`).
    """

    name = "fake"
    model = "fake-model"

    def __init__(self):
        self.last_structured_user = None
        self.last_structured_schema = None

    def complete_structured(self, system, user, *, tool_name,
                            tool_description, input_schema):
        self.last_structured_user = user
        self.last_structured_schema = input_schema
        antwort = {
            "titel": "Deep Dive",
            "folgen-nr-vorschlag": 1,
            "text": "Folge 1: Deep Dive.\n\nKIM: Los.\n\nRUBEN: Aber.",
        }
        # META nur liefern, wenn das erwachsen-Schema es erlaubt.
        if "meta" in input_schema.get("properties", {}):
            antwort["meta"] = {
                "these": "Die zentrale These.",
                "schnitt": "Der Bogen.",
                "quellen": ["https://example.org/a"],
                "begriffe_neu": ["Qubit"],
            }
        return antwort


class FakeAgent:
    """Doppelung der `get_agent`-Sicht (`.step` + `.capabilities`).

    Merkt sich JEDEN `.step`-Aufruf (AC3c-Payload-Inspektion). `raises` simuliert
    einen web_search-/Provider-Fehler; `caps` steuert das opt-in-Gate (Vendor
    ohne `web_search` → Degradation).
    """

    def __init__(self, *, text="- Fakt A (belegt)", sources=None,
                 requests=None, raises=None, caps=frozenset({"web_search"})):
        self._text = text
        self._sources = sources if sources is not None else [
            {"url": "https://example.org/a", "title": "T", "page_age": None}]
        self._requests = requests
        self._raises = raises
        self.capabilities = caps
        self.step_calls = []          # (system, messages, tools)

    def step(self, system, messages, tools):
        self.step_calls.append((system, messages, tools))
        if self._raises is not None:
            raise self._raises
        req = self._requests if self._requests is not None else len(self._sources)
        return {
            "text": self._text,
            "tool_calls": [],
            "usage": None,
            "web_search": list(self._sources),
            "web_search_requests": req,
        }


def _step_user(agent):
    """Zieht die reine User-Nachricht (das thema) aus dem letzten step-Call."""
    _system, messages, _tools = agent.step_calls[-1]
    return messages[-1]["content"]


def _step_tool_max_uses(agent):
    _system, _messages, tools = agent.step_calls[-1]
    return tools[0]["max_uses"]


class FakeStore:
    """Doppelung der Zugangsdaten-Naht (`get(name)`)."""

    def __init__(self, werte):
        self._werte = dict(werte)

    def get(self, name, default=None):
        return self._werte.get(name, default)


# Bible/Historie mit Familien-Daten — dürfen NIE in die web_search-Anfrage geraten.
_BIBLE_MIT_FAMILIE = ("Mia (4 Jahre) wohnt im Beispieltal. Geheimwort: "
                      "Vögelchen. Finn ist die Katze der Familie Sonntag.")
_HISTORIE_MIT_FAMILIE = "## Folge 1: Mia und Finn im Garten"
_FAMILIEN_TOKEN = ["Mia", "Finn", "Sonntag", "Beispieltal", "Vögelchen",
                   "Geheimwort", "familie"]


# ============================================================
#  HSP-56 — Zielgruppe-Prompt-Schnitt
# ============================================================

def test_load_system_prompt_waehlt_kind_vs_erwachsen():
    """AC1: _load_system_prompt(zielgruppe) wählt die korrekte Datei."""
    kind = llm_service._load_system_prompt("kind")
    erwachsen = llm_service._load_system_prompt("erwachsen")
    assert kind != erwachsen
    # Kind-Prompt ist der klassische GeschichtenBuddy (keine KIM/RUBEN-Pflicht).
    assert "KIM:" not in kind
    # Default (leer/unbekannt) → Kind.
    assert llm_service._load_system_prompt("") == kind
    assert llm_service._load_system_prompt("kinder") == kind


def test_erwachsen_prompt_erzwingt_dialog_duester_und_meta():
    """AC1: erwachsen-Prompt erzwingt KIM:/RUBEN:-Skript, erlaubt düster, META."""
    p = llm_service._load_system_prompt("erwachsen")
    assert "KIM:" in p
    assert "RUBEN:" in p
    assert "düster" in p.lower()
    assert "META" in p
    # Anti-Slop-Self-Check (AC4/HSP-59) steht im Prompt (0 Zusatz-Calls).
    assert "Anti-Slop" in p or "Slop" in p


def test_kind_prompt_byte_gleich_dateipfad():
    """AC1: die Kind-Datei ist die byte-gleiche Umbenennung (Pfad-Umschaltung)."""
    assert llm_service.PROMPT_KIND.endswith("geschichtenbuddy-kind.md")
    assert llm_service.PROMPT_GESCHICHTENBUDDY == llm_service.PROMPT_KIND
    assert os.path.exists(llm_service.PROMPT_KIND)
    assert os.path.exists(llm_service.PROMPT_ERWACHSEN)


# ============================================================
#  HSP-57 — Recherche-Vorschritt (web_search) verdrahtet
# ============================================================

def test_erwachsen_speist_recherche_block_in_single_shot():
    """AC2: web_search-Fakten+Quellen landen im Single-Shot-User-Kontext."""
    llm = FakeLLM()
    agent = FakeAgent()
    vorschlag = llm_service.erzeuge_folgen_vorschlag(
        idee="Quantencomputing und seine Risiken",
        bible="", historie="", naechste_nummer=1, llm=llm,
        zielgruppe="erwachsen", agent=agent)
    # Der Recherche-Block ist im User-Kontext des Single-Shots.
    assert "# Recherche (Fakten & Quellen)" in llm.last_structured_user
    assert "Fakt A (belegt)" in llm.last_structured_user
    assert "https://example.org/a" in llm.last_structured_user
    # Single-Shot-Vertrag: complete_structured mit erwachsen-Schema.
    assert "meta" in llm.last_structured_schema["properties"]
    # EIN web_search-Call (Form B1), kein Zwei-Stufen-Query-Gen/Distill mehr.
    assert len(agent.step_calls) == 1
    assert vorschlag["meta"]["these"] == "Die zentrale These."


def test_kind_bleibt_single_shot_ohne_recherche_schema():
    """AC2/AC3a: Kind-Pfad nutzt das UNVERÄNDERTE Kind-Schema, kein meta."""
    llm = FakeLLM()
    agent = FakeAgent()
    vorschlag = llm_service.erzeuge_folgen_vorschlag(
        idee="Stigi findet eine Feder", bible="", historie="",
        naechste_nummer=1, llm=llm, name="Mia", alter=4,
        zielgruppe="kind", agent=agent)
    assert llm.last_structured_schema == llm_service.FOLGEN_INPUT_SCHEMA
    assert "meta" not in llm.last_structured_schema["properties"]
    assert "meta" not in vorschlag
    assert "# Recherche" not in llm.last_structured_user


def test_n_suchen_hart_gedeckelt_ueber_max_uses():
    """AC2: N-Suchen hart gedeckelt in [3,5] via web_search `max_uses`, an tiefe."""
    agent_tief = FakeAgent()
    research_service.recherchiere(thema="thema", agent=agent_tief, tiefe="tief")
    assert _step_tool_max_uses(agent_tief) == research_service.MAX_SUCHEN == 5

    agent_flach = FakeAgent()
    research_service.recherchiere(thema="thema", agent=agent_flach, tiefe="flach")
    assert _step_tool_max_uses(agent_flach) == research_service.MIN_SUCHEN == 3

    # Unbekannte tiefe → Default, immer in [MIN,MAX].
    assert research_service.MIN_SUCHEN <= research_service._n_fuer_tiefe(
        "unbekannt") <= research_service.MAX_SUCHEN


# ============================================================
#  HSP-58 — Datenabfluss-Invariante (HART, SICHERHEITSKRITISCH)
# ============================================================

def test_recherche_laeuft_NIE_bei_kind():
    """AC3a (HART): Recherche läuft NIE bei zielgruppe:kind (Config-Invariante)."""
    llm = FakeLLM()
    agent = FakeAgent()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Eine harmlose Kinder-Idee", bible=_BIBLE_MIT_FAMILIE,
        historie=_HISTORIE_MIT_FAMILIE, naechste_nummer=1, llm=llm,
        name="Mia", alter=4, zielgruppe="kind", agent=agent)
    assert agent.step_calls == [], "HSP-58-BRUCH: web_search lief bei Kind-Instanz"


def test_websearch_payload_enthaelt_KEINE_familiendaten():
    """AC3c (HART): die an web_search gesendete Nachricht enthält NUR das thema —
    NIE Bible/Historie/Personen-Daten (§3/RAT-26)."""
    llm = FakeLLM()
    agent = FakeAgent()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Quantencomputing und seine gesellschaftlichen Risiken",
        bible=_BIBLE_MIT_FAMILIE, historie=_HISTORIE_MIT_FAMILIE,
        naechste_nummer=1, llm=llm, name="Emil", alter=39,
        zielgruppe="erwachsen", agent=agent)

    assert agent.step_calls, "Recherche muss gelaufen sein"
    payload = _step_user(agent)
    # Der web_search-Call bekam AUSSCHLIESSLICH das thema — kein bible/historie.
    assert payload == "Quantencomputing und seine gesellschaftlichen Risiken"
    for token in _FAMILIEN_TOKEN:
        assert token.lower() not in payload.lower(), (
            "HSP-58-BRUCH: Familien-Token %r floss in die web_search-Anfrage: %r"
            % (token, payload))


def test_degradation_bei_fehlender_agent_sicht():
    """AC3b (HART): keine Agent-Sicht → Folge OHNE Recherche + Marker, kein Abbruch."""
    ergebnis = research_service.recherchiere(thema="thema", agent=None)
    assert ergebnis.degraded is True
    assert ergebnis.block == ""
    assert ergebnis.suchen_count == 0


def test_degradation_bei_vendor_ohne_web_search():
    """AC3b/AC4 (HART): Slot-Vendor ohne `web_search`-Capability (z. B. Mistral)
    → Degradation, KEIN Silent-Send eines unbekannten Server-Tools."""
    agent = FakeAgent(caps=frozenset({"tool_use", "system_message_distinct"}))
    ergebnis = research_service.recherchiere(thema="thema", agent=agent)
    assert ergebnis.degraded is True
    assert ergebnis.block == ""
    assert agent.step_calls == [], "web_search darf ohne Capability NICHT laufen"


def test_degradation_bei_websearch_fehler():
    """AC3b (HART): web_search-/Provider-Fehler → Degradation, kein harter Abbruch."""
    agent = FakeAgent(raises=RuntimeError("HTTP 429 (Quota)"))
    ergebnis = research_service.recherchiere(thema="thema", agent=agent)
    assert ergebnis.degraded is True
    assert ergebnis.block == ""

    # Und der GESAMTE Folgen-Pfad reißt nicht ab — die Folge kommt trotzdem.
    vorschlag = llm_service.erzeuge_folgen_vorschlag(
        idee="thema", bible="", historie="", naechste_nummer=1,
        llm=FakeLLM(), zielgruppe="erwachsen",
        agent=FakeAgent(raises=RuntimeError("Netz weg")))
    assert vorschlag["titel"]


def test_degradation_bei_leeren_treffern():
    """AC3b: web_search ohne Treffer → Degradation (keine belegte Recherche)."""
    agent = FakeAgent(sources=[], requests=2)
    ergebnis = research_service.recherchiere(thema="thema", agent=agent)
    assert ergebnis.degraded is True
    assert ergebnis.block == ""
    # Der Zähler hält die (leer gebliebenen) Suchen trotzdem fest.
    assert ergebnis.suchen_count == 2


def test_degradation_folge_kommt_trotzdem_ohne_block():
    """AC3b: bei Degradation trägt der Single-Shot KEINEN Recherche-Block."""
    llm = FakeLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="thema", bible="", historie="", naechste_nummer=1, llm=llm,
        zielgruppe="erwachsen", agent=FakeAgent(raises=RuntimeError("weg")))
    assert "# Recherche (Fakten & Quellen)" not in llm.last_structured_user


# ============================================================
#  HSP-59/HSP-60 — Anti-Slop + META-Block
# ============================================================

def test_meta_block_wird_gefuellt_und_formatiert():
    """AC4: META-Block (these/schnitt/quellen/begriffe_neu) für die Historie."""
    llm = FakeLLM()
    vorschlag = llm_service.erzeuge_folgen_vorschlag(
        idee="thema", bible="", historie="", naechste_nummer=1, llm=llm,
        zielgruppe="erwachsen", agent=FakeAgent())
    meta = vorschlag["meta"]
    assert meta["these"]
    assert meta["schnitt"]
    assert meta["quellen"] == ["https://example.org/a"]
    assert meta["begriffe_neu"] == ["Qubit"]

    formatiert = llm_service.format_meta_historie(meta)
    assert "These:" in formatiert
    assert "Qubit" in formatiert
    assert "https://example.org/a" in formatiert


def test_meta_fehlt_reisst_folge_nicht_ab():
    """AC4: fehlender META-Block → leerer, wohlgeformter META, kein Fehler."""
    assert llm_service._extrahiere_meta({}) == {
        "these": "", "schnitt": "", "quellen": [], "begriffe_neu": []}
    assert llm_service.format_meta_historie(
        {"these": "", "schnitt": "", "quellen": [], "begriffe_neu": []}) == ""


def test_suchen_pro_folge_zaehler():
    """AC4/HSP-60: Log-Zähler suchen_pro_folge = web_search_requests."""
    agent = FakeAgent(
        sources=[
            {"url": "https://a/1", "title": "1", "page_age": None},
            {"url": "https://a/2", "title": "2", "page_age": None},
            {"url": "https://a/3", "title": "3", "page_age": None},
        ],
        requests=3)
    ergebnis = research_service.recherchiere(
        thema="thema", agent=agent, tiefe="tief")
    assert ergebnis.suchen_count == 3
    assert ergebnis.quellen == ["https://a/1", "https://a/2", "https://a/3"]
