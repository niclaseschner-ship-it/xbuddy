"""get_singleshot — multimodaler `images`-Pfad (T1262, LLMP-S11).

Deckt den additiven `images`-Parameter der Singleshot-Sicht ab (llm-providers.md
LLMP-S1 `complete_structured(system, prompt, schema, *, images=None)`):

(a) `complete_structured(images=[…])` reicht den Bild-Block an den Vendor durch
    (Anthropic-Wire-Form `[image-Block, text-Block]`, base64 IM Vendor);
(b) `images=None` ist byte-identisch der heutige Text-Pfad (`content=prompt`) —
    Regression-frei für den hoerspiel-Bestand;
(c) `images` gegen einen Vendor OHNE `multimodal_input` → `LLMCapabilityError`
    (Cap-Gate in der LIB, LLMP-3/LLMP-S11).

Ohne Netz: Anthropic über einen Fake-SDK-Client (Spiegel test_singleshot.py),
der Cap-Gate-Vendor über ein Fake-Modul in `sys.modules` (Spiegel
test_public_api.py).
"""

import base64
import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


SCHEMA = {
    "type": "object",
    "properties": {"termine": {"type": "array", "items": {"type": "object"}}},
    "required": ["termine"],
}
ERGEBNIS = {"termine": [{"titel": "Sportfest", "beginn": "2026-09-15"}]}

FOTO_SLOT = "eltern-chat-anthropic-foto-analyse-api-key"


# ----------------------------------------------------------------------
#  Anthropic-Fakes (Spiegel test_singleshot.py)
# ----------------------------------------------------------------------

def _anthropic_tool_use_block(name, payload):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = payload
    return block


def _anthropic_response(blocks):
    resp = MagicMock()
    resp.content = blocks
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 30
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    resp.usage = usage
    return resp


def _fake_anthropic():
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception
    return fake, client


# ----------------------------------------------------------------------
#  (a) images-Durchreichung an den Vendor
# ----------------------------------------------------------------------

def test_complete_structured_images_reicht_bildblock_durch(jsonl_path):
    """(a) `images=[{bytes, media_type}]` → user-Content `[image-Block, text-
    Block]`; das Bild trägt base64-Daten (IM Vendor kodiert), der text-Block den
    Prompt. Forced tool_use bleibt. Telemetrie trägt den Foto-Slot (AC3)."""
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response(
        [_anthropic_tool_use_block("extract_termine", ERGEBNIS)])

    raw = b"\x89PNG-bild-rohbytes"
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot=FOTO_SLOT, model="claude-opus-4-7")
        out = ss.complete_structured(
            system="Du extrahierst Termine.",
            prompt="Bitte extrahiere ALLE Termine aus dem Bild.",
            schema=SCHEMA,
            tool_name="extract_termine",
            images=[{"bytes": raw, "media_type": "image/png"}],
        )

    assert out == ERGEBNIS
    call = client.messages.create.call_args
    content = call.kwargs["messages"][0]["content"]
    # user-Content ist die 2-Block-Liste [image, text] (nicht der reine String).
    assert isinstance(content, list)
    assert len(content) == 2
    image_block, text_block = content
    assert image_block["type"] == "image"
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    # base64 wurde IM Vendor gebildet (Konsument reicht Rohbytes).
    assert image_block["source"]["data"] == base64.standard_b64encode(raw).decode("ascii")
    assert text_block["type"] == "text"
    assert text_block["text"] == "Bitte extrahiere ALLE Termine aus dem Bild."
    # Forced tool_use bleibt (trägt extract_termine).
    assert call.kwargs["tool_choice"] == {"type": "tool", "name": "extract_termine"}

    # AC3 write_verification: eine provider_calls.jsonl-Zeile mit dem Foto-Slot.
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["slot"] == FOTO_SLOT
    assert parsed["caller"] == "eltern-chat"
    assert "foto-analyse" in parsed["slot"]


# ----------------------------------------------------------------------
#  (b) images=None ist byte-identisch der Text-Pfad
# ----------------------------------------------------------------------

def test_complete_structured_images_none_byte_identisch_textpfad(jsonl_path):
    """(b) `images=None` → user-Content ist der reine `prompt`-String (exakt die
    Alt-Form vor T1262) — kein Bild-Block, Regression-frei für hoerspiel."""
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response(
        [_anthropic_tool_use_block("ergebnis", ERGEBNIS)])

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key")
        ss.complete_structured(system="S", prompt="P", schema=SCHEMA)

    content = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert content == "P"
    assert isinstance(content, str)


def test_complete_structured_images_leer_liste_ist_textpfad(jsonl_path):
    """(b') Leere Liste (`images=[]`) ist ebenfalls der Text-Pfad — falsy ⇒ str-
    Content, kein Cap-Gate-Wurf (nur truthy images verlangt multimodal_input)."""
    fake_anthropic, client = _fake_anthropic()
    client.messages.create.return_value = _anthropic_response(
        [_anthropic_tool_use_block("ergebnis", ERGEBNIS)])

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_singleshot
        ss = get_singleshot(slot="hoerspiel-anthropic-api-key")
        ss.complete_structured(system="S", prompt="P", schema=SCHEMA, images=[])

    content = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert content == "P"


# ----------------------------------------------------------------------
#  (c) Cap-Gate: images gegen Vendor OHNE multimodal_input
# ----------------------------------------------------------------------

def _install_fake_vendor_no_multimodal(name):
    """Fake-Vendor-Modul: singleshot-fähig (structured_output +
    system_message_distinct), ABER OHNE `multimodal_input`."""
    module = types.ModuleType("tools.llm._vendor.%s" % name)
    module.CAPABILITIES = frozenset({"structured_output", "system_message_distinct"})

    class FakeVendor:
        model = "fake-no-mm"

        def __init__(self, *, api_key):
            self.api_key = api_key

        def singleshot_structured(self, **kwargs):  # pragma: no cover - Gate wirft davor
            raise AssertionError("Vendor darf bei images-Cap-Gate nicht erreicht werden")

    setattr(module, name.capitalize() + "Vendor", FakeVendor)
    sys.modules["tools.llm._vendor.%s" % name] = module
    return name


def test_complete_structured_images_ohne_multimodal_cap_wirft(jsonl_path):
    """(c) LLMP-S11: `images` gegen einen Vendor ohne `multimodal_input` wirft
    `LLMCapabilityError` (Cap-Gate in der LIB, zur Call-Zeit) — kein Vendor-Call,
    kein Silent-Drop. Der Text-Pfad (images=None) bleibt für den Vendor offen."""
    name = "fakenomm"
    _install_fake_vendor_no_multimodal(name)
    try:
        with patch("tools.llm.public_api.resolve_api_key", return_value="key-fake"):
            from tools.llm import LLMCapabilityError, get_singleshot
            ss = get_singleshot(slot="eltern-chat-%s-api-key" % name)
            # Text-Pfad bleibt offen (kein Wurf) — Gate greift NUR bei images.
            # (Der Fake-Vendor würde bei einem echten Call AssertionError werfen,
            #  daher hier nur der Gate-Zweig.)
            with pytest.raises(LLMCapabilityError) as exc:
                ss.complete_structured(
                    system="S", prompt="P", schema=SCHEMA,
                    images=[{"bytes": b"x", "media_type": "image/jpeg"}])
        assert "multimodal_input" in str(exc.value)
    finally:
        sys.modules.pop("tools.llm._vendor.%s" % name, None)
