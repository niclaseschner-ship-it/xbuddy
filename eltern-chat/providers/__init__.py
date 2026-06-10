"""KI-Anbieter-Adapter — siehe specs/platform/eltern-chat.md EC-11, E-EC-6
(Refs #27).

Jeder Adapter übersetzt zwischen dem kanonischen Modell (model.py) und der
konkreten Anbieter-API. Der Agent-Kern kennt nur das kanonische Modell; der
Anbieterwechsel ist eine reine Konfigurations-Änderung (EC-11).

V1 liefert nur den Claude-Adapter. Weitere Adapter werden additiv ergänzt — und
NICHT auf Vorrat (E-EC-6, CLAUDE.md §6).
"""


def get_provider(name, api_key, model=""):
    """Liefert den Anbieter-Adapter zum konfigurierten Namen (EC-11).

    Ein Adapter erfüllt das Protokoll `generate(GenerationRequest) ->
    GenerationResponse`. Unbekannte Namen sind ein Konfigurationsfehler.
    """
    if name == "claude":
        # Lazy-Import: das anthropic-SDK wird nur geladen, wenn der
        # Claude-Adapter tatsächlich verwendet wird (Tests laufen ohne SDK).
        from .claude import ClaudeProvider
        return ClaudeProvider(api_key=api_key, model=model)
    if name == "mistral":
        # Lazy-Import: httpx wird nur geladen, wenn der Mistral-Adapter
        # tatsächlich verwendet wird (EC-11, #508).
        from .mistral import MistralProvider
        return MistralProvider(api_key=api_key, model=model)
    raise ValueError("unbekannter KI-Anbieter: %r" % name)
