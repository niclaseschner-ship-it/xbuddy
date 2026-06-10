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
    SYSTEM_PROMPT,
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


# --- TAB-5 Caption-Steuerung (#528) -----------------------------------------

def test_TAB5_caption_jahr_hinweis_fliesst_durch(monkeypatch):
    """AC1: Caption 'Jahr 2026 verwenden' erreicht den Transport und der
    Adapter liefert den Termin mit 2026 zurück — TAB-5 Z. 190-201."""
    received_captions = []

    def fake_transport(*, image_bytes, image_media_type, caption):
        received_captions.append(caption)
        # Transport simuliert LLM, das den Jahr-Hinweis aus der Caption anwendet.
        return [{"titel": "Sportfest", "beginn": "2026-05-10", "ganztags": True}]

    adapter = ClaudeMultimodalProvider(
        api_key="fake-key", transport=fake_transport)
    out = adapter.extract_termine(
        image_bytes=b"img",
        image_media_type="image/jpeg",
        caption="Jahr 2026 verwenden")

    assert len(received_captions) == 1
    assert "2026" in received_captions[0]
    assert len(out) == 1
    assert out[0].beginn.startswith("2026")


def test_TAB5_caption_leer_default_unverändert():
    """AC2: Kein Caption-Hinweis → Default-Verhalten: Transport liefert
    Plan-Datum 1:1, kein Jahr-Override — TAB-5 Z. 190-201."""
    def fake_transport(*, image_bytes, image_media_type, caption):
        # Caption ist leer; der Transport liefert das Datum aus dem Bild.
        assert caption == ""
        return [{"titel": "Elternabend", "beginn": "2025-11-03", "ganztags": True}]

    adapter = ClaudeMultimodalProvider(
        api_key="fake-key", transport=fake_transport)
    out = adapter.extract_termine(
        image_bytes=b"img",
        image_media_type="image/jpeg",
        caption="")

    assert len(out) == 1
    assert out[0].beginn == "2025-11-03"


def test_TAB5_system_prompt_enthaelt_verfeinerungs_klausel():
    """AC3: SYSTEM_PROMPT trägt die E-TAB-5-konforme Caption-Steuerungs-Klausel
    (Verfeinerungs-Hinweis, kein Erfinden) — TAB-5 Z. 190-201."""
    assert "Begleittext" in SYSTEM_PROMPT
    assert "Verfeinerungs-Hinweis" in SYSTEM_PROMPT
    assert "erfindet" in SYSTEM_PROMPT or "erfinde" in SYSTEM_PROMPT.lower()
    # Schema: beginn-Beschreibung trägt Jahr-Ableitungs-Klausel.
    beginn_desc = TOOL_SCHEMA["properties"]["termine"]["items"][
        "properties"]["beginn"]["description"]
    assert "Begleittext" in beginn_desc
    assert "Jahreszahl" in beginn_desc or "Jahr" in beginn_desc


# --- TAB-5 Live-Pfad: _call_anthropic via Mock (#528 Watchdog-Linse 7) ------

def _make_tool_use_response(termine_items):
    """Baut ein Mock-Response-Objekt, wie anthropic.Anthropic.messages.create
    es liefern würde, mit einem tool_use-Block für extract_termine."""
    from unittest.mock import MagicMock
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_termine"
    block.input = {"termine": termine_items}
    response = MagicMock()
    response.content = [block]
    return response


def test_TAB5_call_anthropic_system_prompt_traegt_verfeinerungsklausel():
    """AC1 (Watchdog-Linse 7): _call_anthropic sendet system= mit dem
    Verfeinerungs-Wortlaut (Begleittext + Verfeinerungs-Hinweis) — TAB-5 Z. 190-201.
    Wenn jemand _SYSTEM_PROMPT entfernt oder die system=-Übergabe löscht, schlägt
    dieser Test fehl."""
    from unittest.mock import MagicMock

    fake_response = _make_tool_use_response(
        [{"titel": "Sportfest", "beginn": "2026-05-10", "ganztags": True}])

    provider = ClaudeMultimodalProvider(api_key="fake-key")
    # Direkt self._client setzen — kein echtes anthropic-SDK nötig.
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response
    provider._client = mock_client

    provider.extract_termine(
        image_bytes=b"fake-image",
        image_media_type="image/jpeg",
        caption="Jahr 2026 verwenden")

    assert mock_client.messages.create.called
    call_kwargs = mock_client.messages.create.call_args
    system_arg = call_kwargs.kwargs.get("system") or call_kwargs.args[0] \
        if call_kwargs.args else call_kwargs.kwargs.get("system")
    # call() nutzt ausschließlich kwargs in _call_anthropic
    system_arg = mock_client.messages.create.call_args.kwargs["system"]
    assert "Begleittext" in system_arg, \
        "system= muss 'Begleittext' enthalten (TAB-5 Verfeinerungs-Wortlaut)"
    assert "Verfeinerungs-Hinweis" in system_arg, \
        "system= muss 'Verfeinerungs-Hinweis' enthalten (TAB-5 Z. 190-201)"


def test_TAB5_call_anthropic_tool_schema_traegt_begleittext_klausel():
    """AC2 (Watchdog-Linse 7): _call_anthropic übergibt tools[0].input_schema
    (TOOL_SCHEMA) mit beginn-Description, die Begleittext-/Jahr-Klausel trägt
    — TAB-5 Z. 190-201."""
    from unittest.mock import MagicMock

    fake_response = _make_tool_use_response(
        [{"titel": "Elternabend", "beginn": "2026-11-03", "ganztags": True}])

    provider = ClaudeMultimodalProvider(api_key="fake-key")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response
    provider._client = mock_client

    provider.extract_termine(
        image_bytes=b"img",
        image_media_type="image/jpeg",
        caption="Jahr 2026 verwenden")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    tools_arg = call_kwargs["tools"]
    assert len(tools_arg) == 1, "genau ein Tool erwartet"
    input_schema = tools_arg[0]["input_schema"]
    beginn_desc = (
        input_schema["properties"]["termine"]["items"]
        ["properties"]["beginn"]["description"]
    )
    assert "Begleittext" in beginn_desc, \
        "beginn-Beschreibung muss 'Begleittext' enthalten (TAB-5 Jahr-Ableitung)"
    assert "Jahr" in beginn_desc, \
        "beginn-Beschreibung muss Jahres-Hinweis enthalten (TAB-5 Z. 190-201)"


def test_TAB5_call_anthropic_user_content_hat_image_und_caption():
    """AC3 (Watchdog-Linse 7): _call_anthropic baut messages[0].content als
    [image-Block, text-Block]; text-Block trägt den Caption-Text — TAB-5 Z. 190-201.
    Sichert, dass die Caption tatsächlich im API-Aufruf landet."""
    from unittest.mock import MagicMock

    caption = "Jahr 2026 verwenden — nur Geburtstage"
    fake_response = _make_tool_use_response(
        [{"titel": "Geburtstag Mia", "beginn": "2026-03-14", "ganztags": True}])

    provider = ClaudeMultimodalProvider(api_key="fake-key")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response
    provider._client = mock_client

    provider.extract_termine(
        image_bytes=b"img-bytes",
        image_media_type="image/png",
        caption=caption)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    messages_arg = call_kwargs["messages"]
    assert len(messages_arg) == 1, "genau ein user-Turn erwartet"
    user_content = messages_arg[0]["content"]
    assert len(user_content) == 2, "user_content muss image-Block + text-Block haben"

    image_block = user_content[0]
    assert image_block["type"] == "image", "erster Block muss image sein"
    assert image_block["source"]["media_type"] == "image/png"

    text_block = user_content[1]
    assert text_block["type"] == "text", "zweiter Block muss text sein"
    assert caption in text_block["text"], \
        "text-Block muss den Caption-Text enthalten (TAB-5 Z. 190-201)"
