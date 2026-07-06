"""T1336/AC3 — Partial instance.json + Fallback-Kette (config.load_instance).

Belegt: eine instance.json mit nur kind_id + serien_name + ton + perspektive
(OHNE name/alter/themen_je_alter) zerstört weder name noch alter noch themen —
die config.load_instance-Fallback-Kette greift.

Keine Netz-Aufrufe, keine Live-Daten — Tests legen temp-Verzeichnisse an.
"""

import json
import os
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from hoerspiel import config as config_mod  # noqa: E402


def _write_instance(tmpdir: str, data: dict) -> None:
    path = os.path.join(tmpdir, "instance.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_ac3_partial_instance_json_name_alter_themen_fallback():
    """T1336/AC3: partial instance.json (kind_id+serien_name+ton+perspektive ONLY)
    → name/alter/themen_je_alter fallen auf sichere Defaults zurück, kein Crash.
    """
    finn_serie = "Quasiluxi, Alpaki & Haski — Die Kuscheltier-Abenteuer im Gelben Haus"
    partial = {
        "kind_id": "finn",
        "serien_name": finn_serie,
        "ton": "verspielt, bunt",
        "perspektive": "Wir-Perspektive",
        # name, alter, themen_je_alter absichtlich NICHT gesetzt
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        _write_instance(tmpdir, partial)
        inst = config_mod.load_instance(tmpdir, kind_id="finn")

    # serien_name, ton, perspektive aus Datei
    assert inst.serien_name == finn_serie, \
        "AC3: serien_name muss aus partial instance.json übernommen werden"
    assert inst.ton == "verspielt, bunt", \
        "AC3: ton muss aus partial instance.json übernommen werden"
    assert inst.perspektive == "Wir-Perspektive", \
        "AC3: perspektive muss aus partial instance.json übernommen werden"

    # name/alter: sichere Fallback-Werte (kein Crash, kein fremder Name)
    assert isinstance(inst.name, str), "AC3: name muss str sein"
    assert "Mia" not in inst.name, \
        "AC3: kein Mia-Leak im name-Fallback"
    assert isinstance(inst.alter, int), "AC3: alter muss int sein"
    # alter=0 ist der designierte Leer-Wert (HSP-27: Alter 0 → 422 bei Themen-Endpoint)

    # themen_je_alter: DEFAULT greift, nie None/leer
    assert isinstance(inst.themen_je_alter, dict), \
        "AC3: themen_je_alter Fallback muss dict sein"
    assert len(inst.themen_je_alter) > 0, \
        "AC3: themen_je_alter Fallback darf nicht leer sein"


def test_ac3_serien_name_aus_partial_instance_json_landet_im_prompt():
    """T1336/AC3 + AC2a: serien_name aus partial instance.json landet via
    erzeuge_folgen_vorschlag im LLM-Prompt — End-to-End ohne Netz.
    """
    from hoerspiel import llm_service
    from hoerspiel.providers.base import LLMProvider

    class _RecordingLLM(LLMProvider):
        name = "fake"
        model = "fake-model"

        def __init__(self):
            self.last_user = None

        def complete(self, system, user):  # pragma: no cover
            return "unused"

        def complete_structured(self, system, user, *, tool_name,
                                tool_description, input_schema):
            self.last_user = user
            return {
                "titel": "T",
                "folgen-nr-vorschlag": 1,
                "text": "Folge 1: T.\n\nEin Absatz.",
            }

    finn_serie = "Quasiluxi, Alpaki & Haski — Die Kuscheltier-Abenteuer im Gelben Haus"
    partial = {
        "kind_id": "finn",
        "serien_name": finn_serie,
        "ton": "verspielt, bunt",
        "perspektive": "Wir-Perspektive",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        _write_instance(tmpdir, partial)
        inst = config_mod.load_instance(tmpdir, kind_id="finn")

    llm = _RecordingLLM()
    llm_service.erzeuge_folgen_vorschlag(
        idee="Alpaki verliert seinen Hut",
        bible="", historie="",
        naechste_nummer=1,
        llm=llm,
        name=inst.name,
        alter=inst.alter,
        ton=inst.ton,
        perspektive=inst.perspektive,
        serien_name=inst.serien_name,
    )
    user = llm.last_user
    assert finn_serie in user, \
        "AC3+AC2a: serien_name aus partial instance.json muss im LLM-Prompt landen"
    assert "Stigi, Malini" not in user, \
        "AC3+AC2a: Mias Serie darf im finn-Prompt NICHT erscheinen"
