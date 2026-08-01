"""HSP-45 / #1263 / T1336 — Serien-Rahmen instanz-neutral (llm_service).

Belegt:
- `erzeuge_folgen_vorschlag` reicht die Instanz-Rahmung (name/alter/ton/
  perspektive/serien_name) in den User-Kontext.
- T1336: DEFAULT_SERIEN_RAHMEN = "" (leer); leeres serien_name → keine
  „Serie:"-Zeile im Prompt (kein Mia-Leak für finn oder andere Instanzen).
- Gesetzter serien_name trägt die korrekte Serie.

Keine Netz-Aufrufe — die LLM-Naht ist eine Recording-Doppelung.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from hoerspiel import llm_service  # noqa: E402
from hoerspiel.providers.base import LLMProvider  # noqa: E402


class _RecordingLLM(LLMProvider):
    """Merkt sich den letzten complete_structured-User-Kontext (HSP-32-Naht)."""

    name = "fake"
    model = "fake-model"

    def __init__(self):
        self.last_system = None
        self.last_user = None

    def complete(self, system, user):  # pragma: no cover - hier ungenutzt
        return "unused"

    def complete_structured(self, system, user, *, tool_name,
                            tool_description, input_schema):
        self.last_system = system
        self.last_user = user
        return {
            "titel": "T",
            "folgen-nr-vorschlag": 5,
            "text": "Folge 5: T.\n\nEin Absatz.",
        }


def test_mia_folge_traegt_namen_kein_stigi_bei_leerem_serien_name():
    """T1336/AC1+AC2b: mia-Folge mit serien_name='' → kein Mia-Leak (kein Stigi/Malini).

    „Serie:"-Zeile entfällt, wenn die Instanz keinen serien_name trägt — kein
    DEFAULT_SERIEN_RAHMEN-Fallback auf Mias serie für andere Instanzen.
    """
    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Stigi findet eine Feder", bible="", historie="",
        naechste_nummer=5, llm=llm,
        name="Mia", alter=4, serien_name="")  # serien_name leer → kein Fallback mehr
    user = llm.last_user
    assert "Mia" in user, "Name der Instanz muss im Prompt stehen"
    # T1336: kein Mia-Serien-Leak mehr
    assert "Stigi, Malini" not in user, \
        "T1336: DEFAULT war Mia-Serie — darf bei leerem serien_name nicht erscheinen"
    assert "Serie:" not in user, \
        "T1336: 'Serie:'-Zeile entfällt bei leerem serien_name"


def test_emil_folge_nennt_nie_mia_oder_finn():
    """AC2: emil-Folge trägt Emil + eigene Serie, nennt NIE Mia/Finn."""
    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Eine Folge über Systemdesign", bible="", historie="",
        naechste_nummer=1, llm=llm,
        name="Emil", alter=39, ton="trocken, pointiert",
        perspektive="Ich-Erzähler", serien_name="Nachtschicht-Notizen")
    user = llm.last_user
    assert "Emil" in user
    assert "Nachtschicht-Notizen" in user
    assert "Mia" not in user, "Name-Drift: Mia darf im emil-Prompt nicht auftauchen"
    assert "Finn" not in user, "Name-Drift: Finn darf im emil-Prompt nicht auftauchen"
    # T1336: Mia-Serie-String darf bei gesetzter eigener Serie NICHT erscheinen.
    assert "Stigi, Malini" not in user, \
        "T1336: Mias Serien-Name darf im emil-Prompt nicht auftauchen"


def test_alt_aufruf_ohne_instanz_kein_mia_leak():
    """T1336/AC1: Alt-Aufrufer (ohne name/serien_name) → kein Mia-Serien-Leak.

    Ton/Perspektive greifen via DEFAULT_TON/DEFAULT_PERSPEKTIVE; die „Serie:"-Zeile
    entfällt (kein Mia-Default mehr). Idee-Rückfall ist instanz-neutral.
    """
    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="x", bible="", historie="", naechste_nummer=1, llm=llm)
    user = llm.last_user
    # T1336: kein Mia-Serien-Leak
    assert "Stigi, Malini" not in user, \
        "T1336: Mias Serien-Name darf bei leerem serien_name nicht erscheinen"
    assert "Serie:" not in user, \
        "T1336: 'Serie:'-Zeile entfällt bei leerem serien_name"
    # Ton + Perspektive-Defaults greifen weiterhin
    assert llm_service.DEFAULT_TON in user
    assert llm_service.DEFAULT_PERSPEKTIVE in user
    # Idee-Rückfall ist instanz-neutral (kein „überrasche Mia" mehr).
    assert "überrasche Mia" not in user


def test_ton_und_perspektive_landen_im_kontext():
    """HSP-45: gesetzte ton/perspektive erscheinen wörtlich im Instanz-Kontext."""
    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="x", bible="", historie="", naechste_nummer=1, llm=llm,
        name="Finn", ton="verspielt, bunt", perspektive="Wir-Perspektive",
        serien_name="Quasiluxi, Alpaki & Haski")
    user = llm.last_user
    assert "verspielt, bunt" in user
    assert "Wir-Perspektive" in user
    assert "Quasiluxi, Alpaki & Haski" in user


# ---------------------------------------------------------------------------
# T1336 — Regressions-Tests: instanz-neutrale Serien-Rahmung (AC2a/2b/AC3)
# ---------------------------------------------------------------------------

def test_ac2a_finn_serien_name_quasiluxi_erscheint_im_prompt():
    """T1336/AC2a: finn-Instanz mit serien_name='Quasiluxi, Alpaki & Haski — …'
    → _build_user_context trägt genau diese Serie."""
    llm = _RecordingLLM()
    finn_serie = "Quasiluxi, Alpaki & Haski — Die Kuscheltier-Abenteuer im Gelben Haus"
    llm_service.erzeuge_folgen_vorschlag(
        idee="Alpaki verliert seinen Hut", bible="", historie="",
        naechste_nummer=3, llm=llm,
        name="Finn", alter=5, serien_name=finn_serie)
    user = llm.last_user
    assert finn_serie in user, \
        "AC2a: finn-Serien-Name muss exakt im Story-Prompt stehen"
    assert "Stigi, Malini" not in user, \
        "AC2a: Mias Serien-Name darf im finn-Prompt NICHT erscheinen"


def test_ac2b_leerer_serien_name_nie_stigi_malini():
    """T1336/AC2b: leerer serien_name → NIE 'Stigi, Malini' im Prompt."""
    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="irgendwas", bible="", historie="",
        naechste_nummer=1, llm=llm,
        serien_name="")  # explizit leer
    user = llm.last_user
    assert "Stigi, Malini" not in user, \
        "AC2b: Mias Serie darf bei leerem serien_name NIE im Prompt erscheinen"
    assert "Serie:" not in user, \
        "AC2b: 'Serie:'-Zeile entfällt bei leerem serien_name (T1336)"
