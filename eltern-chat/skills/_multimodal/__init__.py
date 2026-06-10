"""Multimodal-Provider-Naht für den TAB-Skill — specs/platform/termine-aus-bild.md
TAB-5 (Refs #475).

Diese Naht ist **separat** vom Konversations-Pfad (`providers/`): der TAB-Skill
ruft den multimodalen Anbieter mit einem hart-codierten Tool-Schema und einem
`image`-Content-Block auf (TAB-5). Der bestehende `providers.claude.ClaudeProvider`
ist für den Konversations-Pfad (EC-6) zuständig und nimmt Tool-Definitionen
aus dem Aufgaben-Katalog — TAB braucht das **domänenspezifische** Tool-Schema
(Termin-Liste), das nicht in den Konversations-Pfad gehört.

V1 (E-TAB-6): nur Claude. Weitere Adapter werden additiv ergänzt, sobald die
V2-Anbieter-Wahl (OPEN-TAB-Privacy) eine zweite Möglichkeit aufnimmt.

Öffentliche API:
- `MultimodalProvider`-Protocol (`base.py`)
- `ExtractedTermin` / `MultimodalError` (`base.py`)
- `get_multimodal_provider(name, api_key, model)` (`__init__.py`)
"""

from skills._multimodal.base import (
    ExtractedTermin,
    MultimodalError,
    MultimodalProvider,
)


def get_multimodal_provider(name, api_key, model=""):
    """Liefert den multimodalen Anbieter-Adapter zum konfigurierten Namen
    (TAB-5, E-TAB-6).

    `name`    — Anbieter-Bezeichnung (V1: nur `"claude"`).
    `api_key` — API-Schlüssel des Anbieters (EC-15).
    `model`   — Modell-ID; leer → Anbieter-Default (`cfg.provider_model`-Linie).

    Wirft `ValueError` bei unbekanntem Namen — analog `providers.get_provider`.
    """
    if name == "claude":
        # Lazy-Import: `anthropic` wird nur geladen, wenn der Claude-Adapter
        # tatsächlich verwendet wird (Tests laufen ohne SDK).
        from skills._multimodal.claude import ClaudeMultimodalProvider
        return ClaudeMultimodalProvider(api_key=api_key, model=model)
    if name == "mistral":
        # Lazy-Import: `httpx` wird nur geladen, wenn der Mistral-Adapter
        # tatsächlich verwendet wird (E-TAB-6 V2, #508).
        from skills._multimodal.mistral import MistralMultimodalProvider
        return MistralMultimodalProvider(api_key=api_key, model=model)
    raise ValueError("unbekannter multimodaler KI-Anbieter: %r" % name)


__all__ = (
    "ExtractedTermin",
    "MultimodalError",
    "MultimodalProvider",
    "get_multimodal_provider",
)
