"""LibSingleshotAdapter — hoerspiel-Folgen-Pfad über tools.llm (T1084).

Ohne Netz: die Lib-Singleshot-Fassade wird gemockt (`get_singleshot` am
Adapter-Import-Ort gepatcht). Geprüft:
  - complete_structured übersetzt die Signatur-Drift (user/input_schema →
    prompt/schema) und ruft die Fassade,
  - LibProviderError → hoerspiel ProviderError,
  - complete delegiert an den alt_provider,
  - Entry-Path: erzeuge_folgen_vorschlag(llm=Adapter) liefert
    {titel, text, folgen-nr-vorschlag} über den realen llm_service-Pfad.
"""

from unittest.mock import MagicMock, patch

import pytest

from hoerspiel import llm_service
from hoerspiel.providers.base import ProviderError


def _make_adapter(facade, alt_provider=None):
    """Baut einen LibSingleshotAdapter mit gemockter Lib-Fassade."""
    from hoerspiel.providers import lib_adapter
    with patch.object(lib_adapter, "get_singleshot", return_value=facade) as gs:
        adapter = lib_adapter.LibSingleshotAdapter(
            slot="hoerspiel-anthropic-api-key",
            model="claude-opus-4-7",
            alt_provider=alt_provider,
        )
    return adapter, gs


def _make_adapter_with_max_tokens(facade, max_tokens=0, alt_provider=None):
    """Baut einen LibSingleshotAdapter mit gemockter Lib-Fassade + max_tokens."""
    from hoerspiel.providers import lib_adapter
    with patch.object(lib_adapter, "get_singleshot", return_value=facade) as gs:
        adapter = lib_adapter.LibSingleshotAdapter(
            slot="hoerspiel-anthropic-api-key",
            model="claude-opus-4-7",
            alt_provider=alt_provider,
            max_tokens=max_tokens,
        )
    return adapter, gs


def test_complete_structured_translates_signature_drift():
    """user→prompt, input_schema→schema; correlation_id NICHT durchgereicht."""
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    facade.complete_structured.return_value = {"titel": "T", "text": "X",
                                               "folgen-nr-vorschlag": 1}
    adapter, gs = _make_adapter(facade)

    # Fassade EINMAL gebaut, mit Modell-Durchreichung (ohne max_tokens → Default-Pfad 0).
    gs.assert_called_once_with("hoerspiel-anthropic-api-key", "claude-opus-4-7", max_tokens=0)

    schema = {"type": "object"}
    out = adapter.complete_structured(
        "SYS", "USER",
        tool_name="folgen_vorschlag",
        tool_description="desc",
        input_schema=schema,
    )
    assert out == {"titel": "T", "text": "X", "folgen-nr-vorschlag": 1}
    # Signatur-Drift übersetzt: user→prompt, input_schema→schema.
    facade.complete_structured.assert_called_once_with(
        system="SYS",
        prompt="USER",
        schema=schema,
        tool_name="folgen_vorschlag",
        tool_description="desc",
    )
    # correlation_id wurde NICHT durchgereicht (V1-Entscheid None).
    assert "correlation_id" not in facade.complete_structured.call_args.kwargs


def test_lib_provider_error_maps_to_hoerspiel_provider_error():
    """tools.llm.ProviderError → hoerspiel providers.base.ProviderError."""
    from tools.llm import ProviderError as LibProviderError
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    facade.complete_structured.side_effect = LibProviderError("Anbieter weg")
    adapter, _gs = _make_adapter(facade)

    with pytest.raises(ProviderError):
        adapter.complete_structured(
            "S", "U", tool_name="t", tool_description="d", input_schema={})


def test_complete_delegates_to_alt_provider():
    """complete (Synopse, HSP-16) delegiert an den alt_provider."""
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    alt = MagicMock()
    alt.complete.return_value = "Eine kurze Synopse."
    adapter, _gs = _make_adapter(facade, alt_provider=alt)

    result = adapter.complete("SYS-SYNOPSE", "Folgentext")
    assert result == "Eine kurze Synopse."
    alt.complete.assert_called_once_with("SYS-SYNOPSE", "Folgentext")
    # Der Folgen-Pfad (Fassade) wurde NICHT angefasst.
    facade.complete_structured.assert_not_called()


def test_entry_path_erzeuge_folgen_vorschlag_through_adapter():
    """Entry-Path: erzeuge_folgen_vorschlag(llm=Adapter) → realer llm_service-
    Pfad grün, liefert {titel, text, folgen-nr-vorschlag}."""
    ergebnis = {
        "titel": "Stigi und der Trübsee",
        "folgen-nr-vorschlag": 23,
        "text": "Folge 23: Stigi und der Trübsee.\n\nStigi flog über das Tal.",
    }
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    facade.complete_structured.return_value = dict(ergebnis)
    adapter, _gs = _make_adapter(facade)

    out = llm_service.erzeuge_folgen_vorschlag(
        idee="Etwas über den Trübsee.",
        bible="Stigi ist ein Stieglitz.",
        historie="## Folge 22: ...",
        naechste_nummer=23,
        llm=adapter,
    )
    assert out["titel"] == "Stigi und der Trübsee"
    assert out["folgen-nr-vorschlag"] == 23
    assert out["text"].startswith("Folge 23:")
    # llm_service rief complete_structured mit dem HSP-11-Tool.
    kwargs = facade.complete_structured.call_args.kwargs
    assert kwargs["tool_name"] == llm_service.FOLGEN_TOOL_NAME
    assert kwargs["schema"] == llm_service.FOLGEN_INPUT_SCHEMA


def test_adapter_passes_max_tokens_to_get_singleshot():
    """LibSingleshotAdapter reicht max_tokens an get_singleshot durch (AC2).

    Prüft, dass der Adapter-Konstruktor mit max_tokens=8192 diesen Wert
    als Keyword-Argument an get_singleshot weitergibt — verhindert Trunkierung
    langer Folgentexte (T1084, DEFAULT_MAX_TOKENS=2048 < ~3500 Token Folge).
    """
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    _adapter, gs = _make_adapter_with_max_tokens(facade, max_tokens=8192)

    # get_singleshot wurde mit max_tokens=8192 gerufen.
    gs.assert_called_once_with(
        "hoerspiel-anthropic-api-key", "claude-opus-4-7", max_tokens=8192,
    )


def test_adapter_without_max_tokens_uses_default_path():
    """LibSingleshotAdapter ohne max_tokens → get_singleshot erhält max_tokens=0 (Default-Pfad)."""
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    _adapter, gs = _make_adapter_with_max_tokens(facade, max_tokens=0)

    gs.assert_called_once_with(
        "hoerspiel-anthropic-api-key", "claude-opus-4-7", max_tokens=0,
    )
