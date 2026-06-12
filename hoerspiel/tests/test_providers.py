"""HSP-10/HSP-11 — LLM-Service + Provider-Pattern (kopierfähig)."""

import pytest

from hoerspiel import llm_service
from hoerspiel.providers.base import LLMProvider


class _RecordingLLM(LLMProvider):
    name = "fake"
    model = "fake-model"

    def __init__(self, *, structured_payload=None, text_payload=None):
        self.structured_payload = structured_payload
        self.text_payload = text_payload
        self.last_text_call = None
        self.last_structured_call = None

    def complete(self, system, user):
        self.last_text_call = (system, user)
        return self.text_payload or ""

    def complete_structured(self, system, user, *, tool_name,
                            tool_description, input_schema):
        self.last_structured_call = (system, user, tool_name, input_schema)
        if self.structured_payload is None:
            raise llm_service.LLMServiceError("kein structured_payload gesetzt")
        return dict(self.structured_payload)


def test_folgen_vorschlag_aus_structured_call():
    payload = {
        "titel": "Stigi und die Sonne",
        "folgen-nr-vorschlag": 23,
        "text": "Folge 23: Stigi und die Sonne.\n\nStigi sah die Sonne.",
    }
    llm = _RecordingLLM(structured_payload=payload)
    out = llm_service.erzeuge_folgen_vorschlag(
        idee="sonne", bible="bible", historie="historie", naechste_nummer=23,
        llm=llm)
    assert out["titel"] == "Stigi und die Sonne"
    assert out["folgen-nr-vorschlag"] == 23
    assert out["text"].startswith("Folge 23:")
    system, user, tool_name, schema = llm.last_structured_call
    assert "GeschichtenBuddy" in system
    assert "sonne" in user
    assert "bible" in user
    assert tool_name == llm_service.FOLGEN_TOOL_NAME
    assert "text" in schema["required"]


def test_folgen_vorschlag_text_mit_quotes_unbeschwert():
    """Wörtliche Rede mit Quotes bricht das Tool-Use-Schema nicht."""
    payload = {
        "titel": "Schnecken",
        "folgen-nr-vorschlag": 23,
        "text": 'Folge 23: Schnecken.\n\nStigi sagte: „Hallo." Malini rief: „Komm rein!"',
    }
    llm = _RecordingLLM(structured_payload=payload)
    out = llm_service.erzeuge_folgen_vorschlag(
        idee="schnecken", bible="", historie="", naechste_nummer=23, llm=llm)
    assert "„Hallo." in out["text"]


def test_folgen_vorschlag_fehlt_pflichtfeld():
    payload = {"titel": "T"}  # text und nr fehlen
    llm = _RecordingLLM(structured_payload=payload)
    with pytest.raises(llm_service.LLMServiceError):
        llm_service.erzeuge_folgen_vorschlag(
            idee="x", bible="", historie="", naechste_nummer=1, llm=llm)


def test_synopse_strippt_und_returnt():
    llm = _RecordingLLM(text_payload="  Eine kurze Synopse.  ")
    out = llm_service.erzeuge_synopse(titel="T", text="A", llm=llm)
    assert out == "Eine kurze Synopse."


def test_provider_base_complete_nicht_implementiert():
    """Basis-Klasse trägt nur die Schnittstelle (HSP-10)."""
    with pytest.raises(NotImplementedError):
        LLMProvider().complete("s", "u")


def test_provider_base_complete_structured_nicht_implementiert():
    with pytest.raises(NotImplementedError):
        LLMProvider().complete_structured("s", "u", tool_name="x",
                                          tool_description="y", input_schema={})
