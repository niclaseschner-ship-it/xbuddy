"""LibSingleshotAdapter — hoerspiel-Folgen-Pfad über tools.llm (T1084).

Ohne Netz: die Lib-Singleshot-Fassade wird gemockt (`get_singleshot` am
Adapter-Import-Ort gepatcht). Geprüft:
  - complete_structured übersetzt die Signatur-Drift (user/input_schema →
    prompt/schema) und ruft die Fassade,
  - LibProviderError → hoerspiel ProviderError,
  - complete (Synopse) läuft über die Lib-Completion-Sicht
    (get_completion), NICHT über die Singleshot-Fassade,
  - Entry-Path: erzeuge_folgen_vorschlag(llm=Adapter) liefert
    {titel, text, folgen-nr-vorschlag} über den realen llm_service-Pfad.
"""

from unittest.mock import MagicMock, patch

import pytest

from hoerspiel import llm_service
from hoerspiel.providers.base import ProviderError
from tools.llm import LLM_TIMEOUT_LONGFORM_SECONDS


def _make_adapter(facade, completion_facade=None):
    """Baut einen LibSingleshotAdapter mit gemockten Lib-Fassaden.

    `facade` ist die Singleshot-Fassade (get_singleshot); `completion_facade`
    die Freitext-Fassade (get_completion, #1131). Beide `get_*` werden am
    Adapter-Import-Ort gepatcht, damit der `__init__` keinen echten Vendor baut.
    """
    from hoerspiel.providers import lib_adapter
    if completion_facade is None:
        completion_facade = MagicMock(model="claude-opus-4-7")
    with patch.object(lib_adapter, "get_singleshot", return_value=facade) as gs, \
         patch.object(lib_adapter, "get_completion", return_value=completion_facade):
        adapter = lib_adapter.LibSingleshotAdapter(
            slot="hoerspiel-anthropic-api-key",
            model="claude-opus-4-7",
        )
    return adapter, gs


def _make_adapter_with_max_tokens(facade, max_tokens=0):
    """Baut einen LibSingleshotAdapter mit gemockten Lib-Fassaden + max_tokens."""
    from hoerspiel.providers import lib_adapter
    with patch.object(lib_adapter, "get_singleshot", return_value=facade) as gs, \
         patch.object(lib_adapter, "get_completion",
                      return_value=MagicMock(model="claude-opus-4-7")):
        adapter = lib_adapter.LibSingleshotAdapter(
            slot="hoerspiel-anthropic-api-key",
            model="claude-opus-4-7",
            max_tokens=max_tokens,
        )
    return adapter, gs


def test_recherche_agent_lazy_baut_get_agent_facade():
    """T1371: `recherche_agent()` baut die get_agent-Sicht LAZY (Slot+Modell+
    max_tokens), cached sie und baut sie nicht beim __init__ (Kind-Instanzen
    ziehen keine Agent-Fassade)."""
    from hoerspiel.providers import lib_adapter

    facade = MagicMock(model="claude-opus-4-7")
    agent_facade = MagicMock(name="agent", capabilities=frozenset({"web_search"}))
    with patch.object(lib_adapter, "get_singleshot", return_value=facade), \
         patch.object(lib_adapter, "get_completion",
                      return_value=MagicMock(model="claude-opus-4-7")), \
         patch.object(lib_adapter, "get_agent",
                      return_value=agent_facade) as ga:
        adapter = lib_adapter.LibSingleshotAdapter(
            slot="hoerspiel-anthropic-api-key", model="claude-opus-4-7",
            max_tokens=8192)
        # __init__ baut die Agent-Sicht NICHT (lazy).
        ga.assert_not_called()
        first = adapter.recherche_agent()
        second = adapter.recherche_agent()

    ga.assert_called_once_with(
        "hoerspiel-anthropic-api-key", "claude-opus-4-7", max_tokens=8192,
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS)
    assert first is agent_facade
    assert second is agent_facade  # gecacht
    assert "web_search" in first.capabilities


def test_recherche_agent_slot_decoupled_from_singleshot_slot():
    """T1454/AC3: `agent_slot` ENTKOPPELT den Recherche-Agent-Slot vom
    Struktur-/Synopse-Slot. singleshot/completion bekommen den (litellm-)`slot`,
    recherche_agent den anthropic-`agent_slot` (web_search bleibt Anthropic)."""
    from hoerspiel.providers import lib_adapter

    facade = MagicMock(model="claude-opus-4-7")
    agent_facade = MagicMock(name="agent", capabilities=frozenset({"web_search"}))
    with patch.object(lib_adapter, "get_singleshot", return_value=facade) as gs, \
         patch.object(lib_adapter, "get_completion",
                      return_value=MagicMock(model="claude-opus-4-7")) as gc, \
         patch.object(lib_adapter, "get_agent",
                      return_value=agent_facade) as ga:
        adapter = lib_adapter.LibSingleshotAdapter(
            slot="hoerspiel-litellm-claude-api-key",
            model="claude-opus-4-7",
            max_tokens=8192,
            agent_slot="hoerspiel-anthropic-api-key",
        )
        adapter.recherche_agent()

    # Struktur-/Synopse-Pfad läuft über den litellm-Motor-Slot.
    gs.assert_called_once_with(
        "hoerspiel-litellm-claude-api-key", "claude-opus-4-7", max_tokens=8192,
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS)
    gc.assert_called_once_with(
        "hoerspiel-litellm-claude-api-key", "claude-opus-4-7", max_tokens=8192,
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS)
    # Recherche-Agent bleibt auf dem anthropic-Slot (web_search-nativ).
    ga.assert_called_once_with(
        "hoerspiel-anthropic-api-key", "claude-opus-4-7", max_tokens=8192,
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS)


def test_recherche_agent_slot_defaults_to_slot_when_unset():
    """T1454: ohne `agent_slot` fällt der Recherche-Agent auf `slot` zurück
    (Rückwärtskompatibilität — Alt-/Test-Pfad)."""
    from hoerspiel.providers import lib_adapter

    facade = MagicMock(model="claude-opus-4-7")
    agent_facade = MagicMock(name="agent")
    with patch.object(lib_adapter, "get_singleshot", return_value=facade), \
         patch.object(lib_adapter, "get_completion",
                      return_value=MagicMock(model="claude-opus-4-7")), \
         patch.object(lib_adapter, "get_agent",
                      return_value=agent_facade) as ga:
        adapter = lib_adapter.LibSingleshotAdapter(
            slot="hoerspiel-litellm-claude-api-key", model="claude-opus-4-7")
        adapter.recherche_agent()

    ga.assert_called_once_with(
        "hoerspiel-litellm-claude-api-key", "claude-opus-4-7", max_tokens=0,
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS)


def test_complete_structured_translates_signature_drift():
    """user→prompt, input_schema→schema; correlation_id NICHT durchgereicht."""
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    facade.complete_structured.return_value = {"titel": "T", "text": "X",
                                               "folgen-nr-vorschlag": 1}
    adapter, gs = _make_adapter(facade)

    # Fassade EINMAL gebaut, mit Modell-Durchreichung (ohne max_tokens → Default-Pfad 0).
    gs.assert_called_once_with(
        "hoerspiel-anthropic-api-key", "claude-opus-4-7", max_tokens=0,
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS)

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


def test_complete_routes_through_completion_facade():
    """complete (Synopse, HSP-16) läuft über die Lib-Completion-Sicht
    (get_completion), NICHT über die Singleshot-Fassade."""
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    completion = MagicMock(model="claude-opus-4-7")
    completion.complete.return_value = "Eine kurze Synopse."
    adapter, _gs = _make_adapter(facade, completion_facade=completion)

    result = adapter.complete("SYS-SYNOPSE", "Folgentext")
    assert result == "Eine kurze Synopse."
    completion.complete.assert_called_once_with(
        system="SYS-SYNOPSE", user="Folgentext")
    # Der Folgen-Pfad (Singleshot-Fassade) wurde NICHT angefasst.
    facade.complete_structured.assert_not_called()


def test_complete_lib_provider_error_maps_to_hoerspiel_provider_error():
    """Freitext-complete-Pfad: tools.llm.ProviderError → hoerspiel
    providers.base.ProviderError (#1131, Spiegel complete_structured)."""
    from tools.llm import ProviderError as LibProviderError
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    completion = MagicMock(model="claude-opus-4-7")
    completion.complete.side_effect = LibProviderError("Anbieter weg")
    adapter, _gs = _make_adapter(facade, completion_facade=completion)

    with pytest.raises(ProviderError):
        adapter.complete("S", "U")


def test_adapter_passes_max_tokens_to_get_completion():
    """LibSingleshotAdapter reicht max_tokens auch an get_completion durch
    (#1131, AC3 — Synopse-Freitext ohne Trunkierung)."""
    from hoerspiel.providers import lib_adapter
    facade = MagicMock(model="claude-opus-4-7")
    completion = MagicMock(model="claude-opus-4-7")
    with patch.object(lib_adapter, "get_singleshot", return_value=facade), \
         patch.object(lib_adapter, "get_completion",
                      return_value=completion) as gc:
        lib_adapter.LibSingleshotAdapter(
            slot="hoerspiel-anthropic-api-key",
            model="claude-opus-4-7",
            max_tokens=8192,
        )
    gc.assert_called_once_with(
        "hoerspiel-anthropic-api-key", "claude-opus-4-7", max_tokens=8192,
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS,
    )


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


def test_entry_path_erzeuge_synopse_through_adapter():
    """Entry-Path (#1131, AC3): erzeuge_synopse(llm=Adapter) → realer
    llm_service-Pfad läuft über die Lib-Completion-Sicht."""
    facade = MagicMock(model="claude-opus-4-7")
    completion = MagicMock(model="claude-opus-4-7")
    completion.complete.return_value = "  Stigi lernt Mut am Trübsee.  "
    adapter, _gs = _make_adapter(facade, completion_facade=completion)

    out = llm_service.erzeuge_synopse(
        titel="Stigi und der Trübsee",
        text="Folge 23: Stigi und der Trübsee.\n\nStigi flog über das Tal.",
        llm=adapter,
    )
    # erzeuge_synopse strippt das Ergebnis (llm_service.py:135).
    assert out == "Stigi lernt Mut am Trübsee."
    # llm_service rief complete → Completion-Fassade (System=SYNOPSE_PROMPT).
    completion.complete.assert_called_once()
    kwargs = completion.complete.call_args.kwargs
    assert kwargs["system"] == llm_service.SYNOPSE_PROMPT
    assert "Stigi und der Trübsee" in kwargs["user"]


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
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS,
    )


def test_adapter_without_max_tokens_uses_default_path():
    """LibSingleshotAdapter ohne max_tokens → get_singleshot erhält max_tokens=0 (Default-Pfad)."""
    facade = MagicMock()
    facade.model = "claude-opus-4-7"
    _adapter, gs = _make_adapter_with_max_tokens(facade, max_tokens=0)

    gs.assert_called_once_with(
        "hoerspiel-anthropic-api-key", "claude-opus-4-7", max_tokens=0,
        timeout=LLM_TIMEOUT_LONGFORM_SECONDS,
    )
