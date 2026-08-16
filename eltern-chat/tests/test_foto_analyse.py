"""FotoAnalyseProvider — TAB-Foto-Pfad über `tools.llm` (#1262, T1262, #1509).

Deckt den neuen Foto-Adapter ab (specs/platform/termine-aus-bild.md TAB-5,
E-TAB-8), der den `MultimodalProvider`-Duck-Type erfüllt, den Anbieter-Call aber
an die Singleshot-Sicht von `tools.llm` durchreicht:

- forced `extract_termine`-Tool + hart-codiertes Schema + `images`-Durchreichung
  an die Lib-Fassade; `.get("termine")`-Auspacken → list[ExtractedTermin];
- Fehlerpfade → `MultimodalError` (TAB-5 provider_fehler); Bau-Fehler
  (`LLMCapabilityError`) propagiert als Boot-Fehler (NICHT als MultimodalError);
- Typen-Heimat: `ExtractedTermin`/`MultimodalError` sind physisch in
  `foto_analyse` definiert (#1334, PR2); Felder + Signatur korrekt;
- write_verification (AC3): ein Durchlauf durch den ECHTEN LiteLLM-Vendor
  (mockiertes litellm-SDK) schreibt eine `provider_calls.jsonl`-Zeile mit dem
  Foto-Slot (#1509-Migration: `eltern-chat-litellm-foto-analyse-api-key`).

Mock-Naht: für die Adapter-Logik wird `skills.foto_analyse.get_singleshot` durch
eine Fake-Fassade ersetzt; für den Telemetrie-/Wire-Beweis das litellm-SDK
via `patch.dict(sys.modules, …)` + gestubtes `resolve_api_key` (Spiegel
test_vendor_litellm.py).
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# ----------------------------------------------------------------------
#  Fake-Fassade (Adapter-Logik ohne Netz / ohne Store)
# ----------------------------------------------------------------------

class FakeFacade:
    """Ersetzt `get_singleshot(...)`; fängt die complete_structured-kwargs."""

    def __init__(self, result=None, error=None):
        self.model = "claude-opus-4-7"
        self._result = result if result is not None else {"termine": []}
        self._error = error
        self.calls = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


def _patch_facade(monkeypatch, facade):
    monkeypatch.setattr("skills.foto_analyse.get_singleshot",
                        lambda *a, **k: facade)


# ----------------------------------------------------------------------
#  Adapter-Logik: forced tool, schema, images, Auspacken
# ----------------------------------------------------------------------

def test_extract_termine_forced_tool_schema_images_und_unpack(monkeypatch):
    """AC2: forced tool_name='extract_termine', hart-codiertes Schema, images-
    Durchreichung; die Fassade liefert {termine:[…]} → `.get('termine')` wird zu
    list[ExtractedTermin] ausgepackt."""
    facade = FakeFacade(result={"termine": [
        {"titel": "Sportfest", "beginn": "2026-09-15", "ganztags": True,
         "personen_hinweise": "Klasse 3b"},
        {"titel": "Elternabend", "beginn": "2026-09-22T18:00:00+02:00",
         "ende": "2026-09-22T20:00:00+02:00", "ganztags": False},
    ]})
    _patch_facade(monkeypatch, facade)
    from skills.foto_analyse import (
        SYSTEM_PROMPT,
        TOOL_DESCRIPTION,
        TOOL_SCHEMA,
        ExtractedTermin,
        FotoAnalyseProvider,
    )

    prov = FotoAnalyseProvider()
    out = prov.extract_termine(
        image_bytes=b"img-bytes", image_media_type="image/png",
        caption="Bitte termine eintragen")

    # Durchreichung an die Lib-Fassade.
    assert len(facade.calls) == 1
    call = facade.calls[0]
    assert call["tool_name"] == "extract_termine"
    assert call["tool_description"] is TOOL_DESCRIPTION
    assert call["schema"] is TOOL_SCHEMA
    assert call["system"] is SYSTEM_PROMPT
    # Neutrale Wire-Form: Rohbytes + media_type (base64 macht der Vendor).
    assert call["images"] == [{"bytes": b"img-bytes", "media_type": "image/png"}]
    # Caption landet im Prompt-Text.
    assert "Bitte termine eintragen" in call["prompt"]

    # `.get('termine')`-Auspacken → kanonische ExtractedTermin-Objekte.
    assert len(out) == 2
    assert all(isinstance(t, ExtractedTermin) for t in out)
    assert out[0].titel == "Sportfest"
    assert out[0].beginn == "2026-09-15"
    assert out[0].personen_hinweise == "Klasse 3b"
    assert out[1].ende.endswith("+02:00")


def test_extract_termine_leere_liste_kein_fehler(monkeypatch):
    """Leere `termine`-Liste ist KEIN Fehler (TAB-6 wertet nachgelagert als
    'unklar') — der Adapter liefert []."""
    facade = FakeFacade(result={"termine": []})
    _patch_facade(monkeypatch, facade)
    from skills.foto_analyse import FotoAnalyseProvider

    out = FotoAnalyseProvider().extract_termine(
        image_bytes=b"x", image_media_type="image/jpeg", caption="termine")
    assert out == []


def test_extract_termine_ohne_termine_key_wirft(monkeypatch):
    """Fehlt die `termine`-Liste in der Tool-Antwort → MultimodalError."""
    facade = FakeFacade(result={"foo": "bar"})
    _patch_facade(monkeypatch, facade)
    from skills.foto_analyse import FotoAnalyseProvider, MultimodalError

    with pytest.raises(MultimodalError):
        FotoAnalyseProvider().extract_termine(
            image_bytes=b"x", image_media_type="image/jpeg", caption="termine")


def test_extract_termine_ohne_bild_wirft(monkeypatch):
    """Leeres `image_bytes` ist Vertrags-Verletzung → MultimodalError (kein
    Lib-Call)."""
    facade = FakeFacade()
    _patch_facade(monkeypatch, facade)
    from skills.foto_analyse import FotoAnalyseProvider, MultimodalError

    with pytest.raises(MultimodalError):
        FotoAnalyseProvider().extract_termine(
            image_bytes=b"", image_media_type="image/jpeg", caption="termine")
    assert facade.calls == []  # Vendor nicht gerufen.


def test_lib_provider_error_wird_multimodalerror(monkeypatch):
    """Laufzeit-`tools.llm.ProviderError` → MultimodalError (TAB-5 →
    provider_fehler); der Skill fängt nur diese eine Klasse."""
    from tools.llm import ProviderError as LibProviderError
    facade = FakeFacade(error=LibProviderError("anbieter weg"))
    _patch_facade(monkeypatch, facade)
    from skills.foto_analyse import FotoAnalyseProvider, MultimodalError

    with pytest.raises(MultimodalError):
        FotoAnalyseProvider().extract_termine(
            image_bytes=b"x", image_media_type="image/jpeg", caption="termine")


def test_build_llmcapabilityerror_propagiert_als_boot_fehler(monkeypatch):
    """Bau-Fehler (fehlender Foto-Slot-Key / Capability-Mismatch) propagiert als
    LLMCapabilityError — NICHT als MultimodalError verschluckt (Boot-vs-Laufzeit,
    Spiegel lib_adapter). tasks.build_catalog schaltet den Skill dann ab."""
    from tools.llm import LLMCapabilityError

    def _boom(*a, **k):
        raise LLMCapabilityError("kein API-Key im Foto-Slot")

    monkeypatch.setattr("skills.foto_analyse.get_singleshot", _boom)
    from skills.foto_analyse import FotoAnalyseProvider

    with pytest.raises(LLMCapabilityError):
        FotoAnalyseProvider()


# ----------------------------------------------------------------------
#  Konstanten / Typen-Identität
# ----------------------------------------------------------------------

def test_foto_slot_name_woertlich():
    """AC2 echo_check: der ZD-Slot-Name ist wörtlich fixiert (#1509/TAB-5/E-TAB-8).

    Vendor-Segment `litellm` (nicht mehr `anthropic`) — LiteLLM-Motor mit
    `multimodal_input`-Capability (LLMP-3/LLMP-S11, #1509).
    """
    from skills.foto_analyse import FOTO_ANALYSE_SLOT
    assert FOTO_ANALYSE_SLOT == "eltern-chat-litellm-foto-analyse-api-key"


def test_typen_physisch_in_foto_analyse_definiert():
    """AC2 (#1334): ExtractedTermin/MultimodalError sind physisch in
    foto_analyse definiert (kein Re-Export aus _multimodal). Prüft Felder
    und Signatur der kanonischen Heimat."""
    from dataclasses import fields as dc_fields

    from skills.foto_analyse import ExtractedTermin, MultimodalError
    # ExtractedTermin ist ein Dataclass.
    field_names = {f.name for f in dc_fields(ExtractedTermin)}
    assert "titel" in field_names
    assert "beginn" in field_names
    assert "ende" in field_names
    assert "ganztags" in field_names
    assert "personen_hinweise" in field_names
    assert "fehlende_felder" in field_names
    # MultimodalError ist eine Exception.
    assert issubclass(MultimodalError, Exception)
    # Modul-Heimat ist foto_analyse, nicht _multimodal.
    assert "foto_analyse" in ExtractedTermin.__module__
    assert "foto_analyse" in MultimodalError.__module__


def test_tool_schema_ist_hart_codiert():
    """TAB-5: Tool-Name/Schema hart-codiert (E-EC-4, stabile Schnittstelle)."""
    from skills.foto_analyse import TOOL_NAME, TOOL_SCHEMA
    assert TOOL_NAME == "extract_termine"
    assert TOOL_SCHEMA["type"] == "object"
    item_schema = TOOL_SCHEMA["properties"]["termine"]["items"]
    assert set(item_schema["required"]) == {"titel", "beginn"}


# ----------------------------------------------------------------------
#  AC3 write_verification — echter Vendor (mockiertes SDK) schreibt Telemetrie
# ----------------------------------------------------------------------


class _FakeAPIError(Exception):
    """Steht für `litellm.exceptions.APIError` im Test."""


def _make_litellm_singleshot_response(tool_name, tool_input):
    """OpenAI-förmige LiteLLM-ModelResponse für singleshot mit forced tool_use."""
    fn = MagicMock()
    fn.name = tool_name
    fn.arguments = json.dumps(tool_input)
    tc = MagicMock()
    tc.function = fn
    message = MagicMock()
    message.content = None
    message.tool_calls = [tc]
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    resp.usage.prompt_tokens = 210
    resp.usage.completion_tokens = 45
    resp.usage.cache_read_input_tokens = 0
    resp.usage.cache_creation_input_tokens = 0
    return resp


def _fake_litellm_sdk(response):
    fake = MagicMock()
    fake.exceptions.APIError = _FakeAPIError
    fake.completion.return_value = response
    return fake


def test_foto_durchlauf_schreibt_telemetrie_mit_foto_slot(tmp_path, monkeypatch):
    """AC3 (#1509): EIN Durchlauf durch FotoAnalyseProvider (echter LiteLLM-
    Vendor, mockiertes litellm-SDK) schreibt eine provider_calls.jsonl-Zeile
    mit caller=eltern-chat und dem Foto-Slot (litellm-Vendor-Segment).

    Beweist zugleich:
    - Bild-Block landet im litellm.completion-Call als OpenAI-image_url (AC1);
    - Slot trägt `litellm` (nicht mehr `anthropic`, #1509-Migration, AC2);
    - max_tokens wird durchgereicht (Token-Budget-Parität, Migrations-Disziplin).
    """
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    jsonl = tmp_path / "llm" / "provider_calls.jsonl"

    fake_litellm = _fake_litellm_sdk(
        _make_litellm_singleshot_response(
            "extract_termine",
            {"termine": [{"titel": "Sportfest", "beginn": "2026-09-15"}]},
        )
    )

    with patch.dict(sys.modules, {"litellm": fake_litellm}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from skills.foto_analyse import FOTO_ANALYSE_SLOT, FotoAnalyseProvider
        prov = FotoAnalyseProvider()
        out = prov.extract_termine(
            image_bytes=b"png-rohbytes", image_media_type="image/png",
            caption="Bitte termine 2026 eintragen")

    assert len(out) == 1
    assert out[0].titel == "Sportfest"

    # Telemetrie-Zeile mit Foto-Slot (AC3, Connector-Grundlage).
    line = json.loads(jsonl.read_text(encoding="utf-8").strip())
    assert line["caller"] == "eltern-chat"
    assert line["slot"] == FOTO_ANALYSE_SLOT
    assert "foto-analyse" in line["slot"]
    assert "litellm" in line["slot"]  # #1509: LiteLLM-Vendor-Segment
    assert line["model_id"] == "claude-opus-5"

    # Bild-Block landete im litellm.completion-Call (AC1 OpenAI-Vision-Wire-Form).
    call = fake_litellm.completion.call_args
    # max_tokens muss durchgereicht werden (Migrations-Disziplin, hoerspiel-502-Lektion).
    assert call.kwargs["max_tokens"] == 4096
    messages = call.kwargs["messages"]
    # System als eigene Message (system_message_distinct).
    assert messages[0]["role"] == "system"
    # User-Content ist die content-Liste [image_url-Block, text-Block].
    user_content = messages[1]["content"]
    assert isinstance(user_content, list)
    assert len(user_content) == 2
    image_block = user_content[0]
    text_block = user_content[1]
    assert image_block["type"] == "image_url"
    assert "image/png" in image_block["image_url"]["url"]
    assert image_block["image_url"]["url"].startswith("data:image/png;base64,")
    assert text_block["type"] == "text"
    assert text_block["text"].startswith("Begleittext der Familie:")
    # Forced tool_use (benannte Form).
    assert call.kwargs["tool_choice"] == {
        "type": "function", "function": {"name": "extract_termine"}}


# ----------------------------------------------------------------------
#  TAB-5 Content-Guard (#528): Verfeinerungs-/Jahr-Klausel im System-Prompt
# ----------------------------------------------------------------------

def test_TAB5_system_prompt_enthaelt_verfeinerungs_klausel():
    """TAB-5 / #528: _SYSTEM_PROMPT muss die Verfeinerungs-Klausel tragen, die
    Jahres-Ableitung aus dem Begleittext erlaubt (ohne Termine zu erfinden).
    Guard stellt sicher, dass zukünftige Prompt-Refactorings die Klausel nicht
    stillschweigend verlieren."""
    from skills.foto_analyse import _SYSTEM_PROMPT as prompt

    # Kernaussage: Begleittext als zulässige Quelle für fehlende Infos (Jahreszahl)
    assert "Begleittext" in prompt, "_SYSTEM_PROMPT fehlt 'Begleittext'-Referenz"
    assert "Verfeinerungs" in prompt, "_SYSTEM_PROMPT fehlt Verfeinerungs-Hinweis-Klausel"
    # Explizite Nennung von Jahreszahl-Ableitung aus dem Begleittext
    assert "Jahreszahl" in prompt, "_SYSTEM_PROMPT fehlt Jahreszahl-Klausel"
    # Keine Erfindung von Terminen (Anti-Halluzinations-Guard)
    assert "erfindet" in prompt, "_SYSTEM_PROMPT fehlt Erfindungs-Verbot-Klausel"
