"""Tests für den Mistral-Multimodal-Adapter — E-TAB-6 V2 / EC-17 (Refs #508).

AC4: MistralMultimodalProvider implementiert extract_termine() mit demselben
Tool-Schema wie ClaudeMultimodalProvider. Kein Netz-Aufruf — httpx und der
transport-Slot sind Doppelungen.

Pflicht-Test aus #508-Body:
  test_v2_zweiter_adapter_kann_eingesteckt_werden
"""

import json

import pytest

# ============================================================
#  Hilfskonstrukte
# ============================================================

class _FakeHttpxResponse:
    """Doppelung einer httpx-Response mit Tool-Call-Inhalt."""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class _FakeHttpx:
    """Doppelung von httpx.post — gibt eine vorkonfigurierte Antwort zurück."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def post(self, url, *, headers, content, timeout):
        self.calls.append({
            "url": url,
            "payload": json.loads(content),
        })
        return self._response


def _mistral_tool_response(termine_list):
    """Baut eine Mistral-API-Antwort mit einem `extract_termine`-Tool-Call."""
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-tab-1",
                    "type": "function",
                    "function": {
                        "name": "extract_termine",
                        "arguments": json.dumps({"termine": termine_list}),
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "model": "mistral-medium-3504",
    }


def _build_multimodal_provider(monkeypatch, termine_list, status_code=200):
    """Baut einen MistralMultimodalProvider, dessen httpx.post ersetzt ist."""
    import skills._multimodal.mistral as mistral_mod
    from skills._multimodal.mistral import MistralMultimodalProvider

    fake_httpx = _FakeHttpx(
        _FakeHttpxResponse(status_code, _mistral_tool_response(termine_list)))
    monkeypatch.setattr(mistral_mod.httpx, "post", fake_httpx.post)
    provider = MistralMultimodalProvider(api_key="test-key",
                                         model="mistral-medium-3504")
    return provider, fake_httpx


# ============================================================
#  Pflicht-Test aus #508-Body
# ============================================================

def test_v2_zweiter_adapter_kann_eingesteckt_werden():
    """AC4 / #508-Pflicht-Test: der Mistral-Adapter kann über
    get_multimodal_provider() eingesteckt werden — Factory-Naht hält."""
    from skills._multimodal import get_multimodal_provider
    from skills._multimodal.mistral import MistralMultimodalProvider

    provider = get_multimodal_provider("mistral", api_key="test-key")
    assert isinstance(provider, MistralMultimodalProvider)


# ============================================================
#  AC4 — extract_termine() über transport-Naht
# ============================================================

def test_AC4_extract_termine_transport_naht():
    """AC4: extract_termine() über die transport-Naht liefert ExtractedTermin-
    Objekte — kein echter Netz-Aufruf."""
    from skills._multimodal.mistral import MistralMultimodalProvider

    def _transport(image_bytes, image_media_type, caption):
        return [{"titel": "Sportfest", "beginn": "2026-09-15", "ganztags": True}]

    provider = MistralMultimodalProvider(api_key="test-key", transport=_transport)
    result = provider.extract_termine(
        image_bytes=b"fake",
        image_media_type="image/jpeg",
        caption="termine eintragen")

    assert len(result) == 1
    assert result[0].titel == "Sportfest"
    assert result[0].beginn == "2026-09-15"
    assert result[0].ganztags is True


def test_AC4_extract_termine_leeres_bild_wirft():
    """AC4: leere image_bytes lösen MultimodalError aus."""
    from skills._multimodal.base import MultimodalError
    from skills._multimodal.mistral import MistralMultimodalProvider

    provider = MistralMultimodalProvider(api_key="test-key")
    with pytest.raises(MultimodalError):
        provider.extract_termine(
            image_bytes=b"",
            image_media_type="image/jpeg",
            caption="")


def test_AC4_extract_termine_http_aufruf(monkeypatch):
    """AC4: extract_termine() baut den korrekten HTTP-Aufruf — Tool-Choice
    erzwingt das extract_termine-Tool."""
    termine = [{"titel": "Elternabend", "beginn": "2026-10-05", "ganztags": True}]
    provider, fake = _build_multimodal_provider(monkeypatch, termine)

    result = provider.extract_termine(
        image_bytes=b"fake-image-bytes",
        image_media_type="image/jpeg",
        caption="Schulplan 2026")

    assert len(result) == 1
    assert result[0].titel == "Elternabend"

    call = fake.calls[0]
    payload = call["payload"]
    # Tool-Choice muss das extract_termine-Tool erzwingen.
    assert payload["tool_choice"]["type"] == "function"
    assert payload["tool_choice"]["function"]["name"] == "extract_termine"
    # System-Prompt muss vorhanden sein.
    assert any(m["role"] == "system" for m in payload["messages"])
    # User-Nachricht enthält Bild (image_url) und Text.
    user_msg = next(m for m in payload["messages"] if m["role"] == "user")
    content = user_msg["content"]
    types = [c["type"] for c in content]
    assert "image_url" in types
    assert "text" in types


def test_AC4_extract_termine_bild_als_data_url(monkeypatch):
    """AC4: das Bild wird als data-URL (base64) in image_url.url übergeben."""
    import base64
    provider, fake = _build_multimodal_provider(monkeypatch, [])

    image_bytes = b"\xff\xd8\xff"  # JPEG-Magic-Bytes
    provider.extract_termine(
        image_bytes=image_bytes,
        image_media_type="image/jpeg",
        caption="test")

    payload = fake.calls[0]["payload"]
    user_msg = next(m for m in payload["messages"] if m["role"] == "user")
    image_block = next(c for c in user_msg["content"] if c["type"] == "image_url")
    url = image_block["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    # Base64-Daten korrekt rekonstruierbar.
    b64_part = url.split(",", 1)[1]
    assert base64.standard_b64decode(b64_part) == image_bytes


def test_AC4_extract_termine_leere_liste_kein_fehler(monkeypatch):
    """AC4: eine erfolgreich leere Termin-Liste ist kein Fehler — der Anbieter
    hat keine Termine erkannt."""
    provider, _ = _build_multimodal_provider(monkeypatch, [])

    result = provider.extract_termine(
        image_bytes=b"fake",
        image_media_type="image/jpeg",
        caption="")
    assert result == []


# ============================================================
#  AC4 — Fehler-Wrapping
# ============================================================

def test_AC4_http_fehler_wird_als_multimodal_error_verpackt(monkeypatch):
    """AC4: ein HTTP-Fehler wird als MultimodalError verpackt."""
    import skills._multimodal.mistral as mistral_mod
    from skills._multimodal.base import MultimodalError
    from skills._multimodal.mistral import MistralMultimodalProvider

    fake_httpx = _FakeHttpx(
        _FakeHttpxResponse(500, {"error": "internal server error"}))
    monkeypatch.setattr(mistral_mod.httpx, "post", fake_httpx.post)
    provider = MistralMultimodalProvider(api_key="test-key")

    with pytest.raises(MultimodalError) as exc_info:
        provider.extract_termine(
            image_bytes=b"fake",
            image_media_type="image/jpeg",
            caption="")
    assert "500" in str(exc_info.value)


def test_AC4_netzwerkfehler_wird_als_multimodal_error_verpackt(monkeypatch):
    """AC4: ein Netzwerkfehler (httpx.RequestError) wird als MultimodalError
    verpackt."""
    import skills._multimodal.mistral as mistral_mod
    from skills._multimodal.base import MultimodalError
    from skills._multimodal.mistral import MistralMultimodalProvider

    def _fail(*args, **kwargs):
        raise mistral_mod.httpx.RequestError("Verbindung verweigert")

    monkeypatch.setattr(mistral_mod.httpx, "post", _fail)
    provider = MistralMultimodalProvider(api_key="test-key")

    with pytest.raises(MultimodalError) as exc_info:
        provider.extract_termine(
            image_bytes=b"fake",
            image_media_type="image/jpeg",
            caption="")
    assert "Netzwerkfehler" in str(exc_info.value)


def test_AC4_transport_fehler_wird_vereinheitlicht():
    """AC4: ein Nicht-MultimodalError aus dem transport wird als MultimodalError
    verpackt."""
    from skills._multimodal.base import MultimodalError
    from skills._multimodal.mistral import MistralMultimodalProvider

    def _fail_transport(**kwargs):
        raise RuntimeError("transport kaputt")

    provider = MistralMultimodalProvider(
        api_key="test-key", transport=_fail_transport)

    with pytest.raises(MultimodalError) as exc_info:
        provider.extract_termine(
            image_bytes=b"fake",
            image_media_type="image/jpeg",
            caption="")
    assert "transport-Fehler" in str(exc_info.value)


# ============================================================
#  AC4 — Tool-Schema-Stabilität (analog TAB-5-Tests für Claude)
# ============================================================

def test_AC4_tool_schema_identisch_mit_claude():
    """AC4: das Tool-Schema von Mistral ist identisch mit dem Claude-Schema —
    gleicher _TOOL_NAME, gleiche required-Felder."""
    from skills._multimodal.claude import TOOL_NAME as claude_name
    from skills._multimodal.claude import TOOL_SCHEMA as claude_schema
    from skills._multimodal.mistral import TOOL_NAME as mistral_name
    from skills._multimodal.mistral import TOOL_SCHEMA as mistral_schema

    assert mistral_name == claude_name == "extract_termine"
    # Pflicht-Felder müssen übereinstimmen.
    assert (mistral_schema["properties"]["termine"]["items"]["required"]
            == claude_schema["properties"]["termine"]["items"]["required"])


# ============================================================
#  AC4 — Pixtral-Ausschluss: Modell-Default ist NICHT Pixtral
# ============================================================

def test_AC4_pixtral_nicht_default():
    """E-TAB-6 Z.878-884: der Modell-Default des MistralMultimodalProvider
    ist NICHT ein Pixtral-Modell."""
    from skills._multimodal.mistral import MistralMultimodalProvider
    assert "pixtral" not in MistralMultimodalProvider._FALLBACK_MODEL.lower()


# ============================================================
#  AC4 — get_multimodal_provider: Claude-Pfad unverändert
# ============================================================

def test_AC4_claude_pfad_unveraendert():
    """AC2: der Claude-Pfad in skills/_multimodal/__init__.py bleibt
    unverändert — kein Verhaltens-Drift."""
    from skills._multimodal import get_multimodal_provider
    from skills._multimodal.claude import ClaudeMultimodalProvider

    provider = get_multimodal_provider("claude", api_key="test-key")
    assert isinstance(provider, ClaudeMultimodalProvider)


def test_AC4_unbekannter_anbieter_wirft():
    """AC4: unbekannter multimodaler Anbieter-Name → ValueError."""
    from skills._multimodal import get_multimodal_provider
    with pytest.raises(ValueError, match="unbekannter"):
        get_multimodal_provider("unbekannt", api_key="egal")
