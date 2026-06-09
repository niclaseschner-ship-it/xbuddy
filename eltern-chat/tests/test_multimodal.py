"""Tests für die Multimodal-Provider-Naht — specs/platform/termine-aus-bild.md
TAB-5 (Refs #475).

Prüft:
- `get_multimodal_provider("claude", ...)` liefert einen Adapter.
- Unbekannter Name → ValueError.
- Der Claude-Adapter mit gestubbter `transport`-Naht hebt rohe Items
  (Liste of Dicts aus dem Tool-Use-Result) in `ExtractedTermin`-Objekte.
- Transport-Fehler werden zu `MultimodalError`.
- TAB-4-Spec: das Tool-Schema/Description sind hart-codiert und stabil.
"""

import pytest
from skills._multimodal import (
    ExtractedTermin,
    MultimodalError,
    MultimodalProvider,
    get_multimodal_provider,
)
from skills._multimodal.claude import (
    TOOL_DESCRIPTION,
    TOOL_NAME,
    TOOL_SCHEMA,
    ClaudeMultimodalProvider,
)


def test_get_multimodal_provider_claude():
    """V1: `get_multimodal_provider('claude', ...)` liefert einen Adapter."""
    provider = get_multimodal_provider("claude", api_key="fake-key", model="")
    assert isinstance(provider, MultimodalProvider)
    assert isinstance(provider, ClaudeMultimodalProvider)


def test_get_multimodal_provider_unbekannt():
    """Unbekannter Anbieter-Name → ValueError (analog providers.get_provider)."""
    with pytest.raises(ValueError, match="unbekannter multimodaler"):
        get_multimodal_provider("openai", api_key="fake-key", model="")


def test_TAB5_tool_schema_ist_hart_codiert():
    """TAB-5: Tool-Name, Beschreibung und Schema sind hart-codiert (E-EC-4 /
    stabile Schnittstelle). Keine Modell-Formulierung."""
    assert TOOL_NAME == "extract_termine"
    assert isinstance(TOOL_DESCRIPTION, str)
    assert TOOL_DESCRIPTION
    assert TOOL_SCHEMA["type"] == "object"
    # Tool-Schema-Form: termine-Liste mit Pflicht titel + beginn.
    assert "termine" in TOOL_SCHEMA["properties"]
    item_schema = TOOL_SCHEMA["properties"]["termine"]["items"]
    assert set(item_schema["required"]) == {"titel", "beginn"}


def test_claude_adapter_extract_termine_mit_transport():
    """Transport-Naht: das gestubbte transport-Callable liefert rohe Items;
    der Adapter hebt sie in `ExtractedTermin`-Objekte (TAB-5)."""
    def fake_transport(*, image_bytes, image_media_type, caption):
        assert image_bytes == b"fake-image"
        assert image_media_type == "image/jpeg"
        assert "termine" in caption.lower()
        return [
            {"titel": "Sportfest",
             "beginn": "2026-09-15",
             "ganztags": True,
             "personen_hinweise": "Klasse 3b"},
            {"titel": "Elternabend",
             "beginn": "2026-09-22T18:00:00+02:00",
             "ende": "2026-09-22T20:00:00+02:00",
             "ganztags": False},
        ]

    adapter = ClaudeMultimodalProvider(
        api_key="fake-key", transport=fake_transport)
    out = adapter.extract_termine(
        image_bytes=b"fake-image",
        image_media_type="image/jpeg",
        caption="Bitte termine eintragen")
    assert len(out) == 2
    assert all(isinstance(t, ExtractedTermin) for t in out)
    assert out[0].titel == "Sportfest"
    assert out[0].beginn == "2026-09-15"
    assert out[0].personen_hinweise == "Klasse 3b"
    assert out[1].ende.endswith("+02:00")


def test_claude_adapter_extract_termine_leere_liste():
    """Anbieter erkennt keine Termine → leere Liste (kein Fehler) — TAB-6
    bewertet das nachgelagert als „unklar"."""
    def fake_transport(*, image_bytes, image_media_type, caption):
        return []

    adapter = ClaudeMultimodalProvider(
        api_key="fake-key", transport=fake_transport)
    out = adapter.extract_termine(
        image_bytes=b"x", image_media_type="image/jpeg", caption="termine")
    assert out == []


def test_claude_adapter_transport_fehler_wird_multimodalerror():
    """Wirft der Transport (Anthropic-API, Netz, …), übersetzt der Adapter
    das in `MultimodalError` — der TAB-Skill fängt nur diese eine Klasse
    (TAB-5 → provider_fehler)."""
    def boom_transport(*, image_bytes, image_media_type, caption):
        raise RuntimeError("simulated network failure")

    adapter = ClaudeMultimodalProvider(
        api_key="fake-key", transport=boom_transport)
    with pytest.raises(MultimodalError):
        adapter.extract_termine(
            image_bytes=b"x", image_media_type="image/jpeg", caption="termine")


def test_claude_adapter_transport_falsche_form_wird_multimodalerror():
    """Liefert der Transport keine Liste, wirft der Adapter `MultimodalError`."""
    def bad_transport(*, image_bytes, image_media_type, caption):
        return "not-a-list"

    adapter = ClaudeMultimodalProvider(
        api_key="fake-key", transport=bad_transport)
    with pytest.raises(MultimodalError):
        adapter.extract_termine(
            image_bytes=b"x", image_media_type="image/jpeg", caption="termine")


def test_claude_adapter_ohne_bild_wirft():
    """Leeres `image_bytes` ist Vertrags-Verletzung → MultimodalError."""
    adapter = ClaudeMultimodalProvider(api_key="fake-key", transport=lambda **_: [])
    with pytest.raises(MultimodalError):
        adapter.extract_termine(
            image_bytes=b"", image_media_type="image/jpeg", caption="termine")
