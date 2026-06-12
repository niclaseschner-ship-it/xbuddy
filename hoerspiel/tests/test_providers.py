"""HSP-10/HSP-11 — LLM-Service + Provider-Pattern (kopierfähig)."""

import json

import pytest

from hoerspiel import llm_service
from hoerspiel.providers.base import LLMProvider


class _RecordingLLM(LLMProvider):
    name = "fake"
    model = "fake-model"

    def __init__(self, payload):
        self.payload = payload
        self.last_call = None

    def complete(self, system, user):
        self.last_call = (system, user)
        return self.payload


def test_folgen_vorschlag_extrahiert_json():
    payload = json.dumps({
        "titel": "Stigi und die Sonne",
        "folgen-nr-vorschlag": 23,
        "text": "Folge 23: Stigi und die Sonne.\n\nStigi sah die Sonne.",
    })
    llm = _RecordingLLM(payload)
    out = llm_service.erzeuge_folgen_vorschlag(
        idee="sonne", bible="bible", historie="historie", naechste_nummer=23,
        llm=llm)
    assert out["titel"] == "Stigi und die Sonne"
    assert out["folgen-nr-vorschlag"] == 23
    assert out["text"].startswith("Folge 23:")
    assert "GeschichtenBuddy" in llm.last_call[0]
    assert "sonne" in llm.last_call[1]
    assert "bible" in llm.last_call[1]


def test_folgen_vorschlag_extrahiert_aus_code_fence():
    payload = "```json\n" + json.dumps({
        "titel": "T", "folgen-nr-vorschlag": 1,
        "text": "Folge 1: T.\n\nA.",
    }) + "\n```"
    llm = _RecordingLLM(payload)
    out = llm_service.erzeuge_folgen_vorschlag(
        idee="x", bible="", historie="", naechste_nummer=1, llm=llm)
    assert out["titel"] == "T"


def test_folgen_vorschlag_fehlt_pflichtfeld():
    payload = json.dumps({"titel": "T"})  # text und nr fehlen
    llm = _RecordingLLM(payload)
    with pytest.raises(llm_service.LLMServiceError):
        llm_service.erzeuge_folgen_vorschlag(
            idee="x", bible="", historie="", naechste_nummer=1, llm=llm)


def test_folgen_vorschlag_kein_json():
    llm = _RecordingLLM("nur fließtext, kein JSON")
    with pytest.raises(llm_service.LLMServiceError):
        llm_service.erzeuge_folgen_vorschlag(
            idee="x", bible="", historie="", naechste_nummer=1, llm=llm)


def test_synopse_strippt_und_returnt():
    llm = _RecordingLLM("  Eine kurze Synopse.  ")
    out = llm_service.erzeuge_synopse(titel="T", text="A", llm=llm)
    assert out == "Eine kurze Synopse."


def test_provider_base_complete_nicht_implementiert():
    """Basis-Klasse trägt nur die Schnittstelle (HSP-10)."""
    with pytest.raises(NotImplementedError):
        LLMProvider().complete("s", "u")
