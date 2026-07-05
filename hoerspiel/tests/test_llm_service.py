"""HSP-45 / #1263 — Name-Drift-Fix im Story-Prompt (llm_service).

Belegt: `erzeuge_folgen_vorschlag` reicht die Instanz-Rahmung (name/alter/ton/
perspektive/serien_name) in den User-Kontext; eine emil-Folge nennt nie
Mia/Finn, eine mia-Folge trägt Mia + den Serien-Namen (transitionaler
Fallback, geschichtenbuddy.md ist entkernt).

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


def test_mia_folge_traegt_namen_und_serien_fallback():
    """AC2: mia-Folge trägt „Mia" + Serien-Name (Fallback, serien_name leer)."""
    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Stigi findet eine Feder", bible="", historie="",
        naechste_nummer=5, llm=llm,
        name="Mia", alter=4, serien_name="")  # serien_name leer → Fallback
    user = llm.last_user
    assert "Mia" in user
    assert llm_service.DEFAULT_SERIEN_RAHMEN in user, \
        "Serien-Rahmung (Fallback) muss im Story-Prompt stehen"


def test_emil_folge_nennt_nie_mia_oder_finn():
    """AC2: emil-Folge trägt Niclas + eigene Serie, nennt NIE Mia/Finn."""
    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Eine Folge über Systemdesign", bible="", historie="",
        naechste_nummer=1, llm=llm,
        name="Niclas", alter=39, ton="trocken, pointiert",
        perspektive="Ich-Erzähler", serien_name="Nachtschicht-Notizen")
    user = llm.last_user
    assert "Niclas" in user
    assert "Nachtschicht-Notizen" in user
    assert "Mia" not in user, "Name-Drift: Mia darf im emil-Prompt nicht auftauchen"
    assert "Finn" not in user, "Name-Drift: Finn darf im emil-Prompt nicht auftauchen"
    # Transitionaler Mia/Stigi-Fallback darf bei gesetzter Serie NICHT greifen.
    assert llm_service.DEFAULT_SERIEN_RAHMEN not in user


def test_alt_aufruf_ohne_instanz_bleibt_gerahmt():
    """Regression: Alt-Aufrufer (ohne name/serien_name) → transitionale Rahmung,
    keine leere/ungerahmte Story (mia/finn byte-gleich zur alten Rahmung)."""
    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="x", bible="", historie="", naechste_nummer=1, llm=llm)
    user = llm.last_user
    assert llm_service.DEFAULT_SERIEN_RAHMEN in user
    assert llm_service.DEFAULT_TON in user
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
