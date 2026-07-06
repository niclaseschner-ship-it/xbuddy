"""HSP-56..60 — Recherchierte Erwachsenen-Generierung (T1340).

Belegt den zielgruppe-bewussten Prompt-Schnitt (HSP-56), den Recherche-
Vorschritt (HSP-57), die HARTE Datenabfluss-Invariante (HSP-58), den Anti-Slop-
Self-Check + META-Block (HSP-59/HSP-60).

SICHERHEITS-GATE (HSP-58): kein Live-Tavily-Call — der Such-Client ist immer
gedoppelt. Die Payload-Inspektion (AC3c) prüft, dass NUR thema-abgeleitete
Begriffe an Tavily gehen, NIE Bible/Historie/Personen-Daten.
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from hoerspiel import llm_service, research_service  # noqa: E402
from hoerspiel.providers.base import LLMProvider  # noqa: E402
from hoerspiel.tavily_client import (  # noqa: E402
    TavilyClient,
    TavilyError,
    resolve_tavily_key,
)

# ============================================================
#  Doppelungen (kein Netz, kein Live-LLM)
# ============================================================

class FakeLLM(LLMProvider):
    """Deckt beide Nähte: `complete` (Query-Gen + Distill, HSP-57) und
    `complete_structured` (Folgen-Vorschlag, HSP-11). Merkt sich alle Calls.
    """

    name = "fake"
    model = "fake-model"

    def __init__(self, queries="quantencomputing risiken\nquantencomputing studien",
                 fakten="- Fakt A (belegt)\n\nQuellen:\n- https://example.org/a"):
        self._queries = queries
        self._fakten = fakten
        self.complete_calls = []          # (system, user)
        self.last_structured_user = None
        self.last_structured_schema = None

    def complete(self, system, user):
        self.complete_calls.append((system, user))
        if "Suchanfragen" in system or "Recherche-Assistent" in system:
            return self._queries
        return self._fakten

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


class SpyTavily:
    """Merkt sich JEDE gesuchte query (AC3c-Payload-Inspektion)."""

    def __init__(self, results=None, fehler=None):
        self.queries = []
        self._results = results if results is not None else [
            {"title": "T", "url": "https://example.org/a", "content": "Inhalt"}]
        self._fehler = fehler

    def suche(self, query):
        self.queries.append(query)
        if self._fehler is not None:
            raise self._fehler
        return list(self._results)


class FakeStore:
    """Doppelung der Zugangsdaten-Naht (`get(name)`)."""

    def __init__(self, werte):
        self._werte = dict(werte)

    def get(self, name, default=None):
        return self._werte.get(name, default)


# Bible/Historie mit Familien-Daten — dürfen NIE in die Suchanfrage geraten.
_BIBLE_MIT_FAMILIE = ("Paula (4 Jahre) wohnt im Dreisamtal. Geheimwort: "
                      "Vögelchen. Neko ist die Katze der Familie Eschner.")
_HISTORIE_MIT_FAMILIE = "## Folge 1: Paula und Neko im Garten"
_FAMILIEN_TOKEN = ["Paula", "Neko", "Eschner", "Dreisamtal", "Vögelchen",
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
#  HSP-57 — Recherche-Vorschritt verdrahtet
# ============================================================

def test_erwachsen_speist_recherche_block_in_single_shot():
    """AC2: Query-Gen → Tavily → Distill → Fakten-Block landet im Single-Shot-User."""
    llm = FakeLLM()
    tavily = SpyTavily()
    vorschlag = llm_service.erzeuge_folgen_vorschlag(
        idee="Quantencomputing und seine Risiken",
        bible="", historie="", naechste_nummer=1, llm=llm,
        zielgruppe="erwachsen", tavily=tavily)
    # Der Recherche-Block ist im User-Kontext des Single-Shots.
    assert "# Recherche (Fakten & Quellen)" in llm.last_structured_user
    assert "Fakt A (belegt)" in llm.last_structured_user
    # Single-Shot-Vertrag: complete_structured mit erwachsen-Schema.
    assert "meta" in llm.last_structured_schema["properties"]
    # Query-Gen + Distill = 2 Freitext-Calls; Tavily lief.
    assert len(llm.complete_calls) == 2
    assert tavily.queries
    assert vorschlag["meta"]["these"] == "Die zentrale These."


def test_kind_bleibt_single_shot_ohne_recherche_schema():
    """AC2/AC3a: Kind-Pfad nutzt das UNVERÄNDERTE Kind-Schema, kein meta."""
    llm = FakeLLM()
    tavily = SpyTavily()
    vorschlag = llm_service.erzeuge_folgen_vorschlag(
        idee="Stigi findet eine Feder", bible="", historie="",
        naechste_nummer=1, llm=llm, name="Paula", alter=4,
        zielgruppe="kind", tavily=tavily)
    assert llm.last_structured_schema == llm_service.FOLGEN_INPUT_SCHEMA
    assert "meta" not in llm.last_structured_schema["properties"]
    assert "meta" not in vorschlag
    assert "# Recherche" not in llm.last_structured_user


def test_n_suchen_hart_gedeckelt():
    """AC2: N-Suchen hart gedeckelt in [3,5], an tiefe gekoppelt."""
    # Query-Gen liefert 20 Zeilen — es dürfen NIE mehr als MAX_SUCHEN abgehen.
    viele = "\n".join("suche %d" % i for i in range(20))
    llm = FakeLLM(queries=viele)
    tavily = SpyTavily()
    research_service.recherchiere(
        thema="thema", llm=llm, tavily=tavily, tiefe="tief")
    assert len(tavily.queries) == research_service.MAX_SUCHEN == 5

    tavily2 = SpyTavily()
    research_service.recherchiere(
        thema="thema", llm=FakeLLM(queries=viele), tavily=tavily2, tiefe="flach")
    assert len(tavily2.queries) == research_service.MIN_SUCHEN == 3

    # Unbekannte tiefe → Default, immer in [MIN,MAX].
    assert research_service.MIN_SUCHEN <= research_service._n_fuer_tiefe(
        "unbekannt") <= research_service.MAX_SUCHEN


# ============================================================
#  HSP-58 — Datenabfluss-Invariante (HART, SICHERHEITSKRITISCH)
# ============================================================

def test_recherche_laeuft_NIE_bei_kind():
    """AC3a (HART): Recherche läuft NIE bei zielgruppe:kind (Config-Invariante)."""
    llm = FakeLLM()
    tavily = SpyTavily()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Eine harmlose Kinder-Idee", bible=_BIBLE_MIT_FAMILIE,
        historie=_HISTORIE_MIT_FAMILIE, naechste_nummer=1, llm=llm,
        name="Paula", alter=4, zielgruppe="kind", tavily=tavily)
    assert tavily.queries == [], "HSP-58-BRUCH: Tavily lief bei Kind-Instanz"
    # Auch kein Query-Gen/Distill-Call für Kind.
    assert llm.complete_calls == []


def test_tavily_payload_enthaelt_KEINE_familiendaten():
    """AC3c (HART): die an Tavily gesendete Suchanfrage enthält NUR thema-
    abgeleitete Begriffe — NIE Bible/Historie/Personen-Daten (§3/RAT-26)."""
    # Query-Gen würde (im Fake) genau das thema echoen; selbst wenn ein echtes
    # Modell driftet, kann es nur aus dem thema schöpfen — Bible/Historie werden
    # dem Recherche-Service STRUKTURELL nicht übergeben.
    llm = FakeLLM(queries="quantencomputing risiken\nquantencomputing studienlage")
    tavily = SpyTavily()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Quantencomputing und seine gesellschaftlichen Risiken",
        bible=_BIBLE_MIT_FAMILIE, historie=_HISTORIE_MIT_FAMILIE,
        naechste_nummer=1, llm=llm, name="Niclas", alter=39,
        zielgruppe="erwachsen", tavily=tavily)

    assert tavily.queries, "Recherche muss gelaufen sein"
    gesamt_payload = " ".join(tavily.queries)
    for token in _FAMILIEN_TOKEN:
        assert token.lower() not in gesamt_payload.lower(), (
            "HSP-58-BRUCH: Familien-Token %r floss in die Tavily-Suchanfrage: %r"
            % (token, tavily.queries))

    # Zusätzlich: der Query-Gen-Call bekam AUSSCHLIESSLICH das thema als User —
    # NIE bible/historie (strukturelle Absicherung der Invariante).
    query_gen_user = llm.complete_calls[0][1]
    for token in _FAMILIEN_TOKEN:
        assert token.lower() not in query_gen_user.lower(), (
            "HSP-58-BRUCH: Query-Gen bekam Familien-Daten im User-Input")


def test_degradation_bei_fehlendem_key():
    """AC3b (HART): fehlender Key → Folge OHNE Recherche + Marker, kein Abbruch."""
    # tavily=None simuliert „kein Default-Client" (Key-Slot leer).
    llm = FakeLLM()
    # _default_tavily_client greift NUR wenn tavily nicht injiziert wird; wir
    # testen die research-Ebene direkt mit tavily=None.
    ergebnis = research_service.recherchiere(
        thema="thema", llm=llm, tavily=None)
    assert ergebnis.degraded is True
    assert ergebnis.block == ""
    assert ergebnis.suchen_count == 0


def test_degradation_bei_netz_oder_quota_fehler():
    """AC3b (HART): Netz-/Quota-Fehler → Degradation, kein harter Abbruch."""
    llm = FakeLLM()
    tavily = SpyTavily(fehler=TavilyError("HTTP 429 (Quota)"))
    ergebnis = research_service.recherchiere(
        thema="thema", llm=llm, tavily=tavily)
    assert ergebnis.degraded is True
    assert ergebnis.block == ""

    # Und der GESAMTE Folgen-Pfad reißt nicht ab — die Folge kommt trotzdem.
    vorschlag = llm_service.erzeuge_folgen_vorschlag(
        idee="thema", bible="", historie="", naechste_nummer=1,
        llm=FakeLLM(), zielgruppe="erwachsen",
        tavily=SpyTavily(fehler=TavilyError("Netz weg")))
    assert vorschlag["titel"]


def test_degradation_folge_kommt_trotzdem_ohne_block():
    """AC3b: bei Degradation trägt der Single-Shot KEINEN Recherche-Block."""
    llm = FakeLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="thema", bible="", historie="", naechste_nummer=1, llm=llm,
        zielgruppe="erwachsen", tavily=SpyTavily(fehler=TavilyError("weg")))
    assert "# Recherche (Fakten & Quellen)" not in llm.last_structured_user


# ============================================================
#  Tavily-Client — Key-Read + Payload + Degradation
# ============================================================

def test_resolve_tavily_key_liest_slot():
    """AC2: der Key kommt über die Zugangsdaten-Naht aus dem tavily-api-key-Slot."""
    store = FakeStore({"tavily-api-key": "geheim-123"})
    assert resolve_tavily_key(store) == "geheim-123"
    assert resolve_tavily_key(FakeStore({})) is None


def test_tavily_client_payload_nur_query_und_key():
    """AC3c: der HTTP-Payload trägt query + technische Parameter, sonst nichts."""
    erfasst = {}

    def transport(url, payload_bytes):
        erfasst["url"] = url
        erfasst["payload"] = json.loads(payload_bytes.decode("utf-8"))
        return json.dumps({"results": [
            {"title": "T", "url": "https://x/y", "content": "c"}]}).encode()

    client = TavilyClient(api_key="k", transport=transport)
    treffer = client.suche("nur diese suchanfrage")
    assert erfasst["payload"]["query"] == "nur diese suchanfrage"
    assert erfasst["payload"]["api_key"] == "k"
    # Nur erwartete Schlüssel — kein Bible/Historie/Context-Feld.
    assert set(erfasst["payload"].keys()) <= {
        "api_key", "query", "max_results", "search_depth"}
    assert treffer[0]["url"] == "https://x/y"


def test_tavily_client_ohne_key_wirft():
    """AC3b: fehlender Key → TavilyError (Aufrufer degradiert)."""
    client = TavilyClient(api_key=None)
    with pytest.raises(TavilyError):
        client.suche("x")


def test_tavily_client_http_fehler_wirft_tavilyerror():
    """AC3b: HTTP-/Netz-Fehler → TavilyError (kein roher urllib-Fehler nach oben)."""
    import urllib.error

    def transport(url, payload_bytes):
        raise urllib.error.URLError("connection refused")

    client = TavilyClient(api_key="k", transport=transport)
    with pytest.raises(TavilyError):
        client.suche("x")


# ============================================================
#  HSP-59/HSP-60 — Anti-Slop + META-Block
# ============================================================

def test_meta_block_wird_gefuellt_und_formatiert():
    """AC4: META-Block (these/schnitt/quellen/begriffe_neu) für die Historie."""
    llm = FakeLLM()
    vorschlag = llm_service.erzeuge_folgen_vorschlag(
        idee="thema", bible="", historie="", naechste_nummer=1, llm=llm,
        zielgruppe="erwachsen", tavily=SpyTavily())
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
    """AC4/HSP-60: Log-Zähler suchen_pro_folge = Anzahl gelaufener Suchen."""
    llm = FakeLLM(queries="a\nb\nc\nd\ne")
    tavily = SpyTavily()
    ergebnis = research_service.recherchiere(
        thema="thema", llm=llm, tavily=tavily, tiefe="tief")
    assert ergebnis.suchen_count == len(tavily.queries) == 5
